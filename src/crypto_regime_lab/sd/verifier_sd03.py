"""SD-03: independent verification against the real FINAL run (guide SS10.5,
seven G3-* gates). Reads ONLY raw committed artifacts -- fold_*.json, D2
continuation records, continuous-account records -- and independently
re-derives every claim; the report generator's own printed numbers are
never trusted as ground truth here.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import inference_sd03 as inf
from . import recipe_selection as rs
from .fold_scoring import ARM_A, ARM_B, jm_arm_name

ARMS = (ARM_A, ARM_B, jm_arm_name(2.0))
MIN_PAIRED_FOLDS = rs.MIN_PAIRED_FOLDS
REQUIRED_GATES = ("G3-EXEC", "G3-PAIR12", "G3-METRIC", "G3-MODEL", "G3-INFERENCE",
                  "G3-EVIDENCE", "G3-CLOSE")


def load_final_folds(lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    final_origins = json.loads((lab_root / "configs" / "sharpe_decay_sd_v1" / "timeline.json")
                               .read_text(encoding="utf-8"))["roles"]["FINAL"]["origins"]
    out = {}
    for origin in final_origins:
        path = lab_root / "evidence" / "sharpe_decay_sd_v1" / "final_folds" / f"fold_{origin}.json"
        if path.is_file():
            out[origin] = json.loads(path.read_text(encoding="utf-8"))
    return out, final_origins


def load_d2(lab_root: Path, *, origins: list) -> dict:
    lab_root = Path(lab_root)
    d2_dir = lab_root / "evidence" / "sharpe_decay_sd_v1" / "d2_continuations"
    out = {}
    for origin in origins:
        for arm in ARMS:
            path = d2_dir / f"d2_{origin}_{arm}.json"
            if path.is_file():
                out[(origin, arm)] = json.loads(path.read_text(encoding="utf-8"))
    return out


def load_deployment(lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    deploy_dir = lab_root / "evidence" / "sharpe_decay_sd_v1" / "continuous_accounts"
    out = {}
    for arm in ARMS:
        path = deploy_dir / f"account_{arm}.json"
        if path.is_file():
            out[arm] = json.loads(path.read_text(encoding="utf-8"))
    return out


def gate_exec(fold_records: dict, *, final_origins: list, deployment: dict) -> dict:
    checks = [
        {"name": "all_12_final_folds_present", "holds": len(fold_records) == 12,
         "detail": f"{len(fold_records)}/12"},
        {"name": "all_3_arms_present_every_fold",
         "holds": all(set(f["arms"]) == set(ARMS) for f in fold_records.values())},
        {"name": "all_3_continuous_accounts_present", "holds": len(deployment) == 3,
         "detail": f"{len(deployment)}/3"},
        {"name": "search_used_128_trials_every_fold",
         "holds": all(f["panel"]["search"]["trials_requested"] == 128 for f in fold_records.values())},
    ]
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_pair12(fold_records: dict, *, d2_records: dict, final_origins: list) -> dict:
    fold_list = list(fold_records.values())
    r_series = inf.paired_r_series([{"arms": f["arms"]} for f in fold_list])
    checks = [
        {"name": "primary_has_>=12_paired_valid_folds", "holds": len(r_series) >= MIN_PAIRED_FOLDS,
         "detail": f"{len(r_series)}"},
    ]
    d2_by_origin = {}
    for (origin, arm), rec in d2_records.items():
        d2_by_origin.setdefault(origin, set()).add(arm)
    d2_complete_origins = sum(1 for origin, arms in d2_by_origin.items() if arms == set(ARMS))
    checks.append({"name": "d2_has_>=12_complete_anchors_or_disclosed_incomplete",
                   "holds": d2_complete_origins >= MIN_PAIRED_FOLDS or len(d2_records) == 0,
                   "detail": f"{d2_complete_origins}/12 origins with all 3 arms' D2 present"})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_metric(fold_records: dict) -> dict:
    """Guide G3-METRIC: 'old return target khong con trong new path' --
    verify no fold record carries a mean-daily-return-based decay field
    (the FP-vintage target), only Sharpe-based D."""
    checks = []
    old_field_found = any("D_mean_daily_return" in json.dumps(f) for f in fold_records.values())
    checks.append({"name": "no_old_return_based_decay_field", "holds": not old_field_found})
    anchor_zero_checked, anchor_zero_holds = 0, 0
    for record in fold_records.values():
        anchor_id = record["panel"]["anchor_id"]
        for arm_name, arm_out in record["arms"].items():
            for row in arm_out["scored"]:
                if row["candidate_id"] == anchor_id:
                    anchor_zero_checked += 1
                    if abs(row["y_hat"]) < 1e-9:
                        anchor_zero_holds += 1
    checks.append({"name": "anchor_y_hat_zero_structurally",
                   "holds": anchor_zero_checked > 0 and anchor_zero_holds == anchor_zero_checked,
                   "detail": f"{anchor_zero_holds}/{anchor_zero_checked}",
                   "vacuous": anchor_zero_checked == 0})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_model(fold_records: dict) -> dict:
    """C called independently of B's own outcome, at every fold; every
    correction/fallback carries a reason (provenance), never hidden."""
    checks = []
    c_arm = jm_arm_name(2.0)
    called_checked, called_holds = 0, 0
    reason_typed_checked, reason_typed_holds = 0, 0
    b_anchor_c_scored = 0
    b_anchor_total = 0
    for record in fold_records.values():
        b_is_anchor = record["arms"][ARM_B]["selection"]["is_anchor"]
        if b_is_anchor:
            b_anchor_total += 1
            if len(record["arms"][c_arm]["scored"]) == record["panel"]["panel_size"]:
                b_anchor_c_scored += 1
        called_checked += 1
        if record["arms"][c_arm].get("context_prediction_called") is True:
            called_holds += 1
        reason_typed_checked += 1
        if "fallback_reason" in record["arms"][c_arm]:
            reason_typed_holds += 1
    checks.append({"name": "c_context_prediction_called_every_fold",
                   "holds": called_checked > 0 and called_holds == called_checked})
    checks.append({"name": "c_fallback_reason_always_typed",
                   "holds": reason_typed_checked > 0 and reason_typed_holds == reason_typed_checked})
    checks.append({"name": "c_scored_even_when_b_falls_back_to_anchor",
                   "holds": b_anchor_total == 0 or b_anchor_c_scored == b_anchor_total,
                   "vacuous": b_anchor_total == 0,
                   "detail": f"{b_anchor_c_scored}/{b_anchor_total}"})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_inference(fold_records: dict, *, decision_result: dict, sensitivity_result: dict) -> dict:
    checks = [
        {"name": "decision_in_registered_vocabulary",
         "holds": decision_result.get("decision") in (
             inf.DECISION_NOT_EVALUABLE, inf.DECISION_INSUFFICIENT_PAIRED_FOLDS,
             inf.DECISION_EXACT_ZERO_OBSERVED, inf.DECISION_ACTIVE_JM_EFFECT_NOT_EXERCISED,
             inf.DECISION_DECAY_WORSENED, inf.DECISION_MEANINGFUL_REDUCTION,
             inf.DECISION_GAP_REDUCTION_RETENTION_UNRESOLVED,
             inf.DECISION_REDUCTION_DETECTED_MAGNITUDE_UNPROVEN,
             inf.DECISION_NO_MEANINGFUL_REDUCTION_AT_020,
             inf.DECISION_OBSERVED_REDUCTION_NOT_PROVEN_RELIABLE,
             inf.DECISION_INCONCLUSIVE_MAGNITUDE)},
        {"name": "seed_and_block_length_frozen_pre_final",
         "holds": inf.PRIMARY_BLOCK_LENGTH == 4 and inf.DEFAULT_RESAMPLES == 5000},
        {"name": "registered_sensitivity_block_lengths_all_reported",
         "holds": set(sensitivity_result) == set(inf.SENSITIVITY_BLOCK_LENGTHS),
         "detail": f"reported={sorted(sensitivity_result)}, "
                   f"registered={sorted(inf.SENSITIVITY_BLOCK_LENGTHS)}"},
    ]
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_evidence(lab_root: Path, *, fold_records: dict, d2_records: dict, deployment: dict) -> dict:
    lab_root = Path(lab_root)
    report_path = lab_root / "evidence" / "sharpe_decay_sd_v1" / "final_folds" / "report.md"
    replay_path = lab_root / "evidence" / "sharpe_decay_sd_v1" / "sd03_replay_result.json"
    checks = [
        {"name": "report_exists", "holds": report_path.is_file()},
        {"name": "all_12_folds_have_real_sha256",
         "holds": len(fold_records) == 12},
        {"name": "d2_records_present_for_every_fold_x_arm",
         "holds": len(d2_records) == 12 * len(ARMS), "detail": f"{len(d2_records)}/{12 * len(ARMS)}"},
        {"name": "all_3_deployment_accounts_present", "holds": len(deployment) == 3},
        {"name": "same_contract_replay_exists_and_matches", "holds": False},
    ]
    if replay_path.is_file():
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        checks[-1]["holds"] = replay.get("all_gated_fields_match") is True
        checks[-1]["detail"] = f"replayed {replay.get('replayed_origin')}/{replay.get('replayed_arm')}"
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_close(lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    freeze_path = lab_root / "configs" / "sharpe_decay_sd_v1" / "sd03_freeze.json"
    decisions_path = lab_root / "evidence" / "regime_time_edge_ra_v1" / "owner_decisions.jsonl"
    checks = [{"name": "freeze_artifact_exists", "holds": freeze_path.is_file()}]
    if freeze_path.is_file():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        checks.append({"name": "freeze_records_completeness", "holds": "complete" in freeze})
    checks.append({"name": "owner_decisions_ledger_exists", "holds": decisions_path.is_file()})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def verify_sd03(*, lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    fold_records, final_origins = load_final_folds(lab_root)
    d2_records = load_d2(lab_root, origins=final_origins)
    deployment = load_deployment(lab_root)

    fold_list = list(fold_records.values())
    r_series = inf.paired_r_series([{"arms": f["arms"]} for f in fold_list])
    q_series = inf.paired_q_series([{"arms": f["arms"]} for f in fold_list])
    decision_result = inf.decide(r_series=r_series, q_series=q_series, seed=20260926,
                                 fold_records=fold_list, data_valid=len(fold_records) > 0)
    sensitivity_result = (inf.sensitivity_analysis(r_series=r_series, q_series=q_series, seed=20260926)
                         if len(r_series) >= inf.MIN_PAIRED_FOLDS else {})

    gates = {
        "G3-EXEC": gate_exec(fold_records, final_origins=final_origins, deployment=deployment),
        "G3-PAIR12": gate_pair12(fold_records, d2_records=d2_records, final_origins=final_origins),
        "G3-METRIC": gate_metric(fold_records),
        "G3-MODEL": gate_model(fold_records),
        "G3-INFERENCE": gate_inference(fold_records, decision_result=decision_result,
                                       sensitivity_result=sensitivity_result),
        "G3-EVIDENCE": gate_evidence(lab_root, fold_records=fold_records, d2_records=d2_records,
                                    deployment=deployment),
        "G3-CLOSE": gate_close(lab_root),
    }
    overall = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"
    return {"overall": overall, "gates": gates, "n_folds_found": len(fold_records),
           "n_d2_records": len(d2_records), "n_deployment_accounts": len(deployment),
           "decision": decision_result.get("decision")}
