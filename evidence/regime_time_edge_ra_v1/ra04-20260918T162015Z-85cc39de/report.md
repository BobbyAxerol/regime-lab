# RA-04 - Mode 4 support, selector coverage, compact end-to-end controls

## 1. Status va scope
- Technical gate: **PASS** (no positive/robustness outcome required); research status: NOT_ASSESSED; owner review: WAITING_OWNER_REVIEW.
- Branch `mode4-corrective`, HEAD `dc4d4db4b44d4f846c48eab59fb0bfc93884412e`, guide RA-GUIDE-1.0 (section 8), study `regime_time_edge_ra_v1`, run `ra04-20260918T162015Z-85cc39de`.
- Scope completed: RA04.1-RA04.6. Not run: the full 180-day/32-trial registered discovery contract (reserved for RA-05); RA-04 proves the plumbing at phase-owned scale.

## 2. Previous findings va thay doi (F-04)
- F-04 (PRESENT per RA-01's finding_disposition, no raw evidence on this host) reproduced on current source: {'only_first_shard_reliably_day_aligned': True, 'some_candidate_reduces_to_single_shared_datapoint': True, 'different_candidates_share_an_identical_finite_score': True}.
- 2/4 probed candidates reduced to <=1 real finite subperiod score; 1 used the installed selector's pure fallback constant (0 finite of 6); cross-candidate score collapse detected at 2 distinct shared values.
- Mechanism: `split_datetime_index_into_subperiods_v1` (installed engine) splits by bar count, not calendar days -- only shard 0 reliably starts at a UTC day boundary. `TrainingScorer._score` scores complete days only; a candidate that does not trade inside a shard returns sharpe=-inf/ZERO_VARIANCE, correctly filtered by the installed `_collect_subperiod_sharpes`' `np.isfinite` -- but when few shards survive, "temporal robustness" collapses to one shared data point or the registered fallback constant.
- Fixed this phase: `STOCK_MODE4_PLUS_ADMISSION_V1` (RA04.3) - a post-selection guard over the UNCHANGED stock selector, never a second optimizer.

## 3. Actual execution
- Commands: this build, then the thin verifier over the junit of `tests/ra_corrective/test_ra04_cases.py` + `tests/ra_corrective/test_ra04_gates.py`.
- Engine: quantbt-engine 1.1.1 / native 0.4.2; protected tree before `clean` and after unchanged.
- Public-path integration (RA04.6): engine class `quantbt.walkforward.WalkForwardEngine` (installed WalkForwardEngine subclass=True), 8 trials completed at phase-owned scale (24D), oos_used_for_selection reported by selector = False.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
| G04-VALID | Q01-Q07 pass for the pilot cell/primary contract | PASS | readiness.json sha256:5d3dd134bd3c... | PASS |
| G04-READINESS | measured route budget, economics, initial-history eligibility confirmed | PASS | readiness.json sha256:5d3dd134bd3c... | PASS |
| G04-REG | selector/admission/search settings frozen, protected tree unchanged | PASS | admission_policy.json sha256:75593902d360... | PASS |
| G04-MANIFEST | every required artifact indexed and hash-matched | PASS | phase_manifest.json | PASS |

## 5. Compact controls (RA04.5)
| control | purpose | status |
|---|---|---|
| flat_price_deterministic_fee | accounting units | PASS |
| gap_htf_availability | timing | PASS |
| delayed_initial_pending_campaign | lifecycle | PASS |
| relabel_is_not_a_market_change | regime semantics | PASS |
| no_information_null_world | plumbing and inferential guard | PASS |
| action_transmission | treatment can actually execute | PASS |
| known_numeric_effect_on_stored_series | statistical implementation | PASS |

## 6. Route readiness (G04-READINESS)
| alpha | status | fills |
|---|---|---|
| A-SC | OK | 4 |
| A-HMA | OK | 3 |
| A-VWAP | OK | 4 |
| A-HASH | OK | 8 |

## 7. Search registration (RA04.4)
- Budget reused from `configs/time_edge_validation_v4/mode4_binding_r01.json`: 32 trials, is_subperiods=6, seed=20260912 (not re-frozen).
- Search dimensions: {'A-SC': ['AP', 'coeff', 'alpha.condition_threshold'], 'A-HMA': ['max_length', 'take_profit', 'max_sl'], 'A-VWAP': ['dev_mult', 'rsi_len', 'stop_atr'], 'A-HASH': ['mom_len', 'mom_threshold_mult', 'stop_loss_perc']}.
- Behavior witnesses: 4/4 alphas checked, all_witnesses_differ=True.

## 8. Admission policy (RA04.3)
- Contract `STOCK_MODE4_PLUS_ADMISSION_V1`. Thresholds (min_complete_train_days, min_finite_shards) per alpha: {'A-SC': (2, 3), 'A-HMA': (18, 3), 'A-VWAP': (101, 3), 'A-HASH': (3, 3)}.
- Never picks a different winner than the raw stock selection: True.

## 9. Scientific result va kha nang ket luan
- None claimed: RA-04 is a technical phase. What the evidence proves: the F-04 mechanism is real and reproducible on current source; the admission guard catches under-supported selections without ever substituting its own winner; all 4 alphas' search dimensions have measured behavior effect; the active public path (evaluate_oos_candidates=False, no future test segment, pinned installed selector class) is verified both structurally and by one real integration call.
- What it does not prove: ranking IC>0, Sharpe>0, or that regime timing beats a synthetic calendar -- none of those are RA-04 exit conditions per the guide.

## 10. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope, carried forward unresolved: forbidden-claims REVIEW_REQUIRED on T62/T63, 21 undeclared vacuity items in RF-04/RF-05/TE03.7 tests (both pre-existing, unrelated to RA/ code).
- Owner decisions pending: this phase's review; can_start_next_phase=false.

## 11. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra04.py --pytest-xml <junit>` (new run_id per attempt; prior runs immutable).
- Independent verify: re-run the build, or import `verify_ra04` and point it at the run dir with the same junit; deterministic and engine-free.
- Protected trees: fingerprint recorded before/after; phase-changed files: `src/crypto_regime_lab/ra/{mode4_reproduction,mode4_admission,search_registration,compact_controls,public_path,verifier_ra04}.py`, `scripts/run_ra04.py`, `tests/ra_corrective/test_ra04_*.py`, this run dir; committed scoped, no push.
- Next permissible action: RA-05 only after owner approval of this phase.
