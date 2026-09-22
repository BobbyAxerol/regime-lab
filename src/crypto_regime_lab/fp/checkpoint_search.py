"""FP03.2/03.3 -- calibration origins and the checkpoint search itself.

Runs the REAL stock search (``experiments.dynamic_fold_provider.
run_cutoff_walk_forward``, the exact engine RA-05..RA-07/FUP-01..05 already
depend on -- never a hand-rolled replacement objective) at one calibration
origin, then extracts SEQUENTIAL PREFIXES of the resulting real trial
history at each checkpoint level. "Sequential prefix" (guide 6.2) means the
lower-budget checkpoint uses only trials that existed at that point in the
SAME ask/tell order the real search actually produced -- never a separate,
independently-seeded re-run, which the guide explicitly forbids as wasted
and non-comparable work.

CALIBRATION_ORIGINS are chosen by calendar spacing across the registered
development role (2020-01-01 -> 2023-12-31, CLAUDE.md/guide-wide), same
month across three years -- a rule fixed BEFORE any origin's search outcome
is known (guide's own 'không chọn vì stock có PnL đẹp'), not selected after
looking at which one searches well.
"""
from __future__ import annotations

CHECKPOINT_LEVELS = (32, 64, 128, 256)
TRAIN_MEMORY_DAYS = 180  # guide 3.2's registered candidate_training_days
CALIBRATION_ORIGINS = ("2021-06-01", "2022-06-01", "2023-06-01")
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"


def run_origin_search(*, origin_cutoff: str, trials: int, seed: int,
                      route: str = "event", train_memory_days: int = TRAIN_MEMORY_DAYS,
                      forward_days: int = 28) -> dict:
    """One real run_cutoff_walk_forward call, ONE cutoff (this calibration
    origin), trials spent entirely on searching AT that origin. Loads only
    [origin - train_memory_days - buffer, origin + forward_days]: enough for
    the search itself plus FP03.4's forward comparison window, nothing more.

    Returns real, measured ``wall_seconds_measured`` (the whole call, data
    load included) and ``instrumentation`` (peak/base/residual RSS + the
    engine call's own wall time, via the same ``instrumentation.Stage``
    every other real engine call in this study is wrapped in -- guide 11.6:
    a cost claim needs a measurement, never an estimate presented as one).
    """
    import time

    import pandas as pd

    from ..experiments.dynamic_fold_provider import (
        CutoffSchedule, ZeroSignalStrategy, engine_param_ranges, run_cutoff_walk_forward,
    )
    from ..ra.ra05_market import load_real_bars
    from .instrumentation import Stage

    t0 = time.time()
    cutoff_ts = pd.Timestamp(origin_cutoff, tz="UTC")
    load_start = (cutoff_ts - pd.Timedelta(days=train_memory_days + 5)).strftime("%Y-%m-%d")
    load_end = (cutoff_ts + pd.Timedelta(days=forward_days + 1)).strftime("%Y-%m-%d")
    frame, partitions = load_real_bars(SYMBOL, start=load_start, end=load_end)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()

    schedule = CutoffSchedule(arm="FP03_calibration", cutoffs=(cutoff_ts.isoformat(),),
                              source=f"FP03 calibration origin {origin_cutoff}, calendar-spaced "
                                     "(guide FP03.2), fixed before any outcome is known",
                              train_memory_days=train_memory_days)
    # engine_report_level="score": a real pilot on this exact origin (180-day
    # train window, ~300k 1m bars) hit a clean, RLIMIT_AS-caught MemoryError
    # on trial 0 -- attach_canonical_execution_trace's audit ledger, the SAME
    # dominant accumulator FUP-04 already found and fixed on long frames
    # (evidence/corrective_mode4_v3/FUP-04/report_level_memory_repair.json).
    # dynamic_fold_provider.py's own EventAccountScorer._run_account already
    # threads engine_report_level through the search's per-trial scoring
    # (not just the final deployment account), and FUP-04 measured "score"
    # equity-exact against the engine default -- so this changes retention,
    # never the objective value a trial is scored on.
    perf: dict = {}
    with Stage("origin_search", perf):
        result = run_cutoff_walk_forward(
            ALPHA_ID, frame, schedule, param_ranges=engine_param_ranges(ALPHA_ID),
            strategy_class=ZeroSignalStrategy, optuna_trials=trials, seed=seed, route=route,
            research_retention="none", engine_report_level="score")
    return {
        "origin_cutoff": origin_cutoff, "train_memory_days": train_memory_days,
        "forward_days": forward_days, "trials_requested": trials, "seed": seed,
        "market_partitions_used": partitions, "load_start": load_start, "load_end": load_end,
        "frame_rows": int(len(frame)), "wf_result": result,
        "frame_index_last": frame.index[-1].isoformat(),
        "wall_seconds_measured": round(time.time() - t0, 6),
        "instrumentation": perf["origin_search"],
    }


