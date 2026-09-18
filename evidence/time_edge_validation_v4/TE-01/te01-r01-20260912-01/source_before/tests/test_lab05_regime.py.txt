"""LAB-05 acceptance tests T37-T44 plus the invariants behind them."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent

from crypto_regime_lab.regime import causality as C
from crypto_regime_lab.regime import model_selection as MS
from crypto_regime_lab.regime import registry as R
from crypto_regime_lab.regime import robustness as RB
from crypto_regime_lab.regime import worlds as W
from crypto_regime_lab.regime.emissions import (QUALITY_STATUSES, EmissionTape,
                                                ImmutableTapeViolation, OnlineStateFilter,
                                                batch_stream_parity, build_emission,
                                                membership_scores)
from crypto_regime_lab.regime.jump_model import (JumpModelError, fit_jump_model, forward_filter,
                                                 loss_matrix, multi_start_fit, path_objective,
                                                 second_best_gap)
from crypto_regime_lab.regime.oracle import (exhaustive_best_path, exhaustive_endpoint_costs,
                                             exhaustive_online_states)
from crypto_regime_lab.regime.quality import assess, check_degeneracy, fit_novelty_threshold


def _toy(seed=0, n_obs=6, n_states=3, n_features=3):
    rng = np.random.default_rng(seed)
    z = rng.normal(size=(n_obs, n_features))
    mu = rng.normal(size=(n_states, n_features))
    w = rng.random(n_features)
    return z, mu, w


# ---------------------------------------------------------------------------
# T37 — forward DP versus exhaustive enumeration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(6))
def test_t37_endpoint_costs_equal_brute_force(seed):
    z, mu, w = _toy(seed, n_obs=int(4 + seed % 4))
    loss = loss_matrix(z, mu, w)
    lam = 0.3 + 0.4 * seed
    raw = forward_filter(loss, lam, normalise=False)
    assert np.allclose(raw.raw_costs, exhaustive_endpoint_costs(loss, lam), rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("seed", range(6))
def test_t37_online_states_equal_brute_force(seed):
    z, mu, w = _toy(seed, n_obs=int(4 + seed % 4))
    loss = loss_matrix(z, mu, w)
    lam = 0.2 + 0.3 * seed
    result = forward_filter(loss, lam)
    assert np.array_equal(result.online_states, exhaustive_online_states(loss, lam))


def test_t37_offline_path_equals_brute_force_best_path():
    z, mu, w = _toy(3, n_obs=7)
    loss = loss_matrix(z, mu, w)
    result = forward_filter(loss, 0.8, normalise=False, with_offline_path=True)
    best, _ = exhaustive_best_path(loss, 0.8)
    assert np.array_equal(result.offline_path, best)


def test_t37_the_causal_and_offline_answers_really_do_differ():
    """If they never differed, the whole no-backtracking rule would be vacuous."""
    differ = 0
    for seed in range(20):
        z, mu, w = _toy(seed, n_obs=8)
        loss = loss_matrix(z, mu, w)
        result = forward_filter(loss, 0.6, with_offline_path=True)
        if not np.array_equal(result.online_states, result.offline_path):
            differ += 1
    assert differ > 0, "the offline path never rewrote a label; the fixture proves nothing"


def test_t37_offline_path_is_never_decision_eligible():
    z, mu, w = _toy(1)
    result = forward_filter(loss_matrix(z, mu, w), 0.5, with_offline_path=True)
    assert result.offline_decision_eligible is False
    assert "diagnostic" in result.offline_note


def test_t37_normalisation_changes_neither_argmin_nor_differences():
    z, mu, w = _toy(5, n_obs=30)
    loss = loss_matrix(z, mu, w)
    raw = forward_filter(loss, 0.7, normalise=False)
    norm = forward_filter(loss, 0.7, normalise=True)
    assert np.array_equal(raw.online_states, norm.online_states)
    centred_raw = raw.raw_costs - raw.raw_costs.min(axis=1, keepdims=True)
    centred_norm = norm.costs - norm.costs.min(axis=1, keepdims=True)
    assert np.allclose(centred_raw, centred_norm, atol=1e-12)


def test_t37_tie_break_is_the_lowest_state_index():
    loss = np.zeros((4, 3))
    result = forward_filter(loss, 1.0)
    assert set(result.online_states.tolist()) == {0}


# ---------------------------------------------------------------------------
# T38 — batch versus streaming
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_obs,n_states", [(15, 2), (120, 3), (300, 3)])
def test_t38_streaming_equals_batch_at_every_prefix(n_obs, n_states):
    rng = np.random.default_rng(n_obs)
    z = rng.normal(size=(n_obs, 4))
    mu = rng.normal(size=(n_states, 4))
    w = rng.random(4)
    parity = batch_stream_parity(z, mu, w, 0.9)
    assert parity["states_identical"]
    assert parity["costs_identical"]
    assert parity["prefix_vintages_stable"], parity["prefix_mismatches_at"]


def test_t38_the_streaming_filter_cannot_see_the_future():
    """Structural, on the CODE rather than on a word in the prose.

    Parse ``step`` and require that the only array it subscripts are the ones it
    was handed for this observation. A docstring may talk about the future; the
    body may not reach for it.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(OnlineStateFilter.step)))
    function = tree.body[0]
    parameters = {a.arg for a in function.args.args}
    assert "z_t" in parameters, "step must take exactly the current observation"
    assert len(parameters - {"self"}) == 1, (
        f"step takes more than the current observation: {parameters}")

    # the only per-observation state it may carry is the previous cost row
    attributes = {node.attr for node in ast.walk(function)
                  if isinstance(node, ast.Attribute)}
    assert "_previous" in attributes
    for forbidden in ("_series", "_all", "_future", "_panel"):
        assert forbidden not in attributes, f"step reaches for {forbidden}"

    # and it must be callable with a single row, which a look-ahead version could not be
    filt = OnlineStateFilter(np.eye(3), np.ones(3) / 3, 0.5, namespace="ns")
    state, costs, raw = filt.step(np.array([1.0, 0.0, 0.0]))
    assert isinstance(state, int) and costs.shape == (3,) and raw.shape == (3,)


