"""RA-02 phase experiments shared by the tests and the phase runner.

One implementation of: the deterministic 1m market frame, the deployment
facets (semantic key), a real small QuantBT computation, the cross-run reuse
experiment (C01) and the study resume-parity experiment (C08). The tests and
`scripts/run_ra02.py` import the same functions so the artifact's receipts
and the suite's assertions cannot drift apart.

Heavy imports (numpy, pandas, the engine bridge) stay inside the functions so
this module is importable cheaply.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .cache_semantics import assert_causal_hit
from .study_replay import StudyInterrupted, run_study, run_study_dropping_tells

ECONOMICS = {"fee": 0.0004, "slippage": 1.0,
             "contract": "event_lifecycle_v3_next_open"}
DEFAULT_FRAME_ROWS = 2880
DEFAULT_SEED = 20260911
SEARCH_SPACE = {"x": ("float", (0.0, 1.0))}


def market_frame(n=DEFAULT_FRAME_ROWS, seed=7):
    """A valid, deterministic 1m OHLCV frame (validate_market-clean)."""
    import numpy as np
    import pandas as pd

    index = pd.date_range("2020-01-01", periods=n, freq="min", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.05, n))
    return pd.DataFrame({"open": close, "high": close + 0.1,
                         "low": close - 0.1, "close": close,
                         "volume": 1.0}, index=index)


def selection(cutoff_iso):
    """A registered A-SC selection whose decision is ready at its cutoff."""
    return [{"selection_id": "ra02-s1",
             "params": {"AP": 5, "coeff": 2, "novolumedata": False,
                        "src_col": "close", "alpha.condition_threshold": 50},
             "cutoff": cutoff_iso, "ready_at": cutoff_iso}]


def frame_digest(frame) -> str:
    from ..time_edge.storage import digest

    return digest(frame.to_csv(index=True, lineterminator="\n"))


def deployment_facets(frame, cutoff, *, root=None, initial_state=None,
                      economics=None) -> dict:
    """The deployment semantic key: market content, coverage, clock, alpha
    source contract, execution semantics, engine build and initial state."""
    from ..time_edge.compute_cache import code_contract, engine_contract

    from .phase_common import LAB

    root = Path(root) if root is not None else LAB
    return {
        "schema": "ra02_deployment_v1",
        "market": frame_digest(frame),
        "coverage": {"rows": int(len(frame)),
                     "first": str(frame.index[0]),
                     "last": str(frame.index[-1])},
        "alpha": "A-SC",
        "arm": "deployment",
        "cutoff": cutoff.isoformat(),
        "account_start": frame.index[len(frame) // 2].isoformat(),
        "economics": economics or ECONOMICS,
        "contract": code_contract(root, "deployment"),
        "engine_build": engine_contract(root),
        "initial_state": initial_state or {"mode": "fresh", "equity": 20000.0},
    }


def real_engine_payload(frame, cutoff, *, prefix_rows=None, alpha="A-SC") -> dict:
    """One actual small QuantBT computation.

    Only deterministic financial substance is returned: provenance (wall
    clock, producer ids, paths) stays out so two runs over the same semantics
    compare byte-for-byte.
    """
    import numpy as np

    from ..time_edge.execution import PreparedAccount

    account_start = frame.index[len(frame) // 2]
    run = PreparedAccount(frame).run(
        alpha, selection(cutoff.isoformat()), account_start=account_start)
    equity = run["equity"]
    payload = {
        "status": run["status"],
        "terminal_equity": float(run["terminal_equity"]),
        "engine_fill_count": int(run["engine_fill_count"]),
        "callback_count": int(run["callback_count"]),
        "visited_bars": int(len(run["index"])),
        "equity_sha256": hashlib.sha256(equity.tobytes()).hexdigest(),
        "requested_contract": run["requested_contract"],
    }
    if prefix_rows is not None:
        payload["equity_prefix_rows"] = int(prefix_rows)
        payload["equity_prefix_sha256"] = hashlib.sha256(
            np.asarray(equity[:prefix_rows], float).tobytes()).hexdigest()
    return payload


def real_engine_run(frame, cutoff, *, prefix_rows=None, alpha="A-SC") -> dict:
    """Payload plus the separately captured causality coordinates."""
    from .phase_common import utcnow

    return {
        "payload": real_engine_payload(frame, cutoff, prefix_rows=prefix_rows,
                                       alpha=alpha),
        "causality": {
            "physical_compute_at": utcnow(),
            "simulated_cutoff": cutoff.isoformat(),
            "simulated_ready_at": cutoff.isoformat(),
        },
    }


def _canonical(value) -> bytes:
    from ..evidence.manifest import dumps_strict

    return dumps_strict(value).encode("utf-8")


def cross_run_reuse_experiment(root, cache_root, *, rows=DEFAULT_FRAME_ROWS,
                               seed=7, run_a="ra02-phase-a",
                               run_b="ra02-phase-b") -> dict:
    """C01 at phase scope: one real engine run, then a HIT under a new run id.

    The payload excludes provenance (run ids, wall time, paths), so the two
    runs compare byte-for-byte on the financial substance.
    """
    from ..time_edge.compute_cache import ComputeCache

    frame = market_frame(rows, seed=seed)
    cutoff = frame.index[len(frame) // 2]
    facets = deployment_facets(frame, cutoff, root=root)
    cache = ComputeCache(cache_root, "phase02")
    engine_invocations: list[str] = []
    engine_walls: list[float] = []

    def compute(tag):
        def callback():
            engine_invocations.append(tag)
            started = time.perf_counter()
            payload = real_engine_run(frame, cutoff)["payload"]
            engine_walls.append(time.perf_counter() - started)
            return payload
        return callback

    def forbidden():
        raise AssertionError("a HIT must never recompute")

    first_payload, first_event = cache.get_or_compute_singleflight(
        "deployment", facets, compute(run_a), producer=run_a)
    second_payload, second_event = cache.get_or_compute_singleflight(
        "deployment", facets, forbidden, producer=run_b)
    causality = real_engine_run(frame, cutoff)["causality"]
    return {
        "first_computation": {
            "producer": run_a,
            "status": first_event["status"],
            "engine_runs": len(engine_invocations),
            "engine_wall_seconds": (engine_walls[0] if engine_walls else 0.0),
            "visited_bars": first_payload["visited_bars"],
            "payload_sha256": hashlib.sha256(_canonical(first_payload)).hexdigest(),
        },
        "cross_run_reuse": {
            "producer": run_b,
            "status": second_event["status"],
            "new_engine_runs": 0 if second_event["status"] == "HIT" else None,
            "payload_sha256": hashlib.sha256(_canonical(second_payload)).hexdigest(),
            "producer_of_reused_payload": second_event["producer"]["lab_run_id"],
        },
        "equivalence": {"method": "canonical-byte-equal",
                        "passed": first_payload == second_payload},
        "provenance_excluded_from_key": ["lab_run_id", "output_path",
                                         "wall_clock_created_at", "producer_id"],
        "causality_fields": ["physical_compute_at", "simulated_cutoff",
                             "simulated_ready_at"],
        "causality_guard_accepted": bool(assert_causal_hit(causality, cutoff=cutoff)),
        "engine_invocations": engine_invocations,
    }


def resume_parity_experiment(cache_root, *, seed=DEFAULT_SEED, n_trials=6,
                             crash_after=3, run_id="ra02-phase-study") -> dict:
    """C08 at phase scope: crash, replay from cached objectives, compare."""
    from ..time_edge.compute_cache import ComputeCache

    from .study_replay import STARTUP_TRIALS

    cache = ComputeCache(cache_root, "phase02search")
    evaluated: list[dict] = []
    events = {"hits": 0, "misses": 0}

    def objective_of(params):
        def compute():
            evaluated.append(dict(params))
            return {"value": float(1.0 - abs(params["x"] - 0.5))}
        payload, event = cache.get_or_compute_singleflight(
            "search", {"schema": "ra02_resume_v1", **params}, compute,
            producer=run_id)
        if event["status"] == "HIT":
            events["hits"] += 1
        else:
            events["misses"] += 1
        return payload["value"]

    reference = run_study(seed, n_trials, objective_of, space=SEARCH_SPACE)
    records: list[dict] = []
    try:
        run_study(seed, n_trials, objective_of, space=SEARCH_SPACE,
                  interrupt_after=crash_after)
    except StudyInterrupted as interrupted:
        records = interrupted.records
    resumed = run_study(seed, n_trials, objective_of, replay=records,
                        space=SEARCH_SPACE)
    naive = run_study_dropping_tells(seed, records, n_trials - crash_after,
                                     space=SEARCH_SPACE)
    return {
        "seed": seed,
        "n_trials": n_trials,
        "crash_after": crash_after,
        "startup_trials": STARTUP_TRIALS,
        "replayed_trials": len(records),
        "parity_passed": (resumed["proposals"] == reference["proposals"]
                          and resumed["objectives"] == reference["objectives"]),
        "naive_restart_differs": naive != reference["proposals"][crash_after:],
        "reference_proposals_sha256": hashlib.sha256(
            _canonical(reference["proposals"])).hexdigest(),
        "resumed_proposals_sha256": hashlib.sha256(
            _canonical(resumed["proposals"])).hexdigest(),
        "naive_proposals_sha256": hashlib.sha256(_canonical(naive)).hexdigest(),
        "evaluations_reference": reference["evaluations"],
        "evaluations_resumed": resumed["evaluations"],
        "unique_evaluations": len({_canonical(p) for p in evaluated}),
        "evaluation_requests": events["hits"] + events["misses"],
        "cache_hits": events["hits"],
        "cache_misses": events["misses"],
    }