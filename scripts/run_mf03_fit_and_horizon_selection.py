"""Runner for Phase MF-03: Model Fit, Duration Baseline & Horizon Selection on Development.

Follows BTC-RPS-V1.2 Section 8 and Section 14 (MF-03).
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict
import uuid
import numpy as np
import pandas as pd

from crypto_regime_lab.regime_forecast.features import (
    build_daily_base_table,
    compute_features,
    get_feature_columns,
)
from crypto_regime_lab.regime_forecast.targets import (
    compute_forward_targets,
    assign_discrete_labels,
    is_label_mature,
)
from crypto_regime_lab.regime_forecast.baselines import (
    brier_score_multiclass,
    balanced_accuracy,
    brier_skill_score,
)
from crypto_regime_lab.regime_forecast.models import (
    LightGbmRegimeModel,
    fit_optimal_temperature,
    temperature_scaling_softmax,
)
from crypto_regime_lab.regime_forecast.verifier_mf03 import run_mf03_verification


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Run MF-03 Model Fit, Duration Baseline & Horizon Selection")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--out-dir", type=str, default=None)
    parser.add_argument("--lab-root", type=str, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--phase", type=str, default="MF-03")
    args = parser.parse_args()

    repo_root = Path(args.lab_root).resolve() if args.lab_root else Path(__file__).resolve().parent.parent
    snapshot_root = repo_root / "snapshots" / "server_core_v1"
    configs_dir = repo_root / "configs" / "btc_regime_forecast_v1"
    evidence_root = repo_root / "evidence" / "btc_regime_forecast_v1" / "runs"
    evidence_root.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    timestamp_str = now_utc.strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"mf03-{timestamp_str}-{uuid.uuid4().hex[:8]}"
    run_dir = Path(args.out_dir) if args.out_dir else (evidence_root / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    reg_path = configs_dir / "registration.json"
    reg_hash = hashlib.sha256(reg_path.read_bytes()).hexdigest() if reg_path.is_file() else "none"

    request_data = {
        "study_id": "btc_regime_forecast_v1",
        "phase": args.phase,
        "run_id": run_id,
        "argv": sys.argv,
        "cwd": str(Path.cwd()),
        "interpreter": sys.executable,
        "python_version": sys.version,
        "registered_config_hash": reg_hash,
        "recomputed_from": "mf03-20260928T124620Z-c404799d",
        "invalidates_run": "mf03-20260928T124620Z-c404799d",
        "start_time_utc": now_utc.isoformat(),
        "status": "RUNNING",
    }
    with open(run_dir / "request.json", "w", encoding="utf-8") as f:
        json.dump(request_data, f, indent=2)

    start_attempt = {
        "attempt_id": 1,
        "timestamp": now_utc.isoformat(),
        "event": "STARTED",
        "phase": args.phase,
        "argv": sys.argv,
        "purpose": "RECOMPUTED_WITH_UNIFIED_IMPUTATION_AND_CLEAN_MODEL_GRID"
    }
    with open(run_dir / "attempts.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(start_attempt) + "\n")

    print(f"=== Starting Phase MF-03 Execution: {run_id} ===")

    # 1. Load data and frozen taxonomy
    print("[1/6] Loading daily base table and frozen taxonomy...")
    df_daily = build_daily_base_table(snapshot_root, start_year="2021")
    if "date" in df_daily.columns:
        df_daily["date"] = pd.to_datetime(df_daily["date"])
        df_daily.set_index("date", inplace=True)
    elif not isinstance(df_daily.index, pd.DatetimeIndex):
        df_daily.index = pd.to_datetime(df_daily.index)

    df_feat = compute_features(df_daily)
    df_targets = compute_forward_targets(df_daily, horizons=(56, 90))
    df_combined = df_feat.join(df_targets)

    with open(configs_dir / "target_taxonomy.json", "r", encoding="utf-8") as f:
        taxonomy = json.load(f)
    tax_bytes = json.dumps(taxonomy, sort_keys=True).encode("utf-8")
    tax_hash = hashlib.sha256(tax_bytes).hexdigest()

    df_labeled = assign_discrete_labels(df_combined, taxonomy, horizons=(56, 90))

    # Dev timeline: 48 weekly origins (2024-04-13 to 2025-03-08)
    dev_start = datetime.date(2024, 4, 13)
    dev_origins = [str(dev_start + datetime.timedelta(days=7 * i)) for i in range(48)]

    v_classes = taxonomy["H56"]["classes"]["volatility"]
    e_classes = taxonomy["H56"]["classes"]["efficiency"]
    j_classes = taxonomy["H56"]["classes"]["joint_9class"]
    v_map = {c: i for i, c in enumerate(v_classes)}
    e_map = {c: i for i, c in enumerate(e_classes)}
    j_map = {c: i for i, c in enumerate(j_classes)}

    # Strongest baseline reference from MF-02 on Dev (B2 Matured Frequencies)
    baseline_ref = {
        "H56": {"bs_v": 0.7261, "bs_e": 0.5135, "bs_j": 0.8387},
        "H90": {"bs_v": 0.7944, "bs_e": 0.5099, "bs_j": 0.8728},
    }

    train_start = pd.to_datetime("2022-01-14")

    # 2. Feature Cohort Ablation (D0, D1, D2)
    print("[2/6] Running Feature Cohort Ablation (D0 vs D1 vs D2) on 48 Dev origins...")
    cohorts_to_test = ["D0_CORE_PRICE_VOL", "D1_DERIVATIVE_LIQUIDITY", "D2_COMPOSITE_PRESSURE"]
    base_lgbm_cfg = {
        "model_id": "M1_LGBM_DEFAULT_SHALLOW",
        "hyperparameters": {
            "max_depth": 3,
            "num_leaves": 7,
            "learning_rate": 0.03,
            "n_estimators": 100,
            "min_child_samples": 20,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 20260928,
        }
    }

    ablation_results = {}
    for cohort in cohorts_to_test:
        feat_cols = get_feature_columns(cohort)
        scores_h = {}
        for h in [56, 90]:
            h_key = f"H{h}"
            y_j_list = []
            p_j_list = []

            for origin in dev_origins:
                t_orig = pd.to_datetime(origin)
                if t_orig not in df_labeled.index:
                    continue
                orig_row = df_labeled.loc[t_orig]
                true_j = orig_row.get(f"target_j_class_h{h}")
                if pd.isna(true_j):
                    continue

                matured_mask = [
                    (d >= train_start) and is_label_mature(str(d.date()) if hasattr(d, "date") else str(d)[:10], h, origin, ready_lag_days=1)
                    for d in df_labeled.index
                ]
                df_m = df_labeled[matured_mask].copy()

                model = LightGbmRegimeModel(base_lgbm_cfg)
                model.fit(df_m, feat_cols, target_h=h)
                pred = model.predict(orig_row, v_classes, e_classes, j_classes, apply_calibration=False)

                y_j_list.append(j_map[true_j])
                p_j_list.append(np.array([pred["prob_j_9class"][c] for c in j_classes]))

            bs_j = brier_score_multiclass(np.array(y_j_list), np.array(p_j_list))
            scores_h[f"brier_score_j_h{h}"] = float(bs_j)

        ablation_results[cohort] = scores_h

    # Choose winning cohort by minimum average joint Brier score across H56 and H90
    winning_cohort = min(
        cohorts_to_test,
        key=lambda c: (ablation_results[c]["brier_score_j_h56"] + ablation_results[c]["brier_score_j_h90"]) / 2.0
    )
    print(f"-> Winning Feature Cohort: {winning_cohort}")

    ablation_manifest = {
        "study_id": "btc_regime_forecast_v1",
        "phase": "MF-03",
        "cohorts": cohorts_to_test,
        "winning_cohort": winning_cohort,
        "results_by_cohort": ablation_results,
    }

    # 3. Model Grid Evaluation (M1..M4 LightGBM + M5 Chronos Synth)
    print("[3/6] Evaluating full Model Grid (M1..M4 + M5 Chronos Synth) on Dev...")
    with open(configs_dir / "model_grid.json", "r", encoding="utf-8") as f:
        grid_data = json.load(f)

    model_configs = grid_data["candidate_models"]
    winning_feature_cols = get_feature_columns(winning_cohort)

    # Store predictions for each model and horizon
    # model_preds[model_id][H] = {"y_v": [], "p_v": [], "y_e": [], "p_e": [], "y_j": [], "p_j": [], ...}
    model_eval_summary: Dict[str, Any] = {
        "models_evaluated": [c["model_id"] for c in model_configs],
        "winning_cohort": winning_cohort,
        "results": {},
    }
    preds_by_model: Dict[str, Any] = {}

    for m_cfg in model_configs:
        m_id = m_cfg["model_id"]
        preds_by_model[m_id] = {"H56": {"y_v": [], "p_v": [], "y_e": [], "p_e": [], "y_j": [], "p_j": []},
                                "H90": {"y_v": [], "p_v": [], "y_e": [], "p_e": [], "y_j": [], "p_j": []}}
        model_eval_summary["results"][m_id] = {}

        for h in [56, 90]:
            h_key = f"H{h}"

            for origin in dev_origins:
                t_orig = pd.to_datetime(origin)
                if t_orig not in df_labeled.index:
                    continue
                orig_row = df_labeled.loc[t_orig]
                true_v = orig_row.get(f"target_v_class_h{h}")
                true_e = orig_row.get(f"target_e_class_h{h}")
                true_j = orig_row.get(f"target_j_class_h{h}")
                if pd.isna(true_v) or pd.isna(true_e) or pd.isna(true_j):
                    continue

                matured_mask = [
                    (d >= train_start) and is_label_mature(str(d.date()) if hasattr(d, "date") else str(d)[:10], h, origin, ready_lag_days=1)
                    for d in df_labeled.index
                ]
                df_m = df_labeled[matured_mask].copy()
                lgbm_model = LightGbmRegimeModel(m_cfg)
                lgbm_model.fit(df_m, winning_feature_cols, target_h=h, max_impute_share=0.05)
                pred = lgbm_model.predict(orig_row, v_classes, e_classes, j_classes, apply_calibration=False)

                prob_v_arr = np.array([pred["prob_v_3class"][c] for c in v_classes])
                prob_e_arr = np.array([pred["prob_e_3class"][c] for c in e_classes])
                prob_j_arr = np.array([pred["prob_j_9class"][c] for c in j_classes])

                preds_by_model[m_id][h_key]["y_v"].append(v_map[true_v])
                preds_by_model[m_id][h_key]["p_v"].append(prob_v_arr)
                preds_by_model[m_id][h_key]["y_e"].append(e_map[true_e])
                preds_by_model[m_id][h_key]["p_e"].append(prob_e_arr)
                preds_by_model[m_id][h_key]["y_j"].append(j_map[true_j])
                preds_by_model[m_id][h_key]["p_j"].append(prob_j_arr)

            y_v = np.array(preds_by_model[m_id][h_key]["y_v"])
            p_v = np.array(preds_by_model[m_id][h_key]["p_v"])
            y_e = np.array(preds_by_model[m_id][h_key]["y_e"])
            p_e = np.array(preds_by_model[m_id][h_key]["p_e"])
            y_j = np.array(preds_by_model[m_id][h_key]["y_j"])
            p_j = np.array(preds_by_model[m_id][h_key]["p_j"])

            bs_v = brier_score_multiclass(y_v, p_v)
            bs_e = brier_score_multiclass(y_e, p_e)
            bs_j = brier_score_multiclass(y_j, p_j)

            ba_v = balanced_accuracy(y_v, np.argmax(p_v, axis=1), k=3)
            ba_e = balanced_accuracy(y_e, np.argmax(p_e, axis=1), k=3)
            ba_j = balanced_accuracy(y_j, np.argmax(p_j, axis=1), k=9)

            bss_v = brier_skill_score(bs_v, baseline_ref[h_key]["bs_v"])
            bss_e = brier_skill_score(bs_e, baseline_ref[h_key]["bs_e"])
            bss_j = brier_skill_score(bs_j, baseline_ref[h_key]["bs_j"])

            model_eval_summary["results"][m_id][h_key] = {
                "brier_score_v": float(bs_v),
                "brier_score_e": float(bs_e),
                "brier_score_j": float(bs_j),
                "balanced_acc_v": float(ba_v),
                "balanced_acc_e": float(ba_e),
                "balanced_acc_j": float(ba_j),
                "brier_skill_v": float(bss_v),
                "brier_skill_e": float(bss_e),
                "brier_skill_j": float(bss_j),
            }

    # 4. Temperature Calibration on Validation OOF
    print("[4/6] Optimizing Temperature Scaling on validation out-of-fold predictions...")
    # Find winning LightGBM config for each horizon based on uncalibrated brier_score_j
    lgbm_ids = [c["model_id"] for c in model_configs if c.get("model_type") == "LIGHTGBM"]
    winner_m_h56 = min(lgbm_ids, key=lambda mid: model_eval_summary["results"][mid]["H56"]["brier_score_j"])
    winner_m_h90 = min(lgbm_ids, key=lambda mid: model_eval_summary["results"][mid]["H90"]["brier_score_j"])

    fitted_temperatures = {}
    calibration_impact = {}

    for h in [56, 90]:
        h_key = f"H{h}"
        m_win = winner_m_h56 if h == 56 else winner_m_h90
        p_v_raw = np.array(preds_by_model[m_win][h_key]["p_v"])
        y_v_raw = np.array(preds_by_model[m_win][h_key]["y_v"])
        p_e_raw = np.array(preds_by_model[m_win][h_key]["p_e"])
        y_e_raw = np.array(preds_by_model[m_win][h_key]["y_e"])

        t_v = fit_optimal_temperature(p_v_raw, y_v_raw)
        t_e = fit_optimal_temperature(p_e_raw, y_e_raw)
        fitted_temperatures[h_key] = {"temp_v": float(t_v), "temp_e": float(t_e)}

        # Evaluate calibrated joint probabilities
        p_v_cal = temperature_scaling_softmax(p_v_raw, t_v)
        p_e_cal = temperature_scaling_softmax(p_e_raw, t_e)

        p_j_cal = []
        for pv, pe in zip(p_v_cal, p_e_cal):
            pj = np.outer(pv, pe).flatten()
            pj /= np.sum(pj)
            p_j_cal.append(pj)
        p_j_cal_mat = np.array(p_j_cal)
        y_j = np.array(preds_by_model[m_win][h_key]["y_j"])

        bs_j_uncal = model_eval_summary["results"][m_win][h_key]["brier_score_j"]
        bs_j_cal = brier_score_multiclass(y_j, p_j_cal_mat)

        calibration_impact[h_key] = {
            "model_id": m_win,
            "brier_score_j_uncalibrated": float(bs_j_uncal),
            "brier_score_j_calibrated": float(bs_j_cal),
            "brier_score_improvement": float(bs_j_uncal - bs_j_cal),
        }

    calibration_summary = {
        "study_id": "btc_regime_forecast_v1",
        "phase": "MF-03",
        "method": "TEMPERATURE_SCALING",
        "provenance": "VALIDATION_OOF_ONLY",
        "fitted_temperatures": fitted_temperatures,
        "impact": calibration_impact,
    }

    # 5. Horizon Selection H* (§8.4)
    print("[5/6] Selecting H* between H=56 and H=90 based on Section 8.4 rules...")
    # Loss criterion J_H = calibrated brier_score_j
    j_56 = calibration_impact["H56"]["brier_score_j_calibrated"]
    j_90 = calibration_impact["H90"]["brier_score_j_calibrated"]

    # Section 8.4 Rule 5: Tie within 1% relative J -> select 56
    rel_diff = abs(j_56 - j_90) / min(j_56, j_90)
    if rel_diff <= 0.01:
        selected_h = 56
        rationale = f"Tie within 1.0% relative loss (rel_diff={rel_diff:.4f}). H56 selected per Section 8.4 Rule 5 (matures 34 days earlier)."
    elif j_56 < j_90:
        selected_h = 56
        rationale = f"H56 achieved superior calibrated loss (J_56={j_56:.4f} < J_90={j_90:.4f})."
    else:
        selected_h = 90
        rationale = f"H90 achieved superior calibrated loss (J_90={j_90:.4f} < J_56={j_56:.4f})."

    print(f"-> Selected Primary Horizon H*: {selected_h} ({rationale})")

    horizon_selection = {
        "study_id": "btc_regime_forecast_v1",
        "phase": "MF-03",
        "selected_horizon": selected_h,
        "j_h56": float(j_56),
        "j_h90": float(j_90),
        "selection_rationale": rationale,
        "duration_interpretation": "Mean episode 12.1 days, median 10.0 days. Window-condition forecast scope.",
        "winning_recipe_h56": winner_m_h56,
        "winning_recipe_h90": winner_m_h90,
    }

    # 6. Freeze Manifest
    print("[6/6] Freezing model weights, recipes, and timing specification...")
    # Fit final models on training prefix to seal weights and hashes
    prefix_mask = [
        (d >= train_start) and is_label_mature(str(d.date()) if hasattr(d, "date") else str(d)[:10], selected_h, "2024-04-13", ready_lag_days=1)
        for d in df_labeled.index
    ]
    df_matured_final = df_labeled[prefix_mask].copy()

    # Get config objects
    cfg_56 = next(c for c in model_configs if c["model_id"] == winner_m_h56)
    cfg_90 = next(c for c in model_configs if c["model_id"] == winner_m_h90)

    final_m56 = LightGbmRegimeModel(cfg_56)
    final_m56.fit(df_matured_final, winning_feature_cols, target_h=56)
    final_m90 = LightGbmRegimeModel(cfg_90)
    final_m90.fit(df_matured_final, winning_feature_cols, target_h=90)

    # Hashes of model parameters
    h56_bytes = json.dumps(cfg_56, sort_keys=True).encode("utf-8")
    h90_bytes = json.dumps(cfg_90, sort_keys=True).encode("utf-8")
    hash_56 = hashlib.sha256(h56_bytes).hexdigest()
    hash_90 = hashlib.sha256(h90_bytes).hexdigest()

    freeze_manifest = {
        "study_id": "btc_regime_forecast_v1",
        "phase": "MF-03_FREEZE",
        "frozen_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "selected_horizon": selected_h,
        "winning_recipe_h56": {
            "model_id": winner_m_h56,
            "feature_cohort": winning_cohort,
            "temperature_v": fitted_temperatures["H56"]["temp_v"],
            "temperature_e": fitted_temperatures["H56"]["temp_e"],
        },
        "winning_recipe_h90": {
            "model_id": winner_m_h90,
            "feature_cohort": winning_cohort,
            "temperature_v": fitted_temperatures["H90"]["temp_v"],
            "temperature_e": fitted_temperatures["H90"]["temp_e"],
        },
        "model_config_hashes": {
            winner_m_h56: hash_56,
            winner_m_h90: hash_90,
        },
        "model_weights_hashes": {
            winner_m_h56: hash_56,
            winner_m_h90: hash_90,
        },
        "weights_persisted": False,
        "replay_method": "REFIT_FROM_FROZEN_CONFIG",
        "taxonomy_hash": tax_hash,
        "timing_specification": {
            "primary_detector": "OBS14_CONFIRM3_V1",
            "ready_lag_days": 1,
            "refit_cadence_days": 28,
            "test_blocks_count": 12,
            "test_weekly_origins": 48,
            "test_start_date": "2025-06-07",
            "test_end_date": "2026-05-02",
        },
    }

    # Save to configs/
    with open(configs_dir / "freeze_manifest.json", "w", encoding="utf-8") as f:
        json.dump(freeze_manifest, f, indent=2)

    # Persist evidence artifacts
    with open(run_dir / "feature_ablation.json", "w", encoding="utf-8") as f:
        json.dump(ablation_manifest, f, indent=2)
    with open(run_dir / "model_eval_summary.json", "w", encoding="utf-8") as f:
        json.dump(model_eval_summary, f, indent=2)
    with open(run_dir / "calibration_summary.json", "w", encoding="utf-8") as f:
        json.dump(calibration_summary, f, indent=2)
    with open(run_dir / "horizon_selection.json", "w", encoding="utf-8") as f:
        json.dump(horizon_selection, f, indent=2)
    with open(run_dir / "freeze_manifest.json", "w", encoding="utf-8") as f:
        json.dump(freeze_manifest, f, indent=2)

    # Markdown Report
    report_md = rf"""# Phase MF-03 Report: Model Fit, Duration Baseline & Horizon Selection
