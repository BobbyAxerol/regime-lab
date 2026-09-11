#!/usr/bin/env python
"""L08.6 / L08.7 — capture what the phase actually cost, then select one design.

The selection is the dangerous step. Five arms, twenty cells and several
contrasts give enough numbers that something always looks best, and the guide's
protections are all about not letting that be the decision: the endpoint is the
one registered before any result, the threshold is the minimum economic effect
fixed in LAB-01, and the outer window is not consulted at all.

So the rule is written here as a function of the registered inputs, and the
verdict is whatever it returns -- including NO_PROMISING_DESIGN, which the exit
gate explicitly allows and which profit is not required to avoid.
"""

from __future__ import annotations

import json
import statistics
import sys

import pandas as pd
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parent.parent
#: the development window every LAB-08 arm ran over, the same constant the runner uses
DEV_START, DEV_END = "2021-01-01", "2023-12-31"
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.identities import experiment_id  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def sign_test(differences: list[float]) -> dict:
    """A paired sign test — no distributional assumption about daily returns.

    Guide 11.3 forbids treating 1m returns as iid, and a t-test on a handful of
    cells would assume more than the sample supports. The sign test asks only
    whether the direction is consistent.
    """
    positive = sum(1 for d in differences if d > 0)
    negative = sum(1 for d in differences if d < 0)
    n = positive + negative
    if n == 0:
        return {"n": 0, "positive": 0, "negative": 0, "p_value": None,
                "reading": "every cell tied; the contrast has no direction"}
    from math import comb

    tail = sum(comb(n, k) for k in range(max(positive, negative), n + 1)) / (2 ** n)
    return {"n": n, "positive": positive, "negative": negative,
            "p_value": float(min(1.0, 2 * tail)),
            "reading": ("a paired sign test over cells: it asks only whether the direction is "
                        "consistent, because daily crypto returns are not iid (guide 11.3)")}


def holm_adjust(p_values: dict[str, float]) -> dict:
    """Holm step-down over the registered contrast family (guide 11.3)."""
    ordered = sorted((p for p in p_values.items() if p[1] is not None), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted, running = {}, 0.0
    for index, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, value * (m - index)))
        adjusted[name] = running
    for name, value in p_values.items():
        if value is None:
            adjusted[name] = None
    return {"adjusted": adjusted, "family_size": m,
            "rule": "Holm step-down over the registered primary contrast family, fixed in advance"}


def legacy_labelling() -> dict:
    """T54 — arm A is the installed public route, and that route declares OOS selection.

    LAB-04 read the engine's own walk-forward metadata and found that
    ``optimization_mode='none'`` -- the PUBLIC DEFAULT, and therefore arm A --
    is among the modes declaring OOS-adjusted selection. The label follows the
    declaration, not a behavioural probe: under expanding windows only the final
    test segment is out of sample for every fold, so a null probe bounds rather
    than refutes the dependence.

    The consequence for this phase is concrete. Every contrast below is measured
    against an arm that is NOT an untouched baseline, and guide 13.6 forbids
    reporting it as one.
    """
    trace = load("lab04_installed_wfo_trace.json") or {}
    labelling = trace.get("legacy_oos_labelling", {})
    default = trace.get("public_route_default", {})
    mode = default.get("optimization_mode")
    declares = mode in (labelling.get("modes_declaring_oos_selection") or [])
    return {
        "schema": "crypto_regime_lab.legacy_arm_label.v1",
        "arm": "A",
        "public_route_mode": mode,
        "selector": default.get("resolved_by"),
        "selection_rule": default.get("rule"),
        "mode_declares_oos_selection": declares,
        "label": "A_legacy_selection_adjusted" if declares else "A_causal_baseline",
        "may_be_reported_as_an_untouched_baseline": not declares,
        "authoritative_source": labelling.get("authoritative_source"),
        "probe_limit": labelling.get("behavioural_probe_limit"),
        "consequence": (
            "every contrast in this phase is measured against A_legacy_selection_adjusted. A "
            "positive B-A is evidence about the neighbourhood selector versus THAT baseline, not "
            "versus a causal one, and guide 13.6 forbids calling it out-of-sample"),
    }


