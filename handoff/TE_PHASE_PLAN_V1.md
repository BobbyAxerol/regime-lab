# TE PHASE PLAN V1 — 4 phase, cách làm và gate chi tiết

**File này là kế hoạch chính để người dùng đọc và phê duyệt TỪNG PHASE.**
Đi kèm: `handoff/TE_MASTER_PLAN_V1.json` (envelope + gate dạng máy đọc).
Nhánh: `mode4-corrective`. TE-04 CHỈ mở sau khi P0 PASS.

## 0. Cách làm chung (áp dụng mọi phase)

- Một worker, 2 CPU, 4 GiB; mỗi task có cap wall; allocation dùng chung, **append-only**,
  không reset charge; revision chỉ nới trong envelope và phải ghi `measured_reason`.
- Mỗi shard: `te.sh plan --run-id <mới>` → `setsid bash scripts/te.sh run --job … > log 2>&1 < /dev/null &`
  → poll `te.sh status` → collect → **commit scoped**. Không overwrite artifact bất biến; run-id mới mỗi attempt.
- Gate FAIL → dừng đúng phase đó, ghi blocker + số liệu (`NOT_RUN_BUDGET`/`INSUFFICIENT_*`), không retry, không hạ chuẩn.
- Không diễn giải PnL execution thành time edge; mọi claim kinh tế phải qua gate P2/P3.
- Envelope tổng: **250.000s (~70h)**; vượt → dừng, báo.

## P0 — Đóng TE-03.7 structural controls

**Mục tiêu:** có funnel thật và 32-trial selection trong full-path structural controls.

**Việc:**
1. `te-host-controls-07` đã `STOP_REQUESTED` (25/45 targets, wall 7301s, REV10; xem `runs/te-host-controls-07/STOP`).
   Tiếp tục bằng shard per-world (REV09: namespace/state riêng, cap 18000s/shard), BTC-first theo scope
   decision `1cc91e4`, checkpoint từng world, resume bằng run-id mới (không overwrite attempt cũ).
2. Nếu còn vượt cap: REV11 nâng cap theo measured wall (ghi `measured_reason` từ receipt), chạy shard còn lại.
3. Collect + assemble funnel: `valid_observations → triggers → searches → different_params → activated → different_orders`.
4. Guard tests: denominator + zero-kèm-lý-do, không fabricated fills, positive/null không đổi.

**Evidence:** `runs/te-host-controls-0X/`, `te03/controls_*`, report, tests `tests/time_edge_validation_v4/`.

**Gate P0 (PASS khi tất cả):**
- [ ] funnel đủ 6 bước, mỗi bước có denominator; bước 0 ghi `0 + lý do`, không null mù.
- [ ] 32-trial selection COMPLETE: params/objective/components/fills có thật.
- [ ] positive control vẫn hồi phục (min power ≥0.90) và null/placebo vẫn dưới tolerance.
- [ ] `fabricated_fills=false`; mọi file committed.
**FAIL:** hết 2 lần nâng cap → `NOT_RUN_BUDGET` + số liệu; **dừng, không mở P1.**
**Budget:** 30.000s.

## P1 — TE-04 Paired discovery

**Mục tiêu:** so M4_CAL vs M4_REGIME trên cell qualified, có controls và decay.

**Việc:**
1. Paired discovery theo coverage r2 (31 origin, 29 vintage), cùng economics/fee binding/dates.
2. `M4_CAL_MATCHED` bắt buộc nếu refit counts khác rõ; delayed-state/placebo theo budget.
3. Decay D1 (IS→OOS), D2 (fixed-param age, anchor đăng ký trước), D3 (adjacent folds).
4. Funnel từng cell; shard resumable, cap 5.400s/task.
**Evidence:** `evidence/time_edge_validation_v4/te04/paired_discovery.json`, `controls.json`, `decay_panels.json`, `funnel.json`, report MD+JSON.

**Gate P1 (PASS khi):**
- [ ] mọi contrast có `execution_validity` / `implementation_fidelity` / `statistical_status`.
- [ ] 20 cell có status + reason; cell không chạy để null+reason.
- [ ] không còn A01–A08 active trên cell nào (nếu còn → `NOT_EVALUABLE`).
- [ ] valid pairs có account thật (fills/equity), không fabricated.
**FAIL:** cell invalid execution lặp lại không sửa được → dừng, ghi blocker.
**Budget:** 140.000s.

## P2 — Statistical calibration

**Mục tiêu:** đủ điều kiện thống kê cho claim P3.

**Việc:** family + multiplicity; block bootstrap (block chọn ở development); MDE từ account units đo thật; power ở net effect; placebo/delay/risk acceptance.
**Evidence:** `te04/statistical_calibration.json`, report.

**Gate P2 (PASS khi):**
- [ ] mọi contrast có CI + denominator >0; undefined có flag + lý do.
- [ ] MDE đăng ký trước khi so kết quả; không đổi threshold sau khi xem kết quả.
- [ ] power tại net effect đạt, positive/null control giữ nguyên hành vi.
**FAIL:** `calibration_passed=false` → claim P3 tối đa `INCONCLUSIVE`.
**Budget:** 20.000s.

## P3 — TE-05 Freeze, recompute, claims, handoff

**Mục tiêu:** kết luận có scope + handoff tái lập được.

**Việc:** freeze code/inputs/budget (hash thật); recompute từ artifact; `claim_report` theo G3 §12; prospective protocol `SPECIFIED_NOT_EXECUTED`; integrity; docs + reproduction commands.
**Evidence:** `evidence/time_edge_validation_v4/te05/…`, `report.md/json`, `handoff/`.

**Gate P3 (PASS khi):**
- [ ] `TECHNICALLY_VALID` cho scope hỗ trợ; `PARTIAL` nếu A-VWAP/A-HASH còn block.
- [ ] không `POSITIVE` nếu CI chưa vượt MDE; âm/inconclusive được giữ nguyên.
- [ ] quantbt/alphas/storage gốc không bị sửa; integrity PASS.
**FAIL:** giữ kết luận yếu hơn, không publish mạnh hơn evidence.
**Budget:** 60.000s.

## Phê duyệt

| Phase | Trạng thái | Người duyệt |
|---|---|---|
| P0 | đang dở (controls-07 STOPPED; tiếp tục per-world shards) — **user đã duyệt toàn bộ 2026-09-16** | user |
| P1 | chờ P0 PASS (không tự mở) | user (đã duyệt điều kiện) |
| P2 | chờ P1 | user (đã duyệt điều kiện) |
| P3 | chờ P2 | user (đã duyệt điều kiện) |

Duyệt toàn bộ đã xong; tôi chạy lần lượt P0 → P1 → P2 → P3, dừng báo cáo ở mỗi gate.
