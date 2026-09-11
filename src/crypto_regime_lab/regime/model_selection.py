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

from dataclasses import dataclass

import numpy as np

from .causality import apply_scaler, fit_scaler
from .jump_model import (centroid_digest, forward_filter, loss_matrix, multi_start_fit,
                         path_objective)
from .m0_rules import fit_thresholds, label as m0_label

#: Registered before any fit (guide 8.1).
STARTING_K = 3
PARSIMONIOUS_K = 2
EXPANSION_K = 4
K_POLICY = {
    STARTING_K: "primary starting point",
    PARSIMONIOUS_K: "registered parsimonious alternative",
    EXPANSION_K: "opens ONLY on an explicit discovery decision with recorded decision value",
}

#: RF03.2/G10 — a SMALL registered ladder, not a model sweep. The values bracket the
#: registered starting point on the loss scale: lambda is a per-switch penalty in the
#: same units as the per-observation weighted squared loss, so 0.5x/1x/2x are the
#: natural "a few choices with rationale" (guide 8.2 units; guide 8.1 forbids a
#: family sweep).
LAMBDA_CANDIDATES = (0.5, 1.0, 2.0)
N_STATE_CANDIDATES = (PARSIMONIOUS_K, STARTING_K)

#: Cadence is registered as a menu; crossing every K x lambda x cadence is exactly
#: the full-combination sweep RF03.2 forbids by default. The deployed/selected
#: comparison runs at the primary observation interval; an alternate cadence is only
#: scored when it is passed explicitly, and lambda is NOT carried across cadences
#: (lambda_jump_units: not transferable).
CADENCE_CANDIDATES = (
    ("4h", 1, "registered primary observation interval"),
    ("8h", 2, "one bar of the primary panel is dropped; only valid with lambda retuned"),
    ("1d", 6, "six primary bars per observation; only valid with lambda retuned"),
)
PRIMARY_CADENCE = "4h"

#: Scaler fitting rules. ``inner_train`` is the repaired rule (A14): for each inner
#: fold the scaler sees raw[:train_end] only and is applied frozen to the validation
#: block. ``whole_calibration`` is the audited leak, kept ONLY as a deliberately-wrong
#: control so the manifest can demonstrate that the check can go red.
SCALER_MODE_INNER_TRAIN = "inner_train_only"
SCALER_MODE_WHOLE_CALIBRATION = "whole_calibration_leaky_control"
M0_MODEL = "M0"
JM_MODEL = "JM"


@dataclass(frozen=True)
class LadderCandidate:
    """One rung of the registered development ladder. Mutable state is absent on purpose."""

    model: str
    n_states: int
    lambda_jump: float | None
    cadence: str = PRIMARY_CADENCE
    observation_stride: int = 1

    def as_record(self) -> dict:
        return {"model": self.model, "n_states": int(self.n_states),
                "lambda_jump": None if self.lambda_jump is None else float(self.lambda_jump),
                "cadence": self.cadence, "observation_stride": int(self.observation_stride)}


def registered_ladder() -> tuple[LadderCandidate, ...]:
    """M0 + JM K2/K3 at the registered lambda candidates, primary cadence."""
    rungs = [LadderCandidate(M0_MODEL, STARTING_K, None)]
    for k in N_STATE_CANDIDATES:
        for lambda_jump in LAMBDA_CANDIDATES:
            rungs.append(LadderCandidate(JM_MODEL, k, lambda_jump))
    return tuple(rungs)


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


# ---------------------------------------------------------------------------
# G10/A14 — inner-train-only scaler rule and the causal design ladder
# ---------------------------------------------------------------------------

def _scaler_digest(scaler: dict) -> str:
    return centroid_digest(np.vstack([np.asarray(scaler["median"], dtype=np.float64),
                                      np.asarray(scaler["scale"], dtype=np.float64)]))


