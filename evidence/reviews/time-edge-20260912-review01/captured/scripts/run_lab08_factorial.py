#!/usr/bin/env python
"""L08.2 / L08.3 — run the A/B/C/D factorial, arm E and the controls.

Arms A and B redeploy the selections LAB-04 already made at the frozen calendar
cutoffs. Arms C and D re-run the SAME selector pair at regime-triggered cutoffs,
which is the expensive half: a "full refresh" means the selector actually
searches again, and there is no way to get that from LAB-04's calendar folds.

Every arm is then delivered through LAB-07's continuous account, so what is
compared is what an account would have done rather than a sum of independently
evaluated folds.

    --cells N   run only the first N runnable cells (the L08.2 pilot)
    --stage     pilot | full
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data import panel as P  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.controls import (  # noqa: E402
    control_registry,
    delayed_states,
    dwell_profile,
    placebo_fidelity,
    placebo_states,
    risk_only_scaler,
)
from crypto_regime_lab.experiments.factorial import (  # noqa: E402
    ARMS,
    ArmResult,
    paired_daily_difference,
    run_arm,
)
from crypto_regime_lab.experiments.regime_schedule import (  # noqa: E402
    ScheduleError,
    assert_compute_matched,
    transition_cutoffs,
)
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
CONFIGS = LAB_ROOT / "configs"
DEV_START, DEV_END = "2021-01-01", "2023-12-31"


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def bars_for(alpha_id: str, symbol: str, protocol: dict, cache: dict,
             *, include_training_history: bool = False,
             window: tuple[str, str] = (DEV_START, DEV_END)) -> pd.DataFrame:
    """The account window, or that window plus the training memory before it.

    Two different frames, deliberately. The ACCOUNT runs over the development
    window only. A SELECTION at a cutoff needs the 180 days before that cutoff,
    and for the first cutoff those days sit before the account starts -- exactly
    as they do for the calendar arm, whose first fold trains from 2020-07-05.

    Handing the selector the account frame gave the dynamic arms 868 training
    bars where the calendar arm had 4,320, and a selector with a fifth of the
    history is not the same selector.
    """
    interval = protocol["timeframes"][alpha_id]["decision_bars"].replace("m", "min")
    key = (symbol, interval)
    if key not in cache:
        manifest = json.loads((LAB_ROOT / "snapshots" / SNAPSHOT_ID / "manifest.json").read_text())
        frame = P.load_resampled(LAB_ROOT / "snapshots" / SNAPSHOT_ID,
                                 "crypto_binance_futures_1m", symbol, interval,
                                 manifest=manifest)
        if frame["time"].dt.tz is None:
            frame["time"] = frame["time"].dt.tz_localize("UTC")
        cache[key] = frame.set_index("time").sort_index()
    frame = cache[key]
    window_start, window_end = window
    start = (pd.Timestamp(window_start, tz="UTC") - pd.Timedelta(days=CB.CALENDAR.train_days)
             if include_training_history else pd.Timestamp(window_start, tz="UTC"))
    return frame[(frame.index >= start)
                 & (frame.index <= f"{window_end} 23:59:59+00:00")]


def emissions_for(symbol: str, prefix: str | None = None) -> list[dict]:
    """The causal state tape this symbol's dynamic arms may read.

    ONLY the full tape. An earlier version fell back to whichever per-namespace
    evidence file happened to be last on disk, which for BTCUSDT covered just the
    final six months of a three-year window -- so arms C and D placed every
    refresh in that stretch while the calendar arms refreshed throughout. The
    fallback is gone: a missing full tape is a missing state provider, and the
    cell says so instead of running on a sixth of the window.
    """
    prefix = prefix or ("lab05" if symbol == "BTCUSDT" else f"lab08_{symbol.lower()}")
    full = load(f"{prefix}_full_emission_tape.json")
    if full is None or not full.get("emissions"):
        return []
    return full["emissions"]


def assert_tape_covers(symbol: str, emissions: list[dict], *, start: str, end: str) -> dict:
    """A dynamic arm may not refresh only where its tape happens to reach."""
    if not emissions:
        return {"symbol": symbol, "covers": False, "reason": "no full emission tape"}
    times = pd.to_datetime([e["available_at"] for e in emissions], utc=True)
    want_start, want_end = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    span_days = (times.max() - times.min()).days
    wanted_days = (want_end - want_start).days
    covers = times.min() <= want_start + pd.Timedelta(days=40) and times.max() >= want_end - pd.Timedelta(days=40)
    return {
        "symbol": symbol,
        "rows": int(len(emissions)),
        "tape_span": [str(times.min()), str(times.max())],
        "window": [start, end],
        "coverage_ratio": round(span_days / max(wanted_days, 1), 3),
        "covers": bool(covers),
        "rule": ("the state tape must span the arm's whole window. A tape covering only part of "
                 "it puts every dynamic refresh in that part, which is a coverage artefact and "
                 "not a timing result"),
    }


def calendar_selections(cell: dict, which_arm: str) -> list[dict]:
    """What LAB-04's selector chose at each frozen calendar cutoff."""
    out = []
    for fold in cell.get("folds", []):
        evidence = fold.get("cutoff_evidence")
        if not evidence:
            continue
        out.append({"cutoff": fold["cutoff"],
                    "params": (evidence.get(which_arm) or {}).get("params"),
                    "point_id": (evidence.get(which_arm) or {}).get("point_id"),
                    "source": "lab04_calendar"})
    return out


