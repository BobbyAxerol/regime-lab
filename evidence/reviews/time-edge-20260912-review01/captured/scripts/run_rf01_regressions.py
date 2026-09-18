#!/usr/bin/env python
"""RF-01.4 — record the failing-before regression evidence.

Runs the RF-01 before-repair tests (and, with --full, the whole suite), then
writes the outcome into evidence/corrective_mode4_v3/RF-01/ together with the
probe -> finding -> acceptance mapping. Nothing is repaired here: the failures
are the phase's evidence that the findings are real on the audited source.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-01"
BEFORE_TESTS = "tests/mode4_corrective"

PROBE_MAP = [
    {"probe": "P01", "finding": "A01", "tests": ["T01", "T59"],
     "observed": "actual fee rate 0.0002 against the registered one-way 0.0004"},
    {"probe": "P02", "finding": "A02", "tests": ["T03", "T04"],
     "observed": "a version requested at bar 100 is active from bar 0"},
    {"probe": "P03", "finding": "A10", "tests": ["T29", "T30"],
     "observed": "namespace change plus decision_eligible=false still triggers a refit"},
    {"probe": "P04", "finding": "A11", "tests": ["T41", "T42"],
     "observed": "opposite centroids collapse to zero context distance"},
    {"probe": "P05", "finding": "A05", "tests": ["T15", "T16"],
     "observed": "all three searched HMA stop choices map to effective mode 1"},
    {"probe": "P06", "finding": "A03", "tests": ["T11", "T12"],
     "observed": "converged=False with unmapped intents still returns EVALUATED"},
    {"probe": "P07", "finding": "A03", "tests": ["T11"],
     "observed": "different exit price/qty at the same bar still marks converged"},
    {"probe": "P08", "finding": "A07", "tests": ["T51", "T52"],
     "observed": "a 1000 loss at a block boundary is reported as zero by both blocks"},
    {"probe": "P09", "finding": "A15", "tests": ["T59"],
     "observed": "the registered 0.64 bps/day omitted the 0.1 allocation factor"},
    {"probe": "P10", "finding": "A14", "tests": ["T44"],
     "observed": "adding a noise dimension to the target halves variance resolved"},
    {"probe": "P11", "finding": "A04", "tests": ["T18"],
     "observed": "a generated corrective EXIT follow-up is never applied"},
    {"probe": "P12", "finding": "A02", "tests": ["T04"],
     "observed": "the schedule uses the cutoff and ignores fit_ready_at"},
]

HARDCODED_PATH_FIXES = [
    {"path": "tests/test_lab04_evaluator.py", "from": "LAB_ROOT/environments/lab_venv/bin/python",
     "to": "sys.executable"},
    {"path": "scripts/audit_lab04.py", "from": "LAB_ROOT/environments/lab_venv/bin/python",
     "to": "sys.executable"},
    {"path": "scripts/audit_lab05.py", "from": "LAB_ROOT/environments/lab_venv/bin/python",
     "to": "sys.executable"},
    {"path": "scripts/audit_lab06.py", "from": "LAB_ROOT/environments/lab_venv/bin/python",
     "to": "sys.executable"},
    {"path": "scripts/audit_guard_strength.py", "from": "LAB_ROOT/environments/lab_venv/bin/python",
     "to": "pathlib.Path(sys.executable)"},
]


def run_pytest(target: str, verbose: bool) -> tuple[int, str]:
    argv = [sys.executable, "-m", "pytest", target, "--no-header", "-p", "no:cacheprovider"]
    if verbose:
        argv += ["-v", "--tb=short"]
    else:
        argv += ["-q", "--tb=no"]
    done = subprocess.run(argv, cwd=str(LAB_ROOT), capture_output=True, text=True, timeout=1800)
    return done.returncode, done.stdout + done.stderr


def parse_outcomes(output: str) -> list[dict]:
    outcomes = []
    pattern = re.compile(r"(test_\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)")
    for line in output.splitlines():
        match = pattern.search(line)
        if match:
            outcomes.append({"nodeid": match.group(1), "outcome": match.group(2)})
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="also record the full-suite summary")
    args = parser.parse_args()

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    now = utc_now_iso()

    before_code, before_output = run_pytest(BEFORE_TESTS, verbose=True)
    before_log = writer.run_dir / "regression_before_repair.log"
    before_log.write_text(before_output, encoding="utf-8")
    outcomes = parse_outcomes(before_output)
    counts: dict[str, int] = {}
    for record in outcomes:
        counts[record["outcome"]] = counts.get(record["outcome"], 0) + 1

    payload = {
        "schema": "regime_lab.rf01_regression_baseline.v3",
        "generated_at_utc": now,
        "phase": PHASE,
        "purpose": ("failing-before evidence: each FAILED test asserts the behaviour the repaired "
                    "pipeline must have, never that the bug is present"),
        "before_tests": {
            "path": BEFORE_TESTS,
            "returncode": before_code,
            "counts": counts,
            "outcomes": outcomes,
            "log": str(before_log.relative_to(LAB_ROOT)),
            "log_sha256": sha256_file(before_log),
        },
        "full_suite": None,
        "probe_map": PROBE_MAP,
        "probes_reproduced": {
            "results_dir": "evidence/corrective_mode4_v3/probe_reproduction_v1",
            "python": "3.12.13 (lab venv)",
            "note": "the restored audit probes reproduce P01-P12 on the audited source; not a market replay",
        },
        "hardcoded_path_fixes": HARDCODED_PATH_FIXES,
        "rule": ("a skipped test is not a pass; an environment skip is recorded with the reason "
                 "it did not run"),
    }

    if args.full:
        full_code, full_output = run_pytest("tests", verbose=False)
        summary = [line for line in full_output.splitlines()
                   if re.search(r"\d+ (passed|failed|error|skipped)", line)]
        payload["full_suite"] = {
            "returncode": full_code,
            "summary": summary[-1] if summary else None,
            "failed_nodeids": [record["nodeid"] for record in parse_outcomes(full_output)
                               if record["outcome"] in {"FAILED", "ERROR"}],
        }
        payload["full_suite"]["log"] = f"{before_log.parent.name}/regression_full_suite.log"
        (writer.run_dir / "regression_full_suite.log").write_text(full_output, encoding="utf-8")
        payload["full_suite"]["log_sha256"] = sha256_file(writer.run_dir / "regression_full_suite.log")

    writer.write_json("regression_before_repair.json", payload, schema=payload["schema"])
    print(json.dumps({"before_counts": counts, "returncode": before_code,
                      "full_suite": payload["full_suite"]["summary"] if payload["full_suite"] else None},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