def _scalers_identical(left: dict, right: dict) -> bool:
    return (np.array_equal(np.asarray(left["median"]), np.asarray(right["median"]))
            and np.array_equal(np.asarray(left["scale"]), np.asarray(right["scale"])))


def fit_inner_fold_scalers(raw: np.ndarray, folds: list[tuple[int, int, int]], *,
                           mode: str = SCALER_MODE_INNER_TRAIN) -> list[dict]:
    """Fit each inner fold's scaler under the declared rule.

    ``inner_train``: fold i's scaler sees ``raw[:train_end]`` only. This is the A14
    repair. ``whole_calibration``: sees ``raw[:valid_end]``, i.e. the inner
    validation block leaks into the scale -- kept ONLY as a deliberately-wrong
    control, exactly like ``causality.leaky_fit_for_control``.
    """
    raw = np.asarray(raw, dtype=np.float64)
    if mode not in (SCALER_MODE_INNER_TRAIN, SCALER_MODE_WHOLE_CALIBRATION):
        raise ValueError(f"unknown scaler mode {mode!r}")
    records = []
    for train_end, valid_start, valid_end in folds:
        end = int(train_end) if mode == SCALER_MODE_INNER_TRAIN else int(valid_end)
        scaler = fit_scaler(raw[:end])
        records.append({
            "train_end": int(train_end), "valid_start": int(valid_start),
            "valid_end": int(valid_end), "rows_read_by_scaler": end,
            "fitted_rows": int(scaler["fitted_rows"]),
            "scaler_digest": _scaler_digest(scaler),
            "mode": mode,
        })
    return records


def inner_scaler_mutation_probe(raw: np.ndarray, folds: list[tuple[int, int, int]], *,
                                seed: int = 99, shift: float = 11.0,
                                scale: float = 7.0) -> dict:
    """The A14 red probe: mutate the inner-validation suffix FOLD BY FOLD.

    For each fold the scaler must not move: it declared it read only that fold's
    inner train. The deliberately-wrong whole-calibration scaler MUST move on at
    least one fold, or this check could never fire and would prove nothing.
    """
    raw = np.asarray(raw, dtype=np.float64)
    inner_rows, leaky_rows = [], []
    for train_end, valid_start, valid_end in folds:
        if valid_end <= valid_start:
            continue
        mutated = raw.copy()
        rng = np.random.default_rng(seed + int(train_end))
        mutated[valid_start:] = rng.normal(shift, scale,
                                           size=(raw.shape[0] - valid_start, raw.shape[1]))
        mutation_effective = not bool(np.array_equal(raw[valid_start:], mutated[valid_start:]))
        prefix_untouched = bool(np.array_equal(raw[:train_end], mutated[:train_end]))
        inner_before = fit_scaler(raw[:train_end])
        inner_after = fit_scaler(mutated[:train_end])
        leaky_before = fit_scaler(raw[:valid_end])
        leaky_after = fit_scaler(mutated[:valid_end])
        inner_rows.append({
            "train_end": int(train_end), "valid_start": int(valid_start),
            "valid_end": int(valid_end), "mutation_effective": mutation_effective,
            "training_prefix_untouched": prefix_untouched,
            "scaler_unchanged": _scalers_identical(inner_before, inner_after),
            "digest_before": _scaler_digest(inner_before),
            "digest_after": _scaler_digest(inner_after),
        })
        leaky_rows.append({
            "train_end": int(train_end), "valid_end": int(valid_end),
            "scaler_changed": not _scalers_identical(leaky_before, leaky_after),
            "digest_before": _scaler_digest(leaky_before),
            "digest_after": _scaler_digest(leaky_after),
        })
    inner_ok = bool(inner_rows) and all(r["scaler_unchanged"] for r in inner_rows)
    leaky_moves = any(r["scaler_changed"] for r in leaky_rows)
    effective = bool(inner_rows) and all(r["mutation_effective"] and r["training_prefix_untouched"]
                                         for r in inner_rows)
    return {
        "schema": "crypto_regime_lab.inner_scaler_mutation_probe.v1",
        "inner_train": {"mode": SCALER_MODE_INNER_TRAIN, "folds": inner_rows,
                        "all_folds_unchanged": inner_ok,
                        "denominator_folds": len(inner_rows)},
        "whole_calibration_control": {"mode": SCALER_MODE_WHOLE_CALIBRATION, "folds": leaky_rows,
                                      "any_fold_changed": leaky_moves,
                                      "denominator_folds": len(leaky_rows)},
        "mutation_effective": effective,
        "detector_is_meaningful": bool(effective and inner_ok and leaky_moves),
        "rule": ("a scaler that declared it read only the inner train must be bit-identical when "
                 "everything after that train is replaced. The leaky control is required to move, "
                 "otherwise 'unchanged' is vacuous (A14/T39)"),
    }


