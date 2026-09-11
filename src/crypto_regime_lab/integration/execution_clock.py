"""A06 — map a decision made at an HTF close onto the one-minute event clock.

A signal observed at an HTF bar close is available only after that bar has
closed. The earliest fill is the first EXECUTION bar whose open is at or after
that close time; the bar that produced the signal is never the fill bar, and no
future HTF high/low is exposed at the execution open.

Bars are left-labelled: ``index[t]`` is the open, the close is
``index[t] + interval``. The lab's registered execution product is 1m for every
alpha, so this module is the only place the HTF decision clock is translated.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class ExecutionClockError(RuntimeError):
    """A decision cannot be placed on the execution clock."""


def bar_close(open_time: pd.Timestamp, interval: pd.Timedelta) -> pd.Timestamp:
    return pd.Timestamp(open_time) + interval


def first_execution_bar(available_at: pd.Timestamp, execution_index: pd.DatetimeIndex) -> int | None:
    """First execution bar that OPENS at or after ``available_at``.

    A same-close fill is impossible: the bar that closed at ``available_at``
    opened strictly before it, so it is not selected. Returns ``None`` when the
    decision is available after the last execution bar (a real missing fill).
    """
    if not isinstance(execution_index, pd.DatetimeIndex):
        raise ExecutionClockError("execution_index must be a DatetimeIndex")
    position = int(execution_index.searchsorted(pd.Timestamp(available_at), side="left"))
    return position if position < len(execution_index) else None


def htf_interval(index: pd.DatetimeIndex) -> pd.Timedelta:
    """The HTF bar length, read from the index itself rather than assumed."""
    if len(index) < 2:
        raise ExecutionClockError("an HTF index needs at least two bars to infer its interval")
    delta = pd.Timestamp(index[1]) - pd.Timestamp(index[0])
    if delta <= pd.Timedelta(0):
        raise ExecutionClockError(f"HTF index is not increasing: {index[:2].tolist()}")
    return delta


def map_htf_decisions(intents_by_htf_bar: dict[int, list[Any]], htf_index: pd.DatetimeIndex,
                      execution_index: pd.DatetimeIndex) -> dict[int, list[Any]]:
    """Rebase intents from HTF bar positions onto execution bar positions.

    The intent objects are returned unchanged; only the bar they become effective
    on moves. A decision with no remaining execution bar is dropped with its
    position listed under ``None`` so the caller reports a missing fill instead
    of silently shifting it earlier.
    """
    interval = htf_interval(htf_index)
    mapped: dict[int, list[Any]] = {}
    for htf_position in sorted(intents_by_htf_bar):
        if htf_position < 0 or htf_position >= len(htf_index):
            raise ExecutionClockError(f"HTF bar position {htf_position} is outside the index")
        available_at = bar_close(htf_index[htf_position], interval)
        exec_position = first_execution_bar(available_at, execution_index)
        if exec_position is None:
            mapped.setdefault(-1, []).extend(intents_by_htf_bar[htf_position])
            continue
        mapped.setdefault(exec_position, []).extend(intents_by_htf_bar[htf_position])
    return mapped


def execution_slice_after(index: pd.DatetimeIndex, available_at: pd.Timestamp) -> pd.DatetimeIndex:
    """The execution bars that OPEN at or after the decision became available.

    Used by the pilot to prove the engine frame never contains bars the decision
    could not have seen.
    """
    return index[index >= pd.Timestamp(available_at)]
