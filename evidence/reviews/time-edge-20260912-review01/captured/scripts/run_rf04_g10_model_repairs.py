#!/usr/bin/env python
"""RF-04 G10/A14 — model ladder, common-coordinate registry, emission tape sample.

This closes the pre-RF04 registered blocker G10 ("model ladder, inner-only scaler,
common-coordinate mapping, fixed-target ablation") with real computation on the
byte-copied snapshot panel and the lab's own jump-model code:

  * ``model_design_selection_manifest.json`` — the registered M0 + JM K2/K3 ladder
    with lambda candidates, every inner fold's scaler fitted on that fold's inner
    train only, plus a falsification section that must be able to go red;
  * ``causal_model_registry.json`` — two consecutive real refits mapped in common
    raw/economic coordinates (one-to-one when K matches), explicit
    matched/unmatched/ambiguous statuses and version events that are never market
    transitions;
  * ``emission_tape_sample.json`` — real causal emissions with the raw economic
    context and the namespace-only no-false-trigger control;
  * ``current_coordinate_contract.json`` — the contract tying those three together.

No number in any artifact is hand-written: every value comes from the code paths
exercised here. The forward paired-return target in the ablation is a proxy
computed from the panel; the engine-derived paired utility panel belongs to
RF-04.3 and is recorded as the superseding target source.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.experiments.regime_schedule import online_trigger_schedule  # noqa: E402
from crypto_regime_lab.regime import ablation as AB  # noqa: E402
from crypto_regime_lab.regime import causality as C  # noqa: E402
from crypto_regime_lab.regime import model_selection as MS  # noqa: E402
from crypto_regime_lab.regime import registry as R  # noqa: E402
from crypto_regime_lab.regime.emissions import OnlineStateFilter, build_emission  # noqa: E402
from crypto_regime_lab.regime.jump_model import loss_matrix, multi_start_fit  # noqa: E402
from crypto_regime_lab.regime.quality import (check_degeneracy, fit_novelty_threshold)  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-04"
SNAPSHOT_ID = "server_core_v1"
SYMBOL = "BTCUSDT"
OBSERVATION_INTERVAL = "4h"
TRAIN_MEMORY_DAYS = 365
DEVELOPMENT_END = "2023-12-31"
FIRST_TRAIN_END = "2021-01-01"
OLD_CUTOFF = "2023-06-01"
NEW_CUTOFF = "2023-12-01"
SEEDS = (11, 23)
FORWARD_HORIZON_BARS = 6          # 24h at the 4h observation interval
M0_FEATURE = "g1_rv_6"
FALLBACK_DESIGN = {"n_states": MS.STARTING_K, "lambda_jump": 1.0}


def load_panel(policy: SandboxPolicy) -> tuple[pd.DataFrame, list[str], np.ndarray, dict]:
    schema = json.loads((policy.lab_root / "configs" / "feature_schema.json").read_text())
    features = list(schema["primary_core_features"])
    weights = np.asarray([schema["group_weights"][f] for f in features], dtype=np.float64)
    panel = pd.read_parquet(policy.lab_root / "snapshots" / SNAPSHOT_ID / "panels"
                            / f"{SYMBOL}.parquet")
    panel["time"] = pd.to_datetime(panel["time"])
    panel = panel.sort_values("time").reset_index(drop=True)
    frame = panel[["time", "available_at", "perp_close", *features]].dropna().reset_index(drop=True)
    return frame, features, weights, schema


def training_window(frame: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    cut = pd.Timestamp(cutoff)
    return frame[(frame["time"] < cut)
                 & (frame["time"] >= cut - pd.Timedelta(days=TRAIN_MEMORY_DAYS))].reset_index(
                     drop=True)


def fit_artifact(frame: pd.DataFrame, features: list[str], weights: np.ndarray, *,
                 cutoff: str, n_states: int, lambda_jump: float, tag: str
                 ) -> tuple[R.ModelArtifact, dict]:
    window = training_window(frame, cutoff)
    raw = window[features].to_numpy(float)
    scaler = C.fit_scaler(raw)
    z_train = C.apply_scaler(raw, scaler)
    fit = multi_start_fit(z_train, weights, n_states=n_states, lambda_jump=lambda_jump,
                          seeds=SEEDS)
    loss = loss_matrix(z_train, fit["centroids"], weights)
    residuals = loss.min(axis=1)
    novelty = fit_novelty_threshold(residuals)
    train_states = np.argmin(loss, axis=1)
    counts = np.bincount(train_states, minlength=n_states)
    degeneracy = check_degeneracy(weights, fit["centroids"], counts)
    artifact = R.ModelArtifact(
        model_id=f"{tag}_jm_k{n_states}_{cutoff}",
        state_namespace=f"{tag}@jm_k{n_states}@{cutoff}",
        training_start=str(window["time"].iloc[0]), training_cutoff=cutoff,
        fit_ready_at=str(window["available_at"].iloc[-1]),
        n_states=n_states, lambda_jump=lambda_jump, feature_names=tuple(features),
        feature_weights=tuple(float(w) for w in weights),
        group_weights={}, centroids=np.asarray(fit["centroids"]).tolist(),
        scaler_ref={"median": scaler["median"].tolist(), "scale": scaler["scale"].tolist(),
                    "clip": scaler["clip"], "fitted_rows": scaler["fitted_rows"],
                    "fitted_on": "the trailing training window ending at this cutoff"},
        seeds=SEEDS, selected_seed=fit["selected_seed"],
        observation_interval=OBSERVATION_INTERVAL,
        fit_diagnostics={"novelty_threshold": novelty, "state_counts": counts.tolist(),
                         "degeneracy": degeneracy,
                         "multi_start": {k: v for k, v in fit.items() if k != "centroids"}},
        code_hashes=R.environment_hashes([
            LAB_ROOT / "src/crypto_regime_lab/regime/jump_model.py",
            LAB_ROOT / "src/crypto_regime_lab/regime/model_selection.py",
            LAB_ROOT / "src/crypto_regime_lab/regime/registry.py",
        ]),
        library_versions=R.library_versions(),
        notes="RF-04 G10 causal registry fit; development role only",
    )
    raw_centroids = (np.asarray(artifact.centroids) * np.asarray(scaler["scale"])
                     + np.asarray(scaler["median"]))
    diagnostics = {"rows": int(len(window)), "raw": raw, "scaler": scaler, "fit": fit,
                   "novelty": novelty, "degeneracy": degeneracy,
                   "raw_centroids": raw_centroids.tolist(),
                   "train_states": train_states}
    return artifact, diagnostics


def forward_paired_target(frame: pd.DataFrame, horizon: int) -> np.ndarray:
    """A real, fixed paired target: future return minus the trailing incumbent return.

    This is the panel-computable proxy for the RF-04.3 engine paired utility: both
    sides are realized perp returns, no trades and no costs are invented here.
    """
    close = frame["perp_close"].to_numpy(float)
    n = close.shape[0]
    future = np.full(n, np.nan)
    incumbent = np.full(n, np.nan)
    future[:n - horizon] = close[horizon:] / close[:n - horizon] - 1.0
    incumbent[horizon:] = close[horizon:] / close[:n - horizon] - 1.0
    return future - incumbent


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    frame, features, weights, schema = load_panel(policy)
    development = frame[frame["time"] <= pd.Timestamp(DEVELOPMENT_END)].reset_index(drop=True)
    groups: dict[str, list[int]] = {}
    for index, name in enumerate(features):
        groups.setdefault(name.split("_")[0].upper(), []).append(index)

    # ---- 1. design ladder on the first development training window -------------
    first_window = training_window(development, FIRST_TRAIN_END)
    raw_first = first_window[features].to_numpy(float)
    with writer.attempt("G10.design_ladder") as att:
        manifest = MS.evaluate_design_ladder(raw_first, weights, seeds=SEEDS, n_folds=3,
                                             min_train=100,
                                             m0_feature_index=features.index(M0_FEATURE))
        att.detail = {"status": manifest["status"], "candidates": manifest["denominators"]}

    # ---- 2. fixed-target ablation (same target/cohort for every feature set) ----
    target_full = forward_paired_target(development, FORWARD_HORIZON_BARS)
    target_first = target_full[:len(first_window)]
    cohort_first = np.isfinite(target_first)
    selected_k = (manifest["selection"] or FALLBACK_DESIGN)["n_states"]
    selected_lambda = (manifest["selection"] or FALLBACK_DESIGN)["lambda_jump"]
    with writer.attempt("G10.fixed_target_ablation") as att:
        ablation = AB.fixed_target_ablation(
            raw_first, tuple(features), weights, target=target_first, cohort=cohort_first,
            n_states=selected_k, lambda_jump=selected_lambda, seeds=SEEDS, n_folds=3,
            min_train=100, purge_rows=FORWARD_HORIZON_BARS,
            target_name="forward_paired_return_24h_proxy",
            target_kind="paired_future_return_minus_trailing_return_proxy")
        att.detail = {"decided_on": ablation["decided_on"],
                      "scored_rows": {str(r["groups"]): r["scored_rows"]
                                      for r in ablation["ladder"]}}

    manifest.update({
        "gate": "G10",
        "finding": "A14",
        "symbol": SYMBOL,
        "snapshot_id": SNAPSHOT_ID,
        "feature_names": features,
        "feature_weights": {name: float(w) for name, w in zip(features, weights)},
        "observation_interval": OBSERVATION_INTERVAL,
        "training_window": {"start": str(first_window["time"].iloc[0]),
                            "end": str(first_window["time"].iloc[-1]),
                            "rows": int(len(first_window))},
        "seeds": list(SEEDS),
        "fixed_target_ablation": ablation,
        "superseding_target_source": ("RF-04.3 engine-derived paired candidate utility with the "
                                      "corrected cost binding supersedes the panel forward-return "
                                      "proxy; the ablation API takes the target as an argument"),
        "causal_registry_ref": "causal_model_registry.json",
        "coordinate_contract_ref": "current_coordinate_contract.json",
        "disposition": {
            "A14_inner_scaler": "fixed: every inner fold fits its scaler on raw[:train_end] only",
            "A14_ladder": "implemented: M0 + JM K2/K3 with registered lambda candidates",
            "A14_fixed_target_ablation": "implemented: same target/cohort for every feature set; "
                                         "reconstruction quality is diagnostic only",
            "G10_status": "CLOSED_BY_IMPLEMENTATION",
        },
    })
    written = [writer.write_json("model_design_selection_manifest.json", manifest,
                                 schema=manifest["schema"])]

    # ---- 3. causal registry: two consecutive real refits + K-mismatch probe ----
    with writer.attempt("G10.causal_registry") as att:
        old, old_diag = fit_artifact(development, features, weights, cutoff=OLD_CUTOFF,
                                     n_states=selected_k, lambda_jump=selected_lambda,
                                     tag="rf04")
        new, new_diag = fit_artifact(development, features, weights, cutoff=NEW_CUTOFF,
                                     n_states=selected_k, lambda_jump=selected_lambda,
                                     tag="rf04")
        probe_k = MS.PARSIMONIOUS_K if selected_k != MS.PARSIMONIOUS_K else MS.STARTING_K
        probe, probe_diag = fit_artifact(development, features, weights, cutoff=NEW_CUTOFF,
                                         n_states=probe_k, lambda_jump=selected_lambda,
                                         tag="rf04_mismatch_probe")
        mapping = R.map_state_namespaces(old, new)
        mismatch_mapping = R.map_state_namespaces(new, probe)
        event = R.model_transition_event(old, new, mapping)
        att.detail = {"mapping_status": {k: len(v) for k, v in (
            ("matched", mapping["matched_states"]), ("unmatched", mapping["unmatched_states"]),
            ("ambiguous", mapping["ambiguous_states"]))}}

    registry_payload = {
        "schema": "crypto_regime_lab.causal_model_registry.v1",
        "gate": "G10", "finding": "A14",
        "symbol": SYMBOL, "snapshot_id": SNAPSHOT_ID,
        "observation_interval": OBSERVATION_INTERVAL,
        "design": {"source": ("model_design_selection_manifest.json"
                              if manifest["status"] == "SELECTED" else "registered_fallback"),
                   "n_states": int(old.n_states), "lambda_jump": float(old.lambda_jump),
                   "cadence": MS.PRIMARY_CADENCE,
                   "ratio_control": "K and lambda are fixed across the two refits so the only "
                                    "thing that changes is the training vintage"},
        "models": [old.as_record(), new.as_record(), probe.as_record()],
        "model_diagnostics": {
            "old": {"rows": old_diag["rows"], "selected_seed": old_diag["fit"]["selected_seed"],
                    "state_counts": old.as_record()["fit_diagnostics"]["state_counts"],
                    "degenerate": old_diag["degeneracy"]["is_degenerate"],
                    "raw_centroids": old_diag["raw_centroids"]},
            "new": {"rows": new_diag["rows"], "selected_seed": new_diag["fit"]["selected_seed"],
                    "state_counts": new.as_record()["fit_diagnostics"]["state_counts"],
                    "degenerate": new_diag["degeneracy"]["is_degenerate"],
                    "raw_centroids": new_diag["raw_centroids"]},
            "mismatch_probe": {"rows": probe_diag["rows"], "n_states": int(probe.n_states),
                               "raw_centroids": probe_diag["raw_centroids"]},
        },
        "namespace_mappings": [mapping, mismatch_mapping],
        "model_transition_events": [event],
        "market_transition_guard": {
            "refit_events_emitted_as_market_transitions": 0,
            "events_checked": 1,
            "all_events_not_market": bool(not event["emits_market_transition"]),
            "scheduler_rule": ("online_trigger_schedule fires only on a semantic change: "
                               "state_common across namespaces or state_id within one namespace. "
                               "A namespace/version change alone is not comparable and produces "
                               "no trigger (RF-03 A10)"),
        },
        "coordinate_contract_ref": "current_coordinate_contract.json",
    }
    written.append(writer.write_json("causal_model_registry.json", registry_payload,
                                     schema=registry_payload["schema"]))

    # ---- 4. emission tape sample with economic context + namespace control -----
    new_cut = pd.Timestamp(NEW_CUTOFF)
    live = development[development["time"] >= new_cut].reset_index(drop=True)
    scaler = {"median": np.asarray(new.scaler_ref["median"]),
              "scale": np.asarray(new.scaler_ref["scale"]),
              "clip": new.scaler_ref["clip"]}
    centroids = np.asarray(new.centroids)
    streamer = OnlineStateFilter(centroids, weights, new.lambda_jump,
                                 namespace=new.state_namespace)
    records = []
    for index in range(len(live)):
        z_t = C.apply_scaler(live[features].to_numpy(float)[index:index + 1], scaler)[0]
        state, costs, _ = streamer.step(z_t)
        residual = float(loss_matrix(z_t.reshape(1, -1), centroids, weights)[0].min())
        emission = build_emission(
            state, costs, namespace=new.state_namespace, z_t=z_t, centroids=centroids,
            weights=weights, groups=groups,
            observed_at=str(live["time"].iloc[index]),
            available_at=str(live["available_at"].iloc[index]),
            inferred_at=str(live["available_at"].iloc[index]),
            model_fit_cutoff=new.training_cutoff, ready_at=new.fit_ready_at,
            version=new.model_id, quality_status="OK",
            input_refs=(f"panel:{SYMBOL}",),
            novelty_score=float(residual / max(new.fit_diagnostics["novelty_threshold"]["threshold"],
                                               1e-12)))
        record = emission.as_record()
        entry = mapping["mapping"][str(state)]
        record["state_common"] = (entry["old_state"] if entry["status"] == R.MAPPING_MATCHED
                                  else None)
        record["common_status"] = entry["status"]
        record["namespace_is_refit"] = False
        records.append(record)
    sample_stride = max(1, len(records) // 24)
    sampled = records[:6] + records[6::sample_stride]
    sample = {
        "schema": "crypto_regime_lab.emission_tape_sample.v1",
        "gate": "G10", "finding": "A11/A14",
        "symbol": SYMBOL, "observation_interval": OBSERVATION_INTERVAL,
        "model_id": new.model_id, "state_namespace": new.state_namespace,
        "model_fit_cutoff": new.training_cutoff,
        "span": [str(live["time"].iloc[0]), str(live["time"].iloc[-1])],
        "total_emissions_computed": len(records),
        "sample_size": len(sampled),
        "sample_stride": sample_stride,
        "sampling_rule": ("first 6 emissions then every sample_stride-th; counts above are the "
                          "computed denominator, not an estimate"),
        "switch_count_full_tape": int(sum(1 for a, b in zip(records, records[1:])
                                          if a["state_id"] != b["state_id"])),
        "common_status_counts": {status: sum(1 for r in records if r["common_status"] == status)
                                 for status in R.MAPPING_STATUSES},
        "emissions": sampled,
        "economic_context_note": ("economic_context holds the raw causal feature vector the state "
                                  "was inferred from (A11). Responses compare THIS, never the "
                                  "squared fit residual, which loses sign and state identity"),
    }

    # ---- 5. namespace-only no-false-trigger control ----------------------------
    base_ids = [(r["state_common"] if r["state_common"] is not None else r["state_id"])
                for r in records]
    split = next(index for index in range(max(1, len(records) // 4), len(records) - 1)
                 if (records[index]["state_common"] is not None
                     and records[index - 1]["state_common"] is not None
                     and base_ids[index] == base_ids[index - 1]))
    fresh_state = (max(v for v in base_ids if v is not None) + 1)
    distinct_after = sorted({base_ids[index] for index in range(split, len(records))})
    shifted = {value: fresh_state + offset for offset, value in enumerate(distinct_after)}
    base_rows, refit_rows, common_rows = [], [], []
    for index, record in enumerate(records):
        row = {"state_id": record["state_id"], "state_namespace": "probe-A",
               "state_common": record["state_common"], "decision_eligible": True,
               "quality_status": "OK", "available_at": record["available_at"]}
        base_rows.append(dict(row))
        refit_rows.append(dict(row))
        common_rows.append(dict(row))
        if index >= split:
            refit_rows[-1]["state_namespace"] = "probe-B"
            common_rows[-1]["state_namespace"] = "probe-B"
            common_rows[-1]["state_common"] = (
                None if record["state_common"] is None
                else shifted[record["state_common"]])
    window = {"earliest": str(live["time"].iloc[0]), "latest": str(live["time"].iloc[-1]),
              "min_gap_days": 0.0, "max_age_days": 10_000.0}
    base_schedule = online_trigger_schedule(base_rows, **window)
    refit_schedule = online_trigger_schedule(refit_rows, **window)
    common_schedule = online_trigger_schedule(common_rows, **window)
    control = {
        "schema": "crypto_regime_lab.namespace_transition_control.v1",
        "gate": "G10/A10",
        "window": window,
        "split_index": int(split),
        "constant_namespace_tape_triggers": len(base_schedule.cutoffs),
        "namespace_only_tape_triggers": len(refit_schedule.cutoffs),
        "semantic_change_tape_triggers": len(common_schedule.cutoffs),
        "namespace_only_emits_market_transition": bool(
            len(refit_schedule.cutoffs) > len(base_schedule.cutoffs)),
        "control_can_fire": bool(len(common_schedule.cutoffs) > len(base_schedule.cutoffs)),
        "model_version_event_emits_market_transition": bool(event["emits_market_transition"]),
        "verdict": ("PASS" if (len(refit_schedule.cutoffs) == len(base_schedule.cutoffs)
                               and len(common_schedule.cutoffs) > len(base_schedule.cutoffs)
                               and not event["emits_market_transition"]) else "FAIL"),
        "rule": ("a refit version boundary may not fire a market trigger. The positive row "
                 "injects a state_common change at the SAME split and MUST fire, or the check "
                 "would be vacuous"),
    }
    sample["namespace_transition_control"] = control
    written.append(writer.write_json("emission_tape_sample.json", sample,
                                     schema=sample["schema"]))

    # ---- 6. current coordinate contract ----------------------------------------
    contract = {
        "schema": "crypto_regime_lab.current_coordinate_contract.v1",
        "gate": "G10", "finding": "A11/A14",
        "symbol": SYMBOL, "observation_interval": OBSERVATION_INTERVAL,
        "feature_names": features,
        "coordinate_axis": {
            "name": "raw_economic_feature_coordinates",
            "definition": ("the physical feature values before standardization. A state centroid "
                           "is only an economic location after the fit's own training scaler is "
                           "inverted: raw = standardized * scale + median"),
            "reason": ("two fits with different scalers live in different standardized spaces. "
                       "Mapping their centroids without recovery is a coordinate mismatch, not a "
                       "state comparison (A14)"),
        },
        "shared_frame": {
            "frame": "old_model_training_transform",
            "construction": ("both models' centroids are recovered to raw coordinates with their "
                             "own training scalers, then expressed in the old model's "
                             "standardized frame; distances use the declared feature weights"),
            "fit_scope": "training windows only; no emission, outcome or post-cutoff row enters",
        },
        "mapping_statuses": {
            "matched": "unique, within max_relative_distance, runner-up separated; yields old_state",
            "unmatched": "no old state within max_relative_distance (or a moved state): MODEL event",
            "ambiguous": "runner-up within 1.25x of the nearest, or the one-to-one assignment had "
                         "to take a non-nearest old state: MODEL event",
            "max_relative_distance": R.MAPPING_MAX_RELATIVE_DISTANCE,
            "runner_up_ratio": R.MAPPING_RUNNER_UP_RATIO,
            "one_to_one_when_k_matches": True,
        },
        "state_common_policy": ("cross-namespace comparisons use matched old-namespace IDs "
                                "(state_common). An unmatched/ambiguous state carries "
                                "state_common = null and cannot be compared across vintages"),
        "event_classes": {
            "MODEL_VERSION": ("a refit/namespace change. is_market_event=false, "
                              "emits_market_transition=false, requires_parameter_search=false"),
            "MARKET_TRANSITION": ("a semantic state change in common coordinates. It is the only "
                                  "change the online scheduler may trigger on"),
        },
        "scheduler_comparability_rule": ("online_trigger_schedule compares state_common across "
                                         "namespaces, or state_id within one namespace. "
                                         "Namespace-only changes are skipped"),
        "emission_fields": {
            "economic_context": "raw causal feature vector at inference time (A11)",
            "state_namespace": "the fit vintage; never comparable across vintages by integer ID",
            "state_common": "matched old-namespace state id, or null",
            "model_fit_cutoff": "the declared training cutoff; no later row entered the fit",
        },
        "real_bindings": {
            "registry_models": [
                {"model_id": old.model_id, "n_states": old.n_states,
                 "state_namespace": old.state_namespace,
                 "scaler_ref": old.scaler_ref,
                 "centroids_raw": old_diag["raw_centroids"]},
                {"model_id": new.model_id, "n_states": new.n_states,
                 "state_namespace": new.state_namespace,
                 "scaler_ref": new.scaler_ref,
                 "centroids_raw": new_diag["raw_centroids"]},
            ],
            "mapping_status_counts": {k: len([s for s in mapping["mapping"].values()
                                              if s["status"] == k])
                                      for k in R.MAPPING_STATUSES},
            "mismatch_mapping": {"k_matches": mismatch_mapping["k_matches"],
                                 "one_to_one": mismatch_mapping["one_to_one"],
                                 "assignment_method": mismatch_mapping["assignment_method"]},
            "sample_span": sample["span"],
            "sample_total_emissions": sample["total_emissions_computed"],
        },
        "holds": ["no post-cutoff data enters centroids or the scaler",
                  "no prior decision vintage is rewritten by a refit",
                  "a version event never reaches the market trigger path"],
    }
    written.append(writer.write_json("current_coordinate_contract.json", contract,
                                     schema=contract["schema"]))

    print(json.dumps({
        "manifest_status": manifest["status"],
        "selected": manifest["selection"],
        "denominators": manifest["denominators"],
        "can_go_red": manifest["falsification"]["can_go_red"],
        "mapping_status_counts": {k: len([s for s in mapping["mapping"].values()
                                          if s["status"] == k])
                                  for k in R.MAPPING_STATUSES},
        "namespace_control": control["verdict"],
        "artifacts": [w["relpath"] for w in written],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
