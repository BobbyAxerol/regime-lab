# FUP-02 — Expanded-budget, full-development-window paired discovery

Generated from committed FUP-02 artifacts by `scripts/write_fup02_report.py`. No engine was rerun for any number in this report. Contamination stays `NESTED_RETROSPECTIVE`; no holdout and no economic claim is made.

## 1. Objective and what is not tested

Expanded-budget, full-development-window paired discovery of M4_REGIME minus M4_CAL on every cell whose route is qualified (20 primary cells; FUP-01 qualified A-VWAP/A-HASH, A-SC/A-HMA already event-qualified) under the registered 32-64 trials/cutoff budget, with per-contrast validity and a coverage review before any final freeze.

**Not tested:** no paired bootstrap, decay panel, matched control or multiplicity correction is computed; statistical status is NOT_EVALUATED everywhere; no holdout and no prospective interval: contamination stays NESTED_RETROSPECTIVE; 2024+ data is never read and is not claimed as untouched; per-symbol regime tapes are not claimed (the committed BTCUSDT emission tape is reused, identical to RF-04.6)

## 2. Identity, contracts and resolved runtime

- study `corrective_mode4_v3` phase `FUP-02`; budget revision `REGISTERED_BEFORE_THE_FUP02_RUNS` registered at `2026-09-12T04:16:19.041762+00:00` (sha256 `736a4f143dab47f9...`)
- data: `server_core_v1/crypto_binance_futures_1m`, window 2021-01-01..2023-12-31, snapshot manifest sha256 `88c19513043e05bbd7d8901916b87fe01d10822678b020e6cd8d2fdec00300ff`
- Mode 4 contract: `mode_4_is_only_robust`, schedule `per_fold_causal`, metric `is_only_robust`, `oos_used_for_selection=false`
- routes: every cell runs the qualified event route (`evidence/corrective_mode4_v3/FUP-01/route_matrix.json` sha256 `375190802342f8a2...`); the route is read, never re-decided
- contamination: `NESTED_RETROSPECTIVE`, untouched holdout = `False`

## 3. Findings

- **FUP02-F1 — the frozen provider's engine_param_ranges cannot express bool parameter specs** (OPEN_REPRODUCED): experiments/dynamic_fold_provider.py:engine_param_ranges routes a bool spec to the numeric branch and raises TypeError on A-VWAP's exit_at_vwap / time_stop_on. Expected: a bool spec is expressed as the two-choice categorical list the installed engine samples with trial.suggest_categorical. not repaired in the frozen provider: RF-05 pins that file and the freeze guard permits only the one FUP-01 supersession; FUP-02 passes its own bool-aware schema expression to the provider as an argument (scripts/run_fup02.py:engine_param_ranges) and the provider file is never edited Proposal: `handoff/lab_only_patch.diff`.

## 4. Budget: period, trials, seeds, folds and validity

- registered trial budget REGISTERED_BEFORE_THE_FUP02_RUNS: 32 trials/cutoff (range [32, 64]), seed 20260911, train memory 180 days
- folds scored: 25 of 360 planned across 1 executed cells; engine runs 27
- trial ledger: 800 unique trial rows (550 finite objectives) in `evidence/corrective_mode4_v3/FUP-02/trial_ledger.jsonl`
- coverage review: `PARTIAL_COVERAGE_REVIEW`; admissible over scored = 1.0, trials = 800, nonfinite = 250, infeasible = 0

## 5. Technical results versus market results

- technical: 1 cell pairs completed, 1 paired contrasts VALID; every completed arm declares `oos_used_for_selection=False` and deploys through the real native-event account
- market: per-cell headline account numbers are in the table below; they are discovery outcomes, not a statistical result

| cell | coverage | contrast | M4_CAL equity | M4_REGIME equity | CAL trades | REG trades |
|---|---|---|---|---|---|---|
| A-SC/BTCUSDT | NOT_RUN | — | null | null | null | null |
| A-SC/ETHUSDT | NOT_RUN | — | null | null | null | null |
| A-SC/SOLUSDT | NOT_RUN | — | null | null | null | null |
| A-SC/BNBUSDT | NOT_RUN | — | null | null | null | null |
| A-SC/DOGEUSDT | NOT_RUN | — | null | null | null | null |
| A-HMA/BTCUSDT | RUN_VALID | VALID | 19106.523505432844 | 20688.769505556025 | 364 | 289 |
| A-HMA/ETHUSDT | NOT_RUN | — | null | null | null | null |
| A-HMA/SOLUSDT | NOT_RUN | — | null | null | null | null |
| A-HMA/BNBUSDT | NOT_RUN | — | null | null | null | null |
| A-HMA/DOGEUSDT | NOT_RUN | — | null | null | null | null |
| A-VWAP/BTCUSDT | NOT_RUN | — | null | null | null | null |
| A-VWAP/ETHUSDT | NOT_RUN | — | null | null | null | null |
| A-VWAP/SOLUSDT | NOT_RUN | — | null | null | null | null |
| A-VWAP/BNBUSDT | NOT_RUN | — | null | null | null | null |
| A-VWAP/DOGEUSDT | NOT_RUN | — | null | null | null | null |
| A-HASH/BTCUSDT | NOT_RUN | — | null | null | null | null |
| A-HASH/ETHUSDT | NOT_RUN | — | null | null | null | null |
| A-HASH/SOLUSDT | NOT_RUN | — | null | null | null | null |
| A-HASH/BNBUSDT | NOT_RUN | — | null | null | null | null |
| A-HASH/DOGEUSDT | NOT_RUN | — | null | null | null | null |

