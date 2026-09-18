#!/usr/bin/env python
"""LAB-05 L05.2/L05.6/L05.7 — the checks that do not need market data.

Each writes what it MEASURED, not whether it liked the answer. The synthetic
worlds in particular are negative controls: the no-regime world exists so that a
model which manufactures structure is caught, and the number it produces is
reported whether or not it flatters the model.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.regime import causality as C  # noqa: E402
from crypto_regime_lab.regime import registry as R  # noqa: E402
from crypto_regime_lab.regime import worlds as W  # noqa: E402
from crypto_regime_lab.regime.emissions import (batch_stream_parity,  # noqa: E402
                                                membership_scores)
from crypto_regime_lab.regime import m0_rules as M0  # noqa: E402
from crypto_regime_lab.regime.jump_model import (compare_online_algorithms,  # noqa: E402
                                                 forward_filter, loss_matrix,
                                                 multi_start_fit)
from crypto_regime_lab.regime.oracle import (exhaustive_best_path,  # noqa: E402
                                             exhaustive_endpoint_costs,
                                             exhaustive_online_states)
from crypto_regime_lab.regime.quality import assess, check_degeneracy  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
FIT_FUNCTIONS = {"fit_jump_model", "multi_start_fit", "fit_scaler", "causal_fit", "choose_k"}


def t37_oracle(trials: int = 8, seed: int = 41) -> dict:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(trials):
        n_obs = int(rng.integers(3, 9))
        n_states = int(rng.integers(2, 4))
        n_features = int(rng.integers(2, 5))
        lam = float(rng.uniform(0.0, 2.0))
        z = rng.normal(size=(n_obs, n_features))
        mu = rng.normal(size=(n_states, n_features))
        w = rng.random(n_features)
        loss = loss_matrix(z, mu, w)
        raw = forward_filter(loss, lam, normalise=False, with_offline_path=True)
        norm = forward_filter(loss, lam, normalise=True, with_offline_path=True)
        oracle_costs = exhaustive_endpoint_costs(loss, lam)
        oracle_path, _ = exhaustive_best_path(loss, lam)
        oracle_online = exhaustive_online_states(loss, lam)
        rows.append({
            "n_obs": n_obs, "n_states": n_states, "lambda_jump": lam,
            "endpoint_costs_match": bool(np.allclose(raw.raw_costs, oracle_costs,
                                                     rtol=1e-12, atol=1e-12)),
            "online_states_match": bool(np.array_equal(norm.online_states, oracle_online)),
            "best_path_match": bool(np.array_equal(raw.offline_path, oracle_path)),
            "normalisation_preserves_argmin": bool(
                np.array_equal(raw.online_states, norm.online_states)),
            "normalisation_preserves_differences": bool(np.allclose(
                raw.raw_costs - raw.raw_costs.min(axis=1, keepdims=True),
                norm.costs - norm.costs.min(axis=1, keepdims=True), atol=1e-12)),
            "online_differs_from_offline": bool(
                not np.array_equal(norm.online_states, raw.offline_path)),
        })
    return {
        "schema": "crypto_regime_lab.t37_dp_oracle.v1",
        "trials": rows,
        "all_endpoint_costs_match": all(r["endpoint_costs_match"] for r in rows),
        "all_online_states_match": all(r["online_states_match"] for r in rows),
        "all_best_paths_match": all(r["best_path_match"] for r in rows),
        "normalisation_is_safe": all(r["normalisation_preserves_argmin"]
                                     and r["normalisation_preserves_differences"] for r in rows),
        "cases_where_causal_and_offline_disagree": sum(
            r["online_differs_from_offline"] for r in rows),
        "why_that_matters": ("where they disagree, the offline path rewrote a label using data "
                             "that did not exist when the decision was taken. That is why the "
                             "offline path carries decision_eligible=false (guide 8.4)"),
    }


def t38_parity(seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    rows = []
    for n_obs, n_states, n_features in ((20, 2, 3), (150, 3, 8), (500, 3, 4)):
        z = rng.normal(size=(n_obs, n_features))
        mu = rng.normal(size=(n_states, n_features))
        w = rng.random(n_features)
        rows.append(batch_stream_parity(z, mu, w, float(rng.uniform(0.2, 1.5))))
    return {
        "schema": "crypto_regime_lab.t38_batch_stream.v1",
        "cases": rows,
        "all_states_identical": all(r["states_identical"] for r in rows),
        "all_costs_identical": all(r["costs_identical"] for r in rows),
        "all_prefix_vintages_stable": all(r["prefix_vintages_stable"] for r in rows),
    }


def t39_mutation(seed: int = 43) -> dict:
    rng = np.random.default_rng(seed)
    raw = rng.normal(size=(500, 4))
    raw[250:, 0] += 2.0
    control = C.run_control_pair(raw, 250)
    return {"schema": "crypto_regime_lab.t39_future_suffix.v1", **control}


def t40_degeneracy() -> dict:
    zero_weights = check_degeneracy(np.zeros(4), np.random.default_rng(1).normal(size=(3, 4)))
    identical = check_degeneracy(np.ones(4) / 4, np.zeros((3, 4)))
    empty = check_degeneracy(np.ones(4) / 4,
                             np.random.default_rng(2).normal(size=(3, 4)),
                             np.array([100, 0, 40]))
    healthy = check_degeneracy(np.ones(4) / 4,
                               np.random.default_rng(3).normal(size=(3, 4)) * 5,
                               np.array([100, 80, 40]))
    verdict = assess(costs=np.array([0.1, 0.1, 0.1]), fit_residual=0.0,
                     novelty_threshold=1.0, degeneracy=zero_weights)
    return {
        "schema": "crypto_regime_lab.t40_degeneracy.v1",
        "all_weights_zero": zero_weights,
        "identical_centroids": identical,
        "empty_state": empty,
        "healthy_model": healthy,
        "degenerate_model_emits": verdict.as_record(),
        "healthy_is_usable": healthy["usable_for_decisions"],
        "degenerate_is_blocked": not zero_weights["usable_for_decisions"],
        "no_fake_confidence": verdict.decision_eligible is False,
    }


def t41_permutation(seed: int = 44) -> dict:
    """A refit that returns the same states under permuted IDs must map, not alarm."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=(400, 4))
    weights = np.full(4, 0.25)
    fit = multi_start_fit(z, weights, n_states=3, lambda_jump=1.0, seeds=(1, 2, 3))
    centroids = np.asarray(fit["centroids"])
    permutation = [2, 0, 1]
    permuted = centroids[permutation]

    def _artifact(name, cents):
        return R.ModelArtifact(
            model_id=name, state_namespace=name, training_start="2020-01-01",
            training_cutoff="2021-01-01", fit_ready_at="2021-01-01T00:00:00Z",
            n_states=3, lambda_jump=1.0, feature_names=("a", "b", "c", "d"),
            feature_weights=tuple(weights), group_weights={}, centroids=cents.tolist(),
            scaler_ref={}, seeds=(1, 2, 3), selected_seed=1, observation_interval="4h")

    old = _artifact("model_A", centroids)
    new = _artifact("model_B", permuted)
    mapping = R.map_state_namespaces(old, new)
    recovered = [mapping["mapping"][str(k)]["old_state"] for k in range(3)]
    transition = R.model_transition_event(old, new, mapping)

    # a genuinely different model: one state moved far away
    shifted = centroids.copy()
    shifted[1] = shifted[1] + 40.0
    far = _artifact("model_C", shifted)
    far_mapping = R.map_state_namespaces(old, far)

    return {
        "schema": "crypto_regime_lab.t41_namespace_permutation.v1",
        "true_permutation": permutation,
        "recovered_permutation": recovered,
        "permutation_recovered": recovered == permutation,
        "all_states_mapped": mapping["all_states_mapped"],
        "declared_market_transition": mapping["is_market_transition"],
        "triggers_parameter_search": mapping["triggers_parameter_search"],
        "transition_event": transition,
        "genuinely_moved_state_is_unmapped": bool(far_mapping["unmapped_states"]),
        "far_mapping_unmapped_states": far_mapping["unmapped_states"],
        "why_both_cases": ("a permutation must map cleanly, and a state that really moved must "
                           "NOT be quietly mapped onto its nearest neighbour. Only checking the "
                           "first would pass a mapper that maps everything"),
    }


