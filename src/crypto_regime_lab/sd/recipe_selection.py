"""SD-02: choose one JM penalty recipe on the 12 validation folds (guide
SS5.8, SD02.7).

Primary selection criterion is mean validation R = D_B - D_C (guide's own
``sd.metrics.paired_reduction``, D_B/D_C = the Sharpe decay of each arm's
OWN selected candidate at a fold), MAXIMIZED among technically-valid designs
with >= MIN_PAIRED_FOLDS paired-valid folds. A design need NOT have R > 0 to
be selected -- the rule picks the LARGEST R among eligible designs
regardless of sign (guide: "Khong yeu cau R>0 de design duoc lua chon").
Ties within TIE_EPSILON Sharpe points break by larger c, then a
deterministic arm name -- never by peeking at final OOS.
"""
from __future__ import annotations

from .fold_scoring import ARM_B, jm_arm_name

TIE_EPSILON = 1e-6                          # guide SS5.8's own tie tolerance
MIN_PAIRED_FOLDS = 12                       # guide SS5.8/registration.json validation_folds_min
MEANINGFUL_R_SHARPE_POINTS = 0.2            # registration.json meaningful_decay_reduction_sharpe_points

DECISION_NO_VALID_DESIGN = "NO_VALID_JM_DESIGN"
DECISION_WEAK_EVIDENCE = "WEAK_DEVELOPMENT_EVIDENCE"
DECISION_RECIPE_SELECTED = "RECIPE_SELECTED"


class RecipeSelectionError(ValueError):
    """A recipe-selection step was internally inconsistent."""


def paired_r_per_fold(fold_records: list, *, jm_arm: str) -> list:
    """R = D_B - D_C for every fold where BOTH arms' selected-candidate
    decay is defined (guide: 'moi model comparison can cung 12 paired-valid
    validation folds'). A fold missing either side is excluded, never
    imputed."""
    out = []
    for fold in fold_records:
        d_b = fold["arms"][ARM_B].get("D_selected")
        d_c = fold["arms"][jm_arm].get("D_selected")
        if d_b is None or d_c is None:
            continue
        out.append({"origin_cutoff": fold["origin_cutoff"], "R": d_b - d_c})
    return out


def recipe_stats(fold_records: list, *, c: float) -> dict:
    arm = jm_arm_name(c)
    paired = paired_r_per_fold(fold_records, jm_arm=arm)
    n_paired = len(paired)
    mean_r = sum(p["R"] for p in paired) / n_paired if n_paired else None
    return {"c": c, "arm_name": arm, "n_paired_folds": n_paired, "mean_R": mean_r,
           "technically_valid": n_paired >= MIN_PAIRED_FOLDS, "paired": paired}


def select_recipe(fold_records: list, *, recipes: tuple = (0.5, 1.0, 2.0)) -> dict:
    """Guide SS5.8's locked rule. Returns every design's own stats table
    (including losing/negative ones, guide: 'giu ca bang ket qua cac designs
    thua/am') plus the decision."""
    candidates = [recipe_stats(fold_records, c=c) for c in recipes]
    eligible = [cand for cand in candidates if cand["technically_valid"]]
    if not eligible:
        return {"decision": DECISION_NO_VALID_DESIGN, "selected_c": None, "selected_arm": None,
               "mean_R": None, "tie_broken": False, "candidates": candidates}

    best_r = max(cand["mean_R"] for cand in eligible)
    tied = [cand for cand in eligible if abs(cand["mean_R"] - best_r) <= TIE_EPSILON]
    if len(tied) == 1:
        winner = tied[0]
    else:
        winner = sorted(tied, key=lambda cand: (-cand["c"], cand["arm_name"]))[0]

    decision = (DECISION_RECIPE_SELECTED if winner["mean_R"] >= MEANINGFUL_R_SHARPE_POINTS
               else DECISION_WEAK_EVIDENCE)
    return {"decision": decision, "selected_c": winner["c"], "selected_arm": winner["arm_name"],
           "mean_R": winner["mean_R"], "n_paired_folds": winner["n_paired_folds"],
           "tie_broken": len(tied) > 1, "candidates": candidates}
