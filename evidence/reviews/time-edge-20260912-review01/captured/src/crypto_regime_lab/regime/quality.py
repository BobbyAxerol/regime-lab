"""L05.6 — novelty, ambiguity, degeneracy and the fallback semantics.

Guide 8.5 lists ``UNKNOWN_STATE``, ``MISSING_DATA``, ``STALE_MODEL`` and
``UNMAPPED_REFIT_STATE`` as DIFFERENT conditions, and T44 asks specifically that
novelty be distinguishable from missing data. The distinction is not cosmetic: a
feed outage that looks like a novel market state would send a policy hunting for a
regime that is not there, and a genuinely novel market that looks like an outage
would be silently ignored.

T40 covers the other direction. If the feature weights collapse to zero, or a
state ends up with no members, every state ties and the model has nothing to say.
The wrong response is to emit state 0 and a membership score of 1/K as though that
were a finding.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .emissions import (QUALITY_MISSING_DATA, QUALITY_OK, QUALITY_STALE_MODEL,
                        QUALITY_UNKNOWN_STATE)

#: Registered on development, before any emission is judged by it.
NOVELTY_QUANTILE = 0.99
AMBIGUITY_GAP_FLOOR = 1e-9
DEGENERATE_WEIGHT_SUM = 1e-12


@dataclass(frozen=True)
class QualityVerdict:
    status: str
    decision_eligible: bool
    reason: str
    novelty_score: float = 0.0
    ambiguity: float = 0.0
    detail: dict | None = None

    def as_record(self) -> dict:
        return {"status": self.status, "decision_eligible": self.decision_eligible,
                "reason": self.reason, "novelty_score": float(self.novelty_score),
                "ambiguity": float(self.ambiguity), "detail": self.detail or {}}


def fit_novelty_threshold(train_residuals: np.ndarray,
                          quantile: float = NOVELTY_QUANTILE) -> dict:
    """Out-of-support is defined by the TRAINING residual distribution, nothing later."""
    residuals = np.asarray(train_residuals, dtype=np.float64)
    residuals = residuals[np.isfinite(residuals)]
    if residuals.size == 0:
        raise ValueError("no finite training residuals; a novelty threshold cannot be defined")
    return {
        "quantile": float(quantile),
        "threshold": float(np.quantile(residuals, quantile)),
        "train_median": float(np.median(residuals)),
        "train_n": int(residuals.size),
        "fitted_on": "training residuals only, before any inference is judged by it",
    }


def check_degeneracy(weights: np.ndarray, centroids: np.ndarray,
                     state_counts: np.ndarray | None = None) -> dict:
    """T40 — a model that cannot discriminate must say so rather than emit a state.

    Three degeneracies are distinguished because they have different causes: all
    weights collapsed (a sparse-extension failure), centroids that coincide (a fit
    that found one state wearing K hats), and states with no members.
    """
    weights = np.asarray(weights, dtype=np.float64)
    centroids = np.asarray(centroids, dtype=np.float64)
    weight_sum = float(np.abs(weights).sum())
    collapsed_weights = weight_sum <= DEGENERATE_WEIGHT_SUM

    identical = []
    for i in range(centroids.shape[0]):
        for j in range(i + 1, centroids.shape[0]):
            d = centroids[i] - centroids[j]
            if float(np.sqrt(np.sum(weights * d * d))) <= 1e-12:
                identical.append([i, j])

    empty = []
    if state_counts is not None:
        counts = np.asarray(state_counts, dtype=np.int64)
        empty = [int(k) for k in range(counts.size) if counts[k] == 0]

    degenerate = bool(collapsed_weights or identical or empty)
    return {
        "schema": "crypto_regime_lab.regime_degeneracy.v1",
        "weight_sum": weight_sum,
        "collapsed_weights": collapsed_weights,
        "identical_centroid_pairs": identical,
        "empty_states": empty,
        "is_degenerate": degenerate,
        "usable_for_decisions": not degenerate,
        "rule": ("a degenerate model emits UNKNOWN_STATE with decision_eligible=false. It never "
                 "emits state 0 with a 1/K membership score, because that is a tie dressed up as "
                 "a finding (guide 8.5, T40)"),
        "sparse_extension_note": ("all-zero weights are the specific failure guide 8.3 warns "
                                 "about: an objective that is trivially minimised by discarding "
                                 "every feature is not a sparse solution"),
    }


def assess(*, costs: np.ndarray, fit_residual: float, novelty_threshold: float,
           missing_features: tuple[str, ...] = (), observation_age_seconds: float = 0.0,
           model_age_seconds: float = 0.0, max_model_age_seconds: float = float("inf"),
           degeneracy: dict | None = None) -> QualityVerdict:
    """Decide one emission's quality status. Order matters and is deliberate.

    Missing data is checked FIRST: an observation built from absent inputs cannot
    be judged novel, because there is nothing to be novel about. Only once the
    inputs are known present does a large residual mean the market is somewhere the
    training data never went.
    """
    if degeneracy is not None and degeneracy.get("is_degenerate"):
        return QualityVerdict(
            QUALITY_UNKNOWN_STATE, False,
            "the model is degenerate and cannot discriminate between states",
            detail={"degeneracy": degeneracy})

    if missing_features:
        return QualityVerdict(
            QUALITY_MISSING_DATA, False,
            f"required features absent: {sorted(missing_features)}. This is an INPUT failure and "
            "is deliberately not reported as a novel market state (T44)",
            detail={"missing_features": sorted(missing_features)})

    if model_age_seconds > max_model_age_seconds:
        return QualityVerdict(
            QUALITY_STALE_MODEL, False,
            f"the model was fitted {model_age_seconds:.0f}s ago, beyond the declared "
            f"{max_model_age_seconds:.0f}s. A stale model is not a novel market",
            detail={"model_age_seconds": model_age_seconds,
                    "max_model_age_seconds": max_model_age_seconds})

    costs = np.asarray(costs, dtype=np.float64)
    gap = float(np.partition(costs, 1)[1] - costs.min()) if costs.size > 1 else float("inf")
    novelty = float(fit_residual / novelty_threshold) if novelty_threshold > 0 else float("inf")

    if fit_residual > novelty_threshold:
        return QualityVerdict(
            QUALITY_UNKNOWN_STATE, False,
            "the observation sits outside the support the model was trained on: its fit residual "
            f"({fit_residual:.4f}) exceeds the training threshold ({novelty_threshold:.4f}). The "
            "inputs are PRESENT, which is what separates this from MISSING_DATA (T44)",
            novelty_score=novelty, ambiguity=gap,
            detail={"fit_residual": fit_residual, "novelty_threshold": novelty_threshold})

    return QualityVerdict(QUALITY_OK, True, "within training support with present inputs",
                          novelty_score=novelty, ambiguity=gap,
                          detail={"observation_age_seconds": observation_age_seconds})


def stress_overlay(liquidity_z: float, crowding_z: float) -> dict:
    """Guide 8.5 — stress/crowding is a SEPARATE axis, not a bear label.

    It is returned alongside a state, never folded into it. A context can be a
    positive trend AND crowded with thin liquidity at the same time, and forcing
    those onto one label would destroy the only information the overlay carries.
    """
    return {
        "schema": "crypto_regime_lab.stress_overlay.v1",
        "liquidity_z": float(liquidity_z), "crowding_z": float(crowding_z),
        "stress_score": float(max(liquidity_z, crowding_z)),
        "is_a_regime_state": False,
        "joint_labels_created": 0,
        "rule": ("reported on its own axis. It is not a bear state, and it does not multiply the "
                 "state vocabulary into K x stress joint labels (guide 8.5)"),
    }
