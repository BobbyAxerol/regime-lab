# FP_CURRENT

## Current source
- FP-01: PASS (evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/)
- FP-02: run fp02-20260922T180514Z-e4aad0b7 (/root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7)
- FP-02 overall: PASS
- FP-02 gates: FP02-G-PARITY=PASS / FP02-G-CACHE=PASS / FP02-G-LATENCY=PASS / FP02-G-MEMORY=PASS / FP02-G-LINEAGE=PASS / FP02-G-RESUME=PASS
- FP-03: run fp03-20260922T211626Z-6bf07360 (evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/)
- FP-03 overall: PASS
- FP-03 gates: FP03-G-SCHEMA=PASS / FP03-G-PREFIX=PASS / FP03-G-COVERAGE=PASS / FP03-G-CURVE=PASS / FP03-G-FREEZE=PASS

## Phase state
| Phase | Technical | Research | Owner | Evidence |
|---|---|---|---|---|
| FP-01 | PASS | NOT_ASSESSED | PENDING | evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/ |
| FP-02 | PASS | NOT_ASSESSED | PENDING (needs R-18 approval) | evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7/ |
| FP-03 | PASS | NOT_ASSESSED | PENDING (auto-advance pre-approved, R-18 2026-09-22) | evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/ |
| FP-04 | IN_PROGRESS | NOT_ASSESSED | PENDING | — |

## Latest run
FP-03 PASS: search-space qualification (A-SC's 3 tunable dims cross-checked against the engine,
out-of-schema values proved to be typed rejections, all 3 dims showed real BEHAVIOR_DIFFERS) +
learning curve at 3 real calibration origins (2021/2022/2023-06-01), each a REAL
`run_cutoff_walk_forward` search to 256/256 trials (`engine_report_level="score"`, required after a
real RLIMIT_AS-caught MemoryError under the engine default profile on this ~300k-bar/180-day scale).
Real wall times: 2786.63s / 2575.28s / 3042.21s (~43-51 min each); peak RSS 1483.3 / 1474.7 / 1520.0
MiB against the 4096 MiB budget. `B_search` frozen at 256, no blocker (all 3 origins reached it).

**Honest finding, not glossed over**: `D_mean_daily_return` (IS − forward; positive = worse decay)
stayed POSITIVE at every checkpoint of every origin — deeper search never turned decay negative on
this alpha/window. All THREE origins (not just some) showed literally zero IS-objective improvement
from checkpoint 128 → 256 (the identical trial stayed selected) — real evidence search depth beyond
128 bought nothing further here, reported as measured, not asserted.

## Dieu da biet tu evidence
- report_level audit vs score is equity-exact on FP-02's OWN real candidate, not only cited from FUP-04's window (route_parity.json).
- A real multi-selection deployment shows the activation delay applies to the INITIAL version too, not only switches (WARMING sentinel before bar 0's version ever decides) -- lineage_demo.json.
- Cross-run cache reuse and cache-based resume both hold on the real evaluator (cache_reuse.json, resume_demo.json).
- Optuna 4.8.0 is actually installed (guide's own source cites 4.2.1 -- disclosed mismatch); `TPESampler(seed=...)` with all other args default, `n_startup_trials=10` confirmed both from `inspect.signature` and an empirical ask/tell demonstration.
- The stock per-trial objective is `mean_is` (mean shard-IS Sharpe, trade-count-penalized), computed INSIDE the engine -- not independently reproducible outside `run_cutoff_walk_forward`, so FP-03/04 never hand-roll a substitute.

## Dieu chua biet
- Sampler-state resume (Optuna) is unmeasured -- no search loop needed it yet.
- Whether B_search=256 (or a lower committed depth) generalizes to alphas/symbols beyond A-SC/BTCUSDT -- FP-03/04 are a single-cell pilot, matching this lab's established A-SC-first pilot order; full-matrix replication is FP-08's job (guide "Replication scope"), not before.
- FP-04's ledger is being built at 12 of the guide's ~26-39-origin research-default target for the eventual model study (FP-05 onward) -- an explicit, disclosed partial scope (see FP-04 section below), not yet known whether 12 origins give FP-05 enough matured, non-degenerate support.

## Corrections made after FP-03 was committed (2026-09-22, before FP-04 build)
- **A real regression, self-caught before it could propagate**: `checkpoint_search.run_origin_search` had silently stopped measuring/returning `wall_seconds_measured`/`instrumentation` (the `Stage`/timer wrapping was missing from the function actually on disk). FP-03's own committed evidence still shows real numbers only because all 3 of its origins happened to hit a stale `.cache/fp03_search_raw/*.json` file written by an EARLIER, still-working version of the function -- a fresh (non-cached) call would have silently written `None`. Found while auditing FP-03 before reusing `run_origin_search` for FP-04's 12 brand-new (never-cached) origins. Fixed with the `Stage` wrapper restored + a new regression test (`test_fp03_run_origin_search_measures_real_wall_and_instrumentation`, a real small 2-trial engine call) that would have caught this the first time. FP-03's own published numbers are unaffected (they came from the real measured run); only the CODE's reproducibility was at risk.

## Blockers
- None recorded for FP-03 at this evidence. FP-04 origin-grid scope is a disclosed choice, not a blocker (see below).

## Budget
- FP-02 charged 0 to the shared TE ledger; ~16 small real engine calls, all on a 10-day/1m real window.
- FP-03 charged 0 to the shared TE ledger; 768 real search-trial engine calls (256 × 3 origins) plus forward-comparison calls, all real A-SC/BTCUSDT windows.

## FP-04 scope decision (frozen before any FP-04 engine call, disclosed here per CLAUDE.md rule 4)
Guide 3.2's research-default target for the eventual outer/model study is ~26-39 origins ("blocks 28
ngày"). At FP-03's measured real cost (~43-51 min per 256-trial/180-day origin, B_search=256 now
frozen), the full target would cost ~19.5-29 hours of strictly-sequential (workers=1) engine
wall-clock -- roughly 6-10x LAB-08's ~3-hour factorial, the largest prior real-engine commitment
anywhere else in this lab's history. FP-04 freezes a **12-origin** grid instead: quarter-start dates
(Jan/Apr/Jul/Oct 1) across 2021-2023, the same three development-role years FP-03's own
CALIBRATION_ORIGINS already used, extended to quarterly density (~9-10.5 real hours projected).
This is an EXPLICIT, disclosed partial scope, not a silent under-provision -- guide 16's own closing
sentence permits it directly ("Thiếu số origins cho model không làm archive vô giá trị, nhưng không
được gọi model study hoàn tất": a short origin count does not invalidate the archive, but the MODEL
STUDY built on it -- FP-05 onward -- may not be called complete from this alone). FP-04's own
incremental-rebuild guarantee (FP04-T07/T08, both tested) means growing this grid later toward the
full 26-39 target costs only the INCREMENTAL new origins, never a redo of these 12.

## Next authorized action
- FP-04 build IN_PROGRESS (real engine run started 2026-09-22, ~9-10.5h projected across 12 origins,
  idempotent per-origin caching so a restart resumes rather than redoing completed origins).
- FP-05 needs its own R-18 (already pre-approved alongside FP-03/04 per the recorded owner decision,
  but FP-04 must fully complete -- report + scoped commit -- before FP-05 starts, per the owner's
  explicit "no shortcuts" instruction).

## Khong duoc lam
- No bulk search beyond the frozen B_search=256 without a new search_policy.json revision.
- No economics change without a new upgrade record.
- No FP-05 start before FP-04's report is written and committed.
- No silent expansion of the FP-04 origin grid beyond the frozen 12 without disclosing it as a policy revision first.
