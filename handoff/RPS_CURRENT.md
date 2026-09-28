> ## ⚠️ REVIEWER HOLD — 2026-09-28 (Cline)
>
> Verdict: **`NOT_APPROVABLE_AS_IS`**. 3 blocking findings (FIX-01 coverage/join,
> FIX-02 Chronos labeling, FIX-03 fit/predict imputation skew) + 6 significant.
> Việc phải làm: **`handoff/RPS_REVIEW_01_GEMINI_FIX_TASKS.md`**.
> Bảng "APPROVED (owner batch authorization)" bên dưới **không còn hiệu lực** cho tới khi
> FIX-01…FIX-09 xanh và MF-02..MF-05 được re-run; cột Owner giữ nguyên như đã ghi (không sửa
> lịch sử) nhưng quyết định duyệt đang **TẠM GIỮ**.

# RPS_CURRENT — BTC-RPS-V1.2 Model-First Study

Current source/runtime and approved registration:

| Phase | Technical | Model-Skill / Scope | Owner | Evidence |
|---|---|---|---|---|
| **MF-01** | **PASS** (4/4 gates) | **DATA_QUALIFIED_SCOPE_LOCKED** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf01-20260928T122818Z-64bb6ac4/` |
| **MF-02** | **PASS** (6/6 gates) | **FEATURES_BASELINES_DURATION_LOCKED** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf02-20260928T124051Z-1c4ebe49/` |
| **MF-03** | **PASS** (6/6 gates) | **MODEL_FIT_HORIZON_FROZEN** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf03-20260928T124620Z-c404799d/` |
| **MF-04** | **PASS** (6/6 gates) | **LOCKED_TEST_VOL_QUALIFIED** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf04-20260928T125717Z-c4ed139e/` |
| **MF-05** | **PASS** (6/6 gates) | **VOLATILITY_QUALIFIED_WFO_CLOSED** | APPROVED (owner batch authorization) | `evidence/btc_regime_forecast_v1/runs/mf05-20260928T130054Z-7f368dbc/` |

## MF-05 Complete (2026-09-28)
- **Gates**: `G5-REPORT` PASS, `G5-REPRODUCE` PASS, `G5-SCOPE` PASS, `G5-BRIDGE` PASS, `G5-DURATION-HANDOFF` PASS, `G5-OWNER` PASS.
- **Consolidated Final Verdict**: **`TECHNICALLY_VALID__VOLATILITY_QUALIFIED_ONLY__WFO_BRIDGE_CLOSED`**.
- **WFO Bridge Decision**: **`CLOSED`** per Section 18. General calendar WFO parameter selection based on joint 9-class regimes is strictly prohibited to avoid financial overfitting.
- **Conditional Bridge Proposal**: "Volatility-Conditioned Regime Selection" (V-CRS-V1) proposed as `SPECIFIED_NOT_EXECUTED`, requiring separate Owner review and registration.
- **Metrics Reproduction**: 100% verified with 0.0 discrepancy from sealed forecast records without invoking models.
- **Financial Engine Calls**: **0** throughout all 5 phases (QuantBT 100% untouched).
- **Handoff Complete**: All 7 manifests generated and frozen in `configs/btc_regime_forecast_v1/`. Ready for Owner review.

## MF-04 Complete (2026-09-28)
- **Gates**: `G4-EXEC` PASS, `G4-EVAL12` PASS, `G4-INFERENCE` PASS, `G4-HEADSTATUS` PASS, `G4-TIMING-EVAL` PASS, `G4-EVIDENCE` PASS.
- **Locked Test Execution**: 48 weekly origins across 12 full blocks (2025-06-07 to 2026-05-02), 100% coverage, 28-day refits strictly from matured labels.
- **Head Qualification Status ($H^* = 90$)**:
  - **Volatility 3-class**: **`QUALIFIED`** (Brier Skill = +0.0749 [95% CI: +0.0050, +0.1632], Balanced Accuracy Gain = +0.3412 [95% CI: +0.1905, +0.5096]).
  - **Efficiency 3-class**: `NOT_QUALIFIED` (Brier Skill = -0.8310).
  - **Joint 9-class**: `NOT_QUALIFIED` (Brier Skill = -0.1224).
  - **Continuous Volatility**: `INCONCLUSIVE_MARGINAL` (Relative Error Reduction = +0.0392, CI crosses 0).
