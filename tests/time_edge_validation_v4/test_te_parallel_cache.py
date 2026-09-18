"""Guards for the identity-keyed compute cache and the independent-worker scheduler.

These tests never call the engine: the cache is exercised with pure callbacks and
the scheduler with synthetic owned children, so a green run means the accounting,
identity and parallelism contracts hold, not that market work happened.
"""
import time
from types import SimpleNamespace

import pytest

from crypto_regime_lab.time_edge import runtime
from crypto_regime_lab.time_edge.compute_cache import ComputeCache
from crypto_regime_lab.time_edge.storage import EvidenceError, read, save


def unit_cache(lab_tmp):
    return ComputeCache(lab_tmp, "unit-cache", source="unit-source-1")


def test_identical_identity_reuses_the_computation(lab_tmp):
    cache = unit_cache(lab_tmp)
    calls = {"count": 0}
    facets = {"schema": "unit", "cutoff": "2020-01-01T00:00:00+00:00", "economics": {"fee": 0.0004}}
    def compute():
        calls["count"] += 1
        return {"value": 7, "marker": calls["count"]}
    first, first_event = cache.get_or_compute("world", facets, compute, producer="run-a")
    second, second_event = cache.get_or_compute("world", facets, compute, producer="run-b")
    assert calls["count"] == 1, "an identical identity must not recompute"
    assert first_event["status"] == "MISS" and second_event["status"] == "HIT"
    assert first == second
    assert second_event["producer"]["lab_run_id"] == "run-a"
    assert second_event["producer"]["source_identity"] == "unit-source-1"


def test_changed_facets_are_never_reused(lab_tmp):
    cache = unit_cache(lab_tmp)
    calls = {"count": 0}
    def compute():
        calls["count"] += 1
        return {"value": calls["count"]}
    base = {"schema": "unit", "cutoff": "2020-01-01T00:00:00+00:00", "economics": {"fee": 0.0004}}
    variants = [
        {**base, "cutoff": "2020-02-01T00:00:00+00:00"},
        {**base, "economics": {"fee": 0.001}},
        {**base, "source": "different-source"},
        {**base, "condition": "RECURRING_OPPORTUNITY"},
    ]
    cache.get_or_compute("world", base, compute, producer="run-a")
    for variant in variants:
        _, event = cache.get_or_compute("world", variant, compute, producer="run-a")
        assert event["status"] == "MISS", f"facet change must miss: {variant}"
    assert calls["count"] == 1 + len(variants)


def test_tampered_cache_seal_is_an_error_not_a_recompute(lab_tmp):
    cache = unit_cache(lab_tmp)
    facets = {"schema": "unit", "cutoff": "x"}
    cache.get_or_compute("world", facets, lambda: {"value": 1}, producer="run-a")
    identity = cache.identity("world", facets)
    path, seal = cache._paths(identity)
    record = read(path); record["payload"] = {"value": 999}
    path.unlink(); seal.unlink(); save(path, record)
    save(seal, {"schema": "regime_lab.te_compute_cache_seal.v1", "identity": identity, "sha256": "0" * 64})
    with pytest.raises(EvidenceError, match="seal"):
        cache.lookup("world", facets)


def test_cache_rejects_an_unregistered_kind(lab_tmp):
    cache = unit_cache(lab_tmp)
    with pytest.raises(EvidenceError, match="registered kind"):
        cache.lookup("not-a-kind", {"a": 1})


def test_worker_cpu_sets_are_disjoint_and_bounded(monkeypatch):
    monkeypatch.setattr(runtime.os, "sched_getaffinity", lambda pid: {0, 1, 2, 3})
    two = runtime.worker_cpu_sets({"workers": 2, "cpu_limit": 4})
    assert [len(slot) for slot in two] == [2, 2]
    assert sorted(cpu for slot in two for cpu in slot) == [0, 1, 2, 3]
    four = runtime.worker_cpu_sets({"workers": 4, "cpu_limit": 4})
    assert [len(slot) for slot in four] == [1, 1, 1, 1]
    assert len({cpu for slot in four for cpu in slot}) == 4
    capped = runtime.worker_cpu_sets({"workers": 4, "cpu_limit": 2})
    assert len(capped) == 2 and sum(len(slot) for slot in capped) <= 2
    excessive = runtime.worker_cpu_sets({"workers": 99, "cpu_limit": 4})
    assert len(excessive) == 4, "the registered envelope caps workers at four"


