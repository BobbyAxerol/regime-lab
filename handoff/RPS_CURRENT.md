# RPS_CURRENT — BTC-RPS-V1.2 Model-First Study

Current source/runtime and approved registration:

| Phase | Technical | Model-Skill / Scope | Owner | Evidence |
|---|---|---|---|---|
| **MF-01** | **PASS** (4/4 gates) | **DATA_QUALIFIED_SCOPE_LOCKED** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf01-20260928T122818Z-64bb6ac4/` |
| **MF-02** | **PASS** (6/6 gates) | **FEATURES_BASELINES_DURATION_LOCKED** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf02-20260928T124051Z-1c4ebe49/` |
| **MF-03** | NOT_STARTED | PENDING | PENDING | — |
| **MF-04** | NOT_STARTED | PENDING | PENDING | — |
| **MF-05** | NOT_STARTED | PENDING | PENDING | — |

## MF-02 Complete (2026-09-28)
- **Gates**: `G2-FEATURES` PASS, `G2-TARGETS` PASS, `G2-SPLIT` PASS, `G2-BASELINE` PASS, `G2-REGISTRATION` PASS, `G2-DURATION-DEFINITION` PASS.
- **Features**: 40 causal rolling features across cohorts D0_CORE_PRICE_VOL (29), D1_DERIVATIVE_LIQUIDITY (40), D2_COMPOSITE_PRESSURE (40).
- **Targets & Taxonomy**: Forward horizons $H \in \{56, 90\}$, boundaries ($q_{1/3}, q_{2/3}, \tau$) frozen strictly on matured prefix `2022-01-14..2024-01-13` (730 daily origins).
- **Duration / Survival (Section 4D)**: Primary detector `OBS14_CONFIRM3_V1`, 126 episodes ledger, 1 right-censored at cutoff, Kaplan-Meier RMST(90d) and RMRL computed.
- **Baselines Evaluated (48 Dev Origins)**: B1 Persistence, B2 Matured Frequencies, B3 HAR-RV, B4 Regularized Linear. Best joint Brier score: B2 (0.8387 on H56).
- **Model Grid Registered**: 4 LightGBM configs + Chronos-2-Synth challenger in `model_grid.json`.
- **Financial Engine Calls**: 0 (QuantBT untouched).
- **Next Phase**: MF-03 (Model Fit, Duration Baseline & Horizon Selection on Development).

## MF-01 Complete (2026-09-28)
- **Gates**: `G1-SOURCE` PASS, `G1-EXCLUDE` PASS, `G1-TIMELINE` PASS, `G1-EVIDENCE` PASS.
- **Qualified Data**: Binance Spot 1m (2018..2026), Binance Perp 1m (2020..2026), Binance Metrics 5m (2020..2026).
- **Excluded Sources**: CoinGecko dominance, BTCDOM, 1h Orderbook, Deribit options, Fear & Greed, raw REST funding.
- **Timeline**: 180d warmup, 730d initial training, 12 Dev blocks (48 weekly origins), 91d maturity gap, 12 Test blocks (48 weekly origins), 90d follow-up fully covered with 5 days safety cushion.
- **Financial Engine Calls**: 0 (QuantBT untouched).
