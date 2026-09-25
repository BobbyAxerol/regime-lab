#!/usr/bin/env python3
"""SD02.3: build the real causal JM vintage tapes (3 penalty recipes) for
SD-01's 12 INIT origins, from real BTCUSDT daily bars. No engine/search
calls -- pure numpy fits on real daily closes, but real parquet I/O against
the pinned snapshot.

Usage:
  lab_venv/bin/python scripts/run_sd02_init_tapes.py
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.sd import jm_vintage as jv  # noqa: E402
from crypto_regime_lab.sd.verifier_sd01 import INIT_ORIGINS  # noqa: E402

SYMBOL = "BTCUSDT"
OUT_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "sd02_model"
OUT_PATH = OUT_DIR / "init_jm_tapes.json"


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def record_to_dict(rec: jv.VintageOriginRecord) -> dict:
    return asdict(rec)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    tapes = jv.build_vintage_tapes(load_real_bars, SYMBOL, list(INIT_ORIGINS))
    n_ok, n_insufficient, n_failed = 0, 0, 0
    tapes_out = {}
    for c, tape in tapes.items():
        rows = []
        for rec in tape:
            rows.append(record_to_dict(rec))
            if rec.status == jv.STATUS_OK:
                n_ok += 1
            elif rec.status == jv.STATUS_INSUFFICIENT_PREHISTORY:
                n_insufficient += 1
            else:
                n_failed += 1
        tapes_out[str(c)] = rows
        print(f"[{utcnow()}] recipe c={c}: "
             f"{sum(1 for r in tape if r.status == jv.STATUS_OK)}/{len(tape)} OK", flush=True)
    payload = {"schema": "regime_lab.sd02_init_jm_tapes.v1", "study_id": "sharpe_decay_sd_v1",
              "phase_id": "SD-02", "symbol": SYMBOL, "origins": list(INIT_ORIGINS),
              "recipes": list(jv.jm.NORMALIZED_PENALTIES), "generated_at_utc": utcnow(),
              "wall_seconds_measured": round(time.time() - t0, 2),
              "n_records_ok": n_ok, "n_records_insufficient_prehistory": n_insufficient,
              "n_records_fit_failed": n_failed, "tapes": tapes_out}
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_ok": n_ok, "n_insufficient": n_insufficient, "n_failed": n_failed,
                      "out": str(OUT_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
