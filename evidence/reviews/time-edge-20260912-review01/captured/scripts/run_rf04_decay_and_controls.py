#!/usr/bin/env python
"""RF-04.3/RF-04.4 — decay panels (D1/D2/D3), matched calendar control and funnel.

Builds on the committed bounded paired pilot
(``evidence/corrective_mode4_v3/RF-04/paired_discovery_pilot.json``):

* registers all control/anchor rules BEFORE any control run
  (``controls_registration.json``);
* runs the mandatory ``M4_CAL_MATCHED`` budget control: six evenly spaced
  calendar cutoffs (100-day cadence from the primary calendar first cutoff) on
  the SAME machinery as the pilot (``dynamic_fold_provider`` +
  ``run_rf04_paired_pilot``), same cells, budget, seed, economics and dates;
* optionally runs the registered delayed-state placebo (emission ``available_at``
  shifted by 14 days) only if the bounded budget allows, otherwise records
  ``REGISTERED_NOT_RUN`` with a reason;
* replays the registered D2 anchor subset (fold-0 selection of M4_CAL and
  M4_REGIME per cell) through the actual native-event QuantBT account with the
  frozen parameter vector, over three fixed 90-day age windows, and records
  ``null`` + reason for any run that cannot execute;
* reconstructs D1 (IS objective vs post-selection OOS, raw and penalized kept
  separate) and D3 (adjacent operational fold change) from the pilot/control
  account ledgers only;
* writes ``RF-04/decay_panels.json`` and ``RF-04/controls_and_funnel.json`` with
  denominators, units, validity statuses, null reasons and the decision funnel.

No number is invented: every financial value comes from an engine account
(equity/fills/trial ledger) or is a deterministic function of saved values.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

import run_rf04_paired_pilot as pilot  # noqa: E402  (the pilot's own machinery)

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments.dynamic_fold_provider import (  # noqa: E402
    ACCOUNT_CAPITAL,
    ALLOC_PER_TRADE,
    ONE_WAY_TAKER_FEE,
    SLIPPAGE_BPS,
    CutoffSchedule,
    regime_cutoffs,
)
from crypto_regime_lab.experiments.regime_schedule import online_trigger_schedule  # noqa: E402
from crypto_regime_lab.integration.activation import parameter_digest  # noqa: E402
from crypto_regime_lab.integration.continuous_account import VersionWindow  # noqa: E402
from crypto_regime_lab.integration.event_account import run_event_account  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "RF-04"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / RUN_ID

MATCHED_ARM = "M4_CAL_MATCHED"
PLACEBO_ARM = "M4_REGIME_DELAYED"
MATCHED_CADENCE_DAYS = 100
MATCHED_REFITS = 6
PLACEBO_DELAY_DAYS = 14
AGE_H_DAYS = 90
AGE_HORIZONS = 3
PRIMARY_ARMS = ("M4_CAL", "M4_REGIME")
ALL_ARMS = PRIMARY_ARMS + (MATCHED_ARM, PLACEBO_ARM)

BLOCK_BOOTSTRAP = {"block_days": 5, "resamples": 2000, "seed": 20260911}

MATCHED_RULE = (
    "six evenly spaced calendar cutoffs at a fixed 100-day cadence from the primary "
    "calendar first cutoff 2021-01-01 (2021-01-01, 2021-04-11, 2021-07-20, 2021-10-28, "
    "2022-02-05, 2022-05-16), chosen in development before this run to match the 6 refits "
    "of the causal controller while keeping every fold's evaluation segment non-empty"
)

PLACEBO_RULE = (
    "the causal controller reads the same emission tape with every emission's available_at "
    "shifted forward by 14 calendar days; the controller, training memory, budget, seed, "
    "economics and evaluation dates are otherwise identical to M4_REGIME"
)

ANCHOR_RULE = (
    "the registered anchor subset is the FIRST selection (fold 0) of each primary arm on "
    "each cell; parameters are frozen from that selection and replayed through the actual "
    "native-event QuantBT account over H1=[0,90), H2=[90,180), H3=[180,270) days after the "
    "selection cutoff. The rule uses the earliest selection only and cannot select anchors "
    "by how they decay"
)


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ts(value) -> pd.Timestamp:
    moment = pd.Timestamp(value)
    return moment.tz_localize("UTC") if moment.tzinfo is None else moment


def equity_series(account: dict | None) -> pd.Series:
    if not account:
        return pd.Series(dtype=float)
    rows = account.get("equity_daily") or []
    if not rows:
        return pd.Series(dtype=float)
    index = pd.DatetimeIndex([ts(row[0]) for row in rows])
    return pd.Series([float(row[1]) for row in rows], index=index, dtype=float)


def daily_metrics(equity: pd.Series, start, end, *, min_obs: int = 2) -> dict:
    """Canonical daily account metrics on a half-open-ish [start, end] window.

    The first day's return uses the last daily equity BEFORE the window, so the
    first observation is charged to the window rather than dropped (plan 6.2).
    """
    lo, hi = ts(start), ts(end)
    returns = equity.pct_change().dropna()
    inside = returns.loc[(returns.index >= lo) & (returns.index <= hi)]
    observed = int(inside.size)
    out: dict = {
        "start": str(lo), "end": str(hi), "observed_days": observed,
        "mean_daily_return_bps": None, "sharpe": None, "profit_factor_daily": None,
        "max_drawdown_pct": None, "status": "VALID", "reasons": [],
    }
    if observed < min_obs:
        out["status"] = "INSUFFICIENT_OBSERVATIONS"
        out["reasons"].append(f"{observed} daily returns < {min_obs}")
    else:
        mean = float(inside.mean())
        sd = float(inside.std(ddof=1))
        out["mean_daily_return_bps"] = mean * 1e4
        if sd > 0.0:
            out["sharpe"] = float(mean / sd * np.sqrt(365.0))
        else:
            out["reasons"].append("ZERO_VARIANCE")
        gains = float(inside[inside > 0.0].sum())
        losses = float(-inside[inside < 0.0].sum())
        if losses > 0.0 and gains > 0.0:
            out["profit_factor_daily"] = gains / losses
        elif losses == 0.0 and gains > 0.0:
            out["reasons"].append("NO_LOSS_DENOMINATOR")
        else:
            out["reasons"].append("NO_TRADES")
    before = equity.loc[equity.index < lo]
    curve = pd.concat([before.iloc[-1:], equity.loc[(equity.index >= lo) & (equity.index <= hi)]])
    if len(curve) > 1:
        peak = curve.cummax()
        drawdown = (peak - curve) / peak.replace(0.0, np.nan)
        value = float(drawdown.max() * 100.0)
        out["max_drawdown_pct"] = value if np.isfinite(value) else None
    if out["status"] == "VALID" and out["reasons"]:
        out["status"] = "VALID_WITH_FLAGS"
    return out


def fold_window(arm: dict, fold_id: int) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    for row in arm.get("fold_selection_table", []):
        if int(row["fold_id"]) == int(fold_id):
            return ts(row["test_start"]), ts(row["test_end"])
    return None


def matching_trial(arm: dict, fold_id: int, selected: dict) -> dict | None:
    for trial in arm.get("trial_records", []):
        if int(trial.get("schedule_fold_id", -1)) == int(fold_id) and trial.get("params") == selected:
            return trial
    return None


def fold_trade_count(cell: dict, arm: dict, frame: pd.DataFrame,
                     window: tuple[pd.Timestamp, pd.Timestamp]) -> tuple[int | None, str]:
    fills = (arm.get("account") or {}).get("fills") or []
    if not fills:
        source = (arm.get("account") or {}).get("fills_source")
        if (arm.get("account") or {}).get("engine_report", {}).get("num_trades") is not None:
            return None, f"NO_PER_FILL_RECORDS:{source or 'unknown'}"
        return None, "NO_FILL_LEDGER"
    lo, hi = window
    count = 0
    for fill in fills:
        bar = int(fill.get("bar_index", -1))
        if 0 <= bar < len(frame):
            moment = frame.index[bar]
            if lo <= moment <= hi:
                count += 1
    return count, "FILL_LEDGER"


def digests_by_fold(arm: dict) -> dict[int, str]:
    return {int(key): parameter_digest(value)
            for key, value in (arm.get("params_by_fold") or {}).items()}


# ---------------------------------------------------------------------------
# emission tape diagnostics (same comparability rule as the controller)
# ---------------------------------------------------------------------------

def eligible_rows(emissions: list[dict], start, end) -> list[dict]:
    lo, hi = ts(start), ts(end)
    out = []
    for record in emissions:
        if not record.get("decision_eligible", True):
            continue
        if record.get("quality_status", "OK") not in ("OK",):
            continue
        moment = ts(record["available_at"])
        if lo <= moment <= hi:
            out.append(record)
    return out


def semantic_changes(emissions: list[dict]) -> list[pd.Timestamp]:
    """The controller's change rule: same namespace, or state_common on both sides."""
    changes: list[pd.Timestamp] = []
    previous: tuple[object, object, object] | None = None
    for record in emissions:
        moment = ts(record["available_at"])
        common = record.get("state_common")
        namespace = record.get("state_namespace")
        semantic = common if common is not None else record.get("state_id")
        if previous is not None:
            prev_common, prev_namespace, prev_semantic = previous
            comparable = (common is not None and prev_common is not None) or namespace == prev_namespace
            if comparable and semantic != prev_semantic:
                changes.append(moment)
        previous = (common, namespace, semantic)
    return changes


