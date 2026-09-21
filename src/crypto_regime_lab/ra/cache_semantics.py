"""Pure cache-semantics helpers for RA-02 (RA-GUIDE-1.0 §6 RA02.2/RA02.7).

Nothing here touches I/O beyond reading the objects passed in. They encode
the two contracts the cache layer must respect:

* prefix hashing — a task that may only consume data up to a cutoff is keyed
  by a digest of exactly that prefix (precise coverage: row count, first and
  last timestamp, content bytes). A future suffix mutation never changes the
  key; a prefix mutation always does.
* causality on warm cache — a cache hit may only be consumed at a decision
  cutoff when its outcome was already available (mature) at or before that
  cutoff, and the three time coordinates (physical_compute_at,
  simulated_cutoff, simulated_ready_at) are captured separately so a warm
  hit can never be misreported as executed-at-decision-time.
"""
from __future__ import annotations

from datetime import datetime, timezone

PREFIX_DIGEST_SCHEMA = "regime_lab.ra02_prefix_digest.v1"
CAUSALITY_FIELDS = ("physical_compute_at", "simulated_cutoff", "simulated_ready_at")
STATE_MODES = ("fresh", "carry")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse(ts) -> datetime | None:
    if ts is None or ts == 0 or ts == "":
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def prefix_digest(frame, until) -> dict:
    """Digest of the frame rows up to ``until`` (inclusive) — nothing more.

    ``until`` is a timestamp or positional row count. The digest covers the
    exact prefix slice (precise coverage recorded), so appending future rows
    leaves it unchanged while any prefix mutation changes it.
    """
    import hashlib

    if not hasattr(frame, "iloc") or not hasattr(frame, "index"):
        raise TypeError("prefix_digest needs a pandas-like frame")
    if isinstance(until, int) and not isinstance(until, bool):
        prefix = frame.iloc[:until]
        coverage = {"rows": int(until), "mode": "positional"}
    else:
        ts = _parse(until)
        if ts is None:
            raise TypeError("until must be a row count or a parseable timestamp")
        prefix = frame.loc[:pd_timestamp(ts)]
        coverage = {"rows": int(len(prefix)), "mode": "timestamp",
                    "until": ts.isoformat()}
    if len(prefix) == 0:
        raise ValueError("prefix_digest refuses an empty prefix")
    payload = prefix.to_csv(index=True, lineterminator="\n").encode("utf-8")
    return {"schema": PREFIX_DIGEST_SCHEMA, **coverage,
            "first": str(prefix.index[0]), "last": str(prefix.index[-1]),
            "sha256": hashlib.sha256(payload).hexdigest()}


def pd_timestamp(ts: datetime):
    import pandas as pd
    return pd.Timestamp(ts)


def assert_causal_hit(record: dict, *, cutoff) -> dict:
    """Validate that one cache record may be consumed at ``cutoff``.

    Rejects (raises ValueError, never silently passes):
    * a record missing any of the three causality coordinates;
    * a zero/absent simulated_ready_at (a warm hit must carry a real
      availability time, never 0);
    * an outcome that matures after the decision cutoff (future information);
    * a simulated_cutoff that does not match the consuming cutoff.
    Returns the parsed coordinates on success.
    """
    missing = [field for field in CAUSALITY_FIELDS if field not in record]
    if missing:
        raise ValueError("cache hit lacks causality fields: " + ", ".join(missing))
    parsed = {field: _parse(record[field]) for field in CAUSALITY_FIELDS}
    absent = [field for field, value in parsed.items() if value is None]
    if absent:
        raise ValueError("cache hit causality fields unset/zero: " + ", ".join(absent))
    if parsed["simulated_ready_at"] == _EPOCH:
        raise ValueError("cached ready_at must never be the epoch/zero sentinel")
    consuming = _parse(cutoff)
    if consuming is None:
        raise ValueError("consuming cutoff unparseable")
    if parsed["simulated_cutoff"] != consuming:
        raise ValueError(
            f"cache hit was computed for cutoff {parsed['simulated_cutoff'].isoformat()} "
            f"but is being consumed at {consuming.isoformat()}")
    if parsed["simulated_ready_at"] > consuming:
        raise ValueError(
            f"cache outcome matures at {parsed['simulated_ready_at'].isoformat()}, "
            f"after the consuming cutoff {consuming.isoformat()}: future information")
    return parsed


def assert_state_compatible(cached_state: dict, requested_state: dict) -> None:
    """Typed initial-state compatibility for a cached deployment artifact.

    Reusing an account artifact across a fresh vs carry initial state is a
    false HIT: the account starts from a different equity/position state, so
    the produced bytes cannot be equivalent. Rejects (ValueError):
    * a missing/unknown ``mode`` on either side;
    * mismatched modes (the facet should have produced a MISS, so reaching
      here means a caller tried to reuse across states);
    * a carry state that does not restate the carried equity/position.
    """
    if not isinstance(cached_state, dict) or not isinstance(requested_state, dict):
        raise ValueError("initial state must be a declared object")
    for label, state in (("cached", cached_state), ("requested", requested_state)):
        mode = state.get("mode")
        if mode not in STATE_MODES:
            raise ValueError(f"{label} initial state has unknown mode: {mode!r}")
    if cached_state["mode"] != requested_state["mode"]:
        raise ValueError(
            "initial-state mode mismatch: cached "
            f"{cached_state['mode']!r} vs requested {requested_state['mode']!r} "
            "is a typed incompatibility, never a false HIT")
    if requested_state["mode"] == "carry":
        for field in ("carried_equity", "carried_position"):
            if field not in requested_state:
                raise ValueError(
                    "carry initial state must restate " + field
                    + " (cannot be reconstructed from a few equity/position variables)")
