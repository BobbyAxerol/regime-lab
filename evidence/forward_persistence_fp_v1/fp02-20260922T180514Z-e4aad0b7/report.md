# FP-02 — Evaluator and reusable runtime (fp02-20260922T180514Z-e4aad0b7)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7
- started_at: 2026-09-22T18:05:14.544052+00:00
- market window: A-SC 2023-06-01 -> 2023-06-11 (14400 real 1m bars, sha256-verified snapshot)
- engine calls (real): 16

## FP02-G-PARITY — audit route vs score/fast route, same candidate
- status: PASS
- equity_exact_equal: True (max_abs_equity_diff=0.0)
- audit: fill_count=53 engine_fill_count=53 entries=27
- fast (score): fill_count=53 engine_fill_count=0 entries=27
- precedent: FUP-04 evidence/corrective_mode4_v3/FUP-04/report_level_memory_repair.json s7_parity_engine_default_vs_score: max_abs_equity_diff 0.0, exact_equal true, strategy_fills 81==81, entries 41==41 on a different (RA-05 M4_CAL) window -- this run is FP-02's OWN evidence, not a substitute for that one

## FP02-G-CACHE — cross-run reuse + a genuine economic-dependency miss
- first: {'status': 'MISS', 'producer': 'fp02-20260922T180514Z-e4aad0b7-a'}
- reused (different producer, same semantics): {'status': 'HIT', 'producer_of_reused_payload': 'fp02-20260922T180514Z-e4aad0b7-a', 'payload_identical': True}
- changed economics (different fee rate): {'status': 'MISS', 'terminal_equity_changed': True}

## FP02-G-LINEAGE — real multi-selection deployment, pending/activation case
- status: MISS
- switch requested at bar 7200
- activations effected: 2
- fills: 33 total, 33 attributed (0 during a warming/flat sentinel)
- per-activation bar ranges:
  - sentinel:WARMING: bar_range=[0, 511] fills=0
  - fp02-20260922T180514Z-e4aad0b7-initial: bar_range=[511, 7714] fills=30
  - sentinel:WARMING: bar_range=[7714, 8228] fills=0
  - fp02-20260922T180514Z-e4aad0b7-switch: bar_range=[8228, 14400] fills=3

## FP02-G-RESUME — cache-based resume (no search loop exists yet to checkpoint)
- pre-crash statuses: ['MISS', 'MISS']
- post-resume statuses (fresh ComputeCache instance): ['HIT', 'HIT', 'MISS']
- total engine recomputes across BOTH passes: 3 (of 3 unique candidates -- a naive restart would have recomputed all of them twice)

## FP02-G-MEMORY
- budget: 4096 MiB
- per-call peaks: [427.6, 427.6, 427.6, 426.7, 426.7] MiB
- within_budget: True
- not_growing_unboundedly: True
- resource limits applied to this process: {'cpu_limit': '2', 'rlimit_as_gib': 4, 'previous_soft_gib': None}

## Permitted conclusions
- Technical: the common evaluator (candidate + deployment, same underlying qualified route), semantic cache, retention tiers, causality-guarded latency independence and selection-to-fill lineage all exist and are proved on real engine calls over real market bars, not a mocked run.
- Research: NOT_ASSESSED -- no market claim in FP-02.
- Owner review: PENDING; FP-03 needs its own approval (R-18).
