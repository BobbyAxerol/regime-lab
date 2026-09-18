# Session handoff — compact state (mode4-corrective, TE-03.7 P0 chưa pass)

Ngày nén: 2026-09-16. Session mới đọc file này trước, rồi đọc `REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md`
(§RF-01…RF-05), `reports/lab09_report.md`, `evidence/corrective_mode4_v3/*/report.md`,
`evidence/time_edge_validation_v4/*/report.md`, `handoff/TE_CLI_RUNBOOK.md`,
`handoff/TE_MASTER_PLAN_V1.md`, `handoff/TE_PHASE_PLAN_V1.md`.

## 1. Môi trường (không đổi)
- Lab: `/root/bobby/pool_alpha/lab_regime_model_quantbt`, branch `mode4-corrective`, remote `regime-lab`.
- Chỉ dùng venv lab: `<lab>/environments/lab_venv/bin/python`. KHÔNG dùng `/root/bobby/pool_alpha/.venv`.
- `../quantbt`, `../alphas_storage`, snapshot parquet: chỉ đọc. Mọi write trong `LAB_ROOT`.
  Cuối mỗi reply chạy `git -C /root/bobby/pool_alpha/quantbt status --porcelain` và báo.

## 2. Luật lab (tóm tắt, đủ để không phá validity)
- Reports sinh từ script `scripts/write_*report.py` đọc artifact đã commit; không sửa số tay.
- Evidence JSON append-only, có `lab_run_id`; metric thiếu = `null` + reason, không PnL = 0.
- Registrations (hypothesis/endpoint/MDE/seeds/budget) phải có trước run; conclusion dùng đúng
  vocabulary đã đăng ký (`INCONCLUSIVE_SAMPLE`, `FAILED_VALIDITY`, …).
- Không claim edge từ PnL execution; gate đỏ phải sửa/ghi blocker, không làm xanh giả.
- Standing rule user: commit từng phần việc xong (message ngắn, đúng scope), không push nếu chưa được bảo.
- Test: full suite `$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q`
  (lần gần nhất: 1018 passed), RF guards `tests/mode4_corrective` (76 passed), TE guards
  `tests/time_edge_validation_v4` (138–164 passed tùy thời điểm).
- Pyflakes sạch trừ `src/.../alphas/raw-supplied/` (by design).

## 3. Trạng thái công việc
- LAB-01…09 xong: kết luận `FAILED_VALIDITY` (defect COR-13 fee một chiều truyền nhầm vào
  tham số round-trip của engine). Claims cũ hạ về `NOT_EVALUABLE`.
- Corrective RF-01…RF-05 trên `evidence/corrective_mode4_v3/`: RF-01 TECHNICAL_ONLY,
  RF-02 PARTIAL, RF-03 TECHNICAL_PASS, RF-04 step 1 (G11 positive control chạy bằng QuantBT
  simulator: params đổi → trades đổi) xong; pairing 10 cell event-route xong (CAL 6 fills,
  REG 10–12 fills); report RF-04/05 ở `evidence/corrective_mode4_v3/`.
- TE-02/TE-03 Time-Edge V4: technical tests 131→135→138 passed; A-SC public Mode 4 baseline
  thật (104 trials, 58 objective ≠ 0); route matrix 20/20 (A-VWAP/A-HASH QUALIFIED_EVENT sau FUP-01).
- Acceptance T01–T70 riêng cho RF; T01–T64 cũ giữ nguyên.

## 4. P0 hiện tại — TE-03.7 structural controls: CHƯA PASS, bị chặn đúng luật
- controls-05 TIMED_OUT ở cap 8100s; controls-06 shard per-world (REV09, cap 2700/shard):
  shard 1 `NULL_STATIONARY/BTCUSDT` TIMED_OUT, 9 shard còn lại `NOT_RUN_BUDGET`.
- controls-07 (REV10, cap 18000/shard, 10 world-shard) đã `STOP_REQUESTED`, không còn process.
- Bắt buộc: funnel 6 bước (valid→…→orders) phải đo thật + 32-trial selection; thiếu → blocker
  `NOT_RUN_BUDGET` kèm số liệu, **không mở TE-04**.
- Lệch ước lượng: shard đo ~16.652s (targets 4212 + fits 1114 + selections 11326).
- Đã đăng ký: BTCUSDT-first (scope decision `1cc91e4`), 5-symbol chỉ mở sau khi BTC chứng minh
  tiềm năng; dedupe condition×world + tối đa 4 worker cho task độc lập, per-arm compute bằng nhau.

## 5. Việc dở, theo thứ tự
1. TE-03.7: kiểm tra controls-07 đã xong chưa; nếu còn dở, chạy shard nhỏ theo world (mỗi shard ≤ cap),
   checkpoint từng world, đủ 10 shard → assemble funnel + selection → kiểm 4 điều kiện gate P0.
2. Nếu P0 PASS: P1 = TE-04 discovery cặp M4_CAL/M4_REGIME trên cell qualified (scale từ BTC nếu có),
   controls thứ tự, decay D1–D3, funnel từng cell, rồi P2 calibration, P3 freeze/claims.
3. FUP-02 (budget 32–64 trials + window tới 2023) và FUP-03 (dữ liệu hậu freeze): chưa chạy.
4. Commit gần nhất lúc nén: `dea98e1` (BTC control rerun overlap), `d170a1f` (FUP02-F1 proposal),
   `ce3fe20` (funnel assembler). Working tree có ~85 file untracked (evidence/log) — KHÔNG xoá,
   không stage/commit gộp, không reset/clean.
