# RF-04 — Fast real-alpha experiment: metrics, decay and controls

Generated from committed RF-04 artifacts by `scripts/write_rf04_report.py`. The bounded two-cell pilot cannot support an economic claim; no positive result is recorded.

## 1. Objective and what is not tested

Test whether a causal regime-triggered refit schedule (`M4_REGIME`) changes the continuous account outcome against the calendar per-fold causal WFO (`M4_CAL`) on real snapshots, with refit cadence/compute separated by the mandatory budget control (`M4_CAL_MATCHED`), and close the metrics/decay panel (D1 IS->OOS, D2 fixed-parameter age, D3 adjacent operational folds) required before scaling.

**Not tested:** economic superiority. The execution span is a 2-cell bounded pilot (A-SC/BTCUSDT and A-HMA/BTCUSDT) at 8 trials/cutoff on the pilot development window 2021-01-01..2022-06-30. The registered discovery protocol declares the wider cohort `server_core_v1, development 2021-01-01..2023-12-31`; the executed scope is narrower and is reported as such. A-VWAP/A-HASH are route-blocked and the remaining 16 cells were not executed; no 20-cell aggregate exists.

## 2. Identity, contracts and resolved runtime

- branch `mode4-corrective` at RF-01 head `f4ba4e1b151222aa9811b25efcacebf960bf33c9`; plan sha256 `bf983c2b63dd748d778a3d9c38360bfb6f081cb9b445d7a8044fbae63b2c7434`
- QuantBT: `{'quantbt-engine': '1.1.1', 'quantbt-native': '0.4.2'}`, import origin `/root/bobby/pool_alpha/lab_regime_model_quantbt/environments/lab_venv/lib/python3.12/site-packages/quantbt/__init__.py`; native module: ModuleNotFoundError: No module named 'quantbt_native'
- original audit archive sha256 `2765bd069a5caf16921c3df03dfafd8f090f4fdd2de5e1550a5ce390c87a980f` (preserved, not rewritten)
- Mode 4 contract: mode `mode_4_is_only_robust`, schedule `per_fold_causal`, metric `is_only_robust`, backend `endpoint`, `oos_used_for_selection=False`, claim `strict_fold_local_retraining`
- economics per arm: registered pilot budget 32 trials/cutoff (corrective spec range 32-64); the bounded pilot registered the low end overridden to 8 trials/cutoff, seed 20260911, account 20000 USDT, entry notional 2000 USDT, one-way fee 0.0004 bound once, slippage 1bp, 180-day training memory
- MDE: 0.0371 account bps/day (`evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json`, `FROZEN_BEFORE_RF04_RESULTS`)
- snapshot: `server_core_v1` manifest sha256 `88c19513043e05bbd7d8901916b87fe01d10822678b020e6cd8d2fdec00300ff`; A-SC 15m 72960 bars; A-HMA 1h 18240 bars
- requested candidates: 8/cutoff; actual resolved candidates: A-SC 3/6 folds (24/48 trial rows), A-HMA 3/6 folds (24/48 trial rows)

## 3. Findings fixed and their acceptance tests

| finding | repair | RF-04 acceptance |
|---|---|---|
| G10/A14 model design | real model ladder selected on fixed-target rank IC, inner-train-only scaler, one-to-one namespace mapping (JM k=3, lambda=0.5) | `test_committed_manifest_has_denominators_and_can_go_red`, `test_committed_registry_maps_one_to_one_and_guards_market_transitions` |
| G11 positive control | synthetic world with known switches; the policy reads emissions, not ground truth | `test_rf04_positive_control.py` + `positive_control.json` (params_changed_by_treatment=True, treatment_reached_execution=True) |
| RF-03 causal schedule | online controller triggers on eligible semantic changes only, no namespace-as-market transitions | `test_rf03_controller.py` |
| RF-04.3 decay separation | raw and penalized IS flavors kept on separate rows; undefined metrics null plus status | `test_rf04_d1_keeps_raw_and_penalized_separate` |
| RF-04.4 matched control | mandatory `M4_CAL_MATCHED` with 6 evenly spaced calendar cutoffs on the same machinery | `test_rf04_matched_control_present_with_registered_budget` |
| execution-route blocker (new) | A-SC endpoint scorer returns one objective for every sampled candidate and exposes no per-fill ledger | funnel rank diagnostic + this report |

Source hashes: `dynamic_fold_provider.py` `018274ca038f63c7f6764e06e55583fd84f050d353d01e9bf857efa0a84c734a`; `run_rf04_paired_pilot.py` `7772808b0710614467153b4ed52f3c430280d4e240fb593f257c46bef92ca55d`.

