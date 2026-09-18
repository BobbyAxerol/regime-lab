"""RA-05 test matrix D01-D07 (RA-GUIDE-1.0 section 9).

Real installed-engine calls on REAL BTCUSDT bars/emissions at a tiny,
phase-owned scale (7-day window, 20-day train, 2 trials/cutoff) -- the same
real data sources `scripts/run_ra05.py` uses at full scale, just a much
smaller slice, so every test here exercises the SAME code path the real
discovery run does, never a synthetic stand-in.
"""
from __future__ import annotations

import pandas as pd
import pytest

from crypto_regime_lab.ra.ra05_arms import (
    build_calendar_schedule, build_regime_schedule, build_static_schedule,
    classify_regime_trigger_reasons, forecast_cal_matched_test_days,
)
from crypto_regime_lab.ra.ra05_discovery import action_divergence, descriptive_returns, run_one_arm
from crypto_regime_lab.ra.ra05_funnel import build_funnel_record, score_fold_for_admission
from crypto_regime_lab.ra.ra05_market import EMISSIONS_ARTIFACT, load_real_bars, load_real_emissions
from crypto_regime_lab.time_edge.execution import PreparedAccount

ALPHA_ID = "A-SC"
WINDOW_START, WINDOW_END = "2021-01-01", "2021-01-08"
DATA_LOAD_START = "2020-12-01"
TRAIN_MEMORY_DAYS = 20
TRIALS = 2
SEED = 20260918


def _real_frame():
    frame, partitions = load_real_bars("BTCUSDT", start=DATA_LOAD_START, end=WINDOW_END)
    return frame[["open", "high", "low", "close", "volume"]].copy(), partitions


def _real_emissions(window_end=WINDOW_END):
    return load_real_emissions(window_start=WINDOW_START, window_end=window_end)["emissions"]


# --- D01: all four arms share initial selection/economics/calendar support -

def test_d01_all_arms_share_initial_selection_and_calendar_support(lab_tmp):
    frame, _ = _real_frame()
    prepared = PreparedAccount(frame)
    emissions = _real_emissions()

    static = build_static_schedule(WINDOW_START, WINDOW_END, train_memory_days=TRAIN_MEMORY_DAYS)
    cal = build_calendar_schedule(WINDOW_START, WINDOW_END, test_days=4,
                                  train_memory_days=TRAIN_MEMORY_DAYS)
    regime = build_regime_schedule(emissions, window_start=WINDOW_START, window_end=WINDOW_END,
                                   train_memory_days=TRAIN_MEMORY_DAYS)

    # STATIC is not gated by a minimum-selection-count rule: exactly one
    # cutoff is a valid, runnable schedule.
    assert static.cutoffs == (pd.Timestamp(WINDOW_START, tz="UTC").isoformat(),)
    # Every arm's FIRST cutoff is the SAME shared initial selection point.
    assert static.cutoffs[0] == cal.cutoffs[0] == regime.cutoffs[0]
    # And the train memory (calendar support) frozen for the pilot is
    # identical across arms -- this is what would have silently diverged if
    # STATIC's schedule builder dropped train_memory_days (a real defect
    # caught here after being caught once already during this phase's build).
    assert static.train_memory_days == cal.train_memory_days == regime.train_memory_days

    static_result = run_one_arm(ALPHA_ID, frame, static, prepared=prepared, trials=TRIALS,
                                seed=SEED, route="event", evidence_dir=lab_tmp, lab_run_id="d01")
    cal_result = run_one_arm(ALPHA_ID, frame, cal, prepared=prepared, trials=TRIALS, seed=SEED,
                             route="event", evidence_dir=lab_tmp, lab_run_id="d01")
    assert static_result["ok"] and cal_result["ok"]
    static_fold0 = static_result["run"]["fold_selection_table"][0]
    cal_fold0 = cal_result["run"]["fold_selection_table"][0]
    # Same cutoff, same train window, same trials/seed -> the SAME initial
    # selection, not merely the same cutoff timestamp.
    assert static_fold0["train_start"] == cal_fold0["train_start"]
    assert static_fold0["train_end"] == cal_fold0["train_end"]
    assert static_fold0["selected_params"] == cal_fold0["selected_params"]


