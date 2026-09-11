"""Map lab adapter intents onto the installed engine (guide 4.4, L02.7, L02.8).

The lab does NOT implement matching or accounting. It translates its typed
intents into ``quantbt.IntrabarIntentTape`` and lets QuantBT execute them under
``intrabar_bracket_v1``, whose contract was verified on this install to be:

    signal_phase = BAR_CLOSE, entry_fill_phase = NEXT_OPEN,
    market_fill_policy = NEXT_OPEN, same_bar_policy = CONSERVATIVE,
    stop_gap_policy = OPEN_WORSE_THAN_TRIGGER,
    take_profit_gap_policy = LIMIT_PRICE_CONSERVATIVE,
    liquidation_priority = LIQUIDATION_FIRST_AT_GAP,
    funding_phase = POSITION_AT_EVENT, ambiguity_policy = FLAG_AND_CONSERVATIVE

That is the guide's primary clock: a decision at a bar close cannot fill at that
same close. The generic ``orders`` route was measured NOT to provide it (it fills
a market order at the close of the stamped bar), which is recorded as a blocked
capability rather than silently accepted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..alphas.contracts import BarDecision, IntentKind

ENGINE_ID = "intrabar_bracket_v1"


@dataclass
class TapeBuild:
    entry_side: np.ndarray
    entry_size: np.ndarray
    stop_value: np.ndarray
    take_profit_value: np.ndarray
    technical_exit: np.ndarray
    decision_map: dict[int, dict] = field(default_factory=dict)
    unmapped_intents: list[dict] = field(default_factory=list)

    def as_tape(self, level_mode=None):
        import quantbt as q

        return q.IntrabarIntentTape(
            entry_side=self.entry_side,
            entry_size=self.entry_size,
            stop_value=self.stop_value,
            take_profit_value=self.take_profit_value,
            technical_exit=self.technical_exit,
            level_mode=level_mode or q.IntrabarLevelMode.ABSOLUTE_PRICE,
        )


def build_intent_tape(decisions: list[BarDecision], n_bars: int, *,
                      unit_size: float = 1.0,
                      pending_levels: dict[int, tuple[float, float]] | None = None) -> TapeBuild:
    """Fold a decision tape into the engine's array form.

    ``pending_levels`` supplies (stop, take_profit) for an entry bar when the
    adapter derives them from the fill. The engine prices the entry at the next
    open, so an absolute level chosen at the decision close is an INTENT the
    engine may reject or clamp; that is the whole point of feeding it through the
    engine rather than booking it in the adapter.
    """
    entry_side = np.zeros(n_bars)
    entry_size = np.zeros(n_bars)
    stop_value = np.full(n_bars, np.nan)
    take_profit_value = np.full(n_bars, np.nan)
    technical_exit = np.zeros(n_bars, dtype=bool)
    decision_map: dict[int, dict] = {}
    unmapped: list[dict] = []
    levels = pending_levels or {}

    for decision in decisions:
        for intent in decision.intents:
            t = intent.decision_index
            if intent.kind is IntentKind.ENTER_LONG:
                entry_side[t] = 1.0
                entry_size[t] = unit_size
            elif intent.kind is IntentKind.ENTER_SHORT:
                entry_side[t] = -1.0
                entry_size[t] = unit_size
            elif intent.kind is IntentKind.EXIT_ALL:
                technical_exit[t] = True
            elif intent.kind is IntentKind.SET_PROTECTION:
                if intent.stop_price is not None:
                    stop_value[t] = intent.stop_price
                if intent.take_profit_price is not None:
                    take_profit_value[t] = intent.take_profit_price
                if intent.ladder:
                    # A multi-rung ladder is not expressible in this tape; the
                    # final rung is used and the omission is recorded, never hidden.
                    take_profit_value[t] = intent.ladder[-1][0]
                    unmapped.append({
                        "index": t, "kind": intent.kind.value,
                        "reason": "ladder_rungs_beyond_final_not_expressible_in_intent_tape",
                        "rungs": [list(x) for x in intent.ladder],
                        "handling": "BLOCKED_CAPABILITY for partial ladders on this route",
                    })
            elif intent.kind in (IntentKind.AMEND_PROTECTION, IntentKind.CANCEL_PROTECTION,
                                 IntentKind.REDUCE):
                unmapped.append({"index": t, "kind": intent.kind.value,
                                 "reason": "not expressible in IntrabarIntentTape",
                                 "handling": "BLOCKED_CAPABILITY"})
            decision_map.setdefault(t, {"intents": []})["intents"].append(intent.kind.value)

    for t, (stop, tp) in levels.items():
        if 0 <= t < n_bars:
            stop_value[t] = stop
            take_profit_value[t] = tp

    return TapeBuild(entry_side, entry_size, stop_value, take_profit_value,
                     technical_exit, decision_map, unmapped)


def run_intrabar(frame, tape_build: TapeBuild, *, backend: str = "reference",
                 initial_capital: float = 20000.0, fee: float = 0.0004,
                 slippage_bps: float = 1.0, use_funding: bool = False,
                 funding_timestamps=None, funding_rates=None,
                 close_on_last_bar: bool = True, symbol: str = "S",
                 sizing_mode: str = "units", unit_notional: float | None = None) -> dict:
    """Execute a tape on the installed engine and return the account trace."""
    import quantbt as q

    factory = {
        "reference": q.QuantBTEndpoint.intrabar_bracket_reference,
        "rust": q.QuantBTEndpoint.intrabar_bracket_rust,
        "auto": q.QuantBTEndpoint.intrabar_bracket,
    }[backend]
    sizing = {"units": q.IntrabarSizingMode.UNITS,
              "fixed_notional": q.IntrabarSizingMode.FIXED_NOTIONAL}[sizing_mode]
    kwargs: dict[str, Any] = dict(
        level_mode=q.IntrabarLevelMode.ABSOLUTE_PRICE,
        intrabar_sizing_mode=sizing,
        close_on_last_bar=close_on_last_bar,
        account=q.AccountConfig(initial_capital=initial_capital),
        fee=fee, slippage_bps=slippage_bps, symbols=[symbol],
        use_funding=use_funding,
    )
    if sizing is q.IntrabarSizingMode.FIXED_NOTIONAL:
        if unit_notional is None:
            raise ValueError("fixed_notional sizing requires unit_notional")
        # The engine reads the per-entry notional from alloc_per_trade (endpoint.py:3087);
        # passing it any other way silently sizes every entry at zero.
        kwargs["alloc_per_trade"] = float(unit_notional)
    elif unit_notional is not None:
        raise ValueError("unit_notional only applies to sizing_mode='fixed_notional'")
    endpoint = factory(**kwargs)
    backtest_kwargs: dict[str, Any] = {"data": frame, "intent": tape_build.as_tape()}
    if funding_timestamps is not None:
        backtest_kwargs["funding_event_timestamps"] = funding_timestamps
        backtest_kwargs["funding_event_rates"] = funding_rates
    result = endpoint.backtest(**backtest_kwargs)

    def _reason(value) -> str:
        """Normalise IntrabarFillReason to its lowercase value string."""
        if hasattr(value, "value"):
            return str(value.value).lower()
        text = str(value)
        return text.rsplit(".", 1)[-1].lower() if "." in text else text.lower()

    fills = []
    for f in endpoint.fills:
        fills.append({
            "bar_index": int(getattr(f, "bar_index", -1)),
            "sequence": int(getattr(f, "sequence", 0)),
            "side": int(getattr(f, "side", 0)),
            "qty": float(getattr(f, "qty", 0.0)),
            "price": float(getattr(f, "price", float("nan"))),
            "fee": float(getattr(f, "fee", 0.0)),
            "reason": _reason(getattr(f, "reason", "")),
        })
    return {
        "backend": backend,
        "engine_id": ENGINE_ID,
        "equity": np.asarray(result.equity, dtype=float),
        "positions": np.asarray(result.positions, dtype=float),
        "fees": np.asarray(result.fees, dtype=float),
        "funding": np.asarray(result.funding, dtype=float),
        "fills": fills,
        "fills_available": bool(fills),
        "liquidated": bool(np.asarray(result.liquidated).any()) if result.liquidated is not None else False,
        "result": result,
    }


def contract_snapshot() -> dict:
    """The engine contract actually installed, read rather than assumed."""
    import quantbt as q

    contract = q.get_execution_contract(ENGINE_ID)
    fields = getattr(contract, "__dataclass_fields__", {})
    return {
        "engine_id": ENGINE_ID,
        **{name: (lambda v: v.value if hasattr(v, "value") else v)(getattr(contract, name))
           for name in fields},
    }
