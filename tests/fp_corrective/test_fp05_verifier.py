"""The FP-05 verifier fails on real failure shapes, per gate -- plus one
test proving a fully valid bundle passes (mirrors test_fp01..04_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from crypto_regime_lab.fp import selector_b as sb
from crypto_regime_lab.fp.verifier_fp05 import REQUIRED_ARTIFACTS, verify_fp05

TEST_NODE_IDS = (
    "test_walk_forward_oof_never_trains_on_a_later_origins_own_record",
    "test_fit_ridge_recovers_a_known_linear_relationship_at_low_alpha",
)


def _junit(path: Path, *, tests: int = 25, failures: int = 0,
          nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp05_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _real_model_and_inputs():
    """A REAL fit_ridge call so FP05-G-MODEL's refit-determinism check has
    something genuine to reproduce, not a hand-typed (and possibly
    internally-inconsistent) coefficient set."""
    rng = np.random.default_rng(7)
    X = rng.normal(size=(30, len(sb.FEATURE_NAMES)))
    y = X[:, 0] * 0.01 + rng.normal(scale=0.0005, size=30)
    w = np.ones(30)
    model = sb.fit_ridge(X, y, w, alpha=1.0)
    return model, X, y, w


def _bundle(root: Path) -> dict:
    model, X, y, w = _real_model_and_inputs()
    fold_audit = [{
        "validation_origin": "2022-01-01", "validation_origin_time": "2022-01-01T00:00:00+00:00",
        "n_train_rows": 3,
        "train_label_available_ats": ["2021-10-29T00:00:00+00:00", "2021-08-01T00:00:00+00:00"],
    }]
    docs = {
        "oof_diagnostics.json": {
            "schema": "regime_lab.fp05_oof_diagnostics.v1",
            "n_fit_origins": 12, "n_validation_origins": 8,
            "validation_origins": ["2022-01-01"], "fold_audit": fold_audit,
        },
        "model_selection.json": {
            "schema": "regime_lab.fp05_model_selection.v1", "selected_alpha": 1.0,
            "final_model": model, "refit_inputs": {"X": X.tolist(), "y": y.tolist(), "w": w.tolist()},
            "decay_risk_branch": {"branch": "MEAN_DECAY", "reason": "TAIL_ESTIMATE_UNSUPPORTED: x"},
        },
        "candidate_scores.json": {
            "schema": "regime_lab.fp05_candidate_scores.v1",
            "scored": [{"record_id": "2023-10-01:R00", "is_mean_daily_return": 0.0005,
                       "predicted_forward_utility": 0.0003, "decay_risk_score": 0.0002,
                       "branch": "MEAN_DECAY", "D_point_estimate": 0.0002}],
        },
        "admission_and_deployment.json": {
            "schema": "regime_lab.fp05_admission_and_deployment.v1",
            "selector_b_decision": "ADMIT", "selected_params": {"coeff": 4},
            "admission_lineage": {"0": {"decision": "ADMIT", "consumed": {"coeff": 4}}},
            "deployment_result": {"fills": [{"bar_index": 0, "qty": 1.0}], "fill_count": 1},
        },
        "resource_budget.json": {"fp05_wall_seconds_charged_to_shared_ledger": 0},
        "test_registry.json": {"test_node_ids": list(TEST_NODE_IDS)},
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
        "# FP-05\n\n## Permitted conclusions\n- Technical: ok\n- Research: NOT_ASSESSED\n",
        encoding="utf-8")
    (root / "handoff.md").write_text("# FP-05 handoff\n", encoding="utf-8")
    return docs


def _rewrite(root: Path, name: str, doc: dict, manifest: dict) -> None:
    (root / name).write_text(json.dumps(doc), encoding="utf-8")
    for entry in manifest["artifacts"]:
        if entry["path"] == name:
            entry["sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fp05_verifier_passes_on_a_valid_bundle(lab_tmp):
    assert set(REQUIRED_ARTIFACTS) >= {"oof_diagnostics.json", "model_selection.json",
                                       "candidate_scores.json", "admission_and_deployment.json"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp05(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp05_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp05(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp05_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "model_selection.json").write_text('{"forged": true}', encoding="utf-8")
    verdict = verify_fp05(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("model_selection.json" in r for g in verdict["gates"].values() for r in g["reasons"])


def test_fp05_g_split_fails_on_an_injected_future_label_leak(lab_tmp):
    """The real bug class this gate exists to catch: a training row in some
    fold whose label_available_at is AT OR AFTER that fold's own validation
    decision time -- guide 8.4's dormant-risk class, injected directly here."""
    root = Path(str(lab_tmp)) / "future-leak"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    oof = docs["oof_diagnostics.json"]
    oof["fold_audit"][0]["train_label_available_ats"].append("2022-06-01T00:00:00+00:00")
    _rewrite(root, "oof_diagnostics.json", oof, docs["phase_manifest.json"])
    verdict = verify_fp05(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP05-G-SPLIT"]["pass"]
    assert any("future-label leak" in r for r in verdict["gates"]["FP05-G-SPLIT"]["reasons"])


def test_fp05_g_model_fails_when_stored_coef_does_not_match_a_refit(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-coef"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    model_sel = docs["model_selection.json"]
    model_sel["final_model"]["coef"] = [999.0] * len(model_sel["final_model"]["coef"])
    _rewrite(root, "model_selection.json", model_sel, docs["phase_manifest.json"])
    verdict = verify_fp05(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP05-G-MODEL"]["pass"]
    assert any("not deterministic" in r for r in verdict["gates"]["FP05-G-MODEL"]["reasons"])


def test_fp05_g_support_fails_when_stored_branch_disagrees_with_recomputation(lab_tmp):
    """n_fit=12, n_oof=8 recomputes to MEAN_DECAY (guide 8.7); claiming
    TAIL_QUANTILE here is the exact wrong-branch failure this gate exists
    to catch."""
    root = Path(str(lab_tmp)) / "wrong-branch"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    model_sel = docs["model_selection.json"]
    model_sel["decay_risk_branch"] = {"branch": "TAIL_QUANTILE", "reason": None}
    _rewrite(root, "model_selection.json", model_sel, docs["phase_manifest.json"])
    verdict = verify_fp05(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP05-G-SUPPORT"]["pass"]
    assert any("does not match" in r for r in verdict["gates"]["FP05-G-SUPPORT"]["reasons"])


def test_fp05_g_action_fails_when_admit_has_no_deployment_fills(lab_tmp):
    """The real bug class: an ADMIT decision that never actually reached a
    real account -- exactly the shape of LAB-07's 'gate passed on an empty
    run' defect class this lab keeps finding in itself."""
    root = Path(str(lab_tmp)) / "empty-admit"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    admission = docs["admission_and_deployment.json"]
    admission["deployment_result"] = {"fills": [], "fill_count": 0}
    _rewrite(root, "admission_and_deployment.json", admission, docs["phase_manifest.json"])
    verdict = verify_fp05(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP05-G-ACTION"]["pass"]
    assert any("zero fills" in r for r in verdict["gates"]["FP05-G-ACTION"]["reasons"])


def test_fp05_g_report_fails_when_technical_and_research_status_are_not_separated(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-report"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text("# FP-05\n\nEverything looks great.\n", encoding="utf-8")
    verdict = verify_fp05(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP05-G-REPORT"]["pass"]
