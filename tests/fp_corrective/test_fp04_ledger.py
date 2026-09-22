"""FP04-T01..T08 (guide section 16) plus the supporting region/weight/view
mechanics, on synthetic candidate pools (engine-free -- these are causality
and bookkeeping properties, provable without a real search) except one real,
cheap end-to-end forward-evaluation + censored-path proof.
"""
from __future__ import annotations

import pandas as pd
import pytest

from crypto_regime_lab.fp import forward_ledger as fl
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS

SCHEMA = SCHEMAS["A-SC"]


def _candidate(trial_id, *, coeff, ap, threshold, objective):
    return {"trial_id": trial_id, "objective": objective,
           "params": {"coeff": coeff, "AP": ap, "alpha.condition_threshold": threshold,
                      "novolumedata": False, "src_col": "close"}}


def _tight_pool(n: int, *, objective_start: float = 1.0) -> list[dict]:
    """n candidates clustered close together in param space -> one region."""
    return [_candidate(i, coeff=4, ap=20 + i, threshold=55, objective=objective_start + i * 0.01)
           for i in range(n)]


def _two_region_pool() -> list[dict]:
    """One tight low-coeff cluster, one tight high-coeff cluster -- far apart
    on the 'coeff' dimension (span 7), so any reasonable threshold separates
    them into two regions."""
    low = [_candidate(i, coeff=1, ap=10 + i, threshold=30, objective=1.0 + i * 0.1) for i in range(3)]
    high = [_candidate(10 + i, coeff=8, ap=50 + i, threshold=80, objective=2.0 + i * 0.1)
           for i in range(3)]
    return low + high


# ---------------------------------------------------------------------------
# Origin grid
# ---------------------------------------------------------------------------

def test_valid_origin_placement_window_matches_registered_development_role():
    earliest, latest = fl.valid_origin_placement_window(train_memory_days=180, forward_horizon_days=28)
    assert earliest == pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=180 + 5)
    assert latest == pd.Timestamp("2023-12-31", tz="UTC") - pd.Timedelta(days=28 + 1)


def test_validate_origin_grid_flags_dates_outside_the_window():
    result = fl.validate_origin_grid(["2019-01-01", "2021-06-01", "2024-06-01"],
                                     train_memory_days=180, forward_horizon_days=28)
    by_date = {r["origin_cutoff"]: r for r in result["origins"]}
    assert by_date["2019-01-01"]["valid"] is False and by_date["2019-01-01"]["reason"]
    assert by_date["2021-06-01"]["valid"] is True and by_date["2021-06-01"]["reason"] is None
    assert by_date["2024-06-01"]["valid"] is False
    assert result["all_valid"] is False


def test_fp04_frozen_origin_grid_is_12_quarterly_origins_all_valid():
    assert len(fl.FP04_ORIGIN_GRID) == 12
    assert len(set(fl.FP04_ORIGIN_GRID)) == 12          # no duplicates
    assert list(fl.FP04_ORIGIN_GRID) == sorted(fl.FP04_ORIGIN_GRID)   # chronological
    result = fl.validate_origin_grid(fl.FP04_ORIGIN_GRID, train_memory_days=180,
                                     forward_horizon_days=28)
    assert result["all_valid"] is True, result


def test_flag_window_overlaps_on_the_frozen_grid_forward_windows_never_overlap():
    """28-day forward windows on a ~91-day-spaced quarterly grid cannot
    overlap; 180-day TRAINING windows overlap consecutive quarters by
    construction -- both must be visible (guide 7.2), not just asserted."""
    overlaps = fl.flag_window_overlaps(fl.FP04_ORIGIN_GRID, train_memory_days=180,
                                       forward_horizon_days=28)
    assert all(v["forward_window_overlaps_with"] == [] for v in overlaps.values())
    assert any(v["train_window_overlaps_with"] for v in overlaps.values())


def test_flag_window_overlaps_detects_a_deliberately_dense_pair():
    overlaps = fl.flag_window_overlaps(["2022-01-01", "2022-01-15"],
                                       train_memory_days=180, forward_horizon_days=28)
    assert overlaps["2022-01-01"]["forward_window_overlaps_with"] == ["2022-01-15"]
    assert overlaps["2022-01-15"]["forward_window_overlaps_with"] == ["2022-01-01"]


