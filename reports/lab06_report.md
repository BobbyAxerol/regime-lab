# LAB-06 — Conditional parameter response và bốn clocks

Generated from committed artifacts by `scripts/write_lab06_report.py`. Nothing is re-estimated here.

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **episode** | one (decision at T, candidate, outcome over the following horizon) row. It is the unit the response estimator learns from | LAB-06 — 7-day non-overlapping windows, the registered pilot horizon |
| **outcome_available_at** | when an episode's outcome could actually be KNOWN: outcome end plus publication and processing delay. An outcome is unusable before it | LAB-06 — an unfinished horizon is no outcome at all, not a small one (T45) |
| **candidate bank** | the set of parameter versions a switch may choose between, assembled only from discoveries made before the cutoff | LAB-06 — 3-8 entries proposed by guide 7.4; a later discovery is rejected with a reason |
| **paired delta** | U_e(candidate) - U_e(incumbent) on the SAME episode, so the horizon, the initial state and the economics cancel instead of having to be matched | LAB-06 — the quantity the estimator averages (T47) |
| **similarity weight** | how much a past episode counts now: a kernel on context distance, times a recency decay, times an eligibility flag that is 0 or 1 and never a reward for a good outcome | LAB-06 — guide 9.2 |
| **N_eff** | weight concentration, (sum w)^2 / sum w^2. It says how many episodes the weights spread over. It is NOT a count of independent observations | LAB-06 — reported next to the contiguous-block count for exactly that reason |
| **contiguous block** | a run of episodes adjacent in time. Twelve consecutive weeks inside one market stretch are ONE piece of evidence wearing twelve hats | LAB-06 — at least two blocks are required before a recommendation is made |
| **shrinkage** | pulling a local estimate toward a pooled one by a_t = N_eff/(N_eff+kappa), so thin evidence moves the answer less | LAB-06 — a declared heuristic, not a calibrated posterior |
| **transition cost** | the projected cost of moving from one parameter version to another: turnover x (fees + slippage) plus residual handling, in the SAME units as the utility | LAB-06 — it DECIDES; the engine charges. Subtracting it from realised PnL too would bill the same cost twice |
| **inaction region** | the band between 'clearly worse' and 'clearly better after costs', where the answer is keep the incumbent | LAB-06 — without it a policy churns on noise and pays the churn in real fees |
| **campaign** | one entry and everything that follows it until flat or terminal, carrying an IMMUTABLE entry_parameter_digest | LAB-06 — an open trade stays protected by the parameters it entered with (T50) |
| **four clocks** | inference (state update), switch (choose among existing candidates), bank refresh (find new ones), model retrain (refit the state model) — four separate schedules and counters | LAB-06 — merging any two is what produces a recursive trigger storm (T52) |
| **coalesce / supersede** | two refit triggers close together become ONE job; a later trigger supersedes an earlier one, and the superseded job's result is discarded even if it finishes | LAB-06 — deterministic, so a slow job can never activate stale work (T49) |
| **effective_at >= ready_at** | a refit takes effect no earlier than the moment it was ready. There is no backdating | LAB-06 — backdating would let a decision claim knowledge it did not have (T49) |
| **indicator warmup** | an indicator must have seen enough past-only bars before its signals are acted on; it is never reset at a switch and never carried across parameter sets without a contract | LAB-06 — resetting fabricates fresh signals from a cold start (T51) |
| **counterfactual limit** | a difference between the training experiment and the live deployment that no error bar can represent — for example that episodes start flat and a live switch does not | LAB-06 — four are recorded by name (L06.6) |
| **conclusion level** | a label from a vocabulary registered BEFORE any result, so a finding cannot be described with a word invented to fit it | LAB-04 — INCONCLUSIVE_SAMPLE / DESCRIPTIVE_VALUE / NET_PARAMETER_SELECTION_EDGE / FAILED_VALIDITY and three others |
| **read-lock** | re-hashing the source files a snapshot was copied from, to detect that upstream changed under a run | LAB-03 onward — the snapshot manifest IS the lock; every phase re-verifies it before it runs |
| **open trailing partition** | the current period's file, which the collector is still appending to; it is expected to change and is excluded from a primary read | LAB-03 onward — 9 of 627 files; a primary run reads closed partitions only |
| **ingest re-stamp** | an upstream file rewritten with a new `ingested_at` on every row while every MEASURED column stays identical — the digest moves, the numbers do not | LAB-04/05/06 read-lock — 23 closed `binance_futures_metrics_5m` partitions on 2026-09-10, read and proven unchanged, so no cohort is invalidated |
| **content revision** | an upstream change that a read cannot prove benign — a changed value, row count or schema, or a file that will not open. It still invalidates every cohort reading that product | LAB-04/05/06 read-lock — 0 measured; the benign verdict carries the burden of proof, never the invalidating one |
| **primary core** | the products and features a primary run actually consumes — the perpetual 1m bars and the 8 features covering all five symbols (G1×3, G2×2, G5×3) | guide 6.2 / LAB-03 — drift in a product outside it can invalidate a cohort but never the primary run |
| **data role** | the declared purpose of a date window: `development` permits fitting and design choices, `outer_evaluation` permits only a frozen-protocol run | development 2020-01-01→2023-12-31; LAB-04/05/06 stay inside it |

