"""L05.2 — the discrete jump model: loss, causal forward filter, offline path, fit.

Guide 8.2 states the objective and 8.4 states the online recurrence. Two things in
here are easy to conflate and the whole causality argument rests on keeping them
apart.

**The forward filter is not Viterbi.** ``Q_t(k)`` is the cost of the best history
that ENDS in state k at time t. The state emitted at time t is ``argmin_k Q_t(k)``
-- decided with information available at t and never revised. Viterbi would walk
back from ``argmin_k Q_T(k)`` and rewrite earlier labels, which is exactly what
guide 8.4 forbids for anything a decision was taken on. The offline path is
computed here too, but only ever as a diagnostic carrying ``decision_eligible=False``.

**Q is not a ledger of emitted labels.** It is a per-endpoint minimum over paths.
The sequence of emitted states can therefore contain more switches than the
model's own jump penalty would suggest, and the policy's real switching cost must
be counted from the emitted tape, not inferred from ``lambda_jump``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np

#: Ties go to the lowest state index. Fixed, so a relabelling cannot silently
#: change an emission (guide 8.4 "tie-break fixed").
TIE_BREAK = "lowest_state_index"


class JumpModelError(ValueError):
    """A malformed model or input. Never silently repaired."""


def loss_matrix(z: np.ndarray, centroids: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """``l(z_t, mu_k) = 0.5 * sum_j w_j (z_jt - mu_jk)^2`` for every (t, k).

    ``weights`` is the per-feature ``w_j = omega_g / d_g * a_j`` from the feature
    schema, so adding features to one block cannot inflate that block's influence
    (guide 8.2).
    """
    z = np.asarray(z, dtype=np.float64)
    centroids = np.asarray(centroids, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if z.ndim != 2:
        raise JumpModelError("z must be (T, J)")
    if centroids.ndim != 2 or centroids.shape[1] != z.shape[1]:
        raise JumpModelError(f"centroids must be (K, {z.shape[1]}), got {centroids.shape}")
    if weights.shape != (z.shape[1],):
        raise JumpModelError(f"weights must be ({z.shape[1]},), got {weights.shape}")
    if np.any(weights < 0):
        raise JumpModelError("feature weights must be nonnegative (guide 8.2)")
    if not np.isfinite(z).all():
        raise JumpModelError("z contains non-finite values; handle missingness before scoring")
    diff = z[:, None, :] - centroids[None, :, :]
    return 0.5 * np.einsum("tkj,j->tk", diff * diff, weights)


def path_objective(loss: np.ndarray, states: np.ndarray, lambda_jump: float) -> float:
    """The objective of guide 8.2 for one explicit state path."""
    loss = np.asarray(loss, dtype=np.float64)
    states = np.asarray(states, dtype=np.int64)
    if states.shape != (loss.shape[0],):
        raise JumpModelError("states must have one entry per observation")
    fit = float(loss[np.arange(loss.shape[0]), states].sum())
    jumps = int(np.count_nonzero(states[1:] != states[:-1]))
    return fit + float(lambda_jump) * jumps


@dataclass
class ForwardResult:
    """Everything the causal filter produces, including what it must NOT be used for."""

    costs: np.ndarray                 # Q_t(k), possibly row-normalised
    raw_costs: np.ndarray             # Q_t(k) without normalisation
    online_states: np.ndarray         # argmin_k Q_t(k), emitted AT t and never revised
    backpointers: np.ndarray          # argmin_j for the transition into (t, k)
    normalised: bool = False
    offline_path: np.ndarray | None = None
    offline_decision_eligible: bool = False
    offline_note: str = (
        "the offline path is produced by walking back from the terminal argmin, so it rewrites "
        "labels using observations that did not exist when the decision was taken. It is a "
        "diagnostic only (guide 8.4)."
    )

    def switches(self) -> int:
        """Transitions on the EMITTED tape, which is what a policy actually pays for."""
        return int(np.count_nonzero(self.online_states[1:] != self.online_states[:-1]))


def forward_filter(loss: np.ndarray, lambda_jump: float, *,
                   normalise: bool = True, with_offline_path: bool = False) -> ForwardResult:
    """Guide 8.4: ``Q_t(k) = l(z_t, mu_k) + min_j {Q_{t-1}(j) + lambda_J * 1[j != k]}``.

    ``normalise`` subtracts ``min_k Q_t(k)`` after each update to keep the numbers
    on a usable scale. The guide permits this precisely because it shifts a whole
    row by a constant, so it changes neither the argmin nor any difference between
    states; ``raw_costs`` keeps the unshifted values and a test checks both.
    """
    loss = np.asarray(loss, dtype=np.float64)
    if loss.ndim != 2 or loss.shape[0] == 0:
        raise JumpModelError("loss must be (T, K) with T >= 1")
    if lambda_jump < 0:
        raise JumpModelError("lambda_jump must be nonnegative")
    n_obs, n_states = loss.shape

    costs = np.empty((n_obs, n_states), dtype=np.float64)
    raw = np.empty((n_obs, n_states), dtype=np.float64)
    back = np.full((n_obs, n_states), -1, dtype=np.int64)

    costs[0] = loss[0]
    raw[0] = loss[0]
    offset = 0.0
    if normalise:
        shift = float(costs[0].min())
        costs[0] = costs[0] - shift
        offset += shift

    for t in range(1, n_obs):
        previous = costs[t - 1]
        stay = previous                      # j == k, no jump penalty
        best_other = np.empty(n_states, dtype=np.float64)
        arg_other = np.empty(n_states, dtype=np.int64)
        # min over j != k, computed with the fixed lowest-index tie-break
        order = np.argsort(previous, kind="stable")
        best_j, second_j = int(order[0]), int(order[1]) if n_states > 1 else int(order[0])
        for k in range(n_states):
            j = second_j if k == best_j else best_j
            arg_other[k] = j
            best_other[k] = previous[j]
        switch = best_other + float(lambda_jump)
        take_stay = stay <= switch           # ties prefer staying, then lowest index
        costs[t] = loss[t] + np.where(take_stay, stay, switch)
        back[t] = np.where(take_stay, np.arange(n_states), arg_other)
        raw[t] = costs[t] + offset
        if normalise:
            shift = float(costs[t].min())
            costs[t] = costs[t] - shift
            offset += shift

    online = np.argmin(costs, axis=1).astype(np.int64)   # np.argmin -> lowest index on ties

    offline = None
    if with_offline_path:
        offline = np.empty(n_obs, dtype=np.int64)
        offline[-1] = int(np.argmin(costs[-1]))
        for t in range(n_obs - 1, 0, -1):
            offline[t - 1] = back[t, offline[t]]

    return ForwardResult(costs=costs, raw_costs=raw, online_states=online, backpointers=back,
                         normalised=bool(normalise), offline_path=offline)


def second_best_gap(costs: np.ndarray) -> np.ndarray:
    """How far the emitted state is from the runner-up, per observation.

    A small gap means the emission was nearly a coin flip. It is an AMBIGUITY
    measure and is deliberately not converted into a probability (guide 8.5).
    """
    costs = np.asarray(costs, dtype=np.float64)
    if costs.shape[1] < 2:
        return np.full(costs.shape[0], np.inf)
    partitioned = np.partition(costs, 1, axis=1)
    return partitioned[:, 1] - partitioned[:, 0]


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------

@dataclass
class FitDiagnostics:
    """Everything a fit must disclose, whether or not it is flattering."""

    seed: int
    iterations: int
    converged: bool
    objective_trace: list[float] = field(default_factory=list)
    empty_states: list[int] = field(default_factory=list)
    empty_state_policy: str = "retained_as_empty_and_reported"
    final_objective: float = float("nan")

    def as_record(self) -> dict:
        return {
            "seed": self.seed, "iterations": self.iterations, "converged": self.converged,
            "objective_trace": [float(v) for v in self.objective_trace],
            "objective_monotone_nonincreasing": all(
                b <= a + 1e-9 for a, b in zip(self.objective_trace, self.objective_trace[1:])),
            "empty_states": self.empty_states, "empty_state_policy": self.empty_state_policy,
            "final_objective": float(self.final_objective),
        }


def _segment_states(loss: np.ndarray, lambda_jump: float) -> np.ndarray:
    """The DP segmentation used INSIDE the fit.

    This one is allowed to use the whole training window, because fitting is not a
    decision -- it is offline calibration on data whose cutoff is declared. What is
    forbidden is using it to emit a label that a trade was taken on.
    """
    result = forward_filter(loss, lambda_jump, normalise=True, with_offline_path=True)
    return result.offline_path


def fit_jump_model(z: np.ndarray, weights: np.ndarray, *, n_states: int, lambda_jump: float,
                   seed: int, max_iter: int = 50, tol: float = 1e-9) -> tuple[np.ndarray, FitDiagnostics]:
    """Alternating centroid update and DP segmentation (guide 8.2).

    The objective is non-increasing by construction: each half of the alternation
    minimises it with the other half held fixed. That is a LOCAL minimum and the
    guide is explicit that it must not be called a global one.
    """
    z = np.asarray(z, dtype=np.float64)
    if n_states < 1:
        raise JumpModelError("n_states must be >= 1")
    if z.shape[0] < n_states:
        raise JumpModelError(f"{z.shape[0]} observations cannot support {n_states} states")

    rng = np.random.default_rng(seed)
    # k-means++-style spread start, deterministic given the seed
    first = int(rng.integers(0, z.shape[0]))
    chosen = [first]
    for _ in range(1, n_states):
        d = np.min(np.stack([np.sum((z - z[c]) ** 2 * weights, axis=1) for c in chosen]), axis=0)
        total = float(d.sum())
        probabilities = (d / total) if total > 0 else np.full(z.shape[0], 1.0 / z.shape[0])
        chosen.append(int(rng.choice(z.shape[0], p=probabilities)))
    centroids = z[chosen].copy()

    diagnostics = FitDiagnostics(seed=seed, iterations=0, converged=False)
    states = np.zeros(z.shape[0], dtype=np.int64)
    previous = np.inf
    for iteration in range(1, max_iter + 1):
        loss = loss_matrix(z, centroids, weights)
        states = _segment_states(loss, lambda_jump)
        objective = path_objective(loss, states, lambda_jump)
        diagnostics.objective_trace.append(objective)

        empty = []
        for k in range(n_states):
            members = z[states == k]
            if members.size == 0:
                empty.append(k)
                continue                      # keep the centroid; never invent members
            centroids[k] = members.mean(axis=0)
        diagnostics.empty_states = empty
        diagnostics.iterations = iteration
        if previous - objective <= tol:
            diagnostics.converged = True
            break
        previous = objective

    diagnostics.final_objective = diagnostics.objective_trace[-1] if diagnostics.objective_trace \
        else float("nan")
    return centroids, diagnostics


def multi_start_fit(z: np.ndarray, weights: np.ndarray, *, n_states: int, lambda_jump: float,
                    seeds: tuple[int, ...], max_iter: int = 50) -> dict:
    """Bounded multi-start. The winner is chosen on the TRAIN objective only.

    Guide 8.2: "không chọn random seed theo outer profit". Nothing in this function
    can see an outcome, which is the point -- it is structurally unable to pick a
    seed by profit.
    """
    runs = []
    for seed in seeds:
        centroids, diagnostics = fit_jump_model(z, weights, n_states=n_states,
                                                lambda_jump=lambda_jump, seed=seed,
                                                max_iter=max_iter)
        runs.append({"seed": seed, "centroids": centroids, "diagnostics": diagnostics})
    best = min(runs, key=lambda r: (r["diagnostics"].final_objective, r["seed"]))
    spread = [r["diagnostics"].final_objective for r in runs]
    return {
        "centroids": best["centroids"],
        "selected_seed": best["seed"],
        "selection_criterion": "lowest TRAIN objective; ties broken on the lowest seed",
        "outer_information_used": False,
        "runs": [{"seed": r["seed"], **r["diagnostics"].as_record()} for r in runs],
        "objective_spread": {"min": float(min(spread)), "max": float(max(spread)),
                             "range": float(max(spread) - min(spread))},
        "local_minimum_only": (
            "alternating minimisation reaches a LOCAL minimum; the spread across seeds is "
            "reported rather than claiming the best run found the global optimum (guide 8.2)"),
    }


def centroid_digest(centroids: np.ndarray) -> str:
    payload = json.dumps(np.asarray(centroids, dtype=np.float64).round(12).tolist())
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# a SECOND, different online algorithm -- kept separate on purpose
# ---------------------------------------------------------------------------

def greedy_online_states(loss: np.ndarray) -> np.ndarray:
    """Nearest centroid at each observation, with NO history and NO jump penalty.

    Guide L05.2: "Greedy online và endpoint-DP nếu đều thử là hai model versions,
    không mix." This is that other algorithm. It is causal too -- it reads only the
    current observation -- but it is a different model, not a cheaper approximation
    of the DP, and it will flicker wherever the DP holds a state.

    Nothing may blend the two. A study picks one, records which, and the emitted
    tapes carry different model versions.
    """
    loss = np.asarray(loss, dtype=np.float64)
    if loss.ndim != 2:
        raise JumpModelError("loss must be (T, K)")
    return np.argmin(loss, axis=1).astype(np.int64)


def compare_online_algorithms(loss: np.ndarray, lambda_jump: float) -> dict:
    """Measure how far apart the two online algorithms are, and refuse to merge them."""
    endpoint = forward_filter(loss, lambda_jump)
    greedy = greedy_online_states(loss)
    agree = float(np.mean(endpoint.online_states == greedy))
    greedy_switches = int(np.count_nonzero(greedy[1:] != greedy[:-1]))
    return {
        "schema": "crypto_regime_lab.online_algorithm_comparison.v1",
        "endpoint_dp": {
            "model_version_suffix": "endpoint_dp",
            "states": endpoint.online_states.tolist()[:50],
            "switches": endpoint.switches(),
            "uses_history": True, "uses_jump_penalty": True,
        },
        "greedy": {
            "model_version_suffix": "greedy",
            "states": greedy.tolist()[:50],
            "switches": greedy_switches,
            "uses_history": False, "uses_jump_penalty": False,
        },
        "label_agreement": agree,
        "identical": bool(agree == 1.0),
        "switch_ratio_greedy_over_dp": (greedy_switches / endpoint.switches())
        if endpoint.switches() else None,
        "are_two_model_versions": True,
        "mixing_rule": ("these are two models, not two settings of one. A study declares which it "
                        "uses and the emitted tape carries that version; blending them, or "
                        "falling back from one to the other, would make 'the model said X' "
                        "meaningless (guide L05.2)"),
    }