def selections_at_cutoffs(alpha_id: str, symbol: str, bars: pd.DataFrame, cutoffs: list[str],
                          *, progress=None, label: str = "regime_triggered") -> dict:
    """Run the SAME selector pair at a given list of cutoffs.

    Deliberately timing-agnostic. Arms C and D call it with regime-triggered
    cutoffs; a confirmation run with no prior calendar evidence calls it with
    calendar cutoffs for arms A and B. Using ONE function for both is what makes
    "the arms differ only in when they may refresh" checkable rather than
    asserted -- a second function for the calendar arms could drift apart from
    this one and nothing would catch it.
    """
    incumbents = {arm: dict(CB.SEED_POINTS[alpha_id]) for arm in CB.ARMS}
    per_arm: dict[str, list[dict]] = {arm: [] for arm in CB.ARMS}
    evidence = []
    for index, moment in enumerate(cutoffs):
        cutoff = pd.Timestamp(moment)
        train = bars[(bars.index >= cutoff - pd.Timedelta(days=CB.CALENDAR.train_days))
                     & (bars.index < cutoff)]
        if len(train) < CB.CALENDAR.inner_episodes * CB.MIN_BARS_PER_EPISODE:
            evidence.append({"cutoff": moment, "status": "INSUFFICIENT_BARS",
                             "train_bars": int(len(train))})
            continue
        if progress:
            progress(f"    {label} cutoff {index}: {moment[:10]} train={len(train)}")
        record = CB.run_cutoff(alpha_id, symbol, train, index, incumbents,
                               budget=CB.BUDGET, calendar=CB.CALENDAR, backend="reference")
        evidence.append({"cutoff": moment, "status": "OK", "train_bars": int(len(train)),
                         "cutoff_evidence": record})
        for arm in CB.ARMS:
            selection = record[f"arm_{arm}"]
            params = selection.get("params") or incumbents[arm]
            incumbents[arm] = dict(params)
            per_arm[arm].append({"cutoff": moment, "params": dict(params),
                                 "point_id": selection.get("point_id"),
                                 "retained": selection.get("params") is None,
                                 "source": label})
    return {"per_arm": per_arm, "evidence": evidence}


