"""A08 — run the ACTUAL public Mode 4 per_fold_causal WFO on a route-ready alpha.

The old arm A built `WalkForwardTrialRecord`s by hand, wrote a mean episode
utility into the `mean_is_sharpe` field and called a default selector. This
module replaces that with the installed pipeline: a real signal strategy, the
real `QuantBTEndpoint.walk_forward`, real endpoint scoring and the engine's own
Mode 4 IS-only selection. What is captured here is the engine's trace, not a
reconstruction.

A-SC is the route-ready alpha: it is long/flat with no resting protection, so
its decisions are exactly representable as a target series and the engine's
execution of that series preserves the alpha's semantics.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

from crypto_regime_lab.alphas.a_sc import SignalCombineAdapterV1
from crypto_regime_lab.alphas.base import MarketSlice
from crypto_regime_lab.alphas.contracts import IntentKind
from crypto_regime_lab.quantbt_bridge.routes import ONE_WAY_TAKER_FEE, SLIPPAGE_BPS, bound_fee_kwargs

MODE = "mode_4_is_only_robust"
SCHEDULE = "per_fold_causal"
METRIC = "is_only_robust"


class Mode4BaselineError(RuntimeError):
    """The public Mode 4 pipeline could not be run with the registered contract."""


class AScSignalStrategy:
    """The canonical A-SC decisions projected onto the engine's signal contract."""

    def __init__(self, alpha_id: str = "A-SC") -> None:
        self.alpha_id = alpha_id

    def build_signal(self, data, params=None, train_index=None, test_index=None, fold=None):
        if params is None:
            raise Mode4BaselineError("A-SC signal strategy requires params")
        market = MarketSlice(open=data["open"].to_numpy(), high=data["high"].to_numpy(),
                             low=data["low"].to_numpy(), close=data["close"].to_numpy(),
                             volume=data["volume"].to_numpy(), index=data.index)
        adapter = SignalCombineAdapterV1(dict(params), market, vectorised=True)
        targets = np.zeros(len(data))
        position = 0.0
        start = max(adapter.warmup_bars(), 1)
        for t in range(start, len(data)):
            decision = adapter.on_bar_close(t)
            for intent in decision.intents:
                if intent.kind == IntentKind.ENTER_LONG:
                    position = 1.0
                elif intent.kind == IntentKind.ENTER_SHORT:
                    position = -1.0
                elif intent.kind == IntentKind.EXIT_ALL:
                    position = 0.0
            targets[t] = position
        return pd.Series(targets, index=data.index)


def _selection_metadata(record: dict) -> dict:
    metadata = record.get("selection_metadata")
    if metadata is None:
        return {}
    if isinstance(metadata, str):
        import json
        try:
            return json.loads(metadata)
        except ValueError:
            return {"raw": metadata}
    return dict(metadata)


