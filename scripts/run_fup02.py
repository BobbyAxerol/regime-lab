#!/usr/bin/env python
"""FUP-02 — expanded-budget, full-development-window paired discovery.

Registered follow-up study
``evidence/corrective_mode4_v3/followup-studies/followup_studies_registration.json``
entry FUP-02: rerun the paired ``M4_CAL`` vs ``M4_REGIME`` discovery on every
cell whose route is qualified -- all 20 primary cells, with FUP-01 having
qualified A-VWAP/A-HASH on the native-event route and A-SC/A-HMA already
qualified there -- over the full development window ``2021-01-01..2023-12-31``,
at the low end of the registered 32-64 trials/cutoff, with a registered compute
budget revision written BEFORE the first run.

Reuse, never reimplementation
-----------------------------
* the engine pipeline, cutoff schedules, event-account scorer and trial-ledger
  extraction come from ``experiments/dynamic_fold_provider.py`` and
  ``scripts/run_rf04_paired_pilot.py``; this script only orchestrates them;
* the deployment account is built by the provider's own
  ``_event_account_payload`` -- the exact function a whole-arm run uses;
* one fold at a time is computed by filtering the engine's canonical fold list
  (``build_folds`` override that drops everything but the target fold). The fold
  ids, seeds, train windows and test segments are therefore the canonical ones,
  which is verified by ``tests/mode4_corrective/test_fup02_scale.py``.

Shards, checkpoints and budgets
-------------------------------
A shard is ``cell x arm`` (``alpha x symbol x arm``). Inside a shard the work is
checkpointed per fold/cutoff: a completed fold is never recomputed, a retried
fold records every attempt, and a shard that cannot finish inside the
registered per-shard cap stops cleanly with ``BUDGET_STOPPED`` plus the exact
reason. A shard the invocation budget never reached is ``NOT_RUN_BUDGET``. No
metric is fabricated and a non-run cell carries null metrics with a reason.

Usage
-----
    python scripts/run_fup02.py --register-budget       # once, BEFORE any run
    python scripts/run_fup02.py --run                   # first invocation
    python scripts/run_fup02.py --run --resume          # later invocations
    python scripts/run_fup02.py --status                # print the checkpoint
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("NUMBA_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import pandas as pd  # noqa: E402

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

import run_rf04_paired_pilot as pilot_runner  # noqa: E402

import crypto_regime_lab.experiments.dynamic_fold_provider as dfp  # noqa: E402
from crypto_regime_lab.data.qualification import DECISION_INTERVAL  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.integration.activation import parameter_digest  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "FUP-02"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / RUN_ID
FUP01_DIR = LAB_ROOT / "evidence" / STUDY_ID / "FUP-01"
RF02_DIR = LAB_ROOT / "evidence" / STUDY_ID / "RF-02"
REPORT_DIR = LAB_ROOT / "reports"
FOLLOWUP_REGISTRATION = (LAB_ROOT / "evidence" / STUDY_ID / "followup-studies"
                         / "followup_studies_registration.json")
SNAPSHOT_ID = "server_core_v1"
PRODUCT = "crypto_binance_futures_1m"
REGISTERED_SNAPSHOT_MANIFEST_SHA256 = (
    "88c19513043e05bbd7d8901916b87fe01d10822678b020e6cd8d2fdec00300ff"
)
WINDOW = ("2021-01-01", "2023-12-31")
LOAD_START = "2020-06-01"
TRIALS = 32
TRIAL_RANGE = (32, 64)
SEED = 20260911
PRIMARY_ARMS = ("M4_CAL", "M4_REGIME")
REGIME_CONTROLLER = {"min_gap_days": 90.0, "max_age_days": 180.0, "budget": None}
CALENDAR_SPEC = {"first_cutoff": "2021-01-01", "test_days": 180, "train_memory_days": 180}
REGIME_TAPE = LAB_ROOT / "configs" / "lab05_full_emission_tape.json"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")
CELL_ORDER = tuple(f"{alpha}/{symbol}" for alpha in ALPHAS for symbol in SYMBOLS)
#: Execution order is by MEASURED per-cutoff cost (cheapest first) so a fixed
#: invocation budget closes the most complete pairs; it was fixed before any
#: outcome was inspected and is recorded in the artifact.
SHARD_ORDER_ALPHAS = ("A-HMA", "A-HASH", "A-SC", "A-VWAP")
SHARD_STATUS = ("PENDING", "COMPLETE", "BUDGET_STOPPED", "NOT_RUN_BUDGET", "FAILED",
                "INSUFFICIENT_DATA")
CUTOFF_STATUS = ("NOT_RUN", "SCORED", "BUDGET_STOPPED", "ERROR")
COVERAGE_STATUS = ("RUN_VALID", "RUN_NOT_EVALUABLE", "BUDGET_STOPPED", "NOT_RUN_BUDGET",
                   "FAILED", "INSUFFICIENT_DATA", "BLOCKED_CAPABILITY", "NOT_RUN")
ARTIFACT_STATUS = ("RUN_IN_PROGRESS", "PARTIAL_BUDGET_STOPPED", "COMPLETE_ALL_CELLS")

ALPHA_ROUTES = {
    "A-SC": {
        "route": "event",
        "registered_route": "endpoint",
        "route_role": "FIDELITY_ROUTE",
        "fup02_route_note": (
            "paired_discovery_registration.json registered A-SC/BTCUSDT on the endpoint route; "
            "RF-04.6 ran every A-SC cell on the RF-02-qualified event route as the fidelity "
            "route. FUP-02 keeps the event route for all five A-SC cells so the cohort shares "
            "one route and one fill ledger format"
        ),
    },
    "A-HMA": {
        "route": "event",
        "registered_route": "event",
        "route_role": "REGISTERED",
        "fup02_route_note": (
            "the RF-02 route matrix qualifies A-HMA on the native-event route: protection "
            "orders projected and fills returned by the engine"
        ),
    },
    "A-VWAP": {
        "route": "event",
        "registered_route": "event",
        "route_role": "QUALIFIED_BY_FUP01",
        "fup02_route_note": (
            "FUP-01 qualifies A-VWAP on the native-event route: AMEND_PROTECTION reaches the "
            "engine on the tracked protection id and CANCEL/REDUCE/reported fills were observed"
        ),
    },
    "A-HASH": {
        "route": "event",
        "registered_route": "event",
        "route_role": "QUALIFIED_BY_FUP01",
        "fup02_route_note": (
            "FUP-01 qualifies A-HASH on the native-event route: the ordered ladder emits one "
            "reduce-only LIMIT per rung and partial fills reach the adapter as REDUCE"
        ),
    },
}


class BudgetExceeded(TimeoutError):
    """An engine call or an invocation spent its registered wall budget."""


@contextmanager
def wall_budget(seconds):
    """Raise :class:`BudgetExceeded` when the wall-clock budget is spent.

    The provider catches exceptions inside ``run_cutoff_walk_forward`` and
    records them as a returned ``error``; the caller inspects the error text to
    tell a budget stop from a genuine engine failure.
    """
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


def json_stable(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# the registered compute-budget revision (written BEFORE any run)
# ---------------------------------------------------------------------------

def build_budget_revision() -> dict:
    """The FUP-02 compute-budget revision, registered before the runs.

    The measured per-fold micro-benchmarks below were taken with the lab venv on
    one worker, 32 trials, fold 0 of the registered calendar on real snapshot
    data; they are the basis for the caps, not a promise about the full run.
    """
    return {
        "schema": "regime_lab.fup02_compute_budget_revision.v1",
        "phase": "FUP-02",
        "study_id": STUDY_ID,
        "status": "REGISTERED_BEFORE_THE_FUP02_RUNS",
        "registered_at_utc": utc_now_iso(),
        "registration_source": {
            "artifact": "evidence/corrective_mode4_v3/followup-studies/"
                        "followup_studies_registration.json",
            "pointer": "#/studies/1",
            "sha256": sha256_file(FOLLOWUP_REGISTRATION),
            "parent_discovery_protocol": {
                "artifact": "evidence/corrective_mode4_v3/RF-04/discovery_protocol.json",
                "note": ("RF-04's registered discovery protocol already names 32-64 trials/cutoff "
                         "and the 2021-01-01..2023-12-31 development window; FUP-02 is the "
                         "execution of that registration, not a new trial budget"),
            },
        },
        "run_gate": (
            "run_fup02.py refuses to execute any shard unless this artifact exists and its "
            "status is REGISTERED_BEFORE_THE_FUP02_RUNS; --register-budget writes it once"
        ),
        "scope": {
            "cells": list(CELL_ORDER),
            "cells_planned": len(CELL_ORDER),
            "arms": list(PRIMARY_ARMS),
            "shards_planned": len(CELL_ORDER) * len(PRIMARY_ARMS),
            "route": "event (all 20 cells; FUP-01 qualified A-VWAP/A-HASH, A-SC/A-HMA "
                     "already qualified)",
            "development_window": {"start": WINDOW[0], "end": WINDOW[1]},
            "calendar_cutoffs": 7,
            "regime_cutoffs": 11,
            "shard_granularity": "cell x arm, checkpointed per fold/cutoff",
        },
        "trial_budget": {
            "registered_range": list(TRIAL_RANGE),
            "executed_per_cutoff": TRIALS,
            "equal_across_arms": True,
            "selection_reason": (
                "the low end of the registered 32-64 range is executed so the fixed invocation "
                "budget closes the most complete paired cells; the per-arm compute is identical "
                "and no arm is granted more trials than the other"
            ),
            "seed_policy": {
                "seed": SEED,
                "derivation": ("the installed engine derives the per-fold seed as "
                               "(seed + fold_id * 1000003) mod 2**32; both arms and every cell "
                               "use the same base seed and the same derivation"),
                "repeated_seeds_measure": "search variability, not independent observations",
            },
        },
        "coverage_review_rule": {
            "when": "before any final design freeze; not executed by FUP-02 itself",
            "artifact": "coverage_review.json",
            "admissible_definition": (
                "a scored cutoff is admissible when the selector returned selected parameters "
                "and at least one trial objective is finite; pruned/infeasible-only cutoffs are "
                "not admissible"
            ),
            "escalation": (
                "if admissible_over_scored < 0.80 or (nonfinite + infeasible) / trials > 0.25, "
                "escalate the trial budget to 64 in a REVISED budget revision before the frozen "
                "rerun; if coverage stays insufficient, record the insufficiency and do not "
                "present the run as a fully supported design freeze"
            ),
            "deep_selector_audit": (
                "the public provider payload does not expose selector/cluster/fallback fields; "
                "the RF-04.2 transparency ledger deep audit remains the tool for that question"
            ),
        },
        "resource_caps": {
            "workers": 1,
            "worker_justification": (
                "the registered sandbox resource budget is workers=1; keeping one worker keeps "
                "wall seconds comparable with RF-04.6 and keeps both arms sequential inside a "
                "cell (a shard is a cell x arm boundary, never a per-arm race)"
            ),
            "cpu_limit": 2,
            "cpu_change": "none requested; the registered sandbox cpu_limit=2 is unchanged",
            "cpu_change_justification": None,
            "working_memory_gib": 4,
            "measured_peak_rss_gib": 1.02,
            "per_shard_cap_seconds": 900,
            "per_shard_cap_tier": "T3 (guide 8.1: discovery shards <= 900s)",
            "per_cutoff_cap_seconds": 900,
            "per_invocation_budget_seconds": 5400,
            "total_wall_budget_seconds": 43200,
            "total_wall_budget_note": (
                "approved upper bound across all resumable invocations; every invocation writes "
                "its own elapsed seconds and stop reason, and unused budget is never silently "
                "transferred to one arm"
            ),
            "network": "off (run stage)",
            "thread_pinning": ["NUMBA_NUM_THREADS=1", "OMP_NUM_THREADS=1",
                               "OPENBLAS_NUM_THREADS=1", "MKL_NUM_THREADS=1"],
        },
        "revision_rule": {
            "append_only": True,
            "may_change": [
                "wall/invocation budgets and per-shard caps",
                "the trial budget inside the registered 32-64 range when the coverage review "
                "requires it",
            ],
            "must_not_change": [
                "per-arm compute: both arms always receive the same trial budget, seed, "
                "training memory, economics and route",
                "a completed shard is never recomputed for a budget revision",
                "a budget increase is never applied to one arm only",
            ],
            "cpu_change_rule": (
                "any worker/CPU change needs a measured justification recorded here before the "
                "affected shards run and applies to both arms; no CPU change is requested by "
                "this revision"
            ),
        },
        "stop_vocabulary": list(SHARD_STATUS),
        "cutoff_stop_vocabulary": list(CUTOFF_STATUS),
        "non_fabrication": (
            "a non-run or stopped shard/fold stores null metrics plus the exact reason; nothing "
            "is zero-filled or estimated"
        ),
        "pre_run_micro_benchmarks": [
            {"alpha_id": "A-HMA", "symbol": "BTCUSDT", "interval": "1h", "trials": 32,
             "fold_id": 0, "wall_seconds": 45.88, "per_trial_seconds": 1.434,
             "event_account_runs": 25, "peak_rss_mib": 902.1},
            {"alpha_id": "A-HASH", "symbol": "BTCUSDT", "interval": "15min", "trials": 32,
             "fold_id": 0, "wall_seconds": 135.66, "per_trial_seconds": 4.239,
             "event_account_runs": 19, "peak_rss_mib": 997.7},
            {"alpha_id": "A-SC", "symbol": "BTCUSDT", "interval": "15min", "trials": 32,
             "fold_id": 0, "wall_seconds": 176.4, "per_trial_seconds": 5.512,
             "event_account_runs": 31, "peak_rss_mib": 983.7},
            {"alpha_id": "A-VWAP", "symbol": "BTCUSDT", "interval": "15min", "trials": 32,
             "fold_id": 0, "wall_seconds": 180.2, "per_trial_seconds": 5.631,
             "event_account_runs": 33, "peak_rss_mib": 1020.8},
        ],
        "benchmark_conditions": (
            "lab venv, one worker, thread-pinned, fold 0 of the registered calendar schedule, "
            "real snapshot partitions; measured immediately before registration, no selection "
            "on these numbers beyond choosing the cheapest-first execution order"
        ),
        "contamination": {
            "status": "NESTED_RETROSPECTIVE",
            "untouched_holdout": False,
            "reason": ("2021-2023 was already exposed to design and repair work in RF-01..RF-05; "
                       "FUP-02 adds trials and the 2023 development year but is not a holdout "
                       "and makes no confirmation claim"),
            "post_2023_data": "never read by FUP-02",
        },
    }


def register_budget(writer: EvidenceWriter, force: bool) -> dict:
    target = RUN_DIR / "budget_revision.json"
    if target.exists() and not force:
        raise SystemExit(f"{target} exists; pass --force to supersede it explicitly")
    payload = build_budget_revision()
    record = writer.write_json("budget_revision.json", payload, schema=payload["schema"])
    return {"record": record, "payload": payload}


def load_budget_revision() -> dict:
    target = RUN_DIR / "budget_revision.json"
    if not target.is_file():
        raise SystemExit(
            "FUP-02/budget_revision.json is missing; the run must not start before the "
            "compute-budget revision is registered (run --register-budget first)")
    payload = load_json(target)
    if payload.get("status") != "REGISTERED_BEFORE_THE_FUP02_RUNS":
        raise SystemExit(
            f"budget_revision.json status is {payload.get('status')!r}, not "
            "REGISTERED_BEFORE_THE_FUP02_RUNS")
    return payload


# ---------------------------------------------------------------------------
# cohort, schedules, data
# ---------------------------------------------------------------------------

def fup01_route_matrix() -> dict:
    return load_json(FUP01_DIR / "route_matrix.json")


def cell_cohort(route_matrix: dict) -> list[dict]:
    by_cell = {row["cell"]: row for row in route_matrix["cells"]}
    cohort = []
    for name in CELL_ORDER:
        alpha_id, symbol = name.split("/")
        route_row = by_cell[name]
        spec = ALPHA_ROUTES[alpha_id]
        cohort.append({
            "cell": name,
            "alpha_id": alpha_id,
            "symbol": symbol,
            "interval": DECISION_INTERVAL[alpha_id],
            "route": spec["route"],
            "registered_route": spec["registered_route"],
            "route_status": route_row["route_status"],
            "route_role": route_row["route_role"],
            "route_reason": route_row["reason"],
            "fup02_route_note": spec["fup02_route_note"],
            "route_source": {
                "artifact": "evidence/corrective_mode4_v3/FUP-01/route_matrix.json",
                "sha256": sha256_file(FUP01_DIR / "route_matrix.json"),
                "pointer": f"#/cells/{route_row['source'].get('pointer', '')}".rstrip("/"),
            },
        })
    return cohort


def build_schedules() -> dict:
    emissions = load_json(REGIME_TAPE)["emissions"]
    calendar = dfp.calendar_cutoffs(
        window_start=WINDOW[0], window_end=WINDOW[1],
        first_cutoff=CALENDAR_SPEC["first_cutoff"], test_days=CALENDAR_SPEC["test_days"],
        train_memory_days=CALENDAR_SPEC["train_memory_days"])
    dynamic = dfp.regime_cutoffs(
        emissions, window_start=WINDOW[0], window_end=WINDOW[1],
        min_gap_days=REGIME_CONTROLLER["min_gap_days"],
        max_age_days=REGIME_CONTROLLER["max_age_days"],
        budget=REGIME_CONTROLLER["budget"])
    return {"M4_CAL": calendar, "M4_REGIME": dynamic}


def load_window_frame(snapshot_root: Path, symbol: str, interval: str) -> pd.DataFrame:
    """Reuse ``run_rf04_paired_pilot.load_frame`` with the FUP-02 window.

    The RF-04.6 loader reads its window from module globals; they are swapped for
    the duration of the call and restored, so no loader is reimplemented.
    """
    previous_dev = pilot_runner.DEVELOPMENT
    previous_start = pilot_runner.LOAD_START
    pilot_runner.DEVELOPMENT = WINDOW
    pilot_runner.LOAD_START = LOAD_START
    try:
        return pilot_runner.load_frame(snapshot_root, symbol, interval)
    finally:
        pilot_runner.DEVELOPMENT = previous_dev
        pilot_runner.LOAD_START = previous_start


def engine_param_ranges(alpha_id: str) -> dict:
    """The declared alpha schema as an engine search space.

    This mirrors the frozen provider's ``engine_param_ranges`` but handles the
    ``bool`` spec kind that the provider cannot express (A-VWAP has two bool
    knobs). It is a parameter-space expression, not a change to the provider:
    the search space is the registered schema, passed to the provider as an
    argument. Finding FUP02-F1 records this and proposes a lab-only repair.
    """
    ranges: dict = {}
    for name, spec in SCHEMAS[alpha_id].specs.items():
        if spec.kind == "fixed":
            ranges[name] = spec.fixed_value
        elif spec.kind in ("categorical", "bool"):
            ranges[name] = list(spec.choices)
        elif spec.kind == "int":
            ranges[name] = (int(spec.low), int(spec.high), int(spec.step or 1))
        else:
            ranges[name] = (float(spec.low), float(spec.high), float(spec.step or 0.0))
    return ranges


class FoldShardEngine(dfp.CutoffWalkForwardEngine):
    """The provider engine, but only the target fold(s) are optimized.

    The full canonical schedule is always supplied, so ``build_folds`` produces
    the canonical folds (ids, train windows, test segments). Filtering the list
    afterwards means one fold can be computed in isolation with exactly the
    selection the whole-arm call would make for it.
    """

    keep_fold_ids: set[int] | None = None

    def build_folds(self, idx):
        folds = super().build_folds(idx)
        if self.keep_fold_ids is None:
            return folds
        return [fold for fold in folds if int(fold.fold_id) in self.keep_fold_ids]


@contextmanager
def fold_shard_engine(fold_ids):
    previous_class = dfp.CutoffWalkForwardEngine
    previous_keep = FoldShardEngine.keep_fold_ids
    FoldShardEngine.keep_fold_ids = {int(value) for value in fold_ids}
    dfp.CutoffWalkForwardEngine = FoldShardEngine
    try:
        yield
    finally:
        dfp.CutoffWalkForwardEngine = previous_class
        FoldShardEngine.keep_fold_ids = previous_keep


def run_one_fold(alpha_id: str, frame: pd.DataFrame, schedule, fold_id: int,
                 trials: int, seed: int) -> dict:
    """Run one canonical fold through the installed Mode 4 pipeline."""
    with fold_shard_engine({fold_id}):
        return dfp.run_cutoff_walk_forward(
            alpha_id, frame, schedule, param_ranges=engine_param_ranges(alpha_id),
            strategy_class=dfp.ZeroSignalStrategy, optuna_trials=int(trials),
            seed=int(seed), route="event", one_way_fee=dfp.ONE_WAY_TAKER_FEE,
            slippage_bps=dfp.SLIPPAGE_BPS, alloc_per_trade=dfp.ALLOC_PER_TRADE,
            account_capital=dfp.ACCOUNT_CAPITAL)


# ---------------------------------------------------------------------------
# per-cutoff normalization
# ---------------------------------------------------------------------------

def _trial_rows(out: dict, fold_id: int) -> list[dict]:
    rows = out.get("trial_records") or []
    kept = [row for row in rows
            if int(row.get("schedule_fold_id", fold_id)) == int(fold_id)]
    return kept or list(rows)


def _nonfinite_fields(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        for path in (row.get("nonfinite_fields") or {}):
            counts[path] = counts.get(path, 0) + 1
    return dict(sorted(counts.items()))


def _fold_row(out: dict, fold_id: int) -> dict | None:
    for row in out.get("fold_selection_table") or []:
        if int(row.get("fold_id", -1)) == int(fold_id):
            return row
    return None


def cutoff_result(alpha_id: str, fold_id: int, cutoff: str, status: str, reason: str | None,
                  *, wall_seconds: float | None = None, out: dict | None = None) -> dict:
    """Normalize one fold's outcome; a non-scored fold keeps null metrics."""
    base = {
        "fold_id": int(fold_id),
        "cutoff": str(cutoff),
        "status": status,
        "reason": reason,
        "wall_seconds": (None if wall_seconds is None else round(float(wall_seconds), 3)),
        "trials": None,
        "trials_finite": None,
        "trials_nonfinite": None,
        "trials_pruned": None,
        "infeasible_trials": None,
        "candidate_count": None,
        "selected_params": None,
        "selected_digest": None,
        "selected_is_objective": None,
        "admissible": False,
        "admissible_reason": reason or "not scored",
        "event_account_runs": None,
        "event_scorer_calls": None,
        "selection_row": None,
        "nonfinite_value_fields": {},
        "attempts": [],
    }
    if out is None:
        return base
    params = (out.get("params_by_fold") or {}).get(str(fold_id))
    row = _fold_row(out, fold_id)
    trials = _trial_rows(out, fold_id)
    finite = [t for t in trials if t.get("objective") is not None]
    pruned = [t for t in trials if t.get("pruned")]
    status_counts = [(t.get("selection_metadata") or {}).get("status") for t in trials]
    infeasible = [value for value in status_counts
                  if value in ("INFEASIBLE", "INSUFFICIENT_BARS", "NOT_EVALUATED")]
    trace = out.get("trace") or {}
    admissible = bool(params) and bool(finite) and bool(row)
    base.update({
        "trials": len(trials),
        "trials_finite": len(finite),
        "trials_nonfinite": len(trials) - len(finite),
        "trials_pruned": len(pruned),
        "infeasible_trials": len(infeasible),
        "candidate_count": (row or {}).get("candidate_count"),
        "selected_params": params,
        "selected_digest": parameter_digest(params) if params else None,
        "selected_is_objective": (row or {}).get("selected_is_objective"),
        "admissible": admissible,
        "admissible_reason": (
            "selector returned parameters and at least one trial objective is finite"
            if admissible else
            ("no selected parameters for this fold" if not params else
             ("no fold selection row" if not row else "no finite trial objective"))),
        "event_account_runs": trace.get("event_account_runs"),
        "event_scorer_calls": trace.get("event_scorer_calls"),
        "selection_row": (dict(row) if row is not None else None),
    })
    return base


