"""FP01-T02/T05: admission wiring + IS/forward parity on the REAL engine path.

T02: with a forced-reject admission policy the actual deployment account runs
no rejected candidate -- and an explicit null-metrics payload (never PnL=0) is
recorded when nothing was admitted. The paired control uses the SAME schedule
and params with admission_policy=None: the rejected candidate IS consumed
there, proving the test can go red (the wiring, not the fixture, changes the
outcome).

T05: the same params/data/economics through the IS scorer route and the
deployment account route produce identical equity -- the shared economic
contract proved on the engine, not asserted from the constants.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

quantbt = pytest.importorskip("quantbt")

from crypto_regime_lab.experiments.dynamic_fold_provider import (
    CutoffSchedule, ZeroSignalStrategy, engine_param_ranges,
    run_cutoff_walk_forward,
)

ALPHA = "A-SC"


def _frame(n: int = 60) -> pd.DataFrame:
    close = 100 + 2 * np.sin(np.arange(n) / 6.0) + 0.02 * np.arange(n)
    return pd.DataFrame({"open": close, "high": close + 0.3, "low": close - 0.3,
                         "close": close, "volume": np.full(n, 1000.0)},
                        index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"))


def _schedule() -> CutoffSchedule:
    return CutoffSchedule(
        arm="FP01_PROBE", cutoffs=("2024-01-01T12:00:00+00:00", "2024-01-02T12:00:00+00:00"),
        source="FP01-T02/T05 two-cutoff probe on a 60-bar fixture", kind="calendar",
        train_memory_days=1)


def _reject_all(fold_row: dict) -> dict:
    return {"decision": "COMMON_FLAT_FALLBACK", "reason": "FP01-T02 forced rejection probe",
            "kept": None}


def _admit_all(fold_row: dict) -> dict:
    return {"decision": "ADMIT", "reason": "FP01-T02 forced admission probe", "kept": None}


def _run(schedule, admission_policy):
    return run_cutoff_walk_forward(
        ALPHA, _frame(60), schedule, param_ranges=engine_param_ranges(ALPHA),
        strategy_class=ZeroSignalStrategy, optuna_trials=2, seed=20260922,
        route="event", admission_policy=admission_policy)


def test_fp01_t02_forced_rejection_keeps_rejected_params_out_of_the_account():
    rejected = _run(_schedule(), _reject_all)
    assert rejected["ok"], rejected.get("error")
    raw = rejected["params_by_fold"]
    assert len(raw) == 2, "the search must still run and record the stock selection"
    wiring = rejected["admission_wiring"]
    assert wiring["wired"] is True
    assert [wiring["lineage"][k]["decision"] for k in sorted(wiring["lineage"])] == [
        "COMMON_FLAT_FALLBACK", "COMMON_FLAT_FALLBACK"]
    account = rejected["account"]
    assert account["status"] == "NO_ADMITTED_DEPLOYMENT", account
    assert account["equity_daily"] == [] and account["fill_count"] == 0
    assert account["equity_first"] is None and account["equity_last"] is None
    # Non-vacuous paired control: the SAME schedule/params with admission OFF
    # consumes the first fold's params in a real account.
    control = _run(_schedule(), None)
    assert control["ok"], control.get("error")
    assert control["admission_wiring"]["wired"] is False
    assert control["account"].get("status") != "NO_ADMITTED_DEPLOYMENT"
    assert control["account"]["equity_daily"], "the control account has no equity series"
    assert control["params_by_fold"] == raw, (
        "raw stock selection must be identical: only the wiring changed")
    # Forced admission reaches the account with the same params the raw record holds.
    admitted = _run(_schedule(), _admit_all)
    assert admitted["ok"], admitted.get("error")
    assert admitted["deployment_params_by_fold"] == admitted["params_by_fold"]
    assert admitted["account"].get("status") != "NO_ADMITTED_DEPLOYMENT"


def test_fp01_t05_same_params_data_economics_reach_parity():
    from crypto_regime_lab.experiments.dynamic_fold_provider import EventAccountScorer
    run = _run(_schedule(), _admit_all)
    assert run["ok"], run.get("error")
    deployed = run["deployment_params_by_fold"]
    assert deployed, "admission admitted nothing: parity has no deployment to compare"
    first_key = sorted(deployed, key=int)[0]
    first = dict(deployed[first_key])
    scorer = EventAccountScorer(ALPHA)
    cutoff = run["fold_selection_table"][int(first_key)]["test_start"]
    task = {"data": _frame(60), "output": None, "index": _frame(60).index, "fold": None,
            "params": first, "context": "fp01-t05", "trading_days": 365}
    assert str(cutoff) > "2024-01-01", "sanity: fold cutoffs on the fixture frame"
    is_score = scorer.score_batch([task])[0]
    assert is_score.get("status") in ("OK", "EVALUATED"), is_score
    cached = scorer._cache[scorer._key(task)]
    is_equity = [float(v) for v in list(cached["equity"])]
    account_equity = [float(v) for _, v in run["account"]["equity_daily"]]
    assert len(is_equity) > 2 and len(account_equity) > 2
    assert run["requested"]["account_capital"] == scorer.initial_capital == 20000.0
    np.testing.assert_allclose(
        np.asarray(account_equity, dtype=float),
        np.asarray(is_equity[:len(account_equity)], dtype=float),
        rtol=1e-9, err_msg="IS route and deployment route diverge on same economics")