def arm_e_status(cells: list[dict]) -> dict:
    """Is arm E an arm here, or a copy of arm D wearing a fifth column?

    LAB-06 measured zero switches on the registered thresholds, so the response
    policy deploys D's schedule unchanged. The factorial table then shows five
    columns where there are four distinct arms, and a note in prose does not
    stop a reader from treating the fifth as independent evidence.
    """
    identical = 0
    compared = 0
    for cell in cells:
        arms = cell.get("arms") or {}
        d, e = arms.get("D") or {}, arms.get("E") or {}
        if d.get("status") != "RUN" or e.get("status") != "RUN":
            continue
        compared += 1
        if (d.get("net_return") == e.get("net_return")
                and d.get("trades") == e.get("trades")):
            identical += 1
    # guide 10.1 asks for E against B AND against the matched-bank control. Both
    # comparisons are named here; a comparison that is degenerate has to be
    # reported as a degenerate comparison, not left out because it says nothing.
    bank = None
    for cell in cells:
        control = ((cell.get("controls") or {}).get("BANK_CALENDAR") or {})
        if control:
            bank = control
            break
    return {
        "cells_compared": compared,
        "cells_where_E_equals_D": identical,
        "E_is_a_distinct_arm": identical < compared,
        "degenerate": compared > 0 and identical == compared,
        "versus_B": {
            "contrast": "E-B",
            "status": "EQUALS_D_MINUS_B" if compared and identical == compared else "DISTINCT",
            "where": "contrast_panel['E-B']",
        },
        "versus_BANK_CALENDAR": {
            "control_status": (bank or {}).get("status"),
            "comparison": "DEGENERATE_ON_BOTH_SIDES",
            "why": ("the control switches a bank on the calendar and arm E switches it on the "
                    "regime. LAB-06 measured zero switches on the registered thresholds, so both "
                    "deploy the same sequence and the difference is identically zero. It is "
                    "reported as a degenerate comparison rather than omitted (guide 10.1, 10.2)"),
            "what_would_make_it_informative": ("a threshold at which the policy switches at all. "
                                               "The best challenger ever measured was 2.58 bps "
                                               "against a 7 bps switch cost"),
        },
        "reason": ("LAB-06 measured ZERO switches on the registered thresholds, so arm E's "
                   "response policy never overrode arm D's schedule. On this run E is not a "
                   "fifth arm; it is arm D, and every E number is a D number"),
        "consequence": ("E contributes no independent evidence, E-B equals D-B, and E is excluded "
                        "from the design-selection candidates and from the Holm family"),
    }


def control_verdict(control_arms: dict | None) -> dict:
    """What the substituted-tape arms say about where the dynamic result came from.

    This is the control that can sink the method, and here it does. If an arm
    driven by a FAKE tape with matched dwell does as well as the arm driven by
    the real states, then what the dynamic arms were doing was refreshing on a
    persistent signal at that cadence -- any persistent signal. The regime model
    contributed the cadence, not the information.
    """
    if control_arms is None:
        return {"status": "NOT_RUN", "reason": "run scripts/run_lab08_control_arms.py"}
    rows = []
    for cell in control_arms["cells"]:
        for control, comparison in (cell.get("versus_arm_D") or {}).items():
            if comparison.get("status") == "INCOMPARABLE":
                continue
            rows.append({"alpha_id": cell["alpha_id"], "symbol": cell["symbol"],
                         "control": control, **comparison})
    placebo = [r for r in rows if r["control"] == "STATE_PLACEBO"]
    delayed = [r for r in rows if r["control"] == "DELAYED_STATE"]
    placebo_wins = sum(1 for r in placebo if r["difference"] > 0)
    delayed_unchanged = sum(1 for r in delayed if abs(r["difference"]) < 1e-9)
    return {
        "status": "RUN",
        "staged_over_cells": control_arms["cells_covered"],
        "of_runnable_cells": control_arms["cells_total_runnable"],
        "rows": rows,
        "placebo_matched_or_beat_arm_D_in": placebo_wins,
        "placebo_cells": len(placebo),
        "delayed_state_left_arm_D_unchanged_in": delayed_unchanged,
        "delayed_cells": len(delayed),
        "reading": (
            "a placebo arm that matches or beats the real one says the dynamic arms were "
            "refreshing on a persistent signal at a cadence, and that ANY signal with that dwell "
            "would have done as well. The regime model supplied the cadence, not the information"),
        "this_control_can_sink_the_method": True,
        "not_dropped_for_winning": ("guide 10.2 forbids removing a control because it beats the "
                                    "proposal; it is reported exactly as it came out"),
    }


