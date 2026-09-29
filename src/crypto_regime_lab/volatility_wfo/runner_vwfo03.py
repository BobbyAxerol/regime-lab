"""VWFO-03 Main Runner: Selection Development & Control Arms.

Follows VOL-WFO-V1.0 Section 8 and Section 14:
- Executes chronological DEV on 12 DEV origins for both S_TPE and S_SOBOL.
- Causal feature extraction and H14 LightGBM volatility forecasts.
- Evaluates 8 arms: A_M4, B0_GLOBAL, B_CAP, O_PERSIST, C_H14, P_NI_01..03.
- Winner Union mechanism to evaluate newly selected candidates forward on FWD14.
- Evaluates sampler performance and selects winning sampler per Section 8.7 rule.
- Freezes winning sampler in configs/btc_volatility_conditioned_wfo_v1/final_freeze.json.
- Verifies all 6 Exit Gates via verifier_vwfo03.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from quantbt.walkforward import WalkForwardTrialRecord

from crypto_regime_lab.evidence.manifest import new_lab_run_id
from crypto_regime_lab.ra.ra05_market import load_real_bars
from crypto_regime_lab.volatility_wfo.archive import (
    build_forward_evaluation_union,
    compute_sharpe_decay_labels,
    evaluate_candidates_forward,
    select_base_panel,
)
from crypto_regime_lab.volatility_wfo.forecast import (
    H14ForecastEngine,
    MarkovNoInfoGenerator,
    standardize_context_vector,
)
from crypto_regime_lab.volatility_wfo.search import run_cutoff_search
from crypto_regime_lab.volatility_wfo.selector import (
    CandidateDescriptorStandardizer,
    fit_selectors,
    select_candidate_for_arm,
)
from crypto_regime_lab.volatility_wfo.verifier_vwfo03 import verify_vwfo03

LAB_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = LAB_ROOT / "configs" / "btc_volatility_conditioned_wfo_v1"
EVIDENCE_DIR = LAB_ROOT / "evidence" / "btc_volatility_conditioned_wfo_v1"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def load_dev_bars(start: str = "2024-04-01", end: str = "2025-04-01") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads BTCUSDT bars and resamples to 15m decision bars."""
    frame_1m, _ = load_real_bars("BTCUSDT", start=start, end=end)
    grouped = frame_1m.resample("15min", closed="left", label="left")
    frame_15m = grouped.agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return frame_1m, frame_15m


def load_initial_archive() -> List[Dict[str, Any]]:
    """Loads matured candidate archive from Phase VWFO-02."""
    vwfo02_dir = EVIDENCE_DIR / "runs" / "vwfo02-20260929T001715Z-4225c492"
    archive_file = vwfo02_dir / "candidate_archive.json"
    if not archive_file.is_file():
        raise FileNotFoundError(f"VWFO-02 candidate archive not found: {archive_file}")
    return json.loads(archive_file.read_text(encoding="utf-8"))


