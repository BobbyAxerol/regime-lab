"""Explicit TE-01 red baseline; intentionally outside automatic test_ discovery.

Each assertion asks for correct behavior. Known failures remain real failures,
not xfails or bug=True passes. No QuantBT simulation is performed. Run this file
explicitly; the evidence runner separates baseline failures from contract tests.
"""
from pathlib import Path
import runpy

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def observations():
    module = runpy.run_path(str(ROOT / "scripts/audit_time_edge_review.py"))
    sources = {path: (ROOT / path).read_bytes() for path in (
        "src/crypto_regime_lab/experiments/regime_schedule.py",
        "scripts/run_rf04_decay_and_controls.py", "scripts/run_rf05.py")}
    return module["source_probes"](sources)


def test_rf05_excludes_pre_evaluation_return(observations):
    assert observations["rf05_window"]["out_of_window_return_retained"] is False


def test_adjacent_age_windows_are_half_open(observations):
    d = observations["decay"]
    assert (d["observed_H1_days"], d["observed_H2_days"]) == (90, 90)


def test_d2_uses_the_computed_pf_key(observations):
    d = observations["decay"]
    assert d["d2_lookup_profit_factor_value"] == pytest.approx(d["daily_profit_factor_value"])


def test_only_losses_are_zero_pf_not_no_trades(observations):
    result = observations["decay"]["all_loss_daily_returns_result"]
    assert result["profit_factor_daily"] == 0.0


def test_future_model_ready_cannot_trigger(observations):
    assert observations["scheduler"]["future_model_ready_triggered"] == []


def test_missing_eligibility_cannot_trigger(observations):
    assert observations["scheduler"]["missing_eligibility_fields_triggered"] == []


def test_constant_state_has_registered_max_age(observations):
    assert len(observations["scheduler"]["constant_state_365_observations_max_age_180_triggers"]) >= 1


def test_unavailable_training_targets_do_not_change_profile(monkeypatch):
    from crypto_regime_lab.regime import ablation
    # Isolate the actual target-profile/purge logic. The stub is only a fixed
    # fitted centroid provider, not a learned-regime or economic power claim.
    monkeypatch.setattr(ablation, "multi_start_fit", lambda z, w, **kw: {
        "centroids": np.array([[-1.0], [1.0]])})
    raw = np.tile([-1.0, 1.0], 20).reshape(-1, 1)
    target = np.arange(40, dtype=float)
    kwargs = dict(all_features=("g1_test",), weights=np.ones(1), cohort=np.ones(40, dtype=bool),
                  n_states=2, lambda_jump=0.5, seeds=(11,), ladder=(("G1",),),
                  n_folds=1, min_train=20, purge_rows=6)
    before = ablation.fixed_target_ablation(raw, target=target, **kwargs)
    changed = target.copy()
    changed[14:20] += 1000  # forward six-row outcomes not complete before train cutoff=20
    after = ablation.fixed_target_ablation(raw, target=changed, **kwargs)
    assert before["ladder"][0]["folds"][0]["global_train_target_mean"] == after["ladder"][0]["folds"][0]["global_train_target_mean"]
