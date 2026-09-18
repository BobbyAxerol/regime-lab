# RA-01 - baseline lock, scope, protocol migration, testable gates

## 1. Status va scope
- Technical gate: **PASS** (technical phase gate only; no model positivity required); research status: none claimed; owner review: WAITING_OWNER_REVIEW.
- Branch `mode4-corrective`, HEAD `a98fc58999426ea5557a13f46c536be494d1dbd9`, tracked-dirty `M src/crypto_regime_lab/safety/checks.py
 M tests/test_lab01_safety.py`; guide RA-GUIDE-1.0 (section 5), study `regime_time_edge_ra_v1`.
- Scope completed: RA01.1-RA01.6 (inventory, finding map, registration, migration, budget admission, thin verifier). Not run: nothing in phase scope; zero engine launches by this phase.

## 2. Previous findings va thay doi
- F-01..F-08 all carry dispositions (8/8, none "read therefore done"), each with source path, evidence refs and planned phase RA-02..RA-07.
- Methodology revision recorded in protocol_migration (7 rows incl. the T02 run-output-dedup scoping); old registrations/claims/evidence untouched.
- Registration: 4 arms (STATIC, M4_CAL, M4_CAL_MATCHED=CAL_BUDGET canonical, M4_REGIME), primary H-BUDGET = M4_REGIME - M4_CAL_MATCHED; economic fields PENDING_CALIBRATION block dependent economic jobs until resolved in RA-04/RA-07.

## 3. Actual execution
- Interpreter `/root/bobby/pool_alpha/lab_regime_model_quantbt/environments/lab_venv/bin/python` (python 3.12.13); engine quantbt-engine 1.1.1 / quantbt-native 0.4.2 (pip (INSTALLER=pip, no direct_url.json; wheelhouse install)); endpoint sha installed==protected 45ede55d0d66....
- Route: read-only inventory (git status, package metadata, ledger read-only, ps snapshot) -> artifacts -> pytest junit of tests/ra_corrective -> thin verifier. No market data read, no engine call.
- Live inventory: 353 untracked files snapshotted and left alone.
- Ledger reconciliation: 1 RUNNING row(s): 0 live-matched, 1 orphan(s); row bc9d8951... ORPHAN_NO_LIVE_PROCESS (pids []).
- Tests: collected 14, failed 0, errors 0 (junit fed to the verifier; test_registry lists 14 node ids)

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
| G01-ID | branch/HEAD/engine+native pinned; endpoint hashes recorded; protected tree unchanged by the phase | PASS | baseline_identity.json sha256:d7491ef88482... | PASS |
| G01-MIG | >=6 migration rows complete; namespace not immutable R01; approvals PENDING | PASS | protocol_migration.json sha256:d1bdbbe828e7..., registration.json sha256:cb918d1ed410... | PASS |
| G01-VERIFY | receipts+hashes match; real test evidence; no BLOCKED riding a PASS; no missing artifact | PASS | phase_manifest.json + verification.json (test_registry sha256:a950512b76e5...) | PASS |
| G01-BUDGET | remaining == total - charged; admission refuses over-envelope; charge never reset | PASS | resource_budget.json sha256:e688eed22e7d... | PASS |
| G01-REPORT | every finding F-01..F-08 has disposition + evidence + future phase | PASS | finding_disposition.json sha256:0e6f54b96bc8... | PASS |


## 5. Correctness va causality
- RA-01 launches no economic job and reads no market data; causality N/A beyond read-only inventory. The admission path is probed red (over-envelope -> BLOCKED_BUDGET) inside the verifier, not asserted.
- No metric is defined in this phase; PENDING_CALIBRATION fields stay unresolved and blocking.

## 6. Runtime va memory
- Build-only phase: seconds of wall, zero engine accounts/visited bars/cache traffic.
- Ledger TE02-PILOT-R03 at freeze: total 300000s, charged 165457.9s, remaining 134542.1s; caps frozen in resource_budget.json (per-task 27000s, rss 3.0GB, 1 worker, 1 retry - measured bases recorded there).

## 7. Scientific result va kha nang ket luan
- None claimed. Nothing here proves or disproves an economic edge; the registration only fixes arms, contrasts and blocking fields.

## 8. Blockers/debt va quyet dinh
- Running/orphan ledger rows are reconciled with PID evidence above; any orphan is recovered by the TE supervisor (recover_interrupted under the run lock), not by RA-01.
- Shared budget is consumed concurrently by the live controls-10 retry job (not RA-owned); every later launch must re-read the ledger.
- Owner decisions pending: scope approval + migration approval (both PENDING). No P0/P1 is being carried as PASS.

## 9. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra01.py --pytest-xml <junit of tests/ra_corrective>` (new run_id per attempt; prior runs immutable).
- Independent verify: `lab_venv/bin/python scripts/verify_ra01.py --run-dir <dir> --pytest-xml <junit>`.
- Protected trees: before fingerprint recorded in baseline_identity.json / after unchanged (verifier G01-ID goes red on any delta). Phase-changed files: src/crypto_regime_lab/ra/, scripts/run_ra01.py, scripts/verify_ra01.py, tests/ra_corrective/, this run dir; committed scoped, no push.
- Next permissible action: RA-02 only after owner approval of this phase.
