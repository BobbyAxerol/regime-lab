# LAB-08 — Controlled discovery on four alphas × five symbols

Generated from committed artifacts by `scripts/write_lab08_report.py`. Nothing is re-estimated here.

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **arm** | one complete way of running the study: a selector paired with a refresh schedule, delivered on its own continuous account | LAB-08 — A/B/C/D are the core factorial; E is an extension, never a substitute for C or D |
| **registered contrast** | a difference between two arms named BEFORE any of them ran, so the comparison cannot be chosen after seeing which one won | LAB-08 — B-A, C-A, D-B, D-C and the interaction (D-C)-(B-A) |
| **compute-matched** | two arms given the same number of searches and the same training memory, so neither can buy an advantage by being allowed to look more often | LAB-08 — the dynamic arms get the calendar's refresh COUNT; only the timing differs |
| **control** | a run designed to produce the same headline as the method for a DIFFERENT reason, so that reason can be ruled out. None is dropped for beating the proposal | LAB-08 / guide 10.2 — seven of them, staged rather than run as a Cartesian product |
| **placebo fidelity** | whether a fake state tape actually matches the real one's dwell and switch frequency. A placebo that switches more often loses on costs alone, and beating it proves nothing | LAB-08 — 37 real switches against 34 placebo, a ratio of 0.92 |
| **comparable interval** | the span every cohort in a comparison covers. Scoring each on its own longest window would credit a feature group for the period it happens to reach | LAB-08 L08.4 — the derivatives and liquidity cohorts cover far less than the core |
| **variance resolved out of fold** | the share of weighted variance a state assignment removes on data the fit never saw; scale-free, so it means the same thing for 8 features or 11 | LAB-08 — negative for most cohorts, meaning the states resolve nothing held-out |
| **Holm adjustment** | a step-down correction over a family of comparisons fixed in advance, so testing five contrasts does not manufacture one significant result | LAB-08 / guide 11.3 — applied to the registered contrast family |
| **NO_PROMISING_DESIGN** | a valid way for discovery to end. The exit gate does not require profit and forbids relabelling a negative result as a technical failure to justify a re-run | LAB-08 exit — one of exactly two permitted outcomes |
| **conclusion level** | a label from a vocabulary registered BEFORE any result, so a finding cannot be described with a word invented to fit it | LAB-04 — INCONCLUSIVE_SAMPLE / DESCRIPTIVE_VALUE / NET_PARAMETER_SELECTION_EDGE / FAILED_VALIDITY and three others |
| **minimum economic effect** | the smallest daily net-return difference the lab agreed in advance to call meaningful; anything smaller sits inside the cost-stress band | LAB-04 — 6.4e-05/day (0.64 bps/day), derived from cost uncertainty × turnover |
| **sign reversal** | the pooled result points one way while a subgroup points the other; averaging it away would be a false claim | LAB-04 — the pooled winner is B, but A-VWAP reverses |
| **declared post-hoc** | a diagnostic decided AFTER seeing results, marked as such so it can never be mistaken for a pre-registered test and can never change a conclusion | LAB-04 — the gate-bindingness grid |
| **NOT_READY** | an alpha that cannot be certified keeps all its cells with NULL metrics; booking it as PnL = 0 would bias every aggregate | LAB-02/04 — A-HASH, 5 cells |
| **read-lock** | re-hashing the source files a snapshot was copied from, to detect that upstream changed under a run | LAB-03 onward — the snapshot manifest IS the lock; every phase re-verifies it before it runs |
| **open trailing partition** | the current period's file, which the collector is still appending to; it is expected to change and is excluded from a primary read | LAB-03 onward — 9 of 627 files; a primary run reads closed partitions only |
| **ingest re-stamp** | an upstream file rewritten with a new `ingested_at` on every row while every MEASURED column stays identical — the digest moves, the numbers do not | LAB-04/05/06 read-lock — 23 closed `binance_futures_metrics_5m` partitions on 2026-09-10, read and proven unchanged, so no cohort is invalidated |
| **content revision** | an upstream change that a read cannot prove benign — a changed value, row count or schema, or a file that will not open. It still invalidates every cohort reading that product | LAB-04/05/06 read-lock — 0 measured; the benign verdict carries the burden of proof, never the invalidating one |
| **primary core** | the products and features a primary run actually consumes — the perpetual 1m bars and the 8 features covering all five symbols (G1×3, G2×2, G5×3) | guide 6.2 / LAB-03 — drift in a product outside it can invalidate a cohort but never the primary run |
| **data role** | the declared purpose of a date window: `development` permits fitting and design choices, `outer_evaluation` permits only a frozen-protocol run | development 2020-01-01→2023-12-31; LAB-04/05/06 stay inside it |


