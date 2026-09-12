"""1m QuantBT execution, completed-HTF decisions, and selection-only Mode 4.

QuantBT remains the sole account/fill authority. This module binds LAB adapters
and time coordinates to the pinned public endpoint and optimizer.
"""
from dataclasses import asdict, replace
import math
import time

import numpy as np
import pandas as pd

from ..alphas.base import MarketSlice, IntentKind
from ..experiments.evaluator import build_adapter
from ..experiments.dynamic_fold_provider import CutoffWalkForwardEngine, ZeroSignalStrategy, engine_param_ranges, _scrub_payload
from ..experiments.time_edge_contracts import ContractError
from ..integration.event_account import EventAccountStrategy, _position
from ..integration.continuous_account import VersionWindow
from .metrics import account_returns, window_activity, describe
from .storage import digest, save, read, file_digest
from .eligibility import require_history

CONTRACT = "event_lifecycle_v3_next_open"
DECISION_MINUTES = {"A-SC":15, "A-HMA":60, "A-VWAP":15, "A-HASH":15}


def validate_market(frame):
    if frame.empty or frame.index.tz is None or str(frame.index.tz) != "UTC":
        raise ContractError("nonempty UTC 1m market required")
    if not frame.index.equals(pd.date_range(frame.index[0], frame.index[-1], freq="min")):
        raise ContractError("1m data gaps/duplicates/order violation")
    x = frame[["open","high","low","close","volume"]].to_numpy(float)
    if not np.isfinite(x).all() or (x[:,:4] <= 0).any() or (x[:,4] < 0).any():
        raise ContractError("invalid OHLCV domain")
    if (x[:,1] < x[:,[0,2,3]].max(axis=1)).any() or (x[:,2] > x[:,[0,1,3]].min(axis=1)).any():
        raise ContractError("invalid OHLC geometry")


def decision_frame(frame, minutes):
    grouped = frame.resample(f"{minutes}min", closed="left", label="left", origin="epoch")
    bars = grouped.agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"})
    bars = bars.loc[grouped["close"].count() == minutes]
    # Available at the end of the final 1m bar, not its open or the HTF open.
    available = bars.index + pd.Timedelta(minutes=minutes)
    closed_at = frame.index + pd.Timedelta(minutes=1)
    mapping = np.searchsorted(available.asi8, closed_at.asi8, side="right")-1
    return bars, mapping


class DecisionProxy:
    """Fill callbacks use the last completed decision bar, never a forming bar."""
    def __init__(self, adapter, mapping):
        self.inner, self.mapping = adapter, mapping

    def on_fill(self, fill):
        index = int(self.mapping[fill.index])
        if index < 0:
            raise ContractError("fill before any eligible decision bar")
        self.inner.market.set_cursor(index)
        return self.inner.on_fill(replace(fill, index=index))


