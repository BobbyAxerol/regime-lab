"""A-VWAP — daily VWAP mean reversion with an HTF filter (guide 3.2, L02.5).

Preserved (thesis):
  * the z-score of (close - VWAP) against its 50-bar mean and sample stdev,
    with ``dev_len = 50`` fixed;
  * the RSI/ATR conventions of this file, not another alpha's;
  * the entry rules and the HTF trend gate.

Repaired, each with a semantic delta:
  * SD-VWAP-01 short input yields an explicit no-signal warmup, never an IndexError;
  * SD-VWAP-02 next-open fill with levels from the ACTUAL fill;
  * SD-VWAP-03 a frozen exit precedence: stop, take profit, then the time stop;
  * SD-VWAP-04 ``exit_at_vwap`` is OFF in the canonical pilot; when enabled it
    rests at the PREVIOUSLY observed VWAP, never the current bar's own VWAP;
  * SD-VWAP-05 the HTF EMA is joined on ``available_at`` from a closed bucket,
    with warmup derived from the EMA span rather than a hardcoded 200 bars;
  * SD-VWAP-06 no module default is ever executed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .base import AlphaAdapter, MarketSlice
from .contracts import (
    BarDecision, ExecutionPhase, Fill, IntentKind, OrderIntent, QuantityBasis,
)
from .reference import indicators as ref

DEV_LEN = 50                       # fixed in the source; exposing it needs an audited revision
EXIT_PRECEDENCE = ("stop_loss", "take_profit", "time_stop")   # SD-VWAP-03, frozen


class HtfUnavailable(ValueError):
    """Raised when the HTF filter cannot be built causally."""


def htf_ema_available_at(
    index, close: np.ndarray, htf_rule: str, span: int, publication_delay=None
) -> tuple[np.ndarray, np.ndarray]:
    """Closed-bucket HTF EMA joined on availability, not on the resample label.

    Returns ``(htf_ema_per_bar, available_from_index)``. A bucket's EMA becomes
    usable only after the bucket has closed and the publication delay has passed
    (guide 6.3), which is what makes the join causal regardless of whether the
    resample is left- or right-labelled (finding AV-06).
    """
    import pandas as pd

    if index is None:
        raise HtfUnavailable("A-VWAP needs a DatetimeIndex to build the HTF filter")
    idx = pd.DatetimeIndex(index)
    delay = pd.Timedelta(0) if publication_delay is None else pd.Timedelta(publication_delay)

    frame = pd.DataFrame({"close": close}, index=idx)
    buckets = frame.resample(htf_rule, label="left", closed="left").agg({"close": "last"}).dropna()
    if buckets.empty:
        raise HtfUnavailable(f"no complete {htf_rule} bucket in the supplied range")
    offset = pd.tseries.frequencies.to_offset(htf_rule)
    bucket_end = pd.DatetimeIndex([label + offset for label in buckets.index])
    ema = buckets["close"].ewm(span=span, adjust=False).mean().to_numpy()
    available_at = bucket_end + delay

    # Drop any bucket whose window is not fully covered by the supplied data.
    complete = bucket_end <= idx[-1] + pd.Timedelta(0)
    ema = ema[complete]
    available_at = available_at[complete]

    out = np.full(close.size, np.nan)
    available_from = np.full(close.size, -1, dtype=np.int64)
    if ema.size:
        pos = np.searchsorted(available_at.to_numpy(), idx.to_numpy(), side="right") - 1
        valid = pos >= 0
        out[valid] = ema[pos[valid]]
        available_from[valid] = pos[valid]
    return out, available_from


def ema_convergence_bars(span: int, epsilon: float) -> int:
    """Smallest n with (1 - 2/(span+1))**n <= epsilon (guide 3.2)."""
    decay = 1.0 - 2.0 / (span + 1.0)
    if decay <= 0.0:
        return 1
    return int(math.ceil(math.log(epsilon) / math.log(decay)))


@dataclass
class VwapFeatures:
    vwap: np.ndarray
    rsi: np.ndarray
    atr: np.ndarray
    htf_ema: np.ndarray
    z: np.ndarray
    dist: np.ndarray
    dist_sma: np.ndarray
    dist_std: np.ndarray
    new_day: np.ndarray
    htf_available_from: np.ndarray
    htf_warmup_buckets: int


class VwapMeanReversionEventAdapterV1(AlphaAdapter):
    """Owns VWAP/RSI/ATR/HTF and entry eligibility. Owns no fills."""

    alpha_id = "A-VWAP"
    adapter_version = "canonical_v1"

    REQUIRED_PARAMS = ("rsi_len", "rsi_os", "rsi_ob", "dev_mult", "atr_len", "stop_atr",
                       "target_r", "htf_ema_len", "htf_tf", "exit_at_vwap",
                       "time_stop_on", "time_stop_bars")

    def __init__(self, params: dict, market: MarketSlice, *,
                 htf_epsilon: float = 1e-3, publication_delay=None) -> None:
        super().__init__(params, market)
        missing = [k for k in self.REQUIRED_PARAMS if k not in self.params]
        if missing:
            raise KeyError(f"{self.alpha_id}: missing required parameters {missing} "
                           "(the module default is never executed, SD-VWAP-06)")
        if not (float(params["rsi_os"]) < float(params["rsi_ob"])):
            raise ValueError("rsi_os must be below rsi_ob")
        if float(params["dev_mult"]) <= 0 or float(params["stop_atr"]) <= 0 \
                or float(params["target_r"]) <= 0:
            raise ValueError("dev_mult, stop_atr and target_r must be positive")
        self.htf_epsilon = htf_epsilon
        self.publication_delay = publication_delay
        self.features: VwapFeatures | None = None

    def warmup_bars(self) -> int:
        """Real readiness: indicator windows, dev window and HTF EMA convergence."""
        base = max(DEV_LEN, int(self.params["atr_len"]) + 1, int(self.params["rsi_len"]) + 1)
        return base

    def prepare(self) -> None:
        import pandas as pd

        m = self.market
        if m.index is None:
            raise HtfUnavailable("A-VWAP requires a DatetimeIndex (UTC daily reset and HTF join)")
        idx = pd.DatetimeIndex(m.index)
        if idx.tz is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        days = idx.normalize()
        new_day = np.zeros(len(m), dtype=bool)
        new_day[0] = True
        new_day[1:] = days[1:] != days[:-1]

        vwap = ref.daily_vwap(m.high, m.low, m.close, m.volume, new_day)
        rsi = ref.rsi_vwap_convention(m.close, int(self.params["rsi_len"]))
        atr = ref.atr_vwap_convention(m.high, m.low, m.close, int(self.params["atr_len"]))

        htf_ema, available_from = htf_ema_available_at(
            idx, m.close, str(self.params["htf_tf"]), int(self.params["htf_ema_len"]),
            self.publication_delay)
        htf_warmup = ema_convergence_bars(int(self.params["htf_ema_len"]), self.htf_epsilon)

        dist = m.close - vwap
        dist_sma = ref.sma(dist, DEV_LEN)
        dist_std = ref.rolling_std_sample(dist, DEV_LEN)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = np.where(dist_std != 0.0, (dist - dist_sma) / dist_std, 0.0)

        self.features = VwapFeatures(vwap, rsi, atr, htf_ema, z, dist, dist_sma, dist_std,
                                     new_day, available_from, htf_warmup)

    def _ready(self, t: int) -> tuple[bool, str | None]:
        f = self.features
        if t < self.warmup_bars():
            return False, f"indicator warmup requires {self.warmup_bars()} bars"
        if np.isnan(f.htf_ema[t]):
            return False, "no closed HTF bucket is available yet"
        if f.htf_available_from[t] < f.htf_warmup_buckets:
            return False, (f"HTF EMA has seen {f.htf_available_from[t] + 1} closed buckets; "
                           f"{f.htf_warmup_buckets} are needed for span convergence "
                           f"at epsilon={self.htf_epsilon}")
        if f.dist_std[t] == 0.0:
            return False, "zero dispersion: the z-score is undefined, not zero"
        return True, None

    def _decide(self, t: int) -> BarDecision:
        f = self.features
        m = self.market
        entering = self.state.position
        target = entering
        intents: list[OrderIntent] = []

        ready, reason = self._ready(t)
        diagnostics = {
            "vwap": float(f.vwap[t]), "rsi": float(f.rsi[t]), "atr": float(f.atr[t]),
            "htf_ema": None if np.isnan(f.htf_ema[t]) else float(f.htf_ema[t]),
            "z": float(f.z[t]), "dist": float(f.dist[t]), "dist_std": float(f.dist_std[t]),
            "new_day": bool(f.new_day[t]),
            "htf_closed_buckets_seen": int(f.htf_available_from[t]) + 1,
            "exit_precedence": list(EXIT_PRECEDENCE),
        }
        if not ready:
            return BarDecision(index=t, position_entering_bar=entering, target_after_close=entering,
                               warmup_ready=False, blocked_reason=reason, diagnostics=diagnostics)

        # ---- open position: only the TIME stop is a close decision ----
        # The stop and the take profit are resting orders working in the engine;
        # the adapter never books them itself (finding AV-02).
        if entering != 0.0:
            bars_held = t - (self.state.entry_index if self.state.entry_index is not None else t)
            time_stop_due = bool(self.params["time_stop_on"]) and \
                bars_held >= int(self.params["time_stop_bars"])
            diagnostics["bars_held"] = bars_held
            diagnostics["time_stop_due"] = time_stop_due
            if time_stop_due and not self.state.pending_exit:
                self.state.pending_exit = True
                target = 0.0
                intents.append(OrderIntent(
                    kind=IntentKind.EXIT_ALL, decision_index=t,
                    earliest_phase=ExecutionPhase.NEXT_OPEN, reason="time_stop",
                    metadata={"exit_reason": "time_stop", "bars_held": bars_held,
                              "precedence": list(EXIT_PRECEDENCE),
                              "note": "submitted at the close; a resting stop or take profit that "
                                      "triggered intrabar takes precedence"}))
            if bool(self.params["exit_at_vwap"]) and not self.state.pending_exit:
                # SD-VWAP-04: rest at the PREVIOUS bar's observed VWAP, never this bar's.
                intents.append(OrderIntent(
                    kind=IntentKind.AMEND_PROTECTION, decision_index=t,
                    earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                    reason="dynamic_vwap_resting_previous_observed",
                    price=float(f.vwap[t]),
                    metadata={"effective_from_bar": t + 1,
                              "variant": "resting_previous_observed_vwap"}))
            return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
                               intents=intents, diagnostics=diagnostics)

        if self.state.pending_entry_side:
            return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
                               diagnostics=diagnostics)

        trend_long_ok = m.close[t] >= f.htf_ema[t]
        trend_short_ok = m.close[t] <= f.htf_ema[t]
        long_entry = trend_long_ok and f.z[t] <= -float(self.params["dev_mult"]) \
            and f.rsi[t] <= float(self.params["rsi_os"])
        short_entry = trend_short_ok and f.z[t] >= float(self.params["dev_mult"]) \
            and f.rsi[t] >= float(self.params["rsi_ob"])
        diagnostics.update({"trend_long_ok": bool(trend_long_ok),
                            "trend_short_ok": bool(trend_short_ok),
                            "long_entry": bool(long_entry), "short_entry": bool(short_entry)})

        if long_entry:
            self.state.pending_entry_side = 1
            target = 1.0
            self._staged_risk = float(f.atr[t]) * float(self.params["stop_atr"])
            intents.append(OrderIntent(
                kind=IntentKind.ENTER_LONG, decision_index=t,
                earliest_phase=ExecutionPhase.NEXT_OPEN, reason="z_below_band_and_rsi_oversold",
                quantity_basis=QuantityBasis.FIXED_NOTIONAL,
                metadata={"risk_distance": self._staged_risk,
                          "levels_derived_at": "fill", "atr_at_decision": float(f.atr[t])}))
        elif short_entry:
            self.state.pending_entry_side = -1
            target = -1.0
            self._staged_risk = float(f.atr[t]) * float(self.params["stop_atr"])
            intents.append(OrderIntent(
                kind=IntentKind.ENTER_SHORT, decision_index=t,
                earliest_phase=ExecutionPhase.NEXT_OPEN, reason="z_above_band_and_rsi_overbought",
                quantity_basis=QuantityBasis.FIXED_NOTIONAL,
                metadata={"risk_distance": self._staged_risk,
                          "levels_derived_at": "fill", "atr_at_decision": float(f.atr[t])}))

        return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
                           intents=intents, diagnostics=diagnostics)

    def _levels_from_fill(self, fill: Fill) -> list[OrderIntent]:
        """SD-VWAP-02: the stop and target are measured from the ACTUAL fill."""
        risk = getattr(self, "_staged_risk", None)
        if risk is None:
            return []
        side = 1 if fill.quantity > 0 else -1
        stop = fill.price - side * risk
        take_profit = fill.price + side * risk * float(self.params["target_r"])
        self.state.stop_price = stop
        self.state.take_profit_price = take_profit
        return [OrderIntent(
            kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
            earliest_phase=ExecutionPhase.RESTING_INTRABAR,
            reason="bracket_from_actual_fill",
            stop_price=stop, take_profit_price=take_profit,
            metadata={"fill_price": fill.price, "risk_distance": risk,
                      "precedence": list(EXIT_PRECEDENCE)})]
