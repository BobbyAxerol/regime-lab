"""The FP-08 verifier fails on real failure shapes, per gate -- plus one
test proving a fully valid bundle passes (mirrors test_fp01..07_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp08 import REQUIRED_ARTIFACTS, verify_fp08

TEST_NODE_IDS = (
    "test_anchors_from_selections_excludes_fallback_origins",
    "test_age_windows_uses_28_56_84_day_boundaries_not_the_old_90_day_ones",
    "test_signed_decline_h1_minus_later_positive_when_decaying",
)

ALL_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
ALL_ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")


def _junit(path: Path, *, tests: int = 21, failures: int = 0, nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp08_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _one_window(horizon, lo, hi, *, status="COMPLETE", mean=0.001, fill_count=5):
    row = {"horizon": horizon, "days_required": hi - lo, "days_available": hi - lo if status == "COMPLETE" else 0,
          "status": status, "metrics": ({"mean_daily_return": mean} if status == "COMPLETE" else None)}
    if status == "COMPLETE":
        row["exposure"] = {"status": "OK", "fill_count": fill_count}
    return row


def _record(arm, origin, *, h1=0.002, h2=0.0005, h3=0.0003):
    windows = [_one_window("H1", 0, 28, mean=h1), _one_window("H2", 28, 56, mean=h2),
              _one_window("H3", 56, 84, mean=h3)]
    return {
        "arm": arm, "origin_cutoff": origin, "params": {"coeff": 1}, "age_windows": windows,
        "signed_decline": {
            "H1_minus_H2": {"value": h1 - h2, "convention": "H1 - later"},
            "H1_minus_H3": {"value": h1 - h3, "convention": "H1 - later"},
        },
        "censored_horizons": [], "fully_complete": True,
    }


def _coverage_matrix() -> dict:
    cells = []
    for alpha in ALL_ALPHAS:
        for symbol in ALL_SYMBOLS:
            if (alpha, symbol) == ("A-SC", "BTCUSDT"):
                cells.append({"alpha_id": alpha, "symbol": symbol, "status": "COMPLETED",
                             "evidence_ref": "evidence/.../fp07-run"})
            elif (alpha, symbol) == ("A-SC", "ETHUSDT"):
                cells.append({"alpha_id": alpha, "symbol": symbol, "status": "COMPLETED",
                             "evidence_ref": "evidence/.../fp08-cell2-run"})
            else:
                cells.append({"alpha_id": alpha, "symbol": symbol, "status": "NOT_RUN",
                             "reason": "outside FP-08's disclosed 2-cell replication scope"})
    return {"schema": "regime_lab.fp08_coverage_matrix.v1", "cells": cells}


def _bundle(root: Path) -> dict:
    docs = {
        "coverage_matrix.json": _coverage_matrix(),
        "d2_analysis.json": {
            "schema": "regime_lab.fp08_d2_analysis.v1",
            "cell1": {"records": [_record("A_STOCK_CAL", "2021-01-01")]},
            "cell2": {"records": [_record("A_STOCK_CAL", "2021-06-01")]},
        },
        "statistics.json": {
            "schema": "regime_lab.fp08_statistics.v1",
            "contrasts": {
                "C_FP_CONTEXT - B_FP_PERSISTENCE": {"status": "ESTIMATED", "block": 28,
                                                    "estimate": 0.0, "degenerate": True,
                                                    "degenerate_reason": "C==B in cell 1"},
                "B_FP_PERSISTENCE - A_STOCK_CAL": {"status": "ESTIMATED", "block": 28,
                                                   "estimate": -0.0002},
            },
            "concentration_by_period_cell": [
                {"alpha_id": "A-SC", "symbol": "BTCUSDT", "period": "2021", "value": 0.0001},
                {"alpha_id": "A-SC", "symbol": "ETHUSDT", "period": "2021", "value": -0.0002},
            ],
        },
        "contribution_checks.json": {
            "schema": "regime_lab.fp08_contribution_checks.v1",
            "answers": [
                {"question": "Context có thực sự đổi candidate rankings/selections không?",
                "answer": "No in cell 1 -- C never differed from B (0/12 origins CONTEXT_CONDITIONED)"},
            ]},
        "decision_rules.json": {
            "schema": "regime_lab.fp08_decision_rules.v1",
            "dispositions": [{"claim": "B-A economic", "disposition": "Inconclusive effect/support"}],
        },
        "resource_budget.json": {"schema": "regime_lab.fp08_resource_budget.v1"},
        "test_registry.json": {"schema": "regime_lab.fp08_test_registry.v1",
                               "test_node_ids": list(TEST_NODE_IDS)},
        "phase_manifest.json": {"artifacts": []},
        "gate_receipt.json": {"schema": "regime_lab.fp_gate.v1", "technical_gate": "NOT_RUN"},
    }
    entries = []
    for name, doc in docs.items():
        (root / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        entries.append({"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()})
    docs["phase_manifest.json"]["artifacts"] = entries
    (root / "phase_manifest.json").write_text(json.dumps(docs["phase_manifest.json"], indent=2),
                                              encoding="utf-8")
    (root / "report.md").write_text(
        "# FP-08\n\n## Permitted conclusions\n- Technical: ok\n- Research: see decision_rules.json\n",
        encoding="utf-8")
    (root / "handoff.md").write_text("# FP-08 handoff\n", encoding="utf-8")
    return docs


def _rewrite(root: Path, name: str, doc: dict, manifest: dict) -> None:
    (root / name).write_text(json.dumps(doc), encoding="utf-8")
    for entry in manifest["artifacts"]:
        if entry["path"] == name:
            entry["sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fp08_verifier_passes_on_a_valid_bundle(lab_tmp):
    assert set(REQUIRED_ARTIFACTS) >= {"coverage_matrix.json", "d2_analysis.json", "statistics.json"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp08_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp08(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp08_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "d2_analysis.json").write_text('{"forged": true}', encoding="utf-8")
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("d2_analysis.json" in r for g in verdict["gates"].values() for r in g["reasons"])


def test_fp08_g_replication_fails_when_the_matrix_is_not_20_cells(lab_tmp):
    root = Path(str(lab_tmp)) / "wrong-cell-count"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    coverage = docs["coverage_matrix.json"]
    coverage["cells"] = coverage["cells"][:5]
    _rewrite(root, "coverage_matrix.json", coverage, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-REPLICATION"]["pass"]
    assert any("20" in r for r in verdict["gates"]["FP08-G-REPLICATION"]["reasons"])


def test_fp08_g_replication_fails_when_a_completed_cell_has_no_evidence_ref(lab_tmp):
    root = Path(str(lab_tmp)) / "no-evidence-ref"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    coverage = docs["coverage_matrix.json"]
    coverage["cells"][0]["status"] = "COMPLETED"
    coverage["cells"][0].pop("evidence_ref", None)
    coverage["cells"][0].pop("reason", None)
    _rewrite(root, "coverage_matrix.json", coverage, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-REPLICATION"]["pass"]
    assert any("no evidence_ref" in r for r in verdict["gates"]["FP08-G-REPLICATION"]["reasons"])


def test_fp08_g_d2_fails_when_signed_decline_does_not_match_the_raw_windows(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-decline"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    d2doc = docs["d2_analysis.json"]
    d2doc["cell1"]["records"][0]["signed_decline"]["H1_minus_H2"]["value"] = 999.0
    _rewrite(root, "d2_analysis.json", d2doc, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-D2"]["pass"]
    assert any("recomputed from the raw stored" in r for r in verdict["gates"]["FP08-G-D2"]["reasons"])


def test_fp08_g_d2_fails_on_wrong_window_boundaries_the_old_90_day_scheme(lab_tmp):
    root = Path(str(lab_tmp)) / "old-90-day"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    d2doc = docs["d2_analysis.json"]
    d2doc["cell1"]["records"][0]["age_windows"][0]["days_required"] = 90
    _rewrite(root, "d2_analysis.json", d2doc, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-D2"]["pass"]
    assert any("28/56/84-day freeze" in r for r in verdict["gates"]["FP08-G-D2"]["reasons"])


def test_fp08_g_d2_fails_when_a_censored_window_carries_a_metric(lab_tmp):
    root = Path(str(lab_tmp)) / "censored-with-metric"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    d2doc = docs["d2_analysis.json"]
    d2doc["cell1"]["records"][0]["age_windows"][2]["status"] = "CENSORED"
    # metrics left populated -- the bug this gate exists to catch
    _rewrite(root, "d2_analysis.json", d2doc, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-D2"]["pass"]
    assert any("CENSORED but carries" in r for r in verdict["gates"]["FP08-G-D2"]["reasons"])


def test_fp08_g_inference_fails_when_a_degenerate_contrast_has_no_reason(lab_tmp):
    root = Path(str(lab_tmp)) / "degenerate-no-reason"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    stats = docs["statistics.json"]
    stats["contrasts"]["C_FP_CONTEXT - B_FP_PERSISTENCE"]["degenerate_reason"] = None
    _rewrite(root, "statistics.json", stats, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-INFERENCE"]["pass"]
    assert any("degenerate_reason" in r for r in verdict["gates"]["FP08-G-INFERENCE"]["reasons"])


def test_fp08_g_inference_fails_when_a_contrast_does_not_use_the_28_day_block(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-block"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    stats = docs["statistics.json"]
    stats["contrasts"]["B_FP_PERSISTENCE - A_STOCK_CAL"]["block"] = 7
    _rewrite(root, "statistics.json", stats, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-INFERENCE"]["pass"]
    assert any("registered 28-day block" in r for r in verdict["gates"]["FP08-G-INFERENCE"]["reasons"])


def test_fp08_g_inference_fails_when_contribution_checks_has_no_answers(lab_tmp):
    root = Path(str(lab_tmp)) / "empty-contribution"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    contrib = docs["contribution_checks.json"]
    contrib["answers"] = []
    _rewrite(root, "contribution_checks.json", contrib, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-INFERENCE"]["pass"]
    assert any("no answers" in r for r in verdict["gates"]["FP08-G-INFERENCE"]["reasons"])


def test_fp08_g_concentration_fails_when_a_completed_cell_is_absent_from_the_breakdown(lab_tmp):
    root = Path(str(lab_tmp)) / "hidden-cell"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    stats = docs["statistics.json"]
    stats["concentration_by_period_cell"] = [
        row for row in stats["concentration_by_period_cell"] if row["symbol"] != "ETHUSDT"]
    _rewrite(root, "statistics.json", stats, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-CONCENTRATION"]["pass"]
    assert any("absent from the concentration" in r
              for r in verdict["gates"]["FP08-G-CONCENTRATION"]["reasons"])


def test_fp08_g_verdict_fails_on_a_disposition_outside_the_registered_vocabulary(lab_tmp):
    root = Path(str(lab_tmp)) / "invented-label"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    decisions = docs["decision_rules.json"]
    decisions["dispositions"][0]["disposition"] = "Strong proof of edge"
    _rewrite(root, "decision_rules.json", decisions, docs["phase_manifest.json"])
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-VERDICT"]["pass"]
    assert any("registered vocabulary" in r for r in verdict["gates"]["FP08-G-VERDICT"]["reasons"])


def test_fp08_g_verdict_fails_on_a_forbidden_overclaim_phrase(lab_tmp):
    root = Path(str(lab_tmp)) / "overclaim"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text(
        "# FP-08\n\nThis proves the edge across both cells.\n\n"
        "## Permitted conclusions\n- Technical: ok\n",
        encoding="utf-8")
    verdict = verify_fp08(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP08-G-VERDICT"]["pass"]
    assert any("forbidden overclaim phrase" in r for r in verdict["gates"]["FP08-G-VERDICT"]["reasons"])
