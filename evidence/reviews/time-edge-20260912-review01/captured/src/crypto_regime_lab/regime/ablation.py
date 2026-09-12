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

import hashlib

import numpy as np

from .causality import apply_scaler, fit_scaler
from .jump_model import forward_filter, loss_matrix, multi_start_fit
from .model_selection import SCALER_MODE_INNER_TRAIN, inner_splits, score_k

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


# ---------------------------------------------------------------------------
# G10/A14 — fixed-target/cohort ablation (the P10 counterexample repair)
# ---------------------------------------------------------------------------

def _average_ranks(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.shape[0], dtype=np.float64)
    ranks[order] = np.arange(1, values.shape[0] + 1, dtype=np.float64)
    sorted_values = values[order]
    start = 0
    while start < values.shape[0]:
        end = start
        while end + 1 < values.shape[0] and sorted_values[end + 1] == sorted_values[start]:
            end += 1
        if end > start:
            ranks[order[start:end + 1]] = 0.5 * ((start + 1) + (end + 1))
        start = end + 1
    return ranks


def rank_ic(predicted: np.ndarray, realized: np.ndarray) -> dict:
    """Spearman rank correlation between a state profile and a FIXED target.

    This is an out-of-sample rank statistic, not a calibrated forecast: it says
    whether the state a feature set assigns orders the fixed paired target
    correctly. When either side is constant the statistic is undefined and is
    returned as ``null`` with a reason rather than as zero (T61).
    """
    predicted = np.asarray(predicted, dtype=np.float64)
    realized = np.asarray(realized, dtype=np.float64)
    if predicted.shape != realized.shape:
        raise ValueError("predicted and realized must have the same shape")
    finite = np.isfinite(predicted) & np.isfinite(realized)
    n = int(finite.sum())
    if n < 8:
        return {"rank_ic": None, "n": n, "reason": "fewer than 8 finite paired observations"}
    p = _average_ranks(predicted[finite])
    r = _average_ranks(realized[finite])
    p_centered, r_centered = p - p.mean(), r - r.mean()
    denom = float(np.sqrt(np.sum(p_centered ** 2) * np.sum(r_centered ** 2)))
    if denom <= 0:
        return {"rank_ic": None, "n": n, "reason": "predicted or realized is constant; undefined"}
    return {"rank_ic": float(np.sum(p_centered * r_centered) / denom), "n": n, "reason": None}


def _digest(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.round(np.asarray(values, dtype=np.float64), 12).tobytes()).hexdigest()[:16]


