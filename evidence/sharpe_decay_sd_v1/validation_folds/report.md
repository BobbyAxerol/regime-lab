# SD-02 — JM validation on 12 real folds: recipe selection, model quality, freeze

- study_id: sharpe_decay_sd_v1, guide_version: SD-GUIDE-1.0
- generated_at_utc: 2026-09-26T01:11:55.495292+00:00
- real folds found: 12/12 (origins 2022-05-14..2024-01-20)

## Scope (guide SS9.1)
SD-02 asks whether the model has TASK-RELEVANT information and locks exactly one JM recipe for the FINAL run. It does not require the model to win -- guide SS9.5 G2-RELEVANCE explicitly does not gate on a positive result.

## Registered primary hypothesis (configs/sharpe_decay_sd_v1/registration.json)
- id: H_REGIME
- contrast: C_SD_JM vs B_SD_GLOBAL
- estimand: mean paired signed reduction R_bar = mean(D_B - D_C) over >=12 common folds
- safeguard: mean paired standardized forward Sharpe difference Q_bar(C-B) vs non-inferiority margin -0.10
- registered thresholds: meaningful_decay_reduction=0.2 Sharpe points, oos_noninferiority_margin=0.1, prediction_guard_margin=0.1

## Recipe selection (guide SS5.8, SD02.7) — REAL, MEASURED

| recipe c | n_paired_folds | technically_valid | mean R = D_B - D_C |
|---|---:|---|---:|
| 0.5 | 12 | True | 0.405200 |
| 1.0 | 12 | True | 0.405200 |
| 2.0 | 12 | True | 0.405200 |

- **decision: RECIPE_SELECTED**
- selected_c: 2.0
- mean_R of selected design: 0.4052002777808164
- tie_broken: True

Guide SS5.8 does NOT require mean_R > 0 for a design to be selected -- the rule picks the LARGEST R among technically-valid designs regardless of sign, and the losing/negative designs' own numbers are kept in the table above, never dropped.

