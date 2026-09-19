# AGENTS.md — QuantBT Crypto Regime & Parameter Time-Edge Lab

Research lab (not a product) around a pinned, unmodified `quantbt-engine==1.1.1`. It asks whether
regime information selects parameters and times their deployment better than calendar WFO. The
five-phase corrective study RF-01…RF-05 is complete (`REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md`,
Vietnamese, ~13.5k lines; `CLAUDE.md` is the English digest). **The current authority is the RA
guide** `REGIME_LAB_MODE4_CORRECTIVE_AGENT_PHASE_GUIDE_VI.md` (RA-GUIDE-1.0, phases RA-01…RA-08,
per-phase owner approval). `QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md` applies only where
not superseded. Read the active guide before changing anything.

## Current state (verify, don't assume)

- Historical study LAB-01 … LAB-09 is complete and its conclusion is **`FAILED_VALIDITY`**
  (`reports/lab09_report.md`). LAB-10 is folded into the corrective phases below — there is no
  separate LAB-10 run. `evidence/crypto_regime_timeedge_v2/` is append-only and never edited.
- The authoritative plan is the five-phase corrective study **RF-01 … RF-05** on branch
  `mode4-corrective` (`study_id=corrective_mode4_v3`, stable dirs under
  `evidence/corrective_mode4_v3/`). Registered spec:
  `evidence/corrective_mode4_v3/RF-01/corrective_study_spec.json`. Historical claim verdicts are
  superseded to `NOT_EVALUABLE` in `historical_invalidation.json` without editing any historical
  artifact.
- **RF-01 … RF-05 are complete.** RF-01 = identity/binding/invalidation and the then-failing
  before-repair probes; RF-02 = real-snapshot event account and public Mode 4 baseline; RF-03 =
  causal regime controller; RF-04 = 10-cell event-route paired discovery
  (`RF-04/paired_discovery_full.json`) plus design freeze, decay and controls; RF-05 = freeze,
  recompute, claims, integrity and handoff (`RF-05/report.md`, `claim_report.json`, etc.).
  Coverage is **10 of 20 planned cells executed**; A-VWAP/A-HASH stay `BLOCKED_CAPABILITY` with
  null metrics + reasons, never zero-filled.
- **RF-05 claim**: `TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE`, economic `INCONCLUSIVE`. Paired
  common-date daily `M4_REGIME - M4_CAL` aggregate (10 cells): mean −0.1123 bps/day, block
  bootstrap (5 days, 2000 draws, seed 20260911) 95% CI [−0.4940, +0.1907]; `M4_REGIME −
  M4_CAL_MATCHED` (1 evaluable cell, A-HMA/BTCUSDT; A-SC endpoint is `DEVIATED`): +0.1620
  [−0.2142, +0.6154]. Holm over {TIMING, BUDGET_AWARE} (m=2) → both `INCONCLUSIVE` against the
  frozen MDE 0.0371 bps/day; A-SC/SOLUSDT is `NEGATIVE_WITHIN_SCOPE` at cell level. No `POSITIVE`.
  Contamination `NESTED_RETROSPECTIVE` (no untouched holdout);
  `RF-05/prospective_protocol.json` is `SPECIFIED_NOT_EXECUTED` and must not be run here.
- **RA-01 is COMPLETE and its verifier recorded `overall: PASS`** (2026-09-18,
  run `ra01-20260918T093759Z-e72c0dd9`; independent verify exit 0; all five gates G01-ID/MIG/
  VERIFY/BUDGET/REPORT pass). All G01 gates + 14 tests in `tests/ra_corrective/` are green.
  Key facts locked: branch `mode4-corrective`, engine 1.1.1/native 0.4.2 (pip, no direct_url),
  endpoint sha installed==protected; ledger `TE02-PILOT-R03` charged 165457.9s / 300000s with the
  RUNNING row `bc9d8951…` classified `ORPHAN_NO_LIVE_PROCESS` (recovery belongs to the TE
  supervisor, not RA-01); 7-row protocol migration (incl. T02 run-output-dedup scoping); 4-arm
  registration with M4_CAL_MATCHED as canonical CAL_BUDGET and economic fields
  `PENDING_CALIBRATION`. Approvals in RA-01's OWN frozen `registration.json` stay `PENDING`
  forever by design (`ra/verifier.py` enforces this — a script cannot self-approve its own
  phase). Two earlier attempts (08:33Z FAIL — verifier did not read the nested identity schema;
  09:36Z PASS) are kept append-only. RA-01 code/artifacts are committed (commits `b2a58af`, `fa3be63`).
- **Owner approved RA-01→RA-02 on 2026-09-18** — recorded, not inferred, in
  `evidence/regime_time_edge_ra_v1/owner_decisions.jsonl` (append-only; `scripts/
  record_owner_decision.py` writes it, never overwrites a `decision_id`). This is a SEPARATE
  ledger from any phase's own frozen gate — RA-01/RA-02's own `phase_gate.json`/`registration.json`
  correctly keep reading `PENDING`/`false`; the decision ledger is what the *next* phase's
  admission must consult. Before recording, verify the ledger's last entry actually covers the
  transition you are about to start — do not assume today's approval extends past RA-02.
