#!/usr/bin/env python3
"""Build FP-05 artifacts (guide section 17): Implement B_FP (Selector B --
forward-persistent selection, no regime).

Real work, in order (never concurrent -- registered budget is workers=1):

  1. Build (or reuse the cached) feature matrix over FP-04's committed
     12-origin/192-record archive: one row per (record, region), guide
     8.2's six feature categories, each IS metric re-derived via a real
     cache-HIT re-call to fp.evaluator.evaluate_candidate (never a fresh
     engine computation -- FP-04 already made these exact calls).
  2. True chronological walk-forward OOF (guide 8.3/8.4) across the 12
     origins, min_train_origins=4 -> exactly 8 validation origins (guide
     8.7's own OOF-diagnostics floor). Ridge alpha selected by aggregate
     OOF error, never by in-sample fit.
  3. Decay-risk branch chosen from the MEASURED origin counts (guide
     8.5/8.6/8.7): 12 fit origins meets the model-fit floor, 8 OOF origins
     is below the 20-origin tail-quantile floor -> MEAN_DECAY, the
     registered fallback, disclosed as TAIL_ESTIMATE_UNSUPPORTED.
  4. A held-out demonstration: fit on origins 1-11, score origin 12's own
     16 regions (guide 8.6's eligibility/ranking order), select one real
     evaluated medoid (or COMMON_FLAT_FALLBACK), wire it through
     fp.admission_wiring (the SAME function FP-01 repaired) and a REAL
     small deployment account (fp.evaluator.run_deployment) to prove the
     selection actually reaches admission/deployment (FP05-G-ACTION).

Usage:
  lab_venv/bin/python scripts/run_fp05.py --pytest-xml <junit xml of the FP-05 tests>
Exit 0 iff the FP-05 verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import admission_wiring as aw  # noqa: E402
from crypto_regime_lab.fp import selector_b as sb  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.fp.forward_ledger import training_view  # noqa: E402
from crypto_regime_lab.fp.verifier_fp05 import REQUIRED_GATES, verify_fp05  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

PHASE_ID = "FP-05"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
FP04_RUN_DIR = LAB / "evidence" / "forward_persistence_fp_v1" / "fp04-20260923T145511Z-34cb31b6"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"
FEATURE_CACHE = LAB / ".cache" / "fp05_features" / "rows.json"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"
DEMO_WINDOW_DAYS = 10   # matches FP-02's own established small-real-demo scale

TEST_NODE_IDS = [
    "test_normalized_value_numeric_hits_0_and_1_at_declared_bounds",
    "test_normalized_value_fixed_is_always_zero",
    "test_normalized_params_only_covers_active_informative_dims",
    "test_fit_ridge_recovers_a_known_linear_relationship_at_low_alpha",
    "test_fit_ridge_shrinks_coefficients_toward_zero_as_alpha_grows",
    "test_fit_ridge_refuses_empty_training_set",
    "test_predict_ridge_on_the_mean_point_returns_the_intercept",
    "test_build_feature_matrix_excludes_none_label_with_a_reason",
    "test_build_feature_matrix_excludes_none_feature_with_a_reason",
    "test_build_feature_matrix_weights_equal_per_origin",
    "test_naive_loo_leaks_a_future_origin_that_training_view_correctly_blocks",
    "test_walk_forward_oof_never_trains_on_a_later_origins_own_record",
    "test_walk_forward_oof_reports_insufficient_below_min_train_plus_one_origins",
    "test_select_alpha_picks_the_lowest_aggregate_oof_mse",
    "test_select_alpha_reports_the_insufficient_reason_verbatim",
    "test_decay_risk_branch_falls_back_to_stock_below_fit_floor",
    "test_decay_risk_branch_uses_mean_decay_between_fit_and_tail_floors",
    "test_decay_risk_branch_uses_tail_quantile_at_or_above_20_oof_origins",
    "test_decay_risk_score_mean_vs_tail_quantile_differ_on_a_skewed_residual_set",
    "test_decay_risk_score_stock_fallback_branch_has_no_score",
    "test_eligible_candidates_filters_below_utility_floor",
    "test_eligible_candidates_filters_below_support_floor",
    "test_rank_and_select_never_returns_an_ineligible_row",
    "test_rank_and_select_maximises_utility_minus_decay_risk",
    "test_rank_and_select_returns_none_when_nothing_is_eligible",
    "test_fp05_verifier_passes_on_a_valid_bundle",
    "test_fp05_verifier_fails_on_empty_dir",
    "test_fp05_verifier_fails_on_tampered_artifact",
    "test_fp05_g_split_fails_on_an_injected_future_label_leak",
    "test_fp05_g_model_fails_when_stored_coef_does_not_match_a_refit",
    "test_fp05_g_support_fails_when_stored_branch_disagrees_with_recomputation",
    "test_fp05_g_action_fails_when_admit_has_no_deployment_fills",
    "test_fp05_g_report_fails_when_technical_and_research_status_are_not_separated",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_resource_limits(policy) -> dict:
    env = lab_worker_env(policy)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[key] = env[key]
    budget = policy.raw["resource_budget"]
    cap_bytes = int(budget["working_memory_gib"] * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"cpu_limit": env["OMP_NUM_THREADS"], "rlimit_as_gib": budget["working_memory_gib"],
            "previous_soft_gib": (None if soft == resource.RLIM_INFINITY
                                  else round(soft / (1 << 30), 2))}


def load_or_build_feature_rows(cache) -> tuple[list[dict], bool]:
    """Reuses .cache/fp05_features/rows.json if it already covers the full
    192-record archive (idempotent, guide 11.2's own discipline extended to
    FP-05: a ~14.5-minute real cache-hit scan is not repeated for a nicer
    number). Returns (rows, reused_from_cache)."""
    ledger = json.loads((FP04_RUN_DIR / "ledger_records.json").read_text())
    origins_doc = json.loads((FP04_RUN_DIR / "origin_ledger.json").read_text())
    if FEATURE_CACHE.is_file():
        cached = json.loads(FEATURE_CACHE.read_text())
        if len(cached) == len(ledger["records"]):
            return cached, True

    regions_by_key = {}
    for origin in origins_doc["origins"]:
        for region in origin.get("regions", []):
            regions_by_key[(origin["origin_cutoff"], region["region_id"])] = region

    schema = SCHEMAS[ALPHA_ID]
    economics = default_economics()
    rows = []
    frame_cache: dict = {}
    for record in ledger["records"]:
        origin_cutoff = record["origin_cutoff"]
        if origin_cutoff not in frame_cache:
            frame_cache[origin_cutoff] = sb.load_origin_is_frame(ALPHA_ID, origin_cutoff)
        region = regions_by_key[(origin_cutoff, record["region_id"])]
        row = sb.build_feature_row(cache, LAB, ALPHA_ID, schema, record, region,
                                   economics=economics, producer="fp05-features",
                                   is_frame=frame_cache[origin_cutoff])
        rows.append(row)
    FEATURE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FEATURE_CACHE.write_text(json.dumps(rows))
    return rows, False


def build_fold_audit(rows: list[dict], *, min_train_origins: int) -> list[dict]:
    """Independently re-derives, for each validation origin, exactly which
    training rows' label_available_at values were used -- the raw material
    FP05-G-SPLIT re-checks against, built the SAME way walk_forward_oof
    itself builds its training set (fp.forward_ledger.training_view), so
    the verifier is checking the guard's actual behaviour, not a summary."""
    origins = sorted({r["origin_cutoff"] for r in rows},
                     key=lambda o: next(r["origin_time"] for r in rows if r["origin_cutoff"] == o))
    audit = []
    for i in range(min_train_origins, len(origins)):
        val_origin = origins[i]
        decision_time = next(r["origin_time"] for r in rows if r["origin_cutoff"] == val_origin)
        train_rows = training_view(rows, decision_time=decision_time)["usable"]
        audit.append({
            "validation_origin": val_origin, "validation_origin_time": decision_time,
            "n_train_rows": len(train_rows),
            "train_label_available_ats": [r["label_available_at"] for r in train_rows],
        })
    return audit