def fixed_target_ablation(raw: np.ndarray, all_features: tuple[str, ...],
                          weights: np.ndarray, *, target: np.ndarray, cohort: np.ndarray | None,
                          n_states: int, lambda_jump: float, seeds: tuple[int, ...],
                          ladder: tuple[tuple[str, ...], ...] = (("G1",), ("G1", "G2"),
                                                                 ("G1", "G2", "G5")),
                          n_folds: int = 3, min_train: int = 100,
                          purge_rows: int = 0,
                          target_name: str = "future_paired_utility",
                          target_kind: str = "paired") -> dict:
    """G10/A14 — every feature set scored against the SAME fixed target and cohort.

    The audited defect (P10): the ablation statistic was ``variance_resolved`` on
    the feature block itself, so each feature set had a DIFFERENT target --
    explaining G1 versus explaining G1 + G2. Adding a pure-noise dimension moved
    that statistic from 1.0 to 0.5 with the states and the economic target
    unchanged. This API holds ``target`` and ``cohort`` fixed, scores decision
    value out of fold as the rank IC of the state profile against that target, and
    reports reconstruction quality (``variance_resolved``) SEPARATELY as a
    diagnostic that is never the decision column.

    ``purge_rows`` drops the first rows of each validation block so a forward
    outcome window cannot overlap the fit boundary. The scaler is fitted on each
    fold's raw inner train only and applied frozen to validation (A14).
    """
    raw = np.asarray(raw, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if raw.ndim != 2:
        raise ValueError("raw must be (T, J)")
    if target.shape != (raw.shape[0],):
        raise ValueError("target must have one entry per observation")
    if cohort is None:
        cohort = np.ones(raw.shape[0], dtype=bool)
    cohort = np.asarray(cohort, dtype=bool)
    if cohort.shape != (raw.shape[0],):
        raise ValueError("cohort must have one entry per observation")
    folds = inner_splits(raw.shape[0], n_folds, min_train)
    target_digest = _digest(target)
    cohort_digest = _digest(cohort.astype(np.float64))

    rows = []
    previous_rank_ic = None
    previous_reconstruction = None
    for keep in ladder:
        restricted = group_weights(all_features, weights, keep)
        fold_rows = []
        rank_ics, reconstructions = [], []
        scored_total = 0
        for fold_index, (train_end, valid_start, valid_end) in enumerate(folds):
            scaler = fit_scaler(raw[:train_end])
            z_train = apply_scaler(raw[:train_end], scaler)
            fit = multi_start_fit(z_train, restricted, n_states=n_states,
                                  lambda_jump=lambda_jump, seeds=seeds)
            z_valid = apply_scaler(raw[valid_start:valid_end], scaler)
            loss = loss_matrix(z_valid, fit["centroids"], restricted)
            states = forward_filter(loss, lambda_jump).online_states

            train_loss = loss_matrix(z_train, fit["centroids"], restricted)
            train_states = forward_filter(train_loss, lambda_jump).online_states
            train_target = target[:train_end]
            train_cohort = cohort[:train_end] & np.isfinite(train_target)
            global_train_mean = (float(train_target[train_cohort].mean())
                                 if train_cohort.any() else None)
            state_profile = np.full(n_states, np.nan, dtype=np.float64)
            states_without_support = []
            for k in range(n_states):
                members = train_cohort & (train_states == k)
                if members.any():
                    state_profile[k] = float(train_target[members].mean())
                else:
                    states_without_support.append(int(k))
                    state_profile[k] = global_train_mean if global_train_mean is not None else np.nan

            first_scored = int(valid_start + max(0, purge_rows))
            valid_target = target[first_scored:valid_end]
            valid_cohort = cohort[first_scored:valid_end] & np.isfinite(valid_target)
            valid_states = states[first_scored - valid_start:]
            predicted = state_profile[valid_states]
            predicted[~valid_cohort] = np.nan
            realized = valid_target.copy()
            realized[~valid_cohort] = np.nan
            ic = rank_ic(predicted, realized)

            reconstruction = variance_resolved(
                z_valid[first_scored - valid_start:], fit["centroids"],
                valid_states, restricted)
            rank_ics.append(ic["rank_ic"])
            reconstructions.append(reconstruction)
            scored_total += ic["n"]
            fold_rows.append({
                "fold": fold_index,
                "train_end": int(train_end), "valid_start": int(valid_start),
                "valid_end": int(valid_end), "purge_rows": int(purge_rows),
                "scored_rows": int(ic["n"]),
                "rank_ic": ic["rank_ic"], "rank_ic_undefined_reason": ic["reason"],
                "scaler": {"mode": SCALER_MODE_INNER_TRAIN, "fitted_rows": int(train_end),
                           "applied_frozen_to": [int(valid_start), int(valid_end)]},
                "states_without_train_target_support": states_without_support,
                "global_train_target_mean": global_train_mean,
            })
        finite_ics = [v for v in rank_ics if v is not None]
        mean_rank_ic = float(np.mean(finite_ics)) if finite_ics else None
        finite_reconstruction = [v for v in reconstructions if v is not None]
        mean_reconstruction = (float(np.mean(finite_reconstruction))
                               if finite_reconstruction else None)
        incremental = (None if mean_rank_ic is None or previous_rank_ic is None
                       else float(mean_rank_ic - previous_rank_ic))
        incremental_reconstruction = (
            None if mean_reconstruction is None or previous_reconstruction is None
            else float(mean_reconstruction - previous_reconstruction))
        rows.append({
            "groups": list(keep),
            "features_active": int(np.count_nonzero(restricted)),
            "fixed_target": target_name,
            "fixed_target_digest": target_digest,
            "cohort_digest": cohort_digest,
            "decision_value_basis": "fixed_target_rank_ic",
            "fixed_target_rank_ic_mean": mean_rank_ic,
            "fixed_target_rank_ic_folds": rank_ics,
            "scored_rows": int(scored_total),
            "folds_scored": int(len(folds)),
            "incremental_decision_value": incremental,
            "reconstruction_quality": mean_reconstruction,
            "incremental_reconstruction_quality": incremental_reconstruction,
            "reconstruction_quality_used_for_decision": False,
            "folds": fold_rows,
        })
        previous_rank_ic = mean_rank_ic
        previous_reconstruction = mean_reconstruction

    added = [r for r in rows if r["incremental_decision_value"] is not None]
    return {
        "schema": "crypto_regime_lab.fixed_target_ablation.v1",
        "ladder": rows,
        "target_name": target_name,
        "target_kind": target_kind,
        "decided_on": "fixed_target_rank_ic",
        "reconstruction_quality_role": "diagnostic_only",
        "target_fixed_across_sets": True,
        "cohort_fixed_across_sets": True,
        "target_digest": target_digest,
        "cohort_digest": cohort_digest,
        "reconstruction_quality_used_for_decision": False,
        "blocks_with_positive_incremental_decision_value": [
            r["groups"][-1] for r in added if r["incremental_decision_value"] > 0],
        "blocks_with_nonpositive_incremental_decision_value": [
            r["groups"][-1] for r in added if r["incremental_decision_value"] <= 0],
        "p10_counterexample_guard": {
            "old_statistic": ("variance_resolved over the concatenated feature block, so each "
                              "feature set explained ITS OWN target"),
            "old_failure": ("adding a noise dimension moved variance_resolved 1.0 -> 0.5 with the "
                            "states and the economic target unchanged (P10)"),
            "repair": ("every feature set is scored against the same target array and the same "
                       "cohort; the target and cohort digests are recorded on every row"),
            "decision_column": "fixed_target_rank_ic",
            "reconstruction_column_used_for_decision": False,
        },
        "scored_on": "held-out INNER chronological blocks of the development window",
        "holdout_used": False,
        "outcome_used": True,
        "outcome_note": ("the fixed target IS an outcome. It is used only to score held-out "
                         "validation blocks, never to fit the model or the scaler, and the same "
                         "array is used for every feature set"),
        "inner_scaler_rule": ("per fold: fit_scaler(raw[:train_end]); the frozen scaler is applied "
                              "to raw[train_end:valid_end]. No validation observation enters the "
                              "scale (A14)"),
        "purge_rows": int(purge_rows),
        "denominators": {
            "feature_sets": len(rows),
            "folds_per_set": {str(r["groups"]): r["folds_scored"] for r in rows},
            "scored_rows_per_set": {str(r["groups"]): r["scored_rows"] for r in rows},
        },
    }
