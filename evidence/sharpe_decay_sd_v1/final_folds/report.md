# SD-03 — Final A/B/C run: D1/D2/continuous-account Sharpe, inference, conclusion

- study_id: sharpe_decay_sd_v1, guide_version: SD-GUIDE-1.0
- generated_at_utc: 2026-09-26T11:47:53.796223+00:00
- real FINAL folds found: 12/12
- preflight: READY

## Scope (guide SS10)
SD-03 is the one final A/B/C run on >=12 paired OOS folds. Technical PASS does NOT require Sharpe improvement (guide SS10.5). This is the FIRST and ONLY final run -- no re-selection of hyperparameters after seeing results, no SD-04.

## Registered primary hypothesis
- id: H_REGIME
- contrast: C_SD_JM vs B_SD_GLOBAL
- estimand: mean paired signed reduction R_bar = mean(D_B - D_C) over >=12 common folds
- safeguard: mean paired standardized forward Sharpe difference Q_bar(C-B) vs non-inferiority margin -0.10

## D1 table (guide SS10.3) — REAL, MEASURED, every fold shown

| origin | A winner | B winner | C winner | D_B | D_C | R=D_B-D_C |
|---|---|---|---|---:|---:|---:|
| 2024-03-23 | ANCHOR | other | other | 0.8774032239684211 | 0.35323227992747175 | 0.5241709440409493 |
| 2024-05-18 | ANCHOR | ANCHOR | ANCHOR | 3.1921645158465646 | 3.1921645158465646 | 0.0 |
| 2024-07-13 | ANCHOR | other | other | 0.40286287327097425 | 2.003808918818465 | -1.6009460455474909 |
| 2024-09-07 | ANCHOR | other | other | -3.900416531075206 | -3.900416531075206 | 0.0 |
| 2024-11-02 | ANCHOR | other | other | 1.3519708204670566 | 1.675939321205535 | -0.32396850073847827 |
| 2024-12-28 | ANCHOR | other | other | 5.058582477833909 | 5.058582477833909 | 0.0 |
| 2025-02-22 | ANCHOR | other | other | 1.0341977113970036 | 1.0341977113970036 | 0.0 |
| 2025-04-19 | ANCHOR | other | other | -0.4371645170615529 | -0.4371645170615529 | 0.0 |
| 2025-06-14 | ANCHOR | other | other | 2.1565114153704803 | 2.1565114153704803 | 0.0 |
| 2025-08-09 | ANCHOR | other | other | -0.6361069884921766 | -0.6361069884921766 | 0.0 |
| 2025-10-04 | ANCHOR | other | other | 1.9945158187552572 | 1.9945158187552572 | 0.0 |
| 2025-11-29 | ANCHOR | other | other | 0.24529548551638292 | 0.24529548551638292 | 0.0 |

- n paired-valid D1 folds: **12/12**

**HONEST FINDING, DISCLOSED**: 9/12 of these paired folds have R = 0 EXACTLY, by construction, because B_SD_GLOBAL and JM_C2.0 selected the IDENTICAL candidate at those origins (checked directly against each arm's own winner_id) -- not a measured absence of effect at those folds, a structural non-event. Only 3/12 folds carry real, non-trivial evidence about whether the JM correction helps or hurts. This is the same 'more than half the evidence could not have shown an edge' shape LAB-06's own OP-14 finding already named in this lab's history -- the primary R estimate below is computed over all 12 folds (guide's own registered procedure), but its EFFECTIVE sample size for detecting a real effect is much thinner than 12 folds suggests.

## D2 frozen continuations (guide SS2.4)

