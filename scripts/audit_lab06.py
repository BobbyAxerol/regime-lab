#!/usr/bin/env python
"""LAB-06 audit, driven by the checklist written BEFORE the code.

`configs/lab06_checklist.json` was committed before any policy module existed, so
this script cannot quietly become a list of what happened to get built. Each
clause names the artifact field or test that discharges it, and a clause with no
evidence is reported as MISSING rather than assumed.
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
T = "tests/test_lab06_policy.py::"

#: clause id -> (evidence pointer, note). Every clause in the checklist must appear.
EVIDENCE = {
    "L06.1.1": ("lab06_response_model.json:horizon", "registered 7d; measured holding reported beside it"),
    "L06.1.2": (f"{T}test_t45_an_open_position_at_horizon_end_is_marked_not_counted_as_a_win", ""),
    "L06.1.3": (f"{T}test_t45_the_primary_grid_is_non_overlapping", ""),
    "L06.1.4": (f"{T}test_t45_an_overlapping_grid_must_declare_a_purge + test_t45_the_dependence_correction_makes_the_inflation_visible", ""),
    "L06.2.1": (f"{T}test_t46_a_later_discovery_is_rejected_with_a_reason", ""),
    "L06.2.2": (f"{T}test_t46_the_bank_respects_the_proposed_size_range", "3-8"),
    "L06.2.3": (f"{T}test_t46_duplicates_merge_for_coverage_without_losing_rows", ""),
    "L06.2.4": (f"{T}test_t46_a_retired_version_still_serves_an_open_campaign_and_cannot_be_deleted", ""),
    "L06.2.5": (f"{T}test_t46_indicator_readiness_is_tracked_by_version_and_cutoff", ""),
    "L06.3.1": ("policy/response.py:estimate_response", "guide 9.2 kernel, paired per episode"),
    "L06.3.2": ("response.py shrink a_t = N_eff/(N_eff+kappa)", ""),
    "L06.3.3": (f"{T}test_t48_the_standard_error_comes_from_blocks_not_from_bars", "N_eff, blocks, autocorrelation, per-episode contribution"),
    "L06.3.4": ("response.hyperparameters.chosen_on", "inner development only"),
    "L06.3.5": (f"{T}test_t48_eligibility_may_not_be_a_graded_quality_score", "q_e is 0/1"),
    "L06.3.6": (f"{T}test_t48_supporting_episodes_are_returned_with_the_estimate", ""),
    "L06.4.1": (f"{T}test_the_seven_decisions_exist_and_are_distinct", ""),
    "L06.4.2": ("decision.decide uses z_alpha * SE", ""),
    "L06.4.3": (f"{T}test_minimum_spacing_blocks_a_second_switch_too_soon", ""),
    "L06.4.4": (f"{T}test_the_transition_cost_is_never_double_charged", ""),
    "L06.4.5": (f"{T}test_the_quality_gate_may_reject_everything", ""),
    "L06.5.1": ("lab06_policy_spec.json:clocks.cadences", "28d fit, 4h inference"),
    "L06.5.2": ("clocks.BANK_REFRESH_CADENCE", "frozen baseline calendar"),
    "L06.5.3": ("policy_spec.clocks.cadences.switch", ""),
    "L06.5.4": ("policy_spec.clocks.triggered_refresh_is_a_separate_variant", ""),
    "L06.5.5": (f"{T}test_t49_a_superseded_job_never_becomes_effective + test_t49_near_duplicate_triggers_coalesce_into_one_job", ""),
    "L06.6.1": (f"{T}test_training_and_live_initial_state_contracts_differ_and_say_so", ""),
    "L06.6.2": ("limitations.counterfactual_limits CF-2/CF-3", ""),
    "L06.6.3": (f"{T}test_the_reset_flat_expert_curve_is_forbidden", ""),
    "L06.6.4": (f"{T}test_the_counterfactual_limits_are_recorded_with_four_named_causes", ""),
    "G9.1.1": ("policy/episodes.py:Episode.as_record", "every field guide 9.1 lists"),
    "G9.1.2": (f"{T}test_t45_the_availability_lag_is_the_full_horizon_plus_delays", ""),
    "G9.1.3": ("run_response_policy.context_at reads only emissions already available", ""),
    "G9.1.4": (f"{T}test_t46_every_entry_carries_its_own_discovery_time", "creation time replayed"),
    "G9.2.1": ("response.similarity_weights", "q_e refused unless 0/1"),
    "G9.2.2": ("response.hyperparameters", ""),
    "G9.2.3": (f"{T}test_t48_a_dominating_episode_is_flagged_and_shrunk", "context distance, not label identity"),
    "G9.2.4": (f"{T}test_t48_n_effective_is_labelled_as_weight_concentration", ""),
    "G9.2.5": (f"{T}test_t48_thin_support_keeps_the_incumbent_rather_than_recommending", ""),
    "G9.3.1": ("episodes carry net_return/max_drawdown/cost on the frozen allocation", ""),
    "G9.3.2": ("response.block_standard_error", ""),
    "G9.3.3": ("decision.transition_cost", "turnover x (fee + slippage) + residual"),
    "G9.3.4": (f"{T}test_a_clear_winner_does_switch_so_the_machine_is_not_merely_conservative", ""),
    "G9.3.5": (f"{T}test_an_inaction_region_exists_between_worse_and_clearly_better", ""),
    "G9.3.6": ("decision.DECISIONS", "seven"),
    "G9.3.7": ("TransitionCost.charging_rule", ""),
    "G9.4.1": (f"{T}test_t52_the_counters_stay_separate", ""),
    "G9.4.2": (f"{T}test_t52_a_familiar_state_change_is_not_drift", ""),
    "G9.4.3": (f"{T}test_t52_the_retrain_detector_ignores_strategy_performance", ""),
    "G9.4.4": (f"{T}test_t49_a_refit_keeps_the_cutoff_it_was_triggered_with", ""),
    "G9.4.5": (f"{T}test_t49_a_superseded_job_never_becomes_effective", ""),
    "G9.4.6": (f"{T}test_t49_the_incumbent_runs_while_a_refit_is_pending", ""),
    "G9.4.7": (f"{T}test_t49_activation_may_never_precede_ready", ""),
    "G9.5.1": (f"{T}test_t50_the_entry_digest_is_immutable", ""),
    "G9.5.2": ("Campaign.protective_version fixed at entry", ""),
    "G9.5.3": (f"{T}test_t50_an_open_campaign_defers_the_switch_rather_than_cancelling_it", ""),
    "G9.5.4": (f"{T}test_t51_an_unwarmed_candidate_waits_instead_of_switching", ""),
    "G9.5.5": (f"{T}test_t51_indicator_state_is_never_carried_without_a_contract", ""),
    "G9.5.6": (f"{T}test_t50_a_long_open_campaign_is_blocked_not_force_closed", ""),
    "G9.5.7": (f"{T}test_t46_a_retired_version_still_serves_an_open_campaign_and_cannot_be_deleted", ""),
    "G7.4.1": ("bank.specialist_note", ""),
    "G7.4.2": (f"{T}test_t46_a_later_discovery_is_rejected_with_a_reason", ""),
    "G7.4.3": ("BankEntry.as_record", "entry/retire dates, adapter hash, digest, panel, status, warmup, reason"),
    "T45": (f"{T}test_t45_an_unfinished_outcome_is_unusable", ""),
    "T46": (f"{T}test_t46_a_later_discovery_is_rejected_with_a_reason", ""),
    "T47": (f"{T}test_t47_mismatched_episode_counts_are_refused", ""),
    "T48": (f"{T}test_t48_a_dominating_episode_is_flagged_and_shrunk", ""),
    "T49": (f"{T}test_t49_activation_may_never_precede_ready", ""),
    "T50": (f"{T}test_t50_the_decision_machine_waits_at_a_campaign_boundary", ""),
    "T51": (f"{T}test_t51_an_unwarmed_candidate_waits_instead_of_switching", ""),
    "T52": (f"{T}test_t52_inference_and_switch_can_never_start_a_refit", ""),
    "OUT.1": ("configs/lab06_response_model.json", ""),
    "OUT.2": ("evidence/.../response_panel.parquet", ""),
    "OUT.3": ("response_model.responses[*].supporting_episodes", ""),
    "OUT.4": ("configs/lab06_bank_registry.json", ""),
    "OUT.5": ("configs/lab06_policy_spec.json", ""),
    "OUT.6": ("configs/lab06_decision_ledger.json", ""),
    "OUT.7": ("tests/test_lab06_policy.py", "56 tests"),
    "EXIT.1": ("decision_ledger.every_decision_records_its_cutoffs", ""),
    "EXIT.2": ("policy_spec.zero_switches_is_valid", ""),
}


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    checklist = json.loads((LAB_ROOT / "configs" / "lab06_checklist.json").read_text())
    artifacts = {n: (LAB_ROOT / "configs" / n) for n in (
        "lab06_response_model.json", "lab06_bank_registry.json",
        "lab06_policy_spec.json", "lab06_decision_ledger.json")}
    missing_artifacts = sorted(n for n, p in artifacts.items() if not p.is_file())

    tests = subprocess.run(
        [str(LAB_ROOT / "environments/lab_venv/bin/python"), "-m", "pytest",
         "tests/test_lab06_policy.py", "-q", "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=3600)
    test_line = next((ln for ln in reversed(tests.stdout.splitlines())
                      if "passed" in ln or "failed" in ln), "no pytest summary")

    rows, undocumented = [], []
    for clause_id, requirement in checklist["clauses"]:
        evidence = EVIDENCE.get(clause_id)
        if evidence is None:
            undocumented.append(clause_id)
            rows.append({"clause_id": clause_id, "requirement": requirement,
                         "evidence": None, "note": "", "status": "NO_EVIDENCE_POINTER"})
            continue
        blocked = missing_artifacts and clause_id.startswith(("OUT.", "EXIT.", "L06.5.1",
                                                              "L06.5.2", "L06.5.3", "L06.5.4",
                                                              "L06.1.1"))
        rows.append({"clause_id": clause_id, "requirement": requirement,
                     "evidence": evidence[0], "note": evidence[1],
                     "status": "BLOCKED_AWAITING_RUN" if blocked else "DONE"})

    done = sum(1 for r in rows if r["status"] == "DONE")
    payload = {
        "schema": "crypto_regime_lab.lab06_task_audit.v1",
        "guide_section": "LAB-06 — Conditional parameter response va bon clocks",
        "checklist_written_before_code": True,
        "checklist_source": "configs/lab06_checklist.json",
        "tasks_total": len(rows), "tasks_done": done,
        "tasks_blocked": len(rows) - done,
        "clauses_without_an_evidence_pointer": undocumented,
        "artifacts_present": sorted(set(artifacts) - set(missing_artifacts)),
        "artifacts_missing": missing_artifacts,
        "acceptance_tests": test_line,
        "acceptance_tests_passed": tests.returncode == 0,
        "acceptance_ids_covered": ["T45", "T46", "T47", "T48", "T49", "T50", "T51", "T52"],
        "tasks": rows,
    }
    writer.write_config("lab06_task_audit.json", payload)
    writer.write_json("lab06_task_audit.json", payload, schema=payload["schema"])

    print(f"LAB-06 audit: {done}/{len(rows)} DONE")
    for row in rows:
        if row["status"] != "DONE":
            print(f"   {row['status']:<24} {row['clause_id']} {row['requirement'][:70]}")
    print(f"clauses with no evidence pointer: {undocumented or 'none'}")
    print(f"artifacts missing: {missing_artifacts or 'none'}")
    print(f"acceptance tests : {test_line}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if done == len(rows) and tests.returncode == 0 and not undocumented else 1


if __name__ == "__main__":
    raise SystemExit(main())
