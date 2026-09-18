"""RA04.1/RA04.2: pin selector semantics and reproduce F-04 (RA-GUIDE-1.0 section 8).

F-04 (guide table, evidence E07): "7/8 selections of the control used temporal
fallback; a case where one finite subperiod has a score like six [other]
identical finite [scores]." No raw run artifact from the original snapshot
exists on this host (RA-01's finding_disposition.json: current_disposition
PRESENT, not FIXED_WITH_PROOF) -- so this module reproduces the MECHANISM on
the CURRENT source with a pure-helper regression against the REAL installed
selector's own subperiod splitter, rather than pretending to replay numbers
that are not on disk.

Mechanism found (verified against the installed engine, not assumed):
`quantbt.core.wfo_preparation.split_datetime_index_into_subperiods_v1` (the
function the installed is_only_robust selector uses for its own
`is_subperiods` config, default 6) splits a train window into equal BAR-COUNT
shards -- only the FIRST shard starts at a UTC day boundary; every other
shard usually starts mid-day. `TrainingScorer._score` (time_edge/execution.py)
scores a requested subperiod on complete UTC days only, and when a candidate
does not trade inside a shard, the shard's Sharpe is undefined and the scorer
returns sharpe=-inf with status=ZERO_VARIANCE (a deliberate placeholder, not a
crash). The installed selector's `_collect_subperiod_sharpes` filters with
`np.isfinite`, so -inf shards (both INSUFFICIENT_DAYS and ZERO_VARIANCE) are
correctly dropped -- but when 5 or 6 of 6 shards return -inf for a candidate,
its "temporal robustness" score collapses to the ONE surviving shard's raw
value (median==q25==that value, mad==0), or to the engine's registered
fallback constant when ALL 6 are -inf. Several different parameter sets that
all fail to trade in the same shards then compare as identically "temporally
robust" on the strength of one shared data point, or all tie at the fallback
constant -- which is exactly the two things F-04 describes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .phase_common import utcnow

DEFAULT_IS_SUBPERIODS = 6  # quantbt.walkforward.WalkForwardConfig.is_subperiods default


def real_subperiod_shards(train_index: pd.DatetimeIndex, is_subperiods: int = DEFAULT_IS_SUBPERIODS):
    """The SAME splitter the installed selector uses, called directly -- not
    reimplemented. Returns the shard list and whether each shard's own
    boundaries land on UTC day starts (only shard 0 reliably does)."""
    from quantbt.core.wfo_preparation import split_datetime_index_into_subperiods_v1

    shards = list(split_datetime_index_into_subperiods_v1(train_index, int(is_subperiods)))
    rows = []
    for i, shard in enumerate(shards):
        rows.append({
            "shard": i, "start": shard[0].isoformat(), "end": shard[-1].isoformat(),
            "bars": len(shard), "start_is_day_aligned": bool(shard[0] == shard[0].floor("D")),
        })
    return shards, rows


def score_candidate_on_shards(scorer, params: dict, shards) -> dict:
    """One candidate's real per-shard scores via the SAME scorer callback the
    installed selector calls (TrainingScorer.__call__), classified exactly as
    the engine classifies them (np.isfinite), never re-derived independently."""
    rows = []
    for i, shard in enumerate(shards):
        out = scorer(params=params, index=shard)
        finite = bool(np.isfinite(out["sharpe"]))
        # Strict-JSON evidence never carries a raw -inf/NaN (evidence/manifest.py
        # ::dumps_strict refuses it): the placeholder is null, and `status`
        # already carries the classification (INSUFFICIENT_DAYS/ZERO_VARIANCE).
        rows.append({"shard": i, "status": out["status"],
                     "sharpe": out["sharpe"] if finite else None, "finite": finite})
    finite_values = [r["sharpe"] for r in rows if r["finite"]]
    arr = np.asarray(finite_values, dtype=np.float64)
    stats = None
    if arr.size:
        median = float(np.median(arr))
        q25 = float(np.quantile(arr, 0.25))
        mad = float(np.median(np.abs(arr - median)))
        stats = {"temporal_median": median, "temporal_q25": q25, "temporal_mad": mad,
                 "temporal_count": int(arr.size),
                 # the installed selector's own formula (q25_weight/dispersion_penalty
                 # are config-registered; reported with weight=0/penalty=0 baseline so
                 # this module never invents an untested numeric default):
                 "temporal_score_baseline_median_only": median}
    return {"params": params, "shard_rows": rows, "finite_shard_count": int(arr.size),
           "fallback_shard_count": len(rows) - int(arr.size), "stats": stats,
           "used_engine_fallback_constant": arr.size == 0}


def reproduce_f04(prepared, alpha_id: str, train_start, cutoff, candidates: list,
                  evidence_dir, lab_run_id: str, *, is_subperiods: int = DEFAULT_IS_SUBPERIODS) -> dict:
    """RA04.2: score N real candidates over the real engine's own shard split
    of ONE real train window, on the pure-helper path (no full 180-day/32-trial
    Optuna search -- a phase-owned experiment, same scale precedent as
    RA-02/RA-03). Detects both mechanisms named in F-04: candidates that
    collapse to a single shared finite data point, and candidates that share
    the SAME numeric score despite different params (the "six identical"
    pattern) -- verified by exact value match, not by eyeballing.
    """
    from ..time_edge.execution import TrainingScorer

    frame = prepared.frame
    train_index = frame.index[(frame.index >= pd.Timestamp(train_start)) & (frame.index < pd.Timestamp(cutoff))]
    shards, shard_meta = real_subperiod_shards(train_index, is_subperiods)
    scorer = TrainingScorer(prepared, alpha_id, train_start, cutoff, evidence_dir, lab_run_id)

    per_candidate = []
    for params in candidates:
        per_candidate.append(score_candidate_on_shards(scorer, params, shards))

    n = len(per_candidate)
    fallback_dominant = sum(1 for c in per_candidate if c["finite_shard_count"] <= 1)
    # cross-candidate score collapse: do two DIFFERENT parameter sets share the
    # exact same finite shard value (to float precision), which is how a
    # single shared data point makes unrelated candidates look identical?
    value_to_candidates: dict[float, list[int]] = {}
    for ci, c in enumerate(per_candidate):
        for row in c["shard_rows"]:
            if row["finite"]:
                value_to_candidates.setdefault(round(row["sharpe"], 6), []).append(ci)
    collapsed_values = {v: sorted(set(cs)) for v, cs in value_to_candidates.items() if len(set(cs)) > 1}

    return {
        "schema": "regime_lab.ra04_f04_reproduction.v1",
        "reproduced_at_utc": utcnow(),
        "method": ("pure-helper regression: TrainingScorer.__call__ scored against the "
                  "installed selector's OWN split_datetime_index_into_subperiods_v1 shards "
                  "of one real train window; no original raw evidence exists on this host "
                  "(RA-01 finding_disposition F-04 = PRESENT, not FIXED_WITH_PROOF) so this "
                  "characterizes the mechanism on current source rather than replaying "
                  "numbers that are not on disk"),
        "alpha_id": alpha_id, "is_subperiods": is_subperiods,
        "shard_boundaries": shard_meta,
        "shards_with_day_aligned_start": sum(1 for r in shard_meta if r["start_is_day_aligned"]),
        "candidates_probed": n,
        "per_candidate": per_candidate,
        "candidates_with_at_most_one_finite_shard": fallback_dominant,
        "candidates_using_engine_fallback_constant": sum(1 for c in per_candidate if c["used_engine_fallback_constant"]),
        "cross_candidate_score_collapse": collapsed_values,
        "mechanism_confirmed": {
            "only_first_shard_reliably_day_aligned": shard_meta[0]["start_is_day_aligned"]
                and not all(r["start_is_day_aligned"] for r in shard_meta[1:]),
            "some_candidate_reduces_to_single_shared_datapoint": fallback_dominant > 0,
            "different_candidates_share_an_identical_finite_score": bool(collapsed_values),
        },
        "claim_limit": ("does not claim these are the SAME numeric values the original "
                        "snapshot audit (E07) saw -- the market fixture here is a phase-owned "
                        "synthetic frame, not the original data. It claims the MECHANISM is "
                        "real and reproducible on current source, which is what RA04.2 asks for."),
    }
