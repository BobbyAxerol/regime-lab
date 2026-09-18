"""LAB-04 L04.5/L04.6 -- arm A (installed selector) vs arm B (neighborhood selector).

Both arms see the SAME calendar, the SAME training memory, the SAME engine and
account contract, the SAME retention rule and the SAME evaluation budget. No
regime information enters either arm; the only difference between them is which
candidate the selection rule returns from an identical pool of evaluations.

What arm A actually is
----------------------
The installed public route's default (``optimization_mode="none"``,
``candidate_selection_metric="robust_decay"``) resolves the winner in
``quantbt.walkforward._select_oos_candidate_record`` as ``max(records, key=objective)``.
That real function makes arm A's decision here, on real
``WalkForwardTrialRecord`` rows. The fold loop and the evaluation are the lab's,
because the installed WFO strategy contract takes a pandas-series adapter and
cannot host the event adapters -- recorded as a mapping, not passed off as a
call into the installed fold engine.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.qualification import DECISION_INTERVAL
from ..selector.alpha_schemas import SCHEMAS, SEED_POINTS, suggest_point
from ..selector.probe_design import ProbeDesign, ProbeStatus
from ..selector.representative import choose_representative
from ..selector.robust_score import DEFAULT_SURVIVE_THRESHOLD, EpisodePanel, score_all
from ..selector.schema_distance import ParamSchema
from .evaluator import (UTILITY, EvaluationError, episode_bounds, episode_metrics,
                        run_candidate, window_metrics)

#: One source of truth per fact. The decision interval per alpha was pinned in
#: LAB-03 and lives in the qualification module; which alphas are blocked was
#: decided by the LAB-02 certification and lives in its committed artifact. Both
#: were previously re-typed here, which is two places to drift.
CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"
CERTIFICATION = CONFIG_DIR / "lab02_certification_summary.json"


def not_ready_alphas() -> dict[str, str]:
    """Alphas the LAB-02 certification blocked, read from the certification itself.

    A blocked alpha keeps all of its cells with null metrics; it is never booked
    as PnL 0, which would bias every aggregate.
    """
    if not CERTIFICATION.is_file():
        raise FileNotFoundError(
            f"{CERTIFICATION} is missing: LAB-02 certification is a prerequisite of LAB-04 and "
            "the blocked-alpha list may not be guessed"
        )
    payload = json.loads(CERTIFICATION.read_text())
    blocked = {}
    for alpha_id, record in payload["certifications"].items():
        if record["status"] != "READY_FOR_RESEARCH":
            reason = "; ".join(record.get("blockers") or []) or record["status"]
            blocked[alpha_id] = f"LAB-02 certification {record['status']}: {reason}"
    return blocked


NOT_READY = not_ready_alphas()


@dataclass(frozen=True)
class CalendarSpec:
    """The frozen calendar. Identical for both arms; chosen before any result."""

    train_days: int = 180
    test_days: int = 180
    first_cutoff: str = "2021-01-01"
    folds: int = 6
    inner_episodes: int = 6

    def fold_windows(self) -> list[dict]:
        out = []
        cutoff = pd.Timestamp(self.first_cutoff, tz="UTC")
        for i in range(self.folds):
            out.append({
                "fold": i,
                "train_start": (cutoff - pd.Timedelta(days=self.train_days)).isoformat(),
                "cutoff": cutoff.isoformat(),
                "test_end": (cutoff + pd.Timedelta(days=self.test_days)).isoformat(),
            })
            cutoff = cutoff + pd.Timedelta(days=self.test_days)
        return out


@dataclass(frozen=True)
class SearchBudget:
    """Guide 7.2: 64 discovery evaluations + 4 anchors x 8 probes.

    The guide names THREE anchor sources -- the TPE in-sample search, the incumbent,
    and some space-filling coverage -- so the four anchors are split across all
    three. Taking all of them from the top of the TPE ranking would place every
    local panel inside the region the sampler already favours, and arm B could then
    only ever choose near the TPE mode. TPE's own random startup trials do explore
    (Optuna runs 10 of them here), but a startup point is never guaranteed a probe
    panel, so it can be evaluated and still be invisible to a selector that needs
    local evidence.
    """

    discovery_trials: int = 64
    anchors: int = 2                    # top of the TPE ranking
    space_filling_anchors: int = 1      # farthest evaluated point from those
    probes_per_anchor: int = 8
    radius: float = 0.12
    seed: int = 20260910

    @property
    def nominal_total(self) -> int:
        # + 1 for the incumbent, which is always an anchor when one exists
        anchor_slots = self.anchors + self.space_filling_anchors + 1
        return self.discovery_trials + anchor_slots * self.probes_per_anchor


CALENDAR = CalendarSpec()
BUDGET = SearchBudget()


def _point_id(params: dict) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _finite(x):
    """Strict-JSON safe: a non-finite number is missing information, not a value."""
    if x is None:
        return None
    v = float(x)
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------------------
# one cutoff
# ---------------------------------------------------------------------------

@dataclass
class Evaluation:
    point_id: str
    params: dict
    origin: str
    status: str
    episodes: dict = field(default_factory=dict)
    window: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def objective(self) -> float:
        """The in-sample aggregate arm A ranks on: the mean episode utility."""
        values = [e["utility"] for e in self.episodes.values()]
        return float(np.mean(values)) if values else float("-inf")


def _evaluate(alpha_id: str, params: dict, frame: pd.DataFrame, bounds, origin: str,
              schema: ParamSchema, backend: str) -> Evaluation:
    point_id = _point_id(params)
    feasible, reason = schema.is_feasible(params)
    if not feasible:
        return Evaluation(point_id, params, origin, ProbeStatus.STRUCTURALLY_INVALID,
                          error=reason)
    try:
        run = run_candidate(alpha_id, params, frame, backend=backend)
        episodes = episode_metrics(run, bounds)
        window = window_metrics(run)
    except EvaluationError as exc:
        return Evaluation(point_id, params, origin, ProbeStatus.RUNTIME_ERROR, error=str(exc))
    except Exception as exc:                      # a real failure, never a loss of 0
        return Evaluation(point_id, params, origin, ProbeStatus.RUNTIME_ERROR,
                          error=f"{type(exc).__name__}: {exc}")
    if not run.converged or run.unmapped_intents:
        return Evaluation(
            point_id, params, origin, ProbeStatus.NOT_EVALUATED, window=window,
            error=(f"A03: execution is not valid (converged={run.converged}, "
                   f"unmapped_intents={run.unmapped_intents}); it is not scored as a return"))
    return Evaluation(point_id, params, origin, ProbeStatus.EVALUATED, episodes, window)


def _discover(alpha_id: str, schema: ParamSchema, frame: pd.DataFrame, bounds,
              budget: SearchBudget, seed: int, backend: str) -> list[Evaluation]:
    """TPE search on the training window only. It never sees the test window."""
    import logging

    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    logging.getLogger("optuna").setLevel(logging.WARNING)
    found: list[Evaluation] = []
    seen: set[str] = set()

    def objective(trial):
        point = suggest_point(trial, schema)
        pid = _point_id(point)
        if pid in seen:
            # A repeat costs no execution; it is reported, not counted as new evidence.
            prior = next(e for e in found if e.point_id == pid)
            return prior.objective if prior.status == ProbeStatus.EVALUATED else -1e9
        seen.add(pid)
        record = _evaluate(alpha_id, point, frame, bounds, "discovery", schema, backend)
        found.append(record)
        return record.objective if record.status == ProbeStatus.EVALUATED else -1e9

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=budget.discovery_trials, catch=(Exception,))
    return found


def run_cutoff(alpha_id: str, symbol: str, train: pd.DataFrame, fold: int,
               incumbents: dict[str, dict], *, budget: SearchBudget = BUDGET,
               calendar: CalendarSpec = CALENDAR, backend: str = "reference") -> dict:
    """Discovery, probes, and BOTH selection rules over one identical pool."""
    schema = SCHEMAS[alpha_id]
    bounds = episode_bounds(train.index, calendar.inner_episodes)
    seed = budget.seed + fold * 101

    discovery = _discover(alpha_id, schema, train, bounds, budget, seed, backend)
    evaluated = {e.point_id: e for e in discovery}

    ranked = sorted((e for e in discovery if e.status == ProbeStatus.EVALUATED),
                    key=lambda e: e.objective, reverse=True)
    anchors: dict[str, dict] = {}
    for e in ranked[:budget.anchors]:
        anchors[f"discovery_{e.point_id}"] = e.params
    # Space-filling coverage (guide 7.2 step 1): the evaluated discovery point
    # FARTHEST from the anchors already chosen, by the same schema distance the
    # selector uses. Deterministic, and it guarantees at least one local panel
    # outside the region TPE concentrated on.
    space_filling: list[str] = []
    for _ in range(budget.space_filling_anchors):
        chosen = list(anchors.values())
        if not chosen:
            break
        pool = [e for e in ranked if f"discovery_{e.point_id}" not in anchors]
        if not pool:
            break
        far = max(
            pool,
            key=lambda e: (min(schema.distance(e.params, point) for point in chosen),
                           e.point_id),
        )
        key = f"spacefill_{far.point_id}"
        anchors[key] = far.params
        space_filling.append(key)
    # Guide 7.2: the incumbent sits inside the anchor set and gets the same probe
    # budget. Each arm carries its OWN incumbent so neither is judged against the
    # other's; when they differ this cutoff spends one extra anchor, and that is
    # reported rather than hidden.
    by_point = {_point_id(v): k for k, v in anchors.items()}
    incumbent_anchor_ids: dict[str, str] = {}
    for arm, point in incumbents.items():
        if point is None:
            continue
        pid = _point_id(point)
        if pid in by_point:
            # already an anchor (the other arm's incumbent, or a discovery winner):
            # reuse it rather than spending a second probe budget on the same point
            incumbent_anchor_ids[arm] = by_point[pid]
            continue
        key = f"incumbent_{arm}_{pid}"
        anchors[key] = dict(point)
        by_point[pid] = key
        incumbent_anchor_ids[arm] = key

    design = ProbeDesign(schema, radius=budget.radius,
                         probes_per_anchor=budget.probes_per_anchor, seed=seed)
    built = design.build(anchors)

    neighbourhoods: dict[str, list[str]] = {}
    for anchor_id, probes in built["probes"].items():
        anchor_point = anchors[anchor_id]
        anchor_pid = _point_id(anchor_point)
        if anchor_pid not in evaluated:
            evaluated[anchor_pid] = _evaluate(alpha_id, anchor_point, train, bounds,
                                              f"anchor:{anchor_id}", schema, backend)
        members = []
        for probe in probes:
            pid = _point_id(probe["point"])
            if pid not in evaluated:
                evaluated[pid] = _evaluate(alpha_id, probe["point"], train, bounds,
                                           f"probe:{anchor_id}", schema, backend)
            members.append(pid)
        neighbourhoods[anchor_pid] = members
        for pid in members:
            # a probe's neighbourhood is its anchor and its siblings
            neighbourhoods[pid] = [anchor_pid] + [m for m in members if m != pid]

    ok = {pid: e for pid, e in evaluated.items() if e.status == ProbeStatus.EVALUATED}

    # ---- arm A: the installed selector makes this decision -------------
    arm_a = _select_with_installed(ok)

    # ---- arm B: robust neighborhood selection over the same pool -------
    panels = {}
    for pid, e in evaluated.items():
        if e.status == ProbeStatus.STRUCTURALLY_INVALID:
            panels[pid] = EpisodePanel(pid, e.params, structurally_invalid=True,
                                       invalid_reason=e.error)
        elif e.status == ProbeStatus.RUNTIME_ERROR:
            panels[pid] = EpisodePanel(pid, e.params,
                                       failed_episodes={b[0]: e.error or "runtime error"
                                                        for b in bounds})
        else:
            panels[pid] = EpisodePanel(
                pid, e.params,
                utilities={k: v["utility"] for k, v in e.episodes.items()},
                gate_pass={k: v["gate_pass"] for k, v in e.episodes.items()})
    scored = score_all(panels, neighbourhoods)
    eligible = {pid: panels[pid].params for pid in scored["eligible_candidates"]}
    arm_b = _select_with_neighborhood(schema, scored, eligible, ok)

    return {
        "fold": fold, "alpha_id": alpha_id, "symbol": symbol,
        "train_start": train.index[0].isoformat(), "train_end": train.index[-1].isoformat(),
        "train_bars": int(len(train)),
        "budget": {
            **asdict(budget), "nominal_total": budget.nominal_total,
            "unique_executions": len(evaluated),
            "evaluated": len(ok),
            "structurally_invalid": sum(1 for e in evaluated.values()
                                        if e.status == ProbeStatus.STRUCTURALLY_INVALID),
            "runtime_errors": sum(1 for e in evaluated.values()
                                  if e.status == ProbeStatus.RUNTIME_ERROR),
            "candidate_episode_visits": len(ok) * calendar.inner_episodes,
            "anchors_used": len(anchors),
            "anchor_sources": {
                "tpe_top": [k for k in anchors if k.startswith("discovery_")],
                "space_filling": space_filling,
                "incumbent": sorted(set(incumbent_anchor_ids.values())),
            },
            "space_filling_min_distance_to_tpe_anchors": {
                key: _finite(min(
                    schema.distance(anchors[key], anchors[other])
                    for other in anchors
                    if other != key and other.startswith("discovery_")))
                for key in space_filling
            },
            "incumbent_anchor_ids": incumbent_anchor_ids,
            "shared_incumbent_anchor": len(set(incumbent_anchor_ids.values())) == 1,
            "both_arms_see_the_same_pool": True,
        },
        "probe_design": {"design_digest": built["design_digest"], "radius": built["radius"],
                         "probes_per_anchor": built["probes_per_anchor"],
                         "probe_count": built["probe_count"],
                         "unique_probe_ids": built["unique_probe_ids"],
                         "structurally_invalid_rejections":
                             len(built["structurally_invalid_rejections"])},
        "arm_A": arm_a, "arm_B": arm_b,
        "robust_status_counts": scored["status_counts"],
        "local_coverage": _coverage(neighbourhoods, ok, calendar.inner_episodes),
        "evaluations": [
            {"point_id": pid, "origin": e.origin, "status": e.status,
             "objective": _finite(e.objective) if e.status == ProbeStatus.EVALUATED else None,
             "error": e.error}
            for pid, e in evaluated.items()
        ],
        "robust_scores": {pid: s for pid, s in scored["scores"].items()},
    }


def _select_with_installed(ok: dict[str, Evaluation]) -> dict:
    """Arm A. The decision is made by the installed function, not reimplemented.

    A08 / QUARANTINED_FOR_HISTORICAL_TESTS_ONLY. This is the audited defect path:
    the records are built by hand and a mean episode utility is written into the
    ``mean_is_sharpe`` field, so it is an argmax-utility selector wearing a
    Sharpe label, not the public Mode 4 pipeline. The corrective study never
    calls it: arm A is the actual public WFO in
    :mod:`crypto_regime_lab.selector.mode4_baseline`. It stays here so the
    historical LAB-04 tests keep their evidence.
    """
    from quantbt.walkforward import WalkForwardConfig, WalkForwardTrialRecord
    from quantbt.walkforward import _select_oos_candidate_record

    if not ok:
        return {"status": "NO_EVALUATION", "params": None,
                "reason": "no candidate produced a valid evaluation"}
    order = sorted(ok)
    records = []
    for i, pid in enumerate(order):
        e = ok[pid]
        records.append(WalkForwardTrialRecord(
            trial_id=i, params=dict(e.params), objective=e.objective,
            mean_is_sharpe=e.objective, mean_oos_sharpe=0.0, mean_decay=0.0, std_decay=0.0,
            fold_metrics=[], pruned=False,
            selection_metadata={"stage": "is_search", "lab_point_id": pid,
                                "oos_seen_by_optuna": False}))
    config = WalkForwardConfig()
    chosen = _select_oos_candidate_record(records, config)
    return {
        "status": "SELECTED",
        "selector": "quantbt.walkforward._select_oos_candidate_record",
        "candidate_selection_metric": config.candidate_selection_metric,
        "optimization_mode": config.optimization_mode,
        "rule": "max(records, key=objective) -- the public route's default",
        "point_id": chosen.selection_metadata.get("lab_point_id"),
        "params": dict(chosen.params),
        "objective": _finite(chosen.objective),
        "candidates_considered": len(records),
        "selection_metadata": {k: v for k, v in chosen.selection_metadata.items()
                               if isinstance(v, (str, int, float, bool, type(None)))},
    }


def _select_with_neighborhood(schema: ParamSchema, scored: dict, eligible: dict,
                              ok: dict[str, Evaluation]) -> dict:
    """Arm B. R = G - lambda_F*F over an independently designed local panel."""
    if not eligible:
        cause = _dominant_cause(scored["status_counts"])
        return {"status": f"NO_ADMISSIBLE_CANDIDATE:{cause}", "params": None,
                "selector": "lab robust neighborhood",
                "binding_constraint": cause,
                "reason": "no candidate passed quality, survival and local-evidence gates; "
                          "the incumbent is retained rather than fabricating a plateau",
                "status_counts": scored["status_counts"]}
    best_r = max(eligible, key=lambda pid: (scored["scores"][pid]["r"], -int(pid, 16)))
    rep = choose_representative(schema, eligible,
                                evaluated_points=[ok[p].params for p in eligible if p in ok])
    score = scored["scores"][best_r]
    return {
        "status": "SELECTED",
        "selector": "lab robust neighborhood (guide 7.3)",
        "rule": "argmax R over candidates passing quality, survival and local evidence",
        "point_id": best_r, "params": dict(eligible[best_r]),
        "G": _finite(score["g"]), "F": _finite(score["f"]), "R": _finite(score["r"]),
        "P_survive": _finite(score["p_survive"]),
        "episodes_used": score["episodes_used"], "neighbours_used": score["neighbours_used"],
        "eligible_count": len(eligible),
        "candidates_considered": len(scored["scores"]),
        "representative": rep,
    }


def _coverage(neighbourhoods: dict[str, list[str]], ok: dict, episodes: int) -> dict:
    sizes = [len([m for m in members if m in ok]) for members in neighbourhoods.values()]
    return {
        "candidates_with_a_neighbourhood": len(neighbourhoods),
        "median_evaluated_neighbours": float(np.median(sizes)) if sizes else 0.0,
        "min_evaluated_neighbours": int(min(sizes)) if sizes else 0,
        "episodes_per_candidate": episodes,
        "note": "coverage is reported before any selection claim (guide L04.6)",
    }


# ---------------------------------------------------------------------------
# one cell = one alpha on one symbol, all folds, both arms
# ---------------------------------------------------------------------------

ARMS = ("A", "B")

#: The full primary matrix, so a summary can say whether it is looking at all of it.
ALPHA_ORDER_DEFAULT = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")
SYMBOL_ORDER_DEFAULT = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")

#: A window shorter than this per inner episode cannot carry a meaningful account
#: trace, so the fold is reported INSUFFICIENT_BARS instead of scored.
MIN_BARS_PER_EPISODE = 20


def _deploy(alpha_id: str, params: dict, test: pd.DataFrame, backend: str) -> dict:
    try:
        run = run_candidate(alpha_id, params, test, backend=backend)
    except Exception as exc:
        return {"status": "RUNTIME_ERROR", "error": f"{type(exc).__name__}: {exc}",
                "growth": None, "metrics": None}
    metrics = window_metrics(run)
    base = float(run.equity[0])
    growth = (run.equity / base) if base > 0 else None
    return {"status": "DEPLOYED", "error": None,
            "growth": None if growth is None else growth.tolist(),
            "metrics": {k: (_finite(v) if isinstance(v, (int, float)) and not isinstance(v, bool)
                            else v) for k, v in metrics.items()}}


def run_cell(alpha_id: str, symbol: str, bars: pd.DataFrame, *,
             calendar: CalendarSpec = CALENDAR, budget: SearchBudget = BUDGET,
             backend: str = "reference", progress=None) -> dict:
    """One alpha-symbol cell across the whole frozen calendar, both arms."""
    if alpha_id in NOT_READY:
        return {
            "alpha_id": alpha_id, "symbol": symbol, "status": "NOT_READY",
            "reason": NOT_READY[alpha_id],
            "arms": {arm: {"status": "NOT_READY", "net_return": None, "sharpe": None,
                           "trades": None,
                           "note": "null metrics; a blocked alpha is never booked as PnL 0"}
                     for arm in ARMS},
            "folds": [],
        }

    incumbents = {arm: dict(SEED_POINTS[alpha_id]) for arm in ARMS}
    fold_records: list[dict] = []
    chains = {arm: [] for arm in ARMS}
    deployed = {arm: [] for arm in ARMS}

    for window in calendar.fold_windows():
        train = bars[(bars.index >= window["train_start"]) & (bars.index < window["cutoff"])]
        test = bars[(bars.index >= window["cutoff"]) & (bars.index < window["test_end"])]
        if (len(train) < calendar.inner_episodes * MIN_BARS_PER_EPISODE
                or len(test) < MIN_BARS_PER_EPISODE):
            fold_records.append({**window, "status": "INSUFFICIENT_BARS",
                                 "train_bars": int(len(train)), "test_bars": int(len(test))})
            continue
        if progress:
            progress(f"{alpha_id}/{symbol} fold {window['fold']} "
                     f"train={len(train)} test={len(test)}")

        cutoff = run_cutoff(alpha_id, symbol, train, window["fold"], incumbents,
                            budget=budget, calendar=calendar, backend=backend)

        record = {**window, "status": "OK", "train_bars": int(len(train)),
                  "test_bars": int(len(test)), "cutoff_evidence": cutoff, "arms": {}}
        for arm in ARMS:
            selection = cutoff[f"arm_{arm}"]
            if selection["params"] is None:
                # retention rule, identical for both arms: keep the incumbent
                params = incumbents[arm]
                retained = True
            else:
                params = selection["params"]
                retained = False
            turnover = SCHEMAS[alpha_id].distance(incumbents[arm], params)
            out = _deploy(alpha_id, params, test, backend)
            if out["growth"]:
                chains[arm].append({"index": [t.isoformat() for t in test.index],
                                    "growth": out["growth"]})
            deployed[arm].append(params)
            record["arms"][arm] = {
                "selection_status": selection["status"], "retained_incumbent": retained,
                "params": params, "parameter_turnover_vs_incumbent": _finite(turnover),
                "deployment": {k: v for k, v in out.items() if k != "growth"},
                "selection": {k: v for k, v in selection.items() if k != "params"},
            }
            incumbents[arm] = params
        fold_records.append(record)

    return {
        "alpha_id": alpha_id, "symbol": symbol, "status": "RUN",
        "decision_interval": DECISION_INTERVAL[alpha_id],
        "folds": fold_records,
        "arms": {arm: _chain_summary(chains[arm], deployed[arm], alpha_id, fold_records, arm)
                 for arm in ARMS},
    }


def _chain_summary(chain: list[dict], deployed: list[dict], alpha_id: str,
                   folds: list[dict], arm: str) -> dict:
    """One continuous chronological account: folds are chained, never cherry-picked."""
    if not chain:
        return {"status": "NO_DEPLOYMENT", "net_return": None, "sharpe": None, "trades": None}
    equity = []
    level = 1.0
    fold_returns = []
    for leg in chain:
        growth = np.asarray(leg["growth"], dtype=float)
        equity.extend((level * growth).tolist())
        fold_returns.append(float(growth[-1] - 1.0))
        level = level * float(growth[-1])
    equity = np.asarray(equity, dtype=float)
    steps = np.diff(equity) / np.maximum(equity[:-1], 1e-12)
    sharpe = None
    if steps.size > 2 and float(np.std(steps)) > 0:
        sharpe = float(np.mean(steps) / np.std(steps) * math.sqrt(len(steps)))
    peak = np.maximum.accumulate(equity)
    mdd = float(np.max((peak - equity) / peak)) if equity.size else None

    ok_folds = [f for f in folds if f.get("status") == "OK"]
    # NOTE: this counts ENGINE FILLS -- an entry and its exit are two. summarize()
    # derives the fills/entries split from the fold records so that cells written by
    # any version of this module report the same thing.
    engine_fills = sum(int(m["fills"]) for m in _fold_metrics(ok_folds, arm))
    gains = [r for r in fold_returns if r > 0]
    concentration = (max(gains) / sum(gains)) if gains and sum(gains) > 0 else None
    turnovers = [f["arms"][arm]["parameter_turnover_vs_incumbent"] for f in ok_folds]
    turnovers = [t for t in turnovers if t is not None]

    return {
        "status": "DEPLOYED",
        "net_return": _finite(level - 1.0),
        "sharpe_over_chain": _finite(sharpe),
        "max_drawdown": _finite(mdd),
        "trades": engine_fills,
        "fold_returns": [_finite(r) for r in fold_returns],
        "losing_folds": int(sum(1 for r in fold_returns if r < 0)),
        "worst_fold_return": _finite(min(fold_returns)) if fold_returns else None,
        "period_concentration": _finite(concentration),
        "concentration_meaning": ("share of all positive fold return coming from the single best "
                                  "fold; near 1.0 means the result rests on one period"),
        "parameter_turnover": {
            "mean": _finite(float(np.mean(turnovers))) if turnovers else None,
            "max": _finite(float(max(turnovers))) if turnovers else None,
            "per_fold": [_finite(t) for t in turnovers],
        },
        "distinct_parameter_sets": len({_point_id(p) for p in deployed}),
        "account_policy": ("one continuous chronological account: fold legs are chained by growth "
                           "factor with no equity reset and no segment selection; the engine does "
                           "close any open position on the last bar of each leg, so a position is "
                           "not carried across a cutoff"),
    }


# ---------------------------------------------------------------------------
# L04.6 -- evidence before any model-selection claim
# ---------------------------------------------------------------------------

#: A candidate can be inadmissible for three quite different reasons, and one
#: status covering all of them hides which constraint actually bound.
NO_CANDIDATE_CAUSES = ("NO_LOCAL_PANEL", "ALL_FAIL_ECONOMIC_QUALITY", "ALL_FAIL_SURVIVAL",
                       "ALL_PANELS_INCOMPLETE", "MIXED")


def _dominant_cause(status_counts: dict) -> str:
    """Which constraint actually bound at a cutoff where nothing was admissible.

    Derived from the per-candidate robust-score statuses, so it reads the same way
    for a cell written by any version of this module.
    """
    if not status_counts:
        return "UNKNOWN"
    blocking = {k: v for k, v in status_counts.items() if k != "ELIGIBLE"}
    if not blocking:
        return "UNKNOWN"
    mapping = {
        "INSUFFICIENT_LOCAL_EVIDENCE": "NO_LOCAL_PANEL",
        "FAILS_ECONOMIC_QUALITY": "ALL_FAIL_ECONOMIC_QUALITY",
        "FAILS_SURVIVAL": "ALL_FAIL_SURVIVAL",
        "INCOMPLETE_PANEL": "ALL_PANELS_INCOMPLETE",
    }
    # a candidate with no designed neighbourhood was never a contender, so the
    # binding constraint is whichever gate rejected the ones that DID have panels
    contenders = {k: v for k, v in blocking.items() if k != "INSUFFICIENT_LOCAL_EVIDENCE"}
    pool = contenders or blocking
    top = max(pool, key=lambda k: pool[k])
    return mapping.get(top, "MIXED")


def _retention_reasons(cells: list[dict], arm: str) -> dict:
    """Why a selector returned nothing admissible, by the constraint that bound."""
    reasons: dict[str, int] = {}
    for cell in cells:
        for fold in cell.get("folds", []):
            if fold.get("status") != "OK":
                continue
            record = fold["arms"][arm]
            if not record["retained_incumbent"]:
                continue
            selection = record["selection"]
            counts = selection.get("status_counts")
            if counts is None:
                evidence = fold.get("cutoff_evidence") or {}
                counts = evidence.get("robust_status_counts")
            cause = _dominant_cause(counts or {})
            reasons[cause] = reasons.get(cause, 0) + 1
    return dict(sorted(reasons.items()))


def _fold_metrics(folds: list[dict], arm: str) -> list[dict]:
    """The deployment metrics of one arm across a cell's completed folds."""
    out = []
    for fold in folds:
        if fold.get("status") != "OK":
            continue
        metrics = fold["arms"][arm]["deployment"].get("metrics")
        if metrics is not None:
            out.append(metrics)
    return out


def _paired(cells: list[dict], field: str) -> list[tuple[str, float, float]]:
    out = []
    for cell in cells:
        if cell["status"] != "RUN":
            continue
        a, b = cell["arms"].get("A", {}), cell["arms"].get("B", {})
        if a.get(field) is None or b.get(field) is None:
            continue
        out.append((f"{cell['alpha_id']}/{cell['symbol']}", float(a[field]), float(b[field])))
    return out


def _sign_test(pairs: list[tuple[str, float, float]]) -> dict:
    """A paired sign test. Deliberately weak: it states what it can and no more."""
    wins = sum(1 for _, a, b in pairs if b > a)
    losses = sum(1 for _, a, b in pairs if b < a)
    ties = len(pairs) - wins - losses
    n = wins + losses
    p_value = None
    if n:
        k = max(wins, losses)
        tail = sum(math.comb(n, i) for i in range(k, n + 1))
        p_value = min(1.0, 2.0 * tail / (2 ** n))
    return {"cells": len(pairs), "B_better": wins, "A_better": losses, "ties": ties,
            "two_sided_sign_test_p": _finite(p_value),
            "caveat": (f"a paired sign test over {len(pairs)} cells drawn from the same five "
                       "symbols and one calendar; the cells are not independent, so this is a "
                       "descriptive statistic and not a confirmatory test")}


