import pytest
from pathlib import Path
import pandas as pd

from crypto_regime_lab.regime_forecast import features

LAB_ROOT = Path("/root/bobby/pool_alpha/lab_regime_model_quantbt")
SNAPSHOTS_DIR = LAB_ROOT / "snapshots/server_core_v1"

def test_no_contiguous_column_hole_in_role_windows():
    """FIX-01 Acceptance test:
    Verify that features in approved cohorts do not have contiguous missing holes > 7 days
    in role windows (training: 2022-01-14..2024-01-13, dev: 2024-04-13..2025-03-15, test: 2025-06-07..2026-05-09).
    Prior to fixing features.py (which dropped entire rows on partial metrics missingness),
    this test MUST FAIL on 2022 data.
    """
    df_base = features.build_daily_base_table(SNAPSHOTS_DIR, start_year="2021")
    df_feat = features.compute_features(df_base)
    
    role_windows = [
        ("initial_training", "2022-01-14", "2024-01-13"),
        ("development", "2024-04-13", "2025-03-15"),
        ("locked_test", "2025-06-07", "2026-05-09"),
    ]
    
    d1_features = features.COHORTS["D1_DERIVATIVE_LIQUIDITY"]
    
    violations = []
    
    for role_name, start_date, end_date in role_windows:
        mask = (df_feat["date"] >= pd.to_datetime(start_date)) & (df_feat["date"] <= pd.to_datetime(end_date))
        sub = df_feat.loc[mask]
        
        for col in d1_features:
            if col not in sub.columns:
                violations.append(f"{role_name} missing column {col}")
                continue
            is_na = sub[col].isna().values
            # Find longest contiguous run of True (NaN)
            max_run = 0
            curr_run = 0
            for val in is_na:
                if val:
                    curr_run += 1
                    if curr_run > max_run:
                        max_run = curr_run
                else:
                    curr_run = 0
            if max_run > 7:
                violations.append(f"Column '{col}' in role '{role_name}' has contiguous NaN run of {max_run} > 7 days")
                
    if violations:
        pytest.fail(f"Found {len(violations)} contiguous hole violations in role windows:\n" + "\n".join(violations[:10]))


def test_g1_coverage_gate_evaluates_correctly():
    """Verify G1-COVERAGE gate logic and proof of failure on corrupted coverage."""
    from crypto_regime_lab.regime_forecast import verifier_mf01
    
    # Valid coverage table passes
    valid_summary = {
        "status": "PASS",
        "min_column_coverage_training": 0.98,
        "min_column_coverage_dev": 1.0,
        "min_column_coverage_test": 1.0,
        "threshold": 0.95,
        "excluded_low_coverage_columns": []
    }
    assert verifier_mf01.verify_gate_g1_coverage(valid_summary)["status"] == "PASS"
    
    # Defective coverage table (<0.95 threshold) fails
    invalid_summary = {
        "status": "FAIL",
        "min_column_coverage_training": 0.503, # 49.7% missing as found in review
        "min_column_coverage_dev": 1.0,
        "min_column_coverage_test": 1.0,
        "threshold": 0.95,
        "excluded_low_coverage_columns": []
    }
    assert verifier_mf01.verify_gate_g1_coverage(invalid_summary)["status"] == "FAIL"
