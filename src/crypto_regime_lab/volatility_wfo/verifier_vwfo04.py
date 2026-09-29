"""Independent Verifier for Phase VWFO-04: Shared Policy, Streaming Replay & Operational Boundaries.

Follows VOL-WFO-V1.0 Section 15:
Validates the 6 Exit Gates:
1. G4-CLOCKS: Clocks, target windows, and not-before timing verified.
2. G4-LIFECYCLE: Proposal lifecycle, idempotency, version matching, expiry verified.
3. G4-PARITY: Scoped stream vs. batch financial parity (equity path tolerance 1e-6).
4. G4-RECOVERY: Recovery from cold restart without state corruption.
5. G4-NO_PRODUCTION_WRITES: Zero production writes / zero live orders sent.
6. G4-OWNER: Owner review status set to PENDING (R28/R18 rule).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple


def verify_vwfo04(evidence_run_dir: Path, lab_root: Path | None = None) -> Dict[str, Any]:
    """Independent verification of Phase VWFO-04 outputs and gates."""
    if lab_root is None:
        lab_root = evidence_run_dir.parents[3]

    configs_dir = lab_root / "configs" / "btc_volatility_conditioned_wfo_v1"
    live_policy_file = configs_dir / "live_policy.json"

    # Evidence files in run directory
    op_manifest_file = evidence_run_dir / "operational_manifest.json"
    timing_receipt_file = evidence_run_dir / "timing_contract_receipt.json"
    lifecycle_receipt_file = evidence_run_dir / "lifecycle_idempotency_receipt.json"
    parity_receipt_file = evidence_run_dir / "parity_receipt.json"
    recovery_receipt_file = evidence_run_dir / "recovery_receipt.json"
    fault_report_file = evidence_run_dir / "fault_injection_report.json"
    report_file = evidence_run_dir / "report.md"

    gates: Dict[str, Dict[str, Any]] = {}

    # Gate 1: G4-CLOCKS
    if not timing_receipt_file.is_file():
        gates["G4-CLOCKS"] = {"status": "FAIL", "reason": "Missing timing_contract_receipt.json in run dir"}
    else:
        timing_data = json.loads(timing_receipt_file.read_text(encoding="utf-8"))
        clocks_pass = (
            timing_data.get("common_ready_lag_days") == 1
            and timing_data.get("update_cadence_days") == 14
            and timing_data.get("proposal_ttl_days") == 2
            and timing_data.get("max_revalidation_age_days") == 28
            and timing_data.get("backdating_rejected") is True
            and timing_data.get("invalid_window_bounds_rejected") is True
        )
        if clocks_pass:
            gates["G4-CLOCKS"] = {
                "status": "PASS",
                "details": {
                    "common_ready_lag_days": timing_data.get("common_ready_lag_days"),
                    "update_cadence_days": timing_data.get("update_cadence_days"),
                    "proposal_ttl_days": timing_data.get("proposal_ttl_days"),
                    "max_revalidation_age_days": timing_data.get("max_revalidation_age_days"),
                    "symmetric_across_arms": timing_data.get("symmetric_across_arms", True),
                },
            }
        else:
            gates["G4-CLOCKS"] = {"status": "FAIL", "reason": f"Timing contract checks failed: {timing_data}"}

    # Gate 2: G4-LIFECYCLE
    if not lifecycle_receipt_file.is_file() or not fault_report_file.is_file():
        gates["G4-LIFECYCLE"] = {"status": "FAIL", "reason": "Missing lifecycle receipt or fault report"}
    else:
        life_data = json.loads(lifecycle_receipt_file.read_text(encoding="utf-8"))
        fault_data = json.loads(fault_report_file.read_text(encoding="utf-8"))

        lifecycle_pass = (
            life_data.get("idempotency_duplicate_ignored") is True
            and life_data.get("version_mismatch_rejected") is True
            and life_data.get("expired_proposal_rejected") is True
            and life_data.get("same_params_refreshes_watermark_preserves_campaign") is True
            and fault_data.get("all_fault_injections_passed") is True
        )
        if lifecycle_pass:
            gates["G4-LIFECYCLE"] = {
                "status": "PASS",
                "details": {
                    "idempotency_duplicate_ignored": True,
                    "version_mismatch_rejected": True,
                    "expired_proposal_rejected": True,
                    "same_params_refresh_verified": True,
                    "fault_tests_passed": fault_data.get("total_fault_cases_passed"),
                },
            }
        else:
            gates["G4-LIFECYCLE"] = {"status": "FAIL", "reason": "Lifecycle or fault injection checks failed"}

    # Gate 3: G4-PARITY
    if not parity_receipt_file.is_file():
        gates["G4-PARITY"] = {"status": "FAIL", "reason": "Missing parity_receipt.json"}
    else:
        parity_data = json.loads(parity_receipt_file.read_text(encoding="utf-8"))
        p_pass = parity_data.get("parity_pass") is True and parity_data.get("max_equity_diff", 1.0) <= 1e-6
        if p_pass:
            gates["G4-PARITY"] = {
                "status": "PASS",
                "details": {
                    "parity_pass": True,
                    "max_equity_diff": parity_data.get("max_equity_diff"),
                    "final_equity_diff": parity_data.get("final_equity_diff"),
                    "stream_orders": parity_data.get("stream_orders"),
                    "batch_orders": parity_data.get("batch_orders"),
                    "stream_fills": parity_data.get("stream_fills"),
                    "batch_fills": parity_data.get("batch_fills"),
                },
            }
        else:
            gates["G4-PARITY"] = {"status": "FAIL", "reason": f"Parity test failed: {parity_data}"}

    # Gate 4: G4-RECOVERY
    if not recovery_receipt_file.is_file():
        gates["G4-RECOVERY"] = {"status": "FAIL", "reason": "Missing recovery_receipt.json"}
    else:
        rec_data = json.loads(recovery_receipt_file.read_text(encoding="utf-8"))
        rec_pass = (
            rec_data.get("cold_recovery_success") is True
            and rec_data.get("state_corruption_detected") is False
            and rec_data.get("recovered_bundle_valid") is True
        )
        if rec_pass:
            gates["G4-RECOVERY"] = {
                "status": "PASS",
                "details": {
                    "cold_recovery_success": True,
                    "state_corruption_detected": False,
                    "recovered_active_version": rec_data.get("recovered_active_version"),
                    "recovered_proposal_ids_count": rec_data.get("recovered_proposal_ids_count"),
                },
            }
        else:
            gates["G4-RECOVERY"] = {"status": "FAIL", "reason": f"Cold recovery verification failed: {rec_data}"}

    # Gate 5: G4-NO_PRODUCTION_WRITES
    if not op_manifest_file.is_file():
        gates["G4-NO_PRODUCTION_WRITES"] = {"status": "FAIL", "reason": "Missing operational_manifest.json"}
    else:
        op_data = json.loads(op_manifest_file.read_text(encoding="utf-8"))
        no_prod = (
            op_data.get("production_orders_authorized") is False
            and op_data.get("live_orders_sent_count") == 0
        )
        # Check quantbt package git status
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd="/root/bobby/pool_alpha/quantbt",
                capture_output=True,
                text=True,
                check=False,
            )
            quantbt_clean = (res.returncode == 0 and res.stdout.strip() == "")
        except Exception:
            quantbt_clean = False

        if no_prod and quantbt_clean:
            gates["G4-NO_PRODUCTION_WRITES"] = {
                "status": "PASS",
                "details": {
                    "production_orders_authorized": False,
                    "live_orders_sent_count": 0,
                    "quantbt_protected_tree_clean": True,
                },
            }
        else:
            gates["G4-NO_PRODUCTION_WRITES"] = {
                "status": "FAIL",
                "reason": f"Production boundaries violated: no_prod={no_prod}, quantbt_clean={quantbt_clean}",
            }

    # Gate 6: G4-OWNER
    gates["G4-OWNER"] = {
        "status": "PENDING",
        "details": {
            "review_status": "WAITING_OWNER_REVIEW",
            "required_for": "Proceeding to Phase VWFO-05 (Locked Final WFO)",
            "rule": "R28: Verifier cannot approve its own phase; owner approval ledger must record decision",
        },
    }

    # Technical gate evaluation: all 5 automated gates must PASS
    auto_gates = ["G4-CLOCKS", "G4-LIFECYCLE", "G4-PARITY", "G4-RECOVERY", "G4-NO_PRODUCTION_WRITES"]
    technical_pass = all(gates[g]["status"] == "PASS" for g in auto_gates)

    return {
        "schema": "regime_lab.vol_wfo_gate_receipt.v1",
        "phase": "VWFO-04",
        "evidence_run_id": evidence_run_dir.name,
        "technical_gate": "PASS" if technical_pass else "FAIL",
        "implementation_status": "COMPLETE",
        "research_status": "OPERATIONAL_BOUNDARIES_QUALIFIED",
        "owner_review": "PENDING",
        "gates": gates,
    }
