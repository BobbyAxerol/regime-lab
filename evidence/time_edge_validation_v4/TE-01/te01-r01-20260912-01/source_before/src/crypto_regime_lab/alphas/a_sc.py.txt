"""A-SC — SignalCombine / AlphaTrend-like long-flat adapter (guide 3.4, L02.3).

Preserved from the source (thesis, not repaired):
  * the cross formula trend[t] vs trend[t-2] with trend[t-1] vs trend[t-2] (SC-03);
  * long-flat only, no shorting (SC-05);
  * the integer cast of ``coeff`` (SC-02);
  * ``ta``'s ATR and MFI/RSI, because ``ta`` is what the alpha runs.

Repaired, each with a semantic delta:
  * SD-SC-01 the volume fallback resolves ONCE, so construction and dispatch agree;
  * SD-SC-02 one declared decision timestamp with a next-open fill, no double shift;
  * SD-SC-03 amplitude 2 is normalised to a 0/1 direction against the experiment
    notional (``sizing_mapping_v1``); the legacy amplitude path is separate;
  * SD-SC-04 the internal threshold is namespaced ``alpha.condition_threshold``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import AlphaAdapter, MarketSlice
from .contracts import BarDecision, ExecutionPhase, IntentKind, OrderIntent, QuantityBasis

SIZING_MAPPING = "sizing_mapping_v1"


class VolumeUnavailable(ValueError):
    """Raised when the primary crypto path is asked to run without volume (SD-SC-01)."""


@dataclass
class SignalCombineState:
    trend: np.ndarray
    up_t: np.ndarray
    down_t: np.ndarray
    condition: np.ndarray
    buy_signal: np.ndarray
    sell_signal: np.ndarray
    k1: np.ndarray
    k2: np.ndarray
    o1: np.ndarray
    o2: np.ndarray
    long_signal: np.ndarray
    short_signal: np.ndarray
    indicator_used: str
    first_trend_init: int | None


def _bars_since(flags: np.ndarray, lag: int) -> np.ndarray:
    """Bars since a flag, reproducing the source's NaN-until-first-event semantics.

    ``lag=0`` gives K1/K2 (since the current flag), ``lag=1`` gives O1/O2 (since
    the previous bar's flag). The source starts the loop at i=1 and leaves index
    0 as NaN; that is preserved because the comparisons O1 > K2 depend on it.
    """
    n = flags.size
    out = np.full(n, np.nan)
    for i in range(1, n):
        src_idx = i - lag
        fired = bool(flags[src_idx]) if 0 <= src_idx < n else False
        if fired:
            out[i] = 0.0
        elif i > lag and not np.isnan(out[i - 1]):
            out[i] = out[i - 1] + 1.0
    return out


def compute_signal_combine(
    market: MarketSlice,
    *,
    ap: int,
    coeff: int,
    condition_threshold: float,
    use_rsi: bool,
    src_col_values: np.ndarray,
    vectorised: bool = True,
) -> SignalCombineState:
    """Indicator and signal block. ``vectorised`` toggles the SC-06 optimisation.

    Both paths must produce identical output; that equality is a test, not an
    assumption, because the guide only permits vectorising AFTER output parity.
    """
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.volatility import AverageTrueRange
    from ta.volume import MFIIndicator

    n = len(market)
    high = pd.Series(market.high)
    low = pd.Series(market.low)
    close = pd.Series(market.close)

    atr_series = AverageTrueRange(high=high, low=low, close=close, window=ap,
                                  fillna=False).average_true_range()
    if use_rsi:
        condition_series = RSIIndicator(close=pd.Series(src_col_values), window=ap,
                                        fillna=False).rsi()
        indicator_used = "rsi"
    else:
        condition_series = MFIIndicator(high=high, low=low, close=close,
                                        volume=pd.Series(market.volume), window=ap,
                                        fillna=False).money_flow_index()
        indicator_used = "mfi"

    atr = atr_series.to_numpy()
    cond_values = condition_series.to_numpy()
    condition = cond_values >= condition_threshold      # NaN compares False, as in the source

    up_t = np.full(n, np.nan)
    down_t = np.full(n, np.nan)
    trend = np.zeros(n)

    if vectorised:
        up_t[1:] = market.low[1:] - atr[1:] * coeff
        down_t[1:] = market.high[1:] + atr[1:] * coeff
    else:
        for i in range(1, n):
            up_t[i] = market.low[i] - atr[i] * coeff
            down_t[i] = market.high[i] + atr[i] * coeff

    # The recursion is inherently sequential in both paths.
    for i in range(1, n):
        prev = trend[i - 1]
        if condition[i]:
            trend[i] = up_t[i] if up_t[i] > prev else prev
        else:
            trend[i] = down_t[i] if down_t[i] < prev else prev

    # SC-03: the source's own comparison, preserved.
    trend_2 = np.full(n, np.nan)
    trend_1 = np.full(n, np.nan)
    trend_2[2:] = trend[:-2]
    trend_1[1:] = trend[:-1]
    with np.errstate(invalid="ignore"):
        buy_signal = (trend > trend_2) & (trend_1 <= trend_2)
        sell_signal = (trend < trend_2) & (trend_1 >= trend_2)
    buy_signal = np.nan_to_num(buy_signal, nan=0.0).astype(bool)
    sell_signal = np.nan_to_num(sell_signal, nan=0.0).astype(bool)

    k1 = _bars_since(buy_signal, lag=0)
    k2 = _bars_since(sell_signal, lag=0)
    o1 = _bars_since(buy_signal, lag=1)
    o2 = _bars_since(sell_signal, lag=1)

    with np.errstate(invalid="ignore"):
        long_signal = buy_signal & (o1 > k2)
        short_signal = sell_signal & (o2 > k1)
    long_signal = np.nan_to_num(long_signal, nan=0.0).astype(bool)
    short_signal = np.nan_to_num(short_signal, nan=0.0).astype(bool)

    # SC-07 / SD-SC-06: the bar on which the zero seed is first replaced.
    left_seed = np.flatnonzero(trend != 0.0)
    first_trend_init = int(left_seed[0]) if left_seed.size else None

    return SignalCombineState(trend, up_t, down_t, condition, buy_signal, sell_signal,
                              k1, k2, o1, o2, long_signal, short_signal, indicator_used,
                              first_trend_init)


class SignalCombineAdapterV1(AlphaAdapter):
    """Long-flat adapter: intent after close, fill at the next open."""

    alpha_id = "A-SC"
    adapter_version = "canonical_v1"

    REQUIRED_PARAMS = ("coeff", "AP", "novolumedata", "src_col", "alpha.condition_threshold")

    def __init__(self, params: dict, market: MarketSlice, *, strict_volume: bool = True,
                 vectorised: bool = True) -> None:
        super().__init__(params, market)
        self.strict_volume = strict_volume
        self.vectorised = vectorised
        self.signals: SignalCombineState | None = None
        self._resolve_condition_source()

    def _resolve_condition_source(self) -> None:
        """SD-SC-01: decide RSI vs MFI ONCE, before anything is constructed."""
        declared_no_volume = bool(self.params.get("novolumedata", False))
        volume = np.asarray(self.market.volume, dtype=np.float64)
        volume_present = volume.size > 0 and np.isfinite(volume).all() and (volume > 0).any()
        if not volume_present and not declared_no_volume:
            if self.strict_volume:
                raise VolumeUnavailable(
                    "A-SC primary path requires volume for the MFI condition; a missing or empty "
                    "volume series must be an explicit rejection, not a silent RSI substitution "
                    "(finding SC-01)"
                )
            self.use_rsi = True
            self.fallback_applied = True
        else:
            self.use_rsi = declared_no_volume
            self.fallback_applied = False

    def warmup_bars(self) -> int:
        """AP for the indicators, +3 for the two-bar comparison window.

        The trend-seed exclusion (SD-SC-06) is data-dependent and therefore
        applied in ``_decide`` rather than folded into this constant.
        """
        return int(self.params["AP"]) + 3

    def _seed_clear(self, t: int) -> bool:
        """SD-SC-06: has the zero seed left the two-bar comparison window?"""
        assert self.signals is not None
        first = self.signals.first_trend_init
        if first is None:
            return False
        return t >= first + 3

    def prepare(self) -> None:
        threshold = self.params.get("alpha.condition_threshold",
                                    self.params.get("regime_threshold"))
        if threshold is None:
            raise KeyError("alpha.condition_threshold is required (SD-SC-04)")
        src_col = self.params.get("src_col", "close")
        src_values = {"close": self.market.close, "high": self.market.high,
                      "low": self.market.low, "open": self.market.open}[src_col]
        self.signals = compute_signal_combine(
            self.market,
            ap=int(self.params["AP"]),
            coeff=int(self.params["coeff"]),      # SC-02: integer, preserved
            condition_threshold=float(threshold),
            use_rsi=self.use_rsi,
            src_col_values=np.asarray(src_values, dtype=np.float64),
            vectorised=self.vectorised,
        )

    def _decide(self, t: int) -> BarDecision:
        assert self.signals is not None
        s = self.signals
        entering = self.state.position
        target = entering
        intents: list[OrderIntent] = []

        if not self._seed_clear(t):
            return BarDecision(
                index=t, position_entering_bar=entering, target_after_close=entering,
                warmup_ready=False,
                blocked_reason="trend still inside the zero-seed comparison window (SD-SC-06)",
                diagnostics={"trend": float(s.trend[t]), "first_trend_init": s.first_trend_init},
            )

        long_now = bool(s.long_signal[t])
        short_now = bool(s.short_signal[t])

        # Long-flat state machine (SC-05): a short signal flattens, never reverses.
        if entering > 0 and short_now:
            target = 0.0
            intents.append(OrderIntent(
                kind=IntentKind.EXIT_ALL, decision_index=t,
                earliest_phase=ExecutionPhase.NEXT_OPEN, reason="short_signal_flattens_long",
                quantity_basis=QuantityBasis.ALL,
                metadata={"exit_reason": "signal_flip"}))
        elif entering == 0 and long_now and not self.state.pending_entry_side:
            target = 1.0
            self.state.pending_entry_side = 1     # staged, NOT a position
            intents.append(OrderIntent(
                kind=IntentKind.ENTER_LONG, decision_index=t,
                earliest_phase=ExecutionPhase.NEXT_OPEN, reason="long_signal",
                quantity_basis=QuantityBasis.FIXED_NOTIONAL,
                metadata={"sizing_mapping": SIZING_MAPPING,
                          "legacy_amplitude": 2.0, "normalised_direction": 1.0}))

        return BarDecision(
            index=t, position_entering_bar=entering, target_after_close=target,
            intents=intents,
            diagnostics={
                "trend": float(s.trend[t]),
                "upT": float(s.up_t[t]) if not np.isnan(s.up_t[t]) else None,
                "downT": float(s.down_t[t]) if not np.isnan(s.down_t[t]) else None,
                "condition": bool(s.condition[t]),
                "indicator_used": s.indicator_used,
                "buy_signal": bool(s.buy_signal[t]),
                "sell_signal": bool(s.sell_signal[t]),
                "K1": None if np.isnan(s.k1[t]) else float(s.k1[t]),
                "K2": None if np.isnan(s.k2[t]) else float(s.k2[t]),
                "O1": None if np.isnan(s.o1[t]) else float(s.o1[t]),
                "O2": None if np.isnan(s.o2[t]) else float(s.o2[t]),
                "long_signal": long_now,
                "short_signal": short_now,
                "first_trend_init": s.first_trend_init,
            },
        )
