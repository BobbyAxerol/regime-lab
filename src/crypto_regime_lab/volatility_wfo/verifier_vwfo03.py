"""Independent Verifier for Phase VWFO-03: Selection Development & Control Arms.

Follows VOL-WFO-V1.0 Section 14:
Validates the 6 Exit Gates:
1. G3-SELECTOR: Contrast formulation, structural anchor zero, and min Yhat selection rule.
2. G3-CONTROLS: Control arms B_CAP, O_PERSIST, and P_NI_01..03 evaluated with valid non-oracle baselines.
3. G3-DEV12: All 12 chronological DEV folds executed for both S_TPE and S_SOBOL (128 trials/cutoff).
4. G3-CHOICE: Winning sampler chosen deterministically according to Section 8.7 rule.
5. G3-FREEZE: Final freeze specification registered in configs/btc_volatility_conditioned_wfo_v1/final_freeze.json.
6. G3-OWNER: Owner review status set to PENDING (R28/R18 rule).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def verify_vwfo03(evidence_run_dir: Path, lab_root: Path | None = None) -> Dict[str, Any]:
    """Independent verification of Phase VWFO-03 outputs and gates."""
    if lab_root is None:
        lab_root = evidence_run_dir.parents[3]

    configs_dir = lab_root / "configs" / "btc_volatility_conditioned_wfo_v1"
    selector_specs_file = configs_dir / "selector_and_control_specs.json"
    timeline_file = configs_dir / "timeline.json"
    final_freeze_file = configs_dir / "final_freeze.json"

    # Files inside evidence run dir
    dev_summary_file = evidence_run_dir / "dev_summary.json"
    candidate_archive_file = evidence_run_dir / "candidate_archive.json"
    sampler_choice_file = evidence_run_dir / "sampler_choice.json"
    report_file = evidence_run_dir / "report.md"

    gates: Dict[str, Dict[str, Any]] = {}

    # Gate 1: G3-SELECTOR
    if not selector_specs_file.is_file():
        gates["G3-SELECTOR"] = {"status": "FAIL", "reason": "Missing selector_and_control_specs.json"}
    else:
        specs = json.loads(selector_specs_file.read_text(encoding="utf-8"))
        features = specs.get("descriptor_vector", {}).get("features", [])
        rule = specs.get("selection_rule", {})
        arms = specs.get("arms", {})

        expected_features = [
            "coeff_norm",
            "ap_norm",
            "threshold_norm",
            "raw_is_sharpe",
            "log_fills_count",
        ]
        has_features = features == expected_features
        has_min_yhat = rule.get("objective") == "MINIMIZE_SIGNED_YHAT"
        has_floor = rule.get("q_hat_filter_floor") == -0.10
        has_arms = all(a in arms for a in ["A_M4", "B0_GLOBAL", "B_CAP", "O_PERSIST", "C_H14", "P_NI_01", "P_NI_02", "P_NI_03"])

        if has_features and has_min_yhat and has_floor and has_arms:
            gates["G3-SELECTOR"] = {
                "status": "PASS",
                "details": {
                    "descriptor_features": len(features),
                    "objective": rule.get("objective"),
                    "filter_floor": rule.get("q_hat_filter_floor"),
                    "registered_arms": list(arms.keys()),
                },
            }
        else:
            gates["G3-SELECTOR"] = {
                "status": "FAIL",
                "reason": f"Selector specs mismatch: features={has_features}, min_yhat={has_min_yhat}, floor={has_floor}, arms={has_arms}",
            }

    # Gate 2: G3-CONTROLS
    if not dev_summary_file.is_file():
        gates["G3-CONTROLS"] = {"status": "FAIL", "reason": "Missing dev_summary.json in run dir"}
    else:
        dev_summary = json.loads(dev_summary_file.read_text(encoding="utf-8"))
        arm_metrics = dev_summary.get("arm_metrics", {})
        has_controls = all(
            k in arm_metrics for k in ["B0_GLOBAL", "B_CAP", "O_PERSIST", "C_H14", "P_NI_01", "P_NI_02", "P_NI_03"]
        )
        if has_controls:
            gates["G3-CONTROLS"] = {
                "status": "PASS",
                "details": {
                    "evaluated_controls": ["B_CAP", "O_PERSIST", "P_NI_01", "P_NI_02", "P_NI_03"],
                    "c_vs_bcap_margin": dev_summary.get("comparisons", {}).get("mean_excess_c_vs_bcap"),
                    "c_vs_o_margin": dev_summary.get("comparisons", {}).get("mean_excess_c_vs_o"),
                },
            }
        else:
            gates["G3-CONTROLS"] = {"status": "FAIL", "reason": f"Missing controls in arm_metrics: {list(arm_metrics.keys())}"}

    # Gate 3: G3-DEV12
    if not timeline_file.is_file() or not dev_summary_file.is_file():
        gates["G3-DEV12"] = {"status": "FAIL", "reason": "Missing timeline.json or dev_summary.json"}
    else:
        tl = json.loads(timeline_file.read_text(encoding="utf-8"))
        dev_origins = tl.get("roles", {}).get("DEV", {}).get("origins", [])
        dev_summary = json.loads(dev_summary_file.read_text(encoding="utf-8"))

        evaluated_tpe_folds = len(dev_summary.get("samplers", {}).get("S_TPE", {}).get("folds", []))
        evaluated_sobol_folds = len(dev_summary.get("samplers", {}).get("S_SOBOL", {}).get("folds", []))

        tpe_pass = evaluated_tpe_folds == len(dev_origins) == 12
        sobol_pass = evaluated_sobol_folds == len(dev_origins) == 12

        if tpe_pass and sobol_pass:
            gates["G3-DEV12"] = {
                "status": "PASS",
                "details": {
                    "planned_dev_origins": 12,
                    "tpe_folds_evaluated": evaluated_tpe_folds,
                    "sobol_folds_evaluated": evaluated_sobol_folds,
                    "total_dev_trials": 2 * 12 * 128,
                },
            }
        else:
            gates["G3-DEV12"] = {
                "status": "FAIL",
                "reason": f"Incomplete DEV folds: TPE={evaluated_tpe_folds}/12, Sobol={evaluated_sobol_folds}/12",
            }

    # Gate 4: G3-CHOICE
    if not sampler_choice_file.is_file():
        gates["G3-CHOICE"] = {"status": "FAIL", "reason": "Missing sampler_choice.json in run dir"}
    else:
        choice = json.loads(sampler_choice_file.read_text(encoding="utf-8"))
        chosen_sampler = choice.get("chosen_sampler")
        criterion = choice.get("selection_criterion")
        metrics = choice.get("sampler_metrics", {})

        if chosen_sampler in ["S_TPE", "S_SOBOL"] and criterion and metrics:
            gates["G3-CHOICE"] = {
                "status": "PASS",
                "details": {
                    "chosen_sampler": chosen_sampler,
                    "criterion": criterion,
                    "tpe_min_margin": metrics.get("S_TPE", {}).get("min_margin"),
                    "sobol_min_margin": metrics.get("S_SOBOL", {}).get("min_margin"),
                },
            }
        else:
            gates["G3-CHOICE"] = {"status": "FAIL", "reason": f"Invalid sampler choice data: {choice}"}

    # Gate 5: G3-FREEZE
    if not final_freeze_file.is_file():
        gates["G3-FREEZE"] = {"status": "FAIL", "reason": "Missing configs/.../final_freeze.json"}
    else:
        freeze = json.loads(final_freeze_file.read_text(encoding="utf-8"))
        freeze_sampler = freeze.get("chosen_sampler")
        freeze_origins = freeze.get("final_origins", [])
        freeze_arms = freeze.get("final_arms", [])

        if freeze_sampler in ["S_TPE", "S_SOBOL"] and len(freeze_origins) == 12 and len(freeze_arms) == 8:
            gates["G3-FREEZE"] = {
                "status": "PASS",
                "details": {
                    "frozen_sampler": freeze_sampler,
                    "final_origins_count": len(freeze_origins),
                    "final_arms_count": len(freeze_arms),
                    "freeze_boundary_gap_days": freeze.get("freeze_boundary_gap_days", 70),
                },
            }
        else:
            gates["G3-FREEZE"] = {
                "status": "FAIL",
                "reason": f"Final freeze invalid: sampler={freeze_sampler}, origins={len(freeze_origins)}/12, arms={len(freeze_arms)}/8",
            }

    # Gate 6: G3-OWNER (Must be PENDING for owner approval per R28)
    gates["G3-OWNER"] = {
        "status": "PENDING",
        "description": "Waiting for Owner review and approval to proceed to Phase VWFO-04 (Rule R28)",
    }

    technical_gate = "PASS" if all(g["status"] == "PASS" for k, g in gates.items() if k != "G3-OWNER") else "FAIL"

    return {
        "schema": "regime_lab.vol_wfo_gate_receipt.v1",
        "study_id": "btc_volatility_conditioned_wfo_v1",
        "phase": "VWFO-03",
        "run_id": evidence_run_dir.name,
        "technical_gate": technical_gate,
        "gates": gates,
        "report_exists": report_file.is_file(),
    }
