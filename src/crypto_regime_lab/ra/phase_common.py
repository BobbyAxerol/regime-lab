"""Shared helpers for RA phase runners (RA-GUIDE-1.0 §14).

Small, side-effect-light primitives every RA phase needs: subprocess
capture with explicit timeout, file hashing, protected-tree fingerprints
(before/after) and atomic text publication. Kept pure so tests can import
them without pulling phase-specific logic.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parents[3]
QUANTBT = Path("/root/bobby/pool_alpha/quantbt")


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sh(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)
    return (proc.stdout or "").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protected_fingerprint() -> dict:
    """Read-only fingerprint of the protected quantbt tree."""
    status = sh(["git", "status", "--porcelain"], cwd=QUANTBT)
    endpoint = QUANTBT / "src" / "quantbt" / "endpoint.py"
    return {
        "git_status_porcelain": status,
        "git_head": sh(["git", "rev-parse", "HEAD"], cwd=QUANTBT),
        "endpoint_sha256": sha256_file(endpoint) if endpoint.is_file() else None,
    }


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def ledger_snapshot(path: Path) -> dict:
    """Read-only state of a TE allocation ledger (never mutates it)."""
    import sqlite3

    snapshot = {"path": str(path), "spent": None, "attempts": None,
                "budget": None, "by_status": None, "error": None}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        snapshot["spent"] = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(wall,reserved)),0) FROM attempt"
        ).fetchone()[0]
        snapshot["attempts"] = conn.execute(
            "SELECT count(*) FROM attempt").fetchone()[0]
        study = conn.execute("SELECT budget FROM study").fetchone()
        snapshot["budget"] = None if study is None else study[0]
        snapshot["by_status"] = conn.execute(
            "SELECT status, count(*), round(sum(COALESCE(wall,reserved)),1) "
            "FROM attempt GROUP BY status").fetchall()
        conn.close()
    except Exception as exc:  # null+reason, never fabricated
        snapshot["error"] = f"{type(exc).__name__}: {exc}"
    return snapshot
