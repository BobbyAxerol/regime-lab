"""FP-08 statistical analysis (guide FP08.3 / 10.6 / 10.7): B-A/C-B utility
and decay, the primary regime comparison I_D, and the registered-threshold
discipline guide 10.7 requires (delta_decay/epsilon_OOS_noninferiority are
NOT registered anywhere in this lab -- guide 10.7's own explicit fallback
applies: report DESCRIPTIVE for those specific claims, never invent a
threshold to open a positive one. delta_economic_return IS registered
(configs/minimum_economic_effect.json, 6.4e-05/day) and is reused verbatim,
the same value every FP-0N phase already uses).

Engine calls for this module: zero, always (guide FP08.3's own requirement)
-- every function here operates on already-computed D1/D2/paired-contrast
artifacts, never re-runs anything.
"""
from __future__ import annotations

DELTA_ECONOMIC_RETURN = 6.4e-05
DELTA_ECONOMIC_RETURN_SOURCE = "configs/minimum_economic_effect.json:minimum_daily_net_return_difference"
DELTA_DECAY_STATUS = "NOT_REGISTERED"
EPSILON_OOS_NONINFERIORITY_STATUS = "NOT_REGISTERED"
THRESHOLD_FALLBACK_REASON = (
    "guide 10.7: 'Neu business hurdle chua co, dung rule calibration da duoc owner chap nhan; neu "
    "chua materialize duoc thi report descriptive, khong tu dat zero de mo positive claim' -- no "
    "owner-accepted delta_decay or epsilon_OOS_noninferiority exists in this lab's registry, so "
    "claims that would need them stay DESCRIPTIVE rather than being judged against an invented "
    "number")


def positive_decay(d_value: float | None) -> float | None:
    """guide 10.6's D_+ : the positive part of a decay value (worse-than-IS
    decay only; a NEGATIVE D -- forward beat IS -- contributes zero, never
    a negative offset)."""
    if d_value is None:
        return None
    return max(d_value, 0.0)


def primary_regime_comparison(d1_rows_b: list[dict], d1_rows_c: list[dict]) -> dict:
    """guide 10.6: I_D = mean_j(D+_B,j - D+_C,j) at COMMON origins (both B
    and C carry a real, non-null D1 value for that origin). I_D > 0 means C
    reduces positive decay relative to B. NOT_EVALUABLE with a reason when
    there are no common origins (e.g. cell 1's own C==B degeneracy makes
    this trivially zero by construction, disclosed as such rather than
    silently computed and presented as a real comparison)."""
    b_by_origin = {r["origin_cutoff"]: r for r in d1_rows_b}
    c_by_origin = {r["origin_cutoff"]: r for r in d1_rows_c}
    common = sorted(set(b_by_origin) & set(c_by_origin))
    per_origin, evaluable = [], []
    for origin in common:
        b_row, c_row = b_by_origin[origin], c_by_origin[origin]
        b_plus = positive_decay(b_row.get("D_mean_daily_return"))
        c_plus = positive_decay(c_row.get("D_mean_daily_return"))
        row = {"origin_cutoff": origin, "D_plus_B": b_plus, "D_plus_C": c_plus,
              "diff": None if b_plus is None or c_plus is None else b_plus - c_plus}
        per_origin.append(row)
        if row["diff"] is not None:
            evaluable.append(row["diff"])
    degenerate = bool(common) and all(
        b_by_origin[o].get("D_mean_daily_return") == c_by_origin[o].get("D_mean_daily_return")
        for o in common if b_by_origin[o].get("D_mean_daily_return") is not None)
    if not evaluable:
        return {"schema": "regime_lab.fp08_primary_regime_comparison.v1", "status": "NOT_EVALUABLE",
               "reason": "no common origin carries a non-null D1 value for both B and C",
               "per_origin": per_origin, "degenerate": degenerate}
    i_d = sum(evaluable) / len(evaluable)
    return {"schema": "regime_lab.fp08_primary_regime_comparison.v1", "status": "DESCRIPTIVE",
           "I_D": i_d, "n_common_origins_evaluable": len(evaluable), "per_origin": per_origin,
           "degenerate": degenerate,
           "degenerate_reason": ("B and C carry IDENTICAL D1 at every common origin -- I_D is 0 by "
                                 "construction, not a measured decay-reduction effect")
           if degenerate else None,
           "threshold_status": DELTA_DECAY_STATUS, "threshold_reason": THRESHOLD_FALLBACK_REASON,
           "interpretation": "I_D > 0 means C reduces positive decay relative to B -- reported "
                             "descriptively; no registered delta_decay exists to judge significance "
                             "against (guide 10.7)"}


def economic_outperformance_check(contrast: dict) -> dict:
    """guide 10.6's 'Economic outperformance' row: uses the ALREADY
    registered delta_economic_return (6.4e-05/day, reused verbatim from
    every other FP-0N phase) -- the one threshold in this table that DOES
    exist. Reports whether the contrast's own CI clears it, without
    applying a stronger label than the evidence (no Holm/family adjustment
    here -- that is FP-08's own family-level responsibility, applied
    separately over the full registered contrast family)."""
    if contrast.get("status") != "ESTIMATED":
        return {"status": contrast.get("status", "NOT_EVALUABLE"),
               "reason": contrast.get("reason", "contrast not ESTIMATED"),
               "delta_economic_return": DELTA_ECONOMIC_RETURN}
    ci = contrast.get("ci95_basic")
    lower = ci[0] if ci else None
    clears = lower is not None and lower > DELTA_ECONOMIC_RETURN
    return {"status": "ESTIMATED", "delta_economic_return": DELTA_ECONOMIC_RETURN,
           "delta_economic_return_source": DELTA_ECONOMIC_RETURN_SOURCE,
           "ci95_lower_clears_threshold": clears,
           "estimate": contrast.get("estimate"), "ci95_basic": ci}
