"""Scalar reference indicators (guide L02.2).

Each function states which alpha convention it reproduces. Conventions that
differ between the four files are kept as SEPARATE functions rather than
unified: the guide is explicit that Wilder/EMA/padding conventions must not be
"fixed" into one shared implementation.

Naming: ``*_legacy`` reproduces the supplied source exactly (bugs included),
``*_canonical`` is the repaired version carrying a semantic delta.
"""

from __future__ import annotations

import math

import numpy as np

EPS = 1e-12


def _as_f64(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


class WarmupError(ValueError):
    """Raised when an input is too short for the requested window.

    The supplied alphas index past the end instead (finding AV-01, AH-02); the
    adapters must fail fast or return an explicit no-signal warmup.
    """


# --------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------

def sma(src, length: int) -> np.ndarray:
    """Simple moving average. Reproduces vwap.py n_sma for indices >= length-1.

    Unlike the source it raises rather than indexing out of range on short input.
    """
    src = _as_f64(src)
    if length <= 0:
        raise ValueError("length must be positive")
    if src.size < length:
        raise WarmupError(f"sma({length}) needs {length} observations, got {src.size}")
    out = np.zeros_like(src)
    # Sequential accumulation, matching the source loop bit for bit. np.sum uses
    # pairwise summation and would differ in the last ulp, which is enough to make
    # the oracle a near-miss instead of an oracle.
    running = 0.0
    for i in range(length):
        running += src[i]
    out[length - 1] = running / length
    for i in range(length, src.size):
        running += src[i] - src[i - length]
        out[i] = running / length
    return out


def rolling_std_sample(src, length: int) -> np.ndarray:
    """Sample standard deviation (ddof=1). Reproduces vwap.py n_stdev.

    The source computes it from running sums of x and x^2 and clamps a negative
    variance to zero; that clamp is kept because it is load-bearing for the
    z-score, but the running-sum form is replaced by an exact windowed
    computation so catastrophic cancellation cannot change a decision.
    """
    src = _as_f64(src)
    if length <= 1:
        raise ValueError("length must be > 1 for a sample standard deviation")
    out = np.zeros_like(src)
    if src.size < length:
        return out  # source returns zeros for short input; preserved deliberately
    for i in range(length - 1, src.size):
        window = src[i - length + 1: i + 1]
        var = float(np.sum((window - window.mean()) ** 2)) / (length - 1)
        out[i] = math.sqrt(max(0.0, var))
    return out


def ema(src, length: int, seed: str = "first") -> np.ndarray:
    """Exponential moving average, alpha = 2/(length+1).

    ``seed="first"`` reproduces hash_momentum.py (ema[0] = close[0]) and
    adaptive_hma_cpp.py n_ema (out[0] = src[0]).
    """
    src = _as_f64(src)
    if length <= 0:
        raise ValueError("length must be positive")
    alpha = 2.0 / (length + 1.0)
    out = np.zeros_like(src)
    if src.size == 0:
        return out
    if seed != "first":
        raise ValueError("only seed='first' is used by the supplied alphas")
    out[0] = src[0]
    for i in range(1, src.size):
        out[i] = alpha * src[i] + (1.0 - alpha) * out[i - 1]
    return out


def wma(src, length: int, end_index: int) -> float:
    """Weighted MA at one index with the source's index clamping (finding HM-08)."""
    src = _as_f64(src)
    if length <= 0:
        return float(src[end_index])
    total = 0.0
    weight_total = 0.0
    for j in range(length):
        idx = end_index - j
        if idx < 0:
            idx = 0
        weight = length - j
        total += src[idx] * weight
        weight_total += weight
    return total / weight_total if weight_total > 0 else float(src[end_index])


def xhma_at(src, t: int, length: int) -> float:
    """Dynamic Hull MA at t. Reproduces adaptive_hma_cpp.py _xhma_at_t exactly.

    Negative indices clamp to 0, which pads the start of the series with a
    repeated first value; that padding is part of the alpha, not a bug to fix.
    """
    src = _as_f64(src)
    if length <= 1:
        return float(src[t])
    half_len = int(length // 2)
    sqrt_len = int(math.floor(math.sqrt(length)))
    outer = 0.0
    outer_w = 0.0
    for i in range(sqrt_len):
        curr_t = t - i
        if curr_t < 0:
            curr_t = 0
        combined = 2.0 * wma(src, half_len, curr_t) - wma(src, length, curr_t)
        w = sqrt_len - i
        outer += combined * w
        outer_w += w
    return outer / outer_w if outer_w > 0 else float(src[t])


def calc_slope_at(ma_arr, t: int, high, low, close) -> float:
    """Geometric slope angle. Reproduces adaptive_hma_cpp.py _calcslope_at_t."""
    ma_arr, high, low, close = (_as_f64(x) for x in (ma_arr, high, low, close))
    hh = high[t]
    ll = low[t]
    for i in range(1, 34):
        idx = t - i
        if idx < 0:
            idx = 0
        hh = max(hh, high[idx])
        ll = min(ll, low[idx])
    diff = hh - ll
    if diff == 0.0:
        diff = 1e-9
    slope_range = 25.0 / diff * ll
    t_prev2 = max(0, t - 2)
    dt = (ma_arr[t_prev2] - ma_arr[t]) / (close[t] + 1e-9) * slope_range
    c = math.sqrt(1.0 + dt * dt)
    x_angle = round(180.0 * math.acos(1.0 / c) / math.pi)
    return -x_angle if dt > 0.0 else x_angle


# --------------------------------------------------------------------------
# RSI — three distinct conventions live in the supplied files
# --------------------------------------------------------------------------

def _gains_losses(src: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gains = np.zeros_like(src)
    losses = np.zeros_like(src)
    diff = np.diff(src)
    gains[1:] = np.maximum(diff, 0.0)
    losses[1:] = np.maximum(-diff, 0.0)
    return gains, losses


def rsi_vwap_convention(src, length: int) -> np.ndarray:
    """vwap.py n_rsi: SMA seed, Wilder-style (avg*(n-1)+x)/n recursion, 100 on zero loss."""
    src = _as_f64(src)
    if src.size <= length:
        raise WarmupError(f"rsi({length}) needs more than {length} observations, got {src.size}")
    out = np.zeros_like(src)
    gains, losses = _gains_losses(src)
    avg_gain = float(np.mean(gains[1:length + 1]))
    avg_loss = float(np.mean(losses[1:length + 1]))
    out[length] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(length + 1, src.size):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def rsi_hma_legacy(src, length: int) -> np.ndarray:
    """adaptive_hma_cpp.py n_rsi verbatim, including the inconsistent flat rule (HM-07).

    The seed returns 50 when both averages are zero, but every later bar returns
    100 whenever avg_loss is zero regardless of avg_gain.
    """
    src = _as_f64(src)
    out = np.zeros_like(src)
    if src.size <= length:
        return out  # the source returns zeros here
    gains, losses = _gains_losses(src)
    avg_gain = float(np.sum(gains[1:length + 1])) / length
    avg_loss = float(np.sum(losses[1:length + 1])) / length
    if avg_loss == 0.0:
        out[length] = 100.0 if avg_gain > 0.0 else 50.0
    else:
        out[length] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    alpha = 1.0 / length
    for i in range(length + 1, src.size):
        avg_gain = alpha * gains[i] + (1.0 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1.0 - alpha) * avg_loss
        if avg_loss == 0.0:
            out[i] = 100.0                      # <-- the inconsistency (HM-07)
        else:
            out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def rsi_hma_canonical(src, length: int) -> np.ndarray:
    """Repaired flat rule: a flat series stays at 50 instead of jumping to 100.

    Semantic delta SD-HMA-03. Identical to the legacy version wherever
    avg_loss > 0, so only flat segments differ.
    """
    src = _as_f64(src)
    out = np.zeros_like(src)
    if src.size <= length:
        return out
    gains, losses = _gains_losses(src)
    avg_gain = float(np.sum(gains[1:length + 1])) / length
    avg_loss = float(np.sum(losses[1:length + 1])) / length
    out[length] = (100.0 if avg_gain > 0.0 else 50.0) if avg_loss == 0.0 else \
        100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    alpha = 1.0 / length
    for i in range(length + 1, src.size):
        avg_gain = alpha * gains[i] + (1.0 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1.0 - alpha) * avg_loss
        if avg_loss == 0.0:
            out[i] = 100.0 if avg_gain > 0.0 else 50.0   # consistent with the seed
        else:
            out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


# --------------------------------------------------------------------------
# ATR — three distinct conventions live in the supplied files
# --------------------------------------------------------------------------

def true_range(high, low, close) -> np.ndarray:
    """Standard true range; tr[0] = high[0]-low[0] as in adaptive_hma_cpp.py."""
    high, low, close = (_as_f64(x) for x in (high, low, close))
    tr = np.zeros_like(close)
    tr[0] = high[0] - low[0]
    for i in range(1, close.size):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return tr


def atr_vwap_convention(high, low, close, length: int) -> np.ndarray:
    """vwap.py n_atr: tr[0]=0, SMA seed at index `length`, Wilder recursion."""
    high, low, close = (_as_f64(x) for x in (high, low, close))
    if close.size <= length:
        raise WarmupError(f"atr({length}) needs more than {length} observations, got {close.size}")
    tr = np.zeros_like(close)
    for i in range(1, close.size):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out = np.zeros_like(close)
    out[length] = float(np.mean(tr[1:length + 1]))
    for i in range(length + 1, close.size):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


def atr_hma_convention(high, low, close, length: int) -> np.ndarray:
    """adaptive_hma_cpp.py n_atr: true range smoothed by an EMA (2/(n+1)), not Wilder.

    This is the alpha's own convention (guide 3.3) and is preserved, not "fixed".
    """
    return ema(true_range(high, low, close), length)


def atr_hash_legacy_close_move(close, length: int = 14) -> np.ndarray:
    """hash_momentum.py: max(d, |d|) = |close-to-close move|, ignoring high/low (AH-02).

    Seeded at index `length` with mean(tr[1:length+1]) and smoothed with
    alpha = 1/length. Raises on short input instead of indexing out of range.
    """
    close = _as_f64(close)
    if close.size <= length:
        raise WarmupError(
            f"close-move ATR({length}) needs more than {length} observations, got {close.size}"
        )
    tr = np.zeros_like(close)
    for i in range(1, close.size):
        d = close[i] - close[i - 1]
        tr[i] = max(d, abs(d))
    out = np.zeros_like(close)
    alpha = 1.0 / length
    out[length] = float(np.mean(tr[1:length + 1]))
    for i in range(length + 1, close.size):
        out[i] = alpha * tr[i] + (1.0 - alpha) * out[i - 1]
    return out


def atr_hash_true_range_variant(high, low, close, length: int = 14) -> np.ndarray:
    """Research revision SD-HASH-05: the same smoothing, on a real true range.

    A SEPARATE version. It must never be substituted into canonical results.
    """
    high, low, close = (_as_f64(x) for x in (high, low, close))
    if close.size <= length:
        raise WarmupError(f"ATR({length}) needs more than {length} observations, got {close.size}")
    tr = np.zeros_like(close)
    for i in range(1, close.size):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out = np.zeros_like(close)
    alpha = 1.0 / length
    out[length] = float(np.mean(tr[1:length + 1]))
    for i in range(length + 1, close.size):
        out[i] = alpha * tr[i] + (1.0 - alpha) * out[i - 1]
    return out


# --------------------------------------------------------------------------
# Momentum block (hash_momentum.py)
# --------------------------------------------------------------------------

def momentum_block(close, mom_len: int) -> tuple[np.ndarray, np.ndarray]:
    """mom0 = close[t] - close[t-mom_len]; mom_norm = mom0 / population std over 3*mom_len."""
    close = _as_f64(close)
    n = close.size
    mom0 = np.zeros(n)
    for i in range(mom_len, n):
        mom0[i] = close[i] - close[i - mom_len]
    mom_norm = np.zeros(n)
    window = mom_len * 3
    for i in range(window, n):
        std = float(np.std(mom0[i - window + 1: i + 1]))   # population std, matching np.std default
        if std > 0:
            mom_norm[i] = mom0[i] / std
    return mom0, mom_norm


# --------------------------------------------------------------------------
# VWAP (vwap.py)
# --------------------------------------------------------------------------

def daily_vwap(high, low, close, volume, new_day) -> np.ndarray:
    """Session VWAP on hlc3, reset whenever new_day is True. Reproduces n_vwap_daily."""
    high, low, close, volume = (_as_f64(x) for x in (high, low, close, volume))
    new_day = np.asarray(new_day, dtype=bool)
    out = np.zeros_like(close)
    cum_pv = 0.0
    cum_vol = 0.0
    for i in range(close.size):
        if new_day[i]:
            cum_pv = 0.0
            cum_vol = 0.0
        hlc3 = (high[i] + low[i] + close[i]) / 3.0
        cum_pv += hlc3 * volume[i]
        cum_vol += volume[i]
        out[i] = cum_pv / cum_vol if cum_vol != 0 else hlc3
    return out


# --------------------------------------------------------------------------
# Money Flow Index (signal_combine.py uses ta.volume.MFIIndicator)
# --------------------------------------------------------------------------

def mfi(high, low, close, volume, length: int) -> np.ndarray:
    """Money Flow Index reference, matching ta.volume.MFIIndicator's convention.

    ``ta`` compares the typical price to its previous value and treats an
    unchanged typical price as neither positive nor negative flow.
    """
    high, low, close, volume = (_as_f64(x) for x in (high, low, close, volume))
    n = close.size
    typical = (high + low + close) / 3.0
    raw_flow = typical * volume
    out = np.full(n, np.nan)
    if n <= length:
        return out
    up = np.zeros(n)
    down = np.zeros(n)
    for i in range(1, n):
        if typical[i] > typical[i - 1]:
            up[i] = raw_flow[i]
        elif typical[i] < typical[i - 1]:
            down[i] = raw_flow[i]
    for i in range(length, n):
        pos = float(np.sum(up[i - length + 1: i + 1]))
        neg = float(np.sum(down[i - length + 1: i + 1]))
        out[i] = 100.0 - (100.0 / (1.0 + pos / neg)) if neg > 0 else 100.0
    return out
