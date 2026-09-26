"""SD-03: continuous A/B/C account deployment (guide SD03.5).

A thin adapter over the ALREADY-QUALIFIED FP-02 deployment route
(``fp.evaluator.run_deployment`` + ``fp.locked_study.build_admitted_schedule``/
``build_run_deployment_schedule``, guide 5.2, the one qualified execution
route this lab has) -- never a new deployment engine. SD's own job is only
to reshape its real FINAL-fold selection records into the SAME
``{origin: {"source", "params"}}`` shape those functions already expect.

Unlike FP's own selections (where a FALLBACK_TO_A with no upstream params
records ``params=None``, a genuine gap), SD's minY rule ALWAYS has a real
winner -- worst case the anchor itself -- so every FINAL origin carries a
real params value here; there is no analogous "no selection at all" case.
"""
from __future__ import annotations

from ..fp import locked_study as ls
from ..fp.evaluator import run_deployment


class DeploymentSD03Error(ValueError):
    """A deployment-adapter step was internally inconsistent."""


def selections_by_origin_from_final_folds(fold_records: dict, *, arm: str) -> dict:
    """{origin: {"source", "params"}} for ONE arm, from real committed
    SD-03 FINAL fold records. Looks the winner's own params up from that
    arm's own scored table (never re-derives or guesses them)."""
    out = {}
    for origin, fold in sorted(fold_records.items()):
        if arm not in fold["arms"]:
            raise DeploymentSD03Error(f"{origin}: arm {arm!r} not present in fold record")
        sel = fold["arms"][arm]["selection"]
        scored_rows = [r for r in fold["arms"][arm]["scored"] if r["candidate_id"] == sel["winner_id"]]
        if not scored_rows:
            raise DeploymentSD03Error(f"{origin}/{arm}: winner {sel['winner_id']!r} not in its own "
                                      "scored table")
        out[origin] = {"source": arm, "params": scored_rows[0]["params"],
                       "reason": "ANCHOR" if sel["is_anchor"] else "SELECTED"}
    return out


def build_admitted_schedules(fold_records: dict, *, arms: tuple) -> dict:
    """{arm: admitted_schedule} -- reuses fp.locked_study.build_admitted_schedule
    verbatim, one call per arm."""
    return {arm: ls.build_admitted_schedule(selections_by_origin_from_final_folds(fold_records, arm=arm),
                                            arm=arm) for arm in arms}


def build_deployment_schedules(admitted_schedules: dict, *, frame_index) -> dict:
    """{arm: run_deployment-ready schedule} -- reuses
    fp.locked_study.build_run_deployment_schedule verbatim, one call per arm."""
    return {arm: ls.build_run_deployment_schedule(admitted, frame_index=frame_index)
           for arm, admitted in admitted_schedules.items()}


def run_continuous_accounts(cache, root, alpha_id: str, frame, deployment_schedules: dict, *,
                            economics: dict, producer_prefix: str, report_level: str = "score") -> dict:
    """One real fp.evaluator.run_deployment call per arm, same shared
    frame -- the SAME real continuous-account route FP-07 already used."""
    payloads = {}
    for arm, schedule in deployment_schedules.items():
        payload, event = run_deployment(cache, root, alpha_id, frame, schedule,
                                        ready_at=frame.index[0], report_level=report_level,
                                        economics=economics, producer=f"{producer_prefix}-{arm}")
        payloads[arm] = {"payload": payload, "cache_event": event["status"]}
    return payloads