def _score_jm_candidate(raw: np.ndarray, weights: np.ndarray, *, n_states: int,
                        lambda_jump: float, seeds: tuple[int, ...],
                        folds: list[tuple[int, int, int]],
                        scaler_mode: str = SCALER_MODE_INNER_TRAIN) -> dict:
    raw = np.asarray(raw, dtype=np.float64)
    fold_rows, scores = [], []
    for train_end, valid_start, valid_end in folds:
        scaler_end = int(train_end) if scaler_mode == SCALER_MODE_INNER_TRAIN else int(valid_end)
        scaler = fit_scaler(raw[:scaler_end])
        z_train = apply_scaler(raw[:train_end], scaler)
        fit = multi_start_fit(z_train, weights, n_states=n_states, lambda_jump=lambda_jump,
                              seeds=seeds)
        z_valid = apply_scaler(raw[valid_start:valid_end], scaler)
        loss = loss_matrix(z_valid, fit["centroids"], weights)
        states = forward_filter(loss, lambda_jump).online_states
        per_obs = path_objective(loss, states, lambda_jump) / max(1, z_valid.shape[0])
        scores.append(per_obs)
        fold_rows.append({
            "train_end": int(train_end), "valid_start": int(valid_start),
            "valid_end": int(valid_end), "observations_scored": int(z_valid.shape[0]),
            "per_observation_objective": float(per_obs),
            "selected_seed": fit["selected_seed"],
            "empty_states_in_fit": fit["runs"][0]["empty_states"],
            "validation_switches": int(np.count_nonzero(states[1:] != states[:-1])),
            "scaler": {"mode": scaler_mode, "rows_read_by_scaler": scaler_end,
                       "fitted_rows": int(scaler["fitted_rows"]),
                       "digest": _scaler_digest(scaler)},
        })
    return {
        "model": JM_MODEL, "n_states": int(n_states), "lambda_jump": float(lambda_jump),
        "mean_per_observation_objective": float(np.mean(scores)) if scores else None,
        "worst_fold": float(max(scores)) if scores else None,
        "folds": fold_rows,
        "observations_scored": int(sum(r["observations_scored"] for r in fold_rows)),
        "scored_on": "held-out INNER chronological blocks of the development window",
        "holdout_used": False,
        "outcome_used": False,
        "scaler_rule": scaler_mode,
    }


