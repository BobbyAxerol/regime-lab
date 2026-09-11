# Regime-lab — Audit thực tế source, evidence và kết luận về parameter time edge

**Ngày audit:** 11/09/2026.  
**Nguồn:** `regime-lab-main.zip` do người dùng cung cấp; không suy từ GitHub `main` đang thay đổi.  
**SHA-256 ZIP:** `2765bd069a5caf16921c3df03dfafd8f090f4fdd2de5e1550a5ce390c87a980f`.  
**Trạng thái:** `SOURCE_FINDINGS_REPRODUCED / FULL_MARKET_RERUN_NOT_PERFORMED`.  
**Mục tiêu:** xác định lab có kiểm tra đúng giả thuyết regime → lựa chọn/kích hoạt params → lợi ích kinh tế hay không; phân biệt lỗi implementation, hạn chế nghiên cứu và kết quả âm thực sự.

## 1. Kết luận điều hành

**Chưa có cơ sở hợp lệ để kết luận regime-aware WFO không có time edge từ bộ kết quả hiện tại. Cũng chưa có cơ sở để kết luận nó có edge.**

Đây không còn là nghi ngờ chỉ từ plan. Audit đã tái hiện các lỗi concrete trên source được gửi: tham số đầu tiên được kích hoạt trước cutoff, scheduler coi đổi namespace model là market transition và dùng cả emission không eligible, nhánh E được chạy bằng lịch của D, response sử dụng squared residual thay cho context, ba stop-loss modes của HMA đều rơi về một mode, candidate không hội tụ vẫn được chấm, convergence chỉ so bar IDs, PnL ở đầu episodes bị rơi mất và threshold kinh tế thiếu hệ số allocation.

Cần công bằng với Claude: artifact cuối `configs/lab09_claim_report.json` đã tự ghi **FAILED_VALIDITY**, nhận ra fee thực thu bằng nửa mức đăng ký; cũng công khai thiếu A-HASH, response zero-switch, retrospective contamination và nhiều limitations. Vì vậy không mô tả Claude như đã giấu lỗi hoặc đưa một kết luận âm vô điều kiện. Tuy nhiên các subclaims `SELECTION/TIMING = RULED_OUT` và `confirms_the_development_outcome=true` vẫn mạnh hơn evidence có thể chịu được.

Một kết luận phù hợp hơn cho snapshot này:

> Chưa có kết quả hợp lệ để xác nhận hoặc loại trừ parameter-selection/time-edge của regime. C/D mới thử một hybrid calendar-anchored transition schedule; E chưa được thực thi như một response-driven deployment arm. Các kết quả kinh tế hiện có bị ảnh hưởng bởi fee contract, timing, adapter và metric defects; phải sửa và đánh giá lại trước khi suy luận về giá trị regime.

## 2. Tôi thực sự đã kiểm tra gì?

| Công việc | Mức kiểm chứng |
|---|---|
| Kiểm kê archive, bỏ phần không liên quan/không an toàn | 1.893 files trong working copy; không chạy cài đặt từ venv cũ |
| Markdown | Đối chiếu guide, CLAUDE.md, reports LAB-01…09, compliance/improvement/handoff documents; tổng 18 MD trong archive |
| JSON | Parse 859 files thành công; inspection định hướng theo claims, configs, phase results, trials, emissions, policy và reconciliation |
| JSONL | Parse 571 files, 5.634 rows, không lỗi cú pháp |
| Source | 101 Python files trong lab package, 88 scripts, 27 test modules; đọc sâu call paths từ experiment runners tới adapter, QuantBT bridge, selector, regime, response, policy, statistics và reporting |
| Existing tests | Chạy bốn modules regime/selector/policy/uncertainty: 196 pass, 2 fail do đường executable venv cứng không có ở môi trường audit |
| Independent probes | 12 tests nhỏ trên source thực, reference QuantBT hoặc synthetic/mocked counterexamples; kết quả và code kèm bundle |
| Market experiment | **Chưa chạy lại full market experiment**: ZIP có manifest nhưng không có raw market snapshot/panels cần thiết |
| Native Rust wheel | Wheel kèm là CPython 3.12, môi trường audit Python 3.13; chưa chứng nhận native wheel parity |
| Reference engine | Import được QuantBT 1.1.1 từ candidate copy và chạy reference-path fee probe |

Parse mọi JSON không đồng nghĩa chứng minh mọi record đúng. 196 tests pass không chứng minh toàn pipeline pass. Mocked probes minh chứng một validation hole của code, không phải chứng minh market đã gặp mọi tình huống injected. Các số đếm từ market artifacts được ghi riêng với probes.

Không chỉnh QuantBT chính, alpha gốc hoặc storage/server của người dùng. Chỉ tạo bản giải nén và diagnostics trong workspace audit. Không khẳng định biết HEAD Git chỉ từ tên ZIP; archive digest là source identity khả dụng.

## 3. Những phần đáng giữ, không cần đập đi làm lại

1. Có cấu trúc data/model/selector/policy/experiment/evidence tương đối tách bạch; nhiều artifacts có cutoff, role, flags và reasons.
2. Không giấu toàn bộ failures: A-HASH được đánh NOT_READY thay vì cho PnL=0; fee defect được tự phát hiện; zero-switch và vacuous checks đã được mô tả.
3. JM có forward inference/reference tests; distinction smoothed/decision-vintage và model namespace đã được viết trong module.
4. Independent-neighborhood selector giữ bad probes tốt hơn chỉ dùng top-TPE density. Có schema-distance tests và proposal cho generic QuantBT selector.
5. Reporting dùng artifacts đã lưu; paired daily comparison và common-shock resampling là hướng đúng về khung, dù inputs hiện chưa đủ hợp lệ.
6. Có separation giữa production QuantBT và lab. Không cần đưa regime feature/model vào core package để sửa các findings này.

Những foundation này có thể tái sử dụng. Lỗi lớn nằm ở **integration và semantic contracts**: helper có design đúng nhưng runner thực không tuân thủ hoặc không gọi helper.

---

# 4. Các findings cần sửa trước mọi kết luận kinh tế

