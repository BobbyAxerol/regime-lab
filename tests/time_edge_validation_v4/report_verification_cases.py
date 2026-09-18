"""Explicit checks for a committed TE-01 report; never trigger an audit or engine."""
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def report():
    run_id = os.environ["TE01_REPORT_RUN_ID"]
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id)
    folder = ROOT / "evidence/time_edge_validation_v4/TE-01" / run_id
    return folder, (folder / "report.md").read_text(), json.loads((folder / "report.json").read_text())


def read(folder, name):
    return json.loads((folder / name).read_text())


def test_report_measured_numbers_match_independent_artifact_fields(report):
    folder, md, _ = report
    ct, br, snap, v = (read(folder, name + ".json") for name in
                      ("contract_tests", "regression_baseline", "snapshot_verification", "phase_verdict"))
    assert f"| Contract tests PASS / FAIL / SKIP | {ct['counts'].get('PASS',0)} / {ct['counts'].get('FAIL',0)} / {ct['counts'].get('SKIP',0)} |" in md
    assert f"| Before-repair PASS / FAIL / unexpected errors | {br['counts'].get('PASS',0)} / {br['counts'].get('FAIL',0)} / {len(v['baseline_unexpected_errors'])} |" in md
    assert f"| Snapshot files / bytes đã đối chiếu hash và metadata | {snap['files_verified']} / {snap['bytes_verified']} |" in md
    for key in ("wall_seconds", "cpu_seconds"):
        assert f"{v['runtime'][key]:.3f}" in md
    assert str(v["runtime"]["peak_rss_kib"]) in md
    assert str(len(read(folder, "finding_disposition.json")["findings"])) in md
    for case in br["cases"]:
        assert f"| {case['name']} | {case['status']} |" in md


def test_every_report_input_and_audit_manifest_hash_matches(report):
    folder, _, payload = report
    assert hashlib.sha256((folder / "report.md").read_bytes()).hexdigest() == payload["report_md_sha256"]
    for name, expected in payload["inputs"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    entries = read(folder, "artifact_manifest.json")["artifacts"]
    assert entries and len({e["path"] for e in entries}) == len(entries)
    for entry in entries:
        data = (folder / entry["path"]).read_bytes()
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_all_findings_acceptance_ids_and_cell_arms_remain_visible(report):
    folder, md, _ = report
    finding_ids = {r["id"] for r in read(folder, "finding_disposition.json")["findings"]}
    assert finding_ids == ({f"A{i:02d}" for i in range(1,17)} | {f"D{i:02d}" for i in range(1,9)} |
                           {f"N{i:02d}" for i in range(1,6)} | {f"TEF-{i:02d}" for i in range(1,21)})
    assert {r["id"] for r in read(folder, "acceptance_coverage.json")["cases"]} == {f"T{i:02d}" for i in range(1,65)}
    cells = read(folder, "reuse_decision.json")["cells"]
    assert len(cells) == len({c["cell"] for c in cells}) == 20
    for cell in cells:
        assert set(cell["arms"]) == {"M4_CAL", "M4_REGIME", "M4_CAL_MATCHED"}
        assert cell["metrics"] is None and cell["reason"]
        assert cell["cell"] in md


def test_links_and_technical_definitions_are_present(report):
    folder, md, _ = report
    links = re.findall(r"\]\(([^)]+)\)", md)
    assert links
    for link in links:
        if "://" not in link and not link.startswith("#"):
            assert (folder / unquote(link.split("#")[0])).resolve().is_file(), link
    for term in ("Registration", "WFO/Mode 4", "IS/OOS", "Regime/JM", "D1/D2/D3", "PF", "Sharpe",
                 "CI", "δ", "Holm/Bonferroni", "Bootstrap block", "Purge", "Runtime parity"):
        assert f"**{term}:**" in md


def test_no_market_or_full_phase_claim_is_created_by_registration(report):
    folder, md, payload = report
    v = payload["verdict"]
    assert v["technical_registration_validated"] is True
    assert v["runtime_ready"] is False and v["full_phase_complete"] is False
    assert v["new_findings_closed"] == 0
    assert all(v["runtime"][k] == 0 for k in ("engine_runs", "optimizer_runs", "market_statistical_tests"))
    assert read(folder, "fup02_intake.json")["final_handoff_verified"] is False
    assert "TECHNICAL_ONLY; economic NOT_EVALUABLE; runtime gate CLOSED" in md
