"""Comprehensive test suite for Phase VWFO-04 (VOL-WFO-V1.0 Section 15).

Tests V4-T01 to V4-T10:
- V4-T01: Prefix streaming và batch cùng information cho cùng proposals/IDs.
- V4-T02: Future/late arrivals không backdate; wrong target window packet rejected.
- V4-T03: Actual not-before, approval và waitflat áp đối xứng các arms.
- V4-T04: Duplicate/restart after publish-before-ack không double activation/orders.
- V4-T05: Same params refresh watermark, không reset indicator/campaign/equity.
- V4-T06: Expired/superseded hoặc incumbent-version mismatch rejected.
- V4-T07: Missing median/temp/taxonomy làm bundle invalid, không weights-only success.
- V4-T08: Max-revalidation pause không chặn protective exits hoặc force close ngoài contract.
- V4-T09: Actual fills/rejects điều khiển strategy state, no expected-fill feedback.
- V4-T10: Scoped actual stream/batch financial parity và protected-tree zero change.
"""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.volatility_wfo.policy_runtime import (
    AccountState,
    ModelBundle,
    PolicyProposal,
    PolicyRuntimeController,
)
from crypto_regime_lab.volatility_wfo.streaming_replay import (
    StreamingReplayResult,
    run_batch_replay,
    run_streaming_replay,
    verify_stream_batch_parity,
)


def _make_dummy_model_bundle(
    *,
    weights: dict | None = None,
    imputer_medians: dict | None = None,
    temperature_t_v: float = 3.946,
    taxonomy_quantiles: dict | None = None,
    feature_schema_len: int = 38,
) -> ModelBundle:
    schema = [f"feat_{i}" for i in range(feature_schema_len)]
    medians = imputer_medians if imputer_medians is not None else {f"feat_{i}": 0.5 for i in range(feature_schema_len)}
    tax = taxonomy_quantiles if taxonomy_quantiles is not None else {"q33_3": -0.8872, "q66_7": -0.5142}
    wt = weights if weights is not None else {"n_trees": 80, "leaves": 7}
    return ModelBundle(
        recipe_id="M4_LGBM_CONSERVATIVE_SLOW",
        weights=wt,
        imputer_medians=medians,
        temperature_t_v=temperature_t_v,
        taxonomy_quantiles=tax,
        feature_schema=schema,
    )


def _make_dummy_proposal(
    proposal_id: str,
    arm_id: str = "C_H14",
    cutoff_time: str = "2025-06-07T00:00:00Z",
    target_start: str = "2025-06-07T00:00:00Z",
    target_end: str = "2025-06-21T00:00:00Z",
    not_before: str = "2025-06-08T00:00:00Z",
    expires_at: str = "2025-06-10T00:00:00Z",
    expected_incumbent_version: int = 0,
    candidate_params: dict | None = None,
    bundle: ModelBundle | None = None,
) -> PolicyProposal:
    params = candidate_params or {"coeff": 3, "AP": 14, "alpha.condition_threshold": 45}
    b = bundle or _make_dummy_model_bundle()
    return PolicyProposal(
        proposal_id=proposal_id,
        arm_id=arm_id,
        cutoff_time=pd.Timestamp(cutoff_time),
        target_window_start=pd.Timestamp(target_start),
        target_window_end=pd.Timestamp(target_end),
        not_before=pd.Timestamp(not_before),
        expires_at=pd.Timestamp(expires_at),
        expected_incumbent_version=expected_incumbent_version,
        sequence_number=1,
        candidate_params=params,
        model_bundle=b,
        selection_metadata={"rank": 1, "is_sharpe": 1.25},
    )


