# REGIME-LAB — LẦN KIỂM ĐỊNH CUỐI VỀ GIẢM SHARPE DECAY
## Guide ba phase: chuẩn hóa phép đo → kiểm định regime model → so sánh A/B/C trên ít nhất 12 folds

**Phiên bản:** SD-GUIDE-1.0  
**Ngày ban hành:** 24/09/2026  
**Repository:** `BobbyAxerol/regime-lab`  
**Namespace triển khai:** `SD-01`, `SD-02`, `SD-03` — đúng ba phase.  
**Đối tượng thực hiện:** agent đang tiếp tục nghiên cứu của Bobby trên working copy được phép.  
**Trạng thái:** đặc tả công việc mới, không phải bằng chứng đã triển khai hoặc đã chạy thành công.

> **Mục tiêu duy nhất của vòng này:** kiểm tra regime có giúp lựa chọn tham số với **Sharpe decay thấp hơn** hay không, so với cùng phương pháp không dùng regime. Giảm đủ lớn được công nhận ngay cả khi decay vẫn dương hoặc Sharpe OOS vẫn âm. Không bắt chuyển dấu để PASS.
>
> **Thước đo nghiên cứu:** Sharpe, chênh lệch Sharpe và Sharpe decay. Không dùng mean-return/ngày, bps/ngày hoặc phần trăm/ngày làm target, eligibility hurdle hay headline thay thế. Returns vẫn là đầu vào toán học của Sharpe; phí, slippage và accounting vẫn phải được mô phỏng đúng.
>
> **Đủ mẫu:** mỗi phép so sánh model chính có ít nhất 12 validation folds chung; mỗi phép so sánh kết quả cuối có ít nhất 12 paired-valid OOS folds chung. Không cộng các candidates, seeds hoặc hai symbols để tạo ra số 12 giả.
>
> **Không có nghĩa vụ chứng minh regime thắng.** Có nghĩa vụ chạy đúng đối tượng, báo đủ evidence và kết luận đúng mức. Nếu phép thử hợp lệ không ủng hộ thiết kế này, dừng thiết kế này; không mở tiếp cuộc thi model để săn một kết quả dương.

---

## Điều hướng

