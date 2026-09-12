"""Evidence writing for the lab (guide L01.4, 11.5, tests T07, T59, T61).

Rules encoded here:
  * every artifact carries a ``lab_run_id`` and a schema version;
  * JSON is strict (``allow_nan=False``) so NaN/Inf become an explicit status
    plus ``null`` instead of invalid JSON;
  * writes are atomic (tmp + ``os.replace``) and confined to ``LAB_ROOT``;
  * the attempt ledger is append-only and flushed before an operation may be
    reported as successful.
"""

from __future__ import annotations

import json
import math
import os
import platform
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..safety.paths import SandboxPolicy, sha256_file

EVIDENCE_SCHEMA_VERSION = "crypto_regime_lab.evidence.v1"


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def new_lab_run_id(prefix: str = "run") -> str:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


class NonFiniteValue(ValueError):
    """Raised when a numeric value cannot be represented in strict JSON."""


def sanitize_numeric(value: Any) -> tuple[Any, str | None]:
    """Return ``(json_safe_value, status)``.

    A non-finite float becomes ``(None, "NAN"|"POS_INF"|"NEG_INF")`` so the
    reader sees missing-with-reason rather than a fabricated zero.
    """
    if isinstance(value, float):
        if math.isnan(value):
            return None, "NAN"
        if math.isinf(value):
            return None, "POS_INF" if value > 0 else "NEG_INF"
    return value, None


def _default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"{type(obj).__name__} is not JSON serialisable; give it an explicit schema field")


def dumps_strict(payload: Any, indent: int | None = 2) -> str:
    """Strict JSON: rejects NaN/Inf loudly instead of emitting invalid JSON."""
    try:
        return json.dumps(payload, indent=indent, sort_keys=False, allow_nan=False, default=_default)
    except ValueError as exc:  # json raises ValueError for out-of-range floats
        raise NonFiniteValue(
            "payload contains NaN/Infinity; convert to null plus a status field before writing"
        ) from exc


def environment_fingerprint() -> dict:
    """Interpreter/OS/package identity that a rerun can be compared against."""
    import importlib.metadata as md

    packages: dict[str, str | None] = {}
    for name in (
        "quantbt-engine", "quantbt-native", "numpy", "pandas", "numba",
        "llvmlite", "scipy", "pyarrow", "ta", "optuna", "pytest",
    ):
        try:
            packages[name] = md.version(name)
        except Exception:
            packages[name] = None
    quantbt_file = None
    try:
        import quantbt  # imported from the lab venv only

        quantbt_file = quantbt.__file__
    except Exception:
        pass
    numba_meta: dict[str, object] = {}
    try:
        import numba
        import llvmlite

        numba_meta = {
            "numba_version": numba.__version__,
            "llvmlite_version": llvmlite.__version__,
            "threading_layer": os.environ.get("NUMBA_THREADING_LAYER"),
            "num_threads": getattr(numba.config, "NUMBA_NUM_THREADS", None),
            "default_num_threads": getattr(numba.config, "NUMBA_DEFAULT_NUM_THREADS", None),
            "cache_dir": os.environ.get("NUMBA_CACHE_DIR"),
            "disable_jit": getattr(numba.config, "DISABLE_JIT", None),
            "fastmath_policy": (
                "lab reference kernels must run fastmath=False; a fastmath variant is a separate "
                "recorded version, never a silent substitution (guide L02.2)"
            ),
        }
    except Exception as exc:
        numba_meta = {"error": f"{type(exc).__name__}: {exc}"}

    thread_meta = {
        name: os.environ.get(name)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS")
    }
    try:
        thread_meta["os_sched_affinity"] = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        thread_meta["os_sched_affinity"] = None

    return {
        "python_version": sys.version,
        "numba": numba_meta,
        "threads": thread_meta,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "hostname": socket.gethostname(),
        "cpu_count": os.cpu_count(),
        "packages": packages,
        "quantbt_import_origin": quantbt_file,
        "env_flags": {
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE"),
            "NUMBA_CACHE_DIR": os.environ.get("NUMBA_CACHE_DIR"),
            "MPLCONFIGDIR": os.environ.get("MPLCONFIGDIR"),
            "TMPDIR": os.environ.get("TMPDIR"),
        },
    }


