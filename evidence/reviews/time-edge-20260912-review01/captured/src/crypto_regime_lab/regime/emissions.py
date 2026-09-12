"""L05.2/L05.5 — the emission tape: causal, append-only, and identical under
streaming or batch.

Guide 8.4 draws a line the rest of the lab depends on: a label a decision was
taken on may never be rewritten. So an emission carries the vintage it was made
at, the tape is append-only, and a later refit writes ``asof_T_training_labels``
into a SEPARATE series rather than over the decision-vintage tape.

Guide 8.5 fixes what an emission must carry. Notably ``softmax(-cost)`` is a
membership SCORE and is not a probability until something calibrates it, so the
field is named accordingly and a separate flag records that no calibration exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .jump_model import JumpModelError, loss_matrix, second_best_gap

QUALITY_OK = "OK"
QUALITY_UNKNOWN_STATE = "UNKNOWN_STATE"
QUALITY_MISSING_DATA = "MISSING_DATA"
QUALITY_STALE_MODEL = "STALE_MODEL"
QUALITY_UNMAPPED_REFIT_STATE = "UNMAPPED_REFIT_STATE"
#: Guide 8.5 names these as DIFFERENT conditions. Collapsing them would let a data
#: outage look like a novel market state.
QUALITY_STATUSES = (QUALITY_OK, QUALITY_UNKNOWN_STATE, QUALITY_MISSING_DATA,
                    QUALITY_STALE_MODEL, QUALITY_UNMAPPED_REFIT_STATE)


@dataclass(frozen=True)
class Emission:
    """One regime observation, as guide 8.5 specifies it."""

    state_id: int
    state_namespace: str
    state_costs: tuple[float, ...]
    second_best_gap: float
    fit_residual: float
    novelty_score: float
    feature_contributions: tuple[float, ...]
    group_contributions: dict
    observed_at: str
    available_at: str
    inferred_at: str
    model_fit_cutoff: str
    ready_at: str
    version: str
    quality_status: str
    input_refs: tuple[str, ...]
    membership_score: tuple[float, ...]
    membership_is_calibrated: bool = False
    # A11: the raw economic coordinate the state was inferred from. Responses
    # compare THIS, not the squared fit residual, which loses sign and state.
    economic_context: tuple[float, ...] = ()
    decision_eligible: bool = True

    def as_record(self) -> dict:
        return {
            "state_id": int(self.state_id), "state_namespace": self.state_namespace,
            "state_costs": [float(c) for c in self.state_costs],
            "second_best_gap": float(self.second_best_gap),
            "fit_residual": float(self.fit_residual), "novelty_score": float(self.novelty_score),
            "feature_contributions": [float(c) for c in self.feature_contributions],
            "group_contributions": self.group_contributions,
            "observed_at": self.observed_at, "available_at": self.available_at,
            "inferred_at": self.inferred_at, "model_fit_cutoff": self.model_fit_cutoff,
            "ready_at": self.ready_at, "version": self.version,
            "quality_status": self.quality_status, "input_refs": list(self.input_refs),
            "membership_score": [float(m) for m in self.membership_score],
            "membership_is_calibrated": bool(self.membership_is_calibrated),
            "economic_context": [float(v) for v in self.economic_context],
            "membership_note": ("softmax(-cost) over state costs. It is a MEMBERSHIP SCORE, not a "
                                "probability: nothing here calibrates it against outcomes, so "
                                "'0.9' does not mean the market is 90% in this state "
                                "(guide 8.5)"),
            "decision_eligible": bool(self.decision_eligible),
        }


def membership_scores(costs: np.ndarray) -> np.ndarray:
    """``softmax(-cost)``. Named a score, never a probability (guide 8.5, T42)."""
    costs = np.asarray(costs, dtype=np.float64)
    shifted = -(costs - costs.min())
    exponent = np.exp(shifted)
    total = exponent.sum()
    return exponent / total if total > 0 else np.full(costs.shape, 1.0 / costs.size)


class ImmutableTapeViolation(RuntimeError):
    """An attempt to rewrite an emission a decision may already have used."""


@dataclass
class EmissionTape:
    """Append-only. A refit may add a new vintage; it may never edit an old one."""

    namespace: str
    emissions: list[Emission] = field(default_factory=list)
    _sealed_through: int = -1

    def append(self, emission: Emission) -> None:
        if emission.state_namespace != self.namespace:
            raise ImmutableTapeViolation(
                f"emission namespace {emission.state_namespace!r} does not belong on tape "
                f"{self.namespace!r}; a refit gets its OWN namespace (guide 8.4)")
        self.emissions.append(emission)

    def seal(self) -> None:
        """Mark everything written so far as decision-vintage and unrewritable."""
        self._sealed_through = len(self.emissions) - 1

    def overwrite(self, index: int, emission: Emission) -> None:
        if index <= self._sealed_through:
            raise ImmutableTapeViolation(
                f"emission {index} is decision-vintage and cannot be rewritten. A refit's view of "
                "the past belongs in asof_<T>_training_labels, a separate series (guide 8.4)")
        self.emissions[index] = emission

    def states(self) -> np.ndarray:
        return np.asarray([e.state_id for e in self.emissions], dtype=np.int64)

    def switches(self) -> int:
        """Counted from the emitted tape, never inferred from the model's jump penalty."""
        states = self.states()
        return int(np.count_nonzero(states[1:] != states[:-1])) if states.size > 1 else 0

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.emission_tape.v1",
            "state_namespace": self.namespace,
            "emissions": [e.as_record() for e in self.emissions],
            "count": len(self.emissions),
            "sealed_through": self._sealed_through,
            "switch_count": self.switches(),
            "switch_count_rule": ("counted from the EMITTED tape. The model's lambda_jump is not "
                                  "the policy's switching cost and must not be used to infer it "
                                  "(guide 8.4)"),
            "append_only": True,
        }


