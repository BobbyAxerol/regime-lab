# Implementation and test edge plan — chỉ mục thống nhất của Regime Lab

**Ngày lập:** 12/09/2026. **Phạm vi:** `/root/bobby/pool_alpha/lab_regime_model_quantbt`.
**Vai trò:** đầu mối để đọc tình trạng thực, truy nguồn yêu cầu, giao việc, nghiệm thu và tìm báo cáo.
**Trạng thái:** `TE_TECHNICAL_DELIVERY_RUNTIME_BLOCKED`. Người dùng đã dừng OpenCode và duyệt
gộp FUP còn lại vào TE. Bộ code, tests, CLI và runbook đã được triển khai; nghiệm thu kỹ thuật
và phần binding còn thiếu được tách rõ trong báo cáo. **Chưa đóng toàn bộ TE-02…05, chưa có time-edge proof.**

Theo chỉ thị mới nhất: **không tiếp tục FUP như một chuỗi riêng**. Snapshot sau khi người dùng báo dừng
ở [FUP intake](evidence/reviews/fup02-stopped-20260912-01/review.json); không đổi nhãn thành run hoàn tất.
Codex chịu trách nhiệm sửa kỹ thuật, kiểm chứng, runner và hướng dẫn CLI; các job engine/market dài
được chạy từ bộ lệnh bàn giao với isolation/budget/acceptance có evidence.
Việc một task được liệt kê ở đây không có nghĩa code đã được sửa, test đã pass hoặc một market run mới đã được cấp ngân sách.

<a id="approved-coding-order"></a>
## Thứ tự coding và gộp FUP — đã được người dùng duyệt

Checklist viết trước code: [implementation R03](configs/time_edge_validation_v4/implementation_checklist_r03.json).
`IMPLEMENTED` là code đã có; `RUNTIME_QUALIFIED` cần kết quả chạy engine thật; không gộp hai trạng thái.

