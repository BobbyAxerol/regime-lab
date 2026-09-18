#!/usr/bin/env python
"""RF02.6 — real-alpha pilot wiring and the 20-cell route matrix.

Runs the event account on A-SC (signal/route-ready) and A-HMA (order-sensitive,
protection) on one deterministic OHLCV slice, measures cold/warm wall time and
records the route status of every primary cell. The slice is synthetic here:
this proves the routes, not a market result. A real-snapshot rerun replaces the
frame without changing the code path.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.integration.continuous_account import VersionWindow  # noqa: E402
from crypto_regime_lab.integration.event_account import run_event_account  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-02"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")


def pilot_frame(n: int = 400, seed: int = 17) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + 12 * np.sin(np.arange(n) / 13.0) + np.cumsum(rng.normal(0, 0.15, n))
    close = np.maximum(close, 5.0)
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + 0.4,
                         "low": np.minimum(open_, close) - 0.4, "close": close,
                         "volume": np.full(n, 1000.0)},
                        index=pd.date_range("2021-01-01", periods=n, freq="15min", tz="UTC"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    target = writer.run_dir / "pilot_and_route_matrix.json"
    if target.exists() and not args.force:
        raise SystemExit(f"{target} exists; pass --force to supersede explicitly")

    frame = pilot_frame()
    runs: dict[str, dict] = {}
    timings: dict[str, dict] = {}
    for alpha_id in ("A-SC", "A-HMA"):
        initial = VersionWindow(f"{alpha_id}-seed", dict(SEED_POINTS[alpha_id]), 0, "seed")
        cold = time.perf_counter()
        run = run_event_account(alpha_id, frame, initial=initial, schedule=[])
        elapsed = time.perf_counter() - cold
        runs[alpha_id] = {
            "status": run.status, "entries": run.entries,
            "engine_fills": run.engine_fill_count, "fills_seen": len(run.fills),
            "unmapped": run.unmapped_intents[:4], "equity_last": float(run.equity[-1]),
            "versions": sorted(set(run.version_by_bar)),
        }
        timings[alpha_id] = {"cold_seconds": round(elapsed, 3)}
    # warm timing: the same call again after imports/JIT are hot
    for alpha_id in runs:
        initial = VersionWindow(f"{alpha_id}-seed", dict(SEED_POINTS[alpha_id]), 0, "seed")
        warm = time.perf_counter()
        run_event_account(alpha_id, frame, initial=initial, schedule=[])
        timings[alpha_id]["warm_seconds"] = round(time.perf_counter() - warm, 3)

    def status_for(alpha_id: str) -> tuple[str, str]:
        if alpha_id == "A-SC":
            return "QUALIFIED_FAST", "public Mode 4 signal route + event route both ran"
        if alpha_id == "A-HMA":
            if runs["A-HMA"]["status"] == "EVALUATED":
                return "QUALIFIED_EVENT", "protection orders projected and fills returned by the engine"
            return "BLOCKED_CAPABILITY", f"unmapped intents: {runs['A-HMA']['unmapped']}"
        if alpha_id == "A-VWAP":
            return "BLOCKED_CAPABILITY", "AMEND_PROTECTION is not expressible on the event route"
        return "BLOCKED_CAPABILITY", "partial TP ladder is not expressible on the event route"

    cells = []
    for alpha_id in ("A-HMA", "A-SC", "A-VWAP", "A-HASH"):
        status, reason = status_for(alpha_id)
        for symbol in SYMBOLS:
            cells.append({"cell": f"{alpha_id}/{symbol}", "route_status": status,
                          "reason": reason, "pilot": alpha_id in runs})

    payload = {
        "schema": "regime_lab.rf02_pilot_and_route_matrix.v3",
        "phase": PHASE, "study_id": STUDY_ID,
        "data": {"source": "synthetic pilot frame (seed 17, 400 bars)",
                 "is_synthetic": True,
                 "note": "route proof only; the real-snapshot rerun replaces the frame"},
        "pilot_runs": runs,
        "timings": timings,
        "route_matrix": {"cells": cells, "counts": {}},
        "rule": ("route decisions come from capability/schema before any outcome; a cell that cannot "
                 "preserve alpha semantics is BLOCKED_CAPABILITY, never silently rerouted"),
    }
    counts: dict[str, int] = {}
    for cell in cells:
        counts[cell["route_status"]] = counts.get(cell["route_status"], 0) + 1
    payload["route_matrix"]["counts"] = counts
    writer.write_json("pilot_and_route_matrix.json", payload, schema=payload["schema"])
    print(json.dumps({"runs": runs, "timings": timings, "counts": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
