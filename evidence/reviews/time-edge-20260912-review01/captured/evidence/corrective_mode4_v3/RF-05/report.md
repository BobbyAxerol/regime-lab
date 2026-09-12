# RF-05 — Frozen evaluation, falsification, claims and handoff

Generated from committed RF-05 artifacts by `scripts/write_rf05_report.py`. No engine was rerun for any number in this report. The study is corrected retrospective/prequential evidence: no interval is an untouched holdout and no positive result is recorded.

## 1. Objective and what is not tested

Test whether a causal regime-triggered refit schedule (`M4_REGIME`) changes the continuous account outcome against the calendar per_fold_causal WFO (`M4_CAL`) and the refit-count-matched `M4_CAL_MATCHED` control on the frozen RF-04 event cohort, compute the paired common-date statistics and cost-stress panel from the committed result paths, and close the study with evidence-bounded claims and a reproducibility handoff.

**Not tested:** any prospective/untouched interval, A-VWAP and A-HASH (route `BLOCKED_CAPABILITY`), the registered 32-64 trials/cutoff budget (the frozen RF-04 design executed 8), the 2023-01-01..2023-12-31 development extension, funding, and the NEIGH/E secondary arms. Coverage is 10 of 20 planned cells.

## 2. Identity, contracts and resolved runtime

- branch `mode4-corrective` at RF-01 head `f4ba4e1b151222aa9811b25efcacebf960bf33c9`; plan sha256 `bf983c2b63dd748d778a3d9c38360bfb6f081cb9b445d7a8044fbae63b2c7434`
- QuantBT: `{'quantbt-engine': '1.1.1', 'quantbt-native': '0.4.2'}`, import origin `/root/bobby/pool_alpha/lab_regime_model_quantbt/environments/lab_venv/lib/python3.12/site-packages/quantbt/__init__.py`; native module: ModuleNotFoundError: No module named 'quantbt_native'
- Mode 4 contract: mode `mode_4_is_only_robust`, schedule `per_fold_causal`, metric `is_only_robust`, backend `endpoint`, `oos_used_for_selection=False`, claim `strict_fold_local_retraining`
- RF-05 runs no engine at all: the claim statistics, CIs and cost-stress levels are deterministic functions of the committed RF-04 equity/fill paths (`recomputation.json`)
- frozen MDE: 0.0371 account bps/day (`evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json`, `FROZEN_BEFORE_RF04_RESULTS`); historical registered value 6.4e-05 preserved as history
- contamination: `NESTED_RETROSPECTIVE`; untouched holdout = `False`; prospective protocol `SPECIFIED_NOT_EXECUTED` at `evidence/corrective_mode4_v3/RF-05/prospective_protocol.json`
- frozen components: 33 across 9 groups; all present = `True`

## 3. Findings fixed and their acceptance tests

| finding | disposition | evidence / acceptance |
|---|---|---|
| A01 fee binding | FIXED_AND_VERIFIED | `test_a01_bound_fee_kwargs_translate_one_way_exactly_once`, `test_a01_the_bound_route_charges_the_registered_one_way_rate`; event accounts carry `fee_rate=0.0004` |
| A02-A08 execution/timing/ledger contracts | FIXED_AND_VERIFIED | `test_rf02_contracts.py`, `test_rf02_event_account.py`, `test_rf02_mode4_baseline.py`; all 10 event cells carry real per-fill ledgers |
| A09 old E path | QUARANTINED_UNSUPPORTED_PATH | `test_a09_the_old_e_arm_is_quarantined_not_wired_from_d`; E stays disabled |
| A10 namespace/ineligible triggers | FIXED_AND_VERIFIED | `test_rf03_controller.py` |
| A11 economic-context collapse | FIXED_AND_VERIFIED | `test_a11_opposite_economic_contexts_are_not_collapsed` |
| A12/A13 response/bank support | SECONDARY_REPAIRED_NOT_MARKET_EVALUATED | unit-level repairs only; `secondary_contrasts` mark SELECTOR/INTERACTION/POLICY_E NOT_EVALUABLE |
| A14 inner scaler / fixed-target ablation | REPAIRED_UNIT_ONLY | `test_rf04_model_repairs.py` |
| A15 MDE derivation | FIXED_AND_VERIFIED | `mde_corrected.json` frozen before RF-04 results; `test_a15_the_corrected_mde_derivation_is_registered_and_history_preserved` |
| A16 fail-closed claims | FIXED_AND_VERIFIED | `src/crypto_regime_lab/evidence/claim_gate.py`; RF-05 re-derives every status and refuses POSITIVE without CI > MDE and Holm < 0.05 |

