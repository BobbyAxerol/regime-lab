# LAB-04 — Calendar baseline và robust-neighborhood selection

Generated from committed artifacts by `scripts/write_lab04_report.py`. No optimizer or experiment is rerun here.

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **anchor** | a parameter point chosen to be the CENTRE of a local panel, so probes get placed around it | LAB-04 — 4 anchor slots per cutoff: 2 from the TPE ranking, 1 space-filling, 1 incumbent |
| **probe** | a parameter point placed near an anchor to measure how the result changes when the parameters move slightly; it is evaluated even when it loses money | LAB-04 — 8 probes per anchor, inside a frozen radius of 0.12 schema-distance |
| **space-filling** | placing an anchor FAR from the ones already chosen, so the local panels do not all sit inside the region the sampler already favours | LAB-04 — the 3rd of the 4 anchor slots; the evaluated point with the largest minimum distance to the TPE anchors (guide 7.2 step 1) |
| **TPE** | Tree-structured Parzen Estimator, the Optuna sampler that concentrates its trials where past trials scored well | LAB-04 — the 64 discovery evaluations per cutoff; its top 2 points become anchors |
| **local panel** | the set {anchor + its probes} scored over the same inner episodes; it is the evidence that a parameter region is stable rather than a lucky point | LAB-04 — arm B may only choose a candidate that HAS one |
| **inner episode** | a contiguous equal-length block of the training window; the score is computed per episode so a single lucky stretch cannot carry a candidate | LAB-04 — 6 episodes of 30 days inside each 180-day training window |
| **G** | the 0.25 quantile of a candidate's utility across its inner episodes — its LOWER-TAIL quality, not its average | LAB-04 — the economic-quality gate is G > 0 |
| **F** | how much better the candidate is than its neighbours (median over episodes of the 0.75 quantile of regret); a HIGH F means the candidate is a lonely spike | LAB-04 — subtracted from G, so a spike is penalised |
| **R** | the robust score, R = G − λ_F·F: lower-tail quality minus the penalty for being a spike | LAB-04 — arm B selects argmax R among admissible candidates |
| **P_survive** | the share of (candidate, episode) pairs in the local panel that pass the quality and risk gates | LAB-04 — registered threshold 0.60 |
| **medoid** | the member of a set with the smallest total distance to the others — an actual evaluated point, unlike a centroid | LAB-04 — reported as the representative; a centroid is only a proposal until it is run |
| **incumbent** | the parameter set currently deployed, carried into the next cutoff as a candidate | LAB-04 — it is an anchor with the same probe budget as any challenger |
| **cutoff** | the boundary between a fold's training window and its test window; selection happens here and is frozen before the test window is touched | LAB-04 — 6 cutoffs per cell, 90 across the matrix |
| **cell** | one alpha on one symbol, evaluated across the whole calendar | LAB-04 — 4 alphas × 5 symbols = 20 cells |
| **arm A / arm B** | arm A selects with the installed engine's rule (argmax in-sample objective); arm B selects with the lab's robust-neighborhood rule (argmax R). Same calendar, same pool, same budget | LAB-04 — the only registered difference between them is the selection rule |
| **retained the incumbent** | the selector returned nothing admissible, so the previous parameters stayed deployed. It is a valid technical pass, not a failure — but it is also not evidence about the selector | LAB-04 — arm B did this at half of all cutoffs |
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

## L04.1 — What the installed WFO actually does

The public route's default resolves the winner in `quantbt.walkforward._select_oos_candidate_record` as `max(records, key=record.objective)`.

optimization_mode='none' -- the public default -- ran ONE trial on this fixture and simply evaluated the supplied parameters, while every other mode ran 14-15. So the default route performs no parameter search; a selector only exists once a mode is chosen. Arm A therefore instantiates the rule the installed code applies to trial records (_select_oos_candidate_record under the default candidate_selection_metric), and the lab supplies the trial records.

| mode | trials | folds | searched | engine declares OOS used | mutation probe |
|---|---|---|---|---|---|
| `none` | 1 | 3 | False | True | MEASURED → False |
| `mode_1_decay` | 14 | 3 | True | True | MEASURED → False |
| `mode_2_sbb` | 14 | 3 | True | False | MEASURED → False |
| `mode_3_flat_minima` | 14 | 3 | True | True | MEASURED → False |
| `mode_4_is_only_robust` | 14 | 3 | True | False | MEASURED → False |
| `mode_5_full_robust` | 15 | 1 | True | False | NO_OUT_OF_SAMPLE_REGION_EXISTS → None |
| `mode_1_decay@per_fold_decay` | — | — | — | — | MEASURED → True |
| `mode_1_decay@per_fold_causal` | — | — | — | — | INCONCLUSIVE_MUTATION_HAD_NO_EFFECT → None |

- mode_5_full_robust collapsed to a single fold: it is full-sample calibration, not walk-forward, and its selection is not an out-of-sample claim.
- **Legacy OOS labelling.** a mode that declares OOS-adjusted selection is labelled A_legacy_selection_adjusted and is never reported as an untouched baseline (guide 10.1 / 13.6) Modes declaring OOS-adjusted selection: `['none', 'mode_1_decay', 'mode_3_flat_minima']`.
- **Probe power.** under expanding windows only the final test segment is out of sample for every fold, so a null probe bounds rather than refutes OOS dependence; where the declaration and the probe disagree, the declaration is the label

| dimension | measured |
|---|---|
| sampler | `optuna.samplers.TPESampler` + `DuplicatePruner`, seed 42 |
| default trials | 0 |
| objective backend | proxy — scoring_backend='endpoint' returned all-zero Sharpes for this strategy shape, so the proxy objective is used and the divergence is recorded rather than silently accepted |
| candidate freeze | `_select_is_candidate_records(records, param_ranges, config)` → `_select_oos_candidate_record(records, config)` |
| baseline floor | `min_trades_per_year=None`, `trade_penalty_factor=None` — no floor unless configured |
| retention | financial=`score`, research=`none`, scope=`selected_final_execution` |
| fold account policy | `carry_position` |

## L04.2 — Selector counterexamples, scoped by family

a claim about 'the selector' would be wrong: the two families measure distance differently, so every finding names the family it applies to

- **`candidate_selection`** — normalised by the SAMPLED span of observed records
- **`walkforward`** — normalised by the DECLARED param_ranges; non-varying parameters dropped

| id | counterexample | family | verdict | source |
|---|---|---|---|---|
| CE-01 | sharp peak versus a broad profitable neighbourhood | `lab robust score` | **LAB_SELECTOR_IMMUNE** | `selector.robust_score.score_candidate` |
| CE-02 | a perfectly flat region that is negative | `lab robust score` | **LAB_SELECTOR_IMMUNE** | `selector.robust_score.score_candidate` |
| CE-03 | duplicate samples must not inflate the local panel | `lab probe design` | **LAB_SELECTOR_IMMUNE** | `selector.probe_design.ProbeDesign.probes_for` |
| CE-04 | a fixed dimension dilutes every distance | `quantbt.optimization.candidate_selection` | **DEFECT_CONFIRMED** | `_param_distance, candidate_selection.py:281-300` |
| CE-05 | one far-away sample rescales the whole geometry | `quantbt.optimization.candidate_selection` | **DEFECT_CONFIRMED** | `_numeric_span, _param_distance` |
| CE-06 | an inactive parameter manufactures distance | `quantbt.optimization.candidate_selection` | **DEFECT_CONFIRMED** | `_param_distance, candidate_selection.py:290-299` |
| CE-07 | no local consensus available | `lab robust score` | **LAB_SELECTOR_IMMUNE** | `selector.robust_score.score_candidate` |
| CE-08 | a centroid nobody evaluated is not deployable | `lab representative` | **LAB_SELECTOR_IMMUNE** | `selector.representative.assert_evaluated` |
| CE-09 | a raw-quality guard disagrees with the robust objective | `lab robust score` | **LAB_SELECTOR_IMMUNE** | `selector.robust_score.score_candidate` |
| CE-10 | full-sample tuned presets must not seed the primary bank | `lab preset quarantine` | **LAB_SELECTOR_IMMUNE** | `configs/preset_catalog.json` |

