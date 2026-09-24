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
- FP-06: run fp06-20260923T173537Z-1fa316c7 (evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7/)
- FP-06 overall: PASS
- FP-06 gates: FP06-G-ABLATION=PASS / FP06-G-CAUSAL=PASS / FP06-G-SUPPORT=PASS / FP06-G-FREEZE=PASS / FP06-G-CLAIM=PASS
- FP-07: run fp07-20260923T190207Z-5a401d3b (evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/)
- FP-07 overall: PASS
- FP-07 gates: FP07-G-POOL=PASS / FP07-G-EXEC=PASS / FP07-G-ACCOUNT=PASS / FP07-G-DECAY=PASS / FP07-G-COST=PASS / FP07-G-SCOPE=PASS
- FP-08 cell-2 archive: run fp08cell2archive-20260924T125136Z-c93956c8 (evidence/forward_persistence_fp_v1/fp08cell2archive-20260924T125136Z-c93956c8/), verifier_fp04 reused verbatim, all 5 gates PASS
- FP-08 final: run fp08-20260924T152905Z-5b68e8f8 (evidence/forward_persistence_fp_v1/fp08-20260924T152905Z-5b68e8f8/)
- FP-08 overall: PASS
- FP-08 gates: FP08-G-REPLICATION=PASS / FP08-G-D2=PASS / FP08-G-INFERENCE=PASS / FP08-G-CONCENTRATION=PASS / FP08-G-VERDICT=PASS

