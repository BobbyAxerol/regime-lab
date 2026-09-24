"""FP-09 -- timing_policy.py: rolling volatility ratio and schedule derivation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.fp import timing_policy as tp


def _flat_frame(n: int, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2021-01-01", periods=n, freq="1min", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0, 0.01, size=n))
    return pd.DataFrame({"close": close}, index=index)


def test_rolling_volatility_ratio_is_causal():
    """A future spike must never change an earlier bar's ratio."""
    n = 5000
    base = _flat_frame(n, seed=1)
    mutated = base.copy()
    mutated.loc[mutated.index[4000:], "close"] *= 5.0   # violent late-window mutation

    base_ratio = tp.rolling_volatility_ratio(base, short_days=1, long_days=2)
    mutated_ratio = tp.rolling_volatility_ratio(mutated, short_days=1, long_days=2)

    # bars strictly before the mutation start must be byte-identical
    pre = slice(0, 3999)
    pd.testing.assert_series_equal(base_ratio.iloc[pre], mutated_ratio.iloc[pre])


def test_rolling_volatility_ratio_matches_manual_short_over_long():
    n = 10000
    frame = _flat_frame(n, seed=2)
    ratio = tp.rolling_volatility_ratio(frame, short_days=1, long_days=2)
    bars_per_day = tp.BARS_PER_DAY
    returns = frame["close"].pct_change()
    probe = 9000
    manual_short = returns.iloc[probe - bars_per_day + 1: probe + 1].std()
    manual_long = returns.iloc[probe - 2 * bars_per_day + 1: probe + 1].std()
    assert ratio.iloc[probe] == pytest.approx(manual_short / manual_long, rel=1e-9)


def test_rolling_volatility_ratio_is_nan_before_the_long_window_matures():
    frame = _flat_frame(500, seed=3)
    ratio = tp.rolling_volatility_ratio(frame, short_days=1, long_days=2)
    assert pd.isna(ratio.iloc[100])


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.RangeIndex(len(values)))


def test_derive_regime_timing_schedule_finds_first_bar_at_or_below_threshold():
    vol = _series([2.0, 2.0, 2.0, 0.9, 2.0, 2.0])
    base = [{"activation_id": "a@1", "params": {"x": 1}, "requested_at_bar": 0}]
    new_schedule, diags = tp.derive_regime_timing_schedule(
        base, vol, threshold=1.0, k_max_bars=5, n_bars=len(vol))
    assert new_schedule[0]["requested_at_bar"] == 3
    assert diags[0]["hit_threshold"] is True
    assert diags[0]["deferred_bars"] == 3
    assert new_schedule[0]["params"] == {"x": 1}   # params untouched, only timing moves


def test_derive_regime_timing_schedule_falls_back_to_bound_when_never_crossed():
    vol = _series([5.0] * 10)
    base = [{"activation_id": "a@1", "params": {"x": 1}, "requested_at_bar": 2}]
    new_schedule, diags = tp.derive_regime_timing_schedule(
        base, vol, threshold=1.0, k_max_bars=4, n_bars=len(vol))
    assert new_schedule[0]["requested_at_bar"] == 6   # 2 + 4
    assert diags[0]["hit_threshold"] is False
    assert diags[0]["deferred_bars"] == 4


def test_derive_regime_timing_schedule_treats_nan_as_never_crossed():
    vol = _series([float("nan")] * 5 + [0.5])
    base = [{"activation_id": "a@1", "params": {"x": 1}, "requested_at_bar": 0}]
    new_schedule, diags = tp.derive_regime_timing_schedule(
        base, vol, threshold=1.0, k_max_bars=3, n_bars=len(vol))
    assert new_schedule[0]["requested_at_bar"] == 3   # bounded fallback, NaNs never satisfy <= threshold
    assert diags[0]["hit_threshold"] is False


def test_derive_regime_timing_schedule_caps_scan_at_n_bars_minus_one():
    vol = _series([5.0, 5.0, 5.0])
    base = [{"activation_id": "a@1", "params": {"x": 1}, "requested_at_bar": 1}]
    new_schedule, diags = tp.derive_regime_timing_schedule(
        base, vol, threshold=1.0, k_max_bars=100, n_bars=len(vol))
    assert new_schedule[0]["requested_at_bar"] == 2   # capped at n_bars - 1, not 1 + 100
    assert diags[0]["deferred_bars"] == 1


def test_derive_regime_timing_schedule_handles_multiple_events_independently():
    vol = _series([2.0, 0.5, 2.0, 2.0, 2.0, 0.3, 2.0])
    base = [{"activation_id": "a@1", "params": {"x": 1}, "requested_at_bar": 0},
            {"activation_id": "a@2", "params": {"x": 2}, "requested_at_bar": 3}]
    new_schedule, diags = tp.derive_regime_timing_schedule(
        base, vol, threshold=1.0, k_max_bars=5, n_bars=len(vol))
    by_id = {e["activation_id"]: e["requested_at_bar"] for e in new_schedule}
    assert by_id["a@1"] == 1
    assert by_id["a@2"] == 5


