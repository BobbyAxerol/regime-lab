"""The FP-06 verifier fails on real failure shapes, per gate -- plus one
test proving a fully valid bundle passes (mirrors test_fp01..05_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp06 import REQUIRED_ARTIFACTS, verify_fp06

TEST_NODE_IDS = (
    "test_fp06_t01_walk_forward_oof_with_the_default_builder_is_exactly_selector_b",
    "test_fp06_t02_relabeling_a_context_key_does_not_change_the_computed_interaction_value",
    "test_compute_context_features_never_reads_bars_after_the_frame_end",
)


def _junit(path: Path, *, tests: int = 46, failures: int = 0,
          nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp06_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _bundle(root: Path) -> dict:
    b_preds = {"2023-10-01:R00": 0.00001, "2023-10-01:R01": 0.00002}
    c_preds = {"2023-10-01:R00": 0.00003, "2023-10-01:R01": 0.00001}
    diffs = {rid: c_preds[rid] - b_preds[rid] for rid in b_preds}
    docs = {
        "context_policy.json": {
            "schema": "regime_lab.fp06_context_policy.v1",
            "context_feature_names": ["ctx_direction_efficiency", "ctx_volatility_ratio"],
            "interaction_specs": [{"a": "norm_AP", "b": "ctx_direction_efficiency", "reason": "x"}],
            "frozen_at_utc": "2026-09-23T00:00:00+00:00",
        },
        "oof_diagnostics_c.json": {
            "schema": "regime_lab.fp06_oof_diagnostics.v1", "n_fit_origins": 12,
            "n_validation_origins": 8, "validation_origins": ["2022-01-01"],
        },
        "candidate_scores_c.json": {
            "schema": "regime_lab.fp06_candidate_scores.v1", "demo_origin": "2023-10-01",
            "scored": [
                {"record_id": "2023-10-01:R00", "source": "CONTEXT_CONDITIONED"},
                {"record_id": "2023-10-01:R01", "source": "FALLBACK_TO_B"},
            ],
        },
        "ablation.json": {
            "schema": "regime_lab.fp06_ablation.v1", "n_shared": 2, "only_in_b": [], "only_in_c": [],
            "b_predictions": b_preds, "c_predictions": c_preds, "diffs": diffs,
            "mean_diff": sum(diffs.values()) / len(diffs),
        },
        "exposure.json": {
            "schema": "regime_lab.fp06_exposure.v1", "jm_observations": 0, "m0_observations": 0,
            "unknown_stale_ambiguous": 0, "fallback_to_b_count": 1, "context_conditioned_count": 1,
            "n_scored_total": 2,
        },
        "resource_budget.json": {"fp06_wall_seconds_charged_to_shared_ledger": 0},
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
        "# FP-06\n\n## Permitted conclusions\n- Technical: ok\n- Research: NOT_ASSESSED\n",
        encoding="utf-8")
    (root / "handoff.md").write_text("# FP-06 handoff\n", encoding="utf-8")
    return docs


def _rewrite(root: Path, name: str, doc: dict, manifest: dict) -> None:
    (root / name).write_text(json.dumps(doc), encoding="utf-8")
    for entry in manifest["artifacts"]:
        if entry["path"] == name:
            entry["sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fp06_verifier_passes_on_a_valid_bundle(lab_tmp):
    assert set(REQUIRED_ARTIFACTS) >= {"context_policy.json", "ablation.json", "exposure.json"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp06(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp06_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp06(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp06_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "ablation.json").write_text('{"forged": true}', encoding="utf-8")
    verdict = verify_fp06(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("ablation.json" in r for g in verdict["gates"].values() for r in g["reasons"])


def test_fp06_g_ablation_fails_when_stored_diff_does_not_match_recomputation(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-diff"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    ablation = docs["ablation.json"]
    ablation["diffs"]["2023-10-01:R00"] = 999.0   # does not equal c_predictions - b_predictions
    _rewrite(root, "ablation.json", ablation, docs["phase_manifest.json"])
    verdict = verify_fp06(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP06-G-ABLATION"]["pass"]
    assert any("recomputed from the raw stored values" in r
              for r in verdict["gates"]["FP06-G-ABLATION"]["reasons"])


def test_fp06_g_support_fails_when_fallback_count_disagrees_with_recomputation(lab_tmp):
    """The real bug class: exposure.json claiming a fallback count that
    does not match a fresh recount of candidate_scores_c.json's own
    per-candidate source field -- a stale or hand-typed summary number."""
    root = Path(str(lab_tmp)) / "bad-fallback-count"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    exposure = docs["exposure.json"]
    exposure["fallback_to_b_count"] = 999
    _rewrite(root, "exposure.json", exposure, docs["phase_manifest.json"])
    verdict = verify_fp06(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP06-G-SUPPORT"]["pass"]
    assert any("disagrees with a fresh recount" in r
              for r in verdict["gates"]["FP06-G-SUPPORT"]["reasons"])


def test_fp06_g_claim_fails_on_a_jm_specific_claim_with_zero_jm_exposure(lab_tmp):
    """guide 9.5/FP06-G-CLAIM: never call a generic context result
    JM-specific unless JM was actually exercised and separated. exposure.json
    records zero JM observations in this v1 -- the report must not claim
    otherwise."""
    root = Path(str(lab_tmp)) / "jm-overclaim"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text(
        "# FP-06\n\nThis shows a JM-specific contribution.\n\n"
        "## Permitted conclusions\n- Technical: ok\n- Research: NOT_ASSESSED\n",
        encoding="utf-8")
    verdict = verify_fp06(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP06-G-CLAIM"]["pass"]
    assert any("JM-specific" in r for r in verdict["gates"]["FP06-G-CLAIM"]["reasons"])


def test_fp06_g_freeze_fails_when_context_policy_has_no_freeze_timestamp(lab_tmp):
    root = Path(str(lab_tmp)) / "no-freeze"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    policy = docs["context_policy.json"]
    del policy["frozen_at_utc"]
    _rewrite(root, "context_policy.json", policy, docs["phase_manifest.json"])
    verdict = verify_fp06(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP06-G-FREEZE"]["pass"]


def test_fp06_g_causal_fails_when_a_required_causal_test_is_not_registered(lab_tmp):
    root = Path(str(lab_tmp)) / "missing-causal-test"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    registry = docs["test_registry.json"]
    registry["test_node_ids"] = ["test_something_unrelated"]
    _rewrite(root, "test_registry.json", registry, docs["phase_manifest.json"])
    verdict = verify_fp06(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP06-G-CAUSAL"]["pass"]
