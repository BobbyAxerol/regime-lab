# TE Master Plan V1 — khoá mục tiêu, chạy một mạch

Mục tiêu: đi hết TE-03.7 → TE-04 → TE-05 để có **một kết luận có scope** về
calendar vs regime timing, dương/âm/inconclusive đều hợp lệ, với evidence, budget
và gate đã đăng ký trước. Không nới tiêu chí, không zero-fill, không claim edge
từ PnL execution.

## Trạng thái xuất phát (đã có artifact)
- Support TE-03 r2: planned 28 / evaluable 24 (`ESTIMATED`); coverage R01 = 31 origin, 29 vintage.
- Power TE03.7: positive RECOVERED (min power 0.944); null/placebo không false-positive.
- Structural controls: controls-04 đang chạy (REV07, cap 5400s/task, reserve 10800s).
- TE-04 LOCKED.

## P0 — đóng TE-03.7 structural controls (đang chạy)
- controls-04 (REV07). PASS → đóng TE-03.7. Nếu còn vượt cap: đăng ký REV08 nâng lên 8100s/task (3 selection), chạy controls-05; hết envelope → ghi `NOT_RUN_BUDGET` blocker kèm funnel null + lý do.
- Exit: funnel `valid→trigger→search→params→activated→orders` có denominator, selection có params/objective, controls PASS/blocker.

## P1 — TE-04 Discovery (sau P0 PASS)
- Paired M4_CAL vs M4_REGIME trên các cell qualified (A-SC/A-HMA/A-VWAP/A-HASH theo route matrix), cùng coverage r2; M4_CAL_MATCHED bắt buộc nếu refit counts khác rõ; delayed/placebo theo budget.
- Decay D1/D2/D3; funnel từng cell; mọi shard resumable, `setsid`, một worker, cap 5400s/task.
- Artifacts: `evidence/time_edge_validation_v4/te04/…`, report MD+JSON.
- Exit: mọi contrast có validity/fidelity/statistical status; không cần edge dương.

## P2 — Statistical calibration (song song shard nhẹ, sau P1)
- Family + block bootstrap + MDE từ account units đo thật; power ở net effect; placebo/delay/risk acceptance.
- Exit: calibration_passed hoặc blocker kèm số liệu.

## P3 — TE-05 Freeze & claims
- Freeze code/inputs/budgets; recompute; claims theo G3 §12; prospective protocol SPECIFIED_NOT_EXECUTED; integrity; handoff + docs.
- Exit: TECHNICALLY_VALID cho scope hỗ trợ + kết luận kinh tế có bằng chứng; PARTIAL nếu A-VWAP/A-HASH còn block.

## Cơ chế thực thi một lần duyệt
- Mọi shard: `te.sh plan` run-id mới → `setsid ... &` → poll `te.sh status` → collect → commit; không overwrite artifact bất biến.
- **Envelope đề xuất**: tổng 250.000s (~70h engine), per-task cap 5400s, 1 worker, 2 CPU, 4 GiB; revision trong envelope được tự đăng ký append-only; vượt envelope thì dừng và báo.
- Gate FAIL ở bất kỳ phase nào → dừng đúng phase đó, ghi blocker + số liệu, không tự retry, không hạ chuẩn.
