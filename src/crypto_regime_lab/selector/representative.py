"""L04.4 — choosing the representative of a robust set (guide 7.3).

    theta_medoid = argmin over theta_i in C of sum_j d(theta_i, theta_j)

Three rules the guide states and this module enforces:

  * the medoid is chosen only from candidates that were actually EVALUATED and
    are eligible — a geometric centre that nobody ran is not deployable (T33);
  * ties break deterministically on the stable candidate id (T34);
  * the medoid does NOT replace R or the local probes; it picks a representative
    from among points that already passed them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .schema_distance import ParamSchema, ParamSpec


@dataclass
class Representative:
    candidate_id: str
    params: dict
    total_distance: float
    method: str
    tie_broken_on_id: bool
    considered: list[str]

    def as_record(self) -> dict:
        return self.__dict__.copy()


class NotEvaluated(ValueError):
    """Raised when a proposed representative was never evaluated."""


def centroid_point(schema: ParamSchema, points: list[dict]) -> dict:
    """The geometric centre of a set. It is a PROPOSAL, never a deployable choice.

    A centroid usually lands on a point nobody evaluated; guide 7.3 forbids
    deploying it before it has been run. Three details matter and were wrong in
    the first version:

    * a tie between categorical values was broken by ``set`` iteration order,
      which is salted per interpreter, so the "centre" could differ between runs;
    * a ``log``-scaled parameter was averaged linearly even though its distance is
      measured in log space, which put the centre in a different place from the
      geometry that chose it;
    * integer rounding could collapse an ordered pair onto itself and produce a
      point the schema declares infeasible.

    The result is snapped to the declared grid, clamped to the declared bounds and
    ordered to respect declared dependencies.
    """
    if not points:
        raise ValueError("no points")
    centre: dict[str, Any] = {}
    for name, spec in schema.specs.items():
        values = [p[name] for p in points if name in p]
        if not values:
            continue
        if spec.kind in ("categorical", "bool", "fixed"):
            # deterministic: most common, ties broken on the value's own repr
            centre[name] = max(sorted(set(values), key=repr), key=values.count)
        elif spec.kind == "log":
            # the distance for this kind is measured in log space, so the centre is
            # the geometric mean, not the arithmetic one
            centre[name] = math.exp(
                sum(math.log(float(v)) for v in values) / len(values))
        elif spec.kind == "int":
            centre[name] = int(round(sum(float(v) for v in values) / len(values)))
        else:
            centre[name] = sum(float(v) for v in values) / len(values)
        centre[name] = _snap(spec, centre[name])
    _enforce_dependencies(schema, centre)
    return centre


def _snap(spec: ParamSpec, value: Any) -> Any:
    """Put a value on the declared grid and inside the declared bounds."""
    if spec.kind in ("categorical", "bool", "fixed"):
        return value
    low, high = float(spec.low), float(spec.high)
    number = min(max(float(value), low), high)
    step = float(spec.step) if spec.step else None
    if step and step > 0 and spec.kind in ("int", "float"):
        number = low + round((number - low) / step) * step
        number = min(max(number, low), high)
    if spec.kind == "int":
        return int(round(number))
    return float(number)


def _enforce_dependencies(schema: ParamSchema, point: dict) -> None:
    """Keep a declared ordered pair ordered after rounding.

    Averaging two ordered points then rounding can collapse them onto the same
    grid value, which would hand back a centroid the schema itself calls
    infeasible. Push the upper member up by one declared step instead.
    """
    for lower, upper in schema.dependencies:
        if lower not in point or upper not in point:
            continue
        if float(point[lower]) < float(point[upper]):
            continue
        spec_u = schema.specs[upper]
        step = float(spec_u.step) if spec_u.step else 1.0
        raised = float(point[lower]) + step
        if raised <= float(spec_u.high):
            point[upper] = _snap(spec_u, raised)
        else:
            spec_l = schema.specs[lower]
            step_l = float(spec_l.step) if spec_l.step else 1.0
            point[lower] = _snap(spec_l, float(point[upper]) - step_l)


def assert_evaluated(point: dict, evaluated: list[dict]) -> None:
    if point not in evaluated:
        raise NotEvaluated(
            "the proposed representative was never evaluated; guide 7.3 requires a new centroid "
            "to be run before it can be selected"
        )


def medoid(schema: ParamSchema, candidates: dict[str, dict]) -> Representative:
    """Medoid over the feasible, evaluated, eligible candidate set."""
    if not candidates:
        raise ValueError("the eligible candidate set is empty")
    ids = sorted(candidates)
    totals: dict[str, float] = {}
    for a in ids:
        totals[a] = sum(schema.distance(candidates[a], candidates[b]) for b in ids if b != a)
    best = min(totals.values())
    winners = [i for i in ids if abs(totals[i] - best) <= 1e-12]
    chosen = winners[0]                      # deterministic: lowest stable id
    return Representative(candidate_id=chosen, params=candidates[chosen],
                          total_distance=totals[chosen], method="medoid_sum_of_distances",
                          tie_broken_on_id=len(winners) > 1, considered=ids)


def choose_representative(schema: ParamSchema, eligible: dict[str, dict],
                          evaluated_points: list[dict]) -> dict:
    """Pick the representative and record the centroid as a proposal only."""
    rep = medoid(schema, eligible)
    centre = centroid_point(schema, list(eligible.values()))
    centre_evaluated = centre in evaluated_points
    return {
        "schema": "crypto_regime_lab.representative.v1",
        "medoid": rep.as_record(),
        "centroid_proposal": centre,
        "centroid_was_evaluated": centre_evaluated,
        "centroid_deployable": centre_evaluated,
        "centroid_feasible": schema.is_feasible(centre)[0],
        "centroid_infeasible_reason": schema.is_feasible(centre)[1],
        "centroid_rule": (
            "a centroid that has not been evaluated is a proposal, not a selection; it must be run "
            "before it can be deployed (guide 7.3)"
        ),
        "medoid_rule": (
            "the medoid minimises the summed schema distance to the other ELIGIBLE candidates and "
            "does not replace R or the local probes"
        ),
        "tie_break": "lowest stable candidate id",
    }
