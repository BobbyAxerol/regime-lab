#!/usr/bin/env python
"""Record a revision to the registered OS resource budget.

Guide 10.5 and the registration itself: `registered_at_utc` is never re-stamped,
because that would destroy the evidence that the contract pre-dated the arm whose
cost it governs. A change to the budget is therefore an APPEND with its own
stamp, its reason, and what it does and does not affect.

This exists because the LAB-09 confirmation was measured at 24 minutes per cell
-- twelve selector cutoffs at 97 strategy evaluations each -- and the remaining
twelve cells would have taken close to five hours on one worker while three of
the machine's four cores sat idle.

What a second worker changes: the wall clock, and the `workers` figure in the
OPERATIONAL_POLICY report. What it does NOT change: any measured result. Cells
are independent, each is deterministic, and each is written to its own
checkpoint; sharding decides only WHICH process computes a cell, never what it
computes. The MATCHED_TOTAL_COMPUTE report -- unique evaluations, fold-bar
visits, probes, model fits, response evaluations -- is unaffected, because the
same work is done either way.

What it costs, and this is the real cost: LAB-08's wall-second figures were
measured at one worker, so the confirmation's per-cell wall seconds are no
longer comparable to the discovery's. That is stated rather than quietly
absorbed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
TARGET = LAB_ROOT / "configs" / "compute_budget_registration.json"


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    document = json.loads(TARGET.read_text())
    original = dict(document["os_resource_budget"])
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    cpu = int(sys.argv[2]) if len(sys.argv) > 2 else original["cpu_limit"]
    revisions = document.setdefault("os_resource_budget_revisions", [])
    if any(r["to"]["workers"] == workers and r["to"]["cpu_limit"] == cpu for r in revisions):
        print(f"the {workers}-worker / {cpu}-cpu revision is already recorded; not appending")
        return 0

    revised = {**original, "workers": workers, "cpu_limit": cpu}
    revisions.append({
        "revised_at_utc": utc_now_iso(),
        "phase": "LAB-09",
        "from": original,
        "to": revised,
        "requested_by": "the user, after the confirmation was measured at ~24 min per cell",
        "measured_reason": {
            "seconds_per_cell": 1439,
            "cutoffs_per_cell": 12,
            "strategy_evaluations_per_cutoff": 97,
            "why_twelve_and_not_six": (
                "LAB-08's arms A and B redeployed selections LAB-04 had already made. LAB-04 "
                "never ran on the confirmation interval, so the confirmation must select for A "
                "and B here too. That is the entire 2x difference against discovery"),
            "process_was_single_threaded": True,
            "cores_idle": 3,
        },
        "what_it_changes": [
            "the wall clock",
            "the `workers` figure in the OPERATIONAL_POLICY report",
        ],
        "what_it_does_not_change": [
            "any measured result: cells are independent, deterministic and checkpointed, and "
            "sharding decides only which process computes a cell",
            "MATCHED_TOTAL_COMPUTE: the same unique evaluations, fold-bar visits, probes, model "
            "fits and response evaluations are performed either way",
            "working_memory_gib: measured peak is 0.40 GiB per worker against a 4 GiB budget",
        ],
        "per_arm_compute_is_unchanged": True,
        "how_arms_stay_equal": (
            "a shard is a CELL boundary, never an arm boundary. All five arms of a cell run "
            "sequentially inside one process on one core, in the same order, on the same frame. "
            "No arm can finish ahead of another because none of them races another -- which is "
            "the thing guide L08.6 forbids buying with CPU"),
        "cpu_limit_change_justification": (
            None if cpu == original["cpu_limit"] else
            "the registered limit was 2 and the machine has 4 cores. Raising it to "
            f"{cpu} shortens the wall clock and nothing else; the lab processes are niced so the "
            "user's live data collectors preempt them, and the arms remain sequential within "
            "every cell. What is lost is the comparability of wall seconds against LAB-08, "
            "which the previous revision already recorded as lost"),
        "what_it_costs": (
            "LAB-08's wall-second figures were measured at one worker, so the confirmation's "
            "per-cell wall seconds are NOT comparable to the discovery's. Guide 10.5 forbids "
            "changing a baseline's conditions to flatter a new method; here the change flatters "
            "nobody -- it is the same arms on the same cells -- but the comparability is lost "
            "and is recorded as lost"),
        "baseline_protection_rule_still_holds": (
            "no arm was given more compute than another. Both shards run the same code on "
            "disjoint cells, and every arm inside a cell runs sequentially in one process"),
    })
    document["os_resource_budget"] = revised
    document["ledger_last_appended_utc"] = utc_now_iso()
    document["registered_at_utc"] = json.loads(TARGET.read_text())["registered_at_utc"]

    with writer.attempt("L09.budget_revision") as att:
        att.detail = {"from": original["workers"], "to": revised["workers"]}
    writer.write_config("compute_budget_registration.json", document)
    writer.write_json("compute_budget_registration.json", document,
                      schema=document["schema"])

    print(f"registered_at_utc preserved : {document['registered_at_utc']}")
    print(f"workers {original['workers']} -> {revised['workers']}  "
          f"(cpu_limit unchanged at {revised['cpu_limit']})")
    print(f"revisions recorded          : {len(revisions)}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
