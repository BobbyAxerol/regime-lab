"""L04.3 — candidate-independent local probes (guide 7.2).

The probe design is frozen BEFORE any outcome is seen: radius, count and seed.
It is deliberately independent of the optimizer's own sampling, because TPE
concentrates where it already found value and its density is therefore not
evidence of stability (guide 7.1).

Three accounting rules the guide is explicit about, enforced here:

  * every VALID probe stays in the denominator, including the losing ones;
  * a STRUCTURALLY INVALID point is not bad performance — it is excluded with a
    reason and never counted as a loss;
  * a RUNTIME ERROR makes the panel incomplete; it does not become a zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
import numpy as np

from .schema_distance import ParamSchema

# Frozen design constants. Changing one is a registered design decision.
DEFAULT_RADIUS = 0.12          # in schema distance units
DEFAULT_PROBES_PER_ANCHOR = 8
DEFAULT_SEED = 20260910


class ProbeStatus:
    EVALUATED = "EVALUATED"
    STRUCTURALLY_INVALID = "STRUCTURALLY_INVALID"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    DUPLICATE = "DUPLICATE"


@dataclass
class Probe:
    point: dict
    anchor_id: str
    distance_to_anchor: float
    status: str = ProbeStatus.EVALUATED
    reason: str | None = None

    @property
    def probe_id(self) -> str:
        payload = json.dumps(self.point, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def as_record(self) -> dict:
        return {"probe_id": self.probe_id, "point": self.point, "anchor_id": self.anchor_id,
                "distance_to_anchor": self.distance_to_anchor, "status": self.status,
                "reason": self.reason}


@dataclass
class ProbeDesign:
    """A frozen local design around a set of anchors."""

    schema: ParamSchema
    radius: float = DEFAULT_RADIUS
    probes_per_anchor: int = DEFAULT_PROBES_PER_ANCHOR
    seed: int = DEFAULT_SEED
    max_attempts_multiplier: int = 40
    frozen_at: str | None = None
    _rejections: list[dict] = field(default_factory=list, repr=False)

    def design_digest(self) -> str:
        payload = json.dumps({"radius": self.radius, "probes": self.probes_per_anchor,
                              "seed": self.seed, "schema": self.schema.as_record()},
                             sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # -- proposal ---------------------------------------------------------

    def _perturb(self, anchor: dict, rng: np.random.Generator) -> dict:
        """Move a few active dimensions onto neighbouring GRID values.

        Dependent pairs are re-ordered by construction rather than repaired after
        sampling, so the manifold is respected instead of patched (guide 7.1).
        """
        point = dict(anchor)
        # sorted(): set iteration over str is salted per process too, so an
        # unsorted list here would undo the stable seed above.
        active = sorted(n for n in self.schema.active_params(anchor)
                        if self.schema.specs[n].informative)
        if not active:
            return point
        k = int(rng.integers(1, min(3, len(active)) + 1))
        for name in rng.choice(active, size=k, replace=False):
            spec = self.schema.specs[str(name)]
            grid = spec.grid()
            if len(grid) <= 1:
                continue
            try:
                here = grid.index(point[str(name)])
            except ValueError:
                here = int(rng.integers(0, len(grid)))
            offset = int(rng.integers(1, 3)) * (1 if rng.random() < 0.5 else -1)
            point[str(name)] = grid[int(np.clip(here + offset, 0, len(grid) - 1))]
        for lower, upper in self.schema.dependencies:
            if lower in point and upper in point and float(point[lower]) >= float(point[upper]):
                point[lower], point[upper] = (min(float(point[lower]), float(point[upper])),
                                              max(float(point[lower]), float(point[upper])))
                spec_l, spec_u = self.schema.specs[lower], self.schema.specs[upper]
                if spec_l.kind == "int":
                    point[lower] = int(round(point[lower]))
                if spec_u.kind == "int":
                    point[upper] = int(round(point[upper]))
                if float(point[lower]) >= float(point[upper]):
                    return {}          # cannot be made feasible; caller records it
        return point

    def _anchor_seed(self, anchor_id: str) -> int:
        """A per-anchor seed that is stable ACROSS processes.

        ``hash()`` on a str is salted per interpreter unless PYTHONHASHSEED is
        pinned, so using it here would have made a "frozen" design produce a
        different probe set on every run. Derive the stream from a digest instead.
        """
        digest = hashlib.sha256(f"{self.seed}|{anchor_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big")

    def probes_for(self, anchor: dict, anchor_id: str) -> list[Probe]:
        """Unique, feasible probes inside the frozen radius around one anchor."""
        rng = np.random.default_rng(self._anchor_seed(anchor_id))
        probes: list[Probe] = []
        seen: set[str] = set()
        anchor_probe = Probe(point=dict(anchor), anchor_id=anchor_id, distance_to_anchor=0.0)
        seen.add(anchor_probe.probe_id)

        attempts = 0
        limit = self.probes_per_anchor * self.max_attempts_multiplier
        while len(probes) < self.probes_per_anchor and attempts < limit:
            attempts += 1
            candidate = self._perturb(anchor, rng)
            if not candidate:
                self._rejections.append({"anchor_id": anchor_id, "reason": "dependency_unsatisfiable"})
                continue
            feasible, reason = self.schema.is_feasible(candidate)
            if not feasible:
                self._rejections.append({"anchor_id": anchor_id, "point": candidate,
                                         "reason": reason,
                                         "status": ProbeStatus.STRUCTURALLY_INVALID})
                continue
            distance = self.schema.distance(anchor, candidate)
            if distance == 0.0 or distance > self.radius:
                continue
            probe = Probe(point=candidate, anchor_id=anchor_id, distance_to_anchor=distance)
            if probe.probe_id in seen:
                continue
            seen.add(probe.probe_id)
            probes.append(probe)
        return probes

    def build(self, anchors: dict[str, dict]) -> dict:
        """Build the full design. Anchors are included as their own centre points."""
        design: dict[str, list[Probe]] = {}
        for anchor_id, anchor in anchors.items():
            feasible, reason = self.schema.is_feasible(anchor)
            if not feasible:
                self._rejections.append({"anchor_id": anchor_id, "point": anchor,
                                         "reason": f"anchor infeasible: {reason}",
                                         "status": ProbeStatus.STRUCTURALLY_INVALID})
                design[anchor_id] = []
                continue
            design[anchor_id] = self.probes_for(anchor, anchor_id)
        total = sum(len(v) for v in design.values())
        return {
            "schema": "crypto_regime_lab.probe_design.v1",
            "design_digest": self.design_digest(),
            "radius": self.radius,
            "probes_per_anchor": self.probes_per_anchor,
            "seed": self.seed,
            "anchors": {k: v for k, v in anchors.items()},
            "probes": {k: [p.as_record() for p in v] for k, v in design.items()},
            "probe_count": total,
            "unique_probe_ids": len({p.probe_id for v in design.values() for p in v}),
            "structurally_invalid_rejections": self._rejections,
            "accounting_rules": {
                "valid_bad_probes_retained": True,
                "structurally_invalid_is_not_bad_performance": True,
                "runtime_error_means_incomplete_evidence": True,
            },
            "independence_note": (
                "this design does not read the optimizer's sampling density; TPE concentrates "
                "where it already found value, so its density is not evidence of stability"
            ),
        }
