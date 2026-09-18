#!/usr/bin/env python
"""Run the whole of LAB-06 in dependency order and report the exit gate."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PYTHON = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"

STEPS = [
    ("gate    preflight (prerequisite)", ["scripts/preflight.py"], 1800),
    ("gate    read-lock recheck", ["scripts/recheck_readlock.py"], 3600),
    ("L06.1-6 episodes, bank, response, decisions, clocks",
     ["scripts/run_response_policy.py"], 10800),
    ("audit   T45-T52 coverage", ["scripts/update_coverage_lab06.py"], 1800),
    ("audit   clause-by-clause against the pre-written checklist",
     ["scripts/audit_lab06.py"], 3600),
    ("report  glossaries", ["scripts/ensure_report_glossaries.py"], 600),
    ("report  lab06_report.md", ["scripts/write_lab06_report.py"], 900),
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

    print("\n=== LAB-06 exit gate ===")
    audit_path = LAB_ROOT / "configs" / "lab06_task_audit.json"
    ledger_path = LAB_ROOT / "configs" / "lab06_decision_ledger.json"
    spec_path = LAB_ROOT / "configs" / "lab06_policy_spec.json"

    if audit_path.is_file():
        audit = json.loads(audit_path.read_text())
        print(f"    clause audit          : {audit['tasks_done']}/{audit['tasks_total']} DONE")
        print(f"    checklist pre-written : {audit['checklist_written_before_code']}")
        if audit["clauses_without_an_evidence_pointer"]:
            failures.append("clauses without evidence")
    if ledger_path.is_file():
        ledger = json.loads(ledger_path.read_text())
        print(f"    decisions             : {ledger['decisions']} {ledger['counts']}")
        print(f"    every decision evidenced: "
              f"{ledger['every_decision_has_a_reason']} / cutoffs "
              f"{ledger['every_decision_records_its_cutoffs']}")
        if not (ledger["every_decision_has_a_reason"]
                and ledger["every_decision_records_its_cutoffs"]):
            failures.append("a decision lacks evidence or cutoffs")
    else:
        failures.append("decision ledger missing")
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text())
        counters = spec["clocks"]["counters"]
        print(f"    clock counters        : inference {counters['inference']}, "
              f"switch assessments {counters['switch_assessments']}, "
              f"switches {counters['switches_executed']}, "
              f"bank refreshes {counters['bank_refreshes']}, "
              f"retrains {counters['model_retrains']}")

    if failures:
        print(f"\n    STATUS: BLOCKED — {failures}")
        return 1
    print("\n    STATUS: LAB-06 complete. Every keep/switch carries evidence, cutoffs and "
          "consistent units; a zero-switch outcome is a valid technical result. LAB-07 requires "
          "explicit user approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
