"""L04.1 — trace the WFO that is actually installed, and measure its OOS usage.

The guide is explicit: do not assume every mode calls one generic selector, and
if a mode uses OOS data to CHOOSE a candidate, that arm must be labelled
selection-adjusted rather than reported as an untouched baseline.

Reading the source is not enough to settle that, so this module runs the real
engine and mutates ONLY the out-of-sample segment. If the chosen parameters move,
the selector consumed OOS information. That is a measurement, not an inference.

Discovered contract of this install (probed, not assumed):
  * a strategy is called ``strategy(data, params=, fold=, train_index=, test_index=)``
    and receives the WHOLE frame, including the OOS rows — causality is the
    strategy's responsibility, which is itself a leakage surface worth recording;
  * the WalkForwardResult is returned on ``result.metadata["walk_forward_result"]``
    and the config trace on ``result.metadata["walk_forward"]``.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

# Modes the installed engine accepts, with the selection metric each one requires.
MODE_METRIC_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "none": ("robust_decay",),
    "mode_1_decay": ("robust_decay",),
    "mode_2_sbb": ("robust_decay", "mean_oos_sharpe"),
    "mode_3_flat_minima": ("robust_decay",),
    "mode_4_is_only_robust": ("is_only_robust",),
    "mode_5_full_robust": ("full_robust", "full_plateau_robust", "full_temporal_robust",
                           "full_best"),
}
ALL_MODES = tuple(MODE_METRIC_REQUIREMENTS)

# Fields of the config trace the lab wants recorded for every arm.
TRACE_FIELDS = (
    "optimization_mode", "optimization_schedule", "candidate_selection_metric",
    "split_frequency", "window_mode", "train_window", "fold_account_policy",
    "random_seed", "optuna_trials", "scoring_backend", "top_is_fraction", "top_is_k",
    "decay_lambda", "decay_gamma", "sbb_samples", "sbb_block_length",
    "flat_top_fraction", "flat_eps", "flat_selector", "plateau_quantile",
    "dispersion_penalty", "temporal_weight", "plateau_weight",
    "use_bootstrap_penalty", "use_complexity_penalty", "numba_enabled",
)


#: What the ENGINE ITSELF declares about a run's causality. The behavioural probe
#: below asks a different question -- did the selection move when only the OOS
#: segment changed -- and the two answers are reported side by side. A behavioural
#: "did not move" never overrides the engine's own declaration that it looked.
DECLARED_CLAIM_FIELDS = (
    "oos_used_for_selection", "validation_claim", "causality_claim",
    "chronological_validation_claim", "params_semantics", "signal_causality_scope",
    "full_sample_used_for_selection", "optimization_mode", "optimization_schedule",
)


@dataclass
class WfoTrace:
    mode: str
    metric: str
    ok: bool
    selected_params: dict | None = None
    trial_count: int = 0
    fold_count: int = 0
    config_trace: dict = field(default_factory=dict)
    folds: list[dict] = field(default_factory=list)
    declared_claims: dict = field(default_factory=dict)
    selection_metadata: dict = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)
    error: str | None = None

    def as_record(self) -> dict:
        return {
            "mode": self.mode, "metric": self.metric, "ok": self.ok,
            "selected_params": self.selected_params, "trial_count": self.trial_count,
            "fold_count": self.fold_count, "config_trace": self.config_trace,
            "folds": self.folds, "declared_claims": self.declared_claims,
            "selection_metadata": self.selection_metadata,
            "trial_records": self.records, "error": self.error,
        }


def synthetic_frame(n: int = 6000, seed: int = 7, freq: str = "4h",
                    start: str = "2020-01-01") -> pd.DataFrame:
    """A deterministic OHLCV frame long enough for quarterly walk-forward folds."""
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.01, 0.5, n))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({
        "open": open_, "high": np.maximum(open_, close) + 0.3,
        "low": np.minimum(open_, close) - 0.3, "close": close,
        "volume": np.full(n, 1000.0),
    }, index=idx)


def moving_average_strategy(data, params=None, fold=None, train_index=None, test_index=None):
    """A deliberately simple two-parameter strategy for tracing the engine.

    It is NOT one of the four alphas. LAB-04 is about the SELECTOR, and a
    transparent strategy keeps the selector's behaviour visible instead of
    tangled with an alpha's semantics.
    """
    p = params or {}
    close = data["close"]
    fast = max(1, int(p.get("fast", 5)))
    slow = max(fast + 1, int(p.get("slow", 20)))
    signal = (close.rolling(fast).mean() > close.rolling(slow).mean()).astype(float)
    return signal.fillna(0.0)


def _quiet_optuna() -> None:
    """Silence Optuna's per-trial chatter. Optuna itself is a hard dependency, so
    an ImportError here is a real environment problem and is raised, not swallowed."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)