def is_budget_error(out: dict | None) -> bool:
    error = (out or {}).get("error") or ""
    return "BudgetExceeded" in error or "wall budget" in error


# ---------------------------------------------------------------------------
# artifact scaffolding
# ---------------------------------------------------------------------------

def _new_shard(cell: dict, arm: str, schedule) -> dict:
    return {
        "arm": arm,
        "schedule": schedule.as_record(),
        "status": "PENDING",
        "stop_reason": None,
        "cutoffs": list(schedule.cutoffs),
        "fold_count": len(schedule.cutoffs),
        "completed_fold_ids": [],
        "completed_cutoffs": [],
        "cutoff_results": [
            cutoff_result(cell["alpha_id"], fold_id, cutoff, "NOT_RUN",
                          "not attempted yet")
            for fold_id, cutoff in enumerate(schedule.cutoffs)
        ],
        "params_by_fold": {},
        "selected_digest": None,
        "selected_params_last": None,
        "fold_selection_table": [],
        "trial_count": 0,
        "trials_planned": len(schedule.cutoffs) * TRIALS,
        "nonfinite_values": {},
        "infeasible_trials": 0,
        "oos_used_for_selection": None,
        "evaluator_trace": {"event_account_runs": 0, "event_scorer_calls": 0},
        "scoring_backend": None,
        "candidate_selection_metric": "is_only_robust",
        "resolved_evaluator": "lab_event_account_scorer",
        "account": None,
        "account_status": "NOT_RUN",
        "account_reason": "the arm has not completed its cutoff list",
        "account_wall_seconds": None,
        "ok": False,
        "wall_seconds": 0.0,
        "first_attempt_at_utc": None,
        "last_update_at_utc": None,
    }


