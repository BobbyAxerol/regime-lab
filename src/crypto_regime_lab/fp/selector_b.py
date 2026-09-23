"""FP-05 -- Selector B: forward-persistent selection, NO regime/context
(guide section 8 / section 17).

Chooses a region/candidate with good predicted forward utility and low
predicted decay, from FP-04's already-frozen historical archive, using ONLY:
current IS descriptors, parameter geometry, neighborhood fragility, and
historical matured forward evidence (guide 8.1). Never a signed market
regime/context feature -- that is Selector C's job (guide section 9, FP-06).

Pipeline (guide 4.3's pseudocode, scoped to what FP-05 itself owns):

  1. build_feature_matrix   -- one row per (record, region), guide 8.2's six
     feature categories, IS-time information only.
  2. walk_forward_oof       -- true chronological OOF (guide 8.3/8.4): a
     validation origin's training rows are only ever those whose
     label_available_at is BEFORE that origin's own decision time (reuses
     fp.forward_ledger.training_view / fp.chronology.chronological_split
     verbatim -- never a second chronology guard).
  3. select_alpha           -- picks the ridge penalty by aggregate OOF
     error across the walk-forward folds (guide 8.3), never by in-sample
     fit quality (guide 17's "Khong dung training fit quality lam
     predictive evidence").
  4. decay_risk_branch/score -- guide 8.5/8.6: mean-decay branch when OOF
     origin count is below the tail-quantile floor (guide 8.7: <20), the
     registered fallback, not an improvised substitute.
  5. eligible_candidates/rank_and_select -- guide 8.6's ordered eligibility
     checks, then the real evaluated medoid (never an invented point).

Ridge regression is implemented here directly (closed-form, numpy only --
no sklearn is installed in the lab venv, and guide 8.3 explicitly frames
this as "thiet ke can duoc trien khai/kiem chung" -- a design to implement
and verify, not a library call to trust).
"""
from __future__ import annotations

import math

FEATURE_NAMES = (
    # A-SC's 3 active (non-fixed) dims, literal schema names -- FP-05 is
    # scoped to A-SC only, matching FP-03/04's single-cell pilot precedent;
    # a different alpha would need its own FEATURE_NAMES.
    "norm_coeff", "norm_AP", "norm_alpha.condition_threshold",   # effective normalized parameters
    "is_mean_daily_return",                              # raw IS mean net return
    "is_daily_sharpe",                                   # raw IS risk metric
    "region_support_within_origin",                       # temporal finite/support coverage
    "behavioral_diversity_mean_pairwise_distance",        # neighborhood fragility (1)
    "is_objective_spread",                                # neighborhood fragility (2)
    "activity_entries",                                   # activity/exposure descriptor
)
ALPHA_GRID = (0.1, 1.0, 10.0)
#: 4 training origins -> exactly 8 walk-forward validation origins on a
#: 12-origin archive -- guide 8.7's own OOF-diagnostics floor (>=8),
#: not a coincidence: chosen to land exactly on it, disclosed here.
MIN_TRAIN_ORIGINS = 4
MIN_FIT_ORIGINS = 12                 # guide 8.7 "model fit" floor
MIN_OOF_ORIGINS_FOR_DIAGNOSTICS = 8  # guide 8.7 "OOF diagnostics" floor
MIN_OOF_ORIGINS_FOR_TAIL = 20        # guide 8.7 "tail-quantile branch" floor
MIN_SUPPORT_FOR_ELIGIBLE = 2         # reuses FP-04's MIN_SUPPORT_FOR_MODEL_READY verbatim
TAIL_QUANTILE = 0.8                  # guide 8.6's own example: q=0.8
UTILITY_FLOOR_DAILY = 6.4e-05
UTILITY_FLOOR_SOURCE = (
    "configs/minimum_economic_effect.json (reused verbatim): guide 8.6/FP08.5's 'OOS utility/"
    "risk safeguard' names no concrete number anywhere in the guide text -- reusing the lab's "
    "OWN already-registered economic-significance threshold (registered 2026-09-09, before any "
    "FP arm comparison existed) is a disclosed, non-arbitrary choice rather than inventing a "
    "new number for this phase alone")


class SelectorBError(ValueError):
    """A selector-B construction step was internally inconsistent."""


# ---------------------------------------------------------------------------
# Feature engineering (guide 8.2)
# ---------------------------------------------------------------------------