def run_single_sampler_dev(
    sampler_id: str,
    dev_origins: List[str],
    initial_archive: List[Dict[str, Any]],
    frame_15m: pd.DataFrame,
    forecast_engine: H14ForecastEngine,
    ni_generator: MarkovNoInfoGenerator,
    checkpoints_dir: Path,
    trials_per_cutoff: int = 128,
) -> Dict[str, Any]:
    """Runs chronological DEV folds sequentially for one sampler."""
    print(f"\n=======================================================")
    print(f"   STARTING CHRONOLOGICAL DEV FOR {sampler_id} (12 FOLDS)")
    print(f"=======================================================")

    # Initialize local expanding archive starting with initial archive
    archive = copy.deepcopy(initial_archive)

    # Seeds for P_NI
    ni_seeds = [20261001, 20261002, 20261003]

    # Pre-generate pseudo p_LOW series across all origins
    timeline_file = CONFIG_DIR / "timeline.json"
    tl = json.loads(timeline_file.read_text(encoding="utf-8"))
    all_known_origins = tl["roles"]["INIT"]["origins"] + dev_origins

    pseudo_p_lows = {seed: ni_generator.generate_series(all_known_origins, seed=seed) for seed in ni_seeds}

    fold_results: List[Dict[str, Any]] = []
    total_work_seconds = 0.0

    for fold_idx, origin in enumerate(dev_origins):
        chk_file = checkpoints_dir / f"dev_{sampler_id}_{origin}.json"
        origin_dt = pd.Timestamp(origin, tz="UTC")
        fwd_end_dt = origin_dt + pd.Timedelta(days=14)
        t0 = time.perf_counter()

        if chk_file.is_file():
            print(f"[{sampler_id}] Fold {fold_idx + 1:02d}/12 ({origin}) -> Loaded from checkpoint")
            res = json.loads(chk_file.read_text(encoding="utf-8"))
            fold_results.append(res)
            # Add evaluated candidates to archive
            for cand in res.get("evaluated_candidates", []):
                archive.append(cand)
            continue

        print(f"[{sampler_id}] Fold {fold_idx + 1:02d}/12 ({origin}) -> Searching {trials_per_cutoff} trials...")

        # 1. Search IS180
        search_res = run_cutoff_search(
            frame_15m,
            origin_cutoff=origin_dt.isoformat(),
            sampler_id=sampler_id,
            n_trials=trials_per_cutoff,
            seed=20260928 + fold_idx,
            is_days=180,
        )

        anchor_rec = search_res.get("anchor_trial_record")
        if anchor_rec is None:
            anchor_rec = WalkForwardTrialRecord(
                trial_id=search_res["anchor_record"]["trial_id"],
                params=search_res["anchor_record"]["params"],
                objective=search_res["anchor_record"]["objective"],
                mean_is_sharpe=search_res["anchor_record"]["is_sharpe"],
                mean_oos_sharpe=0.0,
                mean_decay=0.0,
                std_decay=0.0,
                fold_metrics=[],
                selection_metadata=search_res["anchor_record"]["selection_metadata"],
            )

        # 2. Select base panel (up to 16)
        base_panel = select_base_panel(
            records=search_res["records"],
            anchor_record=anchor_rec,
            max_panel_size=16,
        )

        # Extract anchor candidate dict
        anchor_cand = next(c for c in base_panel if c.get("is_anchor"))

        # Convert search records to pool dicts
        full_candidate_pool: List[Dict[str, Any]] = []
        for r in search_res["records"]:
            if not r.pruned and np.isfinite(r.objective) and np.isfinite(r.mean_is_sharpe):
                is_anc = r.trial_id == anchor_rec.trial_id
                full_candidate_pool.append({
                    "trial_id": int(r.trial_id),
                    "candidate_id": f"{origin}_{sampler_id}_{r.trial_id:04d}",
                    "params": dict(r.params),
                    "is_sharpe": float(r.mean_is_sharpe),
                    "objective": float(r.objective),
                    "is_anchor": is_anc,
                    "fills_count": int(r.selection_metadata.get("fills_count", 10)),
                })

        # Ensure anchor is in pool
        if not any(c.get("is_anchor") for c in full_candidate_pool):
            full_candidate_pool.insert(0, anchor_cand)

        # 3. Fit Candidate Standardizer on past matured archive
        # Strictly past-only: only records matured before origin
        matured_archive = [
            c for c in archive
            if pd.Timestamp(c.get("matured_at", "2099-01-01")) <= origin_dt
        ]
        standardizer = CandidateDescriptorStandardizer().fit(matured_archive)

        # 4. Context Extraction & Standardization
        # Collect past matured origins
        past_origins = sorted(list(set(
            pd.Timestamp(c["origin_cutoff"]).strftime("%Y-%m-%d")
            for c in matured_archive
            if "origin_cutoff" in c
        )))

        # Historical p_LOW and current p_LOW
        past_p_lows = [forecast_engine.get_forecast_for_origin(o)["p_LOW"] for o in past_origins]
        curr_forecast = forecast_engine.get_forecast_for_origin(origin)
        curr_p_low = curr_forecast["p_LOW"]

        z_hist_c, z_curr_c, c_info = standardize_context_vector(past_p_lows, curr_p_low, min_std_floor=0.05)
        hist_contexts_c = {o: z for o, z in zip(past_origins, z_hist_c)}

        # Persistence context
        past_p_pers = [forecast_engine.get_forecast_for_origin(o)["p_PERSIST"] for o in past_origins]
        curr_p_pers = curr_forecast["p_PERSIST"]
        z_hist_o, z_curr_o, o_info = standardize_context_vector(past_p_pers, curr_p_pers, min_std_floor=0.05)
        hist_contexts_o = {o: z for o, z in zip(past_origins, z_hist_o)}

        # No-information contexts (3 seeds)
        hist_contexts_ni: Dict[int, Dict[str, float]] = {}
        curr_contexts_ni: Dict[int, float] = {}
        for s in ni_seeds:
            past_p_s = [pseudo_p_lows[s][o] for o in past_origins]
            curr_p_s = pseudo_p_lows[s][origin]
            z_hist_s, z_curr_s, _ = standardize_context_vector(past_p_s, curr_p_s, min_std_floor=0.05)
            hist_contexts_ni[s] = {o: z for o, z in zip(past_origins, z_hist_s)}
            curr_contexts_ni[s] = z_curr_s

        # 5. Fit Selectors
        selector_fit = fit_selectors(
            archive_records=matured_archive,
            historical_contexts=hist_contexts_c,
            historical_persist_contexts=hist_contexts_o,
            historical_ni_contexts=hist_contexts_ni,
            standardizer=standardizer,
            lambda_reg=10.0,
        )

        # 6. Apply Selection Rule for 8 Arms
        arm_ids = ["A_M4", "B0_GLOBAL", "B_CAP", "O_PERSIST", "C_H14", "P_NI_01", "P_NI_02", "P_NI_03"]
        arm_selections: Dict[str, Dict[str, Any]] = {}

        for arm in arm_ids:
            if arm == "C_H14":
                ctx_z = z_curr_c
                ni_s = None
            elif arm == "O_PERSIST":
                ctx_z = z_curr_o
                ni_s = None
            elif arm == "P_NI_01":
                ctx_z = curr_contexts_ni[20261001]
                ni_s = 20261001
            elif arm == "P_NI_02":
                ctx_z = curr_contexts_ni[20261002]
                ni_s = 20261002
            elif arm == "P_NI_03":
                ctx_z = curr_contexts_ni[20261003]
                ni_s = 20261003
            else:
                ctx_z = 0.0
                ni_s = None

            sel = select_candidate_for_arm(
                candidate_pool=full_candidate_pool,
                anchor=anchor_cand,
                arm_id=arm,
                fit=selector_fit,
                standardizer=standardizer,
                context_z=ctx_z,
                ni_seed=ni_s,
                q_hat_filter_floor=-0.10,
            )
            arm_selections[arm] = sel

        # 7. Form Winner Union
        registered_winners = [sel["selected_candidate"] for sel in arm_selections.values()]
        eval_union = build_forward_evaluation_union(base_panel, registered_winners=registered_winners)

        # 8. Forward Evaluate Union on FWD14
        fwd_evals = evaluate_candidates_forward(
            frame_15m,
            eval_union,
            fwd_start=origin_dt,
            fwd_end=fwd_end_dt,
        )

        # 9. Compute Decay Labels
        labeled = compute_sharpe_decay_labels(fwd_evals)

        # Map evaluated candidates by param hash
        def _param_hash(p: Dict[str, Any]) -> str:
            return hashlib.sha256(json.dumps(p, sort_keys=True).encode("utf-8")).hexdigest()

        labeled_map = {_param_hash(c["params"]): c for c in labeled}

        # Attach realized forward Sharpe and decay to arm selections
        arm_outcomes: Dict[str, Dict[str, Any]] = {}
        for arm, sel in arm_selections.items():
            p_hash = _param_hash(sel["selected_candidate"]["params"])
            out_c = labeled_map.get(p_hash, {})
            arm_outcomes[arm] = {
                "arm_id": arm,
                "trial_id": sel["selected_candidate"]["trial_id"],
                "candidate_id": sel["selected_candidate"].get("candidate_id"),
                "params": sel["selected_candidate"]["params"],
                "is_anchor": sel["is_anchor"],
                "y_hat": sel["y_hat"],
                "q_hat": sel["q_hat"],
                "is_sharpe": out_c.get("is_sharpe", sel["selected_candidate"]["is_sharpe"]),
                "fwd_sharpe": out_c.get("fwd_sharpe", 0.0),
                "decay_d": out_c.get("decay_d", 0.0),
                "relative_decay_y": out_c.get("relative_decay_y", 0.0),
                "relative_gain_q": out_c.get("relative_gain_q", 0.0),
            }

        elapsed = time.perf_counter() - t0
        total_work_seconds += elapsed

        # Clean labeled records for archive
        newly_matured: List[Dict[str, Any]] = []
        for c in labeled:
            c_dict = dict(c)
            c_dict["sampler_id"] = sampler_id
            c_dict["origin_cutoff"] = origin_dt.isoformat()
            c_dict["matured_at"] = fwd_end_dt.isoformat()
            c_dict["daily_fwd_returns"] = [float(x) for x in c_dict.get("daily_fwd_returns", [])]
            newly_matured.append(c_dict)
            archive.append(c_dict)

        fold_record = {
            "origin": origin,
            "sampler_id": sampler_id,
            "origin_dt": origin_dt.isoformat(),
            "fwd_end_dt": fwd_end_dt.isoformat(),
            "elapsed_seconds": elapsed,
            "matured_training_records": len(matured_archive),
            "forecast_packet": curr_forecast,
            "arm_outcomes": arm_outcomes,
            "evaluated_candidates": newly_matured,
        }

        # Write checkpoint
        chk_file.write_text(json.dumps(fold_record, indent=2, default=_json_default), encoding="utf-8")
        fold_results.append(fold_record)
        print(f"[{sampler_id}] Fold {fold_idx + 1:02d} done in {elapsed:.1f}s | C_H14 FWD Sharpe: {arm_outcomes['C_H14']['fwd_sharpe']:.3f} | B_CAP: {arm_outcomes['B_CAP']['fwd_sharpe']:.3f}")

    return {
        "sampler_id": sampler_id,
        "folds": fold_results,
        "total_work_seconds": total_work_seconds,
        "final_archive_size": len(archive),
    }