class ClockedStrategy(EventAccountStrategy):
    def __init__(self, alpha_id, frame, selections, *, allocation=.1, account_start=None):
        self.account_start=None if account_start is None else pd.Timestamp(account_start)
        self.decisions_frame, self.mapping = decision_frame(frame, DECISION_MINUTES[alpha_id])
        if self.decisions_frame.empty or not selections:
            raise ContractError("decision history and initial selection required")
        self.selection_records = list(selections)
        for selection in self.selection_records:
            if pd.Timestamp(selection["ready_at"]) < pd.Timestamp(selection["cutoff"]):
                raise ContractError("selection ready before cutoff")
        ready = [pd.Timestamp(s["ready_at"]) for s in selections]
        if ready != sorted(ready) or len(set(s["selection_id"] for s in selections)) != len(selections):
            raise ContractError("ordered unique selections required")
        market = MarketSlice(*[self.decisions_frame[c].to_numpy(float) for c in ("open","high","low","close","volume")], index=self.decisions_frame.index)
        # Prevent legacy initialization/warmup; new lifecycle below owns activation.
        initial = VersionWindow("FLAT_UNTIL_READY", {}, len(frame)+1, "placeholder")
        super().__init__(alpha_id, frame, market, initial=initial, schedule=[])
        self.allocation = allocation
        if not 0 < allocation <= .1:
            raise ContractError("registered allocation cap is 10% at leverage one")
        self.next_selection = 0
        self.pending = None
        self.last_decision = -1
        self.version_runs = []
        self.funnel = []
        self.callback_count = 0
        self.decision_count = 0
        self._first_order_versions = set()

    def _place(self, timestamp, side, qty, order_type, **kwargs):
        for key in ("price", "trigger"):
            value = kwargs.get(key)
            if value is not None and (not math.isfinite(value) or value <= 0):
                record = {"kind":"candidate_domain_error", "parameter_version":self._version(),
                          "bar":kwargs["bar"], "field":key, "value":value,
                          "reason":"required protective price is nonpositive/nonfinite"}
                self.unmapped.append(record)
                # Reject the entire candidate; never silently remove protection.
                raise ContractError(str(record))
        command=super()._place(timestamp, side, qty, order_type, **kwargs)
        version=self._version()
        if version not in self._first_order_versions:
            self._first_order_versions.add(version)
            self.funnel.append({"event":"FIRST_ORDER","selection_id":version,"bar":kwargs["bar"],
                                "at":(self.frame.index[kwargs["bar"]]+pd.Timedelta(minutes=1)).isoformat(),
                                "native_bar_label":str(timestamp),"kind":kwargs["kind"],"order_id":command.order_id})
        return command

    def _apply_fills(self, context, bar):
        from .model import jsonable
        first=len(self.fills_out)
        commands=super()._apply_fills(context,bar)
        for offset,(row,event) in enumerate(zip(self.fills_out[first:],context.fills_this_bar)):
            row.update(parameter_version=self._order_version.get(row["order_id"]),
                       sequence=first+offset,sequence_source="observed_callback_order",
                       campaign_id=getattr(event,"campaign_id",None),cycle_id=getattr(event,"cycle_id",None),
                       level_id=getattr(event,"level_id",None),timestamp=str(event.timestamp),
                       engine_fill_metadata=jsonable(dict(getattr(event,"metadata",{}) or {})))
        return commands

    def _observe_order_events(self, context, bar):
        from .model import jsonable
        first=len(self.order_events_out)
        super()._observe_order_events(context,bar)
        for row,event in zip(self.order_events_out[first:],context.order_events_this_bar):
            row["native_event"]=jsonable(asdict(event))

    def _intent_commands(self, intent, context):
        self.unit_notional = self.allocation*float(context.equity)
        if not math.isfinite(self.unit_notional) or self.unit_notional <= 0:
            raise ContractError("engine equity unusable for entry sizing")
        return super()._intent_commands(intent, context)

    def _prepare_pending(self, selection):
        adapter = build_adapter(self.alpha_id, selection["params"], self.market)
        # Indicators may consume causal history. Never call _decide while warming:
        # it would create phantom pending orders in an inactive adapter.
        adapter.prepare(); adapter._prepared = True
        return selection, adapter

    def on_bar_close(self, context):
        bar = int(context.bar_index); self.callback_count += 1
        if self.account_start is not None and self.frame.index[bar] < self.account_start:
            if getattr(context,"fills_this_bar",None):
                raise ContractError("fill before the registered account window")
            return []
        now = self.frame.index[bar]+pd.Timedelta(minutes=1)
        decision_bar = int(self.mapping[bar])
        commands = []
        self._observe_order_events(context, bar)
        if self.adapter is not None:
            commands.extend(self._apply_fills(context, bar))
        elif getattr(context, "fills_this_bar", None):
            raise ContractError("engine fill has no active parameter owner")
        while self.next_selection < len(self.selection_records):
            record = self.selection_records[self.next_selection]
            if pd.Timestamp(record["ready_at"]) > now:
                break
            if self.pending:
                self.funnel.append({"event":"SUPERSEDED", "selection_id":self.pending[0]["selection_id"], "bar":bar})
            self.pending = self._prepare_pending(record)
            self.next_selection += 1
            self.funnel.append({"event":"READY", "selection_id":record["selection_id"], "bar":bar})
        # Active entry orders are commitments too; flat position alone is not enough.
        live_entry = any(getattr(o,"tag",None) == "entry" for o in (getattr(context,"active_orders",None) or []))
        if self.pending and abs(_position(context)) <= 1e-9 and not live_entry:
            record, candidate = self.pending
            history_ready=decision_bar >= candidate.warmup_bars()
            if history_ready and self.alpha_id == "A-VWAP":
                features=candidate.features
                history_ready=bool(features.htf_available_from[decision_bar] >= features.htf_warmup_buckets and np.isfinite(features.htf_ema[decision_bar]))
            if history_ready:
                commands.extend(self._stale_protection_cancels(context, bar, self._version()))
                self.adapter = DecisionProxy(candidate, self.mapping)
                self.active = VersionWindow(record["selection_id"], record["params"], bar, record["selection_id"])
                self.pending = None
                self.funnel.append({"event":"ACTIVATE", "selection_id":record["selection_id"], "bar":bar,
                                    "at":now.isoformat(), "cutoff":record["cutoff"], "model_id":record.get("model_id")})
        version = self._version()
        if not self.version_runs or self.version_runs[-1]["version"] != version:
            self.version_runs.append({"start_bar":bar, "end_bar_exclusive":bar+1, "version":version})
        else:
            self.version_runs[-1]["end_bar_exclusive"] = bar+1
        if self.adapter is not None and decision_bar > self.last_decision:
            # Activation between HTF closes must wait for the next newly closed bar.
            available = self.decisions_frame.index[decision_bar] + pd.Timedelta(minutes=DECISION_MINUTES[self.alpha_id])
            if available == now:
                decision = self.adapter.inner.on_bar_close(decision_bar)
                self.decision_count += 1
                for intent in decision.intents:
                    if intent.kind in (IntentKind.ENTER_LONG,IntentKind.ENTER_SHORT):
                        self.entries += 1
                    commands.extend(self._intent_commands(intent, context))
                # Full intents retained in commands; avoid storing redundant BarDecision objects.
                self.adapter.inner.decisions.clear()
        self.last_decision = max(self.last_decision, decision_bar)
        return commands


