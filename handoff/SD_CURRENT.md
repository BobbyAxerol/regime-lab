# SD_CURRENT

Current source/runtime and approved registration:

| Phase | Technical | Research/scope | Owner | Evidence |
|---|---|---|---|---|
| SD-01 | PASS (7/7 gates) | NOT_ASSESSED — measurement infrastructure + real archive only, no model fit yet | PENDING (SD-02 needs its own R-18) | `evidence/sharpe_decay_sd_v1/init_archive/` |
| SD-02 | not started | — | — | — |
| SD-03 | not started | — | — | — |

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
