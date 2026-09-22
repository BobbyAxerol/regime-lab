#!/usr/bin/env python3
"""Build FP-04 artifacts (guide section 16): historical forward ledger and
parameter regions.

Real engine work, in order (never concurrent -- registered budget is
workers=1):

  1. Freeze the origin grid + region-construction policy BEFORE any engine
     call is spent (guide 3.2: 'Khóa exact budget trước outcome').
  2. Per origin (idempotent: reuses .cache/fp04_search_raw/origin_<date>.json
     verbatim if already written by a prior invocation -- an origin's real
     search is never re-run to produce a nicer number, and a multi-hour
     computation is not thrown away over a process restart):
       a. one real run_cutoff_walk_forward search at the FROZEN B_search=256
          (configs/forward_persistence_fp_v1/search_policy.json, FP-03's own
          measured freeze -- FP-04 reuses it, never re-derives a new depth);
       b. cluster the real trial pool into regions (params only, guide 7.3),
          medoid per region, capped at the frozen representative_subset_size;
       c. real forward evaluation of EVERY region's medoid (fp.evaluator, the
          same route FP-02/03 already qualified), assembled into ledger
          records with full maturity/label timing (guide 16 item 5).
  3. Write the archive + flattened ledger + resource budget + report/handoff,
     verify with fp.verifier_fp04.

Usage:
  lab_venv/bin/python scripts/run_fp04.py --pytest-xml <junit xml of the FP-04 tests>
Exit 0 iff the FP-04 verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import checkpoint_search as cs  # noqa: E402
from crypto_regime_lab.fp import forward_ledger as fl  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.fp.verifier_fp04 import (  # noqa: E402
    MIN_SUPPORT_FOR_MODEL_READY, REQUIRED_GATES, verify_fp04,
)
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

PHASE_ID = "FP-04"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"
RAW_SEARCH_CACHE = LAB / ".cache" / "fp04_search_raw"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"
SEARCH_SEED = 20260922                # guide 3.2: one seed across the discovery stage
FORWARD_HORIZON_DAYS = 28
TRAIN_MEMORY_DAYS = cs.TRAIN_MEMORY_DAYS
DISTANCE_THRESHOLD = 0.12
FROZEN_SEARCH_POLICY = CONFIG_DIR / "search_policy.json"

TEST_NODE_IDS = [
    "test_valid_origin_placement_window_matches_registered_development_role",
    "test_validate_origin_grid_flags_dates_outside_the_window",
    "test_fp04_frozen_origin_grid_is_12_quarterly_origins_all_valid",
    "test_flag_window_overlaps_on_the_frozen_grid_forward_windows_never_overlap",
    "test_flag_window_overlaps_detects_a_deliberately_dense_pair",
    "test_cluster_into_regions_groups_close_points_and_separates_far_ones",
    "test_cluster_into_regions_dedups_identical_params_keeping_best_objective",
    "test_region_medoid_is_a_real_member_never_an_invented_centroid",
    "test_fp04_t04_region_geometry_is_unchanged_by_corrupting_objective_or_adding_forward_fields",
    "test_region_summary_reports_required_guide_7_4_fields_forward_fields_pending",
    "test_build_regions_for_origin_caps_at_max_representatives_by_best_objective",
    "test_maturity_state_before_forward_window_closes_is_not_yet_mature",
    "test_maturity_state_right_at_origin_before_forward_attempt_is_decision_available",
    "test_maturity_state_after_window_closes_with_valid_outcome_is_matured",
    "test_maturity_state_failed_origin_search_is_censored_regardless_of_as_of",
    "test_maturity_state_failed_forward_attempt_after_window_closes_is_censored",
    "test_maturity_state_refuses_an_as_of_before_the_decision_existed",
    "test_fp04_t05_censored_record_has_null_label_with_a_reason_never_zero",
    "test_fp04_t05_origin_search_failure_censors_without_ever_attempting_forward_eval",
    "test_fp04_t01_a_late_discovered_candidate_does_not_appear_in_a_past_origin",
    "test_fp04_t02_mutating_a_stored_forward_label_does_not_change_the_selection",
    "test_fp04_t03_representative_selection_is_unchanged_when_forward_outcome_differs",
    "test_fp04_t06_origin_with_five_representatives_carries_the_same_total_weight_as_one_with_one",
    "test_panel_view_reports_equal_weight_sum_per_origin_flag",
    "test_matured_view_hides_a_record_before_its_own_label_available_at",
    "test_training_view_tags_usable_rows_without_mutating_stored_maturity_state",
    "test_training_view_blocks_a_label_not_yet_available_at_decision_time",
    "test_fp04_t07_incremental_rebuild_only_calls_build_fn_for_new_origins",
    "test_fp04_t07_a_failed_origin_is_retried_not_permanently_cached",
    "test_fp04_t08_old_vintage_records_survive_a_rebuild_under_a_changed_policy",
    "test_geometry_version_id_changes_when_policy_changes_and_is_stable_otherwise",
    "test_evaluate_region_forward_real_small_window_produces_a_usable_decay",
    "test_evaluate_region_forward_empty_slice_is_censored_not_a_crash",
    "test_fp04_verifier_passes_on_a_valid_bundle",
    "test_fp04_verifier_fails_on_empty_dir",
    "test_fp04_verifier_fails_on_tampered_artifact",
    "test_fp04_g_region_fails_when_stored_medoid_does_not_match_recomputation",
    "test_fp04_g_causal_fails_when_a_censored_record_carries_a_nonnull_label",
    "test_fp04_g_causal_fails_on_a_cross_origin_medoid_leak",
    "test_fp04_g_support_fails_when_counts_disagree_with_a_fresh_recount",
    "test_fp04_g_reuse_fails_when_fresh_trial_count_disagrees_with_the_ledger",
    "test_fp04_g_ledger_fails_when_an_origin_is_missing_from_the_frozen_grid",
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


def _frozen_b_search() -> int:
    policy = json.loads(FROZEN_SEARCH_POLICY.read_text())
    if policy.get("blocker") is not None:
        raise SystemExit(f"FP-03 search_policy.json carries a blocker, refusing to proceed: "
                         f"{policy['blocker']}")
    return int(policy["B_search"])


def _frozen_representative_subset_size() -> int:
    policy = json.loads(FROZEN_SEARCH_POLICY.read_text())
    return int(policy["representative_subset_size"])


def load_or_run_origin(origin_cutoff: str, *, trials: int, seed: int) -> dict:
    RAW_SEARCH_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_SEARCH_CACHE / f"origin_{origin_cutoff}.json"
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text())
        if (cached.get("wf_result", {}).get("ok") is True
                and cached.get("trials_requested") == trials
                and cached.get("seed") == seed):
            cached["reused_from_cache"] = str(cache_path)
            return cached
    result = cs.run_origin_search(origin_cutoff=origin_cutoff, trials=trials, seed=seed,
                                  route="event", train_memory_days=TRAIN_MEMORY_DAYS,
                                  forward_days=FORWARD_HORIZON_DAYS)
    cache_path.write_text(json.dumps(result, default=str))
    result["reused_from_cache"] = None
    return result


def build_origin_entry(cache, schema, origin_cutoff: str, *, b_search: int,
                       representative_subset_size: int, economics: dict, producer: str) -> dict:
    raw = load_or_run_origin(origin_cutoff, trials=b_search, seed=SEARCH_SEED)
    wf_result = raw["wf_result"]
    wf_ok = bool(wf_result.get("ok"))
    trial_records = cs._trial_records(wf_result) if wf_ok else []

    regions = []
    if wf_ok and trial_records:
        regions = fl.build_regions_for_origin(
            schema, origin_cutoff=origin_cutoff, trial_records=trial_records,
            distance_threshold=DISTANCE_THRESHOLD,
            max_representatives=representative_subset_size)

        import pandas as pd

        cutoff_ts = pd.Timestamp(origin_cutoff, tz="UTC")
        forward_end = cutoff_ts + pd.Timedelta(days=FORWARD_HORIZON_DAYS)
        frame, _partitions = load_real_bars(
            SYMBOL, start=raw["load_start"],
            end=(forward_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        frame = frame[["open", "high", "low", "close", "volume"]].copy()
        for region in regions:
            forward_result = fl.evaluate_region_forward(
                cache, LAB, ALPHA_ID, frame, region, origin_cutoff=cutoff_ts,
                forward_horizon_days=FORWARD_HORIZON_DAYS, economics=economics,
                producer=f"{producer}-{region['region_id']}")
            region["_forward_result"] = forward_result   # consumed below, not part of guide 7.4 schema

    return {
        "origin_cutoff": origin_cutoff, "wf_ok": wf_ok, "wf_error": wf_result.get("error"),
        "reused_from_cache": raw.get("reused_from_cache"), "seed": raw["seed"],
        "trials_requested": raw["trials_requested"],
        "market_partitions_used": raw["market_partitions_used"],
        "load_start": raw["load_start"], "load_end": raw["load_end"],
        "frame_rows": raw["frame_rows"], "wall_seconds_measured": raw.get("wall_seconds_measured"),
        "instrumentation": raw.get("instrumentation"),
        "trial_records": trial_records,
        "regions": [{k: v for k, v in r.items() if k != "_forward_result"} for r in regions],
        "_regions_with_forward": regions,
    }


def build_ledger_records(origin_entries: list[dict], geometry_version: str) -> dict:
    records = []
    for entry in origin_entries:
        origin_cutoff = entry["origin_cutoff"]
        as_of = (datetime.fromisoformat(origin_cutoff).replace(tzinfo=timezone.utc)
                + timedelta(days=FORWARD_HORIZON_DAYS)).isoformat()
        if not entry["wf_ok"]:
            # no region was ever built -- still ONE censored record per origin
            # so a failed origin is visible in the ledger, not silently absent
            placeholder_region = {"region_id": "R_NONE", "medoid_trial_id": None,
                                  "medoid_params": None,
                                  "is_quality_distribution": {"mean": None},
                                  "historical_support_within_origin": 0}
            records.append(fl.ledger_record(
                origin_cutoff=origin_cutoff, forward_horizon_days=FORWARD_HORIZON_DAYS,
                region=placeholder_region, forward_result=None, wf_ok=False, as_of=as_of,
                geometry_version=geometry_version))
            continue
        for region in entry["_regions_with_forward"]:
            forward_result = region["_forward_result"]
            records.append(fl.ledger_record(
                origin_cutoff=origin_cutoff, forward_horizon_days=FORWARD_HORIZON_DAYS,
                region=region, forward_result=forward_result, wf_ok=True, as_of=as_of,
                geometry_version=geometry_version))
    model_ready = sum(1 for r in records if r["maturity_state"] == "matured_forward_record"
                      and r["region_support_within_origin"] >= MIN_SUPPORT_FOR_MODEL_READY)
    return {
        "schema": "regime_lab.fp04_ledger_records.v1", "records": records,
        "support_summary": {
            "model_ready_count": model_ready,
            "descriptive_only_count": len(records) - model_ready,
            "min_support_for_model_ready": MIN_SUPPORT_FOR_MODEL_READY,
            "min_support_reason": (
                f"a matured record needs >= {MIN_SUPPORT_FOR_MODEL_READY} region members "
                "(within its own origin) before FP-05 may treat it as model-ready evidence "
                "rather than a single-candidate descriptive point -- guide 7.4: 'Region ít "
                "support được shrink/fallback theo policy, không được mô tả là stable chỉ vì "
                "có một candidate tốt'"),
        },
    }


def freeze_region_policy(*, b_search: int, representative_subset_size: int) -> dict:
    grid_check = fl.validate_origin_grid(fl.FP04_ORIGIN_GRID, train_memory_days=TRAIN_MEMORY_DAYS,
                                         forward_horizon_days=FORWARD_HORIZON_DAYS)
    if not grid_check["all_valid"]:
        raise SystemExit(f"frozen origin grid failed validation: {grid_check}")
    overlaps = fl.flag_window_overlaps(fl.FP04_ORIGIN_GRID, train_memory_days=TRAIN_MEMORY_DAYS,
                                       forward_horizon_days=FORWARD_HORIZON_DAYS)
    schema = SCHEMAS[ALPHA_ID]
    geometry_version = fl.geometry_version_id(schema, distance_threshold=DISTANCE_THRESHOLD,
                                              max_representatives=representative_subset_size)
    return {
        "schema": "regime_lab.fp04_region_policy.v1",
        "alpha_id": ALPHA_ID, "symbol": SYMBOL,
        "origin_grid": list(fl.FP04_ORIGIN_GRID),
        "origin_grid_scope_note": (
            f"{len(fl.FP04_ORIGIN_GRID)} of the guide 3.2 research-default target of ~26-39 "
            "blocks -- quarterly (Jan/Apr/Jul/Oct 1) across 2021-2023, the same three "
            "development-role years FP-03's CALIBRATION_ORIGINS already used. Explicit, "
            "disclosed partial coverage per guide 16's own closing permission ('Thiếu số "
            "origins cho model không làm archive vô giá trị, nhưng không được gọi model "
            "study hoàn tất'); FP04-T07's incremental-rebuild guarantee means extending this "
            "grid later costs only the INCREMENTAL new origins."),
        "b_search": b_search, "b_search_source": "configs/forward_persistence_fp_v1/search_policy.json "
                                                  "(FP-03's own frozen depth, reused verbatim)",
        "search_seed": SEARCH_SEED, "train_memory_days": TRAIN_MEMORY_DAYS,
        "forward_horizon_days": FORWARD_HORIZON_DAYS,
        "distance_threshold": DISTANCE_THRESHOLD,
        "distance_threshold_reason": (
            "Gower-like normalised distance (selector.schema_distance.ParamSchema.distance) "
            "averaged over A-SC's 3 active ordinal dimensions; 0.12 keeps candidates within "
            "roughly one declared step of each other in the same region -- a design choice, "
            "not a guide-specified number, frozen before any origin's real clustering result "
            "is seen"),
        "representative_subset_size": representative_subset_size,
        "representative_subset_size_source": "configs/forward_persistence_fp_v1/search_policy.json "
                                             "(FP-03's own frozen cap, reused verbatim)",
        "geometry_version": geometry_version,
        "window_overlaps": overlaps,
        "frozen_at_utc": utcnow(),
    }


def run_fp04(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy)
    started = utcnow()
    economics = default_economics()
    schema = SCHEMAS[ALPHA_ID]

    b_search = _frozen_b_search()
    representative_subset_size = _frozen_representative_subset_size()
    region_policy = freeze_region_policy(b_search=b_search,
                                         representative_subset_size=representative_subset_size)

    lab_run_id = new_lab_run_id("fp04")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    cache = ComputeCache(LAB, "fp04", cache_root=CACHE_ROOT)

    origin_entries = []
    for origin_cutoff in fl.FP04_ORIGIN_GRID:
        origin_entries.append(build_origin_entry(
            cache, schema, origin_cutoff, b_search=b_search,
            representative_subset_size=representative_subset_size, economics=economics,
            producer=f"{lab_run_id}-{origin_cutoff}"))

    ledger = {"schema": "regime_lab.fp04_origin_ledger.v1", "origins": [
        {k: v for k, v in e.items() if k != "_regions_with_forward"} for e in origin_entries]}
    ledger_records_doc = build_ledger_records(origin_entries, region_policy["geometry_version"])

    fresh_trials = sum(len(e["trial_records"]) for e in origin_entries
                       if e["reused_from_cache"] is None and e["wf_ok"])
    reused_origins = [e["origin_cutoff"] for e in origin_entries if e["reused_from_cache"] is not None]
    resource_budget = {
        "schema": "regime_lab.fp04_resource_budget.v1", "lab_run_id": lab_run_id,
        "fp04_wall_seconds_charged_to_shared_ledger": 0,
        "engine_calls_search_trials_fresh": fresh_trials,
        "reused_origins": reused_origins,
        "resource_limits_applied": limits,
        "note": "FP-04's own real engine calls; no shared TE ledger touched",
    }
    test_registry = {"schema": "regime_lab.fp04_test_registry.v1", "lab_run_id": lab_run_id,
                     "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp04_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp04_build") as att:
        writer.write_json("origin_ledger.json", ledger, schema="regime_lab.fp04_origin_ledger.v1")
        writer.write_json("ledger_records.json", ledger_records_doc,
                          schema="regime_lab.fp04_ledger_records.v1")
        writer.write_json("region_policy.json", region_policy,
                          schema="regime_lab.fp04_region_policy.v1")
        writer.write_json("resource_budget.json", resource_budget,
                          schema="regime_lab.fp04_resource_budget.v1")
        writer.write_json("test_registry.json", test_registry,
                          schema="regime_lab.fp04_test_registry.v1")
        writer.write_json("phase_manifest.json", manifest,
                          schema="regime_lab.fp04_phase_manifest.v1")
        att.detail = {"run_dir": str(run_dir)}

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "region_policy.json").write_text(
        json.dumps(region_policy, indent=2) + "\n", encoding="utf-8")
    (run_dir / "region_policy.json").write_text(
        json.dumps(region_policy, indent=2) + "\n", encoding="utf-8")

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, origin_entries=origin_entries,
                                ledger_records_doc=ledger_records_doc, region_policy=region_policy,
                                resource_budget=resource_budget, started=started)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir, region_policy=region_policy,
                                  ledger_records_doc=ledger_records_doc)
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
        for name in ("origin_ledger.json", "ledger_records.json", "region_policy.json",
                     "resource_budget.json", "test_registry.json", "report.md", "handoff.md",
                     "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp04(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, origin_entries, ledger_records_doc, region_policy,
                  resource_budget, started) -> str:
    support = ledger_records_doc["support_summary"]
    lines = [f"# FP-04 — Historical forward ledger and parameter regions ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}",
            f"- alpha: {ALPHA_ID}, symbol: {SYMBOL}, origins: {len(region_policy['origin_grid'])} "
            f"of guide 3.2's ~26-39 research-default target (explicit partial scope, see "
            "region_policy.json.origin_grid_scope_note)",
            f"- B_search (reused from FP-03's frozen search_policy.json): {region_policy['b_search']}",
            f"- fresh engine search-trial calls this run: "
            f"{resource_budget['engine_calls_search_trials_fresh']}",
            f"- origins reused verbatim from .cache (no fresh engine call): "
            f"{resource_budget['reused_origins'] or 'none'}",
            "", "## Per-origin results"]
    for e in origin_entries:
        lines.append(f"### {e['origin_cutoff']}")
        if not e["wf_ok"]:
            lines.append(f"- wf_ok: False, error: {e['wf_error']} -- CENSORED, no region built")
            lines.append("")
            continue
        lines.append(f"- wf_ok: True, trials: {len(e['trial_records'])}/{e['trials_requested']}, "
                     f"wall: {e['wall_seconds_measured']}s, "
                     f"peak_mib: {(e['instrumentation'] or {}).get('peak_mib')}, "
                     f"reused_from_cache: {e['reused_from_cache']}")
        lines.append(f"- regions built: {len(e['regions'])}")
        for region in e["_regions_with_forward"]:
            fwd = region["_forward_result"]
            if fwd and fwd["forward_ok"]:
                d = fwd["decay"]
                lines.append(
                    f"  - {region['region_id']}: support={region['historical_support_within_origin']}, "
                    f"medoid_trial={region['medoid_trial_id']}, "
                    f"is_objective_mean={region['is_quality_distribution']['mean']:.4f}, "
                    f"forward_mean_daily_return={d['forward_metrics']['mean_daily_return']:.6f}, "
                    f"D_mean_daily_return={d['D_mean_daily_return']:.6f} (D=IS-FWD, positive=worse decay)")
            else:
                reason = fwd["reason"] if fwd else "no forward attempt recorded"
                lines.append(f"  - {region['region_id']}: CENSORED -- {reason}")
        lines.append("")
    lines += ["## Support summary (guide FP04-G-SUPPORT)",
             f"- model_ready_count: {support['model_ready_count']} "
             f"(matured AND region_support_within_origin >= {support['min_support_for_model_ready']})",
             f"- descriptive_only_count: {support['descriptive_only_count']}",
             f"- reason for the threshold: {support['min_support_reason']}",
             "", "## Frozen region policy",
             f"```json\n{json.dumps(region_policy, indent=2)}\n```", "",
             "## Glossary",
             "- **region** (a guide 7.3 cluster of real search candidates whose PARAMETERS are "
             "close together, by selector.schema_distance.ParamSchema.distance -- built here per "
             "origin, from that origin's own real trial pool)",
             "- **medoid** (the region's REAL member candidate minimising total distance to the "
             "region's other members -- never an invented centroid; this module's region_medoid)",
             "- **maturity_state** (which of guide 16's five distinctions a ledger record "
             "currently carries -- see forward_ledger.py's module docstring for FP-04's "
             "operational definition of each)",
             "- **matured_forward_record** (a record whose forward window has closed AND produced "
             "a valid forward metric -- the ONLY state a learner may read, guide item 6)",
             "- **censored_or_failed_record** (an origin search or forward evaluation that failed "
             "or could not produce a valid metric -- label stays null with a reason, never zero)",
             "- **decay** (D_mean_daily_return = IS mean daily return - forward mean daily return; "
             "positive is WORSE decay, guide 8.5's D formula, this run's diagnostic field, NOT "
             "the primary FP-05 target)",
             "- **origin** (one historical point in time at which a real search was run from "
             "permitted past data only -- guide 7's chronological origin grid)",
             "- **support** (region_support_within_origin: how many of an origin's OWN real "
             "search candidates fell into a given region -- guide 7.5 forbids treating this as a "
             "cross-origin count)",
             "", "## Permitted conclusions",
             "- Technical: a real historical forward ledger was built at 12 real chronological "
             "origins, region geometry from real search candidates (params only, causality proved "
             "by FP04-T01-T04), forward evaluation on real IS/forward windows, maturity/censorship "
             "states derived per guide 16, origin weighting proved equal-per-origin (FP04-T06), "
             "incremental rebuild proved to skip the engine on existing valid origins (FP04-T07/T08).",
             "- Research: NOT_ASSESSED -- FP-04 builds the archive; it makes no market/edge claim "
             "and compares no arms (that is FP-05 onward).",
             "- Scope: 12 of ~26-39 origins -- an explicit, disclosed partial archive, extensible "
             "without recomputation (see origin_grid_scope_note above).",
             "- Owner review: PENDING; FP-05 needs its own approval (R-18).", ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, region_policy, ledger_records_doc) -> str:
    support = ledger_records_doc["support_summary"]
    return "\n".join([
        f"# FP-04 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        f"- origins in archive: {len(region_policy['origin_grid'])} "
        f"(of guide 3.2's ~26-39 research-default target)",
        f"- model_ready records: {support['model_ready_count']}, "
        f"descriptive_only: {support['descriptive_only_count']}",
        "- next authorized action: NONE until the owner approves FP-04 -> FP-05 (R-18), "
        "unless already pre-approved and recorded.",
        "- FP-05 (guide 17) must reuse: ledger_records.json via fl.matured_view/training_view "
        "(never read origin_ledger.json's raw trial pool directly for fitting), "
        "fp.chronology.chronological_split (already wired inside training_view) for the "
        "no-future-label guard, and region_policy.json's frozen geometry_version.",
        "- extending the origin grid later (toward the guide's ~26-39 target) is INCREMENTAL: "
        "fl.incremental_rebuild only calls the engine for cutoffs not already present with a "
        "valid record (FP04-T07/T08, both tested) -- never a redo of these 12.",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp04(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
