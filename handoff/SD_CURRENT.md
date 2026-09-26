# SD_CURRENT

Current source/runtime and approved registration:

| Phase | Technical | Research/scope | Owner | Evidence |
|---|---|---|---|---|
| SD-01 | PASS (7/7 gates) | NOT_ASSESSED — measurement infrastructure + real archive only, no model fit yet | APPROVED (`dec-cefc167978e6c207`) | `evidence/sharpe_decay_sd_v1/init_archive/` |
| SD-02 | PASS (6/6 gates) | NOT_ASSESSED; recipe RECIPE_SELECTED c=2.0 but DEGENERATE (all 3 recipes pick the identical candidate at every real fold) | APPROVED (`dec-9a35219678adf611`, `dec-c94ea602aeac0f1a`, `dec-c0c54ebc355b112b`) | `evidence/sharpe_decay_sd_v1/validation_folds/` |
| SD-03 | not started | — | APPROVED (`dec-c0c54ebc355b112b`, "phase 3 ... chưa thì làm luôn") | — |

## SD-02 complete (2026-09-26)

**Real 12-fold VALIDATION run**: `scripts/run_sd02_validation.py` ran fully detached
(`setsid nohup ... & disown`), 12/12 real folds, `total_wall_seconds=33666.11` (~9.35h),
peak RSS 1869.5 MiB (within the 4096 MiB budget, no exception needed). Verified alive
mid-run via CPU-time deltas (process time advancing 1:1 with wall clock) and per-fold
file timestamps, not merely `ps` presence.

**Verification (guide SS9.5, `sd/verifier_sd02.py`)**: all 6 G2-* gates PASS, independently
re-derived from the raw `fold_*.json` records (the orchestrator itself writes no
pass/fail judgment) — `G2-ML-VALID` (anchor Y_hat=0 in every arm's own scored table,
zero vacuous checks), `G2-VAL12` (12/12 paired-valid folds for every recipe),
`G2-INDEPENDENCE` (every conditional arm scored a full panel even at real B-anchor
folds, non-vacuous), `G2-RELEVANCE`, `G2-FREEZE` (frozen recipe matches an independent
recomputation), `G2-OWNER`.

**Recipe selection (guide SS5.8)**: decision `RECIPE_SELECTED`, c=2.0, mean_R=0.4052
Sharpe points (>= the registered 0.2 threshold) — **but disclosed as DEGENERATE**: all
three penalty designs (c=0.5/1.0/2.0) selected the byte-identical candidate at every
one of the 12 real folds, checked directly against each arm's own `winner_id` (not
inferred from the mean_R average). The underlying JM state genuinely differs across
recipes at 1/12 folds (proving the mechanism is live, not a code defect), but that
difference never flipped which candidate minY picked. The guide's own tie-break rule
correctly picked the larger c among tied designs — `RECIPE_SELECTED, c=2.0` must NOT be
read as evidence a stronger persistence penalty helps; R never differed by c on any real
fold. This is the same shape this lab's history keeps finding (LAB-08 Arm E=Arm D,
FP-07 C=B degenerate).

**Real per-fold pattern**: A_M4 is always the anchor (by construction). B/R_RULE/JM
move together — 3/12 folds all fall back to the anchor, 9/12 all pick the identical
non-anchor candidate. Full lab suite after SD-02: verification in progress (launched
in background), sd-only suite: **153 passed**.

**Freeze**: `configs/sharpe_decay_sd_v1/sd02_freeze.json` — c=2.0, lambda_global=10.0,
lambda_state=10.0, K=2, panel-only candidate scope, recipe_degeneracy disclosed inline.

## SD-02 in-progress state (2026-09-25, mid-build)

All model-layer CODE is built and tested (114+ new SD-02 tests, all green,
pyflakes clean): `jm_features.py`, `jm_model.py` (Statistical Jump Model K=2,
verified prefix-by-prefix causal-filter parity), `jm_vintage.py` (per-origin
causal tapes, measured raw-prehistory shortfall on 4/12 INIT origins),
`daily_bars.py`, `contrast_features.py`/`ridge_contrast.py`/`model_bc.py`
(intercept-free contrast ridge B + state-conditioned residual correction C),
`r_rule.py`, `candidate_descriptors.py`, `training_rows.py` (wires in the
REAL, verbatim-reused `fp.chronology`/`fp.forward_ledger` causality guard),
`fold_scoring.py`, `recipe_selection.py` (guide SS5.8's locked rule),
`model_quality.py` (MAE(Y), rank diagnostic, state occupancy/dwell/recurrence).

**Owner decision `dec-c94ea602aeac0f1a` (2026-09-25, via AskUserQuestion):**
B/C/R_RULE select among the SAME <=16-candidate representative panel + anchor
SD-01/SD-02's own archive already forward-evaluates at each origin, NOT the
full raw ~100-115-candidate unique-candidate pool -- avoids an estimated
~10h of new, undisclosed real engine compute. Revises `protocol_migration.
json`'s F03b disposition (dated `scope_revision_sd02_20260925`, original
text preserved verbatim, never rewritten). Full protocol registered in
`configs/sharpe_decay_sd_v1/sd02_model_protocol.json`.