def normalized_value(spec, value) -> float:
    """One parameter's value normalised to [0, 1] by its DECLARED bounds
    (never by whatever the archive happened to sample) -- the same
    declared-bounds discipline selector.schema_distance already enforces
    for pairwise distance, applied here to a single point's own features."""
    if spec.kind == "fixed":
        return 0.0
    if spec.kind in ("categorical", "bool"):
        choices = list(spec.choices) or [False, True]
        try:
            idx = choices.index(value)
        except ValueError as exc:
            raise SelectorBError(f"{spec.name}={value!r} not a declared choice") from exc
        return idx / max(1, len(choices) - 1)
    span = spec.span()
    if span <= 0:
        return 0.0
    if spec.kind == "log":
        return (math.log(float(value)) - math.log(spec.low)) / span
    return (float(value) - float(spec.low)) / span


def normalized_params(schema, params: dict) -> dict:
    active = schema.informative_params(params)
    return {f"norm_{name}": normalized_value(schema.specs[name], params[name])
           for name in sorted(active)}


def load_origin_is_frame(alpha_id: str, origin_cutoff, *, train_memory_days=None):
    """The SAME IS-window frame FP-04 loaded for this origin -- load ONCE
    per origin and reuse across every one of that origin's records/regions
    (a caller iterating many records from the same origin must not reload
    the frame per record)."""
    import pandas as pd

    from ..ra.ra05_market import load_real_bars
    from .checkpoint_search import SYMBOL, TRAIN_MEMORY_DAYS

    train_memory_days = TRAIN_MEMORY_DAYS if train_memory_days is None else train_memory_days
    origin_ts = pd.Timestamp(origin_cutoff, tz="UTC")
    load_start = (origin_ts - pd.Timedelta(days=train_memory_days + 5)).strftime("%Y-%m-%d")
    load_end = origin_ts.strftime("%Y-%m-%d")
    frame, _partitions = load_real_bars(SYMBOL, start=load_start, end=load_end)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    return frame.loc[frame.index < origin_ts]


def is_window_metrics(cache, root, alpha_id: str, record: dict, *, economics,
                      report_level: str | None = "score", producer: str,
                      is_frame=None) -> dict:
    """Re-derive the medoid's OWN in-sample mean_daily_return/daily_sharpe by
    RE-REQUESTING the exact evaluate_candidate call FP-04's forward_comparison
    already made for this record's IS window (same alpha/params/cutoff/
    economics -> identical cache key -> a real cache HIT, never a fresh
    engine computation) -- guide 8.2 wants 'raw IS mean net return' and 'raw
    IS risk metric' as two DISTINCT features, not the engine's own penalized
    search objective (which mixes a trade-count penalty into one scalar and
    is not independently reconcilable -- FP-03/04's own discipline).

    ``is_frame``: pass an already-loaded frame (load_origin_is_frame) when
    scoring many records from the SAME origin, to avoid reloading it per
    record; omitted, this loads it itself (standalone/test convenience)."""
    import pandas as pd

    from . import evaluator as ev
    from .forward_comparison import window_metrics

    if is_frame is None:
        is_frame = load_origin_is_frame(alpha_id, record["origin_cutoff"])
    origin_ts = pd.Timestamp(record["origin_cutoff"], tz="UTC")
    payload, event = ev.evaluate_candidate(cache, root, alpha_id, is_frame, record["params"],
                                           cutoff=origin_ts, report_level=report_level,
                                           economics=economics, producer=producer)
    metrics = window_metrics(payload, is_frame, initial_capital=economics["initial_capital"])
    sharpe = metrics["daily_sharpe"]
    return {
        "is_mean_daily_return": metrics["mean_daily_return"],
        "is_daily_sharpe": sharpe["value"] if sharpe["status"] == "OK" else None,
        "is_daily_sharpe_status": sharpe["status"],
        "activity_entries": float(payload["trial_scalar"]["entries"]),
        "cache_event_status": event["status"],
    }


