"""FUP-05 acceptance — the deep-dive registration and its placebo verdict, guarded.

FUP-05 registers the already-finished 12-month decay deep-dive
(ra07decaydive-20260921T072850Z-22eb0631) as a discovery dataset with verdict
DESCRIPTIVE_ONLY, and runs its PLACEBO_TIMING control against a falsification
bar written BEFORE the placebo existed. These tests pin the load-bearing
properties so neither the registration nor the verdict can silently drift:

* the FUP-05 entry exists in the follow-up registration file at index 4 and
  declares DESCRIPTIVE_ONLY (no market/economic claim may ride on this run);
* every deviation the deep-dive took from the frozen RA-05/07 contract is
  disclosed in the placebo artifact (an undisclosed knob is a silent protocol
  change);
* the dataset lock matches the deep-dive files byte-for-byte (hashes
  recomputed, not trusted);
* the verdict follows the pre-registered calendar band mechanically: a
  placebo at/above the band is CADENCE_ARTIFACT, below it is
  SURVIVED_FALSIFICATION — re-asserted here from the recorded numbers, so a
  verdict that contradicts its own inputs cannot persist.
"""

from __future__ import annotations

import json

from crypto_regime_lab.safety.paths import sha256_file

FUP05 = ("evidence", "corrective_mode4_v3", "FUP-05")
REGISTRATION = ("evidence", "corrective_mode4_v3", "followup-studies",
                "followup_studies_registration.json")
DEEPDIVE = ("evidence", "regime_time_edge_ra_v1",
            "ra07decaydive-20260921T072850Z-22eb0631")
RESULT = "placebo_result.json"
STUDY_ID = "FUP-05"

REQUIRED_DEVIATION_KNOBS = {"trials", "M4_CAL test_days",
                            "engine output profile", "window"}


def _registration(lab_root) -> dict:
    payload = json.loads(lab_root.joinpath(*REGISTRATION).read_text(encoding="utf-8"))
    assert payload["studies"][4]["id"] == STUDY_ID, (
        "FUP-05 must be studies[4]; the registration order shifted")
    return payload["studies"][4]


def _result(lab_root) -> dict:
    return json.loads(lab_root.joinpath(*FUP05).joinpath(RESULT).read_text(encoding="utf-8"))


def test_fup05_is_registered_descriptive_only(lab_root):
    entry = _registration(lab_root)
    assert "DESCRIPTIVE_ONLY" not in entry.get("title", "")
    assert any("DESCRIPTIVE_ONLY" in goal for goal in entry["non_goals"]), (
        "the registration must forbid market/economic claims on this run")
    assert entry["budget"].startswith("T0 host-only"), entry["budget"]


def test_fup05_discloses_every_deviation_knob(lab_root):
    """The deep-dive ran off-contract (50 trials, 40-day CAL folds, score
    profile, 12-month window). Each knob must appear in the recorded
    deviations with both sides stated, or the run is unregistered science."""
    result = _result(lab_root)
    knobs = {row["knob"] for row in result["disclosed_deviations"]}
    assert REQUIRED_DEVIATION_KNOBS <= knobs, (
        f"undisclosed knobs: {sorted(REQUIRED_DEVIATION_KNOBS - knobs)}")
    for row in result["disclosed_deviations"]:
        assert row["frozen_contract"] != row["deepdive_value"], row
        assert str(row["reason"]).strip(), row


def test_fup05_dataset_lock_matches_the_deepdive_files(lab_root):
    """The registration must cite the run it actually ran: recompute every
    hash, and require the fold counts to equal the deep-dive's own record."""
    result = _result(lab_root)
    dataset = result["discovery_dataset"]
    assert dataset["verdict"] == "DESCRIPTIVE_ONLY"
    assert dataset["trials"] == 50 and dataset["engine_report_level"] == "score"
    deepdive_payload = json.loads(
        lab_root.joinpath(*DEEPDIVE).joinpath("decay_deepdive.json").read_text(encoding="utf-8"))
    for rel, record in dataset["files"].items():
        assert sha256_file(lab_root.joinpath(*DEEPDIVE).joinpath(rel)) == record["sha256"], rel
    for arm, folds in dataset["fold_counts"].items():
        assert folds == deepdive_payload["arm_summaries"][arm]["meta"].get("fold_count"), arm
    assert dataset["fold_counts"] == {"M4_CAL": 10, "M4_CAL_MATCHED": 7, "M4_REGIME": 9}


def test_fup05_verdict_follows_the_preregistered_band(lab_root):
    """Re-derive the verdict from the recorded numbers: the artifact must not
    be able to say SURVIVED while its own placebo sits inside the calendar
    band it registered, or vice versa."""
    result = _result(lab_root)
    band = result["calendar_band"]
    assert band["M4_CAL_mean_decay"] < 0 and band["M4_CAL_MATCHED_mean_decay"] < 0
    assert band["M4_REGIME_mean_decay"] > 0, (
        "the band must record the actual deep-dive means, not convenient ones")
    mean = result["placebo"]["mean_daily_return_decay"]["mean_signed_delta"]
    assert mean is not None, "a placebo without measurable decay decides nothing"
    cal_worst = max(band["M4_CAL_mean_decay"], band["M4_CAL_MATCHED_mean_decay"])
    expected = "CADENCE_ARTIFACT" if mean >= cal_worst else "SURVIVED_FALSIFICATION"
    assert result["verdict"]["label"] == expected, (
        f"placebo mean {mean:.6f} vs band worst {cal_worst:.6f} demands {expected}")
    assert result["verdict_vocabulary"] == "DESCRIPTIVE_ONLY"
    assert result["placebo"]["fold_count"] >= 5, (
        "fewer than 5 placebo folds cannot even describe a pattern")
    assert result["placebo_seed"] == 20260921, (
        "the seed is part of the registered contract, not a detail")

