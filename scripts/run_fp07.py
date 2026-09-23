#!/usr/bin/env python3
"""Build FP-07 artifacts (guide section 19): the locked A/B/C study.

Real work, in order (never concurrent -- registered budget is workers=1):

  1. Freeze the study (guide 19 precondition: window/cells/budget/metrics
     fixed BEFORE any account runs) into configs/.../fp07_study_freeze.json
     -- primary cell, the 12 reused origins, the shared continuous frame
     span, the FROZEN ridge alphas (read from FP-05/06's own already-
     committed evidence, never re-selected here -- guide 19 item 9: don't
     change the algorithm from a prefix outcome), and a pre-run cost
     estimate from a real measured pilot rate.
  2. At every one of FP-04's 12 origins, compute all three arms' selections
     from the SAME shared pool (fp.locked_study.arm_a_selection /
     walk_forward_b_selection / walk_forward_c_selection) -- zero new
     search-trial engine calls, all of it real cache-hit reads of FP-04's
     already-cached search results and FP-05/06's already-built feature
     archive.
  3. Admission before deployment (fp.admission_wiring, reused verbatim) for
     each arm, then ONE real fp.evaluator.run_deployment call per arm over
     a SHARED continuous 1-minute frame spanning the full registered
     `development` role (2021-01-01 .. 2023-12-31) -- never re-run mid-
     study, never re-optimised.
  4. Canonical daily returns per arm, a D1 table (per-SELECTION IS-vs-
     realized-forward-label lookup from the archive, never re-derived by
     slicing the deployment account -- guide 19 precondition: candidate-
     forward and deployment metrics stay separate), and paired contrasts
     (primary C-B, secondary B-A/C-A) via the SAME registered 28-day block
     bootstrap RA-07/RF-05 already built.

FP-07 reaches no verdict: guide 19's own exit gate (FP07-G-SCOPE) forbids
calling a single, unreplicated cell a finished scientific study. FP-08
(replication) is the phase that can support a claim.

Usage:
  lab_venv/bin/python scripts/run_fp07.py --pytest-xml <junit xml of the FP-07 tests>
Exit 0 iff the FP-07 verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import locked_study as ls  # noqa: E402
from crypto_regime_lab.fp import selector_b as sb  # noqa: E402
from crypto_regime_lab.fp import selector_c as sc  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics, run_deployment  # noqa: E402
from crypto_regime_lab.fp.verifier_fp07 import REQUIRED_GATES, verify_fp07  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

PHASE_ID = "FP-07"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
FEATURE_CACHE = LAB / ".cache" / "fp05_features" / "rows.json"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"

ALPHA_B = 10.0
ALPHA_B_SOURCE = ("evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/"
                  "model_selection.json:selected_alpha")
ALPHA_C = 10.0
ALPHA_C_SOURCE = ("evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7/"
                  "oof_diagnostics_c.json:selected_alpha_c")

FRAME_START = "2021-01-01"
FRAME_END = "2024-01-01"   # exclusive; the full registered `development` role, never touching
                           # `outer_evaluation` (2024-01-01 onward)
PILOT_BARS_PER_SECOND = 6979.0   # measured: 84,960 bars / 12.17s, report_level='score', real cache miss

TEST_NODE_IDS = [
    "test_load_origin_wf_result_reads_the_real_fp04_cache",
    "test_load_origin_wf_result_raises_on_a_missing_origin",
    "test_arm_a_selection_extracts_selected_params",
    "test_arm_a_selection_raises_when_selected_params_missing",
    "test_walk_forward_b_selection_falls_back_to_a_at_the_first_origin",
    "test_walk_forward_b_selection_falls_back_when_nothing_clears_the_utility_floor",
    "test_walk_forward_b_selection_selects_a_real_scored_candidate_when_eligible",
    "test_walk_forward_b_selection_never_uses_a_later_origins_record",
    "test_walk_forward_c_selection_falls_back_to_a_when_b_already_did",
    "test_walk_forward_c_selection_falls_back_to_b_when_nothing_c_scored_is_eligible",
    "test_walk_forward_c_selection_selects_a_real_candidate_when_eligible",
    "test_build_admitted_schedule_admits_a_real_selection",
    "test_build_run_deployment_schedule_maps_origins_to_real_bar_indices",
    "test_build_run_deployment_schedule_skips_a_true_flat_fallback_fold",
    "test_build_run_deployment_schedule_raises_when_everything_fell_back",
    "test_build_run_deployment_schedule_raises_when_origin_is_not_an_exact_bar",
    "test_account_daily_returns_matches_the_synthetic_daily_growth_rate",
    "test_paired_contrast_c_minus_b_sign_and_status",
    "test_paired_contrast_reports_inconclusive_support_below_28_common_days",
    "test_d1_decay_sign_convention_matches_fp01_repaired_convention",
    "test_fp07_verifier_passes_on_a_valid_bundle",
    "test_fp07_verifier_fails_on_empty_dir",
    "test_fp07_verifier_fails_on_tampered_artifact",
    "test_fp07_g_pool_fails_when_a_selection_record_id_is_not_in_the_shared_pool",
    "test_fp07_g_exec_fails_when_an_arm_has_zero_fills",
    "test_fp07_g_account_fails_when_arms_do_not_share_a_common_calendar",
    "test_fp07_g_decay_fails_when_stored_d1_does_not_match_is_minus_forward",
    "test_fp07_g_decay_fails_on_a_fabricated_number_for_a_fallback_origin",
    "test_fp07_g_cost_fails_when_peak_memory_exceeds_the_registered_budget",
    "test_fp07_g_cost_fails_when_no_pre_registered_cost_estimate_exists",
    "test_fp07_g_cost_fails_when_a_budget_exception_is_applied_but_not_disclosed",
    "test_fp07_g_cost_fails_when_the_exception_decision_id_does_not_match_the_freeze_disclosure",
    "test_fp07_g_scope_fails_when_the_report_never_names_fp08",
    "test_fp07_g_scope_fails_on_a_forbidden_overclaim_phrase",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Registered LAB-01 budget (configs/study_registration.json) stays 4 GiB for every other
# phase/call in this lab. FP-07's own 3 run_deployment calls span ~1.58M one-minute bars in ONE
# call each -- a scale no prior phase has run -- and a real RLIMIT_AS MemoryError was measured at
# ~1.2-1.36M bars (4 real probe runs: 100k/400k/800k/1.2M bars, ~1.77 MiB RSS per 1000 bars,
# linear). Owner-approved, disclosed, one-time exception for FP-07 ONLY (AskUserQuestion +
# evidence/regime_time_edge_ra_v1/owner_decisions.jsonl decision_id dec-9cc3ec3e712cf61b): raise
# the virtual-address-space ceiling to 7 GiB, while projected ACTUAL resident memory (~3.1 GiB for
# the full span) stays well inside the host's measured ~4.1 GiB then-available RAM. This constant
# is read ONLY by this script; it does not change configs/study_registration.json.
FP07_RLIMIT_AS_GIB = 7.0
FP07_RLIMIT_AS_EXCEPTION_DECISION = "dec-9cc3ec3e712cf61b"


def _apply_resource_limits(policy, *, working_memory_gib_override: float | None = None) -> dict:
    env = lab_worker_env(policy)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[key] = env[key]
    budget = policy.raw["resource_budget"]
    registered_gib = budget["working_memory_gib"]
    applied_gib = working_memory_gib_override if working_memory_gib_override is not None else registered_gib
    cap_bytes = int(applied_gib * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"cpu_limit": env["OMP_NUM_THREADS"], "rlimit_as_gib": applied_gib,
            "registered_rlimit_as_gib": registered_gib,
            "exception_applied": applied_gib != registered_gib,
            "exception_decision_id": (FP07_RLIMIT_AS_EXCEPTION_DECISION
                                      if applied_gib != registered_gib else None),
            "previous_soft_gib": (None if soft == resource.RLIM_INFINITY
                                  else round(soft / (1 << 30), 2))}


def load_b_rows() -> list[dict]:
    if not FEATURE_CACHE.is_file():
        raise SystemExit(f"FP-07 requires FP-05's feature cache at {FEATURE_CACHE}")
    return json.loads(FEATURE_CACHE.read_text())


def build_c_rows(b_rows: list[dict]) -> list[dict]:
    origins = sorted({r["origin_cutoff"] for r in b_rows})
    context_by_origin = {}
    for origin_cutoff in origins:
        frame = sb.load_origin_is_frame(ALPHA_ID, origin_cutoff)
        context_by_origin[origin_cutoff] = sc.compute_context_features(frame)
    return [sc.build_c_row(row, context_by_origin[row["origin_cutoff"]]) for row in b_rows]


def record_id_for_d1(result: dict, *, fallback_result: dict | None) -> tuple[str | None, str | None]:
    """D1's own lookup key: the record_id this selection's forward label
    lives under, or a disclosed reason there is none. A FALLBACK_TO_B result
    with no record_id of its own (the origin-level branch, not the per-
    candidate OOD branch) reuses B's OWN record_id -- it IS the same
    candidate, not a proxy."""
    rid = result.get("record_id")
    if rid is not None:
        return rid, None
    if result.get("source") == "FALLBACK_TO_B" and fallback_result is not None:
        rid2 = fallback_result.get("record_id")
        if rid2 is not None:
            return rid2, None
    return None, (f"{result.get('source')}: no forward-labelled record for this origin's "
                  f"selection ({result.get('reason', 'no reason given')})")


def run_fp07(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy, working_memory_gib_override=FP07_RLIMIT_AS_GIB)
    started = utcnow()
    t_wall_start = time.perf_counter()
    economics = default_economics()

    lab_run_id = new_lab_run_id("fp07")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    cache = ComputeCache(LAB, "fp04", cache_root=CACHE_ROOT)   # same namespace: real cache hits

    b_rows = load_b_rows()
    c_rows = build_c_rows(b_rows)
    origins_sorted = sorted({r["origin_cutoff"] for r in b_rows},
                            key=lambda o: next(r["origin_time"] for r in b_rows
                                              if r["origin_cutoff"] == o))

    frame_days = (pd.Timestamp(FRAME_END) - pd.Timestamp(FRAME_START)).days
    estimated_bars = frame_days * 1440
    est_minutes_per_arm = estimated_bars / PILOT_BARS_PER_SECOND / 60.0
    study_freeze = {
        "schema": "regime_lab.fp07_study_freeze.v1",
        "primary_cell": {"alpha_id": ALPHA_ID, "symbol": SYMBOL},
        "origins": origins_sorted,
        "frame_span": {
            "start": FRAME_START, "end": FRAME_END,
            "reason": "the full registered `development` data role (configs/study_registration.json, "
                      "2020-01-01..2023-12-31) -- gives the LAST origin's selection genuine deployed "
                      "forward time (2023-10-01 through the role's own end) rather than stopping at its "
                      "bare 28-day forward-label maturity window, while never touching `outer_evaluation` "
                      "(2024-01-01 onward)"},
        "arms": list(ls.ARMS),
        "economics": economics,
        "model_hyperparameters": {
            "alpha_b": ALPHA_B, "alpha_b_source": ALPHA_B_SOURCE,
            "alpha_c": ALPHA_C, "alpha_c_source": ALPHA_C_SOURCE,
            "frozen_reason": "guide 19 item 9 (báo prefix progress nhưng không đổi algorithm theo "
                             "prefix outcome): the ridge alpha was already selected via nested "
                             "walk-forward OOF in FP-05/FP-06, before this locked study started; only "
                             "the model's COEFFICIENTS refit per origin, from that origin's own "
                             "matured training rows -- the hyperparameter itself never moves"},
        "utility_floor_daily": sb.UTILITY_FLOOR_DAILY, "support_floor": sb.MIN_SUPPORT_FOR_ELIGIBLE,
        "d1_method": "per-selection lookup of the SAME record's own (is_mean_daily_return, forward "
                    "label) already computed in FP-04's archive -- never re-derived by slicing the "
                    "continuous deployment account (guide 19 precondition: candidate-forward and "
                    "deployment metrics kept separate)",
        "primary_contrast": "C_FP_CONTEXT - B_FP_PERSISTENCE",
        "secondary_contrasts": ["B_FP_PERSISTENCE - A_STOCK_CAL", "C_FP_CONTEXT - A_STOCK_CAL"],
        "bootstrap": {
            "method": "time_edge.inference.block_mean (RA-07/RF-05's own registered 28-day block "
                     "bootstrap, reused verbatim, never reimplemented)",
            "delta": sb.UTILITY_FLOOR_DAILY, "delta_source": sb.UTILITY_FLOOR_SOURCE},
        "cost_estimate": {
            "pilot_measurement": "84,960 one-minute bars processed via run_deployment in 12.17s "
                                 "(report_level='score', real cache miss) -- measured in this study's "
                                 "own planning step before any full-span account ran",
            "pilot_bars_per_second": PILOT_BARS_PER_SECOND,
            "frame_span_days": frame_days, "estimated_bars_per_arm": estimated_bars,
            "estimated_minutes_per_arm": round(est_minutes_per_arm, 2),
            "estimated_total_minutes_3_arms": round(est_minutes_per_arm * 3, 2)},
        "resource_budget_exception": {
            "registered_working_memory_gib": 4.0, "applied_working_memory_gib": FP07_RLIMIT_AS_GIB,
            "decision_id": FP07_RLIMIT_AS_EXCEPTION_DECISION,
            "decision_ref": "evidence/regime_time_edge_ra_v1/owner_decisions.jsonl",
            "reason": "a first real attempt at the full ~1.58M-bar/3-arm span hit a real RLIMIT_AS "
                     "MemoryError at bar_index=1,360,272 against the registered 4 GiB cap. Four real "
                     "probe runs (100k/400k/800k/1.2M bars, single-activation schedule, "
                     "report_level='score') measured linear RSS growth (~1.77 MiB per 1000 bars: "
                     "454/979/1687 MiB, then a MemoryError at 1.2M bars with RSS at 2403 MiB) -- the "
                     "failure is a virtual-address-space ceiling, not an actual host RAM shortage: "
                     "the full span's ACTUAL resident memory projects to ~3.1 GiB, against a "
                     "then-measured host state of 9.7 GiB total / ~4.1 GiB available. Presented to "
                     "the owner via AskUserQuestion with this real data before being applied; scoped "
                     "to FP-07's own run_deployment calls ONLY -- configs/study_registration.json's "
                     "registered 4 GiB stays unchanged for every other phase/call in this lab.",
        },
        "frozen_at_utc": utcnow(),
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "fp07_study_freeze.json").write_text(
        json.dumps(study_freeze, indent=2) + "\n", encoding="utf-8")

    # -- selections at every origin, all three arms, from the SAME pool --
    selections_by_origin = {"A_STOCK_CAL": {}, "B_FP_PERSISTENCE": {}, "C_FP_CONTEXT": {}}
    for origin in origins_sorted:
        wf = ls.load_origin_wf_result(origin)
        a_params = ls.arm_a_selection(wf)
        selections_by_origin["A_STOCK_CAL"][origin] = {"source": "A_STOCK_INSTALLED", "params": a_params}
        b_res = ls.walk_forward_b_selection(b_rows, {}, origin_cutoff=origin, alpha=ALPHA_B,
                                            utility_floor=sb.UTILITY_FLOOR_DAILY,
                                            support_floor=sb.MIN_SUPPORT_FOR_ELIGIBLE)
        selections_by_origin["B_FP_PERSISTENCE"][origin] = b_res
        c_res = ls.walk_forward_c_selection(c_rows, origin_cutoff=origin, alpha=ALPHA_C,
                                            utility_floor=sb.UTILITY_FLOOR_DAILY,
                                            support_floor=sb.MIN_SUPPORT_FOR_ELIGIBLE, b_result=b_res)
        selections_by_origin["C_FP_CONTEXT"][origin] = c_res

    admitted = {arm: ls.build_admitted_schedule(selections_by_origin[arm], arm=arm) for arm in ls.ARMS}

    frame, _partitions = load_real_bars(SYMBOL, start=FRAME_START, end=FRAME_END)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()

    schedules = {arm: ls.build_run_deployment_schedule(admitted[arm], frame_index=frame.index)
                for arm in ls.ARMS}

    # -- 3 real continuous-account deployments, one shared frame --
    per_arm_seconds, payloads = {}, {}
    for arm in ls.ARMS:
        t0 = time.perf_counter()
        payload, event = run_deployment(cache, LAB, ALPHA_ID, frame, schedules[arm],
                                        ready_at=frame.index[0], report_level="score",
                                        economics=economics, producer=f"{lab_run_id}-{arm}")
        per_arm_seconds[arm] = time.perf_counter() - t0
        payloads[arm] = {"payload": payload, "cache_event": event["status"]}

    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0   # KB -> MiB on Linux
    total_wall = time.perf_counter() - t_wall_start

    daily_returns, accounts_by_arm = {}, {}
    for arm in ls.ARMS:
        payload = payloads[arm]["payload"]
        audit = payload["selected_audit"]
        dr = ls.account_daily_returns(payload, frame, initial_capital=economics["initial_capital"])
        daily_returns[arm] = dr
        accounts_by_arm[arm] = {
            "status": "OK", "fill_count": len(audit["fills"]), "bars": len(frame),
            "entries": payload["trial_scalar"]["entries"],
            "engine_fill_count": audit["engine_fill_count"],
            "cache_event": payloads[arm]["cache_event"],
            "wall_seconds_measured": round(per_arm_seconds[arm], 3),
            "daily_returns_start": dr[0][0] if dr else None,
            "daily_returns_end": dr[-1][0] if dr else None,
            "daily_return_days": len(dr),
            "initial_capital": economics["initial_capital"],
            "n_activations_requested": len(schedules[arm]),
        }
    accounts_doc = {"schema": "regime_lab.fp07_accounts.v1", "frame_bars": len(frame),
                    "shared_initial_capital": economics["initial_capital"], "by_arm": accounts_by_arm}

    # -- D1 table: per-selection lookup, never account-segment slicing --
    b_rows_by_id = {r["record_id"]: r for r in b_rows}
    c_rows_by_id = {r["record_id"]: r for r in c_rows}
    d1_rows = []
    for origin in origins_sorted:
        for arm, rows_by_id in (("B_FP_PERSISTENCE", b_rows_by_id), ("C_FP_CONTEXT", c_rows_by_id)):
            result = selections_by_origin[arm][origin]
            fallback_result = selections_by_origin["B_FP_PERSISTENCE"][origin] if arm == "C_FP_CONTEXT" else None
            rid, reason = record_id_for_d1(result, fallback_result=fallback_result)
            if rid is None:
                d1_rows.append({"arm": arm, "origin_cutoff": origin, "record_id": None,
                               "is_mean_daily_return": None, "forward_label": None,
                               "D_mean_daily_return": None, "reason": reason})
                continue
            row = rows_by_id[rid]
            is_v, fwd_v = row["is_mean_daily_return"], row["label"]
            if fwd_v is None:
                d1_rows.append({"arm": arm, "origin_cutoff": origin, "record_id": rid,
                               "is_mean_daily_return": is_v, "forward_label": None,
                               "D_mean_daily_return": None,
                               "reason": f"record {rid}'s own forward label is not yet matured"})
                continue
            d = ls.d1_decay(is_v, fwd_v)
            d1_rows.append({"arm": arm, "origin_cutoff": origin, "record_id": rid,
                           "is_mean_daily_return": is_v, "forward_label": fwd_v,
                           "D_mean_daily_return": d["D_mean_daily_return"], "reason": None})
    a_exact_matches = 0
    for origin in origins_sorted:
        a_params = selections_by_origin["A_STOCK_CAL"][origin]["params"]
        match = [r for r in b_rows if r["origin_cutoff"] == origin and r["params"] == a_params]
        if match:
            a_exact_matches += 1
            row = match[0]
            fwd_v = row["label"]
            d_val = ls.d1_decay(row["is_mean_daily_return"], fwd_v)["D_mean_daily_return"] if fwd_v is not None else None
            d1_rows.append({"arm": "A_STOCK_CAL", "origin_cutoff": origin, "record_id": row["record_id"],
                           "is_mean_daily_return": row["is_mean_daily_return"], "forward_label": fwd_v,
                           "D_mean_daily_return": d_val,
                           "reason": None if d_val is not None else "forward label not yet matured"})
        else:
            d1_rows.append({"arm": "A_STOCK_CAL", "origin_cutoff": origin, "record_id": None,
                           "is_mean_daily_return": None, "forward_label": None,
                           "D_mean_daily_return": None,
                           "reason": "Arm A's stock selection does not exactly match a region-archive "
                                     "medoid at this origin -- no forward-labelled record exists for "
                                     "it in this archive"})
    d1_doc = {"schema": "regime_lab.fp07_d1_table.v1",
             "convention": "D = IS - forward; positive = worse decay (guide 8.5, FP-01 repaired)",
             "arm_a_exact_match_count": a_exact_matches, "arm_a_exact_match_denominator": len(origins_sorted),
             "rows": d1_rows}

    delta = sb.UTILITY_FLOOR_DAILY
    primary = ls.paired_contrast(daily_returns["C_FP_CONTEXT"], daily_returns["B_FP_PERSISTENCE"],
                                 label="C_FP_CONTEXT - B_FP_PERSISTENCE", delta=delta)
    sec_ba = ls.paired_contrast(daily_returns["B_FP_PERSISTENCE"], daily_returns["A_STOCK_CAL"],
                                label="B_FP_PERSISTENCE - A_STOCK_CAL", delta=delta)
    sec_ca = ls.paired_contrast(daily_returns["C_FP_CONTEXT"], daily_returns["A_STOCK_CAL"],
                                label="C_FP_CONTEXT - A_STOCK_CAL", delta=delta)
    contrasts_doc = {"schema": "regime_lab.fp07_paired_contrasts.v1", "primary": primary,
                    "secondary": {"B_FP_PERSISTENCE - A_STOCK_CAL": sec_ba,
                                 "C_FP_CONTEXT - A_STOCK_CAL": sec_ca}}

    pools_doc = {
        "schema": "regime_lab.fp07_common_candidate_pools.v1", "shared_across_arms": True,
        "record_ids_by_origin": {
            origin: [{"record_id": r["record_id"], "region_id": r["region_id"]}
                    for r in b_rows if r["origin_cutoff"] == origin]
            for origin in origins_sorted},
    }
    selections_doc = {
        "schema": "regime_lab.fp07_selections.v1",
        "by_origin": {origin: {arm: selections_by_origin[arm][origin] for arm in ls.ARMS}
                     for origin in origins_sorted},
    }
    admission_doc = {
        "schema": "regime_lab.fp07_admission_and_schedules.v1",
        "by_arm": {arm: {"lineage": admitted[arm]["lineage"], "n_admitted": len(schedules[arm]),
                        "n_origins": len(origins_sorted)} for arm in ls.ARMS},
    }
    resource_budget_doc = {
        "schema": "regime_lab.fp07_resource_budget.v1", "lab_run_id": lab_run_id,
        "resource_limits_applied": limits,
        "measured": {"peak_rss_mib": round(peak_rss_mib, 1), "total_wall_seconds": round(total_wall, 2),
                    "per_arm_wall_seconds": {a: round(s, 2) for a, s in per_arm_seconds.items()},
                    "frame_bars": len(frame)},
        "note": "3 real fp.evaluator.run_deployment calls (report_level='score', FUP-04/FP-02-proven "
               "equity-exact vs audit) over the SAME shared frame, one per arm -- zero new "
               "search-trial engine calls (Arm A/B/C selection reuses FP-04's already-cached search "
               "results and FP-05/06's already-built feature archive)",
    }
    test_registry_doc = {"schema": "regime_lab.fp07_test_registry.v1", "lab_run_id": lab_run_id,
                        "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp07_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp07_build") as att:
        writer.write_json("study_freeze.json", study_freeze, schema=study_freeze["schema"])
        writer.write_json("common_candidate_pools.json", pools_doc, schema=pools_doc["schema"])
        writer.write_json("selections.json", selections_doc, schema=selections_doc["schema"])
        writer.write_json("admission_and_schedules.json", admission_doc, schema=admission_doc["schema"])
        writer.write_json("accounts.json", accounts_doc, schema=accounts_doc["schema"])
        writer.write_json("d1_table.json", d1_doc, schema=d1_doc["schema"])
        writer.write_json("paired_contrasts.json", contrasts_doc, schema=contrasts_doc["schema"])
        writer.write_json("resource_budget.json", resource_budget_doc, schema=resource_budget_doc["schema"])
        writer.write_json("test_registry.json", test_registry_doc, schema=test_registry_doc["schema"])
        writer.write_json("phase_manifest.json", manifest, schema=manifest["schema"])
        att.detail = {"run_dir": str(run_dir)}

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, started=started,
                                study_freeze=study_freeze, selections_by_origin=selections_by_origin,
                                accounts_doc=accounts_doc, d1_doc=d1_doc, contrasts_doc=contrasts_doc,
                                resource_budget_doc=resource_budget_doc, origins_sorted=origins_sorted)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir, contrasts_doc=contrasts_doc)
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
        for name in ("study_freeze.json", "common_candidate_pools.json", "selections.json",
                     "admission_and_schedules.json", "accounts.json", "d1_table.json",
                     "paired_contrasts.json", "resource_budget.json", "test_registry.json",
                     "report.md", "handoff.md", "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp07(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id, "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, started, study_freeze, selections_by_origin, accounts_doc,
                  d1_doc, contrasts_doc, resource_budget_doc, origins_sorted) -> str:
    lines = [f"# FP-07 — Locked A/B/C study ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}",
            f"- alpha: {ALPHA_ID}, symbol: {SYMBOL}, {len(origins_sorted)} origins "
            f"(reused verbatim from FP-04's frozen grid)",
            f"- shared continuous frame: {study_freeze['frame_span']['start']} .. "
            f"{study_freeze['frame_span']['end']} (exclusive), {accounts_doc['frame_bars']} bars",
            "", "## Study freeze (guide 19 precondition, written before any account ran)",
            f"- alpha_B={study_freeze['model_hyperparameters']['alpha_b']} "
            f"(source: {study_freeze['model_hyperparameters']['alpha_b_source']})",
            f"- alpha_C={study_freeze['model_hyperparameters']['alpha_c']} "
            f"(source: {study_freeze['model_hyperparameters']['alpha_c_source']})",
            f"- pre-run cost estimate: {study_freeze['cost_estimate']['estimated_minutes_per_arm']} "
            f"min/arm, {study_freeze['cost_estimate']['estimated_total_minutes_3_arms']} min total "
            f"(from a real {study_freeze['cost_estimate']['pilot_bars_per_second']:.0f} bars/sec "
            "pilot measurement)",
            f"- **disclosed resource-budget exception**: working_memory_gib "
            f"{study_freeze['resource_budget_exception']['registered_working_memory_gib']} -> "
            f"{study_freeze['resource_budget_exception']['applied_working_memory_gib']} "
            f"(decision {study_freeze['resource_budget_exception']['decision_id']}, "
            f"{study_freeze['resource_budget_exception']['decision_ref']}) -- a real MemoryError "
            "at ~1.2-1.36M bars against the registered 4 GiB cap on a first real attempt, measured "
            "via 4 real probe runs before this exception was applied; the registered 4 GiB budget "
            "is unchanged for every other phase/call in this lab",
            "", "## Selections per origin (all three arms, same shared pool)",
            "| origin | A source | B source | C source |", "|---|---|---|---|"]
    for origin in origins_sorted:
        a = selections_by_origin["A_STOCK_CAL"][origin]["source"]
        b = selections_by_origin["B_FP_PERSISTENCE"][origin]["source"]
        c = selections_by_origin["C_FP_CONTEXT"][origin]["source"]
        lines.append(f"| {origin} | {a} | {b} | {c} |")
    n_b_selected = sum(1 for o in origins_sorted
                      if selections_by_origin["B_FP_PERSISTENCE"][o]["source"] != "FALLBACK_TO_A")
    n_c_context = sum(1 for o in origins_sorted
                      if selections_by_origin["C_FP_CONTEXT"][o]["source"] not in
                      ("FALLBACK_TO_A", "FALLBACK_TO_B"))
    b_admission_origins = [o for o in origins_sorted
                           if selections_by_origin["B_FP_PERSISTENCE"][o]["source"] != "FALLBACK_TO_A"]
    c_matches_b_everywhere = all(
        selections_by_origin["C_FP_CONTEXT"][o]["params"] == selections_by_origin["B_FP_PERSISTENCE"][o]["params"]
        for o in b_admission_origins) if b_admission_origins else False
    lines += ["", f"- Arm B admitted a new selection at {n_b_selected}/{len(origins_sorted)} origins "
             f"({len(origins_sorted) - n_b_selected} had NO new admission -- the account kept "
             "whatever version was already active, or stayed FLAT_UNTIL_READY pre-first-admission; "
             "never a borrowed Arm A value)",
             f"- Arm C used a context-conditioned prediction at {n_c_context}/{len(origins_sorted)} "
             "origins"]
    if n_c_context == 0 and c_matches_b_everywhere and b_admission_origins:
        lines.append(
            f"- **DEGENERATE: C_FP_CONTEXT == B_FP_PERSISTENCE in this run.** At all "
            f"{len(b_admission_origins)} origins where B admitted a new selection "
            f"({', '.join(b_admission_origins)}), C's own utility-maximizing candidate was "
            "out-of-distribution relative to its training window's context range, so C fell back "
            "to B's exact prediction every time (source=FALLBACK_TO_B, never CONTEXT_CONDITIONED) "
            "-- C's params are IDENTICAL to B's at every real admission, making the two accounts "
            "byte-for-byte the same (same fills, same D1). This is guide 20/FP08.5's own named "
            "outcome category: *\"C≈B vì fallback → Context mechanism chưa được exercise đủ\"* "
            "(C looks like B because of fallback -> the context mechanism was not exercised "
            "enough). The PRIMARY contrast below (C-B) is therefore DEGENERATE BY CONSTRUCTION "
            "in this run -- estimate exactly 0.0, not a measured absence of effect.")
    lines += ["", "## Accounts (FP07-G-EXEC/ACCOUNT)",
             "| arm | fills | entries | daily-return days | window |", "|---|---|---|---|---|"]
    for arm, info in accounts_doc["by_arm"].items():
        lines.append(f"| {arm} | {info['fill_count']} | {info['entries']} | "
                     f"{info['daily_return_days']} | {info['daily_returns_start']} .. "
                     f"{info['daily_returns_end']} |")
    lines += ["", "## D1 table (FP07-G-DECAY) -- per-selection IS vs realized forward label",
             f"- convention: {d1_doc['convention']}",
             f"- Arm A: {d1_doc['arm_a_exact_match_count']}/{d1_doc['arm_a_exact_match_denominator']} "
             "origins had an exact params match to a region-archive record (Arm A's stock pick is "
             "measured, not assumed, to rarely coincide with a region medoid)"]
    available = [r for r in d1_doc["rows"] if r["D_mean_daily_return"] is not None]
    lines.append(f"- {len(available)}/{len(d1_doc['rows'])} rows carry a real D1 value; the rest are "
                "null with a disclosed reason (no forward-labelled record for that selection)")
    if available:
        import statistics as _st
        for arm in ("A_STOCK_CAL", "B_FP_PERSISTENCE", "C_FP_CONTEXT"):
            vals = [r["D_mean_daily_return"] for r in available if r["arm"] == arm]
            if vals:
                lines.append(f"  - {arm}: mean D1={_st.fmean(vals):.6f} over {len(vals)} selection(s)")
    lines += ["", "## Paired contrasts (FP07-G-SCOPE: primary C-B, secondary diagnostic only)",
             f"- **PRIMARY: {contrasts_doc['primary']['label']}**: "
             f"status={contrasts_doc['primary']['status']}"]
    if contrasts_doc["primary"]["status"] == "ESTIMATED":
        p = contrasts_doc["primary"]
        lines.append(f"    estimate={p['estimate']:.6f}/day, ci95={p.get('ci95_basic')}, "
                    f"p_one_sided={p.get('p_one_sided')}, n_common_days={p.get('n_common_days')}")
    else:
        lines.append(f"    reason: {contrasts_doc['primary'].get('reason')}")
    for label, c in contrasts_doc["secondary"].items():
        lines.append(f"- secondary/diagnostic: {label}: status={c['status']}"
                     + (f", estimate={c['estimate']:.6f}/day" if c["status"] == "ESTIMATED" else
                       f", reason={c.get('reason')}"))
    lines += ["", "## Resource budget (FP07-G-COST)",
             f"- measured peak RSS: {resource_budget_doc['measured']['peak_rss_mib']} MiB "
             f"(budget: {resource_budget_doc['resource_limits_applied']['rlimit_as_gib']} GiB)",
             f"- measured total wall time: {resource_budget_doc['measured']['total_wall_seconds']}s "
             f"across 3 arms (per-arm: "
             f"{resource_budget_doc['measured']['per_arm_wall_seconds']})",
             "", "## Glossary",
             "- **primary cell** (guide 19: the one alpha/symbol combination this locked study "
             f"runs -- {ALPHA_ID}/{SYMBOL}, the same cell FP-03/04/05/06 already qualified and "
             "built on)",
             "- **whole-policy fallback period** (guide 19 item 8: an origin where a "
             "forward-persistent arm has no new admission -- too little matured training history, "
             "or no candidate cleared the utility/support floor -- so the account keeps its "
             "currently active version, or stays FLAT_UNTIL_READY before its first-ever admission; "
             "never a value borrowed from Arm A)",
             "- **D1** (guide 8.5/FP-01: a selection's own in-sample mean daily return minus its "
             "OWN realized forward-window mean daily return; positive means the selection performed "
             "worse going forward than in-sample -- decay)",
             "- **block bootstrap** (time_edge.inference.block_mean: RA-07/RF-05's own registered "
             "28-day non-overlapping block resample used for every paired contrast's CI/p-value in "
             "this lab, reused verbatim here, never reimplemented)",
             "- **primary vs secondary contrast** (guide 19's own output list separates 'paired "
             "contrasts' without ranking one as the sole claim; this report treats C-B as PRIMARY "
             "per FP-GUIDE-1.0's stated research question migration -- which parameter REGION a "
             "forward-persistent selector picks, with/without context -- and B-A/C-A as diagnostic "
             "context, not a second primary claim)",
             "- **RLIMIT_AS / resource-budget exception** (the OS-level ceiling on a process's "
             "virtual address space this lab uses to turn an uncontrolled OOM kill into a "
             "catchable Python MemoryError, CLAUDE.md's registered hard boundary of <=4 GiB "
             "working set; FP-07's own 3 run_deployment calls needed a disclosed, owner-approved, "
             "one-time exception to 7 GiB -- see 'disclosed resource-budget exception' above -- "
             "because a single continuous account over ~1.58M bars is a new scale for this lab, "
             "never because the registered 4 GiB budget changed for anything else)",
             "", "## Permitted conclusions",
             "- Technical: all three arms selected from the SAME shared per-origin candidate pool "
             "(FP07-G-POOL), all three ran a real continuous deployment account over the identical "
             f"{accounts_doc['frame_bars']}-bar shared frame with real fills (FP07-G-EXEC), daily "
             "returns reconcile to a common calendar window (FP07-G-ACCOUNT), D1 values are "
             "recomputed from their own raw (is_mean, forward_label) pairs and fallback origins stay "
             "null with a reason rather than a fabricated number (FP07-G-DECAY), and the measured "
             "compute cost is disclosed against the pre-registered estimate and the applied "
             f"{study_freeze['resource_budget_exception']['applied_working_memory_gib']} GiB budget "
             "(the registered 4 GiB budget's own disclosed, owner-approved exception -- see above) "
             "(FP07-G-COST).",
             "- Research: NOT_ASSESSED at the verdict level. FP-07 is ONE cell, ONE replication, on "
             "REAL market data with no placebo/randomization control of its own -- guide 19's own "
             "exit gate (FP07-G-SCOPE) forbids calling this a finished scientific study by itself. "
             "**FP-08 (replication, a second cell/seed, D2 continuations and the family-level "
             "inference guide 20 specifies) is required before ANY claim about whether context or "
             "forward-persistent selection helps.** The primary contrast's own estimate/CI/p-value "
             "are reported above verbatim, without a decision-rule label (FP08.5 owns those).",
             "- Owner review: PENDING; FP-08 needs its own R-18 approval per the guide's phase "
             "sequencing, though it may already be covered by the owner's recorded open-ended "
             "auto-advance instruction -- verify against evidence/regime_time_edge_ra_v1/"
             "owner_decisions.jsonl before starting it.", ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, contrasts_doc) -> str:
    return "\n".join([
        f"# FP-07 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        f"- primary contrast (C_FP_CONTEXT - B_FP_PERSISTENCE) status: "
        f"{contrasts_doc['primary']['status']}",
        "- next authorized action: FP-08 (guide section 20, replication/D2/inference) per the "
        "owner's open-ended auto-advance instruction -- MEASURE and DISCLOSE its real compute cost "
        "before running anything.",
        "- FP-08 must reuse: FP-07's own selections/accounts/D1/contrasts machinery wholesale for "
        "a SECOND cell chosen by a pre-registered rule (never by which cell's PnL looks better), "
        "plus D2 age-decline continuations reusing the SAME selected params -- guide 20.",
        "- FP-07 reaches no verdict by design (FP07-G-SCOPE); do not cite its primary contrast as "
        "an edge or a null result on its own.",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp07(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
