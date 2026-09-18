"""RA-02 cache case matrix C01-C10 (RA-GUIDE-1.0 §6).

Every case maps to a guide test ID and runs real code — C01 and C04 run an
actual small QuantBT computation through the pinned engine (no mocked cache),
the rest exercise the real ComputeCache/Ledger/Optuna machinery. Scratch
files go through the lab_tmp fixture because pytest's tmp_path is outside
LAB_ROOT and refused by the read guard.
"""
import json
import shutil
import threading
import time

import pytest

from crypto_regime_lab.ra.cache_experiments import (
    deployment_facets,
    market_frame,
    real_engine_payload,
)
from crypto_regime_lab.ra.cache_semantics import assert_causal_hit, prefix_digest
from crypto_regime_lab.time_edge.compute_cache import (
    CONTRACT_FILES,
    ComputeCache,
    code_contract,
)
from crypto_regime_lab.time_edge.storage import EvidenceError, Ledger, save

ECONOMICS = {"fee": 0.0004, "slippage": 1.0,
             "contract": "event_lifecycle_v3_next_open"}


# --- C01: same semantics, different run id/path -> HIT, 0 new engine runs ---

def test_c01_cross_run_hit_with_zero_new_engine_runs(lab_tmp):
    frame = market_frame(2880)
    cutoff = frame.index[1440]
    facets = deployment_facets(frame, cutoff)
    engine_invocations = []

    def callback_for(producer):
        def callback():
            engine_invocations.append(producer)
            return real_engine_payload(frame, cutoff)
        return callback

    first = ComputeCache(lab_tmp, "ra02")
    payload_a, event_a = first.get_or_compute_singleflight(
        "deployment", facets, callback_for("ra02-run-a"), producer="ra02-run-a")
    assert event_a["status"] == "MISS"
    assert engine_invocations == ["ra02-run-a"]

    # Different storage location: the published entry is copied to another
    # root; identity is location-independent.
    other_root = lab_tmp / "other-root"
    shutil.copytree(first.directory,
                    other_root / "evidence" / "time_edge_validation_v4"
                    / "compute-cache" / "ra02")
    second = ComputeCache(other_root, "ra02")

    def forbidden_callback():
        raise AssertionError("a cache hit must never recompute")

    payload_b, event_b = second.get_or_compute_singleflight(
        "deployment", facets, forbidden_callback, producer="ra02-run-b")
    assert event_b["status"] == "HIT"
    assert event_b["producer"]["lab_run_id"] == "ra02-run-a"  # reuse never silent
    assert event_b["producer"]["lab_run_id"] != "ra02-run-b"
    assert payload_b == payload_a
    assert engine_invocations == ["ra02-run-a"]  # zero new engine runs


# --- C02: changed semantics -> MISS in the dependent scope -------------------

