"""RF-04.1 — a lab-only adapter that injects a CUTOFF LIST into the public Mode 4 WFO.

The corrective plan (7.4) asks for a thin fold/cutoff adapter around the installed
``WalkForwardEngine`` that keeps the engine's own ``optimize_params``, Mode 4
selector, scorer and trial capture. This module supplies exactly that and nothing
else:

* :class:`CutoffWalkForwardEngine` subclasses the installed engine and overrides
  only ``build_folds`` (cutoff list -> canonical folds) and the in-sample strategy
  call (so the search-facing fold does not expose the operational test segment
  end). Everything else is inherited.
* :func:`run_cutoff_walk_forward` runs one arm's schedule. On the ``endpoint``
  route it goes through the public ``QuantBTEndpoint.walk_forward`` factory and
  swaps only the engine class for the duration of the call, so the public
  scorer, stitching and final account are reused. On the ``event`` route it
  builds the engine directly with :class:`EventAccountScorer`, a lab binding
  that scores candidates with the ACTUAL QuantBT native-event account (the
  route RF-02 qualified for order-sensitive alphas), while still reusing the
  engine's Mode 4 selection and trial ledger.

No private default-selector imitation, no hand-built ``WalkForwardTrialRecord``,
no utility written into a Sharpe field.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from quantbt.walkforward import (
    WalkForwardConfig,
    WalkForwardEngine,
    _build_fold_v2,
)

from ..integration.activation import parameter_digest
from ..integration.continuous_account import VersionWindow
from ..quantbt_bridge.routes import ONE_WAY_TAKER_FEE, SLIPPAGE_BPS, bound_fee_kwargs

MODE = "mode_4_is_only_robust"
SCHEDULE = "per_fold_causal"
METRIC = "is_only_robust"

#: Registered pilot economics (corrective_study_spec.json).
ACCOUNT_CAPITAL = 20000.0
ENTRY_NOTIONAL = 2000.0
ALLOC_PER_TRADE = 0.1

#: The registered calendar cadence: 180-day training memory, 180-day operational
#: test windows, first cutoff 2021-01-01 (calendar_baseline.CalendarSpec).
CALENDAR_TRAIN_DAYS = 180
CALENDAR_TEST_DAYS = 180
CALENDAR_FIRST_CUTOFF = "2021-01-01"


class ProviderError(RuntimeError):
    """The cutoff adapter cannot run the registered contract."""


# ---------------------------------------------------------------------------
# schedules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CutoffSchedule:
    """A registered cutoff list plus how it was produced."""

    arm: str
    cutoffs: tuple[str, ...]
    source: str
    kind: str = "calendar"
    train_memory_days: int | None = CALENDAR_TRAIN_DAYS
    diagnostics: dict = field(default_factory=dict)

    def as_record(self) -> dict:
        return {
            "arm": self.arm,
            "kind": self.kind,
            "cutoffs": list(self.cutoffs),
            "count": len(self.cutoffs),
            "train_memory_days": (None if self.train_memory_days is None
                                  else int(self.train_memory_days)),
            "train_memory_rule": ("expanding from the first data bar"
                                  if self.train_memory_days is None
                                  else f"rolling {int(self.train_memory_days)} days"),
            "source": self.source,
            "diagnostics": dict(self.diagnostics),
        }


def calendar_cutoffs(*, first_cutoff: str = CALENDAR_FIRST_CUTOFF,
                     window_start: str, window_end: str,
                     test_days: int = CALENDAR_TEST_DAYS,
                     train_memory_days: int = CALENDAR_TRAIN_DAYS,
                     max_cutoffs: int | None = None) -> CutoffSchedule:
    """The registered calendar cadence, clipped to the declared evaluation window."""
    start = pd.Timestamp(window_start, tz="UTC")
    end = pd.Timestamp(window_end, tz="UTC")
    cutoff = pd.Timestamp(first_cutoff, tz="UTC")
    cutoffs: list[str] = []
    while cutoff <= end:
        if start <= cutoff:
            cutoffs.append(cutoff.isoformat())
        cutoff = cutoff + pd.Timedelta(days=int(test_days))
        if max_cutoffs is not None and len(cutoffs) >= int(max_cutoffs):
            break
    if not cutoffs:
        raise ProviderError("the registered calendar produced no cutoff inside the window")
    return CutoffSchedule(
        arm="M4_CAL", kind="calendar", cutoffs=tuple(cutoffs),
        train_memory_days=int(train_memory_days),
        source=(f"registered CalendarSpec cadence: first cutoff {first_cutoff}, "
                f"{int(test_days)}-day test spacing, 180-day training memory"),
    )


def regime_cutoffs(emissions: Iterable[dict], *, window_start: str, window_end: str,
                   min_gap_days: float = 45.0, max_age_days: float = 180.0,
                   budget: int | None = 6) -> CutoffSchedule:
    """Dynamic cutoffs from the RF-03 online controller over an emission tape."""
    from .regime_schedule import online_trigger_schedule

    schedule = online_trigger_schedule(
        list(emissions), earliest=window_start, latest=window_end,
        min_gap_days=float(min_gap_days), max_age_days=float(max_age_days),
        budget=budget,
    )
    return CutoffSchedule(
        arm="M4_REGIME", kind="regime", cutoffs=tuple(schedule.cutoffs),
        source=schedule.source,
        diagnostics={
            "min_gap_days": float(min_gap_days),
            "max_age_days": float(max_age_days),
            "budget": budget,
            "eligibility_filter": "decision_eligible=True and quality_status in ('OK',)",
        },
    )


def engine_param_ranges(alpha_id: str) -> dict[str, Any]:
    """The declared alpha schema as an engine search space, fixed values included."""
    from ..selector.alpha_schemas import SCHEMAS

    schema = SCHEMAS[alpha_id]
    ranges: dict[str, Any] = {}
    for name, spec in schema.specs.items():
        if spec.kind == "fixed":
            ranges[name] = spec.fixed_value
        elif spec.kind == "categorical":
            ranges[name] = list(spec.choices)
        elif spec.kind == "int":
            ranges[name] = (int(spec.low), int(spec.high), int(spec.step or 1))
        else:
            ranges[name] = (float(spec.low), float(spec.high), float(spec.step or 0.0))
    return ranges


# ---------------------------------------------------------------------------
# the engine hook
# ---------------------------------------------------------------------------

def _cutoff_folds(idx: pd.DatetimeIndex, config: WalkForwardConfig,
                  cutoffs: Sequence[str]) -> list:
    """Canonical folds: rolling train memory, test segment to the next cutoff."""
    idx = pd.DatetimeIndex(pd.to_datetime(idx))
    memory = config.metadata.get("lab_train_memory_days")
    memory_delta = None if memory is None else pd.Timedelta(days=float(memory))
    moments = [pd.Timestamp(value) for value in cutoffs]
    if any(moment.tzinfo is None for moment in moments):
        raise ProviderError("cutoffs must be timezone-aware or UTC ISO strings")
    moments = sorted(moments)
    if not moments:
        raise ProviderError("the cutoff list is empty")
    if moments[0] <= idx[0]:
        raise ProviderError("the first cutoff must be after the first data bar")

    folds = []
    for fold_id, cutoff in enumerate(moments):
        test_start = int(idx.searchsorted(cutoff, side="left"))
        if test_start >= len(idx):
            break
        if fold_id + 1 < len(moments):
            test_stop = int(idx.searchsorted(moments[fold_id + 1], side="left"))
        else:
            test_stop = len(idx)
        if test_stop <= test_start:
            continue
        if memory_delta is None:
            raw_train_start = 0
        else:
            raw_train_start = int(idx.searchsorted(cutoff - memory_delta, side="left"))
        fold = _build_fold_v2(
            idx, fold_id=fold_id, raw_train_start=raw_train_start,
            test_start=test_start, test_stop=test_stop, config=config,
        )
        if fold is None:
            raise ProviderError(f"cutoff {cutoff.isoformat()} produced an empty fold")
        folds.append(fold)
    if not folds:
        raise ProviderError("the cutoff list produced no usable fold")
    return folds


def _search_fold(fold):
    """A fold whose test segment is its own training window (no future end)."""
    from quantbt.walkforward import WalkForwardFold

    return WalkForwardFold(
        fold_id=int(fold.fold_id),
        train_start=fold.train_start,
        train_end=fold.train_end,
        test_start=fold.train_start,
        test_end=fold.train_end,
        train_index=fold.train_index,
        test_index=fold.train_index,
        warmup_index=fold.warmup_index,
        account_policy=fold.account_policy,
    )


class CutoffWalkForwardEngine(WalkForwardEngine):
    """The installed engine with a cutoff-list fold provider and a bounded search view."""

    def build_folds(self, idx):
        cutoffs = self.config.metadata.get("lab_cutoffs")
        if not cutoffs:
            return super().build_folds(idx)
        return _cutoff_folds(idx, self.config, cutoffs)

    def _call_strategy_for_indices(self, data, params, train_index, test_index, fold,
                                   context: str = "out-of-sample generation"):
        if "in-sample" in str(context).lower():
            fold = _search_fold(fold)
        return super()._call_strategy_for_indices(
            data=data, params=params, train_index=train_index, test_index=test_index,
            fold=fold, context=context,
        )


@contextmanager
def _installed_engine_class():
    """Swap only the engine CLASS the endpoint instantiates, then restore it."""
    import quantbt.walkforward as qwf

    original = qwf.WalkForwardEngine
    qwf.WalkForwardEngine = CutoffWalkForwardEngine
    try:
        yield
    finally:
        qwf.WalkForwardEngine = original


# ---------------------------------------------------------------------------
# the order-sensitive evaluator binding (RF02.4)
# ---------------------------------------------------------------------------

class ZeroSignalStrategy:
    """A strategy shaped for the engine contract; the event scorer ignores it."""

    def build_signal(self, data, params=None, train_index=None, test_index=None, fold=None):
        index = pd.DatetimeIndex(test_index if test_index is not None else data.index)
        return pd.Series(0.0, index=index)


def _annualised_sharpe(equity: pd.Series, trading_days: int) -> float:
    """The engine's own metric convention: daily returns, sqrt(trading_days)."""
    daily = equity.resample("1D").last().ffill().dropna()
    returns = daily.pct_change().dropna()
    if len(returns) < 2:
        returns = equity.pct_change().dropna()
    sd = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    if sd <= 0.0:
        return 0.0
    return float(returns.mean() / sd * np.sqrt(float(trading_days)))


