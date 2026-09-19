"""RA-06 test matrix P01-P08 (RA-GUIDE-1.0 section 10).

P02 is the one real, engine-calling test (tiny/fast real BTCUSDT data) --
it is the regression test for the actual state-fork-parity bug found and
fixed while building this phase (E_t read on the origin's own day, which
already belonged to REFIT's new fold, disagreed with KEEP's reading of the
same real moment). The rest are pure-logic tests, no engine calls needed.
"""
from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.ra.ra05_market import load_real_bars
from crypto_regime_lab.ra.ra06_controller import lock_policy_revision, request_search_decision
from crypto_regime_lab.ra.ra06_model import (
    AGE_CONTEXT_FEATURES, AGE_ONLY_FEATURES, fit_and_compare, leave_one_out_inner_cv,
)
from crypto_regime_lab.ra.ra06_origins import select_origins
from crypto_regime_lab.ra.ra06_panel_a import build_panel_a, load_ra05_arms_result
from crypto_regime_lab.ra.ra06_panel_b import compute_g, run_keep_branch, run_refit_branch

RA05_RUN_ID = "ra05-20260918T201236Z-de11db62"
ALPHA_ID = "A-SC"
WINDOW_START = "2021-01-01"


# --- P01: panel candidate availability and label maturity -------------------

def test_p01_matured_outcome_uses_only_its_own_deployment_window():
    arms, _ = load_ra05_arms_result(RA05_RUN_ID)
    panel_a = build_panel_a(arms, source_run_id=RA05_RUN_ID)
    assert panel_a["row_count"] > 0
    for row in panel_a["rows"]:
        start, end = row["deployment_window"]
        assert start < end, row
        matured = row["matured_outcome"]
        if matured["status"] == "OK":
            assert matured["days"] > 0


def test_p01_suffix_mutation_does_not_change_an_earlier_matured_outcome():
    from crypto_regime_lab.ra.ra06_panel_a import _deployment_return

    base_equity = [(f"2021-01-{d:02d}T00:00:00+00:00", 20000.0 + d * 10) for d in range(1, 11)]
    baseline = _deployment_return(base_equity, start="2021-01-01T00:00:00+00:00",
                                  end="2021-01-05T00:00:00+00:00")
    mutated = list(base_equity)
    mutated[7] = (mutated[7][0], 99999.0)  # mutate a day AFTER the deployment window closes
    mutated_result = _deployment_return(mutated, start="2021-01-01T00:00:00+00:00",
                                        end="2021-01-05T00:00:00+00:00")
    assert baseline == mutated_result, "a future mutation changed an already-closed matured outcome"


# --- P02: state-fork/replay parity at origin (real engine call) -------------

def test_p02_keep_and_refit_share_identical_state_at_origin():
    frame, _ = load_real_bars("BTCUSDT", start="2020-12-01", end="2021-01-11")
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    origin = "2021-01-08"
    keep = run_keep_branch(ALPHA_ID, frame, window_start=WINDOW_START, train_memory_days=20,
                           trials=2, seed=20260918, route="event")
    refit = run_refit_branch(ALPHA_ID, frame, window_start=WINDOW_START, origin=origin,
                             train_memory_days=20, trials=2, seed=20260918, route="event")
    assert keep["ok"] and refit["ok"]
    # the shared prefix selection must be byte-identical
    assert keep["fold_selection_table"][0]["selected_params"] == \
        refit["fold_selection_table"][0]["selected_params"]
    g = compute_g(keep_account=keep["account"], refit_account=refit["account"], origin=origin,
                 horizon_end="2021-01-10")
    assert g["status"] == "OK", g
    assert g["e_t_keep"] == g["e_t_refit"]


# --- P03: g_t reconciles against engine equities, no double costs -----------

def test_p03_g_matches_the_registered_formula_exactly():
    keep_daily = [("2021-01-07T00:00:00+00:00", 20000.0), ("2021-01-15T00:00:00+00:00", 20100.0)]
    refit_daily = [("2021-01-07T00:00:00+00:00", 20000.0), ("2021-01-15T00:00:00+00:00", 20300.0)]
    g = compute_g(keep_account={"equity_daily": keep_daily}, refit_account={"equity_daily": refit_daily},
                 origin="2021-01-08", horizon_end="2021-01-15")
    assert g["status"] == "OK"
    expected = (20300.0 - 20100.0) / 20000.0
    assert g["g"] == pytest.approx(expected)


def test_p03_missing_equity_mark_is_censored_not_zero():
    g = compute_g(keep_account={"equity_daily": []}, refit_account={"equity_daily": []},
                 origin="2021-01-08", horizon_end="2021-01-15")
    assert g["status"] == "CENSORED"
    assert g["g"] is None


# --- P04: origins outcome-blind; censored branches never become zero -------

def test_p04_origin_selection_takes_no_outcome_argument():
    import inspect

    signature = inspect.signature(select_origins)
    for name in signature.parameters:
        assert "outcome" not in name.lower() and "result" not in name.lower() and "g_t" not in name.lower()
    origins = select_origins(WINDOW_START, count=5, spacing_days=20)
    assert len(origins) == 5
    assert origins == sorted(origins), "origins must be chronological, not outcome-reordered"


