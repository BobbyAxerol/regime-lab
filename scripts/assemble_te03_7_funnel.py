#!/usr/bin/env python
"""Assemble the TE-03.7 treatment funnel and the 32-trial bank selection.

Reads only measured artifacts of one structural-controls run: the run SQLite
ledger, its job and each shard's sealed nested stages. A completed shard exports
the six registered funnel steps with measured counts and denominators; an
incomplete shard exports null counts with the exact reason plus its sealed
partial stage counts. The bank selection exports params, objective, components
and the selected candidate's real fills. Nothing is zero-filled, no fill is
fabricated, and every step not materialized carries a denominator reason.

The funnel rules, partial-stage reading and gate booleans are the canonical
``scripts/build_te03_7.py`` semantics, imported so the two artifacts cannot
drift apart.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(LAB / "src"))

import build_te03_7 as canonical  # noqa: E402
from crypto_regime_lab.time_edge.storage import digest, file_digest, read, save, utcnow  # noqa: E402

SCHEMA = "regime_lab.te03_7_funnel.v2"
POWER = "evidence/time_edge_validation_v4/te03/te03_7_power.json"
BINDING = "configs/time_edge_validation_v4/mode4_binding_r01.json"
NEVER_LAUNCHED = ("task never launched: the bounded run stopped before this shard; no attempt row "
                  "exists in this run ledger")


def reference(relative):
    path = LAB / relative
    return {"path": relative, "sha256": file_digest(path)} if path.is_file() else None


def shard_rows(run_id):
    """Per-shard terminal status, nested stage counts and sealed selections."""
    directory, job, attempts, stop = canonical.ledger_state(run_id)
    binding = read(LAB / BINDING)
    trials_configured = int(binding["resolved_config"]["optuna_trials"])
    shards, funnels, partials, selections = [], {}, [], []
    for task in job["tasks"]:
        terminal = canonical.task_attempts(job, attempts, task)[-1:]
        terminal = terminal[0] if terminal else None
        status = terminal["status"] if terminal else "NOT_RUN_BUDGET"
        reason = (terminal["reason"] if terminal else NEVER_LAUNCHED)
        wall = None if terminal is None else terminal["wall"]
        task_dir = directory / "tasks" / digest(task)
        stages = canonical.nested_stages(task_dir, task)
        end = (datetime(2019, 1, 1, tzinfo=timezone.utc) + timedelta(days=int(task["days"]))).isoformat()
        if status == "COMPLETE":
            outcome = canonical.outcome_for(directory, job, task)
            if outcome.get("status") != "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED":
                raise SystemExit("completed control has an unexpected result status")
            funnels[task["condition"]] = canonical.funnel_for(outcome, task_dir, condition=task["condition"], end=end)
        elif status in ("TIMED_OUT", "FAILED", "BLOCKED"):
            partials.append(canonical.partial_funnel(task, stages, reason))
        selection = canonical.selection_result(task_dir, task, trials_configured)
        if selection is not None:
            selection["shard_status"] = status
            selection["partial"] = status != "COMPLETE"
            selection["selection_complete"] = (selection["trials_completed"] == trials_configured == 32
                                               and selection["params"] is not None
                                               and selection["objective"] is not None)
            selections.append(selection)
        shards.append({
            "task_id": task["task_id"], "world": task.get("world"), "condition": task["condition"],
            "seed": task["seed"], "days": task["days"],
            "wall_cap_seconds": float(task.get("wall_seconds", job["task_wall_seconds"])),
            "status": status, "reason": reason, "wall_seconds": None if wall is None else float(wall),
            "measured_stages": stages,
        })
    if funnels and len(funnels) == len(job["tasks"]):
        status = "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED"
    elif funnels:
        status = "FULL_PATH_STRUCTURAL_CONTROL_PARTIAL"
    else:
        status = "NOT_RUN_BUDGET"
    return {"directory": directory, "job": job, "trials_configured": trials_configured, "shards": shards,
            "funnels_by_condition": funnels, "partial_funnels": partials, "selection": selections,
            "status": status, "stop": stop}


def p0_gate(controls_status, funnels, selections):
    controls = {"selection_results": selections, "full_path_funnels_by_condition": funnels,
                "fabricated_fills": False}
    gate = canonical.p0_gate(controls, read(LAB / POWER))
    gate["all_registered_shards_completed"] = controls_status == "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED"
    gate["funnel_steps"] = {condition: len(funnel["steps"]) for condition, funnel in funnels.items()}
    gate["shards_with_measured_funnel"] = len(funnels)
    return gate


def assemble_args(args):
    state = shard_rows(args.run_id)
    funnels = state["funnels_by_condition"]
    primary = next(iter(funnels.values())) if funnels else canonical.null_funnel(
        None, reason="no shard completed; the six funnel steps are not measurable from partial stages")
    payload = {
        "schema": SCHEMA,
        "created_at": utcnow(),
        "run_id": args.run_id,
        "supersedes": reference(args.supersedes) if args.supersedes else None,
        "status": state["status"],
        "task_dirs": len({row["task_id"] for row in state["shards"]}),
        "worlds": sum(row["measured_stages"]["worlds_generated"] for row in state["shards"]),
        "sealed_worlds": sum(row["measured_stages"]["worlds_generated"] for row in state["shards"]),
        "trials_configured": state["trials_configured"],
        "shards": state["shards"],
        "full_path_funnel": primary,
        "funnels_by_condition": funnels,
        "partial_funnels": state["partial_funnels"],
        "selection": state["selection"],
        "p0_gate": p0_gate(state["status"], funnels, state["selection"]),
        "run_stop_reason": state["stop"],
        "rule": ("denominator carried for every step; a step not measured is null with a reason and a "
                 "denominator reason, never zero-filled; the bank selection keeps real params, objective, "
                 "components and fills"),
    }
    output = args.output or f"evidence/time_edge_validation_v4/te03/te03_7_funnel_{args.run_id}.json"
    path = LAB / output
    digest_value = save(path, payload)
    print(json.dumps({"output": output, "sha256": digest_value, "status": payload["status"],
                      "funnels": {name: funnel["status"] for name, funnel in funnels.items()},
                      "partial_funnels": len(state["partial_funnels"]),
                      "selections": len(state["selection"]), "p0_gate": payload["p0_gate"]}, indent=1))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="te-host-controls-07")
    parser.add_argument("--output", default=None)
    parser.add_argument("--supersedes", default="evidence/time_edge_validation_v4/te03/te03_7_funnel_r3.json")
    args = parser.parse_args()
    return assemble_args(args)


if __name__ == "__main__":
    raise SystemExit(main())
