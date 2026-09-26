"""Evidence-integrity tests: audit queue, run-commit gate, disk quota (T61, T07, T59).

Guide 11.5: a full writer queue must backpressure or fail explicitly — never
drop — and RUN_SUCCESS is only reachable after required artifacts are flushed.
"""

from __future__ import annotations

import threading
import time

import pytest

from crypto_regime_lab.evidence.audit_queue import (
    AuditQueueClosed, AuditQueueOverflow, BoundedAuditQueue, QueueFullPolicy, RunCommitGate,
)
from crypto_regime_lab.safety.process import disk_usage_report


def _collecting_sink(store: list[dict]):
    def sink(batch: list[dict]) -> int:
        store.extend(batch)
        return len(batch)
    return sink


def test_no_drop_policy_exists():
    """There must be no way to configure silent dropping."""
    assert {p.value for p in QueueFullPolicy} == {"backpressure", "explicit_fail"}


def test_full_queue_fails_explicitly_rather_than_dropping():
    store: list[dict] = []
    q = BoundedAuditQueue(sink=_collecting_sink(store), maxsize=3, policy=QueueFullPolicy.EXPLICIT_FAIL)
    for i in range(3):
        q.offer({"i": i})
    with pytest.raises(AuditQueueOverflow):
        q.offer({"i": 3})
    assert q.stats()["dropped"] == 0
    assert q.flush() == 3
    assert [r["i"] for r in store] == [0, 1, 2]


def test_backpressure_blocks_the_producer_until_the_writer_drains():
    store: list[dict] = []
    q = BoundedAuditQueue(sink=_collecting_sink(store), maxsize=2,
                          policy=QueueFullPolicy.BACKPRESSURE, backpressure_timeout_s=5.0)
    q.offer({"i": 0})
    q.offer({"i": 1})
    blocked = threading.Event()
    done = threading.Event()

    def producer():
        blocked.set()
        q.offer({"i": 2})   # must block, not drop
        done.set()

    thread = threading.Thread(target=producer, daemon=True)
    thread.start()
    blocked.wait(timeout=2)
    time.sleep(0.2)
    assert not done.is_set(), "producer should still be blocked on a full queue"
    q.flush()               # drain -> producer unblocks
    thread.join(timeout=5)
    assert done.is_set()
    q.flush()
    assert sorted(r["i"] for r in store) == [0, 1, 2]
    assert q.stats()["dropped"] == 0


def test_backpressure_timeout_raises_instead_of_losing_a_row():
    q = BoundedAuditQueue(sink=_collecting_sink([]), maxsize=1,
                          policy=QueueFullPolicy.BACKPRESSURE, backpressure_timeout_s=0.3)
    q.offer({"i": 0})
    with pytest.raises(AuditQueueOverflow, match="backpressure timed out"):
        q.offer({"i": 1})


def test_partial_sink_commit_is_an_error():
    """A sink that writes fewer rows than it was given must not be treated as success."""
    def lossy(batch: list[dict]) -> int:
        return len(batch) - 1

    q = BoundedAuditQueue(sink=lossy, maxsize=8)
    q.offer({"i": 0})
    q.offer({"i": 1})
    with pytest.raises(AuditQueueOverflow, match="refusing to lose"):
        q.flush()


def test_closed_queue_refuses_late_records():
    q = BoundedAuditQueue(sink=_collecting_sink([]), maxsize=4)
    q.close()
    with pytest.raises(AuditQueueClosed):
        q.offer({"i": 0})


def test_run_success_requires_every_required_artifact():
    gate = RunCommitGate(required_artifacts=("study.json", "trials.jsonl"))
    gate.mark_committed("study.json")
    result = gate.finalize()
    assert result["status"] == "RUN_INCOMPLETE"
    assert result["missing_artifacts"] == ["trials.jsonl"]
    gate.mark_committed("trials.jsonl")
    assert gate.finalize()["status"] == "RUN_SUCCESS"


def test_run_success_requires_the_queue_to_be_flushed():
    store: list[dict] = []
    q = BoundedAuditQueue(sink=_collecting_sink(store), maxsize=8)
    gate = RunCommitGate(required_artifacts=("trials.jsonl",))
    gate.register_queue(q)
    gate.mark_committed("trials.jsonl")
    q.offer({"i": 0})
    assert q.pending() == 1
    result = gate.finalize()          # finalize flushes, then re-checks
    assert result["status"] == "RUN_SUCCESS"
    assert result["unflushed_rows"] == 0
    assert store == [{"i": 0}]


def test_jsonl_sink_round_trip_through_the_evidence_writer(policy):
    """The real writer is a valid sink: rows land on disk, none are lost."""
    from crypto_regime_lab.evidence.manifest import EvidenceWriter

    writer = EvidenceWriter.open(policy, study_id="selftest")
    q = BoundedAuditQueue(sink=lambda batch: writer.append_jsonl("queued_trials.jsonl", batch), maxsize=16)
    for i in range(10):
        q.offer({"trial_id": f"t{i}", "status": "PRUNED" if i % 2 else "COMPLETE"})
    stats = q.close()
    assert stats["committed"] == 10 and stats["dropped"] == 0
    lines = (writer.run_dir / "queued_trials.jsonl").read_text().strip().splitlines()
    assert len(lines) == 10, "T59: negative/pruned trials are retained, never dropped"


def test_disk_usage_is_within_the_declared_quota(policy):
    report = disk_usage_report(policy)
    assert report["within_quota"] is True, report
    # derived from the registered policy, never hardcoded -- a disclosed
    # quota revision (configs/sandbox_policy.json's own
    # disk_quota_revision_20260926 note) must not silently expire this
    # assertion the way a literal number would.
    assert report["quota_gib"] == policy.raw["resource_budget"]["disk_quota_gib"]
    assert report["headroom_gib"] > 0