def test_t38_an_emission_tape_is_append_only():
    z, mu, w = _toy(2, n_obs=5)
    filt = OnlineStateFilter(mu, w, 0.5, namespace="ns")
    tape = EmissionTape(namespace="ns")
    for t in range(z.shape[0]):
        state, costs, _ = filt.step(z[t])
        tape.append(build_emission(state, costs, namespace="ns", z_t=z[t], centroids=mu,
                                   weights=w, groups={"G": [0, 1, 2]}, observed_at="t",
                                   available_at="t", inferred_at="t", model_fit_cutoff="c",
                                   ready_at="r", version="v"))
    tape.seal()
    with pytest.raises(ImmutableTapeViolation, match="decision-vintage"):
        tape.overwrite(0, tape.emissions[0])


def test_t38_a_foreign_namespace_cannot_be_appended():
    tape = EmissionTape(namespace="model_A")
    z, mu, w = _toy(4, n_obs=2)
    emission = build_emission(0, np.array([0.1, 0.2, 0.3]), namespace="model_B", z_t=z[0],
                              centroids=mu, weights=w, groups={"G": [0, 1, 2]},
                              observed_at="t", available_at="t", inferred_at="t",
                              model_fit_cutoff="c", ready_at="r", version="v")
    with pytest.raises(ImmutableTapeViolation, match="(?i)own namespace"):
        tape.append(emission)


def test_t38_switches_come_from_the_tape_not_from_lambda():
    z, mu, w = _toy(6, n_obs=40)
    result = forward_filter(loss_matrix(z, mu, w), 0.1)
    assert result.switches() == int(np.count_nonzero(
        result.online_states[1:] != result.online_states[:-1]))


# ---------------------------------------------------------------------------
# T39 — fit and scaler cannot read past the cutoff
# ---------------------------------------------------------------------------

def test_t39_a_causal_fit_is_bit_identical_under_a_mutated_future():
    rng = np.random.default_rng(9)
    raw = rng.normal(size=(300, 4))
    result = C.future_suffix_mutation_test(raw, 150)
    assert result["probe_valid"], "the mutation must actually change the suffix"
    assert result["verdict"] == "CAUSAL"
    assert result["digest_before"] == result["digest_after"]


def test_t39_the_detector_catches_a_known_leak():
    """A mutation test that cannot fail proves nothing."""
    rng = np.random.default_rng(10)
    raw = rng.normal(size=(300, 4))
    control = C.run_control_pair(raw, 150)
    assert control["detector_passes_clean_fit"]
    assert control["detector_catches_known_leak"]
    assert control["detector_is_meaningful"]
    assert control["deliberately_leaky_fit"]["scaler_identical"] is False


def test_t39_the_scaler_is_fitted_on_the_prefix_only():
    rng = np.random.default_rng(11)
    raw = rng.normal(size=(200, 3))
    whole = C.fit_scaler(raw)
    prefix = C.fit_scaler(raw[:100])
    assert not np.allclose(whole["median"], prefix["median"])
    assert prefix["fitted_rows"] == 100


# ---------------------------------------------------------------------------
# T40 — degeneracy
# ---------------------------------------------------------------------------

def test_t40_all_zero_weights_is_flagged_and_blocks_decisions():
    report = check_degeneracy(np.zeros(5), np.random.default_rng(1).normal(size=(3, 5)))
    assert report["collapsed_weights"] and report["is_degenerate"]
    assert report["usable_for_decisions"] is False
    verdict = assess(costs=np.zeros(3), fit_residual=0.0, novelty_threshold=1.0,
                     degeneracy=report)
    assert verdict.status == "UNKNOWN_STATE"
    assert verdict.decision_eligible is False


