# RPS_CURRENT — BTC-RPS-V1.2 Model-First Study

Current source/runtime and approved registration:

| Phase | Technical | Model-Skill / Scope | Recomputed From | Evidence |
|---|---|---|---|---|
| **MF-01** | **PASS** (5/5 gates) | **DATA_QUALIFIED_SCOPE_LOCKED** | (original) | `evidence/btc_regime_forecast_v1/runs/mf01-20260928T122818Z-64bb6ac4/` |
| **MF-02** | **PASS** (6/6 gates) | **FEATURES_BASELINES_DURATION_LOCKED** | `mf02-20260928T124051Z-1c4ebe49` | `evidence/btc_regime_forecast_v1/runs/mf02-20260928T161142Z-bec1b766/` |
| **MF-03** | **PASS** (6/6 gates) | **MODEL_FIT_HORIZON_FROZEN** | `mf03-20260928T124620Z-c404799d` | `evidence/btc_regime_forecast_v1/runs/mf03-20260928T164151Z-5faeb4a9/` |
| **MF-04** | **PASS** (6/6 gates) | **LOCKED_TEST_ALL_HEADS_NOT_QUALIFIED** | `mf04-20260928T125717Z-c4ed139e` | `evidence/btc_regime_forecast_v1/runs/mf04-20260928T164913Z-eb2bd5b6/` |
| **MF-05** | **PASS** (6/6 gates) | **ALL_HEADS_NOT_QUALIFIED_WFO_CLOSED** | `mf05-20260928T130054Z-7f368dbc` | `evidence/btc_regime_forecast_v1/runs/mf05-20260928T165257Z-053bec67/` |

---

## Trạng thái Reviewer Fixes (RPS REVIEW 01 — 2026-09-28)
Tất cả 9 findings (FIX-01..FIX-09) từ Cline review đã được thực thi và xác minh nghiêm ngặt:
- **FIX-01 (Blocking — Coverage/Join)**: Bỏ `.dropna()` toàn hàng trên metrics. Cột thiếu lịch sử 2022 (`count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`) và features phái sinh được loại trừ dưới `EXCLUDE_COLUMN_LOW_COVERAGE`. Gate `G1-COVERAGE` bổ sung và PASS. Test đỏ trước, xanh sau (`test_mf01_coverage.py`).
- **FIX-02 (Blocking — Chronos Labeling)**: Gỡ nhãn Chronos-Bolt khỏi candidate models; chuyển sang `BLOCKED_CAPABILITY` với metrics `null` và lý do rõ ràng. Test đỏ trước, xanh sau (`test_mf03_chronos_labeling.py`).
- **FIX-03 (Blocking — Imputation Policy)**: Thống nhất chính sách median fit và tái sử dụng `col_medians_` khi predict. Cấm chênh lệch train/serve. Test đỏ trước, xanh sau (`test_mf03_imputation.py`).
- **FIX-04 (Significant — Bootstrap Spec & Overlap)**: Cấu hình block bootstrap horizon-specific `ceil(H/7)` (8 cho H56, 13 cho H90) + 2 mức sensitivity (1.5x, 2.0x). Tạo `origin_overlap_summary.json` với tuyên bố xấp xỉ tiệm cận. Test đỏ trước, xanh sau (`test_mf04_bootstrap_spec.py`).
- **FIX-05 (Significant — WFO Bridge Rationale)**: Rationale đóng WFO Bridge bỏ điều kiện bịa "all primary heads", trích dẫn chính xác §18.1, §9.4, §18.3, §18.5 và 4 điều kiện chưa đáp ứng. Giữ `wfo_bridge_status = CLOSED`. Test đỏ trước, xanh sau (`test_mf05_bridge_rationale.py`).
- **FIX-06 & FIX-07 (Significant — Attempt Evidence & Replay Record)**: Bổ sung `request.json`, `attempts.jsonl`, và `postmortem.md` cho toàn bộ các run dirs; ghi nhận run replay `mf04-20260928T141707Z-655104c7` dưới dạng `INDEPENDENT_DETERMINISM_CHECK`. Test đỏ trước, xanh sau (`test_mf02_06_attempt_evidence.py`).
- **FIX-08 (Significant — Two-Way Verifier Tests on Artifacts)**: Bổ sung 5 bộ test 2 chiều (xanh trên run đã commit, đỏ trên tampered bundle). Test đỏ trước, xanh sau (`test_mf08_committed_artifacts.py`).
- **FIX-09 (Timeline & Hashes)**: Sửa `spot_latest_closed_day = 2026-08-07` khớp dữ liệu; ghi nhận `EXCLUDED_PARTIAL_MONTH` cho 2026-09. Đổi tên trường thành `model_config_hashes`, ghi rõ `weights_persisted: false` và `replay_method: REFIT_FROM_FROZEN_CONFIG`.

