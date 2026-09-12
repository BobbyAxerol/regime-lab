"""Guide 13.1 — the research-record identity taxonomy, and how each ID is made.

Guide 13.1 opens with "Không gộp trial/candidate/execution/selection/activation
thành một ID": do not collapse them. The reason is joins. In LAB-08 and LAB-09 a
result has to be traceable back through the selection that proposed it, the
execution that measured it, the probe design that framed it and the regime
observation that conditioned it. If two of those share an ID, or one has none,
the join is made later on whatever key happens to be lying around -- and a join
invented after the numbers exist is a place where the numbers can be steered.

Seven of the twelve identities were already in the artifacts. Three that
COMPLETED phases owe were not: ``probe_design_id`` (L04.3 freezes a design),
``execution_id`` (L04.3 counted 9,155 unique executions without naming any) and
``observation_id`` (L05 emitted 1,099 observations without naming any). They are
added here as DERIVATIONS rather than as new stored fields, so an artifact that
already exists gets its identity without being re-run and without a measurement
moving.

The remaining two, ``experiment_id`` and ``activation_id``, belong to phases that
have not run; they are declared here with their owner so LAB-07/08 inherit the
contract instead of inventing one.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: identity -> (what it names, the phase that must mint it)
TAXONOMY: dict[str, dict[str, str]] = {
    "study_id": {"names": "the research protocol", "owner": "LAB-01"},
    "experiment_id": {"names": "arm + cell + cohort + config version", "owner": "LAB-08"},
    "trial_id": {"names": "one optimizer proposal instance", "owner": "LAB-04"},
    "candidate_id": {"names": "strategy version + typed effective params", "owner": "LAB-04"},
    "execution_id": {"names": "candidate + market + initial state + economics + seed",
                     "owner": "LAB-04"},
    "probe_design_id": {"names": "a local validation design, independent of the sampler",
                        "owner": "LAB-04"},
    "model_id": {"names": "a fit artifact: features, scaler, centroids, state namespace",
                 "owner": "LAB-05"},
    "observation_id": {"names": "one decision-vintage regime emission", "owner": "LAB-05"},
    "response_id": {"names": "a conditional estimate plus its supporting episodes",
                    "owner": "LAB-06"},
    "selection_id": {"names": "an evidence-based keep/switch proposal", "owner": "LAB-06"},
    "activation_id": {"names": "the params actually in force at a timestamp/phase",
                      "owner": "LAB-07"},
    "attempt_id": {"names": "one run or retry of an operation", "owner": "LAB-01"},
}


def _digest(kind: str, payload: dict[str, Any], *, width: int = 16) -> str:
    """A content-addressed identity: same inputs, same ID, on any machine.

    ``sort_keys`` and ``default=str`` matter. A dict's insertion order and a
    Timestamp's repr are both incidental, and letting either reach the hash
    would make the ID depend on how the record was built rather than on what it
    says -- which is the one thing an identity must not do.
    """
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{kind}-{hashlib.sha256(body.encode()).hexdigest()[:width]}"


def probe_design_id(*, alpha_id: str, symbol: str, cutoff: Any, seed: int,
                    anchors: int, probes_per_anchor: int, radius: float,
                    space_filling_anchors: int = 0) -> str:
    """L04.3 — names the DESIGN, not the points it produced.

    Deliberately excludes the sampled points: the design is what was frozen
    before evaluation, and an ID that changed with the outcome would describe
    the result rather than the plan.
    """
    return _digest("pd", {
        "alpha_id": alpha_id, "symbol": symbol, "cutoff": cutoff, "seed": seed,
        "anchors": anchors, "probes_per_anchor": probes_per_anchor,
        "radius": radius, "space_filling_anchors": space_filling_anchors,
    })


def execution_id(*, candidate_id: str, symbol: str, interval: str, start: Any, end: Any,
                 initial_state: str, economics: dict, seed: int | None = None) -> str:
    """L04.3 — guide 13.1: candidate + market + initial state + economics + seed.

    Economics is part of the identity on purpose. The same candidate over the
    same bars at a different fee is a DIFFERENT measurement, and giving both the
    same name is how a cost-stress result gets compared against a headline one.
    """
    return _digest("ex", {
        "candidate_id": candidate_id, "symbol": symbol, "interval": interval,
        "start": start, "end": end, "initial_state": initial_state,
        "economics": economics, "seed": seed,
    })


def observation_id(*, model_id: str, state_namespace: str, observed_at: Any,
                   available_at: Any) -> str:
    """L05 — one decision-vintage emission.

    Carries BOTH timestamps. The same bar re-emitted by a later model version is
    a different observation, and ``available_at`` is what a policy is allowed to
    act on, so an identity that dropped it could not distinguish a legitimate
    re-read from a backdated one.
    """
    return _digest("ob", {
        "model_id": model_id, "state_namespace": state_namespace,
        "observed_at": observed_at, "available_at": available_at,
    })


#: identities a completed phase owed, now reconstructible from records that
#: already exist rather than back-filled into them.
DERIVABLE = ("probe_design_id", "execution_id", "observation_id")


def _status(name: str, present: dict[str, list[str]]) -> str:
    """Three states, not two. Collapsing them is what hid the gap in the first place.

    PRESENT   the identity is stored in an artifact.
    DERIVABLE the phase that owed it has run, and the identity is reconstructible
              from what that run recorded -- so nothing is repeated and no
              measurement moves, but it is not yet a stored field.
    OWED      the minting phase has not run.
    """
    if present.get(name):
        return "PRESENT"
    return "DERIVABLE" if name in DERIVABLE else "OWED"


def experiment_id(*, arm: str, alpha_id: str, symbol: str, cohort: str,
                  config_version: str) -> str:
    """LAB-08 — guide 13.1: arm + cell + cohort + config version.

    The config version is part of the identity because the same arm on the same
    cell under a different frozen protocol is a different experiment, and giving
    both the same name is how two runs under different rules come to be compared.
    """
    return _digest("ex-p", {"arm": arm, "alpha_id": alpha_id, "symbol": symbol,
                            "cohort": cohort, "config_version": config_version})


def taxonomy_status(present: dict[str, list[str]]) -> dict:
    """Report which identities exist, where, and which phase still owes one."""
    identities = {
        name: {**spec, "status": _status(name, present), "found_in": present.get(name, [])}
        for name, spec in TAXONOMY.items()
    }
    return {
        "schema": "crypto_regime_lab.identity_taxonomy.v1",
        "guide_section": "13.1",
        "rule": ("trial / candidate / execution / selection / activation are never collapsed "
                 "into one ID; a missing identity is recorded as owed, never improvised at "
                 "join time"),
        "identities": identities,
        "present_count": sum(1 for r in identities.values() if r["status"] == "PRESENT"),
        "derivable_count": sum(1 for r in identities.values() if r["status"] == "DERIVABLE"),
        "owed_count": sum(1 for r in identities.values() if r["status"] == "OWED"),
        "total": len(TAXONOMY),
    }
