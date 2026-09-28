"""Verifier for Phase MF-05: Consolidated Report & WFO Bridge Determination.

Enforces:
1. G5-REPORT: Consolidated scientific report completed with 0 financial engine calls.
2. G5-REPRODUCE: Metrics 100% reproducible from sealed artifacts without model inference.
3. G5-SCOPE: Scientific scope properly bounded (VOLATILITY_FORECAST_QUALIFIED_ONLY__WFO_BRIDGE_CLOSED).
4. G5-BRIDGE: WFO Bridge officially marked CLOSED per Section 18; proposal documented.
5. G5-DURATION-HANDOFF: Empirical duration survival ledger and timing protocol handed off.
6. G5-OWNER: Complete handoff package prepared for Owner review and decision.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def verify_gate_report(report_data: Dict[str, Any]) -> Dict[str, Any]:
    assert report_data.get("study_id") == "btc_regime_forecast_v1", "Invalid study_id"
    assert report_data.get("phases_completed") == ["MF-01", "MF-02", "MF-03", "MF-04", "MF-05"], (
        "Not all 5 phases completed"
    )
    assert report_data.get("financial_engine_calls", -1) == 0, "Financial engine calls must be 0"

    return {
        "status": "PASS",
        "phases": report_data.get("phases_completed"),
        "financial_engine_calls": 0,
    }


def verify_gate_reproduce(reproduce_data: Dict[str, Any]) -> Dict[str, Any]:
    assert reproduce_data.get("reproduction_status") == "VERIFIED", "Metrics reproduction failed"
    assert reproduce_data.get("max_metric_discrepancy", 1.0) < 1e-9, "Metrics reproduction discrepancy > 1e-9"
    assert reproduce_data.get("recomputation_without_models") is True, (
        "Must be recomputed from sealed data without invoking model or engine"
    )

    return {
        "status": "PASS",
        "reproduction": "VERIFIED",
        "max_discrepancy": reproduce_data.get("max_metric_discrepancy"),
    }


def verify_gate_scope(scope_data: Dict[str, Any]) -> Dict[str, Any]:
    valid_claims = [
        "TECHNICALLY_VALID__VOLATILITY_QUALIFIED_ONLY__WFO_BRIDGE_CLOSED",
        "TECHNICALLY_VALID__ALL_HEADS_NOT_QUALIFIED__WFO_BRIDGE_CLOSED",
    ]
    claim = scope_data.get("study_claim_level")
    assert claim in valid_claims, f"Unexpected claim level: {claim}"
    vol_status = scope_data.get("volatility_head_status")
    assert vol_status in ("QUALIFIED", "NOT_QUALIFIED"), f"Invalid volatility_head_status: {vol_status}"
    assert scope_data.get("joint_regime_head_status") == "NOT_QUALIFIED", "Joint head must be NOT_QUALIFIED"

    return {
        "status": "PASS",
        "claim_level": claim,
        "volatility_status": vol_status,
        "joint_status": "NOT_QUALIFIED",
    }


def verify_gate_bridge(bridge_data: Dict[str, Any]) -> Dict[str, Any]:
    status = bridge_data.get("wfo_bridge_status")
    assert status == "CLOSED", f"WFO Bridge must be CLOSED, found: {status}"
    assert bridge_data.get("joint_regime_parameter_selection_permitted") is False, (
        "Parameter selection with un-qualified joint regime cannot be permitted"
    )
    assert "volatility_conditioned_proposal" in bridge_data, "Missing volatility proposal"

    return {
        "status": "PASS",
        "wfo_bridge_status": "CLOSED",
        "joint_selection_permitted": False,
        "proposal_status": "SPECIFIED_NOT_EXECUTED",
    }


def verify_gate_duration_handoff(duration_handoff: Dict[str, Any]) -> Dict[str, Any]:
    assert duration_handoff.get("empirical_dwell_mean_days") is not None, "Missing mean dwell"
    assert duration_handoff.get("survival_curves_available") is True, "Missing survival curves"
    assert duration_handoff.get("misrepresented_as_ml_skill") is False, (
        "Duration cannot be misrepresented as ML skill"
    )

    return {
        "status": "PASS",
        "mean_dwell": duration_handoff.get("empirical_dwell_mean_days"),
        "empirical_survival_handed_off": True,
    }


def verify_gate_owner(owner_data: Dict[str, Any]) -> Dict[str, Any]:
    assert owner_data.get("model_qualification_manifest_exists") is True, "Missing qualification manifest"
    assert owner_data.get("version_manifest_exists") is True, "Missing version manifest"
    assert owner_data.get("exclusion_list_exists") is True, "Missing exclusion list"
    assert owner_data.get("resource_summary_exists") is True, "Missing resource summary"

    return {
        "status": "PASS",
        "package_complete": True,
        "ready_for_owner_review": True,
    }


def run_mf05_verification(run_dir: Path, write_receipt: bool = True) -> Dict[str, Any]:
    """Run all 6 exit gates for MF-05."""
    report_meta_path = run_dir / "report_meta.json"
    reproduce_path = run_dir / "reproduce_audit.json"
    scope_path = run_dir / "study_scope.json"
    bridge_path = run_dir / "wfo_bridge_decision.json"
    duration_path = run_dir / "duration_handoff.json"
    owner_path = run_dir / "owner_handoff_summary.json"

    with open(report_meta_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)
    with open(reproduce_path, "r", encoding="utf-8") as f:
        reproduce_data = json.load(f)
    with open(scope_path, "r", encoding="utf-8") as f:
        scope_data = json.load(f)
    with open(bridge_path, "r", encoding="utf-8") as f:
        bridge_data = json.load(f)
    with open(duration_path, "r", encoding="utf-8") as f:
        duration_handoff = json.load(f)
    with open(owner_path, "r", encoding="utf-8") as f:
        owner_data = json.load(f)

    g5_report = verify_gate_report(report_data)
    g5_reproduce = verify_gate_reproduce(reproduce_data)
    g5_scope = verify_gate_scope(scope_data)
    g5_bridge = verify_gate_bridge(bridge_data)
    g5_duration = verify_gate_duration_handoff(duration_handoff)
    g5_owner = verify_gate_owner(owner_data)

    all_passed = (
        g5_report["status"] == "PASS"
        and g5_reproduce["status"] == "PASS"
        and g5_scope["status"] == "PASS"
        and g5_bridge["status"] == "PASS"
        and g5_duration["status"] == "PASS"
        and g5_owner["status"] == "PASS"
    )

    receipt = {
        "phase": "MF-05",
        "overall_status": "PASS" if all_passed else "FAIL",
        "gates": {
            "G5-REPORT": g5_report,
            "G5-REPRODUCE": g5_reproduce,
            "G5-SCOPE": g5_scope,
            "G5-BRIDGE": g5_bridge,
            "G5-DURATION-HANDOFF": g5_duration,
            "G5-OWNER": g5_owner,
        },
    }

    if write_receipt:
        receipt_path = run_dir / "gate_receipt.json"
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)

    return receipt
