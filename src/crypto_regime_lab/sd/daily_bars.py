"""SD-02: real daily UTC closes from real 1-minute bars (guide SS5.2's
"Observation daily UTC, chi completed bars").

A dedicated, gap-checked extractor -- never quantbt's own
``resample("1D").last().ffill()`` (the SAME silent forward-fill failure mode
``sd/metrics.py``'s own docstring already names and avoids for equity), and
never pandas' bare ``resample().last()`` either, since that ALSO silently
forward-carries a missing day's row as NaN or as the prior bar without
raising. Every calendar day in the requested range must have at least one
real 1m bar, or this module raises rather than interpolating.
"""
from __future__ import annotations

import pandas as pd


class DailyBarsError(ValueError):
    """Real daily-bar coverage was insufficient or contained a gap."""


def daily_closes(frame: pd.DataFrame, *, start, end) -> list:
    """One (date_str, close) pair per UTC calendar day in [start, end),
    using that day's own LAST completed 1m bar. Raises DailyBarsError on
    any day with zero real bars -- never forward-fills, never interpolates,
    never silently skips a day (which would corrupt every downstream
    rolling-window feature by shifting its true dates)."""
    start_ts, end_ts = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    if end_ts <= start_ts:
        raise DailyBarsError(f"end {end} must be strictly after start {start}")
    windowed = frame.loc[(frame.index >= start_ts) & (frame.index < end_ts)]
    if windowed.empty:
        raise DailyBarsError(f"no 1m bars at all in [{start}, {end})")
    expected_days = pd.date_range(start_ts, end_ts, freq="D", inclusive="left")
    out = []
    for day in expected_days:
        day_end = day + pd.Timedelta(days=1)
        day_bars = windowed.loc[(windowed.index >= day) & (windowed.index < day_end)]
        if day_bars.empty:
            raise DailyBarsError(f"missing all 1m bars for calendar day {day.date()} -- "
                                 "refusing to forward-fill or skip")
        out.append((day.strftime("%Y-%m-%d"), float(day_bars["close"].iloc[-1])))
    return out


def daily_log_returns(closes: list) -> list:
    """log(close_t / close_{t-1}) for each consecutive pair. len(returns) ==
    len(closes) - 1 -- callers needing N returns must request N+1 closes."""
    import math

    if len(closes) < 2:
        raise DailyBarsError(f"need >= 2 closes to derive a return, got {len(closes)}")
    values = [c for _, c in closes]
    if any(v <= 0 for v in values):
        raise DailyBarsError("non-positive close encountered -- cannot take log return")
    return [math.log(values[i] / values[i - 1]) for i in range(1, len(values))]
