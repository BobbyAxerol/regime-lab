#!/usr/bin/env python
"""Run the whole of LAB-04 in dependency order and report the exit gate."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PYTHON = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"

STEPS = [
    ("gate    preflight (prerequisite)", ["scripts/preflight.py"], 1800),
    ("gate    read-lock recheck", ["scripts/recheck_readlock.py"], 3600),
    ("L04.1-4 installed selector, counterexamples, probes, parity",
     ["scripts/trace_installed_selector.py"], 5400),
    ("L04.5-6 calendar baseline arms A and B (20 cells)",
     ["scripts/run_calendar_baseline.py"], 28800),
    ("L04.6   rebuild the summary from cell checkpoints",
     ["scripts/summarize_calendar_baseline.py"], 1800),
    ("L04.3.8 registered probe-radius sensitivity",
     ["scripts/probe_radius_sensitivity.py"], 5400),
    ("verify  a committed cutoff still reproduces",
     ["scripts/verify_cell_reproducibility.py"], 3600),
    ("audit   T29-T36 coverage", ["scripts/update_coverage_lab04.py"], 1800),
    ("audit   clause-by-clause", ["scripts/audit_lab04.py"], 3600),
    ("report  lab04_report.md", ["scripts/write_lab04_report.py"], 900),
]


def main() -> int:
    failures: list[str] = []
    for title, argv, timeout in STEPS:
        print(f"\n=== {title} ===", flush=True)
        done = subprocess.run([str(PYTHON), "-W", "ignore", *argv], cwd=LAB_ROOT,
                              capture_output=True, text=True, timeout=timeout)
        for line in [ln for ln in done.stdout.strip().splitlines() if ln][-10:]:
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

    print("\n=== LAB-04 exit gate ===")
    audit_path = LAB_ROOT / "configs" / "lab04_task_audit.json"
    baseline_path = LAB_ROOT / "configs" / "lab04_calendar_baseline.json"
    trace_path = LAB_ROOT / "configs" / "lab04_installed_wfo_trace.json"

    if audit_path.is_file():
        audit = json.loads(audit_path.read_text())
        print(f"    clause audit        : {audit['tasks_done']}/{audit['tasks_total']} DONE")
    if trace_path.is_file():
        trace = json.loads(trace_path.read_text())
        print(f"    public route selector: {trace['public_route_default']['resolved_by']}")
        print(f"    legacy OOS modes     : "
              f"{trace['legacy_oos_labelling']['modes_declaring_oos_selection']}")
    if baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text())
        print(f"    A/B cells            : {baseline['cells_run']} run, "
              f"{baseline['cells_not_ready']} NOT_READY")
        print(f"    search budget        : "
              f"{baseline['search_effort']['unique_executions']} unique executions, "
              f"{baseline['search_effort']['candidate_episode_visits']} episode visits")
        print(f"    verdict              : {baseline['verdict']}")
    else:
        failures.append("calendar baseline artifact missing")

    if failures:
        print(f"\n    STATUS: BLOCKED — {failures}")
        return 1
    print("\n    STATUS: LAB-04 complete. LAB-05 requires explicit user approval before it starts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
