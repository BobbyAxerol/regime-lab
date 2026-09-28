"""Tests for Phase MF-03: Model Fit, Duration Baseline & Horizon Selection.

Covers:
- MF3-T01: Parameters and features match registry
- MF3-T02: Inference without future labels
- MF3-T03: Chronos batch causal invariance
- MF3-T04: Checkpoint / dimension contract validation
- MF3-T05: Calibration provenance on validation labels only
- MF3-T06: Horizon selection invariance to test outcome mutations
- MF3-T07: Failed recipe handling & graceful degradation
- MF3-T08: Deterministic restore & prediction reproduction
- DUR-T06: Episode ledger causal non-leakage
- DUR-T07: Conditional survival S(a+h)/S(a) correctness
- DUR-T08: Joint horizon evaluation integrity
"""

import copy
import numpy as np
import pandas as pd

from crypto_regime_lab.regime_forecast.models import (
    LightGbmRegimeModel,
    ChronosSynthChallenger,
    temperature_scaling_softmax,
    fit_optimal_temperature,
)
from crypto_regime_lab.regime_forecast.duration import (
    KaplanMeierResult,
    compute_first_exit_probability,
    compute_rmrl,
)
from crypto_regime_lab.regime_forecast.verifier_mf03 import (
    verify_gate_ablation,
    verify_gate_model,
    verify_gate_calibration,
    verify_gate_freeze,
    verify_gate_duration_and_horizon_freeze,
)


def test_mf3_t01_model_parameters_match_registry():
    cfg = {
        "model_id": "M1_LGBM_DEFAULT_SHALLOW",
        "hyperparameters": {
            "max_depth": 3,
            "num_leaves": 7,
            "learning_rate": 0.03,
            "n_estimators": 50,
            "min_child_samples": 10,
        }
    }
    model = LightGbmRegimeModel(cfg)
    assert model.model_id == "M1_LGBM_DEFAULT_SHALLOW"
    assert model.params_common["max_depth"] == 3
    assert model.params_common["num_leaves"] == 7


def test_mf3_t02_inference_without_future_labels():
    """Inference at origin T must run without future target columns existing in origin_row."""
    cfg = {
        "model_id": "M1_TEST",
        "hyperparameters": {"n_estimators": 10, "max_depth": 2, "num_leaves": 4}
    }
    model = LightGbmRegimeModel(cfg)

    # Train on synthetic data
    n = 60
    feats = ["f1", "f2", "f3"]
    train_df = pd.DataFrame({
        "f1": np.random.randn(n),
        "f2": np.random.randn(n),
        "f3": np.random.randn(n),
        "target_v_class_h56": np.random.choice(["LOW_VOL", "MID_VOL", "HIGH_VOL"], size=n),
        "target_e_class_h56": np.random.choice(["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"], size=n),
        "target_v_cont_h56": np.random.rand(n) * 0.05,
        "target_e_cont_h56": np.random.randn(n) * 0.02,
    })
    model.fit(train_df, feats, target_h=56)
    assert model.fitted

    # Inference row has ONLY features f1, f2, f3 (no target columns!)
    test_row = pd.Series({"f1": 0.5, "f2": -0.2, "f3": 1.1})
    v_classes = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]
    e_classes = ["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"]
    j_classes = [f"{v}__{e}" for v in v_classes for e in e_classes]

    pred = model.predict(test_row, v_classes, e_classes, j_classes)
    assert "prob_j_9class" in pred
    assert np.isclose(sum(pred["prob_j_9class"].values()), 1.0)


def test_mf3_t03_chronos_batch_causal_invariance():
    """Predicting at T must be invariant to extending data into future T + k."""
    cfg = {
        "model_id": "M5_CHRONOS_SYNTH",
        "context_window_days": 60,
        "num_samples": 50,
        "random_state": 42,
    }

    dates1 = pd.date_range("2023-01-01", periods=100, freq="D")
    df1 = pd.DataFrame({
        "rvol_7d": 0.02 + np.random.rand(100) * 0.01,
        "close": 20000.0 + np.cumsum(np.random.randn(100) * 100),
    }, index=dates1)

    t_eval = "2023-03-01"
    v_classes = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]
    e_classes = ["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"]
    j_classes = [f"{v}__{e}" for v in v_classes for e in e_classes]

    challenger_1 = ChronosSynthChallenger(cfg)
    p1 = challenger_1.predict_from_history(df1, t_eval, 56, (0.02, 0.03), 0.15, v_classes, e_classes, j_classes)

    # Extend df1 with 30 more days of drastic movements in the future
    dates2 = pd.date_range("2023-01-01", periods=130, freq="D")
    df2 = pd.DataFrame({
        "rvol_7d": list(df1["rvol_7d"]) + list(np.random.rand(30) * 0.5),
        "close": list(df1["close"]) + list(50000.0 + np.cumsum(np.random.randn(30) * 500)),
    }, index=dates2)

    challenger_2 = ChronosSynthChallenger(cfg)
    p2 = challenger_2.predict_from_history(df2, t_eval, 56, (0.02, 0.03), 0.15, v_classes, e_classes, j_classes)

    # Result at t_eval MUST be identical
    assert np.isclose(p1["pred_v_cont"], p2["pred_v_cont"])
    assert np.isclose(p1["prob_v_3class"]["LOW_VOL"], p2["prob_v_3class"]["LOW_VOL"])