## 4. Budget, sample and coverage

- raw pilot window 2021-01-01..2022-06-30; folds in the pilot: M4_CAL 3, M4_REGIME 6, M4_CAL_MATCHED 6, M4_REGIME_DELAYED 6
- cutoffs: M4_CAL 2021-01-01T00:00:00+00:00, 2021-06-30T00:00:00+00:00, 2021-12-27T00:00:00+00:00; M4_REGIME 2021-01-03T20:00:00+00:00, 2021-04-10T08:00:00+00:00, 2021-07-21T12:00:00+00:00, 2021-10-28T12:00:00+00:00, 2022-02-26T00:00:00+00:00, 2022-06-06T12:00:00+00:00; M4_CAL_MATCHED 2021-01-01T00:00:00+00:00, 2021-04-11T00:00:00+00:00, 2021-07-20T00:00:00+00:00, 2021-10-28T00:00:00+00:00, 2022-02-05T00:00:00+00:00, 2022-05-16T00:00:00+00:00
- trials: 72 pilot trial rows on each cell; matched and placebo 48 trial rows each on each cell
- coverage: 2 of 20 planned cells executed; A-VWAP/A-HASH stay `BLOCKED_CAPABILITY` (amend/ladder semantics), the other 16 cells `NOT_RUN`; no silent denominator change
- MDE corrected: 0.0371 bps/day; the 8-trial bounded pilot is below the registered 32-64 trials/cutoff

## 5. Technical vs market vs synthetic

- **Market (real snapshot):** all arm records below are real `server_core_v1` data on the development window; no synthetic curve is used in any decay or control number.
- A-SC/BTCUSDT: M4_CAL folds=3 trials=24 equity=19999.969160657056 total_return_pct=-0.0001541967147204559 sharpe=-0.1505374026725576 trades=2 max_dd_pct=0.0008874681061955889 wall=47.665s; M4_REGIME folds=6 trials=48 equity=19999.959669209533 total_return_pct=-0.00020165395233561866 sharpe=-0.22879295671634722 trades=2 max_dd_pct=0.0007657632919013941 wall=107.116s; M4_CAL_MATCHED folds=6 trials=48 equity=19999.969160657056 total_return_pct=-0.0001541967147204559 sharpe=-0.1505374026725576 trades=2 max_dd_pct=0.0008874681061955889 wall=107.224s
- A-HMA/BTCUSDT: M4_CAL folds=3 trials=24 equity=19922.3596154709 total_return_pct=-0.38820192264549247 sharpe=-0.12072810456714066 trades=6 max_dd_pct=2.480420305315043 wall=30.982s; M4_REGIME folds=6 trials=48 equity=20021.084492012164 total_return_pct=0.10542246006082223 sharpe=0.061323155946543306 trades=10 max_dd_pct=1.9233647305383985 wall=54.543s; M4_CAL_MATCHED folds=6 trials=48 equity=19772.661444561334 total_return_pct=-1.1366927771933266 sharpe=-0.3310555261519622 trades=12 max_dd_pct=3.250242905057369 wall=57.519s
- **Synthetic:** G11 positive control only (2 regime vs 4 calendar engine fills, equity 20565.02 vs 21289.25); it never enters a market metric
- **Technical:** D2 replays use the real native-event account on real frames; no mocked evaluation is present in D1/D2/D3

## 6. Metrics and decay

| metric | definition | unit | support / null rule |
|---|---|---|---|
| `mean_daily_return_bps` | mean daily account net return, first day charged from the prior daily equity | account bps/day | null + `INSUFFICIENT_OBSERVATIONS` below 2 daily returns |
| `sharpe` | sqrt(365)*mean/std(daily net return, ddof=1) | ratio | null + `ZERO_VARIANCE` |
| `profit_factor_daily` | sum(positive daily returns)/abs(sum(negative daily returns)) | ratio | null + `NO_LOSS_DENOMINATOR` or `NO_TRADES` |
| `selected_is_objective` | engine Mode 4 robust objective used for selection | engine score | kept raw and penalized on separate D1 rows |

D1 rows 168 (valid 80), D2 rows 36, D3 rows 102 (valid 89); null reasons: IS_ACCOUNT_RETURN_NOT_IN_TRIAL_LEDGER, IS_PROFIT_FACTOR_NOT_IN_TRIAL_LEDGER, OOS_NO_LOSS_DENOMINATOR, OOS_NO_TRADES, OOS_VALID_WITH_FLAGS, UNDEFINED_PROFIT_FACTOR, UNDEFINED_SHARPE, UNDEFINED_VALUE.