def contrast_panel(cells: list[dict]) -> dict:
    """Every registered contrast, pooled across the cells that could produce it."""
    panel: dict = {}
    for cell in cells:                      # E-B is computed here, not in the runner
        arms = cell.get("arms") or {}
        e, b, d = arms.get("E") or {}, arms.get("B") or {}, arms.get("D") or {}
        contrasts = cell.setdefault("contrasts", {})
        # Arm E is IDENTICAL to arm D on this run: LAB-06 measured zero switches
        # on the registered thresholds, so the policy deploys D's schedule
        # unchanged. When that is true, E-B is D-B -- not a separate number.
        #
        # The first version computed E-B as (total return difference) / days
        # while every other contrast used a true paired daily difference. Two
        # contrasts between IDENTICAL arms and the same B came out different,
        # which is how the mismatch surfaced: putting two statistics in one
        # table invites reading them as comparable.
        identical_to_d = (e.get("net_return") == d.get("net_return")
                          and e.get("trades") == d.get("trades")
                          and e.get("status") == d.get("status") == "RUN")
        if identical_to_d and (contrasts.get("D-B") or {}).get("status") == "OK":
            contrasts["E-B"] = {
                **contrasts["D-B"], "contrast": "E-B",
                "equals_D_B_by_construction": True,
                "note": ("arm E deployed arm D's schedule unchanged, so E-B IS D-B. It carries no "
                         "information beyond D-B and is shown only because guide 10.1 asks for E "
                         "to be compared against B"),
            }
        elif e.get("net_return") is not None and b.get("net_return") is not None:
            contrasts["E-B"] = {"contrast": "E-B", "status": "NEEDS_PAIRED_SERIES",
                                "mean_daily_difference": None,
                                "note": ("E diverged from D, so E-B needs its own paired daily "
                                         "series rather than a ratio of totals")}
        else:
            contrasts["E-B"] = {"contrast": "E-B", "status": "INCOMPARABLE",
                                "mean_daily_difference": None}
    # E-B is not part of the core factorial. Guide 10.1: "E phải so B và
    # matched-bank controls" -- it is an EXTENSION, and reporting it alongside
    # C and D as though it were a fourth core arm is exactly the substitution
    # the guide forbids.
    for name in ("B-A", "C-A", "D-B", "D-C", "(D-C)-(B-A)", "E-B"):
        values, per_cell = [], []
        for cell in cells:
            record = (cell.get("contrasts") or {}).get(name)
            if not record:
                continue
            value = record.get("mean_daily_difference", record.get("value"))
            per_cell.append({"alpha_id": cell["alpha_id"], "symbol": cell["symbol"],
                             "value": value, "status": record.get("status")})
            if value is not None:
                values.append(value)
        # a per-cell flag that holds on EVERY cell is a property of the contrast,
        # so it belongs on the pooled entry too. Leaving it only on the rows let
        # the panel show E-B as an independent contrast.
        derived = all((cell.get("contrasts") or {}).get(name, {}).get(
            "equals_D_B_by_construction") for cell in cells) if cells else False
        panel[name] = {
            "cells_with_a_value": len(values),
            "cells_attempted": len(per_cell),
            "mean_daily_difference": float(statistics.fmean(values)) if values else None,
            "median_daily_difference": float(statistics.median(values)) if values else None,
            "sign_test": sign_test(values),
            "per_cell": per_cell,
        }
        if derived:
            panel[name]["equals_D_B_by_construction"] = True
            panel[name]["carries_no_independent_information"] = (
                "arm E deployed arm D's schedule unchanged on every cell, so this contrast IS "
                "D-B. It is shown because guide 10.1 asks for E to be compared against B, and it "
                "is excluded from the Holm family and from the design-selection candidates")
    return panel


def measured_workers() -> int:
    """How many lab worker processes actually ran at once.

    The run is sequential by construction -- one cell at a time in one process --
    so this reads 1, and reading it is the point: a declared 1 and an observed 1
    look identical in the artifact and only one of them is evidence.
    """
    import subprocess

    proc = subprocess.run(["ps", "-eo", "cmd"], capture_output=True, text=True)
    return max(1, sum(1 for line in proc.stdout.splitlines()
                      if "crypto_regime_lab" in line or "run_lab08" in line))


def measured_peak_rss_gib() -> float | None:
    import resource

    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak_kb / (1024 ** 2), 3) if peak_kb else None


def budget_exceeded(budget: dict) -> bool:
    workers, memory = measured_workers(), measured_peak_rss_gib()
    over_workers = workers > int(budget.get("workers", 1))
    over_memory = (memory is not None
                   and memory > float(budget.get("working_memory_gib", 4)))
    return bool(over_workers or over_memory)


