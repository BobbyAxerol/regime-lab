"""VWFO-02 search module: Sampler injection, Mode 4 IS180 search, and stock anchor selection.

Supports S_TPE and S_SOBOL with exactly 128 attempted trials per cutoff.
IS180 evaluation uses QuantBT native event account scoring with subperiod temporal robustness.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import optuna
import pandas as pd
from quantbt.optimization.space import stable_params_key, suggest_params
from quantbt.walkforward import (
    DuplicatePruner,
    WalkForwardConfig,
    WalkForwardTrialRecord,
    _candidate_count,
    _temporal_robustness_stats,
    select_is_only_robust_record,
    split_datetime_index_into_subperiods_v1,
)

from ..alphas.a_sc import SignalCombineAdapterV1, compute_signal_combine
from ..alphas.base import MarketSlice
from ..experiments.dynamic_fold_provider import engine_param_ranges
from ..integration.continuous_account import VersionWindow
from ..integration.event_account import run_event_account

# Suppress Optuna logging noise
optuna.logging.set_verbosity(optuna.logging.WARNING)


def build_sampler(sampler_id: str, seed: int) -> optuna.samplers.BaseSampler:
    """Build the qualified sampler instance with deterministic seed."""
    if sampler_id == "S_TPE":
        return optuna.samplers.TPESampler(seed=seed, n_startup_trials=10)
    elif sampler_id == "S_SOBOL":
        return optuna.samplers.QMCSampler(qmc_type="sobol", seed=seed, scramble=True, warn_independent_sampling=False)
    else:
        raise ValueError(f"Unknown sampler_id: {sampler_id}. Supported: S_TPE, S_SOBOL")


def get_default_mode4_config(trials: int = 128, seed: int = 20260928) -> WalkForwardConfig:
    """Get pinned Mode 4 WalkForwardConfig matching the registered specification."""
    return WalkForwardConfig(
        optimization_mode="mode_4_is_only_robust",
        optimization_schedule="per_fold_causal",
        candidate_selection_metric="is_only_robust",
        optuna_trials=trials,
        random_seed=seed,
        scoring_backend="endpoint",
        scoring_trading_days=365,
        window_mode="rolling",
        train_window="180D",
        is_subperiods=6,
        q25_weight=0.3,
        dispersion_penalty=0.5,
        temporal_weight=0.65,
        plateau_weight=0.35,
        flat_eps=0.15,
        flat_min_samples=3,
        flat_selector="medoid",
        top_is_fraction=0.1,
    )


def compute_annualized_sharpe(daily_returns: np.ndarray | Sequence[float], trading_days: int = 365) -> float:
    """Compute annualized Sharpe ratio from daily returns."""
    rets = np.asarray(daily_returns, dtype=np.float64)
    rets = rets[np.isfinite(rets)]
    if len(rets) < 2:
        return 0.0
    sd = float(np.std(rets, ddof=1))
    if sd <= 1e-12:
        return 0.0
    mean_ret = float(np.mean(rets))
    return float(mean_ret / sd * np.sqrt(float(trading_days)))


def score_candidate_is180(
    frame_15m: pd.DataFrame,
    params: dict[str, Any],
    is_start: pd.Timestamp,
    is_end: pd.Timestamp,
    *,
    alpha_id: str = "A-SC",
    subperiods: int = 6,
    initial_capital: float = 20000.0,
    one_way_fee: float = 0.0004,
    slippage_bps: float = 1.0,
    shards: list[pd.DatetimeIndex] | None = None,
) -> dict[str, Any]:
    """Score a candidate on the 180-day in-sample window with QuantBT native event account."""
    if len(frame_15m) > 0 and frame_15m.index[0] >= is_start and frame_15m.index[-1] < is_end:
        is_data = frame_15m
    else:
        is_mask = (frame_15m.index >= is_start) & (frame_15m.index < is_end)
        is_data = frame_15m.loc[is_mask]

    if len(is_data) < 96:  # at least 1 day of 15m bars
        return {
            "status": "INSUFFICIENT_BARS",
            "is_sharpe": float("-inf"),
            "temporal_score": float("-inf"),
            "daily_returns": [],
            "fills_count": 0,
            "shard_sharpes": [],
        }

    # Parameter feasibility check for A-VWAP
    if alpha_id == "A-VWAP":
        if float(params.get("rsi_os", 30)) >= float(params.get("rsi_ob", 70)):
            return {
                "status": "FAILED_CANDIDATE",
                "reason": "rsi_os >= rsi_ob infeasible",
                "is_sharpe": float("-inf"),
                "temporal_score": float("-inf"),
                "daily_returns": [],
                "fills_count": 0,
                "shard_sharpes": [],
            }

    initial = VersionWindow("is-score", params, 0, "initial", required_warm_bars=None)
    try:
        run = run_event_account(
            alpha_id,
            is_data,
            initial=initial,
            schedule=[],
            initial_capital=initial_capital,
            one_way_fee=one_way_fee,
            slippage_bps=slippage_bps,
            report_level="score",
        )
    except Exception as exc:
        return {
            "status": "FAILED_CANDIDATE",
            "reason": f"{type(exc).__name__}: {exc}"[:200],
            "is_sharpe": float("-inf"),
            "temporal_score": float("-inf"),
            "daily_returns": [],
            "fills_count": 0,
            "shard_sharpes": [],
        }

    if run.status != "EVALUATED":
        return {
            "status": run.status,
            "is_sharpe": float("-inf"),
            "temporal_score": float("-inf"),
            "daily_returns": [],
            "fills_count": 0,
            "shard_sharpes": [],
        }

    equity_series = pd.Series(run.equity, index=is_data.index)
    daily_equity = equity_series.resample("1D").last().ffill().dropna()
    daily_returns = daily_equity.pct_change().dropna().to_numpy()
    is_sharpe = compute_annualized_sharpe(daily_returns, trading_days=365)

    # Compute subperiod Sharpes
    if shards is None:
        shards = list(split_datetime_index_into_subperiods_v1(is_data.index, int(subperiods)))
    shard_sharpes: list[float] = []
    shard_metrics: list[dict[str, Any]] = []

    for shard_idx, shard in enumerate(shards):
        if len(shard) < 2:
            continue
        shard_eq = equity_series.loc[shard[0]:shard[-1]]
        shard_daily = shard_eq.resample("1D").last().ffill().dropna()
        shard_rets = shard_daily.pct_change().dropna().to_numpy()
        shard_sr = compute_annualized_sharpe(shard_rets, trading_days=365)
        shard_sharpes.append(shard_sr)
        shard_metrics.append({
            "shard_id": shard_idx,
            "test_sharpe": shard_sr,
            "is_subperiod_sharpe": shard_sr,
        })

    temporal_stats = _temporal_robustness_stats(
        shard_sharpes,
        q25_weight=0.3,
        dispersion_penalty=0.5,
        fallback=is_sharpe,
    )

    return {
        "status": "EVALUATED",
        "is_sharpe": float(is_sharpe),
        "temporal_score": float(temporal_stats["temporal_score"]),
        "temporal_stats": temporal_stats,
        "daily_returns": [float(r) for r in daily_returns],
        "fills_count": len(run.fills),
        "entries": run.entries,
        "shard_sharpes": shard_sharpes,
        "shard_metrics": shard_metrics,
        "final_equity": float(equity_series.iloc[-1]) if len(equity_series) else initial_capital,
    }


def run_cutoff_search(
    frame_15m: pd.DataFrame,
    origin_cutoff: str | pd.Timestamp,
    sampler_id: str,
    *,
    alpha_id: str = "A-SC",
    n_trials: int = 128,
    seed: int = 20260928,
    is_days: int = 180,
    config: WalkForwardConfig | None = None,
    cache: dict[str, Any] | None = None,
    initial_capital: float = 20000.0,
    one_way_fee: float = 0.0004,
    slippage_bps: float = 1.0,
) -> dict[str, Any]:
    """Execute a 128-trial search on the IS180 window using the designated sampler."""
    if config is None:
        config = get_default_mode4_config(trials=n_trials, seed=seed)

    cutoff = pd.Timestamp(origin_cutoff, tz="UTC")
    is_start = cutoff - pd.Timedelta(days=is_days)
    is_mask = (frame_15m.index >= is_start) & (frame_15m.index < cutoff)
    is_data = frame_15m.loc[is_mask]
    precomputed_shards = list(split_datetime_index_into_subperiods_v1(is_data.index, int(config.is_subperiods)))

    param_ranges = engine_param_ranges(alpha_id)
    sampler = build_sampler(sampler_id, seed=seed)
    pruner = DuplicatePruner()

    study = optuna.create_study(direction="maximize", sampler=sampler, pruner=pruner)

    records: list[WalkForwardTrialRecord] = []
    seen_params: set[str] = set()
    attempted = 0
    completed = 0
    pruned = 0
    failed = 0
    cache_hits = 0

    t0 = time.perf_counter()

    for trial_idx in range(n_trials):
        attempted += 1
        trial = study.ask()
        params = suggest_params(trial, param_ranges)
        key = stable_params_key(params)

        if key in seen_params:
            pruned += 1
            record = WalkForwardTrialRecord(
                trial_id=trial_idx,
                params=dict(params),
                objective=-np.inf,
                mean_is_sharpe=0.0,
                mean_oos_sharpe=0.0,
                mean_decay=0.0,
                std_decay=0.0,
                fold_metrics=[],
                pruned=True,
                selection_metadata={"prune_reason": "duplicate_parameters"},
            )
            records.append(record)
            study.tell(trial, state=optuna.trial.TrialState.PRUNED)
            continue

        seen_params.add(key)

        # Semantic cache lookup
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "params": params,
                    "is_start": is_start.isoformat(),
                    "is_end": cutoff.isoformat(),
                    "fee": one_way_fee,
                    "slippage": slippage_bps,
                    "capital": initial_capital,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        if cache is not None and cache_key in cache:
            score_data = cache[cache_key]
            cache_hits += 1
        else:
            score_data = score_candidate_is180(
                is_data,
                params,
                is_start,
                cutoff,
                alpha_id=alpha_id,
                subperiods=config.is_subperiods,
                initial_capital=initial_capital,
                one_way_fee=one_way_fee,
                slippage_bps=slippage_bps,
                shards=precomputed_shards,
            )
            if cache is not None:
                cache[cache_key] = score_data

        if score_data["status"] != "EVALUATED" or not math.isfinite(score_data["temporal_score"]):
            failed += 1
            record = WalkForwardTrialRecord(
                trial_id=trial_idx,
                params=dict(params),
                objective=-np.inf,
                mean_is_sharpe=float(score_data.get("is_sharpe", 0.0)),
                mean_oos_sharpe=0.0,
                mean_decay=0.0,
                std_decay=0.0,
                fold_metrics=score_data.get("shard_metrics", []),
                pruned=True,
                selection_metadata={"status": score_data["status"]},
            )
            records.append(record)
            study.tell(trial, -np.inf)
            continue

        completed += 1
        temporal_score = score_data["temporal_score"]
        is_sharpe = score_data["is_sharpe"]
        stats = score_data.get("temporal_stats", {})

        record = WalkForwardTrialRecord(
            trial_id=trial_idx,
            params=dict(params),
            objective=float(temporal_score),
            mean_is_sharpe=float(is_sharpe),
            mean_oos_sharpe=0.0,
            mean_decay=0.0,
            std_decay=0.0,
            fold_metrics=score_data["shard_metrics"],
            pruned=False,
            selection_metadata={
                "temporal_score": float(temporal_score),
                "temporal_median": float(stats.get("temporal_median", is_sharpe)),
                "temporal_q25": float(stats.get("temporal_q25", is_sharpe)),
                "temporal_mad": float(stats.get("temporal_mad", 0.0)),
                "temporal_count": float(stats.get("temporal_count", 0.0)),
                "is_sharpe": float(is_sharpe),
                "daily_returns": score_data["daily_returns"],
                "fills_count": score_data["fills_count"],
                "entries": score_data["entries"],
            },
        )
        records.append(record)
        study.tell(trial, float(temporal_score))

    wall_time_s = time.perf_counter() - t0

    # Stock Mode 4 robust anchor selection
    completed_records = [r for r in records if not r.pruned and np.isfinite(r.objective)]
    if not completed_records:
        raise RuntimeError(f"Search produced no completed trials for origin {cutoff}")

    anchor_record = select_is_only_robust_record(completed_records, param_ranges, config=config)

    # Build candidate pool dictionary
    pool = {
        f"cand_{r.trial_id:04d}": {
            "trial_id": r.trial_id,
            "params": dict(r.params),
            "objective": float(r.objective),
            "is_sharpe": float(r.mean_is_sharpe),
            "pruned": bool(r.pruned),
            "selection_metadata": r.selection_metadata,
        }
        for r in records
    }

    return {
        "origin_cutoff": cutoff.isoformat(),
        "is_window": [is_start.isoformat(), cutoff.isoformat()],
        "sampler_id": sampler_id,
        "seed": seed,
        "attempted_trials": attempted,
        "completed_trials": completed,
        "pruned_trials": pruned,
        "failed_trials": failed,
        "unique_params": len(seen_params),
        "cache_hits": cache_hits,
        "wall_time_s": wall_time_s,
        "anchor_record": {
            "trial_id": anchor_record.trial_id,
            "params": dict(anchor_record.params),
            "objective": float(anchor_record.objective),
            "is_sharpe": float(anchor_record.mean_is_sharpe),
            "selection_metadata": dict(anchor_record.selection_metadata),
        },
        "anchor_trial_record": anchor_record,
        "records": records,
        "pool": pool,
    }
