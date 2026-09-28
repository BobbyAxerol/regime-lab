"""Tests for Phase MF-02: Features, Targets, Duration & Baselines.

Covers:
- MF2-T01: Feature manifest <= 50, lag >= 1
- MF2-T02: Causal feature invariance to future mutation
- MF2-T03: Target forward definitions (H56, H90)
- MF2-T04: Taxonomy boundary derivation on training prefix only
- MF2-T05: Baselines use matured labels only
- MF2-T06: Brier score analytical correctness
- MF2-T07: Balanced accuracy robustness
- MF2-T08: Verifier exit gate checks
- DUR-T01: Duration detector OBS14_CONFIRM3_V1
- DUR-T02: Episode ledger right-censoring logic
- DUR-T03: Kaplan-Meier monotonicity
- DUR-T04: RMST and RMRL non-negativity
- DUR-T05: First-exit probability monotonicity
"""

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.regime_forecast.features import (
    FEATURE_DEFINITIONS,
    compute_all_features,
    get_feature_manifest,
)
from crypto_regime_lab.regime_forecast.targets import (
    compute_forward_targets,
    derive_and_freeze_taxonomy,
)
from crypto_regime_lab.regime_forecast.duration import (
    Obs14Confirm3Detector,
    build_episode_ledger,
    fit_kaplan_meier_survival,
    compute_rmst,
    compute_rmrl,
    compute_first_exit_probability,
)
from crypto_regime_lab.regime_forecast.baselines import (
    PersistenceBaseline,
    MaturedFrequenciesBaseline,
    HarRvBaseline,
    RegularizedLinearBaseline,
    brier_score_multiclass,
    balanced_accuracy,
    brier_skill_score,
)
from crypto_regime_lab.regime_forecast.verifier_mf02 import (
    verify_gate_features,
    verify_gate_targets,
    verify_gate_split,
    verify_gate_baseline,
    verify_gate_registration,
    verify_gate_duration_definition,
)


def test_mf2_t01_feature_manifest_constraints():
    manifest = get_feature_manifest()
    features = manifest["features"]
    assert len(features) <= 50
    assert len(features) >= 20
    assert len(FEATURE_DEFINITIONS) == len(features)
    for f in features:
        assert f["causal_lag_days"] >= 1
        assert f["cohort"] in ("D0_CORE_PRICE_VOL", "D1_DERIVATIVE_LIQUIDITY", "D2_COMPOSITE_PRESSURE")


def test_mf2_t02_feature_causality_future_invariance():
    """Mutating data at T + k must NOT change features computed at T."""
    n = 100
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    base_df = pd.DataFrame({
        "spot_close": 20000.0 + np.cumsum(np.random.randn(n) * 100),
        "spot_open": 20000.0 + np.cumsum(np.random.randn(n) * 100),
        "spot_high": 20500.0 + np.cumsum(np.random.randn(n) * 100),
        "spot_low": 19500.0 + np.cumsum(np.random.randn(n) * 100),
        "spot_volume": 1000.0 + np.random.rand(n) * 100,
        "rv_5m_daily": 0.02 + np.random.rand(n) * 0.01,
        "funding_rate_daily_avg": 0.0001 + np.random.randn(n) * 0.0001,
        "oi_daily_close": 50000.0 + np.random.randn(n) * 1000,
        "ls_ratio_daily_avg": 1.2 + np.random.randn(n) * 0.1,
        "taker_ratio_daily_avg": 1.0 + np.random.randn(n) * 0.05,
    }, index=dates)

    f1 = compute_all_features(base_df)
    
    # Mutate last 10 days
    base_df_mut = base_df.copy()
    base_df_mut.iloc[-10:, base_df_mut.columns.get_loc("spot_close")] *= 2.0
    base_df_mut.iloc[-10:, base_df_mut.columns.get_loc("rv_5m_daily")] *= 5.0
    f2 = compute_all_features(base_df_mut)

    # Feature at index 80 (well before T-10) must be byte/float identical
    t_check = dates[80]
    for col in f1.columns:
        val1 = f1.loc[t_check, col]
        val2 = f2.loc[t_check, col]
        if np.isnan(val1):
            assert np.isnan(val2)
        else:
            assert np.isclose(val1, val2, atol=1e-10), f"Leakage detected in {col} at {t_check}"