def build_feature_row(cache, root, alpha_id: str, schema, record: dict, region: dict, *,
                      economics, producer: str, is_frame=None) -> dict:
    """One row: guide 8.2's six feature categories for ONE matured record,
    plus the label/provenance a caller needs (never candidate ID, absolute
    future dates, or post-OOS diagnostics AS features -- guide 8.2's own
    prohibition; record_id/origin_cutoff are carried as METADATA, not fed
    into the model matrix). Pass ``is_frame`` (load_origin_is_frame) when
    building many rows from the same origin."""
    is_metrics = is_window_metrics(cache, root, alpha_id, record, economics=economics,
                                   producer=producer, is_frame=is_frame)
    is_quality = region["is_quality_distribution"]
    row = {
        **normalized_params(schema, region["medoid_params"]),
        "is_mean_daily_return": is_metrics["is_mean_daily_return"],
        "is_daily_sharpe": is_metrics["is_daily_sharpe"],
        "is_daily_sharpe_status": is_metrics["is_daily_sharpe_status"],
        "region_support_within_origin": float(region["historical_support_within_origin"]),
        "behavioral_diversity_mean_pairwise_distance":
            float(region["behavioral_diversity_mean_pairwise_distance"]),
        "is_objective_spread": float(is_quality["max"] - is_quality["min"]),
        "activity_entries": is_metrics["activity_entries"],
    }
    for name in FEATURE_NAMES:
        if name not in row:
            raise SelectorBError(f"build_feature_row did not populate declared feature {name!r}")
    row.update({"record_id": record["record_id"], "origin_cutoff": record["origin_cutoff"],
               "origin_time": record["origin_time"], "label": record["label"],
               "label_available_at": record["label_available_at"],
               "maturity_state": record["maturity_state"], "params": region["medoid_params"],
               "medoid_trial_id": region["medoid_trial_id"], "region_id": region["region_id"]})
    return row


def build_feature_matrix(rows: list[dict]):
    """rows -> (X, y, weights, names). Rows missing a usable label or any
    non-finite feature are EXCLUDED with a reason, never imputed."""
    import numpy as np

    from .forward_ledger import origin_weights

    weights_by_record = origin_weights(rows)
    kept, excluded = [], []
    for row in rows:
        if row["label"] is None:
            excluded.append({"record_id": row["record_id"], "reason": "label is None"})
            continue
        values = [row[name] for name in FEATURE_NAMES]
        if any(v is None for v in values):
            excluded.append({"record_id": row["record_id"],
                            "reason": f"a feature is None: "
                            f"{[n for n, v in zip(FEATURE_NAMES, values) if v is None]}"})
            continue
        if not all(math.isfinite(float(v)) for v in values):
            excluded.append({"record_id": row["record_id"], "reason": "a feature is non-finite"})
            continue
        kept.append(row)
    X = np.array([[float(row[name]) for name in FEATURE_NAMES] for row in kept], dtype=float)
    y = np.array([float(row["label"]) for row in kept], dtype=float)
    w = np.array([weights_by_record[row["record_id"]] for row in kept], dtype=float)
    return X, y, w, list(FEATURE_NAMES), kept, excluded


# ---------------------------------------------------------------------------
# Ridge regression -- closed form, numpy only (guide 8.3)
# ---------------------------------------------------------------------------

def fit_ridge(X, y, sample_weight, alpha: float) -> dict:
    """Weighted ridge: standardise X (mean/std fit on THIS X only -- a
    caller must never pass validation rows in here), intercept via a
    de-meaned y (never penalised), closed-form solve.

    w* = (X'WX + alpha*I)^-1 X'Wy   on standardised X, de-meaned y.
    """
    import numpy as np

    n, p = X.shape
    if n == 0:
        raise SelectorBError("fit_ridge: no training rows")
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std_safe = np.where(std > 1e-12, std, 1.0)
    Xs = (X - mean) / std_safe
    w_sum = sample_weight.sum()
    if w_sum <= 0:
        raise SelectorBError("fit_ridge: non-positive total sample weight")
    y_mean = float((sample_weight * y).sum() / w_sum)
    yc = y - y_mean
    W = np.diag(sample_weight)
    A = Xs.T @ W @ Xs + alpha * np.eye(p)
    b = Xs.T @ W @ yc
    coef = np.linalg.solve(A, b)
    return {"schema": "regime_lab.fp05_ridge_model.v1", "coef": coef.tolist(),
           "intercept": y_mean, "feature_mean": mean.tolist(), "feature_std": std_safe.tolist(),
           "alpha": alpha, "n_train": int(n), "feature_names": list(FEATURE_NAMES)}


def predict_ridge(model: dict, X):
    import numpy as np

    Xs = (np.asarray(X, dtype=float) - np.array(model["feature_mean"])) / \
        np.array(model["feature_std"])
    return Xs @ np.array(model["coef"]) + model["intercept"]


# ---------------------------------------------------------------------------
# Chronological walk-forward OOF (guide 8.3/8.4, reuses fp.forward_ledger /
# fp.chronology verbatim -- never a second chronology guard)
# ---------------------------------------------------------------------------

