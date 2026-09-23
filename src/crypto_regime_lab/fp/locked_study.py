"""FP-07 -- Locked A/B/C study (guide section 19).

Guide 19's own required shape, each piece mapped onto what FP-04/05/06
already built (never a second search, a second selector, or a second
chronology guard):

  * "Search chung tại mỗi cutoff" / "A/B/C chọn trên cùng pool" -- FP-04's
    12 origins already ran the ONE shared search at each cutoff
    (.cache/fp04_search_raw/origin_<date>.json's real wf_result); all three
    arms select from that SAME frozen pool, never a fresh one.
  * Arm A (stock/installed Mode 4): wf_result["selected_params"] -- the
    engine's own is_only_robust selection, already computed, zero new cost.
  * Arm B: fp.selector_b's walk-forward fit, applied at EVERY origin (not
    just the 8 OOF validation folds) -- trains on whichever EARLIER origins
    are matured as of THIS origin's own decision time
    (fp.forward_ledger.training_view, the same guard everywhere else in
    this study), scores THIS origin's own region pool, ranks by guide 8.6's
    eligibility order. Too little prior history (guide 8.7's floors) or no
    eligible candidate -> NO new admission at this origin: the continuous
    account keeps whatever version is already active (or, before Arm B's
    very first real admission, stays FLAT_UNTIL_READY -- the engine's own
    "requested_at_bar > 0" contract, verified in
    integration/continuous_account.py's `_one_sweep` comment "A02"). This is
    a real, disclosed "whole-policy fallback period" (guide 19 item 8): a
    genuine measured cold-start/no-signal cost of running Arm B's OWN
    policy, never silently patched by borrowing Arm A's params for that
    origin (the label "FALLBACK_TO_A" names WHY there is no B-specific
    pick -- Arm A's installed logic is the only thing that ran that quarter
    -- not that Arm A's params were copied into Arm B's schedule).
  * Arm C: fp.selector_c, same mechanism and the same "no new admission,
    not a borrowed value" semantics; an OOD candidate falls back to Arm B's
    own (context-free) prediction (guide 18 task 6); if B itself had no new
    admission at an origin, C has none there either.

Admission-before-deployment (guide 19 item 4) reuses fp.admission_wiring
verbatim; the continuous account itself is one real
fp.evaluator.run_deployment call per arm, spanning from the first origin
to the last origin's own matured forward horizon -- never re-optimized,
never re-run mid-study on a favorable prefix (guide 19 items 9-10).
"""
from __future__ import annotations

import json
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent.parent.parent
RAW_SEARCH_CACHE = LAB / ".cache" / "fp04_search_raw"

ARMS = ("A_STOCK_CAL", "B_FP_PERSISTENCE", "C_FP_CONTEXT")


class LockedStudyError(ValueError):
    """A locked-study construction step was internally inconsistent."""


# ---------------------------------------------------------------------------
# The shared, already-frozen candidate pool (guide 19: 'cùng pool')
# ---------------------------------------------------------------------------

def load_origin_wf_result(origin_cutoff: str) -> dict:
    """The REAL, already-computed FP-04 search result for this origin --
    never re-run. Raises LockedStudyError if the cache is missing (FP-07
    must never silently fall back to a fresh search)."""
    path = RAW_SEARCH_CACHE / f"origin_{origin_cutoff}.json"
    if not path.is_file():
        raise LockedStudyError(f"no cached FP-04 search result for origin {origin_cutoff} at "
                               f"{path} -- FP-07 reuses FP-04's pool, it never searches fresh")
    raw = json.loads(path.read_text())
    if not raw.get("wf_result", {}).get("ok"):
        raise LockedStudyError(f"origin {origin_cutoff}'s cached search was not wf_ok")
    return raw["wf_result"]


def arm_a_selection(wf_result: dict) -> dict:
    """Arm A: the engine's OWN is_only_robust selection (guide's
    registered 'installed Mode 4 selection') -- not a lab-side proxy."""
    params = wf_result.get("selected_params")
    if params is None:
        raise LockedStudyError("wf_result has no selected_params for Arm A")
    return params


