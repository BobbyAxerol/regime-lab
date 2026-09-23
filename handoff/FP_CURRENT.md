# FP_CURRENT

## Current source
- FP-01: PASS (evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/)
- FP-02: run fp02-20260922T180514Z-e4aad0b7 (/root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7)
- FP-02 overall: PASS
- FP-02 gates: FP02-G-PARITY=PASS / FP02-G-CACHE=PASS / FP02-G-LATENCY=PASS / FP02-G-MEMORY=PASS / FP02-G-LINEAGE=PASS / FP02-G-RESUME=PASS
- FP-03: run fp03-20260922T211626Z-6bf07360 (evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/)
- FP-03 overall: PASS
- FP-03 gates: FP03-G-SCHEMA=PASS / FP03-G-PREFIX=PASS / FP03-G-COVERAGE=PASS / FP03-G-CURVE=PASS / FP03-G-FREEZE=PASS
- FP-04: run fp04-20260923T145511Z-34cb31b6 (evidence/forward_persistence_fp_v1/fp04-20260923T145511Z-34cb31b6/; the real-compute run is preserved separately at fp04-20260923T034316Z-7443308d, same content, superseded only for its report's aggregate-summary section)
- FP-04 overall: PASS
- FP-04 gates: FP04-G-LEDGER=PASS / FP04-G-CAUSAL=PASS / FP04-G-REGION=PASS / FP04-G-SUPPORT=PASS / FP04-G-REUSE=PASS

## Phase state
| Phase | Technical | Research | Owner | Evidence |
|---|---|---|---|---|
| FP-01 | PASS | NOT_ASSESSED | PENDING | evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/ |
| FP-02 | PASS | NOT_ASSESSED | PENDING (needs R-18 approval) | evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7/ |
| FP-03 | PASS | NOT_ASSESSED | PENDING (auto-advance pre-approved, R-18 2026-09-22) | evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/ |
| FP-04 | PASS | NOT_ASSESSED | PENDING (auto-advance pre-approved, R-18 2026-09-22) | evidence/forward_persistence_fp_v1/fp04-20260923T145511Z-34cb31b6/ |

## Latest run
FP-04 PASS: historical forward ledger built at 12 real chronological origins (quarter-start dates,
2021-01-01 .. 2023-10-01), each a REAL 256/256-trial `run_cutoff_walk_forward` search (B_search
reused verbatim from FP-03's frozen search_policy.json) + real region clustering (params-only Gower
distance, `distance_threshold=0.12`) + real forward evaluation of every region's medoid (up to 16
per origin, the frozen `representative_subset_size` cap). All 12/12 origins reached `wf_ok=True`;
every origin hit the 16-region cap (real clustering found >16 distinct regions every time).

**Real measured numbers** (from the verified evidence, not asserted):
- 3072 fresh engine search-trial calls (12 × 256), 0 reused (first-ever run of this grid).
- Sum of per-origin search-only wall time: 34254.3s (9.52h) over 12 origins, mean 2854.5s/origin
  (~47.6 min); range 2538.4s (2023-04-01) to 3348.0s (2021-07-01).
- Peak RSS per origin: 1556.5-2289.6 MiB, all against the 4096 MiB budget, no monotonic growth
  across origins (varies with each window's real data volume).
- 192 ledger records (12 origins × 16 regions). **192/192 matured_forward_record, 0 censored** — no
  forward window hit a data gap or a `ContractError` across the whole grid.
- 155 model-ready (matured AND region_support_within_origin >= 2), 37 descriptive-only
  (single-candidate regions).
- `decay_D_mean_daily_return` (IS − forward; positive = worse) over the 192 matured records:
  min=-0.001081, max=0.001022, **mean=-0.000045** (slightly negative — i.e. forward was, on
  average, marginally BETTER than IS at this region-medoid granularity); 84/192 (43.8%) individual
  records still show positive (worse) decay. This is a DIFFERENT shape from FP-03's finding (decay
  positive at every checkpoint of every origin) because FP-03 measured decay for the single BEST
  search candidate per origin, while FP-04 measures it across EVERY kept region's medoid, including
  many with thin support — not a contradiction, a different population.
