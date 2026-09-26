#!/usr/bin/env python3
"""Build the SD-01 real INIT archive (guide section 8, SD01.7).

Real work, per INIT origin (from configs/sharpe_decay_sd_v1/timeline.json,
frozen before any outcome):

  1. Real 128-trial search at the origin (fp.checkpoint_search.
     run_origin_search, the SAME real engine call FP-03/04/07..09 already
     depend on -- never a hand-rolled objective).
  2. The FULL unique-candidate pool from that search (sd.archive.
     unique_candidates) -- kept for SD-02/03's own full-pool prediction
     (guide SS3.2, the F03b remedy); never capped here.
  3. A deterministic <=16-candidate representative panel, ranked by the
     search's own cheap mean_is_sharpe proxy, anchor always included
     (sd.archive.representative_panel, guide SS3.5).
  4. Real canonical IS180/FWD56 Sharpe for every representative + the
     anchor (sd.archive.candidate_window_sharpe -- two fresh
     fp.evaluator.evaluate_candidate calls each, canonical Sharpe via
     sd.metrics, guide SS2.1/2.2).
  5. Real relative-decay labels Y = D(candidate) - D(anchor)
     (sd.metrics.signed_decay + relative_decay, guide SS3.3).

Checkpointed per origin: a crash after origin N completes never re-runs
origins 1..N (the underlying ComputeCache already makes every individual
search/evaluate_candidate call resumable; this script additionally skips
an origin's own ledger-writing step if its own record already exists on
disk, so a restart picks up cleanly).

Usage:
  lab_venv/bin/python scripts/run_sd01_archive.py
"""
from __future__ import annotations

import json
import os
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp.checkpoint_search import run_origin_search, _trial_records  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.sd import archive as ar  # noqa: E402
from crypto_regime_lab.sd import metrics as m  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

STUDY_ID = "sharpe_decay_sd_v1"
PHASE_ID = "SD-01"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
SEARCH_SEED = 20260925
SEARCH_TRIALS = 128
CACHE_ROOT = "evidence/sharpe_decay_sd_v1/compute-cache"
LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "init_archive"
TIMELINE_PATH = LAB / "configs" / "sharpe_decay_sd_v1" / "timeline.json"
PROGRESS_LOG = LAB / "evidence" / "sharpe_decay_sd_v1" / "init_archive" / "progress.jsonl"


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def log_progress(event: str, **fields) -> None:
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"utc": utcnow(), "event": event, **fields}
    with open(PROGRESS_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str), flush=True)


def apply_resource_limits(policy) -> dict:
    env = lab_worker_env(policy)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[key] = env[key]
    budget = policy.raw["resource_budget"]
    cap_bytes = int(budget["working_memory_gib"] * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"rlimit_as_gib": budget["working_memory_gib"], "cpu_limit": env["OMP_NUM_THREADS"],
           "exception_applied": False, "note": "SD01.6's own real micro-profile measured peak "
           "RSS well within the registered budget; no exception needed for the search stage"}


def origin_record_path(origin_cutoff: str) -> Path:
    return LEDGER_DIR / f"origin_{origin_cutoff}.json"


