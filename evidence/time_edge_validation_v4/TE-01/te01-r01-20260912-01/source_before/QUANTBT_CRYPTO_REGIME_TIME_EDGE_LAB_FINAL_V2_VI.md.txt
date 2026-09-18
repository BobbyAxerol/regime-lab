# QuantBT Crypto Regime & Parameter Time-Edge Lab
## Final V2 — Implementation guide cho agent, 10 phase, bốn alpha được cung cấp

**Ngày:** 2026-09-09  
**Baseline nghiên cứu:** `quantbt-engine==1.1.1`; native companion mục tiêu `quantbt-native==0.4.2` theo metadata nguồn đã đọc.  
**Phạm vi:** BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT; crypto trước, không Vietnam/Deribit/options trong lab này.  
**Input được phép:** đúng bốn file trong `alpha_to_tes_regime_model.zip`.  
**Trạng thái tài liệu:** hướng dẫn triển khai và kiểm chứng; có review trực tiếp alpha và diagnostics tổng hợp; **chưa có market backtest hoặc bằng chứng regime tạo thêm lợi nhuận**.  
**Quan hệ với tài liệu trước:** thay thế nội dung nghiên cứu của `QUANTBT_ROBUST_SELECTION_REGIME_AWARE_WFO_RESEARCH_GUIDE_V1_VI.md`; không sửa `implement.md`, repo QuantBT chính, các phase performance đã hoàn tất hoặc alpha bên ngoài archive.

> **Mục tiêu phải có thể bị bác bỏ:** regime information có giúp chọn bộ tham số profitable + stable và sử dụng chúng đúng thời điểm hơn calendar WFO, sau costs, uncertainty, transition và compute budget hay không? Không thiết kế thí nghiệm chỉ để tìm một kết quả dương.

---

# 0. Chỉ thị thực thi và những ranh giới không được vượt

## 0.1 Điều đã được phê duyệt

1. Chạy bằng `.py` và CLI; notebook không phải harness, không phải source of truth.
2. Tạo **một thư mục lab mới**, tách khỏi QuantBT chính và thư mục alpha production. Có thể giữ bản sao nguồn QuantBT trong lab làm reference/candidate.
3. Strategy/model/features vẫn ở Python/research layer; QuantBT xử lý simulation/accounting và cung cấp WFO/evaluation. Không thêm `quantbt-features` vào core.
4. Regime model chính để thử là persistent statistical jump model, có sparse/regularized extension khi có ích; rule-based và HMM/GMM là comparators có ngân sách, không là một cuộc thi ML vô hạn.
5. Tách inference, parameter switching, candidate-bank refresh và model retraining. Regime đổi không mặc định kéo theo retrain model hoặc full Optuna search.
6. Dùng tối đa những **khối thông tin hữu ích và đủ coverage** đang có trên server; không hiểu “tối đa” là nhồi mọi cột vào model.
7. Spot từ `2020-01-01` trở đi được coi là sạch theo xác nhận của người dùng. Chỉ giữ operational checks cần cho timestamp, units, gaps, availability và tính tái hiện; không mở lại tranh luận repair trước 2020 làm blocker.
8. Market-context universe có thể rộng hơn năm symbols giao dịch, nhưng chỉ dùng universe có eligibility point-in-time. Không lấy danh sách coin còn sống hôm nay làm historical universe mặc định.
9. Presets trong alpha đã được TPE tune trên toàn set: có giá trị đối chiếu, **không có giá trị OOS độc lập**.
10. Được sửa/viết lại **bản sao của bốn alpha** để đúng simulation domain. Mọi sửa phải version hóa, tách execution repair khỏi thay đổi alpha thesis và áp dụng nhất quán cho các experimental arms.
11. Lưu đầy đủ reports Markdown, JSON/JSONL, numeric tables và chart-source artifacts; không bỏ negative/inconclusive runs.
12. Không publish, merge, gửi lệnh live, sửa service, sửa collector hoặc nâng package production trong lab.

## 0.2 Safety là điều kiện bắt đầu, không phải checklist cuối

Agent phải bảo đảm output nằm trong `LAB_ROOT` mới. Các đường dẫn sau là **read-only inputs**:

- `QUANTBT_MAIN_ROOT`: repo chính do người dùng chỉ định.
- `HISTORICAL_DATA_CODE_ROOT`: code loader/metadata.
- `HISTORICAL_STORAGE_ROOT`: storage production.
- `ALPHA_ZIP`: archive gốc đã cung cấp.
- Mọi thư mục alpha/strategy khác: **không đọc để tìm thêm strategy, không chỉnh sửa, không import**.

Không chạy `git checkout`, `git reset`, `git clean`, `git worktree add`, `git gc`, `pip install`, `poetry update`, `uv sync`, build hoặc sửa `.git` bên trong QuantBT chính. Worktree dùng chung Git metadata nên không phải lựa chọn mặc định khi yêu cầu là không ghi vào repo chính. Dùng **physical copy hoặc export snapshot đọc-only**, sau đó `git init` độc lập trong lab nếu cần quản lý changes.

Không dùng hard links cho bản sao editable. Không đặt writable symlink quay về source/data gốc. Không `chmod/chown` nguồn gốc để làm “readonly”. Không dùng `sudo`, stop services, kill process ngoài process group của lab, thay cron/systemd, chiếm port hoặc tạo server dashboard.

**Path guards không phải sandbox an ninh đầy đủ.** Muốn bảo vệ trước lỗi import/extension, simulation worker phải chạy trong cơ chế OS đã được phép: isolated user/container với source/data mounts read-only, `LAB_ROOT` writable, không credentials/live keys, không socket Docker/host, không network khi fit/replay. Nếu máy không có isolation như vậy, agent chỉ tạo/scaffold/audit trong lab; không tự claim “tuyệt đối không thể ghi ra ngoài” và không chạy code chưa được containment.

Network acquisition nếu cần là stage riêng có allowlist, ghi vào lab. Không download khi backtest đang replay. Tất cả cache (`NUMBA_CACHE_DIR`, Matplotlib config, temporary files, model cache, Python bytecode nếu có) trỏ vào lab. Dùng `PYTHONDONTWRITEBYTECODE=1` trong các process đọc source protected.

## 0.3 Resource policy đề xuất ban đầu

Đặt một worker, tối đa hai CPU dành cho lab, memory working-set cap 4 GiB và disk quota cấu hình trước. Đây là budget khởi tạo, không phải giả định server có tài nguyên rảnh. Đọc storage theo partitions/chunks, có backpressure; không load tất cả 1m history của mọi symbols vào RAM. Nếu cần tăng tài nguyên, ghi estimate và xin cấp budget thay vì ảnh hưởng services đang chạy.

Kill/cancel chỉ tác động children của `lab_run_id`; cleanup chỉ xóa lab-owned temporary paths. Evidence committed không bị cleanup tự động.

---

# 1. Bằng chứng đã có và giới hạn thực tế

## 1.1 Archive đã đọc đầy đủ

Archive SHA-256:

```text
57406dbb9ffdcf4617e4895925126fa73600a585a6541f996c6b2d980f6701ae
```

Bỏ qua `__MACOSX/` metadata, có đúng bốn `.py`:

| Alpha ID | File | Lines | SHA-256 |
|---|---|---:|---|
| A-VWAP | `vwap.py` | 249 | `ef9e7e8a998a68584e742fb698cfd06ee27ec8355f76566b480810b552376d84` |
| A-HASH | `hash_momentum.py` | 166 | `ab35d90680ea723440d8ad4d831029505e54bf2c2567350313b1cacbfea6c773` |
| A-HMA | `adaptive_hma_cpp.py` | 349 | `86c88f38e86b7e5b6e92108ef30704e5bdd3d69f6a9f9c07069fdff03ad958d2` |
| A-SC | `signal_combine.py` | 145 | `d540deef7d4275d58033a283421edb09296a7df9032361e050512a02823fc504` |

Tên `adaptive_hma_cpp.py` không chứng minh có C++: file cung cấp là Python/Numba. Archive không có dataset hoặc native strategy module đi kèm.

## 1.2 Kiểm chứng đã thực hiện khi viết guide

- Parse AST bốn files, inventory functions và literal parameter dictionaries.
- Chạy 21 diagnostics local, gồm bốn syntax/inventory checks, các source-function probes và một synthetic jump-model DP oracle.
- Khi chạy thân hàm alpha: bỏ decorators/imports bằng AST trong namespace riêng; inject NumPy/Pandas nơi được ghi rõ. Không import/execute nguyên archive như production package.
- Một test fallback SignalCombine dùng API-minimal stubs để chứng minh sai nhánh method dispatch; không thay cho test trên thư viện `ta` thật.
- Environment probes: NumPy 2.3.5, pandas 2.2.3; **không phải environment QuantBT 1.1.1 đã khóa**.
- 21 probes xác nhận đúng hiện tượng/thuộc tính chúng kiểm; không có nghĩa 21 bug hoặc 21 tests của QuantBT đã pass.
- Chưa cài QuantBT trong runtime review, chưa chạy NumPy/Numba production parity, chưa chạy exchange data, chưa chạy TPE/WFO và chưa đo edge.

## 1.3 Repo đã đối chiếu được

`pyproject.toml` trên main hiển thị core 1.1.1 và companion 0.4.2; source layout là `src` [S1]. Docs phân biệt target-close, event-next-open, intrabar và fill replay [S2–S4]. Methodology WFO được đọc ở mức source-page [S5]. Loader có `load(..., columns="full")`, projections và normalization [S6].

Các trang web có thể ở các cached revisions khác nhau. Không lấy chúng làm một checkout nhất quán. Git HEAD chưa pin được do network/DNS trong runtime review; `endpoint.py` và data `endpoint.md` không lấy được đầy đủ. Phase LAB-01 phải xác nhận actual installed signatures, lockfiles và source SHA từ server. Không bịa API mới rồi gọi là API hiện tại.

Các nhận xét selector top-trials/baseline-floor ở guide trước là **hypotheses cần đối chiếu lại pinned source**, không tự mặc định còn lỗi trong 1.1.1.

---

# 2. Presets full-sample và quyền diễn giải kết quả

## 2.1 Bốn tầng alpha version bắt buộc

| Tầng | Mục đích | Được dùng để chứng minh regime edge? |
|---|---|---|
| `raw_supplied` | Bytes nguyên gốc, provenance | Không |
| `legacy_reproduction` | Sửa tối thiểu import/dependency để tái hiện đúng hành vi cũ | Chỉ diagnostic/in-sample reference |
| `canonical_v1` | Execution/timing/accounting chuẩn; thesis alpha giữ lại tối đa | Có, sau correctness và cùng version cho mọi arms |
| `research_revision_N` | Thay signal formula, stop convention hoặc directions có chủ đích | Thí nghiệm riêng, không nhập lẫn canonical results |

Sửa nguyên lý ATR của HASH, cách crossover SignalCombine hoặc cho SignalCombine short là thay đổi strategy semantics, dù hợp lý. Ghi trong `semantic_delta.json`; không quy lợi ích của những sửa đó cho regime.

## 2.2 Presets không phải clean warm-start cho quá khứ

Tất cả presets người dùng đưa được gắn:

```text
provenance = user_full_sample_tpe
eligible_for_retrospective_reference = true
eligible_for_early_fold_warm_start = false
eligible_for_primary_candidate_bank = false
eligible_for_independent_oos_claim = false
```

Có thể chạy chúng trên cùng corrected engine để thấy scale/thesis tham khảo. Không bắt selector mới vượt headline của những presets biết toàn sample. Không dùng chúng để thu hẹp bounds quanh một winner rồi gọi kết quả là untouched historical OOS.

Các bounds/protocol do con người đã nhìn lịch sử thiết kế cũng tạo research selection. Nested historical replay giúp kiểm soát leakage trong code nhưng không xóa toàn bộ prior research exposure. Nếu không biết tuning cutoff, historical outcome chỉ mang claim `RETROSPECTIVE_NESTED_CAUSAL_RESEARCH`; xác nhận mạnh cần data sau protocol freeze hoặc một holdout thực sự chưa dùng. Không bịa một khoảng năm cuối thành “untouched”.

## 2.3 Không tự động nhận các dictionary không thuộc alpha

`vwap.py` có các dictionary `cetp_*`, một dictionary sizing/SL (`keke`), và default cuối đang ghép preset được chú thích cho VN30F1M. Chúng **không phải thêm alpha thứ năm**, không phải valid VWAP search space. Chỉ đăng ký bốn files; lọc preset keys bằng schema của alpha. Các dictionary khác lưu ở `unmapped_presets.json` để audit, không chạy.

---

# 3. Review từng alpha và kế hoạch adaptation

## 3.1 A-HASH — Momentum với partial TP ladder

**Entry points:** `calculate_indicators` lines 5–38; `execute_hash_momentum_backtest` 42–128; `run_hash_strategy` 130–155.

### Findings trực tiếp

| ID | Vị trí | Quan sát | Cách xử lý trong lab |
|---|---|---|---|
| AH-01 | import + 131–133 | Dùng `np` nhưng không import numpy; wrapper bị `NameError` trong standalone module | Thêm import chỉ trong bản sao; original hash giữ nguyên |
| AH-02 | 21–28 | Biến gọi ATR dùng absolute close-to-close move, không nhận high/low; `atr[14]` không guard short input | Legacy giữ `close_move_rma14`; corrected-ATR là version riêng dùng true range |
| AH-03 | 64–94 | `equity` chỉ cộng realized PnL/fees, không mark open position | Không dùng cột này làm equity chuẩn hoặc objective; QuantBT ledger authoritative |
| AH-04 | 74–94 | Chuỗi `elif` chỉ xử lý một TP stage/bar, final TP còn bị phụ thuộc stage trước | Primary dùng explicit ordered ladder; legacy stage-lock là reproduction có nhãn |
| AH-05 | 108–125 | Entry book tại close vừa dùng ra signal; không có open/latency/gap model | Close signal → real next-open fill; levels liên quan entry dựa actual fill |
| AH-06 | 76–86 | TP2 quantity là % của phần còn lại, không phải % entry quantity | Khóa `fraction_of_remaining` để giữ ý nghĩa; không tự đổi về % original |
| AH-07 | 157–162 | 4/6 presets không thỏa `tp1 < tp2 < final` | Reject cho canonical simultaneous ladder; lưu raw order, không sort ngầm |
| AH-08 | 101–104 | Capital check riêng không có margin/reservation/funding model | Chuyển sang QuantBT admission; `initial_capital`, fee, notional là experiment config |

Presets TP không đúng thứ tự cho ladder đồng thời: `huhu`, `bubu`, `haft`, `kuku`. `hihi`, `kaka` có thứ tự tăng. Đây không khẳng định legacy state machine không chạy; nó nói legacy có semantics khác một ladder đặt đồng thời.

### Adapter đích

`HashMomentumEventAdapterV1` giữ indicator logic/cooldown/entry conditions, phát market entry intent sau close. QuantBT tạo fill; adapter cập nhật campaign và đặt reduce-only stop + ladder theo actual fill. Orders của TP stages phải không over-close; stop remaining quantity giảm sau mỗi fill. Không cộng PnL hoặc phí trong adapter.

Chốt `TP2=remaining_fraction`: nếu entry 10 units, TP1 50% → còn 5, TP2 60% phần còn lại → fill 3, còn 2 cho final. Ghi request/fill/remaining quantities trong ledger.

Khi high chạm nhiều targets trong cùng bar, matcher xử lý theo path/priority đã khóa; nếu stop và targets cùng bị chạm, dùng cùng deterministic ambiguity contract ở mọi arms. Không dùng `elif` legacy để tạo artificial delayed fills rồi gọi là realistic execution.

Nếu engine chỉ phát callback tại bar-close, không giả định child protection đặt sau callback đã tồn tại ngay sau entry đầu bar. LAB-02 phải kiểm capability parent/child activation tại fill. Có thể mở rộng hook trong **lab copy** nếu thiếu, hoặc ghi delay theo contract rõ; không tạo fills thủ công để né engine.