def test_t40_identical_centroids_are_degenerate():
    report = check_degeneracy(np.ones(4) / 4, np.zeros((3, 4)))
    assert report["identical_centroid_pairs"]
    assert report["is_degenerate"]


def test_t40_an_empty_state_is_reported_not_hidden():
    report = check_degeneracy(np.ones(3) / 3, np.random.default_rng(2).normal(size=(3, 3)) * 4,
                              np.array([50, 0, 10]))
    assert report["empty_states"] == [1]
    assert report["is_degenerate"]


def test_t40_a_healthy_model_is_usable():
    report = check_degeneracy(np.ones(3) / 3, np.random.default_rng(3).normal(size=(3, 3)) * 6,
                              np.array([50, 30, 10]))
    assert report["is_degenerate"] is False
    assert report["usable_for_decisions"] is True


def test_t40_empty_states_survive_a_fit_without_inventing_members():
    """A state with no members keeps its centroid; the fit does not fabricate data."""
    z = np.vstack([np.zeros((60, 2)), np.ones((60, 2)) * 8])
    centroids, diagnostics = fit_jump_model(z, np.ones(2) / 2, n_states=4, lambda_jump=1.0,
                                            seed=5)
    assert np.isfinite(centroids).all()
    assert diagnostics.empty_state_policy == "retained_as_empty_and_reported"


# ---------------------------------------------------------------------------
# T41 — refit permutes state ids
# ---------------------------------------------------------------------------

def _artifact(name, centroids, weights):
    return R.ModelArtifact(
        model_id=name, state_namespace=name, training_start="2020-01-01",
        training_cutoff="2021-01-01", fit_ready_at="2021-01-01T00:00:00Z",
        n_states=centroids.shape[0], lambda_jump=1.0,
        feature_names=tuple(f"f{i}" for i in range(centroids.shape[1])),
        feature_weights=tuple(weights), group_weights={}, centroids=centroids.tolist(),
        scaler_ref={}, seeds=(1,), selected_seed=1, observation_interval="4h")


def test_t41_a_pure_permutation_maps_cleanly_and_is_not_a_market_event():
    weights = np.full(3, 1 / 3)
    centroids = np.array([[-3.0, 0, 0], [0, 3.0, 0], [0, 0, -3.0]])
    permutation = [1, 2, 0]
    mapping = R.map_state_namespaces(_artifact("A", centroids, weights),
                                     _artifact("B", centroids[permutation], weights))
    assert mapping["all_states_mapped"]
    assert [mapping["mapping"][str(k)]["old_state"] for k in range(3)] == permutation
    assert mapping["is_market_transition"] is False
    assert mapping["triggers_parameter_search"] is False


def test_t41_a_state_that_really_moved_is_left_unmapped():
    """Otherwise the mapper would map anything onto its nearest neighbour."""
    weights = np.full(3, 1 / 3)
    centroids = np.array([[-3.0, 0, 0], [0, 3.0, 0], [0, 0, -3.0]])
    moved = centroids.copy()
    moved[1] = np.array([80.0, 80.0, 80.0])
    mapping = R.map_state_namespaces(_artifact("A", centroids, weights),
                                     _artifact("C", moved, weights))
    assert mapping["unmapped_states"], "a distant new state must not be silently matched"
    assert mapping["all_states_mapped"] is False


def test_t41_relabelling_marks_unmapped_states_as_minus_one():
    weights = np.full(3, 1 / 3)
    centroids = np.array([[-3.0, 0, 0], [0, 3.0, 0], [0, 0, -3.0]])
    moved = centroids.copy()
    moved[2] = np.array([90.0, 90.0, 90.0])
    mapping = R.map_state_namespaces(_artifact("A", centroids, weights),
                                     _artifact("D", moved, weights))
    relabelled = R.relabel_states(np.array([0, 1, 2]), mapping)
    assert -1 in relabelled.tolist()


def test_t41_a_model_transition_never_rewrites_prior_emissions():
    weights = np.full(3, 1 / 3)
    centroids = np.array([[-3.0, 0, 0], [0, 3.0, 0], [0, 0, -3.0]])
    old, new = _artifact("A", centroids, weights), _artifact("B", centroids[[1, 2, 0]], weights)
    event = R.model_transition_event(old, new, R.map_state_namespaces(old, new))
    assert event["is_market_event"] is False
    assert event["requires_parameter_search"] is False
    assert event["prior_emissions_rewritten"] is False


def test_t41_mapping_uses_training_information_only():
    weights = np.full(3, 1 / 3)
    centroids = np.array([[-3.0, 0, 0], [0, 3.0, 0], [0, 0, -3.0]])
    mapping = R.map_state_namespaces(_artifact("A", centroids, weights),
                                     _artifact("B", centroids, weights))
    assert mapping["information_used"] == "training centroids and declared feature weights only"


