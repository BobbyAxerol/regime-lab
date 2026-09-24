"""FP03.4 -- forward comparison on calibration: does more search depth
actually improve FORWARD (post-origin) performance, or only IS?

Reuses fp.evaluator.evaluate_candidate (FP-02) for BOTH sides so the IS and
forward measurements share the identical metric computation
(time_edge.metrics.account_returns/describe, the SAME reducer pair every
other phase in this lab already uses) rather than trying to reproduce the
engine's own internal per-shard mean_is_sharpe objective, which is not
independently recomputable outside the search call that produced it.

Canonical sign (guide 10.2, matches fp/decay_bounds.py's D1):

    D = IS_metric - FORWARD_metric

Positive D is WORSE decay (IS looked better than what forward delivered).
Both windows use the SAME selected params and the SAME economic contract
(guide 5.1's IS/forward consistency requirement) -- this module never lets
the two sides silently diverge on fee/slippage/initial-capital.
"""
from __future__ import annotations


class ForwardComparisonError(ValueError):
    """Raised when the IS/forward windows or metrics are not comparable."""


def window_metrics(payload: dict, frame, *, initial_capital: float) -> dict:
    """time_edge.metrics.describe() over one evaluate_candidate payload's
    equity, sliced to frame's own span. Public: fp.selector_b (FP-05) reuses
    this verbatim for the SAME IS-window metric computation FP-04 already
    established, rather than a second implementation."""
    from ..time_edge.metrics import account_returns, describe

    audit = payload["selected_audit"]
    rows = account_returns(audit["equity"], frame.index, initial_equity=initial_capital,
                           start=frame.index[0], end=frame.index[-1] + (frame.index[1] - frame.index[0]))
    return describe(rows)


def candidate_decay(cache, root, alpha_id: str, is_frame, forward_frame, params: dict, *,
                    origin_cutoff, forward_end, economics: dict, producer: str,
                    report_level: str | None = "score") -> dict:
    """One real candidate's IS window (ending at origin_cutoff) vs its
    forward window (origin_cutoff to forward_end), same params, same
    economic contract -- both frozen selections: the candidate's params come
    from the search's own historical prefix, decided before this forward
    window's outcome is read (guide FP03.4's causality requirement).

    report_level defaults to "score": the IS window here is the SAME
    ~180-day scale that hit a real, RLIMIT_AS-caught MemoryError in the
    engine's default profile during checkpoint_search's own pilot (the
    audit-ledger accumulator FUP-04 already found and fixed on long
    frames). window_metrics only reads equity/index/fills from
    selected_audit, all of which FUP-04 measured unaffected by report_level
    -- this changes retention, never the metric values."""
    from . import evaluator as ev

    if is_frame.index[-1] >= forward_frame.index[0]:
        raise ForwardComparisonError("IS frame must end strictly before the forward frame starts")
    is_payload, is_event = ev.evaluate_candidate(cache, root, alpha_id, is_frame, params,
                                                 cutoff=origin_cutoff, producer=f"{producer}-is",
                                                 report_level=report_level)
    fwd_payload, fwd_event = ev.evaluate_candidate(cache, root, alpha_id, forward_frame, params,
                                                    cutoff=forward_end, producer=f"{producer}-fwd",
                                                    report_level=report_level)
    is_metrics = window_metrics(is_payload, is_frame, initial_capital=economics["initial_capital"])
    fwd_metrics = window_metrics(fwd_payload, forward_frame,
                                 initial_capital=economics["initial_capital"])
    # daily_sharpe is a TYPED dict ({"value", "status"} -- time_edge_contracts.
    # daily_sharpe: null value stays typed with a reason, e.g.
    # INSUFFICIENT_OBSERVATIONS/ZERO_VARIANCE, never silently coerced to 0).
    is_sharpe, fwd_sharpe = is_metrics["daily_sharpe"], fwd_metrics["daily_sharpe"]
    both_ok = is_sharpe["status"] == "OK" and fwd_sharpe["status"] == "OK"
    return {
        "params": params,
        "is_status": is_event["status"], "forward_status": fwd_event["status"],
        "is_metrics": is_metrics, "forward_metrics": fwd_metrics,
        "D_mean_daily_return": is_metrics["mean_daily_return"] - fwd_metrics["mean_daily_return"],
        "D_daily_sharpe": (is_sharpe["value"] - fwd_sharpe["value"]) if both_ok else None,
        "D_daily_sharpe_reason": (None if both_ok else
                                  f"is={is_sharpe['status']}, forward={fwd_sharpe['status']}"),
        "decay_sign_convention": "D = IS - FORWARD; positive D is WORSE decay (guide 10.2)",
    }


