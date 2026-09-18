# RA-01 — baseline lock, scope, migration, testable gates

## 1. Status và scope
- Verdict: **FAIL** (technical phase gate only; no model positivity required).
- run_id `ra01-20260918T083335Z-0af14f6a`, study `regime_time_edge_ra_v1`, branch `mode4-corrective`, HEAD `ea873c098ea12d6fccb0a8e3f40c9d4b77405865`.
- Scope: RA01.1–RA01.6, zero engine launches by this phase (one live controls-10 retry observed, not owned).

## 2. Previous findings và thay đổi
- F-01…F-08 all carry dispositions (8/8, none "read therefore done"); planned phases RA-02…RA-07.
- Methodology revision recorded in protocol_migration (6 rows); old gates untouched.

## 3. Actual execution
- Live inventory at build time: tracked tree clean, 334 untracked files snapshotted (left alone), engine 1.1.1/native 0.4.2, endpoint sha 45ede55d0d66… (installed == protected source).
- Ledger TE02-PILOT-R03: total 300000s, charged 165457.9s.
- Tests: tests/ra_corrective/test_ra01_gates.py run for real; report fed to the verifier (see verification.json).

## 4. Exit-gate matrix
- G01-ID: FAIL — git HEAD not a full 40-hex sha: ''; git branch not recorded; engine/native versions not pinned
- G01-MIG: PASS
- G01-VERIFY: FAIL — missing artifacts: ['report.md', 'handoff.md']
- G01-BUDGET: PASS
- G01-REPORT: PASS

## 5. Correctness và causality
- RA-01 launches no economic jobs; causality N/A beyond read-only inventory. Protected fingerprint taken before/after.

## 6. Runtime và memory
- Build-only phase: seconds of wall, no engine calls, no candidate evaluations.

## 7. Scientific result và khả năng kết luận
- None claimed. Registration namespace `regime_time_edge_ra_v1` created with economic fields PENDING_CALIBRATION, which blocks dependent economic jobs until resolved.

## 8. Blockers/debt và quyết định
- Live controls-10 retry consumes shared budget concurrently; each future launch must re-read the ledger.
- Untracked worktree (~334 files) recorded, not cleaned.
- Decision needed: owner approval of scope + migration (both PENDING) before any RA economic work.

## 9. Reproduction, commit và handoff
- Rerun: `lab_venv/bin/python scripts/run_ra01.py --pytest-xml <junit>` (new run_id each time; old runs immutable).
- Verifier: `lab_venv/bin/python scripts/verify_ra01.py --run-dir <dir> --pytest-xml <junit>`.
- Next: RA-02 after owner approval of this phase.
