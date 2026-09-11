# LAB-09 — Frozen confirmation, robustness and falsification

Generated from committed artifacts by `scripts/write_lab09_report.py`. Nothing is re-estimated here.

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **frozen confirmation** | running a protocol that was fixed in advance on an interval the design was not built on, with nothing adjustable left | LAB-09 — the LAB-08 protocol, unchanged, on 2024-01-01→2026-08-31 |
| **nested retrospective** | an interval that no phase of THIS lab consumed but that still cannot support an out-of-sample claim, because something it depends on was tuned over the whole sample | L09.1 — the supplied presets were TPE-tuned on the full sample with an unknown cutoff, so no interval of this dataset is an untouched holdout |
| **prospective protocol** | a specification for an observation that would begin AFTER the protocol was frozen, so no tuning could have seen it. Written, deliberately not executed | L09.1 — configs/lab09_confirmation_spec.json prospective_protocol |
| **paired daily difference** | two arms compared day by day on the days BOTH were live, rather than by their mean returns | L09.3 — the registered primary endpoint; days where either arm was absent are excluded, never filled with a zero |
| **block bootstrap** | resampling contiguous RUNS of days instead of single days, so the autocorrelation and the volatility clustering in the series survive the resample | L09.3 — moving blocks whose length is chosen on development and applied unchanged |
| **common shock** | a market-wide move that hits every symbol on the same day. Resampling symbols independently destroys it and shrinks the interval for free | L09.3 / T63 — one date sequence is drawn per bootstrap draw and applied to every cell |
| **concentration** | the share of a result carried by its few largest days, measured on the ABSOLUTE daily contribution so that two offsetting days still count as two large days | L09.3 / guide 11.4 — a result carried by a handful of days is a statement about those days |
| **Holm step-down** | a multiple-comparison adjustment applied to a family of contrasts named before the results, which raises each p-value by how many comparisons were made | L09.3 — over the five registered contrasts; E-B is excluded as an extension |
| **exploratory contrast** | a comparison reported outside the registered family and labelled as such, so it cannot quietly borrow the family's error control | L09.3.7 — E-B, which is arm D's schedule under another name wherever the policy never switched |
| **cost stress** | re-running the same deployment with transaction costs multiplied, to see how much of a result survives a worse fill than the one assumed | L09.4 — the registered 1x / 1.5x / 2x grid, applied to the account and not to the selection |
| **one-way fee** | the fee charged on a single trade side. A round-trip fee is two of them | L09.6 — the study registered a one-way rate of 0.0004 and the engine was handed it in a parameter documented as round-trip, so it charged half |
| **AS_DECLARED** | the cost level that reproduces the account the study registered, as opposed to the account it actually ran | L09.4 — fee x2 and slippage x1, because only the fee binding was wrong |
| **stale feed** | a provider that stops updating and then catches up in one step. The catch-up looks like a transition to any arm that acts on one | L09.4.4 — six one-week freezes injected into the state tape |
| **missing enrichment** | observations the provider never delivered, DROPPED rather than filled with a value | L09.4.5 — a fabricated zero would tell the arm something false instead of nothing |
| **mislabelled transition** | a state change dated at the wrong time while the sequence of states is untouched, which isolates timing error from labelling error | L09.4.3 — half the transitions moved by one day in either direction |
| **label permutation** | shuffling the arbitrary integer ids of the states within a fit. A schedule built from WHERE the state changes must be unaffected | L09.5.3 — the control that must change nothing; a difference would mean a decision reads the integer |
| **novelty threshold** | the fit residual beyond which a model declares it has not seen this before, fitted on each training window | L09.5.1 — UNKNOWN_STATE emissions on the confirmation interval |
| **cash identity** | equity change equals minus the signed cash paid out minus the fees; it closes only if the fills, the fees and the equity describe the same account | L09.6.1 — checked on every arm of every cell |
| **parameter-version lifecycle** | every parameter version an account requested, which of them took effect, and how many bars each one traded | L09.6.2 — a version requested and never deployed is the warm-up or flat-book gate working |
| **search cardinality** | how many unique strategy evaluations a cutoff actually spent against the registered ceiling | L09.6.3 — a probe landing on an already-evaluated point is not re-evaluated |
| **replay** | re-running a committed decision with today's code and comparing the result to what was recorded | L09.6.5 — the development accounts and the 1.0x level of the confirmation cost panel |
| **second-best gap** | how far the emitted state is from the runner-up. A small gap means the emission was nearly a coin flip | LAB-05 — the ambiguity measure, reported instead of a fake confidence |
| **conclusion level** | a label from a vocabulary registered BEFORE any result, so a finding cannot be described with a word invented to fit it | LAB-04 — INCONCLUSIVE_SAMPLE / DESCRIPTIVE_VALUE / NET_PARAMETER_SELECTION_EDGE / FAILED_VALIDITY and three others |
| **minimum economic effect** | the smallest daily net-return difference the lab agreed in advance to call meaningful; anything smaller sits inside the cost-stress band | LAB-04 — 6.4e-05/day (0.64 bps/day), derived from cost uncertainty × turnover |
| **sign reversal** | the pooled result points one way while a subgroup points the other; averaging it away would be a false claim | LAB-04 — the pooled winner is B, but A-VWAP reverses |
| **declared post-hoc** | a diagnostic decided AFTER seeing results, marked as such so it can never be mistaken for a pre-registered test and can never change a conclusion | LAB-04 — the gate-bindingness grid |
| **NOT_READY** | an alpha that cannot be certified keeps all its cells with NULL metrics; booking it as PnL = 0 would bias every aggregate | LAB-02/04 — A-HASH, 5 cells |
| **data role** | the declared purpose of a date window: `development` permits fitting and design choices, `outer_evaluation` permits only a frozen-protocol run | development 2020-01-01→2023-12-31; LAB-04/05/06 stay inside it |