def new_artifact(cells: list[dict], schedules: dict, route_matrix_sha: str,
                 budget_revision: dict) -> dict:
    payload = {
        "schema": "regime_lab.fup02_paired_discovery_fullwindow.v1",
        "phase": "FUP-02",
        "study_id": STUDY_ID,
        "status": "RUN_IN_PROGRESS",
        "run_started_at_utc": utc_now_iso(),
        "registration": {
            "artifact": "evidence/corrective_mode4_v3/FUP-02/budget_revision.json",
            "sha256": sha256_file(RUN_DIR / "budget_revision.json"),
            "status": budget_revision["status"],
        },
        "development_window": {"start": WINDOW[0], "end": WINDOW[1], "snapshot_id": SNAPSHOT_ID,
                               "product": PRODUCT},
        "run_config": {
            "trials_per_cutoff": TRIALS,
            "trial_budget_registered_range": list(TRIAL_RANGE),
            "seed": SEED,
            "shard_status_vocabulary": list(SHARD_STATUS),
            "cutoff_status_vocabulary": list(CUTOFF_STATUS),
            "coverage_status_vocabulary": list(COVERAGE_STATUS),
            "per_shard_cap_seconds": budget_revision["resource_caps"]["per_shard_cap_seconds"],
            "per_cutoff_cap_seconds": budget_revision["resource_caps"]["per_cutoff_cap_seconds"],
            "per_invocation_budget_seconds": budget_revision["resource_caps"][
                "per_invocation_budget_seconds"],
            "total_wall_budget_seconds": budget_revision["resource_caps"][
                "total_wall_budget_seconds"],
            "workers": budget_revision["resource_caps"]["workers"],
            "cpu_limit": budget_revision["resource_caps"]["cpu_limit"],
            "shard_order_rule": (
                "execution order by measured per-cutoff cost ascending "
                "(A-HMA, A-HASH, A-SC, A-VWAP) then registered symbol order, both arms per "
                "cell; fixed before any outcome was inspected"
            ),
        },
        "economics": {
            "account_capital": dfp.ACCOUNT_CAPITAL,
            "entry_notional": dfp.ALLOC_PER_TRADE * dfp.ACCOUNT_CAPITAL,
            "alloc_per_trade": dfp.ALLOC_PER_TRADE,
            "one_way_fee": dfp.ONE_WAY_TAKER_FEE,
            "slippage_bps": dfp.SLIPPAGE_BPS,
            "fee_binding": dfp.bound_fee_kwargs(dfp.ONE_WAY_TAKER_FEE),
            "train_memory_days": CALENDAR_SPEC["train_memory_days"],
        },
        "mode4_contract": {
            "optimization_mode": dfp.MODE,
            "optimization_schedule": dfp.SCHEDULE,
            "candidate_selection_metric": dfp.METRIC,
            "scoring_backend": "endpoint",
            "resolved_evaluator": "lab_event_account_scorer",
            "oos_used_for_selection": False,
        },
        "regime_tape": {
            "artifact": "configs/lab05_full_emission_tape.json",
            "sha256": sha256_file(REGIME_TAPE),
            "symbol": "BTCUSDT",
            "per_symbol": False,
            "note": ("the same committed BTCUSDT emission tape RF-03/RF-04 used; kept so the "
                     "regime cutoff list is identical across cells and comparable with RF-04.6; "
                     "per-symbol model tapes are not claimed here"),
        },
        "route_matrix": {
            "artifact": "evidence/corrective_mode4_v3/FUP-01/route_matrix.json",
            "sha256": route_matrix_sha,
            "rule": ("every FUP-02 cell runs the route FUP-01/RF-02 qualified; the route "
                     "decision is read, never re-decided, and a cell without a qualified route "
                     "would be BLOCKED_CAPABILITY with null metrics"),
        },
        "matched_conditions": [
            "same economic account (20000 USDT, 2000 USDT entry notional, one-way fee 0.0004 "
            "bound once, slippage 1bp)",
            "same Mode 4 contract and per-fold causal schedule",
            "same training-memory rule (180 days)",
            "same trial budget per cutoff (32) and same seed (20260911)",
            "same development window and same evaluation dates",
            "only the cutoff list differs between the two arms of a cell",
        ],
        "cells": [],
        "invocations": [],
        "claim_limits": [
            "nested retrospective discovery on 2021-01-01..2023-12-31; no holdout and no live "
            "claim, contamination stays NESTED_RETROSPECTIVE",
            "no paired bootstrap, decay panel or matched control is computed here; "
            "statistical status is NOT_EVALUATED for every contrast",
            "the regime cutoff list comes from the committed BTCUSDT emission tape and is "
            "identical across symbols; per-symbol model tapes are not claimed",
            "the registered trial budget is 32-64/cutoff; FUP-02 executes the low end (32), "
            "equal for both arms",
            "a budget-stopped or non-run shard carries null metrics plus its exact reason",
        ],
    }
    for cell in cells:
        data = None
        payload["cells"].append({
            "cell": cell["cell"],
            "alpha_id": cell["alpha_id"],
            "symbol": cell["symbol"],
            "interval": cell["interval"],
            "route": cell["route"],
            "registered_route": cell["registered_route"],
            "route_status": cell["route_status"],
            "route_role": cell["route_role"],
            "route_reason": cell["route_reason"],
            "fup02_route_note": cell["fup02_route_note"],
            "route_source": cell["route_source"],
            "data": data,
            "executed": False,
            "shards": {arm: _new_shard(cell, arm, schedules[arm]) for arm in PRIMARY_ARMS},
            "contrast": None,
            "wall_seconds_total": 0.0,
            "coverage_status": None,
            "coverage_reason": None,
        })
    return payload