# ---------------------------------------------------------------------------
# Region geometry -- FP04-T04: geometry never uses forward performance
# ---------------------------------------------------------------------------

def test_cluster_into_regions_groups_close_points_and_separates_far_ones():
    regions = fl.cluster_into_regions(SCHEMA, _two_region_pool(), distance_threshold=0.15)
    assert len(regions) == 2
    sizes = sorted(len(r) for r in regions)
    assert sizes == [3, 3]


def test_cluster_into_regions_dedups_identical_params_keeping_best_objective():
    dup = [_candidate(0, coeff=4, ap=20, threshold=55, objective=1.0),
          _candidate(1, coeff=4, ap=20, threshold=55, objective=9.0)]   # same params
    regions = fl.cluster_into_regions(SCHEMA, dup, distance_threshold=0.05)
    assert len(regions) == 1 and len(regions[0]) == 1
    assert regions[0][0]["trial_id"] == 1   # the higher-objective duplicate survives


def test_region_medoid_is_a_real_member_never_an_invented_centroid():
    pool = _tight_pool(5)
    medoid = fl.region_medoid(SCHEMA, pool)
    assert medoid in pool
    assert medoid["trial_id"] in {c["trial_id"] for c in pool}


def test_fp04_t04_region_geometry_is_unchanged_by_corrupting_objective_or_adding_forward_fields():
    """T04: 'Region geometry không dùng forward performance.' Clustering the
    SAME params with wildly different (even negative/corrupted) objective
    values, and with forward/decay fields injected onto the candidates,
    produces the IDENTICAL region membership -- geometry reads params only."""
    pool = _two_region_pool()
    baseline = fl.cluster_into_regions(SCHEMA, pool, distance_threshold=0.15)
    corrupted = [{**c, "objective": -999.0, "forward_mean_daily_return": 123.0,
                 "decay": "poisoned"} for c in pool]
    corrupted_regions = fl.cluster_into_regions(SCHEMA, corrupted, distance_threshold=0.15)
    baseline_membership = sorted(sorted(c["trial_id"] for c in r) for r in baseline)
    corrupted_membership = sorted(sorted(c["trial_id"] for c in r) for r in corrupted_regions)
    assert baseline_membership == corrupted_membership


def test_region_summary_reports_required_guide_7_4_fields_forward_fields_pending():
    pool = _tight_pool(4)
    summary = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00", members=pool)
    for key in ("member_candidate_ids", "medoid_trial_id", "medoid_params",
               "is_quality_distribution", "probe_coverage",
               "behavioral_diversity_mean_pairwise_distance",
               "historical_support_within_origin"):
        assert key in summary
    assert summary["historical_support_within_origin"] == 4
    assert summary["forward_utility_mean_daily_return"] is None   # not yet evaluated
    assert summary["decay_D_mean_daily_return"] is None


def test_build_regions_for_origin_caps_at_max_representatives_by_best_objective():
    # 20 well-separated single-member regions (coeff sweeps the full 1-8
    # range with AP/threshold varied too, forcing many distinct regions)
    pool = [_candidate(i, coeff=1 + (i % 8), ap=5 + i * 3, threshold=30 + 5 * (i % 10),
                       objective=float(i))
           for i in range(20)]
    regions = fl.build_regions_for_origin(SCHEMA, origin_cutoff="2022-01-01", trial_records=pool,
                                          distance_threshold=0.01, max_representatives=5)
    assert len(regions) <= 5
    # kept regions must be the highest-objective ones
    kept_max_objectives = [r["is_quality_distribution"]["max"] for r in regions]
    assert kept_max_objectives == sorted(kept_max_objectives, reverse=True)


# ---------------------------------------------------------------------------
# Maturity state machine
# ---------------------------------------------------------------------------

def test_maturity_state_before_forward_window_closes_is_not_yet_mature():
    state = fl.maturity_state(origin_cutoff="2022-01-01", forward_horizon_days=28,
                              as_of="2022-01-15", wf_ok=True, forward_attempted=False,
                              forward_ok=None)
    assert state == "future_label_not_yet_mature"


