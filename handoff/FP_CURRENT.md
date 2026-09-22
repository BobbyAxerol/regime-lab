# FP_CURRENT

## Current source
- run: fp01-20260922T162253Z-3538bb29 (/root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29)
- overall: PASS
- gates: FP01-G-VALIDITY=PASS / FP01-G-IDENTITY=PASS / FP01-G-MIGRATION=PASS / FP01-G-BUDGET=PASS

## Phase state
| Phase | Technical | Research | Owner | Evidence |
|---|---|---|---|---|
| FP-01 | PASS | NOT_ASSESSED | PENDING | evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/ |
| FP-02 | NOT_RUN | NOT_ASSESSED | PENDING (needs R-18 approval) | — |

## Latest run
FP-01 PASS: identity + 9 finding dispositions + migration registration; zero engine calls.

## Post-PASS follow-up (same session, before first commit)
Independently re-ran the FULL lab suite (not just fp_corrective) before committing: 2 of 1268
tests failed, both in tests/mode4_corrective/ (test_rf05_claims.py::test_rf05_freeze_manifest_hashes_match_committed_files,
test_fup04_declaration.py::test_fup04_ceilings_are_consistent_with_what_is_declared) -- a direct,
mechanical consequence of FP-F02's admission_policy parameter changing
src/crypto_regime_lab/experiments/dynamic_fold_provider.py, an RF-05-frozen file FUP-04 had already
superseded once. Registered the second, chained supersession
(evidence/forward_persistence_fp_v1/FP-01/component_supersession.json, registered_study=FP-01,
resolves via configs/forward_persistence_fp_v1/registration.json#/studies/0) covering both
dynamic_fold_provider.py and tests/mode4_corrective/test_rf05_claims.py (touched to register the new
source). test_fup04_declaration.py's own ceiling test could not represent a multi-hop chain at all
(it asserted FUP-04's declared hash against the LIVE file, which breaks on ANY further supersession
regardless of whether it is properly chained) -- fixed to resolve the chain the same way
test_rf05_claims.py's own freeze guard does, not by loosening the assertion. Targeted re-runs after
the fix: tests/mode4_corrective 105/105 passed; the combined fp01+rf05+fup04 set 26/26 passed.
Full lab-suite re-run confirms it: **1268 passed, 0 failed, 1290.02s** (log kept at
evidence/forward_persistence_fp_v1/FP-01/full_suite_final.log).

## Dieu da biet tu evidence
- Admission was descriptive-only in all published runs; the wired hook exists and is proved by FP01-T02 (FP-F02).
- D1/OOS dropped the first return vs the IS convention; the repaired convention and its real-data delta are recorded (FP-F04).
- Band-alone verdicts are unevaluable by construction (FP-F06).

## Dieu chua biet
- Whether admission-wired deployment changes any economic outcome (needs FP-07).
- The full artifact export (FP-F08 PRESENT).

## Blockers
- FP-F08 PRESENT (planned FP-02/FP-10). Owner review PENDING.

## Budget
- FP-01 charged 0 to the shared TE ledger; engine calls 0.

## Next authorized action
- NONE: wait for owner approval FP-01 -> FP-02 (R-18).

## Khong duoc lam
- No bulk search; no admission/economics change without a new upgrade record; no FP-02 start without approval.