def state_at(rows: list[dict], moment: pd.Timestamp) -> dict | None:
    chosen = None
    for record in rows:
        if ts(record["available_at"]) <= moment:
            chosen = record
        else:
            break
    if chosen is None:
        return None
    return {"state_namespace": chosen.get("state_namespace"), "state_id": chosen.get("state_id")}


def window_regime(rows: list[dict], start, end) -> dict:
    lo, hi = ts(start), ts(end)
    inside = [r for r in rows if lo < ts(r["available_at"]) <= hi]
    states = sorted({(r.get("state_namespace"), r.get("state_id")) for r in inside},
                    key=lambda pair: (str(pair[0]), str(pair[1])))
    changes = [c for c in semantic_changes(rows) if lo < c <= hi]
    return {
        "states": [{"state_namespace": ns, "state_id": sid} for ns, sid in states],
        "transition_count": len(changes),
        "transition_times": [c.isoformat() for c in changes],
    }


def time_since_regime_change(rows: list[dict], moment: pd.Timestamp) -> tuple[float | None, str]:
    changes = [c for c in semantic_changes(rows) if c <= moment]
    if not changes:
        return None, "NO_PRIOR_SEMANTIC_CHANGE_IN_TAPE"
    return float((moment - changes[-1]).total_seconds() / 86400.0), "LAST_SEMANTIC_CHANGE"


# ---------------------------------------------------------------------------
# D1 / D3 panel rows
# ---------------------------------------------------------------------------

def d1_rows(cell: dict, arm_name: str, arm: dict, frame: pd.DataFrame,
            rows: list[dict]) -> list[dict]:
    equity = equity_series(arm.get("account"))
    selection_bias = ("the IS objective is selection-biased; D1 is a generalization-gap "
                      "diagnostic, not an unbiased decay estimator")
    out = []
    for row in arm.get("fold_selection_table", []):
        fold_id = int(row["fold_id"])
        window = fold_window(arm, fold_id)
        if window is None:
            continue
        selected = row.get("selected_params") or {}
        digest = parameter_digest(selected)
        trial = matching_trial(arm, fold_id, selected)
        metadata = dict((trial or {}).get("selection_metadata") or {})
        is_raw = (trial or {}).get("mean_is_sharpe")
        is_penalized = row.get("selected_is_objective")
        metrics = daily_metrics(equity, window[0], window[1])
        trades, trade_status = fold_trade_count(cell, arm, frame, window)
        regime_sel = state_at(rows, ts(row["test_start"]))
        regime_win = window_regime(rows, *window)
        common = {
            "selection_id": f"{cell['cell']}:{arm_name}:fold{fold_id}",
            "parameter_digest": digest,
            "alpha": cell["alpha_id"], "symbol": cell["symbol"], "arm": arm_name,
            "comparison_kind": "IS_TO_OOS",
            "left_start": row.get("train_start"), "left_end": row.get("train_end"),
            "right_start": row.get("test_start"), "right_end": row.get("test_end"),
            "observed_days": metrics["observed_days"],
            "raw_or_penalized": None, "penalty_components": None,
            "validity_status": None, "trade_count": trades, "trade_count_status": trade_status,
            "effective_sample": {"unit": "daily_returns", "value": metrics["observed_days"]},
            "regime_at_selection": regime_sel,
            "regime_in_window": regime_win,
            "in_sample_selection_bias": True, "in_sample_selection_bias_note": selection_bias,
            "diagnostic_only": True,
            "oos_metrics": metrics,
            "is_trial": {"trial_id": (trial or {}).get("trial_id"),
                         "mean_is_sharpe": is_raw,
                         "objective": (trial or {}).get("objective"),
                         "temporal_score": (trial or {}).get("temporal_score"),
                         "selected_is_objective": is_penalized},
        }
        # 1. Sharpe: raw IS Sharpe vs post-selection OOS Sharpe.
        out.append({**common, "metric_name": "sharpe", "unit": "annualised_daily_return_ratio",
                    "metric_definition": "sqrt(365)*mean(daily net return)/std(daily net return, ddof=1); "
                                         "the left value is the engine's raw IS mean_is_sharpe",
                    "raw_or_penalized": "raw",
                    "left_value": is_raw, "right_value": metrics["sharpe"],
                    "signed_delta": (None if is_raw is None or metrics["sharpe"] is None
                                     else float(is_raw) - float(metrics["sharpe"])),
                    "validity_status": ("VALID" if is_raw is not None and metrics["sharpe"] is not None
                                        else "IS_RAW_SHARPE_MISSING" if is_raw is None
                                        else f"OOS_{metrics['status']}"),
                    "penalty_components": None})
        # 2. Sharpe: penalized Mode 4 objective vs the same OOS Sharpe, kept separate.
        out.append({**common, "metric_name": "sharpe", "unit": "annualised_daily_return_ratio",
                    "metric_definition": "Mode 4 robust objective (is_only_robust) used for selection vs "
                                         "the same post-selection OOS daily Sharpe",
                    "raw_or_penalized": "penalized",
                    "left_value": is_penalized, "right_value": metrics["sharpe"],
                    "signed_delta": (None if is_penalized is None or metrics["sharpe"] is None
                                     else float(is_penalized) - float(metrics["sharpe"])),
                    "validity_status": ("VALID" if is_penalized is not None and metrics["sharpe"] is not None
                                        else "IS_PENALIZED_MISSING" if is_penalized is None
                                        else f"OOS_{metrics['status']}"),
                    "penalty_components": {
                        "temporal_score": metadata.get("temporal_score"),
                        "temporal_median": metadata.get("temporal_median"),
                        "temporal_q25": metadata.get("temporal_q25"),
                        "temporal_mad": metadata.get("temporal_mad"),
                        "temporal_count": metadata.get("temporal_count"),
                        "is_subperiod_count": metadata.get("is_subperiod_count"),
                        "objective_mode": metadata.get("objective_mode"),
                        "note": ("the trial ledger does not retain the plateau term separately; the "
                                 "recorded components are the temporal subperiod statistics"),
                    }})
        # 3. Return: IS account return is not in the engine trial ledger; null + reason.
        out.append({**common, "metric_name": "return", "unit": "account_bps/day",
                    "metric_definition": "mean daily net return of the continuous account",
                    "raw_or_penalized": "raw",
                    "left_value": None, "right_value": metrics["mean_daily_return_bps"],
                    "signed_delta": None,
                    "validity_status": "IS_ACCOUNT_RETURN_NOT_IN_TRIAL_LEDGER",
                    "oos_status": metrics["status"],
                    "left_null_reason": ("the engine Mode 4 ledger retains the IS Sharpe objective and "
                                         "temporal subperiod statistics, not an IS account return in "
                                         "account bps/day; no value is invented"),
                    "penalty_components": None})
        # 4. Profit factor: IS trade/daily PF not in the ledger; OOS daily PF is real.
        pf = metrics["profit_factor_daily"]
        out.append({**common, "metric_name": "profit_factor", "unit": "ratio",
                    "metric_definition": "PF_obs = sum(positive daily account returns)/"
                                         "abs(sum(negative daily account returns))",
                    "raw_or_penalized": "raw",
                    "left_value": None, "right_value": pf,
                    "signed_delta": None,
                    "validity_status": ("OOS_NO_LOSS_DENOMINATOR" if pf is None and
                                        "NO_LOSS_DENOMINATOR" in metrics["reasons"]
                                        else "OOS_NO_TRADES" if pf is None and
                                        "NO_TRADES" in metrics["reasons"]
                                        else "IS_PROFIT_FACTOR_NOT_IN_TRIAL_LEDGER" if pf is not None
                                        else f"OOS_{metrics['status']}"),
                    "left_null_reason": "IS profit factor is not retained in the Mode 4 trial ledger",
                    "penalty_components": None})
    return out


