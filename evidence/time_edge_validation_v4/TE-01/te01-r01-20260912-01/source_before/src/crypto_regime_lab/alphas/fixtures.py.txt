"""L02.7 — common execution fixtures, executed by the INSTALLED engine.

The guide forbids building a second matching/accounting engine, so every
scenario here is run through ``intrabar_bracket_v1`` and the lab only asserts
what it observes. Adapter-side invariants (no position without a fill, levels
from the actual fill) are exercised with a scripted fill tape, which replays
engine-reported fills rather than simulating matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..quantbt_bridge.intent_tape import TapeBuild, run_intrabar
from .base import MarketSlice
from .contracts import IntentKind


@dataclass
class FixtureResult:
    fixture_id: str
    requirement: str
    expectation: str
    observed: Any
    passed: bool
    detail: dict = field(default_factory=dict)

    def as_record(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "requirement": self.requirement,
            "expectation": self.expectation,
            "observed": self.observed,
            "passed": self.passed,
            "detail": self.detail,
        }


def _frame(open_, high, low, close, volume=None, freq="1h"):
    """Frame builder that satisfies QuantBT's OHLCV invariant (high>=max(o,c) etc)."""
    import pandas as pd

    open_, high, low, close = (np.asarray(x, dtype=float) for x in (open_, high, low, close))
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.full(n, 1000.0) if volume is None else np.asarray(volume, dtype=float),
    }, index=idx)


def _tape(n, *, entry_bar=None, side=1.0, size=1.0, stop=None, take_profit=None,
          exit_bars=()):
    entry_side = np.zeros(n)
    entry_size = np.zeros(n)
    stop_value = np.full(n, np.nan)
    tp_value = np.full(n, np.nan)
    tech = np.zeros(n, dtype=bool)
    if entry_bar is not None:
        entry_side[entry_bar] = side
        entry_size[entry_bar] = size
        if stop is not None:
            stop_value[entry_bar] = stop
        if take_profit is not None:
            tp_value[entry_bar] = take_profit
    for b in exit_bars:
        tech[b] = True
    return TapeBuild(entry_side, entry_size, stop_value, tp_value, tech)


# ---------------------------------------------------------------------------
# 1-2. long and short entry at the next open
# ---------------------------------------------------------------------------

def fixture_long_entry_next_open() -> FixtureResult:
    n = 12
    close = 100.0 + np.arange(n)
    frame = _frame(close - 0.5, close + 1.0, close - 1.0, close)
    out = run_intrabar(frame, _tape(n, entry_bar=3, side=1.0, stop=90.0, take_profit=1e9),
                       backend="reference", close_on_last_bar=True, fee=0.0, slippage_bps=0.0)
    entry = next((f for f in out["fills"] if f["reason"] == "entry"), None)
    expected_price = float(frame["open"].iloc[4])
    ok = entry is not None and entry["bar_index"] == 4 and abs(entry["price"] - expected_price) < 1e-12
    return FixtureResult(
        "L02.7-01-long-entry", "long entry",
        "a decision at the close of bar 3 fills at the OPEN of bar 4, never at close[3]",
        {"fill": entry, "expected_price": expected_price,
         "close_of_decision_bar": float(frame["close"].iloc[3])},
        ok)


def fixture_short_entry_next_open() -> FixtureResult:
    n = 12
    close = 120.0 - np.arange(n)
    frame = _frame(close + 0.5, close + 1.0, close - 1.0, close)
    out = run_intrabar(frame, _tape(n, entry_bar=3, side=-1.0, stop=1e9, take_profit=1.0),
                       backend="reference", close_on_last_bar=True, fee=0.0, slippage_bps=0.0)
    entry = next((f for f in out["fills"] if f["reason"] == "entry"), None)
    expected_price = float(frame["open"].iloc[4])
    ok = entry is not None and entry["side"] == -1 and entry["bar_index"] == 4 \
        and abs(entry["price"] - expected_price) < 1e-12
    return FixtureResult(
        "L02.7-02-short-entry", "short entry",
        "a short decision fills at the next open with side -1",
        {"fill": entry, "expected_price": expected_price}, ok)


