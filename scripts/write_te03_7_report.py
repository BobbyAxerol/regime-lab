#!/usr/bin/env python3
"""Render the TE03.7 power/null/control report from committed artifacts only."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.storage import read  # noqa: E402


def allocation_state(allocation_id):
    directory = ROOT / "evidence/time_edge_validation_v4/allocations" / allocation_id
    con = sqlite3.connect(directory / "ledger.sqlite")
    total = con.execute("SELECT budget FROM study").fetchone()[0]
    charged = con.execute("SELECT COALESCE(SUM(COALESCE(wall,reserved)),0) FROM attempt").fetchone()[0]
    revisions = con.execute("SELECT id,old_budget,new_budget,prior_charged FROM budget_revision ORDER BY applied_at").fetchall()
    con.close()
    return total, charged, revisions


def funnel_lines(funnel, heading):
    lines = [heading, ""]
    lines.append(f"- status `{funnel['status']}` for condition `{funnel['condition']}`; cell `{funnel.get('cell_id')}`.")
    lines += ["", "| step | count | denominator | reason | denominator reason |", "|---|---|---|---|---|"]
    for step in funnel["steps"]:
        count = "" if step["count"] is None else step["count"]
        denominator = "" if step["denominator"] is None else step["denominator"]
        lines.append(f"| {step['step']} | {count} | {denominator} | {step.get('reason') or ''} | "
                     f"{step.get('denominator_reason') or ''} |")
    lines.append("")
    for step in funnel["steps"]:
        lines.append(f"- `{step['step']}` rule: {step.get('rule')}")
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--power", default="evidence/time_edge_validation_v4/te03/te03_7_power.json")
    parser.add_argument("--controls", default="evidence/time_edge_validation_v4/te03/te03_7_controls_r2.json")
    parser.add_argument("--blocker", default="evidence/time_edge_validation_v4/te03/controls_06_blocker.json")
    parser.add_argument("--allocation-id", default="TE02-PILOT-R03")
    parser.add_argument("--tests-summary", default="tests/time_edge_validation_v4/test_te03_7.py (guards)")
    parser.add_argument("--output", default="reports/time_edge_validation_v4/te03-7-report.md")
    args = parser.parse_args()
    power = read(ROOT / args.power)
    controls = read(ROOT / args.controls)
    blocker_path = ROOT / args.blocker
    blocker = read(blocker_path) if blocker_path.is_file() else None
    total, charged, revisions = allocation_state(args.allocation_id)
    lines = [
        "# TE03.7 report — positive/null power and full-path controls",
        "",
        f"- Evidence: `{args.power}` and `{args.controls}`.",
        f"- Allocation `{args.allocation_id}`: total {total:.0f}s, charged {charged:.3f}s; revisions "
        f"{', '.join(row[0] for row in revisions)}.",
        "- Scope: statistical calibration of the registered family plus the bounded engine full-path controls. "
        "No market edge claim; TE-04 stays closed.",
        "",
        "## Positive/null statistical calibration (known synthetic effects; no engine call)",
        "",
        f"- calibration status: `{power['status']}`; source `{power['source']['path']}`; engine runs {power['source']['engine_runs']}.",
        "| world (delta units) | worlds | family rejections | rate | Wilson 95% | mean of true effects |",
        "|---|---|---|---|---|---|",
    ]
    for row in power["conditions"]:
        lines.append(f"| {row['true_effect_delta_units']} | {row['worlds']} | {row['family_rejections']} | "
                     f"{row['rate']:.4f} | [{row['wilson95'][0]:.4f}, {row['wilson95'][1]:.4f}] | "
                     f"{json.dumps(row['true_means'])} |")
    positive = power["positive_control"]
    null = power["null_control"]
    lines += [
        "",
        f"- positive control at +2 delta: family rate {positive['family_rate']:.4f}, per-hypothesis power "
        f"{json.dumps(positive['per_hypothesis_power'])}, recovered **{positive['recovered']}** ({positive['status']}).",
        f"- null controls: maximum family Wilson upper {null['maximum_family_wilson_upper']:.4f} against tolerance "
        f"{null['tolerance']}; false positive **{null['false_positive']}** ({null['status']}).",
        f"- `full_pipeline_calibration`: `{power['source']['full_pipeline_calibration']}` — the statistical payload "
        "does not certify the engine path.",
        "",
        "## Engine full-path structural controls",
        "",
        f"- run `{controls['run_id']}`: `{controls['status']}`; allocation revision "
        f"`{controls.get('allocation_revision')}`; stop reason: `{controls['run_stop_reason']}`.",
    ]
    sharding = controls.get("sharding")
    if sharding:
        lines.append(f"- sharding: {sharding['unit']}; worlds {', '.join(sharding['worlds'])}; "
                     f"{sharding['shards_completed']}/{sharding['shards_attempted']} attempted shards complete of "
                     f"{sharding['shards_planned']} planned; per-shard cap {sharding['per_shard_cap_seconds']:.0f}s.")
    lines += [
        "| task | world | condition | cap s | status | wall s | reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for task in controls["tasks"]:
        lines.append(f"| {task['task_id']} | {task.get('world')} | {task['condition']} | "
                     f"{task['wall_cap_seconds']:.0f} | {task['status']} | "
                     f"{'' if task['wall_seconds'] is None else round(task['wall_seconds'],1)} | {task['reason']} |")
    if controls.get("measured_basis"):
        basis = controls["measured_basis"]
        lines += [
            "",
            f"- pre-shard projection (old monolith profile): lower bound per condition "
            f"{basis.get('lower_bound_seconds_per_condition'):.0f}s ({basis.get('lower_bound_hours_per_condition')}h); "
            f"two conditions {basis.get('two_condition_lower_bound_hours')}h, excluding "
            f"{'; '.join(basis.get('excludes', []))}.",
        ]
    shard_ref = controls.get("shard_profile")
    if shard_ref:
        shard = read(ROOT / shard_ref["path"])
        residual = shard["measured_residual_lower_bound_per_condition_seconds"]
        lines.append(f"- measured shard residual per world: targets remaining "
                     f"{residual['targets_remaining_18_x_234.0']:.0f}s + model fits "
                     f"{residual['model_fits_53_x_21.015']:.0f}s + calibration/initial selections "
                     f"{residual['calibration_and_initial_selections_7_x_1618.0']:.0f}s = "
                     f"{residual['lower_bound_total']:.0f}s, excluding {', '.join(residual['excluded'])}; "
                     f"per-shard cap {shard['per_shard_cap_seconds']:.0f}s.")
    lines += ["", "## Treatment funnel", ""]
    by_condition = controls.get("full_path_funnels_by_condition") or {}
    if by_condition:
        for condition in sorted(by_condition):
            lines += funnel_lines(by_condition[condition], f"### {condition}")
    else:
        lines += funnel_lines(controls["full_path_funnel"], "### not measured")
    partials = controls.get("partial_funnels") or []
    if partials:
        lines += ["", "### Partial shards (stages that did publish, nothing zero-filled)", ""]
        lines += ["| shard | condition | world | worlds | features | searches (32-trial bank) | targets | vintages |",
                  "|---|---|---|---|---|---|---|---|"]
        for funnel in partials:
            m = funnel["partial_measurements"]
            lines.append(f"| {funnel['shard_task_id']} | {funnel['condition']} | {funnel['world']} | "
                         f"{m['worlds_generated']} | {m['features_built']} | {m['searches_completed']} | "
                         f"{m['targets_completed']}/{m['targets_planned']} | "
                         f"{m['model_vintages_completed']}/{m['model_vintages_planned']} |")
    lines += ["", "## 32-trial Mode 4 selection result", ""]
    selections = controls.get("selection_results") or []
    if not selections:
        lines.append("- no completed full-path control: no 32-trial selection result exists; "
                     "nothing is inferred and no fills are fabricated.")
    for result in selections:
        candidate = result.get("selected_candidate") or {}
        components = result.get("components") or {}
        lines += [
            f"### {result['condition']} — candidate bank selection",
            "",
            f"- search artifact `{result['search_file']}`, cutoff `{result['cutoff']}`, status `{result['status']}`.",
            f"- selected trial {result.get('trial_id')}: params `{json.dumps(result.get('params'))}`, "
            f"objective {result.get('objective')}.",
            f"- components: mean IS Sharpe {components.get('mean_is_sharpe')}, mean OOS Sharpe "
            f"{components.get('mean_oos_sharpe')}, mean decay {components.get('mean_decay')}, "
            f"std decay {components.get('std_decay')}, pruned {components.get('pruned')}.",
            f"- trials completed {result.get('trials_completed')}/{result.get('trials_configured')}; "
            f"scorer calls {result.get('scorer_calls')}; candidate cache hits "
            f"{result.get('candidate_cache_hits')}.",
            f"- selected candidate `{candidate.get('candidate_file')}`: status `{candidate.get('status')}`, "
            f"fills {candidate.get('fill_count')}.",
            "",
        ]
    lines += [
        f"- `truth_entered_learner`: `{controls['truth_entered_learner']}`; fabricated fills: "
        f"`{controls['fabricated_fills']}`.",
        f"- boundary power qualification: `{controls['boundary_power_qualification']}` — a structural world with "
        "opportunity does not specify a known net learner effect of 2 delta.",
        "",
        "## P0 gate checks",
        "",
        "| gate | status |",
        "|---|---|",
    ]
    for name, value in (controls.get("p0_gate") or {}).items():
        lines.append(f"| {name} | {'PASS' if value else 'FAIL'} |")
    if blocker is not None:
        lines += [
            "",
            "## Blocker",
            "",
            f"- `{args.blocker}`: `{blocker['status']}` — {blocker['reason']}.",
            f"- measured: {blocker['measured']['shards_attempted']} attempted / "
            f"{blocker['measured']['shards_planned']} planned shards, "
            f"{blocker['measured']['shards_completed']} complete; bank selection 32 trials complete: "
            f"`{blocker['measured']['bank_selection_32_trials']['complete']}`.",
            f"- next: {blocker['next']}",
        ]
    lines += [
        "",
        "## Delayed and risk controls",
        "",
        f"- {power['delayed_risk_controls']['status']}: {power['delayed_risk_controls']['reason']}",
        "",
        "## Tests",
        "",
        f"- {args.tests_summary}",
        "",
    ]
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    print(json.dumps({"report": args.output, "power_status": power["status"], "controls_status": controls["status"]}, indent=1))


if __name__ == "__main__":
    main()
