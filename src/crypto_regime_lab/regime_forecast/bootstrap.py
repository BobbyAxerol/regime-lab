"""Block bootstrap and head qualification evaluation for BTCUSDT regime forecasting.

Follows BTC-RPS-V1.2 Section 9 and Section 15 (MF-04):
- Circular / Moving Block Bootstrap preserving serial dependence from horizon overlap.
- Block size: default 5 weekly origins (or 28-35 days).
- Draws: 2000 replications with fixed seed 20260928.
- Independent qualification criteria for each head and horizon:
  - Brier Skill Score >= +0.05
  - Balanced Accuracy Gain >= +0.05
  - Relative Error Reduction >= +0.10 (for regression)
  - 95% Confidence Interval strictly positive (lower bound > 0)
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Tuple
import numpy as np


def get_bootstrap_block_spec(horizon_h: int) -> Dict[str, int]:
    """Computes primary and sensitivity block sizes according to Guide Section 6.5:
    - Primary length: ceil(H / 7) origins.
    - Sensitivity 1.5x: ceil(1.5 * H / 7) origins.
    - Sensitivity 2.0x: ceil(2.0 * H / 7) origins.
    """
    primary = int(math.ceil(horizon_h / 7.0))
    sens_1_5 = int(math.ceil(1.5 * horizon_h / 7.0))
    sens_2_0 = int(math.ceil(2.0 * horizon_h / 7.0))
    return {
        "primary": primary,
        "sensitivity_1_5x": sens_1_5,
        "sensitivity_2_0x": sens_2_0,
    }


def compute_origin_overlap_summary(
    origins: List[str],
    horizons: List[int] = [56, 90],
) -> Dict[str, Any]:
    """Generates Section 6.5 overlap summary across weekly evaluation origins."""
    n_origins = len(origins)
    out: Dict[str, Any] = {
        "n_origins": n_origins,
        "origin_interval_days": 7,
    }

    for h in horizons:
        spec = get_bootstrap_block_spec(h)
        primary_k = spec["primary"]
        # Pairs (i, j) with i < j where (j - i)*7 < h
        overlap_pairs = sum(
            1 for i in range(n_origins) for j in range(i + 1, n_origins)
            if (j - i) * 7 < h
        )
        effective_episodes = round(n_origins / float(primary_k), 2)
        calendar_span = (n_origins - 1) * 7 + h

        out[f"H{h}"] = {
            "horizon_days": h,
            "primary_block_size": primary_k,
            "sensitivity_blocks": [spec["sensitivity_1_5x"], spec["sensitivity_2_0x"]],
            "overlapping_origin_pairs": overlap_pairs,
            "calendar_span_days": calendar_span,
            "estimated_effective_independent_episodes": effective_episodes,
            "approximation_caveat": (
                "Moving block bootstrap CI is an asymptotic approximation under overlapping "
                "horizons; effective sample size is limited by horizon length."
            ),
        }
    return out


def compute_block_bootstrap_ci(
    y_true: np.ndarray,
    p_model: np.ndarray,
    p_ref: np.ndarray,
    metric_diff_fn: Callable[[np.ndarray, np.ndarray, np.ndarray], float],
    block_size: int = 5,
    n_boot: int = 2000,
    seed: int = 20260928,
    ci_level: float = 0.95,
) -> Tuple[float, float, float]:
    """Compute moving block bootstrap confidence interval for paired difference metric.
    
    Returns: (point_estimate, ci_lower, ci_upper)
    """
    n = len(y_true)
    if n < block_size or n == 0:
        val = float(metric_diff_fn(y_true, p_model, p_ref))
        return val, val, val

    point_estimate = float(metric_diff_fn(y_true, p_model, p_ref))
    rng = np.random.default_rng(seed)

    # Number of blocks needed
    k_blocks = int(np.ceil(n / block_size))
    max_start = n - block_size

    boot_diffs = []
    for _ in range(n_boot):
        start_indices = rng.integers(0, max_start + 1, size=k_blocks)
        sample_indices = []
        for s in start_indices:
            sample_indices.extend(range(s, s + block_size))
        sample_indices = np.array(sample_indices[:n])

        y_boot = y_true[sample_indices]
        p_m_boot = p_model[sample_indices]
        p_r_boot = p_ref[sample_indices]

        boot_val = metric_diff_fn(y_boot, p_m_boot, p_r_boot)
        boot_diffs.append(boot_val)

    alpha = (1.0 - ci_level) / 2.0
    ci_lower = float(np.percentile(boot_diffs, alpha * 100))
    ci_upper = float(np.percentile(boot_diffs, (1.0 - alpha) * 100))

    return point_estimate, ci_lower, ci_upper


def compute_block_bootstrap_ci_with_sensitivities(
    y_true: np.ndarray,
    p_model: np.ndarray,
    p_ref: np.ndarray,
    metric_diff_fn: Callable[[np.ndarray, np.ndarray, np.ndarray], float],
    horizon_h: int,
    n_boot: int = 2000,
    seed: int = 20260928,
    ci_level: float = 0.95,
) -> Dict[str, Any]:
    """Computes primary block bootstrap CI plus two sensitivities per Section 6.5."""
    spec = get_bootstrap_block_spec(horizon_h)
    primary_k = spec["primary"]
    pt, low, high = compute_block_bootstrap_ci(
        y_true, p_model, p_ref, metric_diff_fn,
        block_size=primary_k, n_boot=n_boot, seed=seed, ci_level=ci_level
    )

    sensitivities = {}
    n = len(y_true)
    for s_name, k in [("sens_1_5x", spec["sensitivity_1_5x"]), ("sens_2_0x", spec["sensitivity_2_0x"])]:
        if n < 2 * k:
            sensitivities[s_name] = {
                "block_size": k,
                "status": "NOT_INFORMATIVE",
                "reason": f"Sample size {n} < 2 * block_size ({2 * k}); insufficient blocks",
                "ci_95": None,
            }
        else:
            _, s_low, s_high = compute_block_bootstrap_ci(
                y_true, p_model, p_ref, metric_diff_fn,
                block_size=k, n_boot=n_boot, seed=seed, ci_level=ci_level
            )
            sensitivities[s_name] = {
                "block_size": k,
                "status": "COMPUTED",
                "ci_95": [s_low, s_high],
            }

    return {
        "point_estimate": pt,
        "ci_lower": low,
        "ci_upper": high,
        "primary_block_size": primary_k,
        "sensitivities": sensitivities,
    }


def qualify_head_status(
    brier_skill: float,
    brier_skill_ci: Tuple[float, float],
    bal_acc_gain: float,
    bal_acc_gain_ci: Tuple[float, float],
    min_brier_skill: float = 0.05,
    min_acc_gain: float = 0.05,
) -> Dict[str, Any]:
    """Determine head qualification status under strict standards."""
    ci_skill_low, ci_skill_high = brier_skill_ci
    ci_acc_low, ci_acc_high = bal_acc_gain_ci

    passes_skill = (brier_skill >= min_brier_skill) and (ci_skill_low > 0.0)
    passes_acc = (bal_acc_gain >= min_acc_gain) and (ci_acc_low > 0.0)

    if passes_skill and passes_acc:
        status = "QUALIFIED"
        reason = "Passes both Brier Skill (>=0.05, CI>0) and Balanced Accuracy Gain (>=0.05, CI>0)"
    elif passes_skill:
        status = "INCONCLUSIVE_SUPPORT"
        reason = "Passes Brier Skill but Balanced Accuracy gain is below threshold"
    elif brier_skill > 0.0 and ci_skill_low <= 0.0:
        status = "INCONCLUSIVE_MARGINAL"
        reason = "Positive point estimate but bootstrap confidence interval overlaps zero"
    else:
        status = "NOT_QUALIFIED"
        reason = "Failed qualification standards; negative or sub-threshold skill against frozen baseline"

    return {
        "status": status,
        "reason": reason,
        "brier_skill": brier_skill,
        "brier_skill_ci_95": [ci_skill_low, ci_skill_high],
        "bal_acc_gain": bal_acc_gain,
        "bal_acc_gain_ci_95": [ci_acc_low, ci_acc_high],
    }


def qualify_continuous_head_status(
    rel_error_reduction: float,
    error_reduction_ci: Tuple[float, float],
    min_reduction: float = 0.10,
) -> Dict[str, Any]:
    """Qualification for continuous regression head."""
    ci_low, ci_high = error_reduction_ci
    if (rel_error_reduction >= min_reduction) and (ci_low > 0.0):
        status = "QUALIFIED"
        reason = "Passes relative error reduction (>=0.10) with strictly positive CI"
    elif rel_error_reduction > 0.0 and ci_low <= 0.0:
        status = "INCONCLUSIVE_MARGINAL"
        reason = "Positive error reduction but bootstrap CI overlaps zero"
    else:
        status = "NOT_QUALIFIED"
        reason = "Failed error reduction standard against frozen baseline"

    return {
        "status": status,
        "reason": reason,
        "rel_error_reduction": rel_error_reduction,
        "rel_error_reduction_ci_95": [ci_low, ci_high],
    }
