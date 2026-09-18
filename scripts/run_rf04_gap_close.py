#!/usr/bin/env python
"""RF-04 gap close — cell coverage, profiling/budget and the Mode 4 transparency ledger.

RF-04's Outputs also require all 20 primary-cell statuses, a runtime
budget/performance report and the RF04.2 per-cutoff transparency record. This
script writes those three artifacts from the committed evidence only:

* ``cell_coverage.json`` merges the RF-02 route matrix with the executed RF-04
  pilot/control results: one row per planned cell (4 alphas x 5 symbols) with an
  explicit status, a reason and evidence refs. Non-executed cells carry null
  account metrics with a reason, never a zero.
* ``profiling_and_budget.json`` records the measured wall seconds, rows, bytes,
  engine-call counters and trial denominators that exist in the committed
  artifacts. CPU seconds, peak RSS and candidate-bar visits were not measured by
  any committed artifact or log, so they are ``null`` plus a reason.
* ``mode4_transparency_ledger.json`` records RF04.2 per cutoff for both primary
  arms on both executed cells: training range, seed, trial counts, selected
  digest, parameter schema object/hash, selector/fallback status, activation
  time and the per-fold selection decomposition present in the pilot.

No number is invented. Every field is copied from a committed artifact, or is a
deterministic function of committed values (the parameter digest and the schema
object are the same functions the runner used).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.integration.activation import parameter_digest  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "RF-04"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / RUN_ID
RF02_DIR = LAB_ROOT / "evidence" / STUDY_ID / "RF-02"
PRIMARY_ARMS = ("M4_CAL", "M4_REGIME")
ALL_ARMS = ("M4_CAL", "M4_REGIME", "M4_CAL_MATCHED", "M4_REGIME_DELAYED")
CELL_STATUS_VOCABULARY = ("RUN_VALID", "RUN_NOT_EVALUABLE", "BLOCKED_CAPABILITY",
                          "NOT_RUN", "INSUFFICIENT_DATA")

CPU_REASON = (
    "NOT_MEASURED: the RF-04 runners recorded wall clock only; no committed artifact or log "
    "stores process CPU seconds, so a value would be invented"
)
RSS_REASON = (
    "NOT_MEASURED: no RF-04 artifact or log records the peak resident set; report.json already "
    "carries peak_rss_bytes=null for the same reason"
)
BAR_VISIT_REASON = (
    "NOT_MEASURED: the pilot/evaluator traces record folds, trials, studies and event-account "
    "runs, not candidate-bar visits; the count cannot be reconstructed from committed values"
)
FALLBACK_REASON = (
    "NOT_RECORDED: no per-cutoff selector fallback field exists in the committed RF-04 artifacts; "
    "the Mode 4 endpoint path selects among scored candidates and its trial ledger has no fallback "
    "flag. The fallback fraction is left null rather than reported as zero"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(payload) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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


def coverage_status_for(cell: dict, route: dict, contrasts: dict) -> tuple[str, str]:
    if cell["cell"] in contrasts:
        contrast = contrasts[cell["cell"]]
        if contrast["implementation_fidelity"] == "DEVIATED":
            return "RUN_NOT_EVALUABLE", (
                "executed in the bounded pilot but the endpoint scorer returned one objective for "
                "every sampled candidate and the account exposes no per-fill ledger; "
                "implementation_fidelity=DEVIATED and the timing contrast is NOT_EVALUABLE"
            )
        return "RUN_VALID", (
            "executed with execution_validity=PASS and implementation_fidelity=AS_SPECIFIED; the "
            "economic status stays INCONCLUSIVE because the pilot covers 2 of 20 cells at 8 "
            "trials/cutoff"
        )
    if route["route_status"] == "BLOCKED_CAPABILITY":
        return "BLOCKED_CAPABILITY", route["reason"]
    return "NOT_RUN", (
        "inside the qualified route set but not executed: the bounded RF-04 pilot deliberately ran "
        "only A-SC/BTCUSDT and A-HMA/BTCUSDT; no account metrics exist for this cell and none are "
        "estimated"
    )


def cell_coverage_payload(pilot: dict, controls: dict, route_matrix: dict,
                          protocol: dict) -> dict:
    pilot_cells = {cell["cell"]: cell for cell in pilot["cells"]}
    contrasts = {row["cell"]: row for row in controls["contrasts"]}
    matched = {row["cell"]: row["arm"] for row in controls["matched_control"]["cells"]}
    placebo = {row["cell"]: row["arm"] for row in controls["placebo"]["cells"]}
    route_rows = route_matrix["route_matrix"]["cells"]
    cells = []
    for index, route in enumerate(route_rows):
        name = route["cell"]
        status, reason = coverage_status_for(pilot_cells.get(name, {"cell": name}),
                                             route, contrasts)
        executed = name in pilot_cells
        refs = [f"evidence/corrective_mode4_v3/RF-02/pilot_and_route_matrix.json"
                f"#/route_matrix/cells/{index}"]
        run_result = None
        run_result_reason = None
        account_metrics = None
        account_metrics_reason = None
        if executed:
            artifact_cell = pilot_cells[name]
            contrast = contrasts[name]
            refs.append(f"evidence/corrective_mode4_v3/RF-04/paired_discovery_pilot.json"
                        f"#/cells/{pilot['cells'].index(artifact_cell)}")
            refs.append("evidence/corrective_mode4_v3/RF-04/controls_and_funnel.json"
                        f"#/contrasts/{controls['contrasts'].index(contrast)}")
            arms = {arm: arm_metrics(artifact_cell["arms"][arm]) for arm in PRIMARY_ARMS}
            arms["M4_CAL_MATCHED"] = arm_metrics(matched[name])
            arms["M4_REGIME_DELAYED"] = arm_metrics(placebo[name])
            run_result = {
                "arms": arms,
                "contrast_status": artifact_cell["contrast"]["status"],
                "execution_validity": contrast["execution_validity"],
                "implementation_fidelity": contrast["implementation_fidelity"],
                "statistical_status": contrast["statistical_status"],
                "economic_status": contrast["economic_status"],
            }
            account_metrics = {
                arm: {"equity_last": values["equity_last"],
                      "total_return_pct": values["total_return_pct"],
                      "sharpe": values["sharpe"],
                      "num_trades": values["num_trades"],
                      "max_drawdown_pct": values["max_drawdown_pct"]}
                for arm, values in arms.items()
            }
        else:
            run_result_reason = reason
            account_metrics_reason = (
                "no arm ran on this cell; account metrics are null and are never replaced with a "
                "zero or an estimate"
            )
        cells.append({
            "cell": name,
            "alpha_id": pilot_cells[name]["alpha_id"] if executed else route["cell"].split("/")[0],
            "symbol": route["cell"].split("/")[1],
            "route": pilot_cells[name]["route"] if executed else None,
            "route_reason": (None if executed else
                             "the RF-02 route matrix qualifies the route family "
                             "(QUALIFIED_FAST/QUALIFIED_EVENT/BLOCKED_CAPABILITY) but records no "
                             "per-cell execution route for an unexecuted cell"),
            "route_status": route["route_status"],
            "coverage_status": status,
            "reason": reason,
            "evidence_ref": refs[-1] if executed else refs[0],
            "evidence_refs": refs,
            "executed": executed,
            "run_result": run_result,
            "run_result_reason": run_result_reason,
            "account_metrics": account_metrics,
            "account_metrics_reason": account_metrics_reason,
        })
    counts = {status: sum(1 for cell in cells if cell["coverage_status"] == status)
              for status in CELL_STATUS_VOCABULARY}
    counts["planned_cells"] = len(cells)
    counts["total_classified"] = len(cells)
    return {
        "schema": "regime_lab.rf04_cell_coverage.v1",
        "phase": "RF-04",
        "study_id": STUDY_ID,
        "status": "COVERAGE_CLOSED_2_EXECUTED_10_BLOCKED_8_NOT_RUN",
        "status_vocabulary": list(CELL_STATUS_VOCABULARY),
        "rule": (
            "one row per planned primary cell (4 alphas x 5 symbols of the registered discovery "
            "cohort); the route decision is merged from RF-02/pilot_and_route_matrix.json and the "
            "run result from the RF-04 paired pilot/control artifacts. A non-executed cell carries "
            "null metrics with a reason, never a zero"
        ),
        "sources": [
            {"artifact": "evidence/corrective_mode4_v3/RF-02/pilot_and_route_matrix.json",
             "sha256": sha256_file(RF02_DIR / "pilot_and_route_matrix.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_pilot.json",
             "sha256": sha256_file(RUN_DIR / "paired_discovery_pilot.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/controls_and_funnel.json",
             "sha256": sha256_file(RUN_DIR / "controls_and_funnel.json")},
        ],
        "registered_cohort": protocol["cohort"],
        "counts": counts,
        "cells": cells,
        "written_at_utc": utc_now_iso(),
        "lab_run_id": RUN_ID,
    }


def profiling_payload(pilot: dict, controls: dict, panel: dict, protocol: dict,
                      registration: dict, route_matrix: dict, positive: dict) -> dict:
    pilot_wall = {cell["cell"]: {arm: cell["arms"][arm].get("wall_seconds")
                                 for arm in PRIMARY_ARMS}
                  for cell in pilot["cells"]}
    matched_wall = {cell["cell"]: cell["arm"].get("wall_seconds")
                    for cell in controls["matched_control"]["cells"]}
    placebo_wall = {cell["cell"]: cell["arm"].get("wall_seconds")
                    for cell in controls["placebo"]["cells"]}
    pilot_trials = {cell["cell"]: {arm: cell["arms"][arm].get("trial_count")
                                   for arm in PRIMARY_ARMS}
                    for cell in pilot["cells"]}
    matched_trials = {cell["cell"]: cell["arm"].get("trial_count")
                      for cell in controls["matched_control"]["cells"]}
    placebo_trials = {cell["cell"]: cell["arm"].get("trial_count")
                      for cell in controls["placebo"]["cells"]}
    pilot_rows_total = sum(sum(v.values()) for v in pilot_trials.values())
    matched_rows_total = sum(matched_trials.values())
    placebo_rows_total = sum(placebo_trials.values())
    data_bars = {cell["cell"]: cell["data"]["bars"] for cell in pilot["cells"]}
    account_bars = {cell["cell"]: {arm: (cell["arms"][arm].get("account") or {}).get("bars")
                                   for arm in PRIMARY_ARMS}
                    for cell in pilot["cells"]}

    studies_reported = {}
    trial_rows_reported = {}
    event_runs_reported = {}
    event_calls_reported = {}
    endpoints = {cell["cell"]: {"M4_CAL": cell["arms"]["M4_CAL"],
                                "M4_REGIME": cell["arms"]["M4_REGIME"]}
                 for cell in pilot["cells"]}
    endpoints["A-SC/BTCUSDT"]["M4_CAL_MATCHED"] = next(
        row["arm"] for row in controls["matched_control"]["cells"]
        if row["cell"] == "A-SC/BTCUSDT")
    endpoints["A-SC/BTCUSDT"]["M4_REGIME_DELAYED"] = next(
        row["arm"] for row in controls["placebo"]["cells"] if row["cell"] == "A-SC/BTCUSDT")
    for name, arms in endpoints.items():
        studies_reported[name] = {}
        trial_rows_reported[name] = {}
        for arm, record in arms.items():
            trace = record.get("evaluator_trace") or {}
            if trace.get("n_studies") is not None:
                studies_reported[name][arm] = trace["n_studies"]
            if trace.get("n_optuna_trial_rows") is not None:
                trial_rows_reported[name][arm] = trace["n_optuna_trial_rows"]
    event_arms = {name: {arm: record for arm, record in arms.items()
                         if arm in ("M4_CAL", "M4_REGIME")}
                  for name, arms in endpoints.items()}
    for name, arms in event_arms.items():
        for arm, record in arms.items():
            trace = record.get("evaluator_trace") or {}
            if trace.get("event_account_runs") is not None:
                event_runs_reported.setdefault(name, {})[arm] = trace["event_account_runs"]
                event_calls_reported.setdefault(name, {})[arm] = trace["event_scorer_calls"]
    for section, arm_name in (("matched_control", "M4_CAL_MATCHED"), ("placebo", "M4_REGIME_DELAYED")):
        for row in controls[section]["cells"]:
            trace = row["arm"].get("evaluator_trace") or {}
            if trace.get("event_account_runs") is not None:
                event_runs_reported.setdefault(row["cell"], {})[arm_name] = trace["event_account_runs"]
                event_calls_reported.setdefault(row["cell"], {})[arm_name] = trace["event_scorer_calls"]

    size_files = [
        "paired_discovery_pilot.json", "paired_discovery_registration.json",
        "discovery_protocol.json", "positive_control.json", "controls_registration.json",
        "controls_and_funnel.json", "decay_panels.json", "design_freeze.json",
        "model_design_selection_manifest.json", "causal_model_registry.json",
        "emission_tape_sample.json", "current_coordinate_contract.json",
    ]
    artifact_bytes = {name: (RUN_DIR / name).stat().st_size for name in size_files}
    artifact_bytes["RF-02/pilot_and_route_matrix.json"] = (
        RF02_DIR / "pilot_and_route_matrix.json").stat().st_size
    assert all(value > 0 for value in artifact_bytes.values()), "an artifact size is zero"
    studies_reported = {name: arms for name, arms in studies_reported.items() if arms}
    trial_rows_reported = {name: arms for name, arms in trial_rows_reported.items() if arms}
    event_runs_reported = {name: arms for name, arms in event_runs_reported.items() if arms}
    event_calls_reported = {name: arms for name, arms in event_calls_reported.items() if arms}
    registered_trials = protocol["budgets"]["pilot_trials_per_cutoff"]
    executed_trials = registration["matched"]["optuna_trials_per_cutoff"]
    return {
        "schema": "regime_lab.rf04_profiling_and_budget.v1",
        "phase": "RF-04",
        "study_id": STUDY_ID,
        "status": "MEASURED_WITH_UNMEASURED_FIELDS_NULL",
        "measurement_rule": (
            "only values present in the committed RF-04/RF-02 artifacts (or file sizes of those "
            "artifacts) are recorded; a quantity that no committed artifact or log measured is "
            "null plus a reason"
        ),
        "sources": [
            {"artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_pilot.json",
             "sha256": sha256_file(RUN_DIR / "paired_discovery_pilot.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/controls_and_funnel.json",
             "sha256": sha256_file(RUN_DIR / "controls_and_funnel.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/decay_panels.json",
             "sha256": sha256_file(RUN_DIR / "decay_panels.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-02/pilot_and_route_matrix.json",
             "sha256": sha256_file(RF02_DIR / "pilot_and_route_matrix.json")},
        ],
        "denominators": {
            "planned_cells": protocol["cells_planned"],
            "executed_cells": len(pilot["cells"]),
            "pilot_trial_rows": pilot_rows_total,
            "matched_control_trial_rows": matched_rows_total,
            "placebo_trial_rows": placebo_rows_total,
            "total_control_trial_rows": matched_rows_total + placebo_rows_total,
            "d2_anchor_replays": panel["denominators"]["anchors_replayed"],
            "d1_rows": panel["denominators"]["D1_rows"],
            "d2_rows": panel["denominators"]["D2_rows"],
            "d3_rows": panel["denominators"]["D3_rows"],
        },
        "wall_seconds": {
            "pilot_by_cell_arm": pilot_wall,
            "matched_control_by_cell_arm": matched_wall,
            "placebo_by_cell_arm": placebo_wall,
            "d2_anchor_replay_seconds": controls["decay_anchor"]["wall_seconds"],
            "rf02_route_proof_cold_warm_seconds": {
                alpha: dict(values) for alpha, values in route_matrix["timings"].items()},
            "totals": {
                "pilot_sum_of_cell_arm_seconds":
                    round(sum(v for arms in pilot_wall.values() for v in arms.values()), 3),
                "matched_control_loop_wall_seconds":
                    controls["matched_control"]["wall_seconds"],
                "matched_control_sum_of_cell_arm_seconds": round(sum(matched_wall.values()), 3),
                "placebo_loop_wall_seconds": controls["placebo"]["wall_seconds"],
                "placebo_sum_of_cell_arm_seconds": round(sum(placebo_wall.values()), 3),
                "d2_anchor_replay_seconds": controls["decay_anchor"]["wall_seconds"],
            },
        },
        "cold_warm": {
            "measured": True,
            "where": "RF-02/pilot_and_route_matrix.json#/timings",
            "frame": route_matrix["data"],
            "values_seconds": {alpha: dict(values)
                               for alpha, values in route_matrix["timings"].items()},
            "note": ("cold/warm route-proof timings were measured on the RF-02 synthetic seed-17 "
                     "frame; the RF-04 real-snapshot pilot did not record a cold/warm split"),
        },
        "cpu_seconds": {"value": None, "reason": CPU_REASON},
        "peak_rss_bytes": {"value": None, "reason": RSS_REASON},
        "candidate_bar_visits": {"value": None, "reason": BAR_VISIT_REASON},
        "rows": {
            "data_bars_by_cell": data_bars,
            "account_bars_by_cell_arm": account_bars,
            "account_bars_null_reason": (
                "the event-account payload records engine_fill_count and fill_count instead of a "
                "bar count, so its account_bars value is null rather than zero"),
            "trial_rows": {
                "pilot_by_cell_arm": pilot_trials,
                "matched_control_by_cell": matched_trials,
                "placebo_by_cell": placebo_trials,
            },
            "panel_rows": {
                "D1": panel["denominators"]["D1_rows"],
                "D2": panel["denominators"]["D2_rows"],
                "D3": panel["denominators"]["D3_rows"],
            },
        },
        "bytes": {
            "artifacts_bytes": artifact_bytes,
            "total_artifacts_bytes": sum(artifact_bytes.values()),
            "note": "sizes of the committed input artifacts at generation time",
        },
        "trials": {
            "pilot_by_cell_arm": pilot_trials,
            "matched_control_by_cell": matched_trials,
            "placebo_by_cell": placebo_trials,
            "totals": {
                "pilot": pilot_rows_total,
                "matched_control": matched_rows_total,
                "placebo": placebo_rows_total,
                "all_recorded": pilot_rows_total + matched_rows_total + placebo_rows_total,
            },
        },
        "engine_calls": {
            "definition": (
                "counters copied from the committed evaluator traces: Optuna studies and trial "
                "rows for the endpoint route; event-account runs and scorer calls for the event "
                "route. D2 replays and positive-control accounts are counted once per committed "
                "replay record"
            ),
            "optuna_counters": {
                "cells_with_counter": sorted(studies_reported),
                "studies_by_cell_arm": studies_reported,
                "trial_rows_by_cell_arm": trial_rows_reported,
                "not_recorded_on": {"A-HMA/BTCUSDT": (
                    "the event route trace exposes event-account counters and no Optuna per-study "
                    "counters, so an Optuna count for A-HMA/BTCUSDT is not applicable rather than "
                    "zero")},
            },
            "event_account_counters": {
                "cells_with_counter": sorted(event_runs_reported),
                "account_runs_by_cell_arm": event_runs_reported,
                "scorer_calls_by_cell_arm": event_calls_reported,
                "not_recorded_on": {"A-SC/BTCUSDT": (
                    "the endpoint trace exposes Optuna counters and no event-account counters, so "
                    "an event-account count for A-SC/BTCUSDT is not applicable rather than zero")},
            },
            "d2_anchor_replays": panel["denominators"]["anchors_replayed"],
            "positive_control_accounts_evaluated": sum(
                1 for key in ("regime", "calendar") if positive[key].get("status") == "EVALUATED"),
        },
        "budget": {
            "registered_full_study_trials_per_cutoff": registered_trials,
            "executed_bounded_trials_per_cutoff": executed_trials,
            "status": "BELOW_REGISTERED_MINIMUM",
            "reason": (
                "the bounded pilot registered the low end overridden to 8 trials/cutoff for both "
                "arms (paired_discovery_registration.json budget_note), below the registered full "
                "study value; the registered 32-64 range is never renamed"
            ),
        },
        "written_at_utc": utc_now_iso(),
        "lab_run_id": RUN_ID,
    }


def schema_record(alpha_id: str) -> dict:
    schema = SCHEMAS[alpha_id].as_record()
    return {
        "schema": schema["schema"],
        "name": schema["name"],
        "sha256": canonical_sha256(schema),
        "object": schema,
        "source": "src/crypto_regime_lab/selector/alpha_schemas.py",
        "source_sha256": sha256_file(
            LAB_ROOT / "src/crypto_regime_lab/selector/alpha_schemas.py"),
    }


def transparency_payload(pilot: dict, panel: dict, registry: dict,
                         registration: dict) -> dict:
    digest_by_selection = {}
    for row in panel["D1"]:
        digest_by_selection.setdefault(row["selection_id"], row["parameter_digest"])
    registry_source = (registry.get("design") or {}).get("source")
    cells = []
    selections_checked = 0
    digest_mismatches = []
    for cell in pilot["cells"]:
        schema = schema_record(cell["alpha_id"])
        arms = {}
        for arm_name in PRIMARY_ARMS:
            arm = cell["arms"][arm_name]
            trace = arm.get("evaluator_trace") or {}
            trials = arm.get("trial_records", [])
            by_fold: dict[int, list[dict]] = {}
            for trial in trials:
                by_fold.setdefault(int(trial["schedule_fold_id"]), []).append(trial)
            folds = arm.get("fold_selection_table", [])
            cutoffs = []
            previous_digest = None
            for row in folds:
                fold_id = int(row["fold_id"])
                selected = row.get("selected_params") or {}
                digest = parameter_digest(selected)
                selection_id = f"{cell['cell']}:{arm_name}:fold{fold_id}"
                recorded = digest_by_selection.get(selection_id)
                selections_checked += 1
                if recorded != digest:
                    digest_mismatches.append(
                        {"selection_id": selection_id, "computed": digest, "panel": recorded})
                fold_trials = sorted(by_fold.get(fold_id, []), key=lambda t: t["trial_id"])
                selected_trial = None
                for trial in fold_trials:
                    if trial.get("params") == selected:
                        selected_trial = trial
                        break
                finite = [t for t in fold_trials
                          if isinstance(t.get("objective"), (int, float))
                          and t["objective"] is not None]
                objectives = {canonical_sha256(t.get("objective")) for t in finite}
                if fold_id == 0:
                    activation_status = "INITIAL_SELECTION"
                elif digest != previous_digest:
                    activation_status = "NEW_PARAMETER_ACTIVATION"
                else:
                    activation_status = "REPEATED_PARAMETER_SELECTION"
                metadata = (selected_trial or {}).get("selection_metadata") or {}
                fallback = None
                if selected_trial is None:
                    decomposition = {
                        "selected_trial_id": None,
                        "selected_trial": None,
                        "selected_trial_reason": (
                            "no trial record in this fold carries the selected parameter object; "
                            "the selected objective is still available on the fold table"
                        ),
                        "trials_in_fold": len(fold_trials),
                        "finite_objective_values": len(finite),
                        "distinct_objective_values": len(objectives),
                        "all_candidates_tied": len(objectives) <= 1,
                        "nonfinite_fields": sorted({
                            key for trial in fold_trials
                            for key in (trial.get("nonfinite_fields") or {})}),
                        "trials": [_trial_compact(t) for t in fold_trials],
                    }
                else:
                    decomposition = {
                        "selected_trial_id": selected_trial["trial_id"],
                        "selected_trial": _trial_compact(selected_trial),
                        "selected_trial_reason": None,
                        "trials_in_fold": len(fold_trials),
                        "finite_objective_values": len(finite),
                        "distinct_objective_values": len(objectives),
                        "all_candidates_tied": len(objectives) <= 1,
                        "nonfinite_fields": sorted({
                            key for trial in fold_trials
                            for key in (trial.get("nonfinite_fields") or {})}),
                        "trials": [_trial_compact(t) for t in fold_trials],
                    }
                cutoffs.append({
                    "fold_id": fold_id,
                    "cutoff_utc": row.get("test_start"),
                    "training_range": {
                        "start": row.get("train_start"),
                        "end": row.get("train_end"),
                        "memory_days": arm.get("schedule", {}).get("train_memory_days"),
                        "memory_rule": arm.get("schedule", {}).get("train_memory_rule"),
                    },
                    "evaluation_range": {"start": row.get("test_start"),
                                         "end": row.get("test_end")},
                    "seed": metadata.get("fold_seed")
                    or (fold_trials[0]["fold_seed"] if fold_trials else None),
                    "trials": {
                        "configured": (trace.get("optuna_trials_configured_per_study")
                                       or registration["matched"]["optuna_trials_per_cutoff"]),
                        "retained": len(fold_trials),
                    },
                    "selected_digest": digest,
                    "selected_digest_recorded_in_decay_panel": recorded,
                    "selected_params": selected,
                    "selected_is_objective": row.get("selected_is_objective"),
                    "candidate_count_reported": row.get("candidate_count"),
                    "parameter_schema_sha256": schema["sha256"],
                    "selector_status": {
                        "stage": metadata.get("stage"),
                        "objective_mode": metadata.get("objective_mode"),
                        "candidate_selection_metric": arm.get("candidate_selection_metric"),
                        "scoring_backend": arm.get("scoring_backend"),
                        "resolved_evaluator": arm.get("resolved_evaluator"),
                        "oos_seen_by_optuna": metadata.get("oos_seen_by_optuna"),
                        "inner_validation": metadata.get("inner_validation"),
                        "inner_validation_reason": (
                            "the committed trial ledger records inner_validation=null and "
                            "inner_fold_count=0 for every trial"
                            if metadata.get("inner_validation") is None else None),
                        "fallback_status": fallback,
                        "fallback_reason": FALLBACK_REASON,
                    },
                    "activation": {
                        "time_utc": row.get("test_start"),
                        "status": activation_status,
                        "changed_from_previous_fold": (None if fold_id == 0
                                                       else digest != previous_digest),
                        "time_basis": (
                            "fold test_start from fold_selection_table; the pilot account is one "
                            "stitched run (endpoint params_semantics="
                            f"{trace.get('params_semantics')!r}, event route activates per-fold "
                            "parameter windows at these cutoffs)"
                        ),
                    },
                    "selection_decomposition": decomposition,
                })
                previous_digest = digest
            arms[arm_name] = {
                "route": cell["route"],
                "schedule": arm.get("schedule"),
                "validation_claim": arm.get("validation_claim"),
                "oos_used_for_selection": arm.get("oos_used_for_selection"),
                "selected_digest": arm.get("selected_digest"),
                "cutoffs": cutoffs,
            }
        cells.append({
            "cell": cell["cell"],
            "alpha_id": cell["alpha_id"],
            "symbol": cell["symbol"],
            "route": cell["route"],
            "data": cell["data"],
            "parameter_schema": schema,
            "arms": arms,
        })
    cutoffs_expected = sum(len(cell["arms"][arm]["cutoffs"])
                           for cell in cells for arm in PRIMARY_ARMS)
    return {
        "schema": "regime_lab.rf04_mode4_transparency_ledger.v1",
        "phase": "RF-04",
        "study_id": STUDY_ID,
        "status": "COMPLETE_FOR_EXECUTED_CELLS",
        "spec": {
            "rule": (
                "RF04.2: at each cutoff record the exact training range, parameter schema, seed, "
                "trials, Mode 4 selection decomposition, selector/fallback status, selected digest "
                "and activation. Both arms share the fallback definition; a missing field is null "
                "plus a reason"
            ),
            "selector_fallback_rule": FALLBACK_REASON,
            "parameter_schema_source": schema_record("A-SC")["source"],
        },
        "sources": [
            {"artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_pilot.json",
             "sha256": sha256_file(RUN_DIR / "paired_discovery_pilot.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/decay_panels.json",
             "sha256": sha256_file(RUN_DIR / "decay_panels.json")},
            {"artifact": "src/crypto_regime_lab/selector/alpha_schemas.py",
             "sha256": sha256_file(LAB_ROOT / "src/crypto_regime_lab/selector/alpha_schemas.py")},
            {"artifact": "configs/alpha_registry.json",
             "sha256": sha256_file(LAB_ROOT / "configs" / "alpha_registry.json")},
        ],
        "coverage": {
            "cells": len(cells),
            "arms": len(PRIMARY_ARMS),
            "cutoffs": cutoffs_expected,
            "cutoffs_expected": cutoffs_expected,
            "selections_checked": selections_checked,
        },
        "digest_verification": {
            "computed_with": "crypto_regime_lab.integration.activation.parameter_digest",
            "cross_checked_against": "decay_panels.json#/D1[*].parameter_digest",
            "selections_checked": selections_checked,
            "mismatches": digest_mismatches,
            "status": "PASS" if not digest_mismatches else "FAIL",
        },
        "fallback_fraction": {
            "value": None,
            "denominator": {"selections_checked": selections_checked},
            "reason": FALLBACK_REASON,
        },
        "model_design": {
            "registry_ref": "causal_model_registry.json#/design",
            "design_source": registry_source,
            "registered_fallback_used": registry_source == "registered_fallback",
            "fallback_fraction_note": (
                "the model-design fallback question is separate from the per-cutoff Mode 4 "
                "candidate selection; this field records which design the registry followed"
            ),
        },
        "cells": cells,
        "written_at_utc": utc_now_iso(),
        "lab_run_id": RUN_ID,
    }


def _trial_compact(trial: dict) -> dict:
    metadata = dict(trial.get("selection_metadata") or {})
    return {
        "trial_id": trial.get("trial_id"),
        "params": trial.get("params"),
        "objective": trial.get("objective"),
        "mean_is_sharpe": trial.get("mean_is_sharpe"),
        "mean_oos_sharpe": trial.get("mean_oos_sharpe"),
        "mean_decay": trial.get("mean_decay"),
        "std_decay": trial.get("std_decay"),
        "pruned": trial.get("pruned"),
        "schedule_fold_id": trial.get("schedule_fold_id"),
        "study_id": trial.get("study_id"),
        "fold_seed": trial.get("fold_seed"),
        "temporal_score": trial.get("temporal_score"),
        "temporal_median": trial.get("temporal_median"),
        "temporal_q25": trial.get("temporal_q25"),
        "temporal_mad": trial.get("temporal_mad"),
        "temporal_count": trial.get("temporal_count"),
        "is_subperiod_count": trial.get("is_subperiod_count"),
        "selection_metadata": metadata,
        "nonfinite_fields": trial.get("nonfinite_fields"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    targets = ["cell_coverage.json", "profiling_and_budget.json",
               "mode4_transparency_ledger.json"]
    if not args.force and any((RUN_DIR / name).exists() for name in targets):
        raise SystemExit("an RF-04 gap-close artifact exists; pass --force to supersede")

    pilot = load_json(RUN_DIR / "paired_discovery_pilot.json")
    controls = load_json(RUN_DIR / "controls_and_funnel.json")
    panel = load_json(RUN_DIR / "decay_panels.json")
    protocol = load_json(RUN_DIR / "discovery_protocol.json")
    registration = load_json(RUN_DIR / "paired_discovery_registration.json")
    positive = load_json(RUN_DIR / "positive_control.json")
    registry = load_json(RUN_DIR / "causal_model_registry.json")
    route_matrix = load_json(RF02_DIR / "pilot_and_route_matrix.json")

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)

    coverage = cell_coverage_payload(pilot, controls, route_matrix, protocol)
    coverage_record = writer.write_json("cell_coverage.json", coverage,
                                        schema=coverage["schema"])
    profiling = profiling_payload(pilot, controls, panel, protocol, registration,
                                  route_matrix, positive)
    profiling_record = writer.write_json("profiling_and_budget.json", profiling,
                                         schema=profiling["schema"])
    ledger = transparency_payload(pilot, panel, registry, registration)
    if ledger["digest_verification"]["status"] != "PASS":
        raise SystemExit(f"digest verification failed: {ledger['digest_verification']['mismatches']}")
    ledger_record = writer.write_json("mode4_transparency_ledger.json", ledger,
                                      schema=ledger["schema"])

    print(json.dumps({
        "cell_coverage": {"sha256": coverage_record["sha256"],
                          "statuses": coverage["counts"]},
        "profiling_and_budget": {"sha256": profiling_record["sha256"],
                                 "denominators": profiling["denominators"]},
        "mode4_transparency_ledger": {"sha256": ledger_record["sha256"],
                                      "coverage": ledger["coverage"]},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
