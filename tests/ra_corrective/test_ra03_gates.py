"""RA-03 verifier red/green gates (RA-GUIDE-1.0 section 7, section 14.3).

The green bundle must PASS; every red case must FAIL with a named reason.
Uses lab_tmp because pytest's tmp_path is outside LAB_ROOT and refused by the
read guard.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.ra.verifier_ra03 import CASE_IDS, REQUIRED_ARTIFACTS, verify_ra03


def _xml(path: Path, *, tests=1, failures=0, skipped=0, node_ids=None) -> Path:
    suite = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                     "errors": "0", "skipped": str(skipped)})
    for nid in (node_ids or ["test_ra03_bundle::test_dummy"]):
        cls, _, name = nid.partition("::")
        ET.SubElement(suite, "testcase", {"classname": cls or "t", "name": name or nid})
    ET.ElementTree(suite).write(path)
    return path


def _all_node_ids():
    return [f"test_ra03_bundle::test_{case.lower()}" for case in CASE_IDS]


def _route_row(alpha, *, status="OK", fills=3):
    return {"alpha_id": alpha, "status": status, "fills": fills if status == "OK" else None,
           "exit_tags": ["entry", "exit"] if fills else [],
           "what_this_proves": "probe"}


def _bundle(root: Path, *, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    docs = {
        "route_matrix.json": {
            "schema": "regime_lab.ra03_route_matrix.v1",
            "rows": [_route_row(a) for a in ("A-SC", "A-HMA", "A-VWAP", "A-HASH")],
            "primary_pilot": "A-SC", "primary_pilot_qualified": True,
            "qualified_alphas": ["A-SC", "A-HMA", "A-VWAP", "A-HASH"]},
        "retention_contract.json": {"tiers": ["TRIAL_SCALAR", "CANDIDATE_COMPACT", "SELECTED_AUDIT"]},
        "memory_profile.json": {
            "registered_per_process_rss_cap_gib": 3.0, "target_headroom_fraction": 0.8,
            "profiles": [
                {"scope": "representative_train_candidate", "alpha_id": "A-SC",
                 "peak_rss_gib_max": 0.3, "registered_per_process_rss_cap_gib": 3.0,
                 "extrapolated": False},
                {"scope": "deployment_scope", "alpha_id": "A-SC",
                 "peak_rss_gib_max": 0.35, "registered_per_process_rss_cap_gib": 3.0,
                 "extrapolated": False},
            ]},
        "parity_report.json": {
            "cases_covered": list(CASE_IDS),
            "required_test_node_ids": _all_node_ids(),
            "primary_semantics_changed_for_speed": False},
        "work_profile.json": {"stages": []},
        "capacity_forecast.json": {
            "measured_cost_per_task_seconds": 2.5, "unmeasured_speedup_commitment": False,
            "admission_probe": {"over_envelope_status": "BLOCKED_BUDGET",
                                "in_envelope_status": "ADMIT"}},
        "resource_receipts.json": {
            "ledger_before": {"spent": 193557.8, "attempts": 140, "budget": 300000.0},
            "ledger_after": {"spent": 193557.8, "attempts": 140, "budget": 300000.0}},
        "phase_gate.json": {"schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-03",
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


def test_ra03_verifier_passes_on_valid_bundle(lab_tmp):
    root = _bundle(lab_tmp / "green")
    xml = _xml(lab_tmp / "green.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "PASS", verdict["gates"]
    assert set(verdict["gates"]) == {"G03-PARITY", "G03-MEM", "G03-ROUTE", "G03-COST",
                                     "G03-LEDGER", "G03-MANIFEST"}


def test_ra03_verifier_fails_on_missing_case(lab_tmp):
    def drop_case(docs):
        docs["parity_report.json"]["cases_covered"] = [c for c in CASE_IDS if c != "M06"]
    root = _bundle(lab_tmp / "missing-case", mutate=drop_case)
    xml = _xml(lab_tmp / "mc.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("M06" in r for r in verdict["gates"]["G03-PARITY"]["reasons"])


def test_ra03_verifier_fails_on_case_absent_from_junit(lab_tmp):
    root = _bundle(lab_tmp / "notrun")
    xml = _xml(lab_tmp / "nr.xml", tests=len(CASE_IDS), node_ids=_all_node_ids()[:-1])
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("required test not found in junit" in r for r in verdict["gates"]["G03-PARITY"]["reasons"])


def test_ra03_verifier_fails_on_semantics_changed_for_speed(lab_tmp):
    def changed(docs):
        docs["parity_report.json"]["primary_semantics_changed_for_speed"] = True
    root = _bundle(lab_tmp / "changed", mutate=changed)
    xml = _xml(lab_tmp / "ch.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G03-PARITY"]["pass"]


def test_ra03_verifier_fails_when_a_profile_exceeds_its_cap_without_extrapolation_flag(lab_tmp):
    def over_cap(docs):
        docs["memory_profile.json"]["profiles"][0]["peak_rss_gib_max"] = 99.0
    root = _bundle(lab_tmp / "overcap", mutate=over_cap)
    xml = _xml(lab_tmp / "oc.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("exceeded the registered per-process cap" in r for r in verdict["gates"]["G03-MEM"]["reasons"])


def test_ra03_verifier_fails_when_deployment_scope_profile_is_missing(lab_tmp):
    def drop_deploy(docs):
        docs["memory_profile.json"]["profiles"] = [docs["memory_profile.json"]["profiles"][0]]
    root = _bundle(lab_tmp / "nodeploy", mutate=drop_deploy)
    xml = _xml(lab_tmp / "nd.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("deployment-scope" in r for r in verdict["gates"]["G03-MEM"]["reasons"])


def test_ra03_verifier_fails_on_fabricated_zero_fill_status(lab_tmp):
    def fabricate(docs):
        rows = docs["route_matrix.json"]["rows"]
        rows[0] = {"alpha_id": "A-SC", "status": "OK", "fills": None, "exit_tags": []}
    root = _bundle(lab_tmp / "fabricate", mutate=fabricate)
    xml = _xml(lab_tmp / "fb.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("fabricated 0" in r for r in verdict["gates"]["G03-ROUTE"]["reasons"])


def test_ra03_verifier_fails_when_pilot_not_qualified(lab_tmp):
    def unqualify(docs):
        docs["route_matrix.json"]["primary_pilot_qualified"] = False
    root = _bundle(lab_tmp / "unqualified", mutate=unqualify)
    xml = _xml(lab_tmp / "uq.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("primary pilot" in r for r in verdict["gates"]["G03-ROUTE"]["reasons"])


def test_ra03_verifier_fails_when_admission_does_not_block_over_envelope(lab_tmp):
    def no_block(docs):
        docs["capacity_forecast.json"]["admission_probe"]["over_envelope_status"] = "ADMIT"
    root = _bundle(lab_tmp / "noblock", mutate=no_block)
    xml = _xml(lab_tmp / "nb.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("not refused" in r for r in verdict["gates"]["G03-COST"]["reasons"])


def test_ra03_verifier_fails_on_unmeasured_speedup_commitment(lab_tmp):
    def commit(docs):
        docs["capacity_forecast.json"]["unmeasured_speedup_commitment"] = True
    root = _bundle(lab_tmp / "speedup", mutate=commit)
    xml = _xml(lab_tmp / "sp.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("unmeasured speedup" in r for r in verdict["gates"]["G03-COST"]["reasons"])


def test_ra03_verifier_fails_on_ledger_reset(lab_tmp):
    def reset_ledger(docs):
        docs["resource_receipts.json"]["ledger_after"]["spent"] = 0.0
    root = _bundle(lab_tmp / "ledger", mutate=reset_ledger)
    xml = _xml(lab_tmp / "lg.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("ledger spent changed" in r for r in verdict["gates"]["G03-LEDGER"]["reasons"])


def test_ra03_verifier_fails_on_protected_delta(lab_tmp):
    root = _bundle(lab_tmp / "protected")
    xml = _xml(lab_tmp / "pd.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml,
                          protected_status_after=" M ../quantbt/src/quantbt/endpoint.py")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G03-LEDGER"]["pass"]


def test_ra03_verifier_fails_on_tampered_artifact(lab_tmp):
    root = _bundle(lab_tmp / "tamper")
    with open(root / "route_matrix.json", "ab") as handle:
        handle.write(b" ")
    xml = _xml(lab_tmp / "tm.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("hash mismatch" in r for r in verdict["gates"]["G03-MANIFEST"]["reasons"])


def test_ra03_verifier_fails_on_wrong_phase_receipt(lab_tmp):
    def wrong_phase(docs):
        docs["phase_gate.json"]["phase_id"] = "RA-04"
    root = _bundle(lab_tmp / "phase", mutate=wrong_phase)
    xml = _xml(lab_tmp / "ph.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("another phase" in r for r in verdict["gates"]["G03-LEDGER"]["reasons"])


def test_ra03_verifier_fails_on_owner_approval_claimed(lab_tmp):
    def approved(docs):
        docs["phase_gate.json"]["owner_review"] = {"status": "APPROVED", "decision_ref": "claimed"}
    root = _bundle(lab_tmp / "approved", mutate=approved)
    xml = _xml(lab_tmp / "ap.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("owner review must stay PENDING" in r for r in verdict["gates"]["G03-LEDGER"]["reasons"])


def test_ra03_verifier_fails_on_skipped_or_zero_tests(lab_tmp):
    root = _bundle(lab_tmp / "tests")
    xml_zero = _xml(lab_tmp / "zero.xml", tests=0, node_ids=[])
    verdict = verify_ra03(root, pytest_xml=xml_zero, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no-tests-collected" in r for r in verdict["gates"]["G03-PARITY"]["reasons"])

    xml_skip = _xml(lab_tmp / "skip.xml", tests=len(CASE_IDS), skipped=1, node_ids=_all_node_ids())
    verdict = verify_ra03(root, pytest_xml=xml_skip, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("skipped" in r for r in verdict["gates"]["G03-PARITY"]["reasons"])


def test_ra03_verifier_fails_on_empty_dir(lab_tmp):
    verdict = verify_ra03(lab_tmp / "empty", pytest_xml=None, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G03-PARITY"]["pass"]
    assert not verdict["gates"]["G03-MANIFEST"]["pass"]
    assert not verdict["gates"]["G03-LEDGER"]["pass"]