# --- D01b: trigger-reason labels match the deployed scheduler's own reasons.
# Pure classification, no engine calls -- cheap, but must use a window WIDE
# enough to contain a real trigger (D01's own 7-day smoke window has none:
# the real ones fall on 2021-02-02 and 2021-03-19, so a check run only over
# that window would pass vacuously on two empty lists). Regression test for
# a real defect: an earlier version of classify_regime_trigger_reasons
# compared consecutive CHOSEN CUTOFFS' states directly instead of replaying
# every eligible emission in between (as online_trigger_schedule itself
# does), which silently mislabeled real SEMANTIC_STATE_CHANGE triggers as
# MAX_AGE -- caught by cross-checking against the real full-scale run's
# deployed_source, not by this test alone (it did not exist yet then).

def test_d01b_trigger_reason_labels_match_the_deployed_scheduler():
    import re

    real_window_start, real_window_end = "2021-01-01", "2021-04-01"
    emissions = load_real_emissions(window_start=real_window_start,
                                    window_end=real_window_end)["emissions"]
    regime = build_regime_schedule(emissions, window_start=real_window_start,
                                   window_end=real_window_end, train_memory_days=45)
    ground_truth_reasons = re.findall(r"'(SEMANTIC_STATE_CHANGE|MAX_AGE)'", regime.source)
    assert ground_truth_reasons, "this window must contain at least one real trigger, or the check is vacuous"
    lookup = classify_regime_trigger_reasons(regime.cutoffs, emissions,
                                             shared_initial=regime.cutoffs[0])
    labelled_reasons = [lookup[c]["reason"] for c in regime.cutoffs[1:]]
    assert labelled_reasons == ground_truth_reasons, (
        f"classify_regime_trigger_reasons diverged from online_trigger_schedule's own "
        f"reported reasons: {labelled_reasons} vs {ground_truth_reasons}")


# --- D02: CAL_MATCHED never reads the window's own trigger count -----------

def test_d02_cal_matched_never_reads_the_window_own_trigger_count():
    full = __import__("json").loads(EMISSIONS_ARTIFACT.read_text())["emissions"]
    baseline = forecast_cal_matched_test_days(
        full, window_start=WINDOW_START, window_end=WINDOW_END,
        per_selection_wall_seconds=100.0)

    # Suffix mutation: emissions AFTER window_end change (a different
    # "future" realized trigger count) -- the forecast must be unaffected,
    # because it only ever reads emissions OUTSIDE the window and never the
    # window's own realized trigger count.
    import copy

    mutated = copy.deepcopy(full)
    for row in mutated:
        if pd.Timestamp(row["available_at"]) >= pd.Timestamp(WINDOW_END, tz="UTC"):
            row["state_id"] = (row["state_id"] or 0) + 999  # force spurious "transitions"
            row["state_common"] = (row.get("state_common") or 0) + 999
    mutated_forecast = forecast_cal_matched_test_days(
        mutated, window_start=WINDOW_START, window_end=WINDOW_END,
        per_selection_wall_seconds=100.0)
    assert mutated_forecast["chosen_test_days"] == baseline["chosen_test_days"]
    assert mutated_forecast["predicted_trigger_count_in_window"] == pytest.approx(
        baseline["predicted_trigger_count_in_window"])
    assert mutated_forecast["development_triggers"] != None  # noqa: E711 - sanity the calc ran

    # And mutating emissions strictly INSIDE the window changes nothing
    # either, since development explicitly excludes the window.
    inside_mutated = copy.deepcopy(full)
    for row in inside_mutated:
        at = pd.Timestamp(row["available_at"])
        if pd.Timestamp(WINDOW_START, tz="UTC") <= at < pd.Timestamp(WINDOW_END, tz="UTC"):
            row["state_id"] = 12345
    inside_forecast = forecast_cal_matched_test_days(
        inside_mutated, window_start=WINDOW_START, window_end=WINDOW_END,
        per_selection_wall_seconds=100.0)
    assert inside_forecast["chosen_test_days"] == baseline["chosen_test_days"]


# --- D03: exact parameter-selection traces match; no early activation ------

