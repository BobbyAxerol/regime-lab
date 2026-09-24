# FP-05 — Implement B_FP (Selector B, no regime) (fp05-20260923T163548Z-9e78d592)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp05-20260923T163548Z-9e78d592
- started_at: 2026-09-23T16:35:48.460585+00:00
- alpha: A-SC, symbol: BTCUSDT, archive: FP-04's 12-origin/192-record ledger

## OOF diagnostics (guide 8.3/8.4/8.7)
- distinct matured (fit) origins: 12 (guide floor >= 12)
- distinct OOF validation origins: 8 (guide floor >= 8 for diagnostics, >= 20 for the tail-quantile branch)
- validation origins: ['2022-01-01', '2022-04-01', '2022-07-01', '2022-10-01', '2023-01-01', '2023-04-01', '2023-07-01', '2023-10-01']
- weighted OOF MSE by alpha:
  - alpha=0.1: n=128, weighted_mse=1.8794355404886332e-07
  - alpha=1.0: n=128, weighted_mse=1.750281030244164e-07
  - alpha=10.0: n=128, weighted_mse=1.744905388068486e-07

## Model selection (guide 8.3)
- selected alpha: 10.0 (lowest aggregate weighted OOF MSE across the walk-forward folds)
- final model trained on 192 rows (0 excluded)
- decay-risk branch: **MEAN_DECAY** -- TAIL_ESTIMATE_UNSUPPORTED: only 8 distinct OOF origins, need >= 20 for the tail-quantile branch (guide 8.7); 12 >= 12 fit origins and 8 >= 8 OOF-diagnostics origins
- utility floor: 0.000064/day (configs/minimum_economic_effect.json (reused verbatim): guide 8.6/FP08.5's 'OOS utility/risk safeguard' names no concrete number anywhere in the guide text -- reusing the lab's OWN already-registered economic-significance threshold (registered 2026-09-09, before any FP arm comparison existed) is a disclosed, non-arbitrary choice rather than inventing a new number for this phase alone)

## Held-out demo: score guide 8.6's ordered checks on the 2023-10-01 candidate pool (model trained on the 11 EARLIER origins only)
  - R00 (support=50.0): predicted_utility=0.000016, decay_risk=0.0001528785767147688, eligible=False, reasons=['predicted utility 0.000016 < floor 0.000064'], ACTUAL forward label=0.000040
  - R01 (support=18.0): predicted_utility=0.000016, decay_risk=0.00014483688753433739, eligible=False, reasons=['predicted utility 0.000016 < floor 0.000064'], ACTUAL forward label=0.000506
  - R02 (support=21.0): predicted_utility=0.000014, decay_risk=0.00014459663658005566, eligible=False, reasons=['predicted utility 0.000014 < floor 0.000064'], ACTUAL forward label=0.000494
  - R03 (support=2.0): predicted_utility=0.000005, decay_risk=0.0001500044041503211, eligible=False, reasons=['predicted utility 0.000005 < floor 0.000064'], ACTUAL forward label=0.000010
  - R04 (support=3.0): predicted_utility=-0.000007, decay_risk=6.360166090029539e-05, eligible=False, reasons=['predicted utility -0.000007 < floor 0.000064'], ACTUAL forward label=0.000070
  - R05 (support=2.0): predicted_utility=0.000005, decay_risk=0.000123734334887228, eligible=False, reasons=['predicted utility 0.000005 < floor 0.000064'], ACTUAL forward label=0.000199
  - R06 (support=1.0): predicted_utility=0.000003, decay_risk=0.00012437221972617707, eligible=False, reasons=['predicted utility 0.000003 < floor 0.000064', 'support 1.0 < floor 2'], ACTUAL forward label=0.000239
  - R07 (support=2.0): predicted_utility=0.000000, decay_risk=0.00011810858468471495, eligible=False, reasons=['predicted utility 0.000000 < floor 0.000064'], ACTUAL forward label=0.000232
  - R08 (support=6.0): predicted_utility=-0.000007, decay_risk=0.00011906954441235905, eligible=False, reasons=['predicted utility -0.000007 < floor 0.000064'], ACTUAL forward label=0.000220
  - R09 (support=2.0): predicted_utility=-0.000009, decay_risk=0.00010804266249707736, eligible=False, reasons=['predicted utility -0.000009 < floor 0.000064'], ACTUAL forward label=0.000131
  - R10 (support=4.0): predicted_utility=-0.000015, decay_risk=0.00012598397390865175, eligible=False, reasons=['predicted utility -0.000015 < floor 0.000064'], ACTUAL forward label=-0.000094
  - R11 (support=2.0): predicted_utility=-0.000005, decay_risk=9.34180240495108e-05, eligible=False, reasons=['predicted utility -0.000005 < floor 0.000064'], ACTUAL forward label=0.000185
  - R12 (support=1.0): predicted_utility=0.000002, decay_risk=8.53993526923489e-05, eligible=False, reasons=['predicted utility 0.000002 < floor 0.000064', 'support 1.0 < floor 2'], ACTUAL forward label=0.000183
  - R13 (support=3.0): predicted_utility=-0.000032, decay_risk=5.841678889620071e-05, eligible=False, reasons=['predicted utility -0.000032 < floor 0.000064'], ACTUAL forward label=0.000018
  - R14 (support=7.0): predicted_utility=-0.000007, decay_risk=8.804060822010827e-05, eligible=False, reasons=['predicted utility -0.000007 < floor 0.000064'], ACTUAL forward label=0.000167
  - R15 (support=2.0): predicted_utility=-0.000004, decay_risk=7.581175528248094e-05, eligible=False, reasons=['predicted utility -0.000004 < floor 0.000064'], ACTUAL forward label=0.000260