## What this phase claims and does not claim

This is **discovery**. It measures what robustness, regime timing and bank switching contribute, with the controls that would explain each away, and it ends by freezing one design or declaring **NO_PROMISING_DESIGN**. Guide L08's exit is explicit that profit is not required to close discovery and that a negative result is not a technical failure to be re-run until it wins.

The outer evaluation window is **not consulted anywhere in this phase**. Every number below comes from the development role.

## L08.1 — the protocol, frozen before any arm ran

Frozen **2026-09-10T14:50:28.446136+00:00**. The freeze script refuses to overwrite an existing stamp, and a test compares it against every factorial run's own timestamp: a protocol that can be rewritten after a result is not frozen.

- **20 cells** — 15 runnable, 5 NOT_READY carrying null metrics
- contrasts registered in advance: `B-A, C-A, D-B, D-C, (D-C)-(B-A)`
- controls: BANK_CALENDAR, CALENDAR_MATCHED, DELAYED_STATE, EXPOST_DIAGNOSTIC, RISK_ONLY, STATE_PLACEBO, USER_PRESET_REFERENCE
- seeds: `{"probe_design": 20260910, "model_multi_start": [11, 23, 37, 51], "placebo": 20260911}`
- stage **discovery**, outer window consumed: **False**

## Data provenance — which historical data this phase read

- snapshot **`server_core_v1`**, byte-copied under `snapshots/server_core_v1/` (627 files, **22,543,243 rows**, 1449 MB)
- read from `/root/bobby/pool_alpha/alphas_storage/_get_data/storage` between `2026-09-09T20:12:26` and `2026-09-09T20:15:47` UTC, copy mode **byte_copy**
- closed partitions **618**, open trailing **9** — only closed partitions are primary-eligible

- read-lock re-verification: **EXTERNAL_VINTAGE_RESTAMP_ONLY**, primary run valid **True**
  - closed-partition drift read and classified: **0 content revisions**, **23 ingest re-stamps** (measurements proven identical)

### What the snapshot holds

| product | symbols | files | rows | span |
|---|---|---|---|---|
| `crypto_binance_futures_1m` | BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT | 390 | 16,891,503 | 2020-01-01 → 2026-09-09 |
| `crypto_binance_futures_metrics_5m` | BTCUSDT, ETHUSDT | 131 | 1,134,907 | 2020-09-01 → 2026-09-09 |
| `crypto_binance_orderbook_snapshot_1h` | BTCUSDT | 2 | 719 | 2026-08-10 → 2026-09-09 |
| `crypto_binance_spot_1m` | BTCUSDT | 104 | 4,516,114 | 2018-01-01 → 2026-08-07 |

### Per-symbol usable history (perpetual 1m, the primary venue)

