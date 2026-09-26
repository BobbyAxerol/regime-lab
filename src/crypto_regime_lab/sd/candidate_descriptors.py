"""SD-02: candidate descriptor rows z (guide SS5.5), built from an already-
committed SD-01 archive label row plus a real cache-hit re-fetch of the
IS-window activity/support descriptor.

SD-01's own committed ``origin_*.json`` files are NEVER modified to add this
field retroactively (this lab's own append-only evidence discipline) -- the
IS-window ``evaluate_candidate`` call was already made once per panel
candidate during SD01.7 and is fully cached (guide/lab convention: same
params/cutoff/economics -> identical cache key -> a real, zero-new-compute
cache HIT, verified by ``cache_event`` on every call this module makes).
"""
from __future__ import annotations

from . import archive as ar
from .contrast_features import raw_feature_row


class DescriptorError(ValueError):
    """A candidate-descriptor build step was internally inconsistent."""


def fetch_activity_entries(cache, root, alpha_id: str, load_real_bars_fn, params: dict, *,
                           origin_cutoff, symbol: str, economics: dict, producer: str) -> dict:
    """Re-derives the candidate's own IS-window entry count -- a real
    ``evaluate_candidate`` call that MUST be a cache HIT for any candidate
    SD-01 already scored (same params/cutoff/economics -> identical cache
    key); a MISS here for an already-archived candidate is treated as a
    genuine anomaly, not silently accepted, so callers can tell the
    difference between "reused" and "recomputed"."""
    import pandas as pd

    from ..fp.evaluator import evaluate_candidate

    bounds = ar.window_bounds(origin_cutoff, kind="IS")
    frame, _partitions = load_real_bars_fn(
        symbol, start=bounds["frame_start"].strftime("%Y-%m-%d"),
        end=(bounds["frame_end"] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    frame = frame[(frame.index >= bounds["frame_start"]) & (frame.index < bounds["frame_end"])]
    payload, cache_event = evaluate_candidate(cache, root, alpha_id, frame, params,
                                              cutoff=origin_cutoff, report_level="score",
                                              economics=economics, producer=producer)
    entries = payload["selected_audit"]["entries"]
    return {"entries": int(entries), "cache_event": cache_event["status"]}


def build_descriptor_row(schema, label_row: dict, *, activity_entries: int) -> dict:
    """One candidate's raw feature row z (guide SS5.5's default set), from
    an already-committed SD-01 archive ``label_row`` plus the fetched
    activity descriptor. Uses the label row's own canonical IS Sharpe
    (``is_window.sharpe``), never the search's cheap ``mean_is_sharpe_search_
    proxy`` (that proxy is explicitly for panel ranking only, guide SS3.5)."""
    if label_row["is_window"]["sharpe_status"] != "OK":
        raise DescriptorError(f"{label_row['candidate_id']}: IS sharpe_status="
                              f"{label_row['is_window']['sharpe_status']}, cannot build a descriptor")
    return raw_feature_row(schema, label_row["params"], is_sharpe=label_row["is_window"]["sharpe"],
                           activity_entries=activity_entries)
