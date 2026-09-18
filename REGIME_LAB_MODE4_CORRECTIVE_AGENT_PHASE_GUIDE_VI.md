# REGIME-LAB — GUIDE TRIỂN KHAI THEO PHASE CHO AGENT
## Mode 4 causal WFO: tăng tốc lab, kiểm định timing edge và nghiên cứu quyết định refit

**Phiên bản:** RA-GUIDE-1.0  
**Ngày:** 18/09/2026  
**Đối tượng thực hiện:** agent đang làm `BobbyAxerol/regime-lab`, nhánh `mode4-corrective`.  
**Phạm vi:** research lab; không phải production deployment, không phải nâng cấp toàn bộ QuantBT.  
**Trạng thái tài liệu:** đặc tả công việc và điều kiện nghiệm thu mới; không phải bằng chứng các phase đã được triển khai hoặc đã có edge.

> **Lệnh thực hiện:** tiếp tục từ implementation corrective hiện có. Không làm lại LAB/RF/TE từ đầu. Hoàn thành lần lượt RA-01 → RA-08 theo dependency và exit gate trong tài liệu này. Không chuyển phase bằng cách đổi tên lỗi, hạ chuẩn, xóa bằng chứng hoặc tự sửa gate thành PASS. Không đặt mục tiêu bắt buộc “regime phải thắng”. Mục tiêu là một phép thử đúng, đủ nhạy với lợi ích có ý nghĩa, có chi phí kiểm soát được và kết luận đúng phạm vi.

---

