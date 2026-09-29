"""Volatility and regime forecasting engine for Volatility-Conditioned WFO (Phase VWFO-03).

Follows VOL-WFO-V1.0 Section 8 and Section 14:
- Precomputes and caches causal H14 volatility forecasts using M4_LGBM_CONSERVATIVE_SLOW
  (38 features, median imputation from training prefix 2022-01-14 to 2024-01-13,
  temperature scaling T_V = 3.946).
- Strictly past-only training: at origin t_origin, uses only labels matured strictly before
  t_origin (i.e. <= t_origin - 15 days).
- Implements persistence baseline p_PERSIST for O_PERSIST.
- Implements stationary Markov pseudo-probability generator for P_NI_01..03.
- Normalizes context z^F_k = (p_LOW,k - p_mean) / s_train with floor s_train >= 0.05.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd

from crypto_regime_lab.regime_forecast.features import build_daily_base_table, compute_features

VOL_CLASSES = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]


def compute_targets_for_horizons(df_daily: pd.DataFrame, horizons: List[int]) -> pd.DataFrame:
    """Computes continuous forward realized volatility targets."""
    df = df_daily.copy()
    if "date" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

    rv_col = "rv" if "rv" in df.columns else "rv_5m_daily"
    targets = pd.DataFrame(index=df.index)

    for h in horizons:
        v_vals = np.full(len(df), np.nan)
        dates = df.index
        for i, dt in enumerate(dates):
            s_start = dt + pd.Timedelta(days=1)
            s_end = s_start + pd.Timedelta(days=h)
            sub = df.loc[s_start : s_end - pd.Timedelta(days=1)]
            if len(sub) == h:
                sum_rv = sub[rv_col].sum()
                v = np.sqrt(365.0 / h * sum_rv)
                v_vals[i] = v
        targets[f"target_v_h{h}"] = v_vals
        targets[f"target_log_v_h{h}"] = np.log(np.maximum(v_vals, 1e-6))
    return targets


def derive_volatility_quantiles(
    targets_df: pd.DataFrame, prefix_start: str, prefix_end: str, horizons: List[int]
) -> Dict[int, Tuple[float, float]]:
    """Derives tertiles (33.3%, 66.7%) of log volatility strictly on training prefix."""
    sub = targets_df.loc[prefix_start:prefix_end]
    tax = {}
    for h in horizons:
        col = f"target_log_v_h{h}"
        valid = sub[col].dropna()
        q1 = float(np.percentile(valid, 33.333333))
        q2 = float(np.percentile(valid, 66.666667))
        tax[h] = (q1, q2)
    return tax


def label_volatility(log_v: float, q1: float, q2: float) -> str:
    """Labels volatility tertile based on frozen training tertiles."""
    if np.isnan(log_v):
        return "UNKNOWN"
    if log_v <= q1:
        return "LOW_VOL"
    elif log_v <= q2:
        return "MID_VOL"
    else:
        return "HIGH_VOL"


def temperature_scale_probs(raw_probs: np.ndarray, temperature: float = 3.946) -> np.ndarray:
    """Applies temperature scaling to raw probability vector."""
    t = max(temperature, 0.1)
    eps = 1e-12
    p = np.clip(raw_probs, eps, 1.0 - eps)
    logits = np.log(p) / t
    logits -= np.max(logits)
    exp_logits = np.exp(logits)
    return exp_logits / np.sum(exp_logits)


class MarkovNoInfoGenerator:
    """Stationary AR(1) / Gaussian Markov process calibrated strictly on INIT prefix."""

    def __init__(self, mu: float = 0.333, sigma: float = 0.035, rho: float = 0.20) -> None:
        self.mu = mu
        self.sigma = sigma
        self.rho = rho

    def generate_series(self, origins: List[str], seed: int) -> Dict[str, float]:
        """Generates deterministic pseudo p_LOW sequence for given origins."""
        rng = np.random.RandomState(seed)
        x = rng.randn()
        vals: Dict[str, float] = {}
        for o in origins:
            x = self.rho * x + np.sqrt(max(1.0 - self.rho**2, 1e-4)) * rng.randn()
            p = float(np.clip(self.mu + self.sigma * x, 0.05, 0.95))
            vals[o] = p
        return vals


class H14ForecastEngine:
    """Causal volatility forecasting engine for all WFO origins."""

    def __init__(
        self,
        snapshot_root: Path,
        cache_dir: Optional[Path] = None,
        model_manifest_path: Optional[Path] = None,
    ) -> None:
        self.snapshot_root = snapshot_root
        self.cache_dir = cache_dir or (snapshot_root.parent.parent / "evidence" / "btc_volatility_conditioned_wfo_v1" / "forecast_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.model_manifest_path = model_manifest_path or (
            snapshot_root.parent.parent / "configs" / "btc_volatility_conditioned_wfo_v1" / "model_manifest.json"
        )
        self.manifest = self._load_manifest()
        self.df_daily: Optional[pd.DataFrame] = None
        self.df_feats: Optional[pd.DataFrame] = None
        self.targets_df: Optional[pd.DataFrame] = None
        self.tax_quantiles: Optional[Tuple[float, float]] = None
        self.cached_forecasts: Dict[str, Dict[str, Any]] = {}
        self._load_or_build_data()

    def _load_manifest(self) -> Dict[str, Any]:
        if self.model_manifest_path.is_file():
            return json.loads(self.model_manifest_path.read_text(encoding="utf-8"))
        return {
            "recipe_id": "M4_LGBM_CONSERVATIVE_SLOW",
            "temperature_scaling": {"T_V": 3.946},
            "model_parameters": {
                "objective": "multiclass",
                "num_class": 3,
                "boosting_type": "gbdt",
                "num_leaves": 7,
                "max_depth": 3,
                "learning_rate": 0.015,
                "n_estimators": 80,
                "min_child_samples": 40,
                "subsample": 0.8,
                "colsample_bytree": 0.65,
                "random_state": 20260928,
                "verbose": -1,
            },
        }

    def _load_or_build_data(self) -> None:
        cache_base = self.cache_dir / "daily_base.parquet"
        cache_feats = self.cache_dir / "daily_features.parquet"
        cache_targets = self.cache_dir / "daily_targets.parquet"

        if cache_base.is_file() and cache_feats.is_file() and cache_targets.is_file():
            self.df_daily = pd.read_parquet(cache_base)
            self.df_feats = pd.read_parquet(cache_feats)
            self.targets_df = pd.read_parquet(cache_targets)
        else:
            df_daily = build_daily_base_table(self.snapshot_root, start_year="2021")
            df_daily["date"] = pd.to_datetime(df_daily["date"])
            df_daily.set_index("date", inplace=True)
            df_feats = compute_features(df_daily)
            targets_df = compute_targets_for_horizons(df_daily, [14])

            # Derive tertiles on training prefix
            tax = derive_volatility_quantiles(targets_df, "2022-01-14", "2024-01-13", [14])
            q1, q2 = tax[14]
            targets_df["label_v_h14"] = [label_volatility(val, q1, q2) for val in targets_df["target_log_v_h14"]]

            df_daily.to_parquet(cache_base)
            df_feats.to_parquet(cache_feats)
            targets_df.to_parquet(cache_targets)

            self.df_daily = df_daily
            self.df_feats = df_feats
            self.targets_df = targets_df

        tax = derive_volatility_quantiles(self.targets_df, "2022-01-14", "2024-01-13", [14])
        self.tax_quantiles = tax[14]

        # Load forecast cache if exists
        fc_path = self.cache_dir / "forecast_packets.json"
        if fc_path.is_file():
            self.cached_forecasts = json.loads(fc_path.read_text(encoding="utf-8"))

    def get_forecast_for_origin(self, origin_date: str) -> Dict[str, Any]:
        """Returns causal forecast packet for origin_date (YYYY-MM-DD)."""
        if origin_date in self.cached_forecasts:
            return self.cached_forecasts[origin_date]

        t_origin = pd.to_datetime(origin_date)
        # Causal training window: only labels matured strictly before origin
        max_train_date = t_origin - pd.Timedelta(days=15)
        train_mask = (self.targets_df.index >= pd.to_datetime("2022-01-14")) & (self.targets_df.index <= max_train_date)
        train_sub = self.targets_df.loc[train_mask]

        X_train = self.df_feats.loc[train_mask].values
        y_train = [VOL_CLASSES.index(l) for l in train_sub["label_v_h14"]]

        mp = self.manifest.get("model_parameters", {})
        clf = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            boosting_type=mp.get("boosting_type", "gbdt"),
            num_leaves=mp.get("num_leaves", 7),
            max_depth=mp.get("max_depth", 3),
            learning_rate=mp.get("learning_rate", 0.015),
            n_estimators=mp.get("n_estimators", 80),
            min_child_samples=mp.get("min_child_samples", 40),
            subsample=mp.get("subsample", 0.8),
            colsample_bytree=mp.get("colsample_bytree", 0.65),
            random_state=mp.get("random_state", 20260928),
            verbosity=-1,
            n_jobs=1,
        )
        clf.fit(X_train, y_train)

        x_test = self.df_feats.loc[[t_origin]].values
        raw_p = clf.predict_proba(x_test)[0]

        t_v = float(self.manifest.get("temperature_scaling", {}).get("T_V", 3.946))
        scaled_p = temperature_scale_probs(raw_p, temperature=t_v)

        # Persistence baseline
        q1, q2 = self.tax_quantiles
        sub_past = self.df_daily.loc[:t_origin].iloc[-14:]
        rv_past = sub_past["rv"].sum() if "rv" in sub_past.columns else 0.0004 * 14
        v_past = np.sqrt(365.0 / 14 * rv_past)
        past_label = label_volatility(np.log(max(v_past, 1e-6)), q1, q2)
        p_persist = 0.70 if past_label == "LOW_VOL" else 0.15

        packet = {
            "origin": origin_date,
            "recipe_id": self.manifest.get("recipe_id", "M4_LGBM_CONSERVATIVE_SLOW"),
            "p_LOW": float(scaled_p[0]),
            "p_MID": float(scaled_p[1]),
            "p_HIGH": float(scaled_p[2]),
            "p_PERSIST": float(p_persist),
            "past_label": past_label,
            "train_samples": int(len(train_sub)),
            "max_train_date": max_train_date.strftime("%Y-%m-%d"),
        }
        self.cached_forecasts[origin_date] = packet
        self._persist_cache()
        return packet

    def _persist_cache(self) -> None:
        fc_path = self.cache_dir / "forecast_packets.json"
        fc_path.write_text(json.dumps(self.cached_forecasts, indent=2), encoding="utf-8")


def standardize_context_vector(
    historical_p_lows: List[float],
    current_p_low: float,
    min_std_floor: float = 0.05,
) -> Tuple[List[float], float, Dict[str, Any]]:
    """Standardizes past and current p_LOW into z^F_k strictly using past statistics.

    If sample std of past p_LOWs is below min_std_floor, flags CONTEXT_VARIATION_LOW
    and zeros out the context correction to prevent artificial amplification.
    """
    if len(historical_p_lows) < 2:
        return [0.0] * len(historical_p_lows), 0.0, {"flag": "INSUFFICIENT_HISTORY", "std": 0.0, "mean": 0.0}

    arr = np.array(historical_p_lows, dtype=np.float64)
    p_mean = float(np.mean(arr))
    p_std = float(np.std(arr, ddof=1))

    if p_std < min_std_floor:
        return (
            [0.0] * len(historical_p_lows),
            0.0,
            {
                "flag": "CONTEXT_VARIATION_LOW",
                "std": p_std,
                "mean": p_mean,
                "min_std_floor": min_std_floor,
            },
        )

    z_hist = [(p - p_mean) / p_std for p in historical_p_lows]
    z_curr = (current_p_low - p_mean) / p_std
    return z_hist, z_curr, {"flag": "VALID_CONTEXT", "std": p_std, "mean": p_mean}
