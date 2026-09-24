"""FP-08 coverage matrix (guide FP08.1: full 20-cell matrix, including
cells not run). Primary matrix is 4 alphas x 5 symbols (CLAUDE.md/guide-
wide, the same 20 cells LAB-08/RF-04/RF-05 already used this convention
for)."""
from __future__ import annotations

ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")

NOT_RUN_REASON = (
    "outside FP-08's owner-approved replication scope (evidence/regime_time_edge_ra_v1/"
    "owner_decisions.jsonl decision dec-b5a96eb125bb80cd): only cell 1 (A-SC/BTCUSDT, FP-04..FP-07) "
    "and cell 2 (A-SC/ETHUSDT, 3 origins) were run. A full 20-cell matrix at cell 1's own depth would "
    "cost far more real engine compute than measured/disclosed here -- guide FP08.1's own 'Coverage "
    "matrix day du cho planned 20 cells, ke ca chua chay' anticipates this.")


def build_coverage_matrix(*, cell1_run_dir: str, cell2_run_dir: str | None,
                          cell2_status: str = "COMPLETED") -> dict:
    """cell2_status lets a caller mark cell 2 IN_PROGRESS/BLOCKED while its
    own real run is still executing, without inventing a premature
    COMPLETED claim FP08-G-REPLICATION would then have nothing real to
    verify against."""
    cells = []
    for alpha in ALPHAS:
        for symbol in SYMBOLS:
            if (alpha, symbol) == ("A-SC", "BTCUSDT"):
                cells.append({"alpha_id": alpha, "symbol": symbol, "status": "COMPLETED",
                             "evidence_ref": cell1_run_dir, "role": "cell1_primary"})
            elif (alpha, symbol) == ("A-SC", "ETHUSDT"):
                row = {"alpha_id": alpha, "symbol": symbol, "status": cell2_status,
                      "role": "cell2_replication"}
                if cell2_status == "COMPLETED":
                    row["evidence_ref"] = cell2_run_dir
                else:
                    row["reason"] = f"cell 2 real run status: {cell2_status}"
                cells.append(row)
            else:
                cells.append({"alpha_id": alpha, "symbol": symbol, "status": "NOT_RUN",
                             "reason": NOT_RUN_REASON})
    return {"schema": "regime_lab.fp08_coverage_matrix.v1", "cells": cells,
           "n_cells": len(cells), "n_completed": sum(1 for c in cells if c["status"] == "COMPLETED")}
