# FP-02 handoff (fp02-20260922T175825Z-82d4405b)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp02-20260922T175825Z-82d4405b
- next authorized action: NONE until the owner approves FP-02 -> FP-03 (record in evidence/regime_time_edge_ra_v1/owner_decisions.jsonl, R-18).
- FP-03 (guide 15) must reuse: fp.evaluator.evaluate_candidate/route_parity/run_deployment, the ComputeCache fp_candidate/fp_deployment kinds.
- FP-02's evaluator does not itself run a checkpointed multi-trial search (FP02-G-RESUME's own scope is cache-based, not sampler-state resume) -- FP-03's search loop is the first place sampler-state resume can be measured.