class EventAccountScorer:
    """Score candidates with the actual QuantBT native-event account (A-HMA).

    The public signal WFO route cannot express resting protection, so RF02.4
    requires an evaluator binding that uses actual QuantBT evaluation while the
    engine keeps its Mode 4 selector and ledger. One event account is run per
    candidate and window; subperiod shards are read off the same equity series.
    """

    def __init__(self, alpha_id: str, *, one_way_fee: float = ONE_WAY_TAKER_FEE,
                 slippage_bps: float = SLIPPAGE_BPS,
                 initial_capital: float = ACCOUNT_CAPITAL,
                 engine_report_level: str | None = None) -> None:
        self.alpha_id = alpha_id
        self.one_way_fee = float(one_way_fee)
        self.slippage_bps = float(slippage_bps)
        self.initial_capital = float(initial_capital)
        # The engine's own output-retention profile (event_account.run_event_account).
        # None keeps the engine default; "score" drops per-bar audit ledgers
        # (measured: equity exact-equal, ~3.4x less peak transient memory).
        self.engine_report_level = engine_report_level
        self._cache: dict[tuple, dict] = {}
        self.calls = 0
        self.account_runs = 0

    def score_batch(self, tasks: Sequence[dict]) -> list[dict]:
        entries = list(tasks)
        # The full in-sample window is scored first so one account run serves
        # every subperiod shard of the same candidate and fold.
        for task in entries:
            if self._is_full_window(task) and self._key(task) not in self._cache:
                self._run_account(task)
        return [self._score_one(task) for task in entries]

    def __call__(self, data, output, index, fold, params, context: str,
                 trading_days: int, **kwargs) -> dict:
        return self.score_batch([{
            "data": data, "output": output, "index": index, "fold": fold,
            "params": params, "context": context, "trading_days": int(trading_days),
        }])[0]

    @staticmethod
    def _run_end(task) -> pd.Timestamp:
        fold = task.get("fold")
        window = pd.DatetimeIndex(task["index"])
        if fold is not None and len(fold.train_index):
            train = pd.DatetimeIndex(fold.train_index)
            if window.isin(train).all():
                return train[-1]
        return window[-1]

    @classmethod
    def _key(cls, task) -> tuple:
        fold = task.get("fold")
        return (
            json.dumps(dict(task["params"]), sort_keys=True, default=str),
            int(fold.fold_id) if fold is not None else -1,
            int(cls._run_end(task).value),
        )

    @staticmethod
    def _is_full_window(task) -> bool:
        fold = task.get("fold")
        if fold is None or not len(fold.train_index):
            return False
        index = pd.DatetimeIndex(task["index"])
        train = pd.DatetimeIndex(fold.train_index)
        return index.equals(train)

    def _run_account(self, task) -> None:
        from ..integration.event_account import run_event_account

        self.calls += 1
        key = self._key(task)
        fold = task.get("fold")
        params = dict(task["params"])
        data = task["data"]
        if fold is not None and len(fold.train_index):
            base = data.loc[data.index >= fold.train_index[0]]
        else:
            base = data
        base = base.loc[base.index <= self._run_end(task)]
        if len(base) < 2:
            self._cache[key] = {"equity": pd.Series(dtype=float), "status": "INSUFFICIENT_BARS",
                                "engine_fill_count": 0}
            return
        initial = VersionWindow(
            f"{self.alpha_id}-score", params, 0, "score-initial", required_warm_bars=None,
        )
        try:
            run = run_event_account(
                self.alpha_id, base, initial=initial, schedule=[],
                initial_capital=self.initial_capital,
                one_way_fee=self.one_way_fee, slippage_bps=self.slippage_bps,
                report_level=self.engine_report_level,
            )
        except ValueError as exc:
            # An infeasible sampled point is not a financial evaluation; it is
            # excluded from selection rather than scored as a return.
            self._cache[key] = {"equity": pd.Series(dtype=float), "status": "INFEASIBLE",
                                "engine_fill_count": 0,
                                "reason": f"{type(exc).__name__}: {exc}"[:200]}
            return
        self.account_runs += 1
        # Fill counting source note (mem_audit 2026-09-20): `engine_fill_count`
        # is derived from the native audit trail, which the engine's reduced
        # output profiles (report_level="score"/"minimal") do not retain (it
        # reads 0 there). The strategy-level fill records (`run.fills`) are
        # profile-invariant: on the real RA-05 fold-0 account call the audit
        # and strategy levels measured IDENTICAL equity (exact float equality,
        # mem_audit s7) and identical strategy-level fill/entry counts
        # (81/81 fills, 41/41 entries) -- so scores use the strategy-level
        # count, and the audit-trail count is kept only as provenance for
        # default-profile runs.
        strategy_fill_count = len(getattr(run, "fills", None) or [])
        self._cache[key] = {
            "equity": pd.Series(np.asarray(run.equity, dtype=float), index=run.index),
            "status": run.status,
            "engine_fill_count": int(run.engine_fill_count),
            "strategy_fill_count": int(strategy_fill_count),
            "unmapped": len(run.unmapped_intents),
            "rejections": len(run.rejections),
        }

    def _score_one(self, task) -> dict:
        key = self._key(task)
        if key not in self._cache:
            self._run_account(task)
        cached = self._cache[key]
        if cached["status"] != "EVALUATED":
            return {"sharpe": float("-inf"), "turnover": 0.0, "trade_count": 0.0,
                    "status": cached["status"]}
        window = pd.DatetimeIndex(task["index"])
        equity = cached["equity"]
        sample = equity.loc[equity.index.isin(window)]
        if len(sample) < 2:
            return {"sharpe": float("-inf"), "turnover": 0.0, "trade_count": 0.0,
                    "status": "INSUFFICIENT_BARS"}
        # turnover/trade_count come from the profile-invariant strategy-level
        # fill records (see _run_account's note) so a reduced engine output
        # profile cannot silently zero a scorer field.
        fills = float(cached.get("strategy_fill_count",
                                 cached["engine_fill_count"]))
        return {
            "sharpe": _annualised_sharpe(sample, int(task["trading_days"])),
            "turnover": fills,
            "trade_count": fills,
            "status": cached["status"],
        }


