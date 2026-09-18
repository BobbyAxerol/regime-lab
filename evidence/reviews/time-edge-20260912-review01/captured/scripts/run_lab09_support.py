#!/usr/bin/env python
"""L09.5 — support and novelty: does the machinery behave where it was not built?

The confirmation interval is two years and eight months the design never saw. Six
situations the guide names have to be looked for there, and each one is reported
whether it occurred or not -- "did not occur" is a finding, "was not checked" is
a gap, and a panel that cannot tell them apart is worthless.

  new regime episode      states the model had not seen, by its own novelty rule
  mixed / ambiguous       observations where the runner-up state was nearly as good
  label permutation       ids permuted after a refit; a correct consumer is unmoved
  stale candidate bank    a bank whose newest candidate is old at decision time
  no challenger qualifies the decision path when nothing clears the bar
  campaign not flat       a switch that had to wait for an open position to close

The last three come from running LAB-06's policy, unchanged, over the
confirmation interval. Unchanged is the point: a policy retuned for the
confirmation confirms nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments.stress import ambiguity_profile  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
#: LAB-05's registered comparator cadence. A model older than this is STALE.
MAX_MODEL_AGE_DAYS = 56


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def gap_quantile(tape_record: dict, q: float) -> float | None:
    gaps = [e["second_best_gap"] for record in tape_record.get("namespaces", {}).values()
            for e in record.get("emissions", []) if e.get("second_best_gap") is not None]
    return float(np.quantile(gaps, q)) if gaps else None


def novelty_panel() -> dict:
    """L09.5.1 — states the model's own novelty rule could not place.

    The rule is LAB-05's, fitted on each training window: an observation whose
    residual exceeds the fitted threshold is UNKNOWN_STATE. It is not a judgement
    made here after seeing the interval.
    """
    per_symbol = {}
    for symbol in SYMBOLS:
        confirmation = load(f"lab09_{symbol.lower()}_emission_tape.json")
        development = load("lab05_emission_tape.json" if symbol == "BTCUSDT"
                          else f"lab08_{symbol.lower()}_emission_tape.json")
        if confirmation is None:
            per_symbol[symbol] = {"status": "NO_CONFIRMATION_TAPE"}
            continue
        counts = confirmation.get("quality_status_counts", {})
        total = sum(counts.values()) or 1
        development_counts = (development or {}).get("quality_status_counts", {})
        development_total = sum(development_counts.values()) or 1
        per_symbol[symbol] = {
            "status": "MEASURED",
            "emissions": total,
            "quality_status_counts": counts,
            "novel_share": counts.get("UNKNOWN_STATE", 0) / total,
            "development_novel_share": development_counts.get("UNKNOWN_STATE", 0)
            / development_total,
            "namespaces": len(confirmation.get("namespaces", {})),
            "switches_within_namespaces": confirmation.get(
                "total_switches_within_namespaces"),
        }
    measured = [v for v in per_symbol.values() if v.get("status") == "MEASURED"]
    return {
        "per_symbol": per_symbol,
        "symbols_with_more_novelty_than_development": sum(
            1 for v in measured if v["novel_share"] > v["development_novel_share"]),
        "symbols_measured": len(measured),
        "a_new_episode_was_exercised": any(v["novel_share"] > 0 for v in measured),
        "rule": ("UNKNOWN_STATE comes from the novelty threshold each model fitted on its own "
                 "training window (LAB-05 L05.3). It is the model saying it has not seen this, "
                 "not the lab deciding after the fact"),
    }


def ambiguity_panel() -> dict:
    """L09.5.2 — how often the chosen state was barely the chosen state."""
    per_symbol = {}
    for symbol in SYMBOLS:
        confirmation = load(f"lab09_{symbol.lower()}_emission_tape.json")
        development = load("lab05_emission_tape.json" if symbol == "BTCUSDT"
                           else f"lab08_{symbol.lower()}_emission_tape.json")
        if confirmation is None:
            per_symbol[symbol] = {"status": "NO_CONFIRMATION_TAPE"}
            continue
        reference = gap_quantile(development, 0.10) if development else None
        per_symbol[symbol] = ambiguity_profile(confirmation, reference_p10=reference)
    measured = [v for v in per_symbol.values() if v.get("observations")]
    return {
        "per_symbol": per_symbol,
        "symbols_more_ambiguous_than_development": sum(
            1 for v in measured if v.get("more_ambiguous_than_development")),
        "symbols_measured": len(measured),
        "reference": ("each symbol's own DEVELOPMENT tenth percentile of the second-best gap. "
                      "Comparing a tape against its own decile would report 10% by "
                      "construction and measure nothing"),
    }


def policy_panel(ledger: dict, banks: dict, spec: dict) -> dict:
    """L09.5.4-6 — the paths LAB-06's policy took on the confirmation interval."""
    counts = (ledger or {}).get("counts", {})
    decisions = (ledger or {}).get("decisions", 0)
    bank_records = (banks or {}).get("banks", {})
    sizes = [len(r.get("admissible", [])) if isinstance(r.get("admissible"), list)
             else r.get("admissible_count", 0) for r in bank_records.values()]
    cutoffs = sorted(bank_records)
    stale = None
    if cutoffs:
        last = pd.Timestamp(cutoffs[-1])
        if last.tzinfo is not None:
            last = last.tz_localize(None)
        end = pd.Timestamp((spec or {}).get("window", [None, None])[1] or last)
        if end.tzinfo is not None:
            end = end.tz_localize(None)
        stale = {"last_bank_cutoff": cutoffs[-1],
                 "interval_end": str(end),
                 "age_at_interval_end_days": float((end - last).days),
                 "older_than_the_registered_comparator_cadence":
                     bool((end - last).days > MAX_MODEL_AGE_DAYS),
                 "comparator_cadence_days": MAX_MODEL_AGE_DAYS}
    return {
        "decisions": decisions,
        "decision_counts": counts,
        "no_challenger_qualified": {
            "occurrences": counts.get("NO_SUPPORTED_CANDIDATE", 0),
            "share": (counts.get("NO_SUPPORTED_CANDIDATE", 0) / decisions) if decisions else None,
            "exercised": counts.get("NO_SUPPORTED_CANDIDATE", 0) > 0,
            "reading": ("the inaction region binding is a valid outcome, not a failure. It is "
                        "reported with its share so a reader can see whether the policy ever "
                        "had a decision to make"),
        },
        "novel_state_fallback": {
            "occurrences": counts.get("FALLBACK_NOVEL_STATE", 0),
            "exercised": counts.get("FALLBACK_NOVEL_STATE", 0) > 0,
            "reading": "the policy met a state it could not use and fell back rather than acting",
        },
        "switches_executed": counts.get("SWITCH_READY", 0),
        "bank": {
            "cutoffs": len(bank_records),
            "sizes": sizes,
            "staleness_at_interval_end": stale,
        },
    }


