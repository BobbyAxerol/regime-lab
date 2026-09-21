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

This script re-runs M4_CAL / M4_CAL_MATCHED / M4_REGIME over a real BTCUSDT
window MUCH LONGER than RA-07's 90-day pilot: 2021-01-01 -> 2022-01-01 (12
months). Originally this targeted 2022-05-15 (~16.5 months) and a 10-fold
regime budget, but 5 real-scale attempts at that size were stopped before
completing: 2 kernel OOM, 1 manual proactive kill (a sudden RSS spike, ahead
of the kernel), 1 caught by this script's own memory watchdog, 1 reaped by
the Claude Code harness's own system-wide low-memory protection -- none of
them a code-correctness bug, all confirmed via dmesg / harness notification,
not guessed. Per the user's explicit direction (2026-09-20), the window was cut
back and the regime budget lowered to 8 -- verified via a cheap, 0-engine-call
query against the real emissions artifact BEFORE committing to this window
that this loses nothing: the 8th and last real regime trigger inside the
original window lands on 2021-12-17, so 2021-01-01 -> 2022-01-01 still
captures all 8 (a 9th/10th never existed in this window in the first place --
the original ">=10" target was never actually reachable here). M4_CAL's own
test_days (the width of each CALENDAR fold, i.e. how much OOS time one
train/select/test cycle covers) also moved 60 -> 100 days at the user's
request, cutting M4_CAL from 9 folds to 4 in one subprocess -- M4_CAL, not
M4_REGIME, is the arm that actually crashed in every real-scale attempt so
far. Everything else (train_memory, trials/cutoff, seed, route, economics)
stays IDENTICAL to RA-05/07's frozen contract; every deviation here (trials,
research_retention, test_days, window, budget) is disclosed, not silent.

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
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.time_edge.execution import PreparedAccount  # noqa: E402

STUDY = "regime_time_edge_ra_v1"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
DEFAULT_TRAIN_MEMORY_DAYS = 45
DEFAULT_CAL_TEST_DAYS = 60  # RA-05/07's frozen-contract calendar fold width; kept here only as a
# reference value for disclosure math, not used by the real (non-smoke) run below.
DEFAULT_TRIALS = 8
DEFAULT_SEED = 20260918
DEFAULT_ROUTE = "event"
REGIME_MIN_GAP_DAYS = 45.0
REGIME_MAX_AGE_DAYS = 180.0
DEEPDIVE_REGIME_BUDGET = 8  # user's explicit direction (2026-09-20), down from an original ">=10"
# ask that 5 real-scale attempts at the larger window never completed. Verified harmless against
# the real emissions tape BEFORE adopting: inside this deep-dive's (now-shortened) window, only 8
# real regime triggers ever exist at RA-05/07's own frozen min_gap/max_age parameters -- a 9th/10th
# was never reachable here even at the original window length, so 8 is the true ceiling this
# window supports, not a weaker compromise.
DEEPDIVE_CAL_TEST_DAYS = 40  # user's explicit direction (2026-09-21), down from
# the interim 100 (which gave only 4 folds -- too few to read a decay pattern).
# Measured, 0 engine calls: 40-day folds over the 2021-01-01 -> 2022-01-01 window
# give M4_CAL 10 folds, balanced against M4_REGIME's 9 real-trigger cutoffs.
DEEPDIVE_TRIALS = 50  # user's explicit direction (2026-09-21): a 2-trial search
# cannot find an optimum, it can only confirm the pipeline runs. 50 trials is
# ABOVE RA-05/07's frozen contract (8) -- disclosed deviation for THIS deep-dive
# only, not silently reused. Memory-safe by measurement, not by hope: each trial
# is one transient scorer account call (~450 MiB peak at score profile, freed
# after; s2/s6 ratchet probe showed a flat peak, no per-trial retention), and
# research_retention="none" (call site below) stops the per-fold ledger from
# accumulating across the arm. What scales with trials is wall time, not peak.
# for THIS deep-dive only -- disclosed deviation, not silently reused. Un-related to the ledger
# issue below; kept low because it was already proven safe, not re-tested at 8 after that fix.
# The research_retention="full_trial_ledger" default (dynamic_fold_provider.py) was a real,
# confirmed OOM contributor -- fixed at the run_cutoff_walk_forward call site below (passes
# "none"), not by this constant. See that call site's comment for the full trace.


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
        # research_retention="none": the confirmed 3rd OOM root cause. Traced in the
        # installed engine (quantbt/walkforward.py): _capture_research_records extends
        # self._research_full_trial_records / _research_full_candidate_records once per
        # fold, for the WHOLE arm's fold sequence, never cleared -- guarded only by this
        # flag (RA-05/07 default it to "full_trial_ledger", the heaviest level). This
        # script's D1 computation reads none of it (fresh TrainingScorer replay + real
        # equity_daily), and _trial_records() reads the SEPARATE compact wf_result.trial_table,
        # which this flag does not affect. Real memtrace evidence: with the flag still at
        # its RA-05/07 default, M4_CAL held a healthy 2.5-3.8GB sawtooth for ~15 minutes,
        # then climbed to OOM territory as more folds accumulated into that ledger
        # (run ra07decaydive-20260919T143621Z-38d3b0b5, killed by the watchdog at
        # avail=384MB before any kernel OOM could fire).
        run_result = run_cutoff_walk_forward(
            ALPHA_ID, frame, schedule, param_ranges=engine_param_ranges(ALPHA_ID),
            strategy_class=ZeroSignalStrategy, optuna_trials=args.trials, seed=args.seed,
            route=args.route, research_retention="none",
            engine_report_level=getattr(args, "engine_report_level", None))
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


