#!/usr/bin/env python3
"""SD02.1/SD02.2 support: backfill each INIT panel candidate's real
activity_entries descriptor via a guaranteed cache-HIT re-fetch (zero new
engine compute). Writes a SEPARATE artifact -- never modifies SD-01's own
committed origin_*.json files (this lab's append-only evidence discipline).

Usage:
  lab_venv/bin/python scripts/run_sd02_descriptors.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.sd import candidate_descriptors as cd  # noqa: E402
from crypto_regime_lab.sd.verifier_sd01 import INIT_ORIGINS  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "init_archive"
CACHE_ROOT = LAB / "evidence" / "sharpe_decay_sd_v1" / "compute-cache"
OUT_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "sd02_model"
PARTIAL_DIR = OUT_DIR / "init_descriptors_partial"
OUT_PATH = OUT_DIR / "init_descriptors.json"


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def origin_partial_path(origin: str) -> Path:
    return PARTIAL_DIR / f"{origin}.json"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    economics = default_economics()
    t0 = time.time()
    for origin in INIT_ORIGINS:
        partial_path = origin_partial_path(origin)
        if partial_path.is_file():
            print(f"[{utcnow()}] {origin}: already built, skipping", flush=True)
            continue
        record = json.loads((LEDGER_DIR / f"origin_{origin}.json").read_text(encoding="utf-8"))
        rows_out = []
        for row in record["label_rows"]:
            fetched = cd.fetch_activity_entries(cache, LAB, "A-SC", load_real_bars, row["params"],
                                                 origin_cutoff=origin, symbol=record["symbol"],
                                                 economics=economics,
                                                 producer=f"sd02-descriptors-{origin}")
            rows_out.append({"candidate_id": row["candidate_id"], "is_anchor": row["is_anchor"],
                            "activity_entries": fetched["entries"], "cache_event": fetched["cache_event"]})
        partial_path.write_text(json.dumps(rows_out, indent=2) + "\n", encoding="utf-8")
        n_hit = sum(1 for r in rows_out if r["cache_event"] == "HIT")
        print(f"[{utcnow()}] {origin}: {len(rows_out)} rows fetched "
             f"(HIT={n_hit} MISS={len(rows_out) - n_hit}), checkpointed", flush=True)

    origins_out = {}
    n_hit, n_miss = 0, 0
    for origin in INIT_ORIGINS:
        rows_out = json.loads(origin_partial_path(origin).read_text(encoding="utf-8"))
        origins_out[origin] = rows_out
        n_hit += sum(1 for r in rows_out if r["cache_event"] == "HIT")
        n_miss += sum(1 for r in rows_out if r["cache_event"] != "HIT")
    payload = {"schema": "regime_lab.sd02_init_descriptors.v1", "study_id": "sharpe_decay_sd_v1",
              "phase_id": "SD-02", "generated_at_utc": utcnow(),
              "wall_seconds_measured": round(time.time() - t0, 2),
              "n_cache_hit": n_hit, "n_cache_miss": n_miss, "origins": origins_out}
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_hit": n_hit, "n_miss": n_miss, "out": str(OUT_PATH)}, indent=2))
    return 0 if n_miss == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