def harness(monkeypatch, lab_tmp, policy, lab_root, outcomes, *, delay=0.):
    monkeypatch.setattr(runtime, "validate_job", lambda *args: None)
    monkeypatch.setattr(runtime.SandboxPolicy, "discover", lambda root: policy)
    monkeypatch.setattr(runtime, "probe_isolation", lambda p: SimpleNamespace(available=True))
    monkeypatch.setattr(runtime, "disk_usage_report", lambda p: {"within_quota": True})
    def synthetic_child(policy, argv, **kwargs):
        output = argv[-1]
        request_path = argv[argv.index("--request") + 1]
        task_id = read(request_path)["task"]["task_id"]
        outcome = outcomes.get(task_id, "OK")
        program = ("import json,pathlib,time; time.sleep(" + repr(delay) + "); "
                   "pathlib.Path(" + repr(output) + ").write_text(json.dumps({'status':"
                   + repr(outcome) + ",'lab_run_id':'parallel-fixture'}))")
        return [str(lab_root / "environments/lab_venv/bin/python"), "-B", "-c", program]
    monkeypatch.setattr(runtime, "build_bwrap_argv", synthetic_child)
    def job(name, tasks, *, workers=2, cpu_limit=4, cap=10., total=200.):
        return {"lab_run_id": name, "allocation_id": "parallel-allocation",
                "total_wall_seconds": total, "task_wall_seconds": cap,
                "workers": workers, "cpu_limit": cpu_limit, "memory_gib": 4,
                "source_identity": "unit-fixture", "inputs": {}, "tasks": tasks}
    return job


def test_independent_tasks_run_in_parallel_within_the_cpu_budget(monkeypatch, lab_tmp, policy, lab_root):
    job = harness(monkeypatch, lab_tmp, policy, lab_root, {}, delay=1.0)
    tasks = [{"task_id": "shard-a", "kind": "qualify", "wall_seconds": 10.},
             {"task_id": "shard-b", "kind": "qualify", "wall_seconds": 10.}]
    started = time.monotonic()
    result = runtime.run_jobs(lab_tmp, job("parallel", tasks))
    wall = time.monotonic() - started
    assert [row["status"] for row in result["attempts"]] == ["COMPLETE", "COMPLETE"]
    assert wall < 1.9, "two independent children must overlap, not serialize"
    assert result["workers"] == 2
    assigned = [cpu for slot in result["cpu_sets"] for cpu in slot]
    assert len(assigned) == len(set(assigned)) <= 4


def test_failed_shard_does_not_stop_an_independent_shard(monkeypatch, lab_tmp, policy, lab_root):
    job = harness(monkeypatch, lab_tmp, policy, lab_root, {"shard-a": "FAILED"})
    tasks = [{"task_id": "shard-a", "kind": "qualify", "wall_seconds": 10.},
             {"task_id": "shard-b", "kind": "qualify", "wall_seconds": 10.}]
    result = runtime.run_jobs(lab_tmp, job("failure-isolation", tasks))
    statuses = {row["status"] for row in result["attempts"]}
    assert statuses == {"FAILED", "COMPLETE"}, "independent shards are not stopped by a sibling"


def test_dependent_of_a_failed_shard_is_never_launched(monkeypatch, lab_tmp, policy, lab_root):
    job = harness(monkeypatch, lab_tmp, policy, lab_root, {"shard-a": "FAILED"})
    tasks = [{"task_id": "shard-a", "kind": "qualify", "wall_seconds": 10.},
             {"task_id": "shard-b", "kind": "qualify", "wall_seconds": 10., "depends_on": ["shard-a"]}]
    result = runtime.run_jobs(lab_tmp, job("dependency-block", tasks))
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["status"] == "FAILED"
    assert "shard-b" in result["not_launched"]


def test_scheduling_does_not_change_task_or_cap(monkeypatch, lab_tmp, policy, lab_root):
    job = harness(monkeypatch, lab_tmp, policy, lab_root, {}, delay=0.)
    tasks = [{"task_id": "arm-a", "kind": "qualify", "wall_seconds": 7.},
             {"task_id": "arm-b", "kind": "qualify", "wall_seconds": 7.}]
    result = runtime.run_jobs(lab_tmp, job("equal-compute", tasks))
    assert len(result["attempts"]) == 2
    allocated = sum(row["reserved"] for row in result["attempts"])
    assert allocated == 14.0, "every task still reserves its full registered cap"
    for row in result["attempts"]:
        attempt = lab_tmp / "evidence/time_edge_validation_v4/runs/equal-compute/attempts" / row["id"]
        request = read(attempt / "request.json")
        assert request["task"]["wall_seconds"] == 7.0
        assert request["task"]["kind"] == "qualify"
    assert result["not_launched"] == {}
