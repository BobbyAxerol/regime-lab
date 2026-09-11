#!/usr/bin/env python
"""Move T37-T44 to COVERED, from the tests that actually exist."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PY_BIN = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"
COVERAGE = LAB_ROOT / "configs" / "acceptance_test_coverage.json"
T = "tests/test_lab05_regime.py::"

LAB05 = {
    "T37": [f"{T}test_t37_endpoint_costs_equal_brute_force",
            f"{T}test_t37_online_states_equal_brute_force",
            f"{T}test_t37_offline_path_equals_brute_force_best_path",
            f"{T}test_t37_the_causal_and_offline_answers_really_do_differ",
            f"{T}test_t37_offline_path_is_never_decision_eligible",
            f"{T}test_t37_normalisation_changes_neither_argmin_nor_differences",
            f"{T}test_t37_tie_break_is_the_lowest_state_index"],
    "T38": [f"{T}test_t38_streaming_equals_batch_at_every_prefix",
            f"{T}test_t38_the_streaming_filter_cannot_see_the_future",
            f"{T}test_t38_an_emission_tape_is_append_only",
            f"{T}test_t38_a_foreign_namespace_cannot_be_appended",
            f"{T}test_t38_switches_come_from_the_tape_not_from_lambda"],
    "T39": [f"{T}test_t39_a_causal_fit_is_bit_identical_under_a_mutated_future",
            f"{T}test_t39_the_detector_catches_a_known_leak",
            f"{T}test_t39_the_scaler_is_fitted_on_the_prefix_only"],
    "T40": [f"{T}test_t40_all_zero_weights_is_flagged_and_blocks_decisions",
            f"{T}test_t40_identical_centroids_are_degenerate",
            f"{T}test_t40_an_empty_state_is_reported_not_hidden",
            f"{T}test_t40_a_healthy_model_is_usable",
            f"{T}test_t40_empty_states_survive_a_fit_without_inventing_members"],
    "T41": [f"{T}test_t41_a_pure_permutation_maps_cleanly_and_is_not_a_market_event",
            f"{T}test_t41_a_state_that_really_moved_is_left_unmapped",
            f"{T}test_t41_relabelling_marks_unmapped_states_as_minus_one",
            f"{T}test_t41_a_model_transition_never_rewrites_prior_emissions",
            f"{T}test_t41_mapping_uses_training_information_only"],
    "T42": [f"{T}test_t42_membership_sums_to_one_and_is_still_not_a_probability",
            f"{T}test_t42_second_best_gap_measures_ambiguity"],
    "T43": [f"{T}test_t43_the_inference_modules_cannot_call_a_fit",
            f"{T}test_t43_the_registry_says_a_transition_is_not_a_search_trigger"],
    "T44": [f"{T}test_t44_identical_residual_but_missing_inputs_gives_a_different_status",
            f"{T}test_t44_all_four_fallback_reasons_are_distinct",
            f"{T}test_t44_the_novelty_threshold_comes_from_training_residuals"],
}


def main() -> int:
    payload = json.loads(COVERAGE.read_text())
    collected = subprocess.run(
        [str(PY_BIN), "-m", "pytest", "tests/test_lab05_regime.py", "--collect-only", "-q",
         "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=1800).stdout
    known = {f"tests/{ln.strip().split('tests/', 1)[-1]}" for ln in collected.splitlines()
             if "::" in ln}
    known |= {node.split("[")[0] for node in known}      # drop parametrisation suffixes

    missing = [t for tests in LAB05.values() for t in tests if t not in known]
    if missing:
        print("these tests do not exist; coverage is NOT updated:")
        for test in missing:
            print(f"   {test}")
        return 1

    for record in payload["requirements"]:
        if record["id"] in LAB05:
            record["status"] = "COVERED"
            record["tests"] = LAB05[record["id"]]
    payload["as_of_phase"] = "LAB-05"
    payload["counts"] = dict(Counter(r["status"] for r in payload["requirements"]))
    COVERAGE.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"coverage as of {payload['as_of_phase']}: {payload['counts']}")
    for record in payload["requirements"]:
        if record["id"] in LAB05:
            print(f"   {record['id']} {record['status']:<10} {len(record['tests'])} tests  "
                  f"{record['title'][:48]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
