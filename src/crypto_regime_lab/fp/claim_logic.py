"""Guide FP01.2 finding 6 + §21: verdicts must use the direct treatment contrast.

The failure mode already exercised once (evidence, not allegation): FUP-05's
``CADENCE_ARTIFACT`` verdict was formed by comparing the placebo to a calendar
*BAND* (placebo >= band worst), never by computing a direct
REGIME_TIMING - PLACEBO (or REGIME_TIMING - CAL_MATCHED) paired contrast.
Guide §21 forbids exactly that as the sole basis for a verdict.

This module makes the correct shape constructible and the wrong shape
explicitly unevaluable. `timing_verdict` returns
``NOT_EVALUABLE_DIRECT_CONTRAST_MISSING`` -- not a verdict -- whenever the
direct contrast row the claim rests on is absent, however suggestive the band
comparison looks.
"""
from __future__ import annotations


ALLOWED_VERDICT_STATUSES = (
    "CADENCE_ARTIFACT",
    "SURVIVED_FALSIFICATION",
    "INCONCLUSIVE_SUPPORT",
    "NOT_EVALUABLE_DIRECT_CONTRAST_MISSING",
)


def direct_pair_delta(treatment: float, comparator: float) -> float:
    """One signed treatment-minus-comparator row, both sides real numbers."""
    for name, value in (("treatment", treatment), ("comparator", comparator)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{name} must be a real number, got {value!r}")
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{name} must be finite, got {value!r}")
    return float(treatment) - float(comparator)


def timing_verdict(*, treatment_arm: str, direct_contrast: dict | None,
                   calendar_band: dict | None = None) -> dict:
    """Form a timing verdict from the DIRECT paired contrast of ``treatment_arm``.

    ``direct_contrast`` must carry ``{"comparator_arm", "delta", "delta_sign"}``
    computed by ``direct_pair_delta`` from the two arms' own real outcomes.
    ``calendar_band`` (where a falsification bar was registered before the
    control existed) is recorded as secondary context only and can never flip
    the status by itself: with no direct contrast the only honest output is
    ``NOT_EVALUABLE_DIRECT_CONTRAST_MISSING``.
    """
    base = {
        "schema": "regime_lab.fp_timing_verdict.v1",
        "treatment_arm": treatment_arm,
        "calendar_band_context": calendar_band,
    }
    if direct_contrast is None:
        return {**base, "status": "NOT_EVALUABLE_DIRECT_CONTRAST_MISSING",
                "reason": ("no direct treatment-minus-comparator contrast supplied; "
                           "a band comparison alone cannot form a verdict (guide 21)") }
    comparator = direct_contrast.get("comparator_arm")
    delta = direct_contrast.get("delta")
    if comparator is None or delta is None:
        return {**base, "status": "NOT_EVALUABLE_DIRECT_CONTRAST_MISSING",
                "comparator_arm": comparator,
                "reason": "direct_contrast lacks comparator_arm and/or a finite delta"}
    sign = direct_contrast.get("delta_sign")
    if sign not in ("treatment_above", "treatment_below"):
        return {**base, "status": "NOT_EVALUABLE_DIRECT_CONTRAST_MISSING",
                "comparator_arm": comparator, "delta": delta,
                "reason": "direct_contrast needs an explicit delta_sign, not an inferred one"}
    if sign == "treatment_below":
        status = "CADENCE_ARTIFACT"
    else:
        status = "SURVIVED_FALSIFICATION"
    return {**base, "status": status, "comparator_arm": comparator, "delta": delta,
            "uncertainty": direct_contrast.get("uncertainty"),
            "note": ("direction only from the direct contrast; strength of evidence "
                     "(significance/equivalence/non-inferiority) is FP08.3/FP-09 work, "
                     "never implied by this status")}