def _trial_records(wf_result: dict) -> list[dict]:
    records = wf_result.get("trial_records")
    if records is None:
        raise ValueError("run_cutoff_walk_forward result carries no trial_records")
    return sorted(records, key=lambda r: r["trial_id"])


def region_coverage(alpha_id: str, records: list[dict]) -> dict:
    """Raw/unique coverage of the DECLARED grid -- a measure, not an
    adjective (guide's own 'raw/unique/behavioral coverage có số đo')."""
    from ..selector.alpha_schemas import SCHEMAS

    schema = SCHEMAS[alpha_id]
    grid_sizes = {name: len(spec.grid()) for name, spec in schema.specs.items()
                 if spec.informative}
    total_grid = 1
    for size in grid_sizes.values():
        total_grid *= max(1, size)
    unique_params = {tuple(sorted(r["params"].items())) for r in records}
    objectives = [r["objective"] for r in records if r.get("objective") is not None]
    behavioral_spread = (max(objectives) - min(objectives)) if len(objectives) >= 2 else 0.0
    return {
        "declared_grid_size": total_grid, "per_dimension_grid_sizes": grid_sizes,
        "n_attempted": len(records), "n_unique": len(unique_params),
        "raw_coverage_fraction": len(records) / total_grid if total_grid else 0.0,
        "unique_coverage_fraction": len(unique_params) / total_grid if total_grid else 0.0,
        "behavioral_objective_spread": behavioral_spread,
        "behavioral_objective_min": min(objectives) if objectives else None,
        "behavioral_objective_max": max(objectives) if objectives else None,
    }


def selected_at_prefix(records: list[dict]) -> dict | None:
    """The best-objective completed trial within this prefix -- what 'the
    checkpoint's selected candidate' means here. Distinct from the engine's
    own is_only_robust temporal+plateau selection (guide 6.4's
    candidate-pool concept), reported separately as a simpler, always-
    computable summary; the full is_only_robust selection is what FP-04/05
    consume from the frozen pool, not recomputed here."""
    completed = [r for r in records if not r.get("pruned") and r.get("objective") is not None]
    if not completed:
        return None
    best = max(completed, key=lambda r: r["objective"])
    return {"trial_id": best["trial_id"], "params": best["params"], "objective": best["objective"]}


def checkpoints_from_prefix(alpha_id: str, wf_result: dict, *,
                            levels=CHECKPOINT_LEVELS) -> list[dict]:
    """Sequential-prefix checkpoints (guide 6.2): checkpoint N uses ONLY the
    first N trials in ask/tell (trial_id) order -- never re-run, never a
    separately-seeded study.

    The engine reports only the WHOLE call's wall_seconds, not a per-trial
    timestamp, so a checkpoint's own cost cannot be MEASURED in isolation
    without re-running (which the sequential-prefix rule forbids). Reported
    as an explicit linear ESTIMATE (total_wall_seconds * level / n_trials),
    never presented as a measurement -- guide 11.6 distinguishes the two."""
    from .search_introspection import classify_real_trials

    all_records = _trial_records(wf_result)
    total_wall = wf_result.get("wall_seconds")
    n_total = len(all_records)
    checkpoints = []
    for level in levels:
        if level > n_total:
            checkpoints.append({"level": level, "status": "NOT_REACHED",
                               "n_trials_available": n_total})
            continue
        prefix = all_records[:level]
        checkpoints.append({
            "level": level, "status": "REACHED",
            "selected": selected_at_prefix(prefix),
            "coverage": region_coverage(alpha_id, prefix),
            "search_classification": classify_real_trials(prefix),
            "estimated_wall_seconds": (
                None if total_wall is None or not n_total
                else round(total_wall * level / n_total, 3)),
            "estimation_method": "linear interpolation of the whole call's measured "
                                 "wall_seconds by trial-count fraction -- NOT a per-trial "
                                 "measurement (the engine does not expose one)",
        })
    return checkpoints
