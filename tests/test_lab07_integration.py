"""LAB-07 — continuous regime-aware WFO integration (T53-T57 and the L07 clauses)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.integration.activation import (
    ActivationError,
    ActivationTape,
    IndicatorState,
    OpenCampaign,
    ProtectiveOrder,
    parameter_digest,
)
from crypto_regime_lab.integration.binding import build_binding_map
from crypto_regime_lab.integration.continuous import (
    AccountState,
    ContinuousError,
    disabled_hooks_parity,
    replay_parity,
)
from crypto_regime_lab.integration.continuous_account import (
    VersionWindow,
    run_continuous_account,
)
from crypto_regime_lab.integration.events import (
    EVENT_KINDS,
    EventBus,
    EventError,
    assert_no_future_activation_end,
)
from crypto_regime_lab.integration.failures import (
    FAILURE_MODES,
    FailureError,
    FailureLedger,
    classify_context,
)
from crypto_regime_lab.integration.jobs import (
    JobError,
    RefitBenchmark,
    TrainingAccountContract,
    TrainingJobRunner,
)
from crypto_regime_lab.integration.segments import SegmentLog


@pytest.fixture(scope="module")
def real_bars(lab_root):
    """A REAL slice of BTCUSDT 15m bars that the alpha actually trades on.

    The synthetic random walk `_bars` builds produces ZERO entries for A-SC at
    any volatility tried, so every test that used it for a trading claim was
    asserting over an empty fill list -- including the one written to guard the
    tape-assembly defect. Tests that need trades use real bars and assert that
    trades happened, so the vacuity cannot come back silently.
    """
    from crypto_regime_lab.data import panel as P

    manifest_path = lab_root / "snapshots" / "server_core_v1" / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("run scripts/snapshot_data.py")
    frame = P.load_resampled(lab_root / "snapshots" / "server_core_v1",
                             "crypto_binance_futures_1m", "BTCUSDT", "15min",
                             manifest=json.loads(manifest_path.read_text()))
    if frame["time"].dt.tz is None:
        frame["time"] = frame["time"].dt.tz_localize("UTC")
    frame = frame.set_index("time").sort_index()
    return frame[(frame.index >= "2021-01-01 00:00:00+00:00")
                 & (frame.index < "2021-07-01 00:00:00+00:00")]


def _bars(n=400, seed=3, start="2021-01-01", freq="15min"):
    rng = np.random.default_rng(seed)
    close = 30_000.0 * np.exp(np.cumsum(rng.normal(0, 0.0008, n)))
    index = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": close, "high": close * 1.002, "low": close * 0.998,
                         "close": close, "volume": rng.uniform(1.0, 9.0, n)}, index=index)


# --- L07.2 the availability event bus -------------------------------------


def test_the_stream_carries_every_kind_the_guide_names():
    assert set(EVENT_KINDS) == {
        "BAR_COMPLETED", "REGIME_OBSERVATION_READY", "REFIT_REQUESTED", "REFIT_STARTED",
        "REFIT_READY", "PARAMETER_ACTIVATED", "ENGINE_FILL"}


def test_refit_request_start_and_ready_are_three_events_not_one():
    """The gap between them is the latency L07.3 forbids setting to zero.

    One event with a mutable status field would make that gap unobservable.
    """
    for kind in ("REFIT_REQUESTED", "REFIT_STARTED", "REFIT_READY"):
        assert kind in EVENT_KINDS


def test_an_event_cannot_be_available_before_it_happened():
    bus = EventBus()
    with pytest.raises(EventError, match="cannot be known before"):
        bus.publish("BAR_COMPLETED", "2021-01-01 12:00", available_at="2021-01-01 11:00")


def test_same_timestamp_events_are_ordered_causally_not_by_arrival():
    """Guide 4.2: same-timestamp events need sequence ids, never millisecond equality."""
    bus = EventBus()
    at = "2021-03-01 08:00"
    bus.publish("ENGINE_FILL", at, order_id="f")          # published FIRST
    bus.publish("BAR_COMPLETED", at, close=1.0)
    bus.publish("REGIME_OBSERVATION_READY", at, state_id=1)
    kinds = [e.kind for e in bus.ordered()]
    assert kinds == ["BAR_COMPLETED", "REGIME_OBSERVATION_READY", "ENGINE_FILL"], (
        "a fill cannot precede the bar that caused it, whatever order they were published in")


def test_visibility_is_decided_by_available_at_not_observed_at():
    bus = EventBus()
    bus.publish("REGIME_OBSERVATION_READY", "2021-01-01 00:00",
                available_at="2021-01-01 04:00", state_id=2)
    assert bus.visible_at("2021-01-01 03:59") == []
    assert len(bus.visible_at("2021-01-01 04:00")) == 1


def test_an_activation_may_not_publish_its_own_end():
    """The cleanest possible look-ahead, and the one that reads as bookkeeping."""
    bus = EventBus()
    bus.publish("PARAMETER_ACTIVATED", "2021-01-01", parameter_version="pv-1")
    assert assert_no_future_activation_end(bus.ordered())["clean"] is True

    bus.publish("PARAMETER_ACTIVATED", "2021-02-01", parameter_version="pv-2",
                activation_end="2021-03-01")
    verdict = assert_no_future_activation_end(bus.ordered())
    assert verdict["clean"] is False and len(verdict["offenders"]) == 1


# --- L07.3 training job isolation -----------------------------------------


def test_a_zero_latency_refit_is_refused():
    """Guide L07.3 names this: never take a refit time of zero to fill earlier."""
    from crypto_regime_lab.integration.jobs import RefitJob
    with pytest.raises(JobError, match="free option"):
        RefitJob(job_id="j", clock="model_retrain", requested_at="2021-01-01",
                 data_cutoff="2021-01-01", latency=pd.Timedelta(0),
                 latency_source="measured_benchmark")


def test_a_latency_with_no_provenance_is_refused():
    from crypto_regime_lab.integration.jobs import RefitJob
    with pytest.raises(JobError, match="no provenance"):
        RefitJob(job_id="j", clock="model_retrain", requested_at="2021-01-01",
                 data_cutoff="2021-01-01", latency=pd.Timedelta("5min"),
                 latency_source="i_guessed")


def test_a_job_cannot_read_past_its_cutoff_however_long_it_runs():
    runner = TrainingJobRunner(RefitBenchmark(measured_seconds_per_fit=2.0, workers=1))
    job = runner.request("j0", "model_retrain", "2021-06-01", fits=2, data_cutoff="2021-06-01")
    job.start("2021-06-01")
    with pytest.raises(JobError, match="does not earn access"):
        job.assert_reads_are_legal(["2021-05-31", "2021-06-02"])


def test_a_job_cannot_be_commissioned_to_read_the_future():
    runner = TrainingJobRunner(RefitBenchmark(measured_seconds_per_fit=2.0, workers=1))
    with pytest.raises(JobError, match="read the future"):
        runner.request("j1", "model_retrain", "2021-06-01", fits=1, data_cutoff="2021-07-01")


def test_partial_waves_round_up_so_the_budget_is_not_exceeded():
    benchmark = RefitBenchmark(measured_seconds_per_fit=10.0, workers=2)
    assert benchmark.latency_for(fits=3) == pd.Timedelta(seconds=20), (
        "three fits on two workers occupy two waves; rounding down hands the dynamic policy "
        "compute the resource budget forbids")


def test_the_training_account_contract_is_not_the_deployment_contract():
    contract = TrainingAccountContract()
    assert contract.resets_between_candidates is True
    assert contract.role == "training"
    record = TrainingJobRunner(
        RefitBenchmark(measured_seconds_per_fit=1.0, workers=1)).as_record()
    assert record["deployment_account_reachable_from_here"] is False


# --- L07.4 activation and migration (guide 9.5) ---------------------------


def test_an_open_campaign_blocks_the_switch_and_is_never_force_closed():
    tape = ActivationTape()
    incumbent, challenger = "pv-old", "pv-new"
    tape.active_version = incumbent
    tape.register_indicator(IndicatorState(challenger, required_bars=10, warm_bars=10))
    campaign = tape.register_campaign(OpenCampaign(
        campaign_id="c0", entry_parameter_digest=incumbent, opened_at="2021-01-01"))

    activation = tape.request("a1", "s1", challenger, "2021-01-02")
    tape.try_activate(activation, "2021-01-02")
    assert activation.activated_at is None
    assert activation.blocked_reason == "TRANSITION_BLOCKED_OPEN_CAMPAIGN"

    with pytest.raises(ActivationError, match="never closed because the parameters changed"):
        campaign.close("2021-01-02", reason="parameters_changed")


def test_a_cold_indicator_makes_the_switch_wait_rather_than_reinitialise():
    tape = ActivationTape()
    tape.active_version = "pv-old"
    tape.register_indicator(IndicatorState("pv-new", required_bars=30, warm_bars=5))
    activation = tape.request("a1", "s1", "pv-new", "2021-01-02")
    tape.try_activate(activation, "2021-01-02")
    assert activation.blocked_reason == "WAITING_FOR_WARM_INDICATORS"


def test_carrying_indicator_state_without_a_contract_is_refused():
    """An HMA warmed at length 40 is not an HMA of length 90 that saw the same bars."""
    old = IndicatorState("pv-old", required_bars=30, warm_bars=30)
    new = IndicatorState("pv-new", required_bars=30)
    with pytest.raises(ActivationError, match="needs a declared contract"):
        new.carry_from(old, contract="")
    new.carry_from(old, contract="both versions use the same fixed-length EMA")
    assert new.is_warm and new.carry_contract


def test_a_retired_version_survives_while_an_order_references_it():
    tape = ActivationTape()
    version = "pv-old"
    tape.register_campaign(OpenCampaign(
        campaign_id="c0", entry_parameter_digest=version, opened_at="2021-01-01",
        protective_orders=[ProtectiveOrder("sl", "stop", version, 100.0)]))
    with pytest.raises(ActivationError, match="live protective orders"):
        tape.retire(version)


def test_the_entry_digest_is_immutable():
    campaign = OpenCampaign(campaign_id="c0", entry_parameter_digest="pv-a",
                            opened_at="2021-01-01")
    campaign.entry_parameter_digest = "pv-b"
    with pytest.raises(ActivationError, match="names what this trade ENTERED with"):
        campaign.assert_digest_immutable()


def test_the_activation_record_never_carries_an_end():
    tape = ActivationTape()
    tape.active_version = "pv-old"
    tape.register_indicator(IndicatorState("pv-new", required_bars=1, warm_bars=1))
    activation = tape.request("a1", "s1", "pv-new", "2021-01-02")
    tape.try_activate(activation, "2021-01-02")
    assert "activation_end" not in activation.as_record()
    assert activation.as_record()["activation_delay_seconds"] == 0.0


# --- L07.5 segments -------------------------------------------------------


def test_an_open_segment_has_no_length_until_the_next_activation_exists():
    log = SegmentLog()
    log.record_activation(activation_id="a0", parameter_version="pv-a", at="2021-01-01")
    assert log.open_segment().length_days() is None, (
        "a running segment's length does not exist yet; writing it would hand a policy the "
        "answer to how long its own decision lasts")
    log.record_activation(activation_id="a1", parameter_version="pv-b", at="2021-02-01")
    assert log.segments[0].length_days() == pytest.approx(31.0)
    assert log.segments[1].end is None


def test_a_no_change_trigger_is_recorded_not_dropped():
    """Dropping them makes the refresh cadence look like the switch rate."""
    log = SegmentLog()
    log.record_activation(activation_id="a0", parameter_version="pv-a", at="2021-01-01")
    log.record_no_change(trigger_id="t1", at="2021-01-05", reason="KEEP_INCUMBENT")
    assert log.as_record()["no_change_trigger_count"] == 1
    assert log.segments[0].triggered_no_change is True


def test_a_decision_may_not_carry_the_length_of_its_own_segment():
    log = SegmentLog()
    assert log.assert_no_future_length_used([{"at": "x", "state": 1}])["clean"] is True
    dirty = log.assert_no_future_length_used([{"at": "x", "segment_length_days": 30}])
    assert dirty["clean"] is False


def test_the_daily_account_is_the_comparison_not_the_mean_of_segment_sharpes():
    """T55 — segments differ in length, so their unweighted mean mis-weights them."""
    log = SegmentLog()
    log.record_activation(activation_id="a0", parameter_version="pv-a", at="2021-01-01")
    log.record_activation(activation_id="a1", parameter_version="pv-b", at="2021-01-11")
    index = pd.date_range("2021-01-01", periods=120, freq="1D", tz="UTC")
    rng = np.random.default_rng(4)
    equity = pd.Series(20_000 * np.exp(np.cumsum(rng.normal(0, 0.003, 120))), index=index)
    report = log.daily_account_comparison(equity)
    assert report["primary_is_the_daily_account"] is True
    assert report["account_daily_sharpe"] is not None
    assert len(set(report["segment_day_counts"])) > 1, "the segments must differ in length"


# --- L07.6 failure handling -----------------------------------------------


def test_missing_and_stale_context_are_different_failures():
    """They have opposite fixes: an outage versus a cadence problem."""
    assert classify_context(None, now="2021-01-02", ttl="8h")[0] == "MISSING_CONTEXT"
    assert classify_context({"available_at": "2021-01-01"}, now="2021-01-03",
                            ttl="8h")[0] == "STALE_CONTEXT"
    assert classify_context({"available_at": "2021-01-03"}, now="2021-01-03",
                            ttl="8h")[0] == "OK"


def test_a_failed_fit_with_no_previous_model_stops_rather_than_guesses():
    ledger = FailureLedger(incumbent_version="pv-a")
    with pytest.raises(FailureError, match="no validated basis"):
        ledger.on_failed_fit(at="2021-01-01", job_id="j", error="diverged",
                             previous_model_id=None)


def test_an_incomplete_panel_is_missing_evidence_not_bad_performance():
    """Otherwise expensive-to-evaluate candidates look systematically worse."""
    ledger = FailureLedger(incumbent_version="pv-a")
    verdict = ledger.on_incomplete_panel(at="2021-01-01", candidate_id="c", have=2, need=6)
    assert verdict["utility"] is None
    assert verdict["counts_as_bad_performance"] is False


def test_an_out_of_order_job_cannot_activate_before_its_ready_event():
    ledger = FailureLedger(incumbent_version="pv-a")
    verdict = ledger.on_out_of_order_job(at="2021-01-01 00:00", job_id="j",
                                         ready_at="2021-01-01 06:00")
    assert verdict["may_activate_from"].startswith("2021-01-01 06:00")
    assert verdict["backdating_refused"] is True


def test_a_partial_artifact_is_refused_not_parsed(tmp_path):
    ledger = FailureLedger(incumbent_version="pv-a")
    broken = tmp_path / "half.json"
    broken.write_text('{"a": 1, "b":')
    with pytest.raises(FailureError, match="not a complete artifact"):
        ledger.read_artifact(broken, at="2021-01-01")


def test_committed_trials_survive_a_worker_failure():
    ledger = FailureLedger(incumbent_version="pv-a")
    ledger.commit_trial({"trial_id": "t1"})
    ledger.commit_trial({"trial_id": "t2"})
    verdict = ledger.on_worker_failure(at="2021-01-01", worker_id="w0", uncommitted=3)
    assert verdict["committed_trials_retained"] == 2
    assert verdict["uncommitted_lost"] == 3


def test_no_failure_resolves_by_choosing_different_parameters():
    ledger = FailureLedger(incumbent_version="pv-a")
    ledger.on_missing_or_stale_context(None, now="2021-01-01", ttl="4h")
    assert ledger.as_record()["random_parameter_selection_used"] is False
    assert set(ledger.as_record()["modes_declared"]) == set(FAILURE_MODES)


# --- L07.1 parity and the continuous account ------------------------------


def test_a_handcrafted_fill_cannot_enter_the_account():
    account = AccountState(initial_capital=1000.0)
    with pytest.raises(ContinuousError, match="handcrafted fill"):
        account.apply_fill(at="2021-01-01", side=1, quantity=1.0, price=100.0,
                           fee=0.0, source="lab")


def test_disabled_and_inert_hooks_give_the_same_path_as_the_baseline():
    """If they differ, merely ASKING the hook has a side effect.

    The three runs must actually TRADE. Comparing three accounts that never move
    is a pass that cannot fail, which is what the first version did.
    """
    frame = _bars(200).reset_index().rename(columns={"index": "time"})
    rng = np.random.default_rng(21)
    frame["signal"] = 0.0
    frame.loc[rng.choice(len(frame), 12, replace=False), "signal"] = 0.05
    report = disabled_hooks_parity(frame, initial_capital=20_000.0, signal_column="signal")
    assert report["identical"] is True
    assert report["fills_compared"] > 0, "three empty accounts agree trivially"
    for run in ("disabled", "inert"):
        assert all(report["comparisons"][run].values())


def test_a_hook_parity_over_an_account_that_never_trades_is_refused():
    frame = _bars(120).reset_index().rename(columns={"index": "time"})
    frame["signal"] = 0.0
    with pytest.raises(ContinuousError, match="three empty accounts"):
        disabled_hooks_parity(frame, initial_capital=20_000.0, signal_column="signal")
    with pytest.raises(ContinuousError, match="actually trades"):
        disabled_hooks_parity(frame, initial_capital=20_000.0)


def test_replay_of_one_event_at_a_time_equals_the_offline_replay():
    bus = EventBus()
    for hour in range(6):
        at = pd.Timestamp("2021-01-01") + pd.Timedelta(hours=hour)
        bus.publish("BAR_COMPLETED", at, close=100.0 + hour)
    report = replay_parity(bus, consume=lambda e: (e.kind, e.sequence))
    assert report["identical"] is True


def test_the_continuous_account_never_resets_across_a_parameter_switch(real_bars):
    """T56 — one engine pass, one equity curve, no splice at the boundary."""
    frame = real_bars
    params_a = {"AP": 47, "alpha.condition_threshold": 70, "coeff": 4,
                "novolumedata": False, "src_col": "close"}
    params_b = {"AP": 36, "alpha.condition_threshold": 55, "coeff": 4,
                "novolumedata": False, "src_col": "close"}
    run = run_continuous_account(
        "A-SC", frame,
        initial=VersionWindow(parameter_digest(params_a), params_a, 0, "act-0"),
        schedule=[VersionWindow(parameter_digest(params_b), params_b, len(frame) // 2, "act-1")])
    record = run.as_record()
    assert record["account_resets"] == 0
    assert record["spliced_from_independent_runs"] is False
    assert record["single_engine_pass"] is True
    assert len(run.equity) == len(frame)
    assert record["entries"] > 0 and record["fills"] > 0, (
        "an account that never traded cannot demonstrate that it was carried across a switch")
    assert record["switches_effected"] == 1, "no switch happened, so nothing was carried across"


def test_the_tape_is_built_from_the_active_adapter_at_every_bar(real_bars):
    """The defect this catches: reading the FINAL adapter's decision list.

    Each version's adapter accumulates only the bars it personally saw, so
    taking the last one's list silently drops every trade made under an earlier
    version -- while the entry counter still counts them. The symptom is a run
    reporting far more entries than fills.
    """
    frame = real_bars
    params_a = {"AP": 47, "alpha.condition_threshold": 70, "coeff": 4,
                "novolumedata": False, "src_col": "close"}
    params_b = {"AP": 30, "alpha.condition_threshold": 35, "coeff": 7,
                "novolumedata": False, "src_col": "close"}
    run = run_continuous_account(
        "A-SC", frame,
        initial=VersionWindow("pv-a", params_a, 0, "act-0"),
        schedule=[VersionWindow("pv-b", params_b, len(frame) // 2, "act-1")])
    assert run.diagnostics["tape_rows"] == len(frame)
    # NOT `if run.entries:` -- that guard made this whole test vacuous on the
    # synthetic fixture, which produced zero entries. The defect it exists to
    # catch is only visible when trades exist under BOTH versions.
    assert run.entries > 0, "no trade happened, so the tape could not be missing one"
    assert len(run.fills) >= run.entries, (
        f"{run.entries} entries produced only {len(run.fills)} fills: the tape is missing "
        "the bars traded under an earlier parameter version")
    versions_that_traded = {run.version_by_bar[int(f["bar_index"])] for f in run.fills}
    assert len(versions_that_traded) > 1, (
        "every fill belongs to one version, so this run cannot show that an earlier version's "
        "trades survive in the tape")


def test_a_switch_waits_for_a_flat_book_and_records_what_it_cost(real_bars):
    frame = real_bars
    params_a = {"AP": 20, "alpha.condition_threshold": 40, "coeff": 5,
                "novolumedata": False, "src_col": "close"}
    params_b = {"AP": 58, "alpha.condition_threshold": 80, "coeff": 1,
                "novolumedata": False, "src_col": "close"}
    run = run_continuous_account(
        "A-SC", frame,
        initial=VersionWindow("pv-a", params_a, 0, "act-0"),
        schedule=[VersionWindow("pv-b", params_b, len(frame) // 2, "act-1")])
    switch = run.switches[0]
    required = run.as_record()["warm_bar_requirements"]["act-1"]["required_warm_bars"]
    assert switch.effective_at_bar is not None, "the switch never landed; nothing was measured"
    assert switch.effective_at_bar >= switch.requested_at_bar + required, (
        "a version may not take effect before its own declared warmup has elapsed")
    assert switch.warm_bars_at_activation >= required


# --- OUT.2 the binding map ------------------------------------------------


def test_every_integration_point_binds_to_a_symbol_that_exists():
    mapping = build_binding_map()
    assert mapping["installed_version"] == "1.1.1"
    for name, binding in mapping["bindings"].items():
        assert binding["status"] == "BOUND", f"{name}: {binding['error']}"


def test_an_unresolvable_hook_is_a_blocker_not_a_reroute():
    """A reroute SUCCEEDS, which is exactly why it is the dangerous failure."""
    mapping = build_binding_map()
    assert "never rerouted" in mapping["reroute_policy"]
    assert "engine_fill_trace_native" in mapping["known_blockers"]


# --- artifacts ------------------------------------------------------------


@pytest.fixture(scope="module")
def trace(lab_root):
    path = lab_root / "configs" / "lab07_continuous_trace.json"
    if not path.is_file():
        pytest.skip("run scripts/run_lab07.py")
    return json.loads(path.read_text())


def test_the_integration_reproduces_the_canonical_baseline_when_idle(trace):
    parity = trace["integration_baseline_parity"]
    assert parity["identical"] is True
    assert all(parity["surfaces"].values()), parity["surfaces"]
    assert parity["canonical_fills"] == parity["integrated_fills"] > 0, (
        "a parity that compares two empty fill lists proves nothing")


def test_the_run_actually_traded(trace):
    """Guards against every gate below passing on a flat account."""
    account = trace["continuous_account"]
    assert account["fills"] > 0 and account["entries"] > 0
    assert account["final_equity"] != account["initial_equity"]


def test_every_switch_records_the_delay_it_cost(trace):
    switches = trace["continuous_account"]["switches"]
    assert switches, "no activation occurred; the migration contract is untested here"
    for switch in switches:
        if switch["effective_at_bar"] is not None:
            assert switch["effective_at_bar"] >= switch["requested_at_bar"]
            assert switch["blocked_bars"] >= 0


def test_refit_latency_is_measured_and_never_zero(trace):
    jobs = trace["training_jobs"]
    assert jobs["benchmark"]["source"] == "measured_benchmark"
    assert jobs["benchmark"]["measured_seconds_per_fit"] > 0
    assert jobs["zero_latency_jobs"] == 0
    assert jobs["min_delay_seconds"] > 0


def test_all_nine_failure_modes_were_exercised(trace):
    failures = trace["failures"]
    assert failures["modes_never_exercised"] == [], failures["modes_never_exercised"]
    assert len(failures["modes_exercised"]) == len(FAILURE_MODES)


def test_the_prefix_holds_when_the_future_is_replaced(trace):
    prefix = trace["prefix_stability"]
    assert prefix["suffix_actually_changed"] is True, (
        "the mutation changed nothing, so 'the prefix held' is trivially true")
    assert prefix["prefix_survives_future_mutation"] is True
    assert prefix["prefix_matches_longer_run"] is True
    assert prefix["entries_in_prefix"] > 0, (
        "no trade happened before the cutoff, so nothing was actually at risk of leaking")


@pytest.fixture(scope="module")
def segments(lab_root):
    path = lab_root / "configs" / "operational_segments.json"
    if not path.is_file():
        pytest.skip("run scripts/run_lab07.py")
    return json.loads(path.read_text())


def test_the_open_segment_has_a_null_end(segments):
    assert segments["open"] == 1
    assert segments["open_segment_has_null_end"] is True
    open_segments = [s for s in segments["segments"] if s["is_open"]]
    assert open_segments[0]["length_days"] is None


def test_segment_sharpes_are_diagnostic_and_the_daily_account_is_primary(segments):
    """T55 with the measured gap, not an assertion that one exists."""
    report = segments["daily_account_comparison"]
    assert report["primary_is_the_daily_account"] is True
    assert len(set(report["segment_day_counts"])) > 1
    if report["unweighted_mean_of_segment_sharpes"] is not None:
        assert report["account_daily_sharpe"] is not None


def test_no_decision_carried_a_future_segment_length(segments):
    assert segments["future_length_guard"]["clean"] is True


# --- leakage audit: properties added after the first pass -----------------


def test_the_exit_fixed_point_is_verified_not_assumed():
    """`run_candidate` iterates its exits to a fixed point; so must this.

    A single forward pass schedules protective exits from a per-trade oracle.
    The whole-window engine run can disagree once positions interact, and an
    unverified disagreement means the adapter was driven by exits the account
    never got. A-SC rests no protective orders so it converges trivially --
    which is exactly why this is checked on an alpha that does.
    """
    frame = _bars(600)
    params = {"AP": 47, "alpha.condition_threshold": 70, "coeff": 4,
              "novolumedata": False, "src_col": "close"}
    run = run_continuous_account(
        "A-SC", frame, initial=VersionWindow("pv-a", params, 0, "act-0"), schedule=[])
    record = run.as_record()
    assert record["exit_fixed_point_converged"] is True
    assert record["sweeps"] >= 1
    assert record["protective_exits"] == record["applied_exit_count"]


def test_the_fixed_point_holds_on_an_alpha_that_rests_protective_orders(lab_root):
    """A-HMA rests stops and targets, so the oracle actually fires here."""
    from crypto_regime_lab.experiments.evaluator import run_candidate

    baseline = json.loads((lab_root / "configs" / "lab04_calendar_baseline.json").read_text())
    cell = next((c for c in baseline["cells"]
                 if c["alpha_id"] == "A-HMA" and c["symbol"] == "BTCUSDT"), None)
    if cell is None or cell["status"] != "RUN":
        pytest.skip("no A-HMA cell in the LAB-04 evidence")
    params = cell["folds"][0]["cutoff_evidence"]["arm_A"]["params"]
    frame = _bars(1500, seed=11, freq="1h")

    reference = run_candidate("A-HMA", params, frame)
    run = run_continuous_account(
        "A-HMA", frame, initial=VersionWindow("pv-h", params, 0, "act-0"), schedule=[])
    record = run.as_record()
    assert record["exit_fixed_point_converged"] is True
    assert len(run.fills) == len(reference.fills), (
        "the integration and run_candidate disagree on an alpha with resting protection")
    if record["protective_exits"]:
        assert record["protective_exits"] == record["applied_exit_count"]


def test_the_warm_requirement_is_the_adapters_own_declaration(lab_root):
    """A hardcoded warm constant is an unregistered free parameter, and it moves results.

    Measured on this cell: 0 / derived / 512 bars give +0.45% / +0.45% / -3.07%.
    The alpha already declares how many bars it refuses to trade without, so the
    switching policy uses that rather than a number someone picked.
    """
    frame = _bars(900, seed=5)
    params_a = {"AP": 20, "alpha.condition_threshold": 40, "coeff": 5,
                "novolumedata": False, "src_col": "close"}
    params_b = {"AP": 57, "alpha.condition_threshold": 80, "coeff": 2,
                "novolumedata": False, "src_col": "close"}
    window = VersionWindow("pv-b", params_b, 400, "act-1")
    assert window.required_warm_bars is None, "the default must be DERIVE, not a constant"
    run = run_continuous_account(
        "A-SC", frame, initial=VersionWindow("pv-a", params_a, 0, "act-0"),
        schedule=[window])
    requirement = run.as_record()["warm_bar_requirements"]["act-1"]
    assert requirement["source"] == "derived_from_adapter_warmup_bars"
    assert requirement["required_warm_bars"] == params_b["AP"] + 3, (
        "A-SC declares warmup_bars() = AP + 3; the switching policy must use that number")


def test_the_warmup_gate_is_reported_as_a_delay_not_an_accuracy_claim():
    """A-SC precomputes its indicators causally over the whole slice.

    The values at bar t are therefore already correct when the shadow adapter is
    built, so waiting does not make them more correct. What the gate buys is that
    the new version has been running on live bars for at least as long as it
    declares it needs. Saying otherwise would overstate what the delay achieves.
    """
    frame = _bars(600)
    params = {"AP": 47, "alpha.condition_threshold": 70, "coeff": 4,
              "novolumedata": False, "src_col": "close"}
    run = run_continuous_account(
        "A-SC", frame, initial=VersionWindow("pv-a", params, 0, "act-0"), schedule=[])
    semantics = run.as_record()["warmup_gate_semantics"]
    assert "policy delay" in semantics
    assert "already correct" in semantics


def test_regime_observations_on_the_stream_reach_no_decision_in_a_calendar_arm():
    """Guide 10.1 arm A uses NO regime information, yet L07.2 puts observations on the stream."""
    from crypto_regime_lab.integration.events import regime_information_isolation

    bus = EventBus()
    for hour in range(20):
        at = pd.Timestamp("2021-01-01", tz="UTC") + pd.Timedelta(hours=hour)
        bus.publish("REGIME_OBSERVATION_READY", at, state_id=hour % 3)
    bus.publish("PARAMETER_ACTIVATED", "2021-01-02", parameter_version="pv-b",
                activation_id="act-1")

    clean = regime_information_isolation(bus.ordered(), arm="A",
                                         activation_sources={"act-1": "calendar_cutoff"})
    assert clean["clean"] is True
    assert clean["regime_information_reached_a_decision"] is False
    assert clean["regime_observations_on_the_stream"] == 20

    dirty = regime_information_isolation(bus.ordered(), arm="A",
                                         activation_sources={"act-1": "regime_observation"})
    assert dirty["clean"] is False
    assert dirty["activations_not_from_the_calendar"][0]["activation_id"] == "act-1"


def test_an_unattributed_activation_is_not_treated_as_a_calendar_one():
    from crypto_regime_lab.integration.events import regime_information_isolation

    bus = EventBus()
    bus.publish("PARAMETER_ACTIVATED", "2021-01-02", parameter_version="pv-b",
                activation_id="act-mystery")
    verdict = regime_information_isolation(bus.ordered(), arm="A", activation_sources={})
    assert verdict["clean"] is False
    assert verdict["activation_sources"]["act-mystery"] == "UNATTRIBUTED"


def test_the_future_mutation_covers_every_input_the_alpha_can_read(trace):
    """A-SC feeds volume into an MFI, so a price-only mutation would miss it."""
    prefix = trace["prefix_stability"]
    assert set(prefix["columns_mutated"]) >= {"open", "high", "low", "close", "volume"}
    assert prefix["suffix_actually_changed"] is True
    assert prefix["prefix_survives_future_mutation"] is True


def test_the_run_records_that_regime_information_reached_nothing(trace):
    isolation = trace["regime_information_isolation"]
    assert isolation["clean"] is True
    assert isolation["regime_information_reached_a_decision"] is False
    assert isolation["regime_observations_on_the_stream"] > 0, (
        "no observations on the stream means this proves nothing")
    assert set(isolation["activation_sources"].values()) == {"calendar_cutoff"}


def test_the_run_stays_inside_the_development_role(trace, lab_root):
    eligibility = json.loads((lab_root / "configs" / "data_eligibility.json").read_text())
    roles = eligibility["data_roles"]
    start, end = (pd.Timestamp(x) for x in trace["window"])
    assert start >= pd.Timestamp(roles["development"]["start"])
    assert end <= pd.Timestamp(roles["development"]["end"])
    assert end < pd.Timestamp(roles["outer_evaluation"]["start"]), (
        "LAB-07 touched the outer evaluation holdout")


def test_every_version_was_requested_at_or_after_the_cutoff_that_selected_it(trace, lab_root):
    """The schedule comes from LAB-04, so its causality has to be re-checked here."""
    baseline = json.loads((lab_root / "configs" / "lab04_calendar_baseline.json").read_text())
    cell = next(c for c in baseline["cells"]
                if c["alpha_id"] == trace["alpha_id"] and c["symbol"] == trace["symbol"])
    for fold, switch in zip(cell["folds"][1:], trace["continuous_account"]["switches"]):
        train_end = pd.Timestamp(fold["cutoff_evidence"]["train_end"])
        cutoff = pd.Timestamp(fold["cutoff"])
        assert train_end <= cutoff, (
            f"fold {fold['fold']} trained past its own cutoff")
        assert switch["effective_at_bar"] >= switch["requested_at_bar"], (
            "a version took effect before it was requested")


def test_the_bus_orders_a_stream_that_mixes_naive_and_aware_timestamps():
    """One naive timestamp would otherwise raise on the first sort.

    The bus is fed by subsystems that disagree about tz-awareness: storage is
    naive UTC by convention, engine frames are aware. A TypeError at sort time
    would take down the ordering of the whole stream, so the coercion happens at
    publish and the convention is stated rather than inherited.
    """
    bus = EventBus()
    bus.publish("BAR_COMPLETED", "2021-01-01 00:00", close=1.0)                    # naive
    bus.publish("BAR_COMPLETED", pd.Timestamp("2021-01-01 01:00", tz="UTC"), close=2.0)
    bus.publish("BAR_COMPLETED", pd.Timestamp("2021-01-01 03:00", tz="Asia/Tokyo"), close=3.0)
    ordered = bus.ordered()
    assert len(ordered) == 3
    assert all(e.observed_at.tzinfo is not None for e in ordered)
    assert [str(e.observed_at) for e in ordered] == sorted(str(e.observed_at) for e in ordered)
    assert "interpreted as UTC" in bus.as_record()["timestamp_convention"]


# --- T57: the optimizer's scheduling contract -----------------------------


def test_t57_the_sequencing_contract_is_declared(lab_root):
    """Guide 10.5 + [S10]: sequential and adaptive batch have different semantics.

    The first version of this coverage cited three tests about refit latency
    rounding, which have nothing to do with T57. A requirement marked COVERED by
    tests that do not test it is worse than one marked NOT_YET_IMPLEMENTED,
    because the gap stops being visible.
    """
    path = lab_root / "configs" / "compute_budget_registration.json"
    if not path.is_file():
        pytest.skip("run scripts/register_compute_budget.py")
    rule = json.loads(path.read_text())["sequencing_rule"]
    assert "deterministic sequential schedule" in rule
    assert "fixed candidate matrix" in rule
    assert "never reported as the same sequence" in rule


def test_t57_the_primary_search_is_a_fixed_matrix_that_actually_reproduces(lab_root):
    """The contract allows two options; this checks which one was taken, from evidence."""
    path = lab_root / "configs" / "lab04_cutoff_reproducibility.json"
    if not path.is_file():
        pytest.skip("run scripts/verify_cell_reproducibility.py")
    record = json.loads(path.read_text())
    assert record["reproduced"] is True
    assert record["probe_design_unchanged"] is True
    assert record["probe_design_digest"] == record["stored_probe_design_digest"]
    for check in record["checks"]:
        assert check["reproduced"] is True
        assert check["same_selected_params"] is True
        assert check["same_point_id"] is True, (
            "a replay that picks a different point is not a reproducible schedule")
        assert check["same_candidate_pool_size"] is True


def test_t57_the_design_is_seeded_not_sampler_dependent(lab_root):
    """A fixed matrix must not depend on process-local ordering to reproduce."""
    path = lab_root / "configs" / "lab04_probe_designs.json"
    if not path.is_file():
        pytest.skip("run scripts/run_lab04.py")
    designs = json.loads(path.read_text())
    assert isinstance(designs["seed"], int)
    determinism = designs["determinism"]
    assert "sha256" in determinism and "sorted" in determinism, (
        "PYTHONHASHSEED-salted hashing or unsorted set iteration would make the 'fixed' matrix "
        "differ between processes")


def test_t57_exactly_one_schedule_type_is_declared_for_the_primary_comparison(lab_root):
    """Structural, because a lexical scan cannot tell a claim from a denial of one.

    Two earlier versions of this test grepped prose: the first flagged four files
    whose only mention of "adaptive batch" was T57's own title, the second
    flagged the checklist's own NEGATION of the forbidden claim. Tuning the
    regex until it passes is the failure this whole audit keeps finding, so the
    property is checked on structured fields instead.

    Guide 10.5 permits one of two schedules for the primary comparison. The
    lab must declare which, once, and the reproducibility evidence must be for
    that same one.
    """
    budget = json.loads(
        (lab_root / "configs" / "compute_budget_registration.json").read_text())
    rule = budget["sequencing_rule"]
    permitted = ["deterministic sequential schedule", "fixed candidate matrix"]
    assert all(option in rule for option in permitted), (
        "the rule must name both permitted schedules so the choice between them is visible")

    designs = json.loads((lab_root / "configs" / "lab04_probe_designs.json").read_text())
    reproducibility = json.loads(
        (lab_root / "configs" / "lab04_cutoff_reproducibility.json").read_text())
    # the schedule actually taken is the fixed matrix: a pinned seed, a design
    # digest, and a replay that lands on the same point
    assert isinstance(designs["seed"], int)
    assert reproducibility["probe_design_unchanged"] is True
    assert reproducibility["reproduced"] is True
    assert all(c["same_point_id"] for c in reproducibility["checks"]), (
        "the fixed matrix must replay to the same decision, or it is not fixed")


def test_the_regime_publication_lag_matches_the_emission_contract(trace, lab_root):
    """A false availability on the tape is a leak waiting to be inherited.

    Bars are left-labelled (guide 6.3), so a 4h observation stamped 00:00 covers
    00:00-04:00 and is knowable only at 04:00 — which is exactly what LAB-05's
    emission tape records. The first version published it at +1 minute, 15x too
    early. Nothing consumes it in this calendar arm, but LAB-08's arms C/D/E
    will.
    """
    from crypto_regime_lab.data.panel import REGIME_INTERVAL

    expected = pd.Timedelta(REGIME_INTERVAL).total_seconds()
    assert trace["regime_publication_lag_seconds"] == expected

    tapes = sorted((lab_root / "evidence").rglob("emission_tape.json"))
    emission = None
    for tape in reversed(tapes):
        document = json.loads(tape.read_text())
        if document.get("emissions"):
            emission = document["emissions"][0]
            break
    if emission is None:
        pytest.skip("no LAB-05 emission tape with records")
    lab05_lag = (pd.Timestamp(emission["available_at"])
                 - pd.Timestamp(emission["observed_at"])).total_seconds()
    assert lab05_lag == expected, (
        f"LAB-05 publishes a regime observation {lab05_lag}s after the stamp; LAB-07 uses "
        f"{expected}s. The two must agree or one of them is claiming a false availability")


def test_exercised_failure_modes_are_not_reported_as_observed(trace):
    """A driven handler and an observed failure are different claims."""
    failures = trace["failures"]
    assert failures["observed_during_the_run"] == []
    assert "does NOT mean the failure occurred" in failures["exercised_means"]
    assert failures["modes_never_exercised"] == []


def test_the_parity_metrics_surface_is_more_than_final_equity(trace):
    """Guide 13.6 forbids equal final equity as a standalone parity claim."""
    parity = trace["integration_baseline_parity"]
    assert set(parity["canonical_metrics"]) >= {
        "total_return", "daily_sharpe", "max_drawdown", "daily_observations", "final_equity"}
    assert parity["canonical_metrics"] == parity["integrated_metrics"]
    assert parity["surfaces"]["metrics"] is True


def test_the_parity_selection_surface_runs_the_switching_machinery(trace):
    """Counting a constant would be trivially true with an empty schedule."""
    parity = trace["integration_baseline_parity"]
    assert "no-op" in parity["selection_surface_is"]
    assert parity["no_op_switch_fills"] == parity["canonical_fills"] > 0
    assert parity["surfaces"]["selection"] is True


def test_activation_sources_are_derived_from_the_tape_not_supplied(trace):
    """The first version was handed the answer it then checked."""
    isolation = trace["regime_information_isolation"]
    assert "not supplied by the caller" in isolation["attribution"]
    assert set(isolation["activation_sources"].values()) == {"calendar_cutoff"}


def test_attribution_uses_the_request_time_not_the_effective_time():
    """One activation's effective bar lands on a 4h observation by coincidence."""
    from crypto_regime_lab.integration.events import attribute_activation_sources

    bus = EventBus()
    cutoff = pd.Timestamp("2021-06-30", tz="UTC")
    effective = pd.Timestamp("2021-07-02 04:00", tz="UTC")
    bus.publish("REGIME_OBSERVATION_READY", effective, state_id=1)
    bus.publish("PARAMETER_ACTIVATED", effective, activation_id="act-1",
                parameter_version="pv-b", requested_at=str(cutoff))
    sources = attribute_activation_sources(bus.ordered(), calendar_cutoffs=[cutoff])
    assert sources["act-1"] == "calendar_cutoff", (
        "attributing on the effective time would call this regime-driven purely because the "
        "activation happened to land on an observation")

    bus2 = EventBus()
    bus2.publish("PARAMETER_ACTIVATED", effective, activation_id="act-2",
                 parameter_version="pv-b")
    assert attribute_activation_sources(
        bus2.ordered(), calendar_cutoffs=[cutoff])["act-2"] == "UNATTRIBUTED_NO_REQUEST_TIME"