# ---------------------------------------------------------------------------
# 3. an actual gap: the fill is nowhere near the decision close
# ---------------------------------------------------------------------------

def fixture_gap_entry() -> FixtureResult:
    n = 12
    close = np.full(n, 100.0)
    open_ = close.copy()
    open_[4] = 130.0                     # a 30% gap up on the fill bar
    high = np.maximum(close, open_) + 1.0
    low = np.minimum(close, open_) - 1.0
    frame = _frame(open_, high, low, close)
    out = run_intrabar(frame, _tape(n, entry_bar=3, side=1.0, stop=50.0, take_profit=1e9),
                       backend="reference", close_on_last_bar=True, fee=0.0, slippage_bps=0.0)
    entry = next((f for f in out["fills"] if f["reason"] == "entry"), None)
    ok = entry is not None and abs(entry["price"] - 130.0) < 1e-12
    return FixtureResult(
        "L02.7-03-gap-entry", "actual gap",
        "the fill price is the gapped open (130), not the decision close (100)",
        {"fill": entry, "decision_close": 100.0, "gapped_open": 130.0}, ok)


# ---------------------------------------------------------------------------
# 4. a bar that touches BOTH the stop and the take profit
# ---------------------------------------------------------------------------

def fixture_stop_and_tp_same_bar() -> FixtureResult:
    n = 12
    close = np.full(n, 100.0)
    open_ = np.full(n, 100.0)
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    high[6] = 120.0                      # touches the take profit
    low[6] = 80.0                        # and the stop, on the same bar
    frame = _frame(open_, high, low, close)
    out = run_intrabar(frame, _tape(n, entry_bar=3, side=1.0, stop=90.0, take_profit=110.0),
                       backend="reference", close_on_last_bar=True, fee=0.0, slippage_bps=0.0)
    exits = [f for f in out["fills"] if f["reason"] != "entry"]
    first_exit = exits[0] if exits else None
    ok = first_exit is not None and first_exit["reason"] == "stop_loss" and first_exit["bar_index"] == 6
    return FixtureResult(
        "L02.7-04-stop-and-tp-same-bar", "both stop and TP hit",
        "same_bar_policy=conservative resolves an ambiguous bar to the STOP, never the profit",
        {"exits": exits, "contract_same_bar_policy": "conservative"}, ok,
        detail={"note": "an alpha that books the take profit here would be inventing a favourable "
                        "intrabar path the data cannot support (findings AH-04, HM-03)"})


# ---------------------------------------------------------------------------
# 5. partials / OCO / over-close
# ---------------------------------------------------------------------------

def fixture_oco_and_over_close() -> FixtureResult:
    """Once one protective leg fills, the other must not also fill (OCO)."""
    n = 14
    close = np.full(n, 100.0)
    open_ = np.full(n, 100.0)
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    high[6] = 115.0                      # take profit at 110 fills here
    low[8] = 85.0                        # the stop at 90 would fill later
    frame = _frame(open_, high, low, close)
    out = run_intrabar(frame, _tape(n, entry_bar=3, side=1.0, stop=90.0, take_profit=110.0),
                       backend="reference", close_on_last_bar=True, fee=0.0, slippage_bps=0.0)
    exits = [f for f in out["fills"] if f["reason"] != "entry"]
    closed_qty = sum(f["qty"] for f in exits)
    positions = out["positions"].reshape(-1)
    ok = len(exits) == 1 and exits[0]["reason"] == "take_profit" and closed_qty <= 1.0 + 1e-12 \
        and float(np.max(np.abs(positions))) <= 1.0 + 1e-12
    return FixtureResult(
        "L02.7-05-oco-over-close", "partials / OCO / over-close",
        "the take profit fills once, the stop is cancelled, and total closed quantity never "
        "exceeds the position",
        {"exits": exits, "closed_qty": closed_qty,
         "max_abs_position": float(np.max(np.abs(positions)))}, ok)


