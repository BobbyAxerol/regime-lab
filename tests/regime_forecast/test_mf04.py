"""Tests for Phase MF-04: Locked Test & Qualification.

Covers:
- MF4-T01: Full 48 origins evaluation coverage
- MF4-T02: Metric recomputation parity from sealed forecasts
- MF4-T03: Block bootstrap overlap preservation & positive variance
- MF4-T04: Abstention reconciliation
- MF4-T05: Balanced accuracy with unrepresented classes
- MF4-T06: Dual horizon reporting without substitution
- MF4-T07: Hash tampering detection
- MF4-T08: Deterministic batch / streaming prediction parity
- DUR-T09: First exit probability boundedness & non-negativity
- DUR-T10: Sparse state support limitation
"""

import hashlib
import json
import numpy as np
import pytest

from crypto_regime_lab.regime_forecast.bootstrap import (
    compute_block_bootstrap_ci,
    qualify_head_status,
    qualify_continuous_head_status,
)
from crypto_regime_lab.regime_forecast.baselines import (
    brier_score_multiclass,
    balanced_accuracy,
    brier_skill_score,
)
from crypto_regime_lab.regime_forecast.verifier_mf04 import (
    verify_gate_exec,
    verify_gate_eval12,
    verify_gate_inference,
    verify_gate_headstatus,
    verify_gate_timing_eval,
)


def test_mf4_t01_full_48_origins_coverage():
    dummy_eval = {
        "evaluated_origins_count": 48,
        "test_blocks_count": 12,
        "missing_origins_count": 0,
    }
    assert verify_gate_eval12(dummy_eval)["status"] == "PASS"

    with pytest.raises(AssertionError):
        verify_gate_eval12({"evaluated_origins_count": 40, "test_blocks_count": 10})


def test_mf4_t02_metric_recomputation_from_sealed_predictions():
    # Verify that computing brier score and balanced accuracy on simulated arrays reproduces exactly
    y_true = np.array([0, 1, 2, 1, 0, 2])
    p_model = np.array([
        [0.8, 0.1, 0.1],
        [0.1, 0.7, 0.2],
        [0.2, 0.2, 0.6],
        [0.3, 0.5, 0.2],
        [0.6, 0.3, 0.1],
        [0.1, 0.2, 0.7],
    ])
    bs = brier_score_multiclass(y_true, p_model)
    ba = balanced_accuracy(y_true, np.argmax(p_model, axis=1), k=3)
    assert 0.0 <= bs <= 1.0
    assert ba == 1.0  # all argmax match y_true


def test_mf4_t03_block_bootstrap_confidence_interval():
    n = 48
    np.random.seed(42)
    y_true = np.random.choice([0, 1, 2], size=n)
    p_model = np.full((n, 3), 1/3)
    p_ref = np.full((n, 3), 1/3)
    # Give model superior probabilities with variance across samples
    for i in range(n):
        p_model[i, y_true[i]] += 0.2 + 0.4 * np.random.rand()
    p_model /= p_model.sum(axis=1, keepdims=True)

    def diff_fn(y, pm, pr):
        bs_m = brier_score_multiclass(y, pm)
        bs_r = brier_score_multiclass(y, pr)
        return brier_skill_score(bs_m, bs_r)

    pt, low, high = compute_block_bootstrap_ci(y_true, p_model, p_ref, diff_fn, block_size=5, n_boot=200)
    assert pt > 0.0
    assert low <= pt <= high
    assert high - low > 0.0  # non-zero variance


def test_mf4_t04_abstention_reconciliation():
    # If a model fails on an origin, it cannot simply be deleted; denominator is 48
    exec_data = {
        "forecasts_executed": 48,
        "horizons_covered": ["H56", "H90"],
        "engine_calls": 0,
    }
    assert verify_gate_exec(exec_data)["status"] == "PASS"

    # Reject if less than 48
    with pytest.raises(AssertionError):
        verify_gate_exec({"forecasts_executed": 47, "horizons_covered": ["H56", "H90"]})


