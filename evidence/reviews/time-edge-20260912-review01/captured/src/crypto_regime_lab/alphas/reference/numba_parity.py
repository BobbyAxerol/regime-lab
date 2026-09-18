"""Numba / fastmath parity (guide L02.2, finding HM-08).

The oracle is pure Python with no fastmath. The alphas ship ``@njit`` kernels and
``adaptive_hma_cpp.py`` uses ``fastmath=True``, which permits floating-point
reassociation. Whether that changes a DECISION is measured here, not assumed:
the same source functions are loaded twice — once with the decorators stripped
(interpreted) and once compiled — and their outputs are compared.

The rule the guide sets is that an accelerated kernel may only be enabled if it
does not change decisions. A numeric difference below the decision threshold is
acceptable and recorded; a different signal is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..source_harness import default_injection, load_functions, numba_injection

# Kernel-level agreement expected from an IEEE-conformant compile; fastmath may
# reassociate, so a small relative drift is tolerated at the VALUE level while
# decisions must match exactly.
VALUE_RTOL = 1e-9
VALUE_ATOL = 1e-9


@dataclass
class NumbaParityResult:
    kernel: str
    fastmath: bool
    max_abs_error: float
    max_rel_error: float
    values_within_tolerance: bool
    decisions_identical: bool | None
    decision_note: str = ""

    def as_record(self) -> dict:
        return {
            "kernel": self.kernel,
            "fastmath": self.fastmath,
            "max_abs_error": self.max_abs_error,
            "max_rel_error": self.max_rel_error,
            "values_within_tolerance": self.values_within_tolerance,
            "decisions_identical": self.decisions_identical,
            "decision_note": self.decision_note,
            "tolerance": {"rtol": VALUE_RTOL, "atol": VALUE_ATOL},
        }


def _fixture(n: int = 300, seed: int = 20260909):
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.8, n))
    high = close + np.abs(rng.normal(0.0, 0.4, n))
    low = close - np.abs(rng.normal(0.0, 0.4, n))
    volume = np.abs(rng.normal(1000.0, 200.0, n)) + 1.0
    return close, high, low, volume


def _compare(kernel: str, fastmath: bool, a, b, decisions=None) -> NumbaParityResult:
    a = np.asarray(a, dtype=float).reshape(-1)
    b = np.asarray(b, dtype=float).reshape(-1)
    finite = np.isfinite(a) & np.isfinite(b)
    diff = np.abs(a[finite] - b[finite])
    denom = np.maximum(np.abs(b[finite]), 1e-12)
    max_abs = float(diff.max()) if diff.size else 0.0
    max_rel = float((diff / denom).max()) if diff.size else 0.0
    within = bool(max_abs <= VALUE_ATOL or max_rel <= VALUE_RTOL)
    identical = None
    note = ""
    if decisions is not None:
        d_interp, d_compiled = decisions
        identical = bool(np.array_equal(np.asarray(d_interp), np.asarray(d_compiled)))
        note = ("decision arrays are identical" if identical
                else "DECISIONS DIFFER: the compiled kernel may not be enabled")
    return NumbaParityResult(kernel, fastmath, max_abs, max_rel, within, identical, note)


def numba_parity(raw_dir: str | Path) -> dict:
    raw_dir = Path(raw_dir)
    close, high, low, volume = _fixture()
    results: list[NumbaParityResult] = []

    # ---- vwap.py: plain @njit, no fastmath ----
    names_v = ("n_sma", "n_stdev", "n_rsi", "n_atr", "n_vwap_daily")
    interp_v = load_functions(raw_dir / "vwap.py", names_v, inject=default_injection())
    comp_v = load_functions(raw_dir / "vwap.py", names_v, inject=numba_injection(),
                            keep_decorators=True)
    results.append(_compare("vwap.n_sma", False, interp_v["n_sma"](close, 50),
                            comp_v["n_sma"](close, 50)))
    results.append(_compare("vwap.n_stdev", False, interp_v["n_stdev"](close, 50),
                            comp_v["n_stdev"](close, 50)))
    results.append(_compare("vwap.n_rsi", False, interp_v["n_rsi"](close, 14),
                            comp_v["n_rsi"](close, 14)))
    results.append(_compare("vwap.n_atr", False, interp_v["n_atr"](high, low, close, 14),
                            comp_v["n_atr"](high, low, close, 14)))
    new_day = np.zeros(close.size, dtype=np.bool_)
    new_day[0] = True
    new_day[::96] = True
    results.append(_compare("vwap.n_vwap_daily", False,
                            interp_v["n_vwap_daily"](high, low, close, volume, new_day),
                            comp_v["n_vwap_daily"](high, low, close, volume, new_day)))

    # ---- adaptive_hma_cpp.py: @njit(fastmath=True) ----
    names_h = ("n_ema", "n_atr", "n_rsi", "_xhma_at_t", "_calcslope_at_t")
    interp_h = load_functions(raw_dir / "adaptive_hma_cpp.py", names_h, inject=default_injection())
    comp_h = load_functions(raw_dir / "adaptive_hma_cpp.py", names_h, inject=numba_injection(),
                            keep_decorators=True)
    results.append(_compare("hma.n_ema[fastmath]", True, interp_h["n_ema"](close, 21),
                            comp_h["n_ema"](close, 21)))
    results.append(_compare("hma.n_atr[fastmath]", True, interp_h["n_atr"](high, low, close, 21),
                            comp_h["n_atr"](high, low, close, 21)))
    rsi_i = interp_h["n_rsi"](close, 14)
    rsi_c = comp_h["n_rsi"](close, 14)
    # A-HMA gates entries on RSI bands; the decision is the band membership.
    band_i = np.digitize(rsi_i, [30.0, 49.0, 51.0, 70.0])
    band_c = np.digitize(rsi_c, [30.0, 49.0, 51.0, 70.0])
    results.append(_compare("hma.n_rsi[fastmath]", True, rsi_i, rsi_c,
                            decisions=(band_i, band_c)))
    xh_i = np.array([interp_h["_xhma_at_t"](close, t, 20) for t in range(0, close.size, 5)])
    xh_c = np.array([comp_h["_xhma_at_t"](close, t, 20) for t in range(0, close.size, 5)])
    results.append(_compare("hma._xhma_at_t[fastmath]", True, xh_i, xh_c))
    ma = interp_h["n_ema"](close, 20)
    sl_i = np.array([interp_h["_calcslope_at_t"](ma, t, high, low, close)
                     for t in range(0, close.size, 5)])
    sl_c = np.array([comp_h["_calcslope_at_t"](ma, t, high, low, close)
                     for t in range(0, close.size, 5)])
    # The slope is rounded to a whole angle and compared against `flat`; the
    # rounded value IS the decision.
    results.append(_compare("hma._calcslope_at_t[fastmath]", True, sl_i, sl_c,
                            decisions=(sl_i, sl_c)))

    # ---- hash_momentum.py: plain @njit ----
    interp_m = load_functions(raw_dir / "hash_momentum.py", ("calculate_indicators",),
                              inject=default_injection())
    comp_m = load_functions(raw_dir / "hash_momentum.py", ("calculate_indicators",),
                            inject=numba_injection(), keep_decorators=True)
    out_i = interp_m["calculate_indicators"](close, 20, 30)
    out_c = comp_m["calculate_indicators"](close, 20, 30)
    for name, i_arr, c_arr in zip(("mom0", "mom_norm", "atr", "ema"), out_i, out_c):
        results.append(_compare(f"hash.{name}", False, i_arr, c_arr))

    records = [r.as_record() for r in results]
    value_failures = [r["kernel"] for r in records if not r["values_within_tolerance"]]
    decision_failures = [r["kernel"] for r in records
                         if r["decisions_identical"] is False]
    return {
        "schema": "crypto_regime_lab.numba_parity.v1",
        "policy": (
            "the oracle is fastmath-free. A compiled kernel is only enabled when it reproduces the "
            "oracle's DECISIONS exactly; a sub-threshold value difference is recorded, a different "
            "signal blocks the kernel (guide L02.2, finding HM-08)."
        ),
        "kernel_count": len(records),
        "results": records,
        "value_failures": value_failures,
        "decision_failures": decision_failures,
        "fastmath_kernels": [r["kernel"] for r in records if r["fastmath"]],
        "status": "PASS" if not decision_failures and not value_failures else "FAIL",
    }
