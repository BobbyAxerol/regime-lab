"""L09.3 — paired uncertainty that keeps the structure the data actually has.

Three properties the guide (11.3, T63) asks for, and what each one costs if it is
dropped:

  * PAIRED. Two arms are compared day by day on the days both were live. An
    unpaired comparison of means lets a difference in which days each arm traded
    masquerade as a difference in how well it traded.
  * BLOCKED. Days are resampled in contiguous runs, never one at a time. Daily
    crypto returns are autocorrelated and volatility clusters; an iid bootstrap
    destroys both and returns an interval far too narrow.
  * COMMON. Every cell is resampled on the SAME dates. Five symbols in one market
    move together, and resampling them independently manufactures diversification
    that does not exist -- the interval shrinks by roughly sqrt(5) for free.

Nothing here chooses its own block length from the data it is about to test: the
length comes from the development series and is applied to the confirmation one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class UncertaintyError(RuntimeError):
    """Raised when an inference would be computed over structure that is not there."""


def autocorrelation(values: np.ndarray, max_lag: int) -> list[float]:
    """Sample autocorrelation of a mean-removed series, lags 1..max_lag."""
    series = np.asarray(values, dtype=float)
    series = series - series.mean()
    denominator = float(series @ series)
    if denominator <= 0:
        return [0.0] * max_lag
    return [float(series[lag:] @ series[:-lag] / denominator)
            for lag in range(1, max_lag + 1)]


def choose_block_length(values: np.ndarray, *, max_lag: int = 60) -> dict:
    """The first lag whose autocorrelation falls inside the +-2/sqrt(n) band.

    A block has to be long enough to carry the dependence it is meant to
    preserve; past that it only costs resolution. The rule is fixed here and run
    on DEVELOPMENT data, so the confirmation interval never picks the block
    length that suits its own answer.
    """
    series = np.asarray(values, dtype=float)
    n = len(series)
    if n < 20:
        raise UncertaintyError(f"a block length needs a series, not {n} points")
    lag_cap = int(min(max_lag, max(2, n // 4)))
    acf = autocorrelation(series, lag_cap)
    band = 2.0 / np.sqrt(n)
    first_inside = next((lag for lag, value in enumerate(acf, start=1)
                         if abs(value) < band), None)
    chosen = int(first_inside) if first_inside else lag_cap
    return {
        "block_length": max(2, chosen),
        "first_lag_inside_band": first_inside,
        "band": float(band),
        "observations": int(n),
        "autocorrelation_lag_1_to_5": [round(v, 6) for v in acf[:5]],
        "rule": ("the first lag at which the sample autocorrelation falls inside +-2/sqrt(n), "
                 "floored at 2. Chosen on development data and applied unchanged to the "
                 "confirmation interval (L09.3.8)"),
    }


def _aligned_matrix(series_by_cell: dict[str, pd.Series]) -> tuple[list[str], pd.DatetimeIndex,
                                                                   np.ndarray]:
    """Cells x dates, on the union calendar, with NaN where a cell was not live."""
    if not series_by_cell:
        raise UncertaintyError("no cell carries a paired daily series")
    names = sorted(series_by_cell)
    frame = pd.DataFrame({name: series_by_cell[name] for name in names}).sort_index()
    return names, frame.index, frame.to_numpy(dtype=float).T


def _blocks(n_dates: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    """One moving-block resample of date POSITIONS, length n_dates."""
    starts = rng.integers(0, n_dates - block_length + 1,
                          size=int(np.ceil(n_dates / block_length)))
    offsets = np.arange(block_length)
    return (starts[:, None] + offsets[None, :]).ravel()[:n_dates]


def paired_block_bootstrap(series_by_cell: dict[str, pd.Series], *, block_length: int,
                           draws: int = 2000, seed: int = 20260911,
                           alpha: float = 0.05) -> dict:
    """Percentile CI for the mean paired daily difference, pooled over cells.

    The point estimate is the mean over cells of each cell's mean paired daily
    difference -- the same statistic the contrast panel reports, so the interval
    belongs to the number it is placed next to.
    """
    names, dates, matrix = _aligned_matrix(series_by_cell)
    n_dates = len(dates)
    if n_dates < 2 * block_length:
        raise UncertaintyError(
            f"{n_dates} dates cannot carry blocks of {block_length}; the interval would be "
            "built from a handful of distinct blocks and would not mean anything")
    rng = np.random.default_rng(seed)

    def statistic(columns: np.ndarray) -> float:
        sample = matrix[:, columns]
        with np.errstate(invalid="ignore"):
            per_cell = np.nanmean(sample, axis=1)
        per_cell = per_cell[~np.isnan(per_cell)]
        return float(per_cell.mean()) if len(per_cell) else np.nan

    point = statistic(np.arange(n_dates))
    values = np.array([statistic(_blocks(n_dates, block_length, rng)) for _ in range(draws)])
    values = values[~np.isnan(values)]
    if len(values) < draws // 2:
        raise UncertaintyError("more than half the bootstrap draws produced no statistic")
    lower, upper = np.quantile(values, [alpha / 2, 1 - alpha / 2])
    share_at_or_below_zero = float((values <= 0).mean())
    p_value = float(min(1.0, 2 * min(share_at_or_below_zero, 1 - share_at_or_below_zero)))
    return {
        "point_estimate": point,
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "confidence": 1 - alpha,
        "p_value": p_value,
        "draws": int(len(values)),
        "block_length_days": int(block_length),
        "dates": int(n_dates),
        "cells": names,
        "cells_pooled": len(names),
        "resampling": ("moving blocks of dates, drawn ONCE per draw and applied to every cell, "
                       "so the cross-sectional dependence between symbols and the common market "
                       "shocks survive the resample (T63)"),
        "statistic_name": "macro-average of per-cell mean paired daily differences",
        "not_a_portfolio": (
            "guide 11.3 forbids averaging cells into an implied portfolio without an explicit "
            "capital allocation and an actual account simulator. There is neither here: each cell "
            "is its own account at its own fixed notional, and this number is a DESCRIPTIVE "
            "macro-average across cells -- not the return of anything anyone could have held"),
        "ci_excludes_zero": bool(lower > 0 or upper < 0),
    }


def concentration(series_by_cell: dict[str, pd.Series]) -> dict:
    """How much of the pooled result comes from how few days.

    Guide 11.4: a result carried by a handful of days is a statement about those
    days. The measure is on the ABSOLUTE contribution, so a large offsetting pair
    counts as concentration rather than cancelling into invisibility.
    """
    names, dates, matrix = _aligned_matrix(series_by_cell)
    del names
    with np.errstate(invalid="ignore"):
        per_day = np.nanmean(matrix, axis=0)
    per_day = pd.Series(per_day, index=dates).dropna()
    if per_day.empty:
        return {"days": 0, "status": "NO_SHARED_DAYS"}
    total = float(per_day.sum())
    magnitude = per_day.abs().sort_values(ascending=False)
    cumulative = magnitude.cumsum() / magnitude.sum()
    out = {
        "days": int(len(per_day)),
        "total": total,
        "top_1_day_share_of_absolute": float(cumulative.iloc[0]),
        "top_5_day_share_of_absolute": float(cumulative.iloc[min(4, len(cumulative) - 1)]),
        "days_for_half_the_absolute_move": int((cumulative < 0.5).sum() + 1),
        "share_of_days_that_are_half_the_move": float(
            ((cumulative < 0.5).sum() + 1) / len(cumulative)),
        "largest_day": {"date": str(magnitude.index[0].date()),
                        "value": float(per_day.loc[magnitude.index[0]])},
        "reading": ("the share of the total ABSOLUTE daily contribution carried by the biggest "
                    "days. A small number of days carrying most of it means the result is about "
                    "those days (guide 11.4)"),
    }
    without_top = per_day.drop(magnitude.index[:5])
    out["mean_without_top_5_days"] = float(without_top.mean()) if len(without_top) else None
    out["mean_with_all_days"] = float(per_day.mean())
    return out


def block_length_sensitivity(series_by_cell: dict[str, pd.Series], *, lengths: tuple[int, ...],
                             draws: int = 800, seed: int = 20260911) -> list[dict]:
    """The same interval at several block lengths (L09.3.8).

    A conclusion that survives only at one block length is a conclusion about the
    block length.
    """
    out = []
    for length in lengths:
        try:
            result = paired_block_bootstrap(series_by_cell, block_length=length,
                                            draws=draws, seed=seed)
        except UncertaintyError as exc:
            out.append({"block_length_days": length, "status": "NOT_COMPUTABLE",
                        "reason": str(exc)})
            continue
        out.append({"block_length_days": length, "status": "OK",
                    "point_estimate": result["point_estimate"],
                    "ci_lower": result["ci_lower"], "ci_upper": result["ci_upper"],
                    "p_value": result["p_value"],
                    "ci_excludes_zero": result["ci_excludes_zero"]})
    return out


def episode_counts(series_by_cell: dict[str, pd.Series]) -> dict:
    """How many days each cell actually contributed, and how many were shared.

    A pooled mean over cells that contributed 20 days and cells that contributed
    900 is not the average of five comparable things, and the counts are the only
    way a reader can see that (L09.3.4).
    """
    names, dates, matrix = _aligned_matrix(series_by_cell)
    live = ~np.isnan(matrix)
    per_cell = {name: int(live[i].sum()) for i, name in enumerate(names)}
    shared = int(live.all(axis=0).sum())
    return {
        "union_days": int(len(dates)),
        "days_all_cells_live": shared,
        "per_cell_days": per_cell,
        "min_cell_days": min(per_cell.values()) if per_cell else 0,
        "max_cell_days": max(per_cell.values()) if per_cell else 0,
        "reading": ("cells contribute unequal numbers of days. The pooled statistic averages "
                    "per-cell means, so a short cell does not get a small vote -- it gets an "
                    "equal one on less evidence"),
    }


def common_period(series_by_cell: dict[str, pd.Series], *,
                  declared: list[str] | None = None) -> dict:
    """Guide 10.4 — is the pooled number a COMMON-period aggregate, or a mixture?

    The clause is specific: report the five-symbol common-period aggregate
    separately from each symbol's longest valid history, and never back-fill a
    return before a symbol listed. A pool whose cells start on different dates is
    the second thing wearing the first thing's name.

    This measures it instead of assuming it. When every cell spans the same
    interval the two aggregates coincide, which is a finding to state rather than
    a detail to skip.
    """
    if not series_by_cell:
        return {"status": "NO_SERIES"}
    spans = {name: (str(series.index.min().date()), str(series.index.max().date()))
             for name, series in series_by_cell.items() if len(series)}
    if not spans:
        return {"status": "NO_SERIES"}
    starts = sorted({span[0] for span in spans.values()})
    ends = sorted({span[1] for span in spans.values()})
    intersection = [max(starts), min(ends)]
    union = [min(starts), max(ends)]
    identical = len(starts) == 1 and len(ends) == 1
    return {
        "status": "MEASURED",
        "cells": len(spans),
        "per_cell_span": spans,
        "distinct_start_dates": starts,
        "distinct_end_dates": ends,
        "common_period": intersection,
        "union_period": union,
        "every_cell_spans_the_same_interval": identical,
        "pooled_statistic_is_a_common_period_aggregate": identical,
        "declared_five_symbol_common_period": declared,
        "window_inside_the_declared_common_period": (
            None if declared is None
            else union[0] >= declared[0][:10] and union[1] <= declared[1][:10]),
        "reading": ("when every cell spans the same interval the common-period aggregate and "
                    "the longest-history aggregate are the same number, and saying so is the "
                    "point. When they differ, the pooled statistic mixes windows and only the "
                    "common-period one is comparable across symbols (guide 10.4)"),
        "zeros_before_listing": ("none: a day a cell was not live is excluded from the pairing, "
                                 "never filled with a zero"),
    }
