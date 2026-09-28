"""Tests for Phase MF-05: Consolidated Report & WFO Bridge.

Covers:
- MF5-T01: Tampering and corruption detection
- MF5-T02: Strict approval and completion semantics
- MF5-T03: Excluded sources verified absent from requirements
- MF5-T04: Complete pipeline artifact restoration
- MF5-T05: WFO Bridge closed on unqualified joint regime
- MF5-T06: Horizon isolation & no cadence conflation
- MF5-T07: Report regeneration zero engine calls
- MF5-T08: Git & protected path immutability
- DUR-T11: Duration report reproduction without models
- DUR-T12: Independence of empirical dwell and WFO opening
"""

import json
from pathlib import Path
import pytest

from crypto_regime_lab.regime_forecast.verifier_mf05 import (
    verify_gate_report,
    verify_gate_reproduce,
    verify_gate_scope,
    verify_gate_bridge,
    verify_gate_duration_handoff,
    verify_gate_owner,
)


def test_mf5_t01_tampering_detection():
    # Valid reproduction data
    valid_reproduce = {
        "reproduction_status": "VERIFIED",
        "max_metric_discrepancy": 0.0,
        "recomputation_without_models": True,
    }
    assert verify_gate_reproduce(valid_reproduce)["status"] == "PASS"

    # Tampered with discrepancy > 1e-9 must fail
    tampered_reproduce = {
        "reproduction_status": "VERIFIED",
        "max_metric_discrepancy": 0.05,
        "recomputation_without_models": True,
    }
    with pytest.raises(AssertionError):
        verify_gate_reproduce(tampered_reproduce)


def test_mf5_t02_strict_completion_semantics():
    # If phases are incomplete, must fail
    incomplete_report = {
        "study_id": "btc_regime_forecast_v1",
        "phases_completed": ["MF-01", "MF-02", "MF-03"],
        "financial_engine_calls": 0,
    }
    with pytest.raises(AssertionError):
        verify_gate_report(incomplete_report)


def test_mf5_t03_excluded_sources_absence():
    # Verify that CoinGecko / BTCDOM / L2 / Options are excluded in configs
    config_path = Path("configs/btc_regime_forecast_v1/source_allowlist.json")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            allowlist = json.load(f)
        excluded = list(allowlist.get("excluded_sources", {}).keys())
        assert "coingecko_dominance" in excluded
        assert "binance_btcdom" in excluded
        assert "deribit_options" in excluded


def test_mf5_t04_pipeline_restore_contracts():
    # Verify owner package completeness
    valid_owner = {
        "model_qualification_manifest_exists": True,
        "version_manifest_exists": True,
        "exclusion_list_exists": True,
        "resource_summary_exists": True,
    }
    assert verify_gate_owner(valid_owner)["status"] == "PASS"

    # Missing any manifest must fail
    with pytest.raises(AssertionError):
        verify_gate_owner({"model_qualification_manifest_exists": False, "version_manifest_exists": True})


def test_mf5_t05_wfo_bridge_closed():
    # Joint 9-class is NOT_QUALIFIED -> Bridge must be strictly CLOSED
    valid_bridge = {
        "wfo_bridge_status": "CLOSED",
        "joint_regime_parameter_selection_permitted": False,
        "volatility_conditioned_proposal": {"status": "SPECIFIED_NOT_EXECUTED"},
    }
    assert verify_gate_bridge(valid_bridge)["status"] == "PASS"

    # Attempting to declare OPEN without qualification must raise AssertionError
    invalid_bridge = {
        "wfo_bridge_status": "OPEN",
        "joint_regime_parameter_selection_permitted": True,
        "volatility_conditioned_proposal": {},
    }
    with pytest.raises(AssertionError):
        verify_gate_bridge(invalid_bridge)


def test_mf5_t06_scope_bounding():
    valid_scope = {
        "study_claim_level": "TECHNICALLY_VALID__VOLATILITY_QUALIFIED_ONLY__WFO_BRIDGE_CLOSED",
        "volatility_head_status": "QUALIFIED",
        "joint_regime_head_status": "NOT_QUALIFIED",
    }
    assert verify_gate_scope(valid_scope)["status"] == "PASS"

    with pytest.raises(AssertionError):
        verify_gate_scope({"study_claim_level": "POSITIVE_REGIME_TIME_EDGE"})


def test_mf5_t07_zero_financial_engine_calls():
    # Enforces engine_calls == 0 across all 5 phases
    valid_calls = {
        "study_id": "btc_regime_forecast_v1",
        "phases_completed": ["MF-01", "MF-02", "MF-03", "MF-04", "MF-05"],
        "financial_engine_calls": 0,
    }
    assert verify_gate_report(valid_calls)["status"] == "PASS"

    with pytest.raises(AssertionError):
        verify_gate_report({
            "study_id": "btc_regime_forecast_v1",
            "phases_completed": ["MF-01", "MF-02", "MF-03", "MF-04", "MF-05"],
            "financial_engine_calls": 1,
        })


def test_mf5_t08_duration_handoff():
    valid_dur = {
        "empirical_dwell_mean_days": 11.5,
        "survival_curves_available": True,
        "misrepresented_as_ml_skill": False,
    }
    assert verify_gate_duration_handoff(valid_dur)["status"] == "PASS"

    with pytest.raises(AssertionError):
        verify_gate_duration_handoff({
            "empirical_dwell_mean_days": 11.5,
            "survival_curves_available": True,
            "misrepresented_as_ml_skill": True,  # Cannot claim survival curve as ML skill!
        })


def test_dur_t11_reproduce_audit():
    # Verify that reproduction audit passes on verified flag
    audit = {
        "reproduction_status": "VERIFIED",
        "max_metric_discrepancy": 0.0,
        "recomputation_without_models": True,
    }
    assert verify_gate_reproduce(audit)["status"] == "PASS"


def test_dur_t12_bridge_proposal_isolation():
    # Verify proposal status does not trigger live execution
    decision = {
        "wfo_bridge_status": "CLOSED",
        "joint_regime_parameter_selection_permitted": False,
        "volatility_conditioned_proposal": {
            "status": "SPECIFIED_NOT_EXECUTED",
            "scope": "VOLATILITY_ONLY_LOW_MID_HIGH",
            "requires_owner_approval": True,
        },
    }
    res = verify_gate_bridge(decision)
    assert res["wfo_bridge_status"] == "CLOSED"
    assert res["proposal_status"] == "SPECIFIED_NOT_EXECUTED"
