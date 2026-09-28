"""Baselines and evaluation metrics for BTCUSDT regime forecasting.

Per REGIME_LAB_BTCUSDT_REGIME_PARAMETER_SELECTION_V1_5_PHASE_GUIDE_VI.md:
Section 7: 4 mandatory baselines:
1. Persistence (naive carry of current observed state / RV / zero efficiency drift)
2. Matured Frequencies (Laplace smoothed historical empirical distribution)
3. HAR-RV (Corsi 2009 autoregressive realized volatility forecast)
4. Regularized Linear / Logistic (L2 penalized linear/multinomial models)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge


@dataclass(frozen=True)
class BaselineForecast:
    """Forecast output for a single origin and horizon."""
    origin: str  # YYYY-MM-DD
    horizon: int  # 56 or 90
    baseline_id: str
    pred_v_cont: float
    pred_e_cont: float
    prob_v_3class: Dict[str, float]  # LOW_VOL, MID_VOL, HIGH_VOL
    prob_e_3class: Dict[str, float]  # TREND_FRIENDLY, RANGE_NEUTRAL, CHOP_HOSTILE
    prob_j_9class: Dict[str, float]  # joint 9-class cells


def brier_score_multiclass(y_true_indices: np.ndarray, prob_matrix: np.ndarray) -> float:
    """Compute multiclass Brier score: mean over N of sum_k (p_ik - y_ik)^2.
    
    y_true_indices: (N,) integers in [0, K-1]
    prob_matrix: (N, K) probabilities summing to 1 along axis 1.
    """
    n, k = prob_matrix.shape
    if n == 0:
        return 0.0
    y_one_hot = np.zeros((n, k), dtype=np.float64)
    y_one_hot[np.arange(n), y_true_indices] = 1.0
    return float(np.mean(np.sum((prob_matrix - y_one_hot) ** 2, axis=1)))


def balanced_accuracy(y_true_indices: np.ndarray, y_pred_indices: np.ndarray, k: int) -> float:
    """Compute balanced accuracy (macro-averaged recall across classes)."""
    recalls = []
    for c in range(k):
        mask = (y_true_indices == c)
        if np.sum(mask) == 0:
            continue
        recall_c = np.sum((y_pred_indices == c) & mask) / np.sum(mask)
        recalls.append(recall_c)
    if not recalls:
        return 0.0
    return float(np.mean(recalls))


def brier_skill_score(brier_model: float, brier_ref: float) -> float:
    """Compute Brier Skill Score: 1 - BS_model / BS_ref."""
    if brier_ref <= 1e-12:
        return 0.0
    return float(1.0 - (brier_model / brier_ref))


class PersistenceBaseline:
    """Baseline 1: Persistence.
    
    Continuous V: current realized volatility RV_28(T)
    Continuous E: zero (neutral efficiency drift)
    Classification: 100% probability assigned to current observed regime at T.
    """
    def __init__(self) -> None:
        self.baseline_id = "B1_PERSISTENCE"

    def predict(
        self,
        origin_row: pd.Series,
        observed_regime: str,
        v_classes: List[str],
        e_classes: List[str],
        j_classes: List[str],
    ) -> Dict[str, Any]:
        rv28 = float(origin_row.get("p1_rv_28d", origin_row.get("rvol_30d", origin_row.get("rvol_7d", origin_row.get("rv", 0.02)))))
        
        # Split observed regime into V and E components if possible (e.g. "MID_VOL__RANGE_NEUTRAL")
        if "__" in observed_regime:
            v_curr, e_curr = observed_regime.split("__", 1)
        else:
            v_curr, e_curr = "MID_VOL", "RANGE_NEUTRAL"

        prob_v = {c: 1.0 if c == v_curr else 0.0 for c in v_classes}
        prob_e = {c: 1.0 if c == e_curr else 0.0 for c in e_classes}
        prob_j = {c: 1.0 if c == observed_regime else 0.0 for c in j_classes}

        return {
            "pred_v_cont": rv28,
            "pred_e_cont": 0.0,
            "prob_v_3class": prob_v,
            "prob_e_3class": prob_e,
            "prob_j_9class": prob_j,
        }


class MaturedFrequenciesBaseline:
    """Baseline 2: Matured Empirical Frequencies with Laplace smoothing (alpha=1).
    
    Only uses labels matured strictly prior to origin T.
    """
    def __init__(self, alpha: float = 1.0) -> None:
        self.baseline_id = "B2_MATURED_FREQ"
        self.alpha = alpha

    def fit_predict(
        self,
        matured_df: pd.DataFrame,
        target_h: int,
        v_classes: List[str],
        e_classes: List[str],
        j_classes: List[str],
    ) -> Dict[str, Any]:
        target_v_col = f"target_v_class_h{target_h}"
        target_e_col = f"target_e_class_h{target_h}"
        target_j_col = f"target_j_class_h{target_h}"
        target_v_cont = f"target_v_cont_h{target_h}"
        target_e_cont = f"target_e_cont_h{target_h}"

        n_matured = len(matured_df)
        if n_matured == 0:
            # Uniform prior
            prob_v = {c: 1.0 / len(v_classes) for c in v_classes}
            prob_e = {c: 1.0 / len(e_classes) for c in e_classes}
            prob_j = {c: 1.0 / len(j_classes) for c in j_classes}
            return {
                "pred_v_cont": 0.03,
                "pred_e_cont": 0.0,
                "prob_v_3class": prob_v,
                "prob_e_3class": prob_e,
                "prob_j_9class": prob_j,
            }

        # Continuous predictions: historical matured mean
        pred_v_cont = float(matured_df[target_v_cont].mean()) if target_v_cont in matured_df else 0.03
        pred_e_cont = float(matured_df[target_e_cont].mean()) if target_e_cont in matured_df else 0.0

        # Laplace smoothing: (count + alpha) / (N + K * alpha)
        prob_v = {}
        for c in v_classes:
            cnt = int((matured_df[target_v_col] == c).sum())
            prob_v[c] = float((cnt + self.alpha) / (n_matured + len(v_classes) * self.alpha))

        prob_e = {}
        for c in e_classes:
            cnt = int((matured_df[target_e_col] == c).sum())
            prob_e[c] = float((cnt + self.alpha) / (n_matured + len(e_classes) * self.alpha))

        prob_j = {}
        for c in j_classes:
            cnt = int((matured_df[target_j_col] == c).sum())
            prob_j[c] = float((cnt + self.alpha) / (n_matured + len(j_classes) * self.alpha))

        return {
            "pred_v_cont": pred_v_cont,
            "pred_e_cont": pred_e_cont,
            "prob_v_3class": prob_v,
            "prob_e_3class": prob_e,
            "prob_j_9class": prob_j,
        }


class HarRvBaseline:
    """Baseline 3: HAR-RV (Corsi 2009) autoregressive model for realized volatility.
    
    log(V_{T,H}) = beta_0 + beta_d * log(RV_1) + beta_w * log(RV_7) + beta_m * log(RV_28) + eps
    Fit on matured training data using OLS / Ridge.
    """
    def __init__(self) -> None:
        self.baseline_id = "B3_HAR_RV"
        self.model = Ridge(alpha=1e-3)
        self.fitted = False
        self.cols = ["rvol_7d", "rvol_30d", "rvol_90d"]

    def _detect_cols(self, df_or_series: Any) -> List[str]:
        cols_present = set(df_or_series.columns if isinstance(df_or_series, pd.DataFrame) else df_or_series.index)
        if {"p1_rv_1d", "p1_rv_7d", "p1_rv_28d"}.issubset(cols_present):
            return ["p1_rv_1d", "p1_rv_7d", "p1_rv_28d"]
        c1 = "rvol_7d" if "rvol_7d" in cols_present else ("rv" if "rv" in cols_present else list(cols_present)[0])
        c7 = "rvol_30d" if "rvol_30d" in cols_present else c1
        c28 = "rvol_90d" if "rvol_90d" in cols_present else c7
        return [c1, c7, c28]

    def fit(self, matured_df: pd.DataFrame, target_h: int) -> None:
        target_col = f"target_v_cont_h{target_h}"
        self.cols = self._detect_cols(matured_df)
        sub = matured_df.dropna(subset=self.cols + [target_col])
        if len(sub) < 10:
            self.fitted = False
            return
        
        # log features with small epsilon to avoid log(0)
        eps = 1e-6
        X = np.log(np.maximum(sub[self.cols].values, eps))
        y = np.log(np.maximum(sub[target_col].values, eps))
        self.model.fit(X, y)
        self.fitted = True

    def predict(
        self,
        origin_row: pd.Series,
        v_cutoffs: Tuple[float, float],
        v_classes: List[str],
        e_classes: List[str],
        j_classes: List[str],
    ) -> Dict[str, Any]:
        eps = 1e-6
        vals = np.array([float(origin_row.get(c, 0.02)) for c in self.cols])
        x_vec = np.log(np.maximum(vals, eps)).reshape(1, -1)

        if self.fitted:
            log_pred = float(self.model.predict(x_vec)[0])
            pred_v = float(np.exp(log_pred))
        else:
            pred_v = float(vals[-1])  # fallback

        # Classify V based on frozen cutoffs (q_1/3, q_2/3)
        q1, q2 = v_cutoffs
        # Smooth probability around cutoffs using logistic-like CDF or distance
        # For a simple calibrated representation:
        if pred_v <= q1:
            p_v = {"LOW_VOL": 0.70, "MID_VOL": 0.25, "HIGH_VOL": 0.05}
        elif pred_v <= q2:
            p_v = {"LOW_VOL": 0.15, "MID_VOL": 0.70, "HIGH_VOL": 0.15}
        else:
            p_v = {"LOW_VOL": 0.05, "MID_VOL": 0.25, "HIGH_VOL": 0.70}

        # HAR-RV has no efficiency model -> uniform or neutral for E
        prob_e = {c: 1.0 / len(e_classes) for c in e_classes}
        
        # Joint probability = product of independent V and E
        prob_j = {}
        for j in j_classes:
            v_part, e_part = j.split("__", 1)
            prob_j[j] = p_v.get(v_part, 1/3) * prob_e.get(e_part, 1/3)

        return {
            "pred_v_cont": pred_v,
            "pred_e_cont": 0.0,
            "prob_v_3class": p_v,
            "prob_e_3class": prob_e,
            "prob_j_9class": prob_j,
        }


class RegularizedLinearBaseline:
    """Baseline 4: L2 Regularized Logistic Regression (Classification) & Ridge (Continuous).
    
    Features: D0 cohort (core price & volatility causal features).
    """
    def __init__(self, c_logistic: float = 1.0, alpha_ridge: float = 10.0) -> None:
        self.baseline_id = "B4_REGULARIZED_LINEAR"
        self.clf_v = LogisticRegression(C=c_logistic, max_iter=1000)
        self.clf_e = LogisticRegression(C=c_logistic, max_iter=1000)
        self.reg_v = Ridge(alpha=alpha_ridge)
        self.reg_e = Ridge(alpha=alpha_ridge)
        self.fitted = False
        self.feature_cols: List[str] = []

    def fit(self, matured_df: pd.DataFrame, feature_cols: List[str], target_h: int) -> None:
        self.feature_cols = feature_cols
        v_class_col = f"target_v_class_h{target_h}"
        e_class_col = f"target_e_class_h{target_h}"
        v_cont_col = f"target_v_cont_h{target_h}"
        e_cont_col = f"target_e_cont_h{target_h}"

        req = feature_cols + [v_class_col, e_class_col, v_cont_col, e_cont_col]
        sub = matured_df.dropna(subset=req)
        if len(sub) < 30:
            self.fitted = False
            return

        X = sub[feature_cols].values
        # Impute any NaNs in X with column mean
        col_means = np.nanmean(X, axis=0)
        inds = np.where(np.isnan(X))
        X[inds] = np.take(col_means, inds[1])

        # Standardize X
        self.x_mean = np.mean(X, axis=0)
        self.x_std = np.std(X, axis=0) + 1e-8
        X_scaled = (X - self.x_mean) / self.x_std

        y_v = sub[v_class_col].values
        y_e = sub[e_class_col].values
        y_v_cont = sub[v_cont_col].values
        y_e_cont = sub[e_cont_col].values

        self.clf_v.fit(X_scaled, y_v)
        self.clf_e.fit(X_scaled, y_e)
        self.reg_v.fit(X_scaled, y_v_cont)
        self.reg_e.fit(X_scaled, y_e_cont)
        self.fitted = True

    def predict(
        self,
        origin_row: pd.Series,
        v_classes: List[str],
        e_classes: List[str],
        j_classes: List[str],
    ) -> Dict[str, Any]:
        if not self.fitted:
            # Fallback uniform
            return {
                "pred_v_cont": 0.03,
                "pred_e_cont": 0.0,
                "prob_v_3class": {c: 1.0 / len(v_classes) for c in v_classes},
                "prob_e_3class": {c: 1.0 / len(e_classes) for c in e_classes},
                "prob_j_9class": {c: 1.0 / len(j_classes) for c in j_classes},
            }

        x_raw = np.array([float(origin_row.get(c, 0.0)) for c in self.feature_cols])
        # Replace NaN
        x_raw = np.nan_to_num(x_raw, nan=0.0)
        x_scaled = (x_raw - self.x_mean) / self.x_std
        x_scaled = x_scaled.reshape(1, -1)

        pred_v_cont = float(self.reg_v.predict(x_scaled)[0])
        pred_e_cont = float(self.reg_e.predict(x_scaled)[0])

        probs_v_arr = self.clf_v.predict_proba(x_scaled)[0]
        prob_v = {c: float(p) for c, p in zip(self.clf_v.classes_, probs_v_arr)}
        for c in v_classes:
            prob_v.setdefault(c, 0.0)

        probs_e_arr = self.clf_e.predict_proba(x_scaled)[0]
        prob_e = {c: float(p) for c, p in zip(self.clf_e.classes_, probs_e_arr)}
        for c in e_classes:
            prob_e.setdefault(c, 0.0)

        # Joint: product of marginals
        prob_j = {}
        for j in j_classes:
            v_part, e_part = j.split("__", 1)
            prob_j[j] = prob_v.get(v_part, 0.0) * prob_e.get(e_part, 0.0)
        
        # Normalize joint to 1.0
        tot = sum(prob_j.values())
        if tot > 0:
            prob_j = {k: v / tot for k, v in prob_j.items()}

        return {
            "pred_v_cont": pred_v_cont,
            "pred_e_cont": pred_e_cont,
            "prob_v_3class": prob_v,
            "prob_e_3class": prob_e,
            "prob_j_9class": prob_j,
        }
