"""Adapter base class enforcing the timing and ownership invariants.

The invariants are enforced here rather than trusted to each adapter:

  * position changes ONLY through ``on_fill``;
  * an entry decision made at the close of bar t may not be effective before the
    next execution boundary;
  * ``on_bar_close(t)`` may not read any array beyond index t;
  * levels that depend on the entry price are set in ``on_fill``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .contracts import BarDecision, ExecutionPhase, Fill, IntentKind, OrderIntent


class LookAheadViolation(RuntimeError):
    """Raised when an adapter reads data it could not have known at the decision."""


class PositionMutationViolation(RuntimeError):
    """Raised when an adapter tries to change its position without a fill."""


@dataclass
class MarketSlice:
    """Bars the adapter is allowed to see, plus a causal read guard."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    index: Any = None                 # optional pandas DatetimeIndex
    _cursor: int = field(default=-1, repr=False)

    def __post_init__(self) -> None:
        lengths = {len(self.open), len(self.high), len(self.low), len(self.close), len(self.volume)}
        if len(lengths) != 1:
            raise ValueError(f"OHLCV arrays have mismatched lengths: {lengths}")

    def __len__(self) -> int:
        return len(self.close)

    def set_cursor(self, t: int) -> None:
        self._cursor = t

    def guard(self, t: int) -> None:
        if self._cursor >= 0 and t > self._cursor:
            raise LookAheadViolation(
                f"read of bar {t} while deciding bar {self._cursor}: a decision may not use future data"
            )


@dataclass
class AdapterState:
    position: float = 0.0
    entry_price: float | None = None
    entry_index: int | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    pending_entry_side: int = 0        # staged but NOT yet filled
    pending_exit: bool = False
    realized_fills: int = 0


class AlphaAdapter(ABC):
    """Base adapter. Subclasses implement ``_decide`` and ``_levels_from_fill``."""

    alpha_id: str = "UNSET"
    adapter_version: str = "canonical_v1"
    timing_contract: str = "event_lifecycle_v3_next_open"

    def __init__(self, params: dict, market: MarketSlice) -> None:
        self.params = dict(params)
        self.market = market
        self.state = AdapterState()
        self.decisions: list[BarDecision] = []
        self._prepared = False

    # -- lifecycle --------------------------------------------------------

    @abstractmethod
    def warmup_bars(self) -> int:
        """Bars required before any decision may be emitted."""

    @abstractmethod
    def prepare(self) -> None:
        """Precompute indicator arrays. Must be causal for every index."""

    @abstractmethod
    def _decide(self, t: int) -> BarDecision:
        """Emit the decision for the completed bar t."""

    def _levels_from_fill(self, fill: Fill) -> list[OrderIntent]:
        """Protective levels derived from the ACTUAL fill price. Default: none."""
        return []

    # -- driving ----------------------------------------------------------

    def on_bar_close(self, t: int) -> BarDecision:
        if not self._prepared:
            self.prepare()
            self._prepared = True
        self.market.set_cursor(t)
        entering = self.state.position
        if t < self.warmup_bars():
            decision = BarDecision(
                index=t, position_entering_bar=entering, target_after_close=entering,
                warmup_ready=False, blocked_reason=f"warmup requires {self.warmup_bars()} bars",
            )
        else:
            decision = self._decide(t)
        self._validate(decision, entering)
        self.decisions.append(decision)
        return decision

    def on_fill(self, fill: Fill) -> list[OrderIntent]:
        """Apply a fill. The ONLY path that changes position."""
        before = self.state.position
        self.state.position = before + fill.quantity
        self.state.realized_fills += 1
        follow_ups: list[OrderIntent] = []
        if fill.intent_kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and before == 0.0:
            self.state.entry_price = fill.price
            self.state.entry_index = fill.index
            self.state.pending_entry_side = 0
            follow_ups = self._levels_from_fill(fill)
        if self.state.position == 0.0:
            self.state.entry_price = None
            self.state.entry_index = None
            self.state.stop_price = None
            self.state.take_profit_price = None
            self.state.pending_exit = False
        return follow_ups

    # -- invariants -------------------------------------------------------

    def _validate(self, decision: BarDecision, entering: float) -> None:
        if decision.position_entering_bar != entering:
            raise PositionMutationViolation(
                f"{self.alpha_id}: position_entering_bar must be the pre-bar exposure"
            )
        if self.state.position != entering:
            raise PositionMutationViolation(
                f"{self.alpha_id}: a decision changed the position without a fill "
                f"({entering} -> {self.state.position})"
            )
        for intent in decision.intents:
            if intent.decision_index != decision.index:
                raise ValueError("an intent must carry the index of the decision that produced it")
            if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT,
                               IntentKind.EXIT_ALL, IntentKind.REDUCE):
                if intent.earliest_phase is ExecutionPhase.RESTING_INTRABAR and \
                        intent.kind is not IntentKind.REDUCE:
                    raise ValueError(f"{intent.kind} may not be marked as already resting")

    # -- convenience ------------------------------------------------------

    def run(self) -> list[BarDecision]:
        """Drive every bar with no execution attached (synthetic decision tape)."""
        for t in range(len(self.market)):
            self.on_bar_close(t)
        return self.decisions

    def decision_frame(self):
        import pandas as pd

        rows = [d.as_record() for d in self.decisions]
        return pd.DataFrame(rows)
