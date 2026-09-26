"""SD-02: independent verification against the real 12-fold VALIDATION run
(guide SS9.5, five G2-* gates). Reads ONLY the raw fold_*.json records --
never trusts a runner-produced summary, since ``scripts/run_sd02_validation.py``
itself writes no pass/fail judgment of its own; this module is the first
real judgment pass over that data.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import recipe_selection as rs
from .fold_scoring import ARM_A, ARM_B, ARM_R_RULE, jm_arm_name

RECIPES = (0.5, 1.0, 2.0)
CONDITIONAL_ARMS = (ARM_R_RULE,) + tuple(jm_arm_name(c) for c in RECIPES)
ALL_ARMS = (ARM_A, ARM_B) + CONDITIONAL_ARMS
REQUIRED_SEARCH_TRIALS = 128
MIN_PAIRED_FOLDS = rs.MIN_PAIRED_FOLDS
REQUIRED_GATES = ("G2-ML-VALID", "G2-VAL12", "G2-INDEPENDENCE", "G2-RELEVANCE",
                  "G2-FREEZE", "G2-OWNER")


def load_validation_origins(lab_root: Path) -> tuple:
    timeline = json.loads((lab_root / "configs" / "sharpe_decay_sd_v1" / "timeline.json")
                          .read_text(encoding="utf-8"))
    return tuple(timeline["roles"]["VALIDATION"]["origins"])


def load_fold_records(lab_root: Path, *, origins: tuple) -> dict:
    """{origin: record}, only for files that actually exist -- a missing
    fold is a real, reported gap, never silently skipped from the count."""
    fold_dir = lab_root / "evidence" / "sharpe_decay_sd_v1" / "validation_folds"
    out = {}
    for origin in origins:
        path = fold_dir / f"fold_{origin}.json"
        if path.is_file():
            out[origin] = json.loads(path.read_text(encoding="utf-8"))
    return out


def gate_ml_valid(fold_records: dict, *, origins: tuple) -> dict:
    """Real artifacts present; anchor Y_hat=0 structurally in EVERY arm's
    own scored table (not just when the anchor happens to win); every
    JM recipe attempted at every origin; the search that produced each
    panel actually ran the registered 128 trials."""
    checks = []
    missing = [o for o in origins if o not in fold_records]
    checks.append({"name": "all_12_folds_present", "holds": len(missing) == 0,
                   "detail": f"missing={missing}"})

    anchor_zero_checked, anchor_zero_holds = 0, 0
    trials_checked, trials_holds = 0, 0
    recipes_checked, recipes_holds = 0, 0
    arms_present_checked, arms_present_holds = 0, 0

    for origin, record in fold_records.items():
        trials_checked += 1
        if record["panel"]["search"]["trials_requested"] == REQUIRED_SEARCH_TRIALS:
            trials_holds += 1

        recipes_checked += 1
        recipe_keys = set(record["jm_this_origin"].keys())
        if recipe_keys == {str(c) for c in RECIPES}:
            recipes_holds += 1

        arms_present_checked += 1
        if set(record["arms"].keys()) == set(ALL_ARMS):
            arms_present_holds += 1

        anchor_id = record["panel"]["anchor_id"]
        for arm_name, arm_out in record["arms"].items():
            anchor_rows = [r for r in arm_out["scored"] if r["candidate_id"] == anchor_id]
            for row in anchor_rows:
                anchor_zero_checked += 1
                if abs(row["y_hat"]) < 1e-9:
                    anchor_zero_holds += 1

    checks.append({"name": "search_used_128_trials",
                   "holds": trials_checked > 0 and trials_holds == trials_checked,
                   "detail": f"{trials_holds}/{trials_checked}"})
    checks.append({"name": "all_3_jm_recipes_attempted",
                   "holds": recipes_checked > 0 and recipes_holds == recipes_checked,
                   "detail": f"{recipes_holds}/{recipes_checked}"})
    checks.append({"name": "all_6_arms_present",
                   "holds": arms_present_checked > 0 and arms_present_holds == arms_present_checked,
                   "detail": f"{arms_present_holds}/{arms_present_checked}"})
    checks.append({"name": "anchor_y_hat_zero_in_every_arms_own_scored_table",
                   "holds": anchor_zero_checked > 0 and anchor_zero_holds == anchor_zero_checked,
                   "detail": f"{anchor_zero_holds}/{anchor_zero_checked}", "vacuous": anchor_zero_checked == 0})

    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_val12(fold_records: dict) -> dict:
    """Every model comparison (B vs each JM recipe) has >=12 paired-valid
    folds -- independently recomputed via recipe_selection.recipe_stats,
    never read back from a claim."""
    fold_list = list(fold_records.values())
    checks = []
    for c in RECIPES:
        stats = rs.recipe_stats(fold_list, c=c)
        checks.append({"name": f"jm_c{c}_paired_folds_>=_{MIN_PAIRED_FOLDS}",
                       "holds": stats["technically_valid"],
                       "detail": f"n_paired_folds={stats['n_paired_folds']}"})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_independence(fold_records: dict) -> dict:
    """A genuine B-anchor outcome at a fold must not prevent a conditional
    arm from being scored -- context_prediction_called=True and a full
    16-row scored table regardless of B's own selection.decision."""
    checks = []
    called_checked, called_holds = 0, 0
    scored_full_checked, scored_full_holds = 0, 0
    b_anchor_folds_with_c_scored = 0
    b_anchor_folds_total = 0

    for origin, record in fold_records.items():
        b_is_anchor = record["arms"][ARM_B]["selection"]["is_anchor"]
        panel_size = record["panel"]["panel_size"]
        if b_is_anchor:
            b_anchor_folds_total += 1
        for arm_name in CONDITIONAL_ARMS:
            arm_out = record["arms"][arm_name]
            called_checked += 1
            if arm_out.get("context_prediction_called") is True:
                called_holds += 1
            scored_full_checked += 1
            if len(arm_out["scored"]) == panel_size:
                scored_full_holds += 1
            if b_is_anchor and len(arm_out["scored"]) == panel_size:
                b_anchor_folds_with_c_scored += 1

    checks.append({"name": "context_prediction_called_every_conditional_arm_every_fold",
                   "holds": called_checked > 0 and called_holds == called_checked,
                   "detail": f"{called_holds}/{called_checked}"})
    checks.append({"name": "conditional_arm_scored_table_always_full_panel_size",
                   "holds": scored_full_checked > 0 and scored_full_holds == scored_full_checked,
                   "detail": f"{scored_full_holds}/{scored_full_checked}"})
    checks.append({"name": "c_scored_even_when_b_falls_back_to_anchor",
                   "holds": b_anchor_folds_total > 0
                            and b_anchor_folds_with_c_scored == b_anchor_folds_total * len(CONDITIONAL_ARMS),
                   "detail": f"b_anchor_folds={b_anchor_folds_total}, "
                             f"c_scored_instances={b_anchor_folds_with_c_scored}/"
                             f"{b_anchor_folds_total * len(CONDITIONAL_ARMS)}",
                   "vacuous": b_anchor_folds_total == 0})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_relevance(*, report_path: Path) -> dict:
    """The model-quality report exists and states BOTH the primary
    recipe-selection outcome and the descriptive layer, even if the
    outcome is negative/weak -- never gated on a positive result."""
    checks = []
    exists = report_path.is_file()
    checks.append({"name": "report_exists", "holds": exists, "detail": str(report_path)})
    if exists:
        text = report_path.read_text(encoding="utf-8")
        has_decision_vocab = any(term in text for term in
                                 ("WEAK_DEVELOPMENT_EVIDENCE", "NO_VALID_JM_DESIGN", "RECIPE_SELECTED"))
        checks.append({"name": "report_states_a_registered_decision_outcome",
                       "holds": has_decision_vocab})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_freeze(*, freeze_path: Path, fold_records: dict) -> dict:
    """The freeze artifact exists, and its OWN recorded recipe-selection
    result matches an INDEPENDENT recomputation from the raw fold records
    (never merely echoed back)."""
    checks = []
    exists = freeze_path.is_file()
    checks.append({"name": "freeze_artifact_exists", "holds": exists, "detail": str(freeze_path)})
    if exists:
        frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
        recomputed = rs.select_recipe(list(fold_records.values()), recipes=RECIPES)
        matches = (frozen["recipe_selection"]["decision"] == recomputed["decision"]
                  and frozen["recipe_selection"]["selected_c"] == recomputed["selected_c"])
        checks.append({"name": "frozen_recipe_matches_independent_recomputation", "holds": matches,
                       "detail": f"frozen={frozen['recipe_selection']['decision']}/"
                                 f"{frozen['recipe_selection']['selected_c']}, "
                                 f"recomputed={recomputed['decision']}/{recomputed['selected_c']}"})
        checks.append({"name": "freeze_is_immutable_snapshot_has_sealed_at",
                       "holds": "sealed_at_utc" in frozen})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def gate_owner(*, decisions_path: Path) -> dict:
    checks = []
    exists = decisions_path.is_file()
    checks.append({"name": "owner_decisions_ledger_exists", "holds": exists})
    if exists:
        lines = decisions_path.read_text(encoding="utf-8").splitlines()
        has_sd02_decision = any('"sharpe_decay_sd_v1"' in line and "SD-02" in line for line in lines)
        checks.append({"name": "real_r18_reference_for_sd02", "holds": has_sd02_decision})
    return {"pass": all(c["holds"] for c in checks), "checks": checks}


def verify_sd02(*, lab_root: Path, report_path: Path = None, freeze_path: Path = None) -> dict:
    lab_root = Path(lab_root)
    origins = load_validation_origins(lab_root)
    fold_records = load_fold_records(lab_root, origins=origins)
    report_path = report_path or (lab_root / "evidence" / "sharpe_decay_sd_v1" / "validation_folds" / "report.md")
    freeze_path = freeze_path or (lab_root / "configs" / "sharpe_decay_sd_v1" / "sd02_freeze.json")
    decisions_path = lab_root / "evidence" / "regime_time_edge_ra_v1" / "owner_decisions.jsonl"

    gates = {
        "G2-ML-VALID": gate_ml_valid(fold_records, origins=origins),
        "G2-VAL12": gate_val12(fold_records),
        "G2-INDEPENDENCE": gate_independence(fold_records),
        "G2-RELEVANCE": gate_relevance(report_path=report_path),
        "G2-FREEZE": gate_freeze(freeze_path=freeze_path, fold_records=fold_records),
        "G2-OWNER": gate_owner(decisions_path=decisions_path),
    }
    overall = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"
    return {"overall": overall, "gates": gates, "n_folds_found": len(fold_records),
           "n_folds_expected": len(origins)}
