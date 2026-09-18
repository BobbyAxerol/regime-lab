"""L07.3 — a refit is a job with a cutoff, a cost and its own account.

Three separate things go wrong when a refit is treated as a function call.

It reads too much: a job requested at T must not see data after T, however long
it takes to finish. It pays nothing: a refit that completes instantly lets a
parameter set become effective at the moment it was requested, which is a free
option on the intervening bars -- guide L07.3 names this directly ("không lấy
thời gian zero để được fill sớm"). And it contaminates: candidate evaluation
normally runs flat/reset, while the deployment account is carrying an open
position, so evaluating a candidate against the live account both mutates it and
scores the candidate on a state it will not inherit (guide 10.3).

Each of the three is a property here rather than a caller's discipline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


class JobError(ValueError):
    """Raised when a refit job would break isolation."""


#: How a refit's duration is decided. Every source is a MEASUREMENT or a frozen
#: scenario; "instant" is deliberately absent rather than discouraged.
LATENCY_SOURCES = ("measured_benchmark", "resource_budget_model", "frozen_scenario")


@dataclass(frozen=True)
class TrainingAccountContract:
    """The account a candidate is evaluated under — NOT the deployment account.

    Guide 10.3: "Candidate training evaluations có reset/initial-state contract
    riêng, không đồng nhất với deployment account." Keeping the two contracts as
    different objects makes the confusion a type error rather than a habit.
    """

    initial_state: str = "flat"
    resets_between_candidates: bool = True
    initial_capital_usdt: float = 20_000.0
    role: str = "training"

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.training_account_contract.v1",
            "initial_state": self.initial_state,
            "resets_between_candidates": self.resets_between_candidates,
            "initial_capital_usdt": self.initial_capital_usdt,
            "role": self.role,
            "rule": ("training evaluations reset so candidates are comparable; the deployment "
                     "account never resets. They are different contracts and a result from one "
                     "is not a result from the other (guide 10.3)"),
        }


@dataclass
class RefitJob:
    """One refit: requested, started, ready, and only then activatable."""

    job_id: str
    clock: str
    requested_at: pd.Timestamp
    data_cutoff: pd.Timestamp
    latency: pd.Timedelta
    latency_source: str
    started_at: pd.Timestamp | None = None
    ready_at: pd.Timestamp | None = None
    outcome: str = "PENDING"
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.requested_at = pd.Timestamp(self.requested_at)
        self.data_cutoff = pd.Timestamp(self.data_cutoff)
        self.latency = pd.Timedelta(self.latency)
        if self.latency <= pd.Timedelta(0):
            raise JobError(
                f"{self.job_id}: refit latency is {self.latency}. A zero or negative latency lets "
                "a parameter set take effect at the instant it was requested, which is a free "
                "option on every bar in between (guide L07.3)")
        if self.latency_source not in LATENCY_SOURCES:
            raise JobError(f"{self.job_id}: latency_source {self.latency_source!r} is not one of "
                           f"{LATENCY_SOURCES}; a duration with no provenance is an assumption")
        if self.data_cutoff > self.requested_at:
            raise JobError(
                f"{self.job_id}: data_cutoff {self.data_cutoff} is after the request "
                f"{self.requested_at}; a job cannot be commissioned to read the future")

    def start(self, at: Any) -> "RefitJob":
        at = pd.Timestamp(at)
        if at < self.requested_at:
            raise JobError(f"{self.job_id} cannot start before it was requested")
        self.started_at = at
        return self

    def finish(self, *, outcome: str = "READY", detail: dict | None = None) -> "RefitJob":
        if self.started_at is None:
            raise JobError(f"{self.job_id} finished without starting")
        self.ready_at = self.started_at + self.latency
        self.outcome = outcome
        self.detail = dict(detail or {})
        return self

    def may_read(self, timestamp: Any) -> bool:
        """L07.3 — the cutoff binds for the whole life of the job, not just at request."""
        return pd.Timestamp(timestamp) <= self.data_cutoff

    def assert_reads_are_legal(self, timestamps: list[Any]) -> dict:
        illegal = [str(pd.Timestamp(t)) for t in timestamps if not self.may_read(t)]
        if illegal:
            raise JobError(
                f"{self.job_id} read {len(illegal)} timestamp(s) after its cutoff "
                f"{self.data_cutoff}, first {illegal[0]}. A long-running job does not earn access "
                "to data that arrived while it ran")
        return {"reads_checked": len(timestamps), "cutoff": str(self.data_cutoff), "illegal": []}

    @property
    def effective_delay(self) -> pd.Timedelta | None:
        return None if self.ready_at is None else self.ready_at - self.requested_at

    def as_record(self) -> dict:
        return {
            "job_id": self.job_id,
            "clock": self.clock,
            "requested_at": str(self.requested_at),
            "data_cutoff": str(self.data_cutoff),
            "started_at": None if self.started_at is None else str(self.started_at),
            "ready_at": None if self.ready_at is None else str(self.ready_at),
            "latency_seconds": float(self.latency.total_seconds()),
            "latency_source": self.latency_source,
            "effective_delay_seconds": (None if self.effective_delay is None
                                        else float(self.effective_delay.total_seconds())),
            "outcome": self.outcome,
            "detail": self.detail,
        }


class RefitBenchmark:
    """Where a latency comes from, recorded so it can be argued with.

    A latency is a modelling choice that moves results, so it is derived from
    something measurable -- observed wall seconds per fit, scaled by how much of
    the resource budget the job may use -- and the derivation is kept next to the
    number.
    """

    def __init__(self, *, measured_seconds_per_fit: float, workers: int,
                 source: str = "measured_benchmark") -> None:
        if measured_seconds_per_fit <= 0:
            raise JobError("a benchmark of zero seconds per fit is not a measurement")
        if workers < 1:
            raise JobError("the resource budget must allow at least one worker")
        self.measured_seconds_per_fit = float(measured_seconds_per_fit)
        self.workers = int(workers)
        self.source = source

    def latency_for(self, *, fits: int) -> pd.Timedelta:
        if fits < 1:
            raise JobError("a refit that fits nothing is not a refit")
        # ceil-divide: three fits on two workers take two waves, not 1.5
        waves = -(-fits // self.workers)
        return pd.Timedelta(seconds=self.measured_seconds_per_fit * waves)

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.refit_benchmark.v1",
            "measured_seconds_per_fit": self.measured_seconds_per_fit,
            "workers": self.workers,
            "source": self.source,
            "rule": ("latency = measured seconds per fit x ceil(fits / workers). Partial waves "
                     "round UP: three fits on two workers occupy two waves, and rounding down "
                     "would hand the dynamic policy compute the resource budget forbids"),
        }


class TrainingJobRunner:
    """Runs refits without ever touching the deployment account.

    The deployment account is not passed in and cannot be reached. That is the
    isolation: not a rule the caller follows, but an object the caller does not
    hold.
    """

    def __init__(self, benchmark: RefitBenchmark,
                 contract: TrainingAccountContract | None = None) -> None:
        self.benchmark = benchmark
        self.contract = contract or TrainingAccountContract()
        self.jobs: list[RefitJob] = []

    def request(self, job_id: str, clock: str, at: Any, *, fits: int,
                data_cutoff: Any = None) -> RefitJob:
        at = pd.Timestamp(at)
        job = RefitJob(
            job_id=job_id, clock=clock, requested_at=at,
            data_cutoff=pd.Timestamp(data_cutoff) if data_cutoff is not None else at,
            latency=self.benchmark.latency_for(fits=fits),
            latency_source=self.benchmark.source)
        self.jobs.append(job)
        return job

    def run(self, job: RefitJob, *, read_timestamps: list[Any] | None = None,
            outcome: str = "READY", detail: dict | None = None) -> RefitJob:
        job.start(job.requested_at)
        if read_timestamps:
            job.assert_reads_are_legal(read_timestamps)
        return job.finish(outcome=outcome, detail=detail)

    def as_record(self) -> dict:
        completed = [j for j in self.jobs if j.ready_at is not None]
        delays = [j.effective_delay.total_seconds() for j in completed]
        return {
            "schema": "crypto_regime_lab.training_jobs.v1",
            "benchmark": self.benchmark.as_record(),
            "training_account_contract": self.contract.as_record(),
            "jobs": [j.as_record() for j in self.jobs],
            "requested": len(self.jobs),
            "completed": len(completed),
            "min_delay_seconds": min(delays) if delays else None,
            "max_delay_seconds": max(delays) if delays else None,
            "zero_latency_jobs": 0,
            "deployment_account_reachable_from_here": False,
            "isolation_rule": (
                "this runner never receives the deployment account, so a refit cannot mutate it. "
                "Candidate evaluation uses the training contract above, whose reset semantics are "
                "deliberately different from deployment (guide 10.3)"),
        }
