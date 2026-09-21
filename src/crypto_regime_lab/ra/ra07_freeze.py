"""RA07.1: freeze the replication spec BEFORE any RA-07 outcome exists
(guide section 11 -- "Primary study, selection rule, risk caps, MDE,
bootstrap, seed schedule va cell expansion deu co registry truoc outcomes
RA-07").

Every number this module produces is computed from RA-05's ALREADY-REAL,
ALREADY-COMMITTED cell-1 evidence (ra05-20260918T201236Z-de11db62) -- no new
engine call. That is deliberate: guide 13.3 requires delta to be
"materialized tu training-only calibration + actual engine traces", and
RA-05's own fills/equity ARE that trace; using them to freeze delta/MDE
before RA-07's own paired outcomes exist is exactly the ordering the guide
requires (freeze first, then look at RA-07's own numbers).
"""
from __future__ import annotations

import pandas as pd

from .ra07_stats_primitives import bootstrap_paired_delta

DELTA_C = 0.0005  # guide 13.3's registered cost-uncertainty increment
Z_TWO_SIDED_95_POWER_80 = 2.8  # z_(1-alpha/2) + z_(1-beta), alpha=0.05, beta=0.20
BOOTSTRAP_BLOCK_LENGTH_DAYS_PRIMARY = 28
BOOTSTRAP_BLOCK_LENGTH_SENSITIVITY = (7, 14, 56)
BOOTSTRAP_N_RESAMPLES = 5000
BOOTSTRAP_SEED = 20260919
PRIMARY_SEED = 20260918  # RA-05's DEFAULT_SEED, already spent
REPLICATION_SEEDS_REGISTERED_NOT_RUN = (20260919, 20260920)
DELAYED_CONTROL_OBSERVATIONS = 1  # one 4h-cadence observation tick, guide RA07.3 point 3
PLACEBO_CONTROL_SEED = 20260921
PLACEBO_FIDELITY_TOLERANCE = 0.35  # experiments.controls.placebo_fidelity's own default


def _equity_before(equity_daily: list, day: pd.Timestamp):
    """The closing equity mark strictly before `day` -- the calibration
    formula's E_{j-} for any fill that occurred on `day`. Falls back to the
    series' own first mark (the account's initial capital) when `day` is
    the very first day in the series, which has no preceding mark."""
    ordered = sorted(((pd.Timestamp(d), float(v)) for d, v in equity_daily), key=lambda r: r[0])
    before = [v for d, v in ordered if d < day]
    if before:
        return before[-1]
    return ordered[0][1] if ordered else None


def materialize_delta(*, fills: list, equity_daily: list, frame_index: pd.DatetimeIndex,
                      account_capital: float) -> dict:
    """guide 13.3: delta_c = mean_{d in calibration} sum_{j in d} (|N_j|/E_{j-}) * delta_c.

    N_j is the fill's real notional (qty * price); E_{j-} is the real
    pre-fill equity, approximated at DAILY granularity (the finest grain
    `equity_daily` carries) as the previous day's closing mark -- disclosed
    here rather than silently assumed. Calibration days include days with
    ZERO fills at zero contribution (guide: "giu flat calibration days"),
    never dropped from the mean's denominator.
    """
    if not fills:
        return {"status": "NO_CALIBRATION_FILLS", "delta": None}
    by_day: dict = {}
    for fill in fills:
        bar_index = fill.get("bar_index")
        if bar_index is None or bar_index >= len(frame_index):
            continue
        day = pd.Timestamp(frame_index[bar_index]).normalize()
        notional = abs(float(fill.get("qty", 0.0)) * float(fill.get("price", 0.0)))
        by_day.setdefault(day, []).append(notional)
    if not by_day:
        return {"status": "NO_FILLS_MAPPED_TO_CALIBRATION_DAYS", "delta": None}
    equity_days = sorted({pd.Timestamp(d).normalize() for d, _ in equity_daily})
    day_contributions = []
    skipped_zero_equity = 0
    for day in equity_days:
        e_pre = _equity_before(equity_daily, day) or account_capital
        if e_pre == 0:
            skipped_zero_equity += 1
            continue
        notionals = by_day.get(day, [])
        contribution = sum((n / e_pre) * DELTA_C for n in notionals)
        day_contributions.append(contribution)
    if not day_contributions:
        return {"status": "NO_VALID_CALIBRATION_DAYS", "delta": None}
    delta = sum(day_contributions) / len(day_contributions)
    return {
        "status": "OK", "delta": delta, "delta_c_increment": DELTA_C,
        "calibration_days": len(day_contributions), "days_with_fills": len(by_day),
        "skipped_zero_equity_days": skipped_zero_equity,
        "method": ("mean over calibration days of sum_j(|N_j|/E_j-)*delta_c; E_j- approximated "
                  "at daily granularity as the previous day's closing equity mark (equity_daily "
                  "has no intraday resolution); flat days with 0 fills contribute 0 and are kept "
                  "in the denominator"),
    }


