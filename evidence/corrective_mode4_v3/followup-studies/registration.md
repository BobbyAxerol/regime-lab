# Follow-up study registration (user-approved)

Predecessor: RF-01..RF-05 on `mode4-corrective`. Parent verdict:
`TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE`, economic `INCONCLUSIVE`. Each item below is a NEW study:
registered before any run, with its own budget, contamination status, report and claim gate.

| id | study | status | blocker |
|---|---|---|---|
| FUP-01 | native-event capability for A-VWAP/A-HASH (amend/cancel/reduce + TP ladder) | `REGISTERED_NOT_EXECUTED` | projection code not written |
| FUP-02 | expanded budget 32-64 trials/cutoff + development window to 2023-12-31 | `REGISTERED_NOT_EXECUTED` | budget revision + engine hours |
| FUP-03 | prospective protocol execution | `REGISTERED_NOT_EXECUTED` | **no post-freeze data exists** (snapshot ends 2026-09-09; freeze 2026-09-11) |

No frozen RF-05 protocol is rerun by this registration. FUP-03 can only start when data with
`available_at > freeze` is ingested and audited; the lab never runs live.
