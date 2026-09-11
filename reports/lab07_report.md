# LAB-07 — Continuous regime-aware WFO integration

Generated from committed artifacts by `scripts/write_lab07_report.py`. Nothing is re-estimated here.

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **availability event bus** | one ordered stream carrying bar completions, regime observations, refit request/start/ready, activations and fills, each with observed_at, available_at and a sequence number | LAB-07 L07.2 — ordering is (available_at, causal rank, arrival); millisecond equality is never an ordering |
| **activation delay** | the gap between when a switch was REQUESTED and when it actually took effect, caused by an open campaign or by indicators that are not yet warm | LAB-07 L07.4 — measured on the real account: 64 to 368 bars across the five switches |
| **operational segment** | the stretch during which one parameter version was effective. Its end is written only when the NEXT activation exists, so a running segment has no length | LAB-07 L07.5 — 6 segments, the last one open with a null end |
| **no-change trigger** | a refresh that fired and changed nothing. It is recorded, because dropping it would make the refresh cadence look like the switch rate | LAB-07 L07.5 — 6,566 of them against 5 activations |
| **disabled versus inert hooks** | DISABLED means the experimental layer is not consulted; INERT means it is consulted and declines. Both must give the baseline path, or merely asking has a side effect | LAB-07 L07.1 — three runs compared, not two |
| **continuous account** | ONE chronological account whose parameter version changes at activation boundaries: one engine pass, one equity curve, no reset and no splice at a boundary | LAB-07 T56 / guide 10.3 — 105,120 bars, 0 resets |
| **training account contract** | the reset/flat account a candidate is EVALUATED under, deliberately different from the deployment account it would be deployed into | LAB-07 L07.3 / guide 10.3 — the refit runner cannot reach the deployment account at all |
| **refit latency** | how long a refit takes before its result may be activated, taken from a measured benchmark rather than assumed | LAB-07 L07.3 — 0.387s per fit measured; a latency of zero is refused because it would be a free option on the bars in between |
| **conclusion level** | a label from a vocabulary registered BEFORE any result, so a finding cannot be described with a word invented to fit it | LAB-04 — INCONCLUSIVE_SAMPLE / DESCRIPTIVE_VALUE / NET_PARAMETER_SELECTION_EDGE / FAILED_VALIDITY and three others |
| **read-lock** | re-hashing the source files a snapshot was copied from, to detect that upstream changed under a run | LAB-03 onward — the snapshot manifest IS the lock; every phase re-verifies it before it runs |
| **open trailing partition** | the current period's file, which the collector is still appending to; it is expected to change and is excluded from a primary read | LAB-03 onward — 9 of 627 files; a primary run reads closed partitions only |
| **ingest re-stamp** | an upstream file rewritten with a new `ingested_at` on every row while every MEASURED column stays identical — the digest moves, the numbers do not | LAB-04/05/06 read-lock — 23 closed `binance_futures_metrics_5m` partitions on 2026-09-10, read and proven unchanged, so no cohort is invalidated |
| **content revision** | an upstream change that a read cannot prove benign — a changed value, row count or schema, or a file that will not open. It still invalidates every cohort reading that product | LAB-04/05/06 read-lock — 0 measured; the benign verdict carries the burden of proof, never the invalidating one |
| **primary core** | the products and features a primary run actually consumes — the perpetual 1m bars and the 8 features covering all five symbols (G1×3, G2×2, G5×3) | guide 6.2 / LAB-03 — drift in a product outside it can invalidate a cohort but never the primary run |
| **data role** | the declared purpose of a date window: `development` permits fitting and design choices, `outer_evaluation` permits only a frozen-protocol run | development 2020-01-01→2023-12-31; LAB-04/05/06 stay inside it |


## What this phase claims and does not claim

