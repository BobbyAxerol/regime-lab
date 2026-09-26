"""Coverage for sd/verifier_sd02.py (guide SS9.5, G2-* gates) -- run against
the REAL committed 12-fold VALIDATION artifacts, matching this lab's
standing discipline of testing verifiers against real evidence, not just
synthetic fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from crypto_regime_lab.sd import verifier_sd02 as v2

LAB = Path(__file__).resolve().parents[2]
VAL_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "validation_folds"


def _has_real_folds() -> bool:
    return (VAL_DIR / "fold_2022-05-14.json").exists()


pytestmark = pytest.mark.skipif(not _has_real_folds(), reason="real SD-02 fold data not present")


def test_load_validation_origins_matches_timeline():
    origins = v2.load_validation_origins(LAB)
    assert len(origins) == 12
    assert origins[0] == "2022-05-14"
    assert origins[-1] == "2024-01-20"


def test_load_fold_records_finds_all_12_real_folds():
    origins = v2.load_validation_origins(LAB)
    records = v2.load_fold_records(LAB, origins=origins)
    assert len(records) == 12
    for origin, record in records.items():
        assert record["origin_cutoff"] == origin


def test_gate_ml_valid_passes_on_real_data():
    origins = v2.load_validation_origins(LAB)
    records = v2.load_fold_records(LAB, origins=origins)
    result = v2.gate_ml_valid(records, origins=origins)
    assert result["pass"] is True
    anchor_check = next(c for c in result["checks"]
                        if c["name"] == "anchor_y_hat_zero_in_every_arms_own_scored_table")
    assert anchor_check["vacuous"] is False
    assert anchor_check["holds"] is True


def test_gate_val12_passes_on_real_data():
    origins = v2.load_validation_origins(LAB)
    records = v2.load_fold_records(LAB, origins=origins)
    result = v2.gate_val12(records)
    assert result["pass"] is True
    for check in result["checks"]:
        assert "12" in check["detail"]


def test_gate_independence_passes_and_is_not_vacuous():
    origins = v2.load_validation_origins(LAB)
    records = v2.load_fold_records(LAB, origins=origins)
    result = v2.gate_independence(records)
    assert result["pass"] is True
    b_anchor_check = next(c for c in result["checks"]
                          if c["name"] == "c_scored_even_when_b_falls_back_to_anchor")
    assert b_anchor_check["vacuous"] is False, "the real data must have >=1 genuine B-anchor fold"


def test_gate_ml_valid_catches_a_missing_fold():
    origins = v2.load_validation_origins(LAB)
    records = v2.load_fold_records(LAB, origins=origins)
    truncated = dict(list(records.items())[:11])
    result = v2.gate_ml_valid(truncated, origins=origins)
    assert result["pass"] is False
    missing_check = next(c for c in result["checks"] if c["name"] == "all_12_folds_present")
    assert missing_check["holds"] is False


def test_gate_independence_catches_a_fabricated_uncalled_arm():
    origins = v2.load_validation_origins(LAB)
    records = v2.load_fold_records(LAB, origins=origins)
    import copy
    broken = copy.deepcopy(records)
    first_origin = next(iter(broken))
    broken[first_origin]["arms"]["R_RULE"]["context_prediction_called"] = False
    result = v2.gate_independence(broken)
    assert result["pass"] is False


def test_verify_sd02_end_to_end_on_real_committed_artifacts():
    result = v2.verify_sd02(lab_root=LAB)
    assert result["n_folds_found"] == 12
    assert result["n_folds_expected"] == 12
    assert result["overall"] == "PASS"
    for gate_name in v2.REQUIRED_GATES:
        assert gate_name in result["gates"]
