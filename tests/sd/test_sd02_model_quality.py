"""Coverage for sd/model_quality.py (guide SS5.1/5.6, SD02.5)."""
from __future__ import annotations

import pytest

from crypto_regime_lab.sd import model_quality as mq


def _rows(y_hats: dict):
    return [{"candidate_id": cid, "y_hat": y} for cid, y in y_hats.items()]


def test_mae_y_one_origin_matches_independent_formula():
    rows = _rows({"a": 0.1, "b": -0.2, "c": 0.05})
    true_y = {"a": 0.0, "b": 0.0, "c": 0.1}
    result = mq.mae_y_one_origin(rows, true_y)
    expected = (0.1 + 0.2 + 0.05) / 3
    assert result["mae"] == pytest.approx(expected)
    assert result["n"] == 3


def test_mae_y_excludes_anchor_when_given():
    rows = _rows({"anchor": 0.0, "b": -0.2})
    true_y = {"anchor": 0.0, "b": 0.0}
    result = mq.mae_y_one_origin(rows, true_y, anchor_id="anchor")
    assert result["n"] == 1
    assert result["mae"] == pytest.approx(0.2)


def test_mae_y_excludes_undefined_labels_never_imputes():
    rows = _rows({"a": 0.1, "b": 0.2})
    true_y = {"a": 0.0}   # b has no true label
    result = mq.mae_y_one_origin(rows, true_y)
    assert result["n"] == 1


def test_mae_y_no_labeled_candidates_typed():
    rows = _rows({"a": 0.1})
    result = mq.mae_y_one_origin(rows, {})
    assert result["status"] == "NO_LABELED_CANDIDATES"
    assert result["mae"] is None


def test_mean_mae_y_unweighted_origin_average():
    result = mq.mean_mae_y([0.1, 0.3, None, 0.2])
    assert result["mean_mae"] == pytest.approx(0.2)
    assert result["n_origins"] == 3


def test_rank_diagnostic_perfect_agreement():
    rows = _rows({"a": 0.1, "b": 0.5, "c": 0.9})
    true_y = {"a": 0.0, "b": 1.0, "c": 2.0}
    result = mq.rank_diagnostic_one_origin(rows, true_y)
    assert result["rho"] == pytest.approx(1.0)


def test_rank_diagnostic_perfect_disagreement():
    rows = _rows({"a": 0.9, "b": 0.5, "c": 0.1})
    true_y = {"a": 0.0, "b": 1.0, "c": 2.0}
    result = mq.rank_diagnostic_one_origin(rows, true_y)
    assert result["rho"] == pytest.approx(-1.0)


def test_rank_diagnostic_no_variation_typed_not_fabricated():
    rows = _rows({"a": 0.1, "b": 0.5, "c": 0.9})
    true_y = {"a": 0.5, "b": 0.5, "c": 0.5}
    result = mq.rank_diagnostic_one_origin(rows, true_y)
    assert result["status"] == "NO_VARIATION"
    assert result["rho"] is None


def test_rank_diagnostic_too_few_candidates():
    rows = _rows({"a": 0.1, "b": 0.5})
    true_y = {"a": 0.0, "b": 1.0}
    result = mq.rank_diagnostic_one_origin(rows, true_y)
    assert result["status"] == "TOO_FEW_CANDIDATES"


def test_state_occupancy_counts_dwell_and_recurrence():
    states = [0, 0, 0, 1, 1, 0, None, 0, 1]
    result = mq.state_occupancy(states)
    assert result["occupancy"] == {0: 5, 1: 3}
    assert result["n_unknown"] == 1
    # runs, in order: [0,0,0](3) [1,1](2) [0](1) <gap> [0](1) [1](1) -- the
    # gap genuinely separates the two single-bar "0" runs into distinct
    # visits (a gap is not evidence of a continuous run through it), so
    # state 0 has THREE separate visits (3,1,1), state 1 has two (2,1).
    assert result["recurrence_count"] == {0: 3, 1: 2}
    assert result["mean_dwell_bars"][0] == pytest.approx((3 + 1 + 1) / 3)
    assert result["mean_dwell_bars"][1] == pytest.approx((2 + 1) / 2)


def test_state_occupancy_empty_input():
    result = mq.state_occupancy([])
    assert result["occupancy"] == {}
    assert result["n_known"] == 0
