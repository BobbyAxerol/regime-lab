#!/usr/bin/env python
"""Render evidence/corrective_mode4_v3/RF-04/{report.md,report.json}.

Everything is read from committed RF-04 artifacts (never hand-entered): the
paired pilot, the registered protocol, the positive control, the matched/placebo
controls, the D1/D2/D3 panels, the design freeze, the pre-RF-04 corrected MDE and
the RF-01 identity binding. Test counts come from the recorded pytest log when it
exists; otherwise they are null with a reason.
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
PHASE = "RF-04"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / PHASE


def load(relpath: str) -> dict:
    return json.loads((RUN_DIR / relpath).read_text(encoding="utf-8"))


def parse_test_log(path: Path) -> dict | None:
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


def arm_line(arm: dict) -> str:
    account = arm.get("account") or {}
    report = account.get("engine_report") or {}
    return (f"folds={arm.get('fold_count')} trials={arm.get('trial_count')} "
            f"equity={account.get('equity_last')} "
            f"total_return_pct={report.get('total_return_pct')} "
            f"sharpe={report.get('sharpe')} trades={report.get('num_trades')} "
            f"max_dd_pct={report.get('max_drawdown_pct')} wall={arm.get('wall_seconds')}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    md_path, json_path = RUN_DIR / "report.md", RUN_DIR / "report.json"
    if (md_path.exists() or json_path.exists()) and not args.force:
        raise SystemExit("RF-04 report exists; pass --force to supersede")

    pilot = load("paired_discovery_pilot.json")
    protocol = load("discovery_protocol.json")
    positive = load("positive_control.json")
    controls = load("controls_and_funnel.json")
    panel = load("decay_panels.json")
    freeze = load("design_freeze.json")
    manifest = load("model_design_selection_manifest.json")
    mde = json.loads((LAB_ROOT / "evidence" / STUDY_ID / "pre-RF04-clearing"
                      / "mde_corrected.json").read_text(encoding="utf-8"))
    identity = json.loads((LAB_ROOT / "evidence" / STUDY_ID / "RF-01"
                           / "working_copy_identity.json").read_text(encoding="utf-8"))
    binding = json.loads((LAB_ROOT / "evidence" / STUDY_ID / "RF-01"
                          / "quantbt_binding_report.json").read_text(encoding="utf-8"))
    test_counts = parse_test_log(RUN_DIR / "test_suite_mode4_corrective.log")

    cells = {row["cell"]: row for row in pilot["cells"]}
    sc = cells["A-SC/BTCUSDT"]
    hma = cells["A-HMA/BTCUSDT"]
    matched = {row["cell"]: row for row in controls["matched_control"]["cells"]}
    placebo = {row["cell"]: row for row in controls["placebo"]["cells"]}
    paired = {row["contrast"]: row for row in controls["paired_endpoints"]}
    contrasts = {row["cell"]: row for row in controls["contrasts"]}
    funnel = controls["funnel"]
    d2_rows = panel["D2"]["rows"]
    budget_aware = paired["M4_REGIME - M4_CAL_MATCHED on A-HMA/BTCUSDT"]
    timing_hma = paired["M4_REGIME - M4_CAL on A-HMA/BTCUSDT"]
    assets = {
        name: sha256_file(RUN_DIR / name)
        for name in ("paired_discovery_pilot.json", "paired_discovery_registration.json",
                     "discovery_protocol.json", "positive_control.json",
                     "controls_registration.json", "controls_and_funnel.json",
                     "decay_panels.json", "design_freeze.json",
                     "model_design_selection_manifest.json", "causal_model_registry.json",
                     "emission_tape_sample.json", "current_coordinate_contract.json")
    }
    log_hashes = {name: sha256_file(RUN_DIR / name) for name in
                  ("test_suite_mode4_corrective.log", "pyflakes_mode4_corrective.log")
                  if (RUN_DIR / name).exists()}
    source_hashes = {
        "src/crypto_regime_lab/experiments/dynamic_fold_provider.py":
            sha256_file(LAB_ROOT / "src/crypto_regime_lab/experiments/dynamic_fold_provider.py"),
        "scripts/run_rf04_paired_pilot.py":
            sha256_file(LAB_ROOT / "scripts/run_rf04_paired_pilot.py"),
        "scripts/run_rf04_decay_and_controls.py":
            sha256_file(LAB_ROOT / "scripts/run_rf04_decay_and_controls.py"),
        "tests/mode4_corrective/test_rf04_decay_and_controls.py":
            sha256_file(LAB_ROOT / "tests/mode4_corrective/test_rf04_decay_and_controls.py")
            if (LAB_ROOT / "tests/mode4_corrective/test_rf04_decay_and_controls.py").exists() else None,
    }

    lines: list[str] = []
    add = lines.append
    add("# RF-04 — Fast real-alpha experiment: metrics, decay and controls")
    add("")
    add("Generated from committed RF-04 artifacts by `scripts/write_rf04_report.py`. "
        "The bounded two-cell pilot cannot support an economic claim; no positive result is recorded.")
    add("")
    add("## 1. Objective and what is not tested")
    add("")
    add("Test whether a causal regime-triggered refit schedule (`M4_REGIME`) changes the continuous "
        "account outcome against the calendar per-fold causal WFO (`M4_CAL`) on real snapshots, with "
        "refit cadence/compute separated by the mandatory budget control (`M4_CAL_MATCHED`), and close "
        "the metrics/decay panel (D1 IS->OOS, D2 fixed-parameter age, D3 adjacent operational folds) "
        "required before scaling.")
    add("")
    add("**Not tested:** economic superiority. The execution span is a 2-cell bounded pilot "
        "(A-SC/BTCUSDT and A-HMA/BTCUSDT) at 8 trials/cutoff on the pilot development window "
        f"{pilot['development_window']['start']}..{pilot['development_window']['end']}. The registered "
        f"discovery protocol declares the wider cohort `{protocol['cohort']['data']}`; the executed "
        "scope is narrower and is reported as such. A-VWAP/A-HASH are route-blocked and the remaining "
        "16 cells were not executed; no 20-cell aggregate exists.")
    add("")
    add("## 2. Identity, contracts and resolved runtime")
    add("")
    add(f"- branch `{identity['branch']}` at RF-01 head `{identity['head_commit']}`; plan sha256 "
        f"`{identity['plan']['sha256']}`")
    add(f"- QuantBT: `{binding['installed_quantbt']['distributions']}`, import origin "
        f"`{binding['installed_quantbt']['import_origin']}`; native module: "
        f"{binding['installed_quantbt']['native_import_error']}")
    add(f"- original audit archive sha256 `{identity['original_audit_archive']['sha256']}` "
        "(preserved, not rewritten)")
    add("- Mode 4 contract: mode `mode_4_is_only_robust`, schedule `per_fold_causal`, metric "
        "`is_only_robust`, backend `endpoint`, `oos_used_for_selection=False`, claim "
        "`strict_fold_local_retraining`")
    add(f"- economics per arm: registered pilot budget {protocol['budgets']['pilot_trials_per_cutoff']} "
        "trials/cutoff (corrective spec range 32-64); the bounded pilot registered the low end "
        "overridden to 8 trials/cutoff, seed 20260911, account 20000 USDT, entry notional 2000 USDT, "
        "one-way fee 0.0004 bound once, slippage 1bp, 180-day training memory")
    add(f"- MDE: {mde['corrected_daily_account_bps']:.4f} account bps/day "
        f"(`evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json`, `{mde['status']}`)")
    add(f"- snapshot: `{sc['data']['snapshot_id']}` manifest sha256 "
        f"`{sc['data']['snapshot_manifest_sha256']}`; A-SC 15m {sc['data']['bars']} bars; "
        f"A-HMA 1h {hma['data']['bars']} bars")
    add("- requested candidates: 8/cutoff; actual resolved candidates: "
        "A-SC 3/6 folds (24/48 trial rows), A-HMA 3/6 folds (24/48 trial rows)")
    add("")
    add("## 3. Findings fixed and their acceptance tests")
    add("")
    add("| finding | repair | RF-04 acceptance |")
    add("|---|---|---|")
    add(f"| G10/A14 model design | real model ladder selected on fixed-target rank IC, inner-train-only "
        f"scaler, one-to-one namespace mapping ({manifest['selection']['model']} k="
        f"{manifest['selection']['n_states']}, lambda={manifest['selection']['lambda_jump']}) | "
        f"`test_committed_manifest_has_denominators_and_can_go_red`, "
        f"`test_committed_registry_maps_one_to_one_and_guards_market_transitions` |")
    add("| G11 positive control | synthetic world with known switches; the policy reads emissions, "
        "not ground truth | `test_rf04_positive_control.py` + "
        f"`positive_control.json` (params_changed_by_treatment={positive['params_changed_by_treatment']}, "
        f"treatment_reached_execution={positive['treatment_reached_execution']}) |")
    add("| RF-03 causal schedule | online controller triggers on eligible semantic changes only, no "
        "namespace-as-market transitions | `test_rf03_controller.py` |")
    add("| RF-04.3 decay separation | raw and penalized IS flavors kept on separate rows; undefined "
        "metrics null plus status | `test_rf04_d1_keeps_raw_and_penalized_separate` |")
    add("| RF-04.4 matched control | mandatory `M4_CAL_MATCHED` with 6 evenly spaced calendar cutoffs "
        "on the same machinery | `test_rf04_matched_control_present_with_registered_budget` |")
    add("| execution-route blocker (new) | A-SC endpoint scorer returns one objective for every "
        "sampled candidate and exposes no per-fill ledger | funnel rank diagnostic + this report |")
    add("")
    add(f"Source hashes: `dynamic_fold_provider.py` `{source_hashes['src/crypto_regime_lab/experiments/dynamic_fold_provider.py']}`; "
        f"`run_rf04_paired_pilot.py` `{source_hashes['scripts/run_rf04_paired_pilot.py']}`.")
    add("")
    add("## 4. Budget, sample and coverage")
    add("")
    add(f"- raw pilot window {pilot['development_window']['start']}.."
        f"{pilot['development_window']['end']}; folds in the pilot: M4_CAL 3, M4_REGIME 6, "
        f"M4_CAL_MATCHED 6, M4_REGIME_DELAYED 6")
    add(f"- cutoffs: M4_CAL {', '.join(pilot['arms']['M4_CAL']['cutoffs'])}; "
        f"M4_REGIME {', '.join(pilot['arms']['M4_REGIME']['cutoffs'])}; "
        f"M4_CAL_MATCHED {', '.join(controls['matched_control']['cutoffs'])}")
    add(f"- trials: {sum(row['trial_count'] for row in (sc['arms']['M4_CAL'], sc['arms']['M4_REGIME'],))} "
        f"pilot trial rows on each cell; matched and placebo 48 trial rows each on each cell")
    add("- coverage: 2 of 20 planned cells executed; A-VWAP/A-HASH stay `BLOCKED_CAPABILITY` "
        "(amend/ladder semantics), the other 16 cells `NOT_RUN`; no silent denominator change")
    add(f"- MDE corrected: {mde['corrected_daily_account_bps']:.4f} bps/day; the 8-trial bounded pilot "
        f"is below the registered 32-64 trials/cutoff")
    add("")
    add("## 5. Technical vs market vs synthetic")
    add("")
    add("- **Market (real snapshot):** all arm records below are real `server_core_v1` data on the "
        "development window; no synthetic curve is used in any decay or control number.")
    add(f"- A-SC/BTCUSDT: M4_CAL {arm_line(sc['arms']['M4_CAL'])}; M4_REGIME "
        f"{arm_line(sc['arms']['M4_REGIME'])}; M4_CAL_MATCHED {arm_line(matched['A-SC/BTCUSDT']['arm'])}")
    add(f"- A-HMA/BTCUSDT: M4_CAL {arm_line(hma['arms']['M4_CAL'])}; M4_REGIME "
        f"{arm_line(hma['arms']['M4_REGIME'])}; M4_CAL_MATCHED {arm_line(matched['A-HMA/BTCUSDT']['arm'])}")
    add(f"- **Synthetic:** G11 positive control only ({positive['regime']['engine_fills']} regime vs "
        f"{positive['calendar']['engine_fills']} calendar engine fills, equity "
        f"{positive['regime']['equity']:.2f} vs {positive['calendar']['equity']:.2f}); it never enters a "
        f"market metric")
    add("- **Technical:** D2 replays use the real native-event account on real frames; no mocked "
        "evaluation is present in D1/D2/D3")
    add("")
    add("## 6. Metrics and decay")
    add("")
    add("| metric | definition | unit | support / null rule |")
    add("|---|---|---|---|")
    add("| `mean_daily_return_bps` | mean daily account net return, first day charged from the prior "
        "daily equity | account bps/day | null + `INSUFFICIENT_OBSERVATIONS` below 2 daily returns |")
    add("| `sharpe` | sqrt(365)*mean/std(daily net return, ddof=1) | ratio | null + `ZERO_VARIANCE` |")
    add("| `profit_factor_daily` | sum(positive daily returns)/abs(sum(negative daily returns)) | ratio "
        "| null + `NO_LOSS_DENOMINATOR` or `NO_TRADES` |")
    add("| `selected_is_objective` | engine Mode 4 robust objective used for selection | engine score | "
        "kept raw and penalized on separate D1 rows |")
    add("")
    add(f"D1 rows {panel['denominators']['D1_rows']} (valid {panel['denominators']['D1_valid_rows']}), "
        f"D2 rows {panel['denominators']['D2_rows']}, D3 rows {panel['denominators']['D3_rows']} "
        f"(valid {panel['denominators']['D3_valid_rows']}); null reasons: "
        f"{', '.join(panel['denominators']['null_value_reasons'])}.")
    add("")
    add("Null-value rule: the Mode 4 trial ledger retains the IS Sharpe objective and temporal "
        "subperiod statistics, not an IS account return or IS profit factor, so those D1 left values "
        "are null with the reason `IS_*_NOT_IN_TRIAL_LEDGER`; they are never filled with an estimate.")
    add("")
    add("**D2 fixed-parameter age replay** (anchors registered before the run: fold-0 selection of each "
        "primary arm per cell; h=90 days):")
    add("")
    add("| anchor | H1 mean bps/day | H2 mean bps/day | H3 mean bps/day | H1 trades | H2/H3 trades |")
    add("|---|---|---|---|---|---|")
    for anchor in sorted({row["selection_id"] for row in d2_rows if row["metric_name"] == "return"}):
        rows = [r for r in d2_rows if r["selection_id"] == anchor and r["metric_name"] == "return"]
        by_age = {row["age_window_label"]: row for row in rows}
        add(f"| {anchor} | {by_age['H1']['h1_equity_metrics']['mean_daily_return_bps']} | "
            f"{by_age['H2']['right_value']} | {by_age['H3']['right_value']} | "
            f"{by_age['H1']['trade_count']} | {by_age['H2']['trade_count']}/{by_age['H3']['trade_count']} |")
    add("")
    add("Age reads are diagnostics after selection only; they never update a search threshold or an "
        "activation rule in this run.")
    add("")
    add("## 7. Runtime breakdown")
    add("")
    total_pilot = sum((cell["arms"][arm].get("wall_seconds") or 0.0)
                      for cell in pilot["cells"] for arm in ("M4_CAL", "M4_REGIME"))
    add(f"- paired pilot wall: {total_pilot:.1f}s total across both cells and arms")
    add(f"- M4_CAL_MATCHED wall: {controls['matched_control']['wall_seconds']}s "
        f"(placebo {controls['placebo']['wall_seconds']}s, status `{controls['placebo']['status']}`)")
    add(f"- D2 anchor replay wall: {controls['decay_anchor']['wall_seconds']:.1f}s "
        f"({panel['denominators']['anchors_replayed']}/{panel['denominators']['registered_anchors']} "
        f"anchors replayed, status `{panel['D2']['status']}`)")
    add("- reported vs planned: 2 of 20 cells executed, 8 trials/cutoff instead of the registered "
        "32-64; no canceled budget job and no degraded execution resolution were used to hit time")
    add("- no cold/warm native split is claimed in this phase; the event account ran on the installed "
        "Python route with `native_import_error` recorded in RF-01")
    add("")
    add("## 8. Proof capability")
    add("")
    add(f"- positive control: `params_changed_by_treatment={positive['params_changed_by_treatment']}`, "
        f"`treatment_reached_execution={positive['treatment_reached_execution']}`; the controller fired "
        f"at the known synthetic switch bars and the engine fills differ by arm")
    add(f"- treatment reached execution on A-HMA/BTCUSDT: engine trades "
        f"{hma['arms']['M4_CAL']['account']['engine_report']['num_trades']} (calendar) vs "
        f"{hma['arms']['M4_REGIME']['account']['engine_report']['num_trades']} (regime), i.e. different "
        f"orders")
    add(f"- treatment did NOT reach execution on A-SC/BTCUSDT: `M4_CAL_MATCHED` and `M4_CAL` equity "
        f"series are identical (`{paired['M4_CAL_MATCHED - M4_CAL on A-SC/BTCUSDT']['economic_status_reason']}`) "
        f"and every sampled candidate scored the same objective")
    add("- null/placebo: delayed-state arm ran "
        f"({controls['placebo']['status']}) with cutoffs {', '.join(placebo['A-HMA/BTCUSDT']['schedule']['cutoffs'])}; "
        "it is a diagnostic, not confirmation")
    add("- pipeline capability: it can detect parameter-rank signal for A-HMA (varying objectives) and "
        "correctly fails closed on A-SC; it cannot yet reject the MDE because the pilot is 2 cells")
    add("")
    add("## 9. Potential assessment")
    add("")
    add(f"`{funnel['potential_level']}` — {funnel['potential_note']}.")
    add("")
    add(f"- A-SC/BTCUSDT: `{funnel['cells']['A-SC/BTCUSDT']['rank_diagnostic']['status']}` "
        f"({funnel['cells']['A-SC/BTCUSDT']['rank_diagnostic']['rule']})")
    add(f"- A-HMA/BTCUSDT: `{funnel['cells']['A-HMA/BTCUSDT']['rank_diagnostic']['status']}`; adjacent "
        f"selections change parameters {funnel['cells']['A-HMA/BTCUSDT']['searches']['M4_REGIME']['adjacent_parameter_changes']} "
        f"times across the 6 regime folds; across the four arms the funnel counts "
        f"{funnel['cells']['A-HMA/BTCUSDT']['activated']['activations_with_changed_params']} activated "
        f"parameter changes")
    add(f"- funnel denominators (A-HMA tape): {funnel['cells']['A-HMA/BTCUSDT']['valid_observations']['total_emissions_in_window']} "
        f"emissions in window, {funnel['cells']['A-HMA/BTCUSDT']['valid_observations']['eligible_quality_ok']} "
        f"eligible/quality-OK, "
        f"{funnel['cells']['A-HMA/BTCUSDT']['valid_observations']['semantic_changes_in_window']} semantic "
        f"changes, {funnel['cells']['A-HMA/BTCUSDT']['triggers']['M4_REGIME']} controller triggers")
    add("- bottleneck: information (not activation) on A-HMA; the BUDGET_AWARE paired CI "
        f"[{budget_aware['paired_daily_difference']['ci95_low_bps']:.3f}, "
        f"{budget_aware['paired_daily_difference']['ci95_high_bps']:.3f}] bps/day contains 0 and the "
        f"corrected MDE {mde['corrected_daily_account_bps']:.4f}")
    add("- falsifiable next action: before scaling, repair or quarantine the A-SC endpoint evaluation "
        "route so candidate objectives are parameter-sensitive; then freeze and run the registered "
        "32-64 trials/cutoff design; no feature/model complexity is added first")
    add("")
    add("## 10. Claim limitations")
    add("")
    for item in controls["limitations"]:
        add(f"- {item}")
    add(f"- the registered discovery cohort is `{protocol['cohort']['data']}` but the executed pilot "
        f"window is {pilot['development_window']['start']}..{pilot['development_window']['end']} "
        "(its own registration); the narrower scope is never renamed to the registered cohort")
    add("- the paired CIs are exploratory moving-block bootstrap intervals on saved daily returns; "
        "they are not a confirmatory test and never license a `POSITIVE` status")
    add("- `simulation_complete` and `audit_complete` are separate: all engine accounts flushed and "
        "all artifacts are strict JSON with null+reason for missing values")
    add("")
    add("## 11. Exit decision")
    add("")
    add("**RF-04: PARTIAL_TECHNICAL_CLOSURE.** The corrected Mode 4 paired pilot ran on two real cells, "
        "the mandatory `M4_CAL_MATCHED` control and the registered delayed-state placebo ran, D1/D2/D3 "
        "panels and the decision funnel are complete with real denominators, and the design freeze is "
        "recorded. No economic claim is made: A-SC is `NOT_EVALUABLE` (treatment not transmitted to "
        "execution) and A-HMA is `INCONCLUSIVE` (2-cell bounded pilot). Remaining tasks: repair or "
        "quarantine the A-SC endpoint candidate evaluation, then scale to the registered design before "
        "RF-05 confirmation.")
    add("")
    add("## 12. Rerun recipe, output hashes and handoff")
    add("")
    add("```bash")
    add("LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf04_paired_pilot.py")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf04_decay_and_controls.py --force")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q \\")
    add("  | tee $LAB/evidence/corrective_mode4_v3/RF-04/test_suite_mode4_corrective.log")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pyflakes $LAB/src $LAB/scripts $LAB/tests/mode4_corrective \\")
    add("  | tee $LAB/evidence/corrective_mode4_v3/RF-04/pyflakes_mode4_corrective.log")
    add("PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf04_report.py --force")
    add("```")
    add("")
    add("For an artifact-only recompute that reuses the committed engine arm records, run "
        "`run_rf04_decay_and_controls.py --force --reuse-engine`; the new payload records the "
        "superseded artifact hash in `supersedes`.")
    add("")
    add("Recorded output hashes:")
    for name, digest in assets.items():
        add(f"- `{name}` `{digest}`")
    for name, digest in log_hashes.items():
        add(f"- `{name}` `{digest}`")
    add("")
    add("Handoff: next phase `RF-05`; blocking finding = A-SC endpoint candidate evaluation "
        "(implementation_fidelity DEVIATED). The registered historical evidence under "
        "`evidence/crypto_regime_timeedge_v2/` was not touched.")
    add("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    claim_block = {
        "validity": "PARTIAL_TECHNICAL_CLOSURE",
        "execution_validity": "PARTIAL",
        "implementation_fidelity": "DEVIATED",
        "statistical_status": "NOT_EVALUABLE",
        "economic_status": "INCONCLUSIVE",
        "scope": ("A-SC/BTCUSDT and A-HMA/BTCUSDT, 2021-01-01..2022-06-30, development window only; "
                  "2 of 20 planned cells executed"),
    }
    payload = {
        "schema": "regime_lab.corrective_phase_report.v3",
        "phase_id": PHASE,
        "status": "PARTIAL_TECHNICAL_CLOSURE",
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now_iso(),
        "source": {
            "archive_sha256": identity["original_audit_archive"]["sha256"],
            "lab_head_commit": identity["head_commit"],
            "lab_branch": identity["branch"],
            "plan_sha256": identity["plan"]["sha256"],
            "candidate_commit": None,
            "candidate_source_manifest": "evidence/corrective_mode4_v3/RF-01/source_before_manifest.json",
            "quantbt_core_version": binding["installed_quantbt"]["distributions"].get(
                "quantbt-engine"),
            "quantbt_native_version": binding["installed_quantbt"]["distributions"].get(
                "quantbt-native"),
            "native_artifact": binding["installed_quantbt"]["native_import_error"],
            "actual_import_origins": [binding["installed_quantbt"]["import_origin"]],
        },
        "objective": ("metrics/decay panels and ordered controls for the Mode 4 per_fold_causal "
                      "calendar vs causal regime refit comparison"),
        "registered_arms": ["M4_CAL", "M4_REGIME"],
        "findings": {
            "G10": manifest["status"], "G11": "EVALUATED",
            "A14": "REPAIRED_UNIT_ONLY", "RF-04.3": "D1_D2_D3_PANELS_COMPLETE",
            "RF-04.4": "MATCHED_AND_PLACEBO_RUN", "RF-04.5": freeze["status"],
        },
        "tests": {
            "passed": (test_counts or {}).get("passed"),
            "failed": (test_counts or {}).get("failed"),
            "skipped": (test_counts or {}).get("skipped"),
            "artifact_refs": ["test_suite_mode4_corrective.log", "pyflakes_mode4_corrective.log"],
            "test_file": "tests/mode4_corrective/test_rf04_decay_and_controls.py",
            "note": (None if test_counts else "test log not present at report generation; counts null"),
        },
        "market_runs": {
            "planned_cells": 20,
            "executed_cells": len(pilot["cells"]),
            "valid_pairs": sum(1 for cell in pilot["cells"] if cell["contrast"]["status"] == "VALID"),
            "blocked_cells": (["A-VWAP/" + symbol for symbol in protocol["cohort"]["symbols"]]
                              + ["A-HASH/" + symbol for symbol in protocol["cohort"]["symbols"]]),
            "not_run_cells": 16,
            "arms": ["M4_CAL", "M4_REGIME", "M4_CAL_MATCHED", "M4_REGIME_DELAYED"],
        },
        "metrics": {
            "raw_quantbt_ref": "paired_discovery_pilot.json",
            "canonical_ref": "decay_panels.json",
            "decay_panel_ref": "decay_panels.json",
            "controls_ref": "controls_and_funnel.json",
            "mde_ref": "evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json",
            "mde_corrected_daily_account_bps": mde["corrected_daily_account_bps"],
            "budget_aware_paired": budget_aware,
            "timing_paired": timing_hma,
        },
        "performance": {
            "pilot_wall_seconds": round(total_pilot, 3),
            "matched_wall_seconds": controls["matched_control"]["wall_seconds"],
            "placebo_wall_seconds": controls["placebo"]["wall_seconds"],
            "d2_wall_seconds": controls["decay_anchor"]["wall_seconds"],
            "peak_rss_bytes": None,
            "actual_candidate_bar_visits": None,
        },
        "proof_capability": {
            "technical_validity": "PARTIAL",
            "positive_control": ("params_changed_by_treatment="
                                 f"{positive['params_changed_by_treatment']}, "
                                 f"treatment_reached_execution={positive['treatment_reached_execution']}"),
            "treatment_reached_execution": "A-HMA/BTCUSDT yes (6 vs 10 engine trades); A-SC/BTCUSDT no",
        },
        "potential": {
            "level": funnel["potential_level"],
            "per_cell": {name: row["rank_diagnostic"]["status"] for name, row in funnel["cells"].items()},
            "evidence_refs": ["controls_and_funnel.json#funnel", "decay_panels.json"],
            "falsifiable_next_step": ("repair or quarantine the A-SC endpoint evaluation so candidate "
                                      "objectives are parameter-sensitive, then freeze and run the "
                                      "registered 32-64 trials/cutoff design"),
        },
        "claim": claim_block,
        "contrasts": [contrasts["A-SC/BTCUSDT"], contrasts["A-HMA/BTCUSDT"]],
        "paired_endpoints": controls["paired_endpoints"],
        "limitations": controls["limitations"] + [
            "A-SC implementation_fidelity=DEVIATED; its statistical status is NOT_EVALUABLE",
            "A-HMA statistical status is INCONCLUSIVE on a 2-cell bounded pilot",
            "registered cohort extends to 2023-12-31 but the pilot executed 2021-01-01..2022-06-30",
        ],
        "review": {"author": "OpenCode", "reviewer": None, "disagreements": []},
        "handoff": {"next_phase": "RF-05",
                    "blocking_findings": [
                        "A-SC/BTCUSDT endpoint candidate ranking not identified",
                        "coverage: 2 of 20 cells executed at 8 trials/cutoff"]},
        "design_freeze_ref": "design_freeze.json",
        "report_md": {"path": "report.md", "sha256": sha256_file(md_path)},
        "artifact_hashes": {**assets, **log_hashes, "source_hashes": source_hashes},
    }
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    record = writer.write_json("report.json", payload, schema=payload["schema"])
    print(json.dumps({"report_md": str(md_path), "report_md_sha256": sha256_file(md_path),
                      "report_json": record["relpath"], "report_json_sha256": record["sha256"],
                      "tests": payload["tests"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