def _score_m0_candidate(raw: np.ndarray, weights: np.ndarray, *,
                        folds: list[tuple[int, int, int]], n_states: int = STARTING_K,
                        m0_feature_index: int = 0) -> dict:
    """M0 control scored on the same held-out blocks.

    M0 is an explainable comparator, not a competitor: it has no jump penalty and
    it labels from a frozen train quantile rule. It is reported so the ladder
    cannot hide a control that would have been better, and the selection rule
    never picks it over a JM rung.
    """
    raw = np.asarray(raw, dtype=np.float64)
    fold_rows, scores = [], []
    for train_end, valid_start, valid_end in folds:
        scaler = fit_scaler(raw[:train_end])
        z_train = apply_scaler(raw[:train_end], scaler)
        thresholds = fit_thresholds(raw[:train_end, m0_feature_index])
        train_states = m0_label(raw[:train_end, m0_feature_index], thresholds)
        centroids = np.empty((n_states, raw.shape[1]), dtype=np.float64)
        fallback = z_train.mean(axis=0)
        for k in range(n_states):
            members = z_train[train_states == k]
            centroids[k] = members.mean(axis=0) if members.size else fallback
        z_valid = apply_scaler(raw[valid_start:valid_end], scaler)
        loss = loss_matrix(z_valid, centroids, weights)
        states = np.argmin(loss, axis=1).astype(np.int64)
        per_obs = float(loss[np.arange(loss.shape[0]), states].mean())
        scores.append(per_obs)
        fold_rows.append({
            "train_end": int(train_end), "valid_start": int(valid_start),
            "valid_end": int(valid_end), "observations_scored": int(z_valid.shape[0]),
            "per_observation_objective": per_obs,
            "validation_switches": int(np.count_nonzero(states[1:] != states[:-1])),
            "thresholds": thresholds,
            "empty_states_in_fit": [int(k) for k in range(n_states)
                                    if not np.any(train_states == k)],
            "scaler": {"mode": SCALER_MODE_INNER_TRAIN, "rows_read_by_scaler": int(train_end),
                       "fitted_rows": int(scaler["fitted_rows"]),
                       "digest": _scaler_digest(scaler)},
        })
    return {
        "model": M0_MODEL, "n_states": int(n_states), "lambda_jump": None,
        "mean_per_observation_objective": float(np.mean(scores)) if scores else None,
        "worst_fold": float(max(scores)) if scores else None,
        "folds": fold_rows,
        "observations_scored": int(sum(r["observations_scored"] for r in fold_rows)),
        "scored_on": "held-out INNER chronological blocks, M0 rule labels, no jump penalty",
        "holdout_used": False,
        "outcome_used": False,
        "scaler_rule": SCALER_MODE_INNER_TRAIN,
        "selection_role": "explainable control only; never selected over a JM rung",
    }


