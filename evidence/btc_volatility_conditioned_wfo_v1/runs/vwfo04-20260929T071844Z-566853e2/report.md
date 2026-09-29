# VWFO-04 Run Report — vwfo04-20260929T071844Z-566853e2

## Identity / scope
- **Phase**: VWFO-04 (Shared policy, streaming replay và operational boundaries)
- **Guide Version**: VOL-WFO-V1.0 (§15, §5.2, §9)
- **Registered Study**: `btc_volatility_conditioned_wfo_v1`
- **Owner Approval Reference**: `dec-vwfo-03-approved-20260929` (VWFO-03->VWFO-04)
- **Execution Mode**: `STREAMING_REPLAY_SHADOW` (Production orders authorized: `False`)
- **Execution Resolution**: 15m decision clock, 1m next-open execution resolution
- **Strategy & Instrument**: A-SC on Binance BTCUSDT Spot/Perpetual

## Câu hỏi và phạm vi được phép
- **Mục tiêu**: Chứng minh policy đã freeze chạy được tuần tự với legal information, không một bản backtest được đơn giản hóa khác live.
- **Điều giữ nguyên**: Toàn bộ model LightGBM H14, taxonomy quantiles, frozen sampler S_TPE, QuantBT engine 1.1.1 read-only.
- **Điều kiểm chuẩn**: Shared decision interface, timing contracts (§5.2), cold recovery, idempotency, fault injection, và financial parity streaming vs batch.

## Planned vs actual
- **Arms evaluated**: 8 arms (`A_M4`, `B0_GLOBAL`, `B_CAP`, `O_PERSIST`, `C_H14`, `P_NI_01`, `P_NI_02`, `P_NI_03`) — 100% symmetric timing contract.
- **Timing contract**: 14-day cadence, 1-day ready lag (`WAIT_FLAT_PREFIX_WITHIN_H14`), 2-day TTL, 28-day max revalidation age.
- **Fault injection suite**: 8/8 fault scenarios successfully evaluated and passed.
- **Streaming vs Batch Parity**: Evaluated on 2,300 real 15m bars (2025-06-01 to 2025-06-25), maximum equity difference `0.00e+00` (strictly $\le 10^{-6}$).
- **QuantBT protected tree**: 100% clean and unmodified.

## Timing & Lifecycle Verification Results
| Dimension | Registered Specification | Replay Status | Result |
|---|---|---|---|
| Common Ready Lag | 1 calendar day | Enforced (`WAIT_FLAT_PREFIX_WITHIN_H14`) | PASS |
| Target Window | 14 calendar days | Strict non-overlapping intervals | PASS |
| Proposal TTL | 2 calendar days post effective | Expired proposals rejected | PASS |
| Max Revalidation Age | 28 calendar days | Triggers `SAFE_ENTRY_PAUSE` | PASS |
| Symmetrical Enforcement | All 8 arms identical | 8/8 arms verified | PASS |
| Idempotency | Dedup by `proposal_id` | Duplicate retry ignored | PASS |
| Incumbent Versioning | Match expected version | Mismatch rejected | PASS |
| Same-param Refresh | Watermark refresh only | Campaign/equity preserved | PASS |

## Fault Injection Summary
- **Total test cases**: 8
- **Passed test cases**: 8 (100%)
- **Cases detail**:
  1. `FAULT-01` (Late arrival): REJECTED (`PROPOSAL_EXPIRED`)
  2. `FAULT-02` (Duplicate proposal retry): IGNORED (`IDEMPOTENT_IGNORED`)
  3. `FAULT-03` (Missing column medians): REJECTED (`MISSING_IMPUTER_MEDIANS`)
  4. `FAULT-04` (Missing temperature scaling): REJECTED (`MISSING_OR_INVALID_TEMPERATURE_SCALING`)
  5. `FAULT-05` (Missing taxonomy quantiles): REJECTED (`MISSING_TAXONOMY_QUANTILES`)
  6. `FAULT-06` (Unknown/Mismatched arm ID): REJECTED (`ARM_MISMATCH`)
  7. `FAULT-07` (Engine order rejection feedback): Cash and position strictly untouched
  8. `FAULT-08` (`SAFE_ENTRY_PAUSE`): New entries blocked, protective exits preserved, zero forced liquidation

## Scoped Streaming vs. Batch Parity
- **Test Dataset**: Real Binance BTCUSDT 15m bars from 2025-06-01 to 2025-06-25 (2304 bars)
- **Max Equity Difference**: `0.00e+00` (Tolerance: `1e-6`)
- **Final Equity Difference**: `0.00e+00`
- **Stream Orders / Fills**: `50` orders / `50` fills
- **Batch Orders / Fills**: `50` orders / `50` fills
- **Parity Verdict**: **PASS**

## Exit Gates Summary
| Gate | Description | Status |
|---|---|---|
| `G4-CLOCKS` | Clocks, target windows, and not-before timing verified | **PASS** |
| `G4-LIFECYCLE` | Proposal lifecycle, idempotency, version matching, expiry verified | **PASS** |
| `G4-PARITY` | Scoped stream vs. batch financial parity (equity path tolerance 1e-6) | **PASS** |
| `G4-RECOVERY` | Recovery from cold restart without state corruption | **PASS** |
| `G4-NO_PRODUCTION_WRITES` | Zero production writes / zero live orders sent / quantbt clean | **PASS** |
| `G4-OWNER` | Owner review to authorize Phase VWFO-05 | **PENDING** |

**Technical Gate**: **PASS**  
**Owner Review**: **PENDING** (Awaiting Owner approval to proceed to Phase VWFO-05: Locked Final WFO, D1/D2 & Conclusion).
