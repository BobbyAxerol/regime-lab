"""L06.3 / guide 9.2 — the similarity-weighted conditional response estimator.

What it answers: given the context now, how much better or worse would this
candidate have been than the incumbent, on past episodes that looked like now?

Three things in here are the difference between an estimate and a fabrication.

**``q_e`` is an ELIGIBILITY, not a bonus.** It is 1 when an episode's data and
evaluation were sound and 0 when they were not. Nothing in this module raises a
weight because an outcome was good — that would be selecting the evidence by its
answer, which guide 9.2 names outright.

**``N_eff`` is weight concentration, not a sample size.** ``(Σw)²/Σw²`` says how
many episodes the weights are spread over. It does NOT say how many independent
observations there are, and treating it as one is how a handful of overlapping
episodes turns into a tight standard error. The contiguous-block count and the
per-episode contribution are reported next to it for exactly that reason.

**The pairing is per episode.** ``U_e(θ) − U_e(θ_inc)`` is a difference on the
SAME episode, so the horizon, the initial-state contract and the economics cancel
(T47). Comparing a challenger's average against an incumbent's average over
different episodes would not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Chosen on inner development, registered before any recommendation (guide 9.2).
BANDWIDTH_H = 1.0
RECENCY_TAU_DAYS = 180.0
SHRINK_KAPPA = 8.0
#: Below this the estimator refuses to recommend and the incumbent stays.
MIN_EFFECTIVE_EPISODES = 4.0
MIN_CONTIGUOUS_BLOCKS = 2
#: One episode carrying more than this share of the weight is a warning (T48).
DOMINANCE_SHARE = 0.5

STATUS_OK = "SUPPORTED"
STATUS_INSUFFICIENT = "INSUFFICIENT_SUPPORT"
STATUS_DOMINATED = "DOMINATED_BY_ONE_EPISODE"
STATUS_NO_EPISODES = "NO_USABLE_EPISODES"


@dataclass
class SupportDiagnostics:
    """Everything guide 9.2 asks to be reported beside the estimate."""

    n_episodes: int
    n_effective: float
    max_weight_share: float
    contiguous_blocks: int
    lag1_autocorrelation: float | None
    per_episode_contribution: list[dict] = field(default_factory=list)

    def as_record(self) -> dict:
        return {
            "n_episodes": self.n_episodes,
            "n_effective": float(self.n_effective),
            "n_effective_meaning": (
                "weight concentration, (sum w)^2 / sum w^2. It is NOT a count of independent "
                "observations and must never be used as one (guide 9.2)"),
            "max_weight_share": float(self.max_weight_share),
            "contiguous_blocks": self.contiguous_blocks,
            "lag1_autocorrelation": self.lag1_autocorrelation,
            "per_episode_contribution": self.per_episode_contribution,
        }


@dataclass
class ResponseEstimate:
    """One conditional recommendation, with its evidence attached."""

    response_id: str
    candidate_id: str
    incumbent_id: str
    delta_local: float | None
    delta_pooled: float | None
    delta_shrunk: float | None
    shrink_weight: float | None
    standard_error: float | None
    status: str
    reason: str | None
    diagnostics: SupportDiagnostics
    supporting_episodes: list[dict] = field(default_factory=list)

    def as_record(self) -> dict:
        return {
            "response_id": self.response_id, "candidate_id": self.candidate_id,
            "incumbent_id": self.incumbent_id,
            "delta_local": self.delta_local, "delta_pooled": self.delta_pooled,
            "delta_shrunk": self.delta_shrunk, "shrink_weight": self.shrink_weight,
            "standard_error": self.standard_error,
            "se_basis": ("paired contiguous blocks of episodes, not iid bars. Episodes inside a "
                         "block share market conditions, so treating each as independent would "
                         "shrink this number without justification (guide 9.3)"),
            "status": self.status, "reason": self.reason,
            "diagnostics": self.diagnostics.as_record(),
            "supporting_episodes": self.supporting_episodes,
            "estimator_note": ("a policy estimator, not a calibrated posterior. The shrinkage is a "
                               "declared heuristic and the interval it implies is not a coverage "
                               "guarantee (guide 9.2)"),
        }


def context_distance(x_t: np.ndarray, x_e: np.ndarray, weights: np.ndarray) -> float:
    """Weighted distance in context space. Weights are TRAIN-ONLY (L06.3.4)."""
    x_t = np.asarray(x_t, dtype=np.float64)
    x_e = np.asarray(x_e, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if x_t.shape != x_e.shape or weights.shape != x_t.shape:
        raise ValueError("context vectors and weights must have the same shape")
    diff = x_t - x_e
    return float(np.sqrt(np.sum(weights * diff * diff)))


def emission_context(emission) -> np.ndarray:
    """A11: the raw economic coordinate of an emission, never the fit residual.

    A residual is a fit-error contribution: it carries neither the sign nor the
    level of the market context, so two opposite regimes sitting on their own
    centroids both report zero residual. Responses must compare this coordinate.
    """
    values = getattr(emission, "economic_context", None)
    if values is None and isinstance(emission, dict):
        values = emission.get("economic_context")
    if not values:
        raise ValueError("emission carries no economic_context; residual-only context is not comparable")
    return np.asarray(values, dtype=np.float64)


def context_distance_economic(left, right, weights: np.ndarray) -> float:
    """Weighted context distance on the raw economic coordinates (A11)."""
    return context_distance(emission_context(left), emission_context(right),
                            np.asarray(weights, dtype=np.float64))


def similarity_weights(x_t: np.ndarray, contexts: np.ndarray, ages_days: np.ndarray,
                       eligibility: np.ndarray, feature_weights: np.ndarray, *,
                       bandwidth: float = BANDWIDTH_H,
                       tau_days: float = RECENCY_TAU_DAYS) -> np.ndarray:
    """Guide 9.2: ``w = exp(-d^2/2h^2) * exp(-(t-e)/tau) * q_e``.

    ``eligibility`` may only be 0 or 1. A continuous "quality" that happened to
    correlate with outcome would smuggle the answer into the weights, so the
    function refuses anything else.
    """
    contexts = np.asarray(contexts, dtype=np.float64)
    ages = np.asarray(ages_days, dtype=np.float64)
    eligibility = np.asarray(eligibility, dtype=np.float64)
    if not np.all(np.isin(eligibility, (0.0, 1.0))):
        raise ValueError(
            "eligibility q_e must be 0 or 1. A graded quality score would let outcome-correlated "
            "information into the weights, which guide 9.2 forbids")
    if bandwidth <= 0 or tau_days <= 0:
        raise ValueError("bandwidth and tau must be positive")
    distances = np.asarray([context_distance(x_t, c, feature_weights) for c in contexts])
    kernel = np.exp(-(distances ** 2) / (2.0 * bandwidth ** 2))
    recency = np.exp(-np.maximum(ages, 0.0) / tau_days)
    return kernel * recency * eligibility


def effective_sample(weights: np.ndarray) -> float:
    weights = np.asarray(weights, dtype=np.float64)
    total = float(weights.sum())
    if total <= 0:
        return 0.0
    return float(total ** 2 / float(np.sum(weights ** 2)))


#: The support set is the smallest group of episodes carrying this share of the
#: weight. Counting blocks over EVERY episode with a non-zero weight would always
#: give one block, because a Gaussian kernel never reaches zero.
SUPPORT_COVERAGE = 0.90


def support_set(weights: np.ndarray, coverage: float = SUPPORT_COVERAGE) -> np.ndarray:
    """Indices of the smallest set of episodes carrying ``coverage`` of the weight."""
    weights = np.asarray(weights, dtype=np.float64)
    total = float(weights.sum())
    if total <= 0:
        return np.asarray([], dtype=int)
    order = np.argsort(-weights)
    cumulative = np.cumsum(weights[order]) / total
    keep = int(np.searchsorted(cumulative, coverage) + 1)
    return np.sort(order[:min(keep, weights.size)])


def contiguous_blocks(order: np.ndarray, weights: np.ndarray, *,
                      coverage: float = SUPPORT_COVERAGE) -> int:
    """How many separate stretches of time the real evidence comes from.

    Counted over the SUPPORT SET, not over every episode with a non-zero weight.
    The kernel gives some weight to everything, so a threshold near zero would
    always report one block and the check would be dead. What matters is whether
    the episodes actually carrying the estimate sit in one stretch of history or
    several: twelve consecutive weeks inside one market regime are one piece of
    evidence wearing twelve hats.
    """
    order = np.asarray(order)
    weights = np.asarray(weights, dtype=np.float64)
    active = support_set(weights, coverage)
    if active.size == 0:
        return 0
    positions = np.sort(order[active])
    return 1 + int(np.count_nonzero(np.diff(positions) > 1))


def lag1_autocorrelation(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=np.float64)
    if values.size < 3:
        return None
    centred = values - values.mean()
    denominator = float(np.sum(centred ** 2))
    if denominator <= 0:
        return None
    return float(np.sum(centred[1:] * centred[:-1]) / denominator)


def block_standard_error(paired_deltas: np.ndarray, order: np.ndarray,
                         weights: np.ndarray) -> float | None:
    """SE from paired CONTIGUOUS blocks, never from treating episodes as iid.

    Episodes are grouped into runs, each run is reduced to one weighted mean, and
    the standard error comes from those block means. With fewer than two blocks
    there is no spread to measure and the answer is None rather than zero.
    """
    deltas = np.asarray(paired_deltas, dtype=np.float64)
    order = np.asarray(order)
    weights = np.asarray(weights, dtype=np.float64)
    active = support_set(weights)
    if active.size < 2:
        return None
    positions = order[active]
    sort_index = np.argsort(positions)
    positions, values, w = (positions[sort_index], deltas[active][sort_index],
                            weights[active][sort_index])
    block_means, start = [], 0
    for i in range(1, len(positions) + 1):
        if i == len(positions) or positions[i] - positions[i - 1] > 1:
            segment_w = w[start:i]
            total = float(segment_w.sum())
            if total > 0:
                block_means.append(float(np.sum(values[start:i] * segment_w) / total))
            start = i
    if len(block_means) < 2:
        return None
    block_means = np.asarray(block_means, dtype=np.float64)
    return float(np.std(block_means, ddof=1) / np.sqrt(block_means.size))


def estimate_response(*, response_id: str, candidate_id: str, incumbent_id: str,
                      x_t: np.ndarray, contexts: np.ndarray, ages_days: np.ndarray,
                      eligibility: np.ndarray, feature_weights: np.ndarray,
                      candidate_utility: np.ndarray, incumbent_utility: np.ndarray,
                      episode_ids: list[str], order: np.ndarray,
                      pooled_delta: float | None = None,
                      bandwidth: float = BANDWIDTH_H, tau_days: float = RECENCY_TAU_DAYS,
                      kappa: float = SHRINK_KAPPA,
                      min_effective: float = MIN_EFFECTIVE_EPISODES,
                      min_blocks: int = MIN_CONTIGUOUS_BLOCKS) -> ResponseEstimate:
    """The guide 9.2 estimator, with its support diagnostics and its refusals."""
    candidate_utility = np.asarray(candidate_utility, dtype=np.float64)
    incumbent_utility = np.asarray(incumbent_utility, dtype=np.float64)
    if candidate_utility.shape != incumbent_utility.shape:
        raise ValueError(
            "the candidate and the incumbent must be scored on the SAME episodes; a per-episode "
            "difference is what makes the horizon, the initial state and the economics cancel "
            "(T47)")
    paired = candidate_utility - incumbent_utility

    if candidate_utility.size == 0:
        empty = SupportDiagnostics(0, 0.0, 0.0, 0, None, [])
        return ResponseEstimate(response_id, candidate_id, incumbent_id, None, pooled_delta,
                                None, None, None, STATUS_NO_EPISODES,
                                "no usable episode at this decision time", empty)

    weights = similarity_weights(x_t, contexts, ages_days, eligibility, feature_weights,
                                 bandwidth=bandwidth, tau_days=tau_days)
    total = float(weights.sum())
    n_eff = effective_sample(weights)
    shares = (weights / total) if total > 0 else np.zeros_like(weights)
    blocks = contiguous_blocks(order, weights)
    diagnostics = SupportDiagnostics(
        n_episodes=int(np.count_nonzero(weights > 1e-9)),
        n_effective=n_eff,
        max_weight_share=float(shares.max()) if shares.size else 0.0,
        contiguous_blocks=blocks,
        lag1_autocorrelation=lag1_autocorrelation(paired),
        per_episode_contribution=[
            {"episode_id": episode_ids[i], "weight": float(weights[i]),
             "share": float(shares[i]), "paired_delta": float(paired[i])}
            for i in np.argsort(-weights)[:10] if weights[i] > 1e-9])

    supporting = [row for row in diagnostics.per_episode_contribution]

    if total <= 0:
        return ResponseEstimate(response_id, candidate_id, incumbent_id, None, pooled_delta,
                                None, None, None, STATUS_NO_EPISODES,
                                "every episode was ineligible or too far in context",
                                diagnostics, supporting)

    delta_local = float(np.sum(weights * paired) / total)
    shrink = float(n_eff / (n_eff + kappa))
    pooled = float(pooled_delta) if pooled_delta is not None else 0.0
    delta_shrunk = shrink * delta_local + (1.0 - shrink) * pooled
    standard_error = block_standard_error(paired, order, weights)

    if n_eff < min_effective or blocks < min_blocks:
        return ResponseEstimate(
            response_id, candidate_id, incumbent_id, delta_local, pooled, delta_shrunk,
            shrink, standard_error, STATUS_INSUFFICIENT,
            f"N_eff={n_eff:.2f} (min {min_effective}) over {blocks} contiguous blocks "
            f"(min {min_blocks}); the incumbent is kept rather than acting on thin support",
            diagnostics, supporting)

    if diagnostics.max_weight_share > DOMINANCE_SHARE:
        return ResponseEstimate(
            response_id, candidate_id, incumbent_id, delta_local, pooled, delta_shrunk,
            shrink, standard_error, STATUS_DOMINATED,
            f"one episode carries {diagnostics.max_weight_share:.1%} of the weight; the estimate "
            "is shrunk toward pooled and flagged rather than presented as a conditional finding "
            "(T48)",
            diagnostics, supporting)

    return ResponseEstimate(response_id, candidate_id, incumbent_id, delta_local, pooled,
                            delta_shrunk, shrink, standard_error, STATUS_OK, None,
                            diagnostics, supporting)


def pooled_delta_from(paired_deltas_by_candidate: dict) -> dict:
    """The pooled prior each local estimate shrinks toward.

    Pooled over ALL eligible episodes without similarity weighting, so it carries
    no information about the current context — which is what makes it a prior
    rather than a second copy of the local estimate.
    """
    out = {}
    for candidate_id, deltas in paired_deltas_by_candidate.items():
        values = np.asarray(deltas, dtype=np.float64)
        out[candidate_id] = float(values.mean()) if values.size else 0.0
    return out


def hyperparameters() -> dict:
    return {
        "bandwidth_h": BANDWIDTH_H, "recency_tau_days": RECENCY_TAU_DAYS,
        "shrink_kappa": SHRINK_KAPPA,
        "min_effective_episodes": MIN_EFFECTIVE_EPISODES,
        "min_contiguous_blocks": MIN_CONTIGUOUS_BLOCKS,
        "dominance_share": DOMINANCE_SHARE,
        "support_coverage": SUPPORT_COVERAGE,
        "chosen_on": "inner development only, registered before any recommendation (guide 9.2)",
        "outcome_information_used_in_weights": False,
    }