**CE-04 — a fixed dimension dilutes every distance**

- observed: `{"distance_with_fixed_dim": 0.57735, "distance_without_fixed_dim": 0.707107, "ratio": 0.8165}`
- expected: a parameter that never varies carries no information and must not enter the denominator
- reproducer: call the installed _param_distance with and without a constant parameter in param_names
- scope: the WFO family is NOT affected: _is_clusterable_param drops any parameter that does not vary before the matrix is built

**CE-05 — one far-away sample rescales the whole geometry**

- observed: `{"distance_before": 0.707107, "distance_after_one_far_sample": 0.007215, "shrink_factor": 98.0, "span_before": 2.0, "span_after": 196.0}`
- expected: geometry must come from the DECLARED bounds, so an unrelated sample cannot rescale it
- reproducer: add one distant record and re-measure the distance between two unchanged points
- scope: the WFO family normalises by the declared (low, high) in param_ranges and is immune; only the CandidateSelector family rescales

**CE-06 — an inactive parameter manufactures distance**

- observed: `{"installed_distance": 0.57735, "cause": "a missing value is not numeric, so the branch returns a full unit of distance"}`
- expected: an inactive conditional parameter must not create distance; a branch MISMATCH is a declared, locked penalty instead
- reproducer: compare two points that differ only in whether a conditional branch is active


## L04.3 — Candidate-independent probe engine

seeds derive from a sha256 of (seed, anchor_id) and every set iteration is sorted, so a design is reproducible across processes

| alpha | probes | unique | structurally invalid rejections |
|---|---|---|---|
| A-SC | 8 | 8 | 0 |
| A-HMA | 8 | 8 | 0 |
| A-VWAP | 8 | 8 | 0 |
| A-HASH | 8 | 8 | 0 |

- `valid_bad_probes_retained` = True
- `structurally_invalid_is_not_bad_performance` = True
- `runtime_error_means_incomplete_evidence` = True

### Registered probe-radius sensitivity (guide 7.2)

the primary radius is 0.12 regardless of what this shows; a radius is a registered design choice, never picked after seeing an outer result

| radius | arm B status | eligible | G (comparable) | R (NOT comparable) | distance from the primary selection |
|---|---|---|---|---|---|
| 0.06 | SELECTED | 16 | +0.2162 | +0.1294 | +0.0455 |
| 0.12 **(primary)** | SELECTED | 15 | +0.1556 | +0.0640 | +0.0000 |
| 0.24 | SELECTED | 13 | +0.1556 | +0.0735 | +0.0000 |

- arm B selection changes with the radius: **True**
- arm A is radius independent: **True**

> **Do not read R down this column.** R = G - lambda_F * F, and F is the regret against NEIGHBOURS. A smaller radius puts the neighbours closer, which mechanically shrinks F and inflates R. So a higher R at a smaller radius is an artefact of the geometry, not evidence that the smaller radius selects better. Only the SELECTED POINT is comparable across radii, and only G is comparable, because G does not depend on the neighbourhood at all.

Comparable across radii: `['the selected point', 'G']`. Not comparable: `['F', 'R', 'P_survive']`. This is one cutoff of one cell, so it characterises the design's sensitivity; it is not a result about which radius performs better, and the primary stays 0.12.

## L04.4 — Robust scoring and incumbent parity

- the incumbent is scored on the same episodes, the same neighbourhood budget and the same utility as any challenger; when the raw guard and the robust objective disagree, both are logged
- same episode count: **True**, same neighbour budget: **True**
- guard **before** (raw quality G): winner `challenger`
- guard **after** (robust objective R): winner `incumbent`
- selection hyperparameters: `{"lambda_f": 1.0, "g_quantile": 0.25, "f_quantile": 0.75, "min_quality": 0.0, "survive_threshold": 0.6, "note": "selection hyperparameters chosen on development; not universal constants"}`