def run_wfo(frame: pd.DataFrame, *, mode: str, metric: str,
            param_ranges: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None,
            strategy: Callable = moving_average_strategy,
            optuna_trials: int = 0, seed: int = 42,
            # the ENGINE's own default split mode, not a lab choice (walkforward.py:409)
            split_mode: str = "walk_forward_2022",
            split_frequency: str = "quarterly",
            optimization_schedule: str = "global",
            scoring_backend: str = "proxy",
            extra_config: dict | None = None) -> WfoTrace:
    """Run the installed walk-forward engine once and capture its trace.

    Two call conventions matter and were PROBED, not assumed:
      * supplying a fixed ``params`` dict alongside ``param_ranges`` makes the
        engine run that one point and skip the search entirely (the per-fold
        schedules reject the combination outright);
      * ``scoring_backend="endpoint"`` returned all-zero Sharpes for this
        strategy shape, so the proxy backend is used and the divergence is
        recorded rather than silently accepted.
    """
    import quantbt as q

    _quiet_optuna()

    trace = WfoTrace(mode=mode, metric=metric, ok=False)
    kwargs: dict[str, Any] = dict(
        strategy_class=strategy, split_mode=split_mode, split_frequency=split_frequency,
        optimization_mode=mode, optimization_schedule=optimization_schedule,
        optuna_trials=optuna_trials, random_seed=seed,
        account=q.AccountConfig(initial_capital=20000.0),
        # A01: EndpointConfig.fee is a legacy ROUND-TRIP rate while the study
        # registers a ONE-WAY rate. Pass both, built from the one-way value, so no
        # route halves or doubles it.
        fee=0.0008, fee_rate=0.0004, slippage_bps=1.0,
        symbols=["S"], use_funding=False,
    )
    # The selection metric lives in the WFO config, not on EndpointConfig; it is
    # passed through `optimization_config` (probed, not assumed).
    optimization_config: dict[str, Any] = {"candidate_selection_metric": metric,
                                           "scoring_backend": scoring_backend}
    if optimization_schedule == "per_fold_causal":
        # The engine refuses causal Mode 1 without a fully specified inner split.
        optimization_config.update({"inner_split_frequency": "quarterly",
                                    "inner_window_mode": "expanding",
                                    "inner_train_window": "365D"})
    if extra_config:
        optimization_config.update(extra_config.pop("optimization_config", {}))
        kwargs.update(extra_config)
    kwargs["optimization_config"] = optimization_config
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            endpoint = q.QuantBTEndpoint.walk_forward(**kwargs)
            backtest_kwargs: dict[str, Any] = {"data": frame}
            if param_ranges:
                # A fixed params dict would turn the search off; never send both.
                backtest_kwargs["param_ranges"] = param_ranges
            else:
                backtest_kwargs["params"] = params or {"fast": 5, "slow": 20}
            result = endpoint.backtest(**backtest_kwargs)
    except Exception as exc:  # a mode that cannot run is recorded, never skipped
        trace.error = f"{type(exc).__name__}: {exc}"[:400]
        return trace

    meta = result.metadata or {}
    wf_result = meta.get("walk_forward_result")
    walk_forward_meta = meta.get("walk_forward") or {}
    trace.config_trace = {k: v for k, v in walk_forward_meta.items() if k in TRACE_FIELDS}
    trace.declared_claims = {k: walk_forward_meta[k] for k in DECLARED_CLAIM_FIELDS
                             if k in walk_forward_meta}
    if wf_result is None:
        trace.error = "no walk_forward_result on the endpoint result"
        return trace

    trace.ok = True
    trace.selected_params = dict(wf_result.params or {})
    trace.fold_count = len(wf_result.folds or [])
    for fold in (wf_result.folds or []):
        trace.folds.append({k: str(getattr(fold, k))
                            for k in ("train_start", "train_end", "test_start", "test_end")
                            if hasattr(fold, k)})
    best = wf_result.best_trial
    if best is not None:
        trace.selection_metadata = dict(getattr(best, "selection_metadata", {}) or {})
    table = wf_result.trial_table
    if table is not None and len(table):
        frame_out = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
        trace.trial_count = int(len(frame_out))
        keep = [c for c in ("trial_id", "objective", "mean_is_sharpe", "mean_oos_sharpe",
                            "mean_decay", "std_decay", "pruned", "params")
                if c in frame_out.columns]
        trace.records = frame_out[keep].head(200).to_dict("records")
    return trace


