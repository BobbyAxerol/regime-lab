# TE03.7 report — positive/null power and full-path controls

- Evidence: `evidence/time_edge_validation_v4/te03/te03_7_power.json` and `evidence/time_edge_validation_v4/te03/te03_7_controls_r2.json`.
- Allocation `TE02-PILOT-R03`: total 105400s, charged 62364.265s; revisions TE02-PILOT-R03-REV01, TE02-PILOT-R03-REV02, TE02-PILOT-R03-REV03, TE02-PILOT-R03-REV04, TE02-PILOT-R03-REV05, TE02-PILOT-R03-REV06, TE02-PILOT-R03-REV07, TE02-PILOT-R03-REV08, TE02-PILOT-R03-REV09.
- Scope: statistical calibration of the registered family plus the bounded engine full-path controls. No market edge claim; TE-04 stays closed.

## Positive/null statistical calibration (known synthetic effects; no engine call)

- calibration status: `STATISTICAL_CALIBRATION_PASS`; source `evidence/time_edge_validation_v4/host-calibration-01.json`; engine runs 0.
| world (delta units) | worlds | family rejections | rate | Wilson 95% | mean of true effects |
|---|---|---|---|---|---|
| 0.0 | 1000 | 0 | 0.0000 | [0.0000, 0.0038] | [0.0, 0.0, 0.0, -0.001] |
| 1.0 | 1000 | 36 | 0.0360 | [0.0261, 0.0494] | [0.001, 0.001, 0.001, 0.0] |
| 2.0 | 1000 | 1000 | 1.0000 | [0.9962, 1.0000] | [0.002, 0.002, 0.002, 0.001] |
| 4.0 | 1000 | 1000 | 1.0000 | [0.9962, 1.0000] | [0.004, 0.004, 0.004, 0.003] |

- positive control at +2 delta: family rate 1.0000, per-hypothesis power [1.0, 1.0, 1.0, 0.944], recovered **True** (RECOVERED).
- null controls: maximum family Wilson upper 0.0494 against tolerance 0.08; false positive **False** (NO_FALSE_POSITIVE_AT_REGISTERED_TOLERANCE).
- `full_pipeline_calibration`: `NOT_EXECUTED_BY_THIS_TASK` — the statistical payload does not certify the engine path.

## Engine full-path structural controls

- run `te-host-controls-06`: `NOT_RUN_BUDGET`; allocation revision `TE02-PILOT-R03-REV09`; stop reason: `None`.
- sharding: one registered world per full-control shard; worlds BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT; 0/1 attempted shards complete of 10 planned; per-shard cap 2700s.
| task | world | condition | cap s | status | wall s | reason |
|---|---|---|---|---|---|---|
| structural-NULL_STATIONARY-BTCUSDT | BTCUSDT | NULL_STATIONARY | 2700 | TIMED_OUT | 2700.1 | task wall cap reached |
| structural-RECURRING_OPPORTUNITY-BTCUSDT | BTCUSDT | RECURRING_OPPORTUNITY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-NULL_STATIONARY-ETHUSDT | ETHUSDT | NULL_STATIONARY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-RECURRING_OPPORTUNITY-ETHUSDT | ETHUSDT | RECURRING_OPPORTUNITY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-NULL_STATIONARY-SOLUSDT | SOLUSDT | NULL_STATIONARY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-RECURRING_OPPORTUNITY-SOLUSDT | SOLUSDT | RECURRING_OPPORTUNITY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-NULL_STATIONARY-BNBUSDT | BNBUSDT | NULL_STATIONARY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-RECURRING_OPPORTUNITY-BNBUSDT | BNBUSDT | RECURRING_OPPORTUNITY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-NULL_STATIONARY-DOGEUSDT | DOGEUSDT | NULL_STATIONARY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |
| structural-RECURRING_OPPORTUNITY-DOGEUSDT | DOGEUSDT | RECURRING_OPPORTUNITY | 2700 | NOT_RUN_BUDGET |  | task never launched: shards are sequential and the runtime does not advance past a shard that did not complete; no attempt row exists in this run ledger |

- pre-shard projection (old monolith profile): lower bound per condition 26869s (7.46h); two conditions 14.93h, excluding regime-triggered selections (one 32-trial search each); two account deployments; world/features/emit overhead.
- measured shard residual per world: targets remaining 4212s + model fits 1114s + calibration/initial selections 11326s = 16652s, excluding regime-triggered selections (one 32-trial search per trigger, 1618.0s each), two account deployments, checkpoint replay overhead; per-shard cap 2700s.

## Treatment funnel

### not measured

- status `NOT_RUN_BUDGET` for condition `None`; cell `None`.

