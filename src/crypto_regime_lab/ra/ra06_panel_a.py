"""RA06.1 Panel A: candidate/behavior panel (guide section 10.1).

`origin x candidate x matured outcome x available context`. Reused directly
from RA-05's real evidence (guide 10.1: "Tai su dung actual QuantBT
evaluations neu cung initial/reset/carry contract") -- RA-05's 4 arms
already ran the SAME alpha/frame/fee/route contract this phase needs (same
account_capital, same fee/slippage binding, same route), so Panel A costs
NO new engine calls: every row's "matured outcome" is the arm's own REAL
account equity path, sliced over that candidate's actual deployment window
-- never a re-run, never a column-switch/summed-return fabrication (guide
explicitly forbids using Panel A to synthesize a policy account PnL).
"""
from __future__ import annotations

import json

import pandas as pd

from ..time_edge.storage import digest
from .phase_common import LAB

RA05_STUDY = "regime_time_edge_ra_v1"


def load_ra05_arms_result(run_id: str) -> dict:
    path = LAB / "evidence" / RA05_STUDY / run_id / "arms_result.json"
    document = json.loads(path.read_text())
    return document["arms"], path


def _deployment_return(equity_daily: list, *, start: str, end: str) -> dict:
    """Real return over [start, end) from the arm's own equity_daily -- the
    matured OOS outcome for whichever candidate was active in that span.
    """
    rows = [(pd.Timestamp(date), value) for date, value in equity_daily
           if pd.Timestamp(start) <= pd.Timestamp(date) < pd.Timestamp(end)]
    if len(rows) < 2:
        return {"status": "INSUFFICIENT_MATURED_DAYS", "days": len(rows), "return": None}
    first, last = rows[0][1], rows[-1][1]
    if first == 0:
        return {"status": "ZERO_DENOMINATOR", "days": len(rows), "return": None}
    return {"status": "OK", "days": len(rows), "return": (last / first) - 1.0,
           "equity_first": first, "equity_last": last}


def build_panel_a(arms: dict, *, source_run_id: str) -> dict:
    """One row per (arm, fold): the candidate actually selected there
    (`candidate_id` = digest of its params, guide: "Cung mot candidate ID
    phai co params/source digest ro"), and its matured OOS outcome over the
    REAL deployment window that followed -- available only once that window
    has closed (the next fold's cutoff, or the arm's own window_end if it
    was the last fold). A union of candidates discovered by different arms
    is never retroactively applied to an origin before that arm actually
    discovered it (guide 10.1) -- each row is scoped to its OWN arm/fold.
    """
    rows = []
    for arm_name, outcome in arms.items():
        if not outcome.get("ok"):
            rows.append({"arm": arm_name, "origin": None, "status": "ARM_NOT_OK",
                        "reason": outcome.get("error")})
            continue
        run = outcome["run"]
        fold_table = run["fold_selection_table"]
        equity_daily = (run.get("account") or {}).get("equity_daily") or []
        window_end = run["requested"].get("window_end") or (
            fold_table[-1]["test_end"] if fold_table else None)
        for index, fold in enumerate(fold_table):
            candidate_id = digest(fold["selected_params"])[:16]
            deploy_end = (fold_table[index + 1]["test_start"] if index + 1 < len(fold_table)
                         else fold.get("test_end") or window_end)
            matured = _deployment_return(equity_daily, start=fold["test_start"], end=deploy_end)
            rows.append({
                "origin": fold["test_start"],
                "arm": arm_name,
                "fold_index": index,
                "candidate_id": candidate_id,
                "candidate_source_digest": candidate_id,
                "params": fold["selected_params"],
                "training_objective": fold.get("selected_is_objective"),
                "candidate_count_at_selection": fold.get("candidate_count"),
                "available_context": {"train_start": fold["train_start"], "train_end": fold["train_end"]},
                "deployment_window": [fold["test_start"], deploy_end],
                "matured_outcome": matured,
                "status": "OK",
            })
    by_candidate: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("candidate_id"):
            by_candidate.setdefault(row["candidate_id"], []).append(row)
    return {
        "schema": "regime_lab.ra06_panel_a.v1",
        "source_run_id": source_run_id,
        "reused_no_new_engine_calls": True,
        "rows": rows,
        "row_count": len(rows),
        "unique_candidates": len(by_candidate),
        "matured_ok_count": sum(1 for r in rows if r.get("matured_outcome", {}).get("status") == "OK"),
    }
