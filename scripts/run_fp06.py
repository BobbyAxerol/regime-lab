#!/usr/bin/env python3
"""Build FP-06 artifacts (guide section 9 / 18): Implement C_FP_CONTEXT --
Selector B plus a frozen context family, added in the right place.

Real work, in order (never concurrent -- registered budget is workers=1):

  1. Reuse Selector B's OWN 192-record feature cache (.cache/fp05_features/
     rows.json, built for real in FP-05) verbatim -- guide 9.1's 'giữ
     nguyên candidate pool, base descriptors, target'.
  2. Compute context features (guide 9.3) once per origin from the SAME
     causal IS frame FP-05 already loads (frame.index < origin_cutoff) --
     12 real cache-friendly disk reads, zero new engine calls.
  3. Freeze context_policy.json BEFORE any fit (guide 18 task 7).
  4. Walk-forward OOF for BOTH B (fp.selector_b's own default builder) and
     C (fp.selector_c.build_c_feature_matrix) through the LITERAL SAME
     fp.selector_b.walk_forward_oof loop -- guide 9.1's 'inner split policy'
     constraint enforced structurally, not by convention.
  5. A held-out demo identical in shape to FP-05's: fit on the 11 earlier
     origins, score the 12th origin's own 16 regions with BOTH B and C,
     ablate C-B on the shared candidate set (FP06-G-ABLATION), apply
     guide 18 task 6's OOD/fallback-to-B check for C specifically.
  6. Record actual JM/M0/unknown exposure (guide 9.4) -- 0/0, disclosed,
     not silently omitted (LAB-08's own measured thin JM/M0 support is why
     this v1 uses continuous economic context instead).

Zero new real search-trial OR deployment engine calls: FP05-G-ACTION
already proved the admission/deployment wiring generically; FP-06's own
exit gate (FP06-G-ABLATION/CAUSAL/SUPPORT/FREEZE/CLAIM) does not require
re-proving it.

Usage:
  lab_venv/bin/python scripts/run_fp06.py --pytest-xml <junit xml of the FP-06 tests>
Exit 0 iff the FP-06 verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import selector_b as sb  # noqa: E402
from crypto_regime_lab.fp import selector_c as sc  # noqa: E402
from crypto_regime_lab.fp.forward_ledger import training_view  # noqa: E402
from crypto_regime_lab.fp.verifier_fp06 import REQUIRED_GATES, verify_fp06  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402

PHASE_ID = "FP-06"
ALPHA_ID = "A-SC"
FEATURE_CACHE = LAB / ".cache" / "fp05_features" / "rows.json"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"

TEST_NODE_IDS = [
    "test_compute_context_features_direction_efficiency_is_near_one_for_a_monotonic_uptrend",
    "test_compute_context_features_direction_efficiency_is_near_zero_for_pure_noise",
    "test_compute_context_features_refuses_a_too_short_frame",
    "test_compute_context_features_never_reads_bars_after_the_frame_end",
    "test_c_feature_names_is_a_strict_superset_of_b_feature_names",
    "test_interaction_specs_are_a_few_not_the_full_cartesian_product",
    "test_build_c_row_computes_interactions_as_the_literal_product",
    "test_fp06_t02_relabeling_a_context_key_does_not_change_the_computed_interaction_value",
    "test_build_c_feature_matrix_excludes_none_context_feature_with_a_reason",
    "test_build_c_feature_matrix_weights_equal_per_origin",
    "test_fp06_t01_walk_forward_oof_with_the_default_builder_is_exactly_selector_b",
    "test_context_support_bounds_from_training_rows_only",
    "test_is_context_ood_true_outside_the_training_range",
    "test_is_context_ood_false_inside_the_training_range",
    "test_fp06_t05_ood_fallback_prediction_carries_no_fake_confidence_fields",
    "test_predict_c_or_fallback_uses_context_conditioned_path_when_in_distribution",
    "test_fp06_t04_additive_only_model_cannot_represent_the_crossover",
    "test_fp06_t04_interaction_model_represents_the_crossover",
    "test_ablation_c_minus_b_only_diffs_shared_record_ids",
    "test_ablation_c_minus_b_handles_no_shared_records",
    "test_fp06_verifier_passes_on_a_valid_bundle",
    "test_fp06_verifier_fails_on_empty_dir",
    "test_fp06_verifier_fails_on_tampered_artifact",
    "test_fp06_g_ablation_fails_when_stored_diff_does_not_match_recomputation",
    "test_fp06_g_support_fails_when_fallback_count_disagrees_with_recomputation",
    "test_fp06_g_claim_fails_on_a_jm_specific_claim_with_zero_jm_exposure",
    "test_fp06_g_freeze_fails_when_context_policy_has_no_freeze_timestamp",
    "test_fp06_g_causal_fails_when_a_required_causal_test_is_not_registered",
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


def load_b_rows() -> list[dict]:
    if not FEATURE_CACHE.is_file():
        raise SystemExit(f"FP-06 requires FP-05's feature cache at {FEATURE_CACHE} -- run "
                         "scripts/run_fp05.py first")
    return json.loads(FEATURE_CACHE.read_text())


def build_c_rows(b_rows: list[dict]) -> tuple[list[dict], dict]:
    """Context features computed ONCE per origin (real disk reads, zero
    engine calls), then merged onto every one of that origin's B rows."""
    origins = sorted({r["origin_cutoff"] for r in b_rows})
    context_by_origin = {}
    for origin_cutoff in origins:
        frame = sb.load_origin_is_frame(ALPHA_ID, origin_cutoff)
        context_by_origin[origin_cutoff] = sc.compute_context_features(frame)
    c_rows = [sc.build_c_row(row, context_by_origin[row["origin_cutoff"]]) for row in b_rows]
    return c_rows, context_by_origin


