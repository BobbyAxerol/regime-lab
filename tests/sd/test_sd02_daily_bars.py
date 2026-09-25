"""Coverage for sd/daily_bars.py."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from crypto_regime_lab.sd import daily_bars as db


def _synthetic_1m_frame(*, start: str, n_days: int, skip_day_index: int = None) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="UTC")
    rows = []
    for d in range(n_days):
        if skip_day_index is not None and d == skip_day_index:
            continue
        day = start_ts + pd.Timedelta(days=d)
        for m in range(0, 1440, 60):   # sparse but real, one bar/hour is enough for a close
            ts = day + pd.Timedelta(minutes=m)
            close = 100.0 + d + m / 100000.0
            rows.append({"time": ts, "open": close, "high": close, "low": close,
                        "close": close, "volume": 1.0})
    frame = pd.DataFrame(rows).set_index(pd.to_datetime([r["time"] for r in rows], utc=True))
    return frame


def test_daily_closes_one_per_day_uses_last_bar_of_day():
    frame = _synthetic_1m_frame(start="2022-01-01", n_days=5)
    closes = db.daily_closes(frame, start="2022-01-01", end="2022-01-06")
    assert len(closes) == 5
    assert closes[0][0] == "2022-01-01"
    # last bar of day 0 is minute 1380 (23:00) -> close = 100.0 + 0 + 1380/100000
    assert closes[0][1] == pytest.approx(100.0 + 1380 / 100000.0)


def test_daily_closes_raises_on_missing_day_never_forward_fills():
    frame = _synthetic_1m_frame(start="2022-01-01", n_days=5, skip_day_index=2)
    with pytest.raises(db.DailyBarsError, match="missing all 1m bars"):
        db.daily_closes(frame, start="2022-01-01", end="2022-01-06")


def test_daily_closes_raises_on_empty_frame():
    frame = _synthetic_1m_frame(start="2022-01-01", n_days=1)
    with pytest.raises(db.DailyBarsError):
        db.daily_closes(frame, start="2025-01-01", end="2025-01-02")


def test_daily_closes_rejects_bad_range():
    frame = _synthetic_1m_frame(start="2022-01-01", n_days=2)
    with pytest.raises(db.DailyBarsError):
        db.daily_closes(frame, start="2022-01-02", end="2022-01-01")


def test_daily_log_returns_matches_independent_formula():
    closes = [("2022-01-01", 100.0), ("2022-01-02", 110.0), ("2022-01-03", 99.0)]
    returns = db.daily_log_returns(closes)
    assert returns == pytest.approx([math.log(110 / 100), math.log(99 / 110)])


def test_daily_log_returns_requires_at_least_two_closes():
    with pytest.raises(db.DailyBarsError):
        db.daily_log_returns([("2022-01-01", 100.0)])


def test_daily_log_returns_rejects_non_positive_close():
    with pytest.raises(db.DailyBarsError):
        db.daily_log_returns([("2022-01-01", 100.0), ("2022-01-02", 0.0)])