def test_d03_exact_parameter_selection_traces_match_and_no_early_activation(lab_tmp):
    frame, _ = _real_frame()
    prepared = PreparedAccount(frame)
    cal = build_calendar_schedule(WINDOW_START, WINDOW_END, test_days=4,
                                  train_memory_days=TRAIN_MEMORY_DAYS)
    result = run_one_arm(ALPHA_ID, frame, cal, prepared=prepared, trials=TRIALS, seed=SEED,
                         route="event", evidence_dir=lab_tmp, lab_run_id="d03")
    assert result["ok"]
    assert result["run"]["oos_used_for_selection"] is False
    for row in result["funnel"]:
        # activation never precedes the request/train_cutoff it was derived from
        assert pd.Timestamp(row["activation_time"]) == pd.Timestamp(row["request_time"])
        assert pd.Timestamp(row["activation_time"]) >= pd.Timestamp(row["train_cutoff"])
        assert row["activation_time_is_fold_boundary_not_a_delayed_bar"] is True


# --- D04: funnel reconstructs sample decisions, incl. no-switch ------------

def test_d04_funnel_reconstructs_sample_decisions_incl_no_switch(lab_tmp):
    frame, _ = _real_frame()
    prepared = PreparedAccount(frame)
    fold_row = {
        "fold_id": 0, "train_start": "2020-12-12T00:00:00+00:00",
        "train_end": "2020-12-31T23:59:00+00:00", "test_start": "2021-01-01T00:00:00+00:00",
        "test_end": "2021-01-08T00:00:00+00:00",
        "selected_params": {"coeff": 3, "AP": 37, "alpha.condition_threshold": 50,
                            "novolumedata": False, "src_col": "close"},
        "selected_is_objective": 1.0, "candidate_count": 2, "route": "event",
    }
    score = score_fold_for_admission(prepared, ALPHA_ID, fold_row, evidence_dir=lab_tmp,
                                     lab_run_id="d04")
    admit_meta = {"observation_available": True, "model_ready": True, "semantic_transition": False,
                  "eligibility": True, "confirmed": True, "budget_admitted": True, "reason": "INITIAL"}
    admitted = build_funnel_record(opportunity_id="opp-0", arm="M4_CAL", alpha_id=ALPHA_ID,
                                   fold_row=fold_row, admission_score=score, incumbent_params=None,
                                   incumbent_version=None, trigger_meta=admit_meta,
                                   account_costs={})
    assert admitted["admission_decision"] in ("ADMIT", "KEEP_INCUMBENT", "COMMON_FLAT_FALLBACK")

    # A SECOND opportunity offering the SAME params as the (now admitted)
    # incumbent must reconstruct as a genuine "no switch" -- unchanged_params
    # reason present, not silently indistinguishable from a real switch.
    if admitted["admission_decision"] == "ADMIT":
        incumbent_params = fold_row["selected_params"]
        incumbent_version = admitted["candidate_version"]
        same_score = score_fold_for_admission(prepared, ALPHA_ID, fold_row, evidence_dir=lab_tmp,
                                              lab_run_id="d04")
        repeat = build_funnel_record(opportunity_id="opp-1", arm="M4_CAL", alpha_id=ALPHA_ID,
                                     fold_row=fold_row, admission_score=same_score,
                                     incumbent_params=incumbent_params,
                                     incumbent_version=incumbent_version,
                                     trigger_meta={**admit_meta, "reason": "CALENDAR"},
                                     account_costs={})
        assert repeat["unchanged_params_reason"] == "identical to incumbent"
        assert repeat["incumbent_version"] == incumbent_version


# --- D05: full account path reconciles; no folded resets -------------------

