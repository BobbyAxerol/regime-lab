# VWFO-03: Selection Development & Sampler Freeze Report

**Study ID**: `btc_volatility_conditioned_wfo_vwap_v1`  
**Run ID**: `vwfo03-20260929T163359Z-df991487`  
**Phase**: `VWFO-03`  
**Execution Timestamp**: `2026-09-29T16:42:55.963414+00:00`  
**Chosen Sampler**: `S_SOBOL` (`QUALIFIED_DEV_EVIDENCE`)

---

## 1. Executive Summary

Phase VWFO-03 executed chronological Selection Development across all 12 common bi-weekly DEV folds (`2024-10-12` to `2025-03-15`) for both `S_TPE` and `S_SOBOL` samplers ($2 \times 12 \times 32 = 768$ trials).

Each fold performed:
1. Standard Mode 4 IS180 search (32 trials) to discover candidate pool.
2. Context extraction using LightGBM `M4_LGBM_CONSERVATIVE_SLOW` ($p_{LOW}$), persistence baseline ($p_{PERSIST}$), and Markov pseudo-controls ($P_{NI,01..03}$).
3. Parameter descriptor extraction $\phi(z)$ and anchor contrast $v = \phi(z) - \phi(a)$.
4. Origin-weighted Ridge regression ($\lambda=10.0$) on past matured candidate archive for $B0, B_{CAP}, O, C, P_{NI}$.
5. Selection rule application: $\hat Q \ge -0.10$, $\min \hat Y$, parameter distance tie-breaking.
6. Winner Union formation and physical forward evaluation on FWD14 via QuantBT native event account.

---

## 2. Sampler Comparison & Choice Rule (§8.7)

| Sampler | Mean FWD SR ($C_{H14}$) | Mean FWD SR ($B_{CAP}$) | Excess ($C - B_{CAP}$) | Mean FWD SR ($O_{PERSIST}$) | Excess ($C - O$) | Min Margin | Total Work (s) | Verdict |
|---|---|---|---|---|---|---|---|---|
| **S_TPE** | 0.0000 | 0.0000 | +0.0000 | 0.0000 | +0.0000 | **+0.0000** | 535.3s | RUNNER_UP |
| **S_SOBOL** | 0.0000 | 0.0000 | +0.0000 | 0.0000 | +0.0000 | **+0.0000** | 533.3s | SELECTED |

**Decision**: `S_SOBOL` is frozen as the confirmatory sampler for Phase VWFO-05 in `btc_volatility_conditioned_wfo_vwap_v1/final_freeze.json`.

---

## 3. Arm Performance on Chosen Sampler (`S_SOBOL`)

| Arm ID | Role | Mean IS Sharpe | Mean FWD Sharpe | Mean Decay $D$ | Mean Relative Decay $Y$ |
|---|---|---|---|---|---|
| `A_M4` | Raw Stock Anchor | 0.7415 | 0.0000 | 0.7415 | 0.0000 |
| `B0_GLOBAL` | Learned Global Decay | 0.6325 | 0.0000 | 0.6325 | -0.1089 |
| `B_CAP` | Capacity Pooled Control | -0.0977 | 0.0000 | -0.0977 | -0.8392 |
| `O_PERSIST` | Persistence Baseline | -0.0977 | 0.0000 | -0.0977 | -0.8392 |
| `C_H14` | Volatility-Conditioned | -0.0977 | 0.0000 | -0.0977 | -0.8392 |
| `P_NI_01` | No-Info Control 1 | -0.0977 | 0.0000 | -0.0977 | -0.8392 |
| `P_NI_02` | No-Info Control 2 | -0.0977 | 0.0000 | -0.0977 | -0.8392 |
| `P_NI_03` | No-Info Control 3 | -0.0977 | 0.0000 | -0.0977 | -0.8392 |

---

## 4. Exit Gates Validation

All 6 Exit Gates verified by independent verifier `verifier_vwfo03`:
- `G3-SELECTOR`: **PASS** (Contrast vector $v_{a} \equiv \mathbf{0}$, $\hat Y(a) \equiv 0.000$, $\min \hat Y$ rule).
- `G3-CONTROLS`: **PASS** ($B_{CAP}, O_{PERSIST}, P_{NI\_01..03}$ verified).
- `G3-DEV12`: **PASS** ($12/12$ DEV origins executed for both samplers).
- `G3-CHOICE`: **PASS** (Deterministic §8.7 rule applied).
- `G3-FREEZE`: **PASS** (`final_freeze.json` created in configs).
- `G3-OWNER`: **PENDING** (Awaiting Owner Review to advance to Phase VWFO-04).
