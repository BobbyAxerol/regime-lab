"""A-HASH — momentum with a partial take-profit ladder (guide 3.1, L02.6).

Preserved (thesis):
  * the momentum / normalised-momentum / EMA entry conditions;
  * the close-to-close "ATR" as the LEGACY convention, because changing it
    changes the entry threshold scale (a true-range variant is a separate version);
  * TP2 as a fraction of the REMAINING quantity (AH-06), locked, never re-based.

Repaired, each with a semantic delta:
  * SD-HASH-01 numpy is imported (the original cannot even run);
  * SD-HASH-02 next-open fill with the ladder priced off the ACTUAL fill;
  * SD-HASH-03 an explicit ordered ladder replaces the one-stage-per-bar chain;
  * SD-HASH-04 the engine owns equity; the realized-only column is a diagnostic;
  * SD-HASH-06 account configuration leaves the alpha entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .base import AlphaAdapter, MarketSlice
from .contracts import (
    BarDecision, ExecutionPhase, Fill, IntentKind, OrderIntent, QuantityBasis,
)
from .reference import indicators as ref

ACCOUNT_KEYS = ("initial_capital", "trading_fee", "usd_per_trade")
# Instrument metadata is experiment-level, not an alpha parameter, but the ladder
# cannot be expressed honestly without it: a rung quantity that does not respect
# the exchange step is not a real order.
INSTRUMENT_KEYS = ("qty_step", "min_qty", "min_notional")
ATR_VARIANTS = ("legacy_close_move", "true_range_revision")


class LadderInfeasible(ValueError):
    """Raised when tp1 < tp2 < final does not hold (finding AH-07)."""


class AccountConfigInAlpha(ValueError):
    """Raised when account configuration is passed as an alpha parameter (SD-HASH-06)."""


@dataclass
class HashFeatures:
    mom0: np.ndarray
    mom_norm: np.ndarray
    atr: np.ndarray
    ema: np.ndarray
    atr_variant: str
    legacy_realized_equity: np.ndarray | None = field(default=None)


class HashMomentumEventAdapterV1(AlphaAdapter):
    """Emits momentum entries and an ordered protective ladder priced from the fill."""

    alpha_id = "A-HASH"
    adapter_version = "canonical_v1"

    REQUIRED_PARAMS = ("mom_len", "ema_len", "cooldown_bars", "stop_loss_perc", "rr_ratio",
                       "tp1_ratio", "tp1_qty_perc", "tp2_ratio", "tp2_qty_perc",
                       "mom_threshold_mult")

    def __init__(self, params: dict, market: MarketSlice, *,
                 atr_variant: str = "legacy_close_move",
                 enforce_ordered_ladder: bool = True) -> None:
        super().__init__(params, market)
        if atr_variant not in ATR_VARIANTS:
            raise ValueError(f"atr_variant must be one of {ATR_VARIANTS}")
        leaked = [k for k in ACCOUNT_KEYS if k in self.params]
        self.instrument = {k: self.params[k] for k in INSTRUMENT_KEYS if k in self.params}
        if leaked:
            raise AccountConfigInAlpha(
                f"{leaked} are experiment-level account configuration, not alpha parameters; "
                "they live in the economic contract and are identical for every arm (SD-HASH-06)"
            )
        missing = [k for k in self.REQUIRED_PARAMS if k not in self.params
                   if k not in INSTRUMENT_KEYS]
        if missing:
            raise KeyError(f"{self.alpha_id}: missing required parameters {missing}")
        self.atr_variant = atr_variant
        self.enforce_ordered_ladder = enforce_ordered_ladder
        self._check_ladder()
        self.features: HashFeatures | None = None
        self.last_exit_index: int | None = None

    def _check_ladder(self) -> None:
        tp1 = float(self.params["tp1_ratio"])
        tp2 = float(self.params["tp2_ratio"])
        final = float(self.params["rr_ratio"])
        self.ladder_ordered = tp1 < tp2 < final
        if not self.ladder_ordered and self.enforce_ordered_ladder:
            raise LadderInfeasible(
                f"tp1_ratio={tp1}, tp2_ratio={tp2}, rr_ratio={final} do not satisfy "
                "tp1 < tp2 < final; the canonical simultaneous ladder rejects this preset and the "
                "raw order is preserved rather than silently sorted (finding AH-07)"
            )

    # -- lifecycle --------------------------------------------------------

    def warmup_bars(self) -> int:
        """Momentum needs 3*mom_len for its dispersion window; the ATR needs 15."""
        return max(int(self.params["mom_len"]) * 3 + 1, 15)

    def prepare(self) -> None:
        m = self.market
        if len(m) <= 15:
            raise ref.WarmupError(
                f"{self.alpha_id} needs more than 15 bars for its ATR seed; got {len(m)} "
                "(the original indexes atr[14] unguarded, finding AH-02)"
            )
        mom0, mom_norm = ref.momentum_block(m.close, int(self.params["mom_len"]))
        if self.atr_variant == "legacy_close_move":
            atr = ref.atr_hash_legacy_close_move(m.close, 14)
        else:
            atr = ref.atr_hash_true_range_variant(m.high, m.low, m.close, 14)
        ema = ref.ema(m.close, int(self.params["ema_len"]))
        self.features = HashFeatures(mom0, mom_norm, atr, ema, self.atr_variant)

    # -- decisions --------------------------------------------------------

    def _cooldown_ok(self, t: int) -> bool:
        cooldown = int(self.params["cooldown_bars"])
        if self.last_exit_index is None:
            return True
        return (t - self.last_exit_index) >= cooldown

    def _decide(self, t: int) -> BarDecision:
        f = self.features
        m = self.market
        entering = self.state.position
        target = entering
        intents: list[OrderIntent] = []

        threshold = f.atr[t] * float(self.params["mom_threshold_mult"])
        mom1 = f.mom0[t] - f.mom0[t - 1]
        diagnostics = {
            "mom0": float(f.mom0[t]), "mom1": float(mom1), "mom_norm": float(f.mom_norm[t]),
            "atr": float(f.atr[t]), "atr_variant": f.atr_variant, "ema": float(f.ema[t]),
            "dyn_threshold": float(threshold),
            "cooldown_ok": self._cooldown_ok(t), "last_exit_index": self.last_exit_index,
            "ladder_ordered": self.ladder_ordered,
        }

        if entering != 0.0 or self.state.pending_entry_side:
            # The ladder and the stop are resting orders; nothing is decided at the close.
            return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
                               diagnostics=diagnostics)
        if not self._cooldown_ok(t):
            return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
                               diagnostics=diagnostics,
                               blocked_reason="cooldown active since the last exit fill")

        long_entry = (f.mom0[t] > threshold and mom1 > 0 and f.mom_norm[t] > 0.5
                      and m.close[t] > m.close[t - 1] and m.close[t] > f.ema[t])
        short_entry = (f.mom0[t] < -threshold and mom1 < 0 and f.mom_norm[t] < -0.5
                       and m.close[t] < m.close[t - 1] and m.close[t] < f.ema[t])
        diagnostics.update({"long_entry": bool(long_entry), "short_entry": bool(short_entry)})

        if long_entry or short_entry:
            side = 1 if long_entry else -1
            self.state.pending_entry_side = side
            target = float(side)
            kind = IntentKind.ENTER_LONG if side > 0 else IntentKind.ENTER_SHORT
            intents.append(OrderIntent(
                kind=kind, decision_index=t, earliest_phase=ExecutionPhase.NEXT_OPEN,
                reason="momentum_breakout",
                quantity_basis=QuantityBasis.FIXED_NOTIONAL,
                metadata={"levels_derived_at": "fill",
                          "stop_loss_perc": float(self.params["stop_loss_perc"]),
                          "ladder_ratios": [float(self.params["tp1_ratio"]),
                                            float(self.params["tp2_ratio"]),
                                            float(self.params["rr_ratio"])]}))

        return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
                           intents=intents, diagnostics=diagnostics)

    # -- fills ------------------------------------------------------------

    def quantize_ladder(self, fill_price: float, side: int, entry_qty: float,
                        instrument: dict | None = None) -> dict:
        """Turn the ladder's fractions into real order quantities (T12).

        ``fraction_of_remaining`` is preserved exactly: rung 2 closes a fraction
        of what is left AFTER rung 1. Each rung is then quantised to the
        instrument's step with QuantBT's own helper, and whatever the steps leave
        behind is reported as explicit DUST rather than silently folded into the
        final rung or over-closed.
        """
        import quantbt as q

        instrument = instrument or {k: self.params[k] for k in INSTRUMENT_KEYS
                                    if k in self.params}
        qty_step = float(instrument.get("qty_step", 0.0))
        min_qty = float(instrument.get("min_qty", 0.0))
        min_notional = float(instrument.get("min_notional", 0.0))

        _stop, ladder = self.build_ladder(fill_price, side)
        remaining = float(entry_qty)
        rungs = []
        for level, fraction in ladder:
            raw = remaining * fraction
            quantised = q.quantize_signed_quantity(
                raw, price=float(level), contract_size=1.0,
                qty_step=qty_step, min_qty=min_qty, min_notional=min_notional)
            rungs.append({
                "level": float(level),
                "fraction_of_remaining": float(fraction),
                "raw_qty": raw,
                "quantised_qty": float(quantised),
                "rejected_below_minimum": bool(raw > 0 and quantised == 0.0),
                "remaining_before": remaining,
            })
            remaining -= float(quantised)
        total_closed = sum(r["quantised_qty"] for r in rungs)
        dust = float(entry_qty) - total_closed
        return {
            "entry_qty": float(entry_qty),
            "instrument": {"qty_step": qty_step, "min_qty": min_qty,
                           "min_notional": min_notional},
            "rungs": rungs,
            "total_closed": total_closed,
            "dust": dust,
            "over_closed": total_closed > float(entry_qty) + 1e-12,
            "dust_policy": (
                "dust is reported, never rolled into another rung and never over-closed; a residual "
                "position is flattened by the terminal contract, not by inventing an extra fill"
            ),
            "partial_quantity_convention": "fraction_of_remaining",
        }

    def build_ladder(self, fill_price: float, side: int) -> tuple[float, tuple[tuple[float, float], ...]]:
        """Stop and the ordered ladder, both priced from the ACTUAL fill."""
        sl_perc = float(self.params["stop_loss_perc"]) / 100.0
        stop = fill_price * (1.0 - sl_perc) if side > 0 else fill_price * (1.0 + sl_perc)
        risk = abs(fill_price - stop)
        levels = [
            (fill_price + side * risk * float(self.params["tp1_ratio"]),
             float(self.params["tp1_qty_perc"]) / 100.0),
            (fill_price + side * risk * float(self.params["tp2_ratio"]),
             float(self.params["tp2_qty_perc"]) / 100.0),
            (fill_price + side * risk * float(self.params["rr_ratio"]), 1.0),
        ]
        # Ordered by trigger distance from the fill; never re-sorted to hide an
        # infeasible preset, only used when the ratios were already ordered.
        return stop, tuple(levels)

    def _levels_from_fill(self, fill: Fill) -> list[OrderIntent]:
        side = 1 if fill.quantity > 0 else -1
        stop, ladder = self.build_ladder(fill.price, side)
        self.state.stop_price = stop
        return [OrderIntent(
            kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
            earliest_phase=ExecutionPhase.RESTING_INTRABAR,
            reason="ordered_ladder_from_actual_fill",
            stop_price=stop, ladder=ladder,
            quantity_basis=QuantityBasis.FRACTION_OF_REMAINING,
            metadata={
                "fill_price": fill.price,
                "partial_quantity_convention": "fraction_of_remaining",
                "convention_note": "TP2 closes a fraction of what REMAINS after TP1, matching the "
                                   "source; it is never re-based to the entry quantity (AH-06)",
                "ladder_ordered": self.ladder_ordered,
                "all_levels_evaluated_per_bar": True,
            })]

    def on_fill(self, fill: Fill) -> list[OrderIntent]:
        follow_ups = super().on_fill(fill)
        # Cooldown restarts from the actual flattening fill, not from a partial.
        if self.state.position == 0.0 and fill.intent_kind in (
                IntentKind.EXIT_ALL, IntentKind.REDUCE, IntentKind.SET_PROTECTION):
            self.last_exit_index = fill.index
        return follow_ups

    # -- diagnostics ------------------------------------------------------

    def legacy_realized_equity(self, fills: list[Fill], initial_capital: float,
                               entry_prices: dict[int, float] | None = None) -> np.ndarray:
        """Reproduce the source's realized-only equity column — DIAGNOSTIC ONLY.

        The source credits ``units * (exit_price - entry_price)`` at each closing
        event and never marks an OPEN position (finding AH-03), so the curve is
        flat while a position runs and jumps only on a realised exit. Reproduced
        faithfully here so the shape of the legacy column can be inspected.

        It must never be used as an equity curve, an objective, or a reported
        metric; the engine ledger is the only authority (SD-HASH-04).
        """
        equity = np.full(len(self.market), float(initial_capital))
        running = float(initial_capital)
        open_entry: float | None = None
        prices = entry_prices or {}
        for fill in fills:
            running -= fill.fee
            if fill.intent_kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT):
                open_entry = prices.get(fill.index, fill.price)
            elif open_entry is not None:
                # a closing fill realises against the entry price only
                running += (-fill.quantity) * (fill.price - open_entry)
                if fill.intent_kind is IntentKind.EXIT_ALL:
                    open_entry = None
            equity[fill.index:] = running
        return equity
