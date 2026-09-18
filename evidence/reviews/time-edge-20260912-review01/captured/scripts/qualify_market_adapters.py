#!/usr/bin/env python
"""LAB-03 L03.7 — market adapter qualification on bounded development slices."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data import panel as P  # noqa: E402
from crypto_regime_lab.data.qualification import (  # noqa: E402
    DECISION_INTERVAL, DEFAULT_SLICE_BARS, qualification_report, qualify,
)
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
# A bounded window inside the DEVELOPMENT role. Pinned, never chosen from results.
SLICE_START = "2022-03-01"
CERTIFIED = ("A-SC", "A-HMA", "A-VWAP")
NOT_READY = ("A-HASH",)


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = json.loads((snapshot_root / "manifest.json").read_text())

    cache: dict[str, pd.DataFrame] = {}

    def bars_for(symbol: str, interval: str) -> pd.DataFrame:
        key = f"{symbol}|{interval}"
        if key not in cache:
            cache[key] = P.load_resampled(snapshot_root, "crypto_binance_futures_1m", symbol,
                                          interval, manifest=manifest)
        frame = cache[key]
        window = frame[frame["time"] >= SLICE_START].head(DEFAULT_SLICE_BARS)
        return window.reset_index(drop=True)

    results = []
    with writer.attempt("L03.7.qualify") as att:
        for alpha_id in CERTIFIED + NOT_READY:
            interval = DECISION_INTERVAL[alpha_id]
            for symbol in P.MARKET_SYMBOLS:
                results.append(qualify(alpha_id, symbol, bars_for(symbol, interval)))
        att.detail = {"cells": len(results),
                      "qualified": sum(1 for r in results if r.status == "QUALIFIED")}

    report = qualification_report(results, list(NOT_READY))
    report["slice_start"] = SLICE_START
    report["slice_bars"] = DEFAULT_SLICE_BARS
    report["snapshot_id"] = SNAPSHOT_ID
    writer.write_config("market_qualification.json", report)
    writer.write_json("market_qualification.json", report, schema=report["schema"])

    print(f"cells attempted : {report['cells_attempted']}  qualified: {report['cells_qualified']}")
    by_alpha: dict[str, list[str]] = {}
    for record in report["results"]:
        by_alpha.setdefault(record["alpha_id"], []).append(record["status"])
    for alpha_id, statuses in by_alpha.items():
        ok = sum(1 for s in statuses if s == "QUALIFIED")
        print(f"   {alpha_id:<8} {ok}/{len(statuses)} qualified  {sorted(set(statuses))}")
    for record in report["results"]:
        if record["status"] != "QUALIFIED":
            print(f"      {record['alpha_id']}/{record['symbol']}: {record['status']} "
                  f"{(record['error'] or '')[:120]}")
    print(f"data role       : {report['data_role']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
