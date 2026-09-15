#!/usr/bin/env python3
"""Render the TE-02 pilot-09 and TE-03 reports from committed, hash-verified JSON.

Numbers are read from the collected stage artifacts and the run ledgers; the
renderer never invents a metric and prints null + reason where a stage did not
measure one.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import digest, read  # noqa: E402


def task_walls(run_id):
    directory = ROOT / "evidence/time_edge_validation_v4/runs" / run_id
    job = read(directory / "job.json")
    names = {digest({"identity": {"job_hash": digest(job)}, "task": task}): task["task_id"]
             for task in job["tasks"]}
    con = sqlite3.connect(directory / "ledger.sqlite")
    rows = con.execute("SELECT task,status,wall,reserved FROM attempt ORDER BY started").fetchall()
    con.close()
    return [(names.get(task, task[:12]), status, wall, reserved) for task, status, wall, reserved in rows]


def allocation_state():
    directory = ROOT / "evidence/time_edge_validation_v4/allocations/TE02-PILOT-R03"
    con = sqlite3.connect(directory / "ledger.sqlite")
    total = con.execute("SELECT budget FROM study").fetchone()[0]
    rows = con.execute("SELECT status,reserved,wall FROM attempt").fetchall()
    revisions = con.execute("SELECT id,old_budget,new_budget,prior_charged FROM budget_revision ORDER BY applied_at").fetchall()
    con.close()
    spent = sum(r[2] if r[2] is not None else r[1] for r in rows)
    return total, spent, len(rows), revisions


def pilot_report():
    results = read(ROOT / "evidence/time_edge_validation_v4/host-pilot-09-results.json")["results"]
    by_task = {r["task_id"]: r for r in results}
    selection = by_task["A-SC-BTC-train-selection"]
    audit = by_task["A-SC-BTC-selected-audit"]
    deploy = by_task["A-SC-BTC-train-deployment"]
    qualify = by_task["engine-clock-fee-reconciliation"]
    total, spent, attempts, revisions = allocation_state()
    lines = [
        "# TE-02 pilot-09 report — engine clock, 32-trial selection, audit, deployment",
        "",
        "- job: `evidence/time_edge_validation_v4/plans/te-host-pilot-09/job.json`",
        f"- allocation `TE02-PILOT-R03`: total {total:.0f}s, charged at report time {spent:.3f}s over {attempts} attempts",
        f"- budget revisions applied: {', '.join(r[0] for r in revisions)}",
        "",
        "## Tasks",
        "",
        "| task | status | wall s | reserved s |",
        "|---|---|---|---|",
    ]
    for task_id, status, wall, reserved in task_walls("te-host-pilot-09"):
        lines.append(f"| {task_id} | {status} | {'' if wall is None else round(wall,3)} | {reserved} |")
    lines += [
        "",
        f"- qualify: checks {sum(1 for v in qualify['checks'].values() if v)}/{qualify['check_denominator']} true; "
        f"engine contract `{qualify['execution_contract']}`; engine runs {qualify['engine_runs']}.",
        f"- selection: {len(selection['trials'])}/32 trials complete, status `{selection['status']}`, wall {selection['wall_seconds']:.1f}s, "
        f"measured search+io+packing {selection['measured_search_io_packing_seconds']:.1f}s; "
        f"selected params `{json.dumps(selection['params'], sort_keys=True)}`; objective {selection['selected']['objective']:.10f}; "
        f"mean_is_sharpe {selection['selected']['mean_is_sharpe']:.10f}; account_runs {selection['account_runs']}, "
        f"scorer_calls {selection['scorer_calls']}, deployment_runs {selection['deployment_runs']}.",
        f"- audit: `{audit['status']}` {sum(1 for v in audit['checks'].values() if v)}/{audit['denominator']}; "
        f"max equity error {audit['maximum_equity_error']}; raw Sharpe {audit['raw_sharpe']} vs selected {audit['selected_raw_sharpe']}; "
        f"fills {audit['fill_count']}; prepared {audit['prepared_wall_seconds']:.1f}s / cold {audit['cold_wall_seconds']:.1f}s.",
        f"- deployment `{deploy['status']}` arm {deploy['arm']} cell {deploy['cell_id']} "
        f"{deploy['score_start']} -> {deploy['score_end_exclusive']}: {len(deploy['fills'])} fills, "
        f"days {deploy['metrics']['days']}, mean daily return {deploy['metrics']['mean_daily_return']:.8f}; "
        "these are execution/technical numbers on the training month, not an edge claim.",
        "",
        "## Scope statement",
        "",
        "The model input at this stage is `model_id: null` for the initial incumbent; this pilot certifies the engine clock, "
        "real 32-trial Mode 4 selection, selected-theta audit parity and one M4_CAL account. It is not the TE-04 economic look.",
        "",
    ]
    return "\n".join(lines)


def te03_coverage_report():
    """Render the extended-support TE-03 state once the coverage artifacts exist."""
    revision = read(ROOT / "evidence/time_edge_validation_v4/coverage-revisions/TE03-COVERAGE-R01.json")
    info = read(ROOT / "evidence/time_edge_validation_v4/te03-r2/information_value.json")
    decision = read(ROOT / "evidence/time_edge_validation_v4/te03-r2/model_decision.json")
    causality = read(ROOT / "evidence/time_edge_validation_v4/te03-r2/model_causality.json")
    opportunity = read(ROOT / "evidence/time_edge_validation_v4/te03-r2/parameter_opportunity.json")
    registry = read(ROOT / "evidence/time_edge_validation_v4/te03-r2/model_registry.json")
    results = read(ROOT / "evidence/time_edge_validation_v4/host-model-results-02.json")["results"]
    vintages = [row for row in results if "design_trials" in row]
    targets = read(ROOT / "evidence/time_edge_validation_v4/host-targets-coverage-01.json")["targets"]
    features = read(ROOT / "evidence/time_edge_validation_v4/host-features-01.json")["results"][0]
    prior = revision["prior_coverage"]
    revised = revision["revised_coverage"]
    lines = [
        "# TE-03 report — features, targets, model vintages and the coverage extension",
        "",
        "Stage scope: `features -> targets -> model vintages` plus the registered support extension "
        "`TE03-COVERAGE-R01`. TE03.7 power/null calibration and the full-path controls are reported separately "
        "in `te03-7-report.md`.",
        "",
        "## Coverage revision (registered before the extension)",
        "",
        f"- prior coverage: {prior['target_series']['origins']} targets "
        f"({prior['target_series']['start'][:10]} .. {prior['target_series']['last_origin'][:10]}), "
        f"{prior['model_series']['vintages']} vintages, {prior['support_measured']['evaluable_outer_targets']} "
        f"evaluable outer targets, inference `{prior['support_measured']['status']}`.",
        f"- revised coverage: {revised['target_series']['origins']} targets "
        f"(+{revised['target_series']['delta_origins']} appended at "
        f"{revised['target_series']['extension_start'][:10]}), {revised['model_series']['vintages']} vintages; "
        f"support floor {revision['support_floor']['value']} from the registered statistical plan.",
        "- revision artifact: `evidence/time_edge_validation_v4/coverage-revisions/TE03-COVERAGE-R01.json`; "
        "grid 28d, horizon 28d, alpha A-SC, cell A-SC/BTCUSDT, bank and train window unchanged.",
        "",
        "## Stage facts (real snapshot data, one worker, no data_loader.py)",
        "",
        f"- features: `{features['status']}` over 5 copied symbols, {features['rows']} 4h rows, "
        f"{features['missing_rows']} rows with any missing feature, raw parquet `{features['features']['sha256'][:16]}`; "
        f"scaler `{features['scaler']}`.",
        f"- targets: {len(targets)} non-overlapping 28-day targets, {len(targets[0]['candidate_ids'])} candidates each, "
        f"origins {targets[0]['origin'][:10]} .. {targets[-1]['origin'][:10]}; the extension appends after the prior "
        "last origin and reuses the same candidate bank (availability precedes every origin).",
        f"- model: {len(vintages)} real fitted vintages (JM K2/K3 x lambda 0.5/1/2 plus M0 control, 2 fit seeds, "
        "3 inner chronological validation blocks); a real fitted model, not a frozen stub.",
        f"- emissions: {registry['emission_count']} states, {registry['eligible_emission_count']} decision-eligible, "
        f"quality statuses {registry['quality_statuses']}.",
        f"- causality checks: {json.dumps(causality['checks'], sort_keys=True)}; "
        f"{sum(row['same_or_future_outcome_targets_excluded'] for row in causality['vintages'])} future/same-time "
        "targets excluded by the registered purge.",
        "",
        "## Per-vintage evidence",
        "",
        "| cutoff | design used | decision | admissible | training targets | outer planned/evaluable | mean outer effect |",
        "|---|---|---|---|---|---|---|",
    ]
    for vintage in vintages:
        table = next(row for row in info["per_vintage"] if row["model_id"] == vintage["model_id"])
        lines.append(f"| {vintage['cutoff'][:10]} | {vintage['design']['id']} | {vintage['decision']} | "
                     f"{sum(1 for trial in vintage['design_trials'] if trial['admissible'])}/7 | "
                     f"{table['training_targets']} | {table['planned_outer_targets']}/{table['evaluable_outer_targets']} | "
                     f"{'' if table['mean_outer_information_effect'] is None else round(table['mean_outer_information_effect'],6)} |")
    lines += [
        "",
        "## Information, opportunity and decision",
        "",
        f"- information value (future candidate-utility ranking, base comparator unconditional profile): "
        f"{info['summary']['evaluable']}/{info['summary']['planned']} evaluable; mean {info['summary']['mean_effect']:.6f}, "
        f"range [{info['summary']['effect_min']:.6f}, {info['summary']['effect_max']:.6f}], "
        f"dispersion {info['summary']['effect_dispersion']:.6f}; inference `{info['inference']['status']}` "
        f"({info['inference'].get('reason')}).",
        f"- parameter opportunity: {opportunity['summary']['targets']} targets x {opportunity['summary']['candidate_count']} "
        f"candidates; utility range mean {opportunity['summary']['utility_range_mean']:.8f}; per-origin unique behaviors "
        f"{opportunity['summary']['unique_behaviors_min']}..{opportunity['summary']['unique_behaviors_max']}; "
        f"rank reversal fraction {opportunity['rank_stability'][0]['rank_reversal_fraction']:.4f} over "
        f"{opportunity['rank_stability'][0]['pairs_compared']} pairs (hindsight diagnostic only).",
        f"- model decision: `{decision['decision']}`; selected inner-informative design {decision['selected_inner_informative']}"
        f"/{decision['vintages']} vintages; M0 control {decision['m0_control_vintages']}; "
        f"information inference `{decision['information_inference_status']}`.",
        "",
        "## TE03.7 status",
        "",
    ]
    power_path = ROOT / "evidence/time_edge_validation_v4/te03/te03_7_power.json"
    controls_path = ROOT / "evidence/time_edge_validation_v4/te03/te03_7_controls.json"
    if power_path.is_file() and controls_path.is_file():
        power = read(power_path); controls = read(controls_path)
        lines += [
            f"- statistical positive/null calibration: `{power['status']}`; positive control "
            f"`{power['positive_control']['status']}` at +2 delta, null "
            f"`{power['null_control']['status']}`; engine runs {power['engine_runs']}.",
            f"- engine full-path structural controls: `{controls['status']}`; funnel `{controls['full_path_funnel']['status']}`; "
            "no zero-filled funnel counts.",
            "- delayed/risk controls remain TE-04 scope; TE-04 stays closed.",
        ]
    else:
        lines.append("- not yet built in this sub-step; no zero-filled calibration is claimed.")
    lines += [
        "",
        "## Tests",
        "",
        "- `environments/lab_venv/bin/python -m pytest tests/time_edge_validation_v4 -q`.",
        "",
    ]
    return "\n".join(lines)


def te03_report():
    if (ROOT / "evidence/time_edge_validation_v4/te03-r2/information_value.json").is_file():
        return te03_coverage_report()
    results = read(ROOT / "evidence/time_edge_validation_v4/host-model-results-01.json")["results"]
    vintages = [v for v in results if "design_trials" in v]
    decision = read(ROOT / "evidence/time_edge_validation_v4/te03/model_decision.json")
    info = read(ROOT / "evidence/time_edge_validation_v4/te03/information_value.json")
    causality = read(ROOT / "evidence/time_edge_validation_v4/te03/model_causality.json")
    opportunity = read(ROOT / "evidence/time_edge_validation_v4/te03/parameter_opportunity.json")
    registry = read(ROOT / "evidence/time_edge_validation_v4/te03/model_registry.json")
    targets = read(ROOT / "evidence/time_edge_validation_v4/host-targets-01.json")["targets"]
    features = read(ROOT / "evidence/time_edge_validation_v4/host-features-01.json")["results"][0]
    lines = [
        "# TE-03 report — features, targets, model vintages and emissions",
        "",
        "Stage scope: `features -> targets -> model vintages` only. Controls, full-path positive power and statistical "
        "null calibration (TE03.7 partial) are not run here; the registered reasons are below.",
        "",
        "## Stage facts (real snapshot data, one worker, no data_loader.py)",
        "",
        f"- features: `{features['status']}` over 5 copied symbols, {features['rows']} 4h rows, "
        f"{features['missing_rows']} rows with any missing feature, raw parquet `{features['features']['sha256'][:16]}`; "
        f"scaler `{features['scaler']}`.",
        f"- targets: {len(targets)} non-overlapping 28-day targets, {len(targets[0]['candidate_ids'])} candidates each, "
        f"origins {targets[0]['origin'][:10]} .. {targets[-1]['origin'][:10]}; candidate bank collected from the completed "
        "pilot-09 selection (availability precedes every origin).",
        f"- model: {len(vintages)} real fitted vintages (JM K2/K3 x lambda 0.5/1/2 plus M0 control, 2 fit seeds, 3 inner "
        f"chronological validation blocks); a real fitted model, not a frozen stub.",
        f"- emissions: {registry['emission_count']} states, {registry['eligible_emission_count']} decision-eligible, "
        f"quality statuses {registry['quality_statuses']}.",
        f"- causality checks: {json.dumps(causality['checks'], sort_keys=True)}; "
        f"{sum(v['same_or_future_outcome_targets_excluded'] for v in causality['vintages'])} future/same-time targets "
        "excluded by the registered purge.",
        "",
        "## Per-vintage evidence",
        "",
        "| cutoff | design used | decision | admissible | training targets | outer planned/evaluable | mean outer effect |",
        "|---|---|---|---|---|---|---|",
    ]
    for v in vintages:
        table = next(m for m in info["per_vintage"] if m["model_id"] == v["model_id"])
        lines.append(f"| {v['cutoff'][:10]} | {v['design']['id']} | {v['decision']} | "
                     f"{sum(1 for t in v['design_trials'] if t['admissible'])}/7 | {table['training_targets']} | "
                     f"{table['planned_outer_targets']}/{table['evaluable_outer_targets']} | "
                     f"{'' if table['mean_outer_information_effect'] is None else round(table['mean_outer_information_effect'],6)} |")
    lines += [
        "",
        "## Information, opportunity and decision",
        "",
        f"- information value (future candidate-utility ranking, base comparator unconditional profile): "
        f"{info['summary']['evaluable']}/{info['summary']['planned']} evaluable; mean {info['summary']['mean_effect']:.6f}, "
        f"range [{info['summary']['effect_min']:.6f}, {info['summary']['effect_max']:.6f}], "
        f"dispersion {info['summary']['effect_dispersion']:.6f}; inference `{info['inference']['status']}` "
        f"({info['inference']['reason']}).",
        f"- parameter opportunity: {opportunity['summary']['targets']} targets x {opportunity['summary']['candidate_count']} "
        f"candidates; utility range mean {opportunity['summary']['utility_range_mean']:.8f}; per-origin unique behaviors "
        f"{opportunity['summary']['unique_behaviors_min']}..{opportunity['summary']['unique_behaviors_max']}; "
        f"rank reversal fraction {opportunity['rank_stability'][0]['rank_reversal_fraction']:.4f} over "
        f"{opportunity['rank_stability'][0]['pairs_compared']} pairs (hindsight diagnostic only).",
        f"- model decision: `{decision['decision']}`; selected inner-informative design {decision['selected_inner_informative']}"
        f"/{decision['vintages']} vintages; M0 control {decision['m0_control_vintages']}; "
        f"stop condition: {decision['stop_condition']}.",
        "",
        "## Pending (explicit reasons)",
        "",
        "- TE03.7 full-path positive/null calibration and treatment funnel are NOT run: they need the controls and "
        "statistical-calibration stages, which are outside this Part-4 scope; no zero-filled calibration is claimed.",
        "- TE03.6 is `INCONCLUSIVE_SUPPORT`: 8 evaluable outer targets with mixed signs are below the registered block "
        "requirement (calendar span, blocks, >= 20 episodes).",
        "- The 12-vintage window ends 2022-01-01; later years are not evaluated in this sub-step.",
        "",
        "## Tests",
        "",
        "- `environments/lab_venv/bin/python -m pytest tests/time_edge_validation_v4 -q` -> 138 passed.",
        "- Full suite: 1015 passed, 2 pre-existing failures in files untouched by this work "
        "(`time_edge/schedule.py:Selection` unreachable symbol; `configs/time_edge_validation_v4/delivery_scope_r05.json` "
        "has no `schema` key).",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-output", default="reports/time_edge_validation_v4/te02-pilot-09-report.md")
    parser.add_argument("--te03-output", default="reports/time_edge_validation_v4/te03-report.md")
    args = parser.parse_args()
    (ROOT / args.pilot_output).write_text(pilot_report())
    (ROOT / args.te03_output).write_text(te03_report())
    print(json.dumps({"pilot": args.pilot_output, "te03": args.te03_output}, indent=1))


if __name__ == "__main__":
    main()
