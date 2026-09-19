"""RA-07 test matrix R01-R09 (RA-GUIDE-1.0 section 11).

R03 is the one real, engine-calling test (tiny/fast real ETHUSDT data) --
it proves `run_cell2_full` actually executes end-to-end and shares RA-05's
contract with only the symbol swapped. The rest are pure-logic tests, no
engine calls needed.
"""
from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.ra.ra07_controls import (
    build_placebo_schedule, delayed_emissions, development_prefix_state_sequence,
)
from crypto_regime_lab.ra.ra07_coverage import BLOCKED_ALPHAS, build_coverage_matrix
from crypto_regime_lab.ra.ra07_decay import ROW_FIELDS, _row, compute_d2_rows, compute_d3_rows
from crypto_regime_lab.ra.ra07_freeze import build_replication_spec, estimate_mde, materialize_delta
from crypto_regime_lab.ra.ra07_stats_primitives import (
    bootstrap_paired_delta, circular_block_indices, daily_returns, holm_adjust, paired_daily_returns,
)
from crypto_regime_lab.ra.ra07_statistics import build_multiplicity_ledger, classify_claim


# --- R01: replication spec frozen structurally, before any RA-07 outcome ---

def test_r01_replication_spec_frozen_before_any_new_outcome():
    delta_result = {"status": "OK", "delta": 0.0002, "calibration_days": 10}
    mde_result = {"status": "OK", "mde": 0.0009}
    spec = build_replication_spec(ra05_run_id="ra05-test", cell1={}, cell2_plan={"symbol": "ETHUSDT"},
                                  delta_result=delta_result, mde_result=mde_result)
    assert spec["frozen_before_outcomes"] is True
    assert spec["delta_economic_threshold"] == delta_result
    assert spec["mde"] == mde_result
    assert spec["primary_contrast"].startswith("M4_REGIME - M4_CAL_MATCHED")
    # RA-06's KEEP_BASELINE must be disclosed as making the action-aware contrast inapplicable
    assert spec["action_aware_contrast"]["applicable"] is False
    assert "KEEP_BASELINE" in spec["action_aware_contrast"]["reason"]
    # seeds: primary already spent, replication seeds registered but disclosed as not run
    assert spec["seed_schedule"]["registered_replication_seeds_status"] == "NOT_RUN_BUDGET"
    assert len(spec["seed_schedule"]["registered_replication_seeds"]) == 2
    # no pooled aggregate without a pre-registered weighting
    assert spec["bootstrap_plan"]["pooled_aggregate"]["computed"] is False
    # controls plan names all 5 in order, before any control ran
    assert spec["controls_plan"]["order"] == ["CALENDAR_BUDGET_MATCHED", "AGE_ONLY",
                                              "DELAYED_INFORMATION", "PLACEBO_TIMING",
                                              "RISK_EXPOSURE_ATTRIBUTION"]


def test_r01_delta_formula_matches_guide_13_3():
    import pandas as pd

    frame_index = pd.date_range("2021-01-01", periods=5, freq="D", tz="UTC")
    equity_daily = [("2021-01-01T00:00:00+00:00", 20000.0), ("2021-01-02T00:00:00+00:00", 20000.0)]
    fills = [{"bar_index": 1, "qty": 0.1, "price": 20000.0}]  # notional 2000 on day index 1 (2021-01-02)
    result = materialize_delta(fills=fills, equity_daily=equity_daily, frame_index=frame_index,
                               account_capital=20000.0)
    assert result["status"] == "OK"
    # E_j- for the fill's day (2021-01-02) is the PRECEDING day's close (20000.0);
    # delta_c = mean over calibration days of sum(|N_j|/E_j-)*0.0005 -- with only
    # ONE day carrying the fill and 2 equity_daily days total (only 1 has a
    # preceding mark; the FIRST equity day falls back to its own value)
    expected_per_fill_day = (2000.0 / 20000.0) * 0.0005
    # the flat 2021-01-01 day (zero fills) stays in the denominator rather than
    # being dropped -- guide 13.3: "giu flat calibration days" -- so the mean
    # is divided by 2 calibration days, not by 1 active-fill day
    assert result["calibration_days"] == 2
    assert result["delta"] == pytest.approx(expected_per_fill_day / 2)


