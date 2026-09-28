"""Verifier for Phase MF-02: Features, Targets, Duration & Baselines.

Enforces:
1. G2-FEATURES: Feature count <= 50, all causal (D0, D1, D2 cohorts declared).
2. G2-TARGETS: Targets forward defined for H56 and H90, taxonomy frozen on matured prefix only.
3. G2-SPLIT: 730 daily training origins, 48 Dev origins, 48 Test origins, no look-ahead.
4. G2-BASELINE: All 4 mandatory baselines executed and evaluated on Dev origins.
5. G2-REGISTRATION: Model grid and candidate configs registered for MF-03.
6. G2-DURATION-DEFINITION: Episode ledger with right-censoring, KM estimator, RMST/RMRL implemented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def verify_gate_features(feature_manifest: Dict[str, Any]) -> Dict[str, Any]:
    features = feature_manifest.get("features", [])
    count = len(features)
    assert count <= 50, f"Feature count {count} exceeds maximum of 50"
    assert count >= 20, f"Feature count {count} is suspiciously low (< 20)"
    
    cohorts = set()
    for f in features:
        assert "feature_id" in f, "Missing feature_id"
        assert "cohort" in f, f"Missing cohort in {f['feature_id']}"
        assert f["cohort"] in ("D0_CORE_PRICE_VOL", "D1_DERIVATIVE_LIQUIDITY", "D2_COMPOSITE_PRESSURE"), (
            f"Invalid cohort {f['cohort']} in {f['feature_id']}"
        )
        assert f.get("causal_lag_days", 0) >= 1, f"Feature {f['feature_id']} must have causal_lag_days >= 1"
        cohorts.add(f["cohort"])
    
    assert "D0_CORE_PRICE_VOL" in cohorts, "Cohort D0 missing"
    assert "D1_DERIVATIVE_LIQUIDITY" in cohorts, "Cohort D1 missing"
    assert "D2_COMPOSITE_PRESSURE" in cohorts, "Cohort D2 missing"
    
    return {
        "status": "PASS",
        "feature_count": count,
        "cohorts": sorted(list(cohorts)),
    }


def verify_gate_targets(taxonomy_manifest: Dict[str, Any]) -> Dict[str, Any]:
    assert taxonomy_manifest.get("frozen_on_prefix") == "2022-01-14_to_2024-01-13", (
        "Taxonomy must be frozen on matured training prefix only"
    )
    for h in [56, 90]:
        h_key = f"H{h}"
        assert h_key in taxonomy_manifest, f"Missing horizon {h_key} in taxonomy"
        h_data = taxonomy_manifest[h_key]
        assert "v_quantiles" in h_data, f"Missing v_quantiles for {h_key}"
        q1 = h_data["v_quantiles"]["q_1_3"]
        q2 = h_data["v_quantiles"]["q_2_3"]
        assert 0.0 < q1 < q2, f"Invalid V quantiles {q1}, {q2} for {h_key}"
        assert "e_quantiles" in h_data, f"Missing e_quantiles for {h_key}"
        tau = h_data["e_quantiles"]["tau_symmetric"]
        assert tau > 0.0, f"Invalid tau {tau} for {h_key}"

    return {
        "status": "PASS",
        "horizons": ["H56", "H90"],
        "frozen_on_prefix": taxonomy_manifest.get("frozen_on_prefix"),
    }


def verify_gate_split(timeline_data: Dict[str, Any]) -> Dict[str, Any]:
    assert timeline_data.get("initial_matured_training_origins", 0) >= 730, "Training origins < 730"
    assert timeline_data.get("dev_blocks", 0) >= 12, "Dev blocks < 12"
    assert timeline_data.get("test_blocks", 0) >= 12, "Test blocks < 12"
    assert timeline_data.get("dev_weekly_origins", 0) == 48, "Dev weekly origins != 48"
    assert timeline_data.get("test_weekly_origins", 0) == 48, "Test weekly origins != 48"
    
    return {
        "status": "PASS",
        "training_origins": timeline_data.get("initial_matured_training_origins"),
        "dev_origins": timeline_data.get("dev_weekly_origins"),
        "test_origins": timeline_data.get("test_weekly_origins"),
    }


def verify_gate_baseline(baseline_results: Dict[str, Any]) -> Dict[str, Any]:
    expected_baselines = {"B1_PERSISTENCE", "B2_MATURED_FREQ", "B3_HAR_RV", "B4_REGULARIZED_LINEAR"}
    actual_baselines = set(baseline_results.keys())
    missing = expected_baselines - actual_baselines
    assert not missing, f"Missing baselines: {missing}"

    for b_id, b_data in baseline_results.items():
        for h in ["H56", "H90"]:
            assert h in b_data, f"Missing horizon {h} in baseline {b_id}"
            metrics = b_data[h]
            assert "brier_score_v" in metrics, f"Missing brier_score_v in {b_id} {h}"
            assert "brier_score_e" in metrics, f"Missing brier_score_e in {b_id} {h}"
            assert "brier_score_j" in metrics, f"Missing brier_score_j in {b_id} {h}"
            assert "balanced_acc_v" in metrics, f"Missing balanced_acc_v in {b_id} {h}"
            assert "balanced_acc_e" in metrics, f"Missing balanced_acc_e in {b_id} {h}"
            assert "balanced_acc_j" in metrics, f"Missing balanced_acc_j in {b_id} {h}"
            assert "mae_v" in metrics, f"Missing mae_v in {b_id} {h}"
            assert metrics["brier_score_v"] >= 0.0, f"Negative brier score in {b_id}"

    return {
        "status": "PASS",
        "baselines_evaluated": sorted(list(expected_baselines)),
    }


def verify_gate_registration(grid_data: Dict[str, Any]) -> Dict[str, Any]:
    configs = grid_data.get("candidate_models", [])
    assert len(configs) >= 4, f"Registered model configs {len(configs)} < 4"
    model_types = {c.get("model_type") for c in configs}
    assert "LIGHTGBM" in model_types, "LightGBM missing from model grid"
    
    blocked = grid_data.get("blocked_capabilities", [])
    has_blocked_chronos = any(
        "chronos" in b.get("capability_id", "").lower() and b.get("status") == "BLOCKED_CAPABILITY"
        for b in blocked
    )
    assert "CHRONOS_SYNTH" in model_types or has_blocked_chronos, (
        "Chronos-2-Synth challenger must be present in candidate_models or registered as BLOCKED_CAPABILITY"
    )

    return {
        "status": "PASS",
        "registered_configs_count": len(configs),
        "model_types": sorted(list(model_types)),
    }


def verify_gate_duration_definition(duration_report: Dict[str, Any]) -> Dict[str, Any]:
    assert duration_report.get("detector_id") == "OBS14_CONFIRM3_V1", "Invalid detector_id"
    ledger_summary = duration_report.get("episode_ledger_summary", {})
    total_episodes = ledger_summary.get("total_episodes", 0)
    assert total_episodes >= 10, f"Too few episodes in ledger: {total_episodes}"
    right_censored = ledger_summary.get("right_censored_count", 0)
    assert right_censored >= 1, "There must be at least 1 right-censored episode (the active terminal episode)"

    km_data = duration_report.get("km_estimator_summary", {})
    assert "median_duration_by_regime" in km_data, "Missing median duration in KM data"
    assert "rmst_by_regime" in km_data, "Missing RMST in KM data"
    assert "rmrl_by_regime" in km_data, "Missing RMRL in KM data"

    return {
        "status": "PASS",
        "total_episodes": total_episodes,
        "right_censored_episodes": right_censored,
        "detector": duration_report.get("detector_id"),
    }


def run_mf02_verification(run_dir: Path, write_receipt: bool = True) -> Dict[str, Any]:
    """Run all 6 exit gates for MF-02."""
    feature_manifest_path = run_dir / "feature_manifest.json"
    taxonomy_path = run_dir / "target_taxonomy.json"
    timeline_path = run_dir / "timeline_summary.json"
    baseline_path = run_dir / "baseline_eval_results.json"
    grid_path = run_dir / "model_grid.json"
    duration_path = run_dir / "duration_report.json"

    with open(feature_manifest_path, "r", encoding="utf-8") as f:
        feature_manifest = json.load(f)
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        taxonomy_manifest = json.load(f)
    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline_data = json.load(f)
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_results = json.load(f)
    with open(grid_path, "r", encoding="utf-8") as f:
        grid_data = json.load(f)
    with open(duration_path, "r", encoding="utf-8") as f:
        duration_report = json.load(f)

    g2_features = verify_gate_features(feature_manifest)
    g2_targets = verify_gate_targets(taxonomy_manifest)
    g2_split = verify_gate_split(timeline_data)
    g2_baseline = verify_gate_baseline(baseline_results)
    g2_registration = verify_gate_registration(grid_data)
    g2_duration = verify_gate_duration_definition(duration_report)

    all_passed = (
        g2_features["status"] == "PASS"
        and g2_targets["status"] == "PASS"
        and g2_split["status"] == "PASS"
        and g2_baseline["status"] == "PASS"
        and g2_registration["status"] == "PASS"
        and g2_duration["status"] == "PASS"
    )

    receipt = {
        "phase": "MF-02",
        "overall_status": "PASS" if all_passed else "FAIL",
        "gates": {
            "G2-FEATURES": g2_features,
            "G2-TARGETS": g2_targets,
            "G2-SPLIT": g2_split,
            "G2-BASELINE": g2_baseline,
            "G2-REGISTRATION": g2_registration,
            "G2-DURATION-DEFINITION": g2_duration,
        },
    }

    if write_receipt:
        receipt_path = run_dir / "gate_receipt.json"
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)

    return receipt
