"""SD-02: JM recipe v1 market features (guide SS5.2).

Three small, frozen, causal features from daily-UTC completed bars, each
tagged with observed_at/available_at/schema_hash. Never annualized inside
a ratio; NaN pairs are excluded, never coerced to 0.
"""
from __future__ import annotations

import hashlib

FEATURE_NAMES = ("log_rv_ratio_28_180", "signed_path_efficiency_56", "autocorr_lag1_56")
RV_SHORT_DAYS = 28
RV_LONG_DAYS = 180
EFFICIENCY_DAYS = 56
AUTOCORR_DAYS = 56
SCHEMA_HASH = hashlib.sha256(
    b"regime_lab.sd_jm_features.v1:" + ",".join(FEATURE_NAMES).encode()).hexdigest()[:16]


class FeatureError(ValueError):
    """A feature could not be computed from the given causal window."""


def log_rv_ratio(daily_log_returns: list) -> float:
    """log(rv_28 / rv_180): rv_h = sample std (ddof=1) of the LAST h daily
    log returns. No annualization inside the ratio (guide: "annualization
    khong can trong ratio"). Requires >=RV_LONG_DAYS observations so BOTH
    windows are exactly the declared length, never a partial-window std."""
    import math

    import numpy as np

    if len(daily_log_returns) < RV_LONG_DAYS:
        raise FeatureError(f"need >= {RV_LONG_DAYS} daily log returns, got {len(daily_log_returns)}")
    short = np.asarray(daily_log_returns[-RV_SHORT_DAYS:], dtype=float)
    long_ = np.asarray(daily_log_returns[-RV_LONG_DAYS:], dtype=float)
    rv_short = float(np.std(short, ddof=1))
    rv_long = float(np.std(long_, ddof=1))
    if rv_short <= 0 or rv_long <= 0:
        raise FeatureError("DEGENERATE_FEATURE_GEOMETRY: zero realized volatility in one window")
    return math.log(rv_short / rv_long)


def signed_path_efficiency(daily_closes: list) -> float:
    """(close_t - close_{t-56}) / sum(abs(daily close changes)) over exactly
    56 completed steps (57 close observations)."""
    import numpy as np

    if len(daily_closes) < EFFICIENCY_DAYS + 1:
        raise FeatureError(f"need >= {EFFICIENCY_DAYS + 1} daily closes, got {len(daily_closes)}")
    window = np.asarray(daily_closes[-(EFFICIENCY_DAYS + 1):], dtype=float)
    net_change = float(window[-1] - window[0])
    total_abs_change = float(np.abs(np.diff(window)).sum())
    if total_abs_change <= 0:
        raise FeatureError("DEGENERATE_FEATURE_GEOMETRY: zero total absolute change over the window")
    return net_change / total_abs_change


def autocorr_lag1(daily_log_returns: list) -> float:
    """Lag-1 autocorrelation of the LAST 56 daily log returns. Only finite
    pairs are used; a NaN/non-finite return is EXCLUDED from both the pair
    it starts and the pair it ends, never coerced to 0."""
    import math

    if len(daily_log_returns) < AUTOCORR_DAYS:
        raise FeatureError(f"need >= {AUTOCORR_DAYS} daily log returns, got {len(daily_log_returns)}")
    window = [float(x) for x in daily_log_returns[-AUTOCORR_DAYS:]]
    pairs = [(a, b) for a, b in zip(window[:-1], window[1:])
            if math.isfinite(a) and math.isfinite(b)]
    if len(pairs) < 2:
        raise FeatureError("fewer than 2 finite lag-1 pairs available")
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    var_x = sum((x - mx) ** 2 for x in xs)
    var_y = sum((y - my) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        raise FeatureError("DEGENERATE_FEATURE_GEOMETRY: zero variance in the autocorrelation window")
    return cov / math.sqrt(var_x * var_y)


def feature_row(daily_log_returns: list, daily_closes: list, *, observed_at: str,
                available_at: str) -> dict:
    """One causal feature row -- raises FeatureError (typed
    DEGENERATE_FEATURE_GEOMETRY inside the message where applicable) rather
    than silently returning a partial or zero-filled row."""
    return {
        "log_rv_ratio_28_180": log_rv_ratio(daily_log_returns),
        "signed_path_efficiency_56": signed_path_efficiency(daily_closes),
        "autocorr_lag1_56": autocorr_lag1(daily_log_returns),
        "observed_at": observed_at, "available_at": available_at, "schema_hash": SCHEMA_HASH,
    }
