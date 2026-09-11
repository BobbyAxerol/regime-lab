# LAB-05 — Persistent regime model và causal emissions

Generated from committed artifacts by `scripts/write_lab05_report.py`. Nothing is refitted here.

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **jump model (JM)** | a clustering of standardized features into K states, plus a penalty for every switch, so the fitted state path is persistent instead of flickering bar to bar | LAB-05 — the primary state model M1 (guide 8.2) |
| **lambda_J / jump penalty** | what one state switch costs the FIT, in standardized-loss units at the sampling frequency. It is not the policy's real switching cost and cannot be carried to another frequency | LAB-05 — 1.0 at a 4h observation interval |
| **Q_t(k)** | the cost of the best history that ENDS in state k at time t. It is a per-endpoint minimum, not a running total of the labels already emitted | LAB-05 — the forward recurrence of guide 8.4 |
| **forward filter / causal emission** | emit argmin_k Q_t(k) at time t using observations up to t only, and never revise it | LAB-05 — the only labels a decision may use |
| **offline best path (Viterbi)** | walking back from the terminal argmin, which REWRITES earlier labels using data that did not exist when they were emitted | LAB-05 — computed as a diagnostic and carries decision_eligible=false (guide 8.4) |
| **state namespace** | a label space belonging to ONE fit. State 2 of one fit and state 2 of the next are unrelated integers until a mapping says otherwise | LAB-05 — one namespace per 28-day refit |
| **namespace mapping** | matching a new fit's states onto the previous fit's, using TRAINING centroids only. A state that cannot be matched is UNMAPPED_REFIT_STATE — a model event, not a market event | LAB-05 — guide 8.4; it never triggers a parameter search |
| **membership score** | softmax(-cost) over the state costs. It sums to one, which is exactly why it must not be called a probability: nothing here calibrates it against outcomes | LAB-05 — carries membership_is_calibrated=false (guide 8.5, T42) |
| **second-best gap** | how far the emitted state is from the runner-up. A small gap means the emission was nearly a coin flip | LAB-05 — the ambiguity measure, reported instead of a fake confidence |
| **novelty / out-of-support** | the observation sits further from every centroid than the training residuals ever did. The inputs are PRESENT — that is what separates it from missing data | LAB-05 — UNKNOWN_STATE at the 0.99 training-residual quantile (T44) |
| **degeneracy** | the model cannot discriminate: weights collapsed to zero, centroids coincide, or a state has no members. The response is UNKNOWN_STATE, never state 0 with a 1/K score | LAB-05 — guide 8.3/8.5, T40 |
| **no-regime world** | a synthetic negative control drawn from ONE distribution throughout. Any persistent state structure reported on it was manufactured by the model | LAB-05 — L05.7; the count of emitted switches on it is the false-structure rate |
| **detection delay** | observations between a true latent switch and the first emitted state change after it, reported as a distribution because a mean hides an occasional very late detection | LAB-05 — measured on the recurring-state and structural-break worlds |
| **conclusion level** | a label from a vocabulary registered BEFORE any result, so a finding cannot be described with a word invented to fit it | LAB-04 — INCONCLUSIVE_SAMPLE / DESCRIPTIVE_VALUE / NET_PARAMETER_SELECTION_EDGE / FAILED_VALIDITY and three others |
| **NOT_READY** | an alpha that cannot be certified keeps all its cells with NULL metrics; booking it as PnL = 0 would bias every aggregate | LAB-02/04 — A-HASH, 5 cells |
| **read-lock** | re-hashing the source files a snapshot was copied from, to detect that upstream changed under a run | LAB-03 onward — the snapshot manifest IS the lock; every phase re-verifies it before it runs |
| **open trailing partition** | the current period's file, which the collector is still appending to; it is expected to change and is excluded from a primary read | LAB-03 onward — 9 of 627 files; a primary run reads closed partitions only |
| **ingest re-stamp** | an upstream file rewritten with a new `ingested_at` on every row while every MEASURED column stays identical — the digest moves, the numbers do not | LAB-04/05/06 read-lock — 23 closed `binance_futures_metrics_5m` partitions on 2026-09-10, read and proven unchanged, so no cohort is invalidated |
| **content revision** | an upstream change that a read cannot prove benign — a changed value, row count or schema, or a file that will not open. It still invalidates every cohort reading that product | LAB-04/05/06 read-lock — 0 measured; the benign verdict carries the burden of proof, never the invalidating one |
| **primary core** | the products and features a primary run actually consumes — the perpetual 1m bars and the 8 features covering all five symbols (G1×3, G2×2, G5×3) | guide 6.2 / LAB-03 — drift in a product outside it can invalidate a cohort but never the primary run |
| **data role** | the declared purpose of a date window: `development` permits fitting and design choices, `outer_evaluation` permits only a frozen-protocol run | development 2020-01-01→2023-12-31; LAB-04/05/06 stay inside it |