# ---------------------------------------------------------------------------
# T42 — membership score is not a probability
# ---------------------------------------------------------------------------

def test_t42_membership_sums_to_one_and_is_still_not_a_probability():
    scores = membership_scores(np.array([0.1, 0.4, 2.0]))
    assert np.isclose(scores.sum(), 1.0)
    z, mu, w = _toy(7, n_obs=1)
    emission = build_emission(0, np.array([0.1, 0.4, 2.0]), namespace="ns", z_t=z[0],
                              centroids=mu, weights=w, groups={"G": [0, 1, 2]},
                              observed_at="t", available_at="t", inferred_at="t",
                              model_fit_cutoff="c", ready_at="r", version="v").as_record()
    assert emission["membership_is_calibrated"] is False
    assert "membership_score" in emission and "probability" not in emission
    assert "not a probability" in emission["membership_note"]


def test_t42_second_best_gap_measures_ambiguity():
    costs = np.array([[0.0, 0.01, 5.0], [0.0, 4.0, 9.0]])
    gaps = second_best_gap(costs)
    assert gaps[0] < gaps[1], "a near-tie must show a smaller gap than a clear winner"


# ---------------------------------------------------------------------------
# T43 — inference never triggers a retrain
# ---------------------------------------------------------------------------

def test_t43_the_inference_modules_cannot_call_a_fit():
    import ast

    watched = {"fit_jump_model", "multi_start_fit", "fit_scaler", "causal_fit", "choose_k"}
    for name in ("emissions.py", "quality.py"):
        path = LAB_ROOT / "src" / "crypto_regime_lab" / "regime" / name
        tree = ast.parse(path.read_text())
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                called.add(getattr(func, "id", None) or getattr(func, "attr", None))
        assert not (called & watched), f"{name} can reach a fit: {called & watched}"


def test_t43_the_registry_says_a_transition_is_not_a_search_trigger():
    weights = np.full(3, 1 / 3)
    centroids = np.array([[-3.0, 0, 0], [0, 3.0, 0], [0, 0, -3.0]])
    mapping = R.map_state_namespaces(_artifact("A", centroids, weights),
                                     _artifact("B", centroids, weights))
    assert mapping["triggers_parameter_search"] is False


# ---------------------------------------------------------------------------
# T44 — novelty versus missing data
# ---------------------------------------------------------------------------

def test_t44_identical_residual_but_missing_inputs_gives_a_different_status():
    costs = np.array([0.2, 0.9, 1.4])
    novel = assess(costs=costs, fit_residual=9.0, novelty_threshold=1.0)
    missing = assess(costs=costs, fit_residual=9.0, novelty_threshold=1.0,
                     missing_features=("g2_taker_imbalance",))
    assert novel.status == "UNKNOWN_STATE"
    assert missing.status == "MISSING_DATA"
    assert novel.status != missing.status


def test_t44_all_four_fallback_reasons_are_distinct():
    costs = np.array([0.2, 0.9, 1.4])
    statuses = {
        assess(costs=costs, fit_residual=0.1, novelty_threshold=1.0).status,
        assess(costs=costs, fit_residual=9.0, novelty_threshold=1.0).status,
        assess(costs=costs, fit_residual=0.1, novelty_threshold=1.0,
               missing_features=("x",)).status,
        assess(costs=costs, fit_residual=0.1, novelty_threshold=1.0,
               model_age_seconds=1e9, max_model_age_seconds=1.0).status,
    }
    assert len(statuses) == 4
    assert statuses <= set(QUALITY_STATUSES)


def test_t44_the_novelty_threshold_comes_from_training_residuals():
    threshold = fit_novelty_threshold(np.abs(np.random.default_rng(4).normal(size=800)))
    assert threshold["quantile"] == 0.99
    assert "training residuals only" in threshold["fitted_on"]


# ---------------------------------------------------------------------------
# L05.3 / L05.4 invariants
# ---------------------------------------------------------------------------

def test_the_objective_never_increases_during_a_fit():
    rng = np.random.default_rng(21)
    z = np.vstack([rng.normal(-2, 1, size=(120, 3)), rng.normal(2, 1, size=(120, 3))])
    report = RB.convergence_report(z, np.ones(3) / 3, n_states=3, lambda_jump=1.0,
                                   seeds=(1, 2, 3))
    assert report["all_monotone"]
    assert report["all_finite"]


def test_multi_start_selects_on_the_train_objective_and_nothing_else():
    rng = np.random.default_rng(22)
    z = rng.normal(size=(200, 3))
    fit = multi_start_fit(z, np.ones(3) / 3, n_states=3, lambda_jump=1.0, seeds=(1, 2, 3, 4))
    assert fit["outer_information_used"] is False
    best = min(r["final_objective"] for r in fit["runs"])
    chosen = next(r for r in fit["runs"] if r["seed"] == fit["selected_seed"])
    assert np.isclose(chosen["final_objective"], best)
    assert "local" in fit["local_minimum_only"].lower()


