# FP-01 — Contracts, migration và validity repairs (fp01-20260922T162253Z-3538bb29)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29
- started_at: 2026-09-22T16:22:52.753382+00:00
- engine calls: 0 (identity/migration/validity; nothing financial runs here)
- shared TE ledger charge: 0 (re-read read-only)

## Exit gates (re-derived by src/crypto_regime_lab/fp/verifier_fp01.py)

Gates FP01-G-VALIDITY / FP01-G-IDENTITY / FP01-G-MIGRATION / FP01-G-BUDGET; see gate_receipt.json for the per-gate reasons on THIS bundle.

## Finding dispositions (guide §13 FP01.2)

### FP-F01 — FIXED_WITH_PROOF
- finding: Development ngoài window nhưng nằm ở tương lai: calibration inputs outside the evaluation window but in the future can steer the calibration.
- required: Enforce before-evaluation và availability
- verification: FP01-T01: future-only mutations leave the pre-evaluation profile identical; one prefix move shifts it; missing boundary and unavailable-at-decision both refuse.
- planned phase: FP-03 (calibration origins) / FP-05 (labels) must pass through this guard
- claim limit: No calibration input at/after the declared evaluation boundary may feed a profile; the tail rides along.

### FP-F02 — FIXED_WITH_PROOF
- finding: Admission tính sau deployment: ra05_discovery.run_one_arm ran the full account first, then recorded admission as a descriptive funnel; the deep-dive ran no admission at all.
- required: Wire admission trước account consumes params
- verification: FP01-T02 on the real engine path: forced rejection of every fold yields NO_ADMITTED_DEPLOYMENT with empty equity/fills (never PnL=0); the admission-OFF control consumes the rejected params; forced admission deploys exactly the raw stock record.
- planned phase: FP-07 locked study passes an admission_policy; FP-02 re-qualifies the route with the wiring on
- claim limit: Runs published before this repair used the unwired path; they keep outputs, cited as invalidated_by FP-F02-wiring for any future admission claim, never edited.

### FP-F03 — NOT_REPRODUCED_WITH_SCOPE
- finding: Warmup lẫn statistical window: warmup bars counted inside the statistical sample.
- required: Compute returns với prior equity rồi clip đúng
- verification: FP01-T04: 31 more warmup marks before the window leave sample count AND every reported return unchanged.
- planned phase: FP-02 re-measures on the qualified route
- claim limit: Warmup handling is a measured property of the boundary functions, never prose.

### FP-F04 — FIXED_WITH_PROOF
- finding: D1 mất first return: ra07_decay._deployment_slice measured the first in-window return from the first IN-WINDOW mark, dropping one observation versus the IS side.
- required: Boundary/partition reconciliation
- verification: FP01-T03: 100->120->108 yields exactly [0.2, -0.1]; legacy reproduces exactly one; no prior mark -> explicit PRIOR_EQUITY_UNAVAILABLE, never an invented 1.0.
- planned phase: FP-07 D1 uses fp/decay_bounds.windowed_returns; RA-07 rows are recomputed_from, never overwritten
- claim limit: Published D1 rows keep values; any FP headline quoting them states the legacy dropped-first-return convention.

### FP-F05 — NOT_REPRODUCED_WITH_SCOPE
- finding: IS/OOS sizing khác nhau: IS scoring vs forward deployment could run different economics.
- required: Shared economic contract
- verification: FP01-T05 on the real engine: IS scorer vs deployment account reach rtol=1e-9 equity parity; capitals equal at 20000.
- planned phase: FP-02 route qualification re-proves parity
- claim limit: Parity is measured per route pair/version, not a standing certificate.

### FP-F06 — FIXED_WITH_PROOF
- finding: Verdict không trực tiếp so treatment: FUP-05's CADENCE_ARTIFACT came from a placebo-vs-BAND comparison, never a direct REGIME_TIMING-minus-comparator contrast.
- required: New claim logic dựa contrast đúng
- verification: Band-only refuses with the missing contrast named; direct below/above decide artifact/survived; unsigned delta is not inferred.
- planned phase: FP-09 verdicts must call fp/claim_logic with the paired direct contrast
- claim limit: FUP-05 CADENCE_ARTIFACT may not be cited as a causal verdict; only as the DESCRIPTIVE band observation.

### FP-F07 — FIXED_WITH_PROOF
- finding: LOO sử dụng future origins: time-sorted leave-one-out can train on future labels; RA-06's ladder never fit (support 5 < 8), so no guard existed anywhere.
- required: Chronological matured-label split
- verification: FP01-T07: naive LOO rows over the same fixture both fail the guard at the held origin's decision time; a row with no availability field refuses.
- planned phase: FP-05 fits go through fp/chronology; the registered MIN_SUPPORT gate stays
- claim limit: No in-sample residual may be presented as generalization uncertainty (guide 8.5).

### FP-F08 — PRESENT
- finding: Raw artifacts thiếu trong package: untracked run dirs and gitignored binaries referenced but not in git.
- required: Export existing outputs, không thay run khác
- verification: Inventory lists every missing/untracked artifact with a planned export action; no run is re-generated to fill a gap.
- planned phase: FP-02 (export small JSON), FP-10 (freeze package with detached digests)
- claim limit: A missing raw artifact caps every claim that needs it; never zero-filled, never replaced by another run.

### FP-F09 — FIXED_WITH_PROOF
- finding: Gate kiểm token/field thay hành vi: a verifier reading its own prior success record instead of the behavior.
- required: Behavioral verifier
- verification: Four failure shapes each proved to fail; the PASS bundle is independently re-verified.
- planned phase: FP-02..FP-10 verifiers inherit this behavioral shape
- claim limit: Neither the process exit code nor this verifier's PASS is evidence without the artifacts it inspected.

## Boundary reconciliation (FP-F04, one real RA-05 M4_CAL window)
- source: evidence/regime_time_edge_ra_v1/ra05-20260918T201236Z-de11db62/arms_result.json
- legacy observations: 59; repaired observations: 60; added: 1
- mean delta (repaired − legacy): -9.420342497526435e-06
- disposition: RA-05 row keeps its published value; FP-07 D1 uses the repaired convention (recomputed_from, never overwritten)

## Artifact inventory (FP-F08)
- files scanned: 814; missing: 0; small-JSON export candidates: 125

## Permitted conclusions
- Technical: admission hook, boundary convention, availability guard, chronology guard, direct-contrast claim logic and behavioral verifier exist on current source, proved by FP01-T01..T07.
- Research: NOT_ASSESSED -- no market claim in FP-01.
- Owner review: PENDING; FP-02 needs its own approval (R-18).
