# REGIME-LAB — VOLATILITY-CONDITIONED WFO V1
## Guide triển khai năm phase: tiếp nhận model H14 → phép đo đúng → selection có đối chứng → policy tuần tự → đánh giá Sharpe decay

**Version:** `VOL-WFO-V1.0`  
**Ngày soạn:** 28/09/2026  
**Study ID đề xuất:** `btc_volatility_conditioned_wfo_v1`  
**Namespace:** `VWFO-01` → `VWFO-05`, đúng năm phase.  
**Scope:** `A-SC / BTCUSDT / 15m`; instrument/venue contract phải đối chiếu actual adapter.  
**Parent:** `BTC-RPS-V1.2 / MODEL-FIRST + REGIME DURATION`, mục 18 về WFO bridge.  
**Nguồn mới:** `handoff.zip`, đặc biệt `handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md` và `handoff/RPS_CURRENT.md`.  
**Trạng thái:** đặc tả giao việc mới. Chưa sửa repository, chưa chạy model mới, chưa chạy QuantBT hoặc cấp phép live trong lúc soạn tài liệu.

> **Câu hỏi duy nhất của phép thử chính:** trên cùng lịch WFO, cùng candidate pool và cùng economics, thông tin dự báo volatility H14 có giúp chọn params với **Sharpe decay thấp hơn** so với các selectors không có thông tin dự báo đó không?
>
> **Không yêu cầu đổi dấu:** decay giảm từ 1,30 xuống 0,85 là giảm 0,45 điểm Sharpe dù vẫn dương. Sharpe forward còn âm không xóa một cải thiện tương đối, nhưng chưa cho phép giao dịch tiền thật.
>
> **Giữ chiều sâu:** ít nhất **128 attempted strategy trials/cutoff/sampler**, **12 development folds chung**, **12 paired-valid final WFO folds chung**; archive chọn params có ít nhất 12 origins đã trưởng thành trước development.
>
> **Tách ba thứ:** dự báo volatility tốt ≠ chọn params tốt ≠ đủ điều kiện live. H14 là hypothesis được đưa sang nghiên cứu WFO; H28 là secondary chưa chứng minh vượt baseline. Không tăng leverage, không risk-scaling theo regime và không event-triggered refit trong treatment chính.
>
> **Tiếp tục từ công việc đã có:** không làm lại toàn bộ MF/FP/SD. Chỉ đối soát bàn giao, sửa domain blockers đang ảnh hưởng đường chạy mới và bổ sung những outputs còn thiếu. Một tài liệu handoff không thay thế raw forecasts hoặc actual financial traces.

---

## Điều hướng

