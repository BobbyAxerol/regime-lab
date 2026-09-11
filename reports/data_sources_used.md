# Data sources actually used — audit view

Generated from committed artifacts by `scripts/write_data_sources_report.py`. Nothing here is re-measured at render time; every figure names the file it came from.

## The short answer

- one historical source: **`/root/bobby/pool_alpha/alphas_storage/_get_data/storage`** — the user's Parquet storage, read-only
- copied byte for byte into `snapshots/server_core_v1/`: **627 files, 22,543,243 rows, 1449 MB**
- read between `2026-09-09T20:12:26` and `2026-09-09T20:15:47` UTC; every run since then reads the COPY, never the live tree
- **no network, no collector, no repair job.** Missing coverage is reported as missing and never fetched (`configs/data_readlock_policy.json`)
- data role **development**: 2020-01-01 → 2023-12-31
- data role **outer_evaluation**: 2024-01-01 → open

## Products, and what each one can and cannot cover

| product | loader class that declares it | symbols present | files | rows | span | role in the study |
|---|---|---|---|---|---|---|
| `crypto_binance_futures_1m` | `CryptoBinance1m` | BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT | 390 | 16,891,503 | 2020-01-01 → 2026-09-09 | PRIMARY: signal and execution venue (guide 4.1) |
| `crypto_binance_futures_metrics_5m` | `BinanceFuturesMetrics5m` | BTCUSDT, ETHUSDT | 131 | 1,134,907 | 2020-09-01 → 2026-09-09 | SERVER_DERIVATIVES: G3 leverage/crowding |
| `crypto_binance_orderbook_snapshot_1h` | `BinanceOrderBookSnapshot1h` | BTCUSDT | 2 | 719 | 2026-08-10 → 2026-09-09 | SERVER_LIQUIDITY: G4 spread/depth |
| `crypto_binance_spot_1m` | `CryptoBinanceSpot1m` | BTCUSDT | 104 | 4,516,114 | 2018-01-01 → 2026-08-07 | SERVER_CORE_LONG spot leg; basis and spot-activity context |

### Wanted by the guide, absent from this storage

- **`funding_rate_history`** — needed for guide 4.1 realistic net carry, and the G3 funding features. Searched: storage tree and the loader's class list.
- **`basis_or_mark_price`** — needed for G3 basis B_t = F_t/S_t - 1 without a spot proxy. Searched: storage tree.

An absent product is never substituted and never treated as zero. Funding in particular does not exist anywhere in this storage, so every primary run is a labelled **no-funding cohort** rather than a run that assumes funding is 0.

- `crypto_binance_spot_1m` has no partition for ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT'] — the collector was never configured for them, so no amount of re-reading storage produces them
- `crypto_binance_futures_metrics_5m` has no partition for ['SOLUSDT', 'BNBUSDT', 'DOGEUSDT'] — the collector was never configured for them, so no amount of re-reading storage produces them
- `crypto_binance_orderbook_snapshot_1h` has no partition for ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT'] — the collector was never configured for them, so no amount of re-reading storage produces them

### Collector configuration, read from the product documents

- **crypto_binance_spot_1m** (`BINANCE_SPOT_1M.md`, sha256 `9dbf36417303…`): the four other symbols were never COLLECTED; the data is not lost, it was never configured, so no amount of re-reading storage will produce it
- **crypto_binance_futures_metrics_5m** (`BINANCE_FUTURES_METRICS_5M.md`, sha256 `f7c6fc010de1…`): SOLUSDT, BNBUSDT and DOGEUSDT are not in the collector config, so the G3 derivatives block can only ever cover BTCUSDT and ETHUSDT here
- **crypto_binance_orderbook_snapshot_1h** (`BINANCE_ORDERBOOK_SNAPSHOT_1H.md`, sha256 `9644b9046a10…`): THIS PRODUCT IS A ROLLING 30-DAY WINDOW. It cannot accumulate history, so SERVER_LIQUIDITY can never support a historical study on this storage; treating its few weeks as a cohort would be a mistake, not a limitation
- **crypto_binance_futures_1m** (`BINANCE_USDM_QUARTERLY_1M.md`, sha256 `f32b65b744fa…`): the five trade symbols are all present

## How much history per symbol

