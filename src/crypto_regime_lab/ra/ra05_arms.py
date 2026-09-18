"""RA05.2/RA05.3: the four arm schedules, the CAL_MATCHED forecast and the
scheduler audit (guide section 9, F-06).

Arm canonical IDs and rules (guide 3.1) -- all four share the SAME initial
Mode 4 selection at `window_start`, the same execution/memory, and differ
ONLY in when (if ever) they re-select:

* STATIC:        one selection at window_start, never refits (diagnostic).
* M4_CAL:         calendar_cutoffs at a frozen cadence.
* M4_CAL_MATCHED: calendar_cutoffs at a cadence FORECAST from a development
                  prefix disjoint from the evaluation window -- never from
                  the window's own realized trigger count (guide 3.4/13.3:
                  "khong sua calendar dua so refit tuong lai").
* M4_REGIME:      the shared initial cutoff, then real-trigger cutoffs from
                  `regime_cutoffs` (RF-04's proven, frozen-adjacent online
                  controller), bounded by a registered budget.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from ..experiments.dynamic_fold_provider import CutoffSchedule, calendar_cutoffs, regime_cutoffs
from ..time_edge.schedule import matched_cadence

#: Reused from RF-04's own regime_cutoffs() defaults (already frozen/tested there;
#: guide 4.2 -- reuse an established policy rather than inventing a new one).
REGIME_MIN_GAP_DAYS = 45.0
REGIME_MAX_AGE_DAYS = 180.0
#: Phase-owned scale cap, frozen before any arm runs (RA05.1).
REGIME_BUDGET = 2
#: Guide 3.4's registered cadence menu.
CAL_MATCHED_MENU = (28, 56, 90, 180)


def build_static_schedule(window_start: str, window_end: str, *,
                          train_memory_days: int) -> CutoffSchedule:
    schedule = calendar_cutoffs(first_cutoff=window_start, window_start=window_start,
                                window_end=window_end, max_cutoffs=1,
                                train_memory_days=train_memory_days)
    return replace(schedule, arm="STATIC",
                   source=schedule.source + " -- STATIC diagnostic: one selection, never refits")


def build_calendar_schedule(window_start: str, window_end: str, *, test_days: int,
                            train_memory_days: int) -> CutoffSchedule:
    return calendar_cutoffs(first_cutoff=window_start, window_start=window_start,
                            window_end=window_end, test_days=test_days,
                            train_memory_days=train_memory_days)


def build_regime_schedule(emissions: list[dict], *, window_start: str, window_end: str,
                          train_memory_days: int, min_gap_days: float = REGIME_MIN_GAP_DAYS,
                          max_age_days: float = REGIME_MAX_AGE_DAYS,
                          budget: int = REGIME_BUDGET) -> CutoffSchedule:
    schedule = regime_cutoffs(emissions, window_start=window_start, window_end=window_end,
                              min_gap_days=min_gap_days, max_age_days=max_age_days, budget=budget)
    cutoffs = list(schedule.cutoffs)
    shared_initial = pd.Timestamp(window_start, tz="UTC").isoformat()
    if not cutoffs or pd.Timestamp(cutoffs[0]) != pd.Timestamp(shared_initial):
        cutoffs = [shared_initial] + cutoffs
    return replace(
        schedule, cutoffs=tuple(cutoffs), train_memory_days=train_memory_days,
        source=schedule.source + (f" -- shared initial cutoff {shared_initial} prepended so "
                                  "M4_REGIME starts from the SAME initial selection as the "
                                  "other arms (guide 3.1: STATIC/all arms share initial "
                                  "selection)"))


def classify_regime_trigger_reasons(cutoffs: tuple[str, ...], emissions: list[dict], *,
                                    shared_initial: str,
                                    quality_allowlist: tuple[str, ...] = ("OK",)) -> dict[str, dict]:
    """Label each of `build_regime_schedule`'s OWN already-chosen cutoffs as
    INITIAL / SEMANTIC_STATE_CHANGE / MAX_AGE, for accurate funnel
    `semantic_transition`/`reason` fields (guide RA05.4). Read-only
    classification of a decision `online_trigger_schedule` (frozen,
    `experiments/regime_schedule.py`) already made -- this does not
    re-decide which cutoffs were chosen, only labels why.

    `online_trigger_schedule` updates its `previous` state tracker on EVERY
    eligible emission it walks, not only on the ones that become triggers --
    so classifying a cutoff correctly requires the SAME emission-by-emission
    replay (comparing each cutoff's state against the state at the
    immediately PRECEDING eligible emission, which can be hours before the
    previous cutoff, not the previous cutoff's own state directly). An
    earlier version of this function compared consecutive CUTOFFS' states
    directly and mislabeled real SEMANTIC_STATE_CHANGE triggers as MAX_AGE
    whenever an intervening eligible emission had already changed `previous`
    on its own -- caught by cross-checking against `deployed_source`'s own
    reported reasons.
    """
    ordered = sorted(
        (row for row in emissions
         if row.get("decision_eligible", True) and row.get("quality_status", "OK") in quality_allowlist),
        key=lambda row: pd.Timestamp(row["available_at"]))
    by_time = {row["available_at"]: row for row in ordered}
    cutoff_set = set(cutoffs)

    out: dict[str, dict] = {}
    previous = None  # (state_common, state_namespace, semantic) -- mirrors online_trigger_schedule
    for row in ordered:
        at = row["available_at"]
        common = row.get("state_common")
        namespace = row.get("state_namespace")
        semantic = common if common is not None else row.get("state_id")
        changed = False
        if previous is not None:
            prev_common, prev_namespace, prev_semantic = previous
            comparable = (common is not None and prev_common is not None) or namespace == prev_namespace
            changed = comparable and semantic != prev_semantic
        if at in cutoff_set and at not in out:
            if at == shared_initial and previous is None:
                reason = "INITIAL"
            elif changed:
                reason = "SEMANTIC_STATE_CHANGE"
            else:
                reason = "MAX_AGE"
            out[at] = {"observation_available": True,
                      "model_ready": row.get("decision_eligible", True),
                      "semantic_transition": bool(changed) if reason != "INITIAL" else False,
                      "eligibility": row.get("quality_status") == "OK",
                      "confirmed": True, "budget_admitted": True, "reason": reason}
        previous = (common, namespace, semantic)
    for cutoff in cutoffs:
        if cutoff not in out:
            emission = by_time.get(cutoff)
            out[cutoff] = {"observation_available": emission is not None, "model_ready": True,
                           "semantic_transition": None, "eligibility": emission is not None,
                           "confirmed": True, "budget_admitted": True,
                           "reason": ("INITIAL" if cutoff == shared_initial
                                     else "UNRESOLVED_NO_MATCHING_ELIGIBLE_EMISSION")}
    return out


def forecast_cal_matched_test_days(full_emissions: list[dict], *, window_start: str,
                                   window_end: str, per_selection_wall_seconds: float,
                                   menu: tuple[int, ...] = CAL_MATCHED_MENU) -> dict:
    """RA05.2: forecast regime work from a DEVELOPMENT prefix disjoint from the
    evaluation window -- the rest of the real emission history, never the
    window's own realized trigger count -- then pick the menu cadence whose
    total predicted work is closest to that forecast (`matched_cadence`).
    """
    from ..experiments.regime_schedule import online_trigger_schedule

    start_ts = pd.Timestamp(window_start, tz="UTC")
    end_ts = pd.Timestamp(window_end, tz="UTC")
    window_days = max(1, (end_ts - start_ts).days)
    development = [row for row in full_emissions
                   if not (start_ts <= pd.Timestamp(row["available_at"]) < end_ts)]
    if not development:
        raise ValueError("no development-prefix emissions disjoint from the evaluation window")
    dev_start = min(pd.Timestamp(row["available_at"]) for row in development)
    dev_end = max(pd.Timestamp(row["available_at"]) for row in development)
    dev_days = max(1, (dev_end - dev_start).days)
    dev_schedule = online_trigger_schedule(
        development, earliest=dev_start.isoformat(), latest=dev_end.isoformat(),
        min_gap_days=REGIME_MIN_GAP_DAYS, max_age_days=REGIME_MAX_AGE_DAYS, budget=None)
    trigger_rate_per_day = len(dev_schedule.cutoffs) / dev_days
    predicted_trigger_count = trigger_rate_per_day * window_days
    #: A forecast of exactly zero triggers cannot be matched against (matched_cadence
    #: requires a positive predicted work); floor at one predicted event and say so.
    floored = predicted_trigger_count <= 0
    effective_trigger_count = max(predicted_trigger_count, 1.0)
    predicted_regime_work = effective_trigger_count * per_selection_wall_seconds
    chosen_days = matched_cadence(predicted_regime_work, per_selection_wall_seconds,
                                  days=window_days, menu=menu)
    return {
        "schema": "regime_lab.ra05_cal_matched_forecast.v1",
        "method": ("development-prefix trigger rate (from real emissions OUTSIDE the "
                  "evaluation window) x measured per-selection wall time, matched to the "
                  "registered 28/56/90/180-day menu -- never the window's own realized "
                  "trigger count"),
        "development_window": [dev_start.isoformat(), dev_end.isoformat()],
        "development_days": dev_days,
        "development_triggers": len(dev_schedule.cutoffs),
        "development_trigger_source": dev_schedule.source,
        "trigger_rate_per_day": trigger_rate_per_day,
        "evaluation_window_days": window_days,
        "predicted_trigger_count_in_window": predicted_trigger_count,
        "predicted_trigger_count_floored_to_one": floored,
        "per_selection_wall_seconds_measured": per_selection_wall_seconds,
        "predicted_regime_work_seconds": predicted_regime_work,
        "menu": list(menu),
        "chosen_test_days": chosen_days,
        "never_uses_realized_window_trigger_count": True,
    }


def audit_scheduler(emissions: list[dict], *, window_start: str, window_end: str,
                    min_gap_days: float = REGIME_MIN_GAP_DAYS,
                    max_age_days: float = REGIME_MAX_AGE_DAYS,
                    regime_budget: int = REGIME_BUDGET) -> dict:
    """RA05.3: audit the scheduler -- raw state changes, eligible/confirmed
    changes, accepted triggers, max-age reason, cooldown suppression, gap
    distribution -- directly engaging F-06 ('28 accepted triggers, median gap
    ~28.17d with min-gap28' from `time_edge/schedule.py`, RA-01
    finding_disposition planned_phase=RA-05).

    Runs BOTH the F-06-cited implementation (`time_edge.schedule.triggers`,
    unbounded budget, so the FULL cadence signature is visible) and the
    function that actually drives M4_REGIME's cutoffs
    (`experiments.regime_schedule.online_trigger_schedule`, budget-capped) on
    the SAME real emissions -- so this phase both engages the finding at its
    own cited source and documents the mechanism actually deployed.
    """
    from ..experiments.regime_schedule import online_trigger_schedule
    from ..time_edge.schedule import triggers as schedule_triggers

    #: time_edge.schedule.triggers's own `utc()` contract refuses a bare date
    #: string (day_label is not offered here) -- normalise to explicit UTC ISO.
    start_iso = pd.Timestamp(window_start, tz="UTC").isoformat()
    end_iso = pd.Timestamp(window_end, tz="UTC").isoformat()
    raw = schedule_triggers(emissions, initial_ready=start_iso, end=end_iso,
                            min_gap_days=min_gap_days, max_age_days=max_age_days,
                            confirmations=2, budget=None)
    accepted = raw["triggers"]
    gaps = [(pd.Timestamp(b["cutoff"]) - pd.Timestamp(a["cutoff"])).total_seconds() / 86400.0
           for a, b in zip(accepted, accepted[1:])]
    rejected_reasons: dict[str, int] = {}
    for row in raw["rejected"]:
        rejected_reasons[row["reason"]] = rejected_reasons.get(row["reason"], 0) + 1
    max_age_count = sum(1 for t in accepted if t["reason"] == "MAX_AGE")
    state_change_count = sum(1 for t in accepted if t["reason"] == "STATE_CHANGE")
    gap_series = pd.Series(gaps, dtype=float)

    deployed = online_trigger_schedule(emissions, earliest=window_start, latest=window_end,
                                       min_gap_days=min_gap_days, max_age_days=max_age_days,
                                       budget=regime_budget)
    return {
        "schema": "regime_lab.ra05_scheduler_audit.v1",
        "f06_finding": ("F-06: 28 accepted triggers, median gap ~28.17d with min-gap28 -- from "
                        "a different (host-emissions) window/params; this is a fresh real-data "
                        "re-audit of the SAME cited function, not a replay of that number"),
        "audited_function": "time_edge.schedule.triggers (time_edge/schedule.py:20-26)",
        "window": [window_start, window_end], "min_gap_days": min_gap_days,
        "max_age_days": max_age_days,
        "emissions_seen": len(emissions),
        "rejected_total": len(raw["rejected"]), "rejected_by_reason": rejected_reasons,
        "accepted_total": len(accepted),
        "accepted_by_reason": {"STATE_CHANGE": state_change_count, "MAX_AGE": max_age_count},
        "gap_days_between_accepted": gaps,
        "gap_days_median": float(gap_series.median()) if gaps else None,
        "gap_days_min": float(gap_series.min()) if gaps else None,
        "median_close_to_min_gap_floor": (
            None if not gaps else bool(abs(float(gap_series.median()) - min_gap_days) <= 3.0)),
        "deployed_scheduler_function": ("experiments.regime_schedule.online_trigger_schedule "
                                        "(the function that actually drives M4_REGIME's cutoffs)"),
        "deployed_triggers": len(deployed.cutoffs), "deployed_source": deployed.source,
        "claim_limit": ("this is a replay/audit over one real bounded window, not 'N actual "
                        "deployments' -- F-06's own caution, still true here"),
    }
