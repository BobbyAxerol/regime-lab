#!/usr/bin/env python
"""Move T53, T58, T59 and T60 to their honest LAB-08 status."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PY_BIN = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"
COVERAGE = LAB_ROOT / "configs" / "acceptance_test_coverage.json"
T = "tests/test_lab08_factorial.py::"

COVERED = {
    "T53": [f"{T}test_the_five_arms_differ_only_in_selector_and_timing",
            f"{T}test_the_dynamic_arm_gets_exactly_the_calendars_refresh_count",
            f"{T}test_the_protocol_registers_every_contrast_and_control",
            f"{T}test_a_contrast_is_taken_on_shared_dates_only"],
    "T58": [f"{T}test_all_seven_mandatory_controls_are_declared",
            f"{T}test_the_placebo_matches_the_real_dwell_rather_than_switching_freely",
            f"{T}test_a_free_running_placebo_is_detected_as_unmatched",
            f"{T}test_risk_only_never_levers_above_the_baseline",
            f"{T}test_an_unseen_state_gets_no_extrapolated_size"],
    "T59": [f"{T}test_an_unrunnable_arm_reports_null_not_zero",
            f"{T}test_the_protocol_covers_all_twenty_cells_including_the_blocked_ones",
            f"{T}test_a_period_with_no_transition_refuses_rather_than_pads"],
    "T60": [f"{T}test_a_contrast_is_taken_on_shared_dates_only",
            f"{T}test_the_hindsight_control_is_never_tradeable"],
}


def main() -> int:
    payload = json.loads(COVERAGE.read_text())
    collected = subprocess.run(
        [str(PY_BIN), "-m", "pytest", "tests/test_lab08_factorial.py", "--collect-only", "-q",
         "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=1800).stdout
    known = {f"tests/{ln.strip().split('tests/', 1)[-1]}" for ln in collected.splitlines()
             if "::" in ln}
    known |= {node.split("[")[0] for node in known}

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
            record.pop("partially_discharged_by", None)
            record["owning_phase"] = "LAB-08"
    payload["as_of_phase"] = "LAB-08"
    payload["counts"] = dict(Counter(r["status"] for r in payload["requirements"]))
    COVERAGE.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"coverage as of {payload['as_of_phase']}: {payload['counts']}")
    for record in payload["requirements"]:
        if record["id"] in COVERED:
            print(f"   {record['id']} {record['status']:<10} {len(record['tests'])} tests  "
                  f"{record['title'][:46]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