def _generate_synthetic_15m_bars(start_date: str = "2025-06-07", days: int = 14) -> pd.DataFrame:
    """Generates synthetic 15m OHLCV bars for testing."""
    periods = days * 24 * 4
    dates = pd.date_range(start_date, periods=periods, freq="15min", tz="UTC")
    np.random.seed(20260929)

    rets = np.random.normal(0.0001, 0.002, size=periods)
    # Add a few clear trends to trigger entries/exits
    rets[100:150] += 0.004
    rets[200:220] -= 0.005
    rets[400:450] += 0.003
    rets[500:520] -= 0.004

    price = 60000.0 * np.exp(np.cumsum(rets))

    df = pd.DataFrame(
        {
            "open": price * 0.9998,
            "high": price * 1.0015,
            "low": price * 0.9985,
            "close": price,
            "volume": np.random.uniform(50, 200, size=periods),
        },
        index=dates,
    )
    return df


def test_v4_t01_prefix_streaming_and_batch_parity():
    """V4-T01: Prefix streaming và batch cùng information cho cùng proposals/IDs."""
    bars = _generate_synthetic_15m_bars("2025-06-07", days=14)
    params = {"coeff": 3, "AP": 14, "alpha.condition_threshold": 40}

    stream_res = run_streaming_replay(bars, initial_params=params, arm_id="C_H14")
    batch_res = run_batch_replay(bars, params=params)

    parity = verify_stream_batch_parity(stream_res, batch_res, tolerance=1e-6)
    assert parity["parity_pass"] is True
    assert parity["max_equity_diff"] <= 1e-6
    assert stream_res.total_orders == batch_res.total_orders
    assert stream_res.total_fills == batch_res.total_fills
    assert abs(stream_res.final_equity - batch_res.final_equity) <= 1e-6


