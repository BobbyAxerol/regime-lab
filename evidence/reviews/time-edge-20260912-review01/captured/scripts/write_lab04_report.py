#!/usr/bin/env python
"""Render reports/lab04_report.md from committed artifacts only.

This never reruns a selector or an experiment. If an artifact is missing the
report says so rather than filling the gap.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"

from crypto_regime_lab.evidence import glossary as G  # noqa: E402
from crypto_regime_lab.evidence.data_sources import data_provenance_lines  # noqa: E402
OUT = LAB_ROOT / "reports" / "lab04_report.md"


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def fmt(value, digits: int = 4, signed: bool = True) -> str:
    """A leading + belongs on a return, not on a count."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    if isinstance(value, int):
        return str(value)
    return str(value)


def main() -> int:
    trace = load("lab04_installed_wfo_trace.json")
    counter = load("lab04_selector_counterexamples.json")
    designs = load("lab04_probe_designs.json")
    parity = load("lab04_incumbent_parity.json")
    baseline = load("lab04_calendar_baseline.json")
    radius = load("lab04_probe_radius_sensitivity.json")
    audit = load("lab04_task_audit.json")
    coverage = load("acceptance_test_coverage.json")
    readlock = load("readlock_verification.json")

    lines: list[str] = []
    add = lines.append
    add("# LAB-04 — Calendar baseline và robust-neighborhood selection")
    add("")
    add("Generated from committed artifacts by `scripts/write_lab04_report.py`. "
        "No optimizer or experiment is rerun here.")
    add("")
    add("## Glossary — what each term means and where it applies")
    add("")
    add("| term | meaning | where it applies in this lab |")
    add("|---|---|---|")
    for term, meaning, where in G.BY_PHASE["LAB-04"]:
        add(f"| **{term}** | {meaning} | {where} |")
    add("")

    # ---- L04.1 ----
    add("## L04.1 — What the installed WFO actually does")
    add("")
    if trace is None:
        add("**MISSING** `configs/lab04_installed_wfo_trace.json`.")
    else:
        add(f"The public route's default resolves the winner in "
            f"`{trace['public_route_default']['resolved_by']}` as "
            f"`{trace['public_route_default']['rule']}`.")
        add("")
        add(trace["search_finding"])
        add("")
        add("| mode | trials | folds | searched | engine declares OOS used | mutation probe |")
        add("|---|---|---|---|---|---|")
        for mode, info in trace["search_behaviour"].items():
            declared = (trace["modes"]["traces"][mode].get("declared_claims", {})
                        .get("oos_used_for_selection"))
            probe = trace["modes"]["oos_usage"].get(mode, {})
            add(f"| `{mode}` | {info['trial_count']} | {info['fold_count']} | "
                f"{info['searched']} | {declared} | {probe.get('status')} → "
                f"{probe.get('uses_oos_for_selection')} |")
        for key, probe in trace["modes"]["oos_usage"].items():
            if "@" in key:
                add(f"| `{key}` | — | — | — | — | {probe.get('status')} → "
                    f"{probe.get('uses_oos_for_selection')} |")
        add("")
        add(f"- {trace['mode_5_note']}")
        add(f"- **Legacy OOS labelling.** {trace['legacy_oos_labelling']['rule']} "
            f"Modes declaring OOS-adjusted selection: "
            f"`{trace['legacy_oos_labelling']['modes_declaring_oos_selection']}`.")
        add(f"- **Probe power.** {trace['legacy_oos_labelling']['behavioural_probe_limit']}")
        defaults = trace["installed_defaults"]
        add("")
        add("| dimension | measured |")
        add("|---|---|")
        add(f"| sampler | `{defaults['optuna_sampler']['class']}` + "
            f"`{defaults['optuna_sampler']['pruner']}`, seed "
            f"{defaults['optuna_sampler']['default_random_seed']} |")
        add(f"| default trials | {defaults['optuna_sampler']['default_optuna_trials']} |")
        add(f"| objective backend | {defaults['objective_backend']['lab_setting']} — "
            f"{defaults['objective_backend']['why']} |")
        add(f"| candidate freeze | `{defaults['candidate_freeze']['stage_1']}` → "
            f"`{defaults['candidate_freeze']['stage_2']}` |")
        add(f"| baseline floor | `min_trades_per_year="
            f"{defaults['baseline_floor']['min_trades_per_year']}`, "
            f"`trade_penalty_factor={defaults['baseline_floor']['trade_penalty_factor']}` — "
            f"no floor unless configured |")
        add(f"| retention | financial=`{defaults['retention']['financial_retention']}`, "
            f"research=`{defaults['retention']['research_retention']}`, "
            f"scope=`{defaults['retention']['financial_scope']}` |")
        add(f"| fold account policy | `{defaults['fold_account_policy']}` |")
    add("")

    # ---- L04.2 ----
    add("## L04.2 — Selector counterexamples, scoped by family")
    add("")
    if counter is None:
        add("**MISSING** `configs/lab04_selector_counterexamples.json`.")
    else:
        add(counter["scoping_rule"])
        add("")
        for name, info in counter["selector_families"].items():
            add(f"- **`{name}`** — {info['geometry']}")
        add("")
        add("| id | counterexample | family | verdict | source |")
        add("|---|---|---|---|---|")
        for case in counter["counterexamples"]:
            add(f"| {case['id']} | {case['title']} | `{case['selector_family']}` | "
                f"**{case['verdict']}** | `{', '.join(case['source_symbols'][:2])}` |")
        add("")
        for case in counter["counterexamples"]:
            if case["verdict"] != "DEFECT_CONFIRMED":
                continue
            add(f"**{case['id']} — {case['title']}**")
            add("")
            add(f"- observed: `{json.dumps(case['observed'])}`")
            add(f"- expected: {case['expectation']}")
            add(f"- reproducer: {case['reproducer']}")
            if case.get("note"):
                add(f"- scope: {case['note']}")
            add("")
    add("")

    # ---- L04.3 / L04.4 ----
    add("## L04.3 — Candidate-independent probe engine")
    add("")
    if designs is None:
        add("**MISSING** `configs/lab04_probe_designs.json`.")
    else:
        add(designs["determinism"])
        add("")
        add("| alpha | probes | unique | structurally invalid rejections |")
        add("|---|---|---|---|")
        for alpha_id, design in designs["designs"].items():
            add(f"| {alpha_id} | {design['probe_count']} | {design['unique_probe_ids']} | "
                f"{design['rejection_count']} |")
        add("")
        rules = next(iter(designs["designs"].values()))["accounting_rules"]
        for key, value in rules.items():
            add(f"- `{key}` = {value}")
    add("")
    add("### Registered probe-radius sensitivity (guide 7.2)")
    add("")
    if radius is None:
        add("**NOT RUN YET** — `configs/lab04_probe_radius_sensitivity.json` is absent.")
    else:
        add(radius["rule"])
        add("")
        add("| radius | arm B status | eligible | G (comparable) | R (NOT comparable) | "
            "distance from the primary selection |")
        add("|---|---|---|---|---|---|")
        for key, rec in radius["results"].items():
            mark = " **(primary)**" if rec["radius"] == radius["primary_radius"] else ""
            add(f"| {rec['radius']}{mark} | {rec['arm_B_status']} | {rec['eligible_count']} | "
                f"{fmt(rec['arm_B_G'])} | {fmt(rec['arm_B_R'])} | "
                f"{fmt(radius['schema_distance_from_primary_selection'].get(key))} |")
        add("")
        add(f"- arm B selection changes with the radius: "
            f"**{radius['selection_changed_with_radius']}**")
        add(f"- arm A is radius independent: **{radius['arm_A_is_radius_independent']}**")
        add("")
        add(f"> **Do not read R down this column.** {radius['R_is_not_comparable_across_radii']}")
        add("")
        add(f"Comparable across radii: `{radius['comparable_across_radii']}`. "
            f"Not comparable: `{radius['not_comparable_across_radii']}`. "
            "This is one cutoff of one cell, so it characterises the design's sensitivity; it is "
            "not a result about which radius performs better, and the primary stays "
            f"{radius['primary_radius']}.")
    add("")
    add("## L04.4 — Robust scoring and incumbent parity")
    add("")
    if parity is None:
        add("**MISSING** `configs/lab04_incumbent_parity.json`.")
    else:
        add(f"- {parity['rule']}")
        add(f"- same episode count: **{parity['same_episode_count']}**, "
            f"same neighbour budget: **{parity['same_neighbour_budget']}**")
        add(f"- guard **before** (raw quality G): winner "
            f"`{parity['guard_before']['winner']}`")
        add(f"- guard **after** (robust objective R): winner "
            f"`{parity['guard_after']['winner']}`")
        add(f"- selection hyperparameters: `{json.dumps(parity['hyperparameters'])}`")
    add("")

    # ---- L04.5 / L04.6 ----
    add("## L04.5 / L04.6 — Arm A vs arm B on the frozen calendar")
    add("")
    if baseline is None:
        add("**NOT RUN YET** — `configs/lab04_calendar_baseline.json` is absent, so no A/B claim "
            "is made in this report.")
    else:
        if not baseline.get("matrix_complete", False):
            add(f"> **PARTIAL MATRIX — {baseline.get('partial_matrix_warning', 'incomplete')}.** "
                "No scope claim is made from it.")
            add("")
        add(f"Arm **A**: {baseline['arms']['A']}  ")
        add(f"Arm **B**: {baseline['arms']['B']}  ")
        add(f"Regime information used: **{baseline['regime_information_used']}**")
        add("")
        add("Matched between the arms:")
        for condition in baseline["matched_conditions"]:
            add(f"- {condition}")
        add("")
        cal = baseline["calendar"]
        add(f"Calendar: train {cal['train_days']}D, test {cal['test_days']}D, "
            f"{cal['folds']} folds from {cal['first_cutoff']}, "
            f"{cal['inner_episodes']} equal-length inner episodes per training window.")
        budget = baseline["search_budget"]
        add(f"Budget per cutoff: {budget['discovery_trials']} discovery + "
            f"{budget['anchors']}+incumbent anchors × {budget['probes_per_anchor']} probes "
            f"= {budget['nominal_total']} nominal.")
        effort = baseline["search_effort"]
        add(f"Actual effort: **{effort['unique_executions']} unique executions**, "
            f"**{effort['candidate_episode_visits']} candidate-episode visits**, "
            f"{effort['structurally_invalid']} structurally invalid, "
            f"{effort['runtime_errors']} runtime errors. {effort['reporting_rule']}")
        add("")
        add("### Every cell, win or lose")
        add("")
        add("```")
        for line in baseline["console_table"]:
            add(line)
        add("```")
        add("")
        add("### What each arm was allowed to choose from")
        add("")
        add("Both arms are handed the identical pool of evaluations at every cutoff. They differ "
            "in admissibility, and that difference is the point rather than a confound: arm A "
            "ranks the whole pool on the in-sample objective, while arm B may only choose a "
            "candidate that has a local panel and clears the quality, survival and local-evidence "
            "gates. A pure discovery point with no designed neighbourhood is "
            "`INSUFFICIENT_LOCAL_EVIDENCE` for arm B by construction.")
        add("")
        pooled = {}
        admissible_a, admissible_b = [], []
        for cell in baseline["cells"]:
            for fold in cell.get("folds", []):
                evidence = fold.get("cutoff_evidence")
                if not evidence:
                    continue
                for status, count in evidence["robust_status_counts"].items():
                    pooled[status] = pooled.get(status, 0) + count
                admissible_a.append(evidence["arm_A"].get("candidates_considered") or 0)
                admissible_b.append(evidence["arm_B"].get("eligible_count") or 0)
        if admissible_a:
            add(f"- mean candidates arm A ranked per cutoff: "
                f"**{sum(admissible_a) / len(admissible_a):.1f}**")
            add(f"- mean candidates arm B found admissible per cutoff: "
                f"**{sum(admissible_b) / len(admissible_b):.1f}**")
        if pooled:
            add(f"- robust-score status counts across every cutoff: `{json.dumps(pooled)}`")
        add("")
        add("### Contrast B − A")
        add("")
        contrast = baseline["contrast_B_minus_A"]
        labels = {"net_return": "net return over the chained account",
                  "sharpe": "Sharpe over the whole chained horizon (NOT annualised)"}
        for metric in ("net_return", "sharpe"):
            test = contrast[metric]
            add(f"- **{labels[metric]}**: B better in {test['B_better']}, A better in "
                f"{test['A_better']}, ties {test['ties']} of {test['cells']} cells; "
                f"sign-test p = {test['two_sided_sign_test_p']}")
        add(f"- mean difference {fmt(contrast['mean_net_return_difference'])}, "
            f"median {fmt(contrast['median_net_return_difference'])}, "
            f"worst cell {fmt(contrast['worst_cell_difference'])}, "
            f"best cell {fmt(contrast['best_cell_difference'])}")
        add(f"- {contrast['net_return']['caveat']}")
        add("")
        add("### Registered hypothesis and the registered endpoint")
        add("")
        hyp = baseline["registered_hypothesis"]
        add(f"This phase evaluates exactly one registered contrast, **{hyp['hypothesis_id']} = "
            f"{hyp['contrast']}**, registered {hyp['registered_at_utc']}: "
            f"*{hyp['question']}*")
        add("")
        add(f"- registered primary endpoint: **{hyp['primary_endpoint']}**")
        add(f"- {hyp['endpoint_note']}")
        add(f"- registered minimum economic effect: "
            f"**{hyp['minimum_economic_effect_per_day']:.2e}/day "
            f"({hyp['minimum_economic_effect_bps_per_day']} bps/day)**, fixed before any arm "
            f"comparison = {hyp['minimum_effect_registered_before_any_comparison']}")
        add(f"- **measured mean daily net-return difference (B−A): "
            f"{hyp['mean_daily_net_return_difference']:.3e}/day**")
        add(f"- cells whose own daily difference clears the minimum effect: "
            f"**{hyp['cells_above_the_minimum_effect']}/{hyp['cells_measured']}**")
        magnitude = ("BELOW" if abs(hyp["mean_daily_net_return_difference"] or 0.0)
                     < hyp["minimum_economic_effect_per_day"] else "above")
        add("")
        add(f"> The pooled effect is **{magnitude}** the registered minimum. A difference below it "
            "sits inside the registered cost-stress band and is reported as inconclusive, never as "
            "an edge. The large-looking terminal chained returns elsewhere in this report are "
            "context, not the endpoint.")
        add("")
        add(f"**Conclusion level: `{hyp['conclusion_level']}`** "
            f"(from the registered vocabulary {hyp['conclusion_level_vocabulary']})")
        add("")
        if hyp["blockers_preventing_a_stronger_claim"]:
            add("Blockers preventing a stronger claim:")
            for blocker in hyp["blockers_preventing_a_stronger_claim"]:
                add(f"- {blocker}")
            add("")
        add(f"- multiplicity: {hyp['family_adjustment']} — applied here: "
            f"**{hyp['family_adjustment_applied']}**. {hyp['family_adjustment_note']}")
        add("- falsification commitments in force:")
        for commitment in hyp["falsification_commitments_in_force"]:
            add(f"  - {commitment}")
        add(f"- exercised in this phase: {hyp['commitment_exercised']}")
        add("")
        add("### How binding is the registered gate? (declared post-hoc)")
        add("")
        gate = baseline["gate_bindingness_diagnostic"]
        add(f"The registered gate is `min_quality={gate['registered_gate']['min_quality']}`, "
            f"`P_survive >= {gate['registered_gate']['survive_threshold']}`, fixed on development "
            "before any arm ran. **It stays the primary and is not revised here.** "
            f"{gate['why_it_is_reported']}")
        add("")
        add("| min_quality | P_survive ≥ | registered | cutoffs with ≥1 admissible | median eligible |")
        add("|---|---|---|---|---|")
        for row in gate["grid"]:
            mark = " **(registered)**" if row["is_the_registered_gate"] else ""
            add(f"| {row['min_quality']} | {row['survive_threshold']} |{mark or ' –'} | "
                f"{row['cutoffs_with_at_least_one_admissible_candidate']}/{row['cutoffs']} | "
                f"{fmt(row['median_eligible_candidates'], 1, False)} |")
        add("")
        add(f"- local panels are NOT the bottleneck: "
            f"**{gate['cutoffs_with_at_least_one_computable_R']}/{gate['cutoffs_total']}** cutoffs "
            f"had at least one candidate with a computable R")
        add(f"- {gate['status_ordering_note']}")
        add(f"- **{gate['what_this_cannot_say']}**")
        add("")
        add("### Cells where an arm never used its selector at all")
        add("")
        stuck = baseline["cells_where_an_arm_never_used_its_selector"]
        for arm in ("A", "B"):
            record = stuck[arm]
            add(f"- arm {arm}: **{record['cells']}/{record['of_cells']}** cells held the "
                f"registered seed point at every cutoff")
            for row in record["detail"]:
                add(f"  - `{row['cell']}` — {row['cutoffs']} cutoffs, binding constraint "
                    f"`{row['binding_constraint']}`, net return {fmt(row['net_return'])}")
        add("")
        add(stuck["reading"])
        add("")
        sub = baseline["contrast_where_both_arms_actually_selected"]
        add("| contrast | cells | B better | A better | sign-test p | mean daily B−A |")
        add("|---|---|---|---|---|---|")
        full = baseline["contrast_B_minus_A"]["net_return"]
        hyp0 = baseline["registered_hypothesis"]
        add(f"| all cells | {full['cells']} | {full['B_better']} | {full['A_better']} | "
            f"{full['two_sided_sign_test_p']} | "
            f"{hyp0['mean_daily_net_return_difference']:.3e} |")
        sub_test = sub["sign_test"]
        add(f"| both arms actually selected | {sub['cells_kept']} | {sub_test['B_better']} | "
            f"{sub_test['A_better']} | {sub_test['two_sided_sign_test_p']} | "
            f"{sub['mean_daily_net_return_difference']:.3e} |")
        add("")
        add(f"Excluded: `{', '.join(sub['cells_excluded'])}`. {sub['reading']}")
        add("")
        add("### The same contrast, split per alpha")
        add("")
        per_alpha = baseline["contrast_by_alpha"]
        add("| alpha | cells | B better | A better | winner | mean B−A | agrees with pooled |")
        add("|---|---|---|---|---|---|---|")
        for alpha_id, record in per_alpha.items():
            if not isinstance(record, dict):
                continue
            add(f"| {alpha_id} | {record['cells']} | {record['B_better']} | "
                f"{record['A_better']} | **{record['winner']}** | "
                f"{fmt(record['mean_difference'])} | "
                f"{record['sign_agrees_with_the_pooled_result']} |")
        add("")
        if per_alpha["reversals"]:
            add(f"> **SIGN REVERSAL in {', '.join(per_alpha['reversals'])}.** The pooled winner is "
                f"`{per_alpha['pooled_winner']}`, but inside these alphas the sign is the other "
                "way. {r}".format(r=per_alpha["reading"]))
        else:
            add(f"No sign reversal: every alpha agrees with the pooled winner "
                f"`{per_alpha['pooled_winner']}`.")
        add("")
        add("### Evidence reported before the selection claim (L04.6)")
        add("")
        add("| dimension | arm A | arm B |")
        add("|---|---|---|")
        tail = baseline["lower_tail"]
        add(f"| cells with a losing chain | {tail['A']['cells_with_a_losing_chain']} | "
            f"{tail['B']['cells_with_a_losing_chain']} |")
        add(f"| worst cell net return | {fmt(tail['A']['worst_cell_net_return'])} | "
            f"{fmt(tail['B']['worst_cell_net_return'])} |")
        add(f"| mean losing folds (of 6) | {fmt(tail['A']['mean_losing_folds'], 2, False)} | "
            f"{fmt(tail['B']['mean_losing_folds'], 2, False)} |")
        add(f"| mean max drawdown | {fmt(tail['A']['mean_max_drawdown'])} | "
            f"{fmt(tail['B']['mean_max_drawdown'])} |")
        conc = baseline["period_concentration"]
        add(f"| period concentration | {fmt(conc['A']['mean'], 4, False)} | "
            f"{fmt(conc['B']['mean'], 4, False)} |")
        finger = baseline["parameter_behaviour_fingerprint"]
        add(f"| engine fills | {finger['A']['engine_fills']} | {finger['B']['engine_fills']} |")
        add(f"| entries (positions opened) | {finger['A']['entries']} | "
            f"{finger['B']['entries']} |")
        add(f"| mean holding bars | {fmt(finger['A']['mean_holding_bars'], 1, False)} | "
            f"{fmt(finger['B']['mean_holding_bars'], 1, False)} |")
        add(f"| mean exposure | {fmt(finger['A']['mean_exposure'], 3, False)} | "
            f"{fmt(finger['B']['mean_exposure'], 3, False)} |")
        add(f"| mean parameter turnover | {fmt(finger['A']['mean_turnover'], 4, False)} | "
            f"{fmt(finger['B']['mean_turnover'], 4, False)} |")
        add(f"| distinct parameter sets per cell (of "
            f"{baseline['calendar']['folds']}) | "
            f"{fmt(finger['A']['mean_distinct_parameter_sets'], 2, False)} | "
            f"{fmt(finger['B']['mean_distinct_parameter_sets'], 2, False)} |")
        cov = baseline["local_coverage"]
        add(f"| median evaluated neighbours | "
            f"{fmt(cov['median_evaluated_neighbours_across_cutoffs'], 1, False)} | "
            f"(shared pool) |")
        add("")
        add(f"- {baseline['retention_rule']} Retention events per arm:")
        for arm in ("A", "B"):
            record = baseline["retention_events"][arm]
            add(f"  - arm {arm}: **{record['retained']}/{record['cutoffs']}** cutoffs kept the "
                f"incumbent — {json.dumps(record['reasons']) if record['reasons'] else 'none'}")
        if baseline["not_ready_detail"]:
            add(f"- **{baseline['cells_not_ready']} cells NOT_READY** with null metrics, never "
                f"PnL 0: {baseline['not_ready_detail'][0]['reason']}")
        add("")
        add("### Integrity checks on the chained account")
        add("")
        failed = []
        unconverged = 0
        legs = 0
        for cell in baseline["cells"]:
            for fold in cell.get("folds", []):
                if fold.get("status") != "OK":
                    continue
                for arm in ("A", "B"):
                    dep = fold["arms"][arm]["deployment"]
                    legs += 1
                    if dep["status"] != "DEPLOYED":
                        failed.append(f"{cell['alpha_id']}/{cell['symbol']} fold "
                                      f"{fold['fold']} arm {arm}: {dep.get('error')}")
                    elif dep.get("metrics") and dep["metrics"].get("converged") is False:
                        unconverged += 1
        add(f"- deployment legs chained: **{legs}**")
        add(f"- legs that failed to deploy (a gap in the chain, never a zero): "
            f"**{len(failed)}**")
        for line in failed[:8]:
            add(f"  - {line}")
        add(f"- legs where the adapter/engine fixed point did not converge: "
            f"**{unconverged}** (a non-converged leg is reported, not silently accepted)")
        add(f"- {baseline['trade_count_convention']}")
        add("")
        add("### What the deployed point's own local panel said")
        add("")
        eviD = baseline["local_evidence_behind_each_deployment"]
        add("| | arm A | arm B |")
        add("|---|---|---|")
        add(f"| deployments | {eviD['A']['deployments']} | {eviD['B']['deployments']} |")
        add(f"| deployed with no local panel at all | "
            f"{eviD['A']['deployed_without_any_local_panel']} | "
            f"{eviD['B']['deployed_without_any_local_panel']} |")
        add(f"| deployed a point its own panel rejects | "
            f"{eviD['A']['deployed_a_point_its_own_panel_rejects']} "
            f"({fmt(eviD['A']['share_its_own_panel_rejects'], 3, False)}) | "
            f"{eviD['B']['deployed_a_point_its_own_panel_rejects']} "
            f"({fmt(eviD['B']['share_its_own_panel_rejects'], 3, False)}) |")
        add(f"| robust status of the deployed point | "
            f"`{json.dumps(eviD['A']['robust_status_of_the_deployed_point'])}` | "
            f"`{json.dumps(eviD['B']['robust_status_of_the_deployed_point'])}` |")
        add("")
        add(eviD["reading"])
        add("")
        add("### Incumbent parity, measured on the run itself")
        add("")
        parity_run = baseline["incumbent_parity_measured"]
        add(f"- cutoffs: **{parity_run['cutoffs']}**; the incumbent was an anchor at "
            f"**{parity_run['cutoffs_where_the_incumbent_was_an_anchor']}** of them "
            f"(always = {parity_run['incumbent_always_an_anchor']})")
        add(f"- probes per anchor seen across every cutoff: "
            f"{parity_run['probes_per_anchor_values_seen']} — same budget for every anchor = "
            f"**{parity_run['every_anchor_got_the_same_probe_budget']}**")
        add(f"- smallest evaluated local panel seen: "
            f"{parity_run['min_evaluated_neighbours_values_seen']}")
        add(f"- {parity_run['rule']}")
        add("")
        add("### What else could explain the difference")
        add("")
        conf = baseline["confounds"]
        add(f"- incumbent retention rate: arm A "
            f"{fmt(conf['incumbent_retention_rate']['A'], 3, False)}, arm B "
            f"{fmt(conf['incumbent_retention_rate']['B'], 3, False)} "
            f"(gap {fmt(conf['retention_rate_gap'], 3, False)})")
        add(f"- material asymmetry: **{conf['asymmetric_switching_is_material']}** — "
            f"{conf['what_it_means']}")
        add(f"- the control that would separate them: {conf['control_that_would_separate_them']}")
        add("")
        add("### Verdict")
        add("")
        add(f"> {baseline['verdict']}")
        add("")
        add(f"{baseline['factorial_rule']}")
    add("")

    # ---- read lock ----
    add("## Read-lock status at the time of this phase")
    add("")
    if readlock is None:
        add("**MISSING** `configs/readlock_verification.json`.")
    else:
        add(f"- status: **{readlock['status']}**, primary run valid: "
            f"**{readlock['primary_run_valid']}**")
        add(f"- the lab's own snapshot bytes: "
            f"{'intact' if not readlock['snapshot_files_changed'] else 'CHANGED'}")
        revisions = readlock.get("closed_partition_content_revisions") or []
        restamps = readlock.get("closed_partition_vintage_restamps") or []
        if readlock.get("closed_partition_drift_classified"):
            add(f"- {len(revisions) + len(restamps)} closed partitions drifted by digest and were "
                f"READ to see what changed: **{len(revisions)} content revisions**, "
                f"**{len(restamps)} ingest re-stamps**")
            if restamps:
                products = sorted({r["product_id"] for r in restamps})
                add(f"  - the re-stamps are `{', '.join(products)}`; every measured column is "
                    "identical and only `ingested_at` moved, so the numbers this phase read are "
                    "the numbers upstream still holds. A digest says *different bytes*; only a "
                    "read says *different numbers*")
        for product, info in readlock["drift_by_product"].items():
            add(f"- **upstream drift**: `{product}` — {info['closed_partitions_changed']} closed "
                f"partitions {info['partition_range'][0]}..{info['partition_range'][1]}, symbols "
                f"{info['symbols']}, in primary core = **{info['in_primary_core']}**")
        add(f"- {readlock['primary_run_valid_rule']}")
    add("")

    if baseline is not None:
        cells = baseline.get("cells") or []
        run = [c for c in cells if c.get("status") == "RUN"]
        lines.extend(data_provenance_lines(LAB_ROOT, snapshot_id=baseline.get(
            "snapshot_id", "server_core_v1"), consumed={
            "symbols": sorted({c["symbol"] for c in run}) or ["none"],
            "products": ["crypto_binance_futures_1m"],
            "role": "development",
            "window": [baseline["calendar"]["first_cutoff"][:10],
                       "2023-12-31"] if baseline.get("calendar") else None,
            "notes": [
                f"**{baseline['cells_run']} of {baseline['cells_total']}** primary cells ran; "
                f"{baseline['cells_not_ready']} are NOT_READY with null metrics rather than a "
                "PnL of 0, which would bias every aggregate",
                f"alphas covered: {', '.join(sorted({c['alpha_id'] for c in run}))}",
                "arm A and arm B share one account contract, one calendar and one search budget; "
                "no arm reads any product the other does not",
            ],
        }))

    # ---- audit / coverage ----
    add("## Audit and acceptance coverage")
    add("")
    if audit:
        add(f"- clause audit: **{audit['tasks_done']}/{audit['tasks_total']}** DONE"
            + (f", blocked: {audit['tasks_blocked']}" if audit["tasks_blocked"] else ""))
        add(f"- acceptance tests: `{audit['acceptance_tests']}` "
            f"(passed = {audit['acceptance_tests_passed']})")
        add(f"- acceptance IDs covered by this phase: "
            f"{', '.join(audit['acceptance_ids_covered'])}")
        for row in audit["tasks"]:
            if row["status"] != "DONE":
                add(f"  - **{row['status']}** {row['task_id']} — {row['requirement']}")
    if coverage:
        add(f"- guide §14 coverage as of {coverage['as_of_phase']}: "
            f"`{json.dumps(coverage['counts'])}` of 64")
    add("")
    add("## Corrections made during LAB-04")
    add("")
    add("- **The probe design was not reproducible.** Per-anchor seeds came from `hash()` on a "
        "string and the active-parameter list came from set iteration, both salted per "
        "interpreter, so a \"frozen\" design produced a different probe set in every process. "
        "Seeds now derive from a SHA-256 digest and every set iteration is sorted; a test runs "
        "the design under three `PYTHONHASHSEED` values and requires identical probe ids.")
    add("- **The OOS mutation probe was invalid as first written.** With "
        "`window_mode=\"expanding\"`, a later fold trains on an earlier fold's test window, so "
        "mutating everything after one global date rewrote training data. Every earlier "
        "\"selection is in-sample only\" reading from that probe was unsupported. The probe now "
        "checks IS invariance on a fixed parameter point first and refuses to conclude otherwise, "
        "and it places the cut after the latest `train_end` across all folds.")
    add("- **Declared search bounds excluded the region the alphas operate in.** The first draft "
        "declared A-HMA `min_length` at 4..40 against preset evidence of 120..320, and A-VWAP "
        "`htf_ema_len` at 10..60 against 130..570. Measured on BTCUSDT over 2020-07..2021-01, "
        "A-VWAP's entry gate was then empty: the reversion trigger fired on 697 long and 1147 "
        "short bars and the HTF trend filter agreed on 0 and 1. Bounds now enclose each alpha's "
        "operating range; preset VALUES remain quarantined and are never candidates or anchors.")
    add("- **The LAB-03 qualification smoke reported zero engine fills** because it sized entries "
        "in raw units — one whole coin, about 35,000 USDT of BTC on 20,000 of capital — which the "
        "engine rejects for margin. The frozen account contract's 2,000 USDT entry notional is "
        "now wired through `unit_notional`, a parameter the bridge previously accepted and "
        "ignored.")
    add("- **A fixed-point loop over the whole window could not converge affordably.** It gained "
        "roughly one trade per pass at about 17 s per pass for A-HMA. Replaced with one "
        "chronological sweep that asks the engine about a single trade at a time (~10 ms), "
        "followed by one whole-window run whose protective exits must agree with what the adapter "
        "was driven with; disagreement is reported, not absorbed.")
    add("- **A-HMA's Hull kernel was 94% of evaluation cost.** A compiled twin was added and is "
        "admitted only while it is bit-exact against the interpreted reference; features were "
        "verified identical and `prepare()` went from 8.7 s to 0.18 s.")
    add("- **The read-lock was too coarse.** A closed-partition change in any product invalidated "
        "every run. Drift is now attributed per product and scored against what a run reads, so "
        "the measured metrics-product rewrite invalidates the G3 cohort without falsely "
        "invalidating a primary run that never reads it.")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines)")
    if baseline is None:
        print("NOTE: the calendar baseline artifact is absent; the report says so explicitly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
