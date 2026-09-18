"""RA-01 gate tests (RA-GUIDE-1.0 §5, gates G01-*).

Every test here runs for real: red cases must FAIL verification with a named
reason, the green case must PASS. Uses the lab_tmp fixture (inside LAB_ROOT)
because pytest's tmp_path is outside the lab and refused by the read guard.
"""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.ra.admission import admit_job
from crypto_regime_lab.ra.reconcile import reconcile_running_rows
from crypto_regime_lab.ra.verifier import FINDINGS, verify_ra01

CAPS = {"per_task_wall_s": 27000.0, "per_process_rss_gb": 3.0,
        "max_workers": 1, "max_retry": 1}
BUDGET = {"total_wall_s": 300000.0, "charged_wall_s": 165458.0}


def _req(wall=60.0, rss=1.0, workers=1, retries=0):
    return {"requested_wall_s": wall, "requested_rss_gb": rss,
            "workers": workers, "retries_used": retries}


# -- admission ---------------------------------------------------------------

def test_admit_accepts_small_job_within_envelope():
    verdict = admit_job(_req(), BUDGET, CAPS)
    assert verdict["status"] == "ADMIT"
    assert verdict["remaining_wall_s"] == BUDGET["total_wall_s"] - BUDGET["charged_wall_s"]


def test_admit_refuses_over_envelope_as_blocked_budget():
    verdict = admit_job(_req(wall=200000.0), BUDGET, CAPS)
    assert verdict["status"] == "BLOCKED_BUDGET"
    assert any("remaining" in r for r in verdict["reasons"])


def test_admit_refuses_over_task_cap():
    verdict = admit_job(_req(wall=27001.0), BUDGET, CAPS)
    assert verdict["status"] == "BLOCKED"
    assert any("per_task_wall_s" in r for r in verdict["reasons"])


def test_admit_refuses_excess_workers():
    verdict = admit_job(_req(workers=2), BUDGET, CAPS)
    assert verdict["status"] == "BLOCKED"
    assert any("max_workers" in r for r in verdict["reasons"])


def test_admit_new_run_id_does_not_reset_charge():
    # Same ledger charge seen under a different run id: remaining is unchanged,
    # so the same over-envelope request is still refused.
    verdict = admit_job(_req(wall=200000.0), dict(BUDGET), CAPS)
    assert verdict["status"] == "BLOCKED_BUDGET"
    assert verdict["remaining_wall_s"] == pytest_remaining()


def pytest_remaining():
    return BUDGET["total_wall_s"] - BUDGET["charged_wall_s"]


# -- bundle helper ------------------------------------------------------------

def _write_bundle(root: Path, *, node_ids=None, blocked_artifact=False) -> Path:
    (root).mkdir(parents=True, exist_ok=True)
    head = "a" * 40
    (root / "baseline_identity.json").write_text(json.dumps({
        "git_branch": "mode4-corrective", "git_head_full": head,
        "engine": {"quantbt_engine_version": "1.1.1",
                   "quantbt_native_version": "0.4.2",
                   "endpoint_sha256_installed": "x",
                   "endpoint_path_installed": "/nonexistent",
                   "endpoint_sha256_protected_source": "y"},
    }))
    (root / "finding_disposition.json").write_text(json.dumps({
        "findings": [{"finding_id": fid, "current_disposition": "PRESENT",
                      "evidence_refs": ["ref"], "planned_phase": "RA-0X"}
                     for fid in FINDINGS],
    }))
    rows = [{"old_gate": f"old-{i}", "new_disposition": f"new-{i}",
             "required_test": f"T{i}"} for i in range(6)]
    (root / "protocol_migration.json").write_text(json.dumps({"rows": rows}))
    (root / "registration.json").write_text(json.dumps({
        "namespace": "regime_time_edge_ra_v1",
        "approvals": {"scope": "PENDING", "migration": "PENDING"},
    }))
    budget_doc = {"total_wall_s": 300000.0, "charged_wall_s": 165458.0,
                  "remaining_wall_s": 134542.0, "frozen_caps": CAPS}
    if blocked_artifact:
        budget_doc["status"] = "BLOCKED"
    (root / "resource_budget.json").write_text(json.dumps(budget_doc))
    (root / "test_registry.json").write_text(json.dumps(
        {"test_node_ids": node_ids or []}))
    (root / "report.md").write_text("# report\n")
    (root / "handoff.md").write_text("# handoff\n")
    manifest_entries = []
    for name in ("baseline_identity.json", "finding_disposition.json",
                 "protocol_migration.json", "registration.json",
                 "resource_budget.json", "test_registry.json"):
        data = (root / name).read_bytes()
        manifest_entries.append({"relpath": name,
                                 "sha256": hashlib.sha256(data).hexdigest()})
    (root / "phase_manifest.json").write_text(json.dumps(
        {"artifacts": manifest_entries}))
    return root


def _write_xml(path: Path, *, tests=1, failures=0, node_ids=None) -> Path:
    suite = ET.Element("testsuite", {"tests": str(tests),
                                     "failures": str(failures), "errors": "0"})
    for nid in (node_ids or ["test_ra01_bundle::test_dummy"]):
        cls, _, name = nid.partition("::")
        ET.SubElement(suite, "testcase", {"classname": cls or "t", "name": name or nid})
    ET.ElementTree(suite).write(path)
    return path