**HONEST FINDING, DISCLOSED, NOT GLOSSED OVER: the three JM penalty designs are DEGENERATE on this real data.** All three recipes (c=0.5, 1.0, 2.0) selected the IDENTICAL candidate at EVERY one of the 12/12 real VALIDATION folds -- checked directly against each arm's own winner_id, not inferred from the mean_R average (which could coincidentally match even with different per-fold sequences). This is the SAME shape this lab's own history keeps finding (LAB-08's 'Arm E was a copy of Arm D', FP-07's 'C=B degenerate'): the tie-break rule correctly picked the larger c (2.0) among tied designs per guide SS5.8, but **'RECIPE_SELECTED, c=2.0' must NOT be read as evidence that a stronger persistence penalty helps** -- R itself never differed by which c was used, on any real fold. This is NOT a code defect: the underlying JM state genuinely DOES differ across recipes at least once (yes, at 1 fold -- confirmed directly from jm_this_origin's own state field), proving the mechanism is live; it simply never changed which candidate the minY rule picked, on this specific real window/alpha/symbol.

## Real per-fold selection outcomes (all 6 arms, same panel pool every fold)

| origin | A_M4 | B_SD_GLOBAL | R_RULE | JM_C0.5 | JM_C1.0 | JM_C2.0 |
|---|---|---|---|---|---|---|
| 2022-05-14 | ANCHOR | ANCHOR | ANCHOR | ANCHOR | ANCHOR | ANCHOR |
| 2022-07-09 | ANCHOR | other | other | other | other | other |
| 2022-09-03 | ANCHOR | ANCHOR | ANCHOR | ANCHOR | ANCHOR | ANCHOR |
| 2022-10-29 | ANCHOR | other | other | other | other | other |
| 2022-12-24 | ANCHOR | other | other | other | other | other |
| 2023-02-18 | ANCHOR | other | other | other | other | other |
| 2023-04-15 | ANCHOR | other | other | other | other | other |
| 2023-06-10 | ANCHOR | ANCHOR | ANCHOR | ANCHOR | ANCHOR | ANCHOR |
| 2023-08-05 | ANCHOR | other | other | other | other | other |
| 2023-09-30 | ANCHOR | other | other | other | other | other |
| 2023-11-25 | ANCHOR | other | other | other | other | other |
| 2024-01-20 | ANCHOR | other | other | other | other | other |

## Model quality diagnostics (guide SS9.2 SD02.5) — descriptive layer, never conflated with economic usefulness

| arm | mean MAE(Y), Sharpe points | n rank-valid folds | mean rank rho |
|---|---:|---:|---:|
| B_SD_GLOBAL | 0.872732 | 12 | 0.1956 |
| R_RULE | 0.857292 | 12 | 0.2257 |
| JM_C0.5 | 0.857027 | 12 | 0.2436 |
| JM_C1.0 | 0.857027 | 12 | 0.2436 |
| JM_C2.0 | 0.856178 | 12 | 0.2363 |

### JM state occupancy/dwell/recurrence per recipe (across the 12 VALIDATION origins)
- **JM_C0.5**: occupancy={1: 4, 0: 8}, recurrence_count={1: 4, 0: 4}, mean_dwell_bars={1: 1.0, 0: 2.0}, n_unknown=0/12
- **JM_C1.0**: occupancy={1: 4, 0: 8}, recurrence_count={1: 4, 0: 4}, mean_dwell_bars={1: 1.0, 0: 2.0}, n_unknown=0/12
- **JM_C2.0**: occupancy={1: 5, 0: 7}, recurrence_count={1: 5, 0: 5}, mean_dwell_bars={1: 1.0, 0: 1.4}, n_unknown=0/12

## Support (guide SS9.3 aggregate fields)

| arm | train_mature_origin_count (mean across folds) |
|---|---:|
| R_RULE | 12.58 |
| JM_C0.5 | 12.58 |
| JM_C1.0 | 12.58 |
| JM_C2.0 | 12.58 |

## Freeze (guide SD02.8)
- sealed_at_utc: 2026-09-26T01:11:55.480942+00:00
- frozen recipe: c=2.0, decision=RECIPE_SELECTED
- frozen hyperparameters: lambda_global=10.0, lambda_state=10.0, K=2

## Verification (guide SS9.5, independent re-derivation from raw fold records)
- overall: **PASS**
- G2-ML-VALID: PASS
- G2-VAL12: PASS
- G2-INDEPENDENCE: PASS
- G2-RELEVANCE: PASS
- G2-FREEZE: PASS
- G2-OWNER: PASS

## Glossary
- **fold** (guide SS9.3: one of the 12 real VALIDATION origins, each a real 128-trial engine search producing its own <=16-candidate representative panel + anchor, chronologically ordered — this study's own unit of real, paired comparison)
- **R = D_B - D_C** (guide SS2.3/SS5.8: the paired reduction in Sharpe decay achieved by adding a state-conditioned correction (C) on top of the global model (B) alone, at one fold; positive means C decayed LESS than B)
- **GLOBAL_FALLBACK** (guide SS5.5/5.6: a conditional arm's own prediction reverts exactly to B's prediction, correction=0, because the state at that origin was unrecognised or below the >=3-origin support floor — never a fabricated correction)
- **panel-only selection scope** (this phase's own owner-approved scope, dec-c94ea602aeac0f1a: B/C/R_RULE select among the SAME <=16-candidate representative panel + anchor SD-01/SD-02's own archive already forward-evaluates, not the full raw candidate pool, to avoid an estimated ~10h of new undisclosed real engine compute)
- **MAE(Y)** (guide SS9.2 SD02.5: mean absolute error between a model's predicted relative Sharpe decay Y_hat and the real, forward-evaluated true Y, averaged WITHIN an origin first, then unweighted across origins — never a pooled per-row average)
- **state occupancy/dwell/recurrence** (guide SS5.6: occupancy = how many origins were in a given JM state; dwell = mean length of a continuous run in that state; recurrence = how many SEPARATE times that state was visited, a gap between visits never assumed to be a continuation)

## Permitted conclusions
- Technical: PASS across all six G2-* gates — the real 12-fold search, JM tapes, contrast ridge B and state-conditioned correction C, and R_RULE all ran for real, are independently re-verified from raw fold records (never a runner-produced summary), and every conditional arm was scored regardless of B's own selection outcome.
- Research: recipe-selection decision is **RECIPE_SELECTED** (c=2.0, mean_R=0.4052002777808164). This is the guide's own registered three-outcome vocabulary (NO_VALID_JM_DESIGN / WEAK_DEVELOPMENT_EVIDENCE / RECIPE_SELECTED) -- not a stronger, invented label. The selection is a TIE-BREAK among degenerate designs, not evidence a stronger penalty is better (see the disclosed finding above) -- research_status remains NOT_ASSESSED for the primary economic question: SD-02 locks which recipe FINAL will use, it does not itself claim JM beats B on Sharpe decay.
- Owner review: PENDING SD-03 needs its own explicit R-18 approval.