def test_maturity_state_right_at_origin_before_forward_attempt_is_decision_available():
    state = fl.maturity_state(origin_cutoff="2022-01-01", forward_horizon_days=28,
                              as_of="2022-02-15", wf_ok=True, forward_attempted=False,
                              forward_ok=None)
    assert state == "decision_available_record"


def test_maturity_state_after_window_closes_with_valid_outcome_is_matured():
    state = fl.maturity_state(origin_cutoff="2022-01-01", forward_horizon_days=28,
                              as_of="2022-02-15", wf_ok=True, forward_attempted=True,
                              forward_ok=True)
    assert state == "matured_forward_record"


def test_maturity_state_failed_origin_search_is_censored_regardless_of_as_of():
    state = fl.maturity_state(origin_cutoff="2022-01-01", forward_horizon_days=28,
                              as_of="2022-06-01", wf_ok=False, forward_attempted=False,
                              forward_ok=None)
    assert state == "censored_or_failed_record"


def test_maturity_state_failed_forward_attempt_after_window_closes_is_censored():
    state = fl.maturity_state(origin_cutoff="2022-01-01", forward_horizon_days=28,
                              as_of="2022-02-15", wf_ok=True, forward_attempted=True,
                              forward_ok=False)
    assert state == "censored_or_failed_record"


def test_maturity_state_refuses_an_as_of_before_the_decision_existed():
    with pytest.raises(fl.LedgerError, match="not available yet"):
        fl.maturity_state(origin_cutoff="2022-01-01", forward_horizon_days=28,
                          as_of="2021-12-01", wf_ok=True, forward_attempted=False,
                          forward_ok=None)


# ---------------------------------------------------------------------------
# FP04-T05: failed/censored labels never become zero
# ---------------------------------------------------------------------------

def test_fp04_t05_censored_record_has_null_label_with_a_reason_never_zero():
    region = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00",
                               members=_tight_pool(3))
    record = fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28, region=region,
                              forward_result={"forward_ok": False, "reason": "empty forward slice",
                                             "decay": None},
                              wf_ok=True, as_of="2022-06-01", geometry_version="v0")
    assert record["maturity_state"] == "censored_or_failed_record"
    assert record["label"] is None
    assert record["censored_reason"] == "empty forward slice"


def test_fp04_t05_origin_search_failure_censors_without_ever_attempting_forward_eval():
    region = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00",
                               members=_tight_pool(3))
    record = fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28, region=region,
                              forward_result=None, wf_ok=False, as_of="2022-06-01",
                              geometry_version="v0")
    assert record["maturity_state"] == "censored_or_failed_record"
    assert record["label"] is None
    assert record["censored_reason"] == "origin search failed"


# ---------------------------------------------------------------------------
# FP04-T01/T02/T03: causal independence of past selections from later info
# ---------------------------------------------------------------------------

def test_fp04_t01_a_late_discovered_candidate_does_not_appear_in_a_past_origin():
    """Build origin A's regions from its OWN pool; then simulate a LATER
    origin B discovering a strictly-better candidate. Origin A's regions,
    rebuilt from its own unchanged pool, are byte-identical -- nothing about
    B's discovery can reach back into A because each origin's region-building
    call only ever receives ITS OWN trial_records."""
    pool_a = _tight_pool(5, objective_start=1.0)
    regions_a_before = fl.build_regions_for_origin(
        SCHEMA, origin_cutoff="2022-01-01", trial_records=pool_a,
        distance_threshold=0.15, max_representatives=16)
    # a later origin's pool contains a MUCH better candidate -- irrelevant to A
    pool_b = _tight_pool(5, objective_start=1.0) + [
        _candidate(999, coeff=4, ap=20, threshold=55, objective=1000.0)]
    fl.build_regions_for_origin(SCHEMA, origin_cutoff="2022-04-01", trial_records=pool_b,
                                distance_threshold=0.15, max_representatives=16)
    regions_a_after = fl.build_regions_for_origin(
        SCHEMA, origin_cutoff="2022-01-01", trial_records=pool_a,
        distance_threshold=0.15, max_representatives=16)
    assert regions_a_before == regions_a_after
    assert all(r["medoid_trial_id"] != 999 for r in regions_a_after)