[0. Phạm vi và nguồn](#scope) · [1. Rules](#rules) · [2. Sharpe và decay](#metrics) · [3. A/B/C và target](#design) · [4. Timeline và 12-fold rule](#timeline) · [5. Regime ML](#model) · [6. Data/execution](#execution) · [7. Inference và kết luận](#inference) · [8. SD-01](#sd-01) · [9. SD-02](#sd-02) · [10. SD-03](#sd-03) · [11. Compute](#compute) · [12. Evidence, report và upgrade](#evidence) · [13. Verifier/runbook](#verifier) · [14. Definition of Done](#done) · [Nguồn](#sources).

<a id="scope"></a>
## 0. Phạm vi, nguồn và thay đổi so với chương trình FP

### 0.1. Không audit lại toàn repo hoặc xây framework mới

Tiếp tục từ code, cache, profiler, actual execution routes và artifact infrastructure đang có. Reuse những phần đúng bằng dependency verification. Không làm lại FP-01…FP-10; không tạo scheduler platform mới, không rewrite QuantBT, không nâng cấp production.

Nguồn nền để agent đọc:

- **[I1]** `REGIME_LAB_FP01_FP10_OBJECTIVE_AUDIT_VI.md`, audit ngày 24/09/2026 của ZIP `regime-lab-main (2).zip`, archive SHA-256 `ce9bb179af6ba3bba4df4608a8e6c4a2c86f9ed633ca530e310a032fc958c6c1`.
- **[I2]** `REGIME_LAB_FORWARD_PERSISTENT_PLATEAU_GUIDE_VI.md`, đặc biệt safety, chronology, same-candidate rule và báo cáo từng run.
- Handoff, registrations, actual attempt ledger và source mới nhất trên host. Audit [I1] là snapshot, không chứng nhận remote HEAD hoặc runtime hiện tại.

Bobby đã thông báo merge vào `main`. Agent phải kiểm actual branch/commit/worktree; không áp snapshot `mode4-corrective` cũ đè lên source mới. Các path trong guide là vị trí cần map, không phải quyền checkout/reset.

### 0.2. Những phát hiện cũ phải xử lý đúng

| Evidence lịch sử trong [I1] | Điều phải khóa ở vòng mới |
|---|---|
| F02: 12 origins tổng nhưng tại từng decision chỉ có 0…11 prior origins; support floor không được runner áp đúng | Có archive khởi tạo đủ trước validation; đếm matured origins ở từng cutoff; test actual path |
| F03: helper decay có nhưng actual runner dùng `max(predicted_forward_utility)` | Actual winner do **predicted relative Sharpe decay** quyết định; kiểm forced-ranking fixture trên runner |
| F03: A được chọn từ toàn search, B/C chỉ từ 16 medoids | A/B/C cùng toàn bộ eligible candidate pool; representative panel chỉ dùng tiết kiệm label evaluations |
| F05: C bị B short-circuit hoặc OOD rồi fallback; không có C-specific selection | C được fit/chấm độc lập khi đủ technical support, không phụ thuộc B admission |
| F05/F06: model cũ không dùng JM/M0 và predictive diagnostic target cũ yếu | Đo riêng model mới; không gọi old return-prediction error là kết quả Sharpe mới; không phủ nhận evidence âm cũ |
| F07: D1 thiếu paired origins; D2 gán origin thành activation và bỏ fallback có params | Đủ 12 common paired rows; timestamps/versions thực; fallback có params vẫn được đánh giá |
| F04: hyperparameter dùng thông tin muộn; inference phụ thuộc label existence | Hyperparameters freeze trước final OOS; feature-only inference không đọc current future labels |
| F10: receipt/publication/replay scope chưa khớp narrative | Detached integrity seal, exact source refs, cold execution khác cache replay; report không overclaim |

Không mặc định mọi lỗi vẫn tồn tại. Mỗi finding có disposition: `PRESENT`, `FIXED_WITH_PROOF`, `SUPERSEDED_PATH_QUARANTINED`, hoặc `NEEDS_RUNTIME`. Chỉ sửa phần còn ảnh hưởng đường chạy mới.

### 0.3. Những thay đổi được yêu cầu rõ trong SD-1.0

1. Target mới là **relative Sharpe decay**, không phải predicted absolute daily return.
2. Stock Mode 4 là baseline A; B là global Sharpe-decay selector; C là B có JM-conditioned interactions.
3. Lịch chọn tham số cố định và giống nhau. **Không nghiên cứu dynamic refit timing, random-delay hay volatility-delay overlay trong vòng này.**
4. Candidate train 180 ngày, forward/evaluation block 56 ngày; search default 128 trials/cutoff. Mọi reuse 256-trial pool phải áp cùng scope cho A/B/C và khai báo trước run.
5. Tách tối thiểu 12 origins khởi tạo, 12 validation folds và 12 final evaluation folds. Không hạ requirement để vừa dữ liệu.
6. Dùng một regime family: JM hai trạng thái, tối đa ba jump-penalty designs. Không mở K3/K4/HMM/HSMM/deep-learning sweep.
7. Cải thiện decay không cần đổi dấu; vẫn phải kiểm OOS Sharpe để phát hiện giảm gap bằng cách chọn IS thấp hơn.
8. Đúng ba phase và một vòng final evaluation đã khóa; sửa lỗi và rerun có version/invalidation, không âm thầm tuning sau kết quả cuối.

Các thay đổi được ghi trong `protocol_migration`; old registrations, reports và negative/null results giữ nguyên.

<a id="rules"></a>
## 1. Rules bắt buộc, áp dụng cho cả ba phase

### 1.1. Safety, engine và Git

**R01 — QuantBT là financial authority duy nhất.** Orders, fills, rejects, positions, cash, fees, equity và liquidation phải do QuantBT sinh. Lab chỉ tạo features, models, proposals, scheduling mỏng và analysis. Tiny independent numeric oracles chỉ dùng trong tests, không làm evaluator tài chính thay engine.

**R02 — Pin actual environment.** Ghi Python, package/native versions, import origins, module/build hashes, lockfile và actual route. Baseline trước từng dùng `quantbt-engine==1.1.1`; không suy host vẫn như vậy và không tự upgrade/downgrade để vượt gate.

**R03 — Protected paths giữ nguyên.** Không sửa sibling QuantBT, site-packages, original alphas, market snapshots hoặc production service. Cần sửa engine thì gửi minimal reproducer và dependency request; chỉ patch khi có authorization riêng trong isolation.

**R04 — Không phá worktree.** Không `git reset --hard`, `git clean`, force checkout, rebase/merge, `git add .` hoặc xóa untracked evidence để dọn trạng thái. Làm trên branch/worktree được phép; commit scoped sau phần việc hoàn thành; không push khi chưa được yêu cầu.

**R05 — Quota thật là giới hạn.** Không tăng workers/threads/RAM, chỉnh cgroup, kill process ngoài job hoặc reset budget bằng run ID mới. Không dùng production venv. Profile trước khi đăng ký bulk cost.

### 1.2. Semantics và chronology

**R06 — Giữ alpha và economic contract.** Không bỏ stops/partial exits/amendments, đổi next-open thành same-close, hoặc đổi equity sizing thành fixed notional để chạy nhanh. Qualified fast route được ưu tiên; không ép vectorization bằng cách đổi chiến lược.

**R07 — Closed bars, UTC và point-in-time.** Crypto naive timestamps mặc định UTC; aware convert UTC giữ thời điểm. Không cộng/trừ 7 giờ. Features và labels đều có `available_at`; HTF chỉ dùng sau close. Dataset version/revision cũng phải đúng contract availability.

**R08 — No outer look-ahead.** Search/model/selection chỉ nhận permitted past. Comparator/calibration phải BEFORE, không chỉ OUTSIDE evaluation window. Không đưa actual future segment end hoặc realized future regime vào lựa chọn tại origin.

**R09 — No future candidate hindsight.** Candidate được khám phá sau origin không được hồi tố thành candidate đã biết. Không tìm winners trên toàn lịch sử rồi gọi replay các đoạn đã dùng là independent forward evidence.

**R10 — Feature-only inference.** Current candidate prediction không được cần future label tồn tại, finite hay non-null. Thêm/xóa/thay label tương lai không đổi selection trước maturity.

**R11 — Admission trước deployment.** Approved proposal phải được xử lý trước khi engine nhận params mới. Rejection phải giữ/đổi theo fallback thực, không chỉ thêm một dòng `KEEP_INCUMBENT` sau khi account đã chạy xong.

**R12 — Continuous account không reset theo fold.** Candidate experiment có thể reset theo standardized contract; deployment account không được ghép từ các candidate returns hoặc independently normalized fold equities.

**R13 — Cache không làm time travel.** Cache hit tiết kiệm compute vật lý, không làm `model_ready_at/search_ready_at` sớm hơn latency contract. Fit/search failure không được đổi thành zero label hoặc valid candidate score.

### 1.3. Scientific và báo cáo

**R14 — Không dùng sign-switch làm tiêu chuẩn.** Decay 1,30 xuống 0,85 là cải thiện 0,45; không yêu cầu xuống âm. Sharpe OOS âm nhưng tốt hơn vẫn có thể là retention evidence, không là live eligibility.

**R15 — Không reuse hurdle sai đơn vị.** Xóa mean-return/day floor khỏi decision path mới. Không đổi tên nó thành Sharpe floor, không convert bằng một hệ số ad hoc. Các ngưỡng mới có đơn vị **điểm Sharpe**.

**R16 — Đếm mẫu đúng.** 12 origins × 16 candidates không là 192 market episodes độc lập. 6 BTC folds + 6 ETH folds không là 12-fold comparison cho một cell. Seeds không bổ sung lịch sử thị trường.

**R17 — Không làm xanh bằng thiếu việc.** Mandatory tests/actual runs/paired rows thiếu thì BLOCKED hoặc INCOMPLETE. `INCONCLUSIVE_SUPPORT` không che việc chưa implement hoặc chưa chạy.

**R18 — Không chọn outcome thuận lợi.** Không đổi windows, penalty, floor, fallback, horizon, seed hay threshold sau khi nhìn final result. Không bỏ fold xấu để đủ 12 folds tốt; không thay cell âm bằng cell khác.

**R19 — Honest negative result.** CI qua 0 không đồng nghĩa no-edge; estimate dương không đồng nghĩa proof. Valid interval loại được hurdle thì dừng thiết kế trong scope đó, không kết luận mọi regime đều vô ích.

**R20 — Evidence trước narrative.** Mọi run, kể cả FAILED/TIMED_OUT, có machine-readable record và Markdown report. Update current handoff sau mỗi run/upgrade; không sửa raw report lịch sử.

**R21 — Gate kiểm hành vi.** Không lấy hiện diện từ `mechanism`, `PASS` hay testcase ID thay actual runtime, timestamps, winner selection và financial trace.

**R22 — Owner review.** Sau phase: verify → generate report → scoped commit → `WAITING_OWNER_REVIEW`. Không qua phase kế tiếp trước approval, trừ chỉ dẫn auto-advance thật của Bobby đã được lưu reference. Guide không tự cấp thêm quota hoặc live/paper permission.

<a id="metrics"></a>
## 2. Sharpe, decay và tiêu chuẩn giảm có ý nghĩa

### 2.1. Chuỗi returns chuẩn

Account không external cashflows:

\[
r_d=E_d/E_{d-1}-1,\qquad
SR(W)=\sqrt{365}\frac{\operatorname{mean}_{d\in W}(r_d-r_{f,d})}
{\operatorname{std}_{d\in W}(r_d-r_{f,d};ddof=1)}.
\]

Default `r_f,d=0` nếu giữ convention engine trước; phải freeze. Đây là annualized Sharpe statistic theo daily UTC sampling, không bảo đảm returns độc lập hoặc estimator chính xác trong 56 ngày.

- Tính returns có preceding equity đúng trước khi clip reporting window.
- Observation đầu account dùng initial equity trước fee/fill đầu tiên.
- Giữ flat days hợp lệ bên trong window; loại warmup bên ngoài.
- Missing market day không được tự gán return 0.
- Full IS có đúng 180 daily returns; standardized forward có đúng 56, không vô tình thành 185/29 như scope mismatch đã audit.
- Sharpe whole continuous path được tính từ whole path, không average fold Sharpes rồi đặt tên portfolio Sharpe.
- Giữ raw QuantBT metrics riêng; canonical recomputation có provenance/sampling/reconciliation.

`ZERO_VARIANCE`, `INSUFFICIENT_OBSERVATIONS`, missing returns hoặc non-finite equity phải có typed status. Không epsilon-fix denominator để tạo Sharpe lớn; không đổi undefined thành 0.

### 2.2. Primary D1: cùng params, IS→forward

Với candidate \(\theta\) tại fold \(k\):

\[
D_k(\theta)=SR_{IS,k}(\theta)-SR_{FWD,k}(\theta).
\]

IS là raw Sharpe trên full 180-day scoring window, không penalized optimizer objective. FWD là standardized 56-day forward outcome. Cả hai cùng alpha/economics/sizing/valuation conventions; initial-state contract được khai báo ở §6.

Primary dùng **signed decay**. Không lấy absolute value, không clip \(D\) về 0, không thay bằng Sharpe ratio retention khi denominator IS âm/gần 0. Positive-part hoặc relative-percent reduction chỉ là secondary nếu đăng ký riêng; vòng này không cần chúng.

IS/forward có thời lượng khác nên sampling uncertainty khác nhau; cùng annualization không xóa hết bias của selection và finite-sample Sharpe. Báo đây là measured generalization gap, không gọi là unbiased causal aging parameter. [S2–S3]

### 2.3. Paired reduction và phân rã bắt buộc

\[
R_k=D_k^{(B)}-D_k^{(C)}.
\]

\(R_k>0\) nghĩa là C ít decay hơn B. Báo \(\overline R\), median, từng fold, uncertainty và number of paired-valid folds.

Bắt buộc reconcile:

\[
R_k=
\underbrace{SR_{IS,k}^{(B)}-SR_{IS,k}^{(C)}}_{\text{IS-reference contribution}}
+
\underbrace{SR_{FWD,k}^{(C)}-SR_{FWD,k}^{(B)}}_{\text{forward-retention contribution}}.
\]

Một gap nhỏ hơn do IS yếu hơn không tự là OOS tốt hơn. Không che điều này bằng cách chỉ báo \(R\).

**Ví dụ số học, không phải kết quả lab:** B có IS 1,80, FWD 0,50, decay 1,30; C có IS 1,75, FWD 0,90, decay 0,85. Reduction 0,45 dù decay vẫn dương. IS contribution 0,05; forward contribution 0,40.

### 2.4. D2: cùng params theo tuổi

Tại 12 evaluation origins đã freeze, chạy một standardized continuation giữ nguyên \(\theta_k\):

```text
H1 = [forward_start, forward_start + 56 ngày)
H2 = [forward_start + 56 ngày, forward_start + 112 ngày)
```

\[
D^{age}_k(\theta)=SR_{H1,k}(\theta)-SR_{H2,k}(\theta).
\]

Không reset account/strategy ở ranh giới H1/H2. Không dùng active account đã thay params tại fold kế tiếp thay frozen continuation. H1 của D2 phải match standardized forward H1 đã có theo parity; reuse thật nếu checkpoint/extension được engine hỗ trợ, không giả extension từ returns columns.

D2 là secondary diagnostic; primary verdict vẫn D1 C−B. Phép so sánh D2 B/C cũng cần ít nhất 12 paired-valid anchors, có 56 ngày follow-up ngoài cuối primary evaluation. Không bỏ anchors fallback có params. Nếu thiếu follow-up, ghi D2 chưa đủ dữ liệu; không điền tương lai giả hoặc dùng 3 anchors để kết luận.

### 2.5. D3 và continuous account

D3 giữa adjacent operational folds chỉ dùng mô tả, vì params/market/activation có thể đổi. Ghi rõ đó không phải decay của cùng vector.

Báo thêm Sharpe từ continuous account cho A/B/C, trên cùng dates. Tách `standardized_candidate_sharpe` và `continuous_account_sharpe`; không gán old-campaign account returns cho newly selected params.

### 2.6. Ngưỡng của vòng cuối

| Field | Default SD-1.0 | Đơn vị/ý nghĩa |
|---|---:|---|
| `meaningful_decay_reduction` | 0.20 | Điểm Sharpe, hurdle cho mean \(R\) |
| `oos_sharpe_noninferiority_margin` | 0.10 | Điểm Sharpe, tolerance cho FWD C−B |
| `prediction_guard_margin` | 0.10 | Điểm Sharpe, guard prediction tương đối với stock anchor; vai trò KHÁC ngưỡng inference |
| `confidence_level` | 0.95 | Confidence reporting target của procedure đã pin |
| `validation_folds_min` | 12 | Folds chung, không là 12 candidates |
| `evaluation_paired_folds_min` | 12 | Paired-valid folds cho từng cell/contrast |

Đây là **experimental defaults của phương án đã thảo luận**, không phải chuẩn thống kê phổ quát hoặc phí live. Materialize chúng trong registration và owner approval trước final OOS. Nếu owner đổi, version trước outcome; không nới sau khi biết kết quả.

Không có rule `D_C < 0`, `SR_C > 0`, `SR_IS > 0` hoặc predicted absolute return > một daily hurdle. Risk/capital/execution safety vẫn có hiệu lực dù mục tiêu không yêu cầu lãi dương.

<a id="design"></a>
## 3. A/B/C, candidate pool và relative Sharpe-decay target

### 3.1. Arms

| ID | Selector | Thông tin thêm | Timing |
|---|---|---|---|
| `A_M4` | Stock Mode 4 thực từ QuantBT | Không dùng Sharpe-decay model | Fixed common calendar |
| `B_SD_GLOBAL` | Dự báo relative Sharpe decay | Candidate/IS descriptors | Cùng A |
| `C_SD_JM` | Cùng B + regime-conditioned effects | JM K=2 và interactions | Cùng A |

Primary hypothesis `H_REGIME = C_SD_JM vs B_SD_GLOBAL` theo reduction \(R\). `B−A` là key secondary về selector; `C−A` là secondary tổng policy. Không gọi B/C là stock Mode 4 không đổi.

Stock binding tham chiếu phải verify actual package:

```text
optimization_mode          = mode_4_is_only_robust
optimization_schedule      = per_fold_causal
candidate_selection_metric = is_only_robust
scoring_backend            = endpoint
```

Không dùng giả Sharpe, private argmax hoặc best-objective checkpoint thay stock selection. Common admission guard nếu có mang version riêng; giữ raw stock winner/reason. Không sửa QuantBT core để thêm một enum mới cho B/C.

### 3.2. Candidate universe chung

Tại cutoff \(t_k\), search chỉ IS tạo \(\mathcal C_k\), gồm mọi unique effective candidates hợp lệ đã được evaluate. Default 128 attempted trials và 2–3 dimensions đã có behavioral-effect tests. TPE seed/startup/ask–tell/pruning được pin; không dùng target regime riêng để TPE đề xuất cho C.

- A chọn stock winner từ đúng \(\mathcal C_k\).
- B/C predict trên **toàn \(\mathcal C_k\)**, không chỉ 16 medoids.
- Common data/candidate-invalid exclusions áp đối xứng và được ghi trước.
- B/C không cần future labels của current candidates để predict.
- Prediction guard khác nhau do prediction của từng model là policy treatment, không phải thay search pool âm thầm.
- 128/256 candidate pool reuse chỉ khi full data, 180-day training, actual sampler/stock scoring, schema và economics match. 45-day pool không được đổi nhãn thành 180-day.
- Chọn search budget từ phase 1 profile/registration, không chọn 128 hoặc 256 tùy origin nào có OOS đẹp.

### 3.3. Anchor và label

Gọi \(a_k\) là raw stock Mode 4 winner tại origin, available trước forward outcome.

\[
Y_{k,\theta}=D_k(\theta)-D_k(a_k).
\]

Đây là **relative Sharpe decay label**, đơn vị điểm Sharpe. Nhỏ hơn là tốt hơn anchor. Candidate cùng origin chia sẻ cùng market shock và anchor; weight theo origins, không gọi các rows đó independent.

Identity dùng cho guard:

\[
Q_{k,\theta}=SR_{FWD,k}(\theta)-SR_{FWD,k}(a_k)
=SR_{IS,k}(\theta)-SR_{IS,k}(a_k)-Y_{k,\theta}.
\]

Với prediction \(\widehat Y_m\):

\[
\widehat Q_m(\theta)=SR_{IS}(\theta)-SR_{IS}(a)-\widehat Y_m(\theta).
\]

Không cần dự báo absolute stock OOS Sharpe để dùng guard này. Label anchor có \(Y_{k,a}=0\); inference phải force \(\widehat Y_m(a)=0\) bằng contrast architecture, không phụ thuộc intercept may rủi.

### 3.4. Rule selection duy nhất

```text
1. Technical/model support check bằng past đã mature.
2. Predict Y_hat cho từng candidate trong common pool, độc lập cho B và C.
3. Tính Q_hat từ identity trên, không đổi sang predicted return.
4. Candidate eligible nếu common safety/data checks đạt và Q_hat >= -0.10.
5. Stock anchor luôn là contrast-zero reference nếu raw anchor hợp lệ.
6. Chọn candidate có Y_hat thấp nhất trong tập eligible.
7. Tie deterministic: gần anchor theo schema trước, sau đó stable candidate ID.
8. Gửi proposal qua actual common admission rồi queue activation theo contract.
```

Không yêu cầu \(\widehat Y<0\): anchor 0 có thể thắng hợp lệ. Không yêu cầu Sharpe của anchor hoặc winner dương. Nếu model unavailable/insufficient past thì B proposal fallback về **stock proposal tại cutoff hiện tại**, không tự giữ một bộ hàng trăm ngày vì old return hurdle.

C có global layer nhưng **không lấy B admission/fallback status làm điều kiện được fit/chấm**. Nếu C technical unavailable thì fallback về B proposal là hợp lệ và được ghi; nếu B không có candidate ngoài anchor vượt guard thì C vẫn phải được đánh giá độc lập.

Common engine safety veto hoặc open-campaign wait có thể giữ incumbent; đó là actual lifecycle event khác statistical/model fallback. Không cưỡng ép đóng positions để tạo cùng activation nếu alpha contract không cho phép.

### 3.5. Label panel tiết kiệm không làm lệch eligible pool

Historical forward labels không bắt buộc có cho mọi 128 candidates. Dùng subset deterministic tối đa 16 representatives/origin, chọn IS-only trước forward, **bắt buộc có stock anchor**. Label bổ sung cho mọi winner của các registered model designs/arms tại origin, kể cả winner nằm ngoài 16 representatives.

Toàn bộ union được đóng băng trước forward evaluation, có inclusion reason. Prediction vẫn trên toàn candidate universe. Trong validation/final, A/B/C winners phải có standardized forward paths để tạo paired D1 đầy đủ. Nếu ba arms chọn cùng params, reuse một exact evaluation, ghi ba logical refs, không tạo ba market samples.

Không chỉ giữ representatives thắng; failed/censored vẫn có rows và reason. Common archive cập nhật theo union rule đã freeze, chia sẻ cho B và C; không tạo một archive thuận lợi riêng cho C.

<a id="timeline"></a>
## 4. Timeline: 12 khởi tạo + 12 validation + 12 final, không trộn vai trò

### 4.1. Ba nhóm origin, không phải ba lần dùng cùng 12 folds

```text
Raw prehistory/warmup
    → INIT: ít nhất 12 matured historical origins
    → VALIDATION: ít nhất 12 forward folds chung để so model recipes
    → FREEZE: chọn một JM recipe và khóa tất cả decision/analysis rules
    → FINAL: ít nhất 12 OOS folds chung để so A/B/C
    → D2 follow-up: đủ 56 ngày tiếp theo cho anchor cuối nếu kết luận D2
```

INIT là training archive, không phải model-performance comparison. Mọi comparison report của VALIDATION hoặc FINAL cần đủ 12 paired-valid folds. Unit tests hoặc micro-profiles ngắn hơn chỉ mang nhãn kỹ thuật, không cấp scientific verdict.

Archive có ít nhất 12 distinct matured origins **ở cutoff validation đầu tiên**. Ở cutoff FINAL đầu tiên, có ít nhất 24 distinct matured origins: 12 INIT và cả 12 VALIDATION. Recipe được chọn bằng toàn bộ validation nên không được bắt đầu FINAL khi label cuối của validation chưa available. Không fit model tại các origins khởi tạo với 1–4 priors rồi gắn nhãn model-ready.

### 4.2. Timing của một fold

Mỗi fold có explicit fields:

```text
train_start         = decision_cutoff - 180 ngày
train_end_exclusive = decision_cutoff
decision_cutoff     = thời điểm khóa input search/model
scheduled_start     = decision_cutoff + common_ready_lag
scheduled_end       = scheduled_start + 56 ngày
label_available_at  = scheduled_end + declared publication lag
model_ready_at / search_ready_at / actual_activation_at = riêng biệt
```

`schedule_start/end` nằm trên daily-UTC boundaries để daily Sharpe có 56 observations đúng. `common_ready_lag` được calibrate từ actual runtime/capability trước evaluation; không bịa là 0 vì có cache. Có thể làm tròn lên ngày theo contract đã freeze. Không lấy latency từ runtime đã dùng future content để đặt lịch sớm hơn.

Within VALIDATION và within FINAL, các standardized 56-day forward windows không chồng lấn và dùng common calendar cho mọi arm. Decision cutoffs có thể nằm trước nominal forward starts do lag.

**Bẫy maturity tại ranh giới:** label của fold vừa kết thúc có thể chưa available ở decision cutoff của fold kế tiếp. Không tự dùng nó chỉ vì hai nominal windows liền nhau. Insert một gap cần thiết giữa INIT→VALIDATION hoặc VALIDATION→FINAL, hoặc schedule start sau maturity+lag; ghi rõ. Không lùi `label_available_at` để đủ 12 priors.

### 4.3. Timeline feasibility là gate đầu, không phải việc sửa cuối

Agent lập `timeline_plan` từ snapshot coverage thực, không đặt ngày tùy ý trong guide. Kiểm:

- Raw data trước first search đủ 180-day IS và exact alpha warmup.
- Feature lookback của model cộng model-fit window cũng cần raw prehistory; rolling feature 180 ngày trên 180 ngày model training không chỉ cần 180 ngày raw data.
- 36 blocks × 56 ngày = 2.016 ngày forward windows, chưa tính prehistory, readiness/maturity gaps và D2 follow-up. Đây là số học về coverage, không phải runtime estimate.
- Final end và D2 end không vượt latest complete data bar; không dùng incomplete current day.
- Crypto primary không dùng pre-2020 để lấp thiếu nếu chưa có authorization dữ liệu riêng.
- Listing/coverage của ETH hoặc alts có thể khiến không đủ; BTC đủ không có nghĩa mọi symbol đủ.

Nếu không đủ, trả `BLOCKED_TIMELINE_COVERAGE` với missing interval. Không tự đổi 56 thành 28 ngày, giảm 12 xuống 8 hoặc bỏ D2 nhưng gọi đủ. Owner có thể duyệt revision trước outcomes; lần đó là contract mới, không sửa âm thầm SD-1.0.

### 4.4. Retrospective và prospective

Dữ liệu đã được xem qua nhiều vòng FP không được gọi untouched. Đặt `LOCKED_RETROSPECTIVE_EVALUATION` nếu policy khóa trước run mới nhưng interval đã consumed. Prospective chỉ dùng decisions/outcomes thật sau freeze, chưa tham gia thiết kế.

Trong FINAL có thể cập nhật **weights** theo các labels đã mature nếu online-expanding update rule đã freeze; không chọn lại K, penalty, feature set, margin hoặc ridge strength theo outcome FINAL. Không chờ hoặc hứa chạy dữ liệu tương lai trong một phiên hiện tại.

### 4.5. Quy tắc thiếu/undefined folds

- Pre-register exact windows trước đọc outcomes; chọn coverage theo timestamp/capability, không theo PnL/Sharpe.
- Một fold undefined Sharpe được giữ cùng reason; không chọn fold khác vì kết quả này không thuận lợi.
- Muốn dự phòng hơn 12 windows thì đăng ký toàn bộ N ngay từ đầu, report toàn bộ N; không chọn 12 winners sau run.
- Nếu paired-valid <12: `INSUFFICIENT_PAIRED_FOLDS`, không positive/negative inferential claim.
- 12 paired-valid folds vẫn không bảo đảm nhiều recurrent regimes hay đủ precision; báo dependence và active-model coverage riêng.

<a id="model"></a>
## 5. Regime ML: nhỏ, thực sự causal và kiểm bằng nhiệm vụ Sharpe decay

### 5.1. Mục tiêu phân biệt ba loại chất lượng

| Lớp | Cần biết | Không được suy thay |
|---|---|---|
| Technical validity | Availability, fit/filter, state mapping đúng | Không tự là economic usefulness |
| Descriptive regime quality | State profiles khác, recurrence/support, switching/novelty hợp lý | Không gọi cluster fit đẹp là accuracy khi thiếu ground truth |
| Task relevance | JM có cải thiện prediction/selection theo relative Sharpe decay so với B? | Không suy từ dự báo hướng giá hoặc old return-target RMSE |

Kết quả trước yếu có thể do model/representation; cũng có thể do candidate opportunity nhỏ, noise, execution hoặc sample. Báo lỗi ở tầng nào bằng evidence; không mặc định «model chưa đủ mạnh» để né kết quả âm.

JM research [S1] gợi ý chọn persistence penalty gắn với strategy objective thay vì chỉ reconstruction. Nghiên cứu đó thuộc allocation trên equity indices, không chứng minh crypto WFO Sharpe-decay thesis. Thiết kế SD dưới đây là đề xuất của lab, không phải reproduction đã được xác nhận của paper.

### 5.2. JM recipe v1

- `K=2` cố định; reuse discrete JM/online filter đã có sau qualification.
- Observation daily UTC, chỉ completed bars. Không mặc định tape 4h/28-day target cũ tương đương recipe này.
- Model calibration window mặc định 180 daily feature observations trước cutoff; tái fit tại fixed selection cutoffs, không dùng regime để đổi lịch.
- Feature preset nhỏ, mặc định ba columns: `log(rv_28 / rv_180)`, signed path efficiency 56 ngày, daily return lag-1 autocorrelation 56 ngày. Exact formula, zero denominator và missing policy phải được freeze.
- Activity feature chỉ được thêm bằng một preset revision trước validation khi có reliable coverage; vòng mặc định không thêm feature search.
- Market returns/volatility là model inputs, không phải output label hoặc daily-return hurdle.
- Standardization fit trên permitted model train, transform frozen cho next period. Không fit scaler trên toàn dataset trước time split.

Signed efficiency ví dụ: `(close_t-close_(t-56))/sum(abs(daily close changes))` trên đúng 56 completed steps. `rv_h` dùng sample std của daily log returns theo h quan sát đã pin; annualization không cần trong ratio. Autocorrelation cần đúng pairs finite, không gán NaN thành 0. Features đều mang `observed_at/available_at/schema_hash`.

### 5.3. Jump penalty có đơn vị rõ

Với standardized features, objective tham chiếu:

\[
\min_{\mu,s}\sum_t\ell(z_t,\mu_{s_t})+
\lambda_J\sum_{t>1}\mathbf1(s_t\ne s_{t-1}).
\]

Tối đa ba designs: hệ số \(c\in\{0.5,1,2\}\) nhân train-only loss scale \(L\) đã định nghĩa. Default \(L\) là median finite one-centroid loss trên current train với cùng feature weights. Record both \(c,L,\lambda_J=cL\). Zero/invalid scale → `DEGENERATE_FEATURE_GEOMETRY`, không chia/nhân epsilon để tạo state giả.

Giá trị 0.5/1/2 không được hiểu như ba universal penalties độc lập preprocessing. Solver seed, tolerance, iterations, initialization và convergence status được pin. Model fit failure ghi riêng với sparse-state outcome.

### 5.4. Filter và identity giữa vintages

- Output tại origin là filtered decision theo past, không smoothed/backtracked label dùng future.
- Có thể batch-fit model bằng train history hợp lệ, nhưng emit decision tape bất biến theo từng prefix.
- Match centroid giữa vintages bằng common raw/economic coordinates và one-to-one assignment; ambiguity/unmatched explicit.
- Đổi model ID không tự thành market transition; không thay namespace rồi gọi state difference là information.
- State 0/1 không có tên bull/bear mặc định cho mọi symbols/vintages.
- Training rows giữ state/model version và economic features **available tại origin**. Không overwrite quá khứ bằng nhãn của final selected model.
- Mỗi penalty recipe có own causal vintage tape. Chọn recipe sau validation không cho phép lấy final fitted centroids viết lại tape lịch sử như đã known từ đầu.

Nếu cần re-expression trong current-fit coordinates cho model training, phải là một registered alternative train-only representation với chronological validation riêng; không bật nhánh đó trong mặc định để né version mapping.

### 5.5. Global model B và conditional model C

Candidate descriptors \(z_{k,\theta}\) mặc định gồm 2–3 schema-normalized effective parameters, raw IS Sharpe và một activity/support descriptor đã qualify. Giữ nhỏ; không dùng candidate ID, future labels, source names hoặc absolute later timestamps làm predictive feature.

Định nghĩa contrast vector:

\[
v_{k,\theta}=\phi(z_{k,\theta})-\phi(z_{k,a_k}).
\]

\(\phi\) và scaler fit chỉ từ matured train rows. Constant columns được flag/drop theo fixed rule; không dùng min/max của một origin làm hard market-OOD box.

B: \(\widehat Y_B=\beta^T v\).

C: \(\widehat Y_C=\beta^T v+\gamma_{s_k}^T v\), với shrinkage về global. Không dùng một pure state intercept duy nhất: cùng state offset cho mọi candidates không thay relative ranking. Không có intercept trong contrast model, nên anchor prediction bằng 0 theo cấu trúc.

Default implementation để dễ đối chiếu:

1. Fit B ridge trên matured labels, một total weight bằng 1 cho mỗi origin: candidate weights trong origin cộng về 1.
2. Giữ global \(\beta\) của B; fit state-specific residual correction trên \(Y-\widehat Y_B\) theo state tại origin.
3. Penalize correction để khi support thấp, coefficients về gần 0; không tự phóng đại state ít mẫu.
4. Prediction unknown/ambiguous state → correction 0, label `GLOBAL_FALLBACK`, vẫn output B proposal và đủ report.

Frozen starting penalties: `lambda_global=10`, `lambda_state=10`, theo objective `sum_origin(mean_candidate_squared_error) + lambda*||coef||^2`. **Phải giữ đúng normalization này**; sklearn/objective khác dùng sum/mean weights cần explicit conversion. Đây là defaults mới cho Sharpe labels, không chứng nhận alpha10 cũ tối ưu; không mở ridge grid trong final run.

Chuẩn hóa dựa matured train, không chuẩn hóa labels bằng full-sample volatility. Không dùng same-origin candidates như hàng trăm regime recurrences. Nếu đội thực thi chọn solver tương đương, numerical fixture phải verify objective/coefficients/predictions.

### 5.6. Support, shrinkage và OOD

- Global B cần >=12 distinct matured train origins tại mọi validation/final decision. Không dùng row count thay origin count.
- Corrections cho một state cần >=3 distinct matured origins thuộc semantic state hợp lệ. Dưới floor: correction 0, ghi `STATE_SUPPORT_LOW`. Floor là engineering convention, không guarantee prediction tốt.
- Có >=3 origins vẫn có thể thiếu recurrence độc lập; report number of separated state visits và concentration.
- Không hard reject mọi context ngoài historical min/max; use input validity, model-fit qualification, state support và global shrinkage. Novelty score được ghi nhưng không thêm threshold ad hoc sau outcome.
- C phải được gọi ở mọi model-ready fold dù B selected anchor/fallback về anchor. Exception là same genuinely missing technical inputs cần cho cả B/C, có reason riêng.
- Không bắt số C-specific selections >0 để pass. Nếu C toàn global fallback, whole-policy result vẫn được báo nhưng không cấp active-JM efficacy verdict.

### 5.7. Rule-based comparator trong validation, không thay C bí mật

Một comparator rẻ `R_RULE` dùng state high/low volatility từ median training `log(rv_28/rv_180)` với causal feature preset; candidate residual-correction architecture, penalty và support giống C. Threshold fit bằng permitted past, không all-history.

Chạy R_RULE trên cùng 12 validation folds để biết JM có thêm giá trị so với state-threshold đơn giản không. Nó là development diagnostic, không được âm thầm thay C bằng rule nếu rule thắng rồi vẫn gọi final result là JM.

Final có đúng A/B/C. Rule chỉ vào final nếu owner duyệt một registration khác trước outcome; đó không còn là mặc định của guide này.

### 5.8. Chọn một JM recipe trên 12 validation folds

Với từng c trong ba penalty designs:

- Chạy chronological candidate selection, labels chỉ từ past matured.
- Tính origin-averaged MAE của \(Y\), rank diagnostic trong từng origin khi đủ variation, selected-candidate D1 reduction C−B và selected forward Sharpe difference.
- Mọi model comparison cần cùng 12 paired-valid validation folds; không so c1 trên 12 folds với c2 trên 5 folds tốt.
- Primary selection criterion: mean validation \(R=D_B-D_C\) lớn nhất trong designs technically valid và có đủ paired folds. Prediction guard §3.4 áp như nhau. Không yêu cầu \(R>0\) để design được lựa chọn.
- Tie trong `1e-6` Sharpe point: chọn stronger normalized persistence c lớn hơn; sau đó deterministic design ID. Không dùng final OOS để break tie.
- Nếu các c đều không đạt technical/data eligibility: `NO_VALID_JM_DESIGN`, không force model; phase 3 có thể chỉ xuất limitation/freeze, không gọi là final regime study hoàn tất.
- Nếu designs hợp lệ nhưng evidence validation yếu/âm: chọn theo cùng rule, ghi `WEAK_DEVELOPMENT_EVIDENCE`; final run vẫn có thể được owner duyệt là kiểm định cuối của recipe đó. Không tuning tiếp tới khi validation dương.

Validation scores dùng để chọn recipe nên **không** được gọi independent confirmation. Toàn selection procedure được đánh giá ở FINAL, với consumed-data disclosure. [S3]

<a id="execution"></a>
## 6. Data, standardized candidates và continuous accounts

### 6.1. Universe và economic defaults

Primary cell đề xuất A-SC/BTCUSDT vì có prior integration work; SD-01 vẫn phải kiểm đủ activity/Sharpe/coverage bằng train-only và technical fixtures, không chọn vì final Sharpe đẹp. Universe cũ 4 alphas × 5 symbols giữ như future scope, không mở toàn matrix lần này. ETH replication chỉ có khi được budget trước final và có >=12 folds riêng.

Study assumptions tham chiếu: initial equity 20.000; allocation fraction 0,10 của actual equity tại entry; leverage cap 1; one-way fee decimal 0,0004; one-way slippage decimal 0,0001. Đây là execution settings, **không phải daily-return mục tiêu** hoặc khẳng định phí sàn hiện hành. Verify endpoint binding và actual notional/cost từ fills; không double fee.

Funding/data/venue assumptions kế thừa contract hợp lệ, có label không venue-exact nếu thiếu. Không sửa assumptions theo arm. Raw costs/exposure/drawdown được giữ cho accounting/safety; báo cáo nghiên cứu chính vẫn dùng Sharpe và Sharpe differences.

### 6.2. Standardized candidate experiment

- Mọi candidate forward tại cùng origin bắt đầu từ same declared flat account/equity, không mang open positions của IS replay sang.
- Warm indicators bằng permitted historical bars, không gọi entry/exit decisions để tự tạo positions trong warmup.
- Candidate chọn tại decision cutoff, chỉ bắt đầu giao dịch sau common ready lag. Bars trong thời gian chờ được dùng cập nhật indicator tại thời điểm hợp lệ, không quay vào selection features.
- Raw IS replay cũng có declared flat initial account và pre-roll hợp lệ; full 180 ngày là economic scoring, pre-roll không nằm trong metric.
- Forward 56 ngày có same strategy/economics conventions; open position cuối window mark-to-market, không forced-close tùy arm.
- Giữ cohort là standardized performance của candidate, không giả thành counterfactual thay params trên live account có orders/campaigns.

Đây là cohort dùng tạo \(Y\), model validation và primary D1. So sánh IS180 với FWD56 có cùng economics, nhưng không có same chronological initial state; limitation này áp đối xứng và phải được nói rõ.

### 6.3. Continuous deployment

A/B/C bắt đầu với cùng incumbent/initial state, chọn trước evaluation và available đúng thời điểm. Không để B flat vì cold start trong khi A đã trade; trước FINAL mọi model phải đủ archive hoặc các arms dùng common explicit fallback initialization.

At each cutoff, common search tạo raw proposals; models fit trên available archive; admission trước queuing; actual engine áp pending/warmup/flat/campaign rules. Có common fallback về current eligible stock proposal cho model insufficiency, tránh giữ last B params nhiều năm vì threshold target cũ.

Không đổi alpha terminal/open-order behavior để ép activation mỗi fold. Nếu actual activation bị chậm, report request/ready/active/fill timestamps và active version mỗi segment. Đồng hồ standardized candidate và continuous-account phải được phân biệt trong output.

Cùng một selected params nhưng khác account state chưa chắc reuse full financial path. Cache account identity phải gồm initial state và approved schedule. Không copy B equity thành C chỉ vì parameters ở một cutoff trùng; chỉ reuse khi entire economic input/initial state/schedule identity được chứng minh.

### 6.4. Late jobs, unknowns và failed candidates

`MODEL_NOT_READY`, `SEARCH_NOT_READY`, `DEFERRED_CAMPAIGN`, `KEEP_INCUMBENT`, `UNCHANGED_PARAMS`, `GLOBAL_FALLBACK` là reasons khác nhau. Không dùng một counter «switch» thay toàn lifecycle.

Failed/pruned optimizer trials giữ lifecycle đúng; exception không thành COMPLETE với score giả. Candidate có IS Sharpe undefined không được dự đoán từ NaN coerced0. Raw stock anchor undefined khiến relative label không evaluable, phải ghi loss of paired coverage thay vì thay anchor hậu kiểm bằng future-best.

### 6.5. Scope điều gì được gọi regime contribution

- C−B trên standardized D1: evidence về lựa chọn tham số và generalization-gap retention.
- C−B continuous-account Sharpe: evidence về policy thực thi với delays/state đã mô phỏng.
- D2: evidence về age-window association của cùng frozen params, không universal causal effect của tuổi.
- JM states mô tả: không tự là forecast accuracy khi không có independent ground truth.
- Một scope có thể tốt ở standardized D1 nhưng không ở account; report hai kết quả, không chỉ chọn cái thuận lợi.

<a id="inference"></a>
## 7. Statistics và cách ra kết luận — không «âm sang dương»

### 7.1. Estimand chính và safeguards

Primary: mean paired signed reduction \(\overline R\) trên >=12 common folds của C−B.

Safeguard: mean paired standardized forward Sharpe difference \(\overline Q_{C-B}\), so với non-inferiority margin −0,10. Continuous-account Sharpe C−B là confirmatory implementation guard riêng nếu đăng ký inference cho nó; không dùng average fold Sharpe thay whole-account statistic.

Report đồng thời IS-reference contribution và FWD contribution của \(\overline R\). Nếu C chỉ chọn IS thấp hơn, kết luận «generalization gap nhỏ hơn» khác «Sharpe OOS tốt hơn».

### 7.2. Procedure default và giới hạn mẫu nhỏ

Trước FINAL, khóa `analysis_plan` gồm paired-fold bootstrap family, block length, resamples, seed, CI construction và required calibration tests. Starting procedure cho **mean fold-decay difference**: moving/circular block bootstrap trên paired origin tuples `(D_A,D_B,D_C,SR_IS,SR_FWD,context_flags)`, primary block length 4 folds; sensitivities 2 và 3 folds báo tất cả, không chọn cái significant.

Lý do cần blocks: các IS180 windows của folds cách 56 ngày chồng lấn; archive/model learning còn có dependence khác. Block4 là design starting point, không chứng minh dependence hết sau bốn folds. Với 12 folds chỉ có rất ít blocks hữu hiệu; CI có thể rộng hoặc không ổn định. Tăng số bootstrap draws không tạo thêm market information.

Default 5.000 resamples và seed fixed trong registration. CI có thể dùng basic bootstrap với centering/inversion được test; ghi rõ đây là approximation cho statistic **mean measured fold decay**, không phải một exact small-sample theorem. Không giả đây là trực tiếp phương pháp Sharpe-whole-path studentized của paper [S2].

Cho whole-account Sharpe difference, cần procedure time-series trên paired daily returns và recompute Sharpe trong từng resample; block choice freeze từ development. Không resample các annualized fold Sharpes rồi gọi đó là account Sharpe inference. Reuse implementation đã qualify nếu đúng estimand. [S2]

Unit/reference tests kiểm sign, centering, ties, constant differences, zero variance, missing rows và data-window count. Calibration nhỏ trên correlated synthetic outcomes chỉ kiểm estimator behavior trong fixture, không cấp market power hoặc learned-regime certificate.

Nếu procedure không đạt reference/calibration hoặc 12-fold interval quá degenerate để diễn giải, giữ descriptive results và `INFERENCE_UNQUALIFIED/LOW_PRECISION`. Không hạ block length hoặc chọn subset sau outcome để có confidence interval đẹp.

### 7.3. Multiple claims và effect precision

Primary một hypothesis family: C−B mean-decay hurdle và OOS-Sharpe safeguard là joint requirement cho một retention claim. Cả hai phải đạt; không lấy một cái thay cái kia. Nếu báo thêm confirmatory B−A, C−A, D2, ETH, đăng ký family và multiplicity procedure trước FINAL; mặc định các phần đó là secondary/descriptive nếu không có plan khác.

Giữ `marginal` và `simultaneous` intervals có label đúng. Không dùng marginal interval để quảng cáo family-adjusted proof. Không dừng khi p vừa <0,05. Nếu báo p-value, null hypothesis/hurdle và degenerate handling phải rõ; bootstrap fraction positive không tự là p-value hợp lệ.

### 7.4. Decision table bắt buộc

| Điều kiện | Kết luận được phép |
|---|---|
| Data/execution/selection invalid hoặc thiếu mandatory arm | `NOT_EVALUABLE` |
| <12 paired-valid folds | `INSUFFICIENT_PAIRED_FOLDS` |
| Hợp lệ, R point estimate >0 nhưng CI qua 0 | Quan sát có giảm, chưa chứng minh đáng tin |
| Cận dưới CI của R >0 nhưng <=0,20 | `REDUCTION_DETECTED_MAGNITUDE_UNPROVEN` nếu inference hợp lệ; chưa chứng minh hurdle 0,20 |
| **Cận dưới CI của R >0,20** và lower CI của mean Q(C−B) >−0,10, safety đạt | `MEANINGFUL_SHARPE_DECAY_REDUCTION_WITHIN_SCOPE` |
| Decay giảm nhưng OOS-Sharpe safeguard không đạt/chưa rõ | `GAP_REDUCTION_RETENTION_UNRESOLVED` hoặc deterioration được đo, không gọi retention success |
| Valid informative upper CI của R <0,20 | `NO_MEANINGFUL_REDUCTION_AT_0_20_WITHIN_SCOPE`; không suy tất cả regime vô ích |
| CI còn cắt qua0,20 | `INCONCLUSIVE_MAGNITUDE` |
| Upper CI của R <0 | `DECAY_WORSENED_WITHIN_SCOPE` |
| C toàn fallback, không state correction được exercise | Report whole-policy observed effect; `ACTIVE_JM_EFFECT_NOT_EXERCISED`, không bác bỏ active JM bằng fallback identity |
| C/B cùng actions và outcomes trong sample | `EXACT_ZERO_OBSERVED`; không automatic p=0/strong no-effect population claim từ degenerate bootstrap |

Không có điều kiện D_C phải âm hay SR_FWD,C phải dương. Trường hợp Sharpe OOS vẫn âm phải nói rõ absolute strategy quality chưa tốt, nhưng không xóa một retention improvement đạt definition.

Dùng `within_scope` và data-role label trong headline. Một retrospective 12-fold result có giá trị historical nhưng không thành prospective confirmation vì được chạy thêm một lần.

### 7.5. Model-diagnostic conclusion riêng

| Evidence | Diagnosis hợp lý |
|---|---|
| JM fit/filter/mapping fail | Technical model issue, chưa kiểm economic thesis |
| States hợp lệ nhưng thiếu recurring/support ở origins | Insufficient state evidence, không thêm K |
| States mô tả rõ nhưng relative-decay MAE/ranking và selections không hơn B | Representation chưa chứng minh task relevance |
| Prediction tốt hơn nhưng winner selection/account không tốt | Kiểm mapping prediction→selection hoặc delay/holding; không kết luận chỉ model yếu |
| Standardized D1 tốt, continuous account không giữ được | Execution/lifecycle contribution limitation |
| C prediction và retention đều yếu trên locked final đủ support | Evidence bất lợi cho JM recipe/selector đang thử; dừng version này |

Không bắt correlation giữa regime và realized outcomes phải mạnh mới cho technical PASS; đó là scientific result được báo sau run, không điều kiện để sửa labels.

---
## Ba phase triển khai và chạy — không mở thêm phase thứ tư

| Phase | Đầu ra thực tế bắt buộc | Điểm owner review |
|---|---|---|
| **SD-01** | Đúng Sharpe/economics; timeline đủ 12+12+12; INIT archive >=12 origins; runtime/candidate/latency contracts đã qualify | Duyệt input/metric/search/model defaults, budget và validation plan |
| **SD-02** | Global/rule/JM comparison trên >=12 validation folds; chọn một JM recipe; khóa final protocol | Duyệt model report, exact final folds và final budget; không yêu cầu validation dương |
| **SD-03** | Một final A/B/C run trên >=12 paired OOS folds, D1/D2/account Sharpe, inference, freeze/replay/handoff | Kết luận giữ baseline, ghi nhận reduction, hoặc dừng version này theo evidence |

Implementation substeps, retries và upgrades nằm trong ba phase; không biến mỗi helper thành một phase hoặc lập một roadmap 10 phase mới.

<a id="sd-01"></a>
## 8. SD-01 — Chuẩn hóa Sharpe và xây đủ lịch sử trước kiểm định

### 8.1. Mục tiêu và inputs

Mục tiêu: phép đo mới thật sự dùng Sharpe; đủ chronological history; actual runner không lặp lại lỗi cũ. Không phải chạy model tới khi có tín hiệu dương.

Inputs: current source/runtime, audit [I1], raw/data metadata, existing candidate/search/account artifacts, quotas thật và owner instructions. Artifact cũ chỉ đủ mean-return hoặc có horizon28 không được gọi là Sharpe56 evidence.

### 8.2. Các việc phải làm theo thứ tự

**SD01.1 — Pin source, quyền và receipts.** Inventory branch/commit, dirty diff, untracked outputs, import/native origins, protected-tree fingerprints, available budget. Không overwrite files đang dở. Mọi findings §0.2 có current disposition và tests/source refs.

**SD01.2 — Migration và thesis registry.** Tạo logical SD namespace và old→new mapping: Sharpe labels, relative target, no sign-switch, three arms, no dynamic timing. Xóa các old daily-return-floor dependencies khỏi new decision path bằng explicit removal/version, không sửa historical records. Hash/manifest không tự tham chiếu receipt mutable.

**SD01.3 — Coverage planner trước bulk compute.** Resolve exact INIT/VALIDATION/FINAL dates, startup gaps, completed-day coverage, first/last raw bars và D2 end. Freeze origin rule không dựa future Sharpe. Xuất counts `prior_mature_origins_at_each_cutoff`, `model_raw_prehistory`, `expected_forward_observations`. Thiếu coverage thì dừng với khoảng thời gian thiếu, không tìm một giai đoạn có output đẹp thay thế.

**SD01.4 — Metric/economics qualification.** Implement hoặc reuse canonical Sharpe wrapper; reconcile IS180/FWD56 counts, first return và timezone. Verify actual fees, equity-sizing, terminal MTM, pre-roll. Standardized candidate account và continuous account có separate cohort IDs. Không giữ IS sizing theo equity nhưng FWD fixed notional.

**SD01.5 — Actual path repair.** Verify stock Mode4 binding, common candidate pool, feature-only inference, pre-deployment admission và actual activation. Thêm hooks/counters rất mỏng vào existing runner; không rebuild lab orchestration. C-specific evaluation path không bị B-admission boolean chặn.

**SD01.6 — Resource và reuse qualification.** Một micro-profile đúng semantics; cache identity/invalidation; compact-retention vs audit parity trên actual candidate; stock cutoff replay và known-rejection fixture. Search budget128, probe policy nếu cần và model overhead phải fit resource allocation. Small technical pilot được gọi đúng, không thay INIT archive.

**SD01.7 — Xây INIT archive thực.** Chạy/reuse ít nhất 12 historical origins hợp lệ với candidate train180 và forward56; mỗi origin có anchor cùng representative panel. Lưu raw candidate IS/FWD daily returns đủ tính Sharpe lại. Label Y mới tính bằng raw Sharpe; không lấy labelreturn cũ nhân một hằng số.

Raw history/features của INIT giữ để SD-02 sinh causal model-vintage tapes theo từng penalty. Quy trình replay features tại historical origin chỉ dùng raw past; việc xây tape sau hôm nay không biến nó thành untouched real-time evidence. Ghi `CAUSAL_HISTORICAL_REPLAY` và data exposure.

**SD01.8 — Generate report, verify, commit.** Báo exactly what reused/ran, cost, validity findings đã sửa, INIT support, plan12validation/12final. SD-01 không có model victory/no-edge verdict. Owner review trước SD-02.

### 8.3. Tests bắt buộc SD-01

| Test ID | Expected behavior và evidence |
|---|---|
| `S1-T01-IDENTITY` | Wrong source/config/native/market hash làm preflight fail; protected paths không bị phase sửa |
| `S1-T02-SUFFIX` | Thay future bars/emissions/labels không đổi pre-cutoff search inputs, calendar hoặc features |
| `S1-T03-MATURITY` | First validation không được mở với11 priors; current row có future label không tự mature |
| `S1-T04-RETURN-BOUNDARY` | Fixture equity100→120→108: hai step returns đúng; clip không mất step đầu; actual180/56 counts |
| `S1-T05-SHARPE` | Known numeric series match independent formula; zero variance/NaN/no-data flagged; Sharpe scale/ties đúng |
| `S1-T06-POOL` | A winner luôn thuộc common pool; B/C prediction domain exact match cả pool, không chỉ representatives |
| `S1-T07-FEATURE-ONLY` | Xóa current future label không đổi prediction/selection; chỉ labels training đã mature mới được tham gia fit |
| `S1-T08-ACTUAL-ADMISSION` | Forced rejection: actual active version/orders không tiêu thụ rejected params; không chỉ check funnel string |
| `S1-T09-DECAY-RANKING` | Two-candidate fixture: min predicted Y và max predicted return chọn khác nhau; actual runner theo Y |
| `S1-T10-C-INDEPENDENT` | B chọn anchor nhưng C có candidate phù hợp trong fixture; C được chấm và proposal được thực thi đúng |
| `S1-T11-ECONOMIC-PARITY` | Audit/score hoặc fast/event candidate run match required equity/fill/sizing/timing semantics |
| `S1-T12-CACHE-READY` | Same semantic task/newrun→no new evaluation; cost/data change→miss; simulated ready không về0 |
| `S1-T13-INIT-ARCHIVE` | >=12 distinct origins có true maturity/labels/anchor/returns; no future-discovered candidate retrofit |
| `S1-T14-GATE-NEGATIVE` | Missing artifact, mutated receipt, BLOCKED JSON, no-tests-collected và mandatory skip không thành PASS |

Source code cần có actual unit/integration tests tương ứng. Bảng này không phải lời tuyên bố tests đã chạy. Những lỗi known phải có failing-before/passing-after hoặc explicit proof source đã sửa trước SD.

### 8.4. Exit gate SD-01

- **G1-SOURCE:** actual identity, protected-state diff và finding dispositions đủ.
- **G1-SHARPE:** S1-T04/05/11 pass, labels thật là Sharpe/economics đã pin.
- **G1-WIRING:** S1-T06…10 pass trên runner, không mocked-only thay actual execution check.
- **G1-TIMELINE:** timeline12INIT+12VAL+12FINAL feasible, explicit labels/latency và D2 scope.
- **G1-ARCHIVE:** INIT>=12 đã có actual/reused verified evidence; plan-only không đủ.
- **G1-RESOURCE:** resource envelope/micro-profile/cache/retention đủ nguồn, không hết quota mà đổi ID.
- **G1-REPORT:** report generated, registry đúng, no positive/negative model claim.

Tất cả mandatory gates pass → `WAITING_OWNER_REVIEW`. Nếu INIT chưa chạy vì budget, phase vẫn incomplete; không dùng «model chưa đủ support» để bỏ phần việc này.

<a id="sd-02"></a>
## 9. SD-02 — Kiểm định JM bằng relative Sharpe decay trên 12 validation folds

### 9.1. Mục tiêu

Đánh giá model có **task-relevant information** và khóa đúng một recipe cho final run. Không dùng final OOS làm validation; không chọn horizon/model family sau khi xem final result.

### 9.2. Các việc phải làm

**SD02.1 — Feature/model protocol.** Materialize exact three market features, model-fit180 feature window, raw-prehistory, standardization, K2, three normalized jump penalties, numerical solver/seed, vintage identity và filters. Verify warm filter dùng causal train terminal state, không future smoothing.

**SD02.2 — Two model layers.** Implement global contrast ridge và JM residual corrections theo §5.5, origin weights/penalties đúng normalization. Anchor zero test; candidate-state interaction test; same input row phải dự báo được dù current future label không có. Anchor Y=0 giữ trong evidence nhưng không tính là một extra informative training observation; khi fit loss, normalize trên non-anchor labeled challengers của origin.

**SD02.3 — Generate INIT causal tapes.** Mỗi penalty recipe được replay theo raw history available tại từng INIT origin; không fit final centroids rồi gán toàn INIT. State support đếm origins và recurrence, không số candidate rows. Những origins unknown giữ record, no fabricated state IDs.

**SD02.4 — Run 12 validation folds chronology.** Mỗi fold search chung; A/B/R_RULE/JM(c=.5/1/2) được evaluate trên same candidate pool. B và C coefficients chỉ fit prior matured Y rows. Freeze predictions/proposals trước forward outcomes, execute standardized forward union của representatives+all selected winners.

Models dùng same common raw-label archive để so công bằng; state tape khác nhau theo penalty là treatment representation. Weighted training count, context support và global fallback report mỗi cutoff. Nếu models có unsupported fold, toàn policy fallback được tính vào 12 folds; không chỉ báo confident subset.

**SD02.5 — Model quality report ba lớp.** Với mỗi recipe xuất causal/fit checks, state descriptions/occupancy/dwell/recurrent visits, MAE(Y) tính mean per-origin, rank diagnostics, selected-candidate Sharpe/decay và R vs B. Không dùng silhouette làm economic gate. Không đưa old return-RMSE vào bảng Sharpe labels mới.

**SD02.6 — Learning-to-action verification.** Chứng minh actual selection dùng minY, guard dùng relative predicted FWD-Sharpe identity, C không short-circuit, support thực thi và fallback về current-stock/global đúng. State effect có thể bằng 0 trên real sample; báo observed outcome, không buộc sửa thresholds cho có effect.

**SD02.7 — Chọn một recipe theo rule đã khóa.** Dùng §5.8, giữ cả bảng kết quả các designs thua/âm. B/rule/JM comparison phải cùng 12 folds. Không yêu cầu mean R dương để chọn; weak recipe được ghi `WEAK_DEVELOPMENT_EVIDENCE`. Technical invalid model khác weak scientific performance.

**SD02.8 — Final freeze và cost admission.** Khóa selected c, all ridge/shrinkage/support parameters, exact 12 final folds, guard, metrics/hurdles, paired inference, D2 anchors, seed, cell scope, resource/time limits và update policy. Frozen weights có thể refit causal trong FINAL theo rule, nhưng không chọn lại hyperparameters. Owner review trước SD-03.

### 9.3. Bảng model validation bắt buộc

```text
model_design_id / fold_id / decision_cutoff
train_mature_origin_count / candidate_rows / total_origin_weight
JM_fit_cutoff / solver_status / transform_hash / model_ready_at
state_at_origin / state_semantic_id / state_support_origins / recurrence_count
global_prediction_called / context_prediction_called
raw_candidate_pool_count / predicted_count / unknown_count
selected_candidate / fallback_reason / Y_hat / Q_hat
SR_IS_selected / SR_FWD_selected / D_selected
Y_MAE_origin / rank_metric_origin / valid_labels
R_vs_B / Q_FWD_vs_B
actual_run_refs / row_source_hash
```

Aggregate có riêng `planned=12`, `attempted`, `paired_valid`, `active_context_evaluated`, `context_correction_used`, `different_from_B`, `actually_activated`. Không dùng tất cả làm cùng một counter «model used».

### 9.4. Tests bắt buộc SD-02

| Test ID | Expected |
|---|---|
| `S2-T01-PAST-TRANSFORM` | Scaler/model fit không dùng validation/future features; suffix mutation không đổi prior predictions |
| `S2-T02-JM-FILTER` | Prefix-by-prefix online parity; no smoothed future labels; degenerate loss scale typed failure |
| `S2-T03-VINTAGE` | Permute namespace/state labels có semantic mapping không đổi economics; ambiguous state không auto-trigger |
| `S2-T04-RELATIVE-ALGEBRA` | Anchor Y_hat=0; Q_hat identity chính xác; minY ranking có known fixture |
| `S2-T05-WEIGHTS` | Nhân duplicate candidate rows cùng origin không nhân origin weight/support; anchor 0 không inflate sample |
| `S2-T06-CONDITIONAL` | Same-origin context interaction có thể đổi candidate order trong positive fixture; pure common offset không được quảng cáo conditional ranking |
| `S2-T07-INDEPENDENT-C` | B-anchor hoặc B-threshold outcome không ngăn C fit/score; genuine shared technical failure có reason |
| `S2-T08-SHRINK-FALLBACK` | Low-state support correction 0, unknown→global; không hard min/max one-point box |
| `S2-T09-TWELVE-VAL` | All comparisons paired-valid>=12; missing model fold không bị drop khỏi denominator thuận lợi |
| `S2-T10-MATURITY` | Labels chỉ vào sau available_at; feature inference không cần label; no chronological LOO future |
| `S2-T11-RECIPE-CHOICE` | Final-future mutation không đổi chosen recipe; ties deterministic; không chọn positive-only |
| `S2-T12-FREEZE` | Alter feature/penalty/margin sau freeze làm final preflight fail |

### 9.5. Exit gate SD-02

- **G2-ML-VALID:** causal features/JM/global/correction implementation đúng, actual validation artifacts có.
- **G2-VAL12:** mọi model comparison được claim có >=12 paired-valid validation folds; không dùng subset size khác nhau.
- **G2-INDEPENDENCE:** C evaluation độc lập B admission, support/fallback có measured evidence.
- **G2-RELEVANCE:** report descriptive/task quality đủ, kể cả negative result; không phải yêu cầu model thắng.
- **G2-FREEZE:** một JM recipe và final spec immutably sealed; no unresolved threshold/clock/candidate contract.
- **G2-OWNER:** review decision/remaining budget có reference thật.

Không có technically valid JM recipe thì ghi `BLOCKED_MODEL_VALIDITY`, không invent một model đủ K. Có valid recipe nhưng task evidence yếu thì final run vẫn được đề xuất một lần theo owner budget; không mở thêm c-grid, K hoặc feature families.

<a id="sd-03"></a>
## 10. SD-03 — Chạy một lần cuối A/B/C, Sharpe decay và kết luận

### 10.1. Điều kiện trước khi chạy

Receipts SD-01/02 còn hiệu lực, owner đã duyệt và final resource allowance đủ. Freeze verifier phải pass. Data role của FINAL, ngày bắt đầu/kết thúc, folds, candidates, guard, selected JM penalty, coefficient-update rule và statistics đều đã khóa.

Dùng một search seed primary và mapping seed theo origin đã pin. Không chạy thêm seeds vì kết quả xấu. ETH chỉ tham gia nếu registration trước FINAL có đủ 12 folds riêng và budget; không thêm ETH để cứu một kết quả BTC đã biết.

### 10.2. Trình tự chạy thực

**SD03.1 — Preflight không gọi engine.** Kiểm inputs, hashes, folds, prior labels và resource budget; xuất planned work. Thiếu required reference hoặc xuất hiện package/route không đúng thì dừng. Không chạy trước rồi sửa manifest cho khớp sau.

**SD03.2 — Common search tại từng cutoff.** Gọi stock Mode 4 thật, giữ đầy đủ trial lifecycle và candidate pool. Hash miền candidates đầu vào của A/B/C phải bằng nhau. Search chỉ đọc history; simulated ready lag theo registration, không bằng 0 vì cache hit.

**SD03.3 — Dự báo, lựa chọn, admission và activation.** B/C fit weights từ matured archive và được đánh giá độc lập. Quy tắc minY cùng relative-Sharpe guard quyết định proposals. Common safety admission xảy ra trước khi đưa vào engine queue. Fallback hoặc unchanged vẫn có selection record đầy đủ.

**SD03.4 — Candidate forward và labels mới.** Chạy đúng union cần cho standardized D1 của A/B/C và archive update. Predictions và representative selections đã freeze trước khi quan sát forward outcomes. Labels chỉ được expose sau maturity cho lần fit hợp lệ tiếp theo. Không sửa thuật toán theo point estimate đang thấy trong FINAL.

**SD03.5 — Continuous A/B/C accounts.** Chạy whole path với account, campaign và pending orders liên tục. Actual activation, callbacks và fills mang parameter version. Không tạo 12 reset accounts rồi nối equities thay deployment. Resume cần full state đúng hoặc deterministic prefix replay, không chỉ equity cuối.

**SD03.6 — Frozen continuations D2.** Chạy 12 prespecified final anchors với params giữ nguyên; H1/H2 liên tục theo §2.4. H1 phải match candidate forward H1. Không reset ở boundary. Nếu B/C có cùng toàn bộ economic inputs thì reuse được, nhưng không bỏ C vì source mang tên `FALLBACK_TO_B`.

**SD03.7 — Analysis không gọi engine.** Tính bảng Sharpe, D1, reduction R, decomposition, model metrics, D2 và continuous-account Sharpe từ stored outputs. Kiểm đủ 12 paired folds trước scientific verdict. Báo tất cả sensitivities đã đăng ký, không chọn riêng kết quả thuận lợi.

**SD03.8 — Kết luận, replay và handoff.** Áp §7.4/7.5, giữ negative/null/outlier cases. Kiểm representative traces và required regression tests. Same-contract replay có thể reuse verified computations; consistency qua cache không được gọi là cold native rerun. Sinh final report và current handoff từ evidence, commit scoped rồi chờ owner review.

### 10.3. Bảng 12 folds bắt buộc

| Nhóm | Columns bắt buộc |
|---|---|
| Identity | cell, fold_id, cutoff, train_start/end, forward_start/end, label_available_at, data role |
| Selections | A/B/C raw winner, approved winner, params hash, common pool hash, selector/model version |
| Readiness | model/search ready, actual activation, pending wait, first affected target/order/fill |
| Sharpe | raw IS và FWD Sharpe A/B/C, observation counts, standardized/economic contract |
| Decay | D_A, D_B, D_C, R(B−C), IS contribution, FWD contribution |
| Model | state, matured train origins, state support origins, correction used, fallback reason |
| Inference | paired-valid status, reasons cho rows invalid, exact trace refs |

Bảng tổng có mean/median R và mọi individual fold. Không chỉ báo aggregate để mất các folds bất lợi. Sharpe âm giữ nguyên. Zero-variance/no-trade cases có typed status; không chuyển undefined thành 0.

### 10.4. Tests và checks bắt buộc SD-03

| Test ID | Expected |
|---|---|
| `S3-T01-FREEZE-INPUT` | Mọi dependency đúng trước run; không có parameter/model/window change ngoài registration |
| `S3-T02-POOL-REPLAY` | Cùng cutoff tái lập stock pool/winner theo contract; miền A/B/C bằng nhau |
| `S3-T03-WINNER-EXEC` | Predicted Y ranking/guard khớp approved params và actual account consumption; có forced counterexample |
| `S3-T04-TWELVE-PAIR` | Primary có >=12 paired-valid OOS folds; D2 có >=12 anchors hoặc trạng thái incomplete rõ, không dùng ít hơn để kết luận |
| `S3-T05-ACCOUNT` | Cash/positions/fills/equity reconcile; không reset theo fold; terminal positions và first fee đúng |
| `S3-T06-DECOMPOSITION` | R=(IS_B−IS_C)+(FWD_C−FWD_B) khớp số học; sign không đảo theo outcome |
| `S3-T07-NO-SIGN-GATE` | Fixture decay 1.30→0.85 cho reduction 0.45; không đòi D<0 hoặc SR>0 |
| `S3-T08-FALLBACK-LINEAGE` | Fallback có params vẫn có D1/D2 rows; all-fallback C có scope đúng và không bị mất denominator |
| `S3-T09-D2-VERSION` | H1→H2 giữ cùng params/account continuation; ready/activation không bị giả là origin |
| `S3-T10-INFERENCE` | Paired blocks, thresholds, degenerate cases và calibration đúng; bootstrap không gọi engine |
| `S3-T11-REPORT-INTEGRITY` | Report tái sinh từ đúng refs; thiếu hoặc stale receipt/account thì không PASS |
| `S3-T12-BUDGET-SAFETY` | Cost, retries và cache savings đầy đủ; protected state không đổi; không reset quota |

### 10.5. Exit gate SD-03 và trạng thái kết thúc

- **G3-EXEC:** actual A/B/C continuous runs và required candidate outputs hoàn tất trong registered scope.
- **G3-PAIR12:** primary có >=12 paired-valid folds; D2 có >=12 anchors nếu phát hành D2 comparison.
- **G3-METRIC:** Sharpe, D1, relative labels và decomposition đúng; old return target không còn trong new path.
- **G3-MODEL:** C được đánh giá độc lập; JM/global usage có provenance; không che prediction weakness hoặc all-fallback.
- **G3-INFERENCE:** estimator/uncertainty đúng scope; thresholds đã freeze; không chọn lại winner sau FINAL.
- **G3-EVIDENCE:** required raw/compact paths, refs và receipts đủ; không thiếu account; final report tái lập được.
- **G3-CLOSE:** current handoff, upgrade history, remaining budget, limitations và owner decision đầy đủ.

Technical PASS không đòi Sharpe cải thiện. Thiếu 12 paired folds thì không được gắn `SCIENTIFIC_COMPLETE`; có thể đóng execution scope với `INCOMPLETE_RESEARCH_SCOPE` và liệt kê phần thiếu, không tự lấy dữ liệu tương lai. Nếu final hợp lệ nhưng không đạt hurdle, kết thúc với kết quả đó. **Không có SD-04.** Một ý tưởng khác cần chỉ dẫn owner mới, không kéo dài guide này để săn kết quả dương.

<a id="compute"></a>
## 11. Compute và cache: đủ chiều sâu, không tạo lại work vô ích

### 11.1. Reuse hợp lệ

- Một common search/cutoff cho A/B/C và các validation model designs; không chạy optimizer lại theo tên arm.
- Scoring candidates và model predictions tách biệt. Thử ba penalties JM chủ yếu tăng model work; chỉ thêm forward run khi registered designs chọn một candidate chưa nằm trong union đã planned.
- Một raw return path đủ dùng tính lại Sharpe, D1, labels và bootstrap; không backtest riêng cho từng metric.
- Stored 28-day labels không đủ thành56-day labels. Nếu raw path có đủ56 ngày và economics/initial state đúng, recompute; nếu thiếu, bounded engine continuation/replay theo capability thật.
- Candidate train180 và OOS56 là accounts/segments có initial-state conventions riêng. Không lấy cắt đoạn giữa path làm reset-account score nếu contract khác.
- D2 cần 112 ngày cùng params. Có prefix parity/checkpoint thật mới extend từ H1; không giả state bằng equity cuối.
- Exact params/economics/initial state/schedule trùng có thể reuse, nhưng mỗi logical arm vẫn có own lineage và charged-work accounting.

### 11.2. Identity và cache safety

Cache key bao gồm data-content/coverage/vintage, pre-roll, symbol/clock, alpha+effectiveparams, engine/native/route/scorer, economics, initial state và window. Model cache còn có target_definition=`RELATIVE_SHARPE_DECAY_V1`, training-origin/label-maturity hashes, features, state tape, penalties và fit policy.

Run ID, output path hay report prose là provenance, không tự đổi economic computation. Ngược lại, metric-definition thay thì labels/predictions/selection downstream phải invalidation, dù raw accounts có thể giữ. Target mới tuyệt đối không cache-hit vào old daily-return predictions chỉ vì shape giống nhau.

Publication crash-safe: data artifact hoàn tất → result hash → manifest → detached receipt seal. Không hash receipt rồi thêm trường PASS vào receipt sau đó. Verifier không được bỏ qua mismatch «vì đó là receipt».

### 11.3. Retention và concurrency

All trials giữ params, status, raw objective, IS Sharpe/support, hashes và exact winner reasons. Full required orders/fills/accounting trace giữ cho deployments và registered audit cases; candidate numerical paths có thể compact/write-to-disk theo block. Không giữ mọi per-bar Python object của mọi candidate trong RAM.

Parallel independent work trong allocation; sequential TPE ask/tell giữ chronology/reproducibility. Causal model updates phụ thuộc matured labels phải theo thứ tự; không parallel rồi cấp labels tương lai sớm. Thay scheduling strategy là versioned change, không gọi identical legacy run. [S4]

### 11.4. Cost ledger và stop

Trước bulk run ghi `planned/actual/reused/failed` cho:

```text
search studies / attempted trials / unique candidate accounts
representative forward runs / additional selected-winner forward runs
JM fits / global and correction fits
continuous deployment accounts / frozen D2 continuations
engine visited bars / callbacks / artifact bytes
CPU/wall/peak RSS / retries / remaining allowance
```

36 origins × 128 search attempts đã là 4.608 attempts trước deduplication, chưa forward/deployment. Đây là lý do bắt cost admission trước, không là lời hứa runtime. 8–16 trial micro-profile không thay configured128 primary search.

Không lấy cache savings làm quyền gọi thêm trials unregistered. OOM/timeout có postmortem và affected-stage checkpoint; tối ưu đúng chỗ trước khi xin budget mới, không đơn giản tăng timeout mỗi lần. Không hứa speedup chưa đo.

<a id="evidence"></a>
## 12. Evidence sau mỗi run và mỗi upgrade

### 12.1. Mọi run phải có report, kể cả thất bại

Run status: `PLANNED`, `RUNNING`, `COMPLETED`, `FAILED`, `TIMED_OUT`, `CANCELED`, `PARTIAL`, `BLOCKED`. Không chuyển failed numeric output thành zeros. Nếu worker crash, postmortem report lấy từ logs/checkpoints thật; measurements chưa ghi phải null.

Logical outputs có thể lưu chung existing TE/FP infrastructure, không tạo service/database mới:

```text
configs/sharpe_decay_sd_v1/
  registration.json
  protocol_migration.json
  timeline.json
  metric_contract.json
  model_and_selector_spec.json
  analysis_plan.json
  resource_budget.json

evidence/sharpe_decay_sd_v1/<run_id>/
  input_manifest.json
  attempts/...
  candidate_pool_refs.json
  labels_and_prediction_refs.json
  selections_and_activation_refs.json
  account_refs.json
  sharpe_fold_table.jsonl
  model_quality.json
  inference_results.json
  gate_receipt.json
  gate_receipt.sha256
  report.md

handoff/
  SD_CURRENT.md
  SD_RUNBOOK.md
  SD_UPGRADE_HISTORY.md
```

File names là logical contracts; được map vào schema hiện có, nhưng mapping phải duy nhất và truy được. Raw data lớn chỉ cần immutable reference/read-only path có hash và availability; raw selected/evaluation outputs cần đủ để người review recompute Sharpe, không chỉ summary declarations.

### 12.2. Mandatory machine-readable rows

**Candidate label:**

```text
origin / candidate_id / params_digest / anchor_id / common_pool_digest
IS_window / forward_window / daily_return_path_refs
SR_IS_candidate / SR_FWD_candidate / SR_IS_anchor / SR_FWD_anchor
D_candidate / D_anchor / Y_relative_decay
label_end / label_available_at / feature_available_at
candidate_discovered_at / inclusion_reason
metric_contract / economic_contract / initial_state_contract
validity_status / reason / source_hash
```

**Prediction and selection:**

```text
fold / arm / decision_time / train_origin_ids / count_mature_origins
model_id / recipe_c / feature_scaler_digest / state_vintage_key
base_model_ready / correction_ready / state_support_origins
evaluated_independently_of_B / predicted_candidate_count
Y_hat / Q_hat / eligible / ranking_position / tie_reason
raw_proposal / approved_proposal / fallback_reason
search_ready / model_ready / indicator_ready / actual_activation
first_affected_order/fill refs / actual parameter version
```

Không yêu cầu labelfields để inference row tồn tại. `labels_and_predictions` có thể chung storage nhưng schemas/past filters phải tách.

### 12.3. Run Markdown template

```markdown
# SD run — <run_id>

## 1. Identity và scope
Phase / guide version / branch / commit / dirty diff / engine-native hashes.
Registration / exact data role / windows / common pool/search/metric contracts.
Technical status / model support / research status / owner approval.

## 2. Câu hỏi và thay đổi của lần này
Primary hypothesis, parent run, những gì giữ nguyên, những gì đổi.
Không nói chung «tối ưu tiếp» khi không có cụ thể source/spec/evidence.

## 3. Planned so với actual
| Hạng mục | Planned | Actual | Evidence/reason |
|---|---:|---:|---|
| INIT mature origins | | | |
| Validation paired folds | | | |
| Final paired folds | | | |
| Search attempts / unique candidates | | | |
| C independent evaluations / corrections / fallback | | | |
| Forward / continuous / D2 accounts | | | |

## 4. Validity và exit gates
| Gate | Expected behavior | Actual | Test/run/hash reference | Status |
|---|---|---|---|---|

## 5. Regime model
Causality/solver/state mapping; state profiles, recurrence, support, novelty.
Y-MAE, ranking và selection outcome theo từng validation/eval origin.
Global và rule-based comparators trên cùng12fold khi phát hành comparison.

## 6. Sharpe và decay
Bảng toàn bộ folds: IS/FWD Sharpe A/B/C, D_A/D_B/D_C, R và decomposition.
Mean/median R, FWD-Sharpe difference, CI/margins, inference limitations.
D2 cùng params; continuous-account Sharpe tách riêng.
Sharpe âm và decay dương vẫn giữ; không chờ sign đổi mới công nhận giảm.

## 7. Compute và failure
Actual engine calls/bars, cache, elapsed/CPU/peak RSS, artifact size, retries.
Missing artifacts/undefined metrics/blocked work, không fake0 hoặc PASS.

## 8. Điều có thể và không thể kết luận
Actual model được exercise hay fallback? Giảmgap do IS thấp hay OOS tốt?
Within-scope result; data consumed/fresh; không biến technical PASS thành edge.

## 9. So với parent run/upgrade
Comparable contract hay không? Metric changes/cost changes/parity evidence.
Những claims/receipts bị invalidate; reanalysis hay actualengine rerun.

## 10. Next authorized action
Một hành động cụ thể, remaining budget, owner decision cần có.
Nếu final run đã kết thúc: dừng version/ghi nhận result, không tự thêm model sweep.
```

Số trong report được generate từ exact artifact refs. Narrative có thể phân tích, nhưng không sửa số tay hoặc chỉ giữ thuận lợi. Charts nếu tạo: một chart riêng cho fold R, một chart IS/FWD Sharpe, một chart D2; không cần dashboard/platform mới.

### 12.4. Upgrade types và nghĩa vụ

| Loại upgrade | Phải làm | Không được làm |
|---|---|---|
| Report/prose only | Regenerate đúng refs, pin renderer version | Ép rerun engine dù economics không đổi |
| Metric bugfix | Recompute từ đủ raw paths; invalidate affected labels/claims | Gọi changed Sharpe là new independent evidence |
| Performance equivalent | Prove parity+measure runtime/memory trên samecontract | Chỉ so final equity rồi bỏ timing/fill khác |
| Correctness repair | Before/after regression; rerun affected financial path | Chỉ sửa report label để hợp thức hóa old account |
| Target/model/threshold change | New specversion, exposure/parent refs, owner approval | Tuning sau final rồi gọi preregistered |
| Data/engine version change | Scope-specific requalification và invalidation | Reuse incompatible prediction/account cache |

Mỗi upgrade có `upgrade_id`, parent/new digests, rationale, affected components, before/after tests, actual run refs, metric/economic impact, claim invalidation và owner decision. Source changed nhưng targeted execution chưa rerun phải ghi pending, không issue certificate.

### 12.5. Current guide phải được viết lại sau từng run

`SD_CURRENT.md` là trạng thái hiện tại, được tạo lại từ ledger; không thay immutable specification hoặc lịch sử.

```markdown
# SD_CURRENT
Current source/runtime and approved registration:

| Phase | Technical | Research/scope | Owner | Evidence |
|---|---|---|---|---|
| SD-01 | | | | |
| SD-02 | | | | |
| SD-03 | | | | |

Latest actual run và parent upgrade:
Known facts with evidence:
Missing/invalidated evidence:
Archive/validation/final paired-fold counts:
Model support / correction / fallback usage:
Sharpe-decay results and exact claim limits:
Remaining budget:
Next authorized action:
Protected worktree status:
```

Các câu «đã xong», «có edge», «không có edge», «model yếu» phải có scope/evidence. Không update handoff bằng cách copy assessment cũ khi current run thay threshold/model.

<a id="verifier"></a>
## 13. Executable gates, CLI và hoàn tất đúng phạm vi

### 13.1. Gate receipt tham chiếu — không phải receipt PASS

```json
{
  "schema": "regime_lab.sharpe_decay_phase_gate.v1",
  "phase_id": "SD-03",
  "guide_version": "SD-GUIDE-1.0",
  "registration_digest": null,
  "source_dependency_digest": null,
  "technical_gate": "NOT_RUN",
  "model_status": "NOT_ASSESSED",
  "research_status": "NOT_ASSESSED",
  "data_role": null,
  "n_validation_paired": 0,
  "n_final_paired": 0,
  "n_d2_paired": 0,
  "required_gates": [],
  "gate_results": [],
  "actual_run_refs": [],
  "verified_reuse_refs": [],
  "test_execution_refs": [],
  "protected_state_refs": [],
  "remaining_resource_budget_ref": null,
  "open_blockers": [],
  "owner_review": {"status": "PENDING", "decision_ref": null},
  "can_start_next_phase": false
}
```

Null fields chỉ là template; actual gate phải có resolved values khi phase yêu cầu. Receipt được seal detached sau finalize, không mutate lại rồi bỏ qua hash mismatch.

### 13.2. Verifier kiểm gì?

1. Required source/config/data/engine identities đúng; references tồn tại, readable và hash khớp.
2. Gate IDs đúng phase; tests có actual commands, counts, exit status và logs. Mandatory skip/xfail/no-collection không thành PASS.
3. Actual financial runs được phase yêu cầu đã hoàn tất; fixture/mock không thay market path.
4. Availability, common pool, C độc lập, minY winner và admission-before-execution được kiểm bằng hành vi.
5. Paired-fold counts lấy từ actual rows đúng windows, không lấy từ `planned_count` tự khai; không bỏ failures khỏi denominator.
6. Metric contract thực là Sharpe; old daily-return floor không reachable trong selector mới.
7. Account outputs không bị cắt ngầm; undefined/censored records giữ typed status.
8. Resource và protected-state checks đúng scope; receipt không tự tạo owner approval.
9. Narrative claim không mạnh hơn research status, model usage và validity.
10. Downstream chỉ reuse receipts khi dependencies liên quan không đổi; sửa README không buộc rerun tài chính vô lý.

### 13.3. CLI không được bịa API

Tái sử dụng existing `scripts/te.sh`, `scripts/run_time_edge.py` hoặc FP runner nếu actual parser hỗ trợ. Có thể thêm thin wrapper `scripts/run_sharpe_decay.py`; đây là **tên đề xuất cần implement**, không phải công cụ đã có.

Logical actions cần có: `plan`, `run`, `resume`, `verify`, `report`, `freeze`. Phải verify `--help`/schema và dry-run trước đưa command vào runbook. Plan/verify/report không gọi engine ngoài explicit recalculation task đã đăng ký.

Mỗi actual invocation lưu argv, cwd, interpreter, env/request hashes, real start/end, exit code, semantic status, stdout/stderr/result refs. Process exit 0 nhưng payload BLOCKED không làm gate PASS.

### 13.4. Final closure labels

```text
TECHNICALLY_COMPLETE / INCOMPLETE_TECHNICAL_SCOPE
RESEARCH_COMPLETE_WITHIN_SCOPE / INCOMPLETE_RESEARCH_SCOPE
MODEL_EXERCISED / MODEL_PARTIALLY_EXERCISED / GLOBAL_FALLBACK_ONLY
MEANINGFUL_SHARPE_DECAY_REDUCTION_WITHIN_SCOPE
REDUCTION_DETECTED_MAGNITUDE_UNPROVEN
GAP_REDUCTION_RETENTION_UNRESOLVED
NO_MEANINGFUL_REDUCTION_AT_0_20_WITHIN_SCOPE
INCONCLUSIVE_MAGNITUDE / LOW_PRECISION
NOT_EVALUABLE / INSUFFICIENT_PAIRED_FOLDS
```

Một final run có thể technical PASS và research INCONCLUSIVE; điều đó không phải lỗi. Mandatory run thiếu thì không gọi technical complete. C toàn fallback thì không gọi một JM active trial bị bác bỏ, dù observed result của whole mixed policy đúng.

<a id="done"></a>
## 14. Definition of Done — đúng ba phase và bằng chứng đủ nghĩa

- [ ] Current source/runtime/branch đã verify; old findings có disposition, lịch sử không bị viết lại.
- [ ] Sharpe là target/primary metric thật; old daily-return floors đã được loại khỏi đường mới.
- [ ] Có >=12 INIT matured origins trước validation, >=12 validation folds và >=12 paired final folds riêng.
- [ ] Timeline, lag, prehistory và D2 không dùng future-unavailable data hoặc fabricated bars.
- [ ] A/B/C cùng full eligible pool; inference B/C không phụ thuộc current future label tồn tại.
- [ ] C được chấm độc lập B admission; actual model usage/fallback có evidence.
- [ ] JM K2, scalers, filter, semantic identity và state-conditioned shrinkage được kiểm đúng.
- [ ] Actual selector xếp bằng predicted relative Sharpe decay; relative guard đúng vai trò.
- [ ] Admission trước actual deployment; initial state, sizing, fees và clocks nhất quán.
- [ ] Standardized D1 tách khỏi continuous account; R decomposition và sign đúng.
- [ ] D2 giữ cùng params trong continuation H1→H2 và có >=12 paired anchors khi phát hành comparison.
- [ ] Thresholds 0.20/0.10 điểm Sharpe được freeze trước outcome; không có sign-switch gate.
- [ ] CI, support, concentration, model quality và scope được báo trung thực; 12 folds không bị mô tả là bảo đảm power.
- [ ] Mọi run kể cả fail có report; mỗi upgrade có before/after evidence và invalidation đúng.
- [ ] `SD_CURRENT.md` và runbook phản ánh latest actual artifacts; receipt seal/hash đúng.
- [ ] Final decision không vượt evidence, không tự mở phase/model family mới.

> **Câu hỏi cuối báo cáo phải trả lời:** trong fixed-calendar, common-candidate experiment đã khóa, JM có làm **Sharpe decay thấp hơn một mức đáng quan tâm** so với global selector không; phần giảm đó đến từ IS reference hay forward retention; model đã thực sự được thử chưa; và mức độ chắc chắn cho phép nói đến đâu?
>
> **Không cần đổi dấu để công nhận giảm. Không cần tự trấn an bằng một model phức tạp hơn khi evidence không ủng hộ.**

<a id="sources"></a>
## Nguồn, provenance và giới hạn của tài liệu

### I1 — Audit FP-01…FP-10 trong cuộc trao đổi

`REGIME_LAB_FP01_FP10_OBJECTIVE_AUDIT_VI.md`, ngày 24/09/2026. Nguồn snapshot `regime-lab-main (2).zip`, archive hash ở §0.1. Các references F02…F10 thuộc audit này; audit phân biệt recorded artifacts, pure source probes và marketruns chưa rerun. Fileguide không cấp lại certificate runtime mới.

### I2 — Forward-persistent guide trước

`REGIME_LAB_FORWARD_PERSISTENT_PLATEAU_GUIDE_VI.md`. Kế thừa engine/safety/chronology/evidence/owner-review rules. SD thay target, timeline, modelpreset và primary comparison theo yêu cầu mới. Không biến target mean return cũ thành Sharpe chỉ bằng đổi tên.

### S1 — Regime model và task-aligned calibration

Yizhan Shu, Chenyu Yu, John M. Mulvey: *Downside Risk Reduction Using Regime-Switching Signals: A Statistical Jump Model Approach*, arXiv:2402.05272, bản v3 17/09/2024. Nguồn hỗ trợ nguyên tắc JM persistence và strategy-linked validation; đây là nghiên cứu equity allocation, không xác nhận Sharpe-decay edge của crypto lab.

```text
https://arxiv.org/abs/2402.05272v3
Truy cập xác minh: 24/09/2026
```

### S2 — Sharpe inference

Olivier Ledoit, Michael Wolf: *Robust performance hypothesis testing with the Sharpe ratio*, Journal of Empirical Finance 15(5), 2008, 850–859. Tác giả đề xuất robust/time-series inference cho Sharpe differences khi returns có heavy tails hoặc dependence. Guide dùng nó để giới hạn cách diễn giải; origin-block mean-decay procedure của lab không tự là implementation đầy đủ của paper.

```text
https://www.ledoit.net/jef2008_abstract.htm
Truy cập xác minh qua abstract được lập chỉ mục: 24/09/2026
```

### S3 — Overfitting trong model selection

Gavin C. Cawley, Nicola L. C. Talbot: *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation*, JMLR11, 2010, 2079–2107. Hỗ trợ việc tách validation chọn recipe khỏi final evaluation và thừa nhận variance của model-selection criterion.

```text
https://www.jmlr.org/papers/v11/cawley10a.html
Truy cập xác minh: 24/09/2026
```

### S4 — Reproducibility của optimizer

Optuna official FAQ, mục reproducible optimization. Sequential ask/tell, fixed seeds và deterministic objective là các thành phần cần kiểm khi tái lập; parallel optimization có nondeterminism. Website tham khảo không cấp phép upgrade dependency host.

```text
https://optuna.readthedocs.io/en/v4.9.0/faq.html
Truy cập xác minh: 24/09/2026; runtime của lab vẫn pin version thực đang được duyệt.
```

**Tất cả defaults 56 ngày, 12+12+12 origins, JM K2, grid 0.5/1/2, ridge penalties 10, các margins 0.20/0.10 và bootstrap-block convention là thiết kế nghiên cứu SD-1.0. Chúng không phải tham số đã được chứng minh tối ưu, không phải kết quả backtest mới, và không bảo đảm regime sẽ giảm decay.**
