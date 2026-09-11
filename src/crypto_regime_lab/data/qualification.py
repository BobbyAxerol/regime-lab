"""L03.7 — market adapter qualification on a bounded development slice.

This is a DOMAIN smoke test: does each certified adapter survive real bars —
their gaps, their HTF buckets, their warmup — and does the installed engine
produce an account trace from the intents? It is explicitly not model selection
and not a performance measurement, and the slice it uses is pinned to the
development role so it can never be reused as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..alphas.base import MarketSlice
from ..alphas.contracts import IntentKind
from ..quantbt_bridge.intent_tape import build_intent_tape, run_intrabar

DATA_ROLE = "development"
# Bounded by construction: a slice, never the sample.
DEFAULT_SLICE_BARS = 1500

# Smoke configurations. Lengths are deliberately small so the qualification runs
# in seconds; they are NOT the study's parameters and never enter a search.
SMOKE_PARAMS = {
    "A-SC": {"coeff": 2, "AP": 14, "novolumedata": False, "src_col": "close",
             "alpha.condition_threshold": 50},
    "A-HMA": dict(min_length=8, max_length=24, minor_min=4, minor_max=12, flat=8.0,
                  atr_fast=6, atr_slow=18, mult=1.5, max_sl=2.0, take_profit=3.0,
                  min_profit=0.5, tick_size=0.01, sl_input="Half Distance Zone"),
    "A-VWAP": dict(rsi_len=14, rsi_os=35, rsi_ob=65, dev_mult=1.5, atr_len=14, stop_atr=2.0,
                   target_r=2.0, htf_ema_len=20, htf_tf="1h", exit_at_vwap=False,
                   time_stop_on=True, time_stop_bars=16),
    "A-HASH": dict(mom_len=10, ema_len=30, cooldown_bars=5, stop_loss_perc=2.0, rr_ratio=3.0,
                   tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
                   mom_threshold_mult=1.0),
}
DECISION_INTERVAL = {"A-SC": "15min", "A-VWAP": "15min", "A-HMA": "1h", "A-HASH": "15min"}


@dataclass
class QualificationResult:
    alpha_id: str
    symbol: str
    status: str
    bars: int
    slice_start: str | None = None
    slice_end: str | None = None
    checks: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_record(self) -> dict:
        return {
            "alpha_id": self.alpha_id, "symbol": self.symbol, "status": self.status,
            "bars": self.bars, "slice_start": self.slice_start, "slice_end": self.slice_end,
            "data_role": DATA_ROLE, "checks": self.checks, "error": self.error,
            "not_model_selection": True,
        }


def build_adapter_for(alpha_id: str, market: MarketSlice):
    from ..alphas.a_hash import HashMomentumEventAdapterV1
    from ..alphas.a_hma import AdaptiveHmaEventAdapterV1
    from ..alphas.a_sc import SignalCombineAdapterV1
    from ..alphas.a_vwap import VwapMeanReversionEventAdapterV1

    cls = {"A-SC": SignalCombineAdapterV1, "A-HMA": AdaptiveHmaEventAdapterV1,
           "A-VWAP": VwapMeanReversionEventAdapterV1,
           "A-HASH": HashMomentumEventAdapterV1}[alpha_id]
    return cls(SMOKE_PARAMS[alpha_id], market)


def qualify(alpha_id: str, symbol: str, bars: pd.DataFrame, *,
            backend: str = "reference") -> QualificationResult:
    """Run one alpha-symbol cell end to end on real bars."""
    import warnings

    frame = bars.copy()
    frame["time"] = pd.to_datetime(frame["time"])
    if frame["time"].dt.tz is None:
        frame["time"] = frame["time"].dt.tz_localize("UTC")
    frame = frame.set_index("time").sort_index()

    result = QualificationResult(alpha_id=alpha_id, symbol=symbol, status="UNKNOWN",
                                 bars=int(len(frame)),
                                 slice_start=str(frame.index[0]) if len(frame) else None,
                                 slice_end=str(frame.index[-1]) if len(frame) else None)
    try:
        market = MarketSlice(frame["open"].to_numpy(float), frame["high"].to_numpy(float),
                             frame["low"].to_numpy(float), frame["close"].to_numpy(float),
                             frame["volume"].to_numpy(float), index=frame.index)
        adapter = build_adapter_for(alpha_id, market)
        decisions = adapter.run()

        expected = pd.date_range(frame.index[0], frame.index[-1],
                                 freq=pd.infer_freq(frame.index[:20]) or None)
        gap_bars = int(len(expected) - len(frame)) if expected is not None else None

        blocked = [d for d in decisions if not d.warmup_ready]
        entries = [i for d in decisions for i in d.intents
                   if i.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT)]
        build = build_intent_tape(decisions, len(frame), unit_size=1.0)
        engine_frame = frame[["open", "high", "low", "close", "volume"]]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = run_intrabar(engine_frame, build, backend=backend, initial_capital=20000.0,
                               fee=0.0004, slippage_bps=1.0, use_funding=False,
                               close_on_last_bar=True)
        equity = np.asarray(out["equity"], dtype=float).reshape(-1)

        result.checks = {
            "decisions": len(decisions),
            "warmup_blocked_bars": len(blocked),
            "warmup_blocked_through": max((d.index for d in blocked), default=-1),
            "no_intent_during_warmup": all(not d.intents for d in blocked),
            "entries": len(entries),
            "engine_fills": len(out["fills"]),
            "account_trace_bars": int(equity.size),
            "account_trace_finite": bool(np.isfinite(equity).all()),
            "terminal_position": float(np.asarray(out["positions"]).reshape(-1)[-1]),
            "missing_bars_in_slice": gap_bars,
            "htf_blocked_reasons": sorted({d.blocked_reason for d in blocked
                                           if d.blocked_reason})[:3],
        }
        ok = (result.checks["no_intent_during_warmup"]
              and result.checks["account_trace_finite"]
              and result.checks["account_trace_bars"] == len(frame))
        result.status = "QUALIFIED" if ok else "FAILED_CHECKS"
    except Exception as exc:  # a failure here is a real domain failure
        result.status = "FAILED"
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def qualification_report(results: list[QualificationResult], not_ready: list[str]) -> dict:
    records = [r.as_record() for r in results]
    qualified = [r for r in records if r["status"] == "QUALIFIED"]
    return {
        "schema": "crypto_regime_lab.market_qualification.v1",
        "data_role": DATA_ROLE,
        "slice_policy": (
            "a bounded development slice per alpha-symbol; it checks gaps, HTF availability, "
            "warmup and the account trace only, and may never be reused as evidence for a result"
        ),
        "smoke_parameters": SMOKE_PARAMS,
        "smoke_parameter_policy": (
            "these lengths keep the smoke fast; they are not the study's parameters and never "
            "enter a search space"
        ),
        "decision_intervals": DECISION_INTERVAL,
        "cells_attempted": len(records),
        "cells_qualified": len(qualified),
        "results": records,
        "not_ready_alphas": not_ready,
        "not_ready_rule": (
            "an alpha carrying a LAB-02 blocker is still listed with all five of its cells; it is "
            "not silently dropped from the matrix"
        ),
        "status": "PASS" if len(qualified) == len(records) else "PARTIAL",
    }
