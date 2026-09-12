"""A-HMA — Adaptive HMA trend adapter (guide 3.3, L02.4).

Preserved (thesis):
  * the adaptive length recursion with ``adaptPct = 0.03141`` (an external regime
    model must prove value ON TOP of this, never by replacing it);
  * the EMA-smoothed ATR convention, not Wilder;
  * the four SL modes and their clamping;
  * the slope/angle formula and its 34-bar high/low window.

Repaired, each with a semantic delta:
  * SD-HMA-01 the fill comes from the engine; nothing assumes next_open == close;
  * SD-HMA-02 pre-bar weight and post-close target are separate fields;
  * SD-HMA-03 the RSI flat case stays 50 instead of jumping to 100;
  * SD-HMA-04 the instrument's real tick replaces the hardcoded 0.0001;
  * SD-HMA-05 min_length > max_length is rejected, never swapped;
  * SD-HMA-06 time_ms / volume / double_up / sl_mult are recorded as ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .base import AlphaAdapter, MarketSlice
from .contracts import (
    BarDecision, ExecutionPhase, Fill, IntentKind, OrderIntent, QuantityBasis,
)
from .reference import indicators as ref

ADAPT_PCT = 0.03141
SL_MODES = {"One Distance Zone": 0, "Half Distance Zone": 1, "Last High/Low": 2, "ATR Only": 3}
# A05: the LAB-02 schema invented the names "Zone Distance" and "ATR", which the
# adapter silently defaulted to mode 1. The canonical names are the raw alpha's
# sl_mode_map keys. Old artifacts replay through an EXPLICIT migration, never a
# silent fallback; a truly unknown name is infeasible.
LEGACY_SL_INPUT_ALIASES = {"Zone Distance": "One Distance Zone", "ATR": "ATR Only"}
IGNORED_KNOBS = ("sl_mult", "double_up", "time_ms", "volume")


class InfeasibleConfiguration(ValueError):
    """Raised for a configuration the adapter refuses to run (SD-HMA-05)."""


@dataclass
class HmaFeatures:
    atr_base: np.ndarray
    atr40: np.ndarray
    atr_fast: np.ndarray
    atr_slow: np.ndarray
    rsi: np.ndarray
    dynamic_hma: np.ndarray
    minor_hma: np.ndarray
    slope: np.ndarray
    dynamic_length: np.ndarray
    minor_length: np.ndarray
    charged: np.ndarray
    ignored_knobs: dict = field(default_factory=dict)


#: The compiled Hull kernel is admitted only while it is bit-exact against the
#: interpreted reference in ``reference/indicators.py``. If the check fails or
#: numba is unavailable, the interpreted path runs and nothing is silently faster
#: and different.
def _admit_fast_xhma():
    try:
        from .reference import fast_indicators as fast
    except Exception:
        return None, {"admitted": False, "reason": "compiled kernels unavailable"}
    report = fast.verify_parity()
    if not report["exact"]:
        return None, {"admitted": False, "reason": "parity not exact",
                      "mismatches": report["mismatches"][:3]}
    return fast.xhma_series, {"admitted": True, "reason": "bit-exact against the reference"}


_FAST_XHMA, FAST_XHMA_ADMISSION = _admit_fast_xhma()


class AdaptiveHmaEventAdapterV1(AlphaAdapter):
    """Indicators and decisions at the close; fills, brackets and equity are the engine's."""

    alpha_id = "A-HMA"
    adapter_version = "canonical_v1"

    REQUIRED_PARAMS = ("min_length", "max_length", "minor_min", "minor_max", "flat",
                       "atr_fast", "atr_slow", "mult", "max_sl", "take_profit",
                       "min_profit", "tick_size")

    def __init__(self, params: dict, market: MarketSlice, *,
                 rsi_variant: str = "canonical", gap_policy: str = "reject") -> None:
        super().__init__(params, market)
        if rsi_variant not in ("canonical", "legacy"):
            raise ValueError("rsi_variant must be 'canonical' or 'legacy'")
        if gap_policy not in ("reject", "normalize"):
            raise ValueError("gap_policy must be 'reject' or 'normalize'")
        self.rsi_variant = rsi_variant
        self.gap_policy = gap_policy
        self.features: HmaFeatures | None = None
        self._validate_params()

    def _validate_params(self) -> None:
        missing = [k for k in self.REQUIRED_PARAMS if k not in self.params]
        if missing:
            raise InfeasibleConfiguration(f"{self.alpha_id}: missing required parameters {missing}")
        if int(self.params["min_length"]) > int(self.params["max_length"]):
            raise InfeasibleConfiguration(
                f"min_length {self.params['min_length']} > max_length {self.params['max_length']}: "
                "an infeasible configuration is rejected, never silently swapped (SD-HMA-05)"
            )
        if int(self.params["minor_min"]) > int(self.params["minor_max"]):
            raise InfeasibleConfiguration("minor_min > minor_max is infeasible")
        if float(self.params["tick_size"]) <= 0:
            raise InfeasibleConfiguration("tick_size must be positive (SD-HMA-04)")
        self.ignored_knobs = {k: self.params[k] for k in IGNORED_KNOBS if k in self.params}
        raw_sl = self.params.get("sl_input", "Half Distance Zone")
        canonical_sl = LEGACY_SL_INPUT_ALIASES.get(raw_sl, raw_sl)
        if canonical_sl not in SL_MODES:
            raise InfeasibleConfiguration(
                f"{self.alpha_id}: unknown sl_input {raw_sl!r}; accepted: {tuple(SL_MODES)}")
        self.sl_input = canonical_sl
        self.sl_input_migrated_from = raw_sl if canonical_sl != raw_sl else None

    # -- lifecycle --------------------------------------------------------

    def warmup_bars(self) -> int:
        """The source's start_idx, made explicit."""
        return max(int(self.params["max_length"]),
                   int(self.params["minor_max"]),
                   int(self.params["atr_slow"]), 48) + 10

    def prepare(self) -> None:
        m = self.market
        n = len(m)
        atr_base = ref.atr_hma_convention(m.high, m.low, m.close, 21)
        atr40 = ref.atr_hma_convention(m.high, m.low, m.close, 40)
        atr_fast = ref.atr_hma_convention(m.high, m.low, m.close, int(self.params["atr_fast"]))
        atr_slow = ref.atr_hma_convention(m.high, m.low, m.close, int(self.params["atr_slow"]))
        rsi_fn = ref.rsi_hma_canonical if self.rsi_variant == "canonical" else ref.rsi_hma_legacy
        rsi = rsi_fn(m.close, 14)

        dyn = np.zeros(n)
        minor = np.zeros(n)
        slope = np.zeros(n)
        dyn_len = np.zeros(n)
        minor_len = np.zeros(n)
        charged = np.zeros(n, dtype=bool)

        min_l, max_l = int(self.params["min_length"]), int(self.params["max_length"])
        mn_l, mx_l = int(self.params["minor_min"]), int(self.params["minor_max"])
        dynamic_length = (min_l + max_l) / 2.0
        minor_length = (mn_l + mx_l) / 2.0

        # The two length recursions read only the ATR pair, and each Hull value reads
        # only the close series, so the lengths can be resolved first and the Hull
        # values filled in one compiled pass. The slope still has to follow bar by
        # bar because it reads the dynamic Hull series it is being written into.
        for t in range(2, n):
            is_charged = atr_fast[t] > atr_slow[t]
            charged[t] = is_charged
            if is_charged:
                dynamic_length = max(min_l, dynamic_length * (1.0 - ADAPT_PCT))
                minor_length = max(mn_l, minor_length * (1.0 - ADAPT_PCT))
            else:
                dynamic_length = min(max_l, dynamic_length * (1.0 + ADAPT_PCT))
                minor_length = min(mx_l, minor_length * (1.0 + ADAPT_PCT))
            dyn_len[t] = dynamic_length
            minor_len[t] = minor_length

        if _FAST_XHMA is not None:
            close = np.asarray(m.close, dtype=np.float64)
            dyn_i = dyn_len.astype(np.int64)
            minor_i = minor_len.astype(np.int64)
            dyn_fast = _FAST_XHMA(close, dyn_i, 2)
            minor_fast = _FAST_XHMA(close, minor_i, 2)
            dyn[2:] = dyn_fast[2:]
            minor[2:] = minor_fast[2:]
            for t in range(2, n):
                slope[t] = ref.calc_slope_at(dyn, t, m.high, m.low, m.close)
        else:
            for t in range(2, n):
                dyn[t] = ref.xhma_at(m.close, t, int(dyn_len[t]))
                minor[t] = ref.xhma_at(m.close, t, int(minor_len[t]))
                slope[t] = ref.calc_slope_at(dyn, t, m.high, m.low, m.close)

        self.features = HmaFeatures(
            atr_base, atr40, atr_fast, atr_slow, rsi, dyn, minor, slope,
            dyn_len, minor_len, charged,
            ignored_knobs={
                "values": self.ignored_knobs,
                "status": "IGNORED_BY_SOURCE",
                "policy": "dropped from the active search space; never re-implemented (SD-HMA-06)",
            },
        )

    # -- decisions --------------------------------------------------------

    def _bands(self, t: int) -> tuple[float, float, float, float]:
        f = self.features
        mult = float(self.params["mult"])
        return (f.dynamic_hma[t] + mult * f.atr40[t],        # upperTL
                f.dynamic_hma[t] - mult * f.atr40[t],        # lowerTL
                f.dynamic_hma[t] + 2.0 * mult * f.atr40[t],  # topTL
                f.dynamic_hma[t] - 2.0 * mult * f.atr40[t])  # botTL

    def _decide(self, t: int) -> BarDecision:
        f = self.features
        m = self.market
        entering = self.state.position
        target = entering
        intents: list[OrderIntent] = []
        flat = float(self.params["flat"])
        upper_tl, lower_tl, top_tl, bot_tl = self._bands(t)

        up_sig = f.slope[t] >= flat and f.charged[t]
        dn_sig = f.slope[t] <= -flat and f.charged[t]
        up_prev = f.slope[t - 1] >= flat and f.charged[t - 1]
        dn_prev = f.slope[t - 1] <= -flat and f.charged[t - 1]

        diagnostics = {
            "dynamic_hma": float(f.dynamic_hma[t]), "minor_hma": float(f.minor_hma[t]),
            "slope": float(f.slope[t]), "charged": bool(f.charged[t]),
            "rsi": float(f.rsi[t]), "atr_base": float(f.atr_base[t]),
            "dynamic_length": float(f.dynamic_length[t]), "minor_length": float(f.minor_length[t]),
            "upperTL": upper_tl, "lowerTL": lower_tl, "topTL": top_tl, "botTL": bot_tl,
            "upSig": bool(up_sig), "dnSig": bool(dn_sig),
            "rsi_variant": self.rsi_variant,
        }

        # ---- managing an open position: technical exit only ----
        # SL and TP are RESTING orders already working in the engine; the adapter
        # never claims them as its own fills (finding HM-03).
        if entering != 0.0 and self.state.entry_price is not None:
            if entering > 0:
                min_profit_level = self.state.entry_price + float(self.params["min_profit"]) * f.atr_base[t]
                rsi_exit = (f.rsi[t] < 50.0) or (f.rsi[t - 1] >= 70.0 and f.rsi[t] < 70.0)
                cross = (m.close[t - 1] >= f.dynamic_hma[t - 1]) and (m.close[t] < f.dynamic_hma[t])
                technical = m.close[t] >= min_profit_level and (rsi_exit or cross)
            else:
                min_profit_level = self.state.entry_price - float(self.params["min_profit"]) * f.atr_base[t]
                rsi_exit = (f.rsi[t] > 50.0) or (f.rsi[t - 1] <= 30.0 and f.rsi[t] > 30.0)
                cross = (m.close[t - 1] <= f.dynamic_hma[t - 1]) and (m.close[t] > f.dynamic_hma[t])
                technical = m.close[t] <= min_profit_level and (rsi_exit or cross)
            diagnostics["min_profit_level"] = float(min_profit_level)
            diagnostics["technical_exit"] = bool(technical)
            if technical and not self.state.pending_exit:
                self.state.pending_exit = True
                target = 0.0
                intents.append(OrderIntent(
                    kind=IntentKind.EXIT_ALL, decision_index=t,
                    earliest_phase=ExecutionPhase.NEXT_OPEN, reason="technical_exit",
                    metadata={"exit_reason": "technical", "rsi_exit": bool(rsi_exit),
                              "hma_cross": bool(cross)}))
            return BarDecision(index=t, position_entering_bar=entering,
                               target_after_close=target, intents=intents, diagnostics=diagnostics)

        # ---- flat: evaluate a new entry ----
        if entering != 0.0 or self.state.pending_entry_side:
            return BarDecision(index=t, position_entering_bar=entering,
                               target_after_close=target, diagnostics=diagnostics)

        tick = float(self.params["tick_size"])
        pip_size = tick * 10.0                                  # SD-HMA-04
        sl_low_max = m.low[t] - float(self.params["max_sl"]) * f.atr_base[t]
        sl_high_max = m.high[t] + float(self.params["max_sl"]) * f.atr_base[t]
        lo = t - 47 if t >= 47 else 0
        hh48 = float(np.max(m.high[lo:t + 1]))
        ll48 = float(np.min(m.low[lo:t + 1]))
        last_high = hh48 + 5.0 * pip_size
        last_low = ll48 - 5.0 * pip_size

        mode = SL_MODES[self.sl_input]
        sl_buy_raw, sl_sell_raw = {
            0: (bot_tl, top_tl),
            1: (lower_tl, upper_tl),
            2: (last_low, last_high),
        }.get(mode, (sl_low_max, sl_high_max))

        buy = (up_sig and not up_prev and m.close[t] > f.dynamic_hma[t]
               and m.low[t] <= upper_tl and 51.0 < f.rsi[t] <= 70.0)
        sell = (dn_sig and not dn_prev and m.close[t] < f.dynamic_hma[t]
                and m.high[t] >= lower_tl and 30.0 <= f.rsi[t] < 49.0)
        mid = (m.high[t] + m.low[t]) / 2.0
        over_buy = (up_sig and not up_prev and f.rsi[t] > 70.0 and m.close[t] > f.dynamic_hma[t]
                    and mid > upper_tl and f.minor_hma[t] > f.dynamic_hma[t])
        over_sell = (dn_sig and not dn_prev and f.rsi[t] < 30.0 and m.close[t] < f.dynamic_hma[t]
                     and mid < lower_tl and f.minor_hma[t] < f.dynamic_hma[t])
        diagnostics.update({"buy": bool(buy), "sell": bool(sell),
                            "overBuy": bool(over_buy), "overSell": bool(over_sell),
                            "sl_mode": mode, "pip_size": pip_size})

        if buy or over_buy:
            self.state.pending_entry_side = 1
            target = 1.0
            self._staged = {
                "side": 1,
                "stop_level": max(sl_buy_raw, sl_low_max),
                "tp_level": m.high[t] + float(self.params["take_profit"]) * f.atr_base[t],
                "decision_index": t,
            }
            intents.append(OrderIntent(
                kind=IntentKind.ENTER_LONG, decision_index=t,
                earliest_phase=ExecutionPhase.NEXT_OPEN,
                reason="overBuy" if over_buy else "buy",
                quantity_basis=QuantityBasis.FIXED_NOTIONAL,
                metadata={"intended_stop_level": self._staged["stop_level"],
                          "intended_tp_level": self._staged["tp_level"],
                          "levels_are_intents_not_fills": True}))
        elif sell or over_sell:
            self.state.pending_entry_side = -1
            target = -1.0
            self._staged = {
                "side": -1,
                "stop_level": min(sl_sell_raw, sl_high_max),
                "tp_level": m.low[t] - float(self.params["take_profit"]) * f.atr_base[t],
                "decision_index": t,
            }
            intents.append(OrderIntent(
                kind=IntentKind.ENTER_SHORT, decision_index=t,
                earliest_phase=ExecutionPhase.NEXT_OPEN,
                reason="overSell" if over_sell else "sell",
                quantity_basis=QuantityBasis.FIXED_NOTIONAL,
                metadata={"intended_stop_level": self._staged["stop_level"],
                          "intended_tp_level": self._staged["tp_level"],
                          "levels_are_intents_not_fills": True}))

        return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
                           intents=intents, diagnostics=diagnostics)

    # -- fills ------------------------------------------------------------

    def _levels_from_fill(self, fill: Fill) -> list[OrderIntent]:
        """Validate the staged bracket against the ACTUAL fill (finding HM-03)."""
        staged = getattr(self, "_staged", None)
        if staged is None:
            return []
        stop_level = staged["stop_level"]
        tp_level = staged["tp_level"]
        side = staged["side"]
        wrong_side = (side > 0 and (stop_level >= fill.price or tp_level <= fill.price)) or \
                     (side < 0 and (stop_level <= fill.price or tp_level >= fill.price))
        if wrong_side:
            if self.gap_policy == "reject":
                self.state.pending_exit = True
                return [OrderIntent(
                    kind=IntentKind.EXIT_ALL, decision_index=fill.index,
                    earliest_phase=ExecutionPhase.NEXT_OPEN,
                    reason="bracket_invalid_after_gap",
                    metadata={"policy": "reject", "fill_price": fill.price,
                              "stop_level": stop_level, "tp_level": tp_level,
                              "note": "a gap put a protective level on the wrong side of the fill; "
                                      "the position is closed rather than booked as instant profit"})]
            distance_stop = abs(staged["stop_level"] - self.market.close[staged["decision_index"]])
            distance_tp = abs(staged["tp_level"] - self.market.close[staged["decision_index"]])
            stop_level = fill.price - side * distance_stop
            tp_level = fill.price + side * distance_tp
        self.state.stop_price = stop_level
        self.state.take_profit_price = tp_level
        return [OrderIntent(
            kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
            earliest_phase=ExecutionPhase.RESTING_INTRABAR, reason="bracket_from_actual_fill",
            stop_price=stop_level, take_profit_price=tp_level,
            metadata={"fill_price": fill.price, "gap_policy": self.gap_policy,
                      "normalized": bool(wrong_side and self.gap_policy == "normalize")})]
