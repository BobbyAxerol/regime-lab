# Phase VWFO-02 Report — Common Pools và Candidate-Forward Archive

**Study**: `btc_volatility_conditioned_wfo_v1`  
**Run ID**: `vwfo02-20260929T162753Z-2d738b72`  
**Executed UTC**: `2026-09-29T16:33:27.944508+00:00`  
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
| `2024-04-13` | 2.18 | 0.00 | 2.18 | -1.54 | -3.61 | `{'rsi_len': 45, 'rsi_os': 40, 'rsi_ob': 80, 'dev_mult': 2.1, 'atr_len': 41, 'stop_atr': 8.5, 'target_r': 3.7, 'htf_ema_len': 280, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 25, 'htf_tf': '1h'}` |
| `2024-04-27` | 0.00 | 0.00 | 0.00 | +0.35 | -0.35 | `{'rsi_len': 48, 'rsi_os': 20, 'rsi_ob': 72, 'dev_mult': 3.6, 'atr_len': 12, 'stop_atr': 9.4, 'target_r': 7.2, 'htf_ema_len': 650, 'exit_at_vwap': False, 'time_stop_on': True, 'time_stop_bars': 80, 'htf_tf': '1h'}` |
| `2024-05-11` | -0.24 | 0.00 | -0.24 | +0.81 | -1.74 | `{'rsi_len': 52, 'rsi_os': 45, 'rsi_ob': 76, 'dev_mult': 2.5, 'atr_len': 85, 'stop_atr': 5.3, 'target_r': 6.5, 'htf_ema_len': 160, 'exit_at_vwap': True, 'time_stop_on': True, 'time_stop_bars': 40, 'htf_tf': '1h'}` |
| `2024-05-25` | -1.15 | 0.00 | -1.15 | +1.32 | -0.88 | `{'rsi_len': 52, 'rsi_os': 25, 'rsi_ob': 63, 'dev_mult': 3.0, 'atr_len': 17, 'stop_atr': 3.8000000000000003, 'target_r': 6.5, 'htf_ema_len': 680, 'exit_at_vwap': True, 'time_stop_on': True, 'time_stop_bars': 10, 'htf_tf': '1h'}` |
| `2024-06-08` | 1.34 | 0.00 | 1.34 | -1.72 | -3.38 | `{'rsi_len': 37, 'rsi_os': 37, 'rsi_ob': 65, 'dev_mult': 1.0, 'atr_len': 16, 'stop_atr': 4.7, 'target_r': 6.6000000000000005, 'htf_ema_len': 340, 'exit_at_vwap': True, 'time_stop_on': False, 'time_stop_bars': 25, 'htf_tf': '1h'}` |
| `2024-06-22` | 2.13 | 0.00 | 2.13 | -1.91 | -4.64 | `{'rsi_len': 60, 'rsi_os': 39, 'rsi_ob': 70, 'dev_mult': 1.4, 'atr_len': 27, 'stop_atr': 6.2, 'target_r': 4.6, 'htf_ema_len': 340, 'exit_at_vwap': True, 'time_stop_on': False, 'time_stop_bars': 55, 'htf_tf': '1h'}` |
| `2024-07-06` | -1.37 | 0.00 | -1.37 | +1.16 | -0.99 | `{'rsi_len': 38, 'rsi_os': 24, 'rsi_ob': 63, 'dev_mult': 4.0, 'atr_len': 21, 'stop_atr': 3.7, 'target_r': 4.2, 'htf_ema_len': 380, 'exit_at_vwap': False, 'time_stop_on': True, 'time_stop_bars': 10, 'htf_tf': '1h'}` |
| `2024-07-20` | 0.11 | 0.00 | 0.11 | +0.04 | -5.50 | `{'rsi_len': 48, 'rsi_os': 16, 'rsi_ob': 55, 'dev_mult': 3.2, 'atr_len': 35, 'stop_atr': 2.3, 'target_r': 5.800000000000001, 'htf_ema_len': 370, 'exit_at_vwap': True, 'time_stop_on': True, 'time_stop_bars': 70, 'htf_tf': '1h'}` |
| `2024-08-03` | 0.00 | 0.00 | 0.00 | +0.12 | -1.83 | `{'rsi_len': 74, 'rsi_os': 31, 'rsi_ob': 56, 'dev_mult': 4.6000000000000005, 'atr_len': 23, 'stop_atr': 3.0, 'target_r': 9.9, 'htf_ema_len': 310, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 60, 'htf_tf': '1h'}` |
| `2024-08-17` | 0.04 | 0.00 | 0.04 | -0.05 | -1.95 | `{'rsi_len': 26, 'rsi_os': 39, 'rsi_ob': 82, 'dev_mult': 4.4, 'atr_len': 51, 'stop_atr': 3.0, 'target_r': 8.100000000000001, 'htf_ema_len': 500, 'exit_at_vwap': False, 'time_stop_on': True, 'time_stop_bars': 5, 'htf_tf': '1h'}` |
| `2024-08-31` | 0.00 | 0.00 | 0.00 | -0.38 | -1.93 | `{'rsi_len': 17, 'rsi_os': 15, 'rsi_ob': 84, 'dev_mult': 1.4, 'atr_len': 32, 'stop_atr': 7.0, 'target_r': 6.300000000000001, 'htf_ema_len': 370, 'exit_at_vwap': True, 'time_stop_on': False, 'time_stop_bars': 5, 'htf_tf': '1h'}` |
| `2024-09-14` | 0.35 | 0.00 | 0.35 | -0.31 | -2.04 | `{'rsi_len': 74, 'rsi_os': 15, 'rsi_ob': 55, 'dev_mult': 2.1, 'atr_len': 13, 'stop_atr': 4.0, 'target_r': 6.0, 'htf_ema_len': 260, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 15, 'htf_tf': '1h'}` |

