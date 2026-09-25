"""SD01.7: real INIT archive build (guide SS3.5, SS8.2).

Two-stage, cost-aware design per origin:

  1. CHEAP ranking for the representative panel: guide SS3.5's own
     "chon IS-only truoc forward" uses the search's OWN already-computed
     per-trial ``mean_is_sharpe`` (a mean-shard-IS Sharpe WITH a trade-count
     penalty, computed inside the engine during search) as a ranking proxy
     -- zero extra engine calls. This is explicitly NOT the canonical IS
     Sharpe guide SS2.2 wants for the real D1 label ("IS la raw Sharpe tren
     full 180-day scoring window, khong penalized optimizer objective") --
     it is used ONLY to decide which <=16 candidates are worth spending
     real forward-evaluation compute on, never as the label itself.
  2. REAL canonical Sharpe for the representative panel + anchor: two fresh
     ``fp.evaluator.evaluate_candidate`` calls per candidate (IS180
     flat-start ending at the origin cutoff, FWD56 flat-start AT the origin
     cutoff -- guide SS6.2's own asymmetry: forward is NOT a continuation of
     the IS account, both start declared-flat, disclosed symmetrically),
     canonical Sharpe via ``sd.metrics.window_sharpe`` composed with
     ``time_edge.metrics.account_returns`` for the raw-equity-to-daily-
     returns step (gap-checked, exact-day-count, preceding-equity base --
     the SAME already-tested primitive SD01.4 reuses).
"""
from __future__ import annotations

PANEL_MAX_SIZE = 16
PRE_ROLL_DAYS = 2   # safely exceeds A-SC's warmup_bars() (AP+3 minutes, tiny vs 180/56 days)


class ArchiveError(ValueError):
    """An archive-build step was internally inconsistent."""


def unique_candidates(trial_records: list[dict]) -> list[dict]:
    """Every unique effective (params) point actually evaluated by the
    search (guide SS3.2: 'moi unique effective candidates hop le da duoc
    evaluate') -- the FULL pool B/C will predict over in SD-02/03, never
    capped here (the cap applies only to the label-evaluation panel below,
    guide SS3.5)."""
    seen: dict = {}
    for r in trial_records:
        if r.get("pruned"):
            continue
        key = tuple(sorted(r["params"].items()))
        if key not in seen:
            seen[key] = r
    return list(seen.values())


def representative_panel(candidates: list[dict], *, anchor_params: dict,
                         max_size: int = PANEL_MAX_SIZE) -> list[dict]:
    """Deterministic subset: rank by the search's own mean_is_sharpe
    (descending -- cheap IS-only proxy), cap at max_size, MUST include the
    anchor (added if not already present in the top max_size). Ties break
    by trial_id for full determinism."""
    ranked = sorted(candidates, key=lambda r: (-r["mean_is_sharpe"], r["trial_id"]))
    panel = ranked[:max_size]
    anchor_key = tuple(sorted(anchor_params.items()))
    if not any(tuple(sorted(r["params"].items())) == anchor_key for r in panel):
        anchor_rows = [r for r in candidates if tuple(sorted(r["params"].items())) == anchor_key]
        if not anchor_rows:
            raise ArchiveError("anchor params not found among the search's own candidates -- "
                               "the stock winner must be a real evaluated trial")
        panel = panel[: max_size - 1] + [anchor_rows[0]]
    return panel


def window_bounds(origin_cutoff, *, kind: str):
    """IS: [cutoff-180d, cutoff). FWD: [cutoff, cutoff+56d). Both frames
    requested with PRE_ROLL_DAYS of pre-roll before their own scored start
    for warmup -- guide SS6.2: pre-roll is not part of the scored metric."""
    import pandas as pd

    cutoff = pd.Timestamp(origin_cutoff, tz="UTC")
    if kind == "IS":
        score_start = cutoff - pd.Timedelta(days=180)
        score_end = cutoff
    elif kind == "FWD":
        score_start = cutoff
        score_end = cutoff + pd.Timedelta(days=56)
    else:
        raise ArchiveError(f"unknown window kind {kind!r}")
    frame_start = score_start - pd.Timedelta(days=PRE_ROLL_DAYS)
    return {"frame_start": frame_start, "frame_end": score_end,
           "score_start": score_start, "score_end": score_end}


