"""Sharpe-decay final study (`study_id=sharpe_decay_sd_v1`,
`REGIME_LAB_SHARPE_DECAY_FINAL_3_PHASE_GUIDE_VI.md`, guide version SD-GUIDE-1.0).

Phase SD-01 standardizes the Sharpe metric and builds the INIT archive.
SD-02 validates a JM recipe on >=12 validation folds. SD-03 runs the one
locked A/B/C final comparison. This is a NEW study, parent
`forward_persistence_fp_v1` -- see configs/sharpe_decay_sd_v1/
protocol_migration.json for the full old->new mapping and finding
dispositions.
"""

SCHEMA_PREFIX = "regime_lab.sd"
GUIDE_VERSION = "SD-GUIDE-1.0"
STUDY_ID = "sharpe_decay_sd_v1"
PARENT_STUDY_ID = "forward_persistence_fp_v1"
PHASE_ID = "SD-01"
