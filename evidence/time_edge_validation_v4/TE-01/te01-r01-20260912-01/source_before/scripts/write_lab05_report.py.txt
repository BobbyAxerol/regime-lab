#!/usr/bin/env python
"""Render reports/lab05_report.md from committed artifacts only (CLAUDE.md rule 9)."""

from __future__ import annotations

import json
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"
OUT = LAB_ROOT / "reports" / "lab05_report.md"

from crypto_regime_lab.evidence import glossary as G  # noqa: E402
from crypto_regime_lab.evidence.data_sources import data_provenance_lines  # noqa: E402


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def fmt(value, digits: int = 4, signed: bool = False) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    return str(value)


def main() -> int:
    selftest = load("lab05_selftest.json")
    registry = load("lab05_regime_model_registry.json")
    tape = load("lab05_emission_tape.json")
    k_choice = load("lab05_k_selection.json")
    audit = load("lab05_task_audit.json")
    coverage = load("acceptance_test_coverage.json")

    lines: list[str] = []
    add = lines.append
    add("# LAB-05 — Persistent regime model và causal emissions")
    add("")
    add("Generated from committed artifacts by `scripts/write_lab05_report.py`. Nothing is "
        "refitted here.")
    add("")
    add("## Glossary — what each term means and where it applies")
    add("")
    add("| term | meaning | where it applies in this lab |")
    add("|---|---|---|")
    for term, meaning, where in G.BY_PHASE["LAB-05"]:
        add(f"| **{term}** | {meaning} | {where} |")
    add("")

    # ---- exit claim, stated before any number ----
    add("## What this phase does and does not claim")
    add("")
    add("The exit gate is a **technical pass**: a causal provider with a reproducible state "
        "vocabulary. Guide L05 forbids inferring predictive or financial value from fit loss, "
        "from agreement with a simulator, or from labels that look clean on a chart. Nothing "
        "below is offered as evidence that these states make money — that question belongs to "
        "LAB-06 onward and is not answered here.")
    add("")
    add("**Scope: 1 symbol.** The model is fitted and audited on "
        f"**{(registry or {}).get('symbol', 'BTCUSDT')}** only. The state vocabulary, the "
        "cadence and the diagnostics are the deliverable; a per-symbol model for the other four "
        "is not built here and no claim below generalises to them.")
    add("")

    if registry is not None:
        models = registry.get("models") or []
        lines.extend(data_provenance_lines(LAB_ROOT, snapshot_id="server_core_v1", consumed={
            "symbols": [registry["symbol"]],
            "products": ["crypto_binance_futures_1m"],
            "role": registry.get("data_role", "development"),
            "window": ["2020-01-01", "2023-12-31"],
            "notes": [
                "the jump model fits the **8 primary-core features (G1×3, G2×2, G5×3)** — the "
                "only features covering all five symbols. They derive from the perpetual 1m bars "
                "alone, so the G3 metrics product and the G4 order-book product are NOT read "
                "here and drift in either cannot reach these fits.",
                f"observation interval **{registry.get('observation_interval')}**, "
                f"rolling training memory **{registry.get('train_memory_days')} days**",
                f"**{len(models)}** fits, "
                + (f"`{models[0]['model_id']}` → `{models[-1]['model_id']}`" if models else "none"),
                f"outer_evaluation holdout touched: "
                f"**{registry.get('outer_evaluation_touched')}**",
            ],
        }))

    # ---- L05.2 acceptance checks ----
    add("## L05.2 / L05.6 — acceptance checks T37–T44")
    add("")
    if selftest is None:
        add("**MISSING** `configs/lab05_selftest.json`.")
    else:
        checks = selftest["acceptance_checks"]
        add("| id | question | measured |")
        add("|---|---|---|")
        t37 = checks["T37"]
        add(f"| T37 | does the forward DP equal exhaustive enumeration? | endpoint costs "
            f"**{t37['all_endpoint_costs_match']}**, online states "
            f"**{t37['all_online_states_match']}**, best path **{t37['all_best_paths_match']}** "
            f"over {len(t37['trials'])} random toy sequences |")
        t38 = checks["T38"]
        add(f"| T38 | batch vs streaming emissions | states "
            f"**{t38['all_states_identical']}**, costs **{t38['all_costs_identical']}**, every "
            f"prefix vintage stable **{t38['all_prefix_vintages_stable']}** |")
        t39 = checks["T39"]
        add(f"| T39 | can the fit see past its cutoff? | clean fit "
            f"`{t39['causal_fit']['verdict']}`, deliberately leaky fit "
            f"`{t39['deliberately_leaky_fit']['verdict']}`, detector meaningful "
            f"**{t39['detector_is_meaningful']}** |")
        t40 = checks["T40"]
        add(f"| T40 | degenerate model | blocked **{t40['degenerate_is_blocked']}**, healthy "
            f"usable **{t40['healthy_is_usable']}**, no fake confidence "
            f"**{t40['no_fake_confidence']}** |")
        t41 = checks["T41"]
        add(f"| T41 | refit permutes state ids | permutation recovered "
            f"**{t41['permutation_recovered']}**, declared a market transition "
            f"**{t41['declared_market_transition']}**, a genuinely moved state left unmapped "
            f"**{t41['genuinely_moved_state_is_unmapped']}** |")
        t42 = checks["T42"]
        add(f"| T42 | membership score vs probability | sums to one "
            f"**{t42['sums_to_one']}**, named a probability **{t42['is_named_probability']}**, "
            f"calibrated **{t42['calibrated']}** |")
        t43 = checks["T43"]
        add(f"| T43 | does inference trigger a retrain? | the inference modules cannot reach a "
            f"fit at all: **{t43['inference_path_calls_no_fit']}** |")
        t44 = checks["T44"]
        add(f"| T44 | novelty vs missing data | four statuses distinct "
            f"**{t44['statuses_are_distinct']}**, missing input wins over an identical residual "
            f"**{t44['missing_wins_over_novelty']}** |")
        add("")
        add("Two of these deserve their measurement spelled out, because a check that cannot "
            "fail proves nothing:")
        add("")
        add(f"- **T37** found the causal emission and the offline best path DISAGREEING in "
            f"**{t37['cases_where_causal_and_offline_disagree']}** of {len(t37['trials'])} "
            f"sequences. {t37['why_that_matters']}")
        add(f"- **T39** ran the same detector over a knowingly leaky fit and it returned "
            f"`{t39['deliberately_leaky_fit']['verdict']}`. {t39['why_the_control_exists']}.")
        add("")

    if selftest is not None and "online_algorithm_versions" in selftest:
        add("### L05.2 — greedy online and endpoint DP are two model versions")
        add("")
        versions = selftest["online_algorithm_versions"]
        add("| λ_J | endpoint-DP switches | greedy switches | label agreement | identical |")
        add("|---|---|---|---|---|")
        for row in versions["comparisons"]:
            add(f"| {row['lambda_jump']} | {row['endpoint_dp']['switches']} | "
                f"{row['greedy']['switches']} | {fmt(row['label_agreement'], 3)} | "
                f"{row['identical']} |")
        add("")
        add(versions["reading"])
        add("")
        add(f"> {versions['comparisons'][0]['mixing_rule']}")
        add("")
        m0 = selftest["m0_comparator"]
        add("### L05.2 — the M0 rule baseline, run as a comparator")
        add("")
        add("| model | switches | best-permutation agreement |")
        add("|---|---|---|")
        add(f"| M0 (frozen volatility quantiles) | {m0['m0']['switches']} | "
            f"{fmt(m0['m0']['agreement'], 3)} |")
        add(f"| M1 (discrete jump model) | {m0['m1']['switches']} | "
            f"{fmt(m0['m1']['agreement'], 3)} |")
        add("")
        add(f"- thresholds fitted on {m0['thresholds_fitted_on']}")
        add(f"- M0 is a control, not a fallback: **{m0['m0_is_a_control_not_a_fallback']}**")
        add(f"- {m0['reading']}")
        add("")

    # ---- L05.7 worlds ----
    add("## L05.7 — synthetic worlds and the negative control")
    add("")
    if selftest is None:
        add("**MISSING**.")
    else:
        worlds = selftest["synthetic_worlds"]
        add("| world | true switches | emitted switches | agreement | median detection delay |")
        add("|---|---|---|---|---|")
        for row in worlds["worlds"]:
            add(f"| {row['name']} | {row['latent_switches']} | {row['emitted_switches']} | "
                f"{fmt(row['agreement']['best_permutation_agreement'], 3)} | "
                f"{fmt(row['detection']['delay_median'], 1)} |")
        add("")
        control = worlds["negative_control"]
        add(f"> **NEGATIVE CONTROL.** {control['finding']}")
        add("")
        add(f"- {worlds['ground_truth_use']}")
        add("")
        noise = selftest["noise_sensitivity"]
        add("| noise σ | agreement | emitted switches | true switches |")
        add("|---|---|---|---|")
        for row in noise["levels"]:
            add(f"| {row['noise']} | {fmt(row['agreement'], 3)} | {row['emitted_switches']} | "
                f"{row['true_switches']} |")
        add("")
        add(noise["reading"])
        add("")

    # ---- L05.1 / L05.3 / L05.5 on real data ----
    add("## L05.1 / L05.3 / L05.5 — fits on the development role")
    add("")
    if registry is None:
        add("**MISSING** `configs/lab05_regime_model_registry.json`.")
    else:
        add(f"- symbol **{registry['symbol']}**, observation interval "
            f"**{registry['observation_interval']}**, training memory "
            f"**{registry['train_memory_days']} days**, λ_J **{registry['lambda_jump']}**, "
            f"K **{registry['n_states']}**")
        add(f"- data role **{registry['data_role']}**, outer evaluation touched: "
            f"**{registry['outer_evaluation_touched']}**")
        clocks = registry["clock_separation"]
        add(f"- {clocks['model_fit_cadence']} ({clocks.get('first_cutoff')} .. "
            f"{clocks.get('last_cutoff')})")
        add(f"- a fit does NOT refresh the bank ({clocks['bank_refresh_triggered_by_this']}) and "
            f"does NOT start a parameter search "
            f"({clocks['parameter_search_triggered_by_this']}). {clocks['rule']}")
        add("")
        models = registry["models"]
        degenerate = [m["training_cutoff"] for m in models
                      if m["fit_diagnostics"]["degeneracy"]["is_degenerate"]]
        add(f"- **{len(models)} fits**, of which **{len(degenerate)}** were degenerate"
            + (f": {degenerate}" if degenerate else ""))
        mappings = registry["namespace_mappings"]
        unmapped = [m for m in mappings if not m["all_states_mapped"]]
        add(f"- **{len(mappings)} namespace mappings** between consecutive fits; "
            f"**{len(unmapped)}** contained a state that could not be matched")
        add(f"- none of them declared a market transition: "
            f"**{not any(m['is_market_transition'] for m in mappings)}**")
        add("")
        add("A refit is free to hand back the same three states under permuted integers. The "
            "state counts below show that happening in practice — the largest state moves "
            "between index positions from one fit to the next — which is exactly why each fit "
            "gets its own namespace.")
        add("")
        add("| cutoff | selected seed | state counts | centroid digest | degenerate |")
        add("|---|---|---|---|---|")
        for model in models[:8]:
            add(f"| {model['training_cutoff']} | {model['selected_seed']} | "
                f"{model['fit_diagnostics']['state_counts']} | `{model['centroid_digest']}` | "
                f"{model['fit_diagnostics']['degeneracy']['is_degenerate']} |")
        if len(models) > 8:
            add(f"| … {len(models) - 8} more fits | | | | |")
        add("")

    if k_choice is not None:
        add("### L05.4 — choosing K")
        add("")
        add(f"- registered starting K: **{k_choice['registered_starting_k']}**, used: "
            f"**{k_choice['registered_k_used']}**")
        add(f"- inner criterion picked **{k_choice['best_by_inner_criterion']}** "
            f"(agrees with the registered choice: "
            f"**{k_choice['inner_criterion_agrees_with_registered']}**)")
        add(f"- holdout inspected: **{k_choice['chart_inspection_used']}**")
        add("")
        add("| K | mean per-observation objective | worst inner fold |")
        add("|---|---|---|")
        for k, score in k_choice["scores"].items():
            add(f"| {k} | {fmt(score['mean_per_observation_objective'], 5)} | "
                f"{fmt(score['worst_fold'], 5)} |")
        add("")
        if not k_choice["inner_criterion_agrees_with_registered"]:
            add(f"> **The registered K and the registered selection method DISAGREE.** The inner "
                f"criterion preferred K={k_choice['best_by_inner_criterion']} by "
                f"{fmt(k_choice.get('relative_margin', 0) * 100, 1)}%. "
                f"{k_choice.get('direction_note', '')}")
            add("")
        add(f"- {k_choice['override_policy']}")
        add(f"- {k_choice['method_note']}")
        add("")

    # ---- guide 8.3 ablation and the model ladder ----
    ablation = load("lab05_group_ablation.json")
    if ablation is not None:
        add("### Guide 8.3 — group ablation")
        add("")
        add("| feature blocks | features | inner objective | variance resolved out of fold | Δ | improved |")
        add("|---|---|---|---|---|---|")
        for row in ablation["ladder"]:
            delta = ("—" if row["variance_resolved_gain"] is None
                     else fmt(row["variance_resolved_gain"], 5, True))
            add(f"| {' + '.join(row['groups'])} | {row['features_active']} | "
                f"{fmt(row['mean_per_observation_objective'], 5)} | "
                f"{fmt(row['variance_resolved_out_of_fold'], 5, True)} | {delta} | "
                f"{row['improved']} |")
        add("")
        add(f"- decided on **{ablation['decided_on']}**, not on the objective. "
            f"{ablation['why_not_the_objective']}")
        add(f"- blocks contributing beyond price/volatility: "
            f"**{ablation['blocks_that_improved_out_of_fold'] or 'NONE'}**")
        add("")
        add(f"> {ablation['finding']}")
        add("")
        ladder = ablation.get("model_ladder")
        if ladder:
            add("### Guide 8.1 — position on the model ladder")
            add("")
            add("| rung | model | built | why not / role |")
            add("|---|---|---|---|")
            for name, rung in ladder["rungs"].items():
                reason = rung.get("why_not") or rung.get("role", "")
                add(f"| {name} | {rung['model']} | {rung['implemented']} | {reason} |")
            add("")
            add(f"- {ladder['scope_rule']}")
            add("")

    # ---- emissions ----
    add("## L05.2 — the emission tape")
    add("")
    if tape is None:
        add("**MISSING** `configs/lab05_emission_tape.json`.")
    else:
        add(f"- **{tape['total_emissions']}** emissions across **{len(tape['namespaces'])}** "
            f"namespaces, produced by {tape['emitted_by']}")
        add(f"- switches counted WITHIN namespaces: "
            f"**{tape['total_switches_within_namespaces']}**")
        add(f"- {tape['cross_namespace_rule']}")
        add("")
        add("| quality status | count |")
        add("|---|---|")
        for status, count in sorted(tape["quality_status_counts"].items()):
            add(f"| `{status}` | {count} |")
        add("")
        add(f"- model transitions emitted: **{len(tape['model_transitions_emitted'])}**, none of "
            "which is a market event")
        add("")
        stress = tape.get("stress_overlay")
        if stress:
            add(f"- **stress overlay** measured on {stress['observations']} observations "
                f"(mean {fmt(stress['mean_stress_score'], 3)}, p95 "
                f"{fmt(stress['p95_stress_score'], 3)}). It is a regime state: "
                f"**{stress['is_a_regime_state']}**; joint labels created: "
                f"**{stress['joint_labels_created']}**. {stress['rule']}")
        cross = tape.get("cross_namespace_view")
        if cross:
            add(f"- **cross-namespace view**: {cross['total_emissions_translated']} emissions "
                f"translated into the previous fit's ids, {cross['total_unmapped']} left as -1. "
                f"decision_eligible = **{cross['decision_eligible']}**. {cross['rule']}")
        add("")
    source = (registry or {}).get("source_transition_check")
    if source:
        add("### L05.3.5 — source transition")
        add("")
        add(f"- declared source columns: `{json.dumps(source['declared_sources'])}`")
        add(f"- real boundaries found: **{source['real_boundaries_found']}**. "
            f"{source['no_transition_note']}")
        control = source["positive_control"]
        add(f"- **positive control**: a 4-IQR level shift was injected into "
            f"`{control['injected_shift_features']}` and the detector flagged "
            f"`{control['detected']}` → can fire: **{control['detector_can_fire']}**. "
            f"{control['why']}")
        add("")

    # ---- audit ----
    add("## Audit and acceptance coverage")
    add("")
    if audit:
        add(f"- clause audit: **{audit['tasks_done']}/{audit['tasks_total']}** DONE"
            + (f", blocked: {audit['tasks_blocked']}" if audit["tasks_blocked"] else ""))
        add(f"- acceptance tests: `{audit['acceptance_tests']}` "
            f"(passed = {audit['acceptance_tests_passed']})")
        for row in audit["tasks"]:
            if row["status"] != "DONE":
                add(f"  - **{row['status']}** {row['task_id']} — {row['requirement']}")
    if coverage:
        add(f"- guide §14 coverage as of {coverage['as_of_phase']}: "
            f"`{json.dumps(coverage['counts'])}` of 64")
    add("")
    add("## Corrections made during LAB-05")
    add("")
    add("- **The first fit schedule did not match the registered cadence.** Guide 8.6 registers a "
        "28-day model fit; the first implementation used four cutoffs six months apart. The "
        "measured consequence was that **762 of 1099 emissions came back `STALE_MODEL`**, because "
        "the model in force was older than the 56-day staleness bound for most of the run. The "
        "schedule now refits every 28 days and each observation is labelled by the model that was "
        "current at that time.")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines)")
    for name, artifact in (("selftest", selftest), ("registry", registry), ("tape", tape)):
        if artifact is None:
            print(f"NOTE: {name} artifact absent; the report says so explicitly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
