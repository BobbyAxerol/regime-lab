# Guide compliance inspection — LAB-01 through LAB-06

Generated from committed artifacts by `scripts/write_guide_compliance_report.py`.

## What this inspection asked

The per-phase audits ask *did every L0N.M task get done*. They all pass. This asks a different question: **does the guide require anything that no L0N.M task owns?** A requirement with no owning task is one every phase audit can pass while it stays undone — and all three gaps below are exactly that shape.

## Phase task audits — unchanged, still passing

| phase | rows audited | granularity | status |
|---|---|---|---|
| LAB-01 | 6 | one row per L0N.M task | DONE |
| LAB-02 | 8 | one row per L0N.M task | DONE, DONE_WITH_RECORDED_BLOCKER |
| LAB-03 | 7 | one row per L0N.M task | DONE |
| LAB-04 | 64 | one row per guide clause | DONE |
| LAB-05 | 53 | one row per guide clause | DONE |
| LAB-06 | 79 | one row per guide clause | DONE |

Acceptance requirements (guide §14): **56 COVERED, 3 PARTIAL, 5 NOT_YET_IMPLEMENTED** of 64.

| id | status | owning phase | title |
|---|---|---|---|
| T53 | PARTIAL | LAB-08 | A/B/C/D fixed economics and budgets |
| T54 | PARTIAL | LAB-08 | Current WFO uses OOS for selection |
| T58 | NOT_YET_IMPLEMENTED | LAB-08 | Risk-only/matched-cadence controls |
| T59 | PARTIAL | LAB-08 | Negative/failed/pruned trials retained |
| T60 | NOT_YET_IMPLEMENTED | LAB-08 | Objective recompute from components |
| T62 | NOT_YET_IMPLEMENTED | LAB-09 | Untested heatmap cells, hindsight labels |
| T63 | NOT_YET_IMPLEMENTED | LAB-09 | Full 5-symbol paired bootstrap |
| T64 | NOT_YET_IMPLEMENTED | LAB-10 | Offline reproduce report/run and sources |

Every one of them is owned by **LAB-08, LAB-09, LAB-10** — no requirement belonging to a completed phase is outstanding.

## Gap 1 — the compute-budget contract was never registered (guide §10.5, L01.5)

L01.5 lists *compute budgets* among the things preregistration fixes, and §10.5 says what that means: two parallel reports, plus an experiment-search ledger that counts every search decision — *"Không chỉ log Optuna alpha trials."*

What existed was `study_registration.json → resource_budget`: **1 worker, 2 CPU, 4 GiB**. That is the OS budget. It says nothing about whether two arms got the same number of chances to find a good parameter set, which is the thing a comparison can actually be gamed on. Neither `MATCHED_TOTAL_COMPUTE` nor `OPERATIONAL_POLICY` appeared anywhere in the lab.

**Why it had to be closed before LAB-07, not during LAB-08.** LAB-07 builds the refit scheduler. Once its cost is visible, the definition of *matched compute* could be chosen — honestly, even — to suit what that cost turned out to be. Registered now, no arm beyond A and B exists to favour.

`configs/compute_budget_registration.json`, status **REGISTERED_BEFORE_LAB07**, opens the ledger with what the completed phases already spent:

| phase | search kind | measured |
|---|---|---|
| LAB-04 | candidate_evaluation | `{"unique_executions": 9155, "candidate_episode_visits": 54930, "wall_seconds": 10788.0}` |
| LAB-05 | model_fit | `{"fits": 40, "starts_per_fit": 4, "observation_interval": "4h"}` |
| LAB-05 | state_count_choice | `{"candidates_considered": [2, 3], "registered_starting_k": 3, "k_used": 3, "chart_inspection_used": false}` |
| LAB-05 | jump_penalty | `{"value_used": 1.0}` |
| LAB-06 | response_hyperparameters | `{"response_estimates": 51944}` |
| LAB-06 | switching_threshold | `{"decisions_assessed": 6566}` |
| LAB-07 | operational_latency | `{"refit_jobs": 40, "measured_seconds_per_fit": 0.38945352006703615, "latency_source": "measured_benchmark", "min_refit_d` |
| LAB-07 | switching_policy_parameter | `{"resolved_to": "derived from each adapter's own warmup_bars()", "values_used": {"act-fold1": {"required_warm_bars": 39,` |

Counted as search: optimizer trials on alpha parameters, state-count (K) choices, jump penalties, response bandwidth and shrinkage, switching thresholds, alpha revisions.

## Gap 2 — the CLI's stage status had gone stale (guide §13.5)

`cli.py` froze an `IMPLEMENTED` set at LAB-01. When LAB-02 and LAB-03 landed, `certify-alphas` and `snapshot-data` went on answering:

```json
{"status": "NOT_IMPLEMENTED_YET", "required_phase": "LAB-02",
 "note": "the CLI refuses a stage whose phase has not landed"}
```

The refusal was honest in spirit — it never faked a pass — but its **reason had become false**, and a stale reason reads like a checked fact. Availability is now READ from `configs/lab0N_task_audit.json`, and a refusal distinguishes `PHASE_NOT_LANDED` from `RUNNER_NOT_WIRED_YET`.

| stage | delivering phase | state |
|---|---|---|
| `preflight` | LAB-01 | runs |
| `verify-source-integrity` | LAB-01 | runs |
| `certify-alphas` | LAB-02 | runs |
| `snapshot-data` | LAB-03 | runs |
| `verify-causality` | LAB-03 (data) + LAB-05 (model) | runs |
| `run` | LAB-08 (discovery) / LAB-09 (confirmation) | PHASE_NOT_LANDED |
| `freeze` | LAB-08 | PHASE_NOT_LANDED |
| `report` | LAB-10 | PHASE_NOT_LANDED |