| symbol | first bar | last bar | rows | first decision bar after warmup |
|---|---|---|---|---|
| BTCUSDT | 2020-01-01 00:00 | 2026-09-09 20:10 | 3,519,131 | 2020-01-06 00:00 |
| ETHUSDT | 2020-01-01 00:00 | 2026-09-09 20:12 | 3,519,133 | 2020-01-06 00:00 |
| SOLUSDT | 2020-09-14 07:00 | 2026-09-09 20:12 | 3,148,633 | 2020-09-19 07:00 |
| BNBUSDT | 2020-02-10 08:01 | 2026-09-09 20:12 | 3,461,052 | 2020-02-15 08:01 |
| DOGEUSDT | 2020-07-10 09:00 | 2026-09-09 20:13 | 3,243,554 | 2020-07-15 09:00 |

### What THIS phase consumed

- symbols: **BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT**
- products: `crypto_binance_futures_1m`
- data role **development**, window **2021-01-01 → 2023-12-31**
- **15 of 20** cells ran; 5 are NOT_READY with null metrics and stay in the denominator
- each arm is ONE continuous account delivered through LAB-07's machinery, not a sum of independently evaluated folds
- regime states for all five symbols were fitted with LAB-05's own code, parameterised by symbol rather than reimplemented

### How the raw bars are read

The lab does NOT call `data_loader.py` at run time. The loader is copied read-only into `vendor_readonly/loader_snapshot/`, pinned by SHA-256, and parsed STATICALLY so its reader classes tell the lab which storage path holds which product (guide 6.1: inventory by product, not by assumed class name). The bars are then read directly from the lab's own byte-copied parquet.

