#!/usr/bin/env python3
"""Build RA-07 artifacts (RA-GUIDE-1.0 section 11): bounded replication,
falsification, decay and inference.

Freezes replication_spec.json (delta/MDE/bootstrap plan/seed schedule/
controls plan) from cell 1's ALREADY-REAL RA-05 evidence BEFORE any new
engine call this phase makes, runs a second real cell (A-SC/ETHUSDT, RA-05's
exact contract) plus the two controls that need a fresh schedule
(DELAYED_INFORMATION, PLACEBO_TIMING, cell 1 only), then builds decay
(D1 needs a cheap deterministic replay per fold; D2/D3 are pure reuse),
bootstrap statistics (zero engine calls) and sensitivity reporting from
STORED outcomes only.

Usage:
  lab_venv/bin/python scripts/run_ra07.py --pytest-xml <junit of tests/ra_corrective>
  lab_venv/bin/python scripts/run_ra07.py --pytest-xml <junit> --smoke   # tiny/fast dry run
Exit 0 iff the verifier reports PASS.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.phase_common import (  # noqa: E402
    ledger_snapshot, protected_fingerprint, sha256_file, sh, utcnow, write_text_atomic,
)
from crypto_regime_lab.ra.ra05_market import (  # noqa: E402
    EMISSIONS_ARTIFACT, load_real_bars, load_real_emissions,
)
from crypto_regime_lab.ra.ra07_cell2 import CELL2_SYMBOL, run_cell2_full  # noqa: E402
from crypto_regime_lab.ra.ra07_controls import (  # noqa: E402
    build_delayed_schedule, build_placebo_schedule, risk_exposure_attribution,
)
from crypto_regime_lab.ra.ra07_coverage import build_coverage_matrix  # noqa: E402
from crypto_regime_lab.ra.ra07_decay import compute_d1_rows, compute_d2_rows, compute_d3_rows  # noqa: E402
from crypto_regime_lab.ra.ra07_freeze import (  # noqa: E402
    BOOTSTRAP_N_RESAMPLES, BOOTSTRAP_SEED, DELAYED_CONTROL_OBSERVATIONS, PLACEBO_CONTROL_SEED,
    build_replication_spec, estimate_mde, materialize_delta,
)
from crypto_regime_lab.ra.ra07_sensitivity import build_sensitivity_report  # noqa: E402
from crypto_regime_lab.ra.ra07_statistics import (  # noqa: E402
    build_multiplicity_ledger, build_support_report, build_uncertainty_results,
)
from crypto_regime_lab.ra.ra07_stats_primitives import (  # noqa: E402
    bootstrap_numeric_reference_check, paired_daily_returns,
)
from crypto_regime_lab.ra.verifier_ra07 import REQUIRED_ARTIFACTS, verify_ra07  # noqa: E402
from crypto_regime_lab.time_edge.execution import PreparedAccount  # noqa: E402
from crypto_regime_lab.experiments.dynamic_fold_provider import (  # noqa: E402
    ZeroSignalStrategy, engine_param_ranges, run_cutoff_walk_forward,
)

STUDY = "regime_time_edge_ra_v1"
RA05_RUN_ID = "ra05-20260918T201236Z-de11db62"
RA06_RUN_ID = "ra06-20260919T035313Z-59cd3ae0"
LEDGER_SQLITE = (LAB / "evidence" / "time_edge_validation_v4" / "allocations"
                 / "TE02-PILOT-R03" / "ledger.sqlite")
PHASE_WALL_CAP_S = 14400.0
ALPHA_ID = "A-SC"
CELL1_SYMBOL = "BTCUSDT"
ACCOUNT_CAPITAL = 20000.0

DEFAULT_WINDOW_START = "2021-01-01"
DEFAULT_WINDOW_END = "2021-04-01"
DEFAULT_DATA_LOAD_START = "2020-11-01"
DEFAULT_TRAIN_MEMORY_DAYS = 45
DEFAULT_CAL_TEST_DAYS = 60
DEFAULT_TRIALS = 8
DEFAULT_SEED = 20260918
DEFAULT_ROUTE = "event"

CASE_NODE_IDS = {
    "R01": ["test_r01_replication_spec_frozen_before_any_new_outcome"],
    "R02": ["test_r02_coverage_matrix_has_20_rows_correct_vocabulary"],
    "R03": ["test_r03_cell2_shares_ra05_contract_except_symbol"],
    "R04": ["test_r04_delayed_emissions_shifts_state_common_not_just_id"],
    "R05": ["test_r05_placebo_never_reads_the_real_evaluation_window_states"],
    "R06": ["test_r06_decay_rows_follow_schema_and_never_average_fold_sharpe"],
    "R07": ["test_r07_bootstrap_is_blocked_paired_and_zero_engine_calls"],
    "R08": ["test_r08_claim_classification_matches_guide_13_5_table"],
    "R09": ["test_r09_multiplicity_holm_applies_to_secondary_family_only"],
}


def build_phase_gate(status: str, research_status: str, gate_results=None, notes=None) -> dict:
    return {
        "schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-07", "guide_version": "RA-GUIDE-1.0",
        "registration_digest": None, "source_dependency_digest": None,
        "implementation_status": "COMPLETE", "technical_gate": status,
        "research_status": research_status,
        "required_gates": ["G07-VALID", "G07-CONTROL", "G07-STATS", "G07-DECAY", "G07-CLAIM"],
        "gate_results": gate_results or [], "mandatory_tests": [], "actual_run_refs": [],
        "verified_reuse_refs": [], "measured_resources": None,
        "protected_state_before_ref": "baseline/protected_before",
        "protected_state_after_ref": "baseline/protected_after",
        "open_blockers": [], "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False, "notes": notes or [],
    }


def build_handoff(run_id: str, verdict: dict, cell1_claim: str) -> str:
    return (
        "# RA-07 handoff\n\n"
        f"- run dir: evidence/{STUDY}/{run_id}/\n"
        f"- technical gate: {verdict['overall']}; primary claim status: {cell1_claim}\n"
        "- approvals: RA-07 owner review PENDING; can_start_next_phase=false\n"
        "- next: RA-08 (freeze, replay, final claims, handoff) only after owner approval AND "
        "after the user's own requested assumption-by-assumption review of RA-05/06/07.\n"
        "- Every RA-07 number in report.md is drawn from committed artifacts in this run dir; "
        "no number here was re-derived by hand.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-xml", required=True)
    parser.add_argument("--smoke", action="store_true",
                        help="tiny/fast config to dry-run the pipeline, not a real replication run")
    args = parser.parse_args()
    phase_started = time.perf_counter()
    prot_before = protected_fingerprint()
    ledger = ledger_snapshot(LEDGER_SQLITE)

    if args.smoke:
        window_start, window_end = "2021-01-01", "2021-01-08"
        data_load_start = "2020-12-01"
        train_memory_days, cal_test_days, trials = 20, 4, 2
        n_resamples = 50
    else:
        window_start, window_end = DEFAULT_WINDOW_START, DEFAULT_WINDOW_END
        data_load_start = DEFAULT_DATA_LOAD_START
        train_memory_days, cal_test_days, trials = (DEFAULT_TRAIN_MEMORY_DAYS,
                                                     DEFAULT_CAL_TEST_DAYS, DEFAULT_TRIALS)
        n_resamples = BOOTSTRAP_N_RESAMPLES
    seed, route = DEFAULT_SEED, DEFAULT_ROUTE

    from crypto_regime_lab.safety.paths import SandboxPolicy

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY, lab_run_id=new_lab_run_id("ra07"))
    run_dir = writer.run_dir
    scratch = run_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    with writer.attempt("ra07_build") as att:
        # === cell 1: load RA-05's own real, already-committed evidence =====
        ra05_arms_path = (LAB / "evidence" / STUDY / RA05_RUN_ID / "arms_result.json")
        cell1_arms = json.loads(ra05_arms_path.read_text())["arms"]

        # cell1_arms ALWAYS comes from RA-05's real, full-scale evidence
        # (never re-run), regardless of --smoke -- so the frame used to
        # replay its folds (D1) and to resolve its real fills' bar_index
        # (delta materialization) must ALWAYS cover RA-05's OWN real window,
        # never the smoke-scale window. In --smoke mode these two frames
        # differ (a smoke frame starting 2020-12-01 assigns completely
        # different timestamps to the same bar_index than RA-05's real frame
        # starting 2020-11-01 does) -- caught by the very first smoke run:
        # TrainingScorer raised "incomplete requested account window"
        # because a late RA-05 fold's train_start fell outside the smoke
        # frame entirely. In the non-smoke (real) run these two loads are
        # identical (same start/end), so this only changes smoke behaviour.
        cell1_real_frame, _ = load_real_bars(CELL1_SYMBOL, start=DEFAULT_DATA_LOAD_START,
                                             end=DEFAULT_WINDOW_END)
        cell1_real_frame = cell1_real_frame[["open", "high", "low", "close", "volume"]].copy()
        cell1_real_prepared = PreparedAccount(cell1_real_frame)

        cell1_frame, cell1_partitions = load_real_bars(CELL1_SYMBOL, start=data_load_start,
                                                        end=window_end)
        cell1_frame = cell1_frame[["open", "high", "low", "close", "volume"]].copy()
        # (no PreparedAccount needed here: delayed/placebo controls call
        # run_cutoff_walk_forward directly on cell1_frame, same as cell2)
        cell1_window_emissions_doc = load_real_emissions(window_start=window_start,
                                                          window_end=window_end)
        cell1_window_emissions = cell1_window_emissions_doc["emissions"]
        full_emissions = json.loads(EMISSIONS_ARTIFACT.read_text())["emissions"]

        # === RA07.1: freeze delta/MDE from cell 1's real fills, BEFORE any
        # new RA-07 outcome exists =========================================
        regime_equity = ((cell1_arms.get("M4_REGIME", {}).get("run", {}).get("account") or {}))
        cal_matched_equity = ((cell1_arms.get("M4_CAL_MATCHED", {}).get("run", {}).get("account") or {}))
        delta_fills = (regime_equity.get("fills") or []) + (cal_matched_equity.get("fills") or [])
        delta_equity_daily = (regime_equity.get("equity_daily") or []) or (
            cal_matched_equity.get("equity_daily") or [])
        delta_result = materialize_delta(fills=delta_fills, equity_daily=delta_equity_daily,
                                         frame_index=cell1_real_frame.index,
                                         account_capital=ACCOUNT_CAPITAL)
        cell1_paired_primary = paired_daily_returns(regime_equity.get("equity_daily") or [],
                                                     cal_matched_equity.get("equity_daily") or [])
        mde_result = estimate_mde(cell1_paired_primary, n_resamples=n_resamples, seed=BOOTSTRAP_SEED)

        cell2_plan = {
            "alpha_id": ALPHA_ID, "symbol": CELL2_SYMBOL,
            "selection_rule": ("capability/coverage: A-SC is one of only 2 route-qualified "
                              "alphas (A-SC, A-HMA) on the event route; ETHUSDT chosen for "
                              "cross-symbol transfer, explicitly testing whether a BTC-derived "
                              "regime tape's timing transfers to a different, correlated symbol "
                              "-- never chosen for its PnL, which was not known before this "
                              "plan was written"),
            "contract": "identical to RA-05 cell 1's discovery_spec (window/train_memory/trials/"
                       "seed/route), symbol swapped only",
        }
        spec = build_replication_spec(ra05_run_id=RA05_RUN_ID, cell1=cell1_arms,
                                      cell2_plan=cell2_plan, delta_result=delta_result,
                                      mde_result=mde_result)
        writer.write_json("replication_spec.json", spec, schema="regime_lab.ra07_replication_spec.v1")

        # === RA07.2: run cell 2 under the frozen contract ===================
        cell2 = run_cell2_full(
            alpha_id=ALPHA_ID, symbol=CELL2_SYMBOL, window_start=window_start,
            window_end=window_end, data_load_start=data_load_start,
            train_memory_days=train_memory_days, cal_test_days=cal_test_days, trials=trials,
            seed=seed, route=route, full_emissions_for_forecast=full_emissions,
            window_emissions=cell1_window_emissions, evidence_dir=scratch / "cell2",
            lab_run_id=writer.lab_run_id)
        cell2_frame = cell2.pop("_frame", None)
        cell2_prepared = cell2.pop("_prepared", None)
        writer.write_json("cell2_result.json", cell2, schema="regime_lab.ra07_cell2_result.v1")

        coverage = build_coverage_matrix(
            cell1={"alpha_id": ALPHA_ID, "symbol": CELL1_SYMBOL, "run_ref": f"{RA05_RUN_ID}",
                  "arms_present": [n for n, o in cell1_arms.items() if o.get("ok")]},
            cell2={"alpha_id": ALPHA_ID, "symbol": CELL2_SYMBOL, "run_ref": writer.lab_run_id,
                  "arms_present": [n for n, o in (cell2.get("arms") or {}).items() if o.get("ok")]})
        writer.write_json("complete_coverage_matrix.json", coverage,
                          schema="regime_lab.ra07_coverage_matrix.v1")

        # === RA07.3: controls ================================================
        delayed_schedule = build_delayed_schedule(
            cell1_window_emissions, window_start=window_start, window_end=window_end,
            train_memory_days=train_memory_days, observations=DELAYED_CONTROL_OBSERVATIONS)
        delayed_result = run_cutoff_walk_forward(
            ALPHA_ID, cell1_frame, delayed_schedule, param_ranges=engine_param_ranges(ALPHA_ID),
            strategy_class=ZeroSignalStrategy, optuna_trials=trials, seed=seed, route=route)

        placebo_build = build_placebo_schedule(
            full_emissions=full_emissions, window_emissions=cell1_window_emissions,
            window_start=window_start, window_end=window_end,
            train_memory_days=train_memory_days, seed=PLACEBO_CONTROL_SEED)
        if placebo_build["status"] == "OK":
            placebo_result = run_cutoff_walk_forward(
                ALPHA_ID, cell1_frame, placebo_build["schedule"],
                param_ranges=engine_param_ranges(ALPHA_ID), strategy_class=ZeroSignalStrategy,
                optuna_trials=trials, seed=seed, route=route)
            placebo_status = "OK" if placebo_result.get("ok") else "RUN_FAILED"
        else:
            placebo_result = None
            placebo_status = placebo_build["status"]

        risk_cell1 = risk_exposure_attribution(
            regime_outcome=cell1_arms.get("M4_REGIME", {}),
            cal_matched_outcome=cell1_arms.get("M4_CAL_MATCHED", {}),
            # cell1_arms is ALWAYS RA-05's real evidence -- frame_index/window_days
            # must match that real window, not this run's smoke-or-real window
            # (same bar_index-mismatch class the D1/delta fix above addresses).
            frame_index=cell1_real_frame.index,
            window_days=(pd.Timestamp(DEFAULT_WINDOW_END) - pd.Timestamp(DEFAULT_WINDOW_START)).days)
        risk_cell2 = risk_exposure_attribution(
            regime_outcome=(cell2.get("arms") or {}).get("M4_REGIME", {}),
            cal_matched_outcome=(cell2.get("arms") or {}).get("M4_CAL_MATCHED", {}),
            frame_index=(cell2_frame.index if cell2_frame is not None else cell1_frame.index),
            window_days=(pd.Timestamp(window_end) - pd.Timestamp(window_start)).days)

        control_results = {
            "CALENDAR_BUDGET_MATCHED": {"status": "ALREADY_AVAILABLE",
                                        "cell1_ref": "M4_CAL_MATCHED arm in RA-05 arms_result.json",
                                        "cell2_ref": "M4_CAL_MATCHED arm in cell2_result.json"},
            "AGE_ONLY": {"status": "NOT_APPLICABLE",
                        "reason": "RA-06 locked KEEP_BASELINE (support=5 < min_required=8); no "
                                  "action-aware policy exists to contrast against AGE_ONLY"},
            "DELAYED_INFORMATION": {
                "status": "OK" if delayed_result.get("ok") else "RUN_FAILED",
                "delay_observations": DELAYED_CONTROL_OBSERVATIONS,
                "schedule_cutoff_count": len(delayed_schedule.cutoffs),
                "fold_count": len(delayed_result.get("fold_selection_table") or []),
                "wall_seconds": delayed_result.get("wall_seconds"),
                "equity_last": (delayed_result.get("account") or {}).get("equity_last"),
                "equity_daily": (delayed_result.get("account") or {}).get("equity_daily"),
                "error": delayed_result.get("error"),
            },
            "PLACEBO_TIMING": {
                "status": placebo_status,
                "seed": PLACEBO_CONTROL_SEED,
                "development_states_count": placebo_build.get("development_states_count"),
                "window_observations_count": placebo_build.get("window_observations_count"),
                "schedule_cutoff_count": (len(placebo_build["schedule"].cutoffs)
                                          if placebo_build.get("schedule") else None),
                "fidelity": placebo_build.get("fidelity"),
                "fold_count": (len(placebo_result.get("fold_selection_table") or [])
                              if placebo_result and placebo_result.get("ok") else None),
                "wall_seconds": placebo_result.get("wall_seconds") if placebo_result else None,
                "equity_last": ((placebo_result.get("account") or {}).get("equity_last")
                               if placebo_result and placebo_result.get("ok") else None),
                "equity_daily": ((placebo_result.get("account") or {}).get("equity_daily")
                                if placebo_result and placebo_result.get("ok") else None),
                "error": placebo_result.get("error") if placebo_result else placebo_build["status"],
            },
            "RISK_EXPOSURE_ATTRIBUTION": {"status": "OK", "cell1": risk_cell1, "cell2": risk_cell2},
        }
        writer.write_json("control_results.json", control_results,
                          schema="regime_lab.ra07_control_results.v1")
        writer.write_json("cost_risk_attribution.json", {"cell1": risk_cell1, "cell2": risk_cell2},
                          schema="regime_lab.ra07_cost_risk_attribution.v1")

        # === RA07.4: decay D1/D2/D3 =========================================
        decay_rows = []
        # cell1_arms is RA-05's real evidence -> replay against cell1_real_prepared
        # (RA-05's own real window), never the smoke-or-real cell1_prepared.
        for symbol, arms, prepared_acct in ((CELL1_SYMBOL, cell1_arms, cell1_real_prepared),
                                            (CELL2_SYMBOL, cell2.get("arms") or {}, cell2_prepared)):
            if prepared_acct is None:
                continue
            for arm_name in ("M4_CAL", "M4_CAL_MATCHED", "M4_REGIME"):
                outcome = arms.get(arm_name)
                if not outcome or not outcome.get("ok"):
                    continue
                fold_table = outcome["run"].get("fold_selection_table") or []
                equity_daily = (outcome["run"].get("account") or {}).get("equity_daily") or []
                window_end_for_arm = outcome["run"].get("requested", {}).get("window_end") or (
                    fold_table[-1]["test_end"] if fold_table else window_end)
                for index, fold_row in enumerate(fold_table):
                    deploy_end = (fold_table[index + 1]["test_start"] if index + 1 < len(fold_table)
                                 else fold_row.get("test_end") or window_end_for_arm)
                    decay_rows.extend(compute_d1_rows(
                        prepared=prepared_acct, alpha_id=ALPHA_ID, symbol=symbol, arm=arm_name,
                        fold_row=fold_row, equity_daily=equity_daily, deploy_end=deploy_end,
                        evidence_dir=scratch / "d1" / symbol / arm_name / str(index),
                        lab_run_id=writer.lab_run_id, regime_at_selection=None))
                decay_rows.extend(compute_d3_rows(fold_selection_table=fold_table,
                                                  equity_daily=equity_daily, alpha_id=ALPHA_ID,
                                                  symbol=symbol, arm=arm_name))
        panel_b_path = LAB / "evidence" / STUDY / RA06_RUN_ID / "panel_b.json"
        panel_b_rows = json.loads(panel_b_path.read_text())["rows"]
        decay_rows.extend(compute_d2_rows(panel_b_rows=panel_b_rows, alpha_id=ALPHA_ID,
                                          symbol=CELL1_SYMBOL, window_start=window_start,
                                          account_capital=ACCOUNT_CAPITAL))
        decay_table = {"schema": "regime_lab.ra07_decay_table.v1", "rows": decay_rows,
                       "row_count": len(decay_rows),
                       "by_comparison_kind": {kind: sum(1 for r in decay_rows if r["comparison_kind"] == kind)
                                              for kind in ("D1_IS_TO_OOS", "D2_PARAMETER_AGE",
                                                          "D3_ADJACENT_OPERATIONAL_FOLDS")},
                       "source_ra06_run_id": RA06_RUN_ID}
        writer.write_json("decay_table.json", decay_table, schema="regime_lab.ra07_decay_table.v1")

        # === RA07.5: statistics on stored outcomes, zero engine calls =======
        paired_accounts = {
            "schema": "regime_lab.ra07_paired_accounts.v1",
            "cell1_primary": cell1_paired_primary,
            "cell2_primary": paired_daily_returns(
                ((cell2.get("arms") or {}).get("M4_REGIME", {}).get("run", {}).get("account") or {})
                .get("equity_daily") or [],
                ((cell2.get("arms") or {}).get("M4_CAL_MATCHED", {}).get("run", {}).get("account") or {})
                .get("equity_daily") or []),
        }
        writer.write_json("paired_accounts.json", paired_accounts,
                          schema="regime_lab.ra07_paired_accounts.v1")

        uncertainty = build_uncertainty_results(
            cell1_arms=cell1_arms, cell2_arms=cell2.get("arms") or {},
            delta=delta_result.get("delta"), bootstrap_plan=spec["bootstrap_plan"])
        writer.write_json("uncertainty_results.json", uncertainty,
                          schema="regime_lab.ra07_uncertainty_results.v1")
        multiplicity = build_multiplicity_ledger(uncertainty)
        writer.write_json("multiplicity_ledger.json", multiplicity,
                          schema="regime_lab.ra07_multiplicity_ledger.v1")
        self_check = bootstrap_numeric_reference_check(seed=BOOTSTRAP_SEED, n_resamples=max(n_resamples, 1000))
        writer.write_json("bootstrap_self_check.json", self_check,
                          schema="regime_lab.ra07_bootstrap_numeric_reference_check.v1")

        support = build_support_report(
            uncertainty_results=uncertainty,
            cell1_meta={"unique_selections": len(set(json.dumps(r["selected_params"], sort_keys=True)
                                                     for r in cell1_arms.get("M4_REGIME", {})
                                                     .get("run", {}).get("fold_selection_table", []))),
                       "switches_admitted": cell1_arms.get("M4_REGIME", {}).get("switches_admitted")},
            cell2_meta={"unique_selections": len(set(json.dumps(r["selected_params"], sort_keys=True)
                                                     for r in (cell2.get("arms") or {}).get("M4_REGIME", {})
                                                     .get("run", {}).get("fold_selection_table", []))),
                       "switches_admitted": (cell2.get("arms") or {}).get("M4_REGIME", {})
                       .get("switches_admitted")})
        writer.write_json("support_report.json", support, schema="regime_lab.ra07_support_report.v1")

        # === RA07.7: sensitivity =============================================
        sensitivity = build_sensitivity_report(
            cell1_arms=cell1_arms, cell2_arms=cell2.get("arms") or {},
            uncertainty_results=uncertainty, cell1_window_emissions=cell1_window_emissions)
        writer.write_json("sensitivity_report.json", sensitivity,
                          schema="regime_lab.ra07_sensitivity_report.v1")

        # === manifest / gate / report =======================================
        import importlib.metadata as md

        def version(name):
            try:
                return md.version(name)
            except Exception:
                return None

        phase_wall = round(time.perf_counter() - phase_started, 1)
        snapshot = {k: ledger.get(k) for k in ("spent", "attempts", "budget")}
        baseline = {
            "git_branch": sh(["git", "branch", "--show-current"], cwd=LAB),
            "git_head_full": sh(["git", "rev-parse", "HEAD"], cwd=LAB),
            "engine_version": version("quantbt-engine"), "native_version": version("quantbt-native"),
            "protected_before": prot_before, "ledger_before": snapshot, "ledger_after": snapshot,
            "phase_wall_cap_s": PHASE_WALL_CAP_S, "phase_measured_wall_s": phase_wall,
            "started_at": utcnow(), "cell1_market_partitions_used": cell1_partitions,
            "cell2_market_partitions_used": cell2.get("market_partitions_used"),
        }
        writer.write_json("baseline_identity.json", baseline, schema="regime_lab.ra07_baseline.v1")

        def manifest_records():
            return [{"relpath": name, "sha256": sha256_file(run_dir / name),
                    "size_bytes": (run_dir / name).stat().st_size}
                   for name in REQUIRED_ARTIFACTS
                   if name not in ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
                   and (run_dir / name).is_file()]

        writer.write_json("phase_manifest.json", {
            "required_gates": ["G07-VALID", "G07-CONTROL", "G07-STATS", "G07-DECAY", "G07-CLAIM"],
            "artifacts": manifest_records(),
            "source_dependency_digests": {"lab_head": baseline["git_head_full"],
                                          "endpoint_protected": prot_before.get("endpoint_sha256")},
            "approvals": {"ra07_review": "PENDING"},
        }, schema="regime_lab.ra07_manifest.v1")

        primary_claim = (uncertainty.get("primary") or {}).get("claim", {}).get("status", "NOT_EVALUABLE")
        writer.write_json("phase_gate.json", build_phase_gate("PENDING_VERIFICATION", primary_claim),
                          schema="regime_lab.ra_phase_gate.v1")
        write_text_atomic(run_dir / "report.md", "# RA-07 report - PENDING_VERIFICATION\n")
        write_text_atomic(run_dir / "handoff.md", "# RA-07 handoff - PENDING_VERIFICATION\n")
        prot_after = protected_fingerprint()

        gate_doc = build_phase_gate("PENDING_VERIFICATION", primary_claim,
                                    notes=["verify ran over the frozen artifact set incl. this receipt"])
        junit = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        try:
            import xml.etree.ElementTree as ET

            xml_root = ET.parse(args.pytest_xml).getroot()
            suites = xml_root.findall("testsuite") or [xml_root]
            junit = {"tests": sum(int(s.get("tests", 0)) for s in suites),
                    "failures": sum(int(s.get("failures", 0)) for s in suites),
                    "errors": sum(int(s.get("errors", 0)) for s in suites),
                    "skipped": sum(int(s.get("skipped", 0)) for s in suites)}
        except Exception:
            pass
        gate_doc["mandatory_tests"] = [{"command": " ".join(sys.argv), **junit}]
        gate_doc["measured_resources"] = {"phase_wall_s": phase_wall}
        gate_doc["actual_run_refs"] = ["cell2_result.json", "control_results.json", "decay_table.json",
                                       "uncertainty_results.json"]
        gate_doc["verified_reuse_refs"] = [f"RA-05 arms_result.json ({RA05_RUN_ID})",
                                           f"RA-06 panel_b.json ({RA06_RUN_ID})",
                                           "dynamic_fold_provider.run_cutoff_walk_forward"]
        gate_doc["protected_state_after_ref"] = "protected status: " + (prot_after["git_status_porcelain"] or "clean")
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        # verify_ra07 checks report.md's OWN text (conclusion_level), which
        # creates a fixed-point problem: the report's displayed gate table
        # wants the FINAL verdict, but that verdict wants the real report to
        # already exist. Resolved in two passes -- pass 1's verdict is used
        # only to draft the report/handoff (their own embedded gate table may
        # show a stale G07-CLAIM here, since report.md was still the
        # PENDING_VERIFICATION placeholder when pass 1 ran); pass 2 re-verifies
        # against the now-real report and REWRITES report/handoff with that
        # settled verdict, so the persisted files and their own displayed
        # gate table agree. Rewriting cannot flip pass 2's own verdict: the
        # only report-content check (conclusion_level's presence) was already
        # satisfied by pass 1's write and is untouched by the rewrite.
        # Caught by this phase's own --smoke run, not assumed correct.
        manifest_doc = json.loads((run_dir / "phase_manifest.json").read_text())
        manifest_doc["artifacts"] = manifest_records()
        writer.write_json("phase_manifest.json", manifest_doc, schema="regime_lab.ra07_manifest.v1")

        pass1_verdict = verify_ra07(run_dir, pytest_xml=args.pytest_xml,
                                    protected_status_after=prot_after["git_status_porcelain"])
        write_text_atomic(run_dir / "report.md", build_report(
            spec=spec, delta_result=delta_result, mde_result=mde_result, coverage=coverage,
            cell2=cell2, control_results=control_results, decay_table=decay_table,
            uncertainty=uncertainty, multiplicity=multiplicity, support=support,
            sensitivity=sensitivity, self_check=self_check, run_id=writer.lab_run_id,
            verdict=pass1_verdict, primary_claim=primary_claim))
        write_text_atomic(run_dir / "handoff.md",
                          build_handoff(writer.lab_run_id, pass1_verdict, primary_claim))

        verdict = verify_ra07(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        write_text_atomic(run_dir / "report.md", build_report(
            spec=spec, delta_result=delta_result, mde_result=mde_result, coverage=coverage,
            cell2=cell2, control_results=control_results, decay_table=decay_table,
            uncertainty=uncertainty, multiplicity=multiplicity, support=support,
            sensitivity=sensitivity, self_check=self_check, run_id=writer.lab_run_id,
            verdict=verdict, primary_claim=primary_claim))
        write_text_atomic(run_dir / "handoff.md",
                          build_handoff(writer.lab_run_id, verdict, primary_claim))
        gate_doc["technical_gate"] = verdict["overall"]
        gate_doc["gate_results"] = [{"gate_id": gid, "status": "PASS" if g["pass"] else "FAIL",
                                     "reasons": g["reasons"][:3]} for gid, g in verdict["gates"].items()]
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")
        writer.write_json("verification.json", verdict, schema="regime_lab.ra07_verification.v1")
        att.detail = {"run_dir": str(run_dir), "overall": verdict["overall"]}

    print(json.dumps({"run_dir": str(run_dir), "overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()}}, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


def build_report(*, spec, delta_result, mde_result, coverage, cell2, control_results, decay_table,
                 uncertainty, multiplicity, support, sensitivity, self_check, run_id, verdict,
                 primary_claim) -> str:
    gate_rows = "\n".join(
        f"| {gid} | PASS | {'PASS' if g['pass'] else 'FAIL'} | {run_id}/phase_manifest.json | "
        f"{'PASS' if g['pass'] else 'FAIL'} |"
        for gid, g in verdict["gates"].items())
    cov_counts = coverage["counts"]
    primary = uncertainty["primary"]
    boot = primary.get("bootstrap") or {}
    return f"""# RA-07 - Replication co gioi han, falsification, decay va inference