def d3_rows(cell: dict, arm_name: str, arm: dict, frame: pd.DataFrame) -> list[dict]:
    equity = equity_series(arm.get("account"))
    folds = sorted(int(row["fold_id"]) for row in arm.get("fold_selection_table", []))
    infos = {}
    for fold_id in folds:
        row = next(r for r in arm["fold_selection_table"] if int(r["fold_id"]) == fold_id)
        window = fold_window(arm, fold_id)
        metrics = daily_metrics(equity, window[0], window[1]) if window else None
        trades, trade_status = fold_trade_count(cell, arm, frame, window) if window else (None, "NO_WINDOW")
        infos[fold_id] = {"row": row, "window": window, "metrics": metrics,
                          "trades": trades, "trade_status": trade_status,
                          "digest": parameter_digest(row.get("selected_params") or {})}
    out = []
    for left, right in zip(folds, folds[1:]):
        a, b = infos[left], infos[right]
        if a["metrics"] is None or b["metrics"] is None:
            out.append({"selection_id": f"{cell['cell']}:{arm_name}:fold{left}->{right}",
                        "validity_status": "MISSING_FOLD_WINDOW"})
            continue
        left_days = (a["window"][1] - a["window"][0]).days
        right_days = (b["window"][1] - b["window"][0]).days
        row = {
            "selection_id": f"{cell['cell']}:{arm_name}:fold{left}->{right}",
            "parameter_digest_left": a["digest"], "parameter_digest_right": b["digest"],
            "parameters_changed": a["digest"] != b["digest"],
            "alpha": cell["alpha_id"], "symbol": cell["symbol"], "arm": arm_name,
            "comparison_kind": "ADJACENT_OPERATIONAL",
            "observed_days": a["metrics"]["observed_days"] + b["metrics"]["observed_days"],
            "left_start": a["window"][0].isoformat(), "left_end": a["window"][1].isoformat(),
            "right_start": b["window"][0].isoformat(), "right_end": b["window"][1].isoformat(),
            "left_length_days": left_days, "right_length_days": right_days,
            "parameter_age_days_at_right_start": (b["window"][0] - a["window"][0]).total_seconds() / 86400.0,
            "left_support": {"observed_days": a["metrics"]["observed_days"], "trade_count": a["trades"],
                             "trade_count_status": a["trade_status"]},
            "right_support": {"observed_days": b["metrics"]["observed_days"], "trade_count": b["trades"],
                              "trade_count_status": b["trade_status"]},
            "raw_or_penalized": "raw",
            "penalty_components": None,
            "diagnostic_only": True,
            "note": ("observed fold change: both the parameter vector and the market state change; "
                     "this is not decay of one frozen parameter vector"),
        }
        for metric_name, left_value, right_value, unit in (
            ("sharpe", a["metrics"]["sharpe"], b["metrics"]["sharpe"], "annualised_daily_return_ratio"),
            ("return", a["metrics"]["mean_daily_return_bps"], b["metrics"]["mean_daily_return_bps"],
             "account_bps/day"),
            ("profit_factor", a["metrics"]["profit_factor_daily"],
             b["metrics"]["profit_factor_daily"], "ratio"),
        ):
            delta = None
            if left_value is not None and right_value is not None:
                delta = float(right_value) - float(left_value)
            out.append({**row, "metric_name": metric_name, "unit": unit,
                        "left_value": left_value, "right_value": right_value,
                        "signed_delta": delta,
                        "validity_status": ("VALID" if delta is not None else "UNDEFINED_VALUE")})
    return out


# ---------------------------------------------------------------------------
# D2 fixed-parameter age replay
# ---------------------------------------------------------------------------

