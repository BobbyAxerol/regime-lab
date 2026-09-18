"""RF-04.1 acceptance — the cutoff provider drives the real Mode 4 pipeline.

Four properties are pinned here:

* a supplied CUTOFF LIST reaches Mode 4 selection (calendar or dynamic);
* calendar and dynamic cutoffs really differ on the fixture;
* every scored fold declares ``oos_used_for_selection=False``;
* mutating the price suffix after a cutoff leaves that cutoff's selection
  unchanged, and the search-facing strategy call never receives the operational
  test segment end.
"""

from __future__ import annotations

import pandas as pd

from crypto_regime_lab.experiments.dynamic_fold_provider import (
    CutoffSchedule,
    calendar_cutoffs,
    engine_param_ranges,
    regime_cutoffs,
    run_cutoff_walk_forward,
)
from crypto_regime_lab.selector.installed_wfo import mutate_oos, synthetic_frame
from crypto_regime_lab.selector.mode4_baseline import AScSignalStrategy

TRIALS = 2
SEED = 11


def _asc_run(frame: pd.DataFrame, cutoffs: tuple[str, ...], trials: int = TRIALS) -> dict:
    schedule = CutoffSchedule(arm="M4_CAL", cutoffs=cutoffs, source="test fixture",
                              train_memory_days=20)
    return run_cutoff_walk_forward(
        "A-SC", frame, schedule, param_ranges=engine_param_ranges("A-SC"),
        strategy_class=AScSignalStrategy, optuna_trials=trials, seed=SEED,
    )


class RecordingASCStrategy(AScSignalStrategy):
    """Records the fold view each strategy call is handed.

    The engine instantiates an isolated copy per call, so the log is class-level.
    """

    calls: list[dict] = []

    def build_signal(self, data, params=None, train_index=None, test_index=None, fold=None):
        calls = type(self).calls
        calls.append({
            "train_end": fold.train_end,
            "fold_test_end": fold.test_end,
            "requested_test_end": pd.DatetimeIndex(test_index)[-1],
        })
        return super().build_signal(data, params=params, train_index=train_index,
                                    test_index=test_index, fold=fold)


def test_rf04_the_provider_passes_the_supplied_cutoff_list_to_mode4_selection():
    frame = synthetic_frame(n=2400, seed=5, freq="4h")
    cutoffs = ("2020-10-01T00:00:00+00:00", "2021-01-01T00:00:00+00:00")
    out = _asc_run(frame, cutoffs)
    assert out["ok"], out.get("error")
    assert out["cutoffs"] == list(cutoffs)
    assert out["optimization_mode"] == "mode_4_is_only_robust"
    assert out["optimization_schedule"] == "per_fold_causal"
    assert out["candidate_selection_metric"] == "is_only_robust"
    assert out["scoring_backend"] == "endpoint"
    assert out["fold_selection_table"], "the cutoff list produced no scored fold"
    selected_starts = [row["test_start"] for row in out["fold_selection_table"]]
    for cutoff in cutoffs[:len(selected_starts)]:
        assert pd.Timestamp(cutoff).isoformat() in selected_starts
    assert set(out["params_by_fold"]) == {
        str(index) for index in range(len(selected_starts))}
    assert out["trial_records"], "Mode 4 selection produced no trial ledger"
    assert out["selected_digest"], "a selection without a digest is unverifiable"


