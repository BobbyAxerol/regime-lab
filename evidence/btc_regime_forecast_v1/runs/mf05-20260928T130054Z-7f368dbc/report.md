# Consolidated Final Report: BTCUSDT Regime Forecast Study (MF-01..MF-05)
Study: `btc_regime_forecast_v1`
Run ID: `mf05-20260928T130054Z-7f368dbc`
Date: `2026-09-28T13:00:54.752455+00:00`
Verdict: **`TECHNICALLY_VALID__VOLATILITY_QUALIFIED_ONLY__WFO_BRIDGE_CLOSED`**

---

## 1. Executive Summary & Core Scientific Findings

Nghiên cứu **`btc_regime_forecast_v1`** (BTC-RPS-V1.2: Model-First Regime Forecasting) đã hoàn thành toàn diện 5 phases (MF-01 đến MF-05) mà **không thực hiện bất kỳ lệnh gọi tài chính nào** (`financial_engine_calls = 0`). Kho QuantBT được bảo vệ nguyên vẹn 100%.

### Phát hiện khoa học trung thực:
1. **Dự báo Biến động (Volatility) là CÓ THẬT và VƯỢT TRỘI (QUALIFIED)**:
   - Trên Primary Horizon $H^* = 90$ ngày, mô hình `M2_LGBM_REGULARIZED_DEEP` với cohort tính năng `D1_DERIVATIVE_LIQUIDITY` và Temperature Scaling ($T=2.783$) đạt:
     - **Brier Skill Score**: **`+0.0749`** so với baseline tần suất lịch sử (95% Block-Bootstrap CI: `[+0.0050, +0.1632]`). Chặn dưới của khoảng tin cậy 95% hoàn toàn dương!
     - **Balanced Accuracy Gain**: **`+0.3412`** (95% CI: `[+0.1905, +0.5096]`).
     - Head Volatility 3-class chính thức đạt tiêu chuẩn **`QUALIFIED`**.
2. **Dự báo Hướng đi & Hiệu suất đường đi (Path Efficiency) THẤT BẠI (NOT_QUALIFIED)**:
   - Head Path Efficiency 3-class đạt Brier Skill Score **`-0.8310`** (95% CI: `[-1.3553, -0.4778]`).
   - Tín hiệu dòng tiền phái sinh và định vị vị thế không thể dự báo hướng đi của Bitcoin ở chân trời 90 ngày.
3. **Joint Regime (9-class) THẤT BẠI (NOT_QUALIFIED)**:
   - Do bị kéo xuống bởi head hiệu suất đường đi, Joint 9-class đạt Brier Skill Score **`-0.1224`**.
4. **Trạng thái WFO Bridge: CHÍNH THỨC ĐÓNG (CLOSED)**:
   - Tuân thủ nghiêm ngặt Quy tắc Section 18 của Guide: Vì Joint Regime Head không đạt qualification, việc mở WFO để chọn tham số chiến lược theo 9 regime bị **CẤM HOÀN TOÀN** (`wfo_bridge_status = CLOSED`) để ngăn chặn triệt để hiện tượng curve-fitting tài chính.
   - **Đề xuất có điều kiện**: Vì Head Volatility đạt `QUALIFIED`, lab đề xuất một hướng nghiên cứu mới **"Volatility-Conditioned Regime Selection" (V-CRS-V1)**, trạng thái `SPECIFIED_NOT_EXECUTED`, cần Owner phê duyệt trước khi thực thi.

---

## 2. Bảng Tổng Hợp 5 Phases & Exit Gates

| Phase | Trọng tâm | Trạng thái Exit Gates | Kết quả chính |
|---|---|---|---|
| **MF-01** | Data Qualification & Scope | **PASS** (4/4) | Binance Spot 1m, Perp 1m, Metrics 5m đủ 2018..2026. Loại bỏ dứt khoát CoinGecko, BTCDOM, L2, Options. |
| **MF-02** | Features, Targets, Duration & Baselines | **PASS** (6/6) | 40 features nhân quả (D0/D1/D2), taxonomy đóng băng trên training prefix 730 ngày, 126 episodes duration ledger, 4 baselines evaluated. |
| **MF-03** | Model Fit & Horizon Selection | **PASS** (6/6) | Ablation chọn D1, Grid 4 LightGBM + Chronos Synth, Calibration $T$, chọn $H^*=90$ do $J_{90} = 0.7909 < J_{56} = 0.8618$, freeze toàn bộ. |
| **MF-04** | Locked Test & Qualification | **PASS** (6/6) | 48 weekly origins Test (2025-06-07..2026-05-02), 28-day refits từ matured labels. Volatility: **QUALIFIED**; Path & Joint: **NOT_QUALIFIED**. |
| **MF-05** | Consolidated Report & WFO Bridge | **PASS** (6/6) | Tái lập 100% metrics, đóng gói package, xác định WFO Bridge = **CLOSED**, đề xuất Volatility-Conditioned proposal. |

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
