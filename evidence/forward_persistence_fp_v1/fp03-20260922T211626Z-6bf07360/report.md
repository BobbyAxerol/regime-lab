# FP-03 — Search-space qualification and learning curve (fp03-20260922T211626Z-6bf07360)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360
- started_at: 2026-09-22T21:16:26.844722+00:00
- alpha: A-SC, calibration origins: ['2021-06-01', '2022-06-01', '2023-06-01']
- real search-trial engine calls: 768

## FP03.1 — Schema qualification
- schema mapping consistent: True
- unknown-value probes correctly rejected: True
- behavioral fixtures (real engine, real window):
  - coeff (2 vs 7): BEHAVIOR_DIFFERS
  - AP (10 vs 45): BEHAVIOR_DIFFERS
  - alpha.condition_threshold (35 vs 75): BEHAVIOR_DIFFERS

## FP03.2/03.3 — Calibration origins and checkpoint search
### 2021-06-01
- wf_ok: True, error: None, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp03_search_raw/origin_2021-06-01.json
- trials: 256/256 requested, wall: 2786.6281351340003s, peak_mib: 1483.3
  - checkpoint 32: selected trial 22 obj=1.8758, raw_coverage=0.00649, startup/adaptive=10/22, unique=32, est_wall=348.065s
  - checkpoint 64: selected trial 41 obj=2.0583, raw_coverage=0.01299, startup/adaptive=10/54, unique=63, est_wall=696.13s
  - checkpoint 128: selected trial 123 obj=2.8184, raw_coverage=0.02597, startup/adaptive=10/118, unique=103, est_wall=1392.259s
  - checkpoint 256: selected trial 123 obj=2.8184, raw_coverage=0.05195, startup/adaptive=10/246, unique=140, est_wall=2784.519s

### 2022-06-01
- wf_ok: True, error: None, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp03_search_raw/origin_2022-06-01.json
- trials: 256/256 requested, wall: 2575.2765379450284s, peak_mib: 1474.7
  - checkpoint 32: selected trial 31 obj=-0.6698, raw_coverage=0.00649, startup/adaptive=10/22, unique=28, est_wall=321.639s
  - checkpoint 64: selected trial 40 obj=0.4300, raw_coverage=0.01299, startup/adaptive=10/54, unique=57, est_wall=643.277s
  - checkpoint 128: selected trial 94 obj=0.8627, raw_coverage=0.02597, startup/adaptive=10/118, unique=97, est_wall=1286.554s
  - checkpoint 256: selected trial 94 obj=0.8627, raw_coverage=0.05195, startup/adaptive=10/246, unique=130, est_wall=2573.108s

### 2023-06-01
- wf_ok: True, error: None, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp03_search_raw/origin_2023-06-01.json
- trials: 256/256 requested, wall: 3042.20975381101s, peak_mib: 1520.0
  - checkpoint 32: selected trial 20 obj=2.8913, raw_coverage=0.00649, startup/adaptive=10/22, unique=30, est_wall=379.969s
  - checkpoint 64: selected trial 20 obj=2.8913, raw_coverage=0.01299, startup/adaptive=10/54, unique=59, est_wall=759.937s
  - checkpoint 128: selected trial 67 obj=3.4443, raw_coverage=0.02597, startup/adaptive=10/118, unique=104, est_wall=1519.874s
  - checkpoint 256: selected trial 67 obj=3.4443, raw_coverage=0.05195, startup/adaptive=10/246, unique=149, est_wall=3039.748s

## FP03.4 — Forward comparison (IS vs forward, real engine both sides)
### 2021-06-01
  - checkpoint 32: IS obj=1.8758 (Δ vs prior=None), forward mean_daily_return=-0.000156 (Δ vs prior=None), D_mean_daily_return=0.000442 (D=IS-FWD, positive=worse decay), incremental_est_wall=n/a
  - checkpoint 64: IS obj=2.0583 (Δ vs prior=0.18249794739733938), forward mean_daily_return=-0.000377 (Δ vs prior=-0.0002218078311361112), D_mean_daily_return=0.000694 (D=IS-FWD, positive=worse decay), incremental_est_wall=348.065s
  - checkpoint 128: IS obj=2.8184 (Δ vs prior=0.7600506443966806), forward mean_daily_return=0.000245 (Δ vs prior=0.0006224667912887985), D_mean_daily_return=0.000208 (D=IS-FWD, positive=worse decay), incremental_est_wall=696.129s
  - checkpoint 256: IS obj=2.8184 (Δ vs prior=0.0), forward mean_daily_return=0.000245 (Δ vs prior=0.0), D_mean_daily_return=0.000208 (D=IS-FWD, positive=worse decay), incremental_est_wall=1392.2599999999998s

