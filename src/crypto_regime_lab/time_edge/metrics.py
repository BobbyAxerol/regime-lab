"""Post-process engine marks. No accounting, fills or synthetic missing observations."""
import numpy as np
import pandas as pd

from ..experiments.time_edge_contracts import ContractError, daily_returns, daily_sharpe, observation_pf


def checked_series(values, index):
    index = pd.DatetimeIndex(index)
    values = np.asarray(values, dtype=float).reshape(-1)
    if index.tz is None or str(index.tz) != "UTC" or not index.is_monotonic_increasing or index.has_duplicates:
        raise ContractError("unique increasing UTC account index required")
    if len(values) != len(index) or not len(values) or not np.isfinite(values).all():
        raise ContractError("finite complete engine marks required")
    return pd.Series(values, index=index)


def account_returns(equity, index, *, initial_equity, start, end, bar_minutes=1):
    series = checked_series(equity, index)
    # OHLCV timestamps label bar OPEN. A mark belongs to that bar's UTC day.
    expected = pd.date_range(series.index[0], series.index[-1], freq=f"{bar_minutes}min")
    if not series.index.equals(expected):
        raise ContractError("market/account gaps: do not forward-fill engine marks")
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    if series.index[0] > lo or series.index[-1] + pd.Timedelta(minutes=bar_minutes) < hi:
        raise ContractError("incomplete requested account window")
    daily = series.resample("1D").last()
    rows = [(d.isoformat(), float(v)) for d, v in daily.items()]
    return daily_returns(rows, initial_equity=initial_equity, start=lo.isoformat(), end=hi.isoformat())


def describe(rows):
    values = np.asarray([r[1] for r in rows], dtype=float)
    if not len(values) or not np.isfinite(values).all() or (values < -1).any():
        raise ContractError("nonempty valid account returns required")
    curve = np.r_[1., np.cumprod(1 + values)]
    peak = np.maximum.accumulate(curve)
    return {"days": len(values), "mean_daily_return": float(values.mean()),
            "total_return": float(curve[-1]-1),
            "daily_sharpe": daily_sharpe(values.tolist()),
            "daily_observation_pf": observation_pf(values.tolist()),
            "max_drawdown": float(np.max(1-curve/peak)),
            "trade_pf": {"value": None, "reason": "requires engine closed-trade ledger; daily PF is separate"}}


def window_activity(fills, index, equity, *, start, end, initial_equity):
    """Count actual window fills; turnover is absolute notional / pre-bar equity.

    Pre-bar equity is explicitly not pre-fill equity when several fills share a
    bar; it must NOT be used as the economic-threshold calibration denominator.
    """
    idx = pd.DatetimeIndex(index)
    eq = np.asarray(equity, dtype=float)
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    selected = [f for f in fills if lo <= idx[int(f["bar_index"])] < hi]
    turnover = 0.
    for f in selected:
        b = int(f["bar_index"])
        before = initial_equity if b == 0 else eq[b-1]
        if not np.isfinite(before) or before <= 0:
            raise ContractError("invalid activity denominator")
        turnover += abs(float(f["qty"])*float(f["price"]))/before
    return {"fill_count": len(selected), "entry_fill_count": sum(f.get("tag") == "entry" for f in selected),
            "completed_campaign_count": sum(abs(f["position_after"]) <= 1e-9 and abs(f["position_before"]) > 1e-9 for f in selected),
            "turnover": turnover, "turnover_unit": "absolute_fill_notional/pre_bar_equity",
            "fees": sum(float(f["fee"]) for f in selected)}


def materialize_delta(cells, *, expected_cells, cutoff):
    """Freeze the registered cost function using true engine pre-fill equity."""
    if set(cells) != set(expected_cells) or not cells:
        raise ContractError("threshold needs all prespecified calibration cells")
    values = {}
    for cell, record in cells.items():
        dates = pd.DatetimeIndex(pd.to_datetime(record["days"], utc=True))
        if not len(dates) or dates.has_duplicates or not dates.equals(pd.date_range(dates[0], dates[-1], freq="D")):
            raise ContractError("calibration includes every flat calendar day")
        if dates[-1] + pd.Timedelta(days=1) > pd.Timestamp(cutoff):
            raise ContractError("threshold calibration contains evaluation data")
        costs = pd.Series(0., index=dates)
        for fill in record["fills"]:
            day = pd.Timestamp(fill["timestamp"]).floor("D")
            before = float(fill["pre_fill_equity"])
            if day not in costs.index or not np.isfinite(before) or before <= 0:
                raise ContractError("invalid calibration fill/engine pre-fill equity")
            costs.loc[day] += abs(float(fill["notional"]))/before*.0005
        values[cell] = float(costs.mean())
    delta = max(values.values())
    if not np.isfinite(delta) or delta <= 0:
        raise ContractError("absent/zero economic threshold blocks claims")
    return {"value": delta, "unit": "account_return/day", "per_cell": values,
            "calibration_cutoff": cutoff, "formula": "max_cell(mean_day(sum_fill(abs(notional)/pre_fill_equity*0.0005)))"}