---

## 3. Kết quả 12 INIT Origins — S_SOBOL

| Cutoff | Anchor $SR_{IS}$ | Anchor $SR_{FWD}$ | Anchor $D$ | Mean $Y$ (Panel) | Min $Y$ (Best Candidate) | Anchor Parameters |
|---|---|---|---|---|---|---|
| `2024-04-13` | -1.49 | 0.00 | -1.49 | +1.93 | +0.06 | `{'rsi_len': 62, 'rsi_os': 22, 'rsi_ob': 64, 'dev_mult': 2.3, 'atr_len': 6, 'stop_atr': 9.3, 'target_r': 7.4, 'htf_ema_len': 550, 'exit_at_vwap': True, 'time_stop_on': True, 'time_stop_bars': 60, 'htf_tf': '1h'}` |
| `2024-04-27` | 0.00 | 0.00 | 0.00 | -0.08 | -2.66 | `{'rsi_len': 55, 'rsi_os': 28, 'rsi_ob': 67, 'dev_mult': 3.6, 'atr_len': 49, 'stop_atr': 2.2, 'target_r': 1.6, 'htf_ema_len': 450, 'exit_at_vwap': False, 'time_stop_on': True, 'time_stop_bars': 75, 'htf_tf': '1h'}` |
| `2024-05-11` | 0.00 | 0.00 | 0.00 | +0.62 | -0.43 | `{'rsi_len': 57, 'rsi_os': 50, 'rsi_ob': 81, 'dev_mult': 4.1, 'atr_len': 35, 'stop_atr': 2.3, 'target_r': 4.6, 'htf_ema_len': 30, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 120, 'htf_tf': '1h'}` |
| `2024-05-25` | 0.00 | 0.00 | 0.00 | -0.24 | -2.37 | `{'rsi_len': 58, 'rsi_os': 27, 'rsi_ob': 69, 'dev_mult': 2.4000000000000004, 'atr_len': 76, 'stop_atr': 1.8, 'target_r': 7.300000000000001, 'htf_ema_len': 340, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 100, 'htf_tf': '1h'}` |
| `2024-06-08` | 2.58 | 0.00 | 2.58 | -2.66 | -4.59 | `{'rsi_len': 13, 'rsi_os': 18, 'rsi_ob': 69, 'dev_mult': 3.1, 'atr_len': 30, 'stop_atr': 7.7, 'target_r': 6.9, 'htf_ema_len': 90, 'exit_at_vwap': True, 'time_stop_on': True, 'time_stop_bars': 25, 'htf_tf': '1h'}` |
| `2024-06-22` | 0.60 | -5.30 | 5.90 | -6.03 | -8.00 | `{'rsi_len': 19, 'rsi_os': 25, 'rsi_ob': 59, 'dev_mult': 1.5, 'atr_len': 74, 'stop_atr': 7.7, 'target_r': 1.8, 'htf_ema_len': 50, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 115, 'htf_tf': '1h'}` |
| `2024-07-06` | 0.00 | 0.00 | 0.00 | -0.65 | -5.70 | `{'rsi_len': 67, 'rsi_os': 19, 'rsi_ob': 73, 'dev_mult': 3.7, 'atr_len': 19, 'stop_atr': 7.5, 'target_r': 1.2, 'htf_ema_len': 90, 'exit_at_vwap': True, 'time_stop_on': True, 'time_stop_bars': 95, 'htf_tf': '1h'}` |
| `2024-07-20` | 0.00 | 0.00 | 0.00 | +0.14 | -3.50 | `{'rsi_len': 67, 'rsi_os': 16, 'rsi_ob': 68, 'dev_mult': 4.0, 'atr_len': 41, 'stop_atr': 3.7, 'target_r': 5.9, 'htf_ema_len': 560, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 5, 'htf_tf': '1h'}` |
| `2024-08-03` | 0.00 | 0.00 | 0.00 | +0.32 | -2.18 | `{'rsi_len': 58, 'rsi_os': 35, 'rsi_ob': 83, 'dev_mult': 2.4000000000000004, 'atr_len': 8, 'stop_atr': 6.5, 'target_r': 1.7000000000000002, 'htf_ema_len': 270, 'exit_at_vwap': True, 'time_stop_on': False, 'time_stop_bars': 65, 'htf_tf': '1h'}` |
| `2024-08-17` | 2.29 | 0.00 | 2.29 | -2.26 | -7.04 | `{'rsi_len': 59, 'rsi_os': 39, 'rsi_ob': 82, 'dev_mult': 1.2000000000000002, 'atr_len': 55, 'stop_atr': 2.7, 'target_r': 6.800000000000001, 'htf_ema_len': 230, 'exit_at_vwap': False, 'time_stop_on': True, 'time_stop_bars': 5, 'htf_tf': '1h'}` |
| `2024-08-31` | 0.00 | 0.00 | 0.00 | -0.26 | -2.59 | `{'rsi_len': 30, 'rsi_os': 10, 'rsi_ob': 88, 'dev_mult': 5.0, 'atr_len': 81, 'stop_atr': 3.2, 'target_r': 8.100000000000001, 'htf_ema_len': 150, 'exit_at_vwap': True, 'time_stop_on': False, 'time_stop_bars': 40, 'htf_tf': '1h'}` |
| `2024-09-14` | 0.59 | 0.00 | 0.59 | -1.22 | -5.93 | `{'rsi_len': 57, 'rsi_os': 36, 'rsi_ob': 58, 'dev_mult': 0.7, 'atr_len': 11, 'stop_atr': 3.4000000000000004, 'target_r': 8.5, 'htf_ema_len': 400, 'exit_at_vwap': True, 'time_stop_on': True, 'time_stop_bars': 35, 'htf_tf': '1h'}` |

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
