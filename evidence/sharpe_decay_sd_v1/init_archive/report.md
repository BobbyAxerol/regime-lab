# SD-01 — Standardize Sharpe and build the real INIT archive

- study_id: sharpe_decay_sd_v1, guide_version: SD-GUIDE-1.0
- branch: research/sharpe-decay-sd-v1 (off main @ f22851db5761)
- generated_at_utc: 2026-09-25T10:22:38.731678+00:00

## Scope (guide SS8.1)
SD-01 standardizes the Sharpe metric and builds the real INIT archive. It carries NO model victory/no-edge verdict -- that is SD-02/03's job. This report states only what was reused, what ran, its real cost, and which validity findings were fixed.

## Migration and finding dispositions (guide SS0.2)
| Finding | Disposition | Remedy in SD |
|---|---|---|
| SELF01_RIDGE_INTERCEPT | PRESENT | fp/selector_b.py's fit_ridge/predict_ridge are NOT reused for SD-02's B_SD_GLOBAL/C_SD_JM ridge models -- SD-02 must implement an intercept-... |
| F02 | PRESENT | SD-GUIDE-1.0 SS4.1's own strict INIT/VALIDATION/FINAL role separation plus explicit prior_mature_origins_at_each_cutoff counting (SD01.3) re... |
| F03a | PRESENT | New minY(Y_hat) selection rule built fresh for SD (SS3.4); tested via S1-T09-DECAY-RANKING with a forced two-candidate fixture. |
| F03b | PRESENT | SD-GUIDE-1.0 SS3.2 requires A/B/C to select from the identical full eligible pool at each cutoff; the 16-representative panel is used ONLY t... |
| F05 | PRESENT | SD-GUIDE-1.0 SS3.4/SS5.6 requires C fit/scored independently of B's admission status at every model-ready fold. Tested via S1-T10-C-INDEPEND... |
| F05_F06_model | SUPERSEDED_PATH_QUARANTINED | SD builds an entirely new JM K=2 model against a Sharpe-decay target (SS5); the old model/target stay quarantined as historical evidence onl... |
| F07 | PRESENT | SD-GUIDE-1.0 requires >=12 full paired D1 rows and explicit origin-vs-activation timestamp fields in D2 (SS2.4, SS4.2, SS10.3); measured fre... |
| F04 | NEEDS_RUNTIME | SD01.5's actual-path repair pass will verify feature-only inference (S1-T07-FEATURE-ONLY) directly against SD's own new code before this dis... |
| F10 | NEEDS_RUNTIME | SD's own gate-receipt/replay verifier (SD-GUIDE-1.0 SS11.2, SS13.1-13.2) is built with these two known failure shapes as explicit regression... |

## Explicit rule changes (guide SS0.3)

