"""LAB-06 acceptance tests T45-T52 plus the invariants behind them."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent

from crypto_regime_lab.policy import bank as BK
from crypto_regime_lab.policy import campaign as CP
from crypto_regime_lab.policy import clocks as CL
from crypto_regime_lab.policy import decision as DC
from crypto_regime_lab.policy import episodes as EP
from crypto_regime_lab.policy import limitations as LM
from crypto_regime_lab.policy import response as RS

T0 = pd.Timestamp("2022-01-01", tz="UTC")


def _episode(offset_days: int, *, net_return: float = 0.01, status=EP.OUTCOME_COMPLETE,
             eligible: bool = True, candidate="c", context=(0.0, 0.0)):
    start = T0 + pd.Timedelta(days=offset_days)
    end = start + pd.Timedelta(days=EP.PILOT_HORIZON_DAYS)
    return EP.Episode(
        episode_id=f"{candidate}@{offset_days}", episode_start=start, decision_time=start,
        context_asof_decision=tuple(context), context_state_id=0, context_namespace="ns",
        candidate_id=candidate, parameter_version="v1",
        outcome_start=start, outcome_end=end,
        outcome_available_at=end + EP.PUBLICATION_DELAY + EP.PROCESSING_DELAY,
        net_return=net_return, max_drawdown=0.01, turnover=0.1, cost=0.0004, trades=4,
        exposure=0.3, terminal_position=0.0,
        initial_state_contract=LM.INITIAL_STATE_FLAT,
        outcome_status=status, quality_eligible=eligible)


# ---------------------------------------------------------------------------
# T45 — an unfinished outcome may not be used at decision T
# ---------------------------------------------------------------------------

def test_t45_an_unfinished_outcome_is_unusable():
    episode = _episode(0)
    just_before = episode.outcome_available_at - pd.Timedelta(seconds=1)
    assert episode.usable_at(episode.outcome_available_at) is True
    assert episode.usable_at(just_before) is False, (
        "an outcome one second short of published is not a small outcome, it is no outcome")


def test_t45_the_availability_lag_is_the_full_horizon_plus_delays():
    episode = _episode(0)
    expected = episode.outcome_end + EP.PUBLICATION_DELAY + EP.PROCESSING_DELAY
    assert episode.outcome_available_at == expected
    assert episode.outcome_available_at > episode.decision_time + pd.Timedelta(
        days=EP.PILOT_HORIZON_DAYS)


def test_t45_the_builder_marks_an_unfinished_window_rather_than_dropping_it():
    times = [T0, T0 + pd.Timedelta(days=7)]
    contexts = {t: {"features": (0.0, 0.0), "state_id": 0, "namespace": "ns"} for t in times}
    grid = EP.build_episodes(
        decision_times=times, contexts=contexts, candidate_id="c", parameter_version="v",
        outcome_fn=lambda s, e: {"net_return": 0.01, "terminal_position": 0.0},
        now=T0 + pd.Timedelta(days=8))
    statuses = {e.outcome_status for e in grid.episodes}
    assert EP.OUTCOME_UNFINISHED in statuses, "the later window has not published yet"
    assert len(grid.episodes) == 2, "an unfinished episode is MARKED, not silently dropped"
    assert grid.usable_at(T0 + pd.Timedelta(days=8)) == [
        e for e in grid.episodes if e.outcome_status == EP.OUTCOME_COMPLETE]


def test_t45_an_open_position_at_horizon_end_is_marked_not_counted_as_a_win():
    grid = EP.build_episodes(
        decision_times=[T0], contexts={T0: {"features": (0.0,), "state_id": 0,
                                            "namespace": "ns"}},
        candidate_id="c", parameter_version="v",
        outcome_fn=lambda s, e: {"net_return": 0.05, "terminal_position": 0.5})
    episode = grid.episodes[0]
    assert episode.outcome_status == EP.OUTCOME_OPEN_POSITION
    assert episode.quality_eligible is True, (
        "an open position is a real outcome under the same account contract; discarding it would "
        "keep only closed wins")
    assert "closed win" in episode.quality_reason


def test_t45_the_primary_grid_is_non_overlapping():
    index = pd.date_range(T0, periods=200, freq="1D", tz="UTC")
    windows = EP.build_grid(index, horizon_days=7)
    for (s1, e1), (s2, _e2) in zip(windows, windows[1:]):
        assert s2 >= e1, "the primary evidence grid must not overlap"


def test_t45_an_overlapping_grid_must_declare_a_purge():
    index = pd.date_range(T0, periods=200, freq="1D", tz="UTC")
    with pytest.raises(EP.EpisodeError, match="purge"):
        EP.build_grid(index, horizon_days=7, overlapping=True, step_days=2, purge_days=0)
    windows = EP.build_grid(index, horizon_days=7, overlapping=True, step_days=2, purge_days=3)
    assert len(windows) > len(EP.build_grid(index, horizon_days=7))


def test_t45_the_dependence_correction_makes_the_inflation_visible():
    correction = EP.dependence_correction(n_windows=100, horizon_days=7, step_days=1)
    assert correction["overlap_factor"] == pytest.approx(7.0)
    assert correction["effective_independent_windows"] == pytest.approx(100 / 7)
    assert correction["effective_independent_windows"] < correction["windows"]


def test_t45_purging_removes_windows_inside_the_shadow():
    index = pd.date_range(T0, periods=60, freq="1D", tz="UTC")
    windows = EP.build_grid(index, horizon_days=7, overlapping=True, step_days=1, purge_days=3)
    purged = EP.purge_overlaps(windows, purge_days=3)
    assert len(purged) < len(windows)
    for (s1, e1), (s2, _e2) in zip(purged, purged[1:]):
        assert s2 >= e1 + pd.Timedelta(days=3)


# ---------------------------------------------------------------------------
# T46 — a candidate discovered after the cutoff never enters the bank
# ---------------------------------------------------------------------------

def _discovery(cid, when, score=1.0):
    """A distinct parameter point per id, so nothing merges as a duplicate by accident."""
    spread = sum(ord(ch) for ch in cid) % 40
    return {"candidate_id": cid, "params": {"AP": 10 + spread, "coeff": 2},
            "discovered_at": when, "score": score, "validation_panel": {}}


def test_t46_a_later_discovery_is_rejected_with_a_reason():
    cutoff = T0
    discoveries = [_discovery("c1", cutoff - pd.Timedelta(days=30)),
                   _discovery("c2", cutoff + pd.Timedelta(days=1))]
    bank = BK.build_bank(cutoff, discoveries, adapter_hash="h", warmup_bars=10)
    ids = [e.candidate_id for e in bank.admissible()]
    assert ids == ["c1"]
    assert any(r["candidate_id"] == "c2" and "after the cutoff" in r["reason"]
               for r in bank.rejected), "a rejection must carry its reason, not vanish"


def test_t46_trial_rows_are_retained_even_when_rejected_or_merged():
    cutoff = T0
    discoveries = [_discovery(f"c{i}", cutoff - pd.Timedelta(days=10)) for i in range(1, 5)]
    discoveries.append(_discovery("c9", cutoff + pd.Timedelta(days=5)))
    bank = BK.build_bank(cutoff, discoveries, adapter_hash="h", warmup_bars=10)
    assert bank.trial_rows_retained == len(discoveries), (
        "a merged or rejected candidate is still a trial that was paid for")


def test_t46_duplicates_merge_for_coverage_without_losing_rows():
    from crypto_regime_lab.selector.alpha_schemas import SCHEMAS

    cutoff = T0
    same = {"AP": 20, "coeff": 2, "alpha.condition_threshold": 50,
            "novolumedata": False, "src_col": "close"}
    discoveries = [
        {"candidate_id": "a", "params": dict(same), "discovered_at": cutoff, "score": 2.0,
         "validation_panel": {}},
        {"candidate_id": "b", "params": dict(same), "discovered_at": cutoff, "score": 1.0,
         "validation_panel": {}},
    ]
    bank = BK.build_bank(cutoff, discoveries, adapter_hash="h", warmup_bars=10,
                         schema=SCHEMAS["A-SC"])
    assert len(bank.admissible()) == 1
    assert bank.admissible()[0].merged_duplicates == ["b"]
    assert bank.trial_rows_retained == 2


def test_t46_the_bank_respects_the_proposed_size_range():
    cutoff = T0
    discoveries = [_discovery(f"c{i}", cutoff - pd.Timedelta(days=1), score=float(i))
                   for i in range(1, 20)]
    bank = BK.build_bank(cutoff, discoveries, adapter_hash="h", warmup_bars=10)
    assert len(bank.admissible()) <= BK.BANK_MAX
    assert bank.as_record()["proposed_size_range"] == [BK.BANK_MIN, BK.BANK_MAX]


def test_t46_a_retired_version_still_serves_an_open_campaign_and_cannot_be_deleted():
    cutoff = T0
    bank = BK.build_bank(cutoff, [_discovery("c1", cutoff)], adapter_hash="h", warmup_bars=10)
    entry = bank.entries[0]
    entry.open_campaign_refs.append("campaign-1")
    bank.retire("c1", cutoff + pd.Timedelta(days=1), "superseded")
    assert bank.serving_open_campaigns()[0].candidate_id == "c1"
    with pytest.raises(BK.BankError, match="still serves open campaigns"):
        bank.remove("c1")


def test_t46_indicator_readiness_is_tracked_by_version_and_cutoff():
    cutoff = T0
    bank = BK.build_bank(cutoff, [_discovery("c1", cutoff)], adapter_hash="h", warmup_bars=100)
    entry = bank.entries[0]
    assert entry.warm_at(cutoff, bar_hours=1.0) is False
    assert entry.warm_at(cutoff + pd.Timedelta(hours=100), bar_hours=1.0) is True


# ---------------------------------------------------------------------------
# T47 — incumbent and challenger are paired on the same episodes
# ---------------------------------------------------------------------------

def _estimate_inputs(n=12, delta=0.01, contexts=None, blocks=2):
    """Episodes drawn from ``blocks`` separated stretches.

    The estimator requires at least two contiguous blocks on purpose: twelve
    consecutive weeks inside one market stretch are ONE piece of evidence wearing
    twelve hats, and a fixture that ignored that would let every downstream test
    pass on support the real estimator would refuse.
    """
    rng = np.random.default_rng(3)
    inc = rng.normal(0.0, 0.005, size=n)
    cand = inc + delta
    ctx = contexts if contexts is not None else np.zeros((n, 2))
    per_block = max(1, n // max(1, blocks))
    order = np.concatenate([np.arange(per_block) + b * 1000
                            for b in range(blocks)])[:n]
    if order.size < n:                       # remainder joins the last block
        order = np.concatenate([order, np.arange(order.size, n) + (blocks - 1) * 1000])
    return dict(x_t=np.zeros(2), contexts=ctx, ages_days=np.arange(n)[::-1] * 7.0,
                eligibility=np.ones(n), feature_weights=np.full(2, 0.5),
                candidate_utility=cand, incumbent_utility=inc,
                episode_ids=[f"e{i}" for i in range(n)], order=order)


def test_t47_mismatched_episode_counts_are_refused():
    inputs = _estimate_inputs()
    inputs["incumbent_utility"] = inputs["incumbent_utility"][:-1]
    with pytest.raises(ValueError, match="SAME episodes"):
        RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i", **inputs)


def test_t47_the_delta_is_a_per_episode_difference():
    inputs = _estimate_inputs(delta=0.02)
    estimate = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i", **inputs)
    assert estimate.delta_local == pytest.approx(0.02, abs=1e-9), (
        "pairing on the same episode is what makes the horizon and economics cancel")


def test_t47_episodes_carry_the_same_initial_state_contract():
    episodes = [_episode(i * 7) for i in range(3)]
    assert len({e.initial_state_contract for e in episodes}) == 1
    assert episodes[0].initial_state_contract == LM.INITIAL_STATE_FLAT


# ---------------------------------------------------------------------------
# T48 — one episode dominating the similarity
# ---------------------------------------------------------------------------

def test_t48_a_dominating_episode_is_flagged_and_shrunk():
    n = 8
    contexts = np.full((n, 2), 10.0)
    contexts[0] = 0.0                      # only this episode looks like now
    inputs = _estimate_inputs(n=n, delta=0.05, contexts=contexts)
    estimate = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i",
                                    **inputs)
    assert estimate.diagnostics.max_weight_share > RS.DOMINANCE_SHARE
    assert estimate.status in (RS.STATUS_DOMINATED, RS.STATUS_INSUFFICIENT)
    assert abs(estimate.delta_shrunk) < abs(estimate.delta_local), (
        "shrinkage toward pooled must pull a dominated estimate back")


def test_t48_n_effective_is_labelled_as_weight_concentration():
    inputs = _estimate_inputs()
    estimate = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i",
                                    **inputs)
    record = estimate.as_record()
    assert "NOT a count of independent observations" in \
        record["diagnostics"]["n_effective_meaning"]


def test_t48_a_single_contiguous_block_is_not_enough_support():
    """Twelve consecutive weeks in one stretch is one piece of evidence, not twelve."""
    inputs = _estimate_inputs(n=12, delta=0.05, blocks=1)
    estimate = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i",
                                    **inputs)
    assert estimate.diagnostics.contiguous_blocks == 1
    assert estimate.status == RS.STATUS_INSUFFICIENT
    assert "contiguous blocks" in estimate.reason


def test_t48_thin_support_keeps_the_incumbent_rather_than_recommending():
    inputs = _estimate_inputs(n=3, delta=0.5)
    estimate = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i",
                                    **inputs)
    assert estimate.status == RS.STATUS_INSUFFICIENT
    assert "incumbent is kept" in estimate.reason


def test_t48_eligibility_may_not_be_a_graded_quality_score():
    inputs = _estimate_inputs()
    inputs["eligibility"] = np.linspace(0.1, 1.0, len(inputs["episode_ids"]))
    with pytest.raises(ValueError, match="0 or 1"):
        RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i", **inputs)


def test_t48_supporting_episodes_are_returned_with_the_estimate():
    inputs = _estimate_inputs()
    estimate = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i",
                                    **inputs)
    assert estimate.supporting_episodes
    for row in estimate.supporting_episodes:
        assert {"episode_id", "weight", "share", "paired_delta"} <= set(row)


def test_t48_the_standard_error_comes_from_blocks_not_from_bars():
    inputs = _estimate_inputs(n=12, blocks=2)
    estimate = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i",
                                    **inputs)
    assert estimate.diagnostics.contiguous_blocks == 2
    assert "paired contiguous blocks" in estimate.as_record()["se_basis"]


# ---------------------------------------------------------------------------
# T49 — refit latency and out-of-order jobs
# ---------------------------------------------------------------------------

def test_t49_activation_may_never_precede_ready():
    scheduler = CL.Scheduler()
    scheduler.trigger("j1", CL.MODEL_RETRAIN, T0)
    scheduler.complete("j1", T0 + pd.Timedelta(hours=6))
    with pytest.raises(CL.ClockError, match="precedes ready_at"):
        scheduler.activate("j1", T0 + pd.Timedelta(hours=1))
    activated = scheduler.activate("j1", T0 + pd.Timedelta(hours=6))
    assert activated.effective_at >= activated.ready_at


def test_t49_a_superseded_job_never_becomes_effective():
    scheduler = CL.Scheduler()
    scheduler.trigger("j1", CL.MODEL_RETRAIN, T0)
    scheduler.trigger("j2", CL.MODEL_RETRAIN, T0 + pd.Timedelta(days=5))
    stale = scheduler.complete("j1", T0 + pd.Timedelta(days=6))     # finishes LATE
    assert stale.status == CL.JOB_SUPERSEDED
    assert "result discarded" in stale.reason
    with pytest.raises(CL.ClockError, match="only a READY job"):
        scheduler.activate("j1", T0 + pd.Timedelta(days=7))


def test_t49_a_refit_keeps_the_cutoff_it_was_triggered_with():
    scheduler = CL.Scheduler()
    job = scheduler.trigger("j1", CL.MODEL_RETRAIN, T0)
    scheduler.complete("j1", T0 + pd.Timedelta(days=3))
    assert job.cutoff == T0, (
        "a long-running job may not extend its cutoff to swallow data that arrived while it ran")


def test_t49_near_duplicate_triggers_coalesce_into_one_job():
    scheduler = CL.Scheduler()
    scheduler.trigger("j1", CL.BANK_REFRESH, T0)
    second = scheduler.trigger("j2", CL.BANK_REFRESH, T0 + pd.Timedelta(hours=2))
    assert second.status == CL.JOB_COALESCED
    assert second.superseded_by == "j1"


def test_t49_the_incumbent_runs_while_a_refit_is_pending():
    scheduler = CL.Scheduler()
    scheduler.trigger("j1", CL.MODEL_RETRAIN, T0)
    assert scheduler.incumbent_runs_while_pending(CL.MODEL_RETRAIN) is True


def test_t49_a_job_cannot_be_ready_before_it_was_triggered():
    scheduler = CL.Scheduler()
    scheduler.trigger("j1", CL.MODEL_RETRAIN, T0)
    with pytest.raises(CL.ClockError, match="ready before it was triggered"):
        scheduler.complete("j1", T0 - pd.Timedelta(hours=1))


# ---------------------------------------------------------------------------
# T50 — a switch while a campaign is open
# ---------------------------------------------------------------------------

def test_t50_the_entry_digest_is_immutable():
    campaign = CP.Campaign("camp-1", T0, "digest-A", "cand-A")
    with pytest.raises(CP.CampaignError, match="immutable"):
        campaign.migrate_entry_digest("digest-B")
    assert campaign.protective_version == "cand-A"


def test_t50_an_open_campaign_defers_the_switch_rather_than_cancelling_it():
    book = CP.CampaignBook()
    book.campaigns.append(CP.Campaign("camp-1", T0, "digest-A", "cand-A"))
    activation = book.request_activation("sel-1", "cand-B", T0 + pd.Timedelta(days=1), "better")
    assert activation.activated_at is None and activation.blocked_by == "open_campaign"
    book.campaigns[0].close(T0 + pd.Timedelta(days=3))
    done = book.try_activate_pending(T0 + pd.Timedelta(days=3))
    assert done and done[0].delay == pd.Timedelta(days=2), (
        "both the requested time and the actual delay must be recorded")


def test_t50_the_decision_machine_waits_at_a_campaign_boundary():
    estimate = _supported_estimate(delta=0.05)
    outcome = DC.decide(selection_id="s", decision_time=T0, incumbent_id="i",
                        estimates=[estimate],
                        costs={"c": DC.transition_cost(1.0, fee_rate=0.0004,
                                                       slippage_rate=0.0001)},
                        quality_status="OK", campaign_open=True, last_switch_at=None,
                        warm_candidates={"c"}, data_cutoff="d", bank_cutoff="b")
    assert outcome.decision == DC.WAIT_CAMPAIGN_BOUNDARY
    assert "entered with" in outcome.reason


def test_t50_a_long_open_campaign_is_blocked_not_force_closed():
    book = CP.CampaignBook()
    book.campaigns.append(CP.Campaign("camp-1", T0, "d", "c"))
    record = book.as_record(now=T0 + pd.Timedelta(days=CP.STALE_CAMPAIGN_DAYS + 5))
    assert record["transition_blocked"] == 1
    assert record["forced_unwind_used"] is False
    assert "manufacture the time edge" in record["forced_unwind_rule"]


# ---------------------------------------------------------------------------
# T51 — unwarmed indicators
# ---------------------------------------------------------------------------

def _supported_estimate(delta=0.05, candidate="c"):
    inputs = _estimate_inputs(n=12, delta=delta)
    return RS.estimate_response(response_id="r", candidate_id=candidate, incumbent_id="i",
                                **inputs)


def test_t51_an_unwarmed_candidate_waits_instead_of_switching():
    estimate = _supported_estimate(delta=0.05)
    outcome = DC.decide(selection_id="s", decision_time=T0, incumbent_id="i",
                        estimates=[estimate],
                        costs={"c": DC.transition_cost(1.0, fee_rate=0.0004,
                                                       slippage_rate=0.0001)},
                        quality_status="OK", campaign_open=False, last_switch_at=None,
                        warm_candidates=set(), data_cutoff="d", bank_cutoff="b")
    assert outcome.decision == DC.WAIT_CAMPAIGN_BOUNDARY
    assert "not warm" in outcome.reason


def test_t51_indicator_state_is_never_carried_without_a_contract():
    a = CP.IndicatorWarmup("cand-A", required_bars=50, bars_seen=50)
    b = CP.IndicatorWarmup("cand-B", required_bars=50)
    with pytest.raises(CP.CampaignError, match="without a declared contract"):
        b.carry_from(a)
    b.carry_from(a, contract="same_indicator_family_and_length")
    assert b.status == CP.WARMUP_READY and b.carried_from == "cand-A"


def test_t51_warmup_progresses_from_cold_through_warming_to_ready():
    warm = CP.IndicatorWarmup("c", required_bars=3)
    assert warm.status == CP.WARMUP_COLD
    warm.observe(1)
    assert warm.status == CP.WARMUP_WARMING
    warm.observe(2)
    assert warm.status == CP.WARMUP_READY


# ---------------------------------------------------------------------------
# T52 — distinct clocks, no recursive trigger storm
# ---------------------------------------------------------------------------

def test_t52_the_four_clocks_are_distinct():
    assert len(set(CL.CLOCKS)) == 4
    assert set(CL.CLOCKS) == {CL.INFERENCE, CL.SWITCH, CL.BANK_REFRESH, CL.MODEL_RETRAIN}


def test_t52_inference_and_switch_can_never_start_a_refit():
    scheduler = CL.Scheduler()
    for clock in (CL.INFERENCE, CL.SWITCH):
        with pytest.raises(CL.ClockError, match="not a refit clock"):
            scheduler.trigger("j", clock, T0)


def test_t52_the_counters_stay_separate():
    counters = CL.ClockCounters()
    counters.inference += 10
    counters.switch_assessments += 5
    counters.switches_executed += 1
    counters.model_retrains += 2
    record = counters.as_record()
    assert record["inference"] == 10 and record["switches_executed"] == 1
    assert record["model_retrains"] == 2
    assert "three separate counters" in record["rule"]


def test_t52_the_retrain_detector_ignores_strategy_performance():
    quiet = CL.retrain_trigger(novelty_rate=0.01, fit_residual_drift=0.05,
                               strategy_performance=-0.90)
    assert quiet["should_retrain"] is False, (
        "a terrible strategy result must not trigger a market-model retrain")
    assert quiet["strategy_performance_used"] is False
    loud = CL.retrain_trigger(novelty_rate=0.5, fit_residual_drift=0.05)
    assert loud["should_retrain"] is True, "genuine covariate novelty must still fire"


def test_t52_a_familiar_state_change_is_not_drift():
    record = CL.retrain_trigger(novelty_rate=0.0, fit_residual_drift=0.0)
    assert "the model working, not the model breaking" in \
        record["familiar_state_change_is_not_drift"]


# ---------------------------------------------------------------------------
# guide 9.3 — the decision machine's own invariants
# ---------------------------------------------------------------------------

def test_the_seven_decisions_exist_and_are_distinct():
    assert len(set(DC.DECISIONS)) == 7


def test_an_inaction_region_exists_between_worse_and_clearly_better():
    cost = DC.transition_cost(1.0, fee_rate=0.0004, slippage_rate=0.0001)
    marginal = _supported_estimate(delta=cost.total * 0.5)
    outcome = DC.decide(selection_id="s", decision_time=T0, incumbent_id="i",
                        estimates=[marginal], costs={"c": cost}, quality_status="OK",
                        campaign_open=False, last_switch_at=None, warm_candidates={"c"},
                        data_cutoff="d", bank_cutoff="b")
    assert outcome.decision == DC.KEEP_INCUMBENT
    assert "inaction region" in outcome.reason


def test_the_quality_gate_may_reject_everything():
    thin = RS.estimate_response(response_id="r", candidate_id="c", incumbent_id="i",
                               **_estimate_inputs(n=2, delta=1.0))
    outcome = DC.decide(selection_id="s", decision_time=T0, incumbent_id="i",
                        estimates=[thin], costs={}, quality_status="OK",
                        campaign_open=False, last_switch_at=None, data_cutoff="d",
                        bank_cutoff="b")
    assert outcome.decision == DC.NO_SUPPORTED_CANDIDATE
    assert "not forced into a trade" in outcome.reason


def test_missing_data_and_a_novel_state_give_different_fallbacks():
    kwargs = dict(selection_id="s", decision_time=T0, incumbent_id="i", estimates=[],
                  costs={}, campaign_open=False, last_switch_at=None,
                  data_cutoff="d", bank_cutoff="b")
    assert DC.decide(quality_status="MISSING_DATA", **kwargs).decision == DC.FALLBACK_DATA
    assert DC.decide(quality_status="UNKNOWN_STATE", **kwargs).decision == \
        DC.FALLBACK_NOVEL_STATE


def test_an_empty_bank_requests_a_refresh_instead_of_forcing_a_choice():
    outcome = DC.decide(selection_id="s", decision_time=T0, incumbent_id="i", estimates=[],
                        costs={}, quality_status="OK", campaign_open=False,
                        last_switch_at=None, bank_adequate=False, data_cutoff="d",
                        bank_cutoff="b")
    assert outcome.decision == DC.REFRESH_BANK_REQUESTED


def test_minimum_spacing_blocks_a_second_switch_too_soon():
    cost = DC.transition_cost(1.0, fee_rate=0.0004, slippage_rate=0.0001)
    outcome = DC.decide(selection_id="s", decision_time=T0, incumbent_id="i",
                        estimates=[_supported_estimate(delta=0.05)], costs={"c": cost},
                        quality_status="OK", campaign_open=False,
                        last_switch_at=T0 - pd.Timedelta(days=1), warm_candidates={"c"},
                        data_cutoff="d", bank_cutoff="b")
    assert outcome.decision == DC.KEEP_INCUMBENT
    assert "minimum spacing" in outcome.reason


def test_a_clear_winner_does_switch_so_the_machine_is_not_merely_conservative():
    cost = DC.transition_cost(1.0, fee_rate=0.0004, slippage_rate=0.0001)
    outcome = DC.decide(selection_id="s", decision_time=T0, incumbent_id="i",
                        estimates=[_supported_estimate(delta=0.05)], costs={"c": cost},
                        quality_status="OK", campaign_open=False, last_switch_at=None,
                        warm_candidates={"c"}, data_cutoff="d", bank_cutoff="b")
    assert outcome.decision == DC.SWITCH_READY, (
        "if nothing could ever switch, every other test here would pass vacuously")
    assert outcome.supporting_episodes


def test_the_transition_cost_is_never_double_charged():
    cost = DC.transition_cost(2.0, fee_rate=0.0004, slippage_rate=0.0001)
    assert cost.total == pytest.approx(2.0 * 0.0005)
    assert "would bill the same cost twice" in cost.as_record()["charging_rule"]


def test_the_policy_spec_records_the_check_order():
    spec = DC.policy_spec()
    assert spec["check_order"][0] == "data quality"
    assert spec["inaction_region"] is True
    assert spec["zero_switches_is_valid"]


# ---------------------------------------------------------------------------
# L06.6 — counterfactual limits
# ---------------------------------------------------------------------------

def test_the_counterfactual_limits_are_recorded_with_four_named_causes():
    limits = LM.counterfactual_limits()
    assert len(limits["limits"]) == 4
    for limit in limits["limits"]:
        assert limit["not_captured_by"] == "response uncertainty"
    assert "would not represent them" in limits["why_uncertainty_is_not_enough"]


def test_the_reset_flat_expert_curve_is_forbidden():
    check = LM.expert_curve_check(False)
    assert check["permitted"] is False
    assert check["reset_flat_expert_curve_used_as_deploy_equity"] is False


def test_training_and_live_initial_state_contracts_differ_and_say_so():
    contract = LM.initial_state_contract()
    assert contract["training_episodes_use"] != contract["live_switch_uses"]
    assert contract["mismatch_is_real"] is True


def test_t46_every_entry_carries_its_own_discovery_time():
    """Regression: a leaked loop variable gave every entry the LAST row's timestamp.

    The filter still worked, so the bank looked right — but the recorded
    ``discovered_at`` was wrong on every entry, which is exactly the lineage field
    T46 exists to protect. It only surfaced because ``admissible()`` re-checks
    instead of trusting the build.
    """
    cutoff = T0 + pd.Timedelta(days=365)
    discoveries = [
        _discovery("early", T0, score=1.0),
        _discovery("late", T0 + pd.Timedelta(days=200), score=2.0),
    ]
    bank = BK.build_bank(cutoff, discoveries, adapter_hash="h", warmup_bars=10)
    by_id = {e.candidate_id: e for e in bank.entries}
    assert by_id["early"].discovered_at == T0
    assert by_id["late"].discovered_at == T0 + pd.Timedelta(days=200)
    assert len({e.discovered_at for e in bank.entries}) == 2, (
        "two candidates found on different days must not share one timestamp")
    # and the re-check must agree with the build
    assert len(bank.admissible()) == len(bank.entries)


def test_t46_admissible_re_checks_rather_than_trusting_the_build():
    """The re-check is what caught the bug above; keep it honest."""
    cutoff = T0
    bank = BK.build_bank(cutoff, [_discovery("c1", T0 - pd.Timedelta(days=1))],
                         adapter_hash="h", warmup_bars=10)
    assert len(bank.admissible()) == 1
    bank.entries[0].discovered_at = cutoff + pd.Timedelta(days=1)   # simulate corruption
    assert bank.admissible() == [], (
        "admissible() must filter on the entry's own timestamp, not on what build_bank believed")


# --- guide 13.4: the minimum evidence a decision has to carry ----------------
def _estimate(candidate_id, delta, se, episodes=9):
    from dataclasses import dataclass

    @dataclass
    class _Est:
        candidate_id: str
        status: str
        delta_shrunk: float
        standard_error: float
        response_id: str = "resp-1"
        supporting_episodes: list = None

    return _Est(candidate_id, "SUPPORTED", delta, se,
                supporting_episodes=[{"episode_id": f"e{i}"} for i in range(episodes)])


def test_a_no_switch_records_what_the_economics_proposed_before_any_gate():
    """Guide 13.4 names `proposal_before_guard` and `decision_after_guard`.

    Without the pair, "no challenger was better" and "a challenger WAS better and
    a gate refused it" are the same row. That difference is the entire content of
    an inaction region, and LAB-06's whole result is an inaction region.
    """
    now = pd.Timestamp("2024-01-01", tz="UTC")
    cost = DC.transition_cost(1.0, fee_rate=0.0004, slippage_rate=0.0001)

    refused = DC.decide(selection_id="s-refused", decision_time=now, incumbent_id="inc",
                        estimates=[_estimate("cand", 0.02, 0.001)], costs={"cand": cost},
                        quality_status="OK", campaign_open=True, last_switch_at=None)
    assert refused.decision == DC.WAIT_CAMPAIGN_BOUNDARY
    assert refused.proposal_before_guard["clears_the_economics"] is True
    assert refused.decision_after_guard["binding_gate"] == "CAMPAIGN_BOUNDARY"
    assert refused.decision_after_guard["changed_the_proposal"] is True

    inaction = DC.decide(selection_id="s-inaction", decision_time=now, incumbent_id="inc",
                         estimates=[_estimate("weak", 0.0001, 0.00005, episodes=1)],
                         costs={"weak": cost}, quality_status="OK", campaign_open=False,
                         last_switch_at=None)
    assert inaction.decision == DC.KEEP_INCUMBENT
    assert inaction.proposal_before_guard["clears_the_economics"] is False
    assert inaction.decision_after_guard["binding_gate"] == "ECONOMICS"
    assert inaction.decision_after_guard["changed_the_proposal"] is False

    # the two are DIFFERENT rows, which is the whole point
    assert (refused.decision_after_guard["changed_the_proposal"]
            != inaction.decision_after_guard["changed_the_proposal"])


def test_a_decision_settled_before_the_economics_says_where_it_stopped():
    now = pd.Timestamp("2024-01-01", tz="UTC")
    early = DC.decide(selection_id="s-novel", decision_time=now, incumbent_id="inc",
                      estimates=[], costs={}, quality_status="UNKNOWN_STATE",
                      campaign_open=False, last_switch_at=None)
    assert early.decision == DC.FALLBACK_NOVEL_STATE
    assert early.proposal_before_guard["status"] == "NO_PROPOSAL"
    assert early.proposal_before_guard["blocked_at"] == "NOVEL_STATE"
    assert early.decision_after_guard["changed_the_proposal"] is False


def test_a_risk_only_action_is_never_called_a_parameter_switch():
    """Guide 13.4: if a threshold only changes risk, action_type is risk_only."""
    now = pd.Timestamp("2024-01-01", tz="UTC")
    cost = DC.transition_cost(1.0, fee_rate=0.0004, slippage_rate=0.0001)
    switched = DC.decide(selection_id="s-switch", decision_time=now, incumbent_id="inc",
                         estimates=[_estimate("cand", 0.02, 0.001)], costs={"cand": cost},
                         quality_status="OK", campaign_open=False, last_switch_at=None,
                         incumbent_params={"fast": 3},
                         candidate_params={"cand": {"fast": 9}}, campaign_version="v0")
    assert switched.decision == DC.SWITCH_READY
    assert switched.action_type == "parameter_switch"
    assert switched.incumbent_params == {"fast": 3}
    assert switched.challenger_params == {"fast": 9}
    assert switched.campaign_version_before == "v0"
    assert switched.campaign_version_after == "cand"

    kept = DC.decide(selection_id="s-keep", decision_time=now, incumbent_id="inc",
                     estimates=[], costs={}, quality_status="OK",
                     campaign_open=False, last_switch_at=None)
    assert kept.action_type == "none", (
        "a decision that deployed nothing must not be typed as a parameter switch")


def test_every_committed_decision_carries_the_guide_13_4_fields(lab_root):
    """And the ledger on disk actually has them, not just the dataclass."""
    import json

    path = lab_root / "configs" / "lab06_decision_ledger.json"
    if not path.is_file():
        pytest.skip("run scripts/run_response_policy.py")
    ledger = json.loads(path.read_text())["ledger"]
    assert ledger, "the ledger is empty"
    required = ("proposal_before_guard", "decision_after_guard", "action_type",
                "incumbent_params", "requested_at", "campaign_version_before",
                "campaign_version_after")
    for row in ledger[:200]:
        for field in required:
            assert field in row, f"decision {row['selection_id']} has no {field}"
        assert row["decision_after_guard"]["binding_gate"] is not None or \
            row["decision"] == DC.SWITCH_READY
