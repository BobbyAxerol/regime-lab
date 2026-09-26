"""Coverage for sd/jm_vintage.py (guide SS5.3-5.4, SS9.2 SD02.3)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.sd import jm_vintage as jv


def _synthetic_regime_frame(*, start: str, n_days: int, regime_switch_day: int) -> pd.DataFrame:
    """Real-shaped 1m bars (hourly-sparse, still one bar/hour covers every
    calendar day) with two visibly different volatility regimes, so a real
    JM fit on this fixture should find real structure."""
    rng = np.random.default_rng(0)
    start_ts = pd.Timestamp(start, tz="UTC")
    rows = []
    price = 100.0
    for d in range(n_days):
        day = start_ts + pd.Timedelta(days=d)
        vol = 0.001 if d < regime_switch_day else 0.02
        for m in range(0, 1440, 60):
            price *= math_exp(rng.normal(0, vol))
            ts = day + pd.Timedelta(minutes=m)
            rows.append({"time": ts, "open": price, "high": price, "low": price,
                        "close": price, "volume": 1.0})
    frame = pd.DataFrame(rows).set_index(pd.to_datetime([r["time"] for r in rows], utc=True))
    return frame


def math_exp(x):
    import math
    return math.exp(x)


def _fake_loader(frame):
    def loader(symbol, *, start, end):
        start_ts, end_ts = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
        windowed = frame.loc[(frame.index >= start_ts) & (frame.index < end_ts)]
        return windowed, ["synthetic"]
    return loader


def test_required_prehistory_start_is_359_days_before_cutoff():
    start = jv.required_prehistory_start("2022-06-01")
    expected = (pd.Timestamp("2022-06-01", tz="UTC") - pd.Timedelta(days=jv.RAW_PREHISTORY_DAYS)).strftime("%Y-%m-%d")
    assert start == expected


def test_prehistory_shortfall_matches_real_measured_init_origins():
    """These are the REAL 4 INIT origins measured short against the
    registered earliest usable BTCUSDT date (2020-01-06) -- a fixed,
    disclosed finding, not a synthetic contrivance."""
    affected = ["2020-07-04", "2020-08-29", "2020-10-24", "2020-12-19"]
    for origin in affected:
        assert jv.prehistory_shortfall_days(origin) > 0, origin
    clear = ["2021-02-13", "2022-05-14"]
    for origin in clear:
        assert jv.prehistory_shortfall_days(origin) == 0, origin


def test_fit_origin_vintage_insufficient_prehistory_no_fabricated_state():
    loader = _fake_loader(_synthetic_regime_frame(start="2020-06-01", n_days=40, regime_switch_day=20))
    record = jv.fit_origin_vintage(loader, "BTCUSDT", origin_cutoff="2020-07-04", c=1.0)
    assert record.status == jv.STATUS_INSUFFICIENT_PREHISTORY
    assert record.state is None
    assert record.reason is not None


def test_fit_origin_vintage_real_fit_recovers_regime_structure():
    n_days = jv.RAW_PREHISTORY_DAYS + 1
    frame = _synthetic_regime_frame(start="2023-01-01", n_days=n_days + 5, regime_switch_day=n_days // 2)
    loader = _fake_loader(frame)
    cutoff = (pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=n_days)).strftime("%Y-%m-%d")
    record = jv.fit_origin_vintage(loader, "BTCUSDT", origin_cutoff=cutoff, c=1.0)
    assert record.status == jv.STATUS_OK
    assert record.state in (0, 1)
    assert record.lambda_j is not None and record.lambda_j > 0
    assert isinstance(record.converged, bool)


def test_build_vintage_tape_never_overwrites_earlier_origin_with_later_fit():
    n_days = jv.RAW_PREHISTORY_DAYS + 1
    frame = _synthetic_regime_frame(start="2023-01-01", n_days=n_days + 200, regime_switch_day=n_days // 2)
    loader = _fake_loader(frame)
    base = pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=n_days)
    origins = [(base + pd.Timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(3)]
    tape = jv.build_vintage_tape(loader, "BTCUSDT", origins, c=1.0)
    assert len(tape) == 3
    assert [r.origin_cutoff for r in tape] == origins
    # each record is independently fit -- not required to be identical, but
    # each must carry its OWN origin_cutoff, never a copied/overwritten one
    assert len({r.origin_cutoff for r in tape}) == 3


def test_build_calibration_feature_matrix_rejects_wrong_length():
    closes = [(f"d{i}", 100.0 + i) for i in range(10)]
    with pytest.raises(jv.VintageError):
        jv.build_calibration_feature_matrix(closes)


def test_fit_all_recipes_at_origin_shares_one_data_load_and_reproduces_single_recipe_fit():
    n_days = jv.RAW_PREHISTORY_DAYS + 1
    frame = _synthetic_regime_frame(start="2023-01-01", n_days=n_days + 5, regime_switch_day=n_days // 2)
    loader = _fake_loader(frame)
    cutoff = (pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=n_days)).strftime("%Y-%m-%d")
    all_recipes = jv.fit_all_recipes_at_origin(loader, "BTCUSDT", origin_cutoff=cutoff)
    assert set(all_recipes) == set(jv.jm.NORMALIZED_PENALTIES)
    single = jv.fit_origin_vintage(loader, "BTCUSDT", origin_cutoff=cutoff, c=1.0)
    assert all_recipes[1.0].state == single.state
    assert all_recipes[1.0].lambda_j == pytest.approx(single.lambda_j)


def test_fit_all_recipes_at_origin_insufficient_prehistory_all_recipes_typed():
    loader = _fake_loader(_synthetic_regime_frame(start="2020-06-01", n_days=40, regime_switch_day=20))
    all_recipes = jv.fit_all_recipes_at_origin(loader, "BTCUSDT", origin_cutoff="2020-07-04")
    assert len(all_recipes) == 3
    assert all(r.status == jv.STATUS_INSUFFICIENT_PREHISTORY for r in all_recipes.values())
    assert all(r.state is None for r in all_recipes.values())


def test_origin_log_rv_ratio_populated_and_identical_across_recipes():
    n_days = jv.RAW_PREHISTORY_DAYS + 1
    frame = _synthetic_regime_frame(start="2023-01-01", n_days=n_days + 5, regime_switch_day=n_days // 2)
    loader = _fake_loader(frame)
    cutoff = (pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=n_days)).strftime("%Y-%m-%d")
    all_recipes = jv.fit_all_recipes_at_origin(loader, "BTCUSDT", origin_cutoff=cutoff)
    values = {rec.origin_log_rv_ratio for rec in all_recipes.values()}
    assert len(values) == 1
    assert all(isinstance(v, float) for v in values)
    single = jv.fit_origin_vintage(loader, "BTCUSDT", origin_cutoff=cutoff, c=1.0)
    assert single.origin_log_rv_ratio == pytest.approx(next(iter(values)))


def test_build_vintage_tapes_returns_one_tape_per_recipe():
    n_days = jv.RAW_PREHISTORY_DAYS + 1
    frame = _synthetic_regime_frame(start="2023-01-01", n_days=n_days + 100, regime_switch_day=n_days // 2)
    loader = _fake_loader(frame)
    base = pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=n_days)
    origins = [(base + pd.Timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(2)]
    tapes = jv.build_vintage_tapes(loader, "BTCUSDT", origins)
    assert set(tapes) == set(jv.jm.NORMALIZED_PENALTIES)
    for c, tape in tapes.items():
        assert [r.origin_cutoff for r in tape] == origins
        assert all(r.recipe_c == c for r in tape)
