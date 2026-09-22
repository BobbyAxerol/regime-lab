"""RA07.5 shared statistics primitives (guide section 13.1/13.4).

Pure math over STORED daily equity series -- no engine calls anywhere in
this module (guide: "Engine calls cho bootstrap/statistical calibration
phai bang 0 [S4]"). Used by ra07_decay.py (D1's IS/OOS Sharpe, which DOES
sit downstream of a real replay call made elsewhere) and ra07_statistics.py
(the block bootstrap, which must never call the engine).

Canonical daily return (guide 13.1): r_d = E_d/E_{d-1} - 1, computed BEFORE
any reporting-window clip. `equity_daily` is a list of [iso_date, equity]
pairs, the same account-payload shape every RA phase's real account result
carries.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 365


def daily_returns(equity_daily: list) -> list[dict]:
    """r_d = E_d/E_{d-1} - 1 for every consecutive pair; flat days keep 0,
    a zero-denominator day is flagged rather than silently divided."""
    if not equity_daily:
        return []
    ordered = sorted(((pd.Timestamp(d), float(v)) for d, v in equity_daily), key=lambda r: r[0])
    out = []
    for (prev_date, prev_val), (date, val) in zip(ordered, ordered[1:]):
        if prev_val == 0:
            out.append({"date": date.isoformat(), "return": None, "status": "ZERO_DENOMINATOR"})
        else:
            out.append({"date": date.isoformat(), "return": (val / prev_val) - 1.0, "status": "OK"})
    return out


def paired_daily_returns(equity_a: list, equity_b: list) -> list[dict]:
    """Align two equity_daily series on their COMMON dates (guide 13.4's
    'same calendar' requirement) and return one row per common date with
    both arms' real daily return and the signed difference (a - b)."""
    ret_a = {r["date"]: r for r in daily_returns(equity_a) if r["status"] == "OK"}
    ret_b = {r["date"]: r for r in daily_returns(equity_b) if r["status"] == "OK"}
    common = sorted(set(ret_a) & set(ret_b))
    return [{"date": d, "r_a": ret_a[d]["return"], "r_b": ret_b[d]["return"],
            "diff": ret_a[d]["return"] - ret_b[d]["return"]} for d in common]


def sharpe(returns: list, *, trading_days_per_year: int = TRADING_DAYS_PER_YEAR):
    """Annualised Sharpe: sample stddev (ddof=1), sqrt(365) convention
    (guide 13.1) -- never sqrt(len(returns)). None (+ reason) on too few
    observations or zero variance, never silently replaced by 0."""
    clean = [float(r) for r in returns if r is not None and math.isfinite(r)]
    if len(clean) < 2:
        return {"value": None, "status": "TOO_FEW_OBSERVATIONS", "n": len(clean)}
    sd = float(np.std(clean, ddof=1))
    if sd == 0.0:
        return {"value": None, "status": "ZERO_VARIANCE", "n": len(clean)}
    mean = float(np.mean(clean))
    return {"value": mean / sd * math.sqrt(trading_days_per_year), "status": "OK", "n": len(clean)}


def profit_factor_return(returns: list) -> dict:
    """PF_return = sum(positive returns) / abs(sum(negative returns)) over
    the registered sampling (guide 13.1) -- distinct from PF_trade, which
    this module never computes (that needs engine-derived trade/campaign
    PnL, not a return series)."""
    clean = [float(r) for r in returns if r is not None and math.isfinite(r)]
    if not clean:
        return {"value": None, "status": "NO_TRADES"}
    gains = sum(r for r in clean if r > 0)
    losses = -sum(r for r in clean if r < 0)
    if losses == 0 and gains == 0:
        return {"value": None, "status": "NO_WIN"}
    if losses == 0:
        return {"value": None, "status": "NO_LOSS_DENOMINATOR"}
    return {"value": gains / losses, "status": "OK"}


def _equity_path_from_returns(returns: list, *, start: float = 1.0) -> list:
    path = [start]
    for r in returns:
        path.append(path[-1] * (1.0 + (r or 0.0)))
    return path


def circular_block_indices(n: int, *, block_length: int, rng: np.random.Generator) -> list:
    """One circular-moving-block resample of index positions [0, n): draw
    block start points uniformly on the circular index (wrap-around), take
    `block_length`-long runs, concatenate until >= n indices, then trim to
    exactly n. This is what makes it a BLOCK bootstrap rather than an iid
    resample of single days (guide 13.4: 'circular moving calendar
    blocks')."""
    if n <= 0:
        return []
    block_length = max(1, min(block_length, n))
    indices: list = []
    while len(indices) < n:
        start = int(rng.integers(0, n))
        block = [(start + offset) % n for offset in range(block_length)]
        indices.extend(block)
    return indices[:n]