## What this phase claims and does not claim

This layer joins the LAB-05 state to the LAB-04 candidate utilities and turns the join into a keep/switch decision. The exit gate is that **every keep or switch carries evidence, data cutoffs and consistent units** — not that switches happen. Guide L06 is explicit: **zero switches because no challenger cleared the bar is a valid result**, and a policy that switched in order to look busy would be the failure, not the pass.

**Scope: 1 of the 20 primary cells.** The mechanism is built and measured on **A-SC / BTCUSDT** only — the first cell of the guide's pilot order (§10.4 A-SC → A-HMA → A-VWAP → A-HASH). Guide L06 asks for the response estimator, the bank, the decision machine and the four clocks; the 4 alpha × 5 symbol matrix is the LAB-08/09 comparison surface, not this phase's. Every number below therefore describes one cell and must not be read as an aggregate over the matrix.

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
- regime context comes from the LAB-05 jump model, which fits the **8 primary-core features (G1×3, G2×2, G5×3)**. Those derive from the perpetual 1m bars alone: the G3 metrics product and the G4 order-book product are cohort extensions this phase does not read, so drift in either cannot reach these results.
- episodes: **1,530** rows in `evidence/crypto_regime_timeedge_v2/response_panel.parquet`, a **7-day** non-overlapping grid
- decisions assessed every **4h** regime observation, **6,566** in total

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

## L06.1 — the episode table

- registered horizon **7 days**; measured mean holding **3.92 days** → the horizon covers the holding period: **True**
- the horizon is registered before any response is estimated. The holding diagnostic is reported next to it, not used to retune it after the fact
- **1530** episode rows written to `evidence/crypto_regime_timeedge_v2/response_panel.parquet`

## L06.2 — the candidate bank and its lineage

| cutoff | admissible | within 3–8 | rejected | trial rows kept |
|---|---|---|---|---|
| 2021-01-01 | 8 | True | 574 | 587 |
| 2021-06-30 | 8 | True | 567 | 587 |
| 2021-12-27 | 8 | True | 560 | 587 |
| 2022-06-25 | 8 | True | 554 | 587 |
| 2022-12-22 | 8 | True | 551 | 587 |
| 2023-06-20 | 8 | True | 538 | 587 |

- every candidate carries the time it was DISCOVERED, and the bank at a cutoff admits only what was discovered before it. Duplicates are merged for coverage but their trial rows are never deleted (T46)
- a candidate whose pooled mean is below the global best may still belong in the bank if it has conditional evidence with enough support. It is dropped for lack of support or for failing cost/risk constraints, never for a low pooled mean alone (guide 7.4)

## L06.3 — the conditional response estimator

- kernel bandwidth **1.0**, recency τ **180.0 days**, shrinkage κ **8.0**
- support gates: N_eff ≥ **4.0** over ≥ **2** contiguous blocks; one episode above **50%** of the weight is flagged
- inner development only, registered before any recommendation (guide 9.2)
- outcome information used in the weights: **False**

- **51944** estimates produced

| status | count |
|---|---|
| `INSUFFICIENT_SUPPORT` | 41240 |
| `SUPPORTED` | 10704 |

- supporting episode ids and weights attached to every estimate: **True**

## L06.4 — the decision ledger

| decision | count |
|---|---|
| `FALLBACK_NOVEL_STATE` | 101 |
| `KEEP_INCUMBENT` | 1322 |
| `NO_SUPPORTED_CANDIDATE` | 5143 |

- decisions: **6566**, switches: **0**

### Which gate actually bound (guide 13.4)

Every decision now records what the economics **proposed before any gate ran** and what the guards did with it — including a no-switch. Without the pair, *no challenger was better* and *a challenger WAS better and a gate refused it* are the same row, and that difference is the entire content of an inaction region.

| binding gate | decisions |
|---|---|
| `SUPPORT` | 5,143 |
| `ECONOMICS` | 1,322 |
| `NOVEL_STATE` | 101 |

The economics ran on **1,322** of 6,566 decisions. A challenger cleared transition cost plus margin on **0** of them, and a later gate refused a clearing challenger on **0**. So the inaction region bound at the **economics**, every time the economics ran: no capacity, warmth, spacing or campaign gate ever had to refuse anything.

Each verdict carries its own denominator. `all(...)` over an empty population is True and reads exactly like a verified claim — *every switch carries its supporting episodes* was reported True across a run with **zero switches**, and quoted here as evidence that it carried them.

| verdict | holds | checked over | reading |
|---|---|---|---|
| `every_decision_has_a_reason` | True | 6566 | verified over 6566 decisions |
| `every_switch_has_supporting_episodes` | **VACUOUS** | 0 | no switches occurred, so this verifies nothing |
| `every_decision_records_its_cutoffs` | True | 6566 | verified over 6566 decisions |

