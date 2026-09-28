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

from typing import Any, Callable, Dict, Tuple
import numpy as np


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