def cell_index(payload: dict) -> dict:
    return {cell["cell"]: cell for cell in payload["cells"]}


def configured(payload: dict) -> tuple:
    config = payload.get("run_config") or {}
    return (config.get("trials_per_cutoff"), config.get("seed"),
            payload.get("development_window", {}).get("start"),
            payload.get("development_window", {}).get("end"))


def run_config_matches(payload: dict) -> bool:
    return configured(payload) == (TRIALS, SEED, WINDOW[0], WINDOW[1])


# ---------------------------------------------------------------------------
# the shard runner
# ---------------------------------------------------------------------------

def data_record(frame: pd.DataFrame, snapshot_root: Path, manifest: dict) -> dict:
    return {
        "symbol": None,  # filled by caller
        "interval": None,
        "source": f"{SNAPSHOT_ID}/{PRODUCT}",
        "is_synthetic": False,
        "window": [str(frame.index[0]), str(frame.index[-1])],
        "bars": int(len(frame)),
        "snapshot_manifest": str(snapshot_root / "manifest.json"),
        "snapshot_manifest_sha256": sha256_file(snapshot_root / "manifest.json"),
        "snapshot_id": manifest.get("snapshot_id", SNAPSHOT_ID),
        "registered_snapshot_manifest_sha256": REGISTERED_SNAPSHOT_MANIFEST_SHA256,
    }


def record_attempt(cutoff_entry: dict, status: str, reason: str | None,
                   wall_seconds: float | None) -> None:
    attempts = cutoff_entry.setdefault("attempts", [])
    attempts.append({
        "attempt": len(attempts) + 1,
        "status": status,
        "reason": reason,
        "wall_seconds": (None if wall_seconds is None else round(float(wall_seconds), 3)),
        "at_utc": utc_now_iso(),
    })


def replace_cutoff_entry(entry: dict, result: dict) -> None:
    """Replace the entry body but never lose the attempt history."""
    attempts = list(entry.get("attempts") or [])
    entry.clear()
    entry.update(result)
    entry["attempts"] = attempts


def rebuild_fold_table(shard: dict) -> None:
    rows = []
    for entry in sorted(shard["cutoff_results"], key=lambda item: item["fold_id"]):
        if entry["status"] != "SCORED":
            continue
        row = entry.get("selection_row")
        if row is not None:
            rows.append(dict(row))
            continue
        rows.append({
            "fold_id": entry["fold_id"],
            "cutoff": entry["cutoff"],
            "selected_params": entry.get("selected_params"),
            "selected_is_objective": entry.get("selected_is_objective"),
            "candidate_count": entry.get("candidate_count"),
            "outer_oos_used_for_selection": False,
            "admissibility": entry.get("admissible_reason"),
        })
    shard["fold_selection_table"] = rows


def shard_wall_seconds(shard: dict) -> float:
    """Every attempt counts, including folds that were stopped and retried."""
    return round(sum(
        float(attempt.get("wall_seconds") or 0.0)
        for entry in shard["cutoff_results"]
        for attempt in (entry.get("attempts") or [])), 3)


def merge_scored_fold(shard: dict, result: dict) -> None:
    """Merge one SCORED fold into the arm summary. Never drops an existing fold.

    Idempotent: re-merging the same fold (a crash between checkpoint and
    ledger append, then a resume) must not double-count the evaluator trace.
    """
    fold_id = int(result["fold_id"])
    if result["status"] != "SCORED":
        return
    first_merge = str(fold_id) not in shard["params_by_fold"]
    if first_merge:
        shard["params_by_fold"][str(fold_id)] = result["selected_params"]
        if result.get("event_account_runs") is not None:
            shard["evaluator_trace"]["event_account_runs"] += int(result["event_account_runs"])
        if result.get("event_scorer_calls") is not None:
            shard["evaluator_trace"]["event_scorer_calls"] += int(result["event_scorer_calls"])
    completed = sorted(int(value) for value in
                       {*shard["completed_fold_ids"], fold_id})
    shard["completed_fold_ids"] = completed
    shard["completed_cutoffs"] = [str(item["cutoff"]) for item in shard["cutoff_results"]
                                  if item["fold_id"] in completed]
    shard["selected_params_last"] = (
        shard["params_by_fold"][str(completed[-1])] if completed else None)
    if shard["params_by_fold"]:
        shard["selected_digest"] = parameter_digest(dict(shard["params_by_fold"]))
        shard["oos_used_for_selection"] = False
    shard["scoring_backend"] = "endpoint"