| step | count | denominator | reason | denominator reason |
|---|---|---|---|---|
| valid_observations |  |  | every shard needs more than its 2700s cap for the registered path; the bounded invocation stopped after the first shard did not complete inside its cap, and no condition-wide funnel was measured | no completed full-path control; no measured denominator exists |
| triggers |  |  | every shard needs more than its 2700s cap for the registered path; the bounded invocation stopped after the first shard did not complete inside its cap, and no condition-wide funnel was measured | no completed full-path control; no measured denominator exists |
| searches |  |  | every shard needs more than its 2700s cap for the registered path; the bounded invocation stopped after the first shard did not complete inside its cap, and no condition-wide funnel was measured | no completed full-path control; no measured denominator exists |
| different_params |  |  | every shard needs more than its 2700s cap for the registered path; the bounded invocation stopped after the first shard did not complete inside its cap, and no condition-wide funnel was measured | no completed full-path control; no measured denominator exists |
| activated |  |  | every shard needs more than its 2700s cap for the registered path; the bounded invocation stopped after the first shard did not complete inside its cap, and no condition-wide funnel was measured | no completed full-path control; no measured denominator exists |
| different_orders |  |  | every shard needs more than its 2700s cap for the registered path; the bounded invocation stopped after the first shard did not complete inside its cap, and no condition-wide funnel was measured | no completed full-path control; no measured denominator exists |

- `valid_observations` rule: eligible emissions with decision_eligible=True; denominator = all emissions in the control window
- `triggers` rule: controller triggers accepted inside the window; denominator = decision-eligible emissions
- `searches` rule: search calls executed = 1 candidate bank + 1 initial + calendar cutoffs + regime triggers; denominator = the same registered schedule
- `different_params` rule: distinct selected parameter digests across the M4_REGIME selections; denominator = M4_REGIME selections
- `activated` rule: ACTIVATE events in the deployed M4_REGIME account; denominator = M4_REGIME commands
- `different_orders` rule: regime fills whose (absolute bar, side) is absent from the calendar fills; denominator = regime fills

### Partial shards (stages that did publish, nothing zero-filled)

| shard | condition | world | worlds | features | searches (32-trial bank) | targets | vintages |
|---|---|---|---|---|---|---|---|
| structural-NULL_STATIONARY-BTCUSDT | NULL_STATIONARY | BTCUSDT | 5 | True | 1 | 4/45 | 0/53 |

## 32-trial Mode 4 selection result

### NULL_STATIONARY — candidate bank selection

- search artifact `evidence/time_edge_validation_v4/runs/te-host-controls-06/tasks/ca73939c2c28963b9544c3039f1dfcbfaf5429867404a1c75cc45e7b48c0fc45/search-388a1edf83af9e16.json`, cutoff `2019-07-15T00:00:00+00:00`, status `SELECTED`.
- selected trial 6: params `{"AP": 31, "alpha.condition_threshold": 80, "coeff": 4, "novolumedata": false, "src_col": "close"}`, objective 1.0501836502293123.
- components: mean IS Sharpe 1.0501836502293123, mean OOS Sharpe 0.0, mean decay 0.0, std decay 0.0, pruned False.
- trials completed 32/32; scorer calls 224; candidate cache hits 0.
- selected candidate `evidence/time_edge_validation_v4/runs/te-host-controls-06/tasks/ca73939c2c28963b9544c3039f1dfcbfaf5429867404a1c75cc45e7b48c0fc45/search-388a1edf83af9e16/candidate-6c711ffb9ee31b687b9463b7074563d78822ad51e78a028e06aeff65521a540a.json`: status `EVALUATED`, fills 5.

- `truth_entered_learner`: `None`; fabricated fills: `False`.
- boundary power qualification: `NOT_EVALUABLE_FROM_STRUCTURAL_WORLD_ALONE` — a structural world with opportunity does not specify a known net learner effect of 2 delta.

## P0 gate checks

| gate | status |
|---|---|
| funnel_six_steps_with_denominators | FAIL |
| no_fabricated_fills | PASS |
| positive_recovers_and_null_under_tolerance | PASS |
| selection_32_trials_complete | PASS |

## Blocker

- `evidence/time_edge_validation_v4/te03/controls_06_blocker.json`: `NOT_RUN_BUDGET` — every shard needs more than its 2700s cap for the registered path; the bounded invocation stopped after the first shard did not complete inside its cap, and no condition-wide funnel was measured.
- measured: 1 attempted / 10 planned shards, 0 complete; bank selection 32 trials complete: `True`.
- next: P0 stops. The sharding itself is sound (each shard has one world, one 2700s cap and its own checkpoint), but the registered full path needs far more wall than the remaining envelope; a further attempt needs a new registered plan (e.g. stage-sliced shards) and a new allocation revision, not a cap raise.

## Delayed and risk controls

- TE04_SCOPE_NOT_STARTED: delayed-state, placebo-tape and risk-only controls are assigned to TE-04.4/R5; TE-04 stays blocked until the TE-02/03 gates close

## Tests

- tests/time_edge_validation_v4/test_te03_7.py (guards)