> **every_switch_has_supporting_episodes** verifies nothing on this run. It is kept, and labelled, rather than counted as evidence.

> **Zero switches.** Guide L06's exit gate says this is a valid technical result: the machinery is judged on whether every decision is evidenced and causally clean, not on whether it decided to trade. The decision counts above say WHICH constraint bound, which is the part a reader can act on.

## L06.5 — four clocks

| clock | cadence |
|---|---|
| inference | 0 days 04:00:00 |
| model_retrain | 28 days 00:00:00 |
| bank_refresh | 180 days 00:00:00 (frozen baseline calendar) |
| switch | every eligible inference boundary, when needed |

- counters — inference **6566**, switch assessments **6566**, switches executed **0**, bank refreshes **6**, model retrains **0**
- model retraining, bank refresh and switch frequency are three separate counters. A high switch count says nothing about how often the model was refitted, and vice versa (guide 8.6)
- a state change never triggers a retrain and a retrain never triggers a parameter search. Merging any two of these clocks is what produces a recursive trigger storm (guide 9.4, T52)
- a triggered-refresh variant is separate: **True**

### Switch rule

`delta_shrunk - z_alpha*SE > C_transition + delta` with z_alpha **1.0** and margin **0.0002**, minimum spacing **7 days 00:00:00**

- check order: data quality → novel/stale state → bank adequacy → support → economics vs transition cost → indicator warmth → switch spacing → campaign boundary
- z_alpha is a conservative decision heuristic. It is NOT a confidence guarantee: with a handful of episodes and a model whose assumptions may be wrong, an arbitrary Gaussian 95% label would be false precision (guide 9.3)
- C_transition decides; the engine charges. The estimate is never subtracted from realised PnL as well (guide 9.3)

### Campaigns

- open **0**, transition-blocked **0**, forced unwind used: **False**
- a long-open campaign is reported TRANSITION_BLOCKED and left alone. Forcing it flat to let a switch through would manufacture the time edge the study is measuring; a forced unwind is a separate ablation with its own costs (guide 9.5)
- a candidate that is not deployed keeps shadow INDICATOR state only. It never keeps a shadow financial account, because a second account would let a hypothetical equity curve leak into a deployment claim (guide 9.5)

## L06.6 — what this layer cannot measure

| id | limit | consequence |
|---|---|---|
| CF-1 | training utilities start flat; a live switch does not | the estimate answers 'what would this candidate have done from flat', which is a different question from 'what happens if I switch to it right now, holding what I hold' |
| CF-2 | the transition cost is a PROJECTION | realised cost depends on the book at the moment of the switch. The projection uses declared fee and slippage rates and cannot know the spread it will actually cross |
| CF-3 | activation delay is state-dependent | a switch waits for a campaign boundary, and how long that takes depends on the very market state that motivated the switch. The delay is therefore correlated with the signal, and a symmetric error bar cannot represent that |
| CF-4 | execution risk is conditional on state | slippage, partial fills and gap risk are worse in exactly the regimes where a switch is most tempting. The response estimate is built from realised episode outcomes and carries no separate term for this |

- response uncertainty measures how much the CONDITIONAL ESTIMATE would move if the episodes were different. It does not measure the four limits above, which are differences between the experiment and the deployment. Widening the error bar would not represent them; it would only make the same estimate less decisive
- the deployed account is a single continuous simulation that pays real fills. A hypothetical curve in which the account resets to flat at every switch -- an 'expert' curve -- is NOT used as deploy equity, because it silently removes CF-1, CF-3 and CF-4 at once (guide L06.6)
- reset-flat expert curve used as deploy equity: **False**

## Audit and acceptance coverage

- clause audit: **79/79** DONE, driven by a checklist written BEFORE the code (`configs/lab06_checklist.json`)
- clauses with no evidence pointer: **none**
- acceptance tests: `56 passed in 0.58s` (passed = True)
- guide §14 coverage as of LAB-09: `{"COVERED": 62, "PARTIAL": 1, "NOT_YET_IMPLEMENTED": 1}` of 64

## Corrections made during LAB-06

- **A leaked loop variable corrupted the bank's lineage.** `build_bank` computed `discovered_at` in the filtering pass and then read that same variable in the building pass, so every entry received the timestamp of whichever discovery happened to be last. The filter itself was correct — the bank held the right candidates — but the recorded discovery time was wrong on all of them, which is exactly the field T46 exists to protect. It surfaced only because `admissible()` re-checks the entry's own timestamp instead of trusting the build, and the measured symptom was banks of size **[0, 0, 0, 0, 0, 8]** where every one should have held 8.
- **The contiguous-block check was structurally dead.** Blocks were counted over every episode with a weight above 1e-9, and a Gaussian kernel never reaches zero, so every set of episodes looked like one unbroken run. Combined with an `order` built from the filtered list index rather than the position in time, the check reported **1 block for all 400 sampled estimates** and every recommendation was refused for the wrong reason. Blocks are now counted over the SUPPORT SET — the smallest group of episodes carrying 90% of the weight — and the order is the episode's index in the global window grid.

