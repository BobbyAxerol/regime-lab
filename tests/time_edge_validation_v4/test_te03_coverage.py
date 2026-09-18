"""TE-03 coverage revisions: registered boundaries, continuity and bridges."""
import pytest

from crypto_regime_lab.experiments.time_edge_contracts import ContractError
from crypto_regime_lab.time_edge.coverage import (COVERAGE_COLLECTION_SCHEMA,
                                                  COVERAGE_REGISTRATION_SCHEMA,
                                                  COVERAGE_REVISION_SCHEMA,
                                                  check_coverage_revision,
                                                  merge_coverage_collections,
                                                  require_registered_coverage)
from crypto_regime_lab.time_edge.planning import make_plan
from crypto_regime_lab.time_edge.storage import file_digest, read, save


def registered():
    return {
        "schema": COVERAGE_REGISTRATION_SCHEMA,
        "target_series": {"start": "2020-12-02T00:00:00Z", "end_exclusive": "2022-01-01T00:00:00Z",
                          "step_days": 28, "horizon_days": 28},
        "model_series": {"start": "2021-02-01T00:00:00Z", "end_exclusive": "2022-01-01T00:00:00Z",
                         "step_days": 28},
    }


def revision(prior_end="2022-01-01T00:00:00Z", revised_target_end="2023-04-19T00:00:00Z",
             extension_start="2021-12-29T00:00:00Z", step_days=28, horizon_days=28):
    return {
        "schema": COVERAGE_REVISION_SCHEMA, "study_id": "time_edge_validation_v4",
        "registration_id": "TE01-R01", "revision_id": "test-revision",
        "stage_scope": "te03_targets_models",
        "prior_coverage": {
            "target_series": {"start": "2020-12-02T00:00:00Z", "end_exclusive": prior_end,
                              "step_days": 28, "horizon_days": 28, "origins": 14,
                              "last_origin": "2021-12-01T00:00:00Z"},
            "model_series": {"start": "2021-02-01T00:00:00Z", "end_exclusive": prior_end,
                             "step_days": 28, "vintages": 12, "last_cutoff": "2021-12-06T00:00:00Z"},
            "support_measured": {"planned_outer_targets": 11, "evaluable_outer_targets": 8},
        },
        "revised_coverage": {
            "target_series": {"start": "2020-12-02T00:00:00Z", "end_exclusive": revised_target_end,
                              "step_days": step_days, "horizon_days": horizon_days,
                              "origins": 31, "extension_start": extension_start,
                              "last_origin": "2023-03-22T00:00:00Z"},
            "model_series": {"start": "2021-02-01T00:00:00Z", "end_exclusive": "2023-04-19T00:00:00Z",
                             "step_days": step_days, "vintages": 29, "last_cutoff": "2023-03-27T00:00:00Z"},
        },
        "support_floor": {"field": "minimum_informative_candidate_episodes", "value": 20},
        "unchanged": {"alpha_id": "A-SC", "cell_id": "A-SC/BTCUSDT", "grid_days": 28, "target_horizon_days": 28},
        "evidence_refs": {"x": {"path": "configs/time_edge_validation_v4/te03_coverage_registration.json",
                                "sha256": "0"*64}},
        "why": "support floor unmet", "what_it_changes": ["end"], "what_it_does_not_change": ["origins"],
    }


def target_spec(start="2021-12-29T00:00:00Z", end="2023-04-19T00:00:00Z"):
    return {"target_series": {"alpha_id": "A-SC", "cell_id": "A-SC/BTCUSDT", "start": start, "end": end,
                              "market": "market", "candidate_bank": "bank"}}


def model_spec(start="2021-02-01T00:00:00Z", end="2023-04-19T00:00:00Z"):
    return {"model_series": {"start": start, "end": end, "features": "features", "targets": "targets",
                             "latency_seconds": 60}}


def test_extending_registered_coverage_without_revision_is_refused():
    with pytest.raises(ContractError, match="register a coverage revision"):
        require_registered_coverage(registered(), target_spec())
    require_registered_coverage(registered(), target_spec(end="2022-01-01T00:00:00Z"))


def test_valid_revision_contains_the_requested_series():
    checked = check_coverage_revision(revision(), spec=target_spec(), registered=registered())
    assert checked["revision_id"] == "test-revision"
    checked = check_coverage_revision(revision(), spec=model_spec(), registered=registered())
    assert checked["revised_coverage"]["model_series"]["vintages"] == 29


def test_revision_must_restate_the_registered_prior_coverage():
    bad = revision()
    bad["prior_coverage"]["target_series"]["end_exclusive"] = "2021-06-01T00:00:00Z"
    with pytest.raises(ContractError, match="does not match the registration"):
        check_coverage_revision(bad, spec=target_spec(), registered=registered())