Mức P0 dưới đây nghĩa là chặn claim của các experiments bị ảnh hưởng, không khẳng định mọi file hay toàn QuantBT engine sai. Source locations được trích lại với SHA-256 trong `REGIME_LAB_SOURCE_EXCERPTS_VI.md`.

## A01 — Fee contract thực thi chỉ bằng nửa mức đăng ký

**Mức:** P0, đã được Claude phát hiện; audit tái hiện độc lập.  
**Nguồn:** `experiments/evaluator.py:86–95`; `quantbt_bridge/intent_tape.py:117–139`; `configs/cost_binding_verification.json`; probe P01; SRC12–13.

Lab đăng ký `taker_fee_rate=0.0004` một chiều nhưng truyền qua argument `fee` có legacy round-trip semantics. Reference run giao dịch notional 2.000 USDT ở giá 100 thu 0,4 USDT mỗi fill, tức rate 0,0002, thay vì 0,8 USDT/rate 0,0004.

**Tại sao ảnh hưởng inference:** các params khác nhau về turnover. Phí sai không triệt tiêu chỉ vì mọi arm dùng cùng rate sai. Fee-sensitivity artifact của lab đã cho thấy một trong 12 selections của probe A-SC/BTC thay đổi khi sửa fee.

**Sửa:** freeze one-way/round-trip binding bằng typed config và golden fill fixture; actual fee/notional phải khớp. Sau đó chạy lại search, probes, selected params và deployment. Không chỉ trừ phí bổ sung vào curve cuối hoặc giữ nguyên selections cũ rồi gọi là corrected WFO.

## A02 — Bộ params đầu tiên được backdate về đầu account

**Mức:** P0, source + synthetic actual-runtime reproduction + exposure trong artifacts.  
**Nguồn:** `experiments/factorial.py:170–203`; `integration/continuous_account.py:207–220`; probes P02/P12; SRC01–02.

`_schedule_from_selections` tạo `requested_at_bar` theo cutoff, nhưng trả phần tử đầu như `initial`. Continuous runner lập `active = initial` ngay từ bar 0; không chờ `initial.requested_at_bar`. `fit_ready_at` cũng không được lowering vào schedule.

P02 dùng HMA initial version chỉ được yêu cầu tại bar 100: cả 100 bars trước đó vẫn ghi active version đó. Toy này không có fills, nên chỉ chứng minh backdated state — không giả nó định lượng PnL thị trường. P12 cho cutoff bar 5, ready bar 10; schedule vẫn requested bar 5.

Trong confirmation, first dynamic cutoffs muộn hơn đầu account: BTC +28 giờ; ETH/SOL/DOGE +64 giờ; BNB +8 giờ. Vì vậy đây không chỉ là một API edge case không được exercise. Mức lợi ích/tổn thất do backdating chưa định lượng vì thiếu raw market replay.

**Sửa:** initial incumbent phải được chọn bằng dữ liệu trước deployment start. Những decisions sau start đều đi qua pending queue. `effective_at >= max(selection_cutoff, fit_ready_at, indicator_ready_at)` rồi tới đúng execution phase. Giữ riêng wall-clock experiment runtime và simulated historical availability. Test đổi toàn suffix sau T không đổi effective params/commands trước T.

## A03 — Candidate/arm không hội tụ vẫn được chấm và đưa vào confirmation

**Mức:** P0.  
**Nguồn:** `evaluator.py:210–239`; `calendar_baseline.py:161–177`; `lab08_factorial_full.json`; `lab09_confirmation_results.json`; P06/P07; SRC14/SRC16.

Có hai lỗi riêng:

- Convergence chỉ kiểm `set(observed_exit_bars) == set(applied_exit_bars)`. Giá, quantity, reason, sequence và reject không được so.
- `_evaluate` trả `ProbeStatus.EVALUATED` ngay cả khi `run.converged=False` hoặc có unmapped intents. Final arm cũng được giữ trong thống kê dù có `exit_fixed_point_converged=false`.

P07 inject adapter exit bar5 giá80 và engine exit bar5 giá120: code vẫn báo converged. P06 inject converged=False, unmapped=3: candidate vẫn EVALUATED.

**Evidence thực:** development có 7 arm-cell outputs nonconverged. Confirmation có 5: A-VWAP/BTC C,D,E; A-VWAP/ETH A; A-VWAP/SOL C. E trùng D nên không gọi đó là năm thí nghiệm độc lập.

**Sửa:** không chấm objective khi execution chưa hợp lệ; không map engine failure thành financial loss. Quan trọng hơn, thay fixed-point bridge bằng actual event/fill feedback (A04). Trong thời gian chưa sửa, invalidate matched comparisons bị ảnh hưởng; không bỏ riêng các arm xấu rồi tính lại panel lệch denominator. Reconciliation gate phải đứng trước uncertainty/claim generator.

## A04 — Adapter nhận fills tự tạo; corrective exits và amendments có thể mất

**Mức:** P0.  
**Nguồn:** `evaluator._sweep:150–192`; `continuous_account.py:293–321`; `a_hma.py:328–340`; `intent_tape.py:101–105`; SRC03/SRC13–14/SRC21–22; P11.

Runner gọi `adapter.on_fill` bằng raw next-open và quantity tính từ notional/raw-open trước khi actual whole-window engine pass xác nhận fill. Trong khi đó fill có thể khác vì slippage, constraints, rejection hoặc protection ordering. Không phải mọi internal future lookup tự động là leakage; vấn đề được chứng minh là **adapter state không do actual execution stream làm authority** và fixed-point reconciliation quá yếu.

HMA có thể trả follow-up EXIT_ALL khi bracket không hợp lệ sau gap. `_sweep` chỉ xử lý follow-up có `stop_price`, bỏ corrective exit. P11 dùng stub phát EXIT_ALL thật vào code `_sweep`: không có applied exit, position vẫn20.

VWAP có nhánh `AMEND_PROTECTION`; bridge ghi unmapped nhưng không thực thi. Trong confirmation, 40/120 selected A-VWAP params records của A–D bật `exit_at_vwap=True`. Con số này là số records cấu hình yêu cầu feature, **không phải số amendments đã được replay**; event counts chưa được lưu đủ để tính tác động.

