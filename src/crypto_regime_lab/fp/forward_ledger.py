"""FP-04 -- historical forward ledger and parameter regions (guide section 16 /
section 7).

An accumulating archive of what a real search found at each historical origin
and how its representative candidates actually performed FORWARD, built so
that no future-discovered winner can be read back into a past origin's
decision (guide 7.1: "Archive không phải bảng winners").

Guide 16's five maturity distinctions, and how this module operationalises
them (the guide names them but does not formally define them -- this is FP-04's
disclosed operational reading, guide-consistent, not a silent substitution):

  * ``decision_available_record`` -- the region/representative SELECTION at
    this origin is known as of ``as_of`` (True whenever as_of >= origin_cutoff:
    a decision made from pre-cutoff information only). Says nothing about the
    forward outcome.
  * ``future_label_not_yet_mature`` -- the decision is available but the
    forward window [origin_cutoff, origin_cutoff+forward_horizon) has not
    closed as of ``as_of`` yet: the label is not knowable yet.
  * ``matured_forward_record`` -- the forward window has closed AND a valid
    forward metric was computed. This is the ONLY state whose ``label`` a
    learner may read (guide item 6: "Chi expose matured records cho learner").
  * ``censored_or_failed_record`` -- the origin's search failed, or the
    forward window closed but no valid metric could be produced (a raised
    ``ContractError``/data gap/insufficient observations). ``label`` stays
    ``None`` with a typed reason -- guide 7.1's "Outcome thiếu không bằng
    zero", never a silent 0.0.
  * ``retrospective_train_replay`` -- NOT a stored state: a query-time tag
    ``training_view`` attaches to a ``matured_forward_record`` when
    ``fp.chronology.chronological_split`` accepts it into a training replay
    at some later ``decision_time``. Distinguishes the stored fact (a record
    matured) from how a learner is consuming it right now.

Region geometry (guide 7.3) reuses ``selector.schema_distance.ParamSchema``
verbatim -- the SAME Gower-like, declared-bounds-normalised distance L04.3
built and LAB-04..08 already relies on. This module never invents a second
distance metric. Geometry clusters on PARAMS ONLY: forward/decay outcomes are
computed strictly AFTER region freeze and never fed back into clustering or
medoid choice (guide 7.3's "Không cluster bằng future outcomes", proved by
FP04-T03/T04).

Guide 7.5's caveat is respected literally: a region's identity is LOCAL to its
own origin's freeze (``region_id`` is only unique within one origin_cutoff),
never claimed as a stable label across origins.
"""
from __future__ import annotations

MATURITY_STATES = (
    "decision_available_record",
    "future_label_not_yet_mature",
    "matured_forward_record",
    "censored_or_failed_record",
)
CONSUMPTION_TAG = "retrospective_train_replay"

DEVELOPMENT_START = "2020-01-01"
DEVELOPMENT_END = "2023-12-31"
LOAD_BUFFER_DAYS = 5

#: FP-04's frozen origin grid: quarter-start dates (Jan/Apr/Jul/Oct 1) across
#: 2021-2023, the SAME three full development-role years FP-03's
#: CALIBRATION_ORIGINS already used (2021-06-01/2022-06-01/2023-06-01,
#: 'same month across three years', guide's own calendar-spacing rule),
#: extended to quarterly density. Chosen BEFORE any origin's search outcome
#: is known (guide's 'không chọn vì stock có PnL đẹp').
#:
#: This is 12 of the guide 3.2's research-default target of ~26-39 blocks --
#: an EXPLICIT, disclosed partial scope, not a silent under-provision. At
#: FP-03's measured real cost (2575-3042s per 256-trial/180-day origin,
#: section 15's frozen B_search), the full 26-39-origin target would cost
#: ~19.5-29 hours of strictly-sequential (workers=1) engine wall-clock --
#: proportionate to attempt now would be roughly 6-10x LAB-08's ~3-hour
#: factorial, the largest real-engine commitment anywhere else in this lab's
#: history. Guide 16's own closing sentence permits this explicitly:
#: 'Thiếu số origins cho model không làm archive vô giá trị, nhưng không
#: được gọi model study hoàn tất' (a short origin count does not invalidate
#: the archive, but the MODEL STUDY -- FP-05 onward's actual fit -- may not
#: be called complete on it alone). FP04-T07's incremental-rebuild guarantee
#: means growing this grid later costs only the INCREMENTAL new origins,
#: never a redo of these 12.
FP04_ORIGIN_GRID = tuple(
    f"{year}-{month:02d}-01" for year in (2021, 2022, 2023) for month in (1, 4, 7, 10)
)