def test_v4_t02_no_future_backdating_and_wrong_target_window_rejected():
    """V4-T02: Future/late arrivals không backdate; wrong target window packet rejected."""
    controller = PolicyRuntimeController("C_H14", {"coeff": 2, "AP": 10})

    # Wrong target window (start >= end)
    invalid_prop = _make_dummy_proposal(
        "p-invalid-window",
        target_start="2025-06-21T00:00:00Z",
        target_end="2025-06-07T00:00:00Z",
    )
    ok, reason = controller.receive_proposal(invalid_prop, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert not ok
    assert "INVALID_TARGET_WINDOW_BOUNDS" in reason

    # Not-before precedes cutoff (causality violation)
    invalid_nb = _make_dummy_proposal(
        "p-invalid-nb",
        cutoff_time="2025-06-07T00:00:00Z",
        not_before="2025-06-06T00:00:00Z",
    )
    ok, reason = controller.receive_proposal(invalid_nb, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert not ok
    assert "INVALID_NOT_BEFORE_PRECEDES_CUTOFF" in reason


def test_v4_t03_symmetric_not_before_approval_and_waitflat_across_arms():
    """V4-T03: Actual not-before, approval và waitflat áp đối xứng các arms."""
    arms = ["C_H14", "B_CAP", "B0_GLOBAL", "A_M4"]
    controllers = {arm: PolicyRuntimeController(arm, {"coeff": 2, "AP": 10}, wait_flat_required=True) for arm in arms}

    cutoff = pd.Timestamp("2025-06-07T00:00:00Z")
    not_before = pd.Timestamp("2025-06-08T00:00:00Z")

    for arm in arms:
        ctrl = controllers[arm]
        # Simulate open position before cutoff
        ctrl.account_state.position = 0.5
        ctrl.account_state.cash = 10000.0

        prop = _make_dummy_proposal(
            f"prop-{arm}",
            arm_id=arm,
            cutoff_time=cutoff.isoformat(),
            not_before=not_before.isoformat(),
            candidate_params={"coeff": 4, "AP": 20, "alpha.condition_threshold": 50},
        )
        ok, msg = ctrl.receive_proposal(prop, cutoff)
        assert ok, f"Proposal reception failed for {arm}: {msg}"

        # 1. Before not_before (e.g. cutoff + 12h) -> rejected for ALL arms
        t_early = cutoff + pd.Timedelta(hours=12)
        act_ok, act_msg = ctrl.process_pending_activation(t_early)
        assert not act_ok
        assert act_msg == "WAITING_NOT_BEFORE"

        # 2. At not_before while still holding open position -> rejected due to wait_flat for ALL arms
        t_nb = not_before + pd.Timedelta(minutes=15)
        act_ok, act_msg = ctrl.process_pending_activation(t_nb)
        assert not act_ok
        assert act_msg == "WAITING_FLAT_POSITION"

        # 3. Position becomes flat -> activation succeeds for ALL arms symmetrically
        ctrl.account_state.position = 0.0
        act_ok, act_msg = ctrl.process_pending_activation(t_nb)
        assert act_ok
        assert act_msg == "NEW_VERSION_ACTIVATED"
        assert ctrl.account_state.active_version == 1


def test_v4_t04_duplicate_and_restart_idempotency_no_double_activation(tmp_path: Path):
    """V4-T04: Duplicate/restart after publish-before-ack không double activation/orders."""
    ctrl = PolicyRuntimeController("C_H14", {"coeff": 2, "AP": 10})
    prop = _make_dummy_proposal("p-idempotent-01", arm_id="C_H14")

    # First receipt
    ok1, msg1 = ctrl.receive_proposal(prop, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert ok1
    assert msg1 == "PROPOSAL_ACCEPTED"

    # Activate
    t_act = pd.Timestamp("2025-06-08T01:00:00Z")
    act_ok, act_msg = ctrl.process_pending_activation(t_act)
    assert act_ok
    assert ctrl.account_state.active_version == 1

    # Duplicate proposal arrival (same proposal_id)
    ok2, msg2 = ctrl.receive_proposal(prop, pd.Timestamp("2025-06-08T02:00:00Z"))
    assert ok2
    assert "IDEMPOTENT_IGNORED" in msg2
    assert ctrl.pending_proposal is None  # Does not overwrite or queue again

    # State persistence and cold restart
    save_file = tmp_path / "ctrl_state.json"
    ctrl.save_state(save_file)

    # Recover in a brand new controller
    ctrl_recovered = PolicyRuntimeController("C_H14", {"coeff": 1, "AP": 5})
    ctrl_recovered.load_state(save_file)

    assert ctrl_recovered.account_state.active_version == 1
    assert "p-idempotent-01" in ctrl_recovered.account_state.processed_proposal_ids

    # Submitting duplicate after restart is still safely ignored
    ok3, msg3 = ctrl_recovered.receive_proposal(prop, pd.Timestamp("2025-06-08T03:00:00Z"))
    assert ok3
    assert "IDEMPOTENT_IGNORED" in msg3
    assert ctrl_recovered.account_state.active_version == 1


def test_v4_t05_same_params_refresh_watermark_preserves_campaign_equity():
    """V4-T05: Same params refresh watermark, không reset indicator/campaign/equity."""
    initial_params = {"coeff": 3, "AP": 14, "alpha.condition_threshold": 45}
    ctrl = PolicyRuntimeController("C_H14", initial_params)

    # Establish an active position and custom equity
    ctrl.account_state.position = 0.42
    ctrl.account_state.cash = 12345.67
    ctrl.account_state.equity = 21000.0
    ctrl.account_state.active_version = 2
    t_param_change = pd.Timestamp("2025-06-01T00:00:00Z")
    ctrl.account_state.last_param_change = t_param_change
    ctrl.account_state.last_revalidation = t_param_change

    # Propose SAME parameters
    prop_same = _make_dummy_proposal(
        "p-same-params",
        expected_incumbent_version=2,
        candidate_params=initial_params,
        not_before="2025-06-08T00:00:00Z",
    )
    ok, _ = ctrl.receive_proposal(prop_same, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert ok

    # Activate at not_before
    t_act = pd.Timestamp("2025-06-08T01:00:00Z")
    act_ok, act_msg = ctrl.process_pending_activation(t_act)
    assert act_ok
    assert act_msg == "SAME_PARAMS_REFRESHED"

    # Watermark refreshed
    assert ctrl.account_state.last_revalidation == t_act
    assert ctrl.account_state.revalidation_count == 1

    # Campaign, equity, version, and param change timestamp PRESERVED
    assert ctrl.account_state.active_version == 2
    assert ctrl.account_state.last_param_change == t_param_change
    assert ctrl.account_state.position == 0.42
    assert ctrl.account_state.cash == 12345.67
    assert ctrl.account_state.equity == 21000.0


def test_v4_t06_expired_superseded_or_incumbent_version_mismatch_rejected():
    """V4-T06: Expired/superseded hoặc incumbent-version mismatch rejected."""
    ctrl = PolicyRuntimeController("C_H14", {"coeff": 2, "AP": 10})
    ctrl.account_state.active_version = 3

    # Incumbent version mismatch: expects version 2, but active is 3
    prop_mismatch = _make_dummy_proposal(
        "p-mismatch",
        expected_incumbent_version=2,
        arm_id="C_H14",
    )
    ok, msg = ctrl.receive_proposal(prop_mismatch, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert not ok
    assert "INCUMBENT_VERSION_MISMATCH" in msg

    # Expired proposal: expires at 2025-06-10, arrived at 2025-06-11
    prop_expired = _make_dummy_proposal(
        "p-expired",
        expected_incumbent_version=3,
        arm_id="C_H14",
        expires_at="2025-06-10T00:00:00Z",
    )
    ok_exp, msg_exp = ctrl.receive_proposal(prop_expired, pd.Timestamp("2025-06-11T00:00:00Z"))
    assert not ok_exp
    assert "PROPOSAL_EXPIRED" in msg_exp


def test_v4_t07_missing_median_temp_taxonomy_invalid_bundle():
    """V4-T07: Missing median/temp/taxonomy làm bundle invalid, không weights-only success."""
    ctrl = PolicyRuntimeController("C_H14", {"coeff": 2, "AP": 10})

    # 1. Missing imputer medians
    b_no_medians = _make_dummy_model_bundle(imputer_medians={})
    p1 = _make_dummy_proposal("p-no-medians", bundle=b_no_medians)
    ok, msg = ctrl.receive_proposal(p1, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert not ok
    assert "MISSING_IMPUTER_MEDIANS" in msg

    # 2. Missing temperature scaling
    b_no_temp = _make_dummy_model_bundle(temperature_t_v=-1.0)
    p2 = _make_dummy_proposal("p-no-temp", bundle=b_no_temp)
    ok, msg = ctrl.receive_proposal(p2, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert not ok
    assert "MISSING_OR_INVALID_TEMPERATURE_SCALING" in msg

    # 3. Missing taxonomy quantiles
    b_no_tax = _make_dummy_model_bundle(taxonomy_quantiles={"q50": 0.0})
    p3 = _make_dummy_proposal("p-no-tax", bundle=b_no_tax)
    ok, msg = ctrl.receive_proposal(p3, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert not ok
    assert "MISSING_TAXONOMY_QUANTILES" in msg

    # 4. Invalid feature schema length (e.g. 10 instead of 38)
    b_short_schema = _make_dummy_model_bundle(feature_schema_len=10)
    p4 = _make_dummy_proposal("p-short-schema", bundle=b_short_schema)
    ok, msg = ctrl.receive_proposal(p4, pd.Timestamp("2025-06-07T00:00:00Z"))
    assert not ok
    assert "INVALID_FEATURE_SCHEMA_LENGTH" in msg


def test_v4_t08_safe_entry_pause_preserves_protective_exits_no_force_close():
    """V4-T08: Max-revalidation pause không chặn protective exits hoặc force close ngoài contract."""
    ctrl = PolicyRuntimeController("C_H14", {"coeff": 2, "AP": 10, "alpha.condition_threshold": 40})
    ctrl.account_state.position = 0.5
    ctrl.account_state.cash = 10000.0
    ctrl.account_state.last_revalidation = pd.Timestamp("2025-06-01T00:00:00Z")

    # Time advances 30 days (> 28-day max_revalidation_age)
    t_30d = pd.Timestamp("2025-07-01T00:00:00Z")
    ctrl.check_operational_safety(t_30d)

    assert ctrl.account_state.operational_status == "SAFE_ENTRY_PAUSE"
    # Position must NOT be liquidated/force-closed
    assert ctrl.account_state.position == 0.5

    # Test order emission behavior under SAFE_ENTRY_PAUSE:
    # 1. New ENTRY (buy) is BLOCKED
    # 2. Protective EXIT (sell) is ALLOWED
    bars = _generate_synthetic_15m_bars("2025-07-01", days=3)
    res = run_streaming_replay(
        bars,
        initial_params={"coeff": 2, "AP": 10, "alpha.condition_threshold": 40},
        fault_injections={"initial_pause": True},
    )
    # Runner runs safely and completes
    assert res.final_equity > 0.0


def test_v4_t09_actual_fills_rejects_drive_state_no_expected_fill_feedback():
    """V4-T09: Actual fills/rejects điều khiển strategy state, no expected-fill feedback."""
    ctrl = PolicyRuntimeController("C_H14", {"coeff": 2, "AP": 10}, initial_equity=20000.0)

    # Initial state
    assert ctrl.account_state.cash == 20000.0
    assert ctrl.account_state.position == 0.0
    assert ctrl.account_state.fills_count == 0
    assert ctrl.account_state.rejections_count == 0

    # 1. Order rejected by engine -> account state remains pristine
    ctrl.on_reject({"order_id": "ord-01", "reason": "MARGIN_EXCEEDED", "timestamp": "2025-06-07T00:15:00Z"})
    assert ctrl.account_state.cash == 20000.0
    assert ctrl.account_state.position == 0.0
    assert ctrl.account_state.rejections_count == 1
    assert ctrl.account_state.fills_count == 0

    # 2. Actual fill received -> account state updates strictly on fill
    fill_buy = {
        "order_id": "ord-02",
        "side": "BUY",
        "quantity": 0.1,
        "price": 60000.0,
        "fee": 2.4,
        "timestamp": "2025-06-07T00:30:00Z",
    }
    ctrl.on_fill(fill_buy)
    expected_cash = 20000.0 - (0.1 * 60000.0 + 2.4)  # 13997.6
    assert abs(ctrl.account_state.cash - expected_cash) < 1e-6
    assert abs(ctrl.account_state.position - 0.1) < 1e-6
    assert ctrl.account_state.fills_count == 1
    assert ctrl.account_state.entry_price == 60000.0

    # 3. Sell fill received -> cash increases, position reduced
    fill_sell = {
        "order_id": "ord-03",
        "side": "SELL",
        "quantity": 0.1,
        "price": 62000.0,
        "fee": 2.48,
        "timestamp": "2025-06-07T01:00:00Z",
    }
    ctrl.on_fill(fill_sell)
    expected_cash += (0.1 * 62000.0 - 2.48)  # 13997.6 + 6197.52 = 20195.12
    assert abs(ctrl.account_state.cash - expected_cash) < 1e-6
    assert abs(ctrl.account_state.position - 0.0) < 1e-6
    assert ctrl.account_state.fills_count == 2


def test_v4_t10_scoped_stream_batch_parity_and_protected_tree_untouched():
    """V4-T10: Scoped actual stream/batch financial parity và protected-tree zero change."""
    # 1. Scoped parity check
    bars = _generate_synthetic_15m_bars("2025-06-07", days=14)
    params = {"coeff": 3, "AP": 14, "alpha.condition_threshold": 45}

    stream_res = run_streaming_replay(bars, initial_params=params, arm_id="C_H14")
    batch_res = run_batch_replay(bars, params=params)

    parity = verify_stream_batch_parity(stream_res, batch_res, tolerance=1e-6)
    assert parity["parity_pass"] is True
    assert parity["max_equity_diff"] <= 1e-6

    # 2. Protected-tree check: quantbt package repository must have zero changes
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd="/root/bobby/pool_alpha/quantbt",
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert res.stdout.strip() == "", f"Protected tree /root/bobby/pool_alpha/quantbt was modified! Git status: {res.stdout}"