def summarize(cells: list[dict], *, wall_seconds: float | None = None) -> dict:
    run_cells = [c for c in cells if c["status"] == "RUN"]
    not_ready = [c for c in cells if c["status"] == "NOT_READY"]

    returns = _paired(run_cells, "net_return")
    sharpes = _paired(run_cells, "sharpe_over_chain")
    diffs = [b - a for _, a, b in returns]

    table = []
    for cell in cells:
        a = cell["arms"].get("A", {})
        b = cell["arms"].get("B", {})
        if cell["status"] == "NOT_READY":
            table.append(f"{cell['alpha_id']:<8}{cell['symbol']:<10} NOT_READY  "
                         f"A=null B=null  (metrics are null, never PnL 0)")
            continue
        table.append(
            f"{cell['alpha_id']:<8}{cell['symbol']:<10} "
            f"A={_fmt(a.get('net_return')):>9} B={_fmt(b.get('net_return')):>9}  "
            f"trades A={a.get('trades')}/B={b.get('trades')}  "
            f"conc A={_fmt(a.get('period_concentration'))}/B={_fmt(b.get('period_concentration'))}")

    total_evals = 0
    total_visits = 0
    invalid = 0
    runtime_errors = 0
    coverage = []
    for cell in run_cells:
        for fold in cell["folds"]:
            evidence = fold.get("cutoff_evidence")
            if not evidence:
                continue
            budget = evidence["budget"]
            total_evals += budget["unique_executions"]
            total_visits += budget["candidate_episode_visits"]
            invalid += budget["structurally_invalid"]
            runtime_errors += budget["runtime_errors"]
            coverage.append(evidence["local_coverage"]["median_evaluated_neighbours"])

    retention_events = {
        arm: {
            "retained": sum(1 for cell in run_cells for fold in cell["folds"]
                            if fold.get("status") == "OK"
                            and fold["arms"][arm]["retained_incumbent"]),
            "cutoffs": sum(1 for cell in run_cells for fold in cell["folds"]
                           if fold.get("status") == "OK"),
            "reasons": _retention_reasons(run_cells, arm),
        } for arm in ARMS
    }

    mean_diff = float(np.mean(diffs)) if diffs else None
    never_switched = _never_switched(run_cells)
    confounds = _confounds(retention_events, run_cells)
    verdict = _with_confound_caveat(_verdict(returns, sharpes, mean_diff), confounds)

    return {
        "schema": "crypto_regime_lab.calendar_baseline.v1",
        "arms": {"A": "installed selector + frozen calendar",
                 "B": "robust neighborhood selector + the SAME frozen calendar"},
        "regime_information_used": False,
        "calendar": asdict(CALENDAR),
        # The budget recorded here must be the one the CELLS were produced with, not
        # whatever the module constant happens to be now. A long run executes the
        # code loaded at launch; reading BUDGET at summarise time would let the
        # artifact claim a design it was never built with.
        "search_budget": _observed_budget(run_cells),
        "matched_conditions": [
            "same fold calendar and cutoffs", "same training memory per fold",
            "same engine, execution contract and frozen account", "same retention rule",
            "same candidate pool at every cutoff", "same evaluation budget",
            "no regime information in either arm",
        ],
        "cells_total": len(cells), "cells_run": len(run_cells),
        "cells_not_ready": len(not_ready),
        "not_ready_detail": [{"alpha_id": c["alpha_id"], "symbol": c["symbol"],
                              "reason": c["reason"]} for c in not_ready],
        "search_effort": {
            "unique_executions": total_evals,
            "candidate_episode_visits": total_visits,
            "structurally_invalid": invalid,
            "runtime_errors": runtime_errors,
            "reporting_rule": ("unique execution count and candidate-episode visits are reported, "
                               "not an Optuna trial count (guide 7.2)"),
        },
        "local_coverage": {
            "median_evaluated_neighbours_across_cutoffs":
                _finite(float(np.median(coverage))) if coverage else None,
            "min_evaluated_neighbours_across_cutoffs":
                _finite(float(min(coverage))) if coverage else None,
        },
        "matrix_complete": (len(cells)
                            == len(ALPHA_ORDER_DEFAULT) * len(SYMBOL_ORDER_DEFAULT)),
        "cells_expected": len(ALPHA_ORDER_DEFAULT) * len(SYMBOL_ORDER_DEFAULT),
        "retention_events": retention_events,
        "retention_rule": ("if a selector returns nothing admissible, the incumbent is retained; "
                           "identical for both arms"),
        "contrast_B_minus_A": {
            "metric_definitions": {
                "net_return": ("terminal growth of the chained account minus 1, where each fold "
                               "leg is chained by its growth factor"),
                "sharpe": ("mean/std of per-bar returns times sqrt(bars) over the WHOLE chained "
                           "horizon; it is not annualised and must not be compared to an "
                           "annualised figure"),
            },
            "net_return": _sign_test(returns),
            "sharpe": _sign_test(sharpes),
            "mean_net_return_difference": _finite(mean_diff),
            "median_net_return_difference": _finite(float(np.median(diffs))) if diffs else None,
            "worst_cell_difference": _finite(float(min(diffs))) if diffs else None,
            "best_cell_difference": _finite(float(max(diffs))) if diffs else None,
            "per_cell": [{"cell": name, "A": _finite(a), "B": _finite(b),
                          "difference": _finite(b - a)} for name, a, b in returns],
        },
        "cells_where_an_arm_never_used_its_selector": never_switched,
        "gate_bindingness_diagnostic": _gate_sensitivity(run_cells),
        "contrast_where_both_arms_actually_selected": _contrast_excluding_stuck(
            run_cells, never_switched),
        "registered_hypothesis": _registered_hypothesis(run_cells, cells),
        "contrast_by_alpha": _contrast_by_alpha(run_cells),
        "lower_tail": {
            arm: {
                "cells_with_a_losing_chain": sum(
                    1 for c in run_cells
                    if (c["arms"][arm].get("net_return") or 0.0) < 0),
                "worst_cell_net_return": _finite(min(
                    [c["arms"][arm]["net_return"] for c in run_cells
                     if c["arms"][arm].get("net_return") is not None], default=None)),
                "mean_losing_folds": _mean_or_none(
                    [c["arms"][arm].get("losing_folds") for c in run_cells]),
                "mean_max_drawdown": _mean_or_none(
                    [c["arms"][arm].get("max_drawdown") for c in run_cells]),
            } for arm in ARMS
        },
        "period_concentration": {
            arm: {
                "mean": _mean_or_none(
                    [c["arms"][arm].get("period_concentration") for c in run_cells]),
                "meaning": "share of positive fold return from the single best fold",
            } for arm in ARMS
        },
        "parameter_behaviour_fingerprint": {
            arm: {
                "mean_turnover": _mean_or_none(
                    [c["arms"][arm].get("parameter_turnover", {}).get("mean")
                     for c in run_cells]),
                "mean_distinct_parameter_sets": _mean_or_none(
                    [c["arms"][arm].get("distinct_parameter_sets") for c in run_cells]),
                "engine_fills": int(sum(
                    m["fills"] for c in run_cells
                    for m in _fold_metrics(c.get("folds", []), arm))),
                "entries": int(sum(
                    m["entries"] for c in run_cells
                    for m in _fold_metrics(c.get("folds", []), arm))),
                "mean_holding_bars": _mean_or_none([
                    m.get("mean_holding_bars") for c in run_cells
                    for m in _fold_metrics(c.get("folds", []), arm)]),
                "mean_exposure": _mean_or_none([
                    m.get("exposure") for c in run_cells
                    for m in _fold_metrics(c.get("folds", []), arm)]),
            } for arm in ARMS
        },
        "trade_count_convention": (
            "engine_fills counts FILLS -- an entry and its exit are two. entries counts positions "
            "opened. The `trades` column in the per-cell table is engine_fills."),
        "console_table": table,
        "confounds": confounds,
        "incumbent_parity_measured": _incumbent_parity(run_cells),
        "local_evidence_behind_each_deployment": _deployed_evidence(run_cells),
        "verdict": verdict,
        "factorial_rule": ("both arms are retained for the LAB-06 factorial regardless of this "
                           "result; B is not assumed correct and A is not retired (guide L04.6)"),
        "wall_seconds": wall_seconds,
        "cells": cells,
    }


