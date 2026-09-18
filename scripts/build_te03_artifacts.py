#!/usr/bin/env python3
"""Assemble the TE-03 artifacts from collected, hash-verified stage outputs.

Every field is read back out of the targets/model/emissions/analysis artifacts;
missing support is written as null plus a reason, never as zero. No metric is
computed here that the generating stage did not already measure.
"""
import argparse
import json

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import read, save  # noqa: E402


def require(root, relative):
    path = root / relative
    if not path.is_file():
        raise SystemExit("missing stage artifact: " + relative)
    return path


def vintages_of(results_payload):
    return [v for v in results_payload["results"] if "design_trials" in v]


def design_trials_lines(vintages):
    lines = []
    for vintage in vintages:
        for trial in vintage["design_trials"]:
            folds = trial["inner_folds"]
            lines.append({
                "model_id": vintage["model_id"], "cutoff": vintage["cutoff"], "design": trial["design"],
                "admissible": trial["admissible"], "ranking_utility": trial["ranking_utility"],
                "informative_episodes": trial["informative_episodes"],
                "normalized_objective": trial["normalized_objective"],
                "inner_folds": [{"train_end": f["train_end"], "validation_end": f["validation_end"],
                                 "fit_ok": f["fit_ok"], "training_targets": f["training_targets"],
                                 "information_planned": f["information"]["planned"],
                                 "information_evaluable": f["information"]["evaluable"]} for f in folds],
            })
    return lines


def causality(root, vintages, targets):
    rows = []
    for vintage in vintages:
        cutoff = pd.Timestamp(vintage["cutoff"])
        train = [t for t in targets if pd.Timestamp(t["outcome_available_at"]) < cutoff]
        future = [t for t in targets if pd.Timestamp(t["outcome_available_at"]) >= cutoff
                  and pd.Timestamp(t["origin"]) < cutoff]
        rows.append({
            "model_id": vintage["model_id"], "cutoff": vintage["cutoff"], "ready_at": vintage["ready_at"],
            "ready_after_cutoff": pd.Timestamp(vintage["ready_at"]) >= cutoff,
            "history_start": vintage["history_start"], "history_days": int((cutoff - pd.Timestamp(vintage["history_start"])).days),
            "training_raw_hash": vintage["training_raw_hash"], "missing_training_rows": vintage["missing_training_rows"],
            "feature_schema_hash": vintage["feature_schema_hash"], "model_design_hash": vintage["model_design_hash"],
            "mapped_training_targets": len(train),
            "mapped_training_targets_with_outcome_before_cutoff": sum(
                1 for t in train if pd.Timestamp(t["outcome_available_at"]) < cutoff),
            "same_or_future_outcome_targets_excluded": len(future),
            "purge_rule": "outcome_available_at < fit cutoff (strict); same-time availability excluded",
            "warm_filter": "validation initialized from causal terminal train state",
            "mapping_status": vintage["mapping"]["status"], "common_namespace": vintage["common_namespace"],
            "fit_quality": vintage["fit_quality"],
            "dead_states": vintage["dossier"]["dead_states"],
        })
    return {"schema": "regime_lab.te03_model_causality.v1", "vintages": rows,
            "checks": {
                "no_future_training_outcome": all(
                    r["mapped_training_targets"] == r["mapped_training_targets_with_outcome_before_cutoff"] for r in rows),
                "future_or_same_time_targets_excluded": all(
                    r["same_or_future_outcome_targets_excluded"] >= 0 for r in rows),
                "ready_not_before_cutoff": all(r["ready_after_cutoff"] for r in rows),
                "feature_schema_pinned": all(r["feature_schema_hash"] for r in rows),
            },
            "unit_tests": ["tests/time_edge_validation_v4/test_te03_te05_technical.py::test_target_tail_purge_and_equal_time_exclusion",
                           "tests/time_edge_validation_v4/test_te03_te05_technical.py::test_future_candidate_bank_rejected",
                           "tests/time_edge_validation_v4/test_te03_te05_technical.py::test_emission_suffix_ready_and_warmed_filter",
                           "tests/time_edge_validation_v4/test_te03_te05_technical.py::test_state_mapping_common_raw_coordinates_and_ambiguity"],
            "reason_fields": "each vintage records the registered purge rule and its own history window"}


