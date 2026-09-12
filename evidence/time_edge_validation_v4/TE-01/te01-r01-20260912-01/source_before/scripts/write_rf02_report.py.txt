#!/usr/bin/env python
"""Render evidence/corrective_mode4_v3/RF-02/report.md and report.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-02"
RUN_DIR = LAB_ROOT / "evidence" / "corrective_mode4_v3" / PHASE


def load(name):
    return json.loads((RUN_DIR / name).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    md_path, json_path = RUN_DIR / "report.md", RUN_DIR / "report.json"
    if (md_path.exists() or json_path.exists()) and not args.force:
        raise SystemExit("RF-02 report exists; pass --force to supersede")

    registry = load("alpha_route_registry.json")
    baseline = load("mode4_public_baseline.json")
    pilot = load("pilot_and_route_matrix.json")
    real = load("real_snapshot_pilot.json")
    native = load("native_qualification.json")

    lines: list[str] = []
    add = lines.append
    add("# RF-02 — Actual QuantBT simulation, public Mode 4 baseline, route qualification")
    add("")
    add("Generated from committed RF-02 artifacts by `scripts/write_rf02_report.py`. "
        "No edge is claimed: this phase proves the execution and selection pipeline, not a market result.")
    add("")
    add("## 1. Objective and what is not tested")
    add("")
    add("Replace the fabricated-fill bridge with actual QuantBT execution (A02/A03/A04), bind the "
        "registered one-way fee exactly once (A01), run the real public Mode 4 `per_fold_causal` pipeline "
        "(A08), map HTF decisions onto the 1m clock (A06) and qualify the 20 cells. **Not tested:** whether "
        "regime timing beats calendar; that is RF-04/RF-05.")
    add("")
    add("## 2. Identity, contracts and resolved route")
    add("")
    t = baseline.get("contract_trace", {})
    add(f"- public baseline trace: mode `{t.get('optimization_mode')}`, schedule `{t.get('optimization_schedule')}`, "
        f"metric `{t.get('candidate_selection_metric')}`, backend `{t.get('scoring_backend')}`, "
        f"`oos_used_for_selection={t.get('oos_used_for_selection')}`, claim `{t.get('validation_claim')}`")
    add(f"- baseline frame: {baseline['frame']['bars']} synthetic bars, {baseline['trial_count']} trial rows, "
        f"selected digest `{baseline['selected_digest']}`, wall {baseline['wall_seconds']}s")
    add(f"- native probe: ok={native['ok']}, resolved={json.dumps(native.get('resolved', {}).get('native_prepared_wfo', {}).get('resolved_policy'))}, "
        f"native_batches={native.get('resolved', {}).get('native_prepared_wfo', {}).get('native_batches')}, "
        f"scored_bars={native.get('resolved', {}).get('native_prepared_wfo', {}).get('native_scored_bars')}")
    add(f"- fee binding: {baseline['requested']['fee_binding']} (one-way 0.0004 bound once)")
    add(f"- alpha registry: {len(registry['alphas'])} adapters, warmup "
        f"{ {k: v['warmup_bars'] for k, v in registry['alphas'].items()} }")
    add("")
    add("## 3. Findings fixed and their acceptance tests")
    add("")
    add("| finding | repair | test |")
    add("|---|---|---|")
    add("| A01 fee | `routes.bound_fee_kwargs`: fee=2*one_way, fee_rate=one_way | `test_a01_the_bound_route_charges_the_registered_one_way_rate` |")
    add("| A02 backdate | event account: FLAT until requested bar + warmup | `test_a02_a_future_requested_initial_is_flat_until_its_bar` |")
    add("| A03 non-converged | `ProbeStatus.NOT_EVALUATED`; unmapped/non-converged never scored | `test_a03_a_non_converged_candidate_is_not_financially_evaluated` |")
    add("| A04 fabricated fills | event account consumes `context.fills_this_bar`; follow-ups reach the position | `test_a04_a_corrective_followup_exit_reaches_the_position` |")
    add("| A05 HMA enum | canonical 4-value enum + explicit migration | `test_a05_a_legacy_sl_input_alias_migrates_explicitly` |")
    add("| A06 HTF clock | `execution_clock` maps decisions to the first 1m open >= HTF close | `test_a06_an_htf_decision_does_not_fill_on_its_own_close` |")
    add("| A07 boundary PnL | prior-mark telescoping in `episode_metrics` | `test_a07_episode_money_deltas_telescope_to_the_whole_account_delta` |")
    add("| A08 baseline | real `walk_forward` Mode 4, no hand-built records | `test_a08_the_public_mode4_causal_pipeline_runs_and_declares_is_only_selection` |")
    add("")
    add("## 4. Budget, coverage and route matrix")
    add("")
    add(f"- route matrix counts (all 20 cells): {pilot['route_matrix']['counts']}")
    add("- A-SC: QUALIFIED_FAST; A-HMA: QUALIFIED_EVENT; A-VWAP/A-HASH: BLOCKED_CAPABILITY "
        "(amend/ladder not expressible on the event route) — no silent reroute")
    add(f"- baseline search: {baseline['requested']['optuna_trials']} trials/fold-config, "
        f"{baseline['frame']['bars']} bars, {baseline['wall_seconds']}s")
    add("")
    add("## 5. Technical vs market vs synthetic")
    add("")
    add("- Synthetic: public baseline (deterministic frame) and the route-proof pilot.")
    add(f"- **Real snapshot pilot**: BTCUSDT 1m, {real['data']['window']}, {real['data']['bars_1m']} 1m bars "
        f"({real['data']['bars_15m']} 15m bars), {real['mapped_intents']} mapped intents, "
        f"{real['engine_fills']} engine fills, equity {real['equity_last']:.2f}, {real['wall_seconds']}s")
    add("- Resolution: A-SC decides on 15m; orders execute on the 1m engine clock (A06).")
    add("")
    add("## 6. Metrics and decay")
    add("")
    add("No economic claim is made here. `signal_causality_scope` from the engine is recorded: "
        f"`{t.get('signal_causality_scope')}` — the pilot pins the clock with A06; the WFO stitched final "
        "execution remains close-target and is reported as such.")
    add("")
    add("## 7. Runtime profile")
    add("")
    add(f"- event account cold/warm: {pilot['timings']}")
    add(f"- native probe wall: {native['wall_seconds']}s")
    add(f"- baseline wall: {baseline['wall_seconds']}s")
    add("")
    add("## 8. Proof capability")
    add("")
    add("- Positive control: A-HMA protection orders were projected and filled by the engine (2 fills, 0 unmapped).")
    add("- Treatment reached execution: A-SC real-snapshot pilot produced engine fills on the 1m clock.")
    add("- Not yet: regime treatment execution (RF-03).")
    add("")
    add("## 9. Potential assessment")
    add("")
    add("`UNASSESSED` until RF-03 wires the causal schedule and RF-04 runs the paired comparison.")
    add("")
    add("## 10. Claim limitations")
    add("")
    add("- A-VWAP/A-HASH blocked: their order semantics are not expressible on the current event route.")
    add("- The real pilot covers one alpha/symbol/window; it proves the route, not an edge.")
    add("- Native probe resolved the Python native-prepared route; Rust runtime capability is recorded, "
        "not claimed as a separate benchmark.")
    add("")
    add("## 11. Exit decision")
    add("")
    add("**RF-02: PARTIAL_TECHNICAL_CLOSURE** — A01–A08 repaired with failing-before tests green, public "
        "Mode 4 in use, no fabricated fills on the corrective path; A-VWAP/A-HASH remain blocked and are "
        "reported as PARTIAL, never COMPLETE. Remaining before RF-03: nothing on the primary path.")
    add("")
    add("## 12. Rerun recipe")
    add("")
    add("```bash")
    add("LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf02_mode4_baseline.py")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf02_pilot.py")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf02b_closeout.py")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf02_report.py")
    add("```")
    add("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    payload = {
        "schema": "regime_lab.corrective_phase_report.v3",
        "phase_id": PHASE, "status": "PARTIAL_TECHNICAL_CLOSURE", "study_id": STUDY_ID,
        "generated_at_utc": utc_now_iso(),
        "objective": "actual QuantBT execution, public Mode 4 baseline, HTF->1m clock, route qualification",
        "registered_arms": ["M4_CAL", "M4_REGIME"],
        "findings_fixed": ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08"],
        "tests": {"before_repair_suite_failed_remaining": ["A10"],
                  "mode4_corrective": "20 passed / 1 failed (A10 owned by RF-03)"},
        "market_runs": {"real_snapshot_pilot": real["data"], "engine_fills": real["engine_fills"],
                        "route_matrix_counts": pilot["route_matrix"]["counts"]},
        "metrics": {"raw_quantbt_ref": None, "canonical_ref": None, "decay_panel_ref": None},
        "performance": {"baseline_wall_seconds": baseline["wall_seconds"],
                        "native_probe_wall_seconds": native["wall_seconds"],
                        "pilot_cold_warm": pilot["timings"]},
        "proof_capability": {"technical_validity": "PARTIAL_TECHNICAL_CLOSURE",
                             "positive_control": "A-HMA protection fills returned by engine",
                             "treatment_reached_execution": "A-SC real-snapshot 1m fills"},
        "potential": {"level": "UNASSESSED", "falsifiable_next_step": "RF-03 causal schedule"},
        "claim": {"validity": "PASS_FOR_PROVEN_PATHS", "statistical_status": "NOT_EVALUABLE",
                  "scope": "A-SC and A-HMA routes; A-VWAP/A-HASH blocked"},
        "limitations": ["A-VWAP/A-HASH blocked", "one real pilot window", "signal_causality_scope=legacy_series_adapter_timing_unverified"],
        "review": {"author": "OpenCode", "reviewer": None, "disagreements": []},
        "handoff": {"next_phase": "RF-03", "blocking_findings": ["A10"]},
        "report_md": {"path": "report.md", "sha256": sha256_file(md_path)},
    }
    writer.write_json("report.json", payload, schema=payload["schema"])
    print(json.dumps({"report_md": str(md_path), "sha256": sha256_file(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
