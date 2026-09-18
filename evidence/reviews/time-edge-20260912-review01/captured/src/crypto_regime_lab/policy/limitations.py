"""L06.6 — what this layer cannot measure, written down before anyone asks.

A response estimate is built from episodes that each started under a declared
initial-state contract, usually flat. A live switch does not. It happens to an
account that is somewhere in the middle of something, and the difference is not
noise around the estimate -- it is a class of risk the estimate has no term for.

Guide L06.6 asks for that to be recorded rather than discovered later, so this
module produces the record instead of leaving it to a reader's goodwill.
"""

from __future__ import annotations

INITIAL_STATE_FLAT = "flat_at_episode_start"
INITIAL_STATE_INHERITED = "inherited_live_position"


def initial_state_contract(kind: str = INITIAL_STATE_FLAT) -> dict:
    return {
        "contract": kind,
        "training_episodes_use": INITIAL_STATE_FLAT,
        "live_switch_uses": INITIAL_STATE_INHERITED,
        "mismatch_is_real": True,
        "why": ("every bank training utility is measured from a declared starting state. A live "
                "switch inherits whatever the account is holding, so the two are not the same "
                "experiment and the difference does not average away"),
    }


def counterfactual_limits() -> dict:
    """The four limits this layer cannot estimate its way out of."""
    return {
        "schema": "crypto_regime_lab.counterfactual_limits.v1",
        "limits": [
            {
                "id": "CF-1",
                "limit": "training utilities start flat; a live switch does not",
                "consequence": ("the estimate answers 'what would this candidate have done from "
                                "flat', which is a different question from 'what happens if I "
                                "switch to it right now, holding what I hold'"),
                "not_captured_by": "response uncertainty",
            },
            {
                "id": "CF-2",
                "limit": "the transition cost is a PROJECTION",
                "consequence": ("realised cost depends on the book at the moment of the switch. "
                                "The projection uses declared fee and slippage rates and cannot "
                                "know the spread it will actually cross"),
                "not_captured_by": "response uncertainty",
            },
            {
                "id": "CF-3",
                "limit": "activation delay is state-dependent",
                "consequence": ("a switch waits for a campaign boundary, and how long that takes "
                                "depends on the very market state that motivated the switch. The "
                                "delay is therefore correlated with the signal, and a symmetric "
                                "error bar cannot represent that"),
                "not_captured_by": "response uncertainty",
            },
            {
                "id": "CF-4",
                "limit": "execution risk is conditional on state",
                "consequence": ("slippage, partial fills and gap risk are worse in exactly the "
                                "regimes where a switch is most tempting. The response estimate "
                                "is built from realised episode outcomes and carries no separate "
                                "term for this"),
                "not_captured_by": "response uncertainty",
            },
        ],
        "deploy_equity_rule": (
            "the deployed account is a single continuous simulation that pays real fills. A "
            "hypothetical curve in which the account resets to flat at every switch -- an 'expert' "
            "curve -- is NOT used as deploy equity, because it silently removes CF-1, CF-3 and "
            "CF-4 at once (guide L06.6)"),
        "why_uncertainty_is_not_enough": (
            "response uncertainty measures how much the CONDITIONAL ESTIMATE would move if the "
            "episodes were different. It does not measure the four limits above, which are "
            "differences between the experiment and the deployment. Widening the error bar would "
            "not represent them; it would only make the same estimate less decisive"),
    }


def expert_curve_check(used_reset_flat_curve: bool) -> dict:
    """A single explicit flag, so the forbidden shortcut cannot be taken silently."""
    return {
        "reset_flat_expert_curve_used_as_deploy_equity": bool(used_reset_flat_curve),
        "permitted": False,
        "detail": ("deploy equity comes from one continuous account. Stitching per-candidate "
                   "curves that each start flat would delete the transition costs and the "
                   "activation delays that make switching expensive (guide L06.6)"),
    }
