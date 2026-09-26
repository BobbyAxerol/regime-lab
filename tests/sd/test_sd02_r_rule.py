"""Coverage for sd/r_rule.py (guide SS5.7)."""
from __future__ import annotations

import pytest

from crypto_regime_lab.sd import r_rule


def test_fit_threshold_is_median_of_train_only_ratios():
    ratios = [-0.5, -0.1, 0.2, 0.4, 1.0]
    assert r_rule.fit_threshold(ratios) == pytest.approx(0.2)


def test_fit_threshold_rejects_empty_input():
    with pytest.raises(r_rule.RRuleError):
        r_rule.fit_threshold([])


def test_assign_state_high_vol_at_or_above_threshold():
    assert r_rule.assign_state(0.5, threshold=0.2) == r_rule.HIGH_VOL_STATE
    assert r_rule.assign_state(0.2, threshold=0.2) == r_rule.HIGH_VOL_STATE  # boundary is inclusive high


def test_assign_state_low_vol_below_threshold():
    assert r_rule.assign_state(0.1, threshold=0.2) == r_rule.LOW_VOL_STATE


def test_states_are_binary_and_distinct():
    assert r_rule.HIGH_VOL_STATE != r_rule.LOW_VOL_STATE
    assert {r_rule.HIGH_VOL_STATE, r_rule.LOW_VOL_STATE} == {0, 1}


def test_state_by_origin_maps_every_origin_and_preserves_none():
    ratios = {"o1": 0.5, "o2": 0.1, "o3": None}
    out = r_rule.state_by_origin(ratios, threshold=0.2)
    assert out["o1"] == r_rule.HIGH_VOL_STATE
    assert out["o2"] == r_rule.LOW_VOL_STATE
    assert out["o3"] is None