## L04.5 / L04.6 — Arm A vs arm B on the frozen calendar

Arm **A**: installed selector + frozen calendar  
Arm **B**: robust neighborhood selector + the SAME frozen calendar  
Regime information used: **False**

Matched between the arms:
- same fold calendar and cutoffs
- same training memory per fold
- same engine, execution contract and frozen account
- same retention rule
- same candidate pool at every cutoff
- same evaluation budget
- no regime information in either arm

Calendar: train 180D, test 180D, 6 folds from 2021-01-01, 6 equal-length inner episodes per training window.
Budget per cutoff: 64 discovery + 2+incumbent anchors × 8 probes = 96 nominal.
Actual effort: **9155 unique executions**, **54930 candidate-episode visits**, 0 structurally invalid, 0 runtime errors. unique execution count and candidate-episode visits are reported, not an Optuna trial count (guide 7.2)

### Every cell, win or lose

```
A-HASH  BNBUSDT    NOT_READY  A=null B=null  (metrics are null, never PnL 0)
A-HASH  BTCUSDT    NOT_READY  A=null B=null  (metrics are null, never PnL 0)
A-HASH  DOGEUSDT   NOT_READY  A=null B=null  (metrics are null, never PnL 0)
A-HASH  ETHUSDT    NOT_READY  A=null B=null  (metrics are null, never PnL 0)
A-HASH  SOLUSDT    NOT_READY  A=null B=null  (metrics are null, never PnL 0)
A-HMA   BNBUSDT    A=  +0.0311 B=  +0.0369  trades A=344/B=276  conc A=+0.6881/B=+0.5377
A-HMA   BTCUSDT    A=  -0.0283 B=  +0.0529  trades A=328/B=272  conc A=+0.5692/B=+0.4584
A-HMA   DOGEUSDT   A=  -0.0113 B=  +0.0569  trades A=284/B=258  conc A=+0.5059/B=+0.4174
A-HMA   ETHUSDT    A=  -0.0809 B=  +0.0150  trades A=442/B=374  conc A=+0.9539/B=+0.9020
A-HMA   SOLUSDT    A=  -0.0915 B=  +0.1719  trades A=280/B=272  conc A=+0.4789/B=+0.4197
A-SC    BNBUSDT    A=  +0.2072 B=  +0.5296  trades A=230/B=336  conc A=+0.9102/B=+0.9737
A-SC    BTCUSDT    A=  +0.0196 B=  +0.0519  trades A=142/B=340  conc A=+0.5460/B=+0.3510
A-SC    DOGEUSDT   A=  +0.4632 B=  +0.6826  trades A=176/B=286  conc A=+0.9530/B=+0.8439
A-SC    ETHUSDT    A=  +0.1534 B=  +0.1294  trades A=690/B=1010  conc A=+0.6599/B=+0.7298
A-SC    SOLUSDT    A=  +0.5426 B=  +0.7749  trades A=150/B=168  conc A=+0.5064/B=+0.3867
A-VWAP  BNBUSDT    A=  +0.0232 B=  -0.0086  trades A=42/B=8  conc A=+0.6369/B=null
A-VWAP  BTCUSDT    A=  -0.0433 B=  -0.0508  trades A=126/B=154  conc A=+0.4380/B=+1.0000
A-VWAP  DOGEUSDT   A=  +0.0612 B=  +0.0296  trades A=742/B=1384  conc A=+0.8175/B=+0.5756
A-VWAP  ETHUSDT    A=  +0.0523 B=  -0.0121  trades A=44/B=8  conc A=+0.7346/B=null
A-VWAP  SOLUSDT    A=  +0.1315 B=  +0.0276  trades A=232/B=398  conc A=+0.8316/B=+0.7837
```

### What each arm was allowed to choose from

