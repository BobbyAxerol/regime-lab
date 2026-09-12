"""L07.5 — operational segments, and the length nobody may know yet.

A segment is the stretch during which one parameter version was effective. Its
length is the single most tempting piece of look-ahead in this phase, because it
looks like bookkeeping: writing ``end`` when the segment opens seems tidy, and it
hands any policy reading the tape the answer to "how long will this decision
last".

So ``end`` stays null until a LATER activation exists, and ``open_segment``
returns the one still running with its end still null. The reporting clock is
untouched by any of this: results are daily UTC on one evaluation interval, and
segments are operational decision boundaries only (guide 10.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


class SegmentError(ValueError):
    """Raised when a segment record would leak its own future."""


@dataclass
class Segment:
    segment_id: str
    parameter_version: str
    start: pd.Timestamp
    activation_id: str
    end: pd.Timestamp | None = None
    ended_by_activation_id: str | None = None
    triggered_no_change: bool = False
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.start = pd.Timestamp(self.start)

    @property
    def is_open(self) -> bool:
        return self.end is None

    def length_days(self, *, as_of: Any = None) -> float | None:
        """Length so far. Returns None for an open segment unless asked as-of a time.

        An open segment has no length. Asking "how long, as of now" is a
        different question from "how long was it", and only the first is
        answerable while it runs.
        """
        if self.end is not None:
            return float((self.end - self.start).total_seconds() / 86400.0)
        if as_of is None:
            return None
        return float((pd.Timestamp(as_of) - self.start).total_seconds() / 86400.0)

    def as_record(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "parameter_version": self.parameter_version,
            "activation_id": self.activation_id,
            "start": str(self.start),
            "end": None if self.end is None else str(self.end),
            "ended_by_activation_id": self.ended_by_activation_id,
            "length_days": self.length_days(),
            "is_open": self.is_open,
            "triggered_no_change": self.triggered_no_change,
            "detail": dict(self.detail),
        }


class SegmentLog:
    """Append-only operational segments for one continuous account."""

    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.no_change_triggers: list[dict] = []

    def open_segment(self) -> Segment | None:
        return self.segments[-1] if self.segments and self.segments[-1].is_open else None

    def record_activation(self, *, activation_id: str, parameter_version: str,
                          at: Any) -> Segment:
        """Start a new segment, closing the previous one — only now is its end known."""
        at = pd.Timestamp(at)
        current = self.open_segment()
        if current is not None:
            if at < current.start:
                raise SegmentError(
                    f"activation at {at} precedes the open segment start {current.start}")
            current.end = at
            current.ended_by_activation_id = activation_id
        segment = Segment(segment_id=f"seg-{len(self.segments)}",
                          parameter_version=parameter_version, start=at,
                          activation_id=activation_id)
        self.segments.append(segment)
        return segment

    def record_no_change(self, *, trigger_id: str, at: Any, reason: str) -> dict:
        """A trigger that changed nothing is still a trigger (guide L07.5).

        Dropping them would make the refresh cadence look like the switch rate,
        and the whole point of four clocks is that those are different numbers.
        """
        record = {"trigger_id": trigger_id, "at": str(pd.Timestamp(at)), "reason": reason,
                  "parameter_version_unchanged": True}
        self.no_change_triggers.append(record)
        current = self.open_segment()
        if current is not None:
            current.triggered_no_change = True
        return record

    def assert_no_future_length_used(self, decisions: list[dict]) -> dict:
        """Guard: no decision may carry the length of the segment it sits in.

        Checked by looking for the field rather than by trusting the caller,
        because this is precisely the leak that reads as a harmless join.
        """
        offenders = [d for d in decisions
                     if any(k in d for k in ("segment_length_days", "segment_end",
                                             "segment_total_return"))]
        return {
            "schema": "crypto_regime_lab.segment_lookahead_guard.v1",
            "decisions_checked": len(decisions),
            "offenders": offenders[:5],
            "clean": not offenders,
            "rule": ("a decision may know which segment it is in and how long that segment has "
                     "run SO FAR; it may never know the segment's total length, its end, or its "
                     "total return, none of which exist yet (guide L07.5)"),
        }

    def daily_account_comparison(self, equity: pd.Series) -> dict:
        """T55 — compare on the daily account, never by averaging fold Sharpes.

        Segments have different lengths by construction, so an unweighted mean of
        per-segment Sharpes weights a three-day segment like a three-month one.
        The daily series does not care where the boundaries fell, which is why
        the guide makes it the comparison surface.
        """
        equity = equity.sort_index()
        daily = equity.resample("1D").last().dropna()
        returns = daily.pct_change().dropna()
        # Segment boundaries and the equity index can disagree on tz-awareness --
        # bars are UTC-aware while a boundary written from a plain date is naive.
        # Comparing them raises rather than silently mis-slicing, so they are
        # aligned to the index once, here, instead of at every call site.
        tz = getattr(returns.index, "tz", None)

        def align(value):
            stamp = pd.Timestamp(value)
            if tz is None:
                return stamp.tz_localize(None) if stamp.tzinfo else stamp
            return stamp.tz_localize(tz) if stamp.tzinfo is None else stamp.tz_convert(tz)

        per_segment = []
        for segment in self.segments:
            start = align(segment.start)
            end = align(segment.end) if segment.end is not None else daily.index[-1]
            window = returns.loc[(returns.index >= start) & (returns.index < end)]
            if len(window) < 2:
                per_segment.append({"segment_id": segment.segment_id, "days": int(len(window)),
                                    "sharpe": None, "reason": "fewer than two daily observations"})
                continue
            std = float(window.std(ddof=1))
            per_segment.append({
                "segment_id": segment.segment_id, "days": int(len(window)),
                "sharpe": (float(window.mean() / std * np.sqrt(365.0)) if std > 0 else None),
            })
        scored = [s for s in per_segment if s["sharpe"] is not None]
        daily_std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
        return {
            "schema": "crypto_regime_lab.daily_account_comparison.v1",
            "daily_observations": int(len(returns)),
            "account_daily_sharpe": (float(returns.mean() / daily_std * np.sqrt(365.0))
                                     if daily_std > 0 else None),
            "per_segment_sharpe": per_segment,
            "unweighted_mean_of_segment_sharpes": (
                float(np.mean([s["sharpe"] for s in scored])) if scored else None),
            "segment_day_counts": [s["days"] for s in per_segment],
            "primary_is_the_daily_account": True,
            "why": ("the per-segment numbers are DIAGNOSTIC. Segment lengths differ by "
                    "construction, so their unweighted mean weights a short segment like a long "
                    "one; the daily account series is indifferent to where the boundaries fell "
                    "and is the comparison the guide asks for (T55, guide 10.3)"),
        }

    def as_record(self) -> dict:
        closed = [s for s in self.segments if not s.is_open]
        lengths = [s.length_days() for s in closed]
        return {
            "schema": "crypto_regime_lab.operational_segments.v1",
            "segments": [s.as_record() for s in self.segments],
            "count": len(self.segments),
            "closed": len(closed),
            "open": sum(1 for s in self.segments if s.is_open),
            "no_change_triggers": self.no_change_triggers,
            "no_change_trigger_count": len(self.no_change_triggers),
            "min_length_days": min(lengths) if lengths else None,
            "max_length_days": max(lengths) if lengths else None,
            "open_segment_has_null_end": all(s.end is None for s in self.segments if s.is_open),
            "reporting_clock": "daily UTC on one evaluation interval, unchanged by segmentation",
            "end_rule": ("a segment's end is written only when the NEXT activation exists. While "
                         "it runs its end is null, because its length does not yet exist "
                         "(guide L07.5)"),
        }