def shard_trial_totals(shard: dict) -> None:
    trials = finite = nonfinite = pruned = infeasible = 0
    fields: dict[str, int] = {}
    for entry in shard["cutoff_results"]:
        if entry["status"] != "SCORED":
            continue
        trials += int(entry.get("trials") or 0)
        finite += int(entry.get("trials_finite") or 0)
        nonfinite += int(entry.get("trials_nonfinite") or 0)
        pruned += int(entry.get("trials_pruned") or 0)
        infeasible += int(entry.get("infeasible_trials") or 0)
        for path, count in (entry.get("nonfinite_value_fields") or {}).items():
            fields[path] = fields.get(path, 0) + int(count)
    shard["trial_count"] = trials
    shard["nonfinite_values"] = {
        "trials_with_nonfinite": nonfinite,
        "fields": dict(sorted(fields.items())),
    }
    shard["infeasible_trials"] = infeasible
    shard["trials_finite"] = finite
    shard["trials_pruned"] = pruned


def finalize_arm(cell: dict, arm: str, shard: dict, frame: pd.DataFrame,
                 budget_seconds: float) -> None:
    """Deploy the selected parameters through the provider's own account builder."""
    schedule = dfp.CutoffSchedule(
        arm=arm, cutoffs=tuple(shard["cutoffs"]),
        source=shard["schedule"]["source"],
        kind=shard["schedule"]["kind"],
        train_memory_days=shard["schedule"]["train_memory_days"],
        diagnostics=dict(shard["schedule"].get("diagnostics") or {}),
    )
    started = time.perf_counter()
    try:
        with wall_budget(budget_seconds):
            account = dfp._event_account_payload(
                cell["alpha_id"], frame, dict(shard["params_by_fold"]), schedule.cutoffs,
                dfp._frame_index(frame), one_way_fee=dfp.ONE_WAY_TAKER_FEE,
                slippage_bps=dfp.SLIPPAGE_BPS, account_capital=dfp.ACCOUNT_CAPITAL)
        account = dfp._scrub_payload(account)
        shard["account"] = account
        shard["account_status"] = account.get("status", "UNKNOWN")
        shard["account_reason"] = None
        shard["ok"] = shard["account_status"] == "EVALUATED"
    except BudgetExceeded as exc:
        shard["account"] = None
        shard["account_status"] = "BUDGET_STOPPED"
        shard["account_reason"] = f"the deployment account exceeded its budget: {exc}"
        shard["ok"] = False
    except Exception as exc:  # recorded, never invented
        shard["account"] = None
        shard["account_status"] = "ERROR"
        shard["account_reason"] = f"{type(exc).__name__}: {exc}"[:400]
        shard["ok"] = False
    finally:
        shard["account_wall_seconds"] = round(time.perf_counter() - started, 3)


def run_shard(cell: dict, arm: str, shard: dict, schedule, frame: pd.DataFrame, *,
              trials: int, seed: int, shard_cap: float, cutoff_cap: float,
              global_deadline: float, ledger: "TrialLedger",
              on_checkpoint, retry_errors: bool = False) -> None:
    """Run the shard's missing folds, then its deployment account.

    ``on_checkpoint`` is called after every fold so an interrupted invocation
    keeps exactly the folds that completed. A fold that ended in ``ERROR`` is
    terminal unless ``retry_errors`` is set: the error is deterministic for the
    same inputs and is recorded, never silently retried forever.
    """
    shard_started = time.monotonic()
    shard_deadline = shard_started + float(shard_cap)
    if shard["first_attempt_at_utc"] is None:
        shard["first_attempt_at_utc"] = utc_now_iso()
    if shard["status"] == "PENDING":
        # attempted but not complete at this checkpoint; the end of this function
        # overwrites the status when the shard actually finishes
        shard["status"] = "BUDGET_STOPPED"
        shard["stop_reason"] = "shard attempt started; not complete at this checkpoint"
    if retry_errors:
        for entry in shard["cutoff_results"]:
            if entry["status"] == "ERROR":
                replace_cutoff_entry(entry, cutoff_result(
                    cell["alpha_id"], entry["fold_id"], entry["cutoff"], "NOT_RUN",
                    "explicit --retry-errors retry requested"))
    for entry in shard["cutoff_results"]:
        fold_id = int(entry["fold_id"])
        if entry["status"] == "SCORED":
            continue
        if entry["status"] == "ERROR" and not retry_errors:
            continue
        remaining = min(shard_deadline - time.monotonic(),
                        global_deadline - time.monotonic())
        if remaining <= 0.0:
            reason = ("the registered per-shard cap of "
                      f"{shard_cap:.0f}s was reached before this fold"
                      if shard_deadline - time.monotonic() <= 0 else
                      "the invocation wall budget was exhausted before this fold")
            result = cutoff_result(cell["alpha_id"], fold_id, entry["cutoff"],
                                   "BUDGET_STOPPED", reason)
            replace_cutoff_entry(entry, result)
            record_attempt(entry, "BUDGET_STOPPED", reason, None)
            shard["stop_reason"] = reason
            break
        limit = min(float(cutoff_cap), remaining)
        started = time.perf_counter()
        try:
            with wall_budget(limit):
                out = run_one_fold(cell["alpha_id"], frame, schedule, fold_id, trials, seed)
        except BudgetExceeded as exc:
            wall = time.perf_counter() - started
            reason = f"per-cutoff cap of {limit:.1f}s exceeded: {exc}"
            result = cutoff_result(cell["alpha_id"], fold_id, entry["cutoff"],
                                   "BUDGET_STOPPED", reason, wall_seconds=wall)
            replace_cutoff_entry(entry, result)
            record_attempt(entry, "BUDGET_STOPPED", reason, wall)
            shard["stop_reason"] = reason
            break
        wall = time.perf_counter() - started
        if is_budget_error(out) or not out.get("ok"):
            if is_budget_error(out):
                status, reason = "BUDGET_STOPPED", (out.get("error") or "wall budget exceeded")
            else:
                status, reason = "ERROR", (out.get("error") or "the engine run failed")
        elif str(fold_id) not in (out.get("params_by_fold") or {}):
            status, reason = "ERROR", "the provider returned no selection for the target fold"
        else:
            status, reason = "SCORED", None
        result = cutoff_result(cell["alpha_id"], fold_id, entry["cutoff"], status, reason,
                               wall_seconds=wall, out=out if status == "SCORED" else None)
        replace_cutoff_entry(entry, result)
        record_attempt(entry, status, reason, wall)
        if status == "SCORED":
            entry["nonfinite_value_fields"] = _nonfinite_fields(_trial_rows(out, fold_id))
            merge_scored_fold(shard, entry)
            ledger.append_cutoff(cell, arm, entry, out)
            shard_trial_totals(shard)
            rebuild_fold_table(shard)
            shard["wall_seconds"] = shard_wall_seconds(shard)
            shard["last_update_at_utc"] = utc_now_iso()
            on_checkpoint()
        if status == "BUDGET_STOPPED":
            shard["stop_reason"] = reason
            break
    shard["wall_seconds"] = shard_wall_seconds(shard)
    shard["last_update_at_utc"] = utc_now_iso()
    completed = len(shard["completed_fold_ids"]) == shard["fold_count"]
    if completed and shard["account"] is None and shard["account_status"] != "ERROR":
        remaining = min(shard_deadline - time.monotonic(), global_deadline - time.monotonic())
        if remaining <= 0.0:
            shard["account_status"] = "BUDGET_STOPPED"
            shard["account_reason"] = (
                "the arm's folds completed but the deployment account was not reached inside "
                "the registered shard/invocation budget")
        else:
            finalize_arm(cell, arm, shard, frame, min(remaining, float(cutoff_cap)))
            shard["wall_seconds"] = round(shard["wall_seconds"]
                                          + float(shard.get("account_wall_seconds") or 0.0), 3)
    if len(shard["completed_fold_ids"]) == shard["fold_count"] and shard["account_status"] == "ERROR":
        shard["status"] = "FAILED"
        shard["stop_reason"] = shard["account_reason"]
    elif len(shard["completed_fold_ids"]) == shard["fold_count"] and shard["ok"]:
        shard["status"] = "COMPLETE"
        shard["stop_reason"] = None
    elif any(item["status"] == "ERROR" for item in shard["cutoff_results"]):
        shard["status"] = "FAILED"
        shard["stop_reason"] = shard["stop_reason"] or "one or more folds failed"
    elif shard["first_attempt_at_utc"] is None:
        shard["status"] = "PENDING"
    elif any(item["status"] in ("SCORED", "BUDGET_STOPPED", "ERROR")
             for item in shard["cutoff_results"]):
        shard["status"] = "BUDGET_STOPPED"
    else:
        shard["status"] = "PENDING"


def mark_not_run_budget(shard: dict, reason: str) -> None:
    if shard["status"] == "COMPLETE":
        return
    if shard["first_attempt_at_utc"] is not None and shard["completed_fold_ids"]:
        shard["status"] = "BUDGET_STOPPED"
        shard["stop_reason"] = shard.get("stop_reason") or reason
        return
    shard["status"] = "NOT_RUN_BUDGET"
    shard["stop_reason"] = reason
    for entry in shard["cutoff_results"]:
        if entry["status"] == "NOT_RUN":
            entry["reason"] = reason


def mark_insufficient(shard: dict, reason: str) -> None:
    shard["status"] = "INSUFFICIENT_DATA"
    shard["stop_reason"] = reason
    for entry in shard["cutoff_results"]:
        if entry["status"] == "NOT_RUN":
            entry["reason"] = reason


