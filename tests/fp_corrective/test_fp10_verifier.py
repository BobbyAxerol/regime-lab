"""The FP-10 verifier fails on real failure shapes, per gate -- plus one
test proving a fully valid bundle passes (mirrors test_fp01..09_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp10 import (
    REQUIRED_ARTIFACTS, REQUIRED_FREEZE_COMPONENTS, verify_fp10,
)

TEST_NODE_IDS = (
    "test_fp10_verifier_passes_on_a_valid_bundle",
    "test_fp10_g_freeze_fails_on_a_tampered_source_file",
)

REPORT_TEXT = (
    "# FP-10 final report\n\n"
    "## Final report questions\n"
    "1. Tang trials co cai thien forward outcomes khong? No -- FP-03 evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/report.md shows D stayed positive at every checkpoint.\n"
    "2. B co tot hon A khong? No -- evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/report.md CI entirely below zero.\n"
    "3. C co tot hon B khong? Degenerate -- evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/report.md C==B.\n"
    "4. Decay giam co di cung utility/risk chap nhan duoc khong? Descriptive only, delta_decay NOT_REGISTERED.\n"
    "5. Ket qua den tu conditional selection, timing, cadence hay exposure? FP-09 evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a/report.md shows a small non-significant timing effect.\n"
    "6. Support va uncertainty cho phep ket luan manh den dau? Weak -- single cell throughout.\n"
    "7. Nhung gia thuyet nao chua duoc thu? H_ADMISSION_FREQUENCY and H_DECAY_RISK_DEFERRAL.\n"
    "8. Chi phi da tieu va phan nao tai su dung duoc? ~14.7h real engine wall time; FP-04's archive is reusable.\n"
    "9. Co nen dung, giu baseline hay mo mot research revision cu the? Keep baseline (Arm A).\n"
)


def _junit(path: Path, *, tests: int = 20, failures: int = 0, nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp10_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _bundle(root: Path, lab_root: Path) -> dict:
    real_file = lab_root / "src" / "crypto_regime_lab" / "fp" / "__init__.py"
    assert real_file.is_file(), "fixture assumes fp/__init__.py exists in the real lab tree"
    code_row = {"path": "src/crypto_regime_lab/fp/__init__.py",
               "sha256": hashlib.sha256(real_file.read_bytes()).hexdigest()}
    docs = {
        "freeze_manifest.json": {
            "schema": "regime_lab.fp10_freeze_manifest.v1", "status": "FROZEN",
            "components": {key: [code_row] if key == "code_dependency_engine_digests" else
                          [{"note": "placeholder"}] for key in REQUIRED_FREEZE_COMPONENTS},
            "data_exposure": {"development_role_span": "2020-01-01..2023-12-31",
                              "outer_evaluation_touched": False,
                              "prospective_status": "NOT_RUN_NO_ELIGIBLE_NEW_DATA",
                              "engineering_status": "COMPLETE_WITHIN_SCOPE"},
        },
        "replay_result.json": {
            "schema": "regime_lab.fp10_replay_result.v1",
            "original_run_dir": "evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a",
            "replay_run_dir": "evidence/forward_persistence_fp_v1/fp10-replay-fixture",
            "evaluation_label": "FROZEN_REPLAY",
            "independence_note": "this is NOT an independent confirmation -- same frozen data replayed",
            "comparisons": [
                {"field": "SELECTOR_FIXED_CAL.fill_count", "original": 3312, "replay": 3312, "match": True},
                {"field": "primary_contrast.estimate", "original": 6e-06, "replay": 6e-06, "match": True},
            ],
        },
        "artifact_index.json": {
            "schema": "regime_lab.fp10_artifact_index.v1",
            "phases": [{"phase": "FP-09", "run_dir": "evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a",
                       "gate": "PASS"}],
        },
        "test_registry.json": {"schema": "regime_lab.fp10_test_registry.v1",
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
    (root / "final_report.md").write_text(REPORT_TEXT, encoding="utf-8")
    (root / "handoff.md").write_text(
        "# FP-10 handoff\n\n"
        "## Replay command\n`lab_venv/bin/python scripts/run_fp09.py --pytest-xml ...`\n\n"
        "## Unresolved issues\n- none blocking\n\n"
        "## Budget summary\n~14.7h real engine wall time across FP-01..09\n\n"
        "See evidence/regime_time_edge_ra_v1/owner_decisions.jsonl for the full decision ledger.\n",
        encoding="utf-8")
    return docs


def _rewrite(root: Path, name: str, doc: dict, manifest: dict) -> None:
    (root / name).write_text(json.dumps(doc), encoding="utf-8")
    for entry in manifest["artifacts"]:
        if entry["path"] == name:
            entry["sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fp10_verifier_passes_on_a_valid_bundle(lab_tmp, lab_root):
    assert set(REQUIRED_ARTIFACTS) >= {"freeze_manifest.json", "replay_result.json", "final_report.md"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root, Path(str(lab_root)))
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp10_verifier_fails_on_empty_dir(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp10_g_freeze_fails_on_a_tampered_source_file(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "tampered-source"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root, Path(str(lab_root)))
    freeze = docs["freeze_manifest.json"]
    freeze["components"]["code_dependency_engine_digests"][0]["sha256"] = "0" * 64
    _rewrite(root, "freeze_manifest.json", freeze, docs["phase_manifest.json"])
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-FREEZE"]["pass"]


def test_fp10_g_freeze_fails_when_a_component_category_is_missing(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "missing-component"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root, Path(str(lab_root)))
    freeze = docs["freeze_manifest.json"]
    del freeze["components"]["support_fallback_admission_rules"]
    _rewrite(root, "freeze_manifest.json", freeze, docs["phase_manifest.json"])
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-FREEZE"]["pass"]


def test_fp10_g_replay_fails_when_a_comparison_does_not_match(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "replay-mismatch"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root, Path(str(lab_root)))
    replay = docs["replay_result.json"]
    replay["comparisons"][0]["match"] = False
    replay["comparisons"][0]["replay"] = 9999
    _rewrite(root, "replay_result.json", replay, docs["phase_manifest.json"])
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-REPLAY"]["pass"]


def test_fp10_g_replay_fails_without_the_non_independence_disclosure(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "replay-overclaim"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root, Path(str(lab_root)))
    replay = docs["replay_result.json"]
    replay["independence_note"] = "this confirms the finding"
    _rewrite(root, "replay_result.json", replay, docs["phase_manifest.json"])
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-REPLAY"]["pass"]


def test_fp10_g_report_fails_when_a_required_question_is_unanswered(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "missing-question"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root, Path(str(lab_root)))
    (root / "final_report.md").write_text("# FP-10\n\nonly a partial report\n", encoding="utf-8")
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-REPORT"]["pass"]


def test_fp10_g_report_fails_on_a_forbidden_overclaim_phrase(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "overclaim"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root, Path(str(lab_root)))
    (root / "final_report.md").write_text(REPORT_TEXT + "\nThis proves the edge.\n", encoding="utf-8")
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-REPORT"]["pass"]


def test_fp10_g_exposure_fails_when_outer_evaluation_touched_is_not_declared_false(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "exposure-silent"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root, Path(str(lab_root)))
    freeze = docs["freeze_manifest.json"]
    del freeze["data_exposure"]["outer_evaluation_touched"]
    _rewrite(root, "freeze_manifest.json", freeze, docs["phase_manifest.json"])
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-EXPOSURE"]["pass"]


def test_fp10_g_handoff_fails_without_a_replay_command_section(lab_tmp, lab_root):
    root = Path(str(lab_tmp)) / "no-replay-command"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root, Path(str(lab_root)))
    (root / "handoff.md").write_text("# FP-10 handoff\n\nnothing else here\n", encoding="utf-8")
    verdict = verify_fp10(root, lab_root=lab_root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP10-G-HANDOFF"]["pass"]
