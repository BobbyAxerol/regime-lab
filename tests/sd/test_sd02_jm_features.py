"""S2-T01-JM-FEATURES-ish coverage for sd/jm_features.py (guide SS5.2, SS9.4)."""
from __future__ import annotations

import math

import pytest

from crypto_regime_lab.sd import jm_features as jf


def _returns(n: int, *, seed: int = 1, scale: float = 0.01) -> list:
    import random
    rng = random.Random(seed)
    return [rng.gauss(0.0, scale) for _ in range(n)]


def _closes_from_returns(returns: list, *, start: float = 100.0) -> list:
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * math.exp(r))
    return closes


def test_log_rv_ratio_matches_independent_formula():
    returns = _returns(200, seed=7)
    got = jf.log_rv_ratio(returns)
    import statistics
    rv_short = statistics.stdev(returns[-28:])
    rv_long = statistics.stdev(returns[-180:])
    expected = math.log(rv_short / rv_long)
    assert got == pytest.approx(expected, rel=1e-12)


def test_log_rv_ratio_requires_exactly_180_min_observations():
    with pytest.raises(jf.FeatureError):
        jf.log_rv_ratio(_returns(179))
    # exactly enough should not raise
    jf.log_rv_ratio(_returns(180, seed=3))


def test_log_rv_ratio_zero_variance_is_typed_not_silent():
    flat = [0.0] * 200
    with pytest.raises(jf.FeatureError, match="DEGENERATE_FEATURE_GEOMETRY"):
        jf.log_rv_ratio(flat)


def test_signed_path_efficiency_known_fixture_pure_trend():
    # A pure monotonic path is 100% efficient: net change == total abs change.
    closes = [100.0 + i for i in range(57)]
    got = jf.signed_path_efficiency(closes)
    assert got == pytest.approx(1.0, abs=1e-12)


def test_signed_path_efficiency_known_fixture_round_trip_is_near_zero():
    # up 56 then back down to start over the same 56 steps folded: use a
    # symmetric zigzag that ends where it started -> net change 0.
    closes = [100.0]
    for i in range(28):
        closes.append(closes[-1] + 1.0)
    for i in range(28):
        closes.append(closes[-1] - 1.0)
    assert len(closes) == 57
    got = jf.signed_path_efficiency(closes)
    assert got == pytest.approx(0.0, abs=1e-12)


def test_signed_path_efficiency_requires_57_closes():
    with pytest.raises(jf.FeatureError):
        jf.signed_path_efficiency([100.0] * 56)


def test_autocorr_lag1_matches_independent_formula():
    returns = _returns(56, seed=11)
    got = jf.autocorr_lag1(returns)
    import numpy as np
    x = np.array(returns[:-1])
    y = np.array(returns[1:])
    expected = float(np.corrcoef(x, y)[0, 1])
    assert got == pytest.approx(expected, rel=1e-9)


def test_autocorr_lag1_excludes_nan_pairs_never_coerces_to_zero():
    returns = _returns(56, seed=13)
    with_nan = list(returns)
    with_nan[10] = float("nan")
    got_with_nan = jf.autocorr_lag1(with_nan)
    # must differ from treating the NaN as 0.0 (which would silently bias it)
    zeroed = list(returns)
    zeroed[10] = 0.0
    got_zeroed = jf.autocorr_lag1(zeroed)
    assert got_with_nan != pytest.approx(got_zeroed, rel=1e-6)
    assert math.isfinite(got_with_nan)


def test_feature_row_tags_provenance_and_schema_hash():
    returns = _returns(200, seed=5)
    closes = _closes_from_returns(returns)
    row = jf.feature_row(returns, closes, observed_at="2022-01-01T00:00:00+00:00",
                         available_at="2022-01-01T00:00:00+00:00")
    assert set(jf.FEATURE_NAMES) <= set(row)
    assert row["schema_hash"] == jf.SCHEMA_HASH
    assert row["observed_at"] == "2022-01-01T00:00:00+00:00"
    assert all(math.isfinite(row[name]) for name in jf.FEATURE_NAMES)


def test_feature_row_raises_on_insufficient_history_never_returns_partial():
    with pytest.raises(jf.FeatureError):
        jf.feature_row(_returns(50), _closes_from_returns(_returns(50)),
                       observed_at="x", available_at="x")
