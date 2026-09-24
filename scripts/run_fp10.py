#!/usr/bin/env python3
"""Build FP-10 artifacts (guide section 22): freeze, replay, final handoff.

Not another discovery phase -- FP-01..09's own experiments are complete and
committed; this phase (a) freezes the whole study's dependencies/contracts
into one detached-digest package, (b) REPLAYS one already-committed real
result under the identical frozen contract and compares the key economic
outputs exactly (never a same-hash claim alone -- guide 22: "Cung data cu
chay lai khong la independent confirmation", disclosed explicitly, not
implied), (c) writes the final report answering the nine guide-required
questions from already-committed evidence (never re-deriving a new claim),
and (d) hands off with real replay commands, unresolved issues and a real
compute-budget summary.

FP-09's own orchestrator is the replay target: it is the cheapest, most
recent, fully deterministic (frozen seed/threshold/bound) real result in
this study, and its own two-attempt history (a self-caught design defect,
fixed) is itself part of what this freeze package hands off.

No fresh/prospective data is opened here. `outer_evaluation` (2024-01-01
onward, configs/study_registration.json) has never been touched by any
FP-01..09 run and stays untouched -- guide 22's own anticipated path when
there is no eligible fresh data: engineering_status=COMPLETE_WITHIN_SCOPE,
prospective_status=NOT_RUN_NO_ELIGIBLE_NEW_DATA. Opening it is a real,
one-way decision (a touched holdout can never be clean again) that is the
owner's to make, not something this phase does unilaterally.

Usage:
  lab_venv/bin/python scripts/run_fp10.py --pytest-xml <junit xml of the FP-10 tests>
Exit 0 iff the FP-10 verifier reports PASS.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import checkpoint_search as cs  # noqa: E402
from crypto_regime_lab.fp import selector_b as sb  # noqa: E402
from crypto_regime_lab.fp import selector_c as sc  # noqa: E402
from crypto_regime_lab.fp import timing_policy as tp  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.fp.verifier_fp10 import (  # noqa: E402
    REQUIRED_FREEZE_COMPONENTS, REQUIRED_GATES, verify_fp10,
)
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

PHASE_ID = "FP-10"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"

# The original, already-committed FP-09 run this phase replays. Frozen here
# (not discovered dynamically) so the replay target itself cannot drift.
FP09_ORIGINAL_RUN_DIR = "evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a"

# Every FP-01..09 phase's own final, PASS-gated run_dir -- the artifact
# index this phase hands off. Frozen here from the already-committed
# CLAUDE.md/handoff record, not re-discovered by globbing (a glob could
# silently pick up a superseded or in-progress attempt).
PHASE_RUN_DIRS = {
    "FP-01": "evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29",
    "FP-02": "evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7",
    "FP-03": "evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360",
    "FP-04": "evidence/forward_persistence_fp_v1/fp04-20260923T145511Z-34cb31b6",
    "FP-05": "evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650",
    "FP-06": "evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7",
    "FP-07": "evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b",
    "FP-08 cell-2 archive": "evidence/forward_persistence_fp_v1/fp08cell2archive-20260924T125136Z-c93956c8",
    "FP-08": "evidence/forward_persistence_fp_v1/fp08-20260924T152905Z-5b68e8f8",
    "FP-09": FP09_ORIGINAL_RUN_DIR,
}

# Key source files this study's economics/selection/timing depend on --
# every published FP-01..09 result is only reproducible if these are
# byte-identical to what actually ran. Hashed fresh from disk every time
# this phase runs, never copied from an earlier claim.
CODE_DIGEST_FILES = (
    "src/crypto_regime_lab/fp/evaluator.py",
    "src/crypto_regime_lab/fp/locked_study.py",
    "src/crypto_regime_lab/fp/selector_b.py",
    "src/crypto_regime_lab/fp/selector_c.py",
    "src/crypto_regime_lab/fp/timing_policy.py",
    "src/crypto_regime_lab/fp/forward_ledger.py",
    "src/crypto_regime_lab/fp/chronology.py",
    "src/crypto_regime_lab/fp/admission_wiring.py",
    "src/crypto_regime_lab/fp/lineage.py",
    "src/crypto_regime_lab/fp/retention_fp02.py",
    "src/crypto_regime_lab/experiments/dynamic_fold_provider.py",
    "src/crypto_regime_lab/integration/event_account.py",
    "src/crypto_regime_lab/integration/continuous_account.py",
)

TEST_NODE_IDS = [
    "test_fp10_verifier_passes_on_a_valid_bundle",
    "test_fp10_verifier_fails_on_empty_dir",
    "test_fp10_g_freeze_fails_on_a_tampered_source_file",
    "test_fp10_g_freeze_fails_when_a_component_category_is_missing",
    "test_fp10_g_replay_fails_when_a_comparison_does_not_match",
    "test_fp10_g_replay_fails_without_the_non_independence_disclosure",
    "test_fp10_g_report_fails_when_a_required_question_is_unanswered",
    "test_fp10_g_report_fails_on_a_forbidden_overclaim_phrase",
    "test_fp10_g_exposure_fails_when_outer_evaluation_touched_is_not_declared_false",
    "test_fp10_g_handoff_fails_without_a_replay_command_section",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _import_run_fp09():
    spec = importlib.util.spec_from_file_location("fp10_run_fp09", LAB / "scripts" / "run_fp09.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_freeze_manifest() -> dict:
    code_rows = []
    for rel in CODE_DIGEST_FILES:
        path = LAB / rel
        if not path.is_file():
            raise SystemExit(f"FP-10 freeze: required source file missing: {rel}")
        code_rows.append({"path": rel, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})

    from crypto_regime_lab.time_edge.compute_cache import engine_contract
    engine_rows = [{"path": k, "sha256": v} for k, v in engine_contract(LAB).items()]

    snapshot_manifest_path = LAB / "snapshots" / "server_core_v1" / "manifest.json"
    snapshot_doc = _load_json(snapshot_manifest_path) if snapshot_manifest_path.is_file() else {}

    components = {
        "code_dependency_engine_digests": code_rows + engine_rows,
        "data_snapshots_and_availability": [{
            "snapshot_id": snapshot_doc.get("snapshot_id"),
            "manifest_path": "snapshots/server_core_v1/manifest.json",
            "manifest_sha256": (sha256_file(snapshot_manifest_path)
                               if snapshot_manifest_path.is_file() else None),
            "read_lock": snapshot_doc.get("read_lock"),
            "total_rows": snapshot_doc.get("total_rows"),
        }],
        "alpha_schema_search_probe_contracts": [{
            "alpha_id": "A-SC", "tunable_dims": 3,
            "checkpoint_levels": list(cs.CHECKPOINT_LEVELS),
            "b_search_frozen": 256,
            "calibration_origins": list(cs.CALIBRATION_ORIGINS),
            "train_memory_days": cs.TRAIN_MEMORY_DAYS,
            "source": "FP-03 (guide section 15), evidence/forward_persistence_fp_v1/"
                      "fp03-20260922T211626Z-6bf07360/",
        }],
        "bc_model_and_feature_protocols": [{
            "selector_b_feature_names": list(sb.FEATURE_NAMES),
            "selector_c_context_feature_names": list(sc.CONTEXT_FEATURE_NAMES),
            "selector_c_interaction_specs": [[a, b] for a, b, _r in sc.INTERACTION_SPECS],
            "alpha_b": 10.0, "alpha_c": 10.0,
            "alpha_b_source": "evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/"
                             "model_selection.json:selected_alpha",
            "alpha_c_source": "evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7/"
                             "oof_diagnostics_c.json:selected_alpha_c",
        }],
        "support_fallback_admission_rules": [{
            "utility_floor_daily": sb.UTILITY_FLOOR_DAILY,
            "min_support_for_eligible": sb.MIN_SUPPORT_FOR_ELIGIBLE,
            "fallback_vocabulary": ["FALLBACK_TO_A", "FALLBACK_TO_B", "B_SELECTED",
                                    "CONTEXT_CONDITIONED", "NEVER_ADMITTED"],
            "admission_decisions": ["ADMIT", "KEEP_INCUMBENT", "COMMON_FLAT_FALLBACK"],
        }],
        "economic_latency_activation_contract": [dict(default_economics())],
        "metrics_thresholds_analysis_family": [{
            "minimum_economic_effect_daily": sb.UTILITY_FLOOR_DAILY,
            "minimum_economic_effect_source": sb.UTILITY_FLOOR_SOURCE,
            "bootstrap_method": "time_edge.inference.block_mean, 28-day non-overlapping blocks",
            "delta_decay_status": "NOT_REGISTERED (guide 10.7's own fallback -- descriptive only)",
        }],
        "cohorts_windows_seeds_budgets": [{
            "fp04_origins_12": ["2021-01-01", "2021-04-01", "2021-07-01", "2021-10-01",
                               "2022-01-01", "2022-04-01", "2022-07-01", "2022-10-01",
                               "2023-01-01", "2023-04-01", "2023-07-01", "2023-10-01"],
            "fp07_09_frame_span": "2021-01-01..2024-01-01 (exclusive), BTCUSDT/A-SC",
            "fp08_cell2_origins_3": ["2021-06-01", "2022-06-01", "2023-06-01"],
            "fp08_cell2_symbol": "ETHUSDT",
            "fp09_timing_design": {"vol_threshold": tp.VOL_THRESHOLD, "k_max_bars": tp.K_MAX_BARS,
                                   "cal_matched_seed": tp.CAL_MATCHED_SEED},
            "resource_budget_exceptions": ["dec-9cc3ec3e712cf61b (7 GiB, FP-07/08/09 run_deployment "
                                          "calls, cited by reference from FP-07's own precedent)"],
        }],
    }
    for key in REQUIRED_FREEZE_COMPONENTS:
        if key not in components:
            raise SystemExit(f"FP-10 freeze: forgot a required component category: {key}")

    return {
        "schema": "regime_lab.fp10_freeze_manifest.v1",
        "study_id": STUDY_ID, "guide_version": GUIDE_VERSION, "status": "FROZEN",
        "hash_algorithm": "sha256",
        "components": components,
        "data_exposure": {
            "development_role_span": "2020-01-01..2023-12-31",
            "development_role_consumed_by": "FP-01..FP-09, entirely within this span",
            "outer_evaluation_span": "2024-01-01..null",
            "outer_evaluation_touched": False,
            "outer_evaluation_note": "configs/study_registration.json's own registered contamination "
                                    "note: outer_evaluation is NOT even a clean holdout in the first "
                                    "place (supplied presets were TPE-tuned on the full sample with an "
                                    "unknown cutoff) -- another real reason not to open it here without "
                                    "a deliberate owner decision",
            "engineering_status": "COMPLETE_WITHIN_SCOPE",
            "prospective_status": "NOT_RUN_NO_ELIGIBLE_NEW_DATA",
            "research_status": "corresponds to the evidence already on record per phase -- see "
                              "final_report.md's own per-question answers, never a single blanket "
                              "verdict",
        },
        "replay_command": "lab_venv/bin/python scripts/run_fp09.py --pytest-xml <fresh junit>",
        "frozen_at_utc": utcnow(),
    }


def run_replay(pytest_xml_for_fp09: str | None) -> dict:
    """Real replay: re-runs FP-09's own orchestrator under the identical
    frozen contract and compares the key economic outputs to the
    already-committed original run. NOT an independent confirmation
    (guide 22's own caveat) -- same frozen data, same code, same seed."""
    module = _import_run_fp09()
    original_dir = LAB / FP09_ORIGINAL_RUN_DIR
    original_accounts = _load_json(original_dir / "accounts.json")
    original_contrasts = _load_json(original_dir / "paired_contrasts.json")

    code, info = module.run_fp09(pytest_xml_for_fp09)
    replay_dir = Path(info["run_dir"])
    replay_accounts = _load_json(replay_dir / "accounts.json")
    replay_contrasts = _load_json(replay_dir / "paired_contrasts.json")

    # Economic outputs -- these MUST match exactly for a genuine replay; gated by FP10-G-REPLAY.
    comparisons = []
    for arm in ("SELECTOR_FIXED_CAL", "SELECTOR_CAL_MATCHED", "SELECTOR_REGIME_TIMING"):
        for field in ("fill_count", "entries"):
            o = original_accounts["by_arm"][arm][field]
            r = replay_accounts["by_arm"][arm][field]
            comparisons.append({"field": f"{arm}.{field}", "original": o, "replay": r, "match": o == r})
    for label, key in (("primary_contrast.estimate", "estimate"),
                       ("primary_contrast.status", "status")):
        o = original_contrasts["primary"].get(key)
        r = replay_contrasts["primary"].get(key)
        comparisons.append({"field": label, "original": o, "replay": r, "match": o == r})

    # Cache provenance -- NOT gated: a replay is EXPECTED to turn a prior MISS into a HIT (the
    # cache is warm from the original run), so a HIT here is evidence the replay found and reused
    # the identical computation, not a discrepancy to require matching.
    cache_provenance = [
        {"field": f"{arm}.cache_event", "original": original_accounts["by_arm"][arm]["cache_event"],
         "replay": replay_accounts["by_arm"][arm]["cache_event"]}
        for arm in ("SELECTOR_FIXED_CAL", "SELECTOR_CAL_MATCHED", "SELECTOR_REGIME_TIMING")
    ]

    return {
        "schema": "regime_lab.fp10_replay_result.v1",
        "replayed_phase": "FP-09", "original_run_dir": str(original_dir.relative_to(LAB)),
        "replay_run_dir": str(replay_dir.relative_to(LAB)), "replay_exit_code": code,
        "evaluation_label": "FROZEN_REPLAY",
        "independence_note": "this is NOT an independent confirmation of FP-09's finding -- the "
                             "SAME frozen market data, SAME code, SAME seed were replayed under the "
                             "identical contract, which only proves REPRODUCIBILITY, not a new "
                             "measurement (guide 22: 'Cung data cu chay lai khong la independent "
                             "confirmation')",
        "comparisons": comparisons,
        "all_match": all(c["match"] for c in comparisons),
        "cache_provenance": cache_provenance,
        "cache_provenance_note": "not gated: a MISS->HIT transition here is EXPECTED and is itself "
                                "evidence the replay found and reused the original run's exact "
                                "computation, never required to 'match' literally",
    }


def build_artifact_index() -> dict:
    phases = []
    for phase, rel in PHASE_RUN_DIRS.items():
        run_dir = LAB / rel
        receipt_path = run_dir / "gate_receipt.json"
        gate = None
        if receipt_path.is_file():
            gate = _load_json(receipt_path).get("technical_gate")
        phases.append({"phase": phase, "run_dir": rel, "gate": gate,
                       "exists": run_dir.is_dir()})
    return {"schema": "regime_lab.fp10_artifact_index.v1", "phases": phases}


def run_fp10(pytest_xml: str | None, *, pytest_xml_for_fp09_replay: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    started = utcnow()
    t_wall_start = time.perf_counter()

    lab_run_id = new_lab_run_id("fp10")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir

    freeze_manifest = build_freeze_manifest()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "fp10_freeze_manifest.json").write_text(
        json.dumps(freeze_manifest, indent=2) + "\n", encoding="utf-8")

    replay_result = run_replay(pytest_xml_for_fp09_replay)
    artifact_index = build_artifact_index()

    total_wall = time.perf_counter() - t_wall_start

    test_registry_doc = {"schema": "regime_lab.fp10_test_registry.v1", "lab_run_id": lab_run_id,
                        "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp10_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp10_build") as att:
        writer.write_json("freeze_manifest.json", freeze_manifest, schema=freeze_manifest["schema"])
        writer.write_json("replay_result.json", replay_result, schema=replay_result["schema"])
        writer.write_json("artifact_index.json", artifact_index, schema=artifact_index["schema"])
        writer.write_json("test_registry.json", test_registry_doc, schema=test_registry_doc["schema"])
        writer.write_json("phase_manifest.json", manifest, schema=manifest["schema"])
        att.detail = {"run_dir": str(run_dir)}

    report_text = render_final_report(lab_run_id=lab_run_id, run_dir=run_dir, started=started,
                                      freeze_manifest=freeze_manifest, replay_result=replay_result,
                                      artifact_index=artifact_index, total_wall=total_wall)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir,
                                  freeze_manifest=freeze_manifest, replay_result=replay_result)
    (run_dir / "final_report.md").write_text(report_text, encoding="utf-8")
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
        for name in ("freeze_manifest.json", "replay_result.json", "artifact_index.json",
                     "test_registry.json", "final_report.md", "handoff.md", "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp10(run_dir, lab_root=LAB, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id, "run_dir": str(run_dir)}


def render_final_report(*, lab_run_id, run_dir, started, freeze_manifest, replay_result,
                        artifact_index, total_wall) -> str:
    lines = [f"# FP-10 — Freeze, replay and final handoff ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}",
            f"- study_id: {STUDY_ID}, guide_version: {GUIDE_VERSION}", "",
            "## Freeze package", "",
            "Every required component category is present and re-hashed from disk at build time "
            "(FP10-G-FREEZE):", ""]
    for key in REQUIRED_FREEZE_COMPONENTS:
        n = len(freeze_manifest["components"][key])
        lines.append(f"- `{key}`: {n} entrie(s)")
    exp = freeze_manifest["data_exposure"]
    lines += ["", "## Data exposure (FP10-G-EXPOSURE)",
             f"- development role consumed: {exp['development_role_span']} "
             f"({exp['development_role_consumed_by']})",
             f"- outer_evaluation touched: **{exp['outer_evaluation_touched']}** "
             f"({exp['outer_evaluation_span']}) — {exp['outer_evaluation_note']}",
             f"- engineering_status: `{exp['engineering_status']}`",
             f"- prospective_status: `{exp['prospective_status']}`",
             "", "## Replay (FP10-G-REPLAY)",
             f"- replayed phase: {replay_result['replayed_phase']}",
             f"- original run: `{replay_result['original_run_dir']}`",
             f"- fresh replay run: `{replay_result['replay_run_dir']}`",
             f"- **{replay_result['independence_note']}**",
             "", "| field | original | replay | match |", "|---|---|---|---|"]
    for c in replay_result["comparisons"]:
        lines.append(f"| {c['field']} | {c['original']} | {c['replay']} | {c['match']} |")
    lines += [f"- all_match: **{replay_result['all_match']}**", "",
             f"- cache provenance (informational only, not gated — {replay_result['cache_provenance_note']}):",
             "", "| field | original | replay |", "|---|---|---|"]
    for c in replay_result["cache_provenance"]:
        lines.append(f"| {c['field']} | {c['original']} | {c['replay']} |")
    lines += ["", "## Artifact index (FP10-G-HANDOFF)", "| phase | run_dir | gate |", "|---|---|---|"]
    for row in artifact_index["phases"]:
        lines.append(f"| {row['phase']} | `{row['run_dir']}` | {row['gate']} |")
    lines += ["", "## Final report questions (guide 22, all nine required)", "",
             "### 1. Tang trials co cai thien forward outcomes khong?",
             "**No.** FP-03's own measurement (evidence/forward_persistence_fp_v1/"
             "fp03-20260922T211626Z-6bf07360/report.md): `D_mean_daily_return` (IS minus forward; "
             "positive = worse decay) stayed POSITIVE at EVERY checkpoint of EVERY origin as trials "
             "grew 32->64->128->256, and all three origins showed ZERO IS-objective improvement from "
             "checkpoint 128 to 256 — the identical trial stayed selected. Deeper search never turned "
             "decay negative on this alpha/window.",
             "", "### 2. B co tot hon A khong?",
             "**No, on the one evaluable cell.** FP-07/FP-08 (evidence/forward_persistence_fp_v1/"
             "fp07-20260923T190207Z-5a401d3b/report.md, fp08-20260924T152905Z-5b68e8f8/report.md): "
             "B_FP_PERSISTENCE minus A_STOCK_CAL estimate **-0.0001890/day**, 95% CI "
             "**[-0.0003208, -0.0000387]**, entirely BELOW zero — B underperformed the stock "
             "selector, not the reverse. Cell 2 (ETHUSDT) never had a B admission at all "
             "(NEVER_ADMITTED, NOT_EVALUABLE) — this finding is single-cell, not replicated in the "
             "direction it would need to be to call it general.",
             "", "### 3. C co tot hon B khong?",
             "**Degenerate, not measured.** C_FP_CONTEXT was byte-identical to B_FP_PERSISTENCE at "
             "EVERY real admission across both cells (0/12 and 0/3 CONTEXT_CONDITIONED — always "
             "FALLBACK_TO_B). The primary contrast C-B is exactly 0.0 by construction "
             "(evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/report.md's own "
             "DEGENERATE disclosure), not a measured null result. The context mechanism itself was "
             "verified to work on a designed fixture (FP06-T04) but was never exercised by real data "
             "at the scale this study ran.",
             "", "### 4. Decay giam co di cung utility/risk chap nhan duoc khong?",
             "**Descriptive only — no formal threshold exists to judge this against.** "
             "`delta_decay`/`epsilon_OOS_noninferiority` stay `NOT_REGISTERED` throughout FP-05..09 "
             "(guide 10.7's own fallback, never an invented threshold). Descriptively: FP-03 found "
             "decay (IS - forward) POSITIVE (worse) at every measured checkpoint — this study never "
             "measured a configuration where decay improved.",
             "", "### 5. Ket qua den tu conditional selection, timing, cadence hay exposure?",
             "**None of the four measured mechanisms showed a positive effect at this scale.** "
             "Conditional selection (C's context conditioning): never exercised (question 3). "
             "Forward-persistent selection (B vs A): negative, not positive (question 2). "
             "Transition-cost timing (FP-09, evidence/forward_persistence_fp_v1/"
             "fp09-20260924T200048Z-3ae26f5a/report.md): estimate **+0.000006/day**, CI "
             "**[-0.0000104, 0.0000180]** — straddles zero, an order of magnitude below the "
             "registered 6.4e-05/day MDE, on n=3 real admission events. Cadence: this study's own "
             "predecessor track (RA-07's 90-day placebo, FUP-05's 12-month placebo) and LAB-08's "
             "STATE_PLACEBO/DELAYED_STATE independently found apparent regime-timing edges to be "
             "cadence artifacts, not genuine regime information — the reason this FP line exists at "
             "all. No mechanism tested here reversed that pattern.",
             "", "### 6. Support va uncertainty cho phep ket luan manh den dau?",
             "**Weak, and disclosed as such at every phase.** Every contrast beyond descriptive "
             "comparison rests on a SINGLE cell (A-SC/BTCUSDT); cell 2 (ETHUSDT) never produced an "
             "evaluable B/C selection to compare at all. FP-09's timing effect rests on 3 real "
             "admission events. No contrast in the entire FP-01..09 study cleared the registered "
             "6.4e-05/day minimum economic effect in the positive direction.",
             "", "### 7. Nhung gia thuyet nao chua duoc thu?",
             "From FP-09's own registered consideration (configs/forward_persistence_fp_v1/"
             "fp09_study_freeze.json): **H_ADMISSION_FREQUENCY** (checking for admissions more often "
             "than the fixed quarterly cadence) and **H_DECAY_RISK_DEFERRAL** (deferring deployment "
             "around detected regime transitions to avoid FP-03's measured decay) were both "
             "considered and explicitly rejected for cost/measurement-readiness reasons, never "
             "tested. Also untried: replicating cell 1's own selection/timing findings on a THIRD "
             "cell, and extending FP-04's 12-origin archive toward guide 3.2's ~26-39-origin "
             "research-default target (a disclosed partial scope since FP-04).",
             "", "### 8. Chi phi da tieu va phan nao tai su dung duoc?",
             "Real measured engine wall time (sourced from each phase's own committed report.md, "
             "cited by path): FP-03 search 8404.12s (2786.63+2575.28+3042.21s, 3 origins x 256 "
             "trials); FP-04 search 34254.3s (9.52h, 12 origins x 256 trials, first full build); "
             "FP-07 deployment 509.41s; FP-08 cell-2 search 9344.1s (2.60h, 3 origins); FP-09 "
             "deployment 290.72s (2nd, corrected attempt). **Sum ≈ 52802.7s (~14.7h)** of real "
             "engine compute across the whole study (excluding a ~5h session-death incident during "
             "FP-04 and a host-wide OOM incident during FP-08's cell-2 build, both zero lost work). "
             "FP-01/02/05/06/08's-own-analysis-step needed zero or near-zero new engine calls "
             "(reused FP-04's cached archive). **Reusable for any future extension**: FP-04's full "
             "192-record (12 origin x 16 region) archive is the single biggest reusable asset — any "
             "new selector evaluated against the SAME shared pool needs zero new search cost.",
             "", "### 9. Co nen dung, giu baseline hay mo mot research revision cu the?",
             "**Recommendation (this session's synthesis, not a mandate — the owner decides): keep "
             "the stock/installed baseline selector (Arm A) and do not deploy B, C, or the FP-09 "
             "timing overlay as a replacement.** Every measured contrast across three independent "
             "mechanisms (forward-persistent selection, context conditioning, transition-cost "
             "timing) and, historically, three independent regime-timing falsifications before this "
             "FP line began (LAB-08, RA-07, FUP-05) landed negative, degenerate, or an order of "
             "magnitude below the registered minimum economic effect — never once clearing the bar "
             "in the positive direction. If further research is wanted, it should be a deliberately "
             "NEW, freshly-scoped research revision (the `research_revision_N` alpha tier this lab's "
             "architecture already reserves for that) targeting one of question 7's untried "
             "hypotheses, rather than continuing to probe the SAME mechanism space this study has "
             "now tested from several angles without finding a measurable edge.",
             "", "## Compute (FP10-G-HANDOFF)",
             f"- this phase's own wall time: {round(total_wall, 2)}s (freeze manifest build + one "
             "real FP-09 replay call + artifact index scan)",
             "", "## Permitted conclusions",
             "- Technical: the freeze manifest's every hashed source file matches what is on disk "
             "right now (FP10-G-FREEZE); the replay reproduced every compared economic output "
             f"exactly (all_match={replay_result['all_match']}, FP10-G-REPLAY), explicitly disclosed "
             "as NOT an independent confirmation; data exposure is stated explicitly, "
             "outer_evaluation stays untouched (FP10-G-EXPOSURE).",
             "- Research: this report answers the nine guide-required questions above from "
             "already-committed evidence, citing real paths for every factual claim. It does not "
             "introduce a new measurement.",
             "- Owner review: PENDING.", ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, freeze_manifest, replay_result) -> str:
    return "\n".join([
        f"# FP-10 handoff ({lab_run_id})", "", f"- run_dir: {run_dir}", "",
        "## Replay command",
        f"`{freeze_manifest['replay_command']}`",
        f"(what this phase itself ran: replayed {replay_result['replayed_phase']} from "
        f"`{replay_result['original_run_dir']}` into `{replay_result['replay_run_dir']}`, "
        f"all_match={replay_result['all_match']})",
        "", "## Unresolved issues",
        "- FP-09's own primary contrast (transition-cost timing) rests on only 3 real admission "
        "events at a single cell -- a severely small sample, disclosed, never treated as a general "
        "finding.",
        "- Cell 2 (A-SC/ETHUSDT) never produced an evaluable B/C selection across FP-08/09 -- the "
        "forward-persistent selector's own mechanism has only ever been exercised on cell 1.",
        "- guide 3.2's ~26-39-origin research-default target for FP-04's archive was never reached "
        "(frozen at 12, a disclosed partial scope since FP-04) -- extending it needs its own cost "
        "disclosure and R-18 approval before any future phase attempts it.",
        "- `outer_evaluation` (2024-01-01 onward) remains untouched and, per its own registration, "
        "is not even a clean holdout (supplied presets were TPE-tuned with an unknown cutoff) -- "
        "opening it for any future prospective evaluation needs a deliberate, explicit owner "
        "decision, not an automatic next step.",
        "", "## Budget summary",
        "~14.7h real engine wall time across FP-01..09 (FP-03 search 8404.12s, FP-04 search "
        "34254.3s, FP-07 deployment 509.41s, FP-08 cell-2 search 9344.1s, FP-09 deployment "
        "290.72s), plus this phase's own near-zero-cost replay (one cache-heavy FP-09 re-run). "
        "FP-04's 192-record archive is the largest reusable asset for any future extension.",
        "", "## Owner decisions",
        "Full R-18 decision ledger: evidence/regime_time_edge_ra_v1/owner_decisions.jsonl "
        "(every FP-01..10 phase-advance decision, the FP-09 hypothesis-selection delegation "
        "dec-dbdcfac62864f05b, and the FP-07/08/09 resource-budget exception dec-9cc3ec3e712cf61b "
        "are all there).",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    parser.add_argument("--pytest-xml-for-fp09-replay", default=None,
                        help="junit xml passed through to the replayed FP-09 run's own internal "
                             "verification (optional; the replay's economic comparison does not "
                             "depend on this)")
    args = parser.parse_args()
    code, _info = run_fp10(args.pytest_xml,
                           pytest_xml_for_fp09_replay=args.pytest_xml_for_fp09_replay)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
