"""Coverage for sd/contrast_features.py (guide SS5.5)."""
from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.selector.alpha_schemas import A_SC
from crypto_regime_lab.sd import contrast_features as cf


ANCHOR_PARAMS = {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
                 "novolumedata": False, "src_col": "close"}
CAND_PARAMS = {"coeff": 6, "AP": 32, "alpha.condition_threshold": 80,
              "novolumedata": False, "src_col": "close"}


def test_raw_feature_row_has_norm_params_plus_extras_only():
    row = cf.raw_feature_row(A_SC, CAND_PARAMS, is_sharpe=1.23, activity_entries=28)
    assert set(row) == {"norm_coeff", "norm_AP", "norm_alpha.condition_threshold",
                        "is_daily_sharpe", "activity_entries"}
    assert row["is_daily_sharpe"] == pytest.approx(1.23)
    assert row["activity_entries"] == pytest.approx(28.0)
    # no candidate_id, source name, or timestamp field ever appears
    assert "candidate_id" not in row and "trial_id" not in row


def test_fit_phi_drops_constant_columns_never_divides_by_zero():
    import random
    rng = random.Random(2)
    rows = [cf.raw_feature_row(A_SC, CAND_PARAMS, is_sharpe=1.0 + rng.gauss(0, 0.1),
                               activity_entries=20) for _ in range(5)]
    fit = cf.fit_phi(rows)
    # activity_entries and the norm_* params are constant across these rows
    # (identical CAND_PARAMS every time); only is_daily_sharpe varies.
    assert "is_daily_sharpe" in fit.feature_names
    assert "activity_entries" in fit.dropped_names
    assert "norm_coeff" in fit.dropped_names


def test_fit_phi_raises_typed_error_when_every_column_is_constant():
    rows = [cf.raw_feature_row(A_SC, CAND_PARAMS, is_sharpe=1.0, activity_entries=20)] * 5
    with pytest.raises(cf.ContrastFeatureError, match="DEGENERATE_FEATURE_GEOMETRY"):
        cf.fit_phi(rows)


def test_phi_and_contrast_vector_anchor_against_itself_is_exact_zero():
    import random
    rng = random.Random(1)
    rows = [cf.raw_feature_row(A_SC, CAND_PARAMS, is_sharpe=rng.gauss(1, 0.3),
                               activity_entries=rng.randint(10, 40)) for _ in range(20)]
    fit = cf.fit_phi(rows)
    anchor_row = cf.raw_feature_row(A_SC, ANCHOR_PARAMS, is_sharpe=0.5, activity_entries=15)
    v = cf.contrast_vector(fit, anchor_row, anchor_row)
    assert np.allclose(v, 0.0)


def test_phi_standardization_matches_independent_formula():
    rows = [{"a": float(i), "b": float(2 * i)} for i in range(1, 21)]
    fit = cf.fit_phi(rows)
    assert set(fit.feature_names) == {"a", "b"}
    row = {"a": 5.0, "b": 10.0}
    got = cf.phi(fit, row)
    expected_a = (5.0 - fit.mean["a"]) / fit.std["a"]
    expected_b = (10.0 - fit.mean["b"]) / fit.std["b"]
    assert got[list(fit.feature_names).index("a")] == pytest.approx(expected_a)
    assert got[list(fit.feature_names).index("b")] == pytest.approx(expected_b)


def test_phi_raises_on_missing_dimension():
    rows = [{"a": float(i), "b": float(2 * i)} for i in range(1, 21)]
    fit = cf.fit_phi(rows)
    with pytest.raises(cf.ContrastFeatureError):
        cf.phi(fit, {"a": 1.0})


def test_contrast_vector_nonzero_for_different_candidates():
    rows = [{"a": float(i), "b": float(2 * i)} for i in range(1, 21)]
    fit = cf.fit_phi(rows)
    v = cf.contrast_vector(fit, {"a": 3.0, "b": 4.0}, {"a": 1.0, "b": 2.0})
    assert not np.allclose(v, 0.0)