def orchestrate(args, engine_report_level: str | None = None) -> int:
    started = time.perf_counter()
    prot_before = protected_fingerprint()

    if args.smoke:
        window_start, window_end = "2021-01-01", "2021-02-15"
        data_load_start = "2020-12-01"
        regime_budget, trials, cal_test_days = 2, 2, DEFAULT_CAL_TEST_DAYS
    else:
        # Window shortened 2022-05-15 -> 2022-01-01 and regime_budget 10 -> 8 per the user's
        # explicit direction (2026-09-20), after 5 real-scale attempts at the larger size never
        # completed. Verified against the real emissions tape before adopting: this window still
        # contains all 8 real regime triggers the original window had (the 8th lands 2021-12-17,
        # well inside 2022-01-01) -- no loss versus the original ">=10" ask, which this window
        # never actually supported past 8 anyway.
        window_start, window_end = "2021-01-01", "2022-01-01"
        data_load_start = "2020-11-01"
        regime_budget, trials, cal_test_days = (
            DEEPDIVE_REGIME_BUDGET, DEEPDIVE_TRIALS, DEEPDIVE_CAL_TEST_DAYS)

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY, lab_run_id=new_lab_run_id("ra07decaydive"))
    run_dir = writer.run_dir
    scratch = run_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    script = str(Path(__file__).resolve())
    # Root cause of the OOM that survived BOTH the PreparedAccount fix and the
    # trials cut: every arm subprocess inherited this orchestrator's own
    # environment as-is, with no OMP_NUM_THREADS/OPENBLAS_NUM_THREADS/
    # MKL_NUM_THREADS/NUMBA_NUM_THREADS limit -- on this 4-CPU box, BLAS/Numba
    # were therefore free to fan out across all 4 cores for array ops inside
    # the native engine, each thread holding its own working buffers. That
    # matches what was actually observed far better than gradual accumulation
    # does: RSS jumped ~1.6 GiB -> ~3.6 GiB within seconds, not a steady climb.
    # The lab already has a dedicated utility for exactly this
    # (safety/process.py::lab_worker_env, built from the registered
    # sandbox_policy.json resource_budget.cpu_limit=2) -- this script simply
    # never called it when spawning subprocesses. Fixed by passing it as the
    # subprocess env instead of inventing a new thread-limiting mechanism.
    worker_env = lab_worker_env(policy)

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
        if engine_report_level:
            cmd += ["--engine-report-level", engine_report_level]
        subprocess.run(cmd, check=True, env=worker_env)
        return json.loads(out_path.read_text())

    with writer.attempt("decay_deepdive") as att:
        cal_result = spawn("M4_CAL", test_days=cal_test_days)
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
            "engine_report_level": engine_report_level,
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
            f"- engine_report_level: {engine_report_level or 'engine-default'}\n"
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
    parser.add_argument("--engine-report-level", default=None,
                        help=("engine output retention profile passed to "
                              "run_event_account (None=engine default; 'score' "
                              "drops per-bar audit ledgers; measured equity-exact)"))
    parser.add_argument("--lab-run-id")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.run_arm:
        return run_single_arm(args)
    return orchestrate(args, engine_report_level=args.engine_report_level)


if __name__ == "__main__":
    raise SystemExit(main())
