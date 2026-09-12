"""L05.1/L05.5 — the model artifact, and mapping state IDs across a refit.

Guide 8.4: "Model A/B state IDs được namespaced, mapping centroids chỉ theo train
information. Mapping không tin cậy → uncertainty/model-transition event, không
automatic market refit trigger."

The failure this prevents is specific. A refit is free to hand back the same three
market states under permuted integer labels. If the two versions share a namespace,
the permutation reads as every instrument changing regime at once -- a market event
that never happened. So each fit gets its own namespace, and a mapping between
namespaces is derived from TRAINING centroids alone and is allowed to fail.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass, field

import numpy as np

from .jump_model import JumpModelError, centroid_digest

#: How close two centroids must be, relative to the spread of the states within a
#: fit, before the mapping is trusted. Declared here, not tuned per refit.
MAPPING_MAX_RELATIVE_DISTANCE = 0.5
MAPPING_RUNNER_UP_RATIO = 1.25

#: G10/A14 — the explicit mapping statuses. ``matched`` is the only status that
#: yields an ``old_state``; ``unmatched`` is a state the old model never had and
#: ``ambiguous`` is one the assignment cannot separate. Both are MODEL events and
#: neither is ever emitted as a market transition.
MAPPING_MATCHED = "matched"
MAPPING_UNMATCHED = "unmatched"
MAPPING_AMBIGUOUS = "ambiguous"
MAPPING_STATUSES = (MAPPING_MATCHED, MAPPING_UNMATCHED, MAPPING_AMBIGUOUS)
#: Back-compatible aliases (historical code imports these names).
MAPPING_CONFIDENT = MAPPING_MATCHED
MAPPING_UNMAPPED = MAPPING_UNMATCHED


@dataclass
class ModelArtifact:
    """Everything L05.1 says a model must carry to be re-runnable and auditable."""

    model_id: str
    state_namespace: str
    training_start: str
    training_cutoff: str
    fit_ready_at: str
    n_states: int
    lambda_jump: float
    feature_names: tuple[str, ...]
    feature_weights: tuple[float, ...]
    group_weights: dict
    centroids: list
    scaler_ref: dict
    seeds: tuple[int, ...]
    selected_seed: int
    observation_interval: str
    fit_diagnostics: dict = field(default_factory=dict)
    code_hashes: dict = field(default_factory=dict)
    library_versions: dict = field(default_factory=dict)
    notes: str = ""

    def centroid_digest(self) -> str:
        return centroid_digest(np.asarray(self.centroids, dtype=np.float64))

    def as_record(self) -> dict:
        record = asdict(self)
        record["schema"] = "crypto_regime_lab.regime_model.v1"
        record["centroid_digest"] = self.centroid_digest()
        record["feature_names"] = list(self.feature_names)
        record["feature_weights"] = [float(w) for w in self.feature_weights]
        record["seeds"] = list(self.seeds)
        record["decision_rule"] = (
            "online emission is argmin_k Q_t(k) from the forward recurrence, decided at t and "
            "never revised. The offline best path is diagnostic only (guide 8.4).")
        record["state_naming_rule"] = (
            "states describe FEATURE STRUCTURE. They are not named from outer PnL and are not "
            "forced into bull/neutral/bear when the centroids do not support it (guide 8.1).")
        return record


def environment_hashes(module_paths: list) -> dict:
    """Hash the code that produced a fit, so a later run can prove it is the same."""
    from pathlib import Path

    out = {}
    for path in module_paths:
        p = Path(path)
        if p.is_file():
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


def library_versions() -> dict:
    import numpy

    versions = {"python": sys.version.split()[0], "numpy": numpy.__version__,
                "platform": platform.platform()}
    try:
        import scipy

        versions["scipy"] = scipy.__version__
    except ImportError:
        versions["scipy"] = "not installed"
    return versions


def verify_library_method(module_name: str, method_name: str) -> dict:
    """L05.1 — a library method name may only be used after the PINNED source is read.

    Guide 8.1/L05.1 warns that ``.predict_online`` does not necessarily implement
    the DP this lab specifies. So the lab never calls such a method on the strength
    of its name; it records whether the symbol exists and refuses to assume what it
    does.
    """
    import importlib
    import inspect

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        return {"module": module_name, "method": method_name, "status": "MODULE_ABSENT",
                "detail": str(exc)[:200], "safe_to_call": False}
    target = getattr(module, method_name, None)
    if target is None:
        return {"module": module_name, "method": method_name, "status": "SYMBOL_ABSENT",
                "safe_to_call": False}
    try:
        source = inspect.getsource(target)
    except (OSError, TypeError):
        source = ""
    return {
        "module": module_name, "method": method_name, "status": "PRESENT",
        "signature": str(inspect.signature(target)) if callable(target) else None,
        "source_available": bool(source),
        "source_digest": hashlib.sha256(source.encode()).hexdigest()[:16] if source else None,
        "safe_to_call": False,
        "rule": ("presence is not semantics. A method is used only after its pinned source has "
                 "been read and shown to implement the recurrence this lab specifies "
                 "(guide L05.1); until then the lab uses its own verified implementation."),
    }


# ---------------------------------------------------------------------------
# namespace mapping across a refit
# ---------------------------------------------------------------------------

def _scaler_affine(artifact: ModelArtifact) -> tuple[np.ndarray, np.ndarray]:
    """The artifact's training-only transform, or identity when it has none.

    A centroid is a point in the model's STANDARDIZED space. Comparing
    standardized centroids across two fits with different scalers compares two
    different coordinate systems (A14). The scaler_ref is the training-only
    transform that recovers the raw economic coordinate.
    """
    centroids = np.asarray(artifact.centroids, dtype=np.float64)
    scaler_ref = artifact.scaler_ref or {}
    if "median" in scaler_ref and "scale" in scaler_ref:
        median = np.asarray(scaler_ref["median"], dtype=np.float64)
        scale = np.asarray(scaler_ref["scale"], dtype=np.float64)
        if median.shape != (centroids.shape[1],) or scale.shape != (centroids.shape[1],):
            raise JumpModelError("scaler_ref does not match the centroid width")
        if np.any(scale == 0):
            raise JumpModelError("scaler_ref has a zero scale; the transform is not invertible")
        return median, scale
    return np.zeros(centroids.shape[1], dtype=np.float64), np.ones(centroids.shape[1],
                                                                    dtype=np.float64)


def _common_coordinates(artifact: ModelArtifact, frame_median: np.ndarray,
                        frame_scale: np.ndarray) -> np.ndarray:
    """Express an artifact's centroids in the shared (old-model) coordinate frame."""
    median, scale = _scaler_affine(artifact)
    raw = np.asarray(artifact.centroids, dtype=np.float64) * scale + median
    return (raw - frame_median) / frame_scale