def freeze_context_policy() -> dict:
    return {
        "schema": "regime_lab.fp06_context_policy.v1",
        "context_feature_names": list(sc.CONTEXT_FEATURE_NAMES),
        "interaction_specs": [{"a": a, "b": b, "reason": reason}
                              for a, b, reason in sc.INTERACTION_SPECS],
        "direction_lookback_days": sc.DIRECTION_LOOKBACK_DAYS,
        "vol_short_days": sc.VOL_SHORT_DAYS, "vol_long_days": sc.VOL_LONG_DAYS,
        "jm_m0_used": False,
        "jm_m0_reason": "LAB-08's own measured history found JM/M0 calibration-vintage state "
                        "support too thin to build on (only 1.64% of scoring observations "
                        "carried a state key seen during calibration) -- a disclosed design "
                        "choice, not a silent omission; guide 9.4's exposure count is still "
                        "recorded, at zero.",
        "not_full_cartesian": f"{len(sc.INTERACTION_SPECS)} of "
                              f"{len(sb.FEATURE_NAMES) * len(sc.CONTEXT_FEATURE_NAMES)} possible "
                              "candidate-descriptor x context pairs (guide 9.2's prohibition)",
        "frozen_at_utc": utcnow(),
    }


def run_fp06(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy)
    started = utcnow()

    b_rows = load_b_rows()
    c_rows, context_by_origin = build_c_rows(b_rows)
    context_policy = freeze_context_policy()

    lab_run_id = new_lab_run_id("fp06")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir

    # -- walk-forward OOF: B via the default builder, C via sc's builder --
    oof_b = sb.walk_forward_oof(b_rows, min_train_origins=sb.MIN_TRAIN_ORIGINS,
                                alpha_grid=sb.ALPHA_GRID)
    oof_c = sb.walk_forward_oof(c_rows, min_train_origins=sb.MIN_TRAIN_ORIGINS,
                                alpha_grid=sb.ALPHA_GRID,
                                feature_matrix_fn=sc.build_c_feature_matrix)
    alpha_b = sb.select_alpha(oof_b, sb.ALPHA_GRID)
    alpha_c = sb.select_alpha(oof_c, sb.ALPHA_GRID)
    if alpha_b["selected_alpha"] is None or alpha_c["selected_alpha"] is None:
        raise SystemExit(f"FP-06 cannot proceed: B={alpha_b}, C={alpha_c}")

    # -- held-out demo: fit on the 11 earlier origins, score the 12th --
    origins_sorted = sorted({r["origin_cutoff"] for r in b_rows},
                            key=lambda o: next(r["origin_time"] for r in b_rows
                                              if r["origin_cutoff"] == o))
    demo_origin = origins_sorted[-1]
    demo_decision_time = next(r["origin_time"] for r in b_rows if r["origin_cutoff"] == demo_origin)
    demo_train_b = training_view(b_rows, decision_time=demo_decision_time)["usable"]
    demo_train_c = training_view(c_rows, decision_time=demo_decision_time)["usable"]
    demo_val_b = [r for r in b_rows if r["origin_cutoff"] == demo_origin]
    demo_val_c = [r for r in c_rows if r["origin_cutoff"] == demo_origin]

    Xb_tr, yb_tr, wb_tr, _n1, _k1, _e1 = sb.build_feature_matrix(demo_train_b)
    b_model = sb.fit_ridge(Xb_tr, yb_tr, wb_tr, alpha_b["selected_alpha"])
    Xc_tr, yc_tr, wc_tr, _n2, kept_c_tr, _e2 = sc.build_c_feature_matrix(demo_train_c)
    c_model = sc.fit_ridge_c(Xc_tr, yc_tr, wc_tr, alpha_c["selected_alpha"])
    bounds = sc.context_support_bounds(kept_c_tr)

    Xb_va, yb_va, _wb_va, _n3, kept_b_va, _e3 = sb.build_feature_matrix(demo_val_b)
    b_preds_arr = sb.predict_ridge(b_model, Xb_va) if len(Xb_va) else []
    b_predictions = {row["record_id"]: float(p) for row, p in zip(kept_b_va, b_preds_arr)}

    scored_c = []
    for row in demo_val_c:
        if row.get("label") is None or any(row.get(n) is None for n in sc.c_feature_names()):
            continue
        result = sc.predict_c_or_fallback(c_model=c_model, b_model=b_model, row=row, bounds=bounds)
        scored_c.append({
            "record_id": row["record_id"], "region_id": row["region_id"],
            "predicted_forward_utility": result["predicted_forward_utility"],
            "source": result["source"], "fallback_reasons": result["fallback_reasons"],
            "is_mean_daily_return": row["is_mean_daily_return"],
            "region_support_within_origin": row["region_support_within_origin"],
            "ctx_direction_efficiency": row["ctx_direction_efficiency"],
            "ctx_volatility_ratio": row["ctx_volatility_ratio"],
            "actual_forward_label": row["label"],
        })
    c_predictions = {r["record_id"]: r["predicted_forward_utility"] for r in scored_c}

    ablation_result = sc.ablation_c_minus_b(b_predictions, c_predictions)
    ablation_doc = {**ablation_result, "b_predictions": b_predictions, "c_predictions": c_predictions}

    fallback_count = sum(1 for r in scored_c if r["source"] == "FALLBACK_TO_B")
    context_count = sum(1 for r in scored_c if r["source"] == "CONTEXT_CONDITIONED")
    exposure = {
        "schema": "regime_lab.fp06_exposure.v1",
        "jm_observations": 0, "m0_observations": 0, "unknown_stale_ambiguous": 0,
        "jm_m0_note": context_policy["jm_m0_reason"],
        "fallback_to_b_count": fallback_count, "context_conditioned_count": context_count,
        "n_scored_total": len(scored_c),
        "demo_origin": demo_origin, "demo_train_origins": origins_sorted[:-1],
    }

    oof_diagnostics_c = {
        "schema": "regime_lab.fp06_oof_diagnostics.v1",
        "n_fit_origins": len({r["origin_cutoff"] for r in c_rows if r["label"] is not None}),
        "n_validation_origins": oof_c["n_validation_origins"],
        "validation_origins": oof_c["validation_origins"],
        "alpha_grid": list(sb.ALPHA_GRID), "by_alpha_b": oof_b["by_alpha"],
        "by_alpha_c": oof_c["by_alpha"], "selected_alpha_b": alpha_b["selected_alpha"],
        "selected_alpha_c": alpha_c["selected_alpha"],
    }
    candidate_scores_c = {"schema": "regime_lab.fp06_candidate_scores.v1",
                          "demo_origin": demo_origin, "scored": scored_c}
    resource_budget = {
        "schema": "regime_lab.fp06_resource_budget.v1", "lab_run_id": lab_run_id,
        "fp06_wall_seconds_charged_to_shared_ledger": 0,
        "new_search_trial_engine_calls": 0, "new_deployment_engine_calls": 0,
        "resource_limits_applied": limits,
        "note": "FP-06 spends zero new real engine calls: context features are computed from "
               "market frames already real-loaded, and this phase's own exit gate does not "
               "require re-proving admission/deployment wiring (FP05-G-ACTION already did).",
    }
    test_registry = {"schema": "regime_lab.fp06_test_registry.v1", "lab_run_id": lab_run_id,
                     "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp06_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp06_build") as att:
        writer.write_json("context_policy.json", context_policy,
                          schema="regime_lab.fp06_context_policy.v1")
        writer.write_json("oof_diagnostics_c.json", oof_diagnostics_c,
                          schema="regime_lab.fp06_oof_diagnostics.v1")
        writer.write_json("candidate_scores_c.json", candidate_scores_c,
                          schema="regime_lab.fp06_candidate_scores.v1")
        writer.write_json("ablation.json", ablation_doc, schema="regime_lab.fp06_ablation.v1")
        writer.write_json("exposure.json", exposure, schema="regime_lab.fp06_exposure.v1")
        writer.write_json("resource_budget.json", resource_budget,
                          schema="regime_lab.fp06_resource_budget.v1")
        writer.write_json("test_registry.json", test_registry,
                          schema="regime_lab.fp06_test_registry.v1")
        writer.write_json("phase_manifest.json", manifest,
                          schema="regime_lab.fp06_phase_manifest.v1")
        att.detail = {"run_dir": str(run_dir)}

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "context_policy.json").write_text(
        json.dumps(context_policy, indent=2) + "\n", encoding="utf-8")
    (run_dir / "context_policy.json").write_text(
        json.dumps(context_policy, indent=2) + "\n", encoding="utf-8")

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, started=started,
                                context_policy=context_policy, oof_diagnostics_c=oof_diagnostics_c,
                                candidate_scores_c=candidate_scores_c, ablation_doc=ablation_doc,
                                exposure=exposure)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir, exposure=exposure,
                                  ablation_result=ablation_result)
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
        for name in ("context_policy.json", "oof_diagnostics_c.json", "candidate_scores_c.json",
                     "ablation.json", "exposure.json", "resource_budget.json", "test_registry.json",
                     "report.md", "handoff.md", "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp06(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, started, context_policy, oof_diagnostics_c,
                  candidate_scores_c, ablation_doc, exposure) -> str:
    lines = [f"# FP-06 — Implement C_FP_CONTEXT (Selector C) ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}",
            f"- alpha: {ALPHA_ID}, archive: FP-04/05's same 12-origin/192-record ledger "
            "(guide 9.1/FP06-T06: identical candidate pool)",
            "", "## Frozen context policy (guide 18 task 7)",
            f"- context features: {context_policy['context_feature_names']}",
            "- interaction terms (guide 9.2: a few, never the full Cartesian product):"]
    for spec in context_policy["interaction_specs"]:
        lines.append(f"  - {spec['a']} x {spec['b']}: {spec['reason']}")
    lines += [f"- {context_policy['not_full_cartesian']}",
             f"- JM/M0 used: {context_policy['jm_m0_used']} -- {context_policy['jm_m0_reason']}",
             "", "## OOF diagnostics -- B and C through the LITERAL SAME walk-forward loop",
             f"- distinct fit origins: {oof_diagnostics_c['n_fit_origins']}, "
             f"validation origins: {oof_diagnostics_c['n_validation_origins']} "
             f"{oof_diagnostics_c['validation_origins']}",
             f"- selected alpha -- B: {oof_diagnostics_c['selected_alpha_b']}, "
             f"C: {oof_diagnostics_c['selected_alpha_c']}",
             "", f"## Held-out demo on {candidate_scores_c['demo_origin']} "
             "(model trained on the 11 earlier origins only)"]
    for row in candidate_scores_c["scored"]:
        lines.append(
            f"  - {row['region_id']}: C_predicted={row['predicted_forward_utility']:.6f} "
            f"(source={row['source']}), B_predicted="
            f"{ablation_doc['b_predictions'].get(row['record_id'])}, "
            f"ACTUAL={row['actual_forward_label']:.6f}"
            + (f", fallback_reasons={row['fallback_reasons']}" if row["fallback_reasons"] else ""))
    lines += ["", "## Ablation: C - B on the shared candidate set (FP06-G-ABLATION)",
             f"- n_shared candidates: {ablation_doc['n_shared']}",
             f"- mean(C - B): {ablation_doc['mean_diff']}",
             f"- only in B (not scored by C): {ablation_doc['only_in_b']}",
             f"- only in C (not scored by B): {ablation_doc['only_in_c']}",
             "", "## Exposure (guide 9.4, guide 9.5's claim-level table)",
             f"- JM observations: {exposure['jm_observations']}, "
             f"M0 observations: {exposure['m0_observations']}, "
             f"unknown/stale/ambiguous: {exposure['unknown_stale_ambiguous']}",
             f"- fallback-to-B count: {exposure['fallback_to_b_count']}, "
             f"context-conditioned count: {exposure['context_conditioned_count']} "
             f"(of {exposure['n_scored_total']} scored)",
             "", "## Glossary",
             "- **context feature** (guide 9.3: a small, frozen set of continuous market "
             "descriptors -- direction efficiency and a volatility ratio in this v1 -- computed "
             "from the SAME causal IS frame, never JM/M0 state in this v1)",
             "- **interaction term** (guide 9.2: a candidate-descriptor x context product term, "
             "the ONLY mechanism that lets a model's predicted candidate RANKING change with "
             "context -- a purely additive f(theta)+g(x) model cannot do this, proved on a "
             "designed fixture, FP06-T04)",
             "- **OOD (out-of-distribution)** (a candidate's context value falls outside the "
             "range observed in ITS OWN model's training rows -- triggers fallback to Selector "
             "B's own prediction rather than an unsupported context-conditioned one)",
             "- **ablation** (C's prediction minus B's prediction on the IDENTICAL candidate, "
             "the guide's required same-scope 'context difference' measurement)",
             "", "## Permitted conclusions",
             "- Technical: Selector C reuses Selector B's candidate pool, base features, target, "
             "estimator family and inner split policy verbatim (same walk_forward_oof call, "
             "different feature_matrix_fn), a designed fixture proves the interaction "
             "architecture CAN represent a context-dependent candidate-ranking crossover that a "
             "pure additive model provably cannot (FP06-T04), and OOD candidates fall back to "
             "Selector B rather than an unsupported context-conditioned prediction.",
             "- Research: NOT_ASSESSED -- FP-06 builds and demonstrates Selector C; it does not "
             "run the locked A/B/C comparison (FP-07) or claim C beats B on real data. Guide 9.2: "
             "'C không tạo khác biệt trên real data vẫn là kết quả hợp lệ nếu execution đúng.'",
             "- Owner review: PENDING; FP-07 needs its own approval per the owner's recorded "
             "open-ended auto-advance instruction.", ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, exposure, ablation_result) -> str:
    return "\n".join([
        f"# FP-06 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        f"- fallback-to-B rate: {exposure['fallback_to_b_count']}/{exposure['n_scored_total']}",
        f"- mean(C - B) on the demo pool: {ablation_result['mean_diff']}",
        "- next authorized action: FP-07 (guide section 1.2/19-ish, the locked A/B/C study) per "
        "the owner's open-ended auto-advance instruction -- MEASURE and DISCLOSE its real compute "
        "cost before running anything, the same discipline FP-04's origin-count scope decision "
        "already demonstrated.",
        "- FP-07 must reuse: fp.selector_b (arm B) and fp.selector_c (arm C) exactly as built "
        "here, plus the stock Mode 4 selector (arm A) -- on a common fixed calendar, guide 1.2.",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp06(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
