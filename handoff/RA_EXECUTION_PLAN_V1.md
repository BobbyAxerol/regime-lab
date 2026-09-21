# RA execution plan V1 — thực thi guide RA-GUIDE-1.0, chờ duyệt RA-01

Trạng thái: **PLAN ONLY — chưa chạy implementation nào cho RA.** Trình tự duyệt: RA-01 trước,
mỗi phase xong báo cáo + chờ duyệt mới (R-18). File này là kế hoạch, không phải bằng chứng pass.

## 0. Thứ tự hiệu lực đã áp dụng

Chỉ dẫn user > guide RA trong phạm vi được giao > contracts đã xác minh > registration
từng run > hướng dẫn lịch sử. Các phase LAB/RF/TE cũ **không chạy lại**; chỉ dùng đúng chỗ
guide mới nhắc: raw financial artifacts ở TE paths (ref path/hash, không copy), historical
runs/invalidations giữ nguyên, số RF-05 là prior result (không suy diễn lại).

## 1. Trạng thái khởi điểm đã kiểm chứng (2026-09-18, read-only)

- Branch `mode4-corrective`, HEAD `2aba1a8`; worktree ~165 file untracked (evidence/log, để yên).
- Ledger `TE02-PILOT-R03`: budget **300000s** (REV10); đã charge **~165458s**
  (COMPLETE 106 / 13511s; FAILED 11 / 27942s; TIMED_OUT 19 / 116703s; CANCELLED 1 / 7302s;
  INTERRUPTED 2 / null); còn lại **~134542s**.
- **1 dòng RUNNING nhưng không có process engine nào sống** → run chết không receipt,
  RA-01 phải đối chiếu, không được lặng lẽ bỏ qua.
- RF-05 (corrective) giữ nguyên: `TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE`,
  economic `INCONCLUSIVE`, MDE 0.0371 bps/day, `NESTED_RETROSPECTIVE`, prospective
  `SPECIFIED_NOT_EXECUTED`. Không dùng lại số này làm kết quả RA.

## 2. RA-01 — khóa hiện trạng (làm đầu tiên, sau khi duyệt)

- **RA01.1**: inventory branch/HEAD/dirty-diff/untracked/package origins-hashes
  (`quantbt-engine==1.1.1`, `quantbt-native==0.4.2`, venv lab), `.lab_marker`, active jobs
  (hiện: không có), ledger allocations, quyền read/write; fingerprint `../quantbt` trước/sau;
  đối chiếu dòng RUNNING-or-orphan nêu trên; cache/tmp/bytecode trong lab.
- **RA01.2**: map F-01…F-08 → path/function/test hiện tại + disposition
  (`PRESENT`/`FIXED_WITH_PROOF`/`SUPERSEDED_PATH_QUARANTINED`/`NOT_REPRODUCED_WITH_SCOPE`/`NEEDS_RUNTIME`);
  lỗi đã sửa có proof thì reuse.
- **RA01.3**: registration mới namespace `regime_time_edge_ra_v1`: 4 arms
  (STATIC, M4_CAL, M4_CAL_MATCHED=CAL_BUDGET, M4_REGIME), primary H-BUDGET
  (`M4_REGIME − M4_CAL_MATCHED`), secondary khai báo, data roles, selector version policy,
  tuning budget (2–3 chiều, 50 trials/cutoff, 1 fixed seed vòng đầu), scope; field chưa rõ →
  `PENDING_CALIBRATION` (chặn economic job tới khi resolve).
- **RA01.4**: bảng migration 6 dòng đúng guide (không sửa acceptance của run cũ để làm xanh).
- **RA01.5**: đọc allocation **thật lúc chạy**; freeze per-task wall cap, memory cap,
  workers/threads, max retry, envelope phase; cap cũ hết → `BLOCKED_BUDGET`, không launch.