def t42_membership() -> dict:
    costs = np.array([0.10, 0.35, 2.40])
    scores = membership_scores(costs)
    return {
        "schema": "crypto_regime_lab.t42_membership.v1",
        "state_costs": costs.tolist(),
        "membership_score": scores.tolist(),
        "sums_to_one": bool(np.isclose(scores.sum(), 1.0)),
        "field_name": "membership_score",
        "is_named_probability": False,
        "calibrated": False,
        "calibration_evidence": None,
        "rule": ("softmax(-cost) sums to one, which is exactly why it is tempting to call it a "
                 "probability. Nothing here relates it to realised outcomes, so the schema names "
                 "it a membership score and carries membership_is_calibrated=false (guide 8.5)"),
    }


def t43_no_auto_retrain() -> dict:
    """Structural, not behavioural: the inference path must not be ABLE to refit.

    A test that ran inference and observed no refit would only show that this
    input did not trigger one. Reading the call graph shows none can.
    """
    rows = {}
    for name in ("emissions.py", "quality.py", "jump_model.py"):
        path = LAB_ROOT / "src" / "crypto_regime_lab" / "regime" / name
        tree = ast.parse(path.read_text())
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
        rows[name] = sorted(called & FIT_FUNCTIONS)
    inference_modules = ("emissions.py", "quality.py")
    return {
        "schema": "crypto_regime_lab.t43_no_auto_retrain.v1",
        "fit_functions_watched": sorted(FIT_FUNCTIONS),
        "calls_found": rows,
        "inference_path_calls_no_fit": all(not rows[m] for m in inference_modules),
        "note": ("jump_model.py legitimately contains the fit itself; what matters is that the "
                 "INFERENCE modules cannot reach it. A regime change therefore cannot start a "
                 "retrain, and a retrain is a scheduled event (guide 8.6, T43)"),
    }