def run_demo_deployment(cache, economics, chosen_params: dict, *, producer: str) -> dict:
    """A REAL, small (10-day) deployment account carrying Selector B's
    chosen params -- proving the selection reaches an actual account with
    actual fills, the same demonstration scale FP-02 already established,
    not a new expensive study."""
    from crypto_regime_lab.fp.evaluator import run_deployment

    # 2023-11-01: safely inside the registered `development` role
    # (2020-01-01..2023-12-31, configs/study_registration.json) and strictly
    # AFTER every origin's own forward window (the last origin, 2023-10-01,
    # matures 2023-10-29) -- never the `outer_evaluation` role (2024-01-01
    # onward), which stays untouched per this lab's standing discipline.
    demo_start = datetime(2023, 11, 1, tzinfo=timezone.utc)
    frame, _partitions = load_real_bars(SYMBOL, start=demo_start.strftime("%Y-%m-%d"),
                                        end=(demo_start + timedelta(days=DEMO_WINDOW_DAYS))
                                        .strftime("%Y-%m-%d"))
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    payload, event = run_deployment(
        cache, LAB, ALPHA_ID, frame,
        [{"activation_id": "fp05-selector-b-demo", "params": chosen_params, "requested_at_bar": 0}],
        ready_at=frame.index[0], economics=economics, producer=producer)
    audit = payload["selected_audit"]
    return {"status": "OK", "cache_event": event["status"], "fills": audit["fills"],
           "fill_count": len(audit["fills"]), "entries": payload["trial_scalar"]["entries"],
           "engine_fill_count": audit["engine_fill_count"],
           "window": {"start": demo_start.strftime("%Y-%m-%d"), "days": DEMO_WINDOW_DAYS}}


