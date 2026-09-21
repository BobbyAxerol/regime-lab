"""RA06.7 deployment controller and RA06.8 lock decision (guide section 10).

`request_search` fires only when a CHEAP causal score (computed from
features available WITHOUT calling the optimizer) clears a frozen rule and
cooldown/budget/quality allow -- it must forecast benefit BEFORE search, not
after (guide: "Neu model can biet optimized challenger quality moi quyet
dinh, search da xay ra va phai charge ke ca khong switch. Khong coi cac
searches bi veto la free").

`lock_policy_revision` is the phase's own G06-SCOPE decision: at most ONE
context-policy revision carries to RA-07, or KEEP_BASELINE with a reason --
never multiple winners for RA-07 to keep trying.
"""
from __future__ import annotations

from .ra06_model import AGE_CONTEXT_FEATURES, AGE_ONLY_FEATURES, MIN_SUPPORT_FOR_MODEL_FIT, ridge_predict

#: Frozen BEFORE any real origin is scored (guide: rule frozen, cooldown/
#: budget/quality gate). Switch cost matches the registered pilot economics
#: (guide 3.2: one_way_fee 0.0004 + slippage 0.0001, round-trip in and out
#: of the new position ~ 2*(fee+slippage) per side pair) -- expressed here
#: as a net-return hurdle the CHEAP score must clear before a real search is
#: even requested.
REQUEST_SEARCH_G_THRESHOLD = 0.002  # 20 bps net-of-switch-cost hurdle on the cheap forecast
COOLDOWN_DAYS = 20  # matches RA-06's own origin spacing -- never request more often than origins exist
MIN_QUALITY_STATUS = "OK"


def cheap_causal_score(features: dict, *, beta: list | None, feature_names: tuple) -> dict:
    """The forecast a controller could make WITHOUT calling the optimizer --
    from a FITTED (fully validated) model's coefficients only. If no model
    was validated (insufficient support), this is honestly NOT_APPLICABLE,
    never a number from an unfit model dressed up as a forecast."""
    if beta is None:
        return {"status": "NOT_APPLICABLE_INSUFFICIENT_SUPPORT", "predicted_g": None}
    import numpy as np

    row = [1.0 if name == "intercept" else float(features[name]) for name in feature_names]
    predicted = float(ridge_predict(np.array([row]), np.array(beta))[0])
    return {"status": "OK", "predicted_g": predicted}


def request_search_decision(features: dict, *, beta: list | None, feature_names: tuple,
                            days_since_last_request: float, budget_remaining: int,
                            quality_status: str = MIN_QUALITY_STATUS,
                            threshold: float = REQUEST_SEARCH_G_THRESHOLD,
                            cooldown_days: float = COOLDOWN_DAYS) -> dict:
    score = cheap_causal_score(features, beta=beta, feature_names=feature_names)
    reasons = []
    if score["status"] != "OK":
        reasons.append(score["status"])
    elif score["predicted_g"] < threshold:
        reasons.append(f"cheap forecast {score['predicted_g']:.5f} below threshold {threshold}")
    if days_since_last_request < cooldown_days:
        reasons.append(f"cooldown active ({days_since_last_request}d < {cooldown_days}d)")
    if budget_remaining <= 0:
        reasons.append("search budget exhausted")
    if quality_status != MIN_QUALITY_STATUS:
        reasons.append(f"quality_status {quality_status!r} not {MIN_QUALITY_STATUS!r}")
    request = not reasons
    return {
        "schema": "regime_lab.ra06_request_search_decision.v1",
        "cheap_score": score, "request_search": request, "veto_reasons": reasons,
        "note": ("a vetoed request still means no search ran and nothing is charged here -- the "
                "charge-even-if-vetoed rule applies once a search DID run and its quality was "
                "consulted before deciding; that path is not exercised by a clean veto"),
    }


def lock_policy_revision(model_ladder: dict, *, min_support: int = MIN_SUPPORT_FOR_MODEL_FIT) -> dict:
    """G06-SCOPE: lock AT MOST ONE context-policy revision, or KEEP_BASELINE
    with a reason. Primary contribution (guide 10.6) is AGE_CONTEXT vs
    AGE_ONLY at equal budget/admission/execution -- never AGE_CONTEXT vs the
    slow calendar alone."""
    if model_ladder["status"] == "INSUFFICIENT_SUPPORT":
        return {
            "schema": "regime_lab.ra06_lock_decision.v1", "decision": "KEEP_BASELINE",
            "reason": (f"support={model_ladder['support']} below the registered floor "
                      f"min_required={model_ladder['min_required']}; guide 10.3's own warning "
                      "that a feasibility-pilot N is not enough to trust a fitted model applies "
                      "literally here -- no context-policy revision is locked"),
            "reference_policy_unchanged": "current JM/M0 timing policy (guide 10.5)",
            "carries_to_ra07": None,
        }
    contribution = model_ladder.get("primary_contribution_loo_mse_reduction")
    if contribution is None or contribution <= 0:
        return {
            "schema": "regime_lab.ra06_lock_decision.v1", "decision": "KEEP_BASELINE",
            "reason": (f"AGE_CONTEXT's inner-CV MSE did not improve over AGE_ONLY "
                      f"(reduction={contribution}) at equal budget/admission/execution"),
            "reference_policy_unchanged": "current JM/M0 timing policy (guide 10.5)",
            "carries_to_ra07": None,
        }
    return {
        "schema": "regime_lab.ra06_lock_decision.v1", "decision": "LOCK_AGE_CONTEXT",
        "reason": (f"AGE_CONTEXT's inner-CV MSE improved over AGE_ONLY by {contribution} at "
                  "equal budget/admission/execution"),
        "reference_policy_unchanged": None,
        "carries_to_ra07": {
            "revision": "AGE_CONTEXT", "feature_names": list(AGE_CONTEXT_FEATURES),
            "beta": model_ladder["age_context"]["full_sample_beta"],
            "compared_against": "AGE_ONLY", "compared_feature_names": list(AGE_ONLY_FEATURES),
        },
        "no_auto_promotion_note": ("a positive inner score alone does not auto-promote this "
                                   "revision to a deployed policy -- guide 10.7: the actual "
                                   "policy is evaluated independently in RA-07, and this run's "
                                   "history stays separate from RA-05's"),
    }