| origin | arm | SR_H1 | SR_H2 | D_age |
|---|---|---:|---:|---:|
| 2024-03-23 | A_M4 | -0.33563380700255446 | -3.4106869704520166 | 3.075053163449462 |
| 2024-03-23 | B_SD_GLOBAL | 0.33856844255032237 | -3.249900705526882 | 3.5884691480772046 |
| 2024-03-23 | JM_C2.0 | 0.933543749245754 | -3.274698159826562 | 4.208241909072316 |
| 2024-05-18 | A_M4 | -1.4268684289890425 | -0.4764035244470148 | -0.9504649045420277 |
| 2024-05-18 | B_SD_GLOBAL | -1.4268684289890425 | -0.4764035244470148 | -0.9504649045420277 |
| 2024-05-18 | JM_C2.0 | -1.4268684289890425 | -0.4764035244470148 | -0.9504649045420277 |
| 2024-07-13 | A_M4 | -0.2690130798322521 | 3.247183996738043 | -3.516197076570295 |
| 2024-07-13 | B_SD_GLOBAL | 0.43322811181753185 | 3.328586640741354 | -2.895358528923822 |
| 2024-07-13 | JM_C2.0 | -1.0725363358942415 | 2.936376815275722 | -4.008913151169963 |
| 2024-09-07 | A_M4 | 2.9375124443415506 | 0.7213835101838391 | 2.2161289341577115 |
| 2024-09-07 | B_SD_GLOBAL | 3.4430096998492807 | 0.08405680717695507 | 3.3589528926723258 |
| 2024-09-07 | JM_C2.0 | 3.4430096998492807 | 0.08405680717695507 | 3.3589528926723258 |
| 2024-11-02 | A_M4 | -0.8978579737418423 | -2.704140652471936 | 1.8062826787300934 |
| 2024-11-02 | B_SD_GLOBAL | -0.32363005433862296 | -2.6502762182731825 | 2.3266461639345595 |
| 2024-11-02 | JM_C2.0 | -1.0263827198046922 | -1.892993564569106 | 0.8666108447644139 |
| 2024-12-28 | A_M4 | -4.72643623904446 | -8.435613032446906 | 3.7091767934024453 |
| 2024-12-28 | B_SD_GLOBAL | -3.841280230163499 | -8.922091161489568 | 5.080810931326069 |
| 2024-12-28 | JM_C2.0 | -3.841280230163499 | -8.922091161489568 | 5.080810931326069 |
| 2025-02-22 | A_M4 | -0.47105485173922323 | -0.44497770749677207 | -0.026077144242451167 |
| 2025-02-22 | B_SD_GLOBAL | -0.787457655679655 | -0.5709932517371744 | -0.21646440394248057 |
| 2025-02-22 | JM_C2.0 | -0.787457655679655 | -0.5709932517371744 | -0.21646440394248057 |
| 2025-04-19 | A_M4 | 0.6492540373927 | -3.4265266836730133 | 4.075780721065714 |
| 2025-04-19 | B_SD_GLOBAL | 0.2987845648396923 | -2.0770432555499254 | 2.3758278203896177 |
| 2025-04-19 | JM_C2.0 | 0.2987845648396923 | -2.0770432555499254 | 2.3758278203896177 |
| 2025-06-14 | A_M4 | -3.3750522052879948 | 0.5227346636655859 | -3.8977868689535806 |
| 2025-06-14 | B_SD_GLOBAL | -2.614976842052486 | -0.8910079631983172 | -1.7239688788541687 |
| 2025-06-14 | JM_C2.0 | -2.614976842052486 | -0.8910079631983172 | -1.7239688788541687 |
| 2025-08-09 | A_M4 | -0.20491302715297863 | -4.519678790347889 | 4.31476576319491 |
| 2025-08-09 | B_SD_GLOBAL | 0.5215824247628542 | -4.682384223266345 | 5.2039666480291995 |
| 2025-08-09 | JM_C2.0 | 0.5215824247628542 | -4.682384223266345 | 5.2039666480291995 |
| 2025-10-04 | A_M4 | -1.677159312412071 | -2.196708278082571 | 0.5195489656704999 |
| 2025-10-04 | B_SD_GLOBAL | 0.046456423921269675 | -1.5748164481042872 | 1.621272872025557 |
| 2025-10-04 | JM_C2.0 | 0.046456423921269675 | -1.5748164481042872 | 1.621272872025557 |
| 2025-11-29 | A_M4 | -2.552157460238652 | 1.5127905617933257 | -4.064948022031977 |
| 2025-11-29 | B_SD_GLOBAL | -1.5038480390178464 | 0.5052778742781352 | -2.0091259132959816 |
| 2025-11-29 | JM_C2.0 | -1.5038480390178464 | 0.5052778742781352 | -2.0091259132959816 |

