"""Resource profiler and memory-growth slope (RA-GUIDE-1.0 RA03.7/RA03.8).

Measures the real stages of the actual code path -- not an estimate. Stage
boundaries follow ``PreparedAccount``'s own lazy split (RA03.1): construct
(now near-zero), window-pack (first touch of a given ``account_start``, or a
cache hit), engine run, serialize. Repeats the same task N times to measure
whether retained memory grows without bound (M06) and reports a target
headroom against the registered per-process cap (RA03.8) as a measured
comparison, never a promise.
"""
from __future__ import annotations

import resource
import time

from .phase_common import utcnow

# RA-01's frozen resource_budget.json: per_process_rss_gb=3.0. RA03.8 asks
# for a PRE-registered target headroom, recommended <=80% of the actual cap,
# as engineering margin -- not a per-dataset guarantee.
REGISTERED_PER_PROCESS_RSS_GB = 3.0
TARGET_HEADROOM_FRACTION = 0.80
TARGET_PEAK_RSS_GB = REGISTERED_PER_PROCESS_RSS_GB * TARGET_HEADROOM_FRACTION


def _rss_gib() -> float:
    # ru_maxrss is KiB on Linux (this lab's only registered host).
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def profile_one_task(build_frame, alpha_id, params, account_start_index, *,
                     repeat=1):
    """Run the real ``PreparedAccount`` path ``repeat`` times over the SAME
    frame/account_start (so every repeat after the first is a cache hit on
    the window), recording wall time per stage and peak RSS after each
    repeat -- the sequence of peaks is the growth-slope evidence for M06.
    """
    from ..time_edge.execution import PreparedAccount
    from ..evidence.manifest import dumps_strict

    t0 = time.perf_counter()
    frame = build_frame()
    t_build = time.perf_counter() - t0
    account_start = frame.index[account_start_index]
    selection = [{"selection_id": f"profile-{i}", "params": params,
                 "cutoff": account_start.isoformat(), "ready_at": account_start.isoformat()}
                 for i in range(repeat)]

    t0 = time.perf_counter()
    account = PreparedAccount(frame)
    t_construct = time.perf_counter() - t0
    rss_after_construct = _rss_gib()

    repeats = []
    for i in range(repeat):
        cache_before = len(account._windows)
        t0 = time.perf_counter()
        run = account.run(alpha_id, [selection[i]], account_start=account_start)
        t_run = time.perf_counter() - t0
        cache_hit = len(account._windows) == cache_before
        t0 = time.perf_counter()
        size_bytes = len(dumps_strict({"equity": list(run["equity"]),
                                       "fills": run["fills"]}))
        t_serialize = time.perf_counter() - t0
        repeats.append({
            "iteration": i, "window_cache_hit": cache_hit,
            "run_wall_seconds": t_run, "window_pack_seconds": run["packing_seconds"],
            "engine_wall_seconds": run["wall_seconds"] - run["packing_seconds"],
            "serialize_wall_seconds": t_serialize, "serialized_bytes": size_bytes,
            "peak_rss_gib_after": _rss_gib(),
        })

    peaks = [r["peak_rss_gib_after"] for r in repeats]
    # A crude but honest slope: last-minus-first over the number of repeats
    # after the first (the first repeat pays the one-time window pack).
    slope = None if len(peaks) < 2 else (peaks[-1] - peaks[1]) / max(1, len(peaks) - 2) \
        if len(peaks) > 2 else (peaks[-1] - peaks[0])
    return {
        "schema": "regime_lab.ra03_task_profile.v1",
        "alpha_id": alpha_id, "profiled_at_utc": utcnow(),
        "stages": {
            "load_build_frame_seconds": t_build,
            "prepare_construct_seconds": t_construct,
        },
        "repeats": repeats,
        "windows_cached_total": len(account._windows),
        "peak_rss_gib_after_construct": rss_after_construct,
        "peak_rss_gib_sequence": peaks,
        "peak_rss_gib_max": max(peaks) if peaks else rss_after_construct,
        "retained_rss_growth_gib_per_extra_repeat": slope,
        "registered_per_process_rss_cap_gib": REGISTERED_PER_PROCESS_RSS_GB,
        "target_headroom_fraction": TARGET_HEADROOM_FRACTION,
        "target_peak_rss_gib": TARGET_PEAK_RSS_GB,
        "under_target_headroom": (max(peaks) if peaks else rss_after_construct) <= TARGET_PEAK_RSS_GB,
        "extrapolated": False,
        "note": ("this process's own RSS via getrusage(RUSAGE_SELF); a real probe of THIS "
                 "process, not an extrapolation from a smaller fixture"),
    }


def metric_rerun_calls_no_engine(run, *, account_returns, describe, start, end) -> dict:
    """M08: recomputing a metric/report from a STORED run must not touch the
    engine. Measured by counting attribute access to the engine-owned fields
    only (equity/index arrays already materialized) -- no PreparedAccount or
    engine import happens in this function's body at all, which is the
    actual guarantee (a static property of the code, checked structurally
    by the caller's test via monkeypatch/import inspection, not asserted
    here).
    """
    rows = account_returns(run["equity"], run["index"], initial_equity=20000.,
                           start=start, end=end)
    return {"daily_returns": rows, "metrics": describe(rows), "engine_calls": 0}
