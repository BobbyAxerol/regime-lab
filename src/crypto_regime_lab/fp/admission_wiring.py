"""Guide FP01.2 finding 2: admission must decide BEFORE the continuous
deployment account consumes a fold's params.

The defect, verified on current source (guide FP01.2 row 2, evidence in
FP-01's ``finding_disposition.json``): ``ra05_discovery.run_one_arm`` ran the
full multi-fold account FIRST inside ``run_cutoff_walk_forward`` (every
``params_by_fold`` consumed at its fold boundary), then recorded admission
decisions as a descriptive funnel. The deep-dive (``scripts/
run_ra07_decay_deepdive.py``) ran the same route directly, with no admission
at all. So a KEEP_INCUMBENT verdict never stopped the account from switching
to the stock winner -- "admission" measured nothing about what was deployed.

The repair: ``run_cutoff_walk_forward`` accepts an optional ``admission_policy``
callable (default None = legacy unwired behavior, byte-identical, so published
runs are reproducible). When present it is consulted per fold BEFORE the
deployment account is built, and only ADMIT (or a previously-deployed
incumbent kept by KEEP_INCUMBENT) params reach the account. Everything --
raw stock selection (kept AS-IS), the per-fold decision, the consumed params
and the digests of both -- is recorded in ``admission_wiring`` lineage so the
FP verifier can re-check it without re-running the engine.
"""
from __future__ import annotations

import hashlib
import json


def supplied_digest(params: dict) -> str:
    """Stable short digest of one fold's supplied params, for lineage rows."""
    return hashlib.sha256(json.dumps(dict(params), sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


def deployment_params_from_decisions(*, params_by_fold: dict, decisions: dict) -> dict:
    """Split the account-consuming params from the raw stock record.

    ``decisions`` maps fold key -> ``{"decision", "reason", "kept"}`` where
    ``decision`` is one of ADMIT / KEEP_INCUMBENT / COMMON_FLAT_FALLBACK and
    ``kept`` (for KEEP_INCUMBENT) is the incumbent's params the caller supplies.
    Raw ``None`` params in a fold are never deployable: they become an explicit
    ``RAW_NONE`` drop in the lineage, never an implicit reuse of whatever came
    before.
    """
    deployment, lineage = {}, {}
    incumbent = None
    for key in sorted(params_by_fold, key=lambda k: int(k)):
        supplied = params_by_fold.get(key)
        decision = decisions.get(key) or {}
        verdict = decision.get("decision")
        row = {"fold": key, "decision": verdict,
               "reason": decision.get("reason"),
               "supplied_digest": (supplied_digest(supplied)
                                   if supplied is not None else None)}
        if supplied is None:
            row.update(consumed=None, consumed_digest=None,
                       blocked_reason="RAW_NONE: no stock selection recorded for this fold")
        elif verdict == "ADMIT":
            incumbent = dict(supplied)
            deployment[key] = dict(supplied)
            row.update(consumed=dict(supplied), consumed_digest=row["supplied_digest"],
                       blocked_reason=None)
        elif verdict == "KEEP_INCUMBENT":
            kept = decision.get("kept")
            if kept is None and incumbent is None:
                row.update(consumed=None, consumed_digest=None,
                        blocked_reason=("KEEP_WITHOUT_INCUMBENT: nothing deployed yet, "
                                        "flat until an ADMIT"))
            else:
                effective = dict(kept) if kept is not None else dict(incumbent)
                deployment[key] = effective
                incumbent = effective
                row.update(consumed=effective,
                           consumed_digest=supplied_digest(effective),
                           blocked_reason=None)
        elif verdict == "COMMON_FLAT_FALLBACK":
            row.update(consumed=None, consumed_digest=None,
                       blocked_reason=("COMMON_FLAT_FALLBACK: no admissible candidate, "
                                       "nothing deployed at this boundary"))
        else:
            raise ValueError(
                f"fold {key}: admission decision must be ADMIT/KEEP_INCUMBENT/"
                f"COMMON_FLAT_FALLBACK, got {verdict!r}")
        lineage[key] = row
    return {"deployment_params_by_fold": deployment, "lineage": lineage}


def no_admitted_deployment_payload(*, arm: str, cutoffs: list, lineage: dict,
                                   reason: str) -> dict:
    """Null-metrics account payload when admission admitted nothing anywhere.

    Not a flat account with invented PnL=0: the arm genuinely deployed nothing,
    so there is no equity series, no fills, and no first bar. Every metric that
    needs an account is None with this reason carried instead.
    """
    return {
        "status": "NO_ADMITTED_DEPLOYMENT",
        "arm": arm,
        "cutoffs": list(cutoffs),
        "reason": reason,
        "equity_first": None, "equity_last": None, "equity_daily": [],
        "bars": 0, "start": None, "end": None,
        "positions_last": None, "fills": [], "fill_count": 0,
        "fills_source": "none_no_deployment", "engine_report": {},
        "admission_lineage": lineage,
    }
