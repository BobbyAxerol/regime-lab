"""L08.3 / guide 10.2 — the seven controls, and what each one would explain away.

A control is not a variant. Each one exists because a specific alternative
explanation would produce the same headline as the method, and the guide is
explicit that none may be dropped for beating the proposal.

The placebo is the one that is easy to fake. A random label sequence switches
far more often than a real regime tape, so a placebo arm would trade constantly
and lose on costs alone -- and "the method beat a strawman" would look like
evidence. Matching dwell and switch frequency is what makes the comparison mean
anything, and generating the placebo from PAST statistics only is what keeps it
from smuggling the future in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class ControlError(ValueError):
    """Raised when a control would not control for what it claims to."""


#: control -> the alternative explanation it removes
CONTROLS = {
    "RISK_ONLY": "the benefit is exposure timing, not parameter selection",
    "CALENDAR_MATCHED": "the benefit is extra search compute, not better timing",
    "BANK_CALENDAR": "the benefit is having a bank at all, not switching within it on regime",
    "STATE_PLACEBO": "the benefit is switching on ANY persistent signal, not on this one",
    "DELAYED_STATE": "the benefit disappears under a realistic observation delay",
    "EXPOST_DIAGNOSTIC": "how much of the ceiling is reachable only with hindsight",
    "USER_PRESET_REFERENCE": "the supplied presets already do as well, retrospectively",
}


@dataclass(frozen=True)
class DwellProfile:
    """The switching behaviour a placebo has to imitate."""

    observations: int
    switches: int
    mean_dwell: float
    state_shares: dict

    @property
    def switch_rate(self) -> float:
        return self.switches / max(self.observations - 1, 1)

    def as_record(self) -> dict:
        return {"observations": self.observations, "switches": self.switches,
                "mean_dwell_observations": self.mean_dwell,
                "switch_rate": self.switch_rate, "state_shares": self.state_shares}


def dwell_profile(states: list) -> DwellProfile:
    states = list(states)
    if len(states) < 2:
        raise ControlError("a dwell profile needs at least two observations")
    switches = sum(1 for a, b in zip(states, states[1:]) if a != b)
    counts: dict = {}
    for state in states:
        counts[str(state)] = counts.get(str(state), 0) + 1
    return DwellProfile(
        observations=len(states), switches=switches,
        mean_dwell=len(states) / max(switches + 1, 1),
        state_shares={k: v / len(states) for k, v in sorted(counts.items())})


def placebo_states(profile: DwellProfile, *, length: int, seed: int) -> list[int]:
    """A fake tape with the SAME dwell and switch frequency, built from past stats only.

    ``profile`` must come from a window that has already closed. Nothing about
    the placebo depends on the period it will be used in: it reproduces a rate
    and a set of shares, not a sequence. Shuffling the real future labels would
    give a placebo that knows exactly when the market turned, which guide 10.2
    forbids in as many words.
    """
    if length < 2:
        raise ControlError("a placebo tape needs at least two observations")
    rng = np.random.default_rng(seed)
    labels = sorted(profile.state_shares)
    weights = np.array([profile.state_shares[k] for k in labels], dtype=float)
    weights = weights / weights.sum()

    out = [int(rng.choice(len(labels), p=weights))]
    for _ in range(length - 1):
        if rng.random() < profile.switch_rate:
            alternatives = [i for i in range(len(labels)) if i != out[-1]]
            share = np.array([profile.state_shares[labels[i]] for i in alternatives], dtype=float)
            out.append(int(rng.choice(alternatives, p=share / share.sum())))
        else:
            out.append(out[-1])
    return out


def placebo_fidelity(real: list, fake: list, *, tolerance: float = 0.35) -> dict:
    """Did the placebo actually match? A strawman placebo invalidates the control."""
    real_profile, fake_profile = dwell_profile(real), dwell_profile(fake)
    real_rate = real_profile.switch_rate
    ratio = (fake_profile.switch_rate / real_rate) if real_rate else float("inf")
    matched = abs(ratio - 1.0) <= tolerance
    return {
        "schema": "crypto_regime_lab.placebo_fidelity.v1",
        "real": real_profile.as_record(),
        "placebo": fake_profile.as_record(),
        "switch_rate_ratio": ratio,
        "tolerance": tolerance,
        "matched": bool(matched),
        "why_it_matters": ("a placebo that switches far more often loses on transaction costs "
                           "alone, and beating it would say nothing about the states. The "
                           "control is only a control while the rates match (guide 10.2)"),
    }


def delayed_states(emissions: list[dict], *, observations: int = 1) -> list[dict]:
    """DELAYED_STATE — push availability out by a registered number of observations.

    The delay is applied to ``available_at``, never to ``observed_at``: the world
    did not change, only when a policy could act on it.
    """
    if observations < 1:
        raise ControlError("a delay of zero observations is not a delay")
    out = []
    for index, record in enumerate(emissions):
        source = emissions[max(index - observations, 0)]
        out.append({**record,
                    "state_id": source["state_id"],
                    "state_namespace": source["state_namespace"],
                    "delayed_by_observations": observations,
                    "delay_is_on_availability_not_on_the_world": True})
    return out


def expost_labels(states: list, *, horizon_returns: list[float]) -> dict:
    """EXPOST_DIAGNOSTIC — the ceiling, computed WITH hindsight and marked unusable.

    This is the one control whose output must never reach a tradeable result. It
    exists to say how much of the available gain needed the future to capture,
    which is a useful number and a forbidden strategy.
    """
    if len(states) != len(horizon_returns):
        raise ControlError("hindsight labels need one forward return per observation")
    by_state: dict = {}
    for state, forward in zip(states, horizon_returns):
        by_state.setdefault(str(state), []).append(float(forward))
    best = {k: float(np.mean(v)) for k, v in by_state.items()}
    return {
        "schema": "crypto_regime_lab.expost_diagnostic.v1",
        "mean_forward_return_by_state": best,
        "best_state": max(best, key=best.get) if best else None,
        "eligible_for_a_trade_result": False,
        "rule": ("these labels are computed from returns that had not happened at decision time. "
                 "They bound what was theoretically available; they are never an arm, never a "
                 "control that trades, and never enter a reported PnL (guide 10.2)"),
    }


def risk_only_scaler(states: list, *, train_states: list, train_returns: list[float],
                     floor: float = 0.5, cap: float = 1.0) -> list[float]:
    """RISK_ONLY — same context, size only, parameters untouched.

    The scale for a state is calibrated on TRAINING observations of that state
    and clipped, so this control cannot beat the method by levering up on
    information the method does not have. A state never seen in training gets
    1.0 rather than an extrapolation.
    """
    if len(train_states) != len(train_returns):
        raise ControlError("calibration needs one return per training observation")
    volatility: dict = {}
    for state, value in zip(train_states, train_returns):
        volatility.setdefault(str(state), []).append(float(value))
    scales = {}
    overall = float(np.std([v for values in volatility.values() for v in values]) or 1.0)
    for state, values in volatility.items():
        own = float(np.std(values)) if len(values) > 1 else overall
        scales[state] = float(np.clip(overall / own if own > 0 else 1.0, floor, cap))
    return [scales.get(str(state), 1.0) for state in states]


def control_registry() -> dict:
    return {
        "schema": "crypto_regime_lab.control_registry.v1",
        "controls": CONTROLS,
        "count": len(CONTROLS),
        "retention_rule": ("no control is dropped because it beats the proposed method "
                           "(guide 10.2)"),
        "staging_rule": ("controls are added in stages rather than as a full Cartesian product "
                         "of every combination (guide 10.2)"),
    }
