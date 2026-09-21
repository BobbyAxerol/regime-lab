# RA-07 - Replication co gioi han, falsification, decay va inference

## 1. Status va scope
- Technical gate: **FAIL**.
- **conclusion_level: INCONCLUSIVE_SUPPORT** (registered vocabulary, guide 13.5's claim-gate table;
  this is the primary H-BUDGET contrast's status -- see section 6 for the CI/delta it was
  derived from, and section 4/9 for the controls/sensitivity that qualify how much this status
  can carry).
- Branch `mode4-corrective`, guide RA-GUIDE-1.0 (section 11), study `regime_time_edge_ra_v1`, run `ra07-20260919T065543Z-69973d51`.
- Primary contrast (guide RA07.1, RA-01 H-BUDGET): M4_REGIME - M4_CAL_MATCHED (information timing only; RA-01 H-BUDGET).
- Action-aware contrast: RA-06's G06-SCOPE lock decision was KEEP_BASELINE (support=5 below the registered floor min_required=8); no AGE_CONTEXT policy revision was locked, so there is no action-aware policy for RA-07 to close a separate AGE_CONTEXT-AGE_ONLY contrast against (guide RA07.1's own conditional: 'neu RA-06 action-aware duoc chon'; it was not).

## 2. Economic threshold delta and MDE (RA07.1, frozen before any RA-07 outcome)
- delta (guide 13.3 formula, calibrated from cell-1's real fills): status=OK,
  value=0.0001452334300587376, calibration_days=151.
- MDE (guide 13.6, from cell-1's own paired daily-return variability): status=OK,
  value=0.000238304601319016.
- RF-05 cross-reference (different contract, never substituted): 0.0371 bps/day.

## 3. Coverage matrix (RA07.2)
- 2 RUN_VALID / 10 BLOCKED_CAPABILITY / 8 NOT_RUN_BUDGET of 20 planned cells.
- Cell 2: A-SC/ETHUSDT, capability_status=EXECUTED.
  A-SC trades ETHUSDT using the SAME BTC-derived regime emissions tape as cell 1 (BTCUSDT) -- this tests whether a BTC-fit regime model's TIMING transfers to trading a different, correlated symbol, not whether an ETH-fit regime model would help ETH.

## 4. Controls (RA07.3)
- CALENDAR_BUDGET_MATCHED: ALREADY_AVAILABLE
- AGE_ONLY: NOT_APPLICABLE -- RA-06 locked KEEP_BASELINE (support=5 < min_required=8); no action-aware policy exists to contrast against AGE_ONLY
- DELAYED_INFORMATION: OK, equity_last=20593.226647669042
- PLACEBO_TIMING: INSUFFICIENT_WINDOW_OBSERVATIONS, fidelity_matched=None, equity_last=None
- RISK_EXPOSURE_ATTRIBUTION: OK

## 5. Decay D1/D2/D3 (RA07.4)
- rows: 32 total, by kind: {'D1_IS_TO_OOS': 22, 'D2_PARAMETER_AGE': 5, 'D3_ADJACENT_OPERATIONAL_FOLDS': 5}

## 6. Bootstrap statistics (RA07.5, zero engine calls)
- Primary contrast n_common_days=150, n_blocks=5
- point_estimate=0.00010749611360878338, CI_95=[-2.3388865982025994e-05, 0.00030376434689337214], p=0.1684
- claim: INCONCLUSIVE_SUPPORT -- conclusion_level for this contrast.
- Numeric reference self-check (synthetic data only): pass=True

## 7. Multiplicity (RA07.5)
- primary unadjusted: {'name': 'cell1: M4_REGIME - M4_CAL_MATCHED', 'p_value': 0.1684, 'adjustment': 'NONE (single pre-registered primary hypothesis, guide 13.4)'}
- secondary Holm family: {"cell1: M4_REGIME - M4_CAL": {"raw_p": 0.4472, "holm_adjusted_p": 0.4472}, "cell1: M4_CAL_MATCHED - M4_CAL": {"raw_p": 0.1452, "holm_adjusted_p": 0.2904}, "cell2: M4_REGIME - M4_CAL_MATCHED": {"raw_p": 0.0, "holm_adjusted_p": 0.0}}

## 8. Support and power (RA07.6)
both cells run a ~90-day phase-owned pilot window (~3 blocks of 28 days at the primary bootstrap block length); every contrast in this phase falls well short of the legacy 12-block/365-day floor, so INCONCLUSIVE_SUPPORT is the expected, not a surprising, outcome here.

## 9. Sensitivity (RA07.7)
- leave-one-cell-out: {"cell1_alone": {"point_estimate": 0.00010749611360878338, "ci_95": [-2.3388865982025994e-05, 0.00030376434689337214]}, "cell2_alone": {"point_estimate": 0.0, "ci_95": [0.0, 0.0]}, "pooled_2_cell_aggregate": {"computed": false, "reason": "no pre-registered partial-scope capital weighting exists"}, "agreement": {"same_sign": false}}

## 10. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref | Status |
|---|---|---|---|---|
| G07-VALID | PASS | PASS | ra07-20260919T065543Z-69973d51/phase_manifest.json | PASS |
| G07-CONTROL | PASS | PASS | ra07-20260919T065543Z-69973d51/phase_manifest.json | PASS |
| G07-STATS | PASS | PASS | ra07-20260919T065543Z-69973d51/phase_manifest.json | PASS |
| G07-DECAY | PASS | PASS | ra07-20260919T065543Z-69973d51/phase_manifest.json | PASS |
| G07-CLAIM | PASS | FAIL | ra07-20260919T065543Z-69973d51/phase_manifest.json | FAIL |
| G07-MANIFEST | PASS | PASS | ra07-20260919T065543Z-69973d51/phase_manifest.json | PASS |

## 11. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Owner decisions pending: this phase's review; can_start_next_phase=false.

## 12. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra07.py --pytest-xml <junit>` (new run_id per attempt;
  prior runs immutable). `--smoke` runs a tiny/fast config to dry-run the pipeline.
- Next permissible action: user-requested assumption review of RA-05/06/07, then RA-08 only
  after separate owner approval of this phase.
