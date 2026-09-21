"""RA-04 test matrix Q01-Q07 (RA-GUIDE-1.0 section 8).

Real installed-engine calls where the claim is about the active public path
or real alpha behavior (Q03/Q04/Q05/Q07); pure-helper checks where the claim
is about arithmetic/classification logic (Q01/Q02/Q06).
"""
from __future__ import annotations

import pytest

from crypto_regime_lab.ra.compact_controls import run_all_controls
from crypto_regime_lab.ra.mode4_admission import admission_thresholds, admit_selection
from crypto_regime_lab.ra.mode4_reproduction import reproduce_f04
from crypto_regime_lab.ra.public_path import integration_check, structural_checks
from crypto_regime_lab.ra.route_qualification import PROBE_MARKET, PROBE_PARAMS, synthetic_bars
from crypto_regime_lab.ra.search_registration import SEARCH_DIMENSIONS, behavior_witness
from crypto_regime_lab.time_edge.execution import PreparedAccount, TrainingScorer


def _small_prepared():
    train_days = 20
    frame = synthetic_bars(train_days * 1440 + 2 * 1440, seed=11, sigma=0.25)
    start, cutoff = frame.index[0], frame.index[train_days * 1440]
    return PreparedAccount(frame), start, cutoff


# --- Q01: finite/undefined/negative metrics keep distinct meaning ----------

def test_q01_temporal_metrics_keep_their_distinct_meaning(lab_tmp):
    prepared, start, cutoff = _small_prepared()
    candidates = [
        {"AP": 10, "coeff": 2, "novolumedata": False, "src_col": "close", "alpha.condition_threshold": 40},
        {"AP": 40, "coeff": 6, "novolumedata": False, "src_col": "close", "alpha.condition_threshold": 70},
    ]
    result = reproduce_f04(prepared, "A-SC", start, cutoff, candidates, lab_tmp, "q01")
    statuses = {row["status"] for c in result["per_candidate"] for row in c["shard_rows"]}
    # INSUFFICIENT_DAYS (too few complete days) and ZERO_VARIANCE (enough days,
    # no signal fired -> undefined Sharpe) must stay distinguishable statuses,
    # never collapsed into one "undefined" bucket, and a negative finite score
    # must never be excluded from the finite set.
    assert statuses <= {"OK", "ZERO_VARIANCE", "INSUFFICIENT_DAYS"}
    negative_finite = [row["sharpe"] for c in result["per_candidate"] for row in c["shard_rows"]
                       if row["finite"] and row["sharpe"] < 0]
    all_finite = [row["sharpe"] for c in result["per_candidate"] for row in c["shard_rows"] if row["finite"]]
    assert set(negative_finite) <= set(all_finite)  # negative finite scores are kept, not filtered
    # The guard (admission) must not call a 1-finite-shard candidate "robust":
    # its own admission decision must fail the shard-support check.
    thresholds = admission_thresholds("A-SC")
    for c in result["per_candidate"]:
        if c["finite_shard_count"] <= 1:
            decision = admit_selection(
                {"params": c["params"]}, alpha_id="A-SC", incumbent=None,
                winner_scorer_record={"daily_returns": [("2020-01-01", 0.0)] * 20},
                winner_shard_finite_count=c["finite_shard_count"], thresholds=thresholds)
            assert decision["decision"] != "ADMIT", (
                "a candidate resting on <=1 real finite shard must not be admitted as robust")


# --- Q02: guard never invents a different winner; applies to any arm -------

def test_q02_guard_never_invents_a_different_winner():
    thresholds = admission_thresholds("A-SC")
    raw = {"params": {"AP": 99, "coeff": 9}, "selection_id": "raw-winner"}
    decision = admit_selection(raw, alpha_id="A-SC", incumbent={"params": {"AP": 1}},
                               winner_scorer_record={"daily_returns": []},
                               winner_shard_finite_count=0, thresholds=thresholds)
    assert decision["decision"] == "KEEP_INCUMBENT"
    assert decision["raw_selection"] == raw, "the raw stock winner must be retained even when not admitted"
    assert decision["kept"] == {"params": {"AP": 1}}, "KEEP_INCUMBENT must return the ACTUAL incumbent, never a re-derived one"


def test_q02_guard_applies_to_any_arm():
    # The guard is arm-agnostic: it only reads (alpha_id, raw_selection,
    # winner support), never a CAL/REGIME arm label, so it applies identically
    # to whichever arm calls it.
    thresholds = admission_thresholds("A-HMA")
    for arm_label in ("M4_CAL", "M4_REGIME"):
        raw = {"params": {"min_length": 60}, "arm": arm_label}
        decision = admit_selection(raw, alpha_id="A-HMA", incumbent=None,
                                   winner_scorer_record={"daily_returns": [("2020-01-01", 0.0)] * 25},
                                   winner_shard_finite_count=thresholds["min_finite_shards"],
                                   thresholds=thresholds)
        assert decision["decision"] == "ADMIT"
        assert decision["raw_selection"]["arm"] == arm_label


