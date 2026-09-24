"""fp.fp08_statistics -- guide FP08.3/10.6/10.7's I_D and threshold
discipline. Synthetic fixtures only (zero engine calls, matches guide
FP08.3's own requirement)."""
from __future__ import annotations

import pytest

from crypto_regime_lab.fp import fp08_statistics as st


def test_positive_decay_clips_negative_to_zero():
    assert st.positive_decay(-0.001) == 0.0
    assert st.positive_decay(0.001) == 0.001
    assert st.positive_decay(None) is None


def _d1_row(origin, value):
    return {"origin_cutoff": origin, "D_mean_daily_return": value}


def test_primary_regime_comparison_detects_the_real_cell1_degenerate_pattern():
    """Mirrors FP-07's own real finding: B and C carry IDENTICAL D1 at
    every common origin (C fell back to B's exact prediction every time).
    I_D must come out exactly 0 and be flagged degenerate, not presented
    as a genuine decay-reduction measurement."""
    b_rows = [_d1_row("2021-04-01", 0.00087), _d1_row("2021-10-01", -0.00087),
             _d1_row("2022-01-01", 0.00053)]
    c_rows = [_d1_row("2021-04-01", 0.00087), _d1_row("2021-10-01", -0.00087),
             _d1_row("2022-01-01", 0.00053)]
    result = st.primary_regime_comparison(b_rows, c_rows)
    assert result["status"] == "DESCRIPTIVE"
    assert result["I_D"] == pytest.approx(0.0, abs=1e-12)
    assert result["degenerate"] is True
    assert "IDENTICAL D1" in result["degenerate_reason"]


def test_primary_regime_comparison_positive_when_c_reduces_decay():
    b_rows = [_d1_row("2022-01-01", 0.002), _d1_row("2022-04-01", 0.001)]
    c_rows = [_d1_row("2022-01-01", 0.0005), _d1_row("2022-04-01", 0.0002)]
    result = st.primary_regime_comparison(b_rows, c_rows)
    assert result["status"] == "DESCRIPTIVE"
    assert result["degenerate"] is False
    assert result["I_D"] > 0
    assert result["I_D"] == pytest.approx(((0.002 - 0.0005) + (0.001 - 0.0002)) / 2)


def test_primary_regime_comparison_negative_decay_contributes_zero_not_negative():
    """D_+ clips negative decay (forward beat IS) to zero -- a negative D
    on one side must never manufacture an inflated I_D via a negative
    offset that was never really 'positive decay'."""
    b_rows = [_d1_row("2022-01-01", -0.005)]   # forward much better than IS
    c_rows = [_d1_row("2022-01-01", 0.001)]
    result = st.primary_regime_comparison(b_rows, c_rows)
    assert result["per_origin"][0]["D_plus_B"] == 0.0
    assert result["per_origin"][0]["D_plus_C"] == 0.001
    assert result["I_D"] == pytest.approx(0.0 - 0.001)


def test_primary_regime_comparison_not_evaluable_with_no_common_origins():
    result = st.primary_regime_comparison([_d1_row("2021-01-01", 0.001)],
                                          [_d1_row("2099-01-01", 0.002)])
    assert result["status"] == "NOT_EVALUABLE"
    assert "no common origin" in result["reason"]


def test_primary_regime_comparison_not_evaluable_is_never_vacuously_degenerate():
    """Regression: the real bug found in FP-08's own first run. Common
    origins EXIST (both B and C carry a row for them) but every D value is
    null (e.g. neither arm ever admitted anything) -- `all()` over the
    resulting empty filtered generator is vacuously True in Python, which
    would wrongly report degenerate=True for a comparison that never
    happened at all. Mirrors this lab's own recorded LAB-06 defect #15
    ('all() over an empty population is True and reads like a verified
    claim')."""
    b_rows = [_d1_row("2021-06-01", None), _d1_row("2022-06-01", None),
             _d1_row("2023-06-01", None)]
    c_rows = [_d1_row("2021-06-01", None), _d1_row("2022-06-01", None),
             _d1_row("2023-06-01", None)]
    result = st.primary_regime_comparison(b_rows, c_rows)
    assert result["status"] == "NOT_EVALUABLE"
    assert result["degenerate"] is False


def test_primary_regime_comparison_carries_the_disclosed_threshold_status():
    result = st.primary_regime_comparison([_d1_row("2022-01-01", 0.001)],
                                          [_d1_row("2022-01-01", 0.0005)])
    assert result["threshold_status"] == "NOT_REGISTERED"
    assert "no owner-accepted" in result["threshold_reason"]


def test_economic_outperformance_check_clears_when_ci_lower_exceeds_the_registered_threshold():
    contrast = {"status": "ESTIMATED", "estimate": 0.0002, "ci95_basic": [0.0001, 0.0003]}
    out = st.economic_outperformance_check(contrast)
    assert out["ci95_lower_clears_threshold"] is True
    assert out["delta_economic_return"] == pytest.approx(6.4e-05)


def test_economic_outperformance_check_does_not_clear_when_ci_lower_is_below_threshold():
    contrast = {"status": "ESTIMATED", "estimate": 0.0002, "ci95_basic": [-0.0003, 0.0003]}
    out = st.economic_outperformance_check(contrast)
    assert out["ci95_lower_clears_threshold"] is False


def test_economic_outperformance_check_passes_through_a_non_estimated_status():
    contrast = {"status": "NOT_EVALUABLE", "reason": "no common days"}
    out = st.economic_outperformance_check(contrast)
    assert out["status"] == "NOT_EVALUABLE"
    assert out["reason"] == "no common days"
