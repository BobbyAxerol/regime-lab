"""SD-02: three-layer model quality diagnostics (guide SS5.1, SS9.2 SD02.5).

Technical validity is checked structurally elsewhere (jm_model's own
prefix-parity guarantee, model_bc's support floors). This module covers the
DESCRIPTIVE layer (state occupancy/dwell/recurrence) and part of the TASK
layer (MAE(Y), a rank diagnostic) -- never conflated with economic
usefulness (guide SS5.1: 'khong tu la economic usefulness').
"""
from __future__ import annotations

import math


class ModelQualityError(ValueError):
    """A model-quality diagnostic could not be computed from its input."""


def mae_y_one_origin(scored_rows: list, true_y_by_candidate: dict, *, anchor_id: str = None) -> dict:
    """Mean |Y_hat - Y_true| over ONE origin's own scored candidates.
    ``anchor_id``, when given, excludes the anchor row -- its Y_hat/Y_true
    are both trivially 0 by construction and would silently deflate the
    MAE if pooled in. Candidates with an undefined true label are
    excluded, never imputed."""
    errors = []
    for row in scored_rows:
        if anchor_id is not None and row["candidate_id"] == anchor_id:
            continue
        true_y = true_y_by_candidate.get(row["candidate_id"])
        if true_y is None:
            continue
        errors.append(abs(row["y_hat"] - true_y))
    if not errors:
        return {"mae": None, "n": 0, "status": "NO_LABELED_CANDIDATES"}
    return {"mae": sum(errors) / len(errors), "n": len(errors), "status": "OK"}


def mean_mae_y(per_origin_maes: list) -> dict:
    """Study-level MAE(Y): the UNWEIGHTED mean of each origin's OWN MAE
    (guide: 'MAE(Y) tinh mean per-origin') -- never a pooled mean over all
    rows (which would let large-panel origins dominate)."""
    valid = [m for m in per_origin_maes if m is not None]
    if not valid:
        return {"mean_mae": None, "n_origins": 0, "status": "NO_VALID_ORIGINS"}
    return {"mean_mae": sum(valid) / len(valid), "n_origins": len(valid), "status": "OK"}


def rank_diagnostic_one_origin(scored_rows: list, true_y_by_candidate: dict) -> dict:
    """Spearman rank correlation between predicted Y_hat and true Y within
    one origin's own candidates. Returns NO_VARIATION (never a fabricated
    correlation) when the true labels don't vary -- a correlation is
    undefined on a constant series."""
    pairs = [(row["y_hat"], true_y_by_candidate[row["candidate_id"]]) for row in scored_rows
            if row["candidate_id"] in true_y_by_candidate]
    if len(pairs) < 3:
        return {"rho": None, "n": len(pairs), "status": "TOO_FEW_CANDIDATES"}
    true_values = [p[1] for p in pairs]
    if len(set(true_values)) < 2:
        return {"rho": None, "n": len(pairs), "status": "NO_VARIATION"}

    def _ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks

    r_pred, r_true = _ranks([p[0] for p in pairs]), _ranks(true_values)
    n = len(pairs)
    mean_p, mean_t = sum(r_pred) / n, sum(r_true) / n
    cov = sum((a - mean_p) * (b - mean_t) for a, b in zip(r_pred, r_true))
    var_p = sum((a - mean_p) ** 2 for a in r_pred)
    var_t = sum((b - mean_t) ** 2 for b in r_true)
    if var_p <= 0 or var_t <= 0:
        return {"rho": None, "n": n, "status": "NO_VARIATION"}
    return {"rho": cov / math.sqrt(var_p * var_t), "n": n, "status": "OK"}


def state_occupancy(states_in_order: list) -> dict:
    """Occupancy (count per state, None/unknown excluded), dwell (mean
    consecutive-run length per state), recurrence (number of distinct runs
    -- i.e. how many separate TIMES a state was visited, not how many bars
    it covered, guide SS5.6: 'report number of separated state visits')."""
    known = [s for s in states_in_order if s is not None]
    occupancy: dict = {}
    for s in known:
        occupancy[s] = occupancy.get(s, 0) + 1
    runs: list = []
    for s in states_in_order:
        if s is None:
            # an unknown observation is a genuine gap, not evidence the
            # surrounding same-state bars form one continuous visit --
            # it breaks the run rather than being silently skipped through.
            runs.append(None)
            continue
        if runs and runs[-1] is not None and runs[-1]["state"] == s:
            runs[-1]["length"] += 1
        else:
            runs.append({"state": s, "length": 1})
    recurrence: dict = {}
    dwell_sum: dict = {}
    for run in runs:
        if run is None:
            continue
        recurrence[run["state"]] = recurrence.get(run["state"], 0) + 1
        dwell_sum[run["state"]] = dwell_sum.get(run["state"], 0) + run["length"]
    dwell = {s: dwell_sum[s] / recurrence[s] for s in recurrence}
    return {"occupancy": occupancy, "recurrence_count": recurrence, "mean_dwell_bars": dwell,
           "n_known": len(known), "n_unknown": len(states_in_order) - len(known)}