## What this phase does and does not claim

The exit gate is a **technical pass**: a causal provider with a reproducible state vocabulary. Guide L05 forbids inferring predictive or financial value from fit loss, from agreement with a simulator, or from labels that look clean on a chart. Nothing below is offered as evidence that these states make money — that question belongs to LAB-06 onward and is not answered here.

**Scope: 1 symbol.** The model is fitted and audited on **BTCUSDT** only. The state vocabulary, the cadence and the diagnostics are the deliverable; a per-symbol model for the other four is not built here and no claim below generalises to them.

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

- symbols: **BTCUSDT**
- products: `crypto_binance_futures_1m`
- data role **development**, window **2020-01-01 → 2023-12-31**
- the jump model fits the **8 primary-core features (G1×3, G2×2, G5×3)** — the only features covering all five symbols. They derive from the perpetual 1m bars alone, so the G3 metrics product and the G4 order-book product are NOT read here and drift in either cannot reach these fits.
- observation interval **4h**, rolling training memory **365 days**
- **40** fits, `jm_k3_2020-12-31` → `jm_k3_2023-12-28`
- outer_evaluation holdout touched: **False**

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

## L05.2 / L05.6 — acceptance checks T37–T44

| id | question | measured |
|---|---|---|
| T37 | does the forward DP equal exhaustive enumeration? | endpoint costs **True**, online states **True**, best path **True** over 8 random toy sequences |
| T38 | batch vs streaming emissions | states **True**, costs **True**, every prefix vintage stable **True** |
| T39 | can the fit see past its cutoff? | clean fit `CAUSAL`, deliberately leaky fit `LEAK_DETECTED`, detector meaningful **True** |
| T40 | degenerate model | blocked **True**, healthy usable **True**, no fake confidence **True** |
| T41 | refit permutes state ids | permutation recovered **True**, declared a market transition **False**, a genuinely moved state left unmapped **True** |
| T42 | membership score vs probability | sums to one **True**, named a probability **False**, calibrated **False** |
| T43 | does inference trigger a retrain? | the inference modules cannot reach a fit at all: **True** |
| T44 | novelty vs missing data | four statuses distinct **True**, missing input wins over an identical residual **True** |

Two of these deserve their measurement spelled out, because a check that cannot fail proves nothing:

- **T37** found the causal emission and the offline best path DISAGREEING in **7** of 8 sequences. where they disagree, the offline path rewrote a label using data that did not exist when the decision was taken. That is why the offline path carries decision_eligible=false (guide 8.4)
- **T39** ran the same detector over a knowingly leaky fit and it returned `LEAK_DETECTED`. a detector that always returns CAUSAL would pass the clean fit too. The known-leaky fit is the only thing that shows the check can fail.

### L05.2 — greedy online and endpoint DP are two model versions

| λ_J | endpoint-DP switches | greedy switches | label agreement | identical |
|---|---|---|---|---|
| 0.5 | 37 | 160 | 0.677 | False |
| 2.0 | 14 | 102 | 0.807 | False |
| 6.0 | 21 | 204 | 0.333 | False |

the jump penalty is exactly what separates them: at lambda_J = 0 the DP reduces to greedy, and as lambda_J grows the DP holds states the greedy labeller abandons. Reporting one and calling it the other would misstate how often the provider changed its mind

> these are two models, not two settings of one. A study declares which it uses and the emitted tape carries that version; blending them, or falling back from one to the other, would make 'the model said X' meaningless (guide L05.2)

### L05.2 — the M0 rule baseline, run as a comparator

| model | switches | best-permutation agreement |
|---|---|---|
| M0 (frozen volatility quantiles) | 504 | 0.547 |
| M1 (discrete jump model) | 22 | 0.983 |

- thresholds fitted on the first 60% of the world only, then frozen
- M0 is a control, not a fallback: **True**
- M0 reads one feature through frozen quantile cuts. Where M1 does better, the gain is attributable to using the whole feature vector with persistence; where it does not, the extra machinery bought nothing on this fixture

## L05.7 — synthetic worlds and the negative control

| world | true switches | emitted switches | agreement | median detection delay |
|---|---|---|---|---|
| no_regime | 0 | 18 | 0.007 | null |
| recurring_state | 14 | 24 | 0.983 | 1.0 |
| structural_break | 1 | 14 | 0.990 | 0.0 |

