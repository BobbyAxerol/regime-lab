"""Compiled twins of the A-HMA hot path, admitted only on bit-exact parity.

``xhma_at`` costs about 17 ``wma`` calls per bar, each O(length). At the declared
A-HMA lengths that measured at 94% of a candidate evaluation, which makes a
96-candidate budget unaffordable. These kernels are the same arithmetic in the
same order under ``@njit`` -- no ``fastmath``, no vectorised reduction, because a
pairwise or SIMD sum would change the accumulation order and therefore the last
bits (the same trap that made the LAB-02 ``vwap.n_sma`` parity case fail).

Nothing here is used unless :func:`verify_parity` reports every case exact. The
interpreted functions in ``indicators.py`` stay the reference definition.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit


@njit(cache=True, nogil=True)
def _wma(src, length, end_index):
    if length <= 0:
        return src[end_index]
    total = 0.0
    weight_total = 0.0
    for j in range(length):
        idx = end_index - j
        if idx < 0:
            idx = 0
        weight = length - j
        total += src[idx] * weight
        weight_total += weight
    if weight_total > 0:
        return total / weight_total
    return src[end_index]


@njit(cache=True, nogil=True)
def _xhma_at(src, t, length):
    if length <= 1:
        return src[t]
    half_len = length // 2
    sqrt_len = int(math.floor(math.sqrt(length)))
    outer = 0.0
    outer_w = 0.0
    for i in range(sqrt_len):
        curr_t = t - i
        if curr_t < 0:
            curr_t = 0
        combined = 2.0 * _wma(src, half_len, curr_t) - _wma(src, length, curr_t)
        w = sqrt_len - i
        outer += combined * w
        outer_w += w
    if outer_w > 0:
        return outer / outer_w
    return src[t]


@njit(cache=True, nogil=True)
def xhma_series(src, lengths, start):
    """``xhma_at`` for every bar from ``start``, with a per-bar length."""
    n = src.shape[0]
    out = np.full(n, np.nan)
    for t in range(start, n):
        length = lengths[t]
        if length > 0:
            out[t] = _xhma_at(src, t, length)
    return out


def wma(src, length: int, end_index: int) -> float:
    return float(_wma(np.asarray(src, dtype=np.float64), int(length), int(end_index)))


def xhma_at(src, t: int, length: int) -> float:
    return float(_xhma_at(np.asarray(src, dtype=np.float64), int(t), int(length)))


def verify_parity(seed: int = 20260910, n: int = 400) -> dict:
    """Compare every kernel against the interpreted reference, bit for bit."""
    from . import indicators as ref

    rng = np.random.default_rng(seed)
    src = np.cumsum(rng.normal(0.0, 1.0, n)) + 100.0
    cases = []
    exact = True
    for length in (2, 3, 7, 20, 55, 200, 240, 360):
        for t in (0, 1, 5, 199, n - 1):
            a = ref.xhma_at(src, t, length)
            b = xhma_at(src, t, length)
            same = (a == b) or (math.isnan(a) and math.isnan(b))
            exact &= same
            if not same:
                cases.append({"kernel": "xhma_at", "length": length, "t": t,
                              "reference": a, "compiled": b, "abs_diff": abs(a - b)})
    for length in (1, 4, 30, 200):
        for t in (0, 3, n - 1):
            a = ref.wma(src, length, t)
            b = wma(src, length, t)
            same = a == b
            exact &= same
            if not same:
                cases.append({"kernel": "wma", "length": length, "t": t,
                              "reference": a, "compiled": b, "abs_diff": abs(a - b)})
    lengths = np.full(n, 200, dtype=np.int64)
    series = xhma_series(src, lengths, 0)
    for t in (0, 10, 250, n - 1):
        a = ref.xhma_at(src, t, 200)
        if a != series[t]:
            exact = False
            cases.append({"kernel": "xhma_series", "t": t, "reference": a,
                          "compiled": float(series[t]), "abs_diff": abs(a - series[t])})
    return {
        "schema": "crypto_regime_lab.fast_indicator_parity.v1",
        "exact": bool(exact),
        "tolerance": "bit-exact equality; no tolerance is granted",
        "fastmath": False,
        "mismatches": cases,
        "admission_rule": "the compiled path is used only while exact is true",
    }