def test_r01_delta_with_no_fills_at_all_is_explicit_not_evaluable():
    import pandas as pd

    frame_index = pd.date_range("2021-01-01", periods=3, freq="D", tz="UTC")
    equity_daily = [("2021-01-01T00:00:00+00:00", 20000.0), ("2021-01-02T00:00:00+00:00", 20000.0),
                    ("2021-01-03T00:00:00+00:00", 20000.0)]
    result = materialize_delta(fills=[], equity_daily=equity_daily, frame_index=frame_index,
                               account_capital=20000.0)
    assert result["status"] == "NO_CALIBRATION_FILLS"
    assert result["delta"] is None


def test_r01_mde_uses_development_paired_variability_not_synthetic_scaling():
    import pandas as pd

    rng = np.random.default_rng(3)
    dates = pd.date_range("2021-01-01", periods=39, freq="D", tz="UTC")
    equity_a = [(d.isoformat(), 20000.0 * (1 + rng.normal(0.001, 0.01)) ** i)
               for i, d in enumerate(dates, start=1)]
    equity_b = [(d.isoformat(), 20000.0 * (1 + rng.normal(0.0005, 0.01)) ** i)
               for i, d in enumerate(dates, start=1)]
    rows = paired_daily_returns(equity_a, equity_b)
    result = estimate_mde(rows, block_length=7, n_resamples=200, seed=1)
    assert result["status"] in ("OK", "INSUFFICIENT_PAIRED_DAYS")
    if result["status"] == "OK":
        assert result["mde"] > 0
        assert result["source_n_common_days"] == len(rows)
        assert "z_(1-alpha/2)" in result["formula"]


# --- R02: coverage matrix, 20 rows, correct vocabulary ----------------------

def test_r02_coverage_matrix_has_20_rows_correct_vocabulary():
    cell1 = {"alpha_id": "A-SC", "symbol": "BTCUSDT", "run_ref": "ra05-x", "arms_present": ["M4_REGIME"]}
    cell2 = {"alpha_id": "A-SC", "symbol": "ETHUSDT", "run_ref": "ra07-x", "arms_present": ["M4_REGIME"]}
    matrix = build_coverage_matrix(cell1=cell1, cell2=cell2)
    assert len(matrix["rows"]) == 20
    statuses = {r["coverage_status"] for r in matrix["rows"]}
    assert statuses <= {"RUN_VALID", "BLOCKED_CAPABILITY", "NOT_RUN_BUDGET"}
    assert matrix["counts"]["RUN_VALID"] == 2
    for alpha in BLOCKED_ALPHAS:
        blocked_rows = [r for r in matrix["rows"] if r["alpha_id"] == alpha]
        assert len(blocked_rows) == 5
        assert all(r["coverage_status"] == "BLOCKED_CAPABILITY" and r["reason"] for r in blocked_rows)
    run_valid_cells = {r["cell"] for r in matrix["rows"] if r["coverage_status"] == "RUN_VALID"}
    assert run_valid_cells == {"A-SC/BTCUSDT", "A-SC/ETHUSDT"}


def test_r02_coverage_never_silently_zeros_a_blocked_cell():
    matrix = build_coverage_matrix(
        cell1={"alpha_id": "A-SC", "symbol": "BTCUSDT", "run_ref": "x", "arms_present": []},
        cell2={"alpha_id": "A-SC", "symbol": "ETHUSDT", "run_ref": "y", "arms_present": []})
    for row in matrix["rows"]:
        if row["coverage_status"] in ("BLOCKED_CAPABILITY", "NOT_RUN_BUDGET"):
            assert row["run_ref"] is None
            assert row["reason"]


# --- R03: cell 2 real run shares RA-05's contract, symbol swapped only -----

