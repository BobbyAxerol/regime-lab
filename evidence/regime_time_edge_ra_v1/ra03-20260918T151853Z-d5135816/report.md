# RA-03 - lazy preparation, retention tiers, route qualification, resource profiling

## 1. Status va scope
- Technical gate: **PASS** (no speedup threshold required); research status: NOT_ASSESSED; owner review: WAITING_OWNER_REVIEW.
- Branch `mode4-corrective`, HEAD `8d768c61fddbbc646311cfa72f9578f36823a5e6`, guide RA-GUIDE-1.0 (section 7), study `regime_time_edge_ra_v1`, run `ra03-20260918T151853Z-d5135816`.
- Scope completed: RA03.1 (fix), RA03.3 (retention contract), RA03.4 (verified via M08), RA03.5 (route matrix, all 4 alphas), RA03.7/RA03.8 (profiler, memory acceptance). RA03.2/RA03.6 verified as already-true properties of the existing window-cache/callback design, not separately re-engineered.

## 2. Previous findings va thay doi
- RA03.1 real defect found and fixed: `PreparedAccount.__init__` eagerly packed the FULL frame via `prepare_native_event_strategy` even though every real caller in this codebase uses a non-zero `account_start` (the frame is built to include pre-roll warmup). Measured on a 10-day-history + 2-day-window fixture: 0.0423s / +7.8 MiB wasted on every construction, was_ever_used=False. Fixed: `first==0` is now just another `_window()` key, packed lazily on first use.
- Known gap recorded, not changed: `TrainingScorer` persists full fills/commands/order_events per trial, more than CANDIDATE_COMPACT specifies (TrainingScorer._score (time_edge/execution.py) persists the FULL fills/commands/order_events for EVERY trial's candidate-*.json, not just tr...).

## 3. Actual execution
- Commands: this build, then the thin verifier over the junit of `tests/ra_corrective/test_ra03_cases.py` + `tests/ra_corrective/test_ra03_gates.py`.
- Route: phase-owned real experiments (route qualification x4 alphas, 2 memory profiles, retention-tier size measurement) -> artifacts -> thin verifier.
- Engine: quantbt-engine 1.1.1 / native 0.4.2; protected tree before `clean` and after unchanged.
- Tests: collected 66, failures 0, errors 0; matrix covers M01-M08.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
| G03-PARITY | M01-M08 pass, no primary-semantics change for speed | PASS | parity_report.json sha256:7766c78d827c... | PASS |
| G03-MEM | representative train candidate + deployment scope both measured under cap | PASS | memory_profile.json sha256:7d3e91dfd7cb... | PASS |
| G03-ROUTE | pilot cell has a real qualified route; every alpha keeps a real status | PASS | route_matrix.json sha256:c3d7a01cb5b3... | PASS |
| G03-COST | planner forecasts from measurements; admission rejects an over-envelope job | PASS | capacity_forecast.json sha256:46228ca41475... | PASS |
| G03-LEDGER | shared TE ledger untouched; protected tree unchanged | PASS | resource_receipts.json sha256:70a8940a769f... | PASS |
| G03-MANIFEST | every required artifact indexed and hash-matched | PASS | phase_manifest.json | PASS |

## 5. Route qualification (RA03.5) - measured, not asserted
| alpha | status | fills | exit tags | what this proves |
|---|---|---|---|---|
| A-SC | OK | 4 | entry, exit | the adapter builds and the event route processes real orders for this alpha |
| A-HMA | OK | 3 | entry, exit | the adapter builds and the event route processes real orders for this alpha |
| A-VWAP | OK | 4 | entry, exit, tp | the adapter builds and the event route processes real orders for this alpha |
| A-HASH | OK | 8 | entry, ladder | the adapter builds and the event route processes real orders for this alpha |

No fast/vectorized route exists in this codebase for any alpha; the event route (`ClockedStrategy`/`EventAccountStrategy`) is what is measured, per the guide's own exit clause. A zero-fill row (none occurred in this probe) would prove only that the route did not crash, not that stops/exits were exercised - every row above has fills>0.

## 6. Memory and resources (RA03.7/RA03.8)
- Registered per-process cap 3.0 GiB; target headroom 80% -> 2.40 GiB.
-   - representative_train_candidate: peak 0.312 GiB, growth/extra-repeat 1.22 MiB, under_target_headroom=True, extrapolated=False
  - deployment_scope: peak 0.375 GiB, growth/extra-repeat 4.07 MiB, under_target_headroom=True, extrapolated=False
- Ledger `TE02-PILOT-R03` unchanged by this phase (RA-03 charges nothing to the shared TE budget).

## 7. Capacity forecast (RA03.7/G03-COST)
- Measured cost/task: 2.490s (representative train-candidate scope, warm repeat).
- Ledger: budget 300000.0s, charged 193557.80508357903s, remaining 106442.2s -> affords ~42754 more measured-scale tasks at this cost, no unmeasured speedup claimed.
- Admission probe: over-envelope request -> `BLOCKED_BUDGET`; in-envelope request -> `ADMIT`.

## 8. Scientific result va kha nang ket luan
- None claimed: RA-03 is a technical phase. What the evidence proves: the measured eager-pack waste is real and fixed without changing financial semantics (M02 byte-equality); all four alphas' one real route processes real orders/exits; measured peak memory sits well under the registered cap on both profiled scopes; a forecast built from measurement correctly blocks an over-envelope job.
- What it does not prove: any economic edge, any speedup ratio at production (1000+ day) scale, or that every parameter region of every alpha exercises every exit path (route qualification used one feasible point per alpha, not the full registered search space).

## 9. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope, carried forward unresolved: forbidden-claims REVIEW_REQUIRED on T62/T63 (pre-existing since commit ac01a8d), 21 undeclared vacuity items in RF-04/RF-05/TE03.7 tests (pre-existing, unrelated to RA/ code). TrainingScorer's over-retention vs CANDIDATE_COMPACT recorded as a known gap, not fixed (wider blast radius than this phase's scope).
- Owner decisions pending: this phase's review; can_start_next_phase=false.

## 10. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra03.py --pytest-xml <junit>` (new run_id per attempt; prior runs immutable).
- Independent verify: re-run the build, or import `verify_ra03` and point it at the run dir with the same junit; deterministic and engine-free.
- Protected trees: fingerprint recorded before/after; phase-changed files: `time_edge/execution.py` (the RA03.1 fix), `src/crypto_regime_lab/ra/{retention,profiler,route_qualification,verifier_ra03}.py`, `scripts/run_ra03.py`, `tests/ra_corrective/test_ra03_*.py`, this run dir; committed scoped, no push.
- Next permissible action: RA-04 only after owner approval of this phase.