def age_windows(cutoff: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    return [(cutoff + pd.Timedelta(days=AGE_H_DAYS * j),
             cutoff + pd.Timedelta(days=AGE_H_DAYS * (j + 1))) for j in range(AGE_HORIZONS)]


def d2_replay(writer: EvidenceWriter, cell: dict, arm_name: str, params: dict,
              cutoff: pd.Timestamp, frame: pd.DataFrame, rows: list[dict]) -> list[dict]:
    """Replay ONE frozen parameter vector through the actual native-event account."""
    end = cutoff + pd.Timedelta(days=AGE_H_DAYS * AGE_HORIZONS)
    base = frame.loc[frame.index <= end]
    if len(base) < 2:
        return []
    bar = int(base.index.searchsorted(cutoff, side="left"))
    initial = VersionWindow(f"{cell['cell']}-{arm_name}-age-anchor", dict(params), bar, "age-anchor")
    with writer.attempt(f"RF04.d2.{cell['cell']}.{arm_name}") as att:
        run = run_event_account(
            cell["alpha_id"], base, initial=initial, schedule=[],
            initial_capital=ACCOUNT_CAPITAL, one_way_fee=ONE_WAY_TAKER_FEE,
            slippage_bps=SLIPPAGE_BPS,
        )
        att.detail = {"status": run.status, "engine_fill_count": int(run.engine_fill_count),
                      "entries": int(run.entries), "bars": int(len(base))}
    equity = pd.Series(np.asarray(run.equity, dtype=float), index=run.index)
    equity = equity.resample("1D").last().ffill().dropna()
    labels = list(run.version_by_bar)
    since_change, since_status = time_since_regime_change(rows, cutoff)
    digest = parameter_digest(params)
    windows = []
    for j, (lo, hi) in enumerate(age_windows(cutoff)):
        metrics = daily_metrics(equity, lo, hi)
        fill_bars = [int(f["bar_index"]) for f in run.fills]
        trade_count = sum(1 for b in fill_bars if 0 <= b < len(base) and lo <= base.index[b] <= hi)
        window_labels = [labels[b] for b in range(len(labels))
                         if 0 <= b < len(base) and lo <= base.index[b] <= hi]
        active = sum(1 for label in window_labels if str(label) not in ("FLAT_UNTIL_READY", "WARMING"))
        windows.append({
            "index": j, "label": f"H{j + 1}", "start": lo, "end": hi,
            "metrics": metrics, "trade_count": trade_count,
            "exposure": {"decision_bars": active, "window_bars": len(window_labels),
                         "decision_ratio": (active / len(window_labels) if window_labels else None)},
            "regime_in_window": window_regime(rows, lo, hi),
        })
    h1 = windows[0]
    out = []
    for window in windows:
        for metric_name in ("sharpe", "return", "profit_factor"):
            left = h1["metrics"].get({"return": "mean_daily_return_bps"}.get(metric_name, metric_name))
            right = window["metrics"].get({"return": "mean_daily_return_bps"}.get(metric_name, metric_name))
            unit = {"sharpe": "annualised_daily_return_ratio",
                    "return": "account_bps/day", "profit_factor": "ratio"}[metric_name]
            delta = None if left is None or right is None else float(left) - float(right)
            out.append({
                "selection_id": f"{cell['cell']}:{arm_name}:fold0",
                "parameter_digest": digest,
                "alpha": cell["alpha_id"], "symbol": cell["symbol"], "arm": f"{arm_name}@{digest}",
                "comparison_kind": "FIXED_PARAM_AGE",
                "age_window_index": window["index"], "age_window_label": window["label"],
                "left_start": h1["start"].isoformat(), "left_end": h1["end"].isoformat(),
                "right_start": window["start"].isoformat(), "right_end": window["end"].isoformat(),
                "observed_days": window["metrics"]["observed_days"],
                "left_value": left, "right_value": right, "signed_delta": delta,
                "metric_name": metric_name, "unit": unit,
                "metric_definition": (f"{metric_name} of the frozen parameter vector in {h1['label']} "
                                      f"minus the same metric in {window['label']}"),
                "raw_or_penalized": "raw", "penalty_components": None,
                "validity_status": ("VALID" if run.status == "EVALUATED" and delta is not None
                                    else f"UNDEFINED_{metric_name.upper()}" if run.status == "EVALUATED"
                                    else f"RUN_{run.status}"),
                "trade_count": window["trade_count"], "trade_count_status": "FILL_LEDGER",
                "equity_metrics": window["metrics"],
                "h1_equity_metrics": h1["metrics"],
                "exposure": window["exposure"],
                "time_since_regime_change_days": since_change,
                "time_since_regime_change_status": since_status,
                "regime_in_window": window["regime_in_window"],
                "replay_route": "native_event",
                "pilot_route": cell["route"],
                "route_match": cell["route"] == "event",
                "route_note": ("the frozen vector is replayed through the qualified native-event account "
                               "with the same account, notional, fee and slippage contract; for the endpoint "
                               "cell this is a different execution binding than the pilot arm"),
                "in_sample_selection_bias": False,
                "anchor_rule": ANCHOR_RULE,
                "diagnostic_only": True,
            })
    return out


# ---------------------------------------------------------------------------
# paired endpoint statistics (saved daily returns only, no financial rerun)
# ---------------------------------------------------------------------------

def paired_bootstrap(diff: pd.Series) -> dict:
    values = np.asarray(diff.dropna(), dtype=float)
    n = int(values.size)
    if n == 0:
        return {"mean_daily_diff_bps": None, "ci95_low_bps": None, "ci95_high_bps": None,
                "n_days": 0, "status": "NO_COMMON_DAYS"}
    mean = float(values.mean()) * 1e4
    zero_variance = bool(np.allclose(values, 0.0, atol=0.0, rtol=0.0))
    block = int(BLOCK_BOOTSTRAP["block_days"])
    resamples = int(BLOCK_BOOTSTRAP["resamples"])
    rng = np.random.default_rng(int(BLOCK_BOOTSTRAP["seed"]))
    block_count = int(np.ceil(n / block))
    if n < block:
        block = max(1, n)
        block_count = int(np.ceil(n / block))
    starts = np.arange(n - block + 1) if n >= block else np.array([0])
    draws = np.empty(resamples, dtype=float)
    for draw in range(resamples):
        picked = rng.choice(starts, size=block_count, replace=True)
        sample = np.concatenate([values[p:p + block] for p in picked])[:n]
        draws[draw] = sample.mean() * 1e4
    return {
        "mean_daily_diff_bps": mean,
        "ci95_low_bps": float(np.percentile(draws, 2.5)),
        "ci95_high_bps": float(np.percentile(draws, 97.5)),
        "n_days": n,
        "zero_variance": zero_variance,
        "method": "paired_moving_block_bootstrap_on_saved_daily_returns",
        "block_days": block, "resamples": resamples, "seed": int(BLOCK_BOOTSTRAP["seed"]),
        "status": ("IDENTICAL_ACCOUNT_SERIES" if zero_variance else "EXPLORATORY_BOUNDED_PILOT"),
    }


def paired_endpoint(cell: dict, left: dict, right: dict, *, left_name: str,
                    right_name: str, implementation_fidelity: str = "AS_SPECIFIED") -> dict:
    left_equity = equity_series((left or {}).get("account")).pct_change()
    right_equity = equity_series((right or {}).get("account")).pct_change()
    joined = pd.concat([left_equity.rename("left"), right_equity.rename("right")], axis=1).dropna()
    diff = joined["left"] - joined["right"]
    stats = paired_bootstrap(diff)
    if stats["n_days"] == 0:
        economic_status, reason = "NOT_EVALUABLE", "no common daily account observations"
    elif stats["zero_variance"]:
        economic_status, reason = ("NOT_EVALUABLE",
                                   "the two account equity series are identical; the timing treatment "
                                   "did not reach execution on this cell")
    elif implementation_fidelity != "AS_SPECIFIED":
        economic_status, reason = ("NOT_EVALUABLE",
                                   f"implementation_fidelity={implementation_fidelity}; A16 fails the "
                                   f"contrast closed before any economic reading")
    else:
        economic_status, reason = ("INCONCLUSIVE",
                                   "bounded 2-cell discovery pilot; the CI is exploratory and cannot "
                                   "support an economic claim")
    return {
        "contrast": f"{left_name} - {right_name} on {cell['cell']}",
        "left_arm": left_name, "right_arm": right_name,
        "paired_daily_difference": stats,
        "mde_corrected_daily_account_bps": 0.0371,
        "economic_status": economic_status,
        "economic_status_reason": reason,
        "claim_limit": ("bounded 2-cell discovery pilot on BTCUSDT; the CI is exploratory and cannot "
                        "support an economic claim"),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def arm_ok(record: dict | None) -> bool:
    if not record:
        return False
    account = record.get("account") or {}
    if record.get("route") == "event":
        return bool(record.get("ok")) and account.get("status") == "EVALUATED"
    return bool(record.get("ok")) and account.get("equity_last") is not None


def contrast_status(cell: dict, left: dict, right: dict, left_name: str,
                    right_name: str) -> dict:
    reasons = []
    for name, arm in ((left_name, left), (right_name, right)):
        if not arm_ok(arm):
            reasons.append(f"{name}: no evaluated engine account")
        if arm.get("oos_used_for_selection") is not False:
            reasons.append(f"{name}: oos_used_for_selection={arm.get('oos_used_for_selection')!r}")
    if list(left.get("cutoffs") or []) == list(right.get("cutoffs") or []):
        reasons.append("the two arms used identical cutoffs (no timing treatment)")
    return {
        "contrast": f"{left_name} - {right_name} on {cell['cell']}",
        "status": "VALID" if not reasons else "NOT_EVALUABLE",
        "reasons": reasons,
        "data_role": "development_discovery_not_confirmation",
    }


def funnel_for(runs: dict, pilot_artifact: dict, emissions: list[dict]) -> dict:
    rows = eligible_rows(emissions, pilot.DEVELOPMENT[0], pilot.DEVELOPMENT[1])
    total_emissions = sum(1 for e in emissions
                          if ts(pilot.DEVELOPMENT[0]) <= ts(e["available_at"]) <= ts(pilot.DEVELOPMENT[1]))
    changes = [c for c in semantic_changes(rows)
               if ts(pilot.DEVELOPMENT[0]) <= c <= ts(pilot.DEVELOPMENT[1])]
    controller = online_trigger_schedule(
        emissions, earliest=pilot.DEVELOPMENT[0], latest=pilot.DEVELOPMENT[1],
        min_gap_days=90.0, max_age_days=180.0, budget=None)
    reasons = [part for part in controller.source.split("reasons ")[-1].strip("[]").split(",")]
    cells_out = {}
    for cell in pilot.CELLS:
        cell_runs = {arm: record for (name, arm), record in runs.items() if name == cell["cell"]}
        per_arm = {}
        for arm_name in ALL_ARMS:
            record = cell_runs.get(arm_name)
            if not record:
                continue
            digests = digests_by_fold(record)
            ordered = [digests[key] for key in sorted(digests)]
            adjacent_changes = sum(1 for a, b in zip(ordered, ordered[1:]) if a != b)
            fold_ties = 0
            fold_total = 0
            distinct_overall = 0
            for fold_id in sorted(digests):
                trials = [t for t in record.get("trial_records", [])
                          if int(t.get("schedule_fold_id", -1)) == fold_id]
                finite = {round(float(t["objective"]), 12) for t in trials
                          if isinstance(t.get("objective"), (int, float))}
                if trials:
                    fold_total += 1
                    distinct_overall += len(finite)
                    if len(finite) <= 1:
                        fold_ties += 1
            per_arm[arm_name] = {
                "cutoffs": len(record.get("cutoffs") or []),
                "folds_scored": record.get("fold_count", 0),
                "trials_retained": record.get("trial_count", 0),
                "selections_with_params": len(digests),
                "distinct_parameter_digests": len(set(ordered)),
                "adjacent_parameter_changes": adjacent_changes,
                "folds_all_candidates_tied": fold_ties,
                "folds_scored_for_rank": fold_total,
                "finite_objective_values": distinct_overall,
                "trades": (record.get("account") or {}).get("engine_report", {}).get("num_trades"),
                "fills": (record.get("account") or {}).get("fill_count"),
                "equity_last": (record.get("account") or {}).get("equity_last"),
                "wall_seconds": record.get("wall_seconds"),
            }
        cell_out = {
            "valid_observations": {"total_emissions_in_window": total_emissions,
                                   "eligible_quality_ok": len(rows),
                                   "eligibility_rule": "decision_eligible=True and quality_status=='OK'",
                                   "semantic_changes_in_window": len(changes)},
            "triggers": {"M4_CAL": len(pilot_artifact["arms"]["M4_CAL"]["cutoffs"]),
                "M4_REGIME": len(controller.cutoffs),
                "M4_REGIME_trigger_reasons": [r.strip().strip("'") for r in reasons],
                "M4_CAL_MATCHED": MATCHED_REFITS},
            "searches": per_arm,
        }
        ranked = [per_arm[a] for a in (PRIMARY_ARMS + (MATCHED_ARM,))
                  if a in per_arm]
        rank_signal = any(entry["folds_scored_for_rank"] > entry["folds_all_candidates_tied"]
                          for entry in ranked) if ranked else False
        adjacent_total = sum(entry["adjacent_parameter_changes"] for entry in ranked)
        cell_out["different_params"] = {
            "adjacent_parameter_changes": adjacent_total,
            "distinct_parameter_digests_by_arm": {a: per_arm[a]["distinct_parameter_digests"]
                                                  for a in per_arm},
        }
        cell_out["activated"] = {
            "activations_with_changed_params": adjacent_total,
            "activation_rule": "a new parameter digest at a fold boundary is an activation event",
        }
        trade_counts = {a: per_arm[a]["trades"] for a in per_arm if a in (PRIMARY_ARMS + (MATCHED_ARM,))}
        cell_out["different_orders"] = {
            "engine_trades_by_arm": trade_counts,
            "orders_differ": len(set(v for v in trade_counts.values() if v is not None)) > 1,
        }
        cell_out["rank_diagnostic"] = {
            "rank_signal_present": rank_signal,
            "status": "PARAMETER_RANK_SIGNAL_PRESENT" if rank_signal else "LOW_PARAMETER_OPPORTUNITY",
            "rule": ("a cell is tagged LOW_PARAMETER_OPPORTUNITY when every scored fold has at most one "
                     "distinct finite candidate objective; A-SC ties exactly because the endpoint scorer "
                     "returned one objective for all sampled candidates in every fold"),
        }
        cells_out[cell["cell"]] = cell_out
    low_cells = [name for name, cell in cells_out.items()
                 if cell["rank_diagnostic"]["status"] == "LOW_PARAMETER_OPPORTUNITY"]
    return {
        "denominator_rule": "counts are per cell and per arm from the committed pilot/control artifacts",
        "cells": cells_out,
        "low_parameter_opportunity_cells": low_cells,
        "potential_level": ("LOW_PARAMETER_OPPORTUNITY" if len(low_cells) == len(cells_out)
                            else "UNASSESSED"),
        "potential_note": ("A-SC/BTCUSDT candidates tie in every fold, so the bounded pilot provides no "
                           "parameter-rank opportunity evidence for that cell; A-HMA/BTCUSDT ranks vary "
                           "but the scope cannot establish informed opportunity"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="replace existing RF-04 control/decay artifacts")
    parser.add_argument("--skip-placebo", action="store_true",
                        help="register but do not run the delayed-state placebo")
    parser.add_argument("--skip-d2", action="store_true",
                        help="register but do not run the fixed-parameter age replay")
    parser.add_argument("--reuse-engine", action="store_true",
                        help="reuse the matched/placebo engine records from the existing "
                             "controls_and_funnel.json instead of re-running those arms")
    args = parser.parse_args()

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    targets = [RUN_DIR / "controls_and_funnel.json", RUN_DIR / "decay_panels.json"]
    if any(path.exists() for path in targets) and not args.force:
        raise SystemExit("RF-04 control/decay artifacts exist; pass --force to supersede")

    pilot_path = RUN_DIR / "paired_discovery_pilot.json"
    pilot_artifact = load_json(pilot_path)
    emissions = load_json(LAB_ROOT / "configs" / "lab05_full_emission_tape.json")["emissions"]
    snapshot_root = policy.lab_root / "snapshots" / pilot.SNAPSHOT_ID

    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)

    prior_controls = None
    supersedes = None
    decay_supersedes = None
    if args.reuse_engine and targets[0].exists():
        prior_controls = load_json(targets[0])
        reason = ("RF-04.3/04.4 metric fix: D2 daily resample, H1-vs-Hj age decay rows, "
                  "paired status fail-closed on identical accounts and deviated fidelity; "
                  "the engine arm records are reused unchanged")
        supersedes = {"path": "controls_and_funnel.json", "sha256": sha256_file(targets[0]),
                      "reason": reason}
        if targets[1].exists():
            decay_supersedes = {"path": "decay_panels.json", "sha256": sha256_file(targets[1]),
                                "reason": reason}

    # ---- registration first, before any control run -----------------------
    development = pilot.DEVELOPMENT
    matched_cutoffs = tuple(
        (ts("2021-01-01") + pd.Timedelta(days=MATCHED_CADENCE_DAYS * index)).isoformat()
        for index in range(MATCHED_REFITS))
    anchors = [
        {"cell": cell["cell"], "alpha_id": cell["alpha_id"], "symbol": cell["symbol"],
         "arm": arm_name, "fold_id": 0}
        for cell in pilot.CELLS for arm_name in PRIMARY_ARMS
    ]
    registration = {
        "schema": "regime_lab.rf04_controls_registration.v1",
        "status": "REGISTERED_BEFORE_CONTROL_RUNS",
        "study_id": STUDY_ID, "phase": "RF-04",
        "pilot_artifact": {"path": str(pilot_path.relative_to(LAB_ROOT)),
                           "sha256": sha256_file(pilot_path)},
        "development_window": {"start": development[0], "end": development[1]},
        "matched_control": {
            "arm": MATCHED_ARM, "required": True,
            "reason": ("the pilot refit counts differ materially (3 calendar vs 6 regime); "
                       "M4_CAL_MATCHED isolates refit count and compute from timing"),
            "rule": MATCHED_RULE, "cutoffs": list(matched_cutoffs),
            "refits": MATCHED_REFITS,
            "budget": {"optuna_trials_per_cutoff": pilot.TRIALS, "seed": pilot.SEED,
                       "train_memory_days": 180, "account_capital": ACCOUNT_CAPITAL,
                       "entry_notional": ALLOC_PER_TRADE * ACCOUNT_CAPITAL,
                       "one_way_fee": ONE_WAY_TAKER_FEE, "slippage_bps": SLIPPAGE_BPS},
            "cells": [cell["cell"] for cell in pilot.CELLS],
        },
        "placebo": {
            "arm": PLACEBO_ARM, "rule": PLACEBO_RULE, "delay_days": PLACEBO_DELAY_DAYS,
            "budget_rule": ("run only if the bounded pilot budget remains under the registered tier cap "
                            "(T3=900s per job) after the mandatory matched control and the D2 anchors; "
                            "otherwise REGISTERED_NOT_RUN with the measured reason"),
        },
        "decay_anchor": {
            "rule": ANCHOR_RULE, "anchors": anchors, "h_days": AGE_H_DAYS,
            "windows": [f"H{j + 1}=[{AGE_H_DAYS * j},{AGE_H_DAYS * (j + 1)}) days"
                        for j in range(AGE_HORIZONS)],
        },
        "registered_at_utc": utc_now_iso(),
    }
    reg_path = RUN_DIR / "controls_registration.json"
    if args.reuse_engine and reg_path.exists():
        registration = load_json(reg_path)
        reg_record = {"relpath": "controls_registration.json", "sha256": sha256_file(reg_path),
                      "size_bytes": reg_path.stat().st_size, "schema": registration["schema"]}
    else:
        reg_record = writer.write_json("controls_registration.json", registration,
                                       schema=registration["schema"])
    print(json.dumps({"registered": reg_record["relpath"], "sha256": reg_record["sha256"]}, indent=2))

    # ---- mandatory M4_CAL_MATCHED ----------------------------------------
    matched_cells = []
    matched_wall = 0.0
    runs: dict[tuple[str, str], dict] = {}
    reuse_matched = bool(prior_controls and prior_controls.get("matched_control", {}).get("cells"))
    if reuse_matched:
        matched_cells = prior_controls["matched_control"]["cells"]
        matched_wall = float(prior_controls["matched_control"].get("wall_seconds") or 0.0)
        for entry in matched_cells:
            runs[(entry["cell"], MATCHED_ARM)] = entry["arm"]
    else:
        for cell in pilot.CELLS:
            frame = pilot.load_frame(snapshot_root, cell["symbol"], cell["interval"])
            schedule = CutoffSchedule(
                arm=MATCHED_ARM, kind="calendar_matched", cutoffs=matched_cutoffs,
                train_memory_days=180,
                source=f"registered matched control: {MATCHED_RULE}",
                diagnostics={"cadence_days": MATCHED_CADENCE_DAYS, "refits": MATCHED_REFITS},
            )
            with writer.attempt(f"RF04.matched.{cell['cell']}") as att:
                record = pilot.arm_record(cell, MATCHED_ARM, schedule, frame)
                att.detail = {"ok": record["ok"], "fold_count": record["fold_count"],
                              "trial_count": record["trial_count"]}
            matched_wall += float(record.get("wall_seconds") or 0.0)
            runs[(cell["cell"], MATCHED_ARM)] = record
            matched_cells.append({
                "cell": cell["cell"], "alpha_id": cell["alpha_id"], "symbol": cell["symbol"],
                "route": cell["route"], "schedule": schedule.as_record(),
                "arm": record,
                "contrast_vs_regime": contrast_status(cell, record,
                                                      pilot_artifact["cells"][pilot.CELLS.index(cell)]
                                                      ["arms"]["M4_REGIME"],
                                                      MATCHED_ARM, "M4_REGIME"),
                "contrast_vs_calendar": contrast_status(cell, record,
                                                        pilot_artifact["cells"][pilot.CELLS.index(cell)]
                                                        ["arms"]["M4_CAL"],
                                                        MATCHED_ARM, "M4_CAL"),
            })

    # ---- delayed-state placebo (registered; run only if budget allows) ----
    placebo_cells = []
    placebo_status = "REGISTERED_NOT_RUN"
    placebo_reason = ""
    placebo_wall = 0.0
    reuse_placebo = bool(prior_controls and prior_controls.get("placebo", {}).get("cells"))
    if reuse_placebo:
        placebo_cells = prior_controls["placebo"]["cells"]
        placebo_status = prior_controls["placebo"].get("status", "REGISTERED_NOT_RUN")
        placebo_reason = prior_controls["placebo"].get("reason", "")
        placebo_wall = float(prior_controls["placebo"].get("wall_seconds") or 0.0)
        for entry in placebo_cells:
            runs[(entry["cell"], PLACEBO_ARM)] = entry["arm"]
    elif args.skip_placebo:
        placebo_reason = "operator skipped the optional placebo (--skip-placebo)"
    else:
        delayed_emissions = [
            {**record,
             "available_at": (ts(record["available_at"])
                              + pd.Timedelta(days=PLACEBO_DELAY_DAYS)).isoformat()}
            for record in emissions
        ]
        delayed_schedule = regime_cutoffs(
            delayed_emissions, window_start=development[0], window_end=development[1],
            min_gap_days=90.0, max_age_days=180.0, budget=None)
        delayed_schedule = CutoffSchedule(
            arm=PLACEBO_ARM, kind="regime_delayed", cutoffs=delayed_schedule.cutoffs,
            train_memory_days=180, source=PLACEBO_RULE,
            diagnostics={"delay_days": PLACEBO_DELAY_DAYS,
                         "min_gap_days": 90.0, "max_age_days": 180.0})
        if not delayed_schedule.cutoffs:
            placebo_reason = "the delayed tape produced no controller cutoff"
        else:
            started = time.perf_counter()
            for cell in pilot.CELLS:
                frame = pilot.load_frame(snapshot_root, cell["symbol"], cell["interval"])
                with writer.attempt(f"RF04.placebo.{cell['cell']}") as att:
                    record = pilot.arm_record(cell, PLACEBO_ARM, delayed_schedule, frame)
                    att.detail = {"ok": record["ok"], "cutoffs": len(record["cutoffs"])}
                runs[(cell["cell"], PLACEBO_ARM)] = record
                placebo_cells.append({
                    "cell": cell["cell"], "schedule": delayed_schedule.as_record(),
                    "arm": record,
                    "contrast_vs_regime": contrast_status(
                        cell, record,
                        pilot_artifact["cells"][pilot.CELLS.index(cell)]["arms"]["M4_REGIME"],
                        PLACEBO_ARM, "M4_REGIME"),
                })
            placebo_wall = time.perf_counter() - started
            placebo_status = "RUN"
    if placebo_status != "RUN" and not placebo_reason:
        placebo_reason = "bounded pilot budget did not allow the optional placebo"

    # ---- D1/D3 panels from committed ledgers ------------------------------
    runs[("A-SC/BTCUSDT", "M4_CAL")] = pilot_artifact["cells"][0]["arms"]["M4_CAL"]
    runs[("A-SC/BTCUSDT", "M4_REGIME")] = pilot_artifact["cells"][0]["arms"]["M4_REGIME"]
    runs[("A-HMA/BTCUSDT", "M4_CAL")] = pilot_artifact["cells"][1]["arms"]["M4_CAL"]
    runs[("A-HMA/BTCUSDT", "M4_REGIME")] = pilot_artifact["cells"][1]["arms"]["M4_REGIME"]

    d1: list[dict] = []
    d3: list[dict] = []
    frames: dict[str, pd.DataFrame] = {}
    for cell in pilot.CELLS:
        frame = pilot.load_frame(snapshot_root, cell["symbol"], cell["interval"])
        frames[cell["cell"]] = frame
        cell_rows = eligible_rows(emissions, development[0], development[1])
        for arm_name in ALL_ARMS:
            record = runs.get((cell["cell"], arm_name))
            if not record or not record.get("ok"):
                continue
            d1.extend(d1_rows(cell, arm_name, record, frame, cell_rows))
            d3.extend(d3_rows(cell, arm_name, record, frame))

    # ---- D2 registered anchor replay --------------------------------------
    d2: list[dict] = []
    d2_status = "REGISTERED_NOT_RUN"
    d2_reason = ""
    d2_wall = None
    if args.skip_d2:
        d2_reason = "operator skipped the registered anchor replay (--skip-d2)"
    else:
        started = time.perf_counter()
        failures = []
        for anchor in anchors:
            cell = next(c for c in pilot.CELLS if c["cell"] == anchor["cell"])
            source_arm = pilot_artifact["cells"][pilot.CELLS.index(cell)]["arms"][anchor["arm"]]
            row = next(r for r in source_arm["fold_selection_table"]
                       if int(r["fold_id"]) == anchor["fold_id"])
            params = row.get("selected_params") or {}
            cutoff = ts(row["test_start"])
            cell_rows = eligible_rows(emissions, development[0], development[1])
            try:
                d2.extend(d2_replay(writer, cell, anchor["arm"], params, cutoff,
                                    frames[cell["cell"]], cell_rows))
            except Exception as exc:  # a run that cannot execute is recorded, never invented
                failures.append({"cell": anchor["cell"], "arm": anchor["arm"],
                                 "error": f"{type(exc).__name__}: {exc}"[:300]})
        d2_status = "COMPLETE" if d2 else "FAILED"
        if failures:
            d2_status = "COMPLETE_WITH_FAILURES"
            d2_reason = f"{len(failures)} anchor replays failed: {failures}"
        d2_wall = time.perf_counter() - started

    # ---- funnel and paired endpoints --------------------------------------
    funnel = funnel_for(runs, pilot_artifact, emissions)
    paired = []
    for cell in pilot.CELLS:
        artifact_cell = pilot_artifact["cells"][pilot.CELLS.index(cell)]
        pairs = (
            ("M4_REGIME", "M4_CAL"),
            ("M4_REGIME", MATCHED_ARM),
            (MATCHED_ARM, "M4_CAL"),
        )
        for left_name, right_name in pairs:
            left = runs.get((cell["cell"], left_name))
            right = runs.get((cell["cell"], right_name))
            if left and right:
                paired.append(paired_endpoint(
                    cell, left, right, left_name=left_name, right_name=right_name,
                    implementation_fidelity="DEVIATED" if cell["route"] == "endpoint"
                    else "AS_SPECIFIED"))

    # per-contrast A16 status for the report
    contrast_statuses = []
    by_cell = {c["cell"]: c for c in pilot_artifact["cells"]}
    for cell in pilot.CELLS:
        artifact_cell = by_cell[cell["cell"]]
        reg = artifact_cell["arms"]["M4_REGIME"]
        cal = artifact_cell["arms"]["M4_CAL"]
        matched = runs.get((cell["cell"], MATCHED_ARM))
        endpoint = cell["route"] == "endpoint"
        all_tied = all(
            entry["folds_scored_for_rank"] > 0
            and entry["folds_all_candidates_tied"] == entry["folds_scored_for_rank"]
            for entry in [funnel["cells"][cell["cell"]]["searches"][arm_name]
                          for arm_name in (PRIMARY_ARMS + (MATCHED_ARM,))
                          if arm_name in funnel["cells"][cell["cell"]]["searches"]]
        )
        contrast_statuses.append({
            "cell": cell["cell"], "route": cell["route"],
            "execution_validity": "PASS",
            "implementation_fidelity": "DEVIATED" if endpoint else "AS_SPECIFIED",
            "statistical_status": "NOT_EVALUABLE" if endpoint else "INCONCLUSIVE",
            "economic_status": "NOT_EVALUABLE" if endpoint else "INCONCLUSIVE",
            "reason": ("candidate objectives are exactly tied in every fold (endpoint scorer) and the "
                       "endpoint account exposes no per-fill ledger; no economic claim is possible"
                       if endpoint else
                       "both arms execute on the native-event account; 2-cell bounded pilot cannot "
                       "support an economic claim"),
            "low_parameter_opportunity": all_tied,
            "arms": {"M4_CAL": cal.get("selected_digest"), "M4_REGIME": reg.get("selected_digest"),
                     MATCHED_ARM: (matched or {}).get("selected_digest")},
        })

    # ---- write controls_and_funnel.json -----------------------------------
    controls = {
        "schema": "regime_lab.rf04_controls_and_funnel.v1",
        "phase": "RF-04", "status": "PILOT_CONTROLS_COMPLETE",
        "study_id": STUDY_ID,
        "registration_artifact": "controls_registration.json",
        "registration_sha256": reg_record["sha256"],
        "pilot_artifact": {"path": "paired_discovery_pilot.json",
                           "sha256": sha256_file(pilot_path)},
        "matched_control": {
            "arm": MATCHED_ARM, "required": True, "rule": MATCHED_RULE,
            "cutoffs": list(matched_cutoffs), "refits": MATCHED_REFITS,
            "cells": matched_cells,
            "wall_seconds": round(matched_wall, 3),
        },
        "placebo": {
            "arm": PLACEBO_ARM, "status": placebo_status, "reason": placebo_reason,
            "rule": PLACEBO_RULE, "delay_days": PLACEBO_DELAY_DAYS,
            "cells": placebo_cells, "wall_seconds": round(placebo_wall, 3),
        },
        "decay_anchor": {"rule": ANCHOR_RULE, "h_days": AGE_H_DAYS,
                         "horizons": AGE_HORIZONS, "status": d2_status,
                         "reason": d2_reason, "wall_seconds": d2_wall},
        "funnel": funnel,
        "paired_endpoints": paired,
        "contrasts": contrast_statuses,
        "supersedes": supersedes,
        "limitations": [
            "bounded 2-cell pilot on BTCUSDT with 8 trials/cutoff; not the registered 32-64",
            "the endpoint cell (A-SC/BTCUSDT) returns one objective for every sampled candidate and no "
            "per-fill ledger; its parameter ranking is not identified",
            "the delayed-state placebo and the D2 anchors are diagnostics, not confirmation evidence",
            "the development window 2021-01-01..2022-06-30 is nested retrospective; no holdout claim",
        ],
        "written_at_utc": utc_now_iso(),
    }
    controls_record = writer.write_json("controls_and_funnel.json", controls,
                                        schema=controls["schema"])

    # ---- write decay_panels.json ------------------------------------------
    d1_valid = [row for row in d1 if row["validity_status"] == "VALID"]
    d3_valid = [row for row in d3 if row.get("validity_status") == "VALID"]
    panel = {
        "schema": "regime_lab.rf04_decay_panels.v1",
        "phase": "RF-04", "status": "COMPLETE" if d2_status.startswith("COMPLETE") else "PARTIAL",
        "study_id": STUDY_ID,
        "registration_artifact": "controls_registration.json",
        "registration_sha256": reg_record["sha256"],
        "definitions": {
            "D1": "IS objective used for selection vs post-selection OOS metrics on the same fold; raw "
                  "and penalized IS flavors are separate rows; IS is selection-biased and the panel is a "
                  "generalization-gap diagnostic",
            "D2": "frozen parameter vector replayed through the native-event account over fixed 90-day "
                  "age windows after its selection cutoff",
            "D3": "observed change between adjacent operational folds; both parameters and market state "
                  "change, so it is not the decay of one parameter vector",
            "sharpe": "sqrt(365)*mean(daily net return)/std(daily net return, ddof=1)",
            "return": "mean daily account net return in bps/day",
            "profit_factor": "sum(positive daily returns)/abs(sum(negative daily returns))",
            "boundary_rule": "the first return inside a window uses the last daily equity before it",
        },
        "denominators": {
            "D1_rows": len(d1), "D1_valid_rows": len(d1_valid),
            "D2_rows": len(d2),
            "D3_rows": len(d3), "D3_valid_rows": len(d3_valid),
            "cells": len(pilot.CELLS), "arms": len(ALL_ARMS),
            "registered_anchors": len(anchors), "anchors_replayed": len(d2) // (AGE_HORIZONS * 3),
            "null_value_reasons": sorted({row.get("validity_status") for row in d1 + d2 + d3
                                          if row.get("validity_status") not in (None, "VALID")}),
        },
        "registration": registration,
        "supersedes": decay_supersedes,
        "D1": d1,
        "D2": {"status": d2_status, "reason": d2_reason, "rows": d2},
        "D3": d3,
        "summary": {
            "placebo_status": placebo_status,
            "matched_wall_seconds": round(matched_wall, 3),
            "d2_wall_seconds": d2_wall,
            "low_parameter_opportunity_cells": funnel["low_parameter_opportunity_cells"],
        },
        "written_at_utc": utc_now_iso(),
    }
    panel_record = writer.write_json("decay_panels.json", panel, schema=panel["schema"])

    # ---- RF04.5 design freeze (recorded before RF-05) ---------------------
    design_freeze = {
        "schema": "regime_lab.rf04_design_freeze.v1",
        "phase": "RF-04", "status": "FROZEN_FOR_RF05_WITH_BLOCKERS",
        "study_id": STUDY_ID,
        "primary_design": {
            "mode4_contract": {"optimization_mode": "mode_4_is_only_robust",
                               "optimization_schedule": "per_fold_causal",
                               "candidate_selection_metric": "is_only_robust",
                               "scoring_backend": "endpoint", "oos_used_for_selection": False},
            "arms": list(PRIMARY_ARMS), "budget_control": MATCHED_ARM,
            "primary_contrasts": [
                {"id": "TIMING", "contrast": "M4_REGIME - M4_CAL"},
                {"id": "BUDGET_AWARE", "contrast": f"M4_REGIME - {MATCHED_ARM}"},
            ],
            "cells": [cell["cell"] for cell in pilot.CELLS],
            "development_window": list(development),
            "economics": {"account_capital": ACCOUNT_CAPITAL,
                          "entry_notional": ALLOC_PER_TRADE * ACCOUNT_CAPITAL,
                          "one_way_fee": ONE_WAY_TAKER_FEE, "slippage_bps": SLIPPAGE_BPS,
                          "trials_per_cutoff": pilot.TRIALS, "seed": pilot.SEED,
                          "train_memory_days": 180},
            "mde_corrected_daily_account_bps": 0.0371,
        },
        "no_promising_design": True,
        "no_promising_design_reason": (
            "the bounded 2-cell pilot establishes no positive primary contrast: A-SC/BTCUSDT has "
            "implementation_fidelity=DEVIATED (treatment not transmitted to execution) and "
            "A-HMA/BTCUSDT is INCONCLUSIVE with the paired CI containing both 0 and the corrected MDE"
        ),
        "blockers": [{"cell": "A-SC/BTCUSDT",
                      "blocker": "endpoint scorer returns one objective for every sampled candidate "
                                 "and the account has no per-fill ledger; parameter ranking is not "
                                 "identified, so the timing contrast is NOT_EVALUABLE"}],
        "not_frozen": ["A-VWAP and A-HASH cells (route BLOCKED_CAPABILITY; not executed)"],
        "rule": ("freeze the registered primary design for RF-05; no new positive cell is promoted and "
                 "the aggregate is never called over 20 cells when only 2 executed"),
        "written_at_utc": utc_now_iso(),
    }
    freeze_record = writer.write_json("design_freeze.json", design_freeze,
                                      schema=design_freeze["schema"])

    print(json.dumps({
        "controls_and_funnel": {"relpath": controls_record["relpath"],
                                "sha256": controls_record["sha256"]},
        "decay_panels": {"relpath": panel_record["relpath"], "sha256": panel_record["sha256"]},
        "design_freeze": {"relpath": freeze_record["relpath"], "sha256": freeze_record["sha256"]},
        "matched_equity": {c["cell"]: c["arm"]["account"].get("equity_last") for c in matched_cells},
        "placebo_status": placebo_status, "d2_status": d2_status,
        "d1_rows": len(d1), "d2_rows": len(d2), "d3_rows": len(d3),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
