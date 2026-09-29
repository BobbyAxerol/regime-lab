"""Volatility-Conditioned WFO Parameter Selectors and Control Arms (Phase VWFO-03).

Follows VOL-WFO-V1.0 Section 8 and Section 14:
- Feature descriptor vector phi(z_{k, theta}) with 5 features:
    1. coeff_norm
    2. ap_norm
    3. threshold_norm
    4. raw_is_sharpe
    5. log_fills_count
- Contrast vector: v_{k, theta} = phi(z_{k, theta}) - phi(z_{k, a})
  Structural identity: v_{k, a} == 0 -> Yhat(anchor) == 0.000 identically.
- Scaling policy: Standardizer fit strictly on past matured training candidates.
- Solvers for 8 arms:
    * A_M4: Raw Stock Mode 4 temporal robustness clustering anchor.
    * B0_GLOBAL: Origin-mean weighted Ridge regression (penalty 10.0) on contrast v.
    * B_CAP: B0 + pooled residual correction gamma_0 with penalty 10.0.
    * O_PERSIST: B0 + pooled residual gamma_0 + interaction z^F_k gamma_1 using p_PERSIST.
    * C_H14: B0 + pooled residual gamma_0 + interaction z^F_k gamma_1 using p_LOW.
    * P_NI_01..03: B0 + pooled residual gamma_0 + interaction z^F_k gamma_1 using pseudo p_LOW (fixed seeds).
- Candidate Selection Rule:
    1. Q_hat(theta) = SR_IS(theta) - SR_IS(a) - Yhat(theta)
    2. Filter Q_hat(theta) >= -0.10
    3. Objective: min signed Yhat(theta) (NOT max return or max Sharpe)
    4. Tie-breaking: Euclidean distance to anchor in parameter space, then candidate ID digest.
    5. Fallback chain: arm winner -> B0 proposal -> anchor.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


DESCRIPTOR_FEATURES = [
    "coeff_norm",
    "ap_norm",
    "threshold_norm",
    "raw_is_sharpe",
    "log_fills_count",
]

PARAM_RANGES = {
    "coeff": 4.0,  # 1 to 5
    "AP": 90.0,  # 10 to 100
    "alpha.condition_threshold": 80.0,  # 10 to 90
}


def _extract_raw_descriptor(cand: Dict[str, Any]) -> np.ndarray:
    """Extracts raw numeric vector [coeff, AP, threshold, is_sharpe, log(1 + fills)]."""
    params = cand.get("params", {})
    coeff = float(params.get("coeff", 2))
    ap = float(params.get("AP", 40))
    threshold = float(params.get("alpha.condition_threshold", 50))
    is_sharpe = float(cand.get("is_sharpe", 0.0))
    fills = float(cand.get("fills_count", 0))
    log_fills = float(np.log1p(max(fills, 0.0)))
    return np.array([coeff, ap, threshold, is_sharpe, log_fills], dtype=np.float64)


class CandidateDescriptorStandardizer:
    """Standardizes candidate descriptors strictly using past matured training candidates."""

    def __init__(self) -> None:
        self.means: np.ndarray = np.zeros(len(DESCRIPTOR_FEATURES), dtype=np.float64)
        self.stds: np.ndarray = np.ones(len(DESCRIPTOR_FEATURES), dtype=np.float64)
        self.fitted: bool = False

    def fit(self, training_candidates: List[Dict[str, Any]]) -> "CandidateDescriptorStandardizer":
        if not training_candidates:
            self.fitted = True
            return self

        raw_matrix = np.array([_extract_raw_descriptor(c) for c in training_candidates], dtype=np.float64)
        self.means = np.mean(raw_matrix, axis=0)
        stds = np.std(raw_matrix, axis=0, ddof=1) if len(raw_matrix) > 1 else np.ones(raw_matrix.shape[1])
        # Floor std at 1e-4 to avoid divide by zero
        self.stds = np.maximum(stds, 1e-4)
        self.fitted = True
        return self

    def transform(self, cand: Dict[str, Any]) -> np.ndarray:
        raw = _extract_raw_descriptor(cand)
        return (raw - self.means) / self.stds


def compute_contrast_vector(
    cand: Dict[str, Any],
    anchor: Dict[str, Any],
    standardizer: CandidateDescriptorStandardizer,
) -> np.ndarray:
    """Computes contrast vector v = phi(cand) - phi(anchor).

    By mathematical identity, if cand is anchor, v is identically zeros.
    """
    if cand.get("is_anchor", False) or cand.get("candidate_id") == anchor.get("candidate_id"):
        return np.zeros(len(DESCRIPTOR_FEATURES), dtype=np.float64)
    phi_cand = standardizer.transform(cand)
    phi_anchor = standardizer.transform(anchor)
    return phi_cand - phi_anchor


def compute_param_distance(cand: Dict[str, Any], anchor: Dict[str, Any]) -> float:
    """Normalized Euclidean distance to anchor in parameter space."""
    p_c = cand.get("params", {})
    p_a = anchor.get("params", {})
    dist_sq = 0.0
    for k, span in PARAM_RANGES.items():
        v_c = float(p_c.get(k, 0.0))
        v_a = float(p_a.get(k, 0.0))
        diff = (v_c - v_a) / max(span, 1.0)
        dist_sq += diff * diff
    return float(np.sqrt(dist_sq))


@dataclass
class SelectorModelFit:
    """Stores fitted weights for B0, B_CAP, and contextual arms."""

    beta_b0: np.ndarray  # shape (d,)
    gamma_cap: np.ndarray  # shape (d,)
    gamma_c_pooled: np.ndarray  # shape (d,)
    gamma_c_interaction: np.ndarray  # shape (d,)
    gamma_o_pooled: np.ndarray  # shape (d,)
    gamma_o_interaction: np.ndarray  # shape (d,)
    gamma_ni_pooled: Dict[int, np.ndarray] = field(default_factory=dict)
    gamma_ni_interaction: Dict[int, np.ndarray] = field(default_factory=dict)
    matured_origins_count: int = 0
    total_training_candidates: int = 0


def fit_selectors(
    archive_records: List[Dict[str, Any]],
    historical_contexts: Dict[str, float],  # origin -> z^F (H14)
    historical_persist_contexts: Dict[str, float],  # origin -> z^F (O_PERSIST)
    historical_ni_contexts: Dict[int, Dict[str, float]],  # seed -> (origin -> z^F)
    standardizer: CandidateDescriptorStandardizer,
    lambda_reg: float = 10.0,
) -> SelectorModelFit:
    """Fits B0, B_CAP, O, C, and P_NI models using sum-of-origin-means weighted ridge regression."""
    # Group records by origin
    origins_map: Dict[str, List[Dict[str, Any]]] = {}
    for r in archive_records:
        orig = r.get("origin_cutoff", "")
        # Only use evaluated non-anchor candidates with valid relative decay
        origins_map.setdefault(orig, []).append(r)

    v_rows: List[np.ndarray] = []
    y_rows: List[float] = []
    w_rows: List[float] = []
    z_c_rows: List[float] = []
    z_o_rows: List[float] = []
    z_ni_rows: Dict[int, List[float]] = {s: [] for s in historical_ni_contexts.keys()}

    matured_origins = 0
    for orig, cands in origins_map.items():
        # Find anchor for this origin
        anchor = next((c for c in cands if c.get("is_anchor")), None)
        if not anchor:
            continue

        non_anchors = [c for c in cands if not c.get("is_anchor") and "relative_decay_y" in c]
        if not non_anchors:
            continue

        matured_origins += 1
        n_k = len(non_anchors)
        w_k = 1.0 / n_k

        z_c = float(historical_contexts.get(orig, 0.0))
        z_o = float(historical_persist_contexts.get(orig, 0.0))

        for c in non_anchors:
            v = compute_contrast_vector(c, anchor, standardizer)
            y = float(c["relative_decay_y"])
            v_rows.append(v)
            y_rows.append(y)
            w_rows.append(w_k)
            z_c_rows.append(z_c)
            z_o_rows.append(z_o)
            for s in historical_ni_contexts.keys():
                z_ni_rows[s].append(float(historical_ni_contexts[s].get(orig, 0.0)))

    d = len(DESCRIPTOR_FEATURES)
    if not v_rows or matured_origins < 1:
        # Cold start fallback
        return SelectorModelFit(
            beta_b0=np.zeros(d),
            gamma_cap=np.zeros(d),
            gamma_c_pooled=np.zeros(d),
            gamma_c_interaction=np.zeros(d),
            gamma_o_pooled=np.zeros(d),
            gamma_o_interaction=np.zeros(d),
            gamma_ni_pooled={s: np.zeros(d) for s in historical_ni_contexts.keys()},
            gamma_ni_interaction={s: np.zeros(d) for s in historical_ni_contexts.keys()},
            matured_origins_count=0,
            total_training_candidates=0,
        )

    V = np.array(v_rows, dtype=np.float64)  # (M, d)
    Y = np.array(y_rows, dtype=np.float64)  # (M,)
    W = np.diag(np.array(w_rows, dtype=np.float64))  # (M, M)

    # 1. Global B0: (V^T W V + 10 I) beta = V^T W Y
    reg_I_d = lambda_reg * np.eye(d, dtype=np.float64)
    beta_b0 = np.linalg.solve(V.T @ W @ V + reg_I_d, V.T @ W @ Y)

    # Residuals e = Y - V beta
    e = Y - V @ beta_b0

    # 2. B_CAP: (V^T W V + 10 I) gamma_0 = V^T W e
    gamma_cap = np.linalg.solve(V.T @ W @ V + reg_I_d, V.T @ W @ e)

    # Helper for contextual residual fit: U = [V, Z * V]
    reg_I_2d = lambda_reg * np.eye(2 * d, dtype=np.float64)

    def _fit_context_gamma(z_list: List[float]) -> Tuple[np.ndarray, np.ndarray]:
        Z_col = np.array(z_list, dtype=np.float64).reshape(-1, 1)
        U = np.hstack([V, Z_col * V])
        gamma_2d = np.linalg.solve(U.T @ W @ U + reg_I_2d, U.T @ W @ e)
        return gamma_2d[:d], gamma_2d[d:]

    # 3. C_H14
    g_c_pool, g_c_inter = _fit_context_gamma(z_c_rows)

    # 4. O_PERSIST
    g_o_pool, g_o_inter = _fit_context_gamma(z_o_rows)

    # 5. P_NI_01..03
    g_ni_pool: Dict[int, np.ndarray] = {}
    g_ni_inter: Dict[int, np.ndarray] = {}
    for s, z_s in z_ni_rows.items():
        g_p, g_i = _fit_context_gamma(z_s)
        g_ni_pool[s] = g_p
        g_ni_inter[s] = g_i

    return SelectorModelFit(
        beta_b0=beta_b0,
        gamma_cap=gamma_cap,
        gamma_c_pooled=g_c_pool,
        gamma_c_interaction=g_c_inter,
        gamma_o_pooled=g_o_pool,
        gamma_o_interaction=g_o_inter,
        gamma_ni_pooled=g_ni_pool,
        gamma_ni_interaction=g_ni_inter,
        matured_origins_count=matured_origins,
        total_training_candidates=len(v_rows),
    )


def predict_yhat(
    cand: Dict[str, Any],
    anchor: Dict[str, Any],
    arm_id: str,
    fit: SelectorModelFit,
    standardizer: CandidateDescriptorStandardizer,
    context_z: float = 0.0,
    ni_seed: Optional[int] = None,
) -> float:
    """Predicts relative Sharpe decay Yhat for candidate under specified arm."""
    if cand.get("is_anchor") or cand.get("candidate_id") == anchor.get("candidate_id"):
        return 0.0

    v = compute_contrast_vector(cand, anchor, standardizer)

    if arm_id == "A_M4":
        return 0.0
    elif arm_id == "B0_GLOBAL":
        return float(fit.beta_b0 @ v)
    elif arm_id == "B_CAP":
        return float((fit.beta_b0 + fit.gamma_cap) @ v)
    elif arm_id == "C_H14":
        total_coef = fit.beta_b0 + fit.gamma_c_pooled + context_z * fit.gamma_c_interaction
        return float(total_coef @ v)
    elif arm_id == "O_PERSIST":
        total_coef = fit.beta_b0 + fit.gamma_o_pooled + context_z * fit.gamma_o_interaction
        return float(total_coef @ v)
    elif arm_id.startswith("P_NI"):
        seed = ni_seed or 20261001
        g_p = fit.gamma_ni_pooled.get(seed, np.zeros_like(fit.beta_b0))
        g_i = fit.gamma_ni_interaction.get(seed, np.zeros_like(fit.beta_b0))
        total_coef = fit.beta_b0 + g_p + context_z * g_i
        return float(total_coef @ v)
    else:
        return float(fit.beta_b0 @ v)


def select_candidate_for_arm(
    candidate_pool: List[Dict[str, Any]],
    anchor: Dict[str, Any],
    arm_id: str,
    fit: SelectorModelFit,
    standardizer: CandidateDescriptorStandardizer,
    context_z: float = 0.0,
    ni_seed: Optional[int] = None,
    q_hat_filter_floor: float = -0.10,
) -> Dict[str, Any]:
    """Applies candidate selection rule (VOL-WFO-V1.0 Section 8.5):

    1. Predict Yhat on full pool.
    2. Compute Qhat(theta) = SR_IS(theta) - SR_IS(anchor) - Yhat(theta).
    3. Filter candidates with Qhat >= q_hat_filter_floor (-0.10).
    4. Select candidate with min signed Yhat (least Sharpe decay).
    5. Tie-break: Euclidean distance to anchor in parameter space, then ID digest.
    """
    sr_is_anchor = float(anchor.get("is_sharpe", 0.0))

    evaluated_pool: List[Dict[str, Any]] = []
    for cand in candidate_pool:
        sr_is_cand = float(cand.get("is_sharpe", 0.0))
        y_hat = predict_yhat(
            cand=cand,
            anchor=anchor,
            arm_id=arm_id,
            fit=fit,
            standardizer=standardizer,
            context_z=context_z,
            ni_seed=ni_seed,
        )
        q_hat = sr_is_cand - sr_is_anchor - y_hat
        p_dist = compute_param_distance(cand, anchor)
        c_id = str(cand.get("candidate_id", ""))
        digest = hashlib.sha256(c_id.encode("utf-8")).hexdigest()

        evaluated_pool.append({
            "candidate": cand,
            "y_hat": y_hat,
            "q_hat": q_hat,
            "p_dist": p_dist,
            "digest": digest,
            "is_anchor": bool(cand.get("is_anchor", False) or c_id == anchor.get("candidate_id")),
        })

    # Filter by Qhat >= -0.10
    eligible = [c for c in evaluated_pool if c["q_hat"] >= q_hat_filter_floor]

    if not eligible:
        # Anchor is always eligible since Qhat(anchor) = 0.0 >= -0.10
        eligible = [c for c in evaluated_pool if c["is_anchor"]]

    # Sort by:
    # 1. min signed y_hat (primary objective)
    # 2. min param distance to anchor (tie-break 1)
    # 3. digest (tie-break 2)
    def sort_key(item: Dict[str, Any]) -> Tuple[float, float, str]:
        # Quantize y_hat to 1e-6 for tie-breaking
        y_quant = float(np.round(item["y_hat"], 6))
        d_quant = float(np.round(item["p_dist"], 6))
        return (y_quant, d_quant, item["digest"])

    eligible.sort(key=sort_key)
    winner_item = eligible[0]

    return {
        "arm_id": arm_id,
        "selected_candidate": winner_item["candidate"],
        "y_hat": winner_item["y_hat"],
        "q_hat": winner_item["q_hat"],
        "is_anchor": winner_item["is_anchor"],
        "param_distance_to_anchor": winner_item["p_dist"],
        "eligible_count": len(eligible),
        "total_pool_count": len(candidate_pool),
    }