## What this phase claims and does not claim

LAB-08 closed with **NO_PROMISING_DESIGN**. That does not suspend this phase: a negative finding has to be confirmed exactly as a positive one would be, and the guide's exit asks for an honest conclusion with a scope rather than for an edge. A **frozen confirmation** is the LAB-08 protocol, unchanged, run on an interval the design was not built on.

What it cannot claim is out-of-sample. The interval is **nested retrospective**: no phase of this lab consumed it, and the supplied presets were still tuned over the whole sample with an unknown cutoff. Both facts are stated because only the first one is about this lab.

## L09.1 — the interval, and what it is not

Unlocked **2026-09-11T03:45:26.023039+00:00**, after the protocol was frozen (2026-09-10T14:50:28.446136+00:00) and before any confirmation run started. The file is never re-issued: re-unlocking would let the protocol be revised once a result was visible.

- interval **2024-01-01 → 2026-09-09**, all five symbols
- consumed by an earlier phase: **False**
- holdout status: **NESTED_RETROSPECTIVE**
- **prospective protocol**: SPECIFIED_NOT_EXECUTED — guide L09.1: the lab specifies a prospective protocol and does not execute it live. Nothing here starts a live process, and the lab has no market execution path

| artifact checked | declared window | inside development |
|---|---|---|
| `lab05_regime_model_registry.json` | development | True |
| `lab07_continuous_trace.json` | 2021-01-01 → 2023-12-31 | True |
| `lab08_pilot_protocol.json` | discovery | True |
| `lab08_factorial_full.json` | cells run on the development window | True |

## L09.2 — the frozen protocol, run

Window **2024-01-01 → 2026-08-31**. 15 of 20 cells ran; 5 carry null metrics. Wall time 0s.

- the calendar moved by exactly one field: `['first_cutoff']` (dataclasses.replace on one field; every other field is carried)
- seeds carried from the frozen protocol: `{"probe_design": 20260910, "model_multi_start": [11, 23, 37, 51], "placebo": 20260911}`
- no module changed while the run was in flight: **True** (9 modules hashed before the first cell and after the last)
- the unlocked interval reaches 2026-09-09 in the 1-minute product; the account stops at the end of the 4h feature panel because the panel is the state provider's input. Trading 9 further days would leave the dynamic arms without a tape while the calendar arms kept refreshing

| alpha | symbol | A | B | C | D | E |
|---|---|---|---|---|---|---|
| A-HASH | BTCUSDT | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ |
| A-HASH | ETHUSDT | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ |
| A-HASH | SOLUSDT | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ |
| A-HASH | BNBUSDT | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ |
| A-HASH | DOGEUSDT | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ | _NOT_READY_ |
| A-HMA | BTCUSDT | -0.09% | +0.10% | -1.08% | -3.78% | -3.78% |
| A-HMA | ETHUSDT | +1.49% | -0.14% | -0.11% | -0.11% | -0.11% |
| A-HMA | SOLUSDT | +3.70% | -1.88% | -1.75% | +0.43% | +0.43% |
| A-HMA | BNBUSDT | -2.03% | -5.23% | -2.51% | -9.09% | -9.09% |
| A-HMA | DOGEUSDT | +6.73% | +6.44% | -2.75% | -1.99% | -1.99% |
| A-SC | BTCUSDT | +8.70% | +5.58% | +2.91% | +5.58% | +5.58% |
| A-SC | ETHUSDT | +2.91% | +6.72% | +6.28% | +7.99% | +7.99% |
| A-SC | SOLUSDT | -0.79% | -4.36% | +6.40% | +5.81% | +5.81% |
| A-SC | BNBUSDT | +10.62% | +6.23% | +5.63% | +4.14% | +4.14% |
| A-SC | DOGEUSDT | +7.17% | +20.63% | +2.06% | +19.39% | +19.39% |
| A-VWAP | BTCUSDT | -2.22% | -2.93% | -3.75% | -1.52% | -1.52% |
| A-VWAP | ETHUSDT | -0.58% | -0.46% | +0.72% | -0.46% | -0.46% |
| A-VWAP | SOLUSDT | -6.29% | -3.36% | -9.77% | -0.91% | -0.91% |
| A-VWAP | BNBUSDT | -1.49% | -1.32% | +2.97% | +4.23% | +4.23% |
| A-VWAP | DOGEUSDT | +2.00% | +0.00% | +3.23% | -1.86% | -1.86% |

