"""FP01.1 live inventory (guide §13 FP01.1): branch/commit/dirty diff/untracked,
lab interpreter + package/native origins, actual resource allocation, data
snapshots + consumed-data history, active jobs, protected state.

Everything is a measurement of the live machine; anything unmeasurable stays
null with a reason, never fabricated.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import sqlite3
import subprocess
from pathlib import Path


def sh(args: list, cwd=None) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)
    return (proc.stdout or "").strip()


def sha256_file(path: Path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def pkg_version(name: str):
    try:
        return md.version(name)
    except Exception:
        return None


def inventory(*, lab_root: Path, protected_root: Path) -> dict:
    """Collect the FP01.1 inventory. No engine call, no ledger write."""
    lab_root, protected_root = Path(lab_root), Path(protected_root)
    venv = lab_root / "environments" / "lab_venv"
    installed_endpoint = (venv / "lib" / "python3.12" / "site-packages"
                          / "quantbt" / "endpoint.py")
    protected_endpoint = protected_root / "src" / "quantbt" / "endpoint.py"
    try:
        marker = __import__("json").loads((lab_root / ".lab_marker.json").read_text())
    except (OSError, ValueError):
        marker = None
    jobs: list = []
    try:
        lines = subprocess.run(["ps", "-eo", "pid,lstart,cmd"], capture_output=True,
                               text=True, timeout=30).stdout.splitlines()
        for line in lines:
            if "ps -eo" in line:
                continue
            parts = line.split(None, 6)
            if len(parts) < 7:
                continue
            cmd = parts[6][:300]
            if str(lab_root) in cmd:
                jobs.append({"pid": parts[0], "started": " ".join(parts[1:5]),
                             "cmd": cmd})
    except Exception as exc:  # keep null+reason, never fabricate
        jobs = [{"error": f"{type(exc).__name__}: {exc}"}]
    ledger_path = (lab_root / "evidence" / "time_edge_validation_v4" / "allocations"
                   / "TE02-PILOT-R03" / "ledger.sqlite")
    ledger = {"path": str(ledger_path), "by_status": None, "error": None}
    try:
        conn = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True)
        ledger["by_status"] = conn.execute(
            "select status,count(*),round(sum(wall),1) from attempt group by status"
        ).fetchall()
        conn.close()
    except Exception as exc:
        ledger["error"] = f"{type(exc).__name__}: {exc}"
    snapshots = sorted(p.name for p in (lab_root / "snapshots").iterdir()
                       if p.is_dir()) if (lab_root / "snapshots").is_dir() else None
    return {
        "git_branch": sh(["git", "branch", "--show-current"], cwd=lab_root),
        "git_head_full": sh(["git", "rev-parse", "HEAD"], cwd=lab_root),
        "git_dirty_tracked": sh(["git", "status", "--porcelain",
                                 "--untracked-files=no"], cwd=lab_root),
        "git_untracked": sorted(
            line[3:] for line in sh(["git", "status", "--porcelain"],
                                    cwd=lab_root).splitlines() if line.startswith("?? ")),
        "lab_marker": marker,
        "engine": {
            "quantbt_engine_version": pkg_version("quantbt-engine"),
            "quantbt_native_version": pkg_version("quantbt-native"),
            "optuna_version": pkg_version("optuna"),
            "endpoint_path_installed": str(installed_endpoint),
            "endpoint_sha256_installed": sha256_file(installed_endpoint),
        },
        "protected": {
            "root": str(protected_root),
            "git_status_porcelain": sh(["git", "status", "--porcelain"], cwd=protected_root),
            "git_head": sh(["git", "rev-parse", "HEAD"], cwd=protected_root),
            "endpoint_sha256": sha256_file(protected_endpoint),
        },
        "resource_allocation": {
            "cpus": __import__("os").cpu_count(),
            "mem_total_mib": (lambda: (lambda v: int(v[0]) // 1024)(
                [int(l.split()[1]) for l in open("/proc/meminfo")
                 if l.startswith("MemTotal:")]))(),
        },
        "snapshots": snapshots,
        "active_lab_jobs": jobs,
        "shared_te_ledger": ledger,
    }
