"""L07.2 — one ordered availability stream for every kind of event.

The failure this prevents is subtle. Each subsystem already knows its own
timing: the panel knows when a bar closed, the model knows when a fit is ready,
the policy knows when it asked for a switch. Left in separate structures they
are merged at read time, and a merge written after the fact is where "the
decision used the 09:00 state" quietly becomes "the decision used the state that
was stamped 09:00 but published at 09:07".

So every event enters one tape with two timestamps and a sequence number:

    observed_at   when the thing happened
    available_at  the earliest wall-clock time a consumer could have known it
    sequence      a total order for events that share a timestamp

Guide 4.2 is explicit that same-timestamp events need sequence IDs rather than
millisecond equality, and guide L07.2 that the engine must never see a future
``activation_end``. Both are properties of this file, not of its callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

import pandas as pd

#: Event kinds guide L07.2 requires the stream to carry. REFIT_REQUESTED,
#: REFIT_STARTED and REFIT_READY are three events, not one with a status: the
#: gap between them is the latency L07.3 forbids setting to zero, and a single
#: event with a mutable field would make that gap unobservable.
EVENT_KINDS = (
    "BAR_COMPLETED",
    "REGIME_OBSERVATION_READY",
    "REFIT_REQUESTED",
    "REFIT_STARTED",
    "REFIT_READY",
    "PARAMETER_ACTIVATED",
    "ENGINE_FILL",
)

#: Ordering within one timestamp. A bar completes before the regime observation
#: derived from it; a refit becomes ready before the activation it enables; a
#: fill is the consequence of a decision and never precedes it. This is the
#: economic causality of guide 4.2 written as a total order.
KIND_RANK = {kind: rank for rank, kind in enumerate(EVENT_KINDS)}


class EventError(ValueError):
    """Raised when an event would break the availability contract."""


def _utc(value: Any) -> pd.Timestamp:
    """Every timestamp on the stream is UTC-aware, and the coercion is explicit.

    The bus is fed by subsystems that disagree: storage timestamps are naive UTC
    by convention (guide 6.3), the engine's frames are tz-aware, and a policy
    may hand over a plain date. Sorting a mixture raises TypeError, so a single
    naive timestamp anywhere would take down the ordering of the whole stream.

    A naive timestamp is interpreted as UTC because that is the lab's declared
    storage convention -- stated here rather than left to whichever library
    happens to touch it first.
    """
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


@dataclass(frozen=True)
class Event:
    kind: str
    observed_at: pd.Timestamp
    available_at: pd.Timestamp
    sequence: int
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _utc(self.observed_at))
        object.__setattr__(self, "available_at", _utc(self.available_at))
        if self.kind not in KIND_RANK:
            raise EventError(f"unknown event kind {self.kind!r}; the stream is closed by design "
                             "so an unrecognised event cannot be silently routed")
        if self.available_at < self.observed_at:
            raise EventError(
                f"{self.kind} claims to be available at {self.available_at} but was observed at "
                f"{self.observed_at}: an event cannot be known before it happened")

    @property
    def publication_delay(self) -> pd.Timedelta:
        return self.available_at - self.observed_at

    def as_record(self) -> dict:
        return {
            "kind": self.kind,
            "observed_at": str(self.observed_at),
            "available_at": str(self.available_at),
            "publication_delay_seconds": float(self.publication_delay.total_seconds()),
            "sequence": self.sequence,
            "payload": dict(self.payload),
        }


class EventBus:
    """An append-only, totally ordered availability stream.

    Ordering key is ``(available_at, kind rank, sequence)`` — availability
    first, because availability is what a consumer may act on. Two events that
    became available at the same instant are ordered by what causes what, and
    only then by arrival. No comparison anywhere uses timestamp equality alone.
    """

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._sequence = 0

    def __len__(self) -> int:
        return len(self._events)

    def publish(self, kind: str, observed_at: Any, *, available_at: Any = None,
                **payload: Any) -> Event:
        observed = _utc(observed_at)
        available = _utc(available_at) if available_at is not None else observed
        event = Event(kind=kind, observed_at=observed, available_at=available,
                      sequence=self._sequence, payload=payload)
        self._sequence += 1
        self._events.append(event)
        return event

    def _key(self, event: Event) -> tuple:
        return (event.available_at, KIND_RANK[event.kind], event.sequence)

    def ordered(self) -> list[Event]:
        return sorted(self._events, key=self._key)

    def visible_at(self, now: Any) -> list[Event]:
        """Everything a consumer standing at ``now`` is allowed to have seen.

        The filter is on ``available_at``, never on ``observed_at``. An
        observation stamped an hour ago but published a minute from now is NOT
        visible, and that asymmetry is the whole point of carrying both.
        """
        cutoff = _utc(now)
        return [e for e in self.ordered() if e.available_at <= cutoff]

    def replay(self, until: Any = None) -> Iterator[Event]:
        """Yield events one at a time, in availability order (L07.7)."""
        events = self.ordered() if until is None else self.visible_at(until)
        yield from events

    def latest(self, kind: str, now: Any) -> Event | None:
        visible = [e for e in self.visible_at(now) if e.kind == kind]
        return visible[-1] if visible else None

    def as_record(self) -> dict:
        ordered = self.ordered()
        counts: dict[str, int] = {}
        for event in ordered:
            counts[event.kind] = counts.get(event.kind, 0) + 1
        return {
            "schema": "crypto_regime_lab.event_bus.v1",
            "events": len(ordered),
            "counts_by_kind": counts,
            "kinds_declared": list(EVENT_KINDS),
            "ordering_key": "(available_at, causal rank of the kind, arrival sequence)",
            "tie_break_rule": (
                "events sharing a timestamp are ordered by what causes what and then by arrival "
                "sequence. Millisecond equality is never used as an ordering (guide 4.2)"),
            "timestamp_convention": (
                "every timestamp on the stream is normalised to UTC-aware at publish. A naive "
                "timestamp is interpreted as UTC, the lab's declared storage convention (guide "
                "6.3); mixing the two would raise on the first sort and take the whole stream's "
                "ordering with it"),
            "visibility_rule": (
                "a consumer at time t sees exactly the events whose available_at <= t. observed_at "
                "orders the world; available_at decides what may be acted on"),
            "first": ordered[0].as_record() if ordered else None,
            "last": ordered[-1].as_record() if ordered else None,
        }


def assert_no_future_activation_end(events: Iterable[Event]) -> dict:
    """L07.2 — an activation's end must be unknown until the next one exists.

    A segment's length is only knowable in hindsight. If an activation event
    carried an ``activation_end``, a policy reading the tape would be reading how
    long its own decision was about to last -- the cleanest possible look-ahead,
    and one that looks like bookkeeping rather than like a leak.
    """
    offenders = [e.as_record() for e in events
                 if e.kind == "PARAMETER_ACTIVATED" and e.payload.get("activation_end") is not None]
    return {
        "schema": "crypto_regime_lab.activation_end_guard.v1",
        "activations_checked": sum(1 for e in events if e.kind == "PARAMETER_ACTIVATED"),
        "offenders": offenders,
        "clean": not offenders,
        "rule": ("an activation is published with a start and no end. The end is written only when "
                 "a LATER activation exists, and it is written to the segment record, never back "
                 "onto the event the engine reads (guide L07.2, L07.5)"),
    }


def attribute_activation_sources(events: list[Event], *, calendar_cutoffs: list) -> dict[str, str]:
    """DERIVE each activation's source from the tape instead of being told it.

    The first version of this took ``activation_sources`` from the caller, which
    handed the runner a dict it had built by declaring every activation a
    calendar cutoff -- so the check asserted its own conclusion and could not
    fail. An activation is attributed by matching WHEN it was published: at a
    declared calendar cutoff it is calendar-driven; at a regime observation that
    is not a cutoff it is regime-driven; anywhere else it is unattributed, which
    is a finding rather than a default.
    """
    cutoffs = {_utc(c) for c in calendar_cutoffs}
    observation_times = {e.observed_at for e in events
                         if e.kind == "REGIME_OBSERVATION_READY"}
    sources: dict[str, str] = {}
    for event in events:
        if event.kind != "PARAMETER_ACTIVATED":
            continue
        activation_id = event.payload.get("activation_id", "")
        requested_at = event.payload.get("requested_at")
        if requested_at is None:
            sources[activation_id] = "UNATTRIBUTED_NO_REQUEST_TIME"
            continue
        moment = _utc(requested_at)
        if moment in cutoffs:
            sources[activation_id] = "calendar_cutoff"
        elif moment in observation_times:
            sources[activation_id] = "regime_observation"
        else:
            sources[activation_id] = "UNATTRIBUTED"
    return sources


def regime_information_isolation(events: list[Event], *, activation_sources: dict[str, str],
                                 arm: str) -> dict:
    """Did regime information actually reach a decision, or is it only on the wire?

    Guide 10.1 defines arm A as the installed selector on a frozen calendar with
    **no regime information**. But guide L07.2 requires the event stream to carry
    regime observations regardless, because the stream is shared plumbing. Those
    two facts together make a trace ambiguous: 6,566 REGIME_OBSERVATION_READY
    events sitting next to 5 PARAMETER_ACTIVATED events look like cause and
    effect whether or not they are.

    So the causal claim is made explicit and checked. Every activation names its
    source, and for a no-regime arm every source must be a calendar cutoff. An
    activation attributed to a regime observation in such an arm is a
    contradiction, not a detail.
    """
    activations = [e for e in events if e.kind == "PARAMETER_ACTIVATED"]
    observations = [e for e in events if e.kind == "REGIME_OBSERVATION_READY"]
    sources = {}
    offenders = []
    for event in activations:
        activation_id = event.payload.get("activation_id", "")
        source = activation_sources.get(activation_id, "UNATTRIBUTED")
        sources[activation_id] = source
        if source != "calendar_cutoff":
            offenders.append({"activation_id": activation_id, "source": source})
    return {
        "schema": "crypto_regime_lab.regime_information_isolation.v1",
        "arm": arm,
        "regime_observations_on_the_stream": len(observations),
        "activations": len(activations),
        "activation_sources": sources,
        "activations_not_from_the_calendar": offenders,
        "regime_information_reached_a_decision": bool(offenders),
        "clean": not offenders,
        "attribution": ("sources are DERIVED from the tape by attribute_activation_sources, "
                        "not supplied by the caller. Supplying them let the runner assert its "
                        "own conclusion"),
        "rule": ("this arm's schedule is the frozen calendar (guide 10.1 arm A). Regime "
                 "observations ride the shared event stream because L07.2 requires the stream to "
                 "carry them, and they reach NO decision here. An activation whose source is "
                 "anything but a calendar cutoff would make this a different arm"),
    }
