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
- FP-05: run fp05-20260923T163839Z-79516650 (evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/; an earlier run fp05-20260923T163548Z-9e78d592 is preserved, superseded only by the FP05-G-ACTION plumbing-proof strengthening below)
- FP-05 overall: PASS
- FP-05 gates: FP05-G-SPLIT=PASS / FP05-G-MODEL=PASS / FP05-G-SCORE=PASS / FP05-G-SUPPORT=PASS / FP05-G-ACTION=PASS / FP05-G-REPORT=PASS

## Phase state
| Phase | Technical | Research | Owner | Evidence |
|---|---|---|---|---|
| FP-01 | PASS | NOT_ASSESSED | PENDING | evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/ |
| FP-02 | PASS | NOT_ASSESSED | PENDING (needs R-18 approval) | evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7/ |
| FP-03 | PASS | NOT_ASSESSED | PENDING (auto-advance pre-approved, R-18 2026-09-22) | evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/ |
| FP-04 | PASS | NOT_ASSESSED | PENDING (auto-advance pre-approved, R-18 2026-09-22) | evidence/forward_persistence_fp_v1/fp04-20260923T145511Z-34cb31b6/ |
| FP-05 | PASS | NOT_ASSESSED | PENDING (open-ended auto-advance, R-18 2026-09-23) | evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/ |

## Latest run
FP-05 PASS: Selector B (forward-persistent selection, no regime) built and demonstrated on FP-04's
full 12-origin/192-record archive. True chronological walk-forward OOF (guide 8.3/8.4):
`min_train_origins=4` on 12 origins gives exactly **8 validation origins**, guide 8.7's own stated
OOF-diagnostics floor, hit deliberately, not by coincidence. Ridge alpha selected from the grid
`[0.1, 1.0, 10.0]` by aggregate weighted OOF MSE (**alpha=10.0 won**: weighted MSE
1.745e-07 vs 1.750e-07 at alpha=1.0 vs 1.879e-07 at alpha=0.1 — a real, if narrow, margin). Decay-risk
branch **MEAN_DECAY** (`TAIL_ESTIMATE_UNSUPPORTED`): 12 fit origins clears the guide's model-fit floor
(>=12) but 8 OOF origins is below the tail-quantile floor (>=20) — the guide's OWN registered
fallback, not an improvisation.

**Held-out demo, real and honest**: scored all 16 of origin 2023-10-01's regions with a model
trained ONLY on the 11 earlier origins (a genuinely out-of-sample test). **Zero of the 16 cleared the
predicted-utility floor** (6.4e-05/day, reused verbatim from `configs/minimum_economic_effect.json`
since guide 8.6/FP08.5's "OOS utility/risk safeguard" names no concrete number anywhere in the guide
text) — predicted utilities ranged -0.000032 to +0.000016, all below the floor, even though several
candidates' ACTUAL realized forward labels were much higher (e.g. one candidate predicted +0.000016
but actually realized +0.000506). Selector B's real, disclosed output: **COMMON_FLAT_FALLBACK** — not
cherry-picked, the eligibility gate did exactly what it is supposed to do.

