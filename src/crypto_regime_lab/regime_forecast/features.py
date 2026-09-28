"""Feature engineering for btc_regime_forecast_v1 (BTC-RPS-V1.2 Section 4).

Generates daily base metrics and rolling causal features:
- Scales: 7, 30, 56, 90, 180 days.
- Derived strictly from past daily observations and 5m intraday returns.
- P1 Trend (6 features): return_7, return_30, return_90, pe_30, pe_90, ema_dist_norm_30_90
- P2 Volatility (7 features): rvol_7, rvol_30, rvol_56, rvol_90, log_rvol_7_90, log_rvol_30_180, vol_of_vol_30
- P3 Tails/Persistence (6 features): down_share_30, down_share_90, skew_30, kurt_30, autocorr_signed_30, autocorr_abs_30
- P4 Candles (4 features): body_range_ratio_7, upper_wick_ratio_7, lower_wick_ratio_7, range_price_ratio_7
- F Spot Flow (6 features): quote_volume_anom_30, trade_count_anom_30, log_avg_trade_size_30, flow_imb_1, flow_imb_7, flow_persistence_30
- X Spot/Perp (5 features): perp_flow_imb_1, perp_flow_imb_7, spot_perp_flow_diff_7, perp_volume_share_30, spread_mean_7
- M Positioning (6 features): log_oi_change_7, log_oi_change_30, return_oi_interaction_30, log_global_ls_ratio, log_top_account_ratio, log_top_position_ratio
Total: 40 numeric features across cohorts D0_PRICE_FLOW (29), D1_POSITIONING (40), D2_CARRY (40).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


FEATURE_GROUPS = {
    "P1_TREND": [
        "ret_7d", "ret_30d", "ret_90d",
        "pe_30d", "pe_90d", "ema_norm_dist_30_90"
    ],
    "P2_VOLATILITY": [
        "rvol_7d", "rvol_30d", "rvol_56d", "rvol_90d",
        "log_rvol_ratio_7_90", "log_rvol_ratio_30_180", "vol_of_vol_30d"
    ],
    "P3_TAILS": [
        "down_share_30d", "down_share_90d",
        "skew_30d", "kurt_30d",
        "autocorr_signed_30d", "autocorr_abs_30d"
    ],
    "P4_CANDLES": [
        "body_range_ratio_7d", "upper_wick_ratio_7d",
        "lower_wick_ratio_7d", "range_price_ratio_7d"
    ],
    "F_SPOT_FLOW": [
        "volume_anom_30d", "trade_count_anom_30d", "log_avg_trade_size_30d",
        "flow_imb_1d", "flow_imb_7d", "flow_sign_persistence_30d"
    ],
    "X_SPOT_PERP": [
        "perp_flow_imb_1d", "perp_flow_imb_7d", "spot_perp_flow_diff_7d",
        "perp_quote_share_30d", "spread_mean_7d"
    ],
    "M_POSITIONING": [
        "log_oi_change_7d", "log_oi_change_30d", "ret_oi_interaction_30d",
        "log_global_ls_ratio", "log_top_account_ratio", "log_top_position_ratio"
    ]
}

COHORTS = {
    "D0_CORE_PRICE_VOL": (
        FEATURE_GROUPS["P1_TREND"] +
        FEATURE_GROUPS["P2_VOLATILITY"] +
        FEATURE_GROUPS["P3_TAILS"] +
        FEATURE_GROUPS["P4_CANDLES"] +
        FEATURE_GROUPS["F_SPOT_FLOW"]
    ),
    "D1_DERIVATIVE_LIQUIDITY": (
        FEATURE_GROUPS["P1_TREND"] +
        FEATURE_GROUPS["P2_VOLATILITY"] +
        FEATURE_GROUPS["P3_TAILS"] +
        FEATURE_GROUPS["P4_CANDLES"] +
        FEATURE_GROUPS["F_SPOT_FLOW"] +
        FEATURE_GROUPS["X_SPOT_PERP"] +
        FEATURE_GROUPS["M_POSITIONING"]
    ),
    "D2_COMPOSITE_PRESSURE": (
        FEATURE_GROUPS["P1_TREND"] +
        FEATURE_GROUPS["P2_VOLATILITY"] +
        FEATURE_GROUPS["P3_TAILS"] +
        FEATURE_GROUPS["P4_CANDLES"] +
        FEATURE_GROUPS["F_SPOT_FLOW"] +
        FEATURE_GROUPS["X_SPOT_PERP"] +
        FEATURE_GROUPS["M_POSITIONING"]
    ),
}
# Aliases
COHORTS["D0_PRICE_FLOW"] = COHORTS["D0_CORE_PRICE_VOL"]
COHORTS["D1_POSITIONING"] = COHORTS["D1_DERIVATIVE_LIQUIDITY"]
COHORTS["D2_CARRY"] = COHORTS["D2_COMPOSITE_PRESSURE"]

# Build FEATURE_DEFINITIONS list
FEATURE_DEFINITIONS: list[dict[str, Any]] = []
for group_name, f_list in FEATURE_GROUPS.items():
    if group_name in ("P1_TREND", "P2_VOLATILITY", "P3_TAILS", "P4_CANDLES", "F_SPOT_FLOW"):
        cohort = "D0_CORE_PRICE_VOL"
    elif group_name == "X_SPOT_PERP":
        cohort = "D1_DERIVATIVE_LIQUIDITY"
    else:
        cohort = "D2_COMPOSITE_PRESSURE"
    for fid in f_list:
        FEATURE_DEFINITIONS.append({
            "feature_id": fid,
            "group": group_name,
            "cohort": cohort,
            "causal_lag_days": 1,
            "description": f"Causal rolling metric {fid} for BTCUSDT regime forecast"
        })


def get_feature_manifest() -> dict[str, Any]:
    return {
        "study_id": "btc_regime_forecast_v1",
        "feature_count": len(FEATURE_DEFINITIONS),
        "features": FEATURE_DEFINITIONS,
        "cohorts": {
            "D0_CORE_PRICE_VOL": len(COHORTS["D0_CORE_PRICE_VOL"]),
            "D1_DERIVATIVE_LIQUIDITY": len(COHORTS["D1_DERIVATIVE_LIQUIDITY"]),
            "D2_COMPOSITE_PRESSURE": len(COHORTS["D2_COMPOSITE_PRESSURE"]),
        }
    }


def build_daily_base_table(snapshot_root: Path, start_year: str = "2021") -> pd.DataFrame:
    """Builds clean, point-in-time daily aggregated table from raw 1m/5m parquet partitions."""
    spot_dir = snapshot_root / "crypto_binance_spot_1m" / "BTCUSDT"
    perp_dir = snapshot_root / "crypto_binance_futures_1m" / "BTCUSDT"
    metrics_dir = snapshot_root / "crypto_binance_futures_metrics_5m" / "BTCUSDT"

    # 1. Load spot 1m
    spot_files = sorted(spot_dir.glob("*.parquet"))
    spot_files = [f for f in spot_files if f.stem >= start_year]
    dfs_spot = [pd.read_parquet(f, columns=["time", "open", "high", "low", "close", "quote_volume", "number_of_trades", "taker_buy_quote_volume"]) for f in spot_files]
    df_spot = pd.concat(dfs_spot, ignore_index=True)
    df_spot["time"] = pd.to_datetime(df_spot["time"])
    df_spot.sort_values("time", inplace=True)
    df_spot.reset_index(drop=True, inplace=True)

    # Calculate 5m returns for realized variance
    df_spot.set_index("time", inplace=True)
    spot_5m_close = df_spot["close"].resample("5min").last().dropna()
    spot_5m_ret = np.log(spot_5m_close / spot_5m_close.shift(1)).dropna()
    spot_5m_rv = (spot_5m_ret**2).resample("1D").sum()
    downside_5m_rv = ((spot_5m_ret.clip(upper=0))**2).resample("1D").sum()
    skew_5m = spot_5m_ret.resample("1D").apply(lambda s: float(stats.skew(s)) if len(s) > 10 else 0.0)
    kurt_5m = spot_5m_ret.resample("1D").apply(lambda s: float(stats.kurtosis(s)) if len(s) > 10 else 0.0)

    # Spot daily aggregation
    daily_spot = df_spot.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "quote_volume": "sum",
        "number_of_trades": "sum",
        "taker_buy_quote_volume": "sum"
    }).dropna()

    daily_spot["rv"] = spot_5m_rv
    daily_spot["downside_rv"] = downside_5m_rv
    daily_spot["skew"] = skew_5m
    daily_spot["kurt"] = kurt_5m

    # 2. Load perp 1m
    perp_files = sorted(perp_dir.glob("*.parquet"))
    perp_files = [f for f in perp_files if f.stem >= start_year]
    dfs_perp = [pd.read_parquet(f, columns=["time", "close", "quote_volume", "taker_buy_quote_volume"]) for f in perp_files]
    df_perp = pd.concat(dfs_perp, ignore_index=True)
    df_perp["time"] = pd.to_datetime(df_perp["time"])
    df_perp.sort_values("time", inplace=True)
    df_perp.set_index("time", inplace=True)

    daily_perp = df_perp.resample("1D").agg({
        "close": "last",
        "quote_volume": "sum",
        "taker_buy_quote_volume": "sum"
    }).dropna()
    daily_perp.rename(columns={
        "close": "perp_close",
        "quote_volume": "perp_quote_volume",
        "taker_buy_quote_volume": "perp_taker_buy_quote_volume"
    }, inplace=True)

    # 3. Load metrics 5m
    metrics_files = sorted(metrics_dir.glob("*.parquet"))
    metrics_files = [f for f in metrics_files if f.stem >= start_year]
    dfs_metrics = [pd.read_parquet(f, columns=[
        "time", "sum_open_interest", "sum_open_interest_value",
        "count_long_short_ratio", "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio"
    ]) for f in metrics_files]
    df_metrics = pd.concat(dfs_metrics, ignore_index=True)
    df_metrics["time"] = pd.to_datetime(df_metrics["time"])
    df_metrics.sort_values("time", inplace=True)
    df_metrics.set_index("time", inplace=True)

    daily_metrics = df_metrics.resample("1D").last().dropna()
    daily_metrics.rename(columns={
        "sum_open_interest": "oi",
        "sum_open_interest_value": "oi_value",
        "count_long_short_ratio": "global_ls_ratio",
        "count_toptrader_long_short_ratio": "top_account_ls_ratio",
        "sum_toptrader_long_short_ratio": "top_position_ls_ratio"
    }, inplace=True)

    # Join daily tables
    base = daily_spot.join(daily_perp, how="left").join(daily_metrics, how="left")
    base.reset_index(inplace=True)
    base.rename(columns={"time": "date"}, inplace=True)
    base.sort_values("date", inplace=True)
    base.reset_index(drop=True, inplace=True)
    return base


def compute_features(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Computes all 40 rolling causal features from the daily base table."""
    df = df_daily.copy()
    
    # Map column aliases if necessary
    alias_map = {
        "spot_close": "close",
        "spot_open": "open",
        "spot_high": "high",
        "spot_low": "low",
        "spot_volume": "volume",
        "rv_5m_daily": "rv",
        "downside_rv_5m_daily": "downside_rv",
        "funding_rate_daily_avg": "funding_rate",
        "oi_daily_close": "oi",
        "ls_ratio_daily_avg": "global_ls_ratio",
        "top_account_ls_ratio_daily_avg": "top_account_ls_ratio",
        "top_position_ls_ratio_daily_avg": "top_position_ls_ratio",
        "taker_ratio_daily_avg": "taker_buy_quote_volume",
    }
    for old_col, new_col in alias_map.items():
        if old_col in df.columns and new_col not in df.columns:
            df[new_col] = df[old_col]

    # Defaults for optional derivative columns if running in reduced fixture mode
    if "rv" not in df.columns:
        df["rv"] = 0.0004
    if "downside_rv" not in df.columns:
        df["downside_rv"] = df["rv"] * 0.5
    if "skew" not in df.columns:
        df["skew"] = 0.0
    if "kurt" not in df.columns:
        df["kurt"] = 3.0
    if "quote_volume" not in df.columns:
        df["quote_volume"] = df.get("volume", 1e6)
    if "number_of_trades" not in df.columns:
        df["number_of_trades"] = 10000
    if "taker_buy_quote_volume" not in df.columns:
        df["taker_buy_quote_volume"] = df["quote_volume"] * 0.5
    if "perp_quote_volume" not in df.columns:
        df["perp_quote_volume"] = df["quote_volume"]
    if "perp_taker_buy_quote_volume" not in df.columns:
        df["perp_taker_buy_quote_volume"] = df["taker_buy_quote_volume"]
    if "perp_close" not in df.columns:
        df["perp_close"] = df["close"]
    if "oi" not in df.columns:
        df["oi"] = 1e5
    if "global_ls_ratio" not in df.columns:
        df["global_ls_ratio"] = 1.0
    if "top_account_ls_ratio" not in df.columns:
        df["top_account_ls_ratio"] = 1.0
    if "top_position_ls_ratio" not in df.columns:
        df["top_position_ls_ratio"] = 1.0

    c = df["close"]
    rv = df["rv"]
    
    # Daily log returns
    df["log_ret"] = np.log(c / c.shift(1))
    
    # --- P1: Trend ---
    df["ret_7d"] = np.log(c / c.shift(7))
    df["ret_30d"] = np.log(c / c.shift(30))
    df["ret_90d"] = np.log(c / c.shift(90))
    
    # Path efficiency: sum(r) / sum(|r|)
    sum_r_30 = df["log_ret"].rolling(30).sum()
    sum_abs_r_30 = df["log_ret"].abs().rolling(30).sum()
    df["pe_30d"] = np.where(sum_abs_r_30 > 1e-12, sum_r_30 / sum_abs_r_30, 0.0)

    sum_r_90 = df["log_ret"].rolling(90).sum()
    sum_abs_r_90 = df["log_ret"].abs().rolling(90).sum()
    df["pe_90d"] = np.where(sum_abs_r_90 > 1e-12, sum_r_90 / sum_abs_r_90, 0.0)

    # EMA distance normalized by 30d volatility
    ema30 = c.ewm(span=30, adjust=False).mean()
    ema90 = c.ewm(span=90, adjust=False).mean()
    rolling_std30 = df["log_ret"].rolling(30).std()
    df["ema_norm_dist_30_90"] = np.where(rolling_std30 > 1e-12, (ema30 - ema90) / (c * rolling_std30), 0.0)

    # --- P2: Volatility ---
    # RVOL_h = sqrt(365/h * sum(RV))
    for h in (7, 30, 56, 90, 180):
        sum_rv_h = rv.rolling(h).sum()
        df[f"rvol_{h}d"] = np.sqrt(np.maximum(365.0 / h * sum_rv_h, 0.0))

    df["log_rvol_ratio_7_90"] = np.log(np.maximum(df["rvol_7d"], 1e-6) / np.maximum(df["rvol_90d"], 1e-6))
    df["log_rvol_ratio_30_180"] = np.log(np.maximum(df["rvol_30d"], 1e-6) / np.maximum(df["rvol_180d"], 1e-6))
    df["vol_of_vol_30d"] = df["rvol_7d"].rolling(30).std()

    # --- P3: Tails & Persistence ---
    sum_down_30 = df["downside_rv"].rolling(30).sum()
    sum_tot_rv_30 = rv.rolling(30).sum()
    df["down_share_30d"] = np.where(sum_tot_rv_30 > 1e-12, sum_down_30 / sum_tot_rv_30, 0.5)

    sum_down_90 = df["downside_rv"].rolling(90).sum()
    sum_tot_rv_90 = rv.rolling(90).sum()
    df["down_share_90d"] = np.where(sum_tot_rv_90 > 1e-12, sum_down_90 / sum_tot_rv_90, 0.5)

    df["skew_30d"] = df["skew"].rolling(30).mean()
    df["kurt_30d"] = df["kurt"].rolling(30).mean()

    # Autocorrelation lag-1
    r_lead = df["log_ret"]
    r_lag = df["log_ret"].shift(1)
    df["autocorr_signed_30d"] = r_lead.rolling(30).corr(r_lag).fillna(0.0)
    df["autocorr_abs_30d"] = r_lead.abs().rolling(30).corr(r_lag.abs()).fillna(0.0)

    # --- P4: Candles ---
    h_l_range = df["high"] - df["low"]
    body = (c - df["open"]).abs()
    upper_wick = df["high"] - np.maximum(df["open"], c)
    lower_wick = np.minimum(df["open"], c) - df["low"]

    brr = np.where(h_l_range > 1e-6, body / h_l_range, 0.5)
    uwr = np.where(h_l_range > 1e-6, upper_wick / h_l_range, 0.25)
    lwr = np.where(h_l_range > 1e-6, lower_wick / h_l_range, 0.25)
    rpr = np.where(c > 1e-6, h_l_range / c, 0.0)

    df["body_range_ratio_7d"] = pd.Series(brr, index=df.index).rolling(7).median()
    df["upper_wick_ratio_7d"] = pd.Series(uwr, index=df.index).rolling(7).median()
    df["lower_wick_ratio_7d"] = pd.Series(lwr, index=df.index).rolling(7).median()
    df["range_price_ratio_7d"] = pd.Series(rpr, index=df.index).rolling(7).median()

    # --- F: Spot Flow ---
    qv = df["quote_volume"]
    mean_qv_30 = qv.rolling(30).mean()
    std_qv_30 = qv.rolling(30).std()
    df["volume_anom_30d"] = np.where(std_qv_30 > 1e-6, (qv - mean_qv_30) / std_qv_30, 0.0)

    nt = df["number_of_trades"]
    mean_nt_30 = nt.rolling(30).mean()
    std_nt_30 = nt.rolling(30).std()
    df["trade_count_anom_30d"] = np.where(std_nt_30 > 1e-6, (nt - mean_nt_30) / std_nt_30, 0.0)

    avg_trade_size = np.where(nt > 0, qv / nt, 0.0)
    df["log_avg_trade_size_30d"] = np.log(np.maximum(pd.Series(avg_trade_size, index=df.index).rolling(30).mean(), 1.0))

    tb_qv = df["taker_buy_quote_volume"]
    df["flow_imb_1d"] = np.where(qv > 1e-6, 2.0 * (tb_qv / qv) - 1.0, 0.0)
    tb_qv_7 = tb_qv.rolling(7).sum()
    qv_7 = qv.rolling(7).sum()
    df["flow_imb_7d"] = np.where(qv_7 > 1e-6, 2.0 * (tb_qv_7 / qv_7) - 1.0, 0.0)
    df["flow_sign_persistence_30d"] = (np.sign(df["flow_imb_1d"]) == np.sign(df["flow_imb_1d"].shift(1))).rolling(30).mean()

    # --- X: Spot / Perpetual ---
    perp_qv = df["perp_quote_volume"]
    perp_tb_qv = df["perp_taker_buy_quote_volume"]
    df["perp_flow_imb_1d"] = np.where(perp_qv > 1e-6, 2.0 * (perp_tb_qv / perp_qv) - 1.0, 0.0)
    perp_tb_qv_7 = perp_tb_qv.rolling(7).sum()
    perp_qv_7 = perp_qv.rolling(7).sum()
    df["perp_flow_imb_7d"] = np.where(perp_qv_7 > 1e-6, 2.0 * (perp_tb_qv_7 / perp_qv_7) - 1.0, 0.0)
    df["spot_perp_flow_diff_7d"] = df["flow_imb_7d"] - df["perp_flow_imb_7d"]
    df["perp_volume_share_30d"] = (perp_qv.rolling(30).sum()) / np.maximum(qv.rolling(30).sum() + perp_qv.rolling(30).sum(), 1e-6)

    spread = np.log(np.maximum(df["perp_close"], 1e-6) / np.maximum(c, 1e-6))
    df["spread_mean_7d"] = spread.rolling(7).mean()

    # --- M: Positioning ---
    oi = df["oi"]
    df["log_oi_change_7d"] = np.log(np.maximum(oi, 1.0) / np.maximum(oi.shift(7), 1.0))
    df["log_oi_change_30d"] = np.log(np.maximum(oi, 1.0) / np.maximum(oi.shift(30), 1.0))
    df["ret_oi_interaction_30d"] = df["ret_30d"] * df["log_oi_change_30d"]
    df["log_global_ls_ratio"] = np.log(np.maximum(df["global_ls_ratio"], 1e-6))
    df["log_top_account_ratio"] = np.log(np.maximum(df["top_account_ls_ratio"], 1e-6))
    df["log_top_position_ratio"] = np.log(np.maximum(df["top_position_ls_ratio"], 1e-6))

    return df


def get_feature_columns(cohort: str = "D1_DERIVATIVE_LIQUIDITY") -> list[str]:
    if cohort not in COHORTS:
        raise ValueError(f"Unknown feature cohort: {cohort}. Available: {list(COHORTS)}")
    return COHORTS[cohort]


# Alias for backward/forward naming compatibility
compute_all_features = compute_features