LAB-04 selected parameters fold by fold, LAB-05 produced states, LAB-06 turned them into keep/switch decisions. Each evaluated its own windows independently. **This phase asks whether those decisions can be DELIVERED on one account that never restarts** — and nothing more. It does not claim an edge, and it does not compare arms; the four-arm factorial is LAB-08's.

The exit gate is negative in form: no leakage, no account resets, no handcrafted fills, disabled-hooks parity, dynamic integration, and an unsupported hook recorded as a blocker rather than rerouted. A phase that passes it has shown the machinery does not distort what it delivers.

**Scope: 1 of the 20 primary cells** — A-SC / BTCUSDT, development role, at A-SC's registered 15-minute primary decision interval (guide §10.4).

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
- data role **development**, window **2021-01-01 → 2023-12-31**
- **105,120** 15-minute bars — the alpha's registered decision interval, not the cheaper 4h panel. An integration run on 4h would have had almost no trades, and every gate below would have passed on a flat account
- the activation schedule is arm A's OWN LAB-04 selections at its own six cutoffs; no parameter set here was invented for this phase

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

## L07.1 — parity before anything else

The integration with **nothing scheduled** must reproduce the canonical `run_candidate` path over the same real bars. If it did not, every arm comparison downstream would be measured against a baseline this phase had quietly altered.

| surface | identical |
|---|---|
| orders | **True** |
| account | **True** |
| metrics | **True** |
| selection | **True** |

- canonical fills **238**, integrated fills **238** — equal, and non-zero, so this is not two empty lists agreeing
- final equity 21,997.5687 vs 21,997.5687
- equal final equity is the weakest possible parity and guide 13.6 forbids it as a standalone claim, so metrics compares the whole reported set and selection runs the switching machinery on a no-op activation instead of counting a constant

Separately, **DISABLED vs INERT vs baseline**: identical = **True**. DISABLED never consults the hooks; INERT consults them and they decline. If those two paths differ, the act of asking has a side effect -- and a side effect that small would not read as a bug, it would read as an edge

Fixed-intent Python/Rust parity: **PASS**, established before any performance number is quoted. The native backend exposes no per-fill trace, so full event-trace parity is recorded as `BLOCKED_CAPABILITY` and never claimed.

## T56 / guide 10.3 — one account, parameters changing under it

| | |
|---|---|
| bars | 105,120 |
| entries | 74 |
| engine fills | 148 |
| equity | 20,000 → 20,090.48 (**+0.45%**) |
| account resets | **0** |
| spliced from independent runs | **False** |
| single engine pass | **True** |

Every switch, with what the migration contract cost it:

| activation | requested at bar | effective at bar | blocked for | reason while blocked |
|---|---|---|---|---|
| `act-fold1` | 17,280 | 17,486 | 206 bars | — |
| `act-fold2` | 34,560 | 34,596 | 36 bars | — |
| `act-fold3` | 51,840 | 52,208 | 368 bars | — |
| `act-fold4` | 69,120 | 69,181 | 61 bars | — |
| `act-fold5` | 86,400 | 86,433 | 33 bars | — |

**No switch was instant.** Each waited for a flat book and for its own indicators to warm on real history — guide §9.5's contract, priced in bars. A layer that activated on request would have reported a timing edge it could never have taken.

## L07.4 — the migration contract, exercised on paths this run did not hit

The tape carries **9** requested activations, **6** effected. Beyond the five the account performed, the guide §9.5 paths this particular run never reached are driven explicitly, because a contract tested only by its happy path is a contract nobody has tested:

| blocked reason | count |
|---|---|
| `TRANSITION_BLOCKED_OPEN_CAMPAIGN` | 1 |
| `WAITING_FOR_WARM_INDICATORS` | 1 |

- versions still referenced by live protective orders: `[]` — a retired version stays resolvable while any order points at it
- forced unwind used: **False**

