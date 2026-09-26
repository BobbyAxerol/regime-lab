"""SD-02: Statistical Jump Model, K=2 (guide SS5.3-SS5.4).

Objective: min_{mu,s} sum_t l(z_t, mu_{s_t}) + lambda_J * sum_t 1(s_t != s_{t-1}),
with l = squared Euclidean distance on standardized features (the JM
literature's own default loss).

Two distinct passes, deliberately kept separate so the emitted tape can
never leak future information into a past bar's state:

1. FIT (batch, internal only): coordinate descent between (a) a full
   forward+backward Viterbi decode of the whole training batch given
   frozen centroids, and (b) recomputing centroids as the mean of their
   assigned points. This is legitimate because the WHOLE batch is already
   "past" relative to the origin cutoff -- it is not a leak across the
   origin boundary, only an internal training step.
2. FILTER (forward-only, causal, what gets emitted/tape-recorded): given
   the FROZEN, already-fit centroids, a strictly forward recursion
   state[t] = argmin_k cost[t][k] where cost[t][k] only depends on
   z[1..t]. Running this on any PREFIX of a sequence reproduces the exact
   same states for that prefix as running it on the full sequence --
   this is the "prefix-by-prefix online parity" guarantee (S2-T02).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

K_STATES = 2
DEFAULT_TOLERANCE = 1e-8
DEFAULT_MAX_ITER = 100
DEFAULT_SEED = 20260925
SCHEMA_HASH = hashlib.sha256(b"regime_lab.sd_jm_model.v1").hexdigest()[:16]

NORMALIZED_PENALTIES = (0.5, 1.0, 2.0)


class JMError(ValueError):
    """Jump model fit or filter could not proceed."""


@dataclass(frozen=True)
class JMFit:
    centroids: np.ndarray            # shape (K, n_features), in STANDARDIZED units
    feature_mean: np.ndarray         # shape (n_features,) -- train-only
    feature_std: np.ndarray          # shape (n_features,) -- train-only, ddof=1
    lambda_j: float                  # penalty in STANDARDIZED squared-distance units
    n_iter: int
    converged: bool
    seed: int
    train_terminal_state: int        # filtered state of the LAST training row (causal "current" state)
    schema_hash: str = field(default=SCHEMA_HASH)


def _squared_loss(z: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """z: (T, F), mu: (K, F) -> (T, K) squared Euclidean distances."""
    diff = z[:, None, :] - mu[None, :, :]
    return np.sum(diff * diff, axis=2)


def _causal_forward_states(loss: np.ndarray, lambda_j: float) -> np.ndarray:
    """Strictly forward, greedy-argmin filter. loss: (T, K). Returns (T,)
    int state path where state[t] depends ONLY on loss[0..t]. This is the
    function whose output is emitted/tape-recorded -- never the batch
    Viterbi path used internally during fitting."""
    t_len, k = loss.shape
    cost = np.empty((t_len, k), dtype=float)
    cost[0] = loss[0]
    for t in range(1, t_len):
        prev = cost[t - 1]
        for state in range(k):
            stay = prev[state]
            switch = min(prev[j] for j in range(k) if j != state) + lambda_j
            cost[t, state] = loss[t, state] + min(stay, switch)
    return np.argmin(cost, axis=1)


def _batch_viterbi_path(loss: np.ndarray, lambda_j: float) -> np.ndarray:
    """Full forward-DP + backward-traceback over the WHOLE batch -- the
    globally optimal path GIVEN the current centroids. Used only inside
    the internal fit loop (an E-step), never emitted directly."""
    t_len, k = loss.shape
    cost = np.empty((t_len, k), dtype=float)
    back = np.zeros((t_len, k), dtype=int)
    cost[0] = loss[0]
    for t in range(1, t_len):
        prev = cost[t - 1]
        for state in range(k):
            candidates = [(prev[j] + (0.0 if j == state else lambda_j), j) for j in range(k)]
            best_cost, best_prev = min(candidates, key=lambda c: c[0])
            cost[t, state] = loss[t, state] + best_cost
            back[t, state] = best_prev
    path = np.zeros(t_len, dtype=int)
    path[-1] = int(np.argmin(cost[-1]))
    for t in range(t_len - 2, -1, -1):
        path[t] = back[t + 1, path[t + 1]]
    return path


def _init_centroids(z: np.ndarray, *, seed: int) -> np.ndarray:
    """Deterministic k-means++-style init, pinned by seed (guide SS5.3:
    "Solver seed ... initialization ... duoc pin")."""
    rng = np.random.default_rng(seed)
    first_idx = int(rng.integers(0, z.shape[0]))
    first = z[first_idx]
    dist_sq = np.sum((z - first[None, :]) ** 2, axis=1)
    total = float(dist_sq.sum())
    if total <= 0:
        raise JMError("DEGENERATE_FEATURE_GEOMETRY: all standardized feature rows identical")
    probs = dist_sq / total
    second_idx = int(rng.choice(z.shape[0], p=probs))
    return np.stack([first, z[second_idx]], axis=0)


def standardize(z_raw: np.ndarray) -> tuple:
    """Train-only standardization. Returns (z_std, mean, std). Raises on a
    zero-variance feature rather than dividing by zero silently."""
    mean = z_raw.mean(axis=0)
    std = z_raw.std(axis=0, ddof=1)
    if np.any(std <= 0):
        raise JMError("DEGENERATE_FEATURE_GEOMETRY: a feature has zero train-window variance")
    return (z_raw - mean[None, :]) / std[None, :], mean, std


def fit_jm(z_raw: np.ndarray, *, lambda_j: float, seed: int = DEFAULT_SEED,
          tolerance: float = DEFAULT_TOLERANCE, max_iter: int = DEFAULT_MAX_ITER) -> JMFit:
    """Batch-fit centroids via coordinate descent (Viterbi E-step + mean
    M-step) on a causal training window (all rows already <= origin
    cutoff). The RETURNED train_terminal_state comes from a SEPARATE
    causal forward filter pass over this same window with the final
    frozen centroids -- not from the internal batch Viterbi path."""
    if z_raw.ndim != 2:
        raise JMError(f"expected 2D (T, F) array, got shape {z_raw.shape}")
    t_len = z_raw.shape[0]
    if t_len < K_STATES + 1:
        raise JMError(f"need >= {K_STATES + 1} rows to fit K={K_STATES}, got {t_len}")
    if lambda_j < 0:
        raise JMError("lambda_j must be >= 0")

    z, mean, std = standardize(z_raw)
    centroids = _init_centroids(z, seed=seed)
    prev_path = None
    converged = False
    n_iter = 0
    for n_iter in range(1, max_iter + 1):
        loss = _squared_loss(z, centroids)
        path = _batch_viterbi_path(loss, lambda_j)
        if prev_path is not None and np.array_equal(path, prev_path):
            converged = True
            break
        new_centroids = np.array(centroids)
        for k in range(K_STATES):
            mask = path == k
            if np.any(mask):
                new_centroids[k] = z[mask].mean(axis=0)
        shift = float(np.max(np.abs(new_centroids - centroids)))
        centroids = new_centroids
        prev_path = path
        if shift < tolerance:
            converged = True
            break

    filter_loss = _squared_loss(z, centroids)
    filtered_states = _causal_forward_states(filter_loss, lambda_j)
    return JMFit(centroids=centroids, feature_mean=mean, feature_std=std, lambda_j=lambda_j,
                n_iter=n_iter, converged=converged, seed=seed,
                train_terminal_state=int(filtered_states[-1]))


def causal_filter_states(fit: JMFit, z_raw: np.ndarray) -> np.ndarray:
    """Apply an ALREADY-FIT (frozen centroids) model's forward filter to any
    raw feature sequence, standardized with the FIT's own train-only
    mean/std (never re-fit on the new data). Prefix-by-prefix online
    parity: filtering z_raw[:n] and then z_raw for a longer n' > n
    reproduces identical states for indices [0, n)."""
    if z_raw.ndim != 2 or z_raw.shape[1] != fit.centroids.shape[1]:
        raise JMError(f"feature dimensionality mismatch: expected {fit.centroids.shape[1]}, "
                      f"got {z_raw.shape[1] if z_raw.ndim == 2 else z_raw.ndim}")
    z_std = (z_raw - fit.feature_mean[None, :]) / fit.feature_std[None, :]
    loss = _squared_loss(z_std, fit.centroids)
    return _causal_forward_states(loss, fit.lambda_j)


def normalized_lambda(c: float, loss_scale: float) -> float:
    """lambda_J = c * loss_scale (guide SS5.3: normalized penalty designs
    c in {0.5, 1, 2} against a train-only median one-centroid loss scale)."""
    if loss_scale <= 0:
        raise JMError("DEGENERATE_FEATURE_GEOMETRY: non-positive loss_scale")
    return c * loss_scale


def median_one_centroid_loss_scale(z_raw: np.ndarray) -> float:
    """Train-only default L: median finite one-centroid (grand-mean) loss
    on the current train window, with the SAME standardization the fit
    itself will use (guide SS5.3)."""
    z, _, _ = standardize(z_raw)
    grand_mean = z.mean(axis=0, keepdims=True)
    per_row_loss = np.sum((z - grand_mean) ** 2, axis=1)
    return float(np.median(per_row_loss))
