"""RA06.1/10.2/10.3 Panel B: action benefit panel (guide section 10).

KEEP vs REFIT from the SAME real incumbent state at each origin, via
deterministic replay prefix through the installed engine (guide 10.3's
sanctioned fallback -- no native QuantBT checkpoint/clone-state capability
exists in this install; confirmed by inspection -- `grep` over
`src/crypto_regime_lab/` and the vendored engine copy found no
checkpoint/clone/fork-state API -- before choosing this path, not assumed).

KEEP: one continuous real account, schedule=[window_start] (the SAME single
selection RA-05's STATIC arm made), run once through the LAST origin's
horizon end -- covers every origin's KEEP branch in a single real run,
since none of them ever refit, and `run_cutoff_walk_forward`'s own fold
mechanics run the LAST (only) fold's test segment to the end of whatever
frame it is given, so one long frame gives every origin's KEEP reading in
one pass.

REFIT: one real account per origin, schedule=[window_start, origin] -- the
SAME initial selection (reproduced deterministically: same frame prefix,
same seed, same trials -> byte-identical to KEEP's own first fold) plus ONE
additional real search exactly at the origin, continued through that
origin's own horizon end (the frame is truncated per origin, since the
installed fold mechanics run to the frame's end, not to a schedule-level
"window_end" field). The shared, deterministic prefix is what gives both
branches the SAME real account state at the origin (guide 10.1: "ca hai
branches bat dau tu cung full account/strategy state") without a bespoke
state-fork API.
"""
from __future__ import annotations

import pandas as pd

from ..experiments.dynamic_fold_provider import (
    CutoffSchedule, ZeroSignalStrategy, engine_param_ranges, run_cutoff_walk_forward,
)


def _utc_iso(moment: str) -> str:
    """`CutoffSchedule`'s cutoffs must be explicit-UTC ISO strings -- a bare
    date like "2021-01-01" parses tz-naive and `_cutoff_folds` refuses it."""
    return pd.Timestamp(moment, tz="UTC").isoformat()


def build_refit_schedule(window_start: str, origin: str, *, train_memory_days: int) -> CutoffSchedule:
    return CutoffSchedule(
        arm="RA06_REFIT", kind="calendar", cutoffs=(_utc_iso(window_start), _utc_iso(origin)),
        train_memory_days=train_memory_days,
        source=(f"RA06 Panel B REFIT: shared initial selection at {window_start} (reproduces "
               "KEEP's own first fold deterministically), real refit search at "
               f"{origin}"),
    )


def build_keep_schedule(window_start: str, *, train_memory_days: int) -> CutoffSchedule:
    return CutoffSchedule(
        arm="RA06_KEEP", kind="calendar", cutoffs=(_utc_iso(window_start),),
        train_memory_days=train_memory_days,
        source=f"RA06 Panel B KEEP: single selection at {window_start}, never refits",
    )


def run_keep_branch(alpha_id: str, frame: pd.DataFrame, *, window_start: str,
                    train_memory_days: int, trials: int, seed: int, route: str) -> dict:
    schedule = build_keep_schedule(window_start, train_memory_days=train_memory_days)
    return run_cutoff_walk_forward(
        alpha_id, frame, schedule, param_ranges=engine_param_ranges(alpha_id),
        strategy_class=ZeroSignalStrategy, optuna_trials=trials, seed=seed, route=route)


def run_refit_branch(alpha_id: str, frame: pd.DataFrame, *, window_start: str, origin: str,
                     train_memory_days: int, trials: int, seed: int, route: str) -> dict:
    schedule = build_refit_schedule(window_start, origin, train_memory_days=train_memory_days)
    return run_cutoff_walk_forward(
        alpha_id, frame, schedule, param_ranges=engine_param_ranges(alpha_id),
        strategy_class=ZeroSignalStrategy, optuna_trials=trials, seed=seed, route=route)


def _equity_at(equity_daily: list, at: str, *, strictly_before: bool = False):
    """The real equity mark at, or immediately before, `at` (guide 10.2:
    both equities must be real engine outputs, never interpolated/invented).

    `strictly_before=True` excludes the mark ON `at` itself. This matters
    for E_t specifically: `run_cutoff_walk_forward`'s REFIT schedule makes
    `origin` the FIRST bar of the NEW fold (`test_start=origin`), so the
    equity mark dated exactly `origin` already reflects a full day of
    NEW-params trading -- reading it as "the state BEFORE the decision"
    would silently read the decision's own consequence into its own
    precondition. Confirmed empirically: KEEP and REFIT's marks match
    exactly through the day before origin and only diverge starting on
    origin's own day, exactly where the new fold's test_start begins.
    """
    target = pd.Timestamp(at, tz="UTC") if pd.Timestamp(at).tzinfo is None else pd.Timestamp(at)
    candidates = []
    for date, value in equity_daily:
        stamp = pd.Timestamp(date)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        if stamp < target or (not strictly_before and stamp == target):
            candidates.append((stamp, value))
    if not candidates:
        return None
    return max(candidates, key=lambda row: row[0])[1]


