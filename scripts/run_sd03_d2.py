#!/usr/bin/env python3
"""SD03.6: real D2 frozen continuations (guide SS2.4).

For each of the 12 real FINAL origins and each of the 3 arms (A_M4,
B_SD_GLOBAL, JM_C2.0), run ONE real continuous 112-day evaluate_candidate
call on that arm's own winning candidate's UNCHANGED params -- checkpointed
per (origin, arm), so a partial run resumes cleanly.

Requires scripts/run_sd03_final_archive.py to have completed (reads its
real fold_*.json records for the winner params).

Usage:
  lab_venv/bin/python scripts/run_sd03_d2.py
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
from crypto_regime_lab.sd import deployment_sd03 as dep  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
CACHE_ROOT = LAB / "evidence" / "sharpe_decay_sd_v1" / "compute-cache"
FINAL_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "final_folds"
D2_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "d2_continuations"
TIMELINE_PATH = LAB / "configs" / "sharpe_decay_sd_v1" / "timeline.json"
PROGRESS_LOG = D2_LEDGER_DIR / "progress.jsonl"
ARMS = ("A_M4", "B_SD_GLOBAL", "JM_C2.0")


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def log_progress(event: str, **fields) -> None:
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"utc": utcnow(), "event": event, **fields}
    with open(PROGRESS_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str), flush=True)


def record_path(origin: str, arm: str) -> Path:
    return D2_LEDGER_DIR / f"d2_{origin}_{arm}.json"


def load_final_folds() -> dict:
    final_origins = json.loads(TIMELINE_PATH.read_text())["roles"]["FINAL"]["origins"]
    out = {}
    for origin in final_origins:
        path = FINAL_LEDGER_DIR / f"fold_{origin}.json"
        if not path.is_file():
            raise SystemExit(f"required FINAL fold record missing: {path} -- run "
                             "scripts/run_sd03_final_archive.py to completion first")
        out[origin] = json.loads(path.read_text(encoding="utf-8"))
    return out


def main() -> int:
    D2_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    fold_records = load_final_folds()
    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    economics = default_economics()
    log_progress("run_start", n_origins=len(fold_records), arms=list(ARMS))

    t_run_start = time.perf_counter()
    for origin, fold in sorted(fold_records.items()):
        for arm in ARMS:
            path = record_path(origin, arm)
            if path.is_file():
                log_progress("d2_already_built_skipping", origin=origin, arm=arm)
                continue
            selections = dep.selections_by_origin_from_final_folds({origin: fold}, arm=arm)
            params = selections[origin]["params"]
            t0 = time.perf_counter()
            result = d2.candidate_d2_continuation(cache, LAB, ALPHA_ID, load_real_bars, params,
                                                   origin_cutoff=origin, symbol=SYMBOL,
                                                   economics=economics,
                                                   producer=f"sd03-d2-{origin}-{arm}")
            wall = time.perf_counter() - t0
            record = {"schema": "regime_lab.sd03_d2_continuation.v1", "origin_cutoff": origin,
                     "arm": arm, "params": params, "result": result,
                     "wall_seconds_measured": round(wall, 2), "written_at_utc": utcnow()}
            path.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
            log_progress("d2_complete", origin=origin, arm=arm, status=result["status"],
                        d_age=result.get("d_age"), wall_seconds=round(wall, 2))

    total_wall = time.perf_counter() - t_run_start
    n_built = sum(1 for o in fold_records for a in ARMS if record_path(o, a).is_file())
    log_progress("run_complete", total_wall_seconds=round(total_wall, 2), n_built=n_built,
                n_expected=len(fold_records) * len(ARMS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
