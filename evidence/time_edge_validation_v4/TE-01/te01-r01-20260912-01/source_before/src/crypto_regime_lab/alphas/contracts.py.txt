"""Typed adapter contract shared by the four alphas (guide 4.2, 4.4, L02.3-L02.7).

The single rule this file exists to enforce: an adapter OWNS indicators and
decisions and owns nothing else. It emits intents at a bar close; the engine
decides whether, when and at what price they fill. An adapter never sets a
position from an intent, and any level that depends on the entry price is
derived in ``on_fill`` from the ACTUAL fill, never from the signal bar's close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentKind(str, Enum):
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT_ALL = "exit_all"
    REDUCE = "reduce"                 # partial close, e.g. a TP ladder rung
    SET_PROTECTION = "set_protection"  # resting stop / take-profit bracket
    AMEND_PROTECTION = "amend_protection"
    CANCEL_PROTECTION = "cancel_protection"


class ExecutionPhase(str, Enum):
    """Earliest phase at which an intent may become effective (guide 4.2)."""

    NEXT_OPEN = "next_open"           # market order staged at a close decision
    RESTING_INTRABAR = "resting_intrabar"  # protective order already working


class QuantityBasis(str, Enum):
    FIXED_NOTIONAL = "fixed_notional"       # experiment-level notional
    FRACTION_OF_REMAINING = "fraction_of_remaining"  # A-HASH TP2 (finding AH-06)
    FRACTION_OF_ENTRY = "fraction_of_entry"
    ALL = "all"


class ExitReason(str, Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LADDER = "take_profit_ladder"
    TIME_STOP = "time_stop"
    TECHNICAL = "technical"
    SIGNAL_FLIP = "signal_flip"


@dataclass(frozen=True)
class OrderIntent:
    """One staged instruction. Carries no fill price and no resulting position."""

    kind: IntentKind
    decision_index: int
    earliest_phase: ExecutionPhase
    reason: str
    quantity_basis: QuantityBasis = QuantityBasis.ALL
    quantity_value: float | None = None
    price: float | None = None          # a LEVEL for protective orders, never a fill price
    stop_price: float | None = None
    take_profit_price: float | None = None
    ladder: tuple[tuple[float, float], ...] = ()   # ((level, fraction), ...) in trigger order
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT, IntentKind.EXIT_ALL):
            if self.earliest_phase is not ExecutionPhase.NEXT_OPEN:
                raise ValueError(
                    f"{self.kind} is a close decision and must be staged for the next open "
                    "(guide 4.2: a signal close cannot fill at that same close)"
                )


@dataclass(frozen=True)
class Fill:
    """An engine-reported fill. The only thing that may change an adapter's position."""

    index: int
    side: int                # +1 long, -1 short
    quantity: float          # signed change in position
    price: float
    intent_kind: IntentKind
    fee: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BarDecision:
    """Everything an adapter produces for one completed bar."""

    index: int
    position_entering_bar: float     # pre-bar exposure (finding HM-02)
    target_after_close: float        # the intent AFTER this close; not a position
    intents: list[OrderIntent] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warmup_ready: bool = True
    blocked_reason: str | None = None

    def as_record(self) -> dict:
        return {
            "index": self.index,
            "position_entering_bar": self.position_entering_bar,
            "target_after_close": self.target_after_close,
            "warmup_ready": self.warmup_ready,
            "blocked_reason": self.blocked_reason,
            "intents": [
                {
                    "kind": i.kind.value,
                    "decision_index": i.decision_index,
                    "earliest_phase": i.earliest_phase.value,
                    "reason": i.reason,
                    "quantity_basis": i.quantity_basis.value,
                    "quantity_value": i.quantity_value,
                    "price": i.price,
                    "stop_price": i.stop_price,
                    "take_profit_price": i.take_profit_price,
                    "ladder": [list(x) for x in i.ladder],
                    "metadata": i.metadata,
                }
                for i in self.intents
            ],
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class AlphaCertification:
    """The record guide 13.3 requires for every alpha, ready or not."""

    alpha_id: str
    raw_source_digest: str
    adapter_version: str | None
    status: str
    indicator_convention: str | None = None
    timing_contract: str | None = None
    partial_quantity_convention: str | None = None
    engine_capabilities_verified: tuple[str, ...] = ()
    semantic_delta_refs: tuple[str, ...] = ()
    golden_trace_refs: tuple[str, ...] = ()
    market_test_evidence_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.alpha_certification.v1",
            "alpha_id": self.alpha_id,
            "raw_source_digest": self.raw_source_digest,
            "adapter_version": self.adapter_version,
            "status": self.status,
            "indicator_convention": self.indicator_convention,
            "timing_contract": self.timing_contract,
            "partial_quantity_convention": self.partial_quantity_convention,
            "engine_capabilities_verified": list(self.engine_capabilities_verified),
            "semantic_delta_refs": list(self.semantic_delta_refs),
            "golden_trace_refs": list(self.golden_trace_refs),
            "market_test_evidence_refs": list(self.market_test_evidence_refs),
            "blockers": list(self.blockers),
        }
