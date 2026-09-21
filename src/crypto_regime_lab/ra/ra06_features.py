"""RA06.5 feature computation for the AGE_ONLY/AGE_CONTEXT ladder (guide
section 10.5's suggested list: age, distance/context, volatility/
persistence, trailing performance -- not all mandatory, a small disclosed
subset used here).

Every feature is computed CAUSALLY (only data strictly before the origin)
and CHEAPLY (no optimizer call, no new engine run) so the deployment
controller (ra06_controller.py) can score them before deciding whether a
real search is worth requesting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _utc(value) -> pd.Timestamp:
    """Every timestamp this module compares must be explicit-UTC -- origins
    come out of `ra06_origins.select_origins` already tz-aware, but a bare
    date string like window_start parses tz-naive, and mixing the two raises
    (caught by the RA-06 --smoke dry run before it reached the real run)."""
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def age_days(origin: str, incumbent_selected_at: str) -> float:
    return (_utc(origin) - _utc(incumbent_selected_at)).total_seconds() / 86400.0


def realized_vol(frame: pd.DataFrame, *, at: str, lookback_days: int = 20) -> float:
    """Trailing close-to-close realized volatility strictly before `at` --
    causal by construction (the window ends at `at`, exclusive)."""
    end = _utc(at)
    start = end - pd.Timedelta(days=lookback_days)
    window = frame.loc[(frame.index >= start) & (frame.index < end), "close"]
    if len(window) < 2:
        return None
    log_returns = np.diff(np.log(window.to_numpy()))
    if len(log_returns) < 2:
        return None
    return float(np.std(log_returns, ddof=1))


def regime_transitions_since(emissions: list[dict], *, since: str, until: str) -> int:
    """Count of real SEMANTIC state changes between `since` (exclusive) and
    `until` (exclusive) -- the same comparable-namespace rule
    `online_trigger_schedule`/`classify_regime_trigger_reasons` use, applied
    here as a raw COUNT (a signed regime-distance proxy), not a trigger
    decision."""
    since_ts, until_ts = _utc(since), _utc(until)
    ordered = sorted(
        (row for row in emissions
         if row.get("decision_eligible", True) and row.get("quality_status", "OK") == "OK"),
        key=lambda row: pd.Timestamp(row["available_at"]))
    count = 0
    previous = None
    for row in ordered:
        at = _utc(row["available_at"])
        common = row.get("state_common")
        namespace = row.get("state_namespace")
        semantic = common if common is not None else row.get("state_id")
        changed = False
        if previous is not None:
            prev_common, prev_namespace, prev_semantic = previous
            comparable = (common is not None and prev_common is not None) or namespace == prev_namespace
            changed = comparable and semantic != prev_semantic
        if changed and since_ts < at < until_ts:
            count += 1
        previous = (common, namespace, semantic)
    return count


def incumbent_trailing_return(equity_daily: list, *, at: str, lookback_days: int = 20):
    """The KEEP branch's OWN real trailing return over [at-lookback, at) --
    "actual trailing strategy performance" (guide 10.5), from the CORRECT
    branch/account (never another policy's)."""
    end = _utc(at)
    start = end - pd.Timedelta(days=lookback_days)
    rows = []
    for date, value in equity_daily:
        stamp = _utc(date)
        if start <= stamp < end:
            rows.append((stamp, value))
    if len(rows) < 2:
        return None
    rows.sort(key=lambda row: row[0])
    first, last = rows[0][1], rows[-1][1]
    if first == 0:
        return None
    return (last / first) - 1.0


def build_origin_features(*, origin: str, window_start: str, frame: pd.DataFrame,
                          emissions: list[dict], keep_equity_daily: list) -> dict:
    return {
        "age_days": age_days(origin, window_start),
        "realized_vol_20d": realized_vol(frame, at=origin, lookback_days=20),
        "regime_transitions_since_incumbent": regime_transitions_since(
            emissions, since=window_start, until=origin),
        "incumbent_trailing_return": incumbent_trailing_return(
            keep_equity_daily, at=origin, lookback_days=20),
    }
