"""FP-05 selector_b: feature engineering, ridge, chronological walk-forward
OOF, decay-risk branching, eligibility/ranking -- on synthetic feature rows
(engine-free; the causal/numerical properties here don't need a real search)
plus the guide 8.4-mandated dormant-risk regression proving a naive
time-sorted LOO leaks future origins while walk_forward_oof's own guard
(fp.forward_ledger.training_view) does not.
"""
from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.fp import selector_b as sb
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS

SCHEMA = SCHEMAS["A-SC"]


# ---------------------------------------------------------------------------
# normalized_value / normalized_params
# ---------------------------------------------------------------------------

def test_normalized_value_numeric_hits_0_and_1_at_declared_bounds():
    spec = SCHEMA.specs["AP"]   # int 5-60
    assert sb.normalized_value(spec, 5) == pytest.approx(0.0)
    assert sb.normalized_value(spec, 60) == pytest.approx(1.0)
    assert sb.normalized_value(spec, 32.5) == pytest.approx(0.5, abs=0.01)


def test_normalized_value_fixed_is_always_zero():
    spec = SCHEMA.specs["src_col"]
    assert sb.normalized_value(spec, "close") == 0.0


def test_normalized_params_only_covers_active_informative_dims():
    params = {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
             "novolumedata": False, "src_col": "close"}
    out = sb.normalized_params(SCHEMA, params)
    assert set(out) == {"norm_coeff", "norm_AP", "norm_alpha.condition_threshold"}
    assert all(0.0 <= v <= 1.0 for v in out.values())


# ---------------------------------------------------------------------------
# ridge regression -- closed form, numpy only
# ---------------------------------------------------------------------------

def test_fit_ridge_recovers_a_known_linear_relationship_at_low_alpha():
    rng = np.random.default_rng(20260923)
    n = 200
    X = rng.normal(size=(n, len(sb.FEATURE_NAMES)))
    true_coef = np.array([0.02, -0.01, 0.0, 0.03, 0.0, 0.0, 0.0, 0.0, 0.01])
    y = X @ true_coef + 0.001 + rng.normal(scale=0.001, size=n)
    w = np.ones(n)
    model = sb.fit_ridge(X, y, w, alpha=1e-6)
    preds = sb.predict_ridge(model, X)
    residual = y - preds
    assert np.abs(residual).mean() < 0.002   # near-perfect recovery at ~no penalty


def test_fit_ridge_shrinks_coefficients_toward_zero_as_alpha_grows():
    rng = np.random.default_rng(1)
    n = 100
    X = rng.normal(size=(n, len(sb.FEATURE_NAMES)))
    y = X[:, 0] * 0.05 + rng.normal(scale=0.01, size=n)
    w = np.ones(n)
    low = sb.fit_ridge(X, y, w, alpha=0.01)
    high = sb.fit_ridge(X, y, w, alpha=1000.0)
    assert np.linalg.norm(high["coef"]) < np.linalg.norm(low["coef"])


def test_fit_ridge_refuses_empty_training_set():
    with pytest.raises(sb.SelectorBError, match="no training rows"):
        sb.fit_ridge(np.zeros((0, 3)), np.zeros(0), np.zeros(0), alpha=1.0)


def test_predict_ridge_on_the_mean_point_returns_the_intercept():
    X = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0]])
    y = np.array([1.0, 2.0, 3.0])
    w = np.ones(3)
    model = sb.fit_ridge(X, y, w, alpha=1.0)
    mean_point = np.array([model["feature_mean"]])
    pred = sb.predict_ridge(model, mean_point)
    assert pred[0] == pytest.approx(model["intercept"])


# ---------------------------------------------------------------------------
# build_feature_matrix -- exclusion discipline
# ---------------------------------------------------------------------------

def _row(record_id, origin_cutoff, *, label=0.0001, **overrides):
    base = {name: 0.5 for name in sb.FEATURE_NAMES}
    base.update(overrides)
    base.update({"record_id": record_id, "origin_cutoff": origin_cutoff, "label": label})
    return base


def test_build_feature_matrix_excludes_none_label_with_a_reason():
    rows = [_row("A:R00", "2022-01-01", label=None), _row("A:R01", "2022-01-01")]
    X, y, w, names, kept, excluded = sb.build_feature_matrix(rows)
    assert len(kept) == 1 and kept[0]["record_id"] == "A:R01"
    assert len(excluded) == 1 and excluded[0]["record_id"] == "A:R00"
    assert "label is None" in excluded[0]["reason"]


def test_build_feature_matrix_excludes_none_feature_with_a_reason():
    rows = [_row("A:R00", "2022-01-01", is_daily_sharpe=None)]
    X, y, w, names, kept, excluded = sb.build_feature_matrix(rows)
    assert kept == []
    assert "is_daily_sharpe" in excluded[0]["reason"]


def test_build_feature_matrix_weights_equal_per_origin():
    rows = ([_row("A:R00", "2022-01-01")]
           + [_row(f"B:R{i:02d}", "2022-04-01") for i in range(5)])
    X, y, w, names, kept, excluded = sb.build_feature_matrix(rows)
    assert not excluded
    a_weight = w[[r["record_id"] for r in kept].index("A:R00")]
    b_weight_total = sum(w[i] for i, r in enumerate(kept) if r["origin_cutoff"] == "2022-04-01")
    assert a_weight == pytest.approx(b_weight_total)


# ---------------------------------------------------------------------------
# FP04-T01-style dormant-risk regression, applied to FP-05's own model:
# a naive time-sorted LOO leaks future origins into training; walk_forward_oof
# (via fp.forward_ledger.training_view) does not. Guide 8.4's own required
# regression test before opening any statistical fit.
# ---------------------------------------------------------------------------

def _synthetic_archive(n_origins: int = 12, *, n_per_origin: int = 3, horizon_days: int = 28):
    """Realistic-shaped rows: origin_cutoff/origin_time/label_available_at
    computed the SAME way fp.forward_ledger.ledger_record does, so
    training_view's tz/availability logic exercises for real."""
    import pandas as pd

    rows = []
    base = pd.Timestamp("2021-01-01", tz="UTC")
    for i in range(n_origins):
        origin_ts = base + pd.Timedelta(days=91 * i)
        origin_cutoff = origin_ts.strftime("%Y-%m-%d")
        label_available_at = (origin_ts + pd.Timedelta(days=horizon_days)).isoformat()
        for j in range(n_per_origin):
            rows.append(_row(f"{origin_cutoff}:R{j:02d}", origin_cutoff,
                             label=0.0001 * (i + j),
                             **{"norm_AP": 0.1 * j}) | {
                "origin_time": origin_ts.isoformat(), "label_available_at": label_available_at,
            })
    return rows


def test_naive_loo_leaks_a_future_origin_that_training_view_correctly_blocks():
    from crypto_regime_lab.fp.chronology import naive_time_sorted_loo_train
    from crypto_regime_lab.fp.forward_ledger import training_view

    rows = _synthetic_archive(n_origins=12, n_per_origin=1)
    # validate at the 6th origin (index 5): held out by naive LOO
    held_position = 5
    held_row = rows[held_position]
    naive_train = naive_time_sorted_loo_train(
        [{**r, "origin_time": r["origin_time"]} for r in rows], held=held_position)
    # a LATER origin (index 6, strictly after the held-out one) is present in
    # the naive LOO training set -- its label could not have existed yet
    later_origin_row = rows[6]
    assert later_origin_row in naive_train, "test setup: naive LOO should include a later origin"

    guarded = training_view(rows, decision_time=held_row["origin_time"])
    guarded_ids = {r["record_id"] for r in guarded["usable"]}
    assert later_origin_row["record_id"] not in guarded_ids, (
        "training_view must exclude an origin whose label could not have been "
        "available at the held-out origin's own decision time")
    # and the guard is not simply excluding EVERYTHING -- earlier origins remain usable
    earlier_origin_row = rows[0]
    assert earlier_origin_row["record_id"] in guarded_ids


def test_walk_forward_oof_never_trains_on_a_later_origins_own_record():
    rows = _synthetic_archive(n_origins=12, n_per_origin=2)
    result = sb.walk_forward_oof(rows, min_train_origins=4, alpha_grid=(1.0,))
    assert result["insufficient"] is False
    assert result["n_validation_origins"] == 8   # guide 8.7's own OOF floor, exactly
    validated = set(result["validation_origins"])
    all_origins = sorted({r["origin_cutoff"] for r in rows})
    # every validation origin must be from position 4 onward (0-indexed)
    for origin in validated:
        assert all_origins.index(origin) >= 4


def test_walk_forward_oof_reports_insufficient_below_min_train_plus_one_origins():
    rows = _synthetic_archive(n_origins=4, n_per_origin=1)
    result = sb.walk_forward_oof(rows, min_train_origins=4, alpha_grid=(1.0,))
    assert result["insufficient"] is True
    assert "only 4 distinct origins" in result["reason"]


# ---------------------------------------------------------------------------
# select_alpha
# ---------------------------------------------------------------------------

def test_select_alpha_picks_the_lowest_aggregate_oof_mse():
    oof = {"insufficient": False, "by_alpha": {
        "0.1": {"n": 10, "weighted_mse": 0.002},
        "1.0": {"n": 10, "weighted_mse": 0.0005},
        "10.0": {"n": 10, "weighted_mse": 0.003},
    }}
    result = sb.select_alpha(oof, alpha_grid=(0.1, 1.0, 10.0))
    assert result["selected_alpha"] == 1.0


