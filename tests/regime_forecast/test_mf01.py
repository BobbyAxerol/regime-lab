"""Tests for Phase MF-01: Data qualification, scope, and source exclusion.

Covers MF1-T01 through MF1-T08 per BTC-RPS-V1.2 Section 12.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.regime_forecast import sources, timeline, verifier_mf01


@pytest.fixture
def lab_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_mf1_t01_incompatible_reader_rejected(lab_root):
    """MF1-T01: Reader incompatible hoặc sai market/symbol bị từ chối, không bypass manifest."""
    # Wrong symbol
    with pytest.raises(ValueError, match="BTCUSDT only"):
        sources.verify_reader_compatibility("crypto_binance_spot_1m", "ETHUSDT")
        
    # Unapproved reader product
    with pytest.raises(ValueError, match="Incompatible or unapproved product_id"):
        sources.verify_reader_compatibility("unapproved_vendor_reader", "BTCUSDT")
        
    # Correct reader and symbol passes
    sources.verify_reader_compatibility("crypto_binance_spot_1m", "BTCUSDT")
    sources.verify_reader_compatibility("crypto_binance_futures_1m", "BTCUSDT")
    sources.verify_reader_compatibility("crypto_binance_futures_metrics_5m", "BTCUSDT")


def test_mf1_t02_coingecko_excluded_core_runs(lab_root):
    """MF1-T02: CoinGecko thiếu lịch sử được EXCLUDED; core build vẫn chạy."""
    allowlist = sources.get_source_allowlist(lab_root)
    excluded = allowlist.get("excluded_sources", {})
    
    assert "coingecko_dominance" in excluded
    assert excluded["coingecko_dominance"]["status"] == "EXCLUDED_INSUFFICIENT_HISTORY"
    assert "Public API limited to 365 days" in excluded["coingecko_dominance"]["reason"]
    
    # Core approved sources still exist and are qualified
    approved = allowlist.get("approved_sources", {})
    assert "crypto_binance_spot_1m" in approved
    assert approved["crypto_binance_spot_1m"]["status"] == "QUALIFIED_AVAILABLE"


def test_mf1_t03_timestamp_unit_and_timezone_detected():
    """MF1-T03: Sai timestamp unit/timezone bị phát hiện; aware/naive conversion giữ đúng thời điểm."""
    # Non-UTC timezone should raise ValueError
    ts_non_utc = pd.Series(pd.date_range("2022-01-01", periods=5, freq="D", tz="Asia/Ho_Chi_Minh"))
    with pytest.raises(ValueError, match="Non-UTC timezone detected"):
        sources.verify_timestamp_integrity(ts_non_utc)
        
    # Out of bounds unit error (e.g. milliseconds interpreted as nanoseconds -> year 1970)
    ts_bad_unit = pd.Series(pd.to_datetime([1640995200, 1641081600], unit="ns")) # 1970
    with pytest.raises(ValueError, match="Timestamp unit error detected"):
        sources.verify_timestamp_integrity(ts_bad_unit)
        
    # Valid UTC naive datetime
    ts_valid = pd.Series(pd.date_range("2022-01-01", periods=5, freq="D"))
    sources.verify_timestamp_integrity(ts_valid)


def test_mf1_t04_oi_aggregation_and_taker_ratio():
    """MF1-T04: Không cộng OI snapshots; ratios và volumes dùng đúng đơn vị, aggregation."""
    # Summing OI snapshots is strictly forbidden
    oi_series = pd.Series([50000.0, 51000.0, 52000.0, 51500.0])
    with pytest.raises(ValueError, match="FORBIDDEN: Summing open interest snapshots"):
        sources.aggregate_oi_safely(oi_series, method="sum")
        
    # Last observation is correct
    assert sources.aggregate_oi_safely(oi_series, method="last") == 51500.0
    assert sources.aggregate_oi_safely(oi_series, method="mean") == 51125.0
    
    # Taker buy ratio is sum(num)/sum(denom), not average of ratios
    buy_vol = pd.Series([10.0, 20.0, 30.0])
    total_vol = pd.Series([20.0, 50.0, 100.0])
    ratio = sources.aggregate_taker_ratio_safely(buy_vol, total_vol)
    expected = 60.0 / 170.0
    assert abs(ratio - expected) < 1e-9


def test_mf1_t05_null_handling_no_fake_zeros():
    """MF1-T05: Source gaps/null không bị đổi thành zero hoặc series forward-filled giả."""
    # An empty or completely NaN OI series must return NaN, never 0.0
    empty_oi = pd.Series([np.nan, np.nan])
    result = sources.aggregate_oi_safely(empty_oi, method="last")
    assert np.isnan(result)


def test_mf1_t06_proxy_spot_perp_detection():
    """MF1-T06: Proxy/substituted spot–perpetual data được flag, không tạo spread signal giả."""
    spot_real = np.array([30000.0, 30100.0, 30050.0, 30200.0])
    perp_real = np.array([30005.0, 30095.0, 30052.0, 30210.0])
    
    # Real spot and perp should NOT be flagged as proxy copy
    assert not sources.check_for_substituted_proxy(spot_real, perp_real)
    
    # An exact duplicate copy must be detected
    spot_fake = perp_real.copy()
    assert sources.check_for_substituted_proxy(spot_fake, perp_real)


def test_mf1_t07_timeline_and_coverage_reproducible(lab_root):
    """MF1-T07: Timeline và field coverage tái lập từ raw refs, không chọn ngày theo outcome."""
    spec = timeline.load_timeline_spec(lab_root)
    result = timeline.verify_timeline_integrity(spec)
    
    assert result["all_pass"] is True
    # Verify exact counts
    dev_sched = timeline.build_evaluation_schedule("development", spec)
    assert len(dev_sched) == 48
    test_sched = timeline.build_evaluation_schedule("locked_test", spec)
    assert len(test_sched) == 48
    
    # Check block structure
    assert dev_sched[0]["block_index"] == 0
    assert dev_sched[47]["block_index"] == 11
    assert test_sched[0]["block_index"] == 0
    assert test_sched[47]["block_index"] == 11


def test_mf1_t08_protected_paths_and_verifier(lab_root):
    """MF1-T08: Protected paths không bị sửa; exports có bytes/hash thật, không empty-file PASS."""
    # Verifier gates should pass
    result = verifier_mf01.verify_mf01(lab_root)
    assert result["overall"] == "PASS"
    assert result["gates"]["G1-SOURCE"]["pass"] is True
    assert result["gates"]["G1-EXCLUDE"]["pass"] is True
    assert result["gates"]["G1-TIMELINE"]["pass"] is True
    assert result["gates"]["G1-EVIDENCE"]["pass"] is True
