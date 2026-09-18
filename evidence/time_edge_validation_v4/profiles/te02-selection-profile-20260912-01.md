# TE-02 selection runtime profile — pilot-07

- lab_run_id: `te-host-pilot-07`; schema `regime_lab.te02_selection_runtime_profile.v1`
- selection: **10/32 trials complete** (31.25%) in one attempt; TIMED_OUT at 600.049s against cap 600s (`task wall cap reached`).
- candidate accounts: 10/10 EVALUATED, 0 FAILED_CANDIDATE, 0 FAILED_TECHNICAL; engine wall sum 538.841s, mean 53.884s, range [51.713, 59.609]. Callbacks per candidate: [259200].
- inter-trial wall: [60.488, 54.408, 54.288, 54.596, 53.298, 52.751, 54.45, 53.436, 54.9, 52.241] (sum 544.856s); setup before trial 0: 9.814s.
- 32-trial projection: 1740.1s => registered cap 2700s (55.2% margin over projection).
- RSS/CPU: selection peak not observable (cap-killed child has no `worker_result.json`); qualify task peak RSS 256116 KiB, CPU 7.862s, affinity 2 CPUs.
- allocation `TE02-PILOT-R03` at profile time: charged 769.443826s of 1800s (9 prior attempts), remaining 1030.556174s — below the ~1740s a 32-trial selection needs.

## Source paths

- `job`: `evidence/time_edge_validation_v4/runs/te-host-pilot-07/job.json`
- `run_ledger`: `evidence/time_edge_validation_v4/runs/te-host-pilot-07/ledger.sqlite`
- `shared_allocation_ledger`: `evidence/time_edge_validation_v4/allocations/TE02-PILOT-R03/ledger.sqlite`
- `selection_task_evidence`: `evidence/time_edge_validation_v4/runs/te-host-pilot-07/tasks/b27d2eec7dbf244311c66e78c9b8f03ea67e8d22df6b2c3ff3f112389d7d115d`
- `selection_attempt`: `evidence/time_edge_validation_v4/runs/te-host-pilot-07/attempts/e8dd918475584a48b807b318de10d834`

## Per-trial candidate walls

| trial | objective | candidate status | engine wall s | fills | daily sharpe |
|---|---|---|---|---|---|
| 0 | 2.151612 | EVALUATED | 59.609 | 27 | 2.151612 |
| 1 | 1.356848 | EVALUATED | 53.627 | 212 | 1.356848 |
| 2 | 2.293601 | EVALUATED | 53.786 | 13 | 2.293601 |
| 3 | 1.202396 | EVALUATED | 54.047 | 144 | 1.202396 |
| 4 | 0.677275 | EVALUATED | 52.582 | 340 | 0.677275 |
| 5 | 3.061310 | EVALUATED | 52.213 | 23 | 3.061310 |
| 6 | 3.076400 | EVALUATED | 54.058 | 17 | 3.076400 |
| 7 | 1.669160 | EVALUATED | 52.884 | 127 | 1.669160 |
| 8 | 1.579810 | EVALUATED | 54.321 | 120 | 1.579810 |
| 9 | 2.486065 | EVALUATED | 51.713 | 19 | 2.486065 |

No PnL or edge interpretation: these are runtime measurements of a selection-only training pilot.