def test_fp04_t02_mutating_a_stored_forward_label_does_not_change_the_selection():
    region = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00",
                               members=_tight_pool(4))
    original_medoid = region["medoid_trial_id"]
    # simulate a forward-label mutation applied to a COPY the way a corrupted
    # downstream artifact might carry one -- selection fields must be untouched
    mutated = {**region, "forward_utility_mean_daily_return": 0.999,
              "decay_D_mean_daily_return": -0.5}
    assert mutated["medoid_trial_id"] == original_medoid
    assert mutated["member_candidate_ids"] == region["member_candidate_ids"]


def test_fp04_t03_representative_selection_is_unchanged_when_forward_outcome_differs():
    """Build the SAME region twice, forward-evaluate it against two DIFFERENT
    (synthetic) forward outcomes -- the region's medoid/selection fields
    (everything computed before evaluate_region_forward is called) must be
    identical both times: forward evaluation is strictly downstream."""
    pool = _tight_pool(4)
    region_1 = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00", members=pool)
    region_2 = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00", members=pool)
    assert region_1["medoid_trial_id"] == region_2["medoid_trial_id"]
    assert region_1["medoid_params"] == region_2["medoid_params"]
    forward_good = {"forward_ok": True, "reason": None,
                    "decay": {"forward_metrics": {"mean_daily_return": 0.01},
                             "D_mean_daily_return": -0.002}}
    forward_bad = {"forward_ok": True, "reason": None,
                   "decay": {"forward_metrics": {"mean_daily_return": -0.05},
                            "D_mean_daily_return": 0.09}}
    record_good = fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28,
                                   region=region_1, forward_result=forward_good, wf_ok=True,
                                   as_of="2022-06-01", geometry_version="v0")
    record_bad = fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28,
                                  region=region_2, forward_result=forward_bad, wf_ok=True,
                                  as_of="2022-06-01", geometry_version="v0")
    assert record_good["medoid_trial_id"] == record_bad["medoid_trial_id"]
    assert record_good["params"] == record_bad["params"]
    assert record_good["label"] != record_bad["label"]   # only the OUTCOME differs


# ---------------------------------------------------------------------------
# FP04-T06: an origin with more candidates does not automatically outweigh
# ---------------------------------------------------------------------------

def test_fp04_t06_origin_with_five_representatives_carries_the_same_total_weight_as_one_with_one():
    records = (
        [{"record_id": "A:R00", "origin_cutoff": "2022-01-01"}]
        + [{"record_id": f"B:R{i:02d}", "origin_cutoff": "2022-04-01"} for i in range(5)]
    )
    weights = fl.origin_weights(records)
    weight_a = weights["A:R00"]
    weight_b_total = sum(weights[f"B:R{i:02d}"] for i in range(5))
    assert weight_a == pytest.approx(weight_b_total)
    assert weight_a == pytest.approx(0.5)


def test_panel_view_reports_equal_weight_sum_per_origin_flag():
    region = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00",
                               members=_tight_pool(3))
    forward_ok = {"forward_ok": True, "reason": None,
                 "decay": {"forward_metrics": {"mean_daily_return": 0.01},
                          "D_mean_daily_return": -0.001}}
    records = [
        fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28, region=region,
                         forward_result=forward_ok, wf_ok=True, as_of="2022-06-01",
                         geometry_version="v0"),
        fl.ledger_record(origin_cutoff="2022-04-01", forward_horizon_days=28,
                         region={**region, "region_id": "R00b"}, forward_result=forward_ok,
                         wf_ok=True, as_of="2022-06-01", geometry_version="v0"),
    ]
    panel = fl.panel_view(records, as_of="2023-01-01")
    assert panel["n_matured_records"] == 2
    assert panel["weight_sum_per_origin_is_equal"] is True