**Điều hướng:** [Rules](#rules) · [Research contract](#research-contract) · [Phase map](#phase-map) · [RA-01](#ra-01) · [RA-02](#ra-02) · [RA-03](#ra-03) · [RA-04](#ra-04) · [RA-05](#ra-05) · [RA-06](#ra-06) · [RA-07](#ra-07) · [RA-08](#ra-08) · [Metrics/claims](#metrics-claims) · [Evidence/report](#evidence-report) · [CLI](#cli) · [Definition of Done](#done).

## 0. Đọc trước khi sửa code

### 0.1. Nguồn và giới hạn của guide

Guide dựa trên snapshot `regime-lab-main 2.zip` và audit corrective đã thảo luận, không dựa trên `main` cũ:

```text
archive_sha256 = 261b50f28e7a599345e081d0d4ca7cf951d7dfa3c55ca4635ab9c02b3bfa6422
archive_label  = regime-lab-main 2.zip
branch_label_in_handoff = mode4-corrective
```

ZIP không chứa bằng chứng Git HEAD để xác nhận trạng thái remote. Agent phải ghi branch, commit, dirty diff và các file đang làm trên host thực tại RA-01. Không suy ra HEAD từ tên ZIP. Source mới hơn phải được đối chiếu từng finding; không buộc sửa lại lỗi đã có bằng chứng sửa đúng.

Các tài liệu/nguồn cần đọc, theo thứ tự:

1. **Guide này**, nhất là §1–§5 và phase đang thực hiện.
2. `handoff/SESSION_TE_CURRENT.md`, `handoff/TE_MASTER_PLAN_V1.md/.json`, `handoff/TE_PHASE_PLAN_V1.md`, `handoff/TE_CLI_RUNBOOK.md`, cùng ledger/attempt mới hơn handoff.
3. `REGIME_MODE4_CORRECTIVE_REVIEW_VI.md`: E01–E08; các paths và hashes trong audit.
4. Registration và source đang có tại `configs/time_edge_validation_v4/`, `src/crypto_regime_lab/time_edge/`, `experiments/dynamic_fold_provider.py` và các tests tương ứng.
5. `REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md` để giữ economic/causal contracts và lịch sử findings; không lấy lỗi của runner legacy áp máy móc lên `time_edge/`.

Guide này tự chứa mục tiêu, contracts, phase tasks, gates và mẫu báo cáo. File audit bổ sung source excerpts; không cần một ZIP evidence phụ để hiểu phải làm gì.

### 0.2. Thứ tự hiệu lực và cách thay registration

Thứ tự hiệu lực: chỉ dẫn mới của Bobby → guide này trong phạm vi được giao → economic/safety contracts đã xác minh → registration tương ứng với từng run → các hướng dẫn lịch sử.

**Guide mới cho phép thiết kế lại thứ tự gate, không cho phép viết lại lịch sử.** RA-01 phải tạo `protocol_migration` có old rule → new rule → lý do → affected claims/tests. Chỉ job mang registration mới được dùng gate mới. Không sửa acceptance của TE run cũ để làm nó xanh.

Các thay đổi được yêu cầu rõ:

- Tách **technical validity**, **scientific support**, **economic evidence** và **owner approval**.
- Không lấy ranking-IC dương, số switches > 0 hoặc economic PnL dương làm điều kiện kỹ thuật để mở discovery.
- Không bắt một ma trận synthetic nhiều năm hoàn thành trước khi chạy discovery thị trường nhỏ đã đúng execution.
- Không bỏ causal/fill/accounting/isolation/resource gates. Những gate này vẫn chặn đường chạy liên quan.
- `M4_CAL_BUDGET` là tên báo cáo dễ hiểu; canonical ID tái sử dụng `M4_CAL_MATCHED` đang có. Không tạo hai arms kinh tế giống nhau chỉ vì khác tên.
- Giữ nguyên raw historical runs, invalidations, costs, consumed-data disclosures và previous negative/null results.

### 0.3. Đích nghiên cứu và nhận định khả thi

Nghiên cứu chính là **timing-only**: cùng QuantBT Mode 4 train-only selector, cùng training-memory rule và execution; regime thay thời điểm yêu cầu refit. Nghiên cứu thứ cấp là **action-aware**: context có giúp quyết định refit hay giữ incumbent không? Regime-conditioned training/specialist-bank/deep-learning sweep không thuộc vòng triển khai này.

Khả thi về kỹ thuật không đồng nghĩa đã chứng minh economic edge. Không ghi xác suất thành công hoặc hứa speedup chưa đo. Có thể kết thúc nghiên cứu hợp lệ với kết luận âm, không đủ support hoặc chưa đủ dữ liệu mới; không được biến các trạng thái đó thành lỗi triển khai hoặc tự tuyên bố model thắng.

---

<a id="rules"></a>
## 1. Các rules không được vi phạm

### 1.1. Engine và môi trường

**R-01 — QuantBT là authority duy nhất cho mô phỏng tài chính.** Orders, actual fills, rejects, positions, cash, fees, equity, margin và liquidation phải đến từ engine. Lab chỉ tạo signals/intents, regime models, scheduling, adapters, analysis và tiny test oracles. Không có financial simulator thứ hai trong notebook, panel builder hoặc response model.

**R-02 — Pin actual environment.** Baseline registration trong snapshot là `quantbt-engine==1.1.1`, `quantbt-native==0.4.2`; venv lab là `LAB_ROOT/environments/lab_venv`. Ghi distribution version, module origin, package/native hashes, Python/NumPy/Optuna versions, lockfile và actual route. Tên package hoặc `backend='rust'` không chứng minh native đã chạy. Nếu host đã khác, lập version disposition trước economic work; không downgrade/upgrade tự động.

**R-03 — Không sửa engine protected để vượt gate.** Không sửa `../quantbt`, package production hoặc site-packages trực tiếp. Snapshot có `engine_source_mutations_allowed=false`. Phát hiện bug engine thì viết minimal reproducer + proposed patch/dependency report. Chỉ triển khai engine patch trong isolation sau chỉ dẫn riêng của owner. Lab-only admission guard phải có tên/version riêng, giữ stock outputs và áp đối xứng cho arms; không gọi nó stock selector không đổi.

**R-04 — Dùng đúng Mode 4.** Contract logic:

```text
optimization_mode           = mode_4_is_only_robust
optimization_schedule       = per_fold_causal
candidate_selection_metric  = is_only_robust
scoring_backend             = endpoint
calendar_contract           = exact_v2
```

Agent phải xác nhận binding thực trong package đã pin. Causal optimization không được chấm future OOS candidates để chọn params. Không tạo trial record giả Sharpe rồi gọi private argmax. Không thay Mode 4 thành fixed bank, Mode 5 hoặc full-set TPE mà vẫn giữ tên thí nghiệm.

**R-05 — Ưu tiên fast route tương đương.** `pct_equity`/prepared/native vectorized được ưu tiên khi giữ đúng signal availability, fill clock, sizing, protection và state semantics. Fill-dependent alpha dùng qualified event route. Không bỏ partial TP, amendment, stops, fees hoặc đổi next-open thành next-close để chạy nhanh. Route variant thay semantics phải là cohort riêng, không thay primary tự động.

### 1.2. Repository, dữ liệu và hạ tầng

**R-06 — Chỉ write trong lab được phép.** Mặc định host path từ handoff: `/root/bobby/pool_alpha/lab_regime_model_quantbt`. Verify actual path, `.lab_marker`, allowlist và sandbox trước write. `../quantbt`, `../alphas_storage`, original alpha files, loader/data snapshots và production services là protected/read-only. Không dùng hardlink cho mutable code copy. Không chạy environment được copy trong ZIP.

**R-07 — Không phá công việc đang dở.** Không `git reset --hard`, `git clean`, xóa untracked evidence, force checkout, rebase/merge hoặc gom `git add .` để dọn trạng thái. Commit scoped sau đơn vị việc hoàn thành. **Không push** nếu chưa được yêu cầu. Không áp workflow/PR rules riêng của Portal hoặc contributor khác sang repo này.

**R-08 — Tài nguyên không tự tăng.** Baseline envelope gần nhất trong snapshot là 1 worker, 2 CPU, 4 GiB RAM và một ledger chi phí đã dùng. RA-01 phải đọc allocation mới nhất trên host; quyền cấp thực mới là authority. Không reset quota bằng run ID mới, không đổi cgroup/isolation, không dùng production venv hoặc kill process ngoài run. Không mở nhiều workers chỉ vì máy có nhiều cores.

**R-09 — Scope market/alpha giữ nguyên.** Universe dự kiến: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT; bốn alpha A-SC, A-HMA, A-VWAP, A-HASH. Crypto spot từ 01/01/2020 theo convention người dùng, nhưng chỉ sau listing/coverage và đủ warmup thật. Không lấp giá trước listing, không lấy pre-2020 làm shortcut nếu chưa có authorization dữ liệu riêng.

**R-10 — Timestamp và availability.** Crypto datetime-naive được hiểu là UTC; aware thì convert UTC giữ nguyên thời điểm. Không tự cộng/trừ 7 giờ. Bar timestamp và `available_at` phải phân biệt; feature HTF chỉ dùng khi bar đóng. Không áp UTC-naive cho thị trường khác. Missing data không bằng zero-return day; flat account trong ngày market hợp lệ vẫn giữ return 0.

### 1.3. Causality, reporting và scientific discipline

**R-11 — Không backdate.** Search/model/indicator ready phải sau cutoff hợp lệ. Initial incumbent giống giữa arms, chọn trước evaluation; nếu chưa sẵn sàng, common flat-until-ready. Không backfill params chọn muộn vào bar 0. Không truyền future dynamic-segment end vào training.

**R-12 — Continuous account là continuous.** Mỗi deployment arm giữ một account theo chronology; version switch tuân theo campaign/pending-order rules. Không reset ở fold boundary rồi ghép equities. Không ghép candidate returns thành switching-account PnL nếu chưa được engine thực thi với state chính xác.

**R-13 — Không sửa protocol theo kết quả rồi giả là preregistered.** Parameter ranges, trial budgets, model ladder, scheduler knobs, horizon, seed policy, primary contrast và uncertainty plan phải có trước outcome tương ứng. Revision có parent hash, lý do và data-exposure disclosure. Không chỉ giữ successful seeds/cells/runs.

**R-14 — Trial lifecycle đầy đủ.** `trial_id`, `candidate_id`, `evaluation_id`, `selection_id` và `attempt_id` khác nhau. Failed/pruned/duplicate/reused trials vẫn được ghi. Runtime exception không được đổi thành COMPLETE với score −1e9. Undefined financial metrics dùng `null + status/reason`, không NaN/Infinity trong JSON chuẩn.

**R-15 — Không lấy sự im lặng làm bằng chứng.** Zero switches có thể là policy đúng; zero fills có thể là market case hợp lệ. Nếu treatment thật sự không đổi actions, report economic contrast tương ứng và cơ chế không được exercise. Chỉ positive-control fixture mới bắt buộc tạo hành vi đã thiết kế; không ép thị trường thật phải có lãi/giao dịch/transition để PASS.

**R-16 — Evidence trước lời kết luận.** Báo cáo được sinh từ artifacts/ledger, không chỉnh số tay. Mỗi finding có path/hash, source/runtime scope và status. Không claim full-suite, native parity, speedup hoặc market rerun từ một test helper hay metadata.

**R-17 — Tôn trọng exit gate.** Gate mandatory thiếu/FAIL/BLOCKED thì phase chưa hoàn tất. Không bỏ test, chuyển thành `xfail`, giảm tolerance, thay expected result theo output hiện tại hoặc dán receipt của source khác. Deviation không được tự cấp waiver.

**R-18 — Owner review theo phase.** Khi technical exit gate PASS, commit phần việc và báo `WAITING_OWNER_REVIEW`. Mặc định không mở phase kế tiếp trước phê duyệt của Bobby. Chỉ được auto-advance nếu Bobby đã chỉ dẫn rõ; phải ghi reference của chỉ dẫn, không tự tạo approval. Trong phase được duyệt, không hỏi lại các quyết định đã chốt trong guide.

---

## 2. Snapshot findings phải được đối chiếu, không được quên

| ID | Bằng chứng đã có | Nghĩa vụ trong guide | Không được kết luận quá mức |
|---|---|---|---|
| F-01 | Mode 4 causal, activation và actual event feedback đã có; pilot09 có 32 candidates/224 scorer calls [E01]. | Reuse và regression; RA-01/04. | Không gọi runner mới là fake Mode 4 theo lỗi legacy. |
| F-02 | Semantic market không đổi nhưng `run_id`/path đổi manifest hash gây search cache miss [E05]. | Sửa identity, invalidate đúng, cross-run actual reuse; RA-02. | Cache metadata HIT không đủ nếu engine vẫn chạy lại. |
| F-03 | controls-10 lỗi memory sau ~23.496,66 giây, chưa hoàn tất deployment; prepare full rồi window [E06]. | Lazy preparation, retention, lifecycle, measured memory; RA-03. | OOM không là NO_EDGE; 84,4 MiB không là toàn working set. |
| F-04 | 7/8 selections của control dùng temporal fallback; case một finite subperiod có score như sáu finite giống nhau [E07]. | Raw/support distinction, admission policy, stock preservation; RA-04. | Không gọi mọi fallback là bug hoặc xóa low-trade alphas tùy tiện. |
| F-05 | R2: 5/29 vintages JM, 24 M0; 24 evaluable episodes; rank-IC delta −0,03263 [E03]. | Giữ kết quả âm/inconclusive, sửa target/support; RA-05/06. | Không suy IC thành PnL hoặc 24 episodes thành 729 independent samples. |
| F-06 | Replay có 28 accepted triggers, median gap ~28,17 ngày với min-gap28 [E04]. | Calendar budget-matched + cadence diagnostics; RA-05. | Đây là replay scheduler, không phải 28 actual deployments. |
| F-07 | M0 là threshold-state model, không phải abstain/no-op [E02]. | Report actual mixture và policy fallback; RA-05/06. | Không mô tả cả path là JM khi M0 chiếm đa số. |
| F-08 | Synthetic power calibration `engine_runs=0`; world có regime chưa chắc alpha có known edge [E08]. | Controls nhỏ đúng mục tiêu; statistical power riêng; RA-04/07. | Không chứng nhận market power từ injected synthetic effect. |

RA-01 tạo disposition cho từng finding: `PRESENT`, `FIXED_WITH_PROOF`, `SUPERSEDED_PATH_QUARANTINED`, `NOT_REPRODUCED_WITH_SCOPE`, hoặc `NEEDS_RUNTIME`. Không tạo trạng thái “đã đọc nên xong”.

---

<a id="research-contract"></a>
## 3. Thiết kế nghiên cứu bắt buộc

### 3.1. Bốn arms chính, cùng conventions

| Canonical ID | Vai trò | Rule |
|---|---|---|
| `STATIC` | Diagnostic không refit | Cùng initial Mode 4 selection như các arms, giữ params; alpha vẫn giao dịch theo params đó. |
| `M4_CAL` | Baseline lịch hiện tại | Calendar cadence được freeze, mặc định snapshot 180 ngày. |
| `M4_CAL_MATCHED` | Báo cáo có thể ghi CAL_BUDGET | Cadence chọn từ development/profiling, không dùng realized future refit count. |
| `M4_REGIME` | Primary timing treatment | Cùng Mode 4, memory, execution; chỉ scheduling khác. |

Primary confirmatory contrast mới đề xuất theo guide: `M4_REGIME − M4_CAL_MATCHED`. Contrast với `M4_CAL` là key secondary; `STATIC` là diagnostic. Đây là thay đổi so với old four-hypothesis family: phải ghi vào migration và freeze trước outcomes mới, không chọn lại primary vì bảng cũ cho kết quả thuận lợi.

Raw legacy replay giữ old names/configs. Không trộn old-stock với guarded/new-selector outcomes trong một treatment contrast.

### 3.2. Economic baseline và giữ semantics

Baseline trong snapshot [E09], phải resolve qua actual route:

```text
initial_equity                 20,000
allocation_fraction            0.10 của actual equity tại entry
leverage_cap                   1
one_way_fee_rate                0.0004
one_way_slippage_rate           0.0001 (1 bp)
training_memory_days           180
primary_execution_resolution   1m khi giữ event/order-sensitive cohort
funding                        missing_declared_not_venue_exact
terminal                       mark-to-market, open positions giữ/censored
```

Đây là study assumptions, không phải khẳng định phí live hiện hành của sàn. Dùng golden fills xác nhận units và binding. `fee=2×one_way_fee` chỉ ở route có semantics đó; không double-charge typed API. Actual entry sizing không lấy từ tên constructor.

Decision resolutions tham chiếu: A-SC/A-VWAP/A-HASH 15m, A-HMA 1h. Chuyển sang fast route chỉ khi cùng timing/economics đã qualify. Nếu route không support, `BLOCKED_CAPABILITY` cho cell/route; không lén chạy coarse bars.

### 3.3. Data split và ngân sách thử nghiệm

Giữ development lịch sử là retrospective. Snapshot ghi [E09]:

- `[2021-01-01, 2024-01-01)` là development, có thể cần lùi evaluation start tới khi đủ initial/model/alpha history theo rule đăng ký.
- `[2024-01-01, 2026-09-01)` đã consumed, chỉ dùng retrospective theo permission/registration; không đổi thành untouched holdout.
- Prospective chỉ gồm decision/outcome sau một freeze thật và đủ mature; ngày lớn hơn split cũ không tự là dữ liệu mới chưa xem.

Mỗi run freeze exact `[start,end)`, effective warmup, data hash và exposure history. Không tự lấy 2019 cho crypto primary. Data sau 2026-09-01 cũng phải kiểm exposure và availability; guide không cấp trước claim “fresh”.

Primary discovery: 1 cell qualified, rồi 1 cell khác có coverage/behavior hợp lệ. Full scope vẫn có coverage matrix 20 cells. Không chọn cells vì PnL đẹp; không chạy tất cả ngay. Một partial study có thể hoàn tất đúng phạm vi nhưng không là full-universe certificate.

Tuning mặc định mới: **2–3 chiều có ý nghĩa, 50 attempted trials/cutoff, 1 fixed seed ở vòng đầu**. Số tổ hợp có thể quanh 1.000 sau constraints; không đồng nghĩa chạy 1.000 trials. Legacy 32-trial results giữ nguyên. Có thể dùng 32–64 trong coverage revision đã freeze trước paired outcomes; không tự tăng mãi tới khi có plateau/lãi. Thử 8–16 trials chỉ là plumbing/profile, không chứng nhận selector robustness.

### 3.4. Work, cache và latency

`allocated_budget`, `charged_work`, `realized_work` và `model_overhead` phải tách. Equal trials/refit không có nghĩa equal total compute. CAL_MATCHED sử dụng dự báo regime work từ development, menu hiện có 28/56/90/180 ngày; tie chọn cadence chậm hơn theo contract cũ, trừ revision explicit.

Realized work khác > tolerance đã freeze thì chỉ claim **bounded-budget**, không “identical-compute”. Không sửa calendar dựa số refit tương lai. Report actual candidate-window-bars, engine accounts, callbacks, wall/CPU/RSS và wasted attempts.

**Cache không cho quyền đi ngược thời gian.** Artifact có cutoff/data legality trước decision mới được reuse. Khi backtest dùng cached answer, ready time vẫn theo latency contract đã calibrate, không bằng 0 vì chạy lại nhanh. Research resource savings và simulated deployment latency là hai đại lượng khác nhau.

### 3.5. Các loại kết quả tách biệt

```text
technical_gate: NOT_RUN | RUNNING | PASS | FAIL | BLOCKED
research_status: NOT_ASSESSED | DISCOVERY_ONLY | INCONCLUSIVE_SUPPORT |
                 INCONCLUSIVE_EFFECT | POSITIVE_WITHIN_SCOPE |
                 NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE | UNDERPERFORMED_WITHIN_SCOPE
reproducibility: NOT_TESTED | PARTIAL | VERIFIED_SAME_CONTRACT
owner_review:    PENDING | APPROVED | CHANGES_REQUESTED
```

`PASS` kỹ thuật không có nghĩa positive edge. CI chứa 0 không là NO_EDGE. Mandatory artifact không có do OOM/capability thì BLOCKED; không được dùng `INCONCLUSIVE_SUPPORT` để che một job chưa chạy. Ngược lại, mẫu ít nhưng computations hợp lệ có thể có technical PASS và research INCONCLUSIVE_SUPPORT.

---

<a id="phase-map"></a>
## 4. Phase map và exit policy

| Phase | Đích bắt buộc | Dependency | Điểm dừng owner |
|---|---|---|---|
| **RA-01** | Pin hiện trạng, migration protocol, executable gate verification, budget ledger | Không | Duyệt contracts/migration trước economic work |
| **RA-02** | Semantic cache, correct invalidation, crash-safe reuse/checkpoint | RA-01 | Duyệt actual cache tests |
| **RA-03** | Lazy memory, retention tiers, qualified fast routes, profiler | RA-02 | Duyệt parity + tài nguyên |
| **RA-04** | Mode 4 support/coverage và compact end-to-end validity controls | RA-03 | Duyệt selector contract và readiness |
| **RA-05** | Timing-only discovery 4 arms, calendar-matched, action lineage | RA-04 | Duyệt discovery interpretation, không yêu cầu positive |
| **RA-06** | Reusable response panel, action-target, age-only/context comparison | RA-05 | Duyệt tối đa một policy revision cho tiếp tục |
| **RA-07** | Bounded replication, falsification, decay và inference | RA-06 | Duyệt policy/analysis freeze và claims scope |
| **RA-08** | Frozen replay/evaluation, final claims, runbook và handoff | RA-07 | Owner quyết định kết thúc/mở nghiên cứu tiếp |

Không renumber LAB/RF/TE hoặc gọi mọi subtask là phase mới. RA là implementation sequence bổ sung; mapping sang TE tasks giữ trong một registry.

### 4.1. Trình tự đóng phase

`implementation → tests → actual scoped run khi phase yêu cầu → verify artifacts → generate report → scoped commit → owner review`.

Reviewer/owner nhận báo cáo có bằng chứng đã chạy. Không báo “xong phase” chỉ vì code compile hoặc đã viết test chưa chạy. Không mở dependent economic jobs khi prerequisite receipt thiếu, expired theo source dependency hoặc FAIL.

### 4.2. Reuse bằng chứng, không bắt rerun vô lý

Mỗi receipt pin dependency digest của phần nó chứng nhận, không hash toàn repo rồi invalidate vì sửa README. Reuse được nếu source/economics/data/test protocol liên quan không đổi; ghi `verified_reuse_of` và kiểm hash thực. Đổi CLI gate/reporting phải test phần affected; không bắt rerun accounts nếu financial computation không đổi.

### 4.3. Không tạo hệ thống orchestration thứ hai

Tái sử dụng `scripts/te.sh`, `scripts/run_time_edge.py`, runtime/ledger/cache/planning/reporting hiện có. Các artifact dưới đây là **logical records**; có thể lưu trong JSON/JSONL hiện có và index bằng manifest, không phải buộc tạo hàng chục service/database/schema framework mới.

Chỉ thêm lớp RA registry/verifier mỏng. Không migrate sang Ray/Airflow/Kubernetes, không đổi database chỉ để chạy guide, không rewrite native core, không mua data và không mở dự án ML platform.

---
<a id="ra-01"></a>
## 5. RA-01 — Khóa hiện trạng, scope, protocol migration và gate có thể kiểm tra

### Mục tiêu

Biết chính xác code/runtime nào đang được sửa, phần nào đã làm đúng và rule nào thay đổi. Sau phase này, một job không hợp lệ không thể đi qua RA verifier chỉ vì CLI trả exit code 0 hoặc một field tự khai là PASS.

### Công việc bắt buộc

**RA01.1 — Inventory thực, không khôi phục bản cũ đè lên host.** Ghi branch/HEAD, dirty diff, untracked inventory, package origins/hashes, `.lab_marker`, active jobs thuộc lab, ledger allocations và quyền read/write thực. Snapshot status không thay host status. Cẩn thận với commands có side effect/import ghi cache; cache/tmp/bytecode chỉ trong lab. Chụp protected tree fingerprints/status trước và sau, không khẳng định protected tree vốn sạch nếu nó đã dirty từ trước.

**RA01.2 — Map finding và source.** Đối chiếu F-01…F-08 sang current path/function/test. Mỗi finding có `current_disposition`, `evidence_refs`, `affected_paths`, `planned_phase`. Những lỗi đã sửa có source/runtime proof thì reuse, không viết lại cho đủ phase.

**RA01.3 — Tạo registration mới tối thiểu.** Dùng namespace `regime_time_edge_ra_v1` hoặc alias được ghi rõ vào TE planner; không gọi cùng immutable R01. Khóa 4 arms, primary/secondary contrasts, data roles, selector version policy, tuning budget và scope mở rộng. `STATIC` kế thừa initial selection; CAL_BUDGET alias canonical CAL_MATCHED. Record fields chưa xác định phải là `PENDING_CALIBRATION`, khiến economic job bị chặn tới khi được resolve ở phase quy định.

**RA01.4 — Migration gate cũ.** Tạo bảng ít nhất các dòng sau:

| Old gate/rule | New disposition | Test phải có |
|---|---|---|
| Full multi-year learned synthetic matrix bắt buộc trước discovery | Giữ history, thay readiness bằng compact validity/E2E controls RA-04; full scientific calibration sang RA-07 | Invalid execution vẫn blocked; model IC âm không tự block |
| Ranking IC > 0 như prerequisite economic run | Diagnostic/secondary endpoint, không technical gate | IC âm + execution hợp lệ vẫn được plan discovery |
| Minimum switch/selection count chung cho mọi kết luận | Diagnostic cho mechanism/support; không bắt STATIC đổi params hoặc treatment luôn hành động | Identical-action policy report đúng, không ép switch |
| ≥365 ngày cho economic inference | Giữ floor đăng ký cho confirmatory inference; shorter technical pilot chỉ descriptive | Short pilot không được cấp economic verdict |
| Old four-hypothesis family | Historical unchanged; new primary H-BUDGET, các claims khác có family khai báo | Không bỏ một hypothesis đã nhìn outcome để giảm multiplicity |
| Quota/cost per legacy run | Charge ledger tích lũy, không reset theo namespace | New ID không tạo free compute |

Migration là **methodology revision có chủ ý**, không phải chứng nhận old gate đã pass. Chỉ owner phê duyệt migration mới mở đường RA economics. Không nới threshold/risk cap âm thầm trong cùng migration.

**RA01.5 — Resource admission.** Đọc available allocation thật. Tạo cost model dựa measurements đã có và micro-profile nằm trong quyền hiện tại. Khóa per-task wall cap, memory cap, workers/threads, max retry và phase envelope. Nếu cap cũ đã hết, `BLOCKED_BUDGET`; không khởi chạy job bằng run ID mới. Guide không tự cấp thêm 250.000 giây hoặc bất kỳ quota đã tiêu trước đó.

**RA01.6 — Thin verifier.** Tái dùng manifest verifier; thêm RA receipt check nếu thiếu. Nó phải đối chiếu required gate IDs, artifact hashes, source dependency digests, actual commands/exit/status, test counts, missing artifacts, block reasons, protected-state delta và approval dependency. Chỉ exit 0 không đủ, vì task có thể trả JSON `BLOCKED` với process success.

### Artifacts tối thiểu

`baseline_identity`, `finding_disposition`, `protocol_migration`, `registration`, `resource_budget`, `test_registry`, `phase_manifest`, `report.md`, `handoff`.

Các tên này có thể là records trong file hiện có; index một chỗ. Dữ liệu approval để `PENDING` đến khi có quyết định thật.

### Tests và exit gate RA-01

- **G01-ID:** pin đúng branch/worktree và actual engine/native; protected paths không có thay đổi do phase gây ra.
- **G01-MIG:** old registrations/claims/evidence bất biến; mapping old→new đầy đủ và owner duyệt scope trước phase sau.
- **G01-VERIFY:** thiếu receipt, wrong hash, stale dependency, `BLOCKED` trong JSON, no-tests-collected và mandatory xfail đều không thể PASS.
- **G01-BUDGET:** new run ID không reset charge; admission từ chối job vượt envelope thật; không launch economic job qua preflight.
- **G01-REPORT:** tất cả findings có disposition và future phase; no fake completed status.

**Exit:** technical PASS + evidence + scoped commit → WAITING_OWNER_REVIEW. Không đợi model dương để đóng RA-01. Nếu source/version/path không xác định được thì BLOCKED, không đoán.

---

<a id="ra-02"></a>
## 6. RA-02 — Semantic cache, đúng invalidation và checkpoint không làm đổi thí nghiệm

### Mục tiêu

Cùng một phép tính hợp lệ được chạy một lần; đổi nơi lưu/run ID không làm tính lại. Ngược lại, đổi dữ liệu hoặc financial semantics phải invalidation đúng. Cache không làm thay chronology, TPE information flow hoặc simulated ready time.

### Source ưu tiên

`time_edge/compute_cache.py`, `pipeline_controls.py`, `planning.py`, `storage.py`, `runtime.py` và các evaluator/candidate caches thực sự được runner gọi. Map current names tại RA-01.

### Công việc bắt buộc

**RA02.1 — Tách computation identity và provenance.** Gợi ý contract semantic key:

```text
schema_version
ordered market-content / coverage / correction-vintage digest
symbol + interval + observed/available clock contract
requested scoring window + allowed pre-roll + data prefix cutoff
alpha source/dependency digest + canonical effective params
execution clock + sizing + fees/slippage/funding + constraints
engine/native build + route semantic version
initial account/strategy state digest or fresh-state contract
scorer/metric/selector-support version
```

Key của search thêm search-space/constraints, sampler/version/seed, trial budget và ask/tell contract. Key của model thêm training cutoff, feature protocol, mature-label panel digest, target/horizon và design-selection rule. Deployment key thêm ordered **causal** selections, activation policy và initial state.

`lab_run_id`, output path, wall-clock creation time và producer ID nằm ở receipt/provenance, không trong financial cache key. Backend changes có thể làm invalidation nếu equivalence chưa chứng nhận. Không bỏ data-revision vintage vì raw price path nhìn giống nhau.

**RA02.2 — Prefix hashing đúng phạm vi.** Khi task chỉ được phép dùng data đến cutoff, future suffix đổi không nên đổi key của task prefix, nhưng feature/state phải được chứng minh prefix-causal. Hash slice/partition content kèm precise coverage; không reuse một full-partition hash có future information rồi cho phép model đọc phần tương lai. Code/feature warmup thay đổi phải invalidation phần affected.

**RA02.3 — Dependency closure.** Hash alpha helpers, schema, shared transformations và execution bridge, không chỉ top-level file. Test sửa shared helper phải MISS. Doc-only/provenance-only changes không tạo MISS của numeric task. Report cold compile/cache overhead tách financial work.

**RA02.4 — Atomic cache receipt.** Write artifact temp trong lab → flush/commit theo filesystem contract → hash/validate → atomic publish receipt. Corrupt, incomplete hoặc failed attempt không được coi HIT. Dùng locking existing runtime; không tạo hai writers cho một semantic key. Legacy records không có đủ identity proof thì quarantine/recompute, không suy equivalent chỉ từ params/PnL.

**RA02.5 — Giữ trial identity và TPE sequence.** Reused candidate vẫn tạo trial lifecycle reference; không bỏ tell/update của sampler. Restart một TPE study chỉ từ danh sách complete trials có thể không tái tạo đúng RNG state: phải pin/checkpoint state được library hỗ trợ, hoặc deterministic replay ask/tell với cached objectives và test prefix equivalence. Không nạp pickle không tin cậy, không đổi Optuna version để resume. [S1]

**RA02.6 — Checkpoint đúng mức.** Task artifacts, search trial receipts và independent cells có thể checkpoint. Continuous account checkpoint chỉ được dùng khi QuantBT expose state đầy đủ và certified restore. Nếu thiếu, replay deterministic prefix bằng engine; không tự serialize vài biến equity/position rồi coi là full state.

**RA02.7 — Causality cả khi warm-cache.** Cache outcome có available/mature time sau cutoff phải bị từ chối. Hit của search không làm ready_at sớm hơn latency đã freeze. Capture `physical_compute_at`, `simulated_cutoff`, `simulated_ready_at` riêng.

### Tests bắt buộc

| Test ID | Case | Expected |
|---|---|---|
| C01 | Same semantics, run ID/path khác | HIT, 0 new candidate engine runs ở task đã cache |
| C02 | Market content/correction, fee, sizing, timing hoặc alpha helper thay đổi | MISS đúng dependent scope |
| C03 | Chỉ sửa report text/producer path | Numeric cache vẫn dùng được |
| C04 | Future suffix mutation, task train prefix không đổi | Key/output prefix không đổi; không future access |
| C05 | Crash trước receipt/partial payload/corrupt file | Không HIT; preserve failed attempt |
| C06 | Concurrent request cùng key trong quyền worker test | Một owner computation; deterministic validated reuse |
| C07 | Duplicate params do TPE | Trial ledger đủ; evaluation reused; ask/tell sequence không bị bỏ |
| C08 | Crash/resume study | Same subsequent proposals/objectives/selection như uninterrupted contract |
| C09 | Mature outcome/search ready chưa tới decision | Reject future artifact; cached ready không bằng 0 |
| C10 | Reuse giữa reset vs carry initial state khác | MISS hoặc typed incompatibility, không false HIT |

C01 phải có ít nhất một **actual small QuantBT computation**, không chỉ mocked cache. Synthetic/mocked tests bổ sung failure paths. Không cần chạy multi-year 50-trial study chỉ để kiểm format key.

### Artifacts và exit gate RA-02

Lưu `cache_contract`, `dependency_manifest`, `cache_test_matrix`, `actual_cross_run_reuse`, `resume_parity`, counters before/after và phase report.

- **G02-SEM:** C01–C10 pass trên scope khai báo, bao gồm actual numeric reuse.
- **G02-NUM:** outputs tài chính trước/sau tối ưu tương đương theo tolerance freeze; differences provenance được tách.
- **G02-COUNT:** report `requested_trials`, `unique_evaluations`, `cache_hits`, `cache_misses`, `new_engine_runs`, `visited_bars`; không tính cache-hit bars là vừa execute.
- **G02-LEDGER:** attempts/costs cũ còn nguyên; child source/config khác không reuse sai; checkpoint không reset budget.

**Exit:** PASS không yêu cầu speedup tùy ý 5×/10×. Bắt buộc loại recomputation sai đã xác nhận. Không đạt thì sửa ở RA-02, không tăng timeout thay thế.

---

<a id="ra-03"></a>
## 7. RA-03 — Memory, retention, fast routes và profiling thực

### Mục tiêu

Không prepare/copy/retain dữ liệu dư; candidate search lấy output gọn, selected deployment vẫn có trace đủ audit. Đo runtime/RSS của đường thực tế trước khi mở nhiều cutoffs/cells.

### Công việc bắt buộc

**RA03.1 — Lazy `PreparedAccount`.** Loại eager full-frame preparation không được sử dụng. Resolve account start/end trước khi pack engine arrays; validate/sort/dedup theo data contract một lần, không lặp ở từng candidate. Giữ indicator history riêng với account execution window và absolute↔relative index mapping có test. Không giảm warmup tùy ý; recursive indicator warmup phải theo algorithm/convergence protocol.

**RA03.2 — Immutable prepared inputs.** Reuse read-only market arrays giữa candidates khi engine API support và không mutate. Một candidate vẫn có account/strategy state riêng. Cache deterministic feature blocks theo true parameter dependencies; tránh một giant DataFrame copy cho mỗi slice. Có thể dùng `.npy`/memmap read-only nhưng phải đo copies ở boundary; memmap không tự làm Python/native conversion zero-copy. [S2]

**RA03.3 — Retention tiers.** Dùng capabilities thật của pinned QuantBT; tên tiers dưới đây là lab policy, không phải API kwargs đã tồn tại:

| Policy | Giữ bắt buộc | Không giữ vô ích |
|---|---|---|
| `TRIAL_SCALAR` | Full trial metadata/status, raw objectives, support counts, actual-route/provenance, costs/engine counters | Redundant Python object per bar |
| `CANDIDATE_COMPACT` | Required return/equity observations, exposure/cost and report support cho targets/metrics đã đăng ký; trace references | Toàn audit trong RAM khi không dùng |
| `SELECTED_AUDIT` | Orders/fills/rejects/amends/cancels, account invariants, version/activation lineage và reconstructable path | Duplicate copies của cùng trace |

Giữ all trial lifecycle ở mọi tier. Stream/chunk disk output nếu engine cho phép; nếu thiếu sink, reducer ngoài engine chỉ được xử lý **actual financial events**, không mô phỏng lại fills. Profile native retention bên trong: streaming Python output không chữa được native object accumulation còn tồn tại.

Selected audit rerun dùng same initial state/data/params/economics/seed; audit rerun không được chọn lại winner. Ít nhất audit selected + deterministic nonwinner cases trước freeze; không chứng minh toàn ranking chỉ từ một winner.

**RA03.4 — Compute một lần, đọc metrics nhiều lần.** Một candidate run có thể cung cấp các temporal subwindow metrics theo contract đang dùng. Không đổi reset-account objective thành slicing continuous account nếu semantics khác. Bootstrap/report/rank analysis phải dùng stored outputs, không rerun financial engine mỗi statistic.

**RA03.5 — Route qualification thực.** A-SC ưu tiên thử fast target/pct_equity equivalent; A-HMA kiểm stop/gap/technical exit; A-VWAP amendment/corrective paths; A-HASH partial ladder. Profile route tương đương, không KPI “bao nhiêu % cells vectorized”. Không tạo coarse-price surrogate làm objective final. Route không equivalent vẫn có thể được nghiên cứu riêng sau owner approval, không tại primary phase này.

**RA03.6 — Giảm callbacks đúng semantics.** Deterministic indicator computation vectorize/precompute causal; pack arrays một lần. Không bỏ event callback có khả năng nhận fills/order lifecycle. Khi fill-dependent, giữ actual feedback hoặc dùng engine-native protocol đã có; không đưa custom simulated positions vào adapter để giảm crossing.

**RA03.7 — Resource profiler và worker budget.** Đo load/prepare/feature/engine/selector/serialization từng stage, account runs, visited bars, callbacks, CPU, wall, peak RSS/process-tree memory, output bytes, cold/warm work. Dùng resource isolation hiện có. Initial 1 worker; chỉ tăng trong owner-approved allocation và có aggregate-memory test. Giữ native/BLAS pools theo core quota; không oversubscribe mọi tầng. TPE trong một primary study giữ sequential reproducible contract. [S1]

**RA03.8 — Memory acceptance.** Pre-register một target headroom, khuyến nghị peak process-tree memory ≤80% actual cap trên representative fixture; đây là kỹ thuật margin, không phải guarantee mọi dataset. Lưu slope retained memory qua repeated candidate runs để tìm growth. Nếu vượt cap, giảm duplicate objects/retention/copies; không lén giảm thời gian train, bỏ fees hoặc cắt protection resolution. Nếu capability/resource vẫn không đủ: BLOCKED với measured evidence.

### Tests và benchmark

- **M01:** full preparation không xảy ra nếu chỉ window runner được dùng; data preparation counters đúng.
- **M02:** absolute/relative bars, warmup, ready/activation và fills quanh boundary parity.
- **M03:** prepared/cold inputs không cross-contaminate state giữa hai candidates.
- **M04:** scalar/compact/audit tiers cho same task giữ financial outputs và selector inputs tương đương.
- **M05:** compact account metrics tái tạo từ audit trace theo declared reducer; first return/fee không bị mất.
- **M06:** repeated runs không tăng retained objects không giới hạn; kill đúng own task khi vượt guard; completed artifacts còn recoverable.
- **M07:** fast/reference route test trên gap, stop/TP, sizing và stateful fixtures relevant; unsupported không tự fallback “native”.
- **M08:** one metric/report rerun và bootstrap dry-run không phát sinh financial engine call.

Benchmark dùng cùng data/params/economic contract và hardware quota. Test warm-cache tiết kiệm work phải report riêng khỏi raw engine throughput. Không cần rerun controls-10 đầy đủ trước khi đo representative stage.

### Artifacts và exit gate RA-03

`route_matrix`, `retention_contract`, `memory_profile`, `parity_report`, `work_profile`, `capacity_forecast`, `resource_receipts`.

- **G03-PARITY:** M01–M08 pass, không đổi primary semantics để lấy speed.
- **G03-MEM:** đại diện train candidate và deployment scope dự định đều qua actual memory test dưới cap; extrapolation phải được đánh dấu, không thay actual probe của allocation-risky stage.
- **G03-ROUTE:** pilot cell có qualified route thật. Other cells thiếu capability giữ status, không gán metric 0.
- **G03-COST:** planner có forecast từ measurements và reject job vượt envelope; không có cam kết speedup chưa đo.

**Exit:** không bắt engine rewrite. Nếu exact fast route chưa có nhưng event route đủ budget thì dùng event; nếu mọi exact route không đủ budget thì BLOCKED, không hạ financial validity.

---

<a id="ra-04"></a>
## 8. RA-04 — Mode 4 support, selector coverage và compact end-to-end controls

### Mục tiêu

Đảm bảo stock Mode 4 được gọi đúng và các outcome thiếu support không bị quảng cáo là robustness. Thay full synthetic matrix gate bằng các controls nhỏ có hypothesis kỹ thuật cụ thể, vẫn bắt được lỗi active public path.

### Công việc bắt buộc

**RA04.1 — Pin selector semantics và raw evidence.** Capture actual selected policy, raw score components, temporal returns/Sharpe/status mỗi subperiod, trade/campaign/open-position counts, top-trial count, cluster/fallback reason. One campaign dài qua nhiều periods khác one sparse isolated trade; finite coverage, exposure coverage và completed trades không được dùng thay nhau.

**RA04.2 — Reproduce F-04.** Dùng pure helper regression và public selection fixture cho một finite subperiod + năm undefined. Xác nhận path thực dùng metadata/support gì. Không sửa tất cả undefined thành 0, không loại negative finite. Keep old raw output để reproduction.

**RA04.3 — Admission policy, không viết selector thứ hai.** Nếu stock path có support failure cần guard, default implementation là lab-only post-selection admission:

```text
stock Mode 4 search/selection → giữ nguyên raw selected record
→ check training-only support theo rule đã freeze
→ đủ: admit raw selection
→ thiếu: KEEP_INCUMBENT với reason; initial chưa có thì common flat fallback
```

Không tự chọn next-best bằng optimizer riêng khi raw winner không đủ. Tên contract là `STOCK_MODE4_PLUS_ADMISSION_V1`, không gọi unchanged stock. Support thresholds phải dựa alpha horizon/holding/data và technical coverage trước paired outcomes; không hardcode một minimum trade count chung cho mọi alpha. Không áp return>0 gate nếu chưa được đăng ký như risk/eligibility policy.

Nếu cần modify engine helper để sửa đúng root cause, giữ R-03: minimal reproducer + patch proposal, không sửa installed package tự ý. Agent không được chặn mọi engineering work chờ patch nếu có admission wrapper hợp lệ; nhưng không được claim nguyên bản đã được sửa.

**RA04.4 — Search dimensions/budget.** Chọn 2–3 effective parameters từ canonical schemas, kiểm behavior witnesses. Freeze 50 attempts/cutoff default hoặc coverage revision 32–64 có lý do. Log unique feasible params/behavior, top-trial count, cluster size, fallback coverage. Vẫn fallback nhiều thì report đúng; không ép cluster bằng tăng epsilon đến khi có medoid. Geometry/selector extension khác phải là separate future study, không cộng thêm factorial ngay.

**RA04.5 — Compact control set.** Tái sử dụng fixtures đang có; bổ sung thiếu ở active runner:

| Control | Mục đích | Điều kiện PASS đúng |
|---|---|---|
| Flat-price round trip / deterministic fee | Accounting units | Actual fees/notional/equity đúng; có intentional fills trong fixture |
| Gap/HTF availability | Timing | Close-derived signal không được fill trước next eligible boundary |
| Delayed initial/search + pending campaign | Lifecycle | No backdate; incumbent giữ tới actual allowed activation |
| State permutation / model-refit-only | Regime semantics | Relabel/refit không tự thành market change |
| No-information/null world | Plumbing và inferential guard | Không leak truth; không claim edge từ one random win; không yêu cầu PnL đúng 0 |
| Action-transmission world | Treatment có thể thực thi | Params/activation/targets/orders/fills đổi theo cơ chế đã thiết kế |
| Known numeric effect on stored series | Statistical implementation | Estimator/CI code đúng với numeric reference; nhãn STATISTICAL_ONLY |

Action-transmission control phải dùng actual alpha có behavior chứng minh được hoặc explicit test-only policy. Test-only policy không thay real-alpha economic study. Có thể dùng fixture dài vừa đủ valid warmup/support; không nén 180-day market study thành vài bars rồi gọi equivalent. Không đòi known market edge trong mọi synthetic market có regime.

**RA04.6 — Public-path assertions.** Chứng minh scheduled cutoff đi vào same Mode 4 evaluator và selector đã pin, `evaluate_oos_candidates=False`, train-only objects không có future segment-end. Same-cutoff fixed-calendar harness phải match public reference. Module-level tests không thay active runner integration.

### Tests và exit gate RA-04

- **Q01:** finite/undefined/negative temporal metrics được giữ nghĩa; guard không biến one-sample thành high-confidence robustness.
- **Q02:** guard applies both CAL/REGIME; raw stock winner/reason retained; veto giữ incumbent không hidden optimizer.
- **Q03:** categorical/numeric tuning parameters có behavior effect; unknown enum raises, không collapse silently.
- **Q04:** public fixed-calendar parity, no future price/label/model access; suffix mutation không đổi quá khứ.
- **Q05:** compact controls ở trên có actual path evidence; null market không cần có lãi hoặc exactly-zero returns.
- **Q06:** zero-action real case được phân loại đúng; không ép positive-control expectation vào real sample.
- **Q07:** full trial ledger, actual route, selector support và failed/pruned lifecycle reconstructable.

**G04-VALID:** Q01–Q07 PASS cho pilot cell/primary contract. **G04-READINESS:** measured route đủ budget, exact economics và initial-history eligibility đã xác nhận. **G04-REG:** selector/admission/search settings freeze và owner duyệt trước RA-05.

**Không phải exit condition:** ranking IC>0, Sharpe>0, regime thắng synthetic CAL, hay mọi trials tạo plateau. Model đơn giản/âm không chặn technical PASS nếu đường đo đúng.

---
<a id="ra-05"></a>
## 9. RA-05 — Discovery nhỏ: 4 arms, timing đúng và calendar budget-matched

### Mục tiêu

Có phép so sánh kinh tế thực đầu tiên theo thiết kế mới trên một cell đã qualify. Trả lời được treatment thay hành động gì và đóng góp bao nhiêu, không đợi một model đạt significance trung gian.

### Công việc bắt buộc

**RA05.1 — Freeze discovery spec trước run.** Chọn pilot cell theo capability, coverage, decision/trade support và cost đã đo. Mặc định xem A-SC/BTCUSDT trước vì có integration evidence, nhưng không tự coi đủ support cho mọi cửa sổ. Rule đổi pilot phải không dựa PnL. Khóa exact window, initial selection, 4 arms, cutoff policy, seed, 50-trial budget đã duyệt, route, cost, latency và metrics. Common valid dates giữa arms; không shift riêng treatment để bỏ giai đoạn xấu.

**RA05.2 — CAL_MATCHED thật.** Từ development prefix riêng và cost profile, dự báo regime searches/model work; chọn calendar cadence trong menu đã đăng ký. Tính cả initial selection (shared hoặc charged rõ), search, model, feature và deployment work. Mỗi arm có logical budget account; cross-arm physical cache reuse không được cấp thêm unregistered searches cho bên được HIT.

Báo đồng thời `allocated`, `predicted`, `actual`, `deferred_requests`, `cache_savings`. Work mismatch ngoài tolerance vẫn có thể là valid bounded-budget experiment nhưng không được gắn equal-compute. Không match lại cadence sau nhìn realized future schedule.

**RA05.3 — Audit scheduler đang có trước khi nâng model.** Record raw state changes, eligible/confirmed changes, semantic namespace, accepted trigger, max-age reason, cooldown suppression và gap distribution. Đo tỷ lệ triggers ngay sau min-gap, so event proximity với calendar. Không tự giảm min-gap để tạo thêm biến động hay tăng cooldown để làm graph đẹp.

Model-fit, model-inference, parameter-search và activation là các clocks khác nhau. R2 fallback M0-heavy phải hiện trong báo cáo; không gọi mọi state là JM. Treatment hiện tại giữ protocol của nó trong vòng này, kể cả M0; fallback mới là revision RA-06, không đổi giữa run.

**RA05.4 — Decision-to-PnL funnel.** Mỗi opportunity có stable ID và ít nhất:

```text
observation_available / model_ready / semantic_transition
eligibility / confirmed / budget_admitted / request_time
train_cutoff / selected_time / search_ready / selected_params_digest
raw_selector / admission_decision / unchanged_params_reason
warm_indicator_ready / campaign_or_pending_order_wait
activation_time / first_affected_target / first_affected_order / first_affected_fill
incumbent_version / candidate_version / actual_costs / engine trace refs
```

Counters có denominators; distinguish request≠search≠changed params≠activation≠trade. `KEEP_INCUMBENT`, `UNCHANGED_PARAMS`, `DEFER_BUDGET`, `NO_NEW_ORDER` là outcomes hợp lệ nếu reason đúng. Không dùng count>0 như bằng chứng edge.

**RA05.5 — Actual continuous deployments.** Chạy STATIC/CAL/CAL_MATCHED/REGIME với cùng initial account và sizing. Phiên bản mới chỉ activate theo lifecycle đã freeze. Chỉ market-only schedulers mới có thể compile schedule/tape offline **sau khi causal decisions đã capture và verify**. Scheduler đọc account/strategy performance phải chạy chronology với actual state feedback, không precompute trên một account khác.

**RA05.6 — Lưu outcomes để nghiên cứu tiếp.** Thu compact account paths, selections và actual contexts; không tính thêm hàng chục horizons chưa đăng ký. Dataset từ RA-05 là development cho RA-06, không trở thành untouched confirmation của model dùng nó học.

**RA05.7 — Report đúng tầng.** Short plumbing scope chỉ cho DISCOVERY_ONLY. Economic scope đủ temporal history thì report point estimate, uncertainty descriptive theo §13, costs/risk, action divergence và scope. Primary mean-return difference phải tính trên cùng calendar; operational folds khác nhau không được so bằng fold index.

### Tests và exit gate RA-05

- **D01:** all four arms share initial selection/economics/calendar support; STATIC không bị minimum-selection-count gate chặn.
- **D02:** CAL_MATCHED không đọc future schedule/count; suffix mutation giữ pre-cutoff schedule.
- **D03:** exact parameter-selection traces cùng cutoff match reference theo contract; new params không activate sớm.
- **D04:** funnel reconstructs sample decisions, bao gồm không switch và delayed switch.
- **D05:** full account path reconciles cash/positions/fills/equity; no folded resets; daily metrics không thiếu first return.
- **D06:** costs/latencies/budgets/cache credits đúng; zero-fill/zero-change case không bị giả thành runtime error hoặc fake positive.
- **D07:** outputs đủ cả 4 arms; một arm OOM/failed không bị bỏ để chỉ report các arms còn lại như full comparison.

**G05-EXEC:** actual 4-arm run hoàn tất trong declared pilot scope, hoặc phase BLOCKED có partial artifacts. **G05-TRACE:** D01–D07 pass. **G05-LEARN:** report có kết luận mechanism, không chỉ bảng Sharpe. **G05-SCOPE:** mọi status/CI/phạm vi đủ nguồn; owner review trước RA-06.

**Không đòi regime thắng để PASS.** Nếu actions không khác trên scope đã chạy, report đúng observed zero effect và limited mechanism exercise; không kết luận mọi regime vô ích. Nếu technical failure, không chuyển thành scientific null.

---

<a id="ra-06"></a>
## 10. RA-06 — Panel tái sử dụng, refit-vs-keep target và một policy revision có giới hạn

### Mục tiêu

Đưa model về đúng câu hỏi quyết định, nhưng không mở một cuộc thi mô hình lớn. Tách lợi ích của regime/context khỏi việc chỉ biết tuổi bộ tham số. Chỉ dùng outcomes đã mature và account state có nguồn gốc đúng.

### 10.1. Hai panel khác nhau, không được trộn

**Panel A — candidate/behavior panel:** `origin × candidate × matured outcome × available context`. Tái sử dụng actual QuantBT evaluations nếu cùng initial/reset/carry contract. Bank chỉ dùng từ khi available; union candidates được khám phá ở tương lai không được hồi tố vào origins trước discovery. Cùng một candidate ID phải có params/source digest rõ.

Panel A phục vụ feature/ranking/support analysis. Không dùng column switching hoặc cộng returns của candidates để tạo policy account PnL.

**Panel B — action benefit panel:** `origin × incumbent state × causal refit result × continuation outcomes`. Cả hai branches bắt đầu từ **cùng full account/strategy state**. Hành động so sánh là:

- KEEP: giữ incumbent theo policy, không nhận một refit không thuộc branch.
- REFIT: search bằng dữ liệu tới cutoff, chờ latency và safe activation, sau đó chạy causal selected version.

Default local experiment không có additional refits trong horizon ở cả hai branches để isolate action; nếu có background policy thì phải giống và được pin ở cả hai. Account states thay do actions là kết quả hợp lệ, không cố ép equity/positions tiếp tục giống nhau.

### 10.2. Target và units

Với common equity trước decision là `E_t`, định nghĩa plain net-return action label:

\[
g_t(H)=\frac{E^{\mathrm{refit}}_{t+H}-E^{\mathrm{keep}}_{t+H}}{E_t}.
\]

Cả hai equities phải là engine outputs sau fees/slippage và valuation contract. Không trừ switching costs lần nữa nếu đã nằm trong equity. Censored outcome, failed branch hoặc thiếu future bars phải `null + reason`, không gán g=0. Waiting campaign có thể làm g gần 0 trong horizon và đó là kết quả thật.

Nếu dùng risk-penalized utility thay net return, định nghĩa/weights freeze trong development và áp same branches; không chọn utility sau khi nhìn cái nào tạo effect dương.

Target record có `origin`, `label_end`, `label_available_at`, `incumbent_policy_id`, full state digest/reference, raw selected/admitted params, branch economics, latency, terminal semantics và branch execution receipts. Label chỉ được dùng khi `label_available_at <= model_fit_cutoff`; với convention strict `<` hiện tại, giữ nhất quán hoặc version explicit.

### 10.3. Fork state bằng engine, không tự tạo oracle

Ưu tiên QuantBT checkpoint/clone-state nếu có actual supported capability và parity tests. State gồm orders/pending/protection, position/cash, fee accounting, strategy indicator/campaign state và parameter version, không chỉ equity/qty.

Nếu chưa có capability: dùng deterministic replay prefix qua QuantBT để tái tạo state tại origin, rồi branch. Chọn origins trước outcome theo timestamp/eligibility, giới hạn khoảng 8–12 cho **feasibility pilot** nếu budget cho phép. Đây không phải sample size đủ để học model đáng tin. Không tự viết stateful simulator để né chi phí replay.

Nếu không có budget tạo Panel B đủ support, implement/test panel pipeline, giữ scientific `INCONCLUSIVE_SUPPORT` và dùng calendar/current policy làm fallback. Không chạy thêm vô hạn hoặc hạ minimum support để bắt model phải fit. Optional statistical fit chỉ được SKIP theo branch đã preregister trong RA-06; mandatory engineering tests vẫn phải chạy.

### 10.4. Chọn origins không thiên lệch theo outcome

Origins dùng một grid/calendar hoặc union các **causal eligible requests** đã định trước, có rule cho control origins. Không chỉ lấy transitions thắng, không chọn anchors vì challenger có performance cao nhìn từ tương lai. Khi lấy cả event-triggered và calendar origins, lưu inclusion rule và không giả đây là uniform sample của mọi ngày.

State của panel thuộc behavior policy đã tạo nó. Action-aware policy mới có thể đi vào states khác; phải final replay bằng engine. Off-policy panel association không tự là causal effect trong thị trường hoặc guarantee policy mới tốt.

### 10.5. Model ladder có giới hạn

Giữ current JM/M0 timing policy làm reference. Trong nhánh action-aware chỉ thử:

| Model/policy | Input | Mục đích |
|---|---|---|
| `AGE_ONLY` | Parameter age và các controls đã freeze thật sự cần thiết | Đối chứng cadence/aging |
| `AGE_CONTEXT` | AGE_ONLY + một nhóm nhỏ signed economic context/regime-distance/persistence | Kiểm incremental information của context |

Tối đa **một family estimator nhỏ** có regularization/shrinkage, lựa chọn bằng inner time-series splits. Không chạy JM+HMM+HSMM+trees+deep model × mọi horizon. Có thể chọn ridge/partial-pooling đơn giản; hyperparameter grid nhỏ được ghi trước. Không dùng calibrated-probability language cho heuristic confidence/membership chưa calibrate.

Feature gợi ý để lựa chọn trong development, không buộc dùng tất cả: age, distance với training context/current incumbent context, volatility/path persistence, uncertainty/novelty, actual trailing strategy performance. Giữ sign/economic coordinates; residual-square contribution chỉ là novelty/fit diagnostic, không thay market context. Features từ performance phải lấy từ branch/account đúng, không account của policy khác.

### 10.6. Split, support và fallback

Default target horizon kế thừa 28 ngày; chỉ thêm tối đa một sensitivity horizon có lý do từ holding period/search+activation latency. Không dùng mọi 7/14/28/56 ngày để chọn kết quả đẹp. Model-input cadence, training memory và label horizon là các knobs khác nhau.

Fit scaler/feature transforms trong inner train; purge training labels kéo dài qua validation origin; respect maturity. Overlapping outcomes được đánh dấu cluster/overlap, không gọi chúng độc lập. Candidate multiplicity/seeds không nhân số market episodes.

Nếu insufficient support, fallback phiên bản mới là **KEEP_INCUMBENT hoặc calendar đã freeze**, không tự thay bằng M0 mà vẫn gọi policy không đổi. Fallback occurrence vẫn tính vào whole-policy OOS. Không chỉ báo các khoảng model đủ confidence hoặc profitable.

Primary AGE_CONTEXT contribution phải so với AGE_ONLY cùng budget, admission và execution. Không dùng AGE_CONTEXT thắng calendar chậm như bằng chứng riêng về regime.

### 10.7. Deployment controller và compute

Default policy mới `request_search` chỉ khi cheap causal score vượt rule đã freeze, cooldown/budget/quality cho phép. Nó dự báo lợi ích **trước khi** gọi optimizer. Nếu model cần biết optimized challenger quality mới quyết định, search đã xảy ra và phải charge kể cả không switch. Không coi các searches bị veto là free.

Chỉ một actionable revision được mang sang RA-07. Không tự promotion vì inner score dương; model/hyperparameters chọn bằng development, actual policy sẽ được đánh giá độc lập. RA-05 policy giữ lịch sử riêng.

### Tests và exit gate RA-06

- **P01:** panel candidate availability và label maturity; suffix/future-label mutation không đổi decisions trước cutoff.
- **P02:** state-fork/restore hoặc deterministic prefix replay parity ở origin, bao gồm pending/campaign/fill state.
- **P03:** branch g_t đối chiếu engine equities/fees, không double costs, no reset-flat shortcut.
- **P04:** origins không phụ thuộc outcome; failed/censored branches không thành zero labels.
- **P05:** AGE_ONLY vs AGE_CONTEXT cùng target, cohort, split và economic contract.
- **P06:** scaler/regularization/design selection train-only; sample counts/overlap/uncertainty truthful.
- **P07:** fallback giữ đúng policy; low support không tự tăng K hoặc fabricate confidence.
- **P08:** panel metrics/report reruns không gọi engine; state-dependent final policy không precompute từ sai account.

**G06-PANEL:** panel builder và mandatory branch tests P01–P08 pass, actual feasibility panel có provenance hoặc BLOCKED_CAPABILITY nếu engine path không thể thực thi. **G06-MODEL:** training attempt có đủ support thì chạy; insufficient support có measured disposition theo preregistered branch, không financial claim. **G06-SCOPE:** khóa tối đa một context-policy revision, hoặc KEEP_BASELINE có lý do; không chọn nhiều winners để RA-07 thử tiếp.

**Exit:** mechanical phase có thể PASS với research INCONCLUSIVE_SUPPORT sau khi hoàn thành branch được đăng ký. Missing implementation/actual required feasibility run không được đội lốt INCONCLUSIVE_SUPPORT để qua phase.

---

<a id="ra-07"></a>
## 11. RA-07 — Replication có giới hạn, falsification, decay và inference

### Mục tiêu

Đo lợi ích kinh tế, tách information timing khỏi cadence/search randomness/exposure và mô tả độ tin cậy đúng. Chỉ mở thêm phạm vi có kế hoạch, không tạo Cartesian sweep.

### Công việc bắt buộc

**RA07.1 — Freeze analysis trước replication.** Dùng primary H-BUDGET cho timing-only; nếu RA-06 action-aware được chọn, đóng riêng contrast AGE_CONTEXT−AGE_ONLY. Không gộp winner của hai câu hỏi thành một “best regime”. Primary study, selection rule, risk caps, MDE, bootstrap, seed schedule và cell expansion đều có registry trước outcomes RA-07.

Một fixed seed đầu đã dùng ở discovery; có thể thêm hai seeds đã định trước cho replication nếu budget đủ. Đây là search variability, không thêm independent market samples. Không lấy seed tốt nhất làm headline.

**RA07.2 — Một cell thứ hai trước full20.** Chọn theo rule capability/coverage/behavior và không theo PnL. Có thể là symbol khác của cùng alpha hoặc alpha khác; phải nói rõ đang kiểm transfer loại nào. Cross-symbol crypto dependence không được bỏ qua. Coverage matrix đủ20 luôn tồn tại, với `PLANNED`, `VALID`, `INSUFFICIENT_HISTORY`, `BLOCKED_CAPABILITY`, `NOT_RUN_BUDGET`, v.v.

Không thay mẫu khi cell cho kết quả âm. Mở nhiều cells hơn theo approved budget, không prerequisite rằng first cell phải significant. Full20 aggregate chỉ khi đủ planned cells hoặc đã freeze một partial-scope aggregate khác trước outcomes.

**RA07.3 — Đối chứng đủ để phân rã đóng góp.** Thực hiện thứ tự trong budget:

1. Calendar budget-matched bắt buộc, đã có RA-05.
2. AGE_ONLY khi kiểm action-aware, bắt buộc cho claim context contribution.
3. Delayed-information control: delay causal tape/decision availability theo rule fix trong development; không sửa execution fills thành giá khác tùy ý.
4. Placebo timing: seeded schedule/renewal policy có budget/cooldown được calibrate trước OOS và không đọc future market. Không circular-shift tape tương lai vào quá khứ rồi gọi live-feasible.
5. Risk/exposure attribution từ actual paths. Nếu chỉ giảm exposure mà tốt hơn thì report contribution đúng; dedicated risk-only arm chỉ thêm khi đã đăng ký, không bỏ điều kiện claim đó.

Placebo budget/seeds finite và registered. Bỏ qua placebo vì không có compute phải ghi phạm vi claim thiếu control; không gắn “information-specific edge verified”. Một schedule shuffle hồi cứu chỉ diagnostic, không primary causal comparator.

**RA07.4 — Decay D1/D2/D3 bắt buộc theo §13.** Reuse actual paths khi contract tương đương. D2 cần frozen selected params replay bằng engine, limited anchors chọn theo timestamp trước age outcome. Giữ partial/censored anchors với reason; không tạo full follow-up bằng future beyond eval end. Không average fold Sharpe thành whole-run Sharpe.

**RA07.5 — Statistics trên stored outcomes.** Daily paired mean net-return difference là primary. Bootstrap đồng bộ calendar blocks giữa arms/cells; seeds không bootstrap như markets độc lập. Recompute SR/PF mỗi resample khi báo CI; không dùng distribution của per-fold Sharpe. Engine calls cho bootstrap/statistical calibration phải bằng 0. [S4]

**RA07.6 — Support và power có nghĩa.** Số days, distinct market blocks, mature action labels, parameter versions và recurrent episodes phải báo riêng. Default old support floors như ≥365 common days và ≥12 blocks chỉ là floors, không chứng minh power. Không bắt STATIC có ≥3 selections. Conditional-regime claim cần recurrent/support appropriate; whole-path effect có thể được mô tả khi treatment ít switches nhưng uncertainty phải phản ánh mẫu.

Ước lượng precision/MDE từ paired outcome variability của development, không scale synthetic noise theo δ rồi gọi market power. Statistical null-boundary calibration kiểm estimator/type-I implementation; end-to-end controls kiểm learned pipeline. Không tự kết luận FWER 5% từ vài synthetic worlds. Nếu calibration quá thiếu thì giảm claim, không manufacture PASS.

**RA07.7 — Concentration, stability và economic scope.** Báo contribution theo calendar periods, symbol/alpha, regime-vintage/fallback, exposure, turnover, tail losses, search frequency và cost. Leave-one-period/cell-out sensitivity được định trước và report tất cả; không drop outlier cho kết quả đẹp. Relative improvement khi cả arms lỗ không thành eligibility để live.

### Artifacts và exit gate RA-07

`replication_spec`, `complete_coverage_matrix`, `paired_accounts`, `control_results`, `decay_table`, `uncertainty_results`, `multiplicity_ledger`, `sensitivity_report`, `cost_risk_attribution`.

- **G07-VALID:** all claimed comparisons có common support/economic contract và no failed arm silently omitted.
- **G07-CONTROL:** controls bắt buộc theo claim đã thực hiện; missing optional control giới hạn claim rõ, không tự nâng loại bằng chứng.
- **G07-STATS:** analytic/golden fixtures + no-engine bootstrap + synchronized blocks; CI/MDE/adjustments theo frozen plan.
- **G07-DECAY:** D1/D2/D3 đúng definitions; missing/censored follow-up không giả; all anchors lineage rõ.
- **G07-CLAIM:** research conclusion có status đúng kể cả âm/inconclusive; không outcome-based early stop/p-value shopping.

**Exit:** PASS theo completed approved scope, không theo PnL. Job bắt buộc chưa chạy vì budget thì BLOCKED hoặc owner-approved scope revision trước outcomes; không backdate revision để gọi full completion.

---

<a id="ra-08"></a>
## 12. RA-08 — Freeze thật, replay, final claims và handoff

### Mục tiêu

Bàn giao được một lab tái lập, policy/analysis package đóng băng và một kết luận đúng độ mạnh bằng chứng. Không biến repeated retrospective replay thành independent confirmation.

### Công việc bắt buộc

**RA08.1 — Immutable freeze package.** Pin code/dependency digests, actual environment/native, data snapshots/availability, alpha/schema, selector/admission, model/feature/horizon, scheduler/fallback, budgets/seeds/latency, metric/MDE/analysis plan, planned cohort và expected artifacts. Manifest không tự hash chính mình; lưu detached hash hoặc root digest không self-referential.

**RA08.2 — Verify-before-run.** Source/data/economic dependency mismatch phải fail trước economic task. Test modifying fee/feature/helper/label maturity invalidates freeze. Sửa prose/report rendering không ép rerun financial engine nếu computation contract không đổi, nhưng report version phải được pin riêng.

**RA08.3 — Ba nhãn evaluation khác nhau.**

| Nhãn | Nghĩa | Claim được phép |
|---|---|---|
| `FROZEN_REPLAY` | Cùng data cũ, cùng configs sau sửa execution/performance | Reproducibility, không independent confirmation |
| `LOCKED_RETROSPECTIVE_EVALUATION` | Policy khóa trước lượt chạy nhưng interval đã có lịch sử được xem/sử dụng | Kết quả historical với contamination disclosure |
| `PROSPECTIVE_FROZEN_EVALUATION` | Future eligible observations/decisions/outcomes thật sau freeze, chưa được dùng thiết kế | Có thể independent confirmation nếu đủ support và contracts |

Không có fresh/matured observations trong phiên thực hiện thì **không chờ vô hạn và không fake future results**. Hoàn tất engineering/freeze/replay/report, đặt prospective `NOT_RUN_NO_ELIGIBLE_NEW_DATA` và overall `TECHNICALLY_COMPLETE_RESEARCH_UNCONFIRMED`. Đây là completion branch được cho phép của RA-08, không phải scientific PASS.

Guide không tự tạo live process/cron hay hứa chạy tương lai. Việc chạy prospective mới là một authorized run sau đó, chỉ trên data đủ điều kiện; không cấp API trading/live permission.

**RA08.4 — Confirmation không chọn lại policy.** Dữ liệu confirmation chỉ vào những update mà **learning rule đã freeze** cho phép theo chronology. Không cấm online retrain causal đã đăng ký, nhưng không được đổi algorithm/hyperparameter policy/scheduler sau nhìn kết quả. Bug fix có ảnh hưởng economics phải invalidate affected comparison và tạo version/re-evaluation scope mới; không giữ cùng untouched claim.

**RA08.5 — Final claim gate.** Áp §13. Không dùng strong-edge headline nếu chỉ có một rank-IC diagnostic hoặc pilot plumbing. Report primary effect/CI/MDE, absolute strategy performance, risk, cost, scope, contamination, sensitivity và independent-evaluation status. Không claim current JM tốt nếu actual policy chủ yếu fallback.

**RA08.6 — Handoff đủ chạy lại.** Gồm current branch/commit/worktree diff, verified CLI commands, env pin, artifact locations, budget remaining, freeze manifest, decisions, closed/open issues, replication commands và những gì không được suy ra. Không có “TODO critical” nhưng status COMPLETE; dependency bị block phải ghi rõ authority cần quyết định.

### Tests và exit gate RA-08

- **Z01:** freeze verifier phát hiện missing/tampered/stale artifacts, không self-hash sai.
- **Z02:** frozen replay tái lập financial outputs trong registered tolerance; reusing verified computations có lineage.
- **Z03:** consumed interval không thể được gắn prospective/untouched bởi đổi run ID.
- **Z04:** report sinh từ artifacts, handles null/undefined/partial scope và no-new-data branch đúng.
- **Z05:** final guide/runbook commands đã được kiểm `--help`/schema và dry-run; không có fictitious CLI/API.
- **Z06:** protected paths unchanged bởi triển khai; scoped commits/remaining budget/owner handoff đầy đủ.

**Exit:** technical PASS + final scoped research status + owner review. Nếu prospective chưa có data, dùng completion branch ở RA08.3; không claim economic confirmation. Nếu reproduction thất bại thì phase FAIL/BLOCKED, không “kết thúc vì bài toán khó”.

---
<a id="metrics-claims"></a>
## 13. Metric, decay, uncertainty và claim contracts

### 13.1. Hai lớp metrics

Giữ `metrics_quantbt_raw` không sửa; thêm `metrics_research_canonical` có sampling, units, provenance và reconciliation. Không coi alias/placeholder fields của một route là actual economic turnover/volatility nếu chưa verify. Agent phải xác nhận current metric implementation, không suy definition từ tên.

Canonical daily crypto returns trên account không external cashflows:

\[
r_d=E_d/E_{d-1}-1.
\]

`E_{d-1}` ngày đầu là preceding actual account mark hoặc pre-fee initial equity nếu thực sự bắt đầu account. Tính returns trước khi clip reporting window. Valid flat days giữ 0; market data gap không được auto fill 0. Money PnL của adjacent blocks phải telescope về total account PnL, compounded returns phải nối đúng; không bỏ bước equity từ boundary đầu vào.

Annualized daily Sharpe dùng cùng risk-free convention và `sqrt(365)`, sample standard deviation theo registered definition. Không dùng `sqrt(number_of_bars_in_fold)` để so các folds khác độ dài. Whole-period Sharpe tính từ whole continuous return path, không average fold Sharpes. Nonfinite/zero variance/too few observations có flags; không thay bằng 0 rồi diễn giải là estimate đáng tin.

Profit Factor phải mang definition riêng:

- `PF_return`: sum positive returns / absolute sum negative returns trên sampling ghi rõ.
- `PF_trade`: gross winning / gross losing **engine-derived trade/campaign PnL**, với fee/funding attribution, partial exits và grouping policy rõ.

Không trộn hai PF hoặc tạo financial matching engine mới để có trade PF. `NO_TRADES`, `NO_LOSS_DENOMINATOR`, `NO_WIN`, `CENSORED_OPEN_CAMPAIGNS` có encoding rõ; không thêm epsilon để giả denominator. Open campaigns vẫn đóng góp unrealized equity nhưng không thành completed trades.

### 13.2. Decay đúng đối tượng

| Loại | Cách đo | Giới hạn diễn giải |
|---|---|---|
| **D1 IS→OOS** | Cùng selected params; raw IS metrics và post-selection OOS metrics; normalize horizon | IS chịu selection bias; không là causal decay estimator không thiên lệch |
| **D2 parameter age** | Freeze cùng theta, replay liên tục qua H1/H2/H3; fixed anchors trước outcome | Time/context thay đổi cùng age; report association, không universal causal aging |
| **D3 adjacent operational folds** | Metrics theo actual active params và các segments kế tiếp | Params, dates và durations đều có thể khác; không gọi là decay cùng theta |

Return decay dùng mean daily net return hoặc equal-horizon returns, không total-return 180 ngày trừ total-return 28 ngày. Sharpe dùng signed difference, không chia ratio khi denominator gần 0/âm. PF log-difference chỉ khi cả hai dương hữu hạn và cùng definition; các cases khác giữ flags, không drop âm thầm.

D2 default horizon/anchor policy kế thừa registration đủ follow-up hoặc revision trước outcomes. Không buộc 270 ngày follow-up cho một kỹ thuật pilot vài tuần; pilot chỉ không được claim D2 complete. Reporting row tối thiểu:

```text
selection_id, theta_digest, alpha, symbol, arm, selector_contract
comparison_kind, left_window, right_window, horizon, observed_days
metric_name, metric_definition, unit, raw_or_penalized
left_value, right_value, signed_delta, validity_status
fills, campaigns_closed/open, exposure_days, support_count
regime_at_selection, regime_in_window, parameter_age, diagnostic_only
```

### 13.3. Economic threshold δ

Không tự gán “strong edge” là Sharpe +0,5 hoặc một mức bps/day tùy ý. Chưa có business hurdle owner chọn thì dùng cost-uncertainty rule đã đăng ký, được materialize từ training-only calibration và actual engine traces. Snapshot rule tham chiếu [E09]:

\[
\delta_c=\operatorname{mean}_{d\in\text{calibration}}
\sum_{j\in d}\frac{|N_j|}{E_{j^-}}\,\Delta c,
\qquad \Delta c=0.0005.
\]

`N_j` là actual fill notional; `E_{j^-}` là actual pre-fill equity; giữ flat calibration days. Scope aggregate dùng rule max across prespecified cells như registration hoặc revision explicit. Freeze numeric δ + calibration trace hashes **trước paired outcome được dùng claim**. Không lấy realized REGIME OOS turnover để chọn δ thấp.

Đây là hurdle về chi phí bất định, không tự là business requirement hoặc phí live hiện hành. Nếu no calibration fills/invalid units thì δ không materialize được; vẫn có thể chạy technical/descriptive discovery trong budget nhưng economic hurdle claim bị chặn. Không đặt δ=0 để mở gate. Khi owner chọn business hurdle, ghi riêng nguồn quyết định và freeze trước đánh giá mới.

Base net-return đã trừ phí thật theo model; δ không được trừ thêm vào path rồi lại so path với δ lần nữa. Compute CPU cost báo riêng; chỉ quy đổi vào account-return nếu có economic cost convention được owner duyệt.

### 13.4. Statistical analysis

Primary estimator:

\[
\widehat\Delta=\frac{1}{D}\sum_d
\left(r^{REGIME}_d-r^{CAL\_MATCHED}_d\right).
\]

Trên aggregate, capital weights chọn trước, cùng calendar, không average cell Sharpes. Nếu cells thiếu/coverage khác, report fixed named partial cohort; không thay weights từng ngày theo cell nào vừa có dữ liệu rồi vẫn gọi fixed portfolio.

Default bootstrap có thể kế thừa circular moving calendar blocks và seed/draw count đã pin, nhưng phải verify centering/inversion bằng numeric reference. Primary block length 28 ngày; sensitivities 7/14/56 chỉ report nếu được giữ trong new plan, tất cả cùng lúc, không chọn cái significant. Sample block unit phải phù hợp actual observation grid; panel sparse episodes không được lặp giá trị trên nhiều ngày để giả thêm observations.

Same block resample indexes cho paired arms và correlated cells. Seeds giữ cấp search randomness; không coi 20 cells × 3 seeds là 60 independent markets. Với SR/PF, recompute whole statistic mỗi resample, count invalid denominator draws; không bootstrap trade rows như iid mặc định. [S4]

Primary one-hypothesis claim mới phải đăng ký trước. Additional confirmatory claims dùng family/multiplicity đã freeze; có thể giữ Holm cho secondary family. Các previously tried models/policies có exposure ledger; multiplicity correction không làm consumed retrospective data trở lại untouched. [S3]

Khoảng tin cậy/thử nghiệm trên development chỉ là discovery evidence. Statistical calibration và bootstrap không gọi engine. Không dừng khi p vừa <0,05 trừ một sequential design được đăng ký và triển khai riêng; mặc định dùng fixed-horizon evaluation.

### 13.5. Claim gate

Với CI `[L,U]`, δ đã freeze và conditions kỹ thuật/support/risk:

| Điều kiện | Trạng thái/diễn giải |
|---|---|
| Data/execution/treatment invalid hoặc arm bắt buộc chưa chạy | `NOT_EVALUABLE`; không positive/negative economic conclusion |
| Technical hợp lệ nhưng sample/temporal support quá thiếu | `INCONCLUSIVE_SUPPORT`; có thể report descriptive numbers |
| Valid + sufficient registered support + L>δ + inferential/control/risk rules pass | `POSITIVE_WITHIN_SCOPE`; ghi retrospective/prospective và loại contribution |
| Valid + sufficiently informative interval + U<δ | `NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE` cho mức δ đã thử |
| Valid + U<0 | Thêm `UNDERPERFORMED_WITHIN_SCOPE` |
| Interval còn cắt qua δ | `INCONCLUSIVE_EFFECT`, không NO_EDGE |
| Regime hơn CAL nhưng không hơn CAL_MATCHED | Chưa có information-timing contribution riêng; cadence contribution có thể tồn tại |
| Context policy hơn AGE_ONLY sau cùng rules | Evidence context/action contribution trong scope; không tự là mọi regime/alpha |
| Cả hai arms lỗ, treatment lỗ ít hơn | Relative improvement và absolute deployment eligibility là hai câu hỏi khác |
| Chỉ fallback path được dùng phần lớn | Claim cho actual mixed/fallback policy, không riêng model JM |

Risk mặc định kế thừa registration: max drawdown deterioration absolute cap 0,02 so với comparator và same leverage/sizing cap; owner có thể chọn khác trước eval, không nới sau outcome. Báo exposure/turnover/tail loss và cost sensitivities. Nếu positive chỉ do exposure thay đổi, đặt contribution label đúng; không gọi parameter-selection/timing information edge đã tách hoàn toàn khi control thiếu.

Không dùng từ “strong” chỉ vì point estimate cao. Headline phải nêu economic hurdle, uncertainty, concentration, scope và independent-evaluation status. Live/canary/paper promotion nằm ngoài guide.

---

<a id="evidence-report"></a>
## 14. Evidence layout, executable gate và report contract

### 14.1. Logical layout, không buộc duplicate dữ liệu

```text
configs/regime_time_edge_ra_v1/
  registration.json
  protocol_migration.json
  phase_registry.json
  resource_budget.json
  metric_and_analysis_plan.json

evidence/regime_time_edge_ra_v1/
  <run_id>/
    manifest.json
    attempts/...
    gate_receipt.json
    report.md
    artifact_refs.json

handoff/
  RA_CURRENT.md
  RA_RUNBOOK.md
```

Đây là namespace đề xuất mới, phải triển khai mapping vào planner hiện có. Raw financial artifacts có thể tiếp tục nằm ở TE paths; RA manifest reference bằng path/hash/version, không copy lại hàng GB. Tất cả mutable outputs trong lab; immutable original/evidence files không bị overwrite.

CSV/Parquet/JSONL summaries là derived artifacts. Gate kiểm source-of-truth refs chứ không chỉ summary tự khai. Giữ raw history lỗi và `superseded_by` khi sửa.

### 14.2. Record gate mẫu — chưa phải PASS

```json
{
  "schema": "regime_lab.ra_phase_gate.v1",
  "phase_id": "RA-02",
  "guide_version": "RA-GUIDE-1.0",
  "registration_digest": null,
  "source_dependency_digest": null,
  "implementation_status": "NOT_RUN",
  "technical_gate": "NOT_RUN",
  "research_status": "NOT_ASSESSED",
  "required_gates": ["G02-SEM", "G02-NUM", "G02-COUNT", "G02-LEDGER"],
  "gate_results": [],
  "mandatory_tests": [],
  "actual_run_refs": [],
  "verified_reuse_refs": [],
  "measured_resources": null,
  "protected_state_before_ref": null,
  "protected_state_after_ref": null,
  "open_blockers": [],
  "owner_review": {"status": "PENDING", "decision_ref": null},
  "can_start_next_phase": false
}
```

Mẫu là contract mới phải implement/test, không phải schema CLI cũ tự hỗ trợ. Không đưa record null này vào runner như executable success. PASS receipt phải có fields resolve bằng actual artifacts; không fill `decision_ref` bằng một câu agent tự viết.

`gate_results` mỗi row có gate_id, status, test IDs, expected criterion, actual result, artifact refs và verifier version. `mandatory_tests` có command, exit code, collected/executed/passed/failed/skipped counts, log refs và dependency digest. A test presence assertion không thay kết quả runtime khi gate yêu cầu runtime.

### 14.3. Verifier phải kiểm gì?

Một phase chỉ technical PASS khi:

1. Required artifacts tồn tại, readable, hash đúng và dependencies thuộc source/config đã khai báo.
2. Required gates đủ, không duplicate ID hoặc gắn receipt sai phase.
3. Mandatory tests đã execute; không fail, no-collection, skipped hoặc xfail đối với case bắt buộc.
4. Actual financial run được yêu cầu đã có complete receipt và status hợp lệ; mocked-only không thay actual.
5. Financial data không bị silently truncated, coerced null→0 hoặc dropped failed arm.
6. Resource/safety/protected-state checks pass; không có phase-blocking unresolved issues.
7. Report sinh lại được từ same refs; claims không mạnh hơn research status.
8. Next-phase start còn cần owner approval hoặc explicit auto-advance instruction thật.

`NOT_APPLICABLE` chỉ hợp lệ với nhánh conditional đã preregister, có predicate chứng minh và coverage disposition. Không dùng nó để bỏ một gate difficult/failed. Ví dụ RA-06 model fitting khi labels không đủ được defer; tests label maturity/state-fork vẫn bắt buộc. RA-08 prospective chưa có data được pending; frozen replay vẫn bắt buộc.

### 14.4. Mẫu báo cáo bắt buộc mỗi phase

```markdown
# RA-XX — <tên phase>

## 1. Status và scope
- Technical gate / research status / owner review.
- Branch, commit, dirty diff digest; registration và guide version.
- Scope actually completed; phần chưa chạy ghi riêng.

## 2. Previous findings và thay đổi
- Finding ID → current source location → before → after.
- Những phần đã đúng được reuse, không viết lại.
- Methodology/economic changes, cache invalidation và affected claims.

## 3. Actual execution
- Commands/interpreter/source versions; actual route.
- Data windows/coverage/initial state; attempts, not-run/failed reasons.
- Tests collected/run/pass/fail/skip; raw log/artifact references.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |

## 5. Correctness và causality
- Public-path assertions, suffix tests, fees/fills/equity, warmup/activation.
- Undefined metrics, partial scope và parity differences.

## 6. Runtime và memory
- New engine accounts/visited bars/callbacks, cache hit/miss/reuse.
- Cold/warm wall/CPU/peak process-tree memory/output bytes.
- Charged work/remaining budget; forecast error và lý do.

## 7. Scientific result và khả năng kết luận
- Technical-only hoặc actual comparison; effect/CI/MDE khi có.
- Evidence có thể chứng minh điều gì, chưa chứng minh điều gì.
- Contribution: cadence/context/exposure/selector/unknown.
- Null/negative/insufficient-support được giữ nguyên.

## 8. Blockers/debt và quyết định
- Mỗi blocker có cause, scope, attempted fix, evidence, owner action nếu cần.
- Không có P0/P1 liên quan phase chưa xử lý mà vẫn ghi PASS.
- Work có kế hoạch ở phase sau không bị gọi giả là “đã hoàn tất”.

## 9. Reproduction, commit và handoff
- Verified commands, data/environment refs, freeze/reuse refs.
- Protected trees before/after; files changed; scoped commits; no unauthorized push.
- Next permissible action; WAITING_OWNER_REVIEW hoặc explicit authorized continuation.
```

Đây là template cho agent, không yêu cầu user tự điền. Agent phải tự lấy values từ logs/ledger, không viết “tests pass” chung chung. Có thể report gọn nhưng không bỏ required evidence fields.

### 14.5. Issue/deviation protocol

Mọi deviation có `issue_id`, `discovered_in_phase`, `source/contract impacted`, `severity`, `reproducer`, `proposed_fix`, `retest`, `resource impact`, `approval_required`, `disposition`.

P0: safety, leakage, accounting, wrong treatment, invalid reuse hoặc false claim. P1: missing mandatory execution/retention, OOM/infeasible pipeline, support falsely presented as robust, gate bypass. P2: nonblocking diagnostics/docs/performance opportunity ngoài exit scope. Không đổi severity để đóng phase.

Nếu lỗi thuộc engine protected: report dependency và patch proposal, không tự sửa. Nếu owner từ chối extension, đóng scope/defer bằng approval thực; không báo full intended study complete.

---

<a id="cli"></a>
## 15. CLI và cách vận hành cho agent

### 15.1. Lệnh có trong snapshot, phải verify lại trên host

Các lệnh dưới đây đã có dạng tương ứng trong `scripts/run_time_edge.py`/`handoff/TE_CLI_RUNBOOK.md` của snapshot [E10]. Chúng không chứng minh RA spec schema đã được hỗ trợ. Đọc `--help` và current planner trước khi đưa spec mới vào.

```bash
cd /root/bobby/pool_alpha/lab_regime_model_quantbt
bash scripts/te.sh --help

# Không tự stage/clean/reset; chỉ đọc hiện trạng.
git branch --show-current
git rev-parse HEAD
git status --short

git -C /root/bobby/pool_alpha/quantbt status --porcelain
```

Preflight/coverage output phải là path mới trong allowed evidence root, không overwrite artifact cũ. Coverage của legacy R01 chỉ là tham chiếu nếu RA evaluation window khác; planner phải dùng actual RA spec.

```bash
# Các biến phải trỏ tới records đã tạo/verify trong phase, không phải template chưa resolve.
: "${PREFLIGHT_OUT:?set a new allowed preflight output path}"
: "${COVERAGE_OUT:?set a new allowed coverage output path}"
bash scripts/te.sh preflight --output "$PREFLIGHT_OUT"
bash scripts/te.sh coverage --output "$COVERAGE_OUT"
```

Sau khi planner đã hỗ trợ/validate registration RA và phase prerequisite:

```bash
: "${RUN_ID:?set the approved run id}"
: "${SPEC:?set the validated RA spec path}"
: "${ALLOCATION:?set the existing approved allocation path}"
bash scripts/te.sh plan --run-id "$RUN_ID" --stage custom \
  --spec "$SPEC" --allocation "$ALLOCATION"

# JOB là đường dẫn thực planner vừa trả về; không suy bằng tên file đoán.
: "${JOB:?set the verified job path returned by the planner}"
bash scripts/te.sh run --job "$JOB" --max-tasks 1
bash scripts/te.sh status --run-id "$RUN_ID"
```

`--max-tasks 1` dùng để kiểm một task/checkpoint, không giảm total trial/search budget đã freeze. Không gọi `_worker` trực tiếp để bypass isolation/planning/ledger. Tất cả code/spec unresolved placeholders phải bị planner reject trước run.

Stop/resume có sẵn, chỉ tác động own run:

```bash
bash scripts/te.sh stop --run-id "$RUN_ID"
# Chỉ resume sau khi verify source/semantic identity và còn budget.
bash scripts/te.sh run --job "$JOB" --resume --max-tasks 1
```

Không retry vô hạn lỗi deterministic. Technical fix tạo superseding job với relevant cache invalidation; transient retry vẫn charge ledger. Giữ failed attempts. Không lấy historical 70h envelope làm quyền chạy tiếp nếu remaining budget đã hết.

### 15.2. Những chức năng mới agent phải làm, không được giả đã có

RA phase registry, source-scoped receipt verifier, migrated scientific gates, 4-arm RA spec, action-panel runner và final RA report mapping là **new integration work**. Tái dùng implementations hiện có; thêm thin extension có tests khi thiếu. Chọn naming theo repo, không buộc tạo API đặc biệt chỉ để giống tài liệu.

Nếu thêm `scripts/verify_ra_phase.py`, đây là tên đề xuất; agent phải implement/help/test trước khi đưa lệnh ấy vào actual runbook. Final runbook chỉ giữ commands đã kiểm thật.

### 15.3. Quy tắc một session

Bắt đầu bằng handoff + current gate + git/ledger status. Xác nhận phase được phép. Làm đúng subtask có dependency đã pass. Sau thay đổi chạy affected tests, update evidence/report/manifest và commit scoped. Kết thúc bằng status thật và next permitted action.

Không dành một session để viết thêm các “master plan” không có code/test. Không xóa context cũ; handoff phải phân biệt current source và historical receipts. Không lặp lại full audit hoặc full market suite mỗi khi sửa report text.

---

<a id="done"></a>
## 16. Definition of Done của toàn đợt RA

Đợt triển khai chỉ được ghi `TECHNICALLY_COMPLETE` khi:

- RA-01…RA-08 có receipts và owner decisions phù hợp; các conditional no-data/support branches được dùng đúng, không bỏ mandatory tests.
- Semantic cache tái sử dụng cross-run thật và invalidation đúng dependency; no future availability shortcut.
- Memory/retention/route có measured parity/resource proof; representative actual deployments không OOM trong scoped allocation.
- Mode 4 actual path, support/admission semantics và full trial lifecycle được pin; không secret selector rewrite.
- Có four-arm real-alpha discovery đúng accounting, CAL_MATCHED, action lineage và scope.
- Action-aware panel/model branch đã thực hiện tới mức preregistered support/capability cho phép; không fake fitted model khi labels thiếu.
- Replication/decay/statistics/controls đúng claimed scope; all missing cells và consumed data có disclosure.
- Freeze/replay/runbook/report verification hoàn tất; prospective result chỉ khi data thực và mature.
- Không có unresolved P0/P1 thuộc completed scope; protected repos/data/services không bị agent thay đổi; no unauthorized push.

Các trạng thái kết thúc nghiên cứu được phép gồm:

```text
TECHNICALLY_COMPLETE_RESEARCH_UNCONFIRMED
VALID_SCOPED_POSITIVE_EVIDENCE
VALID_SCOPED_NO_MEANINGFUL_IMPROVEMENT
VALID_SCOPED_INCONCLUSIVE
BLOCKED_WITH_REPRODUCIBLE_EVIDENCE
```

`BLOCKED_WITH_REPRODUCIBLE_EVIDENCE` là bàn giao blocker có giá trị, **không phải technical completion**. Full20/independent confirmation/live applicability chỉ được claim khi evidence tương ứng thực có.

> **Điều agent phải chứng minh không phải “đã chạy nhiều tests” hoặc “đã làm model phức tạp hơn”. Phải chứng minh phép so sánh đúng, treatment thực sự được triển khai, computations không bị lặp vô ích, mọi kết luận có scope/uncertainty, và người khác có thể tái hiện quyết định từ artifacts.**

---

<a id="sources"></a>
## 17. Nguồn và truy vết

### 17.1. Evidence nội bộ

`[E01]`…`[E08]` là các sections trong `REGIME_MODE4_CORRECTIVE_REVIEW_VI.md` (audit ngày 18/09/2026). Audit ghi rõ source-confirmed, artifact-reanalysis, probe/test và những gì chưa chạy; không dùng nó như certificate current remote HEAD.

| Ref | Source để agent đối chiếu |
|---|---|
| E01 | `time_edge/execution.py:63–90,129–207,390–438`; `experiments/dynamic_fold_provider.py:225–265`; `reports/time_edge_validation_v4/te02-pilot-09-report.md` |
| E02 | `configs/time_edge_validation_v4/r01/model_protocol.json`; `time_edge/model.py`; `data/panel.py` |
| E03 | `evidence/time_edge_validation_v4/te03-r2/`; audit section E03 và `audit_results.json` |
| E04 | `time_edge/schedule.py:20–86`; diagnostic replay trong audit; `host-emissions-03.json` |
| E05 | `time_edge/pipeline_controls.py`; `time_edge/compute_cache.py`; cross-run comparisons controls08/09/10 |
| E06 | `time_edge/execution.py:210–306`; controls-10 attempt ledger/stderr; audit E06 |
| E07 | `time_edge/execution.py:309–388`; snapshot `quantbt_candidate/quantbt/walkforward.py:4070–4125,4369–4410`; binding R01; audit E07 |
| E08 | `time_edge/controls.py`; statistical calibration artifacts; audit E08 |
| E09 | Original ZIP `configs/time_edge_validation_v4/r01/execution_contract.json`, `evaluation_windows.json`, `statistical_analysis_plan.json`; đọc bổ sung khi soạn guide |
| E10 | Original ZIP `scripts/run_time_edge.py`, `handoff/TE_CLI_RUNBOOK.md`, `handoff/TE_PHASE_PLAN_V1.md`, `handoff/TE_MASTER_PLAN_V1.json`; đọc bổ sung khi soạn guide |

Source line numbers thuộc snapshot, có thể đổi ở host. Ghi hashes/mapping thực tại RA-01. Không dùng `quantbt_candidate` làm imported authority chỉ vì source audit nằm đó; distribution/module origins của runtime phải được xác nhận.

### 17.2. Tài liệu kỹ thuật tham khảo

Các tài liệu dưới đây hỗ trợ nguyên tắc phương pháp/kỹ thuật, **không cấp phép upgrade dependency lên version website đang hiển thị**. Không dùng nghiên cứu của thị trường khác như bằng chứng edge cho lab.

**[S1] Optuna official FAQ — reproducibility, storage/resume, trial failures.** Parallel optimization có nondeterminism; fixed seeds còn đòi deterministic objective. Giữ same-version state và verify resume contract.

```text
https://optuna.readthedocs.io/en/stable/faq.html
Accessed: 2026-09-18
```

**[S2] NumPy official `memmap` reference.** Memory mapping cho phép truy cập từng phần file; không bảo đảm mọi downstream operation không copy hoặc tiết kiệm peak memory.

```text
https://numpy.org/doc/stable/reference/generated/numpy.memmap.html
Accessed: 2026-09-18
```

**[S3] Cawley & Talbot (2010), JMLR — On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation.** Finite-sample model-selection criterion có thể bị overfit; cần phân biệt development selection với independent assessment.

```text
https://www.jmlr.org/beta/papers/v11/cawley10a.html
Accessed: 2026-09-18
```

**[S4] Ledoit & Wolf (2008) — Robust performance hypothesis testing with the Sharpe ratio.** Nghiên cứu đề xuất robust/time-series bootstrap inference cho so sánh Sharpe; guide không coi một iid test là mặc định đúng cho financial returns.

```text
https://www.ledoit.net/jef2008_abstract.htm
Source: author abstract, Journal of Empirical Finance (2008)
Verified via indexed primary-source abstract: 2026-09-18
```

**[S5] Yizhan Shu, Chenyu Yu & John M. Mulvey (2024) — Downside Risk Reduction Using Regime-Switching Signals: A Statistical Jump Model Approach.** Chỉ tham khảo cơ chế regime/risk. Không phải bằng chứng direct cho timing-only crypto WFO; không cần làm lại paper để đóng các phase.

```text
https://arxiv.org/abs/2402.05272
Accessed: 2026-09-18
```

### 17.3. Phạm vi đã làm khi soạn guide

Đã dùng audit corrective có sẵn, đối chiếu thêm registration/CLI trong ZIP và tài liệu phương pháp gốc để soạn specification. **Không chạy mới RA implementation, không chạy full native market backtest, không sửa repo/engine/production của người dùng.** Những IDs, artifacts và functions đánh dấu mới là yêu cầu cho agent triển khai, không phải features đã tồn tại hoặc PASS receipts.

### 17.4. Hash của các nguồn đọc bổ sung trong ZIP

Các hash sau xác nhận bytes tham chiếu khi soạn guide; không chứng nhận current host chưa thay đổi.

| Source | SHA-256 |
|---|---|
| `configs/time_edge_validation_v4/r01/execution_contract.json` | `bdc1309f2220686ed5feccf1d524dab03207df4900642e24f71ba429d41d3d34` |
| `configs/time_edge_validation_v4/r01/evaluation_windows.json` | `529ed66ae064d6253d0a9ae0ec8312ab70f760ec49f5da7a2214902886a23819` |
| `configs/time_edge_validation_v4/r01/statistical_analysis_plan.json` | `7a64f0d3c1a24d20fa838a40b2060ec90b2e28d8090bf102f1f354a118048cca` |
| `scripts/run_time_edge.py` | `b40f1a981e0c1ba16e7b7b429233d04b79e306c6c778e20cc9f68ebb7940b927` |
| `handoff/TE_CLI_RUNBOOK.md` | `355b48fd5974738dc57ce48ac89bde79b9085343846390063ec4dc3f8d443782` |
| `handoff/TE_MASTER_PLAN_V1.json` | `635b379a74fe899472670e87d97c240c9473c4b634309abf755c26298ff88a43` |
