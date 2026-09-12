"""L06.1 / guide 9.1 — the outcome episode table.

An episode pairs a decision made at time T with the outcome that followed it. Two
rules decide whether a row may be used, and both are about time rather than about
performance:

* an outcome is usable at T only once ``end + publication delay <= T``. A horizon
  that has not finished is not a small outcome, it is NO outcome, and using it is
  the most direct form of look-ahead available here (T45);
* the context attached to a row is the context as of the DECISION, never the
  context revealed by the outcome. Building a response label from future PnL and
  feeding it back into a regime fit at ``episode_start`` is named and forbidden
  in guide 9.1.

The primary evidence grid is non-overlapping. Overlapping episodes are available
as an extension, but they arrive with a purge and with the dependence correction
made explicit, because thousands of overlapped bars can shrink a standard error
to nothing while carrying almost no new information.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

#: Registered for the pilot (guide L06.1). Changing it is a registered decision,
#: not a tuning knob.
PILOT_HORIZON_DAYS = 7
#: The lab publishes its own panel, so the only delay is processing. Recorded
#: explicitly rather than assumed to be zero.
PUBLICATION_DELAY = pd.Timedelta(0)
PROCESSING_DELAY = pd.Timedelta(hours=4)      # one regime observation interval

OUTCOME_COMPLETE = "COMPLETE"
OUTCOME_UNFINISHED = "UNFINISHED_AT_DECISION"
OUTCOME_OPEN_POSITION = "OPEN_POSITION_AT_HORIZON_END"
OUTCOME_INSUFFICIENT_BARS = "INSUFFICIENT_BARS"


class EpisodeError(ValueError):
    """A malformed episode request. Never silently repaired."""


@dataclass(frozen=True)
class Episode:
    """One (decision, candidate, outcome) row, with everything guide 9.1 lists."""

    episode_id: str
    episode_start: pd.Timestamp
    decision_time: pd.Timestamp
    context_asof_decision: tuple[float, ...]
    context_state_id: int | None
    context_namespace: str | None
    candidate_id: str
    parameter_version: str
    outcome_start: pd.Timestamp
    outcome_end: pd.Timestamp
    outcome_available_at: pd.Timestamp
    net_return: float | None
    max_drawdown: float | None
    turnover: float | None
    cost: float | None
    trades: int | None
    exposure: float | None
    terminal_position: float | None
    initial_state_contract: str
    outcome_status: str
    quality_eligible: bool
    quality_reason: str | None = None

    def as_record(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "episode_start": str(self.episode_start),
            "decision_time": str(self.decision_time),
            "context_asof_decision": list(self.context_asof_decision),
            "context_state_id": self.context_state_id,
            "context_namespace": self.context_namespace,
            "candidate_id": self.candidate_id,
            "parameter_version": self.parameter_version,
            "outcome_start": str(self.outcome_start),
            "outcome_end": str(self.outcome_end),
            "outcome_available_at": str(self.outcome_available_at),
            "net_return": self.net_return, "max_drawdown": self.max_drawdown,
            "turnover": self.turnover, "cost": self.cost, "trades": self.trades,
            "exposure": self.exposure, "terminal_position": self.terminal_position,
            "initial_state_contract": self.initial_state_contract,
            "outcome_status": self.outcome_status,
            "quality_eligible": self.quality_eligible,
            "quality_reason": self.quality_reason,
        }

    def usable_at(self, decision_time: pd.Timestamp) -> bool:
        """Guide 9.1: usable only once the outcome is finished AND published."""
        return (self.outcome_status == OUTCOME_COMPLETE
                and self.quality_eligible
                and self.outcome_available_at <= pd.Timestamp(decision_time))


@dataclass
class EpisodeGrid:
    """A set of episodes plus how it was laid out."""

    episodes: list[Episode] = field(default_factory=list)
    horizon_days: int = PILOT_HORIZON_DAYS
    overlapping: bool = False
    purge_days: int = 0

    def usable_at(self, decision_time: pd.Timestamp) -> list[Episode]:
        return [e for e in self.episodes if e.usable_at(decision_time)]

    def as_record(self) -> dict:
        statuses: dict[str, int] = {}
        for episode in self.episodes:
            statuses[episode.outcome_status] = statuses.get(episode.outcome_status, 0) + 1
        return {
            "schema": "crypto_regime_lab.episode_grid.v1",
            "episodes": len(self.episodes),
            "horizon_days": self.horizon_days,
            "overlapping": self.overlapping,
            "purge_days": self.purge_days,
            "outcome_status_counts": statuses,
            "eligible": sum(1 for e in self.episodes if e.quality_eligible),
            "grid_rule": (
                "the primary evidence grid is NON-OVERLAPPING. An overlapping grid is an "
                "extension and carries a purge plus an explicit dependence correction, because "
                "overlapping outcomes share bars and would otherwise shrink a standard error "
                "without adding information (guide 9.1)"),
            "availability_rule": (
                f"an outcome is usable at T only when outcome_end + {PUBLICATION_DELAY} "
                f"publication + {PROCESSING_DELAY} processing <= T. An unfinished horizon is not "
                "a small outcome, it is no outcome (T45)"),
        }


def horizon_from_holding_diagnostics(mean_holding_bars: float, bar_hours: float,
                                     *, registered_days: int = PILOT_HORIZON_DAYS) -> dict:
    """L06.1 — the horizon is chosen from holding diagnostics at DEVELOPMENT.

    The registered pilot horizon stands; the measured holding period is reported
    beside it so a reader can see whether 7 days is short or long for this alpha
    rather than taking it on faith.
    """
    measured_days = float(mean_holding_bars) * float(bar_hours) / 24.0
    return {
        "registered_horizon_days": int(registered_days),
        "measured_mean_holding_days": measured_days,
        "horizon_covers_mean_holding": measured_days <= registered_days,
        "ratio": measured_days / registered_days if registered_days else None,
        "rule": ("the horizon is registered before any response is estimated. The holding "
                 "diagnostic is reported next to it, not used to retune it after the fact"),
    }


def _grid_starts(index: pd.DatetimeIndex, horizon: pd.Timedelta, *, overlapping: bool,
                 step: pd.Timedelta | None) -> list[pd.Timestamp]:
    if len(index) == 0:
        raise EpisodeError("empty index")
    start, end = index[0], index[-1]
    stride = (step if overlapping and step is not None else horizon)
    out, cursor = [], start
    while cursor + horizon <= end:
        out.append(cursor)
        cursor = cursor + stride
    return out


def build_grid(index: pd.DatetimeIndex, *, horizon_days: int = PILOT_HORIZON_DAYS,
               overlapping: bool = False, step_days: int | None = None,
               purge_days: int = 0) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Lay out the (start, end) windows. Non-overlapping unless asked otherwise."""
    horizon = pd.Timedelta(days=horizon_days)
    if overlapping:
        if step_days is None or step_days >= horizon_days:
            raise EpisodeError("an overlapping grid needs a step shorter than the horizon")
        if purge_days <= 0:
            raise EpisodeError(
                "an overlapping grid must declare a purge; without it, adjacent episodes share "
                "bars and the dependence correction has nothing to work with (guide 9.1)")
    starts = _grid_starts(index, horizon, overlapping=overlapping,
                          step=pd.Timedelta(days=step_days) if step_days else None)
    return [(s, s + horizon) for s in starts]


