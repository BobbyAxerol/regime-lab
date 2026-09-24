"""fp.fp08_contribution -- guide FP08.4's five questions, each cited to
real per-cell evidence."""
from __future__ import annotations

from crypto_regime_lab.fp import fp08_contribution as fc


def _sel(source):
    return {"source": source, "params": {"coeff": 1}}


def test_build_contribution_checks_all_na_when_no_cell_ever_used_context():
    cell1 = {"C_FP_CONTEXT": {o: _sel("FALLBACK_TO_B") for o in
                              ("2021-04-01", "2021-10-01", "2022-01-01")}}
    cell2 = {"C_FP_CONTEXT": {o: _sel("FALLBACK_TO_A") for o in ("2021-06-01",)}}
    out = fc.build_contribution_checks(cell1_selections_by_origin=cell1,
                                       cell2_selections_by_origin=cell2)
    by_q = {row["question"]: row for row in out["answers"]}
    assert by_q["Context có thực sự đổi candidate rankings/selections không?"]["answer"] == "No"
    assert by_q["Benefit có còn sau common calendar?"]["answer"] == "N/A"
    assert by_q["Context improvement có chỉ là market-wide offset không?"]["answer"] == "N/A"
    assert by_q["C thắng do conditional selection hay chỉ giảm exposure?"]["answer"] == "N/A"


def test_build_contribution_checks_yes_when_a_context_conditioned_selection_exists():
    cell1 = {"C_FP_CONTEXT": {"2022-04-01": _sel("CONTEXT_CONDITIONED")}}
    cell2 = {"C_FP_CONTEXT": {}}
    out = fc.build_contribution_checks(cell1_selections_by_origin=cell1,
                                       cell2_selections_by_origin=cell2)
    by_q = {row["question"]: row for row in out["answers"]}
    assert by_q["Context có thực sự đổi candidate rankings/selections không?"]["answer"] == "Yes"
    assert by_q["Benefit có còn sau common calendar?"]["answer"] == "REQUIRES_MANUAL_REVIEW"


def test_build_contribution_checks_vintage_question_flags_a_pattern_that_differs_by_cell():
    cell1 = {"C_FP_CONTEXT": {"2022-04-01": _sel("CONTEXT_CONDITIONED")}}
    cell2 = {"C_FP_CONTEXT": {"2021-06-01": _sel("FALLBACK_TO_A")}}
    out = fc.build_contribution_checks(cell1_selections_by_origin=cell1,
                                       cell2_selections_by_origin=cell2)
    vintage = next(row for row in out["answers"] if "vintage" in row["question_en"])
    assert vintage["answer"] == "YES_PATTERN_DIFFERS_BY_CELL"


def test_build_contribution_checks_vintage_question_consistent_when_both_cells_agree():
    cell1 = {"C_FP_CONTEXT": {o: _sel("FALLBACK_TO_B") for o in ("2021-04-01",)}}
    cell2 = {"C_FP_CONTEXT": {o: _sel("FALLBACK_TO_A") for o in ("2021-06-01",)}}
    out = fc.build_contribution_checks(cell1_selections_by_origin=cell1,
                                       cell2_selections_by_origin=cell2)
    vintage = next(row for row in out["answers"] if "vintage" in row["question_en"])
    assert vintage["answer"] == "CONSISTENT_ACROSS_CELLS"


def test_build_contribution_checks_real_cell1_data_matches_the_committed_fp07_finding():
    """Sanity check against FP-07's own real, committed selections.json --
    0/12 CONTEXT_CONDITIONED, matching the report's own disclosed number."""
    import json
    from pathlib import Path

    doc = json.loads(Path(
        "evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/selections.json"
    ).read_text())
    cell1 = {"C_FP_CONTEXT": {o: arms["C_FP_CONTEXT"] for o, arms in doc["by_origin"].items()}}
    out = fc.build_contribution_checks(cell1_selections_by_origin=cell1,
                                       cell2_selections_by_origin={"C_FP_CONTEXT": {}})
    q1 = next(row for row in out["answers"] if "rankings" in row["question_en"])
    assert q1["answer"] == "No"
    assert "cell1: 0/12" in q1["evidence"]
