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

MAPPING_CONFIDENT = "MAPPED"
MAPPING_UNMAPPED = "UNMAPPED_REFIT_STATE"
MAPPING_AMBIGUOUS = "AMBIGUOUS_MAPPING"


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

def map_state_namespaces(old: ModelArtifact, new: ModelArtifact, *,
                         max_relative_distance: float = MAPPING_MAX_RELATIVE_DISTANCE) -> dict:
    """Map new-model states onto old-model states using TRAINING centroids only.

    No emission, no outcome and no market data after either cutoff enters this. A
    state that cannot be matched confidently is ``UNMAPPED_REFIT_STATE`` -- a model
    event, explicitly NOT a market transition and explicitly not a retrain trigger.
    """
    if tuple(old.feature_names) != tuple(new.feature_names):
        raise JumpModelError("cannot map namespaces across different feature schemas")
    old_c = np.asarray(old.centroids, dtype=np.float64)
    new_c = np.asarray(new.centroids, dtype=np.float64)
    weights = np.asarray(new.feature_weights, dtype=np.float64)

    def _distance(a, b):
        d = a - b
        return float(np.sqrt(np.sum(weights * d * d)))

    # scale by how far apart the OLD model's own states are: a "close" match must be
    # close relative to the structure the model itself resolves
    spread = [
        _distance(old_c[i], old_c[j])
        for i in range(old_c.shape[0]) for j in range(i + 1, old_c.shape[0])
    ]
    reference = float(np.median(spread)) if spread else 1.0
    if reference <= 0:
        reference = 1.0

    mapping = {}
    for k in range(new_c.shape[0]):
        distances = np.asarray([_distance(new_c[k], old_c[j]) for j in range(old_c.shape[0])])
        order = np.argsort(distances, kind="stable")
        best = int(order[0])
        best_d = float(distances[best])
        runner_up = float(distances[order[1]]) if distances.size > 1 else float("inf")
        relative = best_d / reference
        if relative > max_relative_distance:
            status = MAPPING_UNMAPPED
        elif runner_up < float("inf") and best_d > 0 and runner_up / max(best_d, 1e-12) < 1.25:
            status = MAPPING_AMBIGUOUS
        else:
            status = MAPPING_CONFIDENT
        mapping[str(k)] = {
            "new_state": k,
            "old_state": best if status == MAPPING_CONFIDENT else None,
            "status": status,
            "distance": best_d,
            "relative_distance": relative,
            "runner_up_distance": runner_up,
        }

    unmapped = [k for k, v in mapping.items() if v["status"] != MAPPING_CONFIDENT]
    return {
        "schema": "crypto_regime_lab.state_namespace_mapping.v1",
        "old_namespace": old.state_namespace, "new_namespace": new.state_namespace,
        "old_centroid_digest": old.centroid_digest(),
        "new_centroid_digest": new.centroid_digest(),
        "reference_spread": reference,
        "max_relative_distance": max_relative_distance,
        "mapping": mapping,
        "unmapped_states": unmapped,
        "all_states_mapped": not unmapped,
        "information_used": "training centroids and declared feature weights only",
        "is_market_transition": False,
        "triggers_parameter_search": False,
        "rule": ("a permuted or unmatched state ID after a refit is a MODEL event. It is emitted "
                 "as a model-transition/uncertainty record and never as a market regime change, "
                 "and it never triggers a parameter search or a market refit (guide 8.4)"),
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
    """The record emitted when the model version changes."""
    return {
        "schema": "crypto_regime_lab.model_transition.v1",
        "from_version": old.model_id, "to_version": new.model_id,
        "from_namespace": old.state_namespace, "to_namespace": new.state_namespace,
        "training_cutoff": new.training_cutoff,
        "mapping_confident": mapping["all_states_mapped"],
        "unmapped_states": mapping["unmapped_states"],
        "event_type": "MODEL_TRANSITION" if mapping["all_states_mapped"]
        else "MODEL_TRANSITION_WITH_UNMAPPED_STATES",
        "is_market_event": False,
        "requires_parameter_search": False,
        "prior_emissions_rewritten": False,
        "prior_emissions_rule": ("decision-vintage emissions stay exactly as they were emitted; "
                                 "the new model's view of the same past is a separate "
                                 "asof_<cutoff>_training_labels series (guide 8.4)"),
    }


def dumps(artifact: ModelArtifact) -> str:
    return json.dumps(artifact.as_record(), indent=2, sort_keys=True, allow_nan=False)