def endpoint(*, fee=.0004, slippage=1., native_backend="rust"):
    import quantbt as q
    return q.QuantBTEndpoint.native_event_strategy(
        account=q.AccountConfig(initial_capital=20000., leverage=1.),
        symbols=["S"], fee_rate=fee, fee=2*fee, slippage_bps=slippage,
        use_funding=False, execution_contract=CONTRACT, native_backend=native_backend,
        backend_policy="certified_only", report_level="audit", audit_sink="memory")


class PreparedAccount:
    def __init__(self, frame, *, fee=.0004, slippage=1., native_backend="rust"):
        validate_market(frame)
        self.frame = frame
        started = time.perf_counter()
        self.endpoint = endpoint(fee=fee, slippage=slippage, native_backend=native_backend)
        self.runner = self.endpoint.prepare_native_event_strategy(data=frame)
        self.packing_seconds = time.perf_counter()-started
        self.runs = 0

    def run(self, alpha_id, selections, *, account_start=None, cold=False):
        strategy = ClockedStrategy(alpha_id, self.frame, selections,account_start=account_start)
        started = time.perf_counter()
        try:
            first = 0 if account_start is None or cold else int(self.frame.index.searchsorted(pd.Timestamp(account_start)))
            if cold:
                result = self.endpoint.simulate(data=self.frame,strategy=strategy)
            else:
                result = (self.runner.run(strategy, report_level="audit") if first == 0 else
                          self.runner.run_window(strategy,start_bar=first,end_bar=len(self.frame),report_level="audit"))
        except Exception as exc:
            # Caller's append-only trial evidence retains even a constructor/fill error.
            raise ContractError(f"{type(exc).__name__}: {exc}; unmapped={strategy.unmapped}; rejected={strategy.rejections}") from exc
        self.runs += 1
        equity = np.asarray(result.equity, float).reshape(-1)
        positions = np.asarray(result.positions, float).reshape(-1)
        index = self.frame.index[first:]
        if len(equity) != len(index) or len(positions) != len(index):
            raise ContractError("prepared engine window returned unexpected mark coordinates")
        for fill in strategy.fills_out:
            fill["absolute_bar_index"] = fill["bar_index"]
            fill["bar_index"] -= first
        raw_meta = dict(getattr(result,"metadata",{}) or {})
        tables = {k:v for k,v in raw_meta.items() if isinstance(v,(pd.DataFrame,pd.Series))}
        tables.update({"engine_diagnostics":result.diagnostics,"engine_margin":result.margin,
                       "engine_fees":result.fees,"engine_funding":result.funding})
        meta = _scrub_payload({k:({"retained_engine_table":k} if k in tables else v) for k,v in raw_meta.items()})
        observed = len(getattr(result, "fills", None) or [])
        valid = not strategy.unmapped and not strategy.rejections and observed == len(strategy.fills_out)
        return {"status":"EVALUATED" if valid else "NOT_EVALUATED", "equity":equity, "positions":positions,
                "index":index, "fills":strategy.fills_out, "commands":strategy.commands_out,
                "order_events":strategy.order_events_out, "version_runs":strategy.version_runs,
                "funnel":strategy.funnel, "unmapped":strategy.unmapped, "rejections":strategy.rejections,
                "engine_fill_count":observed, "engine_metadata":meta, "engine_tables":tables,"requested_contract":CONTRACT,
                "wall_seconds":time.perf_counter()-started, "packing_seconds":self.packing_seconds,
                "callback_count":strategy.callback_count, "decision_count":strategy.decision_count,
                "engine_absolute_start_bar":first,"terminal_position":float(positions[-1]), "terminal_equity":float(equity[-1])}


