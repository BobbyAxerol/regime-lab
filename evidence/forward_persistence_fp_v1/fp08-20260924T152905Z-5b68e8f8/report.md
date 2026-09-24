# FP Run Report — fp08-20260924T152905Z-5b68e8f8

## 1. Identity
- Phase: FP-08
- Registration: forward_persistence_fp_v1
- Source/engine/data digests: cell1=fp07-20260923T190207Z-5a401d3b, cell2_status=COMPLETED
- Parent run hoặc upgrade: FP-07 (fp07-20260923T190207Z-5a401d3b)
- Scope và data role: cell1=A-SC/BTCUSDT (12 origins, development role); cell2=A-SC/ETHUSDT (3 origins, development role)

## 2. Câu hỏi của lần chạy
- Hypothesis: phân biệt đóng góp thật của forward-persistent/context selection với search randomness, một đoạn thị trường đặc biệt hoặc metric artifact (guide 20 mục tiêu)
- Primary contrast: C_FP_CONTEXT - B_FP_PERSISTENCE, mỗi cell, cộng với I_D (guide 10.6's B vs C positive-decay comparison)
- Điều gì được giữ nguyên: alpha_B=alpha_C=10.0 (reused từ cell 1), economics, report_level, admission mechanism, block bootstrap (28-day)
- Điều gì thay đổi: symbol (BTCUSDT -> ETHUSDT), origin count (12 -> 3)

## 3. Planned vs actual
| Hạng mục | Planned | Actual | Lý do chênh lệch |
|---|---:|---:|---|
| Cells | 20 | 2 | owner-approved 2-cell replication scope (dec-b5a96eb125bb80cd); guide FP08.1 explicitly permits a partial coverage matrix |
| Origins/folds (cell2) | 3 | 3 | as approved |

## 4. Validity
| Check | Expected | Actual | Evidence | Status |
|---|---|---|---|---|
| Coverage matrix complete | 20 cells | 20 cells | coverage_matrix.json | PASS |
| D2 window boundaries | 28/56/84 days | 28/56/84 days | d2_analysis.json | PASS |

## 5. Search và support
- Startup/adaptive trials: N/A (this script makes zero new engine calls)
- cell1 D1 rows with a real value: 7/36
- cell2 D1 rows with a real value: 1/9

## 6. Kết quả
- cell1: C_FP_CONTEXT - B_FP_PERSISTENCE: status=ESTIMATED, estimate=0.0 **[DEGENERATE]**
- cell1: B_FP_PERSISTENCE - A_STOCK_CAL: status=ESTIMATED, estimate=-0.0001889748502425521
- cell1: C_FP_CONTEXT - A_STOCK_CAL: status=ESTIMATED, estimate=-0.0001889748502425521
- cell2: C_FP_CONTEXT - B_FP_PERSISTENCE (cell2): status=NOT_EVALUABLE, estimate=None
- cell2: B_FP_PERSISTENCE - A_STOCK_CAL: status=NOT_EVALUABLE, estimate=None
- cell2: C_FP_CONTEXT - A_STOCK_CAL: status=NOT_EVALUABLE, estimate=None
- I_D (cell1): 0.0 (status=DESCRIPTIVE, DEGENERATE)
- I_D (cell2): None (status=NOT_EVALUABLE)

## 7. Cơ chế
- Context có thực sự đổi candidate rankings/selections không? -> **No** (cell1: 0/12 origins CONTEXT_CONDITIONED; cell2: 0/3 origins CONTEXT_CONDITIONED)
- Benefit có còn sau common calendar? -> **N/A** (no cell shows a single CONTEXT_CONDITIONED selection -- C's own predictions were always either FALLBACK_TO_A or FALLBACK_TO_B, so there is no context-driven effect for the next three questions to examine)
- Context improvement có chỉ là market-wide offset không? -> **N/A** (no cell shows a single CONTEXT_CONDITIONED selection -- C's own predictions were always either FALLBACK_TO_A or FALLBACK_TO_B, so there is no context-driven effect for the next three questions to examine)
- C thắng do conditional selection hay chỉ giảm exposure? -> **N/A** (no cell shows a single CONTEXT_CONDITIONED selection -- C's own predictions were always either FALLBACK_TO_A or FALLBACK_TO_B, so there is no context-driven effect for the next three questions to examine)
- Kết quả có phụ thuộc một origin/model vintage không? -> **CONSISTENT_ACROSS_CELLS** (cell1 (A-SC/BTCUSDT, 12 origins) and cell2 (A-SC/ETHUSDT, 3 origins) both show 0/12 and 0/3 CONTEXT_CONDITIONED selections respectively)

## 8. Compute
- Engine calls / bars / callbacks: 0 (this script), real compute in run_fp08_cell2_archive.py/run_fp08_cell2_study.py/build_fp08_cell*_d2.py
- Cache hits/misses: all D1/D2 reused via real cache HIT (asserted by those scripts)
- Budget còn lại: N/A

## 9. Kết luận được phép
- Technical: coverage matrix built (2/20 completed, 18 disclosed NOT_RUN), D2 age-windows use guide's own 28/56/84-day boundaries, every degenerate contrast is flagged with a reason, decision-rule dispositions come only from guide FP08.5's registered vocabulary.
- Research: dispositions below, per guide FP08.5's own table:
  - cell1: C_FP_CONTEXT - B_FP_PERSISTENCE: **Context mechanism chưa được exercise đủ** (the underlying contrast is degenerate (C==B via fallback) -- the context mechanism was never exercised, so this is not a genuine effect measurement)
  - cell1: B_FP_PERSISTENCE - A_STOCK_CAL: **No meaningful improvement tại threshold đã thử** (ci95_upper=-3.872726972319523e-05 is below the registered threshold 6.4e-05 -- the CI is narrow enough to exclude a meaningful effect at this threshold)
  - cell1: C_FP_CONTEXT - A_STOCK_CAL: **No meaningful improvement tại threshold đã thử** (ci95_upper=-3.872726972319523e-05 is below the registered threshold 6.4e-05 -- the CI is narrow enough to exclude a meaningful effect at this threshold)
  - cell2: C_FP_CONTEXT - B_FP_PERSISTENCE (cell2): **Inconclusive effect/support** (contrast status is 'NOT_EVALUABLE', not ESTIMATED -- no CI to judge against a threshold)
  - cell2: B_FP_PERSISTENCE - A_STOCK_CAL: **Inconclusive effect/support** (contrast status is 'NOT_EVALUABLE', not ESTIMATED -- no CI to judge against a threshold)
  - cell2: C_FP_CONTEXT - A_STOCK_CAL: **Inconclusive effect/support** (contrast status is 'NOT_EVALUABLE', not ESTIMATED -- no CI to judge against a threshold)
- Scope: 2 of 20 cells run; the other 18 are NOT_RUN, disclosed with a reason (coverage_matrix.json).
- Điều chưa được chứng minh: whether Selector B/C's own decision mechanism generalizes beyond cell 1/cell 2's origins -- delta_decay and epsilon_OOS_noninferiority are NOT_REGISTERED in this lab (guide 10.7), so decay-reduction and non-inferiority claims stay descriptive, never judged against an invented threshold.

## 10. So với run trước
- Comparable contract hay không: cell1 reuses FP-07's own committed artifacts unchanged; cell2 is new.
- Numerical changes: N/A (first FP-08 run).

## 11. Next action
- Một bước tiếp theo cụ thể: FP-09 (secondary timing extension) is a CONDITIONAL branch needing its own owner approval with a specific mechanistic hypothesis (guide 21) -- not opened automatically from FP-08 alone.
- Owner approval cần có: FP-08 -> FP-09/FP-10 needs its own R-18.
- Không mở thêm phạm vi nào: no new cell, no new origin count, no new resource exception without its own disclosed decision.

## Glossary
- **I_D** (guide 10.6: mean over common origins of (D+_B - D+_C), the POSITIVE part of each arm's own D1 decay -- I_D>0 means C reduces positive decay relative to B; computed here from each cell's own committed D1 table, zero new engine calls)
- **D_+ (positive decay)** (guide 10.6: max(D, 0) -- a NEGATIVE D, where forward beat IS, contributes zero rather than an offsetting negative value)
- **degenerate contrast** (a paired contrast between two arms whose underlying accounts are byte-for-byte identical, e.g. cell 1's C==B -- its estimate is exactly 0 by construction, not a measured absence of effect)
- **NOT_REGISTERED threshold** (guide 10.7: delta_decay and epsilon_OOS_noninferiority have no owner-accepted value in this lab's registry; claims needing them stay DESCRIPTIVE per the guide's own explicit fallback, never judged against an invented number)
- **coverage matrix** (guide FP08.1: the full 4-alpha x 5-symbol = 20-cell primary matrix, every cell's status reported even when NOT_RUN, with a disclosed reason)