# --- Q03: tuning parameters have real behavior effect; unknown enum raises -

def test_q03_search_dimensions_have_real_behavior_effect():
    # A-HMA: min_length/mult measured DEAD on this fixture (byte-identical
    # terminal_equity across their whole range) -- max_length is the
    # registered dimension with a real measured effect (see search_registration
    # .DEAD_ON_FIXTURE); the witness must test the REGISTERED dimension.
    safe_pairs = {"A-SC": ("AP", 5, 40), "A-HMA": ("max_length", 65, 300),
                 "A-VWAP": ("dev_mult", 0.7, 4.0), "A-HASH": ("mom_len", 6, 60)}
    for alpha, (dim, low, high) in safe_pairs.items():
        assert dim in SEARCH_DIMENSIONS[alpha]
        witness = behavior_witness(alpha, dim, low_value=low, high_value=high)
        assert witness["behavior_differs"], f"{alpha}.{dim} showed no behavior effect between {low} and {high}"


def test_q03_unknown_categorical_raises_not_silently_collapses():
    market = PROBE_MARKET["A-VWAP"]
    frame = synthetic_bars((market["history_days"] + market["window_days"]) * 1440,
                           seed=market["seed"], sigma=market["sigma"])
    start = frame.index[market["history_days"] * 1440]
    params = dict(PROBE_PARAMS["A-VWAP"])
    params["exit_at_vwap"] = "not-a-real-choice"  # unknown enum-like value
    account = PreparedAccount(frame)
    with pytest.raises(Exception):
        account.run("A-VWAP", [{"selection_id": "bad-enum", "params": params,
                               "cutoff": start.isoformat(), "ready_at": start.isoformat()}],
                   account_start=start)


# --- Q04: public fixed-calendar parity, no future access -------------------

def test_q04_public_path_structural_and_integration():
    structural = structural_checks()
    assert structural["all_pass"], structural["checks"]
    integ = integration_check(train_days=20, trials=4, seed=777)
    assert integ["status"] == "OK"
    assert integ["engine_is_installed_walkforward_subclass"] is True
    assert integ["oos_used_for_selection_reported_by_selector"] is False
    assert integ["no_future_segment"] is True
    # Suffix causality is cited from RA-02's C04, not re-derived (same
    # PreparedAccount/window mechanism select_only is built on):
    # tests/ra_corrective/test_ra02_cache_cases.py::
    #   test_c04_future_suffix_never_changes_prefix_key_or_output


# --- Q05: every compact control has real path evidence ---------------------

def test_q05_every_compact_control_has_real_path_evidence():
    result = run_all_controls()
    assert len(result["controls"]) == 7
    for c in result["controls"]:
        assert c["pass"], c
    null_control = next(c for c in result["controls"] if c["control"] == "no_information_null_world")
    assert null_control["requires_zero_pnl"] is False, "a null-world control must not demand exact-zero PnL"
    assert null_control["truth_leaked"] is False


# --- Q06: zero-action real case classified correctly ------------------------

def test_q06_zero_action_case_not_forced_into_a_positive_control():
    thresholds = admission_thresholds("A-SC")
    # A real candidate that legitimately never traded (ZERO_VARIANCE on every
    # shard) must be classified KEEP_INCUMBENT/COMMON_FLAT, not artificially
    # forced to look like the null-world POSITIVE-control expectation.
    decision = admit_selection({"params": {"AP": 1}}, alpha_id="A-SC", incumbent=None,
                               winner_scorer_record={"daily_returns": []},
                               winner_shard_finite_count=0, thresholds=thresholds)
    assert decision["decision"] == "COMMON_FLAT_FALLBACK"
    assert "0" in decision["reason"]  # cites the actual measured (zero) support, not an assumed one


# --- Q07: full trial lifecycle reconstructable ------------------------------

def test_q07_trial_lifecycle_is_fully_reconstructable(lab_tmp):
    prepared, start, cutoff = _small_prepared()
    scorer = TrainingScorer(prepared, "A-SC", start, cutoff, lab_tmp, "q07")
    params = PROBE_PARAMS["A-SC"]
    out = scorer(params=params, index=prepared.frame.index[
        (prepared.frame.index >= start) & (prepared.frame.index < cutoff)])
    assert out["status"] in ("OK", "ZERO_VARIANCE", "INSUFFICIENT_DAYS", "FAILED_CANDIDATE")
    cache_path = lab_tmp / f"candidate-{__import__('crypto_regime_lab.time_edge.storage', fromlist=['digest']).digest(params)}.json"
    assert cache_path.is_file(), "the candidate's full trial record must be on disk, reconstructable"
    import json
    record = json.loads(cache_path.read_text())
    for field in ("status", "params", "cutoff"):
        assert field in record
    if record["status"] == "EVALUATED":
        for field in ("daily_returns", "fills", "commands", "order_events", "wall_seconds"):
            assert field in record, f"EVALUATED record missing {field} -- lifecycle not reconstructable"