- **RA01.6**: thin verifier (manifest verifier + RA receipt check theo G01-ID/MIG/VERIFY/BUDGET/REPORT).
- Artifacts: `baseline_identity`, `finding_disposition`, `protocol_migration`, `registration`,
  `resource_budget`, `test_registry`, `phase_manifest`, `report.md`, `handoff` — dưới
  `evidence/regime_time_edge_ra_v1/<run_id>/`, map vào planner hiện có.
- Exit: technical PASS + evidence + scoped commit → `WAITING_OWNER_REVIEW`.

## 3. RA-02 → RA-08 (làm lần lượt sau duyệt từng phase)

- **RA-02** (sau RA-01): semantic cache + invalidation đúng (tests C01–C10, C01 phải có actual
  QuantBT computation thật); exit G02-SEM/NUM/COUNT/LEDGER.
- **RA-03** (sau RA-02): lazy memory, retention tiers, fast-route parity (M01–M08),
  profiler thực; exit G03-PARITY/MEM/ROUTE/COST. Không hạ validity tài chính để lấy tốc độ.
- **RA-04** (sau RA-03): stock Mode 4 + admission `STOCK_MODE4_PLUS_ADMISSION_V1`,
  compact controls, public-path parity (Q01–Q07); exit G04-VALID/READINESS/REG + owner
  duyệt settings trước RA-05.
- **RA-05** (sau RA-04): discovery 4 arms trên cell qualified, CAL_MATCHED thật từ development,
  funnel decision-to-PnL, report tầng đúng (D01–D07); exit G05-EXEC/TRACE/LEARN/SCOPE.
  Không đòi regime thắng để PASS.
- **RA-06** (sau RA-05): Panel A/B tách bạch, target `g_t(H)`, fork state bằng engine,
  origins không thiên lệch outcome, ladder tối đa AGE_ONLY/AGE_CONTEXT, tối đa một policy
  revision (P01–P08); exit G06-PANEL/MODEL/SCOPE.
- **RA-07** (sau RA-06): freeze analysis trước replication, cell thứ hai không theo PnL,
  controls đủ thứ tự, decay D1–D3, statistics trên stored outcomes, support/power,
  concentration/stability (G07-VALID/CONTROL/STATS/DECAY/CLAIM).
- **RA-08** (sau RA-07): immutable freeze, verify-before-run, 3 nhãn evaluation tách bạch
  (replay ≠ retrospective ≠ prospective), final claim gate §13, handoff tái chạy được
  (Z01–Z06). Không có data mới thì prospective `NOT_RUN_NO_ELIGIBLE_NEW_DATA` +
  `TECHNICALLY_COMPLETE_RESEARCH_UNCONFIRMED` — đây là nhánh hoàn tất hợp lệ, không phải PASS khoa học.

## 4. Điều giữ nguyên trong mọi phase

Một worker trừ khi allocation duyệt nhiều hơn; run-id mới mỗi attempt; chặn run vượt
envelope thật; giữ failed attempts; bootstrap/report không gọi engine; CI chứa 0 không
phải NO_EDGE; MDE freeze trước paired outcome dùng claim; prospective không tự chạy live.

## 6. FUP-04/FUP-05 — kết luận deep-dive 12 tháng + placebo (2026-09-21, đã commit, chờ push)

Trạng thái: **DONE — chờ owner duyệt hướng tiếp theo.** RA-01→RA-07 đã COMPLETE
trước đó ( xem `owner_decisions.jsonl` + AGENTS.md); deep-dive và FUP-04/FUP-05 là
follow-up do owner chỉ đạo trực tiếp, ngoài phase plan, không thay thế RA-08.

### 6.1. Bối cảnh: vì sao có deep-dive