# ---------------------------------------------------------------------------
# contrasts, coverage, review
# ---------------------------------------------------------------------------

def build_contrast(cell: dict) -> dict | None:
    shards = cell["shards"]
    calendar, regime = shards["M4_CAL"], shards["M4_REGIME"]
    if calendar["status"] != "COMPLETE" or regime["status"] != "COMPLETE":
        return None
    contrast = pilot_runner.contrast_validity(calendar, regime, cell)
    contrast["checks"]["same_trial_budget"] = TRIALS
    contrast["route"] = cell["route"]
    contrast["route_role"] = cell["route_role"]
    contrast["claim_limit"] = (
        f"expanded-budget full-window paired discovery on {cell['cell']} "
        f"({WINDOW[0]}..{WINDOW[1]}, {TRIALS} trials/cutoff); no statistical claim, no edge "
        "inference, no holdout claim and no confirmation claim is made from it")
    if contrast["status"] == "VALID":
        contrast["implementation_fidelity"] = "AS_SPECIFIED"
        contrast["implementation_fidelity_reason"] = (
            "both arms selected parameters without outer OOS, the event account is EVALUATED "
            "with a per-fill ledger and the two arms used different cutoffs")
    else:
        contrast["implementation_fidelity"] = "DEVIATED"
        contrast["implementation_fidelity_reason"] = (
            "; ".join(contrast["reasons"]) or "the paired contrast failed a validity check")
    contrast["statistical_status"] = "NOT_EVALUATED"
    contrast["economic_status"] = "NOT_EVALUATED"
    contrast["status_reason"] = (
        "expanded-budget discovery run; no paired bootstrap, decay panel or matched control is "
        "computed in FUP-02, so the economic status stays NOT_EVALUATED")
    return contrast


def cell_coverage_status(cell: dict) -> tuple[str, str]:
    shards = cell["shards"]
    statuses = {arm: shards[arm]["status"] for arm in PRIMARY_ARMS}
    if any(value == "INSUFFICIENT_DATA" for value in statuses.values()):
        return "INSUFFICIENT_DATA", (
            "at least one arm could not load the registered snapshot data: "
            + "; ".join(f"{arm}: {shards[arm]['stop_reason']}" for arm in PRIMARY_ARMS
                        if shards[arm]["status"] == "INSUFFICIENT_DATA"))
    if all(value == "COMPLETE" for value in statuses.values()):
        contrast = cell.get("contrast") or {}
        if contrast.get("status") == "VALID":
            return "RUN_VALID", (
                "both arms completed the full cutoff list on the qualified event route and the "
                "paired contrast is VALID; economic status NOT_EVALUATED (no inference here)")
        return "RUN_NOT_EVALUABLE", (
            "both arms completed but the paired contrast is "
            f"{contrast.get('status')}: {'; '.join(contrast.get('reasons') or [])}")
    if any(value == "FAILED" for value in statuses.values()):
        return "FAILED", "; ".join(
            f"{arm}: {shards[arm]['stop_reason']}" for arm in PRIMARY_ARMS
            if shards[arm]["status"] == "FAILED")
    if any(value == "BUDGET_STOPPED" for value in statuses.values()):
        return "BUDGET_STOPPED", "; ".join(
            f"{arm}: {shards[arm]['stop_reason'] or 'stopped by the registered budget'}"
            for arm in PRIMARY_ARMS if shards[arm]["status"] == "BUDGET_STOPPED")
    if all(value == "NOT_RUN_BUDGET" for value in statuses.values()):
        return "NOT_RUN_BUDGET", (
            "neither arm was reached inside the registered invocation budget: "
            + "; ".join(shards[arm]["stop_reason"] or "" for arm in PRIMARY_ARMS))
    if all(value == "PENDING" for value in statuses.values()):
        return "NOT_RUN", "no shard of this cell has been attempted yet"
    return "BUDGET_STOPPED", (
        "at least one arm is incomplete (" + ", ".join(
            f"{arm}={statuses[arm]}" for arm in PRIMARY_ARMS) + ")")


def _cell_account_metrics(cell: dict) -> dict | None:
    out = {}
    for arm in PRIMARY_ARMS:
        shard = cell["shards"][arm]
        if shard["status"] == "COMPLETE" and shard["account"]:
            report = shard["account"].get("engine_report") or {}
            trades = report.get("num_trades")
            if trades is None:
                trades = shard["account"].get("engine_fill_count")
            out[arm] = {
                "equity_last": shard["account"].get("equity_last"),
                "total_return_pct": report.get("total_return_pct"),
                "sharpe": report.get("sharpe"),
                "num_trades": trades,
                "max_drawdown_pct": report.get("max_drawdown_pct"),
                "fill_count": shard["account"].get("fill_count"),
                "wall_seconds": shard.get("wall_seconds"),
            }
    return out or None


def refresh_cell_rollups(payload: dict) -> None:
    for cell in payload["cells"]:
        cell["contrast"] = build_contrast(cell)
        cell["executed"] = any(cell["shards"][arm]["first_attempt_at_utc"] is not None
                               for arm in PRIMARY_ARMS)
        for arm in PRIMARY_ARMS:
            shard = cell["shards"][arm]
            if shard["status"] == "PENDING" and shard["first_attempt_at_utc"] is not None:
                shard["status"] = "BUDGET_STOPPED"
                shard["stop_reason"] = (
                    shard["stop_reason"] or
                    ("the shard was attempted but no fold completed before the stop"
                     if not shard["completed_fold_ids"] else
                     "the shard was attempted but has not completed its fold list"))
        cell["wall_seconds_total"] = round(sum(
            float(cell["shards"][arm].get("wall_seconds") or 0.0) for arm in PRIMARY_ARMS), 3)
        status, reason = cell_coverage_status(cell)
        cell["coverage_status"] = status
        cell["coverage_reason"] = reason
    complete = [cell for cell in payload["cells"]
                if cell["coverage_status"] in ("RUN_VALID", "RUN_NOT_EVALUABLE")]
    stopped = [cell for cell in payload["cells"]
               if cell["coverage_status"] in ("BUDGET_STOPPED", "NOT_RUN_BUDGET", "FAILED",
                                              "INSUFFICIENT_DATA")]
    if len(complete) == len(payload["cells"]):
        payload["status"] = "COMPLETE_ALL_CELLS"
    elif payload["status"] != "COMPLETE_ALL_CELLS":
        payload["status"] = ("PARTIAL_BUDGET_STOPPED"
                             if stopped else "RUN_IN_PROGRESS")


def build_cell_coverage(payload: dict, full_sha: str) -> dict:
    cells = []
    for index, cell in enumerate(payload["cells"]):
        refs = [f"evidence/corrective_mode4_v3/FUP-02/paired_discovery_fullwindow.json"
                f"#/cells/{index}",
                "evidence/corrective_mode4_v3/FUP-01/route_matrix.json"]
        metrics = _cell_account_metrics(cell)
        entry = {
            "cell": cell["cell"],
            "alpha_id": cell["alpha_id"],
            "symbol": cell["symbol"],
            "route": cell["route"],
            "route_status": cell["route_status"],
            "route_role": cell["route_role"],
            "coverage_status": cell["coverage_status"],
            "reason": cell["coverage_reason"],
            "executed": cell["executed"],
            "arm_status": {arm: cell["shards"][arm]["status"] for arm in PRIMARY_ARMS},
            "completed_folds": {arm: len(cell["shards"][arm]["completed_fold_ids"])
                                for arm in PRIMARY_ARMS},
            "planned_folds": {arm: cell["shards"][arm]["fold_count"] for arm in PRIMARY_ARMS},
            "account_metrics": metrics,
            "account_metrics_reason": (
                None if metrics else
                "no arm completed; account metrics are null and are never replaced with a "
                "zero or an estimate"),
            "contrast_status": (cell.get("contrast") or {}).get("status"),
            "evidence_ref": refs[0],
            "evidence_refs": refs,
        }
        cells.append(entry)
    counts = {status: sum(1 for cell in cells if cell["coverage_status"] == status)
              for status in COVERAGE_STATUS}
    counts["planned_cells"] = len(cells)
    counts["total_classified"] = len(cells)
    executed = sum(1 for cell in cells if cell["executed"])
    return {
        "schema": "regime_lab.fup02_cell_coverage.v1",
        "phase": "FUP-02",
        "study_id": STUDY_ID,
        "status": (f"FUP02_COVERAGE_{'CLOSED' if not counts['BUDGET_STOPPED'] and not counts['NOT_RUN_BUDGET'] and not counts['FAILED'] and not counts['INSUFFICIENT_DATA'] else 'PARTIAL'}"
                   f"_{executed}_EXECUTED"),
        "status_vocabulary": list(COVERAGE_STATUS),
        "rule": (
            "one row per planned primary cell (4 alphas x 5 symbols); the route is merged from "
            "FUP-01/route_matrix.json and the run result from "
            "FUP-02/paired_discovery_fullwindow.json. A non-executed or non-complete cell "
            "carries null metrics with a reason, never a zero"
        ),
        "sources": [
            {"artifact": "evidence/corrective_mode4_v3/FUP-02/paired_discovery_fullwindow.json",
             "sha256": full_sha},
            {"artifact": "evidence/corrective_mode4_v3/FUP-01/route_matrix.json",
             "sha256": sha256_file(FUP01_DIR / "route_matrix.json")},
        ],
        "registered_cohort": {
            "alphas": list(ALPHAS), "symbols": list(SYMBOLS),
            "data": f"{SNAPSHOT_ID}, development {WINDOW[0]}..{WINDOW[1]}",
        },
        "route_matrix_ref": "evidence/corrective_mode4_v3/FUP-01/route_matrix.json",
        "counts": counts,
        "cells": cells,
    }