def evaluate_design_ladder(raw: np.ndarray, weights: np.ndarray, *,
                           candidates: tuple[LadderCandidate, ...] | None = None,
                           seeds: tuple[int, ...] = (11, 23), n_folds: int = 3,
                           min_train: int = 100,
                           m0_feature_index: int = 0) -> dict:
    """G10/A14 — the registered small ladder, scored with inner-train-only scalers.

    Every rung is scored on the same nested inner splits. The scaler for every
    fold is fitted on that fold's raw inner train and applied frozen to the inner
    validation block, so an inner comparison cannot be contaminated by validation
    observations (A14). The returned manifest carries a denominator for every
    claim and a falsification section whose leakage CONTROL must move, otherwise
    the whole selection is ``NOT_EVALUABLE``.
    """
    raw = np.asarray(raw, dtype=np.float64)
    if raw.ndim != 2 or raw.shape[0] < 30:
        raise ValueError("raw must be a (T, J) matrix with enough rows for inner folds")
    weights = np.asarray(weights, dtype=np.float64)
    if weights.shape != (raw.shape[1],):
        raise ValueError(f"weights must be ({raw.shape[1]},), got {weights.shape}")
    ladder = tuple(candidates) if candidates is not None else registered_ladder()

    results, attempted, evaluated, folds_scored, observations_scored = [], 0, 0, 0, 0
    for index, candidate in enumerate(ladder):
        if candidate.observation_stride < 1:
            raise ValueError("observation_stride must be >= 1")
        sub = raw[::candidate.observation_stride]
        attempted += 1
        try:
            folds = inner_splits(sub.shape[0], n_folds, min_train)
        except ValueError as exc:
            results.append({**candidate.as_record(), "candidate_index": index,
                            "status": "NOT_EVALUABLE", "reason": str(exc)})
            continue
        if candidate.model == M0_MODEL:
            score = _score_m0_candidate(sub, weights, folds=folds, n_states=candidate.n_states,
                                        m0_feature_index=m0_feature_index)
        elif candidate.model == JM_MODEL:
            score = _score_jm_candidate(sub, weights, n_states=candidate.n_states,
                                        lambda_jump=float(candidate.lambda_jump),
                                        seeds=seeds, folds=folds)
        else:
            results.append({**candidate.as_record(), "candidate_index": index,
                            "status": "NOT_EVALUABLE",
                            "reason": f"unknown model {candidate.model!r}"})
            continue
        evaluated += 1
        folds_scored += len(score["folds"])
        observations_scored += score["observations_scored"]
        results.append({**candidate.as_record(), "candidate_index": index,
                        "status": "SCORED", "score": score})

    primary_jm = [r for r in results
                  if r.get("status") == "SCORED" and r["model"] == JM_MODEL
                  and r["cadence"] == PRIMARY_CADENCE]
    selected = None
    if primary_jm:
        selected = min(primary_jm,
                       key=lambda r: (r["score"]["mean_per_observation_objective"],
                                      r["n_states"], r["lambda_jump"]))

    folds = []
    try:
        folds = inner_splits(raw.shape[0], n_folds, min_train)
    except ValueError:
        folds = []
    mutation = inner_scaler_mutation_probe(raw, folds)
    leaky_control = None
    if selected is not None:
        leaky = _score_jm_candidate(raw, weights, n_states=selected["n_states"],
                                    lambda_jump=float(selected["lambda_jump"]), seeds=seeds,
                                    folds=folds, scaler_mode=SCALER_MODE_WHOLE_CALIBRATION)
        inner_mean = selected["score"]["mean_per_observation_objective"]
        leaky_mean = leaky["mean_per_observation_objective"]
        leaky_control = {
            "candidate": {"n_states": selected["n_states"],
                          "lambda_jump": selected["lambda_jump"]},
            "inner_train_mean_objective": inner_mean,
            "whole_calibration_mean_objective": leaky_mean,
            "objectives_differ": bool(inner_mean is not None and leaky_mean is not None
                                      and not np.isclose(inner_mean, leaky_mean)),
            "leaky_fold_scaler_digests": [f["scaler"]["digest"] for f in leaky["folds"]],
        }
    can_go_red = bool(mutation["detector_is_meaningful"]
                      and leaky_control is not None and leaky_control["objectives_differ"])
    denominators = {
        "candidates_attempted": attempted,
        "candidates_evaluated": evaluated,
        "folds_scored": folds_scored,
        "observations_scored": observations_scored,
    }
    status = ("SELECTED" if selected is not None and denominators["folds_scored"] > 0
              and denominators["candidates_evaluated"] > 0 and can_go_red else "NOT_EVALUABLE")
    return {
        "schema": "crypto_regime_lab.model_design_selection_manifest.v1",
        "status": status,
        "source_observations": int(raw.shape[0]),
        "source_features": int(raw.shape[1]),
        "candidate_grid": {
            "models": [M0_MODEL, JM_MODEL],
            "n_state_candidates": list(N_STATE_CANDIDATES),
            "lambda_candidates": list(LAMBDA_CANDIDATES),
            "cadence_menu": [{"cadence": c, "stride": s, "rationale": why}
                             for c, s, why in CADENCE_CANDIDATES],
            "cadence_rule": ("the selected comparison runs at the primary observation interval. "
                             "Alternate cadences are registered but not crossed by default, and "
                             "lambda is not transferable across cadences (RF03.2, lambda_jump_units)"),
            "default_ladder": [c.as_record() for c in registered_ladder()],
        },
        "candidates": results,
        "selection": None if selected is None else {
            "model": selected["model"], "n_states": selected["n_states"],
            "lambda_jump": selected["lambda_jump"], "cadence": selected["cadence"],
            "mean_per_observation_objective": selected["score"]["mean_per_observation_objective"],
            "candidate_index": selected["candidate_index"],
            "deployment_action": ("RECORDED_DESIGN_SELECTION. The frozen historical constants stay "
                                  "untouched; a new registration version is required before an "
                                  "outer/confirmation role may deploy the selected design "
                                  "(RF03.2: outer/confirmation does not retune)"),
        },
        "selection_rule": ("lowest mean per-observation objective on held-out inner chronological "
                           "blocks at the primary cadence; ties break to smaller K, then smaller "
                           "lambda. M0 is a control and is never selected"),
        "denominators": denominators,
        "falsification": {
            "inner_scaler_mutation_probe": mutation,
            "leaky_scaler_control": leaky_control,
            "can_go_red": can_go_red,
            "rule": ("the selection is SELECTED only when the inner-train scaler survives a "
                     "per-fold suffix mutation AND the deliberately leaky whole-calibration "
                     "scaler moves the objective. Otherwise the manifest is NOT_EVALUABLE"),
        },
        "inner_scaler_rule": ("per fold: fit_scaler(raw[:train_end]); the frozen scaler is applied "
                              "to raw[train_end:valid_end]. No validation observation enters the "
                              "scale (A14)"),
        "holdout_used": False,
        "outcome_used": False,
        "m0_feature_index": int(m0_feature_index),
    }


