"""RF-02 event-account acceptance — actual fills, no backdating, follow-ups land.

A02: a version requested after bar 0 is flat until its requested bar.
A04: an on_fill follow-up EXIT_ALL reaches the position.
Engine authority: every fill the adapter saw is one QuantBT produced.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from crypto_regime_lab.alphas.contracts import (
    BarDecision, ExecutionPhase, IntentKind, OrderIntent,
)
from crypto_regime_lab.integration import event_account as EA
from crypto_regime_lab.integration.continuous_account import VersionWindow
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS


def _frame(n: int = 12) -> pd.DataFrame:
    close = 100 + 10 * np.sin(np.arange(n) / 10.0) + 0.05 * np.arange(n)
    return pd.DataFrame({"open": close, "high": close + 0.4, "low": close - 0.4,
                         "close": close, "volume": np.full(n, 1000.0)},
                        index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"))


class _StubAdapter:
    def __init__(self) -> None:
        self.follow_ups = 0

    def warmup_bars(self) -> int:
        return 0

    def on_bar_close(self, t: int) -> BarDecision:
        intents = []
        if t == 2:
            intents = [OrderIntent(kind=IntentKind.ENTER_LONG, decision_index=t,
                                   earliest_phase=ExecutionPhase.NEXT_OPEN, reason="stub_entry")]
        return BarDecision(index=t, position_entering_bar=0.0, target_after_close=0.0,
                           intents=intents)

    def on_fill(self, fill):
        if fill.intent_kind is IntentKind.ENTER_LONG:
            self.follow_ups += 1
            return [OrderIntent(kind=IntentKind.EXIT_ALL, decision_index=fill.index,
                                earliest_phase=ExecutionPhase.NEXT_OPEN,
                                reason="bracket_invalid_after_gap")]
        return []


def test_a04_a_corrective_followup_exit_reaches_the_position():
    stub = _StubAdapter()
    with patch.object(EA, "build_adapter", return_value=stub):
        run = EA.run_event_account("A-SC", _frame(12),
                                   initial=VersionWindow("V1", dict(SEED_POINTS["A-SC"]), 0, "v1"),
                                   schedule=[])
    assert stub.follow_ups == 1, "the stub never emitted its corrective exit"
    assert run.engine_fill_count == len(run.fills)
    assert abs(float(run.positions[-1])) < 1e-9, (
        "the corrective follow-up exit was generated but the position stayed open")


def test_a02_a_future_requested_initial_is_flat_until_its_bar():
    future = VersionWindow("FUTURE", dict(SEED_POINTS["A-SC"]), 5, "future")
    run = EA.run_event_account("A-SC", _frame(80), initial=future, schedule=[])
    assert run.version_by_bar[0] == "FLAT_UNTIL_READY"
    assert all(version != "FUTURE" for version in run.version_by_bar[:5]), run.version_by_bar[:5]
    assert "FUTURE" in run.version_by_bar, "the version never activated"
    first = run.version_by_bar.index("FUTURE")
    assert first >= 5, "the version activated before it was requested"


def test_engine_fills_are_the_only_fills_the_adapter_saw():
    run = EA.run_event_account("A-SC", _frame(240),
                               initial=VersionWindow("V1", dict(SEED_POINTS["A-SC"]), 0, "v1"),
                               schedule=[])
    assert run.status == "EVALUATED", run.unmapped_intents
    assert run.engine_fill_count > 0, "the fixture must actually trade or it proves nothing"
    assert run.engine_fill_count == len(run.fills), (
        "a fill reached the adapter that QuantBT did not produce")
    assert np.isfinite(run.equity).all()
    assert run.diagnostics["fee_binding"] == {"fee": 0.0008, "fee_rate": 0.0004}
