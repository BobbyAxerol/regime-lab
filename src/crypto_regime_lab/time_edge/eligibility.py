"""Outcome-blind data/history eligibility before an engine allocation is spent."""
import math
from pathlib import Path

import pandas as pd

from ..experiments.time_edge_contracts import ContractError
from ..selector.alpha_schemas import SCHEMAS
from .storage import read, file_digest


def history_days(alpha_id):
    """Conservative whole-day bound for every candidate in the pinned space.

    Include one extra completed bucket at both boundaries. This is a history
    requirement, not a promise that a data-dependent entry condition will fire.
    """
    specs=SCHEMAS[alpha_id].specs
    high=lambda key: int(specs[key].high)
    if alpha_id == "A-SC": minutes=(high("AP")+5)*15
    elif alpha_id == "A-HMA": minutes=(max(high("max_length"),high("minor_max"),high("atr_slow"),48)+12)*60
    elif alpha_id == "A-HASH": minutes=(max(3*high("mom_len")+1,15)+2)*15
    elif alpha_id == "A-VWAP":
        from ..alphas.a_vwap import ema_convergence_bars, DEV_LEN
        buckets=ema_convergence_bars(high("htf_ema_len"),1e-3)
        minutes=max((max(DEV_LEN,high("atr_len")+1,high("rsi_len")+1)+2)*15,(buckets+2)*60)
    else: raise ContractError("unregistered alpha")
    return math.ceil(minutes/1440)


def history_start(alpha_id, account_start):
    return (pd.Timestamp(account_start)-pd.Timedelta(days=history_days(alpha_id))).floor("D").isoformat()


def require_history(frame, alpha_id, account_start):
    required=pd.Timestamp(history_start(alpha_id,account_start))
    if frame.empty or frame.index[0] > required:
        raise ContractError(f"insufficient all-candidate indicator history: {alpha_id} needs data from {required.isoformat()}")


def coverage(root):
    root=Path(root); path=root/"snapshots/server_core_v1/manifest.json"
    manifest=read(path); cutoff=pd.Timestamp("2020-12-31T00:00:00Z")
    rows=[]
    for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","DOGEUSDT"):
        parts=[r for r in manifest["files"] if r["product_id"] == "crypto_binance_futures_1m" and r["symbol"] == symbol and r["closed"]]
        first=min(pd.Timestamp(r["time_min"],tz="UTC") for r in parts) if parts else None
        for alpha in SCHEMAS:
            required=pd.Timestamp(history_start(alpha,cutoff-pd.Timedelta(days=180)))
            eligible=first is not None and first <= required
            rows.append({"cell_id":f"{alpha}/{symbol}","first_available":None if first is None else first.isoformat(),
                "registered_initial_cutoff":cutoff.isoformat(),"train_days":180,"history_days":history_days(alpha),
                "required_history_start":required.isoformat(),"boundary_status":"BOUNDARY_ELIGIBLE" if eligible else "INSUFFICIENT_HISTORY",
                "earliest_boundary_eligible_cutoff":None if first is None else (first.ceil("D")+pd.Timedelta(days=180+history_days(alpha))).isoformat(),
                "internal_gap_status":"NOT_CHECKED_BY_MANIFEST_BOUNDARY_AUDIT"})
    failed=[r["cell_id"] for r in rows if r["boundary_status"] != "BOUNDARY_ELIGIBLE"]
    return {"lab_run_id":"TE-DATA-ELIGIBILITY-R05","snapshot_manifest_sha256":file_digest(path),"cells":rows,
            "boundary_eligible_cells":len(rows)-len(failed),"planned_cells":len(rows),"blocked_cells":failed,
            "status":"BLOCKED_REGISTERED_INITIAL_HISTORY" if failed else "BOUNDARY_CHECK_PASSED",
            "reason":"No shortened train, parameter-dependent score start, dropped cell, or silently moved initial cutoff is allowed.",
            "next_action":"A separate preregistration must resolve missing history before the original full cohort can run; worker still verifies exact contiguous 1m coverage.",
            "engine_runs":0}