## Phase state
| Phase | Technical | Research | Owner | Evidence |
|---|---|---|---|---|
| FP-01 | PASS | NOT_ASSESSED | PENDING | evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/ |
| FP-02 | PASS | NOT_ASSESSED | PENDING (needs R-18 approval) | evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7/ |
| FP-03 | PASS | NOT_ASSESSED | PENDING (auto-advance pre-approved, R-18 2026-09-22) | evidence/forward_persistence_fp_v1/fp03-20260922T211626Z-6bf07360/ |
| FP-04 | PASS | NOT_ASSESSED | PENDING (auto-advance pre-approved, R-18 2026-09-22) | evidence/forward_persistence_fp_v1/fp04-20260923T145511Z-34cb31b6/ |
| FP-05 | PASS | NOT_ASSESSED | PENDING (open-ended auto-advance, R-18 2026-09-23) | evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/ |
| FP-06 | PASS | NOT_ASSESSED | PENDING (open-ended auto-advance, R-18 2026-09-23) | evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7/ |
| FP-07 | PASS | NOT_ASSESSED (guide forbids a verdict from one cell) | PENDING (open-ended auto-advance, R-18 2026-09-23; separate exception decision dec-9cc3ec3e712cf61b for the 7 GiB budget) | evidence/forward_persistence_fp_v1/fp07-20260923T190207Z-5a401d3b/ |
| FP-08 | PASS | NOT_ASSESSED (2 of 20 cells; guide's own decision-rule dispositions applied, no stronger claim) | PENDING (open-ended auto-advance, R-18 2026-09-23/24: dec-b5a96eb125bb80cd cell-2 scope, dec-fa173dea205de5e2 + dec-61a43dad79d0ec5c corrected scope understanding) | evidence/forward_persistence_fp_v1/fp08-20260924T152905Z-5b68e8f8/ |

## Latest run
FP-08 PASS: replication, D2 and inference (guide section 20). Combines cell 1 (FP-04..FP-07,
already committed, reused UNCHANGED) with cell 2 (A-SC/ETHUSDT, 3 origins, owner-approved
`dec-b5a96eb125bb80cd`) into the guide FP08.3/.4/.5 statistics, contribution checks and decision
rules, plus the full 20-cell coverage matrix (2 COMPLETED, 18 honestly NOT_RUN with a disclosed
reason).

**Real cell-2 archive**: A-SC/ETHUSDT, 3 origins (2021-06-01/2022-06-01/2023-06-01, reusing FP-03's
own precedented calibration dates), 512 fresh 256-trial search calls (origin 1 reused from a
survived cache after a real incident, below). Measured search wall time: origin 1 **3439.3s**
(57.3min), origin 2 **3109.3s** (51.8min), origin 3 **2795.5s** (46.6min) — total **9344.1s
(2.60h)**, all `wf_ok=True`, peak RSS 1487.8/1624.6/2278.8 MiB, all within the registered 4 GiB
budget (the archive stage itself never needed the 7 GiB exception). 48 ledger records (3×16-region
cap), 40 model-ready, 8 descriptive-only. `verifier_fp04` reused **verbatim, unmodified** — its
gates are generic over whatever origins/symbol the ledger actually contains. All 5 gates PASS.

**A real operational incident, disclosed in full — a genuinely new failure mode for this lab.** The
first cell-2 archive attempt was killed by the Linux kernel **OOM-killer** (out-of-memory killer —
a Linux mechanism that force-kills a process when the WHOLE HOST is critically low on physical
memory, distinct from this lab's own RLIMIT_AS mechanism which only catches ONE process exceeding
ITS OWN self-imposed cap) at 04:43 UTC 2026-09-24, verified via `dmesg`: `total-vm:3835932kB`
(≈3.66 GiB) — **under** this process's own 4 GiB RLIMIT_AS cap. This was host-wide memory pressure
from OTHER always-on tenants on this **shared** host (7 live market-data collectors for the user's
other projects, plus several IDE servers — Warp, Cline, Antigravity, VSCode — all independently
running), not this process misbehaving, and this host has **zero swap configured**, so there is no
cushion once physical RAM is exhausted — the kernel kills immediately rather than degrading
gracefully. A real, disclosed limitation: **RLIMIT_AS protects a process from exceeding its own
budget; it cannot protect against the kernel OOM-killing it for host-wide pressure caused by other
processes.** Origin 1 was already safely cached (verified: `wf_ok=True`, 256/256 trials) — **zero
lost work** — relaunched once host memory recovered (owner-confirmed: "chạy lại luôn"), origins 2-3
completed cleanly on the second attempt with no further OOM event. A separate, real disk-pressure
episode during the same window (host dropped to 1.4 GiB free from OTHER tenants' own growth — a
488 MiB Docker container log, a 473 MiB Codex log, neither touched) resolved itself before it
became critical (measured: this lab's OWN new cache growth during that window was only 20 MiB).

**Real cell-2 study — Selector B/C fell back to A at ALL 3 origins.** A real, honest, MEASURED
finding, not a structural impossibility: origins 2 and 3 genuinely had matured training data and
attempted a real fit (a corrected understanding recorded before this run, `dec-61a43dad79d0ec5c` —
`fp.locked_study`'s walk-forward selection does NOT enforce `selector_b.MIN_FIT_ORIGINS=12`, that
floor gates a different, diagnostic-only path never called from `locked_study.py`) — they simply
never found a candidate clearing the registered utility/support floor (6.4e-05/day, support≥2) at
either origin. Arm A (stock installed selector): **4516 real fills** on ETHUSDT across the full
continuous account (2021-06-01..2024-01-01, ~1.36M bars). Total wall time **211.8s** (only Arm A
needed a real deployment call; B/C had nothing to deploy). Two real code fixes were needed —
`fp.locked_study.build_run_deployment_schedule` correctly raises when an arm has zero admissions,
but the FIRST version of `run_fp08_cell2_study.py`/`build_fp08_cell2_d2.py` did not handle this
real case and crashed; fixed to record `NEVER_ADMITTED` (null metrics, a reason, never a crash,
never a fabricated account) and mark dependent paired contrasts `NOT_EVALUABLE`.

**A second real bug, self-caught before the report was trusted — a vacuous-truth pattern this lab's
own history (LAB-06 defect #15) had already found once before.** `fp.fp08_statistics.
primary_regime_comparison`'s `degenerate` flag was computed via `all(... for o in common if
b_row.D is not None)` — when EVERY D value is null (both B and C in cell 2 never admitted
anything), that generator is EMPTY, and Python's `all()` over an empty set is vacuously `True`, so
a comparison that never happened at all was reported as `degenerate=True` (identical accounts)
rather than the correct `NOT_EVALUABLE` with no comparison possible at all. Found by manually
inspecting cell 2's own real `statistics.json` before trusting the auto-generated report, not by a
failing test. Fixed: `degenerate` is now computed ONLY over origins that were actually evaluable,
and is explicitly `False` (never vacuous) when nothing was compared; a regression test reproduces
the exact real shape. Cell 2's report now correctly reads **"Inconclusive effect/support"** for all
three of its own contrasts, not the misleading "Context mechanism chưa được exercise đủ" the bug
would have produced.

**FP-08's own findings (guide FP08.5 dispositions, the registered six-label vocabulary, never a
stronger invented one)**:

| Contrast | Cell | Status | Estimate | Disposition |
|---|---|---|---:|---|
| C_FP_CONTEXT − B_FP_PERSISTENCE | 1 | ESTIMATED (degenerate) | 0.0 exactly | Context mechanism chưa được exercise đủ |
| B_FP_PERSISTENCE − A_STOCK_CAL | 1 | ESTIMATED | −0.0001890/day | No meaningful improvement tại threshold đã thử |
| C_FP_CONTEXT − A_STOCK_CAL | 1 | ESTIMATED | −0.0001890/day | No meaningful improvement tại threshold đã thử |
| C_FP_CONTEXT − B_FP_PERSISTENCE | 2 | NOT_EVALUABLE | — | Inconclusive effect/support |
| B_FP_PERSISTENCE − A_STOCK_CAL | 2 | NOT_EVALUABLE | — | Inconclusive effect/support |
| C_FP_CONTEXT − A_STOCK_CAL | 2 | NOT_EVALUABLE | — | Inconclusive effect/support |

I_D (guide 10.6, mean positive-decay difference B vs C at common origins): cell 1 = **0.0**
(DESCRIPTIVE, degenerate — C≡B); cell 2 = **NOT_EVALUABLE** (no common origin has real data for
both B and C — correctly `degenerate=False` after the fix above, not the vacuous `True` the bug
would have shown). `delta_decay`/`epsilon_OOS_noninferiority` are `NOT_REGISTERED` anywhere in this
lab (guide 10.7's own explicit fallback) — decay-reduction and non-inferiority claims stay
DESCRIPTIVE throughout, never judged against an invented threshold. `delta_economic_return`
(6.4e-05/day) IS registered and reused verbatim for the "economic outperformance" row.

**Guide FP08.4 contribution checks**: context never changed a single candidate ranking/selection in
EITHER cell (cell1: 0/12, cell2: 0/3 `CONTEXT_CONDITIONED` origins) — the three downstream questions
(benefit persists after common calendar / is it a market-wide offset / conditional selection vs
reduced exposure) are correctly **N/A**, since there is no context-driven effect to examine at all.
The vintage question resolves **CONSISTENT_ACROSS_CELLS**: both cells show zero context-driven
selections, the SAME pattern, not a cell-specific artifact.

**A finding not yet fully explored**: cell 2's Selector B/C declined at every single origin — a
MORE extreme pattern than cell 1's 3/12 real admissions. Guide FP08.4's own question ("does the
result depend on one origin/model vintage") is answered CONSISTENT here in the narrow sense that
NEITHER cell shows context conditioning — but the underlying SELECTION rate itself (0/3 vs 3/12) is
not identical, and this report does not further diagnose why (fewer origins → less training history
at any given decision point is the most likely explanation, not investigated further here — this
would be a natural `reports/improvement_opinions.md` entry, guide R25/CLAUDE.md rule 11, write
only, not run).

Independently re-verified via `scripts/verify_fp08.py` against fresh test evidence (**1503/1503
passed**) before finalizing, never trusting the orchestrator's own internal check. Full lab suite:
**1503 passed, 0 failed**.

### FP-07 (superseded as "latest" by FP-08 above, unchanged)
FP-07 PASS: the locked A/B/C study (guide section 19), the FIRST phase that actually touches the
research question. Real 3-arm continuous-account run, A-SC/BTCUSDT, **1,576,800 real one-minute
bars per arm** (2021-01-01..2023-12-31, the full registered `development` role, never touching
`outer_evaluation`). All three arms select from the SAME shared per-origin pool at all 12 of
FP-04's frozen origins (FP07-G-POOL). Arm A = the engine's own installed `is_only_robust` pick,
already cached from FP-04, admitted at all 12/12 origins. Arm B/C = walk-forward selection through
`fp.selector_b`/`fp.selector_c` verbatim (frozen alpha=10.0 for both, read from FP-05/FP-06's own
committed evidence, never re-selected here) -- **3/12 real admissions each**: the first 4 origins
(2021-01-01..2021-10-01) have no new admission at all (MIN_TRAIN_ORIGINS=4's genuine cold start),
and 5 of the remaining 8 had no candidate clear the utility/support floor. A no-admission origin
means the account keeps whatever version is already active (or stays FLAT_UNTIL_READY
pre-first-admission) -- never a value silently borrowed from Arm A, confirmed against the engine's
own `_one_sweep` "A02" flat-until-ready contract.

**A real capacity finding, measured and disclosed before use.** A first real attempt at the full
span hit a genuine `MemoryError` (RLIMIT_AS-caught) at `bar_index=1,360,272` against the registered
4 GiB working-memory cap -- a single-call bar count no prior phase in this lab has run. Four real
probe runs (100k/400k/800k/1.2M bars, single-activation schedule) measured linear RSS growth
(~1.77 MiB per 1000 bars: 454/979/1687 MiB, then a MemoryError at 1.2M bars with RSS at 2403 MiB),
showing the failure is a virtual-address-space ceiling, not an actual host RAM shortage (projected
~3.1 GiB real RSS for the full span against a then-measured ~4.1 GiB available). Presented to the
owner via AskUserQuestion with this real data; a disclosed, scoped, ONE-TIME exception to 7 GiB was
approved (decision `dec-9cc3ec3e712cf61b`, `owner_decisions.jsonl`) for FP-07's own three
`run_deployment` calls only -- the registered 4 GiB budget is unchanged for every other phase/call
in this lab. Measured peak RSS on the successful run: **3357.7 MiB**, comfortably under the 7 GiB
cap. Total measured wall time: **509.41s** (~8.5 min) across all 3 arms (Arm A 25.02s -- a
legitimate, content-verified cache HIT reusing a real, complete computation from the earlier failed
attempt, which had finished Arm A before crashing on Arm B; Arm B 241.55s; Arm C 236.22s, both real
cache MISSes).

**Honest, load-bearing finding: C_FP_CONTEXT == B_FP_PERSISTENCE in this run.** At all 3 origins
where B admitted a selection (2021-04-01, 2021-10-01, 2022-01-01), C's own utility-maximizing
candidate was out-of-distribution relative to its training window's context range, so C fell back
to B's exact prediction every single time (`source=FALLBACK_TO_B`, never `CONTEXT_CONDITIONED`,
0/12 origins). C's params are IDENTICAL to B's at every real admission -- the two accounts are
byte-for-byte the same (3312 fills each, identical D1 at every origin). This is guide 20/FP08.5's
own named outcome category verbatim: *"C≈B vì fallback → Context mechanism chưa được exercise đủ"*
(C looks like B because of fallback -> the context mechanism was not exercised enough). The
**PRIMARY contrast (C-B) is therefore DEGENERATE BY CONSTRUCTION**: estimate exactly 0.0,
ci95=[0.0, 0.0], p_one_sided=1.0 over 1095 common days -- reported as a degenerate artifact of this
run, explicitly NOT as a measured absence of a context effect.

**Secondary/diagnostic contrasts** (guide 19 draws no verdict from these; FP08.5 owns decision
rules): B_FP_PERSISTENCE − A_STOCK_CAL and C_FP_CONTEXT − A_STOCK_CAL are identical for the same
reason (C≡B) -- both **estimate = −0.0001889748502425521/day**, 95% CI
**[−0.0003208041703683213, −0.0000387272697232]** (block bootstrap, 28-day blocks, 39
non-overlapping blocks, seed 2026091201), i.e. the forward-persistent selector UNDERPERFORMED the
stock installed selector over this single cell/window, with a CI entirely below zero. This is ONE
unreplicated cell with no placebo control of its own -- guide 19/FP07-G-SCOPE explicitly forbids
treating this as a verdict; FP-08's replication is required before any claim.

**D1 table** (guide 8.5, per-selection IS-vs-realized-forward-label lookup, never derived by slicing
the deployment account): only 7 of 36 (arm, origin) rows carry a real value -- the rest are null
with a disclosed reason (a fallback origin has no forward-labelled record; Arm A's stock pick
matched a region-archive medoid at only 1/12 origins, measured across all 12, not assumed). Where
present: A_STOCK_CAL mean D1=−0.000413 (1 selection), B_FP_PERSISTENCE and C_FP_CONTEXT both
mean D1=+0.000176 (3 selections each, identical by the C≡B finding above).

**A cache-hit correctness check, done rather than assumed**: Arm A's "HIT" was independently
content-verified (not just trusted) -- the cached payload's equity array has exactly 1,576,800
rows, 1,460 fills, and a 12-entry schedule, all matching the report -- confirming it is a real,
complete result, not a stale/partial entry from the earlier crashed attempt.

**Independently re-verified with fresh test evidence** after the orchestrator's own internal check
ran against a stale pre-flight `junit.xml` missing 2 last-minute budget-exception-disclosure tests
(added after that pytest run) -- re-verified via `scripts/verify_fp07.py` against 182/182
`tests/fp_corrective` passing, never trusting the runner's own PASS/FAIL. Full lab suite:
**1437 passed, 0 failed**.

### FP-06 (superseded as "latest" by FP-07 above, unchanged)
FP-06 PASS: Selector C (Selector B plus a frozen context family, guide section 9) built on the
IDENTICAL 12-origin/192-record archive B used, through the LITERAL SAME
`fp.selector_b.walk_forward_oof` loop (now generalised to accept a `feature_matrix_fn`, the ONLY
change made to Selector B's own code) -- guide 9.1's "candidate pool, target, inner split policy,
regularization-selection rule stay identical" enforced structurally, not by convention.

**Two frozen context features** (guide 9.3, JM/M0 explicitly NOT used -- LAB-08's own measured
1.64% JM/M0 calibration-vintage support was too thin to build on, a disclosed choice, exposure still
recorded at zero): `ctx_direction_efficiency` (signed path efficiency) and `ctx_volatility_ratio`
(short/long realized-vol ratio), both computed from the same causal IS frame B already loads.
**Two registered interaction terms** (guide 9.2: `norm_AP × ctx_direction_efficiency`,
`norm_coeff × ctx_volatility_ratio` — 2 of 18 possible pairs, never the full Cartesian product).

**Guide 9.2's own counterexample, proven not just avoided**: a designed fixture (two candidates
differing only in `norm_AP`, a true label with a context-dependent crossover — high-AP wins when
trending, low-AP wins when choppy) shows a purely additive model (candidate + context as separate
columns, no product term) predicts the SAME relative candidate ranking regardless of context — it
structurally cannot represent a crossover — while Selector C's interaction architecture correctly
FLIPS the predicted ranking between the two contexts (`FP06-T04`, both directions tested and passed).

**Real held-out demo, same 16 candidates FP-05 scored**: alpha=10.0 selected for both B and C
independently (same value). All 16 candidates stayed **in-distribution** (0 OOD fallback,
16/16 context-conditioned). **mean(C − B) = 4.79e-07** — a tiny, real, honest adjustment; C's
predictions remained far below the utility floor on every candidate, same as B's. Guide 9.2's own
permitted outcome: *"C không tạo khác biệt trên real data vẫn là kết quả hợp lệ nếu execution
đúng"* (C creating no difference on real data is still a valid result if execution is correct).

**Cost: zero new engine calls of any kind** — no new search trials, no new deployment calls (FP-06's
own exit gate does not require re-proving admission/deployment wiring; FP05-G-ACTION already did
that generically). Context features come from 12 real disk reads of already-real-loaded market
frames. Full lab suite: **1403 passed, 0 failed**.

### FP-05 (superseded as "latest" by FP-06 above, unchanged)
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
- A single `run_deployment` call over ~1.58M one-minute bars needs a virtual-address-space ceiling well above its own actual resident-memory need (measured: ~3.1 GiB projected RSS vs a genuine MemoryError below a 4 GiB RLIMIT_AS cap) -- the constraint is fragmentation/transient-allocation headroom in the installed quantbt engine, not a host RAM shortage. This is now a MEASURED fact for future phases (FP-08's own continuous accounts will hit the same shape).
- At this cell/window, Selector C's context mechanism was available (16 candidates scored, 10-13 eligible) but its OWN utility-maximizing pick was out-of-distribution relative to C's training window's context range at every one of B's 3 real admissions -- context conditioning never actually fired in a real walk-forward setting, distinct from FP-06's held-out demo (0/16 OOD there). Whether this is specific to A-SC/BTCUSDT's narrow early-history context range or a more general early-cold-start pattern is unknown -- FP-08's second cell will show whether it recurs.

## Dieu chua biet
- Sampler-state resume (Optuna) is unmeasured -- no search loop needed it yet.
- Whether B_search=256 (or a lower committed depth) generalizes to alphas/symbols beyond A-SC/BTCUSDT -- FP-03/04/05/06/07 are a single-cell pilot, matching this lab's established A-SC-first pilot order; full-matrix replication is FP-08's job (guide "Replication scope"), not before.
- Whether Selector B or C actually beats the stock selector -- FP-07 measured ONE cell's real numbers (B/C underperformed A by ~0.000189/day, CI entirely below zero) but guide 19/FP07-G-SCOPE explicitly forbids treating one unreplicated cell as a verdict; that needs FP-08.
- Whether C≡B (context mechanism never firing) is a property of this one cell/window or a more general pattern -- FP-08's second cell is the first real evidence either way.
- Whether B/C's measured underperformance vs A in this cell reflects a real cost of the walk-forward cold-start (9/12 origins with no new admission) or something else -- FP-07 draws no verdict; FP-08's own inference machinery (guide 20 FP08.3) is where this gets tested properly.

## Corrections made after FP-03 was committed (2026-09-22, before FP-04 build)
- **A real regression, self-caught before it could propagate**: `checkpoint_search.run_origin_search` had silently stopped measuring/returning `wall_seconds_measured`/`instrumentation` (the `Stage`/timer wrapping was missing from the function actually on disk). FP-03's own committed evidence still shows real numbers only because all 3 of its origins happened to hit a stale `.cache/fp03_search_raw/*.json` file written by an EARLIER, still-working version of the function -- a fresh (non-cached) call would have silently written `None`. Found while auditing FP-03 before reusing `run_origin_search` for FP-04's 12 brand-new (never-cached) origins. Fixed with the `Stage` wrapper restored + a new regression test (`test_fp03_run_origin_search_measures_real_wall_and_instrumentation`, a real small 2-trial engine call) that would have caught this the first time. FP-03's own published numbers are unaffected (they came from the real measured run); only the CODE's reproducibility was at risk.

## Corrections made during FP-04's own build (2026-09-23, before any real engine call)
- **A vacuous gate, caught by its own regression test failing for the wrong reason**: `ledger_record()` originally reformatted `origin_cutoff` through `origin_ts.isoformat()`, which silently stopped string-matching `origin_ledger.json`'s own plain-date `origin_cutoff` field. This made `FP04-G-CAUSAL`'s cross-origin-leak check vacuous -- it would never have fired on the real run either, since the dict lookup it depends on always missed. Fixed to keep `origin_cutoff` as the plain join key and `origin_time` as the qualified timestamp; `verifier_fp04.py`'s own `label_available_at` re-derivation was fixed to normalise tz on both sides accordingly.
- Three test-fixture bugs (wrong expected medoid in a hand-built fixture, an `as_of` date miscalculated relative to the 28-day horizon, a float-format assumption) and one real `training_view` bug (did not normalise `decision_time` to tz-aware before calling `fp.chronology.chronological_split`, raising `TypeError` on a naive input) -- all found and fixed before the real build, full suite 1340/1340 passed.

## Corrections made during FP-05's own build (2026-09-23)
- **`FEATURE_NAMES` declared a feature key (`norm_threshold`) that `normalized_params()` never actually produces** (the real key is `norm_alpha.condition_threshold`, the schema's own literal dotted name) -- would have raised `SelectorBError` on every single real call to `build_feature_row`. Found by a test's own assertion failing on the very first real run, before any engine call.
- **The first draft of the demo deployment window used `2024-01-01`**, which falls inside the registered `outer_evaluation` data role that must stay untouched per this lab's standing discipline -- moved to `2023-11-01` (inside `development`, strictly after every origin's own forward window) before any real deployment call was made.
- **`FP05-G-ACTION` passed vacuously the first time it ran for real**: Selector B's own real, honest `COMMON_FLAT_FALLBACK` verdict meant the gate's own ADMIT+real-fills check was never exercised by real data, only by a synthetic test. Fixed by adding an unconditional "plumbing proof" (a second real deployment, independent of B's own verdict) and requiring it in the verifier -- the same "gate passed because nothing happened" defect class this lab's history (LAB-06/07) keeps finding in itself, caught here before it could ship as a silent gap.

## Corrections made during FP-07's own build (2026-09-23)
- **A frame-tuple unpacking bug**: `load_real_bars` returns `(frame, partitions)`; the first draft of `run_fp07.py` used the return value directly as the frame, crashing immediately with `TypeError`. Caught on the very first launch, before any real engine call.
- **A genuine capacity gap, not a bug**: the registered 4 GiB working-memory budget cannot fit a single `run_deployment` call over the full ~1.58M-bar span (real `MemoryError` at bar 1,360,272). Root-caused with 4 real probe runs rather than guessed at; resolved via a disclosed, owner-approved, scoped exception (see "Latest run" above), not a silent workaround and not a violation of the guide's "one continuous account, no stitching" design.
- **A report-wording bug found during real-number review, not by being asked**: `render_report`'s "Technical" conclusion cited "the 4 GiB budget" after the exception raised the APPLIED cap to 7 GiB -- misleading next to the exception disclosure two paragraphs above it. Fixed to cite the actual applied cap. Re-rendered from the already-computed artifacts (0 engine calls re-run), re-verified (182/182 fresh test evidence), gate_receipt.json updated to reflect the corrected, independently re-verified state.
- **The C≡B degenerate pattern was present in the raw artifacts but not prominently disclosed in the first rendering** of report.md -- added an explicit `DEGENERATE` callout naming guide 20/FP08.5's own outcome category, matching the LAB-08 "Arm E was a copy of Arm D" disclosure precedent, so a reader cannot mistake the primary contrast's exact-zero estimate for a measured null effect.

## Blockers
- None recorded for FP-08 at this evidence. All five gates PASS. FP-08 itself reaches no verdict beyond guide FP08.5's own registered decision-rule labels -- neither cell clears the registered economic threshold, and cell 2's B/C never admitted anything (NOT_EVALUABLE, not a fabricated result).

## Budget
- FP-02 charged 0 to the shared TE ledger; ~16 small real engine calls, all on a 10-day/1m real window.
- FP-03 charged 0 to the shared TE ledger; 768 real search-trial engine calls (256 × 3 origins) plus forward-comparison calls, all real A-SC/BTCUSDT windows.
- FP-04 charged 0 to the shared TE ledger; 3072 real search-trial engine calls (256 × 12 origins) plus 384 real forward-evaluation engine calls, all real A-SC/BTCUSDT windows. Peak RSS never exceeded 2289.6 MiB against the 4096 MiB budget across any of the 12 origins.
- FP-05 charged 0 to the shared TE ledger; 0 NEW search-trial engine calls (pure cache-hit reuse of FP-04's own calls) plus 1 new real small (10-day) deployment call for the plumbing proof.
- FP-06 charged 0 to the shared TE ledger; **0 new engine calls of any kind** (no search trials, no deployment calls) -- context features came from 12 real disk reads of already-loaded market frames, reusing FP-05's own feature cache entirely.
- FP-07 charged 0 to the shared TE ledger; 3 real `run_deployment` calls (1 per arm, 1,576,800 bars each; Arm A a content-verified real cache HIT reusing a prior attempt's completed work, B/C real cache MISSes), plus 4 small real memory-probe calls (100k/400k/800k/1.2M bars) used only for the capacity diagnostic. Total measured wall time 509.41s for the successful run; peak RSS 3357.7 MiB against the disclosed, owner-approved 7 GiB exception (registered budget stays 4 GiB everywhere else in this lab).
- FP-08 charged 0 to the shared TE ledger; cell-2 archive: 512 real search-trial-256 calls (2 fresh origins, 1 reused from a survived cache), 9344.1s total search wall (2.60h), peak RSS 2278.8 MiB against the REGISTERED 4 GiB budget (no exception needed for the archive stage). Cell-2 study: 1 real `run_deployment` call (Arm A only, ~1.36M bars, 211.8s, B/C had nothing to deploy), reusing the disclosed 7 GiB exception pattern defensively (peak measured well under it). `run_fp08.py` itself: 0 new engine calls (guide FP08.3's own requirement), reads only already-computed D1/D2/paired-contrast artifacts.

## FP-08 operational incident (host-wide OOM, disclosed per CLAUDE.md rule 4)
The first cell-2 archive attempt was killed by the Linux kernel OOM-killer at 04:43 UTC 2026-09-24
while this process's own memory (3.66 GiB virtual) was UNDER its own 4 GiB RLIMIT_AS cap -- verified
via `dmesg`, not assumed. This shared host runs 7 persistent live market-data collectors plus
several IDE servers at all times (~5.5 GiB baseline usage) and has **zero swap configured**, so a
transient spike from ANY of those other tenants can trigger the kernel OOM-killer with no cushion.
**RLIMIT_AS protects a process from exceeding its OWN budget; it cannot protect against the kernel
killing it for host-wide pressure caused by OTHER processes** -- a real, disclosed limitation of
this lab's established resource-safety pattern, not previously encountered (FP-03/04/07's own
MemoryErrors were all this process's own RLIMIT_AS catching itself, a fundamentally different
mechanism). Origin 1's real search result survived (cached, verified valid) -- zero lost work;
relaunched after owner confirmation once host memory recovered, origins 2-3 completed cleanly with
no further incident. No code or contract change was needed to fix this -- it was a host condition,
not a lab defect -- but future phases with a large continuous-account or search stage on this same
host should expect the same shared-tenancy risk and budget for a possible relaunch.

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
- FP-08 is COMPLETE and committed. All five gates PASS. Per the owner's 2026-09-23 open-ended
  decision (`dec-f08d01887b889afb`) plus the explicit 2026-09-24 confirmation to rerun and finish
  FP-08 after the OOM incident, FP-09 may be considered next -- but FP-09 (guide section 21,
  secondary timing extension) is its OWN explicit CONDITIONAL branch: guide 21 requires the owner to
  approve its reason, scope and budget, AND a specific mechanistic hypothesis, not just "no result
  yet so try timing next". **Do not open FP-09 from the open-ended auto-advance alone** -- present
  the FP-08 findings and ask.
- FP-10 (freeze, replay, final handoff) is the OTHER path once the owner decides no further phase is
  needed.
- Both cells' own findings are now on record: cell 1 shows C≡B degenerate (context mechanism never
  exercised) and B/C measurably underperforming A (CI entirely below the registered threshold, "No
  meaningful improvement"); cell 2 shows B/C declining at EVERY origin (NOT_EVALUABLE, no comparison
  possible at all) while Arm A traded normally. Neither cell found context conditioning to matter.

## Khong duoc lam
- No bulk search beyond the frozen B_search=256 without a new search_policy.json revision.
- No economics change without a new upgrade record.
- No silent expansion of the FP-04 origin grid beyond the frozen 12, or the FP-08 cell-2 grid beyond its frozen 3, without disclosing it as a policy revision first.
- No claim that Selector B or C beats or loses to the stock selector beyond guide FP08.5's own registered disposition labels already applied (`No meaningful improvement tại threshold đã thử` for cell 1's B-A/C-A; `Inconclusive effect/support` for all of cell 2's contrasts) -- never a stronger invented label.
- No claim from FP-07/08's C≡B finding that context conditioning "doesn't work" in general -- it is a property of these two cells/windows, disclosed as DEGENERATE/NOT_EVALUABLE, not generalized beyond them.
- No FP-09 without its own explicit R-18 approval carrying a specific mechanistic hypothesis (guide 21) -- the open-ended auto-advance does not cover it.
- No large new real-compute commitment without measuring and disclosing the cost first (the dec-9cc3ec3e712cf61b / dec-b5a96eb125bb80cd pattern), and no working-memory budget exception beyond the registered 4 GiB without its own disclosed decision record scoped to the specific calls that need it.
- No claim that this lab's RLIMIT_AS mechanism protects against host-wide OOM kills from other tenants -- FP-08's own incident proved it does not; only this process's own budget is protected.