def _fake_project(lab_tmp):
    root = lab_tmp / "proj"
    for name in CONTRACT_FILES["deployment"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# original bytes\n")
    return root


def test_c02_changed_semantics_miss_in_dependent_scope(lab_tmp):
    root = _fake_project(lab_tmp)
    cache = ComputeCache(root, "ra02closure")
    base_facets = {"contract": code_contract(root, "deployment"), "p": 1}
    _, event = cache.get_or_compute_singleflight(
        "deployment", base_facets, lambda: {"v": 1}, producer="c02-a")
    assert event["status"] == "MISS"

    _, again = cache.get_or_compute_singleflight(
        "deployment", base_facets, lambda: {"v": 2}, producer="c02-a2")
    assert again["status"] == "HIT"

    # mutate a shared financial-semantics helper -> MISS (dependency closure)
    (root / "src/crypto_regime_lab/experiments/time_edge_contracts.py").write_text(
        "# edited helper bytes\n")
    mutated = {"contract": code_contract(root, "deployment"), "p": 1}
    assert cache.identity("deployment", mutated) != cache.identity(
        "deployment", base_facets)
    _, event = cache.get_or_compute_singleflight(
        "deployment", mutated, lambda: {"v": 3}, producer="c02-b")
    assert event["status"] == "MISS"

    # mutate a kind-owned file -> MISS too
    (root / "src/crypto_regime_lab/time_edge/workers.py").write_text(
        "# edited worker bytes\n")
    _, event = cache.get_or_compute_singleflight(
        "deployment", {"contract": code_contract(root, "deployment"), "p": 1},
        lambda: {"v": 4}, producer="c02-c")
    assert event["status"] == "MISS"


# --- C03: doc-only change keeps the numeric cache usable ---------------------

def test_c03_doc_only_change_keeps_numeric_cache(lab_tmp):
    root = _fake_project(lab_tmp)
    cache = ComputeCache(root, "ra02doc")
    facets = {"contract": code_contract(root, "deployment"), "p": 1}
    payload, event = cache.get_or_compute_singleflight(
        "deployment", facets, lambda: {"numeric": [1.5, 2.5]}, producer="c03-a")
    assert event["status"] == "MISS"
    (root / "README.md").write_text("# prose-only documentation change\n")
    payload2, event2 = cache.get_or_compute_singleflight(
        "deployment", facets, lambda: pytest.fail("doc change must not recompute"),
        producer="c03-b")
    assert event2["status"] == "HIT"
    assert payload2 == payload

# --- C04: future suffix mutation keeps prefix key and prefix output ----------

def test_c04_future_suffix_never_changes_prefix_key_or_output(lab_tmp):
    cut = 1440
    frame = market_frame(2880, seed=11)
    until = frame.index[cut - 1]
    digest_a = prefix_digest(frame, until)

    mutated = frame.copy()
    shifted = mutated.iloc[cut:].copy()
    for column in ("open", "high", "low", "close"):
        shifted[column] = shifted[column] + 0.5
    mutated.iloc[cut:] = shifted
    assert prefix_digest(mutated, until) == digest_a  # suffix: key unchanged

    bumped = frame.copy()
    bumped.iloc[10] = bumped.iloc[10] + 0.01  # prefix row mutation
    assert prefix_digest(bumped, until) != digest_a

    # Real engine: identical prefix, different suffix -> identical prefix equity.
    cache = ComputeCache(lab_tmp, "ra02suffix")
    runs = []
    for tag, candidate in (("a", frame), ("b", mutated)):
        payload, event = cache.get_or_compute_singleflight(
            "deployment", deployment_facets(candidate, candidate.index[cut]),
            lambda f=candidate: real_engine_payload(f, f.index[cut],
                                                    prefix_rows=cut),
            producer="c04-" + tag)
        assert event["status"] == "MISS"  # suffix differs -> different identity
        runs.append(payload)
    assert runs[0]["visited_bars"] == runs[1]["visited_bars"]
    assert runs[0]["equity_prefix_rows"] == runs[1]["equity_prefix_rows"]
    assert runs[0]["equity_prefix_sha256"] == runs[1]["equity_prefix_sha256"]


# --- C05: crash/partial/corrupt is never a hit; attempts preserved -----------

def test_c05_partial_or_corrupt_publication_is_never_a_hit(lab_tmp):
    cache = ComputeCache(lab_tmp, "ra02c05")
    facets = {"schema": "ra02_c05_v1", "k": 1}
    identity = cache.identity("deployment", facets)
    path, seal = cache._paths(identity)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text('{"partial": true')  # payload without seal: crash pre-receipt
    with pytest.raises(EvidenceError):
        cache.lookup("deployment", facets)

    # A seal that does not match the payload bytes is drift, never a hit.
    path.write_bytes(b'{"payload": {"v": 9}}')
    save(seal, {"sha256": "0" * 64})
    with pytest.raises(EvidenceError, match="seal hash drift"):
        cache.lookup("deployment", facets)

    # A failed attempt stays in the ledger: charged, never silently dropped.
    ledger = Ledger(lab_tmp / "alloc-c05", {"allocation_id": "RA02-C05"}, 100.0)
    attempt = ledger.begin("task-key", 40.0)
    assert ledger.spent() == 40.0  # reserved while running
    ledger.finish(attempt, status="FAILED", wall=12.5, reason="engine exit 1")
    assert ledger.spent() == 12.5
    row = ledger.db.execute("SELECT status, reason FROM attempt WHERE id=?",
                            (attempt,)).fetchone()
    assert row["status"] == "FAILED" and row["reason"] == "engine exit 1"

# --- C06: concurrent same-key requests -> one owner computation --------------

def test_c06_concurrent_same_key_runs_one_computation(lab_tmp):
    cache = ComputeCache(lab_tmp, "ra02c06")
    facets = {"schema": "ra02_c06_v1", "k": 7}
    calls = []
    results = {}
    errors = []
    barrier = threading.Barrier(4)

    def callback():
        calls.append("compute")
        time.sleep(0.2)
        return {"value": 123}

    def worker(index):
        try:
            barrier.wait(timeout=10)
            payload, event = cache.get_or_compute_singleflight(
                "deployment", facets, callback, producer=f"c06-{index}")
            results[index] = (payload, event["status"])
        except Exception as exc:  # pragma: no cover - surfaced by the assert
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors, errors
    assert len(calls) == 1  # exactly one owner computation
    statuses = sorted(status for _, status in results.values())
    assert statuses == ["HIT", "HIT", "HIT", "MISS"]
    payloads = {json.dumps(payload, sort_keys=True) for payload, _ in results.values()}
    assert len(payloads) == 1  # deterministic validated reuse


# --- C07: duplicate params keep the trial ledger and reuse the evaluation ----

def test_c07_duplicate_params_keep_trial_ledger_and_reuse(lab_tmp):
    from crypto_regime_lab.ra.study_replay import run_study

    cache = ComputeCache(lab_tmp, "ra02c07")
    evaluations = []

    def objective_of(evaluation_key):
        def compute():
            evaluations.append(dict(evaluation_key))
            return {"value": float(evaluation_key["x"])}
        payload, event = cache.get_or_compute_singleflight(
            "search", {"schema": "ra02_search_v1", **evaluation_key}, compute,
            producer="c07")
        assert event["status"] in ("HIT", "MISS")
        return payload["value"]

    # A tiny integer grid forces duplicate proposals and duplicate evaluations.
    def objective_grid(params):
        return objective_of({"x": int(params["x"]) % 3})

    result = run_study(20260911, 8, objective_grid, space={"x": ("int", (0, 5))})
    asks = len(result["proposals"])
    assert asks == 8  # every ask answered
    assert len(result["objectives"]) == 8  # every tell recorded
    proposals = {json.dumps(p, sort_keys=True) for p in result["proposals"]}
    assert len(proposals) < asks, "the grid was expected to produce duplicates"
    evaluation_keys = {json.dumps(p, sort_keys=True) for p in evaluations}
    assert len(evaluations) == len(evaluation_keys) < asks  # one eval per unique key
    assert any(cache.directory.glob("*.seal.json")), "search cache published nothing"

# --- C08: crash/resume study reproduces the uninterrupted contract -----------

def test_c08_resume_parity_with_replay_and_red_control(lab_tmp):
    from crypto_regime_lab.ra.study_replay import (
        StudyInterrupted, run_study, run_study_dropping_tells,
    )

    cache = ComputeCache(lab_tmp, "ra02c08")
    evaluations = []

    def objective_of(params):
        def compute():
            evaluations.append(dict(params))
            return {"value": float(1.0 - abs(params["x"] - 0.5))}
        payload, _ = cache.get_or_compute_singleflight(
            "search", {"schema": "ra02_resume_v1", **params}, compute,
            producer="c08")
        return payload["value"]

    seed = 20260911
    space = {"x": ("float", (0.0, 1.0))}
    reference = run_study(seed, 6, objective_of, space=space)  # uninterrupted

    records = []
    try:
        run_study(seed, 6, objective_of, space=space, interrupt_after=3)
    except StudyInterrupted as interrupted:
        records = interrupted.records
    assert len(records) == 3
    resumed = run_study(seed, 6, objective_of, replay=records, space=space)
    assert resumed["proposals"] == reference["proposals"]
    assert resumed["objectives"] == reference["objectives"]
    assert resumed["evaluations"] < reference["evaluations"]  # cache served them

    # Red control: dropping the tell/update cannot reproduce the continuation.
    naive = run_study_dropping_tells(seed, records, 3, space=space)
    assert naive != reference["proposals"][3:], (
        "the parity test would prove nothing if a tell-dropping restart "
        "reproduced the same continuation")


# --- C09: mature-after-cutoff artifacts are rejected; ready is never 0 -------

def test_c09_future_or_zero_ready_rejected(lab_tmp):
    cutoff = "2026-01-05T00:00:00+00:00"
    base = {"physical_compute_at": "2026-01-04T23:00:00+00:00",
            "simulated_cutoff": cutoff,
            "simulated_ready_at": "2026-01-04T12:00:00+00:00"}
    parsed = assert_causal_hit(base, cutoff=cutoff)  # matured before the decision
    assert parsed["simulated_ready_at"].isoformat() == "2026-01-04T12:00:00+00:00"
    assert parsed["physical_compute_at"].isoformat() == "2026-01-04T23:00:00+00:00"

    future = dict(base, simulated_ready_at="2026-01-06T00:00:00+00:00")
    with pytest.raises(ValueError, match="future information|matures"):
        assert_causal_hit(future, cutoff=cutoff)

    for zero in (0, "1970-01-01T00:00:00+00:00", None):
        with pytest.raises(ValueError, match="zero|epoch|unset"):
            assert_causal_hit(dict(base, simulated_ready_at=zero), cutoff=cutoff)

    missing = {k: v for k, v in base.items() if k != "physical_compute_at"}
    with pytest.raises(ValueError, match="causality fields"):
        assert_causal_hit(missing, cutoff=cutoff)

    mismatched = dict(base, simulated_cutoff="2026-01-04T00:00:00+00:00")
    with pytest.raises(ValueError, match="computed for cutoff"):
        assert_causal_hit(mismatched, cutoff=cutoff)


# --- C10: reset vs carry initial state never produces a false hit ------------

def test_c10_initial_state_difference_is_never_a_false_hit(lab_tmp):
    from crypto_regime_lab.ra.cache_semantics import assert_state_compatible

    frame = market_frame(600)
    cutoff = frame.index[300]
    fresh = {"mode": "fresh", "equity": 20000.0}
    carry = {"mode": "carry", "carried_equity": 20150.0, "carried_position": 0.5}
    cache = ComputeCache(lab_tmp, "ra02c10")

    payload_fresh, event = cache.get_or_compute_singleflight(
        "deployment", deployment_facets(frame, cutoff, initial_state=fresh),
        lambda: {"account": "fresh-result"}, producer="c10-fresh")
    assert event["status"] == "MISS"

    payload_carry, event_carry = cache.get_or_compute_singleflight(
        "deployment", deployment_facets(frame, cutoff, initial_state=carry),
        lambda: {"account": "carry-result"}, producer="c10-carry")
    assert event_carry["status"] == "MISS"  # never a false HIT
    assert payload_carry["account"] == "carry-result"

    _, repeat = cache.get_or_compute_singleflight(
        "deployment", deployment_facets(frame, cutoff, initial_state=fresh),
        lambda: pytest.fail("fresh state must HIT"), producer="c10-fresh-2")
    assert repeat["status"] == "HIT"
    assert payload_fresh["account"] == "fresh-result"

    assert_state_compatible(carry, dict(carry))
    with pytest.raises(ValueError, match="typed incompatibility"):
        assert_state_compatible(fresh, carry)
    with pytest.raises(ValueError, match="must restate"):
        assert_state_compatible({"mode": "carry"}, {"mode": "carry"})
