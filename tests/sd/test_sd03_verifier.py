"""Coverage for sd/verifier_sd03.py (guide SS10.5, G3-* gates) -- run
against the REAL committed 12-fold FINAL/D2/continuous-account artifacts.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from crypto_regime_lab.sd import verifier_sd03 as v3

LAB = Path(__file__).resolve().parents[2]


def _has_real_final() -> bool:
    return (LAB / "evidence" / "sharpe_decay_sd_v1" / "final_folds" / "fold_2024-03-23.json").exists()


pytestmark = pytest.mark.skipif(not _has_real_final(), reason="real SD-03 FINAL data not present")


def test_load_final_folds_finds_all_12():
    fold_records, final_origins = v3.load_final_folds(LAB)
    assert len(fold_records) == 12
    assert len(final_origins) == 12


def test_load_d2_finds_all_36():
    _, final_origins = v3.load_final_folds(LAB)
    d2_records = v3.load_d2(LAB, origins=final_origins)
    assert len(d2_records) == 36


def test_load_deployment_finds_all_3():
    deployment = v3.load_deployment(LAB)
    assert len(deployment) == 3
    assert set(deployment) == set(v3.ARMS)


def test_gate_exec_passes_on_real_data():
    fold_records, final_origins = v3.load_final_folds(LAB)
    deployment = v3.load_deployment(LAB)
    result = v3.gate_exec(fold_records, final_origins=final_origins, deployment=deployment)
    assert result["pass"] is True


def test_gate_exec_catches_missing_fold():
    fold_records, final_origins = v3.load_final_folds(LAB)
    truncated = dict(list(fold_records.items())[:11])
    deployment = v3.load_deployment(LAB)
    result = v3.gate_exec(truncated, final_origins=final_origins, deployment=deployment)
    assert result["pass"] is False


def test_gate_pair12_passes_on_real_data():
    fold_records, final_origins = v3.load_final_folds(LAB)
    d2_records = v3.load_d2(LAB, origins=final_origins)
    result = v3.gate_pair12(fold_records, d2_records=d2_records, final_origins=final_origins)
    assert result["pass"] is True


def test_gate_metric_passes_and_anchor_zero_not_vacuous():
    fold_records, _ = v3.load_final_folds(LAB)
    result = v3.gate_metric(fold_records)
    assert result["pass"] is True
    anchor_check = next(c for c in result["checks"] if c["name"] == "anchor_y_hat_zero_structurally")
    assert anchor_check["vacuous"] is False


def test_gate_metric_catches_old_return_field_injection():
    fold_records, _ = v3.load_final_folds(LAB)
    poisoned = copy.deepcopy(fold_records)
    first = next(iter(poisoned))
    poisoned[first]["D_mean_daily_return"] = 0.5
    result = v3.gate_metric(poisoned)
    assert result["pass"] is False


def test_gate_model_passes_and_b_anchor_check_not_vacuous():
    fold_records, _ = v3.load_final_folds(LAB)
    result = v3.gate_model(fold_records)
    assert result["pass"] is True
    b_anchor_check = next(c for c in result["checks"]
                          if c["name"] == "c_scored_even_when_b_falls_back_to_anchor")
    assert b_anchor_check["vacuous"] is False, "the real FINAL data must have >=1 genuine B-anchor fold"


def test_gate_evidence_passes_on_real_data():
    fold_records, final_origins = v3.load_final_folds(LAB)
    d2_records = v3.load_d2(LAB, origins=final_origins)
    deployment = v3.load_deployment(LAB)
    result = v3.gate_evidence(LAB, fold_records=fold_records, d2_records=d2_records, deployment=deployment)
    assert result["pass"] is True


def test_gate_close_passes_on_real_data():
    result = v3.gate_close(LAB)
    assert result["pass"] is True


def test_verify_sd03_end_to_end_real():
    result = v3.verify_sd03(lab_root=LAB)
    assert result["overall"] == "PASS"
    assert result["n_folds_found"] == 12
    assert result["n_d2_records"] == 36
    assert result["n_deployment_accounts"] == 3
    for gate_name in v3.REQUIRED_GATES:
        assert gate_name in result["gates"]
