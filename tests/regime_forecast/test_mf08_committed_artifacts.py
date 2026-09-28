import pytest
import shutil
import json
from pathlib import Path

from crypto_regime_lab.regime_forecast import (
    verifier_mf01,
    verifier_mf02,
    verifier_mf03,
    verifier_mf04,
    verifier_mf05,
)

LAB_ROOT = Path("/root/bobby/pool_alpha/lab_regime_model_quantbt")
RUNS_DIR = LAB_ROOT / "evidence/btc_regime_forecast_v1/runs"

def test_mf01_verifier_on_committed_run_and_tampered_bundle(lab_tmp):
    # Committed run
    d = RUNS_DIR / "mf01-20260928T122818Z-64bb6ac4"
    res = verifier_mf01.verify_mf01(LAB_ROOT, run_dir=d)
    assert res["overall"] == "PASS"

    # Tampered run: corrupted coverage below threshold
    copied = lab_tmp / "tampered_mf01"
    shutil.copytree(d, copied)
    cov_path = copied / "coverage_summary.json"
    with open(cov_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["min_column_coverage_training"] = 0.50
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    res_tampered = verifier_mf01.verify_gate_g1_coverage(cov_path)
    assert res_tampered["pass"] is False, "Corrupted coverage must fail G1-COVERAGE"


def test_mf02_verifier_on_committed_run_and_tampered_bundle(lab_tmp):
    d = RUNS_DIR / "mf02-20260928T124051Z-1c4ebe49"
    res = verifier_mf02.run_mf02_verification(d, write_receipt=False)
    assert res["overall_status"] == "PASS"

    # Tampered bundle: mutate baseline results
    copied = lab_tmp / "tampered_mf02"
    shutil.copytree(d, copied)
    summary_path = copied / "baseline_eval_results.json"
    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Corrupt baseline results by removing required baseline B1_PERSISTENCE
    del data["B1_PERSISTENCE"]
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(AssertionError):
        verifier_mf02.run_mf02_verification(copied, write_receipt=False)


def test_mf03_verifier_on_committed_run_and_tampered_bundle(lab_tmp):
    d = RUNS_DIR / "mf03-20260928T124620Z-c404799d"
    res = verifier_mf03.run_mf03_verification(d, write_receipt=False)
    assert res["overall_status"] == "PASS"

    # Tampered bundle: mutate calibration method
    copied = lab_tmp / "tampered_mf03"
    shutil.copytree(d, copied)
    cal_path = copied / "calibration_summary.json"
    with open(cal_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["method"] = "INVALID_METHOD"
    with open(cal_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(AssertionError):
        verifier_mf03.run_mf03_verification(copied, write_receipt=False)


def test_mf04_verifier_on_committed_run_and_tampered_bundle(lab_tmp):
    d = RUNS_DIR / "mf04-20260928T125717Z-c4ed139e"
    res = verifier_mf04.run_mf04_verification(d, write_receipt=False)
    assert res["overall_status"] == "PASS"

    # Tampered bundle: mutate forecasts count to < 48
    copied = lab_tmp / "tampered_mf04"
    shutil.copytree(d, copied)
    summary_path = copied / "test_evaluation_summary.json"
    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["exec_summary"]["forecasts_executed"] = 10
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(AssertionError):
        verifier_mf04.run_mf04_verification(copied, write_receipt=False)


def test_mf05_verifier_on_committed_run_and_tampered_bundle(lab_tmp):
    d = RUNS_DIR / "mf05-20260928T130054Z-7f368dbc"
    res = verifier_mf05.run_mf05_verification(d, write_receipt=False)
    assert res["overall_status"] == "PASS"

    # Tampered bundle: mutate reproduction discrepancy
    copied = lab_tmp / "tampered_mf05"
    shutil.copytree(d, copied)
    audit_path = copied / "reproduce_audit.json"
    with open(audit_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["max_metric_discrepancy"] = 0.50
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(AssertionError):
        verifier_mf05.run_mf05_verification(copied, write_receipt=False)
