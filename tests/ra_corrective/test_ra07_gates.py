"""RA-07 verifier red/green gates (RA-GUIDE-1.0 section 11, section 14.3).

The green bundle must PASS; every red case must FAIL with a named reason.
Uses lab_tmp because pytest's tmp_path is outside LAB_ROOT and refused by
the read guard.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.ra.verifier_ra07 import CASE_IDS, REQUIRED_ARTIFACTS, verify_ra07


def _xml(path: Path, *, tests=1, failures=0, skipped=0, node_ids=None) -> Path:
    suite = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                     "errors": "0", "skipped": str(skipped)})
    for nid in (node_ids or ["test_ra07_bundle::test_dummy"]):
        cls, _, name = nid.partition("::")
        ET.SubElement(suite, "testcase", {"classname": cls or "t", "name": name or nid})
    ET.ElementTree(suite).write(path)
    return path


def _all_node_ids():
    return [f"test_ra07_bundle::test_{case.lower()}" for case in CASE_IDS]


def _bundle(root: Path, *, mutate=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    coverage_rows = [{"cell": f"A-SC/{s}", "coverage_status": "RUN_VALID"}
                     for s in ("BTCUSDT", "ETHUSDT")]
    coverage_rows += [{"cell": f"A-SC/{s}", "coverage_status": "NOT_RUN_BUDGET"}
                      for s in ("SOLUSDT", "BNBUSDT", "DOGEUSDT")]
    coverage_rows += [{"cell": f"A-HMA/{s}", "coverage_status": "NOT_RUN_BUDGET"}
                      for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")]
    coverage_rows += [{"cell": f"A-VWAP/{s}", "coverage_status": "BLOCKED_CAPABILITY"}
                      for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")]
    coverage_rows += [{"cell": f"A-HASH/{s}", "coverage_status": "BLOCKED_CAPABILITY"}
                      for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")]
    docs = {
        "replication_spec.json": {"frozen_before_outcomes": True,
                                  "bootstrap_plan": {"block_length_days_primary": 28, "seed": 20260919}},
        "complete_coverage_matrix.json": {"rows": coverage_rows},
        "cell2_result.json": {"capability_status": "EXECUTED",
                              "arms": {"STATIC": {"ok": True}, "M4_CAL": {"ok": True},
                                      "M4_CAL_MATCHED": {"ok": True}, "M4_REGIME": {"ok": True}}},
        "paired_accounts.json": {"cell1_primary": [], "cell2_primary": []},
        "control_results.json": {
            "CALENDAR_BUDGET_MATCHED": {"status": "ALREADY_AVAILABLE"},
            "AGE_ONLY": {"status": "NOT_APPLICABLE", "reason": "RA-06 locked KEEP_BASELINE"},
            "DELAYED_INFORMATION": {"status": "OK"},
            "PLACEBO_TIMING": {"status": "OK", "fidelity": {"matched": True}},
            "RISK_EXPOSURE_ATTRIBUTION": {"status": "OK"},
        },
        "decay_table.json": {"rows": [
            {"comparison_kind": "D1_IS_TO_OOS", "validity_status": "OK", "metric_name": "mean_daily_return"},
            {"comparison_kind": "D2_PARAMETER_AGE", "validity_status": "OK", "metric_name": "segment_return"},
            {"comparison_kind": "D3_ADJACENT_OPERATIONAL_FOLDS", "validity_status": "OK",
             "metric_name": "mean_daily_return"},
        ]},
        "uncertainty_results.json": {
            "no_engine_calls": True,
            "bootstrap_plan_used": {"block_length_days_primary": 28, "seed": 20260919},
            "primary": {"claim": {"status": "INCONCLUSIVE_SUPPORT"}},
            "secondary": {"x": {"claim": {"status": "INCONCLUSIVE_SUPPORT"}}},
        },
        "multiplicity_ledger.json": {
            "primary_unadjusted": {"adjustment": "NONE (single pre-registered primary hypothesis, guide 13.4)"},
        },
        "bootstrap_self_check.json": {"pass": True, "uses_only_synthetic_data": True},
        "support_report.json": {"per_contrast": {}},
        "sensitivity_report.json": {"leave_one_period_out_cell1_primary": {}},
        "cost_risk_attribution.json": {"cell1": {}, "cell2": {}},
        "phase_gate.json": {"schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-07",
                            "guide_version": "RA-GUIDE-1.0", "implementation_status": "COMPLETE",
                            "technical_gate": "PASS",
                            "owner_review": {"status": "PENDING", "decision_ref": None},
                            "can_start_next_phase": False},
    }
    if mutate:
        mutate(docs)
    (root / "report.md").write_text("# RA-07 report\n\nconclusion_level: INCONCLUSIVE_SUPPORT\n")
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


def test_ra07_verifier_passes_on_valid_bundle(lab_tmp):
    root = _bundle(lab_tmp / "green")
    xml = _xml(lab_tmp / "green.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "PASS", verdict["gates"]
    assert set(verdict["gates"]) == {"G07-VALID", "G07-CONTROL", "G07-STATS", "G07-DECAY",
                                     "G07-CLAIM", "G07-MANIFEST"}


def test_ra07_verifier_fails_on_missing_artifact(lab_tmp):
    root = _bundle(lab_tmp / "missing")
    (root / "decay_table.json").unlink()
    xml = _xml(lab_tmp / "missing.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("missing artifacts" in r for r in verdict["gates"]["G07-VALID"]["reasons"])


def test_ra07_verifier_fails_when_coverage_matrix_is_short(lab_tmp):
    def truncate(docs):
        docs["complete_coverage_matrix.json"]["rows"] = docs["complete_coverage_matrix.json"]["rows"][:5]

    root = _bundle(lab_tmp / "short", mutate=truncate)
    xml = _xml(lab_tmp / "short.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("expected 20" in r for r in verdict["gates"]["G07-VALID"]["reasons"])


def test_ra07_verifier_fails_when_fewer_than_2_cells_run(lab_tmp):
    def one_cell(docs):
        rows = docs["complete_coverage_matrix.json"]["rows"]
        for row in rows:
            if row["coverage_status"] == "RUN_VALID" and row["cell"] == "A-SC/ETHUSDT":
                row["coverage_status"] = "NOT_RUN_BUDGET"

    root = _bundle(lab_tmp / "onecell", mutate=one_cell)
    xml = _xml(lab_tmp / "onecell.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("fewer than 2 RUN_VALID" in r for r in verdict["gates"]["G07-VALID"]["reasons"])


def test_ra07_verifier_fails_when_cell2_executed_but_arm_missing(lab_tmp):
    def drop_arm(docs):
        del docs["cell2_result.json"]["arms"]["M4_REGIME"]

    root = _bundle(lab_tmp / "droparm", mutate=drop_arm)
    xml = _xml(lab_tmp / "droparm.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("silent drop" in r for r in verdict["gates"]["G07-VALID"]["reasons"])


def test_ra07_verifier_fails_when_age_only_not_applicable_has_no_reason(lab_tmp):
    def no_reason(docs):
        docs["control_results.json"]["AGE_ONLY"] = {"status": "NOT_APPLICABLE"}

    root = _bundle(lab_tmp / "noreason", mutate=no_reason)
    xml = _xml(lab_tmp / "noreason.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("NOT_APPLICABLE" in r for r in verdict["gates"]["G07-CONTROL"]["reasons"])


def test_ra07_verifier_fails_when_placebo_ok_but_no_fidelity(lab_tmp):
    def no_fidelity(docs):
        docs["control_results.json"]["PLACEBO_TIMING"] = {"status": "OK"}

    root = _bundle(lab_tmp / "nofid", mutate=no_fidelity)
    xml = _xml(lab_tmp / "nofid.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no fidelity check" in r for r in verdict["gates"]["G07-CONTROL"]["reasons"])


def test_ra07_verifier_fails_when_bootstrap_used_a_different_seed_than_frozen(lab_tmp):
    def drift(docs):
        docs["uncertainty_results.json"]["bootstrap_plan_used"]["seed"] = 999

    root = _bundle(lab_tmp / "seeddrift", mutate=drift)
    xml = _xml(lab_tmp / "seeddrift.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("seed used does not match" in r for r in verdict["gates"]["G07-STATS"]["reasons"])


def test_ra07_verifier_fails_when_numeric_reference_check_did_not_pass(lab_tmp):
    def broken_check(docs):
        docs["bootstrap_self_check.json"]["pass"] = False

    root = _bundle(lab_tmp / "brokencheck", mutate=broken_check)
    xml = _xml(lab_tmp / "brokencheck.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("did not pass" in r for r in verdict["gates"]["G07-STATS"]["reasons"])


def test_ra07_verifier_fails_when_primary_hypothesis_gets_multiplicity_adjusted(lab_tmp):
    def adjust_primary(docs):
        docs["multiplicity_ledger.json"]["primary_unadjusted"]["adjustment"] = "HOLM"

    root = _bundle(lab_tmp / "adjprimary", mutate=adjust_primary)
    xml = _xml(lab_tmp / "adjprimary.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("must stay unadjusted" in r for r in verdict["gates"]["G07-STATS"]["reasons"])


def test_ra07_verifier_fails_when_a_decay_kind_is_missing(lab_tmp):
    def drop_d2(docs):
        docs["decay_table.json"]["rows"] = [r for r in docs["decay_table.json"]["rows"]
                                            if r["comparison_kind"] != "D2_PARAMETER_AGE"]

    root = _bundle(lab_tmp / "missingd2", mutate=drop_d2)
    xml = _xml(lab_tmp / "missingd2.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("D2_PARAMETER_AGE" in r for r in verdict["gates"]["G07-DECAY"]["reasons"])


def test_ra07_verifier_fails_when_a_decay_row_averages_fold_sharpe(lab_tmp):
    def bad_metric(docs):
        docs["decay_table.json"]["rows"][0]["metric_name"] = "average_fold_sharpe"

    root = _bundle(lab_tmp / "avgsharpe", mutate=bad_metric)
    xml = _xml(lab_tmp / "avgsharpe.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("forbids" in r for r in verdict["gates"]["G07-DECAY"]["reasons"])


def test_ra07_verifier_fails_when_claim_status_outside_registered_vocabulary(lab_tmp):
    def bad_claim(docs):
        docs["uncertainty_results.json"]["primary"]["claim"]["status"] = "STRONG_EDGE"

    root = _bundle(lab_tmp / "badclaim", mutate=bad_claim)
    xml = _xml(lab_tmp / "badclaim.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("not in registered vocabulary" in r for r in verdict["gates"]["G07-CLAIM"]["reasons"])


def test_ra07_verifier_fails_when_report_has_no_conclusion_level(lab_tmp):
    root = _bundle(lab_tmp / "noconclusion")
    (root / "report.md").write_text("# RA-07 report\n\nno conclusion stated\n")
    xml = _xml(lab_tmp / "noconclusion.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("conclusion_level" in r for r in verdict["gates"]["G07-CLAIM"]["reasons"])


def test_ra07_verifier_fails_on_hash_mismatch(lab_tmp):
    root = _bundle(lab_tmp / "tamper")
    manifest = json.loads((root / "phase_manifest.json").read_text())
    for entry in manifest["artifacts"]:
        if entry["relpath"] == "decay_table.json":
            entry["sha256"] = "0" * 64
    (root / "phase_manifest.json").write_text(json.dumps(manifest))
    xml = _xml(lab_tmp / "tamper.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("hash mismatch" in r for r in verdict["gates"]["G07-MANIFEST"]["reasons"])


def test_ra07_verifier_fails_on_test_failures(lab_tmp):
    root = _bundle(lab_tmp / "redtests")
    xml = _xml(lab_tmp / "redtests.xml", tests=len(CASE_IDS), failures=1, node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("failures" in r for r in verdict["gates"]["G07-VALID"]["reasons"])


def test_ra07_verifier_fails_when_owner_review_is_not_pending(lab_tmp):
    def approve(docs):
        docs["phase_gate.json"]["owner_review"] = {"status": "APPROVED", "decision_ref": "x"}

    root = _bundle(lab_tmp / "approved", mutate=approve)
    xml = _xml(lab_tmp / "approved.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("PENDING" in r for r in verdict["gates"]["G07-CLAIM"]["reasons"])


def test_ra07_verifier_fails_when_protected_tree_changed(lab_tmp):
    root = _bundle(lab_tmp / "dirty")
    xml = _xml(lab_tmp / "dirty.xml", tests=len(CASE_IDS), node_ids=_all_node_ids())
    verdict = verify_ra07(root, pytest_xml=xml, protected_status_after=" M some_file.py\n")
    assert verdict["overall"] == "FAIL"
    assert any("protected tree changed" in r for r in verdict["gates"]["G07-CLAIM"]["reasons"])
