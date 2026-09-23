# FP-04 — Historical forward ledger and parameter regions (fp04-20260923T145511Z-34cb31b6)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp04-20260923T145511Z-34cb31b6
- started_at: 2026-09-23T14:55:11.280141+00:00
- alpha: A-SC, symbol: BTCUSDT, origins: 12 of guide 3.2's ~26-39 research-default target (explicit partial scope, see region_policy.json.origin_grid_scope_note)
- B_search (reused from FP-03's frozen search_policy.json): 256
- fresh engine search-trial calls this run: 0
- origins reused verbatim from .cache (no fresh engine call): ['2021-01-01', '2021-04-01', '2021-07-01', '2021-10-01', '2022-01-01', '2022-04-01', '2022-07-01', '2022-10-01', '2023-01-01', '2023-04-01', '2023-07-01', '2023-10-01']

## Aggregate summary (measured, not asserted -- see Per-origin results for the full per-region breakdown this rolls up)
- origins searched OK / total: 12/12
- total records: 192 = 12 origins x 16 representative_subset_size cap
- matured_forward_record: 192, censored_or_failed_record: 0
- sum of per-origin search-only wall_seconds_measured: 34254.3s (9.52h) over 12 origins, mean 2854.5s/origin
- TOTAL wall clock, launch to report-write (includes region build + forward eval, not just search; verification follows this and adds a few more seconds): started=2026-09-23T14:55:11.280141+00:00, report_written=2026-09-23T15:09:36.095247+00:00
- decay_D_mean_daily_return (IS - forward; positive=worse) over 192 matured records: min=-0.001081, max=0.001022, mean=-0.000045
- positive (worse) decay: 84/192 (43.8%)
- label (forward mean_daily_return) over 192 matured records: min=-0.001059, max=0.001112, mean=0.000010

## Per-origin results
### 2021-01-01
- wf_ok: True, trials: 256/256, wall: 3137.454257s, peak_mib: 1556.5, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2021-01-01.json
- regions built: 16
  - R00: support=45, medoid_trial=83, is_objective_mean=1.9693, forward_mean_daily_return=0.000121, D_mean_daily_return=0.000142 (D=IS-FWD, positive=worse decay)
  - R01: support=22, medoid_trial=181, is_objective_mean=1.8906, forward_mean_daily_return=0.000080, D_mean_daily_return=0.000160 (D=IS-FWD, positive=worse decay)
  - R02: support=34, medoid_trial=234, is_objective_mean=1.7571, forward_mean_daily_return=0.000067, D_mean_daily_return=0.000169 (D=IS-FWD, positive=worse decay)
  - R03: support=4, medoid_trial=255, is_objective_mean=1.8040, forward_mean_daily_return=0.000263, D_mean_daily_return=-0.000035 (D=IS-FWD, positive=worse decay)
  - R04: support=5, medoid_trial=50, is_objective_mean=1.7549, forward_mean_daily_return=0.000316, D_mean_daily_return=-0.000060 (D=IS-FWD, positive=worse decay)
  - R05: support=2, medoid_trial=18, is_objective_mean=1.6453, forward_mean_daily_return=0.000106, D_mean_daily_return=0.000115 (D=IS-FWD, positive=worse decay)
  - R06: support=5, medoid_trial=117, is_objective_mean=1.7840, forward_mean_daily_return=-0.000282, D_mean_daily_return=0.000516 (D=IS-FWD, positive=worse decay)
  - R07: support=3, medoid_trial=49, is_objective_mean=1.5785, forward_mean_daily_return=0.000376, D_mean_daily_return=-0.000220 (D=IS-FWD, positive=worse decay)
  - R08: support=3, medoid_trial=28, is_objective_mean=1.4414, forward_mean_daily_return=0.000460, D_mean_daily_return=-0.000283 (D=IS-FWD, positive=worse decay)
  - R09: support=4, medoid_trial=179, is_objective_mean=1.0054, forward_mean_daily_return=0.000472, D_mean_daily_return=-0.000318 (D=IS-FWD, positive=worse decay)
  - R10: support=5, medoid_trial=25, is_objective_mean=1.1307, forward_mean_daily_return=-0.000038, D_mean_daily_return=0.000158 (D=IS-FWD, positive=worse decay)
  - R11: support=3, medoid_trial=0, is_objective_mean=0.3766, forward_mean_daily_return=-0.000538, D_mean_daily_return=0.000672 (D=IS-FWD, positive=worse decay)
  - R12: support=1, medoid_trial=35, is_objective_mean=1.2235, forward_mean_daily_return=-0.000067, D_mean_daily_return=0.000197 (D=IS-FWD, positive=worse decay)
  - R13: support=4, medoid_trial=4, is_objective_mean=0.1701, forward_mean_daily_return=-0.000115, D_mean_daily_return=0.000083 (D=IS-FWD, positive=worse decay)
  - R14: support=1, medoid_trial=30, is_objective_mean=0.8980, forward_mean_daily_return=0.000490, D_mean_daily_return=-0.000412 (D=IS-FWD, positive=worse decay)
  - R15: support=1, medoid_trial=158, is_objective_mean=0.7681, forward_mean_daily_return=-0.000087, D_mean_daily_return=0.000163 (D=IS-FWD, positive=worse decay)

### 2021-04-01
- wf_ok: True, trials: 256/256, wall: 2903.178604s, peak_mib: 2175.2, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2021-04-01.json
- regions built: 16
  - R00: support=58, medoid_trial=188, is_objective_mean=3.2135, forward_mean_daily_return=-0.000226, D_mean_daily_return=0.000788 (D=IS-FWD, positive=worse decay)
  - R01: support=18, medoid_trial=34, is_objective_mean=2.7278, forward_mean_daily_return=-0.000151, D_mean_daily_return=0.000668 (D=IS-FWD, positive=worse decay)
  - R02: support=6, medoid_trial=179, is_objective_mean=3.0739, forward_mean_daily_return=-0.000254, D_mean_daily_return=0.000777 (D=IS-FWD, positive=worse decay)
  - R03: support=2, medoid_trial=47, is_objective_mean=2.9597, forward_mean_daily_return=-0.000396, D_mean_daily_return=0.000869 (D=IS-FWD, positive=worse decay)
  - R04: support=1, medoid_trial=77, is_objective_mean=2.9872, forward_mean_daily_return=-0.000185, D_mean_daily_return=0.000429 (D=IS-FWD, positive=worse decay)
  - R05: support=12, medoid_trial=84, is_objective_mean=2.3695, forward_mean_daily_return=-0.000422, D_mean_daily_return=0.000825 (D=IS-FWD, positive=worse decay)
  - R06: support=5, medoid_trial=43, is_objective_mean=2.2294, forward_mean_daily_return=-0.000614, D_mean_daily_return=0.000952 (D=IS-FWD, positive=worse decay)
  - R07: support=5, medoid_trial=12, is_objective_mean=2.3829, forward_mean_daily_return=-0.000317, D_mean_daily_return=0.000705 (D=IS-FWD, positive=worse decay)
  - R08: support=1, medoid_trial=60, is_objective_mean=2.4925, forward_mean_daily_return=-0.000208, D_mean_daily_return=0.000607 (D=IS-FWD, positive=worse decay)
  - R09: support=3, medoid_trial=39, is_objective_mean=1.6681, forward_mean_daily_return=-0.000202, D_mean_daily_return=0.000589 (D=IS-FWD, positive=worse decay)
  - R10: support=1, medoid_trial=36, is_objective_mean=2.4057, forward_mean_daily_return=-0.000346, D_mean_daily_return=0.000796 (D=IS-FWD, positive=worse decay)
  - R11: support=4, medoid_trial=46, is_objective_mean=2.1422, forward_mean_daily_return=-0.000348, D_mean_daily_return=0.000755 (D=IS-FWD, positive=worse decay)
  - R12: support=5, medoid_trial=9, is_objective_mean=2.1831, forward_mean_daily_return=-0.000268, D_mean_daily_return=0.000615 (D=IS-FWD, positive=worse decay)
  - R13: support=3, medoid_trial=14, is_objective_mean=2.2173, forward_mean_daily_return=-0.000326, D_mean_daily_return=0.000716 (D=IS-FWD, positive=worse decay)
  - R14: support=1, medoid_trial=16, is_objective_mean=2.0151, forward_mean_daily_return=-0.000322, D_mean_daily_return=0.000643 (D=IS-FWD, positive=worse decay)
  - R15: support=2, medoid_trial=6, is_objective_mean=1.1608, forward_mean_daily_return=-0.000181, D_mean_daily_return=0.000388 (D=IS-FWD, positive=worse decay)

### 2021-07-01
- wf_ok: True, trials: 256/256, wall: 3347.990386s, peak_mib: 2289.6, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2021-07-01.json
- regions built: 16
  - R00: support=24, medoid_trial=101, is_objective_mean=1.2914, forward_mean_daily_return=0.000316, D_mean_daily_return=-0.000156 (D=IS-FWD, positive=worse decay)
  - R01: support=27, medoid_trial=7, is_objective_mean=0.3526, forward_mean_daily_return=0.000212, D_mean_daily_return=-0.000069 (D=IS-FWD, positive=worse decay)
  - R02: support=48, medoid_trial=15, is_objective_mean=0.5528, forward_mean_daily_return=0.000287, D_mean_daily_return=0.000016 (D=IS-FWD, positive=worse decay)
  - R03: support=7, medoid_trial=90, is_objective_mean=0.3709, forward_mean_daily_return=0.000582, D_mean_daily_return=-0.000466 (D=IS-FWD, positive=worse decay)
  - R04: support=6, medoid_trial=55, is_objective_mean=-0.2156, forward_mean_daily_return=0.000617, D_mean_daily_return=-0.000616 (D=IS-FWD, positive=worse decay)
  - R05: support=8, medoid_trial=251, is_objective_mean=0.3700, forward_mean_daily_return=0.000217, D_mean_daily_return=-0.000080 (D=IS-FWD, positive=worse decay)
  - R06: support=1, medoid_trial=20, is_objective_mean=1.0594, forward_mean_daily_return=0.000604, D_mean_daily_return=-0.000355 (D=IS-FWD, positive=worse decay)
  - R07: support=8, medoid_trial=38, is_objective_mean=-0.0060, forward_mean_daily_return=0.000260, D_mean_daily_return=-0.000122 (D=IS-FWD, positive=worse decay)
  - R08: support=7, medoid_trial=130, is_objective_mean=-0.5220, forward_mean_daily_return=0.000394, D_mean_daily_return=-0.000350 (D=IS-FWD, positive=worse decay)
  - R09: support=2, medoid_trial=13, is_objective_mean=0.1867, forward_mean_daily_return=0.000581, D_mean_daily_return=-0.000460 (D=IS-FWD, positive=worse decay)
  - R10: support=1, medoid_trial=29, is_objective_mean=0.0155, forward_mean_daily_return=0.000383, D_mean_daily_return=-0.000339 (D=IS-FWD, positive=worse decay)
  - R11: support=4, medoid_trial=19, is_objective_mean=-1.2218, forward_mean_daily_return=-0.000105, D_mean_daily_return=0.000099 (D=IS-FWD, positive=worse decay)
  - R12: support=1, medoid_trial=2, is_objective_mean=-0.3133, forward_mean_daily_return=0.000224, D_mean_daily_return=-0.000233 (D=IS-FWD, positive=worse decay)
  - R13: support=2, medoid_trial=9, is_objective_mean=-0.7995, forward_mean_daily_return=0.000038, D_mean_daily_return=-0.000100 (D=IS-FWD, positive=worse decay)
  - R14: support=1, medoid_trial=40, is_objective_mean=-0.4076, forward_mean_daily_return=-0.000151, D_mean_daily_return=0.000113 (D=IS-FWD, positive=worse decay)
  - R15: support=2, medoid_trial=5, is_objective_mean=-0.6394, forward_mean_daily_return=0.000390, D_mean_daily_return=-0.000370 (D=IS-FWD, positive=worse decay)

### 2021-10-01
- wf_ok: True, trials: 256/256, wall: 2632.873919s, peak_mib: 2128.3, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2021-10-01.json
- regions built: 16
  - R00: support=44, medoid_trial=32, is_objective_mean=2.0929, forward_mean_daily_return=0.000652, D_mean_daily_return=-0.000413 (D=IS-FWD, positive=worse decay)
  - R01: support=23, medoid_trial=172, is_objective_mean=1.6531, forward_mean_daily_return=0.000578, D_mean_daily_return=-0.000384 (D=IS-FWD, positive=worse decay)
  - R02: support=9, medoid_trial=7, is_objective_mean=0.7400, forward_mean_daily_return=0.000046, D_mean_daily_return=0.000089 (D=IS-FWD, positive=worse decay)
  - R03: support=8, medoid_trial=47, is_objective_mean=1.0124, forward_mean_daily_return=0.000625, D_mean_daily_return=-0.000462 (D=IS-FWD, positive=worse decay)
  - R04: support=11, medoid_trial=78, is_objective_mean=-0.3583, forward_mean_daily_return=0.000195, D_mean_daily_return=-0.000142 (D=IS-FWD, positive=worse decay)
  - R05: support=3, medoid_trial=215, is_objective_mean=-0.6546, forward_mean_daily_return=0.000434, D_mean_daily_return=-0.000394 (D=IS-FWD, positive=worse decay)
  - R06: support=2, medoid_trial=19, is_objective_mean=0.0884, forward_mean_daily_return=0.000078, D_mean_daily_return=-0.000088 (D=IS-FWD, positive=worse decay)
  - R07: support=1, medoid_trial=13, is_objective_mean=-0.2512, forward_mean_daily_return=0.000206, D_mean_daily_return=-0.000256 (D=IS-FWD, positive=worse decay)
  - R08: support=4, medoid_trial=240, is_objective_mean=-1.4141, forward_mean_daily_return=0.000420, D_mean_daily_return=-0.000573 (D=IS-FWD, positive=worse decay)
  - R09: support=1, medoid_trial=60, is_objective_mean=-0.7678, forward_mean_daily_return=0.000157, D_mean_daily_return=-0.000310 (D=IS-FWD, positive=worse decay)
  - R10: support=2, medoid_trial=5, is_objective_mean=-2.6622, forward_mean_daily_return=0.000520, D_mean_daily_return=-0.000724 (D=IS-FWD, positive=worse decay)
  - R11: support=2, medoid_trial=40, is_objective_mean=-1.2405, forward_mean_daily_return=0.000171, D_mean_daily_return=-0.000369 (D=IS-FWD, positive=worse decay)
  - R12: support=2, medoid_trial=9, is_objective_mean=-1.4041, forward_mean_daily_return=0.000148, D_mean_daily_return=-0.000396 (D=IS-FWD, positive=worse decay)
  - R13: support=2, medoid_trial=2, is_objective_mean=-1.8051, forward_mean_daily_return=0.000650, D_mean_daily_return=-0.000983 (D=IS-FWD, positive=worse decay)
  - R14: support=2, medoid_trial=3, is_objective_mean=-2.2382, forward_mean_daily_return=0.000481, D_mean_daily_return=-0.000815 (D=IS-FWD, positive=worse decay)
  - R15: support=3, medoid_trial=93, is_objective_mean=-5.1591, forward_mean_daily_return=-0.000738, D_mean_daily_return=-0.000867 (D=IS-FWD, positive=worse decay)

### 2022-01-01
- wf_ok: True, trials: 256/256, wall: 2716.572414s, peak_mib: 2093.1, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2022-01-01.json
- regions built: 16
  - R00: support=55, medoid_trial=107, is_objective_mean=2.2505, forward_mean_daily_return=-0.000274, D_mean_daily_return=0.000526 (D=IS-FWD, positive=worse decay)
  - R01: support=23, medoid_trial=186, is_objective_mean=2.5753, forward_mean_daily_return=-0.000312, D_mean_daily_return=0.000589 (D=IS-FWD, positive=worse decay)
  - R02: support=3, medoid_trial=238, is_objective_mean=1.3911, forward_mean_daily_return=-0.000567, D_mean_daily_return=0.000759 (D=IS-FWD, positive=worse decay)
  - R03: support=6, medoid_trial=7, is_objective_mean=0.9669, forward_mean_daily_return=-0.000361, D_mean_daily_return=0.000422 (D=IS-FWD, positive=worse decay)
  - R04: support=4, medoid_trial=67, is_objective_mean=0.5016, forward_mean_daily_return=-0.000208, D_mean_daily_return=0.000344 (D=IS-FWD, positive=worse decay)
  - R05: support=2, medoid_trial=94, is_objective_mean=0.4480, forward_mean_daily_return=-0.000537, D_mean_daily_return=0.000646 (D=IS-FWD, positive=worse decay)
  - R06: support=1, medoid_trial=58, is_objective_mean=0.4884, forward_mean_daily_return=-0.000836, D_mean_daily_return=0.000887 (D=IS-FWD, positive=worse decay)
  - R07: support=3, medoid_trial=78, is_objective_mean=-0.1790, forward_mean_daily_return=-0.000249, D_mean_daily_return=0.000280 (D=IS-FWD, positive=worse decay)
  - R08: support=4, medoid_trial=27, is_objective_mean=-0.5752, forward_mean_daily_return=-0.000382, D_mean_daily_return=0.000417 (D=IS-FWD, positive=worse decay)
  - R09: support=5, medoid_trial=88, is_objective_mean=-2.1653, forward_mean_daily_return=-0.000635, D_mean_daily_return=0.000629 (D=IS-FWD, positive=worse decay)
  - R10: support=2, medoid_trial=60, is_objective_mean=-0.7045, forward_mean_daily_return=-0.001059, D_mean_daily_return=0.001022 (D=IS-FWD, positive=worse decay)
  - R11: support=2, medoid_trial=89, is_objective_mean=-0.2848, forward_mean_daily_return=-0.000634, D_mean_daily_return=0.000584 (D=IS-FWD, positive=worse decay)
  - R12: support=2, medoid_trial=9, is_objective_mean=-0.4057, forward_mean_daily_return=-0.000655, D_mean_daily_return=0.000590 (D=IS-FWD, positive=worse decay)
  - R13: support=3, medoid_trial=178, is_objective_mean=-1.6740, forward_mean_daily_return=-0.000901, D_mean_daily_return=0.000806 (D=IS-FWD, positive=worse decay)
  - R14: support=1, medoid_trial=158, is_objective_mean=-1.2982, forward_mean_daily_return=-0.000690, D_mean_daily_return=0.000481 (D=IS-FWD, positive=worse decay)
  - R15: support=1, medoid_trial=2, is_objective_mean=-1.4932, forward_mean_daily_return=-0.000560, D_mean_daily_return=0.000347 (D=IS-FWD, positive=worse decay)

### 2022-04-01
- wf_ok: True, trials: 256/256, wall: 2994.087292s, peak_mib: 2138.5, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2022-04-01.json
- regions built: 16
  - R00: support=2, medoid_trial=254, is_objective_mean=0.9556, forward_mean_daily_return=0.000016, D_mean_daily_return=0.000149 (D=IS-FWD, positive=worse decay)
  - R01: support=15, medoid_trial=244, is_objective_mean=-0.2089, forward_mean_daily_return=-0.000235, D_mean_daily_return=0.000260 (D=IS-FWD, positive=worse decay)
  - R02: support=54, medoid_trial=141, is_objective_mean=-0.5494, forward_mean_daily_return=-0.000078, D_mean_daily_return=0.000088 (D=IS-FWD, positive=worse decay)
  - R03: support=11, medoid_trial=200, is_objective_mean=-0.6104, forward_mean_daily_return=-0.000079, D_mean_daily_return=0.000053 (D=IS-FWD, positive=worse decay)
  - R04: support=3, medoid_trial=14, is_objective_mean=-0.7216, forward_mean_daily_return=-0.000126, D_mean_daily_return=0.000020 (D=IS-FWD, positive=worse decay)
  - R05: support=4, medoid_trial=100, is_objective_mean=-1.6552, forward_mean_daily_return=-0.000526, D_mean_daily_return=0.000387 (D=IS-FWD, positive=worse decay)
  - R06: support=15, medoid_trial=64, is_objective_mean=-1.5223, forward_mean_daily_return=-0.000473, D_mean_daily_return=0.000334 (D=IS-FWD, positive=worse decay)
  - R07: support=1, medoid_trial=65, is_objective_mean=-1.2140, forward_mean_daily_return=-0.000069, D_mean_daily_return=-0.000036 (D=IS-FWD, positive=worse decay)
  - R08: support=2, medoid_trial=38, is_objective_mean=-1.8759, forward_mean_daily_return=-0.000429, D_mean_daily_return=0.000344 (D=IS-FWD, positive=worse decay)
  - R09: support=2, medoid_trial=116, is_objective_mean=-4.8602, forward_mean_daily_return=-0.000878, D_mean_daily_return=0.000732 (D=IS-FWD, positive=worse decay)
  - R10: support=5, medoid_trial=190, is_objective_mean=-2.4397, forward_mean_daily_return=-0.000439, D_mean_daily_return=0.000329 (D=IS-FWD, positive=worse decay)
  - R11: support=1, medoid_trial=247, is_objective_mean=-1.8644, forward_mean_daily_return=-0.000057, D_mean_daily_return=-0.000123 (D=IS-FWD, positive=worse decay)
  - R12: support=2, medoid_trial=16, is_objective_mean=-2.0969, forward_mean_daily_return=-0.000015, D_mean_daily_return=-0.000173 (D=IS-FWD, positive=worse decay)
  - R13: support=5, medoid_trial=146, is_objective_mean=-5.1505, forward_mean_daily_return=-0.000698, D_mean_daily_return=0.000100 (D=IS-FWD, positive=worse decay)
  - R14: support=3, medoid_trial=0, is_objective_mean=-2.1376, forward_mean_daily_return=-0.000140, D_mean_daily_return=-0.000089 (D=IS-FWD, positive=worse decay)
  - R15: support=5, medoid_trial=149, is_objective_mean=-3.1386, forward_mean_daily_return=-0.000534, D_mean_daily_return=0.000353 (D=IS-FWD, positive=worse decay)

### 2022-07-01
- wf_ok: True, trials: 256/256, wall: 2685.41495s, peak_mib: 2079.4, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2022-07-01.json
- regions built: 16
  - R00: support=62, medoid_trial=42, is_objective_mean=-0.5735, forward_mean_daily_return=0.000338, D_mean_daily_return=-0.000374 (D=IS-FWD, positive=worse decay)
  - R01: support=21, medoid_trial=223, is_objective_mean=-0.5360, forward_mean_daily_return=0.000674, D_mean_daily_return=-0.000741 (D=IS-FWD, positive=worse decay)
  - R02: support=3, medoid_trial=50, is_objective_mean=-1.3103, forward_mean_daily_return=0.000476, D_mean_daily_return=-0.000749 (D=IS-FWD, positive=worse decay)
  - R03: support=8, medoid_trial=97, is_objective_mean=-1.3359, forward_mean_daily_return=0.000368, D_mean_daily_return=-0.000591 (D=IS-FWD, positive=worse decay)
  - R04: support=2, medoid_trial=40, is_objective_mean=-1.3743, forward_mean_daily_return=0.000612, D_mean_daily_return=-0.000761 (D=IS-FWD, positive=worse decay)
  - R05: support=4, medoid_trial=140, is_objective_mean=-1.8869, forward_mean_daily_return=0.000011, D_mean_daily_return=-0.000264 (D=IS-FWD, positive=worse decay)
  - R06: support=3, medoid_trial=34, is_objective_mean=-1.6545, forward_mean_daily_return=0.000243, D_mean_daily_return=-0.000532 (D=IS-FWD, positive=worse decay)
  - R07: support=3, medoid_trial=11, is_objective_mean=-1.9801, forward_mean_daily_return=0.000318, D_mean_daily_return=-0.000595 (D=IS-FWD, positive=worse decay)
  - R08: support=4, medoid_trial=244, is_objective_mean=-3.4431, forward_mean_daily_return=0.000085, D_mean_daily_return=-0.000225 (D=IS-FWD, positive=worse decay)
  - R09: support=2, medoid_trial=252, is_objective_mean=-2.0566, forward_mean_daily_return=0.000331, D_mean_daily_return=-0.000628 (D=IS-FWD, positive=worse decay)
  - R10: support=1, medoid_trial=15, is_objective_mean=-2.1086, forward_mean_daily_return=0.000039, D_mean_daily_return=-0.000335 (D=IS-FWD, positive=worse decay)
  - R11: support=4, medoid_trial=0, is_objective_mean=-2.8421, forward_mean_daily_return=0.000545, D_mean_daily_return=-0.000866 (D=IS-FWD, positive=worse decay)
  - R12: support=1, medoid_trial=126, is_objective_mean=-2.7597, forward_mean_daily_return=-0.000195, D_mean_daily_return=-0.000153 (D=IS-FWD, positive=worse decay)
  - R13: support=2, medoid_trial=195, is_objective_mean=-3.9297, forward_mean_daily_return=0.000447, D_mean_daily_return=-0.000953 (D=IS-FWD, positive=worse decay)
  - R14: support=3, medoid_trial=194, is_objective_mean=-4.1391, forward_mean_daily_return=-0.000040, D_mean_daily_return=-0.000510 (D=IS-FWD, positive=worse decay)
  - R15: support=3, medoid_trial=105, is_objective_mean=-4.0345, forward_mean_daily_return=0.000276, D_mean_daily_return=-0.000791 (D=IS-FWD, positive=worse decay)

### 2022-10-01
- wf_ok: True, trials: 256/256, wall: 2906.678439s, peak_mib: 2154.9, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2022-10-01.json
- regions built: 16
  - R00: support=35, medoid_trial=125, is_objective_mean=-1.1853, forward_mean_daily_return=-0.000079, D_mean_daily_return=0.000061 (D=IS-FWD, positive=worse decay)
  - R01: support=22, medoid_trial=212, is_objective_mean=-0.4901, forward_mean_daily_return=-0.000071, D_mean_daily_return=0.000073 (D=IS-FWD, positive=worse decay)
  - R02: support=15, medoid_trial=56, is_objective_mean=-1.5240, forward_mean_daily_return=0.000185, D_mean_daily_return=-0.000248 (D=IS-FWD, positive=worse decay)
  - R03: support=22, medoid_trial=71, is_objective_mean=-2.0497, forward_mean_daily_return=0.000147, D_mean_daily_return=-0.000206 (D=IS-FWD, positive=worse decay)
  - R04: support=10, medoid_trial=94, is_objective_mean=-2.5255, forward_mean_daily_return=0.000127, D_mean_daily_return=-0.000335 (D=IS-FWD, positive=worse decay)
  - R05: support=2, medoid_trial=58, is_objective_mean=-1.7236, forward_mean_daily_return=-0.000037, D_mean_daily_return=-0.000132 (D=IS-FWD, positive=worse decay)
  - R06: support=2, medoid_trial=13, is_objective_mean=-1.6255, forward_mean_daily_return=0.000298, D_mean_daily_return=-0.000477 (D=IS-FWD, positive=worse decay)
  - R07: support=1, medoid_trial=247, is_objective_mean=-1.9362, forward_mean_daily_return=0.000091, D_mean_daily_return=-0.000335 (D=IS-FWD, positive=worse decay)
  - R08: support=1, medoid_trial=46, is_objective_mean=-2.2918, forward_mean_daily_return=-0.000024, D_mean_daily_return=-0.000268 (D=IS-FWD, positive=worse decay)
  - R09: support=1, medoid_trial=100, is_objective_mean=-2.3689, forward_mean_daily_return=0.000031, D_mean_daily_return=-0.000354 (D=IS-FWD, positive=worse decay)
  - R10: support=2, medoid_trial=9, is_objective_mean=-2.4368, forward_mean_daily_return=-0.000166, D_mean_daily_return=-0.000166 (D=IS-FWD, positive=worse decay)
  - R11: support=2, medoid_trial=180, is_objective_mean=-2.9944, forward_mean_daily_return=-0.000271, D_mean_daily_return=-0.000063 (D=IS-FWD, positive=worse decay)
  - R12: support=1, medoid_trial=57, is_objective_mean=-2.6268, forward_mean_daily_return=-0.000028, D_mean_daily_return=-0.000280 (D=IS-FWD, positive=worse decay)
  - R13: support=7, medoid_trial=40, is_objective_mean=-5.3811, forward_mean_daily_return=-0.000481, D_mean_daily_return=-0.000007 (D=IS-FWD, positive=worse decay)
  - R14: support=2, medoid_trial=60, is_objective_mean=-3.7195, forward_mean_daily_return=-0.000424, D_mean_daily_return=-0.000060 (D=IS-FWD, positive=worse decay)
  - R15: support=2, medoid_trial=228, is_objective_mean=-4.1774, forward_mean_daily_return=-0.000367, D_mean_daily_return=-0.000115 (D=IS-FWD, positive=worse decay)

### 2023-01-01
- wf_ok: True, trials: 256/256, wall: 2645.511638s, peak_mib: 2116.0, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2023-01-01.json
- regions built: 16
  - R00: support=49, medoid_trial=22, is_objective_mean=-1.4061, forward_mean_daily_return=0.000450, D_mean_daily_return=-0.000434 (D=IS-FWD, positive=worse decay)
  - R01: support=18, medoid_trial=62, is_objective_mean=-1.5318, forward_mean_daily_return=0.000289, D_mean_daily_return=-0.000298 (D=IS-FWD, positive=worse decay)
  - R02: support=14, medoid_trial=194, is_objective_mean=-0.5916, forward_mean_daily_return=0.001112, D_mean_daily_return=-0.001081 (D=IS-FWD, positive=worse decay)
  - R03: support=2, medoid_trial=47, is_objective_mean=-1.0191, forward_mean_daily_return=0.000987, D_mean_daily_return=-0.000983 (D=IS-FWD, positive=worse decay)
  - R04: support=8, medoid_trial=235, is_objective_mean=-1.3856, forward_mean_daily_return=0.001021, D_mean_daily_return=-0.001076 (D=IS-FWD, positive=worse decay)
  - R05: support=2, medoid_trial=13, is_objective_mean=-1.8168, forward_mean_daily_return=0.000597, D_mean_daily_return=-0.000706 (D=IS-FWD, positive=worse decay)
  - R06: support=13, medoid_trial=161, is_objective_mean=-5.1293, forward_mean_daily_return=0.000048, D_mean_daily_return=-0.000275 (D=IS-FWD, positive=worse decay)
  - R07: support=1, medoid_trial=19, is_objective_mean=-2.7289, forward_mean_daily_return=0.000386, D_mean_daily_return=-0.000660 (D=IS-FWD, positive=worse decay)
  - R08: support=2, medoid_trial=4, is_objective_mean=-4.1160, forward_mean_daily_return=0.000315, D_mean_daily_return=-0.000670 (D=IS-FWD, positive=worse decay)
  - R09: support=1, medoid_trial=193, is_objective_mean=-4.0042, forward_mean_daily_return=0.000391, D_mean_daily_return=-0.000771 (D=IS-FWD, positive=worse decay)
  - R10: support=2, medoid_trial=0, is_objective_mean=-4.3258, forward_mean_daily_return=0.000085, D_mean_daily_return=-0.000473 (D=IS-FWD, positive=worse decay)
  - R11: support=2, medoid_trial=6, is_objective_mean=-4.9965, forward_mean_daily_return=0.000428, D_mean_daily_return=-0.000875 (D=IS-FWD, positive=worse decay)
  - R12: support=1, medoid_trial=5, is_objective_mean=-4.4107, forward_mean_daily_return=0.000547, D_mean_daily_return=-0.001013 (D=IS-FWD, positive=worse decay)
  - R13: support=2, medoid_trial=8, is_objective_mean=-4.7900, forward_mean_daily_return=0.000264, D_mean_daily_return=-0.000697 (D=IS-FWD, positive=worse decay)
  - R14: support=3, medoid_trial=110, is_objective_mean=-5.5595, forward_mean_daily_return=0.000170, D_mean_daily_return=-0.000678 (D=IS-FWD, positive=worse decay)
  - R15: support=3, medoid_trial=59, is_objective_mean=-8.4798, forward_mean_daily_return=0.000118, D_mean_daily_return=-0.000685 (D=IS-FWD, positive=worse decay)

### 2023-04-01
- wf_ok: True, trials: 256/256, wall: 2538.424746s, peak_mib: 2086.5, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2023-04-01.json
- regions built: 16
  - R00: support=29, medoid_trial=212, is_objective_mean=1.9189, forward_mean_daily_return=0.000202, D_mean_daily_return=0.000049 (D=IS-FWD, positive=worse decay)
  - R01: support=36, medoid_trial=44, is_objective_mean=2.2832, forward_mean_daily_return=0.000156, D_mean_daily_return=0.000144 (D=IS-FWD, positive=worse decay)
  - R02: support=6, medoid_trial=59, is_objective_mean=1.2970, forward_mean_daily_return=0.000065, D_mean_daily_return=0.000200 (D=IS-FWD, positive=worse decay)
  - R03: support=11, medoid_trial=16, is_objective_mean=1.4238, forward_mean_daily_return=0.000313, D_mean_daily_return=-0.000151 (D=IS-FWD, positive=worse decay)
  - R04: support=10, medoid_trial=103, is_objective_mean=0.7966, forward_mean_daily_return=0.000106, D_mean_daily_return=-0.000085 (D=IS-FWD, positive=worse decay)
  - R05: support=1, medoid_trial=25, is_objective_mean=1.7493, forward_mean_daily_return=0.000323, D_mean_daily_return=-0.000143 (D=IS-FWD, positive=worse decay)
  - R06: support=2, medoid_trial=20, is_objective_mean=1.2005, forward_mean_daily_return=0.000080, D_mean_daily_return=0.000064 (D=IS-FWD, positive=worse decay)
  - R07: support=3, medoid_trial=221, is_objective_mean=0.2429, forward_mean_daily_return=0.000128, D_mean_daily_return=-0.000032 (D=IS-FWD, positive=worse decay)
  - R08: support=3, medoid_trial=26, is_objective_mean=-0.1916, forward_mean_daily_return=-0.000022, D_mean_daily_return=0.000109 (D=IS-FWD, positive=worse decay)
  - R09: support=1, medoid_trial=17, is_objective_mean=-0.1309, forward_mean_daily_return=-0.000139, D_mean_daily_return=0.000124 (D=IS-FWD, positive=worse decay)
  - R10: support=2, medoid_trial=29, is_objective_mean=-1.4327, forward_mean_daily_return=-0.000117, D_mean_daily_return=0.000084 (D=IS-FWD, positive=worse decay)
  - R11: support=1, medoid_trial=28, is_objective_mean=-0.3593, forward_mean_daily_return=-0.000203, D_mean_daily_return=0.000173 (D=IS-FWD, positive=worse decay)
  - R12: support=2, medoid_trial=34, is_objective_mean=-1.2792, forward_mean_daily_return=-0.000028, D_mean_daily_return=-0.000091 (D=IS-FWD, positive=worse decay)
  - R13: support=3, medoid_trial=105, is_objective_mean=-1.6159, forward_mean_daily_return=0.000032, D_mean_daily_return=-0.000163 (D=IS-FWD, positive=worse decay)
  - R14: support=1, medoid_trial=178, is_objective_mean=-1.8196, forward_mean_daily_return=-0.000234, D_mean_daily_return=-0.000004 (D=IS-FWD, positive=worse decay)
  - R15: support=1, medoid_trial=5, is_objective_mean=-1.8262, forward_mean_daily_return=-0.000084, D_mean_daily_return=-0.000132 (D=IS-FWD, positive=worse decay)

### 2023-07-01
- wf_ok: True, trials: 256/256, wall: 2793.805682s, peak_mib: 2124.3, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2023-07-01.json
- regions built: 16
  - R00: support=57, medoid_trial=108, is_objective_mean=2.8448, forward_mean_daily_return=-0.000344, D_mean_daily_return=0.000686 (D=IS-FWD, positive=worse decay)
  - R01: support=22, medoid_trial=233, is_objective_mean=2.0543, forward_mean_daily_return=-0.000185, D_mean_daily_return=0.000490 (D=IS-FWD, positive=worse decay)
  - R02: support=8, medoid_trial=51, is_objective_mean=1.8513, forward_mean_daily_return=-0.000089, D_mean_daily_return=0.000351 (D=IS-FWD, positive=worse decay)
  - R03: support=11, medoid_trial=199, is_objective_mean=1.5850, forward_mean_daily_return=-0.000218, D_mean_daily_return=0.000432 (D=IS-FWD, positive=worse decay)
  - R04: support=8, medoid_trial=15, is_objective_mean=1.6255, forward_mean_daily_return=-0.000302, D_mean_daily_return=0.000488 (D=IS-FWD, positive=worse decay)
  - R05: support=2, medoid_trial=178, is_objective_mean=1.1831, forward_mean_daily_return=-0.000198, D_mean_daily_return=0.000389 (D=IS-FWD, positive=worse decay)
  - R06: support=2, medoid_trial=219, is_objective_mean=1.5703, forward_mean_daily_return=-0.000278, D_mean_daily_return=0.000432 (D=IS-FWD, positive=worse decay)
  - R07: support=5, medoid_trial=22, is_objective_mean=0.6685, forward_mean_daily_return=-0.000293, D_mean_daily_return=0.000382 (D=IS-FWD, positive=worse decay)
  - R08: support=1, medoid_trial=17, is_objective_mean=0.9694, forward_mean_daily_return=-0.000330, D_mean_daily_return=0.000424 (D=IS-FWD, positive=worse decay)
  - R09: support=3, medoid_trial=190, is_objective_mean=0.2546, forward_mean_daily_return=-0.000279, D_mean_daily_return=0.000288 (D=IS-FWD, positive=worse decay)
  - R10: support=1, medoid_trial=5, is_objective_mean=0.0029, forward_mean_daily_return=-0.000515, D_mean_daily_return=0.000482 (D=IS-FWD, positive=worse decay)
  - R11: support=1, medoid_trial=39, is_objective_mean=-0.0455, forward_mean_daily_return=-0.000418, D_mean_daily_return=0.000401 (D=IS-FWD, positive=worse decay)
  - R12: support=4, medoid_trial=49, is_objective_mean=-0.3536, forward_mean_daily_return=-0.000362, D_mean_daily_return=0.000336 (D=IS-FWD, positive=worse decay)
  - R13: support=2, medoid_trial=10, is_objective_mean=-0.2923, forward_mean_daily_return=-0.000517, D_mean_daily_return=0.000476 (D=IS-FWD, positive=worse decay)
  - R14: support=2, medoid_trial=35, is_objective_mean=-0.2650, forward_mean_daily_return=-0.000278, D_mean_daily_return=0.000239 (D=IS-FWD, positive=worse decay)
  - R15: support=2, medoid_trial=7, is_objective_mean=-1.5758, forward_mean_daily_return=-0.000219, D_mean_daily_return=0.000190 (D=IS-FWD, positive=worse decay)

### 2023-10-01
- wf_ok: True, trials: 256/256, wall: 2952.336294s, peak_mib: 2151.5, reused_from_cache: /root/bobby/pool_alpha/lab_regime_model_quantbt/.cache/fp04_search_raw/origin_2023-10-01.json
- regions built: 16
  - R00: support=50, medoid_trial=26, is_objective_mean=-1.3547, forward_mean_daily_return=0.000040, D_mean_daily_return=-0.000079 (D=IS-FWD, positive=worse decay)
  - R01: support=18, medoid_trial=219, is_objective_mean=-0.5886, forward_mean_daily_return=0.000506, D_mean_daily_return=-0.000563 (D=IS-FWD, positive=worse decay)
  - R02: support=21, medoid_trial=211, is_objective_mean=-1.0527, forward_mean_daily_return=0.000494, D_mean_daily_return=-0.000554 (D=IS-FWD, positive=worse decay)
  - R03: support=2, medoid_trial=19, is_objective_mean=-0.9515, forward_mean_daily_return=0.000010, D_mean_daily_return=-0.000067 (D=IS-FWD, positive=worse decay)
  - R04: support=3, medoid_trial=87, is_objective_mean=-2.6894, forward_mean_daily_return=0.000070, D_mean_daily_return=-0.000388 (D=IS-FWD, positive=worse decay)
  - R05: support=2, medoid_trial=213, is_objective_mean=-2.2856, forward_mean_daily_return=0.000199, D_mean_daily_return=-0.000321 (D=IS-FWD, positive=worse decay)
  - R06: support=1, medoid_trial=13, is_objective_mean=-1.7661, forward_mean_daily_return=0.000239, D_mean_daily_return=-0.000360 (D=IS-FWD, positive=worse decay)
  - R07: support=2, medoid_trial=220, is_objective_mean=-2.4528, forward_mean_daily_return=0.000232, D_mean_daily_return=-0.000373 (D=IS-FWD, positive=worse decay)
  - R08: support=6, medoid_trial=145, is_objective_mean=-5.1660, forward_mean_daily_return=0.000220, D_mean_daily_return=-0.000366 (D=IS-FWD, positive=worse decay)
  - R09: support=2, medoid_trial=210, is_objective_mean=-2.5764, forward_mean_daily_return=0.000131, D_mean_daily_return=-0.000309 (D=IS-FWD, positive=worse decay)
  - R10: support=4, medoid_trial=85, is_objective_mean=-6.1885, forward_mean_daily_return=-0.000094, D_mean_daily_return=-0.000041 (D=IS-FWD, positive=worse decay)
  - R11: support=2, medoid_trial=29, is_objective_mean=-3.4186, forward_mean_daily_return=0.000185, D_mean_daily_return=-0.000402 (D=IS-FWD, positive=worse decay)
  - R12: support=1, medoid_trial=21, is_objective_mean=-3.1742, forward_mean_daily_return=0.000183, D_mean_daily_return=-0.000417 (D=IS-FWD, positive=worse decay)
  - R13: support=3, medoid_trial=5, is_objective_mean=-3.8991, forward_mean_daily_return=0.000018, D_mean_daily_return=-0.000381 (D=IS-FWD, positive=worse decay)
  - R14: support=7, medoid_trial=67, is_objective_mean=-3.9400, forward_mean_daily_return=0.000167, D_mean_daily_return=-0.000402 (D=IS-FWD, positive=worse decay)
  - R15: support=2, medoid_trial=25, is_objective_mean=-3.6969, forward_mean_daily_return=0.000260, D_mean_daily_return=-0.000532 (D=IS-FWD, positive=worse decay)

## Support summary (guide FP04-G-SUPPORT)
- model_ready_count: 155 (matured AND region_support_within_origin >= 2)
- descriptive_only_count: 37
- reason for the threshold: a matured record needs >= 2 region members (within its own origin) before FP-05 may treat it as model-ready evidence rather than a single-candidate descriptive point -- guide 7.4: 'Region ít support được shrink/fallback theo policy, không được mô tả là stable chỉ vì có một candidate tốt'

## Frozen region policy
```json
{
  "schema": "regime_lab.fp04_region_policy.v1",
  "alpha_id": "A-SC",
  "symbol": "BTCUSDT",
  "origin_grid": [
    "2021-01-01",
    "2021-04-01",
    "2021-07-01",
    "2021-10-01",
    "2022-01-01",
    "2022-04-01",
    "2022-07-01",
    "2022-10-01",
    "2023-01-01",
    "2023-04-01",
    "2023-07-01",
    "2023-10-01"
  ],
  "origin_grid_scope_note": "12 of the guide 3.2 research-default target of ~26-39 blocks -- quarterly (Jan/Apr/Jul/Oct 1) across 2021-2023, the same three development-role years FP-03's CALIBRATION_ORIGINS already used. Explicit, disclosed partial coverage per guide 16's own closing permission ('Thi\u1ebfu s\u1ed1 origins cho model kh\u00f4ng l\u00e0m archive v\u00f4 gi\u00e1 tr\u1ecb, nh\u01b0ng kh\u00f4ng \u0111\u01b0\u1ee3c g\u1ecdi model study ho\u00e0n t\u1ea5t'); FP04-T07's incremental-rebuild guarantee means extending this grid later costs only the INCREMENTAL new origins.",
  "b_search": 256,
  "b_search_source": "configs/forward_persistence_fp_v1/search_policy.json (FP-03's own frozen depth, reused verbatim)",
  "search_seed": 20260922,
  "train_memory_days": 180,
  "forward_horizon_days": 28,
  "distance_threshold": 0.12,
  "distance_threshold_reason": "Gower-like normalised distance (selector.schema_distance.ParamSchema.distance) averaged over A-SC's 3 active ordinal dimensions; 0.12 keeps candidates within roughly one declared step of each other in the same region -- a design choice, not a guide-specified number, frozen before any origin's real clustering result is seen",
  "representative_subset_size": 16,
  "representative_subset_size_source": "configs/forward_persistence_fp_v1/search_policy.json (FP-03's own frozen cap, reused verbatim)",
  "geometry_version": "3e025b00d7955796",
  "window_overlaps": {
    "2021-01-01": {
      "train_window_overlaps_with": [
        "2021-04-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2021-04-01": {
      "train_window_overlaps_with": [
        "2021-01-01",
        "2021-07-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2021-07-01": {
      "train_window_overlaps_with": [
        "2021-04-01",
        "2021-10-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2021-10-01": {
      "train_window_overlaps_with": [
        "2021-07-01",
        "2022-01-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2022-01-01": {
      "train_window_overlaps_with": [
        "2021-10-01",
        "2022-04-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2022-04-01": {
      "train_window_overlaps_with": [
        "2022-01-01",
        "2022-07-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2022-07-01": {
      "train_window_overlaps_with": [
        "2022-04-01",
        "2022-10-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2022-10-01": {
      "train_window_overlaps_with": [
        "2022-07-01",
        "2023-01-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2023-01-01": {
      "train_window_overlaps_with": [
        "2022-10-01",
        "2023-04-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2023-04-01": {
      "train_window_overlaps_with": [
        "2023-01-01",
        "2023-07-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2023-07-01": {
      "train_window_overlaps_with": [
        "2023-04-01",
        "2023-10-01"
      ],
      "forward_window_overlaps_with": []
    },
    "2023-10-01": {
      "train_window_overlaps_with": [
        "2023-07-01"
      ],
      "forward_window_overlaps_with": []
    }
  },
  "frozen_at_utc": "2026-09-23T14:55:11.291160+00:00"
}
```

## Glossary
- **region** (a guide 7.3 cluster of real search candidates whose PARAMETERS are close together, by selector.schema_distance.ParamSchema.distance -- built here per origin, from that origin's own real trial pool)
- **medoid** (the region's REAL member candidate minimising total distance to the region's other members -- never an invented centroid; this module's region_medoid)
- **maturity_state** (which of guide 16's five distinctions a ledger record currently carries -- see forward_ledger.py's module docstring for FP-04's operational definition of each)
- **matured_forward_record** (a record whose forward window has closed AND produced a valid forward metric -- the ONLY state a learner may read, guide item 6)
- **censored_or_failed_record** (an origin search or forward evaluation that failed or could not produce a valid metric -- label stays null with a reason, never zero)
- **decay** (D_mean_daily_return = IS mean daily return - forward mean daily return; positive is WORSE decay, guide 8.5's D formula, this run's diagnostic field, NOT the primary FP-05 target)
- **origin** (one historical point in time at which a real search was run from permitted past data only -- guide 7's chronological origin grid)
- **support** (region_support_within_origin: how many of an origin's OWN real search candidates fell into a given region -- guide 7.5 forbids treating this as a cross-origin count)

## Permitted conclusions
- Technical: a real historical forward ledger was built at 12 real chronological origins, region geometry from real search candidates (params only, causality proved by FP04-T01-T04), forward evaluation on real IS/forward windows, maturity/censorship states derived per guide 16, origin weighting proved equal-per-origin (FP04-T06), incremental rebuild proved to skip the engine on existing valid origins (FP04-T07/T08).
- Research: NOT_ASSESSED -- FP-04 builds the archive; it makes no market/edge claim and compares no arms (that is FP-05 onward).
- Scope: 12 of ~26-39 origins -- an explicit, disclosed partial archive, extensible without recomputation (see origin_grid_scope_note above).
- Owner review: PENDING; FP-05 needs its own approval (R-18).