def test_a_constant_feature_is_reported():
    z = np.random.default_rng(23).normal(size=(100, 3))
    z[:, 1] = 4.0
    report = RB.constant_feature_report(z, ("a", "b", "c"))
    assert report["constant_features"] == ["b"]


def test_k_selection_never_sees_a_holdout_or_an_outcome():
    rng = np.random.default_rng(24)
    z = np.vstack([rng.normal(-2, 1, size=(200, 3)), rng.normal(2, 1, size=(200, 3))])
    choice = MS.choose_k(z, np.ones(3) / 3, lambda_jump=1.0, seeds=(1, 2))
    assert choice["chart_inspection_used"] is False
    for score in choice["scores"].values():
        assert score["holdout_used"] is False
        assert score["outcome_used"] is False


def test_k4_stays_shut_without_an_explicit_decision():
    rng = np.random.default_rng(25)
    z = rng.normal(size=(400, 3))
    without = MS.choose_k(z, np.ones(3) / 3, lambda_jump=1.0, seeds=(1,),
                          candidates=(2, 3, 4))
    assert without["expansion_k_requested"] is True
    assert without["expansion_k_admitted"] is False
    assert 4 not in without["candidates_considered"]

    with_decision = MS.choose_k(z, np.ones(3) / 3, lambda_jump=1.0, seeds=(1,),
                                candidates=(2, 3, 4),
                                expansion_decision={"approved": True,
                                                    "decision_value": "recorded in discovery"})
    assert with_decision["expansion_k_admitted"] is True


def test_lambda_jump_is_not_transferable_across_frequencies():
    units = MS.lambda_jump_units(1.0, "4h")
    assert units["transferable_across_frequencies"] is False


# ---------------------------------------------------------------------------
# L05.7 — synthetic worlds
# ---------------------------------------------------------------------------

def test_the_no_regime_world_exposes_manufactured_structure():
    world = W.no_regime_world()
    weights = np.full(world.z.shape[1], 1 / world.z.shape[1])
    fit = multi_start_fit(world.z, weights, n_states=3, lambda_jump=1.0, seeds=(1, 2))
    result = forward_filter(loss_matrix(world.z, fit["centroids"], weights), 1.0)
    assert world.as_record()["latent_switches"] == 0
    assert result.switches() > 0, (
        "if the model emitted no switches on noise the control would prove nothing; the point is "
        "that it DOES, and that persistent-looking states are not evidence of regimes")
    agreement = W.label_agreement(result.online_states, world.latent)
    assert agreement["diagnostic_only"] is True


def test_the_recurring_world_is_re_identified():
    world = W.recurring_state_world()
    weights = np.full(world.z.shape[1], 1 / world.z.shape[1])
    fit = multi_start_fit(world.z, weights, n_states=3, lambda_jump=1.0, seeds=(1, 2, 3))
    result = forward_filter(loss_matrix(world.z, fit["centroids"], weights), 1.0)
    agreement = W.label_agreement(result.online_states, world.latent)
    assert agreement["best_permutation_agreement"] > 0.8


def test_the_structural_break_is_detected_with_a_reported_delay():
    world = W.structural_break_world()
    weights = np.full(world.z.shape[1], 1 / world.z.shape[1])
    fit = multi_start_fit(world.z, weights, n_states=2, lambda_jump=1.0, seeds=(1, 2, 3))
    result = forward_filter(loss_matrix(world.z, fit["centroids"], weights), 1.0)
    detection = W.detection_delay(result.online_states, world.latent)
    assert detection["true_switches"] == 1
    assert detection["detected"] == 1
    assert detection["delay_median"] is not None


def test_ground_truth_is_declared_diagnostic_only():
    for maker in (W.no_regime_world, W.recurring_state_world, W.structural_break_world):
        record = maker().as_record()
        assert "never enters a feature" in record["ground_truth_is_diagnostic_only"]


# ---------------------------------------------------------------------------
# L05.1 — the artifact and library-method discipline
# ---------------------------------------------------------------------------

def test_a_library_method_is_never_trusted_by_name():
    probe = R.verify_library_method("quantbt", "volatility_regime_labels")
    assert probe["safe_to_call"] is False
    assert "presence is not semantics" in probe.get("rule", "") or probe["status"] != "PRESENT"


def test_the_model_artifact_carries_what_l051_requires():
    weights = np.full(3, 1 / 3)
    artifact = _artifact("m", np.eye(3), weights)
    record = artifact.as_record()
    for field in ("training_cutoff", "scaler_ref", "feature_weights", "centroids", "lambda_jump",
                  "state_namespace", "seeds", "selected_seed", "fit_ready_at", "code_hashes",
                  "library_versions", "centroid_digest"):
        assert field in record, f"the artifact is missing {field}"
    assert "never revised" in record["decision_rule"]
    assert "not named from outer PnL" in record["state_naming_rule"]


