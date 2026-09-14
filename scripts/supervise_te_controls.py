#!/usr/bin/env python3
"""Drive a TE controls job to completion with bounded, checkpointed attempts.

The full-path engine control is far larger than one task cap. Each attempt
resumes the nested stages the previous attempt published and charges only its
measured wall. The supervisor stops on completion, on budget exhaustion or on
a non-timeout terminal failure; it never rewrites evidence, never increases the
registered allocation and never hides a TIMED_OUT attempt.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.runtime import run_jobs  # noqa: E402
from crypto_regime_lab.time_edge.storage import EvidenceError, Ledger, digest, read  # noqa: E402

TIMEOUT_REASON = "task wall cap reached"


def task_states(directory, job):
    ledger = Ledger(directory, {"job_hash": digest(job)}, job["total_wall_seconds"])
    try:
        return {task["task_id"]: ledger.cached(task) is not None for task in job["tasks"]}
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    parser.add_argument("--max-attempts", type=int, default=64)
    args = parser.parse_args()
    job = read(ROOT / args.job)
    directory = ROOT / "evidence/time_edge_validation_v4/runs" / job["lab_run_id"]
    try:
        for attempt in range(1, args.max_attempts + 1):
            if (directory / "ledger.sqlite").is_file():
                states = task_states(directory, job)
                if states and all(states.values()):
                    print(json.dumps({"supervisor": "COMPLETE", "run_id": job["lab_run_id"],
                                      "attempts": attempt - 1, "tasks": states}))
                    return 0
            try:
                status = run_jobs(ROOT, job, retry_failed=True)
            except EvidenceError as exc:
                print(json.dumps({"supervisor": "STOPPED", "run_id": job["lab_run_id"],
                                  "attempt": attempt, "reason": f"{type(exc).__name__}: {exc}"}))
                return 3
            last = status["attempts"][-1] if status["attempts"] else None
            print(json.dumps({"supervisor": "ATTEMPT", "run_id": job["lab_run_id"], "attempt": attempt,
                              "charged_wall_seconds": status["charged_wall_seconds"],
                              "last_status": None if last is None else last["status"],
                              "last_reason": None if last is None else last["reason"]}), flush=True)
            if last is not None and last["status"] != "COMPLETE" and last["reason"] != TIMEOUT_REASON:
                print(json.dumps({"supervisor": "STOPPED", "run_id": job["lab_run_id"],
                                  "attempt": attempt, "last": last}))
                return 3
        print(json.dumps({"supervisor": "INCOMPLETE", "run_id": job["lab_run_id"],
                          "reason": "max attempts reached without completion"}))
        return 3
    except EvidenceError as exc:
        print(json.dumps({"supervisor": "STOPPED", "run_id": job["lab_run_id"],
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
