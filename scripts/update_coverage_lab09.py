#!/usr/bin/env python
"""Move T62 and T63 to their honest LAB-09 status.

T64 (offline reproduction of the report and the run from committed sources) is
LAB-10's and stays NOT_YET_IMPLEMENTED here. Claiming it now because the report
happens to render would be exactly the kind of coverage inflation this file
exists to prevent.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PY_BIN = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"
COVERAGE = LAB_ROOT / "configs" / "acceptance_test_coverage.json"
C = "tests/test_lab09_confirmation.py::"
U = "tests/test_lab09_uncertainty.py::"

COVERED = {
    "T62": [f"{C}test_no_untested_cell_is_presented_as_evidence",
            f"{C}test_the_confirmation_runs_the_same_matrix",
            f"{C}test_a_missing_measurement_is_never_reported_as_a_negative_result",
            f"{C}test_the_scope_of_the_conclusion_is_explicit"],
    "T63": [f"{U}test_symbols_are_resampled_together_so_common_shocks_survive",
            f"{U}test_blocks_widen_the_interval_on_an_autocorrelated_series",
            f"{U}test_pairing_excludes_days_a_cell_was_not_live",
            f"{U}test_the_interval_refuses_a_window_too_short_for_its_blocks",
            f"{C}test_the_block_length_came_from_development"],
}
FILES = ["tests/test_lab09_confirmation.py", "tests/test_lab09_uncertainty.py"]


def main() -> int:
    payload = json.loads(COVERAGE.read_text())
    collected = subprocess.run(
        [str(PY_BIN), "-m", "pytest", *FILES, "--collect-only", "-q", "--no-header",
         "-p", "no:warnings"],
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
            record["owning_phase"] = "LAB-09"
    payload["as_of_phase"] = "LAB-09"
    payload["counts"] = dict(Counter(r["status"] for r in payload["requirements"]))
    COVERAGE.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"coverage as of {payload['as_of_phase']}: {payload['counts']}")
    for record in payload["requirements"]:
        if record["status"] != "COVERED":
            print(f"   {record['id']} {record['status']:<22} {record['title'][:52]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