def walk_forward_oof(rows: list[dict], *, min_train_origins: int = MIN_TRAIN_ORIGINS,
                     alpha_grid=ALPHA_GRID) -> dict:
    """One fold per validation origin (sorted chronologically, from
    min_train_origins onward): training rows are exactly those a
    fp.forward_ledger.training_view call would accept at that origin's own
    decision time -- the SAME guard FP-04 already proved catches a future-
    label leak (guide 8.4's dormant-risk regression). Returns, per alpha,
    every fold's (record_id, predicted, actual, residual) plus the
    aggregate weighted MSE used to select alpha."""
    import numpy as np

    from .forward_ledger import origin_weights, training_view

    origins = sorted({row["origin_cutoff"] for row in rows},
                     key=lambda o: rows_by_origin_time(rows, o))
    if len(origins) < min_train_origins + 1:
        return {"schema": "regime_lab.fp05_oof.v1", "folds": [], "n_validation_origins": 0,
               "by_alpha": {}, "insufficient": True,
               "reason": f"only {len(origins)} distinct origins, need at least "
               f"{min_train_origins + 1} for one walk-forward fold"}

    folds_by_alpha = {alpha: [] for alpha in alpha_grid}
    validation_origins = []
    for i in range(min_train_origins, len(origins)):
        val_origin = origins[i]
        decision_time = next(r["origin_time"] for r in rows if r["origin_cutoff"] == val_origin)
        train_rows = training_view(rows, decision_time=decision_time)["usable"]
        val_rows = [r for r in rows if r["origin_cutoff"] == val_origin and r["label"] is not None]
        if not train_rows or not val_rows:
            continue
        validation_origins.append(val_origin)
        X_tr, y_tr, w_tr, _names, _kept_tr, _exc_tr = build_feature_matrix(train_rows)
        X_va, y_va, _w_va, _names2, kept_va, _exc_va = build_feature_matrix(val_rows)
        if len(X_tr) == 0 or len(X_va) == 0:
            continue
        for alpha in alpha_grid:
            model = fit_ridge(X_tr, y_tr, w_tr, alpha)
            preds = predict_ridge(model, X_va)
            for row, pred, actual in zip(kept_va, preds, y_va):
                folds_by_alpha[alpha].append({
                    "record_id": row["record_id"], "origin_cutoff": val_origin,
                    "predicted": float(pred), "actual": float(actual),
                    "residual": float(actual - pred),
                })
    by_alpha = {}
    for alpha, rows_out in folds_by_alpha.items():
        if not rows_out:
            by_alpha[str(alpha)] = {"n": 0, "weighted_mse": None}
            continue
        origin_w = origin_weights([{"record_id": r["record_id"], "origin_cutoff": r["origin_cutoff"]}
                                   for r in rows_out_dedup(rows_out)])
        sq_err = np.array([(r["residual"]) ** 2 for r in rows_out])
        w = np.array([origin_w[r["record_id"]] for r in rows_out])
        weighted_mse = float((sq_err * w).sum() / w.sum()) if w.sum() > 0 else None
        by_alpha[str(alpha)] = {"n": len(rows_out), "weighted_mse": weighted_mse}
    return {"schema": "regime_lab.fp05_oof.v1", "folds": folds_by_alpha,
           "n_validation_origins": len(validation_origins),
           "validation_origins": validation_origins, "by_alpha": by_alpha, "insufficient": False}


def rows_by_origin_time(rows: list[dict], origin_cutoff: str) -> str:
    return next(r["origin_time"] for r in rows if r["origin_cutoff"] == origin_cutoff)


def rows_out_dedup(rows_out: list[dict]) -> list[dict]:
    seen = {}
    for r in rows_out:
        seen[r["record_id"]] = r
    return list(seen.values())


def select_alpha(oof_result: dict, alpha_grid=ALPHA_GRID) -> dict:
    """Picks the alpha with the lowest aggregate weighted OOF MSE -- never
    by in-sample fit (guide 17: 'khong dung training fit quality lam
    predictive evidence')."""
    if oof_result.get("insufficient"):
        return {"selected_alpha": None, "reason": oof_result["reason"]}
    scored = [(alpha, oof_result["by_alpha"][str(alpha)]["weighted_mse"]) for alpha in alpha_grid]
    scored = [(a, m) for a, m in scored if m is not None]
    if not scored:
        return {"selected_alpha": None, "reason": "no alpha produced any OOF prediction"}
    best_alpha, best_mse = min(scored, key=lambda pair: pair[1])
    return {"selected_alpha": best_alpha, "oof_weighted_mse": best_mse,
           "all_scores": {str(a): m for a, m in scored}}


# ---------------------------------------------------------------------------
# Decay-risk branch (guide 8.5/8.6/8.7)
# ---------------------------------------------------------------------------

