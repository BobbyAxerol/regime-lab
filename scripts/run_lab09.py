#!/usr/bin/env python
"""Run the whole of LAB-09 in dependency order and report the exit gate.

The order is not a convenience. The unlock has to be stamped before the state
provider for the interval is fitted; the provider before the frozen run; the run
before anything that measures it; and the claim last, because it reads every one
of them. A step that runs out of order would either read a missing artifact or,
worse, read a stale one.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PYTHON = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")

STEPS = [
    ("gate    preflight (prerequisite)", ["scripts/preflight.py"], 1800),
    ("gate    read-lock recheck", ["scripts/recheck_readlock.py"], 3600),
    ("L09.1   unlock the confirmation interval", ["scripts/unlock_lab09_confirmation.py"], 600),
    *[(f"L09.2a  state provider {symbol}",
       ["scripts/fit_regime_model.py", "--symbol", symbol, "--role", "confirmation",
        "--artifact-prefix", f"lab09_{symbol.lower()}"], 7200) for symbol in SYMBOLS],
    ("L09.6   verify the cost binding", ["scripts/verify_cost_binding.py"], 1800),
    ("L09.3/6 replay development, calibrate the block length",
     ["scripts/replay_lab08_development.py"], 10800),
    ("L09.2b  the frozen protocol on the confirmation interval",
     ["scripts/run_lab09_confirmation.py"], 43200),
    ("L09.4   cost and information stress", ["scripts/run_lab09_stress.py"], 21600),
    ("L09.5a  the policy on the confirmation interval",
     ["scripts/run_response_policy.py", "--role", "confirmation"], 14400),
    ("L09.7a  group ablation inside the interval", ["scripts/ablate_lab09_states.py"], 3600),
    ("L09.5b  support and novelty", ["scripts/run_lab09_support.py"], 1800),
    ("L09.6   fee sensitivity of the SELECTION", ["scripts/probe_fee_sensitivity.py"], 7200),
    ("L09.3/6/7 uncertainty, reconciliation and the claim",
     ["scripts/analyse_lab09_confirmation.py"], 7200),
    ("OUT.6/7 leakage/contamination and limitations",
     ["scripts/write_lab09_limitations.py"], 900),
    ("audit   guide 4.3 execution resolution", ["scripts/verify_execution_resolution.py"], 3600),
    ("audit   T62-T63 coverage", ["scripts/update_coverage_lab09.py"], 1800),
    ("audit   corrections", ["scripts/build_correction_ledger.py"], 1800),
    ("audit   cross-phase evidence pointers", ["scripts/audit_evidence_pointers.py"], 3600),
    ("audit   guide subsections nothing claims",
     ["scripts/audit_guide_section_coverage.py"], 3600),
    ("audit   assertion vacuity", ["scripts/audit_assertion_vacuity.py"], 7200),
    ("audit   clause-by-clause against the pre-written checklist",
     ["scripts/audit_lab09.py"], 3600),
    ("report  glossaries", ["scripts/ensure_report_glossaries.py"], 600),
    ("report  lab09_report.md", ["scripts/write_lab09_report.py"], 900),
]

#: The registered budget is ONE worker. Every step above is sequential for that
#: reason, and running two of them at once is not a speed-up -- it is a budget
#: violation, and on this machine it also OOM-killed a nine-hour run once.
ONE_AT_A_TIME = True


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
                           cwd=LAB_ROOT, capture_output=True, text=True, timeout=7200)
    summary = [ln for ln in tests.stdout.strip().splitlines()
               if "passed" in ln or "failed" in ln]
    print(f"    {summary[-1] if summary else 'no pytest summary'}")
    if tests.returncode != 0:
        failures.append("acceptance tests")

    print("\n=== LAB-09 exit gate ===")
    audit = LAB_ROOT / "configs" / "lab09_task_audit.json"
    claim = LAB_ROOT / "configs" / "lab09_claim_report.json"
    if audit.is_file():
        document = json.loads(audit.read_text())
        print(f"    clause audit          : {document['tasks_done']}/{document['tasks_total']} DONE")
        print(f"    checklist pre-written : {document['checklist_written_before_code']}")
        print(f"    pointers resolved     : {document['evidence_pointers_are_resolved']}")
        if document["clauses_without_resolved_evidence"]:
            failures.append("clauses without resolved evidence")
    if claim.is_file():
        document = json.loads(claim.read_text())
        print(f"    conclusion level      : {document['conclusion_level']}")
        print(f"    confirms development  : {document['confirms_the_development_outcome']}")
        for blocker in document["blockers"]:
            print(f"    blocker               : {blocker[:110]}")
    print(f"\n    failures: {failures or 'none'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