class TrainingScorer:
    """One engine account per unique candidate; subwindows reuse canonical returns."""
    def __init__(self, prepared, alpha_id, train_start, cutoff, evidence_dir, lab_run_id):
        self.prepared, self.alpha_id = prepared, alpha_id
        self.start, self.cutoff = pd.Timestamp(train_start), pd.Timestamp(cutoff)
        self.directory, self.lab_run_id = evidence_dir, lab_run_id
        self.cache = {}; self.calls = 0
        self.cache_hits = 0

    def __call__(self, **task):
        return self.score_batch([task])[0]

    def score_batch(self, tasks):
        return [self._score(t) for t in tasks]

    def _score(self, task):
        self.calls += 1
        params = dict(task["params"]); key = digest(params)
        if key not in self.cache:
            path = self.directory/f"candidate-{key}.json"
            seal = self.directory/f"candidate-{key}.sha256.json"
            if path.exists() and seal.exists():
                if file_digest(path) != read(seal)["sha256"]:
                    raise ContractError("partial candidate cache hash drift")
                record = read(path)
                if record["params"] != params or record["cutoff"] != self.cutoff.isoformat() or record["lab_run_id"] != self.lab_run_id:
                    raise ContractError("partial candidate cache identity drift")
                if record["status"] == "FAILED_TECHNICAL":
                    raise ContractError(record["reason"])
                self.cache[key] = record; self.cache_hits += 1
            elif path.exists() or seal.exists():
                raise ContractError("incomplete candidate publication requires a new superseding task; do not overwrite evidence")
        if key not in self.cache:
            record = {"lab_run_id":self.lab_run_id, "params":params, "cutoff":self.cutoff.isoformat()}
            try:
                run = self.prepared.run(self.alpha_id, [{"selection_id":key,"params":params,
                    "cutoff":self.start.isoformat(),"ready_at":self.start.isoformat()}], account_start=self.start)
                if run["status"] != "EVALUATED":
                    raise ContractError("engine account fidelity failed")
                lo,hi=self.start.ceil("D"),self.cutoff.floor("D")
                rows = account_returns(run["equity"],run["index"],initial_equity=20000.,start=lo,end=hi)
                daily_activity=[]
                for date,_ in rows:
                    day=pd.Timestamp(date,tz="UTC")
                    daily_activity.append({"date":date,**window_activity(run["fills"],run["index"],run["equity"],start=day,end=day+pd.Timedelta(days=1),initial_equity=20000.)})
                record.update(status="EVALUATED", daily_returns=rows, metrics=describe(rows),
                              fills=run["fills"], engine_metadata=run["engine_metadata"],
                              commands=run["commands"],order_events=run["order_events"],daily_activity=daily_activity,
                              complete_day_start=lo.isoformat(),complete_day_end_exclusive=hi.isoformat(),
                              wall_seconds=run["wall_seconds"], callback_count=run["callback_count"])
            except Exception as exc:
                kind="FAILED_CANDIDATE" if "candidate_domain_error" in str(exc) else "FAILED_TECHNICAL"
                record.update(status=kind, reason=f"{type(exc).__name__}: {exc}", metrics=None)
            self.cache[key] = record
            h=save(path, record); save(seal,{"lab_run_id":self.lab_run_id,"sha256":h})
            if record["status"] == "FAILED_TECHNICAL": raise ContractError(record["reason"])
        record=self.cache[key]
        if record["status"] != "EVALUATED":
            return {"sharpe":float("-inf"),"turnover":float("nan"),"trade_count":float("nan"),"status":"FAILED_CANDIDATE"}
        rows=record["daily_returns"]
        idx = pd.DatetimeIndex(task["index"])
        if idx.empty or idx[0] < self.start or idx[-1] >= self.cutoff:
            raise ContractError("scorer requested data outside the train window")
        lo, hi = idx[0].floor("D"), (idx[-1]+pd.Timedelta(minutes=1)).floor("D")
        if idx[0] != lo or idx[-1]+pd.Timedelta(minutes=1) != hi:
            # Engine subperiods can split mid-day. Score complete UTC days only,
            # record denominators; do not accidentally include partial future days.
            lo = idx[0].ceil("D"); hi = (idx[-1]+pd.Timedelta(minutes=1)).floor("D")
        sample = [r for r in rows if lo <= pd.Timestamp(r[0],tz="UTC") < hi]
        if len(sample) < 2:
            return {"sharpe":float("-inf"),"turnover":0.,"trade_count":0.,"status":"INSUFFICIENT_DAYS"}
        summary = describe(sample)
        selected=[r for r in record["daily_activity"] if lo <= pd.Timestamp(r["date"],tz="UTC") < hi]
        activity={k:sum(r[k] for r in selected) for k in ("fill_count","entry_fill_count","completed_campaign_count","fees")}
        activity["turnover_pre_bar_diagnostic"]=sum(r["turnover"] for r in selected)
        sr = summary["daily_sharpe"]["value"]
        return {"sharpe":float("-inf") if sr is None else sr, "turnover":float("nan"),
                "turnover_reason":"registered pre-fill equity unavailable; pre-bar diagnostic is separate; turnover penalties disabled",
                "trade_count":float(activity["completed_campaign_count"]), "status":"OK" if sr is not None else "ZERO_VARIANCE",
                "daily_count":len(sample), **activity}


