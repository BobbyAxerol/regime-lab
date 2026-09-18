# Audit reproduction bundle

Actual findings on the user-uploaded regime-lab-main.zip, reviewed 2026-09-11. This is not a full market rerun, not a native-wheel certificate, and not evidence that regime edge exists.

Read REGIME_LAB_ACTUAL_SOURCE_AUDIT_VI.md and source excerpts first.

## Run synthetic/source probes

Use an isolated environment with numpy, pandas, numba, optuna, pytest. The supplied quantbt_candidate directory contains the Python reference. Python 3.13 was used for this audit; the included upstream cp312 native wheel was not executed.

```bash
export REGIME_LAB_ROOT=/absolute/path/to/regime-lab-main
export REGIME_AUDIT_OUT=/absolute/path/to/new_audit_output
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMBA_CACHE_DIR="$REGIME_AUDIT_OUT/numba_cache"
mkdir -p "$REGIME_AUDIT_OUT"
python audit_probes.py
python additional_probes.py
python audit_evidence.py
```

Scripts read the provided source and write only to the requested audit directory; do not point that directory at source or production data. No package installation or network calls are performed. Some probes intentionally inject mismatched/failing engine results to demonstrate inadequate validation: they are not historical market observations.

Existing test subset run:

```bash
PYTHONPATH="$REGIME_LAB_ROOT/src:$REGIME_LAB_ROOT/quantbt_candidate" \
python -m pytest "$REGIME_LAB_ROOT/tests/test_lab05_regime.py" \
 "$REGIME_LAB_ROOT/tests/test_lab04_selector.py" \
 "$REGIME_LAB_ROOT/tests/test_lab06_policy.py" \
 "$REGIME_LAB_ROOT/tests/test_lab09_uncertainty.py" -q
```

Recorded result: 196 passed, 2 failed because tests reference a missing original venv executable. The original pytest log is retained. This should not be presented as two financial failures or a full-suite pass.

No raw market data, original complete repository, dependencies, credentials or venv is redistributed in this bundle. Source excerpts are selected from the user's provided code with original line numbers and full-file hashes. Market experiment reproduction still requires the snapshots named in the source manifests.