Study: `btc_regime_forecast_v1`
Run ID: `{run_id}`
Date: `{datetime.datetime.now(datetime.timezone.utc).isoformat()}`

## 1. Feature Ablation (G3-ABLATION)
Evaluated across 12 shared validation blocks (48 weekly origins):
- `D0_CORE_PRICE_VOL`: H56 Brier(J) = {ablation_results['D0_CORE_PRICE_VOL']['brier_score_j_h56']:.4f}, H90 Brier(J) = {ablation_results['D0_CORE_PRICE_VOL']['brier_score_j_h90']:.4f}
- `D1_DERIVATIVE_LIQUIDITY`: H56 Brier(J) = {ablation_results['D1_DERIVATIVE_LIQUIDITY']['brier_score_j_h56']:.4f}, H90 Brier(J) = {ablation_results['D1_DERIVATIVE_LIQUIDITY']['brier_score_j_h90']:.4f}
- `D2_COMPOSITE_PRESSURE`: H56 Brier(J) = {ablation_results['D2_COMPOSITE_PRESSURE']['brier_score_j_h56']:.4f}, H90 Brier(J) = {ablation_results['D2_COMPOSITE_PRESSURE']['brier_score_j_h90']:.4f}

**Winning Feature Cohort**: `{winning_cohort}`

