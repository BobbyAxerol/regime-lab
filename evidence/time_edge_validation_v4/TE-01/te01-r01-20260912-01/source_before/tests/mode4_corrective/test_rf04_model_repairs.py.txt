"""RF-04 G10/A14 model repairs — real-code acceptance for the registered blocker.

Each test names the defect it pins:

  * A14 inner leakage: mutating an inner validation suffix must not move the
    scaler fitted on that fold's inner train, while the deliberately leaky
    whole-calibration scaler MUST move (otherwise the check is vacuous);
  * A14 namespace mapping: one-to-one in common raw/economic coordinates when K
    matches, with explicit matched/unmatched/ambiguous statuses;
  * A10/A14: a refit version event is a MODEL event and never a market
    transition, and a namespace-only change fires no trigger;
  * A14/P10 fixed-target ablation: every feature set is scored against the same
    target/cohort, and the reconstruction statistic that the P10 counterexample
    halved is diagnostic only;
  * the committed design-selection manifest carries a denominator and a way to
    go red (no ``all([]) == True`` vacuity).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from crypto_regime_lab.regime import ablation as AB
from crypto_regime_lab.regime import model_selection as MS
from crypto_regime_lab.regime import registry as R


def _synthetic_raw(n: int = 240, j: int = 3, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    latent = np.sign(np.sin(np.arange(n) / 13.0))
    columns = [latent + rng.normal(0, 0.2, n)]
    while len(columns) < j:
        columns.append(rng.normal(size=n))
    return np.column_stack(columns)


# --- A14 inner-train-only scaler -------------------------------------------

def test_inner_train_suffix_mutation_does_not_change_fitted_scaler():
    raw = _synthetic_raw()
    folds = MS.inner_splits(raw.shape[0], 3, 100)
    probe = MS.inner_scaler_mutation_probe(raw, folds)
    assert probe["mutation_effective"] is True
    assert probe["inner_train"]["denominator_folds"] == len(folds) > 0
    assert probe["inner_train"]["all_folds_unchanged"] is True, (
        "an inner fold's scaler moved after a suffix mutation, so it read its own validation")
    assert probe["whole_calibration_control"]["any_fold_changed"] is True, (
        "the leaky control never moved; the check could not go red and proves nothing")
    assert probe["detector_is_meaningful"] is True


def test_fold_scaler_reads_only_the_inner_train_prefix():
    raw = _synthetic_raw(n=300, j=2)
    folds = MS.inner_splits(raw.shape[0], 3, 100)
    records = MS.fit_inner_fold_scalers(raw, folds)
    for fold, (train_end, valid_start, valid_end) in zip(records, folds):
        assert fold["fitted_rows"] == train_end
        assert fold["rows_read_by_scaler"] == train_end
        assert fold["rows_read_by_scaler"] < valid_end


# --- A14 common-coordinate one-to-one mapping -------------------------------

def _artifact(name: str, raw_centroids: np.ndarray, *, median, scale,
              weights=(0.5, 0.5)) -> R.ModelArtifact:
    median = np.asarray(median, dtype=np.float64)
    scale = np.asarray(scale, dtype=np.float64)
    standardized = (np.asarray(raw_centroids, dtype=np.float64) - median) / scale
    return R.ModelArtifact(
        model_id=name, state_namespace=name, training_start="2020-01-01",
        training_cutoff="2021-01-01", fit_ready_at="2021-01-01T00:00:00Z",
        n_states=standardized.shape[0], lambda_jump=1.0,
        feature_names=("f0", "f1"), feature_weights=tuple(weights), group_weights={},
        centroids=standardized.tolist(),
        scaler_ref={"median": median.tolist(), "scale": scale.tolist(), "clip": 5.0,
                    "fitted_rows": 1000, "fitted_on": "training window only"},
        seeds=(1,), selected_seed=1, observation_interval="4h")


def test_k_matches_maps_one_to_one_in_common_raw_coordinates_across_scalers():
    raw_old = np.array([[12.0, -4.0], [8.0, -5.0], [14.0, -6.0]])
    old = _artifact("old", raw_old, median=[10.0, -5.0], scale=[2.0, 0.5])
    # the new fit uses a different scaler; the same two states plus one that moved
    raw_new = np.array([[8.0, -5.0], [12.0, -4.0], [100.0, 100.0]])
    new = _artifact("new", raw_new, median=[0.0, 0.0], scale=[1.0, 1.0])
    mapping = R.map_state_namespaces(old, new)

    assert mapping["k_matches"] is True
    assert mapping["one_to_one"] is True
    assert mapping["assignment_method"] == "exact_permutation"
    assert mapping["mapping"]["0"]["old_state"] == 1
    assert mapping["mapping"]["0"]["status"] == R.MAPPING_MATCHED
    assert mapping["mapping"]["1"]["old_state"] == 0
    assert mapping["mapping"]["2"]["status"] == R.MAPPING_UNMATCHED
    assert mapping["mapping"]["2"]["old_state"] is None
    assert mapping["matched_states"] == ["0", "1"]
    assert mapping["unmatched_states"] == ["2"]
    assert mapping["ambiguous_states"] == []
    assert mapping["all_states_mapped"] is False
    # every status is one of the three explicit names, not an ad-hoc label
    assert {v["status"] for v in mapping["mapping"].values()} <= set(R.MAPPING_STATUSES)


def test_k_mismatch_is_not_forced_one_to_one():
    raw_old = np.array([[12.0, -4.0], [8.0, -5.0], [14.0, -6.0]])
    old = _artifact("old", raw_old, median=[10.0, -5.0], scale=[2.0, 0.5])
    raw_new = np.array([[8.0, -5.0], [12.0, -4.0]])
    new = _artifact("new", raw_new, median=[0.0, 0.0], scale=[1.0, 1.0])
    mapping = R.map_state_namespaces(old, new)
    assert mapping["k_matches"] is False
    assert mapping["one_to_one"] is False
    assert mapping["assignment_method"] == "independent_nearest_k_mismatch"
    assert mapping["mapping"]["0"]["status"] == R.MAPPING_MATCHED
    assert mapping["mapping"]["0"]["old_state"] == 1


def test_a_permutation_without_scalers_still_maps_cleanly_one_to_one():
    weights = np.full(3, 1 / 3)
    centroids = np.array([[-3.0, 0, 0], [0, 3.0, 0], [0, 0, -3.0]])
    legacy = R.ModelArtifact(
        model_id="A", state_namespace="A", training_start="2020-01-01",
        training_cutoff="2021-01-01", fit_ready_at="x", n_states=3, lambda_jump=1.0,
        feature_names=("f0", "f1", "f2"), feature_weights=tuple(weights), group_weights={},
        centroids=centroids.tolist(), scaler_ref={}, seeds=(1,), selected_seed=1,
        observation_interval="4h")
    permuted = R.ModelArtifact(
        **{**legacy.__dict__, "model_id": "B", "state_namespace": "B",
           "centroids": centroids[[1, 2, 0]].tolist()})
    mapping = R.map_state_namespaces(legacy, permuted)
    assert mapping["all_states_mapped"] is True
    assert [mapping["mapping"][str(k)]["old_state"] for k in range(3)] == [1, 2, 0]
    assert mapping["one_to_one"] is True


# --- A10/A14 refit events are not market transitions ------------------------

def test_namespace_only_change_emits_no_market_transition():
    from crypto_regime_lab.experiments.regime_schedule import online_trigger_schedule

    raw_old = np.array([[12.0, -4.0], [8.0, -5.0], [14.0, -6.0]])
    old = _artifact("old", raw_old, median=[10.0, -5.0], scale=[2.0, 0.5])
    new = _artifact("new", raw_old, median=[0.0, 0.0], scale=[1.0, 1.0])
    mapping = R.map_state_namespaces(old, new)
    event = R.model_transition_event(old, new, mapping)

    assert mapping["is_market_transition"] is False
    assert mapping["emits_market_transition"] is False
    assert event["event_class"] == "MODEL_VERSION"
    assert event["is_market_event"] is False
    assert event["emits_market_transition"] is False
    assert event["requires_parameter_search"] is False
    assert event["mapping_status_counts"] == {"matched": 3, "unmatched": 0, "ambiguous": 0}

    emissions = [
        {"state_id": 0, "state_namespace": "v1", "state_common": 0,
         "decision_eligible": True, "quality_status": "OK",
         "available_at": "2024-01-01T00:00:00+00:00"},
        {"state_id": 0, "state_namespace": "v2", "state_common": 0,
         "decision_eligible": True, "quality_status": "OK",
         "available_at": "2024-02-01T00:00:00+00:00"},
    ]
    schedule = online_trigger_schedule(emissions, earliest="2024-01-01", latest="2024-06-01",
                                       min_gap_days=0.0, max_age_days=10_000.0)
    assert schedule.cutoffs == (), "a namespace-only change triggered a market search"

    emissions[1]["state_common"] = 1
    fired = online_trigger_schedule(emissions, earliest="2024-01-01", latest="2024-06-01",
                                    min_gap_days=0.0, max_age_days=10_000.0)
    assert len(fired.cutoffs) == 1, "the positive control must be able to fire"


# --- A14/P10 fixed-target ablation ------------------------------------------

def test_p10_counterexample_reproduced_but_not_used_as_decision_value():
    n = 300
    latent = np.r_[np.full(n // 2, -1.0), np.full(n // 2, 1.0)]
    noise = np.random.default_rng(11).normal(size=n)
    noise = (noise - noise.mean()) / noise.std()
    states = (latent > 0).astype(np.int64)
    clean = latent.reshape(-1, 1)
    polluted = np.column_stack([latent, noise])
    resolved_clean = AB.variance_resolved(clean, np.array([[-1.0], [1.0]]), states, np.ones(1))
    resolved_polluted = AB.variance_resolved(polluted, np.array([[-1.0, 0.0], [1.0, 0.0]]),
                                             states, np.array([0.5, 0.5]))
    assert resolved_clean == pytest.approx(1.0)
    assert resolved_polluted == pytest.approx(0.5), (
        "the P10 counterexample must be reproducible: fixed states, same economic target, "
        "statistic halved by an added noise dimension")
    assert resolved_polluted != resolved_clean


def test_fixed_target_ablation_reports_rank_ic_not_a_reconstruction_change():
    rng = np.random.default_rng(5)
    n = 360
    latent = np.sign(np.sin(np.arange(n) / 15.0))
    raw = np.column_stack([latent + rng.normal(0, 0.15, n), rng.normal(size=n),
                           rng.normal(size=n)])
    target = np.roll(latent, -1) * 0.01          # same fixed target for every feature set
    result = AB.fixed_target_ablation(
        raw, ("g1_signal", "g2_noise", "g5_noise"), np.full(3, 1 / 3),
        target=target, cohort=np.ones(n, dtype=bool),
        n_states=2, lambda_jump=1.0, seeds=(11,), n_folds=3, min_train=100, purge_rows=1)

    assert result["decided_on"] == "fixed_target_rank_ic"
    assert result["target_fixed_across_sets"] is True
    assert result["cohort_fixed_across_sets"] is True
    assert result["reconstruction_quality_used_for_decision"] is False
    assert result["p10_counterexample_guard"]["reconstruction_column_used_for_decision"] is False
    first, second, third = result["ladder"]
    assert first["incremental_decision_value"] is None
    assert second["incremental_decision_value"] == pytest.approx(
        second["fixed_target_rank_ic_mean"] - first["fixed_target_rank_ic_mean"])
    assert third["incremental_decision_value"] == pytest.approx(
        third["fixed_target_rank_ic_mean"] - second["fixed_target_rank_ic_mean"])
    for row in result["ladder"]:
        assert row["reconstruction_quality_used_for_decision"] is False
        assert row["fixed_target_digest"] == result["target_digest"]
        assert row["cohort_digest"] == result["cohort_digest"]
        assert row["decision_value_basis"] == "fixed_target_rank_ic"
        # the noise-group delta is a FIXED-TARGET delta, never a reconstruction delta
        if row["incremental_reconstruction_quality"] is not None and row[
                "incremental_decision_value"] is not None:
            assert row["incremental_decision_value"] == pytest.approx(
                row["fixed_target_rank_ic_mean"]
                - result["ladder"][result["ladder"].index(row) - 1]["fixed_target_rank_ic_mean"])


# --- committed G10 artifact: denominators and a way to go red ----------------

def _manifest(lab_root) -> dict:
    return json.loads((lab_root / "evidence" / "corrective_mode4_v3" / "RF-04"
                       / "model_design_selection_manifest.json").read_text(encoding="utf-8"))


def test_committed_manifest_has_denominators_and_can_go_red(lab_root):
    manifest = _manifest(lab_root)
    assert manifest["gate"] == "G10"
    assert manifest["status"] == "SELECTED"
    denominators = manifest["denominators"]
    assert denominators["candidates_attempted"] == denominators["candidates_evaluated"] > 0
    assert denominators["folds_scored"] > 0
    assert denominators["observations_scored"] > 0

    grid = manifest["candidate_grid"]
    assert "M0" in grid["models"] and "JM" in grid["models"]
    assert set(grid["n_state_candidates"]) >= {2, 3}
    assert len(grid["lambda_candidates"]) >= 2
    assert "JM" in {c["model"] for c in manifest["candidates"]}

    falsification = manifest["falsification"]
    assert falsification["can_go_red"] is True
    assert falsification["inner_scaler_mutation_probe"]["inner_train"][
        "all_folds_unchanged"] is True
    assert falsification["inner_scaler_mutation_probe"]["whole_calibration_control"][
        "any_fold_changed"] is True
    assert falsification["leaky_scaler_control"]["objectives_differ"] is True
    assert manifest["holdout_used"] is False
    assert manifest["fixed_target_ablation"]["decided_on"] == "fixed_target_rank_ic"


def test_manifest_is_not_selectable_from_a_vacuous_run():
    weights = np.full(2, 0.5)
    with pytest.raises(ValueError):
        MS.evaluate_design_ladder(np.zeros((10, 2)), weights)
    tiny = MS.evaluate_design_ladder(np.random.default_rng(0).normal(size=(35, 2)), weights,
                                     candidates=(MS.LadderCandidate("JM", 2, 1.0),),
                                     n_folds=3, min_train=100)
    assert tiny["status"] == "NOT_EVALUABLE"
    assert tiny["denominators"]["candidates_evaluated"] == 0


def test_alternate_cadence_is_registered_scored_but_not_selected():
    raw = _synthetic_raw(n=420, j=3)
    candidate = MS.LadderCandidate("JM", 2, 1.0, cadence="8h", observation_stride=2)
    manifest = MS.evaluate_design_ladder(raw, np.full(3, 1 / 3), candidates=(candidate,),
                                         seeds=(11,), n_folds=3, min_train=100)
    assert manifest["candidates"][0]["status"] == "SCORED"
    assert manifest["candidates"][0]["score"]["observations_scored"] > 0
    assert manifest["selection"] is None, (
        "a non-primary cadence rung is scored for the record but cannot be selected: lambda is "
        "not transferable across cadences")
    assert manifest["status"] == "NOT_EVALUABLE"
    menus = {entry["cadence"] for entry in manifest["candidate_grid"]["cadence_menu"]}
    assert {"4h", "8h"} <= menus


def test_committed_registry_maps_one_to_one_and_guards_market_transitions(lab_root):
    registry = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-04"
         / "causal_model_registry.json").read_text(encoding="utf-8"))
    mapping = registry["namespace_mappings"][0]
    assert mapping["one_to_one"] is True
    assert mapping["assignment_method"] == "exact_permutation"
    assert set(mapping["matched_states"]).isdisjoint(mapping["unmatched_states"])
    assert mapping["emits_market_transition"] is False
    assert registry["market_transition_guard"]["refit_events_emitted_as_market_transitions"] == 0
    event = registry["model_transition_events"][0]
    assert event["emits_market_transition"] is False
    assert event["event_class"] == "MODEL_VERSION"
    mismatch = registry["namespace_mappings"][1]
    assert mismatch["k_matches"] is False and mismatch["one_to_one"] is False


def test_committed_emission_sample_has_economic_context_and_zero_false_triggers(lab_root):
    sample = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-04"
         / "emission_tape_sample.json").read_text(encoding="utf-8"))
    assert sample["sample_size"] > 0
    assert sample["total_emissions_computed"] >= sample["sample_size"]
    for emission in sample["emissions"]:
        assert len(emission["economic_context"]) == len(sample["emissions"][0]["economic_context"])
        assert "state_common" in emission
    control = sample["namespace_transition_control"]
    assert control["namespace_only_tape_triggers"] == control["constant_namespace_tape_triggers"]
    assert control["control_can_fire"] is True
    assert control["verdict"] == "PASS"