# ---------------------------------------------------------------------------
# Arm B / Arm C walk-forward selection at ONE origin (guide 8.6's ordered
# eligibility, reusing fp.selector_b / fp.selector_c verbatim)
# ---------------------------------------------------------------------------

def walk_forward_b_selection(b_rows: list[dict], regions_by_origin: dict, *, origin_cutoff: str,
                             alpha: float, utility_floor: float, support_floor: int) -> dict:
    """Fits B on whichever EARLIER origins are matured as of this origin's
    OWN decision time, scores this origin's OWN region pool, ranks by
    guide 8.6. Admits NO new params (source=FALLBACK_TO_A, params=None) when
    there is no usable training data or no eligible candidate -- the account
    keeps its currently active version (or stays flat pre-first-admission);
    it never borrows Arm A's own params for that origin. A real, disclosed
    fallback period, never hidden."""
    from . import selector_b as sb
    from .forward_ledger import training_view

    origin_time = next((r["origin_time"] for r in b_rows if r["origin_cutoff"] == origin_cutoff),
                       None)
    if origin_time is None:
        raise LockedStudyError(f"no B rows carry origin_cutoff={origin_cutoff}")
    train_rows = training_view(b_rows, decision_time=origin_time)["usable"]
    val_rows = [r for r in b_rows if r["origin_cutoff"] == origin_cutoff and r["label"] is not None]
    if not train_rows:
        return {"source": "FALLBACK_TO_A", "params": None,
               "reason": "no matured training rows available before this origin's own decision "
               "time (guide 8.7's fit floor not met yet)"}
    X_tr, y_tr, w_tr, _n, _k, _e = sb.build_feature_matrix(train_rows)
    if len(X_tr) == 0:
        return {"source": "FALLBACK_TO_A", "params": None,
               "reason": "training rows exist but none survived feature construction"}
    model = sb.fit_ridge(X_tr, y_tr, w_tr, alpha)
    X_va, _y_va, _w_va, _n2, kept_va, _e2 = sb.build_feature_matrix(val_rows)
    if len(X_va) == 0:
        return {"source": "FALLBACK_TO_A", "params": None,
               "reason": "this origin's own candidate pool produced no scorable rows"}
    preds = sb.predict_ridge(model, X_va)
    scored = [{"record_id": row["record_id"], "params": row["params"],
              "region_support_within_origin": row["region_support_within_origin"],
              "predicted_forward_utility": float(pred)}
             for row, pred in zip(kept_va, preds)]
    eligible = sb.eligible_candidates(scored, utility_floor=utility_floor, support_floor=support_floor)
    # decay-risk score is not computed here (no OOF residuals at every origin
    # in this per-cutoff loop) -- ranking uses predicted utility alone,
    # eligibility already screens for the utility/support floors guide 8.6
    # requires BEFORE decay is even assessed
    passing = [r for r in eligible if r["eligible"]]
    if not passing:
        return {"source": "FALLBACK_TO_A", "params": None, "model_alpha": alpha,
               "reason": "no candidate cleared the utility/support floor at this origin",
               "n_scored": len(scored)}
    winner = max(passing, key=lambda r: r["predicted_forward_utility"])
    return {"source": "B_SELECTED", "params": winner["params"], "model_alpha": alpha,
           "record_id": winner["record_id"],
           "predicted_forward_utility": winner["predicted_forward_utility"],
           "n_scored": len(scored), "n_eligible": len(passing)}


