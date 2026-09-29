"""Independent Gate Verifier for VWFO-01.

Validates the 6 Exit Gates of Phase VWFO-01:
- G1-HANDOFF: Model evidence reconciled, discrepancies explained, bridge status defined.
- G1-FORECAST: Model recipe, 38 features, imputation, temperature, taxonomy qualified.
- G1-DOMAIN: Sizing, warmup, next-open execution, and Sharpe typing verified.
- G1-TIMELINE: 36 decision windows, causality, maturity ordering verified.
- G1-BUDGET: Planned trials, resources, no production writes verified.
- G1-OWNER: Checks owner review status (PENDING until explicit approval).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .reconciliation import reconcile_h14_evidence
from .timeline import build_wfo_timeline_spec, verify_wfo_timeline
from .domain import (
    calculate_intended_notional,
    calculate_order_quantity,
    verify_account_preroll_cleanliness,
    execute_next_open_order,
    compute_canonical_sharpe,
    evaluate_proposal_consumption_gate
)


def verify_gate_handoff(lab_root: Path | None = None) -> Dict[str, Any]:
    try:
        recon = reconcile_h14_evidence(lab_root)
        holds = (
            recon["status"] == "RECONCILED"
            and recon["std_model_verified"]["accuracy"] == 0.625
            and recon["enhanced_model_verified"]["accuracy"] == 0.5833333333333334
            and recon["enhanced_model_verified"]["correct_count"] == 28
            and recon["wfo_bridge_recommendation"] == "MODEL_HANDOFF_ACCEPTED_H14"
        )
        return {
            "gate": "G1-HANDOFF",
            "status": "PASS" if holds else "FAIL",
            "details": recon
        }
    except Exception as e:
        return {
            "gate": "G1-HANDOFF",
            "status": "FAIL",
            "reason": str(e)
        }



def verify_gate_forecast(config_root: Path) -> Dict[str, Any]:
    manifest_path = config_root / "model_manifest.json"
    if not manifest_path.is_file():
        return {"gate": "G1-FORECAST", "status": "FAIL", "reason": f"Missing {manifest_path}"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    params = manifest.get("model_parameters", {})

    holds = (
        manifest.get("model_family") == "LightGBM"
        and manifest.get("recipe_id") == "M4_LGBM_CONSERVATIVE_SLOW"
        and params.get("num_leaves") == 7
        and params.get("max_depth") == 3
        and params.get("learning_rate") == 0.015
        and params.get("n_estimators") == 80
        and params.get("min_child_samples") == 40
        and params.get("colsample_bytree") == 0.65
        and len(manifest.get("feature_schema", [])) == 38
        and manifest.get("imputation_policy", {}).get("strategy") == "TRAIN_MEDIAN_REUSE"
        and manifest.get("temperature_scaling", {}).get("status") == "FROZEN_VALIDATION"
    )
    return {
        "gate": "G1-FORECAST",
        "status": "PASS" if holds else "FAIL",
        "manifest_path": str(manifest_path),
        "holds": holds
    }


def verify_gate_domain() -> Dict[str, Any]:
    checks = []

    # 1. Sizing: 20k -> 2k, 30k -> 3k
    n20 = calculate_intended_notional(20000.0, 0.10)
    n30 = calculate_intended_notional(30000.0, 0.10)
    sizing_holds = (abs(n20 - 2000.0) < 1e-6 and abs(n30 - 3000.0) < 1e-6)
    checks.append({"check": "dynamic_equity_sizing", "holds": sizing_holds})

    # 2. Preroll protection
    clean_state = {"orders_count": 0, "fills_count": 0, "position": 0.0, "fee_drift": 0.0, "cash_drift": 0.0}
    preroll_clean = verify_account_preroll_cleanliness(clean_state)["is_clean"]
    dirty_state = {"orders_count": 1, "fills_count": 0, "position": 0.0, "fee_drift": 0.0, "cash_drift": 0.0}
    preroll_dirty = not verify_account_preroll_cleanliness(dirty_state)["is_clean"]
    checks.append({"check": "preroll_cleanliness_detection", "holds": preroll_clean and preroll_dirty})

    # 3. Next-open contract
    dec_bar = {"close": 50000.0}
    next_bar = {"open": 50100.0, "close": 50500.0}
    exec_res = execute_next_open_order(dec_bar, next_bar, 2000.0)
    next_open_holds = (
        exec_res["fill_price"] == 50100.0
        and not exec_res["same_close_leakage_detected"]
        and not exec_res["next_close_leakage_detected"]
    )
    checks.append({"check": "next_open_contract", "holds": next_open_holds})

    # 4. Typed Sharpe
    zero_res = compute_canonical_sharpe([0.0] * 14)
    var_res = compute_canonical_sharpe([0.001] * 14)
    valid_res = compute_canonical_sharpe([0.001, -0.0005] * 7)
    sharpe_typed_holds = (
        zero_res["status"] == "NO_TRADE_WITH_ZERO_RETURNS"
        and var_res["status"] == "ZERO_VARIANCE"
        and valid_res["status"] == "VALID"
        and valid_res["sharpe"] is not None
    )
    checks.append({"check": "canonical_sharpe_typing", "holds": sharpe_typed_holds})

    # 5. Readiness and admission gates
    blocked = evaluate_proposal_consumption_gate(False, True, "ADMIT", "2025-06-07T00:00:00", "2025-06-07T00:00:00")
    admitted = evaluate_proposal_consumption_gate(True, True, "ADMIT", "2025-06-07T00:00:00", "2025-06-07T00:00:00")
    gate_holds = (not blocked["can_consume"] and admitted["can_consume"])
    checks.append({"check": "proposal_consumption_gate", "holds": gate_holds})

    all_holds = all(c["holds"] for c in checks)
    return {
        "gate": "G1-DOMAIN",
        "status": "PASS" if all_holds else "FAIL",
        "checks": checks
    }


def verify_gate_timeline() -> Dict[str, Any]:
    spec = build_wfo_timeline_spec()
    res = verify_wfo_timeline(spec)
    return {
        "gate": "G1-TIMELINE",
        "status": res["status"],
        "details": res
    }


def verify_gate_budget(config_root: Path) -> Dict[str, Any]:
    budget_path = config_root / "resource_budget.json"
    if not budget_path.is_file():
        return {"gate": "G1-BUDGET", "status": "FAIL", "reason": f"Missing {budget_path}"}
    budget = json.loads(budget_path.read_text(encoding="utf-8"))

    holds = (
        budget.get("trials_per_sampler_cutoff") in (32, 128)
        and budget.get("production_writes_allowed") is False
        and budget.get("max_memory_gib") <= 4.0
    )
    return {
        "gate": "G1-BUDGET",
        "status": "PASS" if holds else "FAIL",
        "holds": holds
    }


def verify_gate_owner(config_root: Path) -> Dict[str, Any]:
    reg_path = config_root / "registration.json"
    status = "PENDING"
    if reg_path.is_file():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        status = reg.get("owner_approval", {}).get("status", "PENDING")

    return {
        "gate": "G1-OWNER",
        "status": status,
        "notes": "Owner approval stays PENDING in self-verification per R28; actual approval recorded by owner."
    }


def verify_vwfo01(lab_root: Path | None = None, study_id: str = "btc_volatility_conditioned_wfo_v1") -> Dict[str, Any]:
    """Runs complete verifier for VWFO-01."""
    if lab_root is None:
        lab_root = Path(__file__).resolve().parents[3]
    config_root = lab_root / "configs" / study_id

    g_handoff = verify_gate_handoff(lab_root)
    g_forecast = verify_gate_forecast(config_root)
    g_domain = verify_gate_domain()
    g_timeline = verify_gate_timeline()
    g_budget = verify_gate_budget(config_root)
    g_owner = verify_gate_owner(config_root)

    technical_pass = (
        g_handoff["status"] == "PASS"
        and g_forecast["status"] == "PASS"
        and g_domain["status"] == "PASS"
        and g_timeline["status"] == "PASS"
        and g_budget["status"] == "PASS"
    )

    return {
        "schema": "regime_lab.vwfo01_verification.v1",
        "phase": "VWFO-01",
        "technical_gate": "PASS" if technical_pass else "FAIL",
        "gates": {
            "G1-HANDOFF": g_handoff["status"],
            "G1-FORECAST": g_forecast["status"],
            "G1-DOMAIN": g_domain["status"],
            "G1-TIMELINE": g_timeline["status"],
            "G1-BUDGET": g_budget["status"],
            "G1-OWNER": g_owner["status"]
        },
        "details": {
            "handoff": g_handoff,
            "forecast": g_forecast,
            "domain": g_domain,
            "timeline": g_timeline,
            "budget": g_budget,
            "owner": g_owner
        }
    }
