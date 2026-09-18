"""L08.2 arms C and D — refresh WHEN the regime moves, not when the calendar says.

The contribution being isolated is timing, so everything except timing must be
held identical: the same selector pair, the same training memory, the same
engine and costs, and -- the part that is easy to get wrong -- the same NUMBER of
refreshes.

Guide 10.5 forbids giving the new method more search than the baseline. A
regime-triggered arm that refits whenever the state changes would refresh far
more often than the calendar's six, and any advantage it showed would be
confounded with having been allowed to look more times. So the dynamic arms get
exactly as many refreshes as the calendar arms; the model chooses only WHERE
they fall.

The choice is causal by construction: a trigger is picked from state changes
that have already been emitted, using a rule that reads no future observation.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .calendar_baseline import CalendarSpec


class ScheduleError(ValueError):
    """Raised when a regime schedule would not be comparable to the calendar."""


@dataclass(frozen=True)
class RegimeSchedule:
    """A drop-in for ``CalendarSpec`` whose cutoffs come from the state tape."""

    cutoffs: tuple[str, ...]
    train_days: int = 180
    test_days: int = 180
    inner_episodes: int = 6
    source: str = "regime_transitions"

    @property
    def folds(self) -> int:
        return len(self.cutoffs)

    @property
    def first_cutoff(self) -> str:
        return self.cutoffs[0]

    def fold_windows(self) -> list[dict]:
        out = []
        for index, moment in enumerate(self.cutoffs):
            cutoff = pd.Timestamp(moment)
            if cutoff.tzinfo is None:
                cutoff = cutoff.tz_localize("UTC")
            out.append({
                "fold": index,
                "train_start": (cutoff - pd.Timedelta(days=self.train_days)).isoformat(),
                "cutoff": cutoff.isoformat(),
                "test_end": (cutoff + pd.Timedelta(days=self.test_days)).isoformat(),
            })
        return out

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.regime_schedule.v1",
            "cutoffs": list(self.cutoffs),
            "refreshes": self.folds,
            "train_days": self.train_days,
            "source": self.source,
            "matched_rule": ("the dynamic arms get exactly as many refreshes as the calendar "
                             "arms. The model chooses WHERE they fall, never how many, because a "
                             "method allowed to look more times is not being compared on timing "
                             "(guide 10.5)"),
        }


def transition_cutoffs(emissions: list[dict], *, count: int, earliest: str,
                       latest: str, min_gap_days: float = 30.0) -> RegimeSchedule:
    """Pick ``count`` refresh times from state changes already emitted.

    One trigger per period, not the first ``count`` transitions. Taking them
    greedily from the front puts every refresh in the opening months and leaves
    the arm holding its initial parameters for years -- which is a coverage
    artefact wearing a timing result's clothes. Splitting the window into as many
    periods as the calendar has folds and taking the first transition INSIDE each
    period gives the same cadence with the timing chosen by the model, which is
    the only difference the contrast is meant to measure.

    Two properties make it causal rather than merely plausible.

    A trigger sits at an emission's ``available_at``, not at the bar it
    describes: the state for a bar that has not closed is not knowable, and
    LAB-07 found a version of this published fifteen times too early.

    And no transition is ranked by how large or how profitable it turned out to
    be. "The biggest transitions" is a quantity only the future knows; within a
    period the FIRST one is taken.
    """
    earliest_ts = pd.Timestamp(earliest)
    latest_ts = pd.Timestamp(latest)
    if earliest_ts.tzinfo is None:
        earliest_ts = earliest_ts.tz_localize("UTC")
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.tz_localize("UTC")

    changes: list[pd.Timestamp] = []
    previous: tuple[object, object, object] | None = None
    for record in emissions:
        # A10: an ineligible or non-allowlisted emission is not a market state.
        if not record.get("decision_eligible", True):
            continue
        if record.get("quality_status", "OK") not in ("OK",):
            continue
        moment = pd.Timestamp(record["available_at"])
        if moment.tzinfo is None:
            moment = moment.tz_localize("UTC")
        if not (earliest_ts <= moment <= latest_ts):
            continue
        # A10: a namespace/version change is not a market change. A change only
        # counts inside one namespace, or across namespaces when a common
        # coordinate is published for both.
        common = record.get("state_common")
        namespace = record.get("state_namespace")
        semantic = common if common is not None else record.get("state_id")
        if previous is not None:
            prev_common, prev_namespace, prev_semantic = previous
            comparable = (common is not None and prev_common is not None) or namespace == prev_namespace
            if comparable and semantic != prev_semantic:
                changes.append(moment)
        previous = (common, namespace, semantic)

    period = (latest_ts - earliest_ts) / count
    chosen: list[pd.Timestamp] = []
    gap = pd.Timedelta(days=min_gap_days)
    missing_periods: list[int] = []
    for index in range(count):
        window_start = earliest_ts + period * index
        window_end = earliest_ts + period * (index + 1)
        candidates = [m for m in changes if window_start <= m < window_end
                      and (not chosen or m - chosen[-1] >= gap)]
        if candidates:
            chosen.append(candidates[0])            # first in the period, never "biggest"
        else:
            # A10: no transition in this period is a result, not a reason to raise
            # and not a reason to pad the count back to the calendar.
            missing_periods.append(index)

    return RegimeSchedule(
        cutoffs=tuple(t.isoformat() for t in chosen),
        source=(f"{len(changes)} eligible semantic state changes; the first inside each of "
                f"{count} equal periods with a {min_gap_days:g}-day minimum gap; "
                f"{len(missing_periods)} periods had no eligible transition"))


def online_trigger_schedule(emissions: list[dict], *, earliest: str, latest: str,
                            min_gap_days: float = 30.0, max_age_days: float = 180.0,
                            budget: int | None = None,
                            quality_allowlist: tuple[str, ...] = ("OK",)) -> RegimeSchedule:
    """RF-03.3: an online controller with no forced refit count.

    A trigger fires only on an eligible semantic state change (A10), at least
    ``min_gap_days`` after the previous trigger. When no change has fired for
    ``max_age_days`` the controller may request a refresh with reason
    ``MAX_AGE`` — never described as a detected regime. ``budget`` caps the
    number of search requests; the returned ``source`` records the reasons.
    """
    earliest_ts = pd.Timestamp(earliest)
    latest_ts = pd.Timestamp(latest)
    if earliest_ts.tzinfo is None:
        earliest_ts = earliest_ts.tz_localize("UTC")
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.tz_localize("UTC")

    gap = pd.Timedelta(days=min_gap_days)
    max_age = pd.Timedelta(days=max_age_days)
    chosen: list[pd.Timestamp] = []
    triggers: list[dict] = []
    previous: tuple[object, object, object] | None = None
    last_trigger: pd.Timestamp | None = None
    for record in emissions:
        if not record.get("decision_eligible", True):
            continue
        if record.get("quality_status", "OK") not in quality_allowlist:
            continue
        moment = pd.Timestamp(record["available_at"])
        if moment.tzinfo is None:
            moment = moment.tz_localize("UTC")
        if not (earliest_ts <= moment <= latest_ts):
            continue
        common = record.get("state_common")
        namespace = record.get("state_namespace")
        semantic = common if common is not None else record.get("state_id")
        changed = False
        if previous is not None:
            prev_common, prev_namespace, prev_semantic = previous
            comparable = (common is not None and prev_common is not None) or namespace == prev_namespace
            changed = comparable and semantic != prev_semantic
        previous = (common, namespace, semantic)
        if budget is not None and len(chosen) >= budget:
            break
        if last_trigger is not None and moment - last_trigger < gap:
            continue
        if changed:
            chosen.append(moment)
            last_trigger = moment
            triggers.append({"at": moment.isoformat(), "reason": "SEMANTIC_STATE_CHANGE",
                             "namespace": namespace, "state_id": record.get("state_id")})
        elif last_trigger is not None and moment - last_trigger >= max_age:
            chosen.append(moment)
            last_trigger = moment
            triggers.append({"at": moment.isoformat(), "reason": "MAX_AGE",
                             "namespace": namespace, "state_id": record.get("state_id")})
    return RegimeSchedule(
        cutoffs=tuple(t.isoformat() for t in chosen),
        source=(f"online controller: {len(triggers)} triggers, no forced count; "
                f"reasons {[t['reason'] for t in triggers]}"))


def assert_compute_matched(calendar: CalendarSpec, schedule: RegimeSchedule) -> dict:
    """The dynamic arm may not buy its advantage with extra searches."""
    matched = calendar.folds == schedule.folds and calendar.train_days == schedule.train_days
    return {
        "schema": "crypto_regime_lab.compute_match_check.v1",
        "calendar_refreshes": calendar.folds,
        "dynamic_refreshes": schedule.folds,
        "calendar_train_days": calendar.train_days,
        "dynamic_train_days": schedule.train_days,
        "matched": bool(matched),
        "rule": ("same refresh count and same training memory. Only the timing differs, which is "
                 "the contribution being measured (guide 10.1 arm C: 'training memory giữ như A')"),
    }
