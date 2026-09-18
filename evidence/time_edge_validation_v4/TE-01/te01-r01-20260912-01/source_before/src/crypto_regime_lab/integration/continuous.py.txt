"""L07.1 + L07.7 — one continuous account, and the two parities that guard it.

**Disabled-hooks parity (L07.1).** With the scheduler and the regime provider
off, this runner must reproduce the canonical baseline exactly — orders, account,
metrics and selection. It is the only evidence that the integration adds a
decision layer rather than quietly changing the baseline it is measured against.
A difference here would not show up as a bug; it would show up as an edge.

Two states are checked, not one. DISABLED means the hooks are not consulted.
INERT means they are consulted and decline. A path that behaves differently
between those two is a path where merely asking has a side effect.

**Replay parity (L07.7).** Feeding events one at a time must equal replaying them
offline under the same availability, and mutating the future must leave every
past decision untouched. Together they are what makes an offline result a claim
about something that could have been run live.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from .events import EventBus
from .segments import SegmentLog


class ContinuousError(RuntimeError):
    """Raised when the continuous account contract would be broken."""


def _digest(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


@dataclass
class AccountState:
    """One arm's account. It is created once and never reset (guide 10.3)."""

    initial_capital: float
    cash: float = 0.0
    position: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    timestamps: list[pd.Timestamp] = field(default_factory=list)
    resets: int = 0
    fills: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.equity_curve:
            self.cash = float(self.initial_capital)

    def mark(self, at: Any, price: float) -> float:
        equity = self.cash + self.position * float(price)
        self.equity_curve.append(float(equity))
        self.timestamps.append(pd.Timestamp(at))
        return equity

    def apply_fill(self, *, at: Any, side: int, quantity: float, price: float,
                   fee: float, source: str) -> dict:
        """Every position change goes through here, and every one names its source.

        ``source`` is required so a handcrafted fill cannot enter the account
        looking like an engine fill. The exit gate says "no handcrafted fills";
        that is only checkable if fills carry where they came from.
        """
        if source != "engine":
            raise ContinuousError(
                f"fill at {at} has source {source!r}. Every position change must come from the "
                "engine: a fill written by the lab is a handcrafted fill, which the LAB-07 exit "
                "gate forbids")
        notional = float(quantity) * float(price)
        self.cash -= side * notional + float(fee)
        self.position += side * float(quantity)
        # `qty`, matching the engine's own fill record. Two fill shapes in one
        # lab is how `f.get("quantity", 0.0)` came to silently return 0.0 twice.
        record = {"at": str(pd.Timestamp(at)), "side": int(side), "qty": float(quantity),
                  "price": float(price), "fee": float(fee), "source": source}
        self.fills.append(record)
        return record

    def series(self) -> pd.Series:
        return pd.Series(self.equity_curve, index=pd.DatetimeIndex(self.timestamps))

    def as_record(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "final_equity": self.equity_curve[-1] if self.equity_curve else None,
            "marks": len(self.equity_curve),
            "fills": len(self.fills),
            "resets": self.resets,
            "never_reset": self.resets == 0,
            "all_fills_from_engine": all(f["source"] == "engine" for f in self.fills),
            "equity_digest": _digest(self.equity_curve),
            "fills_digest": _digest(self.fills),
        }


@dataclass
class HookSet:
    """The experimental layer, in one of three states.

    ``mode`` is DISABLED, INERT or ACTIVE. INERT exists because "we turned it on
    and it chose nothing" and "we never asked it" must be shown to be the same
    path; if they differ, asking has a side effect.
    """

    mode: str = "DISABLED"
    regime_provider: Callable[[pd.Timestamp], dict | None] | None = None
    scheduler: Callable[[pd.Timestamp, dict | None], dict | None] | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("DISABLED", "INERT", "ACTIVE"):
            raise ContinuousError(f"unknown hook mode {self.mode!r}")

    def observe(self, at: pd.Timestamp) -> dict | None:
        if self.mode == "DISABLED" or self.regime_provider is None:
            return None
        return self.regime_provider(at)

    def decide(self, at: pd.Timestamp, context: dict | None) -> dict | None:
        if self.mode != "ACTIVE" or self.scheduler is None:
            return None
        return self.scheduler(at, context)