## 1. Status va scope
- Technical gate: **{verdict['overall']}**.
- **conclusion_level: {primary_claim}** (registered vocabulary, guide 13.5's claim-gate table;
  this is the primary H-BUDGET contrast's status -- see section 6 for the CI/delta it was
  derived from, and section 4/9 for the controls/sensitivity that qualify how much this status
  can carry).
- Branch `mode4-corrective`, guide RA-GUIDE-1.0 (section 11), study `regime_time_edge_ra_v1`, run `{run_id}`.
- Primary contrast (guide RA07.1, RA-01 H-BUDGET): {spec['primary_contrast']}.
- Action-aware contrast: {spec['action_aware_contrast']['reason']}

## 2. Economic threshold delta and MDE (RA07.1, frozen before any RA-07 outcome)
- delta (guide 13.3 formula, calibrated from cell-1's real fills): status={delta_result.get('status')},
  value={delta_result.get('delta')}, calibration_days={delta_result.get('calibration_days')}.
- MDE (guide 13.6, from cell-1's own paired daily-return variability): status={mde_result.get('status')},
  value={mde_result.get('mde')}.
- RF-05 cross-reference (different contract, never substituted): {spec['mde_cross_reference']['rf05_corrected_daily_account_bps']} bps/day.

## 3. Coverage matrix (RA07.2)
- {cov_counts['RUN_VALID']} RUN_VALID / {cov_counts['BLOCKED_CAPABILITY']} BLOCKED_CAPABILITY / {cov_counts['NOT_RUN_BUDGET']} NOT_RUN_BUDGET of {cov_counts['planned_cells']} planned cells.
- Cell 2: {cell2.get('alpha_id')}/{cell2.get('symbol')}, capability_status={cell2.get('capability_status')}.
  {cell2.get('transfer_kind_note', '')}

## 4. Controls (RA07.3)
- CALENDAR_BUDGET_MATCHED: {control_results['CALENDAR_BUDGET_MATCHED']['status']}
- AGE_ONLY: {control_results['AGE_ONLY']['status']} -- {control_results['AGE_ONLY']['reason']}
- DELAYED_INFORMATION: {control_results['DELAYED_INFORMATION']['status']}, equity_last={control_results['DELAYED_INFORMATION'].get('equity_last')}
- PLACEBO_TIMING: {control_results['PLACEBO_TIMING']['status']}, fidelity_matched={((control_results['PLACEBO_TIMING'].get('fidelity') or {}).get('matched'))}, equity_last={control_results['PLACEBO_TIMING'].get('equity_last')}
- RISK_EXPOSURE_ATTRIBUTION: {control_results['RISK_EXPOSURE_ATTRIBUTION']['status']}

## 5. Decay D1/D2/D3 (RA07.4)
- rows: {decay_table['row_count']} total, by kind: {decay_table['by_comparison_kind']}

## 6. Bootstrap statistics (RA07.5, zero engine calls)
- Primary contrast n_common_days={primary.get('n_common_days')}, n_blocks={primary.get('n_blocks_at_primary_length')}
- point_estimate={boot.get('point_estimate')}, CI_95={boot.get('ci_95')}, p={boot.get('p_value_two_sided')}
- claim: {primary.get('claim', {}).get('status')} -- conclusion_level for this contrast.
- Numeric reference self-check (synthetic data only): pass={self_check.get('pass')}

## 7. Multiplicity (RA07.5)
- primary unadjusted: {multiplicity['primary_unadjusted']}
- secondary Holm family: {json.dumps(multiplicity['secondary_family_holm'])}

## 8. Support and power (RA07.6)
{support['honest_summary']}

## 9. Sensitivity (RA07.7)
- leave-one-cell-out: {json.dumps(sensitivity['leave_one_cell_out'])}

## 10. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref | Status |
|---|---|---|---|---|
{gate_rows}

## 11. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Owner decisions pending: this phase's review; can_start_next_phase=false.

## 12. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra07.py --pytest-xml <junit>` (new run_id per attempt;
  prior runs immutable). `--smoke` runs a tiny/fast config to dry-run the pipeline.
- Next permissible action: user-requested assumption review of RA-05/06/07, then RA-08 only
  after separate owner approval of this phase.
"""


if __name__ == "__main__":
    raise SystemExit(main())
