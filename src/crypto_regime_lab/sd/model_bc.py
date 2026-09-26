"""SD-02: B_SD_GLOBAL and C_SD_JM model fit/predict (guide SS5.5-5.6).

B is the global no-intercept contrast ridge; C adds a state-specific
residual correction, penalized toward 0 under low support (guide SS5.5
points 2-4, SS5.6). Both share the SAME phi/contrast-vector/ridge machinery
in ``contrast_features``/``ridge_contrast`` -- C is never a different model
architecture, only an additive correction in the same v coordinates.

``predict_c`` is unconditionally callable regardless of what B selected or
fell back to (guide SS5.6: "C phai duoc goi o moi model-ready fold du B
selected anchor/fallback ve anchor") -- it has no dependency on B's own
selection OUTCOME, only on B's fitted prediction FUNCTION.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .contrast_features import PhiFit, contrast_vector, fit_phi
from .ridge_contrast import RidgeFit, fit_weighted_ridge, per_origin_weights
from .ridge_contrast import predict as _ridge_predict

MIN_GLOBAL_TRAIN_ORIGINS = 12   # guide SS5.6
MIN_STATE_TRAIN_ORIGINS = 3     # guide SS5.6
LAMBDA_GLOBAL_DEFAULT = 10.0    # guide SS5.5 frozen starting penalty
LAMBDA_STATE_DEFAULT = 10.0     # guide SS5.5 frozen starting penalty


class ModelError(ValueError):
    """A model-B/C fit step did not clear its guide-mandated support floor."""


@dataclass(frozen=True)
class ModelBFit:
    phi_fit: PhiFit
    ridge_fit: RidgeFit
    n_train_origins: int
    lambda_global: float


@dataclass(frozen=True)
class ModelCFit:
    model_b: ModelBFit
    state_ridge_fits: dict = field(default_factory=dict)     # state -> RidgeFit, only states clearing the floor
    state_support_counts: dict = field(default_factory=dict)  # every state seen -> distinct origin count
    lambda_state: float = LAMBDA_STATE_DEFAULT


def _distinct_origins(rows: list) -> list:
    return sorted(set(r["origin_id"] for r in rows))


def fit_model_b(train_rows: list, *, lambda_global: float = LAMBDA_GLOBAL_DEFAULT) -> ModelBFit:
    """``train_rows``: one dict per (matured train origin, panel candidate)
    pair -- {"origin_id", "candidate_features", "anchor_features", "y"}.
    Each origin's own anchor row is naturally already IN this pool (the
    representative panel always includes it, guide SS3.5), contributing a
    trivial v=0/y=0 example -- no separate anchor-only pool exists."""
    origins = _distinct_origins(train_rows)
    if len(origins) < MIN_GLOBAL_TRAIN_ORIGINS:
        raise ModelError(f"global model B needs >= {MIN_GLOBAL_TRAIN_ORIGINS} distinct matured "
                         f"train origins, got {len(origins)}")
    phi_fit = fit_phi([r["candidate_features"] for r in train_rows])
    V = np.array([contrast_vector(phi_fit, r["candidate_features"], r["anchor_features"])
                 for r in train_rows])
    y = np.array([r["y"] for r in train_rows], dtype=float)
    weights = per_origin_weights([r["origin_id"] for r in train_rows])
    ridge_fit = fit_weighted_ridge(V, y, weights, lambda_reg=lambda_global,
                                   n_train_origins=len(origins))
    return ModelBFit(phi_fit=phi_fit, ridge_fit=ridge_fit, n_train_origins=len(origins),
                     lambda_global=lambda_global)


def predict_b(fit: ModelBFit, candidate_features: dict, anchor_features: dict) -> float:
    v = contrast_vector(fit.phi_fit, candidate_features, anchor_features)
    return _ridge_predict(fit.ridge_fit, v)


def fit_model_c(model_b: ModelBFit, train_rows: list, *,
                lambda_state: float = LAMBDA_STATE_DEFAULT) -> ModelCFit:
    """``train_rows``: same shape as ``fit_model_b``'s, PLUS ``"state"``
    (int) per row -- the JM-filtered (or R_RULE) state of that row's own
    origin, shared by every candidate row from that origin. A state with
    fewer than MIN_STATE_TRAIN_ORIGINS distinct origins gets NO fitted
    ridge (correction stays 0 at predict time, guide SS5.6 STATE_SUPPORT_LOW)
    -- never a spuriously-inflated fit on too little data."""
    by_state: dict = {}
    for row in train_rows:
        by_state.setdefault(row["state"], []).append(row)
    state_ridge_fits, state_support_counts = {}, {}
    for state, rows in by_state.items():
        origins = _distinct_origins(rows)
        state_support_counts[state] = len(origins)
        if len(origins) < MIN_STATE_TRAIN_ORIGINS:
            continue
        V = np.array([contrast_vector(model_b.phi_fit, r["candidate_features"], r["anchor_features"])
                     for r in rows])
        residuals = np.array([r["y"] - predict_b(model_b, r["candidate_features"], r["anchor_features"])
                             for r in rows], dtype=float)
        weights = per_origin_weights([r["origin_id"] for r in rows])
        state_ridge_fits[state] = fit_weighted_ridge(V, residuals, weights, lambda_reg=lambda_state,
                                                      n_train_origins=len(origins))
    return ModelCFit(model_b=model_b, state_ridge_fits=state_ridge_fits,
                     state_support_counts=state_support_counts, lambda_state=lambda_state)


def predict_c(fit: ModelCFit, candidate_features: dict, anchor_features: dict, *, state) -> dict:
    """Always callable regardless of B's own selection outcome. Returns the
    additive prediction plus a typed label: ``CONTEXT_CONDITIONED`` when a
    state-specific correction was applied, ``GLOBAL_FALLBACK`` (with a
    ``STATE_SUPPORT_LOW``/``UNKNOWN_STATE`` reason) when correction=0."""
    y_hat_b = predict_b(fit.model_b, candidate_features, anchor_features)
    if state not in fit.state_ridge_fits:
        reason = "STATE_SUPPORT_LOW" if state in fit.state_support_counts else "UNKNOWN_STATE"
        return {"y_hat": y_hat_b, "y_hat_b": y_hat_b, "correction": 0.0,
               "label": "GLOBAL_FALLBACK", "reason": reason, "state": state}
    v = contrast_vector(fit.model_b.phi_fit, candidate_features, anchor_features)
    correction = _ridge_predict(fit.state_ridge_fits[state], v)
    return {"y_hat": y_hat_b + correction, "y_hat_b": y_hat_b, "correction": correction,
           "label": "CONTEXT_CONDITIONED", "reason": None, "state": state}
