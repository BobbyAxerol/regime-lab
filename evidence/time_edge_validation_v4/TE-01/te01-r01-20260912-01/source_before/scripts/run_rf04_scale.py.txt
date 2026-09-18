#!/usr/bin/env python
"""RF-04.6 — scale the bounded paired pilot and settle the A-SC route fidelity.

Scope (RF-04 exit: "scale theo shards tới 4 alphas x 5 symbols hoặc report actual
coverage/blockers"):

* the A-SC cells move to the RF-02-qualified native-event route, because the
  endpoint scorer returned one objective for every sampled candidate and
  exposed no per-fill ledger; the committed A-SC/BTCUSDT endpoint run stays in
  the artifact as the registered route deviation;
* the remaining eight runnable cells (A-SC and A-HMA on ETHUSDT, SOLUSDT,
  BNBUSDT, DOGEUSDT) run through the same bounded M4_CAL vs M4_REGIME pilot
  with the registered economics, development window, training memory, trial
  budget and seed policy;
* the A-HMA/BTCUSDT event run and the A-SC/BTCUSDT endpoint run are reused from
  the committed ``paired_discovery_pilot.json`` (never re-run, never rewritten);
* ``paired_discovery_full.json`` records all 10 runnable cells x both arms, and
  ``cell_coverage.json`` closes all 20 primary cells with an explicit status,
  a reason and an evidence ref.

Bounded and honest: every arm runs under a wall-clock alarm and the whole script
under a global budget. An arm that exceeds its budget is recorded as
``NOT_RUN_BUDGET`` with the exact alarm reason; a cell never reached because the
global budget is spent is recorded the same way. No metric is fabricated and no
missing cell is zero-filled. The artifact is rewritten atomically after the
invocation, so an interrupted bounded run keeps exactly the cells that ran;
``--resume`` continues from a previous partial write and ``--force`` redoes the
fresh runs from scratch.
"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

import run_rf04_paired_pilot as pilot_runner  # noqa: E402  (reuse RF-04.1 machinery)

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.experiments.dynamic_fold_provider import (  # noqa: E402
    ACCOUNT_CAPITAL,
    ALLOC_PER_TRADE,
    ONE_WAY_TAKER_FEE,
    SLIPPAGE_BPS,
    calendar_cutoffs,
    regime_cutoffs,
)
from crypto_regime_lab.quantbt_bridge.routes import bound_fee_kwargs  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "RF-04"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / RUN_ID
RF02_DIR = LAB_ROOT / "evidence" / STUDY_ID / "RF-02"
SNAPSHOT_ID = "server_core_v1"
PRODUCT = "crypto_binance_futures_1m"
DEVELOPMENT = ("2021-01-01", "2022-06-30")
TRIALS = 8
SEED = 20260911
STATUS_VOCABULARY = ("RUN_VALID", "RUN_NOT_EVALUABLE", "BLOCKED_CAPABILITY",
                     "NOT_RUN", "NOT_RUN_BUDGET", "INSUFFICIENT_DATA")
PRIMARY_ARMS = ("M4_CAL", "M4_REGIME")

REGIME_CONTROLLER = {"min_gap_days": 90.0, "max_age_days": 180.0, "budget": None}

ALPHA_ROUTES = {
    "A-SC": {
        "interval": "15min",
        "route": "event",
        "registered_route": "endpoint",
        "route_status": "QUALIFIED_FAST",
        "route_role": "FIDELITY_ROUTE",
        "route_reason": (
            "paired_discovery_registration.json registered A-SC/BTCUSDT on the endpoint route; "
            "the RF-04.1 endpoint run returned one objective for every sampled candidate and the "
            "account exposed no per-fill ledger, so RF-04.6 runs A-SC on the RF-02-qualified "
            "event route ('public Mode 4 signal route + event route both ran') and keeps the "
            "endpoint result as the registered route deviation"
        ),
    },
    "A-HMA": {
        "interval": "1h",
        "route": "event",
        "registered_route": "event",
        "route_status": "QUALIFIED_EVENT",
        "route_role": "REGISTERED",
        "route_reason": (
            "the RF-02 route matrix qualifies A-HMA on the native-event route: protection "
            "orders projected and fills returned by the engine"
        ),
    },
}
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
COHORT = tuple(
    {"cell": f"{alpha}/{symbol}", "alpha_id": alpha, "symbol": symbol, **spec}
    for alpha, spec in ALPHA_ROUTES.items()
    for symbol in SYMBOLS
)

REGIME_TAPE = LAB_ROOT / "configs" / "lab05_full_emission_tape.json"


class BudgetExceeded(TimeoutError):
    """An arm or the whole bounded run spent its wall budget."""


@contextmanager
def wall_budget(seconds):
    """Raise :class:`BudgetExceeded` when the wall-clock budget is spent."""
    if not seconds or seconds <= 0:
        yield
        return

    limit = float(seconds)

    def _handler(signum, frame):
        raise BudgetExceeded(f"wall budget of {limit:.1f}s exceeded")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, limit)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def not_run_arm(cell: dict, arm: str, reason: str) -> dict:
    """A bounded non-run: null metrics plus the exact reason, never a zero."""
    return {
        "arm": arm,
        "route": cell["route"],
        "schedule": None,
        "ok": False,
        "error": f"NOT_RUN_BUDGET: {reason}",
        "budget_status": "NOT_RUN_BUDGET",
        "cutoffs": [],
        "fold_count": 0,
        "params_by_fold": {},
        "selected_params": None,
        "selected_digest": None,
        "fold_selection_table": [],
        "trial_records": [],
        "trial_count": 0,
        "nonfinite_values": {},
        "oos_used_for_selection": None,
        "validation_claim": None,
        "scoring_backend": None,
        "candidate_selection_metric": None,
        "resolved_evaluator": None,
        "account": None,
        "wall_seconds": None,
    }


def build_contrast(cell: dict, calendar: dict, regime: dict) -> dict:
    """Reuse the RF-04.1 contrast checks, re-labelled for the scaled cohort."""
    contrast = pilot_runner.contrast_validity(calendar, regime, cell)
    contrast["route"] = cell["route"]
    contrast["route_role"] = cell["route_role"]
    contrast["claim_limit"] = (
        f"bounded paired discovery on {cell['cell']} (development window "
        f"{DEVELOPMENT[0]}..{DEVELOPMENT[1]}, {TRIALS} trials/cutoff); no statistical "
        "claim, no edge inference and no holdout claim is made from it"
    )
    if contrast["status"] == "VALID":
        contrast["implementation_fidelity"] = "AS_SPECIFIED"
        contrast["implementation_fidelity_reason"] = (
            "both arms selected parameters without outer OOS, the engine account is "
            "EVALUATED and, on the event route, the event scorer ran at least one "
            "QuantBT account; the arms used different cutoffs"
        )
    else:
        contrast["implementation_fidelity"] = "DEVIATED"
        contrast["implementation_fidelity_reason"] = (
            "; ".join(contrast["reasons"]) or "the paired contrast failed a validity check")
    contrast["statistical_status"] = "NOT_EVALUATED"
    contrast["economic_status"] = "NOT_EVALUATED"
    contrast["status_reason"] = (
        "; ".join(contrast["reasons"]) if contrast["status"] != "VALID" else
        "bounded discovery paired run; no paired bootstrap or decay panel is computed "
        "for the scaled cells"
    )
    return contrast


def primary_run(entry: dict | None) -> dict | None:
    if not entry:
        return None
    for run in entry.get("runs", []):
        if run.get("route") == entry.get("primary_route"):
            return run
    return None


def completed_run(entry: dict | None) -> dict | None:
    run = primary_run(entry)
    if run and run.get("status") == "RUN":
        return run
    return None


def run_completed(entry: dict | None) -> bool:
    return completed_run(entry) is not None


def arm_metrics(arm: dict) -> dict:
    account = arm.get("account") or {}
    report = account.get("engine_report") or {}
    trades = report.get("num_trades")
    if trades is None:
        trades = account.get("engine_fill_count")
    return {
        "folds": arm.get("fold_count"),
        "trials": arm.get("trial_count"),
        "equity_last": account.get("equity_last"),
        "total_return_pct": report.get("total_return_pct"),
        "sharpe": report.get("sharpe"),
        "num_trades": trades,
        "max_drawdown_pct": report.get("max_drawdown_pct"),
        "wall_seconds": arm.get("wall_seconds"),
    }


def data_record(cell: dict, frame, snapshot_root: Path, manifest: dict) -> dict:
    return {
        "symbol": cell["symbol"],
        "interval": cell["interval"],
        "source": f"{SNAPSHOT_ID}/{PRODUCT}",
        "is_synthetic": False,
        "window": [str(frame.index[0]), str(frame.index[-1])],
        "bars": int(len(frame)),
        "snapshot_manifest": str(snapshot_root / "manifest.json"),
        "snapshot_manifest_sha256": sha256_file(snapshot_root / "manifest.json"),
        "snapshot_id": manifest.get("snapshot_id", SNAPSHOT_ID),
        "regime_tape_symbol": "BTCUSDT",
    }


def reused_pilot_run(cell: dict, pilot_cell: dict, pilot_sha: str, index: int) -> dict:
    """The committed RF-04.1 run, reused and explicitly sourced."""
    record = copy.deepcopy(pilot_cell)
    deviation = record["route"] == "endpoint" and cell["alpha_id"] == "A-SC"
    contrast = copy.deepcopy(record["contrast"])
    contrast["route"] = record["route"]
    contrast["route_role"] = "REGISTERED_DEVIATION" if deviation else "REGISTERED"
    contrast["implementation_fidelity"] = "DEVIATED" if deviation else "AS_SPECIFIED"
    contrast["implementation_fidelity_reason"] = (
        "the endpoint scorer returned one objective for every sampled candidate and the "
        "account exposed no per-fill ledger; the run is retained as the registered route "
        "deviation and is never used as the scaled A-SC result"
        if deviation else
        "RF-04.1 event run: both arms declared oos_used_for_selection=False and the "
        "event account is EVALUATED with a per-fill ledger"
    )
    return {
        "route": record["route"],
        "route_role": "REGISTERED_DEVIATION" if deviation else "REGISTERED",
        "route_status": "REGISTERED_DEVIATION" if deviation else "REGISTERED",
        "route_reason": (
            "paired_discovery_registration.json registered A-SC/BTCUSDT on the endpoint route; "
            "kept in the full artifact only as the registered route deviation"
            if deviation else cell["route_reason"]
        ),
        "source": {
            "kind": "reused_committed_artifact",
            "artifact": "paired_discovery_pilot.json",
            "sha256": pilot_sha,
            "pointer": f"#/cells/{index}",
            "note": ("same development window, economics, trial budget and seed policy as the "
                     "fresh RF-04.6 runs; the pilot artifact is not rewritten"),
        },
        "status": "RUN",
        "stop_reason": None,
        "cutoffs": {arm: record["arms"][arm].get("cutoffs", []) for arm in PRIMARY_ARMS},
        "fold_count": {arm: record["arms"][arm].get("fold_count") for arm in PRIMARY_ARMS},
        "arms": record["arms"],
        "contrast": contrast,
        "wall_seconds_total": round(sum(
            record["arms"][arm].get("wall_seconds") or 0.0 for arm in PRIMARY_ARMS), 3),
    }


def placeholder_run(cell: dict, status: str, reason: str) -> dict:
    return {
        "route": cell["route"],
        "route_role": cell["route_role"],
        "route_status": cell["route_status"],
        "route_reason": cell["route_reason"],
        "source": {"kind": "not_executed", "artifact": None},
        "status": status,
        "stop_reason": reason,
        "cutoffs": {arm: [] for arm in PRIMARY_ARMS},
        "fold_count": {arm: 0 for arm in PRIMARY_ARMS},
        "arms": {arm: not_run_arm(cell, arm, reason) for arm in PRIMARY_ARMS},
        "contrast": None,
        "wall_seconds_total": 0.0,
    }


def fresh_run(cell: dict, frame, calendar, dynamic, *, arm_budget: float,
              deadline: float) -> dict:
    """Run both arms of one cell under the bounded wall budget."""
    arms: dict[str, dict] = {}
    stop_reason: str | None = None
    for arm_name, schedule in (("M4_CAL", calendar), ("M4_REGIME", dynamic)):
        remaining = deadline - time.monotonic()
        if stop_reason is not None:
            arms[arm_name] = not_run_arm(cell, arm_name, stop_reason)
            continue
        if remaining <= 0:
            stop_reason = "the global wall budget was exhausted before this arm started"
            arms[arm_name] = not_run_arm(cell, arm_name, stop_reason)
            continue
        limit = min(float(arm_budget), remaining)
        started = time.perf_counter()
        try:
            with wall_budget(limit):
                record = pilot_runner.arm_record(cell, arm_name, schedule, frame)
        except BudgetExceeded as exc:
            stop_reason = (
                f"arm {arm_name} exceeded its {limit:.1f}s wall budget ({exc}); the "
                "remaining arms of this cell were not started")
            failed = not_run_arm(cell, arm_name, stop_reason)
            failed["wall_seconds"] = round(time.perf_counter() - started, 3)
            arms[arm_name] = failed
            continue
        record["budget_status"] = "RUN"
        record["arm_budget_seconds"] = round(limit, 3)
        record["cell_arm_elapsed_seconds"] = round(time.perf_counter() - started, 3)
        arms[arm_name] = record
    status = "RUN" if all(arms[arm]["budget_status"] == "RUN" for arm in PRIMARY_ARMS) \
        else "NOT_RUN_BUDGET"
    return {
        "route": cell["route"],
        "route_role": cell["route_role"],
        "route_status": cell["route_status"],
        "route_reason": cell["route_reason"],
        "source": {"kind": "run_rf04_scale", "artifact": "paired_discovery_full.json"},
        "status": status,
        "stop_reason": stop_reason,
        "cutoffs": {arm: list(arms[arm].get("cutoffs") or []) for arm in PRIMARY_ARMS},
        "fold_count": {arm: arms[arm].get("fold_count", 0) for arm in PRIMARY_ARMS},
        "arms": arms,
        "contrast": build_contrast(cell, arms["M4_CAL"], arms["M4_REGIME"]),
        "wall_seconds_total": round(sum(
            arms[arm].get("wall_seconds") or 0.0 for arm in PRIMARY_ARMS), 3),
    }


def pilot_scope(route_matrix: dict) -> dict:
    """The committed RF-04.1 coverage state the full artifact supersedes."""
    per_cell = {}
    for row in route_matrix["route_matrix"]["cells"]:
        name = row["cell"]
        if row["route_status"] == "BLOCKED_CAPABILITY":
            per_cell[name] = "BLOCKED_CAPABILITY"
        elif name == "A-HMA/BTCUSDT":
            per_cell[name] = "RUN_VALID"
        elif name == "A-SC/BTCUSDT":
            per_cell[name] = "RUN_NOT_EVALUABLE"
        else:
            per_cell[name] = "NOT_RUN"
    counts = {status: sum(1 for value in per_cell.values() if value == status)
              for status in STATUS_VOCABULARY}
    counts["planned_cells"] = len(per_cell)
    counts["total_classified"] = len(per_cell)
    return {
        "artifact": "paired_discovery_pilot.json",
        "counts": counts,
        "per_cell": per_cell,
        "note": ("the RF-04.1 two-cell scope, superseded by this full-cohort artifact but "
                 "kept for traceability; the pilot artifact itself is never rewritten"),
    }


def build_full_payload(*, cells: list[dict], calendar, dynamic, registration_sha: str,
                       pilot_sha: str, status: str, pilot_coverage: dict) -> dict:
    return {
        "schema": "regime_lab.rf04_paired_discovery_full.v1",
        "phase": "RF-04",
        "status": status,
        "study_id": STUDY_ID,
        "registration_artifact": {
            "artifact": "paired_discovery_registration.json",
            "sha256": registration_sha,
        },
        "pilot_source_artifact": {
            "artifact": "paired_discovery_pilot.json",
            "sha256": pilot_sha,
        },
        "development_window": {"start": DEVELOPMENT[0], "end": DEVELOPMENT[1]},
        "matched_conditions": [
            "same economic account (20000 USDT, 2000 USDT entry notional, one-way fee "
            "0.0004 bound once, slippage 1bp)",
            "same Mode 4 contract and per-fold causal schedule",
            "same training-memory rule (180 days)",
            "same trial budget per cutoff (8) and same seed (20260911)",
            "same evaluation dates",
            "only the cutoff list differs between the two arms",
        ],
        "economics": {
            "account_capital": ACCOUNT_CAPITAL,
            "entry_notional": ALLOC_PER_TRADE * ACCOUNT_CAPITAL,
            "one_way_fee": ONE_WAY_TAKER_FEE,
            "slippage_bps": SLIPPAGE_BPS,
            "fee_binding": bound_fee_kwargs(ONE_WAY_TAKER_FEE),
            "trials_per_cutoff": TRIALS,
            "seed": SEED,
            "train_memory_days": 180,
        },
        "mode4_contract": {
            "optimization_mode": "mode_4_is_only_robust",
            "optimization_schedule": "per_fold_causal",
            "candidate_selection_metric": "is_only_robust",
            "scoring_backend": "endpoint",
            "oos_used_for_selection": False,
        },
        "regime_tape": {
            "artifact": "configs/lab05_full_emission_tape.json",
            "sha256": sha256_file(REGIME_TAPE),
            "symbol": "BTCUSDT",
            "per_symbol": False,
            "note": ("the RF-04.1 pilot reused the committed BTCUSDT emission tape for every "
                     "cell; RF-04.6 keeps that tape so the regime cutoff list is identical "
                     "across cells, and records it as a scope limitation, not a per-symbol "
                     "tape claim"),
        },
        "arms": {"M4_CAL": calendar.as_record(), "M4_REGIME": dynamic.as_record()},
        "cohort": {
            "planned_cells": 20,
            "runnable_cells": 10,
            "blocked_cells": 10,
            "route_matrix_ref": "evidence/corrective_mode4_v3/RF-02/pilot_and_route_matrix.json",
            "route_cohorts": {
                "event": [cell["cell"] for cell in COHORT],
                "endpoint_deviation": ["A-SC/BTCUSDT"],
            },
        },
        "cells": cells,
        "superseded_pilot_scope": pilot_coverage,
        "claim_limits": [
            "development-window discovery only (2021-01-01..2022-06-30); nested retrospective, "
            "no holdout and no live claim",
            "8 trials/cutoff instead of the registered 32-64; bounded by wall budget",
            "the regime cutoff list comes from the committed BTCUSDT emission tape and is "
            "identical across symbols; per-symbol model tapes are not claimed here",
            "no paired bootstrap, decay panel or control was computed for the scaled cells",
            "the A-SC/BTCUSDT endpoint run is retained only as the registered route deviation",
        ],
        "coverage_ref": "cell_coverage.json",
    }


def coverage_cell(*, route_row: dict, entry: dict | None, cell_index: int | None,
                  controls: dict) -> dict:
    name = route_row["cell"]
    alpha_id, symbol = name.split("/")
    refs = [f"evidence/corrective_mode4_v3/RF-02/pilot_and_route_matrix.json"
            f"#/route_matrix/cells/{route_row['route_index']}"]
    full_ref = ("evidence/corrective_mode4_v3/RF-04/paired_discovery_full.json"
                + (f"#/cells/{cell_index}" if cell_index is not None else ""))
    if route_row["route_status"] == "BLOCKED_CAPABILITY":
        return {
            "cell": name,
            "alpha_id": alpha_id,
            "symbol": symbol,
            "route": None,
            "route_reason": ("the RF-02 route matrix blocks this cell before any outcome; "
                             "no run result exists"),
            "route_status": "BLOCKED_CAPABILITY",
            "coverage_status": "BLOCKED_CAPABILITY",
            "reason": route_row["reason"],
            "evidence_ref": refs[0],
            "evidence_refs": refs,
            "executed": False,
            "run_result": None,
            "run_result_reason": route_row["reason"],
            "account_metrics": None,
            "account_metrics_reason": ("no arm ran on this cell; account metrics are null and "
                                       "are never replaced with a zero or an estimate"),
        }
    if entry is not None:
        refs.append(full_ref)
    run = primary_run(entry)
    if run is None or run.get("status") != "RUN":
        status = ("NOT_RUN_BUDGET" if run is not None and run.get("status") == "NOT_RUN_BUDGET"
                  else "NOT_RUN")
        reason = (
            (run or {}).get("stop_reason") or
            "the cell was not executed in this bounded invocation; no account metrics exist "
            "and none are estimated"
        )
        return {
            "cell": name,
            "alpha_id": alpha_id,
            "symbol": symbol,
            "route": entry.get("primary_route") if entry else None,
            "route_reason": entry.get("route_reason") if entry else None,
            "route_status": route_row["route_status"],
            "coverage_status": status,
            "reason": reason,
            "evidence_ref": refs[-1],
            "evidence_refs": refs,
            "executed": False,
            "run_result": None,
            "run_result_reason": reason,
            "account_metrics": None,
            "account_metrics_reason": ("no arm ran on this cell; account metrics are null and "
                                       "are never replaced with a zero or an estimate"),
        }
    contrast = run["contrast"]
    insufficient = any(
        "INSUFFICIENT" in str(run["arms"][arm].get("error") or "") for arm in PRIMARY_ARMS)
    if contrast["status"] == "VALID":
        coverage_status = "RUN_VALID"
    elif insufficient:
        coverage_status = "INSUFFICIENT_DATA"
    else:
        coverage_status = "RUN_NOT_EVALUABLE"
    deviation_runs = [other for other in (entry or {}).get("runs", []) if other is not run]
    run_result = {
        "route": run["route"],
        "arms": {arm: arm_metrics(run["arms"][arm]) for arm in PRIMARY_ARMS},
        "contrast_status": contrast["status"],
        "execution_validity": "PASS" if contrast["status"] == "VALID" else "FAIL",
        "implementation_fidelity": contrast.get("implementation_fidelity"),
        "statistical_status": "NOT_EVALUATED",
        "statistical_status_reason": contrast.get("status_reason"),
        "economic_status": "NOT_EVALUATED",
        "route_deviations": [{
            "route": other["route"],
            "route_role": other.get("route_role"),
            "implementation_fidelity": (other.get("contrast") or {}).get("implementation_fidelity"),
            "reason": other.get("route_reason"),
            "account_metrics": {arm: arm_metrics(other["arms"][arm])
                                for arm in PRIMARY_ARMS if arm in other.get("arms", {})},
            "source": other.get("source"),
        } for other in deviation_runs],
    }
    account_metrics = dict(run_result["arms"])
    if name in ("A-SC/BTCUSDT", "A-HMA/BTCUSDT") and controls is not None:
        matched = {row["cell"]: row["arm"] for row in controls["matched_control"]["cells"]}
        placebo = {row["cell"]: row["arm"] for row in controls["placebo"]["cells"]}
        if name in matched:
            account_metrics["M4_CAL_MATCHED"] = arm_metrics(matched[name])
            run_result["arms"]["M4_CAL_MATCHED"] = arm_metrics(matched[name])
        if name in placebo:
            account_metrics["M4_REGIME_DELAYED"] = arm_metrics(placebo[name])
            run_result["arms"]["M4_REGIME_DELAYED"] = arm_metrics(placebo[name])
    reason = ("executed on the {route} route with execution_validity=PASS and "
              "implementation_fidelity=AS_SPECIFIED; the economic status stays "
              "NOT_EVALUATED because RF-04.6 is a bounded discovery run with no paired "
              "inference computed").format(route=run["route"]) if coverage_status == "RUN_VALID" \
        else ("executed but the paired contrast is {status}: {reasons}").format(
            status=contrast["status"],
            reasons="; ".join(contrast.get("reasons") or ["see the full artifact"]))
    return {
        "cell": name,
        "alpha_id": alpha_id,
        "symbol": symbol,
        "route": run["route"],
        "route_reason": entry.get("route_reason"),
        "route_status": route_row["route_status"],
        "coverage_status": coverage_status,
        "reason": reason,
        "evidence_ref": refs[-1],
        "evidence_refs": refs,
        "executed": True,
        "run_result": run_result,
        "run_result_reason": None,
        "account_metrics": account_metrics,
        "account_metrics_reason": None,
    }


def build_coverage_payload(*, cells: list[dict], route_matrix: dict, full_sha: str,
                           pilot_sha: str, protocol: dict, controls: dict) -> dict:
    by_cell = {cell["cell"]: cell for cell in cells}
    index_by_cell = {cell["cell"]: index for index, cell in enumerate(cells)}
    entries = []
    for index, route_row in enumerate(route_matrix["route_matrix"]["cells"]):
        name = route_row["cell"]
        row = dict(route_row)
        row["route_index"] = index
        entries.append(coverage_cell(route_row=row, entry=by_cell.get(name),
                                     cell_index=index_by_cell.get(name), controls=controls))
    counts = {status: sum(1 for cell in entries if cell["coverage_status"] == status)
              for status in STATUS_VOCABULARY}
    counts["planned_cells"] = len(entries)
    counts["total_classified"] = len(entries)
    executed = (counts["RUN_VALID"] + counts["RUN_NOT_EVALUABLE"]
                + counts["INSUFFICIENT_DATA"])
    closed = (counts["NOT_RUN"] == 0 and counts["NOT_RUN_BUDGET"] == 0
              and counts["BLOCKED_CAPABILITY"] + executed == counts["planned_cells"])
    status = (f"COVERAGE_{'CLOSED' if closed else 'PARTIAL'}_{executed}_EXECUTED_"
              f"{counts['BLOCKED_CAPABILITY']}_BLOCKED_{counts['NOT_RUN']}_NOT_RUN_"
              f"{counts['NOT_RUN_BUDGET']}_NOT_RUN_BUDGET")
    return {
        "schema": "regime_lab.rf04_cell_coverage.v1",
        "phase": "RF-04",
        "study_id": STUDY_ID,
        "status": status,
        "status_vocabulary": list(STATUS_VOCABULARY),
        "rule": (
            "one row per planned primary cell (4 alphas x 5 symbols of the registered "
            "discovery cohort); the route decision is merged from RF-02/pilot_and_route_matrix.json "
            "and the run result from RF-04/paired_discovery_full.json. A non-executed cell carries "
            "null metrics with a reason, never a zero. A rejected or bounded arm is recorded as "
            "NOT_RUN_BUDGET/RUN_NOT_EVALUABLE with the exact reason"
        ),
        "sources": [
            {"artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_full.json",
             "sha256": full_sha},
            {"artifact": "evidence/corrective_mode4_v3/RF-02/pilot_and_route_matrix.json",
             "sha256": sha256_file(RF02_DIR / "pilot_and_route_matrix.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_pilot.json",
             "sha256": pilot_sha},
        ],
        "registered_cohort": protocol["cohort"],
        "counts": counts,
        "cells": entries,
    }


def full_status(cells: list[dict]) -> str:
    completed = sum(1 for cell in cells if run_completed(cell))
    if completed == len(COHORT):
        return "FULL_PAIRED_DISCOVERY_COMPLETE"
    if completed:
        return "FULL_PAIRED_DISCOVERY_PARTIAL"
    return "FULL_PAIRED_DISCOVERY_NOT_STARTED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", default="all",
                        help="comma-separated cell names, or 'all'")
    parser.add_argument("--resume", action="store_true",
                        help="keep completed runs from an existing paired_discovery_full.json")
    parser.add_argument("--force", action="store_true",
                        help="discard an existing paired_discovery_full.json and redo fresh runs")
    parser.add_argument("--budget-seconds", type=float, default=7200.0,
                        help="global wall budget for this invocation")
    parser.add_argument("--arm-budget-seconds", type=float, default=900.0,
                        help="wall budget for one arm of one cell")
    args = parser.parse_args()
    if args.resume and args.force:
        raise SystemExit("--resume and --force are mutually exclusive")

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)

    full_path = RUN_DIR / "paired_discovery_full.json"
    if full_path.exists() and not (args.resume or args.force):
        raise SystemExit(
            "paired_discovery_full.json exists; pass --resume to continue it or --force to redo")

    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = load_json(snapshot_root / "manifest.json")
    emissions = load_json(REGIME_TAPE)["emissions"]
    route_matrix = load_json(RF02_DIR / "pilot_and_route_matrix.json")
    protocol = load_json(RUN_DIR / "discovery_protocol.json")
    pilot = load_json(RUN_DIR / "paired_discovery_pilot.json")
    pilot_sha = sha256_file(RUN_DIR / "paired_discovery_pilot.json")
    registration_sha = sha256_file(RUN_DIR / "paired_discovery_registration.json")
    controls = load_json(RUN_DIR / "controls_and_funnel.json")
    pilot_by_cell = {cell["cell"]: (index, cell) for index, cell in enumerate(pilot["cells"])}

    calendar = calendar_cutoffs(window_start=DEVELOPMENT[0], window_end=DEVELOPMENT[1],
                                first_cutoff="2021-01-01", test_days=180,
                                train_memory_days=180, max_cutoffs=3)
    dynamic = regime_cutoffs(emissions, window_start=DEVELOPMENT[0], window_end=DEVELOPMENT[1],
                             min_gap_days=REGIME_CONTROLLER["min_gap_days"],
                             max_age_days=REGIME_CONTROLLER["max_age_days"],
                             budget=REGIME_CONTROLLER["budget"])

    selected = {cell["cell"] for cell in COHORT} \
        if args.cells == "all" else set(args.cells.split(","))
    unknown = selected - {cell["cell"] for cell in COHORT}
    if unknown:
        raise SystemExit(f"unknown cells: {sorted(unknown)}")

    existing = load_json(full_path) if (full_path.exists() and args.resume) else None
    reused: dict[str, dict] = {}
    if existing:
        for entry in existing.get("cells", []):
            if run_completed(entry):
                entry = copy.deepcopy(entry)
                entry["runs"] = [
                    run for run in entry.get("runs", [])
                    if (run.get("source") or {}).get("kind") != "not_executed"]
                reused[entry["cell"]] = entry

    deadline = time.monotonic() + float(args.budget_seconds)
    entries: dict[str, dict] = {}
    declared_order = [cell["cell"] for cell in COHORT]
    for cell in COHORT:
        name = cell["cell"]
        if name in reused and not args.force:
            entries[name] = reused[name]
            continue
        pilot_entry = pilot_by_cell.get(name)
        runs = []
        data = None
        if pilot_entry is not None:
            runs.append(reused_pilot_run(cell, pilot_entry[1], pilot_sha, pilot_entry[0]))
            data = pilot_entry[1]["data"]
        if run_completed({"primary_route": cell["route"], "runs": runs}):
            pass
        elif name not in selected:
            runs.append(placeholder_run(
                cell, "NOT_RUN",
                "not selected in this bounded invocation; rerun with --resume and the "
                "remaining --cells to complete the cohort"))
        elif time.monotonic() >= deadline:
            runs.append(placeholder_run(
                cell, "NOT_RUN_BUDGET",
                f"global wall budget of {args.budget_seconds:.0f}s was exhausted by the "
                f"cells that ran before it; {name} was not executed"))
        else:
            frame = pilot_runner.load_frame(snapshot_root, cell["symbol"], cell["interval"])
            if data is None:
                data = data_record(cell, frame, snapshot_root, manifest)
            started = time.perf_counter()
            with writer.attempt(f"RF04.scale.{name}") as att:
                run = fresh_run(cell, frame, calendar, dynamic,
                                arm_budget=args.arm_budget_seconds, deadline=deadline)
                att.detail = {
                    "status": run["status"],
                    "contrast": (run["contrast"] or {}).get("status"),
                    "seconds": round(time.perf_counter() - started, 3),
                }
            runs.append(run)
        entries[name] = {
            "cell": name,
            "alpha_id": cell["alpha_id"],
            "symbol": cell["symbol"],
            "primary_route": cell["route"],
            "registered_route": cell["registered_route"],
            "route_status": cell["route_status"],
            "route_role": cell["route_role"],
            "route_reason": cell["route_reason"],
            "data": data,
            "runs": runs,
        }

    ordered_entries = [entries[name] for name in declared_order]
    payload = build_full_payload(
        cells=ordered_entries, calendar=calendar, dynamic=dynamic,
        registration_sha=registration_sha, pilot_sha=pilot_sha,
        status=full_status(ordered_entries), pilot_coverage=pilot_scope(route_matrix))
    full_record = writer.write_json("paired_discovery_full.json", payload, schema=payload["schema"])
    coverage = build_coverage_payload(
        cells=ordered_entries, route_matrix=route_matrix, full_sha=full_record["sha256"],
        pilot_sha=pilot_sha, protocol=protocol, controls=controls)
    coverage_record = writer.write_json("cell_coverage.json", coverage, schema=coverage["schema"])

    print(json.dumps({
        "paired_discovery_full": {"sha256": full_record["sha256"], "status": payload["status"]},
        "cell_coverage": {"sha256": coverage_record["sha256"], "status": coverage["status"],
                          "counts": coverage["counts"]},
        "cells": [
            {"cell": entry["cell"],
             "primary_route": entry["primary_route"],
             "run_status": (primary_run(entry) or {}).get("status"),
             "contrast": ((primary_run(entry) or {}).get("contrast") or {}).get("status"),
             "M4_CAL_equity": (((primary_run(entry) or {}).get("arms", {})
                                .get("M4_CAL") or {}).get("account") or {}).get("equity_last"),
             "M4_REGIME_equity": (((primary_run(entry) or {}).get("arms", {})
                                   .get("M4_REGIME") or {}).get("account") or {}).get("equity_last"),
             "M4_CAL_fills": (((primary_run(entry) or {}).get("arms", {})
                               .get("M4_CAL") or {}).get("account") or {}).get("fill_count"),
             "M4_REGIME_fills": (((primary_run(entry) or {}).get("arms", {})
                                  .get("M4_REGIME") or {}).get("account") or {}).get("fill_count")}
            for entry in ordered_entries
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