- TOTAL wall clock for the real build: **11h08m38s** (launch 2026-09-23T03:43:16Z, verified
  2026-09-23T14:51:54Z) — this is the SUCCESSFUL relaunch only; see "Operational incident" below for
  the full episode including a first attempt that was killed.
- compute-cache/fp04: 384 real cached evaluate_candidate calls (12 × 16 × 2), 4.3 GiB, git-compressed
  to ~400 MiB.

## Operational incident, disclosed in full (2026-09-22/23)
The FIRST launch of the real 12-origin build (22:46 UTC 2026-09-22, `run_in_background`) was
**killed** after ~5 hours with **0/12 origins completed** — verified via empty
`.cache/fp04_search_raw/`, no OOM event in `dmesg`/`journalctl` near that window (machine uptime
unbroken, 10 days), and a brand-new `claude` CLI process tree starting at 03:38 UTC 2026-09-23 —
i.e. the interactive session that launched the background task ended (terminal/IDE closed or
recycled) and took its child process with it. Not an application bug, not an OOM, not a resource
budget breach; a background task tied to a session's process tree dies with that session. Zero
progress was lost (nothing had completed), but ~5 hours of wall-clock produced nothing. Relaunched
at 03:43 UTC 2026-09-23 with `setsid nohup ... & disown` (confirmed PPID=1, own session, fully
detached) so a repeat session interruption would not kill it again; this second launch ran the full
11h08m to completion undisturbed. **Total wall-clock from the very first launch attempt to verified
completion: ~16 hours**, of which ~5 were wasted to the session-death incident.

