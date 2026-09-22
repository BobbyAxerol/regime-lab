"""The FP-04 verifier fails on real failure shapes, per gate -- plus one test
proving a fully valid bundle passes (mirrors test_fp01/02/03_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp04 import REQUIRED_ARTIFACTS, verify_fp04

TEST_NODE_IDS = (
    "test_fp04_t01_a_late_discovered_candidate_does_not_appear_in_a_past_origin",
    "test_fp04_t07_incremental_rebuild_only_calls_build_fn_for_new_origins",
)


def _junit(path: Path, *, tests: int = 30, failures: int = 0,
          nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp04_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


PARAMS = {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
         "novolumedata": False, "src_col": "close"}


def _trial(i: int, obj: float) -> dict:
    return {"trial_id": i, "objective": obj, "pruned": False,
           "params": {**PARAMS, "AP": 20 + i}}


def _region(region_id: str, member_ids: list[int], medoid_id: int) -> dict:
    return {
        "schema": "regime_lab.fp04_region.v1", "region_id": region_id,
        "member_candidate_ids": member_ids, "geometry_schema_name": "A-SC",
        "medoid_trial_id": medoid_id, "medoid_params": {**PARAMS, "AP": 20 + medoid_id},
        "is_quality_distribution": {"n": len(member_ids), "min": 0.0, "max": float(medoid_id),
                                    "mean": float(medoid_id) / 2},
        "probe_coverage": {"probes_run": 0, "reason": "Q_probe frozen at 0"},
        "behavioral_diversity_mean_pairwise_distance": 0.01,
        "historical_support_within_origin": len(member_ids),
        "historical_support_note": "within-origin only",
        "forward_utility_mean_daily_return": None, "decay_D_mean_daily_return": None,
    }


def _record(record_id: str, origin_cutoff: str, region_id: str, medoid_id: int, *,
           state: str, label, censored_reason=None, support: int = 3,
           horizon_days: int = 28) -> dict:
    import pandas as pd

    origin_ts = pd.Timestamp(origin_cutoff, tz="UTC")
    return {
        "schema": "regime_lab.fp04_ledger_record.v1", "record_id": record_id,
        # origin_cutoff is the PLAIN join key, matching the origin dict's own
        # field (fp/forward_ledger.py::ledger_record's real convention) --
        # origin_time carries the qualified timestamp.
        "origin_cutoff": origin_cutoff, "origin_time": origin_ts.isoformat(),
        "region_id": region_id, "medoid_trial_id": medoid_id, "params": {**PARAMS, "AP": 20 + medoid_id},
        "is_objective": float(medoid_id), "region_support_within_origin": support,
        "maturity_state": state, "label": label,
        "label_available_at": (origin_ts + pd.Timedelta(days=horizon_days)).isoformat(),
        "forward_metrics": None,
        "decay_D_mean_daily_return": None, "censored_reason": censored_reason,
        "geometry_version": "v0",
    }


def _bundle(root: Path) -> dict:
    records = [_trial(i, float(i)) for i in range(8)]
    origin = {
        "origin_cutoff": "2022-01-01", "wf_ok": True, "wf_error": None,
        "reused_from_cache": None, "seed": 1, "trials_requested": 8,
        "market_partitions_used": ["p1"], "load_start": "2021-07-01", "load_end": "2022-02-01",
        "frame_rows": 100, "trial_records": records,
        # trial 1 (AP=21) is the TRUE medoid of {AP=20,21,22}: total distance
        # 2/55, vs trial 0 or trial 2's 3/55 -- FP04-G-REGION recomputes this
        # for real from schema_distance.ParamSchema.distance, so the fixture
        # must use the actual medoid, not an arbitrary member.
        "regions": [_region("R00", [0, 1, 2], 1)],
    }
    ledger = {"schema": "regime_lab.fp04_origin_ledger.v1", "origins": [origin]}
    rec_matured = _record("2022-01-01:R00", "2022-01-01", "R00", 1, state="matured_forward_record",
                          label=0.001, support=3)
    records_doc = {
        "schema": "regime_lab.fp04_ledger_records.v1", "records": [rec_matured],
        "support_summary": {"model_ready_count": 1, "descriptive_only_count": 0,
                            "min_support_for_model_ready": 2},
    }
    region_policy = {
        "schema": "regime_lab.fp04_region_policy.v1", "alpha_id": "A-SC",
        "origin_grid": ["2022-01-01"], "forward_horizon_days": 28,
        "distance_threshold": 0.15, "max_representatives": 16,
    }
    docs = {
        "origin_ledger.json": ledger,
        "ledger_records.json": records_doc,
        "region_policy.json": region_policy,
        "resource_budget.json": {"engine_calls_search_trials_fresh": 8, "reused_origins": []},
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
    (root / "report.md").write_text("# FP-04\n", encoding="utf-8")
    (root / "handoff.md").write_text("# FP-04 handoff\n", encoding="utf-8")
    return docs


def _rewrite(root: Path, name: str, doc: dict, manifest: dict) -> None:
    (root / name).write_text(json.dumps(doc), encoding="utf-8")
    for entry in manifest["artifacts"]:
        if entry["path"] == name:
            entry["sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fp04_verifier_passes_on_a_valid_bundle(lab_tmp):
    assert set(REQUIRED_ARTIFACTS) >= {"origin_ledger.json", "ledger_records.json",
                                       "region_policy.json"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp04_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp04(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp04_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "region_policy.json").write_text('{"forged": true}', encoding="utf-8")
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("region_policy.json" in r for g in verdict["gates"].values() for r in g["reasons"])


def test_fp04_g_region_fails_when_stored_medoid_does_not_match_recomputation(lab_tmp):
    """The real bug class this gate exists to catch: a stored medoid_trial_id
    that does NOT minimise total distance among its own declared members.
    Corrupts the region's stored medoid to a member that is not the true
    medoid (trial 0, the lowest-AP outlier of the three) and requires the
    gate to catch it by recomputing from the SAME raw trial_records."""
    root = Path(str(lab_tmp)) / "bad-medoid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    ledger = docs["origin_ledger.json"]
    ledger["origins"][0]["regions"][0]["medoid_trial_id"] = 0
    _rewrite(root, "origin_ledger.json", ledger, docs["phase_manifest.json"])
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP04-G-REGION"]["pass"]
    assert any("does not match" in r for r in verdict["gates"]["FP04-G-REGION"]["reasons"])


def test_fp04_g_causal_fails_when_a_censored_record_carries_a_nonnull_label(lab_tmp):
    """Guide 7.1: 'Outcome thiếu không bằng zero.' A censored record whose
    label was set to 0.0 (the exact silent-zero failure mode the guide names)
    must be caught, re-derived from the record's OWN maturity_state field."""
    root = Path(str(lab_tmp)) / "censored-nonnull"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    records_doc = docs["ledger_records.json"]
    records_doc["records"].append(
        _record("2022-01-01:R01", "2022-01-01", "R01", 5, state="censored_or_failed_record",
               label=0.0, censored_reason="forward window empty"))
    records_doc["support_summary"]["descriptive_only_count"] = 1
    _rewrite(root, "ledger_records.json", records_doc, docs["phase_manifest.json"])
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP04-G-CAUSAL"]["pass"]
    assert any("non-null label" in r for r in verdict["gates"]["FP04-G-CAUSAL"]["reasons"])