@dataclass
class EvidenceWriter:
    """Atomic, lab-confined artifact writer with an append-only attempt ledger."""

    policy: SandboxPolicy
    lab_run_id: str
    study_id: str = "unregistered"
    _ledger_path: Path | None = None

    @classmethod
    def open(cls, policy: SandboxPolicy, study_id: str = "unregistered", lab_run_id: str | None = None) -> "EvidenceWriter":
        writer = cls(policy=policy, lab_run_id=lab_run_id or new_lab_run_id(), study_id=study_id)
        writer._ledger_path = writer.run_dir / "attempts.jsonl"
        writer.run_dir.mkdir(parents=True, exist_ok=True)
        return writer

    @property
    def run_dir(self) -> Path:
        return self.policy.lab_root / "evidence" / self.study_id / self.lab_run_id

    # -- artifacts --------------------------------------------------------

    def write_json(self, relpath: str | os.PathLike[str], payload: dict, *, schema: str | None = None) -> dict:
        """Write one JSON artifact atomically and return its record."""
        body = dict(payload)
        body.setdefault("schema", schema or EVIDENCE_SCHEMA_VERSION)
        body.setdefault("lab_run_id", self.lab_run_id)
        body.setdefault("study_id", self.study_id)
        body.setdefault("written_at_utc", utc_now_iso())
        text = dumps_strict(body)
        target = self.policy.resolve_write_target(self.run_dir / relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + f".tmp-{os.getpid()}")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        return {
            "artifact_path": str(target),
            "relpath": str(relpath),
            "sha256": sha256_file(target),
            "size_bytes": target.stat().st_size,
            "schema": body["schema"],
        }

    def write_config(self, relpath: str | os.PathLike[str], payload: dict) -> dict:
        """Write a config under ``LAB_ROOT/configs`` (not under the run dir)."""
        text = dumps_strict(payload)
        target = self.policy.resolve_write_target(self.policy.lab_root / "configs" / relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + f".tmp-{os.getpid()}")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        return {"artifact_path": str(target), "sha256": sha256_file(target), "size_bytes": target.stat().st_size}

    def append_jsonl(self, relpath: str | os.PathLike[str], rows: Iterable[dict]) -> int:
        target = self.policy.resolve_write_target(self.run_dir / relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(target, "a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(dumps_strict(row, indent=None) + "\n")
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        return count

    # -- attempt ledger ---------------------------------------------------

    def record_attempt(
        self,
        operation: str,
        status: str,
        *,
        detail: dict | None = None,
        attempt_id: str | None = None,
        duration_s: float | None = None,
    ) -> str:
        """Append one attempt row. Never overwritten, never pruned by a later run."""
        row = {
            "schema": "crypto_regime_lab.attempt.v1",
            "attempt_id": attempt_id or f"att-{uuid.uuid4().hex[:12]}",
            "lab_run_id": self.lab_run_id,
            "study_id": self.study_id,
            "operation": operation,
            "status": status,
            "at_utc": utc_now_iso(),
            "duration_s": duration_s,
            "detail": detail or {},
        }
        self.append_jsonl("attempts.jsonl", [row])
        return row["attempt_id"]

    def attempt(self, operation: str):
        """Context manager recording START then SUCCESS/FAILED for one operation."""
        return _Attempt(self, operation)


class _Attempt:
    def __init__(self, writer: EvidenceWriter, operation: str) -> None:
        self.writer = writer
        self.operation = operation
        self.detail: dict = {}
        self._t0 = 0.0
        self.attempt_id = ""

    def __enter__(self) -> "_Attempt":
        self._t0 = time.monotonic()
        self.attempt_id = self.writer.record_attempt(self.operation, "STARTED")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        duration = time.monotonic() - self._t0
        if exc_type is None:
            self.writer.record_attempt(
                self.operation, "SUCCESS", detail=self.detail, attempt_id=self.attempt_id, duration_s=duration
            )
            return False
        detail = dict(self.detail)
        detail["error_type"] = exc_type.__name__
        detail["error"] = str(exc)
        self.writer.record_attempt(
            self.operation, "FAILED", detail=detail, attempt_id=self.attempt_id, duration_s=duration
        )
        return False  # never swallow the exception