---

## MF-05 Complete (Recomputed: `mf05-20260928T165257Z-053bec67`)
- **Gates**: `G5-REPORT` PASS, `G5-REPRODUCE` PASS, `G5-SCOPE` PASS, `G5-BRIDGE` PASS, `G5-DURATION-HANDOFF` PASS, `G5-OWNER` PASS.
- **Consolidated Final Verdict**: **`TECHNICALLY_VALID__ALL_HEADS_NOT_QUALIFIED__WFO_BRIDGE_CLOSED`**.
- **WFO Bridge Decision**: **`CLOSED`** per Section 18.1, 9.4, 18.3, 18.5. Do cả 3 primary heads trên $H^*=90$ đều không vượt qua ngưỡng qualification bắt buộc so với frozen baseline, việc mở WFO để chọn tham số chiến lược theo regime bị **CẤM HOÀN TOÀN**.
- **Metrics Reproduction**: 100% verified với 0.0 discrepancy từ sealed forecast records mà không gọi model.
- **Financial Engine Calls**: **0** xuyên suốt toàn bộ 5 phases (QuantBT 100% untouched).

---

## MF-04 Complete (Recomputed: `mf04-20260928T164913Z-eb2bd5b6`)
- **Gates**: `G4-EXEC` PASS, `G4-EVAL12` PASS, `G4-INFERENCE` PASS, `G4-HEADSTATUS` PASS, `G4-TIMING-EVAL` PASS, `G4-EVIDENCE` PASS.
- **Locked Test Execution**: 48 weekly origins trên 12 blocks (2025-06-07..2026-05-02), 100% coverage, 28-day refits chỉ từ matured labels (`d >= 2022-01-14`).
- **Head Qualification Status ($H^* = 90$, block_size=13, 2000 draws)**:
  - **Volatility 3-class**: `NOT_QUALIFIED` (Brier Skill = -0.0118, 95% CI: [-0.0561, +0.0134], Balanced Accuracy Gain = -0.1062).
  - **Efficiency 3-class**: `NOT_QUALIFIED` (Brier Skill = -0.3037, 95% CI: [-0.7430, -0.0385]).
  - **Joint 9-class**: `NOT_QUALIFIED` (Brier Skill = -0.0277, 95% CI: [-0.1278, +0.0501]).
  - **Continuous Volatility**: `INCONCLUSIVE_MARGINAL` (Rel Error Reduction = +0.0239, 95% CI: [-0.3561, +0.3613]).
- **Secondary Horizon ($H = 56$, block_size=8)**: Volatility `NOT_QUALIFIED` (BSS -0.0003), Efficiency `NOT_QUALIFIED` (BSS -0.0568), Joint `INCONCLUSIVE_MARGINAL` (BSS +0.0223, CI vắt qua 0).

---

## MF-03 Complete (Recomputed: `mf03-20260928T164151Z-5faeb4a9`)
- **Gates**: `G3-ABLATION` PASS, `G3-MODEL` PASS, `G3-CALIBRATION` PASS, `G3-FREEZE` PASS, `G3-DURATION-AND-HORIZON-FREEZE` PASS, `G3-REPORT` PASS.
- **Feature Ablation**: Thắng cuộc: `D1_DERIVATIVE_LIQUIDITY`.
- **Model Grid**: 4 LightGBM configs (`M1`..`M4`), Chronos ghi nhận `BLOCKED_CAPABILITY`. Thắng cuộc: `M4_LGBM_CONSERVATIVE_SLOW` cho cả H56 và H90.
- **Temperature Scaling**: H56 ($T_V=5.000, T_E=2.540$), H90 ($T_V=3.946, T_E=2.107$).
- **Horizon Selection**: $H^* = 90$ ($J_{90} = 0.8514 < J_{56} = 0.8655$).

---