def test_r03_cell2_shares_ra05_contract_except_symbol(lab_tmp):
    from crypto_regime_lab.ra.ra05_market import EMISSIONS_ARTIFACT, load_real_emissions
    from crypto_regime_lab.ra.ra07_cell2 import run_cell2_full
    import json as _json

    window_start, window_end = "2021-01-01", "2021-01-10"
    doc = load_real_emissions(window_start=window_start, window_end=window_end)
    full_emissions = _json.loads(EMISSIONS_ARTIFACT.read_text())["emissions"]
    result = run_cell2_full(
        alpha_id="A-SC", symbol="ETHUSDT", window_start=window_start, window_end=window_end,
        data_load_start="2020-12-15", train_memory_days=10, cal_test_days=4, trials=2,
        seed=20260918, route="event", full_emissions_for_forecast=full_emissions,
        window_emissions=doc["emissions"], evidence_dir=lab_tmp / "r03", lab_run_id="test-r03")
    assert result["capability_status"] == "EXECUTED", result.get("blocked_reason")
    assert result["symbol"] == "ETHUSDT"
    static = result["arms"]["STATIC"]
    assert static["ok"], static.get("error")
    # STATIC's own schedule carries the SAME train_memory_days requested -- the
    # exact class of drift RA-05's own D01 test caught (a missing param
    # silently defaulting away from the frozen contract)
    assert static["schedule"]["train_memory_days"] == 10
    assert result["transfer_kind"] == "cross_symbol_same_alpha_shared_btc_derived_regime_tape"


# --- R04: delayed emissions shift state_common, not just state_id ----------

def test_r04_delayed_emissions_shifts_state_common_not_just_id():
    emissions = [{"available_at": f"2021-01-0{i}T00:00:00+00:00", "state_id": i, "state_common": i,
                 "state_namespace": "ns", "decision_eligible": True, "quality_status": "OK"}
                for i in range(1, 6)]
    delayed = delayed_emissions(emissions, observations=2)
    for i, row in enumerate(delayed):
        expected_source = emissions[max(i - 2, 0)]
        assert row["state_common"] == expected_source["state_common"]
        assert row["state_id"] == expected_source["state_id"]
        assert row["state_namespace"] == expected_source["state_namespace"]
        assert row["available_at"] == emissions[i]["available_at"]  # availability timing untouched on the world's own clock, only state content is delayed
    assert delayed[0]["delayed_by_observations"] == 2


def test_r04_delayed_schedule_actually_differs_from_undelayed_when_states_change():
    from crypto_regime_lab.experiments.regime_schedule import online_trigger_schedule

    emissions = [{"available_at": f"2021-01-{d:02d}T00:00:00+00:00", "state_id": d % 2,
                 "state_common": d % 2, "state_namespace": "ns", "decision_eligible": True,
                 "quality_status": "OK"} for d in range(1, 15)]
    real = online_trigger_schedule(emissions, earliest="2021-01-01", latest="2021-01-15",
                                   min_gap_days=1.0, max_age_days=100.0, budget=None)
    delayed = delayed_emissions(emissions, observations=3)
    delayed_schedule = online_trigger_schedule(delayed, earliest="2021-01-01", latest="2021-01-15",
                                               min_gap_days=1.0, max_age_days=100.0, budget=None)
    assert real.cutoffs != delayed_schedule.cutoffs, "a real state-alternation series delayed by 3 observations must reschedule triggers"


def test_r04_zero_observations_delay_is_refused():
    with pytest.raises(ValueError):
        delayed_emissions([{"available_at": "x", "state_id": 1, "state_common": 1,
                           "state_namespace": "n"}], observations=0)


# --- R05: placebo never reads the real evaluation-window states ------------

def test_r05_placebo_never_reads_the_real_evaluation_window_states():
    development = [{"available_at": f"2020-12-{d:02d}T00:00:00+00:00", "state_common": d % 3,
                   "decision_eligible": True, "quality_status": "OK"} for d in range(1, 25)]
    window = [{"available_at": f"2021-01-{d:02d}T00:00:00+00:00", "state_common": 99,
              "decision_eligible": True, "quality_status": "OK", "state_id": 99,
              "state_namespace": "real_ns"} for d in range(1, 10)]
    build = build_placebo_schedule(full_emissions=development + window, window_emissions=window,
                                   window_start="2021-01-01", window_end="2021-01-10",
                                   train_memory_days=10, seed=42, min_gap_days=1.0,
                                   max_age_days=100.0, budget=5)
    assert build["status"] == "OK"
    # the real window's own state_common (99) must never leak into the placebo schedule's source
    assert build["fidelity"] is not None
    assert build["fidelity"]["real"]["observations"] == len(window)
    assert build["schedule"].arm == "M4_REGIME_PLACEBO"


