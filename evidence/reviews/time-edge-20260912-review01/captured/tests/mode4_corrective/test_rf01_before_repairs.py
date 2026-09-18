"""RF-01 before-repair tests — correct behaviour the repaired pipeline must show.

These tests are written against the audited source and are EXPECTED TO FAIL until
their finding is fixed (A02 backdating, A03 non-converged scoring, A04 corrective
follow-up, A05 HMA stop-mode collapse, A07 episode boundary PnL, A10 namespace
false trigger). Each failure is recorded in the RF-01 phase report as
failing-before evidence. No test asserts that a bug is present: every one asserts
the behaviour the corrected pipeline must have.

The artifact guards (A09/E quarantine, A15 corrected MDE registration, A16 claim
gate) must already pass; they pin the decisions registered in RF-01.2 so a later
change cannot quietly undo them.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.evidence.claim_gate import statistical_status_allowed


def _frame(n: int = 12) -> pd.DataFrame:
    close = 100 + 3 * np.sin(np.arange(n) * 0.3)
    return pd.DataFrame(
        {"open": close, "high": close + 0.3, "low": close - 0.3,
         "close": close, "volume": np.ones(n) * 100},
        index=pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
    )


# --- A05 ------------------------------------------------------------------

def _a_hma_sl_choices() -> tuple[str, ...]:
    from crypto_regime_lab.selector.alpha_schemas import A_HMA

    specs = getattr(A_HMA, "specs", ())
    sequence = specs.values() if isinstance(specs, dict) else specs
    for spec in sequence:
        if getattr(spec, "name", None) == "sl_input":
            return tuple(spec.choices)
    raise AssertionError("A-HMA schema has no sl_input parameter")


def test_a05_a_hma_search_choices_do_not_collapse_into_one_stop_mode():
    from crypto_regime_lab.alphas.a_hma import SL_MODES

    choices = _a_hma_sl_choices()
    assert len(choices) >= 2
    effective = {choice: SL_MODES.get(choice) for choice in choices}
    assert None not in effective.values(), (
        f"a searched sl_input choice has no adapter mode and silently defaults: {effective}")
    assert len(set(effective.values())) == len(choices), (
        f"distinct searched stop policies collapse to the same effective mode: {effective}")


# --- A02 ------------------------------------------------------------------

def test_a02_a_future_selected_version_is_not_active_before_its_requested_bar():
    from crypto_regime_lab.integration.continuous_account import (
        VersionWindow, run_continuous_account,
    )
    from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS

    frame = _frame(200)
    future = VersionWindow("FUTURE_SELECTED", dict(SEED_POINTS["A-HMA"]), 100, "future")
    run = run_continuous_account("A-HMA", frame, initial=future, schedule=[], backend="reference")
    assert "FUTURE_SELECTED" not in run.version_by_bar[:100], (
        "a parameter version selected at bar 100 is active before it was requested")
    assert run.version_by_bar[100] == "FUTURE_SELECTED"


# --- A03 ------------------------------------------------------------------

def test_a03_a_non_converged_candidate_is_not_financially_evaluated():
    from crypto_regime_lab.experiments import calendar_baseline as cb, evaluator as ev
    from crypto_regime_lab.selector.alpha_schemas import SCHEMAS, SEED_POINTS

    frame = _frame(12)
    bad = ev.CandidateRun(np.arange(12) * 1.0 + 20000, np.zeros(12), [], frame.index, False, 4, 0, 3)
    with patch.object(cb, "run_candidate", return_value=bad):
        result = cb._evaluate("A-SC", SEED_POINTS["A-SC"], frame, [("e0", 0, 12)],
                              "audit", SCHEMAS["A-SC"], "reference")
    assert result.status != cb.ProbeStatus.EVALUATED, (
        "a run that did not converge and left unmapped intents was scored")


# --- A04 ------------------------------------------------------------------

def test_a04_a_corrective_followup_exit_must_reach_the_position():
    from crypto_regime_lab.alphas.contracts import (
        BarDecision, ExecutionPhase, IntentKind, OrderIntent,
    )
    from crypto_regime_lab.experiments import evaluator as ev

    class Stub:
        def __init__(self):
            self.state = SimpleNamespace(position=0.0)
            self.followups: list = []

        def on_bar_close(self, index):
            intents = ([OrderIntent(kind=IntentKind.ENTER_LONG, decision_index=index,
                                    earliest_phase=ExecutionPhase.NEXT_OPEN, reason="audit")]
                       if index == 2 else [])
            return BarDecision(index=index, position_entering_bar=self.state.position,
                               target_after_close=self.state.position, intents=intents)

        def on_fill(self, fill):
            self.state.position += fill.quantity
            if fill.intent_kind == IntentKind.ENTER_LONG:
                exit_all = OrderIntent(kind=IntentKind.EXIT_ALL, decision_index=fill.index,
                                       earliest_phase=ExecutionPhase.NEXT_OPEN,
                                       reason="bracket_invalid_after_gap")
                self.followups.append(exit_all)
                return [exit_all]
            return []

    frame = pd.DataFrame({key: np.full(12, 100.0)
                          for key in ("open", "high", "low", "close", "volume")},
                         index=pd.date_range("2024-01-01", periods=12, freq="15min", tz="UTC"))
    stub = Stub()
    with patch.object(ev, "build_adapter", return_value=stub):
        ev._sweep("AUDIT", {}, frame,
                  [frame[key].to_numpy() for key in ("open", "high", "low", "close", "volume")],
                  frame, backend="reference")
    assert stub.followups, "the test stub never produced a corrective exit"
    assert stub.state.position == pytest.approx(0.0), (
        "the corrective follow-up exit was generated but never applied to the position")


# --- A07 ------------------------------------------------------------------

def test_a07_episode_money_deltas_telescope_to_the_whole_account_delta():
    from crypto_regime_lab.experiments import evaluator as ev

    frame = _frame(4)
    equity = np.array([20000.0, 20000.0, 19000.0, 19000.0])
    run = ev.CandidateRun(equity, np.zeros(4), [], frame.index, True, 1, 0)
    metrics = ev.episode_metrics(run, [("e0", 0, 2), ("e1", 2, 4)])
    total_money = sum(value["net_return"] for value in metrics.values()) * 20000.0
    assert total_money == pytest.approx(equity[-1] - equity[0]), (
        "block returns do not telescope to the whole-account money delta; "
        "the move across the block boundary is dropped")


# --- A10 ------------------------------------------------------------------

def test_a10_a_namespace_change_or_ineligible_emission_does_not_trigger_a_refit():
    from crypto_regime_lab.experiments.regime_schedule import transition_cutoffs

    emissions = [
        {"state_namespace": "v1", "state_id": 0, "available_at": "2024-01-01T00:00:00Z",
         "decision_eligible": True},
        {"state_namespace": "v2", "state_id": 0, "available_at": "2024-01-02T00:00:00Z",
         "decision_eligible": False, "quality_status": "MISSING_DATA"},
    ]
    schedule = transition_cutoffs(emissions, count=1, earliest="2024-01-01",
                                  latest="2024-01-04", min_gap_days=0)
    assert len(schedule.cutoffs) == 0, (
        "a namespace-only change or a decision_eligible=false emission produced a refit")


# --- artifact guards ------------------------------------------------------

def test_a09_the_old_e_arm_is_quarantined_not_wired_from_d(lab_root):
    invalidation = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-01" / "historical_invalidation.json")
        .read_text(encoding="utf-8"))
    spec = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-01" / "corrective_study_spec.json")
        .read_text(encoding="utf-8"))
    assert invalidation["e_arm"]["repaired_claim_status"] == "NOT_IMPLEMENTED_AS_SPECIFIED"
    assert spec["arms"]["E_RESPONSE_V2_status"].startswith("DISABLED")


def test_a15_the_corrected_mde_derivation_is_registered_and_history_preserved(lab_root):
    spec = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-01" / "corrective_study_spec.json")
        .read_text(encoding="utf-8"))
    assert spec["mde"]["historical_registered"]["value"] == pytest.approx(6.4e-05)
    formula = spec["mde"]["corrected_derivation"]["formula"]
    assert "notional_over_equity" in formula
    assert spec["mde"]["corrected_derivation"]["status"].startswith("PENDING_RF02")


def test_a16_a_blocked_pipeline_may_only_report_not_evaluable():
    allowed, _ = statistical_status_allowed("FAIL", "DEVIATED", "NOT_EVALUABLE")
    assert allowed
    for status in ("INCONCLUSIVE", "NEGATIVE_WITHIN_SCOPE", "POSITIVE_WITHIN_SCOPE"):
        allowed, reason = statistical_status_allowed("FAIL", "DEVIATED", status)
        assert not allowed and "NOT_EVALUABLE" in reason
    allowed, _ = statistical_status_allowed("PASS", "AS_SPECIFIED", "INCONCLUSIVE")
    assert allowed
    with pytest.raises(ValueError):
        statistical_status_allowed("UNKNOWN", "AS_SPECIFIED", "INCONCLUSIVE")