Null-value rule: the Mode 4 trial ledger retains the IS Sharpe objective and temporal subperiod statistics, not an IS account return or IS profit factor, so those D1 left values are null with the reason `IS_*_NOT_IN_TRIAL_LEDGER`; they are never filled with an estimate.

**D2 fixed-parameter age replay** (anchors registered before the run: fold-0 selection of each primary arm per cell; h=90 days):

| anchor | H1 mean bps/day | H2 mean bps/day | H3 mean bps/day | H1 trades | H2/H3 trades |
|---|---|---|---|---|---|
| A-HMA/BTCUSDT:M4_CAL:fold0 | -0.6847646647408449 | 0.0 | 0.0 | 2 | 0/0 |
| A-HMA/BTCUSDT:M4_REGIME:fold0 | 1.0225504502367786 | 0.0 | 0.0 | 2 | 0/0 |
| A-SC/BTCUSDT:M4_CAL:fold0 | 3.3093024112172125 | 0.0 | 0.0 | 2 | 0/0 |
| A-SC/BTCUSDT:M4_REGIME:fold0 | 3.3460724380085147 | 0.0 | 0.0 | 2 | 0/0 |

Age reads are diagnostics after selection only; they never update a search threshold or an activation rule in this run.

## 7. Runtime breakdown

- paired pilot wall: 240.3s total across both cells and arms
- M4_CAL_MATCHED wall: 164.743s (placebo 171.856s, status `RUN`)
- D2 anchor replay wall: 34.3s (4/4 anchors replayed, status `COMPLETE`)
- reported vs planned: 2 of 20 cells executed, 8 trials/cutoff instead of the registered 32-64; no canceled budget job and no degraded execution resolution were used to hit time
- no cold/warm native split is claimed in this phase; the event account ran on the installed Python route with `native_import_error` recorded in RF-01

## 8. Proof capability

- positive control: `params_changed_by_treatment=True`, `treatment_reached_execution=True`; the controller fired at the known synthetic switch bars and the engine fills differ by arm
- treatment reached execution on A-HMA/BTCUSDT: engine trades 6 (calendar) vs 10 (regime), i.e. different orders
- treatment did NOT reach execution on A-SC/BTCUSDT: `M4_CAL_MATCHED` and `M4_CAL` equity series are identical (`the two account equity series are identical; the timing treatment did not reach execution on this cell`) and every sampled candidate scored the same objective
- null/placebo: delayed-state arm ran (RUN) with cutoffs 2021-01-17T20:00:00+00:00, 2021-04-24T08:00:00+00:00, 2021-08-04T12:00:00+00:00, 2021-11-11T12:00:00+00:00, 2022-03-12T00:00:00+00:00, 2022-06-20T12:00:00+00:00; it is a diagnostic, not confirmation
- pipeline capability: it can detect parameter-rank signal for A-HMA (varying objectives) and correctly fails closed on A-SC; it cannot yet reject the MDE because the pilot is 2 cells

## 9. Potential assessment

`UNASSESSED` — A-SC/BTCUSDT candidates tie in every fold, so the bounded pilot provides no parameter-rank opportunity evidence for that cell; A-HMA/BTCUSDT ranks vary but the scope cannot establish informed opportunity.

- A-SC/BTCUSDT: `LOW_PARAMETER_OPPORTUNITY` (a cell is tagged LOW_PARAMETER_OPPORTUNITY when every scored fold has at most one distinct finite candidate objective; A-SC ties exactly because the endpoint scorer returned one objective for all sampled candidates in every fold)
- A-HMA/BTCUSDT: `PARAMETER_RANK_SIGNAL_PRESENT`; adjacent selections change parameters 5 times across the 6 regime folds; across the four arms the funnel counts 12 activated parameter changes
- funnel denominators (A-HMA tape): 3271 emissions in window, 3196 eligible/quality-OK, 113 semantic changes, 6 controller triggers
- bottleneck: information (not activation) on A-HMA; the BUDGET_AWARE paired CI [-0.214, 0.615] bps/day contains 0 and the corrected MDE 0.0371
- falsifiable next action: before scaling, repair or quarantine the A-SC endpoint evaluation route so candidate objectives are parameter-sensitive; then freeze and run the registered 32-64 trials/cutoff design; no feature/model complexity is added first

## 10. Claim limitations