def choose_k_causal(raw: np.ndarray, weights: np.ndarray, *, lambda_jump: float,
                    seeds: tuple[int, ...] = (1, 2, 3),
                    candidates=(PARSIMONIOUS_K, STARTING_K), n_folds: int = 3,
                    min_train: int = 100,
                    expansion_decision: dict | None = None) -> dict:
    """``choose_k`` on RAW features, with the inner-train-only scaler rule (A14).

    Keeps the historical ``choose_k`` result keys (``registered_k_used``, ``scores``)
    so the existing registry writer and report renderer keep working, but the
    per-fold scaler now cannot see the inner validation block.
    """
    raw = np.asarray(raw, dtype=np.float64)
    considered = list(candidates)
    if EXPANSION_K in considered and not (expansion_decision or {}).get("approved"):
        considered = [k for k in considered if k != EXPANSION_K]
    folds = inner_splits(raw.shape[0], n_folds, min_train)
    results = {k: _score_jm_candidate(raw, weights, n_states=k, lambda_jump=lambda_jump,
                                      seeds=seeds, folds=folds) for k in considered}
    best = min(results, key=lambda k: (results[k]["mean_per_observation_objective"], k))
    return {
        "schema": "crypto_regime_lab.k_selection.v2",
        "registered_starting_k": STARTING_K,
        "k_policy": {str(k): v for k, v in K_POLICY.items()},
        "candidates_considered": considered,
        "expansion_k_requested": EXPANSION_K in candidates,
        "expansion_k_admitted": EXPANSION_K in considered,
        "expansion_decision": expansion_decision,
        "scores": {str(k): v for k, v in results.items()},
        "best_by_inner_criterion": int(best),
        "selection_rule": ("mean per-observation objective on held-out inner chronological blocks; "
                           "each fold's scaler is fitted on that fold's raw inner train only and "
                           "applied frozen to the validation block; ties break to the SMALLER K"),
        "inner_scaler_rule": ("fit_scaler(raw[:train_end]) per inner fold, applied frozen to "
                              "raw[train_end:valid_end]; the whole-calibration scaler is not used"),
        "inner_folds": [{"train_end": int(a), "valid_start": int(b), "valid_end": int(c)}
                        for a, b, c in folds],
        "chart_inspection_used": False,
        "method_note": ("a lower objective at higher K is close to automatic, so this comparison "
                        "never by itself justifies opening K=4. That needs a recorded discovery "
                        "decision naming the decision value the extra state buys (guide 8.1)"),
    }
