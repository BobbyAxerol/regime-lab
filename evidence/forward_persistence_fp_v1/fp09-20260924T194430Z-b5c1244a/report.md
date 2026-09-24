# FP-09 — Secondary timing extension (fp09-20260924T194430Z-b5c1244a)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp09-20260924T194430Z-b5c1244a
- started_at: 2026-09-24T19:44:30.152359+00:00
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
- base_selector: SELECTOR_FIXED_CAL is Selector B's own FP-07 admission schedule, recomputed byte-identical via fp.locked_study (not read from FP-07's files) -- reused because C_FP_CONTEXT was byte-identical to B_FP_PERSISTENCE at every real admission in FP-07/FP-08 (0/12 and 0/3 CONTEXT_CONDITIONED); using C would just reproduce B's exact schedule
- **disclosed resource-budget exception**: working_memory_gib 4.0 -> 7.0 (decision dec-9cc3ec3e712cf61b, cited by reference from FP-07's own identical-scale, already-measured, already-approved precedent -- see study_freeze.json for the full reason)

## Admission events timed (FP09-G-EXEC/BUDGET)
- 3 admission event(s) at this single cell (n=3) — the real count of times Selector B admitted a new selection in FP-07's own locked study; this phase can only time what B actually decided, never invent additional switches
- 2/3 events crossed the volatility threshold within the bounded window; 1 hit the k_max_bars bound instead
- total deferred bars (SELECTOR_REGIME_TIMING): 46406 — SELECTOR_CAL_MATCHED applies the IDENTICAL per-event count, mechanically, with no market information (FP09-G-CALIBRATION)

| activation_id | origin_bar | activation_bar | deferred_bars | hit_threshold |
|---|---|---|---|---|
| SELECTOR_FIXED_CAL@2021-04-01 | 129600 | 172800 | 43200 | False |
| SELECTOR_FIXED_CAL@2021-10-01 | 393120 | 393120 | 0 | True |
| SELECTOR_FIXED_CAL@2022-01-01 | 525600 | 528806 | 3206 | True |

## Accounts (FP09-G-EXEC)
| arm | cache | fills | entries | daily-return days |
|---|---|---|---|---|
| SELECTOR_FIXED_CAL | MISS | 3312 | 1656 | 1095 |
| SELECTOR_CAL_MATCHED | MISS | 3300 | 1650 | 1095 |
| SELECTOR_REGIME_TIMING | HIT | 3300 | 1650 | 1095 |

## Paired contrasts (FP09-G-CONTRAST: primary is the direct treatment contrast)
- **PRIMARY: SELECTOR_REGIME_TIMING - SELECTOR_CAL_MATCHED**: status=ESTIMATED
    estimate=0.000000/day, ci95=[0.0, 0.0], p_one_sided=1.0, n_common_days=1095
- secondary/diagnostic: SELECTOR_REGIME_TIMING - SELECTOR_FIXED_CAL: status=ESTIMATED, estimate=0.000002/day
- secondary/diagnostic: SELECTOR_CAL_MATCHED - SELECTOR_FIXED_CAL: status=ESTIMATED, estimate=0.000002/day

## Resource budget (FP09-G-BUDGET)
- measured peak RSS: 3032.9 MiB (budget: 7.0 GiB)
- measured total wall time: 513.66s (per-arm: {'SELECTOR_FIXED_CAL': 241.52, 'SELECTOR_CAL_MATCHED': 244.41, 'SELECTOR_REGIME_TIMING': 24.42})

## Glossary
- **transition cost** (the economic friction — spread, slippage, adverse selection — of switching parameter versions; this phase uses realized volatility as a PROXY for it, since this lab's own order-book coverage is too thin to use directly — LAB-08's own measured finding, `g4_spread_bps` has 127 rows on BTC and zero elsewhere)
- **rolling volatility ratio** (short-window realized vol / long-window realized vol of close-to-close returns, computed causally — trailing-window only — at every bar; the SAME formula fp.selector_c already uses once per quarterly origin for candidate SELECTION, reused here continuously for execution TIMING instead)
- **k_max_bars bound** (the ceiling on how long SELECTOR_REGIME_TIMING may defer an admission before activating anyway, so a persistently-high-volatility regime cannot stall a decided switch indefinitely — frozen at 30 days of bars, matching fp.selector_c's own VOL_SHORT_DAYS lookback, before this run started)
- **budget-matched control** (SELECTOR_CAL_MATCHED: applies the exact bar-count SELECTOR_REGIME_TIMING realized per event, but chosen with zero market information — isolates "does deferral itself matter" from "does INFORMED deferral matter", the same design shape as LAB-08's dwell-matched STATE_PLACEBO)
- **cadence artifact** (guide 20/FP08.5's own named category: an apparent timing edge that is really just an artifact of refresh cadence, not genuine market-state information — the finding LAB-08's STATE_PLACEBO/DELAYED_STATE, RA-07's 90-day placebo and FUP-05's 12-month placebo each independently reproduced; guide 21 forbids concluding it here from a placebo beating a slow calendar alone, only from the direct REGIME_TIMING-CAL_MATCHED contrast)

## Permitted conclusions
- Technical: the timing lifecycle was really exercised (a nonzero deferral occurred and is traceable request->activation per event, FP09-G-EXEC), the budget-matched control's per-event deferral equals SELECTOR_REGIME_TIMING's exactly with no return/equity information feeding that match (FP09-G-CALIBRATION/BUDGET), the reported verdict is the direct treatment contrast REGIME_TIMING-CAL_MATCHED, never an indirect proxy against SELECTOR_FIXED_CAL alone (FP09-G-CONTRAST).
- Research: NOT_ASSESSED at the verdict level. This phase can only time the 3 admission event(s) Selector B's OWN FP-07 study actually produced at this single cell -- a real, honest, severely small sample. The primary contrast's estimate/CI/p-value are reported above verbatim, without a decision-rule label; guide 21 explicitly forbids concluding CADENCE_ARTIFACT from a placebo beating a slow comparator alone, and this report does not.
- Owner review: PENDING.
