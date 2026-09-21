#!/usr/bin/env python3
"""Stage-by-stage peak-RSS audit of the RA-07 decay deep-dive memory chain.

Why (2026-09-20): the deep-dive was SIGKILLed even after four prior OOM fixes
and after cutting scope (2 trials, 4 folds, 12-month window). This script
measures -- on the lab's real data paths, no engine modification -- which stage
actually drives resident memory, so the fix targets the dominant accumulator
instead of the next guess. Stages, all with real RA-05 contracts:

  s1  frame load            load_real_bars, deep-dive scale (2020-11-01 ->
                            2022-01-01), the frame every stage pays for.
  s2  scorer account        EventAccountScorer's own engine call: one
                            run_event_account over [train_start, train_end]
                            of RA-05 M4_CAL fold 0 (the per-candidate cost,
                            paid trials x folds times).
  s3  deployment account    run_event_account over the FULL frame with RA-05's
                            real params_by_fold schedule (the per-arm cost).
  s4  D1 replay             build_d1_for_arm's fresh PreparedAccount +
                            TrainingScorer over one real fold window.
  s5  isolation control     s2 re-run in a FRESH subprocess (same interpreter
                            startup class as the deep-dive's per-arm workers)
                            -- partitions s2's peak into true footprint vs
                            residual this process failed to return to the OS.

Output: a table on stdout plus a small JSON under ``.cache/mem_audit/``
(regenerable scratch, never study evidence). Pure measurement: no artifact of
any study is read or written, no engine call is added or removed.
"""
from __future__ import annotations

import argparse
import gc
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402

# The deep-dive's own scale (run_ra07_decay_deepdive.py, non-smoke branch).
DEEPDIVE_LOAD_START = "2020-11-01"
DEEPDIVE_WINDOW_END = "2022-01-01"
# RA-05's frozen real window (fold/cutoff source for s2/s4).
RA05_RUN_DIR = LAB / "evidence" / "regime_time_edge_ra_v1" / "ra05-20260918T201236Z-de11db62"
RA05_LOAD_START = "2020-11-01"
RA05_WINDOW_END = "2021-04-01"


def _vm_rss_kib() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return 0


class RssSampler:
    """Background peak-RSS sampler (20 ms tick; python-thread, GIL is fine --
    the engine's own python loop holds the GIL most of the wall time)."""

    def __init__(self) -> None:
        self.peak_kib = _vm_rss_kib()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.peak_kib = _vm_rss_kib()
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(0.02):
                rss = _vm_rss_kib()
                if rss > self.peak_kib:
                    self.peak_kib = rss

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> int:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2.0)
            self._thread = None
        self.peak_kib = max(self.peak_kib, _vm_rss_kib())
        return self.peak_kib


def _mib(kib: int) -> float:
    return round(kib / 1024.0, 1)


class Stage:
    """One measured stage: peak RSS, wall time, and a post-gc residual reading."""

    def __init__(self, name: str, results: dict) -> None:
        self.name = name
        self.results = results
        self.sampler = RssSampler()
        self.notes: dict = {}

    def __enter__(self) -> "Stage":
        gc.collect()
        self.base_kib = _vm_rss_kib()
        self.sampler.start()
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.wall_s = round(time.perf_counter() - self.t0, 3)
        peak = self.sampler.stop()
        gc.collect()
        time.sleep(0.1)
        after_kib = _vm_rss_kib()
        self.results[self.name] = {
            "base_mib": _mib(self.base_kib), "peak_mib": _mib(peak),
            "after_gc_mib": _mib(after_kib),
            "delta_mib": _mib(peak - self.base_kib),
            "residual_mib": _mib(after_kib - self.base_kib),
            "wall_s": self.wall_s, **self.notes,
        }
        del self.sampler


def _ra05_fold_rows() -> list[dict]:
    payload = json.loads((RA05_RUN_DIR / "arms_result.json").read_text())
    run = payload["arms"]["M4_CAL"]["run"]
    folds = run["fold_selection_table"]
    if not folds:
        raise SystemExit("RA-05 M4_CAL fold_selection_table is empty")
    return folds


