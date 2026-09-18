"""Guide 9.5 — campaigns, migration, and what a switch may not do to an open trade.

A campaign is one entry and everything that follows it until the position is flat
or terminal. It carries an IMMUTABLE ``entry_parameter_digest``, and that
immutability is the whole mechanism: an open trade keeps the stop and target it
entered with, whatever the selector decides afterwards. Only the policy for the
NEXT entry may change.

Two temptations are refused explicitly.

**Force-closing to make a switch happen.** A campaign that stays open for a long
time is reported ``TRANSITION_BLOCKED``, not unwound. Forcing it flat would
manufacture the very time edge the study is trying to measure. A forced unwind is
a separate ablation and it carries its own costs.

**Carrying indicator state across a parameter change.** An adaptive-length HMA
fitted under params A is not the same series under params B. Guide 9.5 forbids
both resetting it at every switch (which fabricates fresh signals) and carrying
it over without a contract (which silently mixes two models).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

CAMPAIGN_OPEN = "OPEN"
CAMPAIGN_CLOSED = "CLOSED"
CAMPAIGN_TRANSITION_BLOCKED = "TRANSITION_BLOCKED"

WARMUP_COLD = "COLD"
WARMUP_WARMING = "WARMING"
WARMUP_READY = "READY"

#: Beyond this a still-open campaign is reported stale rather than waited on silently.
STALE_CAMPAIGN_DAYS = 60


class CampaignError(ValueError):
    """An operation that would rewrite an entered campaign."""


@dataclass
class Campaign:
    """One entry and its lifetime. The entry digest never changes."""

    campaign_id: str
    opened_at: pd.Timestamp
    entry_parameter_digest: str
    entry_candidate_id: str
    status: str = CAMPAIGN_OPEN
    closed_at: pd.Timestamp | None = None
    protective_version: str | None = None

    def __post_init__(self) -> None:
        if self.protective_version is None:
            object.__setattr__(self, "protective_version", self.entry_candidate_id)

    def age_days(self, now: pd.Timestamp) -> float:
        return float((pd.Timestamp(now) - self.opened_at).total_seconds() / 86400.0)

    def mark_stale_if_needed(self, now: pd.Timestamp,
                             limit_days: int = STALE_CAMPAIGN_DAYS) -> str:
        if self.status == CAMPAIGN_OPEN and self.age_days(now) > limit_days:
            self.status = CAMPAIGN_TRANSITION_BLOCKED
        return self.status

    def close(self, when: pd.Timestamp) -> None:
        self.status = CAMPAIGN_CLOSED
        self.closed_at = pd.Timestamp(when)

    def migrate_entry_digest(self, new_digest: str) -> None:
        raise CampaignError(
            "entry_parameter_digest is immutable. An open trade stays protected by the parameters "
            "it entered with; only the policy for the NEXT entry may change (guide 9.5)")

    def as_record(self) -> dict:
        return {
            "campaign_id": self.campaign_id, "opened_at": str(self.opened_at),
            "entry_parameter_digest": self.entry_parameter_digest,
            "entry_candidate_id": self.entry_candidate_id,
            "protective_version": self.protective_version,
            "status": self.status,
            "closed_at": None if self.closed_at is None else str(self.closed_at),
            "immutability_rule": ("the entry digest and the protective version are fixed at entry. "
                                  "A later switch changes what the NEXT entry uses, never what "
                                  "this one is protected by (guide 9.5, T50)"),
        }


@dataclass
class PendingActivation:
    """A decision that has been made but cannot take effect yet."""

    selection_id: str
    requested_at: pd.Timestamp
    candidate_id: str
    reason: str
    activated_at: pd.Timestamp | None = None
    blocked_by: str | None = None

    @property
    def delay(self) -> pd.Timedelta | None:
        if self.activated_at is None:
            return None
        return self.activated_at - self.requested_at

    def as_record(self) -> dict:
        return {
            "selection_id": self.selection_id, "requested_at": str(self.requested_at),
            "candidate_id": self.candidate_id, "reason": self.reason,
            "activated_at": None if self.activated_at is None else str(self.activated_at),
            "activation_delay": None if self.delay is None else str(self.delay),
            "blocked_by": self.blocked_by,
            "rule": ("both the requested time and the ACTUAL delay are recorded. A policy that "
                     "reports only the moment it finally acted hides how long it wanted to act "
                     "and could not (guide 9.5)"),
        }


@dataclass
class IndicatorWarmup:
    """Warm state for a candidate's indicators, carried causally.

    Guide 9.5 forbids two shortcuts: resetting the indicator at every switch,
    which produces fresh-looking signals from a cold start, and carrying an
    adaptive-length state from one parameter set to another without a declared
    contract, which mixes two models into one series.
    """

    candidate_id: str
    required_bars: int
    bars_seen: int = 0
    source: str = "warmed_from_history_past_only"
    carried_from: str | None = None

    @property
    def status(self) -> str:
        if self.bars_seen == 0:
            return WARMUP_COLD
        return WARMUP_READY if self.bars_seen >= self.required_bars else WARMUP_WARMING

    def observe(self, bars: int = 1) -> None:
        self.bars_seen += int(bars)

    def carry_from(self, other: "IndicatorWarmup", *, contract: str | None = None) -> None:
        if contract is None:
            raise CampaignError(
                f"refusing to carry adaptive state from {other.candidate_id} to "
                f"{self.candidate_id} without a declared contract: an adaptive-length series is "
                "not the same series under different parameters (guide 9.5)")
        self.bars_seen = other.bars_seen
        self.carried_from = other.candidate_id
        self.source = f"carried_under_contract:{contract}"

    def as_record(self) -> dict:
        return {
            "candidate_id": self.candidate_id, "required_bars": self.required_bars,
            "bars_seen": self.bars_seen, "status": self.status, "source": self.source,
            "carried_from": self.carried_from,
            "rule": ("indicators are warmed from past-only history. They are never reset at a "
                     "switch, and adaptive state is never carried across parameter sets without "
                     "a contract (guide 9.5, T51)"),
        }


@dataclass
class CampaignBook:
    """Every campaign, open and closed, plus the activations waiting on them."""

    campaigns: list[Campaign] = field(default_factory=list)
    pending: list[PendingActivation] = field(default_factory=list)
    warmups: dict = field(default_factory=dict)

    def open_campaigns(self) -> list[Campaign]:
        return [c for c in self.campaigns
                if c.status in (CAMPAIGN_OPEN, CAMPAIGN_TRANSITION_BLOCKED)]

    def digests_in_use(self) -> set:
        return {c.entry_candidate_id for c in self.open_campaigns()}

    def request_activation(self, selection_id: str, candidate_id: str,
                           at: pd.Timestamp, reason: str) -> PendingActivation:
        blocked = "open_campaign" if self.open_campaigns() else None
        activation = PendingActivation(selection_id, pd.Timestamp(at), candidate_id, reason,
                                       blocked_by=blocked)
        if blocked is None:
            activation.activated_at = pd.Timestamp(at)
        self.pending.append(activation)
        return activation

    def try_activate_pending(self, at: pd.Timestamp) -> list[PendingActivation]:
        """Activate what the campaign boundary was blocking, once it is flat."""
        if self.open_campaigns():
            return []
        activated = []
        for activation in self.pending:
            if activation.activated_at is None:
                activation.activated_at = pd.Timestamp(at)
                activated.append(activation)
        return activated

    def as_record(self, now: pd.Timestamp | None = None) -> dict:
        if now is not None:
            for campaign in self.campaigns:
                campaign.mark_stale_if_needed(now)
        delays = [a.delay for a in self.pending if a.delay is not None]
        return {
            "schema": "crypto_regime_lab.campaign_book.v1",
            "campaigns": [c.as_record() for c in self.campaigns],
            "open": len(self.open_campaigns()),
            "transition_blocked": sum(1 for c in self.campaigns
                                      if c.status == CAMPAIGN_TRANSITION_BLOCKED),
            "pending_activations": [a.as_record() for a in self.pending],
            "activation_delays": [str(d) for d in delays],
            "max_activation_delay": str(max(delays)) if delays else None,
            "warmups": {k: v.as_record() for k, v in self.warmups.items()},
            "forced_unwind_used": False,
            "forced_unwind_rule": ("a long-open campaign is reported TRANSITION_BLOCKED and left "
                                   "alone. Forcing it flat to let a switch through would "
                                   "manufacture the time edge the study is measuring; a forced "
                                   "unwind is a separate ablation with its own costs (guide 9.5)"),
            "shadow_account_rule": ("a candidate that is not deployed keeps shadow INDICATOR "
                                    "state only. It never keeps a shadow financial account, "
                                    "because a second account would let a hypothetical equity "
                                    "curve leak into a deployment claim (guide 9.5)"),
        }
