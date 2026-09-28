# Postmortem: Run mf03-20260928T161223Z-c35a819a

- **Phase**: MF-03
- **Timestamp**: 2026-09-28T16:12:35Z
- **Exit Status**: FAILED
- **Root Cause**: `ValueError: Column 'ret_90d' has 7.88% missing rows, which exceeds maximum allowed imputation threshold 5.00%`. The feature table included early 2021 data where rolling lookback features had not yet warmed up.
- **Resolution**: Enforced training origin start date `d >= pd.to_datetime("2022-01-14")` per Guide §6.2 in all mature training masks. Succeeded in run `mf03-20260928T164151Z-5faeb4a9`.
