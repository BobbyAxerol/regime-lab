# FP-07 — Locked A/B/C study (fp07-20260923T190207Z-5a401d3b)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b
- started_at: 2026-09-23T19:02:07.308921+00:00
- alpha: A-SC, symbol: BTCUSDT, 12 origins (reused verbatim from FP-04's frozen grid)
- shared continuous frame: 2021-01-01 .. 2024-01-01 (exclusive), 1576800 bars

## Study freeze (guide 19 precondition, written before any account ran)
- alpha_B=10.0 (source: evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/model_selection.json:selected_alpha)
- alpha_C=10.0 (source: evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7/oof_diagnostics_c.json:selected_alpha_c)
- pre-run cost estimate: 3.77 min/arm, 11.3 min total (from a real 6979 bars/sec pilot measurement)
- **disclosed resource-budget exception**: working_memory_gib 4.0 -> 7.0 (decision dec-9cc3ec3e712cf61b, evidence/regime_time_edge_ra_v1/owner_decisions.jsonl) -- a real MemoryError at ~1.2-1.36M bars against the registered 4 GiB cap on a first real attempt, measured via 4 real probe runs before this exception was applied; the registered 4 GiB budget is unchanged for every other phase/call in this lab

## Selections per origin (all three arms, same shared pool)
| origin | A source | B source | C source |
|---|---|---|---|
| 2021-01-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2021-04-01 | A_STOCK_INSTALLED | B_SELECTED | FALLBACK_TO_B |
| 2021-07-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2021-10-01 | A_STOCK_INSTALLED | B_SELECTED | FALLBACK_TO_B |
| 2022-01-01 | A_STOCK_INSTALLED | B_SELECTED | FALLBACK_TO_B |
| 2022-04-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2022-07-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2022-10-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2023-01-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2023-04-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2023-07-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |
| 2023-10-01 | A_STOCK_INSTALLED | FALLBACK_TO_A | FALLBACK_TO_A |

- Arm B admitted a new selection at 3/12 origins (9 had NO new admission -- the account kept whatever version was already active, or stayed FLAT_UNTIL_READY pre-first-admission; never a borrowed Arm A value)
- Arm C used a context-conditioned prediction at 0/12 origins
- **DEGENERATE: C_FP_CONTEXT == B_FP_PERSISTENCE in this run.** At all 3 origins where B admitted a new selection (2021-04-01, 2021-10-01, 2022-01-01), C's own utility-maximizing candidate was out-of-distribution relative to its training window's context range, so C fell back to B's exact prediction every time (source=FALLBACK_TO_B, never CONTEXT_CONDITIONED) -- C's params are IDENTICAL to B's at every real admission, making the two accounts byte-for-byte the same (same fills, same D1). This is guide 20/FP08.5's own named outcome category: *"C≈B vì fallback → Context mechanism chưa được exercise đủ"* (C looks like B because of fallback -> the context mechanism was not exercised enough). The PRIMARY contrast below (C-B) is therefore DEGENERATE BY CONSTRUCTION in this run -- estimate exactly 0.0, not a measured absence of effect.

## Accounts (FP07-G-EXEC/ACCOUNT)
| arm | fills | entries | daily-return days | window |
|---|---|---|---|---|
| A_STOCK_CAL | 1460 | 730 | 1095 | 2021-01-01 .. 2023-12-31 |
| B_FP_PERSISTENCE | 3312 | 1656 | 1095 | 2021-01-01 .. 2023-12-31 |
| C_FP_CONTEXT | 3312 | 1656 | 1095 | 2021-01-01 .. 2023-12-31 |

## D1 table (FP07-G-DECAY) -- per-selection IS vs realized forward label
- convention: D = IS - forward; positive = worse decay (guide 8.5, FP-01 repaired)
- Arm A: 1/12 origins had an exact params match to a region-archive record (Arm A's stock pick is measured, not assumed, to rarely coincide with a region medoid)
- 7/36 rows carry a real D1 value; the rest are null with a disclosed reason (no forward-labelled record for that selection)
  - A_STOCK_CAL: mean D1=-0.000413 over 1 selection(s)
  - B_FP_PERSISTENCE: mean D1=0.000176 over 3 selection(s)
  - C_FP_CONTEXT: mean D1=0.000176 over 3 selection(s)

## Paired contrasts (FP07-G-SCOPE: primary C-B, secondary diagnostic only)
- **PRIMARY: C_FP_CONTEXT - B_FP_PERSISTENCE**: status=ESTIMATED
    estimate=0.000000/day, ci95=[0.0, 0.0], p_one_sided=1.0, n_common_days=1095
- secondary/diagnostic: B_FP_PERSISTENCE - A_STOCK_CAL: status=ESTIMATED, estimate=-0.000189/day
- secondary/diagnostic: C_FP_CONTEXT - A_STOCK_CAL: status=ESTIMATED, estimate=-0.000189/day

## Resource budget (FP07-G-COST)
- measured peak RSS: 3357.7 MiB (budget: 7.0 GiB)
- measured total wall time: 509.41s across 3 arms (per-arm: {'A_STOCK_CAL': 25.02, 'B_FP_PERSISTENCE': 241.55, 'C_FP_CONTEXT': 236.22})

## Glossary
- **primary cell** (guide 19: the one alpha/symbol combination this locked study runs -- A-SC/BTCUSDT, the same cell FP-03/04/05/06 already qualified and built on)
- **whole-policy fallback period** (guide 19 item 8: an origin where a forward-persistent arm has no new admission -- too little matured training history, or no candidate cleared the utility/support floor -- so the account keeps its currently active version, or stays FLAT_UNTIL_READY before its first-ever admission; never a value borrowed from Arm A)
- **D1** (guide 8.5/FP-01: a selection's own in-sample mean daily return minus its OWN realized forward-window mean daily return; positive means the selection performed worse going forward than in-sample -- decay)
- **block bootstrap** (time_edge.inference.block_mean: RA-07/RF-05's own registered 28-day non-overlapping block resample used for every paired contrast's CI/p-value in this lab, reused verbatim here, never reimplemented)
- **primary vs secondary contrast** (guide 19's own output list separates 'paired contrasts' without ranking one as the sole claim; this report treats C-B as PRIMARY per FP-GUIDE-1.0's stated research question migration -- which parameter REGION a forward-persistent selector picks, with/without context -- and B-A/C-A as diagnostic context, not a second primary claim)
- **RLIMIT_AS / resource-budget exception** (the OS-level ceiling on a process's virtual address space this lab uses to turn an uncontrolled OOM kill into a catchable Python MemoryError, CLAUDE.md's registered hard boundary of <=4 GiB working set; FP-07's own 3 run_deployment calls needed a disclosed, owner-approved, one-time exception to 7 GiB -- see 'disclosed resource-budget exception' above -- because a single continuous account over ~1.58M bars is a new scale for this lab, never because the registered 4 GiB budget changed for anything else)

## Permitted conclusions
- Technical: all three arms selected from the SAME shared per-origin candidate pool (FP07-G-POOL), all three ran a real continuous deployment account over the identical 1576800-bar shared frame with real fills (FP07-G-EXEC), daily returns reconcile to a common calendar window (FP07-G-ACCOUNT), D1 values are recomputed from their own raw (is_mean, forward_label) pairs and fallback origins stay null with a reason rather than a fabricated number (FP07-G-DECAY), and the measured compute cost is disclosed against the pre-registered estimate and the applied 7.0 GiB budget (the registered 4 GiB budget's own disclosed, owner-approved exception -- see above) (FP07-G-COST).
- Research: NOT_ASSESSED at the verdict level. FP-07 is ONE cell, ONE replication, on REAL market data with no placebo/randomization control of its own -- guide 19's own exit gate (FP07-G-SCOPE) forbids calling this a finished scientific study by itself. **FP-08 (replication, a second cell/seed, D2 continuations and the family-level inference guide 20 specifies) is required before ANY claim about whether context or forward-persistent selection helps.** The primary contrast's own estimate/CI/p-value are reported above verbatim, without a decision-rule label (FP08.5 owns those).
- Owner review: PENDING; FP-08 needs its own R-18 approval per the guide's phase sequencing, though it may already be covered by the owner's recorded open-ended auto-advance instruction -- verify against evidence/regime_time_edge_ra_v1/owner_decisions.jsonl before starting it.
