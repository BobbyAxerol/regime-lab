#!/usr/bin/env python
"""L09.4 — cost and information stress on the frozen confirmation run.

Two panels.

ECONOMIC: every arm of every cell is re-run through the engine at 1.0x, 1.5x and
2.0x the configured transaction costs -- the multipliers registered in
`minimum_economic_effect.json` before any arm existed. The 1.0x level is not
redundant: it must reproduce the confirmation run's equity exactly, and it is the
only check that the stress harness is wired to the same account as the run it
claims to stress. A harness that quietly ran a different account would produce a
perfectly plausible panel.

INFORMATION: the state tape the dynamic arms read is corrupted three ways --
transitions dated wrong, a feed that freezes and catches up, an enrichment
product that goes missing -- and arm D is re-run on each resulting schedule. A
fourth, the label permutation, is a control in the opposite direction: it must
change NOTHING, because a refresh schedule reads where the state changes and not
what it is called.

Nothing is retuned in response to any of it (L09.4.6).
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
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.evaluator import ACCOUNT  # noqa: E402
from crypto_regime_lab.experiments.factorial import ARMS, run_arm  # noqa: E402
from crypto_regime_lab.experiments.regime_schedule import (ScheduleError,  # noqa: E402
                                                           transition_cutoffs)
from crypto_regime_lab.experiments.stress import (StressError,  # noqa: E402
                                                  label_permutation,
                                                  missing_enrichment,
                                                  mislabelled_transitions,
                                                  scaled_costs, stale_feed)
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from run_lab08_factorial import bars_for, emissions_for, selections_at_cutoffs  # noqa: E402
from run_lab09_confirmation import CONF_END, CONF_START  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
#: the seeds are fixed HERE, before the stress runs, for the same reason every
#: other seed in this study is fixed in advance
SEEDS = {"mislabelled": 20260912, "stale": 20260913, "missing": 20260914,
         "permutation": 20260915}
#: how hard each information stress is. Registered here and not tuned afterwards.
MISLABEL_FRACTION, MISLABEL_SHIFT = 0.5, 6      # 6 observations of 4h = one day
STALE_RUNS, STALE_OBSERVATIONS = 6, 42          # six one-week freezes
#: contiguous outages, not scattered dropouts: a random 20% drop left the refresh
#: schedule identical on every cutoff, so the stress could not have produced a
#: different answer. Six one-week outages can cover a transition.
MISSING_OUTAGES, MISSING_OBSERVATIONS = 6, 42


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def cost_levels(multipliers: list[float]) -> list[tuple[str, float, float]]:
    """(name, fee multiplier, slippage multiplier) for every level in the panel.

    The registered 1x / 1.5x / 2x grid, plus AS_DECLARED. AS_DECLARED is not a
    stress: it is the account the study REGISTERED at LAB-01. The lab passes the
    registered one-way taker rate into an engine parameter documented as
    round-trip, so every account in every phase has been charged half that fee
    (measured in configs/cost_binding_verification.json). Doubling the fee, and
    ONLY the fee, restores the registered economics -- the slippage binding was
    measured correct at 1 bp per side and is left alone.
    """
    levels = [(f"{m:g}x", m, m) for m in multipliers]
    levels.append(("AS_DECLARED", 2.0, 1.0))
    return levels


def cost_panel(cell: dict, protocol: dict, cache: dict, levels: list[tuple[str, float, float]],
               *, progress=None) -> dict:
    """Every arm of one cell, re-run at each cost level."""
    alpha_id, symbol = cell["alpha_id"], cell["symbol"]
    bars = bars_for(alpha_id, symbol, protocol, cache, window=(CONF_START, CONF_END))
    selections = (cell.get("notes") or {}).get("deployed_selections") or {}
    out: dict = {"alpha_id": alpha_id, "symbol": symbol, "arms": {}}
    for arm in ARMS:
        recorded = (cell.get("arms") or {}).get(arm) or {}
        if recorded.get("status") != "RUN" or arm not in selections:
            out["arms"][arm] = {"status": recorded.get("status", "MISSING"),
                                "reason": "the confirmation run produced no account for this arm"}
            continue
        measured = {}
        for name, fee_scale, slip_scale in levels:
            with scaled_costs(1.0, fee_multiplier=fee_scale,
                              slippage_multiplier=slip_scale) as economics:
                result = run_arm(arm, alpha_id, symbol, bars, selections[arm])
            record = result.as_record()
            measured[name] = {
                "net_return": record["net_return"],
                "daily_sharpe": record["daily_sharpe"],
                "max_drawdown": record["max_drawdown"],
                "trades": record["trades"],
                "taker_fee_rate": economics["taker_fee_rate"],
                "slippage_bps": economics["slippage_bps"],
                "fee_multiplier": fee_scale,
                "slippage_multiplier": slip_scale,
            }
            if progress:
                progress(f"    {arm} {name:<11} net={record['net_return']:+.4%}")
        levels_out, baseline = measured, measured[levels[0][0]]
        reproduces = (baseline["net_return"] is not None
                      and recorded.get("net_return") is not None
                      and abs(baseline["net_return"] - recorded["net_return"]) < 1e-12)
        out["arms"][arm] = {
            "status": "RUN",
            "levels": levels_out,
            "recorded_net_return": recorded.get("net_return"),
            "one_x_reproduces_the_confirmation_run": bool(reproduces),
            "reproduction_gap": (None if baseline["net_return"] is None
                                 or recorded.get("net_return") is None
                                 else baseline["net_return"] - recorded["net_return"]),
            "survives_2x": (levels_out.get("2x", {}).get("net_return") is not None
                            and levels_out["2x"]["net_return"] > 0),
            "as_declared_net_return": levels_out.get("AS_DECLARED", {}).get("net_return"),
            "cost_of_the_binding_defect": (
                None if levels_out.get("AS_DECLARED", {}).get("net_return") is None
                or baseline["net_return"] is None
                else levels_out["AS_DECLARED"]["net_return"] - baseline["net_return"]),
        }
    return out


def information_panel(cell: dict, protocol: dict, cache: dict, *, progress=None) -> dict:
    """Arm D re-run on three corrupted tapes, plus the label-permutation control."""
    alpha_id, symbol = cell["alpha_id"], cell["symbol"]
    bars = bars_for(alpha_id, symbol, protocol, cache, window=(CONF_START, CONF_END))
    training = bars_for(alpha_id, symbol, protocol, cache, include_training_history=True,
                        window=(CONF_START, CONF_END))
    emissions = emissions_for(symbol, f"lab09_{symbol.lower()}")
    real = (cell.get("arms") or {}).get("D") or {}
    # keep the FULL ISO string, offset included. Truncating to 19 characters drops
    # the `+00:00`, which makes pd.Timestamp return a NAIVE stamp, and comparing a
    # naive stamp against the tz-aware bar index raises TypeError on the first
    # cutoff. Formatting for display happens at the print, not in the data.
    real_cutoffs = list(((cell.get("notes") or {}).get("regime_schedule") or {})
                        .get("cutoffs", []))
    out: dict = {"alpha_id": alpha_id, "symbol": symbol,
                 "arm_D_net_return": real.get("net_return"),
                 "arm_D_cutoffs": real_cutoffs, "stresses": {}}

    recipes = [
        ("MISLABELLED_TRANSITIONS",
         lambda: mislabelled_transitions(emissions, fraction=MISLABEL_FRACTION,
                                         shift=MISLABEL_SHIFT, seed=SEEDS["mislabelled"])),
        ("STALE_FEED",
         lambda: stale_feed(emissions, stale_runs=STALE_RUNS,
                            run_observations=STALE_OBSERVATIONS, seed=SEEDS["stale"])),
        ("MISSING_ENRICHMENT",
         lambda: missing_enrichment(emissions, outages=MISSING_OUTAGES,
                                    outage_observations=MISSING_OBSERVATIONS,
                                    seed=SEEDS["missing"])),
        ("LABEL_PERMUTATION",
         lambda: label_permutation(emissions, seed=SEEDS["permutation"])),
    ]
    for name, build in recipes:
        try:
            tape, fidelity = build()
        except StressError as exc:
            out["stresses"][name] = {"status": "NOT_APPLICABLE", "reason": str(exc)}
            continue
        try:
            schedule = transition_cutoffs(
                tape, count=CB.CALENDAR.folds,
                earliest=f"{CONF_START} 00:00:00+00:00",
                latest=f"{CONF_END} 00:00:00+00:00")
        except ScheduleError as exc:
            out["stresses"][name] = {"status": "NO_SCHEDULE", "reason": str(exc),
                                     "fidelity": fidelity,
                                     "reading": ("the corrupted tape cannot support the refresh "
                                                 "count the arm needs. That is a result: the arm "
                                                 "is absent under this stress, not padded")}
            continue
        cutoffs = list(schedule.cutoffs)
        if progress:
            progress(f"    {name}: {[c[:10] for c in cutoffs]}")
        if name == "LABEL_PERMUTATION":
            # the control: identical schedule means nothing downstream reads the label
            out["stresses"][name] = {
                "status": "CONTROL",
                "fidelity": fidelity,
                "cutoffs": cutoffs,
                "schedule_identical_to_arm_D": cutoffs == real_cutoffs,
                "expected": True,
                "reading": ("a jump model's state ids are arbitrary. A refresh schedule built "
                            "from WHERE the state changes must be unchanged by a permutation of "
                            "the labels; a difference would mean a decision reads the label"),
            }
            continue
        arm = run_arm("D", alpha_id, symbol, bars, selections_at_cutoffs(
            alpha_id, symbol, training, cutoffs, label=name.lower())["per_arm"]["B"])
        record = arm.as_record()
        out["stresses"][name] = {
            "status": "RUN",
            "arm_mirrored": "D",
            "fidelity": fidelity,
            "cutoffs": cutoffs,
            "cutoffs_moved_vs_arm_D": sum(1 for a, b in zip(cutoffs, real_cutoffs) if a != b),
            "net_return": record["net_return"],
            "difference_vs_arm_D": (None if record["net_return"] is None
                                    or real.get("net_return") is None
                                    else record["net_return"] - real["net_return"]),
            "trades": record["trades"],
        }
    return out


def refit_latency_panel(protocol: dict) -> dict:
    """L09.4.2 — no zero-latency model refit is used as a default.

    The clause is about a DEFAULT, so the answer cannot be "we measured it once
    in another phase". LAB-07 measured the cost of a fit; what this phase has to
    say is how many DECISION BARS that cost is, on its own timeframes, and that
    the number was measured rather than assumed to be zero.

    Rounding to zero bars is an honest outcome for a 1.46-second fit against a
    15-minute bar. It is only a defect if it is ASSUMED, which is why the
    measured seconds and the arithmetic are both here.
    """
    trace = load("lab07_continuous_trace.json") or {}
    jobs = trace.get("training_jobs") or {}
    seconds = jobs.get("max_delay_seconds")
    per_alpha = {}
    for alpha_id, frames in (protocol.get("timeframes") or {}).items():
        bar = frames["decision_bars"]
        bar_seconds = pd.Timedelta(bar.replace("m", "min")).total_seconds()
        per_alpha[alpha_id] = {
            "decision_bars": bar,
            "bar_seconds": bar_seconds,
            "refit_latency_in_bars": (None if seconds is None
                                      else seconds / bar_seconds),
            "rounds_to_bars": (None if seconds is None
                               else int(seconds // bar_seconds)),
        }
    return {
        "measured_seconds_per_fit": seconds,
        "source": (jobs.get("benchmark") or {}).get("source"),
        "zero_latency_jobs": jobs.get("zero_latency_jobs"),
        "per_alpha": per_alpha,
        "rounds_to_zero_bars_on_every_alpha": all(
            v["rounds_to_bars"] == 0 for v in per_alpha.values()
            if v["rounds_to_bars"] is not None),
        "why_that_is_not_a_free_option": (
            "a fit that costs less than one decision bar still cannot be taken as free: the "
            "ACTIVATION delay is separate and is paid in bars, and the arms pay it. Guide L07.3 "
            "forbids taking a refit latency of zero in order to fill earlier, and the difference "
            "between measuring zero and assuming zero is the whole clause"),
        "activation_delays_are_reported_separately": (
            "configs/lab09_confirmation_results.json cells[].arms[].switch_delays"),
    }


def stress_bite(information: list[dict]) -> dict:
    """Did each stress change anything, and on how many cells?

    A stress that moves no cutoff produces the same refresh schedule, so the arm
    is re-run to the same number and the cell contributes NO evidence about that
    stress. "No difference" then means "the stress did not fire here", not "the
    arm is robust to it" -- and those read identically in a difference column.

    COR-19 was the universal version of this: a stress that could not have
    produced a different answer on any cell. This is the per-cell version, and it
    is reported rather than averaged away.
    """
    out: dict = {}
    for name in ("MISLABELLED_TRANSITIONS", "STALE_FEED", "MISSING_ENRICHMENT"):
        rows = [entry["stresses"].get(name, {}) for entry in information]
        ran = [r for r in rows if r.get("status") == "RUN"]
        moved = [r for r in ran if (r.get("cutoffs_moved_vs_arm_D") or 0) > 0]
        changed = [r for r in ran if r.get("difference_vs_arm_D") not in (None, 0.0)]
        out[name] = {
            "cells_run": len(ran),
            "cells_where_the_schedule_moved": len(moved),
            "cells_where_the_RESULT_moved": len(changed),
            "bit_somewhere": bool(moved),
            "vacuous_on": [entry["alpha_id"] + "/" + entry["symbol"]
                           for entry, row in zip(information, rows)
                           if row.get("status") == "RUN"
                           and not (row.get("cutoffs_moved_vs_arm_D") or 0)],
            "reading": ("a cell whose schedule did not move contributes no evidence about this "
                        "stress: the arm was re-run to the same number because it deployed the "
                        "same parameters at the same times"),
        }
    control = [entry["stresses"].get("LABEL_PERMUTATION", {}) for entry in information]
    out["LABEL_PERMUTATION"] = {
        "is_a_control_that_must_change_nothing": True,
        "cells_checked": sum(1 for c in control if c.get("status") == "CONTROL"),
        "schedules_identical": sum(1 for c in control
                                   if c.get("schedule_identical_to_arm_D")),
        "holds_everywhere": all(c.get("schedule_identical_to_arm_D")
                                for c in control if c.get("status") == "CONTROL"),
        "reading": ("the only one of the four that is SUPPOSED to change nothing. If it ever "
                    "moved a cutoff, something downstream would be reading a state id as though "
                    "the integer meant something"),
    }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--information-cells", type=int, default=3,
                        help="how many cells the staged information stress covers, in order")
    parser.add_argument("--shard", default=None, metavar="K/N",
                        help="compute only the cells whose index mod N equals K, and write their "
                             "checkpoints. Cells are independent and deterministic, so a shard "
                             "decides which process computes a cell and never what it computes. "
                             "A shard never writes the stress document; a final unsharded pass "
                             "assembles it from every checkpoint.")
    args = parser.parse_args(argv)
    shard = None
    if args.shard:
        k, _, n = args.shard.partition("/")
        shard = (int(k), int(n))
        if not 0 <= shard[0] < shard[1]:
            print(f"BLOCKED: --shard K/N needs 0 <= K < N, got {args.shard}")
            return 1

    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    confirmation = load("lab09_confirmation_results.json")
    if confirmation is None:
        print("BLOCKED: run scripts/run_lab09_confirmation.py first (L09.2)")
        return 1
    protocol = load("lab08_pilot_protocol.json")
    effect = load("minimum_economic_effect.json")
    multipliers = [float(m) for m in effect["derivation"]["cost_stress_multipliers"]]
    if multipliers[0] != 1.0:
        print(f"BLOCKED: the registered multipliers must start at 1.0, got {multipliers}")
        return 1

    levels = cost_levels(multipliers)
    run_cells = [c for c in confirmation["cells"] if c["status"] == "RUN"]
    cache: dict = {}
    started = time.perf_counter()

    # Per-cell checkpoints, for the same reason the confirmation has them: a crash
    # or a kill costs one cell rather than the whole panel, and they are what makes
    # sharding safe -- a shard writes checkpoints and nothing else.
    cost_dir = LAB_ROOT / ".cache" / "lab09_stress_cost"
    info_dir = LAB_ROOT / ".cache" / "lab09_stress_info"
    cost_dir.mkdir(parents=True, exist_ok=True)
    info_dir.mkdir(parents=True, exist_ok=True)

    def collect(cells, directory, label, compute):
        out = []
        for index, cell in enumerate(cells):
            name = f"{cell['alpha_id']}_{cell['symbol']}.json"
            checkpoint = directory / name
            if checkpoint.is_file():
                print(f"  {label} {cell['alpha_id']}/{cell['symbol']} (checkpoint)", flush=True)
                out.append(json.loads(checkpoint.read_text()))
                continue
            if shard is not None and index % shard[1] != shard[0]:
                print(f"  {label} {cell['alpha_id']}/{cell['symbol']} (other shard)", flush=True)
                continue
            print(f"  {label} {cell['alpha_id']}/{cell['symbol']} ...", flush=True)
            record = compute(cell)
            checkpoint.write_text(json.dumps(record, indent=2, default=str))
            out.append(record)
        return out

    costs = collect(run_cells, cost_dir, "cost",
                    lambda cell: cost_panel(cell, protocol, cache, levels,
                                            progress=lambda m: print(m, flush=True)))
    information = collect(run_cells[:args.information_cells], info_dir, "info",
                          lambda cell: information_panel(cell, protocol, cache,
                                                         progress=lambda m: print(m, flush=True)))

    if shard is not None:
        print(f"\nshard {shard[0]}/{shard[1]} done; {len(costs)} cost cells and "
              f"{len(information)} information cells available here. "
              "Run without --shard to assemble the stress document.")
        return 0

    # ---- pooled reading of the cost panel
    def pooled(level: str) -> dict:
        per_arm = {}
        for arm in ARMS:
            values = [c["arms"][arm]["levels"][level]["net_return"] for c in costs
                      if c["arms"][arm].get("status") == "RUN"
                      and c["arms"][arm]["levels"][level]["net_return"] is not None]
            per_arm[arm] = {"cells": len(values),
                            "mean_net_return": float(np.mean(values)) if values else None,
                            "cells_positive": int(sum(1 for v in values if v > 0))}
        return per_arm

    harness_ok = all(entry["one_x_reproduces_the_confirmation_run"]
                     for panel in costs for entry in panel["arms"].values()
                     if entry.get("status") == "RUN")
    document = {
        "schema": "crypto_regime_lab.lab09_stress.v1",
        "generated_at_utc": utc_now_iso(),
        "window": [CONF_START, CONF_END],
        "cost_stress": {
            "multipliers": multipliers,
            "levels": [{"name": n, "fee_multiplier": f, "slippage_multiplier": sl}
                       for n, f, sl in levels],
            "registered_in": "configs/minimum_economic_effect.json",
            "registered_at_utc": effect["registered_at_utc"],
            "base_economics": {"taker_fee_rate": ACCOUNT["taker_fee_rate"],
                               "slippage_bps": ACCOUNT["slippage_bps"],
                               "use_funding": ACCOUNT["use_funding"]},
            "applied_to": ("the DEPLOYMENT. Selections are held at the ones the 1.0x run made; "
                           "re-selecting under stressed costs is a different and larger "
                           "experiment, and the guide permits a frozen sensitivity (L09.4)"),
            "limitation": ("a selector that re-scored its candidates at 2x costs might have "
                           "chosen differently, usually towards lower turnover. This panel "
                           "therefore bounds the damage to a FIXED schedule, not to an adaptive "
                           "one"),
            "harness_control": {
                "one_x_reproduces_every_arm": harness_ok,
                "why_it_matters": ("the 1.0x level is the only check that the stress harness is "
                                   "wired to the same account as the run it stresses. A harness "
                                   "running a different account would still produce a plausible "
                                   "panel"),
            },
            "per_cell": costs,
            "pooled": {name: pooled(name) for name, _f, _s in levels},
            "as_declared": {
                "what_it_is": ("the account the study registered at LAB-01: a one-way taker fee "
                               "of 0.0004 and 1 bp of slippage per side. It is reached at fee x2 "
                               "because the lab passes the registered ONE-WAY rate into an "
                               "engine parameter documented as ROUND-TRIP, so the engine halves "
                               "it (measured in configs/cost_binding_verification.json)"),
                "not_a_stress": ("this level is not a hypothetical. It is what the frozen "
                                 "account contract says, and the 1x level is the defect"),
                "slippage_left_at_1x": ("the slippage binding was measured correct -- 1 bp per "
                                        "side, exactly as declared -- so doubling it too would "
                                        "overstate the correction"),
            },
        },
        "information_stress": {
            "staged": True,
            "staging_rule": (f"the first {args.information_cells} RUN cells in protocol order, "
                             "chosen before any stress result was read"),
            "cells_covered": len(information),
            "cells_total_run": len(run_cells),
            "settings": {"mislabel_fraction": MISLABEL_FRACTION,
                         "mislabel_shift_observations": MISLABEL_SHIFT,
                         "stale_stretches": STALE_RUNS,
                         "stale_observations_each": STALE_OBSERVATIONS,
                         "missing_outages": MISSING_OUTAGES,
                         "missing_observations_per_outage": MISSING_OBSERVATIONS,
                         "seeds": SEEDS,
                         "registered_before_the_stress_ran": True},
            "per_cell": information,
            "did_each_stress_actually_bite": stress_bite(information),
        },
        "refit_latency": refit_latency_panel(protocol),
        "no_retuning_after_a_stress": {
            "rule": "L09.4.6. A stress that loses is a result, not a reason to change a setting",
            "this_is_a_COMMITMENT_not_a_measurement": (
                "no artifact can prove a setting was not changed after a result was seen; a "
                "rerun would simply overwrite it. What makes the commitment checkable is that "
                "every setting is recorded HERE with the seeds, and that any change to one after "
                "a stress ran would have to appear in configs/correction_ledger.json with what "
                "it invalidated. Claiming this as verified would be the same overreach the "
                "forbidden-claims audit exists to catch"),
            "settings_recorded_in_this_artifact": "information_stress.settings",
            "where_a_change_would_have_to_appear": "configs/correction_ledger.json",
            "changes_recorded_so_far": (
                "COR-19 changed MISSING_ENRICHMENT from a random 20% drop to contiguous outages. "
                "That change was made BEFORE the stress ran, because a smoke test showed the "
                "random version produced a schedule identical to the real one on all six cutoffs "
                "and therefore could not have produced a different answer"),
        },
        "wall_seconds": time.perf_counter() - started,
    }
    with writer.attempt("L09.4.stress") as att:
        att.detail = {"cost_cells": len(costs), "information_cells": len(information)}
    writer.write_config("lab09_stress.json", document)
    writer.write_json("lab09_stress.json", document, schema=document["schema"])

    print(f"\ncost stress over {len(costs)} cells, harness 1.0x reproduces: {harness_ok}")
    for level, per_arm in document["cost_stress"]["pooled"].items():
        line = "  ".join(
            f"{a}={per_arm[a]['mean_net_return']:+.2%}" if per_arm[a]["mean_net_return"]
            is not None else f"{a}=none" for a in ARMS)
        print(f"  {level:<12} {line}")
    print(f"\ninformation stress over {len(information)} cells")
    for entry in information:
        for name, record in entry["stresses"].items():
            if record["status"] == "RUN":
                print(f"  {entry['alpha_id']}/{entry['symbol']} {name:<24} "
                      f"D={entry['arm_D_net_return']:+.2%} -> {record['net_return']:+.2%} "
                      f"(cutoffs moved {record['cutoffs_moved_vs_arm_D']}/6)")
            elif record["status"] == "CONTROL":
                print(f"  {entry['alpha_id']}/{entry['symbol']} {name:<24} "
                      f"schedule identical: {record['schedule_identical_to_arm_D']}")
            else:
                print(f"  {entry['alpha_id']}/{entry['symbol']} {name:<24} {record['status']}")
    print(f"wall: {document['wall_seconds']:.0f}s")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