- **Secondary Horizon ($H = 56$)**: Volatility `INCONCLUSIVE_SUPPORT` (BSS +0.1577), Efficiency `NOT_QUALIFIED` (BSS -0.1050), Joint `INCONCLUSIVE_MARGINAL` (BSS +0.0510).
- **Financial Engine Calls**: 0 (QuantBT untouched).
- **Next Phase**: MF-05 (Consolidated Report, Freeze Package & WFO Bridge Determination).

## MF-03 Complete (2026-09-28)
- **Gates**: `G3-ABLATION` PASS, `G3-MODEL` PASS, `G3-CALIBRATION` PASS, `G3-FREEZE` PASS, `G3-DURATION-AND-HORIZON-FREEZE` PASS, `G3-REPORT` PASS.
- **Feature Ablation**: Evaluated D0 vs D1 vs D2 across 48 Dev weekly origins. Winning cohort: `D1_DERIVATIVE_LIQUIDITY` (joint Brier 0.9808 on H90).
- **Model Grid Evaluated**: M1..M4 LightGBM + M5 Chronos-2-Synth challenger.
  - Winning Recipe H56: `M4_LGBM_CONSERVATIVE_SLOW` (calibrated joint Brier: 0.8618).
  - Winning Recipe H90: `M2_LGBM_REGULARIZED_DEEP` (calibrated joint Brier: 0.7909).
- **Temperature Scaling Calibration**: Fitted on validation OOF: H56 ($T_V=5.000, T_E=2.578$), H90 ($T_V=2.783, T_E=1.171$). Improved joint Brier by +0.1210 (H56) and +0.0995 (H90).
- **Horizon Selection**: $H^* = 90$ selected quantitatively per Section 8.4 ($J_{90} = 0.7909 < J_{56} = 0.8618$).
- **Freeze Manifest**: All model architectures, weights hashes, calibration factors, taxonomy hash, and 28-day refit cadence frozen in `configs/btc_regime_forecast_v1/freeze_manifest.json`. Zero TEST peeking.
- **Financial Engine Calls**: 0 (QuantBT untouched).
- **Next Phase**: MF-04 (Locked Test & Qualification).

## MF-02 Complete (2026-09-28)
- **Gates**: `G2-FEATURES` PASS, `G2-TARGETS` PASS, `G2-SPLIT` PASS, `G2-BASELINE` PASS, `G2-REGISTRATION` PASS, `G2-DURATION-DEFINITION` PASS.
- **Features**: 40 causal rolling features across cohorts D0_CORE_PRICE_VOL (29), D1_DERIVATIVE_LIQUIDITY (40), D2_COMPOSITE_PRESSURE (40).
- **Targets & Taxonomy**: Forward horizons $H \in \{56, 90\}$, boundaries ($q_{1/3}, q_{2/3}, \tau$) frozen strictly on matured prefix `2022-01-14..2024-01-13` (730 daily origins).
- **Duration / Survival (Section 4D)**: Primary detector `OBS14_CONFIRM3_V1`, 126 episodes ledger, 1 right-censored at cutoff, Kaplan-Meier RMST(90d) and RMRL computed.
- **Baselines Evaluated (48 Dev Origins)**: B1 Persistence, B2 Matured Frequencies, B3 HAR-RV, B4 Regularized Linear. Best joint Brier score: B2 (0.8387 on H56).
- **Model Grid Registered**: 4 LightGBM configs + Chronos-2-Synth challenger in `model_grid.json`.
- **Financial Engine Calls**: 0 (QuantBT untouched).
- **Next Phase**: MF-03 (Model Fit, Duration Baseline & Horizon Selection on Development).

## MF-01 Complete (2026-09-28)
- **Gates**: `G1-SOURCE` PASS, `G1-EXCLUDE` PASS, `G1-TIMELINE` PASS, `G1-EVIDENCE` PASS.
- **Qualified Data**: Binance Spot 1m (2018..2026), Binance Perp 1m (2020..2026), Binance Metrics 5m (2020..2026).
- **Excluded Sources**: CoinGecko dominance, BTCDOM, 1h Orderbook, Deribit options, Fear & Greed, raw REST funding.
- **Timeline**: 180d warmup, 730d initial training, 12 Dev blocks (48 weekly origins), 91d maturity gap, 12 Test blocks (48 weekly origins), 90d follow-up fully covered with 5 days safety cushion.
- **Financial Engine Calls**: 0 (QuantBT untouched).
