#!/usr/bin/env python3
"""Register the TE-02 pilot allocation/task-cap revision (append-only).

The revision is derived from the measured selection profile and the live shared
allocation ledger: prior charges are read from the ledger, never re-stated by
hand, and the new total reserves the selection cap plus the remaining pilot
task caps. Re-running refuses to rewrite different bytes.
"""
import argparse
import json

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import (ALLOCATION_REVISION_SCHEMA, file_digest,
                                                 read, save, utcnow)  # noqa: E402

DEFAULT_PROFILE = "evidence/time_edge_validation_v4/profiles/te02-selection-profile-20260912-01.json"
DEFAULT_OUTPUT = "evidence/time_edge_validation_v4/allocations/revisions/TE02-PILOT-R03-REV01.json"
SELECTION_CAP = 2700.0
TASK_CAP = 600.0
NEW_TOTAL = 5400.0


def ledger_state(root, allocation_id):
    directory = root / "evidence/time_edge_validation_v4/allocations" / allocation_id
    con = sqlite3.connect(directory / "ledger.sqlite")
    total = float(con.execute("SELECT budget FROM study").fetchone()[0])
    rows = con.execute("SELECT status,reserved,wall FROM attempt").fetchall()
    con.close()
    charged = float(sum(r[2] if r[2] is not None else r[1] for r in rows))
    return total, charged, len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allocation-id", default="TE02-PILOT-R03")
    parser.add_argument("--revision-id", default="TE02-PILOT-R03-REV01")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--total", type=float, default=NEW_TOTAL)
    parser.add_argument("--reserve", type=float, default=SELECTION_CAP + 2 * TASK_CAP,
                        help="future wall this revision must reserve in addition to prior charges")
    parser.add_argument("--why", default="selection cap measured too small for the registered 32 trials")
    parser.add_argument("--extra", help="JSON file with additional measured_reason fields")
    args = parser.parse_args()
    root = ROOT
    profile_path = root / args.profile
    profile = read(profile_path)
    prior_total, prior_charged, prior_attempts = ledger_state(root, args.allocation_id)
    assert prior_charged + 1e-6 >= profile["allocation_state_at_profile"]["charged_wall_seconds"], \
        "live ledger charges went backwards; re-measure instead of restamping"
    projection = profile["extrapolation_to_32_trials"]["projected_seconds"]
    assert SELECTION_CAP > projection, "registered selection cap must exceed the measured projection"
    required = prior_charged + args.reserve
    assert args.total >= required, "new total must cover prior charges plus the registered reserve"
    revision = {
        "schema": ALLOCATION_REVISION_SCHEMA,
        "study_id": "time_edge_validation_v4",
        "revision_id": args.revision_id,
        "allocation_id": args.allocation_id,
        "stage_scope": "pilot",
        "registered_at_utc": utcnow(),
        "prior_total_wall_seconds": prior_total,
        "prior_charged_wall_seconds": prior_charged,
        "prior_attempts": prior_attempts,
        "total_wall_seconds": float(args.total),
        "task_wall_seconds": TASK_CAP,
        "selection_task_wall_seconds": SELECTION_CAP,
        "workers": 1,
        "cpu_limit": 2,
        "memory_gib": 4,
        "profile_refs": [{"path": args.profile, "sha256": file_digest(profile_path)}],
        "reserved_future_wall_seconds": args.reserve,
        "measured_reason": {
            "source": DEFAULT_PROFILE,
            "pilot_run": profile["lab_run_id"],
            "trials_configured": profile["selection_task"]["configured_optuna_trials"],
            "trials_completed_at_cap": profile["selection_task"]["trials_completed"],
            "cap_that_timed_out_seconds": profile["selection_task"]["cap_seconds"],
            "mean_candidate_engine_wall_seconds": profile["candidate_accounting"]["engine_wall_seconds"]["mean"],
            "projected_32_trial_seconds": projection,
            "selection_cap_seconds": SELECTION_CAP,
            "cap_over_projection_fraction": round(SELECTION_CAP / projection - 1.0, 4),
            "prior_charges_kept": "the live ledger keeps all %d prior attempts and %.6fs charged; the revision appends, never resets"
                                 % (prior_attempts, prior_charged),
            "why_not_fewer_trials": "the registered per-cutoff trial count is 32 (mode4_binding_r01 resolved_config); "
                                    "lowering it would be an unregistered fidelity reduction",
            "why_this_revision": args.why,
        },
        "per_arm_compute_is_unchanged": True,
        "how_arms_stay_equal": "selection is one shared artifact per cell: M4_CAL, M4_REGIME and M4_CAL_MATCHED all consume "
                               "the same selected parameters from the same 32-trial search, seed and train window. The pilot "
                               "runs one worker sequentially, so no arm can finish ahead of another and no arm receives extra "
                               "trials, threads or a different account window.",
        "cpu_limit_change_justification": None,
        "what_it_changes": [
            "shared allocation total wall: %ss -> %ss (appended to the live ledger)" % (prior_total, args.total),
            args.why,
        ],
        "what_it_does_not_change": [
            "registered 32 trials per cutoff, search seed, scorer, train window, economics and engine contract",
            "workers=1, cpu_limit=2, memory_gib=4 and per-arm compute",
            "every prior attempt and its charged wall in allocations/%s/ledger.sqlite" % args.allocation_id,
        ],
        "what_it_costs": "wall clock only; the shared allocation ledger is raised by %ss "
                         "(%ss new total minus the prior %ss registration) and keeps all prior charges"
                         % (args.total - prior_total, args.total, prior_total),
        "baseline_protection_rule_still_holds": "no arm's interval, fees, outputs, seed or number of attempts is reduced or "
                                                "raised; the same selected theta is reused by every arm",
        "note": "Registered before the next pilot job; pilot-07's measured profile is the justification. This is a budget "
                "revision, not a trial-budget change.",
    }
    if args.extra:
        revision["measured_reason"]["additional"] = read(root / args.extra)
    output = root / args.output
    h = save(output, revision)
    print(json.dumps({"revision": str(output.relative_to(root)), "sha256": h,
                      "prior_charged_wall_seconds": prior_charged, "total_wall_seconds": float(args.total),
                      "selection_task_wall_seconds": SELECTION_CAP, "projected_seconds": projection}, indent=2))


if __name__ == "__main__":
    main()
