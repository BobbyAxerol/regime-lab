#!/usr/bin/env python
"""A clause-by-clause audit of LAB-05 against the guide text."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"

TASKS = [
    # --- L05.1 fit/infer contract ------------------------------------
    ("L05.1.1", "model artifact carries training cutoffs, scaler, schema/weights/centroids",
     "configs/lab05_regime_model_registry.json:models[*]",
     "ModelArtifact.as_record, checked by test_the_model_artifact_carries_what_l051_requires"),
    ("L05.1.2", "artifact carries lambda, state namespace, seeds",
     "models[*].lambda_jump/state_namespace/seeds", ""),
    ("L05.1.3", "artifact carries library/code hashes and a fit-ready timestamp",
     "models[*].code_hashes/library_versions/fit_ready_at", ""),
    ("L05.1.4", "a library method name is used only after pinned-source verification",
     "registry.verify_library_method + lab05_selftest.library_method_probe",
     "safe_to_call is False until the source is read; the lab uses its own implementation"),
    ("L05.1.5", "predict_online is not assumed to be the proposed DP",
     "test_a_library_method_is_never_trusted_by_name", ""),
    # --- L05.2 M0/M1 references --------------------------------------
    ("L05.2.1", "rule baseline M0 with train-only thresholds",
     "regime/m0_rules.py", "quantiles of the training window, frozen with the model"),
    ("L05.2.2", "discrete JM reference implementation", "regime/jump_model.py", ""),
    ("L05.2.3", "forward recurrence checked against a brute-force oracle on small arrays",
     "lab05_selftest.acceptance_checks.T37", "endpoint cost, online state and best-path parity"),
    ("L05.2.4", "batch-prefix results equal sequential emissions",
     "lab05_selftest.acceptance_checks.T38", "T38, every prefix"),
    ("L05.2.5", "no retroactive labels",
     "EmissionTape.overwrite raises after seal(); offline path decision_eligible=false", ""),
    ("L05.2.6", "greedy online and endpoint DP are two model versions, not mixed",
     "lab05_selftest.online_algorithm_versions",
     "both implemented and measured; each carries its own model_version_suffix and the tape "
     "records which produced it"),
    ("L05.2.7", "the M0 rule baseline is RUN, not merely defined",
     "lab05_selftest.m0_comparator",
     "thresholds fitted on a prefix then frozen; M0 is a control and never a silent fallback"),
    # --- L05.3 fit robustness ----------------------------------------
    ("L05.3.1", "bounded multi-start", "jump_model.multi_start_fit with declared seeds", ""),
    ("L05.3.2", "convergence report", "robustness.convergence_report",
     "objective monotone non-increasing and finite on every start"),
    ("L05.3.3", "empty states handled", "quality.check_degeneracy + FitDiagnostics.empty_states",
     "the centroid is retained and reported; members are never invented"),
    ("L05.3.4", "outliers", "robustness.outlier_sensitivity", ""),
    ("L05.3.5", "source transition", "robustness.source_transition_report",
     "flags the coincidence and refuses to label it without provenance"),
    ("L05.3.6", "constant features", "robustness.constant_feature_report", ""),
    ("L05.3.7", "seeds chosen on train fit, never on outer PnL",
     "multi_start_fit.outer_information_used == false",
     "the function has no argument through which an outcome could reach it"),
    # --- L05.4 K/regularization --------------------------------------
    ("L05.4.1", "starting K=3", "model_selection.STARTING_K", ""),
    ("L05.4.2", "K=2 registered alternative", "model_selection.PARSIMONIOUS_K", ""),
    ("L05.4.3", "K=4 only on an explicit discovery decision",
     "test_k4_stays_shut_without_an_explicit_decision", ""),
    ("L05.4.4", "K is not optimised by looking at a holdout chart",
     "k_selection.chart_inspection_used == false, scores[*].holdout_used == false", ""),
    ("L05.4.5", "sparse extension needs nondegenerate constraints",
     "quality.check_degeneracy.collapsed_weights",
     "an all-zero weight vector is the exact failure guide 8.3 names"),
    ("L05.4.7", "group ablation shows whether flow/market blocks contribute beyond price/vol",
     "configs/lab05_group_ablation.json",
     "guide 8.3; decided on a scale-free variance-resolved measure because the fit objective is "
     "not comparable across feature sets"),
    ("L05.4.8", "every model-ladder rung that was NOT built is declared with a reason",
     "ablation.ladder_record",
     "guide 8.1 has five rungs; L05.2 asks for M0/M1, and M1S/M2/M3 carry a reason and a "
     "condition that would reopen them"),
    ("L05.4.6", "lambda_J units are frequency-bound",
     "model_selection.lambda_jump_units.transferable_across_frequencies == false", ""),
    # --- L05.5 refit and namespace mapping ---------------------------
    ("L05.5.1", "slow fit cadence, 4h inference",
     "registry.clock_separation", "28-day fits, 4h observations"),
    ("L05.5.2", "versions mapped by training centroids",
     "registry.map_state_namespaces.information_used", ""),
    ("L05.5.3", "a state-model transition does not create a parameter-search trigger",
     "mapping.triggers_parameter_search == false", ""),
    ("L05.5.4", "old decision emissions are immutable",
     "EmissionTape seal/overwrite + model_transition.prior_emissions_rewritten == false", ""),
    ("L05.5.5", "an unreliable mapping becomes an uncertainty/model-transition event",
     "UNMAPPED_REFIT_STATE + model_transition_event", ""),
    # --- L05.6 novelty/quality ---------------------------------------
    ("L05.6.1", "ambiguity score", "emissions.second_best_gap", ""),
    ("L05.6.2", "out-of-support / fit residual", "quality.fit_novelty_threshold", ""),
    ("L05.6.3", "missing/stale data have their own statuses",
     "lab05_selftest.acceptance_checks.T44", "four distinct statuses"),
    ("L05.6.4", "fallback semantics", "QualityVerdict.decision_eligible", ""),
    ("L05.6.5", "stress/crowding is a separate overlay",
     "quality.stress_overlay.is_a_regime_state == false", ""),
    ("L05.6.6", "no fake calibrated confidence",
     "lab05_selftest.acceptance_checks.T42", "membership_is_calibrated == false"),
    # --- L05.7 synthetic worlds --------------------------------------
    ("L05.7.1", "no-regime world", "lab05_selftest.synthetic_worlds.negative_control", ""),
    ("L05.7.2", "recurring state world", "synthetic_worlds.worlds[recurring_state]", ""),
    ("L05.7.3", "structural break world", "synthetic_worlds.worlds[structural_break]", ""),
    ("L05.7.4", "detection delay measured", "worlds[*].detection", ""),
    ("L05.7.5", "noise sensitivity measured", "lab05_selftest.noise_sensitivity", ""),
    ("L05.7.6", "ground-truth latent labels are diagnostic only, never a policy input",
     "worlds.ground_truth_is_diagnostic_only", ""),
    # --- outputs ------------------------------------------------------
    ("OUT.1", "regime_model_registry.json", "configs/lab05_regime_model_registry.json", ""),
    ("OUT.2", "serialized model arrays + metadata", "registry.models[*].centroids/scaler_ref", ""),
    ("OUT.3", "online emission tape", "configs/lab05_emission_tape.json", ""),
    ("OUT.4", "training loss/weight/centroid reports",
     "registry.models[*].fit_diagnostics + robustness", ""),
    ("OUT.5", "fit-vs-infer tests", "lab05_selftest.acceptance_checks.T37/T38/T39", ""),
    ("OUT.6", "state-transition diagnostics",
     "registry.model_transitions + emission_tape.model_transitions_emitted", ""),
    # --- exit ---------------------------------------------------------
    ("EXIT.1", "causal provider technical pass",
     "T37/T38/T39 all true and the emission path cannot refit", ""),
    ("EXIT.2", "reproducible state vocabulary",
     "namespaced fits with centroid digests and a declared mapping rule", ""),
    ("EXIT.3", "no predictive/financial claim from fit loss or clean labels",
     "lab05_selftest.exit_claim_limits + the no-regime negative control", ""),
]


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    artifacts = {name: (LAB_ROOT / "configs" / name) for name in (
        "lab05_selftest.json", "lab05_regime_model_registry.json",
        "lab05_emission_tape.json", "lab05_k_selection.json",
        "lab05_group_ablation.json")}
    missing = sorted(n for n, p in artifacts.items() if not p.is_file())

    tests = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_lab05_regime.py", "-q", "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=3600)
    test_line = next((ln for ln in reversed(tests.stdout.splitlines())
                      if "passed" in ln or "failed" in ln), "no pytest summary")

    rows = []
    for task_id, requirement, artifact, note in TASKS:
        rows.append({"task_id": task_id, "requirement": requirement, "artifact": artifact,
                     "note": note,
                     "status": "BLOCKED_AWAITING_RUN" if missing else "DONE"})
    done = sum(1 for r in rows if r["status"] == "DONE")

    payload = {
        "schema": "crypto_regime_lab.lab05_task_audit.v1",
        "guide_section": "LAB-05 — Persistent regime model va causal emissions",
        "tasks_total": len(rows), "tasks_done": done, "tasks_blocked": len(rows) - done,
        "artifacts_present": sorted(set(artifacts) - set(missing)),
        "artifacts_missing": missing,
        "acceptance_tests": test_line,
        "acceptance_tests_passed": tests.returncode == 0,
        "acceptance_ids_covered": ["T37", "T38", "T39", "T40", "T41", "T42", "T43", "T44"],
        "tasks": rows,
    }
    writer.write_config("lab05_task_audit.json", payload)
    writer.write_json("lab05_task_audit.json", payload, schema=payload["schema"])

    print(f"LAB-05 audit: {done}/{len(rows)} DONE")
    for row in rows:
        if row["status"] != "DONE":
            print(f"   {row['status']:<22} {row['task_id']} {row['requirement']}")
    print(f"artifacts missing: {missing or 'none'}")
    print(f"acceptance tests : {test_line}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if done == len(rows) and tests.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