def campaign_panel(confirmation: dict) -> dict:
    """L09.5.6 — switches that had to wait, and what they waited for."""
    rows, bars_by_reason = [], {}
    waited_for_campaign = waited_for_warmup = 0
    arms_with_a_record = arms_run = switches_requested = 0
    for cell in confirmation.get("cells", []):
        if cell.get("status") != "RUN":
            continue
        for arm, record in (cell.get("arms") or {}).items():
            if record.get("status") == "RUN":
                arms_run += 1
                switches_requested += record.get("switches_requested") or 0
            delays = record.get("switch_delays")
            if not delays:
                continue
            arms_with_a_record += 1
            for reason, bars in (delays.get("blocked_bars_by_reason") or {}).items():
                bars_by_reason[reason] = bars_by_reason.get(reason, 0) + bars
            waited_for_campaign += delays.get("switches_that_waited_for_an_open_campaign", 0)
            waited_for_warmup += delays.get("switches_that_waited_for_warm_indicators", 0)
            if delays["blocked_bars_total"] > 0 or delays["never_effected"]:
                rows.append({"alpha_id": cell["alpha_id"], "symbol": cell["symbol"], "arm": arm,
                             **delays})
    # The denominator, so "0 arms waited" cannot be read as "checked and fine"
    # when the real answer is "no arm carried the field". Every count above is
    # meaningless without it, and this is the shape of every vacuity this lab has
    # found: a verdict over a population nobody reported.
    if arms_run == 0:
        status = "NO_ARM_RAN"
    elif arms_with_a_record == 0:
        status = "NOT_MEASURED"
    elif switches_requested == 0:
        status = "NO_SWITCH_WAS_EVER_REQUESTED"
    elif not rows:
        status = "MEASURED_NO_SWITCH_EVER_WAITED"
    else:
        status = "MEASURED"
    return {
        "status": status,
        "arms_run": arms_run,
        "arms_carrying_a_switch_delay_record": arms_with_a_record,
        "switches_requested_across_every_arm": switches_requested,
        "arms_with_a_delayed_switch": len(rows),
        "blocked_bars_by_reason_across_every_arm": bars_by_reason,
        "switches_that_waited_for_an_open_campaign": waited_for_campaign,
        "switches_that_waited_for_warm_indicators": waited_for_warmup,
        "a_switch_waited_for_an_open_campaign": waited_for_campaign > 0,
        "measured_from": ("blocked_bars_by_reason, accumulated while each switch waited. The "
                          "blocked_reason field is cleared on activation, so a histogram of "
                          "final reasons cannot answer this"),
        "per_arm": rows[:40],
        "rule": ("guide 9.5: an open campaign keeps the parameters it entered with and is never "
                 "closed early to let a switch land. The wait is the evidence that the rule was "
                 "exercised rather than merely written"),
    }