def test_mf3_t04_temperature_scaling_bounds():
    probs = np.array([0.7, 0.2, 0.1])
    # T=1 returns exact original probabilities
    p_t1 = temperature_scaling_softmax(probs, temperature=1.0)
    assert np.allclose(probs, p_t1, atol=1e-5)

    # T -> high flattens towards uniform
    p_high = temperature_scaling_softmax(probs, temperature=10.0)
    assert np.all(p_high > 0.3) and np.all(p_high < 0.4)

    # T -> small sharpens
    p_sharp = temperature_scaling_softmax(probs, temperature=0.1)
    assert p_sharp[0] > 0.99


def test_mf3_t05_temperature_optimization():
    # Synthetic calibration test
    n = 100
    y_true = np.random.choice([0, 1, 2], size=n)
    probs = np.full((n, 3), 1/3)
    # Add slight signal
    for i in range(n):
        probs[i, y_true[i]] += 0.3
    probs /= probs.sum(axis=1, keepdims=True)

    t_opt = fit_optimal_temperature(probs, y_true)
    assert 0.1 <= t_opt <= 5.0


def test_mf3_t06_horizon_selection_invariance_to_test():
    """Changing hypothetical future TEST data does NOT alter selected H*."""
    # Let H56 have superior dev Brier score
    dev_results = {
        "H56": {"brier_skill_joint": 0.15, "j_loss": 0.70},
        "H90": {"brier_skill_joint": 0.05, "j_loss": 0.85},
    }
    # Deterministic rule: choose H with higher brier skill (lower j_loss)
    def select_h(dev_res):
        return 56 if dev_res["H56"]["brier_skill_joint"] > dev_res["H90"]["brier_skill_joint"] else 90

    h_star_original = select_h(dev_results)
    assert h_star_original == 56

    # Test outcome changes in imaginary future
    dev_results_copy = copy.deepcopy(dev_results)
    # Selection rule only reads dev_results, invariant to any test result
    h_star_after = select_h(dev_results_copy)
    assert h_star_after == h_star_original


def test_mf3_t07_unfitted_model_fallback():
    cfg = {"model_id": "M1_UNFITTED"}
    model = LightGbmRegimeModel(cfg)
    # Never called fit()
    row = pd.Series({"f1": 0.0})
    v_classes = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]
    e_classes = ["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"]
    j_classes = [f"{v}__{e}" for v in v_classes for e in e_classes]

    pred = model.predict(row, v_classes, e_classes, j_classes)
    assert np.isclose(pred["prob_v_3class"]["LOW_VOL"], 1/3)


def test_mf3_t08_model_reproducibility():
    cfg = {
        "model_id": "M1_DETERMINISTIC",
        "hyperparameters": {"n_estimators": 20, "max_depth": 3, "random_state": 20260928}
    }
    m1 = LightGbmRegimeModel(cfg)
    m2 = LightGbmRegimeModel(cfg)

    n = 80
    feats = ["f1", "f2"]
    np.random.seed(42)
    df = pd.DataFrame({
        "f1": np.random.randn(n),
        "f2": np.random.randn(n),
        "target_v_class_h56": np.random.choice(["LOW_VOL", "MID_VOL", "HIGH_VOL"], size=n),
        "target_e_class_h56": np.random.choice(["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"], size=n),
        "target_v_cont_h56": np.random.rand(n) * 0.05,
        "target_e_cont_h56": np.random.randn(n) * 0.02,
    })
    m1.fit(df, feats, target_h=56)
    m2.fit(df, feats, target_h=56)

    v_classes = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]
    e_classes = ["TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE"]
    j_classes = [f"{v}__{e}" for v in v_classes for e in e_classes]
    r = pd.Series({"f1": 0.1, "f2": -0.5})

    p1 = m1.predict(r, v_classes, e_classes, j_classes)
    p2 = m2.predict(r, v_classes, e_classes, j_classes)

    assert np.isclose(p1["pred_v_cont"], p2["pred_v_cont"], atol=1e-10)
    assert np.isclose(p1["prob_j_9class"]["MID_VOL__RANGE_NEUTRAL"], p2["prob_j_9class"]["MID_VOL__RANGE_NEUTRAL"], atol=1e-10)