class LedgerError(ValueError):
    """A ledger construction step was internally inconsistent."""


# ---------------------------------------------------------------------------
# Origin grid
# ---------------------------------------------------------------------------

def valid_origin_placement_window(*, development_start: str = DEVELOPMENT_START,
                                  development_end: str = DEVELOPMENT_END,
                                  train_memory_days: int, forward_horizon_days: int,
                                  load_buffer_days: int = LOAD_BUFFER_DAYS):
    """[earliest, latest] origin_cutoff that keeps BOTH the training lookback
    and the forward horizon strictly inside the registered development role
    (configs/study_registration.json data_roles.development) -- never
    reaching into outer_evaluation (guide 3.3's data-role separation)."""
    import pandas as pd

    earliest = (pd.Timestamp(development_start, tz="UTC")
               + pd.Timedelta(days=train_memory_days + load_buffer_days))
    latest = (pd.Timestamp(development_end, tz="UTC")
             - pd.Timedelta(days=forward_horizon_days + 1))
    if latest < earliest:
        raise LedgerError("no valid origin placement window at this train_memory/forward_horizon")
    return earliest, latest


def validate_origin_grid(origins, *, train_memory_days: int, forward_horizon_days: int) -> dict:
    """Every declared origin must fall inside the valid placement window --
    checked, never assumed, before any engine call is spent on it."""
    import pandas as pd

    earliest, latest = valid_origin_placement_window(
        train_memory_days=train_memory_days, forward_horizon_days=forward_horizon_days)
    rows = []
    for cutoff in origins:
        ts = pd.Timestamp(cutoff, tz="UTC")
        ok = earliest <= ts <= latest
        rows.append({"origin_cutoff": cutoff, "valid": bool(ok),
                    "reason": None if ok else
                    f"{cutoff} outside valid placement window [{earliest.date()}, {latest.date()}]"})
    return {"valid_window": [earliest.isoformat(), latest.isoformat()], "origins": rows,
           "all_valid": all(r["valid"] for r in rows)}


def flag_window_overlaps(origins, *, train_memory_days: int, forward_horizon_days: int) -> dict:
    """Guide 7.2: 'Overlapping forward windows phải được đánh dấu.' Marks BOTH
    training-window and forward-window overlaps between every pair of
    origins -- a fact about the grid, independent of whether any candidate
    ended up using it (7.2 also requires training overlap to be visible, since
    it is what makes cross-origin candidates clustered rather than
    independent observations)."""
    import pandas as pd

    ts = {o: pd.Timestamp(o, tz="UTC") for o in origins}

    def _overlaps(lo1, hi1, lo2, hi2) -> bool:
        return lo1 < hi2 and lo2 < hi1

    out = {}
    for o in origins:
        train_lo, train_hi = ts[o] - pd.Timedelta(days=train_memory_days), ts[o]
        fwd_lo, fwd_hi = ts[o], ts[o] + pd.Timedelta(days=forward_horizon_days)
        train_over, fwd_over = [], []
        for p in origins:
            if p == o:
                continue
            p_train_lo, p_train_hi = ts[p] - pd.Timedelta(days=train_memory_days), ts[p]
            p_fwd_lo, p_fwd_hi = ts[p], ts[p] + pd.Timedelta(days=forward_horizon_days)
            if _overlaps(train_lo, train_hi, p_train_lo, p_train_hi):
                train_over.append(p)
            if _overlaps(fwd_lo, fwd_hi, p_fwd_lo, p_fwd_hi):
                fwd_over.append(p)
        out[o] = {"train_window_overlaps_with": sorted(train_over),
                  "forward_window_overlaps_with": sorted(fwd_over)}
    return out


