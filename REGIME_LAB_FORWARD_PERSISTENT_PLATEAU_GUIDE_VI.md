# REGIME-LAB — FORWARD-PERSISTENT PARAMETER PLATEAU

## Guide triển khai, chạy nghiên cứu và cập nhật theo evidence

**Phiên bản:** FP-GUIDE-1.0  
**Ngày:** 22/09/2026  
**Repository:** `BobbyAxerol/regime-lab`  
**Phạm vi:** research lab, tiếp tục implementation hiện có; không xây lại backtest engine.  
**Namespace mới:** `FP-01` → `FP-10`  
**Trạng thái:** đặc tả triển khai và nghiên cứu; chưa phải bằng chứng các phase đã hoàn thành.

> **Nhiệm vụ chính**
>
> Khám phá tham số IS đủ sâu; học từ những lần kiểm định tiến về phía trước trong lịch sử; chọn vùng tham số có khả năng giữ hiệu quả tốt hơn khi sang OOS; sau đó đo phần đóng góp riêng của regime.
>
> Không đặt nhiệm vụ “phải làm cho regime thắng”. Phải tạo phép thử có khả năng phát hiện lợi ích nếu tồn tại, nhận diện giới hạn dữ liệu và loại trừ một mức lợi ích cụ thể khi bằng chứng đủ mạnh.
>
> **Sau mỗi lần chạy và mỗi lần nâng cấp:** lưu evidence bất biến, viết báo cáo mới từ evidence, cập nhật trạng thái hiện hành và ghi rõ điều gì thay đổi so với lần trước. Không chỉ báo cáo khi kết quả tốt.

### Điều hướng