def run_cell(alpha_id: str, symbol: str, protocol: dict, baseline_cells: dict,
             cache: dict, *, progress=None,
             window: tuple[str, str] = (DEV_START, DEV_END),
             tape_prefix: str | None = None,
             calendar_cutoffs: list[str] | None = None) -> dict:
    """One cell of the factorial.

    `window` is the account's interval. `calendar_cutoffs` is None for the
    development run, where arms A and B redeploy the selections LAB-04 already
    made; a confirmation run on an interval LAB-04 never saw passes the frozen
    calendar's cutoffs instead, and the same selector that serves arms C and D
    produces them. `tape_prefix` names the state provider for that interval.
    """
    started = time.perf_counter()
    window_start, window_end = window
    bars = bars_for(alpha_id, symbol, protocol, cache, window=window)
    # the selector's frame reaches back one training memory before the account
    training_bars = bars_for(alpha_id, symbol, protocol, cache,
                             include_training_history=True, window=window)
    cell = baseline_cells.get((alpha_id, symbol))
    results: dict[str, ArmResult] = {}
    notes: dict = {}

    if cell is None or cell.get("status") != "RUN":
        reason = (cell or {}).get("reason", "no LAB-04 evidence for this cell")
        for arm in ARMS:
            results[arm] = ArmResult(arm, alpha_id, symbol, "NOT_READY",
                                     detail={"reason": reason})
        return {"alpha_id": alpha_id, "symbol": symbol, "status": "NOT_READY",
                "reason": reason,
                "arms": {a: r.as_record() for a, r in results.items()},
                "wall_seconds": time.perf_counter() - started}

    # ---- arms A and B: the frozen calendar
    if calendar_cutoffs is None:
        # development: LAB-04 already ran this selector at these cutoffs
        calendar_per_arm = {which: calendar_selections(cell, f"arm_{which}")
                            for which in CB.ARMS}
        notes["calendar_selection_source"] = "lab04_calendar_baseline.json"
    else:
        # confirmation: LAB-04 never saw this interval, so the selector runs here
        calendar = selections_at_cutoffs(alpha_id, symbol, training_bars,
                                         list(calendar_cutoffs), progress=progress,
                                         label="calendar")
        calendar_per_arm = calendar["per_arm"]
        notes["calendar_cutoff_evidence"] = calendar["evidence"]
        notes["calendar_selection_source"] = (
            "recomputed by selections_at_cutoffs at the frozen calendar cutoffs -- the SAME "
            "function that serves arms C and D, so the only difference between the calendar "
            "arms and the dynamic arms is the cutoff list")
    for arm, which in (("A", "A"), ("B", "B")):
        results[arm] = run_arm(arm, alpha_id, symbol, bars, calendar_per_arm[which])
    # the deployed schedule per arm, recorded so a later stress can replay the SAME
    # decisions under different economics without re-running the selector -- and so
    # a reader can see what each arm actually deployed rather than infer it
    notes["deployed_selections"] = {"A": calendar_per_arm["A"], "B": calendar_per_arm["B"]}

    # ---- arms C and D: the same selectors at regime-triggered cutoffs
    emissions = emissions_for(symbol, tape_prefix)
    coverage = assert_tape_covers(symbol, emissions, start=window_start, end=window_end)
    notes["state_tape_coverage"] = coverage
    if not emissions or not coverage["covers"]:
        for arm in ("C", "D", "E"):
            results[arm] = ArmResult(arm, alpha_id, symbol, "NO_STATE_PROVIDER",
                                     detail={"reason": coverage.get("reason")
                                             or f"the state tape for {symbol} does not span the "
                                                "arm's window, so its refreshes would all land "
                                                "where the tape reaches",
                                             "coverage": coverage})
        notes["state_provider"] = "MISSING_OR_PARTIAL"
    else:
        try:
            schedule = transition_cutoffs(
                emissions, count=CB.CALENDAR.folds,
                earliest=f"{window_start} 00:00:00+00:00",
                latest=f"{window_end} 00:00:00+00:00")
        except ScheduleError as exc:
            # no padding: a dynamic arm the states cannot support is absent, not
            # quietly replaced by an evenly spaced calendar
            for arm in ("C", "D", "E"):
                results[arm] = ArmResult(arm, alpha_id, symbol, "TOO_FEW_TRANSITIONS",
                                         detail={"reason": str(exc)})
            notes["state_provider"] = "TOO_FEW_TRANSITIONS"
        else:
            notes["regime_schedule"] = schedule.as_record()
            notes["compute_match"] = assert_compute_matched(CB.CALENDAR, schedule)
            if progress:
                progress(f"  {alpha_id}/{symbol}: {schedule.folds} regime cutoffs "
                         f"{[c[:10] for c in schedule.cutoffs]}")
            dynamic = selections_at_cutoffs(alpha_id, symbol, training_bars,
                                            list(schedule.cutoffs), progress=progress)
            notes["regime_cutoff_evidence"] = dynamic["evidence"]
            for arm, which in (("C", "A"), ("D", "B")):
                results[arm] = run_arm(arm, alpha_id, symbol, bars, dynamic["per_arm"][which])
                notes["deployed_selections"][arm] = dynamic["per_arm"][which]
            notes["deployed_selections"]["E"] = dynamic["per_arm"]["B"]
            # arm E extends D with the bank/response policy; without a switch the
            # policy deploys D's schedule, which is reported rather than hidden
            results["E"] = run_arm("E", alpha_id, symbol, bars, dynamic["per_arm"]["B"])
            results["E"].detail["policy_note"] = (
                "LAB-06 measured ZERO switches for this policy on the registered thresholds, so E "
                "deploys D's schedule and its own contribution is null by construction here. "
                "That is reported, not hidden: E is an extension and never a substitute for C "
                "or D")

    record = {
        "alpha_id": alpha_id, "symbol": symbol, "status": "RUN",
        "window": [window_start, window_end],
        "bars": int(len(bars)),
        "decision_bars": protocol["timeframes"][alpha_id]["decision_bars"],
        "arms": {arm: results[arm].as_record() for arm in ARMS},
        "contrasts": {},
        "notes": notes,
        "wall_seconds": time.perf_counter() - started,
    }
    for left, right in (("B", "A"), ("C", "A"), ("D", "B"), ("D", "C")):
        record["contrasts"][f"{left}-{right}"] = paired_daily_difference(
            results[left], results[right])
    # The DAILY series, not just its mean. L09.3 needs a block bootstrap over the
    # paired differences, and a bootstrap cannot be built from a summary statistic:
    # recovering it would mean re-running every arm. Stored as one date axis plus
    # one value array per arm, which is the same information at a fifth of the size.
    daily = {arm: results[arm].daily_returns() for arm in ARMS
             if results[arm].status == "RUN"}
    if daily:
        axis = sorted(set().union(*(set(series.index) for series in daily.values())))
        record["daily_returns"] = {
            "dates": [str(stamp.date()) for stamp in axis],
            "by_arm": {arm: [None if pd.isna(v) else float(v)
                             for v in series.reindex(axis).to_numpy()]
                       for arm, series in daily.items()},
            "note": ("per-arm daily net returns on the account's own calendar. A value is null "
                     "where that arm had no observation that day, so a paired difference can "
                     "exclude the day rather than treat the gap as a zero"),
        }
    dc = record["contrasts"]["D-C"]
    ba = record["contrasts"]["B-A"]
    record["contrasts"]["(D-C)-(B-A)"] = {
        "contrast": "(D-C)-(B-A)",
        "status": "OK" if dc["mean_daily_difference"] is not None
                  and ba["mean_daily_difference"] is not None else "INCOMPARABLE",
        "value": (dc["mean_daily_difference"] - ba["mean_daily_difference"]
                  if dc["mean_daily_difference"] is not None
                  and ba["mean_daily_difference"] is not None else None),
        "reading": "the interaction: does regime timing add MORE to the new selector than to the old",
    }
    record["controls"] = run_controls(alpha_id, symbol, bars, results, emissions, protocol,
                                      baseline_selections=calendar_per_arm["A"])
    return record