def run_mode4_public_baseline(frame: pd.DataFrame, *, param_ranges: dict[str, Any],
                              optuna_trials: int, seed: int = 11,
                              split_mode: int | str = 2021, split_frequency: str = "monthly",
                              target_mode: str = "signal_notional",
                              alloc_per_trade: float = 0.1,
                              backend: str = "native_vectorized",
                              one_way_fee: float = ONE_WAY_TAKER_FEE,
                              slippage_bps: float = SLIPPAGE_BPS,
                              strategy_class: type = AScSignalStrategy) -> dict:
    """Run one public Mode 4 causal walk-forward and return its captured trace.

    ``alloc_per_trade`` is an EndpointConfig field and must be passed at the TOP
    level: inside ``optimization_config`` it is ignored, the prepared scorer then
    sizes at a different notional and every objective reads 0. That mistake was
    made and caught here; a zero-objective baseline is now a test failure.
    """
    import optuna
    import quantbt as q

    from crypto_regime_lab.integration.activation import parameter_digest

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    bound = bound_fee_kwargs(one_way_fee)
    kwargs: dict[str, Any] = dict(
        strategy_class=strategy_class,
        split_mode=split_mode, split_frequency=split_frequency,
        optimization_mode=MODE, optimization_schedule=SCHEDULE,
        optuna_trials=int(optuna_trials), random_seed=int(seed),
        target_mode=target_mode, backend=backend,
        account=q.AccountConfig(initial_capital=20000.0),
        alloc_per_trade=float(alloc_per_trade),
        symbols=["S"], use_funding=False, slippage_bps=slippage_bps,
        optimization_config={
            "candidate_selection_metric": METRIC,
            "scoring_backend": "endpoint",
            "research_retention": "full_trial_ledger",
        },
        **bound,
    )
    payload: dict[str, Any] = {
        "schema": "regime_lab.mode4_public_baseline.v3",
        "mode": MODE, "schedule": SCHEDULE, "metric": METRIC,
        "requested": {"split_mode": str(split_mode), "split_frequency": split_frequency,
                      "target_mode": target_mode, "backend": backend,
                      "alloc_per_trade": alloc_per_trade,
                      "optuna_trials": int(optuna_trials), "seed": int(seed),
                      "fee_binding": bound},
        "sizing_contract": {
            "target_mode": target_mode,
            "alloc_per_trade": float(alloc_per_trade),
            "semantics": "constant 0/1 target series; the position is re-anchored on signal changes",
        },
        "ok": False, "error": None,
    }
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            endpoint = q.QuantBTEndpoint.walk_forward(**kwargs)
            result = endpoint.backtest(data=frame, param_ranges=param_ranges)
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"[:500]
        return payload

    meta = result.metadata or {}
    walk_forward = dict(meta.get("walk_forward") or {})
    wf_result = meta.get("walk_forward_result")
    if wf_result is None:
        payload["error"] = "no walk_forward_result on the endpoint result"
        return payload

    fold_table = wf_result.metadata.get("fold_selection_table") if hasattr(wf_result, "metadata") else None
    folds = [{"fold_id": int(getattr(f, "fold_id", i)),
              "train_start": str(getattr(f, "train_start", "")),
              "train_end": str(getattr(f, "train_end", "")),
              "test_start": str(getattr(f, "test_start", "")),
              "test_end": str(getattr(f, "test_end", ""))}
             for i, f in enumerate(wf_result.folds or [])]
    trial_records = []
    if wf_result.trial_table is not None and len(wf_result.trial_table):
        keep = [c for c in ("trial_id", "params", "objective", "mean_is_sharpe", "mean_oos_sharpe",
                            "mean_decay", "std_decay", "pruned", "schedule_fold_id",
                            "study_id", "fold_seed", "selection_metadata", "temporal_score",
                            "temporal_median", "temporal_q25", "temporal_mad", "temporal_count",
                            "is_subperiod_count")
                if c in wf_result.trial_table.columns]
        for record in wf_result.trial_table[keep].to_dict("records"):
            record["selection_metadata"] = _selection_metadata(record)
            trial_records.append(record)

    params_by_fold = {str(k): dict(v) for k, v in (wf_result.metadata.get("params_by_fold") or {}).items()}
    payload.update({
        "ok": True,
        "contract_trace": {k: walk_forward.get(k) for k in (
            "optimization_mode", "optimization_schedule", "candidate_selection_metric",
            "scoring_backend", "split_mode", "split_frequency", "window_mode", "random_seed",
            "optuna_trials", "validation_claim", "causality_claim", "chronological_validation_claim",
            "oos_used_for_selection", "full_sample_used_for_selection", "params_semantics",
            "signal_causality_scope", "research_retention", "financial_retention",
            "financial_retention_scope") if k in walk_forward},
        "folds": folds,
        "fold_count": len(folds),
        "params_by_fold": params_by_fold,
        "selected_params": dict(wf_result.params or {}),
        "selected_digest": parameter_digest(dict(wf_result.params or {})),
        "trial_count": len(trial_records),
        "trial_records": trial_records[:200],
        "fold_selection_table": (fold_table.to_dict("records") if hasattr(fold_table, "to_dict")
                                 else fold_table),
        "scorer": {
            "scoring_backend": walk_forward.get("scoring_backend"),
            "candidate_selection_metric": walk_forward.get("candidate_selection_metric"),
            "prepared_scoring_cache": walk_forward.get("prepared_scoring_cache"),
            "selector_math": ("the engine's own _select_is_candidate_records path; the lab reconstructs "
                              "no records and writes no utility into a Sharpe field"),
        },
        "route_notes": {
            "pct_equity_disqualified": ("on an IS fold the pct_equity fallback opens no position when the "
                                        "sliced signal is a constant target: it scores 0 for a state-like "
                                        "signal. signal_notional establishes the target at the fold start"),
            "signal_causality_scope": walk_forward.get("signal_causality_scope"),
        },
    })
    return payload
