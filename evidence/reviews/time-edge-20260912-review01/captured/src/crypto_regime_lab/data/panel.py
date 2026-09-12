"""Feature panel assembly from a frozen snapshot (guide L03.4, L03.6).

Reads only from ``LAB_ROOT/snapshots/{id}``. Partitions are processed one at a
time and the resampled results concatenated, which keeps the working set far
inside the 4 GiB budget and gives the batch/stream equality the guide requires:
a month boundary is also a 15m/1h/4h bucket boundary, so per-partition
resampling must equal whole-series resampling exactly. That equality is a test,
not an assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import features as F
from .availability import annotate_availability, resample_bars, rules_for
from .inventory import PRODUCTS
from .quality import assess

REGIME_INTERVAL = "4h"          # guide 8.6 starting hypothesis
MARKET_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")

# Coverage decides membership, not ambition. Measured on this storage:
#   G1, G2, G5 cover all five symbols;
#   G3 needs the metrics product, which exists only for BTCUSDT and ETHUSDT;
#   G4 needs the book product, which exists only for BTCUSDT and only for weeks.
# So the PRIMARY core is G1+G2+G5 (8 features, inside guide 6.4's 8-12 budget) and
# the rest are cohort extensions, not silently-NaN core columns (guide 6.2).
PRIMARY_CORE_FEATURES = (
    "g1_rv_6", "g1_direction_6", "g1_efficiency_6",
    "g2_taker_imbalance", "g2_log_activity_30",
    "g5_dispersion_6", "g5_breadth_6", "g5_residual_return_30",
)
DERIVATIVES_EXTENSION_FEATURES = ("g3_dlog_oi", "g3_return_oi_interaction", "g3_basis")
LIQUIDITY_EXTENSION_FEATURES = ("g4_spread_bps", "g4_log_amihud_30")
REGISTERED_ALTERNATIVES = (
    "g1_downside_ratio_6", "g1_jump_concentration_6", "g2_trade_count_30",
    "g5_factor_concentration_30",
)
FEATURE_TIERS = {
    "primary_core": PRIMARY_CORE_FEATURES,
    "derivatives_extension": DERIVATIVES_EXTENSION_FEATURES,
    "liquidity_extension": LIQUIDITY_EXTENSION_FEATURES,
    "registered_alternative": REGISTERED_ALTERNATIVES,
}

# The core feature schema. Deliberately small: guide 6.4 sets a starting budget
# of roughly 8-12 active features, and adding more is a registered hypothesis.
FEATURE_SPECS: dict[str, F.FeatureSpec] = {
    s.name: s for s in (
        F.FeatureSpec("g1_rv_6", "G1", "local", 6, ("close",),
                      "realized volatility over 6 regime bars"),
        F.FeatureSpec("g1_direction_6", "G1", "local", 6, ("close",),
                      "sum(r)/sqrt(sum r^2): a direction descriptor",
                      caveat="not a t-statistic"),
        F.FeatureSpec("g1_efficiency_6", "G1", "local", 6, ("close",),
                      "|sum r| / sum|r|: separates directional from choppy volatility"),
        F.FeatureSpec("g1_downside_ratio_6", "G1", "local", 6, ("close",),
                      "share of realized variance from negative returns",
                      caveat="a variation ratio, not a crash probability"),
        F.FeatureSpec("g2_taker_imbalance", "G2", "local", None,
                      ("taker_buy_base_volume", "volume"),
                      "2*takerbuy/volume - 1 on the regime bar",
                      caveat="both sides of every trade exist; not net capital inflow"),
        F.FeatureSpec("g2_log_activity_30", "G2", "local", 30, ("quote_volume",),
                      "log(quote volume / trailing median)"),
        F.FeatureSpec("g2_trade_count_30", "G2", "local", 30, ("number_of_trades",),
                      "log(trade count / trailing median)"),
        F.FeatureSpec("g3_dlog_oi", "G3", "local", None, ("sum_open_interest",),
                      "change in log open interest",
                      caveat="a rise is not evidence of new longs"),
        F.FeatureSpec("g3_basis", "G3", "local", None, ("close", "spot_close"),
                      "F/S - 1 on synchronised closes",
                      caveat="requires a spot series for the same symbol"),
        F.FeatureSpec("g3_return_oi_interaction", "G3", "local", None,
                      ("close", "sum_open_interest"),
                      "one preregistered return x OI-change interaction"),
        F.FeatureSpec("g4_spread_bps", "G4", "local", None, ("spread_bps",),
                      "relative spread in basis points",
                      caveat="a missing snapshot is missing, never a zero spread"),
        F.FeatureSpec("g4_log_amihud_30", "G4", "local", 30, ("close", "quote_volume"),
                      "log of the rolling |r| / quote volume impact proxy",
                      caveat="a proxy, not a measured impact"),
        F.FeatureSpec("g1_jump_concentration_6", "G1", "local", 6, ("close",),
                      "largest squared return as a share of window variance"),
        F.FeatureSpec("g5_dispersion_6", "G5", "market", 6, ("market_returns",),
                      "cross-sectional dispersion of the eligible universe"),
        F.FeatureSpec("g5_breadth_6", "G5", "market", 6, ("market_returns",),
                      "share of the eligible universe with a positive trailing return"),
        F.FeatureSpec("g5_factor_concentration_30", "G5", "market", 30, ("market_returns",),
                      "first-eigenvalue share of a trailing covariance"),
        F.FeatureSpec("g5_residual_return_30", "G5", "local", 30, ("close", "market_returns"),
                      "return residual to a beta fitted on a PAST window only"),
    )
}


class PanelError(RuntimeError):
    """Raised when a panel cannot be built causally."""


@dataclass
class SymbolPanel:
    symbol: str
    frame: pd.DataFrame
    quality: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# Columns that MUST be float64 downstream regardless of how a partition stored
# them. Measured on this storage: SOLUSDT volume is int64 until 2024-12 and
# double after, and DOGEUSDT volume is int64 throughout. Reading those straight
# through would make a feature's dtype depend on which month it came from, and
# would truncate any fractional value that later appears.
FLOAT_COLUMNS = ("open", "high", "low", "close", "volume", "quote_volume",
                 "taker_buy_base_volume", "taker_buy_quote_volume",
                 "sum_open_interest", "sum_open_interest_value", "spread_bps")


def normalize_numeric_dtypes(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Coerce flow/price columns to float64 and report what had to be coerced."""
    out = frame.copy()
    coerced: dict[str, str] = {}
    for column in FLOAT_COLUMNS:
        if column in out.columns and out[column].dtype.kind != "f":
            coerced[column] = str(out[column].dtype)
            out[column] = out[column].astype("float64")
    return out, coerced


