#!/usr/bin/env python
"""Render reports/lab07_report.md from committed artifacts only (CLAUDE.md rule 9)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"
OUT = LAB_ROOT / "reports" / "lab07_report.md"

from crypto_regime_lab.evidence import glossary as G  # noqa: E402
from crypto_regime_lab.evidence.data_sources import data_provenance_lines  # noqa: E402


def load(name):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def main() -> int:
    trace = load("lab07_continuous_trace.json")
    segments = load("operational_segments.json")
    activations = load("parameter_activation_tape.json")
    binding = load("integration_binding_map.json")
    audit = load("lab07_task_audit.json")
    coverage = load("acceptance_test_coverage.json")
    causality = load("causality_verification.json")
    leakage = load("lab07_leakage_audit.json")

    lines: list[str] = []
    add = lines.append
    add("# LAB-07 — Continuous regime-aware WFO integration")
    add("")
    add("Generated from committed artifacts by `scripts/write_lab07_report.py`. Nothing is "
        "re-estimated here.")
    add("")
    lines.extend(G.render(G.BY_PHASE["LAB-07"]))
    add("")

    add("## What this phase claims and does not claim")
    add("")
    add("LAB-04 selected parameters fold by fold, LAB-05 produced states, LAB-06 turned them into "
        "keep/switch decisions. Each evaluated its own windows independently. **This phase asks "
        "whether those decisions can be DELIVERED on one account that never restarts** — and "
        "nothing more. It does not claim an edge, and it does not compare arms; the four-arm "
        "factorial is LAB-08's.")
    add("")
    add("The exit gate is negative in form: no leakage, no account resets, no handcrafted fills, "
        "disabled-hooks parity, dynamic integration, and an unsupported hook recorded as a "
        "blocker rather than rerouted. A phase that passes it has shown the machinery does not "
        "distort what it delivers.")
    add("")
    add("**Scope: 1 of the 20 primary cells** — A-SC / BTCUSDT, development role, at A-SC's "
        "registered 15-minute primary decision interval (guide §10.4).")
    add("")

    if trace:
        lines.extend(data_provenance_lines(LAB_ROOT, snapshot_id="server_core_v1", consumed={
            "symbols": [trace["symbol"]],
            "products": ["crypto_binance_futures_1m"],
            "role": trace["data_role"],
            "window": trace["window"],
            "notes": [
                f"**{trace['bars']:,}** 15-minute bars — the alpha's registered decision "
                "interval, not the cheaper 4h panel. An integration run on 4h would have had "
                "almost no trades, and every gate below would have passed on a flat account",
                "the activation schedule is arm A's OWN LAB-04 selections at its own six "
                "cutoffs; no parameter set here was invented for this phase",
            ],
        }))

    # ---- L07.1 ----
    add("## L07.1 — parity before anything else")
    add("")
    if trace:
        parity = trace["integration_baseline_parity"]
        add("The integration with **nothing scheduled** must reproduce the canonical "
            "`run_candidate` path over the same real bars. If it did not, every arm comparison "
            "downstream would be measured against a baseline this phase had quietly altered.")
        add("")
        add("| surface | identical |")
        add("|---|---|")
        for surface, ok in parity["surfaces"].items():
            add(f"| {surface} | **{ok}** |")
        add("")
        add(f"- canonical fills **{parity['canonical_fills']}**, integrated fills "
            f"**{parity['integrated_fills']}** — equal, and non-zero, so this is not two empty "
            "lists agreeing")
        add(f"- final equity {parity['canonical_final_equity']:,.4f} vs "
            f"{parity['integrated_final_equity']:,.4f}")
        add(f"- {parity['why_four_surfaces']}")
        add("")
        hook = trace["inert_hook_parity"]
        add(f"Separately, **DISABLED vs INERT vs baseline**: identical = **{hook['identical']}**. "
            f"{hook['why_three_runs']}")
        add("")
        engine = trace["engine_fixed_intent_parity"]
        add(f"Fixed-intent Python/Rust parity: **{engine['status']}**, established before any "
            "performance number is quoted. The native backend exposes no per-fill trace, so "
            "full event-trace parity is recorded as `BLOCKED_CAPABILITY` and never claimed.")
        add("")

    # ---- T56 the account ----
    add("## T56 / guide 10.3 — one account, parameters changing under it")
    add("")
    if trace:
        account = trace["continuous_account"]
        add("| | |")
        add("|---|---|")
        add(f"| bars | {trace['bars']:,} |")
        add(f"| entries | {account['entries']} |")
        add(f"| engine fills | {account['fills']} |")
        add(f"| equity | {account['initial_equity']:,.0f} → "
            f"{account['final_equity']:,.2f} (**{account['total_return']:+.2%}**) |")
        add(f"| account resets | **{account['account_resets']}** |")
        add(f"| spliced from independent runs | **{account['spliced_from_independent_runs']}** |")
        add(f"| single engine pass | **{account['single_engine_pass']}** |")
        add("")
        add("Every switch, with what the migration contract cost it:")
        add("")
        add("| activation | requested at bar | effective at bar | blocked for | reason while blocked |")
        add("|---|---|---|---|---|")
        for switch in account["switches"]:
            add(f"| `{switch['activation_id']}` | {switch['requested_at_bar']:,} | "
                f"{switch['effective_at_bar']:,} | {switch['blocked_bars']} bars | "
                f"{switch['blocked_reason'] or '—'} |")
        add("")
        add("**No switch was instant.** Each waited for a flat book and for its own indicators to "
            "warm on real history — guide §9.5's contract, priced in bars. A layer that activated "
            "on request would have reported a timing edge it could never have taken.")
        add("")

    # ---- L07.5 segments ----
    add("## L07.4 — the migration contract, exercised on paths this run did not hit")
    add("")
    if activations:
        add(f"The tape carries **{activations['requested']}** requested activations, "
            f"**{activations['effected']}** effected. Beyond the five the account performed, the "
            "guide §9.5 paths this particular run never reached are driven explicitly, because a "
            "contract tested only by its happy path is a contract nobody has tested:")
        add("")
        add("| blocked reason | count |")
        add("|---|---|")
        for reason, count in sorted(activations["blocked_by_reason"].items()):
            add(f"| `{reason}` | {count} |")
        add("")
        add(f"- versions still referenced by live protective orders: "
            f"`{activations['versions_referenced_by_live_orders']}` — a retired version stays "
            "resolvable while any order points at it")
        add(f"- forced unwind used: **{activations['forced_unwind_used']}**")
        add("")
        for key, rule in activations["rules"].items():
            add(f"- **{key}**: {rule}")
        add("")

    add("## L07.5 / T55 — segments, and the average that flatters")
    add("")
    if segments:
        add(f"**{segments['count']}** segments ({segments['closed']} closed, "
            f"{segments['open']} open), and **{segments['no_change_trigger_count']:,}** no-change "
            "triggers — a refresh that fired and changed nothing is recorded, because dropping "
            "them would make the refresh cadence look like the switch rate.")
        add("")
        add("| segment | version | start | end | length (days) |")
        add("|---|---|---|---|---|")
        for segment in segments["segments"]:
            length = ("—" if segment["length_days"] is None
                      else f"{segment['length_days']:.1f}")
            add(f"| {segment['segment_id']} | `{segment['parameter_version'][:14]}` | "
                f"{segment['start'][:10]} | {str(segment['end'])[:10] if segment['end'] else '**null**'} | "
                f"{length} |")
        add("")
        add(f"The open segment's end is null: **{segments['open_segment_has_null_end']}**. Its "
            "length does not exist yet, and writing it would hand any policy reading the tape the "
            "answer to how long its own decision is about to last.")
        add("")
        daily = segments["daily_account_comparison"]
        if daily.get("account_daily_sharpe") is not None:
            add("### The measured gap T55 exists to prevent")
            add("")
            add("| | |")
            add("|---|---|")
            add(f"| **account daily Sharpe** (primary) | **{daily['account_daily_sharpe']:.4f}** |")
            add(f"| unweighted mean of per-segment Sharpes | "
                f"{daily['unweighted_mean_of_segment_sharpes']:.4f} |")
            add(f"| segment day counts | {daily['segment_day_counts']} |")
            add("")
            ratio = (daily["unweighted_mean_of_segment_sharpes"]
                     / daily["account_daily_sharpe"]) if daily["account_daily_sharpe"] else None
            if ratio:
                add(f"Averaging the fold Sharpes gives **{ratio:.1f}×** the account's own number "
                    "on the same trades. The segments differ in length by construction, so an "
                    "unweighted mean weights a 177-day segment like a 193-day one. The daily "
                    "account series is indifferent to where the boundaries fell, which is why the "
                    "guide makes it the comparison.")
            add("")
            add("| segment | days | Sharpe (diagnostic only) |")
            add("|---|---|---|")
            for row in daily["per_segment_sharpe"]:
                value = "—" if row["sharpe"] is None else f"{row['sharpe']:+.3f}"
                add(f"| {row['segment_id']} | {row['days']} | {value} |")
            add("")

    # ---- L07.3 ----
    add("## L07.3 — a refit costs time, and the cost is measured")
    add("")
    if trace:
        jobs = trace["training_jobs"]
        benchmark = jobs["benchmark"]
        add(f"- latency source **{benchmark['source']}**: one real `causal_fit` is timed in the "
            f"run at **{benchmark['measured_seconds_per_fit']:.3f} s/fit** on "
            f"{benchmark['workers']} worker")
        add(f"- **{jobs['requested']}** refit jobs at the registered 28-day cadence, "
            f"{jobs['completed']} completed; delays "
            f"{jobs['min_delay_seconds']:.2f}s to {jobs['max_delay_seconds']:.2f}s")
        add(f"- jobs with zero latency: **{jobs['zero_latency_jobs']}**")
        add(f"- {benchmark['rule']}")
        add(f"- deployment account reachable from the refit runner: "
            f"**{jobs['deployment_account_reachable_from_here']}** — {jobs['isolation_rule']}")
        add("")

    # ---- L07.6 ----
    add("## L07.6 — what happens when something breaks")
    add("")
    if trace:
        failures = trace["failures"]
        add(f"All **{len(failures['modes_exercised'])} of {len(failures['modes_declared'])}** "
            "declared failure modes were EXERCISED, not merely declared:")
        add("")
        add("| mode | times | outcome |")
        add("|---|---|---|")
        seen: dict[str, str] = {}
        for record in failures["records"]:
            seen.setdefault(record["mode"], record["outcome"])
        for mode, count in sorted(failures["by_mode"].items()):
            add(f"| `{mode}` | {count} | {seen.get(mode, '')} |")
        add("")
        add(f"- parameters chosen at random to resolve a failure: "
            f"**{failures['random_parameter_selection_used']}**")
        add(f"- {failures['rule']}")
        add("")

    # ---- L07.7 ----
    add("## L07.7 — the future cannot reach the past")
    add("")
    if trace:
        replay = trace["replay_parity"]
        prefix = trace["prefix_stability"]
        add(f"- **replay parity**: streaming one event at a time equals the offline replay — "
            f"**{replay['identical']}** over {replay['events']:,} events. The consumer derives "
            "the DECISION each event implies rather than reading the event's own fields back, "
            "which would have passed on any tape at all.")
        add(f"- **prefix stability on the real account**: every price after bar "
            f"{prefix['cutoff_bar']:,} multiplied by 5, and the mutation really did change the "
            f"suffix (**{prefix['suffix_actually_changed']}**). Equity and active version before "
            f"the cutoff stayed bit-identical: **{prefix['prefix_survives_future_mutation']}**.")
        add(f"- **{prefix['entries_in_prefix']}** trades happened before the cutoff, so there was "
            "something at risk of leaking. A prefix with no trades would have proved nothing.")
        add(f"- the prefix of the longer run equals the whole of the shorter run: "
            f"**{prefix['prefix_matches_longer_run']}**")
        add("")
    if causality:
        add(f"The four-layer causality gate is **{causality['status']}** with the leaky control "
            f"detected (**{causality['leaky_control_is_detected']}**): "
            f"{', '.join(causality['verdicts'])}.")
        add("")

    # ---- binding ----
    add("## Leakage audit — LAB-07 and everything it inherits")
    add("")
    if leakage:
        add(f"A separate, harsher pass (`scripts/audit_lab07_leakage.py`): **can any information "
            f"from after a decision reach that decision**, through this phase or through anything "
            f"it inherited from LAB-03 to LAB-06? **{leakage['checks_passed']}/"
            f"{leakage['checks_total']} — {leakage['status']}**.")
        add("")
        add("| check | verdict | had something to detect |")
        add("|---|---|---|")
        for check in leakage["checks"]:
            detect = "yes" if check.get("had_something_to_detect") else "**no**"
            add(f"| {check['check']} | {'PASS' if check['passed'] else 'FAIL'} | {detect} |")
        add("")
        add(f"> {leakage['vacuity_rule']}")
        add("")
        if leakage["checks_with_nothing_to_detect"]:
            add(f"One probe had nothing to detect: **{leakage['checks_with_nothing_to_detect'][0]}"
                "**. A-SC rests no protective orders at all — 119 entries, 119 technical exits, "
                "zero stops or targets — so the exit fixed point converges trivially on this "
                "cell. The property is exercised on **A-HMA**, which rests both, in "
                "`test_the_fixed_point_holds_on_an_alpha_that_rests_protective_orders`: 26 "
                "protective exits, converged, and identical to `run_candidate`.")
            add("")
        mutation = next(c for c in leakage["checks"] if "prefix" in c["check"])
        add(f"The strongest of these is the future-mutation probe. Every column the adapter can "
            f"read — `{', '.join(mutation['columns_mutated'])}` — is multiplied by 5 after bar "
            f"{mutation['cutoff_bar']:,}, with **{mutation['trades_before_the_cutoff']}** trades "
            "already in the prefix. {}".format(mutation["note"]))
        add("")

    add("## OUT.2 — what the lab binds to, and what it refuses to fake")
    add("")
    if binding:
        add(f"Probed against the INSTALLED package (`{binding['installed_version']}`): "
            f"**{len(binding['bound'])} bound, {len(binding['blocked'])} blocked**.")
        add("")
        add("| lab operation | installed symbol | status |")
        add("|---|---|---|")
        for name, bind in binding["bindings"].items():
            add(f"| {name} | `{bind['installed_symbol']}` | **{bind['status']}** |")
        add("")
        add(f"> {binding['reroute_policy']}")
        add("")
        add("Known blockers, recorded rather than worked around:")
        add("")
        for name, blocker in binding["known_blockers"].items():
            add(f"- **`{name}`** — {blocker['consequence']}")
        add("")

    # ---- audit ----
    add("## Audit and acceptance coverage")
    add("")
    if audit:
        add(f"- **{audit['tasks_done']}/{audit['tasks_total']}** checklist clauses DONE, "
            f"driven by `{audit['checklist_source']}` written BEFORE any integration code "
            f"(`checklist_written_before_code: {audit['checklist_written_before_code']}`)")
        add(f"- clauses with no evidence pointer: "
            f"**{audit['clauses_without_an_evidence_pointer'] or 'none'}**")
        add(f"- acceptance tests: **{audit['acceptance_tests']}**")
        add("")
    if coverage:
        counts = coverage["counts"]
        add(f"Guide §14 coverage as of {coverage['as_of_phase']}: **{counts['COVERED']} COVERED, "
            f"{counts['PARTIAL']} PARTIAL, {counts['NOT_YET_IMPLEMENTED']} NOT_YET_IMPLEMENTED** "
            "of 64.")
        add("")
        add("| id | status | note |")
        add("|---|---|---|")
        for row in coverage["requirements"]:
            if row["id"] in ("T53", "T54", "T55", "T56", "T57"):
                note = row.get("partial_reason", "")[:150]
                add(f"| {row['id']} | **{row['status']}** | {note} |")
        add("")
        add("T53 and T54 stay PARTIAL deliberately. T53 asks whether A/B/C/D share fixed "
            "economics and arms C/D do not exist; T54 asks that the legacy label be applied to a "
            "reported arm comparison and there is no arm comparison yet. Marking either COVERED "
            "would be this phase taking credit for LAB-08's work.")
        add("")

    add("## Corrections made during LAB-07")
    add("")
    add("Both were found by self-review before this report was written, and both are the same "
        "failure: **a gate that passes because nothing happened.**")
    add("")
    add("1. **The first run traded nothing.** Driving the continuous account from the 4h feature "
        "panel with no signals gave 0 fills, a flat equity curve, 1 segment and a null Sharpe — "
        "and every gate passed. `all_fills_from_engine` was true over an empty list; the T55 "
        "comparison had one segment to compare. Rebuilt on **105,120 real 15-minute bars** with "
        "the real A-SC adapter and arm A's own six LAB-04 selections: 75 entries, 150 fills, "
        "6 segments.")
    add("2. **The intent tape was built from the final adapter's decision list.** Each parameter "
        "version's adapter accumulates only the bars it personally saw, so taking the last one's "
        "list silently dropped every trade made under an earlier version — while the entry "
        "counter still counted them. The symptom was **75 entries but 18 fills**, and the "
        "reported return was **+2.11%**. Assembling the tape from the ACTIVE adapter at each bar "
        "gives 150 fills and **+0.17%**. The first number would have been published.")
    add("")
    add("### Found by the leakage re-audit, after the first version of this report")
    add("")
    add("3. **The warm-up gate was a magic number, and it moves the result.** `WARM_BARS = 64` "
        "was a constant I picked. Measured on this cell, 0 / derived / 512 bars give **+0.45% / "
        "+0.45% / −3.07%** — an unregistered free parameter of the switching policy, which guide "
        "§10.5 puts in the experiment-search ledger. The requirement is now **derived from each "
        "adapter's own `warmup_bars()`** (39, 36, 60, 61, 33 bars = its `AP + 3`), so it is the "
        "alpha's declaration rather than my choice. The headline return moved from +0.17% to "
        "**+0.45%** as a result.")
    add("")
    add("4. **The warm-up gate does not do what the first draft said.** A-SC precomputes its "
        "indicator arrays causally over the whole slice, so the values at a bar are already "
        "correct the moment the shadow adapter is built; waiting does not make them more so. "
        "What the gate actually buys is that the new version has been running on live bars for "
        "at least as long as it declares it needs — a **policy delay**, now reported as one "
        "instead of as an accuracy claim.")
    add("")
    add("5. **The exit fixed point was missing.** `run_candidate` iterates protective exits until "
        "the whole-window engine run agrees with what the sweep applied; the integration did one "
        "pass. Harmless for A-SC, which rests no protection — and silently wrong for A-HMA, "
        "A-VWAP and A-HASH, which LAB-08 runs through this same function. Added, and verified "
        "against `run_candidate` on A-HMA.")
    add("")
    add("6. **The future-mutation probe left `volume` untouched.** A-SC feeds volume into an MFI, "
        "so a strategy reading the future through volume would have passed. Every readable "
        "column is now mutated.")
    add("")
    add("7. **The trace mixed two arms.** It is labelled `A_calendar_on_one_account` — guide "
        "§10.1 arm A, which uses **no regime information** — while carrying 6,566 "
        "`REGIME_OBSERVATION_READY` events, because L07.2 requires the stream to carry them. "
        "Next to 5 activations that looks like cause and effect whether or not it is. Every "
        "activation now names its source, and `regime_information_reached_a_decision` is "
        "**False**, checked rather than asserted.")
    add("")
    add("8. **The event bus crashed on a mixed-timezone stream.** Storage timestamps are naive "
        "UTC by convention and engine frames are aware; one naive timestamp raised `TypeError` on "
        "the first sort and would have taken the whole stream's ordering with it. Normalised at "
        "publish, with the interpretation stated rather than inherited.")
    add("")
    add("### Found by a second leakage pass, before LAB-08")
    add("")
    add("Six more, and every one was a **check that could not fail**:")
    add("")
    add("9. **The regime-isolation check was circular.** The runner built "
        "`{activation_id: \"calendar_cutoff\"}` and handed it to the function that then verified "
        "every source was `calendar_cutoff`. It asserted its own conclusion. Sources are now "
        "DERIVED from the tape by matching against LAB-04's declared cutoffs — and the moment "
        "they were, **the check failed**: activations are published at their EFFECTIVE time, and "
        "one of them lands on a 4h regime observation by pure coincidence. Attribution now keys "
        "on the REQUEST time, which the activation carries because it is a past fact.")
    add("")
    add("10. **Two of the four parity surfaces were trivial.** `metrics` compared only final "
        "equity — which guide §13.6 forbids as a standalone parity claim and which `account` "
        "already implies. `selection` counted a constant that is true by construction when the "
        "schedule is empty. `metrics` now compares the whole reported set (return, Sharpe, "
        "drawdown, observation count, final equity) and `selection` schedules an activation to "
        "the SAME parameters halfway through and requires it to be a no-op — which runs the "
        "switching machinery instead of counting a constant.")
    add("")
    add("11. **The inert-hook parity compared three empty accounts.** Its digest was "
        "`4f53cda18c2baa0c` — the SHA-256 of an empty list — in all three runs. It is now driven "
        "by the canonical run's real fills, and `disabled_hooks_parity` **refuses** a signal "
        "column that never trades.")
    add("")
    add("12. **The replay consumer read a key that does not exist.** `payload.get(\"quantity\", "
        "0.0)` on an engine fill whose key is `qty` returned **0.0 for every fill**, so the "
        "consumer looked like it was reading the account while reading a default. It now raises "
        "on a missing key rather than defaulting.")
    add("")
    add("13. **T57 was marked COVERED by tests that do not test it.** The three cited tests were "
        "about refit-latency rounding; T57 is about sequential-vs-adaptive-batch semantics. "
        "Replaced with five that check the declared contract, the fixed candidate matrix "
        "replaying to the same point, and seeded determinism. Two intermediate versions of the "
        "last test grepped prose and flagged T57's own title, then its own negation — so it is "
        "now structural rather than lexical.")
    add("")
    add("14. **The regime publication lag was invented.** Observations were published at "
        "**+1 minute**; bars are left-labelled, so an observation stamped at a bar open is "
        "knowable only when that bar closes — **+4h**, which is exactly what LAB-05's emission "
        "tape records. **15× too early.** Nothing consumes it in this calendar arm, but LAB-08's "
        "arms C/D/E will, and a false availability on the tape is a leak waiting to be "
        "inherited. Now derived from `panel.REGIME_INTERVAL` and cross-checked against LAB-05.")
    add("")
    add("A fifteenth was caught by the reachability gate: `prefix_stability` in `continuous.py` was "
        "superseded by the real-account version in the runner and left behind as a weaker "
        "duplicate. Deleted.")
    add("")
    add("A sixteenth was caught by a new test rather than by the run: "
        "`daily_account_comparison` compared tz-naive segment boundaries against a tz-aware "
        "equity index. It worked in the runner because both happened to be aware, and raised "
        "`TypeError` the moment a caller mixed them. Boundaries are now aligned to the index "
        "once, inside the function.")
    add("")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
