"""RA07.2: the full 20-cell coverage matrix (guide section 11 -- "Coverage
matrix du 20 luon ton tai"). One row per (alpha, symbol) in the registered
primary cohort, whatever this phase actually ran.

Capability facts (which alphas the one available execution route can even
process) are NOT re-probed here -- they are the same real, already-measured
facts RF-04's `cell_coverage.json` recorded from RF-02's route matrix
(A-VWAP: AMEND_PROTECTION not expressible on the event route; A-HASH:
partial TP ladder not expressible on the event route). Re-deciding capability
from scratch here would risk disagreeing with an already-measured fact for
no reason; this module cites it instead (guide 4.2: reuse an established
finding).
"""
from __future__ import annotations

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")

STATUS_VOCABULARY = ("RUN_VALID", "BLOCKED_CAPABILITY", "NOT_RUN_BUDGET")

#: guide RA07.2's own vocabulary examples also list PLANNED/VALID/
#: INSUFFICIENT_HISTORY; this study resolves every cell to one of the three
#: above immediately (no cell is left in a pre-execution PLANNED state, and
#: no cell fails on data-history grounds), so those labels are not used.
BLOCKED_ALPHAS = {
    "A-VWAP": "AMEND_PROTECTION is not expressible on the event route (RF-02 route matrix, "
             "reused verbatim from evidence/corrective_mode4_v3/RF-04/cell_coverage.json)",
    "A-HASH": "partial TP ladder is not expressible on the event route (RF-02 route matrix, "
             "reused verbatim from evidence/corrective_mode4_v3/RF-04/cell_coverage.json)",
}


def build_coverage_matrix(*, cell1: dict, cell2: dict) -> dict:
    """`cell1`/`cell2` are ``{"alpha_id", "symbol", "run_ref", "arms_present"}``
    -- the two cells this phase actually ran. Every other cell in the 20-cell
    cohort is classified from the reused capability facts, never executed
    here (a disclosed, honest scope reduction consistent with RA07.2:
    'Khong thay mau khi cell cho ket qua am. Mo nhieu cells hon theo approved
    budget, khong prerequisite rang first cell phai significant').
    """
    executed = {(cell1["alpha_id"], cell1["symbol"]): cell1,
               (cell2["alpha_id"], cell2["symbol"]): cell2}
    rows = []
    for alpha in ALPHAS:
        for symbol in SYMBOLS:
            key = (alpha, symbol)
            if key in executed:
                cell = executed[key]
                rows.append({
                    "cell": f"{alpha}/{symbol}", "alpha_id": alpha, "symbol": symbol,
                    "coverage_status": "RUN_VALID",
                    "reason": "executed this phase on the event route, real per-fill account",
                    "run_ref": cell["run_ref"], "arms_present": cell["arms_present"],
                })
            elif alpha in BLOCKED_ALPHAS:
                rows.append({
                    "cell": f"{alpha}/{symbol}", "alpha_id": alpha, "symbol": symbol,
                    "coverage_status": "BLOCKED_CAPABILITY", "reason": BLOCKED_ALPHAS[alpha],
                    "run_ref": None, "arms_present": None,
                })
            else:
                rows.append({
                    "cell": f"{alpha}/{symbol}", "alpha_id": alpha, "symbol": symbol,
                    "coverage_status": "NOT_RUN_BUDGET",
                    "reason": ("capability/route qualified (event route, RF-02) but not executed "
                              "this phase; budget was spent on the 2 cells above plus the "
                              "mandatory controls and decay/bootstrap machinery -- disclosed scope "
                              "limit, never a silent zero"),
                    "run_ref": None, "arms_present": None,
                })
    counts = {status: sum(1 for r in rows if r["coverage_status"] == status)
             for status in STATUS_VOCABULARY}
    return {
        "schema": "regime_lab.ra07_coverage_matrix.v1",
        "status_vocabulary": list(STATUS_VOCABULARY),
        "registered_cohort": {"symbols": list(SYMBOLS), "alphas": list(ALPHAS)},
        "rows": rows, "counts": {**counts, "planned_cells": len(rows)},
        "rule": ("one row per (alpha, symbol) of the registered 4x5 cohort; a non-executed cell "
                "carries null run_ref with a reason, never a fabricated metric; changing which "
                "cells run is governed only by capability/coverage/behavior/cost, never by a "
                "cell's own PnL (guide RA07.2, RA-01 scope.change_rule)"),
    }
