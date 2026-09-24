"""FP-02: the common evaluator (guide section 14).

Maps onto the ONE qualified execution route this lab has
(``ra/route_qualification.py``: the native-event-strategy route via
``integration/event_account.py::run_event_account`` -- no separate fast/
vectorized route exists here, and the guide's own exit clause covers that
case: use the qualified route within budget rather than inventing one).
``report_level`` (FUP-04, already measured equity-exact across levels) is
this route's own audit/score distinction: ``None`` is the audit-grade,
full-retention run; ``"score"`` is the fast/compact one this evaluator
intends to use at scale once route_parity (below) re-proves it on the
candidate actually being evaluated, not just cited from FUP-04's frame.

Two account types (guide section 5), same underlying call, different usage:

* ``evaluate_candidate`` -- standardized candidate cohort (5.1): one
  parameter point, ``schedule=[]``, always the SAME initial capital ("fresh"
  state). Cached: the same candidate is reusable across search/forward-label/
  report without recomputation (FP02-G-CACHE).
* ``run_deployment`` -- continuous deployment cohort (5.2): one or more
  ``VersionWindow`` requests in ``schedule``, carrying the account through
  chronology. ``EventAccountStrategy`` itself enforces the pending/warm
  activation delay (guide 9.5); this module never re-derives it, only reads
  ``diagnostics["switches"]`` + ``version_by_bar`` back for lineage.

Every cached payload excludes provenance (wall-clock, producer id) from its
CONTENT so two runs of the same semantics compare byte-for-byte (the
``causality`` block is the one exception: it is semantic, not provenance --
FP02-G-LATENCY needs it on every payload, hit or miss).
"""
from __future__ import annotations

from . import retention_fp02
from .lineage import build_lineage

CANDIDATE_KIND = "fp_candidate"
DEPLOYMENT_KIND = "fp_deployment"
FACET_SCHEMA = "regime_lab.fp02_evaluator_facets.v1"
ROUTE = "integration.event_account.run_event_account"


class EvaluatorError(ValueError):
    """A facet or record was internally inconsistent -- never silently patched."""


def default_economics() -> dict:
    """Guide 3.1's frozen contract, read from the SAME constants
    event_account.py itself defaults to (never a second hardcoded copy)."""
    from ..quantbt_bridge.routes import ONE_WAY_TAKER_FEE, SLIPPAGE_BPS

    return {"initial_capital": 20000.0, "one_way_fee": float(ONE_WAY_TAKER_FEE),
            "slippage_bps": float(SLIPPAGE_BPS), "use_funding": False}


def _frame_facet(frame) -> dict:
    from ..ra.cache_experiments import frame_digest

    return {"market_digest": frame_digest(frame), "rows": int(len(frame)),
            "first": str(frame.index[0]), "last": str(frame.index[-1])}


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def candidate_facets(root, alpha_id: str, frame, params: dict, *, cutoff,
                     report_level: str | None, economics: dict) -> dict:
    from ..time_edge.compute_cache import code_contract, engine_contract

    return {
        "schema": FACET_SCHEMA, "kind": "candidate", "route": ROUTE,
        "market": _frame_facet(frame), "alpha": alpha_id,
        "params": {k: params[k] for k in sorted(params)},
        "cutoff": _iso(cutoff), "economics": economics,
        "initial_state": {"mode": "fresh", "equity": economics["initial_capital"]},
        "report_level": report_level,
        "contract": code_contract(root, CANDIDATE_KIND),
        "engine_build": engine_contract(root),
    }