def transition_diagnostics(confirmation: dict, support_novelty: dict) -> dict:
    """Guide 11.4 — the diagnostics sit around DETECTED transitions.

    Every metric the clause names, and for the one that cannot be measured at
    this granularity, what it would take. A panel that silently omits the hard
    metric reads as though the hard metric came out fine.
    """
    from crypto_regime_lab.selector.alpha_schemas import SCHEMAS

    rows, turnovers, dwell = [], [], []
    repeats = {"same_point_as_previous_cutoff": 0, "cutoff_pairs": 0}
    requested = effected = 0
    for cell in confirmation.get("cells", []):
        if cell.get("status") != "RUN":
            continue
        schema = SCHEMAS.get(cell["alpha_id"])
        selections = (cell.get("notes") or {}).get("deployed_selections") or {}
        for arm, record in (cell.get("arms") or {}).items():
            if record.get("status") != "RUN":
                continue
            delays = record.get("switch_delays") or {}
            requested += record.get("switches_requested") or 0
            effected += record.get("switches_effected") or 0
            bars_by_version = record.get("bars_by_parameter_version") or {}
            if bars_by_version:
                dwell.append(max(bars_by_version.values()))
            rows.append({
                "cell": f"{cell['alpha_id']}/{cell['symbol']}", "arm": arm,
                "activation_delay_bars_total": delays.get("blocked_bars_total"),
                "activation_delay_bars_max": delays.get("max_blocked_bars"),
                "refused_switches": len(delays.get("never_effected", [])),
                "longest_run_on_one_version_bars": max(bars_by_version.values())
                if bars_by_version else None,
            })
            chain = selections.get(arm) or []
            for previous, current in zip(chain, chain[1:]):
                repeats["cutoff_pairs"] += 1
                if previous.get("point_id") == current.get("point_id"):
                    repeats["same_point_as_previous_cutoff"] += 1
                if schema and previous.get("params") and current.get("params"):
                    turnovers.append(float(schema.distance(previous["params"],
                                                           current["params"])))
    novelty = support_novelty["per_symbol"]
    unknown = sum(v.get("quality_status_counts", {}).get("UNKNOWN_STATE", 0)
                  for v in novelty.values() if v.get("status") == "MEASURED")
    emissions = sum(v.get("emissions", 0) for v in novelty.values()
                    if v.get("status") == "MEASURED")
    return {
        "anchored_on": ("transitions the model DETECTED, which is what a deployment acts on. "
                        "Nothing here is anchored on a retrospective true start, which is only "
                        "knowable after the fact (guide 11.4)"),
        "activation_delay": {
            "arms": len(rows),
            "total_blocked_bars": sum(r["activation_delay_bars_total"] or 0 for r in rows),
            "max_blocked_bars": max((r["activation_delay_bars_max"] or 0 for r in rows),
                                    default=0),
        },
        "transition_turnover": {
            "parameter_moves_measured": len(turnovers),
            "mean_schema_distance": float(np.mean(turnovers)) if turnovers else None,
            "max_schema_distance": float(max(turnovers)) if turnovers else None,
            "units": "the selector's own schema distance, the same metric it uses to decide",
        },
        "avoided_or_refused_switches": {
            "requested": requested, "effected": effected, "refused": requested - effected,
            "reading": ("a requested version that never took effect is the flat-book or warm-up "
                        "gate holding it, not a lost trade")},
        "stale_incumbent": {
            "longest_run_on_one_version_bars": max(dwell) if dwell else None,
            "median_longest_run_bars": float(np.median(dwell)) if dwell else None,
            "note": ("each arm deploys its versions contiguously, so the bars on a version ARE "
                     "its dwell")},
        "unknown_and_fallback_usage": {
            "unknown_state_emissions": unknown,
            "emissions": emissions,
            "share": (unknown / emissions) if emissions else None},
        "parameter_rank_stability": {
            **repeats,
            "share_unchanged": (repeats["same_point_as_previous_cutoff"]
                                / repeats["cutoff_pairs"]) if repeats["cutoff_pairs"] else None,
            "reading": ("how often the selector re-chose the same point at the next cutoff. A "
                        "selector that never repeats is chasing noise; one that always repeats "
                        "is not selecting")},
        "wrong_switch_loss": {
            "status": "NOT_MEASURED_AT_SWITCH_LEVEL",
            "why": ("a per-switch loss needs a counterfactual account that held the incumbent "
                    "through that switch and nothing else, which is one extra engine pass per "
                    "switch"),
            "what_stands_in": ("the arm-level contrasts. C-A and D-B already answer the same "
                               "question in aggregate: whether switching on the regime beat not "
                               "switching on it"),
            "not_reported_as_zero": True},
        "per_arm": rows[:40],
    }


