"""Characterisation tests for the regime facility already inside QuantBT 1.1.1.

These lock in what the installed engine actually does, so a later claim like
"QuantBT already does regime" cannot be made loosely, and so an upstream change
in semantics is caught rather than absorbed.
"""

from __future__ import annotations

import numpy as np
import pytest

quantbt = pytest.importorskip("quantbt")


def test_labels_are_not_causal_within_the_window():
    """Mutating only the tail changes labels in the prefix (guide 8.4 / T25 shape)."""
    rng = np.random.default_rng(20260909)
    base = rng.normal(0.0, 0.005, 400)
    mutated = base.copy()
    mutated[300:] = rng.normal(0.0, 0.05, 100)

    prefix_base = quantbt.volatility_regime_labels(base, regime_count=3, lookback=20)[:300]
    prefix_mut = quantbt.volatility_regime_labels(mutated, regime_count=3, lookback=20)[:300]

    changed = int(np.sum(prefix_base != prefix_mut))
    assert changed > 0, (
        "expected in-sample quantile cuts to make prefix labels depend on later data; "
        "if this now passes causally, the lab's M0 comparator description must be revised"
    )


def test_labels_are_direction_blind():
    rng = np.random.default_rng(11)
    up = np.abs(rng.normal(0.0, 0.01, 300))
    assert np.array_equal(
        quantbt.volatility_regime_labels(up, regime_count=3, lookback=20),
        quantbt.volatility_regime_labels(-up, regime_count=3, lookback=20),
    )


def test_labels_are_equal_frequency_by_construction():
    """Quantile bucketing gives ~equal counts, so label frequency carries no state evidence."""
    rng = np.random.default_rng(7)
    series = np.concatenate([rng.normal(0, 0.002, 300), rng.normal(0, 0.02, 300)])
    labels = quantbt.volatility_regime_labels(series, regime_count=3, lookback=20)
    _, counts = np.unique(labels, return_counts=True)
    assert counts.max() - counts.min() <= 2, counts


def test_constant_series_is_labelled_highest_regime_not_lowest():
    """Degenerate edge case: zero dispersion collapses the cuts and yields label K-1."""
    labels = quantbt.volatility_regime_labels(np.zeros(200), regime_count=3, lookback=20)
    assert set(labels.tolist()) == {2}, (
        "a flat series lands in the HIGHEST volatility bucket; any lab code reusing this "
        "labeller must handle zero dispersion explicitly rather than trust the label"
    )


def test_empty_input_returns_empty_not_an_exception():
    assert quantbt.volatility_regime_labels(np.array([]), regime_count=3, lookback=20).size == 0


def test_target_execution_contract_exists_in_this_install():
    """The guide's primary clock must be a real contract, not an assumed one."""
    assert quantbt.EVENT_LIFECYCLE_V3_NEXT_OPEN in quantbt.EXECUTION_CONTRACT_REGISTRY
    assert quantbt.EVENT_LIFECYCLE_V3_NEXT_OPEN in quantbt.EVENT_CLOCK_CONTRACTS


def test_installed_baseline_is_the_guide_baseline():
    import importlib.metadata as md

    assert md.version("quantbt-engine") == "1.1.1"
    assert md.version("quantbt-native") == "0.4.2"


def test_quantbt_is_imported_from_the_lab_venv_not_the_protected_tree():
    origin = quantbt.__file__
    assert "/lab_regime_model_quantbt/environments/lab_venv/" in origin, origin
    assert "/pool_alpha/quantbt/" not in origin, origin
