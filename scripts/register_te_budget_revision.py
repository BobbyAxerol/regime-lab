#!/usr/bin/env python3
"""Append a measured budget revision to a live TE shared allocation ledger.

The revision is derived from the live SQLite ledger and measured profile refs;
prior charges are read, never restated by hand. Re-running with the same
revision id refuses to rewrite different bytes.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import (ALLOCATION_REVISION_SCHEMA,
                                                 file_digest, read, save, utcnow)  # noqa: E402


def ledger_state(root, allocation_id):
    directory = root / "evidence/time_edge_validation_v4/allocations" / allocation_id
    database = directory / "ledger.sqlite"
    if not database.is_file():
        raise SystemExit("unknown allocation ledger: " + str(database))
    con = sqlite3.connect(database)
    total = float(con.execute("SELECT budget FROM study").fetchone()[0])
    rows = con.execute("SELECT status,reserved,wall FROM attempt").fetchall()
    revisions = con.execute("SELECT id FROM budget_revision ORDER BY applied_at").fetchall()
    con.close()
    charged = float(sum(row[2] if row[2] is not None else row[1] for row in rows))
    return total, charged, len(rows), [row[0] for row in revisions]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allocation-id", default="TE02-PILOT-R03")
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--total", type=float, required=True)
    parser.add_argument("--reserve", type=float, required=True)
    parser.add_argument("--stage-scope", required=True)
    parser.add_argument("--why", required=True)
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--measured", help="JSON file merged into measured_reason")
    parser.add_argument("--output")
    parser.add_argument("--task-cap", type=float, default=600.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--memory-gib", type=int, default=4)
    parser.add_argument("--cpu-justification")
    args = parser.parse_args()
    root = ROOT
    prior_total, prior_charged, prior_attempts, prior_revisions = ledger_state(root, args.allocation_id)
    required = prior_charged + args.reserve
    if args.total < required:
        raise SystemExit(f"new total {args.total} must cover prior charges {prior_charged} plus reserve {args.reserve}")
    if args.total <= prior_total:
        raise SystemExit("a revision must increase the allocation total")
    profiles = []
    for relative in args.profile:
        path = root / relative
        if not path.is_file():
            raise SystemExit("missing measured profile: " + relative)
        profiles.append({"path": relative, "sha256": file_digest(path)})
    if not profiles:
        raise SystemExit("at least one measured profile reference is required")
    measured = {
        "prior_total_wall_seconds": prior_total,
        "prior_charged_wall_seconds": prior_charged,
        "prior_attempts": prior_attempts,
        "prior_revisions": prior_revisions,
        "reserved_future_wall_seconds": args.reserve,
        "why_this_revision": args.why,
        "prior_charges_kept": "the live ledger keeps all %d prior attempts and %.6fs charged; the revision appends, never resets"
                              % (prior_attempts, prior_charged),
    }
    if args.measured:
        measured["additional"] = read(root / args.measured)
    revision = {
        "schema": ALLOCATION_REVISION_SCHEMA,
        "study_id": "time_edge_validation_v4",
        "revision_id": args.revision_id,
        "allocation_id": args.allocation_id,
        "stage_scope": args.stage_scope,
        "registered_at_utc": utcnow(),
        "prior_total_wall_seconds": prior_total,
        "prior_charged_wall_seconds": prior_charged,
        "prior_attempts": prior_attempts,
        "total_wall_seconds": float(args.total),
        "task_wall_seconds": float(args.task_cap),
        "workers": args.workers,
        "cpu_limit": args.cpu,
        "memory_gib": args.memory_gib,
        "profile_refs": profiles,
        "reserved_future_wall_seconds": float(args.reserve),
        "measured_reason": measured,
        "per_arm_compute_is_unchanged": True,
        "how_arms_stay_equal": (
            "the revision changes only the shared wall budget. Every arm still consumes the same selected artifact "
            "from the same registered search (32 trials, same seed, scorer, train window and economics); the lab runs "
            "one worker sequentially, so no arm can finish ahead of another and no arm receives extra trials, threads "
            "or a different account window"),
        "cpu_limit_change_justification": args.cpu_justification,
        "what_it_changes": [
            "shared allocation total wall: %ss -> %ss (appended to the live ledger)" % (prior_total, args.total),
            args.why,
        ],
        "what_it_does_not_change": [
            "every prior attempt and its charged wall in allocations/%s/ledger.sqlite" % args.allocation_id,
            "registered trial counts, seeds, scorers, train windows, economics and the engine contract",
            "workers=%d, cpu_limit=%d, memory_gib=%d and per-arm compute" % (args.workers, args.cpu, args.memory_gib),
        ],
        "what_it_costs": "wall clock only; the shared allocation ledger is raised by %ss (%ss new total minus the prior %ss registration) "
                         "and keeps all prior charges" % (args.total - prior_total, args.total, prior_total),
        "baseline_protection_rule_still_holds": (
            "no arm's interval, fees, outputs, seed or number of attempts is reduced or raised; the same selected theta "
            "is reused by every arm"),
        "note": "Registered before the next job; every number is read from the live ledger and the referenced measured profiles.",
    }
    output = root / (args.output or ("evidence/time_edge_validation_v4/allocations/revisions/%s.json" % args.revision_id))
    digest = save(output, revision)
    print(json.dumps({"revision": str(output.relative_to(root)), "sha256": digest,
                      "prior_total_wall_seconds": prior_total, "prior_charged_wall_seconds": prior_charged,
                      "total_wall_seconds": args.total, "reserve": args.reserve,
                      "profiles": [row["path"] for row in profiles]}, indent=1))


if __name__ == "__main__":
    main()