Both arms are handed the identical pool of evaluations at every cutoff. They differ in admissibility, and that difference is the point rather than a confound: arm A ranks the whole pool on the in-sample objective, while arm B may only choose a candidate that has a local panel and clears the quality, survival and local-evidence gates. A pure discovery point with no designed neighbourhood is `INSUFFICIENT_LOCAL_EVIDENCE` for arm B by construction.

- mean candidates arm A ranked per cutoff: **101.7**
- mean candidates arm B found admissible per cutoff: **4.5**
- robust-score status counts across every cutoff: `{"ELIGIBLE": 409, "FAILS_ECONOMIC_QUALITY": 3433, "INSUFFICIENT_LOCAL_EVIDENCE": 5295, "FAILS_SURVIVAL": 18}`

### Contrast B − A

- **net return over the chained account**: B better in 9, A better in 6, ties 0 of 15 cells; sign-test p = 0.60723876953125
- **Sharpe over the whole chained horizon (NOT annualised)**: B better in 9, A better in 6, ties 0 of 15 cells; sign-test p = 0.60723876953125
- mean difference +0.0705, median +0.0323, worst cell -0.1039, best cell +0.3224
- a paired sign test over 15 cells drawn from the same five symbols and one calendar; the cells are not independent, so this is a descriptive statistic and not a confirmatory test

### Registered hypothesis and the registered endpoint

This phase evaluates exactly one registered contrast, **H1 = B-A**, registered 2026-09-09T18:48:15.264005+00:00: *does independent-neighborhood selection beat the installed selector on the same calendar?*

- registered primary endpoint: **mean daily net-return difference between arms on the same risk budget**
- terminal chained return is reported elsewhere for context; it is NOT the registered endpoint and is not used to decide the conclusion
- registered minimum economic effect: **6.40e-05/day (0.64 bps/day)**, fixed before any arm comparison = True
- **measured mean daily net-return difference (B−A): 5.567e-05/day**
- cells whose own daily difference clears the minimum effect: **7/15**

> The pooled effect is **BELOW** the registered minimum. A difference below it sits inside the registered cost-stress band and is reported as inconclusive, never as an edge. The large-looking terminal chained returns elsewhere in this report are context, not the endpoint.

**Conclusion level: `INCONCLUSIVE_SAMPLE`** (from the registered vocabulary ['DESCRIPTIVE_VALUE', 'CONDITIONAL_RESPONSE_EVIDENCE', 'NET_PARAMETER_SELECTION_EDGE', 'NET_TIMING_EDGE', 'NET_POLICY_EDGE', 'NO_INCREMENTAL_VALUE', 'INCONCLUSIVE_SAMPLE', 'FAILED_VALIDITY'])

Blockers preventing a stronger claim:
- the sign reverses inside A-VWAP
- the arms switched parameters at materially different rates, so the contrast mixes selection quality with switching frequency
- 4 of 15 cells had an arm that never exercised its selector at any cutoff, so part of this contrast compares a fixed seed point against a selector rather than two selectors

- multiplicity: Holm-type across the primary contrast family; block bootstrap for paired uncertainty — applied here: **False**. H1 is one member of a five-contrast primary family; the Holm-type adjustment and the paired block bootstrap are applied in LAB-09 once the other arms exist. No adjusted p-value is claimed here.
- falsification commitments in force:
  - a negative or inconclusive result is a valid outcome and is published, not rerun until it wins
  - risk-only improvement is never recorded as a parameter-selection edge
  - zero switches because no challenger qualified is a valid technical pass
  - an alpha that cannot be certified is reported NOT_READY with null metrics, never PnL=0
- exercised in this phase: zero switches because no challenger qualified is a valid technical pass -- arm B retained the incumbent wherever no candidate cleared the registered gates, and that is reported as a pass, not repaired by loosening a threshold

### How binding is the registered gate? (declared post-hoc)

The registered gate is `min_quality=0.0`, `P_survive >= 0.6`, fixed on development before any arm ran. **It stays the primary and is not revised here.** the registered gate bound at half of all cutoffs; a reader cannot weigh the result without that, and hiding it would make the retention rate look like a property of the market rather than of a threshold the lab chose