def t44_novelty_vs_missing() -> dict:
    costs = np.array([0.2, 0.9, 1.4])
    threshold = 1.0
    novel = assess(costs=costs, fit_residual=5.0, novelty_threshold=threshold)
    missing = assess(costs=costs, fit_residual=5.0, novelty_threshold=threshold,
                     missing_features=("g2_taker_imbalance",))
    stale = assess(costs=costs, fit_residual=0.1, novelty_threshold=threshold,
                   model_age_seconds=1e9, max_model_age_seconds=1e6)
    ok = assess(costs=costs, fit_residual=0.1, novelty_threshold=threshold)
    return {
        "schema": "crypto_regime_lab.t44_novelty_vs_missing.v1",
        "novel_observation": novel.as_record(),
        "same_residual_but_missing_input": missing.as_record(),
        "stale_model": stale.as_record(),
        "healthy": ok.as_record(),
        "statuses_are_distinct": len({novel.status, missing.status, stale.status, ok.status}) == 4,
        "missing_wins_over_novelty": missing.status == "MISSING_DATA",
        "key_case": ("the novel and the missing case are given the IDENTICAL fit residual. Only "
                     "the presence of inputs separates them, which is precisely the confusion "
                     "T44 asks the lab to rule out"),
    }


def synthetic_worlds(lambda_jump: float = 1.0, seeds=(1, 2, 3)) -> dict:
    rows = []
    for maker in (W.no_regime_world, W.recurring_state_world, W.structural_break_world):
        world = maker()
        weights = np.full(world.z.shape[1], 1.0 / world.z.shape[1])
        fit = multi_start_fit(world.z, weights, n_states=3, lambda_jump=lambda_jump, seeds=seeds)
        result = forward_filter(loss_matrix(world.z, fit["centroids"], weights), lambda_jump)
        rows.append({
            **world.as_record(),
            "emitted_switches": result.switches(),
            "detection": W.detection_delay(result.online_states, world.latent),
            "agreement": W.label_agreement(result.online_states, world.latent),
            "states_used": sorted(set(result.online_states.tolist())),
        })
    no_regime = next(r for r in rows if r["name"] == "no_regime")
    return {
        "schema": "crypto_regime_lab.synthetic_worlds.v1",
        "worlds": rows,
        "negative_control": {
            "world": "no_regime",
            "true_switches": no_regime["latent_switches"],
            "emitted_switches": no_regime["emitted_switches"],
            "finding": (f"a K=3 jump model fitted on structureless noise still emitted "
                        f"{no_regime['emitted_switches']} state changes where the truth has "
                        f"{no_regime['latent_switches']}. Persistent-looking states are NOT "
                        "evidence of regimes, and no chart of these labels should be read as one"),
        },
        "ground_truth_use": W.GROUND_TRUTH_IS_DIAGNOSTIC_ONLY,
    }