- **open_campaign**: an open trade stays protected by the parameters it entered with; the switch waits for terminal (guide 9.5)
- **warm_indicators**: a new version waits until its indicators are causally warm; it never reinitialises to activate sooner
- **delay_is_recorded**: requested_at and activated_at are both kept, so the price of switching is measured rather than assumed away
- **retirement**: a retired version stays resolvable while any live order references it
- **no_forced_close**: a campaign is never closed to let a switch land; forced unwind is a separate ablation with its own costs

## L07.5 / T55 — segments, and the average that flatters

**6** segments (5 closed, 1 open), and **6,566** no-change triggers — a refresh that fired and changed nothing is recorded, because dropping them would make the refresh cadence look like the switch rate.

| segment | version | start | end | length (days) |
|---|---|---|---|---|
| seg-0 | `pv-18f098c54d7` | 2021-01-01 | 2021-07-02 | 182.1 |
| seg-1 | `pv-224417467fc` | 2021-07-02 | 2021-12-27 | 178.2 |
| seg-2 | `pv-9e73415a51d` | 2021-12-27 | 2022-06-28 | 183.5 |
| seg-3 | `pv-faa15bbfee2` | 2022-06-28 | 2022-12-22 | 176.8 |
| seg-4 | `pv-d3bf37ec84b` | 2022-12-22 | 2023-06-20 | 179.7 |
| seg-5 | `pv-80ad8c254e4` | 2023-06-20 | **null** | — |

The open segment's end is null: **True**. Its length does not exist yet, and writing it would hand any policy reading the tape the answer to how long its own decision is about to last.

### The measured gap T55 exists to prevent

| | |
|---|---|
| **account daily Sharpe** (primary) | **0.0581** |
| unweighted mean of per-segment Sharpes | 0.0971 |
| segment day counts | [182, 178, 183, 177, 180, 193] |

Averaging the fold Sharpes gives **1.7×** the account's own number on the same trades. The segments differ in length by construction, so an unweighted mean weights a 177-day segment like a 193-day one. The daily account series is indifferent to where the boundaries fell, which is why the guide makes it the comparison.

| segment | days | Sharpe (diagnostic only) |
|---|---|---|
| seg-0 | 182 | -0.687 |
| seg-1 | 178 | +1.458 |
| seg-2 | 183 | -1.288 |
| seg-3 | 177 | +0.006 |
| seg-4 | 180 | -0.208 |
| seg-5 | 193 | +1.303 |

## L07.3 — a refit costs time, and the cost is measured

- latency source **measured_benchmark**: one real `causal_fit` is timed in the run at **0.366 s/fit** on 1 worker
- **40** refit jobs at the registered 28-day cadence, 40 completed; delays 1.46s to 1.46s
- jobs with zero latency: **0**
- latency = measured seconds per fit x ceil(fits / workers). Partial waves round UP: three fits on two workers occupy two waves, and rounding down would hand the dynamic policy compute the resource budget forbids
- deployment account reachable from the refit runner: **False** — this runner never receives the deployment account, so a refit cannot mutate it. Candidate evaluation uses the training contract above, whose reset semantics are deliberately different from deployment (guide 10.3)

## L07.6 — what happens when something breaks

All **9 of 9** declared failure modes were EXERCISED, not merely declared:

| mode | times | outcome |
|---|---|---|
| `INCOMPLETE_PROBE_PANEL` | 1 | EVIDENCE_INCOMPLETE |
| `INTERRUPTED_ARTIFACT` | 1 | REFUSED_TO_READ |
| `LIQUIDATION` | 1 | RECORDED_ECONOMIC_EVENT |
| `MISSING_CONTEXT` | 1 | HOLD_INCUMBENT |
| `MODEL_FIT_FAILED` | 1 | KEEP_PREVIOUS_MODEL |
| `OUT_OF_ORDER_JOB` | 1 | HOLD_INCUMBENT |
| `SIMULATION_REJECT` | 1 | RECORDED_NO_POSITION_CHANGE |
| `STALE_CONTEXT` | 1 | HOLD_INCUMBENT |
| `WORKER_FAILURE` | 1 | TRIALS_RETAINED |