def snapshot_files(snapshot_root: Path, product_id: str, symbol: str) -> list[Path]:
    base = Path(snapshot_root) / product_id / symbol
    return sorted(base.glob("*.parquet")) if base.is_dir() else []


def load_resampled(snapshot_root: Path, product_id: str, symbol: str,
                   target_interval: str, *, fail_closed: bool = True,
                   quality_out: list[dict] | None = None,
                   closed_only: bool = True,
                   manifest: dict | None = None) -> pd.DataFrame:
    """Read a product partition by partition and resample to ``target_interval``."""
    spec = PRODUCTS[product_id]
    rules = rules_for(product_id, spec["kind"], target_interval)
    open_partitions = set()
    if closed_only and manifest is not None:
        open_partitions = {r["partition"] for r in manifest["files"]
                           if r["product_id"] == product_id and r["symbol"] == symbol
                           and not r["closed"]}

    chunks: list[pd.DataFrame] = []
    for path in snapshot_files(snapshot_root, product_id, symbol):
        if path.stem in open_partitions:
            continue                       # an open trailing partition is excluded, with a reason
        stored = pd.read_parquet(path)
        raw, coerced = normalize_numeric_dtypes(stored)
        report = assess(raw, product_id=product_id, symbol=symbol,
                        interval=spec["interval"], fail_closed=fail_closed)
        if quality_out is not None:
            quality_out.append({**report.as_record(), "partition": path.stem,
                                "stored_dtypes_coerced": coerced})
        if spec["interval"] == target_interval:
            chunk = raw.copy()
        else:
            chunk = resample_bars(raw, spec["interval"], target_interval, require_complete=True)
        chunks.append(chunk)
    if not chunks:
        raise PanelError(f"no closed partition for {product_id}/{symbol}")
    frame = pd.concat(chunks, ignore_index=True).sort_values("time").reset_index(drop=True)
    return annotate_availability(frame, rules)


def build_symbol_features(bars: pd.DataFrame) -> pd.DataFrame:
    """G1/G2/G4 local features on the regime bars of one symbol."""
    out = pd.DataFrame({"time": bars["time"], "available_at": bars["available_at"]})
    close = bars["close"].astype("float64")
    r = F.log_returns(close)
    out["ret"] = r
    out["perp_close"] = close
    out["g1_rv_6"] = F.realized_vol(r, 6)
    out["g1_direction_6"] = F.direction_descriptor(r, 6)
    out["g1_efficiency_6"] = F.path_efficiency(r, 6)
    out["g1_downside_ratio_6"] = F.downside_ratio(r, 6)
    out["g1_jump_concentration_6"] = F.jump_concentration(r, 6)
    if {"taker_buy_base_volume", "volume"} <= set(bars.columns):
        out["g2_taker_imbalance"] = F.taker_imbalance(
            bars["taker_buy_base_volume"].astype("float64"), bars["volume"].astype("float64"))
    if "quote_volume" in bars.columns:
        out["g2_log_activity_30"] = F.log_activity_ratio(
            bars["quote_volume"].astype("float64"), 30)
        out["g4_log_amihud_30"] = F.log_amihud_impact(r, bars["quote_volume"].astype("float64"), 30)
    if "number_of_trades" in bars.columns:
        out["g2_trade_count_30"] = F.trade_count_change(bars["number_of_trades"], 30)
    return out


