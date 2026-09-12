#!/usr/bin/env python
"""LAB-08 audit, driven by the checklist written BEFORE the code.

`configs/lab08_checklist.json` was committed before `experiments/factorial.py`,
`controls.py` and `regime_schedule.py` existed, so this cannot become a list of
what happened to get built.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
T = "tests/test_lab08_factorial.py::"
P = "lab08_pilot_protocol.json"
F = "lab08_factorial_full.json"
D = "lab08_discovery.json"
A = "lab08_data_ablation.json"

EVIDENCE: dict[str, tuple[str, str]] = {
    # L08.1 freeze
    "L08.1.1": (f"{P}:timeframes", "from the LAB-01 registration, not chosen here"),
    "L08.1.2": (f"{P}:evaluation_interval", "daily UTC on the continuous account"),
    "L08.1.3": (f"{P}:data_roles + primary_matrix.cells", ""),
    "L08.1.4": (f"{P}:seeds", "probe design, model multi-start and placebo"),
    "L08.1.5": (f"{P}:compute_budget", "points at the registration made before LAB-07"),
    "L08.1.6": (f"{P}:controls.USER_PRESET_REFERENCE + preset_role", "retrospective only"),
    "L08.1.7": (f"{P}:contamination", "the outer window is declared NOT an untouched holdout"),
    "L08.1.8": (f"{T}test_the_protocol_was_frozen_before_any_arm_ran",
                "the freeze script refuses to overwrite; the test compares timestamps"),
    # L08.2 factorial
    "L08.2.1": (f"{F}:cells[].arms — every arm runs through run_continuous_account", ""),
    "L08.2.2": (f"{P}:economics.identical_across_arms + evaluator.ACCOUNT", ""),
    "L08.2.3": (f"{F}:cells[].notes.compute_match", "same cutoff count and training memory"),
    "L08.2.4": ("experiments/calendar_baseline.py retention rule, shared by both selectors", ""),
    "L08.2.5": ("lab07_continuous_trace.json:training_jobs.benchmark.source",
                "measured latency, never zero (carried from LAB-07)"),
    "L08.2.6": ("lab08_factorial_pilot.json:is_a_result=false",
                "the pilot found two defects: a state tape covering a sixth of the window, and "
                "dynamic training windows a fifth the size of the calendar's"),
    "L08.2.7": (f"{F}:cells_planned=20 with NOT_READY rows carrying null metrics", ""),
    "L08.2.8": (f"{T}test_an_unrunnable_arm_reports_null_not_zero", ""),
    "L08.2.9": (f"{F}:cells[].arms[].status", "INSUFFICIENT/NOT_READY reported, never a zero"),
    "L08.2.10": (f"{D}:contrast_panel", "B-A, C-A, D-B, D-C and the interaction"),
    # L08.3 arm E and controls
    "L08.3.1": (f"{D}:contrast_panel['D-B'] + cells[].arms.E.policy_note", ""),
    "L08.3.2": (f"{F}:cells[].controls.BANK_CALENDAR", "reported degenerate, not dropped"),
    "L08.3.3": (f"{F}:cells[].controls.CALENDAR_MATCHED",
                "satisfied by construction: the dynamic arms were given the calendar's budget"),
    "L08.3.4": (f"{F}:cells[].controls.RISK_ONLY", "arm A's own selections, resized only"),
    "L08.3.5": (f"{T}test_the_placebo_matches_the_real_dwell_rather_than_switching_freely", ""),
    "L08.3.6": (f"{T}test_the_placebo_is_built_from_rates_not_from_a_future_sequence", ""),
    "L08.3.7": (f"{T}test_the_delay_control_moves_availability_not_the_world", ""),
    "L08.3.8": (f"{T}test_the_hindsight_control_is_never_tradeable", ""),
    "L08.3.9": (f"{F}:cells[].controls.USER_PRESET_REFERENCE.eligible_as_a_core_outcome=false", ""),
    "L08.3.10": ("experiments/controls.py:control_registry().retention_rule "
                 f"+ {T}test_all_seven_mandatory_controls_are_declared", ""),
    "L08.3.11": ("controls.control_registry().staging_rule", "no Cartesian product"),
    # L08.4 data ablation
    "L08.4.1": (f"{A}:per_symbol[].scores", "core vs derivatives vs liquidity"),
    "L08.4.2": (f"{A}:per_symbol[].comparable_interval",
                "every cohort scored on the SAME rows; the mislabelled liquidity cohort that "
                "scored an impact proxy as the order book was split apart"),
    "L08.4.3": ("compute_budget_registration.json:ledger_opened_with", ""),
    "L08.4.4": (f"{A}:comparable_interval_rule", ""),
    # L08.5 ladder
    "L08.5.1": (f"{A}:complexity_ladder + ladder_declared_unbuilt", "M1S and M2 declared unbuilt"),
    "L08.5.2": (f"{A}:tuning_stage", "development only"),
    "L08.5.3": (f"{A}:ladder_rule", "no default sweep"),
    "L08.5.4": (f"{A}:complexity_ladder[].question/expected_failure/stop_condition", ""),
    # L08.6 compute
    "L08.6.1": (f"{D}:compute.unique_strategy_executions_in_dynamic_refreshes", ""),
    "L08.6.2": (f"{F}:cells[].bars", "candidate episode bars per cell"),
    "L08.6.3": ("lab08_*_regime_model_registry.json:models", "40 fits per symbol"),
    "L08.6.4": ("lab06_response_model.json:response_count", "carried from LAB-06"),
    "L08.6.5": (f"{D}:compute.wall_seconds_per_cell", "min, median and max"),
    "L08.6.6": ("lab07_continuous_trace.json:continuous_account.switches[].blocked_bars",
                "activation delay, measured in LAB-07"),
    "L08.6.7": (f"{D}:compute.budget_exceeded=false", "one worker, within the registered budget"),
    # L08.7 selection
    "L08.7.1": (f"{D}:design_selection.outcome", "DESIGN_FROZEN or NO_PROMISING_DESIGN"),
    "L08.7.2": (f"{D}:design_selection.decision_rule + evidence_stage", "development only"),
    "L08.7.3": (f"{D}:design_selection.tradeoffs", ""),
    "L08.7.4": (f"{D}:design_selection.failure_cases", ""),
    "L08.7.5": (f"{D}:design_selection.uncertainty", ""),
    "L08.7.6": (f"{D}:design_selection.evidence_stage",
                "the outer window was not consulted at any point"),
    "L08.7.7": (f"{D}:design_selection.alpha_versions_frozen", ""),
    "L08.7.8": (f"{D}:design_selection.optional_alpha_improvements_folded_in=false", ""),
    # guide 11 / 10.3
    "G11.1.1": (f"{P}:stage=discovery + outer_window_is_not_consumed", ""),
    "G11.2.1": (f"{D}:design_selection.registered_endpoint", ""),
    "G11.2.2": (f"{D}:design_selection.conclusion_vocabulary", ""),
    "G11.2.3": (f"{F}:cells[].controls.RISK_ONLY", "exposure is isolated from selection"),
    "G10.3.6": (f"{P}:economics + account_rule", ""),
    "G10.3.7": (f"{F}:cells[].arms[].account_resets=0", ""),
    "G10.3.8": ("operational_segments.json:daily_account_comparison",
                "the daily account is primary; per-segment Sharpes are diagnostic (T55)"),
    # acceptance
    "T53.2": (f"{P}:economics.identical_across_arms + {F}:cells[].notes.compute_match", ""),
    "T58.1": (f"{F}:cells[].controls.RISK_ONLY and .CALENDAR_MATCHED", ""),
    "T59.1": (f"{T}test_an_unrunnable_arm_reports_null_not_zero "
              "+ lab04_calendar_baseline.json:search_effort.structurally_invalid", ""),
    "T60.1": ("experiments/factorial.py:ArmResult.as_record recomputes every metric from the "
              "equity path", "no metric is carried over from another artifact"),
    # outputs
    "OUT.1": (f"{F} + evidence/**/attempts.jsonl", ""),
    "OUT.2": (f"{D}:contrast_panel", ""),
    "OUT.3": (f"{F}:cells[].notes.regime_cutoff_evidence[].cutoff_evidence.robust_scores",
              "the local-neighbourhood panel behind every dynamic selection"),
    "OUT.4": ("lab08_*_regime_model_registry.json:models[].feature_weights/centroids", ""),
    "OUT.5": ("reports/lab08_report.md", ""),
    "OUT.6": (f"{D}:design_selection", ""),
    "OUT.7": (f"{D}:all_attempted_hypotheses", ""),
    # exit
    "EXIT.1": (f"{D}:design_selection.outcome", ""),
    "EXIT.2": (f"{D}:design_selection.not_required_to_be_profitable", ""),
    "EXIT.3": (f"{D}:design_selection.not_required_to_be_profitable",
               "a negative result is not a technical failure"),
    "EXIT.4": ("correction_ledger.json", "every re-run is recorded with what it superseded"),
}

ARTIFACTS = (P, F, D, A, "lab08_checklist.json")


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    checklist = json.loads((LAB_ROOT / "configs" / "lab08_checklist.json").read_text())
    tasks = []
    for clause_id, requirement in checklist["clauses"]:
        evidence, note = EVIDENCE.get(clause_id, ("", ""))
        tasks.append({"clause_id": clause_id, "requirement": requirement,
                      "evidence": evidence, "note": note,
                      "status": "DONE" if evidence else "MISSING"})

    missing = [a for a in ARTIFACTS if not (LAB_ROOT / "configs" / a).is_file()]
    proc = subprocess.run(
        [str(LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"), "-m", "pytest",
         str(LAB_ROOT / "tests" / "test_lab08_factorial.py"), "-q"],
        capture_output=True, text=True, cwd=str(LAB_ROOT))
    summary = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]

    document = {
        "schema": "crypto_regime_lab.lab08_task_audit.v1",
        "guide_section": "LAB-08",
        "checklist_written_before_code": checklist["written_before_code"],
        "checklist_source": "configs/lab08_checklist.json",
        "tasks_total": len(tasks),
        "tasks_done": sum(1 for t in tasks if t["status"] == "DONE"),
        "tasks_blocked": sum(1 for t in tasks if t["status"] != "DONE"),
        "clauses_without_an_evidence_pointer": [t["clause_id"] for t in tasks
                                                if t["status"] != "DONE"],
        "artifacts_present": [a for a in ARTIFACTS if a not in missing],
        "artifacts_missing": missing,
        "acceptance_tests": summary[-1] if summary else "not run",
        "acceptance_tests_passed": proc.returncode == 0,
        "acceptance_ids_covered": ["T53", "T58", "T59", "T60"],
        "tasks": tasks,
    }
    with writer.attempt("L08.audit") as att:
        att.detail = {"done": document["tasks_done"], "total": document["tasks_total"]}
    writer.write_config("lab08_task_audit.json", document)
    writer.write_json("lab08_task_audit.json", document, schema=document["schema"])

    print(f"LAB-08 audit: {document['tasks_done']}/{document['tasks_total']} DONE")
    print(f"clauses with no evidence pointer: "
          f"{document['clauses_without_an_evidence_pointer'] or 'none'}")
    print(f"artifacts missing: {missing or 'none'}")
    print(f"acceptance tests : {document['acceptance_tests']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if document["tasks_blocked"] == 0 and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