| symbol | product | partitions (closed) | rows | first | last |
|---|---|---|---|---|---|
| BTCUSDT | `crypto_binance_futures_1m` | 81 (80) | 3,519,131 | 2020-01-01 00:00 | 2026-09-09 20:10 |
| BTCUSDT | `crypto_binance_spot_1m` | 104 (103) | 4,516,114 | 2018-01-01 00:00 | 2026-08-07 04:13 |
| BTCUSDT | `crypto_binance_futures_metrics_5m` | 73 (72) | 632,870 | 2020-09-01 00:00 | 2026-09-09 15:45 |
| BTCUSDT | `crypto_binance_orderbook_snapshot_1h` | 2 (1) | 719 | 2026-08-10 19:00 | 2026-09-09 19:00 |
| ETHUSDT | `crypto_binance_futures_1m` | 81 (80) | 3,519,133 | 2020-01-01 00:00 | 2026-09-09 20:12 |
| ETHUSDT | `crypto_binance_futures_metrics_5m` | 58 (57) | 502,037 | 2021-12-01 00:00 | 2026-09-09 15:50 |
| SOLUSDT | `crypto_binance_futures_1m` | 73 (72) | 3,148,633 | 2020-09-14 07:00 | 2026-09-09 20:12 |
| BNBUSDT | `crypto_binance_futures_1m` | 80 (79) | 3,461,052 | 2020-02-10 08:01 | 2026-09-09 20:12 |
| DOGEUSDT | `crypto_binance_futures_1m` | 75 (74) | 3,243,554 | 2020-07-10 09:00 | 2026-09-09 20:13 |

- five-symbol common period: **2020-09-14 → 2026-09-09**
- the five-symbol common-period aggregate is reported SEPARATELY from each symbol's longest valid history; returns are never back-filled with zeros before listing (guide 10.4)
- spot clean convention: from **2020-01-01** — spot bars before this date exist in storage but are outside the user's clean convention and are excluded from eligibility

## Is the source still what it was when it was read?

- checked `2026-09-10T10:41:51` UTC → **EXTERNAL_VINTAGE_RESTAMP_ONLY**
- the lab's own 627 snapshot files: **all intact** (this is the number that decides whether past results still describe real data)
- upstream files whose bytes differ now: **32**
  - of the closed ones, READ and classified: **0 content revisions**, **23 ingest re-stamps**
  - example re-stamp: `crypto_binance_futures_metrics_5m` BTCUSDT 2020-09 — 8,636 rows compared, `ingested_at` moved 2026-09-09 15:53:23 → 2026-09-10 10:31:38, every measured column identical
  - open trailing: **7** (the collector appending — excluded from any primary read)
  - rolling-window: **2** (the order book rewrites its own 30-day window by design)
- cohorts invalidated: **none**
- primary run valid: **True**

> the file digest detects drift; a read decides what the drift MEANS. A closed partition stops invalidating its cohort only when every measured column is read and proven identical (VINTAGE_RESTAMP_ONLY). A changed value, row count or schema, or a file that will not read, stays CONTENT_REVISION and still invalidates. Without deep=True nothing is classified and every closed-partition drift invalidates.

### How the raw bars are read

The lab does NOT call `data_loader.py` at run time. The loader is copied read-only into `vendor_readonly/loader_snapshot/`, pinned by SHA-256, and parsed STATICALLY so its reader classes tell the lab which storage path holds which product (guide 6.1: inventory by product, not by assumed class name). The bars are then read directly from the lab's own byte-copied parquet.

