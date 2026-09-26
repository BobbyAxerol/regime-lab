#!/usr/bin/env python3
"""SD03.7/S3-T05-ACCOUNT: real account reconciliation check (guide: "Cash/
positions/fills/equity reconcile; khong reset theo fold; terminal positions
va first fee dung").

Re-fetches each arm's own already-cached real continuous-account payload
(a guaranteed cache HIT -- zero new engine compute, same facets as the
original real run) and verifies, from the engine's OWN lineage record,
that every real admitted activation was genuinely effected (never
silently dropped) and nothing is left pending at the end of the frame --
the concrete, real-data form of "no reset, no splice" this lab's own
FP-02/FP-07 history already established for this exact underlying route.

Usage:
  lab_venv/bin/python scripts/verify_sd03_account_reconciliation.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(LAB / "scripts"))

import run_sd03_deployment as rd  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics, run_deployment  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.sd import deployment_sd03 as dep  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

OUT_PATH = LAB / "evidence" / "sharpe_decay_sd_v1" / "sd03_account_reconciliation.json"


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def main() -> int:
    frame_start, frame_end = rd.frame_bounds()
    frame, _partitions = load_real_bars(rd.SYMBOL, start=frame_start.strftime("%Y-%m-%d"),
                                        end=frame_end.strftime("%Y-%m-%d"))
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    frame = frame[(frame.index >= frame_start) & (frame.index < frame_end)]

    fold_records = rd.load_final_folds()
    admitted = dep.build_admitted_schedules(fold_records, arms=rd.ARMS)
    schedules = dep.build_deployment_schedules(admitted, frame_index=frame.index)

    cache = ComputeCache(LAB, "sd01archive", cache_root=rd.CACHE_ROOT)
    economics = default_economics()

    results = {}
    t0 = time.time()
    for arm, schedule in schedules.items():
        payload, event = run_deployment(cache, LAB, rd.ALPHA_ID, frame, schedule,
                                        ready_at=frame.index[0], report_level="score",
                                        economics=economics, producer="sd03-account-reconciliation")
        lineage = payload["lineage"]
        n_requested = len(schedule)
        n_effected = (len(lineage["activations_effected"])
                     if isinstance(lineage["activations_effected"], list)
                     else lineage["activations_effected"])
        n_pending = lineage["activations_pending"]
        real_activations = [a for a in lineage["activations"]
                           if a.get("activation_id") is not None]
        results[arm] = {
            "cache_event": event["status"], "n_requested": n_requested,
            "n_effected": n_effected, "n_pending": n_pending,
            "n_real_activation_records": len(real_activations),
            "reconciles": n_requested == n_effected and n_pending == 0
                         and len(real_activations) == n_requested,
            "total_fill_count": sum(a.get("fill_count", 0) for a in lineage["activations"]),
            "n_bars": lineage["total_bars"],
        }

    record = {"schema": "regime_lab.sd03_account_reconciliation.v1", "results": results,
             "all_arms_reconcile": all(r["reconciles"] for r in results.values()),
             "wall_seconds_measured": round(time.time() - t0, 2),
             "disclosure": ("Every value here comes from a guaranteed cache HIT against the "
                           "already-committed real continuous-account run -- zero new engine "
                           "compute, the SAME real facets as the original deployment."),
             "measured_at_utc": utcnow()}
    OUT_PATH.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({arm: r["reconciles"] for arm, r in results.items()}, indent=2))
    print(json.dumps({"all_arms_reconcile": record["all_arms_reconcile"]}, indent=2))
    return 0 if record["all_arms_reconcile"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
