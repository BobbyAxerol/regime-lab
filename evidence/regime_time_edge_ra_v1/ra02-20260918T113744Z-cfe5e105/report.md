# RA-02 - semantic cache, correct invalidation, checkpoint-safe resume

## 1. Status va scope
- Technical gate: **FAIL** (no speedup threshold is required); research status: NOT_ASSESSED; owner review: WAITING_OWNER_REVIEW.
- Branch `mode4-corrective`, HEAD `161c34a7a1e4e737d3ac0acd58ca85d86c70d925`, guide RA-GUIDE-1.0 (section 6), study `regime_time_edge_ra_v1`, run `ra02-20260918T113744Z-cfe5e105`.
- Scope completed: RA02.1-RA02.7 (identity/provenance split, prefix hashing, dependency closure, atomic receipts, trial identity + replay, checkpoint level, warm-cache causality). Not run: nothing in phase scope.

## 2. Previous findings va thay doi
- F-02 (metadata HIT without actual reuse) is addressed by C01 at phase scope: one real QuantBT computation, then a HIT under a new run id with 0 new engine runs and a byte-equal payload.
- Backend change (RA02.3): every kind's closure now hashes the shared financial-semantics files (6 files incl. alpha base, evaluator/engine bridge, event/continuous account bridge, contract helpers). Equivalence of the old backend was never certified, so pre-RA-02 entries are invalidated, not assumed equal.

## 3. Actual execution
- Commands: this build, then the thin verifier over the junit of `tests/ra_corrective/test_ra02_cache_cases.py` + `tests/ra_corrective/test_ra02_gates.py`.
- Route: phase-owned experiments (real engine deployment run + cross-run lookup; crash/resume TPE study over cached objectives) -> artifacts -> thin verifier.
- Engine: quantbt-engine 1.1.1 / native 0.4.2; protected tree before `clean` and after unchanged.
- Tests: collected 37, failures 0, errors 0, skipped 0; matrix covers C01-C10.
- Cross-run reuse: producer `ra02-20260918T113744Z-cfe5e105-a` ran the engine 1 time(s) over 1440 bars; consumer `ra02-20260918T113744Z-cfe5e105-b` got **HIT** with new_engine_runs=0; equivalence `canonical-byte-equal` passed=True.
- Resume parity: seed 20260911, 6 trials, crash after 3, replay 3; parity_passed=True; red control (tell-dropping restart differs)=True.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
| G02-SEM | C01-C10 ran and passed; cross-run reuse is a real HIT with 0 new engine runs | FAIL: first computation did not record a real engine run | cache_test_matrix.json sha256:c399c60228e6... | FAIL |
| G02-NUM | reused output equals the producer's within a frozen tolerance; provenance separated | PASS | actual_cross_run_reuse.json sha256:fe35332cd6c3... | PASS |
| G02-COUNT | all counters present and consistent; cache-hit bars are never counted as executed | FAIL: requested_trials < evaluation requests | counters.json sha256:29144b6cb73f... | FAIL |
| G02-LEDGER | old attempts/costs intact; phase inside its sub-envelope; protected tree unchanged | PASS | resource_envelope.json sha256:a723be27d312... | PASS |
| G02-MANIFEST | every required artifact indexed and hash-matched | PASS | phase_manifest.json (report.md/handoff.md/verification.json are verdict-bearing and outside the JSON hash scope) | PASS |

## 5. Correctness va causality
- Causality fields are captured separately (physical_compute_at, simulated_cutoff, simulated_ready_at); a hit whose outcome matures after the consuming cutoff, whose ready time is the zero sentinel, or whose simulated cutoff differs is rejected (C09).
- Prefix hashing: a future-suffix mutation leaves the prefix key unchanged and the engine's prefix equity identical across two real runs (C04); a prefix mutation changes the key.
- Initial state is typed: fresh vs carry can never be a false HIT (C10).

## 6. Runtime va memory
- Counters (scope: phase-owned experiments): requested_trials=12, unique_evaluations=7, cache_hits=7, cache_misses=7, new_engine_runs=1, visited_bars=1440.
- Cache-hit bars are reported separately and never counted as executed work (cache_hit_bars_counted_as_executed=false).
- Phase wall 2.9s against the frozen sub-envelope 3600.0s. Ledger TE02-PILOT-R03 spent 193557.80508357903 -> 193557.80508357903, attempts 140 -> 140, budget 300000.0: unchanged by this phase.

## 7. Scientific result va kha nang ket luan
- None claimed: RA-02 is a technical phase. What the evidence proves: identical semantics are computed once across run ids and storage paths; changed semantics invalidate exactly their dependent scope; a crash/resume reproduces the uninterrupted study; corrupted or partial publications are never hits.
- What it does not prove: any economic edge, any speedup ratio, or that a continuous-account checkpoint is safe (no certified engine restore exists, so the prefix is replayed instead).

## 8. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope: the forbidden-claims audit REVIEW_REQUIRED on T62/T63 (pre-existing since commit ac01a8d) and the TE ledger orphan row recorded in RA-01.
- Owner decisions pending: RA-01 scope/migration approvals and this phase's review; can_start_next_phase=false.

## 9. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra02.py --pytest-xml <junit>` (new run_id per attempt; prior runs immutable).
- Independent verify: re-run the build, or import `verify_ra02` and point it at the run dir with the same junit; the verifier is deterministic and engine-free.
- Protected trees: fingerprint recorded before/after; phase-changed files: src/crypto_regime_lab/ra/, src/crypto_regime_lab/time_edge/compute_cache.py, scripts/run_ra02.py, tests/ra_corrective/, this run dir; committed scoped, no push.
- Next permissible action: RA-03 only after owner approval of this phase.
