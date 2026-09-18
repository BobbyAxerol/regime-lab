#!/usr/bin/env python
"""Render reports/lab06_report.md from committed artifacts only (CLAUDE.md rule 9)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"
OUT = LAB_ROOT / "reports" / "lab06_report.md"

from crypto_regime_lab.evidence import glossary as G  # noqa: E402
from crypto_regime_lab.evidence.data_sources import data_provenance_lines  # noqa: E402


def load(name):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def fmt(value, digits=4, signed=False):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    return str(value)


def main() -> int:
    model = load("lab06_response_model.json")
    registry = load("lab06_bank_registry.json")
    spec = load("lab06_policy_spec.json")
    ledger = load("lab06_decision_ledger.json")
    audit = load("lab06_task_audit.json")
    coverage = load("acceptance_test_coverage.json")

    lines: list[str] = []
    add = lines.append
    add("# LAB-06 — Conditional parameter response và bốn clocks")
    add("")
    add("Generated from committed artifacts by `scripts/write_lab06_report.py`. Nothing is "
        "re-estimated here.")
    add("")
    add("## Glossary — what each term means and where it applies")
    add("")
    add("| term | meaning | where it applies in this lab |")
    add("|---|---|---|")
    for term, meaning, where in G.BY_PHASE["LAB-06"]:
        add(f"| **{term}** | {meaning} | {where} |")
    add("")

    add("## What this phase claims and does not claim")
    add("")
    add("This layer joins the LAB-05 state to the LAB-04 candidate utilities and turns the join "
        "into a keep/switch decision. The exit gate is that **every keep or switch carries "
        "evidence, data cutoffs and consistent units** — not that switches happen. Guide L06 is "
        "explicit: **zero switches because no challenger cleared the bar is a valid result**, and "
        "a policy that switched in order to look busy would be the failure, not the pass.")
    add("")
    add("**Scope: 1 of the 20 primary cells.** The mechanism is built and measured on "
        f"**{(model or {}).get('alpha_id', 'A-SC')} / {(model or {}).get('symbol', 'BTCUSDT')}** "
        "only — the first cell of the guide's pilot order (§10.4 A-SC → A-HMA → A-VWAP → "
        "A-HASH). Guide L06 asks for the response estimator, the bank, the decision machine and "
        "the four clocks; the 4 alpha × 5 symbol matrix is the LAB-08/09 comparison surface, not "
        "this phase's. Every number below therefore describes one cell and must not be read as "
        "an aggregate over the matrix.")
    add("")

    if model is not None:
        panel_rows = model.get("episode_panel_rows")
        lines.extend(data_provenance_lines(LAB_ROOT, snapshot_id="server_core_v1", consumed={
            "symbols": [model["symbol"]],
            "products": ["crypto_binance_futures_1m"],
            "role": "development",
            "window": ["2020-01-01", "2023-12-31"],
            "notes": [
                "regime context comes from the LAB-05 jump model, which fits the **8 primary-core "
                "features (G1×3, G2×2, G5×3)**. Those derive from the perpetual 1m bars alone: "
                "the G3 metrics product and the G4 order-book product are cohort extensions this "
                "phase does not read, so drift in either cannot reach these results.",
                f"episodes: **{panel_rows:,}** rows in "
                f"`{model.get('episode_panel_path')}`, a **"
                f"{model['horizon']['registered_horizon_days']}-day** non-overlapping grid",
                f"decisions assessed every **4h** regime observation, "
                f"**{(ledger or {}).get('decisions', 0):,}** in total",
            ],
        }))

    if model is not None:
        add("## L06.1 — the episode table")
        add("")
        horizon = model["horizon"]
        add(f"- registered horizon **{horizon['registered_horizon_days']} days**; measured mean "
            f"holding **{fmt(horizon['measured_mean_holding_days'], 2)} days** → the horizon "
            f"covers the holding period: **{horizon['horizon_covers_mean_holding']}**")
        add(f"- {horizon['rule']}")
        add(f"- **{model['episode_panel_rows']}** episode rows written to "
            f"`{model['episode_panel_path']}`")
        add("")

    if registry is not None:
        add("## L06.2 — the candidate bank and its lineage")
        add("")
        add("| cutoff | admissible | within 3–8 | rejected | trial rows kept |")
        add("|---|---|---|---|---|")
        for cutoff, bank in registry["banks"].items():
            add(f"| {cutoff[:10]} | {bank['admissible_count']} | "
                f"{bank['within_proposed_size']} | {len(bank['rejected'])} | "
                f"{bank['trial_rows_retained']} |")
        add("")
        first = next(iter(registry["banks"].values()))
        add(f"- {first['lineage_rule']}")
        add(f"- {registry['specialist_rule']['rule']}")
        add("")

    if model is not None:
        add("## L06.3 — the conditional response estimator")
        add("")
        hyper = model["hyperparameters"]
        add(f"- kernel bandwidth **{hyper['bandwidth_h']}**, recency τ **"
            f"{hyper['recency_tau_days']} days**, shrinkage κ **{hyper['shrink_kappa']}**")
        add(f"- support gates: N_eff ≥ **{hyper['min_effective_episodes']}** over ≥ "
            f"**{hyper['min_contiguous_blocks']}** contiguous blocks; one episode above "
            f"**{hyper['dominance_share']:.0%}** of the weight is flagged")
        add(f"- {hyper['chosen_on']}")
        add(f"- outcome information used in the weights: "
            f"**{hyper['outcome_information_used_in_weights']}**")
        add("")
        add(f"- **{model['response_count']}** estimates produced")
        add("")
        add("| status | count |")
        add("|---|---|")
        for status, count in sorted(model["status_counts"].items()):
            add(f"| `{status}` | {count} |")
        add("")
        add(f"- supporting episode ids and weights attached to every estimate: "
            f"**{model['supporting_neighbors_attached']}**")
        add("")

    if ledger is not None:
        add("## L06.4 — the decision ledger")
        add("")
        add("| decision | count |")
        add("|---|---|")
        for name, count in ledger["counts"].items():
            add(f"| `{name}` | {count} |")
        add("")
        add(f"- decisions: **{ledger['decisions']}**, switches: **{ledger['switch_count']}**")
        add("")
        rows = ledger.get("ledger") or []
        if rows and "decision_after_guard" in rows[0]:
            gates: dict = {}
            for row in rows:
                gate = row["decision_after_guard"]["binding_gate"] or "none"
                gates[gate] = gates.get(gate, 0) + 1
            economics_ran = sum(1 for r in rows
                                if (r["proposal_before_guard"] or {}).get("status") == "PROPOSED")
            cleared = sum(1 for r in rows
                          if (r["proposal_before_guard"] or {}).get("clears_the_economics"))
            refused = sum(1 for r in rows
                          if r["decision_after_guard"]["changed_the_proposal"])
            add("### Which gate actually bound (guide 13.4)")
            add("")
            add("Every decision now records what the economics **proposed before any gate ran** "
                "and what the guards did with it — including a no-switch. Without the pair, "
                "*no challenger was better* and *a challenger WAS better and a gate refused it* "
                "are the same row, and that difference is the entire content of an inaction "
                "region.")
            add("")
            add("| binding gate | decisions |")
            add("|---|---|")
            for gate, count in sorted(gates.items(), key=lambda kv: -kv[1]):
                add(f"| `{gate}` | {count:,} |")
            add("")
            add(f"The economics ran on **{economics_ran:,}** of {len(rows):,} decisions. A "
                f"challenger cleared transition cost plus margin on **{cleared}** of them, and a "
                f"later gate refused a clearing challenger on **{refused}**. So the inaction "
                "region bound at the **economics**, every time the economics ran: no capacity, "
                "warmth, spacing or campaign gate ever had to refuse anything.")
            add("")
        add("Each verdict carries its own denominator. `all(...)` over an empty population is "
            "True and reads exactly like a verified claim — *every switch carries its supporting "
            "episodes* was reported True across a run with **zero switches**, and quoted here as "
            "evidence that it carried them.")
        add("")
        add("| verdict | holds | checked over | reading |")
        add("|---|---|---|---|")
        for name, verdict in (ledger.get("verdicts") or {}).items():
            mark = "**VACUOUS**" if verdict["vacuous"] else str(verdict["holds"])
            add(f"| `{name}` | {mark} | {verdict['checked']} | {verdict['reading']} |")
        add("")
        if ledger.get("vacuous_verdicts"):
            add(f"> **{', '.join(ledger['vacuous_verdicts'])}** verifies nothing on this run. It "
                "is kept, and labelled, rather than counted as evidence.")
            add("")
        if ledger["switch_count"] == 0:
            add("> **Zero switches.** Guide L06's exit gate says this is a valid technical result: "
                "the machinery is judged on whether every decision is evidenced and causally "
                "clean, not on whether it decided to trade. The decision counts above say WHICH "
                "constraint bound, which is the part a reader can act on.")
            add("")

    if spec is not None:
        add("## L06.5 — four clocks")
        add("")
        clocks = spec["clocks"]
        add("| clock | cadence |")
        add("|---|---|")
        for name, cadence in clocks["cadences"].items():
            add(f"| {name} | {cadence} |")
        add("")
        counters = clocks["counters"]
        add(f"- counters — inference **{counters['inference']}**, switch assessments "
            f"**{counters['switch_assessments']}**, switches executed "
            f"**{counters['switches_executed']}**, bank refreshes "
            f"**{counters['bank_refreshes']}**, model retrains **{counters['model_retrains']}**")
        add(f"- {counters['rule']}")
        add(f"- {clocks['separation_rule']}")
        add(f"- a triggered-refresh variant is separate: "
            f"**{clocks['triggered_refresh_is_a_separate_variant']}**")
        add("")
        add("### Switch rule")
        add("")
        add(f"`{spec['switch_rule']}` with z_alpha **{spec['z_alpha']}** and margin "
            f"**{spec['delta_margin']}**, minimum spacing **{spec['min_switch_spacing']}**")
        add("")
        add(f"- check order: {' → '.join(spec['check_order'])}")
        add(f"- {spec['z_alpha_note']}")
        add(f"- {spec['cost_charging']}")
        add("")
        campaigns = spec["campaigns"]
        add("### Campaigns")
        add("")
        add(f"- open **{campaigns['open']}**, transition-blocked "
            f"**{campaigns['transition_blocked']}**, forced unwind used: "
            f"**{campaigns['forced_unwind_used']}**")
        add(f"- {campaigns['forced_unwind_rule']}")
        add(f"- {campaigns['shadow_account_rule']}")
        add("")
        add("## L06.6 — what this layer cannot measure")
        add("")
        limits = spec["counterfactual_limits"]
        add("| id | limit | consequence |")
        add("|---|---|---|")
        for limit in limits["limits"]:
            add(f"| {limit['id']} | {limit['limit']} | {limit['consequence']} |")
        add("")
        add(f"- {limits['why_uncertainty_is_not_enough']}")
        add(f"- {limits['deploy_equity_rule']}")
        add(f"- reset-flat expert curve used as deploy equity: "
            f"**{spec['expert_curve']['reset_flat_expert_curve_used_as_deploy_equity']}**")
        add("")

    add("## Audit and acceptance coverage")
    add("")
    if audit:
        add(f"- clause audit: **{audit['tasks_done']}/{audit['tasks_total']}** DONE, "
            f"driven by a checklist written BEFORE the code "
            f"(`{audit['checklist_source']}`)")
        add(f"- clauses with no evidence pointer: "
            f"**{audit['clauses_without_an_evidence_pointer'] or 'none'}**")
        add(f"- acceptance tests: `{audit['acceptance_tests']}` "
            f"(passed = {audit['acceptance_tests_passed']})")
        for row in audit["tasks"]:
            if row["status"] != "DONE":
                add(f"  - **{row['status']}** {row['clause_id']} — {row['requirement']}")
    if coverage:
        add(f"- guide §14 coverage as of {coverage['as_of_phase']}: "
            f"`{json.dumps(coverage['counts'])}` of 64")
    add("")
    add("## Corrections made during LAB-06")
    add("")
    add("- **A leaked loop variable corrupted the bank's lineage.** `build_bank` computed "
        "`discovered_at` in the filtering pass and then read that same variable in the building "
        "pass, so every entry received the timestamp of whichever discovery happened to be last. "
        "The filter itself was correct — the bank held the right candidates — but the recorded "
        "discovery time was wrong on all of them, which is exactly the field T46 exists to "
        "protect. It surfaced only because `admissible()` re-checks the entry's own timestamp "
        "instead of trusting the build, and the measured symptom was banks of size "
        "**[0, 0, 0, 0, 0, 8]** where every one should have held 8.")
    add("- **The contiguous-block check was structurally dead.** Blocks were counted over every "
        "episode with a weight above 1e-9, and a Gaussian kernel never reaches zero, so every "
        "set of episodes looked like one unbroken run. Combined with an `order` built from the "
        "filtered list index rather than the position in time, the check reported **1 block for "
        "all 400 sampled estimates** and every recommendation was refused for the wrong reason. "
        "Blocks are now counted over the SUPPORT SET — the smallest group of episodes carrying "
        "90% of the weight — and the order is the episode's index in the global window grid.")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines)")
    for name, artifact in (("response_model", model), ("bank_registry", registry),
                           ("policy_spec", spec), ("decision_ledger", ledger)):
        if artifact is None:
            print(f"NOTE: {name} absent; the report says so")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
