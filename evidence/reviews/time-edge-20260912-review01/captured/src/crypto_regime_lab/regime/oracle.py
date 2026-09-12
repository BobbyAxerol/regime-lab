"""T37 — a brute-force oracle for the jump-model recurrence.

The forward recurrence in ``jump_model.forward_filter`` is a dynamic program, and
a dynamic program is an ASSERTION that a local recurrence equals a global minimum.
On short sequences that assertion can simply be checked: enumerate every one of
the ``K**T`` state paths, score each with the guide's objective, and compare.

This is deliberately the slow, obvious implementation. It shares no code with the
DP beyond ``path_objective``, so a bug in the recurrence cannot hide in both.
"""

from __future__ import annotations

import itertools

import numpy as np

from .jump_model import JumpModelError, path_objective

#: Above this the enumeration stops being a check and starts being a hang.
MAX_ENUMERATED_PATHS = 5_000_000


def enumerate_paths(n_obs: int, n_states: int):
    if n_states ** n_obs > MAX_ENUMERATED_PATHS:
        raise JumpModelError(
            f"{n_states}**{n_obs} paths exceeds the {MAX_ENUMERATED_PATHS} enumeration cap; "
            "this oracle is only for toy sequences")
    return itertools.product(range(n_states), repeat=n_obs)


def exhaustive_endpoint_costs(loss: np.ndarray, lambda_jump: float) -> np.ndarray:
    """``best[t, k]`` = the minimum objective over every path of length t+1 ending in k.

    This is exactly what ``Q_t(k)`` claims to be, computed without any recurrence.
    """
    loss = np.asarray(loss, dtype=np.float64)
    n_obs, n_states = loss.shape
    best = np.full((n_obs, n_states), np.inf)
    for prefix_len in range(1, n_obs + 1):
        window = loss[:prefix_len]
        for path in enumerate_paths(prefix_len, n_states):
            states = np.asarray(path, dtype=np.int64)
            value = path_objective(window, states, lambda_jump)
            end = states[-1]
            if value < best[prefix_len - 1, end]:
                best[prefix_len - 1, end] = value
    return best


def exhaustive_best_path(loss: np.ndarray, lambda_jump: float) -> tuple[np.ndarray, float]:
    """The single lowest-objective full path, with the lowest-index tie-break."""
    loss = np.asarray(loss, dtype=np.float64)
    n_obs, n_states = loss.shape
    best_value = np.inf
    best_path: tuple[int, ...] | None = None
    for path in enumerate_paths(n_obs, n_states):
        value = path_objective(loss, np.asarray(path, dtype=np.int64), lambda_jump)
        if value < best_value - 1e-12 or (best_path is not None
                                          and abs(value - best_value) <= 1e-12
                                          and path < best_path):
            best_value, best_path = value, path
    return np.asarray(best_path, dtype=np.int64), float(best_value)


def exhaustive_online_states(loss: np.ndarray, lambda_jump: float) -> np.ndarray:
    """What a causal filter MUST emit: at each t, the endpoint state with the lowest
    cost using observations 1..t only. Derived from the exhaustive costs, so it
    depends on no recurrence at all."""
    best = exhaustive_endpoint_costs(loss, lambda_jump)
    return np.argmin(best, axis=1).astype(np.int64)