| Ưu tiên | Phase/task bắt đầu | Phần FUP được tiếp nhận | Đầu ra để nghiệm thu |
|---|---|---|---|
| 1 | [TE-02](#te-02): TE02.1/2/3/7 rồi 4/5/6/8 | FUP-02 scorer, triển khai lặp, lỗi domain, shard/resume/budget; capability còn thiếu từ FUP-01 | Engine adapter đúng clock/sizing, selection-only, ledger không mất lỗi, CLI pilot/profile/resume |
| 2 | [TE-03](#te-03): TE03.1–8 | Các follow-up về regime model, label, causality, opportunity và controls | Model đã chọn nối vào emitted tape; dossier mỗi fold; full-path control CLI |
| 3 | [TE-04](#te-04): TE04.1–9 | FUP discovery chưa chạy, matched controls, decay và statistics | CLI chạy có resume; metrics/decay/inference từ artifacts; calibration trước claim |
| 4 | [TE-05](#te-05): TE05.1–6 | FUP freeze, coverage/reproducibility và báo cáo còn thiếu | Freeze/verify/report CLI; báo cáo MD+JSON từ artifacts đã commit; hướng dẫn OpenCode/người dùng |

Sau mỗi phần coding: commit riêng, báo test thật và giới hạn; sau mỗi phase: báo cáo và khuyến nghị
task tiếp theo. Giữ mọi failed/partial artifacts của FUP làm diagnostic; chỉ tái dùng cache đúng
identity/cutoff/economics, không dùng nhãn RUN_VALID cũ để bỏ qua TE acceptance.

<a id="technical-delivery"></a>
### Bàn giao kỹ thuật 12/09 — đọc trước khi chạy tiếp

- [Báo cáo nghiệm thu theo phase và đủ 20 findings](reports/time_edge_validation_v4/te-delivery-20260912-01.md)
  được sinh từ [JSON đã commit](evidence/time_edge_validation_v4/delivery/te-delivery-20260912-01.json).
- [Runbook và lệnh CLI](handoff/TE_CLI_RUNBOOK.md): bắt đầu bằng **TE-02 preflight → qualification → pilot train A-SC/BTC**.
  Job đã tạo: [qualify](evidence/time_edge_validation_v4/plans/te-host-qualify-01/job.json),
  [pilot](evidence/time_edge_validation_v4/plans/te-host-pilot-01/job.json). Không cần đợi FUP-02.
- [Bộ kiểm tra kỹ thuật](evidence/time_edge_validation_v4/technical/te-technical-20260912-02/acceptance.json): **131 PASS / 33,19 giây**;
  actual installed optimizer với synthetic account scorer, pure learned-model/math/causality, process fault injection;
  **0 market engine runs**, không dùng test PASS như economic evidence.
- Hai phát hiện mới: **8/20 cells thiếu initial history** (SOL/DOGE × 4 alpha); A-VWAP cần prefix tới **101 ngày**
  ở biên parameter space. [Coverage](evidence/time_edge_validation_v4/delivery/coverage-20260912-01.json).
  R01 vẫn immutable; planner/worker chặn thiếu history, không ngầm đổi dates/cells.
- Các binding còn thiếu: real four-alpha lifecycle/sizing/pre-fill equity; measured parity/latency;
  full-path power ở net effect biết trước và placebo/delay/risk acceptance. Chi tiết từng finding trong report,
  [R04](configs/time_edge_validation_v4/implementation_binding_r04.json) và [inventory R05](configs/time_edge_validation_v4/delivery_scope_r05.json).
  Những gate này phải được giải quyết/nghiệm thu trước TE-04 discovery; không viết PASS thủ công để vượt.
- Các mục review FUP/RF bên dưới là **bằng chứng lịch sử trước repair**. CLI canonical mới ở
  `scripts/run_time_edge.py`, package `src/crypto_regime_lab/time_edge/`; không coi fixes đó đã sửa ngược evidence FUP cũ.

## 0. Đọc từ đây

1. [Kết luận và phạm vi kiểm chứng](#review-conclusion).
2. [Ảnh chụp số liệu và tiến độ](#measured-review).
3. [Chỉ mục hai guide](#guide-index) và [bản đồ code/evidence](#code-map).
4. [Danh sách findings có bằng chứng](#findings).
5. [Kế hoạch năm phase kết nối](#phase-index), từ [TE-01](#te-01) tới [TE-05](#te-05).
6. [Đánh giá model regime và ý nghĩa nhãn](#regime-evaluation).
7. [Thống kê, time edge và decay theo fold](#statistical-design).
8. [Hợp đồng báo cáo bắt buộc ở mọi phase](#report-contract).
9. [Nhóm phép thử](#test-groups) và [134 yêu cầu gốc có phân công](#guide-requirements).
10. [Cách tiếp nhận FUP-02, tái sử dụng và bàn giao](#handoff).

**Thứ tự ưu tiên:** chỉ thị mới của người dùng → [Corrective V3][g3] → contracts đã xác minh →
[Final V2][g2] ở phần không bị thay thế. Tài liệu này tổ chức thực hiện hai guide; không tự thay chúng.
Trong tài liệu này, **G2** là Final V2 ngày 09/09; **G3** là Corrective V3 ngày 11/09.
Không dùng tên mơ hồ “V2 mới” để đổi nhầm thứ tự áp dụng.

G3 ưu tiên cặp **M4_CAL/M4_REGIME** với cùng bộ chọn Mode 4. Selector extension và E response là
nghiên cứu phụ; không cần mở lại toàn factorial cũ để làm primary timing study. Tuy nhiên, các đường
phụ chưa sửa phải bị chặn thực sự, không được tiếp tục xuất kết luận kinh tế.

<a id="review-conclusion"></a>
## 1. Kết luận review và giới hạn

**Chưa có kết quả đủ cơ sở chứng minh time edge.** Có nhiều sửa chữa hữu ích, dữ liệu thật và tài khoản
QuantBT thật; nhưng các lỗ hổng dưới đây khiến nhãn “technical pass” không đủ để nghiệm thu phương pháp.
Tăng số lượt thử hoặc số cell chưa tự đóng các lỗ hổng đó.

Mục tiêu cần trả lời gồm ba câu riêng:

- **Validity:** kết quả có đúng về dữ liệu, thời gian, bộ chọn và thực thi không?
- **Information/action value:** model regime có thông tin hữu ích cho lựa chọn/thời điểm dùng tham số,
  và thông tin ấy có đi tới lệnh thực sự không?
- **Economic evidence:** phần lợi ích còn lại sau phí, độ trễ, rủi ro và compute có vượt ngưỡng đã đăng ký,
  với độ bất định được xử lý đúng không? Có giảm decay không, giảm loại nào, trên phạm vi nào?

Kết quả âm hoặc chưa rõ vẫn là kết quả hợp lệ nếu phép thử đúng. Không tiếp tục tăng complexity chỉ để
tìm một cell dương. Cũng không dùng pipeline chưa truyền treatment, lỗi runtime hoặc thiếu support để
kết luận “regime không có time edge”.

### 1.1 Những gì được kiểm tra trong lượt này

- Lập chỉ mục và parse AST **toàn bộ Python trong `src/`, `scripts/`, `tests/`**; inventory JSON/JSONL/
  Markdown ở configs, evidence, reports, handoff. AST là cây cú pháp, không thực thi module.
- Đọc sâu các đường đang quyết định market result: data loading, event account, Mode 4 provider/scorer,
  model fitting/emission, controller, FUP-02 checkpoint, RF-04 decay/controls, RF-05 statistics và tests liên quan.
- Chụp nguyên bytes của source và các artifacts quan trọng; lưu hash để evidence không bị thay khi
  OpenCode tiếp tục ghi checkpoint.
- Chạy probes nhỏ từ các **hàm trích từ source**, không import runner, không gọi QuantBT/optimizer.
  Các probes kiểm arithmetic/controller; không phải backtest hay kiểm định time edge trên thị trường.

**Không tuyên bố:** đã chứng minh mọi dòng trong codebase đúng/sai; đã chạy lại full suite; đã tái hiện
native wheel trên mọi route; đã kiểm mọi parquet row; đã audit toàn repo QuantBT/alpha production;
đã đo p-value mới cho thị trường. Những phần đó có task và gate cụ thể bên dưới.

### 1.2 Đừng nhầm loại kiểm chứng

| Loại | Trả lời | Không được suy ra |
|---|---|---|
| Unit/contract test | Hàm xử lý phí, biên ngày, eligibility, trạng thái đúng không? | Có time edge |
| Source probe | Hàm trong source có counterexample không? | Toàn pipeline runtime đã tái hiện |
| Engine integration | Lệnh/callback/fills/account đi đúng engine không? | Model có thông tin dự báo |
| Synthetic power/null experiment | Pipeline đầy đủ có phát hiện hiệu ứng biết trước và kiểm soát báo động giả không? | Lợi thế đã tồn tại trên crypto thật |
| Retrospective market study | Trong lịch sử và thiết kế đã xem, hiệu ứng/độ bất định là gì? | Untouched confirmation hay deploy-ready |
| Frozen prospective evaluation | Thiết kế khóa trước dữ liệu mới có giữ kết quả không? | Tự động cho phép live |

Unit tests không cần mỗi cái có p-value. Vấn đề cần sửa là dùng unit pass hoặc field `True` làm bằng
chứng cho một giả thuyết thống kê mà chưa được thực nghiệm. Số bars, số assertions và số rows JSON
không phải số quan sát độc lập của time edge.

<a id="measured-review"></a>
## 2. Báo cáo review từ artifacts đã chụp

Khối này được sinh bởi `scripts/render_time_edge_plan.py` từ evidence review riêng, không gõ lại số bằng tay.

<!-- BEGIN MEASURED_REVIEW -->

Bản chụp `time-edge-20260912-review01` bắt đầu **2026-09-12T05:16:53.745169+00:00**, kết thúc **2026-09-12T05:17:13.370929+00:00**.
FUP-02 tại checkpoint **2026-09-12T05:16:46.601353+00:00**. Đây là ảnh chụp lịch sử; OpenCode tiếp tục chạy và có thể đã đi xa hơn.

| Hạng mục rà soát | Đo được | Giới hạn diễn giải |
|---|---:|---|
| Python trong src/scripts/tests | 263 files; 71,498 dòng | Lập inventory AST toàn phạm vi; không đồng nghĩa mọi dòng được chứng minh đúng |
| Hàm test được lập chỉ mục | 835 | Chưa chạy lại; khác số test cases có tham số hóa |
| JSON/JSONL/Markdown trong configs/evidence/reports/handoff | 1587 files | Kiểm parse, hash và chỉ mục; parse được không phải semantic pass |
| Lỗi parse source / JSON | 0 / 0 | Không thay thế kiểm chứng execution/statistics |
| Engine / optimizer / market statistical tests chạy trong review | 0 / 0 / 0 | Không can thiệp FUP-02 |
| Thời gian capture và probes | 19.636 giây | Không phải thời gian đọc sâu hoặc benchmark backtest |

**FUP-02:** 2/20 cặp `RUN_VALID`; 67/360 cutoffs đã chấm; 2144 trials, 1466 hữu hạn, 678 không hữu hạn (31.623%). `infeasible_trials=0` là số runner ghi, chưa chứng minh không có lỗi thực thi.

| Cell đã bắt đầu | Calendar: trạng thái, đã chấm/kế hoạch | Regime: trạng thái, đã chấm/kế hoạch |
|---|---|---|
| A-HMA/BTCUSDT | COMPLETE, 7/7 | COMPLETE, 11/11 |
| A-HMA/ETHUSDT | COMPLETE, 7/7 | COMPLETE, 11/11 |
| A-HMA/SOLUSDT | FAILED, 6/7 | FAILED, 9/11 |
| A-HMA/BNBUSDT | COMPLETE, 7/7 | PENDING, 9/11 |

Lỗi được giữ nguyên từ checkpoint:

- `A-HMA/SOLUSDT / M4_CAL / fold 4`: NativeEventStrategyError: native-event strategy callback 'on_bar_close' failed at bar_index=3312, timestamp=2022-11-10 00:00:00+00:00, strategy_id='EventAccountStrategy': ValueError: limit commands require price > 0
- `A-HMA/SOLUSDT / M4_REGIME / fold 4`: NativeEventStrategyError: native-event strategy callback 'on_bar_close' failed at bar_index=18890, timestamp=2022-11-10 09:00:00+00:00, strategy_id='EventAccountStrategy': ValueError: limit commands require price > 0
- `A-HMA/SOLUSDT / M4_REGIME / fold 7`: NativeEventStrategyError: native-event strategy callback 'on_bar_close' failed at bar_index=3113, timestamp=2022-11-09 21:00:00+00:00, strategy_id='EventAccountStrategy': ValueError: limit commands require price > 0

| Regime model / decay | Kết quả từ artifacts |
|---|---|
| Tape chính | BTCUSDT; 6571 emissions; 40 model vintages |
| Thiết kế trong registry của tape chính | K=3, lambda=1.0, memory=365 ngày |
| Thiết kế chọn riêng ở RF-04 | K=3, lambda=0.5; deployment_action ghi RECORDED_DESIGN_SELECTION |
| Emissions có ready_at / state_common / economic_context | 0 / 0 / 0 trên 6571 |
| D1 / D2 / D3 | 168 / 36 / 102 rows; chỉ 2 cells |
| D2 anchors / self-comparisons | 4 anchors; 12 rows H1−H1 |
| D2 Profit Factor | 12/12 null; 3 rows có PF nền hữu hạn |
| D2 khác route với pilot | 18/36 rows |

**Probes source nhỏ đã thực hiện**, không dùng QuantBT và không là kết quả thị trường:

- Model chỉ ready năm 2025 vẫn tạo trigger tại `2021-01-03T00:00:00+00:00` trong hàm controller được trích từ source.
- Tape cố định 365 observations với max-age 180 ngày tạo 0 triggers; chưa có mốc khởi tạo last_trigger.
- Hai cửa sổ 90 ngày trả 91 và 91 observations, dùng chung ngày biên 2021-04-01.
- Hàm daily metrics tạo PF=2.044444, nhưng lookup `profit_factor` của D2 trả null.
- Chuỗi chỉ có ngày lỗ bị ghi `NO_TRADES`; dữ liệu lợi nhuận ngày không đủ để suy ra không có giao dịch.
- RF-05 giữ lại ngày trước evaluation_start trong chuỗi chênh lệch lợi nhuận.

Hash tham chiếu ngược FUP-02: `{"cell_coverage_sha256": false, "coverage_review_sha256": false}`. Chiều từ coverage/review tới checkpoint: `{"cell_coverage.json": true, "coverage_review.json": true}`.

Nguồn máy đọc: [audit.json](evidence/reviews/time-edge-20260912-review01/audit.json), [observations.json](evidence/reviews/time-edge-20260912-review01/observations.json), [source_probes.json](evidence/reviews/time-edge-20260912-review01/source_probes.json), [capture_manifest.json](evidence/reviews/time-edge-20260912-review01/capture_manifest.json).

<!-- END MEASURED_REVIEW -->

### 2.1 Đọc trạng thái lịch sử thế nào

| Giai đoạn | Đã có | Quyền diễn giải hiện tại |
|---|---|---|
| LAB-01…09 | Reports, artifacts, historical tests; LAB-09 có `FAILED_VALIDITY` | Các subclaims cũ được supersede bằng RF-01 invalidation; giữ nguyên lịch sử |
| RF-01 | Identity, registration, audit findings, before-repair tests | Technical preparation; không market edge |
| RF-02 | Public Mode 4 binding, event account, pilot và route qualification | Supported scope; báo cáo tự ghi `PARTIAL_TECHNICAL_CLOSURE` |
| RF-03 | Controller tests, context/mapping repairs và dispositions | Có helper/unit repairs; cần chứng minh chúng đi vào tape/controller thực |
| RF-04 | Cặp pilot, 10-cell scaled results, model design riêng, decay/controls ở pilot | Không được dùng bảng decay pilot như bằng chứng decay của scaled cohort/FUP |
| RF-05 | Freeze, recompute, claim `INCONCLUSIVE`, handoff | Kết luận đã lưu; review này chưa nghiệm thu lại vì các findings về window/model/metrics |
| FUP-01 | VWAP/HASH command capability; committed evidence | Khả năng lệnh có chứng cứ; không phải 20-cell market comparison |
| FUP-02 | Budget revision, resumable shards, partial real results | Tiếp tục theo chỉ thị người dùng; giữ discovery, không tự nâng thành xác nhận |
| FUP-03 | Prospective registration | Chưa có evidence execution; cần post-freeze data eligibility thực và protocol hiện hành |

**Đánh giá hướng làm của OpenCode/Claude:** hướng primary Mode 4 và việc giữ kết luận INCONCLUSIVE
phù hợp ý chính G3; FUP-01/02 đang mở capability, coverage và compute. Tuy nhiên, chưa đáp ứng đầy đủ
hai guide về actual deployed model, causal readiness, kiểm chứng positive/null toàn pipeline, decay
và báo cáo từng phase. Các mục đó phải được nghiệm thu theo evidence, không dựa vào agent nào làm
hoặc nhãn COMPLETE. Git/artifacts ở đây không đủ để quy từng lỗi cho riêng OpenCode hay Claude.

Nguồn lịch sử: [RF-01 report](evidence/corrective_mode4_v3/RF-01/report.md),
[RF-02 report](evidence/corrective_mode4_v3/RF-02/report.md),
[RF-03 report](evidence/corrective_mode4_v3/RF-03/report.md),
[RF-04 report](evidence/corrective_mode4_v3/RF-04/report.md),
[RF-05 report](evidence/corrective_mode4_v3/RF-05/report.md),
[FUP-02 report](evidence/corrective_mode4_v3/FUP-02/report.md).
Các file live này có thể thay đổi; khi đối chiếu findings dùng bản chụp trong [capture manifest](evidence/reviews/time-edge-20260912-review01/capture_manifest.json).

<a id="guide-index"></a>
## 3. Chỉ mục nghĩa vụ trong hai guide

| Chủ đề | Final V2 | Corrective V3 | Nơi thực hiện/đọc báo cáo |
|---|---|---|---|
| Safety, phạm vi, provenance, presets | [§0][g2-0], [§1][g2-1], [§2][g2-2], [§6][g2-6] | [§1][g3-1], [§4.2][g3-4.2], [RF-01][g3-rf01] | TE-01 |
| Bốn alpha và economic/execution contract | [§3][g2-3], [§4][g2-4] | [§3][g3-3], [§4.1][g3-4.1], [§5][g3-5], [RF-02][g3-rf02] | TE-02 |
| Robust selector / Mode 4 thực | [§7][g2-7], [§10.1][g2-10.1] | [§2][g3-2], [§7.4][g3-7.4], [§8.4][g3-8.4] | TE-02; TG-03 |
| Model regime, nhãn, feature information | [§6.4][g2-6.4], [§8][g2-8] | [§7.2][g3-7.2], [RF-03][g3-rf03], [§11.3][g3-11.3] | TE-03; model dossier |
| Availability, clocks và deployment | [§8.4][g2-8.4], [§9][g2-9] | [§7.3][g3-7.3], [§7.4][g3-7.4], [§11.2][g3-11.2] | TE-02 + TE-03 |
| Timing/cadence/risk/selector attribution | [§10][g2-10] | [§2.2][g3-2.2], [§2.3][g3-2.3], [RF-04][g3-rf04] | TE-04 |
| Return, PF, Sharpe, ba loại decay | [§11][g2-11] | [§6.1–6.5][g3-6], [§11.4][g3-11.4] | TE-04; TG-07/08 |
| Statistical uncertainty, MDE, multiplicity | [§11.2][g2-11.2], [§11.3][g2-11.3] | [§6.6][g3-6.6], [§6.7][g3-6.7], [RF-05][g3-rf05] | TE-04 → TE-05 |
| Compute và tốc độ | [§0.3][g2-0.3], [§10.5][g2-10.5] | [§8][g3-8] | TE-02; measured budget ở mọi phase |
| Report, charts, reproducibility và claims | [§12][g2-12], [§13][g2-13], [§14][g2-14] | [§10][g3-10], [§11][g3-11], [§12][g3-12] | Mọi phase; TE-05 đóng |
| E response/selector extension | [§7.4][g2-7.4], [§9][g2-9], [§10.1][g2-10.1] | [§7.5][g3-7.5], [§12.3][g3-12.3] | TG-12; disabled hoặc nghiên cứu phụ riêng |

<a id="code-map"></a>
## 4. Bản đồ code, evidence và phạm vi rà soát

Đọc từ entry point tới account/statistics; sự tồn tại của helper đúng không chứng minh caller dùng nó.
Inventory đầy đủ: [source_inventory.json](evidence/reviews/time-edge-20260912-review01/source_inventory.json),
[evidence_inventory.json](evidence/reviews/time-edge-20260912-review01/evidence_inventory.json).

| Thành phần | Code / entry point cần theo | Evidence đầu vào/đầu ra | Điều phải chứng minh |
|---|---|---|---|
| Safety/data | `safety/`, `data/`; `scripts/run_rf04_paired_pilot.py:load_frame` | sandbox policy, snapshot manifest, data eligibility | Worker containment thực; clock/symbol/hash/coverage đúng |
| Alpha | `alphas/a_sc.py`, `a_hma.py`, `a_vwap.py`, `a_hash.py`, `base.py`, `contracts.py` | semantic delta, schemas, route registry, FUP-01 | Giữ thesis/version, mọi sampled parameter có nghĩa, bảo toàn lệnh |
| Selector | `selector/`, `experiments/dynamic_fold_provider.py:EventAccountScorer` | trial ledger, selected params, scorer metadata | Mode 4 thật và scorer phù hợp cùng economic contract |
| Model | `regime/`, `scripts/fit_regime_model.py`, `run_rf04_g10_model_repairs.py` | model registry, design manifest, emissions | Model đã chọn được deployed; labels có lineage và điểm mạnh/yếu đo được |
| Controller | `experiments/regime_schedule.py`, `dynamic_fold_provider.py:regime_cutoffs` | trigger/search/ready/activation ledger | Không đọc thông tin chưa có; không biến model refit thành market transition |
| Execution | `integration/event_account.py`, `continuous_account.py`, `activation.py`, `execution_clock.py` | engine equity/positions/fills/orders, version tape | Một account liên tục; đúng resolution, ready time và campaign policy |
| FUP runner | `scripts/run_fup02.py` | FUP-02 shards/trials/attempts/budget | Resume deterministic, failures retained, resource cap thật |
| Decay/controls | `scripts/run_rf04_decay_and_controls.py`, `run_rf04_gap_close.py` | D1/D2/D3, controls/funnel | Metric đúng definition; cùng params khi cần; đủ attribution |
| Inference | `experiments/uncertainty.py`, `scripts/run_rf05.py`, `evidence/claim_gate.py` | paired series, resampling, MDE, family claims | Đúng dates/weights/dependence/threshold; gates không tự xác nhận |
| Historical/secondary | `evaluator.py`, `factorial.py`, `policy/`, `response/`, old runners | LAB artifacts, invalidation, secondary disposition | Không bị gọi lại như corrected primary; mọi đường chưa sửa bị quarantine |
| CLI/report/audits | `cli.py`, report writers, `tests/`, audit scripts | Markdown/JSON/charts/source hashes | Default entry points dẫn đúng study; report từ artifact đã đóng |

`quantbt_candidate`, installed wheels và raw alpha copies được dùng như nguồn tham chiếu đã pin,
không là package mới đã sửa trong lượt này. Các repos production không thuộc phạm vi ghi.

<a id="findings"></a>
## 5. Findings và disposition cần thực hiện

**Phân loại bằng chứng:** `SOURCE_CONFIRMED` = đường code đọc được; `PROBE_CONFIRMED` = counterexample
nhỏ đã chạy; `ARTIFACT_CONFIRMED` = giá trị có trong snapshot; `NEEDS_RUNTIME_PROOF` = cần integration
để xác định toàn bộ ảnh hưởng. `P0` chặn kết luận của contrast bị ảnh hưởng; không có nghĩa mọi artifact
trong lab đều sai. `P1` chặn nghiệm thu một deliverable/phạm vi cụ thể. `SCOPE` là giới hạn phải giữ.

Mỗi finding dưới đây đang **OPEN** trong kế hoạch này, kể cả khi report lịch sử dùng chữ “fixed”.
Chỉ chuyển sang CLOSED khi có test đúng đường runtime và affected outputs đã được xử lý.

<a id="tef-01"></a>
### TEF-01 — Cửa sổ thống kê chứa warmup trước kỳ đánh giá · P0 · TE-01/04

- **Evidence:** [observations account_windows](evidence/reviews/time-edge-20260912-review01/observations.json).
  RF-04 A-HMA/BTC account có 214 equity dates trước 2021-01-01, đều flat; RF-05 dùng cả chuỗi qua
  `paired_daily_diff` ở [run_rf05.py](scripts/run_rf05.py). FUP-02 tiếp tục lưu prefix từ 2020-06-01.
- **Chứng minh:** `ARTIFACT_CONFIRMED + PROBE_CONFIRMED`. Giữ raw equity để warmup/reproduce là hợp lệ;
  đưa các ngày ngoài evaluation window vào mean/Sharpe/bootstrap là lỗi estimand của kỳ đã đăng ký.
- **Sửa/test:** dùng previous mark để tính first return, sau đó lọc return timestamps vào `[eval_start, eval_end)`;
  test phí observation đầu, ngày đầu kỳ, warmup dài/ngắn không đổi statistic trong kỳ, symbol thiếu coverage.
- **Rerun:** trước hết recompute statistics từ saved paths; chỉ rerun engine nếu execution/selection cũng sai.
- **Guide:** [G3 §6.2][g3-6.2], [§6.6][g3-6.6], V3:T51/T52/T58; [G2 §10.3][g2-10.3].

<a id="tef-02"></a>
### TEF-02 — Age windows D2 dùng chung ngày biên · P1 · TE-04

- [daily_metrics/age_windows/d2_replay](scripts/run_rf04_decay_and_controls.py) chọn `<= hi` ở cả hai
  cửa sổ; source probe hai khoảng 90 ngày trả 91 observations mỗi khoảng. Artifact có cả rows 90/91 ngày.
- **Chứng minh:** `PROBE_CONFIRMED + ARTIFACT_CONFIRMED`; thống nhất half-open `[a,b)`, timezone và
  nhãn daily mark. Window sau nhận boundary return đúng một lần, không mất phí/PnL ở đầu kỳ.
- **Gate:** tập dates disjoint; money PnL partition telescope; compounded returns khớp whole path.
- **Guide:** [G3 §6.2][g3-6.2], [§6.5][g3-6.5]; V3:T51/T52/T57.

<a id="tef-03"></a>
### TEF-03 — Profit Factor lookup và trạng thái không đúng · P1 · TE-04

- D2 tra key `profit_factor`, trong khi `daily_metrics` trả `profit_factor_daily`: toàn bộ PF D2 đang null,
  kể cả rows có underlying PF hữu hạn. Daily metrics cũng gắn `NO_TRADES` cho chuỗi ngày chỉ lỗ.
- **Chứng minh:** `SOURCE/PROBE/ARTIFACT_CONFIRMED`. Có negative-return observations không chứng minh
  số trades; với denominator losses > 0 và gains = 0, return-based PF = 0 theo definition.
- **Sửa/test:** tên metric có sampling/unit/source; PF có lãi/lỗ, chỉ lãi, chỉ lỗ, flat, no fills,
  open positions, fee-only ngày đầu. D2 PF log-gap chỉ khi cả PF > 0 và hữu hạn; còn lại null + reason đúng.
- **Guide:** [G3 §6.4][g3-6.4], [§6.5][g3-6.5], V3:T54/T56; không suy trade PF từ daily returns.

<a id="tef-04"></a>
### TEF-04 — Bảng decay chưa trả lời so sánh hai method trong scope hiện tại · P1 · TE-04

- [decay_panels.json](evidence/corrective_mode4_v3/RF-04/decay_panels.json) chỉ có hai pilot cells;
  D2 chỉ bốn fold-0 anchors; có H1−H1 self-comparisons và A-SC replay route khác pilot route.
  D1 gắn selected digest với operational OOS interval, dù incumbent có thể còn active sau cutoff.
- **Chứng minh:** scope/route `ARTIFACT_CONFIRMED`; mức gán sai PnL cho selected params cần runtime trace.
  “Có 36 rows” không phải 36 independent tests; “D2 COMPLETE” không phải đã chứng minh giảm decay.
- **Sửa/test:** giữ D1 fixed-selected evaluation và operational carried-account attribution riêng;
  anchors có selection/activation lineage; so method trên shared calendar/age design đã đăng ký;
  loại H1−H1 khỏi denominator kiểm định nhưng giữ làm reference.
- **Guide:** [G3 §6.5][g3-6.5], [§6.6][g3-6.6], [RF-04][g3-rf04]; V3:T55–T58.

<a id="tef-05"></a>
### TEF-05 — Model selection/repair chưa nối vào tape chính · P0 đối với claim model mới · TE-03

- FUP-02 và scaled RF-04 đọc `configs/lab05_full_emission_tape.json`. Registry của tape đó dùng
  K=3/lambda=1.0. RF-04 chọn riêng K=3/lambda=0.5 và ghi **RECORDED_DESIGN_SELECTION**.
- Tape chính không mang `ready_at`, `model_fit_cutoff`, `state_common`, `economic_context`; các model
  sample/coordinate repairs ở RF-04 không tự thay thế nó. [Model observations](evidence/reviews/time-edge-20260912-review01/observations.json).
- **Sửa/test:** registry → frozen model design → emitted tape → controller dùng đúng hashes và schema;
  không sửa lại tape historical. Tape mới có đủ lineage; assert actual deployed design, không chỉ file tồn tại.
- BTC làm context chung cho các symbol có thể là hypothesis hợp lệ; phải đăng ký như vậy và giới hạn claim.
  Không tự coi common BTC là lỗi bắt buộc sửa thành per-symbol, cũng không claim đã thử per-symbol model.
- **Guide:** [G3 §7.2][g3-7.2], [RF-03][g3-rf03], V3:T29/T42/T43/T50; [G2 §8][g2-8].

<a id="tef-06"></a>
### TEF-06 — Controller không kiểm model ready; input thiếu field được mặc định hợp lệ · P0 · TE-03

- [online_trigger_schedule](src/crypto_regime_lab/experiments/regime_schedule.py) kiểm `available_at`
  và quality/eligibility nhưng không kiểm model-ready; missing `decision_eligible` mặc định True,
  missing quality mặc định OK. Probe đưa model ready năm 2025 vẫn trigger tại 2021.
- **Chứng minh:** `PROBE_CONFIRMED`; active tape thiếu ready nên caller chưa đủ thông tin để chứng minh
  eligibility đầy đủ. Không đơn giản lấy wall time năm 2026 làm operational historical ready time.
- **Sửa/test:** phân biệt `computed_at_wall_utc` với `ready_at_replay`; validation bắt missing/late/stale/
  unknown/ambiguous; actual scheduler test future-ready không trigger, positive eligible case trigger.
- **Guide:** [G3 §7.3][g3-7.3], [§7.4][g3-7.4]; V3:T04/T05/T29/T30/T32.

<a id="tef-07"></a>
### TEF-07 — Không có initial/max-age lifecycle đầy đủ · P1 · TE-02/03

- `last_trigger` bắt đầu None; max-age chỉ chạy sau khi đã có trigger đầu. Probe tape constant một năm
  không có refresh dù max-age=180 ngày. Provider cũng từ chối empty cutoff list; dynamic arm khởi đầu
  tại first trigger, calendar có initial cutoff riêng.
- **Sửa/test:** common initial incumbent hoặc explicit common flat policy; đồng hồ tuổi tham số bắt đầu
  từ incumbent availability. Zero-transition phải có keep/max-age theo protocol, không empty schedule error.
  So sánh initial exposure/latency giữa hai arms để tránh gọi thời gian đứng ngoài thị trường là parameter edge.
- **Guide:** [G3 §7.3][g3-7.3], [§2.3][g3-2.3], V3:T03/T31/T32/T40.

<a id="tef-08"></a>
### TEF-08 — Purge forward outcomes sai phía trong model ablation · P0 đối với information claim · TE-03

- [fixed_target_ablation](src/crypto_regime_lab/regime/ablation.py) fit state target profile từ
  `target[:train_end]`; chỉ bỏ đầu validation. Với target horizon 6, sáu training origins cuối có outcome
  kết thúc tại/sau cutoff. Bỏ validation head không làm các training outcomes ấy trở thành thông tin đã có.
- [forward_paired_target](scripts/run_rf04_g10_model_repairs.py) là future market return trừ trailing
  market return, không phải QuantBT paired candidate utility. Tên “paired” chưa chứng minh parameter ranking.
- **Sửa/test:** purge theo `outcome_available_at <= decision_time` và sequence contract; mutate chỉ
  outcomes chưa kết thúc phải giữ nguyên fitted response/profile trước cutoff. Feature/model scaler và
  supervised target-profile đều phải qua gate; giữ proxy như descriptive diagnostic.
- **Guide:** [G3 §7.2][g3-7.2], [§7.5][g3-7.5]; V3:T43/T44/T45; [G2 §9.1][g2-9.1].

<a id="tef-09"></a>
### TEF-09 — Positive control chưa kiểm full learned pipeline · P1 · TE-03/04

- [run_rf04_step1.py](scripts/run_rf04_step1.py) tạo emissions từ world state và chọn params từ
  `params_for_state[state_by_bar[b]]`. Không fit JM để infer labels, không chạy Mode 4 để tìm params.
  Test chủ yếu assert params/fill counts khác nhau.
- **Chứng minh:** `SOURCE_CONFIRMED`; đây là execution/controller plumbing control, có giá trị ở scope đó.
  Nó chưa chứng minh khả năng học regime rồi tìm time edge, hoặc false-positive rate của phép thử cuối.
- **Sửa/test:** giữ control cũ đúng nhãn; thêm full-path positive/null worlds qua feature/model/selector/
  scheduler/account/statistics, không đưa ground-truth state/optimal params vào policy.
- **Guide:** [G3 RF-03.4][g3-rf03], [§11.2][g3-11.2]; V3:T38/T39; [G2 §10.2][g2-10.2].

<a id="tef-10"></a>
### TEF-10 — Route đúng engine chưa đồng nghĩa đúng clock/resolution · P0 nếu claim sai cohort · TE-02

- FUP-02 đưa frame 1h cho A-HMA, 15m cho các alpha còn lại vào event account; event account chạy trên
  chính frame đó. Chưa phải bằng chứng protection 1m. `ENGINE_EFFECTIVE_PHASE` là next_bar với engine
  xử lý tại close theo binding hiện có; `declared_phase=next_open` không tự thay execution clock.
- FUP-01 ghi backend resolved Python. Phải giữ requested/resolved riêng; không claim Rust speedup từ tên route.
- **Sửa/test:** trace full public route cho gap/stop/TP/HTF boundary; hoặc dựng 1m execution đúng guide,
  hoặc đăng ký một coarse/next-close cohort riêng với consequence rõ. Cả scoring và deployment cùng contract.
- **Guide:** [G3 §5][g3-5], [§4.1 A06][g3-4.1], [§4.3 N02][g3-4.3]; V3:T06/T07/T08/T68; [G2 §4][g2-4].

<a id="tef-11"></a>
### TEF-11 — Ready/activation/warmup không có trace đủ để chứng minh policy · P0/P1 · TE-02

- Event deployment nhận VersionWindow từ cutoff, không propagate selection-ready/compute-latency
  đã ghi trong corrective spec. Pending version đếm warm bars rồi sau activation lại chờ warmup;
  chưa thấy indicator-only warming ở pending loop. Main payload chỉ giữ 8 labels đầu trong `versions`.
- **Chứng minh:** `SOURCE_CONFIRMED`; mức sai behavior theo alpha cần actual integration witness.
  Không giả định chỉ bỏ thời gian chờ là sửa đúng; có indicator precompute và stateful recurrence cần kiểm riêng.
- **Sửa/test:** readiness dùng past history; common initial; pending/superseded/campaign migration;
  lưu compressed full parameter-version intervals và first affected order; không double warm hoặc backdate.
- **Guide:** [G3 §7.3–7.4][g3-7.3], [RF-02][g3-rf02]; V3:T04/T21/T22/T32/T49; [G2 §9.4–9.5][g2-9.4].

<a id="tef-12"></a>
### TEF-12 — Candidate scorer metrics/support cần qualify lại · P0 nếu đổi selection · TE-02

- [EventAccountScorer](src/crypto_regime_lab/experiments/dynamic_fold_provider.py) chạy account bắt đầu
  từ train start rồi đọc các subperiods; không lấy pre-train warmup vào score run. Mỗi subperiod trả
  `trade_count/turnover` từ fill count của whole cached account, không từ riêng khoảng score.
- `_annualised_sharpe` có nhánh ít daily observations chuyển sang bar returns nhưng vẫn nhân sqrt(365).
  First-return/fee và minimum-support phải được qualify cùng Mode 4 penalty/temporal objective.
- **Chứng minh:** `SOURCE_CONFIRMED`; tác động selector/penalty cần public-path parity trước kết luận.
- **Sửa/test:** scorer output có definition/canonical units và per-window counts; warm outside scoring;
  selected audit parity với QuantBT cùng dates/economics; không sửa objective chỉ ở một arm.
- **Guide:** [G3 §2.1][g3-2.1], [§4.3 N04/N05][g3-4.3], [RF-02.4][g3-rf02]; V3:T25–T28/T53/T55.

<a id="tef-13"></a>
### TEF-13 — Chấm một cutoff còn chạy deployment tới cuối frame · P1 compute / P0 failure semantics · TE-02

- [run_one_fold](scripts/run_fup02.py) gọi provider. Provider sau selection còn gọi
  `_event_account_payload` trên full frame. Sau khi đủ cutoffs, FUP runner lại deploy full arm.
- Source path này tạo công việc lặp và cho phép lỗi **sau cutoff** làm cả kết quả fold thành ERROR.
  Checkpoint SOL ghi cutoff 2022-02-26 nhưng callback failure ở 2022-11-10; đây là evidence cần tách
  training-selection status khỏi post-selection deployment status, không mặc định đây là selection leakage đã chứng minh.
- **Sửa/test:** training-only operation trả selected/trials trước; deployment riêng một account/arm;
  future suffix mutation không đổi selection hoặc xóa completed training ledger. Đo counters trước/sau.
- **Guide:** [G3 §2.4][g3-2.4], [§7.4][g3-7.4], [§8.2][g3-8.2]; V3:T27/T35/T63/T66/T67.

<a id="tef-14"></a>
### TEF-14 — Runtime errors và trial retention chưa đủ · P0/P1 · TE-02

- SOL có callback `limit commands require price > 0`. Provider bắt exception và trả error-only;
  FUP chỉ append trial rows cho SCORED cutoffs. Các thử nghiệm đã xảy ra trong errored cutoff có thể
  không đi vào ledger cuối; `infeasible_trials=0` không chứng minh không có sampled points không khả thi.
- **Sửa/test:** xác định alpha/params/bar/command/version gây lỗi; tách domain infeasibility, runtime bug,
  prune, timeout và deployment failure. Giữ tất cả attempts/intermediate/partial trials, cấm −1e9 financial
  COMPLETE; chỉ rerun affected work với registration/version mới khi cần.
- **Guide:** [G3 §4.2 D03/D08][g3-4.2], [§8.1][g3-8.1]; V3:T12/T13/T18/T36/T63.

<a id="tef-15"></a>
### TEF-15 — Budget và resume chưa phải total-compute gate · P1 · TE-02

- Total wall budget có field 43.200 giây nhưng đường main deadline dựa vào invocation hiện tại;
  chưa thấy gate trừ tổng spent trước khi mở invocation kế. Resume chủ yếu kiểm trials/seed/window/budget hash,
  chưa đóng đầy đủ code/alpha/schema/model/tape/route identity.
- **Sửa/test:** cộng failed/retried/completed/aborted costs, nêu phần không đo được; invocation budget không
  được vượt remainder; crash-safe resume theo manifest identity, append-only revisions, không ghi đè completed shard.
- Trial coverage hơn ngưỡng nonfinite phải theo registered review, trước final freeze; kiểm nguyên nhân trước
  tăng compute. Số trials/cutoff bằng nhau không phải tổng ngân sách hai arms bằng nhau.
- **Guide:** [G3 §8][g3-8], V3:T33–T36/T63/T66/T67; [G2 §10.5][g2-10.5].

<a id="tef-16"></a>
### TEF-16 — Báo cáo và hash drift, missing phase report · P1 · TE-01/05

- `write_checkpoint` ghi main payload trước khi gắn hashes của coverage/review mới; main chứa backlink
  của lần trước. Probe đọc ổn định chứng minh mismatch, dù chiều coverage→main khớp.
- RF-04 report còn pilot while scaled artifact mới hơn; FUP-02 report có thể chậm checkpoint và in
  “committed artifacts” khi file chưa commit. FUP-01 snapshot chưa có `report.md/report.json` riêng.
  AGENTS/CLAUDE ghi “complete” rộng hơn `PARTIAL_TECHNICAL_CLOSURE` của RF-05.
- **Sửa/test:** immutable checkpoint generations + external root manifest không self/circular hash;
  report pin một generation; verify numbers/counts/status/commit provenance; current index dẫn superseding
  report, không sửa registration/historical artifacts để xóa lịch sử.
- **Guide:** [G3 §10][g3-10], [§12.6][g3-12.6]; V3:T62/T64/T65/T69/T70.

<a id="tef-17"></a>
### TEF-17 — Statistics/claim gates có chữ thống kê nhưng chưa được calibration đầy đủ · P1 · TE-04/05

- RF-05 có block bootstrap và Holm, nên không đúng nếu nói “không có thống kê nào”. Tuy nhiên tests
  chủ yếu kiểm fields/denominators dương và nhãn INCONCLUSIVE; chưa chứng minh test có đúng coverage/power.
- `p_two_sided` là tỷ lệ bootstrap draws nằm hai phía 0; cần validate cách dùng như p-value dưới null,
  và consistency với hypothesis về ngưỡng kinh tế δ, không chỉ sign/zero. Đây là `NEEDS_STATISTICAL_VALIDATION`,
  chưa kết luận mọi bootstrap percentile CI tự động sai.
- Identical equity series đang tự thành `NOT_EVALUABLE`/“treatment did not reach execution”. Đường tài khoản
  trùng nhau có thể là outcome hợp lệ; phải xét pipeline/control/action ledger trước khi quy lỗi implementation.
- **Gate:** calibration bằng null/known-effect worlds; confidence interval, multiplicity, dependence,
  zero variance, constant nonzero difference, missing cells và MDE cùng units; không chọn block length theo p đẹp.
- **Guide:** [G3 §6.6–6.7][g3-6.6], [§12.2][g3-12.2]; V3:T38/T39/T60/T61; [G2 §11.3][g2-11.3].

<a id="tef-18"></a>
### TEF-18 — Attribution controls và study design còn partial · P1/SCOPE · TE-04

- FUP-02 chưa có matched control/decay/paired uncertainty. RF-05 budget-aware chỉ một cell evaluable;
  A-SC matched control ở endpoint khác primary event route. `placebo` hiện là delayed tape, không phải
  một control giả trạng thái độc lập với thông tin thị trường.
- **Sửa/test:** calendar comparator được chọn trên development, giới hạn max budget ex ante; ghi realized
  compute riêng. Dwell-matched placebo, delayed-state và risk-only có rationale/budget; không loại control vì thắng.
- Không dùng realized future regime count để dựng live-feasible calendar trên chính evaluation path rồi
  gọi information edge. Nếu phân tích hồi cứu như vậy, giữ nhãn diagnostic.
- **Guide:** [G3 §2.2–2.3][g3-2.2], [RF-04.4][g3-rf04]; [G2 §10.2][g2-10.2].

<a id="tef-19"></a>
### TEF-19 — Mất execution lineage và metric aliases · P1 · TE-02/05

- Main provider payload cắt version tape còn 8 phần tử, bỏ order IDs/version/sequence khỏi fills, và
  `engine_report.num_trades` lấy engine fill count. FUP-02 report gọi chúng là trades.
- Decay `exposure` hiện đếm bars có adapter active, không phải bars có vị thế; không dùng nó như financial exposure.
- **Sửa/test:** lưu interval tape đầy đủ, order/fill/campaign lineage và engine positions; phân biệt entries,
  partial fills, completed campaigns, decision availability và actual exposure. Chart activation phải truy được.
- **Guide:** [G3 §4.3 N04][g3-4.3], [§6.1][g3-6.1], [§10.5][g3-10.5]; V3:T10/T21/T32/T49/T54/T64.

<a id="tef-20"></a>
### TEF-20 — Scope limitations và đường cũ chưa được đóng ở entry point · P1/SCOPE · TE-01/05

- Funding vẫn missing; instrument/tick/lot provenance cần trace theo symbol. Không suy venue-exact từ
  cùng một placeholder symbol trong engine. CLI `run` còn dẫn về LAB-08 historical runner.
- Test quarantine hiện có kiểm marker và vài source modules, chưa tự chứng minh mọi public entry point
  từ chối historical economic inference. Những module E/response đúng unit nhưng chưa market-evaluate phải giữ riêng.
- **Sửa/test:** canonical runner/study routing, protected source integrity, explicit no-funding cohort,
  per-symbol contract registry; quarantine test bằng invocation bị từ chối, không chỉ grep string.
- **Guide:** [G3 §1.3][g3-1.3], [§4.2][g3-4.2], [§7.5][g3-7.5], [§12.4][g3-12.4]; [G2 §13][g2-13].

### 5.1 Kết nối với findings audit gốc

| Findings G3 | Review hiện tại cần giữ/kiểm lại |
|---|---|
| A01 phí | Giữ repair đã có; TG-02 kiểm cùng rate ở scorer/deployment/partial fills, không giả tự regression-free |
| A02–A04 | TEF-06/07/10/11/13/14/19 |
| A05 enum/parameter effect | TEF-12/14; TG-02/03 kiểm từng category và sampled feasible domain |
| A06 resolution | TEF-10 |
| A07 boundary PnL | TEF-01/02/03 |
| A08 Mode 4 | TEF-09/12/13 |
| A09 E alias | TEF-20; TG-12 |
| A10 namespace/controller | TEF-05/06/07 |
| A11 economic context | TEF-05/08; TG-05/06 |
| A12/A13 response support/bank | TEF-08/11/19/20; secondary quarantine khi chưa mở |
| A14 model selection/scaling/ablation | TEF-05/06/08/09 |
| A15 MDE units | TEF-01/12/17/18; TE-01 khóa lại derivation trước results |
| A16 claim gating | TEF-17/20 |
| D01–D08 | Capture/repro, current interpreter, full ledger, exact counts, instrument/funding scope, docs/routing và runtime tests |
| N01–N05 | TEF-02/03/10/12/16/19 |

Không thay disposition gốc bằng bảng này. TE-01 tạo superseding disposition ledger với old ID, current
source/hash, affected contrasts, current proof, retest và output cần tái tạo.

<a id="phase-index"></a>
## 6. Kế hoạch thực hiện nối tiếp — năm phase TE

TE là nhãn tracking của **lượt sửa/kiểm chứng tiếp theo**, không sửa tên hoặc claim của RF/FUP đã chạy.
Study ID đề xuất `time_edge_validation_v4` là **PLANNED**, chưa có registration được frozen.

| Phase | Mục tiêu | Guide gốc | Dependencies | Trạng thái hiện tại |
|---|---|---|---|---|
| [TE-01](#te-01) | Khóa scope, hypotheses, identities, metric definitions và audit backlog | G3 RF-01; G2 LAB-01/03 | Registration đã kiểm; tiếp nhận cuối FUP-02 còn pending | TECHNICAL_REGISTRATION_VALIDATED; PHASE_PARTIAL |
| [TE-02](#te-02) | Correct economic engine, Mode 4, delivery, budget/resume | G3 RF-02 + RF-03.3; G2 LAB-02/04/07 | TE-01 contracts | NOT_STARTED |
| [TE-03](#te-03) | Model regime được đánh giá và nối vào controller, full positive/null capability | G3 RF-03; G2 LAB-05/06 | TE-01; dùng engine đã qualify ở TE-02 cho full controls | NOT_STARTED |
| [TE-04](#te-04) | Controlled discovery, time edge, decay và uncertainty | G3 RF-04; G2 LAB-08 | TE-02 + TE-03 technical gates | NOT_STARTED |
| [TE-05](#te-05) | Freeze, confirm trong đúng data role, claims và handoff | G3 RF-05; G2 LAB-09/10 | TE-04 design freeze; data eligibility | NOT_STARTED |

Thứ tự code repairs có thể đan xen giữa TE-02/03, nhưng market inference phải chờ cả hai. Không mở
phase bằng chữ COMPLETE từ phase cũ; mỗi gate đánh giá đúng source/model/engine/data version đang dùng.

**Chỉ mục báo cáo mới:** namespace đề xuất `evidence/time_edge_validation_v4/TE-0N/<run_id>/`.
Mỗi run có `report.md`, `report.json`, `artifact_manifest.json`; audit TE-01 đã có, các phase sau chưa chạy.
Sau mỗi run, cập nhật link đúng run trong bảng dưới, không trỏ tới file có thể bị ghi đè.

| Phase | Report MD / JSON hiện có | Nhiệm vụ kế tiếp | Chủ sở hữu thực hiện / reviewer |
|---|---|---|---|
| TE-01 | [Report MD][te01-report] / [JSON][te01-json]; [identity supplement][te01-identity] | TE01.1 chờ bàn giao cuối FUP-02; chuẩn bị qualification TE-02/03 theo gates | Codex; chưa có reviewer độc lập |
| TE-02 | Chưa có — NOT_STARTED | Sau TE-01: TE02.1/2 route + scorer qualification | Codex; chưa có reviewer độc lập |
| TE-03 | Chưa có — NOT_STARTED | Sau TE-01: TE03.1/2 model protocol + causality | Codex; chưa có reviewer độc lập |
| TE-04 | Chưa có — NOT_STARTED | Sau TE-02/03: TE04.1 paired pilot | Codex; chưa có reviewer độc lập |
| TE-05 | Chưa có — NOT_STARTED | Sau TE-04: TE05.1/2 freeze + data-role eligibility | Codex; chưa có reviewer độc lập |

<a id="te-01"></a>
### TE-01 — Registration, nguồn sự thật và phạm vi tái sử dụng

**Guide:** [G3 RF-01][g3-rf01], [§6.6–6.7][g3-6.6], [§10][g3-10];
[G2 §0][g2-0], [§2][g2-2], [§6][g2-6], [§13][g2-13].
**Findings:** TEF-01/05/15/16/17/18/20. **Ngân sách loại T0:** reads/schema/probes; chưa engine run.

| Task | Việc cần làm | Output bắt buộc | Gate |
|---|---|---|---|
| TE01.1 | Pin git/source/package/module/snapshot/alpha/schema/model hashes; capture FUP generation và interrupted attempts | `source_data_manifest.json`, `fup02_intake.json` | Không missing identity được quảng cáo reproducible |
| TE01.2 | Map A01–A16, D01–D08, N01–N05 và TEF-01…20 tới actual paths/callers/tests | `finding_disposition.json` | Mỗi finding có affected scope, bằng chứng, retest và owner |
| TE01.3 | Khóa evaluation dates, UTC boundaries, initial/terminal policies, warmup vs scoring; thống nhất metrics | `metric_contract.json`, `evaluation_windows.json` | Tests biên/first fee trước báo cáo mới |
| TE01.4 | Register hypotheses, estimator, weights/missing-cell policy, δ và multiplicity, support/power, stopping | `study_registration.json`, `statistical_analysis_plan.json` | Không null bắt buộc; chưa nhìn results mới để chọn metric thắng |
| TE01.5 | Register model hypothesis: common BTC hoặc per-symbol, features, K/lambda/cadence ladder nhỏ, selection rule | `model_protocol.json` | Không gọi model selection manifest riêng là deployed design |
| TE01.6 | Register route/resolution/compute contract, phase budgets và tier caps | `compute_budget.json`, `execution_contract.json` | Wall/CPU/RSS/candidate work và residual budget có cách đo |
| TE01.7 | Classify evidence reuse; tiếp tục historical invalidation bằng record mới | `reuse_decision.json`, `invalidation.json` | Không sửa curves/history, không tự relabel prospective |

**Registration đang dùng:** [R01 manifest](configs/time_edge_validation_v4/r01/registration_manifest.json),
[Mode 4 resolved knobs](configs/time_edge_validation_v4/mode4_binding_r01.json).
R01 cho phép sửa kỹ thuật; không phải financial spec đã đủ điều kiện chạy thị trường.
Ngưỡng δ đã đăng ký bằng công thức chi phí trên account turnover; số cụ thể và trace calibration
phải được khóa trước TE-04. Không dùng null hoặc ngưỡng lịch sử để bỏ qua gate này.

| Task | Guide chi tiết | Artifact / hợp đồng để thực hiện và nghiệm thu | Trạng thái TE-01 |
|---|---|---|---|
| TE01.1 | [G3 RF01.1][g3-rf011]; [G2 §0][g2-0], [§6][g2-6] | [Source/data manifest][te01-source], [FUP intake][te01-fup], [package binding][te01-binding], [identity supplement][te01-identity] | Đã pin checkpoint; chưa có bàn giao cuối FUP |
| TE01.2 | [G3 RF01.2][g3-rf012], [RF01.4][g3-rf014]; [G2 §14][g2-14] | [Finding disposition][te01-findings], [baseline][te01-baseline], [T01–T64 coverage][te01-acceptance] | Map đủ; chưa coi findings là đã sửa |
| TE01.3 | [G3 RF01.3][g3-rf013], [§6.6][g3-6.6]; [G2 §11][g2-11] | [Metric contract](configs/time_edge_validation_v4/r01/metric_contract.json), [evaluation windows](configs/time_edge_validation_v4/r01/evaluation_windows.json), [tests][te01-tests] | Kiểm hợp đồng arithmetic; chưa nối lại caller RF/FUP |
| TE01.4 | [G3 RF01.5][g3-rf015], [§6.6–6.7][g3-6.6]; [G2 §10][g2-10], [§11][g2-11] | [Study registration](configs/time_edge_validation_v4/r01/study_registration.json), [statistical analysis plan](configs/time_edge_validation_v4/r01/statistical_analysis_plan.json) | Đăng ký hypotheses/CI/multiplicity/support; δ numeric và calibration chờ TE-02/03 |
| TE01.5 | [G3 RF01.5][g3-rf015]; [G2 §8][g2-8] | [Model protocol](configs/time_edge_validation_v4/r01/model_protocol.json) | Đăng ký design/selection/label/fold dossier; chưa fit hoặc deploy |
| TE01.6 | [G3 RF01.1][g3-rf011], [RF01.5][g3-rf015], [§8][g3-8]; [G2 §4][g2-4] | [Execution contract](configs/time_edge_validation_v4/r01/execution_contract.json), [compute budget](configs/time_edge_validation_v4/r01/compute_budget.json), [OS probe][te01-isolation] | Đã đo audit; OS namespace hiện không tạo được, market gate đóng |
| TE01.7 | [G3 RF01.2][g3-rf012]; [G2 §13][g2-13] | [Reuse decision][te01-reuse], [invalidation overlay][te01-invalidation], [correction ledger](configs/correction_ledger.json) | Phân loại theo cell/arm và dependency; giữ nguyên lịch sử |

<!-- BEGIN TE01_MEASURED -->
**Số đo từ run `te01-r01-20260912-01` đã commit:**

- Hợp đồng: **69 PASS**; baseline trước sửa: **8 FAIL đúng lỗi**, unexpected errors **0**.
- Kiểm báo cáo: **5 PASS**; [evidence][te01-report-check].
- Snapshot: **627 files / 1,448,678,208 bytes**, hash/size/row-count metadata khớp; chưa kiểm lại mọi candle row.
- Audit: **16.299s wall**, **10.058s CPU**, peak RSS **213,796 KiB**; engine/optimizer/market tests **0/0/0**.
- FUP snapshot lúc **2026-09-12T06:36:57.892446+00:00**, `PARTIAL_BUDGET_STOPPED`: `{"NOT_RUN_BUDGET": 13, "RUN_VALID": 3, "FAILED": 2, "BUDGET_STOPPED": 2}`; đây là checkpoint đã pin, không phải bàn giao cuối.
<!-- END TE01_MEASURED -->

**Giới hạn cần đọc đúng:** baseline dùng source probes và một centroid stub để cô lập lỗi purge;
không phải full model/engine control. Model cũ là `INHERITED_FROZEN_INPUT`, không được đánh giá lại
trong TE-01. D1/D2/D3 và CAL–REGIME chưa có số đo thị trường mới; TE-03 sở hữu model dossier và
TE-04 sở hữu paired time-edge/decay inference. Findings mới vẫn OPEN đến khi caller thật và
affected outputs được sửa/kiểm; hợp đồng mới PASS không tự đóng chúng.

TE-02 có thể bắt đầu sửa và kiểm kỹ thuật trên bản sao vật lý riêng trong lab dựa trên R01.
Việc sửa trực tiếp code dùng chung với FUP phải chờ bàn giao nguồn;
market workers còn cần OS isolation, engine/model qualification, δ đã materialize và tổng budget.
Xem [phase verdict][te01-verdict] và [reproduction/runtime-gate verification][te01-reproduction].

**Báo cáo TE-01:** bảng planned/existing/reusable/quarantined/needs-rerun theo cell và arm; model readiness,
metric audit trước sửa, toàn findings và đúng test scope. Không có performance claim.

**Exit:** registered spec kiểm được và regression cases đã viết trước repairs; protected sources được
xác minh; central index đủ link tới artifacts. `REGISTRATION_VALIDATED`, không `TIME_EDGE_VALIDATED`.

<a id="te-02"></a>
### TE-02 — Engine/Mode 4 đúng, delivery có causality và tốc độ đo được

**Guide:** [G3 RF-02][g3-rf02], [§5][g3-5], [§7.4][g3-7.4], [§8][g3-8];
[G2 §3][g2-3], [§4][g2-4], [§7][g2-7], [§9.4–9.5][g2-9.4].
**Findings:** TEF-07/10/11/12/13/14/15/19/20. **Tests:** TG-02/03/04/10/11.

| Task | Việc cần làm | Evidence/test bắt buộc |
|---|---|---|
| TE02.1 | Chọn đúng event/signal route theo từng alpha; bảo toàn four-alpha semantic versions và true execution clock | Route matrix đủ 20 cells; gap/partial/ladder/amend/reject fixtures; requested/resolved backend |
| TE02.2 | Sửa scorer warmup, per-window trade/fill/support metrics, penalty/unit boundaries | Same-cutoff public Mode 4 parity; selected params/objective components; no outer OOS selection |
| TE02.3 | Tách train-only selection khỏi continuous deployment | Counter exact số evaluations/deployments; future deployment failure không xóa training result |
| TE02.4 | Common initial; search latency và readiness; pending/supersede; flat/campaign migration | Full trigger→search→selection→ready→activate→first-order trace; two-arm same-contract test |
| TE02.5 | Full order/fill/positions/version trace; reconcile account | IDs/sequence/campaign/fee; no reset/splice; partition và terminal position check |
| TE02.6 | Classify lỗi SOL và domain failures; persist partial trials/attempts | Tiny captured reproducer, failed-before/pass-after; no silent domain narrowing/zero metrics |
| TE02.7 | Resume và total budget; cache identity và crash recovery | Terminate chỉ test child; resumed/fresh parity; no duplicate/lost trials; exhausted total refuses new task |
| TE02.8 | Profile đường đúng trước mở rộng | Cold/warm, native/Python/callback/packing/audit, actual bar visits, allocations, peak RSS, cost per completed cell |

**Tối ưu hợp lệ:** cache market/indicator thuần theo cutoff/version; score gọn nhưng giữ full trial
metadata; một deployment/account/arm; reuse model tape đúng identity. Không tự bỏ lệnh bảo vệ,
đổi resolution hoặc tắt audit để giảm thời gian.

**Báo cáo TE-02:** mỗi alpha có thực thi được những lifecycle events nào, gì chưa exercise; mỗi route có
đúng contract nào; scorer và deployment đã match ra sao; model lúc này **frozen input/stub hay real model**
phải ghi rõ. Báo cáo phí/returns pilot chỉ để chứng minh execution, không dùng để chọn cell thắng.

**Exit:** supported cells có real fills/account và Mode 4 parity; public-path regression đỏ trước/xanh
sau; failures có full ledger; resource gates hoạt động. Alpha blocked vẫn giữ BLOCKED/PARTIAL.

<a id="te-03"></a>
### TE-03 — Model regime có ý nghĩa, có khả năng cung cấp thông tin và được dùng thật

**Guide:** [G3 RF-03][g3-rf03], [§7.2–7.5][g3-7.2];
[G2 §6.4][g2-6.4], [§8][g2-8], [§9.1–9.3][g2-9.1].
**Findings:** TEF-05/06/07/08/09/11/18. **Tests:** TG-04/05/06/09/12.

| Task | Việc cần làm | Output/gate |
|---|---|---|
| TE03.1 | Model ladder M0 + JM K2/K3, lambda/cadence/feature choices có budget và tiêu chí train/inner-valid | `model_design_trials.jsonl`; tất cả alternatives kể cả âm, actual selected design |
| TE03.2 | Inner-train preprocessing, outcome-end purge, common coordinate mapping, warmed online filter | `model_causality.json`; suffix/namespace/scale/refit tests fail on leaky variants |
| TE03.3 | Tạo deployed tape đầy đủ lineage/readiness/quality; immutable vintages | `model_registry.json`, `emissions`, schema và hash join tới actual controller |
| TE03.4 | Dossier nhãn và quality theo từng fit/fold/symbol | Bảng nghĩa trạng thái, occupancy/dwell/transition/unknown/dead states/stability/support |
| TE03.5 | Đo parameter opportunity bằng cùng engine/economics và train-eligible candidate set | `parameter_opportunity.json`; behavioral diversity, rank reversals, support; hindsight chỉ diagnostic |
| TE03.6 | Đo thông tin regime cho **future paired candidate utility/ranking**, tách khỏi prediction market direction | `information_value.json`; held-out time blocks, base comparator, effect/CI/null và eligibility |
| TE03.7 | Positive/null full path và treatment funnel | `power_null_calibration.json`, `activation_funnel.json`; learned labels + Mode 4 + engine |
| TE03.8 | Quyết định giữ design/mở revision nhỏ/dừng vì thiếu support | `model_decision.json`; causal rationale, budget và stop condition; E/NEIGH giữ secondary |

**Điểm bắt buộc:** nhãn `state_id=0/1/2` là ký hiệu của model version, không có chân lý phổ quát rằng
0=bull và 1=bear. Ý nghĩa economic descriptors được đặt từ train/history sẵn có; mô tả future outcomes
riêng để kiểm chứng, không dùng để đặt tên/lựa chọn policy cho chính khoảng đã đo.

Model không cần dự báo giá tuyệt đối tốt để có timing value; nó cần bổ sung thông tin cho **quyết định
đang thử**. Ngược lại, cluster separation tốt hoặc market-return rank correlation dương chưa chứng minh
bộ tham số nào nên được thay lúc nào. Chi tiết ở [model evaluation](#regime-evaluation).

**Báo cáo TE-03:** bắt buộc đánh giá từng model vintage/fold với mean/dispersion/support và uncertainty
ở mục tiêu kinh tế; chỉ ra design được deployed thực. Có synthetic labels accuracy thì ghi chỉ thuộc world
có ground truth. Không yêu cầu “model phải có edge” để báo cáo đúng trạng thái.

**Exit:** model/controller technical pass; full-path positive control đủ sức phát hiện effect đã biết;
null calibration hợp lệ; information/opportunity được đánh giá hoặc ghi insufficient support. Market
result chưa positive không chặn technical closure, nhưng phải chi phối quyết định có đáng mở rộng TE-04.

<a id="te-04"></a>
### TE-04 — Controlled discovery và đo time edge/decay

**Guide:** [G3 RF-04][g3-rf04], [§2][g3-2], [§6][g3-6], [§8][g3-8];
[G2 §10][g2-10], [§11][g2-11]. **Findings:** TEF-01–04/09/17/18/19.
**Tests:** TG-07/08/09. Chỉ bắt đầu sau TE-02/03 gates.

| Task | Việc cần làm | Output/gate |
|---|---|---|
| TE04.1 | Pilot subset theo rule đã đăng ký, đủ warmup/coverage/parameter opportunity; cùng dates/economics | Per-cell paired accounts, all planned statuses, source/design identity |
| TE04.2 | M4_CAL, M4_REGIME và budget-aware control; thêm placebo/delay/risk theo hypotheses | Control fidelity, actual compute/exposure/refits; không drop control vì thắng |
| TE04.3 | Full Mode 4 transparency ở từng cutoff | Temporal components, cluster/plateau/fallback, unique behavioral candidates, admissibility denominators |
| TE04.4 | Chuẩn hóa daily return/Sharpe/PF/DD, positions/costs và terminal effects | Raw/canonical side by side; first-return/partition/missing-date tests |
| TE04.5 | D1/D2/D3 và **so sánh decay giữa methods** theo design dưới đây | Per-fold bảng đầy đủ, contrast/effect/CI/support; không chỉ số rows |
| TE04.6 | Dependence-aware paired inference và multiplicity | Estimand, weights/active-cell count/date mask, bootstrap draws/seed, δ, corrected significance |
| TE04.7 | Model metrics nối với mỗi fold/account, attribution funnel và bottleneck | Model information vs opportunity vs activation vs costs, evidence cho từng nhận định |
| TE04.8 | Scale theo shards khi technical/support/budget gates đủ; giữ mọi kết quả | Đủ 20 status rows; performance profile và resume manifest; không chỉ winners |
| TE04.9 | Khóa một design hoặc ghi no-promising/insufficient design | `design_freeze.json`, exposed-data ledger, plan next action có giới hạn |

**Không được trì hoãn mọi metric đến sau full run.** Sau mỗi cặp hoàn chỉnh có thể sinh descriptive
report từ artifact đã đóng; statistical looks và stopping rule phải đăng ký. Nếu theo dõi liên tục để
dừng khi p đẹp thì cần sequential inference design riêng. Technical/budget stop không là hiệu quả âm.

**Báo cáo TE-04:** kết quả tổng và từng cell; per-fold model/decay; primary effect/CI/MDE; đủ controls;
cost/latency/risk; bad/failed/no-trade/unknown counts; full cohort coverage. Không có effect hợp lệ phải
ghi NOT_EVALUABLE/INCONCLUSIVE đúng nguyên nhân, không nhét một “quality score” che blockers.

**Exit:** effect và decay được tính bằng đúng contracts, có statistical capability và scoped conclusion;
design đã freeze hoặc có decision dừng hợp lý. Không bắt hiệu ứng phải dương.

<a id="te-05"></a>
### TE-05 — Frozen evaluation, claims và báo cáo hợp nhất

**Guide:** [G3 RF-05][g3-rf05], [§10][g3-10], [§12][g3-12];
[G2 LAB-09/10 trong §12][g2-12], [§13.6][g2-13.6]. **Tests:** TG-07/08/09/11/12.

| Task | Việc cần làm | Output/gate |
|---|---|---|
| TE05.1 | Pin code/alpha/model/scorer/policy/economics/seeds/budgets/metrics/thresholds | Immutable freeze manifest, no circular hash, full contamination audit |
| TE05.2 | Xác định data role thực và execution eligibility | Nếu không có untouched/post-freeze data: chỉ retrospective technical closure + prospective spec |
| TE05.3 | Chạy frozen evaluation nếu prerequisites và ngân sách đã có; rerun đúng affected chain | Same-engine selected audit parity, stress scopes; không rescale old curves thay fee-sensitive search |
| TE05.4 | Recompute paired timing + registered decay + model/funnel tables từ saved evidence | Independent reconstruction trong tolerance; no engine call để format/chart/bootstrap |
| TE05.5 | Apply validity/fidelity/support/inference/risk gates | Claim per cell/aggregate/hypothesis; caveat missing coverage/funding/data role |
| TE05.6 | Publish nội bộ bundle và central index | `report.md/json`, chart data, reproducibility manifest, scoped patch proposals; no production merge |

**Báo cáo TE-05 phải trả lời trực tiếp:**

1. Trên scope nào, thí nghiệm thực sự hợp lệ?
2. Model regime nào được dùng, nhãn có đặc tính gì, có information value cho parameter decision không?
3. Timing return gain bao nhiêu, có vượt δ và controls không?
4. D1/D2/D3 có kết quả gì; loại decay nào regime tốt hơn, với effect/CI/support nào?
5. Nếu chưa chứng minh được: do technical error, sample/power, model information, parameter opportunity,
   policy activation, costs hay economic effect nhỏ? Evidence nào phân biệt các lý do đó?
6. Nghiên cứu tiếp nào có hypothesis/budget/stop condition cụ thể? Phần nào nên dừng?

**Exit:** scoped technical + statistical + economic verdict, reproducibility và all required reports;
PARTIAL/BLOCKED không đổi thành COMPLETE. Prospective có thể `SPECIFIED_NOT_EXECUTED` và việc này phải
hiện ngay trong central index; không được tính như đã xác nhận live edge.

<a id="regime-evaluation"></a>
## 7. Hợp đồng đánh giá model regime — ở mọi phase có dùng model

### 7.1 Model dossier bắt buộc

Mỗi report có một mục “Regime model used and evaluated”. Phase chỉ dùng artifact cũ phải ghi
`INHERITED_FROZEN_INPUT`, phase chưa dùng model ghi `NOT_EVALUATED_IN_THIS_PHASE` với lý do.
Không tạo thêm fit chỉ để lấp report; thông tin tái sử dụng phải có reference/hash và data role đúng.

| Nhóm | Fields/metrics bắt buộc | Cách diễn giải |
|---|---|---|
| Identity | model_id/version, symbol/context universe, feature/scaler hashes, K/lambda/weights/seeds | Actual deployed model; so khớp design selection |
| Time/coverage | train_start/end, input available_at, fit-ready replay, inference times, score window, gaps | Không dùng wall time hiện tại thay causality clock |
| State meaning | namespace/state/common-state, raw feature centroid/profile, train-only descriptive name | Không coi cùng ID ở hai refits là cùng trạng thái |
| Statistical structure | occupancy counts, dwell distribution, transition matrix/rate, recurrence episodes | Nêu denominators và intervals có overlap |
| Fit quality | held-out objective/fit residual, dead/empty states, feature contribution, convergence/seed variability | Reconstruction chỉ descriptive, không kinh tế |
| Stability/availability | suffix invariance, ID permutation, mapping matched/ambiguous/unmatched, unknown/stale ratios, detection delay | Phân biệt model transition với market transition |
| Information value | future paired candidate utility/rank prediction so M0/no-regime, effect/CI, calibration/support | Target phải là quyết định đang thử; không chỉ direction forecast |
| Deployment impact | valid emissions → triggers → searches → params khác → ready → activate → orders khác → net benefit | Đếm từ ledger, không suy từ total fill count đơn lẻ |

Regime memberships là scores trừ khi đã có calibration thích hợp; không viết “90% bull” từ softmax
cost. Với labels không giám sát, không báo “accuracy của nhãn” trên market nếu không có độc lập ground truth.

### 7.2 Thử nghiệm thông tin phải nối được tới tham số

- Candidate set theo đúng cutoff/causal discovery; không lấy winners cả sample làm bank quá khứ.
- Với mỗi candidate, đo hành vi (signal/position/turnover/campaign) và utility cùng account/economic
  convention. Hai vector khác số nhưng cùng hành vi không tăng opportunity thật.
- Tạo future utility labels sau khi outcomes hoàn tất; chỉ các labels đã available mới đi vào fitting.
- So regime-conditional ranking/utility với unconditional/M0 và controls đã đăng ký. Không dùng loss
  giải thích features làm thước đo duy nhất cho parameter information.
- State × candidate × episode phải có support counts, uncertainty, recurrence và khoảng không đánh giá
  được. Shrink/fallback không được biến missing support thành zero gain đã đo.
- Hindsight best-param/segment chỉ là opportunity diagnostic: có thể cho biết có khoảng để khai thác,
  không phải executable profit curve hoặc lợi thế đã chứng minh.

### 7.3 Mỗi fold phải nối tới model nào

Một operational fold có thể đi qua nhiều model vintages vì model-retrain clock khác parameter-refresh.
Report cần cả model tại selection và toàn model versions trong khoảng operational. Không gán nguyên
fold cho một label tại ngày đầu, không gộp namespace transitions vào regime transitions.

Per-fold dossier gồm: `selection_id`, `model_id_at_selection`, `model_ids_during_window`, state/quality
counts, source masks, parameter age, trigger reason, known-at timestamps, parameter digest thực active,
orders/positions/costs. Bảng này join tới [metrics/decay](#statistical-design) bằng IDs, không join theo số thứ tự fold giữa hai arms.

<a id="statistical-design"></a>
## 8. Thiết kế thống kê và decay

### 8.1 Estimands và hypotheses cần khóa ở TE-01

| Hypothesis | Contrast/đại lượng | Loại kết luận |
|---|---|---|
| H-TIMING | Mean daily account net return của M4_REGIME − M4_CAL trên cùng lịch đánh giá | Primary timing value trong scope |
| H-BUDGET | M4_REGIME − M4_CAL_MATCHED với policy compute/cadence live-feasible đã đăng ký | Có tách được information timing khỏi thêm compute không? |
| H-DECAY | Một contrast decay chính được chọn trước, ví dụ chênh lệch age degradation của mean daily return H1→H3 | Có giảm decay theo definition đó không? |
| H-MODEL-INFO | Incremental prediction/decision utility của regime so unconditional/M0 trên future paired candidate outcome | Model có thông tin liên quan không? |
| H-RISK/controls | Risk-only, delay, placebo và constraint tests theo hypothesis/budget | Attribution/sensitivity; chưa mặc định là thêm primary family |

H-DECAY/H-MODEL-INFO là phần phải **đăng ký trong study mới**, không thêm hậu nghiệm vào family RF-05.
TE-01 chốt primary/secondary/gatekeeping family, threshold δ cho từng endpoint và error control.
Không lấy p-value so 0 thay chứng minh vượt δ. Không chọn metric/H2 hay H3 sau khi thấy bên nào đẹp.

Đối với net benefit, δ phải cùng **account bps/day** (1 bp = 0,01%) và economics thực. Giữ MDE lịch sử
như lịch sử; chỉ kế thừa nếu derivation còn đúng với contract mới. Cần risk constraints ngoài mean return.

### 8.2 Returns, sampling, uncertainty và support

- Daily net return: `r_d = E_d / E_previous_mark − 1`; first study observation dùng initial capital trước
  fee/fill. Giữ flat days trong evaluation scope, bỏ warmup ngoài scope. Missing market day không tự fill zero.
- Daily Sharpe: `sqrt(365) × mean(r−rf)/std(r−rf, ddof=1)` với frozen rf; không chuyển sampling âm thầm,
  không average per-fold Sharpe thành whole-account Sharpe. Ít observations/zero variance có status.
- PF observations và trade PF tách tên, nguồn, sampling và denominator; trade PF chỉ từ engine/reducer
  đã qualify về partial closes/campaign fees/funding. Zero-loss/zero-trade/only-loss khác nhau.
- Bootstrap paired theo **calendar blocks**; giữ cùng resampled timestamps cho cả arms/symbols khi đo
  common-market aggregate. Block length chọn từ development/dependence diagnostics, có sensitivity đã đăng ký.
- Report số ngày, non-flat days, trades/campaigns, distinct selections, episodes, overlap và effective support.
  Nhiều 1m bars hay nhiều TPE seeds không tạo thêm independent market histories.
- Cross-cell weights và missing/listing policy khóa trước: nếu row-wise mean làm số cells đổi theo ngày,
  report active-cell count và capital policy; không gọi constant-weight portfolio nếu vốn đang được tái phân bổ ngầm.
- Statistical test cần null calibration và power để phát hiện effect δ, với uncertainty của chính tỷ lệ
  false positives/power. Monte Carlo repetitions/precision đăng ký trước; dùng paths ngắn đủ cơ chế, không full history mỗi repetition.
- Negative/zero results không bị loại. Identical paths cần evidence về implementation/action, không suy
  failure chỉ từ equality; valid policy không action có thể là outcome thật nhưng không loại toàn bộ market information.

### 8.3 D1 — IS → first OOS của cùng bộ tham số

Đo raw IS/OOS Sharpe, mean daily net return và PF theo same definition/economics; gap additive.
IS selection bias phải được ghi rõ. Giữ `candidate_decay_quantbt` và penalties ở cột riêng.

Nếu params mới chưa active vì incumbent đang có campaign/latency, **operational fold PnL không phải
fixed-selected-param OOS**. Tách hai bảng:

1. Diagnostic evaluation cùng frozen θ trong IS/OOS với initial-state/warmup policy kiểm được.
2. Actual carried-account attribution theo `effective_parameter_version`, trong đó costs/old incumbent
   thuộc đúng version thực sự active. Không gán returns trong thời gian chờ cho challenger chưa dùng.

Return của train 180 ngày trừ total return OOS 90 ngày không có cùng horizon; dùng normalized daily
utility hoặc fixed horizon đã khóa. PF log-gap chỉ dùng khi denominator/support hợp lệ.

### 8.4 D2 — Hiệu quả theo tuổi của cùng θ

- Chọn anchors trước outcomes theo rule coverage/holding support; danh sách và ngân sách lưu trước run.
  Không chỉ chọn fold-0 mãi nếu kết luận nhắm tới mọi selected fold; nếu subset, ghi coverage và lý do.
- Với mỗi θ, giữ θ cố định và replay chronology thật trên H1/H2/H3 half-open. Warmup ở ngoài scoring;
  giữ independent diagnostic account policy nhất quán, không ghép nó vào operational PnL.
- Mốc tuổi phải rõ: từ selection-ready hay actual activation; nên xuất cả hai với primary definition
  khóa trước. Latency/campaign wait không biến thành tuổi-param performance mà không disclosure.
- Với utility μ, `D_age,j = μ(H1) − μ(Hj)`; giá trị lớn hơn là degradation nhiều hơn theo definition.
  Với PF dương/hữu hạn, dùng `log(PF_H1) − log(PF_Hj)`; SR dùng additive gap.
- H1−H1 giữ làm reference, không tính một phép thử độc lập. Cùng daily boundary chỉ xuất hiện một lần.

**So regime với calendar:** đối chiếu `D_CAL − D_REGIME` trên matched calendar/age cohorts đã đăng ký;
dương nghĩa regime có degradation nhỏ hơn theo metric ấy. Selection dates khác nhau tạo market-context
confounding: phải dùng common-date design/stratification/control và uncertainty phù hợp, hoặc chỉ gọi
association diagnostic. Không pair “fold 3” hai arms như cùng thời gian.

CI phải giữ dependence giữa anchors/windows overlap và common shocks. Không iid bootstrap từng row
decay hoặc lấy percentile của per-fold Sharpes như CI của whole study. H-DECAY cần effect, CI, δ_decay,
support và kiểm multiplicity; nếu thiếu dữ liệu để đánh giá thì ghi INCONCLUSIVE/NOT_EVALUABLE.

### 8.5 D3 — Thay đổi giữa operational folds

Xuất metric từng fold, độ dài, params/versions, model vintages, state composition, exposure, returns,
drawdown, fees và support. `M(fold_next) − M(fold_prev)` là thay đổi quan sát khi **cả params và market
có thể đổi**; không gọi pure parameter decay. Các so sánh chính vẫn trên common daily/monthly windows.

### 8.6 Bảng kết quả bắt buộc

| Bảng | Fields tối thiểu |
|---|---|
| `model_fold_metrics` | study/run/cell/arm/fold/model IDs; train/ready/score times; K/lambda/feature hash; label profiles; occupancy/dwell/transitions/unknown; information target/effect/CI/support |
| `operational_fold_metrics` | cutoff/selection/ready/activation; intended/actual θ; date bounds; capital/fees/funding/positions; raw/canonical return/SR/PF/DD; counts/null reasons |
| `decay_panel` | selection/θ/model IDs; D1/D2/D3; same-parameter flag; left/right windows; metric definition/unit/raw-penalized; values/gap/support; route/fidelity; diagnostic flag |
| `method_decay_contrasts` | registered contrast; comparable date/age cohorts; CAL/REG values; paired effect/CI/δ; dependence/multiplicity; missing/blocked denominator |
| `paired_primary_results` | common dates and weights; effect/CI/MDE; bootstrap/resampling config; adjusted inference; risk gates; scoped verdict |
| `activation_funnel` | input quality → eligible transition → requested → searched → selected → different behavior → ready → activated → orders → economic result, mỗi bước có reasons |

<a id="report-contract"></a>
## 9. Báo cáo bắt buộc ở mọi phase

Report là output của writer đọc artifacts đã đóng, không chạy optimizer để sinh số hoặc format.
Mỗi phase có **Markdown + JSON** cùng source references. Những fields không áp dụng ghi status và reason,
không điền 0. Báo cáo cũ không sửa tay để khớp kết luận mới.

### 9.1 Mười ba phần của phase report

1. Objective/hypotheses và những gì phase không test.
2. Guide/task/test IDs, source/data/alpha/model/economic identity; requested/resolved engine.
3. Findings được sửa; failing-before/passing-after; source/hash/caller và affected scope.
4. Planned vs actual work: cells/folds/trials/seeds/bars/episodes, coverage, warmup, failures.
5. Kết quả tách unit/source probe/synthetic/real market; không cộng chúng thành một số “pass”.
6. **Regime model dossier**: model dùng thật, label meaning/quality/information/support và liên kết từng fold.
7. Raw/canonical account metrics và **D1/D2/D3 + method contrasts**, hoặc NOT_EVALUATED với task sở hữu.
8. Statistical design/estimand/CI/MDE/multiplicity/power/null; constraints và error modes.
9. Runtime/profile: actual CPU/wall/RSS/work counts, cached vs executed, stop/resume budgets.
10. Proof capability và bottleneck có evidence: opportunity/information/activation/cost/sample/validity.
11. Verdict, remaining blockers, review disagreements; technical/statistical/economic/deployment tách riêng.
12. Rerun/render commands, hashes, chart-source refs, handoff task và central index update.
13. **Khuyến nghị bước tiếp theo theo kế hoạch chung:** ưu tiên task nào, vì sao từ evidence vừa có,
    điều kiện bắt đầu, phạm vi reuse/rerun và tiêu chí nghiệm thu; theo §9.4 bên dưới.

Mỗi report kèm glossary định nghĩa metric, đơn vị và denominator đang dùng. Tối thiểu:
**IS/OOS** = khoảng dùng chọn tham số/khoảng đánh giá về sau; **WFO** = tối ưu và đánh giá cuốn chiếu;
**θ** = một bộ tham số; **CI** = khoảng tin cậy theo phương pháp đã đăng ký;
**PF** = tổng phần lãi chia tổng độ lớn phần lỗ trên sampling đã nêu;
**δ kinh tế** = mức cải thiện nhỏ nhất đáng quan tâm theo chi phí/quy mô vốn.
Tên field MDE lịch sử của lab được giữ để truy nguồn, nhưng không đánh đồng δ kinh tế với
**minimum detectable effect thống kê**: mức hiệu ứng phép thử có thể phát hiện tại alpha, power
và cỡ mẫu/dependence đã đăng ký. Report phải cho biết sample hiện có đủ độ nhạy cho δ hay chưa,
không tính “observed power” từ chính point estimate rồi dùng nó xác nhận kết luận.

### 9.2 Máy đọc và chart data

Schema đích đề xuất, chưa là report đã đạt:

```json
{
  "phase_id": "TE-03",
  "status": "NOT_STARTED",
  "task_ids": [],
  "guide_refs": [],
  "source_manifest_ref": null,
  "data_role": null,
  "tests": {"unit": null, "source_probe": null, "engine": null, "statistical": null},
  "regime_model": {"status": "NOT_EVALUATED", "deployed_registry_ref": null, "fold_metrics_ref": null},
  "metrics": {"raw_ref": null, "canonical_ref": null, "decay_ref": null, "method_contrasts_ref": null},
  "coverage": {"planned": null, "completed": null, "blocked": null, "reasons": []},
  "claim": {"validity": "NOT_TESTED", "statistical": "NOT_EVALUABLE", "economic": "NOT_EVALUATED"},
  "remaining_findings": [],
  "next_actions": [],
  "runtime_ref": null,
  "reproduction_ref": null
}
```

Các validator phải từ chối COMPLETE khi required refs/measurements còn null. Schema production cần
bao gồm fields ở §9.1 và có versions; example trên chỉ phác thảo nhóm chính.

Charts cần có dữ liệu tái tạo bằng `.py`: daily equity/drawdown, activation trên regime/ready timeline,
label occupancy/transition/stability, raw vs penalized IS/OOS, age-decay curves kèm support/CI,
per-cell paired effects, funnel và cost profile. Không tô màu nhãn trên giá rồi gọi là edge evidence.

### 9.3 Review record để đóng task

| task_id | status | implementation commit | before/after test evidence | measured result ref | guide/test IDs | reviewer finding | remaining |
|---|---|---|---|---|---|---|---|
| TE01.1 / TE01.2 preparation | IN_PROGRESS | `8882df8` | Chưa chạy regression tests; đã kiểm schema/hash và lint runner | [Preparation report](evidence/time_edge_validation_v4/TE-01/prep-20260912-01/report.md) | G3 RF-01; TG-01 | Toàn bộ TEF vẫn OPEN | Final FUP intake, full A/D/N mapping, contracts và before-repair cases |

Vocabulary tracking: NOT_STARTED / IN_PROGRESS / BLOCKED_WITH_REASON / IMPLEMENTED_PENDING_TEST /
VERIFIED_WITHIN_SCOPE / PARTIAL / CLOSED. `CLOSED` cần đủ deliverables, không chỉ file presence.
Review này không tự gọi “independent statistical validation” vì là cùng một người rà source/evidence.

### 9.4 Khuyến nghị sau mỗi phase — yêu cầu của người dùng

Mỗi lần báo cáo kết thúc hoặc tạm chốt một phase, cả báo cáo MD/JSON và câu trả lời cho người dùng
phải có khuyến nghị cụ thể. Áp dụng cả khi phase PARTIAL/BLOCKED, và sau phase cuối nếu nên dừng
nghiên cứu trong phạm vi đã kiểm. Báo cáo đã commit giữ nguyên; cập nhật bằng record/báo cáo mới.

- Chốt trạng thái phase, phần đạt/chưa đạt và kết luận được phép rút ra từ evidence.
- Nêu 1–3 việc ưu tiên kế tiếp với phase/task ID và link đến mục tương ứng trong plan/guide.
- Giải thích mỗi việc giải quyết blocker hoặc câu hỏi nào; phân biệt việc có thể làm ngay và việc
  phải chờ dependency thật. Không tự coi dependency chưa có evidence là đã hoàn tất.
- Nêu đầu ra và phép kiểm để nghiệm thu; chỉ rõ phần tái sử dụng và phần cần chạy lại. Runtime/budget
  dự kiến phải dựa trên profile đã đo; chưa có profile ghi `NOT_PROFILED`, không hứa thời lượng.
- Ghi khuyến nghị trong `next_actions` của report JSON: `priority`, `phase_id`, `task_id`, `plan_ref`,
  `guide_refs`, `reason_evidence_refs`, `readiness`, `dependencies`, `expected_outputs`,
  `acceptance_checks`, `reuse_scope`, `budget_ref`. Kết quả âm/chưa rõ có thể dẫn tới khuyến nghị dừng,
  thu hẹp claim hoặc sửa phép thử theo registration, không mặc định mở thêm grid để tìm số dương.

**Khuyến nghị hiện tại sau TE-01, đã sửa sau rà soát chi phí:** đề nghị ngừng mở thêm FUP shard/resume
ở checkpoint an toàn, giữ kết quả PARTIAL và bàn giao; đề nghị này chưa được thực hiện trên process.
[TE01.1](#te-01) tiếp nhận source/evidence cuối khi có; **không cần chờ việc này mới triển khai TE-02 độc lập**.
Bước triển khai tiếp theo ưu tiên [TE02.1 rồi TE02.2](#te-02):
đúng route/clock/lifecycle từng alpha trước, rồi kiểm scorer và public Mode 4 trên cùng cutoff.
Trong lúc chờ FUP có thể sửa và kiểm fixtures/adapters trên bản sao lab riêng; không sửa source mà
FUP đang dùng. Engine pilots cần chứng minh module import từ đúng bản sao, OS isolation và budget đã đăng ký. Nghiệm thu
bằng actual fills/fees/activation traces và selected-params/objective parity; sau đó mới mở rộng
TE02.3–TE02.8, rồi [TE-03](#te-03) model/controls và [TE-04](#te-04) time-edge/decay inference.

<a id="test-groups"></a>
## 10. Nhóm phép thử và tiêu chí có thể thất bại

Các tên test mới bên dưới là **đề xuất**, chưa phải file/hàm đã tồn tại. Tests hiện có giữ nguyên và
được mở rộng khi thực hiện; không nới assertion hoặc tolerance để làm gate xanh.

<a id="tg-01"></a>
### TG-01 — Scope, data, provenance, registration

Hash drift/late data/wrong symbol/ms-vs-ns/missing partitions/protected writes; prereg timestamps;
evaluation role/first mark. Source inventory không là operational data audit. Map tới tests safety/data
hiện có và thêm `test_registered_eval_mask_excludes_warmup` cùng per-symbol coverage witnesses.

<a id="tg-02"></a>
### TG-02 — Alpha và execution economics

Golden flat-price fees, gap next-open/next-close, 1m/coarse divergence, HMA categories, VWAP amendment,
HASH ladder, SC long-flat, partial/reject/cancel/staging, tick/lot/min-notional. Test actual QuantBT public
endpoint với real command/fill trace; mỗi supported route cần witness và fail case.

<a id="tg-03"></a>
### TG-03 — Mode 4 và candidate scorer

Fixed-calendar provider/public selector parity; scorer per-window metric/penalty/support equivalence;
fee-sensitive selected params; no future prices/segment end/outer outcomes; failed/pruned trials retained.
`test_subperiod_support_uses_subperiod_fills`, `test_scoring_warmup_is_outside_score` là proposed guards.

<a id="tg-04"></a>
### TG-04 — Four clocks và actual activation

Initial incumbent ready, model/selection/indicator ready, latency/out-of-order jobs, common initial
exposure, no-change/max-age, campaign carry, parameter version active before first affected order,
single warmup và proper shadow state. Đếm no-op/multi-activation ở cùng bar và test coalesce policy.

<a id="tg-05"></a>
### TG-05 — Causality và label identity của model

Full runner suffix mutation trên raw inputs; inner scaler/outcome profile; missing-ready rejects;
namespace/label permutation; one-to-one common-coordinate mapping; unknown/dead/stale policy;
warm filter state; selected-vs-deployed design equality. Không chỉ test helper rồi đọc tape cũ ở market run.

<a id="tg-06"></a>
### TG-06 — Parameter opportunity và regime information

Same-cohort/fixed target ablation, outcome-end embargo/purge; conditional ranking vs unconditional/M0;
behaviorally equivalent parameters; role of common BTC context; episode/support/recurrence; outcome
suffix mutation thay chưa-available labels không đổi fitted profile. Null/known informative context controls.

<a id="tg-07"></a>
### TG-07 — Statistical arithmetic và calibrated inference

Daily first fee, warmup invariance, exact day counts, shared shocks, missing-cell capital policy,
known constant/zero/nonzero effects, overlap/autocorrelation, bootstrap CI coverage, null rejection rate,
power quanh registered δ, multiplicity/hierarchical tests. Financial assumptions giữ nguyên giữa samples;
bootstrap saved paths không chạy optimizer mỗi draw.

<a id="tg-08"></a>
### TG-08 — Decay D1/D2/D3

Non-overlap boundaries/telescoping, same θ/effective version, same metric units/raw-penalized,
PF key/edge cases/log-gap, negative IS/near-zero levels, diagnostic-vs-operational separation,
route fidelity, H1−H1 excluded from inferential denominator, matching dates/age windows, uncertainty
với overlapping anchors. Controlled-world stable/decaying parameter cases phải trả đúng dấu/mức gap.

<a id="tg-09"></a>
### TG-09 — Full positive/null và controls

Giữ execution plumbing control cũ đúng scope. Full pipeline learns states từ observable features và
Mode 4 chọn params từ training; world truth dùng để chấm cuối, không vào policy. Register world
seeds/replicates/effect levels/Monte Carlo precision. Null không bắt false positives bằng 0 tuyệt đối;
report interval của tỷ lệ rejection. Placebo/delay/matched-calendar/risk-only giữ ngay cả khi thắng treatment.

<a id="tg-10"></a>
### TG-10 — Resource, cache và resume

Budget remainder tích lũy, failed work accounting, source/params/tape/schema/route hash changes,
mid-fold crash, no duplicate/missing trials, deterministic restart, cache mutable state isolation,
timeout khác tài chính. Test orchestration bằng synthetic fake-work counts; engine parity trên pilot nhỏ.

<a id="tg-11"></a>
### TG-11 — Evidence/report/claims

Malformed JSON, required flush failures, stale rollups, immutable root hashes, missing joins/8-row
truncation, fills-vs-trades/exposure alias, numbers absent from Markdown, wrong model ref, incomplete
coverage. Inject each material blocker → affected claim không được positive/negative beyond scope.

<a id="tg-12"></a>
### TG-12 — Secondary và historical quarantine

CLI/canonical runner từ chối historical invalid inference, E alias, unsupported alpha/route. E/NEIGH
chỉ enabled khi có own protocol/positive integration/support; không đưa old E=D null vào kết luận mới.

<a id="guide-requirements"></a>
## 11. Traceability của toàn bộ yêu cầu acceptance trong hai guide

Khối sau sinh từ hai registry hiện có. Link tới test cũ là điểm bắt đầu đọc, không certificate;
guide link mang toàn expected behavior; nhóm TG và phase phải thêm runtime tests thiếu khi triển khai.

<!-- BEGIN GUIDE_REQUIREMENTS -->

Mỗi ID dưới đây là **nghĩa vụ**, chưa là test đã pass trong review. `V2:T01` và `V3:T01` khác nhau.
Trạng thái COVERED cũ được giữ như khai báo lịch sử; nghiệm thu kế hoạch này cần evidence mới và test chạy đúng đường code.

| ID gốc | Nội dung / tên trong registry | Phase chịu trách nhiệm | Test/index hiện có hoặc nhóm cần bổ sung |
|---|---|---|---|
| [V2:T01][g2-14] | LAB_ROOT inside protected repo -> preflight reject | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t01_lab_root_outside_protected_roots](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T02][g2-14] | Symlink/hardlink editable copy pointing at source | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t02_write_target_escaping_lab_is_refused](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T03][g2-14] | ZIP path traversal/symlink/duplicate | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t03_hostile_zip_rejected_before_extraction](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T04][g2-14] | Archive hash or 4-file allowlist changed | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t04_four_alpha_digests_match_guide](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T05][g2-14] | Import writes cache to protected path (sandbox fixture) | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t05_worker_caches_resolve_inside_lab](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T06][g2-14] | Network/live credentials in replay worker | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t06_credentials_stripped_from_worker_env](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T07][g2-14] | Memory/process/cancel over budget | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t07_cancel_refuses_foreign_process_group](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T08][g2-14] | Source hash before/after | [TE-01](#te-01) | [tests/test_lab01_safety.py::test_t08_protected_sources_unchanged_since_bootstrap](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T09][g2-14] | HASH standalone missing numpy | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t09_raw_hash_cannot_run_without_numpy](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T10][g2-14] | HASH short arrays and ATR convention | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t10_raw_hash_indexes_past_the_end_on_short_input](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T11][g2-14] | HASH multiple TP crossed same bar | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t11_raw_source_fills_only_one_rung_on_a_bar_that_crosses_all](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T12][g2-14] | HASH TP2 remaining fraction and lot rounding | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t12_tp2_is_a_fraction_of_the_remaining_quantity](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T13][g2-14] | HMA open != previous close | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t13_levels_move_when_the_open_gaps_away_from_the_close](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T14][g2-14] | HMA invalid min/max, unused knobs | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t14_inverted_lengths_are_rejected_not_swapped](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T15][g2-14] | HMA RSI flat, warmup/padding | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t15_rsi_flat_repair_and_legacy_are_both_available](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T16][g2-14] | VWAP dynamic threshold not yet available | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t16_dynamic_vwap_exit_is_off_by_default_and_lagged_when_enabled](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T17][g2-14] | VWAP UTC day, HTF close and missing bucket | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t17_utc_day_reset_and_htf_availability](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T18][g2-14] | VWAP simultaneous time/SL/TP | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t18_exit_precedence_is_frozen_and_identical_for_every_arm](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T19][g2-14] | SC missing volume/RSI fallback | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t19_missing_volume_is_an_explicit_rejection](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T20][g2-14] | SC long-flat/amplitude/crossover | [TE-02](#te-02) | [tests/test_lab02_alphas.py::test_t20_position_is_long_flat_and_never_short](tests/test_lab02_alphas.py); khai báo cũ `COVERED` |
| [V2:T21][g2-14] | Fractional crypto volume | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t21_volume_stays_fractional_through_resampling](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T22][g2-14] | ms/ns and open/close labels | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t22_bar_close_is_derived_not_read_from_close_time](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T23][g2-14] | Same-length symbols, offset timestamps | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t23_symbol_column_must_match_the_request](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T24][g2-14] | Symbol before listing | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t24_no_bars_are_fabricated_before_listing](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T25][g2-14] | Changed future raw data/preprocessing | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t25_trailing_features_are_causal](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T26][g2-14] | Snapshot sample_time at end of hour | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t26_book_snapshot_uses_sample_time_not_the_hour_label](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T27][g2-14] | Market universe and source revision | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t27_vintage_id_combines_source_and_ingest](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T28][g2-14] | Enrichment missing/stale | [TE-01](#te-01) | [tests/test_lab03_data.py::test_t28_enrichment_is_inventoried_but_not_acquired](tests/test_lab03_data.py); khai báo cũ `COVERED` |
| [V2:T29][g2-14] | Sharp peak vs broad profitable neighborhood | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t29_broad_neighbourhood_beats_a_sharp_peak](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T30][g2-14] | Flat but negative region | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t30_flat_but_negative_fails_economic_quality](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T31][g2-14] | Fixed/inactive params/far sampled point | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t31_geometry_is_unchanged_by_a_far_sampled_point](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T32][g2-14] | Dependent parameter TP/length manifold | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t32_probes_on_a_dependent_manifold_are_feasible_and_unique](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T33][g2-14] | Centroid not yet evaluated | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t33_unevaluated_centroid_is_not_deployable](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T34][g2-14] | Medoid metric/tie-break | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t34_medoid_minimises_the_same_distance_the_selector_declares](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T35][g2-14] | Incumbent guard differs from robust objective | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t35_incumbent_guard_disagreement_is_visible](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T36][g2-14] | Full-set tuned presets into early bank | [TE-02](#te-02) | [tests/test_lab04_selector.py::test_t36_presets_are_barred_from_the_primary_bank](tests/test_lab04_selector.py); khai báo cũ `COVERED` |
| [V2:T37][g2-14] | Forward JM DP vs exhaustive tiny paths | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t37_endpoint_costs_equal_brute_force](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T38][g2-14] | Batch versus streaming regime emissions | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t38_streaming_equals_batch_at_every_prefix](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T39][g2-14] | Model/scaler fit with future suffix | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t39_a_causal_fit_is_bit_identical_under_a_mutated_future](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T40][g2-14] | Sparse weights collapse to 0/empty states | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t40_all_zero_weights_is_flagged_and_blocks_decisions](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T41][g2-14] | Model refit permutes state IDs | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t41_a_pure_permutation_maps_cleanly_and_is_not_a_market_event](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T42][g2-14] | Membership score called a probability | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t42_membership_sums_to_one_and_is_still_not_a_probability](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T43][g2-14] | Known regime change and model drift | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t43_the_inference_modules_cannot_call_a_fit](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T44][g2-14] | Novelty versus missing data | [TE-03](#te-03) | [tests/test_lab05_regime.py::test_t44_identical_residual_but_missing_inputs_gives_a_different_status](tests/test_lab05_regime.py); khai báo cũ `COVERED` |
| [V2:T45][g2-14] | Response outcome not yet complete | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t45_an_unfinished_outcome_is_unusable](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T46][g2-14] | Candidate discovered after inner cutoff | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t46_a_later_discovery_is_rejected_with_a_reason](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T47][g2-14] | Incumbent/challenger paired episodes | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t47_mismatched_episode_counts_are_refused](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T48][g2-14] | One episode dominates similarity | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t48_a_dominating_episode_is_flagged_and_shrunk](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T49][g2-14] | Refit latency/job out-of-order | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t49_activation_may_never_precede_ready](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T50][g2-14] | Params switch while campaign open | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t50_the_entry_digest_is_immutable](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T51][g2-14] | New parameter indicators not warm | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t51_an_unwarmed_candidate_waits_instead_of_switching](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T52][g2-14] | Model fit/bank refresh/switch counters | [TE-03](#te-03) | [tests/test_lab06_policy.py::test_t52_the_four_clocks_are_distinct](tests/test_lab06_policy.py); khai báo cũ `COVERED` |
| [V2:T53][g2-14] | A/B/C/D fixed economics and budgets | [TE-04](#te-04) | [tests/test_lab08_factorial.py::test_the_five_arms_differ_only_in_selector_and_timing](tests/test_lab08_factorial.py); khai báo cũ `COVERED` |
| [V2:T54][g2-14] | Current WFO uses OOS for selection | [TE-05](#te-05) | [tests/test_lab04_legacy_labelling.py::test_modes_declaring_oos_selection_are_named_and_labelled](tests/test_lab04_legacy_labelling.py); khai báo cũ `COVERED` |
| [V2:T55][g2-14] | Dynamic folds of different length | [TE-02](#te-02) | [tests/test_lab07_integration.py::test_the_daily_account_is_the_comparison_not_the_mean_of_segment_sharpes](tests/test_lab07_integration.py); khai báo cũ `COVERED` |
| [V2:T56][g2-14] | Carried account across segments | [TE-02](#te-02) | [tests/test_lab07_integration.py::test_the_continuous_account_never_resets_across_a_parameter_switch](tests/test_lab07_integration.py); khai báo cũ `COVERED` |
| [V2:T57][g2-14] | Sequential optimizer vs adaptive batch | [TE-02](#te-02) | [tests/test_lab07_integration.py::test_t57_the_sequencing_contract_is_declared](tests/test_lab07_integration.py); khai báo cũ `COVERED` |
| [V2:T58][g2-14] | Risk-only/matched-cadence controls | [TE-04](#te-04) | [tests/test_lab08_factorial.py::test_all_seven_mandatory_controls_are_declared](tests/test_lab08_factorial.py); khai báo cũ `COVERED` |
| [V2:T59][g2-14] | Negative/failed/pruned trials retained | [TE-04](#te-04) | [tests/test_lab08_factorial.py::test_an_unrunnable_arm_reports_null_not_zero](tests/test_lab08_factorial.py); khai báo cũ `COVERED` |
| [V2:T60][g2-14] | Objective recompute from components | [TE-04](#te-04) | [tests/test_lab08_factorial.py::test_a_contrast_is_taken_on_shared_dates_only](tests/test_lab08_factorial.py); khai báo cũ `COVERED` |
| [V2:T61][g2-14] | JSON NaN/Inf, audit queue/error | [TE-05](#te-05) | [tests/test_lab01_safety.py::test_t61_nan_and_inf_are_refused_by_the_writer](tests/test_lab01_safety.py); khai báo cũ `COVERED` |
| [V2:T62][g2-14] | Untested heatmap cells, hindsight labels | [TE-05](#te-05) | [tests/test_lab09_confirmation.py::test_no_untested_cell_is_presented_as_evidence](tests/test_lab09_confirmation.py); khai báo cũ `COVERED` |
| [V2:T63][g2-14] | Full 5-symbol paired bootstrap | [TE-05](#te-05) | [tests/test_lab09_uncertainty.py::test_symbols_are_resampled_together_so_common_shocks_survive](tests/test_lab09_uncertainty.py); khai báo cũ `COVERED` |
| [V2:T64][g2-14] | Offline reproduce report/run and sources | [TE-05](#te-05) | Chưa có test pointer trong registry; khai báo cũ `NOT_YET_IMPLEMENTED` |
| [V3:T01][g3-11] | Một buy và một sell có notional biết trước | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T02][g3-11] | Giá thay đổi khi đang giữ position với allocation bằng 10% | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T03][g3-11] | Initial candidate chỉ sẵn sàng sau account start | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T04][g3-11] | Selection cutoff trước fit-ready và indicator-ready | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T05][g3-11] | Sửa toàn future suffix sau T | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T06][g3-11] | Close-generated intent chạy trên next-open route | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T07][g3-11] | Prepared same-close route được đề nghị cho next-open alpha | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T08][g3-11] | HTF 15m/1h signal và execution 1m | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T09][g3-11] | Actual fill có slippage/reject/partial quantity | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T10][g3-11] | Nhiều fills cùng một bar, khác IDs/sequence/price | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T11][g3-11] | Cùng exit bar nhưng khác price/qty/reason | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T12][g3-11] | Unmapped intent hoặc execution invalid | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T13][g3-11] | Callback phát staged commands rồi raise | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T14][g3-11] | Một order business-rejected trong batch hợp lệ | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T15][g3-11] | HMA stop-mode categories | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T16][g3-11] | Thêm một ignored/fixed parameter | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T17][g3-11] | VWAP dynamic protection amendment | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T18][g3-11] | HMA entry gap làm bracket invalid | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T19][g3-11] | HASH ladder partial TP | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T20][g3-11] | SignalCombine source long-flat | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T21][g3-11] | Protective orders còn mở khi params đổi | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T22][g3-11] | Bắt đầu episode sau một warmup prefix | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T23][g3-11] | Symbol bị thiếu bars/khác calendar hoặc trước listing | [TE-01](#te-01) | [TG-01](#tg-01); cần map tới runtime test + evidence |
| [V3:T24][g3-11] | Spot/perp, tick/lot/funding coverage khác nhau | [TE-01](#te-01) | [TG-01](#tg-01); cần map tới runtime test + evidence |
| [V3:T25][g3-11] | Baseline public Mode 4 | [TE-02](#te-02) | [TG-03](#tg-03); cần map tới runtime test + evidence |
| [V3:T26][g3-11] | Tạo utility rồi gán trường `mean_is_sharpe` | [TE-02](#te-02) | [TG-03](#tg-03); cần map tới runtime test + evidence |
| [V3:T27][g3-11] | Thay outer OOS data/outcomes | [TE-02](#te-02) | [TG-03](#tg-03); cần map tới runtime test + evidence |
| [V3:T28][g3-11] | Dynamic fold provider nhận lịch cố định như baseline | [TE-02](#te-02) | [TG-03](#tg-03); cần map tới runtime test + evidence |
| [V3:T29][g3-11] | Cùng model state, đổi namespace hoặc permute IDs | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T30][g3-11] | Emission `decision_eligible=false`, missing/stale/unknown | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T31][g3-11] | Không có regime changes trong cả interval | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T32][g3-11] | Inference → trigger → search → ready → activation | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T33][g3-11] | So hai cutoffs có số trials/cache hits khác nhau | [TE-02](#te-02) | [TG-10](#tg-10); cần map tới runtime test + evidence |
| [V3:T34][g3-11] | Sequential TPE versus batch mode | [TE-02](#te-02) | [TG-10](#tg-10); cần map tới runtime test + evidence |
| [V3:T35][g3-11] | Candidate reuse cache | [TE-02](#te-02) | [TG-10](#tg-10); cần map tới runtime test + evidence |
| [V3:T36][g3-11] | Score cache ở một pruned/failed evaluation | [TE-02](#te-02) | [TG-10](#tg-10); cần map tới runtime test + evidence |
| [V3:T37][g3-11] | E path chưa nối response | [TE-03](#te-03) | [TG-12](#tg-12); cần map tới runtime test + evidence |
| [V3:T38][g3-11] | Synthetic recurring-state world có advantage đã biết | [TE-03 → TE-04](#te-03) | [TG-09](#tg-09); cần map tới runtime test + evidence |
| [V3:T39][g3-11] | Synthetic null world hoặc delayed/placebo state | [TE-03 → TE-04](#te-03) | [TG-09](#tg-09); cần map tới runtime test + evidence |
| [V3:T40][g3-11] | Toàn pipeline regime off | [TE-02](#te-02) | [TG-03](#tg-03); cần map tới runtime test + evidence |
| [V3:T41][g3-11] | Bull và bear đều sát centroid riêng | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T42][g3-11] | Refit scaler/model giữa versions | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T43][g3-11] | Inner fold preprocessing | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T44][g3-11] | Thêm data group nhưng target/coverage phải cố định | [TE-03](#te-03) | [TG-06](#tg-06); cần map tới runtime test + evidence |
| [V3:T45][g3-11] | Episode outcome kết thúc sau decision cutoff | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T46][g3-11] | Một đoạn liên tiếp chứa nhiều weighted episodes | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T47][g3-11] | Candidate bank chứa global anchor và specialists | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T48][g3-11] | Projected switching cost theo current account | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T49][g3-11] | Parameter recommendation không active do open campaign | [TE-02](#te-02) | [TG-04](#tg-04); cần map tới runtime test + evidence |
| [V3:T50][g3-11] | Model K/cadence được chọn từ development | [TE-03](#te-03) | [TG-05](#tg-05); cần map tới runtime test + evidence |
| [V3:T51][g3-11] | Loss đúng tại đầu block | [TE-04](#te-04) | [TG-07](#tg-07); cần map tới runtime test + evidence |
| [V3:T52][g3-11] | First fill/fee ở observation đầu | [TE-04](#te-04) | [TG-07](#tg-07); cần map tới runtime test + evidence |
| [V3:T53][g3-11] | Returns trên hai windows khác độ dài | [TE-04](#te-04) | [TG-07](#tg-07); cần map tới runtime test + evidence |
| [V3:T54][g3-11] | Profit Factor observations khác trade PF | [TE-04](#te-04) | [TG-07](#tg-07); cần map tới runtime test + evidence |
| [V3:T55][g3-11] | OOS metric trừ trade-frequency penalty | [TE-04](#te-04) | [TG-08](#tg-08); cần map tới runtime test + evidence |
| [V3:T56][g3-11] | Negative/near-zero IS Sharpe hoặc return | [TE-04](#te-04) | [TG-08](#tg-08); cần map tới runtime test + evidence |
| [V3:T57][g3-11] | Đổi params giữa hai folds | [TE-04](#te-04) | [TG-08](#tg-08); cần map tới runtime test + evidence |
| [V3:T58][g3-11] | Dynamic folds có length khác nhau | [TE-04](#te-04) | [TG-07](#tg-07); cần map tới runtime test + evidence |
| [V3:T59][g3-11] | Equity-fraction thay fixed notional | [TE-01](#te-01) | [TG-01](#tg-01); cần map tới runtime test + evidence |
| [V3:T60][g3-11] | P0 invalidity kèm CI trông rõ âm/dương | [TE-05](#te-05) | [TG-11](#tg-11); cần map tới runtime test + evidence |
| [V3:T61][g3-11] | Confidence interval chứa meaningful positive và zero | [TE-05](#te-05) | [TG-11](#tg-11); cần map tới runtime test + evidence |
| [V3:T62][g3-11] | Một số cells chưa sẵn sàng hoặc failed | [TE-05](#te-05) | [TG-11](#tg-11); cần map tới runtime test + evidence |
| [V3:T63][g3-11] | Audit duplicate/pruned/failed trials | [TE-02](#te-02) | [TG-10](#tg-10); cần map tới runtime test + evidence |
| [V3:T64][g3-11] | Sample estimates ghi 4.000 nhưng giữ 400 | [TE-01](#te-01) | [TG-01](#tg-01); cần map tới runtime test + evidence |
| [V3:T65][g3-11] | Required audit writer flush lỗi | [TE-05](#te-05) | [TG-11](#tg-11); cần map tới runtime test + evidence |
| [V3:T66][g3-11] | Cache enabled/disabled và retained views | [TE-02](#te-02) | [TG-10](#tg-10); cần map tới runtime test + evidence |
| [V3:T67][g3-11] | T0/T1 pilot vượt budget | [TE-02](#te-02) | [TG-10](#tg-10); cần map tới runtime test + evidence |
| [V3:T68][g3-11] | Native backend không có capability nhưng request require | [TE-02](#te-02) | [TG-02](#tg-02); cần map tới runtime test + evidence |
| [V3:T69][g3-11] | Rebuild report từ artifacts | [TE-05](#te-05) | [TG-11](#tg-11); cần map tới runtime test + evidence |
| [V3:T70][g3-11] | Khôi phục evidence từ Markdown này | [TE-01](#te-01) | [TG-01](#tg-01); cần map tới runtime test + evidence |

<!-- END GUIDE_REQUIREMENTS -->

<a id="handoff"></a>
## 12. Tiếp nhận FUP-02 và cách làm tiếp để tiết kiệm compute

### 12.1 Trong khi OpenCode tiếp tục chạy

- Giữ FUP-02 theo yêu cầu người dùng. Không sửa các source/imports/configs/tapes/registrations mà process
  đó đang dùng; không gửi lệnh dừng hoặc chạy thêm job cạnh tranh tài nguyên.
- Review/plan và evidence của lượt này ở namespace riêng. Live report có thể chậm checkpoint; dùng
  timestamp/hash đã pin để giải thích khác biệt, không gọi nó số mới nhất vĩnh viễn.
- Kết quả FUP-02 được tiếp nhận như discovery với giới hạn đã nêu; pending/failed không thành zero.
  Một checkpoint có selected params không đồng nghĩa arm account hoặc pair contrast đã hoàn tất.

### 12.2 Phân loại tái sử dụng trước khi quyết định rerun

| Thay đổi | Có thể tái sử dụng | Công việc phải làm lại |
|---|---|---|
| Chỉ report labels/hash/index | Raw artifacts đúng identity | Render/reconcile/manifest generation; không optimizer |
| Evaluation mask, metrics, bootstrap, decay arithmetic | Equity/fills có đủ marks và đúng execution | Recompute từ saved paths; D2 thiếu underlying path thì replay đúng anchors, không full search |
| Model labeling semantics hoặc trigger policy | Immutable source data/causal features; candidate evaluation đúng exact cutoff có thể cache | New tape/schedule và affected selection/deployment; không rewrite old tape |
| Scorer fee/metric/penalty/warmup hoặc alpha behavior | Market snapshot/pure indicators chỉ khi cache key còn đúng | Affected search + deployment + downstream inference, không rescale old curves |
| Execution resolution/latency/sizing | Data và registered design ideas | Contract/version mới, route parity rồi affected engine chain |
| Larger trial budget | Completed old design giữ làm discovery | New revision với full identity, không trộn 32/64 thành một matched run |

Freeze test của RF-05 chỉ cho một FUP-01 supersession là guard lịch sử, không lý do tạo workaround
vĩnh viễn. Lượt sửa tiếp theo dùng **study/version/manifest mới** và giữ frozen RF-05 evidence nguyên vẹn.
Không sửa pin cũ để làm test pass; không copy scripts thành nhiều implementation trái nhau.

<a id="fup-cost-decision"></a>
#### Rà soát điều kiện chờ và chi phí FUP-02

[Báo cáo cost/validity](evidence/reviews/fup02-cost-20260912-01/report.md) và
[JSON đã capture](evidence/reviews/fup02-cost-20260912-01/review.json) phân biệt thời gian trôi qua,
wall của invocation đã đóng và phần đang chạy; không tự suy CPU/RAM host từ sandbox hiện tại.
FUP vẫn hữu ích cho debug/profile trong đúng scope, nhưng nhãn RUN_VALID cũ không nghiệm thu
warmup/scorer, execution clock hoặc model/statistical controls của TE study mới.

Điều kiện chờ được thu hẹp theo [operational revision R02](configs/time_edge_validation_v4/operational_dependency_revision_r02.json):
final handoff cần cho tiếp nhận kết quả FUP cuối và sửa cùng source; không cần cho sửa kỹ thuật ở
bản sao lab độc lập. R01 và báo cáo TE-01 cũ giữ nguyên lịch sử. Runtime gate hiện tại vẫn đóng;
TE-02 phải kiểm đường nguồn độc lập bằng actual import/hash evidence trước engine pilot, không đặt
`fup02_final_handoff=true` giả. Các gate về isolation, ngân sách và validity vẫn áp dụng.

Khuyến nghị: ngừng mở thêm FUP shard/resume ở checkpoint an toàn, bàn giao PARTIAL có ledger;
sửa TE02.1/2, tách selection/deployment TE02.3 và tổng budget/resume TE02.7 trước khi mở rộng.
Đây là khuyến nghị sau review, chưa phải lệnh đã thực thi trên process của OpenCode.

### 12.3 Budget/stop rules

- T0: arithmetic/schema/controller probes nhỏ; T1: engine lifecycle/parity pilot; T2: full model/Mode 4
  treatment pilot; T3: bounded resumable discovery; T4: frozen run có total budget.
- Kế thừa guardrails G3: T0 target 60s, T1 120s, T2 600s, T3 900s/task như **budget cần đăng ký**, không
  hứa toàn nghiên cứu hoàn thành trong số phút đó. Nếu không đủ warmup/events trong cap, profile và
  record revision; không giảm fidelity âm thầm.
- Stop statistical inference khi validity fail. Technical failures phải repair/cap affected scope.
- Stop mở rộng model nếu không có parameter opportunity đủ support. Nếu có opportunity nhưng model
  chưa informative, thử một representation/horizon delta có registration riêng; không grid search vô hạn.
- Nếu information có nhưng activation/cost chặn, sửa policy scenario riêng; không backdate timestamps.
- Economic results được chấp nhận âm/inconclusive; outcome-based stopping phải nằm trong analysis plan.

### 12.4 Lệnh review/report thực sự đã có

Từ LAB_ROOT, capture **mới** (tên thư mục phải chưa tồn tại):

```bash
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B \
  scripts/audit_time_edge_review.py --out evidence/reviews/<new-review-id>
```

Lệnh này chỉ đọc existing files, chạy source probes nhỏ và ghi namespace review mới; không chạy engine.
Phạm vi dữ liệu đã capture và hash được ghi trong `audit.json`/`capture_manifest.json`.

Render các bảng đo và traceability của plan từ một review đã lưu:

```bash
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B \
  scripts/render_time_edge_plan.py --review evidence/reviews/time-edge-20260912-review01
```

Renderer đọc hai guide đã capture và hai acceptance registries được pin. Riêng review01, registries
ở `plan_inputs/`, có [manifest](evidence/reviews/time-edge-20260912-review01/plan_input_manifest.json)
xác nhận hashes khớp inventory lúc audit; các lần capture mới giữ chúng trực tiếp trong `captured/configs/`.

**Runner TE-01 đã thực thi:** chỉ đọc nguồn/snapshot metadata, kiểm contracts và baseline; không engine.

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  environments/lab_venv/bin/python -B scripts/run_te01.py audit --run-id FRESH_RUN_ID
# Commit đúng audit artifacts trước khi render:
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B \
  scripts/run_te01.py report --run-id te01-r01-20260912-01
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B \
  scripts/run_te01.py runtime-gate --run-id te01-r01-20260912-01
TE01_REPORT_RUN_ID=te01-r01-20260912-01 PYTHONDONTWRITEBYTECODE=1 \
  environments/lab_venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/time_edge_validation_v4/report_verification_cases.py
```

Runtime gate hiện trả exit 2 theo đúng các blocker trong evidence. `audit` bắt buộc thư mục mới;
không ghi đè run đã có. `before_repair_cases.py` được gọi riêng nên các FAIL chuẩn bị không lẫn
với default pytest suite mà OpenCode có thể đang dùng. Các runner TE-02…TE-05 chưa được triển khai.

## 13. Change log và điều kiện cập nhật

| Lần | Nội dung | Không được hiểu là |
|---|---|---|
| 2026-09-12, review01 | Inventory code/evidence; source probes; 20 findings; thống nhất 5 phase và model/time-edge/decay/report/test contracts | Đã repair runtime, đã chạy TE study, đã xác nhận kết luận thị trường |
| 2026-09-12, TE-01 preparation | Người dùng giao Codex triển khai; checklist trước code, source identities, 20 OPEN findings và report MD/JSON riêng | Đã hoàn thành TE-01, đã sửa 20 findings hoặc đã can thiệp FUP-02 |
| 2026-09-12, TE-01 R01 | Registration + baseline + source/data/package identities + reuse/invalidation; code `bc58622`, evidence `afb3e0c`, report `49fa565`; [báo cáo][te01-report] | Đã sửa toàn findings, đã có time edge, đã hoàn tất FUP hoặc đã mở market workers |

Sau mỗi task hoàn tất: commit scoped work theo quy tắc lab, ghi task ID/commit/evidence/test result,
update status/next task tại đây. Không push nếu chưa được yêu cầu; không merge/publish/deploy/live.
Đường dẫn QuantBT chính và alpha originals luôn read-only; kiểm và báo `../quantbt` status ở cuối trao đổi.

<!-- BEGIN GUIDE_LINKS -->

[g2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md
[g2-0]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#0-chỉ-thị-thực-thi-và-những-ranh-giới-không-được-vượt
[g2-0.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#01-điều-đã-được-phê-duyệt
[g2-0.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#02-safety-là-điều-kiện-bắt-đầu-không-phải-checklist-cuối
[g2-0.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#03-resource-policy-đề-xuất-ban-đầu
[g2-1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#1-bằng-chứng-đã-có-và-giới-hạn-thực-tế
[g2-1.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#11-archive-đã-đọc-đầy-đủ
[g2-1.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#12-kiểm-chứng-đã-thực-hiện-khi-viết-guide
[g2-1.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#13-repo-đã-đối-chiếu-được
[g2-10]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#10-thiết-kế-chứng-minh-selector-timing-và-bank-không-bị-nhập-nhằng
[g2-10.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#101-trục-so-sánh-abcd
[g2-10.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#102-controls-bắt-buộc
[g2-10.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#103-cùng-economic-engine-và-account-path
[g2-10.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#104-twenty-primary-cells-và-lịch-chạy
[g2-10.5]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#105-compute-budgets-và-baselines
[g2-11]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#11-phương-pháp-kết-luận-và-publishing-evidence
[g2-11.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#111-hai-giai-đoạn-thông-tin
[g2-11.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#112-primary-outcome-và-không-ép-tốt-hơn-mọi-mặt
[g2-11.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#113-paired-uncertainty-và-multiple-comparisons
[g2-11.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#114-transition-specific-diagnostics
[g2-11.5]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#115-datareport-artifacts
[g2-12]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#12-roadmap-chính-thức--đúng-10-phase
[g2-13]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#13-schemas-cli-đích-và-definition-of-done
[g2-13.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#131-research-record-identities
[g2-13.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#132-study-registration-example--schema-đích-không-kết-quả-đã-điền
[g2-13.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#133-alpha-certification-record
[g2-13.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#134-decision-evidence-tối-thiểu
[g2-13.5]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#135-cli-đích-để-agent-implement
[g2-13.6]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#136-những-claim-không-được-phát-hành
[g2-13.7]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#137-stopcontinue-rules
[g2-14]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#14-bộ-acceptance-tests--64-yêu-cầu-chưa-phải-64-tests-đã-chạy
[g2-2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#2-presets-full-sample-và-quyền-diễn-giải-kết-quả
[g2-2.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#21-bốn-tầng-alpha-version-bắt-buộc
[g2-2.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#22-presets-không-phải-clean-warm-start-cho-quá-khứ
[g2-2.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#23-không-tự-động-nhận-các-dictionary-không-thuộc-alpha
[g2-3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#3-review-từng-alpha-và-kế-hoạch-adaptation
[g2-3.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#31-a-hash--momentum-với-partial-tp-ladder
[g2-3.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#32-a-vwap--daily-vwap-mean-reversion-với-htf-filter
[g2-3.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#33-a-hma--adaptive-hma-trend-strategy
[g2-3.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#34-a-sc--signalcombine--alphatrend-like-long-flat
[g2-4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#4-chọn-execution-contract-trước-khi-so-methodology
[g2-4.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#41-primary-economic-setup
[g2-4.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#42-một-signal-close-không-thể-fill-lại-chính-close-vừa-quan-sát
[g2-4.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#43-protective-order-fidelity
[g2-4.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#44-minimum-engine-adapter-facade--api-lab-không-giả-api-quantbt-mới
[g2-5]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#5-kiến-trúc-lab-và-registry
[g2-5.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#51-quyền-sửa-alpha-rộng-nhưng-có-causal-attribution
[g2-6]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#6-data-design-server-first-năm-symbols-không-mở-rộng-scope-ngầm
[g2-6.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#61-inventory-theo-data-products-không-theo-các-tên-class-giả-định
[g2-6.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#62-cohorts-và-phạm-vi-lịch-sử
[g2-6.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#63-timestamp-và-resampling
[g2-6.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#64-feature-blocks-và-toán-học
[g2-6.5]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#65-external-free-data--optional-enrichment-không-thành-scope-creep
[g2-7]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#7-robust-parameter-selection-search-khác-validation
[g2-7.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#71-definition-và-geometry
[g2-7.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#72-candidate-discovery--independent-local-probes
[g2-7.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#73-một-robust-score-minh-bạch-để-triển-khai-trước
[g2-7.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#74-candidate-bank-cho-regime-policy
[g2-8]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#8-regime-model-persistent-states--transparent-online-decision
[g2-8.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#81-model-ladder-có-giới-hạn
[g2-8.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#82-objective-discrete-jm
[g2-8.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#83-sparse-extension-không-được-có-nghiệm-weights0-vô-nghĩa
[g2-8.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#84-online-inference-causal
[g2-8.5]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#85-output-và-uncertainty
[g2-8.6]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#86-training-và-model-selection-cadence
[g2-9]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#9-parameter-response-model-và-time-edge-policy
[g2-9.1]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#91-đây-là-lớp-nối-regime-với-quyết-định
[g2-9.2]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#92-historical-similarity-và-shrinkage
[g2-9.3]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#93-utility-và-transition-cost-cùng-đơn-vị
[g2-9.4]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#94-bốn-clocks-không-gộp
[g2-9.5]: QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md#95-campaign-and-bank-migration
[g3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md
[g3-1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#1-kết-luận-phản-biện-và-những-gì-phải-giữ
[g3-1.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#11-kết-luận-về-snapshot-đã-gửi
[g3-1.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#12-tái-sử-dụng-không-làm-lại-toàn-bộ
[g3-1.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#13-rules-an-toàn-và-phạm-vi-alphadata
[g3-10]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#10-rules-báo-cáo-cho-từng-phase
[g3-10.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#101-mỗi-phase-bắt-buộc-markdown--machine-readable-json
[g3-10.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#102-minimal-phase-report-json-schema-sketch
[g3-10.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#103-disposition-cho-mỗi-finding
[g3-10.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#104-trục-đánh-giá-tiềm-năng--không-ép-positive-narrative
[g3-10.5]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#105-records-cần-để-recompute-và-làm-chart
[g3-11]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#11-bộ-kiểm-thử-nghiệm-thu
[g3-11.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#111-nhóm-contract-execution-và-alpha
[g3-11.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#112-nhóm-mode-4-và-causal-schedule
[g3-11.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#113-nhóm-model-response-và-uncertainty
[g3-11.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#114-nhóm-metrics-báo-cáo-và-performance
[g3-12]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#12-handoff-claim-và-điều-kiện-kết-thúc
[g3-12.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#121-bảng-kết-quả-bắt-buộc-cho-claude-và-opencode
[g3-12.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#122-claim-rules-cuối-cùng
[g3-12.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#123-quy-tắc-dừng-và-mở-rộng
[g3-12.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#124-entry-points-và-commands-của-corrective-runner
[g3-12.5]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#125-handoff-manifest-đề-xuất
[g3-12.6]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#126-định-nghĩa-hoàn-thành
[g3-13]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#13-nguồn-phạm-vi-kiểm-chứng-và-cách-dùng-phụ-lục
[g3-13.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#131-ba-đầu-vào-audit-được-hợp-nhất
[g3-13.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#132-nguồn-technical-bổ-sung-không-thay-source-đã-pin
[g3-13.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#133-tính-chất-của-phụ-lục
[g3-13.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#134-kiểm-tra-toàn-vẹn-của-bản-hợp-nhất-này
[g3-2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#2-mục-tiêu-mode-4-và-thiết-kế-so-sánh
[g3-2.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#21-khóa-mục-tiêu-chính-không-tráo-sang-mode-1mode-5argmax
[g3-2.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#22-arms-mới--tên-riêng-để-không-nhầm-historical-abcde
[g3-2.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#23-những-thứ-phải-giống-giữa-primary-arms
[g3-2.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#24-continuous-deployment-khác-candidate-scoring
[g3-3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#3-source-quantbt-đã-kiểm-tra-thêm-khi-hợp-nhất
[g3-4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#4-đăng-ký-toàn-bộ-lỗi-và-corrective-actions
[g3-4.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#41-findings-a01a16-mandatory-disposition
[g3-4.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#42-các-phần-datatesttransparency-của-audit-cũng-phải-đóng
[g3-4.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#43-các-kiểm-tra-mới-của-lần-hợp-nhất
[g3-5]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#5-endpoint-routing-nhanh-nhưng-không-đổi-alpha
[g3-5.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#51-chính-sách-vectorized-first
[g3-5.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#52-ba-mức-sử-dụng-fast-route
[g3-5.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#53-timing-và-execution-resolution
[g3-5.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#54-percent-equity-khác-fixed-notional
[g3-6]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#6-metrics-fold-decay-và-cách-suy-luận-time-edge
[g3-6.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#61-giữ-metrics-hiện-có-thêm-definitions-thay-vì-đổi-thầm
[g3-6.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#62-return-và-pnl-partition-đúng
[g3-6.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#63-sharpe-cùng-đồng-hồ
[g3-6.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#64-profit-factor-hai-definitions-không-được-trộn
[g3-6.5]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#65-ba-nghĩa-của-decay-phải-tách
[g3-6.6]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#66-primary-endpoint-và-uncertainty
[g3-6.7]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#67-minimum-economic-effect-và-claim-gates
[g3-7]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#7-dữ-liệu-regime-và-timing-policy
[g3-7.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#71-data-trust-contract-vừa-đủ-không-audit-lại-cả-hệ-thống
[g3-7.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#72-regime-model-sửa-representation-trước-tăng-complexity
[g3-7.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#73-triggers-live-replayable
[g3-7.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#74-primary-dynamic-mode-4-integration-không-được-lộ-future-segment-end
[g3-7.5]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#75-secondary-selector-và-response-repair-không-lấn-mục-tiêu-chính
[g3-8]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#8-tăng-tốc-thí-nghiệm-và-quản-lý-ngân-sách
[g3-8.1]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#81-không-tạo-một-bài-test-chạy-hàng-giờ
[g3-8.2]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#82-lộ-trình-loại-công-việc-lặp
[g3-8.3]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#83-tpe-và-concurrency-không-đổi-methodology
[g3-8.4]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#84-pilot-budgets-đủ-để-thực-sự-exercise-mode-4
[g3-8.5]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#85-profiler-và-bảng-chi-phí-bắt-buộc
[g3-9]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#9-năm-phase-triển-khai
[g3-rf01]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf-01--khóa-phạm-vi-invalidate-đúng-và-biến-findings-thành-regressions
[g3-rf02]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf-02--actual-quantbt-simulation-mode-4-baseline-và-fast-execution-qualification
[g3-rf03]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf-03--regime-causal-đúng-và-lịch-mode-4-động-thực-sự
[g3-rf04]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf-04--thí-nghiệm-nhanh-trên-alpha-thật-đóng-metrics-và-decay
[g3-rf05]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf-05--frozen-đánh-giá-lại-phản-chứng-báo-cáohandoff-có-thể-kiểm-tra

<!-- END GUIDE_LINKS -->

[te01-report]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/report.md
[te01-json]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/report.json
[te01-identity]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/identity_report.md
[te01-source]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/source_data_manifest.json
[te01-fup]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/fup02_intake.json
[te01-binding]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/quantbt_binding_report.json
[te01-findings]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/finding_disposition.json
[te01-baseline]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/regression_baseline.json
[te01-acceptance]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/acceptance_coverage.json
[te01-tests]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/contract_tests.json
[te01-isolation]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/os_isolation.json
[te01-reuse]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/reuse_decision.json
[te01-invalidation]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/invalidation.json
[te01-verdict]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/phase_verdict.json
[te01-reproduction]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/reproduction_verification.json
[te01-report-check]: evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/report_verification.json
[g3-rf011]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf011--isolated-working-copy-và-identity
[g3-rf012]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf012--invalidation-và-claim-sửa-ngay
[g3-rf013]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf013--mode-4configmetric-contract-inventory
[g3-rf014]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf014--regression-suite-nhỏ-và-positive-control-plan
[g3-rf015]: REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md#rf015--register-primary-protocol-và-costtime-budgets
