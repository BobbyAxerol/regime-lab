#!/usr/bin/env python
"""Move T29-T36 to COVERED and re-count, from the tests that actually exist."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PY_BIN = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"
COVERAGE = LAB_ROOT / "configs" / "acceptance_test_coverage.json"

LAB04 = {
    "T29": ["tests/test_lab04_selector.py::test_t29_broad_neighbourhood_beats_a_sharp_peak",
            "tests/test_lab04_selector.py::test_t29_bad_neighbour_counterexample_is_first_class",
            "tests/test_lab04_selector.py::test_t29_valid_bad_probes_stay_in_the_denominator",
            "tests/test_lab04_selector.py::test_t29_runtime_error_is_incomplete_evidence_not_a_loss",
            "tests/test_lab04_selector.py::test_t29_structurally_invalid_is_not_bad_performance"],
    "T30": ["tests/test_lab04_selector.py::test_t30_flat_but_negative_fails_economic_quality",
            "tests/test_lab04_selector.py::test_t30_a_flat_negative_region_is_never_eligible"],
    "T31": ["tests/test_lab04_selector.py::test_t31_geometry_is_unchanged_by_a_far_sampled_point",
            "tests/test_lab04_selector.py::test_t31_lab_distance_ignores_samples_entirely",
            "tests/test_lab04_selector.py::test_t31_fixed_dimension_is_excluded_from_the_denominator",
            "tests/test_lab04_selector.py::test_t31_inactive_parameter_creates_no_false_distance"],
    "T32": ["tests/test_lab04_selector.py::test_t32_probes_on_a_dependent_manifold_are_feasible_and_unique",
            "tests/test_lab04_selector.py::test_t32_dependencies_are_parameterised_not_repaired",
            "tests/test_lab04_selector.py::test_t32_a_chained_dependency_is_declared_in_full",
            "tests/test_lab04_selector.py::test_t32_probe_design_is_reproducible_across_processes",
            "tests/test_lab04_selector.py::test_t32_inactive_conditional_key_still_builds_a_valid_point"],
    "T33": ["tests/test_lab04_selector.py::test_t33_unevaluated_centroid_is_not_deployable",
            "tests/test_lab04_selector.py::test_t33_assert_evaluated_accepts_only_a_point_that_was_run"],
    "T34": ["tests/test_lab04_selector.py::test_t34_medoid_minimises_the_same_distance_the_selector_declares",
            "tests/test_lab04_selector.py::test_t34_tie_break_is_deterministic_on_the_stable_id"],
    "T35": ["tests/test_lab04_selector.py::test_t35_incumbent_guard_disagreement_is_visible",
            "tests/test_lab04_selector.py::test_t35_incumbent_receives_the_same_validation_budget",
            "tests/test_lab04_selector.py::test_t35_the_incumbent_is_an_anchor_with_a_full_probe_budget"],
    "T36": ["tests/test_lab04_selector.py::test_t36_presets_are_barred_from_the_primary_bank",
            "tests/test_lab04_selector.py::test_t36_no_preset_value_is_a_seed_point_or_an_anchor",
            "tests/test_lab04_selector.py::test_t36_declared_bounds_enclose_the_alpha_operating_range"],
}


#: Requirements OWNED by a later phase that LAB-04 partly discharges. They stay
#: PARTIAL with the reason stated: claiming COVERED would hide the part still owed.
CROSS_PHASE_PARTIAL = {
    "T53": {
        "tests": [
            "tests/test_lab04_selector.py::test_account_contract_matches_the_frozen_registration",
            "tests/test_lab04_selector.py::test_utility_costs_are_not_charged_twice",
            "tests/test_lab04_evaluator.py::test_entries_are_sized_to_the_frozen_entry_notional",
            "tests/test_lab04_evaluator.py::test_both_arms_choose_from_the_identical_pool",
            "tests/test_lab04_evaluator.py::test_anchor_budget_matches_the_guide",
        ],
        "partial_reason": (
            "LAB-04 fixes the economics and the search budget for arms A and B and shows they are "
            "identical. Arms C, D and E do not exist yet, so the four-arm claim is not available."),
    },
    "T54": {
        "tests": [
            "tests/test_lab04_legacy_labelling.py::test_modes_declaring_oos_selection_are_named_and_labelled",
            "tests/test_lab04_legacy_labelling.py::test_the_engines_own_oos_claim_is_captured_for_every_mode",
            "tests/test_lab04_legacy_labelling.py::test_a_null_behavioural_probe_never_overrides_the_declaration",
            "tests/test_lab04_legacy_labelling.py::test_the_mutation_probe_proves_it_could_have_detected_a_change",
            "tests/test_lab04_legacy_labelling.py::test_full_sample_calibration_is_not_reported_as_walk_forward",
        ],
        "partial_reason": (
            "LAB-04 measures which installed modes consume OOS to select and fixes the labelling "
            "rule (A_legacy_selection_adjusted, never an untouched baseline). LAB-07 still owes the "
            "application of that label to a reported arm comparison."),
    },
    "T59": {
        "tests": [
            "tests/test_lab04_selector.py::test_t29_valid_bad_probes_stay_in_the_denominator",
            "tests/test_lab04_selector.py::test_t29_runtime_error_is_incomplete_evidence_not_a_loss",
            "tests/test_lab04_selector.py::test_t29_structurally_invalid_is_not_bad_performance",
            "tests/test_lab04_selector.py::test_a_not_ready_alpha_reports_null_never_zero",
            "tests/test_lab04_evaluator.py::test_summaries_never_mean_an_empty_list",
        ],
        "partial_reason": (
            "LAB-04 retains every valid losing probe in the denominator, keeps structurally invalid "
            "points as excluded-with-reason rather than as bad performance, records runtime errors "
            "as incomplete evidence, and reports a blocked alpha as null. LAB-08 still owes the "
            "full trial ledger and the objective recompute."),
    },
}


def main() -> int:
    payload = json.loads(COVERAGE.read_text())
    collected = subprocess.run(
        [str(PY_BIN), "-m", "pytest", "tests/test_lab04_selector.py", "--collect-only", "-q",
         "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=1800).stdout
    # pytest prints node ids relative to its rootdir, which sits above LAB_ROOT
    known = {line.strip().split("tests/", 1)[-1] for line in collected.splitlines()
             if "::" in line}
    known = {f"tests/{node}" for node in known}

    collected_all = subprocess.run(
        [str(PY_BIN), "-m", "pytest", "tests/", "--collect-only", "-q", "--no-header",
         "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=1800).stdout
    known_all = {f"tests/{ln.strip().split('tests/', 1)[-1]}"
                 for ln in collected_all.splitlines() if "::" in ln}

    missing = []
    for req_id, tests in LAB04.items():
        for test in tests:
            if test not in known:
                missing.append(test)
    for req_id, record in CROSS_PHASE_PARTIAL.items():
        for test in record["tests"]:
            if test not in known_all:
                missing.append(test)
    if missing:
        print("these tests do not exist; coverage is NOT updated:")
        for test in missing:
            print(f"   {test}")
        return 1

    for record in payload["requirements"]:
        if record["id"] in LAB04:
            record["status"] = "COVERED"
            record["tests"] = LAB04[record["id"]]
        elif record["id"] in CROSS_PHASE_PARTIAL:
            extra = CROSS_PHASE_PARTIAL[record["id"]]
            record["status"] = "PARTIAL"
            record["tests"] = sorted(set(record.get("tests") or []) | set(extra["tests"]))
            record["partial_reason"] = extra["partial_reason"]
            record["partially_discharged_by"] = "LAB-04"
    payload["as_of_phase"] = "LAB-04"
    payload["counts"] = dict(Counter(r["status"] for r in payload["requirements"]))
    COVERAGE.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"coverage as of {payload['as_of_phase']}: {payload['counts']}")
    for record in payload["requirements"]:
        if record["id"] in LAB04 or record["id"] in CROSS_PHASE_PARTIAL:
            print(f"   {record['id']} {record['status']:<10} {len(record['tests'])} tests  "
                  f"{record['title'][:46]}")
            if record.get("partial_reason"):
                print(f"        still owed: {record['partial_reason'][-96:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
