# FP_CURRENT

## Current source
- FP-01: PASS (evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/)
- FP-02: run fp02-20260922T180514Z-e4aad0b7 (/root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7)
- FP-02 overall: PASS
- FP-02 gates: FP02-G-PARITY=PASS / FP02-G-CACHE=PASS / FP02-G-LATENCY=PASS / FP02-G-MEMORY=PASS / FP02-G-LINEAGE=PASS / FP02-G-RESUME=PASS

## Phase state
| Phase | Technical | Research | Owner | Evidence |
|---|---|---|---|---|
| FP-01 | PASS | NOT_ASSESSED | PENDING | evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/ |
| FP-02 | PASS | NOT_ASSESSED | PENDING (needs R-18 approval) | evidence/forward_persistence_fp_v1/fp02-20260922T180514Z-e4aad0b7/ |
| FP-03 | NOT_RUN | NOT_ASSESSED | PENDING (needs R-18 approval) | — |

## Latest run
FP-02 PASS: common evaluator (candidate + deployment on the qualified event-account route), semantic cache, retention tiers, causal-latency guard and selection-to-fill lineage, all proved on real engine calls over a real 10-day A-SC/BTCUSDT window.

## Dieu da biet tu evidence
- report_level audit vs score is equity-exact on FP-02's OWN real candidate, not only cited from FUP-04's window (route_parity.json).
- A real multi-selection deployment shows the activation delay applies to the INITIAL version too, not only switches (WARMING sentinel before bar 0's version ever decides) -- lineage_demo.json.
- Cross-run cache reuse and cache-based resume both hold on the real evaluator (cache_reuse.json, resume_demo.json).

## Dieu chua biet
- Sampler-state resume (Optuna) is unmeasured -- no search loop exists yet (FP-03).
- Whether the evaluator's cache/lineage design holds up at FP-03's 128-trial scale.

## Blockers
- None recorded for FP-02 at this evidence.

## Budget
- FP-02 charged 0 to the shared TE ledger; ~16 small real engine calls, all on a 10-day/1m real window.

## Next authorized action
- NONE: wait for owner approval FP-02 -> FP-03 (R-18).

## Khong duoc lam
- No bulk search; no economics change without a new upgrade record; no FP-03 start without approval.
