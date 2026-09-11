"""A02/A03/A04 — continuous account on QuantBT's native-event strategy route.

The lab adapter is the decision source; QuantBT is the execution authority. Every
fill the adapter sees is one QuantBT actually produced (``context.fills_this_bar``),
never a lab-built next-open guess. Commands emitted while handling a fill are
follow-ups executed on the next bar, so A-HMA's gap-repair EXIT_ALL and A-VWAP's
amend path reach the position instead of being dropped.

A run that cannot express an intent (unmapped kind), or whose engine result is
missing, is ``NOT_EVALUATED``: it is never scored as a return. Initial and later
versions activate only at/after ``max(requested_at_bar, warmup)``; nothing is
backdated to bar 0 (A02).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..alphas.base import Fill, IntentKind, MarketSlice
from ..alphas.contracts import BarDecision, OrderIntent
from ..experiments.evaluator import ACCOUNT, build_adapter
from ..quantbt_bridge.routes import ONE_WAY_TAKER_FEE, SLIPPAGE_BPS, bound_fee_kwargs

SYMBOL = "S"


class EventAccountError(RuntimeError):
    """The event account cannot be run under the registered contract."""


@dataclass
class EventAccountRun:
    equity: np.ndarray
    positions: np.ndarray
    fills: list[dict]
    index: pd.DatetimeIndex
    version_by_bar: list[str]
    entries: int
    engine_fill_count: int
    unmapped_intents: list[dict] = field(default_factory=list)
    status: str = "EVALUATED"
    diagnostics: dict = field(default_factory=dict)

    @property
    def scored(self) -> bool:
        return self.status == "EVALUATED"


def _side_sign(value: Any) -> int:
    text = getattr(value, "value", value)
    return 1 if str(text).lower() in {"buy", "long", "1", "1.0"} else -1


def _position(context) -> float:
    positions = getattr(context, "positions", None)
    if positions is None:
        return 0.0
    if hasattr(positions, "get"):
        return float(positions.get(SYMBOL, 0.0) or 0.0)
    array = np.asarray(positions, dtype=float).reshape(-1)
    return float(array[0]) if array.size else 0.0


class EventAccountStrategy:
    """One carried account; version switches are pending until warm and flat."""

    def __init__(self, alpha_id: str, frame: pd.DataFrame, market: MarketSlice, *,
                 initial, schedule, unit_notional: float = ACCOUNT["entry_notional_usdt"],
                 warmup_policy: str = "adapter_warmup_bars") -> None:
        self.alpha_id = alpha_id
        self.frame = frame
        self.market = market
        self.initial = initial
        self.schedule = list(schedule)
        self.unit_notional = float(unit_notional)
        self.warmup_policy = warmup_policy
        self.adapter = None
        self.active = None
        self.shadow: dict[str, tuple[Any, Any, int]] = {}
        self.version_by_bar: list[str] = []
        self.entries = 0
        self.unmapped: list[dict] = []
        self.fills_out: list[dict] = []
        self.switches: list[dict] = []
        self._active_ready = initial.requested_at_bar <= 0
        self._active_since: int | None = None
        self._active_warmup: int = 0
        if self._active_ready:
            self.active = initial
            self.adapter = build_adapter(self.alpha_id, initial.params, self.market)
            self._active_since = 0
            self._active_warmup = int(self.adapter.warmup_bars())

    # -- command projection ------------------------------------------------

    def _place(self, timestamp, side: int, qty: float, order_type, *, price=None,
               trigger=None, reduce_only=False, tag=None, oco=None):
        import quantbt as q

        return q.OrderCommand(
            timestamp=timestamp, action=q.OrderAction.PLACE, symbol=SYMBOL,
            side=q.OrderSide.BUY if side > 0 else q.OrderSide.SELL,
            order_type=order_type, qty=float(qty), price=price, trigger_price=trigger,
            reduce_only=bool(reduce_only), tag=tag, oco_group_id=oco)

    def _current_price(self, context) -> float:
        close = context.close
        if hasattr(close, "__len__"):
            return float(np.asarray(close, dtype=float).reshape(-1)[-1])
        return float(close)

    def _intent_commands(self, intent: OrderIntent, context):
        import quantbt as q

        if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT):
            side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
            price = self._current_price(context)
            if not np.isfinite(price) or price <= 0:
                raise EventAccountError("entry close is not usable")
            qty = self.unit_notional / price
            return [self._place(context.timestamp, side, qty, q.OrderType.MARKET,
                                tag="entry", reduce_only=False)]
        if intent.kind is IntentKind.EXIT_ALL:
            position = _position(context)
            if position == 0.0:
                return []
            return [self._place(context.timestamp, -int(np.sign(position)), abs(position),
                                q.OrderType.MARKET, tag="exit", reduce_only=True)]
        if intent.kind is IntentKind.SET_PROTECTION:
            position = _position(context)
            if position == 0.0:
                return []
            side = -int(np.sign(position))
            qty = abs(position)
            oco = "protection"
            commands = []
            if intent.stop_price is not None:
                commands.append(self._place(context.timestamp, side, qty, q.OrderType.STOP_MARKET,
                                            trigger=float(intent.stop_price), reduce_only=True,
                                            tag="stop", oco=oco))
            target = intent.take_profit_price
            if target is None and intent.ladder:
                target = intent.ladder[-1][0]
            if target is not None:
                commands.append(self._place(context.timestamp, side, qty, q.OrderType.LIMIT,
                                            price=float(target), reduce_only=True, tag="tp",
                                            oco=oco))
            return commands
        # AMEND/CANCEL/REDUCE and partial ladders are not carried on this route.
        self.unmapped.append({"kind": str(getattr(intent.kind, "value", intent.kind)),
                              "bar": int(context.bar_index), "reason": "unmapped_on_event_route"})
        return []

    # -- lifecycle ---------------------------------------------------------

    def initialize(self, context):
        return []

    def on_bar_close(self, context):
        bar = int(context.bar_index)
        if not self._active_ready and bar >= self.initial.requested_at_bar:
            self._active_ready = True
            self.active = self.initial
            self.adapter = build_adapter(self.alpha_id, self.active.params, self.market)
            self._active_since = bar
            self._active_warmup = int(self.adapter.warmup_bars())

        if self.adapter is None:
            self.version_by_bar.append("FLAT_UNTIL_READY")
            return []

        commands = []
        # 1. Actual engine fills drive the adapter; follow-ups become commands now.
        for event in (getattr(context, "fills_this_bar", None) or []):
            side = _side_sign(getattr(event, "side", 1))
            tag = str(getattr(event, "tag", "") or "")
            fee = float(getattr(event, "fee", 0.0) or 0.0)
            price = float(getattr(event, "price", float("nan")))
            qty = float(getattr(event, "qty", 0.0) or 0.0)
            self.fills_out.append({"bar_index": bar, "side": side, "qty": qty, "price": price,
                                   "fee": fee, "tag": tag})
            kind = IntentKind.ENTER_LONG if (tag == "entry" and side > 0) else (
                IntentKind.ENTER_SHORT if (tag == "entry" and side < 0) else IntentKind.EXIT_ALL)
            follow_ups = self.adapter.on_fill(Fill(index=bar, side=side, quantity=qty,
                                                   price=price, intent_kind=kind,
                                                   metadata={"tag": tag, "fee": fee}))
            for follow in follow_ups or []:
                commands.extend(self._intent_commands(follow, context))

        # 2. Pending versions warm on every bar and may activate when flat.
        while self.schedule and self.schedule[0].requested_at_bar <= bar:
            window = self.schedule.pop(0)
            candidate = build_adapter(self.alpha_id, window.params, self.market)
            if window.required_warm_bars is None:
                window.required_warm_bars = int(candidate.warmup_bars())
            self.shadow[window.activation_id] = (candidate, window, bar)
        for activation_id, (candidate, window, requested_bar) in list(self.shadow.items()):
            warm_bars = bar - requested_bar
            if _position(context) != 0.0 or warm_bars < (window.required_warm_bars or 0):
                continue
            self.adapter = candidate
            self.active = window
            self._active_since = bar
            self._active_warmup = int(window.required_warm_bars or 0)
            self.switches.append({"activation_id": activation_id, "effective_at_bar": bar,
                                  "requested_at_bar": window.requested_at_bar})
            del self.shadow[activation_id]

        # A02: nothing decides before the active version's indicators are warm.
        if self._active_since is not None and bar - self._active_since < self._active_warmup:
            self.version_by_bar.append("WARMING")
            return commands

        # 3. Active adapter decides; only its intents become commands.
        self.version_by_bar.append(self.active.parameter_version)
        decision: BarDecision = self.adapter.on_bar_close(bar)
        for intent in decision.intents:
            if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT):
                self.entries += 1
            commands.extend(self._intent_commands(intent, context))
        return commands

    def finalize(self, context):
        return []


def run_event_account(alpha_id: str, frame: pd.DataFrame, *, initial, schedule,
                      backend: str = "native_event", initial_capital: float = 20000.0,
                      one_way_fee: float = ONE_WAY_TAKER_FEE,
                      slippage_bps: float = SLIPPAGE_BPS) -> EventAccountRun:
    """Run one carried account on the public native-event strategy route."""
    import quantbt as q

    arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
    market = MarketSlice(*arrays, index=frame.index)
    strategy = EventAccountStrategy(alpha_id, frame, market, initial=initial, schedule=schedule)
    endpoint = q.QuantBTEndpoint.native_event_strategy(
        account=q.AccountConfig(initial_capital=initial_capital),
        slippage_bps=slippage_bps, symbols=[SYMBOL], use_funding=False,
        **bound_fee_kwargs(one_way_fee),
    )
    result = endpoint.simulate(data=frame, strategy=strategy)
    status = "EVALUATED" if not strategy.unmapped else "NOT_EVALUATED"
    return EventAccountRun(
        equity=np.asarray(result.equity, dtype=float).reshape(-1),
        positions=np.asarray(result.positions, dtype=float).reshape(-1),
        fills=strategy.fills_out,
        index=frame.index,
        version_by_bar=strategy.version_by_bar,
        entries=strategy.entries,
        engine_fill_count=len(getattr(result, "fills", None) or []),
        unmapped_intents=strategy.unmapped,
        status=status,
        diagnostics={"engine_backend": backend, "switches": strategy.switches,
                     "fee_binding": bound_fee_kwargs(one_way_fee)},
    )
