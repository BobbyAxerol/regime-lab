# RA-05 - Discovery nho: 4 arms, timing dung va calendar budget-matched

## 1. Status va scope
- Technical gate: **PASS**; research status: **DISCOVERY_ONLY** (guide 3.5: no
  positive/edge claim offered; a short pilot cannot be given an economic verdict per RA01.4's
  migration table).
- Branch `mode4-corrective`, guide RA-GUIDE-1.0 (section 9), study `regime_time_edge_ra_v1`, run `ra05-20260918T190605Z-9ac5e045`.
- Pilot cell A-SC/BTCUSDT, window
  2021-01-01 to 2021-01-08 (90-day window, 45-day rolling train memory (registered: 180), 8 trials/cutoff (registered: 50) -- same precedent as RA-02/03/04's phase-owned real-but-small experiments; the full registered contract is not spent proving plumbing here).

## 2. Previous findings va thay doi (F-05/F-06/F-07)
- F-06 (28 accepted triggers, median gap ~28.17d, min-gap28, `time_edge/schedule.py`): re-audited
  on real emissions in this window -- 0 accepted trigger(s) via the
  F-06-cited function (confirmations=2), vs 0 via the function that
  actually drives M4_REGIME (`online_trigger_schedule`, no confirmation requirement). This
  divergence between two real scheduler implementations on the SAME data is itself the audit's
  finding, not an error.
- F-05/F-07 (JM/M0 mixture, rank-IC): the real emissions reused here come from the SAME
  29-vintage ladder F-05 measured (5/29 JM, 24 M0); this phase consumes that mixture as-is,
  neither re-fitting nor recharacterising it.

## 3. Actual execution
- Real BTCUSDT 1m bars (snapshots/server_core_v1/manifest.json), real regime emissions
  (evidence/time_edge_validation_v4/host-emissions-03.json), sha256-verified before read.
- Engine: quantbt-engine 1.1.1 / native 0.4.2; protected tree before `clean` and after unchanged.
- Route `event` (real per-fill native QuantBT account, RF-04 precedent for A-SC), seed
  `20260918`, 2 trials/cutoff.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref | Status |
|---|---|---|---|---|
| G05-EXEC | PASS | PASS | ra05-20260918T190605Z-9ac5e045/phase_manifest.json | PASS |
| G05-TRACE | PASS | PASS | ra05-20260918T190605Z-9ac5e045/phase_manifest.json | PASS |
| G05-LEARN | PASS | PASS | ra05-20260918T190605Z-9ac5e045/phase_manifest.json | PASS |
| G05-SCOPE | PASS | PASS | ra05-20260918T190605Z-9ac5e045/phase_manifest.json | PASS |
| G05-MANIFEST | PASS | PASS | ra05-20260918T190605Z-9ac5e045/phase_manifest.json | PASS |

## 5. Correctness va causality
- All four arms called the SAME `run_cutoff_walk_forward` (same alpha, frame, trials, seed,
  route, fees); the ONLY varying input is `schedule` (guide 3.1).
- `oos_used_for_selection` reported False by every arm's own selector metadata.
- CAL_MATCHED's cadence forecast used a development prefix DISJOINT from the evaluation window
  (real emissions outside `[2021-01-01, 2021-01-08)`), never the
  window's own realized trigger count -- 806 development days,
  18 triggers, rate 0.02233/day ->
  predicted 0.16 triggers in-window -> menu choice
  **180 days** (menu [28, 56, 90, 180]).

## 6. Runtime va memory
- Phase wall time and resource use recorded in `phase_gate.json.measured_resources`.

## 7. Scientific result va kha nang ket luan
- **Action divergence (the RA-05 mechanism question, independent of PnL):**
- STATIC_vs_M4_CAL: 0/1 folds diverged (no)
- STATIC_vs_M4_CAL_MATCHED: 0/1 folds diverged (no)
- STATIC_vs_M4_REGIME: 0/1 folds diverged (no)
- M4_CAL_vs_M4_CAL_MATCHED: 0/1 folds diverged (no)
- M4_CAL_vs_M4_REGIME: 0/1 folds diverged (no)
- M4_CAL_MATCHED_vs_M4_REGIME: 0/1 folds diverged (no)
- **Descriptive returns (point estimates only, no CI/claim-gate -- RA-07 scope):**

| arm | total return | fills | folds | admitted/kept |
|---|---|---|---|---|
| STATIC | 2.9661% | 54 | 1 | 1/0 |
| M4_CAL | 3.0273% | 35 | 2 | 1/1 |
| M4_CAL_MATCHED | 2.9661% | 54 | 1 | 1/0 |
| M4_REGIME | 2.9661% | 54 | 1 | 1/0 |

- None claimed: RA-05 is DISCOVERY_ONLY. What the evidence shows: whether the four arms'
  admission-guarded selections actually diverge in real params/timing under real data, and what
  that costs/returns descriptively -- not whether regime timing beats calendar timing with
  statistical confidence (guide: "khong doi regime thang de PASS").
- What it does not prove: any CI-bounded claim on the primary H-BUDGET contrast
  (M4_REGIME - M4_CAL_MATCHED) -- this pilot's window does not clear the registered >=365-day
  confirmatory floor (RA01.4).

## 8. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope, carried forward unresolved: T62/T63
  forbidden-claims (resolved earlier this session, see AGENTS.md), TE-03.7 still NOT_RUN_BUDGET
  (separate study/track, not touched here).
- Owner decisions pending: this phase's review; can_start_next_phase=false.

## 9. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra05.py --pytest-xml <junit>` (new run_id per attempt;
  prior runs immutable). `--smoke` runs a tiny/fast config to dry-run the pipeline.
- Independent verify: re-run the build, or import `verify_ra05` and point it at the run dir with
  the same junit; deterministic given the same real snapshot bytes.
- Protected trees: fingerprint recorded before/after; phase-changed files:
  `src/crypto_regime_lab/ra/{ra05_market,ra05_arms,ra05_funnel,ra05_discovery,verifier_ra05}.py`,
  `scripts/run_ra05.py`, `tests/ra_corrective/test_ra05_*.py`, this run dir; committed scoped, no
  push.
- Next permissible action: RA-06 only after owner approval of this phase.
