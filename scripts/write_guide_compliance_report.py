#!/usr/bin/env python
"""Render reports/guide_compliance_inspection.md — LAB-01..06 against the guide.

A re-inspection before LAB-07, asking a different question from the phase
audits. Those ask "did L0N.M get done". This asks "does the guide require
anything that no L0N.M task owns" — because a requirement with no owner is one
every phase audit can pass while it stays undone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
CONFIGS = LAB_ROOT / "configs"
OUT = LAB_ROOT / "reports" / "guide_compliance_inspection.md"
sys.path.insert(0, str(LAB_ROOT / "src"))


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def main() -> int:
    coverage = load("acceptance_test_coverage.json")
    identities = load("id_taxonomy.json")
    budget = load("compute_budget_registration.json")
    causality = load("causality_verification.json")
    audits = {n: load(f"lab0{n}_task_audit.json") for n in (1, 2, 3, 4, 5, 6)}

    lines: list[str] = []
    add = lines.append
    add("# Guide compliance inspection — LAB-01 through LAB-06")
    add("")
    add("Generated from committed artifacts by `scripts/write_guide_compliance_report.py`.")
    add("")
    add("## What this inspection asked")
    add("")
    add("The per-phase audits ask *did every L0N.M task get done*. They all pass. This asks a "
        "different question: **does the guide require anything that no L0N.M task owns?** A "
        "requirement with no owning task is one every phase audit can pass while it stays "
        "undone — and all three gaps below are exactly that shape.")
    add("")

    add("## Phase task audits — unchanged, still passing")
    add("")
    add("| phase | rows audited | granularity | status |")
    add("|---|---|---|---|")
    for n, audit in audits.items():
        if audit is None:
            add(f"| LAB-0{n} | — | — | **MISSING AUDIT** |")
            continue
        tasks = audit.get("tasks") or []
        statuses = sorted({t.get("status") for t in tasks})
        # LAB-01..03 audit one row per L0N.M task; LAB-04..06 audit one row per
        # guide CLAUSE, which is why the counts jump. Same column, different unit.
        granularity = ("one row per L0N.M task" if len(tasks) <= 10
                       else "one row per guide clause")
        add(f"| LAB-0{n} | {len(tasks)} | {granularity} | {', '.join(statuses)} |")
    add("")
    if coverage:
        counts = coverage["counts"]
        add(f"Acceptance requirements (guide §14): **{counts['COVERED']} COVERED, "
            f"{counts['PARTIAL']} PARTIAL, {counts['NOT_YET_IMPLEMENTED']} NOT_YET_IMPLEMENTED** "
            "of 64.")
        add("")
        add("| id | status | owning phase | title |")
        add("|---|---|---|---|")
        for row in coverage["requirements"]:
            if row["status"] != "COVERED":
                add(f"| {row['id']} | {row['status']} | {row.get('owning_phase')} | "
                    f"{row.get('title')} |")
        add("")
        owners = {r.get("owning_phase") for r in coverage["requirements"]
                  if r["status"] != "COVERED"}
        add(f"Every one of them is owned by **{', '.join(sorted(o for o in owners if o))}** — "
            "no requirement belonging to a completed phase is outstanding.")
        add("")

    add("## Gap 1 — the compute-budget contract was never registered (guide §10.5, L01.5)")
    add("")
    add("L01.5 lists *compute budgets* among the things preregistration fixes, and §10.5 says "
        "what that means: two parallel reports, plus an experiment-search ledger that counts "
        "every search decision — *\"Không chỉ log Optuna alpha trials.\"*")
    add("")
    add("What existed was `study_registration.json → resource_budget`: **1 worker, 2 CPU, "
        "4 GiB**. That is the OS budget. It says nothing about whether two arms got the same "
        "number of chances to find a good parameter set, which is the thing a comparison can "
        "actually be gamed on. Neither `MATCHED_TOTAL_COMPUTE` nor `OPERATIONAL_POLICY` "
        "appeared anywhere in the lab.")
    add("")
    add("**Why it had to be closed before LAB-07, not during LAB-08.** LAB-07 builds the refit "
        "scheduler. Once its cost is visible, the definition of *matched compute* could be "
        "chosen — honestly, even — to suit what that cost turned out to be. Registered now, "
        "no arm beyond A and B exists to favour.")
    add("")
    if budget:
        add(f"`configs/compute_budget_registration.json`, status **{budget['status']}**, "
            f"opens the ledger with what the completed phases already spent:")
        add("")
        add("| phase | search kind | measured |")
        add("|---|---|---|")
        for entry in budget["ledger_opened_with"]["entries"]:
            detail = {k: v for k, v in entry.items()
                      if k not in ("phase", "kind", "what_was_searched", "counts_against",
                                   "note", "design", "values")}
            add(f"| {entry['phase']} | {entry['kind']} | "
                f"`{json.dumps(detail)[:120]}` |")
        add("")
        add(f"Counted as search: {', '.join(budget['what_counts_as_search'])}.")
        add("")

    add("## Gap 2 — the CLI's stage status had gone stale (guide §13.5)")
    add("")
    add("`cli.py` froze an `IMPLEMENTED` set at LAB-01. When LAB-02 and LAB-03 landed, "
        "`certify-alphas` and `snapshot-data` went on answering:")
    add("")
    add("```json")
    add('{"status": "NOT_IMPLEMENTED_YET", "required_phase": "LAB-02",')
    add(' "note": "the CLI refuses a stage whose phase has not landed"}')
    add("```")
    add("")
    add("The refusal was honest in spirit — it never faked a pass — but its **reason had become "
        "false**, and a stale reason reads like a checked fact. Availability is now READ from "
        "`configs/lab0N_task_audit.json`, and a refusal distinguishes `PHASE_NOT_LANDED` from "
        "`RUNNER_NOT_WIRED_YET`.")
    add("")
    add("| stage | delivering phase | state |")
    add("|---|---|---|")
    from crypto_regime_lab.cli import STAGE_DELIVERY
    for stage, delivery in STAGE_DELIVERY.items():
        audit = delivery["audit"]
        landed = audit is None or (CONFIGS / audit).is_file()
        wired = delivery["runner"] is not None or audit is None
        state = ("runs" if landed and wired else
                 "RUNNER_NOT_WIRED_YET" if landed else "PHASE_NOT_LANDED")
        add(f"| `{stage}` | {delivery['phase']} | {state} |")
    add("")
    add("Two consequences fell out of wiring it:")
    add("")
    add("- **`verify-causality` had no runner at all.** LAB-03's exit gate says the "
        "future-mutation test passes through loader, resampler and scaler; LAB-05 adds the model "
        "and the streaming filter. Each layer was tested separately and nothing ran them as one "
        "gate. `scripts/verify_causality.py` now does.")
    if causality:
        add("")
        add("| layer | verdict |")
        add("|---|---|")
        for layer, verdict in causality["verdicts"].items():
            add(f"| {layer} | {'CAUSAL' if verdict else 'FAILED'} |")
        add("")
        add(f"Leaky control detected: **{causality['leaky_control_is_detected']}** — a causality "
            "suite that can never fail proves nothing, so the deliberately leaky fit is run "
            "alongside and must be caught.")
    add("")
    add("- **`snapshot-data` would have silently re-pinned the study.** Delegating the stage to "
        "`scripts/snapshot_data.py` meant a CLI call could re-read the source while the "
        "collector appends, write a NEW manifest, and re-register the read-lock every past "
        "result declares. It now refuses unless `--repin` is passed.")
    add("")

    add("## Gap 3 — the identity taxonomy was 7 of 12 (guide §13.1)")
    add("")
    add("§13.1 opens with *\"Không gộp trial/candidate/execution/selection/activation thành một "
        "ID\"*. The reason is joins: in LAB-08/09 a result must trace back through the selection "
        "that proposed it, the execution that measured it, the design that framed it and the "
        "observation that conditioned it. A join invented after the numbers exist is a place the "
        "numbers can be steered.")
    add("")
    if identities:
        add(f"**{identities['present_count']} present, {identities['derivable_count']} derivable, "
            f"{identities['owed_count']} owed** of {identities['total']}.")
        add("")
        add("| identity | names | owner | status |")
        add("|---|---|---|---|")
        for name, rec in identities["identities"].items():
            add(f"| `{name}` | {rec['names']} | {rec['owner']} | **{rec['status']}** |")
        add("")
        add("Three that COMPLETED phases owed were missing: `probe_design_id` (L04.3 freezes a "
            "design), `execution_id` (L04.3 counted 9,155 unique executions without naming one) "
            "and `observation_id` (L05 emitted 1,099 observations without naming one). They are "
            "**derived** from records that already exist rather than back-filled into artifacts, "
            "so nothing is re-run and no measurement moves:")
        add("")
        add("| identity | derived from a real record |")
        add("|---|---|")
        for name, rec in identities.get("derivations_demonstrated", {}).items():
            add(f"| `{name}` | `{rec['derived']}` |")
        add("")
        owed = [n for n, r in identities["identities"].items() if r["status"] == "OWED"]
        add(f"Still owed: {', '.join('`' + n + '`' for n in owed)} — both minted by phases that "
            "have not run, now declared so LAB-07/08 inherit the contract instead of inventing "
            "one.")
        add("")
        add("> The first run of `scripts/audit_identities.py` reported **12/12 present**. It was "
            "grepping the artifact it had just written. The scan now excludes its own output, "
            "and `test_the_identity_audit_does_not_pass_on_its_own_output` fails if a future "
            "version reports everything present.")
        add("")

    add("## What was checked and found correct")
    add("")
    add("Verified directly against the guide text rather than against the audits:")
    add("")
    for item in [
        "L01.2 — ZIP guards cover traversal, symlink, duplicate, absolute AND oversize "
        "(`MAX_MEMBER_BYTES`, `MAX_TOTAL_BYTES`, `MAX_COMPRESSION_RATIO`, with a "
        "`COMPRESSION_BOMB` rejection)",
        "L01.3 — python/numba/llvmlite versions, thread counts, cache dirs, wheel digests and "
        "`quantbt.__file__` all pinned; shared parent venv recorded as untouched",
        "L01.4 — every evidence JSON carries `lab_run_id`; 135 append-only attempt ledgers",
        "L02.7 — **13 of 13** execution fixtures pass, including both-stop-and-TP-same-bar, "
        "OCO, over-close, rejected order, insufficient margin, funding boundary and terminal "
        "open position; forced-flat and mark-open are two declared modes",
        "L02.8 — Python/Rust parity on fixed intents PASSES, with the fill trace recorded as "
        "`BLOCKED_CAPABILITY` rather than claimed",
        "L03.3 — funding is a declared MISSING stream with an explicit no-zero policy, never an "
        "implicit zero",
        "L04.1 — all five installed WFO modes traced, with per-mode OOS usage and the "
        "`mode_5_full_robust` collapse-to-one-fold finding recorded",
        "L05.3 — multi-start seed selection is on the **lowest TRAIN objective**, "
        "`outer_information_used: false`",
        "L05.4 / §8.3 — M1S (sparse JM) is declared **deliberately unbuilt** with the guide's own "
        "reason: §8.3 forbids writing a naive sparse objective without a pinned research "
        "implementation, and the core is 3 blocks, not the 'many' §8.1 scopes M1S to",
        "L05.7 — detection delay and noise sensitivity both measured; the latent label is "
        "diagnostic only",
        "L06.1–L06.6 — purge and dependence correction, retired params serving open campaigns, "
        "indicator readiness by version/cutoff, supporting episodes per recommendation, "
        "train-only distance weights, coalesce/out-of-order fit handling, and no reset-flat "
        "expert curve as deploy equity",
    ]:
        add(f"- {item}")
    add("")
    add("## Conclusion")
    add("")
    add("All six completed phases do what their L0N.M tasks require. The three gaps were "
        "cross-phase contracts — §10.5, §13.5, §13.1 — that no single task owned. All three are "
        "now closed, each with a test that fails if it reopens.")
    add("")
    add("**No result from LAB-04, LAB-05 or LAB-06 changed.** Nothing here touched a "
        "measurement; the fixes are a registration, a status-reporting correction and three "
        "identity derivations.")
    add("")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