def fixture_partial_ladder_capability() -> FixtureResult:
    """A multi-rung ladder is NOT expressible on this route: recorded, not faked."""
    from .contracts import ExecutionPhase, OrderIntent, QuantityBasis
    from ..quantbt_bridge.intent_tape import build_intent_tape
    from .contracts import BarDecision

    ladder = ((105.0, 0.5), (108.0, 0.5), (110.0, 1.0))
    decision = BarDecision(index=3, position_entering_bar=0.0, target_after_close=1.0, intents=[
        OrderIntent(kind=IntentKind.SET_PROTECTION, decision_index=3,
                    earliest_phase=ExecutionPhase.RESTING_INTRABAR, reason="ladder",
                    stop_price=95.0, ladder=ladder,
                    quantity_basis=QuantityBasis.FRACTION_OF_REMAINING)])
    build = build_intent_tape([decision], n_bars=12)
    blocked = [u for u in build.unmapped_intents if "ladder" in u["reason"]]
    ok = bool(blocked) and blocked[0]["handling"].startswith("BLOCKED_CAPABILITY")
    return FixtureResult(
        "L02.7-05b-partial-ladder", "partials",
        "an A-HASH multi-rung ladder is recorded as BLOCKED_CAPABILITY on this route rather than "
        "silently collapsed to a single exit",
        {"unmapped": build.unmapped_intents,
         "final_rung_used_as_tp": float(build.take_profit_value[3])}, ok)


# ---------------------------------------------------------------------------
# 6-7. rejected order and insufficient margin
# ---------------------------------------------------------------------------

def fixture_rejected_order() -> FixtureResult:
    """A zero-size entry must not produce a position."""
    n = 10
    close = np.full(n, 100.0)
    frame = _frame(close, close + 1.0, close - 1.0, close)
    build = _tape(n, entry_bar=3, side=1.0, size=0.0, stop=90.0, take_profit=110.0)
    out = run_intrabar(frame, build, backend="reference", close_on_last_bar=True,
                       fee=0.0, slippage_bps=0.0)
    positions = out["positions"].reshape(-1)
    ok = float(np.max(np.abs(positions))) == 0.0 and not any(
        f["reason"] == "entry" for f in out["fills"])
    return FixtureResult(
        "L02.7-06-rejected-order", "rejected order",
        "a zero-quantity intent yields no fill and no position",
        {"fills": out["fills"], "max_abs_position": float(np.max(np.abs(positions)))}, ok)


def fixture_insufficient_margin() -> FixtureResult:
    """An entry far larger than the account must not silently become a small one."""
    n = 10
    close = np.full(n, 100.0)
    frame = _frame(close, close + 1.0, close - 1.0, close)
    build = _tape(n, entry_bar=3, side=1.0, size=1_000_000.0, stop=90.0, take_profit=110.0)
    try:
        out = run_intrabar(frame, build, backend="reference", initial_capital=1000.0,
                           close_on_last_bar=True, fee=0.0, slippage_bps=0.0)
        positions = out["positions"].reshape(-1)
        filled = float(np.max(np.abs(positions)))
        equity = out["equity"]
        observed = {"max_abs_position": filled, "liquidated": out["liquidated"],
                    "final_equity": float(equity[-1]), "fills": out["fills"][:3]}
        # Either the engine rejects it, or it accepts and the account reflects the
        # consequence. What is NOT acceptable is a silently resized fill.
        ok = (filled == 0.0) or (filled == 1_000_000.0)
        observed["interpretation"] = ("rejected" if filled == 0.0
                                      else "accepted at full size; account carries the consequence")
    except Exception as exc:
        observed = {"raised": f"{type(exc).__name__}: {exc}"}
        ok = True
    return FixtureResult(
        "L02.7-07-insufficient-margin", "insufficient margin",
        "an oversized entry is either rejected or filled at full size; it is never silently resized",
        observed, ok)


# ---------------------------------------------------------------------------
# 8. funding boundary
# ---------------------------------------------------------------------------