# ---------------------------------------------------------------------------
# Region geometry (params only, guide 7.3)
# ---------------------------------------------------------------------------

def _dedup_by_params(candidates: list[dict]) -> list[dict]:
    seen = {}
    for c in candidates:
        key = tuple(sorted(c["params"].items()))
        if key not in seen or c["objective"] > seen[key]["objective"]:
            seen[key] = c
    return list(seen.values())


def cluster_into_regions(schema, candidates: list[dict], *, distance_threshold: float) -> list[list[dict]]:
    """Greedy deterministic clustering, PARAMS ONLY (never forward/decay
    outcomes -- guide 7.3). Candidates are deduplicated by parameter point
    first (repeated evaluations of the identical point are the SAME
    candidate), then processed in descending IS-objective order so the
    best-performing point in a neighbourhood anchors it first. A candidate
    joins the nearest existing region if within ``distance_threshold`` of
    that region's CURRENT medoid, else opens a new region. No scipy/sklearn
    dependency: the search space here is 1-3 ordinal dimensions and a
    handful of unique candidates per origin (guide's own measured coverage:
    <=150 unique points out of a 4928-point grid at B_search=256), so a
    threshold walk is both sufficient and fully auditable.
    """
    unique = _dedup_by_params(candidates)
    ordered = sorted(unique, key=lambda c: c["objective"], reverse=True)
    regions: list[list[dict]] = []
    medoids: list[dict] = []
    for candidate in ordered:
        best_region, best_distance = None, None
        for idx, medoid in enumerate(medoids):
            d = schema.distance(candidate["params"], medoid["params"])
            if best_distance is None or d < best_distance:
                best_region, best_distance = idx, d
        if best_region is not None and best_distance <= distance_threshold:
            regions[best_region].append(candidate)
            medoids[best_region] = region_medoid(schema, regions[best_region])
        else:
            regions.append([candidate])
            medoids.append(candidate)
    return regions


def region_medoid(schema, members: list[dict]) -> dict:
    """The REAL member minimising total distance to the others -- never an
    invented centroid (guide 7.4: 'Không tạo centroid params rồi deploy mà
    chưa đánh giá')."""
    if len(members) == 1:
        return members[0]
    return min(members, key=lambda m: sum(schema.distance(m["params"], other["params"])
                                          for other in members if other is not m))


def region_summary(schema, *, origin_cutoff: str, region_id: str, members: list[dict],
                   q_probe: int = 0) -> dict:
    """Guide 7.4's required per-region fields. Forward utility/decay are left
    None here (pending, filled by the caller after a real forward evaluation
    of the medoid) -- computed strictly AFTER this summary exists, so region
    geometry can never have depended on them (FP04-T04)."""
    medoid = region_medoid(schema, members)
    objectives = [m["objective"] for m in members]
    pairwise = [schema.distance(a["params"], b["params"])
               for i, a in enumerate(members) for b in members[i + 1:]]
    return {
        "schema": "regime_lab.fp04_region.v1",
        "origin_cutoff": origin_cutoff, "region_id": region_id,
        "member_candidate_ids": [m["trial_id"] for m in members],
        "geometry_schema_name": schema.name,
        "medoid_trial_id": medoid["trial_id"], "medoid_params": medoid["params"],
        "is_quality_distribution": {
            "n": len(objectives), "min": min(objectives), "max": max(objectives),
            "mean": sum(objectives) / len(objectives)},
        "probe_coverage": {"probes_run": 0, "reason": (
            "Q_probe frozen at 0 in FP-03 search_policy.json (guide 6.5 not exercised "
            "this study); disclosed, not assumed" if q_probe == 0 else
            f"{q_probe} independent probes recorded separately")},
        "behavioral_diversity_mean_pairwise_distance": (
            sum(pairwise) / len(pairwise) if pairwise else 0.0),
        "historical_support_within_origin": len(members),
        "historical_support_note": (
            "support counted WITHIN this origin's own search only -- guide 7.5 forbids "
            "treating a region id as universal across origins, so no cross-origin support "
            "claim is made in FP-04"),
        "forward_utility_mean_daily_return": None,   # filled after forward eval
        "decay_D_mean_daily_return": None,            # filled after forward eval
    }