def select_only(frame, *, alpha_id, cutoff, binding, evidence_dir, lab_run_id, fee=.0004, slippage=1.):
    import quantbt.walkforward as public_wfo
    from quantbt.walkforward import WalkForwardConfig, WalkForwardFold
    cutoff = pd.Timestamp(cutoff); start = cutoff-pd.Timedelta(days=180)
    if frame.index[-1] >= cutoff:
        raise ContractError("selection receives train/history only; no outer OOS row allowed")
    train = frame.index[(frame.index >= start) & (frame.index < cutoff)]
    if len(train) != 180*1440:
        raise ContractError("selection needs complete registered 180-day train window")
    require_history(frame,alpha_id,start)
    config = WalkForwardConfig(**binding["resolved_config"], metadata={
        **binding["metadata"],"compact_trial_ledger":False})
    scorer = TrainingScorer(PreparedAccount(frame,fee=fee,slippage=slippage),alpha_id,start,cutoff,evidence_dir,lab_run_id)
    class CapturedEngine(CutoffWalkForwardEngine):
        def evaluate_params_is(self, *args, **kwargs):
            record = super().evaluate_params_is(*args, **kwargs)
            save(evidence_dir/f"trial-{record.trial_id:04d}.json",
                 _scrub_payload({"lab_run_id":lab_run_id,"record":asdict(record)}))
            return record
    engine = CapturedEngine(strategy=ZeroSignalStrategy(),config=config,scorer=scorer)
    fold = WalkForwardFold(fold_id=0,train_start=train[0],train_end=train[-1],
        test_start=train[0],test_end=train[-1],train_index=train,test_index=train,
        warmup_index=frame.index[frame.index < start],account_policy="reset_flat")
    started = time.perf_counter()
    original_callback = public_wfo.logging_callback
    def capture_callback(study, trial):
        save(evidence_dir/f"optuna-{trial.number:04d}.json",_scrub_payload({"lab_run_id":lab_run_id,
            "number":trial.number,"state":trial.state.name,"params":trial.params,"value":trial.value,
            "user_attrs":trial.user_attrs}))
        original_callback(study,trial)
    # One isolated worker, no other optimizer thread; restore public callback even
    # on failure. Selection math and Optuna sampler are left untouched.
    public_wfo.logging_callback = capture_callback
    try:
        selected, trials, candidates = engine.optimize_params(
            data=frame,folds=[fold],param_ranges=engine_param_ranges(alpha_id),
            evaluate_oos_candidates=False,random_seed=binding["search_seed"])
    finally:
        public_wfo.logging_callback = original_callback
    record = _scrub_payload({"lab_run_id":lab_run_id,"alpha_id":alpha_id,"cutoff":cutoff.isoformat(),
        "selected":asdict(selected),"trials":[asdict(x) for x in trials],
        "candidates":[asdict(x) for x in candidates],"selector":"installed Mode 4 optimize_params(evaluate_oos_candidates=False)",
        "account_runs":scorer.prepared.runs,"scorer_calls":scorer.calls,"persistent_candidate_cache_hits":scorer.cache_hits,
        "deployment_runs":0,"wall_seconds":time.perf_counter()-started})
    if not math.isfinite(selected.objective):
        record.update(status="NO_ADMISSIBLE_CANDIDATE",params=None)
    else:
        record.update(status="SELECTED",params=dict(selected.params))
    return record