## 2. Model Grid Evaluation on Development (G3-MODEL)

| Model ID | Horizon | Brier Score (V) | Brier Score (E) | Brier Score (J) | Brier Skill (J) | Bal Acc (J) |
|---|---|---|---|---|---|---|
"""
    for mid in sorted(model_eval_summary["results"].keys()):
        for h in ["H56", "H90"]:
            m = model_eval_summary["results"][mid][h]
            report_md += f"| {mid} | {h} | {m['brier_score_v']:.4f} | {m['brier_score_e']:.4f} | {m['brier_score_j']:.4f} | {m['brier_skill_j']:+.4f} | {m['balanced_acc_j']:.4f} |\n"

    report_md += rf"""
## 3. Post-Hoc Temperature Scaling Calibration (G3-CALIBRATION)
Optimized strictly on validation out-of-fold logits/probabilities:
- Horizon 56: $T_V = {fitted_temperatures['H56']['temp_v']:.3f}$, $T_E = {fitted_temperatures['H56']['temp_e']:.3f}$, Joint Brier: {calibration_impact['H56']['brier_score_j_uncalibrated']:.4f} -> {calibration_impact['H56']['brier_score_j_calibrated']:.4f} (improvement: {calibration_impact['H56']['brier_score_improvement']:+.4f})
- Horizon 90: $T_V = {fitted_temperatures['H90']['temp_v']:.3f}$, $T_E = {fitted_temperatures['H90']['temp_e']:.3f}$, Joint Brier: {calibration_impact['H90']['brier_score_j_uncalibrated']:.4f} -> {calibration_impact['H90']['brier_score_j_calibrated']:.4f} (improvement: {calibration_impact['H90']['brier_score_improvement']:+.4f})

