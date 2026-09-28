# RPS_CURRENT — BTC-RPS-V1.2 Model-First Study

Current source/runtime and approved registration:

| Phase | Technical | Model-Skill / Scope | Owner | Evidence |
|---|---|---|---|---|
| **MF-01** | **PASS** (4/4 gates) | **DATA_QUALIFIED_SCOPE_LOCKED** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf01-20260928T122818Z-64bb6ac4/` |
| **MF-02** | NOT_STARTED | PENDING | PENDING | — |
| **MF-03** | NOT_STARTED | PENDING | PENDING | — |
| **MF-04** | NOT_STARTED | PENDING | PENDING | — |
| **MF-05** | NOT_STARTED | PENDING | PENDING | — |

## MF-01 Complete (2026-09-28)
- **Gates**: `G1-SOURCE` PASS, `G1-EXCLUDE` PASS, `G1-TIMELINE` PASS, `G1-EVIDENCE` PASS.
- **Qualified Data**: Binance Spot 1m (2018..2026), Binance Perp 1m (2020..2026), Binance Metrics 5m (2020..2026).
- **Excluded Sources**: CoinGecko dominance, BTCDOM, 1h Orderbook, Deribit options, Fear & Greed, raw REST funding.
- **Timeline**: 180d warmup, 730d initial training, 12 Dev blocks (48 weekly origins), 91d maturity gap, 12 Test blocks (48 weekly origins), 90d follow-up fully covered with 5 days safety cushion.
- **Financial Engine Calls**: 0 (QuantBT untouched).
- **Next Phase**: MF-02 (Features, Targets, Duration & Baselines).
