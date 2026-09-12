"""L09.4 — the stresses a confirmation has to survive to mean anything.

Two kinds live here, and they are different in an important way.

ECONOMIC stress re-runs the account with the costs multiplied. It is exact rather
than approximate because the sizing is fixed-notional: position size does not
depend on the equity path, so a stressed run is a real engine pass and not an
arithmetic adjustment applied afterwards. The 1.0x level is kept in the panel on
purpose -- it must reproduce the recorded equity to the bit, and if it does not,
the harness is wrong and nothing else in the panel can be believed.

INFORMATION stress corrupts the state tape the dynamic arms read: transitions
labelled at the wrong time, a feed that stops updating, an enrichment product
that goes missing. Each one produces a different refresh schedule, and the arm is
re-run on it. What is NOT re-run is the selection under stressed economics --
holding the selections fixed is the "frozen sensitivity" the guide permits, and
it is a real limitation rather than a detail: a selector that re-scored its
candidates at 2x costs might have chosen differently.

Nothing here retunes anything. A stress that loses is a result (L09.4.6).
"""

from __future__ import annotations

import contextlib

import numpy as np

from .evaluator import ACCOUNT


class StressError(RuntimeError):
    """Raised when a stress would not be comparable to the run it stresses."""


@contextlib.contextmanager
def scaled_costs(multiplier: float, *, fee_multiplier: float | None = None,
                 slippage_multiplier: float | None = None):
    """Run the block with the transaction costs multiplied.

    By default both components move together: the taker fee and the slippage.
    Scaling only the fee would understate the stress on a high-turnover arm,
    because slippage is charged per fill in the price and the fee is charged on
    notional.

    The per-component overrides exist for ONE named reason, and it is not a
    tuning knob. `scripts/verify_cost_binding.py` measures that the engine is
    charging half the registered one-way taker fee -- the registered one-way rate
    is passed into a parameter the engine documents as round-trip -- so the
    account the study REGISTERED is reproduced at fee x2 and slippage x1, and
    that level has to be addressable separately from a uniform stress.
    """
    if multiplier <= 0:
        raise StressError(f"a cost multiplier must be positive, not {multiplier}")
    fee_scale = multiplier if fee_multiplier is None else fee_multiplier
    slip_scale = multiplier if slippage_multiplier is None else slippage_multiplier
    if fee_scale <= 0 or slip_scale <= 0:
        raise StressError("a per-component cost multiplier must be positive")
    original = {"taker_fee_rate": ACCOUNT["taker_fee_rate"],
                "slippage_bps": ACCOUNT["slippage_bps"]}
    ACCOUNT["taker_fee_rate"] = original["taker_fee_rate"] * fee_scale
    ACCOUNT["slippage_bps"] = original["slippage_bps"] * slip_scale
    try:
        yield {"taker_fee_rate": ACCOUNT["taker_fee_rate"],
               "slippage_bps": ACCOUNT["slippage_bps"], "multiplier": multiplier,
               "fee_multiplier": fee_scale, "slippage_multiplier": slip_scale}
    finally:
        ACCOUNT.update(original)


def transitions_in(emissions: list[dict]) -> list[int]:
    """Positions where the state changes, counted within a namespace.

    A model refit starts a new namespace, and a state id in one namespace is not
    the same state as the same integer in another (guide 8.4), so a namespace
    boundary is not a transition.
    """
    out = []
    for i in range(1, len(emissions)):
        previous, current = emissions[i - 1], emissions[i]
        if previous["state_namespace"] != current["state_namespace"]:
            continue
        if previous["state_id"] != current["state_id"]:
            out.append(i)
    return out


