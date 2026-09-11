# RF-01 — Freeze, invalidation, contracts and failing tests

Generated from committed RF-01 artifacts by `scripts/write_rf01_report.py`. No model and no market was run in this phase. **proof status: TECHNICAL_ONLY** — this is not evidence of an edge or of its absence.

## 1. Objective, and what is not tested

Stop the invalid interpretation of the historical results, register the corrected Mode 4 protocol, and turn each audit finding into a regression before any repair. **Not tested here:** whether regime timing has an edge. RF-01 runs no market experiment by design (merged plan RF-01 exit).

## 2. Identity and resolved runtime

- branch `mode4-corrective`, head `fd2d4f0dc5a6667cad763d80bc45e59cd0daf7e5`; working tree entries 3
- plan sha256 `bf983c2b63dd748d778a3d9c38360bfb6f081cb9b445d7a8044fbae63b2c7434`; audit archive `2765bd069a5caf16921c3df03dfafd8f090f4fdd2de5e1550a5ce390c87a980f` (present in lab: False)
- recovered audit bundle: 20 members, 1462711 bytes, `RESTORED_VERIFIED`, restored code executed: False
- python `3.12.13` at `/root/bobby/pool_alpha/lab_regime_model_quantbt/environments/lab_venv/bin/python`
- quantbt-engine `1.1.1`, quantbt-native `0.4.2`, import origin `/root/bobby/pool_alpha/lab_regime_model_quantbt/environments/lab_venv/lib/python3.12/site-packages/quantbt/__init__.py`
- candidate copy `quantbt_candidate`: endpoint sha256 `45ede55d0d66dd3a30089584b92199a455acca83e8f0418df3305874c28929a6`, matches the audited VFY01 hash: **True**
- preflight gate **PASS**, counts {'PASS': 9}
- protected-path write probes refused: **True**

## 3. Findings, disposition and failing-before evidence

16 P0/P1 findings from the merged audit are mapped in `historical_invalidation.json`; the old claim verdicts are superseded without editing any historical artifact.

| id | disposition | planned phase | required tests |
|---|---|---|---|
| A01 | `OPEN_REPRODUCED` | RF-02 | T01, T59 |
| A02 | `OPEN_REPRODUCED` | RF-02 | T03, T04, T05 |
| A03 | `OPEN_REPRODUCED` | RF-02 | T11, T12 |
| A04 | `OPEN_REPRODUCED` | RF-02 | T09, T10, T13, T14, T17, T18 |
| A05 | `OPEN_REPRODUCED` | RF-02 | T15, T16 |
| A06 | `OPEN_REPRODUCED` | RF-02 | T06, T07, T08 |
| A07 | `OPEN_REPRODUCED` | RF-02 | T51, T52 |
| A08 | `OPEN_REPRODUCED` | RF-02 | T25, T26, T40 |
| A09 | `QUARANTINED_UNSUPPORTED_PATH` | RF-03 | T37, T38 |
| A10 | `OPEN_REPRODUCED` | RF-03 | T29, T30, T31 |
| A11 | `OPEN_REPRODUCED` | RF-03 | T41, T42 |
| A12 | `OPEN_REPRODUCED` | RF-03 | T45, T46, T48, T49 |
| A13 | `OPEN_REPRODUCED` | RF-03 | T47 |
| A14 | `OPEN_REPRODUCED` | RF-03 | T43, T44, T50 |
| A15 | `OPEN_REPRODUCED` | RF-01 | T59 |
| A16 | `FIXED_PENDING_TEST` | RF-01 | T60, T61, T62 |

### Claim supersession

| contribution | historical verdict | repaired status | caused by |
|---|---|---|---|
| SELECTION | `RULED_OUT` | `NOT_EVALUABLE` | A01, A03, A04, A07, A08, A15 |
| TIMING | `RULED_OUT` | `NOT_EVALUABLE` | A01, A02, A03, A04, A06, A08, A10, A14, A15 |
| DESCRIPTIVE | `NOT_SUPPORTED` | `NOT_EVALUABLE` | A05, A14 |
| PREDICTIVE | `NOT_SUPPORTED` | `NOT_EVALUABLE` | A11, A12, A14 |
| POLICY | `NULL_BY_CONSTRUCTION` | `NOT_IMPLEMENTED_AS_SPECIFIED` | A09, A10, A11, A12, A13 |

### Failing-before regression tests

The RF-01 test set (`tests/mode4_corrective`) records **6 failing / 3 passing**. Failures:

- `test_a02_a_future_selected_version_is_not_active_before_its_requested_bar`
- `test_a03_a_non_converged_candidate_is_not_financially_evaluated`
- `test_a04_a_corrective_followup_exit_must_reach_the_position`
- `test_a05_a_hma_search_choices_do_not_collapse_into_one_stop_mode`
- `test_a07_episode_money_deltas_telescope_to_the_whole_account_delta`
- `test_a10_a_namespace_change_or_ineligible_emission_does_not_trigger_a_refit`