**Sửa:** một vòng `on_bar_close → commands → QuantBT acceptance/fills → on_fill/on_order_event → follow-up commands`. Actual price/qty/reject/fee phải đi ngược vào adapter. Mọi intent phải là executed, explicitly rejected hoặc unsupported-blocked; không “unmapped nhưng vẫn scored”. Giữ package QuantBT chính read-only; dùng public event/reactive surface nếu đủ. Nếu package không đủ capability, mở lab-local integration proposal được duyệt hoặc block route — không tự mô phỏng fills giả để hoàn thành checklist.

## A05 — Không gian stop-loss của HMA không giống không gian được khai báo

**Mức:** P0 cho study A-HMA.  
**Nguồn:** `selector/alpha_schemas.py:59–62`; `alphas/a_hma.py:32`, `:260`; SRC18–20; P05.

Schema đưa ra `Half Distance Zone`, `Zone Distance`, `ATR`. Adapter thực chấp nhận `One Distance Zone`, `Half Distance Zone`, `Last High/Low`, `ATR Only`. Adapter dùng `.get(sl_input, 1)` nên ba choices đang search đều map về mode 1.

Confirmation có 120 HMA selected records A–D: ATR: 43, Half: 47, Zone: 30. Chúng không chứng minh ba stop policies khác nhau vì effective mode vẫn giống nhau.

**Sửa:** dùng một enum/schema canonical, reject unknown thay vì default im lặng. Mỗi active parameter có behavioral probe chứng minh nó có thể thay đổi signals/orders đúng domain. Dedupe theo effective semantics và không thưởng coverage giả. Sửa names bằng migration có version rồi chạy lại search. Không diễn giải kết quả cũ là so đủ stop-mode family.

Tick cứng trong HMA cũng cần kết nối registry thật. Tuy nhiên mode phụ thuộc tick đang không reach được từ các choices trên; audit **không quy PnL hiện tại cho lỗi tick chưa được chứng minh tác động**.

## A06 — Execution timeframe thực không phải 1 phút như protocol

**Mức:** P0 contract deviation, đã được OP-19 tự nhận.  
**Nguồn:** `evaluator.py:207–208`; `continuous_account.py:170–171`; `reports/improvement_opinions.md`.

Decision frame 15m/1h được dùng làm engine frame. Resolution protection không phải 1m như guide/protocol. Cùng approximation giữa arms không bảo đảm comparative effect không đổi: params thay stops/targets/turnover nên intrabar bias có thể khác nhau.

**Sửa:** map completed HTF decisions vào one-minute event clock; emit order earliest hợp lệ, đặt bảo vệ sau actual fill, không cung cấp future HTF high/low tại open. Giữ execution 1m cho mọi arms. Hoặc đăng ký study 15m/1h riêng với claim hẹp, không gọi đó là đúng protocol 1m ban đầu.

## A07 — Episode utility bỏ mất PnL tại điểm đầu mỗi block

**Mức:** P0 cho selector/response metrics.  
**Nguồn:** `evaluator.py:267–290`; SRC15; P08.

`net_return=(segment[-1]-segment[0])/capital` không tính biến động từ observation ngay trước `lo` tới observation `lo`.

Toy equity `[20000,20000,19000,19000]`, chia blocks `[0:2]` và `[2:4]`: code cho cả hai net returns=0 dù account mất 1.000. Đây là mất PnL tại boundary, không phải vấn đề compounding.

**Sửa:** dùng prior mark/equity trước block, hoặc sum chính xác committed account deltas theo half-open interval. Với `lo=0`, dùng initial equity trước observation đầu. Drawdown block cũng phải định nghĩa starting watermark. Invariant: tổng money deltas của partition nối lại bằng whole-path delta, có external cashflows tách riêng.

## A08 — Arm A không tái hiện đúng public WFO/robust selector người dùng muốn làm baseline

**Mức:** P0 về target comparison; không khẳng định helper argmax tự sai toán.  
**Nguồn:** `calendar_baseline.py:351–409` và module docstring; SRC17.

Lab có custom calendar loop. `_select_with_installed` tạo candidate records với objective là mean utility, điền trường `mean_is_sharpe` bằng utility, `mean_oos_sharpe=0`, dùng default selector/optimization_mode chứ không trace đúng current public WFO robust configuration.

Một thí nghiệm **argmax utility vs neighborhood selector** vẫn có giá trị nếu được gọi đúng. Nhưng không tương đương “WFO hiện tại dùng plateau của người dùng vs WFO regime”. Metadata về OOS-selection từ một route khác cũng không được gắn sang local loop chưa dùng route đó.

**Sửa:** giữ A_custom_argmax như control, thêm baseline actual public QuantBT với config/route/selector cuối cùng được pin. Nếu actual legacy uses selection-adjusted OOS, ghi riêng reproduction arm và chọn causal baseline hợp lệ; không sửa ngầm rồi gọi giống hệt bản cũ. Không ghi utility vào trường Sharpe nếu đơn vị không phải Sharpe.

## A09 — E là bản sao lịch D, không phải conditional-response deployment

**Mức:** P0, confirmed source + actual artifacts.  
**Nguồn:** `scripts/run_lab08_factorial.py:279–293`; SRC05.

Runner gán E cùng selections của D và gọi `run_arm` tương tự. Comment nói LAB-06 không có switch nên E dùng lịch của D. Nhưng LAB-06 chỉ chạy policy trên A-SC/BTC, với incumbent/policy context khác. Không được suy zero-switch của một cell thành hành vi của 15 cells; cũng không được thay E calendar-bank design bằng D dynamic-refresh schedule.

**Evidence:** E và D trùng daily path trong tất cả 15/15 development cells và 15/15 confirmation cells. Đây là null do construction, không phải measured economic null của conditional policy.

**Sửa:** E hiện gắn `NOT_IMPLEMENTED_AS_SPECIFIED`; không tính E-D như evidence kiểm định. Implement response/event policy trong continuous runner từng scope; bank refresh và switch clocks độc lập. Positive-control synthetic world phải làm E switch đúng và tạo order path khác khi advantages đủ lớn. No-switch trên market sau khi wiring đúng vẫn là kết quả hợp lệ, không ép nó phải giao dịch.