def bootstrap_paired_delta(rows: list, *, block_length: int, n_resamples: int, seed: int) -> dict:
    """The RA07.5 primary bootstrap: resample BLOCKS of (date, r_a, r_b)
    together (same indices for both arms, guide 13.4: 'same block resample
    indexes cho paired arms'), recompute Delta-hat, SR_a, SR_b, PF_a, PF_b
    from each resampled PATH (never from the distribution of per-day/
    per-fold Sharpes). Zero engine calls -- pure numpy over `rows`, which
    the caller must have already built from STORED equity_daily.
    """
    n = len(rows)
    if n == 0:
        return {"status": "NO_PAIRED_DAYS", "n_common_days": 0}
    diffs = np.array([r["diff"] for r in rows], dtype=float)
    r_a = np.array([r["r_a"] for r in rows], dtype=float)
    r_b = np.array([r["r_b"] for r in rows], dtype=float)
    point_estimate = float(np.mean(diffs))
    if bool(np.all(diffs == 0.0)):
        # Degenerate identical-arms input: every paired diff is exactly zero,
        # so NO resample can produce a nonzero delta. The percentile machinery
        # below would return p=0.0 (frac_above == frac_below == 0 means
        # "no resample exceeded zero on either side" -- read backwards as
        # significance). Short-circuit with the maximal p-value and a CI
        # collapsed on zero, flagged as degenerate. Caught by FP01-T06; the
        # non-degenerate path below is unchanged.
        return {
            "status": "OK",
            "n_common_days": n,
            "block_length_days": block_length,
            "n_resamples": n_resamples,
            "seed": seed,
            "point_estimate": 0.0,
            "bootstrap_mean": 0.0,
            "bootstrap_se": 0.0,
            "ci_95": [0.0, 0.0],
            "ci_method": "percentile",
            "p_value_two_sided": 1.0,
            "degenerate_identical_arms": True,
            "degenerate_reason": ("every paired diff is exactly 0.0: no resample can "
                                  "leave zero, so significance is impossible by "
                                  "construction, not measured"),
            "sharpe_a": {"resample_mean": None, "resample_n_valid": 0,
                         "resample_n_invalid": n_resamples},
            "sharpe_b": {"resample_mean": None, "resample_n_valid": 0,
                         "resample_n_invalid": n_resamples},
            "pf_a": {"resample_mean": None, "resample_n_valid": 0,
                     "resample_n_invalid": n_resamples},
            "pf_b": {"resample_mean": None, "resample_n_valid": 0,
                     "resample_n_invalid": n_resamples},
            "whole_sample_sharpe_a": sharpe(list(r_a)),
            "whole_sample_sharpe_b": sharpe(list(r_b)),
        }

    rng = np.random.default_rng(seed)
    deltas = np.empty(n_resamples, dtype=float)
    sharpe_a_draws, sharpe_b_draws = [], []
    pf_a_draws, pf_b_draws = [], []
    invalid_sharpe_a = invalid_sharpe_b = invalid_pf_a = invalid_pf_b = 0
    for b in range(n_resamples):
        idx = circular_block_indices(n, block_length=block_length, rng=rng)
        deltas[b] = float(np.mean(diffs[idx]))
        sa = sharpe(list(r_a[idx]))
        sb = sharpe(list(r_b[idx]))
        pa = profit_factor_return(list(r_a[idx]))
        pb = profit_factor_return(list(r_b[idx]))
        if sa["status"] == "OK":
            sharpe_a_draws.append(sa["value"])
        else:
            invalid_sharpe_a += 1
        if sb["status"] == "OK":
            sharpe_b_draws.append(sb["value"])
        else:
            invalid_sharpe_b += 1
        if pa["status"] == "OK":
            pf_a_draws.append(pa["value"])
        else:
            invalid_pf_a += 1
        if pb["status"] == "OK":
            pf_b_draws.append(pb["value"])
        else:
            invalid_pf_b += 1

    ci_low, ci_high = (float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5)))
    frac_above = float(np.mean(deltas > 0))
    frac_below = float(np.mean(deltas < 0))
    p_value = min(1.0, 2.0 * min(frac_above, frac_below))
    return {
        "status": "OK",
        "n_common_days": n,
        "block_length_days": block_length,
        "n_resamples": n_resamples,
        "seed": seed,
        "point_estimate": point_estimate,
        "bootstrap_mean": float(np.mean(deltas)),
        "bootstrap_se": float(np.std(deltas, ddof=1)),
        "ci_95": [ci_low, ci_high],
        "ci_method": "percentile",
        "p_value_two_sided": p_value,
        "sharpe_a": {"resample_mean": float(np.mean(sharpe_a_draws)) if sharpe_a_draws else None,
                    "resample_n_valid": len(sharpe_a_draws), "resample_n_invalid": invalid_sharpe_a},
        "sharpe_b": {"resample_mean": float(np.mean(sharpe_b_draws)) if sharpe_b_draws else None,
                    "resample_n_valid": len(sharpe_b_draws), "resample_n_invalid": invalid_sharpe_b},
        "pf_a": {"resample_mean": float(np.mean(pf_a_draws)) if pf_a_draws else None,
                "resample_n_valid": len(pf_a_draws), "resample_n_invalid": invalid_pf_a},
        "pf_b": {"resample_mean": float(np.mean(pf_b_draws)) if pf_b_draws else None,
                "resample_n_valid": len(pf_b_draws), "resample_n_invalid": invalid_pf_b},
        "whole_sample_sharpe_a": sharpe(list(r_a)),
        "whole_sample_sharpe_b": sharpe(list(r_b)),
        "whole_sample_pf_a": profit_factor_return(list(r_a)),
        "whole_sample_pf_b": profit_factor_return(list(r_b)),
        "no_engine_calls": True,
    }


