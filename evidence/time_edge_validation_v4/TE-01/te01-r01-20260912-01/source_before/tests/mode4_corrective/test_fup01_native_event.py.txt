"""FUP-01 native-event command projection acceptance.

Stub-based contract tests for the FUP-01 projection (RF02.1/RF02.2):

* T17 — A-VWAP dynamic protection amendment: the projected ``AMEND`` reaches the
  engine on the tracked protection id at the next-bar effective phase, and the
  ``CANCEL`` projection reaches the engine on the tracked id;
* T19 — A-HASH ladder partial TP: one reduce-only LIMIT per rung, the position is
  not flattened until the final rung, partials reach the adapter as REDUCE and
  each partial pays the one-way fee;
* T20 — the route matrix does not silently promote or reroute a cell: all 20
  primary cells carry a status and a reason, and the A-SC long-flat cells keep
  their committed qualification;
* A03/G5 — an intent the route cannot project forces ``NOT_EVALUATED``.

The tests run the actual pinned engine through ``run_event_account`` with a
scripted adapter; only the decision source is a stub.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd

from crypto_regime_lab.alphas.a_hash import HashMomentumEventAdapterV1
from crypto_regime_lab.alphas.base import Fill, MarketSlice
from crypto_regime_lab.alphas.contracts import (
    BarDecision, ExecutionPhase, IntentKind, OrderIntent, QuantityBasis,
)
from crypto_regime_lab.integration import event_account as EA
from crypto_regime_lab.integration.continuous_account import VersionWindow
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS

ONE_WAY_FEE = 0.0004
FILL_KEYS = ("bar_index", "side", "qty", "price", "fee", "tag", "order_id",
             "intent_kind", "position_before", "position_after")


def _frame(*, ladder: bool, n: int = 30) -> pd.DataFrame:
    close = np.full(n, 100.0)
    if ladder:
        close[5] = 100.5
        close[7] = 101.4
        close[8] = 100.9
        close[10] = 102.4
        close[11] = 101.6
        close[13] = 103.4
        close[14:] = 103.6
    else:
        close[5:12] = 100.6
        close[12:16] = 100.2
        close[16:] = 100.4
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + 0.05,
                         "low": np.minimum(open_, close) - 0.05, "close": close,
                         "volume": np.full(n, 1000.0)},
                        index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"))


class _ScriptedAdapter:
    """A stub decision source: engine fills drive its protection follow-ups."""

    def __init__(self, script: dict[int, list[OrderIntent]], *, ladder: bool = False) -> None:
        self.script = script
        self.ladder = ladder
        self.position = 0.0
        self.received = []

    def warmup_bars(self) -> int:
        return 0

    def _protection(self, fill) -> OrderIntent:
        side = 1 if fill.quantity > 0 else -1
        stop = fill.price * (0.95 if side > 0 else 1.05)
        if self.ladder:
            rungs = ((fill.price * (1 + side * 0.01), 0.4),
                     (fill.price * (1 + side * 0.02), 0.5),
                     (fill.price * (1 + side * 0.03), 1.0))
            return OrderIntent(kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
                               earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                               reason="stub_ladder", stop_price=stop, ladder=rungs,
                               quantity_basis=QuantityBasis.FRACTION_OF_REMAINING)
        return OrderIntent(kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
                           earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                           reason="stub_protection", stop_price=stop,
                           take_profit_price=fill.price * (1 + side * 0.15))

    def on_bar_close(self, t: int) -> BarDecision:
        return BarDecision(index=t, position_entering_bar=self.position,
                           target_after_close=self.position,
                           intents=list(self.script.get(t, [])))

    def on_fill(self, fill) -> list[OrderIntent]:
        self.position += fill.quantity
        self.received.append(fill)
        if fill.intent_kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT):
            return [self._protection(fill)]
        return []


def _entry(index: int = 1) -> OrderIntent:
    return OrderIntent(kind=IntentKind.ENTER_LONG, decision_index=index,
                       earliest_phase=ExecutionPhase.NEXT_OPEN, reason="stub_entry")


def _run(adapter: _ScriptedAdapter, frame: pd.DataFrame) -> EA.EventAccountRun:
    with patch.object(EA, "build_adapter", return_value=adapter):
        return EA.run_event_account("A-VWAP", frame,
                                    initial=VersionWindow("V1", {}, 0, "v1"), schedule=[])


def _stop_order_id(run: EA.EventAccountRun) -> str:
    return next(command["order_id"] for command in run.commands if command["tag"] == "stop")


# --- T17: A-VWAP amend / cancel projection ---------------------------------

def test_t17_amend_protection_targets_the_tracked_order_and_reaches_the_engine():
    """T17: the projected AMEND hits the tracked stop at the next-bar phase."""
    adapter = _ScriptedAdapter({
        1: [_entry()],
        3: [OrderIntent(kind=IntentKind.AMEND_PROTECTION, decision_index=3,
                        earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                        reason="stub_amend", stop_price=96.0)],
    })
    run = _run(adapter, _frame(ladder=False))
    assert run.status == "EVALUATED", run.unmapped_intents
    stop_id = _stop_order_id(run)
    amends = [command for command in run.commands if command["engine_action"] == "amend"]
    assert amends and amends[0]["target_order_id"] == stop_id
    assert amends[0]["effective_phase"] == "next_bar"
    assert amends[0]["declared_phase"] == "resting_intrabar"
    events = [event for event in run.order_events if event["event_name"] == "amend"]
    assert events and events[0]["target_order_id"] == stop_id
    assert events[0]["bar"] > amends[0]["bar"], "the amend was effective on its own bar"
    assert not any(fill["tag"] == "stop" for fill in run.fills), "the stop must stay resting"


def test_t17_cancel_protection_targets_the_tracked_order_and_reaches_the_engine():
    """T17: the projected CANCEL hits the tracked stop and no unknown-order reject."""
    adapter = _ScriptedAdapter({
        1: [_entry()],
        5: [OrderIntent(kind=IntentKind.CANCEL_PROTECTION, decision_index=5,
                        earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                        reason="stub_cancel", metadata={"protection_target": "stop"})],
    })
    run = _run(adapter, _frame(ladder=False))
    assert run.status == "EVALUATED", (run.unmapped_intents, run.rejections)
    stop_id = _stop_order_id(run)
    cancels = [command for command in run.commands if command["engine_action"] == "cancel"]
    assert cancels and cancels[0]["target_order_id"] == stop_id
    events = [event for event in run.order_events if event["event_name"] == "cancel"]
    assert events and events[0]["target_order_id"] == stop_id
    assert not run.rejections, run.rejections


def test_t17_reduce_projection_is_capped_at_the_open_position():
    """T17: a 200%-of-remaining REDUCE never closes more than the position."""
    adapter = _ScriptedAdapter({
        1: [_entry()],
        5: [OrderIntent(kind=IntentKind.REDUCE, decision_index=5,
                        earliest_phase=ExecutionPhase.NEXT_OPEN, reason="stub_reduce",
                        quantity_basis=QuantityBasis.FRACTION_OF_REMAINING,
                        quantity_value=2.0)],
    })
    run = _run(adapter, _frame(ladder=False))
    assert run.status == "EVALUATED", run.unmapped_intents
    reduces = [command for command in run.commands if command["kind"] == "reduce"]
    assert reduces and reduces[0]["reduce_only"] is True
    entry_qty = next(fill["qty"] for fill in run.fills if fill["tag"] == "entry")
    assert reduces[0]["qty"] == entry_qty, "the reduce was not capped at the position"
    assert abs(float(run.positions[-1])) < 1e-9
    assert all(fill["position_after"] >= -1e-9 for fill in run.fills)


# --- T19: A-HASH ladder -----------------------------------------------------

def test_t19_ladder_partial_fills_do_not_flatten_until_the_last_rung():
    """T19: rungs fill in order; the position stays open until the final rung."""
    adapter = _ScriptedAdapter({1: [_entry()]}, ladder=True)
    run = _run(adapter, _frame(ladder=True))
    assert run.status == "EVALUATED", run.unmapped_intents
    ladder = [fill for fill in run.fills if fill["tag"] == "ladder"]
    assert len(ladder) >= 3, f"expected three rung fills, saw {len(ladder)}"
    entry_qty = next(fill["qty"] for fill in run.fills if fill["tag"] == "entry")
    assert ladder[0]["position_after"] > 0.0, "the first rung wrongly flattened the position"
    assert ladder[1]["position_after"] > 0.0, "the second rung wrongly flattened the position"
    assert abs(ladder[-1]["position_after"]) < 1e-9, "the final rung did not flatten"
    assert abs(sum(fill["qty"] for fill in ladder) - entry_qty) < 1e-9 * entry_qty
    assert all(fill["intent_kind"] == "reduce" for fill in ladder), (
        "a ladder partial must reach the adapter as REDUCE, never EXIT_ALL")
    assert all(received.intent_kind is IntentKind.REDUCE for received in adapter.received[1:])


def test_t19_each_partial_fill_pays_the_one_way_fee():
    """T19: fees are charged per partial fill at the bound one-way rate."""
    adapter = _ScriptedAdapter({1: [_entry()]}, ladder=True)
    run = _run(adapter, _frame(ladder=True))
    ladder = [fill for fill in run.fills if fill["tag"] == "ladder"]
    assert ladder, "the fixture must fill at least one rung"
    for fill in ladder:
        expected = fill["qty"] * fill["price"] * ONE_WAY_FEE
        assert fill["fee"] == expected or abs(fill["fee"] - expected) / expected < 1e-9
    assert all(all(fill[key] is not None for key in FILL_KEYS) for fill in run.fills)


def test_t19_hash_cooldown_restarts_only_on_full_flatten():
    """T19: the real A-HASH adapter never starts its cooldown on a partial rung."""
    market = MarketSlice(open=np.full(20, 100.0), high=np.full(20, 101.0),
                         low=np.full(20, 99.0), close=np.full(20, 100.0),
                         volume=np.full(20, 1000.0),
                         index=pd.date_range("2024-01-01", periods=20, freq="1h", tz="UTC"))
    adapter = HashMomentumEventAdapterV1(dict(SEED_POINTS["A-HASH"]), market)
    adapter.on_fill(Fill(index=1, side=1, quantity=10.0, price=100.0,
                         intent_kind=IntentKind.ENTER_LONG))
    adapter.on_fill(Fill(index=5, side=-1, quantity=-4.0, price=101.0,
                         intent_kind=IntentKind.REDUCE))
    assert adapter.state.position == 6.0
    assert adapter.last_exit_index is None, "a partial rung started the cooldown"
    adapter.on_fill(Fill(index=9, side=-1, quantity=-6.0, price=102.0,
                         intent_kind=IntentKind.REDUCE))
    assert adapter.state.position == 0.0
    assert adapter.last_exit_index == 9, "the flattening rung must start the cooldown"


# --- A03/G5: unprojectable intent ------------------------------------------

def test_a03_an_unprojectable_intent_forces_not_evaluated():
    """A03/G5: an AMEND with no tracked protection is unsupported, not dropped."""
    adapter = _ScriptedAdapter({
        1: [OrderIntent(kind=IntentKind.AMEND_PROTECTION, decision_index=1,
                        earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                        reason="stub_orphan_amend", stop_price=96.0)],
    })
    run = _run(adapter, _frame(ladder=False))
    assert run.status == "NOT_EVALUATED"
    assert run.scored is False
    assert any(entry["reason"] == "amend_protection_without_a_tracked_order"
               for entry in run.unmapped_intents), run.unmapped_intents


# --- T20: route matrix guard -------------------------------------------------

def test_t20_route_matrix_covers_all_20_cells_and_never_zero_fills_metrics(lab_root):
    """T20: 20 unique cells, every status has a reason, no metric is fabricated."""
    matrix = json.loads((lab_root / "evidence" / "corrective_mode4_v3" / "FUP-01"
                         / "route_matrix.json").read_text(encoding="utf-8"))
    cells = matrix["cells"]
    assert len(cells) == 20
    assert len({cell["cell"] for cell in cells}) == 20
    expected = {f"{alpha}/{symbol}" for alpha in ("A-SC", "A-HMA", "A-VWAP", "A-HASH")
                for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")}
    assert {cell["cell"] for cell in cells} == expected
    vocabulary = set(matrix["status_vocabulary"])
    for cell in cells:
        assert cell["route_status"] in vocabulary, cell
        assert cell["reason"], f"{cell['cell']} has no reason"
        assert cell["metrics"] is None, (
            f"{cell['cell']} carries metrics in a route-only artifact")
        assert cell["metrics_reason"], f"{cell['cell']} has no metrics reason"


def test_t20_long_flat_cells_are_not_silently_promoted_or_rerouted(lab_root):
    """T20: A-SC keeps its committed long-flat qualification; nothing is invented."""
    matrix = json.loads((lab_root / "evidence" / "corrective_mode4_v3" / "FUP-01"
                         / "route_matrix.json").read_text(encoding="utf-8"))
    sc_cells = [cell for cell in matrix["cells"] if cell["alpha_id"] == "A-SC"]
    assert len(sc_cells) == 5
    assert all(cell["route_status"] == "QUALIFIED_FAST" for cell in sc_cells)
    assert all(cell["source"]["kind"] == "committed_rf04_cell" for cell in sc_cells)
    new = {cell["alpha_id"]: cell["route_status"] for cell in matrix["cells"]
           if cell["alpha_id"] in ("A-VWAP", "A-HASH")}
    assert set(new) == {"A-VWAP", "A-HASH"}
    assert all(status == "QUALIFIED_EVENT" for status in new.values()), new


def test_fup01_capability_artifact_records_the_engine_events(lab_root):
    """T17/T19 evidence: both alphas qualified on observed engine events."""
    capability = json.loads((lab_root / "evidence" / "corrective_mode4_v3" / "FUP-01"
                             / "native_event_capability.json").read_text(encoding="utf-8"))
    assert capability["blocked_capabilities"] == []
    vwap = capability["alphas"]["A-VWAP"]
    assert vwap["status"] == "QUALIFIED_EVENT"
    assert vwap["real_btcusdt_window"]["engine_events_observed"].get("amend", 0) >= 1
    assert vwap["real_btcusdt_window"]["per_fill_ledger_non_null"] is True
    hash_alpha = capability["alphas"]["A-HASH"]
    assert hash_alpha["status"] == "QUALIFIED_EVENT"
    ladder_fills = [fill for fill in hash_alpha["real_btcusdt_window"]["per_fill_ledger"]
                    if fill["tag"] == "ladder"]
    assert len(ladder_fills) >= 2
    assert hash_alpha["real_btcusdt_window"]["fee_accounting"]["pass"] is True
    assert hash_alpha["real_btcusdt_window"]["ladder_summary"][
        "ladder_episodes_with_two_or_more_rungs"] >= 1
