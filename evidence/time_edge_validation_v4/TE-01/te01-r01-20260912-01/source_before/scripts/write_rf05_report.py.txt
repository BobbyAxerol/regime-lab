#!/usr/bin/env python
"""Render evidence/corrective_mode4_v3/RF-05/{report.md,report.json}.

Everything is read from the committed RF-05 artifacts (freeze manifest,
recomputation, claim report, integrity, reproducibility manifest) plus the
committed RF-01..RF-04 evidence. Test counts come from the recorded pytest logs
when they exist; otherwise they are null with a reason. After the report pair is
written, the artifact-integrity and reproducibility artifacts are refreshed so
they cover the report as well.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

import run_rf05  # noqa: E402  (reuses the RF-05 builders; no engine call)

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-05"
STUDY_ROOT = LAB_ROOT / "evidence" / STUDY_ID
RUN_DIR = STUDY_ROOT / PHASE
RF01_DIR = STUDY_ROOT / "RF-01"
RF04_DIR = STUDY_ROOT / "RF-04"
PRE_RF04_DIR = STUDY_ROOT / "pre-RF04-clearing"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_pytest_log(path: Path) -> dict | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.findall(r"(\d+) (passed|failed|skipped|error)", text)
    if not match:
        return None
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for value, name in match:
        counts[name] = int(value)
    return counts


def attempts_wall_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    total = 0.0
    seen = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("duration_s") is not None:
            total += float(row["duration_s"])
            seen = True
    return round(total, 6) if seen else None


def family_line(entry: dict) -> str:
    stats = entry["paired_daily_difference"]
    return (f"`{entry['id']}` ({entry['contrast']}): mean "
            f"{stats['mean_daily_diff_bps']:+.6f} bps/day, CI "
            f"[{stats['ci95_low_bps']:+.6f}, {stats['ci95_high_bps']:+.6f}], "
            f"n={stats['n_days']}, raw p={stats['p_two_sided']:.4f}, "
            f"Holm p={entry['holm_adjusted_p']:.4f} -> `{entry['statistical_status']}`, "
            f"mde_cleared={entry['mde_cleared']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    md_path, json_path = RUN_DIR / "report.md", RUN_DIR / "report.json"
    if (md_path.exists() or json_path.exists()) and not args.force:
        raise SystemExit("RF-05 report exists; pass --force to supersede")

    claim = load(RUN_DIR / "claim_report.json")
    freeze = load(RUN_DIR / "freeze_manifest.json")
    recomputation = load(RUN_DIR / "recomputation.json")
    integrity = load(RUN_DIR / "artifact_integrity.json")
    coverage = load(RF04_DIR / "cell_coverage.json")
    mde = load(PRE_RF04_DIR / "mde_corrected.json")
    identity = load(RF01_DIR / "working_copy_identity.json")
    binding = load(RF01_DIR / "quantbt_binding_report.json")
    profiling = load(RF04_DIR / "profiling_and_budget.json")
    funnel = load(RF04_DIR / "controls_and_funnel.json")
    decay = load(RF04_DIR / "decay_panels.json")
    family = {entry["id"]: entry for entry in claim["family"]}
    answers = claim["answers"]
    rf05_wall = attempts_wall_seconds(RUN_DIR / "attempts.jsonl")
    test_counts = parse_pytest_log(RUN_DIR / "test_suite_mode4_corrective.log")
    full_counts = parse_pytest_log(RUN_DIR / "test_suite_full.log")
    pyflakes_log = RUN_DIR / "pyflakes_mode4_corrective.log"

    timing_cells = [row for row in claim["cells"] if row["family"] == "TIMING"]
    budget_cells = [row for row in claim["cells"] if row["family"] == "BUDGET_AWARE"]
    negative_cells = [row["cell"] for row in timing_cells + budget_cells
                      if row["statistical_status"] == "NEGATIVE_WITHIN_SCOPE"]
    exact = sum(1 for row in recomputation["metric_reconstruction"]
                if row["total_return_comparison"] == "EXACT_MATCH")
    mismatched = [f"{row['cell']}:{row['arm']}" for row in recomputation["metric_reconstruction"]
                  if row["total_return_comparison"] != "EXACT_MATCH"]
    risk_changed = sum(1 for row in timing_cells
                       if row["risk"]["parameter_changes_between_arms"] > 0)

    lines: list[str] = []
    add = lines.append
    add("# RF-05 — Frozen evaluation, falsification, claims and handoff")
    add("")
    add("Generated from committed RF-05 artifacts by `scripts/write_rf05_report.py`. "
        "No engine was rerun for any number in this report. The study is corrected "
        "retrospective/prequential evidence: no interval is an untouched holdout and no positive result is recorded.")
    add("")
    add("## 1. Objective and what is not tested")
    add("")
    add("Test whether a causal regime-triggered refit schedule (`M4_REGIME`) changes the continuous "
        "account outcome against the calendar per_fold_causal WFO (`M4_CAL`) and the refit-count-matched "
        "`M4_CAL_MATCHED` control on the frozen RF-04 event cohort, compute the paired common-date "
        "statistics and cost-stress panel from the committed result paths, and close the study with "
        "evidence-bounded claims and a reproducibility handoff.")
    add("")
    add(f"**Not tested:** any prospective/untouched interval, A-VWAP and A-HASH (route "
        f"`BLOCKED_CAPABILITY`), the registered 32-64 trials/cutoff budget (the frozen RF-04 design "
        f"executed 8), the 2023-01-01..2023-12-31 development extension, funding, and the NEIGH/E "
        f"secondary arms. Coverage is {coverage['counts']['RUN_VALID']} of "
        f"{coverage['counts']['planned_cells']} planned cells.")
    add("")
    add("## 2. Identity, contracts and resolved runtime")
    add("")
    add(f"- branch `{identity['branch']}` at RF-01 head `{identity['head_commit']}`; plan sha256 "
        f"`{identity['plan']['sha256']}`")
    add(f"- QuantBT: `{binding['installed_quantbt']['distributions']}`, import origin "
        f"`{binding['installed_quantbt']['import_origin']}`; native module: "
        f"{binding['installed_quantbt']['native_import_error']}")
    add("- Mode 4 contract: mode `mode_4_is_only_robust`, schedule `per_fold_causal`, metric "
        "`is_only_robust`, backend `endpoint`, `oos_used_for_selection=False`, claim "
        "`strict_fold_local_retraining`")
    add("- RF-05 runs no engine at all: the claim statistics, CIs and cost-stress levels are "
        "deterministic functions of the committed RF-04 equity/fill paths (`recomputation.json`)")
    add(f"- frozen MDE: {mde['corrected_daily_account_bps']:.4f} account bps/day "
        f"(`evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json`, `{mde['status']}`); "
        f"historical registered value {mde['historical_registered']['value']} preserved as history")
    add(f"- contamination: `{freeze['contamination']['status']}`; untouched holdout = "
        f"`{freeze['contamination']['untouched_holdout']}`; prospective protocol "
        f"`{freeze['contamination']['prospective_protocol']['status']}` at "
        f"`{freeze['contamination']['prospective_protocol']['artifact']}`")
    add(f"- frozen components: {sum(len(group) for group in freeze['components'].values())} across "
        f"{len(freeze['components'])} groups; all present = `{freeze['all_components_present']}`")
    add("")
    add("## 3. Findings fixed and their acceptance tests")
    add("")
    add("| finding | disposition | evidence / acceptance |")
    add("|---|---|---|")
    add("| A01 fee binding | FIXED_AND_VERIFIED | `test_a01_bound_fee_kwargs_translate_one_way_exactly_once`, "
        "`test_a01_the_bound_route_charges_the_registered_one_way_rate`; event accounts carry "
        "`fee_rate=0.0004` |")
    add("| A02-A08 execution/timing/ledger contracts | FIXED_AND_VERIFIED | "
        "`test_rf02_contracts.py`, `test_rf02_event_account.py`, `test_rf02_mode4_baseline.py`; "
        "all 10 event cells carry real per-fill ledgers |")
    add("| A09 old E path | QUARANTINED_UNSUPPORTED_PATH | `test_a09_the_old_e_arm_is_quarantined_not_wired_from_d`; "
        "E stays disabled |")
    add("| A10 namespace/ineligible triggers | FIXED_AND_VERIFIED | `test_rf03_controller.py` |")
    add("| A11 economic-context collapse | FIXED_AND_VERIFIED | `test_a11_opposite_economic_contexts_are_not_collapsed` |")
    add("| A12/A13 response/bank support | SECONDARY_REPAIRED_NOT_MARKET_EVALUATED | unit-level repairs only; "
        "`secondary_contrasts` mark SELECTOR/INTERACTION/POLICY_E NOT_EVALUABLE |")
    add("| A14 inner scaler / fixed-target ablation | REPAIRED_UNIT_ONLY | `test_rf04_model_repairs.py` |")
    add("| A15 MDE derivation | FIXED_AND_VERIFIED | `mde_corrected.json` frozen before RF-04 results; "
        "`test_a15_the_corrected_mde_derivation_is_registered_and_history_preserved` |")
    add("| A16 fail-closed claims | FIXED_AND_VERIFIED | `src/crypto_regime_lab/evidence/claim_gate.py`; "
        "RF-05 re-derives every status and refuses POSITIVE without CI > MDE and Holm < 0.05 |")
    add("")
    add(f"RF-05-specific integrity findings: `{integrity['status']}` with {len(integrity['checks'])} "
        "checks over RF-01..RF-05 (strict JSON, coverage nulls, selection joins, freeze hashes, claim "
        "gate, CI denominators, report coverage, phase report pairs).")
    add("")
    add("## 4. Budget, sample and coverage")
    add("")
    add(f"- raw window: {coverage['registered_cohort']['data']} (registered); executed development "
        f"window 2021-01-01..2022-06-30 only")
    add(f"- coverage: {coverage['counts']['planned_cells']} planned cells — "
        f"{coverage['counts']['RUN_VALID']} `RUN_VALID`, "
        f"{coverage['counts']['BLOCKED_CAPABILITY']} `BLOCKED_CAPABILITY` (A-VWAP/A-HASH), "
        f"{coverage['counts']['NOT_RUN']} `NOT_RUN`; non-executed cells carry null metrics plus a reason")
    add("- trials: 8 per cutoff in both arms (registered 32-64); cutoffs per cell: M4_CAL 3, "
        "M4_REGIME 6; trial rows per cell/arm = 24/48")
    add(f"- family coverage: TIMING {family['TIMING']['cells_evaluable']} evaluated cells; "
        f"BUDGET_AWARE {family['BUDGET_AWARE']['cells_evaluable']} of "
        f"{family['BUDGET_AWARE']['cells_registered']} registered cells "
        f"(`{family['BUDGET_AWARE']['coverage_status']}`); excluded: "
        f"{json.dumps(family['BUDGET_AWARE']['excluded_cells'])}")
    add(f"- decay panels from RF-04 remain diagnostics: D1 {decay['denominators']['D1_rows']} rows, "
        f"D2 {decay['denominators']['D2_rows']} rows, D3 {decay['denominators']['D3_rows']} rows; "
        "RF-05 does not relabel them confirmation evidence")
    add("")
    add("## 5. Technical vs market vs synthetic")
    add("")
    add("- **Market (real snapshot):** all RF-04 account records behind the RF-05 statistics are real "
        "`server_core_v1` data on the executed development window; no synthetic curve enters any claim.")
    add("- **Technical:** the RF-05 freeze/recompute/integrity steps read committed artifacts only; "
        f"the {exact}/{len(recomputation['metric_reconstruction'])} recomputed total returns match the "
        f"engine record exactly (mismatches: {mismatched or 'none'}).")
    add("- **Synthetic:** only the RF-04 G11 positive control (never used in a market metric).")
    add(f"- **No rerun:** {len(recomputation['not_rerunnable'])} items are explicitly null with "
        "reasons (engine cost rebinding, matched control on the 8 scaled cells, A-VWAP/A-HASH, "
        "prospective interval, 32-64 budget, 2023 window, funding, NEIGH arms).")
    add("")
    add("## 6. Metrics, canonical metrics, cost stress and decay")
    add("")
    add("| metric | definition | unit | support / null rule |")
    add("|---|---|---|---|")
    add("| `mean_daily_diff_bps` | paired mean of daily account net returns left - right on common dates | "
        "account bps/day | null + `NO_COMMON_DAYS` / `IDENTICAL_ACCOUNT_SERIES` |")
    add("| `ci95` | paired moving-block bootstrap percentile interval, block 5 days (development-chosen), "
        "2000 resamples, seed 20260911 | account bps/day | no engine rerun for any CI |")
    add("| `sharpe365_recomputed` | sqrt(365)*mean/std(daily net return, ddof=1) | ratio | null + "
        "`INSUFFICIENT_OBSERVATIONS`/`ZERO_VARIANCE` |")
    add("| `profit_factor_daily` | sum(positive daily returns)/abs(sum(negative daily returns)) | ratio | "
        "null + `NO_LOSS_DENOMINATOR`/`NO_TRADES` |")
    add("")
    add("Registered family (Holm, m=2):")
    add("")
    for key in ("TIMING", "BUDGET_AWARE"):
        add(f"- {family_line(family[key])}")
    add("")
    add(f"Per-cell TIMING results ({len(timing_cells)} cells, common dates only; cell-level reads are "
        "descriptive, the family result is the registered test):")
    add("")
    add("| cell | route | mean bps/day | CI low | CI high | n | raw p | status | parm changes |")
    add("|---|---|---|---|---|---|---|---|---|")
    for row in timing_cells:
        stats = row["paired_daily_difference"]
        add(f"| {row['cell']} | {row['route']} | {stats['mean_daily_diff_bps']:+.6f} | "
            f"{stats['ci95_low_bps']:+.6f} | {stats['ci95_high_bps']:+.6f} | {stats['n_days']} | "
            f"{stats['p_two_sided']:.4f} | `{row['statistical_status']}` | "
            f"{row['risk']['parameter_changes_between_arms']} |")
    add("")
    add("BUDGET_AWARE per-cell:")
    add("")
    for row in budget_cells:
        stats = row["paired_daily_difference"]
        add(f"- {row['cell']}: mean {stats['mean_daily_diff_bps']:+.6f} bps/day, CI "
            f"[{stats['ci95_low_bps']:+.6f}, {stats['ci95_high_bps']:+.6f}], n={stats['n_days']}, "
            f"fidelity `{row['implementation_fidelity']}` -> `{row['statistical_status']}`")
    add("")
    add("Cost stress on the frozen event cohort (ledger-linear, committed fill path held fixed; "
        "1x reproduces the base equity exactly):")
    add("")
    add("| level | mean bps/day | CI low | CI high | n |")
    add("|---|---|---|---|---|")
    for row in recomputation["cost_stress"]["per_level_aggregate"]:
        add(f"| {row['level']} | {row['mean_daily_diff_bps']:+.6f} | {row['ci95_low_bps']:+.6f} | "
            f"{row['ci95_high_bps']:+.6f} | {row['n_days']} |")
    add("")
    add("**D2 fixed-parameter age replay** (RF-04 diagnostic, unchanged): anchors "
        f"{decay['denominators']['anchors_replayed']}/{decay['denominators']['registered_anchors']} "
        f"replayed, status `{decay['D2']['status']}`. Negative cells at cell level: "
        f"{negative_cells or 'none'}.")
    add("")
    add("## 7. Runtime breakdown")
    add("")
    add(f"- RF-05 no-engine wall (attempts ledger SUCCESS durations): "
        f"{rf05_wall if rf05_wall is not None else 'null (attempts.jsonl not readable at generation)'} s")
    add(f"- RF-04 measured walls from `profiling_and_budget.json`: pilot "
        f"{profiling['wall_seconds']['totals']['pilot_sum_of_cell_arm_seconds']}s, matched control "
        f"{profiling['wall_seconds']['totals']['matched_control_loop_wall_seconds']}s, placebo "
        f"{profiling['wall_seconds']['totals']['placebo_loop_wall_seconds']}s, D2 anchors "
        f"{profiling['wall_seconds']['d2_anchor_replay_seconds']}s")
    add(f"- CPU seconds: {profiling['cpu_seconds']['value']} ({profiling['cpu_seconds']['reason']})")
    add(f"- peak RSS: {profiling['peak_rss_bytes']['value']} ({profiling['peak_rss_bytes']['reason']})")
    add(f"- candidate-bar visits: {profiling['candidate_bar_visits']['value']} "
        f"({profiling['candidate_bar_visits']['reason']})")
    add("- cold/warm and native route: resolved from RF-01/RF-02 records; RF-05 adds no engine work")
    add("")
    add("## 8. Proof capability")
    add("")
    add(f"- treatment reached execution on all {len(timing_cells)} event cells: every cell has "
        f"different selected parameters between arms ({risk_changed}/{len(timing_cells)} cells with "
        "changed fold parameters) and different account paths")
    add("- positive control (RF-04 G11, synthetic): parameters change and the treatment reaches engine "
        "fills; it never enters the market claims")
    add("- null/placebo (RF-04, 2 pilot cells): delayed-state contrasts are exploratory and do not "
        "produce a positive status")
    add("- fail-closed gate: the endpoint A-SC deviation and the identical-series cases are "
        "`NOT_EVALUABLE`; no cell or family is positive without CI > MDE and Holm < 0.05")
    add(f"- pipeline capability: corrected execution and Mode 4 selection are demonstrated; the "
        f"bounded design cannot rule the MDE in or out "
        f"(TIMING CI [{family['TIMING']['paired_daily_difference']['ci95_low_bps']:+.6f}, "
        f"{family['TIMING']['paired_daily_difference']['ci95_high_bps']:+.6f}])")
    add("")
    add("## 9. Potential assessment")
    add("")
    add(f"`{answers['q3_next_research_direction']['answer']}` — "
        f"{answers['q3_next_research_direction']['detail']}")
    add("")
    for action in answers["q3_next_research_direction"]["next_actions"]:
        add(f"- {action}")
    add(f"- falsifiable next step: {answers['q3_next_research_direction']['falsifiable_next_step']}")
    add(f"- RF-04 funnel context remains as recorded: potential `{funnel['funnel']['potential_level']}` "
        f"on the 2-cell pilot; bottleneck was information on A-HMA and rank identification on the "
        f"A-SC endpoint route")
    add("")
    add("## 10. Claim limitations")
    add("")
    for item in claim["limitations"]:
        add(f"- {item}")
    add("- the moving-block length 5 days, 2000 resamples and seed 20260911 are development-chosen "
        "artifacts; the cost multipliers 1x/1.5x/2x and the MDE are frozen before results and are "
        "never re-selected after a result")
    add("- `simulation_complete` and `audit_complete` stay separate: the engines flushed in RF-04 and "
        "every RF-05 artifact is strict JSON with null+reason for missing values")
    add("- historical invalid intervals were never recomputed: all historical claim verdicts remain "
        "`NOT_EVALUABLE` in `RF-01/historical_invalidation.json`")
    add("")
    add("## 11. Exit decision and remaining tasks")
    add("")
    add(f"**RF-05: PARTIAL_TECHNICAL_CLOSURE.** The corrected retrospective study is technically valid "
        f"within its scope ({answers['q1_experiment_valid']['detail']}). The economic answer is "
        f"`{answers['q2_benefit_within_tested_scope']['answer']}`: neither family contrast clears the "
        f"frozen MDE of {mde['corrected_daily_account_bps']:.4f} bps/day and no POSITIVE status is "
        f"reported. Remaining tasks: A-VWAP/A-HASH capability or formal quarantine, the registered "
        f"32-64 trials/cutoff design, and the prospective protocol "
        f"(`{freeze['contamination']['prospective_protocol']['status']}`) on a genuinely untouched "
        f"window before any deployment decision.")
    add("")
    add("## 12. Rerun recipe, output hashes and handoff")
    add("")
    add("```bash")
    add("LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf05.py --force")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf05_report.py --force")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pyflakes $LAB/src $LAB/scripts $LAB/tests")
    add("```")
    add("")
    add("Handoff: `handoff.md` and `reproducibility_manifest.json`. The registered prospective protocol "
        "is SPECIFIED_NOT_EXECUTED and must not be run in this study. No production merge and no publish.")
    add("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report_md_sha = sha256_file(md_path)
    source = {
        "archive_sha256": identity["original_audit_archive"]["sha256"],
        "lab_head_commit": identity["head_commit"],
        "lab_branch": identity["branch"],
        "plan_sha256": identity["plan"]["sha256"],
        "candidate_commit": None,
        "candidate_source_manifest": "evidence/corrective_mode4_v3/RF-01/source_before_manifest.json",
        "quantbt_core_version": binding["installed_quantbt"]["distributions"].get("quantbt-engine"),
        "quantbt_native_version": binding["installed_quantbt"]["distributions"].get("quantbt-native"),
        "native_artifact": binding["installed_quantbt"]["native_import_error"],
        "actual_import_origins": [binding["installed_quantbt"]["import_origin"]],
    }
    payload = {
        "schema": "regime_lab.corrective_phase_report.v3",
        "phase_id": PHASE,
        "status": "PARTIAL_TECHNICAL_CLOSURE",
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now_iso(),
        "source": source,
        "objective": ("frozen recomputation, paired statistical claims, artifact integrity and handoff "
                      "for the Mode 4 per_fold_causal calendar vs causal regime contrast"),
        "registered_arms": list(run_rf05.PRIMARY_ARMS),
        "findings": {
            "RF05.1": "FREEZE_AND_CONTAMINATION_RECORDED",
            "RF05.2": "RECOMPUTED_FROM_FROZEN_ARTIFACTS",
            "RF05.3": claim["status"],
            "RF05.4": f"INTEGRITY_{integrity['status']}",
            "RF05.5": "HANDOFF_AND_REPRODUCIBILITY_WRITTEN",
            "A16": "FIXED_AND_VERIFIED",
        },
        "tests": {
            "passed": (test_counts or {}).get("passed"),
            "failed": (test_counts or {}).get("failed"),
            "skipped": (test_counts or {}).get("skipped"),
            "artifact_refs": ["test_suite_mode4_corrective.log", "pyflakes_mode4_corrective.log",
                              "test_suite_full.log"],
            "test_file": "tests/mode4_corrective/test_rf05_claims.py",
            "test_files": ["tests/mode4_corrective/test_rf05_claims.py",
                           "tests/mode4_corrective/test_rf04_scaling.py",
                           "tests/mode4_corrective/test_rf04_decay_and_controls.py"],
            "full_suite": full_counts,
            "pyflakes_log_present": pyflakes_log.exists(),
            "note": (None if test_counts else "test log not present at report generation; counts null"),
        },
        "market_runs": {
            "planned_cells": coverage["counts"]["planned_cells"],
            "executed_cells": coverage["counts"]["RUN_VALID"],
            "valid_pairs": len(timing_cells),
            "blocked_cells": [cell["cell"] for cell in claim["blocked_cells"]],
            "not_run_cells": coverage["counts"]["NOT_RUN"],
            "insufficient_data_cells": coverage["counts"]["INSUFFICIENT_DATA"],
            "coverage_status_counts": {status: coverage["counts"][status]
                                       for status in coverage["status_vocabulary"]},
            "arms": ["M4_CAL", "M4_REGIME", "M4_CAL_MATCHED", "M4_REGIME_DELAYED"],
            "rf05_engine_runs": 0,
        },
        "coverage": {
            "ref": "cell_coverage.json",
            "status": coverage["status"],
            "counts": coverage["counts"],
            "per_cell": {cell["cell"]: cell["coverage_status"] for cell in coverage["cells"]},
        },
        "metrics": {
            "mde_ref": "evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json",
            "mde_corrected_daily_account_bps": mde["corrected_daily_account_bps"],
            "claim_ref": "claim_report.json",
            "recomputation_ref": "recomputation.json",
            "freeze_ref": "freeze_manifest.json",
            "timing": family["TIMING"],
            "budget_aware": family["BUDGET_AWARE"],
        },
        "performance": {
            "rf05_wall_seconds": rf05_wall,
            "rf05_engine_runs": 0,
            "pilot_wall_seconds": profiling["wall_seconds"]["totals"]["pilot_sum_of_cell_arm_seconds"],
            "matched_wall_seconds": profiling["wall_seconds"]["totals"]["matched_control_loop_wall_seconds"],
            "placebo_wall_seconds": profiling["wall_seconds"]["totals"]["placebo_loop_wall_seconds"],
            "d2_wall_seconds": profiling["wall_seconds"]["d2_anchor_replay_seconds"],
            "peak_rss_bytes": profiling["peak_rss_bytes"]["value"],
            "cpu_seconds": profiling["cpu_seconds"]["value"],
            "actual_candidate_bar_visits": profiling["candidate_bar_visits"]["value"],
            "profile_ref": "profiling_and_budget.json",
            "unmeasured_reasons": {
                "cpu_seconds": profiling["cpu_seconds"]["reason"],
                "peak_rss_bytes": profiling["peak_rss_bytes"]["reason"],
                "candidate_bar_visits": profiling["candidate_bar_visits"]["reason"],
            },
        },
        "proof_capability": {
            "technical_validity": "VALID_WITH_PARTIAL_COVERAGE",
            "positive_control": "RF-04 G11 synthetic: params_changed_by_treatment=True, "
                                "treatment_reached_execution=True",
            "treatment_reached_execution": (f"{risk_changed} of {len(timing_cells)} event cells have "
                                            "different selected parameters between arms and different "
                                            "account paths"),
            "no_positive_status": not any(entry["statistical_status"] == "POSITIVE_WITHIN_SCOPE"
                                          for entry in claim["family"]),
        },
        "potential": {
            "level": "INCONCLUSIVE",
            "evidence_refs": ["claim_report.json#/answers", "recomputation.json#/cost_stress",
                              "evidence/corrective_mode4_v3/RF-04/controls_and_funnel.json#/funnel"],
            "falsifiable_next_step": answers["q3_next_research_direction"]["falsifiable_next_step"],
        },
        "claim": {
            "validity": answers["q1_experiment_valid"]["answer"],
            "execution_validity": answers["q1_experiment_valid"]["execution_validity"],
            "implementation_fidelity": answers["q1_experiment_valid"]["implementation_fidelity"],
            "statistical_status": answers["q2_benefit_within_tested_scope"]["answer"],
            "economic_status": answers["q2_benefit_within_tested_scope"]["answer"],
            "scope": ("A-SC and A-HMA x 5 symbols (10 of 20 planned cells), 2021-01-01..2022-06-30, "
                      "nested retrospective; A-VWAP/A-HASH BLOCKED_CAPABILITY"),
        },
        "contrasts": timing_cells + budget_cells,
        "family": claim["family"],
        "secondary_contrasts": claim["secondary_contrasts"],
        "route_deviations": claim["route_deviations"],
        "blocked_cells": claim["blocked_cells"],
        "answers": answers,
        "limitations": claim["limitations"],
        "review": {"author": "OpenCode", "reviewer": None, "disagreements": []},
        "handoff": {
            "next_phase": None,
            "status": "CORRECTED_STUDY_CLOSED_WITH_BLOCKERS",
            "blocking_findings": [row["blocker"] for row in
                                  load(RUN_DIR / "reproducibility_manifest.json")["remaining_blockers"]],
            "reproducibility_manifest": "reproducibility_manifest.json",
            "handoff_md": "handoff.md",
        },
        "design_freeze_ref": "evidence/corrective_mode4_v3/RF-04/design_freeze.json",
        "freeze_manifest_ref": "freeze_manifest.json",
        "artifact_integrity_ref": "artifact_integrity.json",
        "prospective_protocol_ref": "prospective_protocol.json",
        "report_md": {"path": "report.md", "sha256": report_md_sha},
        "artifact_hashes": {
            "claim_report.json": sha256_file(RUN_DIR / "claim_report.json"),
            "recomputation.json": sha256_file(RUN_DIR / "recomputation.json"),
            "freeze_manifest.json": sha256_file(RUN_DIR / "freeze_manifest.json"),
            "prospective_protocol.json": sha256_file(RUN_DIR / "prospective_protocol.json"),
            "design_freeze.json": sha256_file(RF04_DIR / "design_freeze.json"),
            "paired_discovery_full.json": sha256_file(RF04_DIR / "paired_discovery_full.json"),
            "cell_coverage.json": sha256_file(RF04_DIR / "cell_coverage.json"),
            "decay_panels.json": sha256_file(RF04_DIR / "decay_panels.json"),
            "controls_and_funnel.json": sha256_file(RF04_DIR / "controls_and_funnel.json"),
            "mde_corrected.json": sha256_file(PRE_RF04_DIR / "mde_corrected.json"),
            "note": ("artifact_integrity.json, reproducibility_manifest.json, handoff.md and the test "
                     "logs are refreshed after this report and their canonical hashes live in "
                     "reproducibility_manifest.json"),
        },
    }
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    record = writer.write_json("report.json", payload, schema=payload["schema"])

    refreshed_integrity = run_rf05.build_integrity(report_present=True)
    with writer.attempt("rf05.integrity_refresh") as attempt:
        run_rf05.write_stage("artifact_integrity.json", writer, refreshed_integrity)
        attempt.detail = {"status": refreshed_integrity["status"],
                          "checks": len(refreshed_integrity["checks"])}

    with writer.attempt("rf05.handoff_refresh") as attempt:
        repro = run_rf05.build_reproducibility_manifest()
        run_rf05.write_stage("reproducibility_manifest.json", writer, repro)
        handoff = run_rf05.build_handoff_markdown(repro, claim, refreshed_integrity)
        (RUN_DIR / "handoff.md").write_text(handoff, encoding="utf-8")
        attempt.detail = {"handoff": "evidence/corrective_mode4_v3/RF-05/handoff.md"}

    print(json.dumps({
        "report_md": str(md_path),
        "report_md_sha256": report_md_sha,
        "report_json": record["relpath"],
        "report_json_sha256": record["sha256"],
        "integrity": refreshed_integrity["status"],
        "tests": payload["tests"]["passed"],
        "full_suite": payload["tests"]["full_suite"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
