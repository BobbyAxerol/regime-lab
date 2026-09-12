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
    args = parser.parse_args()
    root = ROOT
    profile_path = root / args.profile
    profile = read(profile_path)
    prior_total, prior_charged, prior_attempts = ledger_state(root, args.allocation_id)
    assert abs(prior_total - profile["allocation_state_at_profile"]["total_wall_seconds"]) < 1e-6, \
        "profile and live allocation total disagree"
    assert abs(prior_charged - profile["allocation_state_at_profile"]["charged_wall_seconds"]) < 1e-6, \
        "live ledger gained charges after the profile; re-measure instead of restamping"
    projection = profile["extrapolation_to_32_trials"]["projected_seconds"]
    assert SELECTION_CAP > projection, "registered selection cap must exceed the measured projection"
    required = prior_charged + SELECTION_CAP + 2 * TASK_CAP
    assert NEW_TOTAL >= required, "new total must reserve selection, audit and deployment caps"
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
        "total_wall_seconds": NEW_TOTAL,
        "task_wall_seconds": TASK_CAP,
        "selection_task_wall_seconds": SELECTION_CAP,
        "workers": 1,
        "cpu_limit": 2,
        "memory_gib": 4,
        "profile_refs": [{"path": args.profile, "sha256": file_digest(profile_path)}],
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
        },
        "per_arm_compute_is_unchanged": True,
        "how_arms_stay_equal": "selection is one shared artifact per cell: M4_CAL, M4_REGIME and M4_CAL_MATCHED all consume "
                               "the same selected parameters from the same 32-trial search, seed and train window. The pilot "
                               "runs one worker sequentially, so no arm can finish ahead of another and no arm receives extra "
                               "trials, threads or a different account window.",
        "cpu_limit_change_justification": None,
        "what_it_changes": [
            "selection task wall cap: 600s -> 2700s",
            "shared allocation total wall: 1800s -> 5400s (appended to the live ledger)",
        ],
        "what_it_does_not_change": [
            "registered 32 trials per cutoff, search seed, scorer, train window, economics and engine contract",
            "workers=1, cpu_limit=2, memory_gib=4 and per-arm compute",
            "every prior attempt and its charged wall in allocations/TE02-PILOT-R03/ledger.sqlite",
        ],
        "what_it_costs": "wall clock only; the shared allocation ledger is raised by 3600s "
                         "(5400s new total minus the prior 1800s registration) and keeps all prior charges",
        "baseline_protection_rule_still_holds": "no arm's interval, fees, outputs, seed or number of attempts is reduced or "
                                                "raised; the same selected theta is reused by every arm",
        "note": "Registered before pilot-08 ran; pilot-07's measured profile is the justification. This is a budget revision, "
                "not a trial-budget change.",
    }
    output = root / args.output
    h = save(output, revision)
    print(json.dumps({"revision": str(output.relative_to(root)), "sha256": h,
                      "prior_charged_wall_seconds": prior_charged, "total_wall_seconds": NEW_TOTAL,
                      "selection_task_wall_seconds": SELECTION_CAP, "projected_seconds": projection}, indent=2))


if __name__ == "__main__":
    main()