def _one_to_one_assignment(distance: np.ndarray, *, exact_max_states: int = 6) -> tuple[list[int], str]:
    """Minimum-total-distance one-to-one assignment; exact for small K, greedy above.

    Independent nearest-neighbour mapping is what allowed many-to-one matches:
    two genuinely different new states could both claim one old state. With equal
    K a permutation is the only defensible mapping, so one is chosen.
    """
    n_new, n_old = distance.shape
    if n_new != n_old:
        raise JumpModelError("one-to-one assignment requires equal state counts")
    if n_new <= exact_max_states:
        import itertools

        best_perm, best_cost = None, float("inf")
        for perm in itertools.permutations(range(n_old)):
            cost = float(sum(distance[k, perm[k]] for k in range(n_new)))
            if cost < best_cost:
                best_perm, best_cost = perm, cost
        return list(best_perm), "exact_permutation"
    pairs = sorted(((float(distance[k, j]), k, j) for k in range(n_new) for j in range(n_old)),
                   key=lambda row: (row[0], row[1], row[2]))
    assigned_new: dict[int, int] = {}
    used_old: set[int] = set()
    for _, k, j in pairs:
        if k in assigned_new or j in used_old:
            continue
        assigned_new[k] = j
        used_old.add(j)
    return [assigned_new[k] for k in range(n_new)], "greedy_global"


