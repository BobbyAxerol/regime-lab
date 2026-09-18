#!/usr/bin/env python
"""LAB-07 — continuous regime-aware WFO integration, end to end.

Runs the integration on the same cell LAB-06 used (A-SC / BTCUSDT, development
role) and writes every artifact the phase owes. Nothing here re-estimates a
LAB-04/05/06 result; this phase asks whether those results can be DELIVERED on
one continuous account without leakage, resets or handcrafted fills.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data.panel import REGIME_INTERVAL as P_REGIME_INTERVAL  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.integration.activation import (  # noqa: E402
    ActivationTape,
    IndicatorState,
    OpenCampaign,
    ProtectiveOrder,
    parameter_digest,
)
from crypto_regime_lab.integration.binding import build_binding_map  # noqa: E402
from crypto_regime_lab.integration.continuous import (  # noqa: E402
    ContinuousRun,
    HookSet,
    disabled_hooks_parity,
    replay_parity,
)
from crypto_regime_lab.integration.continuous_account import (  # noqa: E402
    VersionWindow,
    integration_baseline_parity,
    run_continuous_account,
)
from crypto_regime_lab.integration.events import (  # noqa: E402
    assert_no_future_activation_end,
    attribute_activation_sources,
    regime_information_isolation,
)
from crypto_regime_lab.integration.failures import FailureLedger  # noqa: E402
from crypto_regime_lab.integration.jobs import RefitBenchmark, TrainingJobRunner  # noqa: E402
from crypto_regime_lab.quantbt_bridge.parity import parity_report  # noqa: E402
from crypto_regime_lab.regime.causality import causal_fit  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SYMBOL = "BTCUSDT"
ALPHA = "A-SC"
DEV_START, DEV_END = "2021-01-01", "2023-12-31"
DECISION_INTERVAL = "15min"            # guide 10.4: A-SC's registered primary
#: A regime observation is knowable only once its own bar has completed. Bars are
#: left-labelled, so that is one full regime interval after the stamp -- exactly
#: what LAB-05's emission tape records as available_at.
REGIME_PUBLICATION_LAG = pd.Timedelta(P_REGIME_INTERVAL)
INITIAL_CAPITAL = 20_000.0


def load_bars() -> pd.DataFrame:
    """Real OHLCV at A-SC's REGISTERED primary decision interval (guide 10.4: 15m).

    The 4h feature panel would have been cheaper and would have made every gate
    below pass on a flat account. An integration that never trades cannot
    demonstrate a carried account, a segment boundary or a fill that came from
    the engine, so the bars have to be the ones the alpha actually decides on.
    """
    from crypto_regime_lab.data import panel as P

    manifest = json.loads((LAB_ROOT / "snapshots" / "server_core_v1"
                           / "manifest.json").read_text())
    frame = P.load_resampled(LAB_ROOT / "snapshots" / "server_core_v1",
                             "crypto_binance_futures_1m", SYMBOL, DECISION_INTERVAL,
                             manifest=manifest)
    if frame["time"].dt.tz is None:
        frame["time"] = frame["time"].dt.tz_localize("UTC")
    frame = frame.set_index("time").sort_index()
    return frame[(frame.index >= f"{DEV_START} 00:00:00+00:00")
                 & (frame.index <= f"{DEV_END} 23:59:59+00:00")]


def deployed_schedule(bars: pd.DataFrame) -> tuple[VersionWindow, list[VersionWindow]]:
    """The activation schedule is arm A's OWN LAB-04 selections, not invented points.

    LAB-04 evaluated each fold as an independent window. The question LAB-07 asks
    is whether those same six selections can be DELIVERED on one account that
    never restarts -- so the parameters have to be the ones LAB-04 actually
    deployed, at the cutoffs it actually deployed them.
    """
    baseline = json.loads((LAB_ROOT / "configs" / "lab04_calendar_baseline.json").read_text())
    cell = next(c for c in baseline["cells"]
                if c["alpha_id"] == ALPHA and c["symbol"] == SYMBOL)
    windows: list[VersionWindow] = []
    for fold in cell["folds"]:
        arm_a = fold.get("cutoff_evidence", {}).get("arm_A", {})
        params = arm_a.get("params")
        if not params:
            continue
        cutoff = pd.Timestamp(fold["cutoff"])
        position = int(bars.index.searchsorted(cutoff))
        if position >= len(bars):
            continue
        windows.append(VersionWindow(
            parameter_version=parameter_digest(params), params=params,
            requested_at_bar=position, activation_id=f"act-fold{fold['fold']}"))
    if not windows:
        raise RuntimeError("no arm-A selections found; LAB-04 evidence is required here")
    return windows[0], windows[1:]


def measure_refit_latency(bars: pd.DataFrame) -> RefitBenchmark:
    """L07.3.4 — MEASURE a fit rather than assume a duration.

    LAB-05 recorded no per-fit timing, so a latency taken from it would be an
    invention. One real causal_fit is timed here at the same shape LAB-05 used.
    """
    rng = np.random.default_rng(17)
    raw = rng.normal(0, 1, (min(len(bars), 2190), 8))
    started = time.perf_counter()
    causal_fit(raw, cutoff=raw.shape[0] // 2, n_states=3, lambda_jump=1.0, seeds=(11, 23, 37, 51))
    elapsed = time.perf_counter() - started
    return RefitBenchmark(measured_seconds_per_fit=max(elapsed, 1e-3), workers=1,
                          source="measured_benchmark")


def build_run(bars: pd.DataFrame, decisions: list[dict], account_run) -> ContinuousRun:
    """The event stream for the same run: regime observations, activations, fills.

    Driven by two real sources at once -- the LAB-06 decision ledger supplies the
    4h regime observations and their keep/switch verdicts, and the continuous
    account supplies the activations that actually took effect and the fills the
    engine actually produced. Nothing here is synthesised.
    """
    by_time = {pd.Timestamp(d["decision_time"]): d for d in decisions}
    effective = {s.effective_at_bar: s for s in account_run.switches
                 if s.effective_at_bar is not None}
    fills_by_bar: dict[int, list[dict]] = {}
    for fill in account_run.fills:
        fills_by_bar.setdefault(int(fill["bar_index"]), []).append(fill)

    run = ContinuousRun(arm="A_calendar_on_one_account", initial_capital=INITIAL_CAPITAL,
                        hooks=HookSet(mode="ACTIVE"),
                        baseline_version=account_run.version_by_bar[0],
                        started_at=bars.index[0])
    for position, timestamp in enumerate(bars.index):
        run.bus.publish("BAR_COMPLETED", timestamp, close=float(bars["close"].iloc[position]))
        record = by_time.get(timestamp)
        if record is not None:
            # available_at comes from LAB-05's own emission contract, not from a
            # number picked here. Bars are LEFT-labelled (guide 6.3), so a 4h
            # observation stamped 00:00 covers 00:00-04:00 and is knowable only
            # at 04:00. A 1-minute delay -- the first version -- published it 15x
            # too early. Nothing consumes it in this arm, but LAB-08's arms C/D/E
            # will, and a false availability on the tape is a leak waiting to be
            # inherited.
            run.bus.publish("REGIME_OBSERVATION_READY", timestamp,
                            available_at=timestamp + REGIME_PUBLICATION_LAG,
                            decision=record["decision"], selection_id=record["selection_id"])
            if record["decision"] != "SWITCH":
                run.segments.record_no_change(trigger_id=record["selection_id"], at=timestamp,
                                              reason=record["decision"])
                run.decisions.append({"at": str(timestamp), "decision": record["decision"]})
        switch = effective.get(position)
        if switch is not None:
            # requested_at is a PAST fact at activation, so it is carried; the
            # attribution needs it because an activation's effective time is
            # neither a cutoff nor an observation, and one of them here lands on
            # a 4h observation purely by coincidence
            run.bus.publish("PARAMETER_ACTIVATED", timestamp,
                            parameter_version=switch.parameter_version,
                            activation_id=switch.activation_id,
                            requested_at=str(bars.index[switch.requested_at_bar]))
            run.segments.record_activation(activation_id=switch.activation_id,
                                           parameter_version=switch.parameter_version,
                                           at=timestamp)
        for fill in fills_by_bar.get(position, []):
            run.bus.publish("ENGINE_FILL", timestamp, **{k: v for k, v in fill.items()
                                                         if k != "bar_index"})
        run.selections.append(run.segments.open_segment().parameter_version)
    return run


def exercise_failures(ledger: FailureLedger, now: pd.Timestamp) -> None:
    """Every declared failure mode is EXERCISED, not merely declared (L07.6)."""
    ledger.on_missing_or_stale_context(None, now=now, ttl="8h")
    ledger.on_missing_or_stale_context(
        {"available_at": now - pd.Timedelta("2D")}, now=now, ttl="8h")
    ledger.on_failed_fit(at=now, job_id="job-fail", error="did not converge",
                         previous_model_id="jm_k3_2023-12-28")
    ledger.on_incomplete_panel(at=now, candidate_id="cand-7", have=2, need=6)
    ledger.on_out_of_order_job(at=now, job_id="job-late", ready_at=now + pd.Timedelta("4h"))
    ledger.on_simulation_reject(at=now, order_id="ord-1", reason="insufficient margin")
    ledger.on_liquidation(at=now, campaign_id="camp-liq", equity_after=11_842.0)
    ledger.commit_trial({"trial_id": "t-1", "objective": -0.12})
    ledger.commit_trial({"trial_id": "t-2", "objective": 0.04})
    ledger.on_worker_failure(at=now, worker_id="w-0", uncommitted=1)
    broken = LAB_ROOT / ".cache" / "interrupted_artifact.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text('{"partial": tru')          # a write that died mid-flush
    try:
        ledger.read_artifact(broken, at=now)
    except Exception:
        pass
    broken.unlink(missing_ok=True)


def build_activation_tape(bars: pd.DataFrame, account_run) -> ActivationTape:
    """L07.4 / OUT.5 — the activation tape of the REAL continuous account.

    Every row here is an activation the account actually performed, with the
    delay it actually incurred. The contract exercises that follow (blocked by an
    open campaign, blocked by cold indicators, retirement while orders are live)
    are appended as NAMED exercises so the tape shows the paths that did not
    occur in this run as well as the ones that did -- a contract only tested by
    the happy path is a contract nobody has tested.
    """
    tape = ActivationTape(max_campaign_age_days=30.0)
    versions = list(dict.fromkeys(account_run.version_by_bar))
    required = {switch.parameter_version: switch.warm_bars_at_activation or 0
                for switch in account_run.switches}
    for index, version in enumerate(versions):
        bars_needed = required.get(version, 0)
        tape.register_indicator(IndicatorState(parameter_version=version,
                                               required_bars=bars_needed,
                                               warm_bars=bars_needed if index == 0 else 0))
    tape.active_version = versions[0]

    for switch in account_run.switches:
        requested = bars.index[switch.requested_at_bar]
        activation = tape.request(switch.activation_id, f"sel-{switch.activation_id}",
                                  switch.parameter_version, requested)
        if switch.effective_at_bar is not None:
            state = tape.indicators[switch.parameter_version]
            state.observe(state.required_bars)
            activation.activated_at = bars.index[switch.effective_at_bar]
            activation.blocked_reason = None
            tape.active_version = switch.parameter_version
        else:
            activation.blocked_reason = switch.blocked_reason

    _exercise_migration_contract(tape, bars)
    return tape


def _exercise_migration_contract(tape: ActivationTape, bars: pd.DataFrame) -> None:
    """Drive the guide 9.5 paths this particular run did not happen to hit."""
    incumbent = parameter_digest({"cid": "contract_incumbent"})
    challenger = parameter_digest({"cid": "contract_challenger"})
    saved_active = tape.active_version
    tape.active_version = incumbent
    tape.register_indicator(IndicatorState(parameter_version=incumbent, required_bars=30,
                                           warm_bars=30))
    cold = tape.register_indicator(IndicatorState(parameter_version=challenger, required_bars=30))

    first = bars.index[0]
    campaign = tape.register_campaign(OpenCampaign(
        campaign_id="contract-camp", entry_parameter_digest=incumbent, opened_at=first,
        protective_orders=[ProtectiveOrder(order_id="sl-contract", kind="stop",
                                          parameter_version=incumbent, price=28_000.0)]))

    # 1. requested while a campaign is open -> blocked, by design
    blocked = tape.request("contract-open", "sel-open", challenger, first + pd.Timedelta("4h"))
    tape.try_activate(blocked, first + pd.Timedelta("4h"))

    # 2. the campaign reaches terminal on its own terms; never forced for a switch
    campaign.close(first + pd.Timedelta("3D"), reason="take_profit")

    # 3. now blocked only by cold indicators
    cold_try = tape.request("contract-cold", "sel-cold", challenger, first + pd.Timedelta("3D"))
    tape.try_activate(cold_try, first + pd.Timedelta("3D"))

    # 4. warm, then activate; the delay is whatever the contract cost
    cold.observe(30)
    warm = tape.request("contract-warm", "sel-warm", challenger, first + pd.Timedelta("3D"))
    tape.try_activate(warm, first + pd.Timedelta("3D") + pd.Timedelta("4h"))

    # 5. a trigger that changes nothing is still recorded
    tape.request("contract-nochange", "sel-nochange", tape.active_version,
                 first + pd.Timedelta("5D"))
    tape.active_version = saved_active


def _fold_cutoffs() -> list:
    """The calendar cutoffs LAB-04 declared, read from its own evidence."""
    baseline = json.loads((LAB_ROOT / "configs" / "lab04_calendar_baseline.json").read_text())
    cell = next(c for c in baseline["cells"]
                if c["alpha_id"] == ALPHA and c["symbol"] == SYMBOL)
    return [f["cutoff"] for f in cell["folds"]]


def _decision_of(event) -> tuple:
    """What a consumer would DO with this event, so replay parity tests decisions.

    Reading the event's own fields back would pass on any tape at all. The
    consumer has to derive something: which parameter version is in force, and
    whether this event changes it.
    """
    if event.kind == "PARAMETER_ACTIVATED":
        return ("switch_to", event.payload.get("parameter_version"), event.sequence)
    if event.kind == "REGIME_OBSERVATION_READY":
        return ("assess", event.payload.get("decision"), event.sequence)
    if event.kind == "ENGINE_FILL":
        # `qty`, not `quantity`: the engine's own key. `.get("quantity", 0.0)`
        # returned 0.0 for every fill and the consumer looked like it was
        # reading the account when it was reading a default.
        if "qty" not in event.payload:
            raise KeyError(f"ENGINE_FILL at {event.observed_at} has no 'qty'; the consumer would "
                           f"silently read a default. payload keys: {sorted(event.payload)}")
        return ("account_moves", round(float(event.payload["qty"]), 12),
                round(float(event.payload["price"]), 8), event.sequence)
    return ("observe", event.kind, event.sequence)


def account_prefix_stability(bars: pd.DataFrame, initial: VersionWindow,
                             schedule: list[VersionWindow]) -> dict:
    """L07.7 on the REAL account: mutate the future, require the past unchanged.

    Running the hookless stub here would have proved only that a run with no
    decisions is causal. What has to hold is that the run WITH activations,
    fills and an open campaign produces bit-identical equity and versions over
    the prefix when everything after the cutoff is replaced.
    """
    cutoff = len(bars) // 2
    mutated = bars.copy()
    tail = mutated.index[cutoff:]
    # EVERY column the adapter can read, not just prices. A-SC feeds volume into
    # an MFI, so leaving volume untouched would let a strategy that read the
    # future through volume pass this probe.
    mutated_columns = [c for c in ("open", "high", "low", "close", "volume")
                       if c in mutated.columns]
    for column in mutated_columns:
        mutated.loc[tail, column] = mutated.loc[tail, column] * 5.0
    suffix_changed = all(
        not bars[column].iloc[cutoff:].equals(mutated[column].iloc[cutoff:])
        for column in mutated_columns)

    def keep(windows: list[VersionWindow], limit: int) -> list[VersionWindow]:
        return [w for w in windows if w.requested_at_bar < limit]

    full = run_continuous_account(ALPHA, bars, initial=initial, schedule=schedule)
    after = run_continuous_account(ALPHA, mutated, initial=initial, schedule=schedule)
    short = run_continuous_account(ALPHA, bars.iloc[:cutoff], initial=initial,
                                   schedule=keep(schedule, cutoff))

    def equity(run, upto):
        return [round(float(v), 8) for v in run.equity[:upto]]

    return {
        "schema": "crypto_regime_lab.account_prefix_stability.v1",
        "cutoff_bar": int(cutoff),
        "suffix_actually_changed": bool(suffix_changed),
        "columns_mutated": mutated_columns,
        "prefix_survives_future_mutation": bool(
            equity(full, cutoff) == equity(after, cutoff)
            and full.version_by_bar[:cutoff] == after.version_by_bar[:cutoff]),
        "prefix_matches_longer_run": bool(
            equity(short, len(short.equity)) == equity(full, len(short.equity))
            and short.version_by_bar == full.version_by_bar[:len(short.version_by_bar)]),
        "entries_in_prefix": int(sum(1 for f in full.fills if int(f["bar_index"]) < cutoff)),
        "rule": ("the account carries an open position across the cutoff, so this is the run "
                 "where a leak would actually show: replacing every price after the cutoff must "
                 "leave the equity and the active version bit-identical before it"),
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    bars = load_bars()
    ledger_doc = json.loads((LAB_ROOT / "configs" / "lab06_decision_ledger.json").read_text())
    decisions = ledger_doc["ledger"]

    # ---- OUT.2 binding map ----
    with writer.attempt("L07.0.binding_map") as att:
        binding = build_binding_map()
        att.detail = {"bound": len(binding["bound"]), "blocked": len(binding["blocked"])}
    writer.write_config("integration_binding_map.json", binding)
    writer.write_json("integration_binding_map.json", binding, schema=binding["schema"])

    # ---- L07.1 disabled-hooks parity + fixed-intent Python/Rust parity ----
    with writer.attempt("L07.1.disabled_hooks_parity") as att:
        initial, schedule = deployed_schedule(bars)
        # the parity that matters: the whole integration path with NOTHING
        # scheduled must reproduce run_candidate over the same real bars
        baseline_parity = integration_baseline_parity(ALPHA, bars, initial.params)
        # and the cheap one: consulting an inert hook must have no side effect.
        # It is driven by the REAL fills the canonical run produced, so the three
        # accounts actually move -- three empty accounts agree trivially.
        hook_frame = bars.reset_index()
        hook_frame["signal"] = 0.0
        canonical_fills = run_continuous_account(
            ALPHA, bars, initial=VersionWindow("baseline", initial.params, 0, "act-b"),
            schedule=[]).fills
        for fill in canonical_fills:
            hook_frame.loc[int(fill["bar_index"]), "signal"] = (
                float(fill["side"]) * float(fill["qty"]))
        hook_parity = disabled_hooks_parity(hook_frame, initial_capital=INITIAL_CAPITAL,
                                            signal_column="signal")
        engine_parity = parity_report()
        att.detail = {"baseline_identical": baseline_parity["identical"],
                      "hooks_identical": hook_parity["identical"],
                      "engine_parity": engine_parity["status"]}

    # ---- L07.3 training job isolation ----
    with writer.attempt("L07.3.training_jobs") as att:
        benchmark = measure_refit_latency(bars)
        runner = TrainingJobRunner(benchmark)
        cutoffs = pd.date_range(DEV_START, DEV_END, freq="28D")
        for index, cutoff in enumerate(cutoffs):
            job = runner.request(f"refit-{index}", "model_retrain", cutoff, fits=4,
                                 data_cutoff=cutoff)
            legal = [cutoff - pd.Timedelta("1D"), cutoff]
            runner.run(job, read_timestamps=legal)
        att.detail = {"jobs": len(runner.jobs),
                      "seconds_per_fit": benchmark.measured_seconds_per_fit}

    # ---- T56 the ONE continuous account, parameters changing mid-run ----
    with writer.attempt("L07.4.continuous_account") as att:
        account_run = run_continuous_account(ALPHA, bars, initial=initial, schedule=schedule)
        att.detail = {"bars": len(bars), "entries": account_run.entries,
                      "switches": len(account_run.switches)}
    account_record = account_run.as_record()

    # ---- L07.4 / OUT.5 activation tape ----
    with writer.attempt("L07.4.activation") as att:
        tape = build_activation_tape(bars, account_run)
        att.detail = {"requested": len(tape.activations)}
    activation_record = tape.as_record()
    writer.write_config("parameter_activation_tape.json", activation_record)
    writer.write_json("parameter_activation_tape.json", activation_record,
                      schema=activation_record["schema"])

    # ---- L07.2 + L07.5 the event stream and the segments it implies ----
    with writer.attempt("L07.2.continuous_run") as att:
        run = build_run(bars, decisions, account_run)
        end_guard = assert_no_future_activation_end(run.bus.ordered())
        # every activation in this arm must trace to a calendar cutoff, never to
        # a regime observation that merely shares the stream with it
        # sources are DERIVED from the tape against the cutoffs LAB-04 declared;
        # handing them in would make this check assert its own conclusion
        cutoffs = _fold_cutoffs()
        isolation = regime_information_isolation(
            run.bus.ordered(), arm=run.arm,
            activation_sources=attribute_activation_sources(
                run.bus.ordered(), calendar_cutoffs=cutoffs))
        segment_guard = run.segments.assert_no_future_length_used(run.decisions)
        equity = pd.Series(account_run.equity, index=account_run.index)
        daily = run.segments.daily_account_comparison(equity)
        att.detail = {"bars": len(bars), "events": len(run.bus),
                      "segments": len(run.segments.segments)}
    segments_record = {**run.segments.as_record(),
                       "daily_account_comparison": daily,
                       "future_length_guard": segment_guard}
    writer.write_config("operational_segments.json", segments_record)
    writer.write_json("operational_segments.json", segments_record,
                      schema=segments_record["schema"])

    # ---- L07.7 replay parity and prefix stability, on the REAL account ----
    with writer.attempt("L07.7.replay_parity") as att:
        # consume the DECISION each event implies, not the event's own metadata:
        # replaying a tape's labels back to itself would pass on any tape
        replay = replay_parity(run.bus, consume=_decision_of)
        prefix = account_prefix_stability(bars, initial, schedule)
        att.detail = {"replay_identical": replay["identical"],
                      "prefix_holds": prefix["prefix_survives_future_mutation"]}

    # ---- L07.6 failure handling ----
    with writer.attempt("L07.6.failures") as att:
        failures = FailureLedger(incumbent_version=parameter_digest({"cid": "incumbent_seed"}))
        exercise_failures(failures, pd.Timestamp(DEV_END))
        att.detail = {"modes_exercised": len(failures.as_record()["modes_exercised"])}

    trace = {
        "schema": "crypto_regime_lab.lab07_continuous_trace.v1",
        "generated_at_utc": utc_now_iso(),
        "alpha_id": ALPHA, "symbol": SYMBOL,
        "data_role": "development", "window": [DEV_START, DEV_END],
        "bars": int(len(bars)),
        "integration_baseline_parity": baseline_parity,
        "inert_hook_parity": hook_parity,
        "engine_fixed_intent_parity": engine_parity,
        "training_jobs": runner.as_record(),
        "continuous_account": account_record,
        "run": run.as_record(),
        "activation_end_guard": end_guard,
        "regime_information_isolation": isolation,
        "regime_publication_lag_seconds": float(REGIME_PUBLICATION_LAG.total_seconds()),
        "regime_publication_lag_source": (
            "one full regime interval, because bars are left-labelled and an observation is "
            "knowable only once its own bar completes; this is what LAB-05's emission tape "
            "records as available_at"),
        "replay_parity": replay,
        "prefix_stability": prefix,
        "failures": failures.as_record(),
    }
    writer.write_config("lab07_continuous_trace.json", trace)
    writer.write_json("lab07_continuous_trace.json", trace, schema=trace["schema"])

    print(f"bars                : {len(bars):,} {DECISION_INTERVAL} bars {DEV_START}..{DEV_END}")
    print(f"binding map         : {len(binding['bound'])} bound, "
          f"{len(binding['blocked'])} blocked")
    print(f"integration parity   : identical={baseline_parity['identical']} "
          f"(canonical run_candidate vs integration with no schedule, 4 surfaces; "
          f"{baseline_parity['canonical_fills']} vs {baseline_parity['integrated_fills']} fills)")
    print(f"inert-hook parity    : identical={hook_parity['identical']} "
          f"(DISABLED vs INERT vs baseline over {hook_parity['fills_compared']} real fills)")
    print(f"engine intent parity : {engine_parity['status']}")
    print(f"refit latency        : {benchmark.measured_seconds_per_fit:.3f}s/fit measured, "
          f"{len(runner.jobs)} jobs, max delay "
          f"{runner.as_record()['max_delay_seconds']:.1f}s")
    print(f"activations          : {activation_record['requested']} requested, "
          f"{activation_record['effected']} effected, "
          f"blocked={activation_record['blocked_by_reason']}")
    print(f"segments             : {segments_record['count']} "
          f"({segments_record['no_change_trigger_count']} no-change triggers)")
    print(f"continuous account   : {account_record['entries']} entries, "
          f"{account_record['fills']} fills, equity "
          f"{account_record['initial_equity']:,.0f} -> {account_record['final_equity']:,.2f} "
          f"({account_record['total_return']:+.2%})")
    print(f"                       resets={account_record['account_resets']}, "
          f"spliced={account_record['spliced_from_independent_runs']}, "
          f"switches effected={account_record['switches_effected']}/"
          f"{len(account_record['switches'])}")
    for switch in account_record["switches"]:
        print(f"    {switch['activation_id']}: requested bar {switch['requested_at_bar']}, "
              f"effective {switch['effective_at_bar']}, blocked {switch['blocked_bars']} bars")
    print(f"regime isolation     : clean={isolation['clean']}, "
          f"{isolation['regime_observations_on_the_stream']:,} observations on the stream "
          f"reached {sum(1 for v in isolation['activation_sources'].values() if v != 'calendar_cutoff')} decisions")
    print(f"replay parity        : {replay['identical']}")
    print(f"prefix stability     : longer={prefix['prefix_matches_longer_run']}, "
          f"mutated future={prefix['prefix_survives_future_mutation']}")
    print(f"failure modes        : {len(failures.as_record()['modes_exercised'])}/"
          f"{len(failures.as_record()['modes_declared'])} exercised")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
