# RA-01 handoff

- run dir: evidence/regime_time_edge_ra_v1/ra01-20260918T093759Z-e72c0dd9/
- approvals: scope=PENDING, migration=PENDING
- next: RA-02 semantic cache, only after owner approves RA-01.
- Reconciliation verdict: see baseline_identity.json running_row_reconciliation; any ORPHAN_NO_LIVE_PROCESS row must be recovered via the TE supervisor (recover_interrupted under the run lock) before RA-02 launches against this ledger.
- live controls-10 retry job is concurrent budget consumption, not RA-owned.