- parameters chosen at random to resolve a failure: **False**
- every failure resolves to the validated incumbent or a named incomplete status. No failure is resolved by choosing different parameters, and none is resolved by inventing a value (guide L07.6)

## L07.7 — the future cannot reach the past

- **replay parity**: streaming one event at a time equals the offline replay — **True** over 111,839 events. The consumer derives the DECISION each event implies rather than reading the event's own fields back, which would have passed on any tape at all.
- **prefix stability on the real account**: every price after bar 52,560 multiplied by 5, and the mutation really did change the suffix (**True**). Equity and active version before the cutoff stayed bit-identical: **True**.
- **118** trades happened before the cutoff, so there was something at risk of leaking. A prefix with no trades would have proved nothing.
- the prefix of the longer run equals the whole of the shorter run: **True**

The four-layer causality gate is **CAUSAL** with the leaky control detected (**True**): resampler, scaler, model, online_filter.

## Leakage audit — LAB-07 and everything it inherits

A separate, harsher pass (`scripts/audit_lab07_leakage.py`): **can any information from after a decision reach that decision**, through this phase or through anything it inherited from LAB-03 to LAB-06? **12/12 — CLEAN**.

| check | verdict | had something to detect |
|---|---|---|
| the run stays inside the development role | PASS | yes |
| every parameter version was selected before it was requested | PASS | yes |
| replacing every input after a cutoff leaves the prefix bit-identical | PASS | yes |
| no activation event carries its own end | PASS | yes |
| no decision carries the length, end or total return of its own segment | PASS | yes |
| regime observations on the stream reach no decision in this calendar arm | PASS | yes |
| a refit reads nothing after its cutoff and pays a measured latency | PASS | yes |
| protective exits are iterated to a fixed point, not taken from one pass | PASS | **no** |
| a regime observation is published no earlier than LAB-05 says it is knowable | PASS | yes |
| the parity surfaces compare something that actually moved | PASS | yes |
| loader, resampler, scaler, model and stream are each causal | PASS | yes |
| the bytes the run read still are what the manifest recorded | PASS | yes |

> a probe that had nothing to detect is reported, not counted as evidence. Every defect found in LAB-06 and LAB-07 was a gate that passed because nothing happened

One probe had nothing to detect: **protective exits are iterated to a fixed point, not taken from one pass**. A-SC rests no protective orders at all — 119 entries, 119 technical exits, zero stops or targets — so the exit fixed point converges trivially on this cell. The property is exercised on **A-HMA**, which rests both, in `test_the_fixed_point_holds_on_an_alpha_that_rests_protective_orders`: 26 protective exits, converged, and identical to `run_candidate`.

The strongest of these is the future-mutation probe. Every column the adapter can read — `open, high, low, close, volume` — is multiplied by 5 after bar 52,560, with **118** trades already in the prefix. this is also the empirical proof that the adapters' whole-slice indicator precomputation is causal: if a value at bar t depended on any bar after the cutoff, the prefix would move

## OUT.2 — what the lab binds to, and what it refuses to fake

Probed against the INSTALLED package (`1.1.1`): **7 bound, 0 blocked**.

| lab operation | installed symbol | status |
|---|---|---|
| execution_contract | `quantbt.QuantBTEndpoint.intrabar_bracket_reference` | **BOUND** |
| execution_contract_native | `quantbt.QuantBTEndpoint.intrabar_bracket_rust` | **BOUND** |
| walkforward | `quantbt.walkforward` | **BOUND** |
| walkforward_config | `quantbt.WalkForwardConfig` | **BOUND** |
| walkforward_support_matrix | `quantbt.walkforward_support_matrix` | **BOUND** |
| candidate_selection | `quantbt.optimization.candidate_selection` | **BOUND** |
| volatility_regime_labels | `quantbt.volatility_regime_labels` | **BOUND** |

