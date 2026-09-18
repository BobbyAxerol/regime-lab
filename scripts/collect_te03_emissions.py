#!/usr/bin/env python3
"""Extract the deployed emissions/registry payload from a completed models run.

The payload is read through the run ledger cache (hash verified), so the
emission tape is exactly the bytes the isolated worker published.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import Ledger, digest, read, save  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-id", default="deployed-emissions")
    parser.add_argument("--output", required=True)
    parser.add_argument("--lab-run-id", default="TE03-EMISSIONS-02")
    args = parser.parse_args()
    directory = ROOT / "evidence/time_edge_validation_v4/runs" / args.run_id
    job = read(directory / "job.json")
    task = next((row for row in job["tasks"] if row["task_id"] == args.task_id), None)
    if task is None:
        raise SystemExit("unknown task in run: " + args.task_id)
    ledger = Ledger(directory, {"job_hash": digest(job)}, job["total_wall_seconds"])
    try:
        result = ledger.cached(task)
        key = digest({"identity": ledger.identity, "task": task})
        attempt = next(row for row in reversed(ledger.status()["attempts"])
                       if row["task"] == key and row["status"] == "COMPLETE")
    finally:
        ledger.close()
    if result is None or "emissions" not in result:
        raise SystemExit("no completed emissions task output")
    payload = {
        "lab_run_id": args.lab_run_id,
        "source_identity": job["source_identity"],
        "source_refs": [{"path": str((directory / attempt["result_path"]).relative_to(ROOT)),
                         "sha256": attempt["result_hash"]}],
        "emissions": result["emissions"],
        "model_registry": result["model_registry"],
        "emit_wall_seconds": result.get("measured_wall_seconds"),
    }
    output = ROOT / args.output
    digest_value = save(output, payload)
    print(json.dumps({"path": args.output, "sha256": digest_value, "emissions": len(payload["emissions"]),
                      "models": len(payload["model_registry"])}, indent=1))


if __name__ == "__main__":
    main()
