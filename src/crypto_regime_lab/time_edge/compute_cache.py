"""Identity-keyed shared cache for TE nested artifacts.

An entry is reusable only when every facet that can change the produced bytes is
identical: the world/cutoff/economics facets of the computation, the hash of the
code that computes it, and the registered input hashes. The cache never keys on a
task or run ID. Every publication records the producer run and its full source
identity; every consumer records the producer in its own cache ledger, so a reuse
is never silent. A corrupt or drifted seal raises instead of recomputing.
"""
from pathlib import Path
import threading

from .runtime import local, source_identity
from .storage import EvidenceError, canonical, digest, file_digest, jsonable, read, save, utcnow

CACHE_SCHEMA = "regime_lab.te_compute_cache.v1"
CACHE_SEAL_SCHEMA = "regime_lab.te_compute_cache_seal.v1"
CACHE_ROOT = "evidence/time_edge_validation_v4/compute-cache"

# The cache root may never contain a path seed/exclusion pattern that the read
# guard refuses; contracts name files relative to LAB_ROOT.
#
# RA-02 (RA-GUIDE-1.0 §6 RA02.3): every kind also hashes the shared financial
# semantics closure — alpha adapter base, the evaluator/engine bridge, the
# event/continuous account execution bridge and the shared contract helpers.
# Editing any of these must MISS every dependent kind. This deliberately
# invalidates pre-RA-02 cache entries: backend changes invalidate unless
# equivalence is certified, and it was not.
SHARED_FINANCIAL_CLOSURE = (
    "src/crypto_regime_lab/alphas/base.py",
    "src/crypto_regime_lab/experiments/time_edge_contracts.py",
    "src/crypto_regime_lab/experiments/evaluator.py",
    "src/crypto_regime_lab/experiments/dynamic_fold_provider.py",
    "src/crypto_regime_lab/integration/event_account.py",
    "src/crypto_regime_lab/integration/continuous_account.py",
)

CONTRACT_FILES = {
    kind: SHARED_FINANCIAL_CLOSURE + files
    for kind, files in {
    "world": ("src/crypto_regime_lab/time_edge/controls.py",),
    "targets": ("src/crypto_regime_lab/time_edge/workers.py",
                "src/crypto_regime_lab/time_edge/execution.py",
                "src/crypto_regime_lab/time_edge/metrics.py",
                "src/crypto_regime_lab/time_edge/eligibility.py",
                "src/crypto_regime_lab/time_edge/storage.py"),
    "search": ("src/crypto_regime_lab/time_edge/execution.py",
               "src/crypto_regime_lab/time_edge/eligibility.py",
               "src/crypto_regime_lab/time_edge/metrics.py",
               "src/crypto_regime_lab/time_edge/storage.py"),
    "fit": ("src/crypto_regime_lab/time_edge/model.py",
            "src/crypto_regime_lab/time_edge/metrics.py",
            "src/crypto_regime_lab/time_edge/storage.py"),
    "features": ("src/crypto_regime_lab/time_edge/workers.py",
                 "src/crypto_regime_lab/time_edge/storage.py",
                 "src/crypto_regime_lab/data/panel.py",
                 "src/crypto_regime_lab/data/availability.py"),
    "deployment": ("src/crypto_regime_lab/time_edge/workers.py",
                   "src/crypto_regime_lab/time_edge/execution.py",
                   "src/crypto_regime_lab/time_edge/metrics.py",
                   "src/crypto_regime_lab/time_edge/eligibility.py",
                   "src/crypto_regime_lab/time_edge/storage.py"),
    "causal_event": ("src/crypto_regime_lab/time_edge/execution.py",),
    # FP-02 (forward_persistence_fp_v1): the common evaluator's own two
    # account types. SHARED_FINANCIAL_CLOSURE already covers event_account.py
    # / continuous_account.py / evaluator.py / dynamic_fold_provider.py for
    # every kind; these add only what FP-02 itself introduces, so an edit to
    # fp/evaluator.py or fp/lineage.py correctly misses every cached FP-02
    # entry without touching any TE kind above.
    "fp_candidate": ("src/crypto_regime_lab/fp/evaluator.py",
                     "src/crypto_regime_lab/fp/retention_fp02.py"),
    "fp_deployment": ("src/crypto_regime_lab/fp/evaluator.py",
                      "src/crypto_regime_lab/fp/lineage.py",
                      "src/crypto_regime_lab/fp/retention_fp02.py"),
    }.items()
}


def code_contract(root, kind):
    files = CONTRACT_FILES.get(kind)
    if not files:
        raise EvidenceError("unregistered cache contract kind: " + str(kind))
    root = Path(root)
    contract = {}
    for name in files:
        path = root / name
        if not path.is_file():
            raise EvidenceError("cache contract file missing: " + name)
        contract[name] = file_digest(path)
    return contract


