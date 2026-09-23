"""The FP-07 verifier fails on real failure shapes, per gate -- plus one
test proving a fully valid bundle passes (mirrors test_fp01..06_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp07 import REQUIRED_ARTIFACTS, verify_fp07

TEST_NODE_IDS = (
    "test_load_origin_wf_result_reads_the_real_fp04_cache",
    "test_walk_forward_b_selection_never_uses_a_later_origins_record",
    "test_paired_contrast_c_minus_b_sign_and_status",
)

ORIGINS = ("2021-01-01", "2021-04-01")


def _junit(path: Path, *, tests: int = 20, failures: int = 0, nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp07_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _bundle(root: Path) -> dict:
    docs = {
        "study_freeze.json": {
            "schema": "regime_lab.fp07_study_freeze.v1",
            "primary_cell": {"alpha_id": "A-SC", "symbol": "BTCUSDT"},
            "origins": list(ORIGINS),
            "frame_span": {"start": "2021-01-01", "end": "2021-04-10"},
            "cost_estimate": {"pilot_bars_per_second": 6979.0,
                              "estimated_minutes_per_arm": 3.55,
                              "estimated_total_minutes": 10.7},
            "frozen_at_utc": "2026-09-23T00:00:00+00:00",
        },
        "common_candidate_pools.json": {
            "schema": "regime_lab.fp07_common_candidate_pools.v1",
            "shared_across_arms": True,
            "record_ids_by_origin": {
                "2021-01-01": [{"record_id": "2021-01-01:R00"}, {"record_id": "2021-01-01:R01"}],
                "2021-04-01": [{"record_id": "2021-04-01:R00"}, {"record_id": "2021-04-01:R01"}],
            },
        },
        "selections.json": {
            "schema": "regime_lab.fp07_selections.v1",
            "by_origin": {
                "2021-01-01": {
                    "A_STOCK_CAL": {"params": {"coeff": 3}},
                    "B_FP_PERSISTENCE": {"source": "FALLBACK_TO_A", "params": None, "record_id": None},
                    "C_FP_CONTEXT": {"source": "FALLBACK_TO_A", "params": None, "record_id": None},
                },
                "2021-04-01": {
                    "A_STOCK_CAL": {"params": {"coeff": 5}},
                    "B_FP_PERSISTENCE": {"source": "B_SELECTED", "params": {"coeff": 4},
                                         "record_id": "2021-04-01:R00"},
                    "C_FP_CONTEXT": {"source": "CONTEXT_CONDITIONED", "params": {"coeff": 6},
                                     "record_id": "2021-04-01:R01"},
                },
            },
        },
        "admission_and_schedules.json": {
            "schema": "regime_lab.fp07_admission_and_schedules.v1",
            "by_arm": {
                "A_STOCK_CAL": {"lineage": {"0": {"decision": "ADMIT"}, "1": {"decision": "ADMIT"}}},
                "B_FP_PERSISTENCE": {"lineage": {"0": {"decision": "COMMON_FLAT_FALLBACK"},
                                                 "1": {"decision": "ADMIT"}}},
                "C_FP_CONTEXT": {"lineage": {"0": {"decision": "COMMON_FLAT_FALLBACK"},
                                             "1": {"decision": "ADMIT"}}},
            },
        },
        "accounts.json": {
            "schema": "regime_lab.fp07_accounts.v1",
            "frame_bars": 144000, "shared_initial_capital": 20000.0,
            "by_arm": {
                arm: {"status": "OK", "fill_count": 12, "bars": 144000,
                     "daily_returns_start": "2021-01-01", "daily_returns_end": "2021-04-10",
                     "daily_return_days": 99, "initial_capital": 20000.0}
                for arm in ("A_STOCK_CAL", "B_FP_PERSISTENCE", "C_FP_CONTEXT")
            },
        },
        "d1_table.json": {
            "schema": "regime_lab.fp07_d1_table.v1",
            "convention": "D = IS - forward; positive = worse decay (guide 8.5, FP-01 repaired)",
            "rows": [
                {"arm": "B_FP_PERSISTENCE", "origin_cutoff": "2021-01-01",
                 "is_mean_daily_return": None, "forward_label": None,
                 "D_mean_daily_return": None,
                 "reason": "FALLBACK_TO_A: no B-specific selection at this origin"},
                {"arm": "B_FP_PERSISTENCE", "origin_cutoff": "2021-04-01",
                 "is_mean_daily_return": 0.0010, "forward_label": 0.0006,
                 "D_mean_daily_return": 0.0004, "reason": None},
                {"arm": "C_FP_CONTEXT", "origin_cutoff": "2021-04-01",
                 "is_mean_daily_return": 0.0012, "forward_label": 0.0009,
                 "D_mean_daily_return": 0.0003, "reason": None},
            ],
        },
        "paired_contrasts.json": {
            "schema": "regime_lab.fp07_paired_contrasts.v1",
            "primary": {"label": "C_FP_CONTEXT - B_FP_PERSISTENCE", "status": "ESTIMATED",
                       "estimate": 0.00005},
            "secondary": {
                "B_FP_PERSISTENCE - A_STOCK_CAL": {"status": "ESTIMATED", "estimate": 0.00002},
                "C_FP_CONTEXT - A_STOCK_CAL": {"status": "ESTIMATED", "estimate": 0.00007},
            },
        },
        "resource_budget.json": {
            "schema": "regime_lab.fp07_resource_budget.v1",
            "resource_limits_applied": {"rlimit_as_gib": 4},
            "measured": {"peak_rss_mib": 500.0, "total_wall_seconds": 700.0},
        },
        "test_registry.json": {"schema": "regime_lab.fp07_test_registry.v1",
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
        "# FP-07\n\nPrimary contrast C_FP_CONTEXT - B_FP_PERSISTENCE estimated.\n\n"
        "Any verdict needs FP-08 replication before it can be trusted.\n\n"
        "## Permitted conclusions\n- Technical: ok\n- Research: NOT_ASSESSED\n",
        encoding="utf-8")
    (root / "handoff.md").write_text("# FP-07 handoff\n", encoding="utf-8")
    return docs


def _rewrite(root: Path, name: str, doc: dict, manifest: dict) -> None:
    (root / name).write_text(json.dumps(doc), encoding="utf-8")
    for entry in manifest["artifacts"]:
        if entry["path"] == name:
            entry["sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fp07_verifier_passes_on_a_valid_bundle(lab_tmp):
    assert set(REQUIRED_ARTIFACTS) >= {"study_freeze.json", "d1_table.json", "paired_contrasts.json"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp07_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp07(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp07_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "d1_table.json").write_text('{"forged": true}', encoding="utf-8")
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("d1_table.json" in r for g in verdict["gates"].values() for r in g["reasons"])


def test_fp07_g_pool_fails_when_a_selection_record_id_is_not_in_the_shared_pool(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-pool"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    selections = docs["selections.json"]
    selections["by_origin"]["2021-04-01"]["B_FP_PERSISTENCE"]["record_id"] = "2021-04-01:R99"
    _rewrite(root, "selections.json", selections, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-POOL"]["pass"]
    assert any("not found in that origin's own shared pool" in r
              for r in verdict["gates"]["FP07-G-POOL"]["reasons"])


def test_fp07_g_exec_fails_when_an_arm_has_zero_fills(lab_tmp):
    """The real bug class this lab keeps finding: a gate that passes because
    an arm's run was empty (LAB-06/07's own recorded lesson)."""
    root = Path(str(lab_tmp)) / "empty-arm"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    accounts = docs["accounts.json"]
    accounts["by_arm"]["C_FP_CONTEXT"]["fill_count"] = 0
    _rewrite(root, "accounts.json", accounts, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-EXEC"]["pass"]
    assert any("zero fills" in r for r in verdict["gates"]["FP07-G-EXEC"]["reasons"])


def test_fp07_g_account_fails_when_arms_do_not_share_a_common_calendar(lab_tmp):
    root = Path(str(lab_tmp)) / "mismatched-calendar"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    accounts = docs["accounts.json"]
    accounts["by_arm"]["A_STOCK_CAL"]["daily_returns_end"] = "2021-05-01"
    _rewrite(root, "accounts.json", accounts, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-ACCOUNT"]["pass"]
    assert any("common daily-return end" in r for r in verdict["gates"]["FP07-G-ACCOUNT"]["reasons"])


def test_fp07_g_decay_fails_when_stored_d1_does_not_match_is_minus_forward(lab_tmp):
    root = Path(str(lab_tmp)) / "bad-d1"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    d1 = docs["d1_table.json"]
    d1["rows"][1]["D_mean_daily_return"] = 0.999
    _rewrite(root, "d1_table.json", d1, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-DECAY"]["pass"]
    assert any("recomputed from the raw stored values" in r
              for r in verdict["gates"]["FP07-G-DECAY"]["reasons"])


def test_fp07_g_decay_fails_on_a_fabricated_number_for_a_fallback_origin(lab_tmp):
    """A fallback origin (no real forward-labelled record) must stay null
    with a reason -- never a fabricated D1, guide's own 'null means visibly
    missing information' contract."""
    root = Path(str(lab_tmp)) / "fabricated-fallback-d1"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    d1 = docs["d1_table.json"]
    d1["rows"][0]["D_mean_daily_return"] = 0.0001   # fabricated: is/forward are still null
    _rewrite(root, "d1_table.json", d1, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-DECAY"]["pass"]
    assert any("inputs are missing" in r for r in verdict["gates"]["FP07-G-DECAY"]["reasons"])


def test_fp07_g_cost_fails_when_peak_memory_exceeds_the_registered_budget(lab_tmp):
    root = Path(str(lab_tmp)) / "over-budget"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    budget = docs["resource_budget.json"]
    budget["measured"]["peak_rss_mib"] = 999999.0
    _rewrite(root, "resource_budget.json", budget, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-COST"]["pass"]
    assert any("exceeds the" in r for r in verdict["gates"]["FP07-G-COST"]["reasons"])


def test_fp07_g_cost_fails_when_no_pre_registered_cost_estimate_exists(lab_tmp):
    root = Path(str(lab_tmp)) / "no-estimate"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    freeze = docs["study_freeze.json"]
    del freeze["cost_estimate"]
    _rewrite(root, "study_freeze.json", freeze, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-COST"]["pass"]
    assert any("no pre-registered cost_estimate" in r for r in verdict["gates"]["FP07-G-COST"]["reasons"])


def test_fp07_g_cost_fails_when_a_budget_exception_is_applied_but_not_disclosed(lab_tmp):
    """A real bug class this lab's own history keeps finding: a budget cap
    silently raised at runtime with no matching disclosed decision record."""
    root = Path(str(lab_tmp)) / "silent-exception"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    budget = docs["resource_budget.json"]
    budget["resource_limits_applied"] = {"rlimit_as_gib": 7.0, "exception_applied": True,
                                         "exception_decision_id": None}
    _rewrite(root, "resource_budget.json", budget, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-COST"]["pass"]
    assert any("must never be silent" in r for r in verdict["gates"]["FP07-G-COST"]["reasons"])


def test_fp07_g_cost_fails_when_the_exception_decision_id_does_not_match_the_freeze_disclosure(lab_tmp):
    root = Path(str(lab_tmp)) / "mismatched-exception"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    budget = docs["resource_budget.json"]
    budget["resource_limits_applied"] = {"rlimit_as_gib": 7.0, "exception_applied": True,
                                         "exception_decision_id": "dec-real-one"}
    _rewrite(root, "resource_budget.json", budget, docs["phase_manifest.json"])
    freeze = docs["study_freeze.json"]
    freeze["resource_budget_exception"] = {"decision_id": "dec-different-one",
                                           "applied_working_memory_gib": 7.0}
    _rewrite(root, "study_freeze.json", freeze, docs["phase_manifest.json"])
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-COST"]["pass"]
    assert any("does not match" in r for r in verdict["gates"]["FP07-G-COST"]["reasons"])


def test_fp07_g_scope_fails_when_the_report_never_names_fp08(lab_tmp):
    root = Path(str(lab_tmp)) / "no-fp08"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text(
        "# FP-07\n\nPrimary contrast estimated.\n\n"
        "## Permitted conclusions\n- Technical: ok\n- Research: NOT_ASSESSED\n",
        encoding="utf-8")
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-SCOPE"]["pass"]
    assert any("FP-08" in r for r in verdict["gates"]["FP07-G-SCOPE"]["reasons"])


def test_fp07_g_scope_fails_on_a_forbidden_overclaim_phrase(lab_tmp):
    root = Path(str(lab_tmp)) / "overclaim"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text(
        "# FP-07\n\nThis run proves the edge and needs FP-08 to replicate.\n\n"
        "## Permitted conclusions\n- Technical: ok\n- Research: NOT_ASSESSED\n",
        encoding="utf-8")
    verdict = verify_fp07(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP07-G-SCOPE"]["pass"]
    assert any("forbidden overclaim phrase" in r for r in verdict["gates"]["FP07-G-SCOPE"]["reasons"])
