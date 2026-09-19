"""RA07.7: concentration, stability and economic scope -- leave-one-out
sensitivity defined and reported for ALL periods/cells (never dropping the
inconvenient one), plus contribution attribution by calendar period,
regime-vintage/fallback, exposure and search cost. Zero engine calls: pure
re-aggregation of already-computed paired rows and already-committed arm
metadata.
"""
from __future__ import annotations

import pandas as pd

from .ra07_stats_primitives import paired_daily_returns


def _month_bucket(date_str: str) -> str:
    return pd.Timestamp(date_str).strftime("%Y-%m")


def leave_one_period_out(rows: list, *, bucket_fn=_month_bucket) -> dict:
    """Pre-defined periods (calendar month buckets); recompute the paired
    mean with each period excluded, one at a time, ALL reported (guide
    RA07.7: 'duoc dinh truoc va report tat ca; khong drop outlier cho ket
    qua dep')."""
    if not rows:
        return {"status": "NO_PAIRED_DAYS", "periods": {}}
    buckets: dict = {}
    for row in rows:
        buckets.setdefault(bucket_fn(row["date"]), []).append(row)
    full_mean = sum(r["diff"] for r in rows) / len(rows)
    out = {}
    for held_out in buckets:
        remaining = [r for name, group in buckets.items() if name != held_out for r in group]
        out[held_out] = {
            "held_out_period": held_out, "held_out_days": len(buckets[held_out]),
            "remaining_days": len(remaining),
            "mean_with_period_excluded": (sum(r["diff"] for r in remaining) / len(remaining)
                                          if remaining else None),
            "delta_vs_full_sample": (None if not remaining else
                                     (sum(r["diff"] for r in remaining) / len(remaining)) - full_mean),
        }
    return {"status": "OK", "full_sample_mean": full_mean, "periods": out,
           "n_periods": len(buckets)}


def contribution_by_period(rows: list, *, bucket_fn=_month_bucket) -> dict:
    """How much of the total paired PnL difference each calendar period
    contributed -- a concentration check, not a significance claim."""
    if not rows:
        return {}
    buckets: dict = {}
    for row in rows:
        buckets.setdefault(bucket_fn(row["date"]), []).append(row["diff"])
    total = sum(d for group in buckets.values() for d in group)
    return {name: {"days": len(group), "sum_diff": sum(group),
                  "share_of_total": (sum(group) / total) if total else None}
           for name, group in sorted(buckets.items())}


def leave_one_cell_out(cell1_primary: dict, cell2_primary: dict) -> dict:
    """With exactly 2 cells this phase, 'leave one cell out' reduces to each
    cell's own already-computed point estimate -- reported explicitly rather
    than silently implied, and no pooled 2-cell aggregate is computed (guide
    RA07.2: no aggregate before enough planned cells or a registered
    partial-scope weighting)."""
    return {
        "cell1_alone": {"point_estimate": (cell1_primary.get("bootstrap") or {}).get("point_estimate"),
                        "ci_95": (cell1_primary.get("bootstrap") or {}).get("ci_95")},
        "cell2_alone": {"point_estimate": (cell2_primary.get("bootstrap") or {}).get("point_estimate"),
                        "ci_95": (cell2_primary.get("bootstrap") or {}).get("ci_95")},
        "pooled_2_cell_aggregate": {"computed": False,
                                    "reason": "no pre-registered partial-scope capital weighting exists"},
        "agreement": {
            "same_sign": (None if not (cell1_primary.get("bootstrap") and cell2_primary.get("bootstrap"))
                         else (cell1_primary["bootstrap"]["point_estimate"] > 0)
                         == (cell2_primary["bootstrap"]["point_estimate"] > 0)),
        },
    }


def regime_vintage_attribution(emissions_in_window: list) -> dict:
    """Which model_id(s)/namespaces were actually active during the
    evaluation window -- descriptive only; this module does not re-derive
    the JM/M0 classification (that lives in host-emissions-03.json's own
    `model_registry` field, F-05's finding, never recomputed here)."""
    if not emissions_in_window:
        return {"status": "NO_EMISSIONS_IN_WINDOW", "vintages": []}
    by_namespace: dict = {}
    for row in emissions_in_window:
        ns = row.get("state_namespace")
        entry = by_namespace.setdefault(ns, {"model_id": row.get("model_id"), "count": 0})
        entry["count"] += 1
    return {"status": "OK", "distinct_namespaces_active": len(by_namespace),
           "vintages": [{"namespace": ns, **info} for ns, info in by_namespace.items()],
           "note": "JM/M0 classification per namespace is F-05's own finding "
                  "(host-emissions-03.json model_registry), not re-derived here"}


def search_frequency_and_cost(arms: dict) -> dict:
    """Reuses each arm's own already-measured real wall time / switch count
    -- no new timing run."""
    out = {}
    for name, outcome in arms.items():
        if not outcome.get("ok"):
            out[name] = {"status": "NOT_EVALUABLE"}
            continue
        run = outcome["run"]
        out[name] = {
            "status": "OK", "wall_seconds": run.get("wall_seconds"),
            "fold_count": len(run.get("fold_selection_table") or []),
            "switches_admitted": outcome.get("switches_admitted"),
            "switches_kept_incumbent": outcome.get("switches_kept_incumbent"),
        }
    return out


def build_sensitivity_report(*, cell1_arms: dict, cell2_arms: dict, uncertainty_results: dict,
                             cell1_window_emissions: list) -> dict:
    rows_cell1 = paired_daily_returns(
        (cell1_arms.get("M4_REGIME", {}).get("run", {}).get("account") or {}).get("equity_daily") or [],
        (cell1_arms.get("M4_CAL_MATCHED", {}).get("run", {}).get("account") or {}).get("equity_daily") or [])
    return {
        "schema": "regime_lab.ra07_sensitivity_report.v1",
        "leave_one_period_out_cell1_primary": leave_one_period_out(rows_cell1),
        "contribution_by_period_cell1_primary": contribution_by_period(rows_cell1),
        "leave_one_cell_out": leave_one_cell_out(uncertainty_results["primary"],
                                                 uncertainty_results["secondary"]
                                                 ["cell2: M4_REGIME - M4_CAL_MATCHED"]),
        "regime_vintage_attribution_cell1": regime_vintage_attribution(cell1_window_emissions),
        "search_frequency_and_cost_cell1": search_frequency_and_cost(cell1_arms),
        "search_frequency_and_cost_cell2": search_frequency_and_cost(cell2_arms),
        "rule": ("all periods/cells reported, none dropped as an outlier (guide RA07.7); relative "
                "improvement when both arms lose money is a separate question from live "
                "deployment eligibility and is never conflated here"),
    }
