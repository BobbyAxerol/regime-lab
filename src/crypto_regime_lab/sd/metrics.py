"""SD-01: canonical Sharpe wrapper (guide SS2.1, SS8.2 SD01.4).

Reuses, verbatim, the two already-built and already-tested primitives this
lab's own RA-07/FP history established for exactly this purpose -- this
module is a THIN windowing/composition layer, never a new return-computation
engine (guide SS0.1: reuse existing correct parts via dependency verification):

  * ``experiments.time_edge_contracts.daily_returns`` -- the canonical
    (date, equity) -> (date, return) transform: preceding-equity first
    observation, a hard ``ContractError`` on any missing/duplicate/unordered
    day (never a silent forward-fill), and an EXACT expected-day-count check
    that closes the exact bug guide SS2.1 names verbatim ("khong vo tinh
    thanh 185/29 nhu scope mismatch da audit").
  * ``ra.ra07_stats_primitives.sharpe`` -- typed
    ZERO_VARIANCE/TOO_FEW_OBSERVATIONS status, fixed sqrt(365)
    annualization, never a silent 0.0 substitute.

Neither of these is ``quantbt.metrics.performance.sharpe`` or
``quantbt.core.types.BacktestResult.daily_equity`` -- both were probed
against the actually-installed quantbt==1.1.1 package before this module was
written, and both have a real, verified silent-failure mode this study's own
rules forbid: ``sharpe()`` returns a bare ``0.0`` when the sample has zero
variance (indistinguishable from a genuinely-computed zero), and
``daily_equity`` calls ``resample("1D").last().ffill()`` before
``pct_change()``, which silently assigns a 0% return to any missing market
day. Neither failure mode exists in the two primitives this module wraps.

``r_f,d = 0`` (guide SS2.1's own frozen default, matching this lab's prior
RA-07/FP convention) -- ``ra07_stats_primitives.sharpe`` never subtracts a
risk-free rate, so every returns list passed through this module is already
the excess-return series under that pinned convention.
"""
from __future__ import annotations

from ..experiments.time_edge_contracts import ContractError, daily_returns
from ..ra.ra07_stats_primitives import sharpe as _typed_sharpe

RISK_FREE_DAILY = 0.0
IS_WINDOW_DAYS = 180
FORWARD_WINDOW_DAYS = 56
D2_WINDOW_DAYS = 56


class MetricWindowError(ValueError):
    """A requested Sharpe window could not be built from the raw equity rows given."""


def window_sharpe(equity_daily_rows: list, *, initial_equity: float,
                  window_start: str, window_end: str, expected_days: int) -> dict:
    """One canonical Sharpe number for one EXACT calendar window.

    ``equity_daily_rows`` is a list of ``(iso_date, equity)`` pairs spanning
    at least one day strictly before ``window_start`` through ``window_end``
    (exclusive) -- that one leading day supplies the preceding-equity base
    for the window's own first return (guide SS2.1: "Observation dau account
    dung initial equity truoc fee/fill dau tien"), and ``initial_equity`` is
    the pre-fee balance before the FIRST row in ``equity_daily_rows``, used
    only if that row itself is the window's own first return.

    Raises ``MetricWindowError`` -- never silently returns a wrong count --
    if the window cannot be built with EXACTLY ``expected_days`` returns
    (the guide SS2.1 180/56 boundary bug this module exists to close), or if
    any day in range is missing, duplicated or unordered.

    ``window_start``/``window_end`` accept a bare ``YYYY-MM-DD`` day label,
    matching this lab's own convention elsewhere (origins/cutoffs); the
    underlying ``time_edge_contracts.daily_returns`` requires an explicit
    UTC offset on its own ``start``/``end`` (unlike its ``rows`` dates,
    which DO accept a bare day label) -- normalized here so callers never
    have to know that asymmetry.
    """
    def _day(value: str) -> str:
        return f"{value}T00:00:00+00:00" if len(value) == 10 else value

    try:
        rows = daily_returns(equity_daily_rows, initial_equity=initial_equity,
                             start=_day(window_start), end=_day(window_end))
    except ContractError as exc:
        raise MetricWindowError(str(exc)) from exc
    if len(rows) != expected_days:
        raise MetricWindowError(
            f"expected exactly {expected_days} returns in [{window_start}, {window_end}), "
            f"got {len(rows)}")
    returns = [r[1] for r in rows]
    result = _typed_sharpe(returns)
    return {"window_start": window_start, "window_end": window_end,
           "n_days": len(returns), "returns": returns,
           "sharpe": result["value"], "sharpe_status": result["status"]}


def signed_decay(is_window: dict, forward_window: dict) -> dict:
    """D = SR_IS - SR_FWD (guide SS2.2). Signed -- never absolute-valued,
    never clipped to 0, never substituted by a retention ratio. Undefined
    input (either window's own sharpe_status != OK) propagates as a typed
    null, never a fabricated numeric decay."""
    if is_window["sharpe_status"] != "OK" or forward_window["sharpe_status"] != "OK":
        return {"value": None, "status": "UNDEFINED_INPUT",
               "is_status": is_window["sharpe_status"],
               "fwd_status": forward_window["sharpe_status"]}
    return {"value": is_window["sharpe"] - forward_window["sharpe"], "status": "OK"}


def relative_decay(candidate_decay: dict, anchor_decay: dict) -> dict:
    """Y = D(candidate) - D(anchor) (guide SS3.3), the relative Sharpe-decay
    label in Sharpe points. Y(anchor, anchor) = 0 by construction whenever
    both sides are the identical decay record; undefined input propagates
    as a typed null."""
    if candidate_decay["status"] != "OK" or anchor_decay["status"] != "OK":
        return {"value": None, "status": "UNDEFINED_INPUT",
               "candidate_status": candidate_decay["status"],
               "anchor_status": anchor_decay["status"]}
    return {"value": candidate_decay["value"] - anchor_decay["value"], "status": "OK"}


def paired_reduction(decay_b: dict, decay_c: dict) -> dict:
    """R = D_B - D_C (guide SS2.3). R > 0 means C decays less than B.
    Undefined input propagates as a typed null, never a fabricated 0."""
    if decay_b["status"] != "OK" or decay_c["status"] != "OK":
        return {"value": None, "status": "UNDEFINED_INPUT",
               "b_status": decay_b["status"], "c_status": decay_c["status"]}
    return {"value": decay_b["value"] - decay_c["value"], "status": "OK"}
