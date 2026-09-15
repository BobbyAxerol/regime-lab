#!/usr/bin/env python
"""Measure how much of a structural-controls run repeats work already on disk.

Compares one run against a prior run of the same registered condition and asks,
per cache kind, whether the prior artifact would be a cache HIT today: the code
contract files must be unchanged and the produced bytes must be identical. A
kind whose contract moved is a legitimate recompute and is reported as such.

Reads only committed artifacts and the working tree; runs no engine and writes
no cache entry.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.time_edge.compute_cache import CONTRACT_FILES  # noqa: E402
from crypto_regime_lab.time_edge.storage import file_digest, read, save, utcnow  # noqa: E402

RUNS = LAB / "evidence/time_edge_validation_v4/runs"
WORLDS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")

# An unchanged code contract is necessary but not sufficient for reuse: a stage
# whose cache FACETS embed another stage's output also dies when that stage is
# recomputed. `fit` keys on digest(targets), so a moved targets contract carries
# the fits with it even though model.py never changed. Read from
# pipeline_controls.full_control, where each facet dict is built.
# Verified line by line against pipeline_controls.full_control:
#   world_facets   -> generator/contract/seed/condition/days/symbol          : no input
#   features       -> markets={symbol: world sha}                            : world
#   search_facets  -> market=world sha                                       : world
#   targets facets -> market=world sha, candidate_bank digest                : world, search
#   fit facets     -> features=features_sha, targets=digest(targets)         : targets, features
#   deployment     -> market=world sha, selection_ids                        : world, search
FACET_DEPENDS_ON = {"world": (), "features": ("world",), "targets": ("world", "search"),
                    "search": ("world",), "fit": ("targets", "features"),
                    "deployment": ("world", "search")}


def task_dirs(run_id):
    return sorted(p for p in (RUNS / run_id / "tasks").glob("*") if p.is_dir())


def condition_of(run_id, task_dir):
    job = read(RUNS / run_id / "job.json")
    from crypto_regime_lab.time_edge.storage import digest
    for task in job["tasks"]:
        if digest(task) == task_dir.name:
            return task["condition"], task
    return None, None


def stage_counts(task_dir):
    def count(prefix):
        return len([p for p in task_dir.glob(prefix + "-*.json") if not p.name.endswith(".seal.json")])
    return {"targets": count("targets"), "model_fits": count("model"), "searches": count("search"),
            "deployments": len(list(task_dir.glob("deployment*.json")))}


def worlds_match(old_dir, new_dir):
    rows = []
    for symbol in WORLDS:
        old = old_dir / f"raw-{symbol}/observable_market.parquet"
        new = new_dir / f"raw-{symbol}/observable_market.parquet"
        if not old.is_file() or not new.is_file():
            rows.append({"symbol": symbol, "identical": None, "reason": "one side absent"})
            continue
        a, b = file_digest(old), file_digest(new)
        rows.append({"symbol": symbol, "identical": a == b, "sha256": a if a == b else None,
                     "bytes": old.stat().st_size, "same_inode": old.stat().st_ino == new.stat().st_ino})
    return rows


def searches_match(old_dir, new_dir):
    rows = []
    for old in sorted(old_dir.glob("search-*.json")):
        if old.name.endswith(".seal.json"):
            continue
        new = new_dir / old.name
        payload = read(old)
        row = {"artifact": old.name, "cutoff": payload.get("cutoff"), "status": payload.get("status"),
               "params": payload.get("params"), "trials": len(payload.get("trials") or []),
               "recomputed_in_new_run": new.is_file()}
        if new.is_file():
            row["new_params"] = read(new).get("params")
            row["same_selection"] = row["new_params"] == row["params"]
        rows.append(row)
    return rows


def contract_moved_since(commit_cutoff):
    """Which cache kinds have a contract file committed after the prior run."""
    import subprocess
    moved = {}
    for kind, files in sorted(CONTRACT_FILES.items()):
        changed = []
        for name in files:
            out = subprocess.run(["git", "log", "--since", commit_cutoff, "--format=%h %ad %s",
                                  "--date=format:%Y-%m-%d %H:%M", "--", name],
                                 cwd=LAB, capture_output=True, text=True).stdout.strip()
            if out:
                changed.append({"file": name, "commits": out.splitlines()})
        moved[kind] = {"contract_moved": bool(changed), "changed_files": changed}
    return moved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-run", default="te-host-controls-02")
    parser.add_argument("--current-run", default="te-host-controls-btc-02")
    parser.add_argument("--condition", default="NULL_STATIONARY")
    parser.add_argument("--prior-finished", default="2026-09-14T14:10:00",
                        help="git --since cutoff: when the prior run stopped producing")
    parser.add_argument("--selection-wall-seconds", type=float, default=1618.0,
                        help="measured wall of one 32-trial selection, from the registered profile")
    parser.add_argument("--output", default=None)
    parser.add_argument("--supersedes", default=None)
    parser.add_argument("--supersede-reason", default=None)
    args = parser.parse_args()

    old_dir = new_dir = None
    for candidate in task_dirs(args.prior_run):
        if condition_of(args.prior_run, candidate)[0] == args.condition:
            old_dir = candidate
    for candidate in task_dirs(args.current_run):
        if condition_of(args.current_run, candidate)[0] == args.condition:
            new_dir = candidate
    if old_dir is None or new_dir is None:
        raise SystemExit(f"no {args.condition} task dir in both runs")

    worlds = worlds_match(old_dir, new_dir)
    searches = searches_match(old_dir, new_dir)
    moved = contract_moved_since(args.prior_finished)
    contract_stable = {kind for kind, row in moved.items() if not row["contract_moved"]}
    recomputing = set(moved) - contract_stable
    # Propagate: a kind is reusable only if every kind its facets embed is also reusable.
    reusable = set(contract_stable)
    for _ in range(len(moved)):
        reusable = {kind for kind in reusable
                    if all(parent in reusable for parent in FACET_DEPENDS_ON.get(kind, ()))}
    lost_to_dependency = sorted(contract_stable - reusable)
    reusable = sorted(reusable)
    prior_stages = stage_counts(old_dir)
    redone = sum(1 for row in searches if row.get("recomputed_in_new_run"))
    still_owed = len(searches) - redone

    payload = {
        "schema": "regime_lab.te_recompute_measurement.v1",
        "recorded_at_utc": utcnow(),
        "prior_run": args.prior_run, "current_run": args.current_run, "condition": args.condition,
        "prior_task_dir": str(old_dir.relative_to(LAB)), "current_task_dir": str(new_dir.relative_to(LAB)),
        "supersedes": args.supersedes, "supersede_reason": args.supersede_reason,
        "prior_stages_completed": prior_stages,
        "cache_kind_contracts": moved,
        "kinds_whose_contract_is_unchanged": sorted(contract_stable),
        "kinds_that_must_recompute_because_their_contract_moved": sorted(recomputing),
        "kinds_that_must_recompute_because_a_facet_input_moved": lost_to_dependency,
        "facet_dependencies": {k: list(v) for k, v in sorted(FACET_DEPENDS_ON.items())},
        "kinds_actually_reusable": reusable,
        "worlds": worlds,
        "worlds_identical": sum(1 for row in worlds if row["identical"] is True),
        "worlds_checked": len(worlds),
        "world_bytes_duplicated": sum(row.get("bytes", 0) for row in worlds if row["identical"] is True),
        "searches": searches,
        "searches_on_disk_from_prior_run": len(searches),
        "searches_already_recomputed_in_current_run": redone,
        "searches_still_owed_by_current_run": still_owed,
        "selection_wall_seconds": args.selection_wall_seconds,
        "recomputable_selection_seconds_still_avoidable": still_owed * args.selection_wall_seconds,
        "why_not_a_cache_hit": ("the prior run predates the identity-keyed compute cache (added "
                                "2026-09-15), so its artifacts were never published; the cache never "
                                "keys on a run id, so nothing but the missing publication prevents reuse"),
        "not_claimed": [
            "that the recompute is a defect: the cache simply did not exist when the prior run ran",
            "that a backfill is safe while a run is reading the cache - publish and seal are two "
            "writes, and a lookup between them raises",
            "that an unchanged contract alone makes a kind reusable - `fit` keys on "
            "digest(targets), so a moved targets contract invalidates the fits too",
        ],
    }
    if bool(args.supersedes) != bool(args.supersede_reason):
        raise SystemExit("--supersedes and --supersede-reason go together: a replacement states why")
    out = LAB / (args.output or f"evidence/time_edge_validation_v4/operations/"
                                f"recompute-{args.current_run}-{args.condition.lower()}-01.json")
    save(out, payload)
    print("wrote", out.relative_to(LAB))
    print(json.dumps({k: payload[k] for k in (
        "prior_stages_completed", "kinds_whose_contract_is_unchanged",
        "kinds_that_must_recompute_because_their_contract_moved",
        "kinds_that_must_recompute_because_a_facet_input_moved", "kinds_actually_reusable",
        "worlds_identical", "worlds_checked", "world_bytes_duplicated",
        "searches_on_disk_from_prior_run", "searches_already_recomputed_in_current_run",
        "searches_still_owed_by_current_run", "recomputable_selection_seconds_still_avoidable")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
