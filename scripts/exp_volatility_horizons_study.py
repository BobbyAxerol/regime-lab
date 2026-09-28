"""Exploratory Study: Volatility-Conditioned Selection across Multiple Horizons.

Horizons: H in {14, 28, 56, 90} calendar days.
Tasks:
1. Volatility 3-class classification: LOW_VOL, MID_VOL, HIGH_VOL.
2. Continuous Log-Volatility regression.
Comparison:
- Baseline 1: Historical Frequency (Dirichlet alpha=1)
- Baseline 2: Persistence (Trailing realized vol)
- Model A: LightGBM with Standard Features (D1)
- Model B: LightGBM with Enhanced Volatility & Derivatives Pressure Features (D_VOL_ENHANCED)

Metrics computed:
- Overall Accuracy
- Balanced Accuracy
- Macro F1 & Per-class Precision / Recall / F1
- Confusion Matrix
- Brier Score, Brier Skill Score (BSS) + 95% Block Bootstrap CI (with sensitivities)
- Continuous Log-Vol MAE & Relative Error Reduction
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
import lightgbm as lgb

from crypto_regime_lab.regime_forecast.features import build_daily_base_table, compute_features
from crypto_regime_lab.regime_forecast.baselines import (
    brier_score_multiclass,
    brier_skill_score,
    balanced_accuracy,
)
from crypto_regime_lab.regime_forecast.bootstrap import (
    compute_block_bootstrap_ci_with_sensitivities,
    get_bootstrap_block_spec,
)


HORIZONS = [14, 28, 56, 90]
VOL_CLASSES = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]


def engineer_enhanced_volatility_features(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Computes specialized volatility and derivatives positioning features."""
    df = df_daily.copy()
    if "date" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df_base_feats = compute_features(df)
    res = df_base_feats.copy()

    # 1. Specialized Volatility Term Structure
    rv_daily = df["rv"] if "rv" in df.columns else df_base_feats["rvol_7d"]**2 / 365.0
    
    # Realized vol at multiple horizons
    for w in [7, 14, 28, 60, 90]:
        res[f"rvol_{w}d_ann"] = np.sqrt(365.0 * rv_daily.rolling(w, min_periods=max(2, w // 2)).mean())

    # Volatility term structure ratios (curve slope & inversion)
    res["vol_ratio_7_28"] = res["rvol_7d_ann"] / (res["rvol_28d_ann"] + 1e-6)
    res["vol_ratio_14_60"] = res["rvol_14d_ann"] / (res["rvol_60d_ann"] + 1e-6)
    res["vol_ratio_28_90"] = res["rvol_28d_ann"] / (res["rvol_90d_ann"] + 1e-6)

    # Volatility of Volatility
    res["vol_of_vol_14d"] = rv_daily.rolling(14, min_periods=7).std() / (rv_daily.rolling(14, min_periods=7).mean() + 1e-6)
    res["vol_of_vol_28d"] = rv_daily.rolling(28, min_periods=14).std() / (rv_daily.rolling(28, min_periods=14).mean() + 1e-6)

    # Downside volatility share
    if "downside_rv" in df.columns:
        down_share_14 = df["downside_rv"].rolling(14, min_periods=7).sum() / (rv_daily.rolling(14, min_periods=7).sum() + 1e-6)
        res["downside_vol_share_14d"] = down_share_14.clip(0.0, 1.0)
        down_share_28 = df["downside_rv"].rolling(28, min_periods=14).sum() / (rv_daily.rolling(28, min_periods=14).sum() + 1e-6)
        res["downside_vol_share_28d"] = down_share_28.clip(0.0, 1.0)

    # 2. Parkinson Range Volatility & Intraday Shock
    if "high" in df.columns and "low" in df.columns:
        log_hl_sq = (np.log(df["high"] / (df["low"] + 1e-8)))**2
        parkinson_14 = np.sqrt(365.0 / (4.0 * np.log(2.0)) * log_hl_sq.rolling(14, min_periods=7).mean())
        res["parkinson_vol_14d"] = parkinson_14
        res["range_to_rv_ratio_14d"] = parkinson_14 / (res["rvol_14d_ann"] + 1e-6)

    # 3. Derivatives Positioning & Leverage Overhang
    if "oi" in df.columns:
        oi_s = df["oi"]
        res["oi_change_7d"] = (oi_s / (oi_s.shift(7) + 1e-6) - 1.0).clip(-2.0, 5.0)
        res["oi_change_14d"] = (oi_s / (oi_s.shift(14) + 1e-6) - 1.0).clip(-2.0, 5.0)
        res["oi_vol_interaction_14d"] = res["oi_change_14d"].abs() * res["rvol_14d_ann"]

    if "perp_close" in df.columns and "close" in df.columns:
        basis_spread_bps = (df["perp_close"] - df["close"]) / df["close"] * 10000.0
        res["basis_spread_bps"] = basis_spread_bps.clip(-500.0, 500.0)
        res["basis_vol_7d"] = basis_spread_bps.rolling(7, min_periods=3).std().fillna(0.0)
        res["basis_vol_14d"] = basis_spread_bps.rolling(14, min_periods=7).std().fillna(0.0)

    if "perp_quote_volume" in df.columns and "perp_taker_buy_quote_volume" in df.columns:
        perp_vol = df["perp_quote_volume"] + 1e-6
        perp_taker_buy = df["perp_taker_buy_quote_volume"]
        perp_taker_imb_7d = ((2.0 * perp_taker_buy - perp_vol) / perp_vol).rolling(7, min_periods=3).mean()
        res["perp_taker_imb_7d"] = perp_taker_imb_7d.clip(-1.0, 1.0)

    res.replace([np.inf, -np.inf], np.nan, inplace=True)
    res.bfill(inplace=True)
    res.ffill(inplace=True)
    res.fillna(0.0, inplace=True)
    return res


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
            sub = df.loc[s_start:s_end - pd.Timedelta(days=1)]
            if len(sub) == h:
                sum_rv = sub[rv_col].sum()
                v = np.sqrt(365.0 / h * sum_rv)
                v_vals[i] = v
        targets[f"target_v_h{h}"] = v_vals
        targets[f"target_log_v_h{h}"] = np.log(np.maximum(v_vals, 1e-6))
    return targets


def derive_volatility_quantiles(targets_df: pd.DataFrame, prefix_start: str, prefix_end: str, horizons: List[int]) -> Dict[int, Tuple[float, float]]:
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
    if np.isnan(log_v):
        return "UNKNOWN"
    if log_v <= q1:
        return "LOW_VOL"
    elif log_v <= q2:
        return "MID_VOL"
    else:
        return "HIGH_VOL"


def run_experiment():
    print("=== STARTING VOLATILITY-CONDITIONED MULTI-HORIZON STUDY ===")
    snapshot_root = Path("snapshots/server_core_v1")
    df_daily = build_daily_base_table(snapshot_root, start_year="2021")
    df_daily["date"] = pd.to_datetime(df_daily["date"])
    df_daily.set_index("date", inplace=True)

    print(f"Data range: {df_daily.index.min()} to {df_daily.index.max()} ({len(df_daily)} rows)")

    # 1. Targets & Taxonomy
    print(f"Computing targets for horizons: {HORIZONS}...")
    targets_df = compute_targets_for_horizons(df_daily, HORIZONS)
    tax_quantiles = derive_volatility_quantiles(targets_df, "2022-01-14", "2024-01-13", HORIZONS)
    for h, (q1, q2) in tax_quantiles.items():
        print(f"  H={h:2d}d Volatility cutoffs (log-vol): q1/3={q1:.4f} (vol={np.exp(q1)*100:.1f}%), q2/3={q2:.4f} (vol={np.exp(q2)*100:.1f}%)")

    # Add discrete target columns
    for h in HORIZONS:
        q1, q2 = tax_quantiles[h]
        targets_df[f"label_v_h{h}"] = [label_volatility(val, q1, q2) for val in targets_df[f"target_log_v_h{h}"]]

    # 2. Features: Baseline D1 vs Enhanced D_VOL
    print("Computing features...")
    df_feat_standard = compute_features(df_daily)
    df_feat_enhanced = engineer_enhanced_volatility_features(df_daily)

    # Origins: 48 weekly origins in locked test set
    test_origins = pd.date_range("2025-06-07", "2026-05-02", freq="7D")
    print(f"Locked Test Set: {len(test_origins)} weekly origins ({test_origins.min().strftime('%Y-%m-%d')} to {test_origins.max().strftime('%Y-%m-%d')})")

    study_results: Dict[str, Any] = {}

    for h in HORIZONS:
        print(f"\n=======================================================")
        print(f"   EVALUATING HORIZON H = {h} DAYS (Weekly Refits)")
        print(f"=======================================================")
        q1, q2 = tax_quantiles[h]
        target_col = f"label_v_h{h}"
        log_v_col = f"target_log_v_h{h}"

        y_true_indices: List[int] = []
        log_v_true: List[float] = []
        
        preds_hist_freq: List[np.ndarray] = []
        preds_persistence: List[np.ndarray] = []
        preds_model_std: List[np.ndarray] = []
        preds_model_enh: List[np.ndarray] = []

        # Continuous predictions
        preds_cont_ref: List[float] = []
        preds_cont_enh: List[float] = []

        # Weekly origins loop
        for t_origin in test_origins:
            # Ground truth
            true_label = targets_df.loc[t_origin, target_col]
            y_true_indices.append(VOL_CLASSES.index(true_label))
            log_v_true.append(float(targets_df.loc[t_origin, log_v_col]))

            # Train cutoff: only labels mature strictly before t_origin
            max_train_date = t_origin - pd.Timedelta(days=h + 1)
            train_mask = (targets_df.index >= pd.to_datetime("2022-01-14")) & (targets_df.index <= max_train_date)
            train_sub = targets_df.loc[train_mask]

            # 1. Baseline 1: Historical Frequency (Dirichlet alpha=1)
            class_counts = train_sub[target_col].value_counts().reindex(VOL_CLASSES, fill_value=0).values
            probs_hist = (class_counts + 1.0) / (class_counts.sum() + 3.0)
            preds_hist_freq.append(probs_hist)

            # 2. Baseline 2: Persistence (Trailing realized vol mapped to taxonomy)
            sub_past = df_daily.loc[:t_origin].iloc[-h:]
            rv_past = sub_past["rv"].sum() if "rv" in sub_past.columns else 0.0004 * h
            v_past = np.sqrt(365.0 / h * rv_past)
            log_v_past = np.log(max(v_past, 1e-6))
            past_label = label_volatility(log_v_past, q1, q2)
            past_idx = VOL_CLASSES.index(past_label)
            probs_pers = np.full(3, 0.15)
            probs_pers[past_idx] = 0.70
            preds_persistence.append(probs_pers)
            preds_cont_ref.append(float(log_v_past))

            # 3. Fit LightGBM Standard (D1)
            X_train_std = df_feat_standard.loc[train_mask].values
            y_train = [VOL_CLASSES.index(l) for l in train_sub[target_col]]
            
            clf_std = lgb.LGBMClassifier(
                objective="multiclass",
                num_class=3,
                n_estimators=100,
                learning_rate=0.03,
                max_depth=3,
                num_leaves=7,
                min_child_samples=32,
                reg_lambda=5.0,
                random_state=20260928,
                verbosity=-1,
                n_jobs=-1
            )
            clf_std.fit(X_train_std, y_train)
            x_test_std = df_feat_standard.loc[[t_origin]].values
            prob_std = clf_std.predict_proba(x_test_std)[0]
            preds_model_std.append(prob_std)

            # 4. Fit LightGBM Enhanced (D_VOL)
            X_train_enh = df_feat_enhanced.loc[train_mask].values
            clf_enh = lgb.LGBMClassifier(
                objective="multiclass",
                num_class=3,
                n_estimators=100,
                learning_rate=0.03,
                max_depth=3,
                num_leaves=7,
                min_child_samples=32,
                reg_lambda=5.0,
                random_state=20260928,
                verbosity=-1,
                n_jobs=-1
            )
            clf_enh.fit(X_train_enh, y_train)
            x_test_enh = df_feat_enhanced.loc[[t_origin]].values
            prob_enh = clf_enh.predict_proba(x_test_enh)[0]
            preds_model_enh.append(prob_enh)

            # Continuous Regressor
            reg_enh = lgb.LGBMRegressor(
                objective="regression",
                n_estimators=100,
                learning_rate=0.03,
                max_depth=3,
                num_leaves=7,
                min_child_samples=32,
                reg_lambda=5.0,
                random_state=20260928,
                verbosity=-1,
                n_jobs=-1
            )
            y_train_cont = train_sub[log_v_col].values
            reg_enh.fit(X_train_enh, y_train_cont)
            pred_cont = float(reg_enh.predict(x_test_enh)[0])
            preds_cont_enh.append(pred_cont)

        # Convert to arrays
        y_true = np.array(y_true_indices)
        P_hist = np.array(preds_hist_freq)
        P_pers = np.array(preds_persistence)
        P_std = np.array(preds_model_std)
        P_enh = np.array(preds_model_enh)

        # Brier scores
        brier_hist = brier_score_multiclass(y_true, P_hist)
        brier_pers = brier_score_multiclass(y_true, P_pers)
        brier_std = brier_score_multiclass(y_true, P_std)
        brier_enh = brier_score_multiclass(y_true, P_enh)

        brier_ref = min(brier_hist, brier_pers)
        ref_name = "HistFreq" if brier_hist <= brier_pers else "Persistence"
        P_ref = P_hist if ref_name == "HistFreq" else P_pers

        bss_std = brier_skill_score(brier_std, brier_ref)
        bss_enh = brier_skill_score(brier_enh, brier_ref)

        # Class predictions (argmax)
        y_pred_ref = np.argmax(P_ref, axis=1)
        y_pred_std = np.argmax(P_std, axis=1)
        y_pred_enh = np.argmax(P_enh, axis=1)

        # Accuracies
        acc_ref = float(accuracy_score(y_true, y_pred_ref))
        acc_std = float(accuracy_score(y_true, y_pred_std))
        acc_enh = float(accuracy_score(y_true, y_pred_enh))

        bal_acc_ref = float(balanced_accuracy_score(y_true, y_pred_ref))
        bal_acc_std = float(balanced_accuracy_score(y_true, y_pred_std))
        bal_acc_enh = float(balanced_accuracy_score(y_true, y_pred_enh))

        macro_f1_ref = float(f1_score(y_true, y_pred_ref, average="macro"))
        macro_f1_std = float(f1_score(y_true, y_pred_std, average="macro"))
        macro_f1_enh = float(f1_score(y_true, y_pred_enh, average="macro"))

        # Per-class F1, Precision, Recall for Enhanced model
        f1_per_class = f1_score(y_true, y_pred_enh, labels=[0, 1, 2], average=None, zero_division=0)
        prec_per_class = precision_score(y_true, y_pred_enh, labels=[0, 1, 2], average=None, zero_division=0)
        rec_per_class = recall_score(y_true, y_pred_enh, labels=[0, 1, 2], average=None, zero_division=0)
        cm_enh = confusion_matrix(y_true, y_pred_enh, labels=[0, 1, 2])

        # Continuous MAE
        log_v_true_arr = np.array(log_v_true)
        log_v_ref_arr = np.array(preds_cont_ref)
        log_v_enh_arr = np.array(preds_cont_enh)
        mae_ref = float(np.mean(np.abs(log_v_true_arr - log_v_ref_arr)))
        mae_enh = float(np.mean(np.abs(log_v_true_arr - log_v_enh_arr)))
        rel_err_red = float(1.0 - (mae_enh / mae_ref)) if mae_ref > 1e-6 else 0.0

        # Block bootstrap for BSS Enhanced
        def diff_bss_enh(y, pm, pr):
            return brier_skill_score(brier_score_multiclass(y, pm), brier_score_multiclass(y, pr))

        res_boot_bss = compute_block_bootstrap_ci_with_sensitivities(y_true, P_enh, P_ref, diff_bss_enh, horizon_h=h, n_boot=2000)
        bss_low, bss_high = res_boot_bss["ci_lower"], res_boot_bss["ci_upper"]

        def diff_ba_enh(y, pm, pr):
            return balanced_accuracy(y, np.argmax(pm, axis=1), k=3) - balanced_accuracy(y, np.argmax(pr, axis=1), k=3)

        res_boot_ba = compute_block_bootstrap_ci_with_sensitivities(y_true, P_enh, P_ref, diff_ba_enh, horizon_h=h, n_boot=2000)
        ba_gain = bal_acc_enh - bal_acc_ref
        ba_low, ba_high = res_boot_ba["ci_lower"], res_boot_ba["ci_upper"]

        print(f"Horizon H={h:2d}d Results:")
        print(f"  Reference Baseline ({ref_name}):")
        print(f"    Brier Score:       {brier_ref:.4f}")
        print(f"    Overall Accuracy:  {acc_ref*100:5.1f}%")
        print(f"    Balanced Accuracy: {bal_acc_ref*100:5.1f}%")
        print(f"    Macro F1-Score:    {macro_f1_ref:5.3f}")
        print(f"  Standard LightGBM (D1):")
        print(f"    Brier Skill Score: {bss_std:+.4f}")
        print(f"    Overall Accuracy:  {acc_std*100:5.1f}%")
        print(f"    Balanced Accuracy: {bal_acc_std*100:5.1f}%")
        print(f"    Macro F1-Score:    {macro_f1_std:5.3f}")
        print(f"  Enhanced LightGBM (D_VOL):")
        print(f"    Brier Score:       {brier_enh:.4f} (BSS = {bss_enh:+.4f}, 95% CI: [{bss_low:+.4f}, {bss_high:+.4f}])")
        print(f"    Overall Accuracy:  {acc_enh*100:5.1f}% (Gain vs Base: {(acc_enh - acc_ref)*100:+.1f}%)")
        print(f"    Balanced Accuracy: {bal_acc_enh*100:5.1f}% (Gain: {ba_gain*100:+.1f}%, 95% CI: [{ba_low*100:+.1f}%, {ba_high*100:+.1f}%])")
        print(f"    Macro F1-Score:    {macro_f1_enh:5.3f}")
        print(f"    Continuous Log-Vol MAE: {mae_enh:.4f} vs Base {mae_ref:.4f} (Rel Error Red: {rel_err_red*100:+.1f}%)")
        print(f"    Per-Class Detailed Metrics:")
        for idx, cname in enumerate(VOL_CLASSES):
            print(f"      - {cname:8s}: Prec={prec_per_class[idx]*100:5.1f}%, Recall={rec_per_class[idx]*100:5.1f}%, F1={f1_per_class[idx]:5.3f}")
        print(f"    Confusion Matrix (Rows=True, Cols=Pred [Low, Mid, High]):\n{cm_enh}")

        study_results[f"H{h}"] = {
            "horizon_days": h,
            "primary_block_size": res_boot_bss["primary_block_size"],
            "baseline_ref_name": ref_name,
            "brier_ref": brier_ref,
            "acc_ref": acc_ref,
            "bal_acc_ref": bal_acc_ref,
            "macro_f1_ref": macro_f1_ref,
            "std_model": {
                "brier": brier_std,
                "bss": bss_std,
                "accuracy": acc_std,
                "balanced_acc": bal_acc_std,
                "macro_f1": macro_f1_std,
            },
            "enhanced_model": {
                "brier": brier_enh,
                "bss": bss_enh,
                "bss_ci_95": [bss_low, bss_high],
                "accuracy": acc_enh,
                "acc_gain": acc_enh - acc_ref,
                "balanced_acc": bal_acc_enh,
                "bal_acc_gain": ba_gain,
                "bal_acc_gain_ci_95": [ba_low, ba_high],
                "macro_f1": macro_f1_enh,
                "continuous_log_v_mae": mae_enh,
                "continuous_log_v_ref_mae": mae_ref,
                "continuous_rel_error_red": rel_err_red,
                "class_metrics": {
                    cname: {
                        "precision": float(prec_per_class[i]),
                        "recall": float(rec_per_class[i]),
                        "f1": float(f1_per_class[i]),
                    }
                    for i, cname in enumerate(VOL_CLASSES)
                },
                "confusion_matrix": cm_enh.tolist(),
            }
        }

    out_dir = Path("evidence/exp_volatility_horizons_v1")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "study_results.json", "w", encoding="utf-8") as f:
        json.dump(study_results, f, indent=2)
    print(f"\nSaved comprehensive study results to {out_dir / 'study_results.json'}")


if __name__ == "__main__":
    run_experiment()
