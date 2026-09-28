import pytest
import numpy as np
import pandas as pd

from crypto_regime_lab.regime_forecast.models import LightGbmRegimeModel

def test_fit_and_predict_imputation_consistency():
    """FIX-03 Acceptance test 1:
    Verify that predict() uses the exact same column medians as fit() for imputation.
    A test row with NaN must yield the exact same prediction as a test row with the stored median.
    Prior to fixing, predict() uses nan_to_num(nan=0.0) which differs from column medians.
    """
    np.random.seed(20260928)
    n = 100
    # Create synthetic dataset with non-zero medians (e.g. centered around 50.0)
    feat1 = np.random.normal(50.0, 5.0, size=n)
    feat2 = np.random.normal(100.0, 10.0, size=n)
    # Inject 2% NaNs into feat1 (< 5% threshold)
    feat1[0:2] = np.nan
    
    df_train = pd.DataFrame({
        "f1": feat1,
        "f2": feat2,
        "target_v_class": np.random.choice(["LOW_VOL", "MID_VOL", "HIGH_VOL"], size=n),
        "target_e_class": np.random.choice(["CHOP_HOSTILE", "RANGE_NEUTRAL", "TREND_FRIENDLY"], size=n),
        "target_v_cont": np.random.uniform(0.01, 0.08, size=n),
        "target_e_cont": np.random.uniform(-0.5, 0.5, size=n),
    })
    
    config = {
        "model_id": "TEST_MODEL",
        "hyperparameters": {
            "max_depth": 2,
            "num_leaves": 4,
            "n_estimators": 10,
            "min_child_samples": 5,
            "random_state": 20260928
        }
    }
    
    model = LightGbmRegimeModel(config)
    model.fit(
        df_matured=df_train,
        feature_cols=["f1", "f2"],
        v_class_col="target_v_class",
        e_class_col="target_e_class",
        v_cont_col="target_v_cont",
        e_cont_col="target_e_cont",
        max_impute_share=0.05
    )
    
    assert model.fitted, "Model must be successfully fitted"
    assert hasattr(model, "col_medians_"), "Model must store col_medians_ from fit"
    assert hasattr(model, "imputed_row_share_per_column_"), "Model must store imputed_row_share_per_column_"
    
    # Test row with NaN in f1
    row_with_nan = pd.Series({"f1": np.nan, "f2": 100.0})
    # Equivalent row with f1 replaced by the median stored in model
    f1_median = model.col_medians_[0]
    assert abs(f1_median - 50.0) < 5.0, "Median of f1 must be around 50.0 (not 0.0)"
    row_with_median = pd.Series({"f1": f1_median, "f2": 100.0})
    
    v_classes = ["LOW_VOL", "MID_VOL", "HIGH_VOL"]
    e_classes = ["CHOP_HOSTILE", "RANGE_NEUTRAL", "TREND_FRIENDLY"]
    j_classes = [f"{v}__{e}" for v in v_classes for e in e_classes]
    
    res_nan = model.predict(row_with_nan, v_classes, e_classes, j_classes)
    res_median = model.predict(row_with_median, v_classes, e_classes, j_classes)
    
    # These must be strictly identical
    assert np.isclose(res_nan["pred_v_cont"], res_median["pred_v_cont"], atol=1e-7), \
        f"pred_v_cont mismatch: {res_nan['pred_v_cont']} vs {res_median['pred_v_cont']}"
    assert np.isclose(res_nan["pred_e_cont"], res_median["pred_e_cont"], atol=1e-7), \
        f"pred_e_cont mismatch: {res_nan['pred_e_cont']} vs {res_median['pred_e_cont']}"
    for c in v_classes:
        assert np.isclose(res_nan["prob_v_3class"][c], res_median["prob_v_3class"][c], atol=1e-7)


def test_refuse_fit_when_column_imputation_exceeds_threshold():
    """FIX-03 Acceptance test 2:
    Verify that LightGbmRegimeModel.fit() raises ValueError if any column has NaN share > max_impute_share.
    """
    np.random.seed(20260928)
    n = 100
    feat1 = np.random.normal(50.0, 5.0, size=n)
    feat2 = np.random.normal(100.0, 10.0, size=n)
    # Inject 10% NaNs (> 5% threshold)
    feat1[0:10] = np.nan
    
    df_train = pd.DataFrame({
        "f1": feat1,
        "f2": feat2,
        "target_v_class": np.random.choice(["LOW_VOL", "MID_VOL", "HIGH_VOL"], size=n),
        "target_e_class": np.random.choice(["CHOP_HOSTILE", "RANGE_NEUTRAL", "TREND_FRIENDLY"], size=n),
        "target_v_cont": np.random.uniform(0.01, 0.08, size=n),
        "target_e_cont": np.random.uniform(-0.5, 0.5, size=n),
    })
    
    config = {
        "model_id": "TEST_MODEL",
        "hyperparameters": {
            "max_depth": 2,
            "num_leaves": 4,
            "n_estimators": 10,
            "random_state": 20260928
        }
    }
    
    model = LightGbmRegimeModel(config)
    with pytest.raises(ValueError, match="exceeds maximum allowed imputation threshold"):
        model.fit(
            df_matured=df_train,
            feature_cols=["f1", "f2"],
            v_class_col="target_v_class",
            e_class_col="target_e_class",
            v_cont_col="target_v_cont",
            e_cont_col="target_e_cont",
            max_impute_share=0.05
        )
