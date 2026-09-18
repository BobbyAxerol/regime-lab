"""Worker environment and resource budget (guide L01.3/0.3, tests T05, T06, T07).

``lab_worker_env`` is the only environment a lab worker should run under: every
cache is redirected into ``LAB_ROOT``, bytecode writing is off, thread pools are
capped to the CPU budget, and credential-shaped variables are stripped.
"""

from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from pathlib import Path

from .paths import SandboxPolicy

CREDENTIAL_ENV_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL", "API_KEY")
CREDENTIAL_ENV_ALLOWLIST = {"SSH_AUTH_SOCK"}


@dataclass(frozen=True)
class ResourceBudget:
    """Initial budget from guide 0.3. A request to raise it is an explicit decision."""

    workers: int = 1
    cpu_limit: int = 2
    working_memory_gib: int = 4
    disk_quota_gib: int = 20

    @classmethod
    def from_policy(cls, policy: SandboxPolicy) -> "ResourceBudget":
        raw = policy.raw.get("resource_budget", {})
        return cls(
            workers=int(raw.get("workers", 1)),
            cpu_limit=int(raw.get("cpu_limit", 2)),
            working_memory_gib=int(raw.get("working_memory_gib", 4)),
            disk_quota_gib=int(raw.get("disk_quota_gib", 20)),
        )


def strip_credentials(env: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """T06: remove credential-shaped variables from a replay worker environment."""
    removed: list[str] = []
    clean = {}
    for key, value in env.items():
        upper = key.upper()
        if key in CREDENTIAL_ENV_ALLOWLIST:
            clean[key] = value
            continue
        if any(marker in upper for marker in CREDENTIAL_ENV_MARKERS):
            removed.append(key)
            continue
        clean[key] = value
    return clean, removed


def lab_worker_env(policy: SandboxPolicy, *, network: bool = False, base: dict[str, str] | None = None) -> dict[str, str]:
    """Build the environment for a lab worker process.

    Every cache path resolves inside ``LAB_ROOT`` so an import cannot write into
    a protected tree (T05), and thread counts respect the CPU budget (T07).
    """
    budget = ResourceBudget.from_policy(policy)
    env, _removed = strip_credentials(dict(base if base is not None else os.environ))
    cache_root = policy.lab_root / ".cache"
    for name, sub in (
        ("NUMBA_CACHE_DIR", "numba"),
        ("MPLCONFIGDIR", "matplotlib"),
        ("XDG_CACHE_HOME", "xdg"),
        ("TMPDIR", "tmp"),
        ("PIP_CACHE_DIR", "pip"),
        ("HF_HOME", "hf"),
    ):
        path = cache_root / sub
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = str(cache_root / "pycache")
    env["CRYPTO_REGIME_LAB_ROOT"] = str(policy.lab_root)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        env[name] = str(budget.cpu_limit)
    if not network:
        # Advisory only: a real block needs an OS mechanism. Recorded, not claimed as enforcement.
        env["CRYPTO_REGIME_LAB_NETWORK"] = "disabled"
        env["no_proxy"] = "*"
        env["NO_PROXY"] = "*"
        for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
            env.pop(var, None)
    else:
        env["CRYPTO_REGIME_LAB_NETWORK"] = "acquisition_stage"
    return env


def become_process_group_leader() -> dict:
    """Own a process group so cancellation only reaches this lab's children."""
    try:
        os.setpgrp()
        return {"pgid": os.getpgid(0), "status": "OWNED"}
    except OSError as exc:
        return {"pgid": os.getpgid(0), "status": f"NOT_OWNED: {exc}"}


def terminate_own_group(pgid: int, sig: int = signal.SIGTERM) -> dict:
    """Cancel only our own process group; refuses to signal any other group."""
    if pgid != os.getpgid(0):
        return {"status": "REFUSED", "reason": "pgid is not this process' group", "pgid": pgid}
    os.killpg(pgid, sig)
    return {"status": "SIGNALLED", "pgid": pgid, "signal": int(sig)}


def disk_usage_report(policy: SandboxPolicy) -> dict:
    """Disk quota accounting (guide 0.3). Over-quota is a stop, not a warning."""
    import shutil as _shutil

    budget = ResourceBudget.from_policy(policy)
    used = 0
    for path in policy.lab_root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                used += path.stat().st_size
        except OSError:
            continue
    total, _used_fs, free = _shutil.disk_usage(policy.lab_root)
    quota_bytes = budget.disk_quota_gib * (1 << 30)
    return {
        "lab_bytes_used": used,
        "lab_gib_used": round(used / (1 << 30), 3),
        "quota_gib": budget.disk_quota_gib,
        "quota_bytes": quota_bytes,
        "within_quota": used <= quota_bytes,
        "filesystem_free_gib": round(free / (1 << 30), 3),
        "filesystem_total_gib": round(total / (1 << 30), 3),
        "headroom_gib": round((quota_bytes - used) / (1 << 30), 3),
    }


def cache_paths_inside_lab(env: dict[str, str], policy: SandboxPolicy) -> list[str]:
    """T05 check: report any cache variable that still points outside the lab."""
    offenders = []
    for name in ("NUMBA_CACHE_DIR", "MPLCONFIGDIR", "XDG_CACHE_HOME", "TMPDIR", "PIP_CACHE_DIR", "PYTHONPYCACHEPREFIX"):
        value = env.get(name)
        if value is None:
            offenders.append(f"{name}=<unset>")
            continue
        try:
            Path(os.path.realpath(value)).relative_to(policy.lab_root)
        except ValueError:
            offenders.append(f"{name}={value}")
    return offenders
