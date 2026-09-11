"""L04.3 — parameter-space geometry from the DECLARED schema (guide 7.1).

The distance is Gower-like over the parameters that are ACTIVE in both points:

    d(theta, phi) = sum_{j in A} w_j d_j(theta_j, phi_j) / sum_{j in A} w_j

Four properties the guide insists on, each enforced here and tested:

  * numeric/log/int distances are normalised by the DECLARED bounds and step, not
    by the span of whatever happened to be sampled — so adding one far-away
    sample cannot rescale the geometry;
  * a FIXED parameter never enters the denominator: it carries no information and
    would otherwise dilute every distance;
  * an INACTIVE parameter (its conditional branch is off) creates no distance;
  * a conditional BRANCH MISMATCH costs a locked penalty rather than being
    silently skipped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Literal

ParamKind = Literal["int", "float", "log", "categorical", "bool", "fixed"]

# Locked before any result is seen: two points whose conditional branches differ
# are this far apart on that dimension, whatever their values.
BRANCH_MISMATCH_PENALTY = 1.0


class SchemaError(ValueError):
    """Raised for a malformed parameter schema."""


@dataclass(frozen=True)
class ParamSpec:
    """One declared parameter. Bounds come from the SCHEMA, never from samples."""

    name: str
    kind: ParamKind
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: tuple[Any, ...] = ()
    weight: float = 1.0
    active_when: tuple[str, Any] | None = None   # (other_param, required_value)
    fixed_value: Any = None

    def __post_init__(self) -> None:
        if self.kind in ("int", "float", "log"):
            if self.low is None or self.high is None:
                raise SchemaError(f"{self.name}: numeric parameters need declared low and high")
            if self.high < self.low:
                raise SchemaError(f"{self.name}: high < low")
            if self.kind == "log" and self.low <= 0:
                raise SchemaError(f"{self.name}: log parameters need low > 0")
        elif self.kind == "categorical":
            if not self.choices:
                raise SchemaError(f"{self.name}: categorical parameters need choices")
        elif self.kind == "fixed":
            if self.fixed_value is None:
                raise SchemaError(f"{self.name}: fixed parameters need a value")

    @property
    def informative(self) -> bool:
        """A fixed parameter carries no information and must not dilute a distance."""
        return self.kind != "fixed"

    def span(self) -> float:
        if self.kind == "log":
            return math.log(self.high) - math.log(self.low)
        if self.kind in ("int", "float"):
            return float(self.high) - float(self.low)
        return 1.0

    def normalised_distance(self, a: Any, b: Any) -> float:
        """Distance on this dimension alone, in [0, 1]."""
        if self.kind in ("categorical", "bool"):
            return 0.0 if a == b else 1.0
        if self.kind == "fixed":
            return 0.0
        span = self.span()
        if span <= 0:
            return 0.0
        if self.kind == "log":
            raw = abs(math.log(float(a)) - math.log(float(b)))
        else:
            raw = abs(float(a) - float(b))
        return min(1.0, raw / span)

    def grid(self) -> list[Any]:
        """Every feasible value of this dimension under the declared step."""
        if self.kind in ("categorical", "bool"):
            return list(self.choices) if self.choices else [True, False]
        if self.kind == "fixed":
            return [self.fixed_value]
        step = self.step or (1.0 if self.kind == "int" else self.span() / 10.0)
        if self.kind == "log":
            n = max(1, int(round(self.span() / (step if step > 0 else 0.1))))
            return [math.exp(math.log(self.low) + i * self.span() / n) for i in range(n + 1)]
        values: list[Any] = []
        current = float(self.low)
        while current <= float(self.high) + 1e-12:
            values.append(int(round(current)) if self.kind == "int" else current)
            current += step
        return values


@dataclass
class ParamSchema:
    """The declared search space of one alpha, plus its dependency rules."""

    specs: dict[str, ParamSpec]
    dependencies: tuple[tuple[str, str], ...] = ()   # (lower, upper): lower < upper
    name: str = "schema"

    @classmethod
    def from_specs(cls, specs: Iterable[ParamSpec], **kwargs) -> "ParamSchema":
        return cls(specs={s.name: s for s in specs}, **kwargs)

    def active_params(self, point: dict) -> set[str]:
        """Which parameters are active at this point (conditional branches resolved)."""
        active = set()
        for name, spec in self.specs.items():
            if spec.active_when is not None:
                other, required = spec.active_when
                if point.get(other) != required:
                    continue
            active.add(name)
        return active

    def informative_params(self, point: dict) -> set[str]:
        return {n for n in self.active_params(point) if self.specs[n].informative}

    def is_feasible(self, point: dict) -> tuple[bool, str | None]:
        """Structural feasibility. A structurally invalid point is NOT bad performance."""
        for name in self.active_params(point):
            spec = self.specs[name]
            if name not in point:
                return False, f"missing active parameter {name}"
            value = point[name]
            if spec.kind in ("int", "float", "log"):
                if not (spec.low - 1e-12 <= float(value) <= spec.high + 1e-12):
                    return False, f"{name}={value} outside declared bounds"
            elif spec.kind == "categorical" and value not in spec.choices:
                return False, f"{name}={value!r} not a declared choice"
        for lower, upper in self.dependencies:
            if lower in point and upper in point and not float(point[lower]) < float(point[upper]):
                return False, f"dependency violated: {lower} < {upper}"
        return True, None

    def distance(self, a: dict, b: dict) -> float:
        """Gower-like distance over the parameters informative in BOTH points."""
        active_a = self.active_params(a)
        active_b = self.active_params(b)
        branch_mismatch = active_a.symmetric_difference(active_b)
        shared = {n for n in (active_a & active_b) if self.specs[n].informative}

        missing = sorted(n for n in shared if n not in a or n not in b)
        if missing:
            # a KeyError here would surface far from its cause; name the parameter
            raise SchemaError(
                f"{self.name}: cannot measure a distance, these parameters are active but absent "
                f"from one of the points: {missing}. Validate with is_feasible() first."
            )

        numerator = 0.0
        denominator = 0.0
        for name in sorted(shared):        # deterministic float accumulation order
            spec = self.specs[name]
            numerator += spec.weight * spec.normalised_distance(a[name], b[name])
            denominator += spec.weight
        for name in sorted(branch_mismatch):
            spec = self.specs[name]
            if not spec.informative:
                continue
            numerator += spec.weight * BRANCH_MISMATCH_PENALTY
            denominator += spec.weight
        if denominator == 0.0:
            return 0.0
        return numerator / denominator

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.param_schema.v1",
            "name": self.name,
            "parameters": {
                n: {"kind": s.kind, "low": s.low, "high": s.high, "step": s.step,
                    "choices": list(s.choices), "weight": s.weight,
                    "active_when": list(s.active_when) if s.active_when else None,
                    "fixed_value": s.fixed_value, "informative": s.informative}
                for n, s in self.specs.items()
            },
            "dependencies": [list(d) for d in self.dependencies],
            "branch_mismatch_penalty": BRANCH_MISMATCH_PENALTY,
            "distance_rule": (
                "normalised by DECLARED bounds and step; fixed parameters excluded from the "
                "denominator; inactive parameters create no distance; a branch mismatch costs a "
                "locked penalty"
            ),
        }