## A10 — Regime schedule coi model version change là market change và bỏ qua eligibility

**Mức:** P0.  
**Nguồn:** `experiments/regime_schedule.py:107–138`; `regime/registry.py:144–211`; SRC04/SRC25; P03.

Scheduler dùng `(state_namespace, state_id)` làm identity, nên namespace đổi thì coi là transition ngay cả state semantic không đổi. Nó không lọc `decision_eligible` hay `quality_status`. Registry đã viết rõ model-version event không mặc định là market event, nhưng runner không sử dụng distinction đó.

**Reanalysis:** dedupe theo symbol × development/confirmation có 60 cutoffs. 13/60 trùng namespace transition; replicated qua ba alpha là 39/180 selection events. 6/60 cutoffs dùng emission `decision_eligible=false` / UNKNOWN_STATE. Một namespace boundary vẫn có thể trùng market change thật; không thể gọi cả 13 là chuyển đổi kinh tế giả; đó là các events chưa có kiểm chứng mapping đúng.

Scheduler còn chia toàn evaluation range thành 6 bins bằng nhau, lấy first transition mỗi bin, gap>=30d. Cách này có thể là một **hybrid calendar-anchored experiment** hợp lệ nếu preregistered; không tự gọi nó leakage vì biết horizon nghiên cứu. Nhưng nó không kiểm chứng unrestricted online regime-trigger policy như yêu cầu rộng hơn. Nếu không có transition, code raise thay vì giữ incumbent/fallback theo một online state machine.

**Sửa:** phân biệt data/model/market transitions, validate emissions, semantic mapping qua common raw coordinates hoặc descriptor ổn định. Nếu UNKNOWN làm refit trigger, phải là novelty policy riêng có reason, không dùng như state transition im lặng. Calendar-anchored mode giữ làm comparator; actual online mode có minimum-spacing/max-age/budget/risk gates và không ép đủ đúng 6 refits mới được gọi hợp lệ.

## A11 — Response estimator dùng sai đại diện điều kiện thị trường

**Mức:** P0 mục tiêu mô hình; source + mathematical counterexample.  
**Nguồn:** `scripts/run_response_policy.py:78–100`; `regime/emissions.py:201–229`; `policy/response.py`; SRC06–07/SRC10; P04.

`feature_contributions = 0.5*w*(z-mu_selected)^2` là contribution vào **fit error** của model. Response runner lại đưa vector đó vào `features`, sau đó dùng Euclidean/kernel similarity để tìm historical contexts. State ID được lưu metadata nhưng không bổ sung vào distance đang dùng.

Toy hai contexts `z=-2` và `z=+2`, mỗi cái đúng centroid tương ứng: residual vectors đều bằng 0, distance bằng 0. Một downtrend và uptrend rất điển hình có thể bị coi như cùng context. Đây không nói residual hoàn toàn không chứa thông tin; nó nói **residual không bảo toàn economic coordinates, sign hay state identity cần cho bài toán**.

**Sửa:** regime emission phải giữ snapshot raw/standardized causal economic features hoặc reference tới panel immutable, group representation, state namespace/mapping. Fit residual chỉ dùng novelty/quality. Khi so contexts qua model refit, dùng chung transformation được fit ở current valid training cutoff, giữ original decision vintages riêng; không so numeric residuals từ khác scaler như một tọa độ kinh tế chung.

## A12 — Response study bị thiếu support và chưa gắn với deployment thực

**Mức:** P1 lớn; làm kết quả zero-switch khó diễn giải.  
**Nguồn:** `run_response_policy.py:48`, `:223–265`, `:319…`; `policy/response.py:152–188`; `policy/decision.py`; SRC08–10.

Có năm điểm cần tách:

1. Policy chỉ được evaluate riêng cho **A-SC/BTC**, không phải toàn bộ ma trận.
2. Mỗi episode bảy ngày chạy adapter mới trên cửa sổ đã cắt, không cung cấp phần lịch sử warmup trước episode. Engine đóng position ở cuối cửa sổ. Đây là một counterfactual reset-flat theo tuần; không tự phản ánh continuous campaign.
3. `CampaignBook` được tạo rỗng; indicator warmup được đánh READY sẵn. Runner không cập nhật book bằng actual deployment fills. Có module và test campaign không đồng nghĩa experiment sử dụng chúng.
4. `contiguous_blocks` đếm những đoạn rời trong tập episodes mang 90% weights. Một dải nhiều tuần liên tiếp vẫn chỉ là một block và bị từ chối. Khoảng trống giữa các weights không tự xác định tính độc lập thống kê.
5. Transition cost dùng `projected_turnover=1`, trong khi entry allocation là 0,1 account equity. Hurdle khoảng 7 bps cần được đối chiếu với actual transition policy; không thể mặc định đó là chi phí chuyển đổi thực tế của tài khoản.

**Số liệu confirmation:** 46.040 candidate estimates; 45.720 `INSUFFICIENT_SUPPORT` (khoảng 99,3%); 320 supported. Có 5.839 decisions: 5.728 `NO_SUPPORTED_CANDIDATE`, 37 `KEEP_INCUMBENT`, 74 `FALLBACK_NOVEL_STATE`; không có switch. Development cũng không có switch.

Không có nghĩa phải nới thresholds để ép có giao dịch. Nhưng trước khi nói model không tạo lợi thế, cần biết mô hình đang được chấm trên informative episodes hay phần lớn là cold-start/flat observations.

**Sửa:** warm indicators bằng history hợp lệ, rồi bắt đầu episode account theo contract riêng. Giữ reset-flat response và actual-state switching là hai khái niệm. Xây uncertainty theo dependence/time blocks đã đăng ký; không coi số mảnh rời của support weights là số regime độc lập. Chi phí được quy về cùng allocation/horizon và lấy từ transition plan thực. Cuối cùng, nối policy vào E thật rồi mới đánh giá hành vi no-switch.

## A13 — Candidate bank chưa triển khai conditional-specialist admission