## Dieu da biet tu evidence
- report_level audit vs score is equity-exact on FP-02's OWN real candidate, not only cited from FUP-04's window (route_parity.json).
- A real multi-selection deployment shows the activation delay applies to the INITIAL version too, not only switches (WARMING sentinel before bar 0's version ever decides) -- lineage_demo.json.
- Cross-run cache reuse and cache-based resume both hold on the real evaluator (cache_reuse.json, resume_demo.json).
- Optuna 4.8.0 is actually installed (guide's own source cites 4.2.1 -- disclosed mismatch); `TPESampler(seed=...)` with all other args default, `n_startup_trials=10` confirmed both from `inspect.signature` and an empirical ask/tell demonstration.
- The stock per-trial objective is `mean_is` (mean shard-IS Sharpe, trade-count-penalized), computed INSIDE the engine -- not independently reproducible outside `run_cutoff_walk_forward`, so FP-03/04 never hand-roll a substitute.
- The incremental-rebuild design (FP04-T07/T08) is now proven on the REAL 12-origin grid, not just synthetic tests: a full re-run of `run_fp04.py` after the report enhancement hit 0 fresh engine calls and reused all 12 origins verbatim (resource_budget.json), completing in 14m26s instead of ~11h.

## Dieu chua biet
- Sampler-state resume (Optuna) is unmeasured -- no search loop needed it yet.
- Whether B_search=256 (or a lower committed depth) generalizes to alphas/symbols beyond A-SC/BTCUSDT -- FP-03/04 are a single-cell pilot, matching this lab's established A-SC-first pilot order; full-matrix replication is FP-08's job (guide "Replication scope"), not before.
- FP-04's ledger has 12 of the guide's ~26-39-origin research-default target — confirmed sufficient to build and pass the archive's own gates (155 model-ready records), but not yet known whether it is enough for FP-05's actual model fit (chronological train/validate split needs multiple held-out origins).
- Whether the region-medoid-level decay finding (mean slightly negative) is a real effect or noise at this granularity — FP-04 makes no such claim (research status NOT_ASSESSED); that judgment belongs to FP-05 onward's registered endpoint comparison.

## Corrections made after FP-03 was committed (2026-09-22, before FP-04 build)
- **A real regression, self-caught before it could propagate**: `checkpoint_search.run_origin_search` had silently stopped measuring/returning `wall_seconds_measured`/`instrumentation` (the `Stage`/timer wrapping was missing from the function actually on disk). FP-03's own committed evidence still shows real numbers only because all 3 of its origins happened to hit a stale `.cache/fp03_search_raw/*.json` file written by an EARLIER, still-working version of the function -- a fresh (non-cached) call would have silently written `None`. Found while auditing FP-03 before reusing `run_origin_search` for FP-04's 12 brand-new (never-cached) origins. Fixed with the `Stage` wrapper restored + a new regression test (`test_fp03_run_origin_search_measures_real_wall_and_instrumentation`, a real small 2-trial engine call) that would have caught this the first time. FP-03's own published numbers are unaffected (they came from the real measured run); only the CODE's reproducibility was at risk.

## Corrections made during FP-04's own build (2026-09-23, before any real engine call)
- **A vacuous gate, caught by its own regression test failing for the wrong reason**: `ledger_record()` originally reformatted `origin_cutoff` through `origin_ts.isoformat()`, which silently stopped string-matching `origin_ledger.json`'s own plain-date `origin_cutoff` field. This made `FP04-G-CAUSAL`'s cross-origin-leak check vacuous -- it would never have fired on the real run either, since the dict lookup it depends on always missed. Fixed to keep `origin_cutoff` as the plain join key and `origin_time` as the qualified timestamp; `verifier_fp04.py`'s own `label_available_at` re-derivation was fixed to normalise tz on both sides accordingly.
- Three test-fixture bugs (wrong expected medoid in a hand-built fixture, an `as_of` date miscalculated relative to the 28-day horizon, a float-format assumption) and one real `training_view` bug (did not normalise `decision_time` to tz-aware before calling `fp.chronology.chronological_split`, raising `TypeError` on a naive input) -- all found and fixed before the real build, full suite 1340/1340 passed.

## Blockers
- None recorded for FP-04 at this evidence.

## Budget
- FP-02 charged 0 to the shared TE ledger; ~16 small real engine calls, all on a 10-day/1m real window.
- FP-03 charged 0 to the shared TE ledger; 768 real search-trial engine calls (256 × 3 origins) plus forward-comparison calls, all real A-SC/BTCUSDT windows.
- FP-04 charged 0 to the shared TE ledger; 3072 real search-trial engine calls (256 × 12 origins) plus 384 real forward-evaluation engine calls, all real A-SC/BTCUSDT windows. Peak RSS never exceeded 2289.6 MiB against the 4096 MiB budget across any of the 12 origins.

## FP-04 scope decision (frozen before any FP-04 engine call, disclosed here per CLAUDE.md rule 4)
Guide 3.2's research-default target for the eventual outer/model study is ~26-39 origins ("blocks 28
ngày"). At FP-03's measured real cost (~43-51 min per 256-trial/180-day origin, B_search=256 now
frozen), the full target would cost ~19.5-29 hours of strictly-sequential (workers=1) engine
wall-clock -- roughly 6-10x LAB-08's ~3-hour factorial, the largest prior real-engine commitment
anywhere else in this lab's history. FP-04 froze a **12-origin** grid instead: quarter-start dates
(Jan/Apr/Jul/Oct 1) across 2021-2023, the same three development-role years FP-03's own
CALIBRATION_ORIGINS already used, extended to quarterly density. Measured real cost: 9.52h of search
alone (34254.3s), ~11.15h total including region-build/forward-eval/write/verify -- close to the
original ~9-10.5h projection. This is an EXPLICIT, disclosed partial scope, not a silent
under-provision -- guide 16's own closing sentence permits it directly ("Thiếu số origins cho model
không làm archive vô giá trị, nhưng không được gọi model study hoàn tất": a short origin count does
not invalidate the archive, but the MODEL STUDY built on it -- FP-05 onward -- may not be called
complete from this alone). FP-04's own incremental-rebuild guarantee (FP04-T07/T08, tested AND now
proven on the real grid: a full re-run hit 0 fresh engine calls) means growing this grid later toward
the full 26-39 target costs only the INCREMENTAL new origins, never a redo of these 12.

## Next authorized action
- FP-04 is COMPLETE and committed. FP-05 (guide 17, Selector B — forward-persistent selection, no
  regime) is next, already pre-approved alongside FP-03/04 per the recorded owner decision, but has
  not been started -- no FP-05 code, no FP-05 evidence exists yet.

## Khong duoc lam
- No bulk search beyond the frozen B_search=256 without a new search_policy.json revision.
- No economics change without a new upgrade record.
- No silent expansion of the FP-04 origin grid beyond the frozen 12 without disclosing it as a policy revision first.
- No FP-05 claim of "model study complete" citing only FP-04's 12-origin archive (guide 16's own limit).
