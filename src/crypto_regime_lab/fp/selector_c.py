"""FP-06 -- Selector C: Selector B PLUS a frozen context family, added in
the right place (guide section 9 / section 18).

Guide 9.1 is a hard constraint enforced structurally here, not just by
convention: candidate pool, base descriptors, target, estimator family,
inner split policy, regularization-selection rule, support/fallback
semantics, economics and timing all stay IDENTICAL to Selector B. The only
thing this module adds is a small, frozen context feature set plus a few
registered candidate-descriptor x context interactions. Concretely:
fp.selector_b.walk_forward_oof is called with THIS module's own
feature-matrix builder passed in as ``feature_matrix_fn`` -- B and C run
through the literal same walk-forward loop and the literal same
fp.forward_ledger.training_view chronology guard, never two similar-looking
copies.

Guide 9.2's own counterexample is why interactions exist at all: a purely
additive model mu_hat(theta, x) = f(theta) + g(x) adds the SAME g(x) to
every candidate at a cutoff, so it can shift the overall predicted level
but can never change which candidate ranks best there. To let context
actually condition candidate advantage, C needs
mu_hat(theta, x) = f(z_theta) + g(x) + h(z_theta, x) -- a few registered
interaction terms, never the full Cartesian product of every base feature
against every context feature (guide 9.2's explicit prohibition).

Context features (guide 9.3's own suggested categories, JM/M0 explicitly
NOT used in this v1 -- LAB-08's own measured history found JM/M0 state
support too thin to build on, only 1.64% of scoring observations carried a
calibration-vintage state key; a disclosed choice, not a silent omission,
guide 9.4 still requires the exposure count to be recorded, at zero):

  * ``ctx_direction_efficiency`` -- signed net price change / summed
    absolute bar-to-bar change over a recent lookback: +-1, trend vs chop.
  * ``ctx_volatility_ratio`` -- short-window realized vol / long-window
    realized vol: >1 means recently more volatile than the training-memory
    norm.

Both are computed from the SAME causal IS frame fp.selector_b already
loads per origin (frame.index < origin_cutoff by construction) -- guide
9.6's 'no realized future regime in selection' is satisfied structurally,
not by convention, and proved by a real future-mutation test.
"""
from __future__ import annotations

CONTEXT_FEATURE_NAMES = ("ctx_direction_efficiency", "ctx_volatility_ratio")

#: Frozen BEFORE any real fit (guide 18 task 7: freeze the context family
#: before FP-07). Each pair has a stated, non-arbitrary rationale -- 2 of
#: the possible 3x2=6 candidate-descriptor x context crossings, never the
#: full Cartesian product (guide 9.2's explicit prohibition).
INTERACTION_SPECS = (
    ("norm_AP", "ctx_direction_efficiency",
     "AP is a lookback/period parameter; a shorter/longer effective lookback "
     "plausibly behaves differently in a trending vs. choppy market"),
    ("norm_coeff", "ctx_volatility_ratio",
     "coeff scales signal sensitivity; plausibly interacts with whether "
     "recent volatility is elevated relative to the training-memory norm"),
)

DIRECTION_LOOKBACK_DAYS = 30
VOL_SHORT_DAYS = 30
VOL_LONG_DAYS = 180   # matches fp.checkpoint_search.TRAIN_MEMORY_DAYS


def _interaction_name(a: str, b: str) -> str:
    return f"interact_{a}_x_{b}"


def c_feature_names():
    from . import selector_b as sb

    return (list(sb.FEATURE_NAMES) + list(CONTEXT_FEATURE_NAMES)
           + [_interaction_name(a, b) for a, b, _reason in INTERACTION_SPECS])


class SelectorCError(ValueError):
    """A Selector C construction step was internally inconsistent."""


# ---------------------------------------------------------------------------
# Context features (guide 9.3), computed from the SAME causal IS frame
# ---------------------------------------------------------------------------

def compute_context_features(is_frame) -> dict:
    """Both features read ONLY bars strictly before origin_cutoff (is_frame
    is already sliced that way by fp.selector_b.load_origin_is_frame) --
    guide 9.6's 'no realized future regime in selection', by construction."""
    closes = is_frame["close"]
    bars_per_day = 1440   # 1-minute bars
    recent = closes.tail(DIRECTION_LOOKBACK_DAYS * bars_per_day)
    if len(recent) < 2:
        raise SelectorCError("is_frame too short for the direction-efficiency lookback")
    net_change = float(recent.iloc[-1] - recent.iloc[0])
    total_abs_change = float(recent.diff().abs().sum())
    direction_efficiency = net_change / total_abs_change if total_abs_change > 0 else 0.0

    returns = closes.pct_change().dropna()
    short = returns.tail(VOL_SHORT_DAYS * bars_per_day)
    long_ = returns.tail(VOL_LONG_DAYS * bars_per_day)
    if len(short) < 2 or len(long_) < 2:
        raise SelectorCError("is_frame too short for the volatility-ratio lookback")
    vol_short, vol_long = float(short.std()), float(long_.std())
    volatility_ratio = vol_short / vol_long if vol_long > 0 else 1.0
    return {"ctx_direction_efficiency": direction_efficiency,
           "ctx_volatility_ratio": volatility_ratio}