RF-05-specific integrity findings: `PASS` with 8 checks over RF-01..RF-05 (strict JSON, coverage nulls, selection joins, freeze hashes, claim gate, CI denominators, report coverage, phase report pairs).

## 4. Budget, sample and coverage

- raw window: server_core_v1, development 2021-01-01..2023-12-31 (registered); executed development window 2021-01-01..2022-06-30 only
- coverage: 20 planned cells — 10 `RUN_VALID`, 10 `BLOCKED_CAPABILITY` (A-VWAP/A-HASH), 0 `NOT_RUN`; non-executed cells carry null metrics plus a reason
- trials: 8 per cutoff in both arms (registered 32-64); cutoffs per cell: M4_CAL 3, M4_REGIME 6; trial rows per cell/arm = 24/48
- family coverage: TIMING 10 evaluated cells; BUDGET_AWARE 1 of 2 registered cells (`PARTIAL_COVERAGE_1_OF_2_REGISTERED`); excluded: [{"cell": "A-SC/BTCUSDT", "reason": "the matched control exists only on the 'endpoint' route while the primary arm executes on the 'event' route; the routes differ, so the budget contrast is not on the same execution binding"}]
- decay panels from RF-04 remain diagnostics: D1 168 rows, D2 36 rows, D3 102 rows; RF-05 does not relabel them confirmation evidence

## 5. Technical vs market vs synthetic

- **Market (real snapshot):** all RF-04 account records behind the RF-05 statistics are real `server_core_v1` data on the executed development window; no synthetic curve enters any claim.
- **Technical:** the RF-05 freeze/recompute/integrity steps read committed artifacts only; the 20/20 recomputed total returns match the engine record exactly (mismatches: none).
- **Synthetic:** only the RF-04 G11 positive control (never used in a market metric).
- **No rerun:** 8 items are explicitly null with reasons (engine cost rebinding, matched control on the 8 scaled cells, A-VWAP/A-HASH, prospective interval, 32-64 budget, 2023 window, funding, NEIGH arms).

## 6. Metrics, canonical metrics, cost stress and decay

| metric | definition | unit | support / null rule |
|---|---|---|---|
| `mean_daily_diff_bps` | paired mean of daily account net returns left - right on common dates | account bps/day | null + `NO_COMMON_DAYS` / `IDENTICAL_ACCOUNT_SERIES` |
| `ci95` | paired moving-block bootstrap percentile interval, block 5 days (development-chosen), 2000 resamples, seed 20260911 | account bps/day | no engine rerun for any CI |
| `sharpe365_recomputed` | sqrt(365)*mean/std(daily net return, ddof=1) | ratio | null + `INSUFFICIENT_OBSERVATIONS`/`ZERO_VARIANCE` |
| `profit_factor_daily` | sum(positive daily returns)/abs(sum(negative daily returns)) | ratio | null + `NO_LOSS_DENOMINATOR`/`NO_TRADES` |

Registered family (Holm, m=2):

- `TIMING` (M4_REGIME - M4_CAL): mean -0.112319 bps/day, CI [-0.493975, +0.190658], n=759, raw p=0.5370, Holm p=0.8720 -> `INCONCLUSIVE`, mde_cleared=False
- `BUDGET_AWARE` (M4_REGIME - M4_CAL_MATCHED): mean +0.161999 bps/day, CI [-0.214218, +0.615415], n=759, raw p=0.4360, Holm p=0.8720 -> `INCONCLUSIVE`, mde_cleared=False

