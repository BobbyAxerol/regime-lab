"""Registered paired, calendar-block inference; never bootstrap an engine run."""
import numpy as np
import pandas as pd

from ..experiments.time_edge_contracts import ContractError, holm_adjust

HYPOTHESES = ("H-TIMING", "H-BUDGET", "H-DECAY", "H-MODEL-INFO")


def fixed_cohort(cells, expected_cells):
    if not cells or not set(cells) <= set(expected_cells):
        raise ContractError("nonempty registered cohort required")
    columns = {}
    for cell, rows in sorted(cells.items()):
        dates = pd.to_datetime([r[0] for r in rows], utc=True)
        if dates.has_duplicates:
            raise ContractError("duplicate cell date")
        columns[cell] = pd.Series([float(r[1]) for r in rows], index=dates)
    frame = pd.concat(columns, axis=1)
    common = frame.dropna()
    if common.empty or not np.isfinite(common.to_numpy()).all():
        raise ContractError("no finite common-date cohort")
    if not common.index.equals(pd.date_range(common.index[0], common.index[-1], freq="D")):
        raise ContractError("common date intersection is not a complete daily calendar")
    return {"cells": list(common.columns), "full_cohort": set(cells) == set(expected_cells),
            "excluded_cells": sorted(set(expected_cells)-set(cells)),
            "unmatched_dates": int(len(frame)-len(common)), "fixed_weight": 1/len(cells),
            "dates": [x.isoformat() for x in common.index],
            "values": common.mean(axis=1).tolist()}


def block_mean(values, *, delta, block=28, draws=4999, seed=2026091201, family_size=4, alpha=.05):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or not np.isfinite(delta):
        raise ContractError("finite one-dimensional paired data required")
    if not isinstance(block, int) or not 1 <= block <= len(x) or draws < 99 or family_size != 4:
        raise ContractError("invalid registered bootstrap dimensions")
    estimate = float(x.mean()); centered = x-estimate
    rng = np.random.default_rng(seed)
    # Vectorize block sums; final partial block preserves exactly N observations.
    n = len(x); whole, tail = divmod(n, block)
    cumulative = np.r_[0., np.cumsum(np.r_[centered, centered[:block]])]
    starts = np.arange(n)
    sums = cumulative[starts+block]-cumulative[starts]
    noise = np.empty(draws)
    for offset in range(0, draws, 256):
        count = min(256, draws-offset)
        chosen = rng.integers(0, n, size=(count, whole+(tail > 0)))
        total = sums[chosen[:, :whole]].sum(axis=1)
        if tail:
            s = chosen[:, -1]; total += cumulative[s+tail]-cumulative[s]
        noise[offset:offset+count] = total/n
    def interval(tail_alpha):
        low, high = np.quantile(noise, [tail_alpha, 1-tail_alpha])
        return [float(estimate-high), float(estimate-low)]
    return {"estimate": estimate, "threshold": float(delta), "n": n, "block": block,
            "nonoverlapping_blocks": n//block, "draws": draws, "seed": seed,
            "invalid_draws": 0, "ci95_basic": interval(alpha/2),
            "ci_simultaneous_basic": interval(alpha/(2*family_size)),
            "p_one_sided": float((1+np.count_nonzero(noise >= estimate-delta))/(draws+1))}


def family(series, thresholds, *, draws=4999, seed=2026091201):
    if set(series) != set(HYPOTHESES) or set(thresholds) != set(HYPOTHESES):
        raise ContractError("all four registered hypotheses must remain in family")
    result = {}
    for h in HYPOTHESES:
        values = series[h]
        if values is None or thresholds[h] is None:
            result[h] = {"status": "NOT_EVALUABLE", "estimate": None,
                         "reason": "missing registered contrast or materialized threshold", "p_for_multiplicity": 1.}
            continue
        if isinstance(values, dict):
            primary = block_weighted(values["numerator"],values["weight"],delta=thresholds[h],draws=draws,seed=seed)
            if primary["status"] != "ESTIMATED":
                result[h] = {**primary,"p_for_multiplicity":1.}; continue
            sensitivity = [block_weighted(values["numerator"],values["weight"],delta=thresholds[h],block=b,draws=draws,seed=seed) for b in (7,14,56)]
            result[h] = {**primary,"sensitivity":sensitivity,"p_for_multiplicity":primary["p_one_sided"]}
            continue
        if len(values) < 365:
            result[h] = {"status": "INCONCLUSIVE_SUPPORT", "estimate": float(np.mean(values)) if len(values) else None,
                         "reason": "less than 365 common calendar days", "p_for_multiplicity": 1.}
            continue
        primary = block_mean(values, delta=thresholds[h], draws=draws, seed=seed)
        sensitivity = [block_mean(values, delta=thresholds[h], block=b, draws=draws, seed=seed) for b in (7,14,56)]
        result[h] = {"status": "ESTIMATED_NOT_CLAIMED", **primary, "sensitivity": sensitivity,
                     "p_for_multiplicity": primary["p_one_sided"]}
    adjusted = holm_adjust([result[h]["p_for_multiplicity"] for h in HYPOTHESES])
    for h, p in zip(HYPOTHESES, adjusted):
        result[h]["adjusted_p"] = p
    return result