def _mean_or_none(values: list) -> float | None:
    """np.mean of an empty list is a nan plus a warning; a missing mean is None."""
    clean = [v for v in values if v is not None]
    return _finite(float(np.mean(clean))) if clean else None


def _deployed_evidence(run_cells: list[dict]) -> dict:
    """Did the point each arm actually deployed have any local stability evidence?

    This is the lab's own question turned on itself, read back from the robust-score
    status of the point each arm actually chose.

    The expected failure mode was arm A deploying a point no probe ever surrounded.
    It does not happen here, and the reason is structural rather than lucky: arm A
    picks the best in-sample objective, and the top discovery points ARE the
    anchors, so arm A's choice always has a local panel. What the measurement finds
    instead is sharper -- arm A frequently deploys a point whose own local panel
    says it fails the quality or survival gate, because arm A never consults it.
    """
    out: dict[str, dict] = {}
    for arm in ARMS:
        counts: dict[str, int] = {}
        deployments = 0
        for cell in run_cells:
            for fold in cell.get("folds", []):
                evidence = fold.get("cutoff_evidence")
                if not evidence or fold.get("status") != "OK":
                    continue
                point_id = evidence[f"arm_{arm}"].get("point_id")
                if point_id is None:
                    continue
                deployments += 1
                score = evidence.get("robust_scores", {}).get(point_id)
                status = score["status"] if score else "NOT_SCORED"
                counts[status] = counts.get(status, 0) + 1
        no_panel = counts.get("INSUFFICIENT_LOCAL_EVIDENCE", 0)
        rejected = sum(count for status, count in counts.items()
                       if status not in ("ELIGIBLE", "INSUFFICIENT_LOCAL_EVIDENCE",
                                         "NOT_SCORED"))
        out[arm] = {
            "deployments": deployments,
            "robust_status_of_the_deployed_point": dict(sorted(counts.items())),
            "deployed_without_any_local_panel": no_panel,
            "share_without_a_local_panel": _finite(no_panel / deployments) if deployments else None,
            "deployed_a_point_its_own_panel_rejects": rejected,
            "share_its_own_panel_rejects": _finite(rejected / deployments) if deployments else None,
        }
    out["reading"] = (
        "share_without_a_local_panel is the sharp-peak-with-no-evidence exposure. It is zero for "
        "both arms here, and structurally so: arm A picks the top in-sample objective and the top "
        "discovery points are exactly the anchors that get probed. The informative number is "
        "share_its_own_panel_rejects -- a point that WAS surrounded by probes, whose panel says it "
        "fails the quality or survival gate, and which arm A deploys anyway because its rule never "
        "reads that panel. Arm B cannot do this by construction, which is a definitional "
        "difference between the arms, not an out-of-sample result.")
    return out