| min_quality | P_survive ≥ | registered | cutoffs with ≥1 admissible | median eligible |
|---|---|---|---|---|
| -1.0 | 0.6 | – | 52/90 | 9.0 |
| -0.5 | 0.6 | – | 50/90 | 6.0 |
| 0.0 | 0.5 | – | 46/90 | 1.0 |
| 0.0 | 0.6 | **(registered)** | 44/90 | 0.0 |
| 0.0 | 0.7 | – | 39/90 | 0.0 |

- local panels are NOT the bottleneck: **90/90** cutoffs had at least one candidate with a computable R
- score_candidate labels a candidate by the FIRST gate it fails, so FAILS_SURVIVAL is undercounted while the quality gate binds. Loosening min_quality does not admit everything: it exposes the P_survive gate underneath, which is why a very loose quality threshold still leaves many cutoffs with nothing admissible.
- **eligibility is re-derived from stored G and P_survive, so this shows only how often a looser gate would have left arm B something to choose. It does NOT simulate the outcome of choosing it and is not evidence that a looser gate performs better.**

### Cells where an arm never used its selector at all

- arm A: **0/15** cells held the registered seed point at every cutoff
- arm B: **4/15** cells held the registered seed point at every cutoff
  - `A-SC/BNBUSDT` — 6 cutoffs, binding constraint `ALL_FAIL_ECONOMIC_QUALITY`, net return +0.5296
  - `A-SC/DOGEUSDT` — 6 cutoffs, binding constraint `ALL_FAIL_ECONOMIC_QUALITY`, net return +0.6826
  - `A-VWAP/BNBUSDT` — 6 cutoffs, binding constraint `ALL_FAIL_ECONOMIC_QUALITY`, net return -0.0086
  - `A-VWAP/ETHUSDT` — 6 cutoffs, binding constraint `ALL_FAIL_ECONOMIC_QUALITY`, net return -0.0121

an arm listed here ran the registered seed point for the whole evaluation and never exercised its selector. That is a valid technical pass under the registered falsification commitments, and it is NOT evidence about the selector. Any contrast that includes these cells is partly a comparison against a fixed seed point.

| contrast | cells | B better | A better | sign-test p | mean daily B−A |
|---|---|---|---|---|---|
| all cells | 15 | 9 | 6 | 0.60723876953125 | 5.567e-05 |
| both arms actually selected | 11 | 7 | 4 | 0.548828125 | 4.379e-05 |

Excluded: `A-SC/BNBUSDT, A-SC/DOGEUSDT, A-VWAP/BNBUSDT, A-VWAP/ETHUSDT`. the same contrast with every cell removed in which an arm never exercised its selector. If the effect lives mostly in the excluded cells, the phase measured holding still rather than selecting well.

### The same contrast, split per alpha

| alpha | cells | B better | A better | winner | mean B−A | agrees with pooled |
|---|---|---|---|---|---|---|
| A-HMA | 5 | 5 | 0 | **B** | +0.1029 | True |
| A-SC | 5 | 4 | 1 | **B** | +0.1565 | True |
| A-VWAP | 5 | 0 | 5 | **A** | -0.0478 | False |

> **SIGN REVERSAL in A-VWAP.** The pooled winner is `B`, but inside these alphas the sign is the other way. an alpha whose sign disagrees with the pooled result is a reversal, not noise to be averaged away. The pooled sign test must never be quoted on its own where a reversal exists (guide 13.6).

### Evidence reported before the selection claim (L04.6)

