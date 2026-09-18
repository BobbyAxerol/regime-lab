"""Numeric parity contract (guide L02.2).

Two comparisons, both measured rather than assumed:

  1. reference oracle vs the ORIGINAL source kernel loaded through the AST
     harness — the oracle only earns the name if it reproduces the source;
  2. reference oracle vs the ``ta`` library — where a convention genuinely
     differs, the difference is RECORDED as a divergence, never "fixed" on
     either side (the guide forbids silently changing Wilder/EMA/padding
     conventions).

Tolerances are declared per pair up front. A pair whose measured error exceeds
its tolerance is a FAIL that blocks the alpha's certification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..source_harness import default_injection, load_functions
from . import indicators as ref

# Declared before measurement. float64 accumulation order differs between a
# running-sum loop and a windowed recomputation, so a pure-loop pair gets exact
# equality while a re-derived pair gets a small absolute tolerance.
TOLERANCES: dict[str, dict[str, float]] = {
    "exact":        {"atol": 0.0,    "rtol": 0.0},
    "accumulation": {"atol": 1e-9,   "rtol": 1e-12},
    "loose":        {"atol": 1e-6,   "rtol": 1e-9},
    # A pair whose two sides implement DIFFERENT documented conventions. The
    # requirement is not "small" but "characterised and decaying": the seed
    # difference of a Wilder-style recursion must wash out, so the error late in
    # the series must be a small fraction of the error early in it.
    # No atol/rtol: this class is not judged by closeness. Infinity is deliberately
    # NOT used, because the evidence writer refuses non-finite JSON (T61).
    "documented_divergence": {"atol": None, "rtol": None,
                              "max_early_error": 5.0, "required_decay_ratio": 0.10},
}


@dataclass
class ParityResult:
    pair_id: str
    kind: str
    tolerance_class: str
    max_abs_error: float
    max_rel_error: float
    passed: bool
    compared_points: int
    note: str = ""

    def as_record(self) -> dict:
        return {
            "pair_id": self.pair_id,
            "kind": self.kind,
            "tolerance_class": self.tolerance_class,
            "tolerance": TOLERANCES[self.tolerance_class],
            "max_abs_error": self.max_abs_error,
            "max_rel_error": self.max_rel_error,
            "compared_points": self.compared_points,
            "passed": self.passed,
            "note": self.note,
        }


def _compare(pair_id: str, kind: str, a, b, tolerance_class: str,
             mask=None, note: str = "") -> ParityResult:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if mask is None:
        mask = np.ones_like(a, dtype=bool)
    mask = mask & np.isfinite(a) & np.isfinite(b)
    if not mask.any():
        return ParityResult(pair_id, kind, tolerance_class, float("nan"), float("nan"),
                            False, 0, note="no comparable points")
    diff = np.abs(a[mask] - b[mask])
    denom = np.maximum(np.abs(b[mask]), 1e-12)
    max_abs = float(diff.max())
    max_rel = float((diff / denom).max())
    tol = TOLERANCES[tolerance_class]
    if tolerance_class == "documented_divergence":
        idx = np.flatnonzero(mask)
        split = idx.size // 2
        early = float(np.abs(a[idx[:split]] - b[idx[:split]]).max()) if split else max_abs
        late = float(np.abs(a[idx[split:]] - b[idx[split:]]).max()) if split else max_abs
        decayed = late <= max(early * tol["required_decay_ratio"], 1e-12)
        bounded = early <= tol["max_early_error"]
        passed = bool(decayed and bounded)
        note = (note + f" | early_max={early:.3e} late_max={late:.3e} "
                       f"decay_ok={decayed} bounded={bounded}").strip(" |")
        return ParityResult(pair_id, kind, tolerance_class, max_abs, max_rel, passed,
                            int(mask.sum()), note)
    atol, rtol = tol.get("atol"), tol.get("rtol")
    if atol is None and rtol is None:
        passed = bool(max_abs == 0.0)
    elif atol or rtol:
        passed = bool(max_abs <= (atol or 0.0) or max_rel <= (rtol or 0.0))
    else:
        passed = bool(max_abs == 0.0)
    return ParityResult(pair_id, kind, tolerance_class, max_abs, max_rel, passed,
                        int(mask.sum()), note)


def _fixture(n: int = 400, seed: int = 20260909):
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.8, n))
    high = close + np.abs(rng.normal(0.0, 0.4, n))
    low = close - np.abs(rng.normal(0.0, 0.4, n))
    volume = np.abs(rng.normal(1000.0, 200.0, n)) + 1.0
    return close, high, low, volume


def source_parity(raw_dir: str | Path) -> list[ParityResult]:
    """Oracle vs the original kernels, loaded from source without importing them."""
    raw_dir = Path(raw_dir)
    close, high, low, volume = _fixture()
    n = close.size
    inject = default_injection()
    results: list[ParityResult] = []

    # ---- vwap.py ----
    v = load_functions(raw_dir / "vwap.py",
                       ("n_sma", "n_stdev", "n_rsi", "n_atr", "n_vwap_daily"), inject=inject)
    results.append(_compare("vwap.n_sma", "source_vs_oracle",
                            v["n_sma"](close, 50), ref.sma(close, 50), "exact",
                            mask=np.arange(n) >= 49))
    results.append(_compare("vwap.n_stdev", "source_vs_oracle",
                            v["n_stdev"](close, 50), ref.rolling_std_sample(close, 50),
                            "accumulation", mask=np.arange(n) >= 49,
                            note="source uses running sums of x and x^2; the oracle recomputes the "
                                 "window, so a small accumulation difference is expected and bounded"))
    results.append(_compare("vwap.n_rsi", "source_vs_oracle",
                            v["n_rsi"](close, 14), ref.rsi_vwap_convention(close, 14), "exact",
                            mask=np.arange(n) >= 14))
    results.append(_compare("vwap.n_atr", "source_vs_oracle",
                            v["n_atr"](high, low, close, 14), ref.atr_vwap_convention(high, low, close, 14),
                            "exact", mask=np.arange(n) >= 14))
    new_day = np.zeros(n, dtype=bool)
    new_day[0] = True
    new_day[::96] = True
    results.append(_compare("vwap.n_vwap_daily", "source_vs_oracle",
                            v["n_vwap_daily"](high, low, close, volume, new_day),
                            ref.daily_vwap(high, low, close, volume, new_day), "exact"))

    # ---- adaptive_hma_cpp.py ----
    h = load_functions(raw_dir / "adaptive_hma_cpp.py",
                       ("n_ema", "n_atr", "n_rsi", "_xhma_at_t", "_calcslope_at_t"), inject=inject)
    results.append(_compare("hma.n_ema", "source_vs_oracle",
                            h["n_ema"](close, 21), ref.ema(close, 21), "exact"))
    results.append(_compare("hma.n_atr", "source_vs_oracle",
                            h["n_atr"](high, low, close, 21),
                            ref.atr_hma_convention(high, low, close, 21), "exact",
                            note="this alpha smooths true range with an EMA, not Wilder; preserved"))
    results.append(_compare("hma.n_rsi_legacy", "source_vs_oracle",
                            h["n_rsi"](close, 14), ref.rsi_hma_legacy(close, 14), "exact",
                            mask=np.arange(n) >= 14))
    xh_src = np.array([h["_xhma_at_t"](close, t, 20) for t in range(0, n, 7)])
    xh_ref = np.array([ref.xhma_at(close, t, 20) for t in range(0, n, 7)])
    results.append(_compare("hma._xhma_at_t", "source_vs_oracle", xh_src, xh_ref, "exact"))
    ma = h["n_ema"](close, 20)
    sl_src = np.array([h["_calcslope_at_t"](ma, t, high, low, close) for t in range(0, n, 7)])
    sl_ref = np.array([ref.calc_slope_at(ma, t, high, low, close) for t in range(0, n, 7)])
    results.append(_compare("hma._calcslope_at_t", "source_vs_oracle", sl_src, sl_ref, "exact"))

    # ---- hash_momentum.py ----
    hm = load_functions(raw_dir / "hash_momentum.py", ("calculate_indicators",), inject=inject)
    mom0_s, mom_norm_s, atr_s, ema_s = hm["calculate_indicators"](close, 20, 30)
    mom0_r, mom_norm_r = ref.momentum_block(close, 20)
    results.append(_compare("hash.mom0", "source_vs_oracle", mom0_s, mom0_r, "exact"))
    results.append(_compare("hash.mom_norm", "source_vs_oracle", mom_norm_s, mom_norm_r, "exact"))
    results.append(_compare("hash.atr_close_move", "source_vs_oracle", atr_s,
                            ref.atr_hash_legacy_close_move(close, 14), "exact",
                            mask=np.arange(n) >= 14,
                            note="the source's ATR is the absolute close-to-close move (AH-02); "
                                 "the oracle reproduces it rather than repairing it"))
    results.append(_compare("hash.ema", "source_vs_oracle", ema_s, ref.ema(close, 30), "exact"))
    return results


def library_parity() -> list[ParityResult]:
    """Oracle vs ``ta``. Divergences are documented, not reconciled."""
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import SMAIndicator
    from ta.volatility import AverageTrueRange
    from ta.volume import MFIIndicator

    close, high, low, volume = _fixture()
    n = close.size
    s_close, s_high, s_low, s_vol = (pd.Series(x) for x in (close, high, low, volume))
    warm = np.arange(n) >= 60
    results: list[ParityResult] = []

    results.append(_compare(
        "ta.SMAIndicator", "oracle_vs_library",
        ref.sma(close, 50), SMAIndicator(close=s_close, window=50).sma_indicator().to_numpy(),
        "accumulation", mask=warm,
        note="same definition; only float accumulation order differs"))

    results.append(_compare(
        "ta.RSIIndicator", "oracle_vs_library",
        ref.rsi_vwap_convention(close, 14), RSIIndicator(close=s_close, window=14).rsi().to_numpy(),
        "documented_divergence", mask=warm,
        note="ta seeds Wilder's average differently from the alpha's SMA seed; the residual is a "
             "documented convention divergence, and the alpha's convention is the one that ships"))

    results.append(_compare(
        "ta.AverageTrueRange", "oracle_vs_library",
        ref.atr_vwap_convention(high, low, close, 14),
        AverageTrueRange(high=s_high, low=s_low, close=s_close, window=14).average_true_range().to_numpy(),
        "documented_divergence", mask=warm,
        note="ta uses its own smoothing seed; A-SC consumes ta directly so ta is authoritative THERE, "
             "while A-VWAP keeps its own n_atr convention"))

    results.append(_compare(
        "ta.MFIIndicator", "oracle_vs_library",
        ref.mfi(high, low, close, volume, 14),
        MFIIndicator(high=s_high, low=s_low, close=s_close, volume=s_vol, window=14)
        .money_flow_index().to_numpy(),
        "accumulation", mask=warm,
        note="A-SC's condition indicator; the oracle must track ta here because ta is what the alpha runs"))
    return results


def parity_report(raw_dir: str | Path) -> dict:
    source = [r.as_record() for r in source_parity(raw_dir)]
    library = [r.as_record() for r in library_parity()]
    failures = [r["pair_id"] for r in source + library if not r["passed"]]
    divergences = [r["pair_id"] for r in library if r["tolerance_class"] == "documented_divergence"]
    return {
        "schema": "crypto_regime_lab.parity_report.v1",
        "tolerance_classes": TOLERANCES,
        "fastmath": "disabled — the oracle is pure Python/NumPy; source @njit decorators are stripped "
                    "by the AST harness so no fastmath reassociation is exercised (HM-08, SD-HMA-07)",
        "source_vs_oracle": source,
        "oracle_vs_library": library,
        "failures": failures,
        "documented_divergences": divergences,
        "divergence_policy": (
            "A documented divergence is a real difference in convention between the alpha and the "
            "library. Neither side is edited to make them agree. The alpha's own convention is what "
            "ships wherever the alpha computes the indicator itself; ta is authoritative only where "
            "the alpha actually calls ta (A-SC). The requirement is that the seed difference decays."
        ),
        "status": "PASS" if not failures else "FAIL",
    }
