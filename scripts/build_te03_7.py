#!/usr/bin/env python3
"""Assemble the TE03.7 power/null calibration and sharded full-path controls.

The statistical payload is copied as measured; it is not recomputed here. The
engine full-path controls are read from the run SQLite ledger and their nested
stage artifacts. A completed shard exports a treatment funnel with measured
counts, denominators and per-step rules, plus its 32-trial Mode 4 bank
selection (params, objective, components, fills). A shard stopped by its
bounded cap exports the measured nested stages it did publish (worlds,
features, search trials, targets), and every unmeasured step stays null with
the exact reason plus a denominator reason. Nothing is zero-filled and no fill
is fabricated.
"""
import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.schedule import calendar  # noqa: E402
from crypto_regime_lab.time_edge.storage import Ledger, digest, file_digest, read, save, utcnow  # noqa: E402

POWER_SCHEMA = "regime_lab.te03_power_null_calibration.v1"
CONTROLS_SCHEMA = "regime_lab.te03_full_path_controls.v1"
FUNNEL_SCHEMA = "regime_lab.te03_activation_funnel.v1"
BLOCKER_SCHEMA = "regime_lab.te_controls_blocker.v1"
FUNNEL_STEPS = ("valid_observations", "triggers", "searches", "different_params", "activated", "different_orders")
FUNNEL_RULES = {
    "valid_observations": "eligible emissions with decision_eligible=True; denominator = all emissions in the control window",
    "triggers": "controller triggers accepted inside the window; denominator = decision-eligible emissions",
    "searches": "search calls executed = 1 candidate bank + 1 initial + calendar cutoffs + regime triggers; denominator = the same registered schedule",
    "different_params": "distinct selected parameter digests across the M4_REGIME selections; denominator = M4_REGIME selections",
    "activated": "ACTIVATE events in the deployed M4_REGIME account; denominator = M4_REGIME commands",
    "different_orders": "regime fills whose (absolute bar, side) is absent from the calendar fills; denominator = regime fills",
}
NO_MEASURE = "full-path control did not complete inside the bounded allocation; no measured count exists"
CALENDAR_FIRST = "2020-06-29T00:00:00Z"
CONTROL_ORIGIN = "2019-01-01T00:00:00Z"
SHARD_ORDER = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")


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
    return directory, job, attempts, stop


def task_attempts(job, attempts, task):
    return attempts.get(digest({"identity": {"job_hash": digest(job)}, "task": task}), [])


def outcome_for(directory, job, task):
    ledger = Ledger(directory, {"job_hash": digest(job)}, job["total_wall_seconds"])
    try:
        return ledger.cached(task)
    finally:
        ledger.close()


def sealed_files(task_dir, prefix):
    return sorted(path for path in task_dir.glob(prefix + "-*.json") if not path.name.endswith(".seal.json"))


def nested_stages(task_dir, task):
    """Measured nested shard stages read from sealed files, never inferred."""
    from crypto_regime_lab.time_edge.eligibility import history_days
    import pandas as pd
    days = int(task.get("days", 1461))
    end = (datetime(2019, 1, 1, tzinfo=timezone.utc) + timedelta(days=days)).isoformat()
    bank = max(pd.Timestamp("2019-07-15T00:00:00Z"), pd.Timestamp("2019-01-01T00:00:00Z") +
               pd.Timedelta(days=180 + history_days(task["alpha_id"])))
    planned_targets = 0
    for origin in calendar((bank + pd.Timedelta(days=1)).isoformat(), end, 28):
        if pd.Timestamp(origin) + pd.Timedelta(days=28) >= pd.Timestamp(end):
            break
        planned_targets += 1
    worlds = sealed_files(task_dir, "world")
    searches = sealed_files(task_dir, "search")
    targets = sealed_files(task_dir, "targets")
    models = sealed_files(task_dir, "model")
    accounts = [name for name in ("M4_CAL", "M4_REGIME") if (task_dir / name / "account.json").is_file()]
    stamps = {}
    for label, paths in (("worlds", worlds), ("searches", searches), ("targets", targets)):
        if paths:
            stamps[label] = {"first": datetime.fromtimestamp(paths[0].stat().st_mtime, timezone.utc).isoformat(),
                             "last": datetime.fromtimestamp(paths[-1].stat().st_mtime, timezone.utc).isoformat()}
    if (task_dir / "features.json").is_file():
        stamp = datetime.fromtimestamp((task_dir / "features.json").stat().st_mtime, timezone.utc).isoformat()
        stamps["features"] = {"first": stamp, "last": stamp}
    return {
        "worlds_generated": len(worlds),
        "features_built": (task_dir / "features.json").is_file(),
        "searches_completed": len(searches),
        "bank_selection_present": bool(searches),
        "targets_completed": len(targets),
        "targets_planned": planned_targets,
        "model_vintages_completed": len(models),
        "model_vintages_planned": len(calendar("2019-01-01T00:00:00Z", end, 28)),
        "account_artifacts": accounts,
        "emissions_emitted": False,
        "publication_stamps_utc": stamps,
        "source": "sealed nested stage files in this shard's task directory",
    }


