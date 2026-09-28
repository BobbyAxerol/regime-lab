# Postmortem: Run mf05-20260928T165017Z-4d2a8459

- **Phase**: MF-05
- **Timestamp**: 2026-09-28T16:50:17Z
- **Exit Status**: FAILED
- **Root Cause**: `KeyError: 'bss_model'`. The metric key in `test_evaluation_summary.json` is `brier_skill` rather than `bss_model`.
- **Resolution**: Updated `scripts/run_mf05_consolidated_report.py` to use `.get("brier_skill", ...)` and format metric outputs dynamically. Succeeded in run `mf05-20260928T165257Z-053bec67`.