That distinction is measured, not asserted: `scripts/verify_loader_parity.py` calls the pinned loader (`sha256 99612d99ada25732…`) on 15 partitions (each symbol's first, middle and last closed partition) and diffs its output against the same bytes read directly. **10 of 15 disagree**, always on the same column.

| symbol | partition | stored dtype | bars with a fractional volume | bars a cast sends to zero | columns differing |
|---|---|---|---|---|---|
| BTCUSDT | 2020-01 | `float64` | 44,594 | 92 | volume |
| BTCUSDT | 2023-05 | `float64` | 44,598 | 0 | volume |
| BTCUSDT | 2026-08 | `float64` | 44,594 | 41 | volume |
| ETHUSDT | 2020-01 | `float64` | 44,548 | 58 | volume |
| ETHUSDT | 2023-05 | `float64` | 44,603 | 0 | volume |
| ETHUSDT | 2026-08 | `float64` | 44,591 | 0 | volume |
| BNBUSDT | 2020-02 | `float64` | 28,032 | 1 | volume |
| BNBUSDT | 2023-06 | `float64` | 42,737 | 0 | volume |
| BNBUSDT | 2026-08 | `float64` | 44,174 | 0 | volume |
| SOLUSDT | 2020-09 | `int64` | 0 | 0 | — |
| SOLUSDT | 2023-09 | `int64` | 0 | 0 | — |
| SOLUSDT | 2026-08 | `float64` | 44,176 | 0 | volume |
| DOGEUSDT | 2020-07 | `int64` | 0 | 0 | — |
| DOGEUSDT | 2023-08 | `int64` | 0 | 0 | — |
| DOGEUSDT | 2026-08 | `int64` | 0 | 0 | — |

MarketDataLoaderBase._normalize casts volume to int64. Symbols whose stored volume is fractional lose the fraction on every bar, and a bar under 1.0 unit with real trades becomes volume 0. Symbols already stored as int64 are unaffected, so the defect is invisible on exactly the symbols one would test first.

reading the parquet directly preserves the stored resolution; panel.normalize_numeric_dtypes coerces to float64 on read so a feature's dtype never depends on which month it came from

Largest measured loss — **BTCUSDT 2026-08**: 44,594 of 44,640 bars differ, **0.515%** of the partition's total volume is lost, and **41** bars with real trades become volume 0. Those bars feed the G2 activity and taker-imbalance features, where a zero denominator is masked rather than epsilon-padded — so the truncation would have removed observations, not merely blurred them.

Guarded by `test_t21_resampling_never_truncates_real_volume`, `test_t21_stored_volume_dtype_varies_and_is_coerced` and `test_loader_endpoint_parity_artifact_matches_a_live_call`.

## Measured defects in the raw data — do not re-trust these columns

| column | defect | what the lab does instead |
|---|---|---|
| `close_time` | near the 1970 epoch for SOL/BNB perps, mixed for BTC spot, sometimes a STRING; 145 of 385 partitions untrusted | derives `bar_close = time + interval` and never reads the column |
| `volume` | dtype varies by symbol AND by month (SOL integral until 2024-12, DOGE integral throughout) | coerces to float64 on read so a feature's dtype never depends on which month it came from |
| quantity step | SOL's step changed mid-sample (integral → fractional, 2025-04) | a single pinned step in the instrument registry would be wrong for part of the history; the change is recorded rather than averaged away |
| 2026-05 BTC/ETH | carry a second ingest day (2026-06-12, ~44k rows) — the documented continuity repair | masked in every panel as `in_documented_repair_window` |

## Which phase consumed which slice

| phase | alphas × symbols | products read | window | notes |
|---|---|---|---|---|
| LAB-04 | 15/20 cells (3 alphas × 5 symbols) | `crypto_binance_futures_1m` | development | 5 cells NOT_READY with null metrics, never PnL 0 |
| LAB-05 | 1 symbol (BTCUSDT) | `crypto_binance_futures_1m` via the 8 primary-core features | development | 40 fits at 4h, 365d memory; outer holdout touched: False |
| LAB-06 | 1 of 20 cells (A-SC / BTCUSDT) | `crypto_binance_futures_1m` | development | 1,530 episodes, 6,566 decisions at 4h |

G3 (open interest and trader ratios) and G4 (order-book spread) are **cohort extensions**: no phase above reads them, which is why the 23 upstream re-stamps in the metrics product cannot reach any result on this page.

## Re-derive every number on this page

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
$LAB/environments/lab_venv/bin/python $LAB/scripts/recheck_readlock.py       # re-hash 627 files, classify any drift
$LAB/environments/lab_venv/bin/python $LAB/scripts/verify_loader_parity.py   # call the pinned loader, diff against the parquet
$LAB/environments/lab_venv/bin/python $LAB/scripts/refresh_data_eligibility.py # rebuild the coverage report from the manifest
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/test_lab03_pipeline.py $LAB/tests/test_lab03_data.py -q
```