def mutate_oos(frame: pd.DataFrame, oos_start: str, *, scale: float = 6.0,
               seed: int = 99) -> pd.DataFrame:
    """Replace the OOS segment with a very different path; leave IS untouched.

    Only bars at or after ``oos_start`` change. If a selector is in-sample only,
    its choice cannot move.
    """
    out = frame.copy()
    mask = out.index >= pd.Timestamp(oos_start, tz="UTC")
    rng = np.random.default_rng(seed)
    n = int(mask.sum())
    if n == 0:
        raise ValueError("the mutation window selected no rows")
    anchor = float(out.loc[~mask, "close"].iloc[-1]) if (~mask).any() else 100.0
    path = anchor + np.cumsum(rng.normal(0.0, scale, n))
    open_ = np.r_[anchor, path[:-1]]
    out.loc[mask, "close"] = path
    out.loc[mask, "open"] = open_
    out.loc[mask, "high"] = np.maximum(open_, path) + 0.3
    out.loc[mask, "low"] = np.minimum(open_, path) - 0.3
    return out


def last_train_end(trace: WfoTrace) -> str | None:
    """The latest bar any fold TRAINS on. Anything after it is out of sample for
    every fold, which is the only cut a mutation probe may use here."""
    ends = [f.get("train_end") for f in trace.folds if f.get("train_end")]
    return max(ends) if ends else None