def build_one_origin(cache, *, origin_cutoff: str, economics: dict) -> dict:
    t_origin_start = time.perf_counter()
    search = run_origin_search(origin_cutoff=origin_cutoff, trials=SEARCH_TRIALS, seed=SEARCH_SEED,
                               train_memory_days=180, forward_days=56, symbol=SYMBOL, alpha_id=ALPHA_ID)
    if not search["wf_result"].get("ok"):
        raise SystemExit(f"origin {origin_cutoff}: real search did not return ok=True")
    records = _trial_records(search["wf_result"])
    candidates = ar.unique_candidates(records)
    anchor_params = search["wf_result"]["selected_params"]
    panel = ar.representative_panel(candidates, anchor_params=anchor_params)
    log_progress("search_done", origin=origin_cutoff, n_trials=len(records),
                 n_unique_candidates=len(candidates), panel_size=len(panel),
                 wall_seconds=round(search["wall_seconds_measured"], 2))

    def _candidate_id(params: dict) -> str:
        return "|".join(f"{k}={v}" for k, v in sorted(params.items()))

    anchor_id = _candidate_id(anchor_params)
    label_rows = []
    for i, row in enumerate(panel):
        params = row["params"]
        cid = _candidate_id(params)
        t_cand = time.perf_counter()
        is_result = ar.candidate_window_sharpe(cache, LAB, ALPHA_ID, load_real_bars, params,
                                               origin_cutoff=origin_cutoff, kind="IS", symbol=SYMBOL,
                                               economics=economics,
                                               producer=f"sd01archive-{origin_cutoff}")
        fwd_result = ar.candidate_window_sharpe(cache, LAB, ALPHA_ID, load_real_bars, params,
                                                origin_cutoff=origin_cutoff, kind="FWD", symbol=SYMBOL,
                                                economics=economics,
                                                producer=f"sd01archive-{origin_cutoff}")
        decay = m.signed_decay(
            {"sharpe": is_result["sharpe"], "sharpe_status": is_result["sharpe_status"]},
            {"sharpe": fwd_result["sharpe"], "sharpe_status": fwd_result["sharpe_status"]})
        label_rows.append({
            "candidate_id": cid, "params": params, "is_anchor": cid == anchor_id,
            "trial_id": row["trial_id"], "mean_is_sharpe_search_proxy": row["mean_is_sharpe"],
            "is_window": is_result, "fwd_window": fwd_result, "decay": decay,
        })
        log_progress("candidate_done", origin=origin_cutoff, candidate_index=i, total=len(panel),
                     candidate_id=cid, is_anchor=cid == anchor_id,
                     is_status=is_result["sharpe_status"], fwd_status=fwd_result["sharpe_status"],
                     decay_status=decay["status"], decay_value=decay.get("value"),
                     wall_seconds=round(time.perf_counter() - t_cand, 2))

    anchor_rows = [r for r in label_rows if r["is_anchor"]]
    if not anchor_rows:
        raise SystemExit(f"origin {origin_cutoff}: anchor not present in label_rows (build bug)")
    anchor_decay = anchor_rows[0]["decay"]
    for r in label_rows:
        r["relative_decay_Y"] = m.relative_decay(r["decay"], anchor_decay)

    origin_wall = time.perf_counter() - t_origin_start
    record = {
        "schema": "regime_lab.sd01_origin_record.v1", "study_id": STUDY_ID, "phase_id": PHASE_ID,
        "origin_cutoff": origin_cutoff, "alpha_id": ALPHA_ID, "symbol": SYMBOL,
        "search": {"trials_requested": SEARCH_TRIALS, "seed": SEARCH_SEED,
                  "wall_seconds_measured": search["wall_seconds_measured"],
                  "instrumentation": search["instrumentation"], "n_trial_records": len(records),
                  "n_unique_candidates": len(candidates)},
        "anchor_params": anchor_params, "anchor_id": anchor_id,
        "panel_size": len(panel), "label_rows": label_rows,
        "candidate_pool_record_ids": [_candidate_id(c["params"]) for c in candidates],
        "candidate_pool_trial_ids": {_candidate_id(c["params"]): c["trial_id"] for c in candidates},
        "origin_wall_seconds_measured": round(origin_wall, 2),
        "written_at_utc": utcnow(),
    }
    return record


def main() -> int:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = apply_resource_limits(policy)
    log_progress("run_start", limits=limits)

    timeline = json.loads(TIMELINE_PATH.read_text())
    init_origins = timeline["roles"]["INIT"]["origins"]

    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    economics = default_economics()

    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    peak_rss_overall = 0.0
    t_run_start = time.perf_counter()
    for origin_cutoff in init_origins:
        path = origin_record_path(origin_cutoff)
        if path.is_file():
            log_progress("origin_already_built_skipping", origin=origin_cutoff)
            continue
        log_progress("origin_start", origin=origin_cutoff)
        record = build_one_origin(cache, origin_cutoff=origin_cutoff, economics=economics)
        path.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
        peak_rss_overall = max(peak_rss_overall,
                               resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0)
        log_progress("origin_complete", origin=origin_cutoff,
                    origin_wall_seconds=record["origin_wall_seconds_measured"],
                    peak_rss_mib_so_far=round(peak_rss_overall, 1),
                    sha256=sha256_file(path))

    total_wall = time.perf_counter() - t_run_start
    log_progress("run_complete", total_wall_seconds=round(total_wall, 2),
                peak_rss_mib=round(peak_rss_overall, 1),
                n_origins_built=sum(1 for o in init_origins if origin_record_path(o).is_file()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
