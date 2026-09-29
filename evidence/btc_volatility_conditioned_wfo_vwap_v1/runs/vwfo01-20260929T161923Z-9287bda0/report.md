# VWFO Run Report — vwfo01-20260929T161923Z-9287bda0

## 1. Identity / Scope
- **Study ID**: `btc_volatility_conditioned_wfo_vwap_v1`
- **Phase**: `VWFO-01` (Handoff Acceptance & Financial Boundary Qualification)
- **Run ID**: `vwfo01-20260929T161923Z-9287bda0`
- **Git State**: branch `main`, commit `42251e88aa81097a66e7b89f0495508743a7eda7` (dirty: `True`)
- **Target Alpha / Venue**: `A-VWAP / BTCUSDT / 15m` on Binance
- **Engine Build**: QuantBT `1.1.1` (pinned, read-only)

## 2. Câu hỏi và Phạm vi được phép
- **Mục tiêu**: Tiếp nhận kết quả model dự báo biến động $H=14$, đối soát mâu thuẫn số liệu bàn giao, chuẩn hóa trật tự thời gian (timeline 36 decision points) và kiểm chuẩn miền tài chính (domain contracts) trước khi chạy Walk-Forward Optimization.
- **Quyền hạn**: Chỉ thẩm định và chuẩn bị hợp đồng (0 financial engine runs ngoài microprofile, không live order).

## 3. Planned vs Actual
- **Handoff Reconciliation**: Đã hoàn thành đối soát chi tiết giữa số liệu bảng và ma trận nhầm lẫn.
- **Timeline**: Lập kế hoạch 36 decision points (12 INIT + 12 DEV + 12 FINAL = 504 ngày forward).
- **Domain Qualification**: Kiểm chuẩn thành công dynamic sizing (10%), warmup sạch, next-open execution, và phân loại trạng thái Sharpe.

## 4. Source và Domain Validity
- **Handoff Discrepancy Resolved**:
  - Handoff text ghi Headline: Accuracy `62.5%`, Macro F1 `0.493`, BSS `+0.0791` (thuộc về `std_model`).
  - Handoff text in Ma trận nhầm lẫn: `[[21, 2, 2], [7, 6, 3], [3, 3, 1]]` (tổng đúng 28/48 = `58.33%`, Macro F1 `0.449`, thuộc về `enhanced_model`).
  - Nguyên nhân: Bản tổng kết text lấy headline của mô hình `std_model` nhưng ghép ma trận của `enhanced_model`. Cả 2 mô hình đều có Skill dương (+7.9% và +4.6%) trên tập test OOS 48 tuần.
  - Lựa chọn cho WFO: Chọn mô hình chuẩn 38 features (`std_model`) với BSS cao nhất `+0.0791`.

## 5. Model-to-Action
- **Model Frozen**: LightGBM `M4_LGBM_CONSERVATIVE_SLOW` (num_leaves=7, max_depth=3, lr=0.015, min_child_samples=40, colsample_bytree=0.65).
- **Conditioning**: Tín hiệu $p_{LOW}$ liên tục từ phân phối xác suất 3 lớp [`LOW_VOL`, `MID_VOL`, `HIGH_VOL`].
- **Readiness Policy**: `WAIT_FLAT_PREFIX_WITHIN_H14` giữ vốn phẳng trong thời gian tính toán trước `not_before`.

## 6. Kết quả từng Fold (Timeline Schedule)
- **INIT (12 origins)**: `2024-04-13` đến `2024-09-14`, trưởng thành hoàn toàn vào `2024-09-28`.
- **DEV (12 folds)**: `2024-10-12` đến `2025-03-15`, trưởng thành hoàn toàn vào `2025-03-29`.
- **Freeze Boundary**: Khoảng cách 70 ngày (`2025-03-29` đến `2025-06-07`) để khóa sampler.
- **FINAL (12 folds)**: `2025-06-07` đến `2025-11-08`, trưởng thành vào `2025-11-22`.
- **D2 Continuation**: 28 ngày cho anchor cuối, kết thúc `2025-12-06` (trước giới hạn dữ liệu `2026-08-07`).

## 7. Controls / Limitations
- Tách bạch rõ: Dự báo volatility tốt $
e$ Chọn tham số tốt $
e$ An toàn giao dịch live.
- Không cho phép tăng đòn bẩy hoặc gán TP/SL thủ công theo nhãn biến động trong primary treatment.

## 8. Compute
- Workload: Verification và reconciliation script chạy thuần túy trên CPU (thời gian thực thi < 2 giây, peak RSS < 150 MiB).
- Financial Engine Calls: **0** (QuantBT engine giữ nguyên vẹn 100%).

## 9. So với Run trước
- Đây là run khởi đầu (`VWFO-01`) của nghiên cứu WFO mới `btc_volatility_conditioned_wfo_v1`.
- Cầu nối WFO cũ của H90/H56 giữ nguyên trạng thái `CLOSED`.
- Cầu nối mới cho H14 được đề xuất: `MODEL_HANDOFF_ACCEPTED_H14`.

## 10. Gates và Quyết định
| Gate ID | Expected | Actual | Status |
|---|---|---|---|
| **G1-HANDOFF** | Mâu thuẫn được đối soát, nguồn đầy đủ | Reconciled std_model (62.5%) vs enh_model (58.33%) | **PASS** |
| **G1-FORECAST** | Recipe M4, 38 features, imputation, temp | Verified model_manifest.json | **PASS** |
| **G1-DOMAIN** | Sizing, warmup, next-open, Sharpe typing | All domain checks passed | **PASS** |
| **G1-TIMELINE** | 36 decision points, 504d forward, no overlap | 12 INIT + 12 DEV + 12 FINAL verified | **PASS** |
| **G1-BUDGET** | 128 trials, 0 production writes | Resource budget verified | **PASS** |
| **G1-OWNER** | Owner review | Awaiting Owner review | **PENDING** |

**Technical Gate**: **PASS**  
**Trạng thái tiếp theo**: `WAITING_OWNER_REVIEW` trước khi tiến hành VWFO-02.