def map_state_namespaces(old: ModelArtifact, new: ModelArtifact, *,
                         max_relative_distance: float = MAPPING_MAX_RELATIVE_DISTANCE) -> dict:
    """Map new-model states onto old-model states in COMMON raw/economic coordinates.

    No emission, no outcome and no market data after either cutoff enters this. The
    centroids are moved back through each fit's own training scaler into raw
    coordinates and expressed in one shared frame (the old model's transform), so
    two scalers can no longer make the same market state look like two.

    When the state counts match, the mapping is forced to be ONE-TO-ONE: a
    minimum-total-distance permutation. Every new state gets an explicit status:
    ``matched`` (confident, unique), ``unmatched`` (the old model has no such
    state, or it moved too far) or ``ambiguous`` (the old states cannot be told
    apart). Only ``matched`` yields an ``old_state``. A refit event -- and any
    unmapped or ambiguous state -- is a MODEL event: it is never emitted as a
    market transition and never triggers a parameter search.
    """
    if tuple(old.feature_names) != tuple(new.feature_names):
        raise JumpModelError("cannot map namespaces across different feature schemas")
    old_c = np.asarray(old.centroids, dtype=np.float64)
    new_c = np.asarray(new.centroids, dtype=np.float64)
    if old_c.ndim != 2 or new_c.ndim != 2 or old_c.shape[1] != new_c.shape[1]:
        raise JumpModelError("centroids must be (K, J) with matching feature width")
    weights = np.asarray(new.feature_weights, dtype=np.float64)
    if weights.shape != (old_c.shape[1],):
        raise JumpModelError("feature_weights do not match the centroid width")

    # Shared frame: the old model's training transform. Both fits' centroids are
    # recovered to raw coordinates first, so the frame is a real economic space.
    frame_median, frame_scale = _scaler_affine(old)
    old_common = _common_coordinates(old, frame_median, frame_scale)
    new_common = _common_coordinates(new, frame_median, frame_scale)
    new_median, new_scale = _scaler_affine(new)
    old_median, old_scale = _scaler_affine(old)
    new_raw = np.asarray(new.centroids, dtype=np.float64) * new_scale + new_median
    old_raw = np.asarray(old.centroids, dtype=np.float64) * old_scale + old_median

    def _distance(a, b):
        d = a - b
        return float(np.sqrt(np.sum(weights * d * d)))

    spread = [
        _distance(old_common[i], old_common[j])
        for i in range(old_common.shape[0]) for j in range(i + 1, old_common.shape[0])
    ]
    reference = float(np.median(spread)) if spread else 1.0
    if reference <= 0:
        reference = 1.0

    k_matches = old_common.shape[0] == new_common.shape[0]
    assignment_method = "independent_nearest_k_mismatch"
    assignment_total_distance = None
    if k_matches:
        distance_matrix = np.asarray(
            [[_distance(new_common[k], old_common[j]) for j in range(old_common.shape[0])]
             for k in range(new_common.shape[0])], dtype=np.float64)
        assignment, assignment_method = _one_to_one_assignment(distance_matrix)
        assignment_total_distance = float(sum(distance_matrix[k, assignment[k]]
                                              for k in range(new_common.shape[0])))
    else:
        assignment = [int(np.argmin([_distance(new_common[k], old_common[j])
                                     for j in range(old_common.shape[0])]))
                      for k in range(new_common.shape[0])]

    mapping = {}
    for k in range(new_common.shape[0]):
        distances = np.asarray([_distance(new_common[k], old_common[j])
                                for j in range(old_common.shape[0])])
        order = np.argsort(distances, kind="stable")
        nearest = int(order[0])
        best_d = float(distances[nearest])
        runner_up = float(distances[order[1]]) if distances.size > 1 else float("inf")
        relative = best_d / reference
        assigned = int(assignment[k])
        if relative > max_relative_distance:
            status = MAPPING_UNMATCHED
        elif k_matches and assigned != nearest:
            # the one-to-one constraint had to give this new state a non-nearest
            # old state: the structure cannot be separated unambiguously
            status = MAPPING_AMBIGUOUS
        elif runner_up < float("inf") and best_d > 0 and runner_up / max(best_d, 1e-12) < 1.25:
            status = MAPPING_AMBIGUOUS
        else:
            status = MAPPING_MATCHED
        mapping[str(k)] = {
            "new_state": k,
            "old_state": assigned if status == MAPPING_MATCHED else None,
            "assigned_old_state": assigned,
            "status": status,
            "distance": best_d,
            "assigned_distance": _distance(new_common[k], old_common[assigned]),
            "nearest_distance": best_d,
            "relative_distance": relative,
            "runner_up_distance": runner_up,
            "new_centroid_raw": [float(v) for v in new_raw[k]],
            "old_centroid_raw_assigned": [float(v) for v in old_raw[assigned]],
            "new_centroid_common": [float(v) for v in new_common[k]],
            "old_centroid_common_assigned": [float(v) for v in old_common[assigned]],
        }

    matched = [k for k, v in mapping.items() if v["status"] == MAPPING_MATCHED]
    unmatched = [k for k, v in mapping.items() if v["status"] == MAPPING_UNMATCHED]
    ambiguous = [k for k, v in mapping.items() if v["status"] == MAPPING_AMBIGUOUS]
    return {
        "schema": "crypto_regime_lab.state_namespace_mapping.v2",
        "old_namespace": old.state_namespace, "new_namespace": new.state_namespace,
        "old_centroid_digest": old.centroid_digest(),
        "new_centroid_digest": new.centroid_digest(),
        "reference_spread": reference,
        "max_relative_distance": max_relative_distance,
        "common_coordinate_frame": {
            "frame": "old_model_training_transform",
            "axis": "raw economic feature coordinates recovered through each fit's own scaler, "
                    "then expressed in the old model's standardized frame",
            "old_scaler_ref_present": bool(old.scaler_ref),
            "new_scaler_ref_present": bool(new.scaler_ref),
        },
        "k_matches": bool(k_matches),
        "one_to_one": bool(k_matches),
        "assignment_method": assignment_method,
        "assignment_total_distance": assignment_total_distance,
        "mapping": mapping,
        "matched_states": matched,
        "unmatched_states": unmatched,
        "ambiguous_states": ambiguous,
        "unmapped_states": unmatched + ambiguous,
        "all_states_mapped": not unmatched and not ambiguous,
        "information_used": "training centroids and declared feature weights only",
        "is_market_transition": False,
        "emits_market_transition": False,
        "triggers_parameter_search": False,
        "rule": ("a permuted or unmatched state ID after a refit is a MODEL event. It is emitted "
                 "as a model-transition/uncertainty record and never as a market regime change, "
                 "and it never triggers a parameter search or a market refit (guide 8.4). When K "
                 "matches the mapping is one-to-one in common raw/economic coordinates (A14)"),
    }


