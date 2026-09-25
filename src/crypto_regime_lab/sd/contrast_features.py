"""SD-02: candidate descriptors z and the contrast vector v (guide SS5.5).

z_{k,theta} = {2-3 schema-normalized effective parameters} + raw IS Sharpe +
one qualified activity/support descriptor. v = phi(z_candidate) - phi(z_anchor),
with phi (a per-feature standardizer with a fixed constant-column-drop rule)
fit ONLY from matured train rows -- never on validation/final rows, never on
the full dataset before the time split.

Reuses ``fp.selector_b.normalized_params`` VERBATIM for the schema-normalized
parameter dims (the same declared-bounds normalization A-SC's own FEATURE_NAMES
already used in FP-05/06) -- not re-derived, so a bound fix there is inherited
automatically rather than silently drifting out of sync.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..fp.selector_b import normalized_params

EXTRA_FEATURE_NAMES = ("is_daily_sharpe", "activity_entries")


class ContrastFeatureError(ValueError):
    """A contrast-feature step was internally inconsistent."""


def raw_feature_row(schema, params: dict, *, is_sharpe: float, activity_entries: int) -> dict:
    """One candidate's raw (pre-standardization) descriptor row. Never
    includes candidate_id, a future label, a source name or an absolute
    later timestamp (guide SS5.5's explicit exclusion list)."""
    row = dict(normalized_params(schema, params))
    row["is_daily_sharpe"] = float(is_sharpe)
    row["activity_entries"] = float(activity_entries)
    return row


@dataclass(frozen=True)
class PhiFit:
    feature_names: tuple    # surviving (non-constant), sorted deterministic
    dropped_names: tuple    # constant-in-train columns, flagged and dropped
    mean: dict
    std: dict
    n_train_rows: int


def fit_phi(rows: list) -> PhiFit:
    """Fit phi's standardizer from matured train rows ONLY. A column with
    zero (or undefined, n<2) train-window variance is DROPPED via a fixed
    rule (guide SS5.5: 'Constant columns duoc flag/drop theo fixed rule'),
    never divided-by-epsilon into a fabricated near-infinite scale."""
    if not rows:
        raise ContrastFeatureError("fit_phi requires at least one matured train row")
    all_names = sorted(set().union(*(set(r) for r in rows)))
    missing = [name for r in rows for name in all_names if name not in r]
    if missing:
        raise ContrastFeatureError("inconsistent feature keys across rows given to fit_phi")
    kept, dropped, mean, std = [], [], {}, {}
    for name in all_names:
        vals = np.array([r[name] for r in rows], dtype=float)
        s = float(vals.std(ddof=1)) if len(vals) > 1 else 0.0
        if not np.isfinite(s) or s <= 0:
            dropped.append(name)
            continue
        kept.append(name)
        mean[name] = float(vals.mean())
        std[name] = s
    if not kept:
        raise ContrastFeatureError("DEGENERATE_FEATURE_GEOMETRY: every candidate feature was "
                                   "constant across the matured train rows")
    return PhiFit(feature_names=tuple(kept), dropped_names=tuple(dropped), mean=mean, std=std,
                 n_train_rows=len(rows))


def phi(fit: PhiFit, row: dict) -> np.ndarray:
    """Standardize one raw feature row into phi's surviving dimensions,
    using the FROZEN train-only mean/std (never re-fit on validation data)."""
    missing = [name for name in fit.feature_names if name not in row]
    if missing:
        raise ContrastFeatureError(f"row missing phi dimensions: {missing}")
    return np.array([(row[name] - fit.mean[name]) / fit.std[name] for name in fit.feature_names])


def contrast_vector(fit: PhiFit, candidate_row: dict, anchor_row: dict) -> np.ndarray:
    """v = phi(candidate) - phi(anchor). v == 0 exactly when candidate_row
    == anchor_row (the anchor's own contrast against itself), which is what
    forces B/C's no-intercept prediction to 0 at the anchor by construction."""
    return phi(fit, candidate_row) - phi(fit, anchor_row)
