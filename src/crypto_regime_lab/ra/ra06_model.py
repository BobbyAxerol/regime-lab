"""RA06.5/10.6 model ladder: AGE_ONLY vs AGE_CONTEXT (guide section 10).

At most one small family estimator -- hand-implemented closed-form ridge
(no sklearn in this venv; the formula is standard and auditable:
beta = (X'X + alpha*I)^-1 X'y) -- chosen via inner time-series
(leave-one-origin-out, never a random/shuffled split) cross-validation,
with a small hyperparameter grid PRE-REGISTERED before any fit is run. No
calibrated-probability language is used anywhere for this uncalibrated
heuristic.

`MIN_SUPPORT_FOR_MODEL_FIT` is guide 10.3's own warning made concrete: an
8-12-origin feasibility pilot ("day khong phai sample size du de hoc model
dang tin") is not enough to trust a fitted comparison. Below the floor, the
phase reports INSUFFICIENT_SUPPORT structurally (G06-MODEL's own sanctioned,
non-financial-claim outcome) rather than fit anyway and imply a result the
sample cannot support.
"""
from __future__ import annotations

import numpy as np

#: Pre-registered before any model is fit (guide 10.5: "hyperparameter grid
#: nho duoc ghi truoc").
RIDGE_ALPHA_GRID = (0.1, 1.0, 10.0)
#: Below this many OK (non-censored) Panel B rows, a fit is not attempted as
#: a claim -- guide 10.3's own floor language, made a concrete number here.
MIN_SUPPORT_FOR_MODEL_FIT = 8

AGE_ONLY_FEATURES = ("intercept", "age_days")
AGE_CONTEXT_FEATURES = AGE_ONLY_FEATURES + ("realized_vol_20d", "regime_transitions_since_incumbent",
                                            "incumbent_trailing_return")


def ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Closed-form ridge. `alpha` never regularises the intercept column."""
    n_features = X.shape[1]
    penalty = np.eye(n_features) * alpha
    penalty[0, 0] = 0.0  # column 0 is always the intercept by convention here
    return np.linalg.solve(X.T @ X + penalty, X.T @ y)


def ridge_predict(X: np.ndarray, beta: np.ndarray) -> np.ndarray:
    return X @ beta


def leave_one_out_inner_cv(X: np.ndarray, y: np.ndarray, *,
                           alpha_grid: tuple = RIDGE_ALPHA_GRID) -> dict:
    """P06: design selection is TRAIN-ONLY -- leave-one-origin-out, never a
    random/shuffled split (guide 10.6 purge/maturity discipline applied to
    model selection, not just labels)."""
    n = len(y)
    per_alpha = {}
    for alpha in alpha_grid:
        errors = []
        for i in range(n):
            train_idx = [j for j in range(n) if j != i]
            if len(train_idx) < 2:
                continue
            beta = ridge_fit(X[train_idx], y[train_idx], alpha)
            pred = float(ridge_predict(X[i:i + 1], beta)[0])
            errors.append((pred - y[i]) ** 2)
        per_alpha[alpha] = float(np.mean(errors)) if errors else None
    scored = [(alpha, mse) for alpha, mse in per_alpha.items() if mse is not None]
    selected_alpha = min(scored, key=lambda row: row[1])[0] if scored else None
    return {
        "schema": "regime_lab.ra06_inner_cv.v1", "method": "leave_one_origin_out",
        "alpha_grid": list(alpha_grid), "per_alpha_loo_mse": per_alpha,
        "selected_alpha": selected_alpha,
        "selected_loo_mse": per_alpha.get(selected_alpha) if selected_alpha is not None else None,
    }


def build_feature_matrix(rows: list[dict], *, feature_names: tuple) -> tuple:
    """Row order preserved (time-series, never shuffled). Each row must
    already carry every named feature -- missing features fail loudly, not
    silently as 0 (guide 10.2's null+reason discipline extended to
    features)."""
    X = np.zeros((len(rows), len(feature_names)), dtype=float)
    for i, row in enumerate(rows):
        for j, name in enumerate(feature_names):
            if name == "intercept":
                X[i, j] = 1.0
                continue
            if name not in row["features"] or row["features"][name] is None:
                raise ValueError(f"row for origin {row.get('origin')} missing feature {name!r}")
            X[i, j] = float(row["features"][name])
    y = np.array([row["g"] for row in rows], dtype=float)
    return X, y


def fit_one_ladder_entry(rows: list[dict], *, feature_names: tuple, label: str) -> dict:
    X, y = build_feature_matrix(rows, feature_names=feature_names)
    cv = leave_one_out_inner_cv(X, y)
    beta = (ridge_fit(X, y, cv["selected_alpha"]) if cv["selected_alpha"] is not None else None)
    return {
        "schema": "regime_lab.ra06_model_fit.v1", "label": label,
        "feature_names": list(feature_names), "n": len(rows),
        "inner_cv": cv,
        "full_sample_beta": (beta.tolist() if beta is not None else None),
        "calibrated_probability_language_used": False,
    }


def fit_and_compare(panel_b_rows: list[dict], *, min_support: int = MIN_SUPPORT_FOR_MODEL_FIT) -> dict:
    """P05: AGE_ONLY vs AGE_CONTEXT on the SAME target/cohort/split/economic
    contract (guide 10.6). Below `min_support` OK rows, report
    INSUFFICIENT_SUPPORT and do not fit -- a fit on too few points to trust
    is not run just because it is possible to run it.
    """
    ok_rows = [row for row in panel_b_rows if row["g"]["status"] == "OK"]
    if len(ok_rows) < min_support:
        return {
            "schema": "regime_lab.ra06_model_ladder.v1", "status": "INSUFFICIENT_SUPPORT",
            "support": len(ok_rows), "min_required": min_support,
            "disposition": ("measured, preregistered branch (guide G06-MODEL): a training "
                            "attempt below the registered support floor is not run as a claim; "
                            "this is a valid, non-financial-claim phase outcome, not a missing "
                            "implementation"),
            "age_only": None, "age_context": None, "primary_contribution": None,
        }
    labelled_rows = [{"origin": row["origin"], "g": row["g"]["g"], "features": row["features"]}
                     for row in ok_rows]
    age_only = fit_one_ladder_entry(labelled_rows, feature_names=AGE_ONLY_FEATURES, label="AGE_ONLY")
    age_context = fit_one_ladder_entry(labelled_rows, feature_names=AGE_CONTEXT_FEATURES,
                                       label="AGE_CONTEXT")
    contribution = None
    if (age_only["inner_cv"]["selected_loo_mse"] is not None
            and age_context["inner_cv"]["selected_loo_mse"] is not None):
        contribution = age_only["inner_cv"]["selected_loo_mse"] - age_context["inner_cv"]["selected_loo_mse"]
    return {
        "schema": "regime_lab.ra06_model_ladder.v1", "status": "FIT_ATTEMPTED",
        "support": len(ok_rows), "min_required": min_support,
        "age_only": age_only, "age_context": age_context,
        "primary_contribution_loo_mse_reduction": contribution,
        "primary_contribution_note": ("AGE_CONTEXT's inner-CV MSE improvement over AGE_ONLY at "
                                      "EQUAL budget/admission/execution -- guide 10.6: never use "
                                      "AGE_CONTEXT beating a slow calendar as standalone evidence "
                                      "about regime; this compares AGE_CONTEXT to AGE_ONLY only"),
    }
