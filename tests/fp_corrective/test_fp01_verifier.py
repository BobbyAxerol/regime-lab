"""FP01-T07-adjacent: the FP-01 verifier fails on the four failure shapes.

Each test builds a minimal bundle directory on the lab_tmp fixture (inside
LAB_ROOT, through the read guard) and asserts verify_fp01 refuses it -- plus
one test proving a fully valid bundle passes, so the refusal tests cannot all
pass by construction (the verifier can genuinely go green).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp01 import (
    ALLOWED_DISPOSITIONS, FINDING_IDS, REQUIRED_ARTIFACTS, REQUIRED_TEST_NODES,
    verify_fp01,
)

VALID_DISPOSITIONS = ["FIXED_WITH_PROOF"] * 9


def _junit(path: Path, *, tests: int = 8, failures: int = 0,
           nodes: tuple = REQUIRED_TEST_NODES) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp01_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _bundle(root: Path, *, head: str = "a" * 40) -> dict:
    docs = {
        "baseline_identity.json": {
            "git_head_full": head, "git_branch": "mode4-corrective",
            "engine": {"quantbt_engine_version": "1.1.1", "quantbt_native_version": "0.4.2"},
            "protected": {"git_status_porcelain": ""}},
        "finding_disposition.json": {
            "findings": [
                {"finding_id": fid, "current_disposition": disp,
                 "evidence_refs": ["somewhere"], "planned_phase": "FP-02"}
                for fid, disp in zip(FINDING_IDS, VALID_DISPOSITIONS)]},
        "protocol_migration.json": {
            "rows": [{"old_rule": "o", "new_rule": "n", "reason": "r",
                      "affected_claims_or_tests": "t"}]},
        "registration.json": {
            "study_id": "forward_persistence_fp_v1", "guide_version": "FP-GUIDE-1.0",
            "primary": {"contrast": "C_FP_CONTEXT minus B_FP_PERSISTENCE"},
            "secondary": {"timing": "conditional FP-09"}, "arms": ["A_STOCK_CAL"],
            "registered_at_utc": "2026-09-22T00:00:00+00:00"},
        "resource_budget.json": {
            "fp01_wall_seconds_charged_to_shared_ledger": 0,
            "shared_ledger_untouched_proof": "re-read only"},
        "test_registry.json": {"test_node_ids": list(REQUIRED_TEST_NODES)},
        "phase_manifest.json": {"artifacts": []},
        "decay_reconciliation.json": {"schema": "regime_lab.fp_decay_boundary_reconciliation.v1"},
        "artifact_inventory.json": {"missing": []},
        "gate_receipt.json": {"schema": "regime_lab.fp_gate.v1", "technical_gate": "NOT_RUN"},
    }
    entries = []
    for name, doc in docs.items():
        (root / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        entries.append({"path": name,
                        "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()})
    docs["phase_manifest.json"]["artifacts"] = entries
    (root / "phase_manifest.json").write_text(
        json.dumps(docs["phase_manifest.json"], indent=2), encoding="utf-8")
    (root / "report.md").write_text("# FP-01\n", encoding="utf-8")
    (root / "handoff.md").write_text("# FP-01 handoff\n", encoding="utf-8")
    return docs


def _names_present() -> None:
    assert set(REQUIRED_ARTIFACTS) >= {
        "baseline_identity.json", "finding_disposition.json", "protocol_migration.json",
        "registration.json", "resource_budget.json", "test_registry.json",
        "phase_manifest.json", "gate_receipt.json", "report.md", "handoff.md"}
    assert len(REQUIRED_TEST_NODES) == 8 and len(FINDING_IDS) == 9
    assert set(ALLOWED_DISPOSITIONS) >= {"PRESENT", "FIXED_WITH_PROOF"}


def test_fp01_verifier_passes_on_a_valid_bundle(lab_tmp):
    _names_present()
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp01(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp01_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp01(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"], "an empty dir must report what is missing"


def test_fp01_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "registration.json").write_text('{"study_id": "forged"}', encoding="utf-8")
    verdict = verify_fp01(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL", "a post-manifest edit must not PASS"
    assert any("registration.json" in r
               for g in verdict["gates"].values() for r in g["reasons"])


def test_fp01_verifier_fails_on_zero_tests(lab_tmp):
    root = Path(str(lab_tmp)) / "zerotests"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml, tests=0, nodes=())
    _bundle(root)
    verdict = verify_fp01(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("no-tests-collected" in r or "required FP01 test" in r
               for g in verdict["gates"].values() for r in g["reasons"])


def test_fp01_verifier_fails_on_disposition_without_evidence(lab_tmp):
    root = Path(str(lab_tmp)) / "noevidence"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    docs["finding_disposition.json"]["findings"][0]["evidence_refs"] = []
    (root / "finding_disposition.json").write_text(
        json.dumps(docs["finding_disposition.json"], indent=2), encoding="utf-8")
    manifest = json.loads((root / "phase_manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["artifacts"]:
        if entry["path"] == "finding_disposition.json":
            entry["sha256"] = hashlib.sha256(
                (root / "finding_disposition.json").read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest, indent=2),
                                              encoding="utf-8")
    verdict = verify_fp01(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL", "a disposition without evidence must not PASS"

