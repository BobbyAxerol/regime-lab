# Data eligibility — LAB-03

Snapshot `server_core_v1` · 627 partitions · 22,543,243 rows · 1449 MB · 618 closed / 9 open

## 1. What the storage actually contains

| Product | Symbols present | Symbols absent |
|---|---|---|
| `crypto_binance_spot_1m` | BTCUSDT | ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT |
| `crypto_binance_futures_1m` | BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT | — |
| `crypto_binance_futures_metrics_5m` | BTCUSDT, ETHUSDT | SOLUSDT, BNBUSDT, DOGEUSDT |
| `crypto_binance_orderbook_snapshot_1h` | BTCUSDT | ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT |

Products the cohorts wanted and that do **not** exist here:

- **`funding_rate_history`** — no funding series exists in this storage, so a realistic net-carry claim cannot be made and the funding cohort is MISSING, never silently zero (guide 4.1)
- **`basis_or_mark_price`** — basis must be derived from synchronised spot and perp closes where spot exists, and is unavailable for the four symbols with no spot product

## 2. Cohorts, reported separately

| Cohort | Members | Common period | Status |
|---|---|---|---|
| SERVER_CORE_LONG | 5 (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT) | 2020-09-14 07:00:00 → 2026-09-09 20:10:00 | AVAILABLE |
| SERVER_CORE_SPOT | 1 (BTCUSDT) | 2020-01-01 → 2026-08-07 04:13:00 | AVAILABLE |
| SERVER_DERIVATIVES | 2 (BTCUSDT, ETHUSDT) | 2021-12-01 00:00:00 → 2026-09-09 15:45:00 | AVAILABLE |
| SERVER_LIQUIDITY | 1 (BTCUSDT) | 2026-08-10 19:00:00 → 2026-09-09 19:00:00 | AVAILABLE |
| FREE_ENRICHED | 0 (—) | — | EMPTY |

> cohorts are reported independently. Intersecting every source would shrink the core cohort to the orderbook product's few weeks, which the guide forbids (6.2).

## 3. Usable interval per symbol

| Symbol | Data starts | First decision bar (after warmup) | Ends |
|---|---|---|---|
| BTCUSDT | 2020-01-01 00:00:00 | 2020-01-06 00:00:00 | 2026-09-09 20:10:00 |
| ETHUSDT | 2020-01-01 00:00:00 | 2020-01-06 00:00:00 | 2026-09-09 20:12:00 |
| SOLUSDT | 2020-09-14 07:00:00 | 2020-09-19 07:00:00 | 2026-09-09 20:12:00 |
| BNBUSDT | 2020-02-10 08:01:00 | 2020-02-15 08:01:00 | 2026-09-09 20:12:00 |
| DOGEUSDT | 2020-07-10 09:00:00 | 2020-07-15 09:00:00 | 2026-09-09 20:13:00 |

Five-symbol common period: **2020-09-14 07:00:00 → 2026-09-09 20:10:00** (it begins at SOLUSDT's listing). Each symbol's longest history is reported separately; returns are never back-filled with zeros before listing.

## 4. Availability

- Bar close is **derived** as `time + interval`. The stored `close_time` column is a diagnostic only.
- `available_at` = `bar_close + publication_delay`.
- Book snapshots use their real `sample_time`, not the hour label.
- Funding: **MISSING** — a missing funding history is NEVER treated as zero carry. Any cohort that would need funding is marked missing, and a no-funding study carries its own disclaimer (guide 4.1).

## 5. Feature schema

Regime observation interval: **4h**. Primary core: **8 features** (guide budget 8–12, respected = True).

| Tier | Features | Coverage |
|---|---|---|
| primary_core | g1_rv_6, g1_direction_6, g1_efficiency_6, g2_taker_imbalance, g2_log_activity_30, g5_dispersion_6, g5_breadth_6, g5_residual_return_30 | BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT |
| derivatives_extension | g3_dlog_oi, g3_return_oi_interaction, g3_basis | BTCUSDT, ETHUSDT |
| liquidity_extension | g4_log_amihud_30 | BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT |
| registered_alternative | g1_downside_ratio_6, g1_jump_concentration_6, g2_trade_count_30, g5_factor_concentration_30 | BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT |

> only the primary_core tier covers all five symbols and may enter the regime model. G3 needs the metrics product (BTCUSDT and ETHUSDT only) and G4 needs the book product (BTCUSDT, weeks only), so they are cohort EXTENSIONS evaluated on their own interval rather than silently-NaN core columns (guide 6.2).

Dropped by the scaler:

- `g4_spread_bps` — no finite observation in the training slice

Scaler fitted on **2020-01-01 00:00:00 → 2023-12-31 00:00:00** (40,869 rows), fitted on the training slice only; never on the full history.

## 6. Instrument metadata (inferred from the snapshot)

| Symbol | Tick sizes observed | Quantity steps observed | Stable? |
|---|---|---|---|
| BTCUSDT | [0.01, 0.1] | [0.001] | tick=False, qty=True |
| ETHUSDT | [0.01] | [0.001] | tick=True, qty=True |
| SOLUSDT | [0.001, 0.01] | [0.01, 1.0] | tick=False, qty=False |
| BNBUSDT | [0.001, 0.01] | [0.01] | tick=False, qty=True |
| DOGEUSDT | [1e-06, 1e-05] | [1.0] | tick=False, qty=True |

Registry digest `85ae389330d104d80a581e09`. Unstable quantity step: ['SOLUSDT'].

## 7. Minimum economic effect

**0.640 bps per day**, derived as `cost_uncertainty_per_round_trip * busiest_round_trips_per_day` from a 10 bps round trip, a 10 bps cost-stress band and 0.064 round trips per day for the busiest alpha.

> an improvement smaller than this sits inside the registered cost-stress band and is reported as inconclusive, not as an edge. The threshold is fixed now, before any arm has been compared, so it can never be chosen to fit an observed delta (guide 11.2).

## 8. Market adapter qualification

20/20 cells qualified on real bars from 2022-03-01 (1500 bars, development role).

> a bounded development slice per alpha-symbol; it checks gaps, HTF availability, warmup and the account trace only, and may never be reused as evidence for a result

## 9. Enrichment

Acquired: **none**. Primary runs without it: True.

- `defillama_stablecoin_supply` — NOT_ACQUIRED: snapshot endpoint availability and revisions; a rise in raw TVL is NOT an inflow
- `whale_alert_published_alerts` — NOT_ACQUIRED: use the publication timestamp, deduplicate event ids, carry coverage masks; this is not whale netflow and not the full transaction set
- `farside_btc_etf_flows` — NOT_ACQUIRED: respect the publication lag; never fill 0 before the product existed
- `coin_metrics_community` — NOT_ACQUIRED: review coverage and the non-commercial terms before any use; free does not mean unrestricted commercial use

## 10. What this does not establish

- No backtest has been run and no arm has been compared. Nothing here is evidence about edge.
- The liquidity cohort has no data inside the development window, so `g4_spread_bps` cannot be scaled and the cohort cannot enter the primary model.
- Funding does not exist in this storage; every primary run is a labelled no-funding cohort.
- Instrument metadata is INFERRED from observed granularity, not read from venue metadata.

