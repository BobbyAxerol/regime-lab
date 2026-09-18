#!/usr/bin/env python
"""Run the whole of LAB-05 in dependency order and report the exit gate."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PYTHON = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"

STEPS = [
    ("gate    preflight (prerequisite)", ["scripts/preflight.py"], 1800),
    ("gate    read-lock recheck", ["scripts/recheck_readlock.py"], 3600),
    ("L05.2/6/7 acceptance checks T37-T44 and synthetic worlds",
     ["scripts/regime_selftest.py"], 3600),
    ("L05.1/3/4/5 fit on the development role and emit causally",
     ["scripts/fit_regime_model.py"], 10800),
    ("audit   T37-T44 coverage", ["scripts/update_coverage_lab05.py"], 1800),
    ("audit   clause-by-clause", ["scripts/audit_lab05.py"], 3600),
    ("report  glossaries", ["scripts/ensure_report_glossaries.py"], 600),
    ("report  lab05_report.md", ["scripts/write_lab05_report.py"], 900),
]


def main() -> int:
    failures: list[str] = []
    for title, argv, timeout in STEPS:
        print(f"\n=== {title} ===", flush=True)
        done = subprocess.run([str(PYTHON), "-W", "ignore", *argv], cwd=LAB_ROOT,
                              capture_output=True, text=True, timeout=timeout)
        for line in [ln for ln in done.stdout.strip().splitlines() if ln][-12:]:
            print(f"    {line}")
        if done.returncode != 0:
            failures.append(title)
            print(f"    FAILED rc={done.returncode}\n    {done.stderr.strip()[-800:]}")
            break

    print("\n=== acceptance tests ===")
    tests = subprocess.run([str(PYTHON), "-m", "pytest", "tests", "-q", "-p", "no:warnings"],
                           cwd=LAB_ROOT, capture_output=True, text=True, timeout=5400)
    summary = [ln for ln in tests.stdout.strip().splitlines()
               if "passed" in ln or "failed" in ln]
    print(f"    {summary[-1] if summary else 'no pytest summary'}")
    if tests.returncode != 0:
        failures.append("acceptance tests")

    print("\n=== LAB-05 exit gate ===")
    audit_path = LAB_ROOT / "configs" / "lab05_task_audit.json"
    selftest_path = LAB_ROOT / "configs" / "lab05_selftest.json"
    registry_path = LAB_ROOT / "configs" / "lab05_regime_model_registry.json"

    if audit_path.is_file():
        audit = json.loads(audit_path.read_text())
        print(f"    clause audit         : {audit['tasks_done']}/{audit['tasks_total']} DONE")
    if selftest_path.is_file():
        checks = json.loads(selftest_path.read_text())["acceptance_checks"]
        print(f"    T37 DP == brute force: {checks['T37']['all_endpoint_costs_match']}")
        print(f"    T38 batch == stream  : {checks['T38']['all_states_identical']}")
        print(f"    T39 detector works   : {checks['T39']['detector_is_meaningful']}")
        print(f"    T43 inference cannot refit: "
              f"{checks['T43']['inference_path_calls_no_fit']}")
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text())
        mappings = registry["namespace_mappings"]
        print(f"    fits                 : {len(registry['models'])}, "
              f"namespace maps {len(mappings)}, "
              f"unmapped in {sum(1 for m in mappings if not m['all_states_mapped'])}")
        print(f"    market transition claimed by a mapping: "
              f"{any(m['is_market_transition'] for m in mappings)}")
    else:
        failures.append("regime model registry missing")

    if failures:
        print(f"\n    STATUS: BLOCKED — {failures}")
        return 1
    print("\n    STATUS: LAB-05 complete (TECHNICAL pass only — no predictive or financial "
          "value is claimed). LAB-06 requires explicit user approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
