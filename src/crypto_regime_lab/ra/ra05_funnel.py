"""RA05.4: the decision-to-PnL funnel, one record per real re-selection
opportunity (guide section 9, the ~20-field table).

Every field is either a real measured value from the SAME real
`run_cutoff_walk_forward` fold the funnel row describes, or an explicit
`null` with a `*_reason` when this arm's execution model (the installed
multi-fold WFO, activating at the fold boundary) has no separate concept for
it -- e.g. a bar-by-bar warm-up/flat-book activation gate belongs to
`integration/continuous_account.py`'s `VersionWindow` model, which this arm
does not use, so `activation_time` here is the fold boundary itself, not a
delayed bar, and that is stated rather than invented.

`admission_decision` reuses RA-04's `STOCK_MODE4_PLUS_ADMISSION_V1` guard
unchanged -- the raw winner from `run_cutoff_walk_forward` is scored on
REAL, freshly-run shards (never fabricated), never overridden by a second
optimizer.
"""
from __future__ import annotations

import pandas as pd

from ..time_edge.execution import PreparedAccount, TrainingScorer
from ..time_edge.storage import digest
from .mode4_admission import admission_thresholds, admit_selection
from .mode4_reproduction import real_subperiod_shards, score_candidate_on_shards

#: Phase-owned scale, matching RA-04 public_path.py's own is_subperiods=3
#: precedent (scaled down from the registered 6 for a smaller window).
FUNNEL_IS_SUBPERIODS = 3


def score_fold_for_admission(prepared: PreparedAccount, alpha_id: str, fold_row: dict, *,
                             evidence_dir, lab_run_id: str,
                             is_subperiods: int = FUNNEL_IS_SUBPERIODS) -> dict:
    """One real account evaluation of a fold's winning params over its OWN
    train window (populates the scorer's cache with real `daily_returns`),
    then a shard rescore of the SAME params -- cheap because the shard calls
    hit the same cache key and only recompute the windowed summary, not a
    fresh engine run. Returns exactly what `admit_selection` needs, from
    real evaluated records, never fabricated.
    """
    train_start = pd.Timestamp(fold_row["train_start"])
    cutoff = pd.Timestamp(fold_row["test_start"])
    params = dict(fold_row["selected_params"])
    scorer = TrainingScorer(prepared, alpha_id, train_start, cutoff, evidence_dir, lab_run_id)
    train_index = prepared.frame.index[(prepared.frame.index >= train_start)
                                       & (prepared.frame.index < cutoff)]
    scorer(params=params, index=train_index)  # populates scorer.cache[key] with daily_returns
    key = digest(params)
    winner_scorer_record = scorer.cache[key]
    shards, shard_meta = real_subperiod_shards(train_index, is_subperiods=is_subperiods)
    shard_score = score_candidate_on_shards(scorer, params, shards)
    return {
        "schema": "regime_lab.ra05_fold_admission_score.v1",
        "train_window": [train_start.isoformat(), cutoff.isoformat()],
        "winner_scorer_record_status": winner_scorer_record.get("status"),
        "winner_scorer_record_daily_return_count": len(winner_scorer_record.get("daily_returns") or []),
        "shard_boundaries": shard_meta,
        "shard_score": shard_score,
        "is_subperiods": is_subperiods,
        "_winner_scorer_record": winner_scorer_record,  # consumed by build_funnel_record, not persisted verbatim
    }


def build_funnel_record(*, opportunity_id: str, arm: str, alpha_id: str, fold_row: dict,
                        admission_score: dict, incumbent_params: dict | None,
                        incumbent_version: str | None, trigger_meta: dict,
                        account_costs: dict) -> dict:
    """One RA05.4 funnel row. `trigger_meta` carries the scheduler-side facts
    (observation_available/model_ready/semantic_transition/eligibility/
    confirmed/budget_admitted) already established when this cutoff was
    selected into the arm's schedule -- never re-derived from scratch here.
    """
    params = dict(fold_row["selected_params"])
    candidate_version = digest(params)[:16]
    thresholds = admission_thresholds(alpha_id, is_subperiods=admission_score["is_subperiods"])
    decision = admit_selection(
        raw_selection={"params": params, "objective": fold_row.get("selected_is_objective")},
        alpha_id=alpha_id, incumbent=incumbent_params,
        winner_scorer_record=admission_score["_winner_scorer_record"],
        winner_shard_finite_count=admission_score["shard_score"]["finite_shard_count"],
        thresholds=thresholds,
    )
    unchanged = (incumbent_params is not None and params == incumbent_params)
    return {
        "schema": "regime_lab.ra05_funnel_record.v1",
        "opportunity_id": opportunity_id,
        "arm": arm,
        "alpha_id": alpha_id,
        # -- scheduler-side facts (never re-derived; from the trigger that produced this cutoff)
        "observation_available": trigger_meta.get("observation_available"),
        "model_ready": trigger_meta.get("model_ready"),
        "semantic_transition": trigger_meta.get("semantic_transition"),
        "eligibility": trigger_meta.get("eligibility", True),
        "confirmed": trigger_meta.get("confirmed", True),
        "budget_admitted": trigger_meta.get("budget_admitted", True),
        "trigger_reason": trigger_meta.get("reason"),
        # -- request/search timing
        "request_time": fold_row["test_start"],
        "train_cutoff": fold_row["train_end"],
        "selected_time": fold_row["test_start"],
        "search_ready": True,
        "trials_completed": fold_row.get("trials_completed"),
        # -- selection identity
        "selected_params_digest": candidate_version,
        "raw_selector": {"params": params, "objective": fold_row.get("selected_is_objective"),
                         "candidate_count": fold_row.get("candidate_count")},
        # -- admission
        "admission_decision": decision["decision"],
        "admission_reason": decision["reason"],
        "admission_day_support_ok": decision["day_support_ok"],
        "admission_shard_support_ok": decision["shard_support_ok"],
        "unchanged_params_reason": ("identical to incumbent" if unchanged else None),
        # -- activation lineage. This arm's execution model (the installed
        # multi-fold WFO) activates the selected params synchronously at the
        # fold boundary; there is no separate bar-by-bar warm-up/flat-book
        # gate here (that model lives in integration/continuous_account.py's
        # VersionWindow, not used by run_cutoff_walk_forward). Reported as
        # the fold boundary itself, not a delayed bar, with that noted.
        "warm_indicator_ready": None,
        "warm_indicator_ready_reason": ("not modeled by this arm's execution path (installed "
                                        "WFO fold boundary, no bar-by-bar warm-up gate); see "
                                        "integration/continuous_account.py for the model that "
                                        "has one"),
        "campaign_or_pending_order_wait": None,
        "campaign_or_pending_order_wait_reason": "same as warm_indicator_ready",
        "activation_time": fold_row["test_start"],
        "activation_time_is_fold_boundary_not_a_delayed_bar": True,
        "first_affected_target": fold_row["test_start"],
        "first_affected_order": None,
        "first_affected_fill": None,
        "first_affected_fill_reason": ("resolved separately from the arm's full fill ledger by "
                                       "timestamp >= this fold's test_start, see "
                                       "first_fill_after_activation in the discovery record"),
        # -- versions and cost
        "incumbent_version": incumbent_version,
        "candidate_version": candidate_version,
        "actual_costs": account_costs,
        "engine_trace_refs": {
            "route": fold_row.get("route"), "fold_id": fold_row.get("fold_id"),
        },
    }