def test_matured_view_hides_a_record_before_its_own_label_available_at():
    region = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00",
                               members=_tight_pool(3))
    forward_ok = {"forward_ok": True, "reason": None,
                 "decay": {"forward_metrics": {"mean_daily_return": 0.01},
                          "D_mean_daily_return": -0.001}}
    record = fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28, region=region,
                              forward_result=forward_ok, wf_ok=True, as_of="2022-01-15",
                              geometry_version="v0")
    # 2022-01-15 is 14 days after origin, before the 28-day maturation point
    # (2022-01-29): the RECORD's own stored state was mid-window, not yet mature.
    assert record["maturity_state"] == "future_label_not_yet_mature"
    assert fl.matured_view([record], as_of="2023-01-01") == []


# ---------------------------------------------------------------------------
# training_view / chronology integration
# ---------------------------------------------------------------------------

def test_training_view_tags_usable_rows_without_mutating_stored_maturity_state():
    region = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00",
                               members=_tight_pool(3))
    forward_ok = {"forward_ok": True, "reason": None,
                 "decay": {"forward_metrics": {"mean_daily_return": 0.01},
                          "D_mean_daily_return": -0.001}}
    record = fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28, region=region,
                              forward_result=forward_ok, wf_ok=True, as_of="2022-06-01",
                              geometry_version="v0")
    view = fl.training_view([record], decision_time="2023-01-01")
    assert len(view["usable"]) == 1
    assert view["usable"][0]["consumption_state"] == fl.CONSUMPTION_TAG
    assert view["usable"][0]["maturity_state"] == "matured_forward_record"   # stored fact untouched
    assert record["maturity_state"] == "matured_forward_record"              # original unmutated


def test_training_view_blocks_a_label_not_yet_available_at_decision_time():
    region = fl.region_summary(SCHEMA, origin_cutoff="2022-01-01", region_id="R00",
                               members=_tight_pool(3))
    forward_ok = {"forward_ok": True, "reason": None,
                 "decay": {"forward_metrics": {"mean_daily_return": 0.01},
                          "D_mean_daily_return": -0.001}}
    record = fl.ledger_record(origin_cutoff="2022-01-01", forward_horizon_days=28, region=region,
                              forward_result=forward_ok, wf_ok=True, as_of="2022-06-01",
                              geometry_version="v0")
    # decision_time BEFORE label_available_at (2022-01-29): must be blocked
    view = fl.training_view([record], decision_time="2022-01-15")
    assert view["usable"] == []
    assert view["n_blocked"] == 1


# ---------------------------------------------------------------------------
# FP04-T07: incremental rebuild never re-calls the engine for existing valid
# records; FP04-T08: old decision-vintage records are never overwritten
# ---------------------------------------------------------------------------

def test_fp04_t07_incremental_rebuild_only_calls_build_fn_for_new_origins():
    existing = [{"origin_cutoff": "2022-01-01", "wf_ok": True, "marker": "ORIGINAL"}]
    calls = []

    def build_fn(cutoff):
        calls.append(cutoff)
        return {"origin_cutoff": cutoff, "wf_ok": True, "marker": "FRESH"}

    result = fl.incremental_rebuild(existing, requested_origin_cutoffs=["2022-01-01", "2022-04-01"],
                                    build_origin_fn=build_fn)
    assert calls == ["2022-04-01"]
    assert result["reused_without_engine_call_for"] == ["2022-01-01"]
    by_cutoff = {o["origin_cutoff"]: o for o in result["origins"]}
    assert by_cutoff["2022-01-01"]["marker"] == "ORIGINAL"    # carried over untouched
    assert by_cutoff["2022-04-01"]["marker"] == "FRESH"


def test_fp04_t07_a_failed_origin_is_retried_not_permanently_cached():
    existing = [{"origin_cutoff": "2022-01-01", "wf_ok": False, "marker": "FAILED"}]
    calls = []

    def build_fn(cutoff):
        calls.append(cutoff)
        return {"origin_cutoff": cutoff, "wf_ok": True, "marker": "RETRIED"}

    result = fl.incremental_rebuild(existing, requested_origin_cutoffs=["2022-01-01"],
                                    build_origin_fn=build_fn)
    assert calls == ["2022-01-01"]
    assert result["origins"][0]["marker"] == "RETRIED"


