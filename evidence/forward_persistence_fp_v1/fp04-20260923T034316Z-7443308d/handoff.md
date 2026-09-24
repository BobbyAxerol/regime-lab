# FP-04 handoff (fp04-20260923T034316Z-7443308d)

- run_dir: /root/bobby/pool_alpha/lab_regime_model_quantbt/evidence/forward_persistence_fp_v1/fp04-20260923T034316Z-7443308d
- origins in archive: 12 (of guide 3.2's ~26-39 research-default target)
- model_ready records: 155, descriptive_only: 37
- next authorized action: NONE until the owner approves FP-04 -> FP-05 (R-18), unless already pre-approved and recorded.
- FP-05 (guide 17) must reuse: ledger_records.json via fl.matured_view/training_view (never read origin_ledger.json's raw trial pool directly for fitting), fp.chronology.chronological_split (already wired inside training_view) for the no-future-label guard, and region_policy.json's frozen geometry_version.
- extending the origin grid later (toward the guide's ~26-39 target) is INCREMENTAL: fl.incremental_rebuild only calls the engine for cutoffs not already present with a valid record (FP04-T07/T08, both tested) -- never a redo of these 12.
