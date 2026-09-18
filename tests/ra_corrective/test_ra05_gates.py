"""RA-05 verifier red/green gates (RA-GUIDE-1.0 section 9, section 14.3).

The green bundle must PASS; every red case must FAIL with a named reason.
Uses lab_tmp because pytest's tmp_path is outside LAB_ROOT and refused by the
read guard.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.ra.verifier_ra05 import ARMS, CASE_IDS, REQUIRED_ARTIFACTS, verify_ra05


def _xml(path: Path, *, tests=1, failures=0, skipped=0, node_ids=None) -> Path:
    suite = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                     "errors": "0", "skipped": str(skipped)})
    for nid in (node_ids or ["test_ra05_bundle::test_dummy"]):
        cls, _, name = nid.partition("::")
        ET.SubElement(suite, "testcase", {"classname": cls or "t", "name": name or nid})
    ET.ElementTree(suite).write(path)
    return path


def _all_node_ids():
    return [f"test_ra05_bundle::test_{case.lower()}" for case in CASE_IDS]


def _bundle(root: Path, *, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    docs = {
        "discovery_spec.json": {"window": {"start": "2021-01-01", "end": "2021-04-01"},
                                "primary_contrast": "M4_REGIME - M4_CAL_MATCHED"},
        "cal_matched_forecast.json": {"chosen_test_days": 56,
                                      "never_uses_realized_window_trigger_count": True},
        "scheduler_audit.json": {"accepted_total": 1, "deployed_triggers": 2},
        "arms_result.json": {"arms": {arm: {"ok": True} for arm in ARMS}},
        "action_divergence.json": {"pairwise": {"STATIC_vs_M4_CAL": {"diverged": True}}},
        "descriptive_returns.json": {"note": "point estimates only; scope limited",
                                     "by_arm": {arm: {"status": "OK"} for arm in ARMS}},
        "phase_gate.json": {"schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-05",
                            "guide_version": "RA-GUIDE-1.0", "implementation_status": "COMPLETE",
                            "technical_gate": "PASS", "research_status": "DISCOVERY_ONLY",
                            "owner_review": {"status": "PENDING", "decision_ref": None},
                            "can_start_next_phase": False},
    }
    if mutate:
        mutate(docs)
    (root / "report.md").write_text(
        "# RA-05 report\n\n## 7. Scientific result va kha nang ket luan\n"
        "- Action divergence (the RA-05 mechanism question, independent of PnL): diverged\n")
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


def test_ra05_verifier_passes_on_valid_bundle(lab_tmp):
    root = _bundle(lab_tmp / "green")
    xml = _xml(lab_tmp / "green.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "PASS", verdict["gates"]
    assert set(verdict["gates"]) == {"G05-EXEC", "G05-TRACE", "G05-LEARN", "G05-SCOPE",
                                     "G05-MANIFEST"}


def test_ra05_verifier_fails_on_missing_artifact(lab_tmp):
    root = _bundle(lab_tmp / "missing")
    (root / "scheduler_audit.json").unlink()
    xml = _xml(lab_tmp / "missing.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("missing artifacts" in r for r in verdict["gates"]["G05-EXEC"]["reasons"])


def test_ra05_verifier_fails_when_an_arm_is_silently_dropped(lab_tmp):
    def drop_arm(docs):
        del docs["arms_result.json"]["arms"]["M4_REGIME"]

    root = _bundle(lab_tmp / "dropped", mutate=drop_arm)
    xml = _xml(lab_tmp / "dropped.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("M4_REGIME" in r for r in verdict["gates"]["G05-EXEC"]["reasons"])


def test_ra05_verifier_fails_when_an_arm_neither_ok_nor_erred(lab_tmp):
    def half_reported(docs):
        docs["arms_result.json"]["arms"]["M4_CAL"] = {"ok": False}  # no error recorded either

    root = _bundle(lab_tmp / "half", mutate=half_reported)
    xml = _xml(lab_tmp / "half.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("silently dropped" in r for r in verdict["gates"]["G05-EXEC"]["reasons"])


def test_ra05_verifier_fails_on_missing_d_case_test(lab_tmp):
    root = _bundle(lab_tmp / "nod")
    node_ids = [n for n in _all_node_ids() if "d04" not in n]
    xml = _xml(lab_tmp / "nod.xml", tests=len(node_ids), node_ids=node_ids)
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("D04" in r for r in verdict["gates"]["G05-TRACE"]["reasons"])


def test_ra05_verifier_fails_when_report_lacks_a_mechanism_conclusion(lab_tmp):
    root = _bundle(lab_tmp / "nomech")
    (root / "report.md").write_text("# RA-05 report\n\n| arm | Sharpe |\n|---|---|\n| STATIC | 0.1 |\n")
    entries = []
    for name in REQUIRED_ARTIFACTS:
        if name in ("phase_manifest.json",):
            continue
        if name.endswith(".json"):
            data = (root / name).read_bytes()
            entries.append({"relpath": name, "sha256": hashlib.sha256(data).hexdigest()})
    (root / "phase_manifest.json").write_text(json.dumps({"artifacts": entries}))
    xml = _xml(lab_tmp / "nomech.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("mechanism" in r for r in verdict["gates"]["G05-LEARN"]["reasons"])


def test_ra05_verifier_fails_when_divergence_has_no_pairwise_comparisons(lab_tmp):
    def empty_pairwise(docs):
        docs["action_divergence.json"]["pairwise"] = {}

    root = _bundle(lab_tmp / "nopair", mutate=empty_pairwise)
    xml = _xml(lab_tmp / "nopair.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("pairwise" in r for r in verdict["gates"]["G05-LEARN"]["reasons"])


def test_ra05_verifier_fails_when_descriptive_returns_omits_scope_note(lab_tmp):
    def drop_note(docs):
        del docs["descriptive_returns.json"]["note"]

    root = _bundle(lab_tmp / "nonote", mutate=drop_note)
    xml = _xml(lab_tmp / "nonote.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("scope limits" in r for r in verdict["gates"]["G05-SCOPE"]["reasons"])


def test_ra05_verifier_fails_when_research_status_overclaims(lab_tmp):
    def overclaim(docs):
        docs["phase_gate.json"]["research_status"] = "POSITIVE_WITHIN_SCOPE"

    root = _bundle(lab_tmp / "overclaim", mutate=overclaim)
    xml = _xml(lab_tmp / "overclaim.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("DISCOVERY_ONLY" in r for r in verdict["gates"]["G05-SCOPE"]["reasons"])


def test_ra05_verifier_fails_when_owner_review_is_not_pending(lab_tmp):
    def approve(docs):
        docs["phase_gate.json"]["owner_review"] = {"status": "APPROVED", "decision_ref": "x"}

    root = _bundle(lab_tmp / "approved", mutate=approve)
    xml = _xml(lab_tmp / "approved.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("PENDING" in r for r in verdict["gates"]["G05-SCOPE"]["reasons"])


def test_ra05_verifier_fails_on_hash_mismatch(lab_tmp):
    root = _bundle(lab_tmp / "tamper")
    manifest = json.loads((root / "phase_manifest.json").read_text())
    for entry in manifest["artifacts"]:
        if entry["relpath"] == "arms_result.json":
            entry["sha256"] = "0" * 64
    (root / "phase_manifest.json").write_text(json.dumps(manifest))
    xml = _xml(lab_tmp / "tamper.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("hash mismatch" in r for r in verdict["gates"]["G05-MANIFEST"]["reasons"])


def test_ra05_verifier_fails_on_test_failures(lab_tmp):
    root = _bundle(lab_tmp / "redtests")
    xml = _xml(lab_tmp / "redtests.xml", tests=len(CASE_IDS), failures=1,
              node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("failures" in r for r in verdict["gates"]["G05-EXEC"]["reasons"])


def test_ra05_verifier_fails_when_protected_tree_changed(lab_tmp):
    root = _bundle(lab_tmp / "dirty")
    xml = _xml(lab_tmp / "dirty.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after=" M some_file.py\n")
    assert verdict["overall"] == "FAIL"
    assert any("protected tree changed" in r for r in verdict["gates"]["G05-SCOPE"]["reasons"])


def test_ra05_verifier_fails_when_a_json_artifact_reports_blocked(lab_tmp):
    def block_it(docs):
        docs["scheduler_audit.json"]["status"] = "BLOCKED"

    root = _bundle(lab_tmp / "blocked", mutate=block_it)
    xml = _xml(lab_tmp / "blocked.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra05(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("BLOCKED" in r for r in verdict["gates"]["G05-EXEC"]["reasons"])