| dimension | arm A | arm B |
|---|---|---|
| cells with a losing chain | 5 | 3 |
| worst cell net return | -0.0915 | -0.0508 |
| mean losing folds (of 6) | 3.00 | 2.73 |
| mean max drawdown | +0.1027 | +0.0882 |
| period concentration | 0.6820 | 0.6446 |
| engine fills | 4252 | 5544 |
| entries (positions opened) | 2126 | 2772 |
| mean holding bars | 444.4 | 259.3 |
| mean exposure | 0.333 | 0.314 |
| mean parameter turnover | 0.3580 | 0.1594 |
| distinct parameter sets per cell (of 6) | 6.00 | 3.33 |
| median evaluated neighbours | 8.0 | (shared pool) |

- if a selector returns nothing admissible, the incumbent is retained; identical for both arms Retention events per arm:
  - arm A: **0/90** cutoffs kept the incumbent — none
  - arm B: **46/90** cutoffs kept the incumbent — {"ALL_FAIL_ECONOMIC_QUALITY": 46}
- **5 cells NOT_READY** with null metrics, never PnL 0: LAB-02 certification NOT_READY_SPECIFIC_BLOCKER: BLOCKED_CAPABILITY: the canonical three-rung partial ladder needs a next-open entry, a protective stop and partial reduce-only exits on ONE route. intrabar_bracket_v1 provides the first two but a single take-profit level; the orders route provides the ladder but fills the entry at the stamped bar's close and rejects stop_market. Measured, not assumed.

### Integrity checks on the chained account

- deployment legs chained: **180**
- legs that failed to deploy (a gap in the chain, never a zero): **0**
- legs where the adapter/engine fixed point did not converge: **0** (a non-converged leg is reported, not silently accepted)
- engine_fills counts FILLS -- an entry and its exit are two. entries counts positions opened. The `trades` column in the per-cell table is engine_fills.

### What the deployed point's own local panel said

| | arm A | arm B |
|---|---|---|
| deployments | 90 | 44 |
| deployed with no local panel at all | 0 | 0 |
| deployed a point its own panel rejects | 56 (0.622) | 0 (0.000) |
| robust status of the deployed point | `{"ELIGIBLE": 34, "FAILS_ECONOMIC_QUALITY": 54, "FAILS_SURVIVAL": 2}` | `{"ELIGIBLE": 44}` |

share_without_a_local_panel is the sharp-peak-with-no-evidence exposure. It is zero for both arms here, and structurally so: arm A picks the top in-sample objective and the top discovery points are exactly the anchors that get probed. The informative number is share_its_own_panel_rejects -- a point that WAS surrounded by probes, whose panel says it fails the quality or survival gate, and which arm A deploys anyway because its rule never reads that panel. Arm B cannot do this by construction, which is a definitional difference between the arms, not an out-of-sample result.

### Incumbent parity, measured on the run itself

- cutoffs: **90**; the incumbent was an anchor at **90** of them (always = True)
- probes per anchor seen across every cutoff: [8] — same budget for every anchor = **True**
- smallest evaluated local panel seen: [8]
- guide 7.2: the incumbent sits inside the anchor set and receives the same probe design, budget and constraints as any challenger

### What else could explain the difference

- incumbent retention rate: arm A 0.000, arm B 0.511 (gap 0.511)
- material asymmetry: **True** — arm B kept the incumbent at a materially different rate from arm A, so any B-A difference mixes TWO mechanisms: choosing a better point, and changing the point less often. This experiment does not separate them.
- the control that would separate them: a HOLD control on the same calendar that never re-selects after the first cutoff. It is registered in the LAB-06 control family (CALENDAR_MATCHED / RISK_ONLY) and is NOT run here; until it is, no causal claim about the selector is available

### Verdict

> no separation: B better in 9 cells, A better in 6, sign-test p=0.60723876953125. The neighborhood selector is not shown to improve stable performance on this calendar; both arms are kept for the factorial rather than defaulting to the new selector CAVEAT: arm B kept the incumbent at a materially different rate from arm A, so any B-A difference mixes TWO mechanisms: choosing a better point, and changing the point less often. This experiment does not separate them. a HOLD control on the same calendar that never re-selects after the first cutoff. It is registered in the LAB-06 control family (CALENDAR_MATCHED / RISK_ONLY) and is NOT run here; until it is, no causal claim about the selector is available.