def mislabelled_transitions(emissions: list[dict], *, fraction: float, shift: int,
                            seed: int) -> tuple[list[dict], dict]:
    """Move a fraction of the transitions in time, keeping the state sequence.

    This is the realistic failure: the model finds the right regimes but dates
    the change wrong. It is strictly harder to detect than a wrong label, and it
    is what a dynamic arm is most exposed to, because the arm acts ON the
    transition. The state VALUES are untouched, so any difference in the result
    is attributable to timing alone.
    """
    if not 0.0 <= fraction <= 1.0:
        raise StressError(f"fraction must be in [0, 1], not {fraction}")
    rng = np.random.default_rng(seed)
    tape = [dict(e) for e in emissions]
    points = transitions_in(emissions)
    if not points:
        return tape, {"transitions": 0, "moved": 0,
                      "reason": "the tape has no within-namespace transition to move"}
    chosen = rng.choice(points, size=max(1, int(round(len(points) * fraction))),
                        replace=False)
    moved = 0
    for point in sorted(chosen):
        direction = int(rng.choice([-1, 1]))
        target = point + direction * shift
        low, high = min(point, target), max(point, target)
        if low < 1 or high >= len(tape):
            continue
        # rewrite the run boundary: the state that starts at `point` now starts at
        # `target`, and only inside one namespace
        namespace = tape[point]["state_namespace"]
        if any(tape[i]["state_namespace"] != namespace for i in range(low, high + 1)):
            continue
        new_state = tape[point]["state_id"]
        old_state = tape[point - 1]["state_id"]
        for i in range(low, high + 1):
            tape[i]["state_id"] = new_state if direction < 0 else old_state
        moved += 1
    return tape, {
        "transitions": len(points),
        "transitions_after": len(transitions_in(tape)),
        "selected": int(len(chosen)),
        "moved": moved,
        "positions_that_differ": int(sum(1 for a, b in zip(emissions, tape)
                                         if a["state_id"] != b["state_id"])),
        "shift_observations": shift,
        "fraction": fraction,
        "state_values_unchanged": True,
        "what_it_isolates": ("the model finds the right regimes and dates them wrong. Only the "
                             "timing of each change moves; the sequence of states does not"),
    }


def stale_feed(emissions: list[dict], *, stale_runs: int, run_observations: int,
               seed: int) -> tuple[list[dict], dict]:
    """Freeze the tape for several stretches: the provider stops updating.

    A stale feed is not a delayed feed. A delay shifts everything; staleness holds
    one value while the world moves and then jumps. The jump is the part that
    matters, because a dynamic arm reads it as a transition.
    """
    rng = np.random.default_rng(seed)
    tape = [dict(e) for e in emissions]
    if len(tape) < stale_runs * run_observations * 2:
        raise StressError("the tape is too short to carry that many stale stretches")
    starts = sorted(rng.choice(np.arange(1, len(tape) - run_observations),
                               size=stale_runs, replace=False))
    frozen = 0
    for start in starts:
        held = tape[start - 1]
        for i in range(start, min(start + run_observations, len(tape))):
            if tape[i]["state_namespace"] != held["state_namespace"]:
                break
            tape[i] = {**tape[i], "state_id": held["state_id"],
                       "quality_status": "STALE_FEED"}
            frozen += 1
    return tape, {
        "stale_stretches": stale_runs,
        "observations_per_stretch": run_observations,
        "observations_frozen": frozen,
        "share_of_tape_frozen": frozen / len(tape),
        "what_it_isolates": ("a provider that stops updating and then catches up in one step. "
                             "The catch-up looks like a transition to any arm that acts on one"),
    }


