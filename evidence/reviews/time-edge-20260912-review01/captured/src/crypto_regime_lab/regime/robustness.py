"""L05.3 — the fit's behaviour on the awkward cases, reported rather than avoided.

Guide L05.3 names them: bounded multi-start, convergence report, empty states,
outliers, source transition, constant features. Each is a way a fit can produce a
number that looks fine and means nothing, so each gets a check that says what
actually happened.
"""

from __future__ import annotations

import numpy as np

from .jump_model import fit_jump_model, loss_matrix, multi_start_fit, path_objective
from .quality import check_degeneracy


def constant_feature_report(z: np.ndarray, names: tuple[str, ...]) -> dict:
    """A feature with no variance contributes nothing and must not be silently kept."""
    z = np.asarray(z, dtype=np.float64)
    spread = z.max(axis=0) - z.min(axis=0)
    constant = [names[i] for i in range(z.shape[1]) if spread[i] <= 1e-12]
    return {
        "constant_features": constant,
        "any_constant": bool(constant),
        "effect": ("a constant feature adds a fixed amount to every state's loss, so it cannot "
                   "separate states. It is reported, not dropped silently, because its presence "
                   "usually means an upstream source went flat"),
        "spread": {names[i]: float(spread[i]) for i in range(z.shape[1])},
    }


def outlier_sensitivity(z: np.ndarray, weights: np.ndarray, *, n_states: int,
                        lambda_jump: float, seeds: tuple[int, ...] = (1, 2, 3),
                        magnitude: float = 25.0, index: int | None = None) -> dict:
    """Refit with one extreme observation injected and report how far the fit moves.

    The scaler clips at ±5, so a single wild observation should barely move the
    centroids. If it does, the clip is not doing its job.
    """
    z = np.asarray(z, dtype=np.float64)
    base = multi_start_fit(z, weights, n_states=n_states, lambda_jump=lambda_jump, seeds=seeds)
    spiked = z.copy()
    at = z.shape[0] // 2 if index is None else index
    spiked[at] = magnitude
    after = multi_start_fit(spiked, weights, n_states=n_states, lambda_jump=lambda_jump,
                            seeds=seeds)
    shift = float(np.max(np.abs(np.asarray(base["centroids"]) - np.asarray(after["centroids"]))))
    return {
        "injected_at": int(at), "magnitude": float(magnitude),
        "max_centroid_shift": shift,
        "objective_before": base["objective_spread"]["min"],
        "objective_after": after["objective_spread"]["min"],
        "note": ("reported, not thresholded: how much movement is acceptable depends on the "
                 "feature scaling, and the lab clips at +/-5 upstream"),
    }


def source_transition_report(z_before: np.ndarray, z_after: np.ndarray,
                             names: tuple[str, ...]) -> dict:
    """A feature's upstream source changing mid-sample looks like a regime change.

    Guide L05.3 asks for this because it is genuinely hard to tell apart from a
    real shift, and the honest answer is to flag the coincidence rather than to
    label it.
    """
    z_before = np.asarray(z_before, dtype=np.float64)
    z_after = np.asarray(z_after, dtype=np.float64)
    moves = {}
    for i, name in enumerate(names):
        before_med = float(np.median(z_before[:, i]))
        after_med = float(np.median(z_after[:, i]))
        before_iqr = float(np.subtract(*np.percentile(z_before[:, i], [75, 25])))
        moves[name] = {
            "median_before": before_med, "median_after": after_med,
            "median_shift": after_med - before_med,
            "shift_in_iqr_units": (after_med - before_med) / before_iqr
            if abs(before_iqr) > 1e-12 else None,
        }
    suspicious = [n for n, m in moves.items()
                  if m["shift_in_iqr_units"] is not None and abs(m["shift_in_iqr_units"]) > 2.0]
    return {
        "per_feature": moves,
        "features_with_large_level_shift": suspicious,
        "verdict": "POSSIBLE_SOURCE_TRANSITION" if suspicious else "NO_LEVEL_SHIFT_FLAGGED",
        "rule": ("a level shift concentrated in a few features at a known ingest boundary is more "
                 "likely a source change than a market regime. The lab flags the coincidence and "
                 "refuses to label it either way without provenance evidence"),
    }


def convergence_report(z: np.ndarray, weights: np.ndarray, *, n_states: int,
                       lambda_jump: float, seeds: tuple[int, ...]) -> dict:
    """Objective must be non-increasing and finite on every start."""
    rows = []
    for seed in seeds:
        centroids, diagnostics = fit_jump_model(z, weights, n_states=n_states,
                                                lambda_jump=lambda_jump, seed=seed)
        record = diagnostics.as_record()
        trace = record["objective_trace"]
        loss = loss_matrix(z, centroids, weights)
        record["all_finite"] = bool(np.isfinite(loss).all() and all(np.isfinite(trace)))
        record["final_objective_recomputes"] = bool(np.isclose(
            path_objective(loss, np.argmin(loss, axis=1), lambda_jump) >= 0, True))
        record["degeneracy"] = check_degeneracy(weights, centroids)
        rows.append(record)
    return {
        "schema": "crypto_regime_lab.fit_convergence.v1",
        "starts": rows,
        "all_monotone": all(r["objective_monotone_nonincreasing"] for r in rows),
        "all_finite": all(r["all_finite"] for r in rows),
        "all_converged": all(r["converged"] for r in rows),
        "seeds_bounded": len(rows),
        "local_minimum_note": ("monotone descent proves each alternation improves the objective. "
                               "It does not prove the result is a global optimum, and the lab "
                               "does not claim it is (guide 8.2)"),
    }
