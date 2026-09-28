"""Target definitions, taxonomy freezing, and ground truth labeling for btc_regime_forecast_v1.

Follows BTC-RPS-V1.2 Section 5, Section 13 (MF-02).
- Candidate horizons: H in {56, 90} calendar days.
- Target start: s = T + ready_lag_days (default ready_lag = 1 day).
- Target window: [s, s + H).
- Future realized volatility: V_{T,H} = sqrt(365/H * sum_{d=s}^{s+H-1} RV_d), Z^V = log(V).
- Future path efficiency: E_{T,H} = sum(r_d) / sum(|r_d|).
- Taxonomy frozen from mature initial training history:
  - Volatility 3-class: LOW_VOL, MID_VOL, HIGH_VOL via q_1/3 and q_2/3 of Z^V.
  - Path efficiency 3-class: TREND_FRIENDLY, RANGE_NEUTRAL, CHOP_HOSTILE (or DIRECTIONAL_DOWN, LOW_EFFICIENCY, DIRECTIONAL_UP).
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


VOLATILITY_CLASSES = ("LOW_VOL", "MID_VOL", "HIGH_VOL")
EFFICIENCY_CLASSES = ("TREND_FRIENDLY", "RANGE_NEUTRAL", "CHOP_HOSTILE")


def compute_forward_targets(
    df_daily: pd.DataFrame,
    horizons: Union[int, List[int], Tuple[int, ...]] = (56, 90),
    origin_date: Optional[str] = None,
    ready_lag_days: int = 1,
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """Compute exact continuous forward targets V_{T,H} and E_{T,H}.
    
    If origin_date is provided, returns dict for that single origin.
    Otherwise returns DataFrame indexed like df_daily with forward target columns.
    """
    if isinstance(horizons, int):
        horizons_list = [horizons]
    else:
        horizons_list = list(horizons)

    df = df_daily.copy()
    if "date" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # If single origin requested
    if origin_date is not None:
        t_origin = pd.to_datetime(origin_date)
        res = {"origin_date": origin_date, "valid": True}
        for h in horizons_list:
            s_start = t_origin + pd.Timedelta(days=ready_lag_days)
            s_end = s_start + pd.Timedelta(days=h)
            sub = df.loc[s_start:s_end - pd.Timedelta(days=1)]
            if len(sub) < h:
                res[f"H{h}"] = {"valid": False, "reason": f"INCOMPLETE: {len(sub)}/{h}"}
            else:
                rv_col = "rv_5m_daily" if "rv_5m_daily" in sub.columns else ("rv" if "rv" in sub.columns else None)
                if rv_col is not None:
                    sum_rv = sub[rv_col].sum()
                    v = float(np.sqrt(365.0 / h * sum_rv))
                else:
                    v = float("nan")
                
                close_col = "spot_close" if "spot_close" in sub.columns else ("close" if "close" in sub.columns else None)
                if close_col is not None:
                    rets = np.log(sub[close_col] / sub[close_col].shift(1)).dropna()
                    sum_r = float(rets.sum())
                    sum_abs = float(rets.abs().sum())
                    e = float(sum_r / sum_abs) if sum_abs > 1e-12 else 0.0
                else:
                    e = float("nan")
                
                res[f"H{h}"] = {
                    "valid": True,
                    "volatility": v,
                    "log_volatility": float(np.log(max(v, 1e-6))),
                    "efficiency": e,
                }
        return res

    # Vectorized / rolling forward calculation for all dates
    res_df = pd.DataFrame(index=df.index)
    rv_col = "rv_5m_daily" if "rv_5m_daily" in df.columns else ("rv" if "rv" in df.columns else None)
    close_col = "spot_close" if "spot_close" in df.columns else ("close" if "close" in df.columns else None)

    for h in horizons_list:
        v_col = f"target_v_cont_h{h}"
        e_col = f"target_e_cont_h{h}"
        v_vals = np.full(len(df), np.nan)
        e_vals = np.full(len(df), np.nan)

        dates = df.index
        for i, dt in enumerate(dates):
            s_start = dt + pd.Timedelta(days=ready_lag_days)
            s_end = s_start + pd.Timedelta(days=h)
            sub = df.loc[s_start:s_end - pd.Timedelta(days=1)]
            if len(sub) == h:
                if rv_col is not None:
                    sum_rv = sub[rv_col].sum()
                    v_vals[i] = np.sqrt(365.0 / h * sum_rv)
                if close_col is not None:
                    rets = np.log(sub[close_col] / sub[close_col].shift(1)).dropna()
                    sum_r = float(rets.sum())
                    sum_abs = float(rets.abs().sum())
                    e_vals[i] = (sum_r / sum_abs) if sum_abs > 1e-12 else 0.0

        res_df[v_col] = v_vals
        res_df[e_col] = e_vals

    return res_df


def derive_and_freeze_taxonomy(
    targets_df: pd.DataFrame,
    prefix_start: str = "2022-01-14",
    prefix_end: str = "2024-01-13",
    horizons: Tuple[int, ...] = (56, 90),
) -> Dict[str, Any]:
    """Derive and freeze taxonomy boundaries strictly from training prefix."""
    df = targets_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
        else:
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass

    if isinstance(df.index, pd.DatetimeIndex):
        t_start = pd.to_datetime(prefix_start)
        t_end = pd.to_datetime(prefix_end)
        sub = df.loc[t_start:t_end]
    else:
        sub = df.loc[prefix_start:prefix_end]

    tax: Dict[str, Any] = {
        "study_id": "btc_regime_forecast_v1",
        "schema": "regime_lab.target_taxonomy.v2",
        "frozen_on_prefix": f"{prefix_start}_to_{prefix_end}",
        "prefix_sample_count": len(sub),
    }

    for h in horizons:
        v_col = f"target_v_cont_h{h}"
        e_col = f"target_e_cont_h{h}"
        v_clean = sub[v_col].dropna().values
        e_clean = sub[e_col].dropna().values

        if len(v_clean) > 0:
            q1 = float(np.quantile(v_clean, 1.0 / 3.0))
            q2 = float(np.quantile(v_clean, 2.0 / 3.0))
        else:
            q1, q2 = 0.40, 0.70

        if len(e_clean) > 0:
            tau = float(np.quantile(np.abs(e_clean), 0.50))
        else:
            tau = 0.20

        tax[f"H{h}"] = {
            "v_quantiles": {
                "q_1_3": q1,
                "q_2_3": q2,
            },
            "e_quantiles": {
                "tau_symmetric": tau,
            },
            "classes": {
                "volatility": list(VOLATILITY_CLASSES),
                "efficiency": list(EFFICIENCY_CLASSES),
                "joint_9class": [f"{v}__{e}" for v in VOLATILITY_CLASSES for e in EFFICIENCY_CLASSES],
            },
        }

    return tax


def assign_discrete_labels(
    targets_df: pd.DataFrame,
    taxonomy: Dict[str, Any],
    horizons: Tuple[int, ...] = (56, 90),
) -> pd.DataFrame:
    """Assign discrete 3-class and 9-class labels to continuous targets."""
    df = targets_df.copy()
    for h in horizons:
        h_key = f"H{h}"
        q1 = taxonomy[h_key]["v_quantiles"]["q_1_3"]
        q2 = taxonomy[h_key]["v_quantiles"]["q_2_3"]
        tau = taxonomy[h_key]["e_quantiles"]["tau_symmetric"]

        v_col = f"target_v_cont_h{h}"
        e_col = f"target_e_cont_h{h}"

        v_labels = []
        e_labels = []
        j_labels = []

        for _, row in df.iterrows():
            v_val = row.get(v_col)
            e_val = row.get(e_col)

            if pd.isna(v_val):
                v_lbl = np.nan
            elif v_val <= q1:
                v_lbl = "LOW_VOL"
            elif v_val <= q2:
                v_lbl = "MID_VOL"
            else:
                v_lbl = "HIGH_VOL"

            if pd.isna(e_val):
                e_lbl = np.nan
            elif e_val > tau:
                e_lbl = "TREND_FRIENDLY"
            elif e_val < -tau:
                e_lbl = "CHOP_HOSTILE"
            else:
                e_lbl = "RANGE_NEUTRAL"

            if pd.isna(v_lbl) or pd.isna(e_lbl):
                j_lbl = np.nan
            else:
                j_lbl = f"{v_lbl}__{e_lbl}"

            v_labels.append(v_lbl)
            e_labels.append(e_lbl)
            j_labels.append(j_lbl)

        df[f"target_v_class_h{h}"] = v_labels
        df[f"target_e_class_h{h}"] = e_labels
        df[f"target_j_class_h{h}"] = j_labels

    return df


def is_label_mature(origin_date: str, horizon_days: int, as_of_date: str, ready_lag_days: int = 1) -> bool:
    t_orig = datetime.date.fromisoformat(origin_date)
    t_mature = t_orig + datetime.timedelta(days=ready_lag_days + horizon_days)
    t_as_of = datetime.date.fromisoformat(as_of_date)
    return t_mature <= t_as_of
