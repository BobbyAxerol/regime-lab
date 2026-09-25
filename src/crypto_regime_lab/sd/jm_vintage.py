"""SD-02: causal JM vintage tapes, one per penalty recipe (guide SS5.3-5.4,
SS9.2 SD02.3).

Each origin is refit FRESH from its own raw prehistory (never a final-fit
centroid written back over history -- guide: "khong fit final centroids roi
gan toan INIT"). An origin whose raw prehistory is too short for a FULL
180-observation calibration feature series is recorded with an EXPLICIT,
typed ``INSUFFICIENT_RAW_PREHISTORY`` status and NO fabricated state ID
(guide SD02.3: "Nhung origins unknown giu record, no fabricated state IDs")
-- never a partial/shrunk calibration window standing in for the guide's own
declared default of exactly 180.

Measured against this lab's real, pinned BTCUSDT snapshot (earliest usable
date 2020-01-06, ``configs/sharpe_decay_sd_v1/registration.json``'s own
``data_role_exception.measured_full_interval``): exactly 4 of SD-01's 12
INIT origins (2020-07-04, 2020-08-29, 2020-10-24, 2020-12-19) fall short of
the RAW_PREHISTORY_DAYS requirement; all 12 VALIDATION origins (>= 2022-05-14)
clear it with wide margin.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import jm_features as jf
from . import jm_model as jm
from .daily_bars import DailyBarsError, daily_closes, daily_log_returns

CALIBRATION_DAYS = 180                                             # guide SS5.2
#: raw closes needed before the origin cutoff: 180 (rv_180's own lookback,
#: to give the EARLIEST calibration day a full 180-return rv window) + 180
#: (the calibration window itself) = 360 closes -> 359 raw returns.
RAW_PREHISTORY_DAYS = jf.RV_LONG_DAYS + CALIBRATION_DAYS
EARLIEST_USABLE_DATE = "2020-01-06"   # registration.json's own measured BTCUSDT floor

STATUS_OK = "OK"
STATUS_INSUFFICIENT_PREHISTORY = "INSUFFICIENT_RAW_PREHISTORY"
STATUS_FIT_FAILED = "MODEL_FIT_FAILED"


class VintageError(ValueError):
    """A vintage-tape build step was internally inconsistent."""


@dataclass(frozen=True)
class VintageOriginRecord:
    origin_cutoff: str
    recipe_c: float
    status: str
    state: object            # int state, or None when status != OK
    lambda_j: object
    loss_scale: object
    n_iter: object
    converged: object
    reason: object
    #: raw (non-standardized) log(rv_28/rv_180) at the origin's own last
    #: calibration day -- identical across recipes at a given origin (it is
    #: read straight off the shared z_raw before any recipe-specific fit),
    #: exposed for r_rule.py's OWN causal median-threshold state assignment
    #: so it never has to reload/recompute raw prehistory a second time.
    origin_log_rv_ratio: object = None


def required_prehistory_start(origin_cutoff: str) -> str:
    cutoff = pd.Timestamp(origin_cutoff, tz="UTC")
    return (cutoff - pd.Timedelta(days=RAW_PREHISTORY_DAYS)).strftime("%Y-%m-%d")


def prehistory_shortfall_days(origin_cutoff: str) -> int:
    """>0 iff this origin's raw-prehistory need reaches before the
    registered earliest usable date -- measured, never assumed."""
    needed = pd.Timestamp(required_prehistory_start(origin_cutoff), tz="UTC")
    earliest = pd.Timestamp(EARLIEST_USABLE_DATE, tz="UTC")
    return max(0, (earliest - needed).days)


def build_calibration_feature_matrix(closes: list) -> np.ndarray:
    """``closes``: exactly RAW_PREHISTORY_DAYS + 1 (date, close) pairs,
    ascending, ending the day before the origin cutoff. Returns
    (CALIBRATION_DAYS, 3) via the growing-prefix pattern: for each of the
    last CALIBRATION_DAYS closes, ``jm_features`` functions are handed the
    FULL prefix up to that day and take their own trailing window --
    exactly reproducing what a truly causal online computation would see."""
    expected_len = RAW_PREHISTORY_DAYS
    if len(closes) != expected_len:
        raise VintageError(f"expected exactly {expected_len} raw closes, got {len(closes)}")
    all_returns = daily_log_returns(closes)   # len == RAW_PREHISTORY_DAYS - 1
    rows = []
    for j in range(jf.RV_LONG_DAYS, RAW_PREHISTORY_DAYS):
        row = jf.feature_row(all_returns[:j], [c for _, c in closes[:j + 1]],
                             observed_at=closes[j][0], available_at=closes[j][0])
        rows.append([row[name] for name in jf.FEATURE_NAMES])
    matrix = np.array(rows, dtype=float)
    if matrix.shape != (CALIBRATION_DAYS, len(jf.FEATURE_NAMES)):
        raise VintageError(f"internal shape error: got {matrix.shape}, "
                           f"expected ({CALIBRATION_DAYS}, {len(jf.FEATURE_NAMES)})")
    return matrix


def fit_origin_vintage(load_real_bars_fn, symbol: str, *, origin_cutoff: str, c: float) -> VintageOriginRecord:
    """One origin, one penalty design c. Loads its own real raw prehistory
    fresh (no reuse of a neighboring origin's fit), builds the 180-row
    calibration feature matrix, fits JM K=2, and returns the CAUSAL FILTERED
    terminal state (never the batch-smoothed path -- ``jm_model.fit_jm``'s
    own ``train_terminal_state`` already enforces this)."""
    shortfall = prehistory_shortfall_days(origin_cutoff)
    if shortfall > 0:
        return VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c,
                                   status=STATUS_INSUFFICIENT_PREHISTORY, state=None,
                                   lambda_j=None, loss_scale=None, n_iter=None, converged=None,
                                   reason=f"raw prehistory shortfall of {shortfall} days against "
                                          f"the registered earliest usable date {EARLIEST_USABLE_DATE}")
    prehistory_start = required_prehistory_start(origin_cutoff)
    try:
        frame, _partitions = load_real_bars_fn(symbol, start=prehistory_start, end=origin_cutoff)
        closes = daily_closes(frame, start=prehistory_start, end=origin_cutoff)
    except DailyBarsError as exc:
        return VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c,
                                   status=STATUS_INSUFFICIENT_PREHISTORY, state=None,
                                   lambda_j=None, loss_scale=None, n_iter=None, converged=None,
                                   reason=f"real daily-bar coverage gap: {exc}")
    try:
        z_raw = build_calibration_feature_matrix(closes)
        loss_scale = jm.median_one_centroid_loss_scale(z_raw)
        lambda_j = jm.normalized_lambda(c, loss_scale)
        fit = jm.fit_jm(z_raw, lambda_j=lambda_j, seed=jm.DEFAULT_SEED)
    except (jf.FeatureError, jm.JMError) as exc:
        return VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c, status=STATUS_FIT_FAILED,
                                   state=None, lambda_j=None, loss_scale=None, n_iter=None,
                                   converged=None, reason=str(exc))
    return VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c, status=STATUS_OK,
                               state=fit.train_terminal_state, lambda_j=lambda_j,
                               loss_scale=loss_scale, n_iter=fit.n_iter, converged=fit.converged,
                               reason=None, origin_log_rv_ratio=float(z_raw[-1][0]))


def build_vintage_tape(load_real_bars_fn, symbol: str, origins: list, *, c: float) -> list:
    """The immutable, per-origin, per-recipe causal tape (guide SD02.3):
    one independent fit call per origin, in chronological order, but each
    origin's own record is NEVER overwritten by a later origin's fit."""
    return [fit_origin_vintage(load_real_bars_fn, symbol, origin_cutoff=o, c=c) for o in origins]


def fit_all_recipes_at_origin(load_real_bars_fn, symbol: str, *, origin_cutoff: str,
                              recipes: tuple = jm.NORMALIZED_PENALTIES) -> dict:
    """All penalty designs for ONE origin, loading the raw prehistory (and
    building the calibration feature matrix) exactly ONCE and reusing it for
    every recipe -- the z_raw feature matrix is IDENTICAL across recipes (only
    lambda_j differs), so this guarantees byte-identical input across designs
    at this origin AND avoids redundant real I/O against the pinned parquet
    snapshot. Returns {c: VintageOriginRecord}."""
    shortfall = prehistory_shortfall_days(origin_cutoff)
    if shortfall > 0:
        reason = (f"raw prehistory shortfall of {shortfall} days against the registered "
                 f"earliest usable date {EARLIEST_USABLE_DATE}")
        return {c: VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c,
                                       status=STATUS_INSUFFICIENT_PREHISTORY, state=None,
                                       lambda_j=None, loss_scale=None, n_iter=None,
                                       converged=None, reason=reason) for c in recipes}
    prehistory_start = required_prehistory_start(origin_cutoff)
    try:
        frame, _partitions = load_real_bars_fn(symbol, start=prehistory_start, end=origin_cutoff)
        closes = daily_closes(frame, start=prehistory_start, end=origin_cutoff)
        z_raw = build_calibration_feature_matrix(closes)
    except (DailyBarsError, jf.FeatureError, VintageError) as exc:
        reason = f"real daily-bar/feature build failure: {exc}"
        return {c: VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c,
                                       status=STATUS_INSUFFICIENT_PREHISTORY, state=None,
                                       lambda_j=None, loss_scale=None, n_iter=None,
                                       converged=None, reason=reason) for c in recipes}
    out = {}
    origin_log_rv_ratio = float(z_raw[-1][0])
    for c in recipes:
        try:
            loss_scale = jm.median_one_centroid_loss_scale(z_raw)
            lambda_j = jm.normalized_lambda(c, loss_scale)
            fit = jm.fit_jm(z_raw, lambda_j=lambda_j, seed=jm.DEFAULT_SEED)
            out[c] = VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c, status=STATUS_OK,
                                         state=fit.train_terminal_state, lambda_j=lambda_j,
                                         loss_scale=loss_scale, n_iter=fit.n_iter,
                                         converged=fit.converged, reason=None,
                                         origin_log_rv_ratio=origin_log_rv_ratio)
        except jm.JMError as exc:
            out[c] = VintageOriginRecord(origin_cutoff=origin_cutoff, recipe_c=c,
                                         status=STATUS_FIT_FAILED, state=None, lambda_j=None,
                                         loss_scale=None, n_iter=None, converged=None, reason=str(exc))
    return out


def build_vintage_tapes(load_real_bars_fn, symbol: str, origins: list, *,
                        recipes: tuple = jm.NORMALIZED_PENALTIES) -> dict:
    """{c: [VintageOriginRecord, ...]} for every recipe, one data load per
    origin shared across all recipes (see ``fit_all_recipes_at_origin``)."""
    per_origin = [fit_all_recipes_at_origin(load_real_bars_fn, symbol, origin_cutoff=o, recipes=recipes)
                 for o in origins]
    return {c: [rec[c] for rec in per_origin] for c in recipes}
