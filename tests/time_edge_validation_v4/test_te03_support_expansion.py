"""TE-03 support expansion: coverage revision, bridge and >=20 episodes."""
import pandas as pd

from crypto_regime_lab.time_edge.coverage import (COVERAGE_COLLECTION_SCHEMA,
                                                  COVERAGE_REVISION_SCHEMA,
                                                  check_coverage_revision)
from crypto_regime_lab.time_edge.storage import file_digest, read


def load(lab_root, relative):
    return read(lab_root / relative)


def test_coverage_revision_extents_and_floor(lab_root):
    revision = load(lab_root, "evidence/time_edge_validation_v4/coverage-revisions/TE03-COVERAGE-R01.json")
    assert revision["schema"] == COVERAGE_REVISION_SCHEMA
    prior = revision["prior_coverage"]
    revised = revision["revised_coverage"]
    assert prior["target_series"]["origins"] == 14 and prior["model_series"]["vintages"] == 12
    assert prior["support_measured"]["evaluable_outer_targets"] == 8
    assert revision["support_floor"]["value"] == 20
    assert revised["target_series"]["origins"] == 31 and revised["target_series"]["delta_origins"] == 17
    assert revised["model_series"]["vintages"] == 29
    prior_last = pd.Timestamp(prior["target_series"]["last_origin"])
    extension = pd.Timestamp(revised["target_series"]["extension_start"])
    assert extension == prior_last + pd.Timedelta(days=28)
    assert revision["unchanged"]["grid_days"] == 28 and revision["unchanged"]["target_horizon_days"] == 28
    for name, reference in revision["evidence_refs"].items():
        assert file_digest(lab_root / reference["path"]) == reference["sha256"], name


def test_coverage_bridge_appends_without_gaps_or_duplicates(lab_root):
    bridge = load(lab_root, "evidence/time_edge_validation_v4/host-targets-coverage-01.json")
    prior = load(lab_root, "evidence/time_edge_validation_v4/host-targets-01.json")
    assert bridge["schema"] == COVERAGE_COLLECTION_SCHEMA
    assert bridge["coverage_revision"]["revision_id"] == "TE03-COVERAGE-R01"
    origins = [pd.Timestamp(row["origin"]) for row in bridge["targets"]]
    assert len(origins) == 31 and len(set(origins)) == 31
    assert all(b - a == pd.Timedelta(days=28) for a, b in zip(origins, origins[1:]))
    assert origins[:len(prior["targets"])] == [pd.Timestamp(row["origin"]) for row in prior["targets"]]
    identities = {row["source_identity"] for row in bridge["sources"]}
    assert len(identities) == 2 and len(bridge["sources"]) == 2
    assert all(row["role"] in ("prior", "extension") for row in bridge["sources"])


def test_registered_extension_series_is_accepted_and_embedded(lab_root):
    revision = load(lab_root, "evidence/time_edge_validation_v4/coverage-revisions/TE03-COVERAGE-R01.json")
    registered = load(lab_root, "configs/time_edge_validation_v4/te03_coverage_registration.json")
    target_spec = {"target_series": {"alpha_id": "A-SC", "cell_id": "A-SC/BTCUSDT",
                                     "start": "2021-12-29T00:00:00Z", "end": "2023-04-19T00:00:00Z"}}
    checked = check_coverage_revision(revision, spec=target_spec, registered=registered)
    assert checked["revised_coverage"]["target_series"]["delta_origins"] == 17
    model_spec = {"model_series": {"start": "2021-02-01T00:00:00Z", "end": "2023-04-19T00:00:00Z"}}
    check_coverage_revision(revision, spec=model_spec, registered=registered)
    job = load(lab_root, "evidence/time_edge_validation_v4/plans/te-host-targets-03/job.json")
    reference = job["inputs"]["coverage_revision"]
    assert file_digest(lab_root / reference["path"]) == reference["sha256"]
    assert job["budget_revision"]["revision_id"] == "TE02-PILOT-R03-REV04"


def test_information_value_reaches_twenty_evaluable_episodes(lab_root):
    info = load(lab_root, "evidence/time_edge_validation_v4/te03-r2/information_value.json")
    summary = info["summary"]
    assert summary["evaluable"] >= 20, summary
    assert summary["planned"] >= summary["evaluable"]
    assert info["inference"]["status"] in ("ESTIMATED", "ESTIMATED_NOT_CLAIMED", "NOT_EVALUABLE")
    if info["inference"]["status"] == "ESTIMATED":
        assert info["inference"]["episodes"] >= 20 and info["inference"]["n"] >= 365
        assert info["inference"]["block"] == 28


def test_every_unavailable_outer_row_has_a_reason_not_a_zero(lab_root):
    info = load(lab_root, "evidence/time_edge_validation_v4/te03-r2/information_value.json")
    for row in info["rows"]:
        if row["effect"] is None:
            assert row["reason"]
    assert info["summary"]["evaluable"] + sum(1 for row in info["rows"] if row["effect"] is None) == len(info["rows"])
    decision = load(lab_root, "evidence/time_edge_validation_v4/te03-r2/model_decision.json")
    assert decision["vintages"] == 29 and decision["m0_control_vintages"] + decision["selected_inner_informative"] == 29