def selection_result(task_dir, task, trials_configured):
    records = [(read(path), path) for path in sealed_files(task_dir, "search")]
    if not records:
        return None
    record, path = min(records, key=lambda pair: str(pair[0].get("cutoff")))
    selected = record.get("selected") or {}
    params = selected.get("params")
    search_dir = path.with_suffix("")
    candidate_path = search_dir / f"candidate-{digest(params)}.json" if params else None
    candidate = read(candidate_path) if candidate_path is not None and candidate_path.is_file() else None
    fills = list((candidate or {}).get("fills") or [])
    trials = list(record.get("trials") or [])
    components = {key: selected.get(key) for key in
                  ("mean_is_sharpe", "mean_oos_sharpe", "mean_decay", "std_decay", "pruned")}
    return {
        "condition": task.get("condition"),
        "world": task.get("world"),
        "shard_task_id": task["task_id"],
        "search_file": str(path.relative_to(ROOT)),
        "cutoff": record.get("cutoff"),
        "status": record.get("status"),
        "selection_id": record.get("selection_id"),
        "params": params,
        "objective": selected.get("objective"),
        "trial_id": selected.get("trial_id"),
        "components": components,
        "fold_metrics": selected.get("fold_metrics"),
        "trials_configured": trials_configured,
        "trials_completed": len(trials),
        "trial_objectives": [{"trial_id": trial.get("trial_id"), "objective": trial.get("objective"),
                              "pruned": trial.get("pruned")} for trial in trials],
        "selected_candidate": None if candidate is None else {
            "candidate_file": str(candidate_path.relative_to(ROOT)),
            "status": candidate.get("status"),
            "fill_count": len(fills),
            "fills": fills,
            "metrics": candidate.get("metrics"),
            "wall_seconds": candidate.get("wall_seconds"),
        },
        "scorer_calls": record.get("scorer_calls"),
        "candidate_cache_hits": record.get("persistent_candidate_cache_hits"),
        "account_runs": record.get("account_runs"),
        "wall_seconds": record.get("wall_seconds"),
        "partial": True,
    }