def _incumbent_parity(run_cells: list[dict]) -> dict:
    """L04.4, checked on the real run rather than only on a fixture.

    The incumbent must be an ANCHOR with the same probe budget as any discovery
    anchor, and its local panel must be the same size. Both are read back out of
    what the cutoffs actually recorded.
    """
    cutoffs = 0
    incumbent_is_anchor = 0
    probes_per_anchor: set[int] = set()
    min_neighbours: set[int] = set()
    shared_anchor = 0
    for cell in run_cells:
        for fold in cell.get("folds", []):
            evidence = fold.get("cutoff_evidence")
            if not evidence:
                continue
            cutoffs += 1
            budget = evidence["budget"]
            if budget.get("incumbent_anchor_ids"):
                incumbent_is_anchor += 1
            if budget.get("shared_incumbent_anchor"):
                shared_anchor += 1
            probes_per_anchor.add(int(evidence["probe_design"]["probes_per_anchor"]))
            min_neighbours.add(int(evidence["local_coverage"]["min_evaluated_neighbours"]))
    return {
        "cutoffs": cutoffs,
        "cutoffs_where_the_incumbent_was_an_anchor": incumbent_is_anchor,
        "incumbent_always_an_anchor": cutoffs > 0 and incumbent_is_anchor == cutoffs,
        "probes_per_anchor_values_seen": sorted(probes_per_anchor),
        "every_anchor_got_the_same_probe_budget": len(probes_per_anchor) <= 1,
        "min_evaluated_neighbours_values_seen": sorted(min_neighbours),
        "no_candidate_had_a_smaller_panel_than_another":
            len(min_neighbours) <= 1 and sorted(min_neighbours) == sorted(probes_per_anchor),
        "cutoffs_where_both_arms_shared_one_incumbent_anchor": shared_anchor,
        "rule": ("guide 7.2: the incumbent sits inside the anchor set and receives the same probe "
                 "design, budget and constraints as any challenger"),
    }


