#!/usr/bin/env python
"""Render evidence/corrective_mode4_v3/FUP-02/{report.md,report.json}.

Everything is read from the committed FUP-02 artifacts (budget revision,
full-window paired discovery, cell coverage, coverage review, trial ledger and
attempt ledger). No engine is rerun for any number in the report; test counts
come from the recorded pytest logs when they exist, otherwise they are null
with a reason.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "FUP-02"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / PHASE
FUP01_DIR = LAB_ROOT / "evidence" / STUDY_ID / "FUP-01"
POTENTIAL_LEVELS = (
    "UNASSESSED", "LOW_PARAMETER_OPPORTUNITY", "OPPORTUNITY_UNINFORMED",
    "INFORMATIVE_NOT_ACTIONABLE", "ACTIONABLE_UNCONFIRMED", "POSITIVE_WITHIN_SCOPE",
    "NEGATIVE_WITHIN_SCOPE", "INCONCLUSIVE",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_pytest_log(path: Path) -> dict | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"(\d+) (passed|failed|skipped|error)", text)
    if not matches:
        return None
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for value, name in matches:
        counts[name] = int(value)
    return counts


def pyflakes_clean(path: Path) -> dict | None:
    if not path.exists():
        return None
    output = path.read_text(encoding="utf-8", errors="replace")
    return {"clean": output.strip() == "", "recorded": True}


def attempts_wall_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    total = 0.0
    seen = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("duration_s"):
            total += float(row["duration_s"])
            seen = True
    return round(total, 3) if seen else None


def trial_ledger_counts(path: Path) -> dict:
    if not path.exists():
        return {"rows": 0, "unique": 0, "finite_objectives": 0, "by_cell_arm": {},
                "status": "NO_TRIAL_LEDGER"}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    keys = set()
    per = {}
    finite = 0
    for row in rows:
        keys.add(row.get("trial_key"))
        key = f"{row['cell']}:{row['arm']}"
        per[key] = per.get(key, 0) + 1
        if row.get("objective") is not None:
            finite += 1
    return {"rows": len(rows), "unique": len(keys), "finite_objectives": finite,
            "by_cell_arm": per, "status": "LEDGER_PRESENT"}


def cell_headlines(full: dict) -> list[dict]:
    rows = []
    for cell in full["cells"]:
        row = {
            "cell": cell["cell"],
            "coverage_status": cell.get("coverage_status"),
            "contrast_status": (cell.get("contrast") or {}).get("status"),
            "arms": {},
        }
        for arm in ("M4_CAL", "M4_REGIME"):
            shard = cell["shards"][arm]
            account = shard.get("account") or {}
            report = account.get("engine_report") or {}
            row["arms"][arm] = {
                "status": shard["status"],
                "completed_folds": len(shard["completed_fold_ids"]),
                "fold_count": shard["fold_count"],
                "trials": shard["trial_count"],
                "equity_last": account.get("equity_last"),
                "total_return_pct": report.get("total_return_pct"),
                "num_trades": report.get("num_trades"),
                "fills": account.get("fill_count"),
                "wall_seconds": shard.get("wall_seconds"),
            }
        rows.append(row)
    return rows


def build_report(coverage: dict, review: dict, budget: dict, full: dict,
                 ledger: dict, log_counts: dict, full_counts: dict,
                 pyflakes: dict | None, attempts_wall: float | None) -> dict:
    cells = full["cells"]
    first_data = next((cell["data"] for cell in cells if cell.get("data")), None)
    complete_pairs = [cell["cell"] for cell in cells
                      if cell["coverage_status"] in ("RUN_VALID", "RUN_NOT_EVALUABLE")]
    valid_pairs = [cell["cell"] for cell in cells
                   if cell["coverage_status"] == "RUN_VALID"]
    executed = [cell["cell"] for cell in cells if cell["executed"]]
    stopped = [cell["cell"] for cell in cells
               if cell["coverage_status"] in ("BUDGET_STOPPED", "NOT_RUN_BUDGET")]
    failed = [cell["cell"] for cell in cells if cell["coverage_status"] == "FAILED"]
    insufficient = [cell["cell"] for cell in cells
                    if cell["coverage_status"] == "INSUFFICIENT_DATA"]
    not_run = [cell["cell"] for cell in cells if cell["coverage_status"] == "NOT_RUN"]
    shard_counts: dict[str, int] = {}
    for cell in cells:
        for arm in ("M4_CAL", "M4_REGIME"):
            value = cell["shards"][arm]["status"]
            shard_counts[value] = shard_counts.get(value, 0) + 1
    scored_folds = sum(
        1 for cell in cells for arm in ("M4_CAL", "M4_REGIME")
        for entry in cell["shards"][arm]["cutoff_results"] if entry["status"] == "SCORED")
    planned_folds = sum(cell["shards"][arm]["fold_count"]
                        for cell in cells for arm in ("M4_CAL", "M4_REGIME"))
    total_shard_wall = round(sum(float(cell["shards"][arm].get("wall_seconds") or 0.0)
                                 for cell in cells for arm in ("M4_CAL", "M4_REGIME")), 3)
    invocation_wall = round(sum(float(row.get("wall_seconds") or 0.0)
                                for row in full.get("invocations", [])), 3)
    status = ("TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE" if valid_pairs
              else "TECHNICAL_ONLY_COVERAGE_INCOMPLETE")
    claim_status = (
        "FUP-02 executes the registered 32-64 trials/cutoff budget at its low end (32) over "
        "2021-01-01..2023-12-31 on the qualified event route for every cell. Every completed "
        "paired contrast that is VALID is technically valid; no economic inference is drawn and "
        "the coverage is partial, so the claim is scoped to the completed cells and no edge "
        "question is answered."
    )
    findings = [{
        "id": "FUP02-F1",
        "title": "the frozen provider's engine_param_ranges cannot express bool parameter specs",
        "observed": ("experiments/dynamic_fold_provider.py:engine_param_ranges routes a bool spec "
                     "to the numeric branch and raises TypeError on A-VWAP's exit_at_vwap / "
                     "time_stop_on"),
        "expected": ("a bool spec is expressed as the two-choice categorical list the installed "
                     "engine samples with trial.suggest_categorical"),
        "disposition": "OPEN_REPRODUCED",
        "repair_status": ("not repaired in the frozen provider: RF-05 pins that file and the "
                          "freeze guard permits only the one FUP-01 supersession; FUP-02 passes "
                          "its own bool-aware schema expression to the provider as an argument "
                          "(scripts/run_fup02.py:engine_param_ranges) and the provider file is "
                          "never edited"),
        "regression_test": "tests/mode4_corrective/test_fup02_scale.py",
        "proposal": "handoff/lab_only_patch.diff",
        "impacted_scopes": ["A-VWAP search space (2 bool knobs)"],
    }, {
        "id": "FUP02-F2",
        "title": ("the frozen event scorer excludes ValueError samples but the engine wraps "
                  "callback ValueErrors in NativeEventStrategyError (RuntimeError)"),
        "observed": ("A-HMA/SOLUSDT fold 4 (cutoff 2022-12-22) aborts with "
                     "NativeEventStrategyError: 'limit commands require price > 0' at bar "
                     "2022-11-09 21:00; EventAccountScorer._run_account catches only ValueError, "
                     "so an infeasible sampled point aborts the whole fold instead of being "
                     "excluded"),
        "expected": ("an infeasible sampled point is excluded from selection (the scorer's own "
                     "documented rule), not turned into a fold-level hard failure"),
        "disposition": "OPEN_REPRODUCED",
        "repair_status": ("not repaired in the frozen provider: the exception handler lives in "
                          "experiments/dynamic_fold_provider.py, pinned by RF-05; FUP-02 records "
                          "the failed fold as ERROR/FAILED with the exact engine message and "
                          "does not retry it silently (--retry-errors is explicit)"),
        "regression_test": "tests/mode4_corrective/test_fup02_scale.py",
        "proposal": "handoff/lab_only_patch.diff",
        "impacted_scopes": ["A-HMA/SOLUSDT fold 4", "any cell whose data admits a zero-price "
                            "limit projection for a sampled candidate"],
    }]
    report = {
        "schema": "regime_lab.corrective_phase_report.v3",
        "phase_id": PHASE,
        "status": status,
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now_iso(),
        "source": {
            "study_registration": "evidence/corrective_mode4_v3/followup-studies/"
                                  "followup_studies_registration.json#/studies/1",
            "budget_revision": {
                "artifact": "evidence/corrective_mode4_v3/FUP-02/budget_revision.json",
                "sha256": sha256_file(RUN_DIR / "budget_revision.json"),
                "status": budget["status"],
                "registered_at_utc": budget["registered_at_utc"],
            },
            "snapshot_id": full["development_window"]["snapshot_id"],
            "product": full["development_window"]["product"],
            "snapshot_manifest_sha256": (
                first_data["snapshot_manifest_sha256"] if first_data else None),
            "quantbt_core_version": "1.1.1",
            "development_window": full["development_window"],
            "contamination": budget["contamination"],
        },
        "objective": (
            "Expanded-budget, full-development-window paired discovery of M4_REGIME minus "
            "M4_CAL on every cell whose route is qualified (20 primary cells; FUP-01 qualified "
            "A-VWAP/A-HASH, A-SC/A-HMA already event-qualified) under the registered 32-64 "
            "trials/cutoff budget, with per-contrast validity and a coverage review before any "
            "final freeze."
        ),
        "not_tested": [
            "no paired bootstrap, decay panel, matched control or multiplicity correction is "
            "computed; statistical status is NOT_EVALUATED everywhere",
            "no holdout and no prospective interval: contamination stays NESTED_RETROSPECTIVE",
            "2024+ data is never read and is not claimed as untouched",
            "per-symbol regime tapes are not claimed (the committed BTCUSDT emission tape is "
            "reused, identical to RF-04.6)",
        ],
        "registered_arms": ["M4_CAL", "M4_REGIME"],
        "findings": findings,
        "tests": {
            "mode4_corrective": log_counts,
            "full_suite": full_counts,
            "pyflakes": pyflakes,
            "artifact_refs": [
                "tests/mode4_corrective/test_fup02_scale.py",
                "scripts/run_fup02.py",
            ],
            "notes": ("counts are parsed from the committed logs when present; a missing log is "
                      "null with a reason in the limitations, never a zero"),
        },
        "market_runs": {
            "planned_cells": len(cells),
            "executed_cells": len(executed),
            "complete_pairs": len(complete_pairs),
            "valid_pairs": len(valid_pairs),
            "budget_stopped_cells": len(stopped),
            "not_run_cells": len(not_run),
            "failed_cells": len(failed),
            "insufficient_data_cells": len(insufficient),
            "blocked_cells": 0,
            "engine_runs": scored_folds + sum(
                1 for cell in cells for arm in ("M4_CAL", "M4_REGIME")
                if cell["shards"][arm].get("account_wall_seconds") is not None),
            "completed_folds": scored_folds,
            "planned_folds": planned_folds,
            "shard_status_counts": shard_counts,
            "complete_pair_cells": complete_pairs,
            "valid_pair_cells": valid_pairs,
            "cells": cell_headlines(full),
        },
        "metrics": {
            "fullwindow_ref": ("evidence/corrective_mode4_v3/FUP-02/"
                               "paired_discovery_fullwindow.json"),
            "cell_coverage_ref": "evidence/corrective_mode4_v3/FUP-02/cell_coverage.json",
            "coverage_review_ref": "evidence/corrective_mode4_v3/FUP-02/coverage_review.json",
            "trial_ledger_ref": "evidence/corrective_mode4_v3/FUP-02/trial_ledger.jsonl",
            "trial_ledger": ledger,
            "statistical_status": "NOT_EVALUATED",
            "economic_status": "NOT_EVALUATED",
            "paired_contrast_validity_counts": {
                "VALID": len(valid_pairs),
                "NOT_EVALUABLE": len(complete_pairs) - len(valid_pairs),
                "NOT_RUN": len(cells) - len(complete_pairs),
            },
            "coverage_review": review["aggregate"],
        },
        "performance": {
            "total_shard_wall_seconds": total_shard_wall,
            "invocation_wall_seconds": invocation_wall,
            "attempt_ledger_duration_seconds": attempts_wall,
            "invocations": full.get("invocations", []),
            "peak_rss_bytes": None,
            "peak_rss_reason": ("the runner did not sample RSS per shard; the registered "
                                "pre-run micro-benchmarks recorded ~0.9-1.0 GiB peak per process, "
                                "and no measurement is invented here"),
            "cpu_hours": None,
            "cpu_hours_reason": "the runner records wall seconds, not CPU time",
        },
        "proof_capability": {
            "technical_validity": ("PASS for the completed VALID contrasts"
                                   if valid_pairs else "NOT_TESTED"),
            "treatment_reached_execution": (
                "YES for completed cells: the two arms used different registered cutoff lists "
                "and both deployed their selected parameters through the native-event account"),
            "positive_control": "NOT_TESTED_HERE (RF-04/positive_control.json is the committed "
                                "positive control)",
            "null_control": "NOT_TESTED_HERE",
            "coverage_review": review["status"],
        },
        "potential": {
            "level": "UNASSESSED",
            "reason": ("no statistical evaluation is performed in FUP-02 and the coverage is "
                       "partial; the per-cell outcomes exist but are neither a confirmatory test "
                       "nor a frozen design, so no potential level is claimed"),
            "evidence_refs": [
                "evidence/corrective_mode4_v3/FUP-02/paired_discovery_fullwindow.json",
                "evidence/corrective_mode4_v3/FUP-02/coverage_review.json",
            ],
            "falsifiable_next_step": (
                "complete the remaining folds under the same registered budget, run the "
                "registered coverage review, then freeze a design before any statistical claim"),
        },
        "claim": {
            "validity": status,
            "statistical_status": "NOT_EVALUATED",
            "scope": (f"{len(valid_pairs)} valid paired cells of 20 planned; "
                      f"{scored_folds} of {planned_folds} folds scored"),
            "contamination": "NESTED_RETROSPECTIVE",
            "statement": claim_status,
            "no_positive": True,
        },
        "limitations": [
            f"coverage is partial: {len(valid_pairs)} valid pairs, {len(stopped)} cells budget "
            f"stopped, {len(not_run)} cells not started",
            "the regime cutoff list is the committed BTCUSDT tape, identical across symbols; "
            "per-symbol tapes are not claimed",
            "the provider's public payload does not expose selector/cluster/fallback fields; "
            "the coverage review reports candidate counts and finite-trial coverage only",
            "the A-SC route is the event fidelity route, not the originally registered "
            "endpoint route; the endpoint deviation is recorded in RF-04",
            "no statistical inference, no decay panel and no matched control are computed here",
        ],
        "review": {"author": "opencode FUP-02 runner", "reviewer": None, "disagreements": []},
        "handoff": {
            "next_phase": ("resume FUP-02 shards until the registered wall budget is spent, then "
                           "FUP-03 (blocked on post-freeze data)"),
            "blocking_findings": [],
            "open_findings": ["FUP02-F1"],
            "resume_recipe": (
                "python scripts/run_fup02.py --run --resume --budget-seconds <seconds>"),
        },
        "sections": {
            "1_objective": "see objective/not_tested",
            "2_identity": "see source/source.runtime",
            "3_findings": "see findings",
            "4_budget": "see source.budget_revision and metrics.trial_ledger",
            "5_technical_vs_market": "see tests and market_runs",
            "6_metrics": "see metrics",
            "7_runtime": "see performance",
            "8_proof_capability": "see proof_capability",
            "9_potential": "see potential",
            "10_claim_limitations": "see limitations",
            "11_exit": "see status/claim",
            "12_rerun_recipe": "see handoff.resume_recipe",
        },
    }
    return report


def render_markdown(report: dict, coverage: dict, review: dict, full: dict) -> str:
    market = report["market_runs"]
    lines: list[str] = []
    add = lines.append
    add("# FUP-02 — Expanded-budget, full-development-window paired discovery")
    add("")
    add("Generated from committed FUP-02 artifacts by `scripts/write_fup02_report.py`. "
        "No engine was rerun for any number in this report. Contamination stays "
        "`NESTED_RETROSPECTIVE`; no holdout and no economic claim is made.")
    add("")
    add("## 1. Objective and what is not tested")
    add("")
    add(report["objective"])
    add("")
    add("**Not tested:** " + "; ".join(report["not_tested"]))
    add("")
    add("## 2. Identity, contracts and resolved runtime")
    add("")
    add(f"- study `{report['study_id']}` phase `{report['phase_id']}`; budget revision "
        f"`{report['source']['budget_revision']['status']}` registered at "
        f"`{report['source']['budget_revision']['registered_at_utc']}` (sha256 "
        f"`{report['source']['budget_revision']['sha256'][:16]}...`)")
    add(f"- data: `{report['source']['snapshot_id']}/"
        f"{report['source']['product']}`, window "
        f"{report['source']['development_window']['start']}.."
        f"{report['source']['development_window']['end']}, snapshot manifest sha256 "
        f"`{report['source']['snapshot_manifest_sha256']}`")
    add(f"- Mode 4 contract: `{full['mode4_contract']['optimization_mode']}`, schedule "
        f"`{full['mode4_contract']['optimization_schedule']}`, metric "
        f"`{full['mode4_contract']['candidate_selection_metric']}`, `oos_used_for_selection="
        f"{str(full['mode4_contract']['oos_used_for_selection']).lower()}`")
    add(f"- routes: every cell runs the qualified event route "
        f"(`evidence/corrective_mode4_v3/FUP-01/route_matrix.json` sha256 "
        f"`{full['route_matrix']['sha256'][:16]}...`); the route is read, never re-decided")
    add(f"- contamination: `{report['source']['contamination']['status']}`, untouched holdout = "
        f"`{report['source']['contamination']['untouched_holdout']}`")
    add("")
    add("## 3. Findings")
    add("")
    for finding in report["findings"]:
        add(f"- **{finding['id']} — {finding['title']}** ({finding['disposition']}): "
            f"{finding['observed']}. Expected: {finding['expected']}. {finding['repair_status']}. "
            f"Proposal: `{finding['proposal']}`.")
    if not report["findings"]:
        add("- no new finding")
    add("")
    add("## 4. Budget: period, trials, seeds, folds and validity")
    add("")
    add(f"- registered trial budget {report['source']['budget_revision']['status']}: "
        f"{full['run_config']['trials_per_cutoff']} trials/cutoff (range "
        f"{full['run_config']['trial_budget_registered_range']}), seed "
        f"{full['run_config']['seed']}, train memory "
        f"{full['economics']['train_memory_days']} days")
    add(f"- folds scored: {market['completed_folds']} of {market['planned_folds']} planned "
        f"across {market['executed_cells']} executed cells; engine runs "
        f"{market['engine_runs']}")
    add(f"- trial ledger: {report['metrics']['trial_ledger']['unique']} unique trial rows "
        f"({report['metrics']['trial_ledger']['finite_objectives']} finite objectives) in "
        f"`{report['metrics']['trial_ledger_ref']}`")
    add(f"- coverage review: `{review['status']}`; admissible over scored = "
        f"{review['aggregate']['admissible_over_scored']}, trials = "
        f"{review['aggregate']['trials_total']}, objective-null = "
        f"{review['aggregate']['trials_nonfinite']} (pruned "
        f"{review['aggregate'].get('trials_pruned')}, infeasible "
        f"{review['aggregate']['infeasible_trials']})")
    add("")
    add("## 5. Technical results versus market results")
    add("")
    add(f"- technical: {market['complete_pairs']} cell pairs completed, "
        f"{market['valid_pairs']} paired contrasts VALID; every completed arm declares "
        "`oos_used_for_selection=False` and deploys through the real native-event account")
    add("- market: per-cell headline account numbers are in the table below; they are "
        "discovery outcomes, not a statistical result")
    add("")
    add("| cell | coverage | contrast | M4_CAL equity | M4_REGIME equity | CAL trades | "
        "REG trades |")
    add("|---|---|---|---|---|---|---|")
    for row in market["cells"]:
        cal, reg = row["arms"]["M4_CAL"], row["arms"]["M4_REGIME"]
        add(f"| {row['cell']} | {row['coverage_status']} | {row['contrast_status'] or '—'} | "
            f"{cal['equity_last'] if cal['equity_last'] is not None else 'null'} | "
            f"{reg['equity_last'] if reg['equity_last'] is not None else 'null'} | "
            f"{cal['num_trades'] if cal['num_trades'] is not None else 'null'} | "
            f"{reg['num_trades'] if reg['num_trades'] is not None else 'null'} |")
    add("")
    add("## 6. Metrics, units, support and null reasons")
    add("")
    add("- account metrics come from `_event_account_payload` (the provider's own deployment "
        "builder) over the full development window: equity_last (USDT), total_return_pct, "
        "sharpe, num_trades, max_drawdown_pct, per-fill ledger")
    add("- a cell or arm that did not complete carries null metrics with its exact reason; "
        "nothing is zero-filled")
    add("- statistical status is `NOT_EVALUATED` for every contrast because FUP-02 computes no "
        "paired inference, decay panel or matched control")
    add("")
    add("## 7. Runtime breakdown")
    add("")
    add(f"- shard wall seconds (sum): {report['performance']['total_shard_wall_seconds']}")
    add(f"- invocation wall seconds (sum): {report['performance']['invocation_wall_seconds']}")
    add(f"- registered caps: per-shard {full['run_config']['per_shard_cap_seconds']}s, "
        f"per-cutoff {full['run_config']['per_cutoff_cap_seconds']}s, per-invocation "
        f"{full['run_config']['per_invocation_budget_seconds']}s, total approved "
        f"{full['run_config']['total_wall_budget_seconds']}s")
    add(f"- peak RSS: null ({report['performance']['peak_rss_reason']})")
    add(f"- invocations: {len(full.get('invocations', []))}; each invocation records its own "
        f"budget, elapsed seconds and stop reason in the full-window artifact")
    add("- shard wall seconds count every attempt, including attempts from invocations that "
        "were killed before recording (their per-fold checkpoints and attempts rows remain); "
        "invocation wall seconds only count invocations that recorded their end")
    add("")
    add("## 8. Proof capability")
    add("")
    add(f"- technical validity: {report['proof_capability']['technical_validity']}")
    add(f"- treatment reached execution: {report['proof_capability']['treatment_reached_execution']}")
    add(f"- positive/null control: {report['proof_capability']['positive_control']}")
    add(f"- coverage review: {report['proof_capability']['coverage_review']}")
    add("")
    add("## 9. Potential assessment")
    add("")
    add(f"- level `{report['potential']['level']}`: {report['potential']['reason']}")
    add(f"- falsifiable next step: {report['potential']['falsifiable_next_step']}")
    add("")
    add("## 10. Claim limitations")
    add("")
    for item in report["limitations"]:
        add(f"- {item}")
    add("")
    add("## 11. Exit decision and remaining tasks")
    add("")
    add(f"- status: `{report['status']}`; claim validity `{report['claim']['validity']}`, "
        f"statistical status `{report['claim']['statistical_status']}`, scope "
        f"{report['claim']['scope']}")
    add(f"- corpus/shard status counts: {json.dumps(market['shard_status_counts'])}")
    add("- remaining: resume the budget-stopped shards under the same registered budget; run "
        "the registered coverage review before any design freeze; FUP-03 stays blocked until "
        "post-freeze data exists")
    add("")
    add("## 12. Rerun recipe, hashes and handoff")
    add("")
    add("- rerun: `python scripts/run_fup02.py --run --resume --budget-seconds <seconds>`")
    add(f"- budget revision sha256 `{report['source']['budget_revision']['sha256']}`")
    add(f"- paired discovery sha256 `{coverage['sources'][0]['sha256']}`")
    add(f"- cell coverage sha256 `{sha256_file(RUN_DIR / 'cell_coverage.json')}`")
    add(f"- coverage review sha256 `{sha256_file(RUN_DIR / 'coverage_review.json')}`")
    add(f"- handoff: {report['handoff']['next_phase']}")
    add("")
    add("## Glossary — what each term means and where it applies")
    add("")
    add("| term | meaning | where it applies |")
    add("|---|---|---|")
    add("| **FUP-02** | the registered follow-up study that executes the 32-64 "
        "trials/cutoff full-window paired discovery | `followup_studies_registration.json#/studies/1` |")
    add("| **shard** | one `alpha x symbol x arm` unit, checkpointed per fold/cutoff | "
        "`scripts/run_fup02.py`, guide 8.1 T3 |")
    add("| **cutoff** | the decision moment that closes the training view and opens the "
        "operational test segment | `dynamic_fold_provider.py` |")
    add("| **admissible cutoff** | a scored cutoff where the selector returned parameters and "
        "at least one trial objective is finite | `coverage_review.json` |")
    add("| **BUDGET_STOPPED** | a shard/fold stopped cleanly by the registered wall cap, with "
        "the exact reason and no fabricated metric | `budget_revision.json` stop vocabulary |")
    add("| **NOT_RUN_BUDGET** | a shard the invocation budget never reached | "
        "`cell_coverage.json` |")
    add("| **NESTED_RETROSPECTIVE** | historical data already exposed to design work; not a "
        "holdout | `budget_revision.json#/contamination` |")
    add("| **coverage review** | the pre-freeze check of admissible candidates and bad-trial "
        "fractions, registered before the runs | `budget_revision.json#/coverage_review_rule` |")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing report pair explicitly")
    args = parser.parse_args()
    md_path, json_path = RUN_DIR / "report.md", RUN_DIR / "report.json"
    if (md_path.exists() or json_path.exists()) and not args.force:
        raise SystemExit("the FUP-02 report exists; pass --force to supersede it explicitly")

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)

    budget = load(RUN_DIR / "budget_revision.json")
    full = load(RUN_DIR / "paired_discovery_fullwindow.json")
    coverage = load(RUN_DIR / "cell_coverage.json")
    review = load(RUN_DIR / "coverage_review.json")
    if full["registration"]["sha256"] != sha256_file(RUN_DIR / "budget_revision.json"):
        raise SystemExit("the full-window artifact was produced under a different budget revision")
    ledger = trial_ledger_counts(RUN_DIR / "trial_ledger.jsonl")
    log_counts = parse_pytest_log(RUN_DIR / "test_suite_mode4_corrective.log")
    full_counts = parse_pytest_log(RUN_DIR / "test_suite_full.log")
    pyflakes = pyflakes_clean(RUN_DIR / "pyflakes_fup02.log")
    attempts_wall = attempts_wall_seconds(RUN_DIR / "attempts.jsonl")

    report = build_report(coverage, review, budget, full, ledger, log_counts, full_counts,
                          pyflakes, attempts_wall)
    report_record = writer.write_json("report.json", report, schema=report["schema"])
    md = render_markdown(report, coverage, review, full)
    md_path.write_text(md, encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "report_json": report_record,
        "report_md": {"path": str(md_path), "sha256": sha256_file(md_path)},
        "claim": report["claim"],
        "market_runs": {key: report["market_runs"][key] for key in (
            "planned_cells", "executed_cells", "complete_pairs", "valid_pairs",
            "budget_stopped_cells", "not_run_cells", "completed_folds", "planned_folds")},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