def checkpoint_forward_comparison(cache, root, alpha_id: str, frame, checkpoints: list[dict], *,
                                  origin_cutoff, economics: dict, producer: str,
                                  cumulative_wall_seconds_by_level: dict | None = None) -> list[dict]:
    """For each REACHED checkpoint's selected candidate: IS improvement vs
    the PRIOR reached checkpoint, forward utility, decay, and incremental
    cost (guide FP03.4's four required reports). 'Không chọn budget chỉ
    bằng max IS': this function reports forward+decay+cost explicitly
    alongside IS so a freeze decision cannot be made from IS alone."""
    import pandas as pd

    # Accept either a naive-string origin (localized here) or an already
    # tz-aware Timestamp (passed through): pd.Timestamp(x, tz="UTC") raises
    # on an already-aware x, which a caller holding one (e.g. reusing the
    # same cutoff it already localized for the search call) would hit.
    origin_ts = pd.Timestamp(origin_cutoff)
    origin_ts = origin_ts.tz_localize("UTC") if origin_ts.tzinfo is None else origin_ts
    is_frame = frame.loc[frame.index < origin_ts]
    forward_frame = frame.loc[frame.index >= origin_ts]
    if is_frame.empty or forward_frame.empty:
        raise ForwardComparisonError("origin_cutoff does not split the frame into two nonempty sides")
    forward_end = forward_frame.index[-1] + (forward_frame.index[1] - forward_frame.index[0])

    rows = []
    prior_is_objective = None
    prior_forward_mean_return = None
    for cp in checkpoints:
        if cp["status"] != "REACHED" or cp.get("selected") is None:
            rows.append({"level": cp["level"], "status": cp["status"]})
            continue
        selected = cp["selected"]
        decay = candidate_decay(cache, root, alpha_id, is_frame, forward_frame, selected["params"],
                                origin_cutoff=origin_ts, forward_end=forward_end,
                                economics=economics, producer=f"{producer}-cp{cp['level']}")
        is_improvement = (None if prior_is_objective is None
                          else selected["objective"] - prior_is_objective)
        forward_improvement = (None if prior_forward_mean_return is None
                               else decay["forward_metrics"]["mean_daily_return"]
                               - prior_forward_mean_return)
        incremental_wall = None
        if cumulative_wall_seconds_by_level and cp["level"] in cumulative_wall_seconds_by_level:
            prior_levels = [lv for lv in cumulative_wall_seconds_by_level if lv < cp["level"]]
            if prior_levels:
                incremental_wall = (cumulative_wall_seconds_by_level[cp["level"]]
                                    - cumulative_wall_seconds_by_level[max(prior_levels)])
        rows.append({
            "level": cp["level"], "status": "REACHED",
            "selected_trial_id": selected["trial_id"], "is_search_objective": selected["objective"],
            "decay": decay,
            "is_improvement_vs_prior_checkpoint": is_improvement,
            "forward_mean_daily_return_improvement_vs_prior_checkpoint": forward_improvement,
            "incremental_estimated_wall_seconds_vs_prior_checkpoint": incremental_wall,
        })
        prior_is_objective = selected["objective"]
        prior_forward_mean_return = decay["forward_metrics"]["mean_daily_return"]
    return rows
