"""SD-02: intercept-free, per-origin-weighted contrast ridge (guide SS5.5).

Replaces ``fp/selector_b.py``'s ``fit_ridge``/``predict_ridge`` for SD, which
this study's own migration ledger records as SELF01_RIDGE_INTERCEPT:
``fp/selector_b.py::fit_ridge`` de-means y and fits a separate un-penalized
intercept, added back in ``predict_ridge`` -- incompatible with this guide's
SS5.5 "no intercept, anchor prediction = 0 by construction" requirement. This
module has NO intercept term anywhere: beta^T v with v == 0 (the anchor
against itself) always predicts exactly 0.0, structurally, not by a fitted
coefficient happening to be near zero.

Objective (guide SS5.5, exact normalization -- "phai giu dung normalization
nay"): ``sum_origin(mean_candidate_squared_error) + lambda * ||coef||^2``.
Implemented as weighted ridge with weight_i = 1 / n_origin(i) for every
candidate row i, so every origin contributes total weight exactly 1
regardless of how many candidates it has (guide SS5.5 point 1: "một total
weight bằng 1 cho mỗi origin: candidate weights trong origin cộng về 1").
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np


class RidgeContrastError(ValueError):
    """A ridge-contrast fit/predict step was internally inconsistent."""


def per_origin_weights(origin_ids: list) -> np.ndarray:
    """weight_i = 1 / n_origin(i) -- candidate weights within an origin sum
    to exactly 1, so every origin contributes total weight 1 to the loss
    regardless of its own candidate-pool size."""
    counts = Counter(origin_ids)
    return np.array([1.0 / counts[o] for o in origin_ids], dtype=float)


@dataclass(frozen=True)
class RidgeFit:
    beta: np.ndarray          # shape (n_features,), NO intercept term
    lambda_reg: float
    n_features: int
    n_train_origins: int
    n_train_rows: int


def fit_weighted_ridge(V: np.ndarray, y: np.ndarray, weights: np.ndarray, *,
                       lambda_reg: float, n_train_origins: int) -> RidgeFit:
    """Closed-form solve of
    ``beta* = argmin_beta sum_i w_i (y_i - beta^T v_i)^2 + lambda*||beta||^2``
    -- i.e. ``beta* = (V^T W V + lambda*I)^-1 V^T W y``. No intercept column
    is ever appended to V."""
    if V.ndim != 2:
        raise RidgeContrastError(f"V must be 2D (n_rows, n_features), got shape {V.shape}")
    n_rows, n_features = V.shape
    if y.shape != (n_rows,) or weights.shape != (n_rows,):
        raise RidgeContrastError("y/weights shape mismatch against V's row count")
    if lambda_reg < 0:
        raise RidgeContrastError("lambda_reg must be >= 0")
    w_sqrt = np.sqrt(weights)
    vw = V * w_sqrt[:, None]
    yw = y * w_sqrt
    gram = vw.T @ vw + lambda_reg * np.eye(n_features)
    rhs = vw.T @ yw
    beta = np.linalg.solve(gram, rhs)
    return RidgeFit(beta=beta, lambda_reg=lambda_reg, n_features=n_features,
                    n_train_origins=n_train_origins, n_train_rows=n_rows)


def predict(fit: RidgeFit, v: np.ndarray) -> float:
    """Y_hat = beta^T v. v == 0 (a zero contrast vector) always predicts
    exactly 0.0 -- no intercept exists to move this."""
    if v.shape != (fit.n_features,):
        raise RidgeContrastError(f"contrast vector dimensionality mismatch: expected "
                                 f"{fit.n_features}, got {v.shape}")
    return float(fit.beta @ v)


def weighted_objective_value(V: np.ndarray, y: np.ndarray, weights: np.ndarray,
                             beta: np.ndarray, lambda_reg: float) -> float:
    """Independent re-evaluation of the SAME objective ``fit_weighted_ridge``
    minimizes -- used by tests to verify the closed-form solve against a
    direct scan/gradient check, per guide SS5.5's own fixture-verification
    requirement."""
    residual = y - V @ beta
    return float(np.sum(weights * residual ** 2) + lambda_reg * np.sum(beta ** 2))
