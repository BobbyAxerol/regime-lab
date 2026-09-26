"""SD03.1: preflight, no engine calls (guide SD03.1).

Verify SD-01/SD-02 receipts are still valid, the freeze verifier passes,
the FINAL role's 12 origins and resource budget are registered, and
produce a planned-work manifest -- before any real search runs. Guide:
'Khong chay truoc roi sua manifest cho khop sau' (never run first then fix
the manifest to match after).
"""
from __future__ import annotations

import json
from pathlib import Path


class PreflightError(ValueError):
    """A required preflight reference was missing or invalid."""


def verify_prior_receipts(lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    sd01_path = lab_root / "evidence" / "sharpe_decay_sd_v1" / "init_archive" / "gate_receipt.json"
    sd02_path = lab_root / "evidence" / "sharpe_decay_sd_v1" / "validation_folds" / "gate_receipt.json"
    checks = []
    sd01 = sd02 = None
    if sd01_path.is_file():
        sd01 = json.loads(sd01_path.read_text(encoding="utf-8"))
        checks.append({"name": "sd01_gate_pass", "holds": sd01.get("technical_gate") == "PASS"})
    else:
        checks.append({"name": "sd01_gate_receipt_exists", "holds": False})
    if sd02_path.is_file():
        sd02 = json.loads(sd02_path.read_text(encoding="utf-8"))
        checks.append({"name": "sd02_gate_pass", "holds": sd02.get("technical_gate") == "PASS"})
    else:
        checks.append({"name": "sd02_gate_receipt_exists", "holds": False})
    return {"pass": all(c["holds"] for c in checks), "checks": checks, "sd01": sd01, "sd02": sd02}


def verify_freeze(lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    freeze_path = lab_root / "configs" / "sharpe_decay_sd_v1" / "sd02_freeze.json"
    checks = []
    freeze = None
    if freeze_path.is_file():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        checks.append({"name": "freeze_sealed", "holds": "sealed_at_utc" in freeze})
        checks.append({"name": "recipe_decision_registered",
                       "holds": freeze.get("recipe_selection", {}).get("decision") is not None})
        checks.append({"name": "selected_c_present",
                       "holds": freeze.get("recipe_selection", {}).get("selected_c") is not None})
    else:
        checks.append({"name": "freeze_artifact_exists", "holds": False})
    return {"pass": all(c["holds"] for c in checks), "checks": checks, "freeze": freeze}


def verify_timeline(lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    timeline_path = lab_root / "configs" / "sharpe_decay_sd_v1" / "timeline.json"
    checks = []
    final_origins = []
    if timeline_path.is_file():
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        final_origins = timeline["roles"]["FINAL"]["origins"]
        checks.append({"name": "final_role_has_12_origins", "holds": len(final_origins) == 12})
        checks.append({"name": "final_role_frozen_before_outcome",
                       "holds": timeline.get("frozen_before_any_outcome") is True})
    else:
        checks.append({"name": "timeline_exists", "holds": False})
    return {"pass": all(c["holds"] for c in checks), "checks": checks, "final_origins": final_origins}


def verify_resource_budget(lab_root: Path) -> dict:
    from ..safety.paths import SandboxPolicy

    policy = SandboxPolicy.discover(Path(lab_root))
    budget = policy.raw.get("resource_budget", {})
    checks = [
        {"name": "working_memory_gib_registered", "holds": budget.get("working_memory_gib") is not None},
        {"name": "workers_registered", "holds": budget.get("workers") is not None},
    ]
    return {"pass": all(c["holds"] for c in checks), "checks": checks, "budget": budget}


def planned_work_manifest(*, final_origins: list) -> dict:
    """No engine calls -- just states what SD-03 WILL do, before it runs."""
    return {
        "schema": "regime_lab.sd03_planned_work.v1",
        "final_archive": {"n_origins": len(final_origins), "origins": list(final_origins),
                          "arms": ["A_M4", "B_SD_GLOBAL", "JM_C2.0"],
                          "search_trials_per_origin": 128},
        "d2_continuations": {"n_origins": len(final_origins), "h1_days": 56, "h2_days": 56,
                             "candidates_per_origin": 3},
        "continuous_accounts": {"arms": ["A_M4", "B_SD_GLOBAL", "JM_C2.0"],
                                "route": "fp.evaluator.run_deployment"},
        "statistics": {"primary_block_length": 4, "sensitivity_block_lengths": [2, 3],
                       "resamples": 5000},
    }


def preflight(lab_root: Path) -> dict:
    r_receipts = verify_prior_receipts(lab_root)
    r_freeze = verify_freeze(lab_root)
    r_timeline = verify_timeline(lab_root)
    r_budget = verify_resource_budget(lab_root)
    overall = all(r["pass"] for r in (r_receipts, r_freeze, r_timeline, r_budget))
    manifest = planned_work_manifest(final_origins=r_timeline["final_origins"]) if overall else None
    return {"overall": "READY" if overall else "BLOCKED",
           "prior_receipts": r_receipts, "freeze": r_freeze, "timeline": r_timeline,
           "resource_budget": r_budget, "planned_work_manifest": manifest}