def deployment_facets(root, alpha_id: str, frame, schedule_requests: list[dict], *,
                      report_level: str | None, economics: dict) -> dict:
    from ..time_edge.compute_cache import code_contract, engine_contract

    ordered = sorted(schedule_requests, key=lambda r: r["requested_at_bar"])
    return {
        "schema": FACET_SCHEMA, "kind": "deployment", "route": ROUTE,
        "market": _frame_facet(frame), "alpha": alpha_id,
        "schedule": [{"activation_id": r["activation_id"],
                     "params": {k: r["params"][k] for k in sorted(r["params"])},
                     "requested_at_bar": int(r["requested_at_bar"])} for r in ordered],
        "economics": economics,
        "initial_state": {"mode": "fresh", "equity": economics["initial_capital"]},
        "report_level": report_level,
        "contract": code_contract(root, DEPLOYMENT_KIND),
        "engine_build": engine_contract(root),
    }


def _version_window(request: dict):
    from ..integration.continuous_account import VersionWindow

    return VersionWindow(parameter_version=request["activation_id"],
                         params=dict(request["params"]),
                         requested_at_bar=int(request["requested_at_bar"]),
                         activation_id=request["activation_id"])


def _record_of(run) -> dict:
    return {"status": run.status, "equity": run.equity, "positions": run.positions,
            "fills": run.fills, "version_by_bar": run.version_by_bar,
            "entries": run.entries, "engine_fill_count": run.engine_fill_count,
            "unmapped_intents": run.unmapped_intents, "rejections": run.rejections,
            "commands": run.commands, "order_events": run.order_events,
            "order_ids_by_version": run.order_ids_by_version,
            "diagnostics": run.diagnostics}


def _run_event_account(alpha_id, frame, *, initial, schedule, report_level, economics):
    from ..integration.event_account import run_event_account

    return run_event_account(
        alpha_id, frame, initial=initial, schedule=schedule,
        initial_capital=economics["initial_capital"],
        one_way_fee=economics["one_way_fee"], slippage_bps=economics["slippage_bps"],
        report_level=report_level)


def evaluate_candidate(cache, root, alpha_id: str, frame, params: dict, *, cutoff,
                       report_level: str | None = None, economics: dict | None = None,
                       producer: str) -> tuple[dict, dict]:
    """Standardized candidate (guide 5.1). Returns (payload, cache_event)."""
    from .instrumentation import Stage
    from ..ra.phase_common import utcnow

    economics = economics or default_economics()
    facets = candidate_facets(root, alpha_id, frame, params, cutoff=cutoff,
                              report_level=report_level, economics=economics)

    def compute():
        perf: dict = {}
        initial = _version_window({"activation_id": "fp02-candidate", "params": params,
                                   "requested_at_bar": 0})
        with Stage("evaluate_candidate", perf):
            run = _run_event_account(alpha_id, frame, initial=initial, schedule=[],
                                     report_level=report_level, economics=economics)
        record = _record_of(run)
        ready = _iso(cutoff)
        return {
            "selected_audit": retention_fp02.to_selected_audit(record, index=frame.index),
            "trial_scalar": retention_fp02.to_trial_scalar(record),
            "causality": {"physical_compute_at": utcnow(), "simulated_cutoff": ready,
                         "simulated_ready_at": ready},
            "instrumentation": perf["evaluate_candidate"],
        }

    return cache.get_or_compute_singleflight(CANDIDATE_KIND, facets, compute, producer=producer)