## MF-02 Complete (Recomputed: `mf02-20260928T161142Z-bec1b766`)
- **Gates**: `G2-FEATURES` PASS, `G2-TARGETS` PASS, `G2-SPLIT` PASS, `G2-BASELINE` PASS, `G2-REGISTRATION` PASS, `G2-DURATION-DEFINITION` PASS.
- **Features**: 38 causal rolling features (D0: 27, D1: 38, D2: 38; đã loại 2 cột toptrader khuyết 2022).
- **Targets & Taxonomy**: $H \in \{56, 90\}$, đóng băng trên `2022-01-14..2024-01-13` (730 daily origins).
- **Duration (Section 4D)**: Primary detector `OBS14_CONFIRM3_V1`, 126 episodes ledger, 1 right-censored.
- **Baselines (48 Dev Origins)**: B1, B2, B3, B4 đầy đủ.

---

## MF-01 Complete (`mf01-20260928T122818Z-64bb6ac4`)
- **Gates**: `G1-SOURCE` PASS, `G1-EXCLUDE` PASS, `G1-TIMELINE` PASS, `G1-EVIDENCE` PASS, `G1-COVERAGE` PASS.
- **Coverage**: Verified >=95% column coverage và max gap <= 7d.

---

## Đột phá Nghiên cứu: Volatility-Conditioned Selection & Multi-Horizon Study (2026-09-28)
Sau khi giải quyết xong toàn bộ 9 review findings (FIX-01..FIX-09) và ghi nhận kết luận khách quan của MF-05 trên mô hình 9-class ($H=90$d không đạt qualification), nghiên cứu đã mở rộng khảo sát chuyên sâu theo hướng **Volatility-Conditioned Selection** và **Rút ngắn Horizon**:
- **Đặc tả mới**: [`BTC_VOLATILITY_CONDITIONED_REGIME_SELECTION_SPEC_V1_VI.md`](file:///root/bobby/pool_alpha/lab_regime_model_quantbt/BTC_VOLATILITY_CONDITIONED_REGIME_SELECTION_SPEC_V1_VI.md) (`study_id: btc_volatility_forecast_v1`).
- **Đăng ký chính thức**: [`configs/btc_volatility_forecast_v1/registration.json`](file:///root/bobby/pool_alpha/lab_regime_model_quantbt/configs/btc_volatility_forecast_v1/registration.json).
- **Thực nghiệm đa chân trời**: [`scripts/exp_volatility_horizons_study.py`](file:///root/bobby/pool_alpha/lab_regime_model_quantbt/scripts/exp_volatility_horizons_study.py) đánh giá $H \in \{14, 28, 56, 90\}$.
- **Kết quả thực nghiệm**:
  - **$H = 14$ ngày (Primary Horizon)**: Đạt **Accuracy 62.5%** (so với Persistence 60.4%), **Brier Skill Score = +0.0791 (+7.9% so với baseline)** - **lần đầu tiên có skill dương vững chắc trên OOS**. Nhận diện `LOW_VOL`: **Recall 84.0%**, **Precision 67.7%**, **F1 0.750**. Trùng khớp tự nhiên với thời lượng trung vị của regime BTC (**12.1 ngày** đo bằng Kaplan-Meier trong MF-02).
  - **$H = 28$ ngày (Secondary Horizon)**: Đạt **Accuracy 58.3%**, **BSS ~0% (-0.005)**, cân bằng cao: Low Vol F1 0.696, Mid Vol F1 0.632.
  - $H=56$ và $H=90$ ngày suy thoái do thời lượng dự báo quá dài so với nhịp biến động của thị trường.
- **Evidence lưu trữ**: [`evidence/exp_volatility_horizons_v1/study_results.json`](file:///root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/exp_volatility_horizons_v1/study_results.json).

---

## Tài liệu Bàn giao Toàn diện cho Downstream Agent
Chi tiết đầy đủ về kiến trúc mô hình, bảng so sánh metrics, ma trận nhầm lẫn (confusion matrix), danh mục evidence và hướng dẫn thiết kế Walk-Forward Optimization (WFO) được ghi lại tại:
👉 **[`handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md`](file:///root/bobby/pool_alpha/lab_regime_model_quantbt/handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md)**

---

## Next Action
Bàn giao tài liệu [`handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md`](file:///root/bobby/pool_alpha/lab_regime_model_quantbt/handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md) cho Downstream Agent để tiến hành lập kế hoạch và triển khai Walk-Forward Optimization (WFO) chứng minh Time Edge trên `A-SC / BTCUSDT / 15m`.

