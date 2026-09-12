# TE — bàn giao CLI và nghiệm thu

LAB: `/root/bobby/pool_alpha/lab_regime_model_quantbt`. FUP còn lại đã gộp vào **TE-02 → TE-03 → TE-04 → TE-05**.
TE-01 registration giữ nguyên. Không cần đợi OpenCode/FUP-02; người dùng đã báo dừng.

Đọc [central plan](../implementation%20and%20test_edge_plan.md#approved-coding-order),
[báo cáo coding](../reports/time_edge_validation_v4/te-delivery-20260912-01.md),
[G3](../REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md),
[G2](../QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md).
G3 ưu tiên khi hai guide khác nhau. Các mục bên dưới chỉ cách chạy; không thay registration.

Vị trí hiện tại trong central plan: thứ tự đã duyệt dòng **16**, bàn giao dòng **33**;
TE-01 **556**, TE-02 **616**, TE-03 **645**, TE-04 **679**, TE-05 **709**. Anchor links giữ hiệu lực khi tài liệu thêm dòng.

## 1. Điều kiện đầu vào và trạng thái bàn giao

Code dùng LAB venv, public installed QuantBT Mode 4 và native event v3 next-open. QuantBT/alpha/loader/storage gốc chỉ đọc.
Không dùng CLI legacy để chạy study `time_edge_validation_v4`: entrypoint đó đã chặn study mới.

Trong sandbox Codex, `bwrap` không tạo được namespace. Vì vậy không có market engine run mới.
Trên host, preflight phải báo `AVAILABLE_FOR_QUALIFICATION`. Không bỏ isolation để vượt lỗi.

R01 khởi tạo 31/12/2020 thiếu history ở **8/20 cells (SOL/DOGE × 4 alpha)**.
Warmup toàn miền tham số: SC 1 ngày, HMA 18 ngày, HASH 3 ngày, VWAP 101 ngày, thêm trước 180 ngày train.
Đây là kiểm tra biên manifest; 12 cells còn lại vẫn cần kiểm từng bar/gap trong worker.
Không tự rút train, bỏ cell hoặc đổi cửa sổ. Full discovery hiện bị chặn và cần registration mới giải quyết coverage.

Các gate còn thiếu: lifecycle thực của bốn alpha; parity selected account/optimizer; latency đo thật;
true pre-fill equity/sizing và ngưỡng kinh tế; full-path power ở effect ròng biết trước; placebo/delay/risk acceptance.
Code có guard cho thiếu evidence. Không sửa JSON thành PASS để mở gate.

## 2. Bắt đầu ngay: TE-02, qualification và pilot

```bash
cd /root/bobby/pool_alpha/lab_regime_model_quantbt
bash scripts/te.sh --help
bash scripts/te.sh preflight --output evidence/time_edge_validation_v4/host-preflight-01.json
bash scripts/te.sh coverage --output evidence/time_edge_validation_v4/host-coverage-01.json
```

Hai job đã tạo và hash theo source bàn giao:

```bash
bash scripts/te.sh qualify --job evidence/time_edge_validation_v4/plans/te-host-qualify-01/job.json
bash scripts/te.sh qualify --job evidence/time_edge_validation_v4/plans/te-host-pilot-01/job.json
```

Qualification là fixture 8 bars đo next-open/fee/equity với fills thật; **chưa chứng nhận toàn lifecycle alpha**.
Pilot cố định A-SC/BTC, train cutoff 01/12/2020; 4 tasks: clock → 32-trial actual Mode 4 selection →
selected prepared/cold account audit → account triển khai trong **tháng 12/2020**. Không phải economic look 2021–2023.
Audit yêu cầu fills khác 0, equity/fill/raw selected Sharpe parity; không cho zero-fill fixture PASS.

Job cùng allocation `TE02-PILOT-R03`: **1 worker, 2 CPU, 4 GiB RAM, tổng wall 1.800 giây dùng chung giữa run IDs**.
Mỗi task mặc định tối đa 600 giây, qualification 60 giây. Đây là trần chi phí, không phải dự đoán thời gian hoàn thành.
Không mở full20 để profile. Nếu task timeout, giữ partial và báo runtime/RSS/candidate count để điều chỉnh có căn cứ.

Muốn chỉ chạy task kế tiếp:

```bash
bash scripts/te.sh run --job evidence/time_edge_validation_v4/plans/te-host-pilot-01/job.json --max-tasks 1
bash scripts/te.sh status --run-id te-host-pilot-01
```

Job pin toàn LAB source/config cùng bytes installed QuantBT/native. Khi code/config đổi, phải tạo job identity mới:

```bash
bash scripts/te.sh plan --run-id te-host-pilot-02 --stage pilot
```

Run ID mới vẫn dùng allocation pilot cũ; không được xóa ledger để reset chi phí.

## 3. Stop, resume, lỗi và cache

```bash
bash scripts/te.sh stop --run-id te-host-pilot-01
bash scripts/te.sh run --job evidence/time_edge_validation_v4/plans/te-host-pilot-01/job.json --resume
```

`stop` chỉ yêu cầu dừng process group do **run TE đó** tạo. Không tìm/kill OpenCode hoặc process ngoài run.
`--resume` lưu marker STOP vào history, giữ chi phí, retry task chưa hoàn tất. Completed task và candidate
cache chỉ được dùng khi hash/identity trùng. Lỗi kỹ thuật có artifact thì giữ nguyên; cần sửa source và superseding job,
không ghi đè candidate lỗi để làm run cũ xanh. Crash không có receipt bị tính toàn reservation.

Nếu chỉ retry lỗi tạm thời và chưa gửi STOP:

```bash
bash scripts/te.sh run --job evidence/time_edge_validation_v4/plans/te-host-pilot-01/job.json --retry-failed
```

Mỗi attempt giữ request/result/stdout/stderr/receipt; SQLite giữ trạng thái và chi phí. Failed predecessor chặn dependent tasks.
Scorer dùng một account/unique candidate rồi slice returns cho subwindows; selection không gọi future deployment.
Deployment dùng một account liên tục/arm. Cache không chia sẻ âm thầm sang cutoff, economics hoặc source khác.

## 4. TE-03: features, targets, vintages và emitted model

Guide: G3 RF-03 §§7.2–7.5; G2 §§6.4,8,9.1–9.3. Chỉ mở khi pilot đã nghiệm thu.
Template [te03-models.template.json](te_specs/te03-models.template.json) và
[te03-targets.template.json](te_specs/te03-targets.template.json) chứa đường dẫn `REPLACE_...`, nên cố ý chưa chạy được.
Thay bằng **artifact thực** đã collect, không điền metric thủ công.

```bash
bash scripts/te.sh plan --run-id te-host-features-01 --stage features
bash scripts/te.sh run --job evidence/time_edge_validation_v4/plans/te-host-features-01/job.json
bash scripts/te.sh collect --run-id te-host-pilot-01 --kind bank --task-id A-SC-BTC-train-selection --output evidence/time_edge_validation_v4/host-candidate-bank-01.json
```

Bank pilot chỉ available sau cutoff thực của nó, không dùng để tạo target có origin sớm hơn.
Muốn có model từ đầu 2021 phải tạo bank sớm hơn trên history đủ điều kiện rồi tạo các target 28 ngày đã mature;
SOL/DOGE không có quyền dùng bank/labels từ tương lai để bù listing. Template chọn origin sau bank để minh họa đúng availability.
`features` xuất parquet raw có timestamp availability; lấy reference từ result task, không dùng scaled full-sample features.

```bash
bash scripts/te.sh plan --run-id te-host-targets-01 --stage targets --spec handoff/te_specs/te03-targets.local.json
bash scripts/te.sh run --job evidence/time_edge_validation_v4/plans/te-host-targets-01/job.json
bash scripts/te.sh collect --run-id te-host-targets-01 --kind targets --output evidence/time_edge_validation_v4/host-targets-01.json
bash scripts/te.sh plan --run-id te-host-models-01 --stage models --spec handoff/te_specs/te03-models.local.json
bash scripts/te.sh fit-model --job evidence/time_edge_validation_v4/plans/te-host-models-01/job.json
bash scripts/te.sh collect --run-id te-host-models-01 --kind results --output evidence/time_edge_validation_v4/host-model-results-01.json
```

Mỗi vintage lưu train scaler, K/lambda/seeds/design trials, actual selected design, raw profile mean/std,
occupancy/dwell/transitions/dead states/mapping; emitted tape mang model ID/ready/quality/common namespace.
Outcome-end phải **nhỏ hơn** fit cutoff. Unknown giữ incumbent. Model đổi namespace không tự thành thị trường đổi regime.
Model information dùng future candidate utility ranking của **actual emitted model**, benchmark unconditional cùng bank/economics.
Không dùng inner design score như evidence outer, và không gọi label 0/1 là bull/bear phổ quát.

## 5. Controls và TE-04: chưa mở discovery

Guide: G3 RF-04 §§2,6,8; G2 §§10,11. File
[te03-controls.template.json](te_specs/te03-controls.template.json) mô tả full learned structural control, hai worlds cố định.
Nó chạy observable world → raw features → mature target → JM/M0 → emitted triggers → Mode 4 → real accounts.
Truth file nằm riêng và không truyền vào learner. **World có opportunity không có nghĩa learner timing gain đã biết bằng 2δ.**

```bash
bash scripts/te.sh plan --run-id te-host-controls-01 --stage controls --spec handoff/te_specs/te03-controls.template.json
bash scripts/te.sh controls --job evidence/time_edge_validation_v4/plans/te-host-controls-01/job.json
```

Hai task vẫn dùng shared allocation nếu chưa cấp file khác. Hết budget phải báo, không tự tăng.
Statistical-only calibration ở [te04-statistics.template.json](te_specs/te04-statistics.template.json):
1000 repetitions/condition, 4999 bootstrap draws, four-hypothesis Holm, sparse information episodes,
checkpoint từng world. Delta trong template là đơn vị synthetic fixture, **không phải δ kinh tế thị trường**.
Chạy nó không thể mở `full_pipeline_calibration` gate.

```bash
bash scripts/te.sh plan --run-id te-host-statistics-01 --stage statistical-calibration --spec handoff/te_specs/te04-statistics.template.json
bash scripts/te.sh calibrate --job evidence/time_edge_validation_v4/plans/te-host-statistics-01/job.json
```

Discovery phải có: preregistration giải quyết initial history; runtime acceptance gồm measured artifacts/denominators;
profile theo alpha; δ từ true pre-fill equity; calibration full path; allocation có `profile_refs`.
Mẫu input schema: [te04-discovery.template.json](te_specs/te04-discovery.template.json),
[allocation.template.json](te_specs/allocation.template.json). Mẫu không mang PASS giả.
`plan --stage discovery --spec ... --allocation ...` cố ý từ chối khi còn thiếu các điều kiện này.

Khi đủ gate, planner tạo CAL180/REGIME/CAL_MATCHED, reuse selection cùng cutoff, một account liên tục/arm.
Actual search vượt latency đã freeze bị BLOCKED; không giả rằng tham số đã ready sớm hơn công việc thực.
Decay D2 cần job `--stage decay` giữ một selected theta/anchor, cùng cell/quarter/context, đủ 270 ngày:
H1/H2/H3 mỗi đoạn đúng 90 ngày từ ceil UTC ready; lưu alignment delay. D1 là IS–OOS có selection bias;
D3 là thay đổi fold vận hành, không dùng riêng để kết luận giảm decay.

## 6. TE-05: collect, commit, analyse, freeze, report

Guide: G3 RF-05 §§10,12; G2 §12 LAB-09/10, §13.6. Không cần gọi engine để format/bootstrap/report.

```bash
bash scripts/te.sh collect --run-id YOUR_COMPLETED_RUN --kind accounts --output evidence/time_edge_validation_v4/host-accounts-01.json
```

Collect chỉ nhận completed tasks có hash trùng. `--kind selections` lấy selection trong deployed accounts;
`--kind results` gom nguyên results (vintages/emissions/profile), có thể lặp `--run-id` để gom shards cùng source identity.
Trước report, kiểm `git status --short`/diff và commit **đúng thư mục artifact đã hoàn tất**; không stage toàn repo,
không đưa FUP cũ đang dở vào commit mới. Reports từ input chưa commit hoặc đã sửa bytes sẽ bị từ chối.

Analysis spec chứa refs `accounts`, optional `threshold`, `decay_accounts`, `model_vintages`, `features`,
`targets`, `emissions`, `acceptance`; mỗi ref đúng `{path, sha256}`. `accounts` là refs tới từng account result,
không phải reference tới file collection bao ngoài. Không điền arbitrary information rows vào spec.

```bash
bash scripts/te.sh analyse --spec handoff/te_specs/analysis.local.json --run-id te-host-analysis-01 --output evidence/time_edge_validation_v4/host-analysis-01.json
```

Commit analysis trước, rồi:

```bash
bash scripts/te.sh report --evidence evidence/time_edge_validation_v4/host-analysis-01.json --output reports/time_edge_validation_v4/host-analysis-01.md
bash scripts/te.sh freeze --spec handoff/te_specs/freeze.local.json --run-id te-host-freeze-01 --output evidence/time_edge_validation_v4/host-freeze-01.json
bash scripts/te.sh verify --manifest evidence/time_edge_validation_v4/host-freeze-01.json
```

Freeze spec có `artifacts: [{path, sha256}, ...]`, không được rỗng. Freeze/verify kiểm committed bytes và current source hash.
Report gồm đủ 20 cell statuses, per-fold daily metrics, actual model/unknown/dossier, paired inference, missing reasons.
Không đủ full cohort/gates thì `NOT_EVALUABLE`, không điền 0 cho kết quả thiếu.
Data role hiện tại là nested retrospective; untouched holdout=false; prospective=specified, chưa thực hiện.

## 7. Báo cáo sau mỗi phase

Ghi run ID/commit/hash, số task planned/completed/failed/partial, total charged budget, tests thực đã chạy,
requested/resolved engine contract, model thực dùng, support/unknown/cost/fold metrics, và next task + reason + exit gate.
Lỗi kỹ thuật/thiếu power/không có hiệu ứng kinh tế là ba kết luận khác nhau.

Kiểm tra code bàn giao lại khi có sửa đổi:

```bash
bash scripts/te.sh verify-technical --run-id te-technical-host-01
git -C /root/bobby/pool_alpha/quantbt status --porcelain
```

Không đóng TE phase chỉ vì code/test xanh. Không viết “20/20 findings đã nghiệm thu” khi lifecycle,
pre-fill binding, missing history hoặc full-path calibration còn thiếu. Tiếp theo hiện tại là **TE-02 host qualification/pilot**.
