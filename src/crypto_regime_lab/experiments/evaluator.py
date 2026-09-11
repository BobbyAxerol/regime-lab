"""One candidate evaluation: adapter -> intent tape -> installed engine -> utility.

Two things here are easy to get wrong and both are load-bearing.

**Fill feedback.** The adapters change position only through ``on_fill``, and a
protective exit is a resting order the ENGINE fills. A single forward pass would
therefore leave an adapter believing it is still in a trade the engine already
closed, and it would never trade again. So the pass is repeated until the set of
protective exits the engine reports equals the set the adapter was driven with.
Non-convergence is reported, never quietly accepted.

**Sizing.** The frozen account contract is an entry notional of 2000 USDT on
20000 of capital. Sizing in raw units instead would ask for one whole coin per
entry -- around 35000 USDT of BTC -- and the engine rejects every such entry for
margin. That is exactly what made the LAB-03 qualification smoke report zero
engine fills.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..alphas.base import Fill, IntentKind, MarketSlice
from ..quantbt_bridge.intent_tape import TapeBuild, build_intent_tape, run_intrabar

#: Frozen in LAB-01 for every arm; never tuned, never chosen for prettier returns.
ACCOUNT = {
    "initial_capital_usdt": 20000.0,
    "entry_notional_usdt": 2000.0,
    "taker_fee_rate": 0.0004,
    "slippage_bps": 1.0,
    "use_funding": False,
    "funding_note": "MISSING_NOT_ZERO; this is a labelled no-funding cohort",
}

#: Selection hyperparameters (guide 7.3). Chosen on the development role, registered
#: before any arm comparison, identical for arm A and arm B.
UTILITY = {
    "risk_unit_fraction": 0.01,      # net return is expressed per 1% of capital
    "drawdown_penalty": 0.5,         # the "defined drawdown penalty" of 7.3
    "gate_max_drawdown": 0.10,       # risk gate on an episode
    "gate_min_return": 0.0,          # quality gate on an episode
    "turnover_penalty": 0.0,         # costs are already inside net return; not double charged
}

MAX_SWEEPS = 4
#: How far ahead the exit oracle looks for a resting stop or take profit to fire.
ORACLE_HORIZON = 4000


class EvaluationError(RuntimeError):
    """A candidate could not be evaluated. This is NOT a financial loss."""


@dataclass
class CandidateRun:
    """The account trace of one candidate over one contiguous window."""

    equity: np.ndarray
    positions: np.ndarray
    fills: list[dict]
    index: pd.DatetimeIndex
    converged: bool
    passes: int
    entries: int
    unmapped_intents: int = 0
    diagnostics: dict = field(default_factory=dict)


def build_adapter(alpha_id: str, params: dict, market: MarketSlice):
    from ..alphas.a_hash import HashMomentumEventAdapterV1
    from ..alphas.a_hma import AdaptiveHmaEventAdapterV1
    from ..alphas.a_sc import SignalCombineAdapterV1
    from ..alphas.a_vwap import VwapMeanReversionEventAdapterV1

    cls = {"A-SC": SignalCombineAdapterV1, "A-HMA": AdaptiveHmaEventAdapterV1,
           "A-VWAP": VwapMeanReversionEventAdapterV1,
           "A-HASH": HashMomentumEventAdapterV1}[alpha_id]
    return cls(dict(params), market)


def _engine(frame: pd.DataFrame, tape, backend: str) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_intrabar(frame, tape, backend=backend,
                            initial_capital=ACCOUNT["initial_capital_usdt"],
                            fee=ACCOUNT["taker_fee_rate"],
                            slippage_bps=ACCOUNT["slippage_bps"],
                            use_funding=ACCOUNT["use_funding"], close_on_last_bar=True,
                            sizing_mode="fixed_notional",
                            unit_notional=ACCOUNT["entry_notional_usdt"])


PROTECTIVE = ("stop_loss", "take_profit", "liquidation")


def _exit_oracle(engine_frame: pd.DataFrame, decision_bar: int, side: int,
                 stop: float, take_profit: float, *, backend: str,
                 horizon: int = ORACLE_HORIZON) -> tuple[int | None, float | None, str | None]:
    """Ask the ENGINE when this one position's resting protection fires.

    A single forward pass cannot know this, and iterating the whole window to a
    fixed point converges only about one trade per pass -- measured at roughly
    17 s per pass for A-HMA, which is hopeless at a 96-candidate budget. Asking
    the engine about one trade at a time costs about 10 ms and is exact for the
    quantity that matters: absolute price levels against that bar's own OHLC.
    The whole-window run afterwards re-derives these exits and any disagreement
    is reported rather than absorbed.
    """
    n = len(engine_frame)
    hi = min(n, decision_bar + 1 + horizon)
    segment = engine_frame.iloc[decision_bar:hi]
    m = len(segment)
    if m < 2:
        return None, None, None
    tape = TapeBuild(entry_side=np.zeros(m), entry_size=np.zeros(m),
                     stop_value=np.full(m, np.nan), take_profit_value=np.full(m, np.nan),
                     technical_exit=np.zeros(m, dtype=bool))
    tape.entry_side[0] = float(side)
    tape.entry_size[0] = 1.0
    tape.stop_value[0] = stop
    tape.take_profit_value[0] = take_profit
    out = _engine(segment, tape, backend)
    for fill in out["fills"]:
        if fill["reason"] in PROTECTIVE:
            return decision_bar + int(fill["bar_index"]), float(fill["price"]), fill["reason"]
    return None, None, None


def _sweep(alpha_id: str, params: dict, frame: pd.DataFrame, arrays: list[np.ndarray],
           engine_frame: pd.DataFrame, *, backend: str,
           forced_exits: dict[int, float] | None = None):
    """One chronological pass. Protective exits come from the oracle, or from a
    previously observed whole-window run when ``forced_exits`` is supplied."""
    n = len(frame)
    open_ = arrays[0]
    market = MarketSlice(*arrays, index=frame.index)
    adapter = build_adapter(alpha_id, params, market)
    pending_levels: dict[int, tuple[float, float]] = {}
    applied_exits: dict[int, float] = {}
    next_exit_bar: int | None = None
    next_exit_price: float | None = None

    for t in range(n):
        if forced_exits is not None and t in forced_exits and adapter.state.position != 0.0:
            adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
                                 quantity=-adapter.state.position,
                                 price=float(forced_exits[t]), intent_kind=IntentKind.EXIT_ALL))
            applied_exits[t] = float(forced_exits[t])
        elif next_exit_bar == t and adapter.state.position != 0.0:
            adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
                                 quantity=-adapter.state.position,
                                 price=float(next_exit_price), intent_kind=IntentKind.EXIT_ALL))
            applied_exits[t] = float(next_exit_price)
            next_exit_bar, next_exit_price = None, None

        decision = adapter.on_bar_close(t)
        for intent in decision.intents:
            if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and t + 1 < n:
                side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
                qty = ACCOUNT["entry_notional_usdt"] / max(float(open_[t + 1]), 1e-12)
                follow_ups = adapter.on_fill(Fill(index=t + 1, side=side,
                                                  quantity=float(side) * qty,
                                                  price=float(open_[t + 1]),
                                                  intent_kind=intent.kind))
                stop = take_profit = float("nan")
                for follow in follow_ups:
                    if follow.stop_price is not None:
                        stop = float(follow.stop_price)
                        tp = follow.take_profit_price
                        if tp is None and follow.ladder:
                            tp = follow.ladder[-1][0]
                        take_profit = float(tp) if tp is not None else float("nan")
                if np.isfinite(stop) or np.isfinite(take_profit):
                    pending_levels[t] = (stop, take_profit)
                    if forced_exits is None:
                        bar, price, _ = _exit_oracle(engine_frame, t, side, stop, take_profit,
                                                     backend=backend)
                        next_exit_bar, next_exit_price = bar, price
            elif intent.kind is IntentKind.EXIT_ALL and adapter.state.position != 0.0 \
                    and t + 1 < n:
                adapter.on_fill(Fill(index=t + 1,
                                     side=-int(np.sign(adapter.state.position)),
                                     quantity=-adapter.state.position,
                                     price=float(open_[t + 1]),
                                     intent_kind=IntentKind.EXIT_ALL))
                next_exit_bar, next_exit_price = None, None
    return adapter, pending_levels, applied_exits


def run_candidate(alpha_id: str, params: dict, frame: pd.DataFrame, *,
                  backend: str = "reference", max_sweeps: int = MAX_SWEEPS) -> CandidateRun:
    """Evaluate one parameter point over one contiguous window.

    Sweep chronologically with an exit oracle, run the resulting tape over the
    whole window, and require the whole-window protective exits to agree with the
    exits the adapter was actually driven with. Disagreement triggers a bounded
    repair and, if it persists, ``converged=False`` on the record.
    """
    n = len(frame)
    if n < 10:
        raise EvaluationError(f"window of {n} bars is too short to evaluate")
    arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
    engine_frame = frame[["open", "high", "low", "close", "volume"]]

    forced: dict[int, float] | None = None
    out = build = None
    applied: dict[int, float] = {}
    sweeps = 0
    for attempt in range(max_sweeps):
        sweeps = attempt + 1
        adapter, pending, applied = _sweep(alpha_id, params, frame, arrays, engine_frame,
                                           backend=backend, forced_exits=forced)
        build = build_intent_tape(adapter.decisions, n, unit_size=1.0, pending_levels=pending)
        out = _engine(engine_frame, build, backend)
        observed = {int(f["bar_index"]): float(f["price"]) for f in out["fills"]
                    if f["reason"] in PROTECTIVE}
        if set(observed) == set(applied):
            return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
                                np.asarray(out["positions"], float).reshape(-1),
                                out["fills"], frame.index, True, sweeps,
                                int(np.count_nonzero(build.entry_side)),
                                len(build.unmapped_intents),
                                {"protective_exits": len(observed)})
        forced = observed

    return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
                        np.asarray(out["positions"], float).reshape(-1),
                        out["fills"], frame.index, False, sweeps,
                        int(np.count_nonzero(build.entry_side)),
                        len(build.unmapped_intents),
                        {"unconverged_exit_symmetric_difference":
                             len(set(applied).symmetric_difference(
                                 {int(f["bar_index"]) for f in out["fills"]
                                  if f["reason"] in PROTECTIVE}))})


# ---------------------------------------------------------------------------
# utility
# ---------------------------------------------------------------------------

def episode_bounds(index: pd.DatetimeIndex, episodes: int) -> list[tuple[str, int, int]]:
    """Contiguous inner episodes of EQUAL bar length (guide 7.3).

    Equal length is the point: the score may not mix long and short blocks, so a
    remainder is dropped from the front rather than making one block longer.
    """
    n = len(index)
    if episodes <= 0 or n < episodes * 2:
        raise EvaluationError(f"window of {n} bars cannot carry {episodes} inner episodes")
    size = n // episodes
    start0 = n - size * episodes
    return [(f"e{i}", start0 + i * size, start0 + (i + 1) * size) for i in range(episodes)]


def _drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, (peak - equity) / peak, 0.0)
    return float(np.max(dd)) if dd.size else 0.0


def episode_metrics(run: CandidateRun, bounds: list[tuple[str, int, int]]) -> dict:
    """Utility and gate outcome per inner episode.

    A07: money PnL over the half-open block ``[lo, hi)`` is
    ``E_{hi-1} - E_{lo-1}``, with the first block measuring from the initial
    account before the first observation. The old formula measured from
    ``E[lo]``, so the move across a block boundary was dropped and the block
    money deltas did not telescope to the whole-account delta.
    """
    capital = ACCOUNT["initial_capital_usdt"]
    out: dict[str, dict] = {}
    for name, lo, hi in bounds:
        segment = run.equity[lo:hi]
        if segment.size < 2 or not np.isfinite(segment).all():
            raise EvaluationError(f"episode {name}: account trace is not finite")
        prior = float(run.equity[lo - 1]) if lo > 0 else float(capital)
        if not np.isfinite(prior) or prior <= 0:
            raise EvaluationError(f"episode {name}: starting mark {prior!r} is not usable")
        end = float(segment[-1])
        net_return = (end - prior) / prior
        mdd = _drawdown(np.concatenate([[prior], segment]))
        utility = (net_return - UTILITY["drawdown_penalty"] * mdd) / UTILITY["risk_unit_fraction"]
        trades = sum(1 for f in run.fills if lo <= f["bar_index"] < hi)
        exposure = float(np.mean(np.abs(run.positions[lo:hi]) > 0.0))
        out[name] = {
            "utility": float(utility), "net_return": net_return, "max_drawdown": mdd,
            "starting_equity": prior, "money_delta": end - prior,
            "trades": int(trades), "exposure": exposure,
            "gate_pass": bool(net_return > UTILITY["gate_min_return"]
                              and mdd <= UTILITY["gate_max_drawdown"]),
        }
    return out


def window_metrics(run: CandidateRun) -> dict:
    """Whole-window summary, used for deployment reporting rather than selection."""
    capital = ACCOUNT["initial_capital_usdt"]
    equity = run.equity
    net_return = float(equity[-1] - equity[0]) / capital
    steps = np.diff(equity) / capital
    sharpe = None
    if steps.size > 2 and float(np.std(steps)) > 0:
        sharpe = float(np.mean(steps) / np.std(steps) * np.sqrt(len(steps)))
    holding = []
    open_at = None
    for i, pos in enumerate(run.positions):
        if pos != 0.0 and open_at is None:
            open_at = i
        elif pos == 0.0 and open_at is not None:
            holding.append(i - open_at)
            open_at = None
    return {
        "net_return": net_return,
        "max_drawdown": _drawdown(equity),
        "sharpe_per_window": sharpe,
        "fills": len(run.fills),
        "entries": run.entries,
        "exposure": float(np.mean(np.abs(run.positions) > 0.0)),
        "mean_holding_bars": float(np.mean(holding)) if holding else None,
        "bars": int(equity.size),
        "converged": run.converged,
        "passes": run.passes,
        "unmapped_intents": run.unmapped_intents,
    }


def run_candidate_fixed_point_reference(alpha_id: str, params: dict, frame: pd.DataFrame, *,
                                        backend: str = "reference",
                                        max_passes: int = 40) -> CandidateRun:
    """The slow, obvious way: iterate the WHOLE window to a fixed point.

    This exists only to check :func:`run_candidate`. It re-runs the entire window
    every pass and converges roughly one trade at a time, which is why it is not
    the production path -- but it makes no assumption about isolating a single
    trade, so it is the right thing to test the fast path against.
    """
    n = len(frame)
    arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
    engine_frame = frame[["open", "high", "low", "close", "volume"]]
    forced: dict[int, float] = {}
    out = build = None
    for attempt in range(max_passes):
        adapter, pending, applied = _sweep(alpha_id, params, frame, arrays, engine_frame,
                                           backend=backend, forced_exits=forced)
        build = build_intent_tape(adapter.decisions, n, unit_size=1.0, pending_levels=pending)
        out = _engine(engine_frame, build, backend)
        observed = {int(f["bar_index"]): float(f["price"]) for f in out["fills"]
                    if f["reason"] in PROTECTIVE}
        if set(observed) == set(forced) and attempt > 0:
            return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
                                np.asarray(out["positions"], float).reshape(-1),
                                out["fills"], frame.index, True, attempt + 1,
                                int(np.count_nonzero(build.entry_side)),
                                len(build.unmapped_intents))
        forced = observed
    return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
                        np.asarray(out["positions"], float).reshape(-1),
                        out["fills"], frame.index, False, max_passes,
                        int(np.count_nonzero(build.entry_side)),
                        len(build.unmapped_intents))