def test_revision_cannot_move_the_grid_horizon_or_extension_boundary():
    with pytest.raises(ContractError, match="28-day grid"):
        check_coverage_revision(revision(step_days=14), spec=target_spec(), registered=registered())
    with pytest.raises(ContractError, match="horizon"):
        check_coverage_revision(revision(horizon_days=7), spec=target_spec(), registered=registered())
    with pytest.raises(ContractError, match="contiguously"):
        check_coverage_revision(revision(extension_start="2022-01-26T00:00:00Z"),
                                spec=target_spec(start="2022-01-26T00:00:00Z"), registered=registered())
    with pytest.raises(ContractError, match="exceeds the revised coverage"):
        check_coverage_revision(revision(), spec=target_spec(end="2023-06-01T00:00:00Z"), registered=registered())


def test_model_series_must_recompute_from_the_registered_start():
    with pytest.raises(ContractError, match="recomputed from the registered model start"):
        check_coverage_revision(revision(), spec=model_spec(start="2022-01-03T00:00:00Z"), registered=registered())


def test_plan_refuses_extension_without_coverage(lab_root):
    spec = target_spec()
    spec["inputs"] = {"bank": "evidence/time_edge_validation_v4/host-candidate-bank-01.json",
                      "market": "evidence/time_edge_validation_v4/plans/te-host-features-01/market-BTCUSDT.json"}
    with pytest.raises(ContractError, match="register a coverage revision"):
        make_plan(lab_root, run_id="unit-coverage-refused", stage="targets", spec=spec)


def test_merge_bridge_refuses_duplicates_and_backwards_extension(lab_root, lab_tmp):
    def target(origin):
        return {"origin": origin, "outcome_available_at": origin, "cell_id": "A-SC/BTCUSDT",
                "candidate_set_hash": "h", "utilities": [1.0, 2.0]}
    prior = lab_tmp / "prior.json"; extension = lab_tmp / "extension.json"; coverage = lab_tmp / "revision.json"
    save(prior, {"lab_run_id": "prior", "source_identity": "old",
                 "targets": [target("2021-12-01T00:00:00+00:00")]})
    save(extension, {"lab_run_id": "extension", "source_identity": "new",
                     "targets": [target("2021-12-29T00:00:00+00:00")]})
    save(coverage, {"schema": COVERAGE_REVISION_SCHEMA, "revision_id": "r"})
    prior_ref = {"path": str(prior.relative_to(lab_root)), "sha256": file_digest(prior)}
    extension_ref = {"path": str(extension.relative_to(lab_root)), "sha256": file_digest(extension)}
    coverage_ref = {"path": str(coverage.relative_to(lab_root)), "sha256": file_digest(coverage)}
    merged = merge_coverage_collections(lab_root, prior_refs=[prior_ref], extension_ref=extension_ref,
                                        coverage_ref=coverage_ref, kind="targets",
                                        output=str((lab_tmp / "merged.json").relative_to(lab_root)),
                                        lab_run_id="bridge")
    payload = read(lab_root / merged["path"])
    assert payload["schema"] == COVERAGE_COLLECTION_SCHEMA
    assert [row["origin"][:10] for row in payload["targets"]] == ["2021-12-01", "2021-12-29"]
    assert {row["source_identity"] for row in payload["sources"]} == {"old", "new"}
    duplicate = lab_tmp / "duplicate.json"
    save(duplicate, {"lab_run_id": "duplicate", "source_identity": "new2",
                     "targets": [target("2021-12-01T00:00:00+00:00")]})
    with pytest.raises(ContractError, match="duplicate"):
        merge_coverage_collections(lab_root, prior_refs=[prior_ref],
                                   extension_ref={"path": str(duplicate.relative_to(lab_root)),
                                                  "sha256": file_digest(duplicate)},
                                   coverage_ref=coverage_ref, kind="targets",
                                   output=str((lab_tmp / "duplicate-merged.json").relative_to(lab_root)),
                                   lab_run_id="bridge")
    backwards = lab_tmp / "backwards.json"
    save(backwards, {"lab_run_id": "backwards", "source_identity": "old2",
                     "targets": [target("2021-11-03T00:00:00+00:00")]})
    with pytest.raises(ContractError, match="strictly after"):
        merge_coverage_collections(lab_root, prior_refs=[prior_ref],
                                   extension_ref={"path": str(backwards.relative_to(lab_root)),
                                                  "sha256": file_digest(backwards)},
                                   coverage_ref=coverage_ref, kind="targets",
                                   output=str((lab_tmp / "backwards-merged.json").relative_to(lab_root)),
                                   lab_run_id="bridge")


def test_registered_coverage_config_matches_committed_artifacts(lab_root):
    registration = read(lab_root / "configs/time_edge_validation_v4/te03_coverage_registration.json")
    assert registration["schema"] == COVERAGE_REGISTRATION_SCHEMA
    for name in ("target_series", "model_series"):
        artifact = registration[name]["artifact"]
        assert file_digest(lab_root / artifact["path"]) == artifact["sha256"], name
    assert file_digest(lab_root / registration["target_series"]["candidate_bank"]["path"]) == \
        registration["target_series"]["candidate_bank"]["sha256"]
    assert file_digest(lab_root / registration["support"]["prior_information_artifact"]["path"]) == \
        registration["support"]["prior_information_artifact"]["sha256"]
    assert registration["support"]["floor_value"] == 20
