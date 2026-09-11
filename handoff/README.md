# handoff/

Bounded proposals produced by the lab. **Nothing here has been applied anywhere.**

| file | what it is | status |
|---|---|---|
| `lab_only_patch.diff` | a proposal for `quantbt/optimization/candidate_selection._param_distance` | NOT APPLIED |

## Why this exists

CLAUDE.md rule 1: `../quantbt` is read-only, and any patch idea is written here as a
proposal rather than applied. LAB-04 confirmed three geometry defects in the
`CandidateSelector` family (`configs/lab04_selector_counterexamples.json`, cases
CE-04, CE-05, CE-06), each with a runnable reproducer against the installed
function.

## What is NOT claimed

* The `quantbt.walkforward` record-selector family is **not** affected. It was
  checked and found already correct: `_is_clusterable_param` excludes parameters
  that do not vary, and `_normalize_param_values` normalises by the declared
  `param_ranges`. LAB-04 records that as `VERIFIED_EXISTING_CORRECT`, not as a bug.
* The lab does not depend on this being fixed. `selector/schema_distance.py` uses
  declared-bound geometry, excludes fixed parameters from the denominator and
  charges a locked penalty for a branch mismatch instead of a false coordinate
  distance.
* The diff has not been compiled, tested against the upstream suite, or reviewed by
  the engine's maintainers. It is a starting point for that conversation.

## Verification state

| item | state |
|---|---|
| applied to `/root/bobby/pool_alpha/quantbt` | **no** — that repository is read-only for this lab |
| applied to the installed wheel in `environments/lab_venv` | **no** — the pin `quantbt-engine==1.1.1` / `quantbt-native==0.4.2` is unchanged |
| upstream test suite run against it | no |
| lab tests run against it | no — the lab never calls the patched path |
