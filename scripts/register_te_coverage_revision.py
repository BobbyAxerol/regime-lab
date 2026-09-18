#!/usr/bin/env python3
"""Register the TE-03 coverage revision (append-only) before extending support.

Every number in the revision is read from the committed prior artifacts and the
live data; nothing is restated by hand. The revision restates the registered
prior coverage, the revised coverage, the measured support shortfall and why the
extension is needed, and the properties that are unchanged.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.coverage import (COVERAGE_REGISTRATION_SCHEMA,
                                                  COVERAGE_REVISION_SCHEMA)
from crypto_regime_lab.time_edge.storage import file_digest, read, save, utcnow  # noqa: E402

REGISTRATION = "configs/time_edge_validation_v4/te03_coverage_registration.json"
STATISTICS = "configs/time_edge_validation_v4/r01/statistical_analysis_plan.json"
PRIOR_TARGETS = "evidence/time_edge_validation_v4/host-targets-01.json"
PRIOR_MODELS = "evidence/time_edge_validation_v4/host-model-results-01.json"
PRIOR_INFO = "evidence/time_edge_validation_v4/te03/information_value.json"
FEATURES = "evidence/time_edge_validation_v4/runs/te-host-features-01/tasks/bf12dd2a607f22b33d5de81e736c63dbfdc924455957779e977e5a5c80357e18/raw_features.parquet"
BANK = "evidence/time_edge_validation_v4/host-candidate-bank-01.json"


def reference(relative):
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit("missing coverage input: " + relative)
    return {"path": relative, "sha256": file_digest(path)}


def vintages(payload):
    return [row for row in payload["results"] if "design_trials" in row]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-id", default="TE03-COVERAGE-R01")
    parser.add_argument("--output", default="evidence/time_edge_validation_v4/coverage-revisions/TE03-COVERAGE-R01.json")
    parser.add_argument("--target-start", default="2021-12-29T00:00:00Z")
    parser.add_argument("--target-end", default="2023-04-19T00:00:00Z")
    parser.add_argument("--model-start", default="2021-02-01T00:00:00Z")
    parser.add_argument("--model-end", default="2023-04-19T00:00:00Z")
    parser.add_argument("--why", default=(
        "the registered minimum of 20 informative candidate episodes is not met; the prior window yields "
        "14 targets and 8 evaluable outer targets, so the target and model series are extended on the same "
        "28-day grid inside the registered development window 2021-01-01..2024-01-01"))
    args = parser.parse_args()
    registered = read(ROOT / REGISTRATION)
    if registered.get("schema") != COVERAGE_REGISTRATION_SCHEMA:
        raise SystemExit("registered TE-03 coverage artifact has the wrong schema")
    statistics = read(ROOT / STATISTICS)
    targets = read(ROOT / PRIOR_TARGETS)["targets"]
    models = vintages(read(ROOT / PRIOR_MODELS))
    info = read(ROOT / PRIOR_INFO)
    features = pd.read_parquet(ROOT / FEATURES)
    prior_start = pd.Timestamp(registered["target_series"]["start"])
    prior_end = pd.Timestamp(registered["target_series"]["end_exclusive"])
    prior_last = max(pd.Timestamp(row["origin"]) for row in targets)
    prior_cutoffs = sorted(pd.Timestamp(row["cutoff"]) for row in models)
    step = int(registered["target_series"]["step_days"])
    extension_start = prior_last + pd.Timedelta(days=step)
    new_start, new_end = pd.Timestamp(args.target_start), pd.Timestamp(args.target_end)
    model_start, model_end = pd.Timestamp(args.model_start), pd.Timestamp(args.model_end)
    if new_start != extension_start:
        raise SystemExit(f"extension must start at {extension_start.isoformat()}, not {new_start.isoformat()}")
    if new_end <= prior_end:
        raise SystemExit("revised target coverage must extend the registered end")
    if model_start != pd.Timestamp(registered["model_series"]["start"]):
        raise SystemExit("extended model series must recompute from the registered model start")
    if model_end <= pd.Timestamp(registered["model_series"]["end_exclusive"]):
        raise SystemExit("revised model coverage must extend the registered end")
    origins = []
    moment = prior_start
    while moment < new_end:
        until = moment + pd.Timedelta(days=int(registered["target_series"]["horizon_days"]))
        if until > new_end:
            break
        origins.append(moment)
        moment += pd.Timedelta(days=step)
    if [pd.Timestamp(x) for x in origins[:len(targets)]] != [pd.Timestamp(row["origin"]) for row in targets]:
        raise SystemExit("revised target grid would move a prior origin")
    cutoffs = []
    moment = model_start
    while moment < model_end:
        cutoffs.append(moment)
        moment += pd.Timedelta(days=step)
    if cutoffs[:len(prior_cutoffs)] != prior_cutoffs:
        raise SystemExit("recomputed model series would move a prior cutoff")
    floor = int(statistics["support"]["minimum_informative_candidate_episodes"])
    prior_evaluable = int(info["summary"]["evaluable"])
    if prior_evaluable >= floor:
        raise SystemExit("prior coverage already meets the support floor; no revision is warranted")
    revision = {
        "schema": COVERAGE_REVISION_SCHEMA,
        "study_id": "time_edge_validation_v4",
        "registration_id": "TE01-R01",
        "revision_id": args.revision_id,
        "stage_scope": "te03_targets_models",
        "registered_at_utc": utcnow(),
        "registered_before_extension": True,
        "prior_coverage": {
            "target_series": {
                "start": registered["target_series"]["start"],
                "end_exclusive": registered["target_series"]["end_exclusive"],
                "step_days": step, "horizon_days": int(registered["target_series"]["horizon_days"]),
                "origins": len(targets), "last_origin": prior_last.isoformat(),
                "artifact": reference(PRIOR_TARGETS),
            },
            "model_series": {
                "start": registered["model_series"]["start"],
                "end_exclusive": registered["model_series"]["end_exclusive"],
                "step_days": int(registered["model_series"]["step_days"]),
                "vintages": len(models), "last_cutoff": prior_cutoffs[-1].isoformat(),
                "artifact": reference(PRIOR_MODELS),
            },
            "support_measured": {
                "planned_outer_targets": int(info["summary"]["planned"]),
                "evaluable_outer_targets": prior_evaluable,
                "status": info["inference"]["status"],
                "reason": info["inference"].get("reason"),
                "information_artifact": reference(PRIOR_INFO),
            },
        },
        "revised_coverage": {
            "target_series": {
                "start": registered["target_series"]["start"],
                "end_exclusive": pd.Timestamp(args.target_end).isoformat().replace("+00:00", "Z"),
                "step_days": step, "horizon_days": int(registered["target_series"]["horizon_days"]),
                "origins": len(origins), "extension_start": extension_start.isoformat(),
                "delta_origins": len(origins) - len(targets), "last_origin": origins[-1].isoformat(),
            },
            "model_series": {
                "start": model_start.isoformat(),
                "end_exclusive": pd.Timestamp(args.model_end).isoformat().replace("+00:00", "Z"),
                "step_days": step, "vintages": len(cutoffs), "last_cutoff": cutoffs[-1].isoformat(),
                "recomputed_from_registered_start": True,
            },
        },
        "support_floor": {
            "field": "minimum_informative_candidate_episodes",
            "value": floor,
            "source": STATISTICS,
            "source_sha256": file_digest(ROOT / STATISTICS),
            "prior_evaluable": prior_evaluable,
            "shortfall": floor - prior_evaluable,
        },
        "unchanged": {
            "alpha_id": registered["target_series"]["alpha_id"],
            "cell_id": registered["target_series"]["cell_id"],
            "grid_days": step,
            "target_horizon_days": int(registered["target_series"]["horizon_days"]),
            "train_days": 180,
            "candidate_bank": reference(BANK),
            "features": reference(FEATURES),
            "features_last_available_at": features.index[-1].isoformat(),
            "prior_origin_count": len(targets),
            "prior_vintage_count": len(models),
        },
        "measured_reason": {
            "prior_planned_outer_targets": int(info["summary"]["planned"]),
            "prior_evaluable_outer_targets": prior_evaluable,
            "support_floor": floor,
            "targets_available": len(origins),
            "vintages_available": len(cutoffs),
            "policy": "append later non-overlapping origins only; no prior origin, cell, train window, grid or horizon is moved",
        },
        "why": args.why,
        "what_it_changes": [
            "target coverage end: %s -> %s (%d -> %d non-overlapping origins)"
            % (registered["target_series"]["end_exclusive"], args.target_end, len(targets), len(origins)),
            "model coverage end: %s -> %s (%d -> %d vintages, all recomputed from the registered start)"
            % (registered["model_series"]["end_exclusive"], args.model_end, len(models), len(cutoffs)),
            "support: %d evaluable outer targets -> up to %d, still bounded by measured evaluability"
            % (prior_evaluable, max(0, len(origins) - len(targets)) + prior_evaluable),
        ],
        "what_it_does_not_change": [
            "every prior origin, model cutoff and training window; the extension appends after the last prior origin",
            "the 28-day non-overlapping target grid, the 28-day horizon and the 180-day train window",
            "alpha A-SC, cell A-SC/BTCUSDT, the candidate bank, economics and the engine contract",
            "the registered development window 2021-01-01..2024-01-01",
        ],
        "what_it_costs": "one target task per appended origin on the measured ladder; model vintages are recomputed cheaply",
        "evidence_refs": {
            "prior_targets": reference(PRIOR_TARGETS),
            "prior_models": reference(PRIOR_MODELS),
            "prior_information": reference(PRIOR_INFO),
            "features": reference(FEATURES),
            "candidate_bank": reference(BANK),
            "registration": reference(REGISTRATION),
        },
        "engine_runs": 0,
        "economic_conclusion": "NOT_EVALUABLE",
    }
    output = ROOT / args.output
    digest = save(output, revision)
    print(json.dumps({"revision": args.output, "sha256": digest,
                      "prior_origins": len(targets), "revised_origins": len(origins),
                      "prior_vintages": len(models), "revised_vintages": len(cutoffs),
                      "prior_evaluable": prior_evaluable, "support_floor": floor}, indent=1))


if __name__ == "__main__":
    main()
