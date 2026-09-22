"""FP-02 gates on the real engine path -- no mocked-only run (guide section 14
"Actual runs bắt buộc"). Every test here makes at least one genuine QuantBT
call through ``fp.evaluator``; the small synthetic frame
(``ra.cache_experiments.market_frame``, the same fixture RA-02's own real-
engine cache tests use) keeps each call bounded while still going through
the installed engine for real.
"""
from __future__ import annotations

import pytest

from crypto_regime_lab.fp import evaluator as ev
from crypto_regime_lab.fp.lineage import LineageError, build_lineage
from crypto_regime_lab.ra.cache_experiments import market_frame
from crypto_regime_lab.ra.cache_semantics import assert_causal_hit
from crypto_regime_lab.time_edge.compute_cache import ComputeCache

PARAMS_A = {"AP": 5, "coeff": 2, "novolumedata": False, "src_col": "close",
           "alpha.condition_threshold": 50}
PARAMS_B = {"AP": 8, "coeff": 3, "novolumedata": False, "src_col": "close",
           "alpha.condition_threshold": 40}


@pytest.fixture
def cache(lab_root, lab_tmp):
    return ComputeCache(lab_root, "fp02test", cache_root=str(lab_tmp.relative_to(lab_root)))


def test_fp02_g_parity_audit_vs_score_route(lab_root):
    """FP02-G-PARITY: audit route vs the score/fast route this evaluator
    intends to use, on FP-02's OWN real candidate -- re-proving FUP-04's
    finding fresh rather than citing it as a substitute."""
    frame = market_frame(2000, seed=101)
    result = ev.route_parity(lab_root, "A-SC", frame, PARAMS_A)
    assert result["status"] == "PASS"
    assert result["equity_exact_equal"] is True
    assert result["max_abs_equity_diff"] == 0.0
    assert result["entries_match"] is True
    assert result["fill_count_match"] is True
    # The documented, disclosed asymmetry (FUP-04): the AUDIT ledger's own
    # fill count differs under the score profile; strategy-level fills do not.
    assert result["audit"]["fill_count"] == result["fast"]["fill_count"]
    assert result["audit"]["engine_fill_count"] >= result["fast"]["engine_fill_count"]


def test_fp02_g_cache_same_semantics_hit_different_economics_miss(lab_root, cache):
    """FP02-G-CACHE: a changed run ID (producer) never recomputes; a changed
    economic dependency (fee rate) misses."""
    frame = market_frame(1500, seed=202)
    cutoff = frame.index[-1]

    payload_a, event_a = ev.evaluate_candidate(cache, lab_root, "A-SC", frame, PARAMS_A,
                                               cutoff=cutoff, producer="run-a")
    assert event_a["status"] == "MISS"

    payload_b, event_b = ev.evaluate_candidate(cache, lab_root, "A-SC", frame, PARAMS_A,
                                               cutoff=cutoff, producer="run-b")
    assert event_b["status"] == "HIT"
    assert payload_b == payload_a
    assert event_b["producer"]["lab_run_id"] == "run-a"

    changed_economics = {**ev.default_economics(), "one_way_fee": 0.0009}
    payload_c, event_c = ev.evaluate_candidate(cache, lab_root, "A-SC", frame, PARAMS_A,
                                               cutoff=cutoff, economics=changed_economics,
                                               producer="run-c")
    assert event_c["status"] == "MISS"
    assert payload_c["trial_scalar"]["terminal_equity"] != payload_a["trial_scalar"]["terminal_equity"]


