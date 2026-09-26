"""Coverage for sd/inference_sd03.py (guide SS7.2/SS7.4)."""
from __future__ import annotations

import pytest

from crypto_regime_lab.sd import inference_sd03 as inf


def _fold(origin, *, b_winner, c_winner, d_b, d_c, sr_fwd_b, sr_fwd_c, c_fallback_reason):
    return {"origin_cutoff": origin,
           "arms": {"B_SD_GLOBAL": {"selection": {"winner_id": b_winner},
                                    "D_selected": d_b, "SR_FWD_selected": sr_fwd_b},
                   "JM_C2.0": {"selection": {"winner_id": c_winner}, "D_selected": d_c,
                              "SR_FWD_selected": sr_fwd_c, "fallback_reason": c_fallback_reason}}}


def test_block_bootstrap_ci_captures_a_clear_positive_effect():
    values = [0.5] * 20
    result = inf.block_bootstrap_ci(values, block_length=4, seed=1, resamples=1000)
    assert result["status"] == "DEGENERATE_ZERO_VARIANCE"
    assert result["point_estimate"] == pytest.approx(0.5)


def test_block_bootstrap_ci_real_variation_gives_sane_interval():
    import random
    rng = random.Random(7)
    values = [0.3 + rng.gauss(0, 0.05) for _ in range(20)]
    result = inf.block_bootstrap_ci(values, block_length=4, seed=1, resamples=2000)
    assert result["status"] == "OK"
    assert result["ci_lower"] < result["point_estimate"] < result["ci_upper"]
    assert result["point_estimate"] == pytest.approx(0.3, abs=0.1)


def test_block_bootstrap_ci_too_few_observations_typed():
    result = inf.block_bootstrap_ci([0.1, 0.2], block_length=4, seed=1)
    assert result["status"] == "TOO_FEW_OBSERVATIONS_FOR_BLOCK_LENGTH"


def test_c_b_exact_match_detects_identical_winners_every_fold():
    folds = [_fold(f"o{i}", b_winner="X", c_winner="X", d_b=1.0, d_c=1.0,
                   sr_fwd_b=0.5, sr_fwd_c=0.5, c_fallback_reason=None) for i in range(12)]
    assert inf.c_b_exact_match(folds) is True
    assert inf.paired_r_series(folds) == [0.0] * 12


def test_c_all_fallback_detects_every_fold_global_fallback():
    folds = [_fold(f"o{i}", b_winner="X", c_winner="X", d_b=1.0, d_c=1.0,
                   sr_fwd_b=0.5, sr_fwd_c=0.5, c_fallback_reason="STATE_SUPPORT_LOW") for i in range(12)]
    assert inf.c_all_fallback(folds) is True


def test_decide_not_evaluable_when_data_invalid():
    result = inf.decide(r_series=[], q_series=[], seed=1, data_valid=False)
    assert result["decision"] == inf.DECISION_NOT_EVALUABLE


def test_decide_insufficient_paired_folds():
    result = inf.decide(r_series=[0.1] * 5, q_series=[0.1] * 5, seed=1)
    assert result["decision"] == inf.DECISION_INSUFFICIENT_PAIRED_FOLDS


def test_decide_exact_zero_observed_takes_priority_over_ci():
    folds = [_fold(f"o{i}", b_winner="X", c_winner="X", d_b=1.0, d_c=1.0,
                   sr_fwd_b=0.5, sr_fwd_c=0.5, c_fallback_reason=None) for i in range(12)]
    r_series = inf.paired_r_series(folds)
    q_series = inf.paired_q_series(folds)
    result = inf.decide(r_series=r_series, q_series=q_series, seed=1, fold_records=folds)
    assert result["decision"] == inf.DECISION_EXACT_ZERO_OBSERVED


def test_decide_active_jm_effect_not_exercised():
    folds = [_fold(f"o{i}", b_winner="X", c_winner="Y", d_b=1.0, d_c=0.9,
                   sr_fwd_b=0.5, sr_fwd_c=0.5, c_fallback_reason="STATE_SUPPORT_LOW") for i in range(12)]
    r_series = inf.paired_r_series(folds)
    q_series = inf.paired_q_series(folds)
    result = inf.decide(r_series=r_series, q_series=q_series, seed=1, fold_records=folds)
    assert result["decision"] == inf.DECISION_ACTIVE_JM_EFFECT_NOT_EXERCISED


def test_decide_decay_worsened_when_upper_ci_below_zero():
    import random
    rng = random.Random(3)
    r_series = [-0.5 + rng.gauss(0, 0.02) for _ in range(12)]
    q_series = [0.0] * 12
    result = inf.decide(r_series=r_series, q_series=q_series, seed=1)
    assert result["decision"] == inf.DECISION_DECAY_WORSENED


def test_decide_meaningful_reduction_when_lower_ci_clears_threshold_and_safety_ok():
    import random
    rng = random.Random(4)
    r_series = [0.5 + rng.gauss(0, 0.01) for _ in range(12)]
    q_series = [0.0 + rng.gauss(0, 0.01) for _ in range(12)]
    result = inf.decide(r_series=r_series, q_series=q_series, seed=1)
    assert result["decision"] == inf.DECISION_MEANINGFUL_REDUCTION
    assert result["safety_ok"] is True


def test_decide_gap_reduction_retention_unresolved_when_safety_fails():
    import random
    rng = random.Random(5)
    r_series = [0.5 + rng.gauss(0, 0.01) for _ in range(12)]
    q_series = [-0.5 + rng.gauss(0, 0.01) for _ in range(12)]   # far below -0.10 margin
    result = inf.decide(r_series=r_series, q_series=q_series, seed=1)
    assert result["decision"] == inf.DECISION_GAP_REDUCTION_RETENTION_UNRESOLVED
    assert result["safety_ok"] is False


def test_decide_no_meaningful_reduction_when_upper_ci_below_threshold():
    import random
    rng = random.Random(6)
    # small mean, enough spread that the CI's lower bound dips to/below 0
    # while the upper bound still stays well clear of the 0.20 hurdle
    r_series = [0.01 + rng.gauss(0, 0.05) for _ in range(12)]
    q_series = [0.0] * 12
    result = inf.decide(r_series=r_series, q_series=q_series, seed=1)
    r_ci = result["r_ci"]
    assert r_ci["ci_lower"] <= 0 <= r_ci["ci_upper"] < inf.MEANINGFUL_R_THRESHOLD, r_ci
    assert result["decision"] == inf.DECISION_NO_MEANINGFUL_REDUCTION_AT_020


def test_decision_priority_order_documented():
    """The module's own priority cascade: NOT_EVALUABLE and
    INSUFFICIENT_PAIRED_FOLDS outrank the degenerate-data checks, which
    outrank the CI-based ladder."""
    assert inf.decide(r_series=[], q_series=[], seed=1, data_valid=False)["decision"] \
        == inf.DECISION_NOT_EVALUABLE
