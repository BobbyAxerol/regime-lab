#!/usr/bin/env python
"""Move T45-T52 to COVERED, from the tests that actually exist."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PY_BIN = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"
COVERAGE = LAB_ROOT / "configs" / "acceptance_test_coverage.json"
T = "tests/test_lab06_policy.py::"

LAB06 = {
    "T45": [f"{T}test_t45_an_unfinished_outcome_is_unusable",
            f"{T}test_t45_the_availability_lag_is_the_full_horizon_plus_delays",
            f"{T}test_t45_the_builder_marks_an_unfinished_window_rather_than_dropping_it",
            f"{T}test_t45_an_open_position_at_horizon_end_is_marked_not_counted_as_a_win",
            f"{T}test_t45_the_primary_grid_is_non_overlapping",
            f"{T}test_t45_an_overlapping_grid_must_declare_a_purge",
            f"{T}test_t45_the_dependence_correction_makes_the_inflation_visible",
            f"{T}test_t45_purging_removes_windows_inside_the_shadow"],
    "T46": [f"{T}test_t46_a_later_discovery_is_rejected_with_a_reason",
            f"{T}test_t46_trial_rows_are_retained_even_when_rejected_or_merged",
            f"{T}test_t46_duplicates_merge_for_coverage_without_losing_rows",
            f"{T}test_t46_the_bank_respects_the_proposed_size_range",
            f"{T}test_t46_a_retired_version_still_serves_an_open_campaign_and_cannot_be_deleted",
            f"{T}test_t46_indicator_readiness_is_tracked_by_version_and_cutoff",
            f"{T}test_t46_every_entry_carries_its_own_discovery_time",
            f"{T}test_t46_admissible_re_checks_rather_than_trusting_the_build"],
    "T47": [f"{T}test_t47_mismatched_episode_counts_are_refused",
            f"{T}test_t47_the_delta_is_a_per_episode_difference",
            f"{T}test_t47_episodes_carry_the_same_initial_state_contract"],
    "T48": [f"{T}test_t48_a_dominating_episode_is_flagged_and_shrunk",
            f"{T}test_t48_n_effective_is_labelled_as_weight_concentration",
            f"{T}test_t48_a_single_contiguous_block_is_not_enough_support",
            f"{T}test_t48_thin_support_keeps_the_incumbent_rather_than_recommending",
            f"{T}test_t48_eligibility_may_not_be_a_graded_quality_score",
            f"{T}test_t48_supporting_episodes_are_returned_with_the_estimate",
            f"{T}test_t48_the_standard_error_comes_from_blocks_not_from_bars"],
    "T49": [f"{T}test_t49_activation_may_never_precede_ready",
            f"{T}test_t49_a_superseded_job_never_becomes_effective",
            f"{T}test_t49_a_refit_keeps_the_cutoff_it_was_triggered_with",
            f"{T}test_t49_near_duplicate_triggers_coalesce_into_one_job",
            f"{T}test_t49_the_incumbent_runs_while_a_refit_is_pending",
            f"{T}test_t49_a_job_cannot_be_ready_before_it_was_triggered"],
    "T50": [f"{T}test_t50_the_entry_digest_is_immutable",
            f"{T}test_t50_an_open_campaign_defers_the_switch_rather_than_cancelling_it",
            f"{T}test_t50_the_decision_machine_waits_at_a_campaign_boundary",
            f"{T}test_t50_a_long_open_campaign_is_blocked_not_force_closed"],
    "T51": [f"{T}test_t51_an_unwarmed_candidate_waits_instead_of_switching",
            f"{T}test_t51_indicator_state_is_never_carried_without_a_contract",
            f"{T}test_t51_warmup_progresses_from_cold_through_warming_to_ready"],
    "T52": [f"{T}test_t52_the_four_clocks_are_distinct",
            f"{T}test_t52_inference_and_switch_can_never_start_a_refit",
            f"{T}test_t52_the_counters_stay_separate",
            f"{T}test_t52_the_retrain_detector_ignores_strategy_performance",
            f"{T}test_t52_a_familiar_state_change_is_not_drift"],
}


def main() -> int:
    payload = json.loads(COVERAGE.read_text())
    collected = subprocess.run(
        [str(PY_BIN), "-m", "pytest", "tests/test_lab06_policy.py", "--collect-only", "-q",
         "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=1800).stdout
    known = {f"tests/{ln.strip().split('tests/', 1)[-1]}" for ln in collected.splitlines()
             if "::" in ln}
    known |= {node.split("[")[0] for node in known}

    missing = [t for tests in LAB06.values() for t in tests if t not in known]
    if missing:
        print("these tests do not exist; coverage is NOT updated:")
        for test in missing:
            print(f"   {test}")
        return 1

    for record in payload["requirements"]:
        if record["id"] in LAB06:
            record["status"] = "COVERED"
            record["tests"] = LAB06[record["id"]]
    payload["as_of_phase"] = "LAB-06"
    payload["counts"] = dict(Counter(r["status"] for r in payload["requirements"]))
    COVERAGE.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"coverage as of {payload['as_of_phase']}: {payload['counts']}")
    for record in payload["requirements"]:
        if record["id"] in LAB06:
            print(f"   {record['id']} {record['status']:<10} {len(record['tests'])} tests  "
                  f"{record['title'][:46]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