Passing artifact guards: `test_a09_the_old_e_arm_is_quarantined_not_wired_from_d`, `test_a15_the_corrected_mde_derivation_is_registered_and_history_preserved`, `test_a16_a_blocked_pipeline_may_only_report_not_evaluable`.

Full suite at this commit: **6 failed, 789 passed, 1 warning in 151.82s (0:02:31)** — the six failures are the before-repairs evidence, not a regression in existing behaviour.

## 4. Probes and budget

All **12 restored audit probes (P01, P02, P03, P04, P05, P06, P07, P08, P09, P10, P11, P12) reproduce on the current source** under the lab venv (python 3.12.13). Results: `evidence/corrective_mode4_v3/probe_reproduction_v1/`. They are synthetic/reference probes, not market replay.

| probe | finding | acceptance | observed on current source |
|---|---|---|---|
| P01 | A01 | T01, T59 | actual fee rate 0.0002 against the registered one-way 0.0004 |
| P02 | A02 | T03, T04 | a version requested at bar 100 is active from bar 0 |
| P03 | A10 | T29, T30 | namespace change plus decision_eligible=false still triggers a refit |
| P04 | A11 | T41, T42 | opposite centroids collapse to zero context distance |
| P05 | A05 | T15, T16 | all three searched HMA stop choices map to effective mode 1 |
| P06 | A03 | T11, T12 | converged=False with unmapped intents still returns EVALUATED |
| P07 | A03 | T11 | different exit price/qty at the same bar still marks converged |
| P08 | A07 | T51, T52 | a 1000 loss at a block boundary is reported as zero by both blocks |
| P09 | A15 | T59 | the registered 0.64 bps/day omitted the 0.1 allocation factor |
| P10 | A14 | T44 | adding a noise dimension to the target halves variance resolved |
| P11 | A04 | T18 | a generated corrective EXIT follow-up is never applied |
| P12 | A02 | T04 | the schedule uses the cutoff and ignores fit_ready_at |

RF-01 ran no candidates, trials or market bars. The registered discovery budget (32–64 trials/cutoff) is frozen after an RF-02 dry-run coverage review; it is not spent here.

## 5. Technical vs market vs synthetic

- Market experiments: **none**.
- Synthetic/reference probes: 12, all reproduced (section 4).
- Environment and binding checks: VFY **11/11** present on the candidate copy.

## 6. Metrics and decay

No economic metric is measured in RF-01. The historical metrics are retained as raw evidence and are now labelled `NOT_EVALUABLE` for inference. The corrected MDE derivation is registered in `corrective_study_spec.json` and remains `PENDING_RF02_ACTUAL_ENGINE_UNITS`; it is frozen before RF-04 and never tuned against observed results.

## 7. Runtime profile

RF-01 wall work is bounded: before-repairs tests only (returncode 1), plus the static binding scan and preflight. No T2/T3/T4 job ran. OS resource budget starts at {'workers': 1, 'cpu_limit': 2, 'working_memory_gib': 4}.

## 8. Proof capability

- The pipeline cannot yet detect or reject a time edge: treated as `NOT_TESTED`.
- Positive control and treatment-reached-execution are `NOT_TESTED` until RF-02 qualifies a route.
- What RF-01 *does* prove: every known P0/P1 finding has a mapped disposition, a reproduction, and a failing test or a registered guard; the false claims are quarantined.

## 9. Potential assessment

`UNASSESSED` (merged plan 10.4): the pipeline is not yet valid, so an opportunity/information judgement would be premature. Falsifiable next step: RF-02 route qualification and golden fee/timing fixtures.

## 10. Claim limitations

- historical study: execution validity `FAIL`, implementation fidelity `DEVIATED`, statistical status `NOT_EVALUABLE`
- the corrective study is registered on already-consumed history: `NESTED_RETROSPECTIVE`, no untouched holdout; a prospective protocol is specified and not executed
- A-HASH remains blocked; the matrix cannot be described as all four alphas until RF-02
- funding is absent; no realistic net-carry claim

## 11. Exit decision and remaining tasks

**RF-01 exit: TECHNICAL_ONLY.** Exact scope, imports, units and claim gates are known; every P0 is mapped; false claims are quarantined; probes are small and reproducible. Remaining: RF-02 (actual Mode 4 execution, fee/timing golden fixtures, route matrix).

## 12. Rerun recipe and handoff

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01.py
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01_regressions.py --full
$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf01_report.py
```

- handoff: **RF-02**; blocking findings: A01, A02, A03, A04, A05, A06, A07, A08, A10, A11, A12, A13, A14, A15, D02, D03, D04, D05, D06, D07, D08, N01, N02, N03, N04, N05
- artifact hashes are listed in the generated `report.json`; historical evidence is unchanged.

