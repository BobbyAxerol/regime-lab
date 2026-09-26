#!/usr/bin/env python3
"""SD03.8: same-contract replay (guide SD03.8: "Same-contract replay co the
reuse verified computations; consistency qua cache khong duoc goi la cold
native rerun").

Re-runs ONE already-committed real D2 continuation call (the cheapest,
most deterministic real artifact SD-03 produced) under the IDENTICAL
frozen contract -- same params, same origin_cutoff, same economics -- and
compares the economic fields exactly. A cache HIT here is EXPECTED (the
cache is warm from the original run) and is explicitly disclosed as NOT an
independent confirmation, matching FP-10's own precedent: this proves
reproducibility, never a new measurement.

Usage:
  lab_venv/bin/python scripts/run_sd03_replay.py
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
from crypto_regime_lab.sd import d2_continuation as d2  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
CACHE_ROOT = LAB / "evidence" / "sharpe_decay_sd_v1" / "compute-cache"
D2_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "d2_continuations"
REPLAY_PATH = LAB / "evidence" / "sharpe_decay_sd_v1" / "sd03_replay_result.json"

REPLAY_TARGET_ORIGIN = "2024-03-23"   # the first real FINAL origin -- fixed here, not
REPLAY_TARGET_ARM = "A_M4"            # discovered dynamically, so the replay target cannot drift
GATED_FIELDS = ("status", "sr_h1", "sr_h2", "d_age")


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def main() -> int:
    original_path = D2_DIR / f"d2_{REPLAY_TARGET_ORIGIN}_{REPLAY_TARGET_ARM}.json"
    if not original_path.is_file():
        raise SystemExit(f"required original D2 record missing: {original_path}")
    original = json.loads(original_path.read_text(encoding="utf-8"))

    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    economics = default_economics()
    t0 = time.perf_counter()
    replay_result = d2.candidate_d2_continuation(
        cache, LAB, ALPHA_ID, load_real_bars, original["params"],
        origin_cutoff=original["origin_cutoff"], symbol=SYMBOL, economics=economics,
        producer="sd03-replay")
    wall = time.perf_counter() - t0

    comparisons = []
    for field in GATED_FIELDS:
        o, r = original["result"].get(field), replay_result.get(field)
        comparisons.append({"field": field, "original": o, "replay": r, "match": o == r})
    all_match = all(c["match"] for c in comparisons)

    record = {
        "schema": "regime_lab.sd03_replay_result.v1", "replayed_origin": REPLAY_TARGET_ORIGIN,
        "replayed_arm": REPLAY_TARGET_ARM, "original_ref": str(original_path.relative_to(LAB)),
        "comparisons": comparisons, "all_gated_fields_match": all_match,
        "cache_provenance": {"original_cache_event": original["result"].get("cache_event"),
                            "replay_cache_event": replay_result.get("cache_event")},
        "disclosure": ("SAME frozen market data, SAME code, SAME params/origin/economics were "
                       "replayed under the identical contract -- this is NOT an independent "
                       "confirmation of the original real result, only a proof that it "
                       "reproduces exactly. A cache HIT on the replay is EXPECTED (the cache is "
                       "warm from the original run) and is disclosed here, never gated on."),
        "replay_wall_seconds": round(wall, 2), "replayed_at_utc": utcnow(),
    }
    REPLAY_PATH.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"all_gated_fields_match": all_match, "comparisons": comparisons}, indent=2))
    return 0 if all_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