def stage_s1_load(results: dict, notes: dict) -> tuple[pd.DataFrame, object]:
    """Deep-dive scale frame load -- the baseline every later stage pays."""
    with Stage("s1_frame_load", results) as st:
        frame, partitions = load_real_bars("BTCUSDT", start=DEEPDIVE_LOAD_START,
                                           end=DEEPDIVE_WINDOW_END)
        frame = frame[["open", "high", "low", "close", "volume"]].copy()
        st.notes = {"rows": int(len(frame)), "cols": 5, **notes}
    return frame, partitions


def _event_account_for(frame: pd.DataFrame, initial, schedule, **kwargs):
    from crypto_regime_lab.integration.event_account import run_event_account

    return run_event_account("A-SC", frame, initial=initial, schedule=schedule, **kwargs)


def stage_s2_scorer_account(results: dict, fold_rows: list[dict]) -> None:
    """One scorer-class engine call over one real fold window (RA-05 fold 0):
    the per-candidate, per-fold cost the Mode-4 search pays trials x folds times."""
    from crypto_regime_lab.integration.continuous_account import VersionWindow

    fold = fold_rows[0]
    with Stage("s2_scorer_account_fold0", results) as st:
        frame, _ = load_real_bars("BTCUSDT", start=RA05_LOAD_START, end=RA05_WINDOW_END)
        frame = frame[["open", "high", "low", "close", "volume"]]
        frame.index = pd.DatetimeIndex(frame.index)
        st.notes["load_rows"] = int(len(frame))
        train_start = pd.Timestamp(fold["train_start"])
        train_end = pd.Timestamp(fold["train_end"])
        base = frame.loc[(frame.index >= train_start) & (frame.index <= train_end)]
        st.notes["window_rows"] = int(len(base))
        st.notes["window"] = [fold["train_start"], fold["train_end"]]
        initial = VersionWindow("A-SC-score", dict(fold["selected_params"]), 0, "score-initial")
        run = _event_account_for(base, initial, [])
        st.notes["equity_len"] = int(len(run.equity))
        # Two different counters, kept distinct on purpose: `engine_fill_count`
        # is the NATIVE audit-trail count (reads 0 under a reduced
        # report_level), `strategy_fill_count` is what the lab actually reports
        # and hands to selection. Recording only the first would make a
        # successful reduced-profile run look like it never traded.
        st.notes["engine_fill_count"] = int(run.engine_fill_count)
        st.notes["strategy_fill_count"] = len(getattr(run, "fills", None) or [])
        st.notes["status"] = run.status
        del run, base, frame, initial


def stage_s3_deployment_account(results: dict, fold_rows: list[dict], frame: pd.DataFrame,
                                report_level: str | None = None) -> None:
    """The per-arm deployment call over the FULL deep-dive frame with RA-05's
    real per-fold params (here: RA-05's 2-fold schedule on the 12-month frame)."""
    from crypto_regime_lab.integration.continuous_account import VersionWindow

    with Stage("s3_deployment_full_frame", results) as st:
        idx = frame.index
        moments = {str(i): pd.Timestamp(f["test_start"]) for i, f in enumerate(fold_rows)}
        initial = VersionWindow(
            "A-SC-initial", dict(fold_rows[0]["selected_params"]),
            int(idx.searchsorted(moments["0"], side="left")), "initial")
        schedule = [
            VersionWindow(f"A-SC-{key}", dict(fold_rows[int(key)]["selected_params"]),
                          int(idx.searchsorted(moments[key], side="left")),
                          f"activation-{key}")
            for key in [str(i) for i in range(1, len(fold_rows))]
        ]
        st.notes["frame_rows"] = int(len(frame))
        st.notes["activations"] = len(schedule)
        st.notes["report_level"] = report_level or "engine-default"
        run = _event_account_for(frame, initial, schedule, report_level=report_level)
        st.notes["equity_len"] = int(len(run.equity))
        # Two different counters, kept distinct on purpose: `engine_fill_count`
        # is the NATIVE audit-trail count (reads 0 under a reduced
        # report_level), `strategy_fill_count` is what the lab actually reports
        # and hands to selection. Recording only the first would make a
        # successful reduced-profile run look like it never traded.
        st.notes["engine_fill_count"] = int(run.engine_fill_count)
        st.notes["strategy_fill_count"] = len(getattr(run, "fills", None) or [])
        st.notes["status"] = run.status
        del run, initial, schedule