Two consequences fell out of wiring it:

- **`verify-causality` had no runner at all.** LAB-03's exit gate says the future-mutation test passes through loader, resampler and scaler; LAB-05 adds the model and the streaming filter. Each layer was tested separately and nothing ran them as one gate. `scripts/verify_causality.py` now does.

| layer | verdict |
|---|---|
| resampler | CAUSAL |
| scaler | CAUSAL |
| model | CAUSAL |
| online_filter | CAUSAL |

Leaky control detected: **True** — a causality suite that can never fail proves nothing, so the deliberately leaky fit is run alongside and must be caught.

- **`snapshot-data` would have silently re-pinned the study.** Delegating the stage to `scripts/snapshot_data.py` meant a CLI call could re-read the source while the collector appends, write a NEW manifest, and re-register the read-lock every past result declares. It now refuses unless `--repin` is passed.

## Gap 3 — the identity taxonomy was 7 of 12 (guide §13.1)

§13.1 opens with *"Không gộp trial/candidate/execution/selection/activation thành một ID"*. The reason is joins: in LAB-08/09 a result must trace back through the selection that proposed it, the execution that measured it, the design that framed it and the observation that conditioned it. A join invented after the numbers exist is a place the numbers can be steered.

**8 present, 3 derivable, 1 owed** of 12.

| identity | names | owner | status |
|---|---|---|---|
| `study_id` | the research protocol | LAB-01 | **PRESENT** |
| `experiment_id` | arm + cell + cohort + config version | LAB-08 | **OWED** |
| `trial_id` | one optimizer proposal instance | LAB-04 | **PRESENT** |
| `candidate_id` | strategy version + typed effective params | LAB-04 | **PRESENT** |
| `execution_id` | candidate + market + initial state + economics + seed | LAB-04 | **DERIVABLE** |
| `probe_design_id` | a local validation design, independent of the sampler | LAB-04 | **DERIVABLE** |
| `model_id` | a fit artifact: features, scaler, centroids, state namespace | LAB-05 | **PRESENT** |
| `observation_id` | one decision-vintage regime emission | LAB-05 | **DERIVABLE** |
| `response_id` | a conditional estimate plus its supporting episodes | LAB-06 | **PRESENT** |
| `selection_id` | an evidence-based keep/switch proposal | LAB-06 | **PRESENT** |
| `activation_id` | the params actually in force at a timestamp/phase | LAB-07 | **PRESENT** |
| `attempt_id` | one run or retry of an operation | LAB-01 | **PRESENT** |

Three that COMPLETED phases owed were missing: `probe_design_id` (L04.3 freezes a design), `execution_id` (L04.3 counted 9,155 unique executions without naming one) and `observation_id` (L05 emitted 1,099 observations without naming one). They are **derived** from records that already exist rather than back-filled into artifacts, so nothing is re-run and no measurement moves:

| identity | derived from a real record |
|---|---|
| `probe_design_id` | `pd-6d72da79b988ed47` |
| `execution_id` | `ex-8b422e952c4af67e` |
| `observation_id` | `ob-6714b7083b2e9de7` |

Still owed: `experiment_id` — both minted by phases that have not run, now declared so LAB-07/08 inherit the contract instead of inventing one.

> The first run of `scripts/audit_identities.py` reported **12/12 present**. It was grepping the artifact it had just written. The scan now excludes its own output, and `test_the_identity_audit_does_not_pass_on_its_own_output` fails if a future version reports everything present.

## What was checked and found correct

Verified directly against the guide text rather than against the audits:

- L01.2 — ZIP guards cover traversal, symlink, duplicate, absolute AND oversize (`MAX_MEMBER_BYTES`, `MAX_TOTAL_BYTES`, `MAX_COMPRESSION_RATIO`, with a `COMPRESSION_BOMB` rejection)
- L01.3 — python/numba/llvmlite versions, thread counts, cache dirs, wheel digests and `quantbt.__file__` all pinned; shared parent venv recorded as untouched
- L01.4 — every evidence JSON carries `lab_run_id`; 135 append-only attempt ledgers
- L02.7 — **13 of 13** execution fixtures pass, including both-stop-and-TP-same-bar, OCO, over-close, rejected order, insufficient margin, funding boundary and terminal open position; forced-flat and mark-open are two declared modes
- L02.8 — Python/Rust parity on fixed intents PASSES, with the fill trace recorded as `BLOCKED_CAPABILITY` rather than claimed
- L03.3 — funding is a declared MISSING stream with an explicit no-zero policy, never an implicit zero
- L04.1 — all five installed WFO modes traced, with per-mode OOS usage and the `mode_5_full_robust` collapse-to-one-fold finding recorded
- L05.3 — multi-start seed selection is on the **lowest TRAIN objective**, `outer_information_used: false`
- L05.4 / §8.3 — M1S (sparse JM) is declared **deliberately unbuilt** with the guide's own reason: §8.3 forbids writing a naive sparse objective without a pinned research implementation, and the core is 3 blocks, not the 'many' §8.1 scopes M1S to
- L05.7 — detection delay and noise sensitivity both measured; the latent label is diagnostic only
- L06.1–L06.6 — purge and dependence correction, retired params serving open campaigns, indicator readiness by version/cutoff, supporting episodes per recommendation, train-only distance weights, coalesce/out-of-order fit handling, and no reset-flat expert curve as deploy equity

## Conclusion

All six completed phases do what their L0N.M tasks require. The three gaps were cross-phase contracts — §10.5, §13.5, §13.1 — that no single task owned. All three are now closed, each with a test that fails if it reopens.

**No result from LAB-04, LAB-05 or LAB-06 changed.** Nothing here touched a measurement; the fixes are a registration, a status-reporting correction and three identity derivations.