**A real, load-bearing bug caught before running real compute**: the
orchestrator's `ratio_by_origin` dict was silently DROPPING origins with
insufficient raw prehistory instead of keeping them mapped to `None`, which
would have crashed `training_rows.retag_states`'s missing-key guard the
moment R_RULE tried to tag INIT's 4 known-short origins during the real
12-fold run. Fixed in `scripts/run_sd02_validation.py` (three call sites)
before any real compute was spent on it.

**INIT-side prep** (SD02.1/2.3, zero new engine compute, real I/O only):
- `evidence/sharpe_decay_sd_v1/sd02_model/init_jm_tapes.json` -- REAL, 3
  recipes x 12 origins, 24/36 OK (8/12 per recipe), 12/36
  `INSUFFICIENT_RAW_PREHISTORY` (exactly the 4 measured-short origins x 3
  recipes) -- complete.
- `evidence/sharpe_decay_sd_v1/sd02_model/init_descriptors.json` (real
  activity_entries backfill via guaranteed cache-HIT re-fetch) -- IN
  PROGRESS as of this note, checkpointed per-origin under
  `init_descriptors_partial/`, running fully detached
  (`setsid nohup ... & disown`, matching the pattern proven to survive a
  session restart in SD01.7/FP-04). A first attempt was accidentally killed
  by my own `timeout 900 | tail` piping (which buffers all output until
  EOF, so nothing appeared before the kill) -- fixed by adding per-origin
  checkpointing to `scripts/run_sd02_descriptors.py` and relaunching
  properly detached with direct-to-file logging.

**Not yet run**: the real 12-fold VALIDATION build (`scripts/
run_sd02_validation.py`, SD02.4) -- 12 real 128-trial searches, the major
real-compute commitment of this phase (~9-12h, per SD01.6's own already-
measured extrapolation for the identical search scale). Will launch fully
detached once the descriptor backfill completes and a synthetic-data smoke
test of the orchestrator's core scoring loop passes clean.

## Latest actual run and parent upgrade

SD-01 is the first and only phase run so far. Branch `research/sharpe-decay-sd-v1`,
created off `main` @ `f22851db5761eac828b663d19b6e2b74c9e60c74` (main's tip immediately
after FP-01..10 merged in). Parent study: `forward_persistence_fp_v1`.

## Known facts with evidence

- Guide SD-GUIDE-1.0's own SS0.2 finding table (F02, F03a, F03b, F05, F05_F06_model, F07,
  F04, F10) all have a disposition in `configs/sharpe_decay_sd_v1/protocol_migration.json`.
  Three (F03a, F03b, F05) were independently re-verified against the actual committed FP
  source before being marked `PRESENT`, not copied from the guide's own compressed summary.
  A fourth defect (`SELF01_RIDGE_INTERCEPT`) was self-discovered during SD01.5 design, not
  named anywhere in the guide's own table: `fp/selector_b.py`'s `fit_ridge` has a
  de-meaned-y intercept, incompatible with SD-GUIDE-1.0 SS5.5's explicit "no intercept,
  anchor prediction = 0 by construction" requirement.
- Timeline feasibility (`configs/sharpe_decay_sd_v1/timeline.json`): SD's own strict
  12 INIT + 12 VALIDATION + 12 FINAL (56-day non-overlapping forward windows/role) + 56-day
  D2 design needs >=2252 days with zero scheduling gaps; `development` role alone
  (2020-01-01..2023-12-31, 1460 days) is 792 days short with no guide-compliant way to close
  the gap by tightening INIT spacing alone. Real BTCUSDT coverage measured to extend to
  2026-09-09 (2438 days usable). Owner approved a disclosed, one-time, scoped exception to
  open `outer_evaluation` for `sharpe_decay_sd_v1` ONLY (`dec-61772d86c9594c69`) — does not
  reopen it for `forward_persistence_fp_v1` or any RA/RF study. Exact 36 origin dates frozen
  before any outcome: INIT fully inside `development`, VALIDATION mostly (tail crosses into
  `outer_evaluation`), FINAL entirely inside the genuinely fresh 2024-2026 span, 172 days of
  disclosed margin.
