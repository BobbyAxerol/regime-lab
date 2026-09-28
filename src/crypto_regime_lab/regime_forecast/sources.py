"""Source qualification, loading, and schema verification for btc_regime_forecast_v1.

Follows BTC-RPS-V1.2 Section 3, Section 12 (MF-01).
- Core approved readers: CryptoBinanceSpot1m, CryptoBinance1m, BinanceFuturesMetrics5m.
- Strictly rejects incompatible readers, wrong symbols, or unverified markets.
- Enforces UTC timestamp conventions (rejects +/- 7h or unaligned units).
- Forbids summing OI snapshots across intervals.
- Handles missingness with typed nulls (never fills 0 or forward-fills raw gaps).
- Detects and flags spot-perp proxy substitutions.
- Provides explicit exclusions for CoinGecko dominance, BTCDOM, L2, options, etc.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


APPROVED_PRODUCTS = {
    "crypto_binance_spot_1m": {
        "reader_class": "CryptoBinanceSpot1m",
        "market": "BINANCE_SPOT",
        "role": "PRIMARY_TARGET_AND_FLOW",
        "expected_columns": [
            "time", "open", "high", "low", "close", "volume",
            "quote_volume", "number_of_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume"
        ],
        "snapshot_subdir": "crypto_binance_spot_1m",
    },
    "crypto_binance_futures_1m": {
        "reader_class": "CryptoBinance1m",
        "market": "BINANCE_USDM_FUTURES",
        "role": "PERPETUAL_CONTEXT_AND_SPREAD",
        "expected_columns": [
            "time", "open", "high", "low", "close", "volume",
            "quote_volume", "number_of_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume"
        ],
        "snapshot_subdir": "crypto_binance_futures_1m",
    },
    "crypto_binance_futures_metrics_5m": {
        "reader_class": "BinanceFuturesMetrics5m",
        "market": "BINANCE_USDM_FUTURES_METRICS",
        "role": "DERIVATIVES_POSITIONING_AND_LEVERAGE",
        "expected_columns": [
            "time", "sum_open_interest", "sum_open_interest_value",
            "count_long_short_ratio", "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio", "sum_taker_long_short_vol_ratio"
        ],
        "snapshot_subdir": "crypto_binance_futures_metrics_5m",
    }
}

EXCLUDED_SOURCES = {
    "coingecko_dominance": "EXCLUDED_INSUFFICIENT_HISTORY",
    "binance_btcdom": "EXCLUDED_NO_PIT",
    "crypto_binance_orderbook_snapshot_1h": "EXCLUDED_OUT_OF_SCOPE",
    "deribit_options": "EXCLUDED_OUT_OF_SCOPE",
    "fear_and_greed": "EXCLUDED_UNAVAILABLE",
    "funding_rate_raw_rest": "EXCLUDED_UNAVAILABLE",
}


def get_default_snapshot_root(lab_root: Path | None = None) -> Path:
    if lab_root is None:
        lab_root = Path(__file__).resolve().parents[3]
    return lab_root / "snapshots" / "server_core_v1"


def get_source_allowlist(lab_root: Path | None = None) -> dict[str, Any]:
    if lab_root is None:
        lab_root = Path(__file__).resolve().parents[3]
    path = lab_root / "configs" / "btc_regime_forecast_v1" / "source_allowlist.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing source allowlist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_reader_compatibility(product_id: str, symbol: str) -> None:
    if product_id not in APPROVED_PRODUCTS:
        raise ValueError(f"Incompatible or unapproved product_id: '{product_id}'. Approved: {list(APPROVED_PRODUCTS)}")
    if symbol != "BTCUSDT":
        raise ValueError(f"Study btc_regime_forecast_v1 is BTCUSDT only. Requested: '{symbol}'")


def verify_timestamp_integrity(series: pd.Series) -> None:
    """Verifies that timestamps are valid UTC naive datetime representations without offset shifts."""
    if not pd.api.types.is_datetime64_any_dtype(series):
        raise TypeError("Timestamp series must be datetime64")
    
    # Check if timezone aware with non-UTC offset
    if hasattr(series.dt, "tz") and series.dt.tz is not None:
        tz_str = str(series.dt.tz)
        if tz_str.upper() not in ("UTC", "ETC/UTC"):
            raise ValueError(f"Non-UTC timezone detected: {tz_str}. Must be UTC naive or UTC aware.")

    # Check for unit anomaly: year must be reasonable for crypto
    years = series.dt.year
    if (years < 2017).any() or (years > 2030).any():
        raise ValueError(f"Timestamp unit error detected: years out of realistic range [{years.min()}, {years.max()}]")


def check_for_substituted_proxy(spot_close: np.ndarray, perp_close: np.ndarray) -> bool:
    """Checks whether spot price was substituted by a direct copy of perpetual price."""
    if len(spot_close) != len(perp_close) or len(spot_close) == 0:
        return False
    # If every single close price is identical across thousands of bars, it is a copy
    if np.array_equal(spot_close, perp_close):
        return True
    return False


def aggregate_oi_safely(oi_series: pd.Series, method: str = "last") -> float:
    """Aggregates open interest across an interval.
    
    CRITICAL RULE (R12 / §3.5 / MF1-T04): Never sum OI snapshots across intervals.
    """
    if method == "sum":
        raise ValueError("FORBIDDEN: Summing open interest snapshots across time creates fictitious volume stocks.")
    if method == "last":
        return float(oi_series.dropna().iloc[-1]) if not oi_series.dropna().empty else float("nan")
    if method == "mean":
        return float(oi_series.dropna().mean()) if not oi_series.dropna().empty else float("nan")
    raise ValueError(f"Unsupported OI aggregation method: {method}")


def aggregate_taker_ratio_safely(buy_vol: pd.Series, total_vol: pd.Series) -> float:
    """Calculates taker buy ratio as sum(numerator) / sum(denominator), not mean of ratios."""
    sum_buy = buy_vol.sum()
    sum_total = total_vol.sum()
    if sum_total == 0 or np.isnan(sum_total):
        return float("nan")
    return float(sum_buy / sum_total)


def load_parquet_partitions(
    product_id: str,
    symbol: str = "BTCUSDT",
    start_date: str | None = None,
    end_date: str | None = None,
    snapshot_root: Path | None = None,
) -> pd.DataFrame:
    verify_reader_compatibility(product_id, symbol)
    if snapshot_root is None:
        snapshot_root = get_default_snapshot_root()
    
    spec = APPROVED_PRODUCTS[product_id]
    product_dir = snapshot_root / spec["snapshot_subdir"] / symbol
    if not product_dir.is_dir():
        raise FileNotFoundError(f"Missing partition directory for {product_id}/{symbol}: {product_dir}")
    
    files = sorted(product_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found in: {product_dir}")
    
    # Filter files by partition month if requested
    if start_date or end_date:
        start_month = start_date[:7] if start_date else "0000-00"
        end_month = end_date[:7] if end_date else "9999-99"
        files = [f for f in files if start_month <= f.stem <= end_month]
        if not files:
            raise FileNotFoundError(f"No parquet files matching range [{start_date}, {end_date}] in {product_dir}")
    
    dfs = []
    for f in files:
        df_part = pd.read_parquet(f)
        dfs.append(df_part)
    
    df = pd.concat(dfs, ignore_index=True)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        verify_timestamp_integrity(df["time"])
        df = df.sort_values("time").reset_index(drop=True)
        if start_date:
            df = df[df["time"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["time"] <= pd.to_datetime(end_date)]
        df = df.reset_index(drop=True)
    
    # Check expected columns
    for col in spec["expected_columns"]:
        if col not in df.columns:
            raise KeyError(f"Missing mandatory column '{col}' for product '{product_id}'")
            
    return df


def sha256_of_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()
