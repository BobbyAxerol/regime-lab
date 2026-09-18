"""L04.4 — the transparent robust score of guide 7.3.

    G(theta)  = Q_0.25 over inner episodes e of U(theta, e)
    F(theta)  = median_e Q_0.75 over neighbours u in N(theta) of
                max(0, U(theta, e) - U(u, e))
    R(theta)  = G(theta) - lambda_F * F(theta)
    P_survive = #{(u,e) : quality and risk gates pass}
                / #{(u,e) : valid economic evaluation}

F is a REGRET-AGAINST-NEIGHBOURS term: it is large exactly when a point beats the
points around it, which is what a sharp peak looks like. R therefore rewards a
good score that its neighbourhood also achieves.

Two rules the guide states plainly and this module enforces:
  * a flat but NEGATIVE region fails economic quality — flatness is not the goal;
  * runtime failures leave the panel incomplete, and an incomplete panel cannot
    support a stability claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Selection hyperparameters. Chosen on development, never universal constants.
DEFAULT_LAMBDA_F = 1.0
DEFAULT_G_QUANTILE = 0.25
DEFAULT_F_QUANTILE = 0.75
DEFAULT_SURVIVE_THRESHOLD = 0.60


@dataclass
class EpisodePanel:
    """U(theta, e) for one candidate across inner episodes, plus evaluation status.

    ``utilities`` holds a value per episode; ``failed_episodes`` names episodes
    whose evaluation could not complete. A failed episode is NOT a zero utility.
    """

    candidate_id: str
    params: dict
    utilities: dict[str, float] = field(default_factory=dict)
    failed_episodes: dict[str, str] = field(default_factory=dict)
    gate_pass: dict[str, bool] = field(default_factory=dict)
    structurally_invalid: bool = False
    invalid_reason: str | None = None

    @property
    def complete(self) -> bool:
        return not self.failed_episodes and not self.structurally_invalid

    def episodes(self) -> list[str]:
        return sorted(self.utilities)

    def as_record(self) -> dict:
        return {
            "candidate_id": self.candidate_id, "params": self.params,
            "episodes_evaluated": len(self.utilities),
            "episodes_failed": sorted(self.failed_episodes),
            "complete": self.complete,
            "structurally_invalid": self.structurally_invalid,
            "invalid_reason": self.invalid_reason,
        }


@dataclass
class RobustScore:
    candidate_id: str
    params: dict
    g: float | None
    f: float | None
    r: float | None
    p_survive: float | None
    episodes_used: int
    neighbours_used: int
    complete_panel: bool
    status: str
    reason: str | None = None

    def as_record(self) -> dict:
        return self.__dict__.copy()


def _quantile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q))


def score_candidate(panel: EpisodePanel, neighbours: list[EpisodePanel], *,
                    lambda_f: float = DEFAULT_LAMBDA_F,
                    g_quantile: float = DEFAULT_G_QUANTILE,
                    f_quantile: float = DEFAULT_F_QUANTILE,
                    min_quality: float = 0.0,
                    survive_threshold: float = DEFAULT_SURVIVE_THRESHOLD) -> RobustScore:
    """Score one candidate against its own episodes and its neighbourhood."""
    if panel.structurally_invalid:
        return RobustScore(panel.candidate_id, panel.params, None, None, None, None, 0, 0,
                           False, "STRUCTURALLY_INVALID",
                           panel.invalid_reason or "excluded; not counted as bad performance")
    if not panel.utilities:
        return RobustScore(panel.candidate_id, panel.params, None, None, None, None, 0, 0,
                           False, "NO_EVALUATION", "no episode produced a valid evaluation")

    episodes = panel.episodes()
    g = _quantile([panel.utilities[e] for e in episodes], g_quantile)

    # F: per episode, the 0.75 quantile of this candidate's regret over neighbours.
    per_episode_regret: list[float] = []
    neighbours_used = 0
    for episode in episodes:
        regrets = []
        for neighbour in neighbours:
            if neighbour.structurally_invalid or episode not in neighbour.utilities:
                continue
            regrets.append(max(0.0, panel.utilities[episode] - neighbour.utilities[episode]))
        if regrets:
            neighbours_used = max(neighbours_used, len(regrets))
            per_episode_regret.append(_quantile(regrets, f_quantile))
    f = float(np.median(per_episode_regret)) if per_episode_regret else None

    # P_survive over every (neighbour, episode) pair that produced a valid evaluation.
    valid_pairs = 0
    passing_pairs = 0
    for member in [panel, *neighbours]:
        if member.structurally_invalid:
            continue
        for episode, value in member.utilities.items():
            valid_pairs += 1
            gate = member.gate_pass.get(episode)
            if gate is None:
                gate = value > min_quality
            passing_pairs += int(bool(gate))
    p_survive = (passing_pairs / valid_pairs) if valid_pairs else None

    r = None if f is None else g - lambda_f * f
    complete = panel.complete and all(n.complete for n in neighbours if not n.structurally_invalid)

    if f is None:
        status, reason = "INSUFFICIENT_LOCAL_EVIDENCE", "no neighbour shared an episode with this candidate"
    elif not complete:
        status, reason = "INCOMPLETE_PANEL", (
            "a runtime failure left the local panel incomplete; a stability claim is not available")
    elif g <= min_quality:
        status, reason = "FAILS_ECONOMIC_QUALITY", (
            f"G={g:.6f} is not above the minimum quality {min_quality}; a flat region that is "
            "negative is still rejected")
    elif p_survive is not None and p_survive < survive_threshold:
        status, reason = "FAILS_SURVIVAL", (
            f"P_survive={p_survive:.3f} below the registered threshold {survive_threshold}")
    else:
        status, reason = "ELIGIBLE", None

    return RobustScore(panel.candidate_id, panel.params, g, f, r, p_survive,
                       len(episodes), neighbours_used, complete, status, reason)


def score_all(panels: dict[str, EpisodePanel], neighbourhoods: dict[str, list[str]],
              **kwargs) -> dict:
    """Score every candidate; the incumbent is scored on the same budget."""
    scores: dict[str, RobustScore] = {}
    for candidate_id, panel in panels.items():
        neighbours = [panels[n] for n in neighbourhoods.get(candidate_id, []) if n in panels]
        scores[candidate_id] = score_candidate(panel, neighbours, **kwargs)
    eligible = [s for s in scores.values() if s.status == "ELIGIBLE"]
    return {
        "schema": "crypto_regime_lab.robust_score.v1",
        "formula": {
            "G": f"Q_{kwargs.get('g_quantile', DEFAULT_G_QUANTILE)} of U over inner episodes",
            "F": f"median_e Q_{kwargs.get('f_quantile', DEFAULT_F_QUANTILE)} of max(0, U(theta,e) - U(u,e))",
            "R": "G - lambda_F * F",
            "P_survive": "passing (u, e) pairs / (u, e) pairs with a valid economic evaluation",
        },
        "p_survive_scope": (
            "u ranges over the LOCAL PANEL: the candidate itself plus its neighbours. A "
            "structurally invalid point contributes to neither numerator nor denominator; a "
            "valid point that lost money contributes to the denominator only."),
        "hyperparameters": {
            "lambda_f": kwargs.get("lambda_f", DEFAULT_LAMBDA_F),
            "g_quantile": kwargs.get("g_quantile", DEFAULT_G_QUANTILE),
            "f_quantile": kwargs.get("f_quantile", DEFAULT_F_QUANTILE),
            "min_quality": kwargs.get("min_quality", 0.0),
            "survive_threshold": kwargs.get("survive_threshold", DEFAULT_SURVIVE_THRESHOLD),
            "note": "selection hyperparameters chosen on development; not universal constants",
        },
        "scores": {k: v.as_record() for k, v in scores.items()},
        "panels": {k: v.as_record() for k, v in panels.items()},
        "eligible_candidates": sorted(s.candidate_id for s in eligible),
        "status_counts": {
            status: sum(1 for s in scores.values() if s.status == status)
            for status in sorted({s.status for s in scores.values()})
        },
        "rules": {
            "flat_but_negative_is_rejected": True,
            "structurally_invalid_excluded_not_penalised": True,
            "incomplete_panel_blocks_stability_claim": True,
            "valid_bad_probes_stay_in_the_denominator": True,
        },
    }