def purge_overlaps(windows: list[tuple[pd.Timestamp, pd.Timestamp]],
                   purge_days: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Drop any window that starts inside the purge shadow of the previous KEPT one."""
    if purge_days <= 0:
        return list(windows)
    purge = pd.Timedelta(days=purge_days)
    kept: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for start, end in sorted(windows):
        if kept and start < kept[-1][1] + purge:
            continue
        kept.append((start, end))
    return kept


def dependence_correction(n_windows: int, horizon_days: int, step_days: int) -> dict:
    """How much an overlapping grid inflates the apparent sample size.

    Reported, never applied silently: the effective count is what a standard error
    should be built from, and the ratio makes the inflation visible.
    """
    if step_days <= 0:
        raise EpisodeError("step_days must be positive")
    overlap_factor = max(1.0, horizon_days / step_days)
    effective = n_windows / overlap_factor
    return {
        "windows": int(n_windows),
        "overlap_factor": float(overlap_factor),
        "effective_independent_windows": float(effective),
        "inflation_if_ignored": float(overlap_factor),
        "rule": ("an overlapping grid repeats each bar about horizon/step times. A standard error "
                 "built from the raw window count would be too small by roughly sqrt(overlap "
                 "factor); the effective count is reported so it cannot be used by accident"),
    }


def build_episodes(*, decision_times: list[pd.Timestamp], contexts: dict,
                   candidate_id: str, parameter_version: str,
                   outcome_fn, horizon_days: int = PILOT_HORIZON_DAYS,
                   initial_state_contract: str = "flat_at_episode_start",
                   overlapping: bool = False, purge_days: int = 0,
                   now: pd.Timestamp | None = None) -> EpisodeGrid:
    """Build the episode rows for one candidate.

    ``outcome_fn(start, end)`` returns the realised statistics or None when the
    window cannot be evaluated. ``contexts`` maps a decision time to the context
    AS OF that decision -- the function never receives anything from inside the
    outcome window, which is the structural form of the guide 9.1 rule.
    """
    grid = EpisodeGrid(horizon_days=horizon_days, overlapping=overlapping,
                       purge_days=purge_days)
    horizon = pd.Timedelta(days=horizon_days)
    for decision_time in decision_times:
        context = contexts.get(decision_time)
        if context is None:
            continue
        start, end = decision_time, decision_time + horizon
        available_at = end + PUBLICATION_DELAY + PROCESSING_DELAY
        outcome = outcome_fn(start, end)
        if outcome is None:
            status, eligible, reason = OUTCOME_INSUFFICIENT_BARS, False, "no evaluable window"
            stats = {}
        else:
            stats = outcome
            if now is not None and available_at > pd.Timestamp(now):
                status, eligible = OUTCOME_UNFINISHED, False
                reason = f"outcome_available_at {available_at} is after {now}"
            elif stats.get("terminal_position", 0.0) not in (0.0, None):
                # marked, NOT discarded: an open position at the horizon end is a real
                # outcome under the same account contract (guide L06.1)
                status, eligible, reason = OUTCOME_OPEN_POSITION, True, (
                    "position still open at the horizon end; marked to market under the same "
                    "account contract rather than counted as a closed win")
            else:
                status, eligible, reason = OUTCOME_COMPLETE, True, None
        grid.episodes.append(Episode(
            episode_id=f"{candidate_id}@{decision_time.isoformat()}",
            episode_start=start, decision_time=decision_time,
            context_asof_decision=tuple(float(v) for v in context.get("features", ())),
            context_state_id=context.get("state_id"),
            context_namespace=context.get("namespace"),
            candidate_id=candidate_id, parameter_version=parameter_version,
            outcome_start=start, outcome_end=end, outcome_available_at=available_at,
            net_return=stats.get("net_return"), max_drawdown=stats.get("max_drawdown"),
            turnover=stats.get("turnover"), cost=stats.get("cost"),
            trades=stats.get("trades"), exposure=stats.get("exposure"),
            terminal_position=stats.get("terminal_position"),
            initial_state_contract=initial_state_contract,
            outcome_status=status, quality_eligible=eligible, quality_reason=reason))
    return grid


def informativeness(panel: pd.DataFrame, incumbent_id: str) -> dict:
    """How many episodes can actually TELL two candidates apart.

    A horizon can cover the mean holding period and still be too short to carry a
    comparison: if the incumbent and a challenger both stayed flat all week, that
    episode contributes a paired delta of exactly zero and adds no information,
    however many of them there are. The similarity weights cannot fix this — they
    would just spread weight over episodes that all say nothing.
    """
    incumbent = panel[panel["candidate_id"] == incumbent_id].set_index("decision_time")
    rows, identical, total = [], 0, 0
    for candidate_id, group in panel.groupby("candidate_id"):
        if candidate_id == incumbent_id:
            continue
        group = group.set_index("decision_time")
        common = incumbent.index.intersection(group.index)
        if common.empty:
            continue
        delta = (group.loc[common, "net_return"] - incumbent.loc[common, "net_return"]).abs()
        zero = int((delta < 1e-12).sum())
        identical += zero
        total += len(common)
        rows.append({
            "candidate_id": candidate_id, "episodes": int(len(common)),
            "identical_to_incumbent": zero,
            "share_identical": float(zero / len(common)) if len(common) else None,
            "median_trades": float(group.loc[common, "trades"].median()),
        })
    return {
        "schema": "crypto_regime_lab.episode_informativeness.v1",
        "per_candidate": rows,
        "pairs": int(total), "pairs_with_zero_delta": int(identical),
        "share_uninformative": float(identical / total) if total else None,
        "reading": ("a pair with a delta of exactly zero is an episode in which BOTH the candidate "
                    "and the incumbent did nothing. It cannot distinguish them at any weighting. "
                    "A high share here means the registered horizon is short relative to the "
                    "alpha's trade frequency, and the response estimator is under-powered by "
                    "construction rather than by market conditions"),
        "horizon_is_registered": ("the horizon is NOT changed in response to this. Retuning it "
                                  "after seeing that it was under-powered would be selecting the "
                                  "experiment on its own result"),
    }


def to_frame(grid: EpisodeGrid) -> pd.DataFrame:
    """The response panel, one row per episode."""
    return pd.DataFrame([e.as_record() for e in grid.episodes])