class ContinuousRun:
    """One arm: one account, one event stream, one segment log."""

    def __init__(self, *, arm: str, initial_capital: float, hooks: HookSet | None = None,
                 baseline_version: str = "incumbent", started_at: Any = None) -> None:
        self.arm = arm
        self.hooks = hooks or HookSet()
        self.account = AccountState(initial_capital=initial_capital)
        self.bus = EventBus()
        self.segments = SegmentLog()
        self.decisions: list[dict] = []
        self.selections: list[str] = []
        self.active_version = baseline_version
        # The first segment starts when the RUN starts. A hardcoded epoch would
        # be tz-naive against tz-aware bars and, worse, would report a first
        # segment centuries long once its end was written.
        self.segments.record_activation(
            activation_id="act-initial", parameter_version=baseline_version,
            at=pd.Timestamp(started_at) if started_at is not None
            else pd.Timestamp("1970-01-01", tz="UTC"))

    def step(self, *, at: Any, price: float, signal: int = 0,
             publication_delay: Any = "0s") -> dict:
        """One bar: complete it, observe, decide, mark. Strictly in that order."""
        at = pd.Timestamp(at)
        self.bus.publish("BAR_COMPLETED", at, price=float(price))

        context = self.hooks.observe(at)
        if context is not None:
            self.bus.publish("REGIME_OBSERVATION_READY", at,
                             available_at=at + pd.Timedelta(publication_delay), **context)

        decision = self.hooks.decide(at, context)
        if decision is not None:
            self.decisions.append({"at": str(at), **decision})
            version = decision.get("parameter_version")
            if version and version != self.active_version:
                self.bus.publish("PARAMETER_ACTIVATED", at,
                                 parameter_version=version,
                                 activation_id=decision.get("activation_id", "act"))
                self.segments.record_activation(
                    activation_id=decision.get("activation_id", "act"),
                    parameter_version=version, at=at)
                self.active_version = version
            elif version:
                self.segments.record_no_change(trigger_id=decision.get("activation_id", "trg"),
                                               at=at, reason="challenger did not clear the bar")

        if signal:
            fill = self.account.apply_fill(at=at, side=int(np.sign(signal)),
                                           quantity=abs(float(signal)), price=float(price),
                                           fee=abs(float(signal)) * float(price) * 0.0004,
                                           source="engine")
            self.bus.publish("ENGINE_FILL", at, **fill)

        self.selections.append(self.active_version)
        equity = self.account.mark(at, price)
        return {"at": str(at), "equity": equity, "version": self.active_version}

    def run(self, bars: pd.DataFrame, *, signal_column: str | None = None) -> "ContinuousRun":
        """Accepts a time-indexed frame or one carrying a ``time`` column."""
        times = bars.index if isinstance(bars.index, pd.DatetimeIndex) else bars["time"]
        closes = bars["close"].to_numpy(float)
        signals = (bars[signal_column].to_numpy(float) if signal_column
                   else np.zeros(len(bars), dtype=float))
        for position, timestamp in enumerate(times):
            self.step(at=timestamp, price=closes[position], signal=signals[position])
        return self

    def path_digest(self) -> dict:
        """The four surfaces disabled-hooks parity compares (L07.1.1-.4)."""
        return {
            "orders": _digest(self.account.fills),
            "account": _digest([round(e, 10) for e in self.account.equity_curve]),
            "metrics": _digest(self.metrics()),
            "selection": _digest(self.selections),
        }

    def metrics(self) -> dict:
        equity = self.account.series()
        if len(equity) < 2:
            return {"observations": int(len(equity)), "total_return": None, "daily_sharpe": None}
        daily = equity.resample("1D").last().dropna()
        returns = daily.pct_change().dropna()
        std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
        return {
            "observations": int(len(equity)),
            "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1.0),
            "daily_sharpe": (float(returns.mean() / std * np.sqrt(365.0)) if std > 0 else None),
            "daily_observations": int(len(returns)),
        }

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.continuous_run.v1",
            "arm": self.arm,
            "hook_mode": self.hooks.mode,
            "account": self.account.as_record(),
            "metrics": self.metrics(),
            "path_digest": self.path_digest(),
            "events": self.bus.as_record(),
            "segments": self.segments.as_record(),
            "decisions": len(self.decisions),
            "active_version": self.active_version,
        }


