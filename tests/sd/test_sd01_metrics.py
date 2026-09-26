"""SD-01: canonical Sharpe wrapper (S1-T04-RETURN-BOUNDARY, S1-T05-SHARPE)."""
from __future__ import annotations

import math

import pytest

from crypto_regime_lab.sd import metrics as m


def test_return_boundary_two_step_returns_correct():
    """Fixture equity 100 -> 120 -> 108: two step returns, exact values (guide
    SS2.1 numeric example, S1-T04-RETURN-BOUNDARY)."""
    result = m.window_sharpe(
        [("2020-01-02", 120.0), ("2020-01-03", 108.0)],
        initial_equity=100.0, window_start="2020-01-02", window_end="2020-01-04",
        expected_days=2)
    assert result["returns"] == pytest.approx([0.20, -0.10])
    assert result["n_days"] == 2


def test_return_boundary_clip_does_not_lose_the_first_step():
    """The window's first return uses the preceding (initial) equity, not a
    dropped/undefined first observation."""
    result = m.window_sharpe(
        [("2020-01-02", 110.0)], initial_equity=100.0,
        window_start="2020-01-02", window_end="2020-01-03", expected_days=1)
    assert result["returns"] == pytest.approx([0.10])


def test_return_boundary_actual_180_count_enforced():
    """A window that does not deliver exactly the requested day count raises,
    never silently returns a wrong count (the guide's own named 185/29 bug)."""
    rows = [(f"2020-01-{d:02d}", 100.0 + d) for d in range(2, 32)]   # only 30 rows
    with pytest.raises(m.MetricWindowError):
        m.window_sharpe(rows, initial_equity=100.0, window_start="2020-01-02",
                        window_end="2020-07-30", expected_days=180)


def test_return_boundary_actual_56_count_enforced():
    rows = [(f"2020-{(1 if d <= 30 else 2):02d}-{(d if d <= 30 else d - 30):02d}", 100.0)
           for d in range(2, 40)]   # 38 rows, not 56
    with pytest.raises(m.MetricWindowError):
        m.window_sharpe(rows, initial_equity=100.0, window_start="2020-01-02",
                        window_end="2020-02-27", expected_days=56)


def test_return_boundary_missing_day_raises_not_silently_zero():
    """A gap in the supplied daily rows must raise, never be treated as a 0%
    return for the missing day (quantbt's own ffill behavior, explicitly not
    reused here)."""
    rows = [("2020-01-02", 110.0), ("2020-01-04", 120.0)]   # 2020-01-03 missing
    with pytest.raises(m.MetricWindowError):
        m.window_sharpe(rows, initial_equity=100.0, window_start="2020-01-02",
                        window_end="2020-01-05", expected_days=3)


def test_sharpe_matches_independent_formula():
    """Known numeric series matches an independently-computed formula
    (S1-T05-SHARPE)."""
    returns = [0.01, -0.005, 0.02, 0.0, -0.01, 0.015]
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sd = math.sqrt(var)
    expected = mean / sd * math.sqrt(365)

    # build a real equity path from the returns for window_sharpe
    equity = 100.0
    rows = []
    for i, r in enumerate(returns):
        equity *= (1 + r)
        rows.append((f"2020-01-{2 + i:02d}", equity))
    result = m.window_sharpe(rows, initial_equity=100.0, window_start="2020-01-02",
                             window_end="2020-01-08", expected_days=6)
    assert result["sharpe_status"] == "OK"
    assert result["sharpe"] == pytest.approx(expected, rel=1e-9)


def test_sharpe_zero_variance_is_typed_not_a_bare_zero():
    """A flat (zero-variance) window is flagged ZERO_VARIANCE, never a bare
    0.0 indistinguishable from a genuinely-computed zero -- the exact
    quantbt.metrics.performance.sharpe() failure mode this module avoids."""
    rows = [("2020-01-02", 100.0), ("2020-01-03", 100.0), ("2020-01-04", 100.0)]
    result = m.window_sharpe(rows, initial_equity=100.0, window_start="2020-01-02",
                             window_end="2020-01-05", expected_days=3)
    assert result["sharpe_status"] == "ZERO_VARIANCE"
    assert result["sharpe"] is None


def test_sharpe_too_few_observations_is_typed():
    result = m.window_sharpe([("2020-01-02", 105.0)], initial_equity=100.0,
                             window_start="2020-01-02", window_end="2020-01-03",
                             expected_days=1)
    assert result["sharpe_status"] == "TOO_FEW_OBSERVATIONS"
    assert result["sharpe"] is None