def attribution_panel(confirmation: dict) -> dict:
    """L09.5.7 — is any advantage attributable to TIMING rather than to selection?

    Reads only the registered contrasts. C-A is the timing contribution with the
    old selector, B-A the selector contribution on the old calendar, and the
    interaction asks whether timing adds more to the new selector than to the
    old. Attribution here is arithmetic, not narrative.
    """
    pooled: dict[str, list[float]] = {}
    for cell in confirmation.get("cells", []):
        if cell.get("status") != "RUN":
            continue
        for name, record in (cell.get("contrasts") or {}).items():
            value = record.get("mean_daily_difference", record.get("value"))
            if value is not None:
                pooled.setdefault(name, []).append(float(value))
    means = {name: float(np.mean(values)) for name, values in pooled.items()}
    timing, selection = means.get("C-A"), means.get("B-A")
    return {
        "pooled_mean_daily_difference": means,
        "cells_per_contrast": {name: len(values) for name, values in pooled.items()},
        "timing_contribution": timing,
        "selection_contribution": selection,
        "timing_larger_than_selection": (None if timing is None or selection is None
                                         else abs(timing) > abs(selection)),
        "interaction": means.get("(D-C)-(B-A)"),
        "reading": ("C-A isolates WHEN the parameters were refreshed, holding the selector "
                    "fixed. B-A isolates WHICH parameters, holding the calendar fixed. A "
                    "time-edge claim needs C-A, not the sum"),
    }


