"""RA-02 verifier red/green gates (RA-GUIDE-1.0 §6, §14.3).

The green bundle must PASS; every red case must FAIL with a named reason.
Uses lab_tmp because pytest's tmp_path is outside LAB_ROOT and refused by the
read guard.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.ra.verifier_ra02 import CASE_IDS, REQUIRED_ARTIFACTS, verify_ra02


def _xml(path: Path, *, tests=1, failures=0, skipped=0, node_ids=None) -> Path:
    suite = ET.Element("testsuite", {"tests": str(tests),
                                     "failures": str(failures), "errors": "0",
                                     "skipped": str(skipped)})
    for nid in (node_ids or ["test_ra02_bundle::test_dummy"]):
        cls, _, name = nid.partition("::")
        ET.SubElement(suite, "testcase", {"classname": cls or "t", "name": name or nid})
    ET.ElementTree(suite).write(path)
    return path


def _all_node_ids():
    return [f"test_ra02_bundle::test_{case.lower()}" for case in CASE_IDS]


def _bundle(root: Path, *, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    cases = [{"case_id": case_id, "passed": True,
              "test_node_ids": [f"test_ra02_bundle::test_{case_id.lower()}"]}
             for case_id in CASE_IDS]
    docs = {
        "cache_contract.json": {"schema": "regime_lab.ra02_cache_contract.v1",
                                "kinds": ["world", "targets", "search", "fit",
                                          "features", "deployment"],
                                "provenance_fields_excluded": ["lab_run_id",
                                                               "output_path",
                                                               "created_at"]},
        "dependency_manifest.json": {"closure": ["src/x.py"],
                                     "doc_only_change_is_not_a_miss": True},
        "cache_test_matrix.json": {"cases": cases},
        "actual_cross_run_reuse.json": {
            "first_computation": {"producer": "ra02-run-a", "engine_runs": 1,
                                  "engine_wall_seconds": 1.5,
                                  "payload_sha256": "a" * 64},
            "cross_run_reuse": {"producer": "ra02-run-b", "status": "HIT",
                                "new_engine_runs": 0, "payload_sha256": "a" * 64},
            "equivalence": {"method": "canonical-byte-equal", "passed": True},
            "provenance_excluded_from_key": ["lab_run_id", "output_path"],
            "causality_fields": ["physical_compute_at", "simulated_cutoff",
                                 "simulated_ready_at"]},
        "resume_parity.json": {"parity_passed": True, "naive_restart_differs": True,
                               "seed": 20260911, "trials": 6},
        "counters.json": {"requested_trials": 9, "unique_evaluations": 3,
                          "cache_hits": 2, "cache_misses": 3,
                          "new_engine_runs": 1, "visited_bars": 1440,
                          "unique_evaluation_requests": 5,
                          "cache_hit_bars_counted_as_executed": False,
                          "scope": "ra02 bundle probe"},
        "resource_envelope.json": {"phase_wall_cap_s": 3600,
                                   "phase_measured_wall_s": 12.5,
                                   "ledger_before": {"spent": 165457.9,
                                                     "attempts": 140,
                                                     "budget": 300000.0},
                                   "ledger_after": {"spent": 165457.9,
                                                    "attempts": 140,
                                                    "budget": 300000.0}},
        "phase_gate.json": {"schema": "regime_lab.ra_phase_gate.v1",
                            "phase_id": "RA-02", "guide_version": "RA-GUIDE-1.0",
                            "implementation_status": "COMPLETE",
                            "technical_gate": "PASS",
                            "owner_review": {"status": "PENDING",
                                             "decision_ref": None},
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
            entries.append({"relpath": name,
                            "sha256": hashlib.sha256(data).hexdigest()})
    (root / "phase_manifest.json").write_text(json.dumps({"artifacts": entries}))
    return root


def test_ra02_verifier_fails_on_missing_case(lab_tmp):
    def drop_case(docs):
        docs["cache_test_matrix.json"]["cases"] = [
            row for row in docs["cache_test_matrix.json"]["cases"]
            if row["case_id"] != "C07"]
    root = _bundle(lab_tmp / "missing-case", mutate=drop_case)
    xml = _xml(lab_tmp / "mc.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("C07" in r for r in verdict["gates"]["G02-SEM"]["reasons"])


def test_ra02_verifier_fails_on_case_absent_from_junit(lab_tmp):
    root = _bundle(lab_tmp / "notrun")
    xml = _xml(lab_tmp / "nr.xml", tests=len(CASE_IDS),
               node_ids=_all_node_ids()[:-1])  # C10 never ran
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("C10 test missing from the junit report" in r
               for r in verdict["gates"]["G02-SEM"]["reasons"])


def test_ra02_verifier_fails_on_fake_hit(lab_tmp):
    def fake_hit(docs):
        reuse = docs["actual_cross_run_reuse.json"]
        reuse["cross_run_reuse"]["new_engine_runs"] = 1
        reuse["cross_run_reuse"]["status"] = "MISS"
    root = _bundle(lab_tmp / "fake-hit", mutate=fake_hit)
    xml = _xml(lab_tmp / "fh.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("pure cache HIT" in r for r in verdict["gates"]["G02-SEM"]["reasons"])


def test_ra02_verifier_fails_on_counter_inconsistency(lab_tmp):
    def bad_counters(docs):
        docs["counters.json"]["cache_hits"] = 99  # hits+misses != unique
    root = _bundle(lab_tmp / "bad-count", mutate=bad_counters)
    xml = _xml(lab_tmp / "bc.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G02-COUNT"]["pass"]


def test_ra02_verifier_fails_on_ledger_reset(lab_tmp):
    def reset_ledger(docs):
        docs["resource_envelope.json"]["ledger_after"]["spent"] = 0.0
    root = _bundle(lab_tmp / "ledger", mutate=reset_ledger)
    xml = _xml(lab_tmp / "lg.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("ledger spent changed" in r
               for r in verdict["gates"]["G02-LEDGER"]["reasons"])

# --- PART2 ---
def test_ra02_verifier_passes_on_valid_bundle(lab_tmp):
    root = _bundle(lab_tmp / "green")
    xml = _xml(lab_tmp / "green.xml", tests=len(CASE_IDS),
               node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "PASS", verdict["gates"]
    assert set(verdict["gates"]) == {"G02-SEM", "G02-NUM", "G02-COUNT",
                                     "G02-LEDGER", "G02-MANIFEST"}


def test_ra02_verifier_fails_on_skipped_or_zero_tests(lab_tmp):
    root = _bundle(lab_tmp / "tests")
    xml_zero = _xml(lab_tmp / "zero.xml", tests=0, node_ids=[])
    verdict = verify_ra02(root, pytest_xml=xml_zero, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no-tests-collected" in r for r in verdict["gates"]["G02-SEM"]["reasons"])

    xml_skip = _xml(lab_tmp / "skip.xml", tests=len(CASE_IDS), skipped=1,
                    node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml_skip, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("skipped" in r for r in verdict["gates"]["G02-SEM"]["reasons"])


def test_ra02_verifier_fails_on_tampered_artifact(lab_tmp):
    root = _bundle(lab_tmp / "tamper")
    with open(root / "counters.json", "ab") as handle:
        handle.write(b" ")
    xml = _xml(lab_tmp / "tm.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("hash mismatch" in r for r in verdict["gates"]["G02-MANIFEST"]["reasons"])


def test_ra02_verifier_fails_on_protected_delta(lab_tmp):
    root = _bundle(lab_tmp / "protected")
    xml = _xml(lab_tmp / "pd.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml,
                          protected_status_after=" M ../quantbt/src/quantbt/endpoint.py")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G02-LEDGER"]["pass"]


def test_ra02_verifier_fails_on_blocked_riding_pass(lab_tmp):
    def blocked(docs):
        docs["resume_parity.json"]["status"] = "BLOCKED"
    root = _bundle(lab_tmp / "blocked", mutate=blocked)
    xml = _xml(lab_tmp / "bl.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("BLOCKED" in r for r in verdict["gates"]["G02-SEM"]["reasons"])


def test_ra02_verifier_fails_on_wrong_phase_receipt(lab_tmp):
    def wrong_phase(docs):
        docs["phase_gate.json"]["phase_id"] = "RA-03"
    root = _bundle(lab_tmp / "phase", mutate=wrong_phase)
    xml = _xml(lab_tmp / "ph.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("another phase" in r for r in verdict["gates"]["G02-LEDGER"]["reasons"])


def test_ra02_verifier_fails_on_owner_approval_claimed(lab_tmp):
    def approved(docs):
        docs["phase_gate.json"]["owner_review"] = {"status": "APPROVED",
                                                   "decision_ref": "claimed"}
    root = _bundle(lab_tmp / "approved", mutate=approved)
    xml = _xml(lab_tmp / "ap.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra02(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("owner review must stay PENDING" in r
               for r in verdict["gates"]["G02-LEDGER"]["reasons"])


def test_ra02_verifier_fails_on_empty_dir(lab_tmp):
    verdict = verify_ra02(lab_tmp / "empty", pytest_xml=None,
                          protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G02-SEM"]["pass"]
    assert not verdict["gates"]["G02-MANIFEST"]["pass"]
    assert not verdict["gates"]["G02-LEDGER"]["pass"]
