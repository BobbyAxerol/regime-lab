"""A02/A03/A04 — continuous account on QuantBT's native-event strategy route.

The lab adapter is the decision source; QuantBT is the execution authority. Every
fill the adapter sees is one QuantBT actually produced (``context.fills_this_bar``),
never a lab-built next-open guess. Commands emitted while handling a fill are
follow-ups executed on the next bar, so A-HMA's gap-repair EXIT_ALL and A-VWAP's
amend path reach the position instead of being dropped.

FUP-01 command projection (RF02.1/RF02.2, T17/T19):
  * ``SET_PROTECTION`` -> stop/limit bracket; when ``intent.ladder`` is present,
    one reduce-only LIMIT per rung sized as a fraction of the REMAINING position
    (A-HASH ``fraction_of_remaining`` semantics), fees paid per partial fill;
  * ``AMEND_PROTECTION`` -> engine ``OrderAction.AMEND`` on the tracked
    protection order id, at the engine effective phase (next bar);
  * ``CANCEL_PROTECTION`` -> engine ``OrderAction.CANCEL`` on the tracked id;
  * ``REDUCE`` -> market reduce-only sized from ``quantity_basis`` /
    ``quantity_value``, never more than the open position;
  * every engine-reported order id is tracked per parameter version, and every
    command is recorded with its declared intent phase and the engine effective
    phase. An intent that cannot be projected stays ``unsupported`` and forces
    ``NOT_EVALUATED`` (A03/G5): it is never silently dropped.

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
from ..alphas.contracts import BarDecision, OrderIntent, QuantityBasis
from ..experiments.evaluator import ACCOUNT, build_adapter
from ..quantbt_bridge.routes import ONE_WAY_TAKER_FEE, SLIPPAGE_BPS, bound_fee_kwargs

SYMBOL = "S"
POSITION_TOLERANCE = 1e-6
ENGINE_EFFECTIVE_PHASE = "next_bar"


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
    rejections: list[dict] = field(default_factory=list)
    status: str = "EVALUATED"
    diagnostics: dict = field(default_factory=dict)
    commands: list[dict] = field(default_factory=list)
    order_events: list[dict] = field(default_factory=list)
    order_ids_by_version: dict = field(default_factory=dict)

    @property
    def scored(self) -> bool:
        return self.status == "EVALUATED"


def _side_sign(value: Any) -> int:
    text = getattr(value, "value", value)
    return 1 if str(text).lower() in {"buy", "long", "1", "1.0"} else -1


def _rejection_reason(event) -> str | None:
    """Map one engine order event to a rejection reason, or None when it is fine."""
    name = str(getattr(event, "event_name", "") or getattr(event, "status", "")).lower()
    for token in ("reject", "unsupported", "invalid", "error"):
        if token in name:
            return name
    return None


def _position(context) -> float:
    positions = getattr(context, "positions", None)
    if positions is None:
        return 0.0
    if hasattr(positions, "get"):
        return float(positions.get(SYMBOL, 0.0) or 0.0)
    array = np.asarray(positions, dtype=float).reshape(-1)
    return float(array[0]) if array.size else 0.0


def _kind_name(value: Any) -> str:
    return str(getattr(value, "value", value))


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
        self.rejections: list[dict] = []
        self._seq = 0
        self.fills_out: list[dict] = []
        self.switches: list[dict] = []
        self.commands_out: list[dict] = []
        self.order_events_out: list[dict] = []
        self.order_ids_by_version: dict[str, dict] = {}
        self._order_version: dict[str, str] = {}
        self._protection: list[dict] = []
        self._engine_position = 0.0
        self._entry_qty: float | None = None
        self._active_ready = initial.requested_at_bar <= 0
        self._active_since: int | None = None
        self._active_warmup: int = 0
        if self._active_ready:
            self.active = initial
            self.adapter = build_adapter(self.alpha_id, initial.params, self.market)
            self._active_since = 0
            self._active_warmup = int(self.adapter.warmup_bars())

    # -- tracking ----------------------------------------------------------

    def _version(self) -> str:
        return self.active.parameter_version if self.active is not None else "FLAT_UNTIL_READY"

    def _track_placed(self, order_id: str, tag: str | None, order_type: str,
                      level: float | None, version: str, bar: int) -> None:
        bucket = self.order_ids_by_version.setdefault(version, {"placed": [], "observed": []})
        bucket["placed"].append({"order_id": order_id, "tag": tag, "order_type": order_type,
                                 "level": level, "bar": bar})
        self._order_version[order_id] = version

    def _track_protection(self, order_id: str, tag: str, order_type: str, level: float | None,
                          version: str, bar: int) -> None:
        self._protection.append({"order_id": order_id, "tag": tag, "order_type": order_type,
                                 "level": level, "version": version, "bar": bar})

    def _drop_protection(self, order_ids) -> None:
        targets = {order_id for order_id in order_ids if order_id}
        if targets:
            self._protection = [record for record in self._protection
                                if record["order_id"] not in targets]

    def _pending_ids(self, context) -> set[str] | None:
        """Ids the engine reports as live; ``None`` when the context has no view."""
        active = getattr(context, "active_orders", None)
        if active is None:
            return None
        return {getattr(order, "order_id", None) for order in active
                if getattr(order, "order_id", None)}

    # -- command projection ------------------------------------------------

    def _place(self, timestamp, side: int, qty: float, order_type, *, kind: str, bar: int,
               declared_phase: str | None = None, price=None, trigger=None,
               reduce_only=False, tag=None, oco=None, metadata=None):
        import quantbt as q

        self._seq += 1
        order_id = f"lab-{self._seq}"
        order_type_name = _kind_name(order_type)
        command = q.OrderCommand(
            timestamp=timestamp, action=q.OrderAction.PLACE, symbol=SYMBOL,
            side=q.OrderSide.BUY if side > 0 else q.OrderSide.SELL,
            order_type=order_type, qty=float(qty), price=price, trigger_price=trigger,
            reduce_only=bool(reduce_only), tag=tag, oco_group_id=oco,
            order_id=order_id, metadata=dict(metadata or {}))
        version = self._version()
        self.commands_out.append({
            "bar": bar, "kind": kind, "declared_phase": declared_phase,
            "engine_action": "place", "effective_phase": ENGINE_EFFECTIVE_PHASE,
            "parameter_version": version, "order_id": order_id, "target_order_id": None,
            "tag": tag, "order_type": order_type_name, "qty": float(qty),
            "price": None if price is None else float(price),
            "trigger_price": None if trigger is None else float(trigger),
            "reduce_only": bool(reduce_only),
        })
        self._track_placed(order_id, tag, order_type_name,
                           float(trigger) if trigger is not None else (
                               float(price) if price is not None else None), version, bar)
        return command

    def _lifecycle(self, timestamp, action_name: str, target_order_id: str, *, kind: str,
                   bar: int, declared_phase: str | None = None, qty=None, price=None,
                   trigger=None, tag=None):
        import quantbt as q

        action = getattr(q.OrderAction, action_name)
        kwargs: dict[str, Any] = {"timestamp": timestamp, "action": action,
                                  "target_order_id": target_order_id}
        if action_name == "AMEND":
            if qty is not None:
                kwargs["qty"] = float(qty)
            if price is not None:
                kwargs["price"] = float(price)
            if trigger is not None:
                kwargs["trigger_price"] = float(trigger)
        command = q.OrderCommand(**kwargs)
        self.commands_out.append({
            "bar": bar, "kind": kind, "declared_phase": declared_phase,
            "engine_action": action_name.lower(), "effective_phase": ENGINE_EFFECTIVE_PHASE,
            "parameter_version": self._version(), "order_id": None,
            "target_order_id": target_order_id, "tag": tag, "order_type": None,
            "qty": None if qty is None else float(qty),
            "price": None if price is None else float(price),
            "trigger_price": None if trigger is None else float(trigger),
            "reduce_only": False,
        })
        return command

    def _current_price(self, context) -> float:
        close = context.close
        if hasattr(close, "__len__"):
            return float(np.asarray(close, dtype=float).reshape(-1)[-1])
        return float(close)

    def _unsupported(self, intent, context, reason: str) -> list:
        self.unmapped.append({"kind": _kind_name(intent.kind), "bar": int(context.bar_index),
                              "reason": reason, "handling": "unsupported"})
        return []

    def _reduce_quantity(self, intent: OrderIntent, context) -> tuple[float | None, str | None]:
        """Size a REDUCE from its declared basis; never more than the position."""
        position = abs(_position(context))
        basis = intent.quantity_basis
        value = intent.quantity_value
        if basis is QuantityBasis.FRACTION_OF_REMAINING:
            if value is None:
                return None, "fraction_of_remaining_reduce_without_quantity_value"
            qty = position * float(value)
        elif basis is QuantityBasis.FRACTION_OF_ENTRY:
            if value is None:
                return None, "fraction_of_entry_reduce_without_quantity_value"
            entry = abs(self._entry_qty) if self._entry_qty else position
            qty = entry * float(value)
        elif basis is QuantityBasis.FIXED_NOTIONAL:
            if value is None:
                return None, "fixed_notional_reduce_without_quantity_value"
            price = self._current_price(context)
            if not np.isfinite(price) or price <= 0.0:
                return None, "fixed_notional_reduce_without_a_usable_price"
            qty = float(value) / price
        else:
            qty = position if value is None else abs(float(value))
        if not np.isfinite(qty) or qty <= 0.0 or position == 0.0:
            return 0.0, None
        return float(min(qty, position)), None

    def _protection_target(self, intent: OrderIntent) -> dict | None:
        records = [record for record in self._protection
                   if record["version"] == self._version()]
        if not records:
            return None
        if intent.stop_price is not None:
            for record in records:
                if record["tag"] == "stop":
                    return record
            return None
        if intent.take_profit_price is not None:
            for record in records:
                if record["tag"] in ("tp", "ladder"):
                    return record
            return None
        if intent.price is not None:
            for wanted in ("tp", "stop"):
                for record in records:
                    if record["tag"] == wanted:
                        return record
            return records[0]
        return None

    def _amend_commands(self, intent: OrderIntent, context) -> list:
        record = self._protection_target(intent)
        if record is None:
            return self._unsupported(intent, context, "amend_protection_without_a_tracked_order")
        if record["order_type"] == "stop_market":
            level = intent.stop_price if intent.stop_price is not None else intent.price
            if level is None:
                return self._unsupported(intent, context, "amend_protection_without_a_level")
            record["level"] = float(level)
            return [self._lifecycle(context.timestamp, "AMEND", record["order_id"],
                                    kind=_kind_name(intent.kind), bar=int(context.bar_index),
                                    declared_phase=_kind_name(intent.earliest_phase),
                                    trigger=float(level), tag=record["tag"])]
        level = intent.take_profit_price if intent.take_profit_price is not None else intent.price
        if level is None:
            return self._unsupported(intent, context, "amend_protection_without_a_level")
        record["level"] = float(level)
        return [self._lifecycle(context.timestamp, "AMEND", record["order_id"],
                                kind=_kind_name(intent.kind), bar=int(context.bar_index),
                                declared_phase=_kind_name(intent.earliest_phase),
                                price=float(level), tag=record["tag"])]

    def _cancel_commands(self, intent: OrderIntent, context) -> list:
        records = [record for record in self._protection
                   if record["version"] == self._version()]
        selection = (intent.metadata or {}).get("protection_target")
        if selection in ("stop", "tp", "ladder"):
            if selection == "tp":
                records = [r for r in records if r["tag"] in ("tp", "ladder")]
            else:
                records = [r for r in records if r["tag"] == selection]
        elif intent.stop_price is not None:
            records = [r for r in records if r["tag"] == "stop"]
        elif intent.take_profit_price is not None:
            records = [r for r in records if r["tag"] in ("tp", "ladder")]
        if not records:
            return self._unsupported(intent, context,
                                     "cancel_protection_without_a_tracked_order")
        pending = self._pending_ids(context)
        targets = [record for record in records
                   if pending is None or record["order_id"] in pending]
        if not targets:
            return []
        commands = []
        for record in targets:
            commands.append(self._lifecycle(
                context.timestamp, "CANCEL", record["order_id"],
                kind=_kind_name(intent.kind), bar=int(context.bar_index),
                declared_phase=_kind_name(intent.earliest_phase), tag=record["tag"]))
        self._drop_protection(record["order_id"] for record in targets)
        return commands

    def _ladder_commands(self, intent: OrderIntent, context, side: int, position: float) -> list:
        import quantbt as q

        bar = int(context.bar_index)
        commands = []
        if intent.stop_price is not None:
            commands.append(self._place(
                context.timestamp, side, abs(position), q.OrderType.STOP_MARKET,
                kind=_kind_name(intent.kind), bar=bar,
                declared_phase=_kind_name(intent.earliest_phase),
                trigger=float(intent.stop_price), reduce_only=True, tag="stop"))
            self._track_protection(commands[-1].order_id, "stop", "stop_market",
                                   float(intent.stop_price), self._version(), bar)
        remaining = abs(position)
        for index, (level, fraction) in enumerate(intent.ladder):
            rung_qty = remaining * float(fraction)
            if not np.isfinite(rung_qty) or rung_qty <= 0.0:
                self.unmapped.append({
                    "kind": _kind_name(intent.kind), "bar": bar,
                    "reason": "ladder_rung_not_positive", "rung": index,
                    "level": float(level), "fraction": float(fraction),
                    "handling": "unsupported"})
                continue
            rung_qty = float(min(rung_qty, remaining))
            command = self._place(
                context.timestamp, side, rung_qty, q.OrderType.LIMIT,
                kind=_kind_name(intent.kind), bar=bar,
                declared_phase=_kind_name(intent.earliest_phase),
                price=float(level), reduce_only=True, tag="ladder",
                metadata={"level_id": f"ladder-{index}", "fraction_of_remaining": float(fraction)})
            commands.append(command)
            self._track_protection(command.order_id, "ladder", "limit", float(level),
                                   self._version(), bar)
            remaining -= rung_qty
            if remaining <= 0.0:
                remaining = 0.0
                break
        if remaining > 0.0:
            self.commands_out.append({
                "bar": bar, "kind": _kind_name(intent.kind), "declared_phase": None,
                "engine_action": "none", "effective_phase": None,
                "parameter_version": self._version(), "order_id": None,
                "target_order_id": None, "tag": "ladder_dust", "order_type": None,
                "qty": float(remaining), "price": None, "trigger_price": None,
                "reduce_only": True,
            })
        return commands

    def _intent_commands(self, intent: OrderIntent, context):
        import quantbt as q

        bar = int(context.bar_index)
        declared = _kind_name(intent.earliest_phase)
        if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT):
            side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
            price = self._current_price(context)
            if not np.isfinite(price) or price <= 0:
                raise EventAccountError("entry close is not usable")
            qty = self.unit_notional / price
            return [self._place(context.timestamp, side, qty, q.OrderType.MARKET,
                                kind=_kind_name(intent.kind), bar=bar, declared_phase=declared,
                                tag="entry", reduce_only=False)]
        if intent.kind is IntentKind.EXIT_ALL:
            position = _position(context)
            if position == 0.0:
                return []
            return [self._place(context.timestamp, -int(np.sign(position)), abs(position),
                                q.OrderType.MARKET, kind=_kind_name(intent.kind), bar=bar,
                                declared_phase=declared, tag="exit", reduce_only=True)]
        if intent.kind is IntentKind.REDUCE:
            qty, reason = self._reduce_quantity(intent, context)
            if reason is not None:
                return self._unsupported(intent, context, reason)
            position = _position(context)
            if qty is None or qty <= 0.0 or position == 0.0:
                return []
            return [self._place(context.timestamp, -int(np.sign(position)), float(qty),
                                q.OrderType.MARKET, kind=_kind_name(intent.kind), bar=bar,
                                declared_phase=declared, tag="reduce", reduce_only=True,
                                metadata={"quantity_basis": _kind_name(intent.quantity_basis),
                                          "quantity_value": intent.quantity_value})]
        if intent.kind is IntentKind.SET_PROTECTION:
            position = _position(context)
            if position == 0.0:
                return []
            side = -int(np.sign(position))
            if intent.ladder:
                return self._ladder_commands(intent, context, side, position)
            qty = abs(position)
            oco = "protection"
            commands = []
            if intent.stop_price is not None:
                command = self._place(context.timestamp, side, qty, q.OrderType.STOP_MARKET,
                                      kind=_kind_name(intent.kind), bar=bar,
                                      declared_phase=declared, trigger=float(intent.stop_price),
                                      reduce_only=True, tag="stop", oco=oco)
                commands.append(command)
                self._track_protection(command.order_id, "stop", "stop_market",
                                       float(intent.stop_price), self._version(), bar)
            target = intent.take_profit_price
            if target is None and intent.ladder:
                target = intent.ladder[-1][0]
            if target is not None:
                command = self._place(context.timestamp, side, qty, q.OrderType.LIMIT,
                                      kind=_kind_name(intent.kind), bar=bar,
                                      declared_phase=declared, price=float(target),
                                      reduce_only=True, tag="tp", oco=oco)
                commands.append(command)
                self._track_protection(command.order_id, "tp", "limit", float(target),
                                       self._version(), bar)
            return commands
        if intent.kind is IntentKind.AMEND_PROTECTION:
            return self._amend_commands(intent, context)
        if intent.kind is IntentKind.CANCEL_PROTECTION:
            return self._cancel_commands(intent, context)
        # Unknown kind: not carried on this route, evaluation is invalidated.
        return self._unsupported(intent, context, "unsupported_intent_on_event_route")

    # -- lifecycle ---------------------------------------------------------

    def _stale_protection_cancels(self, context, bar: int, leaving_version: str | None) -> list:
        if leaving_version is None:
            return []
        pending = self._pending_ids(context)
        commands = []
        for record in list(self._protection):
            if record["version"] != leaving_version:
                continue
            if pending is not None and record["order_id"] not in pending:
                self._drop_protection([record["order_id"]])
                continue
            commands.append(self._lifecycle(
                context.timestamp, "CANCEL", record["order_id"], kind="cancel_protection",
                bar=bar, declared_phase="resting_intrabar", tag="stale_version_cleanup"))
            self._drop_protection([record["order_id"]])
        return commands

    def _observe_order_events(self, context, bar: int) -> None:
        for event in (getattr(context, "order_events_this_bar", None) or []):
            order_id = getattr(event, "order_id", None)
            target_id = getattr(event, "target_order_id", None)
            record = {
                "bar": bar,
                "event_name": getattr(event, "event_name", None),
                "status": int(getattr(event, "status", -1) or 0),
                "order_id": order_id,
                "target_order_id": target_id,
                "tag": getattr(event, "tag", None),
            }
            version = self._order_version.get(order_id or target_id)
            record["parameter_version"] = version
            self.order_events_out.append(record)
            if version is not None and version in self.order_ids_by_version:
                self.order_ids_by_version[version]["observed"].append(record)
            reason = _rejection_reason(event)
            if reason is not None:
                self.rejections.append({"bar": bar, "reason": reason, "order_id": order_id,
                                        "target_order_id": target_id})
            if str(record["event_name"]) in ("fill", "cancel", "replace", "expire"):
                self._drop_protection([order_id, target_id])

    @staticmethod
    def _fill_kind(tag: str, side: int, qty: float, position_before: float) -> IntentKind:
        if tag == "entry":
            return IntentKind.ENTER_LONG if side > 0 else IntentKind.ENTER_SHORT
        if tag in ("ladder", "reduce"):
            return IntentKind.REDUCE
        if abs(qty) >= abs(position_before) - 1e-12:
            return IntentKind.EXIT_ALL
        return IntentKind.REDUCE

    def _apply_fills(self, context, bar: int) -> list:
        commands = []
        for event in (getattr(context, "fills_this_bar", None) or []):
            side = _side_sign(getattr(event, "side", 1))
            tag = str(getattr(event, "tag", "") or "")
            fee = float(getattr(event, "fee", 0.0) or 0.0)
            price = float(getattr(event, "price", float("nan")))
            qty = float(getattr(event, "qty", 0.0) or 0.0)
            order_id = getattr(event, "order_id", None)
            position_before = self._engine_position
            self._engine_position += side * qty
            kind = self._fill_kind(tag, side, qty, position_before)
            if kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT):
                self._entry_qty = qty
            self.fills_out.append({
                "bar_index": bar, "side": side, "qty": qty, "price": price, "fee": fee,
                "tag": tag, "order_id": order_id, "intent_kind": kind.value,
                "position_before": position_before, "position_after": self._engine_position,
            })
            follow_ups = self.adapter.on_fill(Fill(
                index=bar, side=side, quantity=side * qty, price=price, intent_kind=kind,
                metadata={"tag": tag, "fee": fee, "order_id": order_id}))
            for follow in follow_ups or []:
                commands.extend(self._intent_commands(follow, context))
        engine_position = _position(context)
        if abs(engine_position - self._engine_position) > POSITION_TOLERANCE:
            self.unmapped.append({
                "kind": "position_divergence", "bar": bar,
                "reason": "the fill ledger and the engine position disagree",
                "ledger_position": float(self._engine_position),
                "engine_position": float(engine_position),
                "handling": "unsupported"})
        # A flattened account has no live protection: cancel whatever is still
        # pending so a stale rung cannot close part of a later campaign.
        if abs(self._engine_position) <= POSITION_TOLERANCE and self._protection:
            commands.extend(self._cancel_pending_protection(context, bar,
                                                             "flatten_cleanup"))
        return commands

    def _cancel_pending_protection(self, context, bar: int, reason: str) -> list:
        pending = self._pending_ids(context)
        commands = []
        for record in list(self._protection):
            if pending is not None and record["order_id"] not in pending:
                self._drop_protection([record["order_id"]])
                continue
            commands.append(self._lifecycle(
                context.timestamp, "CANCEL", record["order_id"], kind="cancel_protection",
                bar=bar, declared_phase="resting_intrabar", tag=reason))
            self._drop_protection([record["order_id"]])
        return commands

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
        # G5: every command must end executed, rejected or unsupported. Rejections
        # are read from the engine's own order events, not inferred.
        self._observe_order_events(context, bar)
        # 1. Actual engine fills drive the adapter; follow-ups become commands now.
        commands.extend(self._apply_fills(context, bar))

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
            leaving_version = self.active.parameter_version if self.active is not None else None
            commands.extend(self._stale_protection_cancels(context, bar, leaving_version))
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
    status = "EVALUATED" if not strategy.unmapped and not strategy.rejections else "NOT_EVALUATED"
    return EventAccountRun(
        equity=np.asarray(result.equity, dtype=float).reshape(-1),
        positions=np.asarray(result.positions, dtype=float).reshape(-1),
        fills=strategy.fills_out,
        index=frame.index,
        version_by_bar=strategy.version_by_bar,
        entries=strategy.entries,
        engine_fill_count=len(getattr(result, "fills", None) or []),
        unmapped_intents=strategy.unmapped,
        rejections=strategy.rejections,
        status=status,
        commands=strategy.commands_out,
        order_events=strategy.order_events_out,
        order_ids_by_version=strategy.order_ids_by_version,
        diagnostics={"engine_backend": backend, "switches": strategy.switches,
                     "fee_binding": bound_fee_kwargs(one_way_fee),
                     "engine_backend_resolved": (
                         getattr(result, "metadata", None) or {}).get(
                             "native_event_backend_resolved"),
                     "command_count": len(strategy.commands_out),
                     "order_event_count": len(strategy.order_events_out)},
    )
