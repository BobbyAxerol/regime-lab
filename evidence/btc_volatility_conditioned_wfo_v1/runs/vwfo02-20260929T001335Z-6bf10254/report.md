# Phase VWFO-02 Report — Common Pools và Candidate-Forward Archive

**Study**: `btc_volatility_conditioned_wfo_v1`  
**Run ID**: `vwfo02-20260929T001335Z-6bf10254`  
**Executed UTC**: `2026-09-29T00:14:46.232307+00:00`  
**Status**: `technical_gate: PASS` | `implementation_status: COMPLETE` | `owner_review: WAITING_OWNER_REVIEW`  

---

## 1. Mục tiêu và Phạm vi

Phase VWFO-02 đã thực hiện đầy đủ các yêu cầu theo Section 13 của Guide `VOL-WFO-V1.0`:
1. **Sampler Qualification & Injection**: Cấu hình và chứng thực thành công 2 samplers `S_TPE` (`optuna.samplers.TPESampler`) và `S_SOBOL` (`optuna.samplers.QMCSampler(qmc_type="sobol")`) với $128$ attempted trials/cutoff.
2. **IS180 Search & Stock Mode 4 Anchor**: Chạy $128$ trials trên $12$ INIT origins cho cả 2 samplers ($2 \times 12 = 24$ searches). Chấm điểm Mode 4 temporal robustness trên 6 subperiods; trích xuất anchor stock Mode 4 chuẩn (`select_is_only_robust_record`), không dùng `argmax(IS_Sharpe)`.
3. **Base Panel Selection**: Chọn base panel tối đa $16$ ứng viên theo luật IS-only (Anchor, Top IS Sharpe, Parameter Diversity, Control Mid/Low).
4. **QuantBT FWD14 Evaluation & Labels**: Chạy backtest trên FWD14 bằng QuantBT native event account; tính toán nhãn suy giảm Sharpe $D_{k,\theta} = SR_{IS} - SR_{FWD}$ và suy giảm tương đối $Y_{k,\theta} = D_{k,\theta} - D_{k,a}$ (với $Y_{k,anchor} = 0.0$ theo đẳng thức cấu trúc).
5. **Shared Candidate Archive**: Lưu trữ toàn bộ kết quả với mốc thời gian `matured_at = origin + 14d`, bảo đảm cách ly nhân quả tuyệt đối (`as_of <= matured_at`).
6. **Semantic Reuse**: Chứng minh cache hit khi chạy lại cấu hình đồng nhất và cache miss khi thay đổi tham số kinh tế.

---

## 2. Kết quả 12 INIT Origins — S_TPE

| Cutoff | Anchor $SR_{IS}$ | Anchor $SR_{FWD}$ | Anchor $D$ | Mean $Y$ (Panel) | Min $Y$ (Best Candidate) | Anchor Parameters |
|---|---|---|---|---|---|---|
| `2024-04-13` | 2.26 | -7.02 | 9.28 | -4.87 | -8.46 | `{'coeff': 2, 'AP': 25, 'alpha.condition_threshold': 55, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-04-27` | 1.71 | 0.37 | 1.34 | +0.79 | -3.62 | `{'coeff': 2, 'AP': 51, 'alpha.condition_threshold': 45, 'novolumedata': False, 'src_col': 'close'}` |

---

## 3. Kết quả 12 INIT Origins — S_SOBOL

| Cutoff | Anchor $SR_{IS}$ | Anchor $SR_{FWD}$ | Anchor $D$ | Mean $Y$ (Panel) | Min $Y$ (Best Candidate) | Anchor Parameters |
|---|---|---|---|---|---|---|
| `2024-04-13` | 2.58 | -6.87 | 9.46 | -4.81 | -7.15 | `{'coeff': 2, 'AP': 17, 'alpha.condition_threshold': 50, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-04-27` | 1.38 | 0.76 | 0.62 | +1.51 | -0.94 | `{'coeff': 2, 'AP': 55, 'alpha.condition_threshold': 40, 'novolumedata': False, 'src_col': 'close'}` |

---

## 4. Kiểm chuẩn Reuse & Caching (Exit Gate G2-REUSE)

- **Identical Search Cache Hit**: `True` (Tái sử dụng $100\%$ kết quả tính toán đã có, 0 engine backtests mới).
- **Fee Alteration Cache Miss**: `True` (Thay đổi fee từ $0.0004$ lên $0.0008$ kích hoạt tính toán mới hợp lệ).
- **No Future Leakage**: `True` (Truy vấn archive tại origin không bao giờ thấy nhãn tương lai chưa trưởng thành).

---

## 5. Tổng kết Exit Gates Phase VWFO-02

| Gate | Mô tả | Trạng thái | Ghi chú |
|---|---|---|---|
| `G2-MODE4` | Stock Mode 4 robust selector anchor | **PASS** | 24/24 searches có Mode 4 anchor hợp lệ, không dùng argmax |
| `G2-POOL` | Full candidate pool & base panel | **PASS** | $128$ trials attempted/pool, panel $\le 16$, đa dạng hóa tham số |
| `G2-INIT12` | 12 INIT origins hoàn tất | **PASS** | $12/12$ origins cho cả TPE và Sobol ($24$ pools hoàn chỉnh) |
| `G2-LABELS` | FWD14 QuantBT paths & D/Y labels | **PASS** | $D$ và $Y$ đối soát hoàn hảo; $Y_{anchor} = 0.0$ cấu trúc |
| `G2-REUSE` | Semantic cache & cross-run reuse | **PASS** | Cache hit khi đồng nhất, miss khi đổi phí, bảo vệ nhân quả |
| `G2-REPORT_OWNER` | Báo cáo chi tiết & chờ duyệt | **PASS** | Đầy đủ `report.md`, `gate_receipt.json`, chuyển `WAITING_OWNER_REVIEW` |

---

## 6. Trạng thái Bàn giao

Hệ thống đã hoàn tất Phase VWFO-02 với **Technical Gate: PASS**.  
Toàn bộ Candidate Archive với 12 matured origins đã sẵn sàng để Phase VWFO-03 phát triển các mô hình Meta-Selector ($B_0, B_{CAP}, O, C_{H14}, P$) và khóa một Sampler tối ưu.  
Tuân thủ Rule R28: Trạng thái hiện tại được đặt là **`WAITING_OWNER_REVIEW`**.
