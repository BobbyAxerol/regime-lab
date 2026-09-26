"""Coverage for sd/ridge_contrast.py (guide SS5.5's frozen normalization)."""
from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.sd import ridge_contrast as rc


def test_per_origin_weights_sum_to_one_within_each_origin():
    origins = ["o1", "o1", "o1", "o2", "o2"]
    w = rc.per_origin_weights(origins)
    assert w[:3].sum() == pytest.approx(1.0)
    assert w[3:].sum() == pytest.approx(1.0)
    assert np.allclose(w[:3], 1 / 3)
    assert np.allclose(w[3:], 1 / 2)


def test_fit_weighted_ridge_matches_independent_closed_form():
    rng = np.random.default_rng(0)
    V = rng.normal(size=(40, 3))
    true_beta = np.array([1.5, -0.5, 0.2])
    y = V @ true_beta + rng.normal(scale=0.01, size=40)
    weights = np.ones(40)
    lam = 2.0
    fit = rc.fit_weighted_ridge(V, y, weights, lambda_reg=lam, n_train_origins=10)
    w_sqrt = np.sqrt(weights)
    vw, yw = V * w_sqrt[:, None], y * w_sqrt
    expected = np.linalg.solve(vw.T @ vw + lam * np.eye(3), vw.T @ yw)
    assert np.allclose(fit.beta, expected, atol=1e-10)


def test_fit_weighted_ridge_minimizes_objective_vs_perturbations():
    """Independently verify optimality: any small perturbation of beta must
    not lower the SAME objective the closed-form solve claims to minimize
    (guide SS5.5's own 'numerical fixture phai verify objective/coefficients/
    predictions' requirement)."""
    rng = np.random.default_rng(1)
    V = rng.normal(size=(30, 2))
    y = rng.normal(size=30)
    weights = rc.per_origin_weights(["a"] * 10 + ["b"] * 10 + ["c"] * 10)
    lam = 5.0
    fit = rc.fit_weighted_ridge(V, y, weights, lambda_reg=lam, n_train_origins=3)
    base = rc.weighted_objective_value(V, y, weights, fit.beta, lam)
    for _ in range(50):
        perturbed = fit.beta + rng.normal(scale=0.05, size=2)
        perturbed_obj = rc.weighted_objective_value(V, y, weights, perturbed, lam)
        assert perturbed_obj >= base - 1e-9


def test_predict_is_zero_for_zero_contrast_vector_no_intercept():
    V = np.array([[1.0, 2.0], [3.0, -1.0], [0.5, 0.5]])
    y = np.array([1.0, -2.0, 0.3])
    weights = np.ones(3)
    fit = rc.fit_weighted_ridge(V, y, weights, lambda_reg=1.0, n_train_origins=3)
    assert rc.predict(fit, np.zeros(2)) == pytest.approx(0.0, abs=1e-15)


def test_predict_rejects_dimension_mismatch():
    V = np.eye(2)
    fit = rc.fit_weighted_ridge(V, np.array([1.0, 2.0]), np.ones(2), lambda_reg=1.0, n_train_origins=2)
    with pytest.raises(rc.RidgeContrastError):
        rc.predict(fit, np.array([1.0, 2.0, 3.0]))


def test_higher_lambda_shrinks_beta_norm():
    rng = np.random.default_rng(3)
    V = rng.normal(size=(50, 4))
    y = rng.normal(size=50)
    weights = np.ones(50)
    fit_low = rc.fit_weighted_ridge(V, y, weights, lambda_reg=0.1, n_train_origins=10)
    fit_high = rc.fit_weighted_ridge(V, y, weights, lambda_reg=100.0, n_train_origins=10)
    assert np.linalg.norm(fit_high.beta) < np.linalg.norm(fit_low.beta)


def test_origin_weighting_prevents_large_origin_domination():
    """An origin with many candidate rows must not dominate the fit purely
    by row count -- construct one origin with 1 informative row and another
    with 20 near-duplicate rows pulling toward a different beta; with
    correct per-origin weighting each origin's PULL is comparable."""
    rng = np.random.default_rng(4)
    v_small_origin = np.array([[1.0, 0.0]])
    y_small_origin = np.array([5.0])
    v_big_origin = rng.normal(scale=0.01, size=(20, 2)) + np.array([[0.0, 1.0]])
    y_big_origin = np.zeros(20)
    V = np.vstack([v_small_origin, v_big_origin])
    y = np.concatenate([y_small_origin, y_big_origin])
    origins = ["small"] + ["big"] * 20
    weights = rc.per_origin_weights(origins)
    fit = rc.fit_weighted_ridge(V, y, weights, lambda_reg=0.01, n_train_origins=2)
    # the "small" origin's own dimension (index 0) should still pull
    # meaningfully toward 5.0, not be drowned out to ~0 by the 20 big rows
    assert fit.beta[0] > 1.0
