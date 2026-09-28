# MF-01 Run Report — mf01-20260928T122749Z-c5d624ad

## 1. Identity và Scope
- **Study ID**: `btc_regime_forecast_v1`
- **Phase**: `MF-01` (Data qualification, scope và source exclusion)
- **Guide**: `BTC-RPS-V1.2 / MODEL-FIRST + REGIME DURATION`
- **Branch**: `research/btc-regime-forecast-v1` @ `2461f42d1b6c`
- **Timestamp**: `2026-09-28T12:27:49.336712+00:00`
- **Target Market**: Binance BTCUSDT Spot (`CryptoBinanceSpot1m`) as primary reference, Binance USD-M Perp (`CryptoBinance1m`) as spread/context, Binance USD-M Metrics (`BinanceFuturesMetrics5m`) as positioning/leverage enrichment.

## 2. Qualified Sources
| Product ID | Reader Class | Role | Files | Total Bytes | Earliest Bar | Latest Bar |
|---|---|---|---:|---:|---|---|
| `crypto_binance_spot_1m` | `CryptoBinanceSpot1m` | Primary Target & Flow | 104 | 343,730,514 | `2018-01-01 00:00:00` | `2026-08-07 04:13:00` |
| `crypto_binance_futures_1m` | `CryptoBinance1m` | Perpetual Context & Spread | 81 | 241,868,712 | `2020-01-01 00:00:00` | `2026-09-09 20:10:00` |
| `crypto_binance_futures_metrics_5m` | `BinanceFuturesMetrics5m` | Derivatives Positioning | 73 | 36,662,580 | `2020-09-01 00:00:00` | `2026-09-09 15:45:00` |

## 3. Excluded Sources
| Source ID | Status | Reason |
|---|---|---|
| `coingecko_dominance` | `EXCLUDED_INSUFFICIENT_HISTORY` | Public API limited to 365d; historical global market-cap requires Pro license; excluded without blocking core. |
| `binance_btcdom` | `EXCLUDED_NO_PIT` | Relative price strength index, not actual global market-cap dominance. |
| `crypto_binance_orderbook_snapshot_1h` | `EXCLUDED_OUT_OF_SCOPE` | History starts 2023; out of scope for daily macro-regime forecast. |
| `deribit_options` | `EXCLUDED_OUT_OF_SCOPE` | No approved live tail; outside core V1.2 deliverables. |
| `fear_and_greed` | `EXCLUDED_UNAVAILABLE` | External supplemental indicator; default OFF. |
| `funding_rate_raw_rest` | `EXCLUDED_UNAVAILABLE` | No separate canonical reader in [I1]; funding proxy derived from perp klines/metrics. |

## 4. Timeline & Feasibility (§6.2)
- **Feature Warmup**: `2021-07-18` → `2022-01-13` (180 days). 100% covered by Spot (2018), Perp (2020-01), Metrics (2020-09).
- **Initial Training**: `2022-01-14` → `2024-01-13` (730 daily origins). H=90 outcomes mature strictly before Development.
- **Development (Validation)**: `2024-04-13` → `2025-03-08` (12 blocks x 28 days = 336 days, 48 weekly origins).
- **Freeze / Maturity Gap**: `2025-03-08` → `2025-06-07` (91 days gap). All validation outcomes mature before Locked Test.
- **Locked Test**: `2025-06-07` → `2026-05-02` (12 blocks x 28 days = 336 days, 48 weekly origins).
- **Follow-up**: Last test origin 2026-05-02 requires follow-up to `2026-08-01` (H=90). Spot data is closed through `2026-08-06` (5 days safety margin). Fully complete.

## 5. Gate Receipts
- **`G1-SOURCE`**: `PASS`
- **`G1-EXCLUDE`**: `PASS`
- **`G1-TIMELINE`**: `PASS`
- **`G1-EVIDENCE`**: `FAIL`
- **Overall Verdict**: **`FAIL`**

## 6. Financial Authority & WFO Status
- **Financial Authority**: Unmodified `quantbt-engine==1.1.1` (pinned, read-only).
- **Financial Engine Calls**: `0` (Strictly zero engine calls in MF-01..MF-05 per Section 12).
- **WFO Status**: `CLOSED_PENDING_MODEL_QUALIFICATION_AND_OWNER`.
