"""L09.3 — the paired block bootstrap has to keep the structure it claims to keep.

Every test here is written so that removing the property it names makes it fail.
The three that matter are the ones the guide asks for by name: pairing, blocking,
and resampling the symbols TOGETHER.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.experiments.uncertainty import (UncertaintyError, autocorrelation,
                                                       block_length_sensitivity,
                                                       choose_block_length, concentration,
                                                       episode_counts,
                                                       paired_block_bootstrap)

DATES = pd.date_range("2024-01-01", periods=600, freq="D", tz="UTC")


def ar1(rho: float, n: int, seed: int, scale: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(n)
    for i in range(1, n):
        out[i] = rho * out[i - 1] + rng.normal(0.0, scale)
    return out


def test_autocorrelation_finds_the_dependence_that_is_there():
    persistent = autocorrelation(ar1(0.9, 800, 1), max_lag=3)
    white = autocorrelation(np.random.default_rng(2).normal(size=800), max_lag=3)
    assert persistent[0] > 0.7
    assert abs(white[0]) < 0.15


def test_block_length_is_longer_for_a_persistent_series():
    persistent = choose_block_length(ar1(0.9, 600, 3))
    white = choose_block_length(np.random.default_rng(4).normal(size=600))
    assert persistent["block_length"] > white["block_length"]
    assert persistent["block_length"] >= 2


def test_block_length_refuses_a_series_too_short_to_have_one():
    with pytest.raises(UncertaintyError):
        choose_block_length(np.arange(5.0))


def test_the_interval_covers_a_known_constant_difference():
    series = {"cell": pd.Series(np.full(len(DATES), 0.001), index=DATES)}
    result = paired_block_bootstrap(series, block_length=5, draws=400, seed=7)
    assert result["point_estimate"] == pytest.approx(0.001)
    assert result["ci_lower"] == pytest.approx(0.001)
    assert result["ci_upper"] == pytest.approx(0.001)


def test_blocks_widen_the_interval_on_an_autocorrelated_series():
    """An iid resample of a persistent series returns an interval that is too narrow.

    This is the whole reason the guide forbids treating daily returns as iid, and
    it is measured here rather than asserted: the same series, the same draws,
    only the block length differs.
    """
    values = ar1(0.9, len(DATES), 11, scale=0.01)
    series = {"cell": pd.Series(values, index=DATES)}
    iid = paired_block_bootstrap(series, block_length=1, draws=1500, seed=13)
    blocked = paired_block_bootstrap(series, block_length=25, draws=1500, seed=13)
    iid_width = iid["ci_upper"] - iid["ci_lower"]
    blocked_width = blocked["ci_upper"] - blocked["ci_lower"]
    assert blocked_width > iid_width * 1.5


def test_symbols_are_resampled_together_so_common_shocks_survive():
    """T63. Five perfectly correlated cells must not look like five independent ones.

    Resampling each cell on its own dates averages the same shock five times over
    different days, which cancels it; the interval then shrinks by roughly
    sqrt(5) for nothing. The implementation draws ONE date sequence per draw, so
    the correlated cells stay correlated and the interval keeps its width.
    """
    shock = ar1(0.5, len(DATES), 17, scale=0.01)
    together = {f"cell{i}": pd.Series(shock, index=DATES) for i in range(5)}
    joint = paired_block_bootstrap(together, block_length=10, draws=1500, seed=19)

    # the counterfactual: the same five cells resampled independently
    rng = np.random.default_rng(19)
    independent = []
    for _ in range(1500):
        per_cell = []
        for _ in range(5):
            starts = rng.integers(0, len(DATES) - 10 + 1, size=len(DATES) // 10)
            columns = (starts[:, None] + np.arange(10)[None, :]).ravel()[:len(DATES)]
            per_cell.append(shock[columns].mean())
        independent.append(float(np.mean(per_cell)))
    independent_width = float(np.quantile(independent, 0.975)
                              - np.quantile(independent, 0.025))
    joint_width = joint["ci_upper"] - joint["ci_lower"]
    assert joint_width > independent_width * 1.6
    assert joint["cells_pooled"] == 5


def test_pairing_excludes_days_a_cell_was_not_live():
    live = pd.Series([0.01] * 300, index=DATES[:300])
    counts = episode_counts({"short": live,
                             "long": pd.Series(np.zeros(len(DATES)), index=DATES)})
    assert counts["per_cell_days"] == {"short": 300, "long": len(DATES)}
    assert counts["days_all_cells_live"] == 300
    assert counts["union_days"] == len(DATES)


def test_the_interval_refuses_a_window_too_short_for_its_blocks():
    short = pd.Series(np.zeros(30), index=DATES[:30])
    with pytest.raises(UncertaintyError):
        paired_block_bootstrap({"cell": short}, block_length=25, draws=100)


def test_concentration_names_the_days_that_carry_the_result():
    values = np.zeros(len(DATES))
    values[100] = 0.5
    series = {"cell": pd.Series(values, index=DATES)}
    out = concentration(series)
    assert out["top_1_day_share_of_absolute"] == pytest.approx(1.0)
    assert out["days_for_half_the_absolute_move"] == 1
    assert out["largest_day"]["date"] == str(DATES[100].date())
    assert out["mean_without_top_5_days"] == pytest.approx(0.0)


def test_concentration_counts_offsetting_days_as_concentration():
    """Two huge days that cancel are still two huge days.

    Measuring concentration on the signed total would show a tiny number and hide
    them, which is the opposite of what guide 11.4 asks for.
    """
    values = np.zeros(len(DATES))
    values[10], values[11] = 0.5, -0.5
    out = concentration({"cell": pd.Series(values, index=DATES)})
    assert out["total"] == pytest.approx(0.0)
    assert out["top_5_day_share_of_absolute"] == pytest.approx(1.0)


def test_sensitivity_reports_every_requested_block_length():
    series = {"cell": pd.Series(ar1(0.7, len(DATES), 23, scale=0.01), index=DATES)}
    rows = block_length_sensitivity(series, lengths=(1, 5, 20, 400), draws=200, seed=29)
    assert [r["block_length_days"] for r in rows] == [1, 5, 20, 400]
    assert rows[-1]["status"] == "NOT_COMPUTABLE"      # 400 blocks will not fit in 600 dates
    assert all(r["status"] == "OK" for r in rows[:3])