> **NEGATIVE CONTROL.** a K=3 jump model fitted on structureless noise still emitted 18 state changes where the truth has 0. Persistent-looking states are NOT evidence of regimes, and no chart of these labels should be read as one

- the latent label is generated by the simulator. It scores detection quality and never enters a feature, a model fit, or a policy input (guide L05.7)

| noise σ | agreement | emitted switches | true switches |
|---|---|---|---|
| 0.5 | 0.994 | 14 | 14 |
| 1.0 | 0.984 | 23 | 14 |
| 2.0 | 0.776 | 266 | 14 |
| 4.0 | 0.419 | 526 | 14 |

separation is held fixed while noise rises, so this traces where the model stops resolving states that really are there

## L05.1 / L05.3 / L05.5 — fits on the development role

- symbol **BTCUSDT**, observation interval **4h**, training memory **365 days**, λ_J **1.0**, K **3**
- data role **development**, outer evaluation touched: **False**
- 40 refits every 28 days (2020-12-31 .. 2023-12-28)
- a fit does NOT refresh the bank (False) and does NOT start a parameter search (False). model retraining, bank refresh and switch frequency are three separate counters. A state change does not trigger a fit and a fit does not trigger a parameter search (guide 8.6, L05.5)

- **40 fits**, of which **0** were degenerate
- **39 namespace mappings** between consecutive fits; **10** contained a state that could not be matched
- none of them declared a market transition: **True**

A refit is free to hand back the same three states under permuted integers. The state counts below show that happening in practice — the largest state moves between index positions from one fit to the next — which is exactly why each fit gets its own namespace.

| cutoff | selected seed | state counts | centroid digest | degenerate |
|---|---|---|---|---|
| 2020-12-31 | 51 | [1422, 261, 477] | `6bed8123fe166b76` | False |
| 2021-01-28 | 11 | [362, 1511, 317] | `0feae67ff706bfd3` | False |
| 2021-02-25 | 23 | [319, 1480, 391] | `7cfd0ba2c3b24d04` | False |
| 2021-03-25 | 11 | [1551, 279, 360] | `1e7f02950814198e` | False |
| 2021-04-22 | 51 | [796, 248, 1146] | `3e2e52bf215b2a0f` | False |
| 2021-05-20 | 23 | [674, 484, 1032] | `407c14a82a869620` | False |
| 2021-06-17 | 51 | [525, 1357, 308] | `87f75df7282065a2` | False |
| 2021-07-15 | 23 | [259, 509, 1422] | `44293b987c0b37b9` | False |
| … 32 more fits | | | | |

### L05.4 — choosing K

- registered starting K: **3**, used: **3**
- inner criterion picked **2** (agrees with the registered choice: **False**)
- holdout inspected: **False**

| K | mean per-observation objective | worst inner fold |
|---|---|---|
| 2 | 0.61564 | 0.76379 |
| 3 | 0.62741 | 0.78393 |

> **The registered K and the registered selection method DISAGREE.** The inner criterion preferred K=2 by 1.9%. the usual worry is that a larger K fits better almost by construction. Here the SMALLER K scored better, which is the opposite direction and is why the standard warning does not settle this case.

- the registered starting K=3 is used and the disagreement is reported rather than acted on. This is a JUDGEMENT CALL and the guide can be read both ways: 8.1 calls K=3 the 'primary starting' K with K=2 a registered 'parsimonious alternative', while 8.3 says K is chosen in nested development -- which is exactly the criterion that preferred K=2 here. The lab keeps the registered starting point because switching after seeing a score, even a nested-development score, is still choosing the model on a result; but the margin is small and the decision belongs to the user, so it is recorded in reports/improvement_opinions.md rather than settled silently.
- a lower objective at higher K is close to automatic, so this comparison never by itself justifies opening K=4. That needs a recorded discovery decision naming the decision value the extra state buys (guide 8.1)

### Guide 8.3 — group ablation

| feature blocks | features | inner objective | variance resolved out of fold | Δ | improved |
|---|---|---|---|---|---|
| G1 | 3 | 0.39758 | +0.33467 | — | None |
| G1 + G2 | 5 | 0.51441 | +0.09465 | -0.24003 | False |
| G1 + G2 + G5 | 8 | 0.62741 | -0.03556 | -0.13021 | False |

- decided on **variance_resolved_out_of_fold**, not on the objective. a different feature set is a DIFFERENT objective function, so its value is not comparable across rows -- a higher number can mean worse states or simply noisier features. variance_resolved is within-state over total weighted variance subtracted from one, which means the same thing at 3 features and at 8. The objective column is kept for reference and is not what the verdict rests on
- blocks contributing beyond price/volatility: **NONE**

