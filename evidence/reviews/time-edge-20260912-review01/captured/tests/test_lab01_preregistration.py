"""L01.1 / L01.3 / L01.5 tests: marker discipline, env pin, quarantine, freeze policy."""

from __future__ import annotations

import json

import pytest

from crypto_regime_lab.safety.paths import SafetyViolation


# --- L01.1 marker discipline ------------------------------------------

def test_marker_accepts_the_registered_study(policy):
    assert policy.validate_lab_marker("crypto_regime_timeedge_v2") == []


def test_marker_rejects_a_different_study(policy):
    problems = policy.validate_lab_marker("some_other_study")
    assert problems and "one LAB_ROOT holds exactly one study" in problems[0]
    with pytest.raises(SafetyViolation):
        policy.assert_lab_marker_ok("some_other_study")


def test_marker_refuses_an_occupied_directory_with_no_marker(policy, lab_tmp):
    """A populated directory without a marker must not be adopted as a lab."""
    from crypto_regime_lab.safety.paths import SandboxPolicy, realpath

    (lab_tmp / "someones_work.txt").write_text("x", encoding="utf-8")
    candidate = SandboxPolicy(lab_root=realpath(lab_tmp), protected_roots=policy.protected_roots)
    problems = candidate.validate_lab_marker("crypto_regime_timeedge_v2")
    assert problems and "refusing to reuse an arbitrary directory" in problems[0]


# --- L01.3 environment pin --------------------------------------------

def test_lockfile_is_hash_pinned_and_complete(lab_root):
    lock = lab_root / "configs" / "requirements.lock"
    if not lock.is_file():
        pytest.skip("run scripts/pin_environment.py")
    lines = lock.read_text().splitlines()
    entries = [ln for ln in lines if ln and not ln.startswith("#")]
    unpinned = [ln for ln in lines if ln.startswith("# UNPINNED_LOCAL_ARTIFACT")]
    assert unpinned == [], f"every package must resolve to a retained artifact: {unpinned}"
    assert len(entries) >= 25
    assert all("--hash=sha256:" in ln for ln in entries)
    assert any(ln.startswith("quantbt-engine==1.1.1 ") for ln in entries)
    assert any(ln.startswith("quantbt-native==0.4.2 ") for ln in entries)


def test_environment_fingerprint_records_numba_and_thread_metadata():
    from crypto_regime_lab.evidence.manifest import environment_fingerprint

    fingerprint = environment_fingerprint()
    assert fingerprint["numba"]["numba_version"]
    assert fingerprint["numba"]["llvmlite_version"]
    assert "fastmath_policy" in fingerprint["numba"]
    assert "OMP_NUM_THREADS" in fingerprint["threads"]


def test_baseline_and_candidate_import_from_different_origins(lab_root):
    pins = sorted((lab_root / "evidence").rglob("environment_pin.json"))
    if not pins:
        pytest.skip("run scripts/pin_environment.py")
    record = json.loads(pins[-1].read_text())["process_separation"]
    assert record["status"] == "SEPARATED", record
    assert record["baseline_from_lab_venv"] is True
    assert record["candidate_from_lab_copy"] is True
    assert record["neither_imports_from_a_protected_root"] is True


def test_process_group_is_owned(lab_root):
    pins = sorted((lab_root / "evidence").rglob("environment_pin.json"))
    if not pins:
        pytest.skip("run scripts/pin_environment.py")
    assert json.loads(pins[-1].read_text())["process_group"]["status"] == "OWNED"


# --- L01.5 quarantine + freeze policy ---------------------------------

@pytest.fixture(scope="module")
def quarantine(lab_root):
    path = lab_root / "configs" / "preset_quarantine_catalog.json"
    if not path.is_file():
        pytest.skip("run scripts/quarantine_presets.py")
    return json.loads(path.read_text())


def test_every_preset_is_quarantined_from_the_primary_path(quarantine):
    assert quarantine["presets"], "catalog is empty"
    for preset in quarantine["presets"]:
        assert preset["provenance"] == "user_full_sample_tpe"
        assert preset["eligible_for_early_fold_warm_start"] is False
        assert preset["eligible_for_primary_candidate_bank"] is False
        assert preset["eligible_for_independent_oos_claim"] is False


def test_preset_identity_includes_file_hash_and_values(quarantine):
    """Guide A.1: the same dictionary name in two files is not the same preset."""
    collisions = quarantine["colliding_dictionary_names"]
    assert collisions, "expected repeated dictionary names across the four files"
    for name, ids in collisions.items():
        assert len(set(ids)) == len(ids), f"{name} produced duplicate identities"


def test_literal_dict_counts_reconcile_with_the_guide(quarantine):
    """Three files match exactly; the single difference is explained, not ignored."""
    crosscheck = quarantine["guide_crosscheck"]
    matching = [f for f, rec in crosscheck.items() if rec["literal_count_matches_guide"]]
    assert set(matching) == {"hash_momentum.py", "vwap.py", "signal_combine.py"}
    hma = crosscheck["adaptive_hma_cpp.py"]
    assert hma["observed_literal_dict_count"] == 14
    assert hma["guide_a1_literal_dict_count"] == 13
    assert hma["outside_modal_group"] == ["sl_mode_map@L311"]
    assert "sl_mode_map" in quarantine["discrepancy_reading"]


def test_schema_split_is_deferred_to_lab02(quarantine):
    assert "LAB-02" in quarantine["lab02_followup"]
    note = quarantine["modal_grouping_is_a_heuristic_not_a_schema_decision"]
    assert "grouping hint" in note and "LAB-02" in note


def test_freeze_and_holdout_policy_is_registered(lab_root):
    path = lab_root / "configs" / "freeze_holdout_policy.json"
    if not path.is_file():
        pytest.skip("run scripts/preregister_study.py")
    policy_doc = json.loads(path.read_text())
    assert policy_doc["holdout_status"]["untouched_holdout_exists"] is False
    assert policy_doc["holdout_status"]["claim_level"] == "RETROSPECTIVE_NESTED_CAUSAL_RESEARCH"
    assert policy_doc["freeze_procedure"]["validator_rule"]
    assert "LAB-02 certification AND LAB-03 data qualification" == policy_doc["unlock_gates"]["market_execution"]