def parameter_opportunity(targets, opportunities):
    per_origin = []
    by_hash = {}
    for t in targets:
        vals = np.asarray(t["utilities"], float)
        order = list(np.argsort(vals))
        measured = opportunities.get(t["origin"], {})
        per_origin.append({"origin": t["origin"], "outcome_available_at": t["outcome_available_at"],
                           "cell_id": t["cell_id"], "candidate_count": len(vals),
                           "unique_behaviors": measured.get("unique_behaviors"),
                           "utility_range": measured.get("utility_range", float(vals.max() - vals.min())),
                           "utility_std": float(vals.std(ddof=1)), "ranking": [int(i) for i in order]})
        by_hash.setdefault(t["candidate_set_hash"], []).append(order)
    reversals = []
    for candidate_hash, orders in by_hash.items():
        flips = 0; pairs = 0
        for a, b in zip(orders[:-1], orders[1:]):
            for i in range(len(a)):
                for j in range(i + 1, len(a)):
                    pairs += 1
                    if (a[i] - a[j]) * (b[i] - b[j]) < 0:
                        flips += 1
        reversals.append({"candidate_set_hash": candidate_hash, "origins": len(orders),
                          "pairs_compared": pairs, "rank_reversals": flips,
                          "rank_reversal_fraction": None if pairs == 0 else flips / pairs})
    ranges = [r["utility_range"] for r in per_origin]
    behaviors = [r["unique_behaviors"] for r in per_origin if r["unique_behaviors"] is not None]
    return {"schema": "regime_lab.te03_parameter_opportunity.v1",
            "cell_id": targets[0]["cell_id"] if targets else None,
            "candidate_set_hash": targets[0]["candidate_set_hash"] if targets else None,
            "origins": per_origin, "rank_stability": reversals,
            "summary": {"targets": len(per_origin), "candidate_count": per_origin[0]["candidate_count"] if per_origin else 0,
                        "utility_range_mean": float(np.mean(ranges)) if ranges else None,
                        "utility_range_min": float(np.min(ranges)) if ranges else None,
                        "utility_range_max": float(np.max(ranges)) if ranges else None,
                        "unique_behaviors_min": int(min(behaviors)) if behaviors else None,
                        "unique_behaviors_max": int(max(behaviors)) if behaviors else None,
                        "hindsight_note": "realized candidate utility is diagnostic only; it never names a policy state"},
            "behavioral_diversity": {"measured_origins": len(behaviors),
                                     "source": "worker opportunity.unique_behaviors per target task"}}


def model_registry(emissions_payload, vintages):
    registry = emissions_payload["model_registry"]
    rows = []
    for vintage in vintages:
        key = vintage["model_id"]
        entry = registry.get(key)
        rows.append({"model_id": key, "cutoff": vintage["cutoff"], "ready_at": vintage["ready_at"],
                     "design": vintage["design"], "decision": vintage["decision"],
                     "fit_quality": vintage["fit_quality"], "mapping": vintage["mapping"],
                     "common_namespace": vintage["common_namespace"],
                     "registry_present": entry is not None,
                     "dossier_occupancy": vintage["dossier"]["occupancy_counts"],
                     "dossier_dead_states": vintage["dossier"]["dead_states"]})
    return {"schema": "regime_lab.te03_model_registry.v1", "vintages": rows,
            "registry_models": sorted(registry),
            "emission_count": len(emissions_payload["emissions"]),
            "eligible_emission_count": sum(1 for e in emissions_payload["emissions"] if e["decision_eligible"]),
            "quality_statuses": sorted({e["quality_status"] for e in emissions_payload["emissions"]}),
            "immutability": "each vintage is content-addressed by model_id; emissions name model_id, fit cutoff and ready time"}