def test_rf04_calendar_and_dynamic_cutoffs_are_actually_different_on_the_fixture():
    frame = synthetic_frame(n=2400, seed=5, freq="4h")
    calendar = calendar_cutoffs(first_cutoff="2020-07-01T00:00:00+00:00",
                                window_start=str(frame.index[0]), window_end=str(frame.index[-1]),
                                test_days=120, train_memory_days=60)
    emissions = []
    for index, moment in enumerate(frame.index):
        state = (index // 120) % 2
        emissions.append({
            "state_id": state, "state_namespace": "fixture",
            "state_common": state, "decision_eligible": True, "quality_status": "OK",
            "available_at": moment.isoformat(),
        })
    dynamic = regime_cutoffs(emissions, window_start=str(frame.index[0]),
                             window_end=str(frame.index[-1]),
                             min_gap_days=10.0, max_age_days=400.0, budget=None)
    assert calendar.cutoffs, "the calendar produced no cutoff"
    assert dynamic.cutoffs, "the dynamic controller produced no cutoff"
    assert list(calendar.cutoffs) != list(dynamic.cutoffs)
    assert calendar.kind == "calendar" and dynamic.kind == "regime"


def test_rf04_every_scored_fold_declares_oos_used_for_selection_false():
    frame = synthetic_frame(n=2400, seed=5, freq="4h")
    cutoffs = ("2020-10-01T00:00:00+00:00", "2021-01-01T00:00:00+00:00")
    out = _asc_run(frame, cutoffs)
    assert out["ok"], out.get("error")
    assert out["oos_used_for_selection"] is False
    for row in out["fold_selection_table"]:
        assert row["outer_oos_used_for_selection"] is False
        assert str(row["causality_claim"]) == "strict_fold_local_retraining"
    for record in out["trial_records"]:
        metadata = record["selection_metadata"]
        assert (metadata.get("oos_used_for_selection") is False
                or metadata.get("oos_seen_by_optuna") is False), metadata


def test_rf04_the_provider_reproduces_the_public_mode4_run_on_the_same_calendar():
    """RF02.4 parity: the lab cutoff provider reduces to the public run."""
    import quantbt as q

    from crypto_regime_lab.integration.activation import parameter_digest

    frame = synthetic_frame(n=2400, seed=5, freq="4h")
    ranges = engine_param_ranges("A-SC")
    common = dict(
        strategy_class=AScSignalStrategy,
        split_mode=2021, split_frequency="monthly",
        optimization_mode="mode_4_is_only_robust", optimization_schedule="per_fold_causal",
        optuna_trials=TRIALS, random_seed=SEED,
        target_mode="signal_notional", backend="native_vectorized",
        account=q.AccountConfig(initial_capital=20000.0), alloc_per_trade=0.1,
        symbols=["S"], use_funding=False, slippage_bps=1.0, fee=0.0008, fee_rate=0.0004,
        optimization_config={"candidate_selection_metric": "is_only_robust",
                             "scoring_backend": "endpoint",
                             "research_retention": "full_trial_ledger"},
    )
    public = q.QuantBTEndpoint.walk_forward(**common).backtest(data=frame, param_ranges=ranges)
    public_wf = public.metadata["walk_forward_result"]
    cutoffs = tuple(fold.test_start.isoformat() for fold in public_wf.folds)
    public_params = {str(key): dict(value)
                     for key, value in (public_wf.metadata.get("params_by_fold") or {}).items()}
    assert cutoffs, "the public run produced no fold to compare against"

    provider = run_cutoff_walk_forward(
        "A-SC", frame,
        CutoffSchedule(arm="M4_CAL", cutoffs=cutoffs, source="parity fixture",
                       train_memory_days=None),
        param_ranges=ranges, strategy_class=AScSignalStrategy,
        optuna_trials=TRIALS, seed=SEED,
    )
    assert provider["ok"], provider.get("error")
    assert provider["cutoffs"] == list(cutoffs)
    assert provider["params_by_fold"] == public_params, (
        "the cutoff provider selected different parameters than the public engine")
    assert provider["selected_digest"] == parameter_digest(dict(public_wf.params))


def test_rf04_changing_the_future_suffix_does_not_change_that_cutoffs_selection():
    frame = synthetic_frame(n=2400, seed=5, freq="4h")
    cutoffs = ("2020-10-01T00:00:00+00:00", "2021-01-01T00:00:00+00:00")
    base = _asc_run(frame, cutoffs)
    assert base["ok"], base.get("error")

    mutated = mutate_oos(frame, cutoffs[0], scale=8.0, seed=99)
    after = _asc_run(mutated, cutoffs)
    assert after["ok"], after.get("error")
    assert (base["params_by_fold"]["0"] == after["params_by_fold"]["0"]), (
        "mutating the suffix after the first cutoff changed that cutoff's selection")
    assert base["trial_count"] == after["trial_count"]

    RecordingASCStrategy.calls = []
    recording = run_cutoff_walk_forward(
        "A-SC", frame, CutoffSchedule(arm="M4_CAL", cutoffs=cutoffs, source="test",
                                      train_memory_days=20),
        param_ranges=engine_param_ranges("A-SC"), strategy_class=RecordingASCStrategy,
        optuna_trials=TRIALS, seed=SEED,
    )
    assert recording["ok"], recording.get("error")
    search_calls = [call for call in RecordingASCStrategy.calls
                    if call["requested_test_end"] == call["train_end"]]
    assert search_calls, "no in-sample strategy call was observed"
    for call in search_calls:
        assert call["fold_test_end"] <= call["train_end"], (
            "the search-facing fold exposed the operational test segment end")