- RA-07 D1 chỉ có 2–3 folds/arm (pilot 90 ngày) — không đủ đọc pattern decay.
- Deep-dive chạy M4_CAL / M4_CAL_MATCHED / M4_REGIME trên BTCUSDT 12 tháng
  (2021-01-01 → 2022-01-01), 50 trials/cutoff, route `event`, profile `score`:
  run `ra07decaydive-20260921T072850Z-22eb0631`, wall 1.91h, cả 3 arms ok=True,
  không OOM. Folds: M4_CAL 10 / M4_CAL_MATCHED 7 / M4_REGIME 9.
- Kết quả mô tả (DESCRIPTIVE_ONLY, không claim): mean return-decay M4_CAL
  −0.000169, MATCHED −0.000186, **M4_REGIME +0.000109** (5/9 folds OOS tốt hơn
  IS). Nhìn từng fold: REGIME tốt lên chủ yếu từ IS âm hồi lại (mean-revert),
  không phải giữ edge tốt — câu hỏi mở cần đối chứng trả lời.

### 6.2. FUP-04 — sửa root cause OOM (commit `16fdd844`, đã xong)

- 1 call `run_event_account` trên frame 613,440 bars đẩy RSS tới 4.24 GiB →
  kernel OOM-kill worker M4_CAL (dmesg 2026-09-20 08:29:01). Đo từng stage:
  frame ~340 MiB, scorer transient ~676 MiB, D1 ~0 — deployment account giữ
  per-bar audit ledger của engine là accumulator duy nhất.
- Fix: thread kwarg `report_level` của engine qua scorer→walkforward→deployment
  →CLI (`--engine-report-level`), **opt-in only** (default None, mọi caller cũ
  byte-identical). Parity s7 trên call RA-05 fold-0 thật: equity byte-equal
  (max|diff|=0.0), counts strategy-level đồng nhất, peak giảm nửa (895→452
  MiB); dưới cap 4 GiB default FAIL, `score` COMPLETE (peak 1110 MiB).
- Kèm: `MALLOC_ARENA_MAX` trong `lab_worker_env`; RF-05 freeze guards sang
  ceiling từ supersession đã đăng ký (2/1). Đăng ký FUP-04 + declaration + 3
  measurement artifacts. Pure technical, không claim thị trường.

### 6.3. FUP-05 — đăng ký deep-dive + PLACEBO_TIMING (commit `f473e679`, đã xong)

- Khóa deep-dive thành discovery dataset (DESCRIPTIVE_ONLY, deviations disclosed,
  hashes pinned) + chạy placebo trên cùng window/contract: synthetic tape
  (seed 20260921, switch-rate 0.786× real, `matched=true` — đối chứng thật,
  không strawman), cùng trigger mechanics + 50-trial search.
- Kết quả (`fup05placebo-20260921T125029Z-32fc0c83`, wall 0.67h): placebo 9 folds,
  **mean decay −0.000031** — nằm trong/trên calendar band (worst −0.000169).
  Tape không mang market info tái hiện được pattern REGIME.
- **Verdict: `CADENCE_ARTIFACT` — không mở RA-08 trên tín hiệu này.**
  Đây là falsification độc lập thứ hai (RA-07 90d + FUP-05 12m) cùng kết luận.
- Artifacts: `evidence/corrective_mode4_v3/FUP-05/placebo_result.json` (+ run dir
  gốc), registration studies[4], `scripts/run_fup05.py`, 4 declaration tests
  (4/4 pass). Không động tới frozen RF-05/RA-07.

### 6.4. Hướng REGIME còn mở (đề xuất, chưa chạy — chờ owner chọn)

- (a) DELAYED_INFORMATION ở delay có ý nghĩa (RA-07 làm 4h quá yếu);
- (b) cross-symbol transfer (ETHUSDT cell 2 mới là check);
- (c) regime làm filter/risk gate thay vì trigger refit (câu hỏi khác, cần
  registration mới).
- Con đường "REGIME timing tốt hơn calendar" ở khung hiện tại đã qua 2
  falsification độc lập và đều rớt — đi tiếp cần đổi câu hỏi, không phải thêm folds.