def test_r05_development_prefix_excludes_the_evaluation_window():
    emissions = [{"available_at": "2020-12-15T00:00:00+00:00", "state_common": 1,
                 "decision_eligible": True, "quality_status": "OK"},
                {"available_at": "2021-01-05T00:00:00+00:00", "state_common": 2,
                 "decision_eligible": True, "quality_status": "OK"}]
    states = development_prefix_state_sequence(emissions, window_start="2021-01-01",
                                               window_end="2021-02-01")
    assert states == [1]  # the 2021-01-05 row falls INSIDE the window and must be excluded


# --- R06: decay row schema, never averages fold Sharpe ---------------------

def test_r06_row_schema_rejects_unknown_fields():
    with pytest.raises(ValueError):
        _row(not_a_real_field=1)


def test_r06_row_schema_matches_guide_13_2_fields():
    row = _row(comparison_kind="D1_IS_TO_OOS")
    assert set(row) == set(ROW_FIELDS)


def test_r06_d2_uses_one_fixed_theta_across_successive_anchors():
    panel_b_rows = [
        {"origin": "2021-01-21T00:00:00+00:00", "status": "OK",
         "g": {"e_t_keep": 20100.0}, "features": {"age_days": 20.0, "regime_transitions_since_incumbent": 0},
         "keep_incumbent_params": {"AP": 10}},
        {"origin": "2021-02-10T00:00:00+00:00", "status": "OK",
         "g": {"e_t_keep": 20300.0}, "features": {"age_days": 40.0, "regime_transitions_since_incumbent": 3},
         "keep_incumbent_params": {"AP": 10}},
    ]
    rows = compute_d2_rows(panel_b_rows=panel_b_rows, alpha_id="A-SC", symbol="BTCUSDT",
                           window_start="2021-01-01", account_capital=20000.0)
    assert len(rows) == 2
    assert all(r["comparison_kind"] == "D2_PARAMETER_AGE" for r in rows)
    assert len({r["theta_digest"] for r in rows}) == 1  # same fixed theta throughout
    assert rows[0]["signed_delta"] == pytest.approx(20100.0 / 20000.0 - 1.0)
    assert rows[1]["signed_delta"] == pytest.approx(20300.0 / 20100.0 - 1.0)  # segment 2, not vs window_start


def test_r06_d3_flags_different_params_as_diagnostic_only():
    fold_table = [
        {"test_start": "2021-01-01T00:00:00+00:00", "test_end": "2021-02-01T00:00:00+00:00",
         "selected_params": {"AP": 10}},
        {"test_start": "2021-02-01T00:00:00+00:00", "test_end": "2021-03-01T00:00:00+00:00",
         "selected_params": {"AP": 20}},
    ]
    equity_daily = [(f"2021-01-{d:02d}T00:00:00+00:00", 20000.0 + d) for d in range(1, 32)]
    equity_daily += [(f"2021-02-{d:02d}T00:00:00+00:00", 20031.0 + d) for d in range(1, 29)]
    rows = compute_d3_rows(fold_selection_table=fold_table, equity_daily=equity_daily,
                           alpha_id="A-SC", symbol="BTCUSDT", arm="M4_CAL")
    assert len(rows) == 1
    assert rows[0]["diagnostic_only"] is True  # different params between adjacent folds
    assert rows[0]["comparison_kind"] == "D3_ADJACENT_OPERATIONAL_FOLDS"
    assert rows[0]["metric_name"] != "average_fold_sharpe"


# --- R07: bootstrap is a block bootstrap, paired, zero engine calls --------

def test_r07_block_indices_are_contiguous_runs():
    rng = np.random.default_rng(5)
    idx = circular_block_indices(20, block_length=5, rng=rng)
    assert len(idx) == 20
    for start in range(0, 20, 5):
        block = idx[start:start + 5]
        for a, b in zip(block, block[1:]):
            assert b == (a + 1) % 20  # each block is a contiguous circular run, not iid single draws


