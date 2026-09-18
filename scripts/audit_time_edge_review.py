#!/usr/bin/env python3
"""Capture a read-only review of the lab into a NEW, review-owned directory.

No lab module, strategy, engine, optimizer or runner is imported or invoked.
The optional small probes execute individual AST-extracted arithmetic/controller
functions, with their source copied into the review. They are source probes,
not backtests, an independent engine audit, or statistical market evidence.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
CORRECTIVE = "evidence/corrective_mode4_v3/"
SELECTED = [
    "AGENTS.md", "CLAUDE.md",
    "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md",
    "REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md",
    "configs/sandbox_policy.json", "configs/lab05_full_emission_tape.json",
    "configs/lab05_regime_model_registry.json", "configs/lab05_k_selection.json",
    "configs/acceptance_test_coverage.json", "configs/rf_acceptance_registry.json",
] + [CORRECTIVE + name for name in [
    "RF-01/corrective_study_spec.json", "RF-01/finding_disposition.json",
    "RF-01/historical_invalidation.json", "RF-02/report.md", "RF-03/report.md",
    "RF-04/model_design_selection_manifest.json", "RF-04/causal_model_registry.json",
    "RF-04/discovery_protocol.json", "RF-04/design_freeze.json",
    "RF-04/decay_panels.json", "RF-04/controls_and_funnel.json",
    "RF-04/paired_discovery_full.json", "RF-04/cell_coverage.json",
    "RF-04/report.md", "RF-04/positive_control.json",
    "RF-05/claim_report.json", "RF-05/report.md", "RF-05/artifact_integrity.json",
    "RF-05/prospective_protocol.json", "RF-05/freeze_manifest.json",
    "followup-studies/followup_studies_registration.json",
    "FUP-01/native_event_capability.json", "FUP-01/route_matrix.json",
    "FUP-02/budget_revision.json", "FUP-02/paired_discovery_fullwindow.json",
    "FUP-02/cell_coverage.json", "FUP-02/coverage_review.json",
    "FUP-02/report.json", "FUP-02/report.md", "FUP-02/attempts.jsonl",
    "FUP-02/trial_ledger.jsonl", "FUP-02/test_suite_full.log",
    "FUP-02/test_suite_mode4_corrective.log",
]]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def invalid(value):
        raise ValueError(f"non-standard JSON number: {value}")
    return json.loads(data, parse_constant=invalid)


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def source_inventory():
    rows, captured = [], {}
    for folder in ("src", "scripts", "tests"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path.is_symlink():
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            captured[rel] = data
            row = {"path": rel, "sha256": digest(data), "bytes": len(data),
                   "lines": len(data.splitlines()), "review_level": "AST_INVENTORY"}
            try:
                tree = ast.parse(data, filename=rel)
                row["symbols"] = [{"name": node.name, "line": node.lineno,
                                   "end_line": node.end_lineno, "kind": type(node).__name__}
                                  for node in ast.walk(tree)
                                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                       ast.ClassDef))]
                row["imports"] = [ast.unparse(node) for node in ast.walk(tree)
                                  if isinstance(node, (ast.Import, ast.ImportFrom))]
                row["test_functions"] = sum(isinstance(node, ast.FunctionDef)
                                             and node.name.startswith("test_")
                                             for node in ast.walk(tree))
                row["parse_status"] = "PARSED"
            except (SyntaxError, ValueError) as exc:
                row["parse_status"] = "ERROR"
                row["error"] = str(exc)
            rows.append(row)
    return rows, captured


def evidence_inventory():
    rows = []
    for folder in ("configs", "evidence", "reports", "handoff"):
        for path in sorted((ROOT / folder).rglob("*")):
            if (not path.is_file() or path.is_symlink()
                    or path.suffix not in (".json", ".jsonl", ".md")
                    or "evidence/reviews/" in path.as_posix()):
                continue
            data = path.read_bytes()
            rel = path.relative_to(ROOT).as_posix()
            row = {"path": rel, "sha256": digest(data), "bytes": len(data)}
            try:
                if path.suffix == ".json":
                    payload = strict_json(data)
                    row["parse_status"] = "PARSED"
                    if isinstance(payload, dict):
                        row["schema"] = payload.get("schema")
                        row["status"] = payload.get("status")
                elif path.suffix == ".jsonl":
                    lines = [line for line in data.splitlines() if line.strip()]
                    for line in lines:
                        strict_json(line)
                    row["parse_status"] = "PARSED"
                    row["rows"] = len(lines)
                else:
                    row["parse_status"] = "TEXT_INVENTORY_ONLY"
            except (ValueError, UnicodeError) as exc:
                row["parse_status"] = "ERROR"
                row["error"] = str(exc)
            row["stable_during_read"] = digest(path.read_bytes()) == row["sha256"]
            rows.append(row)
    return rows


def extract_functions(source: bytes, names, namespace):
    tree = ast.parse(source)
    nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    nodes += [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(nodes) != len(names) + 1:
        raise ValueError(f"missing function in extracted probe: {names}")
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 "<captured-source-probe>", "exec"), namespace)


def source_probes(captured):
    import numpy as np
    import pandas as pd

    out = {"classification": "AST_EXTRACTED_SOURCE_PROBES_NOT_ENGINE_OR_MARKET_TESTS",
           "numpy": np.__version__, "pandas": pd.__version__}
    ns = {"pd": pd, "RegimeSchedule": lambda **kw: SimpleNamespace(**kw)}
    extract_functions(captured["src/crypto_regime_lab/experiments/regime_schedule.py"],
                      {"online_trigger_schedule"}, ns)
    controller = ns["online_trigger_schedule"]
    tape = [{"available_at": "2021-01-01T00:00:00+00:00", "state_id": 0,
             "state_namespace": "one", "quality_status": "OK", "decision_eligible": True,
             "ready_at": "2021-01-01T00:00:00+00:00"},
            {"available_at": "2021-01-03T00:00:00+00:00", "state_id": 1,
             "state_namespace": "one", "quality_status": "OK", "decision_eligible": True,
             "ready_at": "2025-01-01T00:00:00+00:00"}]
    args = {"earliest": "2021-01-01", "latest": "2021-12-31", "min_gap_days": 1,
            "max_age_days": 180, "budget": None}
    delayed = controller(tape, **args)
    missing = controller([{k: v for k, v in r.items()
                           if k not in ("decision_eligible", "quality_status", "ready_at")}
                          for r in tape], **args)
    constant = [{**tape[0], "available_at": str(t)}
                for t in pd.date_range("2021-01-01", "2021-12-31", freq="D", tz="UTC")]
    out["scheduler"] = {
        "future_model_ready_triggered": list(delayed.cutoffs),
        "missing_eligibility_fields_triggered": list(missing.cutoffs),
        "constant_state_365_observations_max_age_180_triggers": list(controller(constant, **args).cutoffs),
        "limitations": "isolated source function; an external validated tape could guard inputs, but the active tape omits ready_at"}

    ns = {"pd": pd, "np": np}
    extract_functions(captured["scripts/run_rf04_decay_and_controls.py"], {"ts", "daily_metrics"}, ns)
    dates = pd.date_range("2020-12-31", "2021-10-01", freq="D", tz="UTC")
    values = 100 * np.cumprod(1 + np.where(np.arange(len(dates)) % 2, 0.01, -0.005))
    curve = pd.Series(values, index=dates)
    first = ns["daily_metrics"](curve, "2021-01-01", "2021-04-01")
    second = ns["daily_metrics"](curve, "2021-04-01", "2021-06-30")
    losing = ns["daily_metrics"](pd.Series([100, 99, 98, 97],
                              index=pd.date_range("2020-12-31", periods=4, tz="UTC")),
                              "2021-01-01", "2021-01-03")
    out["decay"] = {"expected_half_open_days_per_90_day_window": 90,
                    "observed_H1_days": first["observed_days"],
                    "observed_H2_days": second["observed_days"],
                    "shared_boundary_day": "2021-04-01",
                    "daily_profit_factor_value": first["profit_factor_daily"],
                    "d2_lookup_profit_factor_value": first.get("profit_factor"),
                    "all_loss_daily_returns_result": losing}
    out["forward_target_purge_index_check"] = {
        "classification": "SOURCE_INDEX_ANALYSIS",
        "train_end_exclusive": 100, "forward_horizon_rows": 6,
        "train_target_slice_in_source": "target[:train_end]",
        "train_origin_rows_with_outcome_end_at_or_after_cutoff": list(range(94, 100)),
        "validation_head_dropped_in_source": 6,
        "finding": "dropping validation head does not make the six training outcomes available at the training cutoff"}
    ns = {"pd": pd}
    extract_functions(captured["scripts/run_rf05.py"], {"equity_series", "paired_daily_diff"}, ns)
    left = {"equity_daily": [["2020-12-30", 100], ["2020-12-31", 100],
                             ["2021-01-01", 101], ["2021-01-02", 102]]}
    right = {"equity_daily": [[x[0], 100] for x in left["equity_daily"]]}
    diff = ns["paired_daily_diff"](left, right)
    out["rf05_window"] = {"declared_evaluation_start": "2021-01-01",
                          "actual_return_dates": [str(t.date()) for t in diff.index],
                          "out_of_window_return_retained": "2020-12-31" in [str(t.date()) for t in diff.index]}
    return out


def inspect_saved(captured):
    def get(rel):
        return strict_json(captured[rel])
    def cf(rel):
        return get(CORRECTIVE + rel)
    full = cf("FUP-02/paired_discovery_fullwindow.json")
    coverage = cf("FUP-02/cell_coverage.json")
    review = cf("FUP-02/coverage_review.json")
    progress = []
    failures = []
    accounts = []

    def account_summary(name, arm, account, evaluation_start):
        rows = account.get("equity_daily", [])
        if not rows:
            return
        before = [r for r in rows if r[0][:10] < evaluation_start]
        accounts.append({"cell": name, "arm": arm, "evaluation_start": evaluation_start,
                         "rows": len(rows), "first": rows[0], "last": rows[-1],
                         "pre_evaluation_days": len(before),
                         "pre_evaluation_equity_values": sorted({r[1] for r in before}),
                         "engine_report": account.get("engine_report"),
                         "entries": account.get("entries"), "fill_count": account.get("fill_count"),
                         "retained_versions": account.get("versions"),
                         "retained_fill_fields": list(account.get("fills", [{}])[0])
                         if account.get("fills") else []})

    for cell in full["cells"]:
        shards = cell["shards"]
        progress.append({"cell": cell["cell"], "coverage_status": cell.get("coverage_status"),
                         "shards": {arm: {"status": shard["status"],
                                          "scored": len(shard.get("completed_fold_ids", [])),
                                          "planned": shard["fold_count"]}
                                    for arm, shard in shards.items()}})
        for arm, shard in shards.items():
            for result in shard["cutoff_results"]:
                if result["status"] == "ERROR":
                    failures.append({"cell": cell["cell"], "arm": arm,
                                     "fold_id": result["fold_id"], "cutoff": result["cutoff"],
                                     "reason": result.get("reason")})
            if shard.get("account"):
                account_summary(cell["cell"], arm, shard["account"], "2021-01-01")
    for cell in cf("RF-04/paired_discovery_full.json")["cells"]:
        for run in cell.get("runs", []):
            for arm, record in run.get("arms", {}).items():
                if record.get("account"):
                    account_summary("RF04:" + cell["cell"], arm, record["account"], "2021-01-01")
    tape = get("configs/lab05_full_emission_tape.json")
    emissions = tape["emissions"]
    registry = get("configs/lab05_regime_model_registry.json")
    design = cf("RF-04/model_design_selection_manifest.json")
    decay = cf("RF-04/decay_panels.json")
    d2 = decay["D2"]["rows"]
    d2_pf = [r for r in d2 if r["metric_name"] == "profit_factor"]
    ledger = [strict_json(line) for line in captured[CORRECTIVE + "FUP-02/trial_ledger.jsonl"].splitlines()
              if line.strip()]
    return {
        "fup02": {"checkpoint": full.get("last_checkpoint_at_utc"), "status": full["status"],
                  "coverage": coverage["counts"], "review": review["aggregate"],
                  "progress": progress, "runtime_failures": failures,
                  "ledger_rows": len(ledger), "ledger_unique_keys": len({r["trial_key"] for r in ledger}),
                  "completed_invocations_recorded": full["invocations"],
                  "reference_hash_checks": {
                      key: full.get(key) == digest(captured[CORRECTIVE + "FUP-02/" + filename])
                      for key, filename in [("cell_coverage_sha256", "cell_coverage.json"),
                                            ("coverage_review_sha256", "coverage_review.json")]},
                  "forward_reference_hash_checks": {
                      filename: cf("FUP-02/" + filename)["sources"][0]["sha256"]
                      == digest(captured[CORRECTIVE + "FUP-02/paired_discovery_fullwindow.json"])
                      for filename in ["cell_coverage.json", "coverage_review.json"]}},
        "account_windows": accounts,
        "regime": {"active_tape": "configs/lab05_full_emission_tape.json",
                   "rows": len(emissions), "symbol": tape["symbol"], "span": tape["span"],
                   "field_counts": {k: sum(k in row for row in emissions)
                                    for k in ("ready_at", "model_fit_cutoff", "state_common", "economic_context",
                                              "decision_eligible", "quality_status")},
                   "quality_counts": dict(Counter(r.get("quality_status") for r in emissions)),
                   "active_registry_design": {k: registry[k] for k in ("n_states", "lambda_jump", "train_memory_days")},
                   "active_registry_models": len(registry["models"]),
                   "rf04_selected_design": design["selection"],
                   "fixed_target_ablation": {k: design["fixed_target_ablation"][k]
                                             for k in ("target_name", "target_kind", "denominators")},
                   "ablation_rank_ic": [{"groups": r["groups"], "value": r["fixed_target_rank_ic_mean"]}
                                        for r in design["fixed_target_ablation"]["ladder"]]},
        "decay": {"denominators": decay["denominators"],
                  "D2_self_comparison_rows": sum(r["age_window_index"] == 0 for r in d2),
                  "D2_PF_rows": len(d2_pf),
                  "D2_PF_null_rows": sum(r["signed_delta"] is None for r in d2_pf),
                  "D2_PF_rows_with_finite_underlying_PF": sum(
                      r["equity_metrics"].get("profit_factor_daily") is not None for r in d2_pf),
                  "D2_route_mismatch_rows": sum(not r["route_match"] for r in d2),
                  "D2_observed_days": dict(Counter(str(r["observed_days"]) for r in d2)),
                  "D2_validity": dict(Counter(r["validity_status"] for r in d2)),
                  "D1_cells": sorted({r["alpha"] + "/" + r["symbol"] for r in decay["D1"]})},
        "report_pairs": {phase: {ext: (ROOT / CORRECTIVE / phase / ("report." + ext)).exists()
                                  for ext in ("md", "json")}
                         for phase in ("RF-01", "RF-02", "RF-03", "RF-04", "RF-05", "FUP-01", "FUP-02")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="new directory under evidence/reviews/")
    args = parser.parse_args()
    destination = (ROOT / args.out).resolve()
    allowed = (ROOT / "evidence/reviews").resolve()
    if not destination.is_relative_to(allowed) or destination == allowed or destination.exists():
        raise SystemExit("--out must be a NEW directory strictly below LAB_ROOT/evidence/reviews")
    started = time.monotonic()
    capture_started = datetime.now(timezone.utc).isoformat()
    inventory, sources = source_inventory()
    evidence = evidence_inventory()
    selected_paths = [p for p in SELECTED if (ROOT / p).is_file()]
    # Multiple files are produced sequentially by FUP-02. Check stability of the
    # entire byte capture; preserve mismatches rather than repairing its files.
    attempts = []
    for _ in range(3):
        selected = {p: (ROOT / p).read_bytes() for p in selected_paths}
        changed = [p for p, data in selected.items() if (ROOT / p).read_bytes() != data]
        attempts.append(changed)
        if not changed:
            break
    captured = {**sources, **selected}
    observations = inspect_saved(captured)
    probes = source_probes(captured)
    # Writes begin only here, all inside the explicitly requested fresh folder.
    destination.mkdir(parents=True)
    manifest = []
    for rel, data in captured.items():
        target = destination / "captured" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest.append({"source": rel, "captured_path": "captured/" + rel,
                         "sha256": digest(data), "bytes": len(data)})
    write_json(destination / "source_inventory.json", inventory)
    write_json(destination / "evidence_inventory.json", evidence)
    write_json(destination / "source_probes.json", probes)
    write_json(destination / "observations.json", observations)
    write_json(destination / "capture_manifest.json", manifest)
    audit = {"schema": "regime_lab.time_edge_review.v1", "lab_run_id": destination.name,
             "study_id": "time_edge_readonly_review", "capture_started_at_utc": capture_started,
             "completed_at_utc": datetime.now(timezone.utc).isoformat(),
             "source_python_files": len(inventory), "source_lines": sum(r["lines"] for r in inventory),
             "source_ast_errors": [r["path"] for r in inventory if r["parse_status"] == "ERROR"],
             "test_functions_inventoried_not_run": sum(r.get("test_functions", 0) for r in inventory),
             "evidence_text_files": len(evidence),
             "json_parse_errors": [r for r in evidence if r["parse_status"] == "ERROR"],
             "capture_change_checks": attempts, "selected_capture_stable_during_read": not attempts[-1],
             "source_changed_during_review": [p for p, data in sources.items()
                                              if (ROOT / p).read_bytes() != data],
             "elapsed_seconds": time.monotonic() - started,
             "engine_runs": 0, "optimizer_runs": 0, "market_statistical_tests": 0,
             "existing_tests_rerun": 0,
             "scope_limit": "AST/text inventory covers the entire lab source/scripts/tests and saved text evidence; semantic review focuses active economic/model/statistical paths. This is not a certificate that every path is correct.",
             "capture_limit": "FUP-02 continues independently; this is a byte snapshot, not a transactional database freeze.",
             "artifact_hashes": {name: digest((destination / name).read_bytes())
                                  for name in ("source_inventory.json", "evidence_inventory.json",
                                               "source_probes.json", "observations.json", "capture_manifest.json")}}
    write_json(destination / "audit.json", audit)
    print(json.dumps({"output": str(destination.relative_to(ROOT)), "audit": audit}, ensure_ascii=False))


if __name__ == "__main__":
    main()
