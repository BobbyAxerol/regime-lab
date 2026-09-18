"""Reconcile ledger RUNNING rows with live processes (RA-GUIDE-1.0 §5 RA01.1).

A RUNNING row with no live owner process is an orphan that must be
reconciled — charged at its reservation via the supervisor's
``recover_interrupted`` under the run lock — never silently dropped and
never silently counted as live work. RA-01 only records the evidence; it
never mutates the TE ledger.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

_ATTEMPT_DIR_RE = re.compile(r"/attempts/([0-9a-f]{32})/")

SCHEMA = "crypto_regime_lab.ra01_reconcile.v1"
METHOD = (
    "ledger RUNNING rows matched against a live ps snapshot: first by the "
    "attempt id appearing in a process cmdline, then (single-owner runs) by "
    "process start time within the window; unmatched rows are "
    "ORPHAN_NO_LIVE_PROCESS"
)


def _parse_ps_start(raw: str) -> float | None:
    """Epoch seconds from a ``ps lstart`` timestamp (host-local time)."""
    try:
        return time.mktime(time.strptime(raw.strip(), "%a %b %d %H:%M:%S %Y"))
    except (ValueError, TypeError):
        return None


def _parse_iso(ts: str) -> float | None:
    """Epoch seconds from a ledger ISO-8601 timestamp."""
    try:
        dt = datetime.fromisoformat(str(ts).strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def reconcile_running_rows(running_rows: list[dict], processes: list[dict],
                           *, start_window_s: float = 15.0) -> dict:
    """Classify every ledger RUNNING row against a live process snapshot.

    running_rows: ``[{"id", "task", "started"}, ...]`` from the ledger.
    processes:    ``[{"pid", "started" (ps lstart), "cmd"}, ...]`` snapshot.
    """
    live_by_id: dict[str, list[dict]] = {}
    for proc in processes:
        for attempt_id in _ATTEMPT_DIR_RE.findall(proc.get("cmd", "")):
            live_by_id.setdefault(attempt_id, []).append(proc)

    used_pids: set[str] = set()
    classified: list[dict] = []
    for row in running_rows:
        row_epoch = _parse_iso(row.get("started", ""))
        entry = {
            "ledger_attempt_id": row.get("id"),
            "task_key": row.get("task"),
            "started_at": row.get("started"),
        }
        direct = live_by_id.get(row.get("id") or "")
        if direct:
            entry["classification"] = "LIVE_MATCHED_ATTEMPT_ID"
            entry["evidence"] = {
                "pids": sorted(p["pid"] for p in direct),
                "match": "attempt id found in process cmdline",
            }
            used_pids.update(p["pid"] for p in direct)
        else:
            candidates = []
            for proc in processes:
                if proc["pid"] in used_pids:
                    continue
                proc_epoch = _parse_ps_start(proc.get("started", ""))
                if row_epoch is None or proc_epoch is None:
                    continue
                delta = abs(proc_epoch - row_epoch)
                if delta <= start_window_s:
                    candidates.append((delta, proc))
            if candidates:
                candidates.sort(key=lambda pair: pair[0])
                delta, proc = candidates[0]
                entry["classification"] = "LIVE_MATCHED_BY_START_WINDOW"
                entry["evidence"] = {
                    "pids": [proc["pid"]],
                    "delta_s": round(delta, 3),
                    "process_started": proc.get("started"),
                    "match": "process start time within "
                             f"±{start_window_s:g}s of the ledger row",
                }
                used_pids.add(proc["pid"])
            else:
                entry["classification"] = "ORPHAN_NO_LIVE_PROCESS"
                entry["evidence"] = {
                    "pids": [],
                    "match": "no live process carries this attempt id or its "
                             "start time",
                }
                entry["action"] = (
                    "supervisor recover_interrupted under the run lock "
                    "(charges the reservation); RA-01 does not mutate the ledger"
                )
        classified.append(entry)

    live = sum(1 for r in classified if r["classification"].startswith("LIVE"))
    orphans = sum(1 for r in classified if r["classification"] == "ORPHAN_NO_LIVE_PROCESS")
    return {
        "schema": SCHEMA,
        "method": METHOD,
        "rows": classified,
        "summary": {"running_rows": len(classified), "live_matched": live,
                    "orphans": orphans},
    }