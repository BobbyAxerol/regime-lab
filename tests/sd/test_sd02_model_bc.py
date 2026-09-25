"""Coverage for sd/model_bc.py (guide SS5.5-5.6, S2-T04-RELATIVE-ALGEBRA-adjacent)."""
from __future__ import annotations

import random

import numpy as np
import pytest

from crypto_regime_lab.sd import model_bc as mbc


def _synthetic_train_rows(n_origins: int, *, candidates_per_origin: int = 16, seed: int = 0):
    """Deterministic synthetic archive: each origin has one anchor (y=0)
    plus (candidates_per_origin - 1) other candidates with a real linear
    relationship y = 0.6*f1 - 0.3*f2 + noise in contrast-feature space, so
    a fitted ridge should recover a non-trivial beta and beat a
    zero-prediction baseline out of sample."""
    rng = random.Random(seed)
    rows = []
    anchor_features = {"f1": 0.0, "f2": 0.0, "f3": 0.0}
    for o in range(n_origins):
        origin_id = f"o{o:03d}"
        rows.append({"origin_id": origin_id, "candidate_features": dict(anchor_features),
                    "anchor_features": dict(anchor_features), "y": 0.0, "is_anchor": True})
        for c in range(candidates_per_origin - 1):
            f1 = rng.gauss(0, 1)
            f2 = rng.gauss(0, 1)
            f3 = rng.gauss(0, 1)
            y = 0.6 * f1 - 0.3 * f2 + rng.gauss(0, 0.02)
            rows.append({"origin_id": origin_id,
                        "candidate_features": {"f1": f1, "f2": f2, "f3": f3},
                        "anchor_features": dict(anchor_features), "y": y, "is_anchor": False})
    return rows


def test_fit_model_b_requires_min_origin_floor():
    rows = _synthetic_train_rows(n_origins=11)
    with pytest.raises(mbc.ModelError):
        mbc.fit_model_b(rows)
    rows_ok = _synthetic_train_rows(n_origins=12)
    fit = mbc.fit_model_b(rows_ok)
    assert fit.n_train_origins == 12


def test_predict_b_is_exactly_zero_at_the_anchor():
    rows = _synthetic_train_rows(n_origins=12)
    fit = mbc.fit_model_b(rows)
    anchor_features = rows[0]["anchor_features"]
    assert mbc.predict_b(fit, anchor_features, anchor_features) == pytest.approx(0.0, abs=1e-12)


def test_model_b_recovers_a_real_linear_relationship_out_of_sample():
    train_rows = _synthetic_train_rows(n_origins=30, seed=1)
    test_rows = _synthetic_train_rows(n_origins=10, seed=99)
    fit = mbc.fit_model_b(train_rows, lambda_global=1.0)
    preds = [mbc.predict_b(fit, r["candidate_features"], r["anchor_features"]) for r in test_rows]
    actual = [r["y"] for r in test_rows]
    mse_model = float(np.mean([(p - a) ** 2 for p, a in zip(preds, actual)]))
    mse_zero_baseline = float(np.mean([a ** 2 for a in actual]))
    assert mse_model < mse_zero_baseline


def test_model_c_state_support_low_falls_back_to_b_with_zero_correction():
    rows = _synthetic_train_rows(n_origins=12)
    fit_b = mbc.fit_model_b(rows)
    # only 2 distinct origins tagged state=1 -- below MIN_STATE_TRAIN_ORIGINS=3
    for i, row in enumerate(rows):
        row["state"] = 1 if row["origin_id"] in ("o000", "o001") else 0
    fit_c = mbc.fit_model_c(fit_b, rows)
    assert fit_c.state_support_counts[1] == 2
    assert 1 not in fit_c.state_ridge_fits
    result = mbc.predict_c(fit_c, rows[3]["candidate_features"], rows[3]["anchor_features"], state=1)
    assert result["label"] == "GLOBAL_FALLBACK"
    assert result["reason"] == "STATE_SUPPORT_LOW"
    assert result["correction"] == 0.0
    assert result["y_hat"] == pytest.approx(result["y_hat_b"])


def test_model_c_unknown_state_falls_back_distinct_reason():
    rows = _synthetic_train_rows(n_origins=12)
    fit_b = mbc.fit_model_b(rows)
    for row in rows:
        row["state"] = 0
    fit_c = mbc.fit_model_c(fit_b, rows)
    result = mbc.predict_c(fit_c, rows[3]["candidate_features"], rows[3]["anchor_features"], state=99)
    assert result["label"] == "GLOBAL_FALLBACK"
    assert result["reason"] == "UNKNOWN_STATE"


def test_model_c_applies_correction_when_support_clears_floor():
    rows = _synthetic_train_rows(n_origins=20, seed=3)
    fit_b = mbc.fit_model_b(rows)
    # split origins into two states with >=3 each, and make state=1's
    # residual have a REAL, learnable extra pattern (y offset by f3)
    origin_ids = sorted(set(r["origin_id"] for r in rows))
    state_of_origin = {oid: (1 if i % 2 == 0 else 0) for i, oid in enumerate(origin_ids)}
    for row in rows:
        row["state"] = state_of_origin[row["origin_id"]]
        if row["state"] == 1 and not row["is_anchor"]:
            row["y"] = row["y"] + 0.9 * row["candidate_features"]["f3"]
    fit_c = mbc.fit_model_c(fit_b, rows, lambda_state=1.0)
    assert 1 in fit_c.state_ridge_fits and 0 in fit_c.state_ridge_fits
    sample = next(r for r in rows if r["state"] == 1 and not r["is_anchor"])
    result = mbc.predict_c(fit_c, sample["candidate_features"], sample["anchor_features"], state=1)
    assert result["label"] == "CONTEXT_CONDITIONED"
    # C's prediction should be closer to the true (state-adjusted) y than B alone, on average
    state1_rows = [r for r in rows if r["state"] == 1 and not r["is_anchor"]][:20]
    b_errs, c_errs = [], []
    for r in state1_rows:
        b_pred = mbc.predict_b(fit_b, r["candidate_features"], r["anchor_features"])
        c_res = mbc.predict_c(fit_c, r["candidate_features"], r["anchor_features"], state=1)
        b_errs.append((b_pred - r["y"]) ** 2)
        c_errs.append((c_res["y_hat"] - r["y"]) ** 2)
    assert float(np.mean(c_errs)) < float(np.mean(b_errs))


def test_predict_c_callable_regardless_of_which_state_b_would_have_selected():
    """guide SS5.6: C must be callable at every model-ready fold even when B
    fell back to the anchor -- this module has no dependency on any prior B
    SELECTION outcome, only on the fitted B prediction function."""
    rows = _synthetic_train_rows(n_origins=15, seed=11)
    fit_b = mbc.fit_model_b(rows)
    for i, row in enumerate(rows):
        row["state"] = i % 2
    fit_c = mbc.fit_model_c(fit_b, rows)
    # simulate "B fell back to the anchor" by scoring the anchor itself through C
    anchor_row = next(r for r in rows if r["is_anchor"])
    result = mbc.predict_c(fit_c, anchor_row["candidate_features"], anchor_row["anchor_features"], state=0)
    assert result is not None
    assert result["label"] in ("CONTEXT_CONDITIONED", "GLOBAL_FALLBACK")