### 2022-06-01
  - checkpoint 32: IS obj=-0.6698 (Δ vs prior=None), forward mean_daily_return=-0.000871 (Δ vs prior=None), D_mean_daily_return=0.000789 (D=IS-FWD, positive=worse decay), incremental_est_wall=n/a
  - checkpoint 64: IS obj=0.4300 (Δ vs prior=1.0997947773918424), forward mean_daily_return=-0.000728 (Δ vs prior=0.0001427186522463083), D_mean_daily_return=0.000771 (D=IS-FWD, positive=worse decay), incremental_est_wall=321.63800000000003s
  - checkpoint 128: IS obj=0.8627 (Δ vs prior=0.4327437051120222), forward mean_daily_return=-0.000671 (Δ vs prior=5.6989164561630184e-05), D_mean_daily_return=0.000778 (D=IS-FWD, positive=worse decay), incremental_est_wall=643.277s
  - checkpoint 256: IS obj=0.8627 (Δ vs prior=0.0), forward mean_daily_return=-0.000671 (Δ vs prior=0.0), D_mean_daily_return=0.000778 (D=IS-FWD, positive=worse decay), incremental_est_wall=1286.554s

### 2023-06-01
  - checkpoint 32: IS obj=2.8913 (Δ vs prior=None), forward mean_daily_return=0.000254 (Δ vs prior=None), D_mean_daily_return=0.000025 (D=IS-FWD, positive=worse decay), incremental_est_wall=n/a
  - checkpoint 64: IS obj=2.8913 (Δ vs prior=0.0), forward mean_daily_return=0.000254 (Δ vs prior=0.0), D_mean_daily_return=0.000025 (D=IS-FWD, positive=worse decay), incremental_est_wall=379.968s
  - checkpoint 128: IS obj=3.4443 (Δ vs prior=0.5529395960866217), forward mean_daily_return=0.000105 (Δ vs prior=-0.0001493604266266217), D_mean_daily_return=0.000243 (D=IS-FWD, positive=worse decay), incremental_est_wall=759.937s
  - checkpoint 256: IS obj=3.4443 (Δ vs prior=0.0), forward mean_daily_return=0.000105 (Δ vs prior=0.0), D_mean_daily_return=0.000243 (D=IS-FWD, positive=worse decay), incremental_est_wall=1519.874s

## FP03.5 — Frozen search policy
```json
{
  "schema": "regime_lab.fp03_search_policy.v1",
  "B_search": 256,
  "Q_probe": 0,
  "representative_subset_size": 16,
  "startup_exploration_policy": "optuna.samplers.TPESampler default (n_startup_trials=10, random sampling before it, TPE-guided after -- verified empirically on this install, not assumed from documentation)",
  "pruning_policy": "none (stock Mode 4's own walk_forward call constructs no pruner beyond Optuna's own defaults; verified from installed source, not assumed)",
  "seed_policy": "one fixed seed (20260922) per calibration origin this phase; seed-randomness replication is not in FP-03's scope (guide 3.2: 'Initial optimizer seed count: m\u1ed9t seed trong discovery')",
  "calibration_origins": [
    "2021-06-01",
    "2022-06-01",
    "2023-06-01"
  ],
  "train_memory_days": 180,
  "engine_report_level_used": "score",
  "engine_report_level_reason": "engine default profile hit a real, RLIMIT_AS-caught MemoryError on this exact scale (~300k-bar train window); score is FUP-04-proven equity-exact",
  "blocker": null,
  "frozen_at_utc": "2026-09-22T21:17:24.757665+00:00"
}
```

## Permitted conclusions
- Technical: schema qualified, sequential-prefix checkpoints extracted from real engine search history, forward comparison computed on real IS/forward candidate evaluations, budget frozen from measured affordability.
- Research: NOT_ASSESSED -- no market/edge claim in FP-03; forward-vs-IS numbers describe search-depth behavior on calibration data only.
- Owner review: PENDING; FP-04 needs its own approval (R-18).