def missing_enrichment(emissions: list[dict], *, outages: int, outage_observations: int,
                       seed: int) -> tuple[list[dict], dict]:
    """The enrichment product is unavailable for several stretches.

    Dropped, not zeroed. A missing observation booked as a value is the defect
    the read-lock review already found in the volume column, and an arm that
    reads a fabricated zero is being told something false rather than nothing.

    The outages are CONTIGUOUS, and that is the correction rather than a detail.
    An earlier version dropped a random 20% of observations independently, and
    the resulting refresh schedule came out IDENTICAL to the real one on every
    cutoff -- because removing scattered rows almost never moves where the first
    transition of a period falls. The stress ran, cost an hour, and could not
    have produced a different answer. A real enrichment product fails for
    stretches, and a stretch that covers a transition does move the schedule.
    """
    if outages < 1 or outage_observations < 1:
        raise StressError("an outage needs a count and a length")
    rng = np.random.default_rng(seed)
    if len(emissions) < outages * outage_observations * 2:
        raise StressError("the tape is too short to carry that many outages")
    starts = sorted(rng.choice(np.arange(0, len(emissions) - outage_observations),
                               size=outages, replace=False))
    dropped = set()
    for start in starts:
        dropped.update(range(start, min(start + outage_observations, len(emissions))))
    tape = [dict(e) for i, e in enumerate(emissions) if i not in dropped]
    if len(tape) < 10:
        raise StressError("those outages leave no tape")
    return tape, {
        "outages": outages,
        "observations_per_outage": outage_observations,
        "rows_before": len(emissions),
        "rows_after": len(tape),
        "rows_dropped": int(len(emissions) - len(tape)),
        "share_dropped": (len(emissions) - len(tape)) / len(emissions),
        "outage_starts": [int(x) for x in starts],
        "contiguous": True,
        "dropped_not_zeroed": True,
        "what_it_isolates": ("the provider is silent for a stretch. The arm sees a gap, never a "
                             "fabricated value, and a gap that covers a transition moves the "
                             "refresh that would have followed it"),
    }


def label_permutation(emissions: list[dict], *, seed: int) -> tuple[list[dict], dict]:
    """Permute the state ids WITHIN each namespace (L09.5.3).

    A jump model's state ids are arbitrary labels. Any decision rule that reads
    the id itself -- rather than what the state predicts -- would change its
    behaviour under this permutation, and that is the bug it is designed to
    expose. A refresh schedule built from WHERE the state changes should not move
    at all.
    """
    rng = np.random.default_rng(seed)
    by_namespace: dict[str, dict[int, int]] = {}
    tape = []
    for emission in emissions:
        namespace = emission["state_namespace"]
        if namespace not in by_namespace:
            ids = sorted({e["state_id"] for e in emissions
                          if e["state_namespace"] == namespace})
            by_namespace[namespace] = dict(zip(ids, rng.permutation(ids)))
        tape.append({**emission,
                     "state_id": int(by_namespace[namespace][emission["state_id"]])})
    identical_transitions = transitions_in(tape) == transitions_in(emissions)
    return tape, {
        "namespaces_permuted": len(by_namespace),
        "transition_positions_unchanged": identical_transitions,
        "expected": ("a schedule built from WHERE the state changes must be identical. A "
                     "difference means something downstream reads the label itself"),
    }


def ambiguity_profile(tape_record: dict, *, reference_p10: float | None = None) -> dict:
    """Mixed and ambiguous states (L09.5.2), measured on what the model emitted.

    `second_best_gap` is the margin between the chosen state and the runner-up.
    A small gap is an observation the model could nearly as well have labelled
    differently, and it is where a label-driven decision is least supported.
    """
    gaps, statuses = [], {}
    for record in tape_record.get("namespaces", {}).values():
        for emission in record.get("emissions", []):
            gap = emission.get("second_best_gap")
            if gap is not None:
                gaps.append(float(gap))
            status = emission.get("quality_status")
            statuses[status] = statuses.get(status, 0) + 1
    if not gaps:
        return {"observations": 0, "status": "NO_GAP_RECORDED"}
    array = np.asarray(gaps, dtype=float)
    threshold = float(np.quantile(array, 0.10))
    out = {
        "observations": int(len(array)),
        "median_second_best_gap": float(np.median(array)),
        "p10_second_best_gap": threshold,
        "quality_status_counts": statuses,
        "reading": ("the margin between the chosen state and the runner-up. The bottom decile is "
                    "where the label is close to arbitrary, and a decision that reads the label "
                    "is least supported there"),
    }
    if reference_p10 is not None:
        # the interesting question is not "is a tenth of this tape ambiguous" -- that
        # is true of any tape by construction -- but "is this tape MORE ambiguous than
        # the one the design was built on"
        out["reference_p10_from_development"] = float(reference_p10)
        out["share_below_development_p10"] = float((array < reference_p10).mean())
        out["more_ambiguous_than_development"] = bool(
            out["share_below_development_p10"] > 0.10)
    return out
