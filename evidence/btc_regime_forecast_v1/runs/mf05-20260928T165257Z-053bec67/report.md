# Consolidated Final Report: BTCUSDT Regime Forecast Study (MF-01..MF-05)
Study: `btc_regime_forecast_v1`
Run ID: `mf05-20260928T165257Z-053bec67`
Date: `2026-09-28T16:52:57.223568+00:00`
Verdict: **`TECHNICALLY_VALID__ALL_HEADS_NOT_QUALIFIED__WFO_BRIDGE_CLOSED`**

---

## 1. Executive Summary & Core Scientific Findings

Nghiên cứu **`btc_regime_forecast_v1`** (BTC-RPS-V1.2: Model-First Regime Forecasting) đã hoàn thành toàn diện 5 phases (MF-01 đến MF-05) mà **không thực hiện bất kỳ lệnh gọi tài chính nào** (`financial_engine_calls = 0`). Kho QuantBT được bảo vệ nguyên vẹn 100%.

### Phát hiện khoa học trung thực:
1. **Dự báo Biến động (Volatility) trên Locked Test**:
   - Trên Primary Horizon $H^* = 90$ ngày, mô hình `M4_LGBM_CONSERVATIVE_SLOW` với cohort tính năng `D1_DERIVATIVE_LIQUIDITY`:
     - **Brier Skill Score**: **`-0.0118`** so với baseline tần suất lịch sử (95% Block-Bootstrap CI: `[-0.0561, 0.0134]`).
     - **Balanced Accuracy Gain**: **`-0.1062`** (95% CI: `[-0.1667, 0.0496]`).
     - Trạng thái kiểm định: **`NOT_QUALIFIED`** (Không vượt qua ngưỡng qualification bắt buộc BSS >= 0.05 và CI > 0).
2. **Dự báo Hướng đi & Hiệu suất đường đi (Path Efficiency) THẤT BẠI (NOT_QUALIFIED)**:
   - Head Path Efficiency 3-class đạt Brier Skill Score **`-0.3037`** (95% CI: `[-0.7430, -0.0385]`).
   - Tín hiệu dòng tiền phái sinh và định vị vị thế không thể dự báo hướng đi của Bitcoin ở chân trời 90 ngày.
3. **Joint Regime (9-class) THẤT BẠI (NOT_QUALIFIED)**:
   - Do bị kéo xuống bởi cả hai chiều biến động và hiệu suất, Joint 9-class đạt Brier Skill Score **`-0.0277`** (95% CI: `[-0.1278, 0.0501]`).
4. **Trạng thái WFO Bridge: CHÍNH THỨC ĐÓNG (CLOSED)**:
   - Tuân thủ nghiêm ngặt Quy tắc Section 18.1, 9.4, 18.3, 18.5 của Guide: Không có head nào đạt qualification trên Primary Horizon $H^*=90$, việc mở WFO để chọn tham số chiến lược theo regime bị **CẤM HOÀN TOÀN** (`wfo_bridge_status = CLOSED`).
   - Các điều kiện WFO gồm >=128 strategy trials/cutoff, >=12 paired-valid WFO folds, timeline evidence và financial domain gates chưa được đáp ứng trong nghiên cứu model-first này.
   - **Đề xuất có điều kiện**: Đề xuất nghiên cứu "Volatility-Conditioned Regime Selection" (V-CRS-V1) giữ trạng thái `SPECIFIED_NOT_EXECUTED`, cần Owner phê duyệt riêng trước khi thực thi.

---

## 2. Bảng Tổng Hợp 5 Phases & Exit Gates

| Phase | Trọng tâm | Trạng thái Exit Gates | Kết quả chính |
|---|---|---|---|
| **MF-01** | Data Qualification & Scope | **PASS** (5/5) | Binance Spot 1m, Perp 1m, Metrics 5m đủ 2018..2026. G1-COVERAGE pass. Loại bỏ dứt khoát CoinGecko, BTCDOM, L2, Options. |
| **MF-02** | Features, Targets, Duration & Baselines | **PASS** (6/6) | 38 features nhân quả (D0/D1/D2), taxonomy đóng băng trên training prefix 730 ngày, 126 episodes duration ledger, 4 baselines evaluated. |
| **MF-03** | Model Fit & Horizon Selection | **PASS** (6/6) | Ablation chọn D1, Grid 4 LightGBM, Chronos blocked capability, Calibration $T$, chọn $H^*=90$, freeze toàn bộ. |
| **MF-04** | Locked Test & Qualification | **PASS** (6/6) | 48 weekly origins Test (2025-06-07..2026-05-02), 28-day refits từ matured labels. Volatility: NOT_QUALIFIED; Path: NOT_QUALIFIED; Joint: NOT_QUALIFIED. Block bootstrap ceil(H/7) + sensitivities. |
| **MF-05** | Consolidated Report & WFO Bridge | **PASS** (6/6) | Tái lập 100% metrics, đóng gói package, xác định WFO Bridge = **CLOSED**. |

---

## 3. Bàn Giao Thời Lượng (Duration Handoff - Section 4D)
- Primary Detector: `OBS14_CONFIRM3_V1` (14 ngày lookback, 3 ngày confirmation liên tiếp).
- Dwell trung bình trong Test: 11.5 ngày.
- Bàn giao bảng xác suất first-exit và RMRL như bối cảnh thời gian thực nghiệm, **không nhầm lẫn giữa đường cong sinh tồn Kaplan-Meier với kỹ năng dự báo Machine Learning**.

---

## 4. Danh Sách Gói Bàn Giao (Artifacts & Manifests)
Tất cả đã được lưu trữ và đóng băng trong `configs/btc_regime_forecast_v1/`:
1. `MODEL_QUALIFICATION.json`
2. `VERSION_MANIFEST.json`
3. `EXCLUSION_LIST.json`
4. `RESOURCE_SUMMARY.json`
5. `WFO_BRIDGE_DECISION.json`
6. `target_taxonomy.json`
7. `freeze_manifest.json`

Lab đã hoàn thành nhiệm vụ theo chuẩn khoa học cao nhất. Bàn giao đầy đủ cho Owner đưa ra quyết định tiếp theo.