- Real 8-trial micro-profile (SD01.6): 225.05s, peak RSS 1019.4 MiB (registered 4 GiB budget,
  no exception needed). Extrapolated 9.0-12.0h for the full 12-origin/128-trial build,
  cross-checked against FP-03's own real 256-trial measurements.
- Real 12-origin INIT archive (SD01.7): 12/12 origins built, real 128-trial search each
  (never a hand-rolled objective — `fp.checkpoint_search.run_origin_search`, the same real
  engine call FP-03/04/07..09 already depend on), real canonical IS180/FWD56 Sharpe for a
  16-candidate representative panel + anchor at every origin (reusing
  `fp.evaluator.evaluate_candidate` verbatim — same cache kind as FP, a legitimate
  cross-study cache-hit opportunity, never a target-definition conflation). Total wall
  31817.97s (~8.84h, search-only ~6.98h). 192/192 IS Sharpe status OK, 192/192 FWD Sharpe
  status OK, 12/12 anchor `relative_decay_Y == 0.0` exactly (anchor-zero-by-construction
  verified on every real origin). Peak RSS 1987.3 MiB throughout, well within budget, no
  exception needed. Ran as a fully detached background process (`setsid nohup ... & disown`)
  and survived a complete interactive-session restart mid-run undisturbed — 9 of this
  session's own Monitor watch tasks were killed by the session death, the actual archive
  build process was untouched.
- Full lab suite after SD-01: **1578 passed, 0 failed** (42 new SD-01 tests, all green).

## Missing/invalidated evidence

- The external audit `REGIME_LAB_FP01_FP10_OBJECTIVE_AUDIT_VI.md` (SS0.1's own [I1] source,
  archive SHA-256 `ce9bb179af6ba3bba4df4608a8e6c4a2c86f9ed633ca530e310a032fc958c6c1`) is NOT
  present in this lab's directory — requested from the owner, disclosed in
  `protocol_migration.json`'s `missing_source_note`. Findings F02/F03a/F03b/F05 were
  independently re-derived from real source instead and are therefore CONFIRMED regardless;
  F04/F07/F10's dispositions rely on the guide's own compressed table and should be revisited
  against the full audit text if the owner provides it.

## Archive/validation/final paired-fold counts

- INIT: 12/12 origins built (this phase). VALIDATION: 0/12 (SD-02's job). FINAL: 0/12
  (SD-03's job). D2: not started.

## Model support / correction / fallback usage

Not applicable yet — SD-01 builds no model. SD-02 fits the first real global ridge + JM
residual correction against this real archive's 192 label rows.

## Sharpe-decay results and exact claim limits

None. SD-01 makes NO claim about whether JM reduces Sharpe decay. It only builds and
validates the measurement infrastructure (canonical Sharpe wrapper, minY selection rule,
structurally-independent B/C evaluation) and the real candidate archive SD-02 will train
validation-fold models against.

## Remaining budget

Registered 4 GiB / 2 CPU / 1 worker budget, unchanged for every phase/call except the
disclosed `outer_evaluation` data-role exception above (which is a data-scope exception, not
a compute-budget one). SD-01's own real compute: ~8.84h (archive) + ~4min (micro-profile +
integration probes). No resource-budget (RLIMIT_AS) exception was needed anywhere in SD-01 —
peak RSS stayed at ~1987 MiB against the 4096 MiB cap throughout.

## Next authorized action

SD-02 (guide section 9): fit the global contrast ridge (B_SD_GLOBAL) and JM K=2 residual
correction (C_SD_JM) against this real 192-row archive, run the 12 VALIDATION folds
chronologically, choose one JM recipe per guide SS5.8's locked rule, freeze the final
protocol. **Needs its own explicit R-18 owner approval before it begins** — SD-01's own
completion does not carry an implicit go-ahead (guide's per-phase discipline, matching how
every FP-01..10 transition was run).

## Protected worktree status

`../quantbt`: verified clean throughout SD-01 (`git -C ../quantbt status --porcelain`,
checked before every commit) — never touched.