def run_deployment(cache, root, alpha_id: str, frame, schedule_requests: list[dict], *,
                   ready_at, report_level: str | None = None, economics: dict | None = None,
                   producer: str) -> tuple[dict, dict]:
    """Continuous deployment (guide 5.2). ``schedule_requests[0]`` is the
    initial version (``requested_at_bar`` should be 0 or negative); any
    further entries are switch requests. Returns (payload, cache_event)."""
    from .instrumentation import Stage
    from ..ra.phase_common import utcnow

    if not schedule_requests:
        raise EvaluatorError("run_deployment needs at least an initial version")
    economics = economics or default_economics()
    ordered = sorted(schedule_requests, key=lambda r: r["requested_at_bar"])
    facets = deployment_facets(root, alpha_id, frame, schedule_requests,
                               report_level=report_level, economics=economics)

    def compute():
        perf: dict = {}
        initial = _version_window(ordered[0])
        schedule = [_version_window(r) for r in ordered[1:]]
        with Stage("run_deployment", perf):
            run = _run_event_account(alpha_id, frame, initial=initial, schedule=schedule,
                                     report_level=report_level, economics=economics)
        record = _record_of(run)
        lineage = build_lineage(
            switches=record["diagnostics"].get("switches", []),
            version_by_bar=record["version_by_bar"], fills=record["fills"],
            initial_version=ordered[0]["activation_id"])
        ready = _iso(ready_at)
        return {
            "selected_audit": retention_fp02.to_selected_audit(record, index=frame.index),
            "trial_scalar": retention_fp02.to_trial_scalar(record),
            "lineage": lineage,
            "causality": {"physical_compute_at": utcnow(), "simulated_cutoff": ready,
                         "simulated_ready_at": ready},
            "instrumentation": perf["run_deployment"],
        }

    return cache.get_or_compute_singleflight(DEPLOYMENT_KIND, facets, compute, producer=producer)


def route_parity(root, alpha_id: str, frame, params: dict, *,
                 economics: dict | None = None) -> dict:
    """FP02-G-PARITY's required actual run: the SAME candidate through the
    audit route (report_level=None) and the score/fast route this evaluator
    intends to use, compared on equity/fills/entries -- re-proving FUP-04's
    finding fresh, on FP-02's own evaluator rather than citing it as a
    substitute (guide 23.3: a claim needs its own evidence)."""
    import numpy as np

    from ..integration.continuous_account import VersionWindow
    from .instrumentation import Stage

    economics = economics or default_economics()
    perf: dict = {}
    runs = {}
    for level, tag in ((None, "audit"), ("score", "fast")):
        initial = VersionWindow(parameter_version="fp02-parity", params=dict(params),
                                requested_at_bar=0, activation_id="fp02-parity")
        with Stage(f"route_parity_{tag}", perf):
            runs[tag] = _run_event_account(alpha_id, frame, initial=initial, schedule=[],
                                           report_level=level, economics=economics)
    audit_equity = np.asarray(runs["audit"].equity, dtype=float)
    fast_equity = np.asarray(runs["fast"].equity, dtype=float)
    equity_exact = bool(np.array_equal(audit_equity, fast_equity))
    return {
        "schema": "regime_lab.fp02_route_parity.v1", "alpha_id": alpha_id,
        "audit": {"report_level": None, "entries": runs["audit"].entries,
                  "fill_count": len(runs["audit"].fills),
                  "engine_fill_count": runs["audit"].engine_fill_count,
                  "resolved_report_level": runs["audit"].diagnostics.get("resolved_report_level")},
        "fast": {"report_level": "score", "entries": runs["fast"].entries,
                 "fill_count": len(runs["fast"].fills),
                 "engine_fill_count": runs["fast"].engine_fill_count,
                 "resolved_report_level": runs["fast"].diagnostics.get("resolved_report_level")},
        "equity_exact_equal": equity_exact,
        "max_abs_equity_diff": float(np.max(np.abs(audit_equity - fast_equity))),
        "entries_match": runs["audit"].entries == runs["fast"].entries,
        "fill_count_match": len(runs["audit"].fills) == len(runs["fast"].fills),
        "instrumentation": perf,
        "status": "PASS" if (equity_exact and runs["audit"].entries == runs["fast"].entries
                             and len(runs["audit"].fills) == len(runs["fast"].fills)) else "FAIL",
        "precedent": ("FUP-04 evidence/corrective_mode4_v3/FUP-04/report_level_memory_repair.json "
                     "s7_parity_engine_default_vs_score: max_abs_equity_diff 0.0, exact_equal true, "
                     "strategy_fills 81==81, entries 41==41 on a different (RA-05 M4_CAL) window -- "
                     "this run is FP-02's OWN evidence, not a substitute for that one"),
    }
