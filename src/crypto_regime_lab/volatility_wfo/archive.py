"""VWFO-02 Candidate Archive & Sharpe-decay Labels Module.

Manages base panel selection (<= 16 candidates via IS-only rule),
forward evaluation (FWD14) via QuantBT native event account,
computation of Sharpe decay labels D = SR_IS - SR_FWD and Y = D - D_anchor,
and past-only matured archive querying.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from quantbt.walkforward import WalkForwardTrialRecord

from ..experiments.dynamic_fold_provider import engine_param_ranges
from ..integration.continuous_account import VersionWindow
from ..integration.event_account import run_event_account
from .search import compute_annualized_sharpe


def select_base_panel(
    records: Sequence[WalkForwardTrialRecord],
    anchor_record: WalkForwardTrialRecord,
    *,
    max_panel_size: int = 16,
    top_quota: int = 6,
    diversity_quota: int = 5,
    controls_quota: int = 4,
) -> list[dict[str, Any]]:
    """Select up to 16 candidates using the strict IS-only stratified rule.

    1. Stock Mode 4 anchor (Rank 1).
    2. Top IS Sharpe candidates (up to top_quota).
    3. Parameter diversity candidates covering parameter space (up to diversity_quota).
    4. Mid/lower-rank controls (up to controls_quota).
    All candidates are deduplicated by parameter key.
    """
    completed = [r for r in records if not r.pruned and np.isfinite(r.objective) and np.isfinite(r.mean_is_sharpe)]
    if not completed:
        return []

    # Sort descending by IS Sharpe
    ranked = sorted(completed, key=lambda r: r.mean_is_sharpe, reverse=True)

    panel: list[dict[str, Any]] = []
    seen_params: set[str] = set()

    def _key(params: dict[str, Any]) -> str:
        return json.dumps(params, sort_keys=True)

    # 1. Anchor
    anchor_key = _key(anchor_record.params)
    panel.append({
        "trial_id": int(anchor_record.trial_id),
        "params": dict(anchor_record.params),
        "is_sharpe": float(anchor_record.mean_is_sharpe),
        "objective": float(anchor_record.objective),
        "role": "STOCK_MODE4_ANCHOR",
        "is_anchor": True,
        "selection_metadata": dict(anchor_record.selection_metadata),
    })
    seen_params.add(anchor_key)

    # 2. Top IS Sharpe candidates
    top_added = 0
    for r in ranked:
        k = _key(r.params)
        if k not in seen_params:
            panel.append({
                "trial_id": int(r.trial_id),
                "params": dict(r.params),
                "is_sharpe": float(r.mean_is_sharpe),
                "objective": float(r.objective),
                "role": "TOP_IS_SHARPE",
                "is_anchor": False,
                "selection_metadata": dict(r.selection_metadata),
            })
            seen_params.add(k)
            top_added += 1
            if top_added >= top_quota:
                break

    # 3. Parameter diversity candidates
    # Normalize parameter dimensions to compute Euclidean distance in parameter space
    remaining = [r for r in ranked if _key(r.params) not in seen_params]
    div_added = 0
    if remaining:
        # Distance to already chosen panel candidates
        def _norm_dist(p1: dict, p2: dict) -> float:
            # coeff: 1..8 -> range 7
            # AP: 5..60 -> range 55
            # threshold: 30..80 -> range 50
            d_c = (p1.get("coeff", 1) - p2.get("coeff", 1)) / 7.0
            d_ap = (p1.get("AP", 5) - p2.get("AP", 5)) / 55.0
            d_th = (p1.get("alpha.condition_threshold", 30) - p2.get("alpha.condition_threshold", 30)) / 50.0
            return float(math.sqrt(d_c**2 + d_ap**2 + d_th**2))

        while div_added < diversity_quota and remaining:
            # Pick candidate that maximizes minimum distance to all existing panel members
            best_cand = None
            max_min_dist = -1.0
            best_idx = -1
            for idx, cand in enumerate(remaining):
                min_dist = min(_norm_dist(cand.params, p["params"]) for p in panel)
                if min_dist > max_min_dist:
                    max_min_dist = min_dist
                    best_cand = cand
                    best_idx = idx

            if best_cand is not None and best_idx >= 0:
                k = _key(best_cand.params)
                panel.append({
                    "trial_id": int(best_cand.trial_id),
                    "params": dict(best_cand.params),
                    "is_sharpe": float(best_cand.mean_is_sharpe),
                    "objective": float(best_cand.objective),
                    "role": "PARAMETER_DIVERSITY",
                    "is_anchor": False,
                    "selection_metadata": dict(best_cand.selection_metadata),
                })
                seen_params.add(k)
                remaining.pop(best_idx)
                div_added += 1
            else:
                break

    # 4. Controls: mid and lower rank candidates
    remaining_by_sr = [r for r in ranked if _key(r.params) not in seen_params]
    if remaining_by_sr and len(panel) < max_panel_size:
        # Pick 2 around 50th percentile, 2 around 25th percentile
        n_rem = len(remaining_by_sr)
        target_indices = [
            int(n_rem * 0.4),
            int(n_rem * 0.5),
            int(n_rem * 0.7),
            int(n_rem * 0.85),
        ]
        target_indices = sorted(list(set(min(idx, n_rem - 1) for idx in target_indices)))
        for t_idx in target_indices:
            if len(panel) >= max_panel_size:
                break
            cand = remaining_by_sr[t_idx]
            k = _key(cand.params)
            if k not in seen_params:
                panel.append({
                    "trial_id": int(cand.trial_id),
                    "params": dict(cand.params),
                    "is_sharpe": float(cand.mean_is_sharpe),
                    "objective": float(cand.objective),
                    "role": "CONTROL_MID_LOW",
                    "is_anchor": False,
                    "selection_metadata": dict(cand.selection_metadata),
                })
                seen_params.add(k)

    return panel[:max_panel_size]


def build_forward_evaluation_union(
    base_panel: Sequence[dict[str, Any]],
    registered_winners: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build union of base panel and any registered arm winners."""
    union = list(base_panel)
    seen_keys = {json.dumps(p["params"], sort_keys=True) for p in base_panel}

    for winner in registered_winners or []:
        k = json.dumps(winner["params"], sort_keys=True)
        if k not in seen_keys:
            w_copy = dict(winner)
            w_copy["role"] = "REGISTERED_WINNER_EXTENSION"
            union.append(w_copy)
            seen_keys.add(k)

    return union


