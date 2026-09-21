"""RA07.5/RA07.6: bootstrap statistics and support/power reporting on STORED
outcomes only -- zero engine calls anywhere in this module (guide [S4]).

Consumes only already-committed `equity_daily` series (from RA-05's cell 1
and this phase's cell 2 real runs); every function here is pure numpy/stdlib
over data the caller already has in memory or on disk.
"""
from __future__ import annotations

from .ra07_stats_primitives import (
    bootstrap_paired_delta, holm_adjust, paired_daily_returns,
)

#: guide 13.6: named here only as a REFERENCE point, never claimed as proof
#: of power ("Default old support floors ... chi la floors, khong chung
#: minh power").
LEGACY_FLOOR_DAYS = 365
LEGACY_FLOOR_BLOCKS = 12


def _equity_daily(arm_outcome: dict) -> list:
    if not arm_outcome.get("ok"):
        return []
    return (arm_outcome.get("run", {}).get("account") or {}).get("equity_daily") or []


def classify_claim(*, ci, delta, support_ok: bool, technically_valid: bool) -> dict:
    """guide 13.5's claim-gate table, applied literally: validity first,
    then support, then CI-vs-delta. INCONCLUSIVE_EFFECT (not "no edge") when
    the interval still straddles delta."""
    if not technically_valid:
        return {"status": "NOT_EVALUABLE", "labels": ["NOT_EVALUABLE"]}
    if not support_ok:
        return {"status": "INCONCLUSIVE_SUPPORT", "labels": ["INCONCLUSIVE_SUPPORT"],
               "note": "descriptive numbers may still be reported; no economic verdict"}
    low, high = ci
    if delta is None:
        return {"status": "INCONCLUSIVE_SUPPORT", "labels": ["INCONCLUSIVE_SUPPORT"],
               "note": "delta could not be materialized; economic hurdle claim is blocked"}
    if low > delta:
        return {"status": "POSITIVE_WITHIN_SCOPE", "labels": ["POSITIVE_WITHIN_SCOPE"]}
    if high < delta:
        labels = ["NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE"]
        if high < 0:
            labels.append("UNDERPERFORMED_WITHIN_SCOPE")
        return {"status": labels[-1], "labels": labels}
    return {"status": "INCONCLUSIVE_EFFECT", "labels": ["INCONCLUSIVE_EFFECT"]}


def build_contrast(*, name: str, arm_a_outcome: dict, arm_b_outcome: dict, delta,
                   block_length: int, n_resamples: int, seed: int,
                   sensitivity_block_lengths: tuple = ()) -> dict:
    """One named contrast (A minus B): paired daily returns on common dates,
    primary-block-length bootstrap, plus (if requested) sensitivity draws at
    OTHER pre-registered block lengths, ALL reported together (guide 13.4:
    'tat ca cung luc, khong chon cai significant')."""
    equity_a, equity_b = _equity_daily(arm_a_outcome), _equity_daily(arm_b_outcome)
    if not equity_a or not equity_b:
        return {"contrast": name, "status": "NOT_EVALUABLE",
               "reason": "one or both arms did not produce a real equity_daily series",
               "claim": {"status": "NOT_EVALUABLE", "labels": ["NOT_EVALUABLE"]}}
    rows = paired_daily_returns(equity_a, equity_b)
    primary = bootstrap_paired_delta(rows, block_length=block_length, n_resamples=n_resamples,
                                     seed=seed)
    if primary["status"] != "OK":
        return {"contrast": name, "status": primary["status"], "n_common_days": len(rows),
               "claim": {"status": "NOT_EVALUABLE", "labels": ["NOT_EVALUABLE"]}}
    n_blocks = len(rows) // block_length
    support_ok = n_blocks >= LEGACY_FLOOR_BLOCKS and len(rows) >= LEGACY_FLOOR_DAYS
    claim = classify_claim(ci=primary["ci_95"], delta=delta, support_ok=support_ok,
                           technically_valid=True)
    sensitivity = {}
    for alt_len in sensitivity_block_lengths:
        alt = bootstrap_paired_delta(rows, block_length=alt_len, n_resamples=n_resamples, seed=seed)
        sensitivity[str(alt_len)] = {"ci_95": alt.get("ci_95"), "point_estimate": alt.get("point_estimate")}
    return {
        "contrast": name, "status": "OK", "n_common_days": len(rows),
        "n_blocks_at_primary_length": n_blocks,
        "support_floor_check": {"legacy_floor_days": LEGACY_FLOOR_DAYS,
                                "legacy_floor_blocks": LEGACY_FLOOR_BLOCKS,
                                "meets_legacy_floor": support_ok,
                                "note": "a floor met/unmet is not proof of power either way (guide 13.6)"},
        "bootstrap": primary, "block_length_sensitivity": sensitivity,
        "delta_used": delta, "claim": claim,
    }