### Search space khởi tạo — proposal cần freeze trước outcomes

- `mom_len`, `ema_len`: integer periods; chọn dải từ thesis và timeframe, không centered theo preset full sample.
- `mom_threshold_mult`, `stop_loss_perc`: positive, unit explicit; log/linear transform được ghi.
- Parameterize `tp1_R > 0`, `gap12_R > 0`, `gap2F_R > 0`; derive `tp2_R=tp1_R+gap12_R`, `final_R=tp2_R+gap2F_R`.
- `tp1_fraction`, `tp2_fraction_remaining` trong `(0,1)`; fee không phải search parameter.
- `cooldown_bars >= 1` primary; cooldown bắt đầu từ confirmed terminal fill.
- ATR convention là structural family version, không silently mixed trong một trial table.

## 3.2 A-VWAP — Daily VWAP mean reversion với HTF filter

**Entry points:** helpers 8–93; `core_vwap_mean_reversion_logic` 98–178; `generate_vwap_signals` 182–228.

### Findings trực tiếp

| ID | Vị trí | Quan sát | Cách xử lý |
|---|---|---|---|
| AV-01 | 8–17, 43–77, 193 | Một số helpers và `new_day[0]` không guard input ngắn/rỗng | Fail-fast hoặc no-signal valid warmup; không crash/silent zero |
| AV-02 | 98–178 | `open_p` được truyền nhưng không dùng; output chỉ `pos` | Không feed `pos` vào close-target rồi claim SL/TP fills đã đúng |
| AV-03 | 128–150 | Time stop được xét trước price stop/TP dù time condition là boundary event | Freeze event sequence mới: resting protection tại price phases, time stop submit đúng close/next phase |
| AV-04 | 136,146 | Dynamic VWAP dùng full current bar VWAP để xét high/low cùng bar | Không coi full-bar VWAP là limit đã known tại open |
| AV-05 | 158–174 | Giả entry close; stop và TP từ giá giả đó | Entry next-open và levels từ actual fill cùng ATR đã available |
| AV-06 | 200–217 | HTF resample/shift có ý thức causal nhưng availability phụ thuộc index convention | Closed-HTF prefix fixtures; join theo available_at, không chỉ label timestamp |
| AV-07 | 231–249 | Default `params` chọn `tete` chú thích VN; nhiều unrelated presets | Không chạy default; chỉ explicit config cho 5 crypto symbols |

### Adapter đích

`VwapMeanReversionEventAdapterV1` sở hữu VWAP/RSI/ATR/HTF EMA và entry eligibility, không sở hữu fills. Daily VWAP reset tại UTC day theo fixed convention. HTF EMA chỉ dùng bucket đã hoàn tất; không thêm shift hai lần nếu provider đã cung cấp available-at chính xác.

Các dynamic-VWAP exit hợp lệ cần chọn một và version:

- `resting_previous_observed_vwap`: limit được sửa sau close, có hiệu lực từ bar tiếp theo.
- `close_decision_market_exit`: sau close nhận ra exit condition rồi submit market next-open.

Không dùng `vwap[t]` để retroactively đặt intrabar limit. Primary giữ `exit_at_vwap=False` trong pilot nếu muốn giảm ambiguity; sau khi adapter pass, bật như một structural candidate family đã budget. Đây là quyết định experiment cần ghi trước khi nhìn performance, không tắt vì backtest xấu.

HTF EMA length dài có warmup lớn hơn 200 base bars. Warmup gồm indicator history, HTF completion và convergence policy. Với EMA span `L`, có thể chọn số HTF observations `n` sao cho `(1-2/(L+1))^n <= epsilon` (epsilon preregistered); không hardcode 200 bars cho mọi L. Empty/missing hours không được coi là observed price zero.

Search keys: `rsi_len`, `rsi_os<rsi_ob`, `dev_mult>0`, `atr_len`, `stop_atr>0`, `target_r>0`, `htf_ema_len`; `htf_tf` structural. `time_stop_bars` inactive khi `time_stop_on=False`. `dev_len=50` hiện hardcoded: giữ fixed primary; muốn expose phải thành revision có audit.

## 3.3 A-HMA — Adaptive HMA trend strategy

**Entry points:** helpers 8–129; `core_adaptive_hma_signals` 135–293; wrapper 298–328.

### Findings trực tiếp

| ID | Vị trí | Quan sát | Cách xử lý |
|---|---|---|---|
| HM-01 | 283 | Comment coi next open bằng previous close; core không nhận `open` | Actual fill từ engine; không equality assumption |
| HM-02 | 204,214–249 | `pos_weight` là position trước bar nhưng có `exit_type/exit_price` nội bar | Không đưa riêng weight vào ordinary target backtest; cần event/intrabar contract |
| HM-03 | 214–246 | Giá SL/TP đóng trong alpha, không gap/slippage/fill model | Levels là intents, giá fill engine quyết định |
| HM-04 | 333–349 | `hfhf`,`hjhj`,`hoho`,`hbhb` có min_length > max_length | Raw refs giữ; canonical reject, không swap ngầm |
| HM-05 | 135–140,160–167,310–320 | `time_ms`, `volume`, `double_up` unused; `sl_mult` có trong 13 presets nhưng không được đọc | Drop khỏi active search; ghi ignored/deprecated flags, không triển khai tính năng mới dưới tên cũ |
| HM-06 | 161–162 | `mintick=0.0001` hardcoded cho mọi instrument | Dùng instrument tick metadata; pip-buffer semantics versioned |
| HM-07 | 45–55 | RSI flat seed=50 nhưng vòng tiếp theo avg_loss=0 đặt100 kể cả avg_gain=0 | Canonical flat=50; indicator repair riêng, trước A/B |
| HM-08 | 7–134 | `fastmath=True` và dynamic helper padding đầu chuỗi | Reference fastmath off; finite/short-input checks và warmup convergence |
| HM-09 | 303–304 | Epoch conversion giả định nanoseconds | Convert timezone/unit explicit; time_ms hiện unused không được gọi là live timestamp correctness |

ATR helper dùng EMA thay vì Wilder RMA. Đây là **convention của alpha cần giữ hoặc version**, không tự coi là bug rồi đổi trong mọi arm. Giữ adaptive-length logic `adaptPct=0.03141` trong primary; model regime bên ngoài không thay internal adaptation này.

### Adapter đích

`AdaptiveHmaEventAdapterV1`: indicators/state adaptation tính tại close; stop candidates dựa các mức đã known, entry dựa actual fill; bracket resting trong engine. Technical RSI/HMA exit là close decision, earliest market fill theo next-open contract, không gán `exit_price=close[t]` sau khi biết close.

Giữ `SL mode` và cách clamp hiện tại sau khi viết spec; không sửa thành strategy khác vì tên maxSL gợi ý một convention khác. Kiểm SL/TP hợp lệ đối với actual entry khi gap. Có policy rõ khi target nằm sai phía sau gap: reject entry/bracket hoặc normalize theo documented entry-distance contract, không tự fill có lãi tức thời.

Search parameterization `max_length=min_length+positive_span`, `minor_max=minor_min+positive_span`; `atr_fast<atr_slow` nếu family được định nghĩa như vậy. Không đưa `sl_mult/double_up` vào TPE khi chúng không có effect. `flat` là độ của slope implementation, không price scale.

HMA có internal volatility adaptation nên là control quan trọng: external regime phải chứng minh lợi ích **thêm trên adaptation đang có**, không thay adaptive HMA bằng fixed HMA rồi quảng bá regime thắng.

## 3.4 A-SC — SignalCombine / AlphaTrend-like long-flat

**Entry points:** `cal_TA` 16–60; `generate_signals` 62–112; `apply_SigCombine_strategy` 119–145.

### Findings trực tiếp

| ID | Vị trí | Quan sát | Cách xử lý |
|---|---|---|---|
| SC-01 | 39–48 | Thiếu volume thì tạo RSI nhưng dispatch method theo `novolumedata` cũ, có thể gọi MFI method trên RSI | Resolve `use_rsi` một lần; main crypto requires volume, fallback explicit |
| SC-02 | 20 | `coeff=int(...)` | Search integer; không quảng cáo fractional trials là khác nhau |
| SC-03 | 67–69 | Cross formula khác conventional crossover(trend,trend.shift(2)); comments có nêu cách so riêng | Giữ source convention ở canonical-v1; standard crossover là research revision tùy chọn |
| SC-04 | 109–110,125–140 | Approved/shifted signals được tạo nhưng execution dùng unapproved long/short | Không double-shift; decision timestamp và intent timing khai báo riêng |
| SC-05 | 135–140 | Position chỉ 0 hoặc2; short branch đặt0, không có negative position | Canonical là long-flat; không tự bật short |
| SC-06 | 37–48,79–102 | Repeated pandas access và bars-since semantics | Có thể vectorize/array-state trong lab sau output parity; không đổi reset rules |

`regime_threshold` trong file là ngưỡng MFI/RSI nội bộ, **không phải output của regime model mới**. Audit giữ tên public, thêm namespace `alpha.condition_threshold`; external market state dùng namespace khác.

Ý nghĩa amplitude2 chưa có account contract đi kèm. Primary đề xuất normalize direction `0/2 → 0/1` với fixed experiment notional, ghi đây là `sizing_mapping_v1`; chạy legacy amplitude reproduction riêng. Không suy `2` mặc định là leverage2 hay 200% equity.

Target series là intent sau close, không phải realized position. Adapter long-flat phát entry/exit sau close, engine fill next-open. Không có stop/TP riêng trong file: không tự thêm protective exits chỉ để kết quả tốt hơn. Risk controls chung của experiment và liquidation vẫn áp dụng.

---

# 4. Chọn execution contract trước khi so methodology

## 4.1 Primary economic setup

Các alpha có long/short không được execute như spot-cash có thể short miễn phí. Đề xuất primary cohort:

- Signal/entry indicators từ **USD-M linear perpetual OHLCV** cùng instrument giao dịch, nếu dataset sẵn có.
- Spot sạch từ 2020, perp activity/OI/funding/basis dùng làm regime/context theo availability.
- Execution trên real perp OHLCV từ khi instrument có dữ liệu; phí, funding, multiplier, tick/lot lấy contract đã pin.
- A-SC vẫn long-flat trên cùng family account cho comparability. Spot-only long-flat là cohort phụ nếu được chạy, không merge với perpetual results.

Nếu muốn tái hiện alpha từng sinh trên spot rồi execute perp, đó là `signal_venue != execution_venue` contract riêng; alignment/basis explicit. Không lấy spot candles để giả fill perp mà không nhãn.

Mọi account configuration là experiment-level, không TPE tuning: capital, base notional, leverage limit, fee model, funding và slippage. Có thể khởi tạo pilot ở equity 20,000 USDT và entry notional 2,000 USDT, leverage cap 1 trên linear-account contract nếu capability support; đây là **proposal sizing**, không thông số user đã dùng. LAB-01 phải freeze actual config một lần cho tất cả arms, không chọn theo return đẹp.

Funding thiếu lịch sử: không tự xem là0 trên primary có claim realistic net carry. Cohort tương ứng được đánh dấu missing hoặc nghiên cứu no-funding với disclaimer riêng. Cost scenarios phải dùng cùng assumptions cho mọi arms, không áp dụng stress chỉ cho baseline.

## 4.2 Một signal-close không thể fill lại chính close vừa quan sát

Primary clock:

```text
Base execution bars complete / protective orders processed
→ strategy observes completed alpha bar
→ regime/provider observations available at that time
→ decision and staged commands
→ earliest allowed next execution boundary
→ engine acceptance/fill/accounting
```

Các events cùng timestamp có sequence ID và ordering contract: publication/close observation phải xảy ra trước quyết định; quyết định hoàn tất phải trước activation. Không suy thứ tự chỉ từ millisecond equality.

Theo docs source-page, new event research có contract `event_lifecycle_v3_next_open`; phải request explicit, không tin default. `close_target_v2` không mô phỏng intrabar artifacts dù DataFrame có `exit_price` [S2–S3].

## 4.3 Protective-order fidelity

Có thể tính indicator trên 15m/1h và replay protective orders bằng 1m bars; vẫn có ambiguity bên trong 1m. So sánh tất cả arms dùng cùng resolution/path contract. Không coi dữ liệu 1m là tick/L2 thật.

Nếu baseline cũ chỉ simulate 15m, giữ hai cohort: exact legacy resolution và common higher-fidelity corrected cohort. Đừng quy lợi ích do đổi fill fidelity thành regime edge.

## 4.4 Minimum engine adapter facade — API lab, không giả API QuantBT mới

Agent triển khai một `QuantbtBridge` trong lab có các operations:

```text
inspect_installed_contracts()
prepare_market(snapshot, economic_contract)
evaluate_candidate(alpha_factory, params, evaluation_spec)
run_continuous(alpha_factory, parameter_policy, timeline)
replay_fixed_intents(intent_tape, economic_contract)
export_required_artifacts(result)
```

Đây là interface của lab cần implement, không các methods được khẳng định đã tồn tại trong 1.1.1. Bridge gọi public endpoints/supported hooks đã kiểm tra. Nếu WFO public chỉ chấp nhận position tapes và không đủ dynamic reactive lifecycle, dùng evaluator/scheduler adapter trong **lab candidate copy** với engine hiện tại. Không phát triển một matching/accounting engine thứ hai.

Required capability fixtures: child activation sau actual fill, cancel/amend effective phase, partial reduce-only, next-open gap, terminal open position, carry account qua parameter switch. Unsupported không được silently lower sang khác economics; ghi `BLOCKED_CAPABILITY` và patch có tests chỉ trong lab.

---

# 5. Kiến trúc lab và registry

```text
LAB_ROOT/
├── .lab_marker.json
├── README_AGENT.md
├── configs/
│   ├── study_registration.json
│   ├── sandbox_policy.json
│   ├── alpha_registry.json
│   ├── parameter_schemas.json
│   ├── economic_contract.json
│   └── variant_registry.json
├── vendor_readonly/
│   ├── alpha_zip_original.zip
│   ├── alphas_raw/                 # đúng 4 files
│   ├── quantbt_1_1_1_snapshot/
│   └── historical_loader_snapshot/
├── quantbt_candidate/              # independent editable copy, không hardlink
├── wheelhouse/                    # exact artifacts; không thay env production
├── environments/                  # baseline, candidate/model nếu cần tách
├── src/crypto_regime_lab/
│   ├── safety/
│   ├── data/
│   ├── alphas/                     # 4 adapters + shared utilities
│   ├── selector/
│   ├── regime/
│   ├── response/
│   ├── policy/
│   ├── quantbt_bridge/
│   ├── experiments/
│   └── evidence/
├── tests/
├── scripts/                       # mọi harness là .py
├── snapshots/                     # immutable data/manifests
├── evidence/{study_id}/{run_id}/
├── reports/
├── figures/                       # tạo bởi .py từ committed artifacts
└── .cache/
```

Một model/data block dùng chung có thể cache theo immutable identity, nhưng run role và cutoff phải được kiểm trước reuse. Một full-history cached model không được lọt vào early folds vì tên cache trùng.

Baseline/candidate import trong processes riêng. Không `sys.path.insert` source production. Bản sao `quantbt_candidate` phải có package version metadata riêng/local label hoặc source identity rõ; không publish đè1.1.1. Registry ghi actual `quantbt.__file__`, extension path/digest và Python environment.

## 5.1 Quyền sửa alpha rộng nhưng có causal attribution

Agent được sửa syntax, imports, defensive guards, event adaptation, serialization và state machine để đúng domain. Mỗi change lưu:

```text
alpha_id + raw_sha + adapter_version
change_kind = packaging_fix | execution_repair | indicator_repair | thesis_change
before_semantics / after_semantics
source_line_refs
reproducer
expected_effect
applies_to_experiment_arms
```