- **RA-02 is COMPLETE, technical_gate PASS, 5/5 gates** (run `ra02-20260918T134757Z-76c16f60`,
  2026-09-18; two earlier same-day drafts FAILED on real bugs then were fixed — see their kept
  `phase_gate.json`s — a third draft already reached 5/5 before this run). 1 real QuantBT
  engine call (1440 bars), cross-run reuse HIT with 0 new engine runs and a byte-equal payload,
  resume-parity PASS with the red control (tell-dropping restart) actually diverging — proving
  the parity check isn't vacuous. Ledger `TE02-PILOT-R03` unchanged by the phase (RA-02 charges
  nothing to the shared TE budget). Commits `2819fbd6` (implementation), `91c3591b` (evidence,
  4 runs kept). `research_status: NOT_ASSESSED` — no economic/market claim.
- **RA-03 is COMPLETE, technical_gate PASS, 6/6 gates** (run `ra03-20260918T151853Z-d5135816`,
  2026-09-18; two earlier same-day attempts kept append-only — one crashed on a report-formatting
  bug AFTER its verify_ra03() already recorded PASS on all 6 gates, one PASSED but carried a dead
  `schema_declares()` function caught by the reachability gate, same defect class as RA-02's
  `json_bytes_strict`). Real RA03.1 defect found and FIXED in `time_edge/execution.py`:
  `PreparedAccount.__init__` eagerly packed the full frame via `prepare_native_event_strategy`
  even though every real caller (TrainingScorer, candidate_targets, every deploy/decay/
  full_control task) passes a non-zero `account_start` — measured 0.0423s/+7.8 MiB wasted per
  construction, `was_ever_used=False`. Fixed: `first==0` is now just another `_window()` cache
  key, packed lazily. Verified byte-identical output before/after (M02). All 4 alphas' one real
  event route qualified with real fills/exit tags (A-HASH surfaced `ladder`, A-VWAP `tp`); no
  fast/vectorized route exists in this codebase for any alpha. Peak RSS 0.319/0.383 GiB on the two
  profiled scopes against a 2.4 GiB target (80% of the registered 3.0 GiB cap). Capacity forecast
  built from measurement correctly got `BLOCKED_BUDGET` on an over-envelope probe and `ADMIT` on
  an in-envelope one. Ledger `TE02-PILOT-R03` unchanged by the phase. Commits `37191d56` (the
  RA03.1 fix), `0b2246c2` (RA-03 implementation), `16e6f9b2` (the schema_declares fix),
  `8d768c61`/`dc9ca8c0` (evidence, 3 runs kept). `research_status: NOT_ASSESSED` — no economic/
  market claim. Known gap recorded, not changed: `TrainingScorer` persists FULL fills/commands/
  order_events per trial, more than the CANDIDATE_COMPACT retention tier specifies (wider blast
  radius than this phase's scope — other code reads those files).
- **RA-04 is COMPLETE, technical_gate PASS, 4/4 gates** (run `ra04-20260918T162015Z-85cc39de`,
  2026-09-18; one earlier same-day attempt crashed writing `f04_reproduction.json` — raw `-inf`
  Sharpe values violated `evidence/manifest.py`'s strict-JSON refusal of non-finite values, right
  after `selector_semantics.json` had already been written — kept append-only, not discarded).
  **F-04 reproduced on current source** (no raw evidence for it exists on this host): the
  installed engine's own `split_datetime_index_into_subperiods_v1` (`is_subperiods=6`) splits by
  bar count, so only shard 0 reliably starts at a UTC day boundary; `TrainingScorer._score`
  scores complete days only, and a candidate that doesn't trade inside a shard returns
  `sharpe=-inf`/`ZERO_VARIANCE`, correctly dropped by the installed selector's own
  `np.isfinite` filter — but with few surviving shards, "temporal robustness" collapses to one
  shared data point or the registered fallback constant. Measured on a 4-candidate/20-day fixture:
  2/4 candidates ≤1 finite shard, 1/4 hit the pure fallback constant, cross-candidate score
  collapse at 2 distinct shared values (exact float match) — and the SAME mechanism
  (`selector: fallback_best_is_temporal`, `reason: insufficient_cluster_points`,
  `temporal_count: 1.0`) surfaced **organically**, not by construction, through the real active
  public-path integration call (RA04.6). Built `STOCK_MODE4_PLUS_ADMISSION_V1` (RA04.3) — a
  post-selection guard over the unchanged stock selector (never substitutes its own winner):
  ADMIT/KEEP_INCUMBENT/COMMON_FLAT_FALLBACK from two alpha-specific frozen thresholds
  (`min_complete_train_days = max(2, history_days(alpha))`: SC=2, HMA=18, VWAP=101, HASH=3;
  `min_finite_shards = 3 of 6`). Trial budget **reused** from
  `configs/time_edge_validation_v4/mode4_binding_r01.json` (32 trials, `is_subperiods=6`,
  `seed=20260912`), not re-frozen. Search dimensions: 2-3 per alpha with a real
  `behavior_witness()` each — A-HMA's first-tried `min_length`/`mult` were measured **DEAD**
  (byte-identical `terminal_equity` across their whole range on the phase fixture), reported
  honestly and swapped for `max_length`/`take_profit`/`max_sl`. All 7 compact controls (RA04.5)
  passed with real engine evidence. Found and fixed (lab-owned, not frozen by RF-05's
  `freeze_manifest.json`): `alphas/a_vwap.py`'s `exit_at_vwap`/`time_stop_on` used naive
  `bool(x)`, so ANY truthy value (a stray string, `1`) silently meant `True` — now raises unless
  the value `is True`/`is False` exactly; verified behavior-preserving for real True/False,
  301 passed / 0 regressions across every A-VWAP-touching test. Commits `e467e069` (the a_vwap.py
  fix), `db228594` (RA-04 implementation), `0226eebd` (evidence, 2 runs kept).
  `research_status: NOT_ASSESSED` — no economic/market claim; none of Q01-Q07/G04-* require
  ranking IC>0, Sharpe>0, or regime beating a synthetic calendar.
- **Test suite (2026-09-19, 1243 collected): 1243 passed, 0 failed** (full run ≈18m08s — grew
  from the 1202 figure by the 41 new RA-07 tests, and before that from ≈15m12s/1172 by the 30
  RA-06 tests) — still fully green. All three
  previously-documented pre-existing failures were RESOLVED earlier this same session, at the
  owner's explicit request to handle them rather than leave them open (R-17 still respected: each
  was root-caused before being touched, nothing was papered over to force a pass):
  - **T62/T63 forbidden-claims false positive.** `check_regime_works()` in
    `scripts/audit_forbidden_claims.py` read T62/T63 `COVERED` in `acceptance_test_coverage.json`
    as a proxy for "a regime-works claim is being made" — but T62/T63 are about testing
    DISCIPLINE (no untested heatmap cell presented as evidence, the paired bootstrap done
    correctly across 5 symbols), not a published verdict; the proxy was sound only before LAB-09
    built that machinery, and went stale the moment it did. The actual verdict lives in
    `configs/lab09_claim_report.json`: `conclusion_level=FAILED_VALIDITY`,
    `forbidden.fund_grade_alpha_proven=False` — no regime-works claim has ever been made. Fixed to
    read that instead. 9/9 forbidden-claim checks now pass legitimately; the two fields
    `test_the_negative_findings_the_lab_actually_reports_are_preserved` pins
    (`group_ablation_ran`/`group_ablation_improved_out_of_fold`) are unchanged.
  - **21 undeclared vacuity lines** across `test_rf04_decay_and_controls.py`,
    `test_rf04_scaling.py`, `test_rf05_claims.py`, `test_te03_7.py`. Traced with
    `scripts/audit_assertion_vacuity.py` and triaged individually against the real committed
    artifacts (not guessed): all 21 are legitimate contingencies, not bugs — e.g. RF-05's
    `POSITIVE_WITHIN_SCOPE` guard never fires because no RF-05 contrast is ever POSITIVE (the
    study's own honest result), RF-04's placebo-reason/coverage-reason guards never fire because
    the real placebo ran and every cell is RUN_VALID or BLOCKED_CAPABILITY (never NOT_RUN_BUDGET),
    and TE-03.7's 14-line `MEASURED`-branch guard never fires because that controls funnel is
    still `NOT_RUN_BUDGET` (TE02-PILOT-R03 ledger has ~106442s left as of 2026-09-18 — a separate
    study, not touched). Declared with real driving tests (constructed inputs exercising both the
    pass and fail path, matching the file's established LAB-03/04 pattern — not bare
    self-reference) in 5 new `tests/test_contingency_paths.py` functions.
  - **Self-referential ratio miscalculation** (found while fixing the above; not previously
    documented anywhere). The gate's own `reached > 0.99` line is inside `SELF_REFERENTIAL_TESTS`
    (excluded from `never_reached` reporting because reading it is circular — the gate reads its
    own prior run's artifact), but the ratio's denominator never excluded those same lines, a
    standing ~0.1pp undercount. It had been invisible because this exact assertion had apparently
    never once been reached: the same test's earlier `undeclared == []` assert had been failing
    first, on every run, since before the 21 lines above were introduced — a guard auditing guard
    vacuity that was itself vacuous. Fixed by emitting `self_referential_tracked_lines` /
    `self_referential_lines_reached` from the script and excluding them symmetrically in the
    consuming test's formula (verified: 3481/3513 = 99.09% once correctly excluded, vs the
    uncorrected 3482/3519 = 98.9% that had been silently failing this assertion for the first time
    it ever ran).
  Before-repair tests in `tests/mode4_corrective/` are green — never delete or weaken them.
  TE-03.7 itself remains genuinely un-executed (`NOT_RUN_BUDGET`, separate study/approval track —
  advancing it was not part of this cleanup and was not attempted).
  RF-05 guards live in `tests/mode4_corrective/test_rf05_claims.py`.
- **Disk cleanup (2026-09-18)**: `git gc --prune=now` (832M→661M .git), removed regenerable
  `.cache/lab0{4,8,9}_*`/`numba`/`te_*` intermediate caches for COMPLETED historical phases
  (70M→13M, gitignored, regenerates on demand — never rerun those phases though), and
  hardlink-deduplicated byte-identical files inside `evidence/time_edge_validation_v4/runs/`
  (mostly the same synthetic 5-symbol world parquet copied across many timed-out shard attempts
  before the identity-keyed compute cache existed) — verified by sha256 before linking, same
  inode after, zero bytes deleted, ~2.0 GB reclaimed. All targets were gitignored; nothing
  git-tracked changed. Host disk: 6.7G→8.8G free. Do not delete (only dedupe) anything under
  `evidence/` — hardlinking is fine (content/path/hash unchanged); the explicit rule below still
  says never delete a large evidence tree.
- The lab marker keeps `study_id=crypto_regime_timeedge_v2` (LAB-01 bootstrap evidence; not
  rewritten).
- **Time-Edge study (TE, `study_id=time_edge_validation_v4`)** runs between RF-05 and RA:
  registration in `configs/time_edge_validation_v4/`, code in
  `src/crypto_regime_lab/time_edge/` + `experiments/dynamic_fold_provider.py`, evidence under
  `evidence/time_edge_validation_v4/`, handoffs `handoff/SESSION_TE_CURRENT.md`,
  `TE_MASTER_PLAN_V1.md/.json`, `TE_PHASE_PLAN_V1.md`, `TE_CLI_RUNBOOK.md`. Ledger
  `TE02-PILOT-R03` had budget 300000s with ~134542s remaining at RA-01 lock (2026-09-18); the
  orphan RUNNING row (`bc9d8951…`) was then reconciled as FAILED at its reservation (commit
  `7d1b2e5a`), so spent is now 193557.8s, **~106442s remaining**. Reread the ledger before
  admitting any new job — do not reuse either number without checking it live. Its binary/run
  outputs are largely gitignored (manifests, ledgers and small JSON stay in git); large untracked
  evidence trees are left alone, not committed wholesale and **never deleted — dedup by hardlink
  is fine (content/path/hash unchanged), delete is not**.
- **RA study (`study_id=regime_time_edge_ra_v1`, new namespace)**: current phase work per
  RA-GUIDE-1.0. Evidence dirs `evidence/regime_time_edge_ra_v1/<run_id>/`; code
  `src/crypto_regime_lab/ra/`; tests `tests/ra_corrective/` (183 tests, green: 14 RA-01 + 23 RA-02
  (10 C-cases + 13 gates) + 29 RA-03 (12 M-cases + 17 gates) + 24 RA-04 (9 Q-cases + 15 gates) +
  22 RA-05 (8 D-cases incl. D01b + 14 gates) + 30 RA-06 (15 P-cases + 15 gates) + 41 RA-07
  (23 R01-R09 cases + 18 gates)).
  RA-01/RA-02/RA-03/RA-04/RA-05/RA-06/RA-07 all complete; **RA-08 needs its own owner approval
  before starting** (R-18 — the RA-06→RA-07 approval in `owner_decisions.jsonl` does not extend
  to RA-08; check the ledger's LAST entry covers the transition you're about to start, never
  assume an earlier one still applies). The user has also asked to revisit/challenge the
  assumptions made across RA-05/06/07 before RA-08 starts — do not treat RA-07's own conclusion
  as final or push toward RA-08 unprompted. Sequence:
  RA-01 lock (done) → RA-02 semantic cache (done) → RA-03 memory/fast routes (done) → RA-04 Mode 4 support/admission (done) →
  RA-05 4-arm discovery (done) → RA-06 panel/refit-vs-keep (done) → RA-07 replication/falsification (done) →
  RA-08 freeze/claims.
  `handoff/RA_EXECUTION_PLAN_V1.md` is the committed plan (written when only RA-01 was approved;
  RA-01 through RA-06 are now all done — the file's own prose is stale on that point, its per-phase
  task lists are not). Still one phase finished → report → owner review before the next, per
  R-18. `M4_CAL_MATCHED` is the canonical CAL_BUDGET arm id — do not create a second economically
  identical arm.
- **RA-05 is COMPLETE, technical_gate PASS, 5/5 gates** (final run
  `ra05-20260918T201236Z-de11db62`, 2026-09-18; 4 earlier same-day attempts kept append-only —
  2 smoke-scale dry runs and 2 real full-scale runs that surfaced real bugs before this one).
  **The first real economic comparison in the RA track**: real BTCUSDT 1m bars
  (`snapshots/server_core_v1/manifest.json`) and real regime emissions
  (`evidence/time_edge_validation_v4/host-emissions-03.json`, the SAME 29-vintage JM/M0 ladder
  F-05 measured — reused, not re-fit), all four arms (STATIC/M4_CAL/M4_CAL_MATCHED/M4_REGIME)
  through the SAME `dynamic_fold_provider.run_cutoff_walk_forward` (RF-04-proven, real per-fill
  "event" route for A-SC), differing only in `schedule`. Phase-owned scale (90-day window
  2021-01-01→2021-04-01, 45-day rolling train memory vs the registered 180, 8 trials/cutoff vs
  50) — explicitly disclosed as not the full registered 50-trial/multi-year contract, matching
  RA-02/03/04 precedent. `research_status: DISCOVERY_ONLY` throughout — no CI/claim-gate verdict
  offered (this pilot's window does not clear the registered ≥365-day confirmatory floor,
  RA01.4's migration table); that machinery belongs to RA-07.
  **F-06 re-audited at its own cited source** (`time_edge/schedule.py::triggers`,
  confirmations=2): 1 accepted trigger on the real window, vs 2 via the function that actually
  drives M4_REGIME (`experiments.regime_schedule.online_trigger_schedule`, no confirmation
  requirement) — a real, reported divergence between two real scheduler implementations on the
  same data, not an error. **CAL_MATCHED's cadence forecast** used a development prefix
  disjoint from the evaluation window (747 real days, 16 real triggers outside
  `[2021-01-01, 2021-04-01)`, rate 0.0214/day → predicted 1.93 triggers in-window → menu choice
  **56 days**, vs M4_CAL's fixed 60) — verified by a dedicated test (D02) that mutating the
  window's OWN realized emissions changes nothing about the forecast.
  **Real mechanism result** (descriptive only, no claim): all four arms shared the identical
  fold-0 selection (guide 3.1's requirement, verified); M4_CAL and M4_CAL_MATCHED's fold-1
  landed on the same winning params despite different cadences (60d vs 56d), while M4_REGIME's
  event-triggered refreshes (2021-02-02, 2021-03-19) picked genuinely different params — real
  action divergence, independent of PnL. `STOCK_MODE4_PLUS_ADMISSION_V1` (RA-04) fired for real
  on M4_REGIME's 2nd opportunity (`KEEP_INCUMBENT`, "only 1 finite subperiod shards of 3, need
  >= 2"), the first real deployment of the guard outside RA-04's own tests. Returns (point
  estimates, 1-3 folds/arm — not a claim): STATIC +4.34%, M4_CAL +3.38%, M4_CAL_MATCHED +2.63%,
  M4_REGIME +4.30%.
  **4 real bugs found and fixed during build, each with its own regression test**: (1) STATIC's
  schedule builder silently defaulted to the registered 180-day train memory instead of the
  phase's own `train_memory_days`, violating guide 3.1's shared-initial-selection requirement —
  caught by D01, which now pins `static.train_memory_days == cal.train_memory_days ==
  regime.train_memory_days`; (2) `run_one_arm` did not catch `run_cutoff_walk_forward`'s early
  precondition raises (`ProviderError` on an empty schedule executes before that function's own
  try/except), which would have aborted the whole 4-arm comparison instead of recording one
  arm's failure — caught by D07; (3) `TrainingScorer`'s candidate cache (keyed only by
  `digest(params)`) collided across different (arm, fold) pairs that coincidentally selected
  byte-identical params at different cutoffs — a real full-scale run crashed on
  `ContractError: partial candidate cache identity drift`; fixed with a per-(arm,fold) cache
  subdirectory; (4) `classify_regime_trigger_reasons` compared consecutive CHOSEN CUTOFFS'
  states directly instead of replaying every eligible emission in between (as
  `online_trigger_schedule` itself does), silently mislabeling both real `SEMANTIC_STATE_CHANGE`
  triggers as `MAX_AGE` — caught by cross-checking a completed real run's own `deployed_source`
  against the funnel's labels, not by any test at the time; fixed and given a dedicated
  regression test (D01b) using the real 90-day window, since D01's own 7-day smoke window
  contains no real trigger and would pass the same check vacuously.
  Raw financial artifacts at TE paths are referenced by path/hash, not copied.
- **RA-06 is COMPLETE, technical_gate PASS, 4/4 gates** (final run
  `ra06-20260919T035313Z-59cd3ae0`, 2026-09-19; earlier same-day smoke/dry-run attempts kept
  append-only). `research_status: INCONCLUSIVE_SUPPORT` — the guide's own explicitly-sanctioned,
  non-financial-claim mechanical PASS.
  **Panel A** (guide 10.1) reused RA-05's real evidence directly — 8 rows, 4 unique candidates,
  0 new engine calls, each row's matured outcome sliced from the arm's own real
  `equity_daily` over its real deployment window.
  **Panel B** (guide 10.1/10.2/10.3) is new: real KEEP-vs-REFIT branches at 5 real origins (a
  disclosed, budget-conscious reduction from guide 10.3's "8-12 origins if budget allows"
  ceiling), via a **deterministic replay prefix** through `run_cutoff_walk_forward` — confirmed
  by inspection that no native QuantBT checkpoint/clone-state capability exists in this install
  before choosing that path (guide 10.3's own sanctioned fallback). KEEP = one continuous real
  account (`schedule=[window_start]`, RA-05's STATIC arm's own selection, never refits) covering
  every origin's KEEP reading in one pass; REFIT = one real account per origin
  (`schedule=[window_start, origin]`) — the same initial selection reproduced deterministically
  plus one real search exactly at the origin. All 5 origins measured OK, 0 censored.
  **Real g_t(H) result** (28-day horizon, point estimates only — `research_status` forbids a
  claim): REFIT underperformed KEEP at 4 of 5 origins (g = −0.00033, −0.00522, −0.01202,
  −0.01344) and outperformed at 1 (+0.00281) — directionally consistent with the rest of this
  lab's pattern (no robust refit/timing benefit found anywhere so far), but N=5 is far too small
  to treat as anything but descriptive.
  **Model ladder** (guide 10.5/10.6): `INSUFFICIENT_SUPPORT` (support=5 <
  `MIN_SUPPORT_FOR_MODEL_FIT=8`) — AGE_ONLY/AGE_CONTEXT ridge fit (hand-rolled closed-form, no
  sklearn in this venv) correctly not attempted on a sample the guide itself says is too small
  to trust. **G06-SCOPE lock decision: `KEEP_BASELINE`** (current JM/M0 reference policy
  unchanged) — no context-policy revision carried to RA-07, exactly guide's "or KEEP_BASELINE
  with a reason" branch.
  **A real, load-bearing bug found and fixed while building this phase**: `E_t` (guide 10.2's
  "common equity before decision") read on the origin's OWN calendar day disagreed between KEEP
  and REFIT (e.g. keep=20640.20 vs refit=20677.36) despite a byte-identical shared prefix —
  because REFIT's new fold's `test_start` IS the origin, so that whole day already carries a day
  of NEW-params trading for REFIT while KEEP's reading is still old-params. Root-caused by direct
  inspection of both branches' real `equity_daily`/fold tables (not guessed), fixed by reading
  `E_t` strictly BEFORE origin, verified the two branches' `E_t` then match exactly at all 5 real
  origins. P02 is the regression test. A second, minor bug (bare date strings passed to
  `CutoffSchedule`/timestamp comparisons without an explicit UTC offset, in three separate spots)
  was caught by the same `--smoke` dry-run discipline RA-05 established, before it ever reached
  a real full-scale run.
- **RA-07 is COMPLETE, technical_gate PASS, 6/6 gates** (final run
  `ra07-20260919T071527Z-4463ccde`, 2026-09-19; 4 earlier same-day attempts kept append-only —
  1 crash caught by `--smoke` before any real-scale run, 2 smoke runs that surfaced a
  report/verify ordering bug, 1 smoke PASS). `conclusion_level: INCONCLUSIVE_SUPPORT` on the
  registered vocabulary (guide 13.5) — the guide's own sanctioned outcome for a ~90-day pilot,
  not a surprise.
  **RA07.1 freeze** (before any RA-07 outcome existed): delta materialized from cell 1's real
  fills (guide 13.3's formula, `|N_j|/E_j-` summed per day * 0.0005, flat days kept in the
  denominator) = **0.0001452/day** (≈1.45 bps/day) over 151 calibration days; MDE from cell 1's
  own real paired-return bootstrap SE (guide 13.6, never a synthetic-noise scale) =
  **0.000245/day** (≈2.45 bps/day) — **the MDE is LARGER than delta itself**, meaning this
  pilot's own sample cannot reliably resolve an effect the size of its own calibrated hurdle; said
  plainly in the report, not glossed over. RF-05's unrelated 0.0371 bps/day MDE (different
  contract: window/train_memory/seed all differ) is cited only as a cross-reference, never
  substituted.
  **Cell 2** (RA07.2): A-SC/ETHUSDT, RA-05's EXACT frozen contract (same window/train_memory/
  trials/seed/route) with only the symbol swapped — deliberately NOT RF-04's own earlier
  A-SC/ETHUSDT numbers, which used a different window/train_memory/seed and would have mixed
  contracts in a paired comparison. Explicitly a cross-symbol transfer test (BTC-derived regime
  tape used to trade ETH), not an ETH-fit regime claim. Coverage matrix: 2 RUN_VALID / 10
  BLOCKED_CAPABILITY (A-VWAP/A-HASH, reused verbatim from RF-04's route matrix) / 8 NOT_RUN_BUDGET
  of 20 planned cells.
  **Controls** (RA07.3): AGE_ONLY is `NOT_APPLICABLE` (RA-06 locked KEEP_BASELINE, nothing
  action-aware to contrast). DELAYED_INFORMATION (state availability delayed 1 observation/4h,
  `state_id`+`state_namespace`+`state_common` all shifted together) landed on the IDENTICAL 3
  cutoffs as the real M4_REGIME schedule in this window — equity_last 20859.34, byte-identical to
  M4_REGIME's own — a real but WEAK test at this delay size (too small to reschedule anything
  here), not evidence the edge survives a meaningful delay. **PLACEBO_TIMING is the load-bearing
  finding**: a seeded synthetic state tape (switch-rate 0.964x the real one, `matched=True`, not
  a strawman) reached equity_last **20822.54** — essentially matching M4_REGIME's real 20859.34
  and far above M4_CAL_MATCHED's 20526.79. A placebo carrying NO market information reproduces
  nearly all of M4_REGIME's apparent advantage at matched cadence — directly echoing LAB-08's
  STATE_PLACEBO finding, now reproduced independently in the RA track.
  **D1/D2/D3 decay** (RA07.4, 41 rows: 28 D1 + 5 D2 + 8 D3): D1 (one cheap deterministic
  `TrainingScorer` replay per fold against RA-05's own real fold table, zero new search) shows
  OOS < IS in 11 of 14 mean-daily-return rows — the selection-bias decay guide 13.2 warns to
  expect, now measured rather than assumed. D2 (RA-06 Panel B's fixed-theta KEEP anchors, 0 new
  engine calls) shows no clean aging pattern (+0.46%, +2.92%, −0.07%, +0.98%, −0.03% across 5
  successive 20-day segments). D3 (adjacent operational folds, different params, `diagnostic_only`)
  is descriptive only, never read as decay of one theta.
  **Bootstrap statistics** (RA07.5, zero engine calls anywhere — verified by a source-inspection
  test, not assumed): circular moving block bootstrap, 28-day primary block, 5000 resamples, seed
  20260919, verified against a synthetic numeric-reference check (known true delta, known analytic
  SE) before being trusted on real data. Primary contrast (cell 1 H-BUDGET, M4_REGIME −
  M4_CAL_MATCHED): point estimate **+0.0001075/day**, CI_95 **[−0.0000234, +0.0003038]**,
  p=0.1684 → `INCONCLUSIVE_SUPPORT` (only 5 blocks of 28 days vs the 12-block legacy floor — a
  floor, not proof of power, guide 13.6 — and the CI still straddles the calibrated delta
  regardless). Secondary Holm family (guide 13.4, primary itself left unadjusted): cell1
  M4_REGIME−M4_CAL p=0.4472, cell1 M4_CAL_MATCHED−M4_CAL p=0.1452→0.2904 adjusted, cell2 transfer
  check p=0.0788→0.2364 adjusted — none reach significance.
  **Sensitivity** (RA07.7): cell1_alone and cell2_alone point estimates have the SAME sign
  (+0.0001075 and +0.0000656/day) but no pooled 2-cell aggregate is computed (no pre-registered
  capital weighting exists with only 2/20 cells run — guide RA07.2 forbids one otherwise).
  **3 real bugs found and fixed while building this phase**: (1) D1's `daily_returns` cache field
  is a list of `(date, value)` PAIRS, not bare scalars — a naive `if r is not None` filter would
  have kept every row (a tuple is never `None`) and summed/averaged the tuples themselves; caught
  before any run, not by a crash. (2) The first `--smoke` attempt crashed
  (`ContractError: incomplete requested account window`): `cell1_arms` always comes from RA-05's
  real, full-scale evidence (never re-run), but D1's replay frame and delta's fill `bar_index`
  resolution were loaded at THIS run's own smoke-or-real scale — in `--smoke` mode the two frames
  start on different dates, so the same `bar_index` silently pointed at a different calendar day.
  Fixed by always loading cell 1's D1/delta frame at RA-05's own real window, independent of
  `--smoke` (verified: in the non-smoke real run these two loads are identical, so the fix only
  changes smoke behavior). (3) `report.md`'s own `conclusion_level` text was written AFTER the
  verify call that produced `verification.json`, so `G07-CLAIM` failed structurally on the
  `PENDING_VERIFICATION` placeholder regardless of content — fixed with a two-pass verify/write so
  the persisted verdict and the report's own displayed gate table agree.
  `experiments/controls.py`'s `delayed_states` is deliberately NOT reused unmodified for
  DELAYED_INFORMATION: it only shifts `state_id`/`state_namespace`, but this lab's real emissions
  always populate `state_common`, which the trigger logic reads FIRST — a local, schema-correct
  `delayed_emissions()` in `ra07_controls.py` shifts all three fields together instead.
- `reports/improvement_opinions.md` = opinions that are **written, never run**, and never mixed
  into results. Do not implement them without the user picking one.
- Lab git: repo on `main`, remote `regime-lab`; corrective work is on **`mode4-corrective`**.
  **Standing rule (user): commit every finished piece of work**, not only at phase ends. Before
  each commit run `git status` + `git diff`, stage only the intended files, and keep one scoped
  purpose per commit. Never commit the venv or secrets. Push only when explicitly asked.

## Environment and commands

Run from the lab root. Use only the lab venv — never the shared `/root/bobby/pool_alpha/.venv`.

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q            # currently 1243 passed
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/test_x.py::test_y -q
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q   # 76 passed (RF guards)
$LAB/environments/lab_venv/bin/python -m pyflakes src scripts tests     # clean except src/.../alphas/raw-supplied/
PYTHONPATH=src $LAB/environments/lab_venv/bin/python -m crypto_regime_lab.cli <stage> --lab-root $LAB
$LAB/environments/lab_venv/bin/python scripts/<runner>.py               # scripts insert src/ themselves
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01.py           # regenerate RF-01 artifacts (--force to supersede)
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01_regressions.py --full
$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf01_report.py  # renders evidence/corrective_mode4_v3/RF-01/report.md
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf05.py --force   # RF-05 freeze/recompute/claims/integrity/handoff (no engine call)
$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf05_report.py --force  # report.md/json + integrity/repro refresh
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra01.py           # RA-01 baseline lock (writes evidence/regime_time_edge_ra_v1/<run_id>/)
$LAB/environments/lab_venv/bin/python $LAB/scripts/verify_ra01.py        # thin verifier over the RA-01 run dir
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra02.py --pytest-xml <junit of tests/ra_corrective>   # RA-02 semantic cache
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra03.py --pytest-xml <junit of tests/ra_corrective>   # RA-03 lazy prep/retention/route/profiler
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra04.py --pytest-xml <junit of tests/ra_corrective>   # RA-04 Mode 4 support/admission/controls
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra05.py --pytest-xml <junit of tests/ra_corrective>   # RA-05 4-arm discovery (real data); --smoke for a tiny/fast dry run
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra06.py --pytest-xml <junit of tests/ra_corrective>   # RA-06 panel/refit-vs-keep (real data); --smoke for a tiny/fast dry run
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra07.py --pytest-xml <junit of tests/ra_corrective>   # RA-07 cell2/controls/decay/bootstrap (real data); --smoke for a tiny/fast dry run
$LAB/environments/lab_venv/bin/python $LAB/scripts/record_owner_decision.py --decides "RA-0N->RA-0M" --quote "<verbatim>" --reference "<where>"  # append to owner_decisions.jsonl
$LAB/environments/lab_venv/bin/python $LAB/scripts/check_p0_gate.py      # P0 gate from handoff/te_specs
$LAB/environments/lab_venv/bin/python $LAB/scripts/supervise_te_controls.py  # TE controls supervisor (charges the ledger)
```

- The full suite takes ~4–5 minutes; run long jobs in the background and read the log.
- The latest authority for runbooks is `handoff/TE_CLI_RUNBOOK.md` and
  `handoff/RA_EXECUTION_PLAN_V1.md` (RA phases); the RF/LAB scripts above remain valid for
  regeneration and audits (`scripts/audit_*.py`).

- `python -m crypto_regime_lab.cli` needs `PYTHONPATH=src`; pytest gets it from `tests/conftest.py`.
- Rebuild the venv with `scripts/bootstrap_lab.py` + `configs/requirements.lock`; `environments/`
  and `wheelhouse/` are gitignored and machine-specific.
- Audits that gate the reports: `scripts/audit_assertion_vacuity.py`,
  `scripts/audit_guard_strength.py`, `scripts/audit_forbidden_claims.py`,
  `scripts/audit_evidence_pointers.py`, `scripts/audit_lab09.py`.
- **Report `git -C /root/bobby/pool_alpha/quantbt status --porcelain` at the end of every reply**
  (user rule 12). State the result plainly; if anything was touched, say so immediately.

## Hard boundaries (violating these invalidates the lab)

- **All writes stay inside `LAB_ROOT`.** `../quantbt`, `../alphas_storage` (loader + storage), and
  the four supplied alpha files are strictly read-only: no edits, no `pip install -e`, no builds,
  no git write commands, no `chmod`/`sudo`. Lab-only patch ideas go in `handoff/lab_only_patch.diff`
  as proposals.
- QuantBT comes from the lab venv install. Never invent an endpoint — map it in
  `configs/api_binding_map.json` or record `BLOCKED_CAPABILITY`.
- Network is off during `run`/`certify`/`report`. Missing data is reported as missing, never fetched
  or zero-filled.
- **Never call `data_loader.py` at run time.** The lab parses it statically for path routing and
  reads its own byte-copied parquet under `snapshots/` directly; the pinned loader's int64 volume
  cast corrupts fractional-volume symbols (measured in `reports/data_sources_used.md`).
- Point every cache inside the lab; set `PYTHONDONTWRITEBYTECODE=1` in processes touching protected
  source.
- Gitignore policy (commit 4ab071c): **all binary data files are ignored repo-wide** (`*.parquet`,
  sqlite side-files, run-output market data over the GitHub size limit); manifests, ledgers,
  receipts and small JSON stay in git. Never force-add large binaries; record the path/hash instead.

## Repo conventions an agent would otherwise get wrong

- **Reports are generated, not written.** `scripts/write_lab0N_report.py` renders
  `reports/lab0N_report.md` from committed artifacts only; never hand-edit a number. Tests assert
  the figures appear in the markdown, every report has a glossary defining its terms, and the
  registered primary endpoint (`configs/study_registration.json`) + minimum economic effect
  (`configs/minimum_economic_effect.json`) are used — not a more convenient statistic.
- **Registrations precede runs.** Hypothesis IDs, contrasts, conclusion-level vocabulary, seeds,
  cost multipliers and budgets are fixed in `configs/` before measurements; check timestamps
  (`registered_at_utc`) when adding anything. A conclusion level must come from the registered
  vocabulary; a blocker caps the claim.
- **Evidence is append-only and strict JSON**, `lab_run_id` on every artifact, `null` + reason for
  missing metrics. A `NOT_READY` alpha keeps null metrics — never PnL = 0. Corrections are recorded
  in `configs/correction_ledger.json`, and a superseding run must be later, not nicer.
- **Checklists are written before code** (`configs/lab0N_checklist.json`); audits read them.
  Keep tests mapped to the T01–T64 acceptance IDs; `tests/` are the acceptance gates.
- **A green gate is not proof.** Most past defects were checks that passed because nothing
  happened: `all([]) == True`, a key defaulting to `0.0`, a probe handed its own answer. New
  verdicts must carry a denominator and a way to go red. Use the `lab_tmp` fixture for scratch
  files that go through the read guard — pytest's `tmp_path` is outside `LAB_ROOT` and is refused.
- **Separate the four validity axes** (RA guide §0.2): technical validity, scientific support,
  economic evidence and owner approval are independent; a positive ranking-IC, switches > 0 or
  positive PnL is never a condition for opening technical discovery. Gate redesign goes through
  `protocol_migration` (old rule → new rule → reason → affected claims/tests); never edit the
  acceptance of an old run to make it green. Keep historical runs, invalidations, costs and
  previous negative/null results raw and untouched.
- **quantbt cost binding**: `fee` is round-trip; pass the one-way rate as `fee_rate=` (or
  `fee=2*one_way`). The fee defect above cost the whole study its validity.
- The deflated corners: `src/crypto_regime_lab/alphas/raw-supplied/` fails pyflakes by design;
  `snapshots/**/*.parquet`, `environments/`, `wheelhouse/`, `.cache/` are gitignored but
  regenerable.

## Architecture in one paragraph

`src/crypto_regime_lab/` layers: `safety` (path guards, sandbox, source integrity), `data`
(byte-copied parquet panels), `alphas` (4 adapters × version tiers, raw-supplied bytes are
provenance-only), `selector` (robust neighborhood + candidate bank), `regime` (sparse jump-model
state inference), `response` (parameter-response), `policy` (four-clock activation), `experiments`
(factorial arms A–E + `dynamic_fold_provider.py`), `time_edge` (Time-Edge v4 study: allocations,
controls, discovery, funnel), `ra` (RA study: admission rules + thin phase verifier),
`integration` (continuous-account delivery), `quantbt_bridge` (the lab-owned
facade over the installed engine), `evidence` (atomic JSON writer). Arms: A = installed WFO +
calendar, B = neighborhood selector + calendar, C = installed selector + regime-triggered refresh,
D = both, E = bank + response policy. Primary matrix = 4 alphas × 5 symbols = 20 cells; A-HASH is
NOT_READY in all 5.