def attach_derivatives(local: pd.DataFrame, metrics: pd.DataFrame | None) -> pd.DataFrame:
    """G3 from the metrics product, joined on availability."""
    out = local.copy()
    if metrics is None or metrics.empty:
        out["g3_dlog_oi"] = np.nan
        out["g3_return_oi_interaction"] = np.nan
        out["g3_source"] = "ABSENT"
        return out
    oi = metrics[["available_at", "sum_open_interest"]].sort_values("available_at")
    merged = pd.merge_asof(out.sort_values("available_at"), oi,
                           on="available_at", direction="backward")
    merged["g3_dlog_oi"] = F.delta_log_oi(merged["sum_open_interest"].astype("float64"))
    merged["g3_return_oi_interaction"] = F.return_oi_interaction(
        merged["ret"], merged["g3_dlog_oi"])
    merged["g3_source"] = "binance_futures_metrics_5m"
    return merged


def attach_basis(local: pd.DataFrame, spot: pd.DataFrame | None) -> pd.DataFrame:
    """G3 basis on synchronised closes; absent where the symbol has no spot product."""
    out = local.copy()
    if spot is None or spot.empty:
        out["g3_basis"] = np.nan
        out["g3_basis_source"] = "ABSENT_NO_SPOT_PRODUCT"
        return out
    ref = spot[["available_at", "close"]].rename(columns={"close": "spot_close"})
    merged = pd.merge_asof(out.sort_values("available_at"), ref.sort_values("available_at"),
                           on="available_at", direction="backward")
    merged["g3_basis"] = F.basis(merged["perp_close"], merged["spot_close"]) \
        if "perp_close" in merged.columns else np.nan
    merged["g3_basis_source"] = "crypto_binance_spot_1m"
    return merged


def build_market_context(symbol_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """G5 from the point-in-time eligible universe.

    A symbol enters the universe only from the bar it actually has data for, so
    breadth and dispersion are computed on who was tradeable THEN, not on
    today's survivor list (guide 6.2).
    """
    returns = pd.DataFrame({sym: f.set_index("time")["ret"] for sym, f in symbol_frames.items()})
    returns = returns.sort_index()
    eligible = returns.notna().sum(axis=1)
    market = pd.DataFrame(index=returns.index)
    market["eligible_symbols"] = eligible
    market["g5_dispersion_6"] = F.cross_sectional_dispersion(returns, 6)
    market["g5_breadth_6"] = F.breadth(returns, 6)
    market["g5_factor_concentration_30"] = F.common_factor_concentration(returns, 30)
    market["market_return"] = returns.mean(axis=1)
    return market.reset_index().rename(columns={"index": "time"})


def attach_market(local: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    merged = local.merge(market, on="time", how="left")
    beta, residual = F.rolling_beta_and_residual(merged["ret"], merged["market_return"], 30)
    merged["g5_beta_30"] = beta
    merged["g5_residual_return_30"] = residual
    return merged


def attach_liquidity(local: pd.DataFrame, book: pd.DataFrame | None) -> pd.DataFrame:
    """G4 from the book snapshot, joined on the real sample_time availability."""
    out = local.copy()
    if book is None or book.empty:
        out["g4_spread_bps"] = np.nan
        out["g4_source"] = "ABSENT_NO_BOOK_PRODUCT"
        return out
    ref = book[["available_at", "spread_bps"]].sort_values("available_at")
    merged = pd.merge_asof(out.sort_values("available_at"), ref,
                           on="available_at", direction="backward")
    merged["g4_spread_bps"] = merged["spread_bps"]
    merged["g4_source"] = "crypto_binance_orderbook_snapshot_1h"
    return merged


def feature_tier(name: str) -> str:
    for tier, members in FEATURE_TIERS.items():
        if name in members:
            return tier
    return "unassigned"


def core_feature_columns(frame: pd.DataFrame) -> list[str]:
    return [name for name in FEATURE_SPECS if name in frame.columns]


def tier_columns(frame: pd.DataFrame, tier: str) -> list[str]:
    return [n for n in FEATURE_TIERS[tier] if n in frame.columns]
