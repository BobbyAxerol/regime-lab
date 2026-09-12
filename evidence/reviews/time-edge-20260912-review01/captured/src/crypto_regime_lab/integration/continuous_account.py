"""L07.4 + T56 — one account whose PARAMETERS change while it keeps running.

This is the deliverable the rest of LAB-07 exists to protect. Everything else
guards a property; this produces the thing being guarded: a single chronological
pass in which the active parameter version changes at activation boundaries, one
intent tape, one engine run, one equity curve.

The alternative — run each version separately and glue the pieces at the
boundaries — is what T56 forbids, and it is worth naming why it is tempting.
Splicing is easier, it produces a smooth-looking curve, and the seams are
invisible in the output. What it silently assumes is that each version starts
flat at its boundary, which is exactly the assumption guide 9.5 spends its whole
length denying: at a switch there is usually an open position, entered under the
old parameters, protected by orders that must keep the old version.

So the switch here can only take effect where guide 9.5 permits — when the book
is flat and the new indicators are warm — and the account never restarts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..alphas.base import Fill, IntentKind, MarketSlice
from ..alphas.contracts import BarDecision
from ..experiments.evaluator import (
    ACCOUNT,
    MAX_SWEEPS,
    PROTECTIVE,
    _engine,
    _exit_oracle,
    build_adapter,
)
from ..quantbt_bridge.intent_tape import build_intent_tape


class ContinuousAccountError(RuntimeError):
    """Raised when the continuous-account contract would be broken."""


@dataclass
class VersionWindow:
    """A parameter version and the bar from which it is REQUESTED.

    Requested, not effective. When it becomes effective depends on the book and
    on indicator warmth, and that gap is the activation delay LAB-07 measures.
    """

    parameter_version: str
    params: dict
    requested_at_bar: int
    activation_id: str
    #: ``None`` means DERIVE it from the adapter's own ``warmup_bars()``. A
    #: hardcoded number here would be a free parameter of the switching policy,
    #: and it moves results: on this cell, 0 / 60 / 512 bars give +0.45% / +0.17%
    #: / -3.07%. The alpha already declares how many bars it refuses to trade
    #: without, so that declaration is the requirement.
    required_warm_bars: int | None = None
    warm_bars_source: str = "derived_from_adapter_warmup_bars"


@dataclass
class SwitchRecord:
    activation_id: str
    parameter_version: str
    requested_at_bar: int
    effective_at_bar: int | None
    blocked_bars: int
    blocked_reason: str | None
    warm_bars_at_activation: int | None = None
    #: bars waited, per reason, accumulated as they happen. `blocked_reason` is
    #: cleared the moment a switch activates, so without this history a switch
    #: that waited 350 bars for an open campaign to close is indistinguishable
    #: from one that never waited at all -- and guide L09.5.6 asks specifically
    #: what happens when a campaign is NOT flat at a switch boundary.
    blocked_bars_by_reason: dict = field(default_factory=dict)

    def wait(self, reason: str) -> None:
        self.blocked_bars += 1
        self.blocked_reason = reason
        self.blocked_bars_by_reason[reason] = self.blocked_bars_by_reason.get(reason, 0) + 1

    def as_record(self) -> dict:
        return {
            "activation_id": self.activation_id,
            "parameter_version": self.parameter_version,
            "requested_at_bar": self.requested_at_bar,
            "effective_at_bar": self.effective_at_bar,
            "blocked_bars": self.blocked_bars,
            "blocked_reason": self.blocked_reason,
            "blocked_bars_by_reason": dict(self.blocked_bars_by_reason),
            "warm_bars_at_activation": self.warm_bars_at_activation,
        }


@dataclass
class ContinuousAccountRun:
    equity: np.ndarray
    positions: np.ndarray
    fills: list[dict]
    index: pd.DatetimeIndex
    switches: list[SwitchRecord]
    version_by_bar: list[str]
    entries: int
    warm_requirements: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)

    def as_record(self) -> dict:
        by_version: dict[str, int] = {}
        for version in self.version_by_bar:
            by_version[version] = by_version.get(version, 0) + 1
        return {
            "schema": "crypto_regime_lab.continuous_account_run.v1",
            "bars": int(len(self.index)),
            "entries": int(self.entries),
            "fills": len(self.fills),
            "final_equity": float(self.equity[-1]),
            "initial_equity": float(self.equity[0]),
            "total_return": float(self.equity[-1] / self.equity[0] - 1.0),
            "bars_by_parameter_version": by_version,
            "switches": [s.as_record() for s in self.switches],
            "warm_bar_requirements": self.warm_requirements,
            "warm_bar_rule": (
                "the requirement is the ADAPTER'S OWN declared warmup_bars(), counted from the "
                "bar the switch was requested. A hardcoded constant would be an unregistered "
                "free parameter of the switching policy, and it moves the result"),
            "warmup_gate_semantics": (
                "for an adapter that precomputes its indicator arrays causally over the whole "
                "slice, the VALUES at a bar are already correct, so this gate does not make them "
                "more so. What it guarantees is that the new version has been running on live "
                "bars for at least as long as it itself declares it needs before trading -- a "
                "policy delay, and it is reported as one rather than as an accuracy claim"),
            "switches_effected": sum(1 for s in self.switches if s.effective_at_bar is not None),
            "account_resets": 0,
            "spliced_from_independent_runs": False,
            "single_engine_pass": True,
            "exit_fixed_point_converged": self.diagnostics.get(
                "exit_fixed_point_converged"),
            "protective_exits": self.diagnostics.get("protective_exits"),
            "contract": (
                "ONE chronological sweep and ONE engine run over the whole window. The active "
                "parameter version changes at activation boundaries; the account does not "
                "restart, and no segment's equity comes from a separate run (T56, guide 10.3)"),
            **{k: v for k, v in self.diagnostics.items() if k != "applied_exits"},
            "applied_exit_count": len(self.diagnostics.get("applied_exits", {})),
        }


def run_continuous_account(alpha_id: str, frame: pd.DataFrame, *,
                           initial: VersionWindow,
                           schedule: list[VersionWindow],
                           backend: str = "reference",
                           max_sweeps: int = MAX_SWEEPS) -> ContinuousAccountRun:
    """Sweep once, switching parameter versions only where guide 9.5 allows.

    A requested switch waits for BOTH conditions, in this order:

    1. the book is flat -- an open campaign keeps the parameters it entered with,
       and is never closed early to let the switch land;
    2. the new version's indicators are causally warm -- counted from the bar the
       switch was requested, because that is when the new adapter starts seeing
       bars, and never carried over from the old version's state.
    """
    n = len(frame)
    if n < 10:
        raise ContinuousAccountError(f"window of {n} bars is too short")
    arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
    engine_frame = frame[["open", "high", "low", "close", "volume"]]
    market = MarketSlice(*arrays, index=frame.index)

    ordered_schedule = sorted(schedule, key=lambda w: w.requested_at_bar)

    def sweep(forced_exits: dict[int, float] | None):
        return _one_sweep(alpha_id, frame, arrays, engine_frame, market, n,
                          initial=initial, schedule=ordered_schedule, backend=backend,
                          forced_exits=forced_exits)

    # The same fixed point run_candidate uses. A single forward pass schedules
    # protective exits from the per-trade oracle; the whole-window engine run may
    # disagree once several positions interact, and an unverified disagreement
    # means the adapter was driven by exits the account did not actually get.
    # A-SC never fires a protective order, so this loop converges on the first
    # pass here -- but A-HMA, A-VWAP and A-HASH all rest stops, and LAB-08 runs
    # those on this same function.
    forced: dict[int, float] | None = None
    result = None
    for attempt in range(max_sweeps):
        result = sweep(forced)
        observed = {int(f["bar_index"]): float(f["price"]) for f in result.fills
                    if f["reason"] in PROTECTIVE}
        result.diagnostics["sweeps"] = attempt + 1
        result.diagnostics["protective_exits"] = len(observed)
        if set(observed) == set(result.diagnostics["applied_exits"]):
            result.diagnostics["exit_fixed_point_converged"] = True
            return result
        forced = observed
    result.diagnostics["exit_fixed_point_converged"] = False
    result.diagnostics["unconverged_exit_symmetric_difference"] = len(
        set(result.diagnostics["applied_exits"]).symmetric_difference(
            {int(f["bar_index"]) for f in result.fills if f["reason"] in PROTECTIVE}))
    return result


def _one_sweep(alpha_id: str, frame: pd.DataFrame, arrays, engine_frame, market,
               n: int, *, initial: VersionWindow, schedule: list[VersionWindow],
               backend: str, forced_exits: dict[int, float] | None) -> ContinuousAccountRun:
    """One chronological pass. Exits come from the oracle, or from a previously
    observed whole-window run when ``forced_exits`` is supplied."""
    open_ = arrays[0]
    pending = list(schedule)
    # A02: a version selected at a later cutoff may not be active before its own
    # requested bar. If the first (initial) version is requested after bar 0, the
    # account is flat until then instead of backfilling it to bar 0.
    active_ready = initial.requested_at_bar <= 0
    active = initial if active_ready else None
    adapter = build_adapter(alpha_id, initial.params, market)
    # Every version's adapter is fed EVERY bar from the moment it is requested,
    # so its indicators warm on real history rather than being reinitialised at
    # the switch. Only the active one may emit intents.
    shadow: dict[str, tuple[Any, VersionWindow, int]] = {}

    switches: list[SwitchRecord] = []
    version_by_bar: list[str] = []
    # The decision tape must be assembled FROM THE ACTIVE ADAPTER AT EACH BAR.
    # Reading `adapter.decisions` at the end instead would silently return only
    # the last version's decisions -- every bar traded under an earlier version
    # would vanish from the tape while still counting as an entry, which is how
    # a run can report 75 entries and 18 fills.
    tape_decisions: list = []
    pending_levels: dict[int, tuple[float, float]] = {}
    next_exit_bar: int | None = None
    next_exit_price: float | None = None
    entries = 0

    applied_exits: dict[int, float] = {}
    for t in range(n):
        if not active_ready and t >= initial.requested_at_bar:
            active_ready = True
            active = initial
        if not active_ready:
            version_by_bar.append("FLAT_UNTIL_READY")
            tape_decisions.append(BarDecision(index=t, position_entering_bar=0.0,
                                              target_after_close=0.0, intents=[]))
            continue
        # -- an exit observed by a previous whole-window run takes precedence
        if forced_exits is not None and t in forced_exits and adapter.state.position != 0.0:
            adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
                                 quantity=-adapter.state.position,
                                 price=float(forced_exits[t]), intent_kind=IntentKind.EXIT_ALL))
            applied_exits[t] = float(forced_exits[t])
            next_exit_bar, next_exit_price = None, None
        # -- protective exit that the oracle scheduled for this bar
        elif next_exit_bar == t and adapter.state.position != 0.0:
            adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
                                 quantity=-adapter.state.position,
                                 price=float(next_exit_price), intent_kind=IntentKind.EXIT_ALL))
            applied_exits[t] = float(next_exit_price)
            next_exit_bar, next_exit_price = None, None

        # -- newly requested versions start warming their own indicators
        while pending and pending[0].requested_at_bar <= t:
            window = pending.pop(0)
            candidate = build_adapter(alpha_id, window.params, market)
            if window.required_warm_bars is None:
                window.required_warm_bars = int(candidate.warmup_bars())
                window.warm_bars_source = "derived_from_adapter_warmup_bars"
            else:
                window.warm_bars_source = "explicitly_overridden"
            shadow[window.activation_id] = (candidate, window, t)
            switches.append(SwitchRecord(
                activation_id=window.activation_id,
                parameter_version=window.parameter_version,
                requested_at_bar=window.requested_at_bar,
                effective_at_bar=None, blocked_bars=0, blocked_reason="REQUESTED"))

        # -- can any requested version take effect on this bar?
        for activation_id, (candidate_adapter, window, requested_bar) in list(shadow.items()):
            record = next(s for s in switches if s.activation_id == activation_id)
            warm_bars = t - requested_bar
            if adapter.state.position != 0.0:
                record.wait("TRANSITION_BLOCKED_OPEN_CAMPAIGN")
                continue
            if warm_bars < window.required_warm_bars:
                record.wait("WAITING_FOR_WARM_INDICATORS")
                continue
            adapter = candidate_adapter          # the warmed adapter, not a fresh one
            active = window
            record.effective_at_bar = t
            record.blocked_reason = None
            record.warm_bars_at_activation = warm_bars
            del shadow[activation_id]

        # -- every shadow adapter observes the bar so its indicators stay causal
        for candidate_adapter, _, _ in shadow.values():
            if candidate_adapter is not adapter:
                candidate_adapter.on_bar_close(t)

        version_by_bar.append(active.parameter_version)
        decision = adapter.on_bar_close(t)
        tape_decisions.append(decision)
        for intent in decision.intents:
            if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and t + 1 < n:
                side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
                qty = ACCOUNT["entry_notional_usdt"] / max(float(open_[t + 1]), 1e-12)
                follow_ups = adapter.on_fill(Fill(index=t + 1, side=side,
                                                 quantity=float(side) * qty,
                                                 price=float(open_[t + 1]),
                                                 intent_kind=intent.kind))
                entries += 1
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
                adapter.on_fill(Fill(index=t + 1, side=-int(np.sign(adapter.state.position)),
                                     quantity=-adapter.state.position,
                                     price=float(open_[t + 1]),
                                     intent_kind=IntentKind.EXIT_ALL))
                next_exit_bar, next_exit_price = None, None

        # a switch requested while flat, on a bar with no new entry, may land next loop
        if adapter.state.position == 0.0 and shadow:
            for activation_id in list(shadow):
                record = next(s for s in switches if s.activation_id == activation_id)
                if record.blocked_reason == "TRANSITION_BLOCKED_OPEN_CAMPAIGN":
                    record.blocked_reason = "WAITING_FOR_WARM_INDICATORS"

    if len(tape_decisions) != n:
        raise ContinuousAccountError(
            f"the decision tape has {len(tape_decisions)} rows for {n} bars; every bar must "
            "contribute exactly one decision from whichever version was active on it")
    build = build_intent_tape(tape_decisions, n, unit_size=1.0, pending_levels=pending_levels)
    out = _engine(engine_frame, build, backend)
    return ContinuousAccountRun(
        equity=np.asarray(out["equity"], float).reshape(-1),
        positions=np.asarray(out["positions"], float).reshape(-1),
        fills=out["fills"], index=frame.index, switches=switches,
        version_by_bar=version_by_bar, entries=entries,
        warm_requirements={w.activation_id: {"required_warm_bars": w.required_warm_bars,
                                             "source": w.warm_bars_source}
                           for w in schedule},
        diagnostics={"engine_backend": backend,
                     "unmapped_intents": len(build.unmapped_intents),
                     "applied_exits": applied_exits,
                     "tape_rows": len(tape_decisions),
                     "tape_source": ("the active adapter at each bar, not the final adapter's "
                                     "accumulated list")})


#: The fields a fill must carry for a parity to mean anything.
FILL_KEY_FIELDS = ("bar_index", "qty", "price", "side", "reason")


def fills_key(fills: list[dict]) -> list[tuple]:
    """Index every field by its REAL key, with no default to fall back to.

    This read ``f.get("quantity", 0.0)`` while the engine's key is ``qty``, so
    the quantity component was 0.0 on both sides of every comparison -- two runs
    with different fill sizes would still have matched. The same key-name slip
    had already been found once, in the replay consumer, which is why a missing
    field now raises instead of defaulting.
    """
    keyed = []
    for fill in fills:
        missing = set(FILL_KEY_FIELDS) - set(fill)
        if missing:
            raise ContinuousAccountError(
                f"engine fill is missing {sorted(missing)}; a parity that defaults them compares "
                f"constants. keys present: {sorted(fill)}")
        keyed.append((int(fill["bar_index"]), fill["reason"], int(fill["side"]),
                      round(float(fill["price"]), 10), round(float(fill["qty"]), 12)))
    return keyed


def integration_baseline_parity(alpha_id: str, frame: pd.DataFrame, params: dict, *,
                                backend: str = "reference") -> dict:
    """L07.1.1-.4 — with no schedule, the integration IS the canonical baseline.

    This is the disabled-hooks parity that matters. The lightweight version in
    ``continuous.py`` shows that consulting an inert hook has no side effect; this
    one shows that the whole integration path, running a real alpha over real
    bars with a real engine, reproduces ``run_candidate`` exactly when nothing is
    scheduled. If it did not, every arm comparison downstream would be measured
    against a baseline this phase had quietly altered.

    Four surfaces, because equal final equity is the weakest of them and the
    easiest to get by accident (guide 13.6 lists it as a forbidden parity claim).
    """
    from ..experiments.evaluator import run_candidate

    canonical = run_candidate(alpha_id, params, frame, backend=backend)
    integrated = run_continuous_account(
        alpha_id, frame,
        initial=VersionWindow(parameter_version="baseline", params=params,
                              requested_at_bar=0, activation_id="act-baseline"),
        schedule=[], backend=backend)
    # A fourth, non-trivial surface: schedule an activation to the SAME
    # parameters halfway through. It must be a no-op. Counting how many bars
    # report the one scheduled version would be trivially true with an empty
    # schedule -- this exercises the switching machinery and requires it to
    # change nothing.
    no_op = run_continuous_account(
        alpha_id, frame,
        initial=VersionWindow(parameter_version="baseline", params=params,
                              requested_at_bar=0, activation_id="act-baseline"),
        schedule=[VersionWindow(parameter_version="baseline-again", params=dict(params),
                                requested_at_bar=len(frame) // 2,
                                activation_id="act-same")],
        backend=backend)

    equity_same = np.allclose(canonical.equity, integrated.equity, rtol=0, atol=1e-9)

    def metrics_of(equity: np.ndarray, index) -> dict:
        """The reported metric set, not just the last number.

        Equal final equity is the weakest possible parity and guide 13.6 lists
        it among the claims that may not stand alone -- so the surface compares
        the whole reported set, whose path dependence makes agreement mean
        something.
        """
        series = pd.Series(equity, index=index).sort_index()
        daily = series.resample("1D").last().dropna()
        returns = daily.pct_change().dropna()
        std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
        peak = np.maximum.accumulate(equity)
        return {
            "total_return": round(float(equity[-1] / equity[0] - 1.0), 12),
            "daily_sharpe": (round(float(returns.mean() / std * np.sqrt(365.0)), 10)
                             if std > 0 else None),
            "max_drawdown": round(float(np.min(equity / peak - 1.0)), 12),
            "daily_observations": int(len(returns)),
            "final_equity": round(float(equity[-1]), 10),
        }

    canonical_metrics = metrics_of(canonical.equity, frame.index)
    integrated_metrics = metrics_of(integrated.equity, frame.index)
    return {
        "schema": "crypto_regime_lab.integration_baseline_parity.v1",
        "bars": int(len(frame)),
        "surfaces": {
            "orders": fills_key(canonical.fills) == fills_key(integrated.fills),
            "account": bool(equity_same),
            "metrics": canonical_metrics == integrated_metrics,
            "selection": (fills_key(no_op.fills) == fills_key(canonical.fills)
                          and np.allclose(no_op.equity, canonical.equity, rtol=0, atol=1e-9)),
        },
        "canonical_metrics": canonical_metrics,
        "integrated_metrics": integrated_metrics,
        "selection_surface_is": (
            "an activation to the SAME parameters, scheduled halfway through, must be a no-op. "
            "Counting how many bars report the scheduled version would be trivially true with an "
            "empty schedule; this runs the switching machinery and requires it to change nothing"),
        "no_op_switch_fills": len(no_op.fills),
        "canonical_fills": len(canonical.fills),
        "integrated_fills": len(integrated.fills),
        "canonical_final_equity": float(canonical.equity[-1]),
        "integrated_final_equity": float(integrated.equity[-1]),
        "max_absolute_equity_difference": float(np.max(np.abs(
            canonical.equity - integrated.equity))),
        "identical": bool(
            fills_key(canonical.fills) == fills_key(integrated.fills) and equity_same),
        "why_four_surfaces": (
            "equal final equity is the weakest possible parity and guide 13.6 forbids it as a "
            "standalone claim, so metrics compares the whole reported set and selection runs the "
            "switching machinery on a no-op activation instead of counting a constant"),
    }