[Quy tắc](#rules) · [Research contract](#research-contract) · [Chronology](#chronology) · [Search](#search) · [Selector B](#selector-b) · [Selector C](#selector-c) · [Decay](#decay) · [Compute](#compute) · [Phase map](#phase-map) · [FP-01](#fp-01) · [FP-02](#fp-02) · [FP-03](#fp-03) · [FP-04](#fp-04) · [FP-05](#fp-05) · [FP-06](#fp-06) · [FP-07](#fp-07) · [FP-08](#fp-08) · [FP-09](#fp-09) · [FP-10](#fp-10) · [Run reports](#run-reports) · [Upgrade rules](#upgrade-rules) · [Current guide](#current-guide) · [Evidence/gates](#evidence-gates) · [Nguồn](#sources) · [Definition of Done](#done)

---

## 0. Cách sử dụng guide

### 0.1. Thứ tự hiệu lực

Áp dụng theo thứ tự:

1. Chỉ dẫn mới, rõ ràng của Bobby.
2. Guide này trong phạm vi nghiên cứu forward-persistent plateau.
3. Economic, causality, safety và data contracts đã được xác minh.
4. Registration tương ứng với từng run.
5. Các guide LAB/RF/TE/RA trước đây ở những phần không bị thay thế.

Guide này **thay đổi trọng tâm nghiên cứu**, không xóa lịch sử nghiên cứu timing-only hoặc sửa những run cũ thành hợp lệ.

### 0.2. Nguồn bắt buộc đối chiếu

Agent phải đọc:

- `REGIME_LAB_RA_FUP05_OBJECTIVE_REVIEW_2026-09-22_VI.md`.
- `REGIME_LAB_MODE4_CORRECTIVE_AGENT_PHASE_GUIDE_VI.md`.
- Handoff, registration, report và attempt ledger mới nhất trên working copy.
- Source hiện đang được các runner gọi.
- Package/native distribution thực sự được import.

Audit mới nhất đã ghi nhận các vấn đề về calibration dùng tương lai, admission hậu kiểm, cửa sổ thống kê và D1 khác economic contract. Đây là các finding phải được map sang code hiện tại, không được bỏ qua vì đã có receipt PASS. Nguồn đối chiếu: [I1, A03–A06](#source-i1).

### 0.3. Branch và phiên bản nguồn

Bobby đã cho biết kết quả được merge vào `main`. Vì vậy:

- Không mặc định `mode4-corrective` cũ vẫn là nguồn mới nhất.
- Ghi actual branch, commit, dirty diff và untracked inventory tại thời điểm bắt đầu.
- Không suy ra commit từ tên ZIP hoặc tên thư mục.
- Không checkout/reset đè lên công việc đang dở.
- Làm việc trong branch/worktree lab được phép; có thể dùng tên `research/forward-persistent-plateau-v1` nếu phù hợp trạng thái Git và quyền đã cấp.
- Không tự push, merge, rebase hoặc sửa protected repository.

### 0.4. Các tên mới trong guide

Các tên như `ForwardLedger`, `FP_SELECTOR_V1`, `FP_CONTEXT_V1`, `FP_CURRENT.md` và các CLI ở phần cuối là **logical contracts cần triển khai hoặc map vào hệ thống hiện có**.

Không được giả định chúng là API QuantBT đã tồn tại.

Không tạo một orchestration platform hoặc financial simulator mới để thực hiện guide.

---

## 1. Câu hỏi nghiên cứu và thiết kế so sánh

### 1.1. Ba câu hỏi chính

#### H-SEARCH — Search budget

Khi tăng mức khám phá IS, stock Mode 4 có tìm được vùng tham số tốt hơn và giữ hiệu quả OOS tốt hơn không?

#### H-PERSIST — Forward persistence

Với cùng candidate pool, lựa chọn dựa trên lịch sử forward performance và decay có tốt hơn selector stock không?

#### H-REGIME — Incremental regime information

Với cùng phương pháp forward-persistent selection, thêm regime/context có cải thiện khả năng giữ hiệu quả so với không dùng regime không?

**H-REGIME là câu hỏi chính về regime trong chương trình này.**

### 1.2. Ba arms chính

| Canonical ID | Selector | Regime/context | Timing |
|---|---|---|---|
| `A_M4` | Stock Mode 4 | Không dùng cho selection | Calendar cố định |
| `B_FP` | Forward-persistent selector | Không dùng market regime/context | Cùng calendar |
| `C_FP_CONTEXT` | Cùng family selector với B | Có context và tương tác context–candidate | Cùng calendar |

Các contrast:

```text
H-SEARCH: A_M4 ở các search budgets, chỉ calibration trên development.
H-PERSIST: B_FP − A_M4.
H-REGIME: C_FP_CONTEXT − B_FP.
```

`STATIC` có thể được giữ làm diagnostic nếu đã có implementation hợp lệ, nhưng không thay comparator chính.

**Không triển khai dynamic timing cùng lúc với selector mới.** Timing mở ở FP-09, sau khi đã phân biệt được đóng góp của search, selector và context.

### 1.3. Stock Mode 4 và extension phải có tên đúng

Contract stock tham chiếu:

```text
optimization_mode          = mode_4_is_only_robust
optimization_schedule      = per_fold_causal
candidate_selection_metric = is_only_robust
scoring_backend            = endpoint
```

Agent phải xác nhận binding trong package thực.

- `A_M4` sử dụng selector stock.
- `B_FP` và `C_FP_CONTEXT` là **selector extensions**, không được gọi là stock Mode 4 không đổi.
- Không tự thêm tên mode vào engine enum rồi giả là public API.
- Không giả metric mới thành Sharpe để đưa vào selector cũ.
- Không sửa protected engine để tiện triển khai.

Nếu mọi arms dùng chung một admission guard bên ngoài stock selector:

```text
selector_contract = STOCK_MODE4
admission_contract = COMMON_ADMISSION_V1
```

Toàn policy phải được mô tả là stock selector **cộng admission**, không phải stock nguyên bản.

Giữ raw stock winner, raw scores và raw reasons để đối chiếu.

---

<a id="rules"></a>
## 2. Quy tắc không được vi phạm

### 2.1. Engine, strategy và dữ liệu

**R01 — QuantBT là authority tài chính duy nhất.**  
Orders, fills, rejects, position, cash, fees, equity và accounting phải đến từ QuantBT. Lab được viết model, search orchestration, selectors, analysis và test oracles nhỏ; không viết simulator sản xuất thứ hai.

**R02 — Pin runtime thực.**  
Ghi package versions, module origins, native build, hashes và actual route. Các version trong snapshot cũ chỉ là baseline tham chiếu; không tự upgrade hoặc downgrade môi trường.

**R03 — Giữ alpha semantics.**  
Không bỏ stop, partial exit, amendment, campaign logic hoặc thay sizing để tăng tốc mà vẫn gọi là cùng alpha.

**R04 — Fast route phải tương đương.**  
Ưu tiên `pct_equity`, prepared/native/vectorized khi đã chứng minh tương đương timing, sizing và execution. Fill-dependent alpha dùng qualified event route.

**R05 — Không sửa protected paths.**  
Original alphas, data snapshots, sibling QuantBT repository và production services giữ read-only theo quyền thực. Không sửa site-packages trực tiếp.

**R06 — Timestamp và availability.**  
Crypto naive timestamps được hiểu là UTC; aware timestamps convert UTC giữ đúng thời điểm. Không tự cộng/trừ bảy giờ. Features HTF chỉ available sau khi bar đóng.

**R07 — Coverage thật.**  
Giữ universe dự kiến BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT và bốn alphas đã chốt. Dữ liệu primary theo convention từ 01/01/2020, nhưng chỉ sau listing, coverage và warmup thực. Không lấp dữ liệu trước listing.

### 2.2. Causality và selection

**R08 — Không dùng outer OOS để chọn tham số của chính outer fold đó.**

**R09 — Không gọi retrospective replay của một winner được tìm muộn là historical forward evidence.**

**R10 — Label chỉ dùng sau khi đã trưởng thành.**  
`label_available_at` phải trước model-fit/selection cutoff theo event-order contract đã pin.

**R11 — Candidate discovery có thời điểm.**  
Candidate được khám phá ở tương lai không được hồi tố thành candidate đã biết ở origin quá khứ.

**R12 — Admission phải điều khiển deployment.**  
`KEEP_INCUMBENT` phải giữ incumbent trong actual engine state/commands, không chỉ trong JSON report.

**R13 — Continuous account phải thực sự liên tục.**  
Không reset account ở mỗi fold rồi ghép equities thành deployment result.

**R14 — Cache không làm tham số sẵn sàng sớm hơn trong lịch sử.**  
Research runtime savings và simulated deployment latency là hai đại lượng khác nhau.

### 2.3. Scientific discipline

**R15 — Trials không phải market samples.**  
Tăng trials là tăng search coverage; tăng seeds là đo search randomness; tăng historical periods mới tăng bằng chứng theo thời gian.

**R16 — Không tối ưu decay đơn độc.**  
Decay thấp nhưng OOS utility thấp, exposure gần zero hoặc IS yếu không đủ để gọi là cải tiến.

**R17 — Không thay cấu hình theo outer outcome rồi giữ cùng registration.**

**R18 — Không chọn winner seed, winner cell hoặc winner horizon để làm headline.**

**R19 — Không biến lack of significance thành no-edge.**

**R20 — Không biến bug, OOM, missing artifact hoặc arm chưa chạy thành scientific null.**

**R21 — Không tăng complexity chỉ để tìm kết quả dương.**  
Một estimator family cho B/C trong vòng đầu; không sweep đồng thời HMM, HSMM, trees và deep models.

### 2.4. Git, resources và owner review

**R22 — Không `git reset --hard`, `git clean`, force checkout hoặc `git add .` để dọn trạng thái.**

**R23 — Commit scoped sau đơn vị việc hoàn thành. Không push khi chưa được yêu cầu.**

**R24 — Không tự tăng resource allocation.**  
Đọc quota/cgroup/worker budget thực; namespace mới không reset ngân sách đã tiêu.

**R25 — Sau mỗi phase đạt exit gate:**  
Generate report → scoped commit → `WAITING_OWNER_REVIEW`.

Không mở phase kế tiếp trước phê duyệt, trừ khi Bobby đã có chỉ dẫn auto-advance rõ ràng và được ghi reference.

**R26 — Không áp quy tắc PR/contributor riêng của Portal sang regime-lab.**

---

<a id="research-contract"></a>
## 3. Research contract phải freeze

### 3.1. Economic contract

Baseline tham chiếu từ guide trước:

```text
initial_equity              = 20,000
allocation_fraction         = 0.10 của actual equity tại entry
leverage_cap                = 1
one_way_fee_rate            = 0.0004
one_way_slippage            = 1 bp
candidate_training_days    = 180
event_execution_resolution = 1m khi strategy cần
terminal_valuation         = mark-to-market
```

Đây là **study assumptions**, không phải khẳng định phí sàn hiện hành. Binding phải được verify qua golden fills; không nhân đôi phí ở route đã nhận one-way rate. Nguồn đối chiếu: [I2, economic baseline](#source-i2).

Bắt buộc cùng contract giữa:

- Candidate IS scoring.
- Candidate standardized forward scoring.
- A/B/C deployment.
- D1/D2 comparisons tương ứng.

Những khác biệt không thể loại bỏ phải được đặt thành cohort riêng và giới hạn claim.

### 3.2. Research defaults mới

| Thành phần | Giá trị khởi đầu |
|---|---|
| Tuning dimensions | 2–3 tham số có tác động hành vi thật |
| Search-space size | Khoảng 1.000 tổ hợp nếu phù hợp schema; không ép mọi alpha giống nhau |
| Search-budget checkpoints | 32, 64, 128, 256 |
| Budget ứng viên cho primary | 128 attempted search trials/cutoff |
| Independent probe budget | Tối đa 32 evaluations/cutoff, ghi riêng |
| Candidate training memory | 180 ngày |
| Forward label horizon | 28 ngày nếu đủ support cho alpha |
| Historical archive | Mở rộng theo chronology; không giới hạn bằng 180 ngày training |
| Outer study | Mục tiêu khoảng 26–39 blocks 28 ngày khi coverage cho phép |
| First cell | Theo capability/coverage, không theo PnL |
| Initial optimizer seed count | Một seed trong discovery; replication thêm seeds đã định trước |

**Các con số là research defaults, không phải quota đã được cấp hoặc bảo đảm statistical power.**

Agent phải:

1. Đo cost.
2. Khóa exact budget trước outcome.
3. Ghi scope nếu chưa đủ dữ liệu.
4. Không tự giảm 128 xuống 8 hoặc 180 xuống 45 ngày rồi gọi là cùng primary study.

Run 8–16 trials vẫn được phép để test plumbing/profile trong budget, nhưng mang nhãn `TECHNICAL_PILOT_ONLY`.

### 3.3. Data roles

Tách:

```text
ENGINEERING_FIXTURE
DEVELOPMENT_CALIBRATION
HISTORICAL_FORWARD_ARCHIVE
LOCKED_RETROSPECTIVE_EVALUATION
PROSPECTIVE_FROZEN_EVALUATION
```

Một interval đã được dùng để thiết kế không trở lại untouched chỉ vì đổi run ID.

Dữ liệu evaluation có thể được dùng cho các update causal sau khi labels mature **nếu learning rule đó đã được freeze trước**. Điều này không cho phép sửa thuật toán sau khi xem kết quả.

### 3.4. Những quyết định phải được materialize trước primary run

```text
actual cells và exact date windows
search space + effective parameter schema
B_search và Q_probe
sampler/startup/pruning/seed policy
candidate representative-selection rule
region construction + neighborhood rule
archive inclusion + label maturity rules
B/C feature schemas và estimator family
minimum support + fallback policy
economic/activation/latency contracts
primary decay metric + OOS non-inferiority rule
economic hurdle + risk tolerances
bootstrap/analysis family
resource envelope
```

Field chưa resolve có trạng thái `PENDING_CALIBRATION`. Nó có thể không chặn unit tests, nhưng phải chặn economic job cần field đó.

---

<a id="chronology"></a>
## 4. Kiến trúc chronology: ba tầng không được trộn

### 4.1. Tầng 1 — Candidate search tại origin

Tại historical origin \(t_j\):

- Search chỉ nhận dữ liệu hợp lệ trước \(t_j\).
- Candidate IS metrics được tính trên window training đã pin.
- Candidate pool và representative subset được đóng băng.
- Không đọc forward outcome sau \(t_j\).

### 4.2. Tầng 2 — Historical forward evidence

Sau khi candidate set đã được đóng băng:

- Chạy standardized forward evaluation qua QuantBT.
- Lưu outcome.
- Chỉ cho model/selector sử dụng khi `label_available_at` hợp lệ.

Một record tối thiểu:

```text
origin_id
search_cutoff
candidate_available_at
candidate_set_hash
candidate_id / effective_params_hash
IS window và IS metrics
feature_snapshot_at_origin
region/neighborhood descriptors
forward_start / forward_end
label_available_at
forward metrics / decay
initial_state_contract
engine/economic/source digests
validity/support/status
```

### 4.3. Tầng 3 — Outer evaluation

Tại outer cutoff \(T\):

1. Lấy candidate pool được tìm trên dữ liệu hợp lệ tới \(T\).
2. Lấy historical archive chỉ gồm labels đã mature trước \(T\).
3. Fit/update B/C theo learning rule đã freeze.
4. Chọn candidate trước khi đọc outer outcome.
5. Admission và ready-time xử lý trước actual deployment.
6. Quan sát OOS.
7. Sau maturity mới bổ sung records theo registered update rule.

#### Pseudocode về thứ tự — không phải QuantBT API

```text
for cutoff in chronological_cutoffs:

    train_view = permitted_history_before(cutoff)
    archive_view = matured_records_available_before(cutoff)

    candidate_pool = common_search(train_view, frozen_search_spec)
    freeze(candidate_pool)

    descriptors = build_IS_only_descriptors(candidate_pool, train_view)
    model_B, model_C = fit_from_past_only(archive_view)

    raw_A = stock_mode4_select(candidate_pool)
    raw_B = persistent_select(candidate_pool, descriptors, model_B)
    raw_C = context_select(candidate_pool, descriptors, model_C)

    approved = apply_real_admission_before_deployment(raw_A, raw_B, raw_C)
    queue_with_registered_ready_times(approved)

    advance_each_account_with_QuantBT_and_actual_feedback()

    publish_new_labels_only_with_true_maturity_metadata()
```

Nếu outcomes được tính trước trong batch để tối ưu runtime, data-access layer vẫn phải ngăn learner đọc labels chưa available.

### 4.4. Prohibition quan trọng

Không được thực hiện:

```text
Tìm winners bằng toàn dữ liệu đến T
→ đánh giá winners trên các đoạn quá khứ đã nằm trong quá trình search
→ gọi đó là independent forward-validation.
```

Đó có thể là train replay hợp lệ để mô tả, nhưng không phải historical decision evidence.

Tối ưu nhiều lần trên validation criterion vẫn có thể overfit chính criterion đó; outer evaluation phải đánh giá toàn bộ selection procedure. Xem [S3](#source-s3).

---

## 5. Tách candidate evidence khỏi deployment evidence

### 5.1. Standardized candidate cohort

Dùng cho học forward persistence:

- Cùng initial capital tại mỗi origin.
- Cùng warmup rule.
- Cùng sizing/costs.
- Cùng forward-start/ready convention.
- Cùng horizon.
- Không phát sinh phantom positions khi warming indicators.
- Mỗi candidate được QuantBT chạy với params đã freeze.

IS replay và forward replay phải có economic semantics nhất quán. Việc reset account ở đây là **contract của candidate experiment**, không phải deployment.

### 5.2. Continuous deployment cohort

Dùng cho quyết định economic cuối:

- A/B/C giữ account riêng, liên tục theo chronology.
- Cùng initial conditions.
- Version switching tuân theo pending-order/campaign/flat rules.
- Sizing dùng equity thật của từng account.
- Actual activation có thể muộn hơn search cutoff.
- Không ép accounts tiếp tục có cùng equity sau khi actions khác nhau.

### 5.3. Hai cohort trả lời câu hỏi khác nhau

| Cohort | Câu hỏi |
|---|---|
| Standardized candidate | Cùng điều kiện ban đầu, candidate nào giữ hiệu quả tốt hơn? |
| Continuous deployment | Áp policy selection vào vận hành liên tục có tạo lợi ích không? |

Không ghép candidate return columns thành switching-account PnL.

Không gán standardized D1 cho actual deployment rồi bỏ qua thời điểm activation.

Nếu cần action-benefit `REFIT−KEEP`, phải dùng cùng full account/strategy state tại origin bằng checkpoint hoặc deterministic prefix replay. Đây là nghiên cứu phụ, không bắt buộc làm lại mọi candidate evaluation theo cách đắt nhất.

---

<a id="search"></a>
## 6. Search budget và candidate pool chung

### 6.1. TPE phải thực sự được exercise

Log ít nhất:

```text
sampler_class/version
n_startup_trials
n_trials_attempted/completed/failed/pruned
startup_vs_adaptive_trial_count
unique_effective_candidates
duplicate/reused_evaluations
ask/tell sequence
search objective và its version
```

Tài liệu Optuna 4.2.1 ghi `n_startup_trials=10` và dùng random sampling trước ngưỡng này. Agent phải kiểm tra actual version/binding, không suy từ tài liệu rằng runtime của lab chắc chắn giống. Xem [S1](#source-s1).

### 6.2. Learning curve

Trên các calibration origins đã chọn trước:

```text
32 → 64 → 128 → 256
```

Ưu tiên một sequential study với snapshots tại từng checkpoint nếu:

- Search policy không phụ thuộc vào tổng budget theo cách làm đổi prefix.
- Lower-budget snapshot chỉ sử dụng trials đã tồn tại tại checkpoint.
- Neighborhood probes cho checkpoint đó không sử dụng kết quả của trials xuất hiện sau.
- Sampler state và trial history có thể tái lập.

Không chạy bốn study từ đầu khi có thể reuse cùng prefix hợp lệ.

### 6.3. Những gì phải đo

```text
best/selected raw IS quality
temporal-support coverage
stock plateau/fallback reason
candidate/behavioral diversity
independent-neighbor fragility
historical forward utility
historical D1 và D2 khi đủ follow-up
wall/CPU/RSS/accounts/visited bars
```

Budget được chọn bằng development evidence và cost, không bằng outer winner.

### 6.4. Candidate pool A/B/C

Primary A/B/C dùng cùng `C_T` tại mỗi cutoff:

- Cùng search objective/proposal policy.
- Cùng search space.
- Cùng TPE sequence và seed.
- Cùng base trial budget.
- Không để regime arm có thêm hidden candidates.
- Không warm-start B/C bằng winners có lineage tương lai.

Search objective trong primary proposal stage vẫn là objective stock đã pin. Archive/forward labels không được âm thầm đưa vào TPE ở riêng B/C.

### 6.5. Independent probes

Probes dùng đo local fragility, không chỉ lấy mật độ top-TPE samples làm plateau evidence.

Default:

- Tối đa 32 probes/cutoff.
- Chọn bằng parameter geometry và IS-only rules.
- Giữ cả kết quả xấu.
- Ghi `probe_only=true` nếu không thuộc deployment candidate pool.
- Không bổ sung probe-only candidates vào B/C mà A không có.
- Không để probes thay đổi TPE ask/tell sequence sau lưng comparator.

Probes là compute thật, phải được tính vào work ledger.

A stock có thể không sử dụng probe descriptors. Vì vậy, B−A là đóng góp của extension cùng overhead được báo cáo, không mặc định là equal-runtime comparison.

B và C phải có cùng candidate/probe information, chỉ khác context features được đăng ký.

### 6.6. Candidate representative subset cho forward archive

Không nhất thiết forward-run toàn bộ 128 candidates ở mọi origin.

Một subset khởi đầu tối đa 16 candidates có thể gồm:

- Stock winner.
- Đại diện các parameter regions.
- Một số representatives từ chất lượng IS trung bình/thấp nhưng hợp lệ.
- Neutral controls được chọn theo seed/rule định trước.
- Current incumbent nếu nó thuộc permitted candidate universe.

Tất cả phải được chọn **trước forward outcome**.

Không chỉ giữ winners; không loại losers sau khi biết kết quả.

Log inclusion rule. Panel từ subset không được mô tả là unbiased census của toàn search space.

---

## 7. Historical forward ledger và parameter regions

### 7.1. Archive không phải bảng winners

Giữ:

- Tất cả optimizer trials và lifecycle.
- Forward outcomes của subset đã đăng ký.
- Failed/censored outcomes và lý do.
- Các candidate không được chọn.
- Raw metrics và penalized objectives riêng.
- Params/version/schema chính xác.

Outcome thiếu không bằng zero.

### 7.2. Distinct origins mới là support theo thời gian

Không được báo:

```text
12 origins × 16 candidates = 192 independent market observations.
```

Khi fit:

- Tổng weight của mỗi origin phải được kiểm soát để origin có nhiều candidates không tự chi phối.
- Candidates cùng origin được coi là clustered observations.
- Seeds/cells cùng market time không tự trở thành samples độc lập.
- Overlapping forward windows phải được đánh dấu.

### 7.3. Parameter geometry

Feature geometry phải:

- Normalize bằng search-space schema đã freeze.
- Respect integer/log/categorical semantics.
- Không dùng Euclidean average cho categories.
- Không cluster bằng future outcomes.
- Không coi region ID là universal qua mọi origin.
- Giữ raw effective parameters để map được qua phiên bản.

Behavioral fingerprints dùng cho geometry chỉ được xây từ permitted IS behavior tại thời điểm đó.

Approximate behavioral similarity không tự cho phép cache financial evaluations như exact duplicates.

### 7.4. Region representative

Ưu tiên medoid hoặc candidate thực sự đã được chấm.

Không tạo centroid params rồi deploy mà chưa đánh giá.

Một region phải có:

```text
member candidate IDs
geometry/version
medoid ID
IS quality distribution
probe coverage và fragility
behavioral diversity
historical support
forward utility/decay estimates
```

Region ít support được shrink/fallback theo policy, không được mô tả là stable chỉ vì có một candidate tốt.

### 7.5. Mapping lịch sử

Nếu current selector đưa historical descriptors về một coordinate system mới:

- Transform chỉ được fit từ information có sẵn tại cutoff.
- Có transform/version digest.
- Giữ decision-vintage records cũ bất biến.
- Không viết lại lịch sử “candidate này thuộc regime X” rồi giả là label đã biết lúc đó.

---

<a id="selector-b"></a>
## 8. Selector B — forward persistence không dùng regime

### 8.1. Mục tiêu

Chọn vùng/candidate có triển vọng OOS tốt và nguy cơ suy giảm thấp, dựa trên:

- Current IS descriptors.
- Parameter geometry.
- Neighborhood fragility.
- Historical matured forward evidence.

Không dùng signed market regime/context ở B.

### 8.2. Feature set khởi đầu

Chọn một tập nhỏ, freeze trước primary evaluation:

```text
effective normalized parameters
raw IS mean net return
raw IS risk metric
temporal finite/support coverage
neighborhood downside/fragility
activity/exposure descriptors
```

Không đưa candidate ID, absolute future dates hoặc post-OOS diagnostics thành predictive features.

Không thêm hàng chục features chỉ vì panel có nhiều columns.

### 8.3. Estimator family v1

Default đề xuất:

- Một regularized regression family nhỏ để dự báo forward mean net return.
- Ridge là ứng viên khởi đầu.
- Một grid regularization nhỏ, ví dụ `[0.1, 1, 10]` sau khi feature scaling đã chuẩn hóa.
- Lựa chọn bằng chronological matured-label validation.
- Origin-level weighting để candidates trong cùng origin không nhân support.

Đây là thiết kế cần được triển khai/kiểm chứng, không phải tuyên bố ridge tốt nhất.

Không chạy đồng thời nhiều model families trong vòng này.

### 8.4. Không dùng LOO xuyên thời gian

Với validation origin \(t_j\):

```text
train label_available_at < validation decision time
```

Không dùng mọi `j != i` làm train. Sắp xếp rows theo thời gian rồi dùng leave-one-out vẫn có thể đưa future origins vào training.

Archive mới nhất trước đó đã có dormant risk kiểu này; phải có regression test trước khi mở statistical fit. Nguồn đối chiếu: [I1, A08](#source-i1).

### 8.5. Dự báo utility và decay nhất quán

Với candidate \(\theta\):

\[
\widehat D^\mu_T(\theta)
=
\mu_{\mathrm{IS},T}(\theta)
-
\widehat\mu_{\mathrm{forward},T}(\theta).
\]

Không fit hai heads rồi xuất predicted IS, forward và decay mâu thuẫn mà không reconciliation.

Có thể dùng out-of-fold residuals để mô tả downside uncertainty:

\[
\widetilde\mu^{(b)}_T(\theta)
=
\widehat\mu_T(\theta)+e_b,
\]

\[
\widetilde D^{(b)}_{+,T}(\theta)
=
\max\left(
\mu_{\mathrm{IS},T}(\theta)-\widetilde\mu^{(b)}_T(\theta),\,0
\right).
\]

Residuals phải được tạo bởi historical chronological predictions, không lấy in-sample residuals rồi gọi là generalization uncertainty.

Đây là approximation của selector, **không tự là calibrated posterior hoặc confidence interval có coverage đã chứng minh**.

### 8.6. Eligibility và ranking

Thứ tự:

1. Candidate/economics hợp lệ.
2. Đủ support theo contract.
3. Predicted forward utility/risk đạt floor đã freeze.
4. Đánh giá decay risk và neighborhood fragility.
5. Chọn candidate/medoid thực sự đã đánh giá.
6. Common admission trước deployment.

Không chọn candidate vì decay thấp khi predicted utility quá yếu.

Default decay-risk score:

- Đủ tail support: dùng empirical/shrunk quantile của positive decay, chẳng hạn \(q=0.8\).
- Thiếu tail support nhưng đủ fit support: dùng registered mean-decay branch, ghi `TAIL_ESTIMATE_UNSUPPORTED`.
- Thiếu fit support: fallback stock/admitted incumbent theo rule.

Không tự chuyển giữa các score branches theo kết quả nào đẹp hơn.

### 8.7. Support floors

Phân biệt engineering floor với statistical confidence.

Mốc khởi đầu để freeze:

- 6–12 origins: chỉ đủ prototype/descriptive analysis.
- Model fit: ít nhất 12 distinct matured origins và chronological validation khả dụng.
- OOF diagnostics: ít nhất 8 distinct validation origins.
- Tail-quantile branch: ít nhất 20 distinct OOF origins, còn phải báo concentration/weights.

Những floor này **không bảo đảm statistical power hoặc prediction quality**.

Nếu không đạt, dùng fallback đã đăng ký; không hạ floor chỉ để model fit được.

---

<a id="selector-c"></a>
## 9. Selector C — thêm regime/context đúng chỗ

### 9.1. C phải là B cộng thông tin context

Giữ nguyên:

- Candidate pool.
- Base descriptors.
- Target.
- Estimator family.
- Inner split policy.
- Regularization-selection rule.
- Support/fallback semantics.
- Economics và timing.

Chỉ thêm tập context features đã freeze.

### 9.2. Context phải phân biệt candidates

Một model dạng:

\[
\widehat\mu(\theta,x)=f(\theta)+g(x)
\]

cộng cùng một \(g(x)\) cho mọi candidate tại một cutoff. Nó có thể thay mức dự báo chung, nhưng không tự làm thay đổi thứ hạng candidates tại cutoff đó.

Do đó, để nghiên cứu conditional parameter advantage, C phải có cơ chế như:

\[
\widehat\mu(\theta,x)
=
f(z_\theta)
+
g(x)
+
h(z_\theta,x).
\]

Trong v1:

- Chỉ thêm một số ít tương tác candidate-descriptor × context.
- Hoặc dùng regional/context shrinkage đã đăng ký.
- Không mở toàn bộ Cartesian interactions.
- Test phải chứng minh architecture có thể phân biệt candidate advantage trong một fixture có cơ chế đã thiết kế.

**Không ép real data phải tạo khác biệt để technical PASS.**

### 9.3. Context candidates

Một tập nhỏ có thể gồm:

```text
signed direction/path efficiency
volatility level/change
distance so với training context
persistence/novelty
causal JM/M0 state descriptors nếu đủ support
```

Không dùng squared residual contributions thay toàn bộ economic context.

Không gọi Jump Model cost-gap hoặc heuristic membership là probability đã calibrated.

### 9.4. Bắt buộc ghi actual model exposure

Mỗi evaluation window cần:

```text
JM observations/vintages
M0 observations/vintages
unknown/stale/ambiguous
fallback occurrences
actual decisions/activations thuộc từng model regime
```

Không lấy full-history model counts thay exposure trong study window.

Pilot cũ có giai đoạn toàn M0, nên future report không được dùng tên “JM edge” khi policy thực tế không exercise JM. Nguồn đối chiếu: [I1, A08](#source-i1).

### 9.5. Claim levels

| Context thực sự dùng | Cách gọi kết quả |
|---|---|
| Continuous economic context | Context-conditioned parameter-selection contribution |
| JM-derived features được exercise và có đối chứng tương ứng | JM-specific contribution trong scope đã thử |
| M0/JM mixed policy | Contribution của actual mixed policy |
| C fallback gần như toàn bộ về B | Policy chưa exercise context đủ; không fake regime result |

C−B dương không tự chứng minh mọi regime model có edge.

### 9.6. Không dùng realized future regime để chọn hiện tại

Realized transition trong forward window được dùng để phân tích hậu kiểm, nhưng không được đi vào selection tại origin.

Forecast transition risk từ past là feature hợp lệ nếu đã freeze và causal; future state label thực tế thì không.

---

<a id="decay"></a>
## 10. Decay và economic metrics

### 10.1. Return calculation

Với equity \(E_d\):

\[
r_d=E_d/E_{d-1}-1.
\]

Bắt buộc:

- Tính returns với preceding equity đúng trước khi clip reporting window.
- Giữ flat days hợp lệ trong evaluation.
- Bỏ warmup ngoài evaluation.
- Không coi missing market data là zero-return.
- Money PnL partition phải telescope.
- Compounded returns phải nối đúng whole path.

Intraday boundaries phải dùng đúng marks/interval convention, không lấy daily-midnight labels giả làm exact activation boundaries.

### 10.2. D1 — IS→forward decay

Canonical sign mới:

\[
D^\mu_j=\mu_{\mathrm{IS},j}-\mu_{\mathrm{FWD},j}.
\]

**Dương lớn hơn là decay xấu hơn.**

Giữ raw legacy `OOS−IS` dưới tên legacy riêng; không đổi sign âm thầm.

Metrics:

```text
D1_mean_net_return_bps_day
D1_sharpe_difference
D1_log_pf_difference khi hợp lệ
D1_positive_decay
```

IS và forward dùng cùng selected params và economic contract.

D1 vẫn chịu selection bias của IS; không gọi nó estimator không thiên lệch của “causal parameter aging”.

### 10.3. D2 — Frozen-parameter age curve

Với cùng params đã freeze:

```text
H1 = tuổi 0–28 ngày
H2 = tuổi 28–56 ngày
H3 = tuổi 56–84 ngày
```

Các horizon phải freeze theo alpha/support.

Chạy **một continuation liên tục** cho anchor nếu contract cho phép, sau đó lấy các metrics; không reset mỗi age window.

Báo:

- Performance từng age window.
- Signed decline H1→H2/H3.
- Exposure, trades/campaign support.
- Regime/context thực tế.
- Censoring/follow-up thiếu.
- Actual versus standardized-state cohort.

Không chọn anchors vì nhìn thấy decay đẹp.

### 10.4. D3 — Adjacent operational folds

Báo chênh lệch giữa các folds, nhưng ghi rõ params, market và durations có thể khác.

Không dùng D3 thay D1/D2 để chứng minh cùng vector params giữ hiệu quả.

### 10.5. Sharpe và PF

- Sharpe annualization phải cùng sampling; không dùng `sqrt(number_of_bars_in_fold)`.
- Whole-period Sharpe không bằng trung bình fold Sharpes.
- `PF_return` và `PF_trade` là metrics khác nhau.
- Trade/campaign PnL phải lấy từ engine-derived attribution đúng contract.
- Zero variance, no trades, no losses, no wins và open/censored campaigns phải có typed status.
- Không thêm epsilon để manufacture một PF hữu hạn.
- Không loại invalid PF rows âm thầm rồi chỉ báo phần còn đẹp.

### 10.6. Primary regime comparison

Tại common origins:

\[
I_D
=
\operatorname{mean}_j
\left(D^{B}_{+,j}-D^{C}_{+,j}\right).
\]

\(I_D>0\) nghĩa là C giảm positive decay so với B.

Đặt cạnh:

\[
\Delta\mu
=
\operatorname{mean}_d
\left(r^C_d-r^B_d\right).
\]

Các claim riêng:

| Claim | Điều kiện cần |
|---|---|
| Giảm decay có ý nghĩa | Uncertainty hỗ trợ \(I_D>\delta_D\), đủ validity/support |
| Giữ hiệu quả OOS không kém quá mức | Non-inferiority rule với tolerance \(\epsilon_\mu\) đã freeze |
| Economic outperformance | Uncertainty hỗ trợ \(\Delta\mu>\delta_\mu\) và risk rules đạt |
| Strong regime evidence | Có incremental comparison, effect size, uncertainty, replication và scope phù hợp |

Không dùng “không significant khác nhau” để suy ra non-inferiority.

Không gọi “decay thấp hơn” là incremental profit edge nếu OOS utility yếu hơn.

### 10.7. Ngưỡng và uncertainty

Freeze riêng:

```text
delta_decay
epsilon_OOS_noninferiority
delta_economic_return
risk_tolerances
primary statistic
confidence procedure
multiplicity family
```

Không đặt threshold sau khi xem treatment outcome.

Nếu business hurdle chưa có, dùng rule calibration đã được owner chấp nhận; nếu chưa materialize được thì report descriptive, không tự đặt zero để mở positive claim.

Paired block resampling phải giữ common time indexes giữa arms/cells. Seeds đo search randomness, không được resample như các thị trường độc lập.

Đối với Sharpe differences, tài liệu Ledoit–Wolf hỗ trợ dùng inference xử lý heavy tails/time dependence, nhưng lab vẫn phải verify implementation của phương pháp chọn dùng. Xem [S4](#source-s4).

---

<a id="compute"></a>
## 11. Compute plan: tăng chiều sâu mà không nhân công việc vô ích

### 11.1. Một search pool cho A/B/C

Không chạy ba optimizer giống nhau chỉ vì có ba selector arms.

Tạo common candidate pool một lần, sau đó chạy selector A/B/C trên pool đó.

Financial deployment vẫn là account riêng cho mỗi arm.

### 11.2. Archive incremental

Một historical origin/evaluation hợp lệ chỉ tính một lần.

Sang outer cutoff mới:

- Reuse matured records cùng semantic identity.
- Thêm origins/candidates cần thiết.
- Không rebuild toàn historical archive cho mọi fold.

### 11.3. Cache keys

Ít nhất gồm:

```text
data content/coverage/vintage digest
symbol/timeframe/window/pre-roll
alpha source + effective params
economic/execution/initial-state contract
engine/native/route/scorer version
search/probe/feature/model versions khi liên quan
```

`run_id`, output path và producer là provenance, không tự là economic identity.

Không dùng broad hash toàn repo khiến sửa README invalidate hàng nghìn backtests.

Ngược lại, sửa helper có ảnh hưởng economics phải invalidate.

### 11.4. Retention

| Lớp | Giữ gì? |
|---|---|
| Mọi trial | Params, lifecycle, objective, raw metrics, support, source refs |
| Candidate archive | Compact forward returns/metrics và reconstructable references |
| Selected deployments | Full required orders/fills/equity/activation lineage |
| Audit cases | Full trace theo contract |
| Reports | Derived summaries; không là financial source of truth |

Tránh giữ mọi per-bar Python object của mọi candidate trong RAM.

Memory mapping có thể giúp truy cập từng đoạn dữ liệu lớn, nhưng không loại bỏ các copies do operations hoặc engine bindings tạo ra; phải đo actual peak memory. Xem [S5](#source-s5).

### 11.5. Parallelism

- Giữ sequential ask/tell trong mỗi TPE study cần reproducibility.
- Parallel independent cells/seeds/tasks trong quota.
- Không parallel các stages phụ thuộc vào newly matured labels mà phá chronology.
- Không nhân workers × native threads ở mọi tầng.
- Restore sampler/RNG state đúng version khi resume.

Optuna lưu ý parallel/distributed optimization có nondeterminism; fixed sampler seed không đủ nếu objective hoặc execution order không deterministic. Xem [S2](#source-s2).

### 11.6. Cost estimator trước run

Ước lượng riêng:

```text
candidate training runs
probe runs
forward-label runs
D2 continuations
deployment accounts
model fits
report/statistics work
retry reserve
```

Không chỉ lấy `folds × trials` rồi bỏ qua probes, warmup, validation và deployment.

Không hứa speedup trước benchmark.

Bootstrap, chart rendering và metric reconciliation từ đủ stored outputs phải có **zero new engine calls**.

---

<a id="phase-map"></a>
## 12. Phase map

| Phase | Mục tiêu |
|---|---|
| **FP-01** | Pin hiện trạng, migrate scope, sửa blockers làm sai kết luận |
| **FP-02** | Common evaluator, cache, memory, runtime và lineage |
| **FP-03** | Search-space qualification và budget learning curve |
| **FP-04** | Historical forward ledger và parameter regions |
| **FP-05** | Selector B không regime |
| **FP-06** | Selector C có context/interactions |
| **FP-07** | Locked A/B/C study trên common fixed calendar |
| **FP-08** | Replication, D2, uncertainty và contribution analysis |
| **FP-09** | Secondary dynamic-timing study có điều kiện |
| **FP-10** | Freeze, replay, final conclusions và handoff |

**Không coi các phase trước đây phải làm lại từ đầu.** Reuse evidence nếu dependencies và contracts vẫn đúng.

Mỗi phase có bốn trạng thái riêng:

```text
implementation_status
technical_gate
research_status
owner_review
```

`technical_gate=PASS` không đồng nghĩa `research_status=POSITIVE`.

---

<a id="fp-01"></a>
## 13. FP-01 — Contracts, migration và validity repairs

### Mục tiêu

Biết chính xác code/runtime đang dùng và sửa các sai lệch có thể làm hỏng mọi so sánh decay tiếp theo.

### Công việc

#### FP01.1 — Inventory

Ghi:

- Branch/commit/dirty diff/untracked inventory.
- Lab interpreter và package/native origins.
- Actual resource allocation.
- Data snapshots và consumed-data history.
- Active jobs thuộc lab.
- Protected state trước khi thay đổi.

#### FP01.2 — Map audit findings

Ít nhất:

| Finding | Yêu cầu |
|---|---|
| Development ngoài window nhưng nằm ở tương lai | Enforce before-evaluation và availability |
| Admission tính sau deployment | Wire admission trước account consumes params |
| Warmup lẫn statistical window | Compute returns với prior equity rồi clip đúng |
| D1 mất first return | Boundary/partition reconciliation |
| IS/OOS sizing khác nhau | Shared economic contract |
| Verdict không trực tiếp so treatment | New claim logic dựa contrast đúng |
| LOO sử dụng future origins | Chronological matured-label split |
| Raw artifacts thiếu trong package | Export existing outputs, không thay run khác |
| Gate kiểm token/field thay hành vi | Behavioral verifier |

Disposition:

```text
PRESENT
FIXED_WITH_PROOF
SUPERSEDED_PATH_QUARANTINED
NOT_REPRODUCED_WITH_SCOPE
NEEDS_RUNTIME
```

#### FP01.3 — Migration registration

Ghi rõ:

- Primary mới: C−B trên fixed timing.
- Timing-only chuyển sang secondary.
- B/C là selector extensions.
- Trial/episode distinction.
- Decay-primary cùng OOS utility safeguard.
- Historical claims giữ bất biến.

#### FP01.4 — Tests bắt buộc

| Test | Expected |
|---|---|
| `FP01-T01` | Thay future-only emissions không đổi calibration trước evaluation |
| `FP01-T02` | Forced rejection không làm actual engine nhận candidate bị reject |
| `FP01-T03` | 100→120→108 giữ đúng hai boundary returns khi window yêu cầu |
| `FP01-T04` | Warmup ngoài evaluation không tăng sample count |
| `FP01-T05` | Same params/data/economics cho IS/forward route đạt contract parity |
| `FP01-T06` | Identical arms không cho false significant p-value |
| `FP01-T07` | Missing/stale/tampered artifacts không thể PASS |

### Exit gate

- `FP01-G-VALIDITY`: affected tests pass trên đường thực.
- `FP01-G-IDENTITY`: source/runtime/protected states đầy đủ.
- `FP01-G-MIGRATION`: old→new mapping rõ.
- `FP01-G-BUDGET`: không reset hoặc vượt quota.
- Report và owner review hoàn tất trước FP-02.

Không launch bulk search khi admission hoặc comparator chronology còn sai.

---

<a id="fp-02"></a>
## 14. FP-02 — Evaluator và reusable runtime

### Mục tiêu

Một computation hợp lệ được chạy một lần; output đủ dùng lại cho search, forward labels và report mà không đổi economics.

### Công việc

1. Map common evaluator vào QuantBT route đã qualify.
2. Phân biệt standardized candidate account và continuous deployment account.
3. Implement semantic cache/invalidation.
4. Lazy-prepare đúng windows và pre-roll.
5. Tách compact scoring retention khỏi full selected audit.
6. Ghi actual calls, bars, callbacks, wall/CPU/RSS.
7. Implement lineage từ selection đến actual activation/orders/fills.
8. Resolve simulated ready latency độc lập với cache runtime.

### Actual runs bắt buộc

- Một candidate theo route audit.
- Cùng candidate theo score/fast route dự định dùng.
- Một small multi-selection deployment có pending/activation case.
- Cross-run semantic cache reuse.
- Interrupted/resumed task nếu checkpoint là capability được dùng.

Không dùng mocked-only run thay các checks này.

### Tests và gates

| Gate | Điều kiện |
|---|---|
| `FP02-G-PARITY` | Required economics/trace parity đạt tolerance đã pin |
| `FP02-G-CACHE` | Đổi run ID không tạo evaluations mới; đổi economic dependency thì miss |
| `FP02-G-LATENCY` | Cache hit không làm simulated ready_at sớm hơn |
| `FP02-G-MEMORY` | Peak trong allocation; lifecycle measured, không leak theo số trials |
| `FP02-G-LINEAGE` | Sample selections reconstruct được actual activation/fills |
| `FP02-G-RESUME` | Resume không đổi permitted chronology hoặc sampler state |

Chưa đạt fast parity thì dùng route đúng trong phạm vi budget; không đổi chiến lược để có tốc độ.

---

<a id="fp-03"></a>
## 15. FP-03 — Search-space qualification và learning curve

### Mục tiêu

Xác định budget đủ khám phá, không mặc định 8 trials là đủ hoặc 256 trials chắc chắn tốt hơn.

### Công việc

#### FP03.1 — Parameter-effect qualification

Với từng chiều tuning:

- Type/range/step/log/categorical mapping đúng.
- Có fixture chứng minh parameter có thể thay đổi hành vi.
- Unknown values raise rõ.
- Không silent fallback collapse nhiều categories thành một.
- Không kết luận “parameter vô tác dụng” chỉ từ một đoạn real data không có tín hiệu phù hợp.

#### FP03.2 — Calibration origin selection

Chọn một số origins từ development trước outcome:

- Theo thời gian/coverage.
- Có các điều kiện thị trường khác nhau theo thông tin được phép biết.
- Không chọn vì stock có PnL đẹp.
- Không dùng primary outer test làm calibration.

#### FP03.3 — Checkpoint search

Chạy 32/64/128/256 theo sequential prefix khi hợp lệ.

Record selected candidate, region coverage, temporal support, startup/adaptive counts và costs tại từng checkpoint.

#### FP03.4 — Forward comparison trên calibration

Candidates cần replay được đóng băng trước forward outcomes.

Báo cả:

- IS improvement.
- Forward utility improvement.
- Decay.
- Incremental cost.

Không chọn budget chỉ bằng max IS.

#### FP03.5 — Freeze budget

Chốt:

```text
B_search
Q_probe
representative subset size
startup/exploration policy
pruning policy
seed policy
```

Nếu 128 chưa affordable:

- Ghi blocker hoặc đề xuất reduced-scope study.
- Không lén hạ budget trong cùng registration.
- Giảm số simultaneous cells trước khi giảm chiều sâu đã chốt.
- Owner quyết định.

### Exit gate

- `FP03-G-SCHEMA`: effective params và behavior tests đúng.
- `FP03-G-PREFIX`: lower-budget checkpoint không dùng higher-budget information.
- `FP03-G-COVERAGE`: raw/unique/behavioral coverage có số đo.
- `FP03-G-CURVE`: learning curve từ real engine outputs.
- `FP03-G-FREEZE`: budget/ranges đã freeze, owner duyệt.

---

<a id="fp-04"></a>
## 16. FP-04 — Historical forward ledger và regions

### Mục tiêu

Tạo tập bằng chứng tích lũy về việc tham số giữ hiệu quả ra sao, không dùng future-discovered winners để viết lại quá khứ.

### Công việc

1. Tạo chronological origin grid.
2. Tại mỗi origin, search từ permitted past.
3. Freeze pool, regions và representative subset.
4. Chạy candidate forward evaluations.
5. Lưu full label timing/provenance.
6. Chỉ expose matured records cho learner.
7. Build origin-weighted panel views.
8. Reuse outputs cùng semantics.
9. Report support theo origins, regions, candidates và calendar periods.
10. Không tự mở nhiều horizons.

### Bắt buộc phân biệt

```text
decision_available_record
retrospective_train_replay
future_label_not_yet_mature
matured_forward_record
censored_or_failed_record
```

### Tests

| Test | Expected |
|---|---|
| `FP04-T01` | Candidate discovered muộn không xuất hiện trong past origin |
| `FP04-T02` | Future label mutation không đổi earlier selections |
| `FP04-T03` | Representative selection không thay khi forward outcome đổi |
| `FP04-T04` | Region geometry không dùng forward performance |
| `FP04-T05` | Failed/censored labels không thành zero |
| `FP04-T06` | Một origin có nhiều candidates không tự có nhiều weight hơn |
| `FP04-T07` | Incremental rebuild không gọi engine cho records hợp lệ đã tồn tại |
| `FP04-T08` | Old decision-vintage records không bị overwrite |

### Exit gate

- `FP04-G-LEDGER`: actual archive có provenance.
- `FP04-G-CAUSAL`: maturity/discovery tests pass.
- `FP04-G-REGION`: descriptors reconstruct được.
- `FP04-G-SUPPORT`: counts trung thực; model-ready và descriptive-only tách riêng.
- `FP04-G-REUSE`: measured reuse đúng.

Thiếu số origins cho model không làm archive vô giá trị, nhưng không được gọi model study hoàn tất.

---

<a id="fp-05"></a>
## 17. FP-05 — Implement B_FP

### Mục tiêu

Kiểm tra liệu forward-persistent selection không dùng regime có cải thiện việc giữ hiệu quả so với stock selector hay không.

### Công việc

1. Implement small frozen base-feature schema.
2. Implement chronological training/validation.
3. Implement origin weights và regularization selection.
4. Generate true chronological OOF predictions.
5. Implement utility floor, decay-risk branch và support fallback.
6. Chọn evaluated medoid/candidate.
7. Wire selected proposal vào common admission.
8. Giữ raw stock comparator.
9. Log mọi reasons không đủ support hoặc không đổi params.
10. Không sửa model theo outer test.

### Required diagnostics

```text
prediction error theo origin
predicted vs realized forward utility
predicted vs realized decay
eligibility/fallback rate
region selection frequency
neighbor fragility
selected vs stock candidate difference
```

Không dùng training fit quality làm predictive evidence.

### Exit gate

- `FP05-G-SPLIT`: no future origins/labels trong fit.
- `FP05-G-MODEL`: deterministic fit, schema/version đầy đủ.
- `FP05-G-SCORE`: utility/decay algebra và units reconcile.
- `FP05-G-SUPPORT`: insufficient support đi đúng registered fallback.
- `FP05-G-ACTION`: selector output thực sự tới admission/deployment.
- `FP05-G-REPORT`: technical và scientific status tách biệt.

Không yêu cầu B thắng để technical PASS.

---

<a id="fp-06"></a>
## 18. FP-06 — Implement C_FP_CONTEXT

### Mục tiêu

Đo incremental information của context, không để C thắng vì có search budget hoặc candidate pool khác.

### Công việc

1. Reuse toàn bộ B pipeline.
2. Thêm context schema nhỏ và candidate-context interactions đã đăng ký.
3. Fit context transforms chỉ từ permitted training.
4. Ghi actual JM/M0/unknown exposure.
5. Áp cùng label target, origin weights và estimator family.
6. Kiểm OOD/support và fallback về B khi cần.
7. Freeze context family trước FP-07.
8. Không tự mở thêm model ladder.

### Tests

| Test | Expected |
|---|---|
| `FP06-T01` | Context bị disable đúng contract thì C trở về B |
| `FP06-T02` | Namespace relabel không tự thành economic change |
| `FP06-T03` | Future regime labels không vào selection |
| `FP06-T04` | Fixture có conditional parameter advantage được architecture biểu diễn |
| `FP06-T05` | Unsupported context không produce fake calibrated confidence |
| `FP06-T06` | B/C cùng candidate pool, target và base features |
| `FP06-T07` | Actual model-exposure counts match emitted records |

### Exit gate

- `FP06-G-ABLATION`: C−B là context difference đúng scope.
- `FP06-G-CAUSAL`: temporal/context tests pass.
- `FP06-G-SUPPORT`: fallback/unknown policy có actual evidence.
- `FP06-G-FREEZE`: chỉ một context-policy revision đi tiếp.
- `FP06-G-CLAIM`: không gọi generic context result là JM-specific nếu chưa tách.

C không tạo khác biệt trên real data vẫn là kết quả hợp lệ nếu execution đúng.

---

<a id="fp-07"></a>
## 19. FP-07 — Locked A/B/C study

### Mục tiêu

Chạy một phép so sánh đủ chiều sâu trên common fixed calendar, không thay đổi model, budget hoặc windows giữa chừng.

### Preconditions

- FP-01…FP-06 gates và owner approvals phù hợp.
- Exact primary window/cells/budgets/metrics đã freeze.
- Cost estimate trong allocation.
- Common economic/initial/latency contract.
- Candidate-forward và deployment metrics được tách.

### Thực hiện

1. Dùng một primary cell đã qualify.
2. Search chung tại mỗi cutoff.
3. A/B/C chọn trên cùng pool.
4. Admission trước deployment.
5. Chạy actual continuous accounts.
6. Generate standardized D1 cho selections theo sample plan.
7. Lưu full decision-to-PnL lineage.
8. Giữ whole-policy fallback periods.
9. Báo prefix progress nhưng không đổi algorithm theo prefix outcome.
10. Không dừng chỉ vì p-value vừa thuận lợi.

### Output bắt buộc

```text
common candidate pools
all trial lifecycle records
A/B/C selection records
admission and actual activation records
continuous account paths
canonical daily returns
D1 table
search/selector/model costs
fallback/context exposure
paired contrasts
scope/support/validity report
```

### Exit gate

- `FP07-G-POOL`: same pools verified.
- `FP07-G-EXEC`: cả A/B/C actual runs hoàn tất theo registered scope.
- `FP07-G-ACCOUNT`: accounting/first-return/common-window reconciliation pass.
- `FP07-G-DECAY`: D1 đúng sign/units/cohort.
- `FP07-G-COST`: logical và physical budgets rõ.
- `FP07-G-SCOPE`: không gọi short pilot là full scientific study.

Một mandatory arm OOM thì comparison BLOCKED; không bỏ arm đó để báo phần còn lại như full study.

---

<a id="fp-08"></a>
## 20. FP-08 — Replication, D2 và inference

### Mục tiêu

Phân biệt đóng góp thật với search randomness, một đoạn thị trường đặc biệt hoặc metric artifact.

### Công việc

#### FP08.1 — Replication scope

- Thêm cell thứ hai theo rule đã đăng ký, không theo PnL.
- Thêm seeds đã định trước nếu budget đủ.
- Không lấy best seed.
- Coverage matrix đầy đủ cho planned 20 cells, kể cả chưa chạy.

#### FP08.2 — D2 anchors

- Chọn anchors theo timestamp/eligibility trước outcome.
- Dùng cùng selected params trong continuation.
- Tái dùng first-horizon path nếu exact contract/prefix parity.
- Không reset ở age boundaries.
- Giữ censoring khi follow-up thiếu.

#### FP08.3 — Statistical analysis

Tính:

```text
B−A utility và decay
C−B utility và decay
OOS non-inferiority
risk/exposure/turnover changes
D2 age decline
concentration theo periods/cells
```

Engine calls cho statistics/bootstraps phải bằng zero.

#### FP08.4 — Regime contribution checks

Cần biết:

- Context có thực sự đổi candidate rankings/selections không?
- Benefit có còn sau common calendar?
- Context improvement có chỉ là market-wide offset không?
- Kết quả có phụ thuộc một origin/model vintage không?
- C thắng do conditional selection hay chỉ giảm exposure?

#### FP08.5 — Decision rules

| Bằng chứng | Disposition |
|---|---|
| Valid, decay tốt hơn và utility/risk đạt safeguard | Retention contribution trong scope |
| Valid, net utility vượt hurdle | Economic outperformance trong scope |
| CI rộng | Inconclusive effect/support |
| CI đủ hẹp loại benefit threshold | No meaningful improvement tại threshold đã thử |
| Technical invalid | Not evaluable |
| C≈B vì fallback | Context mechanism chưa được exercise đủ |

### Exit gate

- `FP08-G-REPLICATION`: planned runs hoặc authorized partial scope rõ.
- `FP08-G-D2`: frozen-parameter continuations đúng contract.
- `FP08-G-INFERENCE`: paired/dependence/degenerate tests pass.
- `FP08-G-CONCENTRATION`: không ẩn adverse periods/cells.
- `FP08-G-VERDICT`: claim không mạnh hơn evidence.

Nếu chưa có dữ liệu đủ precision, ghi rõ cần thêm bao nhiêu loại support theo cost/precision estimate; không tự chạy vô hạn.

---

<a id="fp-09"></a>
## 21. FP-09 — Secondary timing extension

### Mục tiêu

Sau khi selector được cố định, kiểm tra regime timing có thêm giá trị hay không.

### Không mở tự động

Phase này là conditional branch. Owner phải duyệt lý do, scope và budget.

Không cần bắt core study dương mới được nghiên cứu timing, nhưng phải có một giả thuyết cơ chế cụ thể; không chạy chỉ vì “chưa có kết quả mong muốn”.

### Arms

Dùng cùng frozen selector:

```text
SELECTOR_FIXED_CAL
SELECTOR_CAL_MATCHED
SELECTOR_REGIME_TIMING
```

Nếu có placebo:

- Seed/schedule-generation policy freeze trước evaluation.
- Dwell/cadence calibration dùng past hợp lệ.
- Không circular-shift future tape vào quá khứ rồi gọi causal.
- Nhiều placebo runs dùng cho inference phải có family/budget trước.

### Metrics

- Common-calendar continuous outcome là economic comparison.
- D1/D2 vẫn giữ definition.
- Dynamic operational folds không pair bằng fold index.
- Report request → search → changed params → activation → changed orders/fills.
- Compute/latency model overhead tính đủ.

### Verdict

Không được kết luận `CADENCE_ARTIFACT` chỉ vì placebo hơn một calendar chậm.

Phải so trực tiếp:

```text
REGIME_TIMING − CAL_MATCHED
REGIME_TIMING − PLACEBO policy/distribution, nếu dùng để claim
```

Có uncertainty hoặc equivalence/non-inferiority framework phù hợp với claim.

### Exit gate

- `FP09-G-CALIBRATION`: no future comparator/control calibration.
- `FP09-G-BUDGET`: matched/bounded-budget labeling đúng.
- `FP09-G-EXEC`: actual timing lifecycle.
- `FP09-G-CONTRAST`: verdict dùng trực tiếp treatment contrast.
- `FP09-G-SCOPE`: completed, blocked hoặc preregistered `NOT_OPENED_SECONDARY` rõ.

Không dùng conditional phase để che missing primary implementation.

---

<a id="fp-10"></a>
## 22. FP-10 — Freeze, replay và final handoff

### Mục tiêu

Bàn giao nghiên cứu tái lập được và kết luận đúng scope.

### Freeze package

Gồm:

```text
code/dependency/engine digests
data snapshots + availability
alpha/schema/search/probe contracts
B/C model và feature protocols
support/fallback/admission rules
economic/latency/activation contract
metrics/thresholds/analysis family
exact cohorts/windows/seeds/budgets
artifact index
replay commands đã verify
```

Manifest không tự hash chính nó; dùng detached digest hoặc root hash hợp lệ.

### Evaluation labels

```text
FROZEN_REPLAY
LOCKED_RETROSPECTIVE_EVALUATION
PROSPECTIVE_FROZEN_EVALUATION
```

Cùng data cũ chạy lại không là independent confirmation.

Không có eligible fresh data thì:

```text
engineering_status = COMPLETE_WITHIN_SCOPE
prospective_status = NOT_RUN_NO_ELIGIBLE_NEW_DATA
research_status = tương ứng evidence hiện có
```

Không fake future outcomes hoặc tự mở cron/live process.

### Final report phải trả lời

1. Tăng trials có cải thiện forward outcomes không?
2. B có tốt hơn A không?
3. C có tốt hơn B không?
4. Decay giảm có đi cùng utility/risk chấp nhận được không?
5. Kết quả đến từ conditional selection, timing, cadence hay exposure?
6. Support và uncertainty cho phép kết luận mạnh đến đâu?
7. Những giả thuyết nào chưa được thử?
8. Chi phí đã tiêu và phần nào tái sử dụng được?
9. Có nên dừng, giữ baseline hay mở một research revision cụ thể?

### Exit gate

- `FP10-G-FREEZE`: dependency verifier pass.
- `FP10-G-REPLAY`: cùng contract tái lập outputs trong tolerance.
- `FP10-G-REPORT`: report sinh từ artifact refs đúng.
- `FP10-G-EXPOSURE`: consumed/fresh data labeling đúng.
- `FP10-G-HANDOFF`: commands, unresolved issues, budget và owner decisions đầy đủ.

---

<a id="run-reports"></a>
## 23. Báo cáo sau mọi run — bắt buộc

### 23.1. Không chỉ báo cáo successful runs

Mỗi attempt kết thúc phải có:

```text
COMPLETED
FAILED
BLOCKED
TIMED_OUT
CANCELED
PARTIAL
```

Kèm:

- Command/config/source.
- Start/end thực.
- Status và return/exit semantics.
- Resource usage.
- Outputs đã có.
- Outputs thiếu.
- Error/blocker.
- Next action đúng scope.

Nếu process crash trước khi viết report, runner hoặc postmortem step phải tạo attempt report từ logs/checkpoints. Không fabricate measurements chưa được ghi.

### 23.2. Run report template

```markdown
# FP Run Report — <run_id>

## 1. Identity
- Phase:
- Registration:
- Source/engine/data digests:
- Parent run hoặc upgrade:
- Scope và data role:

## 2. Câu hỏi của lần chạy
- Hypothesis:
- Primary contrast:
- Điều gì được giữ nguyên:
- Điều gì thay đổi:

## 3. Planned vs actual
| Hạng mục | Planned | Actual | Lý do chênh lệch |
|---|---:|---:|---|
| Cells | | | |
| Origins/folds | | | |
| Attempted search trials | | | |
| Unique candidates | | | |
| Probes | | | |
| Matured forward episodes | | | |
| Deployment accounts | | | |

## 4. Validity
| Check | Expected | Actual | Evidence | Status |
|---|---|---|---|---|

## 5. Search và support
- Startup/adaptive trials:
- Plateau/fallback:
- Region/behavior coverage:
- Distinct origins:
- Context/region support:

## 6. Kết quả
- Raw IS:
- Forward/OOS utility:
- D1/D2/D3:
- Costs/risk/exposure:
- Uncertainty:
- Những metrics undefined và lý do:

## 7. Cơ chế
- Params/regions thay đổi gì?
- Context có đổi rankings không?
- Actual activation có xảy ra không?
- Fills/PnL khác ở đâu?

## 8. Compute
- Engine calls / bars / callbacks:
- Cache hits/misses:
- CPU/wall/peak memory:
- Reuse/wasted work:
- Budget còn lại:

## 9. Kết luận được phép
- Technical:
- Research:
- Scope:
- Điều chưa được chứng minh:

## 10. So với run trước
- Comparable contract hay không:
- Numerical changes:
- Root cause/evidence:
- Có cần invalidate downstream không:

## 11. Next action
- Một bước tiếp theo cụ thể:
- Owner approval cần có:
- Không mở thêm phạm vi nào:
```

### 23.3. Báo cáo phải generated từ evidence

- Tables lấy từ machine-readable artifacts.
- Không sửa số tay để “khớp narrative”.
- Narrative có thể viết bằng phân tích, nhưng mọi factual claim phải trỏ tới evidence.
- Artifact thiếu không được điền 0.
- Một run cùng hash không có nghĩa scientific validity đã pass.

---

<a id="upgrade-rules"></a>
## 24. Quy tắc sau mỗi lần nâng cấp

### 24.1. Upgrade types

| Loại | Ví dụ | Nghĩa vụ |
|---|---|---|
| `DOC_ONLY` | Câu chữ/format | Regenerate report; không giả economic change |
| `REPORT_OR_METRIC_FIX` | Clip window, boundary return | Recompute từ đủ outputs; invalidate affected claims |
| `PERF_EQUIVALENT` | Cache/memory/packing | Prove economic parity và measured resource effect |
| `CORRECTNESS_REPAIR` | Admission, timing, fee | Preserve old outputs; rerun affected economics |
| `SEARCH_POLICY_CHANGE` | Budget/startup/probes | New registration và comparison scope |
| `SELECTOR_OR_MODEL_CHANGE` | B/C logic/features | New design version; exposure disclosure |
| `DATA_OR_ENGINE_CHANGE` | Snapshot/native version | Dependency invalidation và targeted requalification |

Không gọi performance upgrade là equivalent chỉ vì final equity gần nhau nếu required trace semantics khác.

### 24.2. Upgrade record bắt buộc

```text
upgrade_id
parent_version
new_version
reason
finding/hypothesis addressed
source/config diff
affected dependencies
expected numerical behavior
tests before/after
old/new run references
observed numerical/resource changes
claims invalidated/superseded
owner approval
```

### 24.3. Reuse đúng mức

- Đổi report rendering không ép chạy lại engine.
- Sửa metric có đủ raw paths thì recompute metrics.
- Sửa economics/admission không được chỉ regenerate report.
- Đổi feature/model chỉ invalidate feature/model/policy dependencies cần thiết.
- Không reuse receipt từ source khác mà không dependency verification.

### 24.4. Không sửa lịch sử

Giữ original run/report/registration.

Dùng:

```text
invalidated_by
superseded_by
recomputed_from
verified_reuse_of
```

Không overwrite số liệu cũ, không xóa failed runs.

---

<a id="current-guide"></a>
## 25. “Luôn viết lại guide theo evidence” nghĩa là gì?

### 25.1. Hai lớp tài liệu

#### A. Guide/spec versioned

Ví dụ:

```text
FP-GUIDE-1.0
FP-GUIDE-1.1
```

Đổi methodology phải có version, diff và owner decision.

#### B. Current execution guide

File đề xuất:

```text
handoff/FP_CURRENT.md
```

File này được **tạo lại sau mỗi run/upgrade**, chứa:

- Current branch/commit.
- Phase status.
- Latest valid evidence.
- Latest run result.
- Những claims đã bị invalidate.
- Những assumptions chưa kiểm chứng.
- Budget thực còn lại.
- Gate đang chặn.
- Đúng một next action đã được phép.

“Viết lại” không có nghĩa tự đổi thresholds hoặc search space sau khi thấy outcome.

### 25.2. Current guide template

```markdown
# FP_CURRENT

## Current source
<actual identity>

## Phase state
| Phase | Technical | Research | Owner | Evidence |
|---|---|---|---|---|

## Latest run
<run_id + result + scope>

## Điều đã biết từ evidence
<facts with exact artifact refs>

## Điều chưa biết
<unrun/unsupported hypotheses>

## Thay đổi kể từ bản trước
<source/config/result/report differences>

## Blockers
<actual blockers, not generic TODO>

## Budget
<allocated / charged / remaining>

## Next authorized action
<one concrete action>

## Không được làm
<scope exclusions relevant now>
```

### 25.3. Không dùng narrative làm gate

Không kiểm:

```text
report contains "mechanism"
funnel contains "KEEP_INCUMBENT"
manifest says "PASS"
```

rồi cấp technical certificate.

Gate phải kiểm actual timestamps, source dependencies, economic outputs và behavior phù hợp.

---

<a id="evidence-gates"></a>
## 26. Evidence layout và gate receipt

### 26.1. Logical layout

```text
configs/forward_persistence_fp_v1/
  registration.json
  protocol_migration.json
  economics.json
  search_policy.json
  region_policy.json
  selector_B.json
  selector_C.json
  analysis_plan.json
  resource_budget.json

evidence/forward_persistence_fp_v1/
  <run_id>/
    manifest.json
    attempts/
    search_refs.json
    archive_refs.json
    selection_refs.json
    account_refs.json
    metrics.json
    gate_receipt.json
    report.md

handoff/
  FP_CURRENT.md
  FP_RUNBOOK.md
  FP_UPGRADE_HISTORY.md
```

Có thể map vào TE/RA storage hiện có. Không buộc copy lại hàng GB artifacts.

### 26.2. Gate receipt mẫu — chưa phải PASS

```json
{
  "schema": "regime_lab.fp_gate.v1",
  "phase_id": "FP-07",
  "guide_version": "FP-GUIDE-1.0",
  "registration_digest": null,
  "source_dependency_digest": null,
  "technical_gate": "NOT_RUN",
  "research_status": "NOT_ASSESSED",
  "scope_status": "NOT_RUN",
  "required_gates": [],
  "gate_results": [],
  "actual_run_refs": [],
  "verified_reuse_refs": [],
  "test_execution_refs": [],
  "measured_resources": null,
  "open_blockers": [],
  "owner_review": {
    "status": "PENDING",
    "decision_ref": null
  },
  "can_start_next_phase": false
}
```

`null` fields phải được resolve khi phase yêu cầu. Mẫu này không được đưa vào runner như success record.

### 26.3. Verifier phải kiểm

1. Required artifacts tồn tại, đọc được, đúng hash.
2. Source/config/data dependencies đúng.
3. Required tests thực sự execute.
4. No collection, mandatory skip/xfail không được PASS.
5. Actual financial runs có khi phase yêu cầu.
6. No failed arm silently omitted.
7. Candidate/label/activation timestamps hợp lệ.
8. Resource/protected-state checks đạt.
9. Report đúng nguồn và không overclaim.
10. Owner approval đúng reference.

`NOT_APPLICABLE` chỉ dùng cho conditional branch đã đăng ký với predicate được chứng minh.

---

## 27. CLI và runbook

### 27.1. Không bịa CLI hiện có

Agent phải inspect actual parser và `--help` của runner hiện tại.

Ưu tiên tái sử dụng:

```text
scripts/te.sh
scripts/run_time_edge.py
existing planner/runtime/cache/ledger
```

Nếu cần wrapper mới, có thể triển khai:

```text
scripts/run_forward_persistence.py
```

Đây là tên đề xuất, chưa phải executable được xác nhận.

### 27.2. Logical commands cần hỗ trợ

```text
plan
run
resume
verify
report
reconcile
freeze
```

Các commands phải phân biệt:

- Preflight không chạy engine.
- Run có resource admission.
- Resume không reset budget hoặc chronology.
- Report/reconcile chỉ chạy engine khi task rõ ràng cần recomputation tài chính.
- Verify trả failure khi payload `BLOCKED`, không chỉ nhìn process exit code.

### 27.3. Evidence của command

Mỗi actual invocation giữ:

```text
argv
cwd
interpreter
environment digest
request/spec hash
start/end
exit code
semantic status
stdout/stderr refs
result/manifest refs
```

Không chạy copied `.venv` từ archive.

Không đặt credentials/secrets vào reports hoặc committed artifacts.

---

## 28. Quy tắc dừng và kết luận

### 28.1. Dừng kỹ thuật

Dừng affected jobs khi:

- Leakage hoặc invalid economic contract.
- Admission không điều khiển account.
- Artifact/identity mismatch.
- Không đủ quota.
- Native capability không đáp ứng.
- Resume/cache làm đổi information flow.

Không sửa status thành green để tiếp tục.

### 28.2. Dừng hoặc đổi giả thuyết nghiên cứu

Sau valid study:

- Search sâu hơn chỉ làm IS tốt và decay xấu hơn: không tự tăng trials mãi.
- B không hơn A với interval đủ rõ: xem lại persistence selector, không đổ lỗi ngay cho regime.
- C không hơn B: chưa có regime contribution trong thiết kế đó.
- C giảm decay nhưng utility giảm quá tolerance: không gọi thành công.
- C chỉ đổi exposure: report risk/exposure contribution đúng tên.
- B/C fallback hầu hết: kết luận model mechanism chưa được exercise đủ.
- Evidence loại benefit hurdle: dừng thiết kế đã thử hoặc mở revision riêng có cơ chế mới.
- Interval rộng: quyết định thêm dữ liệu dựa precision/cost, không dựa mong muốn có p-value.

### 28.3. Không gọi “strong edge” từ một con số

Headline phải nêu:

```text
effect size
decay definition
OOS utility/risk
uncertainty
support
concentration
context/model actually used
retrospective/prospective status
replication scope
```

Positive relative result khi cả arms lỗ không tự là live eligibility.

Live/paper/canary promotion nằm ngoài guide.

---

<a id="sources"></a>
## 29. Nguồn và phạm vi diễn giải

<a id="source-i1"></a>
### I1 — Audit mới nhất

`REGIME_LAB_RA_FUP05_OBJECTIVE_REVIEW_2026-09-22_VI.md`

Sử dụng để đối chiếu:

- A03: comparator/control future calibration.
- A04: admission hậu kiểm.
- A05: warmup lẫn evaluation.
- A06: D1 boundary và economic mismatch.
- A07: overstatement của placebo verdict.
- A08: model exposure, thiếu support và dormant LOO risk.
- A09: gate predicates và scope reductions.

Đây là audit của snapshot đã gửi, không chứng nhận HEAD mới hơn.

<a id="source-i2"></a>
### I2 — Guide RA trước

`REGIME_LAB_MODE4_CORRECTIVE_AGENT_PHASE_GUIDE_VI.md`

Kế thừa safety, economic contracts, evidence preservation, resource accounting và owner review. Primary hypothesis mới của FP được migration rõ, không sửa RA history.

<a id="source-s1"></a>
### S1 — Optuna TPE

```text
https://optuna.readthedocs.io/en/v4.2.1/reference/samplers/generated/optuna.samplers.TPESampler.html
```

Dùng để hiểu sampler/startup behavior. Không cấp phép đổi installed version.

<a id="source-s2"></a>
### S2 — Optuna reproducibility/resume

```text
https://optuna.readthedocs.io/en/v4.2.1/faq.html
```

Dùng cho sampler state, failures, reproducibility và resource considerations.

<a id="source-s3"></a>
### S3 — Model-selection overfitting

```text
https://www.jmlr.org/papers/v11/cawley10a.html
```

Cawley & Talbot, 2010. Hỗ trợ yêu cầu outer evaluation và giới hạn việc tối ưu validation.

<a id="source-s4"></a>
### S4 — Sharpe inference

```text
https://www.ledoit.net/jef2008_abstract.htm
```

Ledoit & Wolf, 2008. Hỗ trợ phân biệt inference có time dependence với kiểm định giản lược.

<a id="source-s5"></a>
### S5 — Memory mapping

```text
https://numpy.org/doc/2.1/reference/generated/numpy.memmap.html
```

Tài liệu kỹ thuật tham khảo. Memory mapping không thay actual profiling.

<a id="source-s6"></a>
### S6 — Jump Model research

```text
https://arxiv.org/abs/2402.05272
```

Nghiên cứu liên quan regime-switching allocation; không phải bằng chứng edge cho crypto WFO của lab.

**Forward-persistent plateau, A/B/C study và selection contracts trong guide là thiết kế nghiên cứu đề xuất. Không được mô tả là phương pháp đã được các nguồn trên chứng minh sẽ tạo alpha.**

---

<a id="done"></a>
## 30. Definition of Done

Chương trình chỉ hoàn tất đúng phạm vi khi:

- [ ] Các validity blockers liên quan đã được sửa hoặc quarantine với bằng chứng.
- [ ] Runtime và QuantBT authority được xác minh.
- [ ] Search budget có learning-curve evidence, không chỉ chọn một số lớn.
- [ ] Candidate pool A/B/C đúng contract.
- [ ] Historical forward ledger có discovery/maturity lineage.
- [ ] Parameter regions/probes không dùng future outcomes.
- [ ] B được triển khai và kiểm định chronological.
- [ ] C có incremental-context comparison đúng.
- [ ] Admission thực sự điều khiển deployment.
- [ ] Actual continuous accounts hoàn tất trong scope đã đăng ký.
- [ ] D1/D2/D3 có đúng definitions, units và boundaries.
- [ ] Decay được đặt cạnh OOS utility/risk, không tối ưu đơn độc.
- [ ] Replication/support/uncertainty được báo trung thực.
- [ ] Mỗi run, kể cả failed run, có report và artifact refs.
- [ ] Mỗi upgrade có before/after evidence và invalidation disposition.
- [ ] `FP_CURRENT.md` phản ánh evidence mới nhất, không phải kế hoạch cũ.
- [ ] Frozen replay và handoff tái lập được.
- [ ] Owner review có reference thật.
- [ ] Không có claim “regime thắng” hoặc “regime vô ích” vượt phạm vi đã thử.

> **Đích đến của guide này không phải tìm một đỉnh IS cao hơn.**
>
> **Đích đến là xác định liệu lịch sử forward performance và regime/context có giúp chọn được vùng tham số giữ hiệu quả tốt hơn sau khi rời IS — bằng một phép thử causal, có đối chứng, có chi phí kiểm soát và có evidence tái lập sau từng lần chạy.**