Thesis changes không bắt user trả lời từng tiểu tiết nhưng phải có default bảo thủ đã nêu trong guide, version riêng và không tự thay primary vì performance tốt hơn. Nếu behavior chưa định nghĩa được an toàn, giữ alpha đó `NOT_READY` trong result matrix; không thay bằng alpha khác hoặc fabricate scores.

---

# 6. Data design: server-first, năm symbols, không mở rộng scope ngầm

## 6.1 Inventory theo data products, không theo các tên class giả định

Source loader đọc được có `CryptoBinance1m`, `load(..., columns="full")` và các timezone/dtype/validation policies; những products khác phải xác nhận bằng actual files/classes trên server [S6]. Agent tìm `endpoint.md`/`endpoints.md` trong bản snapshot code, không kết luận repo thiếu chỉ vì không tải được web page.

Tạo `data_product_inventory.json` với:

```text
product_id / actual_reader_symbol / code_sha
storage_paths / file_hashes / schema / units
earliest_observed / latest_closed / coverage_by_symbol
source and measurement method
bar_timestamp_convention / available_at_rule
revision/vintage policy
license / permitted research and redistribution
read_only_verified
```

Chọn đầu vào theo closed snapshot, không để default `limit`, projection hoặc warning-only validation âm thầm thu hẹp/chỉnh dữ liệu. Failure khi đọc partition phải xuất thành missing coverage; không chạy một backtest trên phần còn lại rồi ghi “full sample”.

## 6.2 Cohorts và phạm vi lịch sử

- `SERVER_CORE_LONG`: spot/perp OHLCV + quote-volume/trade-count/taker volumes thực có. Ưu tiên từ 2020; mỗi symbol bắt đầu tại listing/coverage/warmup hợp lệ.
- `SERVER_DERIVATIVES`: thêm funding, OI, ratios, basis nếu server thực sự có; không giả lịch sử dài bằng nến.
- `SERVER_LIQUIDITY`: snapshots/spread/depth nếu đủ; same-period comparator riêng.
- `FREE_ENRICHED`: stablecoin supply, published whale alerts, BTC ETF flows hoặc network metrics có quyền sử dụng; không là prerequisite để main lab chạy.

Tất cả inventory được làm, nhưng chỉ các nhóm đủ support/coverage mới vào model. Không lấy giao của tất cả nguồn khiến core cohort bị co xuống một tháng. Mỗi enrichment phải compare với core trên **cùng interval**.

Không đọc trade alphas/venues ngoài phạm vi. Market-context universe có thể dùng thêm crypto candles, nhưng historical membership tính từ dữ liệu eligible tại thời điểm, không từ future liquidity rankings. Không suy full market cap dominance từ giá/volume nếu thiếu supply lịch sử.

## 6.3 Timestamp và resampling

Lưu riêng `event_time`, `bar_open`, `bar_close`, `source_published_at`, `available_at`, `archive_ingested_at`, `vintage_id`. UTC là clock chuẩn; conversion ms/ns phải explicit. Binance public archive có thay đổi units theo sản phẩm/thời kỳ; loader phải có unit assertions, không đoán bằng một phép chia cố định [S16].

Một feature từ bucket4h `[00:00,04:00)` chỉ usable sau bucket đóng và publication/processing delay đã định. Gắn feature bằng backward as-of join theo **available_at**, không label đầu bucket. Không forward-fill một observation qua TTL vô hạn.

Aggregation:

- OHLC: first/max/min/last đúng closed bucket.
- Volume/trades/taker activity: sum theo đúng units; không truncation fractional crypto volume.
- OI/mark/funding estimates: last available hoặc convention cụ thể, không sum OI.
- Funding cash events: giữ events, không biến thành bar rate bị áp nhiều lần.
- Snapshots: dùng `sample_time` thật nếu có; đầu giờ lưu trữ không phải availability.
- Missing bar: giữ mask; không fabricate zero volume hoặc price fill để tạo artificial low-vol regime.

User clean-spot convention được giữ. Nếu gặp explicit source flags cho synthetic/proxy rows sau cutoff, không tự bác bỏ convention; ghi consistency exception và sensitivity cohort. Không dùng futures-derived spot proxy để “chứng minh” độc lập về spot-perp basis mà không flag.

## 6.4 Feature blocks và toán học

Với price close đã available, `r_t=log(C_t/C_{t-1})`. Chỉ dùng trailing observations và preprocessing fit đúng cutoff.

### G1 — Direction và path shape

\[
RV_{t,w}=\sqrt{\sum_{i=t-w+1}^{t}r_i^2},\quad
T_{t,w}=\frac{\sum r_i}{\sqrt{\sum r_i^2}+\epsilon},\quad
E_{t,w}=\frac{|\sum r_i|}{\sum|r_i|+\epsilon}.
\]

`T` là direction descriptor, không được gọi t-stat. `E` là path efficiency, giúp phân biệt high-vol range và high-vol directional. Thêm downside/upside variation ratio hoặc jump concentration khi block được budget; không tự gọi đó là crash probability.

### G2 — Activity/active-flow proxies

\[
I_t=2\frac{V^{taker-buy}_t}{V_t}-1
\]

Cùng volume units và interval. `V=0` → missing/undefined status, không ép0. Có thể dùng quote-volume/trade-count changes, log activity relative trailing session/day reference và spot/perp activity ratio. Không gọi taker imbalance là net capital inflow: mọi trade có hai phía.

### G3 — Leverage/crowding

\[
\Delta\log OI_t=\log OI_t-\log OI_{t-1},\quad
B_t=F_t/S_t-1.
\]

OI quantity và notional khác nhau; notional phải xét tác động của price. Basis dùng synchronized spot/perp prices không future as-of. Funding estimate và realized funding event là hai features riêng. Không suy “new longs” chỉ từ OI tăng.

Dùng joint standardized features: return × OI-change, basis/funding deviation, spot activity confirmation. Interactions ít và preregistered; không tự sinh hàng nghìn polynomial features.

### G4 — Liquidity/absorption

Spread, documented depth bands, volume/range and impact proxies. Measurement source thay đổi là data-quality signal, không tự động là market regime. Fit trên source-consistent periods hoặc thêm explicit source cohort; missing snapshot không thành zero spread.

### G5 — Market coordination

Breadth của universe point-in-time, cross-sectional return dispersion, rolling correlation/common-factor concentration và BTC/ETH context. Local symbol residual return có thể được tính so market beta **fit trên past window**. Không train cross-symbol transform dùng observations future của một symbol để hỗ trợ symbol khác.

Primary model dùng một representation market chung và local residual/context. Tránh 3 market labels ×3 local labels ×3 stress labels thành27 ô ít dữ liệu.

### Scaling và group budget

Primary scale:

\[
z_{j,t}=\operatorname{clip}\left(\frac{x_{j,t}-m_{j,train}}{1.4826\,MAD_{j,train}+\epsilon_j},-c,c\right).
\]

`m/MAD/epsilon/clip` trong model artifact. Zero dispersion hoặc missing feature không âm thầm trở thành strong evidence; freeze drop/neutral policy trước inference. Group weighting ngăn nhóm nhiều features lấn át nhóm nhỏ. Fit scaler ở training window của từng nested split, không fit trên full history rồi chỉ infer forward [S15].

Khởi đầu tối đa khoảng 8–12 active features từ các blocks đủ dữ liệu; đây là complexity budget, không yêu cầu loại data inventory. Alternative feature sets được đăng ký như hypotheses và tính vào multiple testing.

## 6.5 External free data — optional enrichment, không thành scope creep

| Nguồn | Ý nghĩa đúng | Rule sử dụng |
|---|---|---|
| DefiLlama public stablecoin history [S11] | Supply/composition/liquidity context chậm | Endpoint availability và revisions được snapshot; không gọi raw TVL tăng là inflow |
| Whale Alert historical social-alert archive [S12] | Published large-transfer alerts | Dùng publication timestamp, deduplicate event IDs, coverage masks; không gọi toàn bộ whales/netflow |
| Farside BTC ETF flows [S13] | Daily ETF flow table trên giai đoạn có dữ liệu | Availability/publication lag; không điền0 trước khi sản phẩm tồn tại |
| Coin Metrics Community [S14] | Một số network/market metrics | Kiểm coverage và NC/commercial terms; không tự dùng cho production fund |

Không mua data trong lab này. Paid extension chỉ là roadmap khi một information gap đã được chứng minh. Không cần Polygon/Massive nếu nó chỉ trùng candles đang có; on-chain wallet attribution là product khác market-data API.

License/provenance đi theo artifacts. Evidence công bố có thể chỉ chia sẻ transforms/config/summary khi raw-data redistribution không được phép.

---

# 7. Robust parameter selection: search khác validation

## 7.1 Definition và geometry

Robust trong lab = **economic quality đủ tốt + local parameter stability + evidence qua relevant periods**. Không chọn vùng phẳng nhưng âm; không yêu cầu mọi specialist thắng ở mọi state nếu policy sử dụng nó được evaluate riêng.

Không đo robustness chỉ bằng top TPE trial density. TPE dùng kết quả đã thấy để chọn điểm tiếp; independent probe design cần tách khỏi search [S10]. Source actual selector được map ở LAB-04; generic optimizer và WFO mode có thể dùng selectors khác nhau.

Khoảng cách Gower-like đề xuất trên active schema:

\[
d(\theta,\phi)=\frac{\sum_{j\in A(\theta,\phi)} w_j d_j(\theta_j,\phi_j)}{\sum_{j\in A(\theta,\phi)}w_j}.
\]

Numeric/log/int metrics theo declared bounds/steps, không theo sampled span. Categorical equality/dissimilarity explicit; fixed keys không vào denominator. Conditional branch mismatch có penalty đã khóa; inactive keys không tạo khoảng cách giả. Dependent constraints parameterize trực tiếp thay vì repair/sort sau sampling.

## 7.2 Candidate discovery → independent local probes

Tại mỗi allowed cutoff:

1. Lấy anchors từ TPE IS search, incumbent và một phần space-filling coverage trong ngân sách.
2. Tạo local probes quanh từng anchor theo schema/radius đã freeze bằng development.
3. Evaluate **mọi probe hợp lệ**, cả lỗ hoặc violated risk; structural invalid giữ lý do riêng; runtime errors không đổi thành financial losses.
4. Chấm center và local panel theo các contiguous inner episodes.
5. Chọn representative đã thật sự evaluate; centroid mới phải chạy trước khi chọn.
6. Incumbent chịu cùng probe design/budget/constraints; không dùng primary-only floor tự đảo robust decision mà không disclosure.
7. Freeze selection trước outer evaluation/activation.

Pilot budget đề xuất: 64 discovery evaluations +4 anchors ×8 unique probes=96 candidate evaluations/cutoff, chưa tính episode visits. Incumbent phải nằm trong4 anchors khi có. Budget này để thử harness; production discovery có thể tăng sau coverage review. Khi so matched-budget, legacy cũng được tổng96 evaluations chứ không chỉ64. Báo **unique execution count và candidate-episode-bar visits**, không chỉ Optuna trial count.

Không khóa probe radius dựa preset full-sample. Một radius lớn và nhỏ có thể là sensitivity đã đăng ký, không lấy radius đẹp nhất sau outer OOS.

## 7.3 Một robust score minh bạch để triển khai trước

Với net utility của parameter `theta` ở inner episode `e` là `U(theta,e)`:

