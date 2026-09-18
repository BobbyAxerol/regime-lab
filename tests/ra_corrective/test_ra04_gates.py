"""RA-04 verifier red/green gates (RA-GUIDE-1.0 section 8, section 14.3).

The green bundle must PASS; every red case must FAIL with a named reason.
Uses lab_tmp because pytest's tmp_path is outside LAB_ROOT and refused by the
read guard.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.ra.verifier_ra04 import CASE_IDS, REQUIRED_ARTIFACTS, verify_ra04


def _xml(path: Path, *, tests=1, failures=0, skipped=0, node_ids=None) -> Path:
    suite = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                     "errors": "0", "skipped": str(skipped)})
    for nid in (node_ids or ["test_ra04_bundle::test_dummy"]):
        cls, _, name = nid.partition("::")
        ET.SubElement(suite, "testcase", {"classname": cls or "t", "name": name or nid})
    ET.ElementTree(suite).write(path)
    return path


def _all_node_ids():
    return [f"test_ra04_bundle::test_{case.lower()}" for case in CASE_IDS]


def _bundle(root: Path, *, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    q_matrix = {case_id: {"test_node_ids": [f"test_ra04_bundle::test_{case_id.lower()}"], "passed": True}
               for case_id in CASE_IDS}
    docs = {
        "selector_semantics.json": {"pinned_selector": "is_only_robust"},
        "f04_reproduction.json": {"mechanism_confirmed": {"some_candidate_reduces_to_single_shared_datapoint": True}},
        "admission_policy.json": {"contract": "STOCK_MODE4_PLUS_ADMISSION_V1",
                                  "thresholds": {a: {"min_complete_train_days": 2, "min_finite_shards": 3}
                                                for a in ("A-SC", "A-HMA", "A-VWAP", "A-HASH")}},
        "search_registration.json": {"budget": {"optuna_trials": 32, "reused_not_refrozen": True}},
        "compact_controls.json": {"controls": [{"control": f"c{i}", "pass": True} for i in range(7)],
                                  "all_pass": True},
        "public_path.json": {"structural": {"all_pass": True}},
        "readiness.json": {
            "route_readiness": {a: {"status": "OK", "fills": 3} for a in ("A-SC", "A-HMA", "A-VWAP", "A-HASH")},
            "economics": {"fee": 0.0004}, "history_eligibility_checked": True,
            "q_matrix": q_matrix},
        "phase_gate.json": {"schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-04",
                            "guide_version": "RA-GUIDE-1.0", "implementation_status": "COMPLETE",
                            "technical_gate": "PASS",
                            "owner_review": {"status": "PENDING", "decision_ref": None},
                            "can_start_next_phase": False},
    }
    if mutate:
        mutate(docs)
    (root / "report.md").write_text("# report\n")
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


def test_ra04_verifier_passes_on_valid_bundle(lab_tmp):
    root = _bundle(lab_tmp / "green")
    xml = _xml(lab_tmp / "green.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "PASS", verdict["gates"]
    assert set(verdict["gates"]) == {"G04-VALID", "G04-READINESS", "G04-REG", "G04-MANIFEST"}


def test_ra04_verifier_fails_on_missing_case(lab_tmp):
    def drop_case(docs):
        del docs["readiness.json"]["q_matrix"]["Q05"]
    root = _bundle(lab_tmp / "missing-case", mutate=drop_case)
    xml = _xml(lab_tmp / "mc.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("Q05" in r for r in verdict["gates"]["G04-VALID"]["reasons"])


def test_ra04_verifier_fails_on_case_absent_from_junit(lab_tmp):
    root = _bundle(lab_tmp / "notrun")
    xml = _xml(lab_tmp / "nr.xml", tests=len(CASE_IDS), node_ids=_all_node_ids()[:-1])
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("missing from the junit report" in r for r in verdict["gates"]["G04-VALID"]["reasons"])


def test_ra04_verifier_fails_when_f04_mechanism_not_confirmed(lab_tmp):
    def no_mechanism(docs):
        docs["f04_reproduction.json"]["mechanism_confirmed"] = {}
    root = _bundle(lab_tmp / "nomech", mutate=no_mechanism)
    xml = _xml(lab_tmp / "nm.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("mechanism_confirmed" in r for r in verdict["gates"]["G04-VALID"]["reasons"])


def test_ra04_verifier_fails_when_a_control_is_missing(lab_tmp):
    def drop_control(docs):
        docs["compact_controls.json"]["controls"] = docs["compact_controls.json"]["controls"][:6]
    root = _bundle(lab_tmp / "dropcontrol", mutate=drop_control)
    xml = _xml(lab_tmp / "dc.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("expected 7 compact controls" in r for r in verdict["gates"]["G04-VALID"]["reasons"])


def test_ra04_verifier_fails_when_a_control_fails(lab_tmp):
    def fail_control(docs):
        docs["compact_controls.json"]["controls"][0]["pass"] = False
        docs["compact_controls.json"]["all_pass"] = False
    root = _bundle(lab_tmp / "failcontrol", mutate=fail_control)
    xml = _xml(lab_tmp / "fc.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("not every compact control passed" in r for r in verdict["gates"]["G04-VALID"]["reasons"])


def test_ra04_verifier_fails_when_route_status_missing(lab_tmp):
    def drop_route(docs):
        del docs["readiness.json"]["route_readiness"]["A-HASH"]
    root = _bundle(lab_tmp / "noroute", mutate=drop_route)
    xml = _xml(lab_tmp / "nr2.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("A-HASH" in r for r in verdict["gates"]["G04-READINESS"]["reasons"])


def test_ra04_verifier_fails_when_history_eligibility_not_checked(lab_tmp):
    def drop_history(docs):
        docs["readiness.json"]["history_eligibility_checked"] = False
    root = _bundle(lab_tmp / "nohist", mutate=drop_history)
    xml = _xml(lab_tmp / "nh.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("history" in r for r in verdict["gates"]["G04-READINESS"]["reasons"])


def test_ra04_verifier_fails_when_an_alpha_has_no_frozen_threshold(lab_tmp):
    def drop_threshold(docs):
        del docs["admission_policy.json"]["thresholds"]["A-VWAP"]
    root = _bundle(lab_tmp / "nothresh", mutate=drop_threshold)
    xml = _xml(lab_tmp / "nt.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("A-VWAP" in r for r in verdict["gates"]["G04-REG"]["reasons"])


def test_ra04_verifier_fails_on_protected_delta(lab_tmp):
    root = _bundle(lab_tmp / "protected")
    xml = _xml(lab_tmp / "pd.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml,
                          protected_status_after=" M ../quantbt/src/quantbt/endpoint.py")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G04-REG"]["pass"]


def test_ra04_verifier_fails_on_tampered_artifact(lab_tmp):
    root = _bundle(lab_tmp / "tamper")
    with open(root / "readiness.json", "ab") as handle:
        handle.write(b" ")
    xml = _xml(lab_tmp / "tm.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("hash mismatch" in r for r in verdict["gates"]["G04-MANIFEST"]["reasons"])


def test_ra04_verifier_fails_on_wrong_phase_receipt(lab_tmp):
    def wrong_phase(docs):
        docs["phase_gate.json"]["phase_id"] = "RA-05"
    root = _bundle(lab_tmp / "phase", mutate=wrong_phase)
    xml = _xml(lab_tmp / "ph.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("another phase" in r for r in verdict["gates"]["G04-REG"]["reasons"])


def test_ra04_verifier_fails_on_owner_approval_claimed(lab_tmp):
    def approved(docs):
        docs["phase_gate.json"]["owner_review"] = {"status": "APPROVED", "decision_ref": "claimed"}
    root = _bundle(lab_tmp / "approved", mutate=approved)
    xml = _xml(lab_tmp / "ap.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("owner review must stay PENDING" in r for r in verdict["gates"]["G04-REG"]["reasons"])


def test_ra04_verifier_fails_on_skipped_or_zero_tests(lab_tmp):
    root = _bundle(lab_tmp / "tests")
    xml_zero = _xml(lab_tmp / "zero.xml", tests=0, node_ids=[])
    verdict = verify_ra04(root, pytest_xml=xml_zero, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no-tests-collected" in r for r in verdict["gates"]["G04-VALID"]["reasons"])

    xml_skip = _xml(lab_tmp / "skip.xml", tests=len(CASE_IDS), skipped=1, node_ids=_all_node_ids())
    verdict = verify_ra04(root, pytest_xml=xml_skip, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("skipped" in r for r in verdict["gates"]["G04-VALID"]["reasons"])


def test_ra04_verifier_fails_on_empty_dir(lab_tmp):
    verdict = verify_ra04(lab_tmp / "empty", pytest_xml=None, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G04-VALID"]["pass"]
    assert not verdict["gates"]["G04-MANIFEST"]["pass"]
    assert not verdict["gates"]["G04-REG"]["pass"]