## 6. Metrics, units, support and null reasons

- account metrics come from `_event_account_payload` (the provider's own deployment builder) over the full development window: equity_last (USDT), total_return_pct, sharpe, num_trades, max_drawdown_pct, per-fill ledger
- a cell or arm that did not complete carries null metrics with its exact reason; nothing is zero-filled
- statistical status is `NOT_EVALUATED` for every contrast because FUP-02 computes no paired inference, decay panel or matched control

## 7. Runtime breakdown

- shard wall seconds (sum): 1275.774
- invocation wall seconds (sum): 935.811
- registered caps: per-shard 900s, per-cutoff 900s, per-invocation 5400s, total approved 43200s
- peak RSS: null (the runner did not sample RSS per shard; the registered pre-run micro-benchmarks recorded ~0.9-1.0 GiB peak per process, and no measurement is invented here)
- invocations: 2; each invocation records its own budget, elapsed seconds and stop reason in the full-window artifact

## 8. Proof capability

- technical validity: PASS for the completed VALID contrasts
- treatment reached execution: YES for completed cells: the two arms used different registered cutoff lists and both deployed their selected parameters through the native-event account
- positive/null control: NOT_TESTED_HERE (RF-04/positive_control.json is the committed positive control)
- coverage review: PARTIAL_COVERAGE_REVIEW

## 9. Potential assessment

- level `UNASSESSED`: no statistical evaluation is performed in FUP-02 and the coverage is partial; the per-cell outcomes exist but are neither a confirmatory test nor a frozen design, so no potential level is claimed
- falsifiable next step: complete the remaining folds under the same registered budget, run the registered coverage review, then freeze a design before any statistical claim

## 10. Claim limitations

- coverage is partial: 1 valid pairs, 0 cells budget stopped, 19 cells not started
- the regime cutoff list is the committed BTCUSDT tape, identical across symbols; per-symbol tapes are not claimed
- the provider's public payload does not expose selector/cluster/fallback fields; the coverage review reports candidate counts and finite-trial coverage only
- the A-SC route is the event fidelity route, not the originally registered endpoint route; the endpoint deviation is recorded in RF-04
- no statistical inference, no decay panel and no matched control are computed here

## 11. Exit decision and remaining tasks

- status: `TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE`; claim validity `TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE`, statistical status `NOT_EVALUATED`, scope 1 valid paired cells of 20 planned; 25 of 360 folds scored
- corpus/shard status counts: {"PENDING": 38, "COMPLETE": 2}
- remaining: resume the budget-stopped shards under the same registered budget; run the registered coverage review before any design freeze; FUP-03 stays blocked until post-freeze data exists

## 12. Rerun recipe, hashes and handoff

- rerun: `python scripts/run_fup02.py --run --resume --budget-seconds <seconds>`
- budget revision sha256 `736a4f143dab47f9753d560a8e56511d365bff1a8a32967fd14a168f7f9ecb7f`
- paired discovery sha256 `7bc16896eb1b29a42f56d4305cfae4fa8e894a31d209e95d57ff3c3709aaa998`
- cell coverage sha256 `1dc8bd9d0f436378ab08d582b86347dba1925e365130bb947381f80b4e3632cb`
- coverage review sha256 `74e489e712129478f62ce314a2ee1d8cb72f100d93fd072039a51db34c1b7008`
- handoff: resume FUP-02 shards until the registered wall budget is spent, then FUP-03 (blocked on post-freeze data)

## Glossary — what each term means and where it applies

| term | meaning | where it applies |
|---|---|---|
| **FUP-02** | the registered follow-up study that executes the 32-64 trials/cutoff full-window paired discovery | `followup_studies_registration.json#/studies/1` |
| **shard** | one `alpha x symbol x arm` unit, checkpointed per fold/cutoff | `scripts/run_fup02.py`, guide 8.1 T3 |
| **cutoff** | the decision moment that closes the training view and opens the operational test segment | `dynamic_fold_provider.py` |
| **admissible cutoff** | a scored cutoff where the selector returned parameters and at least one trial objective is finite | `coverage_review.json` |
| **BUDGET_STOPPED** | a shard/fold stopped cleanly by the registered wall cap, with the exact reason and no fabricated metric | `budget_revision.json` stop vocabulary |
| **NOT_RUN_BUDGET** | a shard the invocation budget never reached | `cell_coverage.json` |
| **NESTED_RETROSPECTIVE** | historical data already exposed to design work; not a holdout | `budget_revision.json#/contamination` |
| **coverage review** | the pre-freeze check of admissible candidates and bad-trial fractions, registered before the runs | `budget_revision.json#/coverage_review_rule` |

