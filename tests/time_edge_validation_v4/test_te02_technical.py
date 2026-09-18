"""TE02/TG02,03,04,10,11: real contracts and callback fixtures, no financial engine."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.time_edge.storage import Ledger, EvidenceError, save, read
from crypto_regime_lab.time_edge.schedule import triggers, matched_cadence
from crypto_regime_lab.time_edge.metrics import account_returns, describe, window_activity, materialize_delta
from crypto_regime_lab.time_edge.execution import decision_frame, validate_market, ClockedStrategy, DecisionProxy, endpoint
from crypto_regime_lab.experiments.time_edge_contracts import ContractError


def bars(n=2880):
    index = pd.date_range("2020-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.,"volume":1.},index=index)


def context(frame, i, *, equity=20000., position=0., active_orders=(), fills=()):
    from quantbt.core.reactive import NativeStrategyContext
    return NativeStrategyContext(bar_index=i,timestamp=frame.index[i],
        **{c:np.array([frame[c].iloc[i]]) for c in ("open","high","low","close","volume")},
        equity=equity,available_equity=equity,initial_margin=0.,maintenance_margin=0.,
        positions={"S":position},fills_this_bar=fills,order_events_this_bar=(),active_orders=active_orders,
        liquidated=False,symbols=("S",))


def emission(at, state=0, **kw):
    return {"available_at":at,"model_id":"v1","model_fit_cutoff":"2019-12-31T00:00:00Z",
        "model_ready_at":"2020-01-01T00:00:00Z","state_namespace":"v1","state_id":state,
        "decision_eligible":True,"quality_status":"OK","feature_schema_hash":"f","model_design_hash":"d",**kw}


def test_immutable_publication(lab_tmp):
    p=lab_tmp/"record.json"; h=save(p,{"a":1}); assert save(p,{"a":1}) == h
    with pytest.raises(EvidenceError): save(p,{"a":2})
    assert read(p) == {"a":1}


def test_resume_budget_and_failure(lab_tmp):
    ledger=Ledger(lab_tmp,{"code":"v1"},10)
    first=ledger.begin({"task":1},6); ledger.finish(first,status="FAILED",wall=4,reason="captured failure")
    assert ledger.cached({"task":1}) is None
    with pytest.raises(EvidenceError,match="EXHAUSTED"): ledger.begin({"task":2},7)
    ledger.close(); ledger=Ledger(lab_tmp,{"code":"v1"},10)
    assert ledger.spent() == 4
    second=ledger.begin({"task":1},6); ledger.finish(second,status="COMPLETE",wall=5,result={"lab_run_id":"test","x":4})
    assert ledger.cached({"task":1})["x"] == 4
    assert ledger.status()["remaining_wall_seconds"] == 1
    ledger.close()


def test_crash_charges_full_reservation(lab_tmp):
    ledger=Ledger(lab_tmp,{"code":"v1"},10)
    ledger.begin({"task":1},8)
    with ledger.lock(): assert ledger.recover_interrupted() == 1
    assert ledger.spent() == 8
    with pytest.raises(EvidenceError): ledger.begin({"task":1},8)
    ledger.close()


@pytest.mark.parametrize("identity,budget", [({"code":"v2"},10),({"code":"v1"},11)])
def test_resume_drift_refused(lab_tmp,identity,budget):
    Ledger(lab_tmp,{"code":"v1"},10).close()
    with pytest.raises(EvidenceError,match="drift"): Ledger(lab_tmp,identity,budget)


def test_cache_tamper_refused(lab_tmp):
    ledger=Ledger(lab_tmp,{},10); aid=ledger.begin("x",5)
    ledger.finish(aid,status="COMPLETE",wall=1,result={"a":1})
    (lab_tmp/f"attempts/{aid}/result.json").write_text('{"a":2}')
    with pytest.raises(EvidenceError,match="drift"): ledger.cached("x")
    ledger.close()


def test_two_workers_refused(lab_tmp):
    a=Ledger(lab_tmp,{},10); b=Ledger(lab_tmp,{},10)
    with a.lock():
        with pytest.raises(EvidenceError,match="another worker"):
            with b.lock(): pass
    a.close(); b.close()


def test_initial_max_age_and_no_future_ready():
    tape=[emission("2020-01-01T04:00:00Z"),emission("2020-06-29T04:00:00Z")]
    result=triggers(tape,initial_ready="2020-01-01T00:00:00Z",end="2021-01-01T00:00:00Z")
    assert [r["reason"] for r in result["triggers"]] == ["MAX_AGE"]
    tape[-1]["model_ready_at"]="2021-01-01T00:00:00Z"
    result=triggers(tape,initial_ready="2020-01-01T00:00:00Z",end="2021-01-01T00:00:00Z")
    assert not result["triggers"] and result["rejected"]


def test_missing_eligibility_and_namespace_not_transition():
    tape=[emission("2020-01-01T04:00:00Z"),emission("2020-03-01T00:00:00Z",1),emission("2020-03-01T04:00:00Z",1)]
    for r in tape[1:]: del r["decision_eligible"]
    args=dict(initial_ready="2020-01-01T00:00:00Z",end="2021-01-01T00:00:00Z")
    assert len(triggers(tape,**args)["rejected"]) == 2
    for r in tape[1:]: r.update(decision_eligible=True,state_namespace="v2",model_id="v2")
    assert not triggers(tape,**args)["triggers"]


def test_controller_needs_two_and_same_time_rejected():
    tape=[emission("2020-01-01T04:00:00Z"),emission("2020-03-01T00:00:00Z",1),emission("2020-03-01T04:00:00Z",1)]
    args=dict(initial_ready="2020-01-01T00:00:00Z",end="2021-01-01T00:00:00Z")
    assert not triggers(tape[:2],**args)["triggers"]
    assert len(triggers(tape,**args)["triggers"]) == 1
    with pytest.raises(ContractError): triggers(tape+[tape[-1]],**args)


def test_matched_training_cost_and_nonfinite():
    assert matched_cadence(40,10,days=360) == 90
    with pytest.raises(ContractError): matched_cadence(float("nan"),10,days=360)


def test_first_fee_and_window_mask():
    frame=bars(3*1440); equity=np.r_[np.full(1440,19990.),np.full(1440,20189.9),np.full(1440,20189.9)]
    rows=account_returns(equity,frame.index,initial_equity=20000.,start="2020-01-01T00:00:00Z",end="2020-01-04T00:00:00Z")
    assert rows[0][1] == pytest.approx(-.0005)
    sliced=account_returns(equity,frame.index,initial_equity=20000.,start="2020-01-02T00:00:00Z",end="2020-01-04T00:00:00Z")
    assert sliced == rows[1:] and sliced[0][1] == pytest.approx(.01)


def test_no_missing_bar_forward_fill():
    frame=bars().drop(bars().index[42])
    with pytest.raises(ContractError,match="gaps"): validate_market(frame)
    with pytest.raises(ContractError,match="gaps"): account_returns(np.ones(len(frame))*20000,frame.index,initial_equity=20000,start="2020-01-01T00:00:00Z",end="2020-01-03T00:00:00Z")


def test_pf_loss_only_and_initial_dd():
    result=describe([("2020-01-01",-.1),("2020-01-02",0.)])
    assert result["daily_observation_pf"]["value"] == 0
    assert result["max_drawdown"] == pytest.approx(.1)
    assert result["trade_pf"]["value"] is None


def test_window_fill_counts_are_not_whole_account():
    frame=bars(); fills=[dict(bar_index=b,qty=1.,price=100.,fee=.04,tag="entry",position_before=0.,position_after=1.) for b in (50,1500)]
    result=window_activity(fills,frame.index,np.full(len(frame),20000.),start=frame.index[0],end=frame.index[1440],initial_equity=20000.)
    assert result["fill_count"] == 1 and result["completed_campaign_count"] == 0
    assert result["turnover"] == pytest.approx(.005)


def test_threshold_flat_days_and_training_only():
    cell={"days":["2020-01-01","2020-01-02"],"fills":[{"timestamp":"2020-01-01T12:00:00Z","pre_fill_equity":20000.,"notional":2000.}]}
    result=materialize_delta({"c":cell},expected_cells=["c"],cutoff="2020-01-03T00:00:00Z")
    assert result["value"] == pytest.approx(.000025)
    with pytest.raises(ContractError): materialize_delta({"c":cell},expected_cells=["c"],cutoff="2020-01-02T00:00:00Z")
    del cell["fills"][0]["pre_fill_equity"]
    with pytest.raises(KeyError): materialize_delta({"c":cell},expected_cells=["c"],cutoff="2020-01-03T00:00:00Z")


@pytest.mark.parametrize("minutes",[15,60])
def test_htf_available_only_after_completed_bar(minutes):
    frame=bars(2*minutes+5); htf,mapping=decision_frame(frame,minutes)
    assert len(htf) == 2 and mapping[minutes-2] == -1 and mapping[minutes-1] == 0
    changed=frame.copy(); changed.iloc[minutes:,changed.columns.get_loc("close")]=10000
    other,_=decision_frame(changed,minutes)
    pd.testing.assert_series_equal(htf.iloc[0],other.iloc[0])


def test_explicit_actual_quantbt_constructor_binding():
    actual=endpoint().config
    assert actual.execution_contract == "event_lifecycle_v3_next_open"
    assert actual.native_backend == "rust" and actual.backend_policy == "certified_only"
    assert actual.v2_fee_rate == .0004 and actual.account.leverage == 1


def test_fill_index_uses_completed_decision_bar():
    from crypto_regime_lab.alphas.contracts import Fill, IntentKind
    seen=[]; adapter=SimpleNamespace(market=SimpleNamespace(set_cursor=lambda i:None),on_fill=lambda f:seen.append(f))
    proxy=DecisionProxy(adapter,np.array([-1,0,0,1]))
    fill=Fill(index=2,side=1,quantity=1.,price=100.,intent_kind=IntentKind.ENTER_LONG)
    proxy.on_fill(fill)
    assert seen[0].index == 0 and fill.index == 2
    with pytest.raises(ContractError): proxy.on_fill(replace(fill,index=0))


def test_no_shadow_decisions_no_double_warmup(monkeypatch):
    from crypto_regime_lab.time_edge import execution
    from crypto_regime_lab.alphas.contracts import BarDecision
    built=[]
    class Stub:
        def __init__(self): self.decisions=[]; self.prepares=0; self.calls=[]
        def warmup_bars(self): return 1
        def prepare(self): self.prepares+=1
        def on_bar_close(self,i): self.calls.append(i); return BarDecision(index=i,position_entering_bar=0.,target_after_close=0.)
    def build(*args):
        adapter=Stub(); built.append(adapter); return adapter
    monkeypatch.setattr(execution,"build_adapter",build)
    frame=bars(60); t="2020-01-01T00:30:00Z"
    strategy=ClockedStrategy("A-SC",frame,[{"selection_id":"s","params":{"x":1},"cutoff":t,"ready_at":t}])
    for i in range(29): strategy.on_bar_close(context(frame,i))
    assert not built
    strategy.on_bar_close(context(frame,29))
    assert built[0].prepares == 1 and built[0].calls == [1]
    assert strategy.funnel[-1]["event"] == "ACTIVATE"


def test_protection_domain_failure_retained():
    import quantbt as q
    frame=bars(60); t="2020-01-01T00:00:00Z"
    strategy=ClockedStrategy("A-SC",frame,[{"selection_id":"s","params":{"x":1},"cutoff":t,"ready_at":t}])
    with pytest.raises(ContractError,match="nonpositive"):
        strategy._place(frame.index[0],-1,1.,q.OrderType.LIMIT,price=-5.,kind="protection",bar=0)
    assert strategy.unmapped[0]["value"] == -5


def test_entry_sizing_uses_current_engine_equity():
    from crypto_regime_lab.alphas.contracts import OrderIntent, IntentKind, ExecutionPhase
    frame=bars(60); t="2020-01-01T00:00:00Z"
    strategy=ClockedStrategy("A-SC",frame,[{"selection_id":"s","params":{"x":1},"cutoff":t,"ready_at":t}])
    intent=OrderIntent(kind=IntentKind.ENTER_LONG,decision_index=0,earliest_phase=ExecutionPhase.NEXT_OPEN,reason="sizing contract fixture")
    first=strategy._intent_commands(intent,context(frame,0,equity=20000.))[0]
    second=strategy._intent_commands(intent,context(frame,0,equity=10000.))[0]
    assert first.qty == 20. and second.qty == 10.


def test_selection_only_actual_mode4_and_persistent_resume(monkeypatch,lab_tmp,lab_root):
    """Real installed optimizer, synthetic scorer-account fixture; ZERO engine runs."""
    from crypto_regime_lab.time_edge import execution
    from crypto_regime_lab.time_edge.storage import read
    import quantbt.walkforward as wfo
    idx=pd.date_range("2020-01-01",periods=181*1440,freq="min",tz="UTC")
    frame=pd.DataFrame({c:np.ones(len(idx)) for c in ("open","high","low","close","volume")},index=idx)
    cutoff=idx[-1]+pd.Timedelta(minutes=1)
    class SyntheticReportedAccount:
        total_calls=0
        def __init__(self,frame,**kwargs): self.runs=0; self.frame=frame
        def run(self,alpha,selections,account_start):
            self.runs+=1; SyntheticReportedAccount.total_calls+=1
            index=self.frame.index[self.frame.index >= account_start]
            shift=(sum(len(str(v)) for v in selections[0]["params"].values())%10)*.00001
            returns=.0001+shift+.001*np.sin(np.arange(180))
            eq=np.repeat(20000*np.cumprod(1+returns),1440)
            return {"status":"EVALUATED","equity":eq,"index":index,"fills":[],"engine_metadata":{},"commands":[],"order_events":[],"wall_seconds":0.,"callback_count":0}
    monkeypatch.setattr(execution,"PreparedAccount",SyntheticReportedAccount)
    binding=read(lab_root/"configs/time_edge_validation_v4/mode4_binding_r01.json")
    old_callback=wfo.logging_callback
    result=execution.select_only(frame,alpha_id="A-SC",cutoff=cutoff,binding=binding,evidence_dir=lab_tmp,lab_run_id="unit-mode4")
    assert result["status"] == "SELECTED" and result["deployment_runs"] == 0
    assert result["selected"]["selection_metadata"]["oos_used_for_selection"] is False
    assert len(list(lab_tmp.glob("optuna-*.json"))) == 32
    assert len(list(lab_tmp.glob("trial-*.json"))) > 0
    assert wfo.logging_callback is old_callback
    count=SyntheticReportedAccount.total_calls
    repeated=execution.select_only(frame,alpha_id="A-SC",cutoff=cutoff,binding=binding,evidence_dir=lab_tmp,lab_run_id="unit-mode4")
    assert repeated["params"] == result["params"]
    assert repeated["selected"]["objective"] == result["selected"]["objective"]
    assert SyntheticReportedAccount.total_calls == count and repeated["persistent_candidate_cache_hits"] > 0