Per-cell TIMING results (10 cells, common dates only; cell-level reads are descriptive, the family result is the registered test):

| cell | route | mean bps/day | CI low | CI high | n | raw p | status | parm changes |
|---|---|---|---|---|---|---|---|---|
| A-SC/BTCUSDT | event | +0.067961 | -0.552415 | +0.616401 | 759 | 0.7780 | `INCONCLUSIVE` | 2 |
| A-SC/ETHUSDT | event | -0.155152 | -0.962780 | +0.701401 | 759 | 0.7450 | `INCONCLUSIVE` | 2 |
| A-SC/SOLUSDT | event | -2.517506 | -5.786555 | -0.058026 | 654 | 0.0380 | `NEGATIVE_WITHIN_SCOPE` | 2 |
| A-SC/BNBUSDT | event | +0.114441 | -0.258391 | +0.510329 | 759 | 0.5060 | `INCONCLUSIVE` | 2 |
| A-SC/DOGEUSDT | event | +0.308348 | -0.712610 | +1.410148 | 720 | 0.5380 | `INCONCLUSIVE` | 2 |
| A-HMA/BTCUSDT | event | +0.063301 | -0.379385 | +0.557921 | 759 | 0.7680 | `INCONCLUSIVE` | 3 |
| A-HMA/ETHUSDT | event | -0.369931 | -1.037550 | +0.169469 | 759 | 0.2100 | `INCONCLUSIVE` | 2 |
| A-HMA/SOLUSDT | event | +0.345829 | -0.256784 | +1.022144 | 654 | 0.2450 | `INCONCLUSIVE` | 2 |
| A-HMA/BNBUSDT | event | +0.182426 | -0.324455 | +0.565893 | 759 | 0.6270 | `INCONCLUSIVE` | 2 |
| A-HMA/DOGEUSDT | event | +0.582431 | -0.757316 | +2.071727 | 720 | 0.3840 | `INCONCLUSIVE` | 1 |

BUDGET_AWARE per-cell:

- A-SC/BTCUSDT: mean +0.346275 bps/day, CI [-0.711324, +1.442292], n=759, fidelity `DEVIATED` -> `NOT_EVALUABLE`
- A-HMA/BTCUSDT: mean +0.161999 bps/day, CI [-0.214218, +0.615415], n=759, fidelity `AS_SPECIFIED` -> `INCONCLUSIVE`

Cost stress on the frozen event cohort (ledger-linear, committed fill path held fixed; 1x reproduces the base equity exactly):

| level | mean bps/day | CI low | CI high | n |
|---|---|---|---|---|
| 1x | -0.112319 | -0.493975 | +0.190658 | 759 |
| 1.5x | -0.114088 | -0.496573 | +0.188202 | 759 |
| 2x | -0.115858 | -0.499173 | +0.185853 | 759 |

**D2 fixed-parameter age replay** (RF-04 diagnostic, unchanged): anchors 4/4 replayed, status `COMPLETE`. Negative cells at cell level: ['A-SC/SOLUSDT'].

## 7. Runtime breakdown

- RF-05 no-engine wall (attempts ledger SUCCESS durations): 18.157065 s
- RF-04 measured walls from `profiling_and_budget.json`: pilot 240.306s, matched control 164.743s, placebo 171.856s, D2 anchors 34.282123731449246s
- CPU seconds: None (NOT_MEASURED: the RF-04 runners recorded wall clock only; no committed artifact or log stores process CPU seconds, so a value would be invented)
- peak RSS: None (NOT_MEASURED: no RF-04 artifact or log records the peak resident set; report.json already carries peak_rss_bytes=null for the same reason)
- candidate-bar visits: None (NOT_MEASURED: the pilot/evaluator traces record folds, trials, studies and event-account runs, not candidate-bar visits; the count cannot be reconstructed from committed values)
- cold/warm and native route: resolved from RF-01/RF-02 records; RF-05 adds no engine work

## 8. Proof capability