def evaluate_candidates_forward(
    frame_15m: pd.DataFrame,
    candidates: Sequence[dict[str, Any]],
    fwd_start: pd.Timestamp,
    fwd_end: pd.Timestamp,
    *,
    initial_capital: float = 20000.0,
    one_way_fee: float = 0.0004,
    slippage_bps: float = 1.0,
    cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate candidate union on the 14-day forward window using QuantBT native event account."""
    fwd_mask = (frame_15m.index >= fwd_start) & (frame_15m.index < fwd_end)
    fwd_data = frame_15m.loc[fwd_mask]

    if len(fwd_data) < 14:
        raise RuntimeError(f"Insufficient bars for forward evaluation in [{fwd_start}, {fwd_end})")

    results: list[dict[str, Any]] = []

    for cand in candidates:
        params = cand["params"]
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "params": params,
                    "fwd_start": fwd_start.isoformat(),
                    "fwd_end": fwd_end.isoformat(),
                    "fee": one_way_fee,
                    "slippage": slippage_bps,
                    "capital": initial_capital,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        if cache is not None and cache_key in cache:
            eval_data = cache[cache_key]
        else:
            initial = VersionWindow("fwd-eval", params, 0, "initial", required_warm_bars=None)
            try:
                run = run_event_account(
                    "A-SC",
                    fwd_data,
                    initial=initial,
                    schedule=[],
                    initial_capital=initial_capital,
                    one_way_fee=one_way_fee,
                    slippage_bps=slippage_bps,
                    report_level="score",
                )
                equity_series = pd.Series(run.equity, index=fwd_data.index)
                daily_equity = equity_series.resample("1D").last().ffill().dropna()
                daily_returns = daily_equity.pct_change().dropna().to_numpy()
                fwd_sharpe = compute_annualized_sharpe(daily_returns, trading_days=365)

                eval_data = {
                    "status": run.status,
                    "fwd_sharpe": float(fwd_sharpe),
                    "daily_fwd_returns": [float(r) for r in daily_returns],
                    "fills_count": len(run.fills),
                    "entries": run.entries,
                    "final_equity": float(equity_series.iloc[-1]) if len(equity_series) else initial_capital,
                }
            except Exception as exc:
                eval_data = {
                    "status": "FAILED_CANDIDATE",
                    "reason": f"{type(exc).__name__}: {exc}"[:200],
                    "fwd_sharpe": 0.0,
                    "daily_fwd_returns": [],
                    "fills_count": 0,
                    "entries": 0,
                    "final_equity": initial_capital,
                }

            if cache is not None:
                cache[cache_key] = eval_data

        merged = dict(cand)
        merged.update(eval_data)
        results.append(merged)

    return results


def compute_sharpe_decay_labels(
    forward_evaluations: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute Sharpe decay D = SR_IS - SR_FWD and relative decay Y = D - D_anchor.

    By definition:
    - D_{k, theta} = SR_{IS180, k, theta} - SR_{FWD14, k, theta}
    - D_{k, anchor} = SR_{IS180, k, anchor} - SR_{FWD14, k, anchor}
    - Y_{k, theta} = D_{k, theta} - D_{k, anchor}  (anchor structurally has Y = 0.0)
    - Q_{k, theta} = SR_{FWD, k, theta} - SR_{FWD, k, anchor} = SR_{IS, theta} - SR_{IS, anchor} - Y_{theta}
    """
    # Find anchor
    anchor_eval = next((e for e in forward_evaluations if e.get("is_anchor")), None)
    if anchor_eval is None:
        raise ValueError("Forward evaluations contain no anchor candidate")

    anchor_is_sharpe = float(anchor_eval.get("is_sharpe", 0.0))
    anchor_fwd_sharpe = float(anchor_eval.get("fwd_sharpe", 0.0))
    d_anchor = anchor_is_sharpe - anchor_fwd_sharpe

    labeled: list[dict[str, Any]] = []

    for e in forward_evaluations:
        row = dict(e)
        is_sr = float(row.get("is_sharpe", 0.0))
        fwd_sr = float(row.get("fwd_sharpe", 0.0))

        d_theta = is_sr - fwd_sr
        y_theta = d_theta - d_anchor
        q_theta = fwd_sr - anchor_fwd_sharpe

        if row.get("is_anchor"):
            y_theta = 0.0  # strictly 0.0 by identity

        row["decay_d"] = float(d_theta)
        row["relative_decay_y"] = float(y_theta)
        row["relative_gain_q"] = float(q_theta)
        row["anchor_decay_d"] = float(d_anchor)
        labeled.append(row)

    return labeled


@dataclass
class CandidateArchive:
    """Expanding shared archive of forward-evaluated candidate records.

    Exposes only matured records as of any given timestamp.
    """

    records: list[dict[str, Any]] = field(default_factory=list)

    def append_origin_records(
        self,
        origin_cutoff: str,
        sampler_id: str,
        labeled_candidates: Sequence[dict[str, Any]],
        *,
        cadence_days: int = 14,
    ) -> None:
        """Append records from one completed origin."""
        cutoff_dt = pd.Timestamp(origin_cutoff, tz="UTC")
        matured_at = (cutoff_dt + pd.Timedelta(days=cadence_days)).isoformat()

        for cand in labeled_candidates:
            rec = {
                "candidate_id": f"{origin_cutoff[:10]}_{sampler_id}_{cand.get('trial_id', 0):04d}",
                "origin_cutoff": origin_cutoff,
                "sampler_id": sampler_id,
                "matured_at": matured_at,
                "params": cand["params"],
                "role": cand.get("role", "PANEL_CANDIDATE"),
                "is_anchor": bool(cand.get("is_anchor", False)),
                "is_sharpe": float(cand.get("is_sharpe", 0.0)),
                "fwd_sharpe": float(cand.get("fwd_sharpe", 0.0)),
                "decay_d": float(cand.get("decay_d", 0.0)),
                "relative_decay_y": float(cand.get("relative_decay_y", 0.0)),
                "relative_gain_q": float(cand.get("relative_gain_q", 0.0)),
                "status": cand.get("status", "EVALUATED"),
                "daily_fwd_returns": cand.get("daily_fwd_returns", []),
                "fills_count": int(cand.get("fills_count", 0)),
                "entries": int(cand.get("entries", 0)),
                "final_equity": float(cand.get("final_equity", 20000.0)),
                "objective": float(cand.get("objective", 0.0)),
            }
            self.records.append(rec)

    def get_matured_archive(
        self,
        as_of: str | pd.Timestamp,
        sampler_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return strictly matured records as of timestamp ``as_of``."""
        as_of_dt = pd.Timestamp(as_of, tz="UTC")
        filtered = []
        for r in self.records:
            mat_dt = pd.Timestamp(r["matured_at"], tz="UTC")
            if mat_dt <= as_of_dt:
                if sampler_id is None or r["sampler_id"] == sampler_id:
                    filtered.append(copy.deepcopy(r))
        return filtered

    def get_all_records(self, sampler_id: str | None = None) -> list[dict[str, Any]]:
        """Return all stored records."""
        if sampler_id is None:
            return copy.deepcopy(self.records)
        return [copy.deepcopy(r) for r in self.records if r["sampler_id"] == sampler_id]

    def compute_origin_weights(
        self,
        matured_records: Sequence[dict[str, Any]],
    ) -> dict[str, float]:
        """Compute normalized weights per candidate record.

        Equal weight per origin: sum of candidate weights for each origin equals 1 / K.
        Non-anchor candidates inside an origin share equal weights.
        """
        if not matured_records:
            return {}

        origins = sorted(list(set(r["origin_cutoff"] for r in matured_records)))
        k_origins = len(origins)
        if k_origins == 0:
            return {}

        weight_per_origin = 1.0 / k_origins
        weights: dict[str, float] = {}

        for orig in origins:
            orig_recs = [r for r in matured_records if r["origin_cutoff"] == orig]
            # Non-anchor candidates are informative for learning relative decay Y
            non_anchors = [r for r in orig_recs if not r["is_anchor"]]
            n_non_anchors = len(non_anchors)

            if n_non_anchors > 0:
                cand_weight = weight_per_origin / n_non_anchors
                for r in orig_recs:
                    cid = r["candidate_id"]
                    weights[cid] = 0.0 if r["is_anchor"] else cand_weight
            else:
                # If only anchor exists, assign origin weight to anchor
                for r in orig_recs:
                    weights[r["candidate_id"]] = weight_per_origin / len(orig_recs)

        return weights

    def to_json(self) -> str:
        return json.dumps(self.records, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> CandidateArchive:
        records = json.loads(json_str)
        return cls(records=records)