def build_coverage_review(payload: dict, full_sha: str) -> dict:
    per_arm = []
    for cell in payload["cells"]:
        for arm in PRIMARY_ARMS:
            shard = cell["shards"][arm]
            scored = [entry for entry in shard["cutoff_results"]
                      if entry["status"] == "SCORED"]
            admissible = [entry for entry in scored if entry["admissible"]]
            trials = sum(int(entry.get("trials") or 0) for entry in scored)
            finite = sum(int(entry.get("trials_finite") or 0) for entry in scored)
            nonfinite = sum(int(entry.get("trials_nonfinite") or 0) for entry in scored)
            pruned = sum(int(entry.get("trials_pruned") or 0) for entry in scored)
            infeasible = sum(int(entry.get("infeasible_trials") or 0) for entry in scored)
            candidate_counts = [entry.get("candidate_count") for entry in scored
                                if entry.get("candidate_count") is not None]
            per_arm.append({
                "cell": cell["cell"],
                "arm": arm,
                "shard_status": shard["status"],
                "cutoffs_planned": shard["fold_count"],
                "cutoffs_scored": len(scored),
                "admissible_cutoffs": len(admissible),
                "admissible_over_scored": (round(len(admissible) / len(scored), 6)
                                           if scored else None),
                "admissible_over_planned": round(len(admissible) / shard["fold_count"], 6),
                "trials_total": trials,
                "trials_finite": finite,
                "trials_nonfinite": nonfinite,
                "trials_pruned": pruned,
                "infeasible_trials": infeasible,
                "finite_fraction": (round(finite / trials, 6) if trials else None),
                "candidate_count_min": (min(candidate_counts) if candidate_counts else None),
                "candidate_count_max": (max(candidate_counts) if candidate_counts else None),
                "nonfinite_fields": shard["nonfinite_values"].get("fields", {}),
            })
    planned_folds = sum(row["cutoffs_planned"] for row in per_arm)
    scored_folds = sum(row["cutoffs_scored"] for row in per_arm)
    admissible_folds = sum(row["admissible_cutoffs"] for row in per_arm)
    trials_total = sum(row["trials_total"] for row in per_arm)
    finite_total = sum(row["trials_finite"] for row in per_arm)
    nonfinite_total = sum(row["trials_nonfinite"] for row in per_arm)
    pruned_total = sum(row["trials_pruned"] for row in per_arm)
    infeasible_total = sum(row["infeasible_trials"] for row in per_arm)
    admissible_over_scored = (admissible_folds / scored_folds) if scored_folds else None
    bad_trial_fraction = ((nonfinite_total + infeasible_total) / trials_total
                          if trials_total else None)
    if scored_folds == 0:
        status = "NO_CUTOFF_SCORED_YET"
    elif scored_folds < planned_folds:
        status = "PARTIAL_COVERAGE_REVIEW"
    elif admissible_over_scored is not None and admissible_over_scored < 0.80:
        status = "COVERAGE_INSUFFICIENT_ESCALATE_TO_64"
    elif bad_trial_fraction is not None and bad_trial_fraction > 0.25:
        status = "COVERAGE_INSUFFICIENT_ESCALATE_TO_64"
    else:
        status = "COVERAGE_SUFFICIENT_FOR_FREEZE"
    return {
        "schema": "regime_lab.fup02_coverage_review.v1",
        "phase": "FUP-02",
        "study_id": STUDY_ID,
        "status": status,
        "rule": (
            "coverage review before any final design freeze (registered in "
            "budget_revision.json#/coverage_review_rule): admissible means the selector "
            "returned parameters and at least one trial objective is finite; escalate to 64 "
            "trials/cutoff in a revised budget if admissible_over_scored < 0.80 or "
            "(nonfinite+infeasible)/trials > 0.25"
        ),
        "admissible_definition": (
            "scored cutoff with selected parameters and at least one finite trial objective"),
        "escalation_thresholds": {
            "min_admissible_over_scored": 0.80,
            "max_bad_trial_fraction": 0.25,
        },
        "deep_selector_audit_limitation": (
            "the public provider payload does not expose selector/cluster/fallback fields; "
            "candidate_count is recorded and the RF-04.2 transparency ledger remains the deep "
            "audit. This review does not claim plateau/cluster coverage"),
        "aggregate": {
            "shards_planned": len(per_arm),
            "cutoffs_planned": planned_folds,
            "cutoffs_scored": scored_folds,
            "admissible_cutoffs": admissible_folds,
            "admissible_over_scored": (round(admissible_over_scored, 6)
                                       if admissible_over_scored is not None else None),
            "trials_total": trials_total,
            "trials_finite": finite_total,
            "trials_nonfinite": nonfinite_total,
            "trials_pruned": pruned_total,
            "infeasible_trials": infeasible_total,
            "bad_trial_fraction": (round(bad_trial_fraction, 6)
                                   if bad_trial_fraction is not None else None),
        },
        "per_cell_arm": per_arm,
        "sources": [
            {"artifact": "evidence/corrective_mode4_v3/FUP-02/paired_discovery_fullwindow.json",
             "sha256": full_sha},
        ],
    }


def write_checkpoint(writer: EvidenceWriter, payload: dict) -> dict:
    payload["last_checkpoint_at_utc"] = utc_now_iso()
    refresh_cell_rollups(payload)
    full = writer.write_json("paired_discovery_fullwindow.json", payload,
                             schema=payload["schema"])
    coverage = build_cell_coverage(payload, full["sha256"])
    coverage_record = writer.write_json("cell_coverage.json", coverage,
                                        schema=coverage["schema"])
    review = build_coverage_review(payload, full["sha256"])
    review_record = writer.write_json("coverage_review.json", review, schema=review["schema"])
    payload["cell_coverage_sha256"] = coverage_record["sha256"]
    payload["coverage_review_sha256"] = review_record["sha256"]
    return {"fullwindow": full, "cell_coverage": coverage_record, "coverage_review": review_record}


# ---------------------------------------------------------------------------
# trial ledger
# ---------------------------------------------------------------------------

