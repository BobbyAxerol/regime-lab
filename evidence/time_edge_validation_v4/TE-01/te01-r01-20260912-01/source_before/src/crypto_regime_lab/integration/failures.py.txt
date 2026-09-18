"""L07.6 — what a continuous run does when something goes wrong.

Every failure mode here has the same shape of wrong answer: substitute
something plausible and carry on. A missing regime context becomes "assume the
last one"; a failed fit becomes "pick the best candidate we have"; an
interrupted artifact becomes "read what got written". Each substitution turns an
absence into a number, and a number cannot afterwards be told apart from a
measurement.

So each mode resolves to a NAMED outcome that keeps the validated incumbent, and
the reason travels with it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


class FailureError(RuntimeError):
    """Raised when a failure would have to be resolved by inventing data."""


#: Every recognised failure, and what the run does. "Choose a different
#: candidate" is absent on purpose: guide L07.6 says keep the validated
#: incumbent or a validated fallback, never a random parameter set.
FAILURE_MODES = {
    "MISSING_CONTEXT": "no regime observation is available at all -> hold the incumbent",
    "STALE_CONTEXT": "an observation exists but is older than its TTL -> hold the incumbent",
    "MODEL_FIT_FAILED": "the refit did not converge or errored -> keep the previous model",
    "INCOMPLETE_PROBE_PANEL": "a probe panel is short -> incomplete EVIDENCE, not bad performance",
    "OUT_OF_ORDER_JOB": "a job reported ready out of sequence -> activation still waits for READY",
    "SIMULATION_REJECT": "the engine refused an order -> recorded, position unchanged",
    "LIQUIDATION": "the engine liquidated -> recorded as a real economic event, never masked",
    "INTERRUPTED_ARTIFACT": "an artifact write did not complete -> the artifact is unreadable",
    "WORKER_FAILURE": "a worker died -> committed trials survive, uncommitted work is lost",
}

#: Outcomes a failure may resolve to.
OUTCOMES = ("HOLD_INCUMBENT", "KEEP_PREVIOUS_MODEL", "EVIDENCE_INCOMPLETE",
            "RECORDED_NO_POSITION_CHANGE", "RECORDED_ECONOMIC_EVENT", "REFUSED_TO_READ",
            "TRIALS_RETAINED")


@dataclass
class FailureRecord:
    mode: str
    at: pd.Timestamp
    outcome: str
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in FAILURE_MODES:
            raise FailureError(f"unknown failure mode {self.mode!r}; an unnamed failure is one "
                               "whose handling was never decided")
        if self.outcome not in OUTCOMES:
            raise FailureError(f"unknown outcome {self.outcome!r}")
        self.at = pd.Timestamp(self.at)

    def as_record(self) -> dict:
        return {"mode": self.mode, "at": str(self.at), "outcome": self.outcome,
                "explanation": FAILURE_MODES[self.mode], "detail": dict(self.detail)}


def classify_context(observation: dict | None, *, now: Any, ttl: Any) -> tuple[str, str]:
    """Missing and stale are different failures and must not be merged.

    Missing means the provider produced nothing — usually an upstream outage.
    Stale means it produced something and the world moved on — usually a
    cadence problem. Collapsing them into "no usable state" hides which one is
    happening, and they have opposite fixes.
    """
    if observation is None:
        return "MISSING_CONTEXT", "no regime observation available at this decision time"
    available_at = pd.Timestamp(observation["available_at"])
    age = pd.Timestamp(now) - available_at
    if age > pd.Timedelta(ttl):
        return "STALE_CONTEXT", f"observation is {age} old, past its TTL of {pd.Timedelta(ttl)}"
    return "OK", "observation is present and fresh"


class FailureLedger:
    """Every failure the run met, with what it did about it."""

    def __init__(self, *, incumbent_version: str) -> None:
        self.incumbent_version = incumbent_version
        self.records: list[FailureRecord] = []
        self.committed_trials: list[dict] = []

    def record(self, mode: str, at: Any, outcome: str, **detail: Any) -> FailureRecord:
        record = FailureRecord(mode=mode, at=at, outcome=outcome, detail=detail)
        self.records.append(record)
        return record

    # -- individual handlers --------------------------------------------
    def on_missing_or_stale_context(self, observation: dict | None, *, now: Any,
                                    ttl: Any) -> tuple[str, str]:
        mode, why = classify_context(observation, now=now, ttl=ttl)
        if mode != "OK":
            self.record(mode, now, "HOLD_INCUMBENT", why=why,
                        held_version=self.incumbent_version)
        return mode, why

    def on_failed_fit(self, *, at: Any, job_id: str, error: str,
                      previous_model_id: str | None) -> str:
        if previous_model_id is None:
            raise FailureError(
                f"{job_id} failed and there is no previous model to keep. Continuing would mean "
                "choosing parameters with no validated basis, which guide L07.6 forbids")
        self.record("MODEL_FIT_FAILED", at, "KEEP_PREVIOUS_MODEL",
                    job_id=job_id, error=error, kept_model_id=previous_model_id)
        return previous_model_id

    def on_incomplete_panel(self, *, at: Any, candidate_id: str, have: int,
                            need: int) -> dict:
        """An incomplete panel is missing evidence — never a poor score.

        Scoring a half-evaluated candidate as if it had performed badly is the
        version of this that biases everything downstream: candidates that were
        expensive to evaluate would look systematically worse than they are.
        """
        record = self.record("INCOMPLETE_PROBE_PANEL", at, "EVIDENCE_INCOMPLETE",
                             candidate_id=candidate_id, episodes_have=have, episodes_need=need)
        return {"candidate_id": candidate_id, "utility": None,
                "status": "EVIDENCE_INCOMPLETE", "counts_as_bad_performance": False,
                "record": record.as_record()}

    def on_out_of_order_job(self, *, at: Any, job_id: str, ready_at: Any) -> dict:
        """A job that reports late does not get to have finished early."""
        at, ready_at = pd.Timestamp(at), pd.Timestamp(ready_at)
        self.record("OUT_OF_ORDER_JOB", at, "HOLD_INCUMBENT",
                    job_id=job_id, ready_at=str(ready_at), observed_at=str(at))
        return {"job_id": job_id, "may_activate_from": str(max(at, ready_at)),
                "backdating_refused": True,
                "rule": "activation is never earlier than the job's own READY event"}

    def on_simulation_reject(self, *, at: Any, order_id: str, reason: str) -> dict:
        self.record("SIMULATION_REJECT", at, "RECORDED_NO_POSITION_CHANGE",
                    order_id=order_id, reason=reason)
        return {"order_id": order_id, "position_changed": False, "reason": reason}

    def on_liquidation(self, *, at: Any, campaign_id: str, equity_after: float) -> dict:
        self.record("LIQUIDATION", at, "RECORDED_ECONOMIC_EVENT",
                    campaign_id=campaign_id, equity_after=equity_after)
        return {"campaign_id": campaign_id, "equity_after": equity_after, "masked": False}

    def commit_trial(self, trial: dict) -> dict:
        """A committed trial survives a worker death; that is what committed means."""
        record = dict(trial)
        body = json.dumps(record, sort_keys=True, default=str)
        record["commit_digest"] = hashlib.sha256(body.encode()).hexdigest()[:16]
        self.committed_trials.append(record)
        return record

    def on_worker_failure(self, *, at: Any, worker_id: str,
                          uncommitted: int = 0) -> dict:
        self.record("WORKER_FAILURE", at, "TRIALS_RETAINED", worker_id=worker_id,
                    committed_trials=len(self.committed_trials), uncommitted_lost=uncommitted)
        return {"worker_id": worker_id, "committed_trials_retained": len(self.committed_trials),
                "uncommitted_lost": uncommitted}

    def read_artifact(self, path: Path, *, at: Any) -> dict:
        """Refuse a partial artifact rather than parse what happens to be there.

        The evidence writer is atomic, so a truncated file means the process
        died mid-write. Reading it would silently produce a shorter run.
        """
        path = Path(path)
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError) as exc:
            self.record("INTERRUPTED_ARTIFACT", at, "REFUSED_TO_READ",
                        path=str(path), error=repr(exc))
            raise FailureError(
                f"{path} is not a complete artifact ({exc.__class__.__name__}). The writer is "
                "atomic, so a partial file means the process died mid-write; reading what landed "
                "would silently shorten the run") from exc
        return payload

    def as_record(self) -> dict:
        by_mode: dict[str, int] = {}
        for record in self.records:
            by_mode[record.mode] = by_mode.get(record.mode, 0) + 1
        return {
            "schema": "crypto_regime_lab.failure_ledger.v1",
            "incumbent_version": self.incumbent_version,
            "records": [r.as_record() for r in self.records],
            "count": len(self.records),
            "by_mode": by_mode,
            "modes_declared": sorted(FAILURE_MODES),
            "modes_exercised": sorted(by_mode),
            "modes_never_exercised": sorted(set(FAILURE_MODES) - set(by_mode)),
            "exercised_means": (
                "the handler was DRIVEN and its outcome recorded. It does NOT mean the failure "
                "occurred during the run: a liquidation or a rejected order that never happened "
                "on this cell is still a path that must be shown to resolve correctly, and "
                "reporting it as observed would be a different and false claim"),
            "observed_during_the_run": [],
            "committed_trials": len(self.committed_trials),
            "random_parameter_selection_used": False,
            "rule": ("every failure resolves to the validated incumbent or a named incomplete "
                     "status. No failure is resolved by choosing different parameters, and none "
                     "is resolved by inventing a value (guide L07.6)"),
        }
