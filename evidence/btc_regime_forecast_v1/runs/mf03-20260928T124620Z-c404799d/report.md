# Phase MF-03 Report: Model Fit, Duration Baseline & Horizon Selection
Study: `btc_regime_forecast_v1`
Run ID: `mf03-20260928T124620Z-c404799d`
Date: `2026-09-28T12:52:20.120597+00:00`

## 1. Feature Ablation (G3-ABLATION)
Evaluated across 12 shared validation blocks (48 weekly origins):
- `D0_CORE_PRICE_VOL`: H56 Brier(J) = 1.1047, H90 Brier(J) = 1.1215
- `D1_DERIVATIVE_LIQUIDITY`: H56 Brier(J) = 1.0003, H90 Brier(J) = 0.9808
- `D2_COMPOSITE_PRESSURE`: H56 Brier(J) = 1.0003, H90 Brier(J) = 0.9808

**Winning Feature Cohort**: `D1_DERIVATIVE_LIQUIDITY`

## 2. Model Grid Evaluation on Development (G3-MODEL)

| Model ID | Horizon | Brier Score (V) | Brier Score (E) | Brier Score (J) | Brier Skill (J) | Bal Acc (J) |
|---|---|---|---|---|---|---|
| M1_LGBM_DEFAULT_SHALLOW | H56 | 0.9562 | 0.6615 | 1.0003 | -0.1926 | 0.1657 |
| M1_LGBM_DEFAULT_SHALLOW | H90 | 0.7052 | 0.5857 | 0.9808 | -0.1238 | 0.0694 |
| M2_LGBM_REGULARIZED_DEEP | H56 | 0.9070 | 0.7194 | 0.9891 | -0.1793 | 0.1333 |
| M2_LGBM_REGULARIZED_DEEP | H90 | 0.6944 | 0.4269 | 0.8904 | -0.0201 | 0.0933 |
| M3_LGBM_FEATURE_SUBSAMPLE | H56 | 0.9381 | 0.6969 | 1.0052 | -0.1986 | 0.0972 |
| M3_LGBM_FEATURE_SUBSAMPLE | H90 | 0.7391 | 0.4625 | 0.9596 | -0.0994 | 0.1197 |
| M4_LGBM_CONSERVATIVE_SLOW | H56 | 0.9076 | 0.6482 | 0.9828 | -0.1718 | 0.1519 |
| M4_LGBM_CONSERVATIVE_SLOW | H90 | 0.6928 | 0.5364 | 0.9185 | -0.0524 | 0.0714 |
| M5_CHRONOS_SYNTH | H56 | 1.5378 | 0.7198 | 1.3482 | -0.6075 | 0.1190 |
| M5_CHRONOS_SYNTH | H90 | 1.7400 | 0.8782 | 1.5004 | -0.7190 | 0.1111 |

## 3. Post-Hoc Temperature Scaling Calibration (G3-CALIBRATION)
Optimized strictly on validation out-of-fold logits/probabilities:
- Horizon 56: $T_V = 5.000$, $T_E = 2.578$, Joint Brier: 0.9828 -> 0.8618 (improvement: +0.1210)
- Horizon 90: $T_V = 2.783$, $T_E = 1.171$, Joint Brier: 0.8904 -> 0.7909 (improvement: +0.0995)

## 4. Horizon Selection H* (§8.4) (G3-DURATION-AND-HORIZON-FREEZE)
- Loss criterion $J_{56} = 0.8618$, $J_{90} = 0.7909$.
- **Selected Primary Horizon $H^*$**: **90**
- **Rationale**: H90 achieved superior calibrated loss (J_90=0.7909 < J_56=0.8618).
- Winning Recipe H56: `M4_LGBM_CONSERVATIVE_SLOW`
- Winning Recipe H90: `M2_LGBM_REGULARIZED_DEEP`

## 5. Freeze Specification (G3-FREEZE)
All model architectures, winning hyperparameters, feature cohorts, calibration temperatures, taxonomy hashes, and 28-day refit cadence are permanently frozen in `configs/btc_regime_forecast_v1/freeze_manifest.json` prior to entering locked Phase MF-04. Zero TEST peeking.
