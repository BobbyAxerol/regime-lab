"""RA07.2: run the second cell under RA-05's EXACT frozen contract (same
window, train_memory_days, trials, route, seed), symbol swapped only.

Deliberately NOT a reuse of RF-04's own A-SC/ETHUSDT numbers
(evidence/corrective_mode4_v3/RF-04/cell_coverage.json): that run used a
DIFFERENT contract (window 2021-01-01..2022-06-30 vs RA-05's
2021-01-01..2021-04-01, train_memory_days=180 vs 45, seed=20260911 vs
20260918, no M4_CAL_MATCHED arm at all for that cell). Mixing a
differently-parameterized run into a paired cross-cell comparison is exactly
the contract-equivalence mistake LAB-06 flagged elsewhere in this lab's own
history ("two contrasts between IDENTICAL arms ... came out different ...
which is how it surfaced"). This module re-runs the full 4-arm contract
fresh on ETHUSDT instead, so cell 1 and cell 2 differ in EXACTLY one thing:
the traded symbol (the regime emissions are the SAME BTC-derived tape used
for cell 1 -- cell 2 therefore tests "does a BTC-fit regime tape's timing
transfer to trading ETH", not "does an ETH-fit regime model help ETH",
and the report must say so plainly, guide RA07.2: "phai noi ro dang kiem
transfer loai nao").
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .ra05_arms import (
    build_calendar_schedule, build_regime_schedule, build_static_schedule,
    classify_regime_trigger_reasons, forecast_cal_matched_test_days,
)
from .ra05_discovery import action_divergence, descriptive_returns, run_one_arm
from .ra05_market import load_real_bars
from ..time_edge.execution import PreparedAccount

CELL2_SYMBOL = "ETHUSDT"
CELL2_TRANSFER_KIND = "cross_symbol_same_alpha_shared_btc_derived_regime_tape"


def run_cell2_full(*, alpha_id: str, symbol: str, window_start: str, window_end: str,
                   data_load_start: str, train_memory_days: int, cal_test_days: int,
                   trials: int, seed: int, route: str, full_emissions_for_forecast: list,
                   window_emissions: list, evidence_dir, lab_run_id: str) -> dict:
    """Mirrors run_ra05.py's main() sequencing exactly (STATIC first to
    measure per-selection wall time -> CAL_MATCHED cadence forecast from a
    development prefix -> the remaining 3 arms), as a reusable function
    instead of a copy-pasted script, so cell 1 and cell 2 share one
    implementation and cannot silently drift apart.
    """
    frame, partitions = load_real_bars(symbol, start=data_load_start, end=window_end)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    prepared = PreparedAccount(frame)

    static_schedule = build_static_schedule(window_start, window_end,
                                            train_memory_days=train_memory_days)
    static_outcome = run_one_arm(alpha_id, frame, static_schedule, prepared=prepared,
                                 trials=trials, seed=seed, route=route,
                                 evidence_dir=evidence_dir, lab_run_id=lab_run_id)
    if not static_outcome.get("ok"):
        return {"capability_status": "BLOCKED_CAPABILITY",
               "blocked_reason": f"STATIC arm failed on {symbol}: {static_outcome.get('error')}",
               "symbol": symbol, "alpha_id": alpha_id}
    per_selection_wall_seconds = (static_outcome["run"]["wall_seconds"]
                                  / max(1, static_outcome["run"]["fold_count"]))

    forecast = forecast_cal_matched_test_days(
        full_emissions_for_forecast, window_start=window_start, window_end=window_end,
        per_selection_wall_seconds=per_selection_wall_seconds)

    cal_schedule = build_calendar_schedule(window_start, window_end, test_days=cal_test_days,
                                           train_memory_days=train_memory_days)
    cal_matched_schedule = replace(
        build_calendar_schedule(window_start, window_end, test_days=forecast["chosen_test_days"],
                                train_memory_days=train_memory_days),
        arm="M4_CAL_MATCHED")
    regime_schedule = build_regime_schedule(window_emissions, window_start=window_start,
                                            window_end=window_end,
                                            train_memory_days=train_memory_days)
    regime_trigger_lookup = classify_regime_trigger_reasons(
        regime_schedule.cutoffs, window_emissions,
        shared_initial=pd.Timestamp(window_start, tz="UTC").isoformat())

    cal_outcome = run_one_arm(alpha_id, frame, cal_schedule, prepared=prepared, trials=trials,
                              seed=seed, route=route, evidence_dir=evidence_dir,
                              lab_run_id=lab_run_id)
    cal_matched_outcome = run_one_arm(alpha_id, frame, cal_matched_schedule, prepared=prepared,
                                      trials=trials, seed=seed, route=route,
                                      evidence_dir=evidence_dir, lab_run_id=lab_run_id)
    regime_outcome = run_one_arm(alpha_id, frame, regime_schedule, prepared=prepared,
                                 trials=trials, seed=seed, route=route,
                                 evidence_dir=evidence_dir, lab_run_id=lab_run_id,
                                 trigger_lookup=regime_trigger_lookup)

    arms = {"STATIC": static_outcome, "M4_CAL": cal_outcome,
           "M4_CAL_MATCHED": cal_matched_outcome, "M4_REGIME": regime_outcome}
    compact_arms = {}
    for name, outcome in arms.items():
        if not outcome.get("ok"):
            compact_arms[name] = outcome
            continue
        run = dict(outcome["run"])
        trial_count = run.pop("trial_records", None)
        run["trial_records_count"] = len(trial_count) if trial_count is not None else None
        compact_arms[name] = {**outcome, "run": run}

    return {
        "capability_status": "EXECUTED", "symbol": symbol, "alpha_id": alpha_id,
        "transfer_kind": CELL2_TRANSFER_KIND,
        "transfer_kind_note": ("A-SC trades ETHUSDT using the SAME BTC-derived regime emissions "
                              "tape as cell 1 (BTCUSDT) -- this tests whether a BTC-fit regime "
                              "model's TIMING transfers to trading a different, correlated "
                              "symbol, not whether an ETH-fit regime model would help ETH."),
        "market_partitions_used": partitions,
        "per_selection_wall_seconds_measured": per_selection_wall_seconds,
        "cal_matched_forecast": forecast,
        "arms": compact_arms,
        "action_divergence": action_divergence(arms),
        "descriptive_returns": descriptive_returns(arms),
        "_frame": frame, "_prepared": prepared,  # in-memory only; popped before JSON persistence
    }