def build_c_row(b_row: dict, context: dict) -> dict:
    """Extends one of Selector B's own feature rows with context +
    registered interactions -- never a second base-feature computation
    (guide 9.1: base descriptors stay identical)."""
    row = {**b_row, **context}
    for a, b, _reason in INTERACTION_SPECS:
        row[_interaction_name(a, b)] = row[a] * row[b]
    return row


def build_c_feature_matrix(rows: list[dict]):
    """Same exclusion discipline as fp.selector_b.build_feature_matrix
    (None label/feature excluded with a reason, equal per-origin weight),
    over C_FEATURE_NAMES instead of B's FEATURE_NAMES."""
    import math

    import numpy as np

    from .forward_ledger import origin_weights

    names = c_feature_names()
    weights_by_record = origin_weights(rows)
    kept, excluded = [], []
    for row in rows:
        if row.get("label") is None:
            excluded.append({"record_id": row["record_id"], "reason": "label is None"})
            continue
        values = [row.get(name) for name in names]
        if any(v is None for v in values):
            excluded.append({"record_id": row["record_id"],
                            "reason": f"a feature is None: "
                            f"{[n for n, v in zip(names, values) if v is None]}"})
            continue
        if not all(math.isfinite(float(v)) for v in values):
            excluded.append({"record_id": row["record_id"], "reason": "a feature is non-finite"})
            continue
        kept.append(row)
    X = np.array([[float(row[name]) for name in names] for row in kept], dtype=float)
    y = np.array([float(row["label"]) for row in kept], dtype=float)
    w = np.array([weights_by_record[row["record_id"]] for row in kept], dtype=float)
    return X, y, w, names, kept, excluded


# ---------------------------------------------------------------------------
# OOD / support check + fallback to B (guide 18 task 6)
# ---------------------------------------------------------------------------

def context_support_bounds(train_rows: list[dict]) -> dict:
    """min/max of each context feature over TRAINING rows only -- the OOD
    reference is fit_from_past_only, same discipline as guide 8.4."""
    bounds = {}
    for name in CONTEXT_FEATURE_NAMES:
        values = [r[name] for r in train_rows if r.get(name) is not None]
        if not values:
            bounds[name] = None
            continue
        bounds[name] = {"min": min(values), "max": max(values)}
    return bounds


def is_context_ood(row: dict, bounds: dict) -> tuple[bool, list[str]]:
    reasons = []
    for name in CONTEXT_FEATURE_NAMES:
        b = bounds.get(name)
        value = row.get(name)
        if b is None or value is None:
            reasons.append(f"{name}: no training support to compare against")
            continue
        if value < b["min"] or value > b["max"]:
            reasons.append(f"{name}={value:.6f} outside training range "
                           f"[{b['min']:.6f}, {b['max']:.6f}]")
    return bool(reasons), reasons


def predict_c_or_fallback(*, c_model: dict, b_model: dict, row: dict, bounds: dict) -> dict:
    """Guide 18 task 6: an OOD/unsupported context candidate falls back to
    Selector B's OWN prediction (fit without context) rather than an
    unsupported context-conditioned one -- guide 9.5's 'C fallback gần như
    toàn bộ về B' claim level exists precisely so this is never hidden."""
    from . import selector_b as sb

    ood, reasons = is_context_ood(row, bounds)
    if ood:
        X_b = [[row[name] for name in sb.FEATURE_NAMES]]
        pred = float(sb.predict_ridge(b_model, X_b)[0])
        return {"predicted_forward_utility": pred, "source": "FALLBACK_TO_B",
               "fallback_reasons": reasons}
    names = c_feature_names()
    X_c = [[row[name] for name in names]]
    pred = float(predict_ridge_c(c_model, X_c)[0])
    return {"predicted_forward_utility": pred, "source": "CONTEXT_CONDITIONED",
           "fallback_reasons": []}


# ---------------------------------------------------------------------------
# Ridge fit/predict -- reuses fp.selector_b's own closed-form implementation
# verbatim (guide 9.1: estimator family stays identical), just over the
# wider C feature matrix.
# ---------------------------------------------------------------------------

def fit_ridge_c(X, y, sample_weight, alpha: float) -> dict:
    from . import selector_b as sb

    model = sb.fit_ridge(X, y, sample_weight, alpha)
    return {**model, "schema": "regime_lab.fp06_ridge_c_model.v1",
           "feature_names": c_feature_names()}


def predict_ridge_c(model: dict, X):
    from . import selector_b as sb

    return sb.predict_ridge(model, X)


# ---------------------------------------------------------------------------
# Ablation: C - B on the identical candidates (guide FP06-G-ABLATION)
# ---------------------------------------------------------------------------

def ablation_c_minus_b(b_predictions: dict, c_predictions: dict) -> dict:
    """b_predictions/c_predictions: {record_id: predicted_forward_utility}.
    Requires the SAME record_id keys on both sides -- guide FP06-T06 (same
    candidate pool/target/base features) is what makes this a valid,
    same-scope difference rather than an apples-to-oranges comparison."""
    shared = sorted(set(b_predictions) & set(c_predictions))
    only_b = sorted(set(b_predictions) - set(c_predictions))
    only_c = sorted(set(c_predictions) - set(b_predictions))
    diffs = {rid: c_predictions[rid] - b_predictions[rid] for rid in shared}
    return {"schema": "regime_lab.fp06_ablation.v1", "n_shared": len(shared),
           "only_in_b": only_b, "only_in_c": only_c, "diffs": diffs,
           "mean_diff": (sum(diffs.values()) / len(diffs)) if diffs else None}