def relabel_states(states: np.ndarray, mapping: dict) -> np.ndarray:
    """Translate new-namespace states into old-namespace IDs; -1 where unmapped.

    -1 is deliberate: an unmapped state must be visibly absent rather than being
    folded into whichever old state happened to be nearest.
    """
    states = np.asarray(states, dtype=np.int64)
    lookup = {int(k): (v["old_state"] if v["status"] == MAPPING_CONFIDENT else -1)
              for k, v in mapping["mapping"].items()}
    return np.asarray([lookup.get(int(s), -1) for s in states], dtype=np.int64)


def model_transition_event(old: ModelArtifact, new: ModelArtifact, mapping: dict) -> dict:
    """The record emitted when the model version changes.

    G10/A14: a version event carries its own class and an explicit guarantee that
    it is not a market transition. The scheduler may refresh on a SEMANTIC state
    change in common coordinates, never on ``new_namespace != old_namespace``.
    """
    return {
        "schema": "crypto_regime_lab.model_transition.v2",
        "event_class": "MODEL_VERSION",
        "from_version": old.model_id, "to_version": new.model_id,
        "from_namespace": old.state_namespace, "to_namespace": new.state_namespace,
        "training_cutoff": new.training_cutoff,
        "mapping_confident": mapping["all_states_mapped"],
        "mapping_status_counts": {
            "matched": len(mapping.get("matched_states", [])),
            "unmatched": len(mapping.get("unmatched_states", [])),
            "ambiguous": len(mapping.get("ambiguous_states", [])),
        },
        "one_to_one": bool(mapping.get("one_to_one", False)),
        "unmapped_states": mapping["unmapped_states"],
        "event_type": "MODEL_TRANSITION" if mapping["all_states_mapped"]
        else "MODEL_TRANSITION_WITH_UNMAPPED_STATES",
        "is_market_event": False,
        "market_transition": False,
        "emits_market_transition": False,
        "requires_parameter_search": False,
        "prior_emissions_rewritten": False,
        "prior_emissions_rule": ("decision-vintage emissions stay exactly as they were emitted; "
                                 "the new model's view of the same past is a separate "
                                 "asof_<cutoff>_training_labels series (guide 8.4)"),
        "rule": ("a namespace/version change is a MODEL event. It is never emitted as a market "
                 "transition and never reaches the trigger path; only a semantic state change in "
                 "common coordinates can (G10/A10)"),
    }


def dumps(artifact: ModelArtifact) -> str:
    return json.dumps(artifact.as_record(), indent=2, sort_keys=True, allow_nan=False)
