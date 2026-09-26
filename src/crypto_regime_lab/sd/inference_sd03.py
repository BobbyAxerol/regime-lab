"""SD-03: paired block-bootstrap inference and the guide's own decision
table (guide SS7.2, SS7.4). This is the ``analysis_plan`` guide SS7.2
requires to be LOCKED before FINAL runs -- frozen here, before any real
FINAL fold exists, never adjusted after seeing an outcome.

Decision-rule interpretation note (disclosed, not silently assumed): guide
SS7.4's table is written as prose, not a literal priority-ordered state
machine -- several rows describe overlapping regions of (point estimate, CI)
space (e.g. row 3 "CI crosses zero" vs rows 7/8 about the 0.20 hurdle,
independently of where zero falls). This module resolves the table into an
explicit priority cascade:

  1. NOT_EVALUABLE (invalid/missing data)
  2. INSUFFICIENT_PAIRED_FOLDS (<12)
  3. EXACT_ZERO_OBSERVED (a degenerate bootstrap: every paired difference
     is exactly zero -- B and C took identical actions with identical
     outcomes in-sample, so no CI computed from it can be trusted)
  4. ACTIVE_JM_EFFECT_NOT_EXERCISED (C was in GLOBAL_FALLBACK at every
     fold -- there is no active correction to have measured an effect of)
  5. Direction first (does the CI clear zero at all), THEN magnitude
     against the 0.20 Sharpe-point hurdle -- matching guide's own framing
     that the 0.20 hurdle question is meaningless until direction is
     established.
"""
from __future__ import annotations

import math

DEFAULT_RESAMPLES = 5000
PRIMARY_BLOCK_LENGTH = 4
SENSITIVITY_BLOCK_LENGTHS = (2, 3)
MEANINGFUL_R_THRESHOLD = 0.20            # registration.json meaningful_decay_reduction_sharpe_points
NONINFERIORITY_MARGIN = -0.10            # registration.json oos_sharpe_noninferiority_margin_sharpe_points
MIN_PAIRED_FOLDS = 12

DECISION_NOT_EVALUABLE = "NOT_EVALUABLE"
DECISION_INSUFFICIENT_PAIRED_FOLDS = "INSUFFICIENT_PAIRED_FOLDS"
DECISION_EXACT_ZERO_OBSERVED = "EXACT_ZERO_OBSERVED"
DECISION_ACTIVE_JM_EFFECT_NOT_EXERCISED = "ACTIVE_JM_EFFECT_NOT_EXERCISED"
DECISION_DECAY_WORSENED = "DECAY_WORSENED_WITHIN_SCOPE"
DECISION_MEANINGFUL_REDUCTION = "MEANINGFUL_SHARPE_DECAY_REDUCTION_WITHIN_SCOPE"
DECISION_GAP_REDUCTION_RETENTION_UNRESOLVED = "GAP_REDUCTION_RETENTION_UNRESOLVED"
DECISION_REDUCTION_DETECTED_MAGNITUDE_UNPROVEN = "REDUCTION_DETECTED_MAGNITUDE_UNPROVEN"
DECISION_NO_MEANINGFUL_REDUCTION_AT_020 = "NO_MEANINGFUL_REDUCTION_AT_0_20_WITHIN_SCOPE"
DECISION_OBSERVED_REDUCTION_NOT_PROVEN_RELIABLE = "OBSERVED_REDUCTION_NOT_PROVEN_RELIABLE"
DECISION_INCONCLUSIVE_MAGNITUDE = "INCONCLUSIVE_MAGNITUDE"


class InferenceError(ValueError):
    """An inference step was internally inconsistent."""


