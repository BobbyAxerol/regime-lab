"""Guide 8.3 — group ablation and the position taken on the model ladder.

Two separate obligations live here.

**Group ablation.** Guide 8.3: "Group ablation cần chứng minh leverage/flow/market
features có contribution ngoài price/volatility." Adding feature blocks almost
always lowers a fit objective, so the question is not whether the objective drops
but whether it drops on data the fit did not see. The comparison therefore runs on
the same nested inner blocks that choose K, never on a holdout.

**The model ladder.** Guide 8.1 defines five rungs. LAB-05's task list asks for M0
and M1 only. Not building M1S, M2 and M3 is a defensible reading, but leaving that
undeclared is not -- a reader would have no way to tell a deliberate scope from an
oversight. The decision, and what would have to be true to revisit it, is recorded.
"""

from __future__ import annotations

import numpy as np

from .model_selection import score_k

#: Guide 8.1. ``implemented`` is a fact about this repository, not an opinion.
MODEL_LADDER = {
    "M0": {
        "model": "rule-based volatility/path-direction/activity",
        "role": "explainable control, thresholds train-only",
        "implemented": True, "module": "regime/m0_rules.py",
    },
    "M1": {
        "model": "regularized discrete statistical jump model",
        "role": "primary state model",
        "implemented": True, "module": "regime/jump_model.py",
    },
    "M1S": {
        "model": "sparse JM or group-regularized features",
        "role": "extension when there are MANY blocks; ablation against M1",
        "implemented": False,
        "why_not": (
            "the primary core is 8 features in 3 blocks (G1 3, G2 2, G5 3). Guide 8.1 scopes M1S "
            "to 'khi nhiều blocks', and 3 is not that. Guide 8.3 also forbids writing a naive "
            "sparse objective and requires a pinned research implementation or a verified "
            "constrained one; none is pinned in this environment, so writing one would be exactly "
            "the move 8.3 warns against."),
        "what_would_change_it": (
            "G3 (leverage) and G4 (liquidity) becoming available for all five symbols would take "
            "the core past 3 blocks. Then M1S needs a pinned implementation with its weight "
            "normalisation and penalty conventions recorded, plus the nondegeneracy guard that "
            "already exists in quality.check_degeneracy."),
    },
    "M2": {
        "model": "small HMM or GMM",
        "role": "comparator; guide 8.1 says do NOT sweep every model family",
        "implemented": False,
        "why_not": ("LAB-05's task list (L05.2) asks for M0 and M1 references. M2 is a comparator "
                    "the guide explicitly declines to make mandatory, and adding it would widen "
                    "the model family sweep 8.1 warns against."),
        "what_would_change_it": ("a claim that the state structure is specific to a jump model "
                                 "rather than to the features would need M2 to be falsifiable."),
    },
    "M3": {
        "model": "online novelty/change detector",
        "role": "diagnostic/secondary trigger, explicitly not wired in by default",
        "implemented": False,
        "why_not": ("guide 8.1 marks it 'chưa ghép default'. The novelty AXIS it would feed is "
                    "already measured -- fit residual against the training-residual quantile in "
                    "quality.assess -- without introducing a second detector whose disagreements "
                    "with M1 would then need their own policy."),
        "what_would_change_it": "a decision to use novelty as a trigger rather than as a status.",
    },
}


def ladder_record() -> dict:
    implemented = [k for k, v in MODEL_LADDER.items() if v["implemented"]]
    return {
        "schema": "crypto_regime_lab.model_ladder.v1",
        "rungs": MODEL_LADDER,
        "implemented": implemented,
        "not_implemented": [k for k, v in MODEL_LADDER.items() if not v["implemented"]],
        "scope_rule": ("LAB-05 L05.2 asks for M0 and M1 references. The other rungs are declared "
                       "unbuilt with a reason and a condition that would reopen them, so an "
                       "omission cannot be mistaken for an oversight (guide 8.1)"),
        "k_policy": "primary K=3; K=2 parsimonious; K=4 only on an explicit discovery decision",
    }


def group_weights(all_features: tuple[str, ...], weights: np.ndarray,
                  keep_groups: tuple[str, ...]) -> np.ndarray:
    """Zero the excluded blocks and renormalise so total weight stays 1.

    Renormalising matters: without it a smaller feature set simply has less total
    weight and a lower loss, and the ablation would measure the normalisation
    rather than the information.
    """
    weights = np.asarray(weights, dtype=np.float64)
    mask = np.asarray([f.split("_")[0].upper() in keep_groups for f in all_features])
    restricted = np.where(mask, weights, 0.0)
    total = restricted.sum()
    if total <= 0:
        raise ValueError(f"keeping {keep_groups} leaves no weight at all")
    return restricted / total