class OnlineStateFilter:
    """Streaming form of guide 8.4, one observation at a time.

    It holds only ``Q_{t-1}`` and the model. Feeding it a sequence one step at a
    time must give exactly what the batch filter gives on the same prefix -- that
    equality is T38, and it is the difference between a provider that can run live
    and one that only looks like it can.
    """

    def __init__(self, centroids: np.ndarray, weights: np.ndarray, lambda_jump: float, *,
                 namespace: str, normalise: bool = True) -> None:
        self.centroids = np.asarray(centroids, dtype=np.float64)
        self.weights = np.asarray(weights, dtype=np.float64)
        self.lambda_jump = float(lambda_jump)
        self.namespace = namespace
        self.normalise = bool(normalise)
        if self.lambda_jump < 0:
            raise JumpModelError("lambda_jump must be nonnegative")
        self._previous: np.ndarray | None = None
        self._offset = 0.0
        self.n_states = self.centroids.shape[0]

    @property
    def observations_seen(self) -> int:
        return 0 if self._previous is None else 1

    def step(self, z_t: np.ndarray) -> tuple[int, np.ndarray, np.ndarray]:
        """Consume one observation; return (state, normalised costs, raw costs).

        No future observation is available to this function by construction, which
        is the strongest form the causality guarantee can take.
        """
        z_t = np.asarray(z_t, dtype=np.float64).reshape(1, -1)
        loss = loss_matrix(z_t, self.centroids, self.weights)[0]
        if self._previous is None:
            costs = loss.copy()
        else:
            previous = self._previous
            order = np.argsort(previous, kind="stable")
            best_j = int(order[0])
            second_j = int(order[1]) if self.n_states > 1 else best_j
            costs = np.empty(self.n_states, dtype=np.float64)
            for k in range(self.n_states):
                other = second_j if k == best_j else best_j
                stay = previous[k]
                switch = previous[other] + self.lambda_jump
                costs[k] = loss[k] + (stay if stay <= switch else switch)
        raw = costs + self._offset
        if self.normalise:
            shift = float(costs.min())
            costs = costs - shift
            self._offset += shift
        self._previous = costs
        return int(np.argmin(costs)), costs, raw