def test_the_loss_rejects_negative_weights_and_non_finite_inputs():
    z, mu, _ = _toy(8, n_obs=4)
    with pytest.raises(JumpModelError, match="nonnegative"):
        loss_matrix(z, mu, np.array([-1.0, 1.0, 1.0]))
    bad = z.copy()
    bad[0, 0] = np.nan
    with pytest.raises(JumpModelError, match="non-finite"):
        loss_matrix(bad, mu, np.ones(3) / 3)


def test_path_objective_counts_jumps_the_way_the_guide_defines_them():
    loss = np.zeros((5, 2))
    assert path_objective(loss, np.array([0, 0, 1, 1, 0]), 2.0) == pytest.approx(4.0)
    assert path_objective(loss, np.array([0, 0, 0, 0, 0]), 2.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# committed artifacts
# ---------------------------------------------------------------------------

def _load(name):
    path = LAB_ROOT / "configs" / name
    if not path.is_file():
        pytest.skip(f"run the LAB-05 scripts to produce {name}")
    return json.loads(path.read_text())


def test_the_selftest_artifact_records_every_acceptance_check():
    payload = _load("lab05_selftest.json")
    for check in ("T37", "T38", "T39", "T40", "T41", "T42", "T43", "T44"):
        assert check in payload["acceptance_checks"]
    assert payload["acceptance_checks"]["T39"]["detector_is_meaningful"] is True
    assert "no predictive or financial value is claimed" in payload["exit_claim_limits"]


def test_the_negative_control_is_recorded_with_its_number():
    payload = _load("lab05_selftest.json")
    control = payload["synthetic_worlds"]["negative_control"]
    assert control["true_switches"] == 0
    assert control["emitted_switches"] > 0
    assert "NOT evidence of regimes" in control["finding"]


def test_the_registry_only_used_development_data():
    registry = _load("lab05_regime_model_registry.json")
    assert registry["data_role"] == "development"
    assert registry["outer_evaluation_touched"] is False
    for model in registry["models"]:
        assert model["training_cutoff"] <= "2023-12-31"
    assert registry["clock_separation"]["parameter_search_triggered_by_this"] is False
    assert registry["clock_separation"]["bank_refresh_triggered_by_this"] is False


# ---------------------------------------------------------------------------
# CLAUDE.md rules 9 and 10 applied to this phase's report
# ---------------------------------------------------------------------------

REPORT = LAB_ROOT / "reports" / "lab05_report.md"


def test_the_lab05_report_carries_the_real_numbers():
    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab05_report.py")
    text = REPORT.read_text()
    registry = _load("lab05_regime_model_registry.json")
    selftest = _load("lab05_selftest.json")

    assert f"**{len(registry['models'])} fits**" in text
    mappings = registry["namespace_mappings"]
    unmapped = sum(1 for m in mappings if not m["all_states_mapped"])
    assert f"**{len(mappings)} namespace mappings**" in text
    assert f"**{unmapped}** contained a state that could not be matched" in text

    control = selftest["synthetic_worlds"]["negative_control"]
    assert str(control["emitted_switches"]) in text
    for check in ("T37", "T38", "T39", "T40", "T41", "T42", "T43", "T44"):
        assert f"| {check} |" in text, f"the report does not tabulate {check}"


def test_the_lab05_report_states_its_claim_limits_before_any_number():
    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab05_report.py")
    text = REPORT.read_text()
    limits = text.index("What this phase does and does not claim")
    first_table = text.index("| id | question | measured |")
    assert limits < first_table, "the claim limits must come before the results"
    assert "technical pass" in text[limits:first_table]
    assert "not answered here" in text[limits:first_table]


def test_the_lab05_report_defines_its_own_terms():
    from crypto_regime_lab.evidence import glossary as G

    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab05_report.py")
    text = REPORT.read_text()
    assert text.count("## Glossary — what each term means and where it applies") == 1
    for term, _, _ in G.BY_PHASE["LAB-05"]:
        assert f"| **{term}** |" in text, f"the report does not define {term}"
    for jargon in ("namespace", "membership score", "jump model", "no-regime world"):
        assert jargon.lower() in text.lower()


def test_the_lab05_report_records_the_cadence_correction():
    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab05_report.py")
    text = REPORT.read_text()
    assert "Corrections made during LAB-05" in text
    assert "762 of 1099" in text, (
        "the measured consequence of the wrong cadence must stay in the record")


# ---------------------------------------------------------------------------
# L05.2 — greedy online and endpoint DP are two model versions
# ---------------------------------------------------------------------------

def test_greedy_and_endpoint_dp_are_genuinely_different_models():
    from crypto_regime_lab.regime.jump_model import compare_online_algorithms

    rng = np.random.default_rng(31)
    z = rng.normal(size=(300, 4))
    mu = rng.normal(size=(3, 4)) * 1.5
    comparison = compare_online_algorithms(loss_matrix(z, mu, np.full(4, 0.25)), 2.0)
    assert comparison["identical"] is False
    assert comparison["greedy"]["switches"] > comparison["endpoint_dp"]["switches"], (
        "without a jump penalty the greedy labeller must flicker more, or the two are not "
        "actually different algorithms")
    assert comparison["are_two_model_versions"] is True
    assert comparison["endpoint_dp"]["uses_jump_penalty"] is True
    assert comparison["greedy"]["uses_jump_penalty"] is False


def test_at_zero_penalty_the_dp_reduces_to_greedy():
    """The one case where they must agree; it pins down what the penalty is doing."""
    from crypto_regime_lab.regime.jump_model import (compare_online_algorithms,
                                                     greedy_online_states)

    rng = np.random.default_rng(32)
    loss = loss_matrix(rng.normal(size=(200, 3)), rng.normal(size=(3, 3)), np.ones(3) / 3)
    assert np.array_equal(forward_filter(loss, 0.0).online_states, greedy_online_states(loss))
    assert compare_online_algorithms(loss, 0.0)["identical"] is True


def test_the_two_online_algorithms_carry_different_version_suffixes():
    from crypto_regime_lab.regime.jump_model import compare_online_algorithms

    rng = np.random.default_rng(33)
    loss = loss_matrix(rng.normal(size=(50, 3)), rng.normal(size=(3, 3)), np.ones(3) / 3)
    comparison = compare_online_algorithms(loss, 1.0)
    assert comparison["endpoint_dp"]["model_version_suffix"] != \
        comparison["greedy"]["model_version_suffix"]
    assert "two models, not two settings" in comparison["mixing_rule"]


# ---------------------------------------------------------------------------
# L05.2 — the M0 rule baseline is run, not merely defined
# ---------------------------------------------------------------------------

def test_m0_thresholds_are_frozen_from_a_training_prefix():
    from crypto_regime_lab.regime import m0_rules as M0

    values = np.abs(np.random.default_rng(34).normal(size=500))
    thresholds = M0.fit_thresholds(values[:300])
    assert thresholds["train_n"] == 300
    assert "training window only" in thresholds["fitted_on"]
    # labelling the whole series must not change the cuts
    labels = M0.label(values, thresholds)
    assert set(labels.tolist()) <= {0, 1, 2}
    assert M0.fit_thresholds(values[:300])["cuts"] == thresholds["cuts"]


def test_m0_is_a_control_and_never_a_silent_fallback():
    from crypto_regime_lab.regime import m0_rules as M0

    described = M0.describe()
    assert described["is_fallback_for_m1"] is False
    assert "never silently substituted" in described["fallback_note"]
    assert "not bull/neutral/bear" in described["naming_note"]


def test_the_selftest_artifact_records_both_model_versions_and_m0():
    payload = _load("lab05_selftest.json")
    versions = payload["online_algorithm_versions"]
    assert versions["comparisons"]
    assert versions["greedy_always_switches_at_least_as_much"] is True
    assert versions["never_identical_at_a_real_penalty"] is True
    m0 = payload["m0_comparator"]
    assert m0["m0"]["switches"] > 0
    assert m0["m0_is_a_control_not_a_fallback"] is True


# ---------------------------------------------------------------------------
# guide 8.3 — group ablation and the declared model-ladder position
# ---------------------------------------------------------------------------

def test_the_model_ladder_declares_every_rung_it_did_not_build():
    from crypto_regime_lab.regime.ablation import MODEL_LADDER, ladder_record

    record = ladder_record()
    assert set(MODEL_LADDER) == {"M0", "M1", "M1S", "M2", "M3"}, "guide 8.1 has five rungs"
    assert record["implemented"] == ["M0", "M1"]
    for name in record["not_implemented"]:
        rung = MODEL_LADDER[name]
        assert rung["why_not"], f"{name} is unbuilt with no reason given"
        assert rung["what_would_change_it"], f"{name} has no condition to revisit it"
    # M1S must cite the specific trap guide 8.3 names
    assert "naive sparse objective" in MODEL_LADDER["M1S"]["why_not"]


def test_ablation_weights_are_renormalised_so_it_measures_information():
    from crypto_regime_lab.regime.ablation import group_weights

    features = ("g1_a", "g1_b", "g2_c", "g5_d")
    weights = np.array([0.25, 0.25, 0.25, 0.25])
    restricted = group_weights(features, weights, ("G1",))
    assert np.isclose(restricted.sum(), 1.0), (
        "without renormalising, a smaller feature set just has less total weight and a lower "
        "loss, and the ablation would measure the normalisation rather than the information")
    assert restricted[2] == 0.0 and restricted[3] == 0.0


def test_ablation_decides_on_the_scale_free_measure_not_the_objective():
    """A different feature set is a different objective; its value is not comparable."""
    from crypto_regime_lab.regime.ablation import group_ablation

    rng = np.random.default_rng(51)
    z = np.vstack([rng.normal(-2, 1, size=(200, 4)), rng.normal(2, 1, size=(200, 4))])
    features = ("g1_a", "g1_b", "g2_c", "g5_d")
    result = group_ablation(z, features, np.full(4, 0.25), n_states=2, lambda_jump=1.0,
                            seeds=(1, 2), ladder=(("G1",), ("G1", "G2"), ("G1", "G2", "G5")))
    assert result["decided_on"] == "variance_resolved_out_of_fold"
    assert "DIFFERENT objective function" in result["why_not_the_objective"]
    for row in result["ladder"]:
        assert "variance_resolved_out_of_fold" in row
        if row["variance_resolved_gain"] is not None:
            assert row["improved"] == (row["variance_resolved_gain"] > 0)


def test_variance_resolved_is_one_when_states_are_perfect():
    from crypto_regime_lab.regime.ablation import variance_resolved

    centroids = np.array([[-5.0, 0.0], [5.0, 0.0]])
    block = np.vstack([np.tile(centroids[0], (50, 1)), np.tile(centroids[1], (50, 1))])
    states = np.array([0] * 50 + [1] * 50)
    assert variance_resolved(block, centroids, states, np.full(2, 0.5)) == pytest.approx(1.0)


def test_the_committed_ablation_reports_its_verdict_either_way():
    result = _load("lab05_group_ablation.json")
    assert "requirement_satisfied" in result
    assert isinstance(result["blocks_that_improved_out_of_fold"], list)
    # whichever way it went, the finding must be stated, not implied
    assert "guide 8.3" in result["finding"]
    if not result["blocks_that_improved_out_of_fold"]:
        assert "does not" in result["finding"], (
            "a failed requirement must say so in words, not only in an empty list")
        assert "NOT changed in response" in result["finding"], (
            "changing the registered feature set on this result would be selecting on an outcome")


# ---------------------------------------------------------------------------
# guards that would otherwise never be exercised
# ---------------------------------------------------------------------------

def test_the_oracle_refuses_a_sequence_it_cannot_enumerate():
    """The enumeration cap is the only thing standing between a check and a hang."""
    from crypto_regime_lab.regime.oracle import MAX_ENUMERATED_PATHS, enumerate_paths

    assert list(enumerate_paths(2, 2)) == [(0, 0), (0, 1), (1, 0), (1, 1)]
    with pytest.raises(JumpModelError, match="enumeration cap"):
        enumerate_paths(40, 3)          # 3**40 paths
    assert MAX_ENUMERATED_PATHS > 0


def test_inner_splits_refuses_windows_it_cannot_score():
    from crypto_regime_lab.regime.model_selection import inner_splits

    splits = inner_splits(400, n_folds=3, min_train=100)
    assert len(splits) == 3
    for train_end, valid_start, valid_end in splits:
        assert train_end == valid_start < valid_end <= 400
    # blocks must be chronological and non-overlapping with their own training window
    assert [s[0] for s in splits] == sorted(s[0] for s in splits)

    with pytest.raises(ValueError, match="cannot support"):
        inner_splits(50, n_folds=3, min_train=100)
    with pytest.raises(ValueError, match="too short to score"):
        inner_splits(105, n_folds=3, min_train=100)


def test_the_dataclasses_carry_what_callers_read_off_them():
    """These are returned by other functions, so nothing constructs them directly."""
    from crypto_regime_lab.regime.jump_model import FitDiagnostics, ForwardResult
    from crypto_regime_lab.regime.quality import QualityVerdict
    from crypto_regime_lab.regime.worlds import World

    z, mu, w = _toy(12, n_obs=20)
    result = forward_filter(loss_matrix(z, mu, w), 0.7, with_offline_path=True)
    assert isinstance(result, ForwardResult)
    assert result.offline_decision_eligible is False
    assert result.costs.shape == result.raw_costs.shape

    _, diagnostics = fit_jump_model(z, w, n_states=2, lambda_jump=1.0, seed=1)
    assert isinstance(diagnostics, FitDiagnostics)
    record = diagnostics.as_record()
    assert record["objective_monotone_nonincreasing"] is True

    verdict = assess(costs=np.array([0.1, 0.5]), fit_residual=0.0, novelty_threshold=1.0)
    assert isinstance(verdict, QualityVerdict)
    assert verdict.as_record()["decision_eligible"] is True

    world = W.no_regime_world(n=50, n_features=2)
    assert isinstance(world, World)
    assert world.as_record()["latent_switches"] == 0
