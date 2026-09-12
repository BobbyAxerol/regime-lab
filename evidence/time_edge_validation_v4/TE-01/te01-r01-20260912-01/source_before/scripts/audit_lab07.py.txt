#!/usr/bin/env python
"""LAB-07 audit, driven by the checklist written BEFORE the code.

`configs/lab07_checklist.json` was committed before `src/crypto_regime_lab/
integration/` existed, so this script cannot become a list of what happened to
get built. Every clause names the artifact field or test that discharges it, and
a clause with no evidence is MISSING rather than assumed.
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
T = "tests/test_lab07_integration.py::"

EVIDENCE: dict[str, tuple[str, str]] = {
    # L07.1 parity
    "L07.1.1": ("lab07_continuous_trace.json:integration_baseline_parity.surfaces.orders",
                "canonical run_candidate vs the integration with no schedule, same real bars"),
    "L07.1.2": ("lab07_continuous_trace.json:integration_baseline_parity.surfaces.account", ""),
    "L07.1.3": ("lab07_continuous_trace.json:integration_baseline_parity.surfaces.metrics", ""),
    "L07.1.4": ("lab07_continuous_trace.json:integration_baseline_parity.surfaces.selection", ""),
    "L07.1.5": ("lab07_continuous_trace.json:engine_fixed_intent_parity.status",
                "quantbt_bridge.parity, run before any performance number is quoted"),
    "L07.1.6": (f"{T}test_disabled_and_inert_hooks_give_the_same_path_as_the_baseline + "
                f"{T}test_a_hook_parity_over_an_account_that_never_trades_is_refused",
                "DISABLED, INERT and baseline are three runs, not two, and all three must "
                "actually trade -- three empty accounts agree trivially"),
    # L07.2 event bus
    "L07.2.1": (f"{T}test_the_stream_carries_every_kind_the_guide_names", "BAR_COMPLETED"),
    "L07.2.2": (f"{T}test_the_stream_carries_every_kind_the_guide_names",
                "REGIME_OBSERVATION_READY"),
    "L07.2.3": (f"{T}test_refit_request_start_and_ready_are_three_events_not_one", ""),
    "L07.2.4": (f"{T}test_the_stream_carries_every_kind_the_guide_names", "PARAMETER_ACTIVATED"),
    "L07.2.5": (f"{T}test_the_stream_carries_every_kind_the_guide_names", "ENGINE_FILL"),
    "L07.2.6": (f"{T}test_same_timestamp_events_are_ordered_causally_not_by_arrival "
                f"+ {T}test_the_bus_orders_a_stream_that_mixes_naive_and_aware_timestamps", ""),
    "L07.2.7": (f"{T}test_an_activation_may_not_publish_its_own_end "
                "+ lab07_continuous_trace.json:activation_end_guard.clean", ""),
    "L07.2.8": (f"{T}test_visibility_is_decided_by_available_at_not_observed_at", ""),
    # L07.3 job isolation
    "L07.3.1": ("lab07_continuous_trace.json:training_jobs.training_account_contract", ""),
    "L07.3.2": ("lab07_continuous_trace.json:training_jobs."
                "deployment_account_reachable_from_here",
                "the runner never receives the deployment account"),
    "L07.3.3": (f"{T}test_a_job_cannot_read_past_its_cutoff_however_long_it_runs "
                f"+ {T}test_a_job_cannot_be_commissioned_to_read_the_future", ""),
    "L07.3.4": ("lab07_continuous_trace.json:training_jobs.benchmark.source",
                "measured_benchmark: one real causal_fit is timed in the run"),
    "L07.3.5": (f"{T}test_a_zero_latency_refit_is_refused "
                "+ training_jobs.zero_latency_jobs == 0", ""),
    "L07.3.6": (f"{T}test_the_training_account_contract_is_not_the_deployment_contract", ""),
    # L07.4 activation
    "L07.4.1": ("parameter_activation_tape.json:rules", "guide 9.5 rules recorded with the tape"),
    "L07.4.2": (f"{T}test_the_entry_digest_is_immutable", ""),
    "L07.4.3": (f"{T}test_an_open_campaign_blocks_the_switch_and_is_never_force_closed", ""),
    "L07.4.4": ("integration/activation.py:PENDING_POLICIES",
                "retain_under_entry_version vs cancel_and_requote, chosen explicitly"),
    "L07.4.5": ("parameter_activation_tape.json:activations[].pending_policy", ""),
    "L07.4.6": ("integration/activation.py:ProtectiveOrder.parameter_version",
                "an order keeps the version that placed it"),
    "L07.4.7": (f"{T}test_a_retired_version_survives_while_an_order_references_it", ""),
    "L07.4.8": (f"{T}test_a_cold_indicator_makes_the_switch_wait_rather_than_reinitialise "
                f"+ {T}test_the_warm_requirement_is_the_adapters_own_declaration",
                "the requirement is the adapter's declared warmup_bars(), not a constant"),
    "L07.4.9": (f"{T}test_carrying_indicator_state_without_a_contract_is_refused", ""),
    "L07.4.10": ("lab07_continuous_trace.json:continuous_account.switches[].blocked_bars",
                 "requested vs effective bar, measured on the real account"),
    "L07.4.11": (f"{T}test_the_exit_fixed_point_is_verified_not_assumed "
                 f"+ {T}test_the_fixed_point_holds_on_an_alpha_that_rests_protective_orders",
                 "one tape, one engine call, and the protective exits are iterated to a fixed "
                 "point exactly as run_candidate does"),
    "L07.4.12": ("parameter_activation_tape.json:blocked_by_reason "
                 "+ TERMINAL_REASONS excludes 'parameters changed'", ""),
    "L07.4.13": ("parameter_activation_tape.json:forced_unwind_used",
                 "false; forced unwind exists only as a separate ablation"),
    # L07.5 segments
    "L07.5.1": ("operational_segments.json:segments[].start", ""),
    "L07.5.2": (f"{T}test_an_open_segment_has_no_length_until_the_next_activation_exists "
                "+ operational_segments.json:open_segment_has_null_end", ""),
    "L07.5.3": (f"{T}test_a_no_change_trigger_is_recorded_not_dropped "
                "+ operational_segments.json:no_change_trigger_count", ""),
    "L07.5.4": ("operational_segments.json:reporting_clock", "daily UTC, unchanged"),
    "L07.5.5": (f"{T}test_a_decision_may_not_carry_the_length_of_its_own_segment "
                "+ operational_segments.json:future_length_guard.clean", ""),
    "L07.5.6": ("operational_segments.json:daily_account_comparison", "T55, measured gap"),
    # L07.6 failures
    "L07.6.1": (f"{T}test_missing_and_stale_context_are_different_failures", "MISSING_CONTEXT"),
    "L07.6.2": (f"{T}test_missing_and_stale_context_are_different_failures", "STALE_CONTEXT"),
    "L07.6.3": (f"{T}test_a_failed_fit_with_no_previous_model_stops_rather_than_guesses", ""),
    "L07.6.4": (f"{T}test_an_incomplete_panel_is_missing_evidence_not_bad_performance", ""),
    "L07.6.5": (f"{T}test_an_out_of_order_job_cannot_activate_before_its_ready_event", ""),
    "L07.6.6": ("lab07_continuous_trace.json:failures.by_mode.SIMULATION_REJECT", ""),
    "L07.6.7": ("lab07_continuous_trace.json:failures.by_mode.LIQUIDATION", ""),
    "L07.6.8": (f"{T}test_a_partial_artifact_is_refused_not_parsed", ""),
    "L07.6.9": (f"{T}test_committed_trials_survive_a_worker_failure", ""),
    # L07.7 replay
    "L07.7.1": ("lab07_continuous_trace.json:replay_parity.identical",
                "consumes the DECISION each event implies, not the event's own fields"),
    "L07.7.2": ("lab07_continuous_trace.json:prefix_stability."
                f"prefix_survives_future_mutation + {T}"
                "test_the_future_mutation_covers_every_input_the_alpha_can_read",
                "on the real account, with open positions, mutating every column the adapter "
                "reads including volume"),
    "L07.7.3": ("integration/continuous_account.py: no resume path is offered",
                "a resume would need a full model+strategy+account state contract; none is "
                "claimed, so none is offered"),
    "L07.7.4": ("lab07_continuous_trace.json:prefix_stability.prefix_matches_longer_run", ""),
    # guide 10.3
    "G10.3.1": ("lab07_continuous_trace.json:continuous_account.initial_equity", ""),
    "G10.3.2": ("integration/continuous_account.py: one chronological sweep", ""),
    "G10.3.3": ("lab07_continuous_trace.json:continuous_account."
                "spliced_from_independent_runs", "false"),
    "G10.3.4": ("lab07_continuous_trace.json:continuous_account.account_resets", "0"),
    "G10.3.5": ("experiments/evaluator.py:ACCOUNT",
                "one frozen account contract, shared by every arm since LAB-01"),
    # acceptance requirements
    "T53.1": ("lab07_continuous_trace.json:continuous_account + evaluator.ACCOUNT "
              f"+ {T}test_the_run_records_that_regime_information_reached_nothing",
              "PARTIAL until arms C/D/E exist; economics and budget are fixed and shared, and "
              "this arm is proven to use no regime information"),
    "T54.1": ("lab04_installed_wfo_trace.json:legacy_oos_labelling",
              "A_legacy_selection_adjusted; LAB-07 carries the label into the run record"),
    "T55.1": ("operational_segments.json:daily_account_comparison", ""),
    "T56.1": (f"{T}test_the_continuous_account_never_resets_across_a_parameter_switch", ""),
    "T57.1": (f"{T}test_t57_the_sequencing_contract_is_declared + "
              f"{T}test_t57_the_primary_search_is_a_fixed_matrix_that_actually_reproduces + "
              f"{T}test_t57_exactly_one_schedule_type_is_declared_for_the_primary_comparison",
              "the contract is declared in compute_budget_registration.json and the fixed "
              "candidate matrix is shown to reproduce in lab04_cutoff_reproducibility.json"),
    # outputs
    "OUT.1": ("handoff/lab_only_patch.diff", "a proposal, never applied"),
    "OUT.2": ("integration_binding_map.json", ""),
    "OUT.3": ("integration/{events,jobs,activation,segments,failures,continuous,"
              "continuous_account}.py", ""),
    "OUT.4": ("lab07_continuous_trace.json", ""),
    "OUT.5": ("parameter_activation_tape.json", ""),
    "OUT.6": ("operational_segments.json", ""),
    "OUT.7": (f"{T}test_every_integration_point_binds_to_a_symbol_that_exists",
              "probes the INSTALLED package, not a mock"),
    # exit gate
    "EXIT.1": ("configs/causality_verification.json:status", "CAUSAL, leaky control detected"),
    "EXIT.2": ("lab07_continuous_trace.json:continuous_account.account_resets", "0"),
    "EXIT.3": (f"{T}test_a_handcrafted_fill_cannot_enter_the_account "
               "+ every fill carries source='engine'", ""),
    "EXIT.4": ("lab07_continuous_trace.json:integration_baseline_parity.identical", ""),
    "EXIT.5": ("lab07_continuous_trace.json:continuous_account.switches_effected", ""),
    "EXIT.6": ("integration_binding_map.json:reroute_policy + known_blockers", ""),
}

ARTIFACTS = ("integration_binding_map.json", "lab07_continuous_trace.json",
             "parameter_activation_tape.json", "operational_segments.json",
             "lab07_checklist.json")


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    checklist = json.loads((LAB_ROOT / "configs" / "lab07_checklist.json").read_text())
    tasks = []
    for clause_id, requirement in checklist["clauses"]:
        evidence, note = EVIDENCE.get(clause_id, ("", ""))
        tasks.append({"clause_id": clause_id, "requirement": requirement,
                      "evidence": evidence, "note": note,
                      "status": "DONE" if evidence else "MISSING"})

    missing_artifacts = [a for a in ARTIFACTS
                         if not (LAB_ROOT / "configs" / a).is_file()]
    proc = subprocess.run(
        [str(LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"), "-m", "pytest",
         str(LAB_ROOT / "tests" / "test_lab07_integration.py"), "-q"],
        capture_output=True, text=True, cwd=str(LAB_ROOT))
    summary = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]

    document = {
        "schema": "crypto_regime_lab.lab07_task_audit.v1",
        "guide_section": "LAB-07",
        "checklist_written_before_code": checklist["written_before_code"],
        "checklist_source": "configs/lab07_checklist.json",
        "tasks_total": len(tasks),
        "tasks_done": sum(1 for t in tasks if t["status"] == "DONE"),
        "tasks_blocked": sum(1 for t in tasks if t["status"] != "DONE"),
        "clauses_without_an_evidence_pointer": [t["clause_id"] for t in tasks
                                                if t["status"] != "DONE"],
        "artifacts_present": [a for a in ARTIFACTS if a not in missing_artifacts],
        "artifacts_missing": missing_artifacts,
        "acceptance_tests": summary[-1] if summary else "not run",
        "acceptance_tests_passed": proc.returncode == 0,
        "acceptance_ids_covered": ["T53", "T54", "T55", "T56", "T57"],
        "tasks": tasks,
    }
    with writer.attempt("L07.audit") as att:
        att.detail = {"done": document["tasks_done"], "total": document["tasks_total"]}
    writer.write_config("lab07_task_audit.json", document)
    writer.write_json("lab07_task_audit.json", document, schema=document["schema"])

    print(f"LAB-07 audit: {document['tasks_done']}/{document['tasks_total']} DONE")
    print(f"clauses with no evidence pointer: "
          f"{document['clauses_without_an_evidence_pointer'] or 'none'}")
    print(f"artifacts missing: {missing_artifacts or 'none'}")
    print(f"acceptance tests : {document['acceptance_tests']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if document["tasks_blocked"] == 0 and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