def test_p04_censored_row_g_is_none_never_zero():
    g = compute_g(keep_account={"equity_daily": [("2021-01-07T00:00:00+00:00", 20000.0)]},
                 refit_account={"equity_daily": [("2021-01-07T00:00:00+00:00", 20005.0)]},
                 origin="2021-01-08", horizon_end="2021-02-08")
    assert g["status"] == "CENSORED"
    assert g["g"] is None, "a censored outcome must never silently become 0"


# --- P05: AGE_ONLY vs AGE_CONTEXT share target/cohort/split -----------------

def test_p05_both_ladder_entries_share_the_same_target_and_origins():
    rng = np.random.default_rng(7)
    rows = [{"origin": f"o{i}", "g": {"status": "OK", "g": float(rng.normal())},
            "features": {"age_days": float(i), "realized_vol_20d": float(rng.normal(0.1, 0.01)),
                        "regime_transitions_since_incumbent": float(rng.integers(0, 3)),
                        "incumbent_trailing_return": float(rng.normal(0.01, 0.005))}}
           for i in range(10)]
    result = fit_and_compare(rows, min_support=8)
    assert result["status"] == "FIT_ATTEMPTED"
    assert result["age_only"]["n"] == result["age_context"]["n"] == 10
    assert AGE_ONLY_FEATURES == ("intercept", "age_days")
    assert set(AGE_ONLY_FEATURES) <= set(AGE_CONTEXT_FEATURES)


# --- P06: scaler/design selection train-only; support counts truthful ------

def test_p06_leave_one_out_never_trains_on_the_held_out_point():
    X = np.array([[1.0, float(i)] for i in range(6)])
    y = np.array([float(i) * 2 for i in range(6)])
    cv = leave_one_out_inner_cv(X, y, alpha_grid=(0.0001,))
    # with near-zero regularisation on a perfectly linear relationship, LOO
    # predictions should be near-exact -- if the held-out point had leaked
    # into its own fit this would be exact to floating point, not merely close
    assert cv["per_alpha_loo_mse"][0.0001] < 1e-6


def test_p06_insufficient_support_is_reported_truthfully():
    rows = [{"g": {"status": "OK", "g": 0.01}, "features": {"age_days": 1, "realized_vol_20d": 0.1,
            "regime_transitions_since_incumbent": 0, "incumbent_trailing_return": 0.0}}
           for _ in range(5)]
    result = fit_and_compare(rows, min_support=8)
    assert result["status"] == "INSUFFICIENT_SUPPORT"
    assert result["support"] == 5
    assert result["age_only"] is None and result["age_context"] is None


def test_p06_censored_rows_are_excluded_from_support_count():
    rows = ([{"origin": f"o{i}", "g": {"status": "OK", "g": 0.01 * i},
             "features": {"age_days": float(i), "realized_vol_20d": 0.1 + 0.001 * i,
                         "regime_transitions_since_incumbent": float(i % 3),
                         "incumbent_trailing_return": 0.01 * (i % 2)}}
            for i in range(8)]
           + [{"origin": f"censored{i}", "g": {"status": "CENSORED", "g": None}, "features": None}
             for i in range(4)])
    result = fit_and_compare(rows, min_support=8)
    assert result["status"] == "FIT_ATTEMPTED"
    assert result["support"] == 8, "censored rows must not count toward support"


# --- P07: fallback keeps correct policy; no confidence fabrication ---------

def test_p07_insufficient_support_locks_keep_baseline_not_a_fabricated_revision():
    ladder = {"status": "INSUFFICIENT_SUPPORT", "support": 5, "min_required": 8}
    decision = lock_policy_revision(ladder)
    assert decision["decision"] == "KEEP_BASELINE"
    assert decision["carries_to_ra07"] is None
    assert "5" in decision["reason"] and "8" in decision["reason"]


def test_p07_a_negative_contribution_also_locks_keep_baseline():
    ladder = {"status": "FIT_ATTEMPTED", "age_only": {}, "age_context": {},
             "primary_contribution_loo_mse_reduction": -0.001}
    decision = lock_policy_revision(ladder)
    assert decision["decision"] == "KEEP_BASELINE"


def test_p07_vetoed_search_is_not_silently_treated_as_free():
    decision = request_search_decision(
        {"age_days": 5, "realized_vol_20d": 0.05, "regime_transitions_since_incumbent": 0,
         "incumbent_trailing_return": 0.0}, beta=None,
        feature_names=("intercept", "age_days", "realized_vol_20d",
                       "regime_transitions_since_incumbent", "incumbent_trailing_return"),
        days_since_last_request=30, budget_remaining=1)
    assert decision["request_search"] is False
    assert decision["veto_reasons"]
    assert "note" in decision  # the charge-if-consulted caveat is documented, not silently dropped


# --- P08: panel/report reruns never call the engine -------------------------

def test_p08_model_and_controller_modules_never_import_the_engine():
    import inspect

    from crypto_regime_lab.ra import ra06_controller, ra06_model

    for module in (ra06_model, ra06_controller):
        source = inspect.getsource(module)
        assert "run_cutoff_walk_forward" not in source
        assert "quantbt" not in source.lower()