def build_regions_for_origin(schema, *, origin_cutoff: str, trial_records: list[dict],
                             distance_threshold: float, max_representatives: int) -> list[dict]:
    """Orchestrates clustering + medoid + per-region summary, capped at
    ``max_representatives`` regions kept by best-member IS objective (guide
    3.2/FP-03's frozen representative_subset_size). Fewer real, distinct
    unique candidates than the cap is reported as-is, never padded."""
    completed = [r for r in trial_records if not r.get("pruned") and r.get("objective") is not None]
    clusters = cluster_into_regions(schema, completed, distance_threshold=distance_threshold)
    clusters.sort(key=lambda members: max(m["objective"] for m in members), reverse=True)
    kept = clusters[:max_representatives]
    return [region_summary(schema, origin_cutoff=origin_cutoff, region_id=f"R{i:02d}",
                           members=members)
           for i, members in enumerate(kept)]


# ---------------------------------------------------------------------------
# Maturity state machine (guide 16's five distinctions)
# ---------------------------------------------------------------------------

def maturity_state(*, origin_cutoff, forward_horizon_days: int, as_of, wf_ok: bool,
                   forward_attempted: bool, forward_ok: bool | None) -> str:
    import pandas as pd

    origin_ts = pd.Timestamp(origin_cutoff, tz="UTC") if pd.Timestamp(origin_cutoff).tzinfo is None \
        else pd.Timestamp(origin_cutoff)
    as_of_ts = pd.Timestamp(as_of, tz="UTC") if pd.Timestamp(as_of).tzinfo is None \
        else pd.Timestamp(as_of)
    if as_of_ts < origin_ts:
        raise LedgerError("as_of precedes origin_cutoff: the decision itself is not available yet")
    if not wf_ok:
        return "censored_or_failed_record"
    matures_at = origin_ts + pd.Timedelta(days=forward_horizon_days)
    if as_of_ts < matures_at:
        return "future_label_not_yet_mature"
    if not forward_attempted:
        return "decision_available_record"
    if forward_ok:
        return "matured_forward_record"
    return "censored_or_failed_record"


# ---------------------------------------------------------------------------
# Forward evaluation of one region's medoid -> one ledger record
# ---------------------------------------------------------------------------

def evaluate_region_forward(cache, root, alpha_id: str, frame, region: dict, *,
                            origin_cutoff, forward_horizon_days: int, economics: dict,
                            producer: str, report_level: str | None = "score") -> dict:
    """One real IS-vs-forward evaluation of a region's medoid (reuses
    fp.forward_comparison.candidate_decay verbatim -- FP-04 never builds a
    second decay computation). A raised ContractError/ForwardComparisonError
    (a real, structural data issue -- e.g. an incomplete forward window) is
    caught here and turned into an explicit censored record, never a crash
    that would take the rest of a multi-hour run down with it, and never a
    silent 0.0 (guide 7.1: 'Outcome thiếu không bằng zero')."""
    import pandas as pd

    from . import forward_comparison as fc
    from ..experiments.time_edge_contracts import ContractError

    origin_ts = pd.Timestamp(origin_cutoff, tz="UTC") if pd.Timestamp(origin_cutoff).tzinfo is None \
        else pd.Timestamp(origin_cutoff)
    forward_end = origin_ts + pd.Timedelta(days=forward_horizon_days)
    is_frame = frame.loc[frame.index < origin_ts]
    forward_frame = frame.loc[(frame.index >= origin_ts) & (frame.index < forward_end)]
    if is_frame.empty or forward_frame.empty:
        return {"forward_ok": False, "reason": "IS or forward slice empty at this frame", "decay": None}
    try:
        decay = fc.candidate_decay(cache, root, alpha_id, is_frame, forward_frame,
                                   region["medoid_params"], origin_cutoff=origin_ts,
                                   forward_end=forward_end, economics=economics,
                                   producer=producer, report_level=report_level)
    except (ContractError, ValueError) as exc:
        return {"forward_ok": False, "reason": f"{type(exc).__name__}: {exc}", "decay": None}
    return {"forward_ok": True, "reason": None, "decay": decay}