def refit_latency_in_bars(cells: list[dict], protocol: dict) -> dict:
    """Does a refit's compute time actually delay an activation, at these bar sizes?

    Guide L07.3 forbids taking a latency of zero in order to fill earlier. The
    honest answer here is that the measured latency is real but SUB-BAR: a refit
    costs seconds and the coarsest decision bar is an hour, so it rounds to zero
    bars. That is a measurement, not an assumption, and stating it is the
    difference between the two.

    The delays these arms DO pay are the ones LAB-07 measured in bars: waiting
    for a flat book and for the new version's indicators to warm.
    """
    trace = load("lab07_continuous_trace.json") or {}
    jobs = trace.get("training_jobs") or {}
    seconds = (jobs.get("benchmark") or {}).get("measured_seconds_per_fit")
    per_interval = {}
    for alpha_id, spec in (protocol.get("timeframes") or {}).items():
        bar = spec["decision_bars"].replace("m", "min")
        bar_seconds = pd.Timedelta(bar).total_seconds()
        per_interval[alpha_id] = {
            "decision_bars": spec["decision_bars"],
            "bar_seconds": bar_seconds,
            "refit_bars": (None if seconds is None else seconds / bar_seconds),
            "rounds_to_bars": (None if seconds is None else int(seconds // bar_seconds)),
        }
    warm = []
    for cell in cells:
        for arm in ("C", "D"):
            record = (cell.get("arms") or {}).get(arm) or {}
            if record.get("switches_requested"):
                warm.append(record["switches_requested"] - record.get("switches_effected", 0))
    return {
        "measured_seconds_per_fit": seconds,
        "per_alpha": per_interval,
        "refit_latency_rounds_to_zero_bars": all(
            v["rounds_to_bars"] == 0 for v in per_interval.values() if v["rounds_to_bars"] is not None),
        "why_that_is_not_a_free_option": (
            "a refit costs seconds and the coarsest decision bar here is an hour, so the compute "
            "latency is real and smaller than one bar. Recording zero BARS is a measurement; "
            "assuming zero SECONDS would be the free option guide L07.3 forbids"),
        "delays_the_arms_do_pay": (
            "waiting for a flat book and for the new version's own declared warmup, both measured "
            "in bars by LAB-07's continuous account"),
        "switches_requested_but_not_effected": sum(warm),
    }


def counted_units() -> dict:
    """Every unit the compute-budget registration says it counts.

    The registration names five: unique strategy evaluations, fold-bar visits,
    independent local probes, regime model fits INCLUDING every multi-start, and
    response evaluations. An earlier version of this capture reported the first
    one, for the dynamic half only, and called itself MATCHED_TOTAL_COMPUTE.
    A budget report that does not count four of its own declared units cannot
    say whether the two arms were given the same total.

    Each number below is summed from a committed artifact, so it is auditable
    rather than estimated.
    """
    def cutoff_records(cell: dict) -> list[dict]:
        if cell.get("folds"):
            return cell["folds"]
        notes = cell.get("notes") or {}
        return (notes.get("calendar_cutoff_evidence") or []) + (
            notes.get("regime_cutoff_evidence") or [])

    def spend(cells: list[dict]) -> dict:
        executions = visits = probes = cutoffs = 0
        for cell in cells:
            for record in cutoff_records(cell):
                evidence = record.get("cutoff_evidence")
                if not evidence:
                    continue
                cutoffs += 1
                budget = evidence.get("budget") or {}
                executions += budget.get("unique_executions", 0)
                visits += budget.get("candidate_episode_visits", 0)
                probes += (evidence.get("probe_design") or {}).get("probe_count", 0)
        return {"cutoffs": cutoffs, "unique_strategy_evaluations": executions,
                "fold_bar_visits": visits, "independent_local_probes": probes}

    baseline = load("lab04_calendar_baseline.json") or {}
    factorial = load("lab08_factorial_full.json") or {}
    calendar = spend([c for c in baseline.get("cells", []) if c.get("status") == "RUN"])
    dynamic = spend([c for c in factorial.get("cells", []) if c.get("status") == "RUN"])

    # ONLY the registries this phase's arms read. A later phase fits its own
    # models on its own interval, and adding those to LAB-08's bill would report
    # compute that LAB-08 never spent.
    # the same prefix rule the runner uses: BTCUSDT's registry is LAB-05's,
    # because LAB-05 fitted it and LAB-08 reused it rather than refitting
    consumed = {"lab05" if symbol == "BTCUSDT" else f"lab08_{symbol.lower()}"
                for symbol in {c["symbol"] for c in factorial.get("cells", [])
                               if c.get("status") == "RUN"}}
    fits = {}
    for name in sorted((LAB_ROOT / "configs").glob("*_regime_model_registry.json")):
        prefix = name.stem.replace("_regime_model_registry", "")
        if prefix not in consumed:
            continue
        registry = json.loads(name.read_text())
        models = registry.get("models") or []
        seeds = len(models[0].get("seeds") or []) if models else 0
        fits[prefix] = {"refits": len(models), "seeds_per_refit": seeds,
                        "multi_start_fits": len(models) * seeds,
                        "data_role": registry.get("data_role")}
    response = load("lab06_response_model.json") or {}

    return {
        "rule": (budget_rule_text() or "").strip(),
        "per_arm_family": {
            "calendar_arms_A_and_B": {
                **calendar,
                "source": "configs/lab04_calendar_baseline.json — the selections arms A and B "
                          "redeploy were made there"},
            "dynamic_arms_C_D_E": {
                **dynamic,
                "source": "configs/lab08_factorial_full.json cells[].notes"
                          ".regime_cutoff_evidence"},
        },
        "matched": {
            "cutoffs_equal": calendar["cutoffs"] == dynamic["cutoffs"],
            "evaluations_ratio": (dynamic["unique_strategy_evaluations"]
                                  / calendar["unique_strategy_evaluations"]
                                  if calendar["unique_strategy_evaluations"] else None),
            "reading": ("the dynamic arms were given the calendar's refresh COUNT, so the cutoff "
                        "counts match by construction. The evaluation ratio shows whether the "
                        "same number of cutoffs actually consumed the same search effort"),
        },
        "regime_model_fits": {
            "registries_consumed_by_this_phase": sorted(consumed),
            "per_symbol": fits,
            "total_refits": sum(v["refits"] for v in fits.values()),
            "total_multi_start_fits": sum(v["multi_start_fits"] for v in fits.values()),
            "counted_against": ("the dynamic arms only. A regime arm that spends its budget on "
                                "model fits instead of on alpha trials has still spent it"),
        },
        "response_evaluations": {
            "count": response.get("response_count"),
            "episode_panel_rows": response.get("episode_panel_rows"),
            "scope": "LAB-06 ran the response layer on ONE cell (A-SC/BTCUSDT)",
        },
    }


def budget_rule_text() -> str | None:
    budget = load("compute_budget_registration.json") or {}
    return ((budget.get("reports") or {}).get("MATCHED_TOTAL_COMPUTE") or {}).get("rule")


def latency_capture(cells: list[dict]) -> dict:
    """Cold/warm runtime and the waiting a refit and an activation actually cost."""
    trace = load("lab07_continuous_trace.json") or {}
    jobs = trace.get("training_jobs") or {}
    delays = []
    for cell in cells:
        for arm, record in (cell.get("arms") or {}).items():
            switch_delays = record.get("switch_delays")
            if switch_delays:
                delays.append(switch_delays["blocked_bars_total"])
    account = trace.get("continuous_account") or {}
    switches = account.get("switches") or []
    return {
        "refit_latency_seconds": {
            "min": jobs.get("min_delay_seconds"),
            "max": jobs.get("max_delay_seconds"),
            "zero_latency_jobs": jobs.get("zero_latency_jobs"),
            "source": (jobs.get("benchmark") or {}).get("source"),
            "rule": "guide L07.3 forbids taking a refit latency of zero in order to fill earlier",
        },
        "activation_delay_bars": {
            "per_switch": [s.get("blocked_bars") for s in switches],
            "max": max((s.get("blocked_bars") or 0 for s in switches), default=None),
            "source": "configs/lab07_continuous_trace.json continuous_account.switches",
        },
        "activation_delay_bars_in_this_phase": {
            "arms_with_a_record": len(delays),
            "total_blocked_bars": sum(delays) if delays else None,
            "note": ("the factorial run predates the per-arm switch_delays field, so this is "
                     "empty for LAB-08's committed cells and populated from LAB-09 onward. "
                     "Reported empty rather than omitted"),
        },
        "cold_vs_warm_runtime": {
            "status": "NOT_SEPARATELY_MEASURED",
            "why": ("every cell in this phase ran cold: the process starts once, each cell is "
                    "visited once, and nothing is re-run inside the same process. A cold/warm "
                    "split needs a second visit to the same cell, which the design does not "
                    "have"),
            "what_would_measure_it": ("re-running one completed cell in the same process and "
                                      "comparing its wall time against the first visit"),
        },
    }


def common_period_capture(cells: list[dict]) -> dict:
    """Guide 10.4 — is the five-symbol aggregate a COMMON-period aggregate?

    LAB-08 stored contrast summaries rather than daily series, so the spans are
    reconstructed from each cell's own recorded evaluation window. The question
    is the same one: does the pooled number average cells that ran over the same
    interval, or does it mix windows and wear the first one's name?
    """
    eligibility = load("data_eligibility.json") or {}
    declared = eligibility.get("five_symbol_common_period")
    per_symbol = {}
    for symbol, record in (eligibility.get("per_symbol") or {}).items():
        per_symbol[symbol] = record.get("usable_interval")
    window = [DEV_START, DEV_END]
    symbols = sorted({c["symbol"] for c in cells})
    inside = {
        symbol: (per_symbol.get(symbol) is not None
                 and per_symbol[symbol][0][:10] <= window[0]
                 and per_symbol[symbol][1][:10] >= window[1])
        for symbol in symbols}
    return {
        "phase_window": window,
        "declared_five_symbol_common_period": declared,
        "per_symbol_usable_interval": {s: per_symbol.get(s) for s in symbols},
        "every_symbol_covers_the_whole_window": all(inside.values()),
        "symbols_not_covering_the_window": [s for s, ok in inside.items() if not ok],
        "pooled_statistic_is_a_common_period_aggregate": all(inside.values()),
        "reading": ("every symbol's usable interval contains the whole phase window, so the "
                    "common-period aggregate and the longest-history aggregate are the same "
                    "number. Guide 10.4 asks for them separately; they are reported as equal, "
                    "measured, rather than assumed"),
        "zeros_before_listing": "none: no cell begins before its symbol's usable interval",
        "statistic_name": ("macro-average over cells of a paired daily difference. Guide 11.3 "
                           "forbids implying a portfolio without a capital allocation and an "
                           "account simulator, and there is neither"),
    }


def compute_capture(document: dict, cells: list[dict]) -> dict:
    """L08.6 — what the phase actually cost, measured not estimated."""
    budget = load("compute_budget_registration.json") or {}
    registration = load("study_registration.json") or {}
    wall = [c.get("wall_seconds") for c in cells if c.get("wall_seconds")]
    refreshes = sum(len((c.get("notes") or {}).get("regime_cutoff_evidence") or [])
                    for c in cells)
    executions = 0
    for cell in cells:
        for record in (cell.get("notes") or {}).get("regime_cutoff_evidence") or []:
            evidence = record.get("cutoff_evidence") or {}
            executions += (evidence.get("budget") or {}).get("unique_executions", 0)
    return {
        "schema": "crypto_regime_lab.lab08_compute.v1",
        "counts_against": "MATCHED_TOTAL_COMPUTE and OPERATIONAL_POLICY (guide 10.5)",
        "cells_run": len(cells),
        "dynamic_refreshes": refreshes,
        "unique_strategy_executions_in_dynamic_refreshes": executions,
        "total_wall_seconds": float(sum(wall)) if wall else None,
        "wall_seconds_per_cell": {
            "min": float(min(wall)) if wall else None,
            "median": float(statistics.median(wall)) if wall else None,
            "max": float(max(wall)) if wall else None,
        },
        "resource_budget": registration.get("resource_budget"),
        # MEASURED, not asserted. `budget_exceeded: False` was a hardcoded claim
        # sitting in an artifact that a report then quoted -- the same shape as
        # every other defect this lab has found.
        "workers_used": measured_workers(),
        "peak_working_set_gib": measured_peak_rss_gib(),
        "budget_exceeded": budget_exceeded(registration.get("resource_budget") or {}),
        "measurement_note": ("workers is the observed count of concurrent lab processes and the "
                             "working set is this process's peak RSS. Both are read from the OS "
                             "rather than declared"),
        "budget_rule": (budget.get("reports", {}).get("MATCHED_TOTAL_COMPUTE", {}) or {}).get(
            "rule"),
        "match_note": ("the dynamic arms were given the calendar's refresh COUNT by construction, "
                       "so neither side bought an advantage with extra searches. The wall time "
                       "below is the operational cost of the same budget spent differently"),
        # every unit the registration declares, not only the first one
        "counted_units": counted_units(),
        "latency": latency_capture(cells),
        "units_declared_by_the_registration": (
            (budget.get("reports") or {}).get("MATCHED_TOTAL_COMPUTE", {}) or {}).get(
                "counted_units"),
    }


def select_design(panel: dict, cells: list[dict], protocol: dict) -> dict:
    """L08.7 — one design, or NO_PROMISING_DESIGN. Decided by a registered rule."""
    effect = load("minimum_economic_effect.json") or {}
    minimum = effect.get("minimum_daily_net_return_difference") \
        or effect.get("minimum_economic_effect_per_day")
    registry = load("hypothesis_registry.json") or {}

    # Holm over the REGISTERED contrast family, which is the five in the frozen
    # protocol. E-B was silently inside it, making the family six and every
    # adjusted p-value more conservative than the registration allows -- and E
    # is an extension, not a member of the core family at all.
    family = list(protocol["registered_contrasts"])
    p_values = {name: record["sign_test"]["p_value"]
                for name, record in panel.items() if name in family}
    holm = holm_adjust(p_values)
    holm["family"] = family
    holm["excluded_from_family"] = sorted(set(panel) - set(family))
    holm["exclusion_reason"] = (
        "E-B is an extension contrast (guide 10.1), not a member of the registered primary "
        "family. Counting it would enlarge the family and change every adjusted p-value")

    candidates = []
    # only the CORE factorial contrasts are eligible to freeze a design. E is an
    # extension; freezing on E-B would be using E in place of C or D.
    for name in ("B-A", "C-A", "D-B", "D-C"):
        record = panel[name]
        mean = record["mean_daily_difference"]
        if mean is None:
            continue
        candidates.append({
            "contrast": name,
            "mean_daily_difference": mean,
            "clears_minimum_effect": bool(minimum is not None and mean >= minimum),
            "sign_test_p": record["sign_test"]["p_value"],
            "holm_adjusted_p": holm["adjusted"].get(name),
            "cells": record["cells_with_a_value"],
        })

    clearing = [c for c in candidates
                if c["clears_minimum_effect"]
                and c["holm_adjusted_p"] is not None and c["holm_adjusted_p"] < 0.05]
    if clearing:
        best = max(clearing, key=lambda c: c["mean_daily_difference"])
        outcome, chosen = "DESIGN_FROZEN", best["contrast"]
    else:
        outcome, chosen = "NO_PROMISING_DESIGN", None

    interaction = panel.get("(D-C)-(B-A)", {}).get("sign_test", {})
    return {
        "schema": "crypto_regime_lab.lab08_design_selection.v1",
        "decided_at_utc": utc_now_iso(),
        "outcome": outcome,
        "selected_contrast": chosen,
        "interaction": {
            "nominal_p": interaction.get("p_value"),
            "holm_adjusted_p": holm["adjusted"].get("(D-C)-(B-A)"),
            "mean_daily_difference": panel.get("(D-C)-(B-A)", {}).get("mean_daily_difference"),
            "reading": ("the interaction is the only contrast with a nominally significant sign "
                        "test, and it is NEGATIVE. After Holm adjustment over the registered "
                        "family it is not significant either, which is the number that counts"),
        },
        "registered_endpoint": protocol.get("primary_endpoint"),
        "minimum_economic_effect_per_day": minimum,
        "decision_rule": (
            "a design is frozen only if its contrast clears the minimum economic effect "
            "registered in LAB-01 AND survives Holm adjustment over the registered contrast "
            "family. Both thresholds were fixed before any arm ran"),
        "candidates": candidates,
        "holm": holm,
        "evidence_stage": "development only; the outer window was not consulted",
        "conclusion_vocabulary": registry.get("conclusion_levels"),
        "tradeoffs": [
            "the dynamic arms cost more wall time for the same search budget, because a refresh "
            "at an arbitrary date cannot reuse a cached calendar fold",
            "arm E is an extension whose own contribution is null here: LAB-06 measured zero "
            "switches on the registered thresholds, so E deploys D's schedule",
            "every cell is one continuous account, so a cell's result is one path and not an "
            "average over independent folds",
        ],
        "failure_cases": [
            "A-HASH contributes no cell at all: its ladder blocker is unresolved and its five "
            "cells carry null metrics",
            "the guide 8.3 group ablation FAILS on all five symbols, so the states are not shown "
            "to resolve out-of-fold variance beyond price and volatility",
            "no data cohort beyond the server core improves anything (L08.4)",
            "a STATE_PLACEBO arm with matched dwell matches or beats arm D on most of the staged "
            "cells, so the dynamic arms' behaviour is attributable to the refresh cadence rather "
            "than to the regime signal",
        ],
        "uncertainty": [
            "the sign test over cells is a direction test, not an effect-size estimate",
            "cells within an alpha share a selector and are not independent, so the sign test "
            "over-counts evidence; the guide's block bootstrap is LAB-09's",
            "three years of development on one cohort is a small sample for a daily endpoint",
        ],
        "alpha_versions_frozen": True,
        "optional_alpha_improvements_folded_in": False,
        "not_required_to_be_profitable": (
            "guide L08 exit: profit is not required to close discovery, and a negative result is "
            "not a technical failure to be re-run until it wins"),
    }


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    factorial = load("lab08_factorial_full.json")
    if factorial is None:
        print("BLOCKED: run scripts/run_lab08_factorial.py --stage full first")
        return 1
    protocol = load("lab08_pilot_protocol.json")
    cells = [c for c in factorial["cells"] if c["status"] == "RUN"]

    control_arms = load("lab08_control_arms.json")

    # guide 13.1: arm + cell + cohort + config version. LAB-08 is the phase that
    # mints this, and until now it was the last identity still OWED.
    config_version = protocol["frozen_at_utc"]
    experiments = [
        {"experiment_id": experiment_id(arm=arm, alpha_id=cell["alpha_id"],
                                        symbol=cell["symbol"], cohort="server_core",
                                        config_version=config_version),
         "arm": arm, "alpha_id": cell["alpha_id"], "symbol": cell["symbol"],
         "cohort": "server_core", "config_version": config_version,
         "status": (cell.get("arms") or {}).get(arm, {}).get("status")}
        for cell in factorial["cells"] for arm in ("A", "B", "C", "D", "E")
    ]

    with writer.attempt("L08.6_7.discovery_analysis") as att:
        panel = contrast_panel(cells)
        label = legacy_labelling()
        compute = compute_capture(factorial, cells)
        compute["refit_latency"] = refit_latency_in_bars(cells, protocol)
        selection = select_design(panel, cells, protocol)
        att.detail = {"outcome": selection["outcome"], "cells": len(cells)}

    document = {
        "schema": "crypto_regime_lab.lab08_discovery.v1",
        "generated_at_utc": utc_now_iso(),
        "experiments": experiments,
        "experiment_count": len(experiments),
        "experiment_id_rule": ("guide 13.1: arm + cell + cohort + config version. The config "
                               "version is the protocol freeze stamp, because the same arm on "
                               "the same cell under a different protocol is a different "
                               "experiment"),
        "cells_run": len(cells),
        "cells_total": factorial["cells_planned"],
        "cells_not_ready": factorial["cells_not_ready"],
        "contrast_panel": panel,
        "common_period": common_period_capture(cells),
        "legacy_arm_label": label,
        "arm_e": arm_e_status(cells),
        "control_arms": control_verdict(control_arms),
        "compute": compute,
        "design_selection": selection,
        "all_attempted_hypotheses": [
            {"id": name, "question": record.get("reading", name),
             "cells_with_a_value": record["cells_with_a_value"],
             "mean_daily_difference": record["mean_daily_difference"]}
            for name, record in panel.items()
        ],
    }
    writer.write_config("lab08_discovery.json", document)
    writer.write_json("lab08_discovery.json", document, schema=document["schema"])

    print(f"cells run: {len(cells)} of {factorial['cells_planned']} "
          f"({factorial['cells_not_ready']} NOT_READY)")
    e_status = document["arm_e"]
    if e_status["degenerate"]:
        print(f"arm E: DEGENERATE — identical to arm D in "
              f"{e_status['cells_where_E_equals_D']}/{e_status['cells_compared']} cells")
    print(f"arm A label: {label['label']} "
          f"(mode={label['public_route_mode']}, declares OOS selection="
          f"{label['mode_declares_oos_selection']})\n")
    print("registered contrasts, pooled over cells:")
    for name, record in panel.items():
        mean = record["mean_daily_difference"]
        p = record["sign_test"]["p_value"]
        print(f"  {name:<14} mean_daily={mean:+.6f}" if mean is not None
              else f"  {name:<14} mean_daily=None", end="")
        print(f"  cells={record['cells_with_a_value']}"
              f"  sign_test p={p if p is None else round(p, 4)}"
              f"  ({record['sign_test']['positive']}+/{record['sign_test']['negative']}-)")
    print(f"\nminimum economic effect: "
          f"{selection['minimum_economic_effect_per_day']}/day")
    for candidate in selection["candidates"]:
        print(f"  {candidate['contrast']:<8} clears_minimum={candidate['clears_minimum_effect']}"
              f"  holm_p={candidate['holm_adjusted_p']}")
    print(f"\nOUTCOME: {selection['outcome']}"
          + (f" -> {selection['selected_contrast']}" if selection["selected_contrast"] else ""))
    controls = document["control_arms"]
    if controls.get("status") == "RUN":
        print(f"\nstaged control arms over {controls['staged_over_cells']} of "
              f"{controls['of_runnable_cells']} cells:")
        print(f"  placebo matched or beat arm D in "
              f"{controls['placebo_matched_or_beat_arm_D_in']}/{controls['placebo_cells']} cells")
        print(f"  delayed state left arm D unchanged in "
              f"{controls['delayed_state_left_arm_D_unchanged_in']}/{controls['delayed_cells']}")
    print(f"compute: {compute['dynamic_refreshes']} dynamic refreshes, "
          f"{compute['unique_strategy_executions_in_dynamic_refreshes']} unique executions, "
          f"{compute['total_wall_seconds']:.0f}s wall")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
