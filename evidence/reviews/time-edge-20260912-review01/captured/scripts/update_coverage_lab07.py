#!/usr/bin/env python
"""Move T53-T57 from PARTIAL/NOT_YET to their honest LAB-07 status.

T55, T56 and T57 become COVERED. T53 and T54 stay PARTIAL, and the reason is
worth stating plainly: T53 asks whether A/B/C/D share fixed economics, and arms
C and D do not exist yet -- LAB-07 fixes the economics and shows one arm running
on them, which is a precondition, not the claim. T54 asks that an OOS-selecting
mode be reported as A_legacy_selection_adjusted in an arm comparison, and there
is no arm comparison until LAB-08.

Marking either COVERED here would be the phase claiming credit for work the
next phase owes.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PY_BIN = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"
COVERAGE = LAB_ROOT / "configs" / "acceptance_test_coverage.json"
T = "tests/test_lab07_integration.py::"

COVERED = {
    "T55": [f"{T}test_the_daily_account_is_the_comparison_not_the_mean_of_segment_sharpes",
            f"{T}test_segment_sharpes_are_diagnostic_and_the_daily_account_is_primary",
            f"{T}test_an_open_segment_has_no_length_until_the_next_activation_exists"],
    "T56": [f"{T}test_the_continuous_account_never_resets_across_a_parameter_switch",
            f"{T}test_the_tape_is_built_from_the_active_adapter_at_every_bar",
            f"{T}test_a_handcrafted_fill_cannot_enter_the_account",
            f"{T}test_the_run_actually_traded"],
    # The first version cited three latency tests here, which have nothing to do
    # with sequential-vs-adaptive-batch semantics. A requirement marked COVERED
    # by tests that do not test it hides the gap instead of showing it.
    "T57": [f"{T}test_t57_the_sequencing_contract_is_declared",
            f"{T}test_t57_the_primary_search_is_a_fixed_matrix_that_actually_reproduces",
            f"{T}test_t57_the_design_is_seeded_not_sampler_dependent",
            f"{T}test_t57_exactly_one_schedule_type_is_declared_for_the_primary_comparison",
            "tests/test_lab04_selector.py::test_t32_probe_design_is_reproducible_across_processes"],
}

STILL_PARTIAL = {
    "T53": ("LAB-07 fixes the economics and runs ONE arm on them: the account contract is "
            "frozen, the compute-budget contract is registered, and the continuous account "
            "never resets. Arms C, D and E do not exist, so the four-arm claim is not "
            "available.", ["tests/test_lab07_integration.py::"
                           "test_the_continuous_account_never_resets_across_a_parameter_switch"]),
    "T54": ("LAB-04 measured which installed modes consume OOS to select and fixed the label. "
            "LAB-07 carries that label into the run record. Applying it to a reported ARM "
            "COMPARISON is LAB-08's, because there is no arm comparison yet.",
            ["tests/test_lab04_legacy_labelling.py::"
             "test_modes_declaring_oos_selection_are_named_and_labelled"]),
}


def main() -> int:
    payload = json.loads(COVERAGE.read_text())
    collected = subprocess.run(
        [str(PY_BIN), "-m", "pytest", "tests/test_lab07_integration.py", "--collect-only", "-q",
         "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=1800).stdout
    known = {f"tests/{ln.strip().split('tests/', 1)[-1]}" for ln in collected.splitlines()
             if "::" in ln}
    known |= {node.split("[")[0] for node in known}
    extra = subprocess.run(
        [str(PY_BIN), "-m", "pytest", "tests/test_lab04_selector.py", "--collect-only", "-q",
         "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=1800).stdout
    known |= {f"tests/{ln.strip().split('tests/', 1)[-1]}" for ln in extra.splitlines()
              if "::" in ln}

    missing = [t for tests in COVERED.values() for t in tests if t not in known]
    if missing:
        print("these tests do not exist; coverage is NOT updated:")
        for test in missing:
            print(f"   {test}")
        return 1

    for record in payload["requirements"]:
        if record["id"] in COVERED:
            record["status"] = "COVERED"
            record["tests"] = COVERED[record["id"]]
            record.pop("partial_reason", None)
            record["owning_phase"] = "LAB-07"
        elif record["id"] in STILL_PARTIAL:
            reason, tests = STILL_PARTIAL[record["id"]]
            record["status"] = "PARTIAL"
            record["partial_reason"] = reason
            record["partially_discharged_by"] = "LAB-04 + LAB-07"
            record["owning_phase"] = "LAB-08"
            record["tests"] = tests
    payload["as_of_phase"] = "LAB-07"
    payload["counts"] = dict(Counter(r["status"] for r in payload["requirements"]))
    COVERAGE.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"coverage as of {payload['as_of_phase']}: {payload['counts']}")
    for record in payload["requirements"]:
        if record["id"] in COVERED or record["id"] in STILL_PARTIAL:
            print(f"   {record['id']} {record['status']:<10} {len(record['tests'])} tests  "
                  f"{record['title'][:46]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
