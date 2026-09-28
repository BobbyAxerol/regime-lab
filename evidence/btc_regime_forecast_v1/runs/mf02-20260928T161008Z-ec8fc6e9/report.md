# Phase MF-02 Report: Features, Targets, Duration & Baselines
Study: `btc_regime_forecast_v1`
Run ID: `mf02-20260928T161008Z-ec8fc6e9`
Date: `2026-09-28T16:10:32.811149+00:00`

## 1. Feature Engineering (G2-FEATURES)
- Total causal features: 38 (strictly <= 50).
- Cohorts:
  - `D0_CORE_PRICE_VOL`: 29 features
  - `D1_DERIVATIVE_LIQUIDITY`: 38 features
  - `D2_COMPOSITE_PRESSURE`: 38 features
- All features generated with causal lag >= 1 day, no future leakage.

## 2. Target Formulation & Frozen Taxonomy (G2-TARGETS)
- Evaluated horizons: $H \in \\{56, 90\\}$ calendar days.
- Frozen prefix: `2022-01-14` to `2024-01-13` (730 daily origins).
- Horizon 56:
  - Realized Volatility: $q_{1/3} = 0.4441$, $q_{2/3} = 0.5641$
  - Path Efficiency: $\\tau = 0.1630$
- Horizon 90:
  - Realized Volatility: $q_{1/3} = 0.4678$, $q_{2/3} = 0.5651$
  - Path Efficiency: $\\tau = 0.1288$

## 3. Duration & Survival Analysis (G2-DURATION-DEFINITION)
- Primary Detector: `OBS14_CONFIRM3_V1`
- Episode Ledger: 126 total episodes, 1 right-censored.
- Mean episode duration: 12.1 days.
- Kaplan-Meier RMST(90d) and RMRL computed across all observable regimes.

## 4. Mandatory Baselines Performance on 48 Dev Origins (G2-BASELINE)

| Baseline | Horizon | Brier Score (V) | Brier Score (E) | Brier Score (J) | Bal Acc (J) | MAE (V) |
|---|---|---|---|---|---|---|
| B1_PERSISTENCE | H56 | 1.5833 | 1.2500 | 1.9167 | 0.0476 | 0.1110 |
| B1_PERSISTENCE | H90 | 1.7917 | 1.3333 | 2.0000 | 0.0000 | 0.0982 |
| B2_MATURED_FREQ | H56 | 0.7261 | 0.5135 | 0.8387 | 0.1667 | 0.1090 |
| B2_MATURED_FREQ | H90 | 0.7944 | 0.5099 | 0.8728 | 0.1667 | 0.1030 |
| B3_HAR_RV | H56 | 0.7892 | 0.6667 | 0.9297 | 0.1481 | 0.0810 |
| B3_HAR_RV | H90 | 0.5846 | 0.6667 | 0.8615 | 0.1667 | 0.0540 |
| B4_REGULARIZED_LINEAR | H56 | 1.0316 | 0.7917 | 1.2099 | 0.1731 | 0.1302 |
| B4_REGULARIZED_LINEAR | H90 | 0.9728 | 0.8514 | 1.2170 | 0.1257 | 0.0993 |

## 5. Exit Gate Verifications
- `G2-FEATURES`: PASS (<=50 features, strictly causal D0/D1/D2 cohorts).
- `G2-TARGETS`: PASS (Continuous targets & taxonomy boundaries frozen on matured training prefix).
- `G2-SPLIT`: PASS (730 training origins, 48 Dev weekly origins, 48 Test weekly origins).
- `G2-BASELINE`: PASS (4 mandatory baselines executed with zero look-ahead bias).
- `G2-REGISTRATION`: PASS (4 LightGBM configs + Chronos challenger registered in model_grid.json).
- `G2-DURATION-DEFINITION`: PASS (Causal state tape, right-censored episode ledger, KM RMST/RMRL).