> an integration point that does not resolve is BLOCKED_CAPABILITY. It is never rerouted to a similar-looking symbol: a reroute succeeds, and a run that completes on economics the study did not register is worse than one that stops

Known blockers, recorded rather than worked around:

- **`engine_fill_trace_native`** — the rust backend exposes no per-fill trace, so Python/Rust parity is established on account path and orders, and full event-trace parity is never claimed
- **`scheduler_callback`** — the installed engine has no refit-scheduler callback, so the lab drives the schedule from OUTSIDE the engine and feeds it fixed intents. The engine's economics are untouched, which is the point

## Audit and acceptance coverage

- **75/75** checklist clauses DONE, driven by `configs/lab07_checklist.json` written BEFORE any integration code (`checklist_written_before_code: True`)
- clauses with no evidence pointer: **none**
- acceptance tests: **68 passed in 3.78s**

Guide §14 coverage as of LAB-07: **56 COVERED, 3 PARTIAL, 5 NOT_YET_IMPLEMENTED** of 64.

| id | status | note |
|---|---|---|
| T53 | **PARTIAL** | LAB-07 fixes the economics and runs ONE arm on them: the account contract is frozen, the compute-budget contract is registered, and the continuous acc |
| T54 | **PARTIAL** | LAB-04 measured which installed modes consume OOS to select and fixed the label. LAB-07 carries that label into the run record. Applying it to a repor |
| T55 | **COVERED** |  |
| T56 | **COVERED** |  |
| T57 | **COVERED** |  |

T53 and T54 stay PARTIAL deliberately. T53 asks whether A/B/C/D share fixed economics and arms C/D do not exist; T54 asks that the legacy label be applied to a reported arm comparison and there is no arm comparison yet. Marking either COVERED would be this phase taking credit for LAB-08's work.

## Corrections made during LAB-07

Both were found by self-review before this report was written, and both are the same failure: **a gate that passes because nothing happened.**

1. **The first run traded nothing.** Driving the continuous account from the 4h feature panel with no signals gave 0 fills, a flat equity curve, 1 segment and a null Sharpe — and every gate passed. `all_fills_from_engine` was true over an empty list; the T55 comparison had one segment to compare. Rebuilt on **105,120 real 15-minute bars** with the real A-SC adapter and arm A's own six LAB-04 selections: 75 entries, 150 fills, 6 segments.
2. **The intent tape was built from the final adapter's decision list.** Each parameter version's adapter accumulates only the bars it personally saw, so taking the last one's list silently dropped every trade made under an earlier version — while the entry counter still counted them. The symptom was **75 entries but 18 fills**, and the reported return was **+2.11%**. Assembling the tape from the ACTIVE adapter at each bar gives 150 fills and **+0.17%**. The first number would have been published.

### Found by the leakage re-audit, after the first version of this report

3. **The warm-up gate was a magic number, and it moves the result.** `WARM_BARS = 64` was a constant I picked. Measured on this cell, 0 / derived / 512 bars give **+0.45% / +0.45% / −3.07%** — an unregistered free parameter of the switching policy, which guide §10.5 puts in the experiment-search ledger. The requirement is now **derived from each adapter's own `warmup_bars()`** (39, 36, 60, 61, 33 bars = its `AP + 3`), so it is the alpha's declaration rather than my choice. The headline return moved from +0.17% to **+0.45%** as a result.

4. **The warm-up gate does not do what the first draft said.** A-SC precomputes its indicator arrays causally over the whole slice, so the values at a bar are already correct the moment the shadow adapter is built; waiting does not make them more so. What the gate actually buys is that the new version has been running on live bars for at least as long as it declares it needs — a **policy delay**, now reported as one instead of as an accuracy claim.

