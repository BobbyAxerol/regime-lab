"""VWFO-05 Final Evaluation, D1/D2 Decomposition, and Bootstrap Inference Module.

Implements VOL-WFO-V1.0 Section 10 and Section 16:
- Canonical Sharpe calculation and D1 decomposition: R_k = (SR_IS,J - SR_IS,C) + Q_k
- Multi-horizon D2 parameter-age diagnostic: D^age = SR_H1 - SR_H2 on 28-day continuations
- Circular moving-block bootstrap (5,000 draws, wrap-around, paired tuples)
- Decision table mapping to typed research conclusions
- Zero-engine reproduction of all statistics from raw daily returns
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .domain import compute_canonical_sharpe


@dataclass
class D1FoldResult:
    fold_idx: int
    origin: str
    target_start: str
    target_end: str
    arm_id: str
    comparator_id: str
    sr_is_c: float
    sr_is_j: float
    sr_fwd_c: float
    sr_fwd_j: float
    decay_c: float
    decay_j: float
    r_decay_reduction: float  # D_j - D_c
    q_fwd_gain: float         # SR_FWD_c - SR_FWD_j
    is_reference_diff: float  # SR_IS_j - SR_IS_c
    decomposition_residual: float  # abs(R - (is_diff + Q))


@dataclass
class D2ContinuationResult:
    origin: str
    arm_id: str
    params: Dict[str, Any]
    h1_start: str
    h1_end: str
    h2_start: str
    h2_end: str
    sr_h1: float
    sr_h2: float
    decay_age: float  # SR_H1 - SR_H2
    h1_daily_returns: List[float]
    h2_daily_returns: List[float]


def compute_d1_decomposition(
    c_outcomes: Sequence[Dict[str, Any]],
    comparator_outcomes: Sequence[Dict[str, Any]],
    comparator_id: str = "B_CAP",
) -> List[D1FoldResult]:
    """Computes exact D1 decomposition across all common paired folds (Section 10.2).

    Identity:
    R_k^{C:J} = D_{k,J} - D_{k,C}
    Q_k^{C:J} = SR_{FWD,k,C} - SR_{FWD,k,J}
    R_k^{C:J} = (SR_{IS,k,J} - SR_{IS,k,C}) + Q_k^{C:J}
    """
    if len(c_outcomes) != len(comparator_outcomes):
        raise ValueError(f"Folds count mismatch: C has {len(c_outcomes)}, comparator has {len(comparator_outcomes)}")

    results: List[D1FoldResult] = []
    for idx, (c_row, j_row) in enumerate(zip(c_outcomes, comparator_outcomes)):
        sr_is_c = float(c_row["is_sharpe"])
        sr_is_j = float(j_row["is_sharpe"])
        sr_fwd_c = float(c_row["fwd_sharpe"])
        sr_fwd_j = float(j_row["fwd_sharpe"])

        d_c = sr_is_c - sr_fwd_c
        d_j = sr_is_j - sr_fwd_j

        r = d_j - d_c
        q = sr_fwd_c - sr_fwd_j
        is_diff = sr_is_j - sr_is_c

        res = abs(r - (is_diff + q))
        if res > 1e-9:
            raise ValueError(f"D1 decomposition identity violated at fold {idx}: residual {res:.2e}")

        results.append(
            D1FoldResult(
                fold_idx=idx,
                origin=c_row.get("origin_cutoff", f"fold_{idx}"),
                target_start=c_row.get("target_start", ""),
                target_end=c_row.get("target_end", ""),
                arm_id="C_H14",
                comparator_id=comparator_id,
                sr_is_c=sr_is_c,
                sr_is_j=sr_is_j,
                sr_fwd_c=sr_fwd_c,
                sr_fwd_j=sr_fwd_j,
                decay_c=d_c,
                decay_j=d_j,
                r_decay_reduction=r,
                q_fwd_gain=q,
                is_reference_diff=is_diff,
                decomposition_residual=res,
            )
        )
    return results


def circular_moving_block_bootstrap(
    data: np.ndarray,
    block_length: int = 3,
    n_draws: int = 5000,
    seed: int = 20260929,
) -> Tuple[float, float, Tuple[float, float], np.ndarray]:
    """Executes circular moving-block bootstrap on paired fold statistics (Section 10.4).

    Guarantees:
    - Wraps indices circularly around the length K.
    - Draws contiguous blocks of length L.
    - Computes sample mean, one-sided 95% lower bound, and 95% basic/percentile CI.
    """
    k = len(data)
    if k < 2:
        raise ValueError(f"Insufficient data for bootstrap: len {k}")

    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(k / block_length))

    boot_means = np.empty(n_draws, dtype=float)

    for b in range(n_draws):
        start_indices = rng.integers(0, k, size=n_blocks)
        sample_indices = []
        for s in start_indices:
            for step in range(block_length):
                sample_indices.append((s + step) % k)
        sample_indices = sample_indices[:k]
        boot_sample = data[sample_indices]
        boot_means[b] = float(np.mean(boot_sample))

    point_estimate = float(np.mean(data))
    one_sided_lower_95 = float(np.percentile(boot_means, 5.0))
    two_sided_ci = (float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5)))

    return point_estimate, one_sided_lower_95, two_sided_ci, boot_means


def evaluate_decision_table(
    r_c_cap_point: float,
    r_c_cap_lower95: float,
    q_c_cap_lower95: float,
    r_c_o_lower95: float,
    q_c_o_lower95: float,
    r_c_p_lower95: float,
    q_c_p_lower95: float,
    q_c_b0_lower95: float,
    common_folds_count: int,
    domain_valid: bool = True,
) -> Dict[str, Any]:
    """Maps empirical bootstrap bounds to preregistered typed decisions (Section 10.5 & 10.6)."""
    if not domain_valid:
        return {
            "verdict": "NOT_EVALUABLE_FOR_REGISTERED_CONTRACT",
            "reason": "Domain/timing/sizing provenance validation failed",
            "primary_conjunction_met": False,
        }

    if common_folds_count < 12:
        return {
            "verdict": "INSUFFICIENT_PAIRED_FOLDS",
            "reason": f"Required >= 12 paired folds, got {common_folds_count}",
            "primary_conjunction_met": False,
        }

    # Primary Conjunction (§10.5):
    # Lower bound(R_C:CAP) > 0.20 AND Lower bound(Q_C:CAP) > -0.10
    primary_r_met = (r_c_cap_lower95 > 0.20)
    primary_q_met = (q_c_cap_lower95 > -0.10)
    primary_met = primary_r_met and primary_q_met

    # Forecast-Information Secondary Conjunction (§10.5):
    # R_C:O > 0, Q_C:O > -0.10, R_C:P > 0, Q_C:P > -0.10, Q_C:B0 > -0.10
    secondary_met = (
        (r_c_o_lower95 > 0.0)
        and (q_c_o_lower95 > -0.10)
        and (r_c_p_lower95 > 0.0)
        and (q_c_p_lower95 > -0.10)
        and (q_c_b0_lower95 > -0.10)
    )

    if primary_met and secondary_met:
        verdict = "PREDICTIVE_VOLATILITY_SELECTION_INFORMATION_WITHIN_SCOPE"
    elif primary_met:
        verdict = "MEANINGFUL_STANDARDIZED_RETENTION_VS_BCAP"
    elif r_c_cap_lower95 > 0.0:
        verdict = "REDUCTION_DETECTED_MAGNITUDE_UNPROVEN"
    elif r_c_cap_point > 0.0:
        verdict = "OBSERVED_REDUCTION_LOW_PRECISION"
    else:
        verdict = "NO_MEANINGFUL_RETENTION_EDGE_OBSERVED"

    return {
        "verdict": verdict,
        "primary_conjunction_met": primary_met,
        "secondary_conjunction_met": secondary_met,
        "primary_r_lower95": r_c_cap_lower95,
        "primary_q_lower95": q_c_cap_lower95,
        "threshold_r": 0.20,
        "threshold_q": -0.10,
        "common_folds_count": common_folds_count,
    }