def _ok_window(sharpe_value: float) -> dict:
    return {"sharpe": sharpe_value, "sharpe_status": "OK", "n_days": 180,
           "window_start": "x", "window_end": "y", "returns": []}


def _bad_window(status: str) -> dict:
    return {"sharpe": None, "sharpe_status": status, "n_days": 0,
           "window_start": "x", "window_end": "y", "returns": []}


def test_signed_decay_is_signed_never_clipped():
    d = m.signed_decay(_ok_window(1.80), _ok_window(0.50))
    assert d == {"value": pytest.approx(1.30), "status": "OK"}
    d_negative = m.signed_decay(_ok_window(0.50), _ok_window(1.80))
    assert d_negative["value"] == pytest.approx(-1.30)   # never absolute-valued


def test_signed_decay_propagates_undefined_input():
    d = m.signed_decay(_bad_window("ZERO_VARIANCE"), _ok_window(0.50))
    assert d["status"] == "UNDEFINED_INPUT"
    assert d["value"] is None
    assert d["is_status"] == "ZERO_VARIANCE"


def test_relative_decay_anchor_zero_by_construction():
    anchor_d = {"value": 1.30, "status": "OK"}
    y = m.relative_decay(anchor_d, anchor_d)
    assert y == {"value": pytest.approx(0.0), "status": "OK"}


def test_relative_decay_propagates_undefined_input():
    y = m.relative_decay({"value": None, "status": "UNDEFINED_INPUT",
                          "is_status": "x", "fwd_status": "y"},
                         {"value": 0.0, "status": "OK"})
    assert y["status"] == "UNDEFINED_INPUT"
    assert y["value"] is None


def test_paired_reduction_guide_numeric_example():
    """Guide SS2.3's own worked example: B decay 1.30, C decay 0.85 ->
    reduction 0.45."""
    decay_b = {"value": 1.30, "status": "OK"}
    decay_c = {"value": 0.85, "status": "OK"}
    r = m.paired_reduction(decay_b, decay_c)
    assert r == {"value": pytest.approx(0.45), "status": "OK"}


def test_paired_reduction_propagates_undefined_input():
    r = m.paired_reduction({"value": None, "status": "UNDEFINED_INPUT"},
                           {"value": 0.85, "status": "OK"})
    assert r["status"] == "UNDEFINED_INPUT"
    assert r["value"] is None


def test_decompose_reduction_guide_numeric_example():
    """Guide SS2.3's own worked example: B IS=1.80 FWD=0.50 (decay 1.30),
    C IS=1.75 FWD=0.90 (decay 0.85) -> reduction 0.45, IS contribution
    0.05, forward contribution 0.40."""
    result = m.decompose_reduction(sr_is_b=1.80, sr_fwd_b=0.50, sr_is_c=1.75, sr_fwd_c=0.90)
    assert result["is_contribution"] == pytest.approx(0.05)
    assert result["fwd_contribution"] == pytest.approx(0.40)
    assert result["r"] == pytest.approx(0.45)


def test_decompose_reduction_reconciles_with_paired_reduction():
    """The decomposition's own R must match paired_reduction()'s R exactly
    -- guide SS2.3: 'bat buoc reconcile', not an approximation."""
    sr_is_b, sr_fwd_b, sr_is_c, sr_fwd_c = 2.1, -0.3, 1.9, 0.6
    decay_b = m.signed_decay({"sharpe": sr_is_b, "sharpe_status": "OK"},
                             {"sharpe": sr_fwd_b, "sharpe_status": "OK"})
    decay_c = m.signed_decay({"sharpe": sr_is_c, "sharpe_status": "OK"},
                             {"sharpe": sr_fwd_c, "sharpe_status": "OK"})
    direct_r = m.paired_reduction(decay_b, decay_c)
    decomposed = m.decompose_reduction(sr_is_b=sr_is_b, sr_fwd_b=sr_fwd_b,
                                       sr_is_c=sr_is_c, sr_fwd_c=sr_fwd_c)
    assert decomposed["r"] == pytest.approx(direct_r["value"])


def test_decompose_reduction_sign_does_not_flip_with_a_weaker_is_fit():
    """Guide SS2.3: a smaller gap from a weaker IS fit is not itself a
    better OOS result -- a case where IS contribution is negative (C's
    own IS is HIGHER than B's) must still decompose correctly, not have
    its sign silently flipped to look favorable."""
    result = m.decompose_reduction(sr_is_b=1.0, sr_fwd_b=0.0, sr_is_c=1.5, sr_fwd_c=0.0)
    assert result["is_contribution"] == pytest.approx(-0.5)
    assert result["fwd_contribution"] == pytest.approx(0.0)
    assert result["r"] == pytest.approx(-0.5)
