# RA-06 - Panel tai su dung, refit-vs-keep target va mot policy revision co gioi han

## 1. Status va scope
- Technical gate: **PASS**; research status: **NOT_ASSESSED**.
- Branch `mode4-corrective`, guide RA-GUIDE-1.0 (section 10), study `regime_time_edge_ra_v1`, run `ra06-20260919T035018Z-fbbe9520`.
- Pilot cell A-SC/BTCUSDT, feasibility-pilot scale: 2 origins,
  7-day calendar spacing, 3-day horizon -- a disclosed
  reduction from guide 10.3's "8-12 origins if budget allows" ceiling (same phase-owned-scale
  precedent as RA-02..05).

## 2. Panel A (reused, no new engine calls)
- 8 rows from RA-05's real evidence (ra05-20260918T201236Z-de11db62),
  4 unique candidates, 8 matured OK.

## 3. Panel B (real KEEP-vs-REFIT, deterministic replay prefix)
- State-fork method: deterministic replay prefix through run_cutoff_walk_forward -- no native QuantBT checkpoint/clone-state capability exists in this install (guide 10.3's sanctioned fallback)
- 2 origins, 2 OK, 0 censored.
- Origin selection rule: pure calendar grid: window_start + spacing_days*(i+1) for i in range(2), spacing_days=7 -- chosen before any branch ran, never adjusted after seeing an outcome

| origin | status | g_t(H) | age | regime transitions |
|---|---|---|---|---|
| 2021-01-08 | OK | 0.01115 | 7d | 0 |
| 2021-01-15 | OK | 0.00000 | 14d | 0 |

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref | Status |
|---|---|---|---|---|
| G06-PANEL | PASS | PASS | ra06-20260919T035018Z-fbbe9520/phase_manifest.json | PASS |
| G06-MODEL | PASS | PASS | ra06-20260919T035018Z-fbbe9520/phase_manifest.json | PASS |
| G06-SCOPE | PASS | PASS | ra06-20260919T035018Z-fbbe9520/phase_manifest.json | PASS |
| G06-MANIFEST | PASS | PASS | ra06-20260919T035018Z-fbbe9520/phase_manifest.json | PASS |

## 5. Correctness va causality
- KEEP and REFIT share a deterministic replay prefix through `run_cutoff_walk_forward`; a real
  bug was found and fixed while building this phase: `E_t` read exactly ON the origin's own day
  disagreed between branches (REFIT's new fold already begins trading that day), fixed by reading
  `E_t` strictly BEFORE origin -- P02 is the regression test.
- Origins are a pure calendar grid, chosen before any branch ran (guide 10.4).

## 6. Model ladder (guide 10.5/10.6)
- Status: **FIT_ATTEMPTED** (support=2, min_required=2).


## 7. Deployment controller demonstration (guide 10.7)
- 2 real origins scored; model_available=False.
- threshold=0.002, cooldown_days=20.

## 8. G06-SCOPE lock decision
- **KEEP_BASELINE**: AGE_CONTEXT's inner-CV MSE did not improve over AGE_ONLY (reduction=None) at equal budget/admission/execution

## 9. Scientific result va kha nang ket luan
- None claimed beyond the lock decision above: RA-06 is a mechanical/feasibility phase (guide:
  "mechanical phase co the PASS voi research INCONCLUSIVE_SUPPORT sau khi hoan thanh branch
  duoc dang ky"). Support at this feasibility-pilot scale (2 OK rows)
  is measured, not manufactured into a stronger claim.

## 10. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Owner decisions pending: this phase's review; can_start_next_phase=false.

## 11. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra06.py --pytest-xml <junit>` (new run_id per attempt;
  prior runs immutable). `--smoke` runs a tiny/fast config to dry-run the pipeline.
- Independent verify: re-run the build, or import `verify_ra06` and point it at the run dir with
  the same junit; deterministic given the same real snapshot bytes.
- Protected trees: fingerprint recorded before/after; phase-changed files:
  `src/crypto_regime_lab/ra/{ra06_panel_a,ra06_panel_b,ra06_origins,ra06_features,ra06_model,ra06_controller,verifier_ra06}.py`,
  `scripts/run_ra06.py`, `tests/ra_corrective/test_ra06_*.py`, this run dir; committed scoped, no
  push.
- Next permissible action: RA-07 only after owner approval of this phase.
