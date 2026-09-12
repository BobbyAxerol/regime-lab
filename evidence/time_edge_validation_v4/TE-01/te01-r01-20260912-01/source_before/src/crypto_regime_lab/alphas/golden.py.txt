"""Deterministic golden fixtures: one synthetic market per alpha, plus the
adapter -> intent tape -> installed engine round trip that produces its trace.

These are the ``golden fixture tapes and account traces`` LAB-02 must deliver.
They are synthetic by design: no market data has been read yet, so nothing here
is evidence about edge, only about mechanism.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..quantbt_bridge.intent_tape import build_intent_tape, run_intrabar
from .base import MarketSlice
from .contracts import Fill, IntentKind


@dataclass
class GoldenFixture:
    alpha_id: str
    name: str
    market: MarketSlice
    params: dict
    index: Any = None
    adapter_kwargs: dict | None = None


def _ohlc(close: np.ndarray, pad: float, open_: np.ndarray | None = None):
    close = np.asarray(close, dtype=float)
    open_ = np.r_[close[0], close[:-1]] if open_ is None else np.asarray(open_, dtype=float)
    high = np.maximum(open_, close) + pad
    low = np.minimum(open_, close) - pad
    return open_, high, low, close


def golden_sc() -> GoldenFixture:
    n = 260
    close = np.concatenate([100 + np.linspace(0, 40, 110),
                            140 - np.linspace(0, 55, 80),
                            85 + np.linspace(0, 30, 70)])
    close = close + np.random.default_rng(11).normal(0, 0.25, n)
    o, h, l, c = _ohlc(close, 0.8)
    return GoldenFixture("A-SC", "rally_reversal_recovery",
                         MarketSlice(o, h, l, c, np.full(n, 1000.0)),
                         {"coeff": 2, "AP": 11, "novolumedata": False, "src_col": "close",
                          "alpha.condition_threshold": 50})


def golden_hma() -> GoldenFixture:
    n = 160
    rng = np.random.default_rng(5)
    close = 100 + np.cumsum(rng.normal(0, 0.9, n))
    o, h, l, c = _ohlc(close, 0.5)
    return GoldenFixture("A-HMA", "random_walk_small_lengths",
                         MarketSlice(o, h, l, c, np.full(n, 1000.0)),
                         dict(min_length=6, max_length=12, minor_min=3, minor_max=6, flat=5.0,
                              atr_fast=3, atr_slow=7, mult=1.0, max_sl=2.0, take_profit=2.0,
                              min_profit=0.5, tick_size=0.01, sl_input="Half Distance Zone"))


def golden_vwap() -> GoldenFixture:
    import pandas as pd

    n = 1200
    rng = np.random.default_rng(9)
    close = np.zeros(n)
    x = 100.0
    for i in range(n):
        x += -0.05 * (x - 100.0) + rng.normal(0, 0.6)
        close[i] = x
    o, h, l, c = _ohlc(close, 0.2)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return GoldenFixture("A-VWAP", "mean_reverting_15m",
                         MarketSlice(o, h, l, c, np.abs(rng.normal(1000, 150, n)) + 1, index=idx),
                         dict(rsi_len=14, rsi_os=45, rsi_ob=55, dev_mult=1.0, atr_len=14,
                              stop_atr=2.0, target_r=2.0, htf_ema_len=20, htf_tf="1h",
                              exit_at_vwap=False, time_stop_on=True, time_stop_bars=8),
                         index=idx)


def golden_hash() -> GoldenFixture:
    n = 400
    rng = np.random.default_rng(21)
    close = 100 + np.cumsum(rng.normal(0.02, 0.7, n))
    o, h, l, c = _ohlc(close, 0.3)
    return GoldenFixture("A-HASH", "drifting_momentum",
                         MarketSlice(o, h, l, c, np.full(n, 1000.0)),
                         dict(mom_len=10, ema_len=30, cooldown_bars=5, stop_loss_perc=2.0,
                              rr_ratio=3.0, tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0,
                              tp2_qty_perc=50, mom_threshold_mult=1.0))


GOLDEN_FIXTURES = {
    "A-SC": golden_sc, "A-HMA": golden_hma, "A-VWAP": golden_vwap, "A-HASH": golden_hash,
}


def build_adapter(fixture: GoldenFixture):
    from .a_hash import HashMomentumEventAdapterV1
    from .a_hma import AdaptiveHmaEventAdapterV1
    from .a_sc import SignalCombineAdapterV1
    from .a_vwap import VwapMeanReversionEventAdapterV1

    cls = {"A-SC": SignalCombineAdapterV1, "A-HMA": AdaptiveHmaEventAdapterV1,
           "A-VWAP": VwapMeanReversionEventAdapterV1, "A-HASH": HashMomentumEventAdapterV1}[fixture.alpha_id]
    return cls(fixture.params, fixture.market, **(fixture.adapter_kwargs or {}))


def drive_with_engine_fills(fixture: "GoldenFixture", *, max_passes: int = 6,
                            backend: str = "reference") -> dict:
    """Drive an adapter to a FIXED POINT against the installed engine.

    A plain fill-tape replay only knows about the fills it invents (entries and
    technical exits). Protective exits are resting orders the ENGINE fills, so an
    adapter whose only exits are a stop or a take profit would appear to stay in
    one position forever and never trade again.

    This runs the loop until it converges: decisions -> tape -> engine -> the
    engine's own fills -> decisions again. The final pass is asserted to be
    self-consistent, so no fill is replayed that the engine did not produce for
    the tape those very decisions generate.
    """
    import pandas as pd
    import warnings

    n = len(fixture.market)
    idx = fixture.index if fixture.index is not None else pd.date_range(
        "2024-01-01", periods=n, freq="1h", tz="UTC")
    frame = pd.DataFrame({"open": fixture.market.open, "high": fixture.market.high,
                          "low": fixture.market.low, "close": fixture.market.close,
                          "volume": fixture.market.volume}, index=idx)

    exit_bars: set[int] = set()
    history: list[dict] = []
    adapter = None
    build = None
    out = None
    for attempt in range(max_passes):
        adapter = build_adapter(fixture)
        pending_levels: dict[int, tuple[float, float]] = {}
        events: list[dict] = []
        for t in range(n):
            decision = adapter.on_bar_close(t)
            for intent in decision.intents:
                events.append({"bar": t, "kind": intent.kind.value, "reason": intent.reason})
                if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and t + 1 < n:
                    side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
                    fill = Fill(index=t + 1, side=side, quantity=float(side),
                                price=float(fixture.market.open[t + 1]), intent_kind=intent.kind)
                    for follow in adapter.on_fill(fill):
                        events.append({"bar": t + 1, "kind": follow.kind.value,
                                       "reason": follow.reason})
                        if follow.stop_price is not None:
                            tp = follow.take_profit_price
                            if tp is None and follow.ladder:
                                tp = follow.ladder[-1][0]
                            pending_levels[t] = (float(follow.stop_price),
                                                 float(tp if tp is not None else np.nan))
                elif intent.kind is IntentKind.EXIT_ALL and adapter.state.position != 0.0 \
                        and t + 1 < n:
                    adapter.on_fill(Fill(index=t + 1, side=-int(np.sign(adapter.state.position)),
                                         quantity=-adapter.state.position,
                                         price=float(fixture.market.open[t + 1]),
                                         intent_kind=IntentKind.EXIT_ALL))
                    exit_bars.discard(t + 1)
            # Replay a protective exit the ENGINE reported on this bar.
            if t in exit_bars and adapter.state.position != 0.0:
                adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
                                     quantity=-adapter.state.position,
                                     price=float(fixture.market.close[t]),
                                     intent_kind=IntentKind.EXIT_ALL))

        build = build_intent_tape(adapter.decisions, n, unit_size=1.0,
                                  pending_levels=pending_levels)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = run_intrabar(frame, build, backend=backend, initial_capital=20000.0,
                               fee=0.0004, slippage_bps=1.0, use_funding=False,
                               close_on_last_bar=True)
        engine_exits = {f["bar_index"] for f in out["fills"]
                        if f["reason"] in ("stop_loss", "take_profit", "liquidation")}
        history.append({"pass": attempt, "entries": int(np.count_nonzero(build.entry_side)),
                        "engine_protective_exits": sorted(engine_exits)})
        if engine_exits == exit_bars:
            return {"adapter": adapter, "build": build, "engine": out, "frame": frame,
                    "events": events, "pending_levels": pending_levels,
                    "converged": True, "passes": attempt + 1, "history": history,
                    "protective_exit_bars": sorted(engine_exits)}
        exit_bars = engine_exits
    return {"adapter": adapter, "build": build, "engine": out, "frame": frame,
            "events": events, "pending_levels": pending_levels,
            "converged": False, "passes": max_passes, "history": history,
            "protective_exit_bars": sorted(exit_bars)}


def golden_trace(alpha_id: str, backend: str = "reference") -> dict:
    """Adapter decisions -> intent tape -> installed engine -> account trace."""

    fixture = GOLDEN_FIXTURES[alpha_id]()
    loop = drive_with_engine_fills(fixture, backend=backend)
    adapter, build, out = loop["adapter"], loop["build"], loop["engine"]
    replay = {"events": loop["events"]}
    n = len(fixture.market)
    decisions = [d.as_record() for d in adapter.decisions]
    tape_payload = {
        "entry_side": build.entry_side.tolist(),
        "entry_size": build.entry_size.tolist(),
        "stop_value": [None if np.isnan(x) else x for x in build.stop_value.tolist()],
        "take_profit_value": [None if np.isnan(x) else x for x in build.take_profit_value.tolist()],
        "technical_exit": build.technical_exit.astype(int).tolist(),
    }
    trace_payload = {
        "equity": out["equity"].reshape(-1).tolist(),
        "positions": out["positions"].reshape(-1).tolist(),
        "fees": out["fees"].reshape(-1).tolist(),
        "fills": out["fills"],
    }
    digest = hashlib.sha256(
        json.dumps({"tape": tape_payload, "trace": trace_payload}, sort_keys=True).encode()
    ).hexdigest()
    return {
        "alpha_id": alpha_id,
        "fixture": fixture.name,
        "backend": backend,
        "bars": n,
        "fixed_point_converged": loop["converged"],
        "fixed_point_passes": loop["passes"],
        "protective_exit_bars": loop["protective_exit_bars"],
        "decision_count": len(decisions),
        "intent_events": replay["events"],
        "warmup_blocked_bars": sum(1 for d in adapter.decisions if not d.warmup_ready),
        "entries": int(np.count_nonzero(build.entry_side)),
        "technical_exits": int(build.technical_exit.sum()),
        "unmapped_intents": build.unmapped_intents,
        "engine_fills": out["fills"],
        "final_equity": float(out["equity"].reshape(-1)[-1]),
        "max_abs_position": float(np.max(np.abs(out["positions"]))),
        "tape": tape_payload,
        "trace": trace_payload,
        "golden_digest": digest,
        "note": "synthetic fixture; this is mechanism evidence, never a performance claim",
    }
