"""Guide FP01.2 finding 4: D1 boundary/partition reconciliation.

The lab has TWO daily-return conventions that disagreed by one observation:
the IS side (``experiments/time_edge_contracts.py::daily_returns``) divides
every reported return by the PRECEDING mark, while the D1/OOS side
(``ra.ra07_decay._deployment_slice``) used the first IN-WINDOW mark as the
base, silently dropping the window's first return. ``_deployment_slice`` is
RA-07 published evidence and is never edited; the repaired convention lives
here, is proved by ``FP01-T03``, and is what FP phases use.
"""
from __future__ import annotations

import pandas as pd

from ..experiments.time_edge_contracts import ContractError


def _marks(marks) -> list:
    ordered = sorted(((pd.Timestamp(date), float(value)) for date, value in marks),
                     key=lambda row: row[0])
    for date, _value in ordered:
        if date.tz is None:
            raise ContractError("daily marks must carry UTC timestamps")
    return ordered


def windowed_returns(marks, *, start, end, prior_mark=None) -> dict:
    """Repaired D1/OOS daily returns over ``[start, end)``.

    Every reported return divides by the PRECEDING mark, including the first
    in-window mark, whose base is the last mark strictly before the window
    (``prior_mark`` when supplied, otherwise looked up in ``marks``).
    Missing evidence stays missing: no prior mark -> explicit status + reason,
    never an invented base of 1.0 and never a silently shortened series.
    """
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    ordered = _marks(marks)
    inside = [(date, value) for date, value in ordered if lo <= date < hi]
    if not inside:
        return {"status": "NO_MARKS_IN_WINDOW", "days": 0, "returns": [],
                "reason": f"no daily mark in [{lo.isoformat()}, {hi.isoformat()})"}
    if prior_mark is None:
        before = [(date, value) for date, value in ordered if date < lo]
        chain = before[-1:] + inside
        base_source = "last_mark_strictly_before_window"
    else:
        base = float(prior_mark)
        if base <= 0:
            return {"status": "NONPOSITIVE_PRIOR_EQUITY", "days": len(inside),
                    "returns": [], "reason": "nonpositive preceding equity; keep the evidence"}
        chain = [(None, base)] + inside
        base_source = "caller_supplied_prior_mark"
    if len(chain) < len(inside) + 1:
        return {"status": "PRIOR_EQUITY_UNAVAILABLE", "days": len(inside), "returns": [],
                "reason": ("first in-window mark has no preceding mark, so its return "
                           "cannot be measured without inventing a denominator")}
    returns = []
    for (prev_date, prev_value), (date, value) in zip(chain, chain[1:]):
        if prev_value <= 0:
            return {"status": "NONPOSITIVE_PRIOR_EQUITY", "days": len(inside),
                    "returns": [],
                    "reason": f"nonpositive equity at {prev_date.isoformat() if prev_date else 'supplied'}"}
        returns.append({"date": date.date().isoformat(),
                        "return": (value / prev_value) - 1.0})
    return {
        "status": "OK",
        "days": len(inside),
        "returns": returns,
        "return_values": [row["return"] for row in returns],
        "mean_daily_return": sum(row["return"] for row in returns) / len(returns),
        "prior_equity_source": base_source,
        "prior_equity": chain[0][1],
        "convention": ("every return divided by the PRECEDING mark, first in-window "
                       "mark included (matches time_edge_contracts.daily_returns)"),
        "mark_span": [inside[0][0].isoformat(), inside[-1][0].isoformat()],
    }


def legacy_first_return_dropped(marks, *, start, end) -> dict:
    """The RA-07 ``_deployment_slice`` convention, reproduced for reconciliation.

    Kept ONLY as the explicit "before" side of the FP-01 reconciliation: it is
    what the published RA-07/deep-dive D1 rows actually did. Never the reported
    convention -- ``windowed_returns`` is.
    """
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    rows = [(pd.Timestamp(d), float(v)) for d, v in marks if lo <= pd.Timestamp(d) < hi]
    rows.sort(key=lambda row: row[0])
    if len(rows) < 2:
        return {"status": "INSUFFICIENT_DAYS", "days": len(rows), "returns": []}
    returns = [(rows[i][1] / rows[i - 1][1]) - 1.0 if rows[i - 1][1] else None
               for i in range(1, len(rows))]
    return {"status": "OK", "days": len(rows), "returns": returns,
            "return_values": [r for r in returns if r is not None]}


def reconcile(marks, *, start, end, prior_mark=None) -> dict:
    """The FP-01 boundary reconciliation artifact for one real window: what the
    published convention dropped, next to the repaired one, from the SAME marks.
    """
    repaired = windowed_returns(marks, start=start, end=end, prior_mark=prior_mark)
    legacy = legacy_first_return_dropped(marks, start=start, end=end)
    delta = None
    if repaired["status"] == "OK" and legacy["status"] == "OK":
        delta = (repaired["mean_daily_return"]
                 - sum(legacy["return_values"]) / len(legacy["return_values"]))
    return {
        "schema": "regime_lab.fp_decay_boundary_reconciliation.v1",
        "window": [str(start), str(end)],
        "repaired": repaired,
        "legacy_ra07_deployment_slice": legacy,
        "observations_added": (len(repaired.get("return_values") or [])
                               - len(legacy.get("return_values") or [])),
        "mean_daily_return_delta": delta,
    }
