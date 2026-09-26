#!/usr/bin/env python3
"""SD03.5: real continuous A/B/C account deployment (guide SD03.5).

Frame span: from 30 days before the first FINAL origin (2024-03-23) through
2 days past the last origin's own D2 tail (2025-11-29 + 112 days), ~760
days / ~1.09M real 1-minute bars -- smaller than FP-07's own 1,576,800-bar
span (which needed a disclosed 7 GiB exception), so a probe decides whether
the registered 4 GiB budget suffices here rather than assuming it does.

Requires scripts/run_sd03_final_archive.py to have completed (reads its
real fold_*.json records to build each arm's admitted schedule).

Usage:
  lab_venv/bin/python scripts/run_sd03_deployment.py --probe   # memory probe only
  lab_venv/bin/python scripts/run_sd03_deployment.py           # full real run
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.sd import deployment_sd03 as dep  # noqa: E402

ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
ARMS = ("A_M4", "B_SD_GLOBAL", "JM_C2.0")
CACHE_ROOT = LAB / "evidence" / "sharpe_decay_sd_v1" / "compute-cache"
FINAL_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "final_folds"
DEPLOY_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "continuous_accounts"
TIMELINE_PATH = LAB / "configs" / "sharpe_decay_sd_v1" / "timeline.json"
PROGRESS_LOG = DEPLOY_DIR / "progress.jsonl"

FRAME_START_PAD_DAYS = 30
D2_TAIL_DAYS = 112
FRAME_END_PAD_DAYS = 2
PROBE_BARS = 200_000


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def log_progress(event: str, **fields) -> None:
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"utc": utcnow(), "event": event, **fields}
    with open(PROGRESS_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str), flush=True)


def apply_resource_limits(policy, *, override_gib: float = None) -> dict:
    env = lab_worker_env(policy)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        import os
        os.environ[key] = env[key]
    budget = policy.raw["resource_budget"]
    gib = override_gib if override_gib is not None else budget["working_memory_gib"]
    cap_bytes = int(gib * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"rlimit_as_gib": gib, "cpu_limit": env["OMP_NUM_THREADS"]}


def frame_bounds():
    import pandas as pd

    final_origins = json.loads(TIMELINE_PATH.read_text())["roles"]["FINAL"]["origins"]
    first = pd.Timestamp(final_origins[0], tz="UTC")
    last = pd.Timestamp(final_origins[-1], tz="UTC")
    frame_start = first - pd.Timedelta(days=FRAME_START_PAD_DAYS)
    frame_end = last + pd.Timedelta(days=D2_TAIL_DAYS + FRAME_END_PAD_DAYS)
    return frame_start, frame_end


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


def run_probe(probe_bars: int = PROBE_BARS) -> int:
    """Real memory probe: load ``probe_bars`` real 1-minute bars and run ONE
    real single-version deployment (the anchor's own params at the first
    FINAL origin), measuring peak RSS to extrapolate to the full span --
    the SAME discipline FP-07 used before committing to its own full-span
    deployment cost."""
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = apply_resource_limits(policy)
    log_progress("probe_start", limits=limits, probe_bars=probe_bars)

    import pandas as pd

    from crypto_regime_lab.time_edge.compute_cache import ComputeCache

    frame_start, _ = frame_bounds()
    probe_end = frame_start + pd.Timedelta(minutes=probe_bars)
    frame, _partitions = load_real_bars(SYMBOL, start=frame_start.strftime("%Y-%m-%d"),
                                        end=(probe_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    frame = frame[(frame.index >= frame_start) & (frame.index < probe_end)]

    fold_records = load_final_folds()
    first_origin = sorted(fold_records)[0]
    selections = dep.selections_by_origin_from_final_folds(
        {first_origin: fold_records[first_origin]}, arm="A_M4")
    params = selections[first_origin]["params"]

    from crypto_regime_lab.fp.evaluator import run_deployment

    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    economics = default_economics()
    schedule = [{"activation_id": "probe@0", "params": params, "requested_at_bar": 0}]
    t0 = time.perf_counter()
    run_deployment(cache, LAB, ALPHA_ID, frame, schedule, ready_at=frame.index[0],
                   report_level="score", economics=economics, producer="sd03-deploy-probe")
    wall = time.perf_counter() - t0
    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    frame_start_full, frame_end_full = frame_bounds()
    full_bars_est = int((frame_end_full - frame_start_full).total_seconds() / 60)
    projected_mib = peak_rss_mib * (full_bars_est / len(frame))

    result = {"probe_bars": len(frame), "wall_seconds": round(wall, 2),
             "peak_rss_mib": round(peak_rss_mib, 1), "full_bars_estimated": full_bars_est,
             "projected_peak_rss_mib": round(projected_mib, 1),
             "registered_budget_mib": 4096.0,
             "within_budget": projected_mib < 4096.0}
    log_progress("probe_complete", **result)
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    (DEPLOY_DIR / f"memory_probe_{probe_bars}.json").write_text(json.dumps({
        "schema": "regime_lab.sd03_deploy_memory_probe.v1", "measured_at_utc": utcnow(), **result,
    }, indent=2) + "\n", encoding="utf-8")
    # run_full() always reads the LARGEST probe point on disk -- the most
    # conservative/informative extrapolation, never the first one tried
    existing = sorted(DEPLOY_DIR.glob("memory_probe_*.json"),
                      key=lambda p: int(p.stem.rsplit("_", 1)[1]))
    largest = json.loads(existing[-1].read_text(encoding="utf-8"))
    (DEPLOY_DIR / "memory_probe.json").write_text(json.dumps(largest, indent=2) + "\n",
                                                  encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


def run_full() -> int:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    probe_path = DEPLOY_DIR / "memory_probe.json"
    if not probe_path.is_file():
        raise SystemExit("no memory_probe.json -- run with --probe first and review the projection "
                         "before committing to the full real deployment span")
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    if not probe["within_budget"]:
        # never silently raise the cap here -- an out-of-budget projection must be
        # disclosed to the owner explicitly, same as FP-07's own AskUserQuestion-gated
        # exception; this script refuses rather than silently widening RLIMIT_AS.
        raise SystemExit(f"memory probe projects {probe['projected_peak_rss_mib']} MiB, over the "
                         f"registered {probe['registered_budget_mib']} MiB budget -- this needs an "
                         "explicit, disclosed owner exception (FP-07's own precedent) before running; "
                         "refusing to proceed silently")
    limits = apply_resource_limits(policy)
    log_progress("deploy_start", limits=limits)

    fold_records = load_final_folds()
    frame_start, frame_end = frame_bounds()
    frame, _partitions = load_real_bars(SYMBOL, start=frame_start.strftime("%Y-%m-%d"),
                                        end=frame_end.strftime("%Y-%m-%d"))
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    frame = frame[(frame.index >= frame_start) & (frame.index < frame_end)]
    log_progress("frame_loaded", n_bars=len(frame), start=str(frame_start), end=str(frame_end))

    from crypto_regime_lab.time_edge.compute_cache import ComputeCache

    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    economics = default_economics()

    admitted = dep.build_admitted_schedules(fold_records, arms=ARMS)
    schedules = dep.build_deployment_schedules(admitted, frame_index=frame.index)

    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    t_run_start = time.perf_counter()
    payloads = dep.run_continuous_accounts(cache, LAB, ALPHA_ID, frame, schedules,
                                           economics=economics, producer_prefix="sd03-deploy")
    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    total_wall = time.perf_counter() - t_run_start

    for arm, entry in payloads.items():
        audit = entry["payload"]["selected_audit"]
        record = {"schema": "regime_lab.sd03_continuous_account.v1", "arm": arm,
                 "n_bars": len(frame), "cache_event": entry["cache_event"],
                 "n_fills": len(audit.get("fills", [])), "n_entries": audit.get("entries"),
                 "written_at_utc": utcnow()}
        (DEPLOY_DIR / f"account_{arm}.json").write_text(json.dumps(record, indent=2, default=str) + "\n",
                                                         encoding="utf-8")
        log_progress("account_complete", arm=arm, cache_event=entry["cache_event"],
                    n_fills=record["n_fills"])

    log_progress("deploy_complete", total_wall_seconds=round(total_wall, 2),
                peak_rss_mib=round(peak_rss_mib, 1), n_bars=len(frame))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--probe-bars", type=int, default=PROBE_BARS)
    args = parser.parse_args()
    return run_probe(args.probe_bars) if args.probe else run_full()


if __name__ == "__main__":
    raise SystemExit(main())