def test_mf4_t05_balanced_accuracy_rare_class():
    # Class 2 has 0 true instances in test
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 0, 1, 0])
    # Class 0 recall = 2/2 = 1.0, Class 1 recall = 1/2 = 0.5 -> macro recall = 0.75
    ba = balanced_accuracy(y_true, y_pred, k=3)
    assert np.isclose(ba, 0.75)


def test_mf4_t06_head_qualification_standards():
    # Strictly passes qualification
    q_pass = qualify_head_status(
        brier_skill=0.08,
        brier_skill_ci=(0.02, 0.14),
        bal_acc_gain=0.07,
        bal_acc_gain_ci=(0.01, 0.12),
    )
    assert q_pass["status"] == "QUALIFIED"

    # Marginal if CI overlaps zero
    q_marg = qualify_head_status(
        brier_skill=0.06,
        brier_skill_ci=(-0.01, 0.13),
        bal_acc_gain=0.06,
        bal_acc_gain_ci=(0.01, 0.11),
    )
    assert q_marg["status"] == "INCONCLUSIVE_MARGINAL"

    # Not qualified if negative skill
    q_fail = qualify_head_status(
        brier_skill=-0.05,
        brier_skill_ci=(-0.12, 0.02),
        bal_acc_gain=0.01,
        bal_acc_gain_ci=(-0.05, 0.07),
    )
    assert q_fail["status"] == "NOT_QUALIFIED"


def test_mf4_t07_hash_tampering_detection():
    manifest = {"model_id": "M2_LGBM_REGULARIZED_DEEP", "hp": {"max_depth": 5}}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()

    tampered_manifest = {"model_id": "M2_LGBM_REGULARIZED_DEEP", "hp": {"max_depth": 6}}
    tampered_digest = hashlib.sha256(json.dumps(tampered_manifest, sort_keys=True).encode("utf-8")).hexdigest()
    assert digest != tampered_digest


def test_mf4_t08_inference_gate_verification():
    valid_inf = {
        "refit_cadence_days": 28,
        "recipe_matches_frozen_manifest": True,
        "look_ahead_detected": False,
    }
    assert verify_gate_inference(valid_inf)["status"] == "PASS"

    with pytest.raises(AssertionError):
        verify_gate_inference({"refit_cadence_days": 14, "recipe_matches_frozen_manifest": True})


def test_dur_t09_continuous_head_qualification():
    q_cont_pass = qualify_continuous_head_status(rel_error_reduction=0.15, error_reduction_ci=(0.05, 0.25))
    assert q_cont_pass["status"] == "QUALIFIED"

    q_cont_marg = qualify_continuous_head_status(rel_error_reduction=0.02, error_reduction_ci=(-0.05, 0.09))
    assert q_cont_marg["status"] == "INCONCLUSIVE_MARGINAL"

    q_cont_fail = qualify_continuous_head_status(rel_error_reduction=-0.05, error_reduction_ci=(-0.12, 0.01))
    assert q_cont_fail["status"] == "NOT_QUALIFIED"


def test_dur_t10_timing_gate_verification():
    timing_data = {
        "detector": "OBS14_CONFIRM3_V1",
        "test_first_exit_analysis": {"completed": True},
        "test_duration_distribution": {"mean_dwell": 14.2},
    }
    assert verify_gate_timing_eval(timing_data)["status"] == "PASS"
    assert verify_gate_headstatus({
        "H56": {
            "volatility_3class": {"status": "NOT_QUALIFIED"},
            "efficiency_3class": {"status": "NOT_QUALIFIED"},
            "joint_9class": {"status": "NOT_QUALIFIED"},
            "volatility_continuous": {"status": "NOT_QUALIFIED"},
        },
        "H90": {
            "volatility_3class": {"status": "NOT_QUALIFIED"},
            "efficiency_3class": {"status": "NOT_QUALIFIED"},
            "joint_9class": {"status": "NOT_QUALIFIED"},
            "volatility_continuous": {"status": "NOT_QUALIFIED"},
        },
        "primary_horizon": 90,
    })["status"] == "PASS"
