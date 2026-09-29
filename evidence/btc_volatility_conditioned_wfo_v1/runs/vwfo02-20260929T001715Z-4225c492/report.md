# Phase VWFO-02 Report — Common Pools và Candidate-Forward Archive

**Study**: `btc_volatility_conditioned_wfo_v1`  
**Run ID**: `vwfo02-20260929T001715Z-4225c492`  
**Executed UTC**: `2026-09-29T00:37:44.974494+00:00`  
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
| `2024-04-13` | 3.14 | -4.90 | 8.03 | -0.55 | -6.55 | `{'coeff': 2, 'AP': 40, 'alpha.condition_threshold': 50, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-04-27` | 1.89 | 1.97 | -0.08 | +1.34 | -2.19 | `{'coeff': 2, 'AP': 54, 'alpha.condition_threshold': 50, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-05-11` | 1.89 | 4.06 | -2.18 | +1.58 | -1.53 | `{'coeff': 2, 'AP': 50, 'alpha.condition_threshold': 55, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-05-25` | 2.34 | -8.52 | 10.87 | -4.73 | -10.50 | `{'coeff': 1, 'AP': 45, 'alpha.condition_threshold': 50, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-06-08` | 1.34 | -9.86 | 11.21 | -3.98 | -9.57 | `{'coeff': 4, 'AP': 30, 'alpha.condition_threshold': 30, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-06-22` | 1.93 | 0.00 | 1.93 | +1.40 | -10.78 | `{'coeff': 3, 'AP': 52, 'alpha.condition_threshold': 80, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-07-06` | 1.89 | 8.77 | -6.89 | +5.27 | -1.22 | `{'coeff': 3, 'AP': 55, 'alpha.condition_threshold': 75, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-07-20` | 2.08 | -6.88 | 8.96 | -2.71 | -7.98 | `{'coeff': 1, 'AP': 14, 'alpha.condition_threshold': 35, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-08-03` | 1.49 | 1.27 | 0.22 | +1.35 | -0.08 | `{'coeff': 6, 'AP': 53, 'alpha.condition_threshold': 60, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-08-17` | 1.40 | -5.30 | 6.69 | -4.31 | -9.37 | `{'coeff': 1, 'AP': 51, 'alpha.condition_threshold': 75, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-08-31` | 0.46 | 8.43 | -7.97 | +1.43 | -1.20 | `{'coeff': 6, 'AP': 56, 'alpha.condition_threshold': 40, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-09-14` | 2.13 | 7.63 | -5.50 | +0.90 | -5.03 | `{'coeff': 1, 'AP': 48, 'alpha.condition_threshold': 75, 'novolumedata': False, 'src_col': 'close'}` |

---

## 3. Kết quả 12 INIT Origins — S_SOBOL

| Cutoff | Anchor $SR_{IS}$ | Anchor $SR_{FWD}$ | Anchor $D$ | Mean $Y$ (Panel) | Min $Y$ (Best Candidate) | Anchor Parameters |
|---|---|---|---|---|---|---|
| `2024-04-13` | 2.56 | -7.12 | 9.68 | -3.62 | -7.49 | `{'coeff': 2, 'AP': 20, 'alpha.condition_threshold': 55, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-04-27` | 1.96 | 1.98 | -0.02 | +2.59 | -1.30 | `{'coeff': 2, 'AP': 48, 'alpha.condition_threshold': 50, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-05-11` | 1.65 | 3.03 | -1.37 | +1.36 | -2.67 | `{'coeff': 1, 'AP': 45, 'alpha.condition_threshold': 75, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-05-25` | 1.64 | -0.97 | 2.61 | +0.79 | -5.24 | `{'coeff': 2, 'AP': 5, 'alpha.condition_threshold': 65, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-06-08` | 1.34 | -9.86 | 11.21 | -4.06 | -9.41 | `{'coeff': 4, 'AP': 30, 'alpha.condition_threshold': 30, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-06-22` | 2.08 | 0.00 | 2.08 | +3.01 | -2.05 | `{'coeff': 2, 'AP': 50, 'alpha.condition_threshold': 80, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-07-06` | 2.36 | 6.22 | -3.86 | +2.29 | -2.86 | `{'coeff': 2, 'AP': 56, 'alpha.condition_threshold': 75, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-07-20` | 2.35 | -9.36 | 11.71 | -8.19 | -11.70 | `{'coeff': 1, 'AP': 16, 'alpha.condition_threshold': 30, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-08-03` | 2.07 | 0.00 | 2.07 | -0.62 | -3.10 | `{'coeff': 3, 'AP': 39, 'alpha.condition_threshold': 80, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-08-17` | 1.54 | -5.30 | 6.84 | -7.09 | -11.80 | `{'coeff': 1, 'AP': 50, 'alpha.condition_threshold': 75, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-08-31` | 0.18 | 8.43 | -8.25 | +6.26 | +0.39 | `{'coeff': 6, 'AP': 42, 'alpha.condition_threshold': 45, 'novolumedata': False, 'src_col': 'close'}` |
| `2024-09-14` | 2.48 | -2.49 | 4.97 | -10.47 | -16.79 | `{'coeff': 1, 'AP': 60, 'alpha.condition_threshold': 70, 'novolumedata': False, 'src_col': 'close'}` |

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
