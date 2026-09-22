"""FP-02 item 5: compact scoring retention, separate from the full selected
audit -- the same three-tier design ``ra/retention.py`` (RA-GUIDE-1.0 RA03.3)
already proved for ``PreparedAccount.run()``'s dict shape, adapted here to
``EventAccountRun``'s actual fields (``integration/event_account.py``) rather
than force-fit onto a shape it was never built for.

``CANDIDATE_COMPACT`` is *derived from* ``SELECTED_AUDIT`` by a declared
function, exactly like ``ra/retention.py::candidate_compact_from_audit`` --
so "compact" can never silently drift from the audit trace it claims to
summarize.
"""
from __future__ import annotations

TIERS = ("TRIAL_SCALAR", "CANDIDATE_COMPACT", "SELECTED_AUDIT")

TRIAL_SCALAR_FIELDS = ("status", "entries", "engine_fill_count",
                       "terminal_equity", "terminal_position")
SELECTED_AUDIT_FIELDS = ("status", "equity", "positions", "fills",
                         "commands", "order_events", "version_by_bar",
                         "entries", "engine_fill_count", "unmapped_intents",
                         "rejections", "order_ids_by_version", "diagnostics")


def _terminal(record: dict) -> dict:
    equity = record["equity"]
    positions = record["positions"]
    return {"terminal_equity": float(equity[-1]) if len(equity) else None,
            "terminal_position": float(positions[-1]) if len(positions) else None}


def to_trial_scalar(record: dict) -> dict:
    """TRIAL_SCALAR: O(1) in bar count -- no equity/positions/fills arrays."""
    enriched = {**record, **_terminal(record)}
    return {field: enriched[field] for field in TRIAL_SCALAR_FIELDS if field in enriched}


def to_selected_audit(record: dict, *, index) -> dict:
    """SELECTED_AUDIT: the reconstructable path -- fills, commands, order
    events, per-bar version and the strategy's own diagnostics (switches
    included). ``index`` (the frame's DatetimeIndex) is passed separately
    since EventAccountRun keeps it off the dict this module receives."""
    out = {field: record[field] for field in SELECTED_AUDIT_FIELDS if field in record}
    out["index"] = [str(ts) for ts in index]
    return out


def to_candidate_compact(audit: dict, *, daily_returns, metrics) -> dict:
    """CANDIDATE_COMPACT built directly, when the caller already has the
    registered return/metric computation (time_edge.metrics reducers) --
    required return/equity observations plus report support, never the full
    audit trace."""
    return {
        "status": audit["status"],
        "daily_returns": list(daily_returns),
        "metrics": metrics,
        "fill_count": len(audit.get("fills") or []),
        "order_event_count": len(audit.get("order_events") or []),
        "entries": audit.get("entries"),
        # Trace reference, not the trace itself.
        "audit_trace_ref": {
            "fills": len(audit.get("fills") or []),
            "commands": len(audit.get("commands") or []),
            "order_events": len(audit.get("order_events") or []),
        },
    }


def candidate_compact_from_audit(audit: dict, *, account_returns, describe,
                                 initial_equity: float, index) -> dict:
    """M05-style derivation (ra/retention.py): CANDIDATE_COMPACT from
    SELECTED_AUDIT alone, using the SAME reducers production code uses, so
    the compact form is provably a strict function of the audit trace."""
    import numpy as np

    rows = account_returns(np.asarray(audit["equity"], dtype=float), index,
                           initial_equity=initial_equity, start=index[0], end=index[-1])
    return to_candidate_compact(audit, daily_returns=rows, metrics=describe(rows))


def tier_sizes(record: dict, *, index) -> dict:
    """Measured (not estimated) byte sizes of each tier's strict-JSON form."""
    from ..evidence.manifest import dumps_strict

    scalar = to_trial_scalar(record)
    audit = to_selected_audit(record, index=index)
    scalar_bytes = len(dumps_strict(_jsonable(scalar)))
    audit_bytes = len(dumps_strict(_jsonable(audit)))
    return {"TRIAL_SCALAR_bytes": scalar_bytes, "SELECTED_AUDIT_bytes": audit_bytes,
            "ratio_audit_over_scalar": audit_bytes / max(1, scalar_bytes)}


def _jsonable(value):
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
