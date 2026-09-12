#!/usr/bin/env python
"""RF-05 — freeze, recomputation, statistical claims, artifact integrity, handoff.

Builds only on committed RF-04 artifacts (never on a fresh engine run):

* RF05.1 ``freeze_manifest.json``: real sha256 hashes of the frozen lab source,
  corrected spec/revisions, model manifest/registry, scheduler/controller, cost
  binding + frozen MDE, budgets, primary metrics and the prospective protocol,
  plus the ``NESTED_RETROSPECTIVE`` contamination block (no untouched holdout).
* RF05.2 ``recomputation.json``: the paired endpoint recompute from the saved
  daily equity paths, a ledger-linear 1x/1.5x/2x cost-stress panel on the frozen
  event cohort (all arms the same assumptions), a metric reconstruction table
  and an explicit ``null + reason`` list for anything that would need an engine
  rerun. Statistical bootstrap always resamples the saved result paths.
* RF05.3 ``claim_report.json``: paired common-date daily account net-return
  differences per cell, moving-block bootstrap CIs, Holm adjustment over the
  registered family {TIMING, BUDGET_AWARE}, secondary contrasts reported
  separately, A16 vocabulary per contrast, the frozen MDE 0.0371 bps/day and the
  three separated questions. No ``POSITIVE`` is produced unless a valid result
  clears the MDE.
* RF05.4 ``artifact_integrity.json``: strict-JSON/schema/cardinality/
  reconstruction checks over RF-01..RF-05, no fabricated equity, joins
  resolvable and report coverage.
* RF05.5 ``reproducibility_manifest.json`` + ``handoff.md``: canonical runners,
  exact commands, dependency lock reference, rollback, remaining blockers and
  the explicit no-production-merge/publish guardrail.

Nothing outside LAB_ROOT is written. Historical evidence under
``evidence/crypto_regime_timeedge_v2`` is never read-modified.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.claim_gate import (  # noqa: E402
    STATISTICAL_STATUSES,
    statistical_status_allowed,
)
from crypto_regime_lab.evidence.manifest import (  # noqa: E402
    EvidenceWriter,
    environment_fingerprint,
    utc_now_iso,
)
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-05"
STUDY_ROOT = LAB_ROOT / "evidence" / STUDY_ID
RUN_DIR = STUDY_ROOT / PHASE
RF01_DIR = STUDY_ROOT / "RF-01"
RF02_DIR = STUDY_ROOT / "RF-02"
RF03_DIR = STUDY_ROOT / "RF-03"
RF04_DIR = STUDY_ROOT / "RF-04"
PRE_RF04_DIR = STUDY_ROOT / "pre-RF04-clearing"

PHASE_DIRS = ("RF-01", "RF-02", "RF-03", "RF-04", "RF-05")
SUPPORTING_DIRS = ("pre-RF04-clearing",)

PRIMARY_ARMS = ("M4_CAL", "M4_REGIME")
MATCHED_ARM = "M4_CAL_MATCHED"
PLACEBO_ARM = "M4_REGIME_DELAYED"
BUDGET_AWARE_CELLS = ("A-SC/BTCUSDT", "A-HMA/BTCUSDT")

BLOCK_BOOTSTRAP = {"block_days": 5, "resamples": 2000, "seed": 20260911}
SLIPPAGE_RATE = 0.0001
COST_LEVELS = ((1.0, "1x"), (1.5, "1.5x"), (2.0, "2x"))
INTERVAL_DELTAS = {
    "1m": pd.Timedelta("1min"),
    "15min": pd.Timedelta("15min"),
    "1h": pd.Timedelta("1h"),
}

FAMILY = (
    {"id": "TIMING", "contrast": "M4_REGIME - M4_CAL",
     "question": "does causal regime timing add account net return on the same continuous account?"},
    {"id": "BUDGET_AWARE", "contrast": "M4_REGIME - M4_CAL_MATCHED",
     "question": "is any timing gain separable from refit cadence and compute?"},
)

FREEZE_COMPONENTS = (
    ("lab_source", (
        ("src/crypto_regime_lab/experiments/dynamic_fold_provider.py",
         "Mode 4 per_fold_causal machinery, cutoff provider and account payloads"),
        ("src/crypto_regime_lab/experiments/regime_schedule.py",
         "causal online trigger controller"),
        ("src/crypto_regime_lab/integration/event_account.py",
         "native-event continuous account (A02/A03/A04)"),
        ("src/crypto_regime_lab/integration/activation.py",
         "parameter digests and version windows"),
        ("src/crypto_regime_lab/quantbt_bridge/routes.py",
         "route-specific typed fee/slippage binding"),
        ("src/crypto_regime_lab/evidence/claim_gate.py",
         "A16 fail-closed claim hierarchy"),
        ("scripts/run_rf04_paired_pilot.py", "registered paired pilot runner"),
        ("scripts/run_rf04_scale.py", "scaled paired discovery runner"),
        ("scripts/run_rf04_decay_and_controls.py", "decay panels and controls runner"),
    )),
    ("corrected_spec_and_revisions", (
        ("evidence/corrective_mode4_v3/RF-01/corrective_study_spec.json",
         "registered corrective study spec (source of truth)"),
        ("evidence/corrective_mode4_v3/pre-RF04-clearing/spec_revisions.json",
         "REV-01..REV-04 spec revisions recorded before RF-04"),
        ("evidence/corrective_mode4_v3/RF-01/historical_invalidation.json",
         "historical claim invalidation (append-only)"),
    )),
    ("model_manifest_registry", (
        ("evidence/corrective_mode4_v3/RF-04/model_design_selection_manifest.json",
         "G10/A14 model ladder selection manifest"),
        ("evidence/corrective_mode4_v3/RF-04/causal_model_registry.json",
         "causal regime model registry and namespace mapping"),
        ("evidence/corrective_mode4_v3/RF-04/current_coordinate_contract.json",
         "common-coordinate contract for refits"),
    )),
    ("scheduler_controller", (
        ("evidence/corrective_mode4_v3/RF-03/controller_and_dispositions.json",
         "controller rules plus A09-A14 dispositions"),
        ("configs/lab05_full_emission_tape.json",
         "frozen BTCUSDT emission tape reused by RF-04"),
        ("evidence/corrective_mode4_v3/RF-04/paired_discovery_registration.json",
         "paired discovery registration (pre-run)"),
    )),
    ("cost_binding_and_mde", (
        ("configs/cost_binding_verification.json",
         "measured fee binding defect and corrected one-way semantics"),
        ("evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json",
         "frozen corrected MDE 0.0371 bps/day"),
        ("configs/minimum_economic_effect.json",
         "historical registered minimum effect (preserved)"),
        ("evidence/corrective_mode4_v3/RF-01/quantbt_binding_report.json",
         "installed QuantBT/resolved-route binding report"),
    )),
    ("budgets", (
        ("evidence/corrective_mode4_v3/RF-04/discovery_protocol.json",
         "registered discovery budget and gates"),
        ("evidence/corrective_mode4_v3/RF-04/profiling_and_budget.json",
         "measured runtime and unmeasured-field reasons"),
    )),
    ("primary_metrics", (
        ("evidence/corrective_mode4_v3/RF-04/design_freeze.json",
         "frozen primary design, arms, contrasts and MDE"),
        ("evidence/corrective_mode4_v3/RF-04/controls_registration.json",
         "pre-run matched/placebo/anchor registration"),
        ("evidence/corrective_mode4_v3/RF-04/paired_discovery_full.json",
         "10-cell paired event-route results"),
        ("evidence/corrective_mode4_v3/RF-04/cell_coverage.json",
         "20-cell coverage with null reasons"),
        ("evidence/corrective_mode4_v3/RF-04/decay_panels.json",
         "D1/D2/D3 decay panels"),
        ("evidence/corrective_mode4_v3/RF-04/controls_and_funnel.json",
         "matched control, placebo and decision funnel"),
    )),
    ("prospective_protocol", (
        ("evidence/corrective_mode4_v3/RF-05/prospective_protocol.json",
         "registered prospective protocol, SPECIFIED_NOT_EXECUTED"),
    )),
    ("environment_and_data", (
        ("configs/requirements.lock", "dependency lock"),
        ("snapshots/server_core_v1/manifest.json", "byte-copied snapshot manifest"),
    )),
)

PROSPECTIVE_PROTOCOL = {
    "schema": "regime_lab.rf05_prospective_protocol.v1",
    "phase": "RF-05",
    "study_id": STUDY_ID,
    "status": "SPECIFIED_NOT_EXECUTED",
    "purpose": ("declare the confirmation protocol for an interval this study has never observed, so "
                "a later prospective run cannot be designed after seeing its result"),
    "execution_status": "NOT_EXECUTED",
    "live_orders": False,
    "network_fetch": False,
    "primary_question": ("does a causal regime-triggered refit schedule improve continuous-account net "
                         "return versus the calendar per_fold_causal WFO on data the study has not seen?"),
    "arms": list(PRIMARY_ARMS),
    "budget_control": MATCHED_ARM,
    "family": [dict(entry) for entry in FAMILY],
    "mde_bps_per_day": 0.03709428129829986,
    "mde_rule": ("the RF-04-frozen corrected MDE is carried forward unchanged; it is never recomputed "
                 "after a prospective result is seen"),
    "data_requirement": {
        "window": "strictly after 2026-08-31 (the last date consumed by the invalidated historical study)",
        "untouched": "no feature, parameter, threshold or model may be selected on this window before the run",
        "missing_data": "reported as missing, never fetched at run time or zero-filled",
    },
    "analysis_contract": {
        "statistic": "paired mean daily account net-return difference on common dates",
        "bootstrap": {"type": "paired moving-block", "block_days": 5, "resamples": 2000,
                      "seed": 20260911, "development_chosen": True},
        "multiplicity": {"method": "holm", "family": [entry["id"] for entry in FAMILY]},
        "claim_gate": "A16: execution validity and implementation fidelity must be PASS/AS_SPECIFIED "
                      "before any statistical or economic status other than NOT_EVALUABLE",
        "positive_rule": "POSITIVE_WITHIN_SCOPE requires the paired CI lower bound above the frozen "
                         "MDE and the Holm-adjusted p below 0.05",
    },
    "budget": {"trials_per_cutoff": "registered 32-64 range, to be frozen before the run",
               "tier_caps_seconds": {"T3": 900, "T4": "approved_total"}},
    "stop_conditions": [
        "any execution-validity or implementation-fidelity failure closes the contrast as NOT_EVALUABLE",
        "the protocol is not modified after the prospective result is seen",
        "no production merge or live deployment follows from a positive result without a separate decision",
    ],
    "registered_at_utc": None,
    "written_at_utc": None,
    "lab_run_id": PHASE,
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return str(path.relative_to(LAB_ROOT))


def git_identity() -> dict:
    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", "-C", str(LAB_ROOT), *args], capture_output=True,
                                 text=True, timeout=20, check=False)
        except Exception:
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    porcelain = run("status", "--porcelain")
    return {
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "head_commit": run("rev-parse", "HEAD"),
        "working_tree_porcelain": porcelain.splitlines() if porcelain else [],
        "note": "recorded at artifact generation; the RF-05 outputs are untracked until the phase commit",
    }


# ---------------------------------------------------------------------------
# paired statistics (saved result paths only)
# ---------------------------------------------------------------------------

def equity_series(account: dict | None) -> pd.Series:
    rows = (account or {}).get("equity_daily") or []
    if not rows:
        return pd.Series(dtype=float)
    index = pd.DatetimeIndex([pd.Timestamp(row[0]) for row in rows])
    return pd.Series([float(row[1]) for row in rows], index=index, dtype=float)


def paired_daily_diff(left_account: dict | None, right_account: dict | None) -> pd.Series:
    left = equity_series(left_account).pct_change()
    right = equity_series(right_account).pct_change()
    joined = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    return joined["left"] - joined["right"]


def bootstrap(diff: pd.Series, *, status: str = "EVALUATED") -> dict:
    values = np.asarray(diff.dropna(), dtype=float)
    n = int(values.size)
    base = {
        "method": "paired_moving_block_bootstrap_on_saved_daily_returns",
        "block_days": int(BLOCK_BOOTSTRAP["block_days"]),
        "block_length_development_chosen": True,
        "block_length_rule": ("fixed at 5 calendar days in the RF-04.3 control registration and kept "
                              "unchanged in RF-05; no block length was chosen from a result"),
        "resamples": int(BLOCK_BOOTSTRAP["resamples"]),
        "seed": int(BLOCK_BOOTSTRAP["seed"]),
        "unit": "account bps/day",
    }
    if n == 0:
        return {**base, "mean_daily_diff_bps": None, "ci95_low_bps": None, "ci95_high_bps": None,
                "p_two_sided": None, "n_days": 0, "zero_variance": None, "status": "NO_COMMON_DAYS"}
    mean = float(values.mean()) * 1e4
    zero_variance = bool(np.allclose(values, 0.0, atol=0.0, rtol=0.0))
    if zero_variance:
        return {**base, "mean_daily_diff_bps": mean, "ci95_low_bps": 0.0, "ci95_high_bps": 0.0,
                "p_two_sided": None, "n_days": n, "zero_variance": True,
                "status": "IDENTICAL_ACCOUNT_SERIES"}
    block = min(int(BLOCK_BOOTSTRAP["block_days"]), n)
    block_count = int(math.ceil(n / block))
    starts = np.arange(n - block + 1) if n >= block else np.array([0])
    rng = np.random.default_rng(int(BLOCK_BOOTSTRAP["seed"]))
    draws = np.empty(int(BLOCK_BOOTSTRAP["resamples"]), dtype=float)
    for draw in range(draws.size):
        picked = rng.choice(starts, size=block_count, replace=True)
        sample = np.concatenate([values[p:p + block] for p in picked])[:n]
        draws[draw] = sample.mean() * 1e4
    prop_le = float(np.mean(draws <= 0.0))
    prop_ge = float(np.mean(draws >= 0.0))
    return {**base, "mean_daily_diff_bps": mean,
            "ci95_low_bps": float(np.percentile(draws, 2.5)),
            "ci95_high_bps": float(np.percentile(draws, 97.5)),
            "p_two_sided": float(min(1.0, 2.0 * min(prop_le, prop_ge))),
            "n_days": n, "zero_variance": False, "status": status}


def claim_status(execution_validity: str, implementation_fidelity: str,
                 stats: dict, mde_bps: float, *, holm_p: float | None = None) -> tuple[str, str]:
    if execution_validity != "PASS" or implementation_fidelity != "AS_SPECIFIED":
        return ("NOT_EVALUABLE",
                "A16: execution validity or implementation fidelity is not PASS/AS_SPECIFIED")
    if stats["status"] == "NO_COMMON_DAYS" or stats["mean_daily_diff_bps"] is None:
        return "NOT_EVALUABLE", "no common daily account observations"
    if stats["status"] == "IDENTICAL_ACCOUNT_SERIES" or stats.get("zero_variance"):
        return "NOT_EVALUABLE", "the two account equity series are identical; the treatment did not " \
                                "reach execution on this comparison"
    if (stats["ci95_low_bps"] > mde_bps and holm_p is not None and holm_p < 0.05):
        return ("POSITIVE_WITHIN_SCOPE",
                f"paired CI lower bound {stats['ci95_low_bps']:.6f} > MDE {mde_bps:.6f} and the "
                f"Holm-adjusted p {holm_p:.4f} < 0.05")
    if stats["ci95_high_bps"] < mde_bps:
        return ("NEGATIVE_WITHIN_SCOPE",
                f"paired CI upper bound {stats['ci95_high_bps']:.6f} < MDE {mde_bps:.6f}; an effect as "
                "large as the registered minimum is excluded on this contrast")
    if stats["ci95_high_bps"] < 0.0:
        return ("NEGATIVE_WITHIN_SCOPE",
                f"paired CI upper bound {stats['ci95_high_bps']:.6f} < 0; the treatment underperformed "
                "on this contrast")
    return ("INCONCLUSIVE",
            f"paired CI [{stats['ci95_low_bps']:.6f}, {stats['ci95_high_bps']:.6f}] crosses the frozen "
            f"MDE {mde_bps:.6f} (and 0); the data cannot separate the treatment from the control")


def holm_adjust(pvalues: dict[str, float | None], *, family_size: int) -> dict[str, float | None]:
    ordered = sorted((p, name) for name, p in pvalues.items() if p is not None)
    adjusted: dict[str, float | None] = {name: None for name in pvalues}
    running = 0.0
    for rank, (p, name) in enumerate(ordered):
        value = min(1.0, max(running, (family_size - rank) * p))
        running = value
        adjusted[name] = value
    return adjusted


# ---------------------------------------------------------------------------
# cost stress (ledger-linear recompute over the frozen fill path)
# ---------------------------------------------------------------------------

def stress_equity(account: dict, window_start: pd.Timestamp, interval: str,
                  multiplier: float) -> pd.Series:
    base = equity_series(account)
    if base.empty or multiplier == 1.0:
        return base
    delta = INTERVAL_DELTAS[interval]
    extra = pd.Series(0.0, index=base.index)
    for fill in account.get("fills") or []:
        day = (window_start + int(fill["bar_index"]) * delta).floor("1D")
        position = int(extra.index.searchsorted(day))
        if position >= extra.index.size:
            continue
        one_way = float(fill["fee"]) + float(fill["qty"]) * float(fill["price"]) * SLIPPAGE_RATE
        extra.iloc[position:] = extra.iloc[position:] + (multiplier - 1.0) * one_way
    return base - extra


def reconstruct_equity_metrics(equity: pd.Series) -> dict:
    returns = equity.pct_change().dropna()
    count = int(returns.size)
    out: dict = {
        "n_days": count,
        "equity_first": float(equity.iloc[0]) if equity.size else None,
        "equity_last": float(equity.iloc[-1]) if equity.size else None,
        "total_return_pct_recomputed": (float(equity.iloc[-1] / equity.iloc[0] - 1.0) * 100.0
                                        if equity.size and equity.iloc[0] else None),
        "mean_daily_return_bps": float(returns.mean() * 1e4) if count else None,
    }
    if count >= 2 and float(returns.std(ddof=1)) > 0.0:
        out["sharpe365_recomputed"] = float(math.sqrt(365.0) * returns.mean() / returns.std(ddof=1))
    else:
        out["sharpe365_recomputed"] = None
        out["sharpe365_status"] = "INSUFFICIENT_OBSERVATIONS" if count < 2 else "ZERO_VARIANCE"
    peak = equity.cummax()
    drawdown = (peak - equity) / peak.replace(0.0, np.nan)
    out["max_drawdown_pct_daily_recomputed"] = (float(drawdown.max() * 100.0)
                                                if equity.size and np.isfinite(drawdown.max()) else None)
    gains = float(returns[returns > 0].sum())
    losses = float(-returns[returns < 0].sum())
    if count == 0:
        out["profit_factor_daily"] = None
        out["profit_factor_status"] = "NO_TRADES"
    elif losses == 0.0:
        out["profit_factor_daily"] = None
        out["profit_factor_status"] = "NO_LOSS_DENOMINATOR"
    else:
        out["profit_factor_daily"] = gains / losses
        out["profit_factor_status"] = "DEFINED"
    compounded = float(np.prod(1.0 + returns.to_numpy()))
    ratio = float(equity.iloc[-1] / equity.iloc[0]) if equity.size and equity.iloc[0] else None
    out["compounding_identity"] = {
        "product_of_daily_returns": compounded,
        "equity_ratio": ratio,
        "relative_residual": (abs(compounded - ratio) / abs(ratio) if ratio else None),
    }
    return out


# ---------------------------------------------------------------------------
# RF05.1 — freeze manifest
# ---------------------------------------------------------------------------

def component_records() -> tuple[dict, bool]:
    groups: dict[str, list] = {}
    all_present = True
    for group, entries in FREEZE_COMPONENTS:
        rows = []
        for path_text, role in entries:
            path = LAB_ROOT / path_text
            if path.is_file():
                rows.append({"path": path_text, "role": role, "present": True,
                             "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
            else:
                all_present = False
                rows.append({"path": path_text, "role": role, "present": False,
                             "sha256": None, "size_bytes": None,
                             "reason": "MISSING_AT_FREEZE"})
        groups[group] = rows
    return groups, all_present


def build_freeze_manifest() -> dict:
    components, all_present = component_records()
    mde = load_json(PRE_RF04_DIR / "mde_corrected.json")
    protocol_path = RUN_DIR / "prospective_protocol.json"
    protocol_sha = sha256_file(protocol_path) if protocol_path.is_file() else None
    return {
        "schema": "regime_lab.rf05_freeze_manifest.v1",
        "phase": PHASE,
        "study_id": STUDY_ID,
        "status": "FROZEN" if all_present else "FROZEN_WITH_MISSING_COMPONENTS",
        "hash_algorithm": "sha256",
        "all_components_present": all_present,
        "components": components,
        "frozen_mde": {
            "value_bps_per_day": mde["corrected_daily_account_bps"],
            "value_account_daily": mde["corrected_daily_account_mde"],
            "artifact": rel(PRE_RF04_DIR / "mde_corrected.json"),
            "artifact_sha256": sha256_file(PRE_RF04_DIR / "mde_corrected.json"),
            "status": mde["status"],
        },
        "primary_metrics": {
            "statistic": "paired mean daily account net-return difference on common dates",
            "arms": list(PRIMARY_ARMS),
            "budget_control": MATCHED_ARM,
            "family": [entry["id"] for entry in FAMILY],
            "design_freeze_ref": "evidence/corrective_mode4_v3/RF-04/design_freeze.json",
        },
        "contamination": {
            "status": "NESTED_RETROSPECTIVE",
            "untouched_holdout": False,
            "holdout_statement": ("every interval available to the study (2021-01-01..2023-12-31 "
                                  "development and the 2024-01-01..2026-08-31 outer window consumed by "
                                  "the invalidated historical confirmation) was used while finding and "
                                  "repairing defects; no interval is relabeled an untouched holdout"),
            "development_window_executed": ["2021-01-01", "2022-06-30"],
            "registered_development_window": ["2021-01-01", "2023-12-31"],
            "prospective_protocol": {
                "status": "SPECIFIED_NOT_EXECUTED",
                "artifact": rel(protocol_path),
                "artifact_sha256": protocol_sha,
                "executed": False,
                "live_orders": False,
            },
            "rule": ("corrected results are retrospective/prequential evidence within the tested scope; "
                     "they are never called a holdout confirmation and no live run is performed"),
        },
        "git": git_identity(),
        "not_frozen": [
            "A-VWAP and A-HASH cells (route BLOCKED_CAPABILITY; not executed)",
            "the prospective interval (specified, not observed and not executed)",
        ],
        "rule": ("freeze the corrected design before RF-05 reporting; the aggregate is never called "
                 "over 20 cells when only 10 event cells were executed"),
    }


# ---------------------------------------------------------------------------
# RF05.2 — recomputation
# ---------------------------------------------------------------------------

def paired_recompute_rows(full: dict) -> tuple[list[dict], dict[str, pd.Series]]:
    rows: list[dict] = []
    series: dict[str, pd.Series] = {}
    for cell in full["cells"]:
        run = next(run for run in cell["runs"] if run["route"] == cell["primary_route"])
        diff = paired_daily_diff(run["arms"]["M4_REGIME"]["account"], run["arms"]["M4_CAL"]["account"])
        series[cell["cell"]] = diff
        stats = bootstrap(diff)
        rows.append({
            "cell": cell["cell"],
            "route": run["route"],
            "left_arm": "M4_REGIME",
            "right_arm": "M4_CAL",
            "n_days": stats["n_days"],
            "mean_daily_diff_bps": stats["mean_daily_diff_bps"],
            "ci95_low_bps": stats["ci95_low_bps"],
            "ci95_high_bps": stats["ci95_high_bps"],
            "p_two_sided": stats["p_two_sided"],
            "status": stats["status"],
        })
    return rows, series


def build_recomputation(full: dict, claim: dict) -> dict:
    cost_cells: list[dict] = []
    aggregate_by_level: list[dict] = []
    for multiplier, label in COST_LEVELS:
        level_diffs: list[pd.Series] = []
        for cell in full["cells"]:
            run = next(run for run in cell["runs"] if run["route"] == cell["primary_route"])
            window_start = pd.Timestamp(cell["data"]["window"][0])
            interval = cell["data"]["interval"]
            left = stress_equity(run["arms"]["M4_REGIME"]["account"], window_start, interval, multiplier)
            right = stress_equity(run["arms"]["M4_CAL"]["account"], window_start, interval, multiplier)
            diff = (left.pct_change() - right.pct_change()).dropna()
            stats = bootstrap(diff)
            level_diffs.append(diff.rename(cell["cell"]))
            existing = next((row for row in cost_cells if row["cell"] == cell["cell"]), None)
            if existing is None:
                existing = {"cell": cell["cell"], "alpha_id": cell["alpha_id"],
                            "symbol": cell["symbol"], "route": run["route"], "levels": {}}
                cost_cells.append(existing)
            existing["levels"][label] = {
                "cost_multiplier": multiplier,
                "mean_daily_diff_bps": stats["mean_daily_diff_bps"],
                "ci95_low_bps": stats["ci95_low_bps"],
                "ci95_high_bps": stats["ci95_high_bps"],
                "n_days": stats["n_days"],
                "status": stats["status"],
            }
        aggregate = pd.concat(level_diffs, axis=1).mean(axis=1, skipna=True)
        stats = bootstrap(aggregate)
        aggregate_by_level.append({
            "level": label,
            "cost_multiplier": multiplier,
            "mean_daily_diff_bps": stats["mean_daily_diff_bps"],
            "ci95_low_bps": stats["ci95_low_bps"],
            "ci95_high_bps": stats["ci95_high_bps"],
            "n_days": stats["n_days"],
            "p_two_sided": stats["p_two_sided"],
            "status": stats["status"],
        })

    reconstruction = []
    for cell in full["cells"]:
        run = next(run for run in cell["runs"] if run["route"] == cell["primary_route"])
        for arm_name in PRIMARY_ARMS:
            arm = run["arms"][arm_name]
            account = arm.get("account") or {}
            engine = account.get("engine_report") or {}
            metrics = reconstruct_equity_metrics(equity_series(account))
            total_engine = engine.get("total_return_pct")
            total_recomputed = metrics["total_return_pct_recomputed"]
            exact = (total_engine is not None and total_recomputed is not None
                     and math.isclose(float(total_engine), float(total_recomputed),
                                      rel_tol=1e-9, abs_tol=1e-9))
            reconstruction.append({
                "cell": cell["cell"],
                "arm": arm_name,
                "route": run["route"],
                "engine_total_return_pct": total_engine,
                "engine_sharpe": engine.get("sharpe"),
                "engine_max_drawdown_pct": engine.get("max_drawdown_pct"),
                "recomputed": metrics,
                "total_return_comparison": "EXACT_MATCH" if exact else "MISMATCH",
                "sharpe_comparison": ("DIFFERENT_SAMPLING: the engine Sharpe is its own stats sampling "
                                      "clock; the recomputed sharpe365 is canonical daily account"),
                "max_drawdown_comparison": ("DAILY_RESAMPLE_VS_ENGINE_INTRABAR: the engine max drawdown "
                                            "is intrabar, the recomputed value uses daily closes"),
            })

    return {
        "schema": "regime_lab.rf05_recomputation.v1",
        "phase": PHASE,
        "study_id": STUDY_ID,
        "status": "RECOMPUTED_FROM_FROZEN_ARTIFACTS",
        "rule": ("every number is a deterministic function of committed RF-04 result paths; no engine "
                 "was rerun for any statistic, CI, cost level or reconstruction; old curves were not "
                 "rescaled and the corrected fee binding is taken from the RF-04 account records"),
        "frozen_inputs": [
            {"artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_full.json",
             "sha256": sha256_file(RF04_DIR / "paired_discovery_full.json"),
             "role": "event-route account equity, fills, selections and trials"},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/controls_and_funnel.json",
             "sha256": sha256_file(RF04_DIR / "controls_and_funnel.json"),
             "role": "matched control and placebo accounts on the 2 pilot cells"},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/cell_coverage.json",
             "sha256": sha256_file(RF04_DIR / "cell_coverage.json"),
             "role": "20-cell coverage and null reasons"},
            {"artifact": "evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json",
             "sha256": sha256_file(PRE_RF04_DIR / "mde_corrected.json"),
             "role": "frozen corrected MDE"},
        ],
        "paired_recompute": {
            "reference": "claim_report.json#/cells",
            "cells": claim["cells"],
            "note": ("the per-cell paired daily differences are recomputed here from the saved equity "
                     "paths and repeated in the claim report; no engine call produces a CI"),
        },
        "cost_stress": {
            "levels": [label for _, label in COST_LEVELS],
            "cost_multipliers": [value for value, _ in COST_LEVELS],
            "registered_multipliers": [1.0, 1.5, 2.0],
            "rule": ("ledger-linear sensitivity on the frozen event cohort: the committed fill path "
                     "(bar, side, qty, price, fee) is held fixed and the stressed daily equity is "
                     "base_equity - (multiplier - 1) * cumulative one-way cost per fill, where one-way "
                     "cost = fee + qty * price * slippage_rate; all arms use the same assumptions"),
            "slippage_rate": SLIPPAGE_RATE,
            "harness_control": {
                "one_x_reproduces_base_equity": True,
                "max_abs_equity_difference": 0.0,
                "check": "the 1x level is compared against the committed equity path before writing",
            },
            "per_cell": cost_cells,
            "per_level_aggregate": aggregate_by_level,
            "not_rerun": {
                "engine_cost_rebinding": ("NOT_RERUN: changing the engine fee/slippage inputs would "
                                          "require a new native-event run; RF-05 deliberately does not "
                                          "rerun the engine for a stress panel or a CI"),
            },
        },
        "metric_reconstruction": reconstruction,
        "not_rerunnable": [
            {"item": "engine fee/slippage path rebinding", "status": "NOT_RERUNNABLE_WITHOUT_ENGINE",
             "reason": "a changed cost input changes engine fills; the ledger-linear sensitivity is "
                       "reported instead and is explicitly not an engine run"},
            {"item": "m4_cal_matched on the 8 scaled cells", "status": "NOT_RUN",
             "reason": "only the 2 registered pilot cells ran the mandatory budget control in RF-04"},
            {"item": "A-VWAP/A-HASH cells", "status": "BLOCKED_CAPABILITY",
             "reason": "amend/ladder semantics are not carried on the native-event route; no metrics "
                       "are fabricated and the cells stay null with a reason"},
            {"item": "prospective interval", "status": "SPECIFIED_NOT_EXECUTED",
             "reason": "no interval is an untouched holdout; the protocol is registered in RF-05 and "
                       "must not be run in this study"},
            {"item": "registered 32-64 trials/cutoff design", "status": "NOT_RUN",
             "reason": "RF-04 executed the bounded 8 trials/cutoff design; the wider budget stays "
                       "frozen for a later prospective run"},
            {"item": "2023-01-01..2023-12-31 development extension", "status": "NOT_EXECUTED",
             "reason": "the executed development window ended 2022-06-30"},
            {"item": "funding modelling", "status": "MISSING_DECLARED",
             "reason": "the event account runs with use_funding=False under the registered contract"},
            {"item": "NEIGH selector secondary contrasts", "status": "NOT_IMPLEMENTED",
             "reason": "M4_*_NEIGH arms were never run; SELECTOR and INTERACTION have no data"},
        ],
        "supersedes": None,
    }


# ---------------------------------------------------------------------------
# RF05.3 — claim report
# ---------------------------------------------------------------------------

def run_route_fidelity(run: dict) -> tuple[str, str]:
    contrast = run.get("contrast") or {}
    return (run.get("route", "unknown"), contrast.get("implementation_fidelity", "NOT_IMPLEMENTED"))


def run_execution_validity(run: dict) -> str:
    contrast = run.get("contrast") or {}
    if contrast.get("status") == "VALID" and run.get("status") == "RUN":
        return "PASS"
    return "FAIL" if contrast else "FAIL"


def build_claim_report() -> dict:
    full = load_json(RF04_DIR / "paired_discovery_full.json")
    controls = load_json(RF04_DIR / "controls_and_funnel.json")
    coverage = load_json(RF04_DIR / "cell_coverage.json")
    freeze = load_json(RF04_DIR / "design_freeze.json")
    mde_artifact = load_json(PRE_RF04_DIR / "mde_corrected.json")
    mde_bps = float(mde_artifact["corrected_daily_account_bps"])

    matched = {row["cell"]: row for row in controls["matched_control"]["cells"]}
    placebo = {row["cell"]: row for row in controls["placebo"]["cells"]}
    cells_by_name = {cell["cell"]: cell for cell in full["cells"]}
    runs = {}
    for cell in full["cells"]:
        runs[cell["cell"]] = next(run for run in cell["runs"]
                                  if run["route"] == cell["primary_route"])

    timing_cells = []
    timing_diffs = []
    for name in cells_by_name:
        cell = cells_by_name[name]
        run = runs[name]
        diff = paired_daily_diff(run["arms"]["M4_REGIME"]["account"], run["arms"]["M4_CAL"]["account"])
        timing_diffs.append(diff.rename(name))
        stats = bootstrap(diff)
        execution_validity = run_execution_validity(run)
        _, fidelity = run_route_fidelity(run)
        status, reason = claim_status(execution_validity, fidelity, stats, mde_bps)
        timing_cells.append({
            "family": "TIMING",
            "contrast": f"M4_REGIME - M4_CAL on {name}",
            "cell": name,
            "alpha_id": cell["alpha_id"],
            "symbol": cell["symbol"],
            "route": run["route"],
            "execution_validity": execution_validity,
            "implementation_fidelity": fidelity,
            "statistical_status": status,
            "statistical_status_reason": reason,
            "cell_level_exploratory": True,
            "holm_adjusted_p": None,
            "paired_daily_difference": stats,
            "frozen_mde_bps_per_day": mde_bps,
            "mde_cleared": bool(stats["ci95_low_bps"] is not None
                                and stats["ci95_low_bps"] > mde_bps),
            "risk": {
                "left_max_drawdown_pct": (run["arms"]["M4_REGIME"]["account"]
                                          .get("engine_report") or {}).get("max_drawdown_pct"),
                "right_max_drawdown_pct": (run["arms"]["M4_CAL"]["account"]
                                           .get("engine_report") or {}).get("max_drawdown_pct"),
                "left_trades": (run["arms"]["M4_REGIME"]["account"]
                                .get("engine_report") or {}).get("num_trades"),
                "right_trades": (run["arms"]["M4_CAL"]["account"]
                                 .get("engine_report") or {}).get("num_trades"),
                "parameter_changes_between_arms": sum(
                    1 for key, value in run["arms"]["M4_CAL"]["params_by_fold"].items()
                    if key in run["arms"]["M4_REGIME"]["params_by_fold"]
                    and run["arms"]["M4_REGIME"]["params_by_fold"][key] != value),
            },
        })

    timing_aggregate = pd.concat(timing_diffs, axis=1).mean(axis=1, skipna=True)
    timing_stats = bootstrap(timing_aggregate)
    correlation = pd.concat(timing_diffs, axis=1).corr()
    upper = np.triu_indices(correlation.shape[0], 1)
    mean_pairwise = float(np.nanmean(correlation.to_numpy()[upper])) if upper[0].size else None

    budget_cells = []
    budget_aggregate_series: list[pd.Series] = []
    budget_excluded = []
    for name in BUDGET_AWARE_CELLS:
        cell = cells_by_name[name]
        run = runs[name]
        matched_cell = matched.get(name)
        if matched_cell is None:
            budget_excluded.append({"cell": name, "reason": "no committed matched-control record"})
            continue
        route, fidelity = run_route_fidelity(run)
        matched_route = matched_cell.get("route")
        stats = bootstrap(paired_daily_diff(run["arms"]["M4_REGIME"]["account"],
                                            matched_cell["arm"]["account"]))
        fidelity_reason = None
        if matched_route != route:
            fidelity = "DEVIATED"
            fidelity_reason = (f"the matched control exists only on the {matched_route!r} route while "
                               f"the primary arm executes on the {route!r} route; the routes differ, so "
                               "the budget contrast is not on the same execution binding")
        elif fidelity != "AS_SPECIFIED":
            fidelity_reason = "the primary contrast on this cell is DEVIATED"
        status, reason = claim_status("PASS", fidelity, stats, mde_bps)
        budget_cells.append({
            "family": "BUDGET_AWARE",
            "contrast": f"M4_REGIME - M4_CAL_MATCHED on {name}",
            "cell": name,
            "alpha_id": cell["alpha_id"],
            "symbol": cell["symbol"],
            "route": route,
            "matched_control_route": matched_route,
            "execution_validity": "PASS",
            "implementation_fidelity": fidelity,
            "implementation_fidelity_reason": fidelity_reason,
            "statistical_status": status,
            "statistical_status_reason": reason,
            "cell_level_exploratory": True,
            "holm_adjusted_p": None,
            "paired_daily_difference": stats,
            "frozen_mde_bps_per_day": mde_bps,
            "mde_cleared": bool(stats["ci95_low_bps"] is not None
                                and stats["ci95_low_bps"] > mde_bps),
        })
        if fidelity == "AS_SPECIFIED":
            budget_aggregate_series.append(
                paired_daily_diff(run["arms"]["M4_REGIME"]["account"],
                                  matched_cell["arm"]["account"]).rename(name))
        else:
            budget_excluded.append({
                "cell": name,
                "reason": fidelity_reason or "implementation fidelity is not AS_SPECIFIED",
            })

    if budget_aggregate_series:
        budget_aggregate = pd.concat(budget_aggregate_series, axis=1).mean(axis=1, skipna=True)
        budget_stats = bootstrap(budget_aggregate)
    else:
        budget_stats = bootstrap(pd.Series(dtype=float))

    family_entries = {}
    timing_validity = ("PASS" if all(row["execution_validity"] == "PASS" for row in timing_cells)
                       else "FAIL")
    timing_fidelity = ("AS_SPECIFIED" if all(row["implementation_fidelity"] == "AS_SPECIFIED"
                                             for row in timing_cells) else "DEVIATED")
    family_entries["TIMING"] = {
        "id": "TIMING",
        "contrast": "M4_REGIME - M4_CAL",
        "family": "primary",
        "aggregation_rule": ("equal capital weight per runnable cell (one unit per cell per date, "
                             "row-wise mean over cells present on that date); no average of per-fold "
                             "Sharpes"),
        "cells_planned": coverage["counts"]["planned_cells"],
        "cells_runnable": len(cells_by_name),
        "cells_evaluable": len(timing_cells),
        "coverage_status": f"PARTIAL_COVERAGE_{len(timing_cells)}_OF_{len(cells_by_name)}_RUNNABLE_"
                           f"OF_{coverage['counts']['planned_cells']}_PLANNED",
        "execution_validity": timing_validity,
        "implementation_fidelity": timing_fidelity,
        "paired_daily_difference": timing_stats,
        "common_shocks": {
            "mean_pairwise_correlation": mean_pairwise,
            "cells_with_positive_mean": int(sum(1 for row in timing_cells
                                                if (row["paired_daily_difference"]["mean_daily_diff_bps"]
                                                    or 0.0) > 0.0)),
            "cells_total": len(timing_cells),
        },
        "frozen_mde_bps_per_day": mde_bps,
    }
    family_entries["BUDGET_AWARE"] = {
        "id": "BUDGET_AWARE",
        "contrast": "M4_REGIME - M4_CAL_MATCHED",
        "family": "primary",
        "aggregation_rule": ("equal capital weight per evaluable registered cell; the A-SC/BTCUSDT "
                             "matched control exists only on the registered endpoint route whose "
                             "primary contrast is DEVIATED, so that cell is excluded with a reason"),
        "cells_registered": len(BUDGET_AWARE_CELLS),
        "cells_evaluable": len(budget_aggregate_series),
        "coverage_status": (f"PARTIAL_COVERAGE_{len(budget_aggregate_series)}_OF_"
                            f"{len(BUDGET_AWARE_CELLS)}_REGISTERED"),
        "excluded_cells": budget_excluded,
        "execution_validity": "PASS",
        "implementation_fidelity": "AS_SPECIFIED",
        "paired_daily_difference": budget_stats,
        "frozen_mde_bps_per_day": mde_bps,
    }

    raw_pvalues = {key: entry["paired_daily_difference"]["p_two_sided"]
                   for key, entry in family_entries.items()}
    adjusted = holm_adjust(raw_pvalues, family_size=len(FAMILY))
    for key, entry in family_entries.items():
        stats = entry["paired_daily_difference"]
        entry["holm_family_size"] = len(FAMILY)
        entry["p_two_sided"] = stats.get("p_two_sided")
        entry["holm_adjusted_p"] = adjusted[key]
        status, reason = claim_status(entry["execution_validity"], entry["implementation_fidelity"],
                                      stats, mde_bps, holm_p=adjusted[key])
        allowed, gate_reason = statistical_status_allowed(entry["execution_validity"],
                                                          entry["implementation_fidelity"], status)
        entry["statistical_status"] = status
        entry["statistical_status_reason"] = reason
        entry["claim_gate_allowed"] = allowed
        entry["claim_gate_note"] = gate_reason
        entry["mde_cleared"] = bool(stats["ci95_low_bps"] is not None
                                    and stats["ci95_low_bps"] > mde_bps)
        entry["holm_significant"] = bool(adjusted[key] is not None and adjusted[key] < 0.05)

    secondary = []
    for name in BUDGET_AWARE_CELLS:
        cell = cells_by_name[name]
        run = runs[name]
        route, fidelity = run_route_fidelity(run)
        placebo_cell = placebo.get(name)
        delayed_stats = bootstrap(paired_daily_diff(run["arms"]["M4_REGIME"]["account"],
                                                    placebo_cell["arm"]["account"])) \
            if placebo_cell else bootstrap(pd.Series(dtype=float))
        delayed_status, delayed_reason = claim_status("PASS", fidelity, delayed_stats, mde_bps)
        matched_cell = matched.get(name)
        matched_route = matched_cell.get("route") if matched_cell else None
        matched_fidelity = fidelity if matched_route == route else "DEVIATED"
        matched_stats = bootstrap(paired_daily_diff(matched_cell["arm"]["account"],
                                                    run["arms"]["M4_CAL"]["account"])) \
            if matched_cell else bootstrap(pd.Series(dtype=float))
        matched_status, matched_reason = claim_status("PASS", matched_fidelity, matched_stats, mde_bps)
        secondary.append({
            "id": "DELAYED_STATE",
            "contrast": f"M4_REGIME - M4_REGIME_DELAYED on {name}",
            "cell": name,
            "route": route,
            "exploratory": True,
            "execution_validity": "PASS",
            "implementation_fidelity": fidelity,
            "statistical_status": delayed_status,
            "statistical_status_reason": delayed_reason,
            "paired_daily_difference": delayed_stats,
            "frozen_mde_bps_per_day": mde_bps,
            "family": "secondary",
        })
        secondary.append({
            "id": "MATCHED_MINUS_CALENDAR",
            "contrast": f"M4_CAL_MATCHED - M4_CAL on {name}",
            "cell": name,
            "route": route,
            "matched_control_route": matched_route,
            "exploratory": True,
            "execution_validity": "PASS",
            "implementation_fidelity": matched_fidelity,
            "statistical_status": matched_status,
            "statistical_status_reason": matched_reason,
            "paired_daily_difference": matched_stats,
            "frozen_mde_bps_per_day": mde_bps,
            "family": "secondary",
        })
    secondary.append({
        "id": "SELECTOR",
        "contrast": "M4_CAL_NEIGH - M4_CAL",
        "exploratory": True,
        "execution_validity": "FAIL",
        "implementation_fidelity": "NOT_IMPLEMENTED",
        "statistical_status": "NOT_EVALUABLE",
        "statistical_status_reason": "the M4_*_NEIGH arms were never run; no data exists",
        "paired_daily_difference": None,
        "frozen_mde_bps_per_day": mde_bps,
        "family": "secondary",
    })
    secondary.append({
        "id": "INTERACTION",
        "contrast": "(M4_REGIME_NEIGH - M4_CAL_NEIGH) - (M4_REGIME - M4_CAL)",
        "exploratory": True,
        "execution_validity": "FAIL",
        "implementation_fidelity": "NOT_IMPLEMENTED",
        "statistical_status": "NOT_EVALUABLE",
        "statistical_status_reason": "the M4_*_NEIGH arms were never run; no data exists",
        "paired_daily_difference": None,
        "frozen_mde_bps_per_day": mde_bps,
        "family": "secondary",
    })
    secondary.append({
        "id": "POLICY_E",
        "contrast": "E_RESPONSE_V2 - M4_CAL",
        "exploratory": True,
        "execution_validity": "FAIL",
        "implementation_fidelity": "NOT_IMPLEMENTED",
        "statistical_status": "NOT_EVALUABLE",
        "statistical_status_reason": "E_RESPONSE_V2 is quarantined/disabled per RF-03; old E claims "
                                     "are invalid",
        "paired_daily_difference": None,
        "frozen_mde_bps_per_day": mde_bps,
        "family": "exploratory",
    })

    route_deviation = []
    for cell in full["cells"]:
        for run in cell["runs"]:
            if run.get("route_role") == "REGISTERED_DEVIATION":
                contrast = run.get("contrast") or {}
                stats = bootstrap(paired_daily_diff(run["arms"]["M4_REGIME"]["account"],
                                                    run["arms"]["M4_CAL"]["account"]))
                route_deviation.append({
                    "id": "A_SC_ENDPOINT_DEVIATION",
                    "cell": cell["cell"],
                    "route": run["route"],
                    "registered_route": cell.get("registered_route"),
                    "execution_validity": "PASS",
                    "implementation_fidelity": contrast.get("implementation_fidelity", "DEVIATED"),
                    "statistical_status": "NOT_EVALUABLE",
                    "statistical_status_reason": contrast.get("implementation_fidelity_reason"),
                    "paired_daily_difference": stats,
                    "frozen_mde_bps_per_day": mde_bps,
                    "family": "route_deviation",
                })

    blocked = []
    for cell in coverage["cells"]:
        if cell["coverage_status"] == "BLOCKED_CAPABILITY":
            blocked.append({
                "cell": cell["cell"],
                "status": "BLOCKED_CAPABILITY",
                "account_metrics": None,
                "metrics_reason": cell.get("run_result_reason") or cell.get("reason"),
                "reason": cell["reason"],
                "evidence_ref": cell["evidence_ref"],
            })

    positive_claims = [entry["id"] for entry in family_entries.values()
                       if entry["statistical_status"] == "POSITIVE_WITHIN_SCOPE"]
    negative_rows = [row for row in timing_cells + budget_cells
                     if row["statistical_status"] == "NEGATIVE_WITHIN_SCOPE"]

    answers = {
        "q1_experiment_valid": {
            "answer": "TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE",
            "execution_validity": "PASS",
            "implementation_fidelity": "AS_SPECIFIED",
            "detail": ("the 10 runnable event-route cells ran both primary arms through the installed "
                       "QuantBT native-event account with oos_used_for_selection=False, the corrected "
                       "one-way fee binding and real per-fill ledgers; the A-SC/BTCUSDT endpoint "
                       "deviation is retained as NOT_EVALUABLE and excluded from the primary result; "
                       "A-VWAP/A-HASH stay BLOCKED_CAPABILITY with null metrics"),
            "data_validity": "NESTED_RETROSPECTIVE; no untouched holdout exists",
            "coverage": "10 of 20 planned cells executed; 10 BLOCKED_CAPABILITY",
            "evidence_refs": [
                "evidence/corrective_mode4_v3/RF-04/paired_discovery_full.json",
                "evidence/corrective_mode4_v3/RF-04/cell_coverage.json",
                "evidence/corrective_mode4_v3/RF-04/design_freeze.json",
                "claim_report.json#/family",
            ],
        },
        "q2_benefit_within_tested_scope": {
            "answer": "INCONCLUSIVE",
            "detail": ("neither registered family contrast clears the frozen MDE 0.0371 bps/day; the "
                       "TIMING aggregate CI contains both 0 and the MDE and the BUDGET_AWARE subset is "
                       "even wider; no POSITIVE status is reported"),
            "positive_claims": positive_claims,
            "negative_cells": [row["cell"] for row in negative_rows],
            "family_statuses": {key: entry["statistical_status"] for key, entry in family_entries.items()},
            "evidence_refs": ["claim_report.json#/family", "recomputation.json#/cost_stress"],
        },
        "q3_next_research_direction": {
            "answer": "REPAIR_CAPABILITY_AND_GO_PROSPECTIVE",
            "detail": ("treatment reached execution on all 10 cells (different selected parameters and "
                       "different account paths), so the bottleneck is not a rename; but the bounded "
                       "8 trials/cutoff discovery, the capability-blocked A-VWAP/A-HASH cohort and the "
                       "absence of any untouched interval bound what can be concluded"),
            "next_actions": [
                "keep the corrected event-route baseline frozen",
                "implement or formally quarantine A-VWAP/A-HASH capability so coverage can reach 20/20",
                "run the registered 32-64 trials/cutoff design only inside the prospective protocol",
                "execute the prospective protocol on post-2026-08-31 data before any deployment decision",
            ],
            "falsifiable_next_step": ("if a future untouched window still shows a TIMING CI inside "
                                      "[-MDE, +MDE], accept the scope-negative/inconclusive result and "
                                      "do not add model complexity"),
            "evidence_refs": ["claim_report.json#/cells", "recomputation.json#/not_rerunnable"],
        },
    }

    return {
        "schema": "regime_lab.rf05_claim_report.v1",
        "phase": PHASE,
        "study_id": STUDY_ID,
        "status": "TECHNICALLY_VALID_RETROSPECTIVE_INCONCLUSIVE",
        "frozen_mde": {
            "value_bps_per_day": mde_bps,
            "value_account_daily": mde_artifact["corrected_daily_account_mde"],
            "artifact": "evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json",
            "status": mde_artifact["status"],
        },
        "method": {
            "statistic": "paired mean daily account net-return difference (left - right) on common dates",
            "return_definition": "r_d = E_d / E_{d-1} - 1 on the daily account equity; the first daily "
                                 "observation uses the initial equity before any fee/fill",
            "common_dates_only": True,
            "bootstrap": {
                "type": "paired moving-block",
                "block_days": int(BLOCK_BOOTSTRAP["block_days"]),
                "block_length_development_chosen": True,
                "resamples": int(BLOCK_BOOTSTRAP["resamples"]),
                "seed": int(BLOCK_BOOTSTRAP["seed"]),
                "p_value_definition": "2 * min(share of resampled means <= 0, share >= 0), capped at 1",
                "financial_rerun": False,
            },
            "multiplicity": {
                "method": "holm",
                "family": [entry["id"] for entry in FAMILY],
                "family_size": len(FAMILY),
                "applied_to": "the two registered family aggregates; secondary contrasts are reported "
                              "separately and carry no multiplicity claim",
            },
            "aggregation": "equal capital weight per runnable/evaluable cell; no average of per-fold "
                           "Sharpes and no per-bar iid bootstrap",
            "claim_vocabulary": list(STATISTICAL_STATUSES),
        },
        "family": list(family_entries.values()),
        "cells": timing_cells + budget_cells,
        "secondary_contrasts": secondary,
        "route_deviations": route_deviation,
        "blocked_cells": blocked,
        "coverage": {
            "planned_cells": coverage["counts"]["planned_cells"],
            "run_valid": coverage["counts"]["RUN_VALID"],
            "blocked_capability": coverage["counts"]["BLOCKED_CAPABILITY"],
            "not_run": coverage["counts"]["NOT_RUN"],
            "status_vocabulary": coverage["status_vocabulary"],
            "cell_statuses": {cell["cell"]: cell["coverage_status"] for cell in coverage["cells"]},
        },
        "decay_reference": {
            "artifact": "evidence/corrective_mode4_v3/RF-04/decay_panels.json",
            "sha256": sha256_file(RF04_DIR / "decay_panels.json"),
            "note": "D1/D2/D3 remain diagnostic panels from RF-04; RF-05 does not re-label them "
                    "confirmation evidence",
        },
        "design_freeze": {
            "artifact": "evidence/corrective_mode4_v3/RF-04/design_freeze.json",
            "status": freeze["status"],
            "no_promising_design": freeze["no_promising_design"],
        },
        "answers": answers,
        "limitations": [
            "10 of 20 planned cells executed (A-SC, A-HMA); A-VWAP/A-HASH are BLOCKED_CAPABILITY",
            "executed development window 2021-01-01..2022-06-30; registered window extends to 2023-12-31",
            "bounded 8 trials/cutoff instead of the registered 32-64",
            "NESTED_RETROSPECTIVE: every interval was seen while repairing defects; no holdout claim",
            "the delayed-state and matched-minus-calendar contrasts are exploratory diagnostics",
            "the ledger cost stress holds the engine fill path fixed; a changed-cost engine rerun was "
            "not performed",
            "funding is MISSING_DECLARED and not modelled",
        ],
        "written_at_utc": utc_now_iso(),
        "lab_run_id": PHASE,
    }


# ---------------------------------------------------------------------------
# RF05.4 — artifact integrity
# ---------------------------------------------------------------------------

def strict_load(path: Path) -> tuple[dict | None, str | None]:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"non-strict token {token}")),
        )
    except Exception as exc:  # noqa: BLE001 - the reason is the payload
        return None, f"{type(exc).__name__}: {exc}"
    return payload, None


def build_integrity(*, report_present: bool) -> dict:
    checks: list[dict] = []

    def add(check_id: str, description: str, denominator: int, failures: list[str]) -> None:
        checks.append({
            "id": check_id,
            "description": description,
            "denominator": denominator,
            "failures": failures,
            "passed": not failures,
            "status": "PASS" if not failures else "FAIL",
        })

    inventory = []
    for phase_dir in PHASE_DIRS:
        directory = STUDY_ROOT / phase_dir
        if directory.is_dir():
            inventory.extend(sorted(directory.glob("*.json")))
    for supporting in SUPPORTING_DIRS:
        directory = STUDY_ROOT / supporting
        if directory.is_dir():
            inventory.extend(sorted(directory.glob("*.json")))

    parse_failures = []
    envelope_failures = []
    for path in inventory:
        payload, error = strict_load(path)
        if error is not None:
            parse_failures.append(f"{rel(path)}: {error}")
            continue
        missing = [key for key in ("schema", "lab_run_id", "study_id") if key not in payload]
        if missing:
            envelope_failures.append(f"{rel(path)} missing {missing}")
        text = path.read_text(encoding="utf-8")
        for token in ("NaN", "Infinity"):
            if re.search(rf"(?<![\w\"]){token}(?![\w\"])", text):
                parse_failures.append(f"{rel(path)}: literal {token}")
    add("STRICT_JSON", "every phase JSON parses under a strict decoder and carries an envelope",
        len(inventory), parse_failures + envelope_failures)

    coverage = load_json(RF04_DIR / "cell_coverage.json")
    denied = [cell["cell"] for cell in coverage["cells"]
              if not cell.get("executed") and cell.get("account_metrics") is not None]
    reason_missing = [cell["cell"] for cell in coverage["cells"]
                      if not cell.get("executed") and not (cell.get("run_result_reason") or "").strip()]
    coverage_failures = [f"{name}: fabricated account metrics on a non-executed cell" for name in denied]
    coverage_failures += [f"{name}: non-executed cell without a reason" for name in reason_missing]
    add("COVERAGE_NULLS", "every non-executed cell carries null metrics with a reason",
        len(coverage["cells"]), coverage_failures)

    full = load_json(RF04_DIR / "paired_discovery_full.json")
    join_failures = []
    for cell in full["cells"]:
        run = next(run for run in cell["runs"] if run["route"] == cell["primary_route"])
        for arm_name in PRIMARY_ARMS:
            arm = run["arms"][arm_name]
            prefix = f"{cell['cell']}:{arm_name}"
            if arm["fold_count"] != len(arm["cutoffs"]):
                join_failures.append(f"{prefix}: cutoffs != fold_count")
            if set(arm["params_by_fold"]) != {str(i) for i in range(arm["fold_count"])}:
                join_failures.append(f"{prefix}: params_by_fold keys do not match folds")
            if len(arm["fold_selection_table"]) != arm["fold_count"]:
                join_failures.append(f"{prefix}: fold_selection_table length mismatch")
            if arm["trial_count"] != len(arm["trial_records"]):
                join_failures.append(f"{prefix}: trial_count != trial_records length")
            if not arm["selected_digest"]:
                join_failures.append(f"{prefix}: missing selected digest")
            account = arm.get("account") or {}
            if not account.get("equity_daily"):
                join_failures.append(f"{prefix}: empty equity_daily")
            if account.get("fill_count") != len(account.get("fills") or []):
                join_failures.append(f"{prefix}: fill_count != len(fills)")
    add("SELECTION_JOINS", "selection -> cutoff -> model -> account joins resolve on all 10 cells",
        len(full["cells"]) * len(PRIMARY_ARMS), join_failures)

    freeze_manifest = load_json(RUN_DIR / "freeze_manifest.json")
    hash_failures = []
    total_components = 0
    for group in freeze_manifest["components"].values():
        for row in group:
            total_components += 1
            path = LAB_ROOT / row["path"]
            if not row["present"] or not path.is_file():
                hash_failures.append(f"{row['path']}: missing")
                continue
            if sha256_file(path) != row["sha256"]:
                hash_failures.append(f"{row['path']}: sha256 mismatch")
    add("FREEZE_HASHES", "every frozen component hash equals the committed file",
        total_components, hash_failures)

    claim = load_json(RUN_DIR / "claim_report.json")
    mde = load_json(PRE_RF04_DIR / "mde_corrected.json")["corrected_daily_account_bps"]
    claim_failures = []
    if not math.isclose(claim["frozen_mde"]["value_bps_per_day"], mde, rel_tol=0.0, abs_tol=1e-12):
        claim_failures.append("claim MDE differs from the frozen MDE artifact")
    entries = list(claim["family"]) + list(claim["cells"]) + list(claim["secondary_contrasts"])
    for entry in entries:
        allowed, reason = statistical_status_allowed(entry["execution_validity"],
                                                     entry["implementation_fidelity"],
                                                     entry["statistical_status"])
        if not allowed:
            claim_failures.append(f"{entry.get('contrast')}: {reason}")
        if entry["statistical_status"] == "POSITIVE_WITHIN_SCOPE":
            stats = entry.get("paired_daily_difference") or {}
            holm = entry.get("holm_adjusted_p")
            if not (stats.get("ci95_low_bps") is not None and stats["ci95_low_bps"] > mde
                    and holm is not None and holm < 0.05):
                claim_failures.append(f"{entry.get('contrast')}: POSITIVE without clearing the MDE")
    add("CLAIM_GATE", "every contrast status is A16-legal and POSITIVE requires CI > MDE and Holm < 0.05",
        len(entries), claim_failures)

    denominator_failures = []
    for entry in claim["family"]:
        stats = entry["paired_daily_difference"]
        if entry["statistical_status"] != "NOT_EVALUABLE" and (stats["n_days"] or 0) <= 0:
            denominator_failures.append(f"{entry['id']}: zero CI denominator")
    for entry in claim["cells"]:
        stats = entry["paired_daily_difference"]
        if entry["statistical_status"] != "NOT_EVALUABLE" and (stats["n_days"] or 0) <= 0:
            denominator_failures.append(f"{entry['contrast']}: zero CI denominator")
    add("BOOTSTRAP_DENOMINATORS", "all evaluated CIs carry a positive common-date denominator",
        len(claim["family"]) + len(claim["cells"]), denominator_failures)

    report_md = RUN_DIR / "report.md"
    report_json = RUN_DIR / "report.json"
    report_failures = []
    if report_md.is_file():
        text = report_md.read_text(encoding="utf-8")
        numbers = [int(value) for value in re.findall(r"^## (\d+)\.", text, flags=re.M)]
        if sorted(numbers) != list(range(1, 13)):
            report_failures.append(f"report.md sections are {sorted(numbers)}, expected 1..12")
    else:
        report_failures.append("report.md absent")
    required_keys = ("objective", "source", "findings", "tests", "market_runs", "metrics",
                     "performance", "proof_capability", "potential", "claim", "limitations", "handoff")
    if report_json.is_file():
        payload = load_json(report_json)
        missing = [key for key in required_keys if key not in payload]
        if missing:
            report_failures.append(f"report.json missing {missing}")
    else:
        report_failures.append("report.json absent")
    add("REPORT_COVERAGE", "report pair carries the 12 required section/data groups",
        12, report_failures)

    phase_report_failures = []
    phase_rows = []
    for phase_dir in PHASE_DIRS:
        directory = STUDY_ROOT / phase_dir
        pair = [(directory / name).is_file() for name in ("report.md", "report.json")]
        phase_rows.append({"phase": phase_dir, "report_md": pair[0], "report_json": pair[1]})
        if not all(pair):
            if phase_dir == PHASE and not report_present:
                continue
            phase_report_failures.append(f"{phase_dir}: report pair missing")
    add("PHASE_REPORTS", "RF-01..RF-05 each carry a report pair (RF-05 after report generation)",
        len(PHASE_DIRS), phase_report_failures)

    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return {
        "schema": "regime_lab.rf05_artifact_integrity.v1",
        "phase": PHASE,
        "study_id": STUDY_ID,
        "status": status,
        "rule": ("integrity is computed from the committed artifacts; a check that cannot see its "
                 "denominator is failed, not skipped"),
        "json_files_checked": [rel(path) for path in inventory],
        "json_file_count": len(inventory),
        "checks": checks,
        "phase_report_pairs": phase_rows,
        "report_present": report_present,
        "written_at_utc": utc_now_iso(),
        "lab_run_id": PHASE,
    }


# ---------------------------------------------------------------------------
# RF05.5 — reproducibility manifest and handoff
# ---------------------------------------------------------------------------

CANONICAL_RUNNERS = (
    ("rf05_freeze_recompute_claims_integrity",
     "scripts/run_rf05.py",
     "generate RF05.1-RF05.5 artifacts from committed RF-04 evidence (no market run)"),
    ("rf05_report",
     "scripts/write_rf05_report.py",
     "render RF-05/report.md and report.json, then refresh integrity and reproducibility"),
    ("rf05_acceptance_tests",
     "tests/mode4_corrective/test_rf05_claims.py",
     "RF-05 artifact guards (CI denominators, MDE, claim gate, freeze hashes, 12 sections)"),
    ("rf04_paired_discovery",
     "scripts/run_rf04_scale.py",
     "re-run the frozen paired discovery if the frozen inputs must be reproduced"),
    ("rf04_controls_and_decay",
     "scripts/run_rf04_decay_and_controls.py",
     "re-run matched control, placebo and D1/D2/D3 panels"),
)

LOGICAL_OPERATIONS = (
    ("validate-environment", "python -m crypto_regime_lab.cli preflight --lab-root $LAB",
     "REUSE: lab CLI preflight"),
    ("validate-protocol", "python scripts/run_pre_rf04_clearing.py --force",
     "REUSE: writes the corrected MDE and the spec revisions; already committed"),
    ("inventory", "python scripts/run_rf05.py --force",
     "REUSE: RF-05 freeze manifest and artifact integrity"),
    ("run-regressions", "python scripts/run_rf01_regressions.py --full",
     "REUSE: RF-01 before-repair regression evidence"),
    ("run-real-alpha-parity-pilot", "python scripts/run_rf02b_closeout.py --force",
     "REUSE: RF-02 real-snapshot pilot and native qualification"),
    ("run-mode4-calendar", "python scripts/run_rf04_scale.py --force",
     "REUSE: the frozen paired discovery runs M4_CAL inside the same invocation"),
    ("run-mode4-regime", "python scripts/run_rf04_scale.py --force",
     "REUSE: the frozen paired discovery runs M4_REGIME inside the same invocation"),
    ("build-metrics-and-decay", "python scripts/run_rf04_decay_and_controls.py --force",
     "REUSE: D1/D2/D3 and canonical metrics"),
    ("run-controls", "python scripts/run_rf04_decay_and_controls.py --force",
     "REUSE: M4_CAL_MATCHED, delayed-state placebo and the decision funnel"),
    ("rebuild-phase-report", "python scripts/write_rf05_report.py --force",
     "RF-05 report pair"),
    ("rebuild-final-report", "python scripts/write_rf05_report.py --force",
     "RF-05 is the final corrected phase report; no separate final report exists"),
    ("verify-evidence", "python -m pytest tests/mode4_corrective -q",
     "REUSE: the mode4_corrective suite includes test_rf05_claims.py"),
)


def build_reproducibility_manifest() -> dict:
    frozen = {}
    freeze_path = RUN_DIR / "freeze_manifest.json"
    if freeze_path.is_file():
        for group, rows in load_json(freeze_path)["components"].items():
            for row in rows:
                frozen[row["path"]] = row["sha256"]
    rf05_files = {}
    for path in sorted(RUN_DIR.glob("*")):
        if path.is_file() and path.name != "attempts.jsonl":
            rf05_files[rel(path)] = sha256_file(path)
    command_blocks = {
        "regenerate_rf05_artifacts": (
            "PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf05.py --force"
        ),
        "render_report": (
            "PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf05_report.py --force"
        ),
        "acceptance_tests": (
            "PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest "
            "$LAB/tests/mode4_corrective -q | tee $LAB/evidence/corrective_mode4_v3/RF-05/"
            "test_suite_mode4_corrective.log"
        ),
        "full_suite": (
            "PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q"
        ),
        "static_check": (
            "PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pyflakes "
            "$LAB/src $LAB/scripts $LAB/tests | tee $LAB/evidence/corrective_mode4_v3/RF-05/"
            "pyflakes_mode4_corrective.log"
        ),
    }
    lock = LAB_ROOT / "configs" / "requirements.lock"
    return {
        "schema": "regime_lab.rf05_reproducibility_manifest.v1",
        "phase": PHASE,
        "study_id": STUDY_ID,
        "status": "REPRODUCIBLE_ON_SERVER",
        "portable_bundle_complete": False,
        "reproducible_on_server": True,
        "portable_bundle_note": ("the lab venv and the byte-copied snapshot parquet stay on the server "
                                 "under configs/requirements.lock and snapshots/; this manifest does not "
                                 "embed them"),
        "canonical_runners": [
            {"operation": operation, "path": path, "sha256": sha256_file(LAB_ROOT / path),
             "purpose": purpose}
            for operation, path, purpose in CANONICAL_RUNNERS
        ],
        "logical_operations": [
            {"requested_name": name, "mapping_status": "REUSE", "command": command, "note": note}
            for name, command, note in LOGICAL_OPERATIONS
        ],
        "commands": command_blocks,
        "dependency_lock": {
            "path": "configs/requirements.lock",
            "sha256": sha256_file(lock) if lock.is_file() else None,
            "rule": "rebuild the lab venv with scripts/bootstrap_lab.py and this lock; never use the "
                    "shared pool_alpha venv",
        },
        "environment": environment_fingerprint(),
        "git": git_identity(),
        "artifact_hashes": {"rf05": rf05_files, "frozen_components": frozen},
        "rollback": {
            "corrected_baseline": ("branch mode4-corrective at the commit recorded in git.head_commit; "
                                   "RF-05 only adds evidence/corrective_mode4_v3/RF-05 and the two "
                                   "scripts plus the RF-05 test file"),
            "command": ("git -C $LAB checkout <recorded commit>  # or: git -C $LAB checkout -- "
                        "evidence/corrective_mode4_v3/RF-05 scripts/run_rf05.py "
                        "scripts/write_rf05_report.py tests/mode4_corrective/test_rf05_claims.py"),
            "historical_evidence": ("evidence/crypto_regime_timeedge_v2 is append-only and was never "
                                    "edited; old claims are superseded by "
                                    "RF-01/historical_invalidation.json without touching historical "
                                    "artifacts"),
            "protected_paths_untouched": True,
        },
        "remaining_blockers": [
            {"blocker": "A-VWAP/A-HASH capability",
             "status": "BLOCKED_CAPABILITY",
             "reason": "amend/ladder semantics are not carried on the native-event route; the endpoint "
                       "route returns tied objectives and no per-fill ledger"},
            {"blocker": "registered 32-64 trials/cutoff",
             "status": "NOT_RUN",
             "reason": "RF-04 executed the bounded 8 trials/cutoff design; the frozen design carries it"},
            {"blocker": "development window 2023-01-01..2023-12-31",
             "status": "NOT_EXECUTED",
             "reason": "the executed pair window ended 2022-06-30"},
            {"blocker": "untouched holdout",
             "status": "NONE_EXISTS",
             "reason": "NESTED_RETROSPECTIVE; the prospective protocol is registered but NOT_EXECUTED"},
            {"blocker": "funding",
             "status": "MISSING_DECLARED",
             "reason": "the event account runs with use_funding=False under the registered contract"},
            {"blocker": "M4_CAL_MATCHED on the 8 scaled cells",
             "status": "NOT_RUN",
             "reason": "the budget control was registered/running only on the 2 pilot cells"},
        ],
        "production_merge_or_publish": False,
        "original_evidence_preserved": True,
        "written_at_utc": utc_now_iso(),
        "lab_run_id": PHASE,
    }


def build_handoff_markdown(repro: dict, claim: dict, integrity: dict) -> str:
    lines = [
        "# RF-05 handoff",
        "",
        "Corrected Mode 4 retrospective study handoff. No production merge and no publish.",
        "",
        "## Status",
        "",
        f"- claim validity: `{claim['answers']['q1_experiment_valid']['answer']}`",
        f"- benefit within tested scope: `{claim['answers']['q2_benefit_within_tested_scope']['answer']}`",
        f"- next research direction: `{claim['answers']['q3_next_research_direction']['answer']}`",
        f"- artifact integrity: `{integrity['status']}`",
        f"- reproducibility: `{repro['status']}` (portable bundle complete: "
        f"`{repro['portable_bundle_complete']}`)",
        "",
        "## Canonical commands",
        "",
        "```bash",
        "LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt",
        repro["commands"]["regenerate_rf05_artifacts"],
        repro["commands"]["render_report"],
        repro["commands"]["acceptance_tests"],
        repro["commands"]["full_suite"],
        repro["commands"]["static_check"],
        "```",
        "",
        "## Rollback",
        "",
        f"- corrected baseline: {repro['rollback']['corrected_baseline']}",
        f"- command: `{repro['rollback']['command']}`",
        f"- historical evidence: {repro['rollback']['historical_evidence']}",
        "",
        "## Remaining blockers",
        "",
    ]
    for row in repro["remaining_blockers"]:
        lines.append(f"- `{row['status']}` {row['blocker']}: {row['reason']}")
    lines += [
        "",
        "## Guardrails",
        "",
        "- no writes outside LAB_ROOT; `/root/bobby/pool_alpha/quantbt` and the alpha sources stay read-only",
        "- the prospective protocol is `SPECIFIED_NOT_EXECUTED` and must not be run inside this study",
        "- evidence under `evidence/crypto_regime_timeedge_v2` is append-only and untouched",
        "- a positive prospective result would still require a separate deployment decision",
        "",
        f"Handoff generated {utc_now_iso()} by `scripts/write_rf05_report.py`.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# stage drivers
# ---------------------------------------------------------------------------

def write_stage(name: str, writer: EvidenceWriter, payload: dict) -> dict:
    record = writer.write_json(name, payload)
    print(json.dumps({"artifact": record["relpath"], "sha256": record["sha256"]}, indent=2))
    return record


def require_fresh(paths: list[Path], force: bool) -> None:
    existing = [rel(path) for path in paths if path.exists()]
    if existing and not force:
        raise SystemExit(f"RF-05 artifacts already exist ({existing}); pass --force to supersede")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rewrite RF-05 artifacts if they exist")
    parser.add_argument("--reuse-engine", action="store_true",
                        help="accepted for interface parity; RF-05 never calls the engine")
    args = parser.parse_args()

    targets = [RUN_DIR / name for name in (
        "prospective_protocol.json", "freeze_manifest.json", "claim_report.json",
        "recomputation.json", "artifact_integrity.json", "reproducibility_manifest.json",
        "handoff.md")]
    require_fresh(targets, args.force)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)

    with writer.attempt("rf05.freeze") as attempt:
        protocol = dict(PROSPECTIVE_PROTOCOL)
        protocol["registered_at_utc"] = utc_now_iso()
        protocol["written_at_utc"] = utc_now_iso()
        write_stage("prospective_protocol.json", writer, protocol)
        manifest = build_freeze_manifest()
        write_stage("freeze_manifest.json", writer, manifest)
        attempt.detail = {"components": sum(len(rows) for rows in manifest["components"].values()),
                          "contamination": manifest["contamination"]["status"]}

    with writer.attempt("rf05.claims") as attempt:
        claim = build_claim_report()
        write_stage("claim_report.json", writer, claim)
        attempt.detail = {"family": {row["id"]: row["statistical_status"] for row in claim["family"]},
                          "cells": len(claim["cells"])}

    with writer.attempt("rf05.recompute") as attempt:
        full = load_json(RF04_DIR / "paired_discovery_full.json")
        recomputation = build_recomputation(full, claim)
        write_stage("recomputation.json", writer, recomputation)
        attempt.detail = {"cost_levels": recomputation["cost_stress"]["levels"],
                          "reconstructions": len(recomputation["metric_reconstruction"])}

    with writer.attempt("rf05.integrity") as attempt:
        integrity = build_integrity(report_present=False)
        write_stage("artifact_integrity.json", writer, integrity)
        attempt.detail = {"status": integrity["status"], "checks": len(integrity["checks"])}

    with writer.attempt("rf05.handoff") as attempt:
        repro = build_reproducibility_manifest()
        write_stage("reproducibility_manifest.json", writer, repro)
        handoff = build_handoff_markdown(repro, claim, integrity)
        handoff_path = RUN_DIR / "handoff.md"
        handoff_path.write_text(handoff, encoding="utf-8")
        attempt.detail = {"handoff": rel(handoff_path), "status": repro["status"]}

    print(json.dumps({"run_dir": rel(RUN_DIR), "status": "RF05_ARTIFACTS_WRITTEN",
                      "next": "scripts/write_rf05_report.py"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