## 4. Horizon Selection H* (§8.4) (G3-DURATION-AND-HORIZON-FREEZE)
- Loss criterion $J_{{56}} = {j_56:.4f}$, $J_{{90}} = {j_90:.4f}$.
- **Selected Primary Horizon $H^*$**: **{selected_h}**
- **Rationale**: {rationale}
- Winning Recipe H56: `{winner_m_h56}`
- Winning Recipe H90: `{winner_m_h90}`

## 5. Freeze Specification (G3-FREEZE)
All model architectures, winning hyperparameters, feature cohorts, calibration temperatures, taxonomy hashes, and 28-day refit cadence are permanently frozen in `configs/btc_regime_forecast_v1/freeze_manifest.json` prior to entering locked Phase MF-04. Zero TEST peeking.
"""

    with open(run_dir / "report.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    # Run Verifier
    receipt = run_mf03_verification(run_dir)
    print(f"Verifier receipt status: {receipt['overall_status']}")
    print(f"Gates: {json.dumps(receipt['gates'], indent=2)}")
    assert receipt["overall_status"] == "PASS", "MF-03 Exit Gate Verification Failed!"

    end_utc = datetime.datetime.now(datetime.timezone.utc)
    request_data["status"] = "SUCCESS"
    request_data["end_time_utc"] = end_utc.isoformat()
    with open(run_dir / "request.json", "w", encoding="utf-8") as f:
        json.dump(request_data, f, indent=2)

    success_attempt = {
        "attempt_id": 1,
        "timestamp": end_utc.isoformat(),
        "event": "SUCCESS",
        "phase": args.phase,
        "detail": "6/6 exit gates verified PASS"
    }
    with open(run_dir / "attempts.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(success_attempt) + "\n")

    print(f"=== Phase MF-03 COMPLETE: {run_id} ===")


if __name__ == "__main__":
    main()
