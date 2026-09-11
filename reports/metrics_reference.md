# What each phase actually measures, and what "better" means

The honest headline first: **most of what this lab checks is not a "better/worse" number at all.**
The large majority of the 781 tests are binary correctness gates — a thing either holds exactly or
it does not. Only LAB-04 produces a number that answers "did this improve anything", and that
number came back **inconclusive**.

Metrics are grouped below by what kind of question they answer, because mixing them is how a
technical pass gets mistaken for an economic result.

---

## Group A — economic metrics you would recognise (LAB-04 only)

These exist in exactly one place: the arm A vs arm B calendar comparison.

| metric | what it is | measured (v1 matrix) |
|---|---|---|
| **mean daily net-return difference** | THE registered primary endpoint: mean daily net return of arm B minus arm A on the same risk budget | **5.695e-05/day** |
| registered minimum economic effect | fixed before any comparison, from cost uncertainty × turnover | 6.4e-05/day |
| **verdict** | endpoint vs threshold | **BELOW → `INCONCLUSIVE_SAMPLE`** |
| terminal chained net return | growth of the chained account minus 1. **Context, not the endpoint** | +0.0697 |
| Sharpe over the chained horizon | mean/std of per-bar returns × √bars. **NOT annualised** | B better in 9 of 15 cells |
| max drawdown | peak-to-trough on the chained account | A 0.1017, B 0.0902 |
| losing folds | of 6 deployment folds, how many lost | A 3.00, B 2.73 |
| period concentration | share of all positive fold return coming from the single best fold | A 0.664, B 0.638 |
| engine fills / entries | an entry and its exit are TWO fills; entries counts positions opened | reported separately, never conflated |

**Decay** is the installed engine's own metric, not the lab's. `robust_decay` is
`candidate_selection_metric`'s default and `mean_decay` / `std_decay` are fields on every
`WalkForwardTrialRecord`. LAB-04 traced it rather than adopting it: under the public default
(`optimization_mode="none"`) the engine runs ONE trial and performs no search, so decay never
selects anything there.

---

## Group B — selection-quality metrics (LAB-04, specific to the robust selector)

These say whether a parameter choice is defensible, not whether it made money.

| metric | what it is | why it exists |
|---|---|---|
| **G** | the 0.25 quantile of a candidate's utility across inner episodes — its LOWER TAIL, not its average | a candidate carried by one lucky stretch fails here |
| **F** | median over episodes of the 0.75 quantile of regret against neighbours | a HIGH F means a lonely spike |
| **R** | `G − λ_F·F` | the robust score arm B maximises |
| **P_survive** | share of (candidate, episode) pairs clearing the quality and risk gates | registered threshold 0.60 |
| parameter turnover | schema distance between consecutive deployments | A 0.354, B 0.172 |
| distinct parameter sets | of 6 cutoffs, how many different points were deployed | A 6.00/6, B 3.40/6 |
| retention rate | how often the selector returned nothing admissible | A 0/90, B 45/90 |

**R is not comparable across probe radii.** F is regret against NEIGHBOURS, so a smaller radius puts
neighbours closer, shrinks F and inflates R mechanically. Only the selected point and G are
comparable across radii.

---

## Group C — regime-model metrics (LAB-05)

None of these is an economic metric and the phase says so before it shows one.

| metric | what it is | measured |
|---|---|---|
| fit objective | `Σ loss + λ_J × switches` | non-increasing on every start, checked |
| per-observation objective | the fit objective divided by block length, on held-out inner blocks | how K is chosen |
| **emitted switch count** | switches on the emitted tape — what a policy actually pays for | 220 across 40 namespaces |
| **switches on pure noise** | the same count on a world with zero true switches | **18** (the false-structure rate) |
| label agreement | best-permutation match to a simulator's latent label. **Diagnostic only** | 0.983 recurring, 0.990 break, **0.007 noise** |
| detection delay | observations between a true switch and the first emitted change, as a distribution | median 1.0 recurring, 0.0 break |
| second-best gap | distance from the emitted state to the runner-up | the ambiguity measure |
| fit residual / novelty score | distance to the nearest centroid, against the 0.99 training-residual quantile | 101 of 6571 flagged |
| quality status counts | OK / UNKNOWN_STATE / MISSING_DATA / STALE_MODEL | 6470 OK, 101 UNKNOWN_STATE, 0 stale |
| unmapped-state rate | refits producing a state that cannot be matched to the previous fit | **10 of 39** |