[0. Nguồn và giới hạn](#s 0) · [1. Evidence và migration](#s 1) · [2. Rules](#s 2) · [3. Thiết kế nghiên cứu](#s 3) · [4. Forecast contract](#s 4) · [5. Timeline](#s 5) · [6. Search/Mode 4](#s 6) · [7. Candidate archive](#s 7) · [8. Selection](#s 8) · [9. Execution/live policy](#s 9) · [10. Metrics/inference](#s 10) · [11. Compute/codebase](#s 11) · [12–16. Năm phase](#s 12) · [17. Reports/upgrades](#s 17) · [18. Config](#s 18) · [19. Definition of Done](#s 19) · [20. Nguồn](#s 20).

<a id="s 0"></a>
## 0. Nguồn, mức bằng chứng và cách dùng guide

### 0.1. Những gì đã thực sự đọc khi soạn

- Đọc bytes của `handoff.zip`, trích xuất các files thuộc `handoff/`; không thực thi scripts/diff trong archive.
- Đọc toàn bộ handoff volatility mới và `RPS_CURRENT.md`; tham chiếu reviewer-fix handoff để biết những phần đã được báo sửa.
- Đối chiếu mục 18 của guide MODEL-FIRST V1.2 và consumer contract hiện có trong cuộc hội thoại.
- Tính lại confusion-matrix arithmetic được in trong handoff. Đây là phép tính từ Markdown, **không phải** tái chạy model hoặc xác minh `study_results.json`.
- Tài liệu chính thức bên ngoài chỉ được dùng cho các lưu ý API/thống kê cụ thể; không thay nội dung nguồn bàn giao.

| Nguồn nhận được | SHA-256 |
|---|---|
| `handoff.zip` | `3722d70827a4ff84ce68bc765ad01bc472304fa102adf4da7d92ce50417d6c64` |
| `handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md` | `692da0a9ad5c030bd5184bd93e88906028cf28f08838be262f6b62f05a201ddc` |
| `handoff/RPS_CURRENT.md` | `a007920cbe0eb642d952b7af7058ad243e84411b1533b4ea94e6e3f7afd59768` |

User báo `main` tại commit `8cc366cb`, đồng bộ với `research/btc-regime-forecast-v1`. **Commit/remote state là thông tin bàn giao, chưa được xác minh trực tiếp khi soạn.** Agent kiểm trên host, không reset/checkout đè worktree theo một SHA viết trong tài liệu.

### 0.2. Những files chỉ được handoff tham chiếu, không có bytes trong ZIP này

```text
BTC_VOLATILITY_CONDITIONED_REGIME_SELECTION_SPEC_V1_VI.md
configs/btc_volatility_forecast_v1/registration.json
scripts/exp_volatility_horizons_study.py
evidence/exp_volatility_horizons_v1/study_results.json
src/crypto_regime_lab/regime_forecast/*
tests/regime_forecast/*
raw forecast/label/temperature/model-vintage payloads của study H14/H28
```

ZIP là handoff bundle, không phải toàn repository. Agent tiếp theo phải đọc các files trên **từ working copy đã có trên host** trước bulk WFO. Không yêu cầu Bobby gửi lại toàn repo nếu files đã nằm trong repo/storage được phép đọc. Nếu một file thực sự không còn, ghi exact missing dependency và chỉ khôi phục payload cần thiết.

Các đường dẫn `file:///root/...` trong handoff là địa chỉ máy nguồn, không là HTTP endpoint và không tự là sandbox path. Không giả chúng đã được reviewer mở thành công.

**Phạm vi truy cập:** không có source code/model payload mới trong ZIP handoff để tác giả guide kiểm actual implementation. Các module cũ là bản đồ đối chiếu, không chứng nhận HEAD mới. Không dùng những source thiếu này để suy rằng agent chưa implement; agent trên host đọc và xác nhận chúng trong VWFO-01.

### 0.3. Evidence tags phải dùng trong reports

```text
HANDOFF_REPORTED           : tác giả bàn giao báo cáo
ARITHMETIC_RECHECKED       : tính lại từ bảng Markdown đã nhận
RAW_FORECAST_VERIFIED      : đã đọc và tái tính từ forecast ledger thật
SOURCE_PATH_VERIFIED      : đã kiểm actual functions/import path
ACTUAL_ENGINE_RUN         : financial outputs từ QuantBT chạy thật
VERIFIED_CACHE_REUSE       : exact semantic computation được tái sử dụng
SPECIFICATION_NEW         : thiết kế mới trong guide này
NOT_RUN / NOT_AVAILABLE   : chưa thực hiện / chưa có nguồn
```

Không nâng `HANDOFF_REPORTED` thành `RAW_FORECAST_VERIFIED` vì file có tiêu đề “skill certificate”. Không hạ evidence thật của model chỉ vì reviewer chưa được cung cấp bytes; phân biệt thiếu source ở bundle với source không tồn tại trên host.

<a id="s 1"></a>
## 1. Tiếp nhận kết quả model, không sửa âm thầm câu chuyện nguồn

### 1.1. Kết quả được handoff báo cáo

| H | Accuracy báo cáo | Macro-F1 báo cáo | BSS so persistence | Vai trò trong guide mới |
|---|---:|---:|---:|---|
| 14 ngày | 62,5% | 0,493 | +0,0791 | Forecast candidate chính, cần đối soát bảng và raw ledger |
| 28 ngày | 58,3% | 0,442 | −0,0050 | Secondary/descriptive; không coi đã vượt baseline |
| 56 ngày | 33,3% | 0,271 | −0,2150 | Kết quả lịch sử, không dùng để chọn params ở study mới |
| 90 ngày | 29,2% | 0,292 | −0,4157 | Kết quả của multi-horizon study mới; không trộn với run MF cũ |

Handoff §2 ghi `M4_LGBM_CONSERVATIVE_SLOW`, 38 features, median imputation từ train, temperature scaling từ validation. §3 ghi 48 weekly origins từ 06/2025 đến 05/2026 và refit hàng tuần. Các chi tiết này phải map vào exact registry/actual class trên host; không rebuild model bằng vài thông số copy từ report.

`RPS_CURRENT.md` còn giữ kết luận đóng WFO của MF H56/H90, rồi bổ sung nhánh H14/H28. Đây là **hai research versions**. Không đổi receipts của MF thành qualified; tạo bridge status mới dành riêng H14.

### 1.2. Mâu thuẫn cần đối soát một lần, bằng raw source

Handoff §3.2 in confusion matrix H14, hàng = truth và cột = prediction:

```text
             pred LOW  pred MID  pred HIGH
true LOW         21       2         2
true MID          7       6         3
true HIGH         3       3         1
```

Từ chính bảng này:

- Số đúng = 21+6+1 = **28/48**, accuracy = **58,33%**, không phải 62,5%.
- Macro-F1 = **0,44943**, không phải 0,493.
- LOW recall 21/25 = 0,84; precision 21/31 ≈ 0,67742; F1 = 0,75: khớp báo cáo.
- HIGH recall 1/7 ≈ 0,14286; precision 1/6 ≈ 0,16667. Không coi classifier là công cụ bảo vệ HIGH_VOL đã đáng tin.
- Từ hai Brier scores làm tròn 0,5704 và 0,5253: BSS ≈ **0,07907**. Confusion matrix không đủ để tái tạo Brier score hoặc CI.

H28 matrix trong handoff cho 28/48 đúng, khớp 58,33%, và HIGH recall = 0/4. Không đổi dữ liệu để ép H14 accuracy thành một trong hai số; đọc forecast ledger, xác định version/cohort/class-order nào đúng và publish correction có liên kết nguồn gốc.

**Đây là blocker của claim và calibration tiếp nhận, không phải lý do mở lại cuộc thi models hoặc viết lại cả MF.** Nếu lỗi chỉ ở Markdown, sửa report từ raw predictions, không rerun engine/model.

### 1.3. Các claims cần giữ đúng mức

| Nội dung bàn giao | Cách sử dụng trong WFO V1 |
|---|---|
| “Skill dương có ý nghĩa thống kê” của H14 | Lấy exact paired losses/CI/procedure từ source; BSS point dương tự nó chưa chứng minh significance |
| “Bắt đáy biến động” | Hiểu là nhận diện LOW_VOL theo taxonomy, không phải dự báo đáy giá BTC |
| H28 “cadence-aligned” | Tên vai trò thiết kế; BSS −0,005 không thành predictive qualification |
| Mean duration 12,1 ngày, median 10,0 ngày trong handoff §1 | Giữ đúng mean/median; `RPS_CURRENT.md` gọi 12,1 là median, cần source đối soát |
| H14 khớp hoàn hảo “chu kỳ vật lý” | Không dùng làm premise. `OBS14_CONFIRM3_V1` phụ thuộc lookback/confirmation; duration là estimate theo detector, không thời gian tự nhiên bất biến |
| LOW_VOL cho phép tăng đòn bẩy hoặc TP chặt an toàn | Giả thuyết chưa được kiểm bằng alpha/engine. Loại khỏi treatment chính |
| 67/67 tests, QuantBT untouched, zero financial calls | Thành quả model được ghi nhận theo handoff; không thay financial-path certification của WFO |

BSS âm so với persistence không đồng nghĩa “kém hơn random guessing”. Không dùng daily-return hoặc max drawdown p-value thay Sharpe-decay criterion của owner.

### 1.4. Đóng/mở bridge đúng version

```text
old_MF_H56_H90_bridge = CLOSED (giữ nguyên lịch sử)
new_H14_WFO_bridge    = PENDING_HANDOFF_RECONCILIATION
```

Trong VWFO-01:

- Nếu raw evidence/maturity/model lineage và scoped H14 qualification khớp: `MODEL_HANDOFF_ACCEPTED_H14`.
- Nếu point skill dương nhưng CI/selection-exposure chưa đủ: `EXPLORATORY_MODEL_EVIDENCE`; chỉ mở controlled WFO theo một owner decision ghi rõ experimental scope. Không cấp qualification giả để vượt gate.
- Nếu timestamp/model-data leakage hoặc artifacts mâu thuẫn chưa giải quyết: `BLOCKED_MODEL_PROVENANCE`.
- Request hiện tại của Bobby cho phép soạn và chuẩn bị bước WFO; không tự cấp quota, quyền sửa kernel hoặc live-trade permission. Agent lưu actual approval theo workflow đã có.

H14 được chọn sau khi đã xem nhiều horizons trên cùng 48-week period phải có `HORIZON_SELECTED_ON_EXPOSED_DATA`. Dùng lại khoảng đó là retrospective exploration, không independent prospective proof. Không đòi xóa dữ liệu này; chỉ giữ đúng claim.

<a id="s 2"></a>
## 2. Rules bắt buộc

### 2.1. Authority, source, permissions

**R01.** QuantBT là financial authority duy nhất. Không tự sinh fills, tự match orders, tự ghép candidate returns thành continuous policy equity.

**R02.** Giữ `/root/bobby/pool_alpha/quantbt` read-only. Handoff báo version 1.1.1; verify actual import/native/build. Không sửa site-packages, kernel hoặc original alpha để vượt gate. Thiếu public capability → minimal reproducer + owner decision.

**R03.** `run_cutoff_walk_forward` là wrapper được handoff chỉ định cho actual policy run. Agent inspect signature/source/`--help`; không bịa kwargs. Thin selector adapter được phép trong lab, nhưng phải gọi đúng engine scorer, stock selector và execution path.

**R04.** Chỉ A-SC/BTCUSDT/15 m. Execution 1 m và volatility features daily không là timeframe-shopping. Không đổi spot/perp, shorting hoặc leverage ngầm.

**R05.** Dùng approved `data_loader`, symbols explicit, `check_val=True`. Không override `DATA_ROOT`, không đọc canonical storage để bypass manifest. Optional external sources thiếu thì giữ excluded, không kéo thêm Coin Gecko/OKX/options vào WFO này.

**R06.** Không destructive Git commands, không xóa untracked evidence, không `git add .`, không tự push/merge. Bắt đầu từ working tree hiện tại; branch/dirty state và protected diffs được ghi trước/sau.

### 2.2. Scientific scope

**R07.** Primary là H14 selection-only trên common calendar 14 ngày. Không gộp event-triggered search, leverage/risk adaptation, stop/TP thủ công theo nhãn thành một arm rồi quy kết cho forecast.

**R08.** Ít nhất 128 attempted strategy trials/cutoff/sampler; tối thiểu 12 DEV và 12 FINAL paired-valid folds riêng. Technical fixture có thể nhỏ hơn nhưng không là scientific result.

**R09.** Cùng search/objective/pool trong mỗi sampler; mọi selector được predict trên toàn pool. Panel labels không làm miền selection co lại.

**R10.** Không refit volatility-model hyperparameters, features, horizon hoặc taxonomy để làm WFO có lãi. Có thể refit weights theo đúng frozen learner/update policy và past-only labels.

**R11.** Forecast phải tồn tại theo as-of lineage hợp lệ; không dùng realized forward-volatility label thay prediction tại origin. Historical reconstruction hợp lệ vẫn phải được ghi là reconstruction.

**R12.** C được fit/chấm độc lập kể cả khi global/stock chọn anchor. Không cho phép B-admission boolean chặn C.

**R13.** Minimize predicted relative **Sharpe decay**, không đổi actual runner sang max predicted return. Chọn params theo quan hệ đã học, không mặc định LOW_VOL luôn phải dùng TP hẹp hoặc giao dịch nhiều.

**R14.** Không yêu cầu Sharpe hoặc decay đổi dấu. Không hạ guard/threshold sau khi thấy kết quả yếu. Không lấy source title “breakthrough” làm kết luận.

**R15.** Forecast skill, conditional selection benefit, calendar/refit benefit và live safety là các claims riêng. Giữ controls để phân biệt.

### 2.3. Domain và chronology

**R16.** Trước economic start, indicators được warm nhưng không orders/fills/positions/fee drift. Không gọi strategy decisions trong pre-roll rồi chỉ cắt metrics.

**R17.** Sizing đúng contract: fraction equity lấy từ engine trước entry command, không fixed 2.000 trá hình; không dùng future fill price/equity để quyết quantity.

**R18.** Cutoff, feature watermark, forecast-ready, search-ready, proposal-ready, scheduled-window-start và actual activation là các timestamps riêng. Không backdate vì cache HIT hoặc batch offline.

**R19.** Admission/rejection xảy ra trước active params nhận vào engine. Same-params revalidation không reset position/indicator/campaign.

**R20.** Train/feature/scaler/imputer/temperature đều biết từ past. Labels chỉ dùng khi cả target window và publication lag đã trưởng thành. Current inference không cần future label tồn tại.

**R21.** Không ghép các ngày cùng regime thành một chuỗi nến “liền nhau”; không chạy backtest trên chronology bị nén. Không chấm candidate bằng realized-regime OOS trước khi chọn.

**R22.** Continuous account không reset theo folds; standardized candidate cohorts tách riêng. D2 giữ cùng params trong một continuation thật.

### 2.4. Evidence và dừng

**R23.** Raw paths/forecasts có bytes/hash/version; counts/test receipt không thay outputs. Negative gate mutation phải FAIL.

**R24.** Mỗi run, kể cả timeout/OOM/failed, có attempt record và report. Mỗi upgrade có parent/diff/dependency invalidation, không overwrite old results.

**R25.** Không tăng allocation, không kill services khác, không dùng production venv. Logical budget, physical work và reuse savings tách riêng; đổi run ID không reset budget.

**R26.** Không promote bằng p-value của metric tình cờ tốt. Scope/thresholds/seed/folds/analysis freeze trước final.

**R27.** Một run thất bại chưa có outcomes không phải no-edge. Model/policy hợp lệ nhưng không cải thiện là negative result cần giữ.

**R28.** Sau mỗi phase: verify → generated report → scoped commit → `WAITING_OWNER_REVIEW`, trừ actual auto-advance authorization đã được lưu. Không tự tạo approval.

**R29.** Policy live-replayable không cấp quyền đặt orders/keys/cron hoặc sửa execution governance. LOW_VOL prediction không nới capital/risk limits.

**R30.** Không phát biểu có/không có edge cho mọi symbols/alphas từ một cell. Không mở thêm model family để cứu final âm.

<a id="s 3"></a>
## 3. Thiết kế chính và vai trò H14/H28

### 3.1. Cấu hình đề xuất để freeze

| Field | Default mới |
|---|---|
| Primary instrument/alpha | A-SC / BTCUSDT / 15 m, actual market contract phải resolve |
| Forecast | LightGBM H14, ba classes với probability vector đầy đủ được lưu |
| Primary conditioning signal | `p_LOW_VOL` continuous; không hard-switch ba buckets |
| Forecast update | Weekly theo handoff; source refit weekly/matured phải được verify |
| WFO search/selection | Calendar mỗi 14 ngày; same origins cho tất cả arms |
| Candidate IS | 180 calendar days, không gồm pre-roll |
| Standardized FWD | 14 calendar days, common window |
| D2 | 28-day frozen continuation: H1=14, H2=14 |
| Search | TPE và Sobol trong INIT/DEV; sau DEV chỉ một sampler frozen ở FINAL |
| Search budget | 128 attempted trials/cutoff/sampler, 2–3 effective dimensions |
| Candidate archive | >=12 matured historical origins trước DEV đầu |
| DEV / FINAL | >=12 folds mỗi role; default 12, đăng ký thêm trước outcomes nếu đủ budget |
| Primary metric | Mean paired signed Sharpe-decay reduction |
| Meaningful reduction | 0,20 điểm Sharpe, default kế thừa cần freeze |
| OOS/account noninferiority margin | 0,10 điểm Sharpe, role riêng với prediction guard |

H14 thành cadence 14 là **policy proposal mới** để horizon/selection được so trực tiếp, không phải quy luật rút ra từ mean duration. Các clocks khác nhau vẫn được ghi riêng.

### 3.2. Vì sao bắt đầu bằng p_LOW thay vì hard labels hoặc HIGH-risk control

LOW_VOL là phần có diagnostic mạnh nhất trong handoff. `p_LOW` được dùng như thông tin để học relative parameter performance; không được gọi nó là buy/sell signal hoặc safe leverage permission. Full p_LOW/p_MID/p_HIGH, reliability và class errors vẫn được report.

Chọn p_LOW liên tục tránh threshold kiểu `if p_LOW>0.6 then high_leverage`. Nó cũng tránh mở quá nhiều interaction dimensions khi meta-archive nhỏ. Full two-coordinate context (`p_LOW,p_HIGH`) chỉ là future preregistered revision, không được tự bật sau khi p_LOW không thắng.

Kết luận phải mang nhãn **LOW-VOL-PROBABILITY-CONDITIONED selection**, không “đã khai thác trọn vẹn ba regimes”.

### 3.3. H28 và đề xuất khác trong handoff được xử lý ra sao

| Nhánh | V1 mặc định | Lý do |
|---|---|---|
| H14 selection, cadence 14 | PRIMARY | Sát horizon có point skill trong nguồn |
| H28 forecast | Lưu diagnostic, không veto/gate H14 | BSS gần 0, không được coi đã qualified như H14 |
| Calendar 28 | Secondary riêng chỉ khi owner phê duyệt trước DEV | Không trộn cadence advantage vào primary |
| H14 forecast dùng cho params giữ 28 ngày | Không thuộc primary | Forecast window không tự có hiệu lực 28 ngày |
| Full H28-conditioned study | Deferred; cần raw scoped qualification hoặc exploratory approval riêng, >=12 folds riêng | Không nhận bằng chứng H14 thay H28 |
| Event-triggered refit | Deferred separate study | Thay cả thời điểm và budget, cần matched controls riêng |
| Leverage/position scaling theo regime | OFF | Forecast LOW không chứng minh an toàn đòn bẩy |
| TP/SL map thủ công theo nhãn | OFF | Direction của mapping chưa được học/kiểm; không thêm alpha mới ngầm |

Primary đã giữ common cadence nên **không cần** thêm một `CAL_MATCHED` khác để bù lịch refit khác nhau. Calendar 28 nếu có phải có common-calendar account comparison, không pair “fold số k” với fold 14 có dates khác.

### 3.4. Những gì được giữ từ nghiên cứu trước

Giữ QuantBT primary authority, stock Mode 4 `per_fold_causal`, full eligible pool, relative Sharpe decay, Brier/calibration provenance, source exclusions và immutable evidence. Không giữ mặc định H56/H90, JM clustering, 9-class joint regime hoặc 112-day stale timeout cho cadence 14.

Guide này là addon triển khai WFO mới. Không sửa các tài liệu model để tuyên bố WFO đã được chạy hoặc mọi H14 claims đã certified.

<a id="s 4"></a>
## 4. Handoff qualification và forecast packet

### 4.1. Qualification gọn, không làm lại toàn bộ model

Trong VWFO-01, đọc exact spec, registration, experiment script, raw probability ledger và evaluator. Tái tính trên đúng 48 origins của study được bàn giao:

1. Accuracy, macro-F1, confusion matrix và class order.
2. Brier convention, Brier scores model/baseline, BSS.
3. Paired forecast-loss uncertainty với đúng units/overlap; không lấy H/7 làm block length nếu đang resample daily returns.
4. Temperatures, imputation medians, train/calibration cutoff và model version.
5. Actual classifier parameters, feature list và field coverage.
6. Exposure do lựa chọn H14 sau multi-horizon screening.
7. Duration definition, mean/median và censoring, nếu dùng để giải thích. Duration không tham gia selection V1.

Không chạy lại financial engine cho bảy công việc này. Chỉ recompute model predictions nếu payload thiếu hoặc provenance thật sự không thể phục hồi.

### 4.2. Model identity từ nguồn, không tự “sửa tốt hơn”

Handoff ghi parameters sau; đây là source snapshot để đối chiếu, không lệnh training được chứng nhận:

```python
{
    "objective": "multiclass", "num_class": 3,
    "boosting_type": "gbdt", "num_leaves": 7, "max_depth": 3,
    "learning_rate": 0.015, "n_estimators": 80,
    "min_child_samples": 40, "subsample": 0.8,
    "colsample_bytree": 0.65, "random_state": 20260928, "verbose": -1
}
```

Trong LightGBM, `subsample/bagging_fraction` cần bagging frequency thích hợp để có tác dụng; handoff không ghi `subsample_freq`. Verify actual model config [E3], **không tự bật bagging** rồi gọi cùng model frozen. `38 features` trong handoff chỉ mô tả các nhóm, không đủ tái tạo feature schema.

Các cột tên “Annualized Basis Spread (Perpetual vs Spot)” và funding 8 h phải đối soát exact formula/units/settlement schedule. Perpetual không có fixed maturity để tự annualize như dated future. Nếu raw formula có version và chỉ là descriptive name, sửa narrative; nếu formula làm thay input, version/invalidate đúng. Không tiện tay mở một data project mới.

### 4.3. Forecast packet tối thiểu

```text
forecast_id, forecast_study_id, source_run_id
symbol, price_reference_market, timeframe, horizon_days
prediction_asof, feature_watermark, input_snapshot_hash
model_train_cutoff, label_watermark, calibration_cutoff
model_recipe_hash, weights_or_refit_recipe_hash, medians_hash, temperature_hash
taxonomy_version, exact_numeric_thresholds, class_order
forecast_ready_at, target_start, target_end, availability_contract
p_LOW, p_MID, p_HIGH, baseline_probabilities
status, calibration_status, missing_fields, source_quality_flags
research_data_role, historical_reconstruction_flag
```

Không copy các mức “~41,2%/~59,8%” từ report để dựng taxonomy. H14/H28 có thể có boundaries khác; exact numeric values phải đến từ approved artifacts. Forecast vectors không được đổi class order giữa retrain và inference.

### 4.4. Weights chưa lưu và historical replay

`RPS_CURRENT.md` ghi ở FIX-09: `weights_persisted:false`, `replay_method:REFIT_FROM_FROZEN_CONFIG`. Cần verify điều này còn đúng với **volatility study mới** hay chỉ MF trước.

- Có stored forecast hợp lệ: dùng nguyên forecast đã lưu, không cần fit lại chỉ để review.
- Cần forecast ở origin mới/quá khứ để đủ WFO timeline: chạy **cùng frozen recipe**, train/median/calibration bằng past available tại origin.
- Không load final 2026 weights để predict origins 2024 rồi gọi causal.
- Không lấy temperature fit bằng late validation áp vào earlier replay mà không disclosure/fix policy.
- Params của recipe được chọn sau khi xem historical years được ghi `RETROSPECTIVE_RECIPE_SELECTION`; weights/labels trước từng origin vẫn bắt buộc past-only. Không claim live-available lịch sử cho recipe được chọn muộn.
- Forecast mới phải có actual persisted booster, medians, temperature, schema hoặc một fully pinned deterministic refit receipt; production/shadow consumer cần restore được, không chỉ config hash.

### 4.5. Không re-label future volatility để chọn training neighbors hôm nay

Matured labels của historical forecast là targets để học. Chỉ **forecast probabilities đã biết tại historical origin** được đưa vào meta-selector context. Oracle realized LOW/MID/HIGH chỉ được dùng cho post-hoc diagnostic có nhãn oracle, không cho training-current selection ngầm.

<a id="s 5"></a>
## 5. Timeline, maturity và 12-fold rule

### 5.1. Ba tập thời gian của WFO khác các folds model

```text
Model history/forecast lineages đủ trước mỗi origin
    → WFO-INIT: >=12 candidate-forward origins matured
    → WFO-DEV:  >=12 common 14-day forward folds
    → freeze sampler/selector/analysis + maturity gap cần thiết
    → WFO-FINAL: >=12 common paired-valid 14-day folds
    → D2 follow-up: thêm14 ngày cho anchor cuối
```

Model 48 weekly forecasts không tự là 48 WFO folds. Lấy mỗi hai tuần từ 48 origins chỉ có khoảng 24 decision opportunities: chưa đủ mặc định cho INIT+DEV+FINAL=36. Agent lập planner bằng actual dates; replay past-only để bổ sung origins hợp lệ nếu dataset và model provenance cho phép. Không bịa thêm 12 origins hoặc tái sử dụng same 14-day window dưới IDs mới.

12+12+12 windows 14 ngày cần **504 calendar days forward**, chưa prehistory 180, forecast-feature lookback, model training/calibration support, publication/readiness gaps và D2. Đây là số học coverage, không estimate runtime.

### 5.2. Forecast horizon và computational latency phải khớp, không shift lén

**Canonical policy mới để agent materialize:** định nghĩa mỗi forecast/financial evaluation theo cùng calendar window `[window_start, window_end)`, độ dài 14 ngày. Cutoff khóa market inputs trước khi compute. Common research-ready lag được profile và freeze. Candidate account giữ flat cho tới `not_before >= max(forecast_ready, search_ready, validation_ready, nominal_ready)`.

- Nếu packet forecast đã định nghĩa target_start **sau cutoff + lag**, align WFO window đúng start đó.
- Nếu source forecast định nghĩa target_start ngay tại cutoff, **không đổi nhãn thành forecast của window dịch sang ngày khác**. V1 có thể đăng ký `WAIT_FLAT_PREFIX_WITHIN_H14`: giữ window nguyên gốc, zero economic activity trong prefix chờ compute cho mọi standardized arm, rồi giao dịch phần còn lại khi ready. Lúc đó report số ngày active khả dĩ, không gọi đủ 14 ngày investment.
- Cách thứ hai là migration có phiên bản của forecast-window target, cần requalification scoped trước dùng; không triển khai tự động.
- Không đọc data phát sinh trong thời gian chờ rồi cho vào selection đã khóa ở cutoff. Indicators có thể cập nhật tuần tự sau cutoff, trước execution, theo đúng thời điểm thực.
- Nếu actual readiness >= window_end: standardized policy có no-deployment/undefined Sharpe status; không xóa fold, không backdate hoặc chuyển sang window mới để tìm kết quả.

VWFO-01 chốt **một** timing contract từ source thực và evidence latency. Quyền chọn hai phương án trên không có nghĩa được dùng khác nhau theo arm hoặc đổi sau khi xem OOS.

### 5.3. Maturity độc lập cho model và meta-selector

```text
market_volatility_label_available = forecast_target_end + source/publication_lag
candidate_forward_label_available = financial_window_end + reporting_lag
model_train_eligible              = market_label_available < model_fit_asof
meta_train_eligible               = candidate_label_available < selection_asof
```

Equality chỉ hợp lệ nếu explicit event ordering chứng minh publication trước snapshot. Fold liền nhau không có nghĩa outcome fold trước đã available ở cutoff tiếp theo. Forecast update weekly không cho dùng hai overlapping forecasts như hai independent regimes.

DEV dùng chọn sampler và bounded selector recipe; toàn DEV outcomes cần cho lựa chọn phải mature trước FINAL start. Không dùng first FINAL day để hoàn thành calibration của DEV.

### 5.4. Data exposure và phạm vi suy luận

- Chọn dates theo coverage/capability trước outcomes, không theo model correctness hoặc alpha Sharpe.
- Period 06/2025–05/2026 đã dùng chọn H14 mang exposure flag. WFO mới trên cùng period là `LOCKED_RETROSPECTIVE_WFO`, không new independent model test.
- Có data sau source study chưa used thì phân loại đúng; đủ 12 complete forward folds mới có standalone inferential cohort. Không đòi chờ tương lai trong guide hoặc giả có đủ.
- Model qualified trên weekly forecasts: primary WFO origins chọn từ exact weekly grid/stride 14; không tự lấy stale p 14 của tuần trước rồi gọi target còn 14 ngày từ hôm nay.
- Target market volatility có thể spot, alpha execution có thể perp; giữ mapping explicit, không đồng nhất hai series/instruments.

### 5.5. Invalid-fold policy

Mỗi planned fold có row, kể cả no trades, undefined Sharpe, invalid data hoặc expired proposal. Không thay bằng fold khác sau outcome. Nếu cần >12 windows dự phòng, preregister toàn bộ N và report toàn N. Ít hơn 12 paired-valid → `INSUFFICIENT_PAIRED_FOLDS`.

14 daily returns tạo Sharpe nhiễu hơn một window dài; 12 folds chỉ là floor, không chứng nhận precision. Không tăng trials để giả tăng independent OOS samples.

<a id="s 6"></a>
## 6. Search và stock Mode 4

### 6.1. Binding cần giữ

```text
optimization_mode          = mode_4_is_only_robust
optimization_schedule      = per_fold_causal
candidate_selection_metric = is_only_robust
scoring_backend            = endpoint
```

Đây là contract tham chiếu từ guide trước, phải verify package 1.1.1 thực. Không “triển khai” bằng điền field metadata mà actual optimizer/selector vẫn chạy mode khác.

- Scorer/optimizer chỉ nhận train 180 view và warmup hợp lệ.
- Không `max(objective)` thay final stock robust selection.
- Không fabricate temporal metrics/trials để gọi helper private.
- Giữ raw stock params, plateau/fallback reason, subperiod-support fields; extensions có version riêng.
- NaN Sharpe/no trade/one finite subperiod cần trạng thái rõ. Không biến một subperiod hữu hạn thành chứng nhận robust qua toàn training.

### 6.2. Hai sampler mặc định, giữ cost hữu hạn

| ID | Cấu hình |
|---|---|
| `S_TPE` | Actual current TPE seed/startup/multivariate/pruning được pin |
| `S_SOBOL` | Optuna QMCSampler Sobol, scrambling và independent categorical sampler có seed |

Theo docs, QMC dùng independent sampler cho categorical và initial trial/search-space inference; 128 attempted trials không tự là 128 pure Sobol points [E1]. TPE có startup phase và objective-dependent proposals [E2]. Không mặc định runtime default hiện tại giống docs stable.

Tất cả samplers dùng cùng IS objective/economics/search space. WFO adapters phải chứng minh actual sampler class/config/ask-tell sequence, không chỉ label `sampler=sobol`.

Public hook không hỗ trợ sampler: dùng approved thin adapter giữ same QuantBT scorer/stock selector; thiếu capability thì scoped blocker, không sửa kernel. Không thêm CMA/GP/multivariate sweep trong V1 mặc định.

### 6.3. Search space

- 2–3 dimensions thật của A-SC đã có behavior tests; lấy exact names/ranges từ schema/source hiện hành.
- Không đưa guessed param names từ chiến lược khác vào guide như API đã có.
- Không biến sizing/leverage thành dimension tuning trong study này.
- Nếu strategy đã có entry/exit threshold parameters thì cho search trong approved range; không thêm SL/TP architecture mới.
- Mọi arm chọn từ **same full technically eligible pool** của sampler đó.
- Freeze range/category/constraint map trước DEV; không mở rộng quanh winner sau khi xem forward.

### 6.4. Trials và resume

Log attempted/completed/pruned/failed/duplicate/unique riêng. Có 128 attempts nhưng nhiều failures chưa có nghĩa search coverage tốt; report và technical-failure budget rõ. Không bù trial bằng seed khác để che failures. Sequential ask/tell hoặc deterministic ordered protocol có bằng chứng; parallel independent tasks chỉ trong quota.

Khi resume, restore sampler RNG/trial ledger; cached financial results được phép nhưng trial chronology không được reorder theo available outcomes.

<a id="s 7"></a>
## 7. Candidate archive và Sharpe-decay labels

### 7.1. Hai lớp thí nghiệm tài chính

| Lớp | Initial state | Mục tiêu |
|---|---|---|
| Standardized candidate | Cùng vốn và flat state; indicator-only warmup; ready lag theo policy | So độ giữ Sharpe của cùng params từ IS sang FWD |
| Continuous deployment | Carry cash/positions/orders/version ownership qua folds | Kiểm policy thực sự vận hành ra sao |

Không chép returns standardized vào account deployment. Không gọi standardized experiment là counterfactual trên live incumbent có vị thế.

### 7.2. Label công thức

Với sampler s, origin k, raw stock anchor a và candidate θ:

\[
D_{k,\theta}=SR_{IS180,k,\theta}-SR_{FWD14,k,\theta},
\quad Y_{k,\theta}=D_{k,\theta}-D_{k,a}.
\]

Giữ anchor Y=0 theo identity. Lower Y nghĩa là ít decay hơn anchor. Raw IS Sharpe không là penalized optimizer objective.

\[
Q_{k,\theta}=SR_{FWD,k,\theta}-SR_{FWD,k,a}
=SR_{IS,k,\theta}-SR_{IS,k,a}-Y_{k,\theta}.
\]

Target không phải realized regime class. Historical context là `p_LOW` forecast tại k; không lấy nhãn LOW sau 14 ngày để sửa prediction.

### 7.3. Label acquisition tiết kiệm

Tại mỗi origin/sampler:

1. Search và đóng băng full pool.
2. Chọn base panel tối đa 16 bằng IS-only rule: anchor; top IS; diversity theo schema + actual IS behavior; một số mid/lower-rank controls. Exact quotas/ties freeze trước DEV.
3. Fit selectors từ past matured labels, predict trên full pool.
4. Chốt **union mọi current winners của registered arms** trước khi đọc current forward data.
5. Forward-evaluate union đó bằng QuantBT; exact trùng params/economics/windows dùng một physical evaluation nhiều logical refs.
6. Sau label maturity mới đưa records vào shared sampler archive.

Không dùng label-panel cap để cấm selector chọn candidate ngoài 16. Không lấy only future-successful candidates vào archive. Failed/censored labels vẫn có rows và reason.

### 7.4. Meta-model support

Default global fit cần >=12 distinct matured candidate origins. Origin có nhiều labeled candidates không được weight hơn origin khác; candidate weights trong mỗi origin cộng về 1, anchor-zero row không tính như một informative extra observation.

Một same 14-day outcome không trở thành nhiều independent samples vì nhiều candidates/seeds. Archive expanding của từng sampler được chia sẻ cho B0/B_CAP/O/C/P. Không train C bằng thêm labels riêng mà B không có.

Model market training support và meta-selector support là hai bộ đếm khác nhau. H14 classifier qualified không tự tạo 12 financial candidate origins.

### 7.5. Cold start

INIT tạo labels để học selection; không pretend C đã operating trong INIT nếu thiếu support. DEV bắt đầu sau >=12 financial labels và forecast lineages hợp lệ. Chưa đủ meta support → current stock proposal tại cutoff, không fit từ 1–4 origins để lấp bảng.

Không bắt đầu FINAL khi classifier/selector thiếu initial support rồi phần lớn account flat; nếu policy deliberately cold-start thì là study riêng có comparator initial conditions tương ứng.

<a id="s 8"></a>
## 8. Volatility-conditioned selection và các đối chứng

### 8.1. Core architecture mới, freeze chứ không tune vô hạn

Với descriptor vector φ gồm 2–3 params normalized, raw IS Sharpe và một IS activity/support descriptor:

\[
v_{k,\theta}=\phi(z_{k,\theta})-\phi(z_{k,a}).
\]

Fit descriptor scaler bằng past matured training only. Không có candidate-ID feature. Scale numeric theo schema/approved train transform; categorical encode đúng. Anchor contrast v=0, vì vậy predicted Y(anchor)=0 structurally.

Global B0:

\[
\hat Y_{B0}=\beta^T v,
\quad \min_\beta \sum_k \operatorname{mean}_{\theta\ne a}(Y-\beta^Tv)^2+10\|\beta\|^2.
\]

Đây là frozen starting regularization, không khẳng định tối ưu. Mọi solver phải khớp sum-of-origin-means normalization; đừng đổi số 10 giữa sum/mean weights rồi gọi cùng model.

### 8.2. Lớp correction và capacity control

Đặt residual e=Y−Yhat_B0. Tại fit cutoff, lấy past `p_LOW` và tính mean/scale chỉ từ historical origins. Default minimum std=0.05 để tránh phóng đại context gần hằng; nếu below thì context correction off, ghi `CONTEXT_VARIATION_LOW`, không covertly create signal. Đây là design convention cần freeze, không numerical repair của dữ liệu.

\[
z^{F}_{k}=(p_{LOW,k}-\bar p_{LOW,train})/s_{train}.
\]

`B_CAP`: fit pooled residual correction γ 0 bằng same rows/weights và penalty 10.

`C_H14`: fit cùng residual architecture, gồm pooled component và interaction:

\[
\hat Y_C=\beta^Tv+\gamma_0^Tv+z^F_k\gamma_1^Tv.
\]

Penalty 10 cho từng coefficient block, same fit masks/weights, no intercept in contrast. Nếu context constant 0, C phải trở về pooled-control solution trong numerical tolerance; test actual solver.

C không hoàn toàn matched degrees-of-freedom với B_CAP vì có interactions; no-information controls bên dưới kiểm bổ sung. Không gán gain của residual refit đơn thuần cho forecasting information.

### 8.3. Observed/persistence-context control O

`O_PERSIST` dùng **baseline probability LOW** từ same forecast evidence/ontology/horizon (hoặc past-only persistence probability mapper đã đóng băng), thay model p_LOW. Cùng residual architecture, penalty, training rows, guard và lifecycle.

Mục tiêu: C có hơn thông tin “volatility đang thấp nên có thể tiếp tục thấp” hay không? Nếu forecast chỉ vượt B0 nhưng không vượt O, chưa chứng minh lợi ích riêng của ML forecast.

Không dùng hard realized forwardLOW làm O. Nếu handoff chỉ lưu baseline hard labels, recover actual probability baseline dùng tính Brier; thiếu thì `BASELINE_PACKET_REQUIRED`, không tự điền probability=1 cho class đoán rồi gọi same comparator.

### 8.4. No-information context controls

Ba policies `P_NI_01..03`, seeds fixed trước FINAL, cùng architecture C. Pseudo p_LOW là chuỗi ngẫu nhiên có autocorrelation/support được hiệu chỉnh **chỉ bằng INIT**; không dùng FINAL chronology để chọn phase shift hoặc seed.

Có thể dùng một finite-state Markov generator với levels/ranges fixed từ INIT, stable daily/weekly counter và probability in[0,1]. Không biến real forecast sang shuffled series dùng các giá trị lấy từ future để quyết định historical origin. Lưu full generation spec/tape.

Training pseudo-context tại historical origins và current prediction cùng một causal generator. Ba seeds không là exact randomization test đủ mạnh; chỉ là predetermined no-information policy controls. Không chọn seed yếu nhất làm comparator.

### 8.5. Rule chọn candidate — actual runner phải thực hiện

Cho mỗi arm m:

\[
\hat Q_m(\theta)=SR_{IS}(\theta)-SR_{IS}(a)-\hat Y_m(\theta).
\]

```text
1. Validate current full pool và legal model/forecast state.
2. Predict Yhat trên toàn pool; current label existence không được đọc.
3. Common data/safety exclusions áp đúng và symmetric.
4. Giữ candidates có Qhat >= -0.10 điểm Sharpe; anchor contrast-zero là fallback hợp lệ.
5. Chọn min signed Yhat, không max predicted return.
6. Tie 1e-6: gần anchor theo approved parameter geometry; sau đó candidate digest.
7. Log ranks/guard reasons/model packet và raw selected proposal.
8. Admission/controller xử lý proposal trước engine activation.
```

Guard −0,10 là margin dự đoán tương đối, khác statistical noninferiority margin dù cùng trị số khởi đầu. Không yêu cầu expected Sharpe>0 hoặc p_LOW>một threshold. HIGH forecast sai không kích hoạt leverage/risk policy.

Nếu model unqualified/unavailable: C fallback B0 proposal **tại current cutoff**. Nếu meta model chưa đủ history: stock proposal current cutoff. Handoff classification errors không được bù bằng tự tăng ngưỡng confidence sau OOS.

### 8.6. Hypotheses và arms

| ID | Vai trò |
|---|---|
| `A_M4` | Raw stock Mode 4 trên pool của sampler |
| `B0_GLOBAL` | Learned Sharpe-decay selection không context |
| `B_CAP` | Thêm pooled correction nhưng không market context |
| `O_PERSIST` | Context từ baseline/persistence forecast |
| `C_H14` | Context từ H14 model p_LOW |
| `P_NI_01..03` | No-information context policies |

Primary: **C_H14 vs B_CAP** về Sharpe-decay reduction, có OOS guard. Để claim **predictive-volatility information** còn cần đối chiếu O_PERSIST và composite placebo. A là reference stock; B0−A cho biết global selection có ích không, không gán gain đó cho volatility.

DEV mặc định chạy A/B0/B_CAP/O/C cho cả hai samplers; no-info generation rule khóa từ đầu, trajectories/3 seeds khóa trước FINAL. FINAL có 8 policies nhưng **một search pool/cutoff của sampler đã chọn**, không 8 lần optimize.

### 8.7. Chọn sampler trên DEV, không chọn lại classifier

Giữ cùng frozen selector architecture, chỉ so sampler TPE/Sobol. Mọi comparison cần >=12 common paired-valid DEV folds.

Rule freeze trước outcomes:

1. Group ưu tiên: mean FWD Sharpe C−B_CAP và C−O không dưới−0,10.
2. Trong group, chọn sampler có `min(mean_R_C:CAP, mean_R_C:O)` lớn nhất.
3. Tie 1 e-6: lower measured total work; rồi predeclared ID order.
4. Mọi sampler đều weak: giữ winner theo cùng rule, ghi `WEAK_DEV_EVIDENCE`; owner duyệt final falsification hoặc dừng. Không đổi context/head/guard để tạo winner dương.
5. Không đủ valid scope: không gọi một sampler là thắng.

DEV selection không là independent confirmation. Không có model-hyperparameter sweep hoặc hardcode low vol aggressive parameters trong phase này.

<a id="s 9"></a>
## 9. Financial execution và policy có thể replay/live

### 9.1. Economic defaults phải được verify bằng actual fills

```yaml
initial_equity: 20000
allocation_fraction: 0.10
leverage_cap: 1
one_way_fee_decimal: 0.0004
one_way_slippage_decimal: 0.0001
strategy_decision_clock: closed_15m
execution_resolution: 1m
execution_ordering: next_open_contract_to_verify
terminal_valuation: mark_to_market
```

Đây là study assumptions kế thừa, không phải mức phí live hiện hành. Lưu intended quantity, reference price khi phát command, rounding, actual fill và charged fees; không double fees ở API đã nhận one-way rate.

Nếu alpha thực sự giao dịch perpetual, phải khóa funding/shorting/instrument rules. Funding làm predictor khác funding cashflows được engine tính. Thiếu engine funding support: giữ truthful modeling limitation và scope, không tự viết một sổ PnL phụ hoặc giả spot/perp tương đương. Không đổi venue để tránh vấn đề.

### 9.2. Warmup, actual start và first return

- Trước economic_start: indicator state được cập nhật từ legal history; engine cash/position/orders vẫn pristine theo standardized contract.
- Từ economic_start tới ready_at: standardized policy giữ flat, không trade trước sẵn sàng. Daily returns 0 của prefix trong window là outcome hợp lệ, không drop để tăng Sharpe.
- Pending strategy state không được cập nhật bằng expected fill. Fill/reject/partial fill feedback lấy từ engine.
- Gap next-open khác next-close; fixture phải buộc hai paths cho khác kết quả để chứng minh runner dùng đúng ordering.
- Actual warmup length lấy từ alpha dependency, không mặc định hai ngày cho mọi indicator.

**Ranh giới quan trọng:** lệnh cấm trước `not_before` áp cho proposal/version mới. Trong continuous account, incumbent còn hợp lệ và protective exits vẫn được hoạt động trong khi chờ; không ép toàn account flat ở mỗi cutoff chỉ để đồng bộ arms.

### 9.3. Shared controller, không hai bản research/live khác nhau

```text
ACTIVE_INCUMBENT
  → CUTOFF_SNAPSHOT_LOCKED
  → SEARCH_AND_FORECAST_PENDING
  → PROPOSAL_COMPUTED
  → CONTRACT_VERIFIED
  → APPROVAL_PENDING (nếu governance cần)
  → PUBLISHED_READY
  → WAIT_NOT_BEFORE
  → WAIT_SAFE_ACTIVATION
  → ACTIVE_NEW_VERSION / REVALIDATED_SAME_PARAMS
```

Mỗi arm có controller/account độc lập nhưng cùng rules. Model forecasts được phát weekly; chỉ lấy packet đồng bộ với decision cutoff đã đăng ký, không activate hàng tuần nếu policy search là 14 ngày. State chuyển giữa kỳ chỉ được log, không trigger tìm params ngoài lịch.

### 9.4. Ownership của positions/orders

Giữ protection/campaign/entry orders theo version đã tạo. Nếu actual adapter yêu cầu chỉ switch khi flat thì wait-flat cho mọi arm. Không gán parameters mới lên open position cũ trừ alpha đã có amendment contract được kiểm.

Proposal ready không có nghĩa active. Log search cutoff, request, publication, earliest legal time, actual activation và reason. Không ghi activation=foldstart chỉ vì report cần một mốc.

Same effective params: cập nhật revalidation watermark nhưng không close/reopen position hoặc reset indicators. Tách `age_since_param_change` và `age_since_revalidation`.

### 9.5. Policy defaults cho cadence 14

Các values sau là **new proposed defaults**, cần được owner freeze và kiểm trên development, không kế thừa TTL112 ngày từ horizon khác:

```text
common_ready_lag = profiled conservative bound, explicit same rule per arm
proposal_ttl = 2 calendar days after nominal effective time
max_revalidation_age = 28 calendar days
update_cadence = 14 calendar days
```

Nếu measured search/model completion không đáp ứng, không tự backdate hoặc tăng TTL khi thấy final không tốt. Owner có thể approve một time-budget contract khác trước final; lưu policy version mới.

| Tình huống | Hành động |
|---|---|
| Model p_LOW thiếu nhưng search/global valid | B0 current proposal; log forecast fallback |
| Global archive thiếu support nhưng search valid | Stock current proposal |
| Forecast stale, schema/taxonomy mismatch hoặc missing invalid inputs | Không dùng nhầm packet; follow approved fallback |
| Search thật thất bại/chưa có payload | Run incomplete; không điền incumbent để giả đã chạy đủ study |
| Deadline-miss được policy preregister và được replay đầy đủ | Valid operational outcome: giữ incumbent hoặc pause theo rule, không drop fold |
| Proposal expired trước safe activation | Không activate; current orders/protection vẫn được quản lý |
| Quá 28 ngày không có revalidation hợp lệ | Pause new entries theo safety interface; exits/protection vẫn chạy |
| Duplicate proposal/retry | Stable ID + expected-incumbent/sequence; không repeated activation/orders |
| Crash sau publish trước ack | Reconcile journal/actual account state; không assume chưa activate |

Pausing entries là operational safety rule đối xứng, không là H14 high-vol trading signal. Không có automatic liquidation của existing positions theo guide.

### 9.6. Model packet và live adapter

Persist booster/schema/imputer medians/temperature/taxonomy, training watermarks và full selector coefficients/normalizers. Weights-only không đủ. Serialization không tin untrusted pickle. Model process restart phải khôi phục đúng forecast IDs và inputs.

Actual live fills phải từ execution broker integration; không lấy OHLCV simulated fill thế cho broker state. Guide chỉ yêu cầu lab shadow/streaming replay, không cấp API keys, không gửi orders, không thay approval R1/R2 hoặc execution code.

### 9.7. Forecast safety scope

LOW_VOL recall/precision không chứng minh tail-risk control. Source matrix có HIGH bị dự báo LOW; volatility thấp cũng không dự báo hướng giá. Không tăng leverage, không bỏ SL, không nâng positioncap hoặc marketing “safe low-vol scalping” từ classifier metrics.

<a id="s 10"></a>
## 10. Sharpe decay, diagnostics và inference

### 10.1. Canonical Sharpe

Với equity E và không external cashflows:

\[
r_d=E_d/E_{d-1}-1,\qquad
SR(W)=\sqrt{365}\,\frac{\operatorname{mean}_{d\in W}(r_d-r_{f,d})}{\operatorname{std}_{d\in W}(r_d-r_{f,d};ddof=1)}.
\]

Default rf=0 phải freeze. Daily UTC marks, đúng preceding equity, IS180 returns và FWD14 returns theo exact boundaries. Raw engine metric được lưu riêng và reconcile; không normalize Sharpe theo số bars của từng fold.

Whole-account SR tính từ whole daily path. Mean của fold Sharpes là mean-fold statistic, không portfolio/account Sharpe. H14 ít observations làm statistic có variance lớn; annualization không tạo thêm dữ liệu.

`ZERO_VARIANCE`, `NO_TRADE_WITH_ZERO_RETURNS`, missing market marks, nonfinite equity và censored path phải có status. Không epsilon-fix volatility hoặc đặt Sharpe undefined=0. Flat days bên trong window giữ nguyên.

### 10.2. Primary contrasts và decomposition

\[
R_k^{C:J}=D_{k,J}-D_{k,C},\qquad Q_k^{C:J}=SR_{FWD,k,C}-SR_{FWD,k,J}.
\]

Với J=B_CAP/O/P-composite/B0 theo claim:

\[
R_k^{C:J}=(SR_{IS,k,J}-SR_{IS,k,C})+Q_k^{C:J}.
\]

Báo đủ từngfold và tổng hợp: Rmean/median, Qmean, number positive/negative/zero, IS-reference contribution và FWD contribution. Không lấy absolute decay, không clipD về 0 cho primary. Giảm gap vì IS yếu hơn khác forward retention improvement.

Thông số freeze:

```text
meaningful_decay_reduction = 0.20 Sharpe points
forward_noninferiority_margin = 0.10 Sharpe points
continuous_account_noninferiority_margin = 0.10 Sharpe points
prediction_guard_margin = 0.10 Sharpe points (vai trò riêng)
min_common_paired_final_folds = 12
```

Không dùng mean daily return/bps/day hay maxdrawdown p-value thay primary. Các returns/costs/drawdown được giữ cho accounting/safety diagnostics, không là criterion mới khi Sharpe không thắng.

### 10.3. D2 parameter-age diagnostic

Tại mọi FINAL origin, dùng same θ trong **một** standardized continuation 28 ngày, H1/H2 mỗi 14. Không reset ở boundary. H1 phải match FWD14 theo daily path/financial traces đủ, không chỉ scalar Sharpe.

\[
D^{age}_{k,m}=SR_{H1,k,m}-SR_{H2,k,m}.
\]

Default D2 cho A/B0/B_CAP/O/C, không thêm placebos vào D2 nếu không có separate budget. Tối thiểu 12 paired anchors cho contrast được diễn giải. Nếu thiếu follow-up ghi incomplete; không lấy một fewanchors làm proof.

D2 không cứu D1 âm. Sự khác biệt giữa params ở các foldk và k+1 không là decay của same params. Overlap của 28-day continuations trên 14-day grid phải được đưa vào inference nếu claim.

### 10.4. Block units: không mang H/7 sang daily returns

| Statistic | Sampling unit | Starting block policy |
|---|---|---|
| Source H14 forecast Brier loss | Weekly forecast origins | 2-origin blocks; sensitivity 3/4 khi support đủ |
| WFO mean paired fold-decay | 14-day fold tuples | 3-fold blocks; report 2/4 sensitivities |
| Continuous-account SR difference | Daily paired returns | 14-day blocks; report 28/42 sensitivities |

Đây là defaults để **qualification trên DEV**, không là định lý đủ decorrelation. IS180 windows overlap mạnh, archive weights và open campaigns tạo thêm dependence. Nếu dependence/support không cho inference đáng tin, ghi `INFERENCE_LOW_PRECISION/UNQUALIFIED`, không tự giảm blocksize để ra p<0.05. K=12,L=3 chỉ cho ít blocks; bootstrap 5000 draws không tạo 5000 market histories.

Primary paired circular moving-block bootstrap: wrap-around đúng, draw common indices cho tất cả arms/tuples, mean-statistic centering/basic interval được test. Seeds, numberdraws 5000, tail convention và alternatives khóa trướcFINAL. Với whole-account SR, recompute SR của resampled **dailyreturn series**, không bootstrap meanfoldSR để gọi accountCI.

Raw saved outputs đủ để bootstrap/report mà engine_calls=0. Không claim bootstrap này tái hiện toàn phân phối training-model/search procedure; nó ước lượng uncertainty của measured paired policy outcomes theo assumptions đã nêu [E5].

### 10.5. Claim hierarchy và multiple comparisons

**Primary claim:** retention so với B_CAP cần đồng thời:

```text
Lower bound(R_C:CAP) > 0.20
Lower bound(Q_C:CAP) > -0.10
valid domain + >=12 paired folds
```

Dùng one-sided 95% lowerbounds với definition/procedure đã freeze. Đây là một conjunction/intersection–union decision; cả hai conditions bắt buộc. Không gọi các marginal bounds là một simultaneous confidence region. Nếu báo các separate discoveries ngoài claim đã đăng ký, phải có family adjustment rõ.

**Forecast-information claim bổ sung** còn phải vượt:

```text
Lower bound(R_C:O) > 0
Lower bound(Q_C:O) > -0.10
Lower bound(R_C:mean(P1,P2,P3)) > 0
Lower bound(Q_C:mean(P1,P2,P3)) > -0.10
Lower bound(Q_C:B0) > -0.10
```

Ba placebo statistics được average **trong từngfold**, không phải equity hoặc Sharpe của một portfolio chưa tồn tại. Tất cả cùng là required conditions cho một preregistered conjunctive information claim, không tùy chọn comparator yếu nhất. Secondary A/B0 comparisons không tự có family-adjusted significance.

Nếu muốn thêm claim continuous-account: lowerbound SR_account(C)−SR_account(B_CAP)>−0,10 và safety/replay đạt; dùng daily procedure riêng. “Noninferiority không bác bỏ được” không đồng nghĩa “đã chứng minh không kém”; phải đạt lowerbound.

Do samples nhỏ và bootstrap approximate, mọi bound kèm inference qualification/sensitivity. Không ghi exact population proof.

### 10.6. Decision table

| Evidence | Kết luận được phép |
|---|---|
| Wrong timing/sizing/forecast provenance hoặc missing required computation | `NOT_EVALUABLE_FOR_REGISTERED_CONTRACT` |
| <12 common paired-valid finalfolds | `INSUFFICIENT_PAIRED_FOLDS` |
| Positive Rpoint nhưng lowerCI<=0 | `OBSERVED_REDUCTION_LOW_PRECISION` |
| LowerCI(R)>0 nhưng chưa>0,20 | `REDUCTION_DETECTED_MAGNITUDE_UNPROVEN` |
| Primary conjunction đạt | `MEANINGFUL_STANDARDIZED_RETENTION_VS_BCAP` |
| Primary + O/P/B0 conditions đạt | `PREDICTIVE_VOLATILITY_SELECTION_INFORMATION_WITHIN_SCOPE` |
| Standardized đạt, continuous không đạt/chưa có | `SELECTION_ONLY_DEPLOYMENT_BENEFIT_UNPROVEN` |
| Qualified upperbound R<0,20 | Không hỗ trợ mức cải thiện 0,20 trong scope, không universal no-edge |
| All outcomes identical sau independent scoring | `EXACT_ZERO_OBSERVED`; không tự p=0, không xóa zerofolds |
| C toàn global fallback | Policy effect được báo; active forecast mechanism chưa được exercise |
| Raw forecast H14 không hơn baseline rõ | Model evidence hạn chế; không gán WFO uncertainty cho “chỉ thiếu trials” |

Một confidence interval còn đi qua 0 không chứng minh chắc chắn deterioration. Một positive relative improvement trong strategy có absolute SR âm không tự là live eligibility.

### 10.7. Phân tích cơ chế bắt buộc, chi phí nhỏ

```text
pool diversity
→ predicted candidate ranking
→ Q-guard và winner
→ actual admission
→ actual activation/delay
→ changed signals/orders/fills/exposure
→ standardized and continuous Sharpe
```

Báo context đã được gọi bao nhiêu lần, correction active/fallback, same selection, altered trades. “Cùng winner” sau independent evaluation là outcome hợp lệ, không tự là copied arm. Dùng hashes/digests params, không chỉ chữ ANCHOR/other.

Phân tích theo realized LOW/MID/HIGH là post-hoc attribution, không mask primary estimate. Không chỉ giữ các folds model đoán đúng để claim edge. Không gọi 21/25 tuầnLOW là 21 independent volatility cycles.

<a id="s 11"></a>
## 11. Codebase mapping, computation và reuse

### 11.1. Map actual source trên host, không assume API mới

| Source reference | Nhiệm vụ |
|---|---|
| `handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md`, `handoff/RPS_CURRENT.md` | Model handoff/scope, reconcile current numbers |
| `BTC_VOLATILITY_CONDITIONED_REGIME_SELECTION_SPEC_V1_VI.md` | Actual H14/H28 experiment definition |
| `configs/btc_volatility_forecast_v1/registration.json` | Taxonomy/model/temporal source of truth cần đọc |
| `scripts/exp_volatility_horizons_study.py` | Recover forecast ledger, Brier baseline và chronological fit |
| `src/crypto_regime_lab/regime_forecast/` | Reuse features/imputation/calibration/model engine |
| `tests/regime_forecast/` | Reuse relevant proofs, không suy native financial PASS |
| `run_cutoff_walk_forward` symbol | Handoff-required financial wrapper; tìm exact module/signature |
| FP/SD evaluator, search, selection và event-account modules trước đây | Map current successors; repair affected boundaries, không duplicate codebase |
| Approved `data_loader` contract | Source reads trên server được cấp quyền |

Có thể tạo thin `volatility_wfo/` orchestration package nếu cần; đây là logical proposal, không khẳng định các modules/CLI ấy đã có. Không copy toàn bộ SD thành một financial implementation khác.

### 11.2. Microprofile trước bulk

Một actual candidate theo audit và scoring profiles, một fixed cutoff theo actual Mode 4 wrapper, một small account có forced reject/version change. Measure RSS/CPU/wall/bars/engine calls/retention. Đúng clocks 15 m/1 m và costs/sizing before speed.

Prefer qualified `pct_equity`/native scoring khi alpha semantics thật tương đương; nếu fill-dependent dùng event route. Không vectorize bằng cách bỏ stop/partial fill hoặc same close thay next open.

### 11.3. Budget arithmetic

Default two samplers INIT 12+DEV 12, final winning sampler 12:

\[
2(12+12)128+12\times 128=\mathbf{7.680}\ attempted\ search\ trials.
\]

Đây là workload arithmetic, không thời gian chạy hứa trước. Forward labels là unique union(panel+winners), không 128×mọi model. FINAL 8 continuous policies dùng chung search outputs; D2 core 5×12=60 logical 28-day continuations trước exact reuse.

Có thể chọn >12 folds trước outcomes nếu approved. Không tăng folds sau nhìn p-value thuận lợi. Optional sampler/cadence/horizon branches cần budget riêng; nếu budget không đủ giữ scope planned/incomplete hoặc owner approve reduced design trước outcomes, không đổi minimum 128/12 ngầm.

### 11.4. Cache identity và invalidation

Tách financial/feature/forecast/search/selection/report caches. Economic cache bind:

```text
data+instrument+coverage+revision
alpha+effectiveparams+decision/execution clocks
engine/native/scorer version
warmup/economicstart/ready/initialstate
sizing/fees/slippage/funding/terminalcontract
```

`run_id` và output path chỉ provenance. Changing p_LOW model không tự invalidates exact candidate financial run; changing equity sizing/pre-roll start **có thể** invalidates search rankings, anchor, labels và deployments. Không reuse labels lỗi để tiết kiệm.

Old 256 pool→128 prefix chỉ hợp lệ nếu exact sampler/trial prefix/economics match và stock selector rerun trên prefix; không dùng full 256 winner làm 128 anchor.

### 11.5. Dữ liệu và artifacts

Reads bounded, featurearrays immutable, chỉ keep active buffers. Export daily returns cần thiết của all standardized selections và all continuous accounts; selected trace giữ orders/fills/version lineage. Full perbar audit chỉ ở scopedcases cần thiết nhưng không làm mất khả năng tái tính metrics.

Monthly/chunkedI/O được phép; financial account state không reset theo chunk. Never run copiedvenv fromZIP. Forecast inference một lần/origin rồi reuse mọi candidate; không 128 lần per 128 trials.

<a id="s 12"></a>
## 12. VWFO-01 — Chấp nhận handoff và qualify financial boundary

### Mục tiêu

Mở đúng bridge H14 dựa nguồn hiện tại, không dùng bảng mâu thuẫn hoặc lỗi execution làm mờ scientific result.

### Công việc theo thứ tự

1. Ghi source/branch/commit/dirty state, runtime 1.1.1 thực, quota và protected baseline. Đọc spec/rawforecast trên host theo §0.
2. Reconcile H14 accuracy/macroF1/confusion/Brier/CI; giữ source values và regenerated values. Chốt exposure/status H14; H28 vẫnsecondary.
3. Xác minh 38 features, medians, temperature, taxonomy, modelrecipe, actual refit cadence và release point. Recover needed forecast lineage, không tuningmodel mới.
4. Resolve target/execution spot/perp, fee/funding/quantity, alpha 15 m và original parameter schema.
5. Lập timeline INIT/DEV/FINAL từ actual forecast/data availability; xác minh có thể bổ sung past-only forecast origins khi 48 weekly tape không đủ.
6. Profile ready lag và khóa exact FWD14/flatprefix contract, TTL/fallback. Không coi forecastduration 12,1 là input điều khiển clock.
7. Sửa/verify warmup, equity sizing, next open, admission, label maturity trên current financial runner.
8. Materialize registration/roster/budget/inference plan. Report explicit bridge status; owner duyệt trước bulk.

### Tests và evidence bắt buộc

| ID | Expected behavior |
|---|---|
| V1-T01 | Rawforecast matrix/Brier recompute match đúng version; mismatch làm claim gate FAIL, không tự sửa probability |
| V1-T02 | Future-price/label suffix không đổi earlier features/forecasts/search inputs; imputer/temp past-only |
| V1-T03 | Standardized account không có orders/fills/cash drift trước economic start; proposal mới không được tạo commands trước not-before; incumbent protection vẫn hoạt động |
| V1-T04 | Equity 20 k/30 k tạo intendednotional 2 k/3 k theo same actual helper; preserve future-price boundary |
| V1-T05 | Gapfixture tách next open với same close/next close; actual runner đúng contract |
| V1-T06 | Known equitypath/14-day window có firstreturn và đúngdaycount; undefined Sharpe typed |
| V1-T07 | Forecast/search notready hoặc admission reject ngăn actual version consumption |
| V1-T08 | INIT11 priors/late calibration không mở DEV; 48 weeklyrows không được count thành 36 biweeklyfolds |
| V1-T09 | Negative artifact/hash/approval/complete=false mutation làm verifier fail |
| V1-T10 | Microprofile và audit-score parity có native financial output, không onlymock |

### Exit gates

- `G1-HANDOFF`: mismatch disposition xong, source đủ, statusmodel không overclaim.
- `G1-FORECAST`: actual packet/maturity/taxonomy/replay policy qualify hoặc owner exploratory approval explicit.
- `G1-DOMAIN`: T03…T07/T10 đạt trong runner cần dùng.
- `G1-TIMELINE`: exact foldplan, forecast coverage, labels và lags feasible.
- `G1-BUDGET`: approved costs/resources/roster; no production mutation.
- `G1-OWNER`: report + actual approval. Chưa đủ thì không bulkWFO.

**Không cần làm lại MF-01…MF-05.** Một reporttypo sửa bằng raw-ledger recomputation là đủ; một economicbug phải sửa financial path và invalidate scope cần thiết.

<a id="s 13"></a>
## 13. VWFO-02 — Common pools và candidate-forward archive

### Mục tiêu

Có search đầy đủ và historical outcomes đúng để học relative Sharpe decay, không rơi lại vào coldstart hoặc panel-selection mismatch.

### Công việc

1. Qualify sampler injection với actual Mode 4 scorer/selector. Pin TPE/Sobol và resume protocol.
2. Chạy/reuse 128 trial×12INIT cho mỗi sampler; INIT forecasts/candidate availability hợp lệ.
3. Sinh full candidate views, basepanels và exact raw stock anchor. Parameter-effect tests dùng current schema.
4. Tạo corrected IS180/FWD14 paths/labels, tracking ready/initial state và units.
5. Expose chỉ matured archive tại mọi cutoff. Shared archive cho tất cả models trong cùng sampler.
6. Chuẩn bị DEV search pools từ past-only views; actual DEVlabel union sẽ do VWFO-03 chốt trước FWD.
7. Ghi raw/cached calls, attempted/completed/unique và memory. Không gọi 16 medoids là full pool.

### Tests

| ID | Expected behavior |
|---|---|
| V2-T01 | Actual sampler class/sequence match manifest; QMC initial/categorical behavior đúng |
| V2-T02 | Reference TPEcutoff match actual Mode 4 objective+selection reason; no argmax substitute |
| V2-T03 | A/B0/B_CAP/O/C có cùng full technical candidate IDs; ngoài 16 panel vẫn predictđược |
| V2-T04 | Deleting/changing current future label không đổi inclusion/ranking/proposal |
| V2-T05 | Panel/winnerunion froze trước outcomes; all registered winners có labels dù ngoàipanel |
| V2-T06 | Origin weights normalizeđúng, 12 maturedorigins không là 12 candidaterows |
| V2-T07 | Same computation newrun cachehit; changed economics helper cachemiss; no future reuse |
| V2-T08 | Resume không đổi RNG/trial timeline; no fake COMPLETE cho failure |
| V2-T09 | RawIS/FWD Sharpe/D/Y reconcile fullpaths; source đúngmarket/180/14 |
| V2-T10 | ActualINIT outputs đầy đủ và budget counters reconcile; không dùng fixture thay completion của nghiên cứu |

### Exit gates

`G2-MODE4`, `G2-POOL`, `G2-INIT12`, `G2-LABELS`, `G2-REUSE`, `G2-REPORT_OWNER` đều pass. DEV không mở bằng 12 future labels chưamature. Thiếu phải ghi scope blocker, không fallbackfit từmột origin.

<a id="s 14"></a>
## 14. VWFO-03 — Development của selection và khóa một sampler

### Mục tiêu

Thử model volatility đã handoff ở **nhiệm vụ lựa chọn params**, không giả accuracy tốt sẽ tự cho WFOedge.

### Công việc

1. Implement B0/B_CAP/O/C theo §8, samearchive/weights/regularization; C p_LOW independent.
2. Chạy chronological DEV>=12 folds/sampler, 128 trials/fold. Mọi fold có forecast packet và own past-only meta-fit.
3. Score full pool, sealwinners trước forward, bổ sung labels cần thiết; không hard-map LOW→aggressive parameter mapping.
4. Report C vsB_CAP, vsO, vsB0, B0 vsA và context/action funnel. Samewinner vẫn giữ trong estimate.
5. Kiểm weak high vol và forecast confidence ở diagnostic, không thay risk limits; H28 chỉ ghi descriptive.
6. Chọn sampler theo rule §8.7, không chọn lại H14 model/horizon/feature/temperature bằng WFOresult.
7. Freeze FINAL 8 arms, exact 12+folds, noinfo 3 seeds/spec, costs, support, taxonomy, forecast update rule, latency, thresholds/inference family.
8. Owner duyệt finalrun hoặc dừng do weak/no-valid-evidence. Không thêm recipe để cho positive.

### Tests

| ID | Expected behavior |
|---|---|
| V3-T01 | Actual selector dùng minY; craftedcase phân biệt với maxreturn |
| V3-T02 | Contrast anchor=0; Qidentity; matrix/scaler không đọc current labels |
| V3-T03 | Contextzero C→B_CAP đúng numerical objective; same weights/masks |
| V3-T04 | B0 chọnanchor nhưng C có alternative trong fixture vẫn được fit/chấm/deploy proposal |
| V3-T05 | O dùng past baseline packet, no oracle label; no-information generator không đọc futures |
| V3-T06 | Historicalp_LOW là actual forecast vintage; realized future label mutation không đổi earlier proposal |
| V3-T07 | Every funded sampler có 12 commonDEVfolds; current winner union trướcFWD |
| V3-T08 | Winner/tiebreak deterministic; changing FINAL labels không đổi DEV sampler choice |
| V3-T09 | Same effective params revalidation không skip decision hoặc claim fresh market observation |
| V3-T10 | Losingpaths preserved; scope/version/seed frozen before FINAL; no fee floor or leverage trigger |

### Exit gates

`G3-SELECTOR`, `G3-CONTROLS`, `G3-DEV12`, `G3-CHOICE`, `G3-FREEZE`, `G3-OWNER`.

Technical PASS không cần positiveDEV. Nhưng source/domain invalid không được “negative scientific result”; phải repair scope trướcfinal. Nếu no-validpath, bàn giao limitation chứ không forcewinner.

<a id="s 15"></a>
## 15. VWFO-04 — Shared policy, streaming replay và operational boundaries

### Mục tiêu

Chứng minh policy đã freeze chạy được tuần tự với legal information, không một bản backtest được đơn giản hóa khác live.

### Công việc

1. Nối forecast packet, searchstate, admission và engine wrapper qua one shared decision interface.
2. Xác minh candidate window/target window/readylag đúng §5.2, pending campaign ownership vànextopen.
3. Atomic publish proposal/modelbundle; expected incumbent/sequence/idempotency; expiries đúng 14-daydesign.
4. Recover weights/imputer/temp/normalizers/taxonomy/forecast watermarks và pending proposal state khi restart.
5. Fault injection trên development windows: latebar/forecast, duplicates, corrupted bundle, unknown source, search failure, pending orders, expired proposal.
6. Run một scoped actual streaming vs batch case; so predictions/params/activation/orders/fills/equity. Không cần chạy full research matrix cho từngfixture.
7. Kiểm `SAFE_ENTRY_PAUSE` vẫn duy trì exits/protection. Không gửi order thật hoặc sửa production.
8. Export exact commands để final wrapper dùng same controller. Tài liệu không được gọi unsupported live adapter là đã có.

### Tests

| ID | Expected behavior |
|---|---|
| V4-T01 | Prefix streaming và batch cùng information cho cùngproposals/IDs |
| V4-T02 | Future/late arrivals không backdate; wrong target window packet rejected |
| V4-T03 | Actual not-before, approval và waitflat áp đối xứng cácarms |
| V4-T04 | Duplicate/restart after publish-beforeack không double activation/orders |
| V4-T05 | Sameparams refresh watermark, không reset indicator/campaign/equity |
| V4-T06 | Expired/superseded hoặc incumbent-version mismatch rejected |
| V4-T07 | Missing median/temp/taxonomy làm bundle invalid, không weights-onlysuccess |
| V4-T08 | Max-revalidation pause không chặn protective exits hoặc forceclose ngoài contract |
| V4-T09 | Actual fills/rejects điều khiển strategy state, noexpected-fill feedback |
| V4-T10 | Scoped actual stream/batch financial parity và protected-tree zero change |

### Exit gates

`G4-CLOCKS`, `G4-LIFECYCLE`, `G4-PARITY`, `G4-RECOVERY`, `G4-NO_PRODUCTION_WRITES`, `G4-OWNER`.

Repair ở phase 4 làm đổineconomics/source dependencies phải invalidate phases 2/3 tương ứng; không giữlabelsfrozen sai chỉ để tránh compute. Không nhân bừa rereuns, chỉ affected scope.

<a id="s 16"></a>
## 16. VWFO-05 — Locked final WFO, D1/D2 và kết luận

### Mục tiêu

Tạo một kết quả có thể tái kiểm: H14 volatility forecast có giúp giảm Sharpe decay trong parameter selection không, và lợi ích có còn sau execution không?

### Công việc

1. Verify finalfreeze/source/feature/forecast/model/selector/economics và all owner permissions. Completion seal sau run không thay preregistration.
2. Chạy chosen sampler 128 trials/cutoff cho >=12 finalfolds,8 policies same pool, same cadence.
3. Cập nhật volatility weights theo frozen weekly model rule và metaweights theo matured archive; không select lại parameters của ML bằngfinalresult.
4. Xuất standardized paths của mọi winner, continuous accounts và actual activation lineage. Missing financial payload làblocker dù commandexit 0.
5. Chạy D2 core 5 arms×12 anchors nếu datafollow-up đầyđủ. Reuse exact shared paths, không nối account đã đổiparams làmD2.
6. Generate D1/Q decomposition, accountSR, D2, predictive/capacity/placebo contrasts, CI/sensitivity theoanalysisđã khóa.
7. Báo fullrisk/cost/activity diagnostics nhưng giữ Sharpe criterion. Không loại các folds xấu/no additional sampler FINAL để chọncurve.
8. Reproduce metrics từ raw outputs với zero engine calls, thêm scoped actual replay khi cầncertification đã registered.
9. Final verdict theo §10.6; cập nhật `WFO_VOL_CURRENT.md`, claims và budget. Không tự livepromote hoặc mởsymbolmới.

### Tests

| ID | Expected behavior |
|---|---|
| V5-T01 | PlannedIDs/dates và >=12 commonpairedfolds verified; no duplicated origin=extra fold |
| V5-T02 | AllSR/D/Y/Q từ raw daily returns; firstreturn, units, signs correct |
| V5-T03 | D1 decomposition exact tolerance; lowerIS không bị gọi forwardgain |
| V5-T04 | D2 H1 full-path parity; H2 frozen params/state, fallback anchors không bịdrop |
| V5-T05 | Continuous Sharpe từ whole daily path, cash/position/fee/MTM reconcile |
| V5-T06 | All final predictions giữ correctasof/model/labels; future mutation không đổi earlier decision |
| V5-T07 | Circular blocks wrap thật; unitsweekly/fold/daily đúng; zeros/constant series không falsep 0 |
| V5-T08 | No-info tapes/3 seeds fixed; composite là statisticmean, không giả portfolio Sharpe |
| V5-T09 | Tamper forecast/return/hash/complete=false/approval pending → đúnggateFAIL |
| V5-T10 | Regenerate report noengine/noinference; cache và actual replay scope rõ |

### Exit gates

- `G5-COMPLETE`: required financial runs/payloads và scope đủ.
- `G5-SHARPE`: primary/secondary metrics đúng và source traceable.
- `G5-CONTROLS`: O/B_CAP/placebos có actual outcomes, không fallback copy do wiringbug.
- `G5-INFERENCE`: procedure qualified hoặc honest limited precision; claims không overreach.
- `G5-EVIDENCE`: rawdata/forecast/returns/hashes/timelines và current report đầy đủ.
- `G5-OWNER_HANDOFF`: bàn giao đãreview; live permission không tự có.

Có thể kết thúc với technical PASS và scientific negative. Nếu mandatory payload còn thiếu, không được gọi technical complete. Không thêmphase 6, không bắt nghiên cứu phải thắng.

<a id="s 17"></a>
## 17. Evidence, báo cáo và quy tắc nâng cấp sau mọi lần chạy

### 17.1. Bốn trạng thái không được gộp

```text
implementation_status: NOT_STARTED | RUNNING | COMPLETE | BLOCKED
technical_gate: NOT_RUN | PASS | FAIL | BLOCKED
research_status: NOT_ASSESSED | EXPLORATORY | scoped scientific disposition
owner_review: PENDING | APPROVED | CHANGES_REQUESTED
```

Source model “67 tests passed” không làm technical WFO tự PASS. Một phase code hoàn thành nhưng chưa đủ actual runs vẫn chưa hoàn thành empirical scope. Cùng một phase có thể technical PASS/research negative, miễn actual required outputs đầy đủ.

### 17.2. Logical artifact layout cần map vào existing infrastructure

```text
configs/btc_volatility_conditioned_wfo_v1/
  registration.json
  handoff_acceptance.json
  model_manifest.json
  timeline.json
  source_and_economics.json
  sampler_specs.json
  candidate_and_label_policy.json
  selector_and_control_specs.json
  live_policy.json
  analysis_plan.json
  resource_budget.json
  final_freeze.json

evidence/btc_volatility_conditioned_wfo_v1/
  runs/<run_id>/
    request.json
    attempts.jsonl
    source_manifest.json
    forecast_packet_refs.json
    search_pool_refs.json
    model_fit_refs.json
    selection_rankings.jsonl
    admission_activation_refs.json
    candidate_forward_refs.json
    account_path_refs.json
    metrics.json
    fold_table.csv
    report.md
    gate_receipt.json
    detached_seal.json
  handoff_reconciliation.json
  development_matrix.json
  qualification_scope.json
  claim_ledger.jsonl
  upgrade_ledger.jsonl

handoff/
  WFO_VOL_CURRENT.md
  WFO_VOL_RUNBOOK.md
```

Đây là tên/contract đề xuất, không giả các CLI/schema đã tồn tại. Artifact bytes có thể nằm trong verified existing cache, không copy toàn bộ lake; reviewer vẫn cần truy được payloads, không chỉ hash viết tay.

### 17.3. Mẫu report bắt buộc cho mọi attempt

```markdown
# VWFO run — <run_id>

## Identity / scope
Phase, guide/registration/source hashes, branch/commit/dirty state.
Actual alpha/instrument/venue/15m, engine build và route.
Model H14 recipe/taxonomy, forecast dates, origin/target-window contract.

## Câu hỏi và phạm vi được phép
Primary contrast; điều giữ nguyên; điều thay đổi.
Model evidence accepted/limited; retrospective/exploratory/prospective.

## Planned vs actual
Samplers; INIT/DEV/FINAL origins; 128 trial attempts mỗi cutoff.
Completed/pruned/failed/unique candidates; base labels và extra winners.
Paired-valid folds; prediction/activation/same-params/fallback counts.

## Source và domain validity
Handoff reconciled từ source nào; còn thiếu gì.
Forecast/label/calibration chronology; economic start; pre-roll; actual sizing.
Stock Mode4 binding, full pool, min-Y actual ranking và rejected-proposal behavior.

## Model-to-action
p_LOW, baseline p_LOW, available_at và packet ID.
B0/B_CAP/O/C winners bằng params/digest, không chỉ ANCHOR/other.
Guard reasons; actual not-before/activation/delay; changed orders/fills.

## Kết quả theo từng fold
IS SR, FWD SR, signed decay, R, Q và IS-reference decomposition.
Continuous-account SR từ raw daily returns; D2 riêng.
CI và sensitivities: đúng sampling units, missing/degenerate cases.

## Controls / limitations
C vs B_CAP; C vs O; composite no-info; B0 vs A.
Effect có phải chỉ do exposure, thêm correction, hoặc một period không?
Không suy HIGH_VOL safety hoặc leverage permission từ LOW_VOL classification.

## Compute
Physical/logical work; CPU/wall/peak RSS; cache/reuse; failure waste.
Model inference/financial calls theo stage; budget còn lại.

## So với run trước
Comparable contract hay không? Changed code/params/data/metric/claim?
Exact invalidated_by/superseded_by/recomputed_from refs.

## Gates và quyết định
Gate ID, expected, actual, executed test/evidence refs, status.
Owner reference. Next authorized action. Không tự mở thêm scope.
```

Attempt FAILED/TIMED_OUT/CANCELED cũng cần report. Không có measurement thì null+reason; không fabricate peakRAM/wall từ estimate. Report tables sinh từ source artifacts, không sửa tay số để hợp narrative.

### 17.4. Sau mỗi run/upgrade

1. Append immutable attempt/result records.
2. Generate report từ actual evidence.
3. Verify required gates độc lập với reporter.
4. Update `WFO_VOL_CURRENT.md` và liên kết trong `RPS_CURRENT.md`, **không xóa trạng thái MF cũ**.
5. Scoped commit + owner review trước phase kế tiếp theo rule.

`WFO_VOL_CURRENT.md` chứa current source/phase, latest valid evidence, open blockers, remaining budget, comparison scope và **một next action được phép**. Nó không tự sửa hypothesis/horizon theo outcome.

### 17.5. Upgrade classification và invalidation

| Thay đổi | Cần làm |
|---|---|
| Typo/report arithmetic | Recompute report từ đủ raw source, correction record; không rerun engine |
| Probability/class-order/calibration source fix | Version forecast/model outputs, invalidate selectors và financial winners bị ảnh hưởng |
| Median/feature/taxonomy/H change | Forecast experiment version mới; không gọi cùng handoff-model frozen |
| Warmup/start/sizing/fees change | Invalidate affected search/labels/accounts; không report-only |
| Sampler/params-range/selection rule change | New registered research design, log data exposure |
| Performance/cache refactor | Required parity + resource evidence, không tự thừa nhận equivalence |
| Source/content revision | Rebuild đúng dependencies, không blanket purge hoặc giữ cache sai |

Upgrade record phải có parent/new hashes, lý do, before/after tests, numerical changes, affected artifacts/claims và owner reference. Lỗi đã sửa thì giữ evidence chứng minh đúng actual path; không chạy lại toàn bộ lab chỉ vì một README đổi.

### 17.6. Gate receipt mẫu, không phải certificate

```json
{
  "schema": "regime_lab.vol_wfo_gate.v1",
  "study_id": "btc_volatility_conditioned_wfo_v1",
  "phase": "VWFO-01",
  "technical_gate": "NOT_RUN",
  "research_status": "NOT_ASSESSED",
  "required_registry_hash": null,
  "source_dependency_hash": null,
  "registration_hash": null,
  "gate_results": [],
  "actual_engine_refs": [],
  "verified_reuse_refs": [],
  "model_handoff_reconciliation_ref": null,
  "open_blockers": [],
  "owner_review": {"status": "PENDING", "reference": null},
  "can_start_next_phase": false
}
```

Verifier cần một immutable required-gate registry độc lập; receipt tự khai empty list không được PASS vì all([]). Hash bytes thực, check `complete==true` và approval content/scope/version, không check key/file existence.

Detached seal chỉ tạo sau receipt/index finalized; không self-hash hoặc sửa mutable receipt mà giữ seal cũ. Test tampered returns/scalars/p_LOW/target time làm đúng gate fail.

### 17.7. CLI discipline

Inspect existing runner `--help`, symbol signatures và package origins. Prefer existing scripts/wrapper; thin `run_volatility_wfo.py` chỉ là tên đề xuất nếu cần implement.

Logical commands:

```text
plan | reconcile-handoff | build-pools | build-archive
run-development | freeze | replay-policy | run-final
verify | report | resume
```

Mỗi invocation có exact argv/cwd/interpreter/environment digest, start/end, exitcode và semantic status. Exit 0 + payload BLOCKED không là completion. Không expose secrets hoặc deploy actual orders.

<a id="s 18"></a>
## 18. Config skeleton — agent phải materialize trước jobs liên quan

```yaml
study_id: btc_volatility_conditioned_wfo_v1
guide_version: VOL-WFO-V1.0
status: SPECIFICATION_NOT_RUN
source:
  handoff_archive_sha256: 3722d70827a4ff84ce68bc765ad01bc472304fa102adf4da7d92ce50417d6c64
  reported_main_commit: 8cc366cb
  actual_commit: null
  actual_import_manifest: null
scope:
  alpha_id: A-SC
  symbol: BTCUSDT
  venue: BINANCE
  instrument_type: RESOLVE_FROM_APPROVED_ALPHA_CONTRACT
  strategy_timeframe: 15m
  execution_timeframe: 1m
  forecast_target_market: RESOLVE_FROM_MODEL_REGISTRATION
  live_orders_authorized: false
handoff_acceptance:
  raw_forecast_reconciled: false
  model_evidence_status: PENDING
  old_MF_bridge_status: PRESERVE_CLOSED_FOR_OLD_HORIZONS
  new_H14_bridge_status: PENDING_HANDOFF_RECONCILIATION
  significance_claim_verified: false
model:
  family: LIGHTGBM_EXISTING_HANDOFF_RECIPE
  recipe_id_reported: M4_LGBM_CONSERVATIVE_SLOW
  primary_horizon_days: 14
  secondary_horizon_days: 28
  secondary_used_for_primary_decisions: false
  conditioning_input: p_LOW_VOL
  context_is_probability_not_trade_direction: true
  class_order: [LOW_VOL, MID_VOL, HIGH_VOL]
  actual_model_hash: null
  feature_schema_hash: null
  taxonomy_hash: null
  imputer_hash: null
  temperature_hash: null
  hyperparameter_tuning_in_wfo: false
  forecast_refit_rule: VERIFY_AND_FREEZE_SOURCE_WEEKLY_MATURED_LABELS
wfo:
  wrapper: run_cutoff_walk_forward
  actual_wrapper_module: null
  engine_version_expected: 1.1.1
  engine_repository_read_only: true
  optimization_mode: mode_4_is_only_robust
  optimization_schedule: per_fold_causal
  candidate_selection_metric: is_only_robust
  scoring_backend: endpoint
  candidate_train_days: 180
  calendar_days: 14
  forward_days: 14
  d2_days: 28
  min_init_matured_origins: 12
  development_folds: 12
  final_folds: 12
  attempted_trials_per_sampler_cutoff: 128
  samplers_development: [S_TPE, S_SOBOL]
  sampler_final: UNSELECTED_BEFORE_DEVELOPMENT
  effective_parameter_dimensions: RESOLVE_2_OR_3_FROM_SCHEMA
  full_pool_prediction: true
  base_label_panel_max: 16
  label_union_all_registered_winners: true
  dynamic_refit_enabled: false
  regime_risk_scaling_enabled: false
  new_handcoded_TP_SL_mapping_enabled: false
selector:
  target: SIGNED_RELATIVE_SHARPE_DECAY
  global_regularization: 10.0
  correction_regularization_each_block: 10.0
  origin_weights_sum: 1.0
  min_meta_matured_origins: 12
  low_probability_std_floor: 0.05
  insufficient_context_policy: ZERO_CONTEXT_CORRECTION
  prediction_guard_sharpe: -0.10
  tie_tolerance_sharpe: 0.000001
  context_chosen_independently_of_global_admission: true
  final_arms: [A_M4, B0_GLOBAL, B_CAP, O_PERSIST, C_H14, P_NI_01, P_NI_02, P_NI_03]
  no_information_seed_list: null
  d2_arms: [A_M4, B0_GLOBAL, B_CAP, O_PERSIST, C_H14]
economics:
  initial_equity: 20000
  allocation_fraction: 0.10
  leverage_cap: 1
  fee_one_way_decimal: 0.0004
  slippage_one_way_decimal: 0.0001
  funding_contract: RESOLVE_FOR_ACTUAL_INSTRUMENT
  terminal: MARK_TO_MARKET
  standardized_initial_state: FLAT_NO_PREROLL_TRADES
  continuous_account_reset_each_fold: false
clocks:
  forecast_target_alignment_contract: MUST_RESOLVE_FROM_SOURCE
  common_ready_lag: null
  allow_backdated_activation: false
  proposal_ttl_days_proposed: 2
  max_revalidation_age_days_proposed: 28
  actual_activation_requires_safe_state: true
analysis:
  primary_contrast: C_H14_VS_B_CAP
  primary_metric: MEAN_SIGNED_SHARPE_DECAY_REDUCTION
  meaningful_reduction_sharpe: 0.20
  forward_noninferiority_margin_sharpe: 0.10
  continuous_noninferiority_margin_sharpe: 0.10
  require_O_PERSIST_for_forecast_information_claim: true
  require_placebo_composite_for_information_claim: true
  bootstrap_draws: 5000
  weekly_forecast_block_origins_default: 2
  fold_block_length_default: 3
  fold_block_sensitivities: [2, 4]
  daily_account_block_days_default: 14
  daily_account_block_sensitivities: [28, 42]
  block_choices_qualified_on_development: false
  confidence_level_one_sided: 0.95
  success_requires_all_registered_conditions: true
  intervals_are_simultaneous: false
  inferential_scope: APPROXIMATE_PAIRED_MEASURED_POLICY_OUTCOMES
authorization:
  owner_phase1_acceptance: null
  owner_bulk_budget: null
  owner_final_freeze: null
  production_writes_allowed: false
resources:
  allocation: null
  must_profile_before_bulk: true
  default_search_attempts_total: 7680
```

Fields `null`, `RESOLVE_*`, temporal rules và inference choices phải materialize trước job cần chúng. Không silently dùng 0 cho missinglag, guessed spot market hoặc assumed approved. Mẫu YAML không phải config chứng nhận run-ready hoặc actual QuantBT API.

<a id="s 19"></a>
## 19. Definition of Done và điều phải trả lại cho Bobby

### 19.1. Checklist

- [ ] Đã đọc actual H14 spec/registry/raw forecasts; reconcile 62,5% vs 28/48 và macroF1 trước claim.
- [ ] H14/H28 roles, oldMF closed status và new bridge authorization tách rõ.
- [ ] Không dùng duration 12,1/median 10 để giả physical market clock hoặc đổi refit tự động.
- [ ] Forecast packet có đúng target window/asof/calibration và model weights/reconstruction lineage.
- [ ] Actual Alpha/market/timeframe/economics verified; no preroll trades, real equity sizing, ready ordering.
- [ ] TPE/Sobol chạy qua same Mode 4 scorer/selector;128 trialfloor và full pool đúng.
- [ ] INIT>=12 matured; DEV>=12; FINAL>=12 commonpairedvalid hoặc truthful incomplete.
- [ ] Actual runner sử dụng min predicted relative Sharpe decay, C independent.
- [ ] B_CAP/O/no-info controls đúng architecture/information và được report.
- [ ] Primary không chứa risk-scaling, eventrefit hoặc new alpha exit logic.
- [ ] StandardizedD1, D2 và continuous account là các cohorts phân biệt; đủrawdailyoutputs.
- [ ] Bootstrap sampling units đúng, uncertainty qualified hoặc honest low precision.
- [ ] Frozen parameters giữ suốtFINAL; all zeros/losingfolds không bịxóa.
- [ ] Rawbytes/checksums/receipts/actual tests verified; không chỉ lưu hashes viết tay.
- [ ] Mọi attempt/upgrade có evidence; current handoff cập nhật, old records immutable.
- [ ] Finalreport nói đúng scope, no live promotion hoặc unsupported regime proof.

### 19.2. Final report phải trả lời năm câu hỏi

1. **Dự báo H14 đã được sử dụng thật thế nào?** Packet, cutoff, p_LOW, availability và actual selection.
2. **Selection có giảm Sharpe decay không?** Mean/median/perfold, CI và phần forward retention so với lowerIS.
3. **Có phải thông tin dự báo đóng góp không?** C so với B_CAP, O_PERSIST, no-info và B0.
4. **Có vận hành được không?** Continuous-account Sharpe, activationdelays, campaign ownership, fallback và measured cost.
5. **Quyết định tiếp theo là gì?** Giữ stock/global, ghi nhận scoped retention, còn uncertainty, dừng version hoặc đề xuất một research revision riêng — không tự mở rộng.

> **Đích đến:** sử dụng kết quả model như một giả thuyết có nguồn gốc rõ, rồi tạo một phép kiểm WFO đúng, đủ sâu và có đối chứng. Không dùng dự báo LOW_VOL để tăng rủi ro, không dùng những sai lệch của handoff để bỏ qua tín hiệu đáng thử, và không dùng kết quả dương của một bảng để thay việc chứng minh whole policy.

<a id="s 20"></a>
## 20. Nguồn, source ranges và phạm vi viện dẫn

### I1 — Handoff mới, nguồn chính

`handoff/RPS_HANDOFF_VOLATILITY_WFO_V1.md`, 173 dòng trong ZIP đã nhận; hash ở §0.

| Claim/source | Dòng trong file gốc |
|---|---|
| H14/H28 headline, model tests và engine chưa dùng | 13–30 |
| Targets, taxonomy, features, LGBM config, calibration/imputation | 34–81 |
| Horizon table, Brier scores và confusion matrices | 85–123 |
| File/spec/evidence/code/engine paths | 127–139 |
| Đề xuất WFO, risk/event-triggered changes và tests | 143–167 |

Guide này **trích lại các nguồn trên dưới nhãn HANDOFF_REPORTED**, và chỉ tự tính lại confusion-matrix arithmetic. Các sửa đổi methodology mới được ghi rõ là proposed contracts/migration; không giả tác giả nguồn đã viết chính sách selection trong guide này.

### I2 — Current-status handoff

`handoff/RPS_CURRENT.md`, 94 dòng, hash ở §0:

- Dòng 15–24: reviewer fixes, coverage/imputation/Chronos/weights disposition.
- Dòng 28–45: old MF verdict, old H56/H90 scope còn đóng.
- Dòng 49–63: model/feature/duration records.
- Dòng 73–93: new multi-horizon study, updated handoff link và nextaction.

“Duration 12,1 làmedian” ở dòng 79 khác mainhandoff dòng 24 ghi mean 12,1/median 10. Source empirical duration phải resolve; không tự hợp nhất thành một con số chắc chắn.

### I3 — Parent guide và lessons từ SD/FP

`REGIME_LAB_BTCUSDT_REGIME_PARAMETER_SELECTION_V1_5_PHASE_GUIDE_VI.md`, bản `BTC-RPS-V1.2 / MODEL-FIRST + REGIME DURATION`, mục 18:

- Forecast qualified + provenance + owner approval + financial domain qualification mới mở WFO.
- QuantBT Mode 4/per_fold_causal, >=128 trials, >=12 pairedfolds, same full pool.
- Sharpe-onlytarget, 0,20 meaningfulreduction, 0,10 guard margins.
- Warmup/sizing/readiness/admission/continuous account/outputs.

Current user handoff đề xuất H14/H28 nên guide mới explicitly thay horizon scope, không rename old 56/90 certificate.

### I4 — Approved consumer contract

`CONSUMER_ENDPOINTS.md`, `hmd-loader-v1`: source-of-truth readers, market scopes, null metrics và temporal semantics. Reader không cấp writer/backfill permission. `CryptoBinance1m` là USD-M perpetual; `CryptoBinanceSpot1m` là spot. HandoffWFO phải resolve đúng actual instrument.

### E1 — Optuna QMC, tài liệu chính thức

```text
https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.QMCSampler.html
```

Tham khảo first-trial inference, categorical independent sampling và Sobol sequence. Không chứng minh Sobol sẽ tạo WFOedge hoặc cấp phép upgrade installed dependency.

### E2 — Optuna TPE, tài liệu chính thức

```text
https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html
```

Tham khảo startup, objective-dependent sampling và actual configuration. Stock QuantBT binding phải verify trên host.

### E3 — LightGBM parameters

```text
https://lightgbm.readthedocs.io/en/stable/Parameters.html
https://lightgbm.readthedocs.io/en/v4.3.0/Parameters.html
```

Tham khảo bagging_fraction/subsample và bagging_freq/subsample_freq. Không bật thêm bagging hoặc sửa hyperparameters của model bàn giao mà vẫn gọi same frozen model.

### E4 — Probability calibration

```text
https://scikit-learn.org/stable/modules/calibration.html
```

Brier/proper losses, calibration và classificationaccuracy đo các khía cạnh khác nhau. Không suy xác suất đã calibrated chỉ vì có một temperature field.

### E5 — Ledoit & Wolf, 2008

```text
https://www.ledoit.net/jef2008_abstract.htm
```

Tham khảo robust time-series inference cho chênh lệch Sharpe. Default meanfold-decay bootstrap trong guide là một study procedure riêng, không tự là exact reproduction của studentized method trong paper.

### E6 — Cawley & Talbot, 2010

```text
https://www.jmlr.org/papers/v11/cawley10a.html
```

Tham khảo selection bias khi tối ưu lựa chọn model trên finite evaluation samples. Việc chọn H14 sau khi xem bốn horizons cần exposure disclosure và future scopedtest, không biến cùng dữ liệu thành untouched.

---

## Ghi chú ban hành

Tài liệu này không chứng nhận code đã implement, model đã có statistical significance, hoặc WFO đã có edge. Nó là guide triển khai tiếp theo từ **handoff hiện có**, kèm một bước đối soát hữu hạn và các gates thực thi đúng domain. Toàn bộ result fields phải được điền từ actual runs, không từ ví dụ hoặc nội dung Markdown này.