- bounded 2-cell pilot on BTCUSDT with 8 trials/cutoff; not the registered 32-64
- the endpoint cell (A-SC/BTCUSDT) returns one objective for every sampled candidate and no per-fill ledger; its parameter ranking is not identified
- the delayed-state placebo and the D2 anchors are diagnostics, not confirmation evidence
- the development window 2021-01-01..2022-06-30 is nested retrospective; no holdout claim
- the registered discovery cohort is `server_core_v1, development 2021-01-01..2023-12-31` but the executed pilot window is 2021-01-01..2022-06-30 (its own registration); the narrower scope is never renamed to the registered cohort
- the paired CIs are exploratory moving-block bootstrap intervals on saved daily returns; they are not a confirmatory test and never license a `POSITIVE` status
- `simulation_complete` and `audit_complete` are separate: all engine accounts flushed and all artifacts are strict JSON with null+reason for missing values

## 11. Exit decision

**RF-04: PARTIAL_TECHNICAL_CLOSURE.** The corrected Mode 4 paired pilot ran on two real cells, the mandatory `M4_CAL_MATCHED` control and the registered delayed-state placebo ran, D1/D2/D3 panels and the decision funnel are complete with real denominators, and the design freeze is recorded. No economic claim is made: A-SC is `NOT_EVALUABLE` (treatment not transmitted to execution) and A-HMA is `INCONCLUSIVE` (2-cell bounded pilot). Remaining tasks: repair or quarantine the A-SC endpoint candidate evaluation, then scale to the registered design before RF-05 confirmation.

## 12. Rerun recipe, output hashes and handoff

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf04_paired_pilot.py
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf04_decay_and_controls.py --force
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q \
  | tee $LAB/evidence/corrective_mode4_v3/RF-04/test_suite_mode4_corrective.log
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pyflakes $LAB/src $LAB/scripts $LAB/tests/mode4_corrective \
  | tee $LAB/evidence/corrective_mode4_v3/RF-04/pyflakes_mode4_corrective.log
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf04_report.py --force
```

For an artifact-only recompute that reuses the committed engine arm records, run `run_rf04_decay_and_controls.py --force --reuse-engine`; the new payload records the superseded artifact hash in `supersedes`.

Recorded output hashes:
- `paired_discovery_pilot.json` `aa70f5a090bce96f9fe070b2a70ef851806b0ca9ed2590c0aed175adeb7210c5`
- `paired_discovery_registration.json` `20c24ded268514391960ca3602dea6b23e5a748d4205896d42cce41a99d3d487`
- `discovery_protocol.json` `94b03a347737895d9f20cffc971081d85a53d042b157a28059ce3857899646b2`
- `positive_control.json` `2e51ec4898d78166de43efa61ba4c8169867f8207a46c0dd4050a1e0a44883ad`
- `controls_registration.json` `69decb922482763defa7cc98b1eb7c04749006736bf3c32674e87d9c68c0bb6d`
- `controls_and_funnel.json` `656a364c7a04a88f21b8c4d067af586d644ad231ff8ceb0fa02d952b2c8f068f`
- `decay_panels.json` `90c9d5c361d33402191b01fa59a17bdab75f97d667f70fe329e33d1ccfe15fdd`
- `design_freeze.json` `accdfe3dfa22923eecda8be2c9ea0671ac8d80018605afd0084f8a8b7b5b25ca`
- `model_design_selection_manifest.json` `47b8ef7f216bda2fc5993fd56ba8d303c9b5f965141a4899b2e6c28bafcb5a7a`
- `causal_model_registry.json` `17ed170e8112f99440330f52bc7ba318548929c6f9a43ecde7c44bb2bd7f43c2`
- `emission_tape_sample.json` `a54d8eae5a0b7472aab5833fc05dc7c9af91f0d3daafccaebe375598c6aae17c`
- `current_coordinate_contract.json` `61c274b5b32e784ad698b7c5f5e1c94c18360a299371be2b26be79307c90ddab`
- `test_suite_mode4_corrective.log` `9ae5a6dfc422233fa81f0383e2ddd7b9d8e5966220433682c7b13134d767bb46`
- `pyflakes_mode4_corrective.log` `ba5a7a923210660e4cf281ff757f4a82938b8ed9ba82df331eab2cd875185b50`

Handoff: next phase `RF-05`; blocking finding = A-SC endpoint candidate evaluation (implementation_fidelity DEVIATED). The registered historical evidence under `evidence/crypto_regime_timeedge_v2/` was not touched.