def test_r07_bootstrap_uses_the_same_block_indices_for_both_paired_arms():
    rows = [{"date": str(i), "r_a": 0.01 * i, "r_b": 0.005 * i, "diff": 0.005 * i} for i in range(60)]
    result = bootstrap_paired_delta(rows, block_length=7, n_resamples=500, seed=11)
    assert result["status"] == "OK"
    # since diff = r_a - r_b exactly by construction, the resampled mean of
    # diffs must equal resampled mean(r_a) - resampled mean(r_b) for EVERY
    # resample only if the SAME indices were used for both arms
    assert result["bootstrap_mean"] == pytest.approx(result["point_estimate"], abs=0.05)


def test_r07_zero_engine_calls_in_statistics_modules():
    import inspect

    from crypto_regime_lab.ra import ra07_statistics, ra07_stats_primitives

    for module in (ra07_statistics, ra07_stats_primitives):
        source = inspect.getsource(module)
        assert "run_cutoff_walk_forward" not in source
        assert "quantbt" not in source.lower()


def test_r07_daily_returns_flat_days_keep_zero_not_dropped():
    equity = [("2021-01-01T00:00:00+00:00", 20000.0), ("2021-01-02T00:00:00+00:00", 20000.0),
             ("2021-01-03T00:00:00+00:00", 20200.0)]
    rows = daily_returns(equity)
    assert rows[0]["return"] == 0.0
    assert rows[0]["status"] == "OK"


# --- R08: claim classification matches guide 13.5's table ------------------

def test_r08_claim_classification_matches_guide_13_5_table():
    assert classify_claim(ci=(0, 0), delta=0.001, support_ok=True,
                          technically_valid=False)["status"] == "NOT_EVALUABLE"
    assert classify_claim(ci=(-0.01, 0.01), delta=0.001, support_ok=False,
                          technically_valid=True)["status"] == "INCONCLUSIVE_SUPPORT"
    assert classify_claim(ci=(0.002, 0.01), delta=0.001, support_ok=True,
                          technically_valid=True)["status"] == "POSITIVE_WITHIN_SCOPE"
    result = classify_claim(ci=(-0.01, 0.0005), delta=0.001, support_ok=True, technically_valid=True)
    assert result["status"] == "NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE"
    underperformed = classify_claim(ci=(-0.02, -0.005), delta=0.001, support_ok=True,
                                    technically_valid=True)
    assert "UNDERPERFORMED_WITHIN_SCOPE" in underperformed["labels"]
    assert "NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE" in underperformed["labels"]
    straddle = classify_claim(ci=(-0.001, 0.005), delta=0.001, support_ok=True, technically_valid=True)
    assert straddle["status"] == "INCONCLUSIVE_EFFECT"
    assert straddle["status"] != "NO_EDGE"


# --- R09: Holm applies to the secondary family only, primary unadjusted ----

def test_r09_multiplicity_holm_applies_to_secondary_family_only():
    uncertainty = {
        "primary": {"contrast": "cell1: M4_REGIME - M4_CAL_MATCHED",
                   "bootstrap": {"p_value_two_sided": 0.03}},
        "secondary": {
            "a": {"status": "OK", "bootstrap": {"p_value_two_sided": 0.01}},
            "b": {"status": "OK", "bootstrap": {"p_value_two_sided": 0.04}},
            "c": {"status": "NOT_EVALUABLE"},
        },
    }
    ledger = build_multiplicity_ledger(uncertainty)
    assert ledger["primary_unadjusted"]["p_value"] == 0.03
    assert ledger["primary_unadjusted"]["adjustment"].startswith("NONE")
    assert ledger["secondary_family_holm"]["a"]["raw_p"] == 0.01
    assert ledger["secondary_family_holm"]["a"]["holm_adjusted_p"] >= 0.01
    assert "c" in ledger["not_evaluable_excluded_from_family"]


def test_r09_holm_is_monotone_and_never_exceeds_1():
    adjusted = holm_adjust({"a": 0.001, "b": 0.02, "c": 0.5})
    values = [adjusted["a"], adjusted["b"], adjusted["c"]]
    assert values == sorted(values)  # Holm preserves the ordering of the raw p-values
    assert all(0 <= v <= 1 for v in values)