def variance_resolved(z_block: np.ndarray, centroids: np.ndarray, states: np.ndarray,
                      weights: np.ndarray) -> float:
    """Share of weighted variance the state assignment removes, on a held-out block.

    This exists because the fit objective is NOT comparable across feature sets: a
    different feature set is a different objective function, and a larger number
    could mean "worse states" or simply "noisier features". This measure is
    scale-free -- within-state weighted variance over total weighted variance,
    subtracted from one -- so the same number means the same thing whether the
    model reads 3 features or 8.
    """
    z_block = np.asarray(z_block, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    grand = np.average(z_block, axis=0, weights=None)
    total = float(np.sum(weights * np.mean((z_block - grand) ** 2, axis=0)))
    if total <= 0:
        return 0.0
    residual = z_block - np.asarray(centroids, dtype=np.float64)[states]
    within = float(np.sum(weights * np.mean(residual ** 2, axis=0)))
    return 1.0 - within / total


def group_ablation(z: np.ndarray, all_features: tuple[str, ...], weights: np.ndarray, *,
                   n_states: int, lambda_jump: float, seeds: tuple[int, ...],
                   ladder: tuple[tuple[str, ...], ...] = (("G1",), ("G1", "G2"),
                                                          ("G1", "G2", "G5")),
                   n_folds: int = 3) -> dict:
    """Does each added block buy anything on data the fit did not see?

    Scored on the held-out inner blocks, so a block that only helps in-sample --
    which every block does -- shows no gain here.
    """
    from .jump_model import forward_filter, loss_matrix, multi_start_fit
    from .model_selection import inner_splits

    rows = []
    previous_objective = None
    previous_resolved = None
    for keep in ladder:
        restricted = group_weights(all_features, weights, keep)
        score = score_k(z, restricted, n_states=n_states, lambda_jump=lambda_jump,
                        seeds=seeds, n_folds=n_folds)

        # the scale-free measure, on the same held-out inner blocks
        resolved = []
        for train_end, valid_start, valid_end in inner_splits(z.shape[0], n_folds):
            fit = multi_start_fit(z[:train_end], restricted, n_states=n_states,
                                  lambda_jump=lambda_jump, seeds=seeds)
            block = z[valid_start:valid_end]
            states = forward_filter(loss_matrix(block, fit["centroids"], restricted),
                                    lambda_jump).online_states
            resolved.append(variance_resolved(block, fit["centroids"], states, restricted))
        mean_resolved = float(np.mean(resolved))

        gain = (None if previous_objective is None
                else previous_objective - score["mean_per_observation_objective"])
        resolved_gain = (None if previous_resolved is None
                         else mean_resolved - previous_resolved)
        rows.append({
            "groups": list(keep),
            "features_active": int(np.count_nonzero(restricted)),
            "mean_per_observation_objective": score["mean_per_observation_objective"],
            "worst_fold": score["worst_fold"],
            "variance_resolved_out_of_fold": mean_resolved,
            "gain_over_previous": gain,
            "variance_resolved_gain": resolved_gain,
            "improved": None if resolved_gain is None else bool(resolved_gain > 0),
            "improved_on_objective": None if gain is None else bool(gain > 0),
        })
        previous_objective = score["mean_per_observation_objective"]
        previous_resolved = mean_resolved

    added = [r for r in rows if r["variance_resolved_gain"] is not None]
    return {
        "schema": "crypto_regime_lab.group_ablation.v1",
        "ladder": rows,
        "blocks_that_improved_out_of_fold": [r["groups"][-1] for r in added if r["improved"]],
        "blocks_that_did_not": [r["groups"][-1] for r in added if not r["improved"]],
        "scored_on": "held-out inner chronological blocks of the development window",
        "holdout_used": False,
        "weights_renormalised": True,
        "decided_on": "variance_resolved_out_of_fold",
        "why_not_the_objective": (
            "a different feature set is a DIFFERENT objective function, so its value is not "
            "comparable across rows -- a higher number can mean worse states or simply noisier "
            "features. variance_resolved is within-state over total weighted variance subtracted "
            "from one, which means the same thing at 3 features and at 8. The objective column is "
            "kept for reference and is not what the verdict rests on"),
        "requirement": ("guide 8.3: flow and market-coordination blocks must be shown to "
                        "contribute BEYOND price/volatility. A block that does not is reported as "
                        "not contributing, not quietly retained"),
        "interpretation_limit": ("this measures contribution to the FIT objective out of fold. It "
                                 "says nothing about whether the extra block improves a trading "
                                 "decision, which is a LAB-06+ question"),
    }
