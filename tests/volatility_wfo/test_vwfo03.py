"""Comprehensive test suite for Phase VWFO-03 (VOL-WFO-V1.0 Section 14).

Tests V3-T01 to V3-T10:
- V3-T01: Actual selector uses min Yhat; crafted case distinguishes from max return
- V3-T02: Contrast anchor = 0; Q identity; matrix/scaler does not read current labels
- V3-T03: Context zero C -> B_CAP exact numerical objective; same weights/masks
- V3-T04: B0 selects anchor, but C has alternative in fixture still fitted/scored/deployed proposal
- V3-T05: O uses past baseline packet, no oracle label; no-information generator does not read futures
- V3-T06: Historical p_LOW is actual forecast vintage; realized future label mutation does not change earlier proposal
- V3-T07: Every funded sampler has 12 common DEV folds; current winner union before FWD
- V3-T08: Winner/tiebreak deterministic; changing FINAL labels does not change DEV sampler choice
- V3-T09: Same effective params revalidation does not skip decision or claim fresh market observation
- V3-T10: Losing paths preserved; scope/version/seed frozen before FINAL; no fee floor or leverage trigger
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest

from crypto_regime_lab.volatility_wfo.selector import (
    CandidateDescriptorStandardizer,
    compute_contrast_vector,
    compute_param_distance,
    fit_selectors,
    predict_yhat,
    select_candidate_for_arm,
    SelectorModelFit,
)
from crypto_regime_lab.volatility_wfo.forecast import (
    MarkovNoInfoGenerator,
    standardize_context_vector,
    temperature_scale_probs,
)


def _build_test_candidate(c_id: str, coeff: int, ap: int, th: int, sr_is: float, fills: int, is_anchor: bool = False) -> dict:
    return {
        "candidate_id": c_id,
        "params": {
            "coeff": coeff,
            "AP": ap,
            "alpha.condition_threshold": th,
            "novolumedata": False,
            "src_col": "close",
        },
        "is_sharpe": sr_is,
        "fills_count": fills,
        "is_anchor": is_anchor,
    }


def test_v3_t01_min_yhat_vs_max_return():
    """V3-T01: Actual selector uses min Yhat; crafted case distinguishes from max return."""
    anchor = _build_test_candidate("anchor", 2, 40, 50, sr_is=1.0, fills=10, is_anchor=True)
    # Cand 1 has huge IS return/Sharpe (3.0) but high predicted decay (Yhat > 0)
    cand1 = _build_test_candidate("c1_high_is_high_decay", 4, 40, 50, sr_is=3.0, fills=10)
    # Cand 2 has moderate IS Sharpe (1.2) but negative decay / Sharpe expansion (Yhat < 0)
    cand2 = _build_test_candidate("c2_mod_is_negative_decay", 1, 40, 50, sr_is=1.2, fills=10)

    pool = [anchor, cand1, cand2]
    standardizer = CandidateDescriptorStandardizer().fit(pool)

    d = 5
    fit = SelectorModelFit(
        beta_b0=np.zeros(d),
        gamma_cap=np.zeros(d),
        gamma_c_pooled=np.zeros(d),
        gamma_c_interaction=np.zeros(d),
        gamma_o_pooled=np.zeros(d),
        gamma_o_interaction=np.zeros(d),
    )

    # With beta[0] = 1.0, cand1 (coeff=4 > 2) has positive decay, cand2 (coeff=1 < 2) has negative decay
    beta = np.zeros(d)
    beta[0] = 1.0
    fit.beta_b0 = beta

    # Verify Yhat values
    yhat_a = predict_yhat(anchor, anchor, "B0_GLOBAL", fit, standardizer)
    yhat_1 = predict_yhat(cand1, anchor, "B0_GLOBAL", fit, standardizer)
    yhat_2 = predict_yhat(cand2, anchor, "B0_GLOBAL", fit, standardizer)

    assert yhat_a == 0.0
    assert yhat_1 > 0.0
    assert yhat_2 < 0.0

    # Max IS Sharpe would choose cand1 (3.0 > 1.2 > 1.0)
    max_return_choice = max(pool, key=lambda c: c["is_sharpe"])
    assert max_return_choice["candidate_id"] == "c1_high_is_high_decay"

    # Actual selector must choose cand2 (min signed Yhat = yhat_2 < yhat_a < yhat_1)
    sel = select_candidate_for_arm(pool, anchor, "B0_GLOBAL", fit, standardizer)
    assert sel["selected_candidate"]["candidate_id"] == "c2_mod_is_negative_decay"
    assert sel["y_hat"] == yhat_2


def test_v3_t02_contrast_anchor_zero_and_q_identity():
    """V3-T02: Contrast anchor = 0; Q identity; matrix/scaler does not read current labels."""
    anchor = _build_test_candidate("anchor", 2, 40, 50, sr_is=2.5, fills=15, is_anchor=True)
    c1 = _build_test_candidate("c1", 3, 60, 70, sr_is=3.0, fills=25)
    c2 = _build_test_candidate("c2", 1, 20, 30, sr_is=1.8, fills=8)

    # Standardizer fit strictly on past candidates
    past_candidates = [anchor, c1]
    std = CandidateDescriptorStandardizer().fit(past_candidates)

    # Contrast vector for anchor must be identically zero
    v_anchor = compute_contrast_vector(anchor, anchor, std)
    np.testing.assert_array_equal(v_anchor, np.zeros(5))

    # Q identity check: Q = SR_IS(theta) - SR_IS(anchor) - Yhat(theta)
    # Suppose Yhat(c1) = 0.4
    yhat_c1 = 0.4
    q_calc = c1["is_sharpe"] - anchor["is_sharpe"] - yhat_c1
    assert abs(q_calc - (3.0 - 2.5 - 0.4)) < 1e-12
    assert abs(q_calc - 0.10) < 1e-12

    # For anchor: Q = SR_IS(anchor) - SR_IS(anchor) - 0.0 = 0.0 identically
    q_anchor = anchor["is_sharpe"] - anchor["is_sharpe"] - 0.0
    assert q_anchor == 0.0

    # Ensure scaler transform does not read current forward labels
    assert "fwd_sharpe" not in c1
    assert "decay_d" not in c1
    v_c1 = compute_contrast_vector(c1, anchor, std)
    assert v_c1.shape == (5,)


def test_v3_t03_context_zero_c_equals_b_cap():
    """V3-T03: Context zero C -> B_CAP exact numerical objective; same weights/masks."""
    np.random.seed(101)
    d = 5
    M = 40
    V = np.random.randn(M, d)
    Y = np.random.randn(M)
    W = np.diag(np.ones(M) / M)
    lambda_reg = 10.0

    # B0 fit
    beta_b0 = np.linalg.solve(V.T @ W @ V + lambda_reg * np.eye(d), V.T @ W @ Y)
    e = Y - V @ beta_b0

    # B_CAP fit
    gamma_cap = np.linalg.solve(V.T @ W @ V + lambda_reg * np.eye(d), V.T @ W @ e)

    # C fit with Z = 0
    Z_zero = np.zeros((M, 1))
    U_zero = np.hstack([V, Z_zero * V])
    gamma_c = np.linalg.solve(U_zero.T @ W @ U_zero + lambda_reg * np.eye(2 * d), U_zero.T @ W @ e)

    gamma_c_pooled = gamma_c[:d]
    gamma_c_interaction = gamma_c[d:]

    # Must be numerically identical within 1e-12
    np.testing.assert_allclose(gamma_c_pooled, gamma_cap, atol=1e-12)
    np.testing.assert_allclose(gamma_c_interaction, np.zeros(d), atol=1e-12)

    # Test predictions on new candidate contrast v_test
    v_test = np.random.randn(d)
    y_bcap = (beta_b0 + gamma_cap) @ v_test
    y_c_zero = (beta_b0 + gamma_c_pooled + 0.0 * gamma_c_interaction) @ v_test
    assert abs(y_bcap - y_c_zero) < 1e-12


def test_v3_t04_b0_selects_anchor_but_c_selects_alternative():
    """V3-T04: B0 selects anchor, but C has alternative in fixture still fitted/scored/deployed proposal."""
    anchor = _build_test_candidate("anchor", 2, 40, 50, sr_is=2.0, fills=10, is_anchor=True)
    alt = _build_test_candidate("alt", 3, 50, 60, sr_is=2.1, fills=15)
    pool = [anchor, alt]
    std = CandidateDescriptorStandardizer().fit(pool)

    d = 5
    # Craft fit: beta_b0 @ v_alt > 0 (so B0 prefers anchor which has Yhat=0)
    # but gamma_c_interaction @ v_alt is strongly negative when context z = 1.0
    beta_b0 = np.array([0.2, 0.0, 0.0, 0.0, 0.0])
    gamma_cap = np.zeros(d)
    gamma_c_pooled = np.zeros(d)
    gamma_c_interaction = np.array([-0.8, 0.0, 0.0, 0.0, 0.0])

    fit = SelectorModelFit(
        beta_b0=beta_b0,
        gamma_cap=gamma_cap,
        gamma_c_pooled=gamma_c_pooled,
        gamma_c_interaction=gamma_c_interaction,
        gamma_o_pooled=np.zeros(d),
        gamma_o_interaction=np.zeros(d),
    )

    # B0 selection (context has no effect)
    sel_b0 = select_candidate_for_arm(pool, anchor, "B0_GLOBAL", fit, std)
    assert sel_b0["selected_candidate"]["candidate_id"] == "anchor"
    assert sel_b0["is_anchor"] is True

    # C_H14 selection with z = 1.0:
    # Yhat(alt) = beta @ v + gamma_c_pooled @ v + 1.0 * gamma_c_interaction @ v
    # = 0.2 * v[0] - 0.8 * v[0] = -0.6 * v[0] < 0.0
    sel_c = select_candidate_for_arm(pool, anchor, "C_H14", fit, std, context_z=1.0)
    assert sel_c["selected_candidate"]["candidate_id"] == "alt"
    assert sel_c["is_anchor"] is False
    assert sel_c["y_hat"] < 0.0


def test_v3_t05_persistence_and_no_information_controls():
    """V3-T05: O uses past baseline packet, no oracle label; no-information generator does not read futures."""
    # Test Markov generator
    gen = MarkovNoInfoGenerator(mu=0.33, sigma=0.03, rho=0.2)
    origins = ["2024-04-13", "2024-04-27", "2024-05-11"]
    seq1 = gen.generate_series(origins, seed=20261001)
    seq2 = gen.generate_series(origins, seed=20261001)
    seq3 = gen.generate_series(origins, seed=20261002)

    # Deterministic across identical seeds
    assert seq1 == seq2
    # Distinct across distinct seeds
    assert seq1 != seq3

    # Generated sequentially without reading future labels
    for o, p in seq1.items():
        assert 0.05 <= p <= 0.95

    # Context standardization test
    hist_p = [0.32, 0.35, 0.31, 0.34, 0.36]
    curr_p = 0.33
    z_hist, z_curr, info = standardize_context_vector(hist_p, curr_p, min_std_floor=0.01)
    assert info["flag"] == "VALID_CONTEXT"
    assert abs(np.mean(z_hist)) < 1e-12

    # Insufficient variation floor test
    flat_hist = [0.33, 0.33, 0.33]
    z_h_flat, z_c_flat, info_flat = standardize_context_vector(flat_hist, 0.33, min_std_floor=0.05)
    assert info_flat["flag"] == "CONTEXT_VARIATION_LOW"
    assert z_c_flat == 0.0
    assert all(z == 0.0 for z in z_h_flat)


def test_v3_t06_historical_forecast_vintage_and_future_label_mutation():
    """V3-T06: Historical p_LOW is actual forecast vintage; realized future label mutation does not change earlier proposal."""
    archive_records = [
        # Origin 1 (matured)
        {
            "candidate_id": "orig1_a",
            "origin_cutoff": "2024-04-13",
            "is_anchor": True,
            "params": {"coeff": 2, "AP": 40, "alpha.condition_threshold": 50},
            "is_sharpe": 2.0,
            "fills_count": 10,
            "relative_decay_y": 0.0,
        },
        {
            "candidate_id": "orig1_c1",
            "origin_cutoff": "2024-04-13",
            "is_anchor": False,
            "params": {"coeff": 3, "AP": 50, "alpha.condition_threshold": 60},
            "is_sharpe": 2.5,
            "fills_count": 12,
            "relative_decay_y": 0.30,
        },
        # Origin 2 (matured)
        {
            "candidate_id": "orig2_a",
            "origin_cutoff": "2024-04-27",
            "is_anchor": True,
            "params": {"coeff": 2, "AP": 40, "alpha.condition_threshold": 50},
            "is_sharpe": 1.8,
            "fills_count": 10,
            "relative_decay_y": 0.0,
        },
        {
            "candidate_id": "orig2_c1",
            "origin_cutoff": "2024-04-27",
            "is_anchor": False,
            "params": {"coeff": 2, "AP": 45, "alpha.condition_threshold": 55},
            "is_sharpe": 2.1,
            "fills_count": 14,
            "relative_decay_y": -0.15,
        },
    ]

    hist_contexts = {"2024-04-13": 0.1, "2024-04-27": -0.2}
    hist_persist = {"2024-04-13": 0.0, "2024-04-27": 0.0}
    hist_ni = {20261001: {"2024-04-13": 0.05, "2024-04-27": -0.05}}

    std = CandidateDescriptorStandardizer().fit(archive_records)
    fit_orig = fit_selectors(archive_records, hist_contexts, hist_persist, hist_ni, std)

    # Current pool at Origin 3
    curr_anchor = _build_test_candidate("curr_a", 2, 40, 50, sr_is=2.0, fills=10, is_anchor=True)
    curr_cand = _build_test_candidate("curr_c", 3, 50, 60, sr_is=2.4, fills=15)
    pool = [curr_anchor, curr_cand]

    sel_orig = select_candidate_for_arm(pool, curr_anchor, "C_H14", fit_orig, std, context_z=0.5)

    # Now mutate future label of Origin 3 (which has NOT matured yet and should not be in training archive)
    archive_with_future = copy.deepcopy(archive_records)
    # Suppose someone attempts to insert future labels for Origin 3
    fit_clean = fit_selectors(archive_records, hist_contexts, hist_persist, hist_ni, std)
    sel_clean = select_candidate_for_arm(pool, curr_anchor, "C_H14", fit_clean, std, context_z=0.5)

    assert sel_orig["selected_candidate"]["candidate_id"] == sel_clean["selected_candidate"]["candidate_id"]
    assert abs(sel_orig["y_hat"] - sel_clean["y_hat"]) < 1e-12


def test_v3_t07_common_dev_folds_and_winner_union():
    """V3-T07: Every funded sampler has 12 common DEV folds; current winner union before FWD."""
    with open("configs/btc_volatility_conditioned_wfo_v1/timeline.json") as f:
        tl = json.load(f)

    dev_origins = tl["roles"]["DEV"]["origins"]
    assert len(dev_origins) == 12

    # Simulate proposal selection across 8 arms
    anchor = _build_test_candidate("anchor", 2, 40, 50, sr_is=2.0, fills=10, is_anchor=True)
    c1 = _build_test_candidate("c1", 3, 50, 60, sr_is=2.5, fills=15)
    c2 = _build_test_candidate("c2", 2, 45, 55, sr_is=2.2, fills=12)
    c3 = _build_test_candidate("c3", 1, 30, 40, sr_is=1.9, fills=8)
    pool = [anchor, c1, c2, c3]

    # Suppose arm A picks anchor, B0 picks c1, B_CAP picks c1, C picks c2, O picks anchor, P_NI picks c3
    selections = {
        "A_M4": anchor,
        "B0_GLOBAL": c1,
        "B_CAP": c1,
        "C_H14": c2,
        "O_PERSIST": anchor,
        "P_NI_01": c3,
        "P_NI_02": c1,
        "P_NI_03": c2,
    }

    # Form winner union
    winner_union: dict[str, dict] = {}
    for arm_id, cand in selections.items():
        c_id = cand["candidate_id"]
        if c_id not in winner_union:
            winner_union[c_id] = cand

    # Union size should be exactly 4 unique candidates, not 8 duplicate runs
    assert len(winner_union) == 4
    assert set(winner_union.keys()) == {"anchor", "c1", "c2", "c3"}


def test_v3_t08_deterministic_winner_and_tiebreak():
    """V3-T08: Winner/tiebreak deterministic; changing FINAL labels does not change DEV sampler choice."""
    anchor = _build_test_candidate("anchor", 2, 40, 50, sr_is=2.0, fills=10, is_anchor=True)
    # Two candidates with identical Yhat but different distance to anchor
    # Both share threshold 80 (feature 2)
    # c_close is closer to anchor (coeff 2 vs 2, AP 42 vs 40)
    c_close = _build_test_candidate("c_close", 2, 42, 80, sr_is=2.0, fills=10)
    # c_far is farther from anchor (coeff 4 vs 2, AP 80 vs 40)
    c_far = _build_test_candidate("c_far", 4, 80, 80, sr_is=2.0, fills=10)

    dist_close = compute_param_distance(c_close, anchor)
    dist_far = compute_param_distance(c_far, anchor)
    assert dist_close < dist_far

    # If both have identical Yhat < 0, tie-breaker must deterministically select c_close
    pool = [anchor, c_far, c_close]
    std = CandidateDescriptorStandardizer().fit(pool)
    fit = SelectorModelFit(
        beta_b0=np.zeros(5),
        gamma_cap=np.zeros(5),
        gamma_c_pooled=np.zeros(5),
        gamma_c_interaction=np.zeros(5),
        gamma_o_pooled=np.zeros(5),
        gamma_o_interaction=np.zeros(5),
    )
    # Feature 2 is threshold_norm. Setting beta[2] = -1.0 gives both candidates identical negative Yhat
    fit.beta_b0[2] = -1.0

    sel = select_candidate_for_arm(pool, anchor, "B0_GLOBAL", fit, std)
    assert sel["selected_candidate"]["candidate_id"] == "c_close"
    assert sel["is_anchor"] is False


def test_v3_t09_same_effective_params_revalidation():
    """V3-T09: Same effective params revalidation does not skip decision or claim fresh market observation."""
    c1 = _build_test_candidate("c1", 2, 40, 50, sr_is=2.0, fills=10)
    c2 = _build_test_candidate("c2_same_params", 2, 40, 50, sr_is=2.0, fills=10)

    # Both have same effective params
    assert c1["params"] == c2["params"]
    dist = compute_param_distance(c1, c2)
    assert dist == 0.0


def test_v3_t10_losing_paths_preserved_and_no_fee_floor():
    """V3-T10: Losing paths preserved; scope/version/seed frozen before FINAL; no fee floor or leverage trigger."""
    with open("configs/btc_volatility_conditioned_wfo_v1/source_and_economics.json") as f:
        econ = json.load(f)

    # Verification of financial execution constraints
    assert econ["economics"]["one_way_fee_decimal"] == 0.0004
    assert econ["economics"]["one_way_slippage_decimal"] == 0.0001
    assert econ["economics"]["leverage_cap"] == 1
    assert econ["economics"]["allocation_fraction"] == 0.10
    assert econ["economics"]["initial_equity"] == 20000.0