## Selector B decision vs stock comparator (guide task 8 / required diagnostic)
- Selector B: COMMON_FLAT_FALLBACK -- no candidate cleared both the utility floor and the support floor
- selected params: None
- stock comparator (best raw IS mean return, no forward-persistence modelling): {'record_id': '2023-10-01:R00', 'params': {'coeff': 3, 'AP': 56, 'alpha.condition_threshold': 80, 'novolumedata': False, 'src_col': 'close'}, 'is_mean_daily_return': -3.892231528041958e-05, 'actual_forward_label': 3.959825617615352e-05}
- selected == stock: False

## Admission and deployment (FP05-G-ACTION)
```json
{
  "0": {
    "fold": "0",
    "decision": "COMMON_FLAT_FALLBACK",
    "reason": "no candidate cleared both the utility floor and the support floor",
    "supplied_digest": null,
    "consumed": null,
    "consumed_digest": null,
    "blocked_reason": "RAW_NONE: no stock selection recorded for this fold"
  }
}
```
- no deployment attempted (COMMON_FLAT_FALLBACK)

## Glossary
- **OOF (out-of-fold)** (a prediction made for an origin whose data was NEVER used to fit the model that produced it -- guide 8.3's walk-forward exercise)
- **walk-forward** (chronological cross-validation: fold i trains on every EARLIER origin's already-matured labels only, guide 8.4)
- **decay-risk branch** (which of guide 8.6's three registered scoring rules applies -- TAIL_QUANTILE, MEAN_DECAY, or FALLBACK_STOCK_INCUMBENT -- chosen from the MEASURED origin counts, never asserted)
- **TAIL_ESTIMATE_UNSUPPORTED** (guide 8.6's own label for the case where fit support is sufficient but tail-quantile support is not -- this run's actual case)
- **eligibility floor** (guide 8.6: a candidate must clear BOTH a predicted-utility floor and a support floor before its decay risk is even assessed)
- **stock comparator** (the best raw in-sample mean-return candidate in the SAME pool, with no forward-persistence model applied -- guide's required 'selected vs stock candidate difference' diagnostic)

## Permitted conclusions
- Technical: a real chronological walk-forward OOF ran on FP-04's full archive (0 future-label leaks, independently re-checked), a ridge model was fit deterministically, the decay-risk branch was chosen from measured origin counts (MEAN_DECAY, TAIL_ESTIMATE_UNSUPPORTED, guide's own registered fallback), and the selector's output was wired through the SAME admission function FP-01 repaired into a COMMON_FLAT_FALLBACK (no eligible candidate).
- Research: NOT_ASSESSED -- FP-05 builds and demonstrates Selector B; it does not run the locked A/B/C comparison (FP-07) or claim B beats the stock selector.
- Owner review: PENDING; FP-06 needs its own approval (R-18).
