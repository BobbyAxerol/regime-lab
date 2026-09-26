"""SD-03: D2 frozen continuations (guide SS2.4).

At each of the 12 FINAL origins, for a candidate's ALREADY-SELECTED,
UNCHANGED params theta_k, measure aging decay:

    H1 = [origin_cutoff, origin_cutoff + 56 days)
    H2 = [origin_cutoff + 56 days, origin_cutoff + 112 days)
    D_age = SR_H1(theta) - SR_H2(theta)

The account is NEVER reset at the H1/H2 boundary -- this module makes ONE
real 112-day ``evaluate_candidate`` call per candidate (a single continuous
account) and SPLITS its own daily-return series into H1/H2 halves, rather
than two separate 56-day calls. H1's own Sharpe should match the candidate's
already-computed FWD-window Sharpe from the FINAL archive build (same
params, same start, same 56 days) -- a real parity check, not assumed.
"""
from __future__ import annotations

from ..fp.evaluator import evaluate_candidate
from ..ra.ra07_stats_primitives import sharpe as _typed_sharpe
from ..time_edge.metrics import account_returns

H1_DAYS = 56
H2_DAYS = 56
D2_TOTAL_DAYS = H1_DAYS + H2_DAYS
PRE_ROLL_DAYS = 2


class D2Error(ValueError):
    """A D2 continuation step was internally inconsistent."""


def d2_window_bounds(origin_cutoff) -> dict:
    import pandas as pd

    cutoff = pd.Timestamp(origin_cutoff, tz="UTC")
    score_start = cutoff
    h1_end = cutoff + pd.Timedelta(days=H1_DAYS)
    score_end = cutoff + pd.Timedelta(days=D2_TOTAL_DAYS)
    frame_start = score_start - pd.Timedelta(days=PRE_ROLL_DAYS)
    return {"frame_start": frame_start, "frame_end": score_end, "score_start": score_start,
           "h1_end": h1_end, "score_end": score_end}


def candidate_d2_continuation(cache, root, alpha_id: str, load_real_bars_fn, params: dict, *,
                              origin_cutoff, symbol: str, economics: dict, producer: str) -> dict:
    """ONE real continuous 112-day evaluate_candidate call, split into H1/H2
    canonical Sharpe -- no reset at the boundary. Returns a typed status on
    any window-build failure, never a fabricated Sharpe."""
    import pandas as pd

    bounds = d2_window_bounds(origin_cutoff)
    frame, _partitions = load_real_bars_fn(
        symbol, start=bounds["frame_start"].strftime("%Y-%m-%d"),
        end=(bounds["score_end"] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    frame = frame[(frame.index >= bounds["frame_start"]) & (frame.index < bounds["score_end"])]
    if not len(frame):
        return {"status": "EMPTY_FRAME", "sr_h1": None, "sr_h2": None, "d_age": None}

    payload, cache_event = evaluate_candidate(cache, root, alpha_id, frame, params,
                                              cutoff=origin_cutoff, report_level="score",
                                              economics=economics, producer=producer)
    audit = payload["selected_audit"]
    initial_equity = economics["initial_capital"]
    try:
        rows = account_returns(audit["equity"], frame.index, initial_equity=initial_equity,
                               start=bounds["score_start"].isoformat(), end=bounds["score_end"].isoformat())
    except Exception as exc:   # noqa: BLE001 -- ContractError from time_edge; typed status below
        return {"status": "WINDOW_BUILD_FAILED", "reason": str(exc), "sr_h1": None, "sr_h2": None,
               "d_age": None}
    if len(rows) != D2_TOTAL_DAYS:
        return {"status": "WRONG_DAY_COUNT", "reason": f"expected {D2_TOTAL_DAYS}, got {len(rows)}",
               "sr_h1": None, "sr_h2": None, "d_age": None}

    h1_end = bounds["h1_end"]
    h1_returns = [r for d, r in rows if pd.Timestamp(d, tz="UTC") < h1_end]
    h2_returns = [r for d, r in rows if pd.Timestamp(d, tz="UTC") >= h1_end]
    if len(h1_returns) != H1_DAYS or len(h2_returns) != H2_DAYS:
        return {"status": "BOUNDARY_SPLIT_MISMATCH",
               "reason": f"h1={len(h1_returns)}, h2={len(h2_returns)}, expected {H1_DAYS}/{H2_DAYS}",
               "sr_h1": None, "sr_h2": None, "d_age": None}

    h1_result = _typed_sharpe(h1_returns)
    h2_result = _typed_sharpe(h2_returns)
    if h1_result["status"] != "OK" or h2_result["status"] != "OK":
        return {"status": "UNDEFINED_SHARPE", "sr_h1": h1_result, "sr_h2": h2_result, "d_age": None,
               "cache_event": cache_event["status"]}
    return {"status": "OK", "sr_h1": h1_result["value"], "sr_h2": h2_result["value"],
           "d_age": h1_result["value"] - h2_result["value"], "cache_event": cache_event["status"],
           "n_days_total": len(rows)}