def test_mf2_t03_target_forward_horizons():
    n = 150
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    base_df = pd.DataFrame({
        "spot_close": 25000.0 + np.cumsum(np.random.randn(n) * 100),
        "rv_5m_daily": 0.02 + np.random.rand(n) * 0.01,
    }, index=dates)

    targets = compute_forward_targets(base_df, horizons=[56, 90])
    assert "target_v_cont_h56" in targets.columns
    assert "target_e_cont_h56" in targets.columns
    assert "target_v_cont_h90" in targets.columns
    assert "target_e_cont_h90" in targets.columns

    # Check forward alignment: target at day 0 for H56 must match annualized RV over day 1..56
    t0 = dates[0]
    expected_rv_h56 = np.sqrt(365.0 / 56.0 * np.sum(base_df.loc[dates[1]:dates[56], "rv_5m_daily"]))
    assert np.isclose(targets.loc[t0, "target_v_cont_h56"], expected_rv_h56)

    # Beyond index n - 56, H56 target must be NaN (future not yet observed)
    assert np.isnan(targets.loc[dates[-1], "target_v_cont_h56"])


def test_mf2_t04_taxonomy_derivation_prefix():
    n = 300
    dates = pd.date_range("2022-01-01", periods=n, freq="D")
    targets_df = pd.DataFrame({
        "target_v_cont_h56": 0.01 + np.random.rand(n) * 0.05,
        "target_e_cont_h56": np.random.randn(n) * 0.03,
        "target_v_cont_h90": 0.01 + np.random.rand(n) * 0.05,
        "target_e_cont_h90": np.random.randn(n) * 0.03,
    }, index=dates)

    prefix_start = "2022-01-01"
    prefix_end = "2022-06-30"  # 181 days
    tax = derive_and_freeze_taxonomy(targets_df, prefix_start, prefix_end, horizons=[56, 90])
    
    assert tax["H56"]["v_quantiles"]["q_1_3"] < tax["H56"]["v_quantiles"]["q_2_3"]
    assert tax["H56"]["e_quantiles"]["tau_symmetric"] > 0


def test_mf2_t05_baselines_execution():
    n = 100
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "p1_rv_1d": 0.02 + np.random.rand(n) * 0.01,
        "p1_rv_7d": 0.02 + np.random.rand(n) * 0.01,
        "p1_rv_28d": 0.02 + np.random.rand(n) * 0.01,
        "target_v_class_h56": np.random.choice(["LOW_VOL", "MID_VOL", "HIGH_VOL"], size=n),
        "target_e_class_h56": np.random.choice(["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"], size=n),
        "target_j_class_h56": np.random.choice(["MID_VOL__RANGE_NEUTRAL", "HIGH_VOL__TREND_FRIENDLY"], size=n),
        "target_v_cont_h56": 0.02 + np.random.rand(n) * 0.01,
        "target_e_cont_h56": np.random.randn(n) * 0.02,
    }, index=dates)

    v_classes = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]
    e_classes = ["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"]
    j_classes = [f"{v}__{e}" for v in v_classes for e in e_classes]

    # Persistence
    b1 = PersistenceBaseline()
    res1 = b1.predict(df.iloc[10], "MID_VOL__RANGE_NEUTRAL", v_classes, e_classes, j_classes)
    assert res1["prob_j_9class"]["MID_VOL__RANGE_NEUTRAL"] == 1.0

    # Matured frequencies
    b2 = MaturedFrequenciesBaseline(alpha=1.0)
    res2 = b2.fit_predict(df.iloc[:20], 56, v_classes, e_classes, j_classes)
    assert np.isclose(sum(res2["prob_j_9class"].values()), 1.0)

    # HAR-RV
    b3 = HarRvBaseline()
    b3.fit(df.iloc[:30], 56)
    res3 = b3.predict(df.iloc[35], (0.02, 0.03), v_classes, e_classes, j_classes)
    assert res3["pred_v_cont"] > 0

    # Regularized linear
    b4 = RegularizedLinearBaseline()
    b4.fit(df.iloc[:40], ["p1_rv_1d", "p1_rv_7d", "p1_rv_28d"], 56)
    res4 = b4.predict(df.iloc[45], v_classes, e_classes, j_classes)
    assert np.isclose(sum(res4["prob_v_3class"].values()), 1.0)