def test_derive_regime_timing_schedule_rejects_empty_schedule():
    with pytest.raises(tp.TimingPolicyError):
        tp.derive_regime_timing_schedule([], _series([1.0]), n_bars=1)


def test_derive_regime_timing_schedule_rejects_negative_requested_at_bar():
    base = [{"activation_id": "a@1", "params": {}, "requested_at_bar": -5}]
    with pytest.raises(tp.TimingPolicyError):
        tp.derive_regime_timing_schedule(base, _series([1.0] * 10), n_bars=10)


def test_derive_cal_matched_schedule_defers_within_the_bound_no_market_data():
    base = [{"activation_id": "a@1", "params": {"x": 1}, "requested_at_bar": 10},
            {"activation_id": "a@2", "params": {"x": 2}, "requested_at_bar": 50}]
    matched, diags = tp.derive_cal_matched_schedule(base, k_max_bars=20, seed=1, n_bars=1000)
    by_id = {e["activation_id"]: e["requested_at_bar"] for e in matched}
    assert 10 <= by_id["a@1"] <= 30
    assert 50 <= by_id["a@2"] <= 70
    assert all(0 <= d["deferred_bars"] <= 20 for d in diags)


def test_derive_cal_matched_schedule_never_touches_params():
    base = [{"activation_id": "a@1", "params": {"x": 1, "y": 2}, "requested_at_bar": 10}]
    matched, _diags = tp.derive_cal_matched_schedule(base, k_max_bars=5, seed=1, n_bars=100)
    assert matched[0]["params"] == {"x": 1, "y": 2}


def test_derive_cal_matched_schedule_is_reproducible_from_the_same_seed():
    base = [{"activation_id": "a@1", "params": {}, "requested_at_bar": 10},
            {"activation_id": "a@2", "params": {}, "requested_at_bar": 50}]
    m1, _ = tp.derive_cal_matched_schedule(base, k_max_bars=20, seed=42, n_bars=1000)
    m2, _ = tp.derive_cal_matched_schedule(base, k_max_bars=20, seed=42, n_bars=1000)
    assert [e["requested_at_bar"] for e in m1] == [e["requested_at_bar"] for e in m2]


def test_derive_cal_matched_schedule_takes_no_input_from_regime_timings_realized_schedule():
    """The whole point of the redesign: CAL_MATCHED must be independently derivable with
    NOTHING from REGIME_TIMING's own realized diagnostics -- an earlier, structurally
    degenerate version accepted REGIME_TIMING's diagnostics as an argument and always
    reproduced its exact schedule. The function signature itself now enforces this."""
    import inspect

    params = list(inspect.signature(tp.derive_cal_matched_schedule).parameters)
    assert "regime_timing_diagnostics" not in params
    assert "vol_ratio" not in params


def test_derive_cal_matched_schedule_caps_at_n_bars_minus_one():
    base = [{"activation_id": "a@1", "params": {}, "requested_at_bar": 90}]
    matched, diags = tp.derive_cal_matched_schedule(base, k_max_bars=1000, seed=1, n_bars=100)
    assert matched[0]["requested_at_bar"] == 99
    assert diags[0]["deferred_bars"] == 9


def test_derive_cal_matched_schedule_rejects_empty_schedule():
    with pytest.raises(tp.TimingPolicyError):
        tp.derive_cal_matched_schedule([], k_max_bars=10, seed=1, n_bars=100)


def test_derive_cal_matched_schedule_rejects_negative_requested_at_bar():
    base = [{"activation_id": "a@1", "params": {}, "requested_at_bar": -5}]
    with pytest.raises(tp.TimingPolicyError):
        tp.derive_cal_matched_schedule(base, k_max_bars=10, seed=1, n_bars=100)


def test_regime_timing_and_cal_matched_schedules_genuinely_differ_in_practice():
    """The real defect this redesign fixes: the old design was mathematically guaranteed to
    reproduce REGIME_TIMING's exact schedule. The new design must NOT, except by coincidence."""
    vol = _series([2.0, 2.0, 0.1, 2.0, 2.0, 2.0, 0.2, 2.0] * 20)
    base = [{"activation_id": "a@1", "params": {"x": 1}, "requested_at_bar": 0},
            {"activation_id": "a@2", "params": {"x": 2}, "requested_at_bar": 4}]
    regime_schedule, _diags = tp.derive_regime_timing_schedule(
        base, vol, threshold=1.0, k_max_bars=6, n_bars=len(vol))
    matched_schedule, _mdiags = tp.derive_cal_matched_schedule(
        base, k_max_bars=6, seed=tp.CAL_MATCHED_SEED, n_bars=len(vol))
    regime_bars = {e["activation_id"]: e["requested_at_bar"] for e in regime_schedule}
    matched_bars = {e["activation_id"]: e["requested_at_bar"] for e in matched_schedule}
    assert regime_bars != matched_bars
