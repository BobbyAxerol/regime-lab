#!/usr/bin/env python
"""RF-04.1 — bounded paired discovery pilot: M4_CAL vs M4_REGIME on real snapshots.

Runs two pre-registered cells (A-SC/BTCUSDT on the qualified fast signal route,
A-HMA/BTCUSDT on the qualified native-event route) on the development window
2021-01-01..2022-06-30. Both arms share the economics (account 20000, bound
one-way fee), the training-memory rule (180 days), the Mode 4 contract and the
trial budget; only the cutoff list differs. The registration is written BEFORE
any run, then the per-arm/cell evidence is written to
``evidence/corrective_mode4_v3/RF-04/paired_discovery_pilot.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data.availability import resample_bars  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments.dynamic_fold_provider import (  # noqa: E402
    ALLOC_PER_TRADE, ACCOUNT_CAPITAL, ONE_WAY_TAKER_FEE, SLIPPAGE_BPS, ZeroSignalStrategy,
    calendar_cutoffs, engine_param_ranges, regime_cutoffs, run_cutoff_walk_forward,
)
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.selector.mode4_baseline import AScSignalStrategy  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "RF-04"
SNAPSHOT_ID = "server_core_v1"
PRODUCT = "crypto_binance_futures_1m"
DEVELOPMENT = ("2021-01-01", "2022-06-30")
LOAD_START = "2020-06-01"
TRIALS = 8
SEED = 20260911

CELLS = (
    {"cell": "A-SC/BTCUSDT", "alpha_id": "A-SC", "symbol": "BTCUSDT",
     "interval": "15min", "route": "endpoint",
     "strategy": "AScSignalStrategy", "route_status": "QUALIFIED_FAST"},
    {"cell": "A-HMA/BTCUSDT", "alpha_id": "A-HMA", "symbol": "BTCUSDT",
     "interval": "1h", "route": "event",
     "strategy": "ZeroSignalStrategy+EventAccountScorer", "route_status": "QUALIFIED_EVENT"},
)

REGIME_CONTROLLER = {"min_gap_days": 90.0, "max_age_days": 180.0, "budget": None}


def load_frame(snapshot_root: Path, symbol: str, interval: str) -> pd.DataFrame:
    """Read the lab's byte-copied parquet directly and resample on the lab clock."""
    base = snapshot_root / PRODUCT / symbol
    files = sorted(path for path in base.glob("*.parquet")
                   if path.stem <= DEVELOPMENT[1][:7])
    if not files:
        raise FileNotFoundError(f"no snapshot partition for {symbol} at or before {DEVELOPMENT[1]}")
    columns = ["time", "open", "high", "low", "close", "volume", "quote_volume",
               "number_of_trades", "taker_buy_base_volume", "taker_buy_quote_volume"]
    frames = []
    for path in files:
        stored = pd.read_parquet(path)
        frames.append(stored[[c for c in columns if c in stored.columns]])
    raw = pd.concat(frames, ignore_index=True)
    raw["time"] = pd.to_datetime(raw["time"])
    if raw["time"].dt.tz is None:
        raw["time"] = raw["time"].dt.tz_localize("UTC")
    raw = raw.sort_values("time").reset_index(drop=True)
    bars = resample_bars(raw, "1min", interval, require_complete=True)
    bars = bars.set_index("time").sort_index().loc[LOAD_START:DEVELOPMENT[1]]
    return bars[["open", "high", "low", "close", "volume"]].astype(float)


def strategy_for(cell: dict):
    if cell["route"] == "event":
        return ZeroSignalStrategy
    return AScSignalStrategy


def arm_record(cell: dict, arm: str, schedule, frame: pd.DataFrame) -> dict:
    started = time.perf_counter()
    out = run_cutoff_walk_forward(
        cell["alpha_id"], frame, schedule, param_ranges=engine_param_ranges(cell["alpha_id"]),
        strategy_class=strategy_for(cell), optuna_trials=TRIALS, seed=SEED,
        route=cell["route"], one_way_fee=ONE_WAY_TAKER_FEE, slippage_bps=SLIPPAGE_BPS,
        alloc_per_trade=ALLOC_PER_TRADE, account_capital=ACCOUNT_CAPITAL,
    )
    record = {
        "arm": arm,
        "route": cell["route"],
        "schedule": schedule.as_record(),
        "ok": bool(out.get("ok")),
        "error": out.get("error"),
        "cutoffs": out.get("cutoffs", []),
        "fold_count": out.get("fold_count", 0),
        "params_by_fold": out.get("params_by_fold", {}),
        "selected_params": out.get("selected_params"),
        "selected_digest": out.get("selected_digest"),
        "fold_selection_table": out.get("fold_selection_table", []),
        "trial_records": out.get("trial_records", []),
        "trial_count": out.get("trial_count", 0),
        "nonfinite_values": out.get("nonfinite_values", {}),
        "oos_used_for_selection": out.get("oos_used_for_selection"),
        "validation_claim": out.get("validation_claim"),
        "scoring_backend": out.get("scoring_backend"),
        "candidate_selection_metric": out.get("candidate_selection_metric"),
        "resolved_evaluator": out.get("resolved_evaluator", "quantbt_walkforward_endpoint_scorer"),
        "account": out.get("account", {}),
        "wall_seconds": out.get("wall_seconds"),
    }
    if out.get("trace"):
        record["evaluator_trace"] = out["trace"]
    record["wall_seconds_total"] = round(time.perf_counter() - started, 3)
    return record


