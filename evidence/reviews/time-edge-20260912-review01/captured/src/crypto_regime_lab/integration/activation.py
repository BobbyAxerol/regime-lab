"""L07.4 + guide 9.5 — when a parameter version actually takes effect.

A decision to switch is not a switch. Between the two sit an open campaign that
entered under the old parameters, protective orders that must keep referencing
the version that placed them, indicators for the new parameters that may not be
warm yet, and a queue of pending entry commands that are now ambiguous.

Guide 9.5 resolves each of those, and every resolution costs the new parameters
time. That delay is the honest price of switching, so it is measured and written
down (``requested_at`` vs ``activated_at``) rather than assumed away. A layer
that activated instantly would report a timing edge it never could have taken.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


class ActivationError(ValueError):
    """Raised when an activation would break the migration contract."""


#: What happens to an entry command that is queued when a switch lands.
#: Guide 9.5 requires the choice to be explicit; leaving it implicit means the
#: engine's queue order silently decides which parameter version traded.
PENDING_POLICIES = ("cancel_and_requote", "retain_under_entry_version")

#: A campaign ends only by reaching one of these. "The parameters changed" is
#: deliberately not among them: guide 9.5 forbids closing a position to make a
#: switch land sooner.
TERMINAL_REASONS = ("stop", "take_profit", "technical_exit", "forced_unwind_ablation")


def parameter_digest(params: dict) -> str:
    """A stable identity for a typed parameter set."""
    body = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return "pv-" + hashlib.sha256(body.encode()).hexdigest()[:16]


@dataclass
class ProtectiveOrder:
    """A stop or target that belongs to the campaign that placed it.

    Carries ``parameter_version`` because after a switch the book holds orders
    from two versions at once. Re-pricing an open stop with the new parameters
    would retroactively change the risk of a trade that was already entered.
    """

    order_id: str
    kind: str
    parameter_version: str
    price: float
    active: bool = True

    def as_record(self) -> dict:
        return {"order_id": self.order_id, "kind": self.kind,
                "parameter_version": self.parameter_version,
                "price": self.price, "active": self.active}


@dataclass
class OpenCampaign:
    """A position and everything that must survive a parameter switch."""

    campaign_id: str
    entry_parameter_digest: str
    opened_at: pd.Timestamp
    protective_orders: list[ProtectiveOrder] = field(default_factory=list)
    closed_at: pd.Timestamp | None = None
    close_reason: str | None = None
    stale: bool = False

    def __post_init__(self) -> None:
        self.opened_at = pd.Timestamp(self.opened_at)
        self._digest_locked = self.entry_parameter_digest

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def assert_digest_immutable(self) -> None:
        if self.entry_parameter_digest != self._digest_locked:
            raise ActivationError(
                f"{self.campaign_id}: entry_parameter_digest changed from {self._digest_locked} "
                f"to {self.entry_parameter_digest}. The digest names what this trade ENTERED "
                "with; rewriting it makes the trade look like it was taken under whichever "
                "parameters happen to be current (guide 9.5)")

    def close(self, when: Any, reason: str) -> None:
        if reason not in TERMINAL_REASONS:
            raise ActivationError(
                f"{self.campaign_id}: {reason!r} is not a terminal reason. A campaign is never "
                "closed because the parameters changed -- guide 9.5 forbids forcing a close to "
                f"manufacture a timing edge. Terminal reasons are {TERMINAL_REASONS}")
        self.closed_at = pd.Timestamp(when)
        self.close_reason = reason
        for order in self.protective_orders:
            order.active = False

    def mark_stale(self, now: Any, *, max_age_days: float) -> bool:
        if self.is_open and (pd.Timestamp(now) - self.opened_at).days > max_age_days:
            self.stale = True
        return self.stale

    def as_record(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "entry_parameter_digest": self.entry_parameter_digest,
            "opened_at": str(self.opened_at),
            "closed_at": None if self.closed_at is None else str(self.closed_at),
            "close_reason": self.close_reason,
            "stale": self.stale,
            "protective_orders": [o.as_record() for o in self.protective_orders],
        }


@dataclass
class IndicatorState:
    """Warmth of the indicators a parameter version needs.

    ``carry_from`` exists because an adaptive-length indicator's state is not
    portable: an HMA warmed at length 40 is not an HMA of length 90 that has
    seen the same bars. Guide 9.5 allows a carry only under a declared contract,
    so the contract is a required argument rather than an optional note.
    """

    parameter_version: str
    required_bars: int
    warm_bars: int = 0
    carried_from: str | None = None
    carry_contract: str | None = None

    @property
    def is_warm(self) -> bool:
        return self.warm_bars >= self.required_bars

    def observe(self, bars: int = 1) -> None:
        self.warm_bars += int(bars)

    def carry_from(self, other: "IndicatorState", *, contract: str) -> None:
        if not contract:
            raise ActivationError(
                f"{self.parameter_version}: carrying indicator state from "
                f"{other.parameter_version} needs a declared contract. An adaptive-length state "
                "is not portable between parameter sets, and an undeclared carry produces a "
                "crossover that never happened (guide 9.5)")
        self.warm_bars = min(other.warm_bars, self.required_bars)
        self.carried_from = other.parameter_version
        self.carry_contract = contract

    def as_record(self) -> dict:
        return {
            "parameter_version": self.parameter_version,
            "required_bars": self.required_bars,
            "warm_bars": self.warm_bars,
            "is_warm": self.is_warm,
            "carried_from": self.carried_from,
            "carry_contract": self.carry_contract,
        }


@dataclass
class Activation:
    """One parameter version becoming effective, with the delay it really took."""

    activation_id: str
    selection_id: str
    parameter_version: str
    requested_at: pd.Timestamp
    activated_at: pd.Timestamp | None = None
    blocked_reason: str | None = None
    pending_policy: str = "retain_under_entry_version"
    no_change: bool = False

    def __post_init__(self) -> None:
        self.requested_at = pd.Timestamp(self.requested_at)
        if self.pending_policy not in PENDING_POLICIES:
            raise ActivationError(f"pending_policy must be one of {PENDING_POLICIES}")

    @property
    def delay(self) -> pd.Timedelta | None:
        return None if self.activated_at is None else self.activated_at - self.requested_at

    def as_record(self) -> dict:
        return {
            "activation_id": self.activation_id,
            "selection_id": self.selection_id,
            "parameter_version": self.parameter_version,
            "requested_at": str(self.requested_at),
            "activated_at": None if self.activated_at is None else str(self.activated_at),
            "activation_delay_seconds": (None if self.delay is None
                                         else float(self.delay.total_seconds())),
            "blocked_reason": self.blocked_reason,
            "pending_policy": self.pending_policy,
            "no_change": self.no_change,
            # deliberately absent: activation_end. See events.assert_no_future_activation_end
        }


class ActivationTape:
    """The append-only record of every requested and effected activation."""

    def __init__(self, *, max_campaign_age_days: float = 30.0) -> None:
        self.activations: list[Activation] = []
        self.campaigns: dict[str, OpenCampaign] = {}
        self.indicators: dict[str, IndicatorState] = {}
        self.retired_versions: set[str] = set()
        self.max_campaign_age_days = float(max_campaign_age_days)
        self.active_version: str | None = None

    # -- registry -------------------------------------------------------
    def register_campaign(self, campaign: OpenCampaign) -> OpenCampaign:
        self.campaigns[campaign.campaign_id] = campaign
        return campaign

    def register_indicator(self, state: IndicatorState) -> IndicatorState:
        self.indicators[state.parameter_version] = state
        return state

    def versions_referenced_by_live_orders(self) -> set[str]:
        return {order.parameter_version
                for campaign in self.campaigns.values() if campaign.is_open
                for order in campaign.protective_orders if order.active}

    def retire(self, version: str) -> None:
        """Retire a version. It stays resolvable while any order references it."""
        live = self.versions_referenced_by_live_orders()
        if version in live:
            raise ActivationError(
                f"{version} still has live protective orders. Guide 9.5: retired bank parameters "
                "must exist until the campaigns they manage reach terminal; deleting one leaves "
                "an order pointing at nothing")
        self.retired_versions.add(version)

    def resolve(self, version: str) -> str:
        """A retired version still resolves — that is what retirement means here."""
        if version in self.retired_versions:
            return "RETIRED_STILL_RESOLVABLE"
        return "ACTIVE"

    # -- activation -----------------------------------------------------
    def request(self, activation_id: str, selection_id: str, parameter_version: str,
                at: Any, *, pending_policy: str = "retain_under_entry_version") -> Activation:
        activation = Activation(activation_id=activation_id, selection_id=selection_id,
                                parameter_version=parameter_version, requested_at=at,
                                pending_policy=pending_policy,
                                no_change=parameter_version == self.active_version)
        self.activations.append(activation)
        return activation

    def try_activate(self, activation: Activation, now: Any) -> Activation:
        """Activate only when guide 9.5's preconditions are all satisfied.

        Order matters. An open campaign blocks first, because no amount of
        indicator warmth makes it safe to switch the parameters a live position
        is protected by. Warmth is checked second, because activating a cold
        indicator produces a signal from a half-filled window.
        """
        now = pd.Timestamp(now)
        for campaign in self.campaigns.values():
            if campaign.is_open:
                campaign.mark_stale(now, max_age_days=self.max_campaign_age_days)
                activation.blocked_reason = (
                    "TRANSITION_BLOCKED_STALE_CAMPAIGN" if campaign.stale
                    else "TRANSITION_BLOCKED_OPEN_CAMPAIGN")
                return activation

        state = self.indicators.get(activation.parameter_version)
        if state is None:
            activation.blocked_reason = "NO_INDICATOR_STATE_REGISTERED"
            return activation
        if not state.is_warm:
            activation.blocked_reason = "WAITING_FOR_WARM_INDICATORS"
            return activation

        activation.activated_at = now
        activation.blocked_reason = None
        previous = self.active_version
        self.active_version = activation.parameter_version
        if previous is not None and previous != activation.parameter_version:
            try:
                self.retire(previous)
            except ActivationError:
                pass  # still referenced; it stays resolvable, which is the point
        return activation

    def as_record(self) -> dict:
        effected = [a for a in self.activations if a.activated_at is not None]
        delays = [a.delay.total_seconds() for a in effected]
        blocked: dict[str, int] = {}
        for activation in self.activations:
            if activation.blocked_reason:
                blocked[activation.blocked_reason] = blocked.get(activation.blocked_reason, 0) + 1
        return {
            "schema": "crypto_regime_lab.parameter_activation_tape.v1",
            "activations": [a.as_record() for a in self.activations],
            "requested": len(self.activations),
            "effected": len(effected),
            "no_change_triggers": sum(1 for a in self.activations if a.no_change),
            "blocked_by_reason": blocked,
            "max_activation_delay_seconds": max(delays) if delays else None,
            "mean_activation_delay_seconds": (sum(delays) / len(delays)) if delays else None,
            "campaigns": [c.as_record() for c in self.campaigns.values()],
            "indicators": [s.as_record() for s in self.indicators.values()],
            "retired_versions": sorted(self.retired_versions),
            "versions_referenced_by_live_orders": sorted(self.versions_referenced_by_live_orders()),
            "forced_unwind_used": False,
            "rules": {
                "open_campaign": ("an open trade stays protected by the parameters it entered "
                                  "with; the switch waits for terminal (guide 9.5)"),
                "warm_indicators": ("a new version waits until its indicators are causally warm; "
                                    "it never reinitialises to activate sooner"),
                "delay_is_recorded": ("requested_at and activated_at are both kept, so the price "
                                      "of switching is measured rather than assumed away"),
                "retirement": ("a retired version stays resolvable while any live order "
                               "references it"),
                "no_forced_close": ("a campaign is never closed to let a switch land; forced "
                                    "unwind is a separate ablation with its own costs"),
            },
        }