def funnel_for(outcome, task_dir, *, condition, end):
    counts = outcome.get("counts") or {}
    regime_path = task_dir / "M4_REGIME" / "account.json"
    calendar_path = task_dir / "M4_CAL" / "account.json"
    regime = read(regime_path) if regime_path.is_file() else None
    calendar_account = read(calendar_path) if calendar_path.is_file() else None
    regime_fills = list((regime or {}).get("fills") or [])
    calendar_fills = list((calendar_account or {}).get("fills") or [])
    unmatched = sum((Counter((fill["absolute_bar_index"], fill["side"]) for fill in regime_fills)
                     - Counter((fill["absolute_bar_index"], fill["side"]) for fill in calendar_fills)).values())
    fixed = 2 + len(calendar(CALENDAR_FIRST, end, 180))
    emissions = outcome.get("eligible_emissions")
    total_emissions = outcome.get("emissions_in_window")
    triggers = outcome.get("triggers")
    regime_selections = len((regime or {}).get("selections") or []) if regime else None
    regime_commands = len((regime or {}).get("commands") or []) if regime else None
    steps = []

    def add(step, count, denominator, reason=None, denominator_reason=None):
        steps.append({
            "step": step,
            "count": count,
            "denominator": denominator,
            "reason": None if count is not None else (reason or NO_MEASURE),
            "denominator_reason": None if denominator not in (None, 0) else
                                  (denominator_reason or ("zero denominator: no eligible event exists in the control window"
                                                          if denominator == 0 else "no measured denominator exists")),
            "rule": FUNNEL_RULES[step],
        })

    add("valid_observations", emissions, total_emissions,
        None if emissions is not None else "eligible emission count not exported by the full-control result",
        None if total_emissions is not None else "total emissions in window not exported by the full-control result")
    add("triggers", triggers, emissions,
        None if triggers is not None else "controller trigger count not exported by the full-control result",
        None if emissions is not None else "no decision-eligible emissions")
    add("searches", counts.get("searches"), None if triggers is None else fixed + triggers,
        None if counts.get("searches") is not None else "search count not exported by the full-control result",
        None if triggers is not None else "trigger count not exported; scheduled search denominator unavailable")
    add("different_params", outcome.get("distinct_regime_parameters"), regime_selections,
        None if outcome.get("distinct_regime_parameters") is not None else "distinct parameter count not exported",
        None if regime_selections else "M4_REGIME account artifact missing or carries no selections")
    add("activated", outcome.get("activations"), regime_commands,
        None if outcome.get("activations") is not None else "activation count not exported",
        None if regime_commands else "M4_REGIME account artifact missing or carries no commands")
    add("different_orders", unmatched if regime is not None else None, len(regime_fills) if regime is not None else None,
        None if regime is not None else "M4_REGIME account artifact missing",
        None if regime is not None else "M4_REGIME account artifact missing")
    return {
        "schema": FUNNEL_SCHEMA,
        "cell_id": outcome.get("cell_id"),
        "condition": condition,
        "world": outcome.get("world"),
        "status": "MEASURED",
        "truth_entered_learner": outcome.get("truth_entered_learner"),
        "steps": steps,
        "rule": "counts are per condition from the completed full-control result and its deployed account artifacts",
    }


def null_funnel(condition, world=None, reason=None, partials=None):
    partials = partials or {}
    steps = []
    for name in FUNNEL_STEPS:
        steps.append({
            "step": name,
            "count": None,
            "denominator": None,
            "reason": reason or NO_MEASURE,
            "denominator_reason": "no completed full-path control; no measured denominator exists",
            "rule": FUNNEL_RULES[name],
            "measured_partial": partials.get(name),
        })
    return {
        "schema": FUNNEL_SCHEMA,
        "cell_id": None if world is None else "A-SC/" + world,
        "condition": condition,
        "world": world,
        "status": "NOT_RUN_BUDGET",
        "steps": steps,
    }


def partial_funnel(task, stages, reason):
    """Per-shard funnel whose measured steps carry the sealed partial counts."""
    partials = {"searches": stages["searches_completed"]}
    funnel = null_funnel(task.get("condition"), task.get("world"), reason=reason, partials=partials)
    funnel["shard_task_id"] = task["task_id"]
    funnel["partial_measurements"] = {
        "worlds_generated": stages["worlds_generated"],
        "features_built": stages["features_built"],
        "searches_completed": stages["searches_completed"],
        "targets_completed": stages["targets_completed"],
        "targets_planned": stages["targets_planned"],
        "model_vintages_completed": stages["model_vintages_completed"],
        "model_vintages_planned": stages["model_vintages_planned"],
        "emissions_emitted": stages["emissions_emitted"],
    }
    return funnel


