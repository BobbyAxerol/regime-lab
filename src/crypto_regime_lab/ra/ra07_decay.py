"""RA07.4: D1/D2/D3 decay, guide section 13.2's three DIFFERENT objects --
never conflated, never averaged into one "decay curve".

D1 (IS->OOS) needs one cheap REAL replay per fold: `TrainingScorer` re-run on
the ALREADY-KNOWN selected params over their ALREADY-KNOWN train window (no
new Optuna search, deterministic, guide RA07.4: "D2 can frozen selected
params replay bang engine" -- the same replay-not-search budget class
applies to D1's IS leg by direct analogy). D2 and D3 make ZERO new engine
calls: D2 reuses RA-06 Panel B's already-committed KEEP-branch anchors, D3
re-slices RA-05/RA-07 cell arms' own already-committed equity_daily.
"""
from __future__ import annotations

import pandas as pd

from ..time_edge.execution import TrainingScorer
from ..time_edge.storage import digest
from .ra07_stats_primitives import sharpe

ROW_FIELDS = (
    "selection_id", "theta_digest", "alpha", "symbol", "arm", "selector_contract",
    "comparison_kind", "left_window", "right_window", "horizon", "observed_days",
    "metric_name", "metric_definition", "unit", "raw_or_penalized",
    "left_value", "right_value", "signed_delta", "validity_status",
    "fills", "campaigns_closed", "campaigns_open", "exposure_days", "support_count",
    "regime_at_selection", "regime_in_window", "parameter_age", "diagnostic_only",
)


def _row(**kwargs) -> dict:
    row = {field: None for field in ROW_FIELDS}
    row.update(kwargs)
    unknown = set(kwargs) - set(ROW_FIELDS)
    if unknown:
        raise ValueError(f"D1/D2/D3 row schema violation: unknown fields {unknown}")
    return row


def _deployment_slice(equity_daily: list, *, start: str, end: str) -> dict:
    rows = [(pd.Timestamp(d), v) for d, v in equity_daily
           if pd.Timestamp(start) <= pd.Timestamp(d) < pd.Timestamp(end)]
    rows.sort(key=lambda r: r[0])
    if len(rows) < 2:
        return {"status": "INSUFFICIENT_DAYS", "days": len(rows), "returns": []}
    returns = [(rows[i][1] / rows[i - 1][1]) - 1.0 if rows[i - 1][1] else None
              for i in range(1, len(rows))]
    return {"status": "OK", "days": len(rows), "returns": returns,
           "mean_daily_return": (sum(r for r in returns if r is not None) / len(returns)
                                 if returns else None)}


def compute_d1_rows(*, prepared, alpha_id: str, symbol: str, arm: str, fold_row: dict,
                    equity_daily: list, deploy_end: str, evidence_dir, lab_run_id: str,
                    regime_at_selection) -> list:
    """D1: same selected params, real IS metrics (fresh deterministic replay)
    vs real post-selection OOS metrics (sliced from the SAME arm's own real
    equity_daily) -- guide 13.2's explicit caveat carried in every row:
    IS carries selection bias, this is NOT an unbiased causal decay
    estimator."""
    train_start = pd.Timestamp(fold_row["train_start"])
    cutoff = pd.Timestamp(fold_row["test_start"])
    params = dict(fold_row["selected_params"])
    theta_digest = digest(params)[:16]
    scorer = TrainingScorer(prepared, alpha_id, train_start, cutoff, evidence_dir, lab_run_id)
    train_index = prepared.frame.index[(prepared.frame.index >= train_start)
                                       & (prepared.frame.index < cutoff)]
    scorer(params=params, index=train_index)
    is_record = scorer.cache[digest(params)]
    # `daily_returns` is a list of (date_iso, return_value) PAIRS (guide's
    # own time_edge_contracts.daily_returns shape, the same convention as
    # `equity_daily` elsewhere in this codebase) -- NOT a list of bare
    # scalars. Caught before running: the naive `if r is not None` filter
    # over the raw pairs would have silently kept every row (a tuple is
    # never None) and then summed/averaged (date, value) TUPLES instead of
    # the returns themselves.
    is_returns = [float(value) for _, value in (is_record.get("daily_returns") or [])
                 if value is not None]

    oos = _deployment_slice(equity_daily, start=fold_row["test_start"], end=deploy_end)
    common = dict(
        selection_id=f"{arm}-{fold_row.get('fold_id', fold_row['test_start'])}",
        theta_digest=theta_digest, alpha=alpha_id, symbol=symbol, arm=arm,
        selector_contract="STOCK_MODE4_PLUS_ADMISSION_V1",
        comparison_kind="D1_IS_TO_OOS",
        left_window=[train_start.isoformat(), cutoff.isoformat()],
        right_window=[fold_row["test_start"], deploy_end],
        horizon=None, raw_or_penalized="raw",
        fills=None, campaigns_closed=None, campaigns_open=None, exposure_days=None,
        regime_at_selection=regime_at_selection, regime_in_window=None,
        parameter_age=(pd.Timestamp(fold_row["test_start"]) - cutoff).total_seconds() / 86400.0,
        diagnostic_only=True,
    )
    rows = []
    is_valid = len(is_returns) >= 2
    oos_valid = oos["status"] == "OK"
    is_mean = (sum(is_returns) / len(is_returns)) if is_valid else None
    rows.append(_row(
        **common, observed_days=(len(is_returns), oos.get("days")),
        metric_name="mean_daily_return", metric_definition="mean of r_d=E_d/E_d-1-1 over the window",
        unit="fraction_per_day", support_count=len(is_returns) if is_valid else 0,
        left_value=is_mean, right_value=oos.get("mean_daily_return"),
        signed_delta=(None if is_mean is None or oos.get("mean_daily_return") is None
                     else oos["mean_daily_return"] - is_mean),
        validity_status="OK" if (is_valid and oos_valid) else "INSUFFICIENT_SUPPORT"))
    is_sharpe = sharpe(is_returns)
    oos_sharpe = sharpe(oos.get("returns") or [])
    rows.append(_row(
        **common, observed_days=(len(is_returns), oos.get("days")),
        metric_name="sharpe", metric_definition="annualised, ddof=1, sqrt(365)", unit="ratio",
        support_count=min(is_sharpe.get("n", 0), oos_sharpe.get("n", 0)),
        left_value=is_sharpe.get("value"), right_value=oos_sharpe.get("value"),
        signed_delta=(None if is_sharpe.get("value") is None or oos_sharpe.get("value") is None
                     else oos_sharpe["value"] - is_sharpe["value"]),
        validity_status="OK" if (is_sharpe["status"] == "OK" and oos_sharpe["status"] == "OK")
        else "INSUFFICIENT_SUPPORT_OR_ZERO_VARIANCE"))
    return rows