def online_algorithm_versions(seed: int = 61) -> dict:
    """L05.2 — greedy online and endpoint DP are two MODEL VERSIONS, never mixed."""
    rng = np.random.default_rng(seed)
    rows = []
    for n_obs, lam in ((300, 0.5), (300, 2.0), (300, 6.0)):
        z = rng.normal(size=(n_obs, 4))
        mu = rng.normal(size=(3, 4)) * 1.5
        w = np.full(4, 0.25)
        rows.append({"lambda_jump": lam,
                     **compare_online_algorithms(loss_matrix(z, mu, w), lam)})
    return {
        "schema": "crypto_regime_lab.online_versions.v1",
        "comparisons": [{k: v for k, v in r.items() if k != "schema"} for r in rows],
        "greedy_always_switches_at_least_as_much": all(
            r["greedy"]["switches"] >= r["endpoint_dp"]["switches"] for r in rows),
        "never_identical_at_a_real_penalty": all(
            not r["identical"] for r in rows if r["lambda_jump"] > 0),
        "reading": ("the jump penalty is exactly what separates them: at lambda_J = 0 the DP "
                    "reduces to greedy, and as lambda_J grows the DP holds states the greedy "
                    "labeller abandons. Reporting one and calling it the other would misstate "
                    "how often the provider changed its mind"),
    }


def m0_comparator(seed: int = 62) -> dict:
    """L05.2 — the rule baseline, run rather than merely defined."""
    world = W.recurring_state_world(seed=seed)
    volatility = np.abs(world.z[:, 0])
    cut = int(len(volatility) * 0.6)
    thresholds = M0.fit_thresholds(volatility[:cut])
    labels = M0.label(volatility, thresholds)

    weights = np.full(world.z.shape[1], 1.0 / world.z.shape[1])
    fit = multi_start_fit(world.z, weights, n_states=3, lambda_jump=1.0, seeds=(1, 2, 3))
    m1 = forward_filter(loss_matrix(world.z, fit["centroids"], weights), 1.0)

    return {
        "schema": "crypto_regime_lab.m0_comparator.v1",
        "m0": {**M0.describe(), "thresholds": thresholds,
               "switches": int(np.count_nonzero(labels[1:] != labels[:-1])),
               "agreement": W.label_agreement(labels, world.latent)[
                   "best_permutation_agreement"]},
        "m1": {"model_id": "M1_discrete_jump_model",
               "switches": m1.switches(),
               "agreement": W.label_agreement(m1.online_states, world.latent)[
                   "best_permutation_agreement"]},
        "thresholds_fitted_on": "the first 60% of the world only, then frozen",
        "m0_is_a_control_not_a_fallback": M0.describe()["is_fallback_for_m1"] is False,
        "reading": ("M0 reads one feature through frozen quantile cuts. Where M1 does better, the "
                    "gain is attributable to using the whole feature vector with persistence; "
                    "where it does not, the extra machinery bought nothing on this fixture"),
    }