---

## Group D — binary correctness gates (most of the lab)

These have no scale. They hold exactly, or the phase is blocked.

| gate | what must hold | result |
|---|---|---|
| T37 | forward DP endpoint costs == exhaustive enumeration over all `K^T` paths | exact |
| T38 | streaming emissions == batch == every prefix, bit-identical | exact |
| T39 | model digest unchanged when the post-cutoff suffix is replaced | exact, AND a known-leaky fit is caught |
| T41 | a permuted refit maps cleanly; a genuinely moved state stays unmapped | both |
| T43 | the inference modules cannot reach a fit function at all | structural |
| LAB-02 | Python and Rust account traces bit-identical; numba kernels bit-exact | exact |
| LAB-04 | the fast evaluator gives identical fills, reasons and equity to a whole-window fixed point | exact |

---

## Group E — contrast and confirmation metrics (LAB-07, LAB-08, LAB-09)

The arms exist from LAB-08 on, so this is where a difference between two ways of running the
study becomes measurable. Every number here is a PAIRED daily difference on the days both arms
were live; none of them is a portfolio.

| metric | what it is | where it is measured |
|---|---|---|
| **paired daily difference** | THE registered primary endpoint, arm minus arm on the same dates. A day either arm was not live is excluded, never filled with a zero | LAB-08 `contrast_panel`, LAB-09 `lab09_uncertainty.json` |
| **block-bootstrap interval** | a 95% interval from resampling contiguous runs of DATES, one sequence per draw applied to every cell so the symbols move together | LAB-09 L09.3 |
| block length | chosen on development from the first autocorrelation lag inside ±2/√n, applied unchanged to the confirmation | `lab09_development_replay.json` |
| **concentration** | share of the total ABSOLUTE daily contribution carried by the biggest days, so two offsetting days count as two big days | LAB-09 L09.3 |
| episode counts | how many days each cell contributed, and how many were shared. A short cell gets an equal vote on less evidence | LAB-09 L09.3 |
| Holm-adjusted p | the sign-test or bootstrap p raised for the size of the registered family. **This is the number that counts**, not the nominal one | LAB-08, LAB-09 |
| cost-stress levels | the same deployment re-run at 1×, 1.5×, 2× the configured costs, plus AS_DECLARED | LAB-09 L09.4 |
| activation delay | bars a requested parameter version waited, split by WHAT it waited for | LAB-07, LAB-09 `switch_delays` |
| transition turnover | schema distance between consecutive deployed parameter sets — the selector's own metric | LAB-09 `transition_diagnostics` |
| parameter rank stability | how often the selector re-chose the same point at the next cutoff | LAB-09 `transition_diagnostics` |
| one-way fee rate implied | fees charged ÷ gross notional, read off the fills. **Measured 0.0002 against a registered 0.0004** | LAB-09 `accounting`, COR-13 |
| cash-identity residual | `equity[-1] − equity[0] − (−Σ side·qty·price − Σ fee)`. Not a performance number: a non-zero value means the fills, fees and equity are not the same account | LAB-09 L09.6.1 |

Two of these are NOT comparisons and are easy to misread as one: the one-way fee rate and the
cash-identity residual are **accounting checks**. A good residual says the books close, not that
the strategy made money.

---

## The rule that ties them together

A metric only means something next to the thing it is being compared against, and that comparison
has to be fixed before the number is seen:

- the **endpoint** is compared to a minimum effect registered before any arm ran;
- the **conclusion level** comes from a vocabulary registered before any result;
- the **switch count** on real data is read against the switch count on pure noise;
- a **detector** is only trusted after it has been shown to fire on a known-bad case.

Where those pairings are missing, the number is reported and no conclusion is drawn from it.