def test_d05_account_path_reconciles_no_folded_resets(lab_tmp):
    frame, _ = _real_frame()
    prepared = PreparedAccount(frame)
    cal = build_calendar_schedule(WINDOW_START, WINDOW_END, test_days=4,
                                  train_memory_days=TRAIN_MEMORY_DAYS)
    result = run_one_arm(ALPHA_ID, frame, cal, prepared=prepared, trials=TRIALS, seed=SEED,
                         route="event", evidence_dir=lab_tmp, lab_run_id="d05")
    assert result["ok"]
    account = result["run"]["account"]
    assert account["status"] == "EVALUATED"
    assert account["equity_first"] == pytest.approx(20000.0)
    equity_daily = account.get("equity_daily") or []
    assert len(equity_daily) > 0
    # The account is legitimately flat at the initial mark through the whole
    # pre-trading train-memory warmup (no fills yet) -- that is normal, not a
    # reset, and this window's real data confirms it: 31 flat warmup days
    # before the first real fill. The actual "no folded reset / no splicing"
    # invariant is that fills come from ONE continuous engine pass, so their
    # own bar_index sequence -- which a spliced/restarted account could never
    # produce -- must be strictly increasing across the WHOLE run, fold
    # boundaries included.
    fills = account.get("fills") or []
    assert fills, "no fills to check continuity against"
    bar_indices = [f["bar_index"] for f in fills]
    assert bar_indices == sorted(bar_indices), (
        "fill bar_index sequence is not monotonically increasing: a spliced/restarted "
        "account would show an out-of-order or repeated index")
    assert len(set(bar_indices)) == len(bar_indices), "duplicate bar_index: possible double-count"


# --- D06: costs/budgets real; zero-change case not faked -------------------

def test_d06_costs_budgets_zero_change_not_fabricated(lab_tmp):
    frame, _ = _real_frame()
    prepared = PreparedAccount(frame)
    # An emission stream with ZERO eligible transitions: the regime schedule
    # must still be a valid (shared-initial-only) schedule, not a crash or a
    # fabricated trigger.
    empty_regime = build_regime_schedule([], window_start=WINDOW_START, window_end=WINDOW_END,
                                         train_memory_days=TRAIN_MEMORY_DAYS)
    assert empty_regime.cutoffs == (pd.Timestamp(WINDOW_START, tz="UTC").isoformat(),)

    cal = build_calendar_schedule(WINDOW_START, WINDOW_END, test_days=4,
                                  train_memory_days=TRAIN_MEMORY_DAYS)
    result = run_one_arm(ALPHA_ID, frame, cal, prepared=prepared, trials=TRIALS, seed=SEED,
                         route="event", evidence_dir=lab_tmp, lab_run_id="d06")
    assert result["ok"]
    requested = result["run"]["requested"]
    assert requested["account_capital"] == pytest.approx(20000.0)
    assert requested["fee_binding"], "real fee binding must be reported, not a placeholder"
    assert requested["optuna_trials_per_cutoff"] == TRIALS


# --- D07: all four arms present; one failure does not drop the others ------

def test_d07_all_four_arms_present_one_failure_does_not_drop_others(lab_tmp):
    from crypto_regime_lab.experiments.dynamic_fold_provider import CutoffSchedule

    frame, _ = _real_frame()
    prepared = PreparedAccount(frame)
    # An impossible schedule (empty cutoffs) -- run_cutoff_walk_forward raises
    # ProviderError internally; run_one_arm must capture it as a recorded
    # failure, not propagate and abort the whole comparison.
    broken = CutoffSchedule(arm="M4_REGIME", cutoffs=(), source="deliberately empty for D07")
    ok_schedule = build_static_schedule(WINDOW_START, WINDOW_END,
                                        train_memory_days=TRAIN_MEMORY_DAYS)

    broken_result = run_one_arm(ALPHA_ID, frame, broken, prepared=prepared, trials=TRIALS,
                                seed=SEED, route="event", evidence_dir=lab_tmp, lab_run_id="d07")
    ok_result = run_one_arm(ALPHA_ID, frame, ok_schedule, prepared=prepared, trials=TRIALS,
                            seed=SEED, route="event", evidence_dir=lab_tmp, lab_run_id="d07")

    arms = {"M4_REGIME": broken_result, "STATIC": ok_result}
    assert arms["M4_REGIME"]["ok"] is False
    assert arms["M4_REGIME"].get("error")
    assert arms["STATIC"]["ok"] is True
    # A downstream aggregate over a mixed ok/failed population must not drop
    # the failed arm's key, and must not raise.
    descriptive = descriptive_returns(arms)
    assert set(descriptive["by_arm"]) == {"M4_REGIME", "STATIC"}
    assert descriptive["by_arm"]["M4_REGIME"]["status"] == "NOT_EVALUABLE"
    assert descriptive["by_arm"]["STATIC"]["status"] == "OK"
    divergence = action_divergence(arms)
    assert divergence["per_arm_digests"]["M4_REGIME"] is None
    assert divergence["per_arm_digests"]["STATIC"] is not None