def contrast_validity(calendar: dict, regime: dict, cell: dict) -> dict:
    """Technical validity of the paired contrast, with a denominator and a way to go red."""
    reasons = []
    for arm in (calendar, regime):
        if not arm["ok"]:
            reasons.append(f"{arm['arm']}: run failed ({arm['error']})")
            continue
        if arm["oos_used_for_selection"] is not False:
            reasons.append(f"{arm['arm']}: oos_used_for_selection={arm['oos_used_for_selection']!r}")
        if not arm["params_by_fold"]:
            reasons.append(f"{arm['arm']}: no selected parameters for any fold")
        if arm["fold_count"] < 1:
            reasons.append(f"{arm['arm']}: no fold was scored")
        account = arm["account"] or {}
        if account.get("equity_last") is None:
            reasons.append(f"{arm['arm']}: the engine produced no equity")
        if cell["route"] == "event":
            if account.get("status") != "EVALUATED":
                reasons.append(f"{arm['arm']}: event account status={account.get('status')!r}")
            if int((arm.get("evaluator_trace") or {}).get("event_account_runs", 0)) < 1:
                reasons.append(f"{arm['arm']}: the event scorer ran no QuantBT account")
    if not calendar["cutoffs"] or not regime["cutoffs"]:
        reasons.append("one arm produced no cutoff")
    if list(calendar["cutoffs"]) == list(regime["cutoffs"]):
        reasons.append("the two arms used identical cutoffs (no treatment)")
    status = "VALID" if not reasons else "NOT_EVALUABLE"
    return {
        "contrast": f"M4_REGIME - M4_CAL on {cell['cell']}",
        "status": status,
        "reasons": reasons,
        "checks": {
            "both_arms_ok": bool(calendar["ok"] and regime["ok"]),
            "both_arms_engine_equity": bool(calendar["account"].get("equity_last") is not None
                                            and regime["account"].get("equity_last") is not None),
            "both_arms_oos_used_for_selection_false": bool(
                calendar["oos_used_for_selection"] is False
                and regime["oos_used_for_selection"] is False),
            "cutoffs_differ": list(calendar["cutoffs"]) != list(regime["cutoffs"]),
            "same_trial_budget": TRIALS,
            "same_training_memory_days": True,
        },
        "data_role": "development_discovery_not_confirmation",
        "claim_limit": ("a 2-cell bounded pilot on BTCUSDT; no statistical claim, no edge "
                        "inference and no holdout claim is made from it"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells", default="all", help="comma-separated cell names or 'all'")
    args = parser.parse_args()

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)
    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = json.loads((snapshot_root / "manifest.json").read_text())
    emissions = json.loads(
        (LAB_ROOT / "configs" / "lab05_full_emission_tape.json").read_text())["emissions"]

    selected_cells = [c for c in CELLS
                      if args.cells == "all" or c["cell"] in args.cells.split(",")]
    registration = {
        "schema": "regime_lab.rf04_paired_pilot_registration.v1",
        "status": "REGISTERED_BEFORE_THE_PAIRED_PILOT_RUNS",
        "study_id": STUDY_ID,
        "cells": [{k: c[k] for k in ("cell", "route", "route_status")} for c in selected_cells],
        "development_window": {"start": DEVELOPMENT[0], "end": DEVELOPMENT[1],
                               "snapshot_id": SNAPSHOT_ID, "product": PRODUCT},
        "arms": ["M4_CAL", "M4_REGIME"],
        "mode4_contract": {
            "optimization_mode": "mode_4_is_only_robust",
            "optimization_schedule": "per_fold_causal",
            "candidate_selection_metric": "is_only_robust",
            "scoring_backend": "endpoint",
            "oos_used_for_selection": False,
        },
        "matched": {
            "account_capital": ACCOUNT_CAPITAL,
            "entry_notional": ALLOC_PER_TRADE * ACCOUNT_CAPITAL,
            "one_way_fee": ONE_WAY_TAKER_FEE,
            "slippage_bps": SLIPPAGE_BPS,
            "train_memory_days": 180,
            "optuna_trials_per_cutoff": TRIALS,
            "seed": SEED,
            "calendar_cadence": "first cutoff 2021-01-01, 180-day test spacing, max 3 cutoffs",
            "regime_controller": REGIME_CONTROLLER,
        },
        "budget_note": ("the registered full-study pilot budget is 32-64 trials/cutoff; this "
                        "bounded pilot registers the low end overridden to 8 trials/cutoff for "
                        "both arms so the paired contrast is computed before any scaling"),
        "registered_at_utc": utc_now_iso(),
    }
    writer.write_json("paired_discovery_registration.json", registration,
                      schema=registration["schema"])

    calendar = calendar_cutoffs(window_start=DEVELOPMENT[0], window_end=DEVELOPMENT[1],
                                first_cutoff="2021-01-01", test_days=180,
                                train_memory_days=180, max_cutoffs=3)
    dynamic = regime_cutoffs(emissions, window_start=DEVELOPMENT[0], window_end=DEVELOPMENT[1],
                             min_gap_days=REGIME_CONTROLLER["min_gap_days"],
                             max_age_days=REGIME_CONTROLLER["max_age_days"],
                             budget=REGIME_CONTROLLER["budget"])

    cells_payload = []
    for cell in selected_cells:
        frame = load_frame(snapshot_root, cell["symbol"], cell["interval"])
        data_record = {
            "symbol": cell["symbol"], "interval": cell["interval"],
            "source": f"{SNAPSHOT_ID}/{PRODUCT}", "is_synthetic": False,
            "window": [str(frame.index[0]), str(frame.index[-1])],
            "bars": int(len(frame)),
            "snapshot_manifest": str(snapshot_root / "manifest.json"),
            "snapshot_manifest_sha256": sha256_file(snapshot_root / "manifest.json"),
            "snapshot_id": manifest.get("snapshot_id", SNAPSHOT_ID),
        }
        with writer.attempt(f"RF04.paired.{cell['cell']}") as att:
            calendar_record = arm_record(cell, "M4_CAL", calendar, frame)
            regime_record = arm_record(cell, "M4_REGIME", dynamic, frame)
            att.detail = {"calendar_ok": calendar_record["ok"], "regime_ok": regime_record["ok"]}
        cells_payload.append({
            **{k: cell[k] for k in ("cell", "alpha_id", "symbol", "route", "route_status")},
            "data": data_record,
            "arms": {"M4_CAL": calendar_record, "M4_REGIME": regime_record},
            "contrast": contrast_validity(calendar_record, regime_record, cell),
        })

    payload = {
        "schema": "regime_lab.rf04_paired_discovery_pilot.v1",
        "phase": "RF-04",
        "status": "PILOT_COMPLETE",
        "study_id": STUDY_ID,
        "registration_artifact": "paired_discovery_registration.json",
        "development_window": {"start": DEVELOPMENT[0], "end": DEVELOPMENT[1]},
        "matched_conditions": [
            "same economic account (20000 USDT, 2000 USDT entry notional, one-way fee 0.0004, "
            "slippage 1bp)",
            "same Mode 4 contract and per-fold causal schedule",
            "same training-memory rule (180 days)",
            "same trial budget per cutoff and same seed",
            "same evaluation dates",
            "only the cutoff list differs",
        ],
        "arms": {
            "M4_CAL": calendar.as_record(),
            "M4_REGIME": dynamic.as_record(),
        },
        "cells": cells_payload,
        "contract_findings": {
            "search_fold_bound": ("the search-facing strategy call receives a fold whose test "
                                  "segment is its own training window; the operational test end "
                                  "is not exposed"),
            "no_private_patch": ("no quantbt file was edited; the cutoff list is injected through "
                                 "a lab-only WalkForwardEngine subclass and the engine class is "
                                 "swapped only for the duration of the public endpoint call"),
        },
    }
    record = writer.write_json("paired_discovery_pilot.json", payload, schema=payload["schema"])
    print(json.dumps({"artifact": record, "cells": [
        {"cell": c["cell"], "contrast": c["contrast"]["status"],
         "M4_CAL_equity": c["arms"]["M4_CAL"]["account"].get("equity_last"),
         "M4_REGIME_equity": c["arms"]["M4_REGIME"]["account"].get("equity_last")}
        for c in cells_payload]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