> guide 8.3 asks the ablation to DEMONSTRATE that the flow and market-coordination blocks contribute beyond price/volatility. On this symbol and window it does not: out of fold, both the fit objective and the scale-free variance-resolved measure get worse as blocks are added, and at the full 8-feature core the state assignment resolves essentially no variance on held-out blocks. The registered core is NOT changed in response -- selecting a feature set on this result would be choosing the model on an outcome. It is recorded as a finding.

### Guide 8.1 — position on the model ladder

| rung | model | built | why not / role |
|---|---|---|---|
| M0 | rule-based volatility/path-direction/activity | True | explainable control, thresholds train-only |
| M1 | regularized discrete statistical jump model | True | primary state model |
| M1S | sparse JM or group-regularized features | False | the primary core is 8 features in 3 blocks (G1 3, G2 2, G5 3). Guide 8.1 scopes M1S to 'khi nhiều blocks', and 3 is not that. Guide 8.3 also forbids writing a naive sparse objective and requires a pinned research implementation or a verified constrained one; none is pinned in this environment, so writing one would be exactly the move 8.3 warns against. |
| M2 | small HMM or GMM | False | LAB-05's task list (L05.2) asks for M0 and M1 references. M2 is a comparator the guide explicitly declines to make mandatory, and adding it would widen the model family sweep 8.1 warns against. |
| M3 | online novelty/change detector | False | guide 8.1 marks it 'chưa ghép default'. The novelty AXIS it would feed is already measured -- fit residual against the training-residual quantile in quality.assess -- without introducing a second detector whose disagreements with M1 would then need their own policy. |

- LAB-05 L05.2 asks for M0 and M1 references. The other rungs are declared unbuilt with a reason and a condition that would reopen them, so an omission cannot be mistaken for an oversight (guide 8.1)

## L05.2 — the emission tape

- **6571** emissions across **40** namespaces, produced by OnlineStateFilter, one observation at a time
- switches counted WITHIN namespaces: **220**
- switches are counted WITHIN a namespace. A model change starts a new namespace and a fresh filter, so a state id in one namespace is not comparable to the same integer in another (guide 8.4)

| quality status | count |
|---|---|
| `OK` | 6470 |
| `UNKNOWN_STATE` | 101 |

- model transitions emitted: **39**, none of which is a market event

- **stress overlay** measured on 6571 observations (mean -26.361, p95 -25.715). It is a regime state: **[False]**; joint labels created: **0**. stress is reported on its own axis from the liquidity/impact features. It is never a bear state and it never multiplies the state vocabulary into K x stress joint labels (guide 8.5)
- **cross-namespace view**: 6403 emissions translated into the previous fit's ids, 283 left as -1. decision_eligible = **False**. translating one fit's states into the previous fit's ids produces a readable series across a refit boundary. It is a DIAGNOSTIC: the emitted tapes stay as they were emitted, an unmapped state becomes -1 rather than being folded into its nearest neighbour, and no decision reads this view (guide 8.4)

### L05.3.5 — source transition

- declared source columns: `{"g3_source": {"distinct_sources": ["binance_futures_metrics_5m"], "runs": 1}, "g4_source": {"distinct_sources": ["crypto_binance_orderbook_snapshot_1h"], "runs": 1}, "g3_basis_source": {"distinct_sources": ["crypto_binance_spot_1m"], "runs": 1}}`
- real boundaries found: **0**. every declared source column holds a single value across the development role for this symbol, so there is no real transition to detect here. That is a finding about the data, not a passing check
- **positive control**: a 4-IQR level shift was injected into `['g1_rv_6', 'g1_direction_6']` and the detector flagged `['g1_rv_6', 'g1_direction_6']` → can fire: **True**. a detector that never fires would look identical to a clean dataset. The control injects a 4-IQR level shift into two named features and requires both to be flagged

## Audit and acceptance coverage

- clause audit: **53/53** DONE
- acceptance tests: `79 passed in 5.55s` (passed = True)
- guide §14 coverage as of LAB-06: `{"COVERED": 53, "PARTIAL": 3, "NOT_YET_IMPLEMENTED": 8}` of 64

## Corrections made during LAB-05

- **The first fit schedule did not match the registered cadence.** Guide 8.6 registers a 28-day model fit; the first implementation used four cutoffs six months apart. The measured consequence was that **762 of 1099 emissions came back `STALE_MODEL`**, because the model in force was older than the 56-day staleness bound for most of the run. The schedule now refits every 28 days and each observation is labelled by the model that was current at that time.