def stage_s4_d1_replay(results: dict, fold_rows: list[dict], frame: pd.DataFrame) -> None:
    """build_d1_for_arm's real per-fold path: fresh PreparedAccount +
    TrainingScorer over one real fold window (run_ra07_decay_deepdive.py)."""
    from crypto_regime_lab.time_edge.execution import PreparedAccount, TrainingScorer

    fold = fold_rows[0]
    with Stage("s4_d1_replay_fold0", results) as st:
        cutoff = pd.Timestamp(fold["test_start"])
        buffer_end = cutoff + pd.Timedelta(days=2)
        sliced = frame.loc[frame.index < buffer_end]
        st.notes["sliced_rows"] = int(len(sliced))
        st.notes["frame_rows"] = int(len(frame))
        prepared = PreparedAccount(sliced)
        train_start = pd.Timestamp(fold["train_start"])
        train_index = prepared.frame.index[(prepared.frame.index >= train_start)
                                           & (prepared.frame.index < cutoff)]
        scorer = TrainingScorer(prepared, "A-SC", train_start, cutoff,
                                LAB / ".cache" / "mem_audit" / "scorer_cache", "memaudit-local")
        scores = scorer(params=dict(fold["selected_params"]), index=train_index)
        st.notes["sharpe"] = scores.get("sharpe")
        st.notes["status"] = scores.get("status")
        del scorer, prepared, sliced, train_index, scores


def stage_s6_ratchet(results: dict, fold_rows: list[dict], repeats: int = 6,
                     report_level: str | None = None) -> None:
    """Repeat the scorer account call N times over the SAME real fold window,
    recording each call's own peak. Flat peaks => the per-call cost is pure
    transient churn; climbing peaks => per-call retention (the accumulation
    shape that matches the deep-dive's OOM profile)."""
    from crypto_regime_lab.integration.continuous_account import VersionWindow

    fold = fold_rows[0]
    frame, _ = load_real_bars("BTCUSDT", start=RA05_LOAD_START, end=RA05_WINDOW_END)
    frame = frame[["open", "high", "low", "close", "volume"]]
    frame.index = pd.DatetimeIndex(frame.index)
    train_start = pd.Timestamp(fold["train_start"])
    train_end = pd.Timestamp(fold["train_end"])
    base = frame.loc[(frame.index >= train_start) & (frame.index <= train_end)]
    initial = VersionWindow("A-SC-score", dict(fold["selected_params"]), 0, "score-initial")
    per_call = []
    for i in range(repeats):
        sampler = RssSampler()
        sampler.start()
        started = time.perf_counter()
        run = _event_account_for(base, initial, [], report_level=report_level)
        wall = round(time.perf_counter() - started, 2)
        sampler.stop()
        del run
        per_call.append({"call": i, "peak_mib": _mib(sampler.peak_kib), "wall_s": wall})
        time.sleep(0.2)
    results["s6_ratchet_probe"] = {"repeats": repeats, "window_rows": int(len(base)),
                                   "report_level": report_level or "engine-default",
                                   "per_call": per_call,
                                   "note": ("flat peaks => pure churn; "
                                            "climbing peaks => per-call retention")}