def compute_g(*, keep_account: dict, refit_account: dict, origin: str, horizon_end: str) -> dict:
    """guide 10.2: g_t(H) = (E_refit_{t+H} - E_keep_{t+H}) / E_t, E_t common.

    E_t is read STRICTLY BEFORE origin (see `_equity_at`) -- the last mark
    both branches share before the REFIT branch's new fold begins trading.
    Both E_t readings (from the KEEP run and the REFIT run) must still AGREE
    exactly -- they share the same deterministic prefix up to that point, so
    a mismatch means the prefix was not actually reproduced identically and
    the row is censored (null + reason), never silently averaged or trusted
    anyway (guide 10.2: censored outcomes get null + reason, never g=0).
    """
    keep_daily = keep_account.get("equity_daily") or []
    refit_daily = refit_account.get("equity_daily") or []
    e_t_keep = _equity_at(keep_daily, origin, strictly_before=True)
    e_t_refit = _equity_at(refit_daily, origin, strictly_before=True)
    e_keep_h = _equity_at(keep_daily, horizon_end)
    e_refit_h = _equity_at(refit_daily, horizon_end)
    if e_t_keep is None or e_t_refit is None or e_keep_h is None or e_refit_h is None:
        return {"status": "CENSORED", "reason": "missing real equity mark at origin or horizon end",
               "g": None, "e_t_keep": e_t_keep, "e_t_refit": e_t_refit,
               "e_keep_h": e_keep_h, "e_refit_h": e_refit_h}
    prefix_mismatch = abs(e_t_keep - e_t_refit) > max(1e-6, 1e-9 * abs(e_t_keep))
    if prefix_mismatch:
        return {"status": "CENSORED",
               "reason": (f"E_t disagrees between branches (keep={e_t_keep}, refit={e_t_refit}); "
                         "the shared deterministic prefix did not reproduce identically"),
               "g": None, "e_t_keep": e_t_keep, "e_t_refit": e_t_refit,
               "e_keep_h": e_keep_h, "e_refit_h": e_refit_h}
    e_t = e_t_keep
    if e_t == 0:
        return {"status": "CENSORED", "reason": "E_t is zero", "g": None,
               "e_t_keep": e_t_keep, "e_t_refit": e_t_refit,
               "e_keep_h": e_keep_h, "e_refit_h": e_refit_h}
    return {"status": "OK", "reason": None, "g": (e_refit_h - e_keep_h) / e_t,
           "e_t_keep": e_t_keep, "e_t_refit": e_t_refit,
           "e_keep_h": e_keep_h, "e_refit_h": e_refit_h}


def build_panel_b(alpha_id: str, frame: pd.DataFrame, *, window_start: str, origins: list[str],
                  horizon_days: int, train_memory_days: int, trials: int, seed: int, route: str,
                  emissions: list[dict]) -> dict:
    """RA06.1/10.2/10.3/10.4/10.5 tied together: one shared real KEEP run,
    one real REFIT run per origin, real causal features for each origin,
    real g_t(H). Every row is either OK or CENSORED with a reason -- never a
    fabricated 0 (guide 10.2).
    """
    from .ra06_features import build_origin_features

    last_horizon_end = (pd.Timestamp(origins[-1]) + pd.Timedelta(days=horizon_days)).isoformat()
    keep_frame = frame.loc[frame.index < pd.Timestamp(last_horizon_end)]
    keep_result = run_keep_branch(alpha_id, keep_frame, window_start=window_start,
                                  train_memory_days=train_memory_days, trials=trials, seed=seed,
                                  route=route)
    if not keep_result.get("ok"):
        return {"schema": "regime_lab.ra06_panel_b.v1", "capability_status": "BLOCKED_CAPABILITY",
               "blocked_reason": f"KEEP branch failed: {keep_result.get('error')}", "rows": []}
    keep_account = keep_result["account"]
    keep_equity_daily = keep_account.get("equity_daily") or []

    rows = []
    for origin in origins:
        horizon_end = (pd.Timestamp(origin) + pd.Timedelta(days=horizon_days)).isoformat()
        origin_frame = frame.loc[frame.index < pd.Timestamp(horizon_end)]
        refit_result = run_refit_branch(alpha_id, origin_frame, window_start=window_start,
                                        origin=origin, train_memory_days=train_memory_days,
                                        trials=trials, seed=seed, route=route)
        if not refit_result.get("ok"):
            rows.append({"origin": origin, "status": "CENSORED",
                        "reason": f"REFIT branch failed: {refit_result.get('error')}",
                        "g": {"status": "CENSORED", "g": None,
                              "reason": f"REFIT branch failed: {refit_result.get('error')}"},
                        "features": None})
            continue
        g = compute_g(keep_account=keep_account, refit_account=refit_result["account"],
                     origin=origin, horizon_end=horizon_end)
        features = build_origin_features(origin=origin, window_start=window_start, frame=frame,
                                         emissions=emissions, keep_equity_daily=keep_equity_daily)
        rows.append({
            "origin": origin, "horizon_end": horizon_end, "horizon_days": horizon_days,
            "status": g["status"], "g": g, "features": features,
            "keep_incumbent_params": keep_result["fold_selection_table"][0]["selected_params"],
            "refit_selected_params": (refit_result["fold_selection_table"][1]["selected_params"]
                                      if len(refit_result["fold_selection_table"]) > 1 else None),
            "keep_wall_seconds": keep_result.get("wall_seconds"),
            "refit_wall_seconds": refit_result.get("wall_seconds"),
        })
    return {
        "schema": "regime_lab.ra06_panel_b.v1", "capability_status": "EXECUTED",
        "window_start": window_start, "horizon_days": horizon_days,
        "train_memory_days": train_memory_days, "trials": trials, "seed": seed, "route": route,
        "state_fork_method": ("deterministic replay prefix through run_cutoff_walk_forward -- no "
                              "native QuantBT checkpoint/clone-state capability exists in this "
                              "install (guide 10.3's sanctioned fallback)"),
        "keep_run": {"ok": True, "wall_seconds": keep_result.get("wall_seconds"),
                    "fold_count": keep_result.get("fold_count")},
        "rows": rows,
        "row_count": len(rows),
        "ok_count": sum(1 for r in rows if r["status"] == "OK"),
        "censored_count": sum(1 for r in rows if r["status"] == "CENSORED"),
    }