def oos_usage_probe(frame: pd.DataFrame, *, mode: str, metric: str,
                    param_ranges: dict[str, Any], oos_start: str | None = None,
                    optuna_trials: int = 12, seed: int = 42,
                    optimization_schedule: str = "global") -> dict:
    """Does this mode's selection depend on OOS data? Measured by mutation."""
    base = run_wfo(frame, mode=mode, metric=metric, param_ranges=param_ranges,
                   optuna_trials=optuna_trials, seed=seed,
                   optimization_schedule=optimization_schedule)
    if not base.ok:
        return {"mode": mode, "metric": metric, "status": "MODE_UNAVAILABLE",
                "error": base.error}
    if oos_start is None:
        # read the cut off the ACTUAL folds instead of assuming a calendar date
        end = last_train_end(base)
        if end is None:
            return {"mode": mode, "metric": metric, "status": "NO_FOLDS_TO_PROBE"}
        oos_start = (pd.Timestamp(end) + pd.Timedelta(seconds=1)).isoformat()
        if not (frame.index > pd.Timestamp(end)).any():
            return {
                "mode": mode, "metric": metric, "schedule": optimization_schedule,
                "status": "NO_OUT_OF_SAMPLE_REGION_EXISTS",
                "last_train_end": str(end), "fold_count": base.fold_count,
                "detail": ("every bar in the frame is inside some fold's training window, so this "
                           "mode has no out-of-sample region to mutate. For a full-sample "
                           "calibration mode that is the finding, not a probe failure."),
            }
    mutated_frame = mutate_oos(frame, oos_start)

    # PRECONDITION. The splits run ``window_mode="expanding"``, so a later fold
    # TRAINS on what an earlier fold tested. Mutating everything after a single
    # global cut therefore rewrites training data too, and a selection that moves
    # afterwards says nothing about OOS usage. Measure that first, on a fixed
    # parameter point so no sampler difference can confound it.
    fixed = {name: (spec[0] if isinstance(spec, (tuple, list)) else spec)
             for name, spec in param_ranges.items()}
    base_fixed = run_wfo(frame, mode="none", metric="robust_decay", params=fixed,
                         optuna_trials=0, seed=seed)
    mutated_fixed = run_wfo(mutated_frame, mode="none", metric="robust_decay", params=fixed,
                            optuna_trials=0, seed=seed)

    def _is_scores(trace: WfoTrace) -> list[float]:
        return [float(r.get("mean_is_sharpe") or 0.0) for r in trace.records]

    is_before, is_after = _is_scores(base_fixed), _is_scores(mutated_fixed)
    is_intact = (base_fixed.ok and mutated_fixed.ok and is_before == is_after)
    if not is_intact:
        return {
            "mode": mode, "metric": metric, "schedule": optimization_schedule,
            "status": "INVALID_PROBE_MUTATION_REACHED_TRAINING_DATA",
            "oos_start": oos_start,
            "fixed_point_is_scores_before": is_before,
            "fixed_point_is_scores_after": is_after,
            "detail": ("with expanding windows a later fold trains on an earlier fold's test "
                       "window, so this cut does not isolate out-of-sample data. No conclusion "
                       "about OOS usage may be drawn from this run."),
        }

    mutated = run_wfo(mutated_frame, mode=mode, metric=metric, param_ranges=param_ranges,
                      optuna_trials=optuna_trials, seed=seed,
                      optimization_schedule=optimization_schedule)
    if not mutated.ok:
        return {"mode": mode, "metric": metric, "status": "MUTATION_RUN_FAILED",
                "error": mutated.error}

    # A mutation test that cannot fail proves nothing. Confirm the OOS scores
    # really moved before drawing any conclusion from the selection staying put.
    def _oos_spread(trace: WfoTrace) -> float:
        values = [abs(float(r.get("mean_oos_sharpe") or 0.0)) for r in trace.records]
        return float(max(values)) if values else 0.0

    base_oos, mutated_oos = _oos_spread(base), _oos_spread(mutated)
    oos_moved = abs(base_oos - mutated_oos) > 1e-9
    same = base.selected_params == mutated.selected_params
    if not oos_moved:
        return {
            "mode": mode, "metric": metric, "schedule": optimization_schedule,
            "status": "INCONCLUSIVE_MUTATION_HAD_NO_EFFECT",
            "baseline_max_abs_oos_sharpe": base_oos,
            "mutated_max_abs_oos_sharpe": mutated_oos,
            "detail": ("the OOS scores did not move, so the mutation could not have changed a "
                       "selection either way; this run is not evidence about OOS usage"),
        }
    return {
        "mode": mode,
        "metric": metric,
        "schedule": optimization_schedule,
        "status": "MEASURED",
        "baseline_selected_params": base.selected_params,
        "mutated_selected_params": mutated.selected_params,
        "selection_unchanged_after_oos_mutation": bool(same),
        "uses_oos_for_selection": bool(not same),
        "arm_label": "A_causal" if same else "A_legacy_selection_adjusted",
        "trial_count": base.trial_count,
        "fold_count": base.fold_count,
        "mutation_effective": True,
        "training_data_untouched_by_mutation": True,
        "oos_start": oos_start,
        "oos_start_rule": "the first bar after the latest train_end across all folds",
        "probe_power": (
            "with expanding windows the only region that is out of sample for EVERY fold is the "
            "final test segment, so this probe mutates just that. A null result bounds OOS "
            "dependence, it does not eliminate it; the engine's own declared_claims are the "
            "authoritative label."),
        "baseline_max_abs_oos_sharpe": base_oos,
        "mutated_max_abs_oos_sharpe": mutated_oos,
        "interpretation": (
            "the chosen parameters did not move when only the out-of-sample segment changed, so "
            "this mode's selection is in-sample only on this fixture"
            if same else
            "the chosen parameters MOVED when only the out-of-sample segment changed: this mode "
            "consumes OOS information to select, so an arm using it must be labelled "
            "A_legacy_selection_adjusted and never reported as an untouched baseline (guide 10.1)"
        ),
    }


