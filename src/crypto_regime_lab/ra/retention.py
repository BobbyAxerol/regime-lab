"""Retention tiers for account-run outputs (RA-GUIDE-1.0 RA03.3).

Three named policies over one ``PreparedAccount.run()`` result. Each is a pure
reducer: given the same real run, every tier's numbers agree exactly with the
others where they overlap (M04), and ``CANDIDATE_COMPACT`` is *derived from*
``SELECTED_AUDIT`` by a declared function rather than recomputed independently
(M05) -- so "compact" can never silently drift from the audit trace it claims
to summarize.

These are lab policy names, not QuantBT API kwargs (the guide is explicit
about that distinction) -- nothing here changes what the engine computes or
retains internally; it only decides what this lab keeps in memory/on disk
after a run has already produced its full result dict.
"""
from __future__ import annotations

TIERS = ("TRIAL_SCALAR", "CANDIDATE_COMPACT", "SELECTED_AUDIT")

# What each tier keeps, and the guide clause it answers to. This is the
# audit trail for "why does this field exist at this tier" -- read it before
# adding or removing a field.
TRIAL_SCALAR_FIELDS = (
    "status", "engine_fill_count", "callback_count", "decision_count",
    "wall_seconds", "packing_seconds", "requested_contract",
    "engine_absolute_start_bar", "terminal_equity", "terminal_position",
)
CANDIDATE_COMPACT_FIELDS = (
    "status", "daily_returns", "metrics", "daily_activity",
    "complete_day_start", "complete_day_end_exclusive",
    "fill_count", "order_event_count", "rejection_count",
)
SELECTED_AUDIT_FIELDS = (
    "status", "equity", "positions", "index", "fills", "commands",
    "order_events", "version_runs", "funnel", "unmapped", "rejections",
    "engine_fill_count", "requested_contract", "wall_seconds",
    "packing_seconds", "callback_count", "decision_count",
    "engine_absolute_start_bar", "terminal_position", "terminal_equity",
)


def to_trial_scalar(run: dict) -> dict:
    """RA03.3 TRIAL_SCALAR: full trial metadata/status/costs/counters.

    Never a redundant per-bar object -- no equity/positions arrays, no fill
    list; every value here is O(1) in the run's bar count.
    """
    return {field: run[field] for field in TRIAL_SCALAR_FIELDS if field in run}


def to_selected_audit(run: dict) -> dict:
    """RA03.3 SELECTED_AUDIT: the reconstructable path -- orders, fills,
    rejects, amends/cancels (inside ``commands``/``order_events``), account
    invariants and version/activation lineage. This is the full run, minus
    engine-internal bookkeeping (``engine_metadata``/``engine_tables``) that
    the audit rerun in ``workers.py::audit_selection`` already treats as
    diagnostic rather than reconstructable state.
    """
    return {field: run[field] for field in SELECTED_AUDIT_FIELDS if field in run}


def to_candidate_compact(run: dict, *, daily_returns, metrics, daily_activity,
                         complete_day_start, complete_day_end_exclusive) -> dict:
    """RA03.3 CANDIDATE_COMPACT built directly, when the caller already has
    the registered return/metric computation (this is what
    ``TrainingScorer._score`` computes today) -- required return/equity
    observations plus report support for the registered targets/metrics,
    never the full audit trace.
    """
    return {
        "status": run["status"],
        "daily_returns": list(daily_returns),
        "metrics": metrics,
        "daily_activity": list(daily_activity),
        "complete_day_start": complete_day_start,
        "complete_day_end_exclusive": complete_day_end_exclusive,
        "fill_count": len(run.get("fills") or []),
        "order_event_count": len(run.get("order_events") or []),
        "rejection_count": len(run.get("rejections") or []),
        # Trace REFERENCE, not the trace itself (RA03.3: "trace references").
        "audit_trace_ref": {
            "fills": len(run.get("fills") or []),
            "commands": len(run.get("commands") or []),
            "order_events": len(run.get("order_events") or []),
        },
    }


def candidate_compact_from_audit(audit: dict, *, account_returns, describe,
                                 window_activity, initial_equity=20000.,
                                 start, end) -> dict:
    """M05: derive CANDIDATE_COMPACT from SELECTED_AUDIT alone, using the
    SAME reducer functions (``account_returns``/``describe``/``window_activity``
    from ``time_edge.metrics``) production code already uses, so the compact
    form is provably a strict function of the audit trace -- never an
    independently-recomputed number that could silently diverge from it.
    First-return and fee information must not be lost: this asserts on the
    caller's behalf by construction (the same reducer that produces the
    canonical daily_returns is the one called here).
    """
    rows = account_returns(audit["equity"], audit["index"],
                           initial_equity=initial_equity, start=start, end=end)
    daily_activity = []
    for date, _ in rows:
        import pandas as pd
        day = pd.Timestamp(date, tz="UTC")
        daily_activity.append({
            "date": date,
            **window_activity(audit["fills"], audit["index"], audit["equity"],
                              start=day, end=day + pd.Timedelta(days=1),
                              initial_equity=initial_equity),
        })
    return to_candidate_compact(
        audit, daily_returns=rows, metrics=describe(rows),
        daily_activity=daily_activity,
        complete_day_start=start.isoformat() if hasattr(start, "isoformat") else start,
        complete_day_end_exclusive=end.isoformat() if hasattr(end, "isoformat") else end)


def tier_sizes(run: dict) -> dict:
    """Measured (not estimated) byte sizes of each tier's strict-JSON form,
    for the retention_contract.json report -- the "don't keep uselessly"
    half of RA03.3 needs an actual number, not an adjective.
    """
    from ..evidence.manifest import dumps_strict

    scalar = to_trial_scalar(run)
    audit = to_selected_audit(run)
    return {
        "TRIAL_SCALAR_bytes": len(dumps_strict(_jsonable(scalar))),
        "SELECTED_AUDIT_bytes": len(dumps_strict(_jsonable(audit))),
        "ratio_audit_over_scalar": (
            len(dumps_strict(_jsonable(audit))) / max(1, len(dumps_strict(_jsonable(scalar))))),
    }


def _jsonable(value):
    """Make numpy arrays/pandas objects JSON-strict for a size measurement
    only -- this is not the evidence writer's own ``jsonable`` (kept
    dependency-light so the size probe never needs the full run pipeline).
    """
    import numpy as np
    import pandas as pd

    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, pd.Index):
        return [str(v) for v in value]
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value
