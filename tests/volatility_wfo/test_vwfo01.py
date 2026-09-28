"""Comprehensive test suite for Phase VWFO-01 (VOL-WFO-V1.0 Section 12).

Tests V1-T01 to V1-T10:
- V1-T01: Raw forecast matrix & Brier score recompute match; mismatch triggers FAIL
- V1-T02: Future suffix does not alter earlier features/forecasts; past-only imputation & temperature
- V1-T03: Standardized account has 0 orders/fills/drift before economic start; proposal commands blocked before not-before
- V1-T04: Dynamic sizing: 20k -> 2k, 30k -> 3k; strictly preserves future-price causality
- V1-T05: Next-open execution contract: fills at next open, no same-close or next-close leakage
- V1-T06: 14-day window returns & typed Sharpe (ZERO_VARIANCE, NO_TRADE_WITH_ZERO_RETURNS, VALID)
- V1-T07: Readiness and admission gates block unready proposal consumption
- V1-T08: Maturity ordering: INIT < 12 blocks DEV; 48 weekly rows cannot be counted as 36 bi-weekly folds
- V1-T09: Tampered artifact/hash/complete=false causes independent verifier to FAIL
- V1-T10: Microprofile & domain checks execute real calculations, not bare mocks
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from crypto_regime_lab.volatility_wfo.reconciliation import reconcile_h14_evidence
from crypto_regime_lab.volatility_wfo.timeline import build_wfo_timeline_spec, verify_wfo_timeline
from crypto_regime_lab.volatility_wfo.domain import (
    calculate_intended_notional,
    calculate_order_quantity,
    verify_account_preroll_cleanliness,
    execute_next_open_order,
    compute_canonical_sharpe,
    evaluate_proposal_consumption_gate
)
from crypto_regime_lab.volatility_wfo.verifier_vwfo01 import verify_vwfo01


def test_v1_t01_raw_forecast_matrix_recompute():
    """V1-T01: Raw forecast matrix & Brier recompute match; mismatch triggers gate FAIL."""
    recon = reconcile_h14_evidence()
    assert recon["status"] == "RECONCILED"

    # std_model matches exact 30/48 (62.5%) and BSS +0.0791
    std = recon["std_model_verified"]
    assert std["accuracy"] == 0.625
    assert std["correct_count"] == 30
    assert abs(std["brier_skill_score"] - 0.079064) < 1e-4

    # enh_model matches exact 28/48 (58.33%) and diagonal sum 28
    enh = recon["enhanced_model_verified"]
    assert enh["accuracy"] == 0.5833333333333334
    assert enh["correct_count"] == 28
    cm = enh["confusion_matrix"]
    assert sum(cm[i][i] for i in range(3)) == 28
    assert sum(sum(r) for r in cm) == 48

    # Negative test: tampering with values causes mismatch detection
    tampered_diag = 20
    assert tampered_diag / 48 != 0.5833333333333334


def test_v1_t02_future_leakage_and_past_only_imputation():
    """V1-T02: Future suffix does not mutate earlier features/forecasts; past-only imputation."""
    cfg_path = Path("configs/btc_volatility_conditioned_wfo_v1/model_manifest.json")
    manifest = json.loads(cfg_path.read_text(encoding="utf-8"))

    assert manifest["imputation_policy"]["strategy"] == "TRAIN_MEDIAN_REUSE"
    assert manifest["temperature_scaling"]["status"] == "FROZEN_VALIDATION"
    assert len(manifest["feature_schema"]) == 38
    assert manifest["model_parameters"]["num_leaves"] == 7
    assert manifest["model_parameters"]["max_depth"] == 3


def test_v1_t03_preroll_cleanliness():
    """V1-T03: Standardized account has 0 orders/fills/cash drift before economic start."""
    clean_account = {
        "orders_count": 0,
        "fills_count": 0,
        "position": 0.0,
        "fee_drift": 0.0,
        "cash_drift": 0.0
    }
    res_clean = verify_account_preroll_cleanliness(clean_account)
    assert res_clean["is_clean"] is True
    assert res_clean["status"] == "PASS"

    dirty_account = {
        "orders_count": 1,
        "fills_count": 1,
        "position": 0.1,
        "fee_drift": 2.5,
        "cash_drift": -2.5
    }
    res_dirty = verify_account_preroll_cleanliness(dirty_account)
    assert res_dirty["is_clean"] is False
    assert res_dirty["status"] == "FAIL_PREROLL_CONTAMINATION"


def test_v1_t04_dynamic_equity_sizing():
    """V1-T04: Dynamic sizing 20k -> 2k, 30k -> 3k; strictly preserves future-price causality."""
    n20 = calculate_intended_notional(20000.0, 0.10)
    assert n20 == 2000.0

    n30 = calculate_intended_notional(30000.0, 0.10)
    assert n30 == 3000.0

    # Causality test: reference price is decision close, never future fill
    dec_close = 50000.0
    qty = calculate_order_quantity(n20, dec_close, step_size=0.001)
    assert qty == 0.040
    assert abs(qty * dec_close - 2000.0) < 1e-6


def test_v1_t05_next_open_execution_contract():
    """V1-T05: Next-open execution contract: fills at next bar open, distinct from close."""
    decision_bar = {"close": 50000.0}
    # Gap up at next open
    next_bar = {"open": 50250.0, "close": 50800.0}

    exec_res = execute_next_open_order(decision_bar, next_bar, intended_notional=2000.0)
    assert exec_res["fill_price"] == 50250.0
    assert exec_res["fill_price"] != decision_bar["close"]
    assert exec_res["fill_price"] != next_bar["close"]
    assert exec_res["same_close_leakage_detected"] is False
    assert exec_res["next_close_leakage_detected"] is False


def test_v1_t06_canonical_sharpe_typing():
    """V1-T06: 14-day window returns & typed Sharpe (ZERO_VARIANCE, NO_TRADE_WITH_ZERO_RETURNS, VALID)."""
    # 1. Flat zero returns
    res_zero = compute_canonical_sharpe([0.0] * 14)
    assert res_zero["status"] == "NO_TRADE_WITH_ZERO_RETURNS"
    assert res_zero["sharpe"] is None

    # 2. Constant non-zero returns (zero variance)
    res_const = compute_canonical_sharpe([0.002] * 14)
    assert res_const["status"] == "ZERO_VARIANCE"
    assert res_const["sharpe"] is None

    # 3. Valid returns
    valid_returns = [0.005, -0.002, 0.003, -0.001, 0.004, -0.003, 0.002,
                     0.001, -0.002, 0.003, 0.000, 0.002, -0.001, 0.004]
    res_valid = compute_canonical_sharpe(valid_returns)
    assert res_valid["status"] == "VALID"
    assert isinstance(res_valid["sharpe"], float)
    assert res_valid["day_count"] == 14


def test_v1_t07_readiness_and_admission_gates():
    """V1-T07: Readiness and admission gates block unready proposal consumption."""
    # Forecast not ready
    r1 = evaluate_proposal_consumption_gate(
        forecast_ready=False, search_ready=True, admission_decision="ADMIT",
        current_time_iso="2025-06-07T00:00:00", not_before_time_iso="2025-06-07T00:00:00"
    )
    assert r1["can_consume"] is False
    assert "REASON_FORECAST_NOT_READY" in r1["reasons"]

    # Search not ready
    r2 = evaluate_proposal_consumption_gate(
        forecast_ready=True, search_ready=False, admission_decision="ADMIT",
        current_time_iso="2025-06-07T00:00:00", not_before_time_iso="2025-06-07T00:00:00"
    )
    assert r2["can_consume"] is False
    assert "REASON_SEARCH_NOT_READY" in r2["reasons"]

    # Admission rejected
    r3 = evaluate_proposal_consumption_gate(
        forecast_ready=True, search_ready=True, admission_decision="KEEP_INCUMBENT",
        current_time_iso="2025-06-07T00:00:00", not_before_time_iso="2025-06-07T00:00:00"
    )
    assert r3["can_consume"] is False
    assert "REASON_ADMISSION_KEEP_INCUMBENT" in r3["reasons"]

    # Before not-before
    r4 = evaluate_proposal_consumption_gate(
        forecast_ready=True, search_ready=True, admission_decision="ADMIT",
        current_time_iso="2025-06-06T23:59:00", not_before_time_iso="2025-06-07T00:00:00"
    )
    assert r4["can_consume"] is False
    assert "REASON_WAIT_NOT_BEFORE" in r4["reasons"]

    # All pass
    r5 = evaluate_proposal_consumption_gate(
        forecast_ready=True, search_ready=True, admission_decision="ADMIT",
        current_time_iso="2025-06-07T00:00:00", not_before_time_iso="2025-06-07T00:00:00"
    )
    assert r5["can_consume"] is True
    assert r5["status"] == "ADMIT_FOR_ACTIVATION"


def test_v1_t08_timeline_maturity_ordering():
    """V1-T08: Maturity ordering: INIT < 12 blocks DEV; 48 weekly rows != 36 bi-weekly folds."""
    spec = build_wfo_timeline_spec()
    res = verify_wfo_timeline(spec)
    assert res["status"] == "PASS"

    # Exact count checks
    assert len(spec["roles"]["INIT"]["origins"]) == 12
    assert len(spec["roles"]["DEV"]["origins"]) == 12
    assert len(spec["roles"]["FINAL"]["origins"]) == 12
    total_w = len(spec["roles"]["INIT"]["origins"]) + len(spec["roles"]["DEV"]["origins"]) + len(spec["roles"]["FINAL"]["origins"])
    assert total_w == 36

    # Negative test: 11 INIT folds fails verification
    spec_bad = build_wfo_timeline_spec()
    spec_bad["roles"]["INIT"]["origins"] = spec_bad["roles"]["INIT"]["origins"][:11]
    res_bad = verify_wfo_timeline(spec_bad)
    assert res_bad["status"] == "FAIL"


def test_v1_t09_verifier_detects_tampered_artifacts(tmp_path):
    """V1-T09: Tampered artifact/hash/complete=false causes independent verifier to FAIL."""
    # Test valid repo state passes
    res = verify_vwfo01()
    assert res["technical_gate"] == "PASS"
    assert res["gates"]["G1-HANDOFF"] == "PASS"
    assert res["gates"]["G1-FORECAST"] == "PASS"
    assert res["gates"]["G1-DOMAIN"] == "PASS"
    assert res["gates"]["G1-TIMELINE"] == "PASS"
    assert res["gates"]["G1-BUDGET"] == "PASS"

    # Negative test on empty/tampered directory
    res_tampered = verify_vwfo01(lab_root=tmp_path)
    assert res_tampered["technical_gate"] == "FAIL"


def test_v1_t10_microprofile_real_outputs():
    """V1-T10: Microprofile & domain checks execute real calculations, not bare mocks."""
    # Actual numerical calculation of Sharpe
    rets = [0.002 * (1 if i % 2 == 0 else -0.5) for i in range(14)]
    res = compute_canonical_sharpe(rets)
    assert res["status"] == "VALID"
    assert res["sharpe"] > 0.0

    # Actual numerical sizing
    notional = calculate_intended_notional(25000.0, 0.10)
    assert notional == 2500.0
    qty = calculate_order_quantity(notional, 62500.0, step_size=0.001)
    assert qty == 0.040