def block_bootstrap_ci(values: list, *, block_length: int, resamples: int = DEFAULT_RESAMPLES,
                       seed: int, confidence_level: float = 0.95) -> dict:
    """Moving/circular block bootstrap on a 1-D paired-difference series
    (guide SS7.2). Returns the basic-bootstrap CI (2*mean - upper_quantile,
    2*mean - lower_quantile centering/inversion) plus the raw resample
    means for reference. A zero-variance/degenerate input is flagged, never
    silently given a fabricated interval."""
    import numpy as np

    n = len(values)
    if n == 0:
        raise InferenceError("block_bootstrap_ci requires at least one value")
    arr = np.asarray(values, dtype=float)
    point_estimate = float(arr.mean())
    if n < block_length:
        return {"point_estimate": point_estimate, "ci_lower": None, "ci_upper": None,
               "status": "TOO_FEW_OBSERVATIONS_FOR_BLOCK_LENGTH", "n": n,
               "block_length": block_length, "resamples": resamples}
    if float(arr.std(ddof=1)) == 0.0:
        return {"point_estimate": point_estimate, "ci_lower": point_estimate, "ci_upper": point_estimate,
               "status": "DEGENERATE_ZERO_VARIANCE", "n": n, "block_length": block_length,
               "resamples": resamples}

    rng = np.random.default_rng(seed)
    n_blocks_needed = math.ceil(n / block_length)
    resample_means = np.empty(resamples, dtype=float)
    max_start = n - block_length + 1   # circular wrap allowed via modulo below
    for i in range(resamples):
        starts = rng.integers(0, max_start if max_start > 0 else n, size=n_blocks_needed)
        chunks = [arr[np.arange(s, s + block_length) % n] for s in starts]
        resampled = np.concatenate(chunks)[:n]
        resample_means[i] = resampled.mean()

    alpha = 1.0 - confidence_level
    lo_q, hi_q = np.quantile(resample_means, [alpha / 2, 1 - alpha / 2])
    ci_lower = float(2 * point_estimate - hi_q)
    ci_upper = float(2 * point_estimate - lo_q)
    return {"point_estimate": point_estimate, "ci_lower": ci_lower, "ci_upper": ci_upper,
           "status": "OK", "n": n, "block_length": block_length, "resamples": resamples,
           "confidence_level": confidence_level, "seed": seed}


def paired_r_series(fold_records: list) -> list:
    """D_B - D_C over folds with BOTH sides defined -- the primary R series
    guide SS7.1 wants (mean paired signed reduction of C-B, C decaying
    LESS than B means positive R). Never imputes a missing side."""
    out = []
    for fold in fold_records:
        d_b = fold["arms"]["B_SD_GLOBAL"].get("D_selected")
        d_c_key = next((k for k in fold["arms"] if k.startswith("JM_C")), None)
        d_c = fold["arms"][d_c_key].get("D_selected") if d_c_key else None
        if d_b is None or d_c is None:
            continue
        out.append(d_b - d_c)
    return out


def paired_q_series(fold_records: list) -> list:
    """Standardized forward Sharpe difference C-B per fold (the SS7.1
    safeguard), over folds with both SR_FWD_selected defined."""
    out = []
    for fold in fold_records:
        sr_b = fold["arms"]["B_SD_GLOBAL"].get("SR_FWD_selected")
        d_c_key = next((k for k in fold["arms"] if k.startswith("JM_C")), None)
        sr_c = fold["arms"][d_c_key].get("SR_FWD_selected") if d_c_key else None
        if sr_b is None or sr_c is None:
            continue
        out.append(sr_c - sr_b)
    return out


def c_all_fallback(fold_records: list) -> bool:
    d_c_key = next((k for k in fold_records[0]["arms"] if k.startswith("JM_C")), None) if fold_records else None
    if d_c_key is None:
        return True
    return all(fold["arms"][d_c_key].get("fallback_reason") is not None for fold in fold_records)


def c_b_exact_match(fold_records: list) -> bool:
    """Guide's EXACT_ZERO_OBSERVED trigger: B and C took the IDENTICAL
    action (same winner_id) at EVERY fold -- the paired R series is then
    identically zero by construction, and a bootstrap over an all-zero
    series is degenerate, not a genuine 'no effect' population estimate."""
    d_c_key = next((k for k in fold_records[0]["arms"] if k.startswith("JM_C")), None) if fold_records else None
    if d_c_key is None:
        return False
    return all(fold["arms"]["B_SD_GLOBAL"]["selection"]["winner_id"]
              == fold["arms"][d_c_key]["selection"]["winner_id"] for fold in fold_records)


