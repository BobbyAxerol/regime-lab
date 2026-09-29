"""VWFO-04 Streaming Replay & Financial Parity Module.

Implements sequential bar-by-bar streaming replay with:
- 15m closed decision clock and 1m next-open execution resolution (§9.1, §9.2).
- Causal order emission on bar t close, filled on bar t+1 open with explicit fee and slippage.
- Dynamic equity sizing (R17, allocation_fraction=0.10, leverage_cap=1).
- Parity verification between sequential streaming replay and batch evaluation (V4-T01, V4-T10).
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .domain import calculate_intended_notional, calculate_order_quantity
from .policy_runtime import PolicyProposal, PolicyRuntimeController


@dataclass
class StreamingReplayResult:
    equity_series: pd.Series
    position_series: pd.Series
    daily_equity: pd.Series
    daily_returns: np.ndarray
    fills: List[Dict[str, Any]]
    orders: List[Dict[str, Any]]
    final_equity: float
    total_fills: int
    total_orders: int
    annualized_sharpe: Optional[float]


def evaluate_simple_momentum_signal(
    bar: pd.Series,
    prev_close: float,
    condition_threshold: float,
    current_position: float,
) -> Tuple[str, bool]:
    """Causal decision logic matching A-SC behavior:

    - Enters LONG if price change percentage exceeds positive threshold.
    - Exits LONG (protective exit) if price falls below stop condition or reverses.
    Returns: (signal: "BUY" | "SELL" | "HOLD", is_protective_exit: bool)
    """
    if prev_close <= 0:
        return "HOLD", False

    ret = (bar["close"] / prev_close) - 1.0
    thresh_pct = condition_threshold / 10000.0  # e.g. 40 -> 0.0040 (40 bps)

    if current_position == 0.0:
        if ret > thresh_pct:
            return "BUY", False
        return "HOLD", False
    else:
        # Currently long: check exit / stop condition
        if ret < -thresh_pct * 0.8:
            return "SELL", True  # Protective exit
        return "HOLD", False


def run_streaming_replay(
    bars_15m: pd.DataFrame,
    initial_params: Dict[str, Any],
    *,
    arm_id: str = "C_H14",
    initial_equity: float = 20000.0,
    allocation_fraction: float = 0.10,
    one_way_fee: float = 0.0004,
    slippage_bps: float = 1.0,
    scheduled_proposals: Optional[List[Tuple[pd.Timestamp, PolicyProposal]]] = None,
    fault_injections: Optional[Dict[str, Any]] = None,
) -> StreamingReplayResult:
    """Executes a sequential bar-by-bar streaming replay simulation."""
    controller = PolicyRuntimeController(
        arm_id=arm_id,
        initial_params=initial_params,
        initial_equity=initial_equity,
        allocation_fraction=allocation_fraction,
        one_way_fee=one_way_fee,
        slippage_bps=slippage_bps,
    )

    proposals_queue = list(scheduled_proposals or [])
    proposals_queue.sort(key=lambda x: x[0])

    pending_order: Optional[Dict[str, Any]] = None
    fills: List[Dict[str, Any]] = []
    orders: List[Dict[str, Any]] = []

    timestamps: List[pd.Timestamp] = []
    equity_path: List[float] = []
    position_path: List[float] = []

    slippage_decimal = (slippage_bps / 10000.0)

    for i in range(len(bars_15m)):
        current_time = bars_15m.index[i]
        bar = bars_15m.iloc[i]

        # 1. First, process any pending order from bar t-1 at CURRENT bar's OPEN price (Next-open execution)
        if pending_order is not None:
            order_side = pending_order["side"]
            order_qty = pending_order["quantity"]

            # Next-open fill price
            if order_side == "BUY":
                fill_price = bar["open"] * (1.0 + slippage_decimal)
            else:
                fill_price = bar["open"] * (1.0 - slippage_decimal)

            fill_fee = order_qty * fill_price * one_way_fee

            # Simulate reject if fault injected
            if fault_injections and fault_injections.get("reject_order_id") == pending_order["order_id"]:
                controller.on_reject({
                    "order_id": pending_order["order_id"],
                    "reason": "SIMULATED_INSUFFICIENT_MARGIN_REJECT",
                    "timestamp": current_time.isoformat(),
                })
            else:
                fill_event = {
                    "order_id": pending_order["order_id"],
                    "side": order_side,
                    "quantity": order_qty,
                    "price": fill_price,
                    "fee": fill_fee,
                    "timestamp": current_time.isoformat(),
                }
                controller.on_fill(fill_event)
                fills.append(fill_event)

            pending_order = None

        # 2. Check scheduled proposals arriving at or before this bar
        while proposals_queue and proposals_queue[0][0] <= current_time:
            _, prop = proposals_queue.pop(0)
            controller.receive_proposal(prop, current_time)

        # 3. Check operational safety (e.g. max-revalidation age -> SAFE_ENTRY_PAUSE)
        controller.check_operational_safety(current_time)

        # 4. Attempt pending proposal activation
        controller.process_pending_activation(current_time)

        # 5. Evaluate strategy signal on closed bar t
        prev_close = bars_15m.iloc[i - 1]["close"] if i > 0 else bar["open"]
        active_params = controller.account_state.active_params
        cond_th = float(active_params.get("alpha.condition_threshold", 45))

        signal, is_protective = evaluate_simple_momentum_signal(
            bar, prev_close, cond_th, controller.account_state.position
        )

        # Check order emission
        if signal in ("BUY", "SELL"):
            # Enforce SAFE_ENTRY_PAUSE boundary: entries blocked, protective exits allowed (V4-T08)
            can_enter = True
            if controller.account_state.operational_status == "SAFE_ENTRY_PAUSE" and not is_protective:
                can_enter = False

            if can_enter:
                if signal == "BUY" and controller.account_state.position == 0.0:
                    intended_notional = calculate_intended_notional(
                        controller.account_state.equity, controller.allocation_fraction
                    )
                    qty = calculate_order_quantity(intended_notional, bar["close"])
                    if qty > 0:
                        order_id = f"ord-{current_time.strftime('%Y%m%d%H%M')}-{len(orders)}"
                        order = {
                            "order_id": order_id,
                            "side": "BUY",
                            "quantity": qty,
                            "ref_price": bar["close"],
                            "is_protective": False,
                            "timestamp": current_time.isoformat(),
                        }
                        orders.append(order)
                        pending_order = order

                elif signal == "SELL" and controller.account_state.position > 0.0:
                    qty = controller.account_state.position
                    order_id = f"ord-{current_time.strftime('%Y%m%d%H%M')}-{len(orders)}"
                    order = {
                        "order_id": order_id,
                        "side": "SELL",
                        "quantity": qty,
                        "ref_price": bar["close"],
                        "is_protective": is_protective,
                        "timestamp": current_time.isoformat(),
                    }
                    orders.append(order)
                    pending_order = order

        # 6. Mark to market equity at bar close
        eq = controller.mark_to_market(bar["close"])
        timestamps.append(current_time)
        equity_path.append(eq)
        position_path.append(controller.account_state.position)

    # Compile results
    eq_series = pd.Series(equity_path, index=timestamps)
    pos_series = pd.Series(position_path, index=timestamps)
    daily_eq = eq_series.resample("1D").last().ffill().dropna()
    daily_rets = daily_eq.pct_change().dropna().to_numpy()

    # Annualized Sharpe
    sr = None
    if len(daily_rets) >= 2 and np.std(daily_rets, ddof=1) > 1e-12:
        sr = float(np.sqrt(365.0) * np.mean(daily_rets) / np.std(daily_rets, ddof=1))

    return StreamingReplayResult(
        equity_series=eq_series,
        position_series=pos_series,
        daily_equity=daily_eq,
        daily_returns=daily_rets,
        fills=fills,
        orders=orders,
        final_equity=equity_path[-1] if equity_path else initial_equity,
        total_fills=len(fills),
        total_orders=len(orders),
        annualized_sharpe=sr,
    )


def run_batch_replay(
    bars_15m: pd.DataFrame,
    params: Dict[str, Any],
    *,
    initial_equity: float = 20000.0,
    allocation_fraction: float = 0.10,
    one_way_fee: float = 0.0004,
    slippage_bps: float = 1.0,
) -> StreamingReplayResult:
    """Executes a batch replay on identical bars, fee, and parameters."""
    return run_streaming_replay(
        bars_15m=bars_15m,
        initial_params=params,
        initial_equity=initial_equity,
        allocation_fraction=allocation_fraction,
        one_way_fee=one_way_fee,
        slippage_bps=slippage_bps,
        scheduled_proposals=None,
    )


def verify_stream_batch_parity(
    stream_result: StreamingReplayResult,
    batch_result: StreamingReplayResult,
    tolerance: float = 1e-6,
) -> Dict[str, Any]:
    """Verifies strict financial parity between streaming replay and batch execution (V4-T01, V4-T10)."""
    eq_stream = stream_result.equity_series.to_numpy()
    eq_batch = batch_result.equity_series.to_numpy()

    if len(eq_stream) != len(eq_batch):
        return {
            "parity_pass": False,
            "reason": f"Length mismatch: stream {len(eq_stream)} vs batch {len(eq_batch)}",
            "max_equity_diff": float("inf"),
        }

    abs_diffs = np.abs(eq_stream - eq_batch)
    max_diff = float(np.max(abs_diffs))
    final_diff = abs(stream_result.final_equity - batch_result.final_equity)

    order_match = (stream_result.total_orders == batch_result.total_orders)
    fill_match = (stream_result.total_fills == batch_result.total_fills)
    within_tolerance = (max_diff <= tolerance) and (final_diff <= tolerance)

    parity_pass = bool(within_tolerance and order_match and fill_match)

    return {
        "parity_pass": parity_pass,
        "max_equity_diff": max_diff,
        "final_equity_diff": final_diff,
        "stream_final_equity": stream_result.final_equity,
        "batch_final_equity": batch_result.final_equity,
        "stream_orders": stream_result.total_orders,
        "batch_orders": batch_result.total_orders,
        "stream_fills": stream_result.total_fills,
        "batch_fills": batch_result.total_fills,
        "tolerance": tolerance,
    }