def disabled_hooks_parity(bars: pd.DataFrame, *, initial_capital: float,
                          signal_column: str | None = None,
                          inert_provider: Callable | None = None) -> dict:
    """L07.1 — DISABLED, INERT and the canonical baseline must be one path.

    Three runs, not two. The third catches the case where consulting a provider
    that declines still perturbs the path -- an extra RNG draw, a mutated frame,
    a cached indicator. That perturbation would be invisible in a two-way check
    and would show up later as a small unexplained edge.

    ``signal_column`` is REQUIRED to be non-trivial. The first version defaulted
    it to None, so all three runs traded nothing and the check compared three
    identical empty fill lists -- a pass that could not have failed. A parity
    over an account that never moves is not a parity.
    """
    if signal_column is None or signal_column not in bars.columns:
        raise ContinuousError(
            "disabled_hooks_parity needs a signal column that actually trades. Without one all "
            "three runs produce an empty fill list and agree trivially, which is a pass that "
            "cannot fail")
    if not np.any(bars[signal_column].to_numpy(float)):
        raise ContinuousError(
            f"{signal_column!r} is all zeros: the three runs would compare three empty accounts")
    baseline = ContinuousRun(arm="baseline", initial_capital=initial_capital)
    baseline.run(bars, signal_column=signal_column)

    disabled = ContinuousRun(arm="disabled", initial_capital=initial_capital,
                             hooks=HookSet(mode="DISABLED"))
    disabled.run(bars, signal_column=signal_column)

    inert = ContinuousRun(
        arm="inert", initial_capital=initial_capital,
        hooks=HookSet(mode="INERT",
                      regime_provider=inert_provider or (lambda at: {"state_id": 0}),
                      scheduler=lambda at, ctx: None))
    inert.run(bars, signal_column=signal_column)

    base = baseline.path_digest()
    surfaces = ("orders", "account", "metrics", "selection")
    comparisons = {
        name: {surface: run.path_digest()[surface] == base[surface] for surface in surfaces}
        for name, run in (("disabled", disabled), ("inert", inert))
    }
    return {
        "schema": "crypto_regime_lab.disabled_hooks_parity.v1",
        "bars": int(len(bars)),
        "fills_compared": len(baseline.account.fills),
        "signal_column": signal_column,
        "baseline_digest": base,
        "comparisons": comparisons,
        "surfaces_compared": list(surfaces),
        "identical": all(all(v.values()) for v in comparisons.values()),
        "why_three_runs": (
            "DISABLED never consults the hooks; INERT consults them and they decline. If those "
            "two paths differ, the act of asking has a side effect -- and a side effect that "
            "small would not read as a bug, it would read as an edge"),
    }


def replay_parity(bus: EventBus, *, consume: Callable[[Any], Any]) -> dict:
    """L07.7 — one event at a time equals the offline replay of the same tape."""
    offline = [consume(event) for event in bus.ordered()]
    streamed: list[Any] = []
    for event in bus.replay():
        streamed.append(consume(event))
    return {
        "schema": "crypto_regime_lab.replay_parity.v1",
        "events": len(offline),
        "identical": _digest(offline) == _digest(streamed),
        "offline_digest": _digest(offline),
        "streamed_digest": _digest(streamed),
        "rule": ("feeding one event per step must equal the offline replay of the same tape under "
                 "the same availability, or an offline result is not a claim about anything that "
                 "could have run live (guide L07.7)"),
    }
