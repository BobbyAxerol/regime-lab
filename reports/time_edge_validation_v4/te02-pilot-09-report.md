# TE-02 pilot-09 report — engine clock, 32-trial selection, audit, deployment

- job: `evidence/time_edge_validation_v4/plans/te-host-pilot-09/job.json`
- allocation `TE02-PILOT-R03`: total 13800s, charged at report time 9404.514s over 43 attempts
- budget revisions applied: TE02-PILOT-R03-REV01, TE02-PILOT-R03-REV02, TE02-PILOT-R03-REV03

## Tasks

| task | status | wall s | reserved s |
|---|---|---|---|
| engine-clock-fee-reconciliation | COMPLETE | 7.611 | 60.0 |
| A-SC-BTC-train-selection | COMPLETE | 1745.541 | 2700.0 |
| A-SC-BTC-selected-audit | COMPLETE | 124.108 | 600.0 |
| A-SC-BTC-train-deployment | COMPLETE | 22.193 | 600.0 |

- qualify: checks 5/5 true; engine contract `event_lifecycle_v3_next_open`; engine runs 1.
- selection: 32/32 trials complete, status `SELECTED`, wall 1736.3s, measured search+io+packing 1737.6s; selected params `{"AP": 48, "alpha.condition_threshold": 60, "coeff": 3, "novolumedata": false, "src_col": "close"}`; objective 3.0409222105; mean_is_sharpe 3.0409222105; account_runs 32, scorer_calls 224, deployment_runs 0.
- audit: `SELECTED_AUDIT_PASS` 5/5; max equity error 0.0; raw Sharpe 3.0409222105250384 vs selected 3.0409222105250384; fills 65; prepared 55.0s / cold 55.5s.
- deployment `EVALUATED` arm M4_CAL cell A-SC/BTCUSDT 2020-12-01T00:00:00Z -> 2020-12-31T00:00:00Z: 9 fills, days 30, mean daily return 0.00105482; these are execution/technical numbers on the training month, not an edge claim.

## Scope statement

The model input at this stage is `model_id: null` for the initial incumbent; this pilot certifies the engine clock, real 32-trial Mode 4 selection, selected-theta audit parity and one M4_CAL account. It is not the TE-04 economic look.
