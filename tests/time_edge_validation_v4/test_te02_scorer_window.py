"""TE-02 scorer memory regression: the engine owns only the account window.

Before this repair ``PreparedAccount.run`` handed the engine the full causal
history frame even though the account begins at ``account_start``. The engine's
audit replay then materialized one event-phase row per phase per history bar
(~4.8M object rows for the A-SC pilot market), which exhausted the worker's
4 GiB cap. These bounded synthetic cases fail on the old path and pass on the
windowed path; no financial engine is imported.
"""
import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.time_edge import execution
from crypto_regime_lab.time_edge.execution import ClockedStrategy
from crypto_regime_lab.experiments.time_edge_contracts import ContractError

PHASES_PER_BAR = 10


def bars(n):
    index = pd.date_range("2020-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.,"volume":1.},index=index)


def selection(ready_at):
    return [{"selection_id":"s","params":{"AP":5,"coeff":2,"novolumedata":False,
             "src_col":"close","alpha.condition_threshold":50},
             "cutoff":"2020-01-01T00:00:00Z","ready_at":ready_at}]


def context(frame, i):
    from quantbt.core.reactive import NativeStrategyContext
    return NativeStrategyContext(bar_index=i,timestamp=frame.index[i],
        **{c:np.array([frame[c].iloc[i]]) for c in ("open","high","low","close","volume")},
        equity=20000.,available_equity=20000.,initial_margin=0.,maintenance_margin=0.,
        positions={"S":0.},fills_this_bar=(),order_events_this_bar=(),active_orders=(),
        liquidated=False,symbols=("S",))


class FakeResult:
    def __init__(self, n):
        self.equity=np.full(n,20000.)
        self.positions=np.zeros(n)
        self.fills=[]
        # The audit guard requires the primary-session audit artifacts.
        self.metadata={"canonical_trace_row_count":n,
                       "accounting_ledger_v1":pd.DataFrame({"equity_actual":[20000.]})}
        self.diagnostics=pd.DataFrame()
        self.margin=pd.DataFrame()
        self.fees=pd.DataFrame()
        self.funding=pd.DataFrame()


def harness(monkeypatch):
    calls=[]
    class FakeRunner:
        def __init__(self,data): self.data=data
        def run(self,strategy,*,report_level):
            assert report_level == "audit"
            calls.append(("run",len(self.data),(len(self.data)-1)*PHASES_PER_BAR+1))
            return FakeResult(len(self.data))
        def run_window(self,strategy,*,start_bar,end_bar,report_level):
            calls.append(("run_window",end_bar,(end_bar-1)*PHASES_PER_BAR+1))
            raise AssertionError("engine was handed history before the account window")
    class FakeEndpoint:
        def prepare_native_event_strategy(self,*,data): return FakeRunner(data)
        def simulate(self,*,data,strategy):
            calls.append(("simulate",len(data),(len(data)-1)*PHASES_PER_BAR+1))
            return FakeResult(len(data))
    monkeypatch.setattr(execution,"endpoint",lambda **kw: FakeEndpoint())
    return calls


def test_engine_materializes_only_the_account_window(monkeypatch):
    history,window_bars=2*1440,1440
    frame=bars(history+window_bars)
    start=frame.index[history]
    calls=harness(monkeypatch)
    account=execution.PreparedAccount(frame)
    run=account.run("A-SC",selection(start.isoformat()),account_start=start)
    assert run["status"] == "EVALUATED"
    assert run["engine_absolute_start_bar"] == history
    assert run["index"].equals(frame.index[history:])
    # The engine's immutable market and its audit phase trace are bounded by the
    # account window. The old path ran on the full frame: 5760 bars and 57591
    # phase rows instead of 1440 and 14391.
    assert calls == [("run",window_bars,(window_bars-1)*PHASES_PER_BAR+1)]
    full_rows=(history+window_bars-1)*PHASES_PER_BAR+1
    assert calls[0][2] < full_rows/2


def test_cold_account_also_runs_on_the_window(monkeypatch):
    history,window_bars=2*1440,1440
    frame=bars(history+window_bars)
    start=frame.index[history]
    calls=harness(monkeypatch)
    run=execution.PreparedAccount(frame).run("A-SC",selection(start.isoformat()),
                                             account_start=start,cold=True)
    assert run["index"].equals(frame.index[history:])
    assert calls == [("simulate",window_bars,(window_bars-1)*PHASES_PER_BAR+1)]


def test_engine_offset_restores_absolute_bar_coordinates():
    frame=bars(60)
    start=frame.index[30]
    strategy=ClockedStrategy("A-SC",frame,selection(frame.index[-1].isoformat()),
                             account_start=start,engine_offset=30)
    strategy.on_bar_close(context(frame,0))
    assert strategy.version_runs[0]["start_bar"] == 30
    strategy.on_bar_close(context(frame,1))
    assert strategy.version_runs[0]["end_bar_exclusive"] == 32
    assert strategy.callback_count == 2


def test_negative_engine_offset_refused():
    frame=bars(10)
    with pytest.raises(ContractError,match="offset"):
        ClockedStrategy("A-SC",frame,selection(frame.index[0].isoformat()),
                        account_start=frame.index[0],engine_offset=-1)
