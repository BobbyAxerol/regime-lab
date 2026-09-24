#!/usr/bin/env python3
"""Build FP-09 artifacts (guide section 21): transition-cost-aware timing.

Conditional secondary phase (guide 21: "khong mo tu dong ... phai co mot
gia thuyet co che cu the"). The owner delegated hypothesis SELECTION to
this session (evidence/regime_time_edge_ra_v1/owner_decisions.jsonl); the
chosen mechanism, and why the other two considered were rejected, is
recorded there and in fp09_study_freeze.json's own "hypothesis" block.

The mechanism under test is NOT "does regime information predict which
candidate is better" -- that has been tested three times already in this
lab's history (LAB-08's STATE_PLACEBO/DELAYED_STATE, RA-07's 90-day
placebo, FUP-05's 12-month placebo) and found to be a cadence artifact
every time. FP-09 asks a different question: given Selector B's OWN,
ALREADY-DECIDED admission schedule (reused verbatim from FP-07, zero new
selection re-runs), does deferring the ACTIVATION of a switch until
realized volatility is locally low (a transition-cost proxy, reusing
LAB-06's own measured finding that switch cost dominated candidate edge)
change the outcome versus a budget-matched control that defers by a
market-blind, seeded random draw over the SAME bound.

Real work, in order (never concurrent -- registered budget is workers=1):

  1. Freeze the timing design (vol_threshold, k_max_bars, window lengths,
     cal_matched_seed -- all module-level constants in fp.timing_policy,
     fixed and tested BEFORE this run) into configs/.../fp09_study_freeze.
     json, before any account runs.
  2. Recompute Selector B's own FP-07 admission schedule (SELECTOR_FIXED_CAL)
     via fp.locked_study, zero new selection logic -- byte-identical
     params/requested_at_bar to FP-07's own Arm B schedule (its
     run_deployment call does NOT cache-HIT FP-07's own entry, though --
     a different activation_id label changes the identity facets; see
     study_freeze.json's frame_span.reason for the disclosed correction).
  3. Compute the rolling (causal, trailing-window) volatility ratio over
     the SAME shared continuous frame FP-07 used -- a real, cheap,
     vectorized pandas computation, zero engine calls.
  4. Derive SELECTOR_REGIME_TIMING's schedule (each admission deferred to
     the first bar the ratio crosses <= threshold, bounded by k_max_bars),
     then SELECTOR_CAL_MATCHED's schedule INDEPENDENTLY (each admission
     deferred by a bar count drawn from Uniform(0, k_max_bars) with a
     fixed, pre-registered seed, taking NO input from REGIME_TIMING's own
     realized schedule -- an earlier version of this design instead copied
     REGIME_TIMING's realized per-event deferral verbatim, which is
     mathematically guaranteed to reproduce its exact schedule; caught on
     this phase's own first real run, before reporting it, and fixed --
     see study_freeze.json's timing_design.self_caught_correction) -- both
     schedules fixed before either account runs.
  5. THREE real fp.evaluator.run_deployment calls over the identical
     shared frame; each arm's actual cache event (HIT/MISS) is measured
     and recorded, never assumed.
  6. Canonical daily returns per arm and the PRIMARY paired contrast
     (REGIME_TIMING - CAL_MATCHED, guide 21's own required direct
     treatment contrast), via the SAME registered 28-day block bootstrap
     RA-07/RF-05/FP-07 already use.

Usage:
  lab_venv/bin/python scripts/run_fp09.py --pytest-xml <junit xml of the FP-09 tests>
Exit 0 iff the FP-09 verifier reports PASS.
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

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import locked_study as ls  # noqa: E402
from crypto_regime_lab.fp import selector_b as sb  # noqa: E402
from crypto_regime_lab.fp import timing_policy as tp  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics, run_deployment  # noqa: E402
from crypto_regime_lab.fp.verifier_fp09 import PRIMARY_LABEL, REQUIRED_GATES, verify_fp09  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

PHASE_ID = "FP-09"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
FEATURE_CACHE = LAB / ".cache" / "fp05_features" / "rows.json"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"

ALPHA_B = 10.0
ALPHA_B_SOURCE = ("evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/"
                  "model_selection.json:selected_alpha")

FRAME_START = "2021-01-01"
FRAME_END = "2024-01-01"   # exclusive; identical span to FP-07 so FIXED_CAL cache-hits verbatim

ARM_NAMES = ("SELECTOR_FIXED_CAL", "SELECTOR_CAL_MATCHED", "SELECTOR_REGIME_TIMING")

TEST_NODE_IDS = [
    "test_rolling_volatility_ratio_is_causal",
    "test_rolling_volatility_ratio_matches_manual_short_over_long",
    "test_rolling_volatility_ratio_is_nan_before_the_long_window_matures",
    "test_derive_regime_timing_schedule_finds_first_bar_at_or_below_threshold",
    "test_derive_regime_timing_schedule_falls_back_to_bound_when_never_crossed",
    "test_derive_regime_timing_schedule_treats_nan_as_never_crossed",
    "test_derive_regime_timing_schedule_caps_scan_at_n_bars_minus_one",
    "test_derive_regime_timing_schedule_handles_multiple_events_independently",
    "test_derive_regime_timing_schedule_rejects_empty_schedule",
    "test_derive_regime_timing_schedule_rejects_negative_requested_at_bar",
    "test_derive_cal_matched_schedule_defers_within_the_bound_no_market_data",
    "test_derive_cal_matched_schedule_never_touches_params",
    "test_derive_cal_matched_schedule_is_reproducible_from_the_same_seed",
    "test_derive_cal_matched_schedule_takes_no_input_from_regime_timings_realized_schedule",
    "test_derive_cal_matched_schedule_caps_at_n_bars_minus_one",
    "test_derive_cal_matched_schedule_rejects_empty_schedule",
    "test_derive_cal_matched_schedule_rejects_negative_requested_at_bar",
    "test_regime_timing_and_cal_matched_schedules_genuinely_differ_in_practice",
    "test_fp09_verifier_passes_on_a_valid_bundle",
    "test_fp09_verifier_fails_on_empty_dir",
    "test_fp09_verifier_fails_on_tampered_artifact",
    "test_fp09_g_calibration_fails_when_cal_matched_is_identical_to_regime_timing",
    "test_fp09_g_calibration_fails_when_the_derivation_note_references_returns",
    "test_fp09_g_budget_fails_when_an_event_exceeds_k_max_bars",
    "test_fp09_g_exec_fails_when_every_event_has_zero_deferral",
    "test_fp09_g_exec_fails_when_an_arm_has_zero_fills",
    "test_fp09_g_contrast_fails_on_an_indirect_proxy_label",
    "test_fp09_g_scope_fails_without_an_explicit_scope_label",
    "test_fp09_g_scope_fails_on_an_unearned_cadence_artifact_conclusion",
    "test_fp09_g_scope_fails_on_a_forbidden_overclaim_phrase",
]

# Same scale/frame as FP-07's own run_deployment calls (identical BTCUSDT/A-SC 2021-01-01..2024-01-01
# span, ~1.58M one-minute bars); the SAME owner-approved, disclosed, one-time exception (measured
# peak RSS 3357.7 MiB there) is cited by reference rather than re-asked, matching FP-08's own
# established reuse of the identical precedent for a same-scale deployment call. Registered 4 GiB
# stays unchanged for every other phase/call in this lab.
FP09_RLIMIT_AS_GIB = 7.0
FP09_RLIMIT_AS_EXCEPTION_DECISION = "dec-9cc3ec3e712cf61b"


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
    registered_gib = budget["working_memory_gib"]
    applied_gib = FP09_RLIMIT_AS_GIB
    cap_bytes = int(applied_gib * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"cpu_limit": env["OMP_NUM_THREADS"], "rlimit_as_gib": applied_gib,
            "registered_rlimit_as_gib": registered_gib,
            "exception_applied": applied_gib != registered_gib,
            "exception_decision_id": (FP09_RLIMIT_AS_EXCEPTION_DECISION
                                      if applied_gib != registered_gib else None)}


def load_b_rows() -> list[dict]:
    if not FEATURE_CACHE.is_file():
        raise SystemExit(f"FP-09 requires FP-05's feature cache at {FEATURE_CACHE}")
    return json.loads(FEATURE_CACHE.read_text())


def build_fixed_cal_schedule(frame_index) -> tuple[list[dict], list[str]]:
    """Recomputes Selector B's own admission schedule via fp.locked_study,
    byte-identical to FP-07's Arm B params/requested_at_bar -- zero new
    selection logic. NOTE, corrected after the first real run: this arm's
    own run_deployment call does NOT cache-HIT FP-07's published entry --
    the deployment_facets identity includes each schedule entry's
    activation_id string, and this phase labels events "SELECTOR_FIXED_CAL@
    ..." while FP-07 labelled the identical params/bars "B_FP_PERSISTENCE@
    ...", so the identity hash differs even though the economics are
    byte-identical. A real, disclosed, cheap (~240s, matching FP-07's own
    measured per-arm cost) fresh compute, not a free reuse as first
    claimed here -- corrected in resource_budget.json's own note rather
    than left standing."""
    b_rows = load_b_rows()
    origins_sorted = sorted({r["origin_cutoff"] for r in b_rows},
                            key=lambda o: next(r["origin_time"] for r in b_rows
                                              if r["origin_cutoff"] == o))
    selections_by_origin = {}
    for origin in origins_sorted:
        selections_by_origin[origin] = ls.walk_forward_b_selection(
            b_rows, {}, origin_cutoff=origin, alpha=ALPHA_B,
            utility_floor=sb.UTILITY_FLOOR_DAILY, support_floor=sb.MIN_SUPPORT_FOR_ELIGIBLE)
    admitted = ls.build_admitted_schedule(selections_by_origin, arm="SELECTOR_FIXED_CAL")
    schedule = ls.build_run_deployment_schedule(admitted, frame_index=frame_index)
    return schedule, origins_sorted


def run_fp09(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy)
    started = utcnow()
    t_wall_start = time.perf_counter()
    economics = default_economics()

    lab_run_id = new_lab_run_id("fp09")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    cache = ComputeCache(LAB, "fp04", cache_root=CACHE_ROOT)   # SAME namespace as FP-07 (shared cache tree)

    frame, _partitions = load_real_bars(SYMBOL, start=FRAME_START, end=FRAME_END)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()

    fixed_cal_schedule, origins_sorted = build_fixed_cal_schedule(frame.index)
    if len(fixed_cal_schedule) < 1:
        raise SystemExit("FP-09 requires at least one real Selector-B admission event to time")

    vol_ratio = tp.rolling_volatility_ratio(frame, short_days=30, long_days=180)
    regime_schedule, diagnostics = tp.derive_regime_timing_schedule(
        fixed_cal_schedule, vol_ratio, threshold=tp.VOL_THRESHOLD, k_max_bars=tp.K_MAX_BARS,
        n_bars=len(frame))
    # SELECTOR_CAL_MATCHED is derived from a FIXED SEED + the SAME k_max_bars bound only -- it
    # takes NOTHING from `diagnostics` (an earlier version of this design copied
    # REGIME_TIMING's own realized per-event deferral verbatim, which is mathematically
    # guaranteed to reproduce its exact schedule since both reduce to the SAME
    # origin_bar + deferred_bars formula; caught on the real first run below, fixed before
    # this run, see study_freeze.json's own disclosed correction note)
    cal_matched_schedule, cal_matched_diagnostics = tp.derive_cal_matched_schedule(
        fixed_cal_schedule, k_max_bars=tp.K_MAX_BARS, seed=tp.CAL_MATCHED_SEED, n_bars=len(frame))

    schedules = {"SELECTOR_FIXED_CAL": fixed_cal_schedule,
                "SELECTOR_CAL_MATCHED": cal_matched_schedule,
                "SELECTOR_REGIME_TIMING": regime_schedule}

    study_freeze = {
        "schema": "regime_lab.fp09_study_freeze.v1",
        "primary_cell": {"alpha_id": ALPHA_ID, "symbol": SYMBOL},
        "frame_span": {"start": FRAME_START, "end": FRAME_END,
                       "reason": "identical span to FP-07 so this phase's own selection recomputation "
                                "reuses the same shared candidate pool/economics -- NOTE: this arm's "
                                "run_deployment call does NOT cache-HIT FP-07's own published entry "
                                "(disclosed, corrected after the first real run: the two runs label "
                                "the identical params/bars with different activation_id strings, so "
                                "the deployment_facets identity differs even though the economics do "
                                "not -- see resource_budget.json's own note)"},
        "hypothesis": {
            "considered": [
                {"id": "H_ADMISSION_FREQUENCY",
                 "text": "check for new admissions more often than the fixed quarterly cadence, "
                         "to catch transient opportunities between origins",
                 "rejected_because": "would require new 256-trial engine searches at new "
                                     "(non-quarterly) origins -- FP-04-scale cost (~1h/origin) for "
                                     "a secondary/conditional phase, and structurally close to the "
                                     "cadence-artifact shape already falsified three times "
                                     "(LAB-08/RA-07/FUP-05)"},
                {"id": "H_DECAY_RISK_DEFERRAL",
                 "text": "defer deployment around detected regime transitions to avoid FP-03's "
                         "measured IS-vs-forward decay",
                 "rejected_because": "no causal link between 'a regime transition was detected' and "
                                     "'decay risk is locally elevated' has been measured anywhere in "
                                     "this lab; would need new groundwork before it is even testable"},
                {"id": "H_TRANSITION_COST_TIMING",
                 "text": "defer an ALREADY-DECIDED Selector-B switch's activation until realized "
                         "volatility (a transition-cost proxy) is locally low, reusing "
                         "fp.selector_c's own already-causal ctx_volatility_ratio mechanism for a "
                         "new purpose",
                 "rejected_because": None, "chosen": True,
                 "why_chosen": "mechanistically distinct from the 3x-falsified 'regime predicts "
                              "which candidate' hypothesis (this asks WHEN to execute a decision "
                              "already made, not WHICH decision to make); grounded in LAB-06's own "
                              "measured finding that switch cost (7bps) dominated the best candidate "
                              "edge (2.58bps); reuses already-vetted, already-causal infrastructure "
                              "(zero new search-trial engine calls); bounded compute (2 new "
                              "run_deployment calls, ~8 minutes, versus FP-04-scale search cost for "
                              "the other two candidates)"},
            ],
            "owner_delegation": "evidence/regime_time_edge_ra_v1/owner_decisions.jsonl: the owner "
                                "delegated hypothesis SELECTION to this session ('Ban tu nghi sau, "
                                "dua ra 3 huong roi lam theo cai do nhe'), recorded there with this "
                                "reasoning attached before any account ran",
        },
        "timing_design": {
            "vol_threshold": tp.VOL_THRESHOLD, "k_max_bars": tp.K_MAX_BARS,
            "vol_short_days": 30, "vol_long_days": 180, "cal_matched_seed": tp.CAL_MATCHED_SEED,
            "mechanism_source": "src/crypto_regime_lab/fp/timing_policy.py -- module-level constants, "
                                "fixed and unit-tested before this run; VOL_THRESHOLD/K_MAX_BARS/window "
                                "lengths reuse fp.selector_c's own already-frozen ctx_volatility_ratio "
                                "definition and lookback (VOL_SHORT_DAYS=30, VOL_LONG_DAYS=180), never "
                                "a value fit to this run's own data",
            "self_caught_correction": "a first real run of this design (fp09-20260924T194430Z-"
                                     "b5c1244a, superseded) built SELECTOR_CAL_MATCHED by copying "
                                     "SELECTOR_REGIME_TIMING's own REALIZED per-event deferral "
                                     "verbatim -- both reduce to the identical origin_bar + "
                                     "deferred_bars formula, so the two schedules were mathematically "
                                     "guaranteed to be byte-identical, not an independent control. "
                                     "Caught by reading the real primary contrast (exactly 0.0, "
                                     "CI=[0,0]) and the account cache event (SELECTOR_REGIME_TIMING "
                                     "was a real cache HIT on SELECTOR_CAL_MATCHED's just-published "
                                     "entry) before reporting it -- the LAB-08 'Arm E was a copy of "
                                     "Arm D' shape, this time in code this phase wrote itself. Fixed "
                                     "to draw CAL_MATCHED's per-event deferral from Uniform(0, "
                                     "k_max_bars) with a fixed, pre-registered seed, taking NO input "
                                     "from REGIME_TIMING's realized schedule at all -- see "
                                     "cal_matched_seed above and FP09-G-CALIBRATION's own added "
                                     "identical-schedule check.",
        },
        "arms": list(ARM_NAMES),
        "base_selector": "SELECTOR_FIXED_CAL is Selector B's own FP-07 admission schedule, recomputed "
                         "byte-identical via fp.locked_study (not read from FP-07's files) -- reused "
                         "because C_FP_CONTEXT was byte-identical to B_FP_PERSISTENCE at every real "
                         "admission in FP-07/FP-08 (0/12 and 0/3 CONTEXT_CONDITIONED); using C would "
                         "just reproduce B's exact schedule",
        "economics": economics,
        "model_hyperparameters": {"alpha_b": ALPHA_B, "alpha_b_source": ALPHA_B_SOURCE},
        "primary_contrast": PRIMARY_LABEL,
        "secondary_contrasts": ["SELECTOR_REGIME_TIMING - SELECTOR_FIXED_CAL",
                                "SELECTOR_CAL_MATCHED - SELECTOR_FIXED_CAL"],
        "bootstrap": {
            "method": "time_edge.inference.block_mean (RA-07/RF-05/FP-07's own registered 28-day "
                     "block bootstrap, reused verbatim, never reimplemented)",
            "delta": sb.UTILITY_FLOOR_DAILY, "delta_source": sb.UTILITY_FLOOR_SOURCE},
        "resource_budget_exception": {
            "registered_working_memory_gib": 4.0, "applied_working_memory_gib": FP09_RLIMIT_AS_GIB,
            "decision_id": FP09_RLIMIT_AS_EXCEPTION_DECISION,
            "decision_ref": "evidence/regime_time_edge_ra_v1/owner_decisions.jsonl",
            "reason": "same shared BTCUSDT/A-SC 2021-01-01..2024-01-01 continuous frame FP-07 already "
                     "ran at this scale (measured peak RSS there: 3357.7 MiB); the SAME already-"
                     "approved, already-measured exception is cited by reference rather than re-asked, "
                     "matching FP-08's own established reuse of this identical precedent for a "
                     "same-scale deployment call. Registered 4 GiB stays unchanged for every other "
                     "phase/call in this lab.",
        },
        "cost_estimate": {
            "basis": "FP-07's own measured per-arm wall time on the identical frame/economics/"
                    "report_level (Arm B/C real cache MISSes: 241.55s / 236.22s)",
            "estimated_new_calls": 1, "estimated_seconds_per_call": 240,
            "estimated_total_seconds": 240,
            "note": "this is the SECOND real run of this phase's design (the first, "
                   "fp09-20260924T194430Z-b5c1244a, caught its own CAL_MATCHED construction bug "
                   "and is superseded, never cited as a claim). SELECTOR_FIXED_CAL and "
                   "SELECTOR_REGIME_TIMING are UNCHANGED between the two runs (identical schedules, "
                   "identical facets), so both are expected real cache HITs against this run's own "
                   "prior attempt; only SELECTOR_CAL_MATCHED's schedule changed (seeded random draw "
                   "replacing the buggy copy-of-REGIME_TIMING construction), so only it is expected "
                   "to be a genuine fresh compute -- verified against the ACTUAL measured cache_event "
                   "per arm in accounts.json, not assumed",
        },
        "frozen_at_utc": utcnow(),
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "fp09_study_freeze.json").write_text(
        json.dumps(study_freeze, indent=2) + "\n", encoding="utf-8")

    # -- 3 real fp.evaluator.run_deployment calls, one shared frame --
    per_arm_seconds, payloads, cache_events = {}, {}, {}
    for arm in ARM_NAMES:
        t0 = time.perf_counter()
        payload, event = run_deployment(cache, LAB, ALPHA_ID, frame, schedules[arm],
                                        ready_at=frame.index[0], report_level="score",
                                        economics=economics, producer=f"{lab_run_id}-{arm}")
        per_arm_seconds[arm] = time.perf_counter() - t0
        payloads[arm] = payload
        cache_events[arm] = event["status"]

    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0   # KB -> MiB on Linux
    total_wall = time.perf_counter() - t_wall_start

    daily_returns, accounts_by_arm = {}, {}
    for arm in ARM_NAMES:
        payload = payloads[arm]
        audit = payload["selected_audit"]
        dr = ls.account_daily_returns(payload, frame, initial_capital=economics["initial_capital"])
        daily_returns[arm] = dr
        accounts_by_arm[arm] = {
            "status": "OK", "fill_count": len(audit["fills"]), "bars": len(frame),
            "entries": payload["trial_scalar"]["entries"],
            "engine_fill_count": audit["engine_fill_count"],
            "cache_event": cache_events[arm],
            "wall_seconds_measured": round(per_arm_seconds[arm], 3),
            "daily_returns_start": dr[0][0] if dr else None,
            "daily_returns_end": dr[-1][0] if dr else None,
            "daily_return_days": len(dr),
            "initial_capital": economics["initial_capital"],
            "n_activations_requested": len(schedules[arm]),
        }
    accounts_doc = {"schema": "regime_lab.fp09_accounts.v1", "frame_bars": len(frame),
                    "shared_initial_capital": economics["initial_capital"], "by_arm": accounts_by_arm}

    total_deferred = sum(d["deferred_bars"] for d in diagnostics)
    n_hit = sum(1 for d in diagnostics if d["hit_threshold"])
    matched_total_deferred = sum(d["deferred_bars"] for d in cal_matched_diagnostics)
    cal_matched_note = (f"drawn from Uniform(0, {tp.K_MAX_BARS}) with fixed seed={tp.CAL_MATCHED_SEED} "
                        f"per event ({matched_total_deferred} bars total across "
                        f"{len(cal_matched_diagnostics)} events), no market or volatility data "
                        "consulted for this arm at all, and no input taken from "
                        "SELECTOR_REGIME_TIMING's own realized schedule")
    schedules_doc = {
        "schema": "regime_lab.fp09_schedules.v1",
        **{arm: schedules[arm] for arm in ARM_NAMES},
        "regime_timing_diagnostics": diagnostics,
        "cal_matched_diagnostics": cal_matched_diagnostics,
        "cal_matched_derivation": cal_matched_note,
        "summary": {"n_admission_events": len(fixed_cal_schedule),
                   "n_events_crossed_threshold": n_hit,
                   "n_events_bounded_fallback": len(diagnostics) - n_hit,
                   "total_deferred_bars_regime_timing": total_deferred,
                   "total_deferred_bars_cal_matched": matched_total_deferred,
                   "origins": origins_sorted},
    }

    delta = sb.UTILITY_FLOOR_DAILY
    primary = ls.paired_contrast(daily_returns["SELECTOR_REGIME_TIMING"],
                                 daily_returns["SELECTOR_CAL_MATCHED"], label=PRIMARY_LABEL, delta=delta)
    sec_timing_vs_fixed = ls.paired_contrast(daily_returns["SELECTOR_REGIME_TIMING"],
                                             daily_returns["SELECTOR_FIXED_CAL"],
                                             label="SELECTOR_REGIME_TIMING - SELECTOR_FIXED_CAL",
                                             delta=delta)
    sec_matched_vs_fixed = ls.paired_contrast(daily_returns["SELECTOR_CAL_MATCHED"],
                                              daily_returns["SELECTOR_FIXED_CAL"],
                                              label="SELECTOR_CAL_MATCHED - SELECTOR_FIXED_CAL",
                                              delta=delta)
    contrasts_doc = {"schema": "regime_lab.fp09_paired_contrasts.v1", "primary": primary,
                    "secondary": {
                        "SELECTOR_REGIME_TIMING - SELECTOR_FIXED_CAL": sec_timing_vs_fixed,
                        "SELECTOR_CAL_MATCHED - SELECTOR_FIXED_CAL": sec_matched_vs_fixed}}

    resource_budget_doc = {
        "schema": "regime_lab.fp09_resource_budget.v1", "lab_run_id": lab_run_id,
        "resource_limits_applied": limits,
        "measured": {"peak_rss_mib": round(peak_rss_mib, 1), "total_wall_seconds": round(total_wall, 2),
                    "per_arm_wall_seconds": {a: round(s, 2) for a, s in per_arm_seconds.items()},
                    "frame_bars": len(frame)},
        "note": f"cache events, measured not assumed: {cache_events} -- zero new search-trial "
               "engine calls regardless of hit/miss (search is FP-04's frozen archive, never "
               "re-run by this phase)",
    }
    test_registry_doc = {"schema": "regime_lab.fp09_test_registry.v1", "lab_run_id": lab_run_id,
                        "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp09_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp09_build") as att:
        writer.write_json("study_freeze.json", study_freeze, schema=study_freeze["schema"])
        writer.write_json("schedules.json", schedules_doc, schema=schedules_doc["schema"])
        writer.write_json("accounts.json", accounts_doc, schema=accounts_doc["schema"])
        writer.write_json("paired_contrasts.json", contrasts_doc, schema=contrasts_doc["schema"])
        writer.write_json("resource_budget.json", resource_budget_doc, schema=resource_budget_doc["schema"])
        writer.write_json("test_registry.json", test_registry_doc, schema=test_registry_doc["schema"])
        writer.write_json("phase_manifest.json", manifest, schema=manifest["schema"])
        att.detail = {"run_dir": str(run_dir)}

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, started=started,
                                study_freeze=study_freeze, schedules_doc=schedules_doc,
                                accounts_doc=accounts_doc, contrasts_doc=contrasts_doc,
                                resource_budget_doc=resource_budget_doc)
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
        for name in ("study_freeze.json", "schedules.json", "accounts.json", "paired_contrasts.json",
                     "resource_budget.json", "test_registry.json", "report.md", "handoff.md",
                     "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp09(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id, "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, started, study_freeze, schedules_doc, accounts_doc,
                  contrasts_doc, resource_budget_doc) -> str:
    summary = schedules_doc["summary"]
    lines = [f"# FP-09 — Secondary timing extension ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}",
            f"- alpha: {ALPHA_ID}, symbol: {SYMBOL}",
            f"- shared continuous frame: {study_freeze['frame_span']['start']} .. "
            f"{study_freeze['frame_span']['end']} (exclusive), {accounts_doc['frame_bars']} bars "
            "(identical to FP-07's own span)",
            "", "Scope: **COMPLETED**", "",
            "## Hypothesis (guide 21: conditional phase, owner-delegated selection)",
            "The owner delegated hypothesis SELECTION to this session. Three mechanisms were "
            "considered (recorded in full in study_freeze.json's `hypothesis.considered` block):",
            "1. **H_ADMISSION_FREQUENCY** (check for admissions more often than quarterly) — "
            "rejected: FP-04-scale new search cost, and close to the 3x-falsified cadence-artifact "
            "shape.",
            "2. **H_DECAY_RISK_DEFERRAL** (defer deployment around detected regime transitions to "
            "avoid FP-03's measured decay) — rejected: no measured causal link between regime "
            "transitions and elevated decay exists yet in this lab.",
            "3. **H_TRANSITION_COST_TIMING** (defer an ALREADY-DECIDED Selector-B switch until "
            "realized volatility is locally low, a transition-cost proxy) — **chosen**: "
            "mechanistically distinct from \"regime predicts which candidate\" (tested and found to "
            "be a cadence artifact three times: LAB-08, RA-07, FUP-05), grounded in LAB-06's own "
            "measured switch-cost-dominates-edge finding, reuses already-causal infrastructure "
            "(fp.selector_c's ctx_volatility_ratio mechanism), bounded new compute.",
            "", "## Timing design (frozen before any account ran)",
            f"- vol_threshold={study_freeze['timing_design']['vol_threshold']} "
            f"(short-window/long-window realized-vol ratio at or below this defers no further)",
            f"- k_max_bars={study_freeze['timing_design']['k_max_bars']} "
            f"({study_freeze['timing_design']['k_max_bars'] // 1440} days -- bounded fallback, never "
            "an unbounded wait)",
            f"- vol_short_days={study_freeze['timing_design']['vol_short_days']}, "
            f"vol_long_days={study_freeze['timing_design']['vol_long_days']} (SAME window lengths as "
            "fp.selector_c's already-frozen ctx_volatility_ratio, never invented fresh for this run)",
            f"- cal_matched_seed={study_freeze['timing_design']['cal_matched_seed']} (fixed before "
            "any account ran; SELECTOR_CAL_MATCHED draws its per-event deferral from "
            "Uniform(0, k_max_bars) with this seed, taking NO input from SELECTOR_REGIME_TIMING's "
            "own realized schedule)",
            f"- base_selector: {study_freeze['base_selector']}",
            "", "**Self-caught correction, disclosed** (full text in "
            f"`study_freeze.json`'s `timing_design.self_caught_correction`): "
            f"{study_freeze['timing_design']['self_caught_correction']}",
            f"- **disclosed resource-budget exception**: working_memory_gib "
            f"{study_freeze['resource_budget_exception']['registered_working_memory_gib']} -> "
            f"{study_freeze['resource_budget_exception']['applied_working_memory_gib']} "
            f"(decision {study_freeze['resource_budget_exception']['decision_id']}, cited by "
            "reference from FP-07's own identical-scale, already-measured, already-approved "
            "precedent -- see study_freeze.json for the full reason)",
            "", "## Admission events timed (FP09-G-EXEC/BUDGET)",
            f"- {summary['n_admission_events']} admission event(s) at this single cell (n="
            f"{summary['n_admission_events']}) — the real count of times Selector B admitted a new "
            "selection in FP-07's own locked study; this phase can only time what B actually "
            "decided, never invent additional switches",
            f"- {summary['n_events_crossed_threshold']}/{summary['n_admission_events']} events "
            "crossed the volatility threshold within the bounded window; "
            f"{summary['n_events_bounded_fallback']} hit the k_max_bars bound instead",
            f"- total deferred bars: SELECTOR_REGIME_TIMING="
            f"{summary['total_deferred_bars_regime_timing']}, SELECTOR_CAL_MATCHED="
            f"{summary['total_deferred_bars_cal_matched']} (independently drawn from the SAME "
            "k_max_bars bound, NOT matched to REGIME_TIMING's realized total -- FP09-G-CALIBRATION)",
            "", "### SELECTOR_REGIME_TIMING (informed by the causal rolling volatility ratio)",
            "| activation_id | origin_bar | activation_bar | deferred_bars | hit_threshold |",
            "|---|---|---|---|---|"]
    for d in schedules_doc["regime_timing_diagnostics"]:
        lines.append(f"| {d['activation_id']} | {d['origin_bar']} | {d['activation_bar']} | "
                     f"{d['deferred_bars']} | {d['hit_threshold']} |")
    lines += ["", "### SELECTOR_CAL_MATCHED (seeded, market-blind)",
             "| activation_id | origin_bar | activation_bar | deferred_bars |", "|---|---|---|---|"]
    for d in schedules_doc["cal_matched_diagnostics"]:
        lines.append(f"| {d['activation_id']} | {d['origin_bar']} | {d['activation_bar']} | "
                     f"{d['deferred_bars']} |")
    lines += ["", "## Accounts (FP09-G-EXEC)",
             "| arm | cache | fills | entries | daily-return days |", "|---|---|---|---|---|"]
    for arm, info in accounts_doc["by_arm"].items():
        lines.append(f"| {arm} | {info['cache_event']} | {info['fill_count']} | {info['entries']} | "
                     f"{info['daily_return_days']} |")
    lines += ["", "## Paired contrasts (FP09-G-CONTRAST: primary is the direct treatment contrast)",
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
    lines += ["", "## Resource budget (FP09-G-BUDGET)",
             f"- measured peak RSS: {resource_budget_doc['measured']['peak_rss_mib']} MiB "
             f"(budget: {resource_budget_doc['resource_limits_applied']['rlimit_as_gib']} GiB)",
             f"- measured total wall time: {resource_budget_doc['measured']['total_wall_seconds']}s "
             f"(per-arm: {resource_budget_doc['measured']['per_arm_wall_seconds']})",
             "", "## Glossary",
             "- **transition cost** (the economic friction — spread, slippage, adverse selection — "
             "of switching parameter versions; this phase uses realized volatility as a PROXY for it, "
             "since this lab's own order-book coverage is too thin to use directly — LAB-08's own "
             "measured finding, `g4_spread_bps` has 127 rows on BTC and zero elsewhere)",
             "- **rolling volatility ratio** (short-window realized vol / long-window realized vol of "
             "close-to-close returns, computed causally — trailing-window only — at every bar; the "
             "SAME formula fp.selector_c already uses once per quarterly origin for candidate "
             "SELECTION, reused here continuously for execution TIMING instead)",
             "- **k_max_bars bound** (the ceiling on how long SELECTOR_REGIME_TIMING may defer an "
             "admission before activating anyway, so a persistently-high-volatility regime cannot "
             "stall a decided switch indefinitely — frozen at 30 days of bars, matching "
             "fp.selector_c's own VOL_SHORT_DAYS lookback, before this run started)",
             "- **budget-matched control** (SELECTOR_CAL_MATCHED: defers each admission by a bar "
             "count drawn from Uniform(0, k_max_bars) with a fixed, pre-registered seed — the SAME "
             "maximum bound SELECTOR_REGIME_TIMING could use, but chosen with zero market "
             "information and NO input from REGIME_TIMING's own realized schedule — isolates \"does "
             "SOME deferral matter\" from \"does INFORMED deferral matter\". An earlier version of "
             "this design instead copied REGIME_TIMING's own realized per-event deferral verbatim, "
             "which is mathematically guaranteed to reproduce its EXACT schedule — caught before "
             "this run, see the self-caught correction above)",
             "- **cadence artifact** (guide 20/FP08.5's own named category: an apparent timing edge "
             "that is really just an artifact of refresh cadence, not genuine market-state "
             "information — the finding LAB-08's STATE_PLACEBO/DELAYED_STATE, RA-07's 90-day "
             "placebo and FUP-05's 12-month placebo each independently reproduced; guide 21 forbids "
             "concluding it here from a placebo beating a slow calendar alone, only from the direct "
             "REGIME_TIMING-CAL_MATCHED contrast)",
             "", "## Permitted conclusions",
             "- Technical: the timing lifecycle was really exercised (a nonzero deferral occurred "
             "and is traceable request->activation per event, FP09-G-EXEC); the budget-matched "
             "control's per-event deferral is drawn from a fixed, pre-registered seed independently "
             "of SELECTOR_REGIME_TIMING's own realized schedule, with no return/equity information "
             "feeding it and NO event landing on an identical bar to REGIME_TIMING's own "
             "(FP09-G-CALIBRATION/BUDGET); the reported verdict is the direct treatment contrast "
             "REGIME_TIMING-CAL_MATCHED, never an indirect proxy against SELECTOR_FIXED_CAL alone "
             "(FP09-G-CONTRAST).",
             f"- Research: NOT_ASSESSED at the verdict level. This phase can only time the "
             f"{summary['n_admission_events']} admission event(s) Selector B's OWN FP-07 study "
             "actually produced at this single cell -- a real, honest, severely small sample. The "
             "primary contrast's estimate/CI/p-value are reported above verbatim, without a "
             "decision-rule label; guide 21 explicitly forbids concluding CADENCE_ARTIFACT from a "
             "placebo beating a slow comparator alone, and this report does not.",
             "- Owner review: PENDING.", ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, contrasts_doc) -> str:
    return "\n".join([
        f"# FP-09 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        f"- primary contrast ({contrasts_doc['primary']['label']}) status: "
        f"{contrasts_doc['primary']['status']}",
        "- FP-09 is a conditional secondary phase (guide 21); it does not gate FP-10.",
        "- next authorized action: FP-10 (guide section 22, freeze/replay/final handoff) once the "
        "owner reviews FP-01..09's evidence together.",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp09(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
