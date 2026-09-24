"""FP-08 decision rules (guide FP08.5's own registered vocabulary table).
Every disposition returned here is one of the six exact guide-registered
labels -- never an invented stronger or weaker one (FP08-G-VERDICT checks
this structurally).

Precedence (highest first, mirrors CLAUDE.md's own established precedence
discipline for conclusion levels): technical invalidity beats everything;
a degenerate contrast (C==B via fallback) is reported as the mechanism
question it actually is, not judged on a CI that cannot mean anything
independent of B; only then does the CI-vs-threshold table apply.
"""
from __future__ import annotations

RETENTION_CONTRIBUTION = "Retention contribution trong scope"
ECONOMIC_OUTPERFORMANCE = "Economic outperformance trong scope"
INCONCLUSIVE = "Inconclusive effect/support"
NO_MEANINGFUL_IMPROVEMENT = "No meaningful improvement tại threshold đã thử"
NOT_EVALUABLE = "Not evaluable"
CONTEXT_NOT_EXERCISED = "Context mechanism chưa được exercise đủ"

REGISTERED_VOCABULARY = (RETENTION_CONTRIBUTION, ECONOMIC_OUTPERFORMANCE, INCONCLUSIVE,
                         NO_MEANINGFUL_IMPROVEMENT, NOT_EVALUABLE, CONTEXT_NOT_EXERCISED)


def classify_disposition(*, claim: str, claim_type: str, technical_valid: bool,
                         degenerate: bool = False, contrast: dict | None = None,
                         delta_threshold: float | None = None,
                         risk_safeguard_met: bool | None = None) -> dict:
    """``claim_type`` is ``'decay_reduction'`` or ``'economic_outperformance'``
    -- selects which of the two positive dispositions applies when the
    evidence clears its threshold. ``contrast`` is a paired-contrast dict
    (status/estimate/ci95_basic, e.g. from fp.locked_study.paired_contrast).
    """
    if claim_type not in ("decay_reduction", "economic_outperformance"):
        raise ValueError(f"unknown claim_type: {claim_type}")

    if not technical_valid:
        return {"claim": claim, "disposition": NOT_EVALUABLE,
               "reason": "technical validity check failed for this claim"}
    if degenerate:
        return {"claim": claim, "disposition": CONTEXT_NOT_EXERCISED,
               "reason": "the underlying contrast is degenerate (C==B via fallback) -- the "
                        "context mechanism was never exercised, so this is not a genuine "
                        "effect measurement"}
    if contrast is None or contrast.get("status") != "ESTIMATED":
        return {"claim": claim, "disposition": INCONCLUSIVE,
               "reason": f"contrast status is {contrast.get('status') if contrast else None!r}, "
                        "not ESTIMATED -- no CI to judge against a threshold"}
    if delta_threshold is None:
        return {"claim": claim, "disposition": INCONCLUSIVE,
               "reason": "no registered threshold exists for this claim (guide 10.7: report "
                        "descriptive rather than invent one) -- CI alone cannot support a "
                        "stronger disposition"}

    ci = contrast.get("ci95_basic")
    if not ci:
        return {"claim": claim, "disposition": INCONCLUSIVE, "reason": "contrast has no CI"}
    lower, upper = ci[0], ci[1]

    if lower > delta_threshold:
        if claim_type == "decay_reduction":
            if risk_safeguard_met is not True:
                return {"claim": claim, "disposition": INCONCLUSIVE,
                       "reason": "CI clears the decay threshold but the utility/risk safeguard "
                                "is not confirmed met -- guide FP08.5 requires BOTH"}
            return {"claim": claim, "disposition": RETENTION_CONTRIBUTION,
                   "reason": f"ci95_lower={lower} exceeds the registered threshold "
                            f"{delta_threshold}, and the utility/risk safeguard is met"}
        return {"claim": claim, "disposition": ECONOMIC_OUTPERFORMANCE,
               "reason": f"ci95_lower={lower} exceeds the registered threshold {delta_threshold}"}
    if upper < delta_threshold:
        return {"claim": claim, "disposition": NO_MEANINGFUL_IMPROVEMENT,
               "reason": f"ci95_upper={upper} is below the registered threshold "
                        f"{delta_threshold} -- the CI is narrow enough to exclude a "
                        "meaningful effect at this threshold"}
    return {"claim": claim, "disposition": INCONCLUSIVE,
           "reason": f"CI [{lower}, {upper}] straddles the registered threshold "
                    f"{delta_threshold} -- too wide to support a stronger disposition"}
