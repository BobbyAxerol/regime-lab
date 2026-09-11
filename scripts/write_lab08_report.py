#!/usr/bin/env python
"""Render reports/lab08_report.md from committed artifacts only (CLAUDE.md rule 9)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"
OUT = LAB_ROOT / "reports" / "lab08_report.md"

from crypto_regime_lab.evidence import glossary as G  # noqa: E402
from crypto_regime_lab.evidence.data_sources import data_provenance_lines  # noqa: E402


def load(name):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def pct(value, digits=2):
    return "—" if value is None else f"{value:+.{digits}%}"


def main() -> int:
    protocol = load("lab08_pilot_protocol.json")
    factorial = load("lab08_factorial_full.json")
    discovery = load("lab08_discovery.json")
    ablation = load("lab08_data_ablation.json")
    audit = load("lab08_task_audit.json")
    coverage = load("acceptance_test_coverage.json")

    lines: list[str] = []
    add = lines.append
    add("# LAB-08 — Controlled discovery on four alphas × five symbols")
    add("")
    add("Generated from committed artifacts by `scripts/write_lab08_report.py`. Nothing is "
        "re-estimated here.")
    add("")
    lines.extend(G.render(G.BY_PHASE["LAB-08"]))
    add("")

    add("## What this phase claims and does not claim")
    add("")
    add("This is **discovery**. It measures what robustness, regime timing and bank switching "
        "contribute, with the controls that would explain each away, and it ends by freezing one "
        "design or declaring **NO_PROMISING_DESIGN**. Guide L08's exit is explicit that profit is "
        "not required to close discovery and that a negative result is not a technical failure to "
        "be re-run until it wins.")
    add("")
    add("The outer evaluation window is **not consulted anywhere in this phase**. Every number "
        "below comes from the development role.")
    add("")

    if protocol:
        add("## L08.1 — the protocol, frozen before any arm ran")
        add("")
        add(f"Frozen **{protocol['frozen_at_utc']}**. The freeze script refuses to overwrite an "
            "existing stamp, and a test compares it against every factorial run's own timestamp: "
            "a protocol that can be rewritten after a result is not frozen.")
        add("")
        matrix = protocol["primary_matrix"]
        add(f"- **{matrix['total']} cells** — {matrix['runnable']} runnable, "
            f"{matrix['not_runnable']} NOT_READY carrying null metrics")
        add(f"- contrasts registered in advance: `{', '.join(protocol['registered_contrasts'])}`")
        add(f"- controls: {', '.join(sorted(protocol['controls']))}")
        add(f"- seeds: `{json.dumps({k: v for k, v in protocol['seeds'].items() if k != 'rule'})}`")
        add(f"- stage **{protocol['stage']}**, outer window consumed: "
            f"**{not protocol['outer_window_is_not_consumed']}**")
        add("")

    if factorial:
        lines.extend(data_provenance_lines(LAB_ROOT, snapshot_id="server_core_v1", consumed={
            "symbols": sorted({c["symbol"] for c in factorial["cells"]
                               if c["status"] == "RUN"}) or ["none"],
            "products": ["crypto_binance_futures_1m"],
            "role": "development",
            "window": ["2021-01-01", "2023-12-31"],
            "notes": [
                f"**{factorial['cells_run']} of {factorial['cells_planned']}** cells ran; "
                f"{factorial['cells_not_ready']} are NOT_READY with null metrics and stay in the "
                "denominator",
                "each arm is ONE continuous account delivered through LAB-07's machinery, not a "
                "sum of independently evaluated folds",
                "regime states for all five symbols were fitted with LAB-05's own code, "
                "parameterised by symbol rather than reimplemented",
            ],
        }))

        add("## L08.2 — the factorial")
        add("")
        add("| alpha | symbol | A | B | C | D | E |")
        add("|---|---|---|---|---|---|---|")
        for cell in factorial["cells"]:
            arms = cell["arms"]
            if cell["status"] != "RUN":
                add(f"| {cell['alpha_id']} | {cell['symbol']} | "
                    + " | ".join([f"*{cell['status']}*"] * 5) + " |")
                continue
            add(f"| {cell['alpha_id']} | {cell['symbol']} | "
                + " | ".join(pct(arms[a].get("net_return")) for a in ("A", "B", "C", "D", "E"))
                + " |")
        add("")
        add(f"Wall time **{factorial['wall_seconds']:.0f}s**. A cell that is NOT_READY keeps null "
            "metrics — never a PnL of 0, which would bias every aggregate (guide 13.2).")
        add("")

    if discovery:
        add("## The registered contrasts")
        add("")
        add("| contrast | mean daily difference | cells | sign test | direction |")
        add("|---|---|---|---|---|")
        for name, record in discovery["contrast_panel"].items():
            mean = record["mean_daily_difference"]
            test = record["sign_test"]
            p = test["p_value"]
            add(f"| `{name}` | "
                f"{'—' if mean is None else f'{mean:+.6f}'} | "
                f"{record['cells_with_a_value']} | "
                f"{'—' if p is None else f'p={p:.4f}'} | "
                f"{test['positive']}+ / {test['negative']}− |")
        add("")
        selection = discovery["design_selection"]
        add(f"> {discovery['contrast_panel']['B-A']['sign_test']['reading']}")
        add("")
        interaction = selection.get("interaction") or {}
        if interaction.get("nominal_p") is not None:
            add(f"The interaction is the only contrast with a nominally significant sign test "
                f"(**p={interaction['nominal_p']:.4f}**) and it is **negative** "
                f"({interaction['mean_daily_difference']:+.3e}). After Holm adjustment over the "
                f"registered family it is **p={interaction['holm_adjusted_p']:.4f}** — not "
                f"significant, and that is the number that counts.")
            add("")
        arm_e = discovery.get("arm_e") or {}
        if arm_e.get("degenerate"):
            add(f"> **Arm E is not a fifth arm on this run.** It is identical to arm D in "
                f"{arm_e['cells_where_E_equals_D']}/{arm_e['cells_compared']} cells — "
                f"{arm_e['reason']} {arm_e['consequence']}")
            add("")

        label = discovery.get("legacy_arm_label") or {}
        if label:
            add("## The baseline is not an untouched baseline")
            add("")
            add(f"Arm A is the installed public route: `optimization_mode="
                f"'{label['public_route_mode']}'`, resolved by `{label['selector']}`, whose rule "
                f"is `{label['selection_rule']}`.")
            add("")
            add(f"LAB-04 read the engine's own walk-forward metadata and found that this mode "
                f"**declares OOS-adjusted selection**: `{label['mode_declares_oos_selection']}`. "
                f"Arm A therefore carries the label **`{label['label']}`** and "
                f"**may not be reported as an untouched baseline** "
                f"(`{label['may_be_reported_as_an_untouched_baseline']}`).")
            add("")
            add(f"> {label['consequence']}")
            add("")
            add(f"The label follows the declaration rather than a behavioural probe: "
                f"{label['probe_limit']}")
            add("")

        add("## L08.7 — the design decision")
        add("")
        add(f"**Outcome: `{selection['outcome']}`**"
            + (f" — `{selection['selected_contrast']}`" if selection["selected_contrast"] else ""))
        add("")
        add(f"The rule was fixed before any arm ran: {selection['decision_rule']}")
        add("")
        add(f"- registered endpoint: **{selection['registered_endpoint']}**")
        add(f"- minimum economic effect: **{selection['minimum_economic_effect_per_day']}/day**")
        add("")
        add("| contrast | mean daily | clears the minimum | Holm-adjusted p |")
        add("|---|---|---|---|")
        for candidate in selection["candidates"]:
            holm = candidate["holm_adjusted_p"]
            holm_text = "—" if holm is None else f"{holm:.4f}"
            add(f"| `{candidate['contrast']}` | {candidate['mean_daily_difference']:+.6f} | "
                f"**{candidate['clears_minimum_effect']}** | {holm_text} |")
        add("")
        for heading, key in (("Tradeoffs", "tradeoffs"), ("Failure cases", "failure_cases"),
                             ("Uncertainty", "uncertainty")):
            add(f"**{heading}**")
            add("")
            for item in selection[key]:
                add(f"- {item}")
            add("")
        add(f"> {selection['not_required_to_be_profitable']}")
        add("")

        controls = discovery.get("control_arms") or {}
        if controls.get("status") == "RUN":
            add("## L08.3 — the control that can sink the method, and does")
            add("")
            add("STATE_PLACEBO and DELAYED_STATE are run as **arms**, not as tapes. Generating a "
                "placebo and reporting its dwell statistics controls for nothing: the "
                "alternative explanation is about what an arm would have EARNED on that tape. "
                "Each control arm mirrors arm D exactly — same selector, same refresh count, "
                "same training memory — and only the tape differs.")
            add("")
            blocked = [c for c in (factorial or {}).get("cells", [])
                       if (c.get("controls") or {}).get("RISK_ONLY", {}).get("status")
                       == "BLOCKED_BY_STATE_NAMESPACING"]
            if blocked:
                record = (blocked[0]["controls"]["RISK_ONLY"])
                add("**RISK_ONLY is BLOCKED, not passing.** A per-state risk scale must be "
                    "fitted on one window and applied on a later one. The model refits every 28 "
                    f"days and LAB-05 declares cross-namespace state translation diagnostic only, "
                    f"so only **{record['share_of_scoring_states_seen_in_calibration']:.2%}** of "
                    f"scoring observations carry a state key seen during calibration "
                    f"({record['state_keys_seen_in_calibration']} of "
                    f"{record['distinct_state_keys']} keys). The rest would fall back to a scale "
                    "of 1.0 and the control would return the baseline path while printing a "
                    f"number. Blocked on **{len(blocked)}** cells. {record['not_dropped']}")
                add("")
            add("| cell | control | arm D | control arm | difference |")
            add("|---|---|---|---|---|")
            for row in controls["rows"]:
                add(f"| {row['alpha_id']}/{row['symbol']} | `{row['control']}` | "
                    f"{row['arm_D_net_return']:+.2%} | {row['control_net_return']:+.2%} | "
                    f"**{row['difference']:+.2%}** |")
            add("")
            add(f"**The placebo matched or beat arm D in "
                f"{controls['placebo_matched_or_beat_arm_D_in']} of "
                f"{controls['placebo_cells']} staged cells**, and a one-observation delay left "
                f"arm D unchanged in {controls['delayed_state_left_arm_D_unchanged_in']} of "
                f"{controls['delayed_cells']}.")
            add("")
            add(f"> {controls['reading']}")
            add("")
            add(f"{controls['not_dropped_for_winning']}")
            add("")
            add(f"Staged over {controls['staged_over_cells']} of "
                f"{controls['of_runnable_cells']} runnable cells, the subset fixed by cell order "
                "before any result was read (guide 10.2 permits a staged design).")
            add("")

        compute = discovery["compute"]
        add("## L08.6 — what the phase actually cost")
        add("")
        add("| | |")
        add("|---|---|")
        add(f"| dynamic refreshes | {compute['dynamic_refreshes']} |")
        add(f"| unique strategy executions in those refreshes | "
            f"{compute['unique_strategy_executions_in_dynamic_refreshes']:,} |")
        add(f"| wall seconds, total | {compute['total_wall_seconds']:.0f} |")
        add(f"| wall seconds per cell (min / median / max) | "
            f"{compute['wall_seconds_per_cell']['min']:.0f} / "
            f"{compute['wall_seconds_per_cell']['median']:.0f} / "
            f"{compute['wall_seconds_per_cell']['max']:.0f} |")
        add(f"| resource budget exceeded | **{compute['budget_exceeded']}** |")
        add("")
        add(f"{compute['match_note']}")
        add("")
        units = compute.get("counted_units") or {}
        if units:
            add("### Every unit the budget registration declares")
            add("")
            add("An earlier version of this table reported ONE of the registered units, for the "
                "dynamic half only, and called the result `MATCHED_TOTAL_COMPUTE`. A budget "
                "report that does not count four of its own declared units cannot say whether "
                "the arms were given the same total.")
            add("")
            add("| unit | calendar arms A, B | dynamic arms C, D, E |")
            add("|---|---|---|")
            left = units["per_arm_family"]["calendar_arms_A_and_B"]
            right = units["per_arm_family"]["dynamic_arms_C_D_E"]
            for label, key in (("cutoffs", "cutoffs"),
                               ("unique strategy evaluations", "unique_strategy_evaluations"),
                               ("fold-bar visits", "fold_bar_visits"),
                               ("independent local probes", "independent_local_probes")):
                add(f"| {label} | {left[key]:,} | {right[key]:,} |")
            fits = units["regime_model_fits"]
            add(f"| regime model fits, multi-start included | — | "
                f"{fits['total_multi_start_fits']:,} "
                f"({fits['total_refits']} refits × seeds) |")
            response = units["response_evaluations"]
            add(f"| response evaluations | — | {response['count']:,} "
                f"({response['scope']}) |")
            add("")
            matched = units["matched"]
            add(f"Cutoff counts equal: **{matched['cutoffs_equal']}**. Search-effort ratio "
                f"**{matched['evaluations_ratio']:.4f}** — compute-matching measured rather than "
                "asserted by construction.")
            add("")
        latency_block = compute.get("latency") or {}
        if latency_block:
            refit = latency_block["refit_latency_seconds"]
            activation = latency_block["activation_delay_bars"]
            add(f"Refit latency **{refit['min']:.3f} s** measured "
                f"(`{refit['source']}`), zero-latency jobs **{refit['zero_latency_jobs']}**. "
                f"Activation delays actually paid, in bars: "
                f"`{activation['per_switch']}` (max {activation['max']}). "
                f"Cold/warm runtime: **{latency_block['cold_vs_warm_runtime']['status']}** — "
                f"{latency_block['cold_vs_warm_runtime']['why']}")
            add("")
        latency = compute.get("refit_latency") or {}
        if latency:
            add(f"A refit costs **{latency['measured_seconds_per_fit']:.3f} s/fit** measured, and "
                f"the coarsest decision bar here is an hour, so the compute latency rounds to "
                f"**zero bars**: `{latency['refit_latency_rounds_to_zero_bars']}`. "
                f"{latency['why_that_is_not_a_free_option']}")
            add("")
            add(f"The delays the arms DO pay are measured in bars: {latency['delays_the_arms_do_pay']}.")
            add("")

    arm_e = (discovery or {}).get("arm_e") or {}
    if arm_e.get("versus_BANK_CALENDAR"):
        add("## Guide 10.1 — arm E against B, and against the matched-bank control")
        add("")
        add(f"E equals D on **{arm_e['cells_where_E_equals_D']} of "
            f"{arm_e['cells_compared']}** cells, so it is not a fifth arm here. "
            f"{arm_e['reason']}")
        add("")
        add("| comparison | status | why |")
        add("|---|---|---|")
        add(f"| `E-B` | {arm_e['versus_B']['status']} | equals `D-B`, shown because guide 10.1 "
            f"asks for it, excluded from the Holm family |")
        bank = arm_e["versus_BANK_CALENDAR"]
        add(f"| E vs `BANK_CALENDAR` | {bank['comparison']} (control: "
            f"{bank['control_status']}) | {bank['why']} |")
        add("")
        add(f"What would make the second one informative: {bank['what_would_make_it_informative']}")
        add("")

    common = (discovery or {}).get("common_period")
    if common:
        add("## Guide 10.4 — is the five-symbol number a common-period aggregate?")
        add("")
        add(f"Phase window **{common['phase_window'][0]} → {common['phase_window'][1]}**. "
            f"Every symbol's usable interval covers the whole window: "
            f"**{common['every_symbol_covers_the_whole_window']}**, so the common-period "
            f"aggregate and the longest-history aggregate are the same number. "
            f"{common['zeros_before_listing']}")
        add("")
        add("| symbol | usable interval |")
        add("|---|---|")
        for symbol, interval in common["per_symbol_usable_interval"].items():
            add(f"| {symbol} | {interval[0][:10]} → {interval[1][:10]} |" if interval
                else f"| {symbol} | — |")
        add("")
        add(f"_{common['statistic_name']}_")
        add("")

    if ablation:
        add("## L08.4 — the data-cohort ablation")
        add("")
        add("Every cohort is scored on the **same rows**. Scoring each on its own longest window "
            "would credit a feature group for the period it happens to cover.")
        add("")
        add("| symbol | cohort | variance resolved out of fold | gain over core | rows |")
        add("|---|---|---|---|---|")
        for entry in ablation["per_symbol"]:
            for cohort, values in (entry.get("scores") or {}).items():
                gain = entry["gain_over_core"][cohort]
                add(f"| {entry['symbol']} | `{cohort}` | "
                    f"{values['variance_resolved_out_of_fold']:+.5f} | {gain:+.5f} | "
                    f"{values['interval_rows']} |")
        add("")
        add(f"**Any cohort beats the core: {ablation['any_cohort_beats_core']}.**")
        add("")
        add("Two cohorts are structurally unavailable and are reported as such rather than "
            "substituted:")
        add("")
        add("- **`server_liquidity_book`** — the spread is the only order-book feature, and that "
            "product is a rolling 30-day window that by design cannot accumulate history (LAB-03). "
            "It has 127 usable rows on BTCUSDT and zero everywhere else.")
        add("- **`server_derivatives`** with basis is BTCUSDT-only, because basis needs a spot "
            "leg and spot was only ever collected for BTCUSDT. The open-interest half is scored "
            "separately as `server_derivatives_oi_only` so ETHUSDT's 10,399 rows are not "
            "discarded by one missing product.")
        add("")

        add("## L08.5 — the complexity ladder")
        add("")
        add("| rung | question | expected failure | stop condition |")
        add("|---|---|---|---|")
        for rung in ablation["complexity_ladder"]:
            add(f"| **{rung['rung']}** | {rung['question']} | {rung['expected_failure']} | "
                f"{rung['stop_condition']} |")
        add("")
        add(f"Implemented: `{ablation['ladder_implemented']}`. Declared deliberately unbuilt: "
            f"`{ablation['ladder_declared_unbuilt']}`. {ablation['tuning_stage']}.")
        add("")

    add("## Audit and acceptance coverage")
    add("")
    if audit:
        add(f"- **{audit['tasks_done']}/{audit['tasks_total']}** checklist clauses DONE, driven "
            f"by `{audit['checklist_source']}` written BEFORE any factorial code "
            f"(`checklist_written_before_code: {audit['checklist_written_before_code']}`)")
        add(f"- clauses with no evidence pointer: "
            f"**{audit['clauses_without_an_evidence_pointer'] or 'none'}**")
        add(f"- acceptance tests: **{audit['acceptance_tests']}**")
        add("")
    if coverage:
        counts = coverage["counts"]
        add(f"Guide §14 coverage as of {coverage['as_of_phase']}: **{counts['COVERED']} COVERED, "
            f"{counts.get('PARTIAL', 0)} PARTIAL, "
            f"{counts.get('NOT_YET_IMPLEMENTED', 0)} NOT_YET_IMPLEMENTED** of 64.")
        add("")

    add("## Corrections made during LAB-08")
    add("")
    add("The pilot exists to be thrown away, and it earned its keep: **two defects, both of "
        "which would have produced a timing result that was really a coverage artefact.**")
    add("")
    add("1. **The state tape covered a sixth of the window.** LAB-05 persisted 1,099 emissions "
        "from one namespace while summarising 6,571 across forty. Reading whichever "
        "per-namespace file was last on disk gave the dynamic arms states for 2023-07 onward "
        "only, so **every** refresh landed in the last six months while the calendar arms "
        "refreshed across three years. The fitter now writes the full tape, the fallback is "
        "gone, and a cell whose tape does not span its window has no dynamic arm.")
    add("2. **The dynamic training windows were a fifth of the calendar's** — 868 bars against "
        "4,320. The selector's frame started where the account started, but the calendar arm's "
        "first fold trains from 180 days *before* that. A selector with a fifth of the history is "
        "not the same selector, so the comparison was not measuring timing. The selector now gets "
        "a frame reaching one training memory back, and every dynamic cutoff trains on 4,320 "
        "bars exactly as the calendar does.")
    add("")
    add("3. **A cell where the selector never selected crashed the run.** Arm B's quality gate "
        "rejected every candidate at all six cutoffs on A-SC/BNBUSDT — `ALL_FAIL_ECONOMIC_"
        "QUALITY` six times — and the schedule builder raised rather than deploying the retained "
        "incumbent. That took nine completed cells down with it, about two hours. A selector that "
        "declines is a **result**: the arm now holds the incumbent seed and carries "
        "`selector_never_selected: true`. The run also checkpoints each cell, so a crash costs "
        "one cell instead of everything before it.")
    add("")
    add("Two more were found while building, before any result existed:")
    add("")
    add("4. **The trigger rule concentrated every refresh at the front.** Taking the first six "
        "transitions with a 30-day gap put all of them in the opening months — the mirror image "
        "of defect 1. Triggers are now taken one per period, so the cadence matches the calendar "
        "and only the timing within each period is the model's choice. A period with no "
        "transition refuses rather than padding: a refresh the states did not ask for is just "
        "the calendar wearing a different label.")
    add("5. **The liquidity cohort scored an impact proxy and called it the order book.** "
        "`g4_log_amihud_30` comes from the perpetual bars and exists for every symbol; "
        "`g4_spread_bps` is the only order-book feature and has 127 rows on BTCUSDT and zero "
        "elsewhere. Matching on the `g4` prefix merged them, so the cohort the guide asks about "
        "was never actually tested. They are now separate cohorts.")
    add("")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
