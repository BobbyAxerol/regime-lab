#!/usr/bin/env python
"""Render reports/lab09_report.md from committed artifacts only (CLAUDE.md rule 9)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"
OUT = LAB_ROOT / "reports" / "lab09_report.md"

from crypto_regime_lab.evidence import glossary as G  # noqa: E402
from crypto_regime_lab.evidence.data_sources import data_provenance_lines  # noqa: E402


def load(name):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def pct(value, digits=2):
    return "—" if value is None else f"{value:+.{digits}%}"


def sci(value, digits=3):
    return "—" if value is None else f"{value:+.{digits}e}"


def main() -> int:
    unlock = load("lab09_confirmation_spec.json")
    results = load("lab09_confirmation_results.json")
    uncertainty = load("lab09_uncertainty.json")
    stress = load("lab09_stress.json")
    support = load("lab09_support.json")
    reconciliation = load("lab09_reconciliation.json")
    claim = load("lab09_claim_report.json")
    limits = load("lab09_limitations.json")
    leakage = load("lab09_leakage_contamination.json")
    binding = load("cost_binding_verification.json")
    replay = load("lab09_development_replay.json")
    ablation = load("lab09_group_ablation.json")
    registry = load("hypothesis_registry.json")
    effect = load("minimum_economic_effect.json")
    audit = load("lab09_task_audit.json")
    coverage = load("acceptance_test_coverage.json")
    ledger = load("correction_ledger.json")

    lines: list[str] = []
    add = lines.append
    add("# LAB-09 — Frozen confirmation, robustness and falsification")
    add("")
    add("Generated from committed artifacts by `scripts/write_lab09_report.py`. Nothing is "
        "re-estimated here.")
    add("")
    lines.extend(G.render(G.BY_PHASE["LAB-09"]))
    add("")

    add("## What this phase claims and does not claim")
    add("")
    add("LAB-08 closed with **NO_PROMISING_DESIGN**. That does not suspend this phase: a negative "
        "finding has to be confirmed exactly as a positive one would be, and the guide's exit "
        "asks for an honest conclusion with a scope rather than for an edge. A **frozen "
        "confirmation** is the LAB-08 protocol, unchanged, run on an interval the design was not "
        "built on.")
    add("")
    add("What it cannot claim is out-of-sample. The interval is **nested retrospective**: no "
        "phase of this lab consumed it, and the supplied presets were still tuned over the whole "
        "sample with an unknown cutoff. Both facts are stated because only the first one is "
        "about this lab.")
    add("")

    # ---------------------------------------------------------------- L09.1
    if unlock:
        add("## L09.1 — the interval, and what it is not")
        add("")
        interval = unlock["interval"]
        add(f"Unlocked **{unlock['unlocked_at_utc']}**, after the protocol was frozen "
            f"({unlock['frozen_protocol']['frozen_at_utc']}) and before any confirmation run "
            "started. The file is never re-issued: re-unlocking would let the protocol be "
            "revised once a result was visible.")
        add("")
        add(f"- interval **{interval['start']} → {interval['end']}**, all five symbols")
        add(f"- consumed by an earlier phase: "
            f"**{unlock['prior_access_audit']['any_phase_read_the_outer_window']}**")
        add(f"- holdout status: **{unlock['holdout_status']}**")
        add(f"- **prospective protocol**: {unlock['prospective_protocol']['status']} — "
            f"{unlock['prospective_protocol']['why']}")
        add("")
        add("| artifact checked | declared window | inside development |")
        add("|---|---|---|")
        for row in unlock["prior_access_audit"]["checked"]:
            declared = row.get("declared")
            declared = (f"{declared[0][:10]} → {declared[1][:10]}"
                        if isinstance(declared, list) and len(declared) == 2
                        else str(declared)[:60])
            add(f"| `{row['artifact']}` | {declared} | {row.get('inside_development')} |")
        add("")

    # ---------------------------------------------------------------- L09.2
    if results:
        add("## L09.2 — the frozen protocol, run")
        add("")
        add(f"Window **{results['window'][0]} → {results['window'][1]}**. "
            f"{results['cells_run']} of {results['cells_planned']} cells ran; "
            f"{results['cells_not_ready']} carry null metrics. "
            f"Wall time {results['wall_seconds']:.0f}s.")
        add("")
        add(f"- the calendar moved by exactly one field: "
            f"`{results['calendar_spec']['changed_from_development']}` "
            f"({results['calendar_spec']['how']})")
        add(f"- seeds carried from the frozen protocol: "
            f"`{json.dumps({k: v for k, v in results['seeds'].items() if k != 'rule'})}`")
        add(f"- no module changed while the run was in flight: "
            f"**{results['no_human_adjustment']['unchanged_during_run']}** "
            f"({results['no_human_adjustment']['modules_hashed']} modules hashed before the "
            "first cell and after the last)")
        add(f"- {results['window_note']}")
        add("")
        add("| alpha | symbol | A | B | C | D | E |")
        add("|---|---|---|---|---|---|---|")
        for cell in results["cells"]:
            arms = cell.get("arms") or {}
            if cell["status"] != "RUN":
                add(f"| {cell['alpha_id']} | {cell['symbol']} | "
                    + " | ".join([f"_{cell['status']}_"] * 5) + " |")
                continue
            values = []
            for arm in ("A", "B", "C", "D", "E"):
                record = arms.get(arm) or {}
                values.append(pct(record.get("net_return")) if record.get("net_return") is not None
                              else f"_{record.get('status', '—')}_")
            add(f"| {cell['alpha_id']} | {cell['symbol']} | " + " | ".join(values) + " |")
        add("")

    # ---------------------------------------------------------------- L09.3
    if uncertainty and registry and effect:
        add("## L09.3 — the registered endpoint, with an interval around it")
        add("")
        minimum = effect["minimum_daily_net_return_difference"]
        add(f"The **registered primary endpoint** is the mean **paired daily difference** in net "
            f"return between two arms on the same dates, registered "
            f"{registry['registered_at_utc']}. The **minimum economic effect** is "
            f"`{minimum:.2e}` per day ({effect['minimum_daily_net_return_bps']} bps), fixed "
            f"{effect['registered_at_utc']} before any arm was compared.")
        add("")
        add(f"The interval is a **block bootstrap** with blocks of "
            f"**{uncertainty['block_length_days']} days**, chosen on development "
            f"(`{uncertainty['block_length_source']}`) and applied here unchanged. "
            f"{uncertainty['draws']} draws. {uncertainty['resampling']}")
        add("")
        add("| id | contrast | question | mean daily | 95% CI | p | Holm p | clears minimum |")
        add("|---|---|---|---|---|---|---|---|")
        by_contrast = {h["contrast"]: h for h in registry["primary_contrasts"]}
        for name in [*results["registered_contrasts"], "E-B"]:
            record = uncertainty["contrasts"].get(name, {})
            hypothesis = by_contrast.get(name, {})
            if record.get("status") != "OK":
                add(f"| {hypothesis.get('id', '—')} | `{name}` | "
                    f"{hypothesis.get('question', 'extension contrast')} | "
                    f"_{record.get('status', 'missing')}_ | — | — | — | — |")
                continue
            holm = record.get("holm_adjusted_p")
            add(f"| {hypothesis.get('id', '—')} | `{name}` | "
                f"{hypothesis.get('question', 'extension: does arm E beat arm B?')} | "
                f"{sci(record['point_estimate'])} | "
                f"[{sci(record['ci_lower'])}, {sci(record['ci_upper'])}] | "
                f"{record['p_value']:.3f} | "
                f"{'—' if holm is None else f'{holm:.3f}'} | "
                f"**{record['clears_minimum_effect']}** |")
        add("")
        add(f"Holm step-down over the registered family `{uncertainty['holm']['family']}`. "
            f"{uncertainty['holm']['exclusion_reason']}")
        add("")
        add("### Episode counts and concentration")
        add("")
        add("| contrast | union days | days all cells live | min cell | max cell | "
            "top-5-day share of absolute | days for half the move |")
        add("|---|---|---|---|---|---|---|")
        for name in results["registered_contrasts"]:
            record = uncertainty["contrasts"].get(name, {})
            if record.get("status") != "OK":
                continue
            episodes, focus = record["episodes"], record["concentration"]
            add(f"| `{name}` | {episodes['union_days']} | {episodes['days_all_cells_live']} | "
                f"{episodes['min_cell_days']} | {episodes['max_cell_days']} | "
                f"{focus['top_5_day_share_of_absolute']:.1%} | "
                f"{focus['days_for_half_the_absolute_move']} |")
        add("")
        add("### Block-length sensitivity")
        add("")
        first = next((r for r in (uncertainty["contrasts"].get(n, {})
                                  for n in results["registered_contrasts"])
                      if r.get("status") == "OK"), None)
        if first:
            add(f"For `{first['cells']}` pooled cells on the first registered contrast:")
            add("")
            add("| block length (days) | mean daily | 95% CI | p | CI excludes zero |")
            add("|---|---|---|---|---|")
            for row in first["block_length_sensitivity"]:
                if row["status"] != "OK":
                    add(f"| {row['block_length_days']} | _{row['status']}_ | — | — | — |")
                    continue
                add(f"| {row['block_length_days']} | {sci(row['point_estimate'])} | "
                    f"[{sci(row['ci_lower'])}, {sci(row['ci_upper'])}] | "
                    f"{row['p_value']:.3f} | {row['ci_excludes_zero']} |")
            add("")

    # ---------------------------------------------------------------- L09.4
    if stress:
        add("## L09.4 — cost and information stress")
        add("")
        cost = stress["cost_stress"]
        add(f"Multipliers `{cost['multipliers']}` were registered in "
            f"`{cost['registered_in']}` on {cost['registered_at_utc']}. "
            f"The **1x** level is a control on the harness itself: it must reproduce the "
            f"confirmation run's equity exactly, and it does for every arm: "
            f"**{cost['harness_control']['one_x_reproduces_every_arm']}**.")
        add("")
        add(f"**AS_DECLARED** is not a stress. {cost['as_declared']['what_it_is']}")
        add("")
        add("| level | fee ×| slip ×| A | B | C | D | E |")
        add("|---|---|---|---|---|---|---|---|")
        by_name = {level["name"]: level for level in cost["levels"]}
        for name, per_arm in cost["pooled"].items():
            level = by_name.get(name, {})
            values = [pct(per_arm[a]["mean_net_return"]) for a in ("A", "B", "C", "D", "E")]
            add(f"| `{name}` | {level.get('fee_multiplier')} | "
                f"{level.get('slippage_multiplier')} | " + " | ".join(values) + " |")
        add("")
        add(f"_{cost['limitation']}_")
        add("")
        info = stress["information_stress"]
        add(f"### Information stress — {info['cells_covered']} of {info['cells_total_run']} "
            "cells")
        add("")
        add(f"{info['staging_rule']}. Settings registered before the stress ran: "
            f"`{json.dumps({k: v for k, v in info['settings'].items() if k != 'seeds'})}`.")
        add("")
        add("| cell | stress | arm D | stressed | difference | cutoffs moved |")
        add("|---|---|---|---|---|---|")
        for entry in info["per_cell"]:
            for name, record in entry["stresses"].items():
                cell = f"{entry['alpha_id']}/{entry['symbol']}"
                if record["status"] == "RUN":
                    add(f"| {cell} | {name} | {pct(entry['arm_D_net_return'])} | "
                        f"{pct(record['net_return'])} | {pct(record['difference_vs_arm_D'])} | "
                        f"{record['cutoffs_moved_vs_arm_D']}/6 |")
                elif record["status"] == "CONTROL":
                    add(f"| {cell} | {name} _(control)_ | — | — | schedule identical: "
                        f"**{record['schedule_identical_to_arm_D']}** | 0/6 |")
                else:
                    add(f"| {cell} | {name} | — | _{record['status']}_ | — | — |")
        add("")

    # ---------------------------------------------------------------- L09.5
    if support:
        add("## L09.5 — support and novelty")
        add("")
        add("| situation | exercised | measured |")
        add("|---|---|---|")
        novelty = support["situations"]["NEW_REGIME_EPISODE"]
        add(f"| new regime episode | **{novelty['a_new_episode_was_exercised']}** | "
            f"{novelty['symbols_with_more_novelty_than_development']} of "
            f"{novelty['symbols_measured']} symbols carry more novel states than development |")
        ambiguity = support["situations"]["MIXED_AMBIGUOUS_STATES"]
        add(f"| mixed / ambiguous states | **{ambiguity['symbols_measured'] > 0}** | "
            f"{ambiguity['symbols_more_ambiguous_than_development']} of "
            f"{ambiguity['symbols_measured']} symbols more ambiguous than development, by each "
            "symbol's own development **second-best gap** decile |")
        permutation = support["situations"]["STATE_LABEL_PERMUTATION_AFTER_REFIT"]
        add(f"| **label permutation** after refit | **{permutation['status']}** | "
            f"schedule identical on {permutation.get('schedules_identical')} of "
            f"{permutation.get('cells_checked')} cells |")
        policy = support["situations"]["POLICY_ON_THE_CONFIRMATION_INTERVAL"]
        if policy.get("status") == "NOT_RUN":
            add(f"| stale bank / no challenger | _NOT_RUN_ | {policy['reason']} |")
        else:
            bank = policy["bank"]["staleness_at_interval_end"] or {}
            add(f"| stale candidate bank | **{bank.get('older_than_the_registered_comparator_cadence')}** | "
                f"last bank cutoff {bank.get('last_bank_cutoff', '—')}, "
                f"{bank.get('age_at_interval_end_days', '—')} days old at the interval end |")
            add(f"| no challenger qualifies | "
                f"**{policy['no_challenger_qualified']['exercised']}** | "
                f"{policy['no_challenger_qualified']['occurrences']} of {policy['decisions']} "
                "decisions |")
        campaign = support["situations"]["CAMPAIGN_NOT_FLAT"]
        add(f"| campaign not flat at a switch | "
            f"**{campaign['a_switch_waited_for_an_open_campaign']}** | "
            f"{campaign['arms_with_a_delayed_switch']} arms had a delayed switch; reasons "
            f"`{json.dumps(campaign['blocked_reasons_across_every_arm'])}` |")
        add("")
        attribution = support["time_edge_attribution"]
        add(f"**Time-edge attribution.** {attribution['reading']} Pooled over the cells: "
            f"timing `C-A` = {sci(attribution['timing_contribution'])}, "
            f"selection `B-A` = {sci(attribution['selection_contribution'])}, "
            f"interaction = {sci(attribution['interaction'])}.")
        add("")
    if ablation:
        add(f"**Descriptive contribution.** The guide 8.3 group ablation, re-measured on a "
            f"window inside the interval ({ablation['window_rule']}): a block beyond price and "
            f"volatility improved out-of-fold variance resolved on "
            f"**{ablation['symbols_where_a_block_improved_out_of_fold']} of "
            f"{ablation['symbols_measured']}** symbols. {ablation['finding']}")
        add("")

    # ---------------------------------------------------------------- L09.6
    if reconciliation:
        add("## L09.6 — reconciliation, and one accounting defect")
        add("")
        financial = reconciliation["financial_identity"]
        add("| check | result |")
        add("|---|---|")
        add(f"| **cash identity** `{financial['identity']}` | "
            f"{financial['arms_holding']}/{financial['arms_checked']} arms hold, worst residual "
            f"{financial['worst_absolute_residual']:.2e} |")
        lifecycle = reconciliation["parameter_version_lifecycle"]
        add(f"| **parameter-version lifecycle** | every bar attributed: "
            f"**{lifecycle['every_bar_attributed']}**; "
            f"{lifecycle['versions_requested_total']} requested, "
            f"{lifecycle['versions_deployed_total']} deployed, "
            f"{lifecycle['requested_but_never_deployed']} gated |")
        cardinality = reconciliation["search_cardinality"]
        add(f"| **search cardinality** | {cardinality['cutoffs_checked']} cutoffs, every "
            f"execution recorded: **{cardinality['all_executions_recorded']}**, unique "
            f"executions {cardinality['unique_executions_range']} against a ceiling of "
            f"{cardinality['nominal_total']} |")
        objective = reconciliation["objective_recomputation"]
        add(f"| **objective recomputation** `{objective['formula']}` | "
            f"{objective['scores_checked']} scores, all match: **{objective['all_match']}** "
            f"(max difference {objective['max_difference']:.2e}) |")
        replay_record = reconciliation["replay"]
        add(f"| **replay** | development: "
            f"{replay_record['development']['arms_matching']}/"
            f"{replay_record['development']['arms_replayed']} exact; confirmation 1x: "
            f"{(replay_record['confirmation'] or {}).get('arms_reproduced')}/"
            f"{(replay_record['confirmation'] or {}).get('arms')} |")
        audits = reconciliation["audits_retained"]
        add(f"| **audits retained** | all present: **{audits['all_present']}**, fast profile "
            f"used: {audits['fast_profile_used']} |")
        add("")
    if binding and not binding["verdict"]["binding_charges_the_registered_rate"]:
        add("### The fee binding — a measured accounting defect")
        add("")
        add(f"The study registered a **one-way fee** of "
            f"`{binding['registered']['one_way_taker_fee_rate']}` "
            f"({binding['registered']['provenance']}). Measured from real fills, the account was "
            f"charged `{binding['measurement']['measured_one_way_fee_rate']}` — "
            f"**{binding['verdict']['measured_over_registered']:.1f}×** the registered rate.")
        add("")
        add(f"{binding['lab_binding']['engine_semantic']}. The correct binding is "
            f"`{binding['lab_binding']['correct_binding_would_be']}`.")
        add("")
        add(f"**Why it was not caught earlier.** {binding['verdict']['why_it_was_not_caught_earlier']}")
        add("")
        add(f"**Direction.** {binding['verdict']['direction']}")
        add("")
        if replay and replay.get("as_declared_economics"):
            declared = replay["as_declared_economics"]
            add("Development contrasts recomputed at the registered fee "
                "(deployment only — the selections cannot be corrected without re-running the "
                "search):")
            add("")
            add("| contrast | at the fee that ran | at the registered fee |")
            add("|---|---|---|")
            discovery = load("lab08_discovery.json") or {}
            panel = discovery.get("contrast_panel", {})
            for name, entry in declared["pooled_contrasts"].items():
                ran = (panel.get(name) or {}).get("mean_daily_difference")
                add(f"| `{name}` | {sci(ran)} | {sci(entry['mean_daily_difference'])} |")
            add("")
            add(f"_{declared['what_it_cannot_correct']}_")
            add("")

    # ---------------------------------------------------------------- L09.7
    if claim:
        add("## L09.7 — the claim")
        add("")
        add(f"{claim['why_separately']}")
        add("")
        add("| contribution | question | verdict | evidence |")
        add("|---|---|---|---|")
        for name, entry in claim["contributions"].items():
            evidence = entry.get("where") or entry.get("evidence") or "—"
            detail = ""
            if entry.get("ci"):
                detail = (f" — {sci(entry['point_estimate'])}, "
                          f"CI [{sci(entry['ci'][0])}, {sci(entry['ci'][1])}]")
            add(f"| **{name}** | {entry['question']} | **{entry['verdict']}**{detail} | "
                f"`{evidence}` |")
        add("")
        add(f"### Conclusion level: **{claim['conclusion_level']}**")
        add("")
        add(f"Drawn from the registered vocabulary in `{claim['vocabulary_source']}`: "
            f"`{', '.join(claim['conclusion_vocabulary'])}`.")
        add("")
        if claim["blockers"]:
            add("Blockers that prevented a stronger conclusion:")
            add("")
            for blocker in claim["blockers"]:
                add(f"- {blocker}")
            add("")
        add(f"**Development outcome being confirmed:** `{claim['development_outcome']}`. "
            f"Confirmed: **{claim['confirms_the_development_outcome']}**.")
        add("")
        add(f"**{claim['forbidden']['statement']}**")
        add("")
        add(f"**Scope.** {claim['scope']['statement']}")
        add("")

    # ---------------------------------------------------------------- falsification
    if registry:
        add("## Falsification commitments exercised")
        add("")
        add("| commitment | exercised in this phase |")
        add("|---|---|")
        exercised = {
            "a negative or inconclusive result is a valid outcome and is published, not rerun "
            "until it wins":
                "the confirmation reproduces NO_PROMISING_DESIGN and is published as it came out",
            "risk-only improvement is never recorded as a parameter-selection edge":
                "RISK_ONLY is reported BLOCKED_BY_STATE_NAMESPACING with its measurement, never "
                "as a scale of 1.0",
            "zero switches because no challenger qualified is a valid technical pass":
                "the policy's decision counts on the confirmation interval are reported as a "
                "result",
            "an alpha that cannot be certified is reported NOT_READY with null metrics, never "
            "PnL=0":
                "A-HASH contributes five NOT_READY cells with null metrics",
        }
        for commitment in registry["falsification_commitments"]:
            add(f"| {commitment} | {exercised.get(commitment, '—')} |")
        add("")

    # ---------------------------------------------------------------- corrections
    add("## Corrections made during LAB-09")
    add("")
    if ledger:
        rows = [c for c in ledger.get("defects", []) if c.get("phase") == "LAB-09"]
        if rows:
            add("| id | what was wrong | what it invalidated | guarded by |")
            add("|---|---|---|---|")
            for row in rows:
                add(f"| {row['id']} | {row['defect']} | {row['invalidated']} | "
                    f"`{row['guarded_by'].split('::')[-1]}` |")
            add("")
            add(f"All {ledger['defects_total']} corrections across every phase are traceable: "
                f"`{ledger.get('rule', '')[:160]}`")
        else:
            add("`configs/correction_ledger.json` carries no LAB-09 row yet; run "
                "`scripts/build_correction_ledger.py`.")
    else:
        add("`configs/correction_ledger.json` is missing.")
    add("")

    # ---------------------------------------------------------------- limitations
    if limits:
        add("## Limitations")
        add("")
        add("| id | limitation | consequence | measured in |")
        add("|---|---|---|---|")
        for row in limits["limitations"]:
            add(f"| {row['id']} | {row['limitation']} | {row['consequence']} | "
                f"`{row['where']}` |")
        add("")
    if leakage:
        add("## Leakage and contamination")
        add("")
        add("| id | finding | severity | measured |")
        add("|---|---|---|---|")
        for finding in leakage["findings"]:
            add(f"| {finding['id']} | {finding['title']} | **{finding['severity']}** | "
                f"`{json.dumps(finding['measured'])}` |")
        add("")

    # ---------------------------------------------------------------- provenance
    if results:
        lines.extend(data_provenance_lines(LAB_ROOT, snapshot_id="server_core_v1", consumed={
            "symbols": sorted({c["symbol"] for c in results["cells"]
                               if c["status"] == "RUN"}) or ["none"],
            "products": ["crypto_binance_futures_1m"],
            "role": "outer_evaluation",
            "window": list(results["window"]),
            "notes": [
                f"**{results['cells_run']} of {results['cells_planned']}** cells ran; "
                f"{results['cells_not_ready']} are NOT_READY with null metrics and stay in the "
                "denominator",
                "the state provider for this interval was fitted by LAB-05's own fitter with the "
                "registered K, lambda, seeds, training memory and refit cadence, parameterised by "
                "role rather than reimplemented",
                "the first model of the interval trains on the 365 days before it, which are "
                "development data. That is what a deployment does on its first day and is "
                "backward-looking; it is recorded as LEAK-04, BY_DESIGN",
                "the account stops at the end of the 4h feature panel, which is the state "
                "provider's input, rather than at the end of the 1-minute product",
            ],
        }))
        add("")

    add("## Audit and acceptance coverage")
    add("")
    if audit:
        add(f"- clause audit: **{audit['tasks_done']}/{audit['tasks_total']} DONE**, from a "
            f"checklist written before the code (`{audit['checklist_source']}`)")
        add(f"- every evidence pointer is RESOLVED, not merely present: "
            f"{audit['resolution_rule']}")
        if audit["clauses_without_resolved_evidence"]:
            add(f"- clauses without resolved evidence: "
                f"`{audit['clauses_without_resolved_evidence']}`")
        add(f"- acceptance tests: {audit['acceptance_tests']}")
    if coverage:
        counts = coverage.get("counts") or {}
        add(f"- acceptance requirements: `{json.dumps(counts)}`")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(LAB_ROOT)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