def decide(*, r_series: list, q_series: list, seed: int, block_length: int = PRIMARY_BLOCK_LENGTH,
          data_valid: bool = True, fold_records: list = None) -> dict:
    """The full SS7.4 decision cascade -- see module docstring for the
    disclosed priority-ordering resolution of the guide's own prose table."""
    if not data_valid:
        return {"decision": DECISION_NOT_EVALUABLE, "reason": "invalid/missing mandatory arm data"}
    if len(r_series) < MIN_PAIRED_FOLDS:
        return {"decision": DECISION_INSUFFICIENT_PAIRED_FOLDS,
               "reason": f"{len(r_series)} < {MIN_PAIRED_FOLDS} paired-valid folds"}

    if fold_records is not None:
        if c_b_exact_match(fold_records):
            return {"decision": DECISION_EXACT_ZERO_OBSERVED,
                   "reason": "B and C selected the identical candidate at every fold -- "
                             "a degenerate bootstrap, not a measured null effect"}
        if c_all_fallback(fold_records):
            return {"decision": DECISION_ACTIVE_JM_EFFECT_NOT_EXERCISED,
                   "reason": "C was in GLOBAL_FALLBACK at every fold -- no active correction "
                             "was ever exercised to measure an effect of"}

    r_ci = block_bootstrap_ci(r_series, block_length=block_length, seed=seed)
    q_ci = block_bootstrap_ci(q_series, block_length=block_length, seed=seed) if q_series else None
    if r_ci["status"] != "OK":
        return {"decision": DECISION_INCONCLUSIVE_MAGNITUDE, "reason": r_ci["status"],
               "r_ci": r_ci, "q_ci": q_ci}

    lo, hi, point = r_ci["ci_lower"], r_ci["ci_upper"], r_ci["point_estimate"]
    safety_ok = q_ci is not None and q_ci["status"] == "OK" and q_ci["ci_lower"] is not None \
        and q_ci["ci_lower"] > NONINFERIORITY_MARGIN

    if hi < 0:
        decision = DECISION_DECAY_WORSENED
    elif lo > MEANINGFUL_R_THRESHOLD:
        decision = DECISION_MEANINGFUL_REDUCTION if safety_ok else DECISION_GAP_REDUCTION_RETENTION_UNRESOLVED
    elif lo > 0:
        decision = DECISION_REDUCTION_DETECTED_MAGNITUDE_UNPROVEN
    elif hi < MEANINGFUL_R_THRESHOLD:
        decision = DECISION_NO_MEANINGFUL_REDUCTION_AT_020
    else:
        decision = (DECISION_OBSERVED_REDUCTION_NOT_PROVEN_RELIABLE if point > 0
                   else DECISION_INCONCLUSIVE_MAGNITUDE)

    return {"decision": decision, "r_ci": r_ci, "q_ci": q_ci, "safety_ok": safety_ok}


def sensitivity_analysis(*, r_series: list, q_series: list, seed: int,
                         block_lengths: tuple = SENSITIVITY_BLOCK_LENGTHS) -> dict:
    """Guide SS7.2: 'sensitivities 2 va 3 folds bao tat ca, khong chon cai
    significant' -- computes the SAME bootstrap at every registered
    sensitivity block length and reports ALL of them alongside the primary
    (block length 4) result, never cherry-picking whichever one happens to
    look significant. Purely descriptive: this function makes no decision
    of its own and must not be used to override ``decide()``'s own primary
    verdict."""
    out = {}
    for block_length in block_lengths:
        r_ci = block_bootstrap_ci(r_series, block_length=block_length, seed=seed)
        q_ci = block_bootstrap_ci(q_series, block_length=block_length, seed=seed) if q_series else None
        out[block_length] = {"r_ci": r_ci, "q_ci": q_ci}
    return out
