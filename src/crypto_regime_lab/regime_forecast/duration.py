"""Regime duration, survival analysis, and episode ledger for btc_regime_forecast_v1.

Follows BTC-RPS-V1.2 Section 4D.
- Observed state axes: OBS_VOL (LOW_VOL/MID_VOL/HIGH_VOL) and OBS_PATH (TREND_FRIENDLY/RANGE_NEUTRAL/CHOP_HOSTILE).
- Detectors: OBS14_CONFIRM3_V1 (primary), OBS14_RAW, OBS28_CONFIRM3, OBS28_RAW.
- Episode ledger tracking confirmed episodes, dwell lengths, and right-censoring at cutoffs.
- Kaplan-Meier empirical survival estimator, Restricted Mean Survival Time (RMST),
  Restricted Mean Remaining Life (RMRL), and first-exit probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


DETECTORS = {
    "OBS14_CONFIRM3_V1": {"lookback": 14, "confirmations": 3},
    "OBS14_RAW": {"lookback": 14, "confirmations": 1},
    "OBS28_CONFIRM3": {"lookback": 28, "confirmations": 3},
    "OBS28_RAW": {"lookback": 28, "confirmations": 1},
}


@dataclass(frozen=True)
class KaplanMeierResult:
    timeline: np.ndarray
    survival_probabilities: np.ndarray
    survival_table: Dict[int, float]
    episodes_count: int
    exits_count: int
    median_duration: Optional[float]
    rmst_90: float


class Obs14Confirm3Detector:
    """Primary detector: 14-day rolling window with 3 consecutive days confirmation."""
    def __init__(self, v_cutoffs: Tuple[float, float] = (0.015, 0.035), e_tau: float = 0.20, min_confirm_days: int = 3) -> None:
        self.detector_id = "OBS14_CONFIRM3_V1"
        self.v_cutoffs = v_cutoffs
        self.e_tau = e_tau
        self.min_confirm_days = min_confirm_days

    def generate_state_tape(self, df_daily: pd.DataFrame) -> pd.DataFrame:
        df = df_daily.copy()
        q1, q2 = self.v_cutoffs
        tau = self.e_tau

        # Determine volatility series
        if "p1_rv_28d" in df.columns:
            v_series = df["p1_rv_28d"]
        elif "rv_5m_daily" in df.columns:
            v_series = df["rv_5m_daily"].rolling(14).mean()
        elif "rv" in df.columns:
            v_series = df["rv"].rolling(14).mean()
        else:
            v_series = pd.Series(0.02, index=df.index)

        # Determine path/efficiency series
        if "p1_er_28d" in df.columns:
            e_series = df["p1_er_28d"]
        elif "spot_close" in df.columns or "close" in df.columns:
            c = df["spot_close"] if "spot_close" in df.columns else df["close"]
            log_ret = np.log(c / c.shift(1))
            sum_r = log_ret.rolling(14).sum()
            sum_abs_r = log_ret.abs().rolling(14).sum()
            e_series = np.where(sum_abs_r > 1e-12, sum_r / sum_abs_r, 0.0)
        else:
            e_series = pd.Series(0.0, index=df.index)

        raw_states = []
        for v, e in zip(v_series, e_series):
            if pd.isna(v) or pd.isna(e):
                raw_states.append("MID_VOL__RANGE_NEUTRAL")
                continue
            if v <= q1:
                v_lbl = "LOW_VOL"
            elif v <= q2:
                v_lbl = "MID_VOL"
            else:
                v_lbl = "HIGH_VOL"

            if e > tau:
                e_lbl = "TREND_FRIENDLY"
            elif e < -tau:
                e_lbl = "CHOP_HOSTILE"
            else:
                e_lbl = "RANGE_NEUTRAL"

            raw_states.append(f"{v_lbl}__{e_lbl}")

        # Causal confirmation logic
        confirmed_states = []
        curr_state = raw_states[0] if raw_states else "MID_VOL__RANGE_NEUTRAL"
        pending_state = None
        pending_count = 0

        for raw in raw_states:
            if raw != curr_state:
                if pending_state == raw:
                    pending_count += 1
                else:
                    pending_state = raw
                    pending_count = 1
                if pending_count >= self.min_confirm_days:
                    curr_state = pending_state
                    pending_state = None
                    pending_count = 0
            else:
                pending_state = None
                pending_count = 0
            confirmed_states.append(curr_state)

        tape = pd.DataFrame({
            "observed_regime": confirmed_states,
            "raw_regime": raw_states,
        }, index=df.index)
        return tape


def build_episode_ledger(
    tape: pd.DataFrame,
    state_col: str = "observed_regime",
    fit_cutoff: Optional[str] = None,
) -> pd.DataFrame:
    """Build episode ledger tracking start, end, duration, and right-censoring."""
    df = tape.copy()
    if fit_cutoff is not None:
        df = df.loc[:fit_cutoff]

    episodes = []
    curr_state = None
    curr_start_idx = 0
    curr_start_date = None

    dates = df.index
    states = df[state_col].values

    for i in range(len(df)):
        st = states[i]
        dt = dates[i]

        if curr_state is None:
            curr_state = st
            curr_start_idx = i
            curr_start_date = dt
            continue

        if st != curr_state:
            # End previous episode
            duration = i - curr_start_idx
            episodes.append({
                "episode_id": f"ep_{len(episodes):04d}",
                "regime": curr_state,
                "start_date": str(curr_start_date),
                "end_date": str(dt),
                "duration_days": int(duration),
                "is_right_censored": False,
                "event_observed": 1,
            })
            curr_state = st
            curr_start_idx = i
            curr_start_date = dt

    # Final ongoing episode is right-censored
    if curr_state is not None:
        duration = len(df) - curr_start_idx
        episodes.append({
            "episode_id": f"ep_{len(episodes):04d}",
            "regime": curr_state,
            "start_date": str(curr_start_date),
            "end_date": str(dates[-1]),
            "duration_days": int(duration),
            "is_right_censored": True,
            "event_observed": 0,
        })

    return pd.DataFrame(episodes)


def fit_kaplan_meier_survival(
    durations_or_df: Union[List[int], np.ndarray, pd.DataFrame],
    censored_or_state: Union[List[bool], np.ndarray, str, None] = None,
) -> KaplanMeierResult:
    """Fit Kaplan-Meier survival curve.
    
    Accepts either:
    - (durations: list, censored: list of bool) where censored is True if right-censored
    - (df_episodes: DataFrame, state: str)
    """
    if isinstance(durations_or_df, pd.DataFrame):
        df_ep = durations_or_df
        state = str(censored_or_state)
        sub = df_ep[df_ep["regime"] == state]
        if len(sub) == 0:
            return KaplanMeierResult(
                timeline=np.array([0]),
                survival_probabilities=np.array([1.0]),
                survival_table={0: 1.0},
                episodes_count=0,
                exits_count=0,
                median_duration=None,
                rmst_90=0.0,
            )
        durations = sub["duration_days"].values
        censored = sub["is_right_censored"].values
    else:
        durations = np.array(durations_or_df)
        censored = np.array(censored_or_state)

    events = 1 - censored.astype(int)
    n_total = len(durations)
    n_exits = int(events.sum())

    order = np.argsort(durations)
    dur_sorted = durations[order]
    ev_sorted = events[order]

    unique_durs = sorted(list(set(dur_sorted)))
    s_val = 1.0
    timeline = [0]
    s_probs = [1.0]
    survival_table = {0: 1.0}

    for u in unique_durs:
        if u == 0:
            continue
        at_risk = np.sum(dur_sorted >= u)
        d_exits = np.sum((dur_sorted == u) & (ev_sorted == 1))
        if at_risk > 0:
            s_val *= (1.0 - d_exits / at_risk)
        timeline.append(int(u))
        s_probs.append(float(s_val))
        survival_table[int(u)] = float(s_val)

    # Median duration where S <= 0.5
    median_dur = None
    for u, s in zip(timeline, s_probs):
        if s <= 0.5:
            median_dur = float(u)
            break

    rmst_90 = compute_rmst(
        KaplanMeierResult(
            timeline=np.array(timeline),
            survival_probabilities=np.array(s_probs),
            survival_table=survival_table,
            episodes_count=n_total,
            exits_count=n_exits,
            median_duration=median_dur,
            rmst_90=0.0,
        ),
        horizon_l=90,
    )

    return KaplanMeierResult(
        timeline=np.array(timeline),
        survival_probabilities=np.array(s_probs),
        survival_table=survival_table,
        episodes_count=n_total,
        exits_count=n_exits,
        median_duration=median_dur,
        rmst_90=rmst_90,
    )


def compute_rmst(km: KaplanMeierResult, horizon_l: int = 90) -> float:
    """Restricted Mean Survival Time up to horizon L."""
    u_grid = np.arange(0, horizon_l + 1)
    s_grid = []
    curr_s = 1.0
    for u in u_grid:
        if u in km.survival_table:
            curr_s = km.survival_table[u]
        s_grid.append(curr_s)
    return float(np.trapezoid(s_grid, u_grid) if hasattr(np, "trapezoid") else np.trapz(s_grid, u_grid))


def compute_rmrl(km: KaplanMeierResult, elapsed_age: int, horizon_l: int = 90) -> float:
    """Restricted Mean Remaining Life up to horizon L given current elapsed age."""
    if elapsed_age >= horizon_l:
        return 0.0

    def get_s(l: int) -> float:
        keys = sorted(km.survival_table.keys())
        val = 1.0
        for k in keys:
            if k <= l:
                val = km.survival_table[k]
            else:
                break
        return val

    s_a = get_s(elapsed_age)
    if s_a <= 1e-6:
        return 0.0

    u_grid = np.arange(elapsed_age, horizon_l + 1)
    s_grid = [get_s(u) / s_a for u in u_grid]
    integral = float(np.trapezoid(s_grid, u_grid) if hasattr(np, "trapezoid") else np.trapz(s_grid, u_grid))
    return max(0.0, min(integral, float(horizon_l - elapsed_age)))


def compute_first_exit_probability(km: KaplanMeierResult, elapsed_age: int, horizon_h: int) -> float:
    """Compute first-exit probability within horizon h given current elapsed age."""
    def get_s(l: int) -> float:
        keys = sorted(km.survival_table.keys())
        val = 1.0
        for k in keys:
            if k <= l:
                val = km.survival_table[k]
            else:
                break
        return val

    s_a = get_s(elapsed_age)
    if s_a <= 1e-6:
        return 1.0
    s_a_h = get_s(elapsed_age + horizon_h)
    return float(np.clip(1.0 - (s_a_h / s_a), 0.0, 1.0))
