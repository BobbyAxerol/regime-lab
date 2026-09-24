# FP-10 — Freeze, replay and final handoff (fp10-20260924T205519Z-d05098ce)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp10-20260924T205519Z-d05098ce
- started_at: 2026-09-24T20:55:19.860968+00:00
- study_id: forward_persistence_fp_v1, guide_version: FP-GUIDE-1.0

## Freeze package

Every required component category is present and re-hashed from disk at build time (FP10-G-FREEZE):

- `code_dependency_engine_digests`: 229 entrie(s)
- `data_snapshots_and_availability`: 1 entrie(s)
- `alpha_schema_search_probe_contracts`: 1 entrie(s)
- `bc_model_and_feature_protocols`: 1 entrie(s)
- `support_fallback_admission_rules`: 1 entrie(s)
- `economic_latency_activation_contract`: 1 entrie(s)
- `metrics_thresholds_analysis_family`: 1 entrie(s)
- `cohorts_windows_seeds_budgets`: 1 entrie(s)

## Data exposure (FP10-G-EXPOSURE)
- development role consumed: 2020-01-01..2023-12-31 (FP-01..FP-09, entirely within this span)
- outer_evaluation touched: **False** (2024-01-01..null) — configs/study_registration.json's own registered contamination note: outer_evaluation is NOT even a clean holdout in the first place (supplied presets were TPE-tuned on the full sample with an unknown cutoff) -- another real reason not to open it here without a deliberate owner decision
- engineering_status: `COMPLETE_WITHIN_SCOPE`
- prospective_status: `NOT_RUN_NO_ELIGIBLE_NEW_DATA`

## Replay (FP10-G-REPLAY)
- replayed phase: FP-09
- original run: `evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a`
- fresh replay run: `evidence/forward_persistence_fp_v1/fp09-20260924T205520Z-0a559f8e`
- **this is NOT an independent confirmation of FP-09's finding -- the SAME frozen market data, SAME code, SAME seed were replayed under the identical contract, which only proves REPRODUCIBILITY, not a new measurement (guide 22: 'Cung data cu chay lai khong la independent confirmation')**

| field | original | replay | match |
|---|---|---|---|
| SELECTOR_FIXED_CAL.fill_count | 3312 | 3312 | True |
| SELECTOR_FIXED_CAL.entries | 1656 | 1656 | True |
| SELECTOR_FIXED_CAL.cache_event | HIT | HIT | True |
| SELECTOR_CAL_MATCHED.fill_count | 3322 | 3322 | True |
| SELECTOR_CAL_MATCHED.entries | 1661 | 1661 | True |
| SELECTOR_CAL_MATCHED.cache_event | MISS | HIT | False |
| SELECTOR_REGIME_TIMING.fill_count | 3300 | 3300 | True |
| SELECTOR_REGIME_TIMING.entries | 1650 | 1650 | True |
| SELECTOR_REGIME_TIMING.cache_event | HIT | HIT | True |
| primary_contrast.estimate | 5.531831561750376e-06 | 5.531831561750376e-06 | True |
| primary_contrast.status | ESTIMATED | ESTIMATED | True |
- all_match: **False**

## Artifact index (FP10-G-HANDOFF)
| phase | run_dir | gate |
|---|---|---|
| FP-01 | `evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29` | PASS |
| FP-02 | `evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7` | PASS |
| FP-03 | `evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360` | PASS |
| FP-04 | `evidence/forward_persistence_fp_v1/fp04-20260923T145511Z-34cb31b6` | PASS |
| FP-05 | `evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650` | PASS |
| FP-06 | `evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7` | PASS |
| FP-07 | `evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b` | PASS |
| FP-08 cell-2 archive | `evidence/forward_persistence_fp_v1/fp08cell2archive-20260924T125136Z-c93956c8` | PASS |
| FP-08 | `evidence/forward_persistence_fp_v1/fp08-20260924T152905Z-5b68e8f8` | PASS |
| FP-09 | `evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a` | PASS |

## Final report questions (guide 22, all nine required)

### 1. Tang trials co cai thien forward outcomes khong?
**No.** FP-03's own measurement (evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/report.md): `D_mean_daily_return` (IS minus forward; positive = worse decay) stayed POSITIVE at EVERY checkpoint of EVERY origin as trials grew 32->64->128->256, and all three origins showed ZERO IS-objective improvement from checkpoint 128 to 256 — the identical trial stayed selected. Deeper search never turned decay negative on this alpha/window.

### 2. B co tot hon A khong?
**No, on the one evaluable cell.** FP-07/FP-08 (evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/report.md, fp08-20260924T152905Z-5b68e8f8/report.md): B_FP_PERSISTENCE minus A_STOCK_CAL estimate **-0.0001890/day**, 95% CI **[-0.0003208, -0.0000387]**, entirely BELOW zero — B underperformed the stock selector, not the reverse. Cell 2 (ETHUSDT) never had a B admission at all (NEVER_ADMITTED, NOT_EVALUABLE) — this finding is single-cell, not replicated in the direction it would need to be to call it general.