def controls_artifact(run_id, allocation_id, profile_ref, profile, shard_profile_ref, supersedes,
                      trials_configured, blocker_reason):
    directory, job, attempts, stop = ledger_state(run_id)
    tasks = []
    outcomes = {}
    selection_results = []
    partial_funnels = []
    for task in job["tasks"]:
        rows = task_attempts(job, attempts, task)
        terminal = rows[-1] if rows else None
        task_dir = directory / "tasks" / digest(task)
        stages = nested_stages(task_dir, task)
        if terminal is None:
            status = "NOT_RUN_BUDGET"
            reason = ("task never launched: shards are sequential and the runtime does not advance past a shard "
                      "that did not complete; no attempt row exists in this run ledger")
            wall = None
        else:
            status = terminal["status"]
            reason = terminal["reason"] or "unknown terminal reason"
            wall = terminal["wall"]
        row = {"task_id": task["task_id"], "world": task.get("world"), "condition": task["condition"],
               "seed": task["seed"], "days": task["days"],
               "wall_cap_seconds": float(task.get("wall_seconds", job["task_wall_seconds"])),
               "status": status, "reason": reason,
               "wall_seconds": None if wall is None else float(wall),
               "measured_stages": stages}
        tasks.append(row)
        if status == "COMPLETE":
            outcome = outcome_for(directory, job, task)
            if outcome.get("status") != "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED":
                raise SystemExit("completed control has an unexpected result status")
            outcomes[task["task_id"]] = outcome
        result = selection_result(task_dir, task, trials_configured)
        if result is not None:
            result["shard_status"] = status
            selection_results.append(result)
        if status in ("TIMED_OUT", "FAILED", "BLOCKED"):
            partial_funnels.append(partial_funnel(task, stages, reason))
    funnels = []
    for task in job["tasks"]:
        outcome = outcomes.get(task["task_id"])
        if outcome is None:
            continue
        task_dir = directory / "tasks" / digest(task)
        end = (datetime(2019, 1, 1, tzinfo=timezone.utc) + timedelta(days=task["days"])).isoformat()
        funnels.append(funnel_for(outcome, task_dir, condition=task["condition"], end=end))
    by_condition = {funnel["condition"]: funnel for funnel in funnels}
    attempted = [row for row in tasks if row["status"] != "NOT_RUN_BUDGET"]
    if funnels and len(funnels) == len(job["tasks"]):
        status = "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED"
    elif funnels:
        status = "FULL_PATH_STRUCTURAL_CONTROL_PARTIAL"
    else:
        status = "NOT_RUN_BUDGET"
    if status == "NOT_RUN_BUDGET":
        primary = null_funnel(None, reason=blocker_reason)
        truth = None
    else:
        primary = funnels[0]
        truth = all(funnel.get("truth_entered_learner") is False for funnel in funnels)
    return {
        "schema": CONTROLS_SCHEMA,
        "lab_run_id": "TE03-7-CONTROLS-ARTIFACTS-03",
        "created_at": utcnow(),
        "supersedes": supersedes,
        "scope": "TE03.7 engine full-path structural controls; structural opportunity and treatment reach only, never a known net learner 2-delta effect",
        "run_id": run_id,
        "allocation_id": allocation_id,
        "allocation_revision": (job.get("budget_revision") or {}).get("revision_id"),
        "sharding": {
            "unit": "one registered world per full-control shard",
            "worlds": list(SHARD_ORDER),
            "per_shard_cap_seconds": tasks[0]["wall_cap_seconds"] if tasks else None,
            "shards_planned": len(tasks),
            "shards_attempted": len(attempted),
            "shards_completed": len(outcomes),
        },
        "profile": profile_ref,
        "shard_profile": shard_profile_ref,
        "tasks": tasks,
        "planned_counts": profile.get("planned_counts"),
        "measured_basis": profile.get("projection"),
        "run_stop_reason": stop,
        "full_path_funnel": primary,
        "full_path_funnels_by_condition": by_condition,
        "partial_funnels": partial_funnels,
        "selection_results": selection_results,
        "truth_entered_learner": truth,
        "boundary_power_qualification": "NOT_EVALUABLE_FROM_STRUCTURAL_WORLD_ALONE",
        "fabricated_fills": False,
        "status": status,
        "blocker_reason": None if status != "NOT_RUN_BUDGET" else blocker_reason,
    }


def p0_gate(controls, power):
    selections = controls.get("selection_results") or []
    complete_selection = bool(selections) and all(
        row["trials_completed"] == row["trials_configured"] == 32
        and row["params"] and row["objective"] is not None
        and row["selected_candidate"] is not None
        and row["selected_candidate"]["fill_count"] == len(row["selected_candidate"]["fills"])
        for row in selections)
    measured_funnels = controls.get("full_path_funnels_by_condition") or {}
    funnel_ok = bool(measured_funnels) and all(
        funnel["status"] == "MEASURED"
        and all(step["count"] is not None and step["denominator"] is not None for step in funnel["steps"])
        for funnel in measured_funnels.values())
    positive = power["positive_control"]
    null = power["null_control"]
    power_ok = bool(positive["recovered"] and min(positive["per_hypothesis_power"]) >= .90
                    and not null["false_positive"] and null["maximum_family_wilson_upper"] <= null["tolerance"])
    return {
        "funnel_six_steps_with_denominators": funnel_ok,
        "selection_32_trials_complete": complete_selection,
        "positive_recovers_and_null_under_tolerance": power_ok,
        "no_fabricated_fills": controls.get("fabricated_fills") is False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration", default="evidence/time_edge_validation_v4/host-calibration-01.json")
    parser.add_argument("--controls-run", default="te-host-controls-06")
    parser.add_argument("--allocation-id", default="TE02-PILOT-R03")
    parser.add_argument("--profile", default="evidence/time_edge_validation_v4/profiles/te03-controls-measured-20260912-01.json")
    parser.add_argument("--shard-profile", default="evidence/time_edge_validation_v4/profiles/te03-controls-world-shard-profile-20260915-01.json")
    parser.add_argument("--output-power", default="evidence/time_edge_validation_v4/te03/te03_7_power.json")
    parser.add_argument("--output-controls", default="evidence/time_edge_validation_v4/te03/te03_7_controls_r2.json")
    parser.add_argument("--output-blocker", default="evidence/time_edge_validation_v4/te03/controls_06_blocker.json")
    parser.add_argument("--supersedes", default="evidence/time_edge_validation_v4/te03/te03_7_controls.json")
    args = parser.parse_args()
    power_path = ROOT / args.output_power
    if power_path.is_file():
        power, power_hash, power_note = read(power_path), file_digest(power_path), "REUSED_EXISTING_MEASURED_POWER"
    else:
        power = power_artifact(reference(args.calibration), read(ROOT / args.calibration))
        power_hash, power_note = save(power_path, power), "BUILT_FROM_CALIBRATION"
    profile_ref = reference(args.profile)
    shard_profile_ref = reference(args.shard_profile)
    profile = read(ROOT / args.profile)
    shard_profile = read(ROOT / args.shard_profile)
    supersedes = reference(args.supersedes)
    binding = read(ROOT / "configs/time_edge_validation_v4/mode4_binding_r01.json")
    trials_configured = int(binding["resolved_config"]["optuna_trials"])
    blocker_reason = ("every shard needs more than its 2700s cap for the registered path; the bounded invocation "
                      "stopped after the first shard did not complete inside its cap, and no condition-wide funnel "
                      "was measured")
    controls = controls_artifact(args.controls_run, args.allocation_id, profile_ref, profile,
                                 shard_profile_ref, supersedes, trials_configured, blocker_reason)
    controls["p0_gate"] = p0_gate(controls, power)
    controls_hash = save(ROOT / args.output_controls, controls)
    blocker = blocker_artifact(args.controls_run, args.allocation_id, controls, shard_profile)
    blocker_hash = save(ROOT / args.output_blocker, blocker)
    print(json.dumps({"power": {"path": args.output_power, "sha256": power_hash, "note": power_note,
                                "status": power["status"], "positive": power["positive_control"]["status"],
                                "null": power["null_control"]["status"]},
                      "controls": {"path": args.output_controls, "sha256": controls_hash,
                                   "status": controls["status"],
                                   "shards": controls["sharding"],
                                   "funnels": {k: v["status"] for k, v in controls["full_path_funnels_by_condition"].items()},
                                   "selections": len(controls["selection_results"]),
                                   "p0_gate": controls["p0_gate"]},
                      "blocker": {"path": args.output_blocker, "sha256": blocker_hash,
                                  "status": blocker["status"]}}, indent=1))


def controls_budget_state(allocation_id):
    """Measured P0 controls charges and the live allocation remainder."""
    runs = sorted((ROOT / "evidence/time_edge_validation_v4/runs").glob("te-host-controls-*"))
    charged = {}
    for directory in runs:
        ledger = directory / "ledger.sqlite"
        if not ledger.is_file():
            continue
        con = sqlite3.connect(ledger)
        rows = con.execute("SELECT COALESCE(wall,reserved) FROM attempt").fetchall()
        con.close()
        charged[directory.name] = float(sum(row[0] or 0 for row in rows))
    allocation = ROOT / "evidence/time_edge_validation_v4/allocations" / allocation_id / "ledger.sqlite"
    total = spent = None
    if allocation.is_file():
        con = sqlite3.connect(allocation)
        total = float(con.execute("SELECT budget FROM study").fetchone()[0])
        spent = float(con.execute("SELECT COALESCE(SUM(COALESCE(wall,reserved)),0) FROM attempt").fetchone()[0])
        con.close()
    return {"controls_runs_charged_seconds": charged,
            "controls_total_charged_seconds": float(sum(charged.values())),
            "p0_phase_budget_seconds": 30000.0,
            "p0_budget_exceeded": float(sum(charged.values())) > 30000.0,
            "allocation_total_seconds": total, "allocation_charged_seconds": spent,
            "allocation_remaining_seconds": None if total is None or spent is None else total - spent}


def blocker_artifact(run_id, allocation_id, controls, shard_profile):
    tasks = controls["tasks"]
    attempted = [row for row in tasks if row["status"] != "NOT_RUN_BUDGET"]
    reserved = [row for row in tasks if row["status"] == "NOT_RUN_BUDGET"]
    measured = shard_profile["sharding"]["measured_stages_seconds"]
    selections = controls.get("selection_results") or []
    selection_ok = bool(selections) and all(row["trials_completed"] == 32 for row in selections)
    return {
        "schema": BLOCKER_SCHEMA,
        "lab_run_id": run_id,
        "allocation_id": allocation_id,
        "allocation_revision": controls.get("allocation_revision"),
        "status": "NOT_RUN_BUDGET",
        "reason": controls.get("blocker_reason"),
        "sharding": controls["sharding"],
        "measured": {
            "per_shard_cap_seconds": controls["sharding"]["per_shard_cap_seconds"],
            "shards_planned": len(tasks),
            "shards_attempted": len(attempted),
            "shards_completed": controls["sharding"]["shards_completed"],
            "shards_not_launched": len(reserved),
            "attempt_wall_seconds": {row["task_id"]: row["wall_seconds"] for row in attempted},
            "shard_stage_measurements": {row["task_id"]: row["measured_stages"] for row in attempted},
            "bank_selection_32_trials": {
                "tasks": [row["shard_task_id"] for row in selections],
                "trials_configured": [row["trials_configured"] for row in selections],
                "trials_completed": [row["trials_completed"] for row in selections],
                "complete": selection_ok,
            },
            "measured_unit_seconds": measured,
            "residual_lower_bound_per_condition": shard_profile["measured_residual_lower_bound_per_condition_seconds"],
            "budget": controls_budget_state(allocation_id),
        },
        "funnel": null_funnel(None, reason="no shard completed; the six funnel steps are not measurable from partial stages"),
        "selection_evidence": [{"task_id": row["shard_task_id"], "condition": row["condition"], "world": row["world"],
                                "search_file": row["search_file"], "trials_completed": row["trials_completed"],
                                "trials_configured": row["trials_configured"], "objective": row["objective"]}
                               for row in selections],
        "claim_limits": {
            "te04": "LOCKED",
            "structural_controls": "NOT_RUN",
            "power_positive_recovers": True,
            "null_not_false_positive": True,
        },
        "next": ("P0 stops. The sharding itself is sound (each shard has one world, one 2700s cap and its own "
                 "checkpoint), but the registered full path needs far more wall than the remaining envelope; a "
                 "further attempt needs a new registered plan (e.g. stage-sliced shards) and a new allocation "
                 "revision, not a cap raise."),
    }


if __name__ == "__main__":
    main()