That distinction is measured, not asserted: `scripts/verify_loader_parity.py` calls the pinned loader (`sha256 99612d99ada25732…`) on 15 partitions (each symbol's first, middle and last closed partition) and diffs its output against the same bytes read directly. **10 of 15 disagree**, always on the same column.

| symbol | partition | stored dtype | bars with a fractional volume | bars a cast sends to zero | columns differing |
|---|---|---|---|---|---|
| BTCUSDT | 2020-01 | `float64` | 44,594 | 92 | volume |
| BTCUSDT | 2023-05 | `float64` | 44,598 | 0 | volume |
| BTCUSDT | 2026-08 | `float64` | 44,594 | 41 | volume |
| ETHUSDT | 2020-01 | `float64` | 44,548 | 58 | volume |
| ETHUSDT | 2023-05 | `float64` | 44,603 | 0 | volume |
| ETHUSDT | 2026-08 | `float64` | 44,591 | 0 | volume |
| BNBUSDT | 2020-02 | `float64` | 28,032 | 1 | volume |
| BNBUSDT | 2023-06 | `float64` | 42,737 | 0 | volume |
| BNBUSDT | 2026-08 | `float64` | 44,174 | 0 | volume |
| SOLUSDT | 2020-09 | `int64` | 0 | 0 | — |
| SOLUSDT | 2023-09 | `int64` | 0 | 0 | — |
| SOLUSDT | 2026-08 | `float64` | 44,176 | 0 | volume |
| DOGEUSDT | 2020-07 | `int64` | 0 | 0 | — |
| DOGEUSDT | 2023-08 | `int64` | 0 | 0 | — |
| DOGEUSDT | 2026-08 | `int64` | 0 | 0 | — |

MarketDataLoaderBase._normalize casts volume to int64. Symbols whose stored volume is fractional lose the fraction on every bar, and a bar under 1.0 unit with real trades becomes volume 0. Symbols already stored as int64 are unaffected, so the defect is invisible on exactly the symbols one would test first.

reading the parquet directly preserves the stored resolution; panel.normalize_numeric_dtypes coerces to float64 on read so a feature's dtype never depends on which month it came from

Largest measured loss — **BTCUSDT 2026-08**: 44,594 of 44,640 bars differ, **0.515%** of the partition's total volume is lost, and **41** bars with real trades become volume 0. Those bars feed the G2 activity and taker-imbalance features, where a zero denominator is masked rather than epsilon-padded — so the truncation would have removed observations, not merely blurred them.

Guarded by `test_t21_resampling_never_truncates_real_volume`, `test_t21_stored_volume_dtype_varies_and_is_coerced` and `test_loader_endpoint_parity_artifact_matches_a_live_call`.

## L08.2 — the factorial

| alpha | symbol | A | B | C | D | E |
|---|---|---|---|---|---|---|
| A-HASH | BTCUSDT | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* |
| A-HASH | ETHUSDT | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* |
| A-HASH | SOLUSDT | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* |
| A-HASH | BNBUSDT | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* |
| A-HASH | DOGEUSDT | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* | *NOT_READY* |
| A-HMA | BTCUSDT | +2.71% | +4.40% | +6.51% | +7.70% | +7.70% |
| A-HMA | ETHUSDT | -2.09% | +3.59% | -2.47% | +1.22% | +1.22% |
| A-HMA | SOLUSDT | +1.60% | +1.99% | +5.01% | -3.55% | -3.55% |
| A-HMA | BNBUSDT | +4.23% | +4.23% | -2.83% | -0.08% | -0.08% |
| A-HMA | DOGEUSDT | +1.04% | +3.39% | +2.61% | +2.91% | +2.91% |
| A-SC | BTCUSDT | +0.45% | +5.34% | -3.42% | +4.22% | +4.22% |
| A-SC | ETHUSDT | +12.77% | +12.90% | +2.30% | +11.03% | +11.03% |
| A-SC | SOLUSDT | +48.88% | +80.53% | +39.69% | +41.76% | +41.76% |
| A-SC | BNBUSDT | +19.50% | +56.69% | +55.31% | +56.72% | +56.72% |
| A-SC | DOGEUSDT | +52.07% | +66.08% | +59.20% | +66.08% | +66.08% |
| A-VWAP | BTCUSDT | -3.50% | -4.40% | +2.65% | -0.57% | -0.57% |
| A-VWAP | ETHUSDT | +1.16% | -1.01% | +4.99% | -1.01% | -1.01% |
| A-VWAP | SOLUSDT | -18.73% | -10.85% | +10.87% | +9.55% | +9.55% |
| A-VWAP | BNBUSDT | +0.17% | -0.78% | -2.02% | -3.62% | -3.62% |
| A-VWAP | DOGEUSDT | +8.97% | +7.10% | +17.45% | +1.03% | +1.03% |

Wall time **10942s**. A cell that is NOT_READY keeps null metrics — never a PnL of 0, which would bias every aggregate (guide 13.2).

## The registered contrasts

| contrast | mean daily difference | cells | sign test | direction | baseline |
|---|---|---|---|---|---|
| `B-A` | +0.000046 | 15 | p=0.1796 | 10+ / 4− | **not untouched** |
| `C-A` | +0.000038 | 15 | p=0.6072 | 9+ / 6− | **not untouched** |
| `D-B` | -0.000013 | 15 | p=0.2668 | 4+ / 9− | — |
| `D-C` | -0.000004 | 15 | p=1.0000 | 8+ / 7− | — |
| `(D-C)-(B-A)` | -0.000050 | 15 | p=0.0352 | 3+ / 12− | **not untouched** |
| `E-B` | -0.000013 | 15 | p=0.2668 | 4+ / 9− | — |

`B-A, C-A, (D-C)-(B-A)` are measured against **A_legacy_selection_adjusted**. The caveat is carried ON each of those contrasts, not only in the section below, so a contrast lifted out of this table cannot lose it (T54).

> a paired sign test over cells: it asks only whether the direction is consistent, because daily crypto returns are not iid (guide 11.3)

The interaction is the only contrast with a nominally significant sign test (**p=0.0352**) and it is **negative** (-5.022e-05). After Holm adjustment over the registered family it is **p=0.1758** — not significant, and that is the number that counts.

> **Arm E is not a fifth arm on this run.** It is identical to arm D in 15/15 cells — LAB-06 measured ZERO switches on the registered thresholds, so arm E's response policy never overrode arm D's schedule. On this run E is not a fifth arm; it is arm D, and every E number is a D number E contributes no independent evidence, E-B equals D-B, and E is excluded from the design-selection candidates and from the Holm family

## The baseline is not an untouched baseline

Arm A is the installed public route: `optimization_mode='none'`, resolved by `quantbt.walkforward._select_oos_candidate_record`, whose rule is `max(records, key=record.objective)`.

LAB-04 read the engine's own walk-forward metadata and found that this mode **declares OOS-adjusted selection**: `True`. Arm A therefore carries the label **`A_legacy_selection_adjusted`** and **may not be reported as an untouched baseline** (`False`).

> every contrast in this phase is measured against A_legacy_selection_adjusted. A positive B-A is evidence about the neighbourhood selector versus THAT baseline, not versus a causal one, and guide 13.6 forbids calling it out-of-sample

The label follows the declaration rather than a behavioural probe: under expanding windows only the final test segment is out of sample for every fold, so a null probe bounds rather than refutes OOS dependence; where the declaration and the probe disagree, the declaration is the label

## L08.7 — the design decision

**Outcome: `NO_PROMISING_DESIGN`**

The rule was fixed before any arm ran: a design is frozen only if its contrast clears the minimum economic effect registered in LAB-01 AND survives Holm adjustment over the registered contrast family. Both thresholds were fixed before any arm ran

- registered endpoint: **{'statistic': 'mean daily net-return difference between arms on the same risk budget', 'aggregation': 'daily UTC paired differences on a common evaluation interval', 'guardrails': ['max_drawdown', 'expected_shortfall', 'exposure', 'turnover', 'costs', 'trade_count'], 'registered_before_results': True}**
- minimum economic effect: **6.4e-05/day**

| contrast | mean daily | clears the minimum | Holm-adjusted p |
|---|---|---|---|
| `B-A` | +0.000046 | **False** | 0.7183 |
| `C-A` | +0.000038 | **False** | 1.0000 |
| `D-B` | -0.000013 | **False** | 0.8005 |
| `D-C` | -0.000004 | **False** | 1.0000 |

**Tradeoffs**

- the dynamic arms cost more wall time for the same search budget, because a refresh at an arbitrary date cannot reuse a cached calendar fold
- arm E is an extension whose own contribution is null here: LAB-06 measured zero switches on the registered thresholds, so E deploys D's schedule
- every cell is one continuous account, so a cell's result is one path and not an average over independent folds

**Failure cases**

- A-HASH contributes no cell at all: its ladder blocker is unresolved and its five cells carry null metrics
- the guide 8.3 group ablation FAILS on all five symbols, so the states are not shown to resolve out-of-fold variance beyond price and volatility
- no data cohort beyond the server core improves anything (L08.4)
- a STATE_PLACEBO arm with matched dwell matches or beats arm D on most of the staged cells, so the dynamic arms' behaviour is attributable to the refresh cadence rather than to the regime signal

**Uncertainty**

- the sign test over cells is a direction test, not an effect-size estimate
- cells within an alpha share a selector and are not independent, so the sign test over-counts evidence; the guide's block bootstrap is LAB-09's
- three years of development on one cohort is a small sample for a daily endpoint

> guide L08 exit: profit is not required to close discovery, and a negative result is not a technical failure to be re-run until it wins

## L08.3 — the control that can sink the method, and does

STATE_PLACEBO and DELAYED_STATE are run as **arms**, not as tapes. Generating a placebo and reporting its dwell statistics controls for nothing: the alternative explanation is about what an arm would have EARNED on that tape. Each control arm mirrors arm D exactly — same selector, same refresh count, same training memory — and only the tape differs.

**RISK_ONLY is BLOCKED, not passing.** A per-state risk scale must be fitted on one window and applied on a later one. The model refits every 28 days and LAB-05 declares cross-namespace state translation diagnostic only, so only **1.64%** of scoring observations carry a state key seen during calibration (18 of 89 keys). The rest would fall back to a scale of 1.0 and the control would return the baseline path while printing a number. Blocked on **15** cells. guide 10.2 forbids removing a control. It is reported BLOCKED with the measurement, never as a scale of 1.0 that looks like a result

| cell | control | arm D | control arm | difference |
|---|---|---|---|---|
| A-HMA/BTCUSDT | `STATE_PLACEBO` | +7.70% | +6.62% | **-1.08%** |
| A-HMA/BTCUSDT | `DELAYED_STATE` | +7.70% | +7.70% | **+0.00%** |
| A-HMA/ETHUSDT | `STATE_PLACEBO` | +1.22% | +2.08% | **+0.86%** |
| A-HMA/ETHUSDT | `DELAYED_STATE` | +1.22% | +1.22% | **+0.00%** |
| A-HMA/SOLUSDT | `STATE_PLACEBO` | -3.55% | +3.02% | **+6.57%** |
| A-HMA/SOLUSDT | `DELAYED_STATE` | -3.55% | +0.27% | **+3.82%** |

**The placebo matched or beat arm D in 2 of 3 staged cells**, and a one-observation delay left arm D unchanged in 2 of 3.

> a placebo arm that matches or beats the real one says the dynamic arms were refreshing on a persistent signal at a cadence, and that ANY signal with that dwell would have done as well. The regime model supplied the cadence, not the information

guide 10.2 forbids removing a control because it beats the proposal; it is reported exactly as it came out

Staged over 3 of 15 runnable cells, the subset fixed by cell order before any result was read (guide 10.2 permits a staged design).

## L08.6 — what the phase actually cost

| | |
|---|---|
| dynamic refreshes | 90 |
| unique strategy executions in those refreshes | 9,136 |
| wall seconds, total | 10603 |
| wall seconds per cell (min / median / max) | 545 / 719 / 987 |
| resource budget exceeded | **False** |

the dynamic arms were given the calendar's refresh COUNT by construction, so neither side bought an advantage with extra searches. The wall time below is the operational cost of the same budget spent differently

### Every unit the budget registration declares

An earlier version of this table reported ONE of the registered units, for the dynamic half only, and called the result `MATCHED_TOTAL_COMPUTE`. A budget report that does not count four of its own declared units cannot say whether the arms were given the same total.

| unit | calendar arms A, B | dynamic arms C, D, E |
|---|---|---|
| cutoffs | 90 | 90 |
| unique strategy evaluations | 9,155 | 9,136 |
| fold-bar visits | 54,930 | 54,816 |
| independent local probes | 3,448 | 3,448 |
| regime model fits, multi-start included | — | 800 (200 refits × seeds) |
| response evaluations | — | 51,944 (LAB-06 ran the response layer on ONE cell (A-SC/BTCUSDT)) |

Cutoff counts equal: **True**. Search-effort ratio **0.9979** — compute-matching measured rather than asserted by construction.

Refit latency **1.463 s** measured (`measured_benchmark`), zero-latency jobs **0**. Activation delays actually paid, in bars: `[206, 36, 368, 61, 33]` (max 368). Cold/warm runtime: **NOT_SEPARATELY_MEASURED** — every cell in this phase ran cold: the process starts once, each cell is visited once, and nothing is re-run inside the same process. A cold/warm split needs a second visit to the same cell, which the design does not have

A refit costs **0.366 s/fit** measured, and the coarsest decision bar here is an hour, so the compute latency rounds to **zero bars**: `True`. a refit costs seconds and the coarsest decision bar here is an hour, so the compute latency is real and smaller than one bar. Recording zero BARS is a measurement; assuming zero SECONDS would be the free option guide L07.3 forbids

The delays the arms DO pay are measured in bars: waiting for a flat book and for the new version's own declared warmup, both measured in bars by LAB-07's continuous account.

## Guide 10.1 — arm E against B, and against the matched-bank control

E equals D on **15 of 15** cells, so it is not a fifth arm here. LAB-06 measured ZERO switches on the registered thresholds, so arm E's response policy never overrode arm D's schedule. On this run E is not a fifth arm; it is arm D, and every E number is a D number

| comparison | status | why |
|---|---|---|
| `E-B` | EQUALS_D_MINUS_B | equals `D-B`, shown because guide 10.1 asks for it, excluded from the Holm family |
| E vs `BANK_CALENDAR` | DEGENERATE_ON_BOTH_SIDES (control: DEGENERATE_HERE) | the control switches a bank on the calendar and arm E switches it on the regime. LAB-06 measured zero switches on the registered thresholds, so both deploy the same sequence and the difference is identically zero. It is reported as a degenerate comparison rather than omitted (guide 10.1, 10.2) |

What would make the second one informative: a threshold at which the policy switches at all. The best challenger ever measured was 2.58 bps against a 7 bps switch cost

## Guide 10.4 — is the five-symbol number a common-period aggregate?

Phase window **2021-01-01 → 2023-12-31**. Every symbol's usable interval covers the whole window: **True**, so the common-period aggregate and the longest-history aggregate are the same number. none: no cell begins before its symbol's usable interval

| symbol | usable interval |
|---|---|
| BNBUSDT | 2020-02-15 → 2026-09-09 |
| BTCUSDT | 2020-01-06 → 2026-09-09 |
| DOGEUSDT | 2020-07-15 → 2026-09-09 |
| ETHUSDT | 2020-01-06 → 2026-09-09 |
| SOLUSDT | 2020-09-19 → 2026-09-09 |

_macro-average over cells of a paired daily difference. Guide 11.3 forbids implying a portfolio without a capital allocation and an account simulator, and there is neither_

## L08.4 — the data-cohort ablation

Every cohort is scored on the **same rows**. Scoring each on its own longest window would credit a feature group for the period it happens to cover.

| symbol | cohort | variance resolved out of fold | gain over core | rows |
|---|---|---|---|---|
| BTCUSDT | `server_core` | -0.00586 | +0.00000 | 7296 |
| BTCUSDT | `server_derivatives` | -0.01406 | -0.00820 | 7290 |
| BTCUSDT | `server_derivatives_oi_only` | -0.01367 | -0.00781 | 7290 |
| BTCUSDT | `server_liquidity_impact` | -0.06200 | -0.05614 | 7296 |
| ETHUSDT | `server_core` | +0.07550 | +0.00000 | 4560 |
| ETHUSDT | `server_derivatives_oi_only` | -0.00588 | -0.08138 | 4554 |
| ETHUSDT | `server_liquidity_impact` | +0.01297 | -0.06253 | 4560 |
| SOLUSDT | `server_core` | -0.00727 | +0.00000 | 7187 |
| SOLUSDT | `server_liquidity_impact` | -0.01634 | -0.00907 | 7187 |
| BNBUSDT | `server_core` | -0.03204 | +0.00000 | 8488 |
| BNBUSDT | `server_liquidity_impact` | -0.08701 | -0.05497 | 8488 |
| DOGEUSDT | `server_core` | +0.04684 | +0.00000 | 7582 |
| DOGEUSDT | `server_liquidity_impact` | +0.01167 | -0.03517 | 7582 |

**Any cohort beats the core: False.**

Two cohorts are structurally unavailable and are reported as such rather than substituted:

- **`server_liquidity_book`** — the spread is the only order-book feature, and that product is a rolling 30-day window that by design cannot accumulate history (LAB-03). It has 127 usable rows on BTCUSDT and zero everywhere else.
- **`server_derivatives`** with basis is BTCUSDT-only, because basis needs a spot leg and spot was only ever collected for BTCUSDT. The open-interest half is scored separately as `server_derivatives_oi_only` so ETHUSDT's 10,399 rows are not discarded by one missing product.

## L08.5 — the complexity ladder

| rung | question | expected failure | stop condition |
|---|---|---|---|
| **M0** | does an explainable rule already separate the states a jump model finds? | M0 tracks volatility only and misses coordinated moves | if M0 resolves as much variance out of fold as M1, M1 is unjustified |
| **M1** | does persistence-penalised clustering resolve out-of-fold variance? | states are volatility buckets with extra steps | if M1 does not beat M0 out of fold, the ladder stops here |
| **M1S** | with many blocks, does sparsity find the ones that matter? | with three blocks there is nothing to select | guide 8.1 scopes M1S to 'many blocks'; with 3 it is not attempted, and guide 8.3 forbids writing a naive sparse objective without a pinned research implementation |
| **M2** | is the structure specific to a jump model or to the features? | a different family finds the same partition | guide 8.1 declines to make M2 mandatory and warns against sweeping model families; not attempted |

Implemented: `['M0', 'M1']`. Declared deliberately unbuilt: `['M1S', 'M2']`. development only; K, lambda, training memory and cadence are never tuned against the outer window.

## Audit and acceptance coverage

- **74/74** checklist clauses DONE, driven by `configs/lab08_checklist.json` written BEFORE any factorial code (`checklist_written_before_code: True`)
- clauses with no evidence pointer: **none**
- acceptance tests: **30 passed in 2.72s**

Guide §14 coverage as of LAB-09: **63 COVERED, 0 PARTIAL, 1 NOT_YET_IMPLEMENTED** of 64.

## Corrections made during LAB-08

The pilot exists to be thrown away, and it earned its keep: **two defects, both of which would have produced a timing result that was really a coverage artefact.**

1. **The state tape covered a sixth of the window.** LAB-05 persisted 1,099 emissions from one namespace while summarising 6,571 across forty. Reading whichever per-namespace file was last on disk gave the dynamic arms states for 2023-07 onward only, so **every** refresh landed in the last six months while the calendar arms refreshed across three years. The fitter now writes the full tape, the fallback is gone, and a cell whose tape does not span its window has no dynamic arm.
2. **The dynamic training windows were a fifth of the calendar's** — 868 bars against 4,320. The selector's frame started where the account started, but the calendar arm's first fold trains from 180 days *before* that. A selector with a fifth of the history is not the same selector, so the comparison was not measuring timing. The selector now gets a frame reaching one training memory back, and every dynamic cutoff trains on 4,320 bars exactly as the calendar does.

3. **A cell where the selector never selected crashed the run.** Arm B's quality gate rejected every candidate at all six cutoffs on A-SC/BNBUSDT — `ALL_FAIL_ECONOMIC_QUALITY` six times — and the schedule builder raised rather than deploying the retained incumbent. That took nine completed cells down with it, about two hours. A selector that declines is a **result**: the arm now holds the incumbent seed and carries `selector_never_selected: true`. The run also checkpoints each cell, so a crash costs one cell instead of everything before it.

Two more were found while building, before any result existed:

4. **The trigger rule concentrated every refresh at the front.** Taking the first six transitions with a 30-day gap put all of them in the opening months — the mirror image of defect 1. Triggers are now taken one per period, so the cadence matches the calendar and only the timing within each period is the model's choice. A period with no transition refuses rather than padding: a refresh the states did not ask for is just the calendar wearing a different label.
5. **The liquidity cohort scored an impact proxy and called it the order book.** `g4_log_amihud_30` comes from the perpetual bars and exists for every symbol; `g4_spread_bps` is the only order-book feature and has 127 rows on BTCUSDT and zero elsewhere. Matching on the `g4` prefix merged them, so the cohort the guide asks about was never actually tested. They are now separate cohorts.

