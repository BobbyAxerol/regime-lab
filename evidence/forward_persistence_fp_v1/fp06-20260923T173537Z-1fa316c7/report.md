# FP-06 — Implement C_FP_CONTEXT (Selector C) (fp06-20260923T173537Z-1fa316c7)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7
- started_at: 2026-09-23T17:35:32.652239+00:00
- alpha: A-SC, archive: FP-04/05's same 12-origin/192-record ledger (guide 9.1/FP06-T06: identical candidate pool)

## Frozen context policy (guide 18 task 7)
- context features: ['ctx_direction_efficiency', 'ctx_volatility_ratio']
- interaction terms (guide 9.2: a few, never the full Cartesian product):
  - norm_AP x ctx_direction_efficiency: AP is a lookback/period parameter; a shorter/longer effective lookback plausibly behaves differently in a trending vs. choppy market
  - norm_coeff x ctx_volatility_ratio: coeff scales signal sensitivity; plausibly interacts with whether recent volatility is elevated relative to the training-memory norm
- 2 of 18 possible candidate-descriptor x context pairs (guide 9.2's prohibition)
- JM/M0 used: False -- LAB-08's own measured history found JM/M0 calibration-vintage state support too thin to build on (only 1.64% of scoring observations carried a state key seen during calibration) -- a disclosed design choice, not a silent omission; guide 9.4's exposure count is still recorded, at zero.

## OOF diagnostics -- B and C through the LITERAL SAME walk-forward loop
- distinct fit origins: 12, validation origins: 8 ['2022-01-01', '2022-04-01', '2022-07-01', '2022-10-01', '2023-01-01', '2023-04-01', '2023-07-01', '2023-10-01']
- selected alpha -- B: 10.0, C: 10.0

## Held-out demo on 2023-10-01 (model trained on the 11 earlier origins only)
  - R00: C_predicted=0.000015 (source=CONTEXT_CONDITIONED), B_predicted=1.6136603384221933e-05, ACTUAL=0.000040
  - R01: C_predicted=0.000018 (source=CONTEXT_CONDITIONED), B_predicted=1.5701976425259238e-05, ACTUAL=0.000506
  - R02: C_predicted=0.000015 (source=CONTEXT_CONDITIONED), B_predicted=1.416064934136976e-05, ACTUAL=0.000494
  - R03: C_predicted=0.000008 (source=CONTEXT_CONDITIONED), B_predicted=4.805164879498106e-06, ACTUAL=0.000010
  - R04: C_predicted=-0.000008 (source=CONTEXT_CONDITIONED), B_predicted=-7.244209515603187e-06, ACTUAL=0.000070
  - R05: C_predicted=0.000006 (source=CONTEXT_CONDITIONED), B_predicted=4.604076413176648e-06, ACTUAL=0.000199
  - R06: C_predicted=0.000005 (source=CONTEXT_CONDITIONED), B_predicted=3.0163377803618496e-06, ACTUAL=0.000239
  - R07: C_predicted=0.000002 (source=CONTEXT_CONDITIONED), B_predicted=3.8103859002599697e-07, ACTUAL=0.000232
  - R08: C_predicted=-0.000009 (source=CONTEXT_CONDITIONED), B_predicted=-6.756938084961399e-06, ACTUAL=0.000220
  - R09: C_predicted=-0.000007 (source=CONTEXT_CONDITIONED), B_predicted=-8.815089055961511e-06, ACTUAL=0.000131
  - R10: C_predicted=-0.000018 (source=CONTEXT_CONDITIONED), B_predicted=-1.467387044664094e-05, ACTUAL=-0.000094
  - R11: C_predicted=-0.000004 (source=CONTEXT_CONDITIONED), B_predicted=-5.486704253690442e-06, ACTUAL=0.000185
  - R12: C_predicted=0.000004 (source=CONTEXT_CONDITIONED), B_predicted=1.9882035058691356e-06, ACTUAL=0.000183
  - R13: C_predicted=-0.000033 (source=CONTEXT_CONDITIONED), B_predicted=-3.2070376026391885e-05, ACTUAL=0.000018
  - R14: C_predicted=-0.000008 (source=CONTEXT_CONDITIONED), B_predicted=-7.303326892143965e-06, ACTUAL=0.000167
  - R15: C_predicted=-0.000003 (source=CONTEXT_CONDITIONED), B_predicted=-4.248784273483298e-06, ACTUAL=0.000260

## Ablation: C - B on the shared candidate set (FP06-G-ABLATION)
- n_shared candidates: 16
- mean(C - B): 4.78867190721576e-07
- only in B (not scored by C): []
- only in C (not scored by B): []

## Exposure (guide 9.4, guide 9.5's claim-level table)
- JM observations: 0, M0 observations: 0, unknown/stale/ambiguous: 0
- fallback-to-B count: 0, context-conditioned count: 16 (of 16 scored)

## Glossary
- **context feature** (guide 9.3: a small, frozen set of continuous market descriptors -- direction efficiency and a volatility ratio in this v1 -- computed from the SAME causal IS frame, never JM/M0 state in this v1)
- **interaction term** (guide 9.2: a candidate-descriptor x context product term, the ONLY mechanism that lets a model's predicted candidate RANKING change with context -- a purely additive f(theta)+g(x) model cannot do this, proved on a designed fixture, FP06-T04)
- **OOD (out-of-distribution)** (a candidate's context value falls outside the range observed in ITS OWN model's training rows -- triggers fallback to Selector B's own prediction rather than an unsupported context-conditioned one)
- **ablation** (C's prediction minus B's prediction on the IDENTICAL candidate, the guide's required same-scope 'context difference' measurement)

## Permitted conclusions
- Technical: Selector C reuses Selector B's candidate pool, base features, target, estimator family and inner split policy verbatim (same walk_forward_oof call, different feature_matrix_fn), a designed fixture proves the interaction architecture CAN represent a context-dependent candidate-ranking crossover that a pure additive model provably cannot (FP06-T04), and OOD candidates fall back to Selector B rather than an unsupported context-conditioned prediction.
- Research: NOT_ASSESSED -- FP-06 builds and demonstrates Selector C; it does not run the locked A/B/C comparison (FP-07) or claim C beats B on real data. Guide 9.2: 'C không tạo khác biệt trên real data vẫn là kết quả hợp lệ nếu execution đúng.'
- Owner review: PENDING; FP-07 needs its own approval per the owner's recorded open-ended auto-advance instruction.
