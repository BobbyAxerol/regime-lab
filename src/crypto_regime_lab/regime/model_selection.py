"""L05.4 — choosing K and the regularization, without looking at a holdout.

Guide 8.1/L05.4: K=3 is the registered starting point, K=2 is the parsimonious
alternative, and K=4 opens only on an explicit discovery decision. The forbidden
method is named outright: "Không optimize K bằng việc nhìn colored regime chart
trên holdout."

So the criterion here is a NESTED chronological validation inside the development
window. The function has no argument through which a holdout or an outcome could
reach it, which is a stronger guarantee than a promise not to look.
"""

from __future__ import annotations

import numpy as np

from .jump_model import forward_filter, loss_matrix, multi_start_fit, path_objective

#: Registered before any fit (guide 8.1).
STARTING_K = 3
PARSIMONIOUS_K = 2
EXPANSION_K = 4
K_POLICY = {
    STARTING_K: "primary starting point",
    PARSIMONIOUS_K: "registered parsimonious alternative",
    EXPANSION_K: "opens ONLY on an explicit discovery decision with recorded decision value",
}


def inner_splits(n_obs: int, n_folds: int = 3, min_train: int = 100) -> list[tuple[int, int, int]]:
    """Chronological expanding inner folds: (train_end, valid_start, valid_end).

    Expanding rather than shuffled, because a regime model is a time-series model
    and a shuffled split would let it validate on data interleaved with its own
    training rows.
    """
    if n_obs < min_train + n_folds:
        raise ValueError(f"{n_obs} observations cannot support {n_folds} inner folds")
    block = (n_obs - min_train) // n_folds
    if block < 10:
        raise ValueError("inner validation blocks would be too short to score")
    out = []
    for i in range(n_folds):
        train_end = min_train + i * block
        valid_end = min(train_end + block, n_obs)
        if valid_end - train_end < 10:
            break
        out.append((train_end, train_end, valid_end))
    return out


def score_k(z: np.ndarray, weights: np.ndarray, *, n_states: int, lambda_jump: float,
            seeds: tuple[int, ...], n_folds: int = 3) -> dict:
    """Mean per-observation objective on held-out INNER blocks.

    Per-observation, because blocks differ in length and a raw sum would reward
    whichever K happened to be scored on the shorter block.
    """
    z = np.asarray(z, dtype=np.float64)
    scores, fold_rows = [], []
    for train_end, valid_start, valid_end in inner_splits(z.shape[0], n_folds):
        fit = multi_start_fit(z[:train_end], weights, n_states=n_states,
                              lambda_jump=lambda_jump, seeds=seeds)
        block = z[valid_start:valid_end]
        loss = loss_matrix(block, fit["centroids"], weights)
        states = forward_filter(loss, lambda_jump).online_states
        per_obs = path_objective(loss, states, lambda_jump) / max(1, block.shape[0])
        scores.append(per_obs)
        fold_rows.append({
            "train_end": int(train_end), "valid_start": int(valid_start),
            "valid_end": int(valid_end), "per_observation_objective": float(per_obs),
            "selected_seed": fit["selected_seed"],
            "empty_states_in_fit": fit["runs"][0]["empty_states"],
        })
    return {
        "n_states": int(n_states),
        "mean_per_observation_objective": float(np.mean(scores)),
        "worst_fold": float(max(scores)),
        "folds": fold_rows,
        "scored_on": "held-out INNER chronological blocks of the development window",
        "holdout_used": False,
        "outcome_used": False,
    }


def choose_k(z: np.ndarray, weights: np.ndarray, *, lambda_jump: float,
             seeds: tuple[int, ...] = (1, 2, 3), candidates=(PARSIMONIOUS_K, STARTING_K),
             n_folds: int = 3, expansion_decision: dict | None = None) -> dict:
    """Compare K on the inner criterion. K=4 requires an explicit recorded decision.

    A lower objective at a higher K is expected -- more states fit better almost by
    construction -- so the comparison alone never opens K=4. That needs a decision
    that says what DECISION VALUE the extra split buys, recorded before it is used.
    """
    considered = list(candidates)
    if EXPANSION_K in considered and not (expansion_decision or {}).get("approved"):
        considered = [k for k in considered if k != EXPANSION_K]

    results = {k: score_k(z, weights, n_states=k, lambda_jump=lambda_jump, seeds=seeds,
                          n_folds=n_folds) for k in considered}
    best = min(results, key=lambda k: (results[k]["mean_per_observation_objective"], k))
    return {
        "schema": "crypto_regime_lab.k_selection.v1",
        "registered_starting_k": STARTING_K,
        "k_policy": {str(k): v for k, v in K_POLICY.items()},
        "candidates_considered": considered,
        "expansion_k_requested": EXPANSION_K in candidates,
        "expansion_k_admitted": EXPANSION_K in considered,
        "expansion_decision": expansion_decision,
        "scores": {str(k): v for k, v in results.items()},
        "best_by_inner_criterion": int(best),
        "selection_rule": ("mean per-observation objective on held-out inner chronological blocks; "
                           "ties break to the SMALLER K"),
        "chart_inspection_used": False,
        "method_note": ("a lower objective at higher K is close to automatic, so this comparison "
                        "never by itself justifies opening K=4. That needs a recorded discovery "
                        "decision naming the decision value the extra state buys (guide 8.1)"),
    }


def lambda_jump_units(lambda_jump: float, observation_interval: str) -> dict:
    """Guide 8.2 — lambda_J has units tied to the standardized loss AND the sampling rate.

    Reusing the same raw penalty at a different frequency and then declaring one
    model better is comparing two different objectives.
    """
    return {
        "lambda_jump": float(lambda_jump),
        "observation_interval": observation_interval,
        "units": "standardized-loss units per switch, at this sampling frequency",
        "transferable_across_frequencies": False,
        "rule": ("changing 4h to 1h requires retuning lambda_J in train/validation, or freezing a "
                 "normalized policy. Carrying the same raw penalty across and comparing is not a "
                 "model comparison (guide 8.2)"),
    }
