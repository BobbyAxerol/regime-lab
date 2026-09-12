"""L08.2 / L08.3 — the A/B/C/D factorial and arm E, on one continuous account each.

What separates the arms is exactly two things: which selector proposes a
parameter set, and when it is allowed to. Everything else -- the engine, the
costs, the retention rule, the training memory, the number of refreshes -- is
held identical, because a difference anywhere else would be a second
explanation for whatever the contrast shows.

    arm  selector              refresh timing
    A    installed WFO         frozen calendar          (baseline)
    B    neighborhood          frozen calendar          (robustness)
    C    installed WFO         regime-triggered         (timing)
    D    neighborhood          regime-triggered         (interaction)
    E    neighborhood + bank + response policy          (extension, not a substitute)

Each arm is delivered through LAB-07's continuous account: one chronological
sweep, one engine pass, no reset at a boundary. LAB-04 evaluated folds
independently, which was right for measuring a selector and wrong for measuring
what an account would have done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..integration.activation import parameter_digest
from ..integration.continuous_account import VersionWindow, run_continuous_account

ARMS = ("A", "B", "C", "D", "E")

#: arm -> (which LAB-04 selector's choice it deploys, which schedule it follows)
ARM_DEFINITION = {
    "A": ("arm_A", "calendar", "installed WFO selector on the frozen calendar"),
    "B": ("arm_B", "calendar", "neighborhood selector on the same calendar"),
    "C": ("arm_A", "regime", "installed selector, regime-triggered refresh"),
    "D": ("arm_B", "regime", "neighborhood selector, regime-triggered refresh"),
    "E": ("arm_B", "regime", "neighborhood selector plus bank and response policy"),
}


class FactorialError(RuntimeError):
    """Raised when an arm would not be comparable to the others."""


@dataclass
class ArmResult:
    arm: str
    alpha_id: str
    symbol: str
    status: str
    equity: np.ndarray | None = None
    index: pd.DatetimeIndex | None = None
    fills: list = field(default_factory=list)
    entries: int = 0
    switches: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    #: True when the equity path was rescaled after the engine produced it (the
    #: RISK_ONLY control). The fills then belong to a DIFFERENT path, so the cash
    #: identity does not apply and must not be reported as failing.
    synthetic_equity: bool = False

    def accounting(self) -> dict:
        """The cash identity for this account (L09.6.1), measured not asserted.

        equity[-1] - equity[0] == -sum(side * qty * price) - sum(fee), with side
        +1 for a buy. It closes because the account is flat on the last bar and
        because funding is off on this cohort -- a labelled no-funding cohort,
        never a silent zero. A residual means fills, fees and equity are not
        describing the same account, which is the one thing a return figure
        cannot be allowed to hide.
        """
        if self.equity is None or len(self.equity) < 2:
            return {"status": "NO_ACCOUNT"}
        if self.synthetic_equity:
            return {"status": "SYNTHETIC_EQUITY_PATH",
                    "fills": len(self.fills),
                    "why": ("this arm's equity was rescaled after the engine produced it, so the "
                            "fills describe the unscaled path. The cash identity applies to the "
                            "account that generated the fills, not to a rescaling of it")}
        signed_cash = sum(f["side"] * f["qty"] * f["price"] for f in self.fills)
        fees = sum(f.get("fee", 0.0) for f in self.fills)
        gross = sum(f["qty"] * f["price"] for f in self.fills)
        change = float(self.equity[-1] - self.equity[0])
        residual = change - (-signed_cash - fees)
        return {
            "fills": len(self.fills),
            "gross_notional": float(gross),
            "signed_cash": float(signed_cash),
            "fees_charged": float(fees),
            "funding_charged": 0.0,
            "funding_status": "MISSING_NOT_ZERO; this is a labelled no-funding cohort",
            "one_way_fee_rate_implied": (float(fees / gross) if gross > 0 else None),
            "equity_change": change,
            "identity_residual": float(residual),
            "identity_holds": bool(abs(residual) <= 1e-6 * max(abs(change), 1.0)),
            "identity": "equity[-1] - equity[0] == -sum(side * qty * price) - sum(fee)",
        }

    def daily_returns(self) -> pd.Series:
        if self.equity is None:
            return pd.Series(dtype=float)
        series = pd.Series(self.equity, index=self.index).sort_index()
        return series.resample("1D").last().dropna().pct_change().dropna()

    def as_record(self) -> dict:
        if self.status != "RUN":
            return {"arm": self.arm, "alpha_id": self.alpha_id, "symbol": self.symbol,
                    "status": self.status,
                    "net_return": None, "daily_sharpe": None, "max_drawdown": None,
                    "trades": None, "entries": None,
                    "note": ("null metrics; a blocked or insufficient cell is never booked as a "
                             "PnL of 0, which would bias every aggregate (guide 13.2)"),
                    **self.detail}
        returns = self.daily_returns()
        std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
        peak = np.maximum.accumulate(self.equity)
        return {
            "accounting": self.accounting(),
            "arm": self.arm, "alpha_id": self.alpha_id, "symbol": self.symbol,
            "status": "RUN",
            "net_return": float(self.equity[-1] / self.equity[0] - 1.0),
            "daily_sharpe": (float(returns.mean() / std * np.sqrt(365.0)) if std > 0 else None),
            "max_drawdown": float(np.min(self.equity / peak - 1.0)),
            "daily_observations": int(len(returns)),
            "trades": len(self.fills),
            "entries": int(self.entries),
            "switches_requested": len(self.switches),
            "switches_effected": sum(1 for s in self.switches if s.effective_at_bar is not None),
            # L09.5.6 asks what happens when a campaign is NOT flat at a switch
            # boundary. That path is only visible here: a switch that waited, and
            # what it waited for. A count of switches alone cannot show it.
            "switch_delays": {
                "blocked_bars_total": sum(s.blocked_bars for s in self.switches),
                "max_blocked_bars": max((s.blocked_bars for s in self.switches), default=0),
                # WHAT each switch waited for, accumulated while it waited. The
                # `blocked_reason` field is cleared on activation, so a histogram
                # of final reasons reads {"none": 5} next to 1,380 blocked bars --
                # technically true and exactly backwards. L09.5.6 asks whether a
                # switch ever waited for an open campaign, and only this answers it.
                "blocked_bars_by_reason": {
                    reason: sum(s.blocked_bars_by_reason.get(reason, 0) for s in self.switches)
                    for reason in sorted({r for s in self.switches
                                          for r in s.blocked_bars_by_reason})},
                "switches_that_waited_for_an_open_campaign": sum(
                    1 for s in self.switches
                    if s.blocked_bars_by_reason.get("TRANSITION_BLOCKED_OPEN_CAMPAIGN")),
                "switches_that_waited_for_warm_indicators": sum(
                    1 for s in self.switches
                    if s.blocked_bars_by_reason.get("WAITING_FOR_WARM_INDICATORS")),
                "final_reason_counts": {
                    reason: sum(1 for s in self.switches
                                if (s.blocked_reason or "none") == reason)
                    for reason in sorted({(s.blocked_reason or "none")
                                          for s in self.switches})},
                "final_reason_note": ("`none` here means the switch eventually activated, not "
                                      "that it never waited. The waiting is in "
                                      "blocked_bars_by_reason"),
                "never_effected": [s.activation_id for s in self.switches
                                   if s.effective_at_bar is None],
            },
            "account_resets": 0,
            **self.detail,
        }


def _schedule_from_selections(selections: list[dict], bars: pd.DataFrame, alpha_id: str,
                              *, seed_params: dict | None = None
                              ) -> tuple[VersionWindow, list[VersionWindow], bool]:
    """Turn a list of (cutoff, params) into an initial version plus a schedule.

    A selector that returns nothing admissible at every cutoff is a RESULT, not
    an error: the retention rule keeps the incumbent, and the honest deployment
    of "never selected" is the seed point held for the whole window. An earlier
    version raised here and took a nine-cell run down with it, which turned a
    reportable finding into a crash.
    """
    windows: list[VersionWindow] = []
    for index, record in enumerate(selections):
        params = record["params"]
        if params is None:
            continue                            # retention: the incumbent stays
        cutoff = pd.Timestamp(record["cutoff"])
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize("UTC")
        position = int(bars.index.searchsorted(cutoff))
        if position >= len(bars):
            continue
        windows.append(VersionWindow(
            parameter_version=parameter_digest(params), params=params,
            requested_at_bar=position, activation_id=f"act-{index}"))
    if windows:
        return windows[0], windows[1:], False
    if seed_params is None:
        raise FactorialError(
            f"{alpha_id}: the selector chose nothing at any cutoff and no incumbent seed was "
            "supplied, so there is nothing to deploy")
    return (VersionWindow(parameter_version=parameter_digest(seed_params),
                          params=dict(seed_params), requested_at_bar=0,
                          activation_id="act-incumbent-retained"), [], True)


def run_arm(arm: str, alpha_id: str, symbol: str, bars: pd.DataFrame,
            selections: list[dict], *, backend: str = "reference",
            size_scale: list[float] | None = None) -> ArmResult:
    """One arm on one cell: one continuous account, one engine pass."""
    if arm not in ARM_DEFINITION:
        raise FactorialError(f"unknown arm {arm!r}")
    if not selections:
        return ArmResult(arm, alpha_id, symbol, "NO_SELECTION",
                         detail={"reason": "the selector returned nothing admissible at any "
                                           "cutoff, which is a result and not an error"})
    from .calendar_baseline import SEED_POINTS

    initial, schedule, retained_throughout = _schedule_from_selections(
        selections, bars, alpha_id, seed_params=SEED_POINTS.get(alpha_id))
    run = run_continuous_account(alpha_id, bars, initial=initial, schedule=schedule,
                                 backend=backend)
    equity = run.equity
    detail: dict[str, Any] = {
        "selector": ARM_DEFINITION[arm][0],
        "schedule": ARM_DEFINITION[arm][1],
        "description": ARM_DEFINITION[arm][2],
        "refreshes_requested": len(selections),
        "selector_never_selected": retained_throughout,
        "retention_note": (
            "the selector returned nothing admissible at any cutoff, so the incumbent seed was "
            "held for the whole window. That is the retention rule doing its job, and it is a "
            "reportable result rather than a failed cell" if retained_throughout else None),
        "exit_fixed_point_converged": run.diagnostics.get("exit_fixed_point_converged"),
        "bars": int(len(bars)),
        # L09.6.2: every parameter version this account deployed, and for how long.
        # A version that was requested and never took effect is visible in
        # switches_requested vs switches_effected; one that took effect and traded
        # no bars would be visible here and nowhere else.
        "bars_by_parameter_version": {version: run.version_by_bar.count(version)
                                      for version in dict.fromkeys(run.version_by_bar)},
        "versions_deployed": len(set(run.version_by_bar)),
        "versions_requested": 1 + len(schedule),
    }
    if size_scale is not None:
        # RISK_ONLY: the same trades, resized. Applied to the equity PATH rather
        # than re-run, because changing size changes nothing about which bars the
        # strategy acted on -- that is the whole definition of the control.
        if len(size_scale) != len(equity):
            raise FactorialError("a risk scale must cover every bar of the account")
        steps = np.diff(equity, prepend=equity[0])
        equity = equity[0] + np.cumsum(steps * np.asarray(size_scale, dtype=float))
        detail["risk_scaled"] = True
        detail["mean_size_scale"] = float(np.mean(size_scale))
    return ArmResult(arm, alpha_id, symbol, "RUN", equity=equity, index=run.index,
                     fills=run.fills, entries=run.entries, switches=run.switches,
                     detail=detail, synthetic_equity=size_scale is not None)


def paired_daily_difference(left: ArmResult, right: ArmResult) -> dict:
    """A contrast on the SAME dates, which is the only kind guide 11.3 allows.

    Two arms whose accounts ran over different day sets are not comparable by
    their means; the difference has to be taken per day and only on days both
    were live.
    """
    if left.status != "RUN" or right.status != "RUN":
        return {"contrast": f"{left.arm}-{right.arm}", "status": "INCOMPARABLE",
                "reason": f"{left.arm}={left.status}, {right.arm}={right.status}",
                "mean_daily_difference": None}
    a, b = left.daily_returns(), right.daily_returns()
    shared = a.index.intersection(b.index)
    if len(shared) < 2:
        return {"contrast": f"{left.arm}-{right.arm}", "status": "INSUFFICIENT_SHARED_DAYS",
                "shared_days": int(len(shared)), "mean_daily_difference": None}
    difference = (a.loc[shared] - b.loc[shared])
    return {
        "contrast": f"{left.arm}-{right.arm}",
        "status": "OK",
        "shared_days": int(len(shared)),
        "mean_daily_difference": float(difference.mean()),
        "median_daily_difference": float(difference.median()),
        "std_daily_difference": float(difference.std(ddof=1)),
        "days_left_better": int((difference > 0).sum()),
        "days_right_better": int((difference < 0).sum()),
        "pairing": "same dates only; days where either arm was not live are excluded",
    }