class TrialLedger:
    """Append-only full trial retention keyed by (cell, arm, fold, trial, params)."""

    def __init__(self, writer: EvidenceWriter):
        self.writer = writer
        self.path = RUN_DIR / "trial_ledger.jsonl"
        self.seen: set[str] = set()
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                self.seen.add(row.get("trial_key"))

    @staticmethod
    def _key(cell: str, arm: str, fold_id: int, row: dict) -> str:
        return json_stable([cell, arm, int(fold_id), int(row.get("trial_id", -1)),
                            row.get("params"), row.get("objective")])

    def append_cutoff(self, cell: dict, arm: str, entry: dict, out: dict) -> int:
        rows = []
        fold_id = int(entry["fold_id"])
        for row in _trial_rows(out, fold_id):
            key = self._key(cell["cell"], arm, fold_id, row)
            if key in self.seen:
                continue
            self.seen.add(key)
            rows.append({
                "schema": "crypto_regime_lab.trial_ledger_row.v1",
                "lab_run_id": RUN_ID,
                "study_id": STUDY_ID,
                "cell": cell["cell"],
                "arm": arm,
                "fold_id": fold_id,
                "cutoff": entry["cutoff"],
                "trial_key": key,
                "trial_id": row.get("trial_id"),
                "params": row.get("params"),
                "objective": row.get("objective"),
                "mean_is_sharpe": row.get("mean_is_sharpe"),
                "mean_oos_sharpe": row.get("mean_oos_sharpe"),
                "pruned": row.get("pruned"),
                "fold_seed": row.get("fold_seed"),
                "schedule_fold_id": row.get("schedule_fold_id"),
                "trial_study_id": row.get("study_id"),
                "selection_metadata": row.get("selection_metadata") or {},
                "nonfinite_fields": row.get("nonfinite_fields") or {},
            })
        return self.writer.append_jsonl("trial_ledger.jsonl", rows) if rows else 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def shard_plan(payload: dict, selected: set[str] | None = None) -> list[tuple[dict, str]]:
    by_cell = cell_index(payload)
    plan = []
    for alpha in SHARD_ORDER_ALPHAS:
        for symbol in SYMBOLS:
            cell = by_cell[f"{alpha}/{symbol}"]
            for arm in PRIMARY_ARMS:
                if selected is None or f"{cell['cell']}:{arm}" in selected or cell["cell"] in selected:
                    plan.append((cell, arm))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register-budget", action="store_true",
                        help="write budget_revision.json; must run before any shard")
    parser.add_argument("--run", action="store_true", help="execute shards")
    parser.add_argument("--status", action="store_true", help="print the checkpoint status")
    parser.add_argument("--reconcile", action="store_true",
                        help="recompute rollups/statuses from the checkpoint without running")
    parser.add_argument("--resume", action="store_true",
                        help="continue an existing paired_discovery_fullwindow.json")
    parser.add_argument("--force", action="store_true",
                        help="discard an existing fullwindow artifact and start fresh")
    parser.add_argument("--shards", default=None,
                        help="comma-separated cell[:arm] subset (default: all)")
    parser.add_argument("--budget-seconds", type=float, default=None,
                        help="invocation wall budget (default: registered)")
    parser.add_argument("--shard-cap-seconds", type=float, default=None)
    parser.add_argument("--cutoff-cap-seconds", type=float, default=None)
    parser.add_argument("--trials", type=int, default=None,
                        help="must be inside the registered 32-64 range")
    parser.add_argument("--retry-errors", action="store_true",
                        help="re-attempt folds recorded as ERROR (deterministic errors will recur)")
    args = parser.parse_args()

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)

    if args.register_budget and not (args.run or args.status):
        summary = register_budget(writer, args.force)
        print(json.dumps({
            "artifact": summary["record"],
            "status": summary["payload"]["status"],
        }, indent=2))
        return 0

    budget = load_budget_revision()
    caps = budget["resource_caps"]
    trials = int(args.trials if args.trials is not None else TRIALS)
    if not TRIAL_RANGE[0] <= trials <= TRIAL_RANGE[1]:
        raise SystemExit(f"--trials {trials} is outside the registered {TRIAL_RANGE}")
    if trials != int(budget["trial_budget"]["executed_per_cutoff"]):
        raise SystemExit(
            "the executed trial budget differs from budget_revision.json; register a revised "
            "budget before running")
    shard_cap = float(args.shard_cap_seconds or caps["per_shard_cap_seconds"])
    cutoff_cap = float(args.cutoff_cap_seconds or caps["per_cutoff_cap_seconds"])
    if shard_cap > 900.0 + 1e-9:
        raise SystemExit("the T3 per-shard cap must stay <= 900s")
    budget_seconds = float(args.budget_seconds or caps["per_invocation_budget_seconds"])

    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = load_json(snapshot_root / "manifest.json")
    manifest_sha = sha256_file(snapshot_root / "manifest.json")
    if manifest_sha != REGISTERED_SNAPSHOT_MANIFEST_SHA256:
        raise SystemExit(
            f"snapshot manifest sha256 {manifest_sha} does not match the registered "
            f"{REGISTERED_SNAPSHOT_MANIFEST_SHA256}")

    route_matrix = fup01_route_matrix()
    cells = cell_cohort(route_matrix)
    schedules = build_schedules()

    full_path = RUN_DIR / "paired_discovery_fullwindow.json"
    if args.status:
        if not full_path.is_file():
            raise SystemExit("no paired_discovery_fullwindow.json to report on")
        payload = load_json(full_path)
        refresh_cell_rollups(payload)
        print(json.dumps({
            "status": payload["status"],
            "cells": {cell["cell"]: {
                "coverage_status": cell["coverage_status"],
                "shards": {arm: cell["shards"][arm]["status"] for arm in PRIMARY_ARMS},
                "completed_folds": {arm: len(cell["shards"][arm]["completed_fold_ids"])
                                    for arm in PRIMARY_ARMS},
            } for cell in payload["cells"]},
            "coverage_counts": {
                status: sum(1 for cell in payload["cells"]
                            if cell["coverage_status"] == status)
                for status in COVERAGE_STATUS},
        }, indent=2))
        return 0
    if args.reconcile:
        if not full_path.is_file():
            raise SystemExit("no paired_discovery_fullwindow.json to reconcile")
        payload = load_json(full_path)
        records = write_checkpoint(writer, payload)
        print(json.dumps({
            "status": payload["status"],
            "fullwindow": records["fullwindow"],
            "coverage_counts": {
                status: sum(1 for cell in payload["cells"]
                            if cell["coverage_status"] == status)
                for status in COVERAGE_STATUS},
        }, indent=2))
        return 0
    if full_path.exists() and not (args.resume or args.force):
        raise SystemExit(
            "paired_discovery_fullwindow.json exists; pass --resume to continue it or --force "
            "to redo")
    if full_path.exists() and args.resume:
        payload = load_json(full_path)
        if not run_config_matches(payload):
            raise SystemExit(
                "the existing artifact's run_config does not match this runner; pass --force "
                "to redo explicitly")
        if (payload.get("registration") or {}).get("sha256") != sha256_file(
                RUN_DIR / "budget_revision.json"):
            raise SystemExit(
                "the existing artifact was produced under a different budget_revision.json; "
                "pass --force to redo explicitly")
    else:
        payload = new_artifact(cells, schedules, sha256_file(FUP01_DIR / "route_matrix.json"),
                               budget)

    selected = None
    if args.shards:
        selected = {value.strip() for value in args.shards.split(",") if value.strip()}

    plan = shard_plan(payload, selected)
    ledger = TrialLedger(writer)
    invocation_started = time.monotonic()
    invocation = {
        "invocation": len(payload["invocations"]) + 1,
        "started_at_utc": utc_now_iso(),
        "budget_seconds": budget_seconds,
        "shard_cap_seconds": shard_cap,
        "cutoff_cap_seconds": cutoff_cap,
        "trials_per_cutoff": trials,
        "planned_shards": [f"{cell['cell']}:{arm}" for cell, arm in plan],
        "ran_shards": [],
        "stop_reason": None,
    }
    global_deadline = invocation_started + budget_seconds
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    data_errors: dict[str, str] = {}

    try:
        for cell, arm in plan:
            shard = cell["shards"][arm]
            if shard["status"] == "COMPLETE":
                invocation["ran_shards"].append({"shard": f"{cell['cell']}:{arm}",
                                                 "result": "ALREADY_COMPLETE"})
                continue
            if time.monotonic() >= global_deadline:
                reason = (f"the invocation budget of {budget_seconds:.0f}s was exhausted before "
                          f"{cell['cell']}:{arm} started")
                mark_not_run_budget(shard, reason)
                invocation["ran_shards"].append({"shard": f"{cell['cell']}:{arm}",
                                                 "result": "NOT_RUN_BUDGET"})
                continue
            key = (cell["symbol"], cell["interval"])
            if key not in frames and cell["cell"] not in data_errors:
                try:
                    frames[key] = load_window_frame(snapshot_root, cell["symbol"],
                                                    cell["interval"])
                except Exception as exc:
                    data_errors[cell["cell"]] = f"{type(exc).__name__}: {exc}"[:400]
            if cell["cell"] in data_errors:
                mark_insufficient(shard, f"snapshot load failed: {data_errors[cell['cell']]}")
                invocation["ran_shards"].append({"shard": f"{cell['cell']}:{arm}",
                                                 "result": "INSUFFICIENT_DATA"})
                write_checkpoint(writer, payload)
                continue
            frame = frames[key]
            if cell["data"] is None:
                record = data_record(frame, snapshot_root, manifest)
                record["symbol"] = cell["symbol"]
                record["interval"] = cell["interval"]
                cell["data"] = record
            with writer.attempt(f"FUP02.shard.{cell['cell']}.{arm}") as att:
                run_shard(cell, arm, shard, schedules[arm], frame, trials=trials, seed=SEED,
                          shard_cap=shard_cap, cutoff_cap=cutoff_cap,
                          global_deadline=global_deadline, ledger=ledger,
                          on_checkpoint=lambda: write_checkpoint(writer, payload),
                          retry_errors=args.retry_errors)
                att.detail = {
                    "status": shard["status"],
                    "completed_folds": len(shard["completed_fold_ids"]),
                    "fold_count": shard["fold_count"],
                    "wall_seconds": shard["wall_seconds"],
                }
            invocation["ran_shards"].append({
                "shard": f"{cell['cell']}:{arm}",
                "result": shard["status"],
                "completed_folds": len(shard["completed_fold_ids"]),
                "wall_seconds": shard["wall_seconds"],
            })
            write_checkpoint(writer, payload)
    finally:
        invocation["ended_at_utc"] = utc_now_iso()
        invocation["wall_seconds"] = round(time.monotonic() - invocation_started, 3)
        if invocation["stop_reason"] is None:
            invocation["stop_reason"] = (
                "invocation completed its planned shard list"
                if time.monotonic() < global_deadline else
                "invocation budget exhausted")
        payload["invocations"].append(invocation)
        write_checkpoint(writer, payload)

    total_wall = sum(float(row.get("wall_seconds") or 0.0)
                     for row in payload["invocations"])
    print(json.dumps({
        "status": payload["status"],
        "invocation": invocation,
        "total_wall_seconds": round(total_wall, 3),
        "coverage": {status: sum(1 for cell in payload["cells"]
                                 if cell["coverage_status"] == status)
                     for status in COVERAGE_STATUS},
        "cells": [{"cell": cell["cell"], "coverage": cell["coverage_status"],
                   "shards": {arm: cell["shards"][arm]["status"] for arm in PRIMARY_ARMS}}
                  for cell in payload["cells"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
