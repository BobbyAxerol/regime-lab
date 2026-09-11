# LAB-03 — Server-first snapshots and causal feature panels

**Status: PASS.** 37/37 guide requirements DONE after a second audit that found and closed 6 further gaps.
**Date:** 2026-09-09 · **Study:** `crypto_regime_timeedge_v2` · **Snapshot:** `server_core_v1`

## 1. What the storage actually holds — and why

The decisive finding is that most absences are **collector configuration**, not lost data. The product documentation sitting beside the loader says so, and the storage agrees exactly.

| Product | Trade symbols present | Why the rest are missing |
|---|---|---|
| `crypto_binance_futures_1m` | **all 5** | — |
| `crypto_binance_spot_1m` | BTCUSDT only | the collector config tracks `BTCUSDT` only, from 2018-01-01 |
| `crypto_binance_futures_metrics_5m` | BTCUSDT, ETHUSDT | SOL/BNB/DOGE were never in the collector's symbol list |
| `crypto_binance_orderbook_snapshot_1h` | BTCUSDT | **`lookback_days: 30`** — a rolling window that can never accumulate history |

**Funding does not exist anywhere in this storage.** No product, no reader class. Every primary run is therefore a labelled no-funding cohort and may not claim realistic net carry. It is never treated as zero.

Snapshot: **627 partitions, 22,542,904 rows, 1449 MB**, byte-copied, 618 closed / 9 open.

## 2. Data defects found by measurement

| Defect | Measured |
|---|---|
| `close_time` is unusable | correct for BTC/ETH/DOGE perps; lands near the **1970 epoch** for SOL (87%) and BNB (100%); mixed for BTC spot; stored as a **string** in some spot partitions. **145 of 385** checked partitions have an untrusted `close_time`. The lab derives `bar_close = time + interval` and never uses the column for availability. |
| volume dtype varies | SOL stores `volume` as **int64 until 2024-12**, then double; DOGE is int64 throughout. Coerced to float64 on read so a feature's dtype cannot depend on which month it came from. |
| quantity step changed | SOLUSDT is integral through 2025-03 and fractional from 2025-04 — a single pinned instrument step would be wrong for part of the history. |
| a documented repair is in the data | the 2026-05 partitions for BTC and ETH carry a **second ingest day (2026-06-12)** covering ~44k rows: the documented continuity repair. Masked in every panel as `in_documented_repair_window`. |

## 3. Cohorts — reported separately, never intersected