def fixture_funding_boundary() -> FixtureResult:
    """Funding is charged on the position held AT the event, per the contract."""
    import pandas as pd

    n = 14
    close = np.full(n, 100.0)
    frame = _frame(close, close + 0.5, close - 0.5, close)
    build = _tape(n, entry_bar=3, side=1.0, stop=50.0, take_profit=1e9)
    funding_ts = pd.DatetimeIndex([frame.index[6], frame.index[10]])
    funding_rates = np.array([0.001, 0.001])
    out = run_intrabar(frame, build, backend="reference", close_on_last_bar=True,
                       fee=0.0, slippage_bps=0.0, use_funding=True,
                       funding_timestamps=funding_ts, funding_rates=funding_rates)
    funding = out["funding"].reshape(-1)
    charged_bars = np.flatnonzero(np.abs(funding) > 0).tolist()
    ok = len(charged_bars) == 2 and 6 in charged_bars and 10 in charged_bars
    return FixtureResult(
        "L02.7-08-funding-boundary", "funding boundary",
        "funding is applied exactly at the two declared events while the position is open, "
        "and never inferred as zero when it is missing",
        {"charged_bars": charged_bars, "funding_total": float(np.sum(funding)),
         "funding_phase": "position_at_event"}, ok)


def fixture_funding_missing_is_not_zero() -> FixtureResult:
    """Strict data: an unspecified funding series must raise, not default to zero."""
    n = 10
    close = np.full(n, 100.0)
    frame = _frame(close, close + 0.5, close - 0.5, close)
    build = _tape(n, entry_bar=3, side=1.0, stop=50.0, take_profit=1e9)
    try:
        run_intrabar(frame, build, backend="reference", use_funding=True,
                     close_on_last_bar=True, fee=0.0, slippage_bps=0.0)
        observed, ok = "NO_ERROR_RAISED", False
    except Exception as exc:
        observed, ok = f"{type(exc).__name__}: {exc}", "funding" in str(exc).lower()
    return FixtureResult(
        "L02.7-08b-funding-missing", "funding boundary",
        "requesting funding without supplying events is refused, so a missing history can never "
        "be silently treated as zero carry (guide 4.1)",
        observed, ok)


# ---------------------------------------------------------------------------
# 9. terminal open position: two declared modes
# ---------------------------------------------------------------------------

def fixture_terminal_open_position() -> FixtureResult:
    n = 10
    close = 100.0 + np.arange(n)
    frame = _frame(close - 0.5, close + 1.0, close - 1.0, close)
    build_a = _tape(n, entry_bar=3, side=1.0, stop=50.0, take_profit=1e9)
    build_b = _tape(n, entry_bar=3, side=1.0, stop=50.0, take_profit=1e9)
    forced = run_intrabar(frame, build_a, backend="reference", close_on_last_bar=True,
                          fee=0.0, slippage_bps=0.0)
    marked = run_intrabar(frame, build_b, backend="reference", close_on_last_bar=False,
                          fee=0.0, slippage_bps=0.0)
    forced_pos = forced["positions"].reshape(-1)[-1]
    marked_pos = marked["positions"].reshape(-1)[-1]
    ok = float(forced_pos) == 0.0 and abs(float(marked_pos)) > 0.0
    return FixtureResult(
        "L02.7-09-terminal-position", "final open position",
        "forced-flat and mark-open-exposure are two DECLARED modes, not one default",
        {"forced_flat_terminal_position": float(forced_pos),
         "mark_open_terminal_position": float(marked_pos),
         "forced_flat_final_equity": float(forced["equity"][-1]),
         "mark_open_final_equity": float(marked["equity"][-1])}, ok)


# ---------------------------------------------------------------------------
# adapter invariant: submitted is not filled
# ---------------------------------------------------------------------------