- **Primary target: predicted forward utility (mean daily return / bps-per-day), gui** -> **Primary target: relative Sharpe decay Y = D(theta) - D(anchor), D = SR_IS - SR_F**
- **Arms: A_STOCK_CAL / B_FP_PERSISTENCE / C_FP_CONTEXT, plus FP-09's SELECTOR_FIXED** -> **Arms: A_M4 (stock Mode 4) / B_SD_GLOBAL (global Sharpe-decay ridge) / C_SD_JM (B**
- **Candidate pool: FP-04's 12-origin/192-record archive, representative_subset_size** -> **Candidate pool: strictly separate 12 INIT + 12 VALIDATION + 12 FINAL origins (36**
- **Selection rule: winner = max(predicted_forward_utility) among eligible candidate** -> **Selection rule: winner = min(Y_hat) among eligible candidates, eligibility via Q**
- **C's selection: fp/locked_study.py's walk_forward_c_selection short-circuits to F** -> **C is evaluated independently of B's admission/fallback status at every model-rea**
- **FP-05/06's ridge-regression target (mean-return based) and context model (JM/M0 ** -> **SD's B/C ridge regression targets relative Sharpe decay; C uses a fresh JM K=2 m**
- **FP-07's D1 table: only 7/36 (arm, origin) rows carried a real value (disclosed s** -> **SD requires a full 12 paired D1 rows per comparison, plus explicit origin-vs-act**
- **Hyperparameters (Selector B/C's ridge alpha) selected via nested walk-forward OO** -> **SD freezes ALL hyperparameters (JM penalty c, ridge lambda_global/lambda_state, **
- **FP-01's gate_receipt.json written twice by design (fixed then); FP-10's first at** -> **SD's own detached-seal/replay verifier must not require provenance fields (cache**

## Timeline feasibility (guide SS4, SD01.3)
- data_role_exception: dec-61772d86c9594c69 (outer_evaluation opened for this study only)
- measured full usable interval: 2020-01-06 .. 2026-09-09 (2438 days)
- feasibility verdict: **FEASIBLE with 172 days of disclosed margin beyond a 7-day boundary-gap pad at each role transition**
- INIT: 2020-07-04 .. 2022-03-12 (fully inside development, retrospective)
- VALIDATION: 2022-05-14 .. 2024-01-20 (mostly development, tail crosses into outer_evaluation)
- FINAL: 2024-03-23 .. 2025-11-29 (entirely inside the genuinely fresh outer_evaluation span)

## Resource qualification (guide SS11, SD01.6)
- real 8-trial micro-profile: 225.04639s, peak RSS 1019.4 MiB (registered budget 4 GiB -- no exception needed)
- extrapolated total for the full 12-origin/128-trial build: 9.0 - 12.0 hours

## Real INIT archive build (guide SS8.2 SD01.7) -- ALL REAL, MEASURED NUMBERS

- **12/12 origins built**, real 128-trial search each, real IS180/FWD56 canonical Sharpe for a 16-candidate representative panel + anchor at each origin
- total wall time: **31817.97s (~8.84h)** (search-only: 25140.44s / ~6.98h)
- total label rows: 192 (12 origins x 16 panel each)
- IS Sharpe status OK: **192/192**
- FWD Sharpe status OK: **192/192**
- anchor relative_decay_Y == 0.0 exactly: **12/12 origins** (the anchor-zero-by-construction guarantee, verified on every real origin)

| origin | search trials | unique candidates | panel | wall seconds |
|---|---:|---:|---:|---:|
| 2020-07-04 | 128 | 115 | 16 | 2994.68 |
| 2020-08-29 | 128 | 100 | 16 | 2686.15 |
| 2020-10-24 | 128 | 96 | 16 | 2565.96 |
| 2020-12-19 | 128 | 105 | 16 | 2704.13 |
| 2021-02-13 | 128 | 102 | 16 | 2608.68 |
| 2021-04-10 | 128 | 106 | 16 | 2687.66 |
| 2021-06-05 | 128 | 103 | 16 | 2623.66 |
| 2021-07-31 | 128 | 102 | 16 | 2598.98 |
| 2021-09-25 | 128 | 96 | 16 | 2431.02 |
| 2021-11-20 | 128 | 102 | 16 | 2529.50 |
| 2022-01-15 | 128 | 102 | 16 | 2512.23 |
| 2022-03-12 | 128 | 112 | 16 | 2875.32 |

## Glossary
- **INIT origin** (guide SS4.1: one of the 12 chronologically-first origins whose own matured real archive record seeds the model-training history VALIDATION will later draw on -- never itself a model-performance comparison)
- **representative panel** (guide SS3.5: a deterministic, <=16-candidate subset of an origin's full real candidate pool, ranked by the search's own cheap mean_is_sharpe proxy, ALWAYS including the stock anchor -- used only to bound how many candidates get real forward-evaluation compute, never to shrink what B/C will predict over)
- **canonical Sharpe** (guide SS2.1: a Sharpe ratio recomputed from raw daily equity via this lab's own already-tested time_edge_contracts.daily_returns + ra07_stats_primitives.sharpe primitives -- exact day-count enforced, missing days raise rather than silently returning 0%, explicitly NOT quantbt's own built-in sharpe()/daily_equity, both verified to have a silent-failure mode)
- **relative Sharpe decay Y** (guide SS3.3: Y = D(candidate) - D(anchor), where D = SR_IS - SR_FWD -- the anchor's own Y is forced to exactly 0.0 by the contrast architecture itself, not by a fitted intercept, verified on all 12 real origins here)
- **anchor** (guide SS3.3: the raw stock Mode 4 winner at an origin, the contrast-zero reference every other candidate's relative decay is measured against)
- **outer_evaluation data-role exception** (this study's own disclosed, one-time, scoped opening of the 2024-01-01-onward interval, previously an untouched holdout across the whole FP study -- decision dec-61772d86c9594c69, scoped to sharpe_decay_sd_v1 only)

## Permitted conclusions
- Technical: the canonical Sharpe wrapper reuses already-tested lab primitives (G1-SHARPE); the minY selection rule and C-independence are structurally proven, not just conventionally avoided (G1-WIRING); the 36-origin timeline is real and feasible with disclosed margin (G1-TIMELINE); the real INIT archive is complete, 192/192 IS and 192/192 FWD canonical Sharpe values computed cleanly, the anchor-zero invariant held on every real origin (G1-ARCHIVE); real compute cost was measured before and during the full build, staying within the registered budget throughout (G1-RESOURCE).
- Research: **NOT_ASSESSED**. SD-01 makes no claim about whether JM reduces Sharpe decay -- it only builds and validates the measurement infrastructure and the real candidate archive SD-02 will train validation-fold models against. No model has been fit, no JM recipe has been chosen, no decay reduction has been estimated.
- Owner review: PENDING. SD-02 needs its own explicit R-18 approval before it begins.