def build_emission(state_id: int, costs: np.ndarray, *, namespace: str, z_t: np.ndarray,
                   centroids: np.ndarray, weights: np.ndarray, groups: dict,
                   observed_at: str, available_at: str, inferred_at: str,
                   model_fit_cutoff: str, ready_at: str, version: str,
                   quality_status: str = QUALITY_OK,
                   input_refs: tuple[str, ...] = (),
                   novelty_score: float = 0.0,
                   decision_eligible: bool = True) -> Emission:
    """Assemble one emission with the fields guide 8.5 requires."""
    if quality_status not in QUALITY_STATUSES:
        raise JumpModelError(f"unknown quality status {quality_status!r}")
    z_t = np.asarray(z_t, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    residual = z_t - np.asarray(centroids, dtype=np.float64)[state_id]
    per_feature = 0.5 * weights * residual * residual
    group_contributions: dict[str, float] = {}
    for name, indices in groups.items():
        group_contributions[name] = float(per_feature[list(indices)].sum())
    gap = float(second_best_gap(np.asarray(costs).reshape(1, -1))[0])
    return Emission(
        state_id=int(state_id), state_namespace=namespace,
        state_costs=tuple(float(c) for c in costs), second_best_gap=gap,
        fit_residual=float(per_feature.sum()), novelty_score=float(novelty_score),
        feature_contributions=tuple(float(c) for c in per_feature),
        group_contributions=group_contributions,
        observed_at=observed_at, available_at=available_at, inferred_at=inferred_at,
        model_fit_cutoff=model_fit_cutoff, ready_at=ready_at, version=version,
        quality_status=quality_status, input_refs=tuple(input_refs),
        membership_score=tuple(float(m) for m in membership_scores(np.asarray(costs))),
        membership_is_calibrated=False,
        economic_context=tuple(float(v) for v in z_t.reshape(-1)),
        decision_eligible=decision_eligible)


def batch_stream_parity(z: np.ndarray, centroids: np.ndarray, weights: np.ndarray,
                        lambda_jump: float, *, namespace: str = "parity") -> dict:
    """T38 — streaming one observation at a time must equal the batch filter at EVERY prefix."""
    from .jump_model import forward_filter

    z = np.asarray(z, dtype=np.float64)
    batch = forward_filter(loss_matrix(z, centroids, weights), lambda_jump, normalise=True)

    streamer = OnlineStateFilter(centroids, weights, lambda_jump, namespace=namespace)
    stream_states, stream_costs = [], []
    for t in range(z.shape[0]):
        state, costs, _ = streamer.step(z[t])
        stream_states.append(state)
        stream_costs.append(costs.copy())
    stream_states = np.asarray(stream_states, dtype=np.int64)
    stream_costs = np.vstack(stream_costs)

    # and every PREFIX re-run from scratch must agree with the same prefix of the full run
    prefix_mismatch = []
    for length in range(1, z.shape[0] + 1):
        prefix = forward_filter(loss_matrix(z[:length], centroids, weights), lambda_jump,
                                normalise=True)
        if not np.array_equal(prefix.online_states, batch.online_states[:length]):
            prefix_mismatch.append(length)

    return {
        "schema": "crypto_regime_lab.batch_stream_parity.v1",
        "observations": int(z.shape[0]),
        "states_identical": bool(np.array_equal(batch.online_states, stream_states)),
        "costs_identical": bool(np.allclose(batch.costs, stream_costs, rtol=0, atol=0)),
        "prefix_vintages_stable": prefix_mismatch == [],
        "prefix_mismatches_at": prefix_mismatch,
        "rule": ("a label emitted at t must be the same whether the provider was run live, "
                 "restarted on the prefix, or run in one batch. Otherwise 'the model said X at "
                 "time t' has no fixed meaning (guide 8.4, T38)"),
    }
