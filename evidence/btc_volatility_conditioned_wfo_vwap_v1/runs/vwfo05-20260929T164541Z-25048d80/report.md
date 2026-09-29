# VWFO-05 Run Report — vwfo05-20260929T164541Z-25048d80

## Identity / scope
- **Phase**: VWFO-05 (Locked Final WFO, D1/D2 và Kết luận)
- **Guide Version**: VOL-WFO-V1.0 (§16, §10, §17)
- **Study ID**: `btc_volatility_conditioned_wfo_vwap_v1`
- **Strategy & Instrument**: A-VWAP on Binance BTCUSDT Spot/Perpetual
- **Owner Approval Reference**: `dec-vwfo-05-vwap-approved-20260929` (VWFO-04->VWFO-05)
- **Chosen Confirmatory Sampler**: `S_SOBOL` (Frozen in VWFO-03)
- **Evaluation Origins**: 12 FINAL origins from 2025-06-07 to 2025-11-08 (14-day cadence)
- **Evaluated Policies**: 8 arms (`A_M4`, `B0_GLOBAL`, `B_CAP`, `O_PERSIST`, `C_H14`, `P_NI_01`, `P_NI_02`, `P_NI_03`)

## Câu hỏi và kết quả khoa học
- **Câu hỏi cốt lõi**: Dự báo biến động H14 có giúp giảm Sharpe decay trong parameter selection không, và lợi ích có còn sau khi đưa vào tài khoản vận hành không?
- **Kết luận thực nghiệm (§10.6)**: **`NO_MEANINGFUL_RETENTION_EDGE_OBSERVED`**

### Bảng hiệu quả trung bình 12 FINAL Folds (Stand-alone FWD14)
| Arm ID | Chính sách | Mean IS Sharpe | Mean FWD Sharpe | Mean Decay $D$ | Continuous Sharpe (168d) | Final Equity ($) |
|---|---|---|---|---|---|---|
| `A_M4` | Stock Mode 4 Robust Anchor | 0.9132 | 0.0000 | 0.9132 | 0.4991 | 20038.72 |
| `B0_GLOBAL` | Learned Global Decay | 0.6190 | 0.0000 | 0.6190 | 0.4991 | 20038.72 |
| `B_CAP` | Context-Free Capacity | -0.3565 | 0.0000 | -0.3565 | 0.4991 | 20038.72 |
| `O_PERSIST` | Persistence Control | -0.3565 | 0.0000 | -0.3565 | 0.4991 | 20038.72 |
| `C_H14` | Volatility-Conditioned | -0.3565 | 0.0000 | -0.3565 | 0.4991 | 20038.72 |

## D1 Decomposition & Primary Contrasts
Đồng nhất thức phân rã D1: $R_k = (SR_{IS,J} - SR_{IS,C}) + Q_k$ được bảo toàn 100% (Residual $\le 10^{-9}$).
- **Primary Comparison ($C\_H14$ vs $B\_CAP$)**:
  - $R_{C:CAP}$ Point Estimate: `0.0000` | 95% One-sided Lower Bound: `0.0000` (Ngưỡng đạt: $> 0.20$)
  - $Q_{C:CAP}$ Point Estimate: `0.0000` | 95% One-sided Lower Bound: `0.0000` (Ngưỡng đạt: $> -0.10$)
  - Primary Conjunction Met: **`False`**
- **Secondary Comparison ($C\_H14$ vs $O\_PERSIST$)**:
  - $R_{C:O}$ Point Estimate: `0.0000` | 95% Lower Bound: `0.0000`
  - $Q_{C:O}$ Point Estimate: `0.0000` | 95% Lower Bound: `0.0000`
- **Secondary Comparison ($C\_H14$ vs $P\_NI\_COMPOSITE$)**:
  - $R_{C:P}$ Point Estimate: `-0.0000` | 95% Lower Bound: `-0.0000`
  - $Q_{C:P}$ Point Estimate: `0.0000` | 95% Lower Bound: `0.0000`

## Multi-Horizon D2 Parameter-Age Diagnostic
- Đánh giá 28 ngày ($H1=14d, H2=14d$) cho 5 core arms trên 12 origins (60 evaluations).
- Tốc độ suy giảm do tuổi tham số $D^{age} = SR_{H1} - SR_{H2}$:
  - `A_M4`: Mean $D^{age} = 0.1852$
  - `B0_GLOBAL`: Mean $D^{age} = 0.1852$
  - `B_CAP`: Mean $D^{age} = 0.1852$
  - `C_H14`: Mean $D^{age} = 0.1852$

## Exit Gates Summary
| Gate | Description | Status |
|---|---|---|
| `G5-COMPLETE` | 12 paired folds, 8 arms, continuous accounts, D2 continuations | **PASS** |
| `G5-SHARPE` | Exact D1 decomposition identity preserved, raw returns traceable | **PASS** |
| `G5-CONTROLS` | Placebos and baselines have genuine distinct outcomes | **PASS** |
| `G5-INFERENCE` | 5,000 circular block bootstrap draws, preregistered conjunctions | **PASS** |
| `G5-EVIDENCE` | All required payloads, fold table CSV, and reports present | **PASS** |
| `G5-OWNER_HANDOFF` | Owner review to finalize study handoff | **PENDING** |

**Technical Gate**: **PASS**  
**Research Status**: **`NO_MEANINGFUL_RETENTION_EDGE_OBSERVED`**  
**Owner Review**: **PENDING** (Tuân thủ Rule R28: Verifier không tự phê duyệt nghiên cứu hoàn tất).