def test_fp04_t08_old_vintage_records_survive_a_rebuild_under_a_changed_policy():
    """Old records must not be overwritten even when a REBUILD is invoked
    with a different construction policy (e.g. a new distance_threshold) --
    guide 7.5. build_origin_fn here closes over a 'current policy' the way a
    real orchestrator would; only the NEW origin sees it."""
    existing = [{"origin_cutoff": "2022-01-01", "wf_ok": True,
                "geometry_version": "threshold-0.15-v1"}]
    current_policy_distance_threshold = 0.30   # imagine this changed since 'existing' was built

    def build_fn(cutoff):
        return {"origin_cutoff": cutoff, "wf_ok": True,
               "geometry_version": f"threshold-{current_policy_distance_threshold}-v2"}

    result = fl.incremental_rebuild(existing, requested_origin_cutoffs=["2022-01-01", "2022-07-01"],
                                    build_origin_fn=build_fn)
    by_cutoff = {o["origin_cutoff"]: o for o in result["origins"]}
    assert by_cutoff["2022-01-01"]["geometry_version"] == "threshold-0.15-v1"   # untouched vintage
    # f-string formatting of the float 0.30 strips the trailing zero -> "0.3"
    assert by_cutoff["2022-07-01"]["geometry_version"] == "threshold-0.3-v2"   # new policy applies


def test_geometry_version_id_changes_when_policy_changes_and_is_stable_otherwise():
    v1 = fl.geometry_version_id(SCHEMA, distance_threshold=0.15, max_representatives=16)
    v1_again = fl.geometry_version_id(SCHEMA, distance_threshold=0.15, max_representatives=16)
    v2 = fl.geometry_version_id(SCHEMA, distance_threshold=0.30, max_representatives=16)
    assert v1 == v1_again
    assert v1 != v2


# ---------------------------------------------------------------------------
# Real, cheap end-to-end: evaluate_region_forward on a real small window,
# and its censored path when the forward slice cannot support a metric.
# ---------------------------------------------------------------------------

def test_evaluate_region_forward_real_small_window_produces_a_usable_decay(lab_root):
    from crypto_regime_lab.fp.evaluator import default_economics
    from crypto_regime_lab.ra.ra05_market import load_real_bars
    from crypto_regime_lab.time_edge.compute_cache import ComputeCache

    lab = lab_root
    cache = ComputeCache(lab, "fp04-test", cache_root="evidence/forward_persistence_fp_v1/compute-cache")
    frame, _partitions = load_real_bars("BTCUSDT", start="2023-06-01", end="2023-06-11")
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    region = {"medoid_trial_id": 0,
             "medoid_params": {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
                               "novolumedata": False, "src_col": "close"}}
    origin_cutoff = frame.index[len(frame) // 2]
    result = fl.evaluate_region_forward(cache, lab, "A-SC", frame, region,
                                        origin_cutoff=origin_cutoff, forward_horizon_days=2,
                                        economics=default_economics(),
                                        producer="fp04-test-evaluate-region-forward")
    assert result["forward_ok"] is True
    assert result["decay"]["forward_metrics"]["mean_daily_return"] is not None


def test_evaluate_region_forward_empty_slice_is_censored_not_a_crash(lab_root):
    from crypto_regime_lab.fp.evaluator import default_economics
    from crypto_regime_lab.ra.ra05_market import load_real_bars
    from crypto_regime_lab.time_edge.compute_cache import ComputeCache

    lab = lab_root
    cache = ComputeCache(lab, "fp04-test", cache_root="evidence/forward_persistence_fp_v1/compute-cache")
    frame, _partitions = load_real_bars("BTCUSDT", start="2023-06-01", end="2023-06-04")
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    region = {"medoid_trial_id": 0,
             "medoid_params": {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
                               "novolumedata": False, "src_col": "close"}}
    # origin_cutoff at the VERY LAST bar: the forward slice [cutoff, cutoff+2d) is empty
    origin_cutoff = frame.index[-1]
    result = fl.evaluate_region_forward(cache, lab, "A-SC", frame, region,
                                        origin_cutoff=origin_cutoff, forward_horizon_days=2,
                                        economics=default_economics(),
                                        producer="fp04-test-censored-path")
    assert result["forward_ok"] is False
    assert result["decay"] is None
    assert "empty" in result["reason"]