- treatment reached execution on all 10 event cells: every cell has different selected parameters between arms (10/10 cells with changed fold parameters) and different account paths
- positive control (RF-04 G11, synthetic): parameters change and the treatment reaches engine fills; it never enters the market claims
- null/placebo (RF-04, 2 pilot cells): delayed-state contrasts are exploratory and do not produce a positive status
- fail-closed gate: the endpoint A-SC deviation and the identical-series cases are `NOT_EVALUABLE`; no cell or family is positive without CI > MDE and Holm < 0.05
- pipeline capability: corrected execution and Mode 4 selection are demonstrated; the bounded design cannot rule the MDE in or out (TIMING CI [-0.493975, +0.190658])

## 9. Potential assessment

`REPAIR_CAPABILITY_AND_GO_PROSPECTIVE` — treatment reached execution on all 10 cells (different selected parameters and different account paths), so the bottleneck is not a rename; but the bounded 8 trials/cutoff discovery, the capability-blocked A-VWAP/A-HASH cohort and the absence of any untouched interval bound what can be concluded

- keep the corrected event-route baseline frozen
- implement or formally quarantine A-VWAP/A-HASH capability so coverage can reach 20/20
- run the registered 32-64 trials/cutoff design only inside the prospective protocol
- execute the prospective protocol on post-2026-08-31 data before any deployment decision
- falsifiable next step: if a future untouched window still shows a TIMING CI inside [-MDE, +MDE], accept the scope-negative/inconclusive result and do not add model complexity
- RF-04 funnel context remains as recorded: potential `UNASSESSED` on the 2-cell pilot; bottleneck was information on A-HMA and rank identification on the A-SC endpoint route

## 10. Claim limitations

- 10 of 20 planned cells executed (A-SC, A-HMA); A-VWAP/A-HASH are BLOCKED_CAPABILITY
- executed development window 2021-01-01..2022-06-30; registered window extends to 2023-12-31
- bounded 8 trials/cutoff instead of the registered 32-64
- NESTED_RETROSPECTIVE: every interval was seen while repairing defects; no holdout claim
- the delayed-state and matched-minus-calendar contrasts are exploratory diagnostics
- the ledger cost stress holds the engine fill path fixed; a changed-cost engine rerun was not performed
- funding is MISSING_DECLARED and not modelled
- the moving-block length 5 days, 2000 resamples and seed 20260911 are development-chosen artifacts; the cost multipliers 1x/1.5x/2x and the MDE are frozen before results and are never re-selected after a result
- `simulation_complete` and `audit_complete` stay separate: the engines flushed in RF-04 and every RF-05 artifact is strict JSON with null+reason for missing values
- historical invalid intervals were never recomputed: all historical claim verdicts remain `NOT_EVALUABLE` in `RF-01/historical_invalidation.json`

## 11. Exit decision and remaining tasks

**RF-05: PARTIAL_TECHNICAL_CLOSURE.** The corrected retrospective study is technically valid within its scope (the 10 runnable event-route cells ran both primary arms through the installed QuantBT native-event account with oos_used_for_selection=False, the corrected one-way fee binding and real per-fill ledgers; the A-SC/BTCUSDT endpoint deviation is retained as NOT_EVALUABLE and excluded from the primary result; A-VWAP/A-HASH stay BLOCKED_CAPABILITY with null metrics). The economic answer is `INCONCLUSIVE`: neither family contrast clears the frozen MDE of 0.0371 bps/day and no POSITIVE status is reported. Remaining tasks: A-VWAP/A-HASH capability or formal quarantine, the registered 32-64 trials/cutoff design, and the prospective protocol (`SPECIFIED_NOT_EXECUTED`) on a genuinely untouched window before any deployment decision.

## 12. Rerun recipe, output hashes and handoff

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf05.py --force
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf05_report.py --force
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pyflakes $LAB/src $LAB/scripts $LAB/tests
```

Handoff: `handoff.md` and `reproducibility_manifest.json`. The registered prospective protocol is SPECIFIED_NOT_EXECUTED and must not be run in this study. No production merge and no publish.