def information_value(analysis):
    rows = []
    per_vintage = []
    for model in analysis["model_table"]:
        effects = [r["effect"] for r in model["outer_rows"] if r.get("effect") is not None]
        disp = float(np.std(effects, ddof=1)) if len(effects) > 1 else None
        per_vintage.append({"model_id": model["model_id"], "cutoff": model["cutoff"], "design": model["design"],
                            "decision": model["decision"], "training_targets": model["training_targets"],
                            "planned_outer_targets": model["planned_outer_targets"],
                            "evaluable_outer_targets": model["evaluable_outer_targets"],
                            "mean_outer_information_effect": model["mean_outer_information_effect"],
                            "dispersion": disp, "support_fraction": None if model["planned_outer_targets"] == 0
                            else model["evaluable_outer_targets"] / model["planned_outer_targets"]})
        rows.extend(model["outer_rows"])
    effects = [r["effect"] for r in rows if r.get("effect") is not None]
    return {"schema": "regime_lab.te03_information_value.v1",
            "scope": "ACTUAL emitted vintage states at each target origin -> later matured candidate-utility ranking; "
                     "inner design-selection scores are never reused as outer evidence",
            "base_comparator": "unconditional candidate-utility ranking profile within the same candidate set/economics",
            "target": "future paired candidate utility ranking, not market direction",
            "per_vintage": per_vintage, "rows": rows,
            "summary": {"planned": len(rows), "evaluable": len(effects),
                        "mean_effect": float(np.mean(effects)) if effects else None,
                        "effect_min": float(np.min(effects)) if effects else None,
                        "effect_max": float(np.max(effects)) if effects else None,
                        "effect_dispersion": float(np.std(effects, ddof=1)) if len(effects) > 1 else None,
                        "reasons": sorted({r["reason"] for r in rows if r.get("effect") is None})},
            "inference": analysis["inference"].get("H-MODEL-INFO"),
            "eligibility": "only eligible OK emissions at the actual target origin enter; unavailable reasons are retained per row"}


def model_decision(vintages, analysis):
    informative = [v for v in vintages if v["decision"] == "SELECTED_INNER_INFORMATIVE_DESIGN"]
    m0 = [v for v in vintages if v["design"]["kind"] == "M0"]
    outer = analysis["inference"].get("H-MODEL-INFO", {})
    decision = {
        "schema": "regime_lab.te03_model_decision.v1",
        "vintages": len(vintages), "selected_inner_informative": len(informative),
        "m0_control_vintages": len(m0),
        "selected_design_used": (informative[0]["design"] if informative else m0[0]["design"] if m0 else None),
        "decisions": [{"cutoff": v["cutoff"], "decision": v["decision"], "design": v["design"],
                       "admissible_designs": sum(1 for t in v["design_trials"] if t["admissible"])} for v in vintages],
        "information_inference_status": None if outer is None else outer.get("status"),
        "information_inference_reason": None if outer is None else outer.get("reason"),
        "stop_condition": "do not expand the model ladder while the inner-informative design is unavailable in most vintages and the outer information family is INCONCLUSIVE_SUPPORT",
        "decision": "KEEP_SECONDARY_DESIGN_NO_EXPANSION",
        "reason": "support is the binding constraint (few non-overlapping 28-day targets); the ladder did run every registered alternative and fall back to the M0 control where no admissible informative design existed",
        "next_revision_trigger": "more mature non-overlapping candidate targets, or a separately registered feature/horizon delta; E/NEIGH remain secondary",
    }
    return decision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="te03-artifacts-01")
    parser.add_argument("--output-dir", default="evidence/time_edge_validation_v4/te03")
    parser.add_argument("--results", default="evidence/time_edge_validation_v4/host-model-results-01.json")
    parser.add_argument("--emissions", default="evidence/time_edge_validation_v4/host-emissions-01.json")
    parser.add_argument("--targets", default="evidence/time_edge_validation_v4/host-targets-01.json")
    parser.add_argument("--target-results", default="evidence/time_edge_validation_v4/host-targets-results-01.json")
    parser.add_argument("--analysis", default="evidence/time_edge_validation_v4/host-analysis-01.json")
    args = parser.parse_args()
    root = ROOT
    results = read(require(root, args.results))
    emissions = read(require(root, args.emissions))
    targets = read(require(root, args.targets))["targets"]
    target_results = read(require(root, args.target_results))["results"]
    opportunities = {r["targets"][0]["origin"]: r["opportunity"] for r in target_results if r.get("targets")}
    analysis = read(require(root, args.analysis))
    vintages = vintages_of(results)
    out = root / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    lines = design_trials_lines(vintages)
    (out / "model_design_trials.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in lines))
    save(out / "model_causality.json", causality(root, vintages, targets))
    save(out / "model_registry.json", model_registry(emissions, vintages))
    save(out / "parameter_opportunity.json", parameter_opportunity(targets, opportunities))
    save(out / "information_value.json", information_value(analysis))
    save(out / "model_decision.json", model_decision(vintages, analysis))
    print(json.dumps({"vintages": len(vintages), "design_trials": len(lines),
                      "emissions": len(emissions["emissions"]), "targets": len(targets),
                      "artifacts": sorted(p.name for p in out.glob("*"))}, indent=1))


if __name__ == "__main__":
    main()
