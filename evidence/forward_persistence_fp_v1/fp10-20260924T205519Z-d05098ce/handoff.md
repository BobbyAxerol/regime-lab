# FP-10 handoff (fp10-20260924T205519Z-d05098ce)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp10-20260924T205519Z-d05098ce

## Replay command
`lab_venv/bin/python scripts/run_fp09.py --pytest-xml <fresh junit>`
(what this phase itself ran: replayed FP-09 from `evidence/forward_persistence_fp_v1/fp09-20260924T200048Z-3ae26f5a` into `evidence/forward_persistence_fp_v1/fp09-20260924T205520Z-0a559f8e`, all_match=False)

## Unresolved issues
- FP-09's own primary contrast (transition-cost timing) rests on only 3 real admission events at a single cell -- a severely small sample, disclosed, never treated as a general finding.
- Cell 2 (A-SC/ETHUSDT) never produced an evaluable B/C selection across FP-08/09 -- the forward-persistent selector's own mechanism has only ever been exercised on cell 1.
- guide 3.2's ~26-39-origin research-default target for FP-04's archive was never reached (frozen at 12, a disclosed partial scope since FP-04) -- extending it needs its own cost disclosure and R-18 approval before any future phase attempts it.
- `outer_evaluation` (2024-01-01 onward) remains untouched and, per its own registration, is not even a clean holdout (supplied presets were TPE-tuned with an unknown cutoff) -- opening it for any future prospective evaluation needs a deliberate, explicit owner decision, not an automatic next step.

## Budget summary
~14.7h real engine wall time across FP-01..09 (FP-03 search 8404.12s, FP-04 search 34254.3s, FP-07 deployment 509.41s, FP-08 cell-2 search 9344.1s, FP-09 deployment 290.72s), plus this phase's own near-zero-cost replay (one cache-heavy FP-09 re-run). FP-04's 192-record archive is the largest reusable asset for any future extension.

## Owner decisions
Full R-18 decision ledger: evidence/regime_time_edge_ra_v1/owner_decisions.jsonl (every FP-01..10 phase-advance decision, the FP-09 hypothesis-selection delegation dec-dbdcfac62864f05b, and the FP-07/08/09 resource-budget exception dec-9cc3ec3e712cf61b are all there).
