"""RA04.3: post-selection admission over an UNCHANGED stock Mode 4 selector.

Contract name `STOCK_MODE4_PLUS_ADMISSION_V1` (never called "unchanged stock" --
it is stock selection PLUS a guard). The stock selector's raw winning record is
never edited and no second optimizer picks a different winner:

    stock Mode 4 search/selection -> keep the raw selected record AS-IS
    -> check TRAINING-ONLY support against a rule frozen before any outcome
    -> enough support: ADMIT the raw selection
    -> not enough: KEEP_INCUMBENT with a reason; no incumbent yet -> COMMON_FLAT

Two support checks, both derived from already-registered, alpha-specific
numbers -- never one hardcoded trade count applied identically to every alpha
(the guide forbids exactly that):

* day coverage: the winner's own full-train scorer record must span at least
  `max(2, history_days(alpha_id))` complete UTC days -- `history_days` is the
  EXISTING per-alpha warmup requirement in `time_edge/eligibility.py`
  (A-SC=1, A-HMA=18, A-VWAP=101, A-HASH=3), and 2 matches the floor already
  enforced inside `TrainingScorer._score` (`len(sample) < 2`) so this check is
  never weaker than the engine path it wraps.
* shard support: at least half of the registered `is_subperiods` (default 6,
  a single engine-wide config, not an alpha-specific outcome count) must have
  produced a FINITE per-shard score for the winner, not the engine's fallback
  constant -- this targets the exact F-04 mechanism (mode4_reproduction.py):
  a selection is not admitted on the strength of one shared data point.

Both thresholds are frozen in `admission_thresholds()` before any candidate in
a run is scored, so nothing here can be tuned after seeing which selection it
would flip.
"""
from __future__ import annotations

import math

from .mode4_reproduction import DEFAULT_IS_SUBPERIODS

CONTRACT_NAME = "STOCK_MODE4_PLUS_ADMISSION_V1"
SHARD_SUPPORT_FRACTION = 0.5  # registered: >=half of is_subperiods shards must be finite


def admission_thresholds(alpha_id: str, *, is_subperiods: int = DEFAULT_IS_SUBPERIODS) -> dict:
    from ..time_edge.eligibility import history_days

    min_days = max(2, history_days(alpha_id))
    min_finite_shards = max(2, math.ceil(is_subperiods * SHARD_SUPPORT_FRACTION))
    return {
        "schema": "regime_lab.ra04_admission_thresholds.v1",
        "alpha_id": alpha_id,
        "min_complete_train_days": min_days,
        "min_complete_train_days_provenance": (
            f"max(2, history_days('{alpha_id}')) -- 2 matches TrainingScorer._score's own "
            "len(sample)<2 floor; history_days is the existing per-alpha warmup requirement"),
        "min_finite_shards": min_finite_shards,
        "min_finite_shards_of": is_subperiods,
        "min_finite_shards_provenance": (
            f"ceil({is_subperiods} * {SHARD_SUPPORT_FRACTION}) -- half of the registered "
            "is_subperiods engine config; a mechanism-soundness floor, not a per-alpha "
            "trade-count guess"),
        "registered_before_any_candidate_scored": True,
    }


def admit_selection(raw_selection: dict, *, alpha_id: str, incumbent, winner_scorer_record: dict,
                    winner_shard_finite_count: int, thresholds: dict) -> dict:
    """One admission decision. Never picks a different winner than
    `raw_selection` -- only ADMIT/KEEP_INCUMBENT/COMMON_FLAT_FALLBACK.

    winner_scorer_record: the TrainingScorer EVALUATED record for the raw
      winner's own params (the SAME record the stock selector's objective was
      computed from -- training-only, no paired/OOS outcome involved).
    winner_shard_finite_count: finite_shard_count from mode4_reproduction's
      per-candidate scoring, for the SAME winner.
    """
    if raw_selection is None:
        raise ValueError("admit_selection needs the raw stock winner, never a fabricated one")
    supported_days = len(winner_scorer_record.get("daily_returns") or [])
    day_ok = supported_days >= thresholds["min_complete_train_days"]
    shard_ok = winner_shard_finite_count >= thresholds["min_finite_shards"]
    reasons = []
    if not day_ok:
        reasons.append(f"only {supported_days} complete train days, need >= "
                       f"{thresholds['min_complete_train_days']}")
    if not shard_ok:
        reasons.append(f"only {winner_shard_finite_count} finite subperiod shards of "
                       f"{thresholds['min_finite_shards_of']}, need >= {thresholds['min_finite_shards']}")
    common = {
        "schema": "regime_lab.ra04_admission_decision.v1", "contract": CONTRACT_NAME,
        "alpha_id": alpha_id, "raw_selection": raw_selection,
        "supported_days": supported_days, "winner_shard_finite_count": winner_shard_finite_count,
        "thresholds": thresholds, "day_support_ok": day_ok, "shard_support_ok": shard_ok,
    }
    if day_ok and shard_ok:
        return {**common, "decision": "ADMIT", "reason": None}
    reason = "; ".join(reasons)
    if incumbent is None:
        return {**common, "decision": "COMMON_FLAT_FALLBACK", "kept": None,
                "reason": f"{reason}; no incumbent yet"}
    return {**common, "decision": "KEEP_INCUMBENT", "kept": incumbent, "reason": reason}
