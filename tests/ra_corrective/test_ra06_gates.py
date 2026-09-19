"""RA-06 verifier red/green gates (RA-GUIDE-1.0 section 10, section 14.3).

The green bundle must PASS; every red case must FAIL with a named reason.
Uses lab_tmp because pytest's tmp_path is outside LAB_ROOT and refused by
the read guard.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.ra.verifier_ra06 import CASE_IDS, REQUIRED_ARTIFACTS, verify_ra06


def _xml(path: Path, *, tests=1, failures=0, skipped=0, node_ids=None) -> Path:
    suite = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                     "errors": "0", "skipped": str(skipped)})
    for nid in (node_ids or ["test_ra06_bundle::test_dummy"]):
        cls, _, name = nid.partition("::")
        ET.SubElement(suite, "testcase", {"classname": cls or "t", "name": name or nid})
    ET.ElementTree(suite).write(path)
    return path


def _all_node_ids():
    return [f"test_ra06_bundle::test_{case.lower()}" for case in CASE_IDS]


def _bundle(root: Path, *, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    docs = {
        "panel_a.json": {"rows": [{"origin": "2021-01-01T00:00:00+00:00", "arm": "STATIC"}]},
        "origins.json": {"origins": ["2021-01-21T00:00:00+00:00"], "rule": "calendar grid"},
        "panel_b.json": {"capability_status": "EXECUTED",
                        "rows": [{"origin": "2021-01-21T00:00:00+00:00", "status": "OK",
                                 "g": {"status": "OK", "g": 0.001}}]},
        "model_ladder.json": {"status": "INSUFFICIENT_SUPPORT", "support": 5, "min_required": 8,
                              "disposition": "measured, preregistered branch"},
        "controller_examples.json": {"examples": [{"request_search": False}]},
        "lock_decision.json": {"decision": "KEEP_BASELINE", "reason": "insufficient support",
                               "carries_to_ra07": None},
        "phase_gate.json": {"schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-06",
                            "guide_version": "RA-GUIDE-1.0", "implementation_status": "COMPLETE",
                            "technical_gate": "PASS",
                            "owner_review": {"status": "PENDING", "decision_ref": None},
                            "can_start_next_phase": False},
    }
    if mutate:
        mutate(docs)
    (root / "report.md").write_text("# RA-06 report\n")
    (root / "handoff.md").write_text("# handoff\n")
    for name, doc in docs.items():
        (root / name).write_text(json.dumps(doc))
    entries = []
    for name in REQUIRED_ARTIFACTS:
        if name == "phase_manifest.json":
            continue
        if name.endswith(".json"):
            data = (root / name).read_bytes()
            entries.append({"relpath": name, "sha256": hashlib.sha256(data).hexdigest()})
    (root / "phase_manifest.json").write_text(json.dumps({"artifacts": entries}))
    return root


def test_ra06_verifier_passes_on_valid_bundle(lab_tmp):
    root = _bundle(lab_tmp / "green")
    xml = _xml(lab_tmp / "green.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "PASS", verdict["gates"]
    assert set(verdict["gates"]) == {"G06-PANEL", "G06-MODEL", "G06-SCOPE", "G06-MANIFEST"}


def test_ra06_verifier_fails_on_missing_artifact(lab_tmp):
    root = _bundle(lab_tmp / "missing")
    (root / "origins.json").unlink()
    xml = _xml(lab_tmp / "missing.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("missing artifacts" in r for r in verdict["gates"]["G06-PANEL"]["reasons"])


def test_ra06_verifier_fails_when_panel_a_has_no_rows(lab_tmp):
    def empty_panel_a(docs):
        docs["panel_a.json"]["rows"] = []

    root = _bundle(lab_tmp / "emptypanel", mutate=empty_panel_a)
    xml = _xml(lab_tmp / "emptypanel.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no rows" in r for r in verdict["gates"]["G06-PANEL"]["reasons"])


def test_ra06_verifier_allows_blocked_capability_with_a_reason(lab_tmp):
    def blocked(docs):
        docs["panel_b.json"] = {"capability_status": "BLOCKED_CAPABILITY",
                                "blocked_reason": "no engine path available", "rows": []}

    root = _bundle(lab_tmp / "blocked_ok", mutate=blocked)
    xml = _xml(lab_tmp / "blocked_ok.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["gates"]["G06-PANEL"]["pass"], verdict["gates"]["G06-PANEL"]


def test_ra06_verifier_fails_blocked_capability_with_no_reason(lab_tmp):
    def blocked_no_reason(docs):
        docs["panel_b.json"] = {"capability_status": "BLOCKED_CAPABILITY", "rows": []}

    root = _bundle(lab_tmp / "blocked_bad", mutate=blocked_no_reason)
    xml = _xml(lab_tmp / "blocked_bad.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no reason" in r for r in verdict["gates"]["G06-PANEL"]["reasons"])


def test_ra06_verifier_fails_on_missing_p_case_test(lab_tmp):
    root = _bundle(lab_tmp / "nop")
    node_ids = [n for n in _all_node_ids() if "p05" not in n]
    xml = _xml(lab_tmp / "nop.xml", tests=len(node_ids), node_ids=node_ids)
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("P05" in r for r in verdict["gates"]["G06-PANEL"]["reasons"])


def test_ra06_verifier_fails_when_insufficient_support_has_no_disposition(lab_tmp):
    def no_disposition(docs):
        del docs["model_ladder.json"]["disposition"]

    root = _bundle(lab_tmp / "nodisp", mutate=no_disposition)
    xml = _xml(lab_tmp / "nodisp.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no measured disposition" in r for r in verdict["gates"]["G06-MODEL"]["reasons"])


def test_ra06_verifier_fails_when_fit_attempted_uses_calibrated_language(lab_tmp):
    def fake_fit(docs):
        docs["model_ladder.json"] = {"status": "FIT_ATTEMPTED",
                                     "age_only": {"calibrated_probability_language_used": True},
                                     "age_context": {"calibrated_probability_language_used": False}}

    root = _bundle(lab_tmp / "calib", mutate=fake_fit)
    xml = _xml(lab_tmp / "calib.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("calibrated-probability" in r for r in verdict["gates"]["G06-MODEL"]["reasons"])


def test_ra06_verifier_fails_when_lock_baseline_also_carries_a_revision(lab_tmp):
    def contradictory(docs):
        docs["lock_decision.json"]["carries_to_ra07"] = {"revision": "AGE_CONTEXT"}

    root = _bundle(lab_tmp / "contra", mutate=contradictory)
    xml = _xml(lab_tmp / "contra.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("must not also carry" in r for r in verdict["gates"]["G06-SCOPE"]["reasons"])


def test_ra06_verifier_fails_when_lock_age_context_carries_nothing(lab_tmp):
    def empty_carry(docs):
        docs["lock_decision.json"] = {"decision": "LOCK_AGE_CONTEXT", "reason": "improved",
                                      "carries_to_ra07": None}

    root = _bundle(lab_tmp / "emptycarry", mutate=empty_carry)
    xml = _xml(lab_tmp / "emptycarry.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("carries nothing forward" in r for r in verdict["gates"]["G06-SCOPE"]["reasons"])


def test_ra06_verifier_fails_when_owner_review_is_not_pending(lab_tmp):
    def approve(docs):
        docs["phase_gate.json"]["owner_review"] = {"status": "APPROVED", "decision_ref": "x"}

    root = _bundle(lab_tmp / "approved", mutate=approve)
    xml = _xml(lab_tmp / "approved.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("PENDING" in r for r in verdict["gates"]["G06-SCOPE"]["reasons"])


def test_ra06_verifier_fails_on_hash_mismatch(lab_tmp):
    root = _bundle(lab_tmp / "tamper")
    manifest = json.loads((root / "phase_manifest.json").read_text())
    for entry in manifest["artifacts"]:
        if entry["relpath"] == "panel_b.json":
            entry["sha256"] = "0" * 64
    (root / "phase_manifest.json").write_text(json.dumps(manifest))
    xml = _xml(lab_tmp / "tamper.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("hash mismatch" in r for r in verdict["gates"]["G06-MANIFEST"]["reasons"])


def test_ra06_verifier_fails_on_test_failures(lab_tmp):
    root = _bundle(lab_tmp / "redtests")
    xml = _xml(lab_tmp / "redtests.xml", tests=len(CASE_IDS), failures=1, node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("failures" in r for r in verdict["gates"]["G06-PANEL"]["reasons"])


def test_ra06_verifier_fails_when_protected_tree_changed(lab_tmp):
    root = _bundle(lab_tmp / "dirty")
    xml = _xml(lab_tmp / "dirty.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after=" M some_file.py\n")
    assert verdict["overall"] == "FAIL"
    assert any("protected tree changed" in r for r in verdict["gates"]["G06-SCOPE"]["reasons"])


def test_ra06_verifier_fails_when_a_json_artifact_reports_blocked_top_level(lab_tmp):
    def block_it(docs):
        docs["origins.json"]["status"] = "BLOCKED"

    root = _bundle(lab_tmp / "blockedtop", mutate=block_it)
    xml = _xml(lab_tmp / "blockedtop.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra06(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("BLOCKED" in r for r in verdict["gates"]["G06-PANEL"]["reasons"])