def _never_switched(run_cells: list[dict]) -> dict:
    """Cells where an arm kept the registered seed point at EVERY cutoff.

    A cell like that is a valid technical pass -- the registered falsification
    commitment says zero switches because no challenger qualified is a pass -- but
    it does not test the selector. Its B-A difference compares the seed point with
    the other arm's selector, and pooling it with cells that did switch overstates
    how much of the matrix actually exercised the thing under test.
    """
    out: dict[str, dict] = {}
    for arm in ARMS:
        stuck = []
        for cell in run_cells:
            ok_folds = [f for f in cell.get("folds", []) if f.get("status") == "OK"]
            if not ok_folds:
                continue
            if all(f["arms"][arm]["retained_incumbent"] for f in ok_folds):
                counts = (ok_folds[0].get("cutoff_evidence") or {}).get(
                    "robust_status_counts", {})
                stuck.append({
                    "cell": f"{cell['alpha_id']}/{cell['symbol']}",
                    "cutoffs": len(ok_folds),
                    "distinct_parameter_sets": cell["arms"][arm]["distinct_parameter_sets"],
                    "binding_constraint": _dominant_cause(counts),
                    "net_return": cell["arms"][arm].get("net_return"),
                })
        out[arm] = {
            "cells": len(stuck),
            "of_cells": len(run_cells),
            "detail": stuck,
        }
    out["reading"] = (
        "an arm listed here ran the registered seed point for the whole evaluation and never "
        "exercised its selector. That is a valid technical pass under the registered "
        "falsification commitments, and it is NOT evidence about the selector. Any contrast that "
        "includes these cells is partly a comparison against a fixed seed point.")
    return out


#: Alternative gates for the POST-HOC diagnostic below. The registered pair is
#: (0.0, 0.60) and stays the primary; nothing here may change a conclusion.
GATE_GRID = ((-1.0, 0.60), (-0.5, 0.60), (0.0, 0.50), (0.0, 0.60), (0.0, 0.70))


def _gate_sensitivity(run_cells: list[dict]) -> dict:
    """How binding is the registered economic-quality gate?

    DECLARED POST-HOC. The registered gate (min_quality 0.0, survive 0.60) was
    fixed on development before any arm ran and it stays the primary. This is
    measured only because the gate turned out to bind at half of all cutoffs, and
    a reader cannot judge the result without knowing that.

    It re-derives ELIGIBILITY from the per-candidate G and P_survive already stored
    in each cutoff, so it costs no new backtest. That is also its limit: it can say
    how often arm B would have HAD something admissible to choose, and it cannot say
    whether choosing it would have paid. No outcome is simulated and none is implied.
    """
    rows = []
    for min_quality, survive in GATE_GRID:
        cutoffs = 0
        with_candidate = 0
        eligible_counts = []
        for cell in run_cells:
            for fold in cell.get("folds", []):
                evidence = fold.get("cutoff_evidence")
                if not evidence or fold.get("status") != "OK":
                    continue
                cutoffs += 1
                eligible = 0
                for score in evidence.get("robust_scores", {}).values():
                    if score.get("r") is None or score.get("g") is None:
                        continue          # no local panel: never a contender
                    if score["status"] in ("STRUCTURALLY_INVALID", "NO_EVALUATION",
                                           "INCOMPLETE_PANEL"):
                        continue
                    p_survive = score.get("p_survive")
                    if score["g"] > min_quality and (p_survive is None
                                                     or p_survive >= survive):
                        eligible += 1
                eligible_counts.append(eligible)
                with_candidate += int(eligible > 0)
        rows.append({
            "min_quality": min_quality, "survive_threshold": survive,
            "is_the_registered_gate": (min_quality, survive) == (
                UTILITY["gate_min_return"], DEFAULT_SURVIVE_THRESHOLD),
            "cutoffs": cutoffs,
            "cutoffs_with_at_least_one_admissible_candidate": with_candidate,
            "share_of_cutoffs_with_a_candidate": _finite(with_candidate / cutoffs)
            if cutoffs else None,
            "median_eligible_candidates": _finite(float(np.median(eligible_counts)))
            if eligible_counts else None,
        })
    # A candidate is labelled by the FIRST gate it fails, so FAILS_SURVIVAL is
    # undercounted in the status histogram: a point that fails quality is never
    # also tested for survival. Loosening the quality gate therefore exposes the
    # survival gate rather than admitting everything.
    cutoffs_total = rows[0]["cutoffs"] if rows else 0
    with_computable_r = 0
    for cell in run_cells:
        for fold in cell.get("folds", []):
            evidence = fold.get("cutoff_evidence")
            if not evidence or fold.get("status") != "OK":
                continue
            if any(score.get("r") is not None
                   for score in evidence.get("robust_scores", {}).values()):
                with_computable_r += 1
    return {
        "declared_post_hoc": True,
        "registered_gate": {"min_quality": UTILITY["gate_min_return"],
                            "survive_threshold": DEFAULT_SURVIVE_THRESHOLD},
        "cutoffs_with_at_least_one_computable_R": with_computable_r,
        "cutoffs_total": cutoffs_total,
        "local_panels_are_not_the_bottleneck": with_computable_r == cutoffs_total,
        "status_ordering_note": (
            "score_candidate labels a candidate by the FIRST gate it fails, so FAILS_SURVIVAL is "
            "undercounted while the quality gate binds. Loosening min_quality does not admit "
            "everything: it exposes the P_survive gate underneath, which is why a very loose "
            "quality threshold still leaves many cutoffs with nothing admissible."),
        "registered_gate_is_the_primary_and_is_not_revised": True,
        "grid": rows,
        "what_this_cannot_say": (
            "eligibility is re-derived from stored G and P_survive, so this shows only how often a "
            "looser gate would have left arm B something to choose. It does NOT simulate the "
            "outcome of choosing it and is not evidence that a looser gate performs better."),
        "why_it_is_reported": (
            "the registered gate bound at half of all cutoffs; a reader cannot weigh the result "
            "without that, and hiding it would make the retention rate look like a property of the "
            "market rather than of a threshold the lab chose"),
    }