# ---------------------------------------------------------------------------
# Ledger records (guide item 5: full label timing/provenance)
# ---------------------------------------------------------------------------

def ledger_record(*, origin_cutoff: str, forward_horizon_days: int, region: dict,
                  forward_result: dict, wf_ok: bool, as_of, geometry_version: str) -> dict:
    """One row, directly consumable by fp.chronology.chronological_split
    (label_field='label', available_field='label_available_at')."""
    import pandas as pd

    origin_ts = pd.Timestamp(origin_cutoff, tz="UTC") if pd.Timestamp(origin_cutoff).tzinfo is None \
        else pd.Timestamp(origin_cutoff)
    label_available_at = (origin_ts + pd.Timedelta(days=forward_horizon_days)).isoformat()
    state = maturity_state(origin_cutoff=origin_ts, forward_horizon_days=forward_horizon_days,
                           as_of=as_of, wf_ok=wf_ok, forward_attempted=forward_result is not None,
                           forward_ok=(forward_result or {}).get("forward_ok"))
    label = None
    decay_value = None
    forward_metrics = None
    if state == "matured_forward_record":
        decay = forward_result["decay"]
        forward_metrics = decay["forward_metrics"]
        label = forward_metrics["mean_daily_return"]
        decay_value = decay["D_mean_daily_return"]
    censored_reason = None
    if state == "censored_or_failed_record":
        censored_reason = (forward_result or {}).get("reason") or "origin search failed"
    return {
        "schema": "regime_lab.fp04_ledger_record.v1",
        "record_id": f"{origin_cutoff}:{region['region_id']}",
        # origin_cutoff stays the ORIGINAL string (the join key against
        # origin_ledger.json's own origin_cutoff field, guide 16's provenance
        # requirement) -- origin_time carries the precise tz-aware timestamp
        # for chronological ordering. Reformatting origin_cutoff through
        # origin_ts.isoformat() here once made it silently stop matching
        # origin_ledger.json's plain-date convention, which made
        # FP04-G-CAUSAL's cross-origin-leak check vacuous (found by the gate's
        # own regression test failing for the wrong reason).
        "origin_cutoff": origin_cutoff, "origin_time": origin_ts.isoformat(),
        "region_id": region["region_id"], "medoid_trial_id": region["medoid_trial_id"],
        "params": region["medoid_params"], "is_objective": region["is_quality_distribution"]["mean"],
        "region_support_within_origin": region["historical_support_within_origin"],
        "maturity_state": state,
        "label": label, "label_available_at": label_available_at,
        "forward_metrics": forward_metrics, "decay_D_mean_daily_return": decay_value,
        "censored_reason": censored_reason,
        "geometry_version": geometry_version,
    }