def test_fp02_g_latency_causal_hit_guard(lab_root, cache):
    """FP02-G-LATENCY: a cache hit never reports readiness earlier than the
    cutoff it was computed for, and a future-maturing record is refused."""
    frame = market_frame(1200, seed=303)
    cutoff = frame.index[len(frame) // 2]
    payload, _event = ev.evaluate_candidate(cache, lab_root, "A-SC", frame, PARAMS_A,
                                            cutoff=cutoff, producer="latency-run")

    parsed = assert_causal_hit(payload["causality"], cutoff=cutoff)
    assert parsed["simulated_ready_at"] == parsed["simulated_cutoff"]

    # A record whose OWN ready_at is tampered to mature after the SAME
    # cutoff it was computed for and is being consumed at -- future
    # information, the one case assert_causal_hit exists to catch.
    tampered = dict(payload["causality"])
    tampered["simulated_ready_at"] = frame.index[-1].isoformat()
    with pytest.raises(ValueError, match="future information"):
        assert_causal_hit(tampered, cutoff=cutoff)

    # A record consumed at a DIFFERENT cutoff than it was computed for is a
    # separate, also-real failure mode -- checked distinctly, not conflated.
    with pytest.raises(ValueError, match="but is being consumed at"):
        assert_causal_hit(payload["causality"], cutoff=frame.index[0])


def test_fp02_g_memory_peak_bounded_and_not_growing_with_repeats(lab_root, cache):
    """FP02-G-MEMORY: peak stays inside the registered budget, and does not
    climb across repeated candidate evaluations -- the RA-07 decay deep-
    dive's own OOM lesson (an unbounded per-call accumulator), applied here
    as a standing regression guard rather than a one-off audit."""
    from crypto_regime_lab.safety.paths import SandboxPolicy

    policy = SandboxPolicy.load(lab_root / "configs" / "sandbox_policy.json")
    budget_mib = policy.raw["resource_budget"]["working_memory_gib"] * 1024

    frame = market_frame(1500, seed=404)
    cutoff = frame.index[-1]
    peaks = []
    for i in range(4):
        params = {**PARAMS_A, "AP": 5 + i}
        payload, event = ev.evaluate_candidate(cache, lab_root, "A-SC", frame, params,
                                               cutoff=cutoff, producer=f"mem-run-{i}")
        assert event["status"] == "MISS"
        peaks.append(payload["instrumentation"]["peak_mib"])

    assert all(p < budget_mib for p in peaks), peaks
    # Not a strict monotonic-non-increase requirement (allocator noise is
    # real) -- the regression this guards is unbounded GROWTH: the last call
    # must not be a large multiple of the first.
    assert peaks[-1] < peaks[0] * 3 + 50, peaks


def test_fp02_g_lineage_reconstructs_activation_and_fills(lab_root, cache):
    """FP02-G-LINEAGE: a real multi-selection deployment with a pending/
    activation case (guide's required run) -- reconstruct which fills
    belong to which activation, and cross-check the reconstruction
    independently rather than trusting build_lineage's own internal asserts."""
    frame = market_frame(3000, seed=505)
    switch_bar = len(frame) // 2
    requests = [
        {"activation_id": "lineage-initial", "params": PARAMS_A, "requested_at_bar": 0},
        {"activation_id": "lineage-switch", "params": PARAMS_B, "requested_at_bar": switch_bar},
    ]
    payload, event = ev.run_deployment(cache, lab_root, "A-SC", frame, requests,
                                       ready_at=frame.index[-1], producer="lineage-run")
    assert event["status"] == "MISS"
    lineage = payload["lineage"]
    assert lineage["activations_effected"] == 2
    assert lineage["fills_attributed"] == lineage["fills_total"]

    # Independent cross-check against the audit trace's own version_by_bar,
    # not against build_lineage's own bookkeeping. Per BAR RANGE, not per
    # sentinel string: "WARMING" occurs more than once (initial AND the
    # switch each warm up separately), so a string-keyed recount would
    # wrongly merge two distinct runs' fill counts into one bucket.
    audit = payload["selected_audit"]
    version_by_bar = audit["version_by_bar"]
    fills = audit["fills"]
    for row in lineage["activations"]:
        if row["bar_range"] is None:
            continue
        start, end = row["bar_range"]
        assert all(version_by_bar[b] == version_by_bar[start] for b in range(start, end)), row
        recount = sum(1 for f in fills if start <= int(f["bar_index"]) < end)
        assert recount == row["fill_count"], row

    effected_ids = {row["activation_id"] for row in lineage["activations"]
                    if row["activation_id"] is not None and row.get("effective_at_bar") is not None}
    assert effected_ids == {"lineage-initial", "lineage-switch"}
    switch_row = next(r for r in lineage["activations"] if r["activation_id"] == "lineage-switch")
    # Guide 9.5: activation waits for flat + warm, so it never lands exactly
    # at the requested bar.
    assert switch_row["effective_at_bar"] >= switch_bar


def test_fp02_lineage_rejects_a_fabricated_disagreement():
    """The guard itself: build_lineage scans version_by_bar as ground truth
    (no separate source to disagree with it by construction), so the one way
    a caller-supplied fills list can be internally inconsistent is a fill
    outside every bar range version_by_bar actually covers -- proved on a
    small fixture the same way FP-01's verifier tests prove failure shapes,
    not only success."""
    version_by_bar = ["v1", "v1", "v2", "v2"]
    good_fill = {"bar_index": 2, "reason": "entry", "side": 1, "price": 1.0, "qty": 1.0}
    ok = build_lineage(switches=[{"activation_id": "v2", "effective_at_bar": 2,
                                  "requested_at_bar": 1}],
                       version_by_bar=version_by_bar, fills=[good_fill], initial_version="v1")
    assert ok["fills_attributed"] == 1

    out_of_range_fill = {"bar_index": 99, "reason": "entry", "side": 1,
                         "price": 1.0, "qty": 1.0}
    with pytest.raises(LineageError):
        build_lineage(switches=[{"activation_id": "v2", "effective_at_bar": 2,
                                 "requested_at_bar": 1}],
                      version_by_bar=version_by_bar, fills=[good_fill, out_of_range_fill],
                      initial_version="v1")


def test_fp02_g_resume_cache_hit_after_simulated_crash(lab_root, lab_tmp, cache):
    """FP02-G-RESUME: FP-02's evaluator introduces no checkpointed search
    loop itself (that is FP-03's), so the resume property it CAN and does
    provide is cache-based -- a process that stops and restarts consults
    the same cache and only recomputes what was never finished, exactly
    C08's shape (ra/cache_experiments.py::resume_parity_experiment) applied
    to FP-02's own real evaluator instead of a toy objective."""
    frame = market_frame(1200, seed=606)
    cutoff = frame.index[-1]
    candidates = [{**PARAMS_A, "AP": ap} for ap in (5, 6, 7)]

    # "run 1": evaluate the first two, then stop (simulated crash).
    first_pass = []
    for i, params in enumerate(candidates[:2]):
        payload, event = ev.evaluate_candidate(cache, lab_root, "A-SC", frame, params,
                                               cutoff=cutoff, producer="resume-run-1")
        first_pass.append((event["status"], payload))
        assert event["status"] == "MISS"

    # "run 2": a FRESH ComputeCache instance over the SAME directory (a new
    # process would construct its own object) resumes all three.
    resumed_cache = ComputeCache(lab_root, "fp02test",
                                 cache_root=str(lab_tmp.relative_to(lab_root)))
    statuses = []
    for params in candidates:
        payload, event = ev.evaluate_candidate(resumed_cache, lab_root, "A-SC", frame, params,
                                               cutoff=cutoff, producer="resume-run-2")
        statuses.append(event["status"])
    assert statuses == ["HIT", "HIT", "MISS"]
    assert statuses.count("MISS") == 1
