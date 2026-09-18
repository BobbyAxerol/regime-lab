# TE-03 report — features, targets, model vintages and emissions

Stage scope: `features -> targets -> model vintages` only. Controls, full-path positive power and statistical null calibration (TE03.7 partial) are not run here; the registered reasons are below.

## Stage facts (real snapshot data, one worker, no data_loader.py)

- features: `RAW_FEATURES_BUILT` over 5 copied symbols, 8766 4h rows, 30 rows with any missing feature, raw parquet `776069b1c024ab40`; scaler `NOT_FITTED`.
- targets: 14 non-overlapping 28-day targets, 32 candidates each, origins 2020-12-02 .. 2021-12-01; candidate bank collected from the completed pilot-09 selection (availability precedes every origin).
- model: 12 real fitted vintages (JM K2/K3 x lambda 0.5/1/2 plus M0 control, 2 fit seeds, 3 inner chronological validation blocks); a real fitted model, not a frozen stub.
- emissions: 2003 states, 2003 decision-eligible, quality statuses ['OK'].
- causality checks: {"feature_schema_pinned": true, "future_or_same_time_targets_excluded": true, "no_future_training_outcome": true, "ready_not_before_cutoff": true}; 12 future/same-time targets excluded by the registered purge.

## Per-vintage evidence

| cutoff | design used | decision | admissible | training targets | outer planned/evaluable | mean outer effect |
|---|---|---|---|---|---|---|
| 2021-02-01 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 2 | 1/0 |  |
| 2021-03-01 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 3 | 1/1 | -0.178288 |
| 2021-03-29 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 4 | 1/1 | 0.294437 |
| 2021-04-26 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 5 | 1/0 |  |
| 2021-05-24 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 6 | 1/0 |  |
| 2021-06-21 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 7 | 1/1 | 0.18042 |
| 2021-07-19 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 8 | 1/1 | -0.261512 |
| 2021-08-16 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 9 | 1/1 | -0.027176 |
| 2021-09-13 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 0/7 | 10 | 1/1 | 0.270906 |
| 2021-10-11 | JM-K3-L0.5 | SELECTED_INNER_INFORMATIVE_DESIGN | 1/7 | 11 | 1/1 | -0.142621 |
| 2021-11-08 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 2/7 | 12 | 1/1 | 0.018381 |
| 2021-12-06 | M0 | NO_PROMISING_DESIGN_M0_CONTROL | 5/7 | 12 | 0/0 |  |

## Information, opportunity and decision

- information value (future candidate-utility ranking, base comparator unconditional profile): 8/11 evaluable; mean 0.019318, range [-0.261512, 0.294437], dispersion 0.210863; inference `INCONCLUSIVE_SUPPORT` (information needs calendar span, blocks and at least 20 episodes).
- parameter opportunity: 14 targets x 32 candidates; utility range mean 0.00100440; per-origin unique behaviors 16..29; rank reversal fraction 0.4611 over 6448 pairs (hindsight diagnostic only).
- model decision: `KEEP_SECONDARY_DESIGN_NO_EXPANSION`; selected inner-informative design 1/12 vintages; M0 control 11; stop condition: do not expand the model ladder while the inner-informative design is unavailable in most vintages and the outer information family is INCONCLUSIVE_SUPPORT.

## Pending (explicit reasons)

- TE03.7 full-path positive/null calibration and treatment funnel are NOT run: they need the controls and statistical-calibration stages, which are outside this Part-4 scope; no zero-filled calibration is claimed.
- TE03.6 is `INCONCLUSIVE_SUPPORT`: 8 evaluable outer targets with mixed signs are below the registered block requirement (calendar span, blocks, >= 20 episodes).
- The 12-vintage window ends 2022-01-01; later years are not evaluated in this sub-step.

## Tests

- `environments/lab_venv/bin/python -m pytest tests/time_edge_validation_v4 -q` -> 138 passed.
- Full suite: 1015 passed, 2 pre-existing failures in files untouched by this work (`time_edge/schedule.py:Selection` unreachable symbol; `configs/time_edge_validation_v4/delivery_scope_r05.json` has no `schema` key).
