"""RA07.3: the 5 ordered controls (guide section 11).

DELAYED_INFORMATION and PLACEBO_TIMING each need a real
`run_cutoff_walk_forward` call (a new schedule, not a new search budget --
same trials/seed/route/fees as M4_REGIME, only the trigger content differs),
so both are scoped to cell 1 only (disclosed in ra07_freeze.build_
replication_spec's controls_plan, registered BEFORE either control ran).

This module deliberately does NOT reuse `experiments.controls.delayed_states`
unmodified: that function only overrides `state_id`/`state_namespace` on a
delayed record, but this lab's REAL emissions artifact
(evidence/time_edge_validation_v4/host-emissions-03.json) always populates
`state_common`, and the trigger logic
(`experiments/regime_schedule.py::online_trigger_schedule`) reads
`state_common` FIRST ("semantic = common if common is not None else
state_id"). Applying the unmodified upstream helper here would silently
leave `state_common` un-delayed and produce a schedule IDENTICAL to
M4_REGIME's real one -- a control that never controls for anything. Verified
by reading the real artifact's schema directly, not assumed from the
function's own docstring.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from ..experiments.controls import dwell_profile, placebo_fidelity, placebo_states
from ..experiments.dynamic_fold_provider import CutoffSchedule
from .ra05_arms import REGIME_BUDGET, REGIME_MAX_AGE_DAYS, REGIME_MIN_GAP_DAYS


def delayed_emissions(emissions: list, *, observations: int) -> list:
    """Delay STATE AVAILABILITY by `observations` steps on the REAL
    observation grid -- state_id, state_namespace AND state_common (this
    schema's actual comparability fields) all shifted together; available_at
    and every other field (decision_eligible, quality_status, ...) stay the
    real, un-delayed value. The world did not change, only when a policy
    could see it."""
    if observations < 1:
        raise ValueError("a delay of zero observations is not a delay")
    ordered = sorted(emissions, key=lambda r: pd.Timestamp(r["available_at"]))
    out = []
    for index, record in enumerate(ordered):
        source = ordered[max(index - observations, 0)]
        out.append({**record, "state_id": source["state_id"],
                   "state_namespace": source["state_namespace"],
                   "state_common": source["state_common"],
                   "delayed_by_observations": observations,
                   "delay_is_on_availability_not_on_the_world": True})
    return out


def build_delayed_schedule(emissions: list, *, window_start: str, window_end: str,
                           train_memory_days: int, observations: int,
                           min_gap_days: float = REGIME_MIN_GAP_DAYS,
                           max_age_days: float = REGIME_MAX_AGE_DAYS,
                           budget: int = REGIME_BUDGET) -> CutoffSchedule:
    """Same trigger mechanics as M4_REGIME (`regime_cutoffs`), fed the
    DELAYED emission tape instead of the real one; same shared initial
    cutoff prepended so this control differs from M4_REGIME in exactly one
    thing (guide RA07.3 point 3: 'khong sua execution fills thanh gia khac
    tuy y' -- nothing about execution changes here, only which cutoffs the
    schedule contains)."""
    from ..experiments.dynamic_fold_provider import regime_cutoffs

    delayed = delayed_emissions(emissions, observations=observations)
    schedule = regime_cutoffs(delayed, window_start=window_start, window_end=window_end,
                              min_gap_days=min_gap_days, max_age_days=max_age_days, budget=budget)
    cutoffs = list(schedule.cutoffs)
    shared_initial = pd.Timestamp(window_start, tz="UTC").isoformat()
    if not cutoffs or pd.Timestamp(cutoffs[0]) != pd.Timestamp(shared_initial):
        cutoffs = [shared_initial] + cutoffs
    return replace(schedule, arm="M4_REGIME_DELAYED", cutoffs=tuple(cutoffs),
                   train_memory_days=train_memory_days,
                   source=schedule.source + f" -- DELAYED_INFORMATION control: state availability "
                                            f"shifted {observations} observation(s); shared "
                                            f"initial cutoff {shared_initial} prepended")


def development_prefix_state_sequence(full_emissions: list, *, window_start: str,
                                      window_end: str) -> list:
    """The SAME development-prefix rule forecast_cal_matched_test_days uses
    (real emissions strictly OUTSIDE the evaluation window) -- reused here so
    the placebo's dwell profile is calibrated before OOS, never from the
    window it will be compared against."""
    start_ts = pd.Timestamp(window_start, tz="UTC")
    end_ts = pd.Timestamp(window_end, tz="UTC")
    development = [row for row in full_emissions
                   if not (start_ts <= pd.Timestamp(row["available_at"]) < end_ts)
                   and row.get("decision_eligible", True)
                   and row.get("quality_status", "OK") == "OK"]
    ordered = sorted(development, key=lambda r: pd.Timestamp(r["available_at"]))
    return [row["state_common"] for row in ordered]


def build_placebo_schedule(*, full_emissions: list, window_emissions: list, window_start: str,
                           window_end: str, train_memory_days: int, seed: int,
                           min_gap_days: float = REGIME_MIN_GAP_DAYS,
                           max_age_days: float = REGIME_MAX_AGE_DAYS,
                           budget: int = REGIME_BUDGET) -> dict:
    """PLACEBO_TIMING (guide RA07.3 point 4): a seeded fake state tape with
    the development prefix's OWN dwell/switch-rate statistics, laid onto the
    REAL evaluation-window observation timestamps (the physical cadence of
    the data feed, not market information), run through the SAME trigger
    mechanics as M4_REGIME. Returns the schedule plus the fidelity check
    (guide: a placebo that does not actually match real switch-rate
    statistics is a strawman, not a control) -- both together, so a caller
    cannot use one without the other.
    """
    from ..experiments.dynamic_fold_provider import regime_cutoffs

    dev_states = development_prefix_state_sequence(full_emissions, window_start=window_start,
                                                    window_end=window_end)
    if len(dev_states) < 2:
        return {"status": "INSUFFICIENT_DEVELOPMENT_STATES", "schedule": None, "fidelity": None}
    profile = dwell_profile(dev_states)

    ordered_window = sorted(window_emissions, key=lambda r: pd.Timestamp(r["available_at"]))
    if len(ordered_window) < 2:
        return {"status": "INSUFFICIENT_WINDOW_OBSERVATIONS", "schedule": None, "fidelity": None}
    fake_labels = placebo_states(profile, length=len(ordered_window), seed=seed)

    placebo_namespace = "RA07_PLACEBO_TIMING_SYNTHETIC_NAMESPACE"
    synthetic = [{**record, "state_id": label, "state_common": label,
                 "state_namespace": placebo_namespace,
                 "placebo_seed": seed, "placebo_source": "development_prefix_dwell_profile"}
                for record, label in zip(ordered_window, fake_labels)]

    schedule = regime_cutoffs(synthetic, window_start=window_start, window_end=window_end,
                              min_gap_days=min_gap_days, max_age_days=max_age_days, budget=budget)
    cutoffs = list(schedule.cutoffs)
    shared_initial = pd.Timestamp(window_start, tz="UTC").isoformat()
    if not cutoffs or pd.Timestamp(cutoffs[0]) != pd.Timestamp(shared_initial):
        cutoffs = [shared_initial] + cutoffs
    final = replace(schedule, arm="M4_REGIME_PLACEBO", cutoffs=tuple(cutoffs),
                    train_memory_days=train_memory_days,
                    source=schedule.source + f" -- PLACEBO_TIMING control: seeded synthetic "
                                             f"labels (seed={seed}) matching the development "
                                             f"prefix's dwell profile; shared initial cutoff "
                                             f"{shared_initial} prepended")

    real_window_states = [row["state_common"] for row in ordered_window]
    fidelity = placebo_fidelity(real_window_states, fake_labels)
    return {"status": "OK", "schedule": final, "fidelity": fidelity,
           "development_states_count": len(dev_states), "window_observations_count": len(ordered_window)}


def _exposure_days(fills: list, frame_index, *, window_days: int) -> dict:
    """Real exposure/turnover from the arm's own fills -- a position is
    'open' from an entry fill's bar until the next exit-tagged fill (or the
    window's end if never closed); this is descriptive attribution, not a
    new accounting engine (guide 13.1 forbids building a second one)."""
    if not fills:
        return {"exposure_days": 0.0, "exposure_fraction_of_window": 0.0, "turnover_notional": 0.0,
               "fill_count": 0}
    ordered = sorted(fills, key=lambda f: f.get("bar_index", 0))
    turnover = sum(abs(float(f.get("qty", 0.0)) * float(f.get("price", 0.0))) for f in ordered)
    open_bar = None
    exposed_bars = 0
    total_bars = len(frame_index)
    for f in ordered:
        idx = f.get("bar_index")
        if idx is None:
            continue
        if f.get("tag") == "entry" and open_bar is None:
            open_bar = idx
        elif f.get("tag") != "entry" and open_bar is not None:
            exposed_bars += max(0, idx - open_bar)
            open_bar = None
    if open_bar is not None:
        exposed_bars += max(0, total_bars - 1 - open_bar)
    minutes_per_bar = 1.0  # frame is real 1m bars (guide primary_execution_resolution)
    exposure_days = exposed_bars * minutes_per_bar / (60.0 * 24.0)
    return {"exposure_days": exposure_days,
           "exposure_fraction_of_window": (exposure_days / window_days) if window_days else None,
           "turnover_notional": turnover, "fill_count": len(ordered)}


def risk_exposure_attribution(*, regime_outcome: dict, cal_matched_outcome: dict,
                              frame_index, window_days: int) -> dict:
    """RA07.3 point 5: report the ACTUAL exposure/turnover contribution from
    real paths -- if a return difference is mostly explained by exposure
    rather than parameter timing, that must be the label (guide 13.5: 'Neu
    positive chi do exposure thay doi, dat contribution label dung')."""
    def one_arm(outcome):
        if not outcome.get("ok"):
            return {"status": "NOT_EVALUABLE", "reason": outcome.get("error")}
        account = outcome["run"].get("account") or {}
        fills = account.get("fills") or []
        attribution = _exposure_days(fills, frame_index, window_days=window_days)
        equity_daily = account.get("equity_daily") or []
        equity_values = [v for _, v in equity_daily]
        peak = equity_values[0] if equity_values else None
        max_dd = 0.0
        for v in equity_values:
            peak = v if peak is None else max(peak, v)
            if peak:
                max_dd = max(max_dd, (peak - v) / peak)
        return {"status": "OK", **attribution, "max_drawdown_fraction": max_dd,
               "equity_last": account.get("equity_last"), "equity_first": account.get("equity_first")}

    regime = one_arm(regime_outcome)
    cal_matched = one_arm(cal_matched_outcome)
    both_ok = regime.get("status") == "OK" and cal_matched.get("status") == "OK"
    exposure_delta = (None if not both_ok else
                      regime["exposure_fraction_of_window"] - cal_matched["exposure_fraction_of_window"])
    return {
        "schema": "regime_lab.ra07_risk_exposure_attribution.v1",
        "M4_REGIME": regime, "M4_CAL_MATCHED": cal_matched,
        "exposure_fraction_delta": exposure_delta,
        "max_drawdown_deterioration_vs_comparator": (
            None if not both_ok else regime["max_drawdown_fraction"] - cal_matched["max_drawdown_fraction"]),
        "risk_cap_registered": 0.02,
        "risk_cap_breached": (None if not both_ok else
                              (regime["max_drawdown_fraction"] - cal_matched["max_drawdown_fraction"]) > 0.02),
        "interpretation_note": ("a positive Delta-hat driven mostly by a large exposure_fraction_delta "
                                "is an exposure-timing contribution, not a parameter-selection/"
                                "information-timing contribution, even if both arms use the same "
                                "selector (guide 13.5)"),
    }