def engine_contract(root):
    """Installed engine bytes that every engine-backed computation depends on."""
    return {key: value for key, value in source_identity(Path(root)).items() if "quantbt" in key}


class ComputeCache:
    """Append-only content-addressed publication, keyed by computed identity."""

    _identity_locks: dict = {}
    _identity_locks_guard = threading.Lock()

    def __init__(self, root, namespace, *, source=None, cache_root=CACHE_ROOT):
        self.root = Path(root).resolve()
        if not str(namespace).replace("-", "").replace("_", "").isalnum():
            raise EvidenceError("unsafe cache namespace")
        self.namespace = str(namespace)
        self.source = source if source is not None else digest(source_identity(self.root))
        # cache_root defaults to the TE study's own path (CACHE_ROOT) so every
        # existing caller is unchanged; a different study (e.g. FP-02) passes
        # its own evidence-tree path instead of nesting its cache inside TE's.
        self.directory = local(self.root, f"{cache_root}/{self.namespace}")

    def identity(self, kind, facets):
        if kind not in CONTRACT_FILES or not isinstance(facets, dict):
            raise EvidenceError("cache identity needs a registered kind and facet object")
        return digest({"schema": CACHE_SCHEMA, "namespace": self.namespace,
                       "kind": kind, "facets": jsonable(facets)})

    def _paths(self, identity):
        return self.directory / (identity + ".json"), self.directory / (identity + ".seal.json")

    def _lock_for(self, identity) -> threading.Lock:
        with ComputeCache._identity_locks_guard:
            return ComputeCache._identity_locks.setdefault(
                (self.namespace, identity), threading.Lock())

    def lookup(self, kind, facets):
        identity = self.identity(kind, facets)
        path, seal = self._paths(identity)
        if not path.exists() and not seal.exists():
            return None
        if not path.is_file() or not seal.is_file():
            raise EvidenceError("incomplete compute-cache publication: " + identity)
        if seal.is_file() and read(seal).get("sha256") != file_digest(path):
            raise EvidenceError("compute-cache seal hash drift: " + identity)
        record = read(path)
        if record.get("schema") != CACHE_SCHEMA or record.get("identity") != identity or record.get("kind") != kind:
            raise EvidenceError("compute-cache identity drift: " + identity)
        if record.get("namespace") != self.namespace:
            raise EvidenceError("compute-cache namespace drift: " + identity)
        return record

    def publish(self, kind, facets, payload, *, producer):
        if not producer:
            raise EvidenceError("compute-cache publication needs a producer run id")
        identity = self.identity(kind, facets)
        path, seal = self._paths(identity)
        record = {"schema": CACHE_SCHEMA, "namespace": self.namespace, "kind": kind,
                  "identity": identity, "facets": jsonable(facets),
                  "producer": {"lab_run_id": producer, "source_identity": self.source,
                               "created_at": utcnow()},
                  "payload": jsonable(payload)}
        try:
            published = save(path, record)
        except EvidenceError:
            # A concurrent producer of the identical computation is allowed to
            # lose the race only when it produced byte-identical substance.
            existing = read(path)
            if existing.get("identity") != identity or canonical(existing.get("payload")) != canonical(record["payload"]):
                raise
            published = file_digest(path)
        if not seal.exists():
            save(seal, {"schema": CACHE_SEAL_SCHEMA, "identity": identity,
                        "sha256": published, "source_identity": self.source})
        elif read(seal).get("sha256") != published:
            raise EvidenceError("compute-cache seal drift: " + identity)
        return read(path)

    def get_or_compute(self, kind, facets, callback, *, producer):
        identity = self.identity(kind, facets)
        found = self.lookup(kind, facets)
        if found is not None:
            return found["payload"], {"status": "HIT", "kind": kind, "identity": identity,
                                      "producer": found["producer"]}
        payload = callback()
        record = self.publish(kind, facets, payload, producer=producer)
        return record["payload"], {"status": "MISS", "kind": kind, "identity": identity,
                                   "producer": record["producer"]}

    def get_or_compute_singleflight(self, kind, facets, callback, *, producer):
        """One owner computation per semantic key among same-process racers.

        RA-02 §6 RA02.4/C06: a per-identity lock plus a re-check after
        acquiring means concurrent consumers of one key perform the callback
        exactly once and the rest receive the published, seal-validated
        payload. Never publishes twice for one key.
        """
        identity = self.identity(kind, facets)
        with self._lock_for(identity):
            return self.get_or_compute(kind, facets, callback, producer=producer)