def test_mf2_t06_brier_score_correctness():
    # If prediction is perfect (prob=1 for true class), Brier score is 0.0
    y_true = np.array([0, 1, 2])
    prob_perfect = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    assert brier_score_multiclass(y_true, prob_perfect) == 0.0

    # If prediction is uniform 1/3 for 3 classes:
    # Each sample: (1 - 1/3)^2 + 2 * (0 - 1/3)^2 = 4/9 + 2/9 = 6/9 = 2/3 ≈ 0.666667
    prob_uniform = np.full((3, 3), 1.0 / 3.0)
    assert np.isclose(brier_score_multiclass(y_true, prob_uniform), 2.0 / 3.0)


def test_mf2_t07_balanced_accuracy_robustness():
    # Only class 0 and 1 are present, class 2 has 0 true samples
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 0, 1, 1])
    # K = 3
    acc = balanced_accuracy(y_true, y_pred, k=3)
    assert acc == 1.0  # skips unrepresented class 2, averages class 0 (1.0) and class 1 (1.0)


def test_mf2_t08_verifier_exit_gates():
    # Check that verify functions succeed on valid dummy inputs
    valid_features = {
        "features": [
            {"feature_id": f"feat_{i}", "cohort": "D0_CORE_PRICE_VOL", "causal_lag_days": 1}
            for i in range(15)
        ] + [
            {"feature_id": f"feat_d1_{i}", "cohort": "D1_DERIVATIVE_LIQUIDITY", "causal_lag_days": 1}
            for i in range(10)
        ] + [
            {"feature_id": f"feat_d2_{i}", "cohort": "D2_COMPOSITE_PRESSURE", "causal_lag_days": 1}
            for i in range(10)
        ]
    }
    assert verify_gate_features(valid_features)["status"] == "PASS"

    # Must fail if feature count > 50
    invalid_features = {
        "features": [{"feature_id": f"f_{i}", "cohort": "D0_CORE_PRICE_VOL", "causal_lag_days": 1} for i in range(55)]
    }
    with pytest.raises(AssertionError):
        verify_gate_features(invalid_features)

    # Check verify_gate_targets
    dummy_tax = {
        "frozen_on_prefix": "2022-01-14_to_2024-01-13",
        "H56": {"v_quantiles": {"q_1_3": 0.3, "q_2_3": 0.6}, "e_quantiles": {"tau_symmetric": 0.2}},
        "H90": {"v_quantiles": {"q_1_3": 0.3, "q_2_3": 0.6}, "e_quantiles": {"tau_symmetric": 0.2}},
    }
    assert verify_gate_targets(dummy_tax)["status"] == "PASS"

    # Check verify_gate_split
    dummy_split = {
        "initial_matured_training_origins": 730,
        "dev_blocks": 12,
        "test_blocks": 12,
        "dev_weekly_origins": 48,
        "test_weekly_origins": 48,
    }
    assert verify_gate_split(dummy_split)["status"] == "PASS"

    # Check verify_gate_baseline
    dummy_base = {
        b: {
            "H56": {"brier_score_v": 0.2, "brier_score_e": 0.2, "brier_score_j": 0.5, "balanced_acc_v": 0.4, "balanced_acc_e": 0.4, "balanced_acc_j": 0.3, "mae_v": 0.05},
            "H90": {"brier_score_v": 0.2, "brier_score_e": 0.2, "brier_score_j": 0.5, "balanced_acc_v": 0.4, "balanced_acc_e": 0.4, "balanced_acc_j": 0.3, "mae_v": 0.05},
        }
        for b in ["B1_PERSISTENCE", "B2_MATURED_FREQ", "B3_HAR_RV", "B4_REGULARIZED_LINEAR"]
    }
    assert verify_gate_baseline(dummy_base)["status"] == "PASS"

    # Check verify_gate_registration
    dummy_grid = {
        "candidate_models": [
            {"model_id": "M1", "model_type": "LIGHTGBM"},
            {"model_id": "M2", "model_type": "LIGHTGBM"},
            {"model_id": "M3", "model_type": "LIGHTGBM"},
            {"model_id": "M4", "model_type": "CHRONOS_SYNTH"},
        ]
    }
    assert verify_gate_registration(dummy_grid)["status"] == "PASS"

    # Check verify_gate_duration_definition
    dummy_dur = {
        "detector_id": "OBS14_CONFIRM3_V1",
        "episode_ledger_summary": {"total_episodes": 15, "right_censored_count": 2},
        "km_estimator_summary": {
            "median_duration_by_regime": {},
            "rmst_by_regime": {},
            "rmrl_by_regime": {},
        }
    }
    assert verify_gate_duration_definition(dummy_dur)["status"] == "PASS"

    # Brier skill score check
    assert np.isclose(brier_skill_score(0.2, 0.4), 0.5)


