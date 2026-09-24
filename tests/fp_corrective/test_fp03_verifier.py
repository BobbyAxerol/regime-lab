"""The FP-03 verifier fails on real failure shapes, per gate -- plus one
test proving a fully valid bundle passes (mirrors test_fp01/02_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp03 import REQUIRED_ARTIFACTS, verify_fp03

TEST_NODE_IDS = (
    "test_fp03_t_schema_mapping_matches_declared_bounds",
    "test_fp03_g_prefix_lower_checkpoint_is_a_true_prefix_of_higher",
)


def _junit(path: Path, *, tests: int = 13, failures: int = 0,
          nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp03_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _trial(i: int, obj: float) -> dict:
    return {"trial_id": i, "objective": obj, "pruned": False,
           "params": {"coeff": 1 + (i % 8), "AP": 5 + i, "alpha.condition_threshold": 30,
                      "novolumedata": False, "src_col": "close"}}


def _checkpoint(level: int, records: list[dict]) -> dict:
    prefix = records[:level]
    best = max(prefix, key=lambda r: r["objective"])
    return {
        "level": level, "status": "REACHED",
        "selected": {"trial_id": best["trial_id"], "params": best["params"],
                    "objective": best["objective"]},
        "coverage": {"declared_grid_size": 4928, "n_attempted": len(prefix),
                    "n_unique": len(prefix), "raw_coverage_fraction": len(prefix) / 4928,
                    "unique_coverage_fraction": len(prefix) / 4928,
                    "behavioral_objective_spread": 1.0},
        "search_classification": {"n_trials_attempted": len(prefix)},
        "estimated_wall_seconds": float(level),
    }


def _bundle(root: Path) -> dict:
    records = [_trial(i, float(i)) for i in range(64)]
    origins = {
        "schema": "regime_lab.fp03_origin_searches.v1",
        "origins": [{
            "origin_cutoff": "2023-06-01", "wf_ok": True, "wf_error": None,
            "trial_records": records,
            "checkpoints": [_checkpoint(32, records), _checkpoint(64, records)],
        }],
    }
    docs = {
        "schema_qualification.json": {
            "schema_mapping": [{"name": "coeff", "engine_mapping_consistent": True}],
            "unknown_value_rejections": [{"dimension": "coeff", "correctly_rejected": True}],
            "fixed_dimensions": [{"dimension": "src_col", "matches_declared": True,
                                  "engine_value_is_scalar": True}],
            "behavioral_fixtures": [{"dimension": "coeff", "outcome": "BEHAVIOR_DIFFERS"}],
        },
        "search_introspection.json": {"schema": "regime_lab.fp03_search_introspection.v1"},
        "origin_searches.json": origins,
        "forward_comparison.json": {"schema": "regime_lab.fp03_forward_comparison.v1",
                                    "origins": []},
        "search_policy.json": {
            "B_search": 64, "Q_probe": 0, "representative_subset_size": 16,
            "startup_exploration_policy": "x", "pruning_policy": "none", "seed_policy": "x",
            "frozen_at_utc": "2026-09-22T00:00:00+00:00",
        },
        "resource_budget.json": {"fp03_wall_seconds_charged_to_shared_ledger": 0},
        "test_registry.json": {"test_node_ids": list(TEST_NODE_IDS)},
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
    (root / "report.md").write_text("# FP-03\n", encoding="utf-8")
    (root / "handoff.md").write_text("# FP-03 handoff\n", encoding="utf-8")
    return docs


def test_fp03_verifier_passes_on_a_valid_bundle(lab_tmp):
    assert set(REQUIRED_ARTIFACTS) >= {"schema_qualification.json", "origin_searches.json",
                                       "forward_comparison.json", "search_policy.json"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp03(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp03_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp03(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp03_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "search_policy.json").write_text('{"B_search": "forged"}', encoding="utf-8")
    verdict = verify_fp03(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("search_policy.json" in r
              for g in verdict["gates"].values() for r in g["reasons"])


def test_fp03_verifier_fails_when_a_checkpoint_leaks_higher_budget_information(lab_tmp):
    """The real bug class this gate exists to catch, found while writing
    this very test: an earlier version of FP03-G-PREFIX compared
    records[:lo] to records[:hi][:lo] from the SAME single sorted list --
    mathematically identical by construction, so it could never fail no
    matter what the checkpoint summary claimed. Fixed to independently
    re-derive 'selected' from the raw prefix instead. This corrupts
    checkpoint 32's selected trial to one that only exists at trial_id 50
    (outside its own budget) and requires the fixed gate to catch it."""
    root = Path(str(lab_tmp)) / "broken-prefix"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    origins = docs["origin_searches.json"]["origins"][0]
    origins["checkpoints"][0]["selected"] = {"trial_id": 50, "params": {}, "objective": 999.0}
    (root / "origin_searches.json").write_text(json.dumps(docs["origin_searches.json"]),
                                                encoding="utf-8")
    manifest = json.loads((root / "phase_manifest.json").read_text())
    for entry in manifest["artifacts"]:
        if entry["path"] == "origin_searches.json":
            entry["sha256"] = hashlib.sha256(
                (root / "origin_searches.json").read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = verify_fp03(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP03-G-PREFIX"]["pass"]
    assert any("leaked" in r or "not the best-objective" in r
              for r in verdict["gates"]["FP03-G-PREFIX"]["reasons"])