**Mức:** P1 về mục đích thí nghiệm.  
**Nguồn:** `run_response_policy.py:126–147`; `policy/bank.py:160–213`; SRC06/SRC11.

Runner đưa robust-score rows vào bank. Bank lọc theo cutoff, sort global R, dedupe theo parameter distance và giới hạn tám candidates. `specialist_note()` mới là mô tả, không phải logic admission. Không có quality-eligibility filtering tương ứng với score-panel verdict trên đường build bank này.

Hai hệ quả có thể cùng tồn tại: một specialist hữu ích bị global ranking loại; một candidate có quality panel không đạt vẫn vào bank nếu xếp hạng đủ cao. Parameter diversity cũng không bảo đảm behavioral diversity, đặc biệt khi HMA có categorical aliases.

**Sửa:** giữ một global anchor và một tập specialists nhỏ có local stability, risk constraints và conditional support. Đo overlap thực của signals, trades, exposure và paired episode ranking. Specialist không nhất thiết thắng ở mọi regime, nhưng vẫn phải qua risk/cost gates. Bank phải lưu thời điểm discovery hợp lệ, actual adapter code hash và indicator readiness. Nếu không tìm thấy các candidates có response đủ khác nhau, đó là kết quả cần báo, không tăng bank vô hạn để tìm winner.

## A14 — Model development và feature ablation chưa chứng minh decision value

**Mức:** P1 methodology.  
**Nguồn:** `scripts/fit_regime_model.py:177–196`; `regime/ablation.py`; SRC24/SRC26; P10.

**Development bị đóng cứng quá sớm.** K=3, lambda=1, observation 4h và fit 28 ngày được giữ như một recipe. Một diagnostic trong development cho K=2 tốt hơn K=3 theo tiêu chuẩn đang dùng, nhưng code không chọn vì lo đổi đăng ký. Không retune confirmation là đúng; học từ development để tạo một design mới rồi freeze trước confirmation cũng chính là quy trình đã duyệt. Điều này không chứng minh K=2 tạo edge.

**Inner validation có preprocessing leakage.** Scaler được fit trên toàn calibration frame trước các inner folds. Inner validation observations có thể ảnh hưởng scale. Vì calibration frame vẫn trước outer boundary, không tự gọi đây là outer-data leakage, nhưng inner comparison không sạch.

**Ablation thay cả target được chấm.** `variance_resolved` trên G1 đo việc giải thích G1; trên G1+G2 đo việc giải thích cả G1+G2. P10 giữ nguyên states và khả năng giải thích một economic target, nhưng thêm noise dimension làm statistic giảm từ 1 xuống 0,5. Điều này không chứng minh nguồn mới không có incremental decision value. Một số panels còn khác coverage: 7.296 và 7.290 observations.

**Model-vintage mapping cần sửa.** Centroids từ các scaler khác nhau đang được so trong standardized coordinates mà chưa đưa về hệ tọa độ chung; greedy mapping có thể many-to-one. Filter khởi tạo lại tại refit mà không warm bằng historical forward state cũng cần contract riêng và đo boundary artifacts.

**Sửa:** fit preprocessing trong từng inner train. Dùng model ladder nhỏ M0/K2/K3 với lambda có nghĩa theo loss units; không mở cuộc thi hàng trăm model. Feature ablation phải dùng cùng cohort và một target cố định, chẳng hạn future paired candidate utility/rank. Reconstruction quality giữ làm diagnostic riêng. Refit state mapping và filter warmup dùng history hợp lệ, không viết đè decision vintages cũ.

## A15 — Minimum economic effect thiếu allocation factor theo chính derivation

**Mức:** P0 inference/economic units; probe P09.  
**Nguồn:** `scripts/close_lab01_blockers.py:52–85`; `configs/minimum_economic_effect.json`; SRC23.

Công thức được lưu:

```text
round-trip cost uncertainty = 2 × (0.0004 + 0.0001) = 0.001
busiest entries/day = 0.064
minimum daily effect = 0.001 × 0.064 = 0.000064 = 0.64 bps/day
```

Nhưng entry notional là 2.000 USDT, initial capital 20.000 USDT. Metric so sánh là **daily return trên account**, không return trên notional của mỗi lệnh. Theo chính cách suy ra cost × turnover đó:

```text
account turnover/day = 0.064 × (2000 / 20000)
account cost-uncertainty return/day = 0.001 × 0.064 × 0.1
                                  = 0.0000064
                                  = 0.064 bps/day
```

Đây là dimensional diagnostic dưới fixed-notional sizing của lab, không phải một MDE phổ quát. Nếu 0,64 bps/day là hurdle kinh doanh được chọn độc lập thì có thể giữ nó, nhưng không mô tả rằng mức đó được suy ra đúng từ allocation/cost đang chạy.

Published 95% CI, theo bps account/day:

- C−A: **[−0,406823; +0,114469]**.
- B−A: **[−0,275585; +0,229622]**.

Cả hai chưa loại được +0,064 bps/day theo derivation đã normalize. Đây không phải evidence positive edge; inputs còn các lỗi khác nên CI cũng phải tính lại. Không dùng phép sửa đơn vị để hạ threshold hậu nghiệm rồi đổi kết luận thành thắng.

**Sửa:** unit-test endpoint/MDE bằng account allocation và turnover thực; đăng ký threshold đúng trước thí nghiệm mới. Giữ threshold cũ như lịch sử đăng ký, thêm corrected derivation và lý do revision; không viết lại registration cũ.

## A16 — Claim hierarchy chưa fail-closed

**Mức:** P0 reporting.  
**Nguồn:** `scripts/analyse_lab09_confirmation.py:880–991`; `configs/lab09_claim_report.json`; SRC27.

Final `FAILED_VALIDITY` là đúng. Nhưng subclaims `RULED_OUT` và `confirms_the_development_outcome=true` vẫn tồn tại dù underlying treatment, metrics hoặc execution chưa hợp lệ. Zero-action policy cũng không thay thế một predictive-validation test của regime features.

**Sửa:** lưu ba chiều độc lập:

```text
execution_validity:
    PASS | FAIL | PARTIAL
implementation_fidelity:
    AS_SPECIFIED | DEVIATED | NOT_IMPLEMENTED
statistical_status:
    NOT_EVALUABLE | INCONCLUSIVE | NEGATIVE_WITHIN_SCOPE | POSITIVE_WITHIN_SCOPE
```

Khi một P0 ảnh hưởng contrast, statistical claim của contrast đó phải `NOT_EVALUABLE`. Giữ raw metrics với invalidation reason; không giấu kết quả âm. Chỉ `RULED_OUT` khi experiment hợp lệ, threshold đúng và evidence đủ để loại mức lợi ích đã đăng ký.

---

# 5. Data, tests và transparency còn thiếu gì?

## 5.1 ZIP không chứa raw data cần cho full market reproduction

Có snapshot manifest và source/wheels, nhưng không có raw market/feature Parquet đầy đủ để chạy lại experiments. Audit này đọc artifacts và chạy toy/reference probes, không tái chạy toàn backtest nhiều năm.

LAB-10 nên ghi `REPRODUCTION_BUNDLE_INCOMPLETE` cho phần đó. Không cần chuyển toàn storage: một pilot pack có raw 1m, features, versions và config của một alpha/symbol đủ để tái hiện các lỗi integration; full experiments có thể chạy lại trên server của người dùng bằng runner đã pin.

## 5.2 Requirement coverage không đồng nghĩa semantic proof

196 existing tests pass là điểm tích cực. Hai failures trong môi trường audit là do hardcoded venv executable không tồn tại, không phải financial assertions thất bại.

Tuy nhiên, probes mới cho thấy test hiện có bỏ lọt những behavior quan trọng. Một assertion rằng artifact tồn tại hoặc report chứa đúng thuật ngữ không chứng minh actual runner sử dụng đúng policy.

Cần mutation tests có chủ đích: fee bị chia đôi, first params bị backdate, model-label permutation, ineligible emission, ignored amendment, fill-price mismatch cùng bar, dropped episode-boundary PnL. Test suite phải fail với từng mutation. Không thay tests semantic bằng việc tăng số checklist items.

## 5.3 Trial ledger cần phân biệt optimizer history và unique evaluations

Calendar discovery cache duplicate params để trả objective cho TPE, nhưng không phải mọi duplicate trial đều có trong unique-evaluation rows. Runtime failure có đường trả −1e9, khiến optimizer có thể ghi COMPLETE thay vì FAIL và học từ failure như một financial outcome.

Cần ba identities: `trial_id`, `evaluation_id`, `candidate_id`. Xuất toàn bộ `study.trials`, kể cả duplicate, pruned và failed. Reused evaluations có references riêng. Không biến lỗi runtime thành lỗ kinh tế; không cache một failed execution thành score hợp lệ.

## 5.4 Response artifact được sampling chưa đủ để kiểm tra toàn quyết định

Artifact confirmation có tổng 46.040 estimates, ghi sample count 4.000 nhưng actual retained response rows là 400. Sample sớm gồm các cases thin-support; 320 estimates supported về sau không có đầy đủ toàn candidate weights trong phần retained này. Decision ledger có một số winner/reason details, không thay thế complete estimate panel.

Sampling được phép nếu được gọi đúng tên. Cần actual count, sampling policy và references đủ để recompute. Với mỗi quyết định, phải truy được candidates, episode weights, utility, uncertainty, cost và lý do keep/switch. Không dùng hash để thay data mà hash không tái dựng được.

## 5.5 Instrument registry và venue claims

Registry suy từ samples hữu ích cho sanity checks nhưng không tự là historical exchange tick/lot/min-notional authority. Fixed-notional intrabar bridge cũng không mặc định enforce toàn metadata trong registry.

Funding bị tắt đã được disclose. Vì vậy chỉ claim kết quả theo registered no-funding economics, không gọi nó venue-exact perpetual hoặc spot-cash result. Không mở rộng thêm Vietnam/Deribit để xử lý những lỗi này; giữ scope crypto đã thống nhất.

## 5.6 Bốn alpha và mười phase chưa được đóng đầy đủ

A-HASH có năm cells NOT_READY nên chỉ 15/20 cells thực chạy. Đây là cách xử lý trung thực; không được ép PnL=0. Nhưng cũng không phát hành kết luận đại diện cả bốn alpha.

Tiếp tục làm ladder/partial-fill adapter trong khả năng package đã có, hoặc thu hẹp scope claim. `CLAUDE.md` còn đoạn “only implementation guide, no code” đồng thời có phần mô tả nhiều phases complete: cần dọn documentation drift. Handoff hiện chưa đủ để xác nhận LAB-10 hoàn tất.

---

# 6. Trả lời ba nghi vấn chính của người dùng

## 6.1 Model regime chưa đủ?

Có những thiếu sót đáng sửa, nhưng chưa thể xếp hạng chất lượng model trên thị trường từ kết quả này. Wrong response coordinates và namespace trigger là lỗi semantic integration, không phải bằng chứng phải thay JM bằng một model lớn hơn.

Feature ablation hiện không dùng fixed prediction target. Response chỉ chạy một cell và bị thiếu support. E chưa thực thi đúng. Do đó chưa chứng minh rằng JM hoặc dữ liệu derivatives không có information value. Cũng chưa có bằng chứng thêm whale/on-chain data sẽ tạo edge.

## 6.2 Cách tính toán, đánh giá chưa chuẩn?

**Có, được xác nhận.** Fee binding, first-param timing, convergence, unmapped intents, HMA search categories, episode returns, MDE units và baseline/E wiring đều có source hoặc probes cụ thể.

Những lỗi này có thể làm kết quả tốt lên hoặc xấu đi; không suy dấu tác động từ trực giác. Cần corrected rerun để đo. Ví dụ, phí thấp có thể ưu ái params turnover cao, còn backdating một bộ params có thể giúp hoặc hại tùy path.

## 6.3 Có thể thực sự không có edge không?

**Có. Khả năng này vẫn phải được chấp nhận.** Sau khi sửa, nếu bank không có rank reversals hữu ích, model không dự báo được relative utility ngoài mẫu, hoặc switching costs ăn hết lợi ích, kết luận âm trong phạm vi đã thử là đúng.