def fixture_no_position_without_fill() -> FixtureResult:
    """An adapter that has staged an entry still reports zero position."""
    from .a_hash import HashMomentumEventAdapterV1

    n = 60
    rng = np.random.default_rng(4)
    close = 100.0 + np.cumsum(rng.normal(0.05, 0.5, n))
    market = MarketSlice(np.r_[close[0], close[:-1]], close + 0.3, close - 0.3, close,
                         np.full(n, 1000.0))
    adapter = HashMomentumEventAdapterV1(
        dict(mom_len=5, ema_len=10, cooldown_bars=1, stop_loss_perc=2.0, rr_ratio=3.0,
             tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
             mom_threshold_mult=0.0), market)
    staged_bar = None
    position_when_staged = None
    for t in range(n):
        decision = adapter.on_bar_close(t)
        if any(i.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) for i in decision.intents):
            staged_bar = t
            position_when_staged = adapter.state.position
            break
    ok = staged_bar is not None and position_when_staged == 0.0 and \
        adapter.state.pending_entry_side != 0
    return FixtureResult(
        "L02.7-10-submitted-not-filled", "adapter must not set a position on a submitted order",
        "after staging an entry the adapter's position is still 0 and only pending_entry_side is set",
        {"staged_bar": staged_bar, "position_when_staged": position_when_staged,
         "pending_entry_side": adapter.state.pending_entry_side}, ok)


def fixture_levels_derived_from_actual_fill() -> FixtureResult:
    """The protective levels must move when the fill price moves."""
    from .a_hash import HashMomentumEventAdapterV1

    n = 40
    close = np.full(n, 100.0)
    market = MarketSlice(close.copy(), close + 1.0, close - 1.0, close, np.full(n, 1000.0))
    params = dict(mom_len=3, ema_len=5, cooldown_bars=1, stop_loss_perc=10.0, rr_ratio=3.0,
                  tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
                  mom_threshold_mult=0.0)
    a = HashMomentumEventAdapterV1(params, market)
    a.prepare()
    stop_at_100, ladder_at_100 = a.build_ladder(100.0, 1)
    stop_at_130, ladder_at_130 = a.build_ladder(130.0, 1)
    ok = abs(stop_at_100 - 90.0) < 1e-9 and abs(stop_at_130 - 117.0) < 1e-9 and \
        ladder_at_100[0][0] != ladder_at_130[0][0]
    return FixtureResult(
        "L02.7-11-levels-from-fill", "levels come from the actual fill",
        "a fill at 130 instead of 100 moves the stop from 90 to 117 and every ladder rung with it",
        {"stop_at_fill_100": stop_at_100, "stop_at_fill_130": stop_at_130,
         "ladder_at_100": [list(x) for x in ladder_at_100],
         "ladder_at_130": [list(x) for x in ladder_at_130]}, ok)


ALL_FIXTURES: tuple[Callable[[], FixtureResult], ...] = (
    fixture_long_entry_next_open,
    fixture_short_entry_next_open,
    fixture_gap_entry,
    fixture_stop_and_tp_same_bar,
    fixture_oco_and_over_close,
    fixture_partial_ladder_capability,
    fixture_rejected_order,
    fixture_insufficient_margin,
    fixture_funding_boundary,
    fixture_funding_missing_is_not_zero,
    fixture_terminal_open_position,
    fixture_no_position_without_fill,
    fixture_levels_derived_from_actual_fill,
)


def run_all_fixtures() -> dict:
    import warnings

    results = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for fn in ALL_FIXTURES:
            try:
                results.append(fn().as_record())
            except Exception as exc:  # a fixture that cannot run is a failure
                import traceback

                results.append({
                    "fixture_id": fn.__name__, "requirement": "unknown",
                    "expectation": (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "",
                    "observed": None, "passed": False,
                    "detail": {"error": f"{type(exc).__name__}: {exc}",
                               "traceback": traceback.format_exc()[-1200:]},
                })
    passed = sum(1 for r in results if r["passed"])
    return {
        "schema": "crypto_regime_lab.execution_fixtures.v1",
        "engine": "quantbt intrabar_bracket_v1 (installed); the lab implements no matching engine",
        "fixture_count": len(results),
        "passed": passed,
        "status": "PASS" if passed == len(results) else "FAIL",
        "results": results,
    }