## L09.3 — the registered endpoint, with an interval around it

The **registered primary endpoint** is the mean **paired daily difference** in net return between two arms on the same dates, registered 2026-09-09T18:48:15.264005+00:00. The **minimum economic effect** is `6.40e-05` per day (0.64 bps), fixed 2026-09-09T20:11:32.125140+00:00 before any arm was compared.

The interval is a **block bootstrap** with blocks of **2 days**, chosen on development (`configs/lab09_development_replay.json, chosen on development`) and applied here unchanged. 4000 draws. moving blocks of DATES, one sequence per draw applied to every cell. Symbols therefore move together and the common shocks survive (T63)

| id | contrast | question | mean daily | 95% CI | p | Holm p | clears minimum |
|---|---|---|---|---|---|---|---|
| H1 | `B-A` | does independent-neighborhood selection beat the installed selector on the same calendar? | -3.215e-06 | [-2.756e-05, +2.296e-05] | 0.806 | 1.000 | **False** |
| H2 | `C-A` | does regime-triggered refresh timing beat the frozen calendar with the same selector? | -1.417e-05 | [-4.068e-05, +1.145e-05] | 0.284 | 1.000 | **False** |
| H3 | `D-B` | does regime timing add anything on top of the new selector? | +1.064e-06 | [-1.823e-05, +1.972e-05] | 0.899 | 1.000 | **False** |
| H4 | `D-C` | does the new selector add anything on top of regime timing? | +1.201e-05 | [-1.522e-05, +4.038e-05] | 0.384 | 1.000 | **False** |
| H5 | `(D-C)-(B-A)` | is there a selector x timing interaction? | +1.523e-05 | [-1.354e-05, +4.359e-05] | 0.281 | 1.000 | **False** |
| — | `E-B` | extension: does arm E beat arm B? | +1.064e-06 | [-1.823e-05, +1.972e-05] | 0.899 | — | **False** |

Holm step-down over the registered family `['B-A', 'C-A', 'D-B', 'D-C', '(D-C)-(B-A)']`. E-B is an EXTENSION contrast (guide 10.1), registered separately from the primary family. Including it would enlarge the family and weaken every adjusted p-value in it, which is a decision that has to be made before the results, not after

### Episode counts and concentration

| contrast | union days | days all cells live | min cell | max cell | top-5-day share of absolute | days for half the move |
|---|---|---|---|---|---|---|
| `B-A` | 973 | 973 | 973 | 973 | 4.0% | 177 |
| `C-A` | 973 | 973 | 973 | 973 | 4.0% | 177 |
| `D-B` | 973 | 973 | 973 | 973 | 3.2% | 178 |
| `D-C` | 973 | 973 | 973 | 973 | 4.7% | 163 |
| `(D-C)-(B-A)` | 973 | 973 | 973 | 973 | 4.0% | 190 |

### Block-length sensitivity

For `['A-HMA/BNBUSDT', 'A-HMA/BTCUSDT', 'A-HMA/DOGEUSDT', 'A-HMA/ETHUSDT', 'A-HMA/SOLUSDT', 'A-SC/BNBUSDT', 'A-SC/BTCUSDT', 'A-SC/DOGEUSDT', 'A-SC/ETHUSDT', 'A-SC/SOLUSDT', 'A-VWAP/BNBUSDT', 'A-VWAP/BTCUSDT', 'A-VWAP/DOGEUSDT', 'A-VWAP/ETHUSDT', 'A-VWAP/SOLUSDT']` pooled cells on the first registered contrast:

| block length (days) | mean daily | 95% CI | p | CI excludes zero |
|---|---|---|---|---|
| 1 | -3.215e-06 | [-2.713e-05, +2.323e-05] | 0.814 | False |
| 5 | -3.215e-06 | [-2.689e-05, +2.297e-05] | 0.800 | False |
| 10 | -3.215e-06 | [-2.968e-05, +2.354e-05] | 0.826 | False |
| 20 | -3.215e-06 | [-3.060e-05, +2.645e-05] | 0.772 | False |
| 40 | -3.215e-06 | [-3.473e-05, +2.827e-05] | 0.796 | False |

## L09.4 — cost and information stress

Multipliers `[1.0, 1.5, 2.0]` were registered in `configs/minimum_economic_effect.json` on 2026-09-09T20:11:32.125140+00:00. The **1x** level is a control on the harness itself: it must reproduce the confirmation run's equity exactly, and it does for every arm: **True**.