def geometry_version_id(schema, *, distance_threshold: float, max_representatives: int) -> str:
    import hashlib
    import json

    payload = json.dumps({"schema_name": schema.name, "distance_threshold": distance_threshold,
                          "max_representatives": max_representatives}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Origin weighting (guide 7.2: an origin with more candidates must not
# automatically outweigh one with fewer -- FP04-T06)
# ---------------------------------------------------------------------------

def origin_weights(records: list[dict]) -> dict:
    origins = sorted({r["origin_cutoff"] for r in records})
    if not origins:
        return {}
    per_origin_share = 1.0 / len(origins)
    counts: dict = {}
    for r in records:
        counts[r["origin_cutoff"]] = counts.get(r["origin_cutoff"], 0) + 1
    return {r["record_id"]: per_origin_share / counts[r["origin_cutoff"]] for r in records}


# ---------------------------------------------------------------------------
# Views (guide items 6-7: matured-only exposure, origin-weighted panel)
# ---------------------------------------------------------------------------

def matured_view(records: list[dict], *, as_of) -> list[dict]:
    """Guide item 6: 'Chỉ expose matured records cho learner.' Recomputes
    maturity against ``as_of`` from each record's own timing fields rather
    than trusting a stored flag, so a caller cannot accidentally read a
    record before it matured just because the ledger was built later."""
    import pandas as pd

    as_of_ts = pd.Timestamp(as_of, tz="UTC") if pd.Timestamp(as_of).tzinfo is None \
        else pd.Timestamp(as_of)
    out = []
    for r in records:
        available = pd.Timestamp(r["label_available_at"])
        if r["maturity_state"] == "matured_forward_record" and available <= as_of_ts:
            out.append(r)
    return out


def panel_view(records: list[dict], *, as_of) -> dict:
    """Guide item 7: origin-weighted panel view over MATURED records only."""
    matured = matured_view(records, as_of=as_of)
    weights = origin_weights(matured)
    return {
        "schema": "regime_lab.fp04_panel_view.v1", "as_of": str(as_of),
        "n_matured_records": len(matured), "n_origins": len({r["origin_cutoff"] for r in matured}),
        "records": matured, "weights": weights,
        "weight_sum_per_origin_is_equal": len({round(sum(weights[r["record_id"]]
                                                          for r in matured
                                                          if r["origin_cutoff"] == o), 9)
                                               for o in {r["origin_cutoff"] for r in matured}}) <= 1,
    }


def training_view(records: list[dict], *, decision_time) -> dict:
    """Guide's fifth distinction, applied at consumption time: every row
    ``fp.chronology.chronological_split`` accepts into a training replay is
    tagged CONSUMPTION_TAG here, without mutating the record's own stored
    ``maturity_state`` (a stored fact vs. how a learner is using it now)."""
    import pandas as pd

    from .chronology import chronological_split

    decision_ts = pd.Timestamp(decision_time)
    decision_ts = decision_ts.tz_localize("UTC") if decision_ts.tzinfo is None else decision_ts
    split = chronological_split(records, decision_time=decision_ts)
    tagged = [{**row, "consumption_state": CONSUMPTION_TAG} for row in split["usable"]]
    return {**split, "usable": tagged}


# ---------------------------------------------------------------------------
# Incremental rebuild (guide item 8 / FP04-T07/T08: reuse, never overwrite)
# ---------------------------------------------------------------------------

def incremental_rebuild(existing_origins: list[dict], *, requested_origin_cutoffs: list[str],
                        build_origin_fn) -> dict:
    """Only calls ``build_origin_fn`` for an origin cutoff that is NOT
    already present with a valid (wf_ok=True) record. An existing valid
    origin's record is carried over BYTE-IDENTICAL -- never recomputed,
    never re-clustered, whatever NEW policy (e.g. a different
    distance_threshold) ``build_origin_fn`` would apply to a fresh call."""
    existing_by_cutoff = {o["origin_cutoff"]: o for o in existing_origins}
    result_origins = []
    engine_calls_made_for = []
    reused_for = []
    for cutoff in requested_origin_cutoffs:
        prior = existing_by_cutoff.get(cutoff)
        if prior is not None and prior.get("wf_ok") is True:
            result_origins.append(prior)
            reused_for.append(cutoff)
            continue
        result_origins.append(build_origin_fn(cutoff))
        engine_calls_made_for.append(cutoff)
    return {"origins": result_origins, "engine_calls_made_for": engine_calls_made_for,
           "reused_without_engine_call_for": reused_for}