# ---------------------------------------------------------------------------
# the provider run
# ---------------------------------------------------------------------------

def _frame_index(frame: pd.DataFrame) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(frame.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx


def _fills_as_records(fills) -> list[dict]:
    out = []
    for fill in fills or []:
        record = {}
        for name in ("bar_index", "sequence", "side", "qty", "price", "fee", "reason", "tag"):
            if hasattr(fill, name):
                value = getattr(fill, name)
                record[name] = value.value if hasattr(value, "value") else value
        out.append(record)
    return out


def _trial_records(wf_result) -> list[dict]:
    table = wf_result.trial_table
    if table is None or not len(table):
        return []
    keep = [c for c in (
        "trial_id", "params", "objective", "mean_is_sharpe", "mean_oos_sharpe",
        "mean_decay", "std_decay", "pruned", "schedule_fold_id", "study_id",
        "fold_seed", "selection_metadata", "temporal_score", "temporal_median",
        "temporal_q25", "temporal_mad", "temporal_count", "is_subperiod_count",
    ) if c in table.columns]
    records = []
    for row in table[keep].to_dict("records"):
        metadata = row.get("selection_metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except ValueError:
                metadata = {"raw": metadata}
        row["selection_metadata"] = dict(metadata or {})
        bad = {}
        for key, value in list(row.items()):
            if isinstance(value, float) and not np.isfinite(value):
                bad[key] = "NAN" if np.isnan(value) else ("POS_INF" if value > 0 else "NEG_INF")
        if bad:
            row["nonfinite_fields"] = bad
        records.append(row)
    return records


def _fold_table_rows(wf_result) -> list[dict]:
    table = wf_result.metadata.get("fold_selection_table")
    if table is None:
        return []
    if hasattr(table, "to_dict"):
        return table.to_dict("records")
    return list(table)


def _iso(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return pd.Timestamp(value).isoformat()


def _endpoint_payload(schedule: CutoffSchedule, wf_result, trace: dict) -> dict:
    params_by_fold = {
        str(key): _jsonable(dict(value))
        for key, value in (wf_result.metadata.get("params_by_fold") or {}).items()
    }
    selected = dict(wf_result.params or {})
    rows = _fold_table_rows(wf_result)
    payload = {
        "params_by_fold": params_by_fold,
        "selected_params": selected,
        "selected_digest": parameter_digest(selected) if selected else None,
        "fold_selection_table": [
            {
                "fold_id": int(row.get("fold_id", index)),
                "train_start": _iso(row.get("train_start")),
                "train_end": _iso(row.get("train_end")),
                "test_start": _iso(row.get("test_start")),
                "test_end": _iso(row.get("test_end")),
                "selected_params": row.get("selected_params"),
                "selected_is_objective": row.get("selected_is_objective"),
                "candidate_count": row.get("candidate_count"),
                "outer_oos_used_for_selection": bool(row.get("outer_oos_used_for_selection", False)),
                "causality_claim": row.get("causality_claim"),
                "outer_oos_metric": row.get("candidate_oos_metric"),
            }
            for index, row in enumerate(rows)
        ],
        "trial_records": _trial_records(wf_result),
        "trial_count": int(wf_result.metadata.get("n_optuna_trial_rows", 0) or len(_trial_records(wf_result))),
        "oos_used_for_selection": bool(wf_result.metadata.get("oos_used_for_selection", True)),
        "validation_claim": wf_result.metadata.get("validation_claim"),
        "causality_claim": wf_result.metadata.get("causality_claim"),
        "scoring_backend": wf_result.metadata.get("scoring_backend"),
        "candidate_selection_metric": wf_result.metadata.get("candidate_selection_metric"),
        "optimization_mode": wf_result.metadata.get("optimization_mode"),
        "optimization_schedule": wf_result.metadata.get("optimization_schedule"),
        "trace": trace,
    }
    return _jsonable(payload)


def run_cutoff_walk_forward(alpha_id: str, frame: pd.DataFrame, schedule: CutoffSchedule,
                            *, param_ranges: dict[str, Any], strategy_class: type,
                            optuna_trials: int = 8, seed: int = 20260911,
                            route: str = "endpoint",
                            backend: str = "native_vectorized",
                            one_way_fee: float = ONE_WAY_TAKER_FEE,
                            slippage_bps: float = SLIPPAGE_BPS,
                            alloc_per_trade: float = ALLOC_PER_TRADE,
                            account_capital: float = ACCOUNT_CAPITAL,
                            research_retention: str = "full_trial_ledger",
                            engine_report_level: str | None = None) -> dict:
    """Run one arm's cutoff list through the installed Mode 4 pipeline.

    ``research_retention`` is passed straight through to the installed engine's
    ``optimization_config`` (verified values: "full_trial_ledger", "selected_only",
    "none" -- quantbt/core/research_audit.py::RESEARCH_RETENTION_LEVELS_V1). It
    only controls an optional audit sidecar (walkforward.py's
    ``_capture_research_records`` / ``self._research_full_trial_records`` and
    ``_research_full_candidate_records``, extended once per fold and never
    cleared for the engine instance's lifetime); it never affects the public
    ``trial_table``, selection, scoring, or the final account. Defaults to the
    prior hardcoded value so every existing caller (RA-05, RA-07) is
    byte-identical.

    ``engine_report_level`` is the engine's own output-retention profile, passed
    to every ``run_event_account`` this route makes (both the per-candidate
    scorer calls and the final deployment account). ``None`` keeps the engine
    default so all existing callers are unchanged. ``"score"`` was measured
    (scripts/mem_audit.py, 2026-09-20) to reproduce the default profile's account
    path EXACTLY -- byte-equal equity, identical strategy-level fill/entry
    counts -- while roughly halving peak transient memory, which is what makes a
    full-length deployment account fit in budget. Scores are read from the
    profile-invariant strategy-level records (see ``EventAccountScorer``), never
    from the audit-only counter a reduced profile zeroes out.
    """
    import warnings

    import optuna
    import quantbt as q

    if optuna_trials <= 0:
        raise ProviderError("the registered per-fold schedule requires optuna_trials > 0")
    if not schedule.cutoffs:
        raise ProviderError(f"{schedule.arm}: the cutoff list is empty")
    idx = _frame_index(frame)
    frame = frame.copy()
    frame.index = idx
    bound = bound_fee_kwargs(one_way_fee)
    memory = (None if schedule.train_memory_days is None
              else int(schedule.train_memory_days))
    config_metadata = {
        "lab_cutoffs": list(schedule.cutoffs),
        "lab_train_memory_days": memory,
        "lab_schedule_arm": schedule.arm,
    }
    optimization_config: dict[str, Any] = {
        "candidate_selection_metric": METRIC,
        "scoring_backend": "endpoint",
        "research_retention": research_retention,
        "inner_split_frequency": "quarterly",
        "inner_window_mode": "expanding",
        "inner_train_window": "365D",
        "metadata": config_metadata,
    }
    endpoint_kwargs: dict[str, Any] = dict(
        strategy_class=strategy_class,
        split_mode=2021, split_frequency="monthly",
        optimization_mode=MODE, optimization_schedule=SCHEDULE,
        optuna_trials=int(optuna_trials), random_seed=int(seed),
        target_mode="signal_notional", backend=backend,
        account=q.AccountConfig(initial_capital=float(account_capital)),
        alloc_per_trade=float(alloc_per_trade),
        symbols=["S"], use_funding=False, slippage_bps=float(slippage_bps),
        optimization_config=optimization_config,
        **bound,
    )
    started = time.perf_counter()
    result_payload: dict[str, Any] = {
        "alpha_id": alpha_id,
        "route": route,
        "requested": {
            "mode": MODE, "schedule": SCHEDULE, "metric": METRIC,
            "optuna_trials_per_cutoff": int(optuna_trials), "seed": int(seed),
            "fee_binding": bound, "account_capital": float(account_capital),
            "alloc_per_trade": float(alloc_per_trade),
            "train_memory_days": memory,
        },
        "ok": False,
        "error": None,
    }
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if route == "endpoint":
                endpoint = q.QuantBTEndpoint.walk_forward(**endpoint_kwargs)
                with _installed_engine_class():
                    result = endpoint.backtest(data=frame, param_ranges=param_ranges)
                wf_result = (result.metadata or {}).get("walk_forward_result")
                if wf_result is None:
                    raise ProviderError("no walk_forward_result on the endpoint result")
                payload = _endpoint_payload(
                    schedule, wf_result, _safe_trace(result.metadata.get("walk_forward", {})))
                payload["account"] = _account_payload(
                    equity=result.equity, positions=result.positions,
                    fills=_fills_as_records(getattr(result, "fills", None)),
                    index=idx, fills_source=(
                        "engine_backtest_result"
                        if getattr(result, "fills", None)
                        else "engine_native_vectorized_no_per_fill_records"
                    ),
                    engine_report=_safe_report(result),
                )
            elif route == "event":
                scorer = EventAccountScorer(
                    alpha_id, one_way_fee=one_way_fee, slippage_bps=slippage_bps,
                    initial_capital=account_capital,
                    engine_report_level=engine_report_level,
                )
                wf_config = _event_walkforward_config(
                    optuna_trials=int(optuna_trials), seed=int(seed), metadata=config_metadata,
                    train_memory_days=memory,
                )
                engine = CutoffWalkForwardEngine(
                    strategy=ZeroSignalStrategy(), config=wf_config, scorer=scorer,
                )
                wf_result = engine.run(data=frame, param_ranges=param_ranges)
                payload = _endpoint_payload(schedule, wf_result, _safe_trace({
                    "optimization_mode": MODE, "optimization_schedule": SCHEDULE,
                    "scoring_backend": "endpoint", "candidate_selection_metric": METRIC,
                    "resolved_evaluator": "lab_event_account_scorer",
                    "event_account_runs": int(scorer.account_runs),
                    "event_scorer_calls": int(scorer.calls),
                    "engine_report_level": engine_report_level,
                }))
                payload["scoring_backend"] = "endpoint"
                payload["resolved_evaluator"] = "lab_event_account_scorer"
                account = _event_account_payload(
                    alpha_id, frame, payload["params_by_fold"], schedule.cutoffs, idx,
                    one_way_fee=one_way_fee, slippage_bps=slippage_bps,
                    account_capital=account_capital,
                    engine_report_level=engine_report_level,
                )
                payload["account"] = account
            else:
                raise ProviderError(f"unknown route {route!r}")
    except Exception as exc:  # a run that cannot execute is recorded, never invented
        result_payload["error"] = f"{type(exc).__name__}: {exc}"[:800]
        result_payload["wall_seconds"] = round(time.perf_counter() - started, 3)
        return _scrub_payload(result_payload)

    result_payload.update(payload)
    result_payload["cutoffs"] = list(schedule.cutoffs)
    result_payload["fold_count"] = len(schedule.cutoffs)
    result_payload["ok"] = True
    result_payload["wall_seconds"] = round(time.perf_counter() - started, 3)
    return _scrub_payload(result_payload)


def _event_walkforward_config(*, optuna_trials: int, seed: int, metadata: dict,
                             train_memory_days: int | None) -> WalkForwardConfig:
    return WalkForwardConfig(
        split_mode=2021, split_frequency="monthly",
        optimization_mode=MODE, optimization_schedule=SCHEDULE,
        candidate_selection_metric=METRIC, scoring_backend="endpoint",
        optuna_trials=int(optuna_trials), random_seed=int(seed),
        target_mode="signal_notional", metadata={
            **metadata, "lab_train_memory_days": (None if train_memory_days is None
                                                  else int(train_memory_days)),
        },
    )


def _safe_report(result) -> dict:
    try:
        report = result.full_report(trading_days=365, scope="full")
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}
    keep = ("sharpe", "total_return_pct", "num_trades", "max_drawdown_pct",
            "profit_factor", "win_rate", "cagr", "sortino")
    out = {}
    for key in keep:
        value = report.get(key)
        if isinstance(value, np.generic):
            value = value.item()
        out[key] = value
    return out


def _jsonable(value):
    """Keep only strict-JSON scalar/sequence values; engine Frames are dropped."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return None


def _safe_trace(meta: dict) -> dict:
    return {key: _jsonable(value) for key, value in dict(meta or {}).items()
            if value is None or isinstance(value, (str, bool, int, float, list, tuple, np.generic))}


def _scrub_nonfinite(value, path: str = ""):
    """Strict JSON: a non-finite number becomes null plus a recorded reason."""
    import math

    if isinstance(value, np.generic):
        return _scrub_nonfinite(value.item(), path)
    if isinstance(value, float):
        if math.isnan(value):
            return None, {path or "$": "NAN"}
        if math.isinf(value):
            return None, {path or "$": "POS_INF" if value > 0 else "NEG_INF"}
        return value, {}
    if isinstance(value, dict):
        out, bad = {}, {}
        for key, item in value.items():
            clean, reasons = _scrub_nonfinite(item, f"{path}.{key}" if path else str(key))
            out[str(key)] = clean
            bad.update(reasons)
        return out, bad
    if isinstance(value, (list, tuple)):
        out, bad = [], {}
        for position, item in enumerate(value):
            clean, reasons = _scrub_nonfinite(item, f"{path}[{position}]")
            out.append(clean)
            bad.update(reasons)
        return out, bad
    return value, {}


def _scrub_payload(payload: dict) -> dict:
    clean, nonfinite = _scrub_nonfinite(_jsonable(payload))
    if nonfinite:
        clean["nonfinite_values"] = dict(sorted(nonfinite.items()))
    return clean


def _daily_equity(equity: pd.Series) -> list[list]:
    daily = equity.resample("1D").last().ffill().dropna()
    return [[moment.isoformat(), float(value)] for moment, value in daily.items()]


def _account_payload(*, equity, positions, fills: list[dict], index: pd.DatetimeIndex,
                     fills_source: str, engine_report: dict | None = None) -> dict:
    equity = np.asarray(equity, dtype=float).reshape(-1)
    positions = np.asarray(positions, dtype=float).reshape(-1)
    curve = pd.Series(equity, index=index)
    return {
        "equity_last": float(equity[-1]) if equity.size else None,
        "equity_first": float(equity[0]) if equity.size else None,
        "equity_daily": _daily_equity(curve) if len(index) else [],
        "bars": int(equity.size),
        "start": str(index[0]) if len(index) else None,
        "end": str(index[-1]) if len(index) else None,
        "positions_last": float(positions[-1]) if positions.size else None,
        "fills": fills,
        "fill_count": len(fills),
        "fills_source": fills_source,
        "engine_report": engine_report or {},
    }


def _event_account_payload(alpha_id: str, frame: pd.DataFrame, params_by_fold: dict,
                           cutoffs: Sequence[str], idx: pd.DatetimeIndex, *,
                           one_way_fee: float, slippage_bps: float,
                           account_capital: float,
                           engine_report_level: str | None = None) -> dict:
    """Deploy the selected params through the actual native-event account."""
    from ..integration.event_account import run_event_account

    folds = sorted(params_by_fold, key=lambda key: int(key))
    if not folds:
        return {"status": "NO_FOLD", "equity_last": None, "fills": [], "fill_count": 0}
    moments = [pd.Timestamp(value).tz_localize("UTC") if pd.Timestamp(value).tzinfo is None
               else pd.Timestamp(value) for value in cutoffs]
    first_fold = int(folds[0])
    first_cutoff = moments[first_fold]
    initial = VersionWindow(
        f"{alpha_id}-initial", dict(params_by_fold[folds[0]]),
        int(idx.searchsorted(first_cutoff, side="left")), "initial",
    )
    schedule = [
        VersionWindow(
            f"{alpha_id}-{key}", dict(params_by_fold[key]),
            int(idx.searchsorted(moments[int(key)], side="left")),
            f"activation-{key}",
        )
        for key in folds[1:]
    ]
    run = run_event_account(
        alpha_id, frame, initial=initial, schedule=schedule,
        initial_capital=float(account_capital),
        one_way_fee=one_way_fee, slippage_bps=slippage_bps,
        report_level=engine_report_level,
    )
    equity = pd.Series(np.asarray(run.equity, dtype=float), index=run.index)
    peak = equity.cummax()
    drawdown = float(((peak - equity) / peak.replace(0.0, np.nan)).max() * 100.0)
    return {
        "status": run.status,
        "equity_last": float(run.equity[-1]) if len(run.equity) else None,
        "equity_first": float(run.equity[0]) if len(run.equity) else None,
        "equity_daily": _daily_equity(equity) if len(equity) else [],
        "engine_report": {
            "sharpe": _annualised_sharpe(equity, 365) if len(equity) > 1 else None,
            "total_return_pct": (float(equity.iloc[-1] / equity.iloc[0] - 1.0) * 100.0
                                 if len(equity) > 1 and equity.iloc[0] else None),
            "num_trades": int(run.engine_fill_count),
            "max_drawdown_pct": drawdown if len(equity) else None,
        },
        "entries": int(run.entries),
        "engine_fill_count": int(run.engine_fill_count),
        "fills": [
            {"bar_index": int(f["bar_index"]), "side": int(f["side"]), "qty": float(f["qty"]),
             "price": float(f["price"]), "fee": float(f["fee"]), "tag": str(f.get("tag", ""))}
            for f in run.fills
        ],
        "fill_count": len(run.fills),
        "fills_source": "integration.event_account.run_event_account",
        "versions": run.version_by_bar[:8],
        "unmapped_intents": run.unmapped_intents[:5],
        "rejections": run.rejections[:5],
        "fee_binding": bound_fee_kwargs(one_way_fee),
    }


__all__ = [
    "ALLOC_PER_TRADE",
    "ACCOUNT_CAPITAL",
    "CALENDAR_FIRST_CUTOFF",
    "CALENDAR_TEST_DAYS",
    "CALENDAR_TRAIN_DAYS",
    "CutoffSchedule",
    "CutoffWalkForwardEngine",
    "EventAccountScorer",
    "MODE",
    "METRIC",
    "ProviderError",
    "SCHEDULE",
    "ZeroSignalStrategy",
    "calendar_cutoffs",
    "engine_param_ranges",
    "regime_cutoffs",
    "run_cutoff_walk_forward",
]
