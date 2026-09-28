# Phase MF-04 Report: Locked Test & Qualification
Study: `btc_regime_forecast_v1`
Run ID: `mf04-20260928T164913Z-eb2bd5b6`
Date: `2026-09-28T16:49:58.971989+00:00`

## 1. Locked Execution Summary (G4-EXEC, G4-EVAL12)
- Evaluated origins: 48 weekly origins across 12 full test blocks (2025-06-07 to 2026-05-02).
- Zero omissions / zero abstentions (100% coverage).
- Financial Engine Calls: 0 (QuantBT strictly locked).
- Refit Cadence: Every 28 days (4 origins) from strictly matured labels prior to origin.

## 2. Independent Head Qualification Results (G4-HEADSTATUS)

### Primary Horizon $H^* = 90$ (Frozen Selection)
- **Volatility Head (3-class)**: Status = `NOT_QUALIFIED`
  - Brier Skill: -0.0118 (95% CI: [-0.0561, +0.0134])
  - Balanced Accuracy Gain: -0.1062 (95% CI: [-0.1667, +0.0496])
  - Reason: Failed qualification standards; negative or sub-threshold skill against frozen baseline
- **Path Efficiency Head (3-class)**: Status = `NOT_QUALIFIED`
  - Brier Skill: -0.3037 (95% CI: [-0.7430, -0.0385])
  - Balanced Accuracy Gain: +0.0000 (95% CI: [-0.5000, +0.0000])
  - Reason: Failed qualification standards; negative or sub-threshold skill against frozen baseline
- **Joint Regime Head (9-class)**: Status = `NOT_QUALIFIED`
  - Brier Skill: -0.0277 (95% CI: [-0.1278, +0.0501])
  - Balanced Accuracy Gain: -0.2000 (95% CI: [-0.2500, +0.0000])
  - Reason: Failed qualification standards; negative or sub-threshold skill against frozen baseline
- **Continuous Volatility Head**: Status = `INCONCLUSIVE_MARGINAL`
  - Relative Error Reduction: +0.0239 (95% CI: [-0.3561, +0.3613])
  - Reason: Positive error reduction but bootstrap CI overlaps zero

### Secondary Horizon $H = 56$ (Disclosed Companion)
- Volatility 3-class: Status = `NOT_QUALIFIED` (BSS: -0.0003)
- Efficiency 3-class: Status = `NOT_QUALIFIED` (BSS: -0.0568)
- Joint 9-class: Status = `INCONCLUSIVE_MARGINAL` (BSS: +0.0223)
- Continuous Vol: Status = `NOT_QUALIFIED` (ErrRed: -0.1695)

## 3. Timing & Duration Evaluation (G4-TIMING-EVAL)
- Test dwell analysis completed with primary detector `OBS14_CONFIRM3_V1`.
- Mean episode dwell in test: 11.5 days.
- Dwell times evaluated as empirical survival context, without misrepresenting survival curve extrapolation as machine learning forecast skill.

## 4. Exit Gate Status
- `G4-EXEC`: PASS (48 origins executed).
- `G4-EVAL12`: PASS (12 full test blocks evaluated).
- `G4-INFERENCE`: PASS (Frozen recipe, 28-day refit cadence, zero look-ahead).
- `G4-HEADSTATUS`: PASS (Rigorous status assigned per head).
- `G4-TIMING-EVAL`: PASS (DUR-T09..10 verified).
- `G4-EVIDENCE`: PASS (Sealed predictions, ground truths, bootstrap CIs).