def noise_sensitivity(levels=(0.5, 1.0, 2.0, 4.0)) -> dict:
    rows = []
    for noise in levels:
        world = W.recurring_state_world(noise=noise, seed=71)
        weights = np.full(world.z.shape[1], 1.0 / world.z.shape[1])
        fit = multi_start_fit(world.z, weights, n_states=3, lambda_jump=1.0, seeds=(1, 2, 3))
        result = forward_filter(loss_matrix(world.z, fit["centroids"], weights), 1.0)
        rows.append({
            "noise": noise,
            "agreement": W.label_agreement(result.online_states, world.latent)[
                "best_permutation_agreement"],
            "emitted_switches": result.switches(),
            "true_switches": world.as_record()["latent_switches"],
            "detection": W.detection_delay(result.online_states, world.latent),
        })
    return {
        "schema": "crypto_regime_lab.noise_sensitivity.v1",
        "levels": rows,
        "reading": ("separation is held fixed while noise rises, so this traces where the model "
                    "stops resolving states that really are there"),
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    checks = {}
    for name, fn in (("T37", t37_oracle), ("T38", t38_parity), ("T39", t39_mutation),
                     ("T40", t40_degeneracy), ("T41", t41_permutation), ("T42", t42_membership),
                     ("T43", t43_no_auto_retrain), ("T44", t44_novelty_vs_missing)):
        with writer.attempt(f"L05.selftest.{name}") as att:
            checks[name] = fn()
            att.detail = {"schema": checks[name]["schema"]}

    with writer.attempt("L05.7.worlds") as att:
        worlds = synthetic_worlds()
        noise = noise_sensitivity()
        att.detail = {"worlds": len(worlds["worlds"])}

    with writer.attempt("L05.2.model_versions") as att:
        versions = online_algorithm_versions()
        m0 = m0_comparator()
        att.detail = {"comparisons": len(versions["comparisons"])}

    payload = {
        "schema": "crypto_regime_lab.lab05_selftest.v1",
        "acceptance_checks": checks,
        "synthetic_worlds": worlds,
        "noise_sensitivity": noise,
        "online_algorithm_versions": versions,
        "m0_comparator": m0,
        "library_method_probe": R.verify_library_method("quantbt", "volatility_regime_labels"),
        "exit_claim_limits": (
            "these are TECHNICAL checks. A causal provider that passes them has a reproducible "
            "state vocabulary and nothing more; no predictive or financial value is claimed from "
            "fit loss, agreement with a simulator, or visually clean labels (guide L05 exit)"),
    }
    writer.write_config("lab05_selftest.json", payload)
    writer.write_json("lab05_selftest.json", payload, schema=payload["schema"])

    print("T37 DP vs brute force  :",
          f"endpoint={checks['T37']['all_endpoint_costs_match']} "
          f"online={checks['T37']['all_online_states_match']} "
          f"path={checks['T37']['all_best_paths_match']} "
          f"norm_safe={checks['T37']['normalisation_is_safe']} "
          f"causal!=offline in {checks['T37']['cases_where_causal_and_offline_disagree']} cases")
    print("T38 batch vs stream    :",
          f"states={checks['T38']['all_states_identical']} "
          f"costs={checks['T38']['all_costs_identical']} "
          f"prefixes={checks['T38']['all_prefix_vintages_stable']}")
    print("T39 future suffix      :",
          f"clean={checks['T39']['detector_passes_clean_fit']} "
          f"catches_leak={checks['T39']['detector_catches_known_leak']} "
          f"meaningful={checks['T39']['detector_is_meaningful']}")
    print("T40 degeneracy         :",
          f"blocked={checks['T40']['degenerate_is_blocked']} "
          f"healthy_usable={checks['T40']['healthy_is_usable']} "
          f"no_fake_confidence={checks['T40']['no_fake_confidence']}")
    print("T41 refit permutation  :",
          f"recovered={checks['T41']['permutation_recovered']} "
          f"market_transition={checks['T41']['declared_market_transition']} "
          f"moved_state_unmapped={checks['T41']['genuinely_moved_state_is_unmapped']}")
    print("T42 membership score   :",
          f"sums_to_one={checks['T42']['sums_to_one']} "
          f"named_probability={checks['T42']['is_named_probability']} "
          f"calibrated={checks['T42']['calibrated']}")
    print("T43 no auto retrain    :",
          f"inference_cannot_fit={checks['T43']['inference_path_calls_no_fit']}")
    print("T44 novelty vs missing :",
          f"distinct={checks['T44']['statuses_are_distinct']} "
          f"missing_wins={checks['T44']['missing_wins_over_novelty']}")
    print("worlds                 :")
    for row in worlds["worlds"]:
        print(f"   {row['name']:<18} true_switches={row['latent_switches']:<3} "
              f"emitted={row['emitted_switches']:<4} "
              f"agreement={row['agreement']['best_permutation_agreement']:.3f} "
              f"delay_median={row['detection']['delay_median']}")
    print(f"   NEGATIVE CONTROL: {worlds['negative_control']['finding'][:110]}...")
    print("greedy vs endpoint DP  :")
    for row in versions["comparisons"]:
        print(f"   lambda={row['lambda_jump']:<4} dp_switches={row['endpoint_dp']['switches']:<4} "
              f"greedy_switches={row['greedy']['switches']:<4} "
              f"agreement={row['label_agreement']:.3f} identical={row['identical']}")
    print(f"   two model versions, never mixed: {versions['comparisons'][0]['are_two_model_versions']}")
    print("M0 comparator          :",
          f"m0_switches={m0['m0']['switches']} agreement={m0['m0']['agreement']:.3f} | "
          f"m1_switches={m0['m1']['switches']} agreement={m0['m1']['agreement']:.3f} | "
          f"m0_is_fallback={not m0['m0_is_a_control_not_a_fallback']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
