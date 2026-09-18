# RF-02 — Actual QuantBT simulation, public Mode 4 baseline, route qualification

Generated from committed RF-02 artifacts by `scripts/write_rf02_report.py`. No edge is claimed: this phase proves the execution and selection pipeline, not a market result.

## 1. Objective and what is not tested

Replace the fabricated-fill bridge with actual QuantBT execution (A02/A03/A04), bind the registered one-way fee exactly once (A01), run the real public Mode 4 `per_fold_causal` pipeline (A08), map HTF decisions onto the 1m clock (A06) and qualify the 20 cells. **Not tested:** whether regime timing beats calendar; that is RF-04/RF-05.

## 2. Identity, contracts and resolved route

- public baseline trace: mode `mode_4_is_only_robust`, schedule `per_fold_causal`, metric `is_only_robust`, backend `endpoint`, `oos_used_for_selection=False`, claim `strict_fold_local_retraining`
- baseline frame: 9000 synthetic bars, 104 trial rows, selected digest `pv-17c54f5e3474ea0d`, wall 32.391s
- native probe: ok=True, resolved="native_prepared", native_batches=3, scored_bars=9588
- fee binding: {'fee': 0.0008, 'fee_rate': 0.0004} (one-way 0.0004 bound once)
- alpha registry: 4 adapters, warmup {'A-SC': 23, 'A-HMA': 250, 'A-VWAP': 50, 'A-HASH': 106}

## 3. Findings fixed and their acceptance tests

| finding | repair | test |
|---|---|---|
| A01 fee | `routes.bound_fee_kwargs`: fee=2*one_way, fee_rate=one_way | `test_a01_the_bound_route_charges_the_registered_one_way_rate` |
| A02 backdate | event account: FLAT until requested bar + warmup | `test_a02_a_future_requested_initial_is_flat_until_its_bar` |
| A03 non-converged | `ProbeStatus.NOT_EVALUATED`; unmapped/non-converged never scored | `test_a03_a_non_converged_candidate_is_not_financially_evaluated` |
| A04 fabricated fills | event account consumes `context.fills_this_bar`; follow-ups reach the position | `test_a04_a_corrective_followup_exit_reaches_the_position` |
| A05 HMA enum | canonical 4-value enum + explicit migration | `test_a05_a_legacy_sl_input_alias_migrates_explicitly` |
| A06 HTF clock | `execution_clock` maps decisions to the first 1m open >= HTF close | `test_a06_an_htf_decision_does_not_fill_on_its_own_close` |
| A07 boundary PnL | prior-mark telescoping in `episode_metrics` | `test_a07_episode_money_deltas_telescope_to_the_whole_account_delta` |
| A08 baseline | real `walk_forward` Mode 4, no hand-built records | `test_a08_the_public_mode4_causal_pipeline_runs_and_declares_is_only_selection` |

## 4. Budget, coverage and route matrix

- route matrix counts (all 20 cells): {'QUALIFIED_EVENT': 5, 'QUALIFIED_FAST': 5, 'BLOCKED_CAPABILITY': 10}
- A-SC: QUALIFIED_FAST; A-HMA: QUALIFIED_EVENT; A-VWAP/A-HASH: BLOCKED_CAPABILITY (amend/ladder not expressible on the event route) — no silent reroute
- baseline search: 8 trials/fold-config, 9000 bars, 32.391s

## 5. Technical vs market vs synthetic

- Synthetic: public baseline (deterministic frame) and the route-proof pilot.
- **Real snapshot pilot**: BTCUSDT 1m, 2021-01-05 00:00..2021-01-20 00:00, 21601 1m bars (1441 15m bars), 1 mapped intents, 1 engine fills, equity 19896.52, 5.668s
- Resolution: A-SC decides on 15m; orders execute on the 1m engine clock (A06).

## 6. Metrics and decay

No economic claim is made here. `signal_causality_scope` from the engine is recorded: `legacy_series_adapter_timing_unverified` — the pilot pins the clock with A06; the WFO stitched final execution remains close-target and is reported as such.

## 7. Runtime profile

- event account cold/warm: {'A-SC': {'cold_seconds': 1.313, 'warm_seconds': 0.161}, 'A-HMA': {'cold_seconds': 0.163, 'warm_seconds': 0.163}}
- native probe wall: 1.115s
- baseline wall: 32.391s

## 8. Proof capability

- Positive control: A-HMA protection orders were projected and filled by the engine (2 fills, 0 unmapped).
- Treatment reached execution: A-SC real-snapshot pilot produced engine fills on the 1m clock.
- Not yet: regime treatment execution (RF-03).

## 9. Potential assessment

`UNASSESSED` until RF-03 wires the causal schedule and RF-04 runs the paired comparison.

## 10. Claim limitations

- A-VWAP/A-HASH blocked: their order semantics are not expressible on the current event route.
- The real pilot covers one alpha/symbol/window; it proves the route, not an edge.
- Native probe resolved the Python native-prepared route; Rust runtime capability is recorded, not claimed as a separate benchmark.

## 11. Exit decision

**RF-02: PARTIAL_TECHNICAL_CLOSURE** — A01–A08 repaired with failing-before tests green, public Mode 4 in use, no fabricated fills on the corrective path; A-VWAP/A-HASH remain blocked and are reported as PARTIAL, never COMPLETE. Remaining before RF-03: nothing on the primary path.

## 12. Rerun recipe

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf02_mode4_baseline.py
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf02_pilot.py
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf02b_closeout.py
$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf02_report.py
```

