#!/usr/bin/env python
"""LAB-04 L04.5/L04.6 -- arm A vs arm B over the frozen calendar, all 20 cells.

Pilot order is A-SC -> A-HMA -> A-VWAP -> A-HASH with BTCUSDT first, and EVERY
cell status is reported whether or not it helps. Each finished cell is written to
its own checkpoint so an interrupted run resumes instead of restarting, and a
partial run is visibly partial rather than passed off as a full matrix.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data import panel as P  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, dumps_strict  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
PILOT_ORDER = CB.ALPHA_ORDER_DEFAULT
SYMBOL_ORDER = CB.SYMBOL_ORDER_DEFAULT
CHECKPOINTS = LAB_ROOT / ".cache" / (sys.argv[1] if len(sys.argv) > 1 else "lab04_cells")


def _bars(root: Path, manifest: dict, symbol: str, interval: str,
          cache: dict) -> pd.DataFrame:
    key = f"{symbol}|{interval}"
    if key not in cache:
        frame = P.load_resampled(root, "crypto_binance_futures_1m", symbol, interval,
                                 manifest=manifest)
        frame["time"] = pd.to_datetime(frame["time"])
        if frame["time"].dt.tz is None:
            frame["time"] = frame["time"].dt.tz_localize("UTC")
        cache[key] = frame.set_index("time").sort_index()
    return cache[key]


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = json.loads((snapshot_root / "manifest.json").read_text())
    cache: dict[str, pd.DataFrame] = {}

    cells: list[dict] = []
    for alpha_id in PILOT_ORDER:
        for symbol in SYMBOL_ORDER:
            checkpoint = CHECKPOINTS / f"{alpha_id}_{symbol}.json"
            if checkpoint.is_file():
                cells.append(json.loads(checkpoint.read_text()))
                print(f"  {alpha_id}/{symbol}: reused checkpoint")
                continue
            t0 = time.time()
            with writer.attempt(f"L04.5.cell.{alpha_id}.{symbol}") as att:
                if alpha_id in CB.NOT_READY:
                    cell = CB.run_cell(alpha_id, symbol, pd.DataFrame())
                else:
                    bars = _bars(snapshot_root, manifest, symbol,
                                 CB.DECISION_INTERVAL[alpha_id], cache)
                    cell = CB.run_cell(alpha_id, symbol, bars)
                cell["wall_seconds"] = round(time.time() - t0, 1)
                att.detail = {"status": cell["status"],
                              "folds": sum(1 for f in cell["folds"]
                                           if f.get("status") == "OK")}
            checkpoint.write_text(dumps_strict(cell))
            cells.append(cell)
            arms = cell.get("arms", {})
            print(f"  {alpha_id}/{symbol}: {cell['status']} in {cell['wall_seconds']}s "
                  f"A={_short(arms.get('A'))} B={_short(arms.get('B'))}", flush=True)

    done = [c for c in cells if c.get("status")]
    print(f"\n=== cells produced: {len(done)}/"
          f"{len(CB.ALPHA_ORDER_DEFAULT) * len(CB.SYMBOL_ORDER_DEFAULT)} ===")
    print("The committed summary is built by scripts/summarize_calendar_baseline.py from these\n"
          "checkpoints, so it always reflects the current summarising code rather than whatever\n"
          "version was loaded when a multi-hour run started.")
    print(f"evidence -> {writer.run_dir}")
    return 0


def _short(arm: dict | None) -> str:
    if not arm:
        return "n/a"
    if arm.get("net_return") is None:
        return arm.get("status", "n/a")
    return f"{arm['net_return']:+.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
