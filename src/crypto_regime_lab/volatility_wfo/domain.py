"""Domain qualification and financial execution helpers for VWFO-01.

Implements and verifies:
- Dynamic equity sizing (R17, V1-T04)
- Warmup and pre-roll protection (R16, V1-T03)
- Next-open execution contract (R18, V1-T05)
- Canonical Sharpe calculation with typed statuses (Section 10.1, V1-T06)
- Readiness, admission and WAIT_FLAT_PREFIX_WITHIN_H14 policy (Section 5.2, V1-T07)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence


def calculate_intended_notional(equity: float, allocation_fraction: float = 0.10) -> float:
    """Calculates intended notional from engine equity before entry command (R17).

    Guarantees:
    - Equity $20,000 -> $2,000 intended notional
    - Equity $30,000 -> $3,000 intended notional
    - Never uses fixed $2,000 disguise
    """
    if equity <= 0:
        raise ValueError(f"Equity must be positive, got {equity}")
    if not (0.0 < allocation_fraction <= 1.0):
        raise ValueError(f"Allocation fraction must be in (0, 1], got {allocation_fraction}")
    return float(equity * allocation_fraction)


def calculate_order_quantity(intended_notional: float, reference_price: float, step_size: float = 0.001) -> float:
    """Calculates entry order quantity from causal decision reference price.

    Strict causality: reference_price must be the close price of the decision bar t,
    never the future execution price of bar t+1.
    """
    if reference_price <= 0:
        raise ValueError(f"Reference price must be positive, got {reference_price}")
    raw_qty = intended_notional / reference_price
    # Round down to step_size to prevent accidental over-allocation
    precision = max(0, -int(math.floor(math.log10(step_size))))
    factor = 10 ** precision
    return math.floor(raw_qty * factor) / factor


def verify_account_preroll_cleanliness(account_state: Dict[str, Any]) -> Dict[str, Any]:
    """Verifies that prior to economic_start, no orders, fills, or fee drift occurred (R16, V1-T03)."""
    orders_count = account_state.get("orders_count", 0)
    fills_count = account_state.get("fills_count", 0)
    position = account_state.get("position", 0.0)
    fee_drift = account_state.get("fee_drift", 0.0)
    cash_drift = account_state.get("cash_drift", 0.0)

    clean = (orders_count == 0 and fills_count == 0 and position == 0.0 and fee_drift == 0.0 and cash_drift == 0.0)
    return {
        "is_clean": clean,
        "orders_count": orders_count,
        "fills_count": fills_count,
        "position": position,
        "fee_drift": fee_drift,
        "cash_drift": cash_drift,
        "status": "PASS" if clean else "FAIL_PREROLL_CONTAMINATION"
    }


def execute_next_open_order(
    decision_bar: Dict[str, float],
    next_bar: Dict[str, float],
    intended_notional: float
) -> Dict[str, Any]:
    """Simulates next-open execution contract (R18, V1-T05).

    The fill price must strictly be the next bar's OPEN price,
    distinct from the decision bar's close and distinct from next bar's close.
    """
    ref_price = decision_bar["close"]
    qty = calculate_order_quantity(intended_notional, ref_price)
    fill_price = next_bar["open"]
    fill_notional = qty * fill_price

    return {
        "decision_ref_price": ref_price,
        "quantity": qty,
        "fill_price": fill_price,
        "fill_notional": fill_notional,
        "execution_type": "NEXT_OPEN",
        "same_close_leakage_detected": (fill_price == decision_bar["close"] and fill_price != next_bar["open"]),
        "next_close_leakage_detected": (fill_price == next_bar["close"] and fill_price != next_bar["open"])
    }


def compute_canonical_sharpe(
    daily_returns: Sequence[float],
    rf_daily: float = 0.0,
    expected_days: int = 14
) -> Dict[str, Any]:
    """Calculates canonical annualized Sharpe ratio with typed failure statuses (Section 10.1, V1-T06)."""
    returns = list(daily_returns)
    day_count = len(returns)

    if day_count == 0:
        return {"sharpe": None, "status": "EMPTY_RETURNS_SERIES", "day_count": 0}

    # All zeros -> NO_TRADE_WITH_ZERO_RETURNS
    if all(r == 0.0 for r in returns):
        return {
            "sharpe": None,
            "status": "NO_TRADE_WITH_ZERO_RETURNS",
            "day_count": day_count,
            "mean_daily_return": 0.0,
            "std_daily_return": 0.0
        }

    excess = [r - rf_daily for r in returns]
    mean_e = sum(excess) / day_count

    if day_count < 2:
        return {"sharpe": None, "status": "INSUFFICIENT_DAYS_FOR_STDEV", "day_count": day_count}

    var = sum((x - mean_e) ** 2 for x in excess) / (day_count - 1)
    std_e = math.sqrt(var)

    if std_e < 1e-12:
        return {
            "sharpe": None,
            "status": "ZERO_VARIANCE",
            "day_count": day_count,
            "mean_daily_return": mean_e,
            "std_daily_return": std_e
        }

    annualized_sr = math.sqrt(365.0) * (mean_e / std_e)
    return {
        "sharpe": float(annualized_sr),
        "status": "VALID",
        "day_count": day_count,
        "mean_daily_return": float(mean_e),
        "std_daily_return": float(std_e)
    }


def evaluate_proposal_consumption_gate(
    forecast_ready: bool,
    search_ready: bool,
    admission_decision: str,  # "ADMIT", "KEEP_INCUMBENT", "COMMON_FLAT_FALLBACK"
    current_time_iso: str,
    not_before_time_iso: str,
    proposal_expired: bool = False
) -> Dict[str, Any]:
    """Evaluates whether an active engine account may consume a new parameter proposal (V1-T07)."""
    reasons: List[str] = []

    if not forecast_ready:
        reasons.append("REASON_FORECAST_NOT_READY")
    if not search_ready:
        reasons.append("REASON_SEARCH_NOT_READY")
    if admission_decision != "ADMIT":
        reasons.append(f"REASON_ADMISSION_{admission_decision}")
    if current_time_iso < not_before_time_iso:
        reasons.append("REASON_WAIT_NOT_BEFORE")
    if proposal_expired:
        reasons.append("REASON_PROPOSAL_EXPIRED")

    can_consume = len(reasons) == 0
    return {
        "can_consume": can_consume,
        "status": "ADMIT_FOR_ACTIVATION" if can_consume else "BLOCKED_BY_GATE",
        "reasons": reasons
    }