## Continuous-account Sharpe (guide SS2.5)

| arm | n_bars | n_fills | n_entries | cache_event |
|---|---:|---:|---:|---|
| A_M4 | 1094400 | 1184 | 592 | MISS |
| B_SD_GLOBAL | 1094400 | 980 | 490 | MISS |
| JM_C2.0 | 1094400 | 986 | 493 | MISS |

## Inference (guide SS7.2/7.4, sd/inference_sd03.py — locked before FINAL)
- **decision: NO_MEANINGFUL_REDUCTION_AT_0_20_WITHIN_SCOPE**
- R point estimate: -0.1167286335204183, 95% CI [-0.2334572670408366, 0.17709308246570335] (block length 4, 5000 resamples, seed 20260926)

### Sensitivity analysis (guide SS7.2: report ALL registered block lengths, never cherry-pick whichever looks significant) — descriptive only, does NOT override the primary (block length 4) decision above

| block length | R point est. | R 95% CI | Q point est. | Q 95% CI |
|---:|---:|---|---:|---|
| 2 | -0.1167286335204183 | [-0.2938217159861216, 0.19377661940757598] | -0.13446181720686756 | [-0.3185049099716878, 0.1660801996363807] |
| 3 | -0.1167286335204183 | [-0.2334572670408366, 0.19377661940757598] | -0.13446181720686756 | [-0.2689236344137351, 0.1750616462006005] |

## Glossary
- **D1** (guide SS2.2: primary decay label, same params, IS->forward Sharpe, measured fresh at each real FINAL origin)
- **D2** (guide SS2.4: a frozen 112-day continuation of the SAME selected params, H1 (first 56 days) vs H2 (next 56 days), no account reset at the boundary -- measures whether the SAME candidate's own performance ages within one deployment)
- **R = D_B - D_C** (guide SS2.3: paired reduction in Sharpe decay from adding the state-conditioned correction; positive means C decayed less than B)
- **continuous account** (guide SS2.5/SD03.5: one account per arm running the WHOLE real path with actual admission/activation/fills, never 12 reset-and-restitched accounts)
- **sensitivity analysis** (guide SS7.2: the SAME paired block-bootstrap re-run at every registered alternate block length (2 and 3 folds, alongside the primary 4), reported in full regardless of which one looks significant -- never used to override the primary decision, only to show whether it is robust to this design choice)
- **same-contract replay** (guide SD03.8: re-running one already-committed real artifact -- here, the A_M4 D2 continuation at the first FINAL origin -- under the IDENTICAL params/cutoff/economics, to prove it reproduces exactly; a cache HIT on the replay is EXPECTED and disclosed, never treated as a fresh independent confirmation)

## Same-contract replay (guide SD03.8)
- replayed: 2024-03-23/A_M4
- all gated fields match: **True**
- cache provenance: original=MISS, replay=HIT (a MISS->HIT transition is expected and is evidence the replay found and reused the identical computation)

## Permitted conclusions
- Technical: preflight READY, 12/12 real FINAL folds present.
- Research: **NO_MEANINGFUL_REDUCTION_AT_0_20_WITHIN_SCOPE** (guide SS7.4's own registered decision vocabulary). Technical PASS does not require Sharpe improvement.
- Owner review: PENDING.