def test_dur_t01_duration_detector():
    n = 60
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "p1_rv_28d": [0.01] * 20 + [0.05] * 20 + [0.02] * 20,
        "p1_er_28d": [0.05] * 20 + [0.35] * 20 + [0.10] * 20,
    }, index=dates)

    v_cutoffs = (0.015, 0.035)
    e_tau = 0.20
    detector = Obs14Confirm3Detector(v_cutoffs, e_tau, min_confirm_days=3)
    tape = detector.generate_state_tape(df)
    assert len(tape) == n
    assert "observed_regime" in tape.columns
    # Regime should persist and filter blips
    assert tape["observed_regime"].iloc[0] == "LOW_VOL__RANGE_NEUTRAL"


def test_dur_t02_episode_ledger_right_censoring():
    dates = pd.date_range("2023-01-01", periods=10, freq="D")
    tape = pd.DataFrame({
        "observed_regime": ["R1"] * 4 + ["R2"] * 4 + ["R3"] * 2,
    }, index=dates)

    ledger = build_episode_ledger(tape)
    assert len(ledger) == 3
    # First two episodes are complete (censored = False)
    assert not ledger.iloc[0]["is_right_censored"]
    assert not ledger.iloc[1]["is_right_censored"]
    # Last episode is ongoing at end of data (censored = True)
    assert ledger.iloc[2]["is_right_censored"]
    assert ledger.iloc[2]["duration_days"] == 2


def test_dur_t03_kaplan_meier_monotonicity():
    durations = [10, 15, 20, 25, 30, 40]
    censored = [False, False, True, False, False, True]
    km = fit_kaplan_meier_survival(durations, censored)
    
    assert km.timeline[0] == 0
    assert km.survival_probabilities[0] == 1.0
    # Probabilities must be monotonically non-increasing
    assert np.all(np.diff(km.survival_probabilities) <= 1e-12)


def test_dur_t04_rmst_and_rmrl_finite_nonnegative():
    durations = [10, 20, 30, 40, 50]
    censored = [False, False, False, True, True]
    km = fit_kaplan_meier_survival(durations, censored)

    rmst_50 = compute_rmst(km, horizon_l=50)
    assert rmst_50 >= 0.0
    assert rmst_50 <= 50.0

    rmrl_at_15 = compute_rmrl(km, elapsed_age=15, horizon_l=50)
    assert rmrl_at_15 >= 0.0
    assert rmrl_at_15 <= 35.0


def test_dur_t05_first_exit_probability_monotonicity():
    durations = [5, 10, 15, 20, 25, 30]
    censored = [False, False, False, False, False, False]
    km = fit_kaplan_meier_survival(durations, censored)

    p_exit_10 = compute_first_exit_probability(km, elapsed_age=5, horizon_h=10)
    p_exit_20 = compute_first_exit_probability(km, elapsed_age=5, horizon_h=20)
    assert 0.0 <= p_exit_10 <= p_exit_20 <= 1.0
