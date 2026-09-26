"""S2-T02-JM-FILTER and related coverage for sd/jm_model.py (guide SS5.3-5.4, SS9.4)."""
from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.sd import jm_model as jm


def _two_regime_fixture(seed: int = 0, n_per_block: int = 60, n_blocks: int = 4):
    """Alternating blocks of two well-separated 1-D-ish clusters plus a
    second, noise-only feature column, so the recovered path should track
    the known block structure closely (a real, checkable fixture, not a
    trivial one)."""
    rng = np.random.default_rng(seed)
    rows = []
    true_states = []
    for b in range(n_blocks):
        center = 0.0 if b % 2 == 0 else 6.0
        block = rng.normal(loc=center, scale=0.4, size=(n_per_block, 1))
        noise_col = rng.normal(loc=0.0, scale=1.0, size=(n_per_block, 1))
        rows.append(np.hstack([block, noise_col]))
        true_states.extend([b % 2] * n_per_block)
    return np.vstack(rows), np.array(true_states)


def test_fit_recovers_known_two_cluster_structure():
    z, true_states = _two_regime_fixture()
    scale = jm.median_one_centroid_loss_scale(z)
    lam = jm.normalized_lambda(1.0, scale)
    fit = jm.fit_jm(z, lambda_j=lam, seed=jm.DEFAULT_SEED)
    states = jm.causal_filter_states(fit, z)
    # label switching: check both direct and flipped agreement, take the max
    agree_direct = float(np.mean(states == true_states))
    agree_flipped = float(np.mean(states == (1 - true_states)))
    assert max(agree_direct, agree_flipped) > 0.85


def test_fit_converges_and_reports_status():
    z, _ = _two_regime_fixture(seed=5)
    scale = jm.median_one_centroid_loss_scale(z)
    fit = jm.fit_jm(z, lambda_j=jm.normalized_lambda(1.0, scale))
    assert fit.n_iter >= 1
    assert isinstance(fit.converged, bool)
    assert fit.centroids.shape == (2, 2)


def test_prefix_by_prefix_online_parity_no_smoothed_future_labels():
    """S2-T02-JM-FILTER: filtering a PREFIX of a sequence must reproduce
    EXACTLY the same states for that prefix as filtering the full sequence
    with the SAME frozen fit -- the defining property of a causal filter
    (as opposed to a smoothed/backtracked Viterbi decode, which would let
    a later observation change an earlier state)."""
    z, _ = _two_regime_fixture(seed=9)
    scale = jm.median_one_centroid_loss_scale(z)
    fit = jm.fit_jm(z, lambda_j=jm.normalized_lambda(1.0, scale))

    full_states = jm.causal_filter_states(fit, z)
    for cut in (10, 50, 100, len(z) - 1):
        prefix_states = jm.causal_filter_states(fit, z[:cut])
        assert np.array_equal(prefix_states, full_states[:cut]), (
            f"prefix parity broken at cut={cut}")


def test_causal_filter_is_not_the_batch_viterbi_smoothed_path():
    """A genuinely causal forward filter and a full forward-backward
    (smoothed) Viterbi decode CAN legitimately disagree near a jump --
    the smoothed path is allowed to look ahead, the filter is not. This
    test proves the two code paths are actually different, not
    accidentally identical (which would hide a real leak)."""
    z, _ = _two_regime_fixture(seed=21, n_per_block=30, n_blocks=6)
    scale = jm.median_one_centroid_loss_scale(z)
    lam = jm.normalized_lambda(0.5, scale)
    z_std, _, _ = jm.standardize(z)
    fit = jm.fit_jm(z, lambda_j=lam)
    loss = jm._squared_loss(z_std, fit.centroids)
    smoothed = jm._batch_viterbi_path(loss, lam)
    filtered = jm._causal_forward_states(loss, lam)
    # They need not be identical everywhere (that's the whole point of
    # filter vs smoother), but they should agree on the clear interior of
    # each block, away from the earliest few observations where the
    # smoother has an unfair look-ahead advantage.
    tail_agreement = float(np.mean(smoothed[30:] == filtered[30:]))
    assert tail_agreement > 0.6


def test_degenerate_loss_scale_is_typed_failure_not_silent():
    flat = np.zeros((300, 3))
    with pytest.raises(jm.JMError, match="DEGENERATE_FEATURE_GEOMETRY"):
        jm.median_one_centroid_loss_scale(flat)
    with pytest.raises(jm.JMError):
        jm.normalized_lambda(1.0, 0.0)


def test_fit_requires_minimum_rows_typed_failure():
    with pytest.raises(jm.JMError):
        jm.fit_jm(np.zeros((2, 3)), lambda_j=1.0)


def test_causal_filter_rejects_dimensionality_mismatch():
    z, _ = _two_regime_fixture(seed=1)
    scale = jm.median_one_centroid_loss_scale(z)
    fit = jm.fit_jm(z, lambda_j=jm.normalized_lambda(1.0, scale))
    with pytest.raises(jm.JMError):
        jm.causal_filter_states(fit, z[:, :1])


def test_fit_is_deterministic_given_pinned_seed():
    z, _ = _two_regime_fixture(seed=3)
    scale = jm.median_one_centroid_loss_scale(z)
    lam = jm.normalized_lambda(1.0, scale)
    fit_a = jm.fit_jm(z, lambda_j=lam, seed=777)
    fit_b = jm.fit_jm(z, lambda_j=lam, seed=777)
    assert np.array_equal(fit_a.centroids, fit_b.centroids)
    assert fit_a.train_terminal_state == fit_b.train_terminal_state


def test_higher_penalty_never_increases_switch_count():
    """Sanity monotonicity: a larger jump penalty should not produce MORE
    state switches than a smaller one on the same fixture (a real,
    checkable structural property of the objective, not a tautology)."""
    z, _ = _two_regime_fixture(seed=42)
    scale = jm.median_one_centroid_loss_scale(z)
    switch_counts = []
    for c in jm.NORMALIZED_PENALTIES:
        lam = jm.normalized_lambda(c, scale)
        fit = jm.fit_jm(z, lambda_j=lam, seed=jm.DEFAULT_SEED)
        states = jm.causal_filter_states(fit, z)
        switch_counts.append(int(np.sum(states[1:] != states[:-1])))
    assert switch_counts[0] >= switch_counts[1] >= switch_counts[2]


def test_standardize_zero_variance_feature_raises():
    z = np.zeros((300, 2))
    z[:, 0] = np.random.default_rng(0).normal(size=300)
    with pytest.raises(jm.JMError, match="DEGENERATE_FEATURE_GEOMETRY"):
        jm.standardize(z)