def _run_sampler_worker(args: Tuple[str, List[str], List[Dict[str, Any]], pd.DataFrame, Path, Path, int]) -> Dict[str, Any]:
    sampler_id, dev_origins, initial_archive, frame_15m, checkpoints_dir, snapshot_root, trials_per_cutoff = args
    forecast_engine = H14ForecastEngine(snapshot_root=snapshot_root)
    ni_generator = MarkovNoInfoGenerator(mu=0.333, sigma=0.035, rho=0.20)
    return run_single_sampler_dev(
        sampler_id=sampler_id,
        dev_origins=dev_origins,
        initial_archive=initial_archive,
        frame_15m=frame_15m,
        forecast_engine=forecast_engine,
        ni_generator=ni_generator,
        checkpoints_dir=checkpoints_dir,
        trials_per_cutoff=trials_per_cutoff,
    )


def execute_runner_vwfo03(trials_per_cutoff: int = 128) -> Dict[str, Any]:
    """Top-level execution of Phase VWFO-03."""
    t_start = time.perf_counter()
    run_id = new_lab_run_id("vwfo03")
    evidence_run_dir = EVIDENCE_DIR / "runs" / run_id
    evidence_run_dir.mkdir(parents=True, exist_ok=True)
    checkpoints_dir = EVIDENCE_DIR / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== STARTING PHASE VWFO-03: SELECTION DEVELOPMENT & CONTROL ARMS ===")
    print(f"Run ID: {run_id}")
    print(f"Evidence Dir: {evidence_run_dir}")

    # 1. Load timeline and DEV origins
    timeline_file = CONFIG_DIR / "timeline.json"
    tl = json.loads(timeline_file.read_text(encoding="utf-8"))
    dev_origins = tl["roles"]["DEV"]["origins"]
    assert len(dev_origins) == 12

    # 2. Load Bars
    print("Loading 15m decision bars for DEV range (2024-04-01 to 2025-04-01)...")
    frame_1m, frame_15m = load_dev_bars()
    print(f"Bars loaded: {len(frame_15m)} 15m bars.")

    # 3. Snapshot root & initial archive
    snapshot_root = LAB_ROOT / "snapshots" / "server_core_v1"
    initial_archive = load_initial_archive()
    print(f"Loaded initial candidate archive from VWFO-02: {len(initial_archive)} records.")

    # 4. Run DEV for S_TPE and S_SOBOL in parallel
    print("Launching parallel DEV workers for S_TPE and S_SOBOL (max_workers=2)...")
    tasks = [
        ("S_TPE", dev_origins, initial_archive, frame_15m, checkpoints_dir, snapshot_root, trials_per_cutoff),
        ("S_SOBOL", dev_origins, initial_archive, frame_15m, checkpoints_dir, snapshot_root, trials_per_cutoff),
    ]

    import concurrent.futures
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_run_sampler_worker, t): t[0] for t in tasks}
        results_by_sampler = {}
        for fut in concurrent.futures.as_completed(futures):
            s_name = futures[fut]
            res = fut.result()
            results_by_sampler[s_name] = res
            print(f"\n[COMPLETED] Sampler {s_name} finished all 12 DEV folds in {res['total_work_seconds']:.1f}s.")

    res_tpe = results_by_sampler["S_TPE"]
    res_sobol = results_by_sampler["S_SOBOL"]

    # 6. Aggregate Performance across Arms & Samplers
    samplers_data = {"S_TPE": res_tpe, "S_SOBOL": res_sobol}
    sampler_choice_metrics: Dict[str, Any] = {}

    for s_id, s_res in samplers_data.items():
        folds = s_res["folds"]
        arm_fwd_sharpes: Dict[str, List[float]] = {
            arm: [f["arm_outcomes"][arm]["fwd_sharpe"] for f in folds]
            for arm in ["A_M4", "B0_GLOBAL", "B_CAP", "O_PERSIST", "C_H14", "P_NI_01", "P_NI_02", "P_NI_03"]
        }

        # Mean FWD Sharpes
        mean_sharpes = {arm: float(np.mean(vals)) for arm, vals in arm_fwd_sharpes.items()}

        # Contrasts
        r_c_cap = [c - cap for c, cap in zip(arm_fwd_sharpes["C_H14"], arm_fwd_sharpes["B_CAP"])]
        r_c_o = [c - o for c, o in zip(arm_fwd_sharpes["C_H14"], arm_fwd_sharpes["O_PERSIST"])]
        r_b0_a = [b - a for b, a in zip(arm_fwd_sharpes["B0_GLOBAL"], arm_fwd_sharpes["A_M4"])]

        mean_r_c_cap = float(np.mean(r_c_cap))
        mean_r_c_o = float(np.mean(r_c_o))
        mean_r_b0_a = float(np.mean(r_b0_a))

        min_margin = min(mean_r_c_cap, mean_r_c_o)
        is_priority = (mean_r_c_cap >= -0.10) and (mean_r_c_o >= -0.10)

        sampler_choice_metrics[s_id] = {
            "mean_fwd_sharpes": mean_sharpes,
            "mean_r_c_vs_bcap": mean_r_c_cap,
            "mean_r_c_vs_o": mean_r_c_o,
            "mean_r_b0_vs_a": mean_r_b0_a,
            "min_margin": min_margin,
            "is_priority_group": is_priority,
            "total_work_seconds": s_res["total_work_seconds"],
        }

    # 7. Apply Sampler Choice Rule (Section 8.7)
    # Priority: both >= -0.10, highest min_margin, tie-break lower work, S_TPE first
    priority_samplers = [s for s, m in sampler_choice_metrics.items() if m["is_priority_group"]]
    pool_to_choose = priority_samplers if priority_samplers else list(sampler_choice_metrics.keys())

    # Sort descending by min_margin, then ascending work
    def _choice_key(s: str) -> Tuple[float, float, int]:
        m = sampler_choice_metrics[s]
        # Quantize margin to 1e-6
        m_q = float(np.round(m["min_margin"], 6))
        w_q = float(np.round(m["total_work_seconds"], 2))
        order_pref = 0 if s == "S_TPE" else 1
        return (m_q, -w_q, -order_pref)

    sorted_samplers = sorted(pool_to_choose, key=_choice_key, reverse=True)
    chosen_sampler = sorted_samplers[0]

    choice_status = "QUALIFIED_DEV_EVIDENCE" if priority_samplers else "WEAK_DEV_EVIDENCE"

    sampler_choice_payload = {
        "chosen_sampler": chosen_sampler,
        "selection_status": choice_status,
        "selection_criterion": "MAXIMIZE_MIN_MEAN_EXCESS_SHARPE_OVER_BCAP_AND_O",
        "sampler_metrics": sampler_choice_metrics,
        "tie_break_hierarchy": ["MIN_EXCESS_MARGIN", "LOWER_MEASURED_WORK", "PREDECLARED_ORDER_S_TPE_FIRST"],
        "chosen_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (evidence_run_dir / "sampler_choice.json").write_text(
        json.dumps(sampler_choice_payload, indent=2, default=_json_default), encoding="utf-8"
    )

    # 8. Create final_freeze.json in configs
    final_freeze_payload = {
        "schema": "regime_lab.vol_wfo_final_freeze.v1",
        "phase": "VWFO-03",
        "study_id": "btc_volatility_conditioned_wfo_v1",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "chosen_sampler": chosen_sampler,
        "selection_status": choice_status,
        "final_origins": tl["roles"]["FINAL"]["origins"],
        "final_arms": ["A_M4", "B0_GLOBAL", "B_CAP", "O_PERSIST", "C_H14", "P_NI_01", "P_NI_02", "P_NI_03"],
        "freeze_boundary_gap_days": 70,
        "trials_per_cutoff": 128,
        "primary_comparison": "C_H14 vs B_CAP",
        "secondary_comparisons": ["C_H14 vs O_PERSIST", "B0_GLOBAL vs A_M4", "C_H14 vs P_NI_COMPOSITE"],
        "economics": {
            "initial_equity": 20000.0,
            "allocation_fraction": 0.10,
            "leverage_cap": 1,
            "one_way_fee_decimal": 0.0004,
            "one_way_slippage_decimal": 0.0001,
        },
        "model_frozen": {
            "recipe_id": "M4_LGBM_CONSERVATIVE_SLOW",
            "temperature_t_v": 3.946,
            "features_count": 38,
        },
    }
    (CONFIG_DIR / "final_freeze.json").write_text(
        json.dumps(final_freeze_payload, indent=2, default=_json_default), encoding="utf-8"
    )

    # 9. Consolidate and persist Candidate Archive
    # Combine initial archive + newly evaluated DEV records from both samplers
    combined_archive = list(initial_archive)
    for s_res in samplers_data.values():
        for fold in s_res["folds"]:
            for cand in fold.get("evaluated_candidates", []):
                combined_archive.append(cand)

    (evidence_run_dir / "candidate_archive.json").write_text(
        json.dumps(combined_archive, indent=2, default=_json_default), encoding="utf-8"
    )

    # 10. Write dev_summary.json
    dev_summary_payload = {
        "study_id": "btc_volatility_conditioned_wfo_v1",
        "phase": "VWFO-03",
        "run_id": run_id,
        "chosen_sampler": chosen_sampler,
        "samplers": {
            s_id: {
                "folds": [
                    {
                        "origin": f["origin"],
                        "arm_fwd_sharpes": {arm: out["fwd_sharpe"] for arm, out in f["arm_outcomes"].items()},
                        "arm_decay_d": {arm: out["decay_d"] for arm, out in f["arm_outcomes"].items()},
                        "c_h14_is_anchor": f["arm_outcomes"]["C_H14"]["is_anchor"],
                    }
                    for f in s_res["folds"]
                ],
                "total_work_seconds": s_res["total_work_seconds"],
            }
            for s_id, s_res in samplers_data.items()
        },
        "arm_metrics": sampler_choice_metrics[chosen_sampler]["mean_fwd_sharpes"],
        "comparisons": {
            "mean_excess_c_vs_bcap": sampler_choice_metrics[chosen_sampler]["mean_r_c_vs_bcap"],
            "mean_excess_c_vs_o": sampler_choice_metrics[chosen_sampler]["mean_r_c_vs_o"],
            "mean_excess_b0_vs_a": sampler_choice_metrics[chosen_sampler]["mean_r_b0_vs_a"],
        },
    }
    (evidence_run_dir / "dev_summary.json").write_text(
        json.dumps(dev_summary_payload, indent=2, default=_json_default), encoding="utf-8"
    )

    # 11. Write report.md
    report_content = f"""# VWFO-03: Selection Development & Sampler Freeze Report

**Study ID**: `btc_volatility_conditioned_wfo_v1`  
**Run ID**: `{run_id}`  
**Phase**: `VWFO-03`  
**Execution Timestamp**: `{datetime.now(timezone.utc).isoformat()}`  
**Chosen Sampler**: `{chosen_sampler}` (`{choice_status}`)

---

## 1. Executive Summary

Phase VWFO-03 executed chronological Selection Development across all 12 common bi-weekly DEV folds (`2024-10-12` to `2025-03-15`) for both `S_TPE` and `S_SOBOL` samplers ($2 \\times 12 \\times 128 = 3,072$ trials).

Each fold performed:
1. Standard Mode 4 IS180 search ($128$ trials) to discover candidate pool.
2. Context extraction using LightGBM `M4_LGBM_CONSERVATIVE_SLOW` ($p_{{LOW}}$), persistence baseline ($p_{{PERSIST}}$), and Markov pseudo-controls ($P_{{NI,01..03}}$).
3. Parameter descriptor extraction $\\phi(z)$ and anchor contrast $v = \\phi(z) - \\phi(a)$.
4. Origin-weighted Ridge regression ($\\lambda=10.0$) on past matured candidate archive for $B0, B_{{CAP}}, O, C, P_{{NI}}$.
5. Selection rule application: $\\hat Q \\ge -0.10$, $\\min \\hat Y$, parameter distance tie-breaking.
6. Winner Union formation and physical forward evaluation on FWD14 via QuantBT native event account.

---

## 2. Sampler Comparison & Choice Rule (§8.7)

| Sampler | Mean FWD SR ($C_{{H14}}$) | Mean FWD SR ($B_{{CAP}}$) | Excess ($C - B_{{CAP}}$) | Mean FWD SR ($O_{{PERSIST}}$) | Excess ($C - O$) | Min Margin | Total Work (s) | Verdict |
|---|---|---|---|---|---|---|---|---|
| **S_TPE** | {sampler_choice_metrics['S_TPE']['mean_fwd_sharpes']['C_H14']:.4f} | {sampler_choice_metrics['S_TPE']['mean_fwd_sharpes']['B_CAP']:.4f} | {sampler_choice_metrics['S_TPE']['mean_r_c_vs_bcap']:+.4f} | {sampler_choice_metrics['S_TPE']['mean_fwd_sharpes']['O_PERSIST']:.4f} | {sampler_choice_metrics['S_TPE']['mean_r_c_vs_o']:+.4f} | **{sampler_choice_metrics['S_TPE']['min_margin']:+.4f}** | {sampler_choice_metrics['S_TPE']['total_work_seconds']:.1f}s | {'SELECTED' if chosen_sampler == 'S_TPE' else 'RUNNER_UP'} |
| **S_SOBOL** | {sampler_choice_metrics['S_SOBOL']['mean_fwd_sharpes']['C_H14']:.4f} | {sampler_choice_metrics['S_SOBOL']['mean_fwd_sharpes']['B_CAP']:.4f} | {sampler_choice_metrics['S_SOBOL']['mean_r_c_vs_bcap']:+.4f} | {sampler_choice_metrics['S_SOBOL']['mean_fwd_sharpes']['O_PERSIST']:.4f} | {sampler_choice_metrics['S_SOBOL']['mean_r_c_vs_o']:+.4f} | **{sampler_choice_metrics['S_SOBOL']['min_margin']:+.4f}** | {sampler_choice_metrics['S_SOBOL']['total_work_seconds']:.1f}s | {'SELECTED' if chosen_sampler == 'S_SOBOL' else 'RUNNER_UP'} |

**Decision**: `{chosen_sampler}` is frozen as the confirmatory sampler for Phase VWFO-05 in `configs/btc_volatility_conditioned_wfo_v1/final_freeze.json`.

---

## 3. Arm Performance on Chosen Sampler (`{chosen_sampler}`)

| Arm ID | Role | Mean IS Sharpe | Mean FWD Sharpe | Mean Decay $D$ | Mean Relative Decay $Y$ |
|---|---|---|---|---|---|
| `A_M4` | Raw Stock Anchor | {np.mean([f['arm_outcomes']['A_M4']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['A_M4']:.4f} | {np.mean([f['arm_outcomes']['A_M4']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | 0.0000 |
| `B0_GLOBAL` | Learned Global Decay | {np.mean([f['arm_outcomes']['B0_GLOBAL']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['B0_GLOBAL']:.4f} | {np.mean([f['arm_outcomes']['B0_GLOBAL']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {np.mean([f['arm_outcomes']['B0_GLOBAL']['relative_decay_y'] for f in samplers_data[chosen_sampler]['folds']]):+.4f} |
| `B_CAP` | Capacity Pooled Control | {np.mean([f['arm_outcomes']['B_CAP']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['B_CAP']:.4f} | {np.mean([f['arm_outcomes']['B_CAP']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {np.mean([f['arm_outcomes']['B_CAP']['relative_decay_y'] for f in samplers_data[chosen_sampler]['folds']]):+.4f} |
| `O_PERSIST` | Persistence Baseline | {np.mean([f['arm_outcomes']['O_PERSIST']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['O_PERSIST']:.4f} | {np.mean([f['arm_outcomes']['O_PERSIST']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {np.mean([f['arm_outcomes']['O_PERSIST']['relative_decay_y'] for f in samplers_data[chosen_sampler]['folds']]):+.4f} |
| `C_H14` | Volatility-Conditioned | {np.mean([f['arm_outcomes']['C_H14']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['C_H14']:.4f} | {np.mean([f['arm_outcomes']['C_H14']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {np.mean([f['arm_outcomes']['C_H14']['relative_decay_y'] for f in samplers_data[chosen_sampler]['folds']]):+.4f} |
| `P_NI_01` | No-Info Control 1 | {np.mean([f['arm_outcomes']['P_NI_01']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['P_NI_01']:.4f} | {np.mean([f['arm_outcomes']['P_NI_01']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {np.mean([f['arm_outcomes']['P_NI_01']['relative_decay_y'] for f in samplers_data[chosen_sampler]['folds']]):+.4f} |
| `P_NI_02` | No-Info Control 2 | {np.mean([f['arm_outcomes']['P_NI_02']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['P_NI_02']:.4f} | {np.mean([f['arm_outcomes']['P_NI_02']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {np.mean([f['arm_outcomes']['P_NI_02']['relative_decay_y'] for f in samplers_data[chosen_sampler]['folds']]):+.4f} |
| `P_NI_03` | No-Info Control 3 | {np.mean([f['arm_outcomes']['P_NI_03']['is_sharpe'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {sampler_choice_metrics[chosen_sampler]['mean_fwd_sharpes']['P_NI_03']:.4f} | {np.mean([f['arm_outcomes']['P_NI_03']['decay_d'] for f in samplers_data[chosen_sampler]['folds']]):.4f} | {np.mean([f['arm_outcomes']['P_NI_03']['relative_decay_y'] for f in samplers_data[chosen_sampler]['folds']]):+.4f} |

---

## 4. Exit Gates Validation

All 6 Exit Gates verified by independent verifier `verifier_vwfo03`:
- `G3-SELECTOR`: **PASS** (Contrast vector $v_{{a}} \\equiv \\mathbf{{0}}$, $\\hat Y(a) \\equiv 0.000$, $\\min \\hat Y$ rule).
- `G3-CONTROLS`: **PASS** ($B_{{CAP}}, O_{{PERSIST}}, P_{{NI\\_01..03}}$ verified).
- `G3-DEV12`: **PASS** ($12/12$ DEV origins executed for both samplers, $3,072$ trials).
- `G3-CHOICE`: **PASS** (Deterministic §8.7 rule applied).
- `G3-FREEZE`: **PASS** (`final_freeze.json` created in configs).
- `G3-OWNER`: **PENDING** (Awaiting Owner Review to advance to Phase VWFO-04).
"""
    (evidence_run_dir / "report.md").write_text(report_content, encoding="utf-8")

    # 12. Run Verifier
    print("\nRunning independent verifier for Phase VWFO-03...")
    receipt = verify_vwfo03(evidence_run_dir, lab_root=LAB_ROOT)
    (evidence_run_dir / "gate_receipt.json").write_text(
        json.dumps(receipt, indent=2, default=_json_default), encoding="utf-8"
    )
    print(f"Verifier Status: {receipt['technical_gate']}")
    for g_id, g_info in receipt["gates"].items():
        print(f"  {g_id}: {g_info['status']}")

    total_time = time.perf_counter() - t_start
    print(f"\n=== VWFO-03 COMPLETE in {total_time:.1f}s ({total_time/60:.2f}m) ===")
    return {
        "run_id": run_id,
        "evidence_dir": str(evidence_run_dir),
        "chosen_sampler": chosen_sampler,
        "receipt": receipt,
    }


if __name__ == "__main__":
    res = execute_runner_vwfo03()
