# Phase MF-03 Report: Model Fit, Duration Baseline & Horizon Selection
Study: `btc_regime_forecast_v1`
Run ID: `mf03-20260928T164151Z-5faeb4a9`
Date: `2026-09-28T16:48:58.955734+00:00`

## 1. Feature Ablation (G3-ABLATION)
Evaluated across 12 shared validation blocks (48 weekly origins):
- `D0_CORE_PRICE_VOL`: H56 Brier(J) = 1.0284, H90 Brier(J) = 1.0731
- `D1_DERIVATIVE_LIQUIDITY`: H56 Brier(J) = 1.0613, H90 Brier(J) = 1.0073
- `D2_COMPOSITE_PRESSURE`: H56 Brier(J) = 1.0613, H90 Brier(J) = 1.0073

**Winning Feature Cohort**: `D1_DERIVATIVE_LIQUIDITY`

## 2. Model Grid Evaluation on Development (G3-MODEL)

| Model ID | Horizon | Brier Score (V) | Brier Score (E) | Brier Score (J) | Brier Skill (J) | Bal Acc (J) |
|---|---|---|---|---|---|---|
| M1_LGBM_DEFAULT_SHALLOW | H56 | 0.8480 | 0.7109 | 1.0613 | -0.2654 | 0.1177 |
| M1_LGBM_DEFAULT_SHALLOW | H90 | 0.7703 | 0.6197 | 1.0073 | -0.1541 | 0.1601 |
| M2_LGBM_REGULARIZED_DEEP | H56 | 0.8501 | 0.7147 | 1.0525 | -0.2549 | 0.1270 |
| M2_LGBM_REGULARIZED_DEEP | H90 | 0.7410 | 0.6609 | 1.0094 | -0.1565 | 0.0820 |
| M3_LGBM_FEATURE_SUBSAMPLE | H56 | 0.8652 | 0.6786 | 1.0344 | -0.2334 | 0.1310 |
| M3_LGBM_FEATURE_SUBSAMPLE | H90 | 0.7679 | 0.6504 | 1.0327 | -0.1832 | 0.0741 |
| M4_LGBM_CONSERVATIVE_SLOW | H56 | 0.7852 | 0.6832 | 0.9851 | -0.1746 | 0.1409 |
| M4_LGBM_CONSERVATIVE_SLOW | H90 | 0.7540 | 0.6114 | 0.9692 | -0.1104 | 0.2130 |

## 3. Post-Hoc Temperature Scaling Calibration (G3-CALIBRATION)
Optimized strictly on validation out-of-fold logits/probabilities:
- Horizon 56: $T_V = 5.000$, $T_E = 2.540$, Joint Brier: 0.9851 -> 0.8655 (improvement: +0.1197)
- Horizon 90: $T_V = 3.946$, $T_E = 2.107$, Joint Brier: 0.9692 -> 0.8514 (improvement: +0.1178)

## 4. Horizon Selection H* (§8.4) (G3-DURATION-AND-HORIZON-FREEZE)
- Loss criterion $J_{56} = 0.8655$, $J_{90} = 0.8514$.
- **Selected Primary Horizon $H^*$**: **90**
- **Rationale**: H90 achieved superior calibrated loss (J_90=0.8514 < J_56=0.8655).
- Winning Recipe H56: `M4_LGBM_CONSERVATIVE_SLOW`
- Winning Recipe H90: `M4_LGBM_CONSERVATIVE_SLOW`

## 5. Freeze Specification (G3-FREEZE)
All model architectures, winning hyperparameters, feature cohorts, calibration temperatures, taxonomy hashes, and 28-day refit cadence are permanently frozen in `configs/btc_regime_forecast_v1/freeze_manifest.json` prior to entering locked Phase MF-04. Zero TEST peeking.