def walk_forward_c_selection(c_rows: list[dict], *, origin_cutoff: str, alpha: float,
                             utility_floor: float, support_floor: int,
                             b_result: dict) -> dict:
    """Same mechanism through Selector C; if B itself had no new admission
    at this origin, C admits nothing there either (guide 9.1: same fallback
    semantics as B -- no borrowed params, just no new switch request)."""
    from . import selector_c as sc
    from .forward_ledger import training_view

    from . import selector_b as sb

    if b_result["source"] == "FALLBACK_TO_A":
        return {"source": "FALLBACK_TO_A", "params": None,
               "reason": f"Arm B itself fell back to A at this origin ({b_result['reason']})"}
    origin_time = next((r["origin_time"] for r in c_rows if r["origin_cutoff"] == origin_cutoff),
                       None)
    if origin_time is None:
        raise LockedStudyError(f"no C rows carry origin_cutoff={origin_cutoff}")
    train_rows = training_view(c_rows, decision_time=origin_time)["usable"]
    val_rows = [r for r in c_rows if r["origin_cutoff"] == origin_cutoff and r["label"] is not None]
    X_tr, y_tr, w_tr, _n, kept_tr, _e = sc.build_c_feature_matrix(train_rows)
    if len(X_tr) == 0:
        return {"source": "FALLBACK_TO_B", "params": b_result["params"],
               "reason": "no C-scorable training rows -- falls back to B's own selection"}
    c_model = sc.fit_ridge_c(X_tr, y_tr, w_tr, alpha)
    bounds = sc.context_support_bounds(kept_tr)
    # C rows already carry every one of B's own feature names verbatim
    # (guide 9.1/FP06-T06: base features preserved) -- the SAME training
    # rows build B's OOD-fallback model directly, no separate row set.
    Xb, yb, wb, _nb, _kb, _eb = sb.build_feature_matrix(train_rows)
    b_model = sb.fit_ridge(Xb, yb, wb, alpha) if len(Xb) else None
    scored = []
    for row in val_rows:
        if any(row.get(n) is None for n in sc.c_feature_names()):
            continue
        if b_model is not None:
            result = sc.predict_c_or_fallback(c_model=c_model, b_model=b_model, row=row, bounds=bounds)
        else:
            result = {"predicted_forward_utility": None, "source": "FALLBACK_TO_B",
                     "fallback_reasons": ["no B model available for OOD fallback"]}
        scored.append({"record_id": row["record_id"], "params": row["params"],
                       "region_support_within_origin": row["region_support_within_origin"],
                       "predicted_forward_utility": result["predicted_forward_utility"],
                       "source": result["source"]})
    scoreable = [r for r in scored if r["predicted_forward_utility"] is not None]
    eligible = sb.eligible_candidates(scoreable, utility_floor=utility_floor,
                                      support_floor=support_floor)
    passing = [r for r in eligible if r["eligible"]]
    if not passing:
        return {"source": "FALLBACK_TO_B", "params": b_result["params"],
               "reason": "no C-scored candidate cleared the utility/support floor",
               "n_scored": len(scored)}
    winner = max(passing, key=lambda r: r["predicted_forward_utility"])
    return {"source": winner["source"], "params": winner["params"], "model_alpha": alpha,
           "record_id": winner["record_id"],
           "predicted_forward_utility": winner["predicted_forward_utility"],
           "n_scored": len(scored), "n_eligible": len(passing)}


# ---------------------------------------------------------------------------
# Schedule construction (guide 19 item 4: admission before deployment)
# ---------------------------------------------------------------------------

def build_admitted_schedule(selections_by_origin: dict, *, arm: str) -> dict:
    """Runs every origin's raw selection through fp.admission_wiring
    (the SAME function FP-01 repaired) -- guide 19 item 4. A fallback
    selection (params=None, e.g. two consecutive FALLBACK_TO_A calls with
    no upstream params) is recorded as a genuine gap, never silently
    dropped or invented."""
    from . import admission_wiring as aw

    params_by_fold, decisions = {}, {}
    for i, (origin_cutoff, result) in enumerate(sorted(selections_by_origin.items())):
        key = str(i)
        params_by_fold[key] = result.get("params")
        decisions[key] = {"decision": "ADMIT" if result.get("params") is not None
                          else "COMMON_FLAT_FALLBACK",
                          "reason": f"{arm}@{origin_cutoff}: {result.get('source')} "
                          f"-- {result.get('reason', 'selected')}", "kept": None}
    out = aw.deployment_params_from_decisions(params_by_fold=params_by_fold, decisions=decisions)
    return {"arm": arm, "origins_ordered": sorted(selections_by_origin),
           "deployment_params_by_fold": out["deployment_params_by_fold"], "lineage": out["lineage"]}


