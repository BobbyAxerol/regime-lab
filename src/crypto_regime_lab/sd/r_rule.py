"""SD-02: R_RULE, the cheap rule-based comparator (guide SS5.7).

State assignment via a median-training-split threshold on
``log(rv_28/rv_180)`` (causal: the threshold is fit ONLY from permitted-past
training origins, never all-history) -- NOT JM's learned 2-state clustering.
Everything downstream (residual-correction architecture, penalty, support
floor) is the IDENTICAL ``model_bc.fit_model_c``/``predict_c`` machinery C
uses; R_RULE differs from C only in how the per-origin state label is
produced. A development diagnostic only (guide SS5.7): never silently
substituted for C in a final run.
"""
from __future__ import annotations

import statistics

HIGH_VOL_STATE = 1
LOW_VOL_STATE = 0


class RRuleError(ValueError):
    """An R_RULE threshold/state step was internally inconsistent."""


def fit_threshold(train_log_rv_ratios: list) -> float:
    """Median of ``log(rv_28/rv_180)`` over PERMITTED-PAST training origins
    only (guide SS5.7: 'Threshold fit bang permitted past, khong all-history').
    One value per origin -- callers must pass one ratio per origin, not one
    per candidate row (the same origin-vs-row-count discipline guide SS5.6
    already requires for state-support counting)."""
    if not train_log_rv_ratios:
        raise RRuleError("fit_threshold requires at least one train-origin ratio")
    return statistics.median(train_log_rv_ratios)


def assign_state(log_rv_ratio: float, *, threshold: float) -> int:
    """HIGH_VOL_STATE iff the origin's own ratio is >= the frozen train-only
    threshold, else LOW_VOL_STATE -- a fixed, deterministic rule, never
    re-derived per prediction."""
    return HIGH_VOL_STATE if log_rv_ratio >= threshold else LOW_VOL_STATE


def state_by_origin(ratio_by_origin: dict, *, threshold: float) -> dict:
    """{origin_cutoff: int state}, for every origin with a known ratio --
    an origin with ``ratio_by_origin[o] is None`` (e.g. insufficient raw
    prehistory, the SAME typed gap JM's own tape can hit) maps to
    ``None``, never a fabricated state ID (mirrors ``jm_vintage``'s own
    ``STATUS_INSUFFICIENT_PREHISTORY`` handling)."""
    return {o: (assign_state(ratio, threshold=threshold) if ratio is not None else None)
           for o, ratio in ratio_by_origin.items()}
