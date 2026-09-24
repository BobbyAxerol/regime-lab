# FP-09 — Secondary timing extension (fp09-20260924T205736Z-36daae3f)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp09-20260924T205736Z-36daae3f
- started_at: 2026-09-24T20:57:36.060309+00:00
- alpha: A-SC, symbol: BTCUSDT
- shared continuous frame: 2021-01-01 .. 2024-01-01 (exclusive), 1576800 bars (identical to FP-07's own span)

Scope: **COMPLETED**

## Hypothesis (guide 21: conditional phase, owner-delegated selection)
The owner delegated hypothesis SELECTION to this session. Three mechanisms were considered (recorded in full in study_freeze.json's `hypothesis.considered` block):
1. **H_ADMISSION_FREQUENCY** (check for admissions more often than quarterly) — rejected: FP-04-scale new search cost, and close to the 3x-falsified cadence-artifact shape.
2. **H_DECAY_RISK_DEFERRAL** (defer deployment around detected regime transitions to avoid FP-03's measured decay) — rejected: no measured causal link between regime transitions and elevated decay exists yet in this lab.
3. **H_TRANSITION_COST_TIMING** (defer an ALREADY-DECIDED Selector-B switch until realized volatility is locally low, a transition-cost proxy) — **chosen**: mechanistically distinct from "regime predicts which candidate" (tested and found to be a cadence artifact three times: LAB-08, RA-07, FUP-05), grounded in LAB-06's own measured switch-cost-dominates-edge finding, reuses already-causal infrastructure (fp.selector_c's ctx_volatility_ratio mechanism), bounded new compute.

## Timing design (frozen before any account ran)
- vol_threshold=1.0 (short-window/long-window realized-vol ratio at or below this defers no further)
- k_max_bars=43200 (30 days -- bounded fallback, never an unbounded wait)
- vol_short_days=30, vol_long_days=180 (SAME window lengths as fp.selector_c's already-frozen ctx_volatility_ratio, never invented fresh for this run)
- cal_matched_seed=20260924 (fixed before any account ran; SELECTOR_CAL_MATCHED draws its per-event deferral from Uniform(0, k_max_bars) with this seed, taking NO input from SELECTOR_REGIME_TIMING's own realized schedule)
- base_selector: SELECTOR_FIXED_CAL is Selector B's own FP-07 admission schedule, recomputed byte-identical via fp.locked_study (not read from FP-07's files) -- reused because C_FP_CONTEXT was byte-identical to B_FP_PERSISTENCE at every real admission in FP-07/FP-08 (0/12 and 0/3 CONTEXT_CONDITIONED); using C would just reproduce B's exact schedule

**Self-caught correction, disclosed** (full text in `study_freeze.json`'s `timing_design.self_caught_correction`): a first real run of this design (fp09-20260924T194430Z-b5c1244a, superseded) built SELECTOR_CAL_MATCHED by copying SELECTOR_REGIME_TIMING's own REALIZED per-event deferral verbatim -- both reduce to the identical origin_bar + deferred_bars formula, so the two schedules were mathematically guaranteed to be byte-identical, not an independent control. Caught by reading the real primary contrast (exactly 0.0, CI=[0,0]) and the account cache event (SELECTOR_REGIME_TIMING was a real cache HIT on SELECTOR_CAL_MATCHED's just-published entry) before reporting it -- the LAB-08 'Arm E was a copy of Arm D' shape, this time in code this phase wrote itself. Fixed to draw CAL_MATCHED's per-event deferral from Uniform(0, k_max_bars) with a fixed, pre-registered seed, taking NO input from REGIME_TIMING's realized schedule at all -- see cal_matched_seed above and FP09-G-CALIBRATION's own added identical-schedule check.
- **disclosed resource-budget exception**: working_memory_gib 4.0 -> 7.0 (decision dec-9cc3ec3e712cf61b, cited by reference from FP-07's own identical-scale, already-measured, already-approved precedent -- see study_freeze.json for the full reason)

## Admission events timed (FP09-G-EXEC/BUDGET)
- 3 admission event(s) at this single cell (n=3) — the real count of times Selector B admitted a new selection in FP-07's own locked study; this phase can only time what B actually decided, never invent additional switches
- 2/3 events crossed the volatility threshold within the bounded window; 1 hit the k_max_bars bound instead
- total deferred bars: SELECTOR_REGIME_TIMING=46406, SELECTOR_CAL_MATCHED=21889 (independently drawn from the SAME k_max_bars bound, NOT matched to REGIME_TIMING's realized total -- FP09-G-CALIBRATION)

### SELECTOR_REGIME_TIMING (informed by the causal rolling volatility ratio)
| activation_id | origin_bar | activation_bar | deferred_bars | hit_threshold |
|---|---|---|---|---|
| SELECTOR_FIXED_CAL@2021-04-01 | 129600 | 172800 | 43200 | False |
| SELECTOR_FIXED_CAL@2021-10-01 | 393120 | 393120 | 0 | True |
| SELECTOR_FIXED_CAL@2022-01-01 | 525600 | 528806 | 3206 | True |

### SELECTOR_CAL_MATCHED (seeded, market-blind)
| activation_id | origin_bar | activation_bar | deferred_bars |
|---|---|---|---|
| SELECTOR_FIXED_CAL@2021-04-01 | 129600 | 145622 | 16022 |
| SELECTOR_FIXED_CAL@2021-10-01 | 393120 | 395968 | 2848 |
| SELECTOR_FIXED_CAL@2022-01-01 | 525600 | 528619 | 3019 |

## Accounts (FP09-G-EXEC)
| arm | cache | fills | entries | daily-return days |
|---|---|---|---|---|
| SELECTOR_FIXED_CAL | HIT | 3312 | 1656 | 1095 |
| SELECTOR_CAL_MATCHED | HIT | 3322 | 1661 | 1095 |
| SELECTOR_REGIME_TIMING | HIT | 3300 | 1650 | 1095 |

## Paired contrasts (FP09-G-CONTRAST: primary is the direct treatment contrast)
- **PRIMARY: SELECTOR_REGIME_TIMING - SELECTOR_CAL_MATCHED**: status=ESTIMATED
    estimate=0.000006/day, ci95=[-1.0440846789665458e-05, 1.7951575940689564e-05], p_one_sided=1.0, n_common_days=1095
- secondary/diagnostic: SELECTOR_REGIME_TIMING - SELECTOR_FIXED_CAL: status=ESTIMATED, estimate=0.000002/day
- secondary/diagnostic: SELECTOR_CAL_MATCHED - SELECTOR_FIXED_CAL: status=ESTIMATED, estimate=-0.000004/day

## Resource budget (FP09-G-BUDGET)
- measured peak RSS: 1808.3 MiB (budget: 7.0 GiB)
- measured total wall time: 65.6s (per-arm: {'SELECTOR_FIXED_CAL': 20.72, 'SELECTOR_CAL_MATCHED': 21.31, 'SELECTOR_REGIME_TIMING': 20.35})

## Glossary
- **transition cost** (the economic friction — spread, slippage, adverse selection — of switching parameter versions; this phase uses realized volatility as a PROXY for it, since this lab's own order-book coverage is too thin to use directly — LAB-08's own measured finding, `g4_spread_bps` has 127 rows on BTC and zero elsewhere)
- **rolling volatility ratio** (short-window realized vol / long-window realized vol of close-to-close returns, computed causally — trailing-window only — at every bar; the SAME formula fp.selector_c already uses once per quarterly origin for candidate SELECTION, reused here continuously for execution TIMING instead)
- **k_max_bars bound** (the ceiling on how long SELECTOR_REGIME_TIMING may defer an admission before activating anyway, so a persistently-high-volatility regime cannot stall a decided switch indefinitely — frozen at 30 days of bars, matching fp.selector_c's own VOL_SHORT_DAYS lookback, before this run started)
- **budget-matched control** (SELECTOR_CAL_MATCHED: defers each admission by a bar count drawn from Uniform(0, k_max_bars) with a fixed, pre-registered seed — the SAME maximum bound SELECTOR_REGIME_TIMING could use, but chosen with zero market information and NO input from REGIME_TIMING's own realized schedule — isolates "does SOME deferral matter" from "does INFORMED deferral matter". An earlier version of this design instead copied REGIME_TIMING's own realized per-event deferral verbatim, which is mathematically guaranteed to reproduce its EXACT schedule — caught before this run, see the self-caught correction above)
- **cadence artifact** (guide 20/FP08.5's own named category: an apparent timing edge that is really just an artifact of refresh cadence, not genuine market-state information — the finding LAB-08's STATE_PLACEBO/DELAYED_STATE, RA-07's 90-day placebo and FUP-05's 12-month placebo each independently reproduced; guide 21 forbids concluding it here from a placebo beating a slow calendar alone, only from the direct REGIME_TIMING-CAL_MATCHED contrast)

## Permitted conclusions
- Technical: the timing lifecycle was really exercised (a nonzero deferral occurred and is traceable request->activation per event, FP09-G-EXEC); the budget-matched control's per-event deferral is drawn from a fixed, pre-registered seed independently of SELECTOR_REGIME_TIMING's own realized schedule, with no return/equity information feeding it and NO event landing on an identical bar to REGIME_TIMING's own (FP09-G-CALIBRATION/BUDGET); the reported verdict is the direct treatment contrast REGIME_TIMING-CAL_MATCHED, never an indirect proxy against SELECTOR_FIXED_CAL alone (FP09-G-CONTRAST).
- Research: NOT_ASSESSED at the verdict level. This phase can only time the 3 admission event(s) Selector B's OWN FP-07 study actually produced at this single cell -- a real, honest, severely small sample. The primary contrast's estimate/CI/p-value are reported above verbatim, without a decision-rule label; guide 21 explicitly forbids concluding CADENCE_ARTIFACT from a placebo beating a slow comparator alone, and this report does not.
- Owner review: PENDING.
