"""RA05.5/RA05.6: run one arm's real schedule through the real installed
Mode 4 pipeline, build its funnel, and reduce all 4 arms to compact,
comparable outcomes (guide section 9).

Every arm calls the SAME `run_cutoff_walk_forward` -- same alpha, same real
frame, same trials/seed/route/fees -- differing ONLY in `schedule`
(guide 3.1: "Cung Mode 4, memory, execution; chi scheduling khac"). This is
what makes the four accounts comparable: one function, one execution path,
one varying input.
"""
from __future__ import annotations

import pandas as pd

from ..experiments.dynamic_fold_provider import (
    CutoffSchedule, ZeroSignalStrategy, engine_param_ranges, run_cutoff_walk_forward,
)
from ..time_edge.execution import PreparedAccount
from .ra05_funnel import build_funnel_record, score_fold_for_admission


def run_one_arm(alpha_id: str, frame: pd.DataFrame, schedule: CutoffSchedule, *,
                prepared: PreparedAccount, trials: int, seed: int, route: str,
                evidence_dir, lab_run_id: str, trigger_lookup: dict | None = None,
                engine_report_level: str | None = None) -> dict:
    """Run one arm's full schedule, then build one funnel record per fold
    using the SAME real per-fold results `run_cutoff_walk_forward` returned
    -- no separate/refabricated selection."""
    base = {"arm": schedule.arm, "schedule": schedule.as_record()}
    try:
        result = run_cutoff_walk_forward(
            alpha_id, frame, schedule, param_ranges=engine_param_ranges(alpha_id),
            strategy_class=ZeroSignalStrategy, optuna_trials=trials, seed=seed, route=route,
            engine_report_level=engine_report_level,
        )
    except Exception as exc:
        # run_cutoff_walk_forward's OWN try/except only wraps its route
        # execution, not its early precondition guards (empty cutoffs,
        # non-positive trials) -- those raise before that block. One arm's
        # structurally invalid schedule must be recorded, never abort the
        # whole 4-arm comparison (guide D07).
        return {**base, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not result.get("ok"):
        return {**base, "ok": False, "error": result.get("error")}

    fold_table = result.get("fold_selection_table") or []
    funnel = []
    incumbent_params = None
    incumbent_version = None
    for index, fold_row in enumerate(fold_table):
        # A UNIQUE cache directory per (arm, fold): TrainingScorer's candidate
        # cache is keyed only by digest(params), and two different folds --
        # even across different arms -- can legitimately select byte-identical
        # params at DIFFERENT cutoffs (the shared-initial selection is exactly
        # this, by design). Reusing one directory across folds then makes the
        # scorer's own identity check correctly refuse the stale-cutoff hit
        # (ContractError: partial candidate cache identity drift) -- not a bug
        # in the scorer, a namespace collision in this caller.
        fold_evidence_dir = (evidence_dir / schedule.arm / f"fold-{index}"
                             if evidence_dir is not None else None)
        if fold_evidence_dir is not None:
            fold_evidence_dir.mkdir(parents=True, exist_ok=True)
        admission_score = score_fold_for_admission(
            prepared, alpha_id, fold_row, evidence_dir=fold_evidence_dir, lab_run_id=lab_run_id)
        trigger_meta = (trigger_lookup or {}).get(fold_row["test_start"])
        if trigger_meta is None:
            trigger_meta = {
                "observation_available": True, "model_ready": True,
                "semantic_transition": False, "eligibility": True, "confirmed": True,
                "budget_admitted": True,
                "reason": "INITIAL" if index == 0 else "CALENDAR",
            }
        record = build_funnel_record(
            opportunity_id=f"{schedule.arm}-{index}", arm=schedule.arm, alpha_id=alpha_id,
            fold_row=fold_row, admission_score=admission_score,
            incumbent_params=incumbent_params, incumbent_version=incumbent_version,
            trigger_meta=trigger_meta, account_costs=result["requested"],
        )
        funnel.append(record)
        if record["admission_decision"] == "ADMIT":
            incumbent_params = fold_row["selected_params"]
            incumbent_version = record["candidate_version"]

    account = result.get("account") or {}
    fills = account.get("fills") or []
    resolve_first_fills(funnel, fills)
    return {**base, "ok": True, "run": result, "funnel": funnel,
           "final_incumbent_version": incumbent_version,
           "switches_admitted": sum(1 for r in funnel if r["admission_decision"] == "ADMIT"),
           "switches_kept_incumbent": sum(1 for r in funnel
                                          if r["admission_decision"] == "KEEP_INCUMBENT")}


def resolve_first_fills(funnel: list[dict], fills: list[dict]) -> None:
    """Fill in `first_affected_fill` from the arm's REAL fill ledger where a
    `timestamp` field is present; otherwise leave the explicit null+reason
    `build_funnel_record` already set (never guessed)."""
    if not fills or "timestamp" not in fills[0]:
        return
    timestamped = sorted(fills, key=lambda row: pd.Timestamp(row["timestamp"]))
    for row in funnel:
        activation = pd.Timestamp(row["activation_time"])
        later = [f for f in timestamped if pd.Timestamp(f["timestamp"]) >= activation]
        if later:
            row["first_affected_fill"] = later[0].get("order_id") or later[0].get("timestamp")
            row["first_affected_fill_timestamp"] = later[0]["timestamp"]
            row["first_affected_fill_reason"] = None


def action_divergence(arms: dict[str, dict]) -> dict:
    """Do the arms actually take different actions? Per-fold param digests
    compared pairwise -- the core RA-05 mechanism question, independent of
    PnL (guide: 'khong dung count>0 nhu bang chung edge')."""
    digests = {}
    for name, outcome in arms.items():
        if not outcome.get("ok"):
            digests[name] = None
            continue
        digests[name] = [row["selected_params_digest"] for row in outcome["funnel"]]
    pairs = {}
    names = [n for n in digests if digests[n] is not None]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = min(len(digests[a]), len(digests[b]))
            same = sum(1 for k in range(shared) if digests[a][k] == digests[b][k])
            pairs[f"{a}_vs_{b}"] = {
                "compared_folds": shared, "identical_selection_folds": same,
                "diverged_folds": shared - same,
                "diverged": same < shared,
            }
    return {"schema": "regime_lab.ra05_action_divergence.v1", "per_arm_digests": digests,
           "pairwise": pairs}


def descriptive_returns(arms: dict[str, dict]) -> dict:
    """Point estimates only -- no CI/bootstrap/claim gate here (guide 13.4/
    13.5 statistical machinery is RA-07's; RA05.7 permits point estimate +
    DESCRIPTIVE uncertainty only, and this pilot's short window does not
    clear the registered >=365-day confirmatory floor (RA01.4 migration
    table) so nothing here is offered as a claim)."""
    out = {}
    for name, outcome in arms.items():
        if not outcome.get("ok"):
            out[name] = {"status": "NOT_EVALUABLE", "reason": outcome.get("error")}
            continue
        account = outcome["run"]["account"]
        equity_first = account.get("equity_first")
        equity_last = account.get("equity_last")
        total_return = (None if not equity_first else (equity_last / equity_first) - 1.0)
        out[name] = {
            "status": "OK", "equity_first": equity_first, "equity_last": equity_last,
            "total_return": total_return, "fill_count": account.get("fill_count"),
            "folds": len(outcome["funnel"]), "switches_admitted": outcome["switches_admitted"],
            "switches_kept_incumbent": outcome["switches_kept_incumbent"],
        }
    return {"schema": "regime_lab.ra05_descriptive_returns.v1", "by_arm": out,
           "note": ("point estimates only; this pilot's window does not clear the registered "
                    ">=365-day confirmatory floor, so no CI/claim-gate verdict is offered here "
                    "(RA-07 scope)")}