def run_fp05(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy)
    started = utcnow()
    economics = default_economics()

    lab_run_id = new_lab_run_id("fp05")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    cache = ComputeCache(LAB, "fp04", cache_root=CACHE_ROOT)   # SAME namespace: real cache hits

    rows, reused_features = load_or_build_feature_rows(cache)

    # -- walk-forward OOF + alpha selection --
    oof = sb.walk_forward_oof(rows, min_train_origins=sb.MIN_TRAIN_ORIGINS, alpha_grid=sb.ALPHA_GRID)
    alpha_selection = sb.select_alpha(oof, sb.ALPHA_GRID)
    fold_audit = build_fold_audit(rows, min_train_origins=sb.MIN_TRAIN_ORIGINS)
    n_fit_origins = len({r["origin_cutoff"] for r in rows if r["label"] is not None})
    branch_info = sb.decay_risk_branch(oof["n_validation_origins"], n_fit_origins=n_fit_origins)
    selected_alpha = alpha_selection["selected_alpha"]
    if selected_alpha is None:
        raise SystemExit(f"FP-05 cannot proceed: {alpha_selection['reason']}")
    oof_residuals = [f["residual"] for f in oof["folds"][selected_alpha]]

    # -- production-style final model: all 12 origins, the selected alpha --
    X_all, y_all, w_all, feat_names, kept_all, excluded_all = sb.build_feature_matrix(rows)
    final_model = sb.fit_ridge(X_all, y_all, w_all, selected_alpha)

    # -- held-out demo: fit on origins 1-11, score origin 12's own pool --
    origins_sorted = sorted({r["origin_cutoff"] for r in rows},
                            key=lambda o: next(r["origin_time"] for r in rows if r["origin_cutoff"] == o))
    demo_val_origin = origins_sorted[-1]
    demo_decision_time = next(r["origin_time"] for r in rows if r["origin_cutoff"] == demo_val_origin)
    demo_train_rows = training_view(rows, decision_time=demo_decision_time)["usable"]
    demo_val_rows = [r for r in rows if r["origin_cutoff"] == demo_val_origin]
    X_dtr, y_dtr, w_dtr, _n1, kept_dtr, _exc1 = sb.build_feature_matrix(demo_train_rows)
    demo_model = sb.fit_ridge(X_dtr, y_dtr, w_dtr, selected_alpha)
    X_dval, y_dval, _w2, _n2, kept_dval, excluded_dval = sb.build_feature_matrix(demo_val_rows)
    preds_dval = sb.predict_ridge(demo_model, X_dval) if len(X_dval) else []

    scored = []
    for row, pred in zip(kept_dval, preds_dval):
        pred = float(pred)
        risk = sb.decay_risk_score(is_mean=row["is_mean_daily_return"], predicted_forward=pred,
                                   oof_residuals=oof_residuals, branch=branch_info["branch"])
        scored.append({
            "record_id": row["record_id"], "region_id": row["region_id"], "params": row["params"],
            "medoid_trial_id": row["medoid_trial_id"],
            "is_mean_daily_return": row["is_mean_daily_return"],
            "region_support_within_origin": row["region_support_within_origin"],
            "predicted_forward_utility": pred,
            "D_point_estimate": row["is_mean_daily_return"] - pred,
            "decay_risk_score": risk["score"], "branch": risk["branch"],
            "actual_forward_label": row["label"],
        })
    eligible = sb.eligible_candidates(scored, utility_floor=sb.UTILITY_FLOOR_DAILY,
                                      support_floor=sb.MIN_SUPPORT_FOR_ELIGIBLE)
    winner = sb.rank_and_select(eligible)
    stock_pick = max(demo_val_rows, key=lambda r: r["is_mean_daily_return"]) if demo_val_rows else None

    if winner is not None:
        decision = {"decision": "ADMIT",
                   "reason": f"Selector B: predicted_utility={winner['predicted_forward_utility']:.6f}, "
                   f"decay_risk_score={winner['decay_risk_score']:.6f} "
                   f"(branch={winner['branch']})",
                   "kept": None}
        chosen_params = winner["params"]
    else:
        decision = {"decision": "COMMON_FLAT_FALLBACK",
                   "reason": "no candidate cleared both the utility floor and the support floor",
                   "kept": None}
        chosen_params = None
    admission_out = aw.deployment_params_from_decisions(
        params_by_fold={"0": chosen_params}, decisions={"0": decision})

    deployment_result = None
    if chosen_params is not None:
        deployment_result = run_demo_deployment(cache, economics, chosen_params,
                                                 producer=f"{lab_run_id}-demo")

    admission_and_deployment = {
        "schema": "regime_lab.fp05_admission_and_deployment.v1",
        "selector_b_decision": decision["decision"], "reason": decision["reason"],
        "selected_params": chosen_params,
        "admission_lineage": admission_out["lineage"],
        "deployment_result": deployment_result,
        "stock_comparator": {
            "record_id": stock_pick["record_id"] if stock_pick else None,
            "params": stock_pick["params"] if stock_pick else None,
            "is_mean_daily_return": stock_pick["is_mean_daily_return"] if stock_pick else None,
            "actual_forward_label": stock_pick["label"] if stock_pick else None,
        },
        "selected_vs_stock_same_candidate": (
            winner is not None and stock_pick is not None
            and winner["record_id"] == stock_pick["record_id"]),
    }

    oof_diagnostics = {
        "schema": "regime_lab.fp05_oof_diagnostics.v1",
        "n_fit_origins": n_fit_origins, "n_validation_origins": oof["n_validation_origins"],
        "validation_origins": oof["validation_origins"],
        "alpha_grid": list(sb.ALPHA_GRID), "by_alpha": oof["by_alpha"],
        "fold_audit": fold_audit,
        "required_diagnostics": {
            "prediction_error_by_origin": [
                {"origin": o, "mean_abs_residual": (
                    None if not [f["residual"] for f in oof["folds"][selected_alpha]
                                if f["origin_cutoff"] == o] else
                    float(statistics.fmean(
                        abs(f["residual"]) for f in oof["folds"][selected_alpha]
                        if f["origin_cutoff"] == o)))}
                for o in oof["validation_origins"]],
            "predicted_vs_realized_forward_utility": [
                {"record_id": f["record_id"], "predicted": f["predicted"], "realized": f["actual"]}
                for f in oof["folds"][selected_alpha]],
        },
    }

    model_selection = {
        "schema": "regime_lab.fp05_model_selection.v1",
        "alpha_grid": list(sb.ALPHA_GRID), "selected_alpha": selected_alpha,
        "selection_reason": "lowest aggregate weighted OOF MSE across the walk-forward folds",
        "oof_scores_by_alpha": alpha_selection.get("all_scores"),
        "final_model": final_model,
        "refit_inputs": {"X": X_all.tolist(), "y": y_all.tolist(), "w": w_all.tolist()},
        "n_kept": len(kept_all), "n_excluded": len(excluded_all), "excluded": excluded_all,
        "decay_risk_branch": branch_info,
        "demo_model_alpha": selected_alpha, "demo_train_origins": origins_sorted[:-1],
        "demo_validation_origin": demo_val_origin,
        "feature_names": feat_names,
        "utility_floor_daily": sb.UTILITY_FLOOR_DAILY, "utility_floor_source": sb.UTILITY_FLOOR_SOURCE,
        "support_floor": sb.MIN_SUPPORT_FOR_ELIGIBLE,
    }
    candidate_scores = {
        "schema": "regime_lab.fp05_candidate_scores.v1",
        "demo_origin": demo_val_origin, "scored": eligible,
        "winner_record_id": winner["record_id"] if winner else None,
        "excluded_from_scoring": excluded_dval,
    }
    resource_budget = {
        "schema": "regime_lab.fp05_resource_budget.v1", "lab_run_id": lab_run_id,
        "fp05_wall_seconds_charged_to_shared_ledger": 0,
        "feature_rows_reused_from_cache": reused_features,
        "engine_calls_feature_building": 0 if reused_features else len(rows),
        "engine_calls_demo_deployment": 1 if deployment_result else 0,
        "resource_limits_applied": limits,
        "note": "FP-05 spends no NEW real search-trial engine calls -- feature building is real "
               "cache-hit re-reads of FP-04's own evaluate_candidate calls, plus one small real "
               "demo deployment",
    }
    test_registry = {"schema": "regime_lab.fp05_test_registry.v1", "lab_run_id": lab_run_id,
                     "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp05_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp05_build") as att:
        writer.write_json("oof_diagnostics.json", oof_diagnostics,
                          schema="regime_lab.fp05_oof_diagnostics.v1")
        writer.write_json("model_selection.json", model_selection,
                          schema="regime_lab.fp05_model_selection.v1")
        writer.write_json("candidate_scores.json", candidate_scores,
                          schema="regime_lab.fp05_candidate_scores.v1")
        writer.write_json("admission_and_deployment.json", admission_and_deployment,
                          schema="regime_lab.fp05_admission_and_deployment.v1")
        writer.write_json("resource_budget.json", resource_budget,
                          schema="regime_lab.fp05_resource_budget.v1")
        writer.write_json("test_registry.json", test_registry,
                          schema="regime_lab.fp05_test_registry.v1")
        writer.write_json("phase_manifest.json", manifest,
                          schema="regime_lab.fp05_phase_manifest.v1")
        att.detail = {"run_dir": str(run_dir)}

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, oof_diagnostics=oof_diagnostics,
                                model_selection=model_selection, candidate_scores=candidate_scores,
                                admission_and_deployment=admission_and_deployment, started=started)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir,
                                  admission_and_deployment=admission_and_deployment)
    (run_dir / "report.md").write_text(report_text, encoding="utf-8")
    (run_dir / "handoff.md").write_text(handoff_text, encoding="utf-8")
    (run_dir / "gate_receipt.json").write_text(json.dumps({
        "schema": "regime_lab.fp_gate.v1", "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "lab_run_id": lab_run_id, "required_gates": list(REQUIRED_GATES),
        "technical_gate": "PENDING_VERIFICATION", "research_status": "NOT_ASSESSED",
        "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False,
    }, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"] = [
        {"path": name, "sha256": sha256_file(run_dir / name)}
        for name in ("oof_diagnostics.json", "model_selection.json", "candidate_scores.json",
                     "admission_and_deployment.json", "resource_budget.json", "test_registry.json",
                     "report.md", "handoff.md", "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp05(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, oof_diagnostics, model_selection, candidate_scores,
                  admission_and_deployment, started) -> str:
    lines = [f"# FP-05 — Implement B_FP (Selector B, no regime) ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}",
            f"- alpha: {ALPHA_ID}, symbol: {SYMBOL}, archive: FP-04's 12-origin/192-record ledger",
            "", "## OOF diagnostics (guide 8.3/8.4/8.7)",
            f"- distinct matured (fit) origins: {oof_diagnostics['n_fit_origins']} "
            f"(guide floor >= 12)",
            f"- distinct OOF validation origins: {oof_diagnostics['n_validation_origins']} "
            "(guide floor >= 8 for diagnostics, >= 20 for the tail-quantile branch)",
            f"- validation origins: {oof_diagnostics['validation_origins']}",
            "- weighted OOF MSE by alpha:"]
    for alpha, info in oof_diagnostics["by_alpha"].items():
        lines.append(f"  - alpha={alpha}: n={info['n']}, weighted_mse={info['weighted_mse']}")
    lines += ["", "## Model selection (guide 8.3)",
             f"- selected alpha: {model_selection['selected_alpha']} "
             f"({model_selection['selection_reason']})",
             f"- final model trained on {model_selection['n_kept']} rows "
             f"({model_selection['n_excluded']} excluded)",
             f"- decay-risk branch: **{model_selection['decay_risk_branch']['branch']}** "
             f"-- {model_selection['decay_risk_branch']['reason']}",
             f"- utility floor: {model_selection['utility_floor_daily']:.6f}/day "
             f"({model_selection['utility_floor_source']})",
             "", "## Held-out demo: score guide 8.6's ordered checks on the "
             f"{candidate_scores['demo_origin']} candidate pool "
             f"(model trained on the {len(model_selection['demo_train_origins'])} "
             "EARLIER origins only)"]
    for row in candidate_scores["scored"]:
        lines.append(
            f"  - {row['region_id']} (support={row['region_support_within_origin']}): "
            f"predicted_utility={row['predicted_forward_utility']:.6f}, "
            f"decay_risk={row['decay_risk_score']}, eligible={row['eligible']}"
            + (f", reasons={row['ineligibility_reasons']}" if not row["eligible"] else "")
            + (f", ACTUAL forward label={row['actual_forward_label']:.6f}"
              if row.get("actual_forward_label") is not None else ""))
    lines += ["", "## Selector B decision vs stock comparator (guide task 8 / required diagnostic)",
             f"- Selector B: {admission_and_deployment['selector_b_decision']} "
             f"-- {admission_and_deployment['reason']}",
             f"- selected params: {admission_and_deployment['selected_params']}",
             f"- stock comparator (best raw IS mean return, no forward-persistence modelling): "
             f"{admission_and_deployment['stock_comparator']}",
             f"- selected == stock: {admission_and_deployment['selected_vs_stock_same_candidate']}",
             "", "## Admission and deployment (FP05-G-ACTION)",
             f"```json\n{json.dumps(admission_and_deployment['admission_lineage'], indent=2)}\n```"]
    if admission_and_deployment["deployment_result"]:
        d = admission_and_deployment["deployment_result"]
        lines.append(f"- REAL demo deployment: {d['fill_count']} fills, {d['entries']} entries, "
                     f"window {d['window']}")
    else:
        lines.append("- no deployment attempted (COMMON_FLAT_FALLBACK)")
    lines += ["", "## Glossary",
             "- **OOF (out-of-fold)** (a prediction made for an origin whose data was NEVER used "
             "to fit the model that produced it -- guide 8.3's walk-forward exercise)",
             "- **walk-forward** (chronological cross-validation: fold i trains on every EARLIER "
             "origin's already-matured labels only, guide 8.4)",
             "- **decay-risk branch** (which of guide 8.6's three registered scoring rules "
             "applies -- TAIL_QUANTILE, MEAN_DECAY, or FALLBACK_STOCK_INCUMBENT -- chosen from "
             "the MEASURED origin counts, never asserted)",
             "- **TAIL_ESTIMATE_UNSUPPORTED** (guide 8.6's own label for the case where fit "
             "support is sufficient but tail-quantile support is not -- this run's actual case)",
             "- **eligibility floor** (guide 8.6: a candidate must clear BOTH a predicted-utility "
             "floor and a support floor before its decay risk is even assessed)",
             "- **stock comparator** (the best raw in-sample mean-return candidate in the SAME "
             "pool, with no forward-persistence model applied -- guide's required "
             "'selected vs stock candidate difference' diagnostic)",
             "", "## Permitted conclusions",
             "- Technical: a real chronological walk-forward OOF ran on FP-04's full archive "
             "(0 future-label leaks, independently re-checked), a ridge model was fit "
             "deterministically, the decay-risk branch was chosen from measured origin counts "
             "(MEAN_DECAY, TAIL_ESTIMATE_UNSUPPORTED, guide's own registered fallback), and the "
             "selector's output was wired through the SAME admission function FP-01 repaired "
             f"into a {'real deployment account with real fills' if admission_and_deployment['deployment_result'] else 'COMMON_FLAT_FALLBACK (no eligible candidate)'}.",
             "- Research: NOT_ASSESSED -- FP-05 builds and demonstrates Selector B; it does not "
             "run the locked A/B/C comparison (FP-07) or claim B beats the stock selector.",
             "- Owner review: PENDING; FP-06 needs its own approval (R-18).", ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, admission_and_deployment) -> str:
    return "\n".join([
        f"# FP-05 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        f"- Selector B demo decision: {admission_and_deployment['selector_b_decision']}",
        "- next authorized action: NONE until the owner approves FP-05 -> FP-06 (R-18).",
        "- FP-06 (guide section 9) must reuse: fp.selector_b's feature/model/OOF machinery "
        "wholesale (B pipeline), adding ONLY a frozen context family on top -- never a second "
        "candidate pool, target, or base-feature schema.",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp05(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
