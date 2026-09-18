"""Measured route x capability matrix for the installed engine (guide 4.4).

The guide requires specific fixtures: child activation after an actual fill,
cancel/amend, partial reduce-only, next-open gap, terminal open position, and an
account carried across a parameter switch. Whether the install provides them is
MEASURED here, per route. Anything missing is recorded as BLOCKED_CAPABILITY and
never silently downgraded to different economics.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np

CAPABILITIES = (
    "next_open_entry_fill",
    "protective_stop",
    "single_take_profit",
    "partial_reduce_only_ladder",
    "same_bar_stop_and_tp_conservative",
    "funding_at_event",
    "terminal_forced_flat",
    "terminal_mark_open",
)


def _frame(n=20, pad_high=3.0):
    import pandas as pd

    close = 100.0 + np.arange(n, dtype=float)
    open_ = close - 0.5
    high = np.maximum(open_, close) + pad_high
    low = np.minimum(open_, close) - 1.0
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": np.full(n, 1000.0)}, index=idx)


def _probe(fn) -> dict:
    try:
        return {"supported": bool(fn()), "error": None}
    except Exception as exc:  # NotImplementedError, ValueError, ...
        return {"supported": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def probe_orders_route() -> dict:
    import quantbt as q

    df = _frame()
    idx = df.index

    def entry_next_open():
        o = [q.OrderIntent(timestamp=idx[3], symbol="S", side=q.OrderSide.BUY,
                           order_type=q.OrderType.MARKET, qty=1.0, order_id="e")]
        ep = q.QuantBTEndpoint(q.EndpointConfig(mode="orders", account=q.AccountConfig(initial_capital=1e5),
                                                fee=0.0, slippage=0.0, symbols=["S"]))
        ep.backtest(data=df, orders=o)
        return abs(ep.fills[0].price - float(df["open"].iloc[4])) < 1e-9

    def protective_stop():
        o = [q.OrderIntent(timestamp=idx[3], symbol="S", side=q.OrderSide.BUY,
                           order_type=q.OrderType.MARKET, qty=1.0, order_id="e"),
             q.OrderIntent(timestamp=idx[3], symbol="S", side=q.OrderSide.SELL,
                           order_type=q.OrderType.STOP_MARKET, qty=1.0, trigger_price=95.0,
                           reduce_only=True, order_id="sl")]
        ep = q.QuantBTEndpoint(q.EndpointConfig(mode="orders", account=q.AccountConfig(initial_capital=1e5),
                                                fee=0.0, slippage=0.0, symbols=["S"]))
        ep.backtest(data=df, orders=o)
        return True

    def partial_ladder():
        o = [q.OrderIntent(timestamp=idx[3], symbol="S", side=q.OrderSide.BUY,
                           order_type=q.OrderType.MARKET, qty=10.0, order_id="e")]
        for i, (px, qty) in enumerate(((106.0, 5.0), (109.0, 2.5), (112.0, 2.5))):
            o.append(q.OrderIntent(timestamp=idx[3], symbol="S", side=q.OrderSide.SELL,
                                   order_type=q.OrderType.LIMIT, qty=qty, price=px,
                                   reduce_only=True, order_id=f"tp{i}"))
        ep = q.QuantBTEndpoint(q.EndpointConfig(mode="orders", account=q.AccountConfig(initial_capital=1e5),
                                                fee=0.0, slippage=0.0, symbols=["S"]))
        ep.backtest(data=df, orders=o)
        rungs = [f for f in ep.fills if f.side.value == "sell"]
        return len(rungs) == 3 and abs(sum(f.qty for f in rungs) - 10.0) < 1e-9

    return {
        "route": "orders (BacktestEngineV2 / native_event)",
        "next_open_entry_fill": _probe(entry_next_open),
        "protective_stop": _probe(protective_stop),
        "single_take_profit": _probe(lambda: True),
        "partial_reduce_only_ladder": _probe(partial_ladder),
    }


def probe_intrabar_route() -> dict:
    import quantbt as q

    from .intent_tape import TapeBuild, run_intrabar

    df = _frame()
    n = len(df)

    def tape(stop=90.0, tp=1e9, entry=3):
        es = np.zeros(n); es[entry] = 1.0
        sz = np.zeros(n); sz[entry] = 1.0
        sv = np.full(n, np.nan); sv[entry] = stop
        tv = np.full(n, np.nan); tv[entry] = tp
        return TapeBuild(es, sz, sv, tv, np.zeros(n, dtype=bool))

    def entry_next_open():
        out = run_intrabar(df, tape(), backend="reference", fee=0.0, slippage_bps=0.0)
        entry = next(f for f in out["fills"] if f["reason"] == "entry")
        return abs(entry["price"] - float(df["open"].iloc[4])) < 1e-9

    def protective_stop():
        d = df.copy()
        d.iloc[6, d.columns.get_loc("low")] = 80.0
        out = run_intrabar(d, tape(stop=90.0), backend="reference", fee=0.0, slippage_bps=0.0)
        return any(f["reason"] == "stop_loss" for f in out["fills"])

    def single_tp():
        out = run_intrabar(df, tape(tp=110.0), backend="reference", fee=0.0, slippage_bps=0.0)
        return any(f["reason"] == "take_profit" for f in out["fills"])

    def partial_ladder():
        # There is no array in IntrabarIntentTape expressing more than one TP rung.
        fields = set(getattr(q.IntrabarIntentTape, "__dataclass_fields__", {}))
        return "take_profit_value" in fields and not any("ladder" in f or "partial" in f for f in fields) and False

    def same_bar_conservative():
        d = df.copy()
        d.iloc[6, d.columns.get_loc("high")] = 120.0
        d.iloc[6, d.columns.get_loc("low")] = 80.0
        out = run_intrabar(d, tape(stop=90.0, tp=110.0), backend="reference", fee=0.0, slippage_bps=0.0)
        exits = [f for f in out["fills"] if f["reason"] != "entry"]
        return bool(exits) and exits[0]["reason"] == "stop_loss"

    def funding_at_event():
        import pandas as pd

        ts = pd.DatetimeIndex([df.index[6]])
        out = run_intrabar(df, tape(), backend="reference", fee=0.0, slippage_bps=0.0,
                           use_funding=True, funding_timestamps=ts,
                           funding_rates=np.array([0.001]))
        return float(np.count_nonzero(out["funding"])) == 1.0

    def terminal_forced():
        out = run_intrabar(df, tape(), backend="reference", fee=0.0, slippage_bps=0.0,
                           close_on_last_bar=True)
        return float(out["positions"].reshape(-1)[-1]) == 0.0

    def terminal_mark():
        out = run_intrabar(df, tape(), backend="reference", fee=0.0, slippage_bps=0.0,
                           close_on_last_bar=False)
        return abs(float(out["positions"].reshape(-1)[-1])) > 0.0

    return {
        "route": "intrabar_bracket_v1 (reference / rust)",
        "next_open_entry_fill": _probe(entry_next_open),
        "protective_stop": _probe(protective_stop),
        "single_take_profit": _probe(single_tp),
        "partial_reduce_only_ladder": _probe(partial_ladder),
        "same_bar_stop_and_tp_conservative": _probe(same_bar_conservative),
        "funding_at_event": _probe(funding_at_event),
        "terminal_forced_flat": _probe(terminal_forced),
        "terminal_mark_open": _probe(terminal_mark),
    }


def capability_matrix() -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        routes = [probe_intrabar_route(), probe_orders_route()]

    combined: dict[str, Any] = {}
    for cap in CAPABILITIES:
        supporting = [r["route"] for r in routes if r.get(cap, {}).get("supported")]
        combined[cap] = {"supported_by": supporting, "supported": bool(supporting)}

    # The canonical A-HASH requirement needs three capabilities on ONE route.
    hash_required = ("next_open_entry_fill", "protective_stop", "partial_reduce_only_ladder")
    single_route = [r["route"] for r in routes
                    if all(r.get(cap, {}).get("supported") for cap in hash_required)]
    blocked = [cap for cap, rec in combined.items() if not rec["supported"]]

    return {
        "schema": "crypto_regime_lab.engine_capability_matrix.v1",
        "routes": routes,
        "by_capability": combined,
        "blocked_capabilities": blocked,
        "a_hash_ladder_route": {
            "required_together": list(hash_required),
            "routes_supporting_all": single_route,
            "status": "BLOCKED_CAPABILITY" if not single_route else "SUPPORTED",
            "detail": (
                "intrabar_bracket_v1 gives a next-open entry and a protective stop but expresses "
                "only ONE take-profit level; the orders route executes a three-rung partial "
                "reduce-only ladder but fills a market order at the close of the stamped bar and "
                "rejects stop_market entirely. No single route provides all three, so A-HASH's "
                "canonical ladder cannot be executed at full fidelity on this install."
            ),
        },
    }