def test_fp04_g_causal_fails_on_a_cross_origin_medoid_leak(lab_tmp):
    """FP04-T01's own gate-level check: a ledger record whose medoid_trial_id
    does not exist in ITS OWN origin's raw trial_records (e.g. it actually
    belongs to a later origin) must be caught."""
    root = Path(str(lab_tmp)) / "cross-origin-leak"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    records_doc = docs["ledger_records.json"]
    records_doc["records"][0]["medoid_trial_id"] = 999   # never in this origin's trial_records
    _rewrite(root, "ledger_records.json", records_doc, docs["phase_manifest.json"])
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP04-G-CAUSAL"]["pass"]
    assert any("cross-origin leak" in r for r in verdict["gates"]["FP04-G-CAUSAL"]["reasons"])


def test_fp04_g_support_fails_when_counts_disagree_with_a_fresh_recount(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-support"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    records_doc = docs["ledger_records.json"]
    records_doc["support_summary"]["model_ready_count"] = 999   # true recount is 1
    _rewrite(root, "ledger_records.json", records_doc, docs["phase_manifest.json"])
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP04-G-SUPPORT"]["pass"]
    assert any("disagrees with a fresh recount" in r
              for r in verdict["gates"]["FP04-G-SUPPORT"]["reasons"])


def test_fp04_g_reuse_fails_when_fresh_trial_count_disagrees_with_the_ledger(lab_tmp):
    """The real bug class: resource_budget.json claiming fewer (or more)
    fresh engine calls than origin_ledger.json's own non-reused origins
    actually spent -- would hide a phantom cache hit or a phantom re-run."""
    root = Path(str(lab_tmp)) / "bad-reuse"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    budget = docs["resource_budget.json"]
    budget["engine_calls_search_trials_fresh"] = 0   # true recount is 8 (one non-reused origin)
    _rewrite(root, "resource_budget.json", budget, docs["phase_manifest.json"])
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP04-G-REUSE"]["pass"]
    assert any("disagrees with a fresh recount" in r
              for r in verdict["gates"]["FP04-G-REUSE"]["reasons"])


def test_fp04_g_ledger_fails_when_an_origin_is_missing_from_the_frozen_grid(lab_tmp):
    root = Path(str(lab_tmp)) / "missing-origin"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    policy = docs["region_policy.json"]
    policy["origin_grid"] = ["2022-01-01", "2022-04-01"]   # ledger only has 2022-01-01
    _rewrite(root, "region_policy.json", policy, docs["phase_manifest.json"])
    verdict = verify_fp04(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP04-G-LEDGER"]["pass"]