Không được chạy lại vô hạn đến khi thắng. Data windows đã dùng để chẩn đoán hoặc chỉnh thiết kế nay là development/exploratory; không tiếp tục gọi chúng untouched confirmation. Thiết kế mới cần được freeze và đánh giá với lineage trung thực, hoặc prospective khi không còn holdout chưa xem.

---

# 7. Hướng cải thiện theo thứ tự

## R1 — Đóng economic, callback và temporal correctness trên một pilot

Giữ QuantBT production read-only. Bắt đầu một alpha/symbol và một interval ngắn nhưng có đủ fills, gaps và transitions, không chạy toàn ma trận nhiều năm ngay.

- Unit-test one-way fee; account/funding contract rõ.
- Decision bars và 1m execution clock tách; chỉ dùng closed higher-timeframe observations.
- Actual engine fills/rejects cập nhật adapter state; không chế tạo feedback rồi hòa giải bằng bar sets.
- Mọi intent có handling hoặc explicit rejection; unsupported chặn candidate.
- HMA enum đúng, VWAP amendment đúng; A-HASH là một adapter workstream riêng.
- Initial incumbent chỉ dùng thông tin trước deployment; ready-time và activation phase được enforce.
- Episode PnL partition reconcile toàn path.
- Không có score khi execution, mapping hoặc trace validation chưa đạt.

**Exit:** fixed-params/regime-off và disabled-hooks parity; actual fee/fill/account fixtures; future-suffix mutation không đổi quyết định trước cutoff. Không cần alpha profitable để pass.

## R2 — Khôi phục đúng các arms đã duyệt

- `A_public`: đúng QuantBT WFO configuration của người dùng; `A_custom_argmax` giữ như control riêng.
- B: independent neighbors, cùng economics/budget và comparable incumbent guard.
- C/D: online trigger hợp lệ, không lấy model version làm market transition, không dùng ineligible emissions.
- E: actual response policy theo từng cell; bank refresh như B, switching riêng; không copy D.
- Kiểm từng đường từ observation tới actual affected order, không chỉ helper unit tests.
- Matched budget phải đếm discovery, probes, episode-bar visits, model fits và response evaluations, không chỉ số lần refresh.

**Exit:** synthetic positive control chứng minh policy có thể đổi params và execution khi advantage đủ rõ; null control kiểm tra false discoveries. Market zero-switch sau wiring đúng vẫn là một kết quả hợp lệ.

## R3 — Xác định cơ hội chọn params trước khi nâng model

Xây bảng `candidate × completed episode` bằng execution đúng, cùng initial-state/horizon contract. Tính paired advantage:

`ΔU(e,c) = U(e,c) − U(e,incumbent)`.

Trả lời lần lượt:

1. Candidates có thực sự khác về signals, trades, exposure và holding behavior không?
2. Có rank reversals tái diễn hay một candidate thắng phần lớn mọi khoảng?
3. Context available tại decision time có giải thích/dự báo những reversals đó ngoài mẫu không?
4. Tổng detection, search và activation delay có nhỏ hơn horizon lợi thế không?

Bank giữ global anchor và conditional specialists đủ local/risk evidence. Response dùng economic coordinates, không fit residual làm context. State labels có thể là input, nhưng continuous-context comparator cần có để kiểm tra việc nén thành labels có làm mất information không.

**Exit:** opportunity/information/decision-value diagnostics rõ; không bắt buộc có edge.

## R4 — Development có kiểm soát cho response, support và cadence

4h inference, 28d retrain và 7d episodes là starting hypotheses, không phải những hằng số đã chứng minh tối ưu.

- Chọn 2–3 horizons dựa trên holding/campaign diagnostics trong development.
- Warmup đúng lịch sử; reset-flat outcomes không bị nhầm với current-state transition value.
- Báo weighted ESS, temporal coverage, activity và regime episodes riêng; uncertainty không dựa vào một số gappy fragments tùy ý.
- Transition costs dựa trên actual state/leg plan và cùng allocation units.
- Inner preprocessing fit trong train; dùng một model ladder nhỏ và lambda phù hợp loss scale.
- Data ablation cùng cohort, cùng prediction target; reconstruction statistics chỉ là diagnostic.

**Exit:** design-selection manifest, full attempted-hypothesis ledger. Thua baseline là một outcome được phép, không phải lý do âm thầm thay alpha hoặc cắt cells.

## R5 — Continuous policy simulation và controls

Trong mỗi arm, account, orders và campaign state liên tục. Existing protection giữ old params hoặc chuyển theo một policy đã đăng ký; không nối phần đẹp của expert curves.

Controls cần có: same-bank calendar, state-placebo có structure tương đương, delayed state, matched cadence và risk-only. E không được dùng bank tốt hơn baseline rồi quy toàn lợi ích cho regime timing.

Đo riêng recommendation, approval, indicator readiness, activation và first affected order. Report net switching gain, lost opportunity do delay, no-supported rate, cost/turnover, conditional rank và continuous PnL/risk.

## R6 — Inference, evidence và handoff mới

- Validity gate đứng trước statistics; invalid contrasts là NOT_EVALUABLE.
- Sửa units, đăng ký effect threshold mới trước results; giữ historical registration bất biến.
- Common-date paired comparison, dependence-aware uncertainty và multiple-comparison scope rõ.
- Mọi trial/decision/evaluation có identity và status; artifact sampling phải disclosure.
- Không overwrite kết quả cũ: thêm `invalidated_by` và `superseded_by`.
- Những periods đã mở không đổi tên thành untouched sau khi sửa method.
- Tối ưu Rust hoặc mua paid data sau khi measurement pipeline đúng, không dùng để trì hoãn correctness.

---

# 8. Mapping plan với implementation

