"""L06.5 / guide 9.4 — four clocks that must never be merged.

    1. inference    — update the state when an observation becomes available
    2. switch       — choose among candidates that already exist; no search runs
    3. bank refresh — find and validate NEW candidates, on a schedule or when stale
    4. model retrain — refit centroids/features on a schedule or on covariate drift

The failure this prevents is a recursive trigger storm: a state change starts a
retrain, the retrain changes the state vocabulary, that reads as another change,
and the loop feeds itself. Guide 9.4 is blunt about it — a familiar market state
transition does not mean the model is broken.

The retrain detector therefore reads COVARIATE fit and novelty only. Using
strategy performance as a drift trigger is a different policy that has to be
evaluated on its own and may not be described as a market-only model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

INFERENCE = "inference"
SWITCH = "switch"
BANK_REFRESH = "bank_refresh"
MODEL_RETRAIN = "model_retrain"
CLOCKS = (INFERENCE, SWITCH, BANK_REFRESH, MODEL_RETRAIN)

#: The registered starting hypotheses of guide 8.6.
INFERENCE_INTERVAL = pd.Timedelta(hours=4)
MODEL_FIT_CADENCE = pd.Timedelta(days=28)
BANK_REFRESH_CADENCE = pd.Timedelta(days=180)     # the frozen baseline calendar

JOB_PENDING = "PENDING"
JOB_RUNNING = "RUNNING"
JOB_READY = "READY"
JOB_SUPERSEDED = "SUPERSEDED"
JOB_CANCELLED = "CANCELLED"
JOB_COALESCED = "COALESCED"


class ClockError(ValueError):
    """An operation that would merge two clocks or activate something early."""


@dataclass
class ClockCounters:
    """Three counters that guide 8.6 requires to stay separate."""

    inference: int = 0
    switch_assessments: int = 0
    switches_executed: int = 0
    bank_refreshes: int = 0
    model_retrains: int = 0

    def as_record(self) -> dict:
        return {
            "inference": self.inference,
            "switch_assessments": self.switch_assessments,
            "switches_executed": self.switches_executed,
            "bank_refreshes": self.bank_refreshes,
            "model_retrains": self.model_retrains,
            "rule": ("model retraining, bank refresh and switch frequency are three separate "
                     "counters. A high switch count says nothing about how often the model was "
                     "refitted, and vice versa (guide 8.6)"),
        }


@dataclass
class RefitJob:
    """A refit request. Its cutoff is frozen at the moment it was triggered."""

    job_id: str
    triggered_at: pd.Timestamp
    cutoff: pd.Timestamp
    clock: str
    status: str = JOB_PENDING
    ready_at: pd.Timestamp | None = None
    effective_at: pd.Timestamp | None = None
    superseded_by: str | None = None
    reason: str = ""

    def as_record(self) -> dict:
        return {
            "job_id": self.job_id, "clock": self.clock,
            "triggered_at": str(self.triggered_at), "cutoff": str(self.cutoff),
            "status": self.status,
            "ready_at": None if self.ready_at is None else str(self.ready_at),
            "effective_at": None if self.effective_at is None else str(self.effective_at),
            "superseded_by": self.superseded_by, "reason": self.reason,
            "cutoff_rule": ("the cutoff is fixed at the trigger. A job that takes a long time may "
                            "NOT quietly extend its cutoff to include data that arrived while it "
                            "ran (guide 9.4)"),
        }


@dataclass
class Scheduler:
    """Deterministic coalesce / cancel / supersede, with no retroactive activation."""

    jobs: list[RefitJob] = field(default_factory=list)
    counters: ClockCounters = field(default_factory=ClockCounters)
    coalesce_window: pd.Timedelta = pd.Timedelta(days=1)

    def _active(self, clock: str) -> list[RefitJob]:
        return [j for j in self.jobs if j.clock == clock
                and j.status in (JOB_PENDING, JOB_RUNNING)]

    def trigger(self, job_id: str, clock: str, at: pd.Timestamp,
                reason: str = "") -> RefitJob:
        """Request a refit. A near-duplicate coalesces; a later one supersedes."""
        if clock not in (BANK_REFRESH, MODEL_RETRAIN):
            raise ClockError(f"{clock} is not a refit clock; inference and switch never refit")
        at = pd.Timestamp(at)
        for existing in self._active(clock):
            if at - existing.triggered_at <= self.coalesce_window:
                # two triggers close together are ONE piece of work
                job = RefitJob(job_id, at, existing.cutoff, clock, status=JOB_COALESCED,
                               reason=f"coalesced into {existing.job_id}: {reason}")
                job.superseded_by = existing.job_id
                self.jobs.append(job)
                return job
            existing.status = JOB_SUPERSEDED
            existing.superseded_by = job_id
            existing.reason = (existing.reason + " | superseded by a newer trigger").strip(" |")
        job = RefitJob(job_id, at, at, clock, status=JOB_PENDING, reason=reason)
        self.jobs.append(job)
        return job

    def complete(self, job_id: str, ready_at: pd.Timestamp) -> RefitJob:
        job = next((j for j in self.jobs if j.job_id == job_id), None)
        if job is None:
            raise ClockError(f"unknown job {job_id}")
        ready_at = pd.Timestamp(ready_at)
        if ready_at < job.triggered_at:
            raise ClockError("a job cannot be ready before it was triggered")
        if job.status == JOB_SUPERSEDED:
            # an out-of-order completion of stale work is DISCARDED, not applied
            job.ready_at = ready_at
            job.reason = (job.reason + " | completed after being superseded; result discarded"
                          ).strip(" |")
            return job
        if job.status == JOB_COALESCED:
            job.ready_at = ready_at
            return job
        job.status = JOB_READY
        job.ready_at = ready_at
        return job

    def activate(self, job_id: str, at: pd.Timestamp) -> RefitJob:
        """``effective_at >= ready_at``. There is no retroactive activation."""
        job = next((j for j in self.jobs if j.job_id == job_id), None)
        if job is None:
            raise ClockError(f"unknown job {job_id}")
        at = pd.Timestamp(at)
        if job.status != JOB_READY:
            raise ClockError(
                f"{job_id} is {job.status}; only a READY job may be activated. A superseded or "
                "coalesced job never becomes effective (guide 9.4)")
        if job.ready_at is None or at < job.ready_at:
            raise ClockError(
                f"effective_at {at} precedes ready_at {job.ready_at}; backdating an activation "
                "would let a decision claim knowledge it did not have (T49)")
        job.effective_at = at
        if job.clock == MODEL_RETRAIN:
            self.counters.model_retrains += 1
        else:
            self.counters.bank_refreshes += 1
        return job

    def incumbent_runs_while_pending(self, clock: str) -> bool:
        """Guide 9.4: while a refit is pending, the incumbent operates."""
        return bool(self._active(clock))

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.clock_scheduler.v1",
            "clocks": list(CLOCKS),
            "cadences": {
                "inference": str(INFERENCE_INTERVAL),
                "model_retrain": str(MODEL_FIT_CADENCE),
                "bank_refresh": str(BANK_REFRESH_CADENCE) + " (frozen baseline calendar)",
                "switch": "every eligible inference boundary, when needed",
            },
            "counters": self.counters.as_record(),
            "jobs": [j.as_record() for j in self.jobs],
            "coalesce_window": str(self.coalesce_window),
            "separation_rule": ("a state change never triggers a retrain and a retrain never "
                                "triggers a parameter search. Merging any two of these clocks is "
                                "what produces a recursive trigger storm (guide 9.4, T52)"),
            "triggered_refresh_is_a_separate_variant": True,
        }


def retrain_trigger(*, novelty_rate: float, fit_residual_drift: float,
                    strategy_performance: float | None = None,
                    novelty_threshold: float = 0.10,
                    residual_threshold: float = 0.50) -> dict:
    """Whether to retrain, from COVARIATE evidence only.

    ``strategy_performance`` is accepted so it can be recorded and explicitly
    IGNORED. Guide 9.4: using performance as a drift trigger is a different policy
    that must be evaluated separately and may not be called a market-only model.
    """
    fires = novelty_rate > novelty_threshold or fit_residual_drift > residual_threshold
    return {
        "should_retrain": bool(fires),
        "novelty_rate": float(novelty_rate),
        "fit_residual_drift": float(fit_residual_drift),
        "novelty_threshold": novelty_threshold, "residual_threshold": residual_threshold,
        "strategy_performance_seen": strategy_performance,
        "strategy_performance_used": False,
        "rule": ("the detector reads covariate fit and novelty only. A performance-triggered "
                 "retrain is a DIFFERENT policy: it must be evaluated on its own and it may not "
                 "be described as a market-only model (guide 9.4)"),
        "familiar_state_change_is_not_drift": (
            "a transition between states the model already knows is the model working, not the "
            "model breaking. Only movement OUTSIDE the training support counts here"),
    }
