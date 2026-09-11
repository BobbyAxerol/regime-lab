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

**Descriptive contribution.** The guide 8.3 group ablation, re-measured on a window inside the interval (the LAST confirmation-role cutoff's training window, which lies entirely inside the confirmation interval. The fitter's own ablation uses the FIRST cutoff's window, which for this role is development data): a block beyond price and volatility improved out-of-fold variance resolved on **0 of 5** symbols. no block beyond price and volatility improves out-of-fold variance resolved on any symbol inside the confirmation interval, which reproduces the development finding

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
| COR-13 | the lab passed the registered ONE-WAY taker fee into the engine's `fee` parameter, which the installed quantbt documents as a LEGACY ROUND-TRIP fee and halves into the canonical one-way rate. Every account since LAB-04 was charged 0.0002 one-way where the study registered 0.0004. The engine default for `fee` is also 0.0004, so the call looked correct and raised nothing | the ABSOLUTE net-return level of every account in LAB-04, LAB-06, LAB-07 and LAB-08. Measured on the development window at the registered fee, the registered contrasts move by at most 5% and none crosses the minimum economic effect, so no CONCLUSION is invalidated -- that is a measurement (configs/lab09_development_replay.json as_declared_economics), not a reassurance | `test_the_fee_binding_defect_is_reported_not_absorbed` |
| COR-14 | the confirmation role's group ablation was computed where LAB-05 computes it -- on the FIRST cutoff's training window -- which for that role is the 365 days BEFORE the interval starts, i.e. development data. It could not support a descriptive claim about the confirmation interval | nothing published: it was caught before the descriptive contribution was written. The claim now reads configs/lab09_group_ablation.json, measured on the LAST cutoff's window | `test_the_descriptive_claim_rests_on_an_in_interval_window` |
| COR-15 | the phase auditors marked a clause DONE when a STRING naming its evidence was present, so a pointer at a renamed field or a deleted test was indistinguishable from a real one | no number. It weakened every clause audit, which is why the LAB-09 auditor RESOLVES each pointer in the artifact, in pytest's collection, or in the source before it counts it | `test_the_audit_resolves_its_evidence_pointers` |
| COR-19 | the MISSING_ENRICHMENT stress dropped a random 20% of emissions independently. Removing scattered rows almost never moves where the FIRST transition of a period falls, so the corrupted tape produced a refresh schedule identical to the real one on all six cutoffs -- the stress would have re-run arm D for an hour and could not have produced a different answer | nothing published: caught by smoke-testing the stress before the run rather than after. The stress now drops CONTIGUOUS outages, which is also what an enrichment product actually does; six week-long outages drop 4.3% of the tape and move one of the six cutoffs | `test_missing_enrichment_drops_contiguous_stretches_not_scattered_rows` |

All 19 corrections across every phase are traceable: `guide 13.7: when validity fails, fix it in the lab, version it and INVALIDATE the affected results -- do not carry on taking headlines. Prose in a report does n`

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

## Audit and acceptance coverage

- clause audit: **7/65 DONE**, from a checklist written before the code (`configs/lab09_checklist.json`)
- every evidence pointer is RESOLVED, not merely present: every pointer is walked in the artifact, collected by pytest, or found in the source. A clause whose pointer names a field that does not exist is UNRESOLVED_EVIDENCE, not DONE -- earlier phases counted the presence of the string
- clauses without resolved evidence: `['L09.1.3', 'L09.1.4', 'L09.1.5', 'L09.1.6', 'L09.2.1', 'L09.2.2', 'L09.2.3', 'L09.2.4', 'L09.2.5', 'L09.2.6', 'L09.2.7', 'L09.3.1', 'L09.3.2', 'L09.3.3', 'L09.3.4', 'L09.3.5', 'L09.3.6', 'L09.3.7', 'L09.3.8', 'L09.4.1', 'L09.4.2', 'L09.4.3', 'L09.4.4', 'L09.4.5', 'L09.4.6', 'L09.5.1', 'L09.5.2', 'L09.5.3', 'L09.5.4', 'L09.5.5', 'L09.5.6', 'L09.5.7', 'L09.6.1', 'L09.6.2', 'L09.6.3', 'L09.6.4', 'L09.6.5', 'L09.6.6', 'L09.7.1', 'L09.7.2', 'L09.7.3', 'L09.7.4', 'L09.7.5', 'L09.7.6', 'L09.7.7', 'G11.2.4', 'G11.4.1', 'G11.4.2', 'G11.4.3', 'T62.1', 'T63.1', 'OUT.2', 'OUT.3', 'OUT.4', 'OUT.5', 'EXIT.1', 'EXIT.2', 'EXIT.3']`
- acceptance tests: 38 passed, 31 skipped in 1.66s
- acceptance requirements: `{"COVERED": 62, "PARTIAL": 1, "NOT_YET_IMPLEMENTED": 1}`

