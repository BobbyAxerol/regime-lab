"""RA-01 resource admission (RA-GUIDE-1.0 §5 RA01.5, G01-BUDGET).

Pure logic, no I/O: given a job request, the live budget state and the
frozen caps, return ADMIT or BLOCKED with named reasons. A new run ID never
resets the charged amount — the caller supplies the ledger's charged total.
"""

from __future__ import annotations


def admit_job(request: dict, budget: dict, caps: dict) -> dict:
    """Decide whether one job may launch.

    request: {requested_wall_s, requested_rss_gb, workers, retries_used}
    budget:  {total_wall_s, charged_wall_s}
    caps:    {per_task_wall_s, per_process_rss_gb, max_workers, max_retry}
    """
    reasons: list[str] = []
    try:
        wall = float(request["requested_wall_s"])
        rss = float(request["requested_rss_gb"])
        workers = int(request["workers"])
        retries = int(request.get("retries_used", 0))
        total = float(budget["total_wall_s"])
        charged = float(budget["charged_wall_s"])
        cap_wall = float(caps["per_task_wall_s"])
        cap_rss = float(caps["per_process_rss_gb"])
        cap_workers = int(caps["max_workers"])
        cap_retry = int(caps["max_retry"])
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "BLOCKED", "reasons": [f"malformed admission input: {exc}"]}

    if workers > cap_workers:
        reasons.append(f"workers {workers} exceeds max_workers {cap_workers}")
    if wall > cap_wall:
        reasons.append(f"requested_wall_s {wall} exceeds per_task_wall_s {cap_wall}")
    if rss > cap_rss:
        reasons.append(f"requested_rss_gb {rss} exceeds per_process_rss_gb {cap_rss}")
    if retries > cap_retry:
        reasons.append(f"retries_used {retries} exceeds max_retry {cap_retry}")
    remaining = total - charged
    if wall > remaining:
        reasons.append(
            f"requested_wall_s {wall} exceeds remaining budget {remaining:.1f} "
            f"(total {total}, charged {charged}): BLOCKED_BUDGET"
        )

    if reasons:
        status = "BLOCKED_BUDGET" if any("BLOCKED_BUDGET" in r for r in reasons) else "BLOCKED"
        return {"status": status, "reasons": reasons,
                "remaining_wall_s": remaining}
    return {"status": "ADMIT", "reasons": [], "remaining_wall_s": remaining}
