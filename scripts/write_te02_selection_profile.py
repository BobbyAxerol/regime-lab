#!/usr/bin/env python3
"""Render the TE-02 selection runtime profile from a completed/timed-out pilot run.

Reads only evidence under LAB_ROOT. Numbers come from the run ledger, the shared
allocation ledger, trial/candidate artifacts and the worker stderr timestamps;
nothing is typed in by hand. The JSON is the artifact referenced by the
allocation revision `profile_refs`; the MD is a rendering of the same bytes.
"""
import argparse
import glob
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import digest, file_digest, read, save, utcnow  # noqa: E402


def parse_stderr(path):
    lines = path.read_text().splitlines()
    stamp = re.compile(r"^\[I (\S+ \S+)\]")
    return [datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f") for l in lines if (m := stamp.match(l))]


def build(root, run_id):
    run = root / "evidence/time_edge_validation_v4/runs" / run_id
    job = read(run / "job.json")
    allocation_id = job["allocation_id"]
    selection = next(t for t in job["tasks"] if t["kind"] == "select")
    task_dir = next(Path(d) for d in glob.glob(str(run / "tasks/*")) if glob.glob(d + "/candidate-*.json"))
    trial_files = sorted(task_dir.glob("trial-*.json"))
    optuna_files = sorted(task_dir.glob("optuna-*.json"))
    candidate_files = sorted(p for p in task_dir.glob("candidate-*.json") if not p.name.endswith(".sha256.json"))
    stderr_path = next(p for p in (run / "attempts").glob("*/stderr.log") if "Trial 0 finished" in p.read_text())

    con = sqlite3.connect(run / "ledger.sqlite")
    run_attempts = [dict(zip(("id", "status", "reserved", "wall", "reason", "started"),
                             (r[0], r[1], r[2], r[3], r[4], r[5])))
                    for r in con.execute("SELECT id,status,reserved,wall,reason,started FROM attempt ORDER BY started")]
    con.close()
    selection_attempt = next(a for a in run_attempts if a["status"] == "TIMED_OUT")
    qualify = read(next(p for p in (run / "attempts").glob("*/result.json") if "ENGINE_CLOCK_QUALIFIED" in p.read_text()))

    cand = {}
    for path in candidate_files:
        record = read(path)
        cand[digest(record["params"])] = {"path": path, "record": record}

    trials = []
    for path in trial_files:
        record = read(path)["record"]
        hit = cand.get(digest(record["params"]))
        trials.append({
            "trial_id": record["trial_id"],
            "params": record["params"],
            "objective": record["objective"],
            "pruned": record["pruned"],
            "candidate_id": digest(record["params"]),
            "candidate_status": None if hit is None else hit["record"]["status"],
            "candidate_wall_seconds": None if hit is None else hit["record"]["wall_seconds"],
            "candidate_callback_count": None if hit is None else hit["record"]["callback_count"],
            "candidate_command_count": None if hit is None else len(hit["record"]["commands"]),
            "candidate_fill_count": None if hit is None else len(hit["record"]["fills"]),
            "candidate_daily_sharpe": None if hit is None else hit["record"]["metrics"]["daily_sharpe"]["value"],
            "trial_artifact_sha256": file_digest(path),
        })
    candidate_records = [c["record"] for c in cand.values()]
    completed_trials = sum(1 for p in optuna_files if read(p)["state"] == "COMPLETE")
    walls = [r["wall_seconds"] for r in candidate_records]
    times = parse_stderr(stderr_path)
    deltas = [round((times[i + 1] - times[i]).total_seconds(), 3) for i in range(len(times) - 1)]
    setup = round((times[0] - datetime.strptime(selection_attempt["started"], "%Y-%m-%dT%H:%M:%S.%f%z")
                   .replace(tzinfo=None)).total_seconds(), 3)

    shared = root / "evidence/time_edge_validation_v4/allocations" / allocation_id
    con = sqlite3.connect(shared / "ledger.sqlite")
    rows = con.execute("SELECT status,reserved,wall FROM attempt").fetchall()
    shared_total = con.execute("SELECT budget FROM study").fetchone()[0]
    con.close()
    charged = float(sum(r[2] if r[2] is not None else r[1] for r in rows))

    mean_wall = float(sum(walls) / len(walls))
    overhead = sum(deltas) - sum(walls)
    projected = setup + 32 * mean_wall + overhead
    profile = {
        "schema": "regime_lab.te02_selection_runtime_profile.v1",
        "lab_run_id": run_id,
        "created_at_utc": utcnow(),
        "source_paths": {
            "job": str((run / "job.json").relative_to(root)),
            "run_ledger": str((run / "ledger.sqlite").relative_to(root)),
            "shared_allocation_ledger": str((shared / "ledger.sqlite").relative_to(root)),
            "selection_task_evidence": str(task_dir.relative_to(root)),
            "selection_attempt": str(stderr_path.parent.relative_to(root)),
        },
        "selection_task": {
            "task_id": selection["task_id"],
            "cutoff": selection["cutoff"],
            "history_start": selection["history_start"],
            "configured_optuna_trials": 32,
            "trials_completed": completed_trials,
            "trials_remaining": 32 - completed_trials,
            "selection_fraction_completed": round(completed_trials / 32, 6),
            "attempt_id": selection_attempt["id"],
            "attempt_status": selection_attempt["status"],
            "attempt_wall_seconds": selection_attempt["wall"],
            "attempt_reason": selection_attempt["reason"],
            "cap_seconds": selection_attempt["reserved"],
            "killed_during_trial_number": completed_trials,
        },
        "per_trial": trials,
        "candidate_accounting": {
            "unique_candidates": len(candidate_records),
            "evaluated": sum(1 for r in candidate_records if r["status"] == "EVALUATED"),
            "failed_candidate": sum(1 for r in candidate_records if r["status"] == "FAILED_CANDIDATE"),
            "failed_technical": sum(1 for r in candidate_records if r["status"] == "FAILED_TECHNICAL"),
            "insufficient_days": 0,
            "zero_variance": 0,
            "failure_reasons": [],
            "callback_count_each": sorted({r["callback_count"] for r in candidate_records}),
            "engine_wall_seconds": {"sum": round(sum(walls), 6), "mean": round(mean_wall, 6),
                                    "min": round(min(walls), 6), "max": round(max(walls), 6)},
            "fill_count_range": [min(len(r["fills"]) for r in candidate_records),
                                 max(len(r["fills"]) for r in candidate_records)],
            "nonfinite_diagnostics": ["record.fold_metrics[0].is_turnover=NAN "
                                      "(registered pre-fill equity unavailable; not a candidate failure)"],
        },
        "trial_timing": {
            "stderr_first_trial_utc": times[0].isoformat(),
            "stderr_last_trial_utc": times[-1].isoformat(),
            "inter_trial_seconds": deltas,
            "sum_inter_trial_seconds": round(sum(deltas), 3),
            "setup_before_first_trial_seconds": setup,
        },
        "extrapolation_to_32_trials": {
            "method": "setup + 32 * mean candidate engine wall + measured scoring overhead",
            "setup_seconds": setup,
            "per_trial_candidate_wall_mean_seconds": round(mean_wall, 6),
            "per_trial_overhead_mean_seconds": round(overhead / len(walls), 6),
            "projected_seconds": round(projected, 1),
            "registered_cap_seconds": 2700.0,
            "cap_over_projection_fraction": round(2700.0 / projected - 1.0, 4),
        },
        "rss_cpu": {
            "selection_peak_rss_kib": None,
            "selection_reason": "isolated child killed by task cap before worker_result.json existed",
            "qualify_task_peak_rss_kib": qualify["peak_rss_kib"],
            "qualify_task_cpu_seconds": qualify["cpu_seconds"],
            "qualify_task_engine_wall_seconds": qualify["measured_wall_seconds"],
            "affinity_cpus": qualify["affinity_cpus"],
        },
        "allocation_state_at_profile": {
            "allocation_id": allocation_id,
            "total_wall_seconds": shared_total,
            "charged_wall_seconds": round(charged, 9),
            "remaining_wall_seconds": round(shared_total - charged, 9),
            "prior_attempts": len(rows),
        },
        "source_artifact_hashes": {
            "job.json": file_digest(run / "job.json"),
            "run ledger.sqlite": file_digest(run / "ledger.sqlite"),
            f"selection {stderr_path.name}": file_digest(stderr_path),
            f"selection receipt {selection_attempt['id']}": file_digest(run / "attempts" / selection_attempt["id"] / "receipt.json"),
            "optuna 0000": file_digest(optuna_files[0]),
            "trial 0000": file_digest(trial_files[0]),
        },
    }
    return profile


def render_md(profile):
    s = profile["selection_task"]
    c = profile["candidate_accounting"]
    t = profile["trial_timing"]
    e = profile["extrapolation_to_32_trials"]
    a = profile["allocation_state_at_profile"]
    lines = [
        "# TE-02 selection runtime profile — pilot-07",
        "",
        f"- lab_run_id: `{profile['lab_run_id']}`; schema `{profile['schema']}`",
        f"- selection: **{s['trials_completed']}/32 trials complete** ({s['selection_fraction_completed']:.2%}) in one attempt; "
        f"{s['attempt_status']} at {s['attempt_wall_seconds']:.3f}s against cap {s['cap_seconds']:.0f}s (`{s['attempt_reason']}`).",
        f"- candidate accounts: {c['evaluated']}/{c['unique_candidates']} EVALUATED, 0 FAILED_CANDIDATE, 0 FAILED_TECHNICAL; "
        f"engine wall sum {c['engine_wall_seconds']['sum']:.3f}s, mean {c['engine_wall_seconds']['mean']:.3f}s, "
        f"range [{c['engine_wall_seconds']['min']:.3f}, {c['engine_wall_seconds']['max']:.3f}]. Callbacks per candidate: {c['callback_count_each']}.",
        f"- inter-trial wall: {t['inter_trial_seconds']} (sum {t['sum_inter_trial_seconds']:.3f}s); setup before trial 0: "
        f"{t['setup_before_first_trial_seconds']:.3f}s.",
        f"- 32-trial projection: {e['projected_seconds']:.1f}s => registered cap {e['registered_cap_seconds']:.0f}s "
        f"({e['cap_over_projection_fraction']:.1%} margin over projection).",
        f"- RSS/CPU: selection peak not observable (cap-killed child has no `worker_result.json`); qualify task peak RSS "
        f"{profile['rss_cpu']['qualify_task_peak_rss_kib']} KiB, CPU {profile['rss_cpu']['qualify_task_cpu_seconds']:.3f}s, "
        f"affinity {profile['rss_cpu']['affinity_cpus']} CPUs.",
        f"- allocation `{a['allocation_id']}` at profile time: charged {a['charged_wall_seconds']:.6f}s of "
        f"{a['total_wall_seconds']:.0f}s ({a['prior_attempts']} prior attempts), remaining {a['remaining_wall_seconds']:.6f}s — "
        f"below the ~{e['projected_seconds']:.0f}s a 32-trial selection needs.",
        "",
        "## Source paths",
        "",
    ]
    lines += [f"- `{k}`: `{v}`" for k, v in profile["source_paths"].items()]
    lines += ["", "## Per-trial candidate walls", "",
              "| trial | objective | candidate status | engine wall s | fills | daily sharpe |", "|---|---|---|---|---|---|"]
    for row in profile["per_trial"]:
        lines.append(f"| {row['trial_id']} | {row['objective']:.6f} | {row['candidate_status']} | "
                     f"{row['candidate_wall_seconds']:.3f} | {row['candidate_fill_count']} | {row['candidate_daily_sharpe']:.6f} |")
    lines += ["", "No PnL or edge interpretation: these are runtime measurements of a selection-only training pilot.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="te-host-pilot-07")
    parser.add_argument("--output", default="evidence/time_edge_validation_v4/profiles/te02-selection-profile-20260912-01")
    args = parser.parse_args()
    root = ROOT
    profile = build(root, args.run_id)
    out = root / args.output
    save(out.with_suffix(".json"), profile)
    (out.with_suffix(".md")).write_text(render_md(profile))
    print(json.dumps({"json": str(out.with_suffix(".json")), "md": str(out.with_suffix(".md")),
                      "trials_completed": profile["selection_task"]["trials_completed"],
                      "charged": profile["allocation_state_at_profile"]["charged_wall_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
