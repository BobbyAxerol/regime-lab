"""FUP-04 — the reduced engine output profiles stay account-path exact.

Real defects behind this file (mem_audit, 2026-09-20): a single
``run_event_account`` call over the full 613k-bar deployment frame drove RSS to
4.24 GiB and the kernel OOM-killed the process (dmesg, same night). The
engine's own documented ``report_level`` kwarg (1.1.1) selects its output
retention profile; measured on the real RA-05 fold-0 account call, the
``score``/``minimal`` profiles reproduce the engine-default account path
EXACTLY (byte-equal equity, identical strategy-level fill/entry counts) while
dropping per-bar audit ledgers (peak 917 -> 497 MiB, wall 20 s -> 5 s).
These tests pin the parity so the opt-in cannot silently drift:

* equity paths are byte-identical between the engine default and ``score``;
* scorer-relevant counters come from profile-invariant strategy-level records
  (the native audit-trail count legitimately reads 0 under reduced profiles);
* the lab plumbing forwards ``report_level`` end-to-end instead of dropping it.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pandas as pd

from crypto_regime_lab.experiments import dynamic_fold_provider as DFP
from crypto_regime_lab.integration import event_account as EA
from crypto_regime_lab.integration.continuous_account import VersionWindow
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS


def _frame(n: int = 120) -> pd.DataFrame:
    close = 100 + 10 * np.sin(np.arange(n) / 9.0) + 0.05 * np.arange(n)
    return pd.DataFrame({"open": close, "high": close + 0.4, "low": close - 0.4,
                         "close": close, "volume": np.full(n, 1000.0)},
                        index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"))


def test_fup04_score_profile_equity_is_exact_vs_engine_default():
    """The compact profile must reproduce the default profile's account path
    byte-for-byte on a real (unstubbed) A-SC account, or no caller may opt in."""
    runs = {}
    for level in (None, "score"):
        runs[level] = EA.run_event_account(
            "A-SC", _frame(240),
            initial=VersionWindow("V1", dict(SEED_POINTS["A-SC"]), 0, "v1"),
            schedule=[], report_level=level)
    default_run, score_run = runs[None], runs["score"]
    assert default_run.status == "EVALUATED" and score_run.status == "EVALUATED"
    assert default_run.engine_fill_count > 0, "fixture must actually trade"
    np.testing.assert_array_equal(np.asarray(default_run.equity, dtype=float),
                                  np.asarray(score_run.equity, dtype=float))
    assert int(score_run.engine_fill_count) == 0, (
        "reduced profiles drop the native audit trail; if this ever returns "
        "here, the engine's contract changed and the counting note in "
        "dynamic_fold_provider must be re-derived, not assumed")
    assert len(score_run.fills) == len(default_run.fills), (
        "strategy-level fills must stay profile-invariant")


def test_fup04_scorer_fields_are_profile_invariant():
    """turnover/trade_count feed selection; they must not read the audit-only
    counter that reduced profiles zero out."""
    frame = _frame(120)
    scorer = DFP.EventAccountScorer("A-SC", engine_report_level="score")
    task = {"data": frame, "index": frame.index,
            "params": dict(SEED_POINTS["A-SC"]),
            "context": "test", "trading_days": 365, "fold": None}
    scores = scorer.score_batch([task])[0]
    assert scores["status"] == "EVALUATED", scores
    assert scores["trade_count"] > 0.0, (
        "a reduced-profile scorer run must still count fills (strategy-level), "
        "never silently zero the selection field")


def test_fup04_report_level_is_forwarded_to_the_engine():
    """Plumbing check: the account path forwards report_level exactly once with
    the caller's value (None forwards nothing and keeps the engine default),
    and the ENGINE-reported resolved profile is recorded for provenance.
    `event_account` imports quantbt inside the call, so the stub is installed in
    sys.modules."""
    captured = {}

    def _fake_native_event_strategy(**kwargs):
        captured.update(kwargs)
        # Mirror the real backend: the engine reports which output profile it
        # actually used (see quantbt/backends/native_event.py metadata).
        resolved = "compact" if kwargs.get("report_level") == "score" else "audit"

        class _Endpoint:
            def simulate(self, data, strategy):
                return types.SimpleNamespace(
                    equity=np.linspace(20000.0, 20100.0, len(data)),
                    positions=np.zeros(len(data)), fills=[],
                    metadata={"rust_output_profile": resolved,
                              "native_event_backend_resolved": "native_event"})

        return _Endpoint()

    fake_q = types.ModuleType("quantbt")
    fake_q.QuantBTEndpoint = types.SimpleNamespace(
        native_event_strategy=staticmethod(_fake_native_event_strategy))
    fake_q.AccountConfig = lambda **kwargs: types.SimpleNamespace(**kwargs)
    initial = VersionWindow("V1", dict(SEED_POINTS["A-SC"]), 0, "v1")
    saved = sys.modules.get("quantbt")
    sys.modules["quantbt"] = fake_q
    try:
        run = EA.run_event_account("A-SC", _frame(24), initial=initial,
                                   schedule=[], report_level="score")
        assert captured.get("report_level") == "score"
        assert run.diagnostics["report_level"] == "score"
        assert run.diagnostics["resolved_report_level"] == "compact", (
            "provenance must carry the engine's own resolved profile, not the "
            "caller's request echoed back")
        captured.clear()
        run_default = EA.run_event_account("A-SC", _frame(24), initial=initial,
                                           schedule=[], report_level=None)
        assert "report_level" not in captured, (
            "None must keep the engine's own default, not pin today's value")
        assert run_default.diagnostics["report_level"] is None
        assert run_default.diagnostics["resolved_report_level"] == "audit", (
            "the engine default must remain distinguishable from a reduced "
            "profile in the recorded diagnostics")
    finally:
        if saved is None:
            sys.modules.pop("quantbt", None)
        else:
            sys.modules["quantbt"] = saved


def test_fup04_walkforward_records_the_resolved_report_level():
    """End-to-end over the real event route: the provider's payload trace must
    record the level it asked the engine for (a silent drop would make a
    reduced-profile run indistinguishable from a default-profile one)."""
    schedule = DFP.CutoffSchedule(
        arm="M4_CAL", cutoffs=("2024-01-08T00:00:00+00:00", "2024-01-16T00:00:00+00:00"),
        source="test fixture", train_memory_days=7)
    wf = DFP.run_cutoff_walk_forward(
        "A-SC", _frame(20 * 24), schedule, param_ranges=DFP.engine_param_ranges("A-SC"),
        strategy_class=DFP.ZeroSignalStrategy, optuna_trials=1, seed=7, route="event",
        engine_report_level="minimal")
    assert wf.get("ok") is True, wf.get("error")
    assert (wf.get("trace") or {}).get("engine_report_level") == "minimal"