both arms are retained for the LAB-06 factorial regardless of this result; B is not assumed correct and A is not retired (guide L04.6)

## Read-lock status at the time of this phase

- status: **EXTERNAL_VINTAGE_RESTAMP_ONLY**, primary run valid: **True**
- the lab's own snapshot bytes: intact
- 23 closed partitions drifted by digest and were READ to see what changed: **0 content revisions**, **23 ingest re-stamps**
  - the re-stamps are `crypto_binance_futures_metrics_5m`; every measured column is identical and only `ingested_at` moved, so the numbers this phase read are the numbers upstream still holds. A digest says *different bytes*; only a read says *different numbers*
- a primary run stays valid while the lab's own snapshot bytes match the manifest and no CLOSED partition of a product the primary core reads has changed upstream. Drift in any other product invalidates the cohorts that read THAT product and is listed in products_invalidated; it is never downgraded to a warning.

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
- **15 of 20** primary cells ran; 5 are NOT_READY with null metrics rather than a PnL of 0, which would bias every aggregate
- alphas covered: A-HMA, A-SC, A-VWAP
- arm A and arm B share one account contract, one calendar and one search budget; no arm reads any product the other does not

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

## Audit and acceptance coverage

- clause audit: **64/64** DONE
- acceptance tests: `71 passed in 26.88s` (passed = True)
- acceptance IDs covered by this phase: T29, T30, T31, T32, T33, T34, T35, T36
- guide §14 coverage as of LAB-06: `{"COVERED": 53, "PARTIAL": 3, "NOT_YET_IMPLEMENTED": 8}` of 64

## Corrections made during LAB-04

- **The probe design was not reproducible.** Per-anchor seeds came from `hash()` on a string and the active-parameter list came from set iteration, both salted per interpreter, so a "frozen" design produced a different probe set in every process. Seeds now derive from a SHA-256 digest and every set iteration is sorted; a test runs the design under three `PYTHONHASHSEED` values and requires identical probe ids.
- **The OOS mutation probe was invalid as first written.** With `window_mode="expanding"`, a later fold trains on an earlier fold's test window, so mutating everything after one global date rewrote training data. Every earlier "selection is in-sample only" reading from that probe was unsupported. The probe now checks IS invariance on a fixed parameter point first and refuses to conclude otherwise, and it places the cut after the latest `train_end` across all folds.
- **Declared search bounds excluded the region the alphas operate in.** The first draft declared A-HMA `min_length` at 4..40 against preset evidence of 120..320, and A-VWAP `htf_ema_len` at 10..60 against 130..570. Measured on BTCUSDT over 2020-07..2021-01, A-VWAP's entry gate was then empty: the reversion trigger fired on 697 long and 1147 short bars and the HTF trend filter agreed on 0 and 1. Bounds now enclose each alpha's operating range; preset VALUES remain quarantined and are never candidates or anchors.
- **The LAB-03 qualification smoke reported zero engine fills** because it sized entries in raw units — one whole coin, about 35,000 USDT of BTC on 20,000 of capital — which the engine rejects for margin. The frozen account contract's 2,000 USDT entry notional is now wired through `unit_notional`, a parameter the bridge previously accepted and ignored.
- **A fixed-point loop over the whole window could not converge affordably.** It gained roughly one trade per pass at about 17 s per pass for A-HMA. Replaced with one chronological sweep that asks the engine about a single trade at a time (~10 ms), followed by one whole-window run whose protective exits must agree with what the adapter was driven with; disagreement is reported, not absorbed.
- **A-HMA's Hull kernel was 94% of evaluation cost.** A compiled twin was added and is admitted only while it is bit-exact against the interpreted reference; features were verified identical and `prepare()` went from 8.7 s to 0.18 s.
- **The read-lock was too coarse.** A closed-partition change in any product invalidated every run. Drift is now attributed per product and scored against what a run reads, so the measured metrics-product rewrite invalidates the G3 cohort without falsely invalidating a primary run that never reads it.

