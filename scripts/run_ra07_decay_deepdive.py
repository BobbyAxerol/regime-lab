#!/usr/bin/env python3
"""RA-07 decay deep-dive (user-requested follow-up, 2026-09-19, not a formal
RA-0N phase -- see AGENTS.md for why: it extends RA-07's own already-approved
D1 measurement with more real folds, reusing RA-07's tested D1 function
unchanged, rather than opening a new guide phase).

The user's point: reducing IS->OOS decay is a meaningful goal on its own,
independent of whether it shows up as higher absolute PnL (which the
PLACEBO_TIMING control already showed is confounded with cadence). But
RA-07's own D1 measurement only had 2-3 folds per arm (90-day pilot window)
-- nowhere near enough to trust a "less decay" pattern, and inspecting the
raw BTCUSDT M4_REGIME rows individually shows exactly why: one huge
improvement (+3.97 Sharpe), one huge additional decay (-4.91 Sharpe), one
mid-sized decay (-3.83) -- a 3-point average hiding two outliers pulling in
opposite directions, not a consistent trend.

This script re-runs M4_CAL / M4_CAL_MATCHED / M4_REGIME over a MUCH LONGER
real BTCUSDT window (2021-01-01 -> 2022-05-15, ~16.5 months instead of 90
days) so M4_REGIME clears exactly the user's requested >=10 real folds --
verified via a cheap, 0-engine-call query against the real emissions
artifact before committing to this run (10 real triggers land inside this
window at the SAME frozen min_gap/max_age parameters RA-05/07 already used,
the last one on 2022-03-17 with 58 days of runway to mature before
window_end, comparable to the ~45-day gap between the others). Everything
else (train_memory, trials/cutoff, seed, route, economics) is held
IDENTICAL to RA-05/07's frozen contract -- only the window length and the
regime budget cap (2 -> 10, since RA-05's cap was a 90-day phase-owned
scale limit, not a methodological one) change.

ONE PROCESS PER ARM (--run-arm), never all three at once: the first attempt
ran all three arms sequentially inside one process and was OOM-killed by the
kernel (RSS ~5.1 GiB on a 9.7 GiB box with other sessions also resident --
confirmed via dmesg, not guessed). Isolating each arm in its own subprocess
bounds peak memory to whatever ONE arm's ~10-13 real folds need, and frees
it fully when that subprocess exits, before the next arm starts.

Usage:
  lab_venv/bin/python scripts/run_ra07_decay_deepdive.py --smoke        # tiny/fast dry run (orchestrator, spawns 3 subprocesses)
  lab_venv/bin/python scripts/run_ra07_decay_deepdive.py                # real run (orchestrator, spawns 3 subprocesses sequentially)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.experiments.dynamic_fold_provider import (  # noqa: E402
    ZeroSignalStrategy, engine_param_ranges, run_cutoff_walk_forward,
)
from crypto_regime_lab.ra.phase_common import protected_fingerprint, sh, utcnow, write_text_atomic  # noqa: E402
from crypto_regime_lab.ra.ra05_arms import (  # noqa: E402
    build_calendar_schedule, build_regime_schedule, forecast_cal_matched_test_days,
)
from crypto_regime_lab.ra.ra05_market import EMISSIONS_ARTIFACT, load_real_bars, load_real_emissions  # noqa: E402
from crypto_regime_lab.ra.ra07_decay import compute_d1_rows  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.time_edge.execution import PreparedAccount  # noqa: E402

STUDY = "regime_time_edge_ra_v1"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
DEFAULT_TRAIN_MEMORY_DAYS = 45
DEFAULT_CAL_TEST_DAYS = 60
DEFAULT_TRIALS = 8
DEFAULT_SEED = 20260918
DEFAULT_ROUTE = "event"
REGIME_MIN_GAP_DAYS = 45.0
REGIME_MAX_AGE_DAYS = 180.0
DEEPDIVE_REGIME_BUDGET = 10  # the user's requested floor exactly; reduced from an initial 12 to
# cut real-run memory/compute after the first attempt's OOM kill (this is a shared, busy box --
# other unrelated live processes were already holding ~4.6 GiB when that attempt ran)
DEEPDIVE_TRIALS = 2  # deliberately BELOW DEFAULT_TRIALS=8 (RA-05/07's own frozen contract value)
# for THIS deep-dive only -- disclosed deviation, not silently reused. Root cause of the OOM that
# survived the PreparedAccount fix: run_cutoff_walk_forward's optimization_config hardcodes
# research_retention="full_trial_ledger" (dynamic_fold_provider.py) -- the engine itself, not
# anything in this lab's own code, is asked to retain a full per-trial ledger for EVERY Optuna
# trial of the WHOLE arm run, for its entire duration. RA-05/06/07's own real runs stayed safe at
# 2-3 folds x 8 trials = 16-24 total trials; M4_CAL here is ~8 folds x 8 trials = 64, M4_REGIME
# ~11 folds x 8 = 88 -- confirmed by dmesg: M4_CAL was OOM-killed (anon-rss 4.75 GiB) within the
# last ~60s of an otherwise-stable 30-minute run, i.e. right as the trial count neared its peak,
# not gradually -- consistent with ledger accumulation, not with the per-fold PreparedAccount
# mechanism already fixed (that pattern was a slow, steady climb from the start). This constant
# is NOT something this script can safely fix at its root: research_retention is hardcoded inside
# run_cutoff_walk_forward, which is shared, already-tested infrastructure other RA phases depend
# on -- reducing the total trial count is the only lever available without touching it.


def _prepared_for_fold(frame: pd.DataFrame, *, fold_row: dict) -> "PreparedAccount":
    """A FRESH PreparedAccount over a frame slice truncated just past this
    fold's own cutoff -- never the full multi-month deep-dive frame.

    Root cause of every OOM crash in this script's earlier attempts:
    PreparedAccount._window(first) caches `self.frame.iloc[key:]` -- from
    `first` (the fold's own train_start) all the way to the END of
    whatever frame it was built from -- and prepares a FULL native engine
    session over that whole slice, forever (`self._windows` is never
    cleared). Reusing ONE PreparedAccount across every fold of a long
    window means each fold adds another near-full-length cached window,
    and an EARLY fold's slice is almost the entire frame. That accumulates
    as O(fold_count x frame_length), which is exactly what scaled a 90-day/
    2-3-fold run (cheap) into a 10-16.5-month/8-13-fold run (~5 GiB, OOM-
    killed four times) -- independent of trial count or (within the range
    tried) window length alone. TrainingScorer only ever needs
    account_returns over [train_start, cutoff) (guide's own ~45-day train
    window), so each fold gets its OWN small, disposable PreparedAccount
    here instead of sharing one that never shrinks.
    """
    cutoff = pd.Timestamp(fold_row["test_start"])
    buffer_end = cutoff + pd.Timedelta(days=2)
    sliced = frame.loc[frame.index < buffer_end]
    return PreparedAccount(sliced)


def build_d1_for_arm(*, frame, alpha_id, symbol, arm_name, outcome, evidence_dir, lab_run_id):
    if not outcome.get("ok"):
        return [], {"ok": False, "error": outcome.get("error")}
    fold_table = outcome["run"].get("fold_selection_table") or []
    equity_daily = (outcome["run"].get("account") or {}).get("equity_daily") or []
    window_end_fallback = fold_table[-1]["test_end"] if fold_table else None
    rows = []
    for index, fold_row in enumerate(fold_table):
        deploy_end = (fold_table[index + 1]["test_start"] if index + 1 < len(fold_table)
                     else fold_row.get("test_end") or window_end_fallback)
        fold_prepared = _prepared_for_fold(frame, fold_row=fold_row)
        rows.extend(compute_d1_rows(
            prepared=fold_prepared, alpha_id=alpha_id, symbol=symbol, arm=arm_name,
            fold_row=fold_row, equity_daily=equity_daily, deploy_end=deploy_end,
            evidence_dir=evidence_dir / arm_name / str(index), lab_run_id=lab_run_id,
            regime_at_selection=None))
        del fold_prepared  # drop the reference now, don't wait for the loop to end
    return rows, {"ok": True, "fold_count": len(fold_table),
                 "equity_last": (outcome["run"].get("account") or {}).get("equity_last"),
                 "wall_seconds": outcome["run"].get("wall_seconds")}


def summarize(rows, *, metric_name):
    picked = [r for r in rows if r["metric_name"] == metric_name and r["signed_delta"] is not None]
    if not picked:
        return {"n": 0}
    deltas = [r["signed_delta"] for r in picked]
    worse = sum(1 for d in deltas if d < 0)
    better = sum(1 for d in deltas if d > 0)
    lefts = [r["left_value"] for r in picked if r["left_value"] is not None]
    rights = [r["right_value"] for r in picked if r["right_value"] is not None]
    return {
        "n": len(picked), "oos_worse_than_is": worse, "oos_better_than_is": better,
        "mean_signed_delta": sum(deltas) / len(deltas),
        "median_signed_delta": sorted(deltas)[len(deltas) // 2],
        "min_signed_delta": min(deltas), "max_signed_delta": max(deltas),
        "mean_is": (sum(lefts) / len(lefts)) if lefts else None,
        "mean_oos": (sum(rights) / len(rights)) if rights else None,
        "per_fold_deltas": deltas,
    }


def run_single_arm(args) -> int:
    """One arm, one process. Writes a compact JSON (D1 rows + summary only,
    never the full fold table / account) to --out, then exits -- memory is
    reclaimed by the OS the moment this process ends.

    Calls `run_cutoff_walk_forward` DIRECTLY instead of going through
    `ra05_discovery.run_one_arm` -- `run_one_arm` unconditionally runs a
    second pass (`score_fold_for_admission`) over every fold to build the
    admission/funnel record, which this script never reads (`outcome
    ["funnel"]`, `switches_admitted` etc. are used nowhere below -- grepped
    to confirm before removing this call, not assumed). That second pass is
    what was actually driving every OOM crash (see `_prepared_for_fold`'s
    docstring for the mechanism); skipping it removes the single biggest
    cost this script was paying for nothing.
    """
    out_dir = Path(args.evidence_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame, partitions = load_real_bars(SYMBOL, start=args.data_load_start, end=args.window_end)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()

    if args.run_arm == "M4_REGIME":
        window_emissions = load_real_emissions(window_start=args.window_start,
                                               window_end=args.window_end)["emissions"]
        schedule = build_regime_schedule(
            window_emissions, window_start=args.window_start, window_end=args.window_end,
            train_memory_days=args.train_memory_days, min_gap_days=REGIME_MIN_GAP_DAYS,
            max_age_days=REGIME_MAX_AGE_DAYS, budget=args.regime_budget)
    else:
        schedule = build_calendar_schedule(args.window_start, args.window_end,
                                           test_days=args.test_days,
                                           train_memory_days=args.train_memory_days)
        if args.run_arm == "M4_CAL_MATCHED":
            schedule = replace(schedule, arm="M4_CAL_MATCHED")

    try:
        run_result = run_cutoff_walk_forward(
            ALPHA_ID, frame, schedule, param_ranges=engine_param_ranges(ALPHA_ID),
            strategy_class=ZeroSignalStrategy, optuna_trials=args.trials, seed=args.seed,
            route=args.route)
    except Exception as exc:  # noqa: BLE001 -- one arm's failure must not crash the orchestrator
        run_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    outcome = {"arm": args.run_arm, "ok": run_result.get("ok", False),
              "error": run_result.get("error"), "run": run_result}
    d1_rows, meta = build_d1_for_arm(frame=frame, alpha_id=ALPHA_ID, symbol=SYMBOL,
                                     arm_name=args.run_arm, outcome=outcome,
                                     evidence_dir=out_dir / "d1", lab_run_id=args.lab_run_id)
    result = {
        "arm": args.run_arm, "meta": meta,
        "mean_daily_return_decay": summarize(d1_rows, metric_name="mean_daily_return"),
        "sharpe_decay": summarize(d1_rows, metric_name="sharpe"),
        "d1_rows": d1_rows, "market_partitions_used": partitions,
    }
    Path(args.out).write_text(json.dumps(result))
    return 0 if outcome.get("ok") else 1


def orchestrate(args) -> int:
    started = time.perf_counter()
    prot_before = protected_fingerprint()

    if args.smoke:
        window_start, window_end = "2021-01-01", "2021-02-15"
        data_load_start = "2020-12-01"
        regime_budget, trials = 2, 2
    else:
        window_start, window_end = "2021-01-01", "2022-05-15"
        data_load_start = "2020-11-01"
        regime_budget, trials = DEEPDIVE_REGIME_BUDGET, DEEPDIVE_TRIALS

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY, lab_run_id=new_lab_run_id("ra07decaydive"))
    run_dir = writer.run_dir
    scratch = run_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    script = str(Path(__file__).resolve())

    def spawn(arm, test_days=None):
        out_path = scratch / f"{arm}.json"
        cmd = [py, script, "--run-arm", arm, "--window-start", window_start,
              "--window-end", window_end, "--data-load-start", data_load_start,
              "--train-memory-days", str(DEFAULT_TRAIN_MEMORY_DAYS), "--trials", str(trials),
              "--seed", str(DEFAULT_SEED), "--route", DEFAULT_ROUTE,
              "--regime-budget", str(regime_budget), "--lab-run-id", writer.lab_run_id,
              "--evidence-dir", str(scratch / arm), "--out", str(out_path)]
        if test_days is not None:
            cmd += ["--test-days", str(test_days)]
        subprocess.run(cmd, check=True)
        return json.loads(out_path.read_text())

    with writer.attempt("decay_deepdive") as att:
        cal_result = spawn("M4_CAL", test_days=DEFAULT_CAL_TEST_DAYS)
        if not cal_result["meta"].get("ok"):
            raise RuntimeError(f"M4_CAL failed: {cal_result['meta'].get('error')}")

        full_emissions = json.loads(EMISSIONS_ARTIFACT.read_text())["emissions"]
        per_selection_wall_seconds = (cal_result["meta"]["wall_seconds"]
                                      / max(1, cal_result["meta"]["fold_count"]))
        forecast = forecast_cal_matched_test_days(
            full_emissions, window_start=window_start, window_end=window_end,
            per_selection_wall_seconds=per_selection_wall_seconds)

        cal_matched_result = spawn("M4_CAL_MATCHED", test_days=forecast["chosen_test_days"])
        regime_result = spawn("M4_REGIME")

        arm_results = {"M4_CAL": cal_result, "M4_CAL_MATCHED": cal_matched_result,
                      "M4_REGIME": regime_result}
        all_d1_rows = [row for r in arm_results.values() for row in r["d1_rows"]]
        arm_summaries = {name: {"meta": r["meta"],
                                "mean_daily_return_decay": r["mean_daily_return_decay"],
                                "sharpe_decay": r["sharpe_decay"]}
                         for name, r in arm_results.items()}

        result = {
            "schema": "regime_lab.ra07_decay_deepdive.v1",
            "purpose": ("user-requested follow-up: does M4_REGIME show LESS IS->OOS decay than "
                       "calendar scheduling, with enough folds (>=10) to trust the pattern? Not a "
                       "formal RA-0N phase -- extends RA-07's own D1 measurement, same function, "
                       "more real folds. Each arm ran in its OWN subprocess (memory isolation; "
                       "the first attempt OOM-killed running all 3 arms in one process)."),
            "window": [window_start, window_end], "regime_budget": regime_budget,
            "train_memory_days": DEFAULT_TRAIN_MEMORY_DAYS, "trials": trials, "seed": DEFAULT_SEED,
            "route": DEFAULT_ROUTE, "cal_matched_forecast": forecast,
            "arm_summaries": arm_summaries, "all_d1_rows": all_d1_rows,
            "phase_wall_seconds": round(time.perf_counter() - started, 1),
            "smoke": args.smoke, "protected_before": prot_before,
        }
        writer.write_json("decay_deepdive.json", result, schema="regime_lab.ra07_decay_deepdive.v1")

        prot_after = protected_fingerprint()
        fold_counts_str = ", ".join(f"{n}={arm_summaries[n]['meta'].get('fold_count')}"
                                    for n in arm_summaries)
        write_text_atomic(run_dir / "note.md", (
            f"# RA-07 decay deep-dive ({'smoke' if args.smoke else 'real'})\n\n"
            f"- window: {window_start} -> {window_end}\n"
            f"- regime_budget: {regime_budget}\n"
            f"- fold counts: {fold_counts_str}\n"
            f"- one subprocess per arm (memory isolation after the first attempt's OOM kill)\n"
            f"- git_branch: {sh(['git', 'branch', '--show-current'], cwd=LAB)}\n"
            f"- git_head: {sh(['git', 'rev-parse', 'HEAD'], cwd=LAB)}\n"
            f"- protected_status_after: {prot_after['git_status_porcelain'] or 'clean'}\n"
            f"- started_at: {utcnow()}\n"
        ))
        att.detail = {"run_dir": str(run_dir),
                      "fold_counts": {n: arm_summaries[n]["meta"].get("fold_count")
                                     for n in arm_summaries}}

    print(json.dumps({
        "run_dir": str(run_dir),
        "fold_counts": {n: arm_summaries[n]["meta"].get("fold_count") for n in arm_summaries},
        "mean_daily_return_decay": {n: arm_summaries[n]["mean_daily_return_decay"].get("mean_signed_delta")
                                    for n in arm_summaries},
        "sharpe_decay": {n: arm_summaries[n]["sharpe_decay"].get("mean_signed_delta")
                        for n in arm_summaries},
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--run-arm", choices=("M4_CAL", "M4_CAL_MATCHED", "M4_REGIME"), default=None,
                        help="internal: run exactly one arm in its own process, write --out, exit")
    parser.add_argument("--window-start")
    parser.add_argument("--window-end")
    parser.add_argument("--data-load-start")
    parser.add_argument("--train-memory-days", type=int)
    parser.add_argument("--trials", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--route")
    parser.add_argument("--test-days", type=int, default=None)
    parser.add_argument("--regime-budget", type=int, default=None)
    parser.add_argument("--lab-run-id")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.run_arm:
        return run_single_arm(args)
    return orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