**AS_DECLARED** is not a stress. the account the study registered at LAB-01: a one-way taker fee of 0.0004 and 1 bp of slippage per side. It is reached at fee x2 because the lab passes the registered ONE-WAY rate into an engine parameter documented as ROUND-TRIP, so the engine halves it (measured in configs/cost_binding_verification.json)

| level | fee ×| slip ×| A | B | C | D | E |
|---|---|---|---|---|---|---|---|
| `1x` | 1.0 | 1.0 | +1.99% | +1.73% | +0.56% | +1.86% | +1.86% |
| `1.5x` | 1.5 | 1.5 | +1.76% | +1.30% | +0.40% | +1.63% | +1.63% |
| `2x` | 2.0 | 2.0 | +1.53% | +0.86% | +0.24% | +1.40% | +1.40% |
| `AS_DECLARED` | 2.0 | 1.0 | +1.68% | +1.15% | +0.35% | +1.55% | +1.55% |

_a selector that re-scored its candidates at 2x costs might have chosen differently, usually towards lower turnover. This panel therefore bounds the damage to a FIXED schedule, not to an adaptive one_

### Information stress — 3 of 15 cells

the first 3 RUN cells in protocol order, chosen before any stress result was read. Settings registered before the stress ran: `{"mislabel_fraction": 0.5, "mislabel_shift_observations": 6, "stale_stretches": 6, "stale_observations_each": 42, "missing_outages": 6, "missing_observations_per_outage": 42, "registered_before_the_stress_ran": true}`.

| cell | stress | arm D | stressed | difference | cutoffs moved |
|---|---|---|---|---|---|
| A-HMA/BTCUSDT | MISLABELLED_TRANSITIONS | -3.78% | -2.09% | +1.69% | 3/6 |
| A-HMA/BTCUSDT | STALE_FEED | -3.78% | -3.28% | +0.50% | 1/6 |
| A-HMA/BTCUSDT | MISSING_ENRICHMENT | -3.78% | -3.78% | +0.00% | 1/6 |
| A-HMA/BTCUSDT | LABEL_PERMUTATION _(control)_ | — | — | schedule identical: **True** | 0/6 |
| A-HMA/ETHUSDT | MISLABELLED_TRANSITIONS | -0.11% | -0.11% | +0.00% | 4/6 |
| A-HMA/ETHUSDT | STALE_FEED | -0.11% | -0.11% | +0.00% | 1/6 |
| A-HMA/ETHUSDT | MISSING_ENRICHMENT | -0.11% | +1.47% | +1.57% | 1/6 |
| A-HMA/ETHUSDT | LABEL_PERMUTATION _(control)_ | — | — | schedule identical: **True** | 0/6 |
| A-HMA/SOLUSDT | MISLABELLED_TRANSITIONS | +0.43% | +0.43% | +0.00% | 0/6 |
| A-HMA/SOLUSDT | STALE_FEED | +0.43% | +0.43% | +0.00% | 1/6 |
| A-HMA/SOLUSDT | MISSING_ENRICHMENT | +0.43% | -0.49% | -0.92% | 1/6 |
| A-HMA/SOLUSDT | LABEL_PERMUTATION _(control)_ | — | — | schedule identical: **True** | 0/6 |

## L09.5 — support and novelty

| situation | exercised | measured |
|---|---|---|
| new regime episode | **True** | 0 of 5 symbols carry more novel states than development |
| mixed / ambiguous states | **True** | 5 of 5 symbols more ambiguous than development, by each symbol's own development **second-best gap** decile |
| **label permutation** after refit | **CHECKED** | schedule identical on 3 of 3 cells |
| stale candidate bank | **True** | last bank cutoff 2026-06-19 00:00:00+00:00, 73.0 days old at the interval end |
| no challenger qualifies | **True** | 5728 of 5839 decisions |
| campaign not flat at a switch | **True** | MEASURED: 75/75 arms had a delayed switch. 105 switches waited for an OPEN CAMPAIGN and 306 for warm indicators; bars waited per reason `{"TRANSITION_BLOCKED_OPEN_CAMPAIGN": 387458, "WAITING_FOR_WARM_INDICATORS": 46859}` |

**Time-edge attribution.** C-A isolates WHEN the parameters were refreshed, holding the selector fixed. B-A isolates WHICH parameters, holding the calendar fixed. A time-edge claim needs C-A, not the sum Pooled over the cells: timing `C-A` = -1.417e-05, selection `B-A` = -3.215e-06, interaction = +1.523e-05.