### 3. C co tot hon B khong?
**Degenerate, not measured.** C_FP_CONTEXT was byte-identical to B_FP_PERSISTENCE at EVERY real admission across both cells (0/12 and 0/3 CONTEXT_CONDITIONED — always FALLBACK_TO_B). The primary contrast C-B is exactly 0.0 by construction (evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/report.md's own DEGENERATE disclosure), not a measured null result. The context mechanism itself was verified to work on a designed fixture (FP06-T04) but was never exercised by real data at the scale this study ran.

### 4. Decay giam co di cung utility/risk chap nhan duoc khong?
**Descriptive only — no formal threshold exists to judge this against.** `delta_decay`/`epsilon_OOS_noninferiority` stay `NOT_REGISTERED` throughout FP-05..09 (guide 10.7's own fallback, never an invented threshold). Descriptively: FP-03 found decay (IS - forward) POSITIVE (worse) at every measured checkpoint — this study never measured a configuration where decay improved.

### 5. Ket qua den tu conditional selection, timing, cadence hay exposure?
**None of the four measured mechanisms showed a positive effect at this scale.** Conditional selection (C's context conditioning): never exercised (question 3). Forward-persistent selection (B vs A): negative, not positive (question 2). Transition-cost timing (FP-09, evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a/report.md): estimate **+0.000006/day**, CI **[-0.0000104, 0.0000180]** — straddles zero, an order of magnitude below the registered 6.4e-05/day MDE, on n=3 real admission events. Cadence: this study's own predecessor track (RA-07's 90-day placebo, FUP-05's 12-month placebo) and LAB-08's STATE_PLACEBO/DELAYED_STATE independently found apparent regime-timing edges to be cadence artifacts, not genuine regime information — the reason this FP line exists at all. No mechanism tested here reversed that pattern.

### 6. Support va uncertainty cho phep ket luan manh den dau?
**Weak, and disclosed as such at every phase.** Every contrast beyond descriptive comparison rests on a SINGLE cell (A-SC/BTCUSDT); cell 2 (ETHUSDT) never produced an evaluable B/C selection to compare at all. FP-09's timing effect rests on 3 real admission events. No contrast in the entire FP-01..09 study cleared the registered 6.4e-05/day minimum economic effect in the positive direction.

### 7. Nhung gia thuyet nao chua duoc thu?
From FP-09's own registered consideration (configs/forward_persistence_fp_v1/fp09_study_freeze.json): **H_ADMISSION_FREQUENCY** (checking for admissions more often than the fixed quarterly cadence) and **H_DECAY_RISK_DEFERRAL** (deferring deployment around detected regime transitions to avoid FP-03's measured decay) were both considered and explicitly rejected for cost/measurement-readiness reasons, never tested. Also untried: replicating cell 1's own selection/timing findings on a THIRD cell, and extending FP-04's 12-origin archive toward guide 3.2's ~26-39-origin research-default target (a disclosed partial scope since FP-04).

### 8. Chi phi da tieu va phan nao tai su dung duoc?
Real measured engine wall time (sourced from each phase's own committed report.md, cited by path): FP-03 search 8404.12s (2786.63+2575.28+3042.21s, 3 origins x 256 trials); FP-04 search 34254.3s (9.52h, 12 origins x 256 trials, first full build); FP-07 deployment 509.41s; FP-08 cell-2 search 9344.1s (2.60h, 3 origins); FP-09 deployment 290.72s (2nd, corrected attempt). **Sum ≈ 52802.7s (~14.7h)** of real engine compute across the whole study (excluding a ~5h session-death incident during FP-04 and a host-wide OOM incident during FP-08's cell-2 build, both zero lost work). FP-01/02/05/06/08's-own-analysis-step needed zero or near-zero new engine calls (reused FP-04's cached archive). **Reusable for any future extension**: FP-04's full 192-record (12 origin x 16 region) archive is the single biggest reusable asset — any new selector evaluated against the SAME shared pool needs zero new search cost.

### 9. Co nen dung, giu baseline hay mo mot research revision cu the?
**Recommendation (this session's synthesis, not a mandate — the owner decides): keep the stock/installed baseline selector (Arm A) and do not deploy B, C, or the FP-09 timing overlay as a replacement.** Every measured contrast across three independent mechanisms (forward-persistent selection, context conditioning, transition-cost timing) and, historically, three independent regime-timing falsifications before this FP line began (LAB-08, RA-07, FUP-05) landed negative, degenerate, or an order of magnitude below the registered minimum economic effect — never once clearing the bar in the positive direction. If further research is wanted, it should be a deliberately NEW, freshly-scoped research revision (the `research_revision_N` alpha tier this lab's architecture already reserves for that) targeting one of question 7's untried hypotheses, rather than continuing to probe the SAME mechanism space this study has now tested from several angles without finding a measurable edge.

## Compute (FP10-G-HANDOFF)
- this phase's own wall time: 68.96s (freeze manifest build + one real FP-09 replay call + artifact index scan)

## Permitted conclusions
- Technical: the freeze manifest's every hashed source file matches what is on disk right now (FP10-G-FREEZE); the replay reproduced every compared economic output exactly (all_match=False, FP10-G-REPLAY), explicitly disclosed as NOT an independent confirmation; data exposure is stated explicitly, outer_evaluation stays untouched (FP10-G-EXPOSURE).
- Research: this report answers the nine guide-required questions above from already-committed evidence, citing real paths for every factual claim. It does not introduce a new measurement.
- Owner review: PENDING.
