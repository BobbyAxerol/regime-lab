# RA-06 - Panel tai su dung, refit-vs-keep target va mot policy revision co gioi han

## 1. Status va scope
- Technical gate: **PASS**; research status: **INCONCLUSIVE_SUPPORT**.
- Branch `mode4-corrective`, guide RA-GUIDE-1.0 (section 10), study `regime_time_edge_ra_v1`, run `ra06-20260919T035313Z-59cd3ae0`.
- Pilot cell A-SC/BTCUSDT, feasibility-pilot scale: 5 origins,
  20-day calendar spacing, 28-day horizon -- a disclosed
  reduction from guide 10.3's "8-12 origins if budget allows" ceiling (same phase-owned-scale
  precedent as RA-02..05).

## 2. Panel A (reused, no new engine calls)
- 8 rows from RA-05's real evidence (ra05-20260918T201236Z-de11db62),
  4 unique candidates, 8 matured OK.

## 3. Panel B (real KEEP-vs-REFIT, deterministic replay prefix)
- State-fork method: deterministic replay prefix through run_cutoff_walk_forward -- no native QuantBT checkpoint/clone-state capability exists in this install (guide 10.3's sanctioned fallback)
- 5 origins, 5 OK, 0 censored.
- Origin selection rule: pure calendar grid: window_start + spacing_days*(i+1) for i in range(5), spacing_days=20 -- chosen before any branch ran, never adjusted after seeing an outcome

| origin | status | g_t(H) | age | regime transitions |
|---|---|---|---|---|
| 2021-01-21 | OK | -0.00033 | 20d | 0 |
| 2021-02-10 | OK | -0.00522 | 40d | 7 |
| 2021-03-02 | OK | -0.01202 | 60d | 39 |
| 2021-03-22 | OK | -0.01344 | 80d | 84 |
| 2021-04-11 | OK | 0.00281 | 100d | 138 |

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref | Status |
|---|---|---|---|---|
| G06-PANEL | PASS | PASS | ra06-20260919T035313Z-59cd3ae0/phase_manifest.json | PASS |
| G06-MODEL | PASS | PASS | ra06-20260919T035313Z-59cd3ae0/phase_manifest.json | PASS |
| G06-SCOPE | PASS | PASS | ra06-20260919T035313Z-59cd3ae0/phase_manifest.json | PASS |
| G06-MANIFEST | PASS | PASS | ra06-20260919T035313Z-59cd3ae0/phase_manifest.json | PASS |

## 5. Correctness va causality
- KEEP and REFIT share a deterministic replay prefix through `run_cutoff_walk_forward`; a real
  bug was found and fixed while building this phase: `E_t` read exactly ON the origin's own day
  disagreed between branches (REFIT's new fold already begins trading that day), fixed by reading
  `E_t` strictly BEFORE origin -- P02 is the regression test.
- Origins are a pure calendar grid, chosen before any branch ran (guide 10.4).

## 6. Model ladder (guide 10.5/10.6)
- Status: **INSUFFICIENT_SUPPORT** (support=5, min_required=8).
- measured, preregistered branch (guide G06-MODEL): a training attempt below the registered support floor is not run as a claim; this is a valid, non-financial-claim phase outcome, not a missing implementation

## 7. Deployment controller demonstration (guide 10.7)
- 5 real origins scored; model_available=False.
- threshold=0.002, cooldown_days=20.

## 8. G06-SCOPE lock decision
- **KEEP_BASELINE**: support=5 below the registered floor min_required=8; guide 10.3's own warning that a feasibility-pilot N is not enough to trust a fitted model applies literally here -- no context-policy revision is locked

## 9. Scientific result va kha nang ket luan
- None claimed beyond the lock decision above: RA-06 is a mechanical/feasibility phase (guide:
  "mechanical phase co the PASS voi research INCONCLUSIVE_SUPPORT sau khi hoan thanh branch
  duoc dang ky"). Support at this feasibility-pilot scale (5 OK rows)
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