| Cohort | Members | Period |
|---|---|---|
| SERVER_CORE_LONG | 5 | 2020-09-14 → 2026-09-09 (starts at SOL's listing) |
| SERVER_CORE_SPOT | BTCUSDT | 2020-01-01 → 2026-08-07 (pre-2020 storage excluded by the user's clean convention) |
| SERVER_DERIVATIVES | BTCUSDT, ETHUSDT | 2021-12-01 → 2026-09-09 |
| SERVER_LIQUIDITY | BTCUSDT | 2026-08-10 → 2026-09-09, rolling |
| FREE_ENRICHED | — | empty; nothing acquired |

Intersecting them would collapse the core cohort to the order book's few weeks, which the guide forbids.

## 3b. The market-context universe cannot be widened here

Guide §6.2 allows a market-context universe broader than the five traded symbols. Measured: this storage holds **exactly five perpetual symbols**. The other 48 symbol directories are dated quarterly contracts (`BTCUSDT_210326`, …) — expiries of the same underlyings, not additional assets. Counting them would inflate breadth without adding information. So G5 breadth, dispersion and factor concentration are computed over five assets because five is the entire universe, not because the scope was narrowed.

## 4. Features — coverage decides membership

The **primary core is exactly 8 features** (guide budget 8–12), and it contains only features that cover all five symbols:

`g1_rv_6`, `g1_direction_6`, `g1_efficiency_6`, `g2_taker_imbalance`, `g2_log_activity_30`, `g5_dispersion_6`, `g5_breadth_6`, `g5_residual_return_30`

G3 needs the metrics product (BTC/ETH only) and G4 needs the book product (BTC, weeks only), so they are **cohort extensions**, not silently-NaN core columns. `g4_spread_bps` was dropped by the scaler with the honest reason that the liquidity cohort has **no data inside the development window at all**.

Scaler: median/MAD, clip ±5, fitted on the **development role 2020-01-01 → 2023-12-31 only**. Group weights `w_j = ω_g/d_g` so a large block cannot dominate. Raw aggregates are retained beside every z-score.

Ratio features mask a zero denominator instead of adding an epsilon: a flat window has no direction and no path efficiency, and the guide requires that to be **missing**, not a number.

## 5. Causality

- `available_at = bar_close + publication_delay`, with `bar_close` derived, never read.
- Book snapshots use their real `sample_time` (measured 0–3593 s inside the hour).
- Future-mutation tests pass through **the loader, the resampler and the scaler**: adding a later partition does not change an earlier read; resampling a longer series does not change earlier buckets; a wild future does not move the fitted median/MAD.
- Batch and streamed resampling are **identical**, so per-partition processing is safe.

## 6. Read-lock — and what it caught

The read-lock distinguishes three kinds of upstream change, and only one invalidates a run:

- **open trailing partitions** (5) — the collector appending to the current month;
- **rolling-window products** (2) — the order book prunes and rewrites its own partitions **by design**, so its partitions are never immutable;
- **immutable products** (0) — a change here would invalidate every run on the snapshot.

The first pass classified the order-book rewrite as `EXTERNAL_DATA_DRIFT` and correctly stopped the build. The fix was not to relax the check but to model the product honestly.

## 7. LAB-01's open blockers, now closed

| Blocker | Closed with |
|---|---|
| `data_roles` | development 2020-01-01→2023-12-31, outer_evaluation 2024-01-01→ (explicitly **not** an untouched holdout) |
| `instrument_registry_digest` | `85ae389330d104d8…`, inferred from measured tick and quantity granularity; records that SOL's step is unstable |
| `minimum_economic_effect` | **0.640 bps/day**, derived as cost-stress span (10 bps per round trip) × the busiest alpha's measured 0.064 round trips/day — fixed **before** any arm comparison |

Study status: `REGISTERED_DATA_PINNED`, **no remaining blockers**.

## 8. Market adapter qualification

**20/20 cells qualified** on real bars (1500 bars from 2022-03-01, development role): no intent during warmup, a finite account trace of the right length, engine fills produced. A-HASH qualifies at the domain level too — its LAB-02 blocker is about ladder fidelity, not about running on real data.

## 9. Honest limits

1. **No backtest has been run and no arm compared.** Nothing here is evidence about edge.
2. **Funding is absent**, so no realistic net-carry claim is possible on this storage.
3. **Basis is BTC-only** and **G3 is BTC/ETH-only**, by collector configuration.
4. **SERVER_LIQUIDITY can never support a historical study** — it is a rolling 30-day window by design.
5. **Instrument metadata is inferred** from observed granularity, not read from venue metadata.
6. **G5 is computed over five assets** — the whole perpetual universe in this storage — so breadth and dispersion are coarse by construction.
7. The `outer_evaluation` role is **not** an untouched holdout; the contamination level remains `RETROSPECTIVE_NESTED_CAUSAL_RESEARCH`.

**Next:** LAB-04 — calendar baseline and robust-neighborhood selection (T29–T36).

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **read-lock** | re-hashing the source files a snapshot was copied from, to detect that upstream changed under a run | LAB-03 — three drift classes; only a CLOSED partition of an immutable product invalidates |
| **open trailing partition** | the current period's file, which the collector is still appending to; it is expected to change and is excluded from a primary read | LAB-03 — 7 partitions at last check |
| **rolling-window product** | a product that prunes and rewrites its own history by design, so it can never be part of an immutable snapshot | LAB-03 — the order book keeps a 30-day window |
| **available_at** | the earliest wall-clock time a value could have been known, = bar_close + publication delay; used instead of the bar label to prevent look-ahead | LAB-03 — bar_close is DERIVED as time + interval because `close_time` is unusable |
| **cohort** | the subset of symbols a feature group can actually cover, given what the collector stored | LAB-03 — G3 (open interest/ratios) covers BTC+ETH only; the primary core is the 8 features covering all five symbols |