**A real gap found and closed before calling this done**: because B declined everything, the
ADMIT-then-real-deployment code path was never exercised by this real run — only by a synthetic gate
test. This is the exact "gate passed because nothing happened" shape LAB-06/07's own history records
finding repeatedly. Fixed by adding an UNCONDITIONAL "plumbing proof": a second real small deployment
(the stock comparator's real, already-evaluated params, independent of B's own verdict) that runs
every time regardless of what B decides, and a verifier check requiring it. Real result: **19 fills,
10 entries** on a real 10-day window (2023-11-01 — inside the `development` role, strictly after every
origin's own forward window, never touching `outer_evaluation`).

**Cost**: no new search-trial engine calls at all — feature-building is 192 real cache-HIT re-reads of
FP-04's own `evaluate_candidate` calls (~868.5s / 14.5min the first time, cached to
`.cache/fp05_features/rows.json` thereafter), plus one real small (10-day) deployment call for the
plumbing proof. Full lab suite: **1375 passed, 0 failed**.

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
- A naive time-sorted LOO (`fp.chronology.naive_time_sorted_loo_train`, FP-01's own "before" control) really does leak a later origin's record into an earlier origin's training set on FP-05's real archive shape -- `fp.forward_ledger.training_view` (the guard `walk_forward_oof` uses) correctly excludes it. Guide 8.4's dormant-risk regression, proved, not just declared.
- 12 fit origins / 8 OOF origins is exactly guide 8.7's own OOF-diagnostics floor -- confirms `MIN_TRAIN_ORIGINS=4` was the intended design point for a 12-origin archive, not an arbitrary choice.

## Dieu chua biet
- Sampler-state resume (Optuna) is unmeasured -- no search loop needed it yet.
- Whether B_search=256 (or a lower committed depth) generalizes to alphas/symbols beyond A-SC/BTCUSDT -- FP-03/04/05 are a single-cell pilot, matching this lab's established A-SC-first pilot order; full-matrix replication is FP-08's job (guide "Replication scope"), not before.
- Whether Selector B (or C, once built) actually beats the stock selector -- FP-05 makes NO such claim (research status NOT_ASSESSED); that is FP-07's job (the locked A/B/C comparison), and even FP-07 alone is not enough to trust a result without FP-08's replication.
- Whether the demo's COMMON_FLAT_FALLBACK outcome is representative or specific to this one held-out origin/alpha/symbol -- only one held-out fold was used for the demo; FP-07's locked study evaluates every origin/decision point, not just one.

## Corrections made after FP-03 was committed (2026-09-22, before FP-04 build)
- **A real regression, self-caught before it could propagate**: `checkpoint_search.run_origin_search` had silently stopped measuring/returning `wall_seconds_measured`/`instrumentation` (the `Stage`/timer wrapping was missing from the function actually on disk). FP-03's own committed evidence still shows real numbers only because all 3 of its origins happened to hit a stale `.cache/fp03_search_raw/*.json` file written by an EARLIER, still-working version of the function -- a fresh (non-cached) call would have silently written `None`. Found while auditing FP-03 before reusing `run_origin_search` for FP-04's 12 brand-new (never-cached) origins. Fixed with the `Stage` wrapper restored + a new regression test (`test_fp03_run_origin_search_measures_real_wall_and_instrumentation`, a real small 2-trial engine call) that would have caught this the first time. FP-03's own published numbers are unaffected (they came from the real measured run); only the CODE's reproducibility was at risk.

## Corrections made during FP-04's own build (2026-09-23, before any real engine call)
- **A vacuous gate, caught by its own regression test failing for the wrong reason**: `ledger_record()` originally reformatted `origin_cutoff` through `origin_ts.isoformat()`, which silently stopped string-matching `origin_ledger.json`'s own plain-date `origin_cutoff` field. This made `FP04-G-CAUSAL`'s cross-origin-leak check vacuous -- it would never have fired on the real run either, since the dict lookup it depends on always missed. Fixed to keep `origin_cutoff` as the plain join key and `origin_time` as the qualified timestamp; `verifier_fp04.py`'s own `label_available_at` re-derivation was fixed to normalise tz on both sides accordingly.
- Three test-fixture bugs (wrong expected medoid in a hand-built fixture, an `as_of` date miscalculated relative to the 28-day horizon, a float-format assumption) and one real `training_view` bug (did not normalise `decision_time` to tz-aware before calling `fp.chronology.chronological_split`, raising `TypeError` on a naive input) -- all found and fixed before the real build, full suite 1340/1340 passed.

## Corrections made during FP-05's own build (2026-09-23)
- **`FEATURE_NAMES` declared a feature key (`norm_threshold`) that `normalized_params()` never actually produces** (the real key is `norm_alpha.condition_threshold`, the schema's own literal dotted name) -- would have raised `SelectorBError` on every single real call to `build_feature_row`. Found by a test's own assertion failing on the very first real run, before any engine call.
- **The first draft of the demo deployment window used `2024-01-01`**, which falls inside the registered `outer_evaluation` data role that must stay untouched per this lab's standing discipline -- moved to `2023-11-01` (inside `development`, strictly after every origin's own forward window) before any real deployment call was made.
- **`FP05-G-ACTION` passed vacuously the first time it ran for real**: Selector B's own real, honest `COMMON_FLAT_FALLBACK` verdict meant the gate's own ADMIT+real-fills check was never exercised by real data, only by a synthetic test. Fixed by adding an unconditional "plumbing proof" (a second real deployment, independent of B's own verdict) and requiring it in the verifier -- the same "gate passed because nothing happened" defect class this lab's history (LAB-06/07) keeps finding in itself, caught here before it could ship as a silent gap.

## Blockers
- None recorded for FP-05 at this evidence.

## Budget
- FP-02 charged 0 to the shared TE ledger; ~16 small real engine calls, all on a 10-day/1m real window.
- FP-03 charged 0 to the shared TE ledger; 768 real search-trial engine calls (256 × 3 origins) plus forward-comparison calls, all real A-SC/BTCUSDT windows.
- FP-04 charged 0 to the shared TE ledger; 3072 real search-trial engine calls (256 × 12 origins) plus 384 real forward-evaluation engine calls, all real A-SC/BTCUSDT windows. Peak RSS never exceeded 2289.6 MiB against the 4096 MiB budget across any of the 12 origins.
- FP-05 charged 0 to the shared TE ledger; 0 NEW search-trial engine calls (pure cache-hit reuse of FP-04's own calls) plus 1 new real small (10-day) deployment call for the plumbing proof.

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

## FP-05 support-floor observation (12-origin archive is exactly at guide 8.7's model-fit floor)
FP-05's model fit had ZERO margin above the "model fit" floor (>=12 distinct matured origins,
guide 8.7) -- FP-04's archive has EXACTLY 12. Had even one origin failed to produce a matured
record, FP-05 would have had to use `FALLBACK_STOCK_INCUMBENT` instead of fitting anything. This
did not happen (all 12 origins matured cleanly), but it is disclosed as a real, measured fact: this
study is operating at the guide's own minimum, not with headroom. FP-06/07 inherit the same
constraint since they reuse this same archive (guide 18's "Reuse toàn bộ B pipeline").

## Next authorized action
- FP-05 is COMPLETE and committed. Per the owner's 2026-09-23 decision (recorded in
  `evidence/regime_time_edge_ra_v1/owner_decisions.jsonl`, decision_id `dec-f08d01887b889afb`),
  FP-06 onward may proceed WITHOUT an intermediate approval message between phases -- the owner will
  review all evidence together once enough phases have run. This does NOT waive per-phase discipline
  (build/test/real-run/independent-verify/report/commit, guide R25) or resource-safety disclosure
  (any large new real-compute cost, especially FP-07's locked A/B/C study, gets measured and
  disclosed BEFORE running, same as FP-04's scope decision above).
- FP-06 (guide section 9, Selector C) is next: MUST reuse fp.selector_b's feature/model/OOF machinery
  wholesale (guide 18.1: "Reuse toàn bộ B pipeline"), adding ONLY a frozen context family on top --
  never a second candidate pool, target, or base-feature schema.

## Khong duoc lam
- No bulk search beyond the frozen B_search=256 without a new search_policy.json revision.
- No economics change without a new upgrade record.
- No silent expansion of the FP-04 origin grid beyond the frozen 12 without disclosing it as a policy revision first.
- No claim that Selector B (or C) beats or loses to the stock selector -- FP-05/06 build and demonstrate only; FP-07 compares, and only with FP-08's replication is that comparison trustworthy.
- No large new real-compute commitment (a new search, a new multi-arm study) without measuring and disclosing the cost first, per the owner's explicit 2026-09-23 instruction reaffirming this even under the open-ended auto-advance.