def bootstrap_numeric_reference_check(*, seed: int = 20260919, n: int = 300,
                                      n_resamples: int = 3000,
                                      tolerance: float = 0.15) -> dict:
    """G07-STATS's 'verify centering/inversion bang numeric reference'
    (guide 13.4): synthetic i.i.d. paired data with a KNOWN true mean
    difference and a KNOWN analytic SE (sigma/sqrt(n)) -- checks the
    bootstrap is centered near the true value and its SE tracks the
    analytic formula, at block_length=1 (which degenerates a block
    bootstrap to plain i.i.d. resampling, the case with a closed-form
    reference). This runs against SYNTHETIC numbers only, never real
    account data -- it validates the estimator's implementation, not any
    RA-07 result."""
    rng = np.random.default_rng(seed)
    true_delta, diff_sigma = 0.001, 0.02
    # diff's own noise is independent of a's level, so the difference series
    # has a controlled, non-degenerate variance (diff_sigma) to check the
    # bootstrap SE against -- letting b = a - true_delta + tiny-noise would
    # cancel a's variance out of diff entirely and trivially "pass".
    a = rng.normal(0.0005, 0.01, n)
    diff_noise = rng.normal(0.0, diff_sigma, n)
    b = a - true_delta - diff_noise
    rows = [{"date": str(i), "r_a": float(a[i]), "r_b": float(b[i]), "diff": float(a[i] - b[i])}
           for i in range(n)]
    boot = bootstrap_paired_delta(rows, block_length=1, n_resamples=n_resamples, seed=seed + 1)
    analytic_se = float(np.std([r["diff"] for r in rows], ddof=1)) / math.sqrt(n)
    se_ratio = boot["bootstrap_se"] / analytic_se if analytic_se else None
    centered = abs(boot["point_estimate"] - true_delta) < 3 * analytic_se
    se_ok = se_ratio is not None and abs(se_ratio - 1.0) <= tolerance
    ci_covers_truth = boot["ci_95"][0] <= true_delta <= boot["ci_95"][1]
    return {
        "schema": "regime_lab.ra07_bootstrap_numeric_reference_check.v1",
        "synthetic_true_delta": true_delta, "analytic_se": analytic_se,
        "bootstrap_point_estimate": boot["point_estimate"], "bootstrap_se": boot["bootstrap_se"],
        "se_ratio_bootstrap_over_analytic": se_ratio, "tolerance": tolerance,
        "centered_within_3_analytic_se": centered, "se_within_tolerance": se_ok,
        "ci_95_covers_true_delta": ci_covers_truth,
        "pass": bool(centered and se_ok and ci_covers_truth),
        "uses_only_synthetic_data": True,
    }


def holm_adjust(named_p_values: dict) -> dict:
    """Standard Holm step-down over a named family of p-values (guide 13.4:
    'co the giu Holm cho secondary family'). Order ascending, multiply the
    k-th smallest by (m - k), enforce monotonicity, cap at 1."""
    items = sorted(named_p_values.items(), key=lambda kv: kv[1])
    m = len(items)
    adjusted = {}
    running_max = 0.0
    for k, (name, p) in enumerate(items):
        value = min(1.0, (m - k) * p)
        running_max = max(running_max, value)
        adjusted[name] = running_max
    return adjusted