def test_every_engine_fill_uses_the_one_fill_shape(real_bars):
    """`f.get("quantity", 0.0)` on a fill whose key is `qty` compared 0.0 with 0.0.

    Two runs with different fill sizes would have matched. The same key-name slip
    had already been found once in the replay consumer, which is why the lab now
    has ONE fill shape and a missing field raises. Checked on behaviour, not on
    the source text -- a docstring that explains the bug contains the string.
    """
    params = {"AP": 47, "alpha.condition_threshold": 70, "coeff": 4,
              "novolumedata": False, "src_col": "close"}
    run = run_continuous_account(
        "A-SC", real_bars, initial=VersionWindow("pv-a", params, 0, "act-0"), schedule=[])
    assert run.fills, "no fills, so this checks nothing"
    for fill in run.fills:
        assert "qty" in fill and "quantity" not in fill, (
            "the lab must have one fill shape; two is how the default came to hide")
        assert float(fill["qty"]) != 0.0, "a zero-quantity fill would hide the defect again"


def test_a_fill_missing_a_field_is_refused_rather_than_defaulted():
    """The guard itself, driven with a fill that lacks the field."""
    from crypto_regime_lab.integration.continuous_account import (
        ContinuousAccountError,
        fills_key,
    )

    complete = {"bar_index": 3, "qty": 0.5, "price": 100.0, "side": 1, "reason": "entry"}
    assert fills_key([complete]) == [(3, "entry", 1, 100.0, 0.5)]
    # different quantities must produce different keys -- the whole point
    bigger = {**complete, "qty": 0.9}
    assert fills_key([complete]) != fills_key([bigger])

    for field in ("bar_index", "qty", "price", "side", "reason"):
        with pytest.raises(ContinuousAccountError, match="missing"):
            fills_key([{k: v for k, v in complete.items() if k != field}])


def test_the_account_state_records_the_same_key_as_the_engine():
    from crypto_regime_lab.integration.continuous import AccountState

    account = AccountState(initial_capital=1000.0)
    record = account.apply_fill(at="2021-01-01", side=1, quantity=0.25, price=100.0,
                                fee=0.04, source="engine")
    assert "qty" in record and record["qty"] == 0.25
    assert "quantity" not in record