def _contrast_excluding_stuck(run_cells: list[dict], never_switched: dict) -> dict:
    """The contrast restricted to cells where BOTH arms actually ran their selector.

    This is the question the phase is really asking. A cell where an arm held the
    registered seed point for the whole evaluation compares a fixed point against a
    selector, not two selectors, so it belongs in a separate line.
    """
    excluded = {row["cell"] for arm in ARMS
                for row in never_switched[arm]["detail"]}
    kept = [c for c in run_cells if f"{c['alpha_id']}/{c['symbol']}" not in excluded]
    pairs = [(f"{c['alpha_id']}/{c['symbol']}",
              c["arms"]["A"]["net_return"], c["arms"]["B"]["net_return"])
             for c in kept
             if c["arms"]["A"].get("net_return") is not None
             and c["arms"]["B"].get("net_return") is not None]
    diffs = [b - a for _, a, b in pairs]
    daily = [_daily_difference(c, CALENDAR.test_days) for c in kept]
    return {
        "cells_excluded": sorted(excluded),
        "cells_kept": len(pairs),
        "sign_test": _sign_test(pairs),
        "mean_net_return_difference": _mean_or_none(diffs),
        "mean_daily_net_return_difference": _mean_or_none(daily),
        "reading": ("the same contrast with every cell removed in which an arm never exercised its "
                    "selector. If the effect lives mostly in the excluded cells, the phase measured "
                    "holding still rather than selecting well."),
    }


def _observed_budget(run_cells: list[dict]) -> dict:
    """The search budget the cells actually recorded, plus any drift from the current default."""
    seen: dict[str, set] = {}
    for cell in run_cells:
        for fold in cell.get("folds", []):
            evidence = fold.get("cutoff_evidence")
            if not evidence:
                continue
            for key, value in evidence["budget"].items():
                if isinstance(value, (int, float, str, bool)) or value is None:
                    seen.setdefault(key, set()).add(value)
    observed = {key: (sorted(values)[0] if len(values) == 1 else sorted(values))
                for key, values in sorted(seen.items())
                if key in asdict(BUDGET) or key == "nominal_total"}
    # a design field absent from every cell means those cells predate it
    for key, value in asdict(BUDGET).items():
        observed.setdefault(key, None)
    current = {**asdict(BUDGET), "nominal_total": BUDGET.nominal_total}
    drift = {key: {"in_cells": observed.get(key), "module_default_now": value}
             for key, value in current.items()
             if key in observed and observed[key] is not None and observed[key] != value}
    observed["nominal_total"] = observed.get("nominal_total") or current["nominal_total"]
    observed["module_default_now"] = current
    observed["differs_from_module_default"] = drift
    observed["provenance_rule"] = (
        "these values are read back out of the cells themselves. A field reported as null was not "
        "recorded by the run that produced them, which means those cells predate that design "
        "field and were NOT built with it.")
    return observed


def _load_registration() -> tuple[dict, dict, dict]:
    study = json.loads((CONFIG_DIR / "study_registration.json").read_text())
    effect = json.loads((CONFIG_DIR / "minimum_economic_effect.json").read_text())
    hypotheses = json.loads((CONFIG_DIR / "hypothesis_registry.json").read_text())
    return study, effect, hypotheses


def _daily_difference(cell: dict, test_days: int) -> float | None:
    """The REGISTERED primary endpoint for one cell.

    study_registration.primary_endpoint: "mean daily net-return difference between
    arms on the same risk budget". Each fold's net return is measured against the
    same frozen capital, so summing the per-fold differences and dividing by the
    days they cover gives that statistic directly. Terminal chained return is NOT
    the endpoint and must not be substituted for it.
    """
    a = cell["arms"]["A"].get("fold_returns")
    b = cell["arms"]["B"].get("fold_returns")
    if not a or not b or len(a) != len(b):
        return None
    days = len(a) * test_days
    if days <= 0:
        return None
    return float(sum(bi - ai for ai, bi in zip(a, b)) / days)


def _registered_hypothesis(run_cells: list[dict], all_cells: list[dict]) -> dict:
    """Tie this phase's result back to the hypothesis registered BEFORE it ran.

    LAB-04 evaluates exactly one registered contrast, H1 = B - A. The conclusion
    level is drawn from the registered vocabulary, never invented here, and the
    registered minimum economic effect decides whether a difference is an edge or
    sits inside the cost-stress band.
    """
    study, effect, hypotheses = _load_registration()
    h1 = next(h for h in hypotheses["primary_contrasts"] if h["id"] == "H1")
    threshold = float(effect["minimum_daily_net_return_difference"])
    test_days = CALENDAR.test_days

    per_cell = []
    for cell in run_cells:
        value = _daily_difference(cell, test_days)
        if value is None:
            continue
        per_cell.append({"cell": f"{cell['alpha_id']}/{cell['symbol']}",
                         "daily_difference": _finite(value),
                         "above_minimum_effect": abs(value) >= threshold})
    values = [row["daily_difference"] for row in per_cell]
    mean_daily = _mean_or_none(values)
    above = sum(1 for row in per_cell if row["above_minimum_effect"])

    split = _contrast_by_alpha(run_cells)
    reversals = split.get("reversals", [])
    confounds = _confounds(
        {arm: {"retained": sum(1 for c in run_cells for f in c["folds"]
                               if f.get("status") == "OK"
                               and f["arms"][arm]["retained_incumbent"]),
               "cutoffs": sum(1 for c in run_cells for f in c["folds"]
                              if f.get("status") == "OK"),
               "reasons": {}} for arm in ARMS},
        run_cells)

    expected_cells = len(ALPHA_ORDER_DEFAULT) * len(SYMBOL_ORDER_DEFAULT)
    blockers = []
    if len(all_cells) != expected_cells:
        blockers.append(f"the primary matrix is incomplete ({len(all_cells)}/{expected_cells})")
    if reversals:
        blockers.append(f"the sign reverses inside {', '.join(reversals)}")
    if confounds["asymmetric_switching_is_material"]:
        blockers.append("the arms switched parameters at materially different rates, so the "
                        "contrast mixes selection quality with switching frequency")
    stuck = _never_switched(run_cells)
    stuck_cells = sum(stuck[arm]["cells"] for arm in ARMS)
    if stuck_cells:
        blockers.append(
            f"{stuck_cells} of {len(run_cells)} cells had an arm that never exercised its selector "
            "at any cutoff, so part of this contrast compares a fixed seed point against a "
            "selector rather than two selectors")

    # Precedence matters. The registered rule for a below-threshold effect is
    # explicit -- "reported as inconclusive, not as an edge" -- so the threshold is
    # checked BEFORE the blockers. Blockers can only make a conclusion weaker; they
    # can never promote a difference that sits inside the cost-stress band.
    if len(all_cells) != expected_cells:
        level = "FAILED_VALIDITY"
    elif mean_daily is None:
        level = "INCONCLUSIVE_SAMPLE"
    elif abs(mean_daily) < threshold:
        level = "INCONCLUSIVE_SAMPLE"
    elif blockers:
        level = "DESCRIPTIVE_VALUE"
    else:
        level = "NET_PARAMETER_SELECTION_EDGE"
    assert level in hypotheses["conclusion_levels"], level

    return {
        "hypothesis_id": h1["id"], "contrast": h1["contrast"], "question": h1["question"],
        "registered_at_utc": hypotheses["registered_at_utc"],
        "primary_endpoint": study["primary_endpoint"]["statistic"],
        "endpoint_note": ("terminal chained return is reported elsewhere for context; it is NOT "
                          "the registered endpoint and is not used to decide the conclusion"),
        "minimum_economic_effect_per_day": threshold,
        "minimum_economic_effect_bps_per_day": effect["minimum_daily_net_return_bps"],
        "minimum_effect_registered_before_any_comparison":
            effect["registered_before_any_arm_comparison"],
        "mean_daily_net_return_difference": mean_daily,
        "cells_above_the_minimum_effect": above,
        "cells_measured": len(per_cell),
        "per_cell": per_cell,
        "conclusion_level": level,
        "conclusion_level_vocabulary": hypotheses["conclusion_levels"],
        "blockers_preventing_a_stronger_claim": blockers,
        "level_rule": ("matrix incomplete -> FAILED_VALIDITY; effect inside the registered "
                       "cost-stress band -> INCONCLUSIVE_SAMPLE; otherwise blockers cap it at "
                       "DESCRIPTIVE_VALUE; only a clean, above-threshold result may be called an "
                       "edge"),
        "family_adjustment": study["hypothesis_family_and_adjustment"]["adjustment"],
        "family_adjustment_applied": False,
        "family_adjustment_note": ("H1 is one member of a five-contrast primary family; the "
                                   "Holm-type adjustment and the paired block bootstrap are "
                                   "applied in LAB-09 once the other arms exist. No adjusted "
                                   "p-value is claimed here."),
        "falsification_commitments_in_force": hypotheses["falsification_commitments"],
        "commitment_exercised": (
            "zero switches because no challenger qualified is a valid technical pass -- arm B "
            "retained the incumbent wherever no candidate cleared the registered gates, and that "
            "is reported as a pass, not repaired by loosening a threshold"),
    }


