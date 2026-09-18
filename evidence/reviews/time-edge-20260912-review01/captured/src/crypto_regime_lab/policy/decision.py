"""L06.4 / guide 9.3 — the decision state machine and the transition cost.

The switch rule is deliberately conservative (guide 9.3):

    delta_shrunk - z_alpha * SE  >  C_transition + delta

Three properties of it are load-bearing.

**There is an inaction region.** Between "clearly worse" and "clearly better
after costs" the answer is KEEP_INCUMBENT. A policy without that region churns on
noise, and the churn is paid in real fees.

**Seven decisions, not two.** "Did not switch" hides four different situations:
nothing was supported, the data was bad, the state was novel, or the campaign was
still open. Guide 9.3 names them separately because they call for different
responses.

**C_transition decides, it never charges.** The estimate exists so the selector
can refuse a marginal switch. The account is charged by the engine, from actual
fills and fees. Subtracting the estimate from realised PnL as well would bill the
same cost twice.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

KEEP_INCUMBENT = "KEEP_INCUMBENT"
SWITCH_READY = "SWITCH_READY"
WAIT_CAMPAIGN_BOUNDARY = "WAIT_CAMPAIGN_BOUNDARY"
REFRESH_BANK_REQUESTED = "REFRESH_BANK_REQUESTED"
FALLBACK_DATA = "FALLBACK_DATA"
FALLBACK_NOVEL_STATE = "FALLBACK_NOVEL_STATE"
NO_SUPPORTED_CANDIDATE = "NO_SUPPORTED_CANDIDATE"
#: Guide 9.3 lists these as DISTINCT decisions. Collapsing them into
#: switched/not-switched destroys the reason, which is the useful part.
DECISIONS = (KEEP_INCUMBENT, SWITCH_READY, WAIT_CAMPAIGN_BOUNDARY, REFRESH_BANK_REQUESTED,
             FALLBACK_DATA, FALLBACK_NOVEL_STATE, NO_SUPPORTED_CANDIDATE)

#: Registered before any decision is taken.
Z_ALPHA = 1.0
#: The margin above transition cost a challenger must clear. Not a p-value.
DELTA_MARGIN = 0.0002
MIN_SWITCH_SPACING = pd.Timedelta(days=7)


@dataclass(frozen=True)
class TransitionCost:
    """Projected cost of moving from one parameter version to another.

    In the SAME units as the utility -- net return on the fixed allocation over
    the response horizon -- because comparing a cost in basis points with a
    utility in return units is the easiest way to get a switch rule backwards.
    """

    projected_turnover: float
    fee_rate: float
    slippage_rate: float
    residual_handling: float
    total: float
    units: str = "net return on the fixed allocation, same horizon as the utility"

    def as_record(self) -> dict:
        return {
            "projected_turnover": self.projected_turnover, "fee_rate": self.fee_rate,
            "slippage_rate": self.slippage_rate, "residual_handling": self.residual_handling,
            "total": self.total, "units": self.units,
            "charging_rule": ("this estimate is used to DECIDE. The account is charged by the "
                              "engine from actual fills and fees; subtracting this from realised "
                              "PnL as well would bill the same cost twice (guide 9.3)"),
        }


def transition_cost(projected_turnover: float, *, fee_rate: float, slippage_rate: float,
                    residual_handling: float = 0.0) -> TransitionCost:
    """Guide 9.3: projected turnover x (fees + slippage), plus residual handling."""
    if projected_turnover < 0:
        raise ValueError("projected turnover cannot be negative")
    total = projected_turnover * (fee_rate + slippage_rate) + residual_handling
    return TransitionCost(projected_turnover, fee_rate, slippage_rate, residual_handling,
                          float(total))


@dataclass
class Decision:
    """One selection decision, with everything needed to re-derive it."""

    selection_id: str
    decision_time: pd.Timestamp
    decision: str
    incumbent_id: str
    challenger_id: str | None
    reason: str
    delta_shrunk: float | None = None
    standard_error: float | None = None
    lower_bound: float | None = None
    transition_cost: float | None = None
    threshold: float | None = None
    response_id: str | None = None
    supporting_episodes: list[dict] | None = None
    data_cutoff: str | None = None
    bank_cutoff: str | None = None
    model_version: str | None = None
    #: guide 13.4 — the minimum evidence every decision has to carry, including a
    #: no-switch. Without the proposal/guard pair a reader cannot tell "no
    #: challenger was better" from "a challenger WAS better and a gate refused
    #: it", and the difference is the entire content of an inaction region.
    proposal_before_guard: dict | None = None
    decision_after_guard: dict | None = None
    action_type: str = "none"
    incumbent_params: dict | None = None
    challenger_params: dict | None = None
    campaign_version_before: str | None = None
    campaign_version_after: str | None = None

    def as_record(self) -> dict:
        return {
            "selection_id": self.selection_id, "decision_time": str(self.decision_time),
            "decision": self.decision, "incumbent_id": self.incumbent_id,
            "challenger_id": self.challenger_id, "reason": self.reason,
            "delta_shrunk": self.delta_shrunk, "standard_error": self.standard_error,
            "lower_bound": self.lower_bound, "transition_cost": self.transition_cost,
            "threshold": self.threshold, "response_id": self.response_id,
            "supporting_episodes": self.supporting_episodes or [],
            "data_cutoff": self.data_cutoff, "bank_cutoff": self.bank_cutoff,
            "model_version": self.model_version,
            # ---- guide 13.4
            "proposal_before_guard": self.proposal_before_guard,
            "decision_after_guard": self.decision_after_guard,
            "action_type": self.action_type,
            "incumbent_params": self.incumbent_params,
            "challenger_params": self.challenger_params,
            "requested_at": str(self.decision_time),
            "ready_at": None,
            "effective_at": None,
            "activation_timestamps_note": (
                "requested_at is this decision. ready_at and effective_at belong to the "
                "ACTIVATION, which is a separate clock and is recorded per activation in "
                "configs/parameter_activation_tape.json; they are null here rather than copied, "
                "because a decision that never activated has neither"),
            "campaign_version_before": self.campaign_version_before,
            "campaign_version_after": self.campaign_version_after,
            "rule": ("switch only when delta_shrunk - z*SE > C_transition + delta AND the quality, "
                     "support and capacity gates pass. Between those bounds the answer is "
                     "KEEP_INCUMBENT: an inaction region (guide 9.3)"),
        }


def decide(*, selection_id: str, decision_time: pd.Timestamp, incumbent_id: str,
           estimates: list, costs: dict, quality_status: str,
           campaign_open: bool, last_switch_at: pd.Timestamp | None,
           bank_adequate: bool = True,
           warm_candidates: set | None = None,
           z_alpha: float = Z_ALPHA, delta: float = DELTA_MARGIN,
           min_spacing: pd.Timedelta = MIN_SWITCH_SPACING,
           data_cutoff: str | None = None, bank_cutoff: str | None = None,
           model_version: str | None = None,
           incumbent_params: dict | None = None,
           candidate_params: dict | None = None,
           campaign_version: str | None = None) -> Decision:
    """Produce one decision. The order of the checks is the policy.

    Data quality is checked before anything else: an estimate built on missing
    inputs is not a weak signal, it is not a signal. Novelty comes next, because a
    context outside the model's training support means the similarity weights are
    extrapolating. Only then does the economic comparison run at all.
    """
    def _mk(decision, reason, *, gate=None, proposal=None, **kw):
        challenger = kw.get("challenger_id")
        switched = decision == SWITCH_READY
        return Decision(
            selection_id=selection_id, decision_time=pd.Timestamp(decision_time),
            decision=decision, incumbent_id=incumbent_id, reason=reason,
            data_cutoff=data_cutoff, bank_cutoff=bank_cutoff,
            model_version=model_version,
            proposal_before_guard=proposal or {
                "status": "NO_PROPOSAL",
                "why": reason,
                "blocked_at": gate,
                "meaning": ("the economics never ran: this decision was settled before any "
                            "challenger could be compared")},
            decision_after_guard={
                "decision": decision,
                "binding_gate": gate,
                "changed_the_proposal": bool(
                    proposal and proposal.get("clears_the_economics") and not switched),
                "meaning": ("`changed_the_proposal` true means a challenger DID clear the "
                            "economics and a later gate refused it. That is a different result "
                            "from no challenger clearing, and only this pair distinguishes them "
                            "(guide 13.4)")},
            # this policy proposes parameter switches only. A risk-only action
            # would be a different action_type, and guide 13.4 forbids calling one
            # a parameter switch -- so the field is always present and is `none`
            # wherever nothing was deployed.
            action_type="parameter_switch" if switched else "none",
            incumbent_params=dict(incumbent_params) if incumbent_params else None,
            challenger_params=(dict((candidate_params or {}).get(challenger, {}))
                               or None) if challenger else None,
            campaign_version_before=campaign_version,
            campaign_version_after=(challenger if switched else campaign_version),
            **kw)

    if quality_status == "MISSING_DATA":
        return _mk(FALLBACK_DATA, "regime inputs are missing; no conditional estimate is "
                                  "available and the incumbent continues",
                   gate="DATA_QUALITY", challenger_id=None)
    if quality_status in ("UNKNOWN_STATE", "STALE_MODEL", "UNMAPPED_REFIT_STATE"):
        return _mk(FALLBACK_NOVEL_STATE,
                   f"regime provider reports {quality_status}; the similarity weights would be "
                   "extrapolating outside the training support, so no switch is proposed",
                   gate="NOVEL_STATE", challenger_id=None)

    if not bank_adequate:
        return _mk(REFRESH_BANK_REQUESTED,
                   "the bank has no admissible challenger with local evidence; a refresh is "
                   "REQUESTED on its own clock and the incumbent keeps running meanwhile",
                   gate="BANK_ADEQUACY", challenger_id=None)

    supported = [e for e in estimates if e.status == "SUPPORTED"]
    if not supported:
        statuses = sorted({e.status for e in estimates}) or ["none"]
        return _mk(NO_SUPPORTED_CANDIDATE,
                   f"no candidate cleared the support gate (statuses {statuses}); the quality gate "
                   "is allowed to reject everything and a best-of-bad is not forced into a trade",
                   gate="SUPPORT", challenger_id=None)

    def _lower(est):
        se = est.standard_error if est.standard_error is not None else 0.0
        return (est.delta_shrunk or 0.0) - z_alpha * se

    best = max(supported, key=lambda e: (_lower(e), e.candidate_id))
    cost = costs.get(best.candidate_id)
    cost_total = cost.total if cost is not None else 0.0
    threshold = cost_total + delta
    lower = _lower(best)

    common = {
        "challenger_id": best.candidate_id, "delta_shrunk": best.delta_shrunk,
        "standard_error": best.standard_error, "lower_bound": lower,
        "transition_cost": cost_total, "threshold": threshold,
        "response_id": best.response_id, "supporting_episodes": best.supporting_episodes,
    }

    proposal = {
        "status": "PROPOSED",
        "challenger_id": best.candidate_id,
        "delta_shrunk": best.delta_shrunk,
        "standard_error": best.standard_error,
        "lower_bound": lower,
        "transition_cost": cost_total,
        "threshold": threshold,
        "clears_the_economics": bool(lower > threshold),
        "supporting_episodes": len(best.supporting_episodes or []),
        "meaning": ("what the ECONOMICS proposed, before any capacity or timing gate ran. "
                    "Recorded for a no-switch too (guide 13.4)"),
    }
    common["proposal"] = proposal

    if lower <= threshold:
        return _mk(KEEP_INCUMBENT,
                   f"the best challenger's conservative lower bound {lower:.6g} does not clear "
                   f"transition cost + margin {threshold:.6g}. This is the inaction region, not a "
                   "failure to find anything", gate="ECONOMICS", **common)

    if warm_candidates is not None and best.candidate_id not in warm_candidates:
        return _mk(WAIT_CAMPAIGN_BOUNDARY,
                   f"{best.candidate_id} clears the economics but its indicators are not warm "
                   "yet; switching now would act on values computed from a cold start (T51)",
                   gate="INDICATOR_WARMTH", **common)

    if last_switch_at is not None and \
            pd.Timestamp(decision_time) - pd.Timestamp(last_switch_at) < min_spacing:
        return _mk(KEEP_INCUMBENT,
                   f"minimum spacing of {min_spacing} since the last switch has not elapsed; "
                   "spacing exists so a marginal estimate cannot churn the account",
                   gate="SWITCH_SPACING", **common)

    if campaign_open:
        return _mk(WAIT_CAMPAIGN_BOUNDARY,
                   "the challenger clears the economics but a campaign is still open; the open "
                   "trade stays protected by the parameters it entered with and the switch waits "
                   "for a flat or terminal boundary (guide 9.5)",
                   gate="CAMPAIGN_BOUNDARY", **common)

    return _mk(SWITCH_READY,
               f"lower bound {lower:.6g} clears transition cost + margin {threshold:.6g} with "
               f"support from {len(best.supporting_episodes or [])} episodes",
               gate=None, **common)


def policy_spec() -> dict:
    """The registered decision policy, in one place."""
    return {
        "schema": "crypto_regime_lab.policy_spec.v1",
        "decisions": list(DECISIONS),
        "switch_rule": "delta_shrunk - z_alpha*SE > C_transition + delta",
        "z_alpha": Z_ALPHA, "delta_margin": DELTA_MARGIN,
        "min_switch_spacing": str(MIN_SWITCH_SPACING),
        "inaction_region": True,
        "quality_gate_may_reject_everything": True,
        "check_order": ["data quality", "novel/stale state", "bank adequacy", "support",
                        "economics vs transition cost", "indicator warmth", "switch spacing",
                        "campaign boundary"],
        "z_alpha_note": ("z_alpha is a conservative decision heuristic. It is NOT a confidence "
                         "guarantee: with a handful of episodes and a model whose assumptions may "
                         "be wrong, an arbitrary Gaussian 95% label would be false precision "
                         "(guide 9.3)"),
        "cost_charging": ("C_transition decides; the engine charges. The estimate is never "
                          "subtracted from realised PnL as well (guide 9.3)"),
        "zero_switches_is_valid": ("a technical pass does not require switches. Zero switches "
                                   "because no challenger cleared the bar is a valid result "
                                   "(L06 exit)"),
    }


def _verified_over(predicate, population: list, what: str) -> dict:
    """A verdict that carries its own denominator.

    ``all(...)`` over an empty population is True, and reads exactly like a
    verified claim. `every_switch_has_supporting_episodes` was reported True
    across a run with ZERO switches and quoted as evidence that every switch
    carried its evidence. It carried nothing, because there was nothing.
    """
    checked = len(population)
    return {
        "holds": all(predicate(item) for item in population),
        "checked": checked,
        "vacuous": checked == 0,
        "reading": (f"no {what} occurred, so this verifies nothing" if checked == 0
                    else f"verified over {checked} {what}"),
    }


def summarize_ledger(decisions: list) -> dict:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.decision] = counts.get(decision.decision, 0) + 1
    switches = counts.get(SWITCH_READY, 0)
    switch_rows = [d for d in decisions if d.decision == SWITCH_READY]
    reason = _verified_over(lambda d: bool(d.reason), decisions, "decisions")
    supported = _verified_over(lambda d: bool(d.supporting_episodes), switch_rows, "switches")
    cutoffs = _verified_over(
        lambda d: d.data_cutoff is not None and d.bank_cutoff is not None,
        decisions, "decisions")
    return {
        "schema": "crypto_regime_lab.decision_ledger.v1",
        "decisions": len(decisions),
        "counts": dict(sorted(counts.items())),
        "switch_count": switches,
        "every_decision_has_a_reason": reason["holds"],
        "every_switch_has_supporting_episodes": supported["holds"],
        "every_decision_records_its_cutoffs": cutoffs["holds"],
        "verdicts": {
            "every_decision_has_a_reason": reason,
            "every_switch_has_supporting_episodes": supported,
            "every_decision_records_its_cutoffs": cutoffs,
        },
        "vacuous_verdicts": sorted(
            name for name, v in (("every_decision_has_a_reason", reason),
                                 ("every_switch_has_supporting_episodes", supported),
                                 ("every_decision_records_its_cutoffs", cutoffs))
            if v["vacuous"]),
        "distinct_decisions_used": sorted(counts),
        "ledger": [d.as_record() for d in decisions],
    }