**Descriptive contribution.** The guide 8.3 group ablation, re-measured on a window inside the interval (the LAST confirmation-role cutoff's training window, which lies entirely inside the confirmation interval. The fitter's own ablation uses the FIRST cutoff's window, which for this role is development data): a block beyond price and volatility improved out-of-fold variance resolved on **0 of 5** symbols. no block beyond price and volatility improves out-of-fold variance resolved on any symbol inside the confirmation interval, which reproduces the development finding

## Was anything chosen after the interval was opened?

Every registration the confirmation deploys carries a stamp that **precedes the unlock** (2026-09-11T03:45:26): **True**. One stamped after it would be a choice made with the interval in view.

| registration | fixed at | precedes the unlock |
|---|---|---|
| `configs/lab08_pilot_protocol.json` | 2026-09-10T14:50:28 | **True** |
| `configs/minimum_economic_effect.json` | 2026-09-09T20:11:32 | **True** |
| `configs/hypothesis_registry.json` | 2026-09-09T18:48:15 | **True** |
| `configs/study_registration.json` | 2026-09-09T18:48:15 | **True** |
| `configs/compute_budget_registration.json` | 2026-09-10T11:29:13 | **True** |

**Seeds, read back from what the run stamped** rather than copied from the freeze: 180 selector cutoffs were each handed the registered base `20260910` (seeds that are not the base: `[]`), and 175 regime refits each used `[11, 23, 37, 51]`. All measured sources match: **True**.

**Engine, re-hashed** rather than declared untouched: `{'quantbt-engine': '1.1.1', 'quantbt-native': '0.4.2'}`, and both wheels LAB-01 pinned still match their SHA-256 (`True`), as does the lockfile (`True`). Untouched: **True**.

**The prospective protocol is not executed because the lab cannot execute**, not because it chose not to: `{"live_execution_allowed": false, "market_experiments_allowed": false, "production_mutations_allowed": false}`.

**Costs between the two phases**: the confirmation charged a one-way fee of `[0.0002]` on every arm, the same rate the discovery charged (`True`). the rate both phases charged is HALF the registered one-way fee (COR-13). 'Untouched' here means the economics did not move BETWEEN the two phases, which is what keeps the confirmation comparable to the discovery it confirms. It does not mean the rate is the registered one

## L09.6 — reconciliation, and one accounting defect

| check | result |
|---|---|
| **cash identity** `equity[-1] - equity[0] == -sum(side * qty * price) - sum(fee)` | 75/75 arms hold, worst residual 1.66e-09 |
| **parameter-version lifecycle** | every bar attributed: **True**; 450 requested, 316 deployed, 134 gated |
| **search cardinality** | 180 cutoffs, every execution recorded: **True**, unique executions [83, 106] against a ceiling of 96 |
| **objective recomputation** `R = G - lambda_F * F, with lambda_F = 1.0 as registered` | 7670 scores, all match: **True** (max difference 0.00e+00) |
| **replay** | development: 75/75 exact; confirmation 1x: 75/75 |
| **audits retained** | all present: **True**, fast profile used: False |

### The fee binding — a measured accounting defect

The study registered a **one-way fee** of `0.0004` (Binance USD-M standard taker rate; re-pin against actual contract data in LAB-03). Measured from real fills, the account was charged `0.0002` — **0.5×** the registered rate.

quantbt endpoint docs: `fee` is a LEGACY ROUND-TRIP fee, converted to the canonical one-way `fee_rate` at the endpoint boundary when explicit `fee_rate` is omitted (v2_fee_rate = fee / 2.0). The correct binding is `fee_rate=<one-way rate>, or fee=2 * <one-way rate>`.

**Why it was not caught earlier.** the engine's default for `fee` is 0.0004, which is also the registered one-way rate, so the call looked correct and produced no warning. LAB-01 recorded the SIGNATURE in api_binding_map.json and never probed the SEMANTIC -- the exact failure the guide's 'never assume a signature' rule names

**Direction.** flattering: every account in every phase paid less than the study declared, so absolute returns are overstated

Development contrasts recomputed at the registered fee (deployment only — the selections cannot be corrected without re-running the search):

| contrast | at the fee that ran | at the registered fee |
|---|---|---|
| `B-A` | +4.586e-05 | +4.389e-05 |
| `C-A` | +3.770e-05 | +3.827e-05 |
| `D-B` | -1.252e-05 | -1.010e-05 |
| `D-C` | -4.362e-06 | -4.476e-06 |
| `(D-C)-(B-A)` | -5.022e-05 | -4.837e-05 |

_selection. Every candidate in LAB-04 and LAB-08 was scored under the halved fee, and rescoring them means re-running the search. This pass therefore bounds the damage to a FIXED schedule_

## L09.7 — the claim

a study that adds them up can call a risk-timing effect a parameter-selection edge and never notice (guide 11.1)

| contribution | question | verdict | evidence |
|---|---|---|---|
| **DESCRIPTIVE** | do the states describe anything beyond price and volatility? | **NOT_SUPPORTED** | `configs/lab09_group_ablation.json` |
| **PREDICTIVE** | do the states predict which parameter set will do better? | **NOT_SUPPORTED** | `configs/lab09_policy_decision_ledger.json` |
| **SELECTION** | does the neighbourhood selector beat the installed one on the same calendar? | **RULED_OUT** — -3.215e-06, CI [-2.756e-05, +2.296e-05] | `—` |
| **TIMING** | does regime-triggered refresh beat the frozen calendar with the same selector? | **RULED_OUT** — -1.417e-05, CI [-4.068e-05, +1.145e-05] | `—` |
| **POLICY** | does the bank and response policy add anything beyond D? | **NULL_BY_CONSTRUCTION** | `configs/lab09_confirmation_results.json arms.E` |

### Conclusion level: **FAILED_VALIDITY**

Drawn from the registered vocabulary in `configs/hypothesis_registry.json`: `DESCRIPTIVE_VALUE, CONDITIONAL_RESPONSE_EVIDENCE, NET_PARAMETER_SELECTION_EDGE, NET_TIMING_EDGE, NET_POLICY_EDGE, NO_INCREMENTAL_VALUE, INCONCLUSIVE_SAMPLE, FAILED_VALIDITY`.

Blockers that prevented a stronger conclusion:

- ACCOUNTING: the lab charged half the registered one-way taker fee in every phase, because the registered ONE-WAY rate was passed into an engine parameter documented as ROUND-TRIP. Measured, not inferred (configs/cost_binding_verification.json)
- MATRIX: 5 of 20 cells are NOT_READY with null metrics, so the matrix is incomplete
- CONTAMINATION: the confirmation interval is NESTED RETROSPECTIVE. The supplied presets were tuned on the full sample with an unknown cutoff, so no interval of this dataset is an untouched holdout

**Development outcome being confirmed:** `NO_PROMISING_DESIGN`. Confirmed: **True**.

**no claim of a proven fund-grade alpha is made or implied. This is a lab backtest on one cohort with no funding product, a nested retrospective interval, and an accounting defect disclosed above (L09.7.7)**

**Scope.** everything above is about three alphas on five Binance USD-M perpetual symbols between 2024-01-01 and 2026-08-31, on a no-funding cohort, with parameters selected under an understated fee. It is not about crypto, about regime models in general, or about any other market

## Falsification commitments exercised

| commitment | exercised in this phase |
|---|---|
| a negative or inconclusive result is a valid outcome and is published, not rerun until it wins | the confirmation reproduces NO_PROMISING_DESIGN and is published as it came out |
| risk-only improvement is never recorded as a parameter-selection edge | RISK_ONLY is reported BLOCKED_BY_STATE_NAMESPACING with its measurement, never as a scale of 1.0 |
| zero switches because no challenger qualified is a valid technical pass | the policy's decision counts on the confirmation interval are reported as a result |
| an alpha that cannot be certified is reported NOT_READY with null metrics, never PnL=0 | A-HASH contributes five NOT_READY cells with null metrics |

## Corrections made during LAB-09

| id | what was wrong | what it invalidated | guarded by |
|---|---|---|---|
| COR-13 | the lab passed the registered ONE-WAY taker fee into the engine's `fee` parameter, which the installed quantbt documents as a LEGACY ROUND-TRIP fee and halves into the canonical one-way rate. Every account since LAB-04 was charged 0.0002 one-way where the study registered 0.0004. The engine default for `fee` is also 0.0004, so the call looked correct and raised nothing | SUPERSEDED READING. This entry first said 'no CONCLUSION is invalidated', on the strength of the deployment-side measurement alone: at the registered fee the development contrasts move by at most 19% in relative terms and none crosses the minimum economic effect. That half still holds. The other half was never measured when the claim was made, and it now is: scripts/probe_fee_sensitivity.py re-selected A-SC/BTCUSDT at the registered fee and ONE of twelve arm-selections CHANGED -- arm A at cutoff 2021-06-30 chose AP=41/threshold=50 instead of AP=36/threshold=55. The selector is fee-sensitive, so the defect is a DESIGN defect and not only an accounting one: the candidate bank LAB-04 built, and every arm LAB-08 and LAB-09 compared, were chosen under a cost the study did not register. By the severity rule fixed BEFORE the probe ran, that is MAJOR, and guide L09's exit makes a major accounting error FAILED_VALIDITY: the affected runs are invalidated, a protocol revision is required before a retest, and the headline is not kept | `test_the_fee_binding_defect_is_reported_not_absorbed` |
| COR-14 | the confirmation role's group ablation was computed where LAB-05 computes it -- on the FIRST cutoff's training window -- which for that role is the 365 days BEFORE the interval starts, i.e. development data. It could not support a descriptive claim about the confirmation interval | nothing published: it was caught before the descriptive contribution was written. The claim now reads configs/lab09_group_ablation.json, measured on the LAST cutoff's window | `test_the_descriptive_claim_rests_on_an_in_interval_window` |
| COR-15 | the phase auditors marked a clause DONE when a STRING naming its evidence was present, so a pointer at a renamed field or a deleted test was indistinguishable from a real one | no number. It weakened every clause audit, which is why the LAB-09 auditor RESOLVES each pointer in the artifact, in pytest's collection, or in the source before it counts it | `test_the_audit_resolves_its_evidence_pointers` |
| COR-19 | the MISSING_ENRICHMENT stress dropped a random 20% of emissions independently. Removing scattered rows almost never moves where the FIRST transition of a period falls, so the corrupted tape produced a refresh schedule identical to the real one on all six cutoffs -- the stress would have re-run arm D for an hour and could not have produced a different answer | nothing published: caught by smoke-testing the stress before the run rather than after. The stress now drops CONTIGUOUS outages, which is also what an enrichment product actually does; six week-long outages drop 4.3% of the tape and move one of the six cutoffs | `test_missing_enrichment_drops_contiguous_stretches_not_scattered_rows` |
| COR-21 | not a defect in a result: two REVISIONS to a registered contract. The OS resource budget registered one worker and a CPU limit of 2. The confirmation was measured at 24 min per cell -- twelve selector cutoffs at 97 strategy evaluations each -- and the remaining twelve cells would have taken close to five hours on one core while three sat idle. The user asked for it to be faster, twice: workers 1 -> 2 with the CPU limit untouched, then 2 -> 3 with the limit raised to 3 | the COMPARABILITY of the confirmation's wall seconds against LAB-08's, which were measured at one worker. No measured RESULT is affected: cells are independent, deterministic and checkpointed, so a shard decides only which process computes a cell. A shard is a CELL boundary and never an arm boundary -- all five arms of a cell still run sequentially in one process on one core -- so no arm can finish ahead of another, which is the thing guide L08.6 forbids buying with CPU. Peak memory is 0.40 GiB per worker against a 4 GiB budget, and the lab processes are niced so the user's live collectors preempt them | `test_a_budget_revision_is_appended_and_never_restamped` |
| COR-22 | the guard written for COR-21 asserted the wrong invariant. It required `cpu_limit` to be identical across a budget revision, as a proxy for 'the conditions a baseline was measured under must not change'. The proxy fails in both directions: it blocks a recorded and justified revision, and it permits any unrecorded change that does not happen to touch that one number | nothing measured. What it weakened is the guard itself. Guide L08.6 forbids raising CPU SO THAT one policy finishes ahead of the baseline, so the invariant is about ARMS: a revision must now state that per-arm compute is unchanged, say HOW the arms stay equal, and justify any change to the CPU limit separately | `test_a_budget_revision_is_appended_and_never_restamped` |

All 23 corrections across every phase are traceable: `guide 13.7: when validity fails, fix it in the lab, version it and INVALIDATE the affected results -- do not carry on taking headlines. Prose in a report does n`

## Limitations

| id | limitation | consequence | measured in |
|---|---|---|---|
| LIM-01 | one of the four alphas contributes no cell | the matrix is 15 of 20. Every aggregate is over three alphas, and A-HASH's blocker is unresolved rather than negative | `configs/lab09_confirmation_results.json` |
| LIM-02 | the parameters were selected under an understated fee | the AS_DECLARED panel corrects the DEPLOYMENT accounting. It cannot correct the SELECTION: every candidate was scored under the halved fee, and rescoring them is a full re-run of the search | `configs/cost_binding_verification.json, configs/lab09_stress.json cost_stress.as_declared` |
| LIM-03 | no funding product exists in this storage | this is a labelled no-funding cohort. A realistic net-carry claim is not available, and the gap is never booked as zero | `configs/study_registration.json execution.fee_funding_slippage_config` |
| LIM-04 | the interval is nested retrospective | no out-of-sample claim is available from this dataset at any interval. A prospective protocol is specified and deliberately not executed | `configs/lab09_confirmation_spec.json` |
| LIM-05 | the state vocabulary is not decision-eligible across refits | the RISK_ONLY control cannot be computed: a per-state risk scale fitted on one window has almost no state key in common with a later one. The control is reported BLOCKED with its measurement rather than as a scale of 1.0 that would look like a result | `configs/lab09_confirmation_results.json cells[].controls.RISK_ONLY` |
| LIM-06 | arm E has no independent contribution here | the response policy deploys arm D's schedule, so E-B IS D-B. It is reported as an extension and excluded from the primary family | `configs/lab09_uncertainty.json exploratory` |
| LIM-07 | the states do not resolve out-of-fold variance beyond price and volatility | guide 8.3's requirement is not met on the confirmation interval either. The registered core is not changed in response, because selecting a feature set on this result would be choosing the model on an outcome | `configs/lab09_group_ablation.json` |
| LIM-08 | the pooled statistic averages per-cell means over unequal day counts | a cell with few days gets an equal vote on less evidence. The counts are reported so the reader can see it rather than infer it | `configs/lab09_uncertainty.json contrasts[].episodes` |
| LIM-09 | the information stress is staged, not exhaustive | the tape corruptions were run on a subset chosen in protocol order before any stress result was read. A cell outside the subset is UNCHECKED, not clear | `configs/lab09_stress.json information_stress.staging_rule` |
| LIM-10 | the account stops before the data does | the last days of the 1-minute product are not traded, because the 4h feature panel that feeds the state provider ends earlier | `configs/lab09_confirmation_results.json window_note` |
| LIM-11 | three years of development and under three of confirmation is a small sample for a daily endpoint | the intervals are wide relative to the minimum economic effect, which is why an inconclusive reading is the honest one rather than a negative one | `configs/lab09_uncertainty.json` |
| LIM-14 | some auxiliary jobs ran concurrently with the registered one-worker budget | the frozen confirmation run itself was executed single-process, so its wall time is a clean operational measurement. Audits and re-runs executed alongside earlier work were contended, and their wall times are NOT reported as performance figures. One such overlap exhausted memory and killed a run, which cost time and no evidence: the run is checkpointed per cell | `configs/compute_budget_registration.json os_resource_budget` |
| LIM-13 | protective orders resolve on the decision bar, not on 1-minute bars as the protocol declares | absolute levels for A-HMA and A-VWAP carry a fill-fidelity effect of unknown sign. Contrasts do not: the resolution is identical across arms. A-SC rests no protection and is unaffected either way | `configs/protective_order_fidelity.json` |
| LIM-12 | the policy layer was measured on one cell | LAB-06's policy runs on A-SC/BTCUSDT. Its decision counts describe that cell and are not a statement about the other fourteen | `configs/lab09_policy_decision_ledger.json` |

## Leakage and contamination

| id | finding | severity | measured |
|---|---|---|---|
| LEAK-01 | the confirmation interval was not used to adjust the design | **CLEAR** | `{"any_phase_read_the_outer_window": false, "phases_checked": 4}` |
| CONTAM-01 | the supplied presets were tuned on the full sample | **MATERIAL** | `{"holdout_status": "NESTED_RETROSPECTIVE"}` |
| ACCT-01 | the account was charged half the registered one-way taker fee | **MAJOR** | `{"measured_over_registered": 0.5}` |
| DATA-01 | the pinned loader disagrees with the bytes on volume | **MATERIAL** | `{"partitions_compared": 15, "partitions_that_disagree": 10, "worst_volume_loss_share": 0.005145980653956174, "bars_a_cast_would_zero": 192}` |
| DATA-02 | closed metrics partitions drifted upstream | **CLEAR** | `{"status": "EXTERNAL_VINTAGE_RESTAMP_ONLY", "files_checked": 627, "closed_partition_drift": 23, "content_revisions": 0, "vintage_restamps": 23, "cohort_runs_invalidated": 0}` |
| LEAK-02 | the LAB-07 leakage audit | **CLEAR** | `{"checks": 12, "passed": 12}` |
| LEAK-03 | causality of the state tape | **CLEAR** | `{"verdict": "CAUSAL"}` |
| LEAK-04 | the confirmation model's first training window reaches into development | **BY_DESIGN** | `{"first_cutoff": "2024-01-01", "training_memory_days": 365}` |
| EXEC-01 | the protocol declares 1-minute execution bars and the account resolves protection on the decision bar | **MATERIAL** | `{"declared": "1m", "actual": "the decision bar", "alphas_exposed": ["A-HMA", "A-VWAP"], "alphas_not_exposed": ["A-SC"]}` |
| LEAK-05 | the confirmation selector's first training window reaches into development | **BY_DESIGN** | `{"first_calendar_cutoff": "2024-01-01", "training_memory_days": 180}` |
| SCOPE-01 | the fitter's own group ablation for the confirmation role is not in-interval | **MATERIAL** | `{"fitter_window": "the FIRST cutoff's training window, which for this role is 2023-01-01..2024-01-01 -- development data"}` |

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
- data role **outer_evaluation**, window **2024-01-01 → 2026-08-31**
- **15 of 20** cells ran; 5 are NOT_READY with null metrics and stay in the denominator
- the state provider for this interval was fitted by LAB-05's own fitter with the registered K, lambda, seeds, training memory and refit cadence, parameterised by role rather than reimplemented
- the first model of the interval trains on the 365 days before it, which are development data. That is what a deployment does on its first day and is backward-looking; it is recorded as LEAK-04, BY_DESIGN
- the account stops at the end of the 4h feature panel, which is the state provider's input, rather than at the end of the 1-minute product

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

- clause audit: **65/65 DONE**, from a checklist written before the code (`configs/lab09_checklist.json`)
- every evidence pointer is RESOLVED, not merely present: every pointer is walked in the artifact, collected by pytest, or found in the source. A clause whose pointer names a field that does not exist is UNRESOLVED_EVIDENCE, not DONE -- earlier phases counted the presence of the string
- acceptance tests: 72 passed in 3.17s
- acceptance requirements: `{"COVERED": 63, "NOT_YET_IMPLEMENTED": 1}`