\[
G(\theta)=Q_{0.25,e}\{U(\theta,e)\},
\]
\[
F(\theta)=\operatorname{median}_{e}Q_{0.75,u\in N(\theta)}\left[\max(0,U(\theta,e)-U(u,e))\right],
\]
\[
R(\theta)=G(\theta)-\lambda_FF(\theta),\quad
P_{survive}(\theta)=\frac{\#\{(u,e):quality/risk\ gates\ pass\}}{\#\{(u,e):valid\ economic\ evaluation\}}.
\]

Không gộp episodes dài/ngắn tùy ý: inner blocks của score cần cùng horizon hoặc utility/time convention. Runtime failures làm panel incomplete và ngăn claim stability. Threshold `P_survive` và utility coefficients là selection hyperparameters chọn trên development; không universal constants.

Utility prototype: net return per fixed risk allocation trừ drawdown penalty đã định. Fee/funding/slippage đã trong net return; turnover penalty nếu có là preference/capacity penalty thêm, không tính cùng chi phí hai lần. Sharpe và tail diagnostics được trả riêng. Không trung bình Sharpe regime như portfolio Sharpe.

Medoid có thể chọn trong **tập candidate đạt quality/stability**:

\[
\theta_{medoid}=\arg\min_{\theta_i\in C}\sum_{\theta_j\in C}d(\theta_i,\theta_j).
\]

Điểm gần centroid chỉ tương đương với một số objective bình phương cụ thể, không tên gọi chung cho mọi medoid. Medoid không thay thế `R` hoặc local probes. Tie-break deterministic theo stable candidate ID. Khi thiếu evidence, giữ incumbent/fallback và ghi `INSUFFICIENT_LOCAL_EVIDENCE`, không fabricate plateau.

## 7.4 Candidate bank cho regime policy

Bank gồm tối đa khoảng 3–8 configurations có behavior khác nhau và đủ local evidence; dùng 16/64 candidates không tự tốt hơn nếu episodes ít. Đây là budget khởi đầu để inner validation chọn nhỏ nhất đủ useful.

Không loại mọi specialist chỉ vì pooled mean thấp hơn global nếu nó có conditional evidence đủ support. Nhưng family nào được thêm vào bank cũng phải được chọn bằng history hợp lệ, chịu cost/risk constraints và được tính vào search trials. Bank tại thời điểmT không có candidates được phát hiện bằng observations sau T.

Candidate bank version có entry/retire dates, strategy adapter hash, parameter digest, validation panel, status, feature warmup readiness và reason. Inactive/hardcoded params không tạo thêm “đa dạng”.

---

# 8. Regime model: persistent states + transparent online decision

## 8.1 Model ladder có giới hạn

| ID | Model | Vai trò |
|---|---|---|
| M0 | Rule-based volatility/path-direction/activity | Control dễ giải thích, threshold train-only |
| M1 | Regularized discrete statistical jump model | Primary state model |
| M1S | Sparse JM hoặc group-regularized features | Extension khi nhiều blocks, ablation so M1 |
| M2 | HMM hoặc GMM nhỏ | Comparator; không quét mọi model family |
| M3 | Online novelty/change detector | Diagnostic/secondary trigger, chưa ghép default |

Primary starting `K=3`; không cố ép names bull/neutral/bear nếu centroids không hỗ trợ. `K=2` là parsimonious alternative; `K=4` chỉ mở khi development cho thấy split có decision value, không vì chart đẹp. States mô tả **feature structure**, không được đặt tên theo outer PnL.

Nguồn SJM crypto và JM online là nền tham khảo, không bằng chứng time edge cho bốn alpha này [S8–S9].

## 8.2 Objective discrete JM

Với standardized features `z_t`, centroids `mu_k` và state path `s_t`:

\[
\min_{\mu,s}\sum_{t=1}^{T}\ell(z_t,\mu_{s_t})+\lambda_J\sum_{t=2}^{T}\mathbb 1[s_t\ne s_{t-1}],
\]
\[
\ell(z_t,\mu_k)=\frac12\sum_g\frac{\omega_g}{d_g}\sum_{j\in g}a_j(z_{jt}-\mu_{jk})^2.
\]

Primary `a_j` fixed nonnegative, group weights sum 1; `d_g` là số active features trong group. Như vậy thêm nhiều features vào một block không tự tăng toàn weight của block. Missing-pattern handling versioned; primary dùng stable complete-core schema và explicit degraded/fallback, không cluster source-missingness làm market state.

Fit bằng alternating centroid update và DP segmentation trên train, multi-start seeds có giới hạn; lưu mọi fit diagnostics, không chọn random seed theo outer profit. Objective decrease/convergence/finiteness/empty-cluster handling cần tests. Không khẳng định alternating local minimum là global optimum.

`lambda_J` có units theo standardized loss và sampling frequency. Khi đổi từ 4h sang 1h phải retune trong train/validation hoặc freeze normalized policy mới; không dùng cùng raw penalty rồi so “model tốt hơn”.

## 8.3 Sparse extension không được có nghiệm weights=0 vô nghĩa

Không tự viết objective `min sum_j w_j*SSE_j` với `w>=0` rồi cho tất cả w=0. Dùng implementation nghiên cứu đã pin hoặc objective constrained được kiểm chứng.

Một cách mô tả sparse update là tối đa hóa weighted between-state dispersion với `w_j>=0`, `||w||_2<=1`, `||w||_1<=s`, kết hợp segmentation theo weighted loss/jump penalty. Đây là mô tả một update family, không khẳng định mọi SparseJumpModel library dùng đúng objective hoàn chỉnh đó. Agent phải đối chiếu paper và pinned source, lưu weight normalization/penalty conventions [S8–S9].

Regularization, feature ranking và K được chọn trong nested development, không bằng holdout. Group ablation cần chứng minh leverage/flow/market features có contribution ngoài price/volatility. Chỉ complexity trong model state thay đổi; alpha execution giữ nguyên.

## 8.4 Online inference causal

Với centroids/weights/model version đã sẵn sàng:

\[
Q_t(k)=\ell(z_t,\mu_k)+\min_j\{Q_{t-1}(j)+\lambda_J\mathbb 1[j\ne k]\}.
\]

Phát `state_t=argmin_k Q_t(k)` tại observation hiện tại. Có thể trừ `min_k Q_t(k)` sau update để giữ numeric scale, không đổi argmin hoặc relative costs. Tie-break fixed. `Q_t` là chi phí của best historical prefix kết thúc ở mỗi state, không phải ledger chi phí của chuỗi labels đã phát ra. Jump penalty của model không thay switching cost thực của policy; count transitions theo immutable emitted-state tape riêng.

**Không backtrack sau khi có future observations để overwrite labels đã dùng giao dịch.** Offline best full path chỉ là diagnostic với `decision_eligible=false`. Endpoint-state filtering này phải so brute-force trên toy sequences và prefix/batch-stream parity.

Khi refit model ởT, có thể forward-filter phần calibration history `<=T` để warm state cho quyết định sắp tới. Các labels tạo bởi model mới cho quá khứ là `asof_T_training_labels`, không ghi đè decision-vintage labels lúc chúng xảy ra. Model A/B state IDs được namespaced, mapping centroids chỉ theo train information. Mapping không tin cậy → uncertainty/model-transition event, không automatic market refit trigger.

## 8.5 Output và uncertainty

Bản discrete JM trả:

```text
state_id / state_namespace
state_costs / second_best_gap
fit_residual / novelty_score
feature_contributions / group_contributions
observed_at / available_at / inferred_at
model_fit_cutoff / ready_at / version
quality_status / input_refs
```

`softmax(-cost)` chỉ là membership score nếu chưa calibration; không gọi 90% membership là 90% thị trường thật sự bull. HMM comparator được trả filtered probability nhưng vẫn conditional on model assumptions. `UNKNOWN_STATE`, `MISSING_DATA`, `STALE_MODEL`, `UNMAPPED_REFIT_STATE` là các trạng thái khác nhau.

Stress/crowding score là trục riêng, không phải bear label và không bắt tạo9 joint labels. Context có thể mô tả một positive trend nhưng crowded/liquidity mỏng.

## 8.6 Training và model selection cadence

Starting operational hypotheses cho lab:

| Clock | Primary proposal | Comparator/sensitivity |
|---|---|---|
| Alpha decision | A-HMA1h; A-HASH/A-VWAP/A-SC15m | Secondary timeframes đăng ký trước, không chọn theo preset comment |
| Regime observation | 4h UTC, complete bucket | 1h alternative chỉ ở discovery |
| Regime model fit | Mỗi 28 ngày, chỉ available history | 56 ngày alternative, không fit mỗi state switch |
| Model train memory | Trailing 365 ngày sau đủ data; minimum 180 ngày cho pilot được gắn flag | 730 ngày nếu coverage và budget đủ; không universal optimum |
| Bank search refresh | Lịch calendar của baseline được freeze | Triggered refresh là separate variant |
| Switch assessment | Mỗi eligible regime observation | Actual activation còn phụ thuộc fill/campaign state |

Những con số này là starting hypotheses, không kết luận best cadence. Cadence cuối được freeze sau discovery; không tune outer outcomes. Model retraining, bank refresh và switch frequency phải ghi thành ba counters riêng.

---

# 9. Parameter-response model và time-edge policy

## 9.1 Đây là lớp nối regime với quyết định

Model trạng thái không tự biết bộ params nào kiếm tiền tốt hơn. Cần bảng episodes/candidates có:

```text
episode_start/decision_time
context_asof_decision
candidate_id/parameter_version
subsequent outcome interval
outcome_available_at
net return/risk/cost/campaign stats
initial state contract
```

Với horizonH, episode outcome chỉ được dùng tại T khi `end + publication/processing delay <= T`. Overlapping outcomes cần purge/blocked inference. Không tạo labels response từ future PnL rồi đưa vào regime fit tại episode_start.

Training có thể backtest một candidate mới phát hiện tại T trên history `<T`; đó là retrospective training analysis của quyết địnhT. Nhưng inner pseudo-live validation tại T' không được dùng bank được discovered sau T'. Candidate creation time phải được replay trong nested experiment.

## 9.2 Historical similarity và shrinkage

Với context `x_t` và historical episode contexts `x_e`:

\[
w_{te}=\exp\{-d(x_t,x_e)^2/(2h^2)\}\exp\{-(t-e)/\tau\}\,q_e,
\]

trong đó `q_e` là data/evaluation quality eligibility, không là trọng số tăng vì outcome đẹp. Các contexts đều từ admissible vintage. `h`, recency `tau`, feature weights chọn inner-only. Không collapse mọi episode cùng label thành interchangeable khi context khác xa.

\[
\widehat\Delta U_t(\theta)=\frac{\sum_e w_{te}[U_e(\theta)-U_e(\theta_{inc})]}{\sum_e w_{te}},
\quad N_{eff}=\frac{(\sum_e w_{te})^2}{\sum_e w_{te}^2}.
\]

`N_eff` chỉ phản ánh weight concentration, không số observations độc lập; thêm count contiguous episodes, autocorrelation/block diagnostics và contribution của từng episode.

Shrink relative estimate:

\[
\widetilde\Delta U_t=a_t\widehat\Delta U_{local}+(1-a_t)\widehat\Delta U_{pooled},\qquad
 a_t=\frac{N_{eff}}{N_{eff}+\kappa}.
\]

Đây là policy estimator đề xuất, không bảo đảm calibrated posterior. Với insufficient episodes, trả status và giữ incumbent; không dùng hàng nghìn overlapped bars để làm SE nhỏ giả.

## 9.3 Utility và transition cost cùng đơn vị

Episode primary utility có thể là net return trên fixed allocation, trừ drawdown/risk penalties đã đăng ký. Relative SE ước lượng từ paired contiguous blocks/episodes, không iid bars. Transition cost tính theo projected turnover, fees, slippage và residual handling; đơn vị quy về cùng return/allocation horizon.

Switch challenger chỉ nếu:

\[
\widetilde\Delta U_t(\theta^*)-z_\alpha SE_t > C_{transition,t}(\theta_{inc}\rightarrow\theta^*)+\delta
\]

và quality/support/capacity gates pass. Đây là conservative decision heuristic, không confidence guarantee nếu model assumptions sai. Không dùng một arbitrary Gaussian95% nhãn khi evidence chỉ vài episodes. Trong main proof, net switching gain phải đo bằng actual continuous simulation.

Giữ một **inaction region**. `KEEP_INCUMBENT`, `SWITCH_READY`, `WAIT_CAMPAIGN_BOUNDARY`, `REFRESH_BANK_REQUESTED`, `FALLBACK_DATA`, `FALLBACK_NOVEL_STATE`, `NO_SUPPORTED_CANDIDATE` là các decisions phân biệt.

`C_transition` estimate không được double-charge vào actual PnL: selector dùng để quyết định; engine chỉ charge actual fills/fees. Repricing/cancel costs nếu engine không support phải có documented model cùng mọi variants.

## 9.4 Bốn clocks không gộp

1. **Inference:** state update với feature observation đã available.
2. **Switch:** chọn giữa candidates đã có, không cần Optuna chạy lại.
3. **Bank refresh:** tìm/validate candidates mới khi stale/bank-inadequate hoặc theo lịch.
4. **Model retrain:** centroids/features không còn phù hợp hoặc đến lịch maintenance.

Một market state transition quen thuộc không làm model hỏng. Retrain detector chỉ từ covariate fit/novelty monitor; muốn dùng strategy performance làm drift trigger là policy khác, phải evaluate riêng và không gọi là market-only model.

Refit job giữ cutoff cố định ở trigger. Nếu job lâu hoặc trigger mới xuất hiện, coalesce/cancel/supersede theo deterministic policy; không để result của job cũ dùng future inputs chưa declared. Trong lúc chờ, incumbent hoạt động. `effective_at >= ready_at` và contract boundary; không retroactive activation.

## 9.5 Campaign and bank migration

Primary policy cho A-HASH/A-VWAP/A-HMA:

- Entry campaign gắn `entry_parameter_digest` bất biến.
- Khi external regime đổi, existing trade bảo vệ theo params đã vào; pending future-entry policy có thể thay.
- Đợi flat/terminal campaign rồi activate decision mới cho entry tiếp theo; ghi requested decision time và actual activation delay.
- New candidate indicators phải đã warm causal. Precompute bank feature streams theo past-only state hoặc warm từ history khi activated; không reset EMA/HMA mỗi switch và không carry một adaptive-length state của paramsA sangB thiếu contract.
- Nếu campaign không đóng trong thời gian dài, báo stale/transition-blocked; không ép close để tạo time edge. Forced unwind là một riêng ablation có costs.

A-SC long-flat có thể rất lâu chưa flat. Primary giữ position until normal exit; candidate signal generators có shadow indicator state nhưng không giữ financial account bóng. Optional next-open target-switch là policy khác, không trộn.

Retired bank params vẫn phải tồn tại để quản lý campaign cũ đến terminal. Không delete parameter version khi còn order references.

---

# 10. Thiết kế chứng minh: selector, timing và bank không bị nhập nhằng

## 10.1 Trục so sánh A/B/C/D

| Arm | Selector | Refit schedule | Mục đích |
|---|---|---|---|
| A | Current installed WFO selector, causal deployment | Calendar hiện tại được freeze | Baseline chính |
| B | Independent-neighborhood selector | Cùng calendar | Contribution của robustness |
| C | Current selector | Regime-triggered full refresh, training memory giữ nhưA | Contribution của timing |
| D | New neighborhood selector | Regime-triggered full refresh | Interaction selector × timing |
| E | New selector + bank + response policy | Model fit chậm; bank refresh nhưB; switching theo regime | Tách intelligent switching khỏi refit nhiều |

A/B/C/D là core factorial; E là extension có định nghĩa khác, không dùng E thay C/D mà không nói. So `B-A`, `C-A`, `D-B`, `D-C` và interaction `(D-C)-(B-A)` trên same-calendar continuous paths. E phải so B và matched-bank controls để biết lợi ích đến từ switching.

Nếu current WFO mode dùng OOS cho candidate selection, giữ nguyên một arm `A_legacy_selection_adjusted` để reproduce; baseline primary phải dùng causal schedule/mode đáp ứng claim. Không sửa semantics âm thầm rồi vẫn gọi “y hệt WFO hiện tại”. Capture route, mode, search_scope, candidate_freeze, selected_params_freeze và data_used_for_selection.

## 10.2 Controls bắt buộc

- `RISK_ONLY`: cùng regime context nhưng chỉ risk scaling, params không đổi.
- `CALENDAR_MATCHED`: calendar cadence/search compute tương đương dynamic policy, chọn bằng development.
- `BANK_CALENDAR`: cùng bank size/candidate identities trong những decision scopes cho phép, switching theo calendar, không regime information.
- `STATE_PLACEBO`: giả labels/scores có approximate dwell/frequency cấu trúc được sinh từ development/known past; không shuffle future labels vào decision tape.
- `DELAYED_STATE`: thêm one-observation hoặc operational delays đã đăng ký; đọc transition sensitivity.
- `EXPOST_DIAGNOSTIC`: labels/full-path hindsight chỉ diagnostics, không eligible trade result.
- `USER_PRESET_REFERENCE`: provided full-sample params trên canonical engine, label retrospective, không core outcome.

Controls triển khai theo staged design, không chạy mọi Cartesian combo ngay. Không bỏ một control vì nó thắng phương pháp đề xuất.

## 10.3 Cùng economic engine và account path

Mỗi arm có account riêng cùng initial conditions; bên trong arm là continuous account theo chronology. Không cộng best segment returns từ nhiều independent runs, không reset tiền tại regime/fold change. Candidate training evaluations có reset/initial-state contract riêng, không đồng nhất với deployment account.

So báo cáo daily UTC trên cùng evaluation interval. Dynamic folds chỉ là operational decision segments; độ dài khác nhau nên không trung bình fold Sharpes không trọng số để xếp hạng.

Phí/slippage/funding và gross exposure constraints giống nhau. Risk-matched analysis dùng sizing calibration trên train hoặc causal rolling estimator, không scale bằng full OOS volatility rồi gọi tradable.

## 10.4 Twenty primary cells và lịch chạy

Primary matrix:4 alpha ×5 symbols =20 cells. Đề xuất timeframes trước khi xem results:

| Alpha | Primary decision bars | Execution bars | Secondary, nếu preregistered |
|---|---|---|---|
| A-SC | 15m | 1m next eligible open | 1h |
| A-VWAP | 15m | 1m protection/next open | 5m |
| A-HMA | 1h | 1m protection/next open | 15m |
| A-HASH | 15m | 1m ladder/protection | 1h |

Các choices này là pilot protocol, không dữ liệu chứng minh best timeframe. Source comments about ETH5m/BTC1h không được dùng để âm thầm chọn primary winning cells. Nếu user muốn exact historic setup, tách reproduction cohort kèm original timeframe chưa được cung cấp/không rõ.

Pilot thứ tự: A-SC → A-HMA → A-VWAP → A-HASH, để đóng signal routing rồi protective lifecycle rồi partial exits. Vẫn phải báo đủ20 cell statuses; không loại alpha khó hoặc ít giao dịch khỏi denominator của kết luận tổng.

Mỗi symbol evaluation start = max(data coverage, listing, model/alpha warmup, global preregistered earliest). Báo common-period five-symbol aggregate riêng với per-symbol longest valid history. Không điền returns0 trước listing.

## 10.5 Compute budgets và baselines

Hai báo cáo song song:

1. `MATCHED_TOTAL_COMPUTE`: unique strategy-evaluation/fold-bar visits, probes, model fits và response evaluations nằm cùng budget.
2. `OPERATIONAL_POLICY`: ngân sách mỗi lần refit tương đương, report total compute/network/latency thực có.

Không giảm time interval, phí, output hoặc số thử của baseline để phương pháp mới đẹp hơn. TPE seed/sampler version/storage scheduling pin; adaptive batch và sequential có semantics khác [S10]. Primary comparison theo deterministic sequential schedule hoặc fixed candidate matrix đủ để reproduce.

Model-search trials, state-count choices, jump penalties, response bandwidth, switching thresholds và alpha revisions đều thuộc experiment-search ledger. Không chỉ log Optuna alpha trials.

---

# 11. Phương pháp kết luận và publishing evidence

## 11.1 Hai giai đoạn thông tin

**Discovery:** sửa adapters, thử hypotheses/features/model K/penalty/cadence bằng development và inner chronological validation. Lưu toàn search history.

**Confirmation:** freeze code/config/data role và primary contrasts rồi chạy interval chưa dùng để chỉnh thiết kế nếu có. Nếu toàn history đã được dùng trong tuning source alpha, không gọi nó independent holdout; làm nested retrospective research và đăng ký prospective observation sau freeze. Không hứa tự chạy nền hoặc live deployment.

Tại mỗi outer pseudo-live cutoff, model/scaler/selector/bank chỉ dùng history available. Inner validation phải refit lại preprocessing/model/candidates tại inner cutoffs; không fit một model outer-train-full rồi đem đánh early inner periods như live.

## 11.2 Primary outcome và không ép “tốt hơn mọi mặt”

Đăng ký một primary utility trước data results. Prototype: mean daily net-return difference trên same risk budget, với drawdown/tail/noninferiority constraints. Daily Sharpe, total return, max drawdown, expected shortfall, exposure, turnover, costs và trade/campaign counts là secondary/guardrail.

Nêu rõ mức improvement tối thiểu có ý nghĩa kinh tế bằng expected execution-cost uncertainty/budget, không tự chọn threshold sau observed delta. Không dùng win-rate tăng làm bằng chứng toàn policy tốt hơn.

Các cấp conclusion:

```text
DESCRIPTIVE_VALUE
CONDITIONAL_RESPONSE_EVIDENCE
NET_PARAMETER_SELECTION_EDGE
NET_TIMING_EDGE
NET_POLICY_EDGE
NO_INCREMENTAL_VALUE
INCONCLUSIVE_SAMPLE
FAILED_VALIDITY
```

Risk-only improvement không được ghi thành parameter-selection edge. Chọn đúng ex-post expert nhưng tất cả experts lỗ không phải tradable edge. Regime chart đẹp không đủ cả descriptive claim nếu labels chỉ phản ánh missing/source changes.

## 11.3 Paired uncertainty và multiple comparisons

Dùng daily paired differences giữa arms trên cùng dates. Block bootstrap giữ thời gian và correlation giữa các symbols/arms; không resample mỗi asset độc lập khi đang kết luận market-wide. Block lengths chọn development và có sensitivity; không giả iid 1m returns. Với ít episodes, report interval rộng/insufficient evidence, không tăng nominal N bằng overlapped horizons.

Holm-type adjustment hoặc family-level bootstrap/max-stat theo protocol đã chọn cho primary contrast family; giữ tất cả20 cells và alpha/timeframe variants đã thử. DSR/PBO nếu thêm chỉ supplementary, không chữa leakage hoặc thay chronological validation.

Không average Sharpes để tạo một portfolio giả. Equal-weight portfolio aggregation chỉ khi có explicit capital allocation và actual account simulator; otherwise report paired panel/macro-average như descriptive statistic có tên đúng.

## 11.4 Transition-specific diagnostics

Lưu evidence quanh detected transitions, không quanh retrospective true starts chỉ biết future. Metrics: detection/activation delay, actual transition turnover/cost, wrong-switch loss, avoided/refused switches, stale incumbent duration, unknown/fallback usage, param rank stability và conditional gain concentration theo episodes.

Nếu model chỉ có lợi trong một crash/one symbol, kết luận giới hạn ở đó. Không giấu thời kỳ thua hoặc state không có đủ observations.

## 11.5 Data/report artifacts

Metadata và decisions dùng strict JSON (`allow_nan=False`), streaming events JSONL; numeric panels Parquet/Arrow nếu dependency hiện có. NaN/Inf có status + null, không invalid JSON. Mỗi schema có version, IDs, parent artifacts, byte sizes/hash, row counts và closed/partial state.

Hash không thay raw ledger. Reconstructed audit ghi khác `original_retained`. RUN_SUCCESS chỉ sau required artifacts committed/flush; writer queue full phải backpressure hoặc explicit failure, không drop.

---

# 12. Roadmap chính thức — đúng 10 phase

IDs dưới đây thuộc **lab nghiên cứu**, không trùng phase78, PERF, NEXT hoặc RP của QuantBT. Không renumber hay reopen những phase production đã hoàn thành.

| Phase | Tên | Đầu ra quyết định |
|---|---|---|
| LAB-01 | Isolated workspace, pinned baseline và preregistration | Có thể chạy lab mà không ghi nguồn chính; đủ identities |
| LAB-02 | Four-alpha canonical adaptation và domain certification | Bốn adapter hoặc explicit blocker, semantic changes được biết |
| LAB-03 | Server-first data snapshots và causal feature panels | Những dữ liệu được phép biết tại từng thời điểm |
| LAB-04 | Calendar baseline và independent-neighborhood selector | Tách contribution của selector khỏi regime |
| LAB-05 | Persistent regime models và online inference | States/vintages causal, minh bạch và reproduce được |
| LAB-06 | Parameter-response model, bank và four-clock policy | Từ market information sang quyết định có uncertainty |
| LAB-07 | Continuous regime-aware WFO integration | Không reset account, không retroactive refit/activation |
| LAB-08 | Controlled discovery trên bốn alpha × năm symbols | A/B/C/D/E, controls, budgets và actual contribution |
| LAB-09 | Frozen confirmation, stress và falsification | Kết luận dương/âm/inconclusive đúng mức evidence |
| LAB-10 | Reports/JSON/charts, reproducibility và handoff | Evidence đọc được, tái hiện được; production không bị thay đổi |

Dependency:

```text
LAB-01
  ├── LAB-02 (synthetic adaptation/specification)
  └── LAB-03 (read-only data snapshots)
LAB-02 + LAB-03 → market adapter qualification → LAB-04
LAB-03 → LAB-05
LAB-04 + LAB-05 → LAB-06 → LAB-07
LAB-04 + LAB-07 → LAB-08 → LAB-09 → LAB-10
```

Agent có thể làm data inventory và synthetic adapters song song trong cùng budget. Không chạy optimization thật trước khi adapter validity pass. Reporting schema/scaffold tạo sớm ở LAB-01, không chờ LAB-10 mới bắt đầu lưu evidence.

---

## LAB-01 — Isolated workspace, pinned baseline và preregistration

### Mục tiêu

Tạo lab duy nhất, enforce read-only boundaries, xác nhận package baseline và đăng ký thí nghiệm trước khi nhìn performance.

### Tasks

**L01.1 — Resolve allowed paths.** Tìm paths người dùng đã cung cấp/configured bằng read-only metadata; không scan toàn alpha storage. Canonicalize realpaths, kiểm LAB_ROOT không nằm trong hoặc bao trùm source/storage/alpha protected roots. LAB_ROOT phải chưa tồn tại hoặc có marker cùng study; không reuse một directory bất kỳ.

**L01.2 — Snapshot nguồn.** Copy đúng archive4alpha, verify SHA; inventory ZIP trước extraction, reject absolute/traversal/duplicate entries/symlink/oversize. Export QuantBT snapshot từ approved commit hoặc cài wheel1.1.1 trong isolated environment; giữ cả source mapping lẫn actual artifact hashes. Không dùng newest main một cách im lặng. Nếu source/server đang dirty, ghi boundary và chọn clean snapshot; không tự sửa/clean repo gốc.

**L01.3 — Environment isolation.** Core/native pair pin, dependency lock, `ta` cho A-SC chỉ trong lab, Numba compiler flags, Python OS/thread metadata. Baseline và candidate processes riêng. Wheel/source imports và native capability được probe; không chạy original arbitrary module trước containment. Development editable chỉ trong lab; official experiment dùng packaged candidate hoặc recorded source identity nhất quán.

**L01.4 — Evidence schema và write guard.** Tạo strict JSON writer atomic-to-lab, append-only attempt ledger, null/status cho missing metrics; mọi artifact có `lab_run_id`. Đặt budgets/cancellation own process group. Verify sources unchanged trước/sau bằng manifests phù hợp; data partitions mutable ngoài lab phải snapshot/read-lock theo policy, không chạy collector.

**L01.5 — Preregister claims và contamination.** Tạo hypothesis registry, 20-cell matrix, baselines/variant IDs, primary timeframes, cost/risk setup, compute budgets, freeze/holdout policy. Presets full-sample đi vào quarantined reference catalog; không warm-start primary.

**L01.6 — Actual API map.** Agent đọc installed `QuantBTEndpoint` signatures, WFO config/modes, command classes, callbacks, parent/OCO, result exports và tests. Lập `api_binding_map.json`: lab operation → actual symbol/version/capability/test. Unknown không điền bằng API tưởng tượng. Map loader trong snapshot bằng inspect/staticread; không import source production với caching side effects.

### Files đích đề xuất

`safety/paths.py`, `safety/process.py`, `scripts/bootstrap_lab.py`, `scripts/preflight.py`, `evidence/manifest.py`, `configs/study_registration.json`, `quantbt_bridge/capabilities.py`.

### Tests/gate

Write ngoài lab bị OS từ chối; ZIP traversal/symlink bị reject; actual version/import origin đúng; no live credentials/network during replay; input hashes giống upload. Giữ một test cố tình ghi protected path **trên fake protected fixture**, không thử ghi vào repo production để kiểm sandbox.

**Exit:** `SAFE_TO_RUN_SYNTHETIC=true`, API/data unknowns liệt kê; market execution còn disabled. Nếu sandbox không enforce được, chỉ scaffold/read-only review, status không được fake PASS.

---

## LAB-02 — Four-alpha canonical adaptation và domain certification

### Mục tiêu

Bỏ quyền financial simulation khỏi alpha legacy, giữ thesis, version hóa mọi sửa và chuẩn hóa timing trước methodology comparison.

### Tasks

**L02.1 — Catalog alpha/presets.** AST inventory input names, parameter reads, unused knobs và presets; chạy probes Phụ lục B. Generate source-line findings và semantic deltas theo Section3. Không import unrelated preset logic hoặc alpha khác.

**L02.2 — Reference drivers.** Viết scalar Python reference cho signal/indicator decisions đã chọn; legacy exact formula riêng. Thư viện ta/Numba phải có numeric parity/tolerance contract; không tự sửa Wilder/EMA/padding conventions. `fastmath=False` cho oracle, native/Numba optimization chưa bật nếu làm đổi decisions.

**L02.3 — A-SC adapter.** Resolve volume fallback; giữ long-flat, original crossover, amplitude mapping versioned. Thực hiện intent-after-close và next-open fill. Test input không bị in-place mutate và all no-signal path; preserve bars-since state.

**L02.4 — A-HMA adapter.** Actual entry fills, resting SL/TP, technical exit next-open, fixed entry params, instrument tick, RSI-flat repair. Trả feature/decision diagnostics thay vì handcrafted fills. Phân biệt weight pre-bar và target post-close để không lag/double count.

**L02.5 — A-VWAP adapter.** UTC daily reset, closed HTF EMA, true warmup readiness, original entry logic, explicit time-stop event và lagged dynamic VWAP nếu bật. Khóa SL/TP/time precedence; khi cần hooks mới chỉ sửa lab candidate engine adapter.

**L02.6 — A-HASH adapter.** Fix import/short-input, tách account config, ATR-convention variants, ordered ladder, actual-fill-dependent partial qty/cooldown. Engine owns equity; legacy realized-only equity được giữ diagnostic không dùng scoring.

**L02.7 — Common execution fixtures.** Long/short entry, actual gap, both stop/TP hit, partials/OCO/over-close, rejected order, insufficient margin, funding boundary, final open position. Adapter không được tự set position khi order chỉ submitted nhưng chưa filled. End-of-tape mark/open exposure và forced-flat là hai modes.

**L02.8 — Engine parity.** Fixed intents trên Python/Rust cùng supported contract so full event/account trace; original alpha và corrected adapter có thể khác do documented repairs. Không ép preserve known bugs cho parity. Giữ corrected alpha version chung A/B/C/D/E.

### Outputs

`alpha_registry.json`, `preset_catalog.json`, `unmapped_presets.json`, `semantic_delta.json`, four adapters, reference drivers, `alpha_certification/{alpha_id}.json`, golden fixture tapes và account traces.

### Exit

Mỗi alpha có `READY_FOR_RESEARCH` hoặc blocker cụ thể. Tối thiểu all4 phải có design/adapter và synthetic suite; alpha không ready không được tự thay bằng khác hoặc bị loại khỏi matrix. Market optimization chỉ chạy cells có qualification. Không có metric marketing từ legacy equity columns.

---

## LAB-03 — Server-first snapshots và causal feature panels

### Mục tiêu

Đóng exactly what was knowable, dùng thông tin sẵn có nhiều nhất mà không cần mua dữ liệu mới.

### Tasks

**L03.1 — Data product inventory.** Đọc code loader, endpoint docs thực và storage metadata; chỉ copy/load partitions thuộc five symbols và declared market universe. Đánh dấu products có/còn thiếu, không bịa dataset sẵn có dựa vào reader name.

**L03.2 — Primary snapshots.** Từ2020 cho spot như user chốt; perp/listing start thực. Freeze files/hash/time ranges và batch ingestion. Không sửa originals hoặc metadata của source. Volume fractional, UTC units và symbol mapping giữ exact.

**L03.3 — Availability builder.** Per product có event/available/ingested/vintage; 1m→15m/1h/4h resampling, `sample_time` cho snapshots, funding events riêng. Missing/stale status và TTL. Reads fail-closed theo primary quality policy, không warning-only rồi tiếp tục full-sample claim.

**L03.4 — Feature blocks.** G1–G5 theo Section6, fixed core schema, training-only scaler/group weights. Phân biệt market/local signals. Giữ intermediate raw aggregates để tính lại feature, không chỉ standardized arrays cuối.

**L03.5 — Data enrichment optional.** Inventory stablecoins/Whale Alert/ETF/network nếu thực sự có quyền và coverage; acquisition riêng write-to-lab only. Không có enriched data vẫn chạy server-core; không blocking.

**L03.6 — Eligibility and cohort reports.** Listing, warmup, market-universe membership, sources, revisions/masks, per-symbol usable intervals, common-period cohorts. Data features được build theo batch hoặc streamed phải prefix-equal.

**L03.7 — Market adapter qualification.** Dùng một bounded historical slice của mỗi alpha-symbol để kiểm gaps/HTF/warmup/account trace. Đây là domain/smoke, không model selection; giữ slice trong development role.

### Outputs

`snapshots/{id}/manifest.json`, `feature_schema.json`, `availability_rules.json`, feature panels, missing/coverage reports, `data_eligibility.md`.

### Exit

Có server-core cohort với explicit coverage và publication assumptions. Future mutation tests pass qua cả loader/resampler/scaler. Không cần external API để tiếp tục primary.

---

## LAB-04 — Calendar baseline và robust-neighborhood selection

### Mục tiêu

Kiểm baseline WFO actual, sửa đúng cách chọn profitable + stable mà chưa đưa regime vào decisions.

### Tasks

**L04.1 — Reproduce exact installed WFO.** Với fixed parameter matrix trước, trace current selected mode, optuna sampler, proxy/native objective, candidate freeze, OOS usage, baseline floor và retention. Distinguish mode1–5 thực của pinned version; không assume tất cả call generic selector.

**L04.2 — Selector counterexamples.** Sharp peak/broad plateau, bad neighbors, duplicate samples, fixed dimensions, sampled-span scaling, missing consensus, invalid centroid và raw baseline override. Gắn actual source symbols/reproducers; nếu already fixed thì ghi verified-existing.

**L04.3 — Candidate-independent probe engine.** Geometry từ schemas4alpha, dependent params ordered, inactive flags excluded; seed/design freeze. Mọi valid bad probe giữ trong denominator. Runtime error → incomplete evidence, structural invalid không tính như bad performance.

**L04.4 — Robust scoring and incumbent parity.** Score Section7, same episode lengths/risk/cost. Incumbent nhận cùng validation budget. Log before/after guard. Centroid/medoid rules chỉ operate trên feasible evaluated candidates có traceable panels.

**L04.5 — Baseline A và selector B.** Cùng calendar/training memory/engine/retention/eval budget, không dùng regime. Chạy pilot one-symbol/one-alpha rồi expand đủ20 cells theo budget; không chọn tiếp symbol thắng để claim toàn scope.

**L04.6 — Evidence before model selection.** Trả actual local coverage, lower-tail, survival, trade counts, period concentration và param-behavior fingerprint. Nếu B không cải thiện stable performance, vẫn giữ A/B cho factorial để không mặc định selector mới đúng.

### Files đích

`selector/schema_distance.py`, `selector/probe_design.py`, `selector/robust_score.py`, `selector/representative.py`, `experiments/calendar_baseline.py`.

### Exit

Biết selector nào public route thực dùng; có honest A/B kết quả và search budget. Legacy OOS-selected modes được label, không reuse như untouched claim.

---

## LAB-05 — Persistent regime model và causal emissions

### Mục tiêu

Một state provider có thể chạy streaming giống live, có states và feature contributions hiểu được, không cần PnL tốt để pass technical gate.

### Tasks

**L05.1 — Fit/infer contract.** Model artifact chứa training cutoffs, scaler, schema/weights/centroids, lambda, state namespace, seeds, library/code hashes và fit-ready timestamp. Method names library chỉ sử dụng sau pinned source verification; `.predict_online` không mặc định cùng thuật toán DP đề xuất.

**L05.2 — M0/M1 references.** Rule baseline và discrete-JM reference; forward recurrence có brute-force oracle trên small arrays. Batch-prefix results phải giống sequential emissions; no retroactive labels. Greedy online và endpoint-DP nếu đều thử là hai model versions, không mix.

**L05.3 — Fit robustness.** Bounded multi-start, convergence report, empty states, outliers, source transition, constant features. Model seeds chọn theo train fit/inner criterion, không theo outer PnL.

**L05.4 — K/regularization.** StartingK3; K2 alternate; K4 chỉ có explicit discovery decision. Sparse feature/group extension cần nondegenerate constraints. Không optimize K bằng việc nhìn colored regime chart trên holdout.

**L05.5 — Refit and namespace mapping.** Fit model cadence chậm, infer4h; map versions bằng training centroids/economic descriptors. State model transition không auto tạo parameter-search trigger. Old decision emissions immutable.

**L05.6 — Novelty/quality.** Ambiguity score, out-of-support/fit residual, missing/stale data; fallback semantic. Stress/crowding overlay riêng; không output fake calibrated confidence.

**L05.7 — Synthetic worlds/negative controls.** No-regime world, recurring state world và structural-break world; test detection delay và noise sensitivity. Ground-truth latent label chỉ dùng diagnostic, không đưa vào policy input.

### Outputs

`regime_model_registry.json`, serialized model arrays + metadata, online emission tape, training loss/weight/centroid reports, fit-vs-infer tests, state-transition diagnostics.

### Exit

Causal provider technical pass và reproducible state vocabulary. Không claim predictive/financial value từ fit loss, silhouette hoặc visually clean labels.

---

## LAB-06 — Conditional parameter response và bốn clocks

### Mục tiêu

Chứng minh nối state/context với expected **relative** utility của params, rồi định nghĩa keep/switch/refresh có thể thực hiện thật.

### Tasks

**L06.1 — Outcome episode builder.** Chọn horizon theo strategy/holding diagnostics ở development, starting7calendar-days cho pilot hoặc một horizon registered khác. Outcome đầy đủ mới được dùng; mark open positions theo same account contract, không chỉ closed wins. Nonoverlap grid cho primary evidence, overlapping extension có purge và dependence corrections.

**L06.2 — Candidate bank lineage.** Bank chỉ từ discoveries trước cutoff,3–8 candidates maximumproposal; effective duplicates merged cho coverage nhưng không xóa trial rows. Retired params vẫn serve open campaigns. Indicator readiness theo version/cutoff.

**L06.3 — Similarity-response estimator.** Weighted paired delta, pooled shrinkage, support diagnostics; model context distance/group weights train-only. Không học nearest episodes bằng selecting episodes có outcome tốt. Trả supporting episode IDs/weights cho mỗi recommendation.

**L06.4 — Decision state machine.** Implement keep/switch/wait/refresh/fallback with uncertainty, minimum spacing và economic cost threshold. Quality gate có thể reject tất cả; không force best-of-bad thành trade.

**L06.5 — Distinct scheduling.** Model fit28d, infer4h như hypothesis; bank calendar như baseline; switching mỗi eligible4h boundary nếu needed; later triggered-refresh variant riêng. Deadline/coalesce/out-of-order fit completion tests.

**L06.6 — Counterfactual limitations.** Bank training utilities có initial-state contract; live switch actual current campaign có transition cost/delay. Không dùng hypothetical reset-flat expert curve làm deploy equity. Record why response uncertainty cannot capture all state-dependent execution risk.

### Outputs

`response_model.json`, `response_panel.parquet`, supporting-neighbor records, `bank_registry.json`, `policy_spec.json`, decision ledger examples và state-machine tests.

### Exit

Mọi keep/switch có evidence, data cutoffs và units nhất quán. Technical pass không phụ thuộc có nhiều switches; zero-switch vì insufficient edge là valid result.

---

## LAB-07 — Continuous regime-aware WFO integration

### Mục tiêu

Nối selector/model/policy vào **bản sao QuantBT**, chạy một account liên tục với parameter versions tại đúng thời điểm; không thay simulation economics.

### Tasks

**L07.1 — Disabled-hooks parity.** Experimental scheduler/provider tắt → current canonical baseline path giống về orders/account/metrics/selection. Same fixed intents Python/Rust parity trước performance.

**L07.2 — Availability event bus.** Ordered stream gồm market bar completions, regime-ready observations, refit request/start/ready, activation và engine fills. Event clock có sequence tie-break; engine không nhìn future `activation_end`.

**L07.3 — Training job isolation.** Refit candidate evaluation dùng snapshot account policy riêng (thường flat/reset cho training); không mutate continuous deployment account. Jobs không truy dữ liệu sau request cutoff. Refit latency từ benchmark/resource budget hoặc scenario đã freeze, không lấy thời gian zero để được fill sớm.

**L07.4 — Parameter activation.** Per-alpha migration policy Section9; pending entry commands có cancel/retain semantics; protective orders của campaign cũ giữ version. Warm indicators đã đủ, no false crossover khi reinitialize. Bank switching vẫn use same QuantBT order lifecycle.

**L07.5 — Dynamic operational segments.** Segment start khi params effective; end chỉ ghi khi có activation kế tiếp; trigger có thể nochange. Reporting clock không đổi. Logs không đưa future segment length vào policy.

**L07.6 — Failure handling.** Missing/stale context, failed model fit, incomplete probe panel, out-of-order jobs, simulation reject/liquidation và interrupted artifacts. Giữ incumbent/fallback đã validated, không chọn random params. Worker failure không erase trials.

**L07.7 — Prefix/stream/live-style replay parity.** Feed một observation/event mỗi bước phải giống offline event replay với same availability. Future mutation không đổi past decisions; reset/resume chỉ nếu full model/strategy/account state contract hỗ trợ, không bắt thêm checkpoint project.

### Outputs

Lab-only QuantBT patch/diff, `integration_binding_map.json`, regime/scheduler/provider adapters, full continuous traces, `parameter_activation_tape`, `operational_segments` và installed-lab smoke tests.

### Exit

No leakage, no account resets, no handcrafted fills, disabled parity và dynamic integration pass. Unknown unsupported hook → blocker hoặc documented lab patch, không silently route sang khác contract.

---

## LAB-08 — Controlled discovery trên bốn alpha × năm symbols

### Mục tiêu

Đo contribution thật của robustness, regime timing, bank switching và data groups với đầy đủ control.

### Tasks

**L08.1 — Freeze pilot protocol.** Primary timeframes, eval intervals, model/data cohorts, seeds và compute budgets vào immutable study registry. Source presets chỉ retrospective control. Outer claims theo contamination status đã ghi.

**L08.2 — Run factorial A/B/C/D.** Same engine/costs/cutoffs/retention, actual operational latency. Sau pilot2cells để debug, chạy20 cell statuses theo registry. Không filter alpha ít trade sau khi biết nó không hiệu quả; insufficient sample được report.

**L08.3 — Add E and controls.** Bank E so B và BANK_CALENDAR; dynamic-refit so budget-matchedcalendar; RISK_ONLY tách exposure effect. Placebo/lagged states có same-ish dwell/frequency được thiết kế past-only; hindsight label chỉ diagnostic.

**L08.4 — Data ablation.** Server-core vs server-derivatives vs server-liquidity trên comparable intervals. Free enrichment optional; tất cả trials thêm vào ledger. Không gắn improvement do short recent window với feature attribution.

**L08.5 — Complexity/cadence ladder.** M0→M1→M1S rồi limited M2 comparator; K, lambda, train memory, refit cadence tuning trong development. Không thử toàn bộ combos mặc định; một proposal phải có question/expected failure/stop condition.

**L08.6 — Capture actual computation.** Trial counts, candidate episode bars, model fits, response evals, cold/warm runtime, compute waiting/activation delays. Không tăng CPU vượt resource budget để cho dynamic policy về trước baseline.

**L08.7 — Select one confirmatory design.** Ghi selection reason dựa development, tradeoffs, failure cases và uncertainty. Không dùng outer confirm results để chọn design. Freeze alpha versions; optional alpha improvements không được nhập vào winner im lặng.

### Outputs

Every-run JSON/JSONL, comparison panels, local-neighborhood charts data, regime feature/weight profiles, discovery report, design-selection manifest và registry of all attempted hypotheses.

### Exit

Có design freeze hoặc `NO_PROMISING_DESIGN`. Không cần đạt profit để đóng discovery; không được gọi negative result là technical failure cần rerun đến khi thắng.

---

## LAB-09 — Frozen confirmation, robustness và falsification

### Mục tiêu

Chứng minh mức claim cuối cùng phù hợp evidence, không nhờ tuning toàn sample hoặc đặc biệt một event.

### Tasks

**L09.1 — Lock data roles.** Xác nhận khoảng chưa được dùng nếu có; nếu không, nói rõ nested retrospective và tạo prospective protocol artifact, không tự thực thi live. All validation access logged; no retuning sau unlock.

**L09.2 — Run frozen protocol.** Same20 cells/cohorts, minimum declared seeds, untouched costs and engine. Stateful deployments cho phép thích nghi theo frozen policy, không human adjustments giữa run.

**L09.3 — Paired uncertainty.** Daily paired deltas/block inference với common market shocks, episode counts và concentration. Multiple comparisons theo family protocol; disclose exploratory contrasts.

**L09.4 — Cost/latency stress.** 1×/1.5×/2× configured transaction-cost assumptions hoặc sensitivity đã freeze; no zero-latency model-refit default. Sai nhãn tập trung transitions, stale feeds, missing enrichment, different order-book approximation nếu post-selection optional. Không retune khi stress thua.

**L09.5 — Support/novelty test.** Regime episode mới, mixed ambiguous states, state-label permutation sau refit, candidate bank stale, no challenger qualifies, campaign không flat. Check fallbacks và time-edge attribution.

**L09.6 — Financial and research reconciliation.** Sum fills/fees/funding/cash/PnL, parameter-version lifecycle, every-trial cardinality, objective recomputation và selected replay. Audits retained không bị fast profile bỏ.

**L09.7 — Decide claim.** Descriptive/predictive/selection/timing/policy contribution đánh riêng. Net gain sau risk/cost có CI đủ hay inconclusive; không claim “fund-grade alpha proven” từ một backtest lab.

### Outputs

`confirmation_spec.json`, frozen results, uncertainty/stress panels, `claim_report.json`, leakage/contamination report và limitations.

### Exit

Một kết luận trung thực có scope; PASS validity không đồng nghĩa PASS edge. Major causal/accounting error → `FAILED_VALIDITY`, invalidates affected runs và cần protocol revision trước retest, không giữ headline.

---

## LAB-10 — Reports, charts, reproducibility và safe handoff

### Mục tiêu

Kết quả đủ dùng để đọc, vẽ biểu đồ, phản biện hoặc phát triển một bài nghiên cứu; không tự merge vào QuantBT chính.

### Tasks

**L10.1 — Build reports từ artifacts.** `.py` build Markdown và JSON summaries, không đọc mutable notebook variables. Report đồng thời baseline, all attempts, negative results và missing coverage.

**L10.2 — Figure source contracts.** Scripts tạo equity/drawdown, paired incremental returns, regime-cost/feature charts, refit/activation timeline, neighborhood heatmaps có untested mask, conditional param-response và transition-loss plots. Tất cả có data hash và config, no fabricated interpolation evidence.

**L10.3 — Reproduction command.** One CLI rebuild report từ committed artifacts offline; một CLI rerun selected bounded studies từ snapshot khi budget đủ. Reproduction of report khác rerun engine; hash equality expected theo schema/numeric contract, không absolute across unrelated hardware.

**L10.4 — Packaging reference.** Lab package/source dùng canonical import namespace, không tự tạo second financial engine. Build candidate lab artifacts, run smoke outside checkout, store code diff so baseline. External regime dependencies không lẻn vào QuantBT production requirements.

**L10.5 — Safety closure.** Input archive/alpha/source manifests unchanged; output writes confined LAB_ROOT; own workers closed, no external services/ports changed. Data snapshot hash drift invalidate run nếu violated freeze. Không xóa evidence sau kết luận âm.

**L10.6 — Handoff memo.** Nếu regime có useful evidence: module boundaries nào nên migrate sau này, public contracts gì cần bổ sung, production risks/capability chưa support, resource expectations. Nếu chỉ diagnostic value: giữ model/report tools ngoài engine; không promote parameter switching.

**L10.7 — Publication package.** Methods/registered hypotheses, code/config versions, source citations, data license restrictions, whole experiment ledger, tables/figures scripts, contamination and limitations. Không export raw restricted data/credentials. Paper claims tách descriptive evidence khỏi causal/economic claims.

### Final deliverables

```text
reports/final_report.md
reports/alpha_adaptation_report.md
reports/data_eligibility_report.md
reports/selector_report.md
reports/regime_model_report.md
reports/time_edge_report.md
reports/limitations_and_negative_results.md
evidence/study_manifest.json
evidence/claim_report.json
evidence/source_integrity_report.json
evidence/all_trials.jsonl
evidence/model_and_policy_trials.jsonl
evidence/parameter_decisions.jsonl
evidence/operational_segments.parquet
figures/*.png + generating .py + source digests
handoff/lab_only_patch.diff
handoff/production_proposal.md       # đề xuất, không auto-merge
```

**Exit:** reproducible evidence và honest claim; original QuantBT/alphas/storage không bị sửa. Không publish model/engine, không start paper/live services nếu chưa có yêu cầu riêng.

---

# 13. Schemas, CLI đích và Definition of Done

## 13.1 Research record identities

Không gộp trial/candidate/execution/selection/activation thành một ID:

```text
study_id             protocol nghiên cứu
experiment_id        arm + cell + cohort + config version
trial_id             optimizer proposal instance
candidate_id         strategy version + typed effective params
execution_id         candidate + market + initial-state + economics + seed
probe_design_id      local validation design độc lập sampler
model_id             fit artifact, features/scaler/centroids/state namespace
observation_id       actual decision-vintage regime emission
response_id          conditional estimate + supporting episodes
selection_id         đề xuất chọn/giữ dựa evidence
activation_id        params thực sự có hiệu lực tại timestamp/phase
attempt_id           một lần chạy/retry của operation
```

Cache reuse vẫn tạo trial rows mới nếu optimizer đã tạo trial mới. `reused_from` không cho phép thay data role/cutoff. Reconstructed report hoặc selected audit rerun không được ghi là original retained trace.

## 13.2 Study registration example — schema đích, không kết quả đã điền

```json
{
  "schema": "crypto_regime_lab.study.v2",
  "status": "DRAFT_REQUIRES_LAB01_FREEZE",
  "baseline": {
    "core_version": "1.1.1",
    "native_expected": "0.4.2",
    "source_sha": null,
    "wheel_digests": null,
    "installed_origins": null
  },
  "allowed_alpha_files": [
    "vwap.py", "hash_momentum.py", "adaptive_hma_cpp.py", "signal_combine.py"
  ],
  "trade_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"],
  "spot_clean_from": "2020-01-01T00:00:00Z",
  "source_preset_role": "retrospective_reference_only",
  "primary_arms": ["A", "B", "C", "D"],
  "extension_arms": ["E"],
  "model": {
    "primary": "discrete_jump_model",
    "initial_states": 3,
    "observation_interval": "4h",
    "fit_cadence_days": 28,
    "train_memory_days": 365,
    "values_are_starting_hypotheses": true
  },
  "execution": {
    "contract": "event_lifecycle_v3_next_open",
    "account_contract": null,
    "instrument_registry_digest": null,
    "fee_funding_slippage_config": null
  },
  "data_roles": null,
  "primary_endpoint": null,
  "minimum_economic_effect": null,
  "hypothesis_family_and_adjustment": null,
  "resource_budget": {"workers": 1, "cpu_limit": 2, "working_memory_gib": 4},
  "market_experiments_allowed": false,
  "production_mutations_allowed": false,
  "live_execution_allowed": false
}
```

Validator không được chuyển sang `FROZEN` khi các field bắt buộc null hoặc artifacts không kiểm chứng được. Null là thiếu thông tin được nhìn thấy, không placeholder được coi PASS. Disk quota/path mounts/cutoffs cụ thể bổ sung trong sandbox/data manifests.

## 13.3 Alpha certification record

```json
{
  "schema": "crypto_regime_lab.alpha_certification.v1",
  "alpha_id": "A-HASH",
  "raw_source_digest": "ab35d90680ea723440d8ad4d831029505e54bf2c2567350313b1cacbfea6c773",
  "adapter_version": null,
  "status": "NOT_YET_CERTIFIED_ON_QUANTBT",
  "indicator_convention": null,
  "timing_contract": null,
  "partial_quantity_convention": "fraction_of_remaining",
  "engine_capabilities_verified": [],
  "semantic_delta_refs": [],
  "golden_trace_refs": [],
  "market_test_evidence_refs": []
}
```

Tất cả four records phải có trong summary, kể cả bị block. `NOT_READY` không có PnL=0; metrics null với reason, tránh bias aggregate.

## 13.4 Decision evidence tối thiểu

Mỗi decision giữ regime/model vintage, context và response episode refs; incumbent/challenger typed params; mean/shrunk delta/uncertainty/support; estimated switching cost; gates; requested/ready/effective timestamps; old/new campaign versions và final reason.

Đặc biệt lưu cả `proposal_before_guard` và `decision_after_guard`, kể cả no-switch. Nếu threshold chế độ chỉ thay risk, record `action_type=risk_only`, không gọi parameter switch.

## 13.5 CLI đích để agent implement

Các lệnh sau là **contract của lab CLI sẽ được viết trong10 phases**, không phải lệnh QuantBT đang tồn tại. CLI phải từ chối chạy phase chưa có prerequisites hoặc marker/sandbox hợp lệ.

```bash
python -m crypto_regime_lab.cli preflight --lab-root "$LAB_ROOT"
python -m crypto_regime_lab.cli certify-alphas --registry "$LAB_ROOT/configs/alpha_registry.json"
python -m crypto_regime_lab.cli snapshot-data --study "$LAB_ROOT/configs/study_registration.json"
python -m crypto_regime_lab.cli verify-causality --study "$LAB_ROOT/configs/study_registration.json"
python -m crypto_regime_lab.cli run --stage discovery --study "$LAB_ROOT/configs/study_registration.json"
python -m crypto_regime_lab.cli freeze --study "$LAB_ROOT/configs/study_registration.json"
python -m crypto_regime_lab.cli run --stage confirmation --study "$LAB_ROOT/configs/study_registration.json"
python -m crypto_regime_lab.cli report --from-artifacts "$LAB_ROOT/evidence"
python -m crypto_regime_lab.cli verify-source-integrity --lab-root "$LAB_ROOT"
```

Không tự freeze hay confirmation khi protocol/alpha/data unresolved. `report` chỉ đọc artifacts được commit, không rerun optimizer tự động. Mỗi command ghi attempts/exit codes/affected artifact IDs và không ghi ngoài lab. Network off trong các lệnh run/certify/report.

## 13.6 Những claim không được phát hành

- “Regime work” chỉ vì states correlate với price sau khi fit full sample.
- “No leakage” chỉ vì signal `.shift(1)`.
- “Out-of-sample” cho provided full-set params hoặc holdout đã dùng để chỉnh policy.
- “Tốt hơn mọi mặt” khi chỉ một metric tốt hoặc exposure giảm.
- “Rust parity” từ final equity gần nhau nhưng order timing/fees khác.
- “Spot-perp carry” từ một derivative account không có spot inventory/borrow.
- “Whale netflow” từ một social-alert subset.
- “All4 alphas certified” vì AST parse thành công.
- “Production an toàn tuyệt đối” chỉ bằng path naming mà chưa có OS-level write isolation.

## 13.7 Stop/continue rules

Nếu validity fail: sửa adapter/data/spec trong lab, tạo version và invalidate affected studies, không tiếp tục lấy headline. Nếu economic edge fail: giữ valid results, có thể kết luận âm hoặc propose hypothesis mới **chỉ quay lại discovery với version mới**. Nếu budget hết: commit partial evidence với actual coverage, không bổ sung synthetic market scores.

Nếu chỉ descriptive value: xuất model/readout để hỗ trợ phân tích, không activate live params. Nếu selection edge nhưng timing không có thêm: giữ selector mới và calendar. Nếu risk-only đủ tốt: không ép dùng model policy phức tạp hơn. Nếu positive chỉ ở một alpha/symbol: migration proposal scope đúng subset đó.

---

# 14. Bộ acceptance tests — 64 yêu cầu, chưa phải 64 tests đã chạy

Mỗi test triển khai trong `.py`, có fixture, expected result và evidence. Assertions financial phải theo economic contract; đừng viết metamorphic invariant sai, ví dụ split-fill có thể đổi per-fill minimum fee/rounding.

| ID | Kiểm tra | Expected |
|---|---|---|
| T01 | LAB_ROOT nằm trong protected repo | Preflight reject |
| T02 | Symlink/hardlink editable trỏ source | Reject hoặc physical copy an toàn |
| T03 | ZIP path traversal/symlink/duplicate | Reject trước extract |
| T04 | Archive hash hoặc allowlist4file đổi | Stop, không tự dùng alpha mới |
| T05 | Import ghi cache ra protected path trong sandbox fixture | Bị deny, worker có error rõ |
| T06 | Network/live credentials trong replay worker | Không accessible |
| T07 | Memory/process/cancel vượt budget | Chỉ own worker dừng, committed artifacts giữ |
| T08 | Source hash trước/sau | Unchanged hoặc explicit external drift invalidate |
| T09 | HASH standalone thiếu numpy | Legacy-minimal fix documented; canonical imports pass |
| T10 | HASH short arrays và ATR convention | Guarded; legacy/corrected conventions không mix |
| T11 | HASH multiple TP crossed same bar | Engine path xử lý đúng quantity/priority |
| T12 | HASH TP2 remaining fraction và lot rounding | Không over-close; dust explicit |
| T13 | HMA open khác previous close | Actual fill/levels theo chosen contract |
| T14 | HMA invalid min/max, unused knobs | Reject invalid; inactive params không inflate search |
| T15 | HMA RSI flat, warmup/padding | Reference contract pass, no false warmup trades |
| T16 | VWAP dynamic threshold chưa available | Không retroactive intrabar fill |
| T17 | VWAP UTC day, HTF close và missing bucket | Proper availability và readiness |
| T18 | VWAP simultaneous time/SL/TP | Same event priority mọi arms |
| T19 | SC thiếu volume/RSI fallback | Resolve branch đúng hoặc explicit reject |
| T20 | SC long-flat/amplitude/crossover | No silent shorts/no double shift; semantic version |
| T21 | Fractional crypto volume | Không truncate thành int |
| T22 | ms/ns và open/close labels | Canonical timestamps đúng; units assertion |
| T23 | Same-length symbols lệch timestamps | No relabel; exact map/reject |
| T24 | Symbol trước listing | Không fabricate historical bars/returns |
| T25 | Changed future raw data/preprocessing | Past feature/state/decision unchanged |
| T26 | Snapshot sample_time cuối giờ | Không available tại đầu giờ |
| T27 | Market universe và source revision | Membership/vintage as-of, no future selection |
| T28 | Enrichment thiếu/stale | Mask/fallback; không zero giả |
| T29 | Sharp peak vs broad profitable neighborhood | Bad probes retained, stability đúng |
| T30 | Flat but negative region | Fails economic quality |
| T31 | Fixed/inactive params/far sampled point | Geometry không đổi tùy sampled artifacts |
| T32 | Dependent parameter TP/length manifold | Generate feasible unique probes |
| T33 | Centroid chưa evaluate | Không deploy trước evaluate |
| T34 | Medoid metric/tie-break | Matches reference distance objective |
| T35 | Incumbent guard khác robust objective | Visible policy; comparable guard primary |
| T36 | Fullset tuned presets vào early bank | Forbidden in primary |
| T37 | Forward JM DP vs exhaustive tiny paths | Endpoint cost/state parity |
| T38 | Batch versus streaming regime emissions | Same prefix vintages |
| T39 | Model/scaler fit với future suffix | Mutation test phát hiện/reject |
| T40 | Sparse weights collapse0/empty states | Degeneracy handled, không fake confidence |
| T41 | Model refit permutes state IDs | Namespaced mapping, không false market transition |
| T42 | Membership score bị gọi probability | Schema phân biệt/calibration evidence |
| T43 | Known regime change và model drift | Inference không automatic retrain |
| T44 | Novelty so với missing data | Separate states/fallback reasons |
| T45 | Response outcome chưa kết thúc | Không được dùng tại decisionT |
| T46 | Candidate discovered sau inner cutoff | Không xuất hiện trong inner pseudo-live bank |
| T47 | Incumbent/challenger paired episodes | Same economics/initial-state/horizon |
| T48 | One episode dominates similarity | Support/uncertainty cảnh báo, shrink/fallback |
| T49 | Refit latency/job out-of-order | No early/backdated activation |
| T50 | Params switch khi campaign còn mở | Old protective version giữ hoặc explicit migration |
| T51 | New parameter indicators chưa warm | Wait/fallback; không reset false signals |
| T52 | Model fit/bank refresh/switch counters | Distinct clocks, no recursive-trigger storm |
| T53 | A/B/C/D fixed economics và budgets | No hidden fee/risk/evaluation advantage |
| T54 | Current WFO uses OOS for selection | Claim selection-adjusted hoặc causal comparator riêng |
| T55 | Dynamic folds khác length | Same daily account comparison, không average fold Sharpe |
| T56 | Carried account qua segments | No reset/virtual splice of expert PnL |
| T57 | Sequential optimizer vs adaptive batch | Contract đúng, no false identical-sequence claim |
| T58 | Risk-only/matched-cadence controls | Present dù chúng thắng method |
| T59 | Negative/failed/pruned trials | Every record retained, null/status đúng |
| T60 | Objective recompute từ components | Khớp reported value theo numeric contract |
| T61 | JSON NaN/Inf, audit queue/error | Valid JSON; no success trước required flush |
| T62 | Heatmap chưa tested, hindsight labels | Mask/diagnostic flag; không evidence giả |
| T63 | Full5symbol paired bootstrap | Common shocks/dependence retained |
| T64 | Offline reproduce report/run và sources | Correct artifact identities; protected originals unchanged |

---

# Phụ lục A — Inventory presets và những assumptions còn cần freeze

## A.1 Preset handling theo file

| File | Literal dictionaries đọc được | Xử lý |
|---|---:|---|
| `hash_momentum.py` | 6 | Catalog fullset references;4 unordered TP cho canonical ladder |
| `adaptive_hma_cpp.py` | 13 | Catalog;4 inverted min/max;13 có `sl_mult` không effect |
| `vwap.py` | 15 | 4 dictionaries mang VWAP keys; `base` có HTF;10 còn lại không phải VWAP parameter schema; final merge dùng `tete` |
| `signal_combine.py` | 1 | Catalog provided config; long-flat amplitude2 ambiguity explicit |

Không coi dictionary name `bubu` ở hai files là cùng parameter set. ID bao gồm alpha/file hash + dictionary name + typed values. Comment “đẹp/xấu/ít trade” là prior human observation, không market evidence được xác minh ở lab.

## A.2 Assumption register

| Assumption | Default xử lý khi chưa có thông tin | Agent không được làm |
|---|---|---|
| Source strategy trading venue | Proposed linear-perp research setup Section4; baseline reproduction label riêng | Claim old PnL parity khi venue/costs chưa biết |
| Original TPE search domain/cutoff | Unknown, presets quarantined | Suy bounds tối ưu từ provided winners |
| Spot clean từ2020 | Accepted user convention | Mở lại source-repair debate ngoài scope |
| Canonical fees/funding/size | Required freeze từ experiment config và instrument data | Điền0/giả leverage để dễ thắng |
| Primary timeframe | Proposed table Section10, freeze before results | Chọn timeframe thắng từ preset comments |
| Dynamic VWAP exit | Versioned lagged-resting hoặc close-decision | Current-bar VWAP giả resting tại open |
| HASH ATR | Explicit legacy-close-move vs true-TR revision | Gọi hai formula là same alpha không giải thích |
| SignalCombine shorting | Off như source primary | Tự thêm short vào kết quả regime primary |
| HMA double_up/sl_mult | Ignored/unsupported như source, không search | Tự implement guessed economics |
| Clean holdout | Unknown until exposure audit | Tự đặt nhãn untouched cho cuối dataset |
| Regime model cadence | 4h inference/28d fit starting hypothesis | Mỗi label change gọi optimizer/retrain vô điều kiện |
| Sparse/JM libraries | Pin actual version và source algorithm | Auto nâng dependency theo stable docs mới |

---

# Phụ lục B — Diagnostics đã chạy trên upload, không phải market evidence

Trong phiên review, đã chạy 21 probes; tất cả xác nhận đúng property/hiện tượng được đặt test. Bốn trong đó chỉ là AST parse. Các lỗi/hành vi trọng yếu:

| Probe | Observed |
|---|---|
| HASH thiếu NumPy | `NameError: name 'np' is not defined` |
| HASH short input10rows | `IndexError` tại unguarded seed index |
| HASH close-only ATR | Constant closes →0 dù high/low có thể có range |
| HASH không MTM | Synthetic10units entry100, last110: reported equity10000; wallet+UPnL=10100 |
| HASH TP branch | Bar chạm TP1/TP2/final: chỉ TP1, units10→5 |
| HASH unordered presets | `huhu`, `bubu`, `haft`, `kuku` |
| HMA RSI flat | Seed50, next bar100 |
| HMA inverted min/max | `hfhf`, `hjhj`, `hoho`, `hbhb` |
| HMA unused | `time_ms`, `volume`, `double_up`;13 presets có `sl_mult` không được đọc |
| HMA gap information | Không có open argument trong core |
| VWAP short input | SMA50 trên10rows bị `IndexError` |
| VWAP open ignored | Thay open sau entry không đổi pos output; không có fill-price evidence |
| SignalCombine positions | Synthetic signals → `[0,2,0,0,2]`, không short |
| SignalCombine fallback | RSI stub vẫn bị gọi `money_flow_index`, `AttributeError` |
| SignalCombine crossover | Current comparison khác conventional shifted-operand crossover; cần spec, không auto-fix |
| JM DP | Max absolute cost error với exhaustive tiny oracle ≈`1.11e-16` |

Test HASH entry ban đầu trong harness cần close tăng để kích hoạt điều kiện gốc; fixture cuối dùng `[99,100,110]`. Không thay thân hàm alpha để tạo kết quả mong muốn. Financial numbers ở bảng là synthetic examples, không trading returns.

Bộ acceptance 64 ở Section 14 **chưa được chạy**; không thay bằng 21 diagnostics này. Không có live/server/WFO benchmark trong review.

---

# Phụ lục C — Lệnh đầu vào cho agent và kiểm soát thực thi

Agent nhận tài liệu này cùng archive và paths do user/môi trường chỉ định. Trình tự bắt buộc:

```text
1. Đọc Sections 0–4 trước, lập source/alpha/safety manifests.
2. Tạo LAB_ROOT mới ngoài protected roots; snapshot/export read-only.
3. Triển khai sandbox, marker, writer và version probes.
4. Chạy source diagnostics/adapter synthetic tests trên bản sao.
5. Snapshot dữ liệu sẵn có; chạy prefix/market-domain certification.
6. Chỉ sau đó mới chạy calendar baseline và regime experiments.
7. Ghi mọi failures và results; không sửa production để "fix nhanh".
8. Dừng sau evidence/handoff. Migrate vào main là yêu cầu khác.
```

Read permission không phải write permission. Có source package trong lab không cho phép mở root production với editor để sửa ngay. Mọi diff đề xuất phải nằm trong `handoff/`.

Không chạy tất cả tests/datasets ngay bằng mọi CPU. Pilot ở slices được gắn development trước, khóa costs/version, rồi scale theo resource policy. Không gọi data collector, trading adapters hoặc scheduler services để lấy market history.

Nếu current QuantBT không support một primitive cần thiết, báo exact capability gap và thêm implementation trong lab copy có regression tests. Không nói “regime không work” khi lỗi nằm ở adapter; cũng không che adapter fail bằng một synthetic position-return proxy.

---

# Phụ lục D — Nguồn và mức độ sử dụng

Nguồn được đối chiếu ngày 2026-09-09. Các URL `main`/`stable` có thể thay đổi; agent lưu snapshot/hash và version thực tại LAB-01. Tài liệu nguồn hỗ trợ cơ chế kỹ thuật, **không chứng nhận hiệu quả của bốn alpha hoặc của regime policy**. Không dùng kết quả công bố của một paper làm số đo của lab.

| ID | Nguồn | Vai trò trong guide |
|---|---|---|
| S1 | [QuantBT pyproject.toml](https://github.com/BobbyAxerol/quantbt/blob/main/pyproject.toml) | Version 1.1.1, native 0.4.2, source layout và dependency constraints; cần pin artifact actual |
| S2 | [QuantBT endpoint reference](https://github.com/BobbyAxerol/quantbt/blob/main/docs/endpoint.md) | Phân biệt target/event/reactive/intrabar factories; actual signatures vẫn phải inspect |
| S3 | [QuantBT execution contracts](https://github.com/BobbyAxerol/quantbt/blob/main/docs/execution_contracts.md) | Timing, target vs order execution và explicit clock IDs |
| S4 | [QuantBT fast intrabar](https://github.com/BobbyAxerol/quantbt/blob/main/docs/fast_intrabar.md) | Specialized intrabar reference; không coi position tape là full order lifecycle |
| S5 | [QuantBT WFO methodology](https://github.com/BobbyAxerol/quantbt/blob/main/methodology/walk_forward.md) | Mapping modes/selection scopes; không thay source-level proof của installed version |
| S6 | [Historical data loader](https://github.com/BobbyAxerol/trading-historical-data/blob/main/data_loader.py) | Reader/projection/normalization; `columns="full"`; server inventory quyết định coverage thật |
| S7 | [Historical data README](https://github.com/BobbyAxerol/trading-historical-data/blob/main/README.md) | Product/data organization overview; không dùng để suy ra every-series availability |
| S8 | [Cortese, Kolm, Lindström — What drives cryptocurrency returns? A sparse statistical jump model approach](https://link.springer.com/article/10.1007/s42521-023-00085-x) | Cơ sở nghiên cứu SJM crypto và feature-selection; không sao chép kết quả hay states làm ground truth |
| S9 | [Statistical jump-model implementation](https://github.com/Yizhan-Oliver-Shu/jump-models) | Discrete/continuous/sparse implementations và online methods; pin source và đối chiếu recursion trước sử dụng |
| S10 | [Optuna 4.8 TPESampler](https://optuna.readthedocs.io/en/v4.8.0/reference/samplers/generated/optuna.samplers.TPESampler.html) | Adaptive sampling và sampler configuration theo baseline dependency; không tự nâng tới stable mới |
| S11 | [DefiLlama API SDK](https://github.com/DefiLlama/api-sdk) | Public stablecoin context và phân biệt endpoints free/pro |
| S12 | [Whale Alert documentation](https://developer.whale-alert.io/api-account/documentation) | Historical published-alert archive; không nhầm enterprise transaction history với public alerts |
| S13 | [Farside Bitcoin ETF flows](https://farside.co.uk/btc/) | Daily flow context trên cohort có dữ liệu, cần publication-time policy |
| S14 | [Coin Metrics Community Data](https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data) | Coverage/license review trước enrichment; không tự suy free đồng nghĩa unrestricted commercial use |
| S15 | [scikit-learn — Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html) | Train-only preprocessing và pipeline leakage; đây là nguyên tắc, không là lệnh nâng dependency |
| S16 | [Binance public data](https://github.com/binance/binance-public-data) | Archive structure, fields và timestamp-unit changes; snapshot actual files |
| S17 | [Online statistical-jump-model downside-risk research](https://arxiv.org/html/2402.05272v3) | Phân biệt training/inference và online evaluation; equity cadence không được áp dụng nguyên xi vào crypto |
| S18 | [Man Group — Regimes, Systematic Models and the Power of Prediction](https://www.man.com/insights/regimes-systematic-models-power-of-prediction) | Nguồn gợi ý historical-similarity decision research; response estimator trong guide là đề xuất riêng cho lab |

**Nguồn sơ cấp cho review alpha:** bốn files được upload trong archive có hashes ở Section 1; line references trong Section 3 là line của raw files, không của bản adapter tương lai. Tác giả lab phải giữ nguyên licenses/copyright notices trong bản sao, không công bố alpha source hoặc dữ liệu có hạn chế quyền sử dụng chỉ vì report được chia sẻ.

Guide V1 trước đây và các thảo luận được dùng để giữ approved scope; khi có khác biệt, Final V2 này là nguồn kế hoạch cho lab. Nếu actual source/capabilities mới thay đổi, ghi correction ADR và explicit plan revision, không sửa evidence của run cũ.

---

# Kết luận và tiêu chuẩn bàn giao

Lab chỉ được bàn giao như một kết quả nghiên cứu có thể kiểm tra khi có đủ ba lớp:

1. **Bốn alpha được chuẩn hóa có thể giải thích:** source nguyên gốc được bảo tồn; imports, indicators, position sizing, entry/exit, TP/SL, partial fills và timing có spec; bản sửa được chứng minh trên synthetic/engine tests trước khi đưa vào A/B.
2. **Methodology thích nghi có thể tái hiện:** selector đo đúng quality + neighborhood stability; regime model chỉ đọc information set hợp lệ; response model không dùng future outcomes; activation và campaign migration thực hiện trên một account liên tục.
3. **Kết luận có evidence chứ không có áp lực phải thắng:** mọi trials, probes, model fits, triggers, decisions, costs, uncertainty và failures được lưu; comparison giữ baseline, compute budget và risk controls; kết quả có thể là có edge, chỉ có diagnostic value, không cải thiện hoặc chưa đủ bằng chứng.

Một lab hoàn tất không đồng nghĩa cả bốn alpha phải profitable hoặc mọi symbol phải có regime edge. Không thay alpha/selector/model sau khi nhìn confirmation rồi ghi đè kết quả. Khi có kết quả đáng triển khai, agent xuất bounded patch/API proposal và reproduction bundle trong `handoff/`; **không tự merge vào QuantBT chính và không tự triển khai live**.


---

# Phụ lục E — Evidence JSON của diagnostics thực sự đã chạy

Đây là record thực từ phiên đọc upload, không phải template cho market results. `CONFIRMED` nghĩa là property/reproducer ghi trong `expectation` đã được quan sát, không nghĩa alpha đã được certify. Bốn `PARSE_*` chỉ kiểm AST. Khi agent chạy lại trong environment đã khóa, tạo run record mới và giữ record này như provenance; không overwrite thành kết quả QuantBT.

```json
{
  "evidence_type": "LOCAL_SOURCE_DIAGNOSTICS_NOT_MARKET_BACKTEST",
  "input_archive_sha256": "57406dbb9ffdcf4617e4895925126fa73600a585a6541f996c6b2d980f6701ae",
  "scope": "local static/AST-loaded function diagnostics only; no QuantBT, ta, JIT or market-data certification",
  "environment": {
    "numpy": "2.3.5",
    "pandas": "2.2.3",
    "quantbt_execution_tested": false,
    "numba_jit_tested": false,
    "ta_real_dependency_tested": false
  },
  "probe_count": 21,
  "confirmed_count": 21,
  "results": [
    {
      "id": "PARSE_vwap.py",
      "status": "CONFIRMED",
      "observed": 249,
      "scope": "synthetic_or_static_source",
      "expectation": "AST parses without import/execution"
    },
    {
      "id": "PARSE_hash_momentum.py",
      "status": "CONFIRMED",
      "observed": 166,
      "scope": "synthetic_or_static_source",
      "expectation": "AST parses without import/execution"
    },
    {
      "id": "PARSE_adaptive_hma_cpp.py",
      "status": "CONFIRMED",
      "observed": 349,
      "scope": "synthetic_or_static_source",
      "expectation": "AST parses without import/execution"
    },
    {
      "id": "PARSE_signal_combine.py",
      "status": "CONFIRMED",
      "observed": 145,
      "scope": "synthetic_or_static_source",
      "expectation": "AST parses without import/execution"
    },
    {
      "id": "HASH_MISSING_NUMPY",
      "status": "CONFIRMED",
      "observed": "NameError: name 'np' is not defined",
      "scope": "synthetic_or_static_source",
      "expectation": "unbound np raises before indicator call"
    },
    {
      "id": "HASH_SHORT_ARRAY",
      "status": "CONFIRMED",
      "observed": "IndexError",
      "scope": "synthetic_or_static_source",
      "expectation": "atr[14] fails for length 10"
    },
    {
      "id": "HASH_ATR_CLOSE_ONLY",
      "status": "CONFIRMED",
      "observed": 0.0,
      "scope": "synthetic_or_static_source",
      "expectation": "constant closes yield 0 regardless of any high/low range"
    },
    {
      "id": "HASH_EQUITY_NO_MTM",
      "status": "CONFIRMED",
      "observed": {
        "units": [
          0.0,
          10.0,
          10.0
        ],
        "reported_equity": [
          10000.0,
          10000.0,
          10000.0
        ],
        "terminal_wallet_plus_unrealized": 10100.0
      },
      "scope": "synthetic_or_static_source",
      "expectation": "open-position equity omits unrealized +100"
    },
    {
      "id": "HASH_ONE_TP_BRANCH_PER_BAR",
      "status": "CONFIRMED",
      "observed": {
        "units": [
          0.0,
          10.0,
          5.0
        ],
        "reported_equity": [
          10000.0,
          10000.0,
          10005.0
        ]
      },
      "scope": "synthetic_or_static_source",
      "expectation": "bar crosses tp1,tp2,final but only tp1 executes"
    },
    {
      "id": "HASH_UNORDERED_TP_PRESETS",
      "status": "CONFIRMED",
      "observed": [
        "huhu",
        "bubu",
        "haft",
        "kuku"
      ],
      "scope": "synthetic_or_static_source",
      "expectation": "invalid for a simultaneous increasing TP ladder"
    },
    {
      "id": "HMA_FLAT_RSI",
      "status": "CONFIRMED",
      "observed": {
        "at_seed": 50.0,
        "next": 100.0
      },
      "scope": "synthetic_or_static_source",
      "expectation": "flat series changes 50 -> 100 in implementation"
    },
    {
      "id": "HMA_INVERTED_LENGTH_PRESETS",
      "status": "CONFIRMED",
      "observed": [
        "hfhf",
        "hjhj",
        "hoho",
        "hbhb"
      ],
      "scope": "synthetic_or_static_source",
      "expectation": "must not silently repair known-tuned presets"
    },
    {
      "id": "HMA_UNUSED_ARGUMENTS",
      "status": "CONFIRMED",
      "observed": [
        "time_ms",
        "volume",
        "double_up"
      ],
      "scope": "synthetic_or_static_source",
      "expectation": "time_ms,volume,double_up do not affect core outputs"
    },
    {
      "id": "HMA_NO_OPEN_INPUT",
      "status": "CONFIRMED",
      "observed": [
        "time_ms",
        "close",
        "high",
        "low",
        "volume",
        "minLength",
        "maxLength",
        "minorMin",
        "minorMax",
        "flat",
        "atrFast",
        "atrSlow",
        "mult",
        "maxSL",
        "takeProfit",
        "minProfit",
        "sl_input_mode",
        "double_up"
      ],
      "scope": "synthetic_or_static_source",
      "expectation": "open price absent from core signature"
    },
    {
      "id": "HMA_IGNORED_SL_MULT",
      "status": "CONFIRMED",
      "observed": 13,
      "scope": "synthetic_or_static_source",
      "expectation": "sl_mult present only in presets, not parameter reads"
    },
    {
      "id": "VWAP_SHORT_ARRAY",
      "status": "CONFIRMED",
      "observed": "IndexError",
      "scope": "synthetic_or_static_source",
      "expectation": "n_sma assumes >=length input"
    },
    {
      "id": "VWAP_OPEN_IGNORED",
      "status": "CONFIRMED",
      "observed": {
        "p200": 1.0,
        "p201": 0.0,
        "same_output_after_open_change": true
      },
      "scope": "synthetic_or_static_source",
      "expectation": "open input never used; output cannot represent gap fill economics"
    },
    {
      "id": "SIGCOMBINE_LONG_FLAT_ONLY",
      "status": "CONFIRMED",
      "observed": [
        0,
        2,
        0,
        0,
        2
      ],
      "scope": "synthetic_or_static_source",
      "expectation": "short signal makes pos=0, never negative"
    },
    {
      "id": "SIGCOMBINE_FALLBACK_DISPATCH",
      "status": "CONFIRMED",
      "observed": "AttributeError: 'StubRsi' object has no attribute 'money_flow_index'",
      "scope": "synthetic_or_static_source",
      "expectation": "RSI fallback still calls money_flow_index when flag false; API-minimal stubs only"
    },
    {
      "id": "SIGCOMBINE_CROSSOVER_DIFF",
      "status": "CONFIRMED",
      "observed": {
        "actual": [
          false,
          false,
          false,
          false
        ],
        "standard_shifted_operand": [
          false,
          false,
          false,
          true
        ]
      },
      "scope": "synthetic_or_static_source",
      "expectation": "current formula differs from conventional crossover against trend.shift(2); specification needed"
    },
    {
      "id": "JM_FORWARD_DP_ORACLE",
      "status": "CONFIRMED",
      "observed": {
        "max_abs_error": 1.1102230246251565e-16,
        "prefix_endpoint_states": [
          0,
          1,
          1,
          0
        ]
      },
      "scope": "synthetic_or_static_source",
      "expectation": "causal endpoint DP matches brute force best-prefix-ending-state cost"
    }
  ]
}
```