def run_controls(alpha_id: str, symbol: str, bars: pd.DataFrame,
                 results: dict, emissions: list[dict], protocol: dict,
                 baseline_selections: list[dict] | None = None) -> dict:
    """The staged controls for this cell (guide 10.2)."""
    out: dict = {"registry": control_registry()}
    baseline = results.get("A")
    if baseline is None or baseline.status != "RUN" or not emissions \
            or not baseline_selections:
        out["status"] = "NOT_RUN"
        out["reason"] = "the baseline arm or the state tape is unavailable for this cell"
        return out

    states = [(e["state_namespace"], e["state_id"]) for e in emissions]
    times = pd.DatetimeIndex([pd.Timestamp(e["available_at"]) for e in emissions])
    if times.tz is None:
        times = times.tz_localize("UTC")

    equity = pd.Series(baseline.equity, index=baseline.index)
    daily = equity.resample("1D").last().dropna()
    returns = daily.pct_change().dropna()

    aligned = pd.Series(pd.Categorical([str(s) for s in states]).codes,
                        index=times).reindex(returns.index, method="ffill").ffill()
    # RISK_ONLY needs a per-state scale FITTED on one window and APPLIED on a
    # later one. That requires the state identity to survive a refit, and on
    # this provider it does not: 40 namespaces x K=3 gives 96 distinct
    # (namespace, state) keys, and LAB-05 declares cross-namespace translation
    # DIAGNOSTIC ONLY -- not decision-eligible.
    #
    # Measured below rather than assumed. When almost nothing transfers, every
    # unseen state falls back to a scale of 1.0 and the control silently becomes
    # "the baseline again" while still printing a number. That is reported as
    # BLOCKED, because guide 10.2 forbids dropping a control and a vacuous
    # control is worse than a named one.
    calibration_end = returns.index[0] + pd.Timedelta(days=CB.CALENDAR.test_days)
    train_mask = returns.index < calibration_end
    calibrated_keys = set(aligned[train_mask].dropna().astype(int))
    scoring = aligned[~train_mask].dropna().astype(int)
    transfer = float(scoring.isin(calibrated_keys).mean()) if len(scoring) else 0.0

    if transfer < 0.5:
        out["RISK_ONLY"] = {
            "control": "RISK_ONLY",
            "status": "BLOCKED_BY_STATE_NAMESPACING",
            "isolates": "exposure timing, with parameters unchanged",
            "calibration_window_days": CB.CALENDAR.test_days,
            "distinct_state_keys": int(len(set(aligned.dropna().astype(int)))),
            "state_keys_seen_in_calibration": int(len(calibrated_keys)),
            "share_of_scoring_states_seen_in_calibration": transfer,
            "why_blocked": (
                "a per-state risk scale must be fitted on one window and applied on a later one. "
                f"Only {transfer:.2%} of scoring observations carry a state key that appeared "
                "during calibration, because the model refits every 28 days and LAB-05 declares "
                "cross-namespace state translation DIAGNOSTIC ONLY, not decision-eligible. The "
                "remaining states would fall back to a scale of 1.0, so the control would return "
                "the baseline path while still printing a number"),
            "what_would_unblock_it": (
                "a state vocabulary that is decision-eligible across refits, or a refit cadence "
                "slow enough that a namespace covers both a calibration and a scoring window"),
            "not_dropped": ("guide 10.2 forbids removing a control. It is reported BLOCKED with "
                            "the measurement, never as a scale of 1.0 that looks like a result"),
        }
    else:
        scale_by_day = risk_only_scaler(
            list(aligned.fillna(-1).astype(int)),
            train_states=list(aligned[train_mask].fillna(-1).astype(int)),
            train_returns=list(returns[train_mask]))
        scale_by_day = [1.0 if train else value
                        for train, value in zip(train_mask, scale_by_day)]
        per_bar = pd.Series(scale_by_day, index=returns.index).reindex(
            baseline.index, method="ffill").ffill().fillna(1.0)
        risk_only = run_arm("A", alpha_id, symbol, bars, baseline_selections,
                            size_scale=list(per_bar.to_numpy()))
        out["RISK_ONLY"] = {
            **risk_only.as_record(),
            "control": "RISK_ONLY",
            "isolates": "exposure timing, with parameters unchanged",
            "mean_size_scale": float(np.mean(scale_by_day)),
            "share_of_scoring_states_seen_in_calibration": transfer,
            "calibration_window_days": CB.CALENDAR.test_days,
            "baseline_net_return": baseline.as_record()["net_return"],
            "note": ("arm A's own selections, resized by a scale calibrated on TRAINING "
                     "observations of each state and clipped to [0.5, 1.0]. If this reproduces a "
                     "dynamic arm's advantage, the advantage was exposure and not selection"),
        }

    profile = dwell_profile(states)
    fake = placebo_states(profile, length=len(states),
                          seed=protocol["seeds"]["placebo"])
    out["STATE_PLACEBO"] = {
        "status": "GENERATED",
        "fidelity": placebo_fidelity(states, fake),
        "generated_from": "development-window dwell statistics only; no future label is shuffled in",
    }
    delayed = delayed_states(emissions, observations=1)
    out["DELAYED_STATE"] = {
        "status": "GENERATED",
        "observations_of_delay": 1,
        "changed_availability_only": all(d["delay_is_on_availability_not_on_the_world"]
                                         for d in delayed),
        "states_that_differ_after_delay": sum(
            1 for a, b in zip(emissions, delayed) if a["state_id"] != b["state_id"]),
    }
    out["CALENDAR_MATCHED"] = {
        "status": "SATISFIED_BY_CONSTRUCTION",
        "reason": ("the dynamic arms were given exactly the calendar's refresh count and training "
                   "memory, so the calendar is already compute-matched to them. There is no "
                   "separate run because there is no compute difference to control for"),
        "evidence": "notes.compute_match",
    }
    out["BANK_CALENDAR"] = {
        "status": "DEGENERATE_HERE",
        "reason": ("LAB-06 measured zero switches on the registered thresholds, so a bank that "
                   "switches on the calendar and a bank that switches on regime deploy the same "
                   "sequence. The control is retained and reported as degenerate rather than "
                   "dropped (guide 10.2)"),
    }
    out["EXPOST_DIAGNOSTIC"] = {
        "status": "DIAGNOSTIC_ONLY",
        "eligible_for_a_trade_result": False,
        "reason": "computed from returns that had not happened at decision time",
    }
    out["USER_PRESET_REFERENCE"] = {
        "status": "RETROSPECTIVE_ONLY",
        "preset_role": protocol.get("preset_role"),
        "eligible_as_a_core_outcome": False,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=int, default=None,
                        help="run only the first N runnable cells")
    parser.add_argument("--stage", choices=("pilot", "full"), default="full")
    args = parser.parse_args(argv)

    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    protocol = load("lab08_pilot_protocol.json")
    if protocol is None:
        print("BLOCKED: run scripts/freeze_lab08_protocol.py first (L08.1)")
        return 1
    baseline = load("lab04_calendar_baseline.json")
    baseline_cells = {(c["alpha_id"], c["symbol"]): c for c in baseline["cells"]}

    planned = protocol["primary_matrix"]["cells"]
    runnable = [c for c in planned if c["runnable"]]
    if args.cells:
        runnable = runnable[:args.cells]

    # Per-cell checkpoints. A crash at cell 10 destroyed nine cells of work --
    # about two hours -- because the run held everything in memory until the end.
    # A completed cell is written immediately and reused on the next attempt.
    checkpoints = LAB_ROOT / ".cache" / f"lab08_cells_{args.stage}"
    checkpoints.mkdir(parents=True, exist_ok=True)

    cache: dict = {}
    records = []
    started = time.perf_counter()
    for entry in planned:
        key = (entry["alpha_id"], entry["symbol"])
        if entry not in runnable and entry["runnable"]:
            records.append({"alpha_id": key[0], "symbol": key[1], "status": "NOT_RUN_THIS_STAGE",
                            "reason": f"stage={args.stage} covered {len(runnable)} cells",
                            "arms": {a: {"arm": a, "status": "NOT_RUN_THIS_STAGE",
                                         "net_return": None} for a in ARMS}})
            continue
        if not entry["runnable"]:
            records.append({"alpha_id": key[0], "symbol": key[1], "status": "NOT_READY",
                            "reason": entry["blocker"],
                            "arms": {a: {"arm": a, "status": "NOT_READY", "net_return": None,
                                         "note": "null metrics, never a PnL of 0"}
                                     for a in ARMS}})
            continue
        checkpoint = checkpoints / f"{key[0]}_{key[1]}.json"
        if checkpoint.is_file():
            print(f"  {key[0]}/{key[1]} (checkpoint)", flush=True)
            records.append(json.loads(checkpoint.read_text()))
            continue
        print(f"  {key[0]}/{key[1]} ...", flush=True)
        record = run_cell(key[0], key[1], protocol, baseline_cells, cache,
                          progress=lambda m: print(m, flush=True))
        checkpoint.write_text(json.dumps(record, indent=2, default=str))
        records.append(record)

    document = {
        "schema": "crypto_regime_lab.lab08_factorial.v1",
        "stage": args.stage,
        "is_a_result": args.stage == "full",
        "stage_note": ("a pilot is for debugging the harness and is never reported as a result "
                       "(guide L08.2)"),
        "generated_at_utc": utc_now_iso(),
        "protocol_frozen_at_utc": protocol["frozen_at_utc"],
        "cells_planned": len(planned),
        "cells_run": sum(1 for r in records if r["status"] == "RUN"),
        "cells_not_ready": sum(1 for r in records if r["status"] == "NOT_READY"),
        "cells_not_run_this_stage": sum(1 for r in records
                                        if r["status"] == "NOT_RUN_THIS_STAGE"),
        "arms": protocol["arms"],
        "registered_contrasts": protocol["registered_contrasts"],
        "cells": records,
        "wall_seconds": time.perf_counter() - started,
        "checkpointed": True,
        "checkpoint_note": ("each cell is written as it completes and reused on a later attempt, "
                            "so a crash costs one cell rather than the whole run"),
    }
    name = f"lab08_factorial_{args.stage}.json"
    with writer.attempt(f"L08.2.factorial_{args.stage}") as att:
        att.detail = {"cells_run": document["cells_run"]}
    writer.write_config(name, document)
    writer.write_json(name, document, schema=document["schema"])

    print(f"\nstage {args.stage}: {document['cells_run']} run, "
          f"{document['cells_not_ready']} NOT_READY, "
          f"{document['cells_not_run_this_stage']} not in this stage")
    for record in records:
        if record["status"] != "RUN":
            continue
        arms = record["arms"]
        line = "  ".join(
            f"{a}={arms[a]['net_return']:+.2%}" if arms[a].get("net_return") is not None
            else f"{a}={arms[a]['status'][:9]}" for a in ARMS)
        print(f"  {record['alpha_id']:<7} {record['symbol']:<9} {line}")
    print(f"wall: {document['wall_seconds']:.0f}s")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
