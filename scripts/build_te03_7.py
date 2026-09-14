#!/usr/bin/env python3
"""Assemble the TE03.7 power/null calibration and full-path control evidence.

The statistical calibration payload is copied as measured, with the positive
and null controls read out of its own conditions. The engine full-path control
ledger is read from the run SQLite; when it cannot complete inside the bounded
allocation the funnel keeps null counts plus the exact per-task reason, never a
zero-filled result.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import Ledger, digest, file_digest, read, save, utcnow  # noqa: E402

POWER_SCHEMA = "regime_lab.te03_power_null_calibration.v1"
CONTROLS_SCHEMA = "regime_lab.te03_full_path_controls.v1"
FUNNEL_SCHEMA = "regime_lab.te03_activation_funnel.v1"
FUNNEL_STEPS = ("valid_observations", "triggers", "searches", "different_params", "activated", "different_orders")


def reference(relative):
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit("missing build input: " + relative)
    return {"path": relative, "sha256": file_digest(path)}


def conditions(payload):
    rows = payload.get("conditions")
    if not isinstance(rows, list) or {row.get("true_effect_delta_units") for row in rows} != {0., 1., 2., 4.}:
        raise SystemExit("statistical calibration must carry the four registered effect worlds")
    for row in rows:
        if int(row.get("worlds", 0)) <= 0 or not row.get("wilson95"):
            raise SystemExit("statistical calibration conditions need nonvacuous worlds and Wilson intervals")
    return {float(row["true_effect_delta_units"]): row for row in rows}


def power_artifact(calibration_ref, payload):
    by_effect = conditions(payload)
    positive = by_effect[2.]
    nulls = [by_effect[0.], by_effect[1.]]
    positive_power = [float(x) for x in positive["per_hypothesis_power"]]
    recovered = min(positive_power) >= .8
    null_upper = max(float(row["wilson95"][1]) for row in nulls)
    false_positive = null_upper > .08
    return {
        "schema": POWER_SCHEMA,
        "lab_run_id": "TE03-7-POWER-ARTIFACTS-01",
        "created_at": utcnow(),
        "scope": ("statistical calibration of the registered four-hypothesis family with known synthetic effects; "
                  "NOT the engine full-path control and NOT a market effect"),
        "source": {**calibration_ref, "status": payload.get("status"), "engine_runs": payload.get("engine_runs"),
                   "scope": payload.get("scope"), "full_pipeline_calibration": payload.get("full_pipeline_calibration")},
        "conditions": payload["conditions"],
        "positive_control": {
            "world": "KNOWN_EFFECT_PLUS_2_DELTA_SYNTHETIC_UNITS",
            "worlds": int(positive["worlds"]),
            "family_rejections": int(positive["family_rejections"]),
            "family_rate": float(positive["rate"]),
            "family_wilson95": positive["wilson95"],
            "per_hypothesis_power": positive_power,
            "recovered": recovered,
            "status": "RECOVERED" if recovered else "NOT_RECOVERED",
            "denominator": int(positive["worlds"]),
        },
        "null_control": {
            "worlds": [{"true_effect_delta_units": float(row["true_effect_delta_units"]),
                        "family_rejections": int(row["family_rejections"]), "rate": float(row["rate"]),
                        "wilson95": row["wilson95"], "worlds": int(row["worlds"]),
                        "denominator": int(row["worlds"])} for row in nulls],
            "maximum_family_wilson_upper": null_upper,
            "false_positive": false_positive,
            "status": "FALSE_POSITIVE_RISK" if false_positive else "NO_FALSE_POSITIVE_AT_REGISTERED_TOLERANCE",
            "tolerance": .08,
        },
        "status": payload.get("status"),
        "delayed_risk_controls": {
            "status": "TE04_SCOPE_NOT_STARTED",
            "reason": "delayed-state, placebo-tape and risk-only controls are assigned to TE-04.4/R5; TE-04 stays "
                      "blocked until the TE-02/03 gates close",
        },
        "engine_runs": int(payload.get("engine_runs", 0)),
    }


def ledger_state(run_id):
    directory = ROOT / "evidence/time_edge_validation_v4/runs" / run_id
    if not (directory / "job.json").is_file():
        raise SystemExit("unknown controls run: " + run_id)
    job = read(directory / "job.json")
    con = sqlite3.connect(directory / "ledger.sqlite")
    rows = con.execute("SELECT task,status,wall,reserved,reason FROM attempt ORDER BY started").fetchall()
    con.close()
    attempts = {}
    for task, status, wall, reserved, reason in rows:
        attempts.setdefault(task, []).append({"status": status, "wall": wall, "reserved": reserved, "reason": reason})
    logs = sorted(directory.glob("console-run-*.log"))
    stop = None
    if logs:
        lines = [line.strip() for line in logs[-1].read_text().splitlines() if line.strip()]
        stop = lines[-1] if lines else None
    return job, attempts, stop


def task_attempts(job, attempts, task):
    return attempts.get(digest({"identity": {"job_hash": digest(job)}, "task": task}), [])


def controls_artifact(run_id, allocation_id, profile_ref, profile):
    job, attempts, stop = ledger_state(run_id)
    directory = ROOT / "evidence/time_edge_validation_v4/runs" / run_id
    tasks = []
    outcome = None
    for task in job["tasks"]:
        rows = task_attempts(job, attempts, task)
        terminal = rows[-1] if rows else None
        if terminal is None:
            status = "NOT_RUN_BUDGET"
            reason = "task never launched: the bounded allocation/run stopped before this task"
        else:
            status = terminal["status"]
            reason = terminal["reason"] or "unknown terminal reason"
        tasks.append({"task_id": task["task_id"], "condition": task["condition"], "seed": task["seed"],
                      "days": task["days"], "wall_cap_seconds": float(task.get("wall_seconds", job["task_wall_seconds"])),
                      "status": status, "reason": reason,
                      "wall_seconds": None if terminal is None or terminal["wall"] is None else float(terminal["wall"])})
        if status == "COMPLETE" and outcome is None:
            ledger = Ledger(directory, {"job_hash": digest(job)}, job["total_wall_seconds"])
            try:
                outcome = ledger.cached(task)
            finally:
                ledger.close()
    if outcome is not None and outcome.get("status") != "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED":
        raise SystemExit("completed control has an unexpected result status")
    funnel = {
        "schema": FUNNEL_SCHEMA,
        "cell_id": "A-SC/BTCUSDT",
        "steps": [{"step": name, "count": None,
                   "reason": "full-path control did not complete inside the bounded allocation; no measured count exists"}
                  for name in FUNNEL_STEPS],
        "status": "NOT_RUN_BUDGET",
        "condition": None,
    }
    if outcome is not None:
        counts = outcome["counts"]
        measured = {"valid_observations": outcome.get("eligible_emissions"), "triggers": outcome.get("triggers"),
                    "searches": counts.get("searches"), "different_params": outcome.get("distinct_regime_parameters"),
                    "activated": outcome.get("activations"), "different_orders": None}
        funnel = {"schema": FUNNEL_SCHEMA, "cell_id": outcome.get("cell_id"), "condition": outcome.get("condition"),
                  "steps": [{"step": name, "count": measured.get(name),
                             "reason": None if measured.get(name) is not None else "not exported by the full-control result"}
                            for name in FUNNEL_STEPS],
                  "status": "MEASURED", "truth_entered_learner": outcome.get("truth_entered_learner")}
    return {
        "schema": CONTROLS_SCHEMA,
        "lab_run_id": "TE03-7-CONTROLS-ARTIFACTS-01",
        "created_at": utcnow(),
        "scope": "TE03.7 engine full-path structural controls; structural opportunity and treatment reach only, never a known net learner 2-delta effect",
        "run_id": run_id,
        "allocation_id": allocation_id,
        "profile": profile_ref,
        "tasks": tasks,
        "planned_counts": profile.get("planned_counts"),
        "measured_basis": profile.get("projection"),
        "run_stop_reason": stop,
        "full_path_funnel": funnel,
        "truth_entered_learner": None if outcome is None else outcome.get("truth_entered_learner"),
        "boundary_power_qualification": "NOT_EVALUABLE_FROM_STRUCTURAL_WORLD_ALONE",
        "fabricated_fills": False,
        "status": "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED" if outcome is not None else "NOT_RUN_BUDGET",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration", default="evidence/time_edge_validation_v4/host-calibration-01.json")
    parser.add_argument("--controls-run", default="te-host-controls-01")
    parser.add_argument("--allocation-id", default="TE02-PILOT-R03")
    parser.add_argument("--profile", default="evidence/time_edge_validation_v4/profiles/te03-controls-measured-20260912-01.json")
    parser.add_argument("--output-power", default="evidence/time_edge_validation_v4/te03/te03_7_power.json")
    parser.add_argument("--output-controls", default="evidence/time_edge_validation_v4/te03/te03_7_controls.json")
    args = parser.parse_args()
    calibration_ref = reference(args.calibration)
    calibration = read(ROOT / args.calibration)
    power = power_artifact(calibration_ref, calibration)
    profile_ref = reference(args.profile)
    profile = read(ROOT / args.profile)
    controls = controls_artifact(args.controls_run, args.allocation_id, profile_ref, profile)
    power_hash = save(ROOT / args.output_power, power)
    controls_hash = save(ROOT / args.output_controls, controls)
    print(json.dumps({"power": {"path": args.output_power, "sha256": power_hash,
                                "status": power["status"], "positive": power["positive_control"]["status"],
                                "null": power["null_control"]["status"]},
                      "controls": {"path": args.output_controls, "sha256": controls_hash,
                                   "status": controls["status"], "funnel": controls["full_path_funnel"]["status"]}}, indent=1))


if __name__ == "__main__":
    main()