def trace_all_modes(frame: pd.DataFrame, param_ranges: dict[str, Any],
                    *, optuna_trials: int = 12, oos_start: str | None = None) -> dict:
    """Trace every installed mode and measure each one's OOS usage."""
    traces, probes = {}, {}
    for mode, metrics in MODE_METRIC_REQUIREMENTS.items():
        metric = metrics[0]
        traces[mode] = run_wfo(frame, mode=mode, metric=metric, param_ranges=param_ranges,
                               optuna_trials=optuna_trials).as_record()
        probes[mode] = oos_usage_probe(frame, mode=mode, metric=metric,
                                       param_ranges=param_ranges, oos_start=oos_start,
                                       optuna_trials=optuna_trials)
    for schedule in ("per_fold_decay", "per_fold_causal"):
        key = f"mode_1_decay@{schedule}"
        probes[key] = oos_usage_probe(
            frame, mode="mode_1_decay", metric="robust_decay", param_ranges=param_ranges,
            oos_start=oos_start, optuna_trials=optuna_trials, optimization_schedule=schedule)
    usable = [m for m, t in traces.items() if t["ok"]]
    oos_selectors = [m for m, p in probes.items() if p.get("uses_oos_for_selection")]
    return {
        "schema": "crypto_regime_lab.installed_wfo_trace.v1",
        "modes_declared": list(ALL_MODES),
        "mode_metric_requirements": {k: list(v) for k, v in MODE_METRIC_REQUIREMENTS.items()},
        "modes_that_ran": usable,
        "modes_that_failed": {m: t["error"] for m, t in traces.items() if not t["ok"]},
        "traces": traces,
        "oos_usage": probes,
        "modes_using_oos_for_selection": oos_selectors,
        "strategy_receives_full_frame": True,
        "strategy_contract_note": (
            "the engine hands the strategy the WHOLE frame plus train_index/test_index, so a "
            "strategy that ignores those indices can read OOS bars. Causality is the strategy's "
            "responsibility here, and the lab's adapters enforce it themselves."
        ),
        "selector_families": {
            "CandidateSelector": ["best", "feasible_best", "pareto_first", "robust_plateau"],
            "wfo_record_selectors": ["select_flat_minima_record", "select_is_only_robust_record",
                                     "select_is_plateau_robust_record",
                                     "select_full_sample_robust_record"],
            "note": "two distinct families exist; a mode does not necessarily call the generic one",
        },
    }


def installed_defaults() -> dict:
    """The rest of L04.1: sampler, objective backend, freeze, floor and retention.

    Read off the installed package rather than assumed from the guide.
    """
    import inspect

    from quantbt.core.research_audit import ResearchRetentionPlanV1
    from quantbt.walkforward import WalkForwardConfig, _select_is_candidate_records
    from quantbt import walkforward as wf

    config = WalkForwardConfig()
    retention = ResearchRetentionPlanV1()
    source = inspect.getsource(wf)
    return {
        "schema": "crypto_regime_lab.installed_wfo_defaults.v1",
        "optuna_sampler": {
            "class": "optuna.samplers.TPESampler",
            "seeded_with": "study_seed derived from config.random_seed",
            "pruner": "DuplicatePruner",
            "early_stopping": config.optuna_early_stopping,
            "default_random_seed": config.random_seed,
            "default_optuna_trials": config.optuna_trials,
            "note": ("optuna_trials defaults to 0 and optimization_mode defaults to 'none', so an "
                     "unconfigured walk_forward call performs NO search"),
        },
        "objective_backend": {
            "lab_setting": "proxy",
            "why": ("scoring_backend='endpoint' returned all-zero Sharpes for this strategy shape, "
                    "so the proxy objective is used and the divergence is recorded rather than "
                    "silently accepted"),
        },
        "candidate_freeze": {
            "stage_1": "_select_is_candidate_records(records, param_ranges, config)",
            "stage_2": "_select_oos_candidate_record(records, config)",
            "metric_default": config.candidate_selection_metric,
            "supported_metrics": ["robust_decay", "mean_oos_sharpe", "mean_is_sharpe",
                                  "is_plateau_robust", "is_only_robust"],
            "frozen_before_outer_evaluation": "_select_is_candidate_records" in source,
            "stage_1_callable": callable(_select_is_candidate_records),
            "stage_1_signature": str(inspect.signature(_select_is_candidate_records)),
        },
        "baseline_floor": {
            "min_trades_per_year": config.min_trades_per_year,
            "trade_penalty_factor": config.trade_penalty_factor,
            "mechanism": "trade_frequency_penalty(trade_count, required_trades, factor)",
            "default_behaviour": ("both default to None, so the installed baseline applies NO "
                                  "trade-frequency floor unless one is configured; a floor is "
                                  "therefore a lab choice and must be disclosed if it flips a "
                                  "robust decision (guide 7.2)"),
        },
        "retention": {
            "financial_retention": retention.financial_retention,
            "research_retention": retention.research_retention,
            "financial_scope": retention.financial_scope,
            "note": ("research_retention defaults to 'none' and the financial scope is "
                     "'selected_final_execution', so per-candidate fill detail is NOT retained by "
                     "default; the lab keeps its own per-candidate evidence instead"),
        },
        "fold_account_policy": config.fold_account_policy,
        "plateau_parameters": {"flat_top_fraction": config.flat_top_fraction,
                               "flat_eps": config.flat_eps,
                               "flat_min_samples": config.flat_min_samples,
                               "q25_weight": config.q25_weight,
                               "dispersion_penalty": config.dispersion_penalty},
    }