def compute_d2_rows(*, panel_b_rows: list, alpha_id: str, symbol: str, window_start: str,
                    account_capital: float, selector_contract: str = "RA06_PANEL_B_KEEP") -> list:
    """D2: ONE fixed theta (RA-06 Panel B's KEEP incumbent, selected once at
    window_start), successive real anchors H1<H2<...<Hn already committed in
    RA-06's evidence (`e_t_keep` at each origin) -- consecutive segment
    returns from the SAME continuous real account, never re-run."""
    ok_rows = sorted((r for r in panel_b_rows if r["status"] == "OK"),
                     key=lambda r: r["features"]["age_days"])
    if not ok_rows:
        return []
    theta_digest = digest(ok_rows[0]["keep_incumbent_params"])[:16]
    rows = []
    prev_equity, prev_anchor, prev_age = account_capital, window_start, 0.0
    for row in ok_rows:
        origin = row["origin"]
        e_t = row["g"]["e_t_keep"]
        age = row["features"]["age_days"]
        segment_return = (e_t / prev_equity) - 1.0 if prev_equity else None
        rows.append(_row(
            selection_id=f"RA06_KEEP-{origin}", theta_digest=theta_digest, alpha=alpha_id,
            symbol=symbol, arm="RA06_KEEP", selector_contract=selector_contract,
            comparison_kind="D2_PARAMETER_AGE",
            left_window=[prev_anchor, origin], right_window=[prev_anchor, origin],
            horizon=age - prev_age, observed_days=None,
            metric_name="segment_return", metric_definition="(E_anchor/E_prev_anchor)-1, fixed theta",
            unit="fraction", raw_or_penalized="raw",
            left_value=prev_equity, right_value=e_t, signed_delta=segment_return,
            validity_status="OK" if segment_return is not None else "CENSORED",
            fills=None, campaigns_closed=None, campaigns_open=None, exposure_days=None,
            support_count=1, regime_at_selection=None,
            regime_in_window=row["features"].get("regime_transitions_since_incumbent"),
            parameter_age=age, diagnostic_only=True,
        ))
        prev_equity, prev_anchor, prev_age = e_t, origin, age
    return rows


def compute_d3_rows(*, fold_selection_table: list, equity_daily: list, alpha_id: str,
                    symbol: str, arm: str, selector_contract: str = "STOCK_MODE4_PLUS_ADMISSION_V1"
                    ) -> list:
    """D3: adjacent OPERATIONAL folds -- real active params, real successive
    segments, but params/dates/durations may all differ between the two
    folds compared (guide 13.2's explicit caveat carried per row: this is
    NOT 'decay of the same theta')."""
    if len(fold_selection_table) < 2:
        return []
    rows = []
    for left, right in zip(fold_selection_table, fold_selection_table[1:]):
        left_slice = _deployment_slice(equity_daily, start=left["test_start"], end=right["test_start"])
        next_end = right.get("test_end") or right["test_start"]
        right_slice = _deployment_slice(equity_daily, start=right["test_start"], end=next_end)
        same_theta = left["selected_params"] == right["selected_params"]
        rows.append(_row(
            selection_id=f"{arm}-{left['test_start']}_vs_{right['test_start']}",
            theta_digest=f"{digest(left['selected_params'])[:8]}_vs_{digest(right['selected_params'])[:8]}",
            alpha=alpha_id, symbol=symbol, arm=arm, selector_contract=selector_contract,
            comparison_kind="D3_ADJACENT_OPERATIONAL_FOLDS",
            left_window=[left["test_start"], right["test_start"]],
            right_window=[right["test_start"], next_end],
            horizon=None, observed_days=(left_slice.get("days"), right_slice.get("days")),
            metric_name="mean_daily_return", metric_definition="mean of r_d over each fold's own segment",
            unit="fraction_per_day", raw_or_penalized="raw",
            left_value=left_slice.get("mean_daily_return"), right_value=right_slice.get("mean_daily_return"),
            signed_delta=(None if left_slice.get("mean_daily_return") is None
                         or right_slice.get("mean_daily_return") is None else
                         right_slice["mean_daily_return"] - left_slice["mean_daily_return"]),
            validity_status=("OK" if left_slice["status"] == "OK" and right_slice["status"] == "OK"
                            else "INSUFFICIENT_SUPPORT"),
            fills=None, campaigns_closed=None, campaigns_open=None, exposure_days=None,
            support_count=min(left_slice.get("days") or 0, right_slice.get("days") or 0),
            regime_at_selection=None, regime_in_window=None, parameter_age=None,
            diagnostic_only=not same_theta,
        ))
    return rows