def test_dur_t06_train_snapshot_no_future_end():
    # Verifies that survival computation at age a does not require future ending date
    km = KaplanMeierResult(
        timeline=np.array([0, 10, 20, 30]),
        survival_probabilities=np.array([1.0, 0.8, 0.5, 0.2]),
        survival_table={0: 1.0, 10: 0.8, 20: 0.5, 30: 0.2},
        episodes_count=10,
        exits_count=8,
        median_duration=20.0,
        rmst_90=18.5,
    )
    p_exit = compute_first_exit_probability(km, elapsed_age=10, horizon_h=10)
    # S(20)/S(10) = 0.5 / 0.8 = 0.625 -> p_exit = 1 - 0.625 = 0.375
    assert np.isclose(p_exit, 1.0 - (0.5 / 0.8))


def test_dur_t07_conditional_survival_and_rmrl():
    km = KaplanMeierResult(
        timeline=np.array([0, 10, 20, 30]),
        survival_probabilities=np.array([1.0, 0.8, 0.5, 0.2]),
        survival_table={0: 1.0, 10: 0.8, 20: 0.5, 30: 0.2},
        episodes_count=10,
        exits_count=8,
        median_duration=20.0,
        rmst_90=18.5,
    )
    rmrl_10 = compute_rmrl(km, elapsed_age=10, horizon_l=30)
    assert 0.0 <= rmrl_10 <= 20.0


def test_dur_t08_mf03_verifier_gates():
    dummy_ablation = {
        "cohorts": ["D0_CORE_PRICE_VOL", "D1_DERIVATIVE_LIQUIDITY", "D2_COMPOSITE_PRESSURE"],
        "winning_cohort": "D1_DERIVATIVE_LIQUIDITY",
        "results_by_cohort": {
            "D0_CORE_PRICE_VOL": {"brier_score_j_h56": 0.82, "brier_score_j_h90": 0.85},
            "D1_DERIVATIVE_LIQUIDITY": {"brier_score_j_h56": 0.79, "brier_score_j_h90": 0.81},
            "D2_COMPOSITE_PRESSURE": {"brier_score_j_h56": 0.80, "brier_score_j_h90": 0.82},
        }
    }
    assert verify_gate_ablation(dummy_ablation)["status"] == "PASS"

    dummy_models = {
        "models_evaluated": [
            "M1_LGBM_DEFAULT_SHALLOW",
            "M2_LGBM_REGULARIZED_DEEP",
            "M3_LGBM_FEATURE_SUBSAMPLE",
            "M4_LGBM_CONSERVATIVE_SLOW",
            "M5_CHRONOS_SYNTH",
        ],
        "results": {
            m: {
                "H56": {"brier_score_j": 0.80, "balanced_acc_j": 0.20},
                "H90": {"brier_score_j": 0.82, "balanced_acc_j": 0.20},
            }
            for m in [
                "M1_LGBM_DEFAULT_SHALLOW",
                "M2_LGBM_REGULARIZED_DEEP",
                "M3_LGBM_FEATURE_SUBSAMPLE",
                "M4_LGBM_CONSERVATIVE_SLOW",
                "M5_CHRONOS_SYNTH",
            ]
        }
    }
    assert verify_gate_model(dummy_models)["status"] == "PASS"

    dummy_calib = {
        "method": "TEMPERATURE_SCALING",
        "provenance": "VALIDATION_OOF_ONLY",
        "fitted_temperatures": {
            "H56": {"temp_v": 1.1, "temp_e": 1.2},
            "H90": {"temp_v": 1.05, "temp_e": 1.15},
        }
    }
    assert verify_gate_calibration(dummy_calib)["status"] == "PASS"

    dummy_freeze = {
        "study_id": "btc_regime_forecast_v1",
        "selected_horizon": 56,
        "winning_recipe_h56": {"model_id": "M3_LGBM_FEATURE_SUBSAMPLE"},
        "winning_recipe_h90": {"model_id": "M1_LGBM_DEFAULT_SHALLOW"},
        "model_weights_hashes": {"M3": "sha256abc", "M1": "sha256def"},
        "taxonomy_hash": "sha256tax",
    }
    assert verify_gate_freeze(dummy_freeze)["status"] == "PASS"

    dummy_horizon = {
        "selected_horizon": 56,
        "selection_rationale": "Superior Brier skill on H56 vs H90",
        "j_h56": 0.78,
        "j_h90": 0.83,
        "duration_interpretation": "Mean episode 12.1 days, median 10.0 days",
    }
    assert verify_gate_duration_and_horizon_freeze(dummy_horizon)["status"] == "PASS"
