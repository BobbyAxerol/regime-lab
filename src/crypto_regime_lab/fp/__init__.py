"""FP study (`study_id=forward_persistence_fp_v1`,
`REGIME_LAB_FORWARD_PERSISTENT_PLATEAU_GUIDE_VI.md`, guide version FP-GUIDE-1.0).

Phase FP-01 owns identity/migration/validity repairs. Modules here are the
reusable pieces the later phases must go through; each one exists because a
named audit finding in guide §13 FP01.2 requires it, not as general-purpose
plumbing:

* ``decay_bounds``  -- finding 4: D1 boundary/partition reconciliation.
* ``availability``  -- finding 1: before-evaluation + availability guards.
* ``chronology``    -- finding 7: chronological matured-label split.
* ``claim_logic``   -- finding 6: verdicts must use the direct treatment contrast.
* ``admission_wiring`` -- finding 2: admission decides BEFORE the account consumes params.
* ``inventory``/``findings``/``verifier_fp01`` -- FP01.1/FP01.2/FP01.4 evidence.
"""

SCHEMA_PREFIX = "regime_lab.fp"
GUIDE_VERSION = "FP-GUIDE-1.0"
STUDY_ID = "forward_persistence_fp_v1"
PHASE_ID = "FP-01"