| Phase | Đáng giữ | Cần đóng lại |
|---|---|---|
| LAB-01 | Isolation, registration, budgets, manifests | MDE units, source/import identity, evidence-role consistency |
| LAB-02 | Adapters, HASH blocked trung thực, reference tests | Actual fills, fee, HMA enum, VWAP amendment, 1m execution |
| LAB-03 | Snapshot metadata và availability layers | Reproduction data pack, actual registry enforcement, matched cohorts |
| LAB-04 | Neighborhood probes và schema geometry | Actual WFO baseline, episode PnL, invalid-run rejection, complete trial ledger |
| LAB-05 | JM DP/reference, model artifacts | Namespace consumer, inner scaler, discovery/model selection, fixed-target ablation |
| LAB-06 | Decision reasons, clocks modules, zero-switch disclosure | Context representation, bank admission, weekly warmup, support/cost units, full matrix |
| LAB-07 | Continuous-account architecture và parameter log | Backdated initial, ready time, fabricated fills, weak convergence, ignored follow-ups |
| LAB-08 | 15 real cells và 5 explicit NOT_READY | E wiring, dynamic-schedule scope, invalid arms, actual compute matching |
| LAB-09 | Paired daily framework, fee defect detected, final FAILED_VALIDITY | Invalid subclaims, threshold units và inherited execution defects |
| LAB-10 | Một số handoff/docs | Full reproducibility/qualification chưa hoàn tất |

Một lỗi integration có thể ảnh hưởng nhiều phases. Không sửa bảng này bằng cách bổ sung assertions về sự tồn tại của files; phải sửa actual public path.

---

# 9. Evidence mới do audit tạo

## 9.1 Probe register

| ID | Kết quả | Loại kiểm tra |
|---|---|---|
| P01 | `fee=.0004` thực thu `.0002/side` | Actual supplied QuantBT reference API, synthetic bars |
| P02 | Initial requested bar100 nhưng active từ0 | Actual continuous runner/HMA, synthetic bars |
| P03 | Same state, new namespace, ineligible vẫn trigger | Actual scheduler, synthetic emissions |
| P04 | Economic contexts −2/+2 thành response vectors 0/0 | Actual emission/response helpers, mathematical toy |
| P05 | Ba HMA choices đều về mode 1 | Actual schema/adapter mapping |
| P06 | Nonconverged + unmapped vẫn EVALUATED | Actual acceptance function với injected bad result |
| P07 | Exit cùng bar nhưng giá80/120 vẫn converged | Actual run_candidate với injected sweep/engine mismatch |
| P08 | Loss1.000 tại boundary biến mất khỏi episode returns | Actual episode_metrics, synthetic equity |
| P09 | Cost-derived MDE thiếu hệ số allocation0,1 | Recalculation từ registered constants và artifact CIs |
| P10 | Ablation statistic đổi vì target feature space đổi | Actual variance_resolved, synthetic fixed labels |
| P11 | Follow-up corrective EXIT không được consume | Actual sweep với stub adapter |
| P12 | Ready bar10 không được dùng, request tại cutoff5 | Actual schedule function, synthetic records |

P06/P07/P11 chủ ý dùng mocks/stubs để kiểm tra contract holes. Không nói giá80/120 hoặc quantity20 đó đã xuất hiện trong market run. Counts từ real artifacts như nonconvergence, unsupported configs và E=D được ghi riêng.

## 9.2 Artifacts bàn giao

- `evidence_reanalysis.json`: cell coverage, E=D, nonconverged arms, selected configs và response statuses.
- `transition_audit.json`, `trigger_eligibility_audit.json`: actual cutoffs, namespace và eligibility.
- `jsonl_row_counts.json`: record counts; không phải semantic certificate.
- `audit_probe_results.json`, `additional_probe_results.json`: 12 probe outputs.
- `pytest_subset.log`: 196 pass và hai environment-path failures; không phải full-suite run.
- `archive_inventory.json`, `artifact_index.json`, `source_excerpt_manifest.json`: source/artifact identities.
- `REGIME_LAB_SOURCE_EXCERPTS_VI.md`: 27 excerpts với source-line numbers và SHA-256 toàn file.

## 9.3 Cách chạy lại probes

Scripts trong bundle nhận source/output paths qua environment. Dùng environment cô lập có NumPy, Pandas, Numba, Optuna và Pytest; reference candidate package đã có trong snapshot. Không cần raw market data để chạy các probes nhỏ.

```bash
export REGIME_LAB_ROOT=/absolute/path/to/regime-lab-main
export REGIME_AUDIT_OUT=/absolute/path/to/new_audit_output
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMBA_CACHE_DIR="$REGIME_AUDIT_OUT/numba_cache"
mkdir -p "$REGIME_AUDIT_OUT"
python audit_probes.py
python additional_probes.py
```

Scripts không tự cài dependencies, không gọi APIs và không sửa source. Môi trường audit hiện tại là Python3.13, chưa chạy được native wheel cp312 kèm archive. Market rerun phải dùng đúng environment, artifacts và snapshot trên server; toy passes không phải native/performance certification.

---

# 10. Quyết định đề nghị

**Giữ evidence cũ, sửa claim và sửa pipeline trước model.** Không cần phá toàn bộ lab hoặc bỏ hết công việc của Claude.

Tôi đề nghị:

1. Thêm invalidation manifest cho các contrasts bị ảnh hưởng, không xóa kết quả âm.
2. Giữ final FAILED_VALIDITY và hạ các subclaims chưa hợp lệ về NOT_EVALUABLE.
3. Sửa economics, decision availability, response representation và actual E wiring trước khi thêm nguồn dữ liệu/model mới.
4. Tái sử dụng những phần safety, data, JM reference và evidence infrastructure đã làm tốt.
5. Sau repaired pilot, chạy một controlled discovery mới; chỉ sau đó quyết định có hypothesis nào đủ triển vọng cho confirmation.

Câu hỏi cần trả lời là:

> Với candidates thực sự có response khác nhau, thông tin available tại decision time có dự báo được relative advantage đủ tốt để chọn và activate params trước khi cơ hội qua đi, trên một continuous account có costs đúng hay không?

Snapshot hiện tại **chưa trả lời hợp lệ câu hỏi đó**. Nó có nhiều hạ tầng nghiên cứu hữu ích và một kết quả âm đã tự cảnh báo, nhưng còn các lỗi tái hiện được khiến không thể dùng để bác bỏ ý tưởng regime-aware parameter timing.