def decay_risk_branch(n_oof_origins: int, *, n_fit_origins: int,
                      tail_min: int = MIN_OOF_ORIGINS_FOR_TAIL,
                      diag_min: int = MIN_OOF_ORIGINS_FOR_DIAGNOSTICS,
                      fit_min: int = MIN_FIT_ORIGINS) -> dict:
    """Guide 8.6's three branches, chosen from MEASURED origin counts, never
    asserted: TAIL_QUANTILE only with >=20 distinct OOF origins;
    MEAN_DECAY (registered fallback, TAIL_ESTIMATE_UNSUPPORTED) with enough
    fit support but not enough tail support; FALLBACK_STOCK_INCUMBENT when
    even the fit floor (>=12 origins) is not met."""
    if n_fit_origins < fit_min:
        return {"branch": "FALLBACK_STOCK_INCUMBENT",
               "reason": f"only {n_fit_origins} distinct matured origins, need >= {fit_min} "
               "for a model fit at all (guide 8.7)"}
    if n_oof_origins >= tail_min:
        return {"branch": "TAIL_QUANTILE", "reason": None}
    return {"branch": "MEAN_DECAY",
           "reason": f"TAIL_ESTIMATE_UNSUPPORTED: only {n_oof_origins} distinct OOF origins, "
           f"need >= {tail_min} for the tail-quantile branch (guide 8.7); "
           f"{n_fit_origins} >= {fit_min} fit origins and {n_oof_origins} "
           f"{'>=' if n_oof_origins >= diag_min else '<'} {diag_min} OOF-diagnostics origins"}


def decay_risk_score(*, is_mean: float, predicted_forward: float, oof_residuals: list[float],
                     branch: str, quantile: float = TAIL_QUANTILE) -> dict:
    """Guide 8.5's D-tilde-plus construction: perturb the point prediction
    by each historical OOF residual, take max(IS - perturbed, 0), then
    either the MEAN (MEAN_DECAY branch) or a high quantile (TAIL_QUANTILE
    branch) of that distribution -- never a plain point-estimate decay,
    which the guide explicitly forbids calling a confidence measure."""
    import numpy as np

    if branch == "FALLBACK_STOCK_INCUMBENT":
        return {"branch": branch, "score": None, "reason": "no model fit -- stock fallback"}
    if not oof_residuals:
        return {"branch": branch, "score": None, "reason": "no OOF residuals available"}
    perturbed = predicted_forward + np.array(oof_residuals, dtype=float)
    d_plus = np.maximum(is_mean - perturbed, 0.0)
    if branch == "TAIL_QUANTILE":
        score = float(np.quantile(d_plus, quantile))
    elif branch == "MEAN_DECAY":
        score = float(d_plus.mean())
    else:
        raise SelectorBError(f"unknown decay-risk branch {branch!r}")
    return {"branch": branch, "score": score, "n_residuals": len(oof_residuals),
           "quantile": quantile if branch == "TAIL_QUANTILE" else None}


# ---------------------------------------------------------------------------
# Eligibility and ranking (guide 8.6)
# ---------------------------------------------------------------------------

def eligible_candidates(scored: list[dict], *, utility_floor: float = UTILITY_FLOOR_DAILY,
                        support_floor: int = MIN_SUPPORT_FOR_ELIGIBLE) -> list[dict]:
    """Guide 8.6 checks 1-3, in order, each row carrying WHY it was
    filtered -- never a silent drop."""
    out = []
    for row in scored:
        reasons = []
        if row.get("predicted_forward_utility") is None:
            reasons.append("no predicted utility")
        elif row["predicted_forward_utility"] < utility_floor:
            reasons.append(f"predicted utility {row['predicted_forward_utility']:.6f} "
                          f"< floor {utility_floor:.6f}")
        if row.get("region_support_within_origin", 0) < support_floor:
            reasons.append(f"support {row.get('region_support_within_origin')} < "
                          f"floor {support_floor}")
        row = {**row, "eligible": not reasons, "ineligibility_reasons": reasons}
        out.append(row)
    return out


def rank_and_select(eligible_rows: list[dict]) -> dict | None:
    """Among ELIGIBLE rows only: real evaluated medoid maximising
    (predicted utility - decay risk score) -- a disclosed, auditable
    risk-adjusted ranking rule (guide 8.6 mandates the ORDER of checks, not
    a specific ranking formula beyond 'assess decay risk then choose the
    evaluated medoid'). Never invents a point: returns one of the rows
    verbatim, or None if nothing is eligible."""
    candidates = [r for r in eligible_rows if r["eligible"]
                 and r.get("decay_risk_score") is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r["predicted_forward_utility"] - r["decay_risk_score"])
