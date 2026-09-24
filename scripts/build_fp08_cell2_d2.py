#!/usr/bin/env python3
"""Build FP-08's cell-2 (A-SC/ETHUSDT) D2 age-curve analysis (guide
10.3/FP08.2). Mirrors build_fp08_cell1_d2.py exactly, reusing cell 2's own
already-computed continuous accounts via real cache-HIT re-calls (zero new
engine calls, asserted not assumed) -- run AFTER run_fp08_cell2_study.py.

Usage:
  lab_venv/bin/python scripts/build_fp08_cell2_d2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import d2_continuation as d2  # noqa: E402
from crypto_regime_lab.fp import locked_study as ls  # noqa: E402
from crypto_regime_lab.fp import selector_b as sb  # noqa: E402
from crypto_regime_lab.fp import selector_c as sc  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics, run_deployment  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

ALPHA_ID = "A-SC"
SYMBOL = "ETHUSDT"
CELL2_STUDY_DIR = LAB / ".cache" / "fp08_cell2_study"
FRAME_START = "2021-06-01"
FRAME_END = "2024-01-01"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"
OUT_PATH = LAB / ".cache" / "fp08_cell2_d2.json"


class Cell2D2Error(RuntimeError):
    """A step that should have been a real cache HIT was not."""


def rebuild_selections_by_origin() -> tuple[dict, list[str]]:
    doc = json.loads((CELL2_STUDY_DIR / "selections.json").read_text())
    origins_sorted = sorted(doc["by_origin"])
    by_arm = {arm: {} for arm in ls.ARMS}
    for origin in origins_sorted:
        for arm in ls.ARMS:
            by_arm[arm][origin] = doc["by_origin"][origin][arm]
    return by_arm, origins_sorted


def main() -> int:
    economics = default_economics()
    cache = ComputeCache(LAB, "fp08cell2", cache_root=CACHE_ROOT)

    selections_by_origin, origins_sorted = rebuild_selections_by_origin()
    admitted = {arm: ls.build_admitted_schedule(selections_by_origin[arm], arm=arm)
               for arm in ls.ARMS}

    frame, _partitions = load_real_bars(SYMBOL, start=FRAME_START, end=FRAME_END)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    schedules = {arm: ls.build_run_deployment_schedule(admitted[arm], frame_index=frame.index)
                for arm in ls.ARMS}

    daily_returns, fills_by_arm = {}, {}
    for arm in ls.ARMS:
        payload, event = run_deployment(cache, LAB, ALPHA_ID, frame, schedules[arm],
                                        ready_at=frame.index[0], report_level="score",
                                        economics=economics, producer="fp08-cell2-d2-reuse")
        if event["status"] != "HIT":
            raise Cell2D2Error(f"{arm}: expected a real cache HIT reusing cell 2's own study "
                              f"computation, got {event['status']}")
        daily_returns[arm] = ls.account_daily_returns(payload, frame,
                                                       initial_capital=economics["initial_capital"])
        fills_by_arm[arm] = payload["selected_audit"]["fills"]

    context_by_origin = {}
    for origin in origins_sorted:
        is_frame = sb.load_origin_is_frame(ALPHA_ID, origin, symbol=SYMBOL)
        context_by_origin[origin] = sc.compute_context_features(is_frame)

    def exposure_in_window(arm: str, *, start_iso: str, end_exclusive_iso: str) -> dict:
        import pandas as pd

        lo, hi = pd.Timestamp(start_iso), pd.Timestamp(end_exclusive_iso)
        count = 0
        for fill in fills_by_arm[arm]:
            ts = frame.index[int(fill["bar_index"])]
            if lo <= ts < hi:
                count += 1
        return {"status": "OK", "fill_count": count}

    records = []
    for arm in ls.ARMS:
        anchors = d2.anchors_from_selections(selections_by_origin, arm=arm,
                                             origins_ordered=origins_sorted)
        for anchor in anchors:
            origin = anchor["origin_cutoff"]
            record = d2.build_d2_record(
                arm=arm, origin_cutoff=origin, params=anchor["params"],
                daily_returns=daily_returns[arm],
                context=context_by_origin.get(origin))
            for window in record["age_windows"]:
                if window["status"] == "COMPLETE":
                    window["exposure"] = exposure_in_window(
                        arm, start_iso=window["start"], end_exclusive_iso=window["end_exclusive"])
            records.append(record)

    out = {
        "schema": "regime_lab.fp08_cell2_d2.v1",
        "cell": "cell2_replication", "alpha_id": ALPHA_ID, "symbol": SYMBOL,
        "engine_calls_new": 0,
        "note": "every arm's continuous account reused via a real cache HIT on cell 2's own "
               "already-computed run_deployment payload -- asserted, not assumed",
        "records": records,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    n_complete = sum(1 for r in records if r["fully_complete"])
    print(json.dumps({"records": len(records), "fully_complete": n_complete,
                      "out_path": str(OUT_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