5. **The exit fixed point was missing.** `run_candidate` iterates protective exits until the whole-window engine run agrees with what the sweep applied; the integration did one pass. Harmless for A-SC, which rests no protection — and silently wrong for A-HMA, A-VWAP and A-HASH, which LAB-08 runs through this same function. Added, and verified against `run_candidate` on A-HMA.

6. **The future-mutation probe left `volume` untouched.** A-SC feeds volume into an MFI, so a strategy reading the future through volume would have passed. Every readable column is now mutated.

7. **The trace mixed two arms.** It is labelled `A_calendar_on_one_account` — guide §10.1 arm A, which uses **no regime information** — while carrying 6,566 `REGIME_OBSERVATION_READY` events, because L07.2 requires the stream to carry them. Next to 5 activations that looks like cause and effect whether or not it is. Every activation now names its source, and `regime_information_reached_a_decision` is **False**, checked rather than asserted.

8. **The event bus crashed on a mixed-timezone stream.** Storage timestamps are naive UTC by convention and engine frames are aware; one naive timestamp raised `TypeError` on the first sort and would have taken the whole stream's ordering with it. Normalised at publish, with the interpretation stated rather than inherited.

### Found by a second leakage pass, before LAB-08

Six more, and every one was a **check that could not fail**:

9. **The regime-isolation check was circular.** The runner built `{activation_id: "calendar_cutoff"}` and handed it to the function that then verified every source was `calendar_cutoff`. It asserted its own conclusion. Sources are now DERIVED from the tape by matching against LAB-04's declared cutoffs — and the moment they were, **the check failed**: activations are published at their EFFECTIVE time, and one of them lands on a 4h regime observation by pure coincidence. Attribution now keys on the REQUEST time, which the activation carries because it is a past fact.

10. **Two of the four parity surfaces were trivial.** `metrics` compared only final equity — which guide §13.6 forbids as a standalone parity claim and which `account` already implies. `selection` counted a constant that is true by construction when the schedule is empty. `metrics` now compares the whole reported set (return, Sharpe, drawdown, observation count, final equity) and `selection` schedules an activation to the SAME parameters halfway through and requires it to be a no-op — which runs the switching machinery instead of counting a constant.

11. **The inert-hook parity compared three empty accounts.** Its digest was `4f53cda18c2baa0c` — the SHA-256 of an empty list — in all three runs. It is now driven by the canonical run's real fills, and `disabled_hooks_parity` **refuses** a signal column that never trades.

12. **The replay consumer read a key that does not exist.** `payload.get("quantity", 0.0)` on an engine fill whose key is `qty` returned **0.0 for every fill**, so the consumer looked like it was reading the account while reading a default. It now raises on a missing key rather than defaulting.

13. **T57 was marked COVERED by tests that do not test it.** The three cited tests were about refit-latency rounding; T57 is about sequential-vs-adaptive-batch semantics. Replaced with five that check the declared contract, the fixed candidate matrix replaying to the same point, and seeded determinism. Two intermediate versions of the last test grepped prose and flagged T57's own title, then its own negation — so it is now structural rather than lexical.

14. **The regime publication lag was invented.** Observations were published at **+1 minute**; bars are left-labelled, so an observation stamped at a bar open is knowable only when that bar closes — **+4h**, which is exactly what LAB-05's emission tape records. **15× too early.** Nothing consumes it in this calendar arm, but LAB-08's arms C/D/E will, and a false availability on the tape is a leak waiting to be inherited. Now derived from `panel.REGIME_INTERVAL` and cross-checked against LAB-05.

A fifteenth was caught by the reachability gate: `prefix_stability` in `continuous.py` was superseded by the real-account version in the runner and left behind as a weaker duplicate. Deleted.

A sixteenth was caught by a new test rather than by the run: `daily_account_comparison` compared tz-naive segment boundaries against a tz-aware equity index. It worked in the runner because both happened to be aware, and raised `TypeError` the moment a caller mixed them. Boundaries are now aligned to the index once, inside the function.