def estimate_mde(paired_rows: list, *, block_length: int = BOOTSTRAP_BLOCK_LENGTH_DAYS_PRIMARY,
                 n_resamples: int = BOOTSTRAP_N_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> dict:
    """guide 13.6: MDE from the PAIRED OUTCOME VARIABILITY of development
    (never a synthetic-noise scale-by-delta trick). MDE = z * bootstrap_SE
    of the primary estimator, z=2.8 for a two-sided 5% test at 80% power --
    both the formula and the z constant stated so the number can be
    checked, not just trusted."""
    if len(paired_rows) < 2:
        return {"status": "INSUFFICIENT_PAIRED_DAYS", "mde": None, "n_common_days": len(paired_rows)}
    boot = bootstrap_paired_delta(paired_rows, block_length=block_length,
                                  n_resamples=n_resamples, seed=seed)
    if boot["status"] != "OK":
        return {"status": boot["status"], "mde": None}
    mde = Z_TWO_SIDED_95_POWER_80 * boot["bootstrap_se"]
    return {
        "status": "OK", "mde": mde, "bootstrap_se_used": boot["bootstrap_se"],
        "z_factor": Z_TWO_SIDED_95_POWER_80,
        "formula": "MDE = z * bootstrap_SE(Delta-hat), z = z_(1-alpha/2) + z_(1-beta), alpha=0.05, beta=0.20",
        "source_block_length_days": block_length, "source_n_resamples": n_resamples,
        "source_seed": seed, "source_n_common_days": len(paired_rows),
    }


def build_replication_spec(*, ra05_run_id: str, cell1: dict, cell2_plan: dict,
                           delta_result: dict, mde_result: dict,
                           rf05_mde_reference_bps: float = 0.0371) -> dict:
    """Freeze every RA07.1-required registration field in one artifact,
    written BEFORE cell-2 or any control/decay/bootstrap RA-07 outcome
    exists. Reuses RA-01's already-registered contrasts/risk-caps verbatim
    rather than re-deciding them (guide 4.2: reuse an established registered
    decision)."""
    return {
        "schema": "regime_lab.ra07_replication_spec.v1",
        "primary_contrast": "M4_REGIME - M4_CAL_MATCHED (information timing only; RA-01 H-BUDGET)",
        "action_aware_contrast": {
            "applicable": False,
            "reason": ("RA-06's G06-SCOPE lock decision was KEEP_BASELINE (support=5 below the "
                      "registered floor min_required=8); no AGE_CONTEXT policy revision was "
                      "locked, so there is no action-aware policy for RA-07 to close a separate "
                      "AGE_CONTEXT-AGE_ONLY contrast against (guide RA07.1's own conditional: "
                      "'neu RA-06 action-aware duoc chon'; it was not)."),
        },
        "secondary_contrasts": ["M4_REGIME - M4_CAL (secondary_timing_incl_cadence)",
                                "M4_CAL_MATCHED - M4_CAL (secondary_cadence)",
                                "cell2: M4_REGIME - M4_CAL_MATCHED (cross-symbol transfer check)"],
        "development_source": {"ra05_run_id": ra05_run_id, "cell": "A-SC/BTCUSDT",
                               "note": "cell-1 development evidence, reused for freeze inputs only"},
        "delta_economic_threshold": delta_result,
        "mde": mde_result,
        "mde_cross_reference": {
            "rf05_corrected_daily_account_bps": rf05_mde_reference_bps,
            "note": ("RF-04/RF-05's own frozen MDE (corrective_mode4_v3, a DIFFERENT contract: "
                    "window 2021-01-01..2022-06-30, train_memory_days=180, seed=20260911) -- "
                    "reported here only as a directional cross-reference, never substituted for "
                    "RA-07's own development-variability MDE above (different window/trials/seed, "
                    "not the same contract)."),
        },
        "risk_caps": {
            "max_drawdown_deterioration_vs_comparator": 0.02, "leverage_sizing": "same as comparator",
            "source": "RA-01 registration.json, reused verbatim, never changed after seeing outcomes",
        },
        "bootstrap_plan": {
            "method": "circular moving block bootstrap, percentile CI",
            "block_length_days_primary": BOOTSTRAP_BLOCK_LENGTH_DAYS_PRIMARY,
            "block_length_days_sensitivity": list(BOOTSTRAP_BLOCK_LENGTH_SENSITIVITY),
            "n_resamples": BOOTSTRAP_N_RESAMPLES, "seed": BOOTSTRAP_SEED,
            "same_block_indices_for_paired_arms": True,
            "recompute_per_resample": ["Delta_hat", "Sharpe_a", "Sharpe_b", "PF_a", "PF_b"],
            "engine_calls_during_bootstrap": 0,
            "pooled_aggregate": {
                "computed": False,
                "reason": ("only 2 of 20 planned cells run this phase; guide RA07.2: 'Full20 "
                          "aggregate chi khi du planned cells hoac da freeze mot partial-scope "
                          "aggregate khac truoc outcomes' -- no partial-scope capital-weighted "
                          "aggregate is registered here, so cell1 and cell2 are reported as "
                          "SEPARATE paired comparisons, never averaged or capital-weighted "
                          "together."),
            },
        },
        "seed_schedule": {
            "primary_seed": PRIMARY_SEED,
            "primary_seed_status": "ALREADY_SPENT_AT_DISCOVERY (RA-05)",
            "registered_replication_seeds": list(REPLICATION_SEEDS_REGISTERED_NOT_RUN),
            "registered_replication_seeds_status": "NOT_RUN_BUDGET",
            "not_run_budget_reason": ("budget this phase is spent on: cell-2 (cross-symbol "
                                      "transfer), the mandatory placebo-timing and "
                                      "delayed-information controls, and D1/D2/D3 decay -- "
                                      "re-running cell 1 under 2 more seeds is disclosed as "
                                      "skipped, not silently dropped. Seeds are search-randomness "
                                      "replication, never independent market samples (guide "
                                      "RA07.1), and no seed is ever chosen post-hoc as a "
                                      "headline."),
        },
        "cell_expansion_plan": cell2_plan,
        "controls_plan": {
            "order": ["CALENDAR_BUDGET_MATCHED", "AGE_ONLY", "DELAYED_INFORMATION",
                     "PLACEBO_TIMING", "RISK_EXPOSURE_ATTRIBUTION"],
            "CALENDAR_BUDGET_MATCHED": {"status": "ALREADY_AVAILABLE",
                                        "source": "RA-05 M4_CAL_MATCHED arm, both cells"},
            "AGE_ONLY": {"status": "NOT_APPLICABLE",
                        "reason": "RA-06 locked KEEP_BASELINE; no action-aware policy exists to "
                                  "contrast against AGE_ONLY"},
            "DELAYED_INFORMATION": {
                "status": "PLANNED", "scope": "cell 1 only (A-SC/BTCUSDT)",
                "delay_observations": DELAYED_CONTROL_OBSERVATIONS,
                "rule": ("state_id/state_namespace/state_common all shifted back by "
                        f"{DELAYED_CONTROL_OBSERVATIONS} observation(s); available_at and every "
                        "other field stay real -- the delay is on availability, never on the "
                        "world (guide RA07.3 point 3)"),
            },
            "PLACEBO_TIMING": {
                "status": "PLANNED", "scope": "cell 1 only (A-SC/BTCUSDT)",
                "seed": PLACEBO_CONTROL_SEED, "fidelity_tolerance": PLACEBO_FIDELITY_TOLERANCE,
                "dwell_profile_source": ("development-prefix real state_common sequence, disjoint "
                                        "from the evaluation window -- the SAME prefix rule "
                                        "forecast_cal_matched_test_days uses, never the "
                                        "evaluation window's own realized sequence"),
                "rule": ("seeded synthetic state labels reproducing the development profile's "
                        "dwell/switch-rate statistics only, laid onto the REAL observation "
                        "timestamp grid (observation cadence is not market information); no "
                        "future market data read; not a circular shift of the real future tape "
                        "(guide RA07.3 point 4)"),
            },
            "RISK_EXPOSURE_ATTRIBUTION": {
                "status": "PLANNED", "scope": "both cells, from actual real fill/equity paths",
            },
        },
        "multiplicity_family": {
            "primary_one_hypothesis": "cell1: M4_REGIME - M4_CAL_MATCHED",
            "secondary_family_holm": ["cell1: M4_REGIME - M4_CAL", "cell1: M4_CAL_MATCHED - M4_CAL",
                                      "cell2: M4_REGIME - M4_CAL_MATCHED"],
            "note": "family fixed here, before any RA-07 p-value is computed (guide 13.4)",
        },
        "frozen_before_outcomes": True,
    }
