# FP-08 cell-2 archive — A-SC/ETHUSDT (fp08cell2archive-20260924T125136Z-c93956c8)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp08cell2archive-20260924T125136Z-c93956c8
- started_at: 2026-09-24T12:51:36.376001+00:00, finished_at: 2026-09-24T14:46:53.360061+00:00
- alpha: A-SC, symbol: ETHUSDT, origins: 3 (guide FP08.1 replication cell, owner-approved scope dec-b5a96eb125bb80cd)
- B_search (reused from FP-03's frozen search_policy.json, alpha-level): 256
- origins searched OK / total: 3/3
- total records: 48, matured: 48, censored: 0
- fresh engine search-trial calls this run: 512
- sum of per-origin search-only wall_seconds_measured: 9344.1s (2.60h) over 3 origins, mean 3114.7s/origin (compare cell 1/BTCUSDT's own ~2786-3042s/origin -- ETHUSDT measured ~2x slower per trial in the pre-run probe, disclosed before this run)
- decay_D_mean_daily_return (IS - forward; positive=worse) over 48 matured records: min=-0.000355, max=0.001430, mean=0.000452
- positive (worse) decay: 44/48

## Per-origin results
### 2021-06-01
- wf_ok: True, trials: 256/256, wall: 3439.270339s, peak_mib: 1487.8, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp08_cell2_search_raw/origin_2021-06-01.json
- regions built: 16
  - R00: support=60, is_objective_mean=2.7856, forward_mean_daily_return=-0.000065, D_mean_daily_return=0.000748
  - R01: support=6, is_objective_mean=2.5761, forward_mean_daily_return=-0.000534, D_mean_daily_return=0.001224
  - R02: support=14, is_objective_mean=1.8943, forward_mean_daily_return=-0.000056, D_mean_daily_return=0.000590
  - R03: support=4, is_objective_mean=2.2088, forward_mean_daily_return=-0.000469, D_mean_daily_return=0.001112
  - R04: support=13, is_objective_mean=1.6877, forward_mean_daily_return=-0.000132, D_mean_daily_return=0.000670
  - R05: support=5, is_objective_mean=1.4403, forward_mean_daily_return=-0.000267, D_mean_daily_return=0.000509
  - R06: support=3, is_objective_mean=1.5558, forward_mean_daily_return=0.000220, D_mean_daily_return=0.000226
  - R07: support=3, is_objective_mean=1.6998, forward_mean_daily_return=-0.000138, D_mean_daily_return=0.000555
  - R08: support=4, is_objective_mean=1.5824, forward_mean_daily_return=-0.000534, D_mean_daily_return=0.001054
  - R09: support=2, is_objective_mean=1.5706, forward_mean_daily_return=-0.000467, D_mean_daily_return=0.000982
  - R10: support=4, is_objective_mean=0.9676, forward_mean_daily_return=-0.000175, D_mean_daily_return=0.000594
  - R11: support=1, is_objective_mean=1.7852, forward_mean_daily_return=0.000402, D_mean_daily_return=0.000045
  - R12: support=2, is_objective_mean=1.6321, forward_mean_daily_return=-0.000222, D_mean_daily_return=0.000602
  - R13: support=4, is_objective_mean=1.0458, forward_mean_daily_return=-0.001054, D_mean_daily_return=0.001430
  - R14: support=1, is_objective_mean=1.6296, forward_mean_daily_return=-0.000858, D_mean_daily_return=0.001284
  - R15: support=1, is_objective_mean=1.6217, forward_mean_daily_return=0.000047, D_mean_daily_return=0.000375

### 2022-06-01
- wf_ok: True, trials: 256/256, wall: 3109.325383s, peak_mib: 1624.6, reused_from_cache: None
- regions built: 16
  - R00: support=46, is_objective_mean=-0.7401, forward_mean_daily_return=-0.000840, D_mean_daily_return=0.000807
  - R01: support=18, is_objective_mean=-0.7279, forward_mean_daily_return=-0.000573, D_mean_daily_return=0.000540
  - R02: support=41, is_objective_mean=-0.8555, forward_mean_daily_return=-0.001014, D_mean_daily_return=0.000908
  - R03: support=5, is_objective_mean=-1.4597, forward_mean_daily_return=0.000256, D_mean_daily_return=-0.000355
  - R04: support=6, is_objective_mean=-1.0509, forward_mean_daily_return=-0.000363, D_mean_daily_return=0.000290
  - R05: support=3, is_objective_mean=-1.1814, forward_mean_daily_return=-0.000861, D_mean_daily_return=0.000730
  - R06: support=1, is_objective_mean=-1.0753, forward_mean_daily_return=-0.000082, D_mean_daily_return=-0.000008
  - R07: support=3, is_objective_mean=-1.1909, forward_mean_daily_return=-0.000635, D_mean_daily_return=0.000505
  - R08: support=5, is_objective_mean=-1.2701, forward_mean_daily_return=-0.000671, D_mean_daily_return=0.000483
  - R09: support=2, is_objective_mean=-1.4321, forward_mean_daily_return=-0.000974, D_mean_daily_return=0.000820
  - R10: support=8, is_objective_mean=-2.0568, forward_mean_daily_return=-0.000839, D_mean_daily_return=0.000585
  - R11: support=4, is_objective_mean=-2.1924, forward_mean_daily_return=-0.000859, D_mean_daily_return=0.000582
  - R12: support=2, is_objective_mean=-2.5920, forward_mean_daily_return=-0.000553, D_mean_daily_return=0.000310
  - R13: support=1, is_objective_mean=-2.1749, forward_mean_daily_return=-0.000995, D_mean_daily_return=0.000712
  - R14: support=1, is_objective_mean=-2.5520, forward_mean_daily_return=-0.000761, D_mean_daily_return=0.000396
  - R15: support=1, is_objective_mean=-2.8214, forward_mean_daily_return=-0.001123, D_mean_daily_return=0.000671

### 2023-06-01
- wf_ok: True, trials: 256/256, wall: 2795.502409s, peak_mib: 2278.8, reused_from_cache: None
- regions built: 16
  - R00: support=20, is_objective_mean=1.3516, forward_mean_daily_return=0.000167, D_mean_daily_return=-0.000061
  - R01: support=37, is_objective_mean=1.2073, forward_mean_daily_return=-0.000026, D_mean_daily_return=0.000151
  - R02: support=22, is_objective_mean=1.1851, forward_mean_daily_return=-0.000127, D_mean_daily_return=0.000260
  - R03: support=8, is_objective_mean=1.0651, forward_mean_daily_return=-0.000015, D_mean_daily_return=0.000184
  - R04: support=2, is_objective_mean=0.6552, forward_mean_daily_return=-0.000011, D_mean_daily_return=0.000150
  - R05: support=4, is_objective_mean=0.6425, forward_mean_daily_return=-0.000110, D_mean_daily_return=0.000200
  - R06: support=3, is_objective_mean=0.3838, forward_mean_daily_return=0.000007, D_mean_daily_return=0.000097
  - R07: support=3, is_objective_mean=0.3314, forward_mean_daily_return=-0.000114, D_mean_daily_return=0.000221
  - R08: support=1, is_objective_mean=0.6544, forward_mean_daily_return=0.000060, D_mean_daily_return=0.000031
  - R09: support=7, is_objective_mean=0.0869, forward_mean_daily_return=0.000036, D_mean_daily_return=-0.000000
  - R10: support=6, is_objective_mean=-0.2997, forward_mean_daily_return=-0.000073, D_mean_daily_return=0.000062
  - R11: support=3, is_objective_mean=-0.0840, forward_mean_daily_return=-0.000155, D_mean_daily_return=0.000173
  - R12: support=4, is_objective_mean=-0.6060, forward_mean_daily_return=-0.000042, D_mean_daily_return=0.000040
  - R13: support=3, is_objective_mean=-0.2740, forward_mean_daily_return=0.000017, D_mean_daily_return=0.000011
  - R14: support=3, is_objective_mean=-0.5552, forward_mean_daily_return=-0.000086, D_mean_daily_return=0.000029
  - R15: support=2, is_objective_mean=-0.6649, forward_mean_daily_return=-0.000191, D_mean_daily_return=0.000157

## Support summary
- model_ready_count: 40, descriptive_only_count: 8

## Permitted conclusions
- Technical: a real historical forward ledger was built at 3 real chronological origins on A-SC/ETHUSDT, reusing FP-04's own already-tested archive machinery unchanged (forward_ledger.py, checkpoint_search.py, verifier_fp04.py).
- Research: NOT_ASSESSED -- this stage builds cell 2's raw candidate archive only; it makes no market/edge claim. Selector B/C fit and the locked A/B/C study for this cell come next, then run_fp08.py combines both cells for guide FP08.3-.5.
- Scope: 3 of cell 1's 12 origins -- an explicit, disclosed, cost-proportionate partial replication (ETHUSDT measured ~2x slower per search trial than BTCUSDT).
