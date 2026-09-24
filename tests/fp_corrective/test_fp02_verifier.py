"""The FP-02 verifier fails on real failure shapes, per gate -- plus one test
proving a fully valid bundle passes, so the refusal tests cannot all pass by
construction (mirrors tests/fp_corrective/test_fp01_verifier.py's pattern).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp02 import (
    REQUIRED_ARTIFACTS, REQUIRED_TEST_NODES, verify_fp02,
)

CUTOFF = "2023-06-10T00:00:00+00:00"


def _junit(path: Path, *, tests: int = 6, failures: int = 0,
          nodes: tuple = REQUIRED_TEST_NODES) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp02_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _bundle(root: Path) -> dict:
    docs = {
        "route_parity.json": {
            "status": "PASS", "equity_exact_equal": True, "max_abs_equity_diff": 0.0,
            "entries_match": True, "fill_count_match": True,
            "audit": {"fill_count": 5, "engine_fill_count": 5},
            "fast": {"fill_count": 5, "engine_fill_count": 0},
        },
        "cache_reuse.json": {
            "first": {"status": "MISS"},
            "first_causality": {"physical_compute_at": "2026-09-22T00:00:00+00:00",
                                "simulated_cutoff": CUTOFF, "simulated_ready_at": CUTOFF},
            "reused": {"status": "HIT", "payload_identical": True},
            "changed_economics": {"status": "MISS", "terminal_equity_changed": True},
        },
        "lineage_demo.json": {
            "status": "MISS",
            "lineage": {
                "fills_total": 3, "fills_attributed": 3, "activations_effected": 2,
                "activations": [
                    {"activation_id": None, "sentinel": "WARMING", "bar_range": [0, 8],
                     "fill_count": 0},
                    {"activation_id": "initial", "bar_range": [8, 500], "fill_count": 2},
                    {"activation_id": None, "sentinel": "WARMING", "bar_range": [500, 511],
                     "fill_count": 0},
                    {"activation_id": "switch", "bar_range": [511, 1000], "fill_count": 1},
                ],
            },
        },
        "resume_demo.json": {
            "pre_resume_statuses": ["MISS", "MISS"],
            "post_resume_statuses": ["HIT", "HIT", "MISS"],
            "total_misses": 3, "unique_candidates": 3,
        },
        "memory_audit.json": {
            "budget_mib": 4096, "per_call_peak_mib": [500.0, 480.0, 510.0, 495.0, 505.0],
            "within_budget": True, "not_growing_unboundedly": True,
        },
        "resource_budget.json": {"fp02_wall_seconds_charged_to_shared_ledger": 0,
                                 "engine_calls": 16},
        "test_registry.json": {"test_node_ids": list(REQUIRED_TEST_NODES)},
        "phase_manifest.json": {"artifacts": []},
        "gate_receipt.json": {"schema": "regime_lab.fp_gate.v1", "technical_gate": "NOT_RUN"},
    }
    entries = []
    for name, doc in docs.items():
        (root / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        entries.append({"path": name,
                        "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()})
    docs["phase_manifest.json"]["artifacts"] = entries
    (root / "phase_manifest.json").write_text(
        json.dumps(docs["phase_manifest.json"], indent=2), encoding="utf-8")
    (root / "report.md").write_text("# FP-02\n", encoding="utf-8")
    (root / "handoff.md").write_text("# FP-02 handoff\n", encoding="utf-8")
    return docs


def _names_present() -> None:
    assert set(REQUIRED_ARTIFACTS) >= {
        "route_parity.json", "cache_reuse.json", "lineage_demo.json", "resume_demo.json",
        "memory_audit.json", "resource_budget.json", "test_registry.json",
        "phase_manifest.json", "gate_receipt.json", "report.md", "handoff.md"}
    assert len(REQUIRED_TEST_NODES) == 6


def test_fp02_verifier_passes_on_a_valid_bundle(lab_tmp):
    _names_present()
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp02(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp02_verifier_survives_the_real_two_stage_gate_receipt_write(lab_tmp):
    """The actual bug this exclusion fixes (found on a real run, not
    invented): run_fp02.py hashes gate_receipt.json into phase_manifest.json
    BEFORE updating gate_receipt.json in place with the verdict THAT
    VERIFICATION run produces. Reproduce the exact sequence here -- hash a
    PLACEHOLDER gate_receipt.json into the manifest, then overwrite
    gate_receipt.json with different (verdict-added) bytes -- and require
    the verifier to still PASS. The other bundle tests never exercise this:
    they write gate_receipt.json ONCE, already final, so this is the only
    test that would have caught the regression before a real run did."""
    root = Path(str(lab_tmp)) / "two-stage"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    # _bundle already wrote a single-stage gate_receipt.json and hashed it
    # into phase_manifest.json; simulate the SECOND write now, exactly as
    # run_fp02.py does, without touching the manifest again.
    docs["gate_receipt.json"]["technical_gate"] = "PASS"
    docs["gate_receipt.json"]["verification"] = {"overall": "PASS"}
    docs["gate_receipt.json"]["verified_at_utc"] = "2026-09-22T18:00:00+00:00"
    (root / "gate_receipt.json").write_text(json.dumps(docs["gate_receipt.json"], indent=2),
                                            encoding="utf-8")
    assert hashlib.sha256((root / "gate_receipt.json").read_bytes()).hexdigest() != next(
        e["sha256"] for e in json.loads((root / "phase_manifest.json").read_text())["artifacts"]
        if e["path"] == "gate_receipt.json"), "the fixture must actually reproduce the drift"
    verdict = verify_fp02(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert not any("gate_receipt.json" in r
                  for g in verdict["gates"].values() for r in g["reasons"])


def test_fp02_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp02(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"], "an empty dir must report what is missing"


def test_fp02_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "route_parity.json").write_text('{"status": "forged"}', encoding="utf-8")
    verdict = verify_fp02(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL", "a post-manifest edit must not PASS"
    assert any("route_parity.json" in r
              for g in verdict["gates"].values() for r in g["reasons"])


def test_fp02_verifier_fails_when_parity_route_disagrees(lab_tmp):
    root = Path(str(lab_tmp)) / "parity-fail"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    docs["route_parity.json"]["equity_exact_equal"] = False
    docs["route_parity.json"]["max_abs_equity_diff"] = 0.5
    (root / "route_parity.json").write_text(json.dumps(docs["route_parity.json"]),
                                            encoding="utf-8")
    manifest = json.loads((root / "phase_manifest.json").read_text())
    for entry in manifest["artifacts"]:
        if entry["path"] == "route_parity.json":
            entry["sha256"] = hashlib.sha256(
                (root / "route_parity.json").read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = verify_fp02(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP02-G-PARITY"]["pass"]


def test_fp02_verifier_fails_when_lineage_fills_do_not_reconcile(lab_tmp):
    root = Path(str(lab_tmp)) / "lineage-fail"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    docs["lineage_demo.json"]["lineage"]["fills_attributed"] = 2  # disagrees with fills_total=3
    (root / "lineage_demo.json").write_text(json.dumps(docs["lineage_demo.json"]),
                                            encoding="utf-8")
    manifest = json.loads((root / "phase_manifest.json").read_text())
    for entry in manifest["artifacts"]:
        if entry["path"] == "lineage_demo.json":
            entry["sha256"] = hashlib.sha256(
                (root / "lineage_demo.json").read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = verify_fp02(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP02-G-LINEAGE"]["pass"]


def test_fp02_verifier_fails_when_resume_recomputes_twice(lab_tmp):
    root = Path(str(lab_tmp)) / "resume-fail"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    # A naive restart: every candidate recomputed in both passes.
    docs["resume_demo.json"] = {"pre_resume_statuses": ["MISS", "MISS"],
                                "post_resume_statuses": ["MISS", "MISS", "MISS"],
                                "total_misses": 5, "unique_candidates": 3}
    (root / "resume_demo.json").write_text(json.dumps(docs["resume_demo.json"]),
                                           encoding="utf-8")
    manifest = json.loads((root / "phase_manifest.json").read_text())
    for entry in manifest["artifacts"]:
        if entry["path"] == "resume_demo.json":
            entry["sha256"] = hashlib.sha256(
                (root / "resume_demo.json").read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = verify_fp02(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP02-G-RESUME"]["pass"]