# -- verifier red/green -------------------------------------------------------

def test_verifier_fails_on_empty_dir(lab_tmp):
    verdict = verify_ra01(lab_tmp / "empty", pytest_xml=None, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G01-VERIFY"]["pass"]


def test_verifier_fails_on_tampered_artifact(lab_tmp):
    root = _write_bundle(lab_tmp / "b")
    with open(root / "registration.json", "ab") as handle:
        handle.write(b" ")
    xml = _write_xml(lab_tmp / "r.xml")
    verdict = verify_ra01(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("hash mismatch" in r for r in verdict["gates"]["G01-VERIFY"]["reasons"])


def test_verifier_fails_on_zero_tests(lab_tmp):
    root = _write_bundle(lab_tmp / "b")
    xml = _write_xml(lab_tmp / "r.xml", tests=0, node_ids=[])
    verdict = verify_ra01(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"
    assert any("no-tests-collected" in r for r in verdict["gates"]["G01-VERIFY"]["reasons"])


def test_verifier_fails_on_blocked_status_riding_pass(lab_tmp):
    root = _write_bundle(lab_tmp / "b", blocked_artifact=True)
    xml = _write_xml(lab_tmp / "r.xml")
    verdict = verify_ra01(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "FAIL"


def test_verifier_fails_on_protected_delta(lab_tmp):
    root = _write_bundle(lab_tmp / "b")
    xml = _write_xml(lab_tmp / "r.xml")
    verdict = verify_ra01(root, pytest_xml=xml,
                          protected_status_after=" M ../quantbt/src/quantbt/endpoint.py")
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["G01-ID"]["pass"]


def test_verifier_passes_on_valid_bundle(lab_tmp):
    node_ids = ["test_ra01_bundle::test_dummy"]
    root = _write_bundle(lab_tmp / "b", node_ids=node_ids)
    xml = _write_xml(lab_tmp / "r.xml", node_ids=node_ids)
    verdict = verify_ra01(root, pytest_xml=xml, protected_status_after="")
    assert verdict["overall"] == "PASS", verdict["gates"]
    assert set(verdict["gates"]) == {"G01-ID", "G01-MIG", "G01-VERIFY",
                                     "G01-BUDGET", "G01-REPORT"}


# -- regression: the 08:33 FAIL run (G01-ID empty-HEAD) ----------------------

def test_verifier_reads_nested_baseline_identity(lab_tmp):
    """A real RA-01 run nests live inventory under 'inventory'; the verifier
    must read that shape. The 08:33Z run failed G01-ID with
    "git HEAD not a full 40-hex sha: ''" purely because of this nesting."""
    root = _write_bundle(lab_tmp / "nested")
    identity = json.loads((root / "baseline_identity.json").read_text())
    nested = {"inventory": identity}
    (root / "baseline_identity.json").write_text(json.dumps(nested))
    entries = []
    for name in ("baseline_identity.json", "finding_disposition.json",
                 "protocol_migration.json", "registration.json",
                 "resource_budget.json", "test_registry.json"):
        data = (root / name).read_bytes()
        entries.append({"relpath": name,
                        "sha256": hashlib.sha256(data).hexdigest()})
    (root / "phase_manifest.json").write_text(json.dumps(
        {"artifacts": entries}))
    xml = _write_xml(lab_tmp / "nested.xml")
    verdict = verify_ra01(root, pytest_xml=xml, protected_status_after="")
    assert verdict["gates"]["G01-ID"]["pass"] == True, verdict["gates"]["G01-ID"]  # noqa: E712


# -- reconcile: live worker vs orphan RUNNING row (RA01.1) --------------------

def test_reconcile_matches_live_worker_by_start_window():
    rows = [{"id": "a" * 32, "task": "task-key", "started":
             "2026-09-18T04:33:17.341513+00:00"}]
    processes = [{"pid": "2899361", "started": "Fri Sep 18 04:33:18 2026",
                  "cmd": "python run_time_edge.py _worker --request "
                         "/x/attempts/37b36330d7c945f2a0cad9630f903b33/request.json"}]
    out = reconcile_running_rows(rows, processes)
    assert out["summary"] == {"running_rows": 1, "live_matched": 1, "orphans": 0}
    assert out["rows"][0]["classification"] == "LIVE_MATCHED_BY_START_WINDOW"
    assert out["rows"][0]["evidence"]["pids"] == ["2899361"]


def test_reconcile_flags_orphan_running_row():
    rows = [{"id": "b" * 32, "task": "task-key",
             "started": "2026-09-18T04:33:17.341513+00:00"}]
    processes = [{"pid": "999", "started": "Fri Sep 18 03:00:00 2026",
                  "cmd": "python run_time_edge.py _worker --request "
                         "/x/attempts/37b36330d7c945f2a0cad9630f903b33/request.json"}]
    out = reconcile_running_rows(rows, processes)
    assert out["summary"]["orphans"] == 1
    row = out["rows"][0]
    assert row["classification"] == "ORPHAN_NO_LIVE_PROCESS"
    assert "recover_interrupted" in row["action"]
