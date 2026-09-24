"""fp.fp08_coverage -- the 20-cell matrix, cells not run reported honestly."""
from __future__ import annotations

from crypto_regime_lab.fp import fp08_coverage as cov


def test_build_coverage_matrix_has_exactly_20_cells():
    out = cov.build_coverage_matrix(cell1_run_dir="run1", cell2_run_dir="run2")
    assert out["n_cells"] == 20
    assert len(out["cells"]) == len(cov.ALPHAS) * len(cov.SYMBOLS)


def test_build_coverage_matrix_marks_cell1_completed_with_evidence():
    out = cov.build_coverage_matrix(cell1_run_dir="run1", cell2_run_dir="run2")
    cell1 = next(c for c in out["cells"] if c["alpha_id"] == "A-SC" and c["symbol"] == "BTCUSDT")
    assert cell1["status"] == "COMPLETED"
    assert cell1["evidence_ref"] == "run1"


def test_build_coverage_matrix_marks_cell2_in_progress_without_an_evidence_ref():
    out = cov.build_coverage_matrix(cell1_run_dir="run1", cell2_run_dir=None,
                                    cell2_status="IN_PROGRESS")
    cell2 = next(c for c in out["cells"] if c["alpha_id"] == "A-SC" and c["symbol"] == "ETHUSDT")
    assert cell2["status"] == "IN_PROGRESS"
    assert "evidence_ref" not in cell2
    assert cell2["reason"]


def test_build_coverage_matrix_marks_every_other_cell_not_run_with_a_reason():
    out = cov.build_coverage_matrix(cell1_run_dir="run1", cell2_run_dir="run2")
    others = [c for c in out["cells"]
             if (c["alpha_id"], c["symbol"]) not in (("A-SC", "BTCUSDT"), ("A-SC", "ETHUSDT"))]
    assert len(others) == 18
    for c in others:
        assert c["status"] == "NOT_RUN"
        assert c["reason"]


def test_build_coverage_matrix_n_completed_reflects_actual_statuses():
    out = cov.build_coverage_matrix(cell1_run_dir="run1", cell2_run_dir=None,
                                    cell2_status="IN_PROGRESS")
    assert out["n_completed"] == 1
    out2 = cov.build_coverage_matrix(cell1_run_dir="run1", cell2_run_dir="run2")
    assert out2["n_completed"] == 2