def build_run_deployment_schedule(admitted: dict, *, frame_index) -> list[dict]:
    """Maps each admitted origin to its real bar index in the shared
    continuous frame -- fp.evaluator.run_deployment's own contract."""
    schedule = []
    for i, origin_cutoff in enumerate(admitted["origins_ordered"]):
        key = str(i)
        params = admitted["deployment_params_by_fold"].get(key)
        if params is None:
            continue   # a genuine COMMON_FLAT_FALLBACK: no activation request at this origin
        import pandas as pd

        origin_ts = pd.Timestamp(origin_cutoff, tz="UTC")
        try:
            bar = frame_index.get_loc(origin_ts)
        except KeyError as exc:
            raise LockedStudyError(f"origin {origin_cutoff} is not an exact bar in the "
                                   "continuous frame's index") from exc
        schedule.append({"activation_id": f"{admitted['arm']}@{origin_cutoff}", "params": params,
                         "requested_at_bar": int(bar)})
    if not schedule:
        raise LockedStudyError(f"{admitted['arm']}: every origin fell back with no admitted "
                               "params -- nothing to deploy")
    return sorted(schedule, key=lambda r: r["requested_at_bar"])


# ---------------------------------------------------------------------------
# Statistical analysis (guide 19's required 'canonical daily returns',
# 'D1 table', 'paired contrasts') -- reuses time_edge.metrics.account_returns
# and experiments.time_edge_contracts.paired_difference/block_mean/
# holm_adjust VERBATIM, the SAME registered inference machinery RA-07/RF-05
# already built and this lab's history already trusts, never a second
# statistical implementation.
# ---------------------------------------------------------------------------

def account_daily_returns(payload: dict, frame, *, initial_capital: float) -> list:
    """Canonical daily returns for one arm's continuous account -- the raw
    (date, return) pairs paired_difference needs, not just describe()'s
    aggregate scalars."""
    from ..time_edge.metrics import account_returns

    audit = payload["selected_audit"]
    return account_returns(audit["equity"], frame.index, initial_equity=initial_capital,
                           start=frame.index[0],
                           end=frame.index[-1] + (frame.index[1] - frame.index[0]))


def paired_contrast(daily_left: list, daily_right: list, *, label: str, delta: float,
                    allow_partial: bool = True) -> dict:
    """left - right (guide's registered sign: e.g. C - B for the primary
    contrast), block-bootstrapped exactly like RA-07/RF-05's own registered
    paired inference (28-day blocks, the SAME time_edge.inference.block_mean
    call, never a bespoke t-test)."""
    from ..experiments.time_edge_contracts import ContractError, paired_difference
    from ..time_edge.inference import block_mean

    try:
        paired = paired_difference(daily_left, daily_right, allow_partial=allow_partial)
    except ContractError as exc:
        return {"label": label, "status": "NOT_EVALUABLE", "reason": str(exc)}
    if len(paired["values"]) < 28:
        return {"label": label, "status": "INCONCLUSIVE_SUPPORT",
               "reason": f"only {len(paired['values'])} common days, need >= 28 for one "
               "bootstrap block", "n_common_days": len(paired["values"]),
               "unmatched_dates": paired["unmatched_dates"]}
    stats = block_mean(paired["values"], delta=delta)
    return {"label": label, "status": "ESTIMATED", **stats,
           "n_common_days": len(paired["values"]), "unmatched_dates": paired["unmatched_dates"],
           "partial": paired["partial"]}


def d1_decay(is_mean: float, forward_mean: float) -> dict:
    """Guide 8.5/FP-01's repaired D1 convention, unchanged: D = IS - forward,
    positive is WORSE decay -- the SAME sign FP-03/04 already used."""
    return {"D_mean_daily_return": is_mean - forward_mean,
           "convention": "D = IS - forward; positive = worse decay (guide 8.5, FP-01 repaired)"}