def stage_s7_report_level(results: dict, fold_rows: list[dict]) -> None:
    """Equity-parity + peak-memory probe for the engine's own report_level
    kwarg on the SAME real fold-0 account call: default (audit ledgers) vs
    'score' (compact profile). Run in its OWN process (--only s7) so the two
    peaks are comparable. Records max |equity diff|, exact-equality, and the
    strategy-level fill/decision counts (which must not depend on the level)."""
    from crypto_regime_lab.integration.continuous_account import VersionWindow

    fold = fold_rows[0]
    frame, _ = load_real_bars("BTCUSDT", start=RA05_LOAD_START, end=RA05_WINDOW_END)
    frame = frame[["open", "high", "low", "close", "volume"]]
    frame.index = pd.DatetimeIndex(frame.index)
    train_start = pd.Timestamp(fold["train_start"])
    train_end = pd.Timestamp(fold["train_end"])
    base = frame.loc[(frame.index >= train_start) & (frame.index <= train_end)]
    initial = VersionWindow("A-SC-score", dict(fold["selected_params"]), 0, "score-initial")

    runs = {}
    for level in ("default", "score"):
        sampler = RssSampler()
        sampler.start()
        started = time.perf_counter()
        run = _event_account_for(base, initial, [],
                                 **({} if level == "default"
                                    else {"report_level": level}))
        wall = round(time.perf_counter() - started, 2)
        sampler.stop()
        runs[level] = {"peak_mib": _mib(sampler.peak_kib), "wall_s": wall, "run": run}
        if level == "default":
            gc.collect()
            time.sleep(0.2)

    a, b = runs["default"]["run"], runs["score"]["run"]
    eq_a = np.asarray(a.equity, dtype=float)
    eq_b = np.asarray(b.equity, dtype=float)
    same_len = eq_a.shape == eq_b.shape
    if same_len and eq_a.size:
        diff = float(np.max(np.abs(eq_a - eq_b)))
        exact = bool(np.array_equal(eq_a, eq_b))
    else:
        diff, exact = None, False
    results["s7_report_level_parity"] = {
        "default_peak_mib": runs["default"]["peak_mib"],
        "score_peak_mib": runs["score"]["peak_mib"],
        "default_wall_s": runs["default"]["wall_s"],
        "score_wall_s": runs["score"]["wall_s"],
        "equity_len_default": int(eq_a.size), "equity_len_score": int(eq_b.size),
        "same_len": same_len, "max_abs_equity_diff": diff, "exact_equal": exact,
        "status_default": a.status, "status_score": b.status,
        "strategy_fills_default": len(a.fills), "strategy_fills_score": len(b.fills),
        "entries_default": int(a.entries), "entries_score": int(b.entries),
        "engine_fill_count_default": int(a.engine_fill_count),
        "engine_fill_count_score": int(b.engine_fill_count),
        "note": ("exact_equal + equal strategy-level counts => the compact "
                 "profile reproduces the default profile's account path here"),
    }



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="s1,s2,s3,s4,s5,s6,s7",
                        help="comma-separated stages to run (default: all)")
    parser.add_argument("--repeats", type=int, default=6,
                        help="s6 ratchet probe call count")
    parser.add_argument("--report-level", default=None,
                        help="report_level forwarded to the s3/s4/s6 engine calls")
    parser.add_argument("--rlimit-gib", type=float, default=None,
                        help=("cap this process's address space (RLIMIT_AS) so an "
                              "over-budget stage raises MemoryError that is RECORDED "
                              "instead of being SIGKILLed by the kernel -- makes the "
                              "OOM reproducible as a measurement"))
    parser.add_argument("--out", default=None, help="optional JSON output path")
    args = parser.parse_args()
    only = {part.strip() for part in args.only.split(",") if part.strip()}

    policy = SandboxPolicy.discover(LAB)
    results: dict = {}
    if args.rlimit_gib:
        import resource

        cap = int(args.rlimit_gib * (1 << 30))
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (cap, hard))
        results["rlimit"] = {"rlimit_as_gib": args.rlimit_gib,
                             "previous_soft": (None if soft == resource.RLIM_INFINITY
                                               else round(soft / (1 << 30), 2))}

    def _guarded(name, fn, *fn_args, **fn_kwargs):
        """A stage that blows its budget is recorded as a failed stage, not a
        crashed audit: an OOM here is a RESULT about the profile under test.

        Two exception classes are expected while --rlimit-gib is in force, both
        measured on this host rather than assumed:
        * MemoryError from a CPython-level allocation;
        * SystemError("error return without exception set") raised at the
          Rust/pyarrow boundary when a native allocation fails mid-call and the
          extension cannot set a Python exception -- observed on the 613k-bar
          deployment account under a 4 GiB cap with the DEFAULT profile.
        Anything else is a real defect and still crashes the audit.
        """
        started = time.perf_counter()
        try:
            fn(*fn_args, **fn_kwargs)
        except (MemoryError, SystemError) as exc:
            results[f"{name}__FAILED"] = {
                "error_type": type(exc).__name__,
                "error": f"{type(exc).__name__}: {exc}"[:200],
                "wall_s": round(time.perf_counter() - started, 2),
            }
            gc.collect()

    fold_rows = _ra05_fold_rows()
    frame = None
    if only & {"s3", "s4"}:
        frame, _parts = stage_s1_load(results, {"purpose": "s3/s4 host frame"})
    elif "s1" in only:
        stage_s1_load(results, {"purpose": "measurement"})

    report_level = args.report_level
    if "s2" in only:
        _guarded("s2_scorer_account_fold0", stage_s2_scorer_account, results, fold_rows)
    if "s3" in only and frame is not None:
        _guarded("s3_deployment_full_frame", stage_s3_deployment_account,
                 results, fold_rows, frame, report_level=report_level)
    if "s4" in only and frame is not None:
        _guarded("s4_d1_replay_fold0", stage_s4_d1_replay, results, fold_rows, frame)
    del frame
    gc.collect()
    if "s6" in only and "s2" not in only:
        _guarded("s6_ratchet_probe", stage_s6_ratchet, results, fold_rows,
                 repeats=max(1, args.repeats), report_level=report_level)
    if "s7" in only:
        _guarded("s7_report_level_parity", stage_s7_report_level, results, fold_rows)

    if "s5" in only and "s2" in only:
        # Isolation control: same s2 measurement in a fresh subprocess, so the
        # peak is not polluted by this process's earlier stages, and the gap
        # between the two s2 peaks shows what a reused process fails to return.
        out_path = Path(args.out) if args.out else (LAB / ".cache" / "mem_audit" / "s5.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--only", "s2",
               "--out", str(out_path)]
        started = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True, env=lab_worker_env(policy))
        results["s5_isolated_s2_control"] = {
            "returncode": proc.returncode,
            "wall_s": round(time.perf_counter() - started, 3),
            "peak_mib": None, "note": "peak read from subprocess JSON",
            "stdout_tail": proc.stdout.strip().splitlines()[-3:],
            "stderr_tail": proc.stderr.strip().splitlines()[-5:],
        }
        if proc.returncode == 0 and out_path.exists():
            child = json.loads(out_path.read_text()).get("stages", {})
            if "s2_scorer_account_fold0" in child:
                results["s5_isolated_s2_control"]["peak_mib"] = \
                    child["s2_scorer_account_fold0"]["peak_mib"]

    report = {"stages": results,
              "vmz": {"peak_policy": "background sampler, 20 ms tick"}}
    dest = Path(args.out) if args.out else (LAB / ".cache" / "mem_audit" /
                                            f"mem_audit-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2))

    print(f"{'stage':<28}{'base':>9}{'peak':>10}{'delta':>9}{'resid':>9}{'wall_s':>9}")
    for name, row in results.items():
        print(f"{name:<28}{row.get('base_mib', float('nan')):>9}"
              f"{row.get('peak_mib', float('nan')):>10}"
              f"{row.get('delta_mib', float('nan')):>9}"
              f"{row.get('residual_mib', float('nan')):>9}"
              f"{row.get('wall_s', float('nan')):>9}")
        extras = {k: v for k, v in row.items() if k not in
                  ("base_mib", "peak_mib", "delta_mib", "residual_mib", "wall_s")}
        if extras:
            print(f"{'':<28}{json.dumps(extras)[:110]}")
    print(f"written: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