def _contrast_by_alpha(run_cells: list[dict]) -> dict:
    """B - A split per alpha.

    A pooled sign test over a mixed matrix can report a clean win while the sign
    is actually reversed inside one of the alphas. Guide 13.6 forbids a "better on
    every dimension" claim built from one aggregate, so the split is reported
    whether or not it is convenient.
    """
    by_alpha: dict[str, list[dict]] = {}
    for cell in run_cells:
        by_alpha.setdefault(cell["alpha_id"], []).append(cell)
    out = {}
    for alpha_id, cells in sorted(by_alpha.items()):
        pairs = [(f"{c['alpha_id']}/{c['symbol']}",
                  c["arms"]["A"]["net_return"], c["arms"]["B"]["net_return"])
                 for c in cells
                 if c["arms"]["A"].get("net_return") is not None
                 and c["arms"]["B"].get("net_return") is not None]
        if not pairs:
            continue
        diffs = [b - a for _, a, b in pairs]
        test = _sign_test(pairs)
        out[alpha_id] = {
            "cells": test["cells"], "B_better": test["B_better"],
            "A_better": test["A_better"],
            "mean_difference": _mean_or_none(diffs),
            "median_difference": _finite(float(np.median(diffs))) if diffs else None,
            "sign_agrees_with_the_pooled_result": None,   # filled below
        }
    pooled_sign = None
    all_pairs = [(f"{c['alpha_id']}/{c['symbol']}",
                  c["arms"]["A"]["net_return"], c["arms"]["B"]["net_return"])
                 for c in run_cells
                 if c["arms"]["A"].get("net_return") is not None
                 and c["arms"]["B"].get("net_return") is not None]
    if all_pairs:
        pooled = _sign_test(all_pairs)
        pooled_sign = "B" if pooled["B_better"] > pooled["A_better"] else (
            "A" if pooled["A_better"] > pooled["B_better"] else "tie")
    for alpha_id, record in out.items():
        local = "B" if record["B_better"] > record["A_better"] else (
            "A" if record["A_better"] > record["B_better"] else "tie")
        record["winner"] = local
        record["sign_agrees_with_the_pooled_result"] = (local == pooled_sign)
    out["pooled_winner"] = pooled_sign
    out["reading"] = (
        "an alpha whose sign disagrees with the pooled result is a reversal, not noise to be "
        "averaged away. The pooled sign test must never be quoted on its own where a reversal "
        "exists (guide 13.6).")
    out["reversals"] = sorted(
        alpha_id for alpha_id, record in out.items()
        if isinstance(record, dict) and record.get("sign_agrees_with_the_pooled_result") is False)
    return out


def _confounds(retention: dict, run_cells: list[dict]) -> dict:
    """What else could explain a B-minus-A difference, stated before it is claimed.

    The one that matters here: arm B declines to switch whenever no candidate has
    enough local evidence. If it declines often, part of any advantage is "changed
    the parameters less", which is a different mechanism from "chose better", and
    the two are not separated by this experiment.
    """
    rates = {arm: (record["retained"] / record["cutoffs"]) if record["cutoffs"] else None
             for arm, record in retention.items()}
    gap = None
    if rates.get("A") is not None and rates.get("B") is not None:
        gap = abs(rates["B"] - rates["A"])
    material = bool(gap is not None and gap >= 0.2)
    return {
        "incumbent_retention_rate": rates,
        "retention_rate_gap": _finite(gap),
        "asymmetric_switching_is_material": material,
        "what_it_means": (
            "arm B kept the incumbent at a materially different rate from arm A, so any B-A "
            "difference mixes TWO mechanisms: choosing a better point, and changing the point "
            "less often. This experiment does not separate them."
            if material else
            "the two arms switched parameters at a similar rate, so the contrast is not obviously "
            "explained by switching frequency alone"),
        "control_that_would_separate_them": (
            "a HOLD control on the same calendar that never re-selects after the first cutoff. It "
            "is registered in the LAB-06 control family (CALENDAR_MATCHED / RISK_ONLY) and is NOT "
            "run here; until it is, no causal claim about the selector is available"),
        "not_run_here": True,
    }


def _fmt(value) -> str:
    return "null" if value is None else f"{value:+.4f}"


def _verdict(returns, sharpes, mean_diff) -> str:
    if not returns:
        return "NO_COMPARABLE_CELLS: no cell produced a deployment for both arms"
    sign = _sign_test(returns)
    if sign["B_better"] > sign["A_better"] and (sign["two_sided_sign_test_p"] or 1.0) < 0.05:
        return (f"B beat A on net return in {sign['B_better']}/{sign['cells']} cells "
                f"(sign-test p={sign['two_sided_sign_test_p']:.3f}); this is a descriptive "
                "calendar-baseline result on the development role, not a confirmatory claim")
    if sign["A_better"] > sign["B_better"] and (sign["two_sided_sign_test_p"] or 1.0) < 0.05:
        return (f"A beat B on net return in {sign['A_better']}/{sign['cells']} cells "
                f"(sign-test p={sign['two_sided_sign_test_p']:.3f}); the neighborhood selector did "
                "NOT improve stable performance here and is not adopted on this evidence")
    return (f"no separation: B better in {sign['B_better']} cells, A better in "
            f"{sign['A_better']}, sign-test p={sign['two_sided_sign_test_p']}. The neighborhood "
            "selector is not shown to improve stable performance on this calendar; both arms are "
            "kept for the factorial rather than defaulting to the new selector")


def _with_confound_caveat(verdict: str, confounds: dict) -> str:
    if not confounds.get("asymmetric_switching_is_material"):
        return verdict
    return (verdict + " CAVEAT: " + confounds["what_it_means"] + " "
            + confounds["control_that_would_separate_them"] + ".")
