"""Correct transaction-cost binding for the corrective Mode 4 study (A01).

The installed endpoint has TWO fee parameters with different conventions:

* ``EndpointConfig.fee`` is a legacy ROUND-TRIP rate (the legacy engines split it
  in half internally: ``fee_oneway = fee / 2``);
* ``EndpointConfig.fee_rate`` / ``v2_fee_rate`` is the canonical ONE-WAY rate.

The lab registers a ONE-WAY taker rate (0.0004). COR-13 passed it as ``fee``, so
every account paid half. The corrected routes below always pass BOTH, made from
one declared one-way rate::

    fee      = 2 * one_way
    fee_rate = one_way

No route may silently halve or double the registered cost. This module is the
active route layer for the corrective study; the old ``intent_tape.run_intrabar``
path stays as audit-only evidence of the defect.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .intent_tape import TapeBuild

ONE_WAY_TAKER_FEE = 0.0004
SLIPPAGE_BPS = 1.0


class RouteError(RuntimeError):
    """A route cannot be executed with the registered economic contract."""


def bound_fee_kwargs(one_way_fee: float = ONE_WAY_TAKER_FEE) -> dict[str, float]:
    """The only place fee conventions are translated. One way in, both out."""
    one_way = float(one_way_fee)
    if one_way < 0:
        raise RouteError(f"one-way fee must be >= 0, got {one_way!r}")
    return {"fee": 2.0 * one_way, "fee_rate": one_way}


def _reason(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value).lower()
    return str(value)


def run_intrabar_route(frame, tape_build: TapeBuild, *, backend: str = "reference",
                       initial_capital: float = 20000.0,
                       one_way_fee: float = ONE_WAY_TAKER_FEE,
                       slippage_bps: float = SLIPPAGE_BPS, use_funding: bool = False,
                       funding_timestamps=None, funding_rates=None,
                       close_on_last_bar: bool = True, symbol: str = "S",
                       sizing_mode: str = "units",
                       unit_notional: float | None = None) -> dict:
    """Execute an intrabar tape with the registered one-way cost bound once."""
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
        slippage_bps=slippage_bps, symbols=[symbol], use_funding=use_funding,
        **bound_fee_kwargs(one_way_fee),
    )
    if sizing is q.IntrabarSizingMode.FIXED_NOTIONAL:
        if unit_notional is None:
            raise RouteError("fixed_notional sizing requires unit_notional")
        kwargs["alloc_per_trade"] = float(unit_notional)
    elif unit_notional is not None:
        raise RouteError("unit_notional only applies to sizing_mode='fixed_notional'")

    endpoint = factory(**kwargs)
    backtest_kwargs: dict[str, Any] = {"data": frame, "intent": tape_build.as_tape()}
    if funding_timestamps is not None:
        backtest_kwargs["funding_event_timestamps"] = funding_timestamps
        backtest_kwargs["funding_event_rates"] = funding_rates
    result = endpoint.backtest(**backtest_kwargs)

    fills = []
    for fill in (getattr(result, "fills", None) or []):
        fills.append({
            "bar_index": int(getattr(fill, "bar_index", -1)),
            "sequence": int(getattr(fill, "sequence", -1)),
            "side": float(getattr(fill, "side", 0.0)),
            "qty": float(getattr(fill, "qty", 0.0)),
            "price": float(getattr(fill, "price", 0.0)),
            "fee": float(getattr(fill, "fee", 0.0)),
            "reason": _reason(getattr(fill, "reason", "unknown")),
        })
    return {
        "backend": backend,
        "engine_id": "intrabar_bracket_v1",
        "contract": {
            "one_way_fee": float(one_way_fee),
            "bound": bound_fee_kwargs(one_way_fee),
            "slippage_bps": float(slippage_bps),
        },
        "equity": np.asarray(getattr(result, "equity", []), dtype=float),
        "positions": np.asarray(getattr(result, "positions", []), dtype=float),
        "fees": np.asarray(getattr(result, "fees", []), dtype=float),
        "funding": np.asarray(getattr(result, "funding", []), dtype=float),
        "fills": fills,
        "liquidated": bool(getattr(result, "liquidated", False)),
        "result": result,
    }


def realized_fee_rate(fill: dict) -> float:
    """The one-way rate actually charged on one fill, from its own notional."""
    notional = abs(float(fill["qty"]) * float(fill["price"]))
    if notional <= 0.0:
        raise RouteError(f"fill has zero notional: {fill!r}")
    return abs(float(fill["fee"])) / notional