def build_uncertainty_results(*, cell1_arms: dict, cell2_arms: dict, delta,
                              bootstrap_plan: dict) -> dict:
    block_length = bootstrap_plan["block_length_days_primary"]
    sensitivity_lengths = tuple(bootstrap_plan["block_length_days_sensitivity"])
    n_resamples = bootstrap_plan["n_resamples"]
    seed = bootstrap_plan["seed"]

    def run(name, arms, a, b):
        if a not in arms or b not in arms:
            return {"contrast": name, "status": "NOT_EVALUABLE", "reason": f"{a} or {b} did not run",
                   "claim": {"status": "NOT_EVALUABLE", "labels": ["NOT_EVALUABLE"]}}
        return build_contrast(name=name, arm_a_outcome=arms[a], arm_b_outcome=arms[b], delta=delta,
                              block_length=block_length, n_resamples=n_resamples, seed=seed,
                              sensitivity_block_lengths=sensitivity_lengths)

    primary = run("cell1: M4_REGIME - M4_CAL_MATCHED", cell1_arms, "M4_REGIME", "M4_CAL_MATCHED")
    secondary = {
        "cell1: M4_REGIME - M4_CAL": run("cell1: M4_REGIME - M4_CAL", cell1_arms, "M4_REGIME", "M4_CAL"),
        "cell1: M4_CAL_MATCHED - M4_CAL": run("cell1: M4_CAL_MATCHED - M4_CAL", cell1_arms,
                                              "M4_CAL_MATCHED", "M4_CAL"),
        "cell2: M4_REGIME - M4_CAL_MATCHED": run("cell2: M4_REGIME - M4_CAL_MATCHED", cell2_arms,
                                                 "M4_REGIME", "M4_CAL_MATCHED"),
    }
    return {
        "schema": "regime_lab.ra07_uncertainty_results.v1",
        "no_engine_calls": True,
        "bootstrap_plan_used": {"block_length_days_primary": block_length,
                                "n_resamples": n_resamples, "seed": seed},
        "primary": primary, "secondary": secondary,
    }


def build_multiplicity_ledger(uncertainty_results: dict) -> dict:
    """Holm over the SECONDARY family only (guide 13.4: the primary is a
    single pre-registered hypothesis, never itself multiplicity-adjusted)."""
    secondary = uncertainty_results["secondary"]
    raw_p = {name: row["bootstrap"]["p_value_two_sided"]
            for name, row in secondary.items() if row.get("status") == "OK"}
    adjusted = holm_adjust(raw_p) if raw_p else {}
    return {
        "schema": "regime_lab.ra07_multiplicity_ledger.v1",
        "primary_unadjusted": {
            "name": uncertainty_results["primary"].get("contrast"),
            "p_value": (uncertainty_results["primary"].get("bootstrap") or {}).get("p_value_two_sided"),
            "adjustment": "NONE (single pre-registered primary hypothesis, guide 13.4)",
        },
        "secondary_family_holm": {
            name: {"raw_p": raw_p.get(name), "holm_adjusted_p": adjusted.get(name)}
            for name in secondary
        },
        "method": "Holm step-down, standard",
        "not_evaluable_excluded_from_family": [name for name, row in secondary.items()
                                               if row.get("status") != "OK"],
    }


def build_support_report(*, uncertainty_results: dict, cell1_meta: dict, cell2_meta: dict) -> dict:
    """guide RA07.6: days, distinct blocks, mature action labels, parameter
    versions and recurrent episodes reported SEPARATELY, never collapsed
    into one pass/fail number."""
    def row_support(row):
        if row.get("status") != "OK":
            return {"n_common_days": row.get("n_common_days", 0), "n_blocks": 0, "status": row["status"]}
        return {"n_common_days": row["n_common_days"], "n_blocks": row["n_blocks_at_primary_length"],
                "status": "OK"}

    all_rows = {"primary": uncertainty_results["primary"], **uncertainty_results["secondary"]}
    return {
        "schema": "regime_lab.ra07_support_report.v1",
        "per_contrast": {name: row_support(row) for name, row in all_rows.items()},
        "parameter_versions": {"cell1_unique_selections": cell1_meta.get("unique_selections"),
                               "cell2_unique_selections": cell2_meta.get("unique_selections")},
        "recurrent_episodes": {"cell1_switches_admitted": cell1_meta.get("switches_admitted"),
                               "cell2_switches_admitted": cell2_meta.get("switches_admitted")},
        "legacy_floor_reference": {"days": LEGACY_FLOOR_DAYS, "blocks": LEGACY_FLOOR_BLOCKS,
                                   "note": "named for orientation only, not proof of power (guide 13.6)"},
        "honest_summary": ("both cells run a ~90-day phase-owned pilot window (~3 blocks of 28 "
                          "days at the primary bootstrap block length); every contrast in this "
                          "phase falls well short of the legacy 12-block/365-day floor, so "
                          "INCONCLUSIVE_SUPPORT is the expected, not a surprising, outcome here."),
    }
