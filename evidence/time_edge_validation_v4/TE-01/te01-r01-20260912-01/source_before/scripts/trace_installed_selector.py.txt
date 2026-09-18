#!/usr/bin/env python
"""LAB-04 L04.1-L04.4 -- what the installed selector actually does, and the
counterexamples that scope each finding to the right selector family."""

from __future__ import annotations

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector import installed_wfo as W  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS, SEED_POINTS  # noqa: E402
from crypto_regime_lab.selector.counterexamples import run_counterexamples  # noqa: E402
from crypto_regime_lab.selector.probe_design import ProbeDesign  # noqa: E402
from crypto_regime_lab.selector.robust_score import (  # noqa: E402
    DEFAULT_LAMBDA_F, DEFAULT_SURVIVE_THRESHOLD, EpisodePanel, score_all)

STUDY_ID = "crypto_regime_timeedge_v2"
PARAM_RANGES = {"fast": (3, 40, 1), "slow": (10, 120, 5), "dev": (50, 50, 1)}


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    frame = W.synthetic_frame()

    # ---- L04.1 -------------------------------------------------------
    with writer.attempt("L04.1.trace_installed_wfo") as att:
        modes = W.trace_all_modes(frame, PARAM_RANGES)
        probes = modes["oos_usage"]
        att.detail = {"modes_traced": len(modes["traces"]), "schedules_probed": len(probes)}
    search = {
        mode: {"trial_count": t.get("trial_count"), "fold_count": t.get("fold_count"),
               "selected_params": t.get("selected_params"),
               "searched": (t.get("trial_count") or 0) > 1}
        for mode, t in modes["traces"].items()
    }
    defaults = W.installed_defaults()
    trace = {"schema": "crypto_regime_lab.installed_wfo_trace.v1",
             "installed_defaults": defaults,
             "modes": modes, "oos_usage_probes": probes,
             "search_behaviour": search,
             "search_finding": (
                 "optimization_mode='none' -- the public default -- ran ONE trial on this fixture "
                 "and simply evaluated the supplied parameters, while every other mode ran 14-15. "
                 "So the default route performs no parameter search; a selector only exists once a "
                 "mode is chosen. Arm A therefore instantiates the rule the installed code applies "
                 "to trial records (_select_oos_candidate_record under the default "
                 "candidate_selection_metric), and the lab supplies the trial records."),
             "legacy_oos_labelling": {
                 "authoritative_source": "the engine's own walk_forward metadata (declared_claims)",
                 "modes_declaring_oos_selection": [
                     m for m, t in modes["traces"].items()
                     if t.get("declared_claims", {}).get("oos_used_for_selection")],
                 "behavioural_probe_limit": (
                     "under expanding windows only the final test segment is out of sample for "
                     "every fold, so a null probe bounds rather than refutes OOS dependence; where "
                     "the declaration and the probe disagree, the declaration is the label"),
                 "rule": ("a mode that declares OOS-adjusted selection is labelled "
                          "A_legacy_selection_adjusted and is never reported as an untouched "
                          "baseline (guide 10.1 / 13.6)"),
             },
             "mode_5_note": (
                 "mode_5_full_robust collapsed to a single fold: it is full-sample calibration, "
                 "not walk-forward, and its selection is not an out-of-sample claim."),
             "public_route_default": {
                 "optimization_mode": "none",
                 "candidate_selection_metric": "robust_decay",
                 "resolved_by": "quantbt.walkforward._select_oos_candidate_record",
                 "rule": "max(records, key=record.objective)",
                 "meaning": ("the default public route picks the best in-sample objective; the "
                             "robust selectors engage only when a mode or metric asks for them")}}
    # Guide 10.1 names SIX things to capture from the installed selector so that
    # "identical to the current WFO" can be checked rather than asserted. The
    # trace above carries all six, but three of them under the engine's own field
    # names -- and a reader looking for `search_scope` will not find
    # `optimization_schedule`. They are named here and each one says where it
    # came from, so the mapping is auditable instead of implicit.
    default = modes["traces"].get("none", {})
    config = default.get("config_trace") or {}
    folds = default.get("folds") or []
    trace["guide_10_1_capture"] = {
        "route": {"value": trace["public_route_default"]["resolved_by"],
                  "from": "public_route_default.resolved_by"},
        "mode": {"value": config.get("optimization_mode"),
                 "declared_modes": modes.get("modes_declared"),
                 "from": "modes.traces[].config_trace.optimization_mode"},
        "search_scope": {
            "value": {"optimization_schedule": config.get("optimization_schedule"),
                      "window_mode": config.get("window_mode"),
                      "split_frequency": config.get("split_frequency"),
                      "trials_on_the_default_route": default.get("trial_count")},
            "from": "modes.traces[].config_trace",
            "meaning": ("'global' schedule with an expanding window means one parameter set is "
                        "chosen over the whole history rather than per fold")},
        "candidate_freeze": {"value": defaults.get("candidate_freeze"),
                             "from": "installed_defaults.candidate_freeze"},
        "selected_params_freeze": {
            "value": {"selected_params": default.get("selected_params"),
                      "frozen_before_outer_evaluation":
                          (defaults.get("candidate_freeze") or {}).get(
                              "frozen_before_outer_evaluation"),
                      "selection_metadata": default.get("selection_metadata")},
            "from": "modes.traces[].selected_params + installed_defaults.candidate_freeze",
            "meaning": ("the parameters the route selected, and the engine's own statement that "
                        "the candidate set was fixed before any outer evaluation")},
        "data_used_for_selection": {
            "value": {"folds": len(folds),
                      "train_spans": [[f["train_start"], f["train_end"]] for f in folds],
                      "test_spans": [[f["test_start"], f["test_end"]] for f in folds],
                      "modes_declaring_oos_selection":
                          trace["legacy_oos_labelling"]["modes_declaring_oos_selection"]},
            "from": "modes.traces[].folds + legacy_oos_labelling",
            "meaning": ("expanding training windows plus the engine's own declaration that the "
                        "default route uses out-of-sample records for selection. That is why "
                        "arm A is labelled A_legacy_selection_adjusted")},
        "why_this_block_exists": (
            "guide 10.1: 'Không sửa semantics âm thầm rồi vẫn gọi y hệt WFO hiện tại.' The six "
            "captures are the record that makes that checkable, and three of them were only "
            "present under the engine's field names"),
    }
    trace["guide_10_1_capture"]["all_six_present"] = all(
        trace["guide_10_1_capture"][field]["value"] is not None
        for field in ("route", "mode", "search_scope", "candidate_freeze",
                      "selected_params_freeze", "data_used_for_selection"))
    writer.write_config("lab04_installed_wfo_trace.json", trace)
    writer.write_json("installed_wfo_trace.json", trace, schema=trace["schema"])

    # ---- L04.2 -------------------------------------------------------
    with writer.attempt("L04.2.counterexamples") as att:
        counter = run_counterexamples()
        att.detail = {"count": counter["count"], "errors": len(counter["errors"]),
                      "by_verdict": {k: len(v) for k, v in counter["by_verdict"].items()}}
    writer.write_config("lab04_selector_counterexamples.json", counter)
    writer.write_json("selector_counterexamples.json", counter, schema=counter["schema"])

    # ---- L04.3 -------------------------------------------------------
    with writer.attempt("L04.3.probe_design") as att:
        designs = {}
        for alpha_id, schema in SCHEMAS.items():
            design = ProbeDesign(schema)
            built = design.build({f"seed_{alpha_id}": dict(SEED_POINTS[alpha_id])})
            designs[alpha_id] = {
                "schema": schema.as_record(), "design_digest": built["design_digest"],
                "probe_count": built["probe_count"],
                "unique_probe_ids": built["unique_probe_ids"],
                "structurally_invalid_rejections": built["structurally_invalid_rejections"][:5],
                "rejection_count": len(built["structurally_invalid_rejections"]),
                "accounting_rules": built["accounting_rules"],
                "probes": built["probes"],
            }
        att.detail = {"alphas": len(designs)}
    payload = {"schema": "crypto_regime_lab.probe_designs.v1",
               "seed": ProbeDesign(SCHEMAS["A-SC"]).seed,
               "determinism": ("seeds derive from a sha256 of (seed, anchor_id) and every set "
                               "iteration is sorted, so a design is reproducible across processes"),
               "designs": designs}
    writer.write_config("lab04_probe_designs.json", payload)
    writer.write_json("probe_designs.json", payload, schema=payload["schema"])

    # ---- L04.4 -------------------------------------------------------
    with writer.attempt("L04.4.incumbent_parity") as att:
        episodes = [f"e{i}" for i in range(6)]
        incumbent = EpisodePanel("incumbent", {"fast": 5}, {e: 0.9 for e in episodes})
        inc_nb = [EpisodePanel(f"in{i}", {"fast": 5 + i}, {e: 0.85 for e in episodes})
                  for i in range(1, 9)]
        challenger = EpisodePanel("challenger", {"fast": 20}, {e: 1.4 for e in episodes})
        ch_nb = [EpisodePanel(f"cn{i}", {"fast": 20 + i}, {e: 0.1 for e in episodes})
                 for i in range(1, 9)]
        panels = {p.candidate_id: p for p in [incumbent, *inc_nb, challenger, *ch_nb]}
        scored = score_all(panels, {"incumbent": [p.candidate_id for p in inc_nb],
                                    "challenger": [p.candidate_id for p in ch_nb]})
        inc, ch = scored["scores"]["incumbent"], scored["scores"]["challenger"]
        parity = {
            "schema": "crypto_regime_lab.incumbent_parity.v1",
            "hyperparameters": scored["hyperparameters"],
            "lambda_f": DEFAULT_LAMBDA_F, "survive_threshold": DEFAULT_SURVIVE_THRESHOLD,
            "incumbent": inc, "challenger": ch,
            "same_episode_count": inc["episodes_used"] == ch["episodes_used"],
            "same_neighbour_budget": inc["neighbours_used"] == ch["neighbours_used"],
            "guard_before": {"metric": "raw quality G",
                             "winner": "challenger" if ch["g"] > inc["g"] else "incumbent"},
            "guard_after": {"metric": "robust objective R",
                            "winner": "challenger" if ch["r"] > inc["r"] else "incumbent"},
            "policy_visible": True,
            "rule": ("the incumbent is scored on the same episodes, the same neighbourhood budget "
                     "and the same utility as any challenger; when the raw guard and the robust "
                     "objective disagree, both are logged"),
        }
        att.detail = {"guard_disagreement":
                      parity["guard_before"]["winner"] != parity["guard_after"]["winner"]}
    writer.write_config("lab04_incumbent_parity.json", parity)
    writer.write_json("incumbent_parity.json", parity, schema=parity["schema"])

    print("L04.1 installed selector")
    print(f"    public default   : {trace['public_route_default']['rule']}")
    for mode, info in search.items():
        print(f"    mode {mode:<22} trials={info['trial_count']:<3} folds={info['fold_count']:<2} "
              f"searched={info['searched']}")
    for key, probe in probes.items():
        declared = (modes["traces"].get(key, {}).get("declared_claims", {})
                    .get("oos_used_for_selection"))
        print(f"    oos-probe {key:<28} declared_oos={str(declared):<5} "
              f"{probe.get('status'):<36} behavioural={probe.get('uses_oos_for_selection')}")
    print(f"    sampler          : {defaults['optuna_sampler']['class']} + "
          f"{defaults['optuna_sampler']['pruner']}")
    print(f"    objective backend: {defaults['objective_backend']['lab_setting']}")
    print(f"    candidate freeze : {defaults['candidate_freeze']['stage_1']} -> "
          f"{defaults['candidate_freeze']['stage_2']}")
    print(f"    baseline floor   : min_trades_per_year="
          f"{defaults['baseline_floor']['min_trades_per_year']} "
          f"penalty_factor={defaults['baseline_floor']['trade_penalty_factor']}")
    print(f"    retention        : financial={defaults['retention']['financial_retention']} "
          f"research={defaults['retention']['research_retention']} "
          f"scope={defaults['retention']['financial_scope']}")
    print("L04.2 counterexamples")
    for record in counter["counterexamples"]:
        print(f"    {record['id']} {record['verdict']:<24} {record['title'][:56]}")
    print("L04.3 probe designs")
    for alpha_id, design in designs.items():
        print(f"    {alpha_id:<8} probes={design['probe_count']:<3} "
              f"unique={design['unique_probe_ids']:<3} rejected={design['rejection_count']}")
    print("L04.4 incumbent parity")
    print(f"    same episodes={parity['same_episode_count']} "
          f"same neighbour budget={parity['same_neighbour_budget']} "
          f"guards disagree={parity['guard_before']['winner'] != parity['guard_after']['winner']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
