# RF-05 handoff

Corrected Mode 4 retrospective study handoff. No production merge and no publish.

## Status

- claim validity: `TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE`
- benefit within tested scope: `INCONCLUSIVE`
- next research direction: `REPAIR_CAPABILITY_AND_GO_PROSPECTIVE`
- artifact integrity: `PASS`
- reproducibility: `REPRODUCIBLE_ON_SERVER` (portable bundle complete: `False`)

## Canonical commands

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf05.py --force
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf05_report.py --force
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q | tee $LAB/evidence/corrective_mode4_v3/RF-05/test_suite_mode4_corrective.log
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q
PYTHONDONTWRITEBYTECODE=1 $LAB/environments/lab_venv/bin/python -m pyflakes $LAB/src $LAB/scripts $LAB/tests | tee $LAB/evidence/corrective_mode4_v3/RF-05/pyflakes_mode4_corrective.log
```

## Rollback

- corrected baseline: branch mode4-corrective at the commit recorded in git.head_commit; RF-05 only adds evidence/corrective_mode4_v3/RF-05 and the two scripts plus the RF-05 test file
- command: `git -C $LAB checkout <recorded commit>  # or: git -C $LAB checkout -- evidence/corrective_mode4_v3/RF-05 scripts/run_rf05.py scripts/write_rf05_report.py tests/mode4_corrective/test_rf05_claims.py`
- historical evidence: evidence/crypto_regime_timeedge_v2 is append-only and was never edited; old claims are superseded by RF-01/historical_invalidation.json without touching historical artifacts

## Remaining blockers

- `BLOCKED_CAPABILITY` A-VWAP/A-HASH capability: amend/ladder semantics are not carried on the native-event route; the endpoint route returns tied objectives and no per-fill ledger
- `NOT_RUN` registered 32-64 trials/cutoff: RF-04 executed the bounded 8 trials/cutoff design; the frozen design carries it
- `NOT_EXECUTED` development window 2023-01-01..2023-12-31: the executed pair window ended 2022-06-30
- `NONE_EXISTS` untouched holdout: NESTED_RETROSPECTIVE; the prospective protocol is registered but NOT_EXECUTED
- `MISSING_DECLARED` funding: the event account runs with use_funding=False under the registered contract
- `NOT_RUN` M4_CAL_MATCHED on the 8 scaled cells: the budget control was registered/running only on the 2 pilot cells

## Guardrails

- no writes outside LAB_ROOT; `/root/bobby/pool_alpha/quantbt` and the alpha sources stay read-only
- the prospective protocol is `SPECIFIED_NOT_EXECUTED` and must not be run inside this study
- evidence under `evidence/crypto_regime_timeedge_v2` is append-only and untouched
- a positive prospective result would still require a separate deployment decision

Handoff generated 2026-09-12T02:33:34.173814+00:00 by `scripts/write_rf05_report.py`.