def main() -> int:
    policy_cfg = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy_cfg.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy_cfg, study_id=STUDY_ID)

    confirmation = load("lab09_confirmation_results.json")
    if confirmation is None:
        print("BLOCKED: run scripts/run_lab09_confirmation.py first (L09.2)")
        return 1
    stress = load("lab09_stress.json")
    ledger = load("lab09_policy_decision_ledger.json")
    banks = load("lab09_policy_bank_registry.json")
    spec = load("lab09_policy_policy_spec.json")

    permutation = {"status": "NOT_RUN", "reason": "configs/lab09_stress.json is missing"}
    if stress:
        checks = [entry["stresses"].get("LABEL_PERMUTATION", {})
                  for entry in stress["information_stress"]["per_cell"]]
        ran = [c for c in checks if c.get("status") == "CONTROL"]
        permutation = {
            "status": "CHECKED" if ran else "NOT_APPLICABLE",
            "cells_checked": len(ran),
            "schedules_identical": sum(1 for c in ran
                                       if c.get("schedule_identical_to_arm_D")),
            "all_identical": bool(ran) and all(c.get("schedule_identical_to_arm_D")
                                               for c in ran),
            "where": "configs/lab09_stress.json information_stress LABEL_PERMUTATION",
            "reading": ("the refresh schedule is built from WHERE the state changes. Permuting "
                        "the ids after a refit must leave it identical; a difference would mean "
                        "a decision reads the integer"),
        }

    policy_measured = (policy_panel(ledger, banks, spec) if ledger
                       else {"status": "NOT_RUN",
                             "reason": ("scripts/run_response_policy.py --role confirmation has "
                                        "not been run, so the three policy situations are "
                                        "UNCHECKED rather than absent")})

    novelty = novelty_panel()
    document = {
        "schema": "crypto_regime_lab.lab09_support.v1",
        "generated_at_utc": utc_now_iso(),
        "window": confirmation["window"],
        "situations": {
            "NEW_REGIME_EPISODE": novelty,
            "MIXED_AMBIGUOUS_STATES": ambiguity_panel(),
            "STATE_LABEL_PERMUTATION_AFTER_REFIT": permutation,
            "POLICY_ON_THE_CONFIRMATION_INTERVAL": policy_measured,
            "CAMPAIGN_NOT_FLAT": campaign_panel(confirmation),
        },
        "time_edge_attribution": attribution_panel(confirmation),
        "transition_diagnostics": transition_diagnostics(confirmation, novelty),
        "unchecked_is_not_absent": ("every situation above reports MEASURED/CHECKED or a reason. "
                                    "A situation that did not occur is a finding; one that was "
                                    "not looked for is a gap, and the two are never merged"),
    }
    with writer.attempt("L09.5.support_novelty") as att:
        att.detail = {"situations": len(document["situations"])}
    writer.write_config("lab09_support.json", document)
    writer.write_json("lab09_support.json", document, schema=document["schema"])

    print(f"new regime episode   : exercised={novelty['a_new_episode_was_exercised']}, "
          f"{novelty['symbols_with_more_novelty_than_development']}/"
          f"{novelty['symbols_measured']} symbols more novel than development")
    ambiguity = document["situations"]["MIXED_AMBIGUOUS_STATES"]
    print(f"ambiguous states     : "
          f"{ambiguity['symbols_more_ambiguous_than_development']}/"
          f"{ambiguity['symbols_measured']} symbols more ambiguous than development")
    print(f"label permutation    : {permutation['status']} "
          f"all_identical={permutation.get('all_identical')}")
    if policy_measured.get("status") == "NOT_RUN":
        print(f"policy paths         : NOT_RUN — {policy_measured['reason']}")
    else:
        print(f"policy paths         : {policy_measured['decisions']} decisions "
              f"{policy_measured['decision_counts']}")
        print(f"  bank staleness     : {policy_measured['bank']['staleness_at_interval_end']}")
    campaign = document["situations"]["CAMPAIGN_NOT_FLAT"]
    print(f"campaign not flat    : {campaign['status']}, "
          f"{campaign['arms_with_a_delayed_switch']}/{campaign['arms_run']} arms delayed; "
          f"waited for an open campaign: "
          f"{campaign['switches_that_waited_for_an_open_campaign']} switches, for warm "
          f"indicators: {campaign['switches_that_waited_for_warm_indicators']}")
    attribution = document["time_edge_attribution"]
    print(f"attribution          : timing(C-A)={attribution['timing_contribution']}, "
          f"selection(B-A)={attribution['selection_contribution']}")
    diagnostics = document["transition_diagnostics"]
    print(f"transition diag      : refused={diagnostics['avoided_or_refused_switches']['refused']}"
          f"/{diagnostics['avoided_or_refused_switches']['requested']}, "
          f"turnover mean={diagnostics['transition_turnover']['mean_schema_distance']}, "
          f"rank stability={diagnostics['parameter_rank_stability']['share_unchanged']}, "
          f"unknown share={diagnostics['unknown_and_fallback_usage']['share']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
