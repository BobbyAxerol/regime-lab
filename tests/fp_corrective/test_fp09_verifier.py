"""The FP-09 verifier fails on real failure shapes, per gate -- plus one
test proving a fully valid bundle passes (mirrors test_fp01..08_verifier.py).
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from crypto_regime_lab.fp.verifier_fp09 import PRIMARY_LABEL, REQUIRED_ARTIFACTS, verify_fp09

TEST_NODE_IDS = (
    "test_rolling_volatility_ratio_is_causal",
    "test_derive_regime_timing_schedule_finds_first_bar_at_or_below_threshold",
    "test_derive_cal_matched_schedule_applies_the_same_deferral_count",
)

REPORT_TEXT = (
    "# FP-09\n\n"
    "Scope: **COMPLETED**\n\n"
    "3 admission events (n=3) at this single cell -- a small, disclosed sample.\n\n"
    "Primary contrast SELECTOR_REGIME_TIMING - SELECTOR_CAL_MATCHED estimated.\n\n"
    "## Permitted conclusions\n- Technical: ok\n- Research: NOT_ASSESSED\n"
)


def _junit(path: Path, *, tests: int = 20, failures: int = 0, nodes: tuple = TEST_NODE_IDS) -> None:
    cases = "".join(
        f'<testcase classname="tests.fp_corrective.test_fp09_x" name="{n}"/>' for n in nodes)
    root = ET.Element("testsuite", {"tests": str(tests), "failures": str(failures),
                                    "errors": "0", "skipped": "0"})
    for child in ET.fromstring(f"<wrap>{cases}</wrap>"):
        root.append(child)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _bundle(root: Path) -> dict:
    docs = {
        "study_freeze.json": {
            "schema": "regime_lab.fp09_study_freeze.v1",
            "primary_cell": {"alpha_id": "A-SC", "symbol": "BTCUSDT"},
            "timing_design": {"vol_threshold": 1.0, "k_max_bars": 43200,
                              "vol_short_days": 30, "vol_long_days": 180,
                              "cal_matched_seed": 20260924},
            "frozen_at_utc": "2026-09-24T00:00:00+00:00",
        },
        "schedules.json": {
            "schema": "regime_lab.fp09_schedules.v1",
            "SELECTOR_FIXED_CAL": [
                {"activation_id": "a@2021-04-01", "params": {"coeff": 4}, "requested_at_bar": 100},
                {"activation_id": "a@2022-01-01", "params": {"coeff": 5}, "requested_at_bar": 5000},
            ],
            "SELECTOR_REGIME_TIMING": [
                {"activation_id": "a@2021-04-01", "params": {"coeff": 4}, "requested_at_bar": 130},
                {"activation_id": "a@2022-01-01", "params": {"coeff": 5}, "requested_at_bar": 5000},
            ],
            "SELECTOR_CAL_MATCHED": [
                {"activation_id": "a@2021-04-01", "params": {"coeff": 4}, "requested_at_bar": 117},
                {"activation_id": "a@2022-01-01", "params": {"coeff": 5}, "requested_at_bar": 5040},
            ],
            "regime_timing_diagnostics": [
                {"activation_id": "a@2021-04-01", "origin_bar": 100, "activation_bar": 130,
                 "deferred_bars": 30, "hit_threshold": True},
                {"activation_id": "a@2022-01-01", "origin_bar": 5000, "activation_bar": 5000,
                 "deferred_bars": 0, "hit_threshold": True},
            ],
            "cal_matched_diagnostics": [
                {"activation_id": "a@2021-04-01", "origin_bar": 100, "activation_bar": 117,
                 "deferred_bars": 17},
                {"activation_id": "a@2022-01-01", "origin_bar": 5000, "activation_bar": 5040,
                 "deferred_bars": 40},
            ],
            "cal_matched_derivation": "drawn from Uniform(0, k_max_bars) with fixed seed=20260924, "
                                      "no market data consulted",
        },
        "accounts.json": {
            "schema": "regime_lab.fp09_accounts.v1",
            "frame_bars": 144000, "shared_initial_capital": 20000.0,
            "by_arm": {
                arm: {"status": "OK", "fill_count": 12, "bars": 144000}
                for arm in ("SELECTOR_FIXED_CAL", "SELECTOR_CAL_MATCHED", "SELECTOR_REGIME_TIMING")
            },
        },
        "paired_contrasts.json": {
            "schema": "regime_lab.fp09_paired_contrasts.v1",
            "primary": {"label": PRIMARY_LABEL, "status": "ESTIMATED", "estimate": 0.00001},
        },
        "resource_budget.json": {
            "schema": "regime_lab.fp09_resource_budget.v1",
            "resource_limits_applied": {"rlimit_as_gib": 7},
            "measured": {"peak_rss_mib": 3000.0, "total_wall_seconds": 500.0},
        },
        "test_registry.json": {"schema": "regime_lab.fp09_test_registry.v1",
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
    (root / "report.md").write_text(REPORT_TEXT, encoding="utf-8")
    (root / "handoff.md").write_text("# FP-09 handoff\n", encoding="utf-8")
    return docs


def _rewrite(root: Path, name: str, doc: dict, manifest: dict) -> None:
    (root / name).write_text(json.dumps(doc), encoding="utf-8")
    for entry in manifest["artifacts"]:
        if entry["path"] == name:
            entry["sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "phase_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fp09_verifier_passes_on_a_valid_bundle(lab_tmp):
    assert set(REQUIRED_ARTIFACTS) >= {"study_freeze.json", "schedules.json", "paired_contrasts.json"}
    root = Path(str(lab_tmp)) / "valid"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "PASS", verdict
    assert all(g["pass"] for g in verdict["gates"].values())


def test_fp09_verifier_fails_on_empty_dir(lab_tmp):
    root = Path(str(lab_tmp)) / "empty"
    root.mkdir()
    verdict = verify_fp09(root, pytest_xml=None)
    assert verdict["overall"] == "FAIL"
    assert verdict["missing_artifacts"]


def test_fp09_verifier_fails_on_tampered_artifact(lab_tmp):
    root = Path(str(lab_tmp)) / "tampered"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "schedules.json").write_text('{"forged": true}', encoding="utf-8")
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert any("schedules.json" in r for g in verdict["gates"].values() for r in g["reasons"])


def test_fp09_g_calibration_fails_when_cal_matched_is_identical_to_regime_timing(lab_tmp):
    """The exact structural defect this phase caught in itself: a CAL_MATCHED schedule built
    FROM REGIME_TIMING's own realized deferral is mathematically guaranteed to reproduce it
    exactly -- not an independent control. The gate must catch that shape."""
    root = Path(str(lab_tmp)) / "degenerate-copy"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    schedules = docs["schedules.json"]
    schedules["SELECTOR_CAL_MATCHED"] = [dict(e) for e in schedules["SELECTOR_REGIME_TIMING"]]
    _rewrite(root, "schedules.json", schedules, docs["phase_manifest.json"])
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-CALIBRATION"]["pass"]


def test_fp09_g_calibration_fails_when_the_derivation_note_references_returns(lab_tmp):
    root = Path(str(lab_tmp)) / "leaky-note"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    schedules = docs["schedules.json"]
    schedules["cal_matched_derivation"] = "matched to REGIME_TIMING's realized daily_return"
    _rewrite(root, "schedules.json", schedules, docs["phase_manifest.json"])
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-CALIBRATION"]["pass"]


def test_fp09_g_budget_fails_when_an_event_exceeds_k_max_bars(lab_tmp):
    root = Path(str(lab_tmp)) / "over-budget"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    schedules = docs["schedules.json"]
    schedules["SELECTOR_REGIME_TIMING"][0]["requested_at_bar"] = 100 + 999999
    schedules["SELECTOR_CAL_MATCHED"][0]["requested_at_bar"] = 100 + 999999
    schedules["regime_timing_diagnostics"][0]["deferred_bars"] = 999999
    _rewrite(root, "schedules.json", schedules, docs["phase_manifest.json"])
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-BUDGET"]["pass"]


def test_fp09_g_exec_fails_when_every_event_has_zero_deferral(lab_tmp):
    root = Path(str(lab_tmp)) / "vacuous-timing"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    schedules = docs["schedules.json"]
    for entry in schedules["SELECTOR_REGIME_TIMING"]:
        entry["requested_at_bar"] = schedules["SELECTOR_FIXED_CAL"][
            [e["activation_id"] for e in schedules["SELECTOR_FIXED_CAL"]].index(entry["activation_id"])
        ]["requested_at_bar"]
    for entry in schedules["SELECTOR_CAL_MATCHED"]:
        entry["requested_at_bar"] = schedules["SELECTOR_FIXED_CAL"][
            [e["activation_id"] for e in schedules["SELECTOR_FIXED_CAL"]].index(entry["activation_id"])
        ]["requested_at_bar"]
    for d in schedules["regime_timing_diagnostics"]:
        d["deferred_bars"] = 0
    _rewrite(root, "schedules.json", schedules, docs["phase_manifest.json"])
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-EXEC"]["pass"]


def test_fp09_g_exec_fails_when_an_arm_has_zero_fills(lab_tmp):
    root = Path(str(lab_tmp)) / "empty-account"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    accounts = docs["accounts.json"]
    accounts["by_arm"]["SELECTOR_REGIME_TIMING"]["fill_count"] = 0
    _rewrite(root, "accounts.json", accounts, docs["phase_manifest.json"])
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-EXEC"]["pass"]


def test_fp09_g_contrast_fails_on_an_indirect_proxy_label(lab_tmp):
    root = Path(str(lab_tmp)) / "wrong-contrast"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    docs = _bundle(root)
    contrasts = docs["paired_contrasts.json"]
    contrasts["primary"]["label"] = "SELECTOR_REGIME_TIMING - SELECTOR_FIXED_CAL"
    _rewrite(root, "paired_contrasts.json", contrasts, docs["phase_manifest.json"])
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-CONTRAST"]["pass"]


def test_fp09_g_scope_fails_without_an_explicit_scope_label(lab_tmp):
    root = Path(str(lab_tmp)) / "no-scope"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text(
        "# FP-09\n\nPrimary contrast SELECTOR_REGIME_TIMING - SELECTOR_CAL_MATCHED estimated.\n\n"
        "## Permitted conclusions\n- Technical: ok\n", encoding="utf-8")
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-SCOPE"]["pass"]


def test_fp09_g_scope_fails_on_an_unearned_cadence_artifact_conclusion(lab_tmp):
    root = Path(str(lab_tmp)) / "cadence-overclaim"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text(
        "# FP-09\n\nScope: **COMPLETED**\n\n3 admission events (n=3).\n\n"
        "Verdict: CADENCE_ARTIFACT, the placebo beat the slow calendar.\n\n"
        "## Permitted conclusions\n- Technical: ok\n", encoding="utf-8")
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-SCOPE"]["pass"]


def test_fp09_g_scope_fails_on_a_forbidden_overclaim_phrase(lab_tmp):
    root = Path(str(lab_tmp)) / "overclaim"
    root.mkdir()
    xml = root / "junit.xml"
    _junit(xml)
    _bundle(root)
    (root / "report.md").write_text(REPORT_TEXT + "\nThis confirms the edge.\n", encoding="utf-8")
    verdict = verify_fp09(root, pytest_xml=xml)
    assert verdict["overall"] == "FAIL"
    assert not verdict["gates"]["FP09-G-SCOPE"]["pass"]
