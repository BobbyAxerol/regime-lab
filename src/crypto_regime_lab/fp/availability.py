"""Guide FP01.2 finding 1: before-evaluation + availability guards.

The audit risk is concrete: development/calibration inputs that sit OUTSIDE
the evaluation window but IN THE FUTURE can silently steer a calibration yet
would have been unavailable at the decision time. RA-05's CAL_MATCHED forecast
happened to use a disjoint development prefix (D02 proved mutating in-window
emissions changes nothing), but no reusable guard forced that -- a new FP
calibration path could have reintroduced the leak without a red line.

This module is that guard: a calibration that does not declare its evaluation
boundary cannot be checked; one that does refuses future inputs and reports
exactly what it excluded.
"""
from __future__ import annotations

import pandas as pd


class ChronologyViolation(ValueError):
    """A use-after/publication-after relationship is required; none held."""


def development_prefix(records, *, evaluation_start, timestamp_field: str = "timestamp") -> dict:
    """Split ``records`` into the usable development prefix and the excluded tail.

    Only records STRICTLY before ``evaluation_start`` may feed a calibration
    made for that evaluation. The tail is not truncated silently: its length
    and earliest timestamp are reported, and a requested split with NO usable
    prefix is an error rather than an empty-profile decision.
    """
    boundary = pd.Timestamp(evaluation_start)
    prefix, excluded = [], []
    for record in records:
        moment = pd.Timestamp(record[timestamp_field])
        (excluded if moment >= boundary else prefix).append(record)
    if not prefix:
        raise ChronologyViolation(
            f"no development record before evaluation_start={boundary.isoformat()}; "
            "refusing to calibrate on an empty prefix")
    return {
        "schema": "regime_lab.fp_development_prefix.v1",
        "evaluation_start": boundary.isoformat(),
        "records": prefix,
        "n_prefix": len(prefix),
        "n_excluded_tail": len(excluded),
        "earliest_excluded": (pd.Timestamp(excluded[0][timestamp_field]).isoformat()
                              if excluded else None),
    }


def assert_available(records, *, decision_time,
                     availability_field: str = "available_at") -> dict:
    """Refuse (raise) when any record used for a decision was published at or
    after the decision time. Uniformly-naive and uniformly-tz-aware mixes are
    coerced to UTC; a missing or unparsable availability field is a refusal,
    not an assumption of availability.
    """
    moment = pd.Timestamp(decision_time)
    checked = 0
    for record in records:
        try:
            published = pd.Timestamp(record[availability_field])
        except (KeyError, TypeError, ValueError) as exc:
            raise ChronologyViolation(
                f"record without a usable {availability_field!r} cannot be proven "
                f"available at {moment.isoformat()}") from exc
        if published >= moment:
            raise ChronologyViolation(
                f"record published {published.isoformat()} is not available at "
                f"decision time {moment.isoformat()}")
        checked += 1
    return {"schema": "regime_lab.fp_availability_check.v1",
            "decision_time": moment.isoformat(), "n_checked": checked,
            "status": "ALL_AVAILABLE"}


def window_dwell_profile(records, *, evaluation_start,
                         timestamp_field: str = "timestamp") -> dict:
    """The cadence statistic an FP CAL_MATCHED-style calibration consumes.

    The evaluation boundary is mandatory precisely so the before-evaluation
    use can be checked: only strictly-before-boundary emissions enter the
    profile, and the tail accounting rides along in the same artifact.
    """
    split = development_prefix(records, evaluation_start=evaluation_start,
                               timestamp_field=timestamp_field)
    ordered = sorted(pd.Timestamp(r[timestamp_field]) for r in split["records"])
    gaps = [(ordered[i] - ordered[i - 1]).total_seconds() / 86400.0
            for i in range(1, len(ordered))]
    return {
        "schema": "regime_lab.fp_window_dwell_profile.v1",
        "evaluation_start": split["evaluation_start"],
        "n_events": len(ordered),
        "first_event": ordered[0].isoformat(),
        "last_event": ordered[-1].isoformat(),
        "mean_gap_days": (sum(gaps) / len(gaps)) if gaps else None,
        "n_excluded_tail": split["n_excluded_tail"],
        "earliest_excluded": split["earliest_excluded"],
        "rate_per_day": (((len(ordered) - 1) / gaps_total(gaps))
                         if gaps and gaps_total(gaps) > 0 else None),
    }


def gaps_total(gaps) -> float:
    """Sum of inter-event gaps in days; zero when fewer than two events."""
    return sum(gaps) if gaps else 0.0
