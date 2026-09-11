"""LAB-03 acceptance tests T21-T28 plus the data-layer modules.

Fixtures are synthetic where a property must be forced (a symbol before listing,
a mutated future); real snapshot partitions are used where the point is what the
storage actually contains.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.data import features as F
from crypto_regime_lab.data import panel as P
from crypto_regime_lab.data.availability import (
    annotate_availability, as_of_join, funding_events, resample_bars, rules_for,
    staleness_mask,
)
from crypto_regime_lab.data.quality import (
    DataQualityError, assess, check_close_time_trust, check_symbol_mapping, check_timestamps,
    check_units_and_dtypes,
)


@pytest.fixture(scope="module")
def snapshot_root(lab_root):
    root = lab_root / "snapshots" / "server_core_v1"
    if not (root / "manifest.json").is_file():
        pytest.skip("run scripts/snapshot_data.py")
    return root


@pytest.fixture(scope="module")
def manifest(snapshot_root):
    return json.loads((snapshot_root / "manifest.json").read_text())


def _bars(n=240, freq="1min", start="2024-01-01", volume=None, symbol="BTCUSDT"):
    idx = pd.date_range(start, periods=n, freq=freq)
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 0.2, n))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({
        "time": idx, "symbol": symbol, "open": open_,
        "high": np.maximum(open_, close) + 0.1, "low": np.minimum(open_, close) - 0.1,
        "close": close,
        "volume": np.full(n, 1.23456789) if volume is None else volume,
        "quote_volume": np.full(n, 1234.56789),
        "number_of_trades": np.arange(n) + 1,
        "taker_buy_base_volume": np.full(n, 0.6),
        "taker_buy_quote_volume": np.full(n, 600.0),
        "close_time": idx + pd.Timedelta("59.999s"),
        "source": "test", "ingested_at": pd.Timestamp("2026-01-01"),
    })


# =====================================================================
# T21 — fractional crypto volume
# =====================================================================

def test_t21_volume_stays_fractional_through_resampling():
    bars = _bars(240)
    checks = check_units_and_dtypes(bars)
    assert checks["volume"]["is_float"] and checks["volume"]["has_fractional_values"]
    out = resample_bars(bars, "1min", "1h")
    assert out["volume"].dtype.kind == "f"
    assert out["volume"].iloc[0] == pytest.approx(1.23456789 * 60, rel=1e-12)
    assert (out["volume"] % 1 != 0).all(), "a summed fractional volume must not become integral"


def test_t21_real_volume_granularity_is_per_symbol(snapshot_root):
    """Measured: BTC/ETH/BNB trade in fractional units; SOL and DOGE have a step of 1.

    Integral volume for SOL and DOGE is the instrument's real quantity step, NOT
    a truncation. The requirement is that the lab never truncates, which is what
    the next test checks.
    """
    from crypto_regime_lab.data.quality import check_quantity_granularity

    observed = {}
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"):
        files = sorted((snapshot_root / "crypto_binance_futures_1m" / symbol).glob("*.parquet"))
        per_era = {}
        for index in (5, 30, len(files) - 2):
            stored = pd.read_parquet(files[index], columns=["volume"])
            frame, coerced = P.normalize_numeric_dtypes(stored)
            assert frame["volume"].dtype.kind == "f", "the lab always presents float volume"
            per_era[files[index].stem] = check_quantity_granularity(frame)["integral_only"]
        observed[symbol] = per_era

    # Fractional throughout.
    for symbol in ("BTCUSDT", "ETHUSDT", "BNBUSDT"):
        assert not any(observed[symbol].values()), symbol
    # Integral throughout: DOGE's step really is 1.
    assert all(observed["DOGEUSDT"].values())
    # SOL's step CHANGED: integral early, fractional late.
    sol = list(observed["SOLUSDT"].values())
    assert sol[0] is True and sol[-1] is False, observed["SOLUSDT"]


def test_t21_stored_volume_dtype_varies_and_is_coerced(snapshot_root):
    """Measured: SOL stores volume as int64 until 2024-12, DOGE as int64 throughout.

    Reading that straight through would make a feature's dtype depend on which
    month it came from. The lab coerces on read and records the coercion.
    """
    import pyarrow.parquet as pq

    dtypes = {}
    for symbol in ("BTCUSDT", "SOLUSDT", "DOGEUSDT"):
        files = sorted((snapshot_root / "crypto_binance_futures_1m" / symbol).glob("*.parquet"))
        observed = {str(pq.ParquetFile(f).schema_arrow.field("volume").type) for f in files}
        dtypes[symbol] = observed
    assert dtypes["BTCUSDT"] == {"double"}
    assert dtypes["SOLUSDT"] == {"int64", "double"}, "SOL changes dtype mid-sample"
    assert dtypes["DOGEUSDT"] == {"int64"}

    early_sol = sorted((snapshot_root / "crypto_binance_futures_1m" / "SOLUSDT")
                       .glob("*.parquet"))[5]
    stored = pd.read_parquet(early_sol)
    assert stored["volume"].dtype.kind == "i"
    coerced_frame, coerced = P.normalize_numeric_dtypes(stored)
    assert coerced["volume"] == "int64"
    assert coerced_frame["volume"].dtype.kind == "f"


def test_t21_resampling_never_truncates_real_volume(snapshot_root):
    path = sorted((snapshot_root / "crypto_binance_futures_1m" / "BTCUSDT")
                  .glob("*.parquet"))[30]
    raw = pd.read_parquet(path)
    hourly = resample_bars(raw, "1min", "1h")
    first_hour = raw[raw["time"] < raw["time"].iloc[0] + pd.Timedelta("1h")]
    assert hourly["volume"].iloc[0] == pytest.approx(float(first_hour["volume"].sum()), rel=1e-15)
    assert hourly["number_of_trades"].iloc[0] == int(first_hour["number_of_trades"].sum())


# =====================================================================
# T22 — timestamp units and open/close labelling
# =====================================================================

def test_t22_bar_close_is_derived_not_read_from_close_time():
    bars = _bars(120)
    bars["close_time"] = pd.Timestamp("1970-01-01")        # the SOL/BNB defect
    rules = rules_for("crypto_binance_futures_1m", "ohlcv_bars", "1min")
    annotated = annotate_availability(bars, rules)
    assert (annotated["bar_close"] == annotated["bar_open"] + pd.Timedelta("1min")).all()
    assert (annotated["available_at"] == annotated["bar_close"]).all()


def test_t22_close_time_defect_is_detected_not_absorbed():
    bars = _bars(120)
    good = check_close_time_trust(bars, "1min")
    assert good["trusted"] is True and good["plausible_fraction"] == 1.0

    bars_epoch = bars.copy()
    bars_epoch["close_time"] = pd.Timestamp("1970-01-01")
    bad = check_close_time_trust(bars_epoch, "1min")
    assert bad["trusted"] is False and bad["epoch_unit_defect_rows"] == len(bars)

    bars_zero = bars.copy()
    bars_zero["close_time"] = bars_zero["time"]
    zero = check_close_time_trust(bars_zero, "1min")
    assert zero["trusted"] is False and zero["equal_to_open_rows"] == len(bars)


def test_t22_real_storage_close_time_defect_map(snapshot_root):
    """The defect is real on this storage, per symbol."""
    observed = {}
    for symbol in ("BTCUSDT", "SOLUSDT", "BNBUSDT"):
        path = sorted((snapshot_root / "crypto_binance_futures_1m" / symbol).glob("*.parquet"))[12]
        frame = pd.read_parquet(path, columns=["time", "close_time"])
        observed[symbol] = check_close_time_trust(frame, "1min")
    assert observed["BTCUSDT"]["trusted"] is True
    assert observed["SOLUSDT"]["trusted"] is False
    assert observed["BNBUSDT"]["trusted"] is False
    assert observed["BNBUSDT"]["epoch_unit_defect_rows"] > 0


def test_t22_time_column_is_on_the_interval_grid():
    checks = check_timestamps(_bars(120), "1min")
    assert checks["on_interval_grid"] and checks["off_grid_rows"] == 0
    assert checks["modal_step_seconds"] == 60.0
    assert checks["duplicate_timestamps"] == 0


def test_t22_off_grid_rows_are_reported():
    bars = _bars(60)
    bars.loc[10, "time"] = bars.loc[10, "time"] + pd.Timedelta("7s")
    checks = check_timestamps(bars, "1min")
    assert not checks["on_interval_grid"] and checks["off_grid_rows"] == 1


# =====================================================================
# T23 — symbol mapping is exact
# =====================================================================

def test_t23_symbol_column_must_match_the_request():
    bars = _bars(60, symbol="ETHUSDT")
    mapping = check_symbol_mapping(bars, "BTCUSDT")
    assert mapping["exact"] is False and mapping["observed"] == ["ETHUSDT"]
    with pytest.raises(DataQualityError, match="symbol"):
        assess(bars, product_id="p", symbol="BTCUSDT", interval="1min")


def test_t23_same_length_series_are_not_relabelled():
    """Two symbols of equal length but different timestamps must not be aligned by position."""
    a = _bars(120, start="2024-01-01", symbol="BTCUSDT")
    b = _bars(120, start="2024-03-01", symbol="ETHUSDT")
    assert len(a) == len(b)
    joined = a.merge(b, on="time", how="inner", suffixes=("_a", "_b"))
    assert joined.empty, "an inner join on time must find nothing; positions are not identities"


# =====================================================================
# T24 — nothing before listing
# =====================================================================

def test_t24_no_bars_are_fabricated_before_listing(manifest):
    starts = {}
    for record in manifest["files"]:
        if record["product_id"] != "crypto_binance_futures_1m":
            continue
        starts[record["symbol"]] = min(starts.get(record["symbol"], record["time_min"]),
                                       record["time_min"])
    assert starts["BTCUSDT"].startswith("2020-01-01")
    assert starts["SOLUSDT"].startswith("2020-09-14"), "SOL lists later; no earlier bar exists"
    assert starts["DOGEUSDT"].startswith("2020-07-10")
    assert starts["BNBUSDT"].startswith("2020-02-10")


def test_t24_market_breadth_uses_the_point_in_time_universe():
    """A symbol not yet listed must not count as a zero return."""
    idx = pd.date_range("2024-01-01", periods=10, freq="4h")
    returns = pd.DataFrame({"A": np.full(10, 0.01), "B": np.r_[[np.nan] * 5, np.full(5, -0.01)]},
                           index=idx)
    breadth = F.breadth(returns, 3)
    assert np.isnan(breadth.iloc[1])
    assert breadth.iloc[4] == pytest.approx(1.0), "only A is eligible before B lists"
    assert breadth.iloc[9] == pytest.approx(0.5)
    dispersion = F.cross_sectional_dispersion(returns, 3)
    assert np.isnan(dispersion.iloc[2]), "dispersion of one eligible symbol is undefined, not zero"


# =====================================================================
# T25 — a changed future must not change the past
# =====================================================================

@pytest.mark.parametrize("feature_fn,window", [
    (F.realized_vol, 6), (F.direction_descriptor, 6), (F.path_efficiency, 6),
    (F.downside_ratio, 6), (F.jump_concentration, 6),
])
def test_t25_trailing_features_are_causal(feature_fn, window):
    rng = np.random.default_rng(11)
    r = pd.Series(rng.normal(0, 0.01, 300))
    prefix_len = 200
    full = feature_fn(r, window)
    mutated = r.copy()
    mutated.iloc[prefix_len:] = rng.normal(0, 0.5, len(r) - prefix_len)
    mutated_full = feature_fn(mutated, window)
    assert np.allclose(full.iloc[:prefix_len].fillna(-999),
                       mutated_full.iloc[:prefix_len].fillna(-999))


def test_t25_resampling_a_longer_series_does_not_change_earlier_buckets():
    bars = _bars(600)
    short = resample_bars(bars.iloc[:300], "1min", "1h")
    long = resample_bars(bars, "1min", "1h")
    common = min(len(short), len(long))
    pd.testing.assert_frame_equal(short.iloc[:common - 1].reset_index(drop=True),
                                  long.iloc[:common - 1].reset_index(drop=True))


def test_t25_scaler_fitted_on_training_is_unaffected_by_future_rows():
    rng = np.random.default_rng(5)
    frame = pd.DataFrame({"time": pd.date_range("2020-01-01", periods=400, freq="4h"),
                          "x": rng.normal(0, 1, 400)})
    train = frame.iloc[:200]
    scaler_a = F.RobustScaler().fit(train, ["x"])
    frame_b = frame.copy()
    frame_b.loc[200:, "x"] = rng.normal(50, 20, 200)      # a wild future
    scaler_b = F.RobustScaler().fit(frame_b.iloc[:200], ["x"])
    assert scaler_a.median_["x"] == scaler_b.median_["x"]
    assert scaler_a.scale_["x"] == scaler_b.scale_["x"]


def test_t25_streamed_and_batch_resampling_agree():
    """Per-partition resampling must equal whole-series resampling (guide L03.6)."""
    bars = _bars(2880)                       # two days of 1m
    whole = resample_bars(bars, "1min", "4h")
    day1 = bars[bars["time"] < "2024-01-02"]
    day2 = bars[bars["time"] >= "2024-01-02"]
    streamed = pd.concat([resample_bars(day1, "1min", "4h"), resample_bars(day2, "1min", "4h")],
                         ignore_index=True)
    pd.testing.assert_frame_equal(whole.reset_index(drop=True), streamed.reset_index(drop=True))


# =====================================================================
# T26 — a snapshot is available when it was sampled
# =====================================================================

def test_t26_book_snapshot_uses_sample_time_not_the_hour_label():
    idx = pd.date_range("2026-08-10 18:00", periods=4, freq="1h")
    frame = pd.DataFrame({"time": idx, "symbol": "BTCUSDT",
                          "sample_time": idx + pd.Timedelta("7min37s"),
                          "spread_bps": [1.0, 1.1, 1.2, 1.3],
                          "source": "rest", "ingested_at": idx})
    rules = rules_for("crypto_binance_orderbook_snapshot_1h", "book_snapshot", "1h")
    out = annotate_availability(frame, rules)
    assert (out["available_at"] == out["sample_time"]).all()
    assert (out["available_at"] > out["bar_open"]).all(), "not available at the top of the hour"
    assert out["availability_basis"].eq("sample_time").all()


def test_t26_real_book_snapshot_is_never_available_before_its_label(snapshot_root):
    """Measured: samples land 0 to ~3593s after the hour label, one exactly on it.

    The requirement is that a snapshot is never available EARLIER than the hour
    it is filed under; the observed spread inside the hour is why the label must
    not be used as the availability timestamp.
    """
    files = sorted((snapshot_root / "crypto_binance_orderbook_snapshot_1h" / "BTCUSDT")
                   .glob("*.parquet"))
    frame = pd.concat([pd.read_parquet(f, columns=["time", "sample_time"]) for f in files])
    delta = (frame["sample_time"] - frame["time"]).dt.total_seconds()
    assert (delta >= 0).all(), "no snapshot may be available before its own hour"
    assert delta.max() > 1800, "samples really do land deep inside the hour"
    on_the_hour = int((delta == 0).sum())
    assert on_the_hour <= 1, f"{on_the_hour} snapshots landed exactly on the label"


def test_t26_staleness_ttl_masks_an_old_observation():
    available = pd.Series(pd.date_range("2024-01-01", periods=5, freq="1h"))
    as_of = pd.Series([pd.Timestamp("2024-01-01 04:00")] * 5)
    stale = staleness_mask(available, as_of, pd.Timedelta("2h"))
    assert stale.tolist() == [True, True, False, False, False]
    assert not staleness_mask(available, as_of, None).any()


# =====================================================================
# T27 — universe membership and source vintage are as-of
# =====================================================================

def test_t27_vintage_id_combines_source_and_ingest():
    bars = _bars(10)
    rules = rules_for("crypto_binance_futures_1m", "ohlcv_bars", "1min")
    out = annotate_availability(bars, rules)
    assert out["vintage_id"].iloc[0] == "test@20260101"
    assert out["archive_ingested_at"].notna().all()


def test_t27_as_of_join_never_reads_a_bucket_that_has_not_closed():
    base = pd.DataFrame({"available_at": pd.date_range("2024-01-01 00:00", periods=6, freq="1h")})
    other = pd.DataFrame({"available_at": pd.to_datetime(["2024-01-01 02:00", "2024-01-01 05:00"]),
                          "value": [10.0, 20.0]})
    merged = as_of_join(base, other, columns=["value"], ttl=None)
    assert merged["value"].tolist()[:2] == [pytest.approx(np.nan, nan_ok=True)] * 0 or True
    assert np.isnan(merged["value"].iloc[0]) and np.isnan(merged["value"].iloc[1])
    assert merged["value"].iloc[2] == 10.0 and merged["value"].iloc[4] == 10.0
    assert merged["value"].iloc[5] == 20.0


def test_t27_real_sources_are_recorded_per_product(manifest):
    sources = {}
    for record in manifest["files"]:
        sources.setdefault(record["product_id"], set()).update(record["sources"])
    assert "binance_vision_spot_monthly" in sources["crypto_binance_spot_1m"]
    assert sources["crypto_binance_futures_1m"], "the perpetual product must record its source"


# =====================================================================
# T28 — missing or stale enrichment is masked, never zero-filled
# =====================================================================

def test_t28_enrichment_is_inventoried_but_not_acquired():
    from crypto_regime_lab.data.enrichment import enrichment_inventory

    doc = enrichment_inventory()
    assert doc["acquired"] == []
    assert doc["primary_runs_without_it"] is True
    for name, spec in doc["sources"].items():
        assert spec["status"] == "NOT_ACQUIRED"
        assert spec["licence_check_required"] is True


def test_t28_missing_join_is_nan_not_zero():
    base = pd.DataFrame({"available_at": pd.date_range("2024-01-01", periods=4, freq="1h")})
    other = pd.DataFrame({"available_at": pd.to_datetime(["2024-01-01 03:00"]), "value": [5.0]})
    merged = as_of_join(base, other, columns=["value"], ttl=None)
    assert merged["missing"].tolist() == [True, True, True, False]
    assert not (merged["value"].fillna(-1) == 0).any(), "a missing value never becomes zero"


def test_t28_stale_values_are_dropped_by_ttl():
    base = pd.DataFrame({"available_at": pd.date_range("2024-01-01 00:00", periods=6, freq="1h")})
    other = pd.DataFrame({"available_at": pd.to_datetime(["2024-01-01 00:00"]), "value": [7.0]})
    merged = as_of_join(base, other, columns=["value"], ttl=pd.Timedelta("2h"))
    assert merged["value"].iloc[0] == 7.0
    assert np.isnan(merged["value"].iloc[5]), "beyond the TTL the value is dropped, not carried"
    assert merged["stale"].iloc[5]


def test_t28_funding_is_missing_and_never_zero(snapshot_root):
    doc = funding_events(snapshot_root)
    assert doc["status"] == "MISSING" and doc["events"] == []
    assert "NEVER treated as zero carry" in doc["policy"]


def test_t28_taker_imbalance_is_undefined_at_zero_volume():
    taker = pd.Series([1.0, 2.0, 0.0])
    volume = pd.Series([2.0, 4.0, 0.0])
    out = F.taker_imbalance(taker, volume)
    assert out.iloc[0] == 0.0 and out.iloc[1] == 0.0
    assert np.isnan(out.iloc[2]), "zero volume is undefined, never a balanced 0"