def test_select_alpha_reports_the_insufficient_reason_verbatim():
    oof = {"insufficient": True, "reason": "only 4 distinct origins, need at least 5"}
    result = sb.select_alpha(oof)
    assert result["selected_alpha"] is None
    assert "only 4 distinct origins" in result["reason"]


# ---------------------------------------------------------------------------
# decay_risk_branch / decay_risk_score
# ---------------------------------------------------------------------------

def test_decay_risk_branch_falls_back_to_stock_below_fit_floor():
    out = sb.decay_risk_branch(n_oof_origins=3, n_fit_origins=6)
    assert out["branch"] == "FALLBACK_STOCK_INCUMBENT"


def test_decay_risk_branch_uses_mean_decay_between_fit_and_tail_floors():
    out = sb.decay_risk_branch(n_oof_origins=8, n_fit_origins=12)
    assert out["branch"] == "MEAN_DECAY"
    assert "TAIL_ESTIMATE_UNSUPPORTED" in out["reason"]


def test_decay_risk_branch_uses_tail_quantile_at_or_above_20_oof_origins():
    out = sb.decay_risk_branch(n_oof_origins=20, n_fit_origins=25)
    assert out["branch"] == "TAIL_QUANTILE"
    assert out["reason"] is None


def test_decay_risk_score_mean_vs_tail_quantile_differ_on_a_skewed_residual_set():
    residuals = [-0.001, -0.0005, 0.0, 0.0002, 0.0005, 0.05]   # one big outlier
    mean_score = sb.decay_risk_score(is_mean=0.001, predicted_forward=0.0008,
                                     oof_residuals=residuals, branch="MEAN_DECAY")
    tail_score = sb.decay_risk_score(is_mean=0.001, predicted_forward=0.0008,
                                     oof_residuals=residuals, branch="TAIL_QUANTILE", quantile=0.8)
    assert mean_score["score"] != tail_score["score"]
    assert mean_score["branch"] == "MEAN_DECAY" and tail_score["branch"] == "TAIL_QUANTILE"


def test_decay_risk_score_stock_fallback_branch_has_no_score():
    out = sb.decay_risk_score(is_mean=0.001, predicted_forward=0.0008, oof_residuals=[0.0],
                              branch="FALLBACK_STOCK_INCUMBENT")
    assert out["score"] is None


# ---------------------------------------------------------------------------
# eligible_candidates / rank_and_select
# ---------------------------------------------------------------------------

def _scored(record_id, *, utility, support, decay_risk=0.0001):
    return {"record_id": record_id, "predicted_forward_utility": utility,
           "region_support_within_origin": support, "decay_risk_score": decay_risk}


def test_eligible_candidates_filters_below_utility_floor():
    rows = [_scored("A", utility=1e-06, support=5), _scored("B", utility=0.001, support=5)]
    out = sb.eligible_candidates(rows, utility_floor=6.4e-05, support_floor=2)
    by_id = {r["record_id"]: r for r in out}
    assert by_id["A"]["eligible"] is False and "predicted utility" in by_id["A"]["ineligibility_reasons"][0]
    assert by_id["B"]["eligible"] is True


def test_eligible_candidates_filters_below_support_floor():
    rows = [_scored("A", utility=0.001, support=1)]
    out = sb.eligible_candidates(rows, utility_floor=6.4e-05, support_floor=2)
    assert out[0]["eligible"] is False
    assert "support" in out[0]["ineligibility_reasons"][0]


def test_rank_and_select_never_returns_an_ineligible_row():
    rows = sb.eligible_candidates(
        [_scored("bad", utility=1e-08, support=5), _scored("good", utility=0.001, support=5)],
        utility_floor=6.4e-05, support_floor=2)
    winner = sb.rank_and_select(rows)
    assert winner["record_id"] == "good"


def test_rank_and_select_maximises_utility_minus_decay_risk():
    rows = sb.eligible_candidates([
        _scored("high_utility_high_risk", utility=0.002, support=5, decay_risk=0.0019),
        _scored("modest_utility_low_risk", utility=0.001, support=5, decay_risk=0.0001),
    ], utility_floor=6.4e-05, support_floor=2)
    winner = sb.rank_and_select(rows)
    assert winner["record_id"] == "modest_utility_low_risk"   # 0.001-0.0001=0.0009 > 0.002-0.0019=0.0001


def test_rank_and_select_returns_none_when_nothing_is_eligible():
    rows = sb.eligible_candidates([_scored("bad", utility=0.0, support=0)],
                                  utility_floor=6.4e-05, support_floor=2)
    assert sb.rank_and_select(rows) is None