def block_weighted(numerator, weight, *, delta, block=28, draws=4999, seed=2026091201):
    """Calendar bootstrap for sparse information episodes, preserving denominators.

    Empty calendar dates carry zero numerator AND zero observation weight. They
    are not fabricated zero rank correlations. Zero-support draws block inference.
    """
    y,w=np.asarray(numerator,float),np.asarray(weight,float)
    if y.shape != w.shape or y.ndim != 1 or not np.isfinite(y).all() or not np.isfinite(w).all() or (w < 0).any() or np.any((w == 0) & (y != 0)):
        raise ContractError("invalid calendar episode numerator/denominator")
    if len(y) < 365 or w.sum() < 20 or len(y)//block < 12:
        return {"status":"INCONCLUSIVE_SUPPORT","estimate":None,"reason":"information needs calendar span, blocks and at least 20 episodes"}
    estimate=float(y.sum()/w.sum()); centered=y-estimate*w
    n=len(y); whole,tail=divmod(n,block); rng=np.random.default_rng(seed)
    noise=np.empty(draws)
    cy=np.r_[0.,np.cumsum(np.r_[centered,centered[:block]])]
    cw=np.r_[0.,np.cumsum(np.r_[w,w[:block]])]
    for offset in range(0,draws,256):
        count=min(256,draws-offset); s=rng.integers(0,n,size=(count,whole+(tail>0)))
        numerator=(cy[s[:,:whole]+block]-cy[s[:,:whole]]).sum(axis=1)
        denominator=(cw[s[:,:whole]+block]-cw[s[:,:whole]]).sum(axis=1)
        if tail:
            numerator += cy[s[:,-1]+tail]-cy[s[:,-1]]
            denominator += cw[s[:,-1]+tail]-cw[s[:,-1]]
        noise[offset:offset+count]=np.divide(numerator,denominator,out=np.full(count,np.nan),where=denominator>0)
    invalid=int((~np.isfinite(noise)).sum())
    if invalid:
        return {"status":"NOT_EVALUABLE","estimate":estimate,"invalid_draws":invalid,"draws":draws,"reason":"zero episode support in resampled calendar blocks"}
    def ci(tail):
        a,b=np.quantile(noise,[tail,1-tail]); return [float(estimate-b),float(estimate-a)]
    return {"status":"ESTIMATED","estimate":estimate,"threshold":delta,"n":n,"episodes":float(w.sum()),
            "block":block,"draws":draws,"seed":seed,"invalid_draws":0,
            "ci95_basic":ci(.025),"ci_simultaneous_basic":ci(.05/8),
            "p_one_sided":float((1+np.count_nonzero(noise >= estimate-delta))/(draws+1))}


def wilson(successes, n, z=1.959963984540054):
    if not 0 <= successes <= n or n <= 0:
        raise ContractError("nonvacuous binomial denominator required")
    p = successes/n; denominator = 1+z*z/n
    middle = (p+z*z/(2*n))/denominator
    half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return [float(middle-half), float(middle+half)]


def calibration_decision(null_successes, positive_successes, n):
    null_ci, power_ci = wilson(null_successes, n), wilson(positive_successes, n)
    passed = n >= 60 and null_ci[1] <= .08 and positive_successes/n >= .8
    return {"worlds": n, "null_rejections": null_successes, "null_wilson95": null_ci,
            "power_at_2delta": positive_successes/n, "power_wilson95": power_ci,
            "status": "PASS" if passed else "CALIBRATION_INCONCLUSIVE"}