def candidate_window_sharpe(cache, root, alpha_id: str, load_real_bars_fn, params: dict, *,
                            origin_cutoff, kind: str, symbol: str, economics: dict,
                            producer: str) -> dict:
    """One real evaluate_candidate call + canonical Sharpe for one
    candidate's IS or FWD window at one origin. Reuses
    fp.evaluator.evaluate_candidate VERBATIM (same cache kind
    "fp_candidate") -- the raw account computation (given identical alpha/
    market/params/cutoff/economics) is genuinely identical regardless of
    which study asks for it, so this is a legitimate, real cache-hit
    opportunity across studies, never a target-definition conflation (the
    RETURNS this function derives from the raw equity are SD's own
    canonical Sharpe computation, entirely separate from anything FP ever
    cached as a label)."""
    import pandas as pd

    from ..fp.evaluator import evaluate_candidate
    from ..time_edge.metrics import account_returns
    from .metrics import IS_WINDOW_DAYS, FORWARD_WINDOW_DAYS
    from ..ra.ra07_stats_primitives import sharpe as _typed_sharpe

    bounds = window_bounds(origin_cutoff, kind=kind)
    frame, _partitions = load_real_bars_fn(
        symbol, start=bounds["frame_start"].strftime("%Y-%m-%d"),
        end=(bounds["frame_end"] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    frame = frame[(frame.index >= bounds["frame_start"]) & (frame.index < bounds["frame_end"])]
    if not len(frame):
        raise ArchiveError(f"empty frame for {kind} window at {origin_cutoff}")

    payload, cache_event = evaluate_candidate(cache, root, alpha_id, frame, params,
                                              cutoff=origin_cutoff, report_level="score",
                                              economics=economics, producer=producer)
    audit = payload["selected_audit"]
    #: SD02.1 panel-only scope decision (owner dec-c94ea602aeac0f1a,
    #: protocol_migration.json F03b scope_revision_sd02_20260925): the IS-kind
    #: call already computes this candidate's real entry count as a byproduct
    #: -- exposing it here means SD-02's own activity/support descriptor never
    #: needs a SEPARATE evaluate_candidate call for a freshly-built (VALIDATION)
    #: origin. INIT's already-committed origin_*.json files predate this field
    #: and are backfilled separately via candidate_descriptors.fetch_activity_entries.
    entries = int(audit["entries"]) if kind == "IS" else None
    initial_equity = economics["initial_capital"]
    expected_days = IS_WINDOW_DAYS if kind == "IS" else FORWARD_WINDOW_DAYS
    try:
        rows = account_returns(audit["equity"], frame.index, initial_equity=initial_equity,
                               start=bounds["score_start"].isoformat(),
                               end=bounds["score_end"].isoformat())
    except Exception as exc:   # noqa: BLE001 -- ContractError from time_edge; typed status below
        return {"sharpe": None, "sharpe_status": "WINDOW_BUILD_FAILED", "reason": str(exc),
               "n_days": 0, "kind": kind, "entries": entries}
    returns = [r[1] for r in rows]
    if len(returns) != expected_days:
        return {"sharpe": None, "sharpe_status": "WRONG_DAY_COUNT",
               "reason": f"expected {expected_days}, got {len(returns)}", "n_days": len(returns),
               "kind": kind, "entries": entries}
    result = _typed_sharpe(returns)
    return {"sharpe": result["value"], "sharpe_status": result["status"],
           "n_days": len(returns), "kind": kind, "cache_event": cache_event["status"],
           "entries": entries}
