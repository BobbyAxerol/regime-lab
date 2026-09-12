# REGIME-LAB — PHẢN BIỆN TỔNG HỢP VÀ KẾ HOẠCH SỬA / KIỂM CHỨNG 5 PHASE
## Mode 4 `per_fold_causal`: Calendar WFO so với Regime-aware WFO trên alpha thật, QuantBT 1.1.1

**Đối tượng thực hiện:** Claude và OpenCode.  
**Ngày hợp nhất:** 11/09/2026.  
**Phiên bản tài liệu:** Corrective Study V3 — đây không phải version package QuantBT.  
**Source đã audit:** ZIP `regime-lab-main.zip` do người dùng cung cấp; không suy ra trạng thái GitHub mới hơn.  
**SHA-256 archive:** `2765bd069a5caf16921c3df03dfafd8f090f4fdd2de5e1550a5ce390c87a980f`.  
**Baseline engine:** QuantBT 1.1.1; companion native 0.4.2 phải được xác minh từ distribution thực, không chỉ tên thư mục.  
**Trạng thái hiện tại:** có findings source và probes đã tái hiện; **chưa có corrected market rerun**, chưa chứng minh có hoặc không có time edge.

> **Nhiệm vụ:** sửa các sai lệch đã phát hiện, sau đó trả lời một câu hỏi chính: *Với cùng bốn alpha thực, cùng economic contract, cùng Mode 4 train-only selector và cùng training-memory rule, lựa chọn thời điểm refit bằng regime causal có cải thiện kết quả ngoài mẫu và giảm decay so với calendar `per_fold_causal` WFO hay không?*
>
> **Không đặt nhiệm vụ “phải chứng minh regime thắng”.** Phải tạo một phép thử có khả năng phát hiện edge nếu nó tồn tại, cũng có khả năng loại mức lợi ích kinh tế đã đăng ký nếu evidence đủ. Pipeline sai hoặc treatment chưa được thực hiện phải cho `NOT_EVALUABLE`, không cho `NO_EDGE`.

---

## Cách đọc và thứ tự ưu tiên của tài liệu

Tài liệu này là **một đầu vào duy nhất** thay cho ba file audit rời. Phần chính là chỉ dẫn mới để làm tiếp; phụ lục bảo toàn tài liệu audit, source excerpts, probe code/results và toàn bộ members của evidence ZIP. Hai JSON kiểm kê lớn được nén lossless trong Markdown để tránh lấp phần hướng dẫn; có utility trích xuất, kiểm hash và **không tự chạy code** ở cuối.

Thứ tự áp dụng khi có mâu thuẫn:

1. Phạm vi và rules mới trong phần chính của tài liệu này.
2. Economic/availability/correctness contracts đã được xác minh trên snapshot/candidate hiện tại.
3. Findings A01–A16 và các supplementary findings trong tài liệu này.
4. Các bản audit/excerpts/probes trong phụ lục — **evidence lịch sử bất biến**, không phải instructions mới để tiếp tục bridge sai.
5. Guide Final V2 cũ chỉ còn hiệu lực ở phần không bị thay thế và không mâu thuẫn.

Đặc biệt: “chạy mọi alpha bằng event engine bất kể capability”, “bắt đủ đúng sáu dynamic refits”, và “E có thể copy lịch D vì policy từng không switch” **không phải yêu cầu mới**. Không sửa Markdown để hợp thức hóa implementation sai. Mọi deviation phải có lý do, scope, consequence và disposition thực.

### Nội dung chính

- [1. Kết luận phản biện và những gì phải giữ](#1-kết-luận-phản-biện-và-những-gì-phải-giữ)
- [2. Mục tiêu Mode 4 và thiết kế so sánh](#2-mục-tiêu-mode-4-và-thiết-kế-so-sánh)
- [3. Source QuantBT đã kiểm tra thêm khi hợp nhất](#3-source-quantbt-đã-kiểm-tra-thêm-khi-hợp-nhất)
- [4. Đăng ký toàn bộ lỗi và corrective actions](#4-đăng-ký-toàn-bộ-lỗi-và-corrective-actions)
- [5. Endpoint routing: nhanh nhưng không đổi alpha](#5-endpoint-routing-nhanh-nhưng-không-đổi-alpha)
- [6. Metrics, fold decay và cách suy luận time edge](#6-metrics-fold-decay-và-cách-suy-luận-time-edge)
- [7. Dữ liệu, regime và timing policy](#7-dữ-liệu-regime-và-timing-policy)
- [8. Tăng tốc thí nghiệm và quản lý ngân sách](#8-tăng-tốc-thí-nghiệm-và-quản-lý-ngân-sách)
- [9. Năm phase triển khai](#9-năm-phase-triển-khai)
- [10. Rules báo cáo cho từng phase](#10-rules-báo-cáo-cho-từng-phase)
- [11. Bộ kiểm thử nghiệm thu](#11-bộ-kiểm-thử-nghiệm-thu)
- [12. Handoff, claim và điều kiện kết thúc](#12-handoff-claim-và-điều-kiện-kết-thúc)
- Phụ lục: source verification mới, bản audit/excerpts nguyên văn, evidence archive hợp nhất, utility khôi phục.

---

# 1. Kết luận phản biện và những gì phải giữ

## 1.1 Kết luận về snapshot đã gửi

Audit trước đã phát hiện A01–A16 bằng source, evidence hoặc probes có loại kiểm chứng rõ. Bộ số liệu hiện tại **không hợp lệ để loại trừ time edge**: phí sai, initial params backdate, actual fill feedback không làm authority, HMA categories collapse, utility mất PnL tại boundary, E được dựng bằng D, scheduler đọc namespace như market transition và response dùng squared residual thay economic context.

Claude đã tự ghi `FAILED_VALIDITY`, phát hiện fee mismatch và công khai A-HASH chưa sẵn sàng. Giữ các disclosure tốt đó. Sai ở chỗ một số subclaims vẫn `RULED_OUT` hoặc xác nhận lại development dù economic/treatment validity đã fail. Không mô tả đây là che giấu hay quy động cơ cho tác giả.

Các con số audit lịch sử cần giữ nguyên nghĩa:

| Evidence | Kết quả đã quan sát | Không được suy thêm |
|---|---|---|
| Files | 1.893 files trong working copy audit; 859 JSON; 571 JSONL / 5.634 rows parse được | Parse được không có nghĩa semantic pass |
| Existing test subset | 196 pass; 2 fail vì executable venv hardcoded không có | Không phải full-suite/native-wheel certificate |
| Independent probes | 12 probes synthetic/reference/mocked có source thật | Không phải backtest thị trường mới |
| Matrix | 15/20 alpha-symbol cells thực chạy; A-HASH NOT_READY | Không đại diện toàn bộ bốn alpha |
| E và D | Cùng daily path ở 15/15 cells development và 15/15 confirmation | Null do construction, không phải response policy thất bại ngoài mẫu |
| Response | 45.720/46.040 estimates thiếu support; 0 switches | Không tự chứng minh không có parameter opportunity |
| Native wheel | Archive có cp312 wheel; audit trước chạy Python 3.13 reference | Không claim Rust execution đã được audit ở môi trường đó |

Các file/probe/hash đầy đủ nằm trong phụ lục. Không cần internet để đọc phản biện này; full market reproduction vẫn cần snapshots được chỉ ra trong manifest trên server.

## 1.2 Tái sử dụng, không làm lại toàn bộ

Giữ safety/data snapshot infrastructure, JM reference/DP tests, schema geometry, phần independent-neighborhood validation đúng, artifact writers và paired-comparison framework có thể sửa. Tập trung thay **bridge tự đoán fills, runner wiring, availability, unit/metric handling và claim gates**.

Không viết matching/accounting engine thứ hai trong lab. Mọi net returns, positions, fees, margin, liquidations và actual fills dùng để kết luận phải đến từ QuantBT. Lab được viết model regime, scheduling, adapters, statistical analysis và independent tiny oracle cho tests; **oracle test không được trở thành production evaluator thay QuantBT**.

## 1.3 Rules an toàn và phạm vi alpha/data

- Chỉ sửa một working copy/lab branch mới được phép. QuantBT chính, alpha originals, các alpha ngoài bốn file và production storage là read-only.
- Không dùng hardlinks cho bản mutable, không `pip install -U` trong production venv, không chạy jobs với quyền write vào data root.
- Không copy/run `.venv` trong ZIP. Environment mới, pin actual packages/lockfiles/import origins. Python source của lab và QuantBT được phân biệt bằng distribution/module hashes.
- Bốn alpha: `signal_combine.py` (A-SC), `adaptive_hma_cpp.py` (A-HMA), `vwap.py` (A-VWAP), `hash_momentum.py` (A-HASH). Giữ raw → canonical → optional research revision thành version riêng.
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT. Spot từ 01/01/2020 được coi sạch theo quy ước người dùng; bắt đầu sau listing/coverage/warmup thực, không fabricate trước listing.
- Dữ liệu giàu hơn trên server dùng khi availability/coverage đủ. Không mở lại dự án mua data, Vietnam, Deribit hoặc native core rewrite trong năm phase này.
- Presets full-set TPE là `RETROSPECTIVE_REFERENCE_ONLY`. Không warm-start fold quá khứ bằng winners đã nhìn tương lai; search-space prior contamination phải được disclose.

---

# 2. Mục tiêu Mode 4 và thiết kế so sánh

## 2.1 Khóa mục tiêu chính, không tráo sang Mode 1/Mode 5/argmax

Cấu hình logic bắt buộc:

```text
optimization_mode       = mode_4_is_only_robust
optimization_schedule   = per_fold_causal
candidate_selection_metric = is_only_robust
scoring_backend         = endpoint
calendar_contract       = exact_v2
```

Các giá trị trên đã tồn tại trong source QuantBT của ZIP; xem VFY01–VFY03 trong phụ lục source verification mới. `per_fold_causal` là chính tả API; không dùng `per_fold_casual`.

Mode 4 là **train-only selection tại từng cutoff**, gồm temporal robustness và plateau logic của implementation đã pin. Không gắn nhãn Mode 4 cho việc tự tạo `WalkForwardTrialRecord` với mean utility điền vào trường Sharpe rồi gọi một private default selector. Không dùng future OOS decay để xếp candidate trong primary study.

Điều đang thử là **timing policy**, không phải một optimizer khác. Nếu phát hiện correctness bug ở Mode 4, sửa có version, chứng minh repair và áp dụng cùng repair cho cả hai arms; keep raw legacy reproduction riêng. Mật độ top-TPE/geometry có thể chưa là robust selector lý tưởng, nhưng không tự sửa nó chỉ ở regime arm.

## 2.2 Arms mới — tên riêng để không nhầm historical A/B/C/D/E

| ID mới | Selector/evaluator | Refit timing | Vai trò |
|---|---|---|---|
| `M4_CAL` | QuantBT Mode 4 thực, same schema/objective | Calendar đã freeze | Baseline chính |
| `M4_REGIME` | Cùng Mode 4, cùng evaluator/settings | Online regime-triggered schedule | Treatment chính |
| `M4_CAL_MATCHED` | Cùng Mode 4 | Calendar cadence/budget chọn trên development để tương đương | Tách ích lợi thông tin khỏi compute/refit frequency |
| `M4_CAL_NEIGH` | Mode-4-derived selector extension có independent probes | Như M4_CAL | Secondary selector study, không gọi stock Mode 4 |
| `M4_REGIME_NEIGH` | Cùng extension với M4_CAL_NEIGH | Như M4_REGIME | Secondary selector × timing interaction |
| `E_RESPONSE_V2` | Candidate bank + conditional response thật | Inference/switch/bank-refresh tách | Secondary; tuyệt đối không copy treatment khác |

**Phải hoàn thành cặp M4_CAL/M4_REGIME trước.** Không chạy toàn factorial × mọi model × mọi horizon trong vòng đầu. Các arms phụ chỉ mở sau validity và primary pilot; nếu E chưa sửa xong, nó phải disabled, `NOT_IMPLEMENTED_AS_SPECIFIED`, không có economic-null claim. Đây là reprioritization theo yêu cầu mới, không phải tự tuyên bố A09/A11–A13 đã được sửa.

Các chênh lệch được đo:

```text
Timing:       M4_REGIME − M4_CAL
Budget-aware: M4_REGIME − M4_CAL_MATCHED
Selector:     M4_CAL_NEIGH − M4_CAL
Interaction:  (M4_REGIME_NEIGH − M4_CAL_NEIGH)
              − (M4_REGIME − M4_CAL)
```

Risk-only, same-bank/calendar, delayed-state và placebo là controls có thứ tự; không tự mở tất cả cùng lúc. Nếu chỉ giảm exposure tốt hơn thì báo `RISK_TIMING_CONTRIBUTION`, chưa gọi `PARAMETER_SELECTION_EDGE`.

## 2.3 Những thứ phải giống giữa primary arms

Giữ cùng alpha semantic version, param schema/constraints, TPE settings, seeds policy, Mode 4 knobs, training-memory length, warmup/purge/embargo rules, initial account, fee/slippage/funding, sizing, market snapshot, permitted source coverage, route/economic contract, output retention và evaluation dates. Khác chủ yếu ở **cutoff do schedule sinh ra** và hệ quả causal của cutoff đó.

Các lần refit khác nhau có thể tạo candidate sets khác nhau vì training information khác; đó là hệ quả hợp lệ của timing. Không ép cùng candidates được discovered từ tương lai vào mọi cutoff để “fair”. Dùng same-cutoff synthetic/fixed-schedule harness để kiểm selector equivalence; dùng seed replicate block để đo variability của optimization thực.

Calendar comparator không được chọn cadence bằng cách xem toàn future realized regime schedule. Có thể so equal maximum budget với một calendar chọn trong development; realized resource use có thể khác và phải được báo. Một phân tích dùng future-refit count để match hồi cứu chỉ là diagnostic, không phải live-feasible control.

## 2.4 Continuous deployment khác candidate scoring

Training candidate có thể được QuantBT score từ fresh/reset account theo Mode 4 contract. Deployment trong mỗi arm là **một account liên tục**. Không nhân/ghép independently normalized fold equities thành carried-account result.

Hai operational segments có end dates khác nhau giữa arms. Reporting/paired statistical comparisons dùng cùng market clock; không so fold #3 của A với fold #3 của B như thể chúng cùng thời gian.

---

# 3. Source QuantBT đã kiểm tra thêm khi hợp nhất

Đã đọc trực tiếp `quantbt_candidate/quantbt` trong ZIP. Những facts sau là **static source verification trên snapshot**, chưa phải native runtime benchmark mới. Hash và excerpt ở phụ lục VFY.

| ID | Quan sát source | Hệ quả thực thi |
|---|---|---|
| VFY01 | `QuantBTEndpoint.pct_equity()` tạo factory legacy; có `_run_pct_equity_transition_native()` opt-in | Không mặc định factory name đồng nghĩa Rust/native fast route |
| VFY02 | `walk_forward()` có Mode 4 + per_fold_causal + endpoint scoring | Phải gọi pipeline này hoặc reuse đúng instance/hooks, không tự thay optimizer |
| VFY03 | `_run_per_fold_schedule` gọi `optimize_params(... evaluate_oos_candidates=False)` cho Mode 4 causal | Selected params phải freeze trước outer OOS; post-selection scoring chỉ reporting |
| VFY04 | Native prepared WFO mặc định `off`; `pct_equity` native scoring yêu cầu `native_prepared_wfo='require'` và `target_runtime='rust'` | Cần kiểm imported extension/capabilities/counters, không bật giả metadata |
| VFY05 | Prepared public scorer dùng `_RUST_DIRECT_TIMING='close_target_v2_same_close'` | Không quảng cáo đây là next-open execution; shift một series không tự đổi close thành open |
| VFY06 | `%_equity` Rust compatibility yêu cầu one-way `fee_rate == fee / 2` | Bind fee theo route và golden fills; không dùng một mapping cho mọi endpoint |
| VFY07 | Standard `profit_factor` tính trên `stats_returns`; không phải trade-ledger PF | Giữ metric gốc, đặt label đúng; trade PF là field bổ sung có definition riêng |
| VFY08 | Outer Mode 4 `candidate_decay` là IS−OOS metric; OOS metric có thể trừ trade-frequency penalty | Giữ raw metrics và penalized optimizer metrics riêng |
| VFY09 | `build_folds` hỗ trợ calendar frequencies, không có keyword regime universal | Dynamic schedule cần thin lab-only fold provider/hook, reuse engine optimize/evaluate; không bịa API |
| VFY10 | `prepare_reactive_walk_forward` source mô tả reset-flat accounts per fold | Không dùng output này như carried live account; final stateful deployment phải có execution riêng hợp lệ |
| VFY11 | Prepared scorer có fields `turnover=report_trade_count`, `mean_return=total_return`, `volatility=0` compatibility | Không diễn giải field aliases như quote turnover, daily mean hoặc volatility đã đo; resolve units/source cho report |

### Hai ví dụ binding để agent hiểu đúng, không phải launcher chạy nghiên cứu

Các keyword dưới đây hiện diện trong snapshot. Strategy signature, signal timing, economic configs, search ranges và native capability **phải được qualify trước**. Không lấy block này làm bằng chứng một alpha fill-dependent đã vectorize được.

```python
# Configuration sketch sử dụng keyword có thật; chưa phải executed experiment.
wf_options = {
    "scoring_backend": "endpoint",
    "candidate_selection_metric": "is_only_robust",
    "native_prepared_wfo": "require",    # chỉ sau capability qualification
    "native_prepared_wfo_workers": 1,    # tăng có benchmark/budget, không nested oversubscription
    "prepared_wfo_strategy": "auto",    # require chỉ khi alpha có protocol thực
    "use_prepared_scoring_cache": True,
    "use_prepared_wfo_context": True,
    "use_scalar_trial_scoring": True,
    "compact_trial_ledger": True,
    "profile_walkforward": True,
    "scoring_trading_days": 365,
}
# Factory target:
# QuantBTEndpoint.walk_forward(
#     strategy_class=VerifiedStrategyAdapter,
#     target_mode="pct_equity",
#     optimization_mode="mode_4_is_only_robust",
#     optimization_schedule="per_fold_causal",
#     optimization_config=wf_options,
#     target_runtime="rust",
#     ... actual frozen economic and calendar config ...,
# )
```

`research_retention` phải được resolve từ enum/schema **thực** trong package và bật full trial ledger. Không chép một tên enum từ guide cũ rồi để fallback `none`. `compact_trial_ledger=True` không phải quyền bỏ trials hoặc objective components.

Một sample legacy binding có thể cần `fee=0.0008` và `fee_rate=0.0004` để thực thu 4 bps/side; phải verify bằng fill notional actual. Event API có thể nhận trực tiếp `fee_rate`; không nhân đôi tiếp. Slippage phải ghi rõ decimal/bps và translation đúng một lần. Không đặt một con số chung cho account/perp/spot khác semantics.

---

# 4. Đăng ký toàn bộ lỗi và corrective actions

## 4.1 Findings A01–A16: mandatory disposition

Bảng này tóm tắt hành động; full rationale/probes/excerpts không bị mất và nằm ở phụ lục. Source locations thuộc snapshot cũ; agent phải map sang file/line hiện tại và report `PRESENT`, `ALREADY_FIXED_WITH_PROOF` hoặc `SUPERSEDED_PATH_QUARANTINED`. Không tự bỏ finding vì code đã rename.

| ID | Vấn đề / evidence | Sửa đúng | Test bắt buộc / phase |
|---|---|---|---|
| A01 | Fee một chiều truyền vào legacy round-trip, thực thu một nửa; P01/SRC12–13 | One-way economic config → endpoint-specific binding; golden fee/fill. Rerun search lẫn deployment | Flat-price round trip, turnover-sensitive selection; RF-01/02 |
| A02 | First future-selected version active từ bar 0; ready time bị bỏ; P02/P12/SRC01–02 | Initial incumbent phải known trước start; mọi update pending, effective sau cutoff/ready/warm boundary | Delayed initial, cutoff vs ready, suffix mutation; RF-01/02 |
| A03 | Convergence so bar sets, ignored qty/price; nonconverged/unmapped vẫn EVALUATED; P06/P07 | Loại fixed-point evaluator khỏi active path; strict runtime status; invalid không được objective hợp lệ | Same bar different price/qty/reject, failure handling; RF-01/02 |
| A04 | Fabricated adapter fills, corrective EXIT bỏ qua, VWAP amend unmapped; P11/SRC03/13/14/21/22 | QuantBT actual fills/rejects là nguồn duy nhất; consume mọi follow-up hoặc reject capability | Gap corrective exit, amendment effective phase, partial fills; RF-02 |
| A05 | Ba HMA schema names map cùng mode1; P05/SRC18–20 | Canonical enum/migration explicit; unknown raises; mỗi parameter có behavioral effect test | Categorical mapping và effect witnesses, no silent fallback; RF-01/02 |
| A06 | Decision 15m/1h được dùng làm protection execution thay 1m protocol | Route capability: giữ 1m cho true order-sensitive cohort; vector cohort dùng clock mới chỉ khi đăng ký rõ; không claim cùng study cũ | HTF availability, stop/TP gap, 1m vs coarse divergence; RF-02 |
| A07 | Block utility thiếu bước PnL đầu; P08/SRC15 | Prior equity hoặc engine deltas theo interval; first block dùng initial account | PnL partition telescoping, partial returns; RF-01/04 |
| A08 | Baseline gọi default helper với utility giả Sharpe, không public WFO Mode 4 | Actual `mode_4_is_only_robust/per_fold_causal`, real scorer + selector path; legacy argmax chỉ control | Golden public fixed-calendar parity, forbidden OOS access; RF-02 |
| A09 | E deploy chính schedule D; actual 15/15 paths bằng | Không dùng E trong primary contrast. Nếu mở E phải wire response từng cell, independent bank schedule | Synthetic E positive-control; no placeholder alias; RF-03/04 |
| A10 | Namespace/version đổi coi là market change; ineligible được trigger; ép 6 bins | Semantic market state mapping, eligibility check; online trigger/min-gap/max-age/budget, no forced N | Namespace permutation, UNKNOWN policy, zero-transition fallback; RF-03 |
| A11 | Response features là squared centroid residual, mất sign/state | Raw economic context / common causal coordinate; residual chỉ novelty/quality | Opposite centroids zero residual vẫn phân biệt context; RF-03 |
| A12 | A-SC/BTC-only response; cold weekly episodes; empty campaign book; gappy-weight support; cost units | Warm indicators, truthful coverage, actual state/activation, ESS+dependence diagnostics, cost theo transition | Support tests, warmup convergence, zero-switch funnel; RF-03/04 |
| A13 | Global-R-only bank, diversity tham số không bằng behavior, quality filtering thiếu | Anchor+conditional specialists đủ risk/local support; behavioral diversity; cutoff lineage | Candidate admission, equivalent params, no future bank; RF-03 secondary |
| A14 | K/cadence cố định mặc dù discovery khác; scaler inner leakage; ablation đổi target/cohort; mapping khác scaler | Fit scaler inner-only; small registered ladder; fixed target/cohort; common-coordinate state assignment | Inner suffix mutation, same-cohort ablation, model-boundary stability; RF-03 |
| A15 | Economic threshold từ cost thiếu allocation 0,1; P09 | Units explicit, endpoint account-return; preregister corrected/new business hurdle, giữ old registration | Notional/account dimensional tests, CI interpretation; RF-01/04 |
| A16 | FAILED_VALIDITY nhưng subclaims RULED_OUT | Validity → implementation fidelity → statistics gating; affected contrast NOT_EVALUABLE | Inject any blocker → no positive/negative financial claim; RF-01/05 |

## 4.2 Các phần data/test/transparency của audit cũng phải đóng

| ID mới | Nghĩa vụ | Disposition cần có |
|---|---|---|
| D01 | Raw pilot market/data pack thiếu trong audit ZIP | Tạo replay pack nhỏ, hoặc manifest+read-only server snapshot thực mà runner resolve được; chưa đủ thì `REPRODUCIBILITY_PARTIAL` |
| D02 | Hai tests hardcode executable venv | Dùng environment/interpreter hiện tại hoặc explicit supported executable; missing env là setup error, không financial pass |
| D03 | Unique evaluation ledger thiếu duplicate/pruned/failed optimizer trials | Export trial lifecycle đầy đủ; `trial_id != evaluation_id != candidate_id`; no runtime error score −1e9/COMPLETE |
| D04 | Response says sample 4.000 nhưng chỉ giữ 400; supported rows thiếu | Actual row counts, sampling policy, complete decision-reconstructable references; full required trial ledger không sample |
| D05 | Tick/lot metadata từ sample chưa là venue historical authority | Pin source/provenance; enforce actual supported constraints; `metadata_only` không gọi certified |
| D06 | No-funding bị hiểu như spot/perp exact | Giữ economic label đúng; primary paired arms cùng assumptions; funding stress extension riêng khi data có |
| D07 | A-HASH năm cells chưa chạy; docs drift | Sửa adapter hoặc block rõ 5 cells; không số 0 giả/no-edge; update CLAUDE/OpenCode handoff rules |
| D08 | Test presence không chứng minh runner sử dụng helper | Public-path assertions + adversarial mutation; mỗi finding có failing-before/passing-after evidence |

## 4.3 Các kiểm tra mới của lần hợp nhất

**N01 — PF definition.** Standard package PF là ratio trên `stats_returns`. Báo `profit_factor_quantbt` theo metric gốc, kèm sampling; trade PF chỉ tính từ engine trade/fill attribution có contract. Không đổi tên/đơn vị để tạo cross-fold decay giả.

**N02 — Native prepared close clock.** Snapshot fast public scorer ghi same-close. Không coi `signal.shift(1)` như next-open: nó có thể thành next-close. Không thay `close` bằng `open` trong data frame để lách guard, vì valuation/high-low/margin đổi nghĩa. Mọi timing cohort phải explicit và được kiểm bằng gap fixture.

**N03 — Audit bundle self-hash.** `audit_bundle_manifest.json` cũ ghi hash/size của chính nó trước khi finalize (record 3.205 bytes, actual 3.366 bytes). Đây là lỗi manifest self-reference, không chứng minh findings tài chính sai. Giữ nguyên historical member; manifest hợp nhất dùng actual hashes của từng member, không self-hash. Utility trích xuất kiểm hashes đó. Không diễn giải old self-entry là bằng chứng toàn ZIP bị corrupt.

**N04 — Observer fields không phải economic metrics.** Prepared scorer trả `turnover` như report trade count, `mean_return` như total return và `volatility=0` placeholder. Report phải map provenance/units; economic turnover lấy notional thực, volatility từ required return observations; zero placeholder không là đo risk.

**N05 — Whole-window Sharpe trong evaluator cũ dùng `sqrt(len(steps))`.** Đó là window-scaled statistic, không annualized Sharpe chung để so segments dài/ngắn. Không dùng nó làm primary fold Sharpe; keep field legacy với tên đầy đủ. Report mới dùng QuantBT metric contract và chuẩn daily-UTC cố định cho common-window comparison.

---

# 5. Endpoint routing: nhanh nhưng không đổi alpha

## 5.1 Chính sách vectorized-first

**Bulk numerical work phải ưu tiên endpoint/prepared runtime đã tối ưu của QuantBT 1.1.1**, đặc biệt target/pct_equity trên strategies có thể biểu diễn đúng bằng signal/target tape. Không gọi full event/audit runner hàng trăm lần chỉ để lấy scalar metrics.

Nhưng **vectorized-first khác vectorized-at-all-costs**. Ba alpha có protective/partial behavior không tự chuyển được thành long/flat positions bằng cách tự tính exits ngoài engine. Tỷ lệ số cells vectorized không là KPI; measured visited work/runtime và preserved semantics mới là KPI.

| Alpha | Route khởi đầu hợp lý | Điều kiện / ngoại lệ |
|---|---|---|
| A-SC | Public Mode 4 + `pct_equity` hoặc signal/target-native đã qualify | Giữ long-flat, crossover convention, availability, transition-based sizing; không tự thêm short |
| A-HMA | Existing QuantBT fast intrabar/target-assisted nếu express đủ exact behavior | Mode enum, stop/gap/technical exit phải đúng. Nếu cần actual fill feedback dùng event-native, không tự dựng fills |
| A-VWAP | Fast QuantBT intrabar cho fixed bounded cases; native event cho amend/corrective paths | `exit_at_vwap=True` không được ignored. Restrict một nghiên cứu subset phải version và report, không silently bỏ knob |
| A-HASH | Existing native event/order engine với multi-TP/partial exits | Giữ ladder actual quantities, OCO/reduce-only theo capability; không collapse về TP cuối để chạy nhanh |

Có thể vectorize indicator generation ở strategy/lab và gom arrays một lần; financial simulation luôn QuantBT. Một parameter set không có custom order dependency có thể dùng fast route riêng, nhưng route decision phải **chỉ dựa capability/schema trước outcome**, không dựa candidate nào kiếm tiền hơn.

## 5.2 Ba mức sử dụng fast route

1. **Equivalent fast route:** same inputs/economic contract → same financial trace theo tolerance đã pin. Được dùng search và final result.
2. **Explicit research target version:** sửa strategy thành target-only là economic/thesis variant mới, được người dùng cho phép nghiên cứu nhưng phải mang version riêng; không đại diện nguyên alpha protective.
3. **Screening surrogate:** chỉ lọc sơ bộ nếu quality/rank gates đã qua trên train; không gọi kết quả của nó là final time-edge evidence. Final selection phải được chấm bằng authoritative compatible route theo policy đã đăng ký; nếu prefilter thay candidate set thì đây là search contract khác cần controls.

Không chỉ kiểm winner rồi coi toàn ranking đúng. Trong primary repaired study, ưu tiên mức1. Mức2/3 không là đường né A04/A06.

## 5.3 Timing và execution resolution

- HTF features tại close chỉ available khi bar đã đóng; chart timestamp mở bar không phải decision availability.
- Orders bảo vệ theo intrabar lifecycle dùng 1m nếu giữ protocol Final V2. Không truyền 15m/1h như thể 1m chỉ để nhanh.
- Signal-target research có thể dùng decision-resolution same-close hoặc một-bar-lag contract nếu đã đăng ký. Đây là idealized/lagged close execution, không same-next-open. Report scope khác true 1m event execution.
- Params mới không được dùng tại close mà chỉ ready sau close; activation phải sang phase tiếp theo được contract cho phép.
- Không gọi native-prepared `require` trên unsupported timing rồi tắt risk/fees để lách capability. Correct fallback cùng semantics được ghi rõ; engine failure không đổi thành Python hidden baseline.

## 5.4 Percent equity khác fixed notional

`pct_equity` có thể thay lượng mua theo equity tại signal transition; dùng fixed 2.000 USDT như artifact cũ là bài toán khác. Đăng ký `sizing_contract`, signal amplitude, leverage multiplier và rebalance semantics bằng golden fixtures. Dùng cùng sizing cho CAL/REGIME trong mỗi cohort.

Allocation 0.10 có thể là 10% theo factory semantics hiện tại, nhưng actual notional còn phụ thuộc signal/leverage/rounding. Kiểm bằng output engine, không suy từ tên config. Strategy position state hoặc fee calculation không được tự nhân notional hai lần.

---
# 6. Metrics, fold decay và cách suy luận time edge

## 6.1 Giữ metrics hiện có; thêm definitions thay vì đổi thầm

Export nguyên bộ QuantBT metrics được route thực trả: total return, Sharpe, Sortino, max drawdown, profit factor, trades/fills, exposure, fees/funding và các metadata optimizer. Mỗi field có `metric_contract`, đơn vị, sampling, nguồn (engine/raw/recomputed), valid-observation count và undefined policy.

Bổ sung hai bảng:

- `metrics_quantbt_raw`: dùng để reproduction và compatibility.
- `metrics_research_canonical`: daily UTC và account-unit metrics dùng để so các schedules.

Nếu chúng khác vì sampling/first-return/penalty/contract, report có reconciliation. Không sửa nguyên số raw để làm bảng khớp. Profit Factor return-based và trade-based có tên khác; trade count và fill count khác nhau.

## 6.2 Return và PnL partition đúng

Với account không có external deposits/withdrawals, daily close equity `E_d` và `E_{d-1}` trước ngày:

\[
r_d=E_d/E_{d-1}-1.
\]

Observation đầu của whole account dùng initial equity trước mọi fee/fill, không bỏ phí ngày đầu. Với half-open block `[a,b)`, money PnL:

\[
\Delta P_{[a,b)}=E_{b^-}-E_{a^-},\qquad
R_{[a,b)}=E_{b^-}/E_{a^-}-1.
\]

Money deltas của partition phải cộng về whole money PnL; compounded returns phải nối đúng bằng tích `(1+r)`. Không cộng raw percentage returns của các capital bases khác nhau rồi gọi là account return. Có external cashflows thì cần contract time-weighted return riêng; primary lab không tự thêm cashflows.

Drawdown của block phải include starting equity/watermark theo definition. Trả cả local-window drawdown và whole-account drawdown attribution nếu cần; không reset historical peak rồi gọi local drawdown là live maxDD.

## 6.3 Sharpe cùng đồng hồ

Đối với canonical daily crypto returns, risk-free daily `r_f,d` đã đăng ký:

\[
SR_{daily}=\sqrt{365}\,\frac{\overline{r_d-r_{f,d}}}{s(r_d-r_{f,d};ddof=1)}.
\]

Nếu giữ package zero-risk-free convention thì ghi rõ. Không dùng `sqrt(số bars trong fold)` để annualize mọi fold. Giữ zero-return days; không drop ngày flat/no-trade. Missing market day không tự là zero; sửa/flag theo data contract trước analysis. Fold rất ngắn hoặc variance 0 có flag `INSUFFICIENT_OBSERVATIONS`/`ZERO_VARIANCE`; giữ raw QuantBT convention nếu engine trả0 nhưng analysis không diễn giải0 như estimate tin cậy.

Không average per-fold Sharpes để ra portfolio/whole-period Sharpe. Primary so trên continuous daily paths cùng dates, canonical SR từ toàn path. Khoảng ngắn dùng returns và uncertainty đầy đủ thay vì annualized headline gây hiểu nhầm.

## 6.4 Profit Factor: hai definitions không được trộn

PF QuantBT snapshot:

\[
PF_{obs}=\frac{\sum_{d:r_d>0}r_d}{|\sum_{d:r_d<0}r_d|}
\]

ở đây `d` phải là **stats sampling thực của engine**; canonical daily PF được ghi riêng nếu sampling khác. Nó không mặc định là “gross winning trades / gross losing trades”.

Nếu có trade ledger chuẩn do QuantBT sinh hoặc reducer report được xác minh:

\[
PF_{trade}=\frac{\sum_{j:p_j>0}p_j}{|\sum_{j:p_j<0}p_j|}.
\]

`p_j` phải nêu rõ realized net PnL, fee/funding attribution, campaign grouping và partial exits. Open positions không biến thành completed trades chỉ vì hết reporting month; unrealized vẫn ở equity. Cần closed/censored counts. Không tự viết financial matching/trade ledger thay engine chỉ để có PF này.

No losses: `value=null`, `status=NO_LOSS_DENOMINATOR`, giữ raw engine infinity ở encoded diagnostic nếu cần. No trades: `NO_TRADES`. Không serialize NaN/Infinity như JSON numbers chuẩn, không cộng epsilon để manufacture hữu hạn, không gọi PF∞ của cash-only là chiến lược tốt.

## 6.5 Ba nghĩa của decay phải tách

### D1 — IS → first OOS degradation của cùng selected params

Với mỗi selection `θ_k`, lưu raw IS temporal/subperiod metrics đã dùng chọn và post-selection OOS metrics. Dùng cùng horizon-normalization/economic contract; chỉ so sau freeze.

\[
D^{SR}_{IS,OOS,k}=SR_{IS,k}-SR_{OOS,k}.
\]

Lưu cả phiên bản raw và `candidate_decay_quantbt` có trade-frequency penalty; không lấy penalized score làm raw Sharpe. IS đã selection-biased nên đây là **generalization-gap diagnostic**, không estimator không thiên lệch của alpha decay.

Return decay nên dùng mean daily net return hoặc fixed-horizon returns tương đương, đơn vị `account_bps/day`. Total return 365d train trừ total return 28d OOS không là meaningful retention ratio. PF có thể dùng:

\[
D^{PF}_{IS,OOS,k}=\log(PF_{IS,k})-\log(PF_{OOS,k})
\]

chỉ khi cả hai hữu hạn, dương, same-definition và đủ support; trường hợp khác giữ flags/đếm, không loại âm thầm.

### D2 — Performance theo tuổi một bộ params được freeze

Đây là diagnostic sát câu hỏi time edge hơn. Với `θ_k` được chọn tại `t_k`, replay **cùng θ_k** qua các age windows fixed trước như `H1=[0,h)`, `H2=[h,2h)`, `H3=[2h,3h)` trên chronology thật. `h` chọn bằng development/holding diagnostics, không tối ưu outer.

\[
D^{SR}_{age,k,j}=SR_{k,H_1}-SR_{k,H_j},\qquad
D^{\mu}_{age,k,j}=\mu_{k,H_1}-\mu_{k,H_j}.
\]

Trả PF log difference khi hợp lệ, trade count, exposure, time since regime change và market context. Cùng θ nhưng markets thay đổi vẫn không cho “causal parameter decay” tuyệt đối; đây là bằng chứng tuổi-param/context association có scope.

Age replay là **diagnostic after selection**, không dùng future age curve để quyết định khi nào deploy trong chính run. Không lấy nó cập nhật search/threshold sau outer rồi giữ claim untouched. Cache replay cho metric views; chỉ chạy subset anchors được đăng ký trước nếu ngân sách hạn chế, không chọn anchors vì chúng decay đẹp.

### D3 — Chênh lệch giữa operational folds liên tiếp

\[
\Delta M_{k\rightarrow k+1}=M(\theta_{k+1},F_{k+1})-M(\theta_k,F_k).
\]

Trả Sharpe/return/PF, length/support/market-state/parameter-age. Đây là **observed fold change**, vì params và thị trường đều thay đổi. Không gọi nó decay của cùng vector params. Không so hai dynamic folds có lengths khác bằng total returns thô hoặc unweighted fold SR.

### Bảng báo cáo decay bắt buộc

```text
selection_id / parameter_digest / alpha / symbol / arm
metric_name / metric_definition / unit
comparison_kind: IS_TO_OOS | FIXED_PARAM_AGE | ADJACENT_OPERATIONAL
left_start/end / right_start/end / observed_days
left_value / right_value / signed_delta
raw_or_penalized / penalty_components
validity_status / trade_count / effective_sample/support
regime_at_selection / regime_in_window / transition_count
in_sample_selection_bias / diagnostic_only
```

## 6.6 Primary endpoint và uncertainty

Primary timing endpoint khởi đầu: paired mean daily **account** net-return difference `M4_REGIME − M4_CAL`, với confidence interval dependence-aware. Report kèm ΔSharpe, maxDD, canonical PF, risk/exposure, turnover và decay panels; không pick metric thắng sau khi xem results.

Common dates giữ cùng initial conditions. Mỗi alpha-symbol có kết quả riêng. Cross-cell aggregate dùng weights xác định trước (ví dụ equal capital cells) và report correlation/common shocks; không average 20 Sharpes. Mất một cell không thay denominator âm thầm; matched-valid subset có nhãn partial coverage và coverage table đủ20 cells.

Dùng paired block bootstrap trên cùng daily indexes cho cả arms; cùng resampled dates cho các symbols nếu đang kiểm common-market aggregate. Block length/hypothesis family/minimum effect chọn trong development; không iid bootstrap từng bar 1m. Nếu cần CI cho SR/PF, recompute statistic từ mỗi resample với proper missing/infinite handling và disclosure — không dùng percentile của per-fold SR như whole-run CI.

Repeated seeds của TPE đo search variability; không xem20 cells×5seeds là100 độc lập hoàn toàn. State/placebo alternatives count vào multiple-testing ledger. Nếu có nhiều contrasts, family và multiplicity adjustment phải đăng ký. Không dùng CI chứa0 như evidence no-edge; không dùng marginally positive point estimate như proof thắng.

## 6.7 Minimum economic effect và claim gates

Giữ old MDE0,64 bps/day như historical registration. Khi corrected cohort đổi sang percent-equity sizing, tính lại economic threshold theo **actual** turnover/account units hoặc dùng business hurdle độc lập do chủ nghiên cứu đặt. Không lấy đơn giản0,064 bps từ finding A15 áp cho mọi sizing mới.

Ví dụ units check (không là target lựa chọn): nếu uncertain round-trip rate0.001 trên notional, round trips/day0.064, notional/equity0.1, uncertainty/account/day là0.0000064 =0,064 bps. Actual percent-equity notional cần từ declared policy/engine trace trong development.

Với threshold dương `δ` đã freeze và CI `[L,U]` của Δdaily-return:

| Điều kiện | Economic conclusion được phép |
|---|---|
| Execution/treatment/data validity fail | `NOT_EVALUABLE` |
| Valid và `L > δ` | `POSITIVE_WITHIN_TESTED_SCOPE` nếu risk/non-inferiority controls cũng pass |
| Valid và `U < δ` | `NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE` đối với mức δ, không “regime không có edge mọi nơi” |
| Valid, CI còn vượt qua δ | `INCONCLUSIVE` |
| Valid và `U < 0` | Treatment underperformed trong scope, report riêng |
| Cả hai arms lỗ nhưng treatment lỗ ít hơn | Relative gain có thể có, nhưng `DEPLOYMENT_ELIGIBILITY` là câu hỏi riêng |

Historical invalid intervals phải giữ raw, không compute lại claims từ chúng. Chỉ kết luận repaired study sau phase gates.

---

# 7. Dữ liệu, regime và timing policy

## 7.1 Data trust contract vừa đủ, không audit lại cả hệ thống

Pin snapshot paths/hashes/read-only; giữ user convention spot≥2020. Kiểm đúng symbol, native units, timestamp ms/ns, duplicate/out-of-order, HTF completion, point-in-time universe, revisions/available_at, source masks và original alpha hashes. Không tải lại candles hoặc sửa collector production để test.

Reuse panels server đã có nếu hash/provenance đủ. Nhóm derivatives/liquidity chỉ dùng khi đủ coverage trên cùng cohort; missing không gán0. Source extra free/paid chưa bắt buộc để sửa findings. Không trì hoãn corrected Mode 4 baseline vì chưa mua on-chain data.

Một replay pack nhỏ phải đủ OHLCV/time/constraints/cost/alpha params để người khác chạy lại pilot bằng QuantBT. Full market data lớn có thể nằm read-only server, nhưng report phải ghi `reproducible_on_server` khác `portable_bundle_complete`.

## 7.2 Regime model: sửa representation trước tăng complexity

Giữ discrete JM đã có, fit objective/reference và online recurrence:

\[
\min_{\mu,s}\sum_t\ell(z_t,\mu_{s_t})+\lambda_J\sum_{t>1}\mathbf 1[s_t\ne s_{t-1}],
\]
\[
Q_t(k)=\ell(z_t,\mu_k)+\min_j\{Q_{t-1}(j)+\lambda_J\mathbf 1[j\ne k]\}.
\]

Fit scaler chỉ trên inner train; transform validation bằng frozen scaler đó. Full outer-train fitting sau model-design selection là hợp lệ, nhưng không ghi inner test đã causal nếu scaler fit cả inner validation. Online emissions không được backtrack/overwrite past decisions.

Store economic feature values/ref, transformation version, state ID/namespace, fit residual và novelty riêng. Residual-square vector không làm context-distance representation. Nếu response so lịch sử dưới current-fit coordinates, mọi raw episodes phải available trước cutoff; decision-vintage tapes cũ vẫn bất biến.

State mapping giữa refits: quy centroids về common raw/economic coordinates hoặc transform cả hai bằng một current-valid transform; dùng one-to-one assignment cho same-K khi feasible, đánh unmatched/ambiguous rõ. Không dùng many-to-one greedy map như một perfect semantic identity. Refit model không tự trigger market-state change.

## 7.3 Triggers live-replayable

Một transition eligible cần thỏa:

```text
available_at <= decision_time
model_ready_at <= decision_time
decision_eligible == true
quality_status thuộc policy allowlist
semantic state thật đổi với confirmation/hysteresis đã freeze
minimum spacing và compute budget còn hợp lệ
```

`UNKNOWN_STATE`, missing data, stale model, model refit, funding event là các reasons khác nhau. Nếu novelty có quyền request refresh thì tạo policy/rationale riêng, không bypass eligibility.

State machine tối thiểu:

```text
OBSERVE → KEEP | REQUEST_SEARCH | DEFER_BUDGET | FALLBACK_QUALITY
REQUEST_SEARCH → PENDING → READY | FAILED | SUPERSEDED
READY → KEEP_INCUMBENT | WAIT_INDICATORS | WAIT_CAMPAIGN | ACTIVATE
```

Không ép đúng N refits hoặc abort vì không có transition trong một calendar bin. Registered max-age có thể request refresh khi market ổn định; ghi `MAX_AGE`, không gắn “regime detected”. Lịch model retrain, inference, parameter search và activation là bốn clocks riêng.

Initial incumbent chọn trước evaluation start bằng đúng Mode 4. Khi chưa có approved incumbent, account ở trạng thái được đăng ký (ví dụ flat), không backfill params được chọn sau start. Warmup của new params dùng past bars đúng algorithm; không gọi full adapter `on_bar_close` phát entry trên shadow rồi tự tạo financial state. Shadow chỉ indicator state, hoặc isolated evaluation, không lẫn với live account.

## 7.4 Primary dynamic Mode 4 integration không được lộ future segment end

Snapshot chưa có API chung `regime_fold_provider`. Thực hiện theo thứ tự:

1. Dùng public extension/hook đã có nếu verify được.
2. Nếu thiếu, thêm **thin lab-only fold/cutoff adapter** quanh `WalkForwardEngine` của candidate copy, giữ `optimize_params`, Mode 4 selector, scorer và trial capture gốc; không rewrite các phần đó.
3. Tại event cutoff thực, đóng training view và gọi IS-only selection; `_run_per_fold_schedule`/`optimize_params(...evaluate_oos_candidates=False)` là reference source để reuse, không private default argmax.
4. Final active schedule được xây online; closed segment end chỉ ghi sau activation kế tiếp. Search không được nhận actual future `segment_end` để lấy horizon/cost tùy ý.
5. Sau mọi decisions được capture, target-only policies có thể compile một causal target tape và gọi **một** QuantBT continuous backtest. Fill-dependent policies phải chạy native event session với actual feedback.
6. Fixed calendar injected qua adapter phải match public Mode 4 run về candidates/selection/effective targets theo contract; changed future suffix không đổi pre-cutoff decisions.

Nếu API internals đòi fold metadata, search-facing view chỉ có train/bounded declared metadata hợp lệ, không expose future observations/actual end phát hiện bằng market. Nếu không thể đáp ứng, sửa hook ở **lab copy** và có diff/reference tests; không dùng empty/synthetic future prices để đánh lừa runtime rồi gọi test thật.

## 7.5 Secondary selector và response repair không lấn mục tiêu chính

Independent probes: metrics đúng, bad feasible neighbors retained, fixed params không đổi geometry, incumbent same objective/constraints, nonfinite/runtime failures distinct. Không thay stock Mode 4 giữa hai primary arms.

E response: candidate bank 3–8 là hypothesis, không bắt tăng 16–64; global anchor + conditional specialists nếu có evidence. Historical outcomes complete trước decision; warmup ngoài score interval; uncertainty dựa true time-dependence, không số fragments trong 90% weights. Cost cùng return/allocation horizon, computed from actual transition plan. Nếu không đủ support, keep incumbent nhưng vẫn xuất đầy đủ decision funnel.

**Không cần full E market sweep để đóng primary Mode 4 timing study**, nhưng A09/A11–A13 phải repaired và tested nếu bật E; nếu chưa bật thì hard-disable và formal quarantine, không tiếp tục publish null của E cũ.

---

# 8. Tăng tốc thí nghiệm và quản lý ngân sách

## 8.1 Không tạo một “bài test” chạy hàng giờ

Tách unit/reproducer, integration pilot, discovery và market research. Một full multi-year 20-cell research run có thể cần tổng compute lớn; không hứa toàn nghiên cứu luôn hoàn tất vài phút. Yêu cầu là **không có vòng lặp lãng phí/monolithic test không progress, không rerun toàn lịch sử chỉ để kiểm một bug**.

Các giới hạn dưới đây là guardrail đề xuất để agent đăng ký trên server, **không phải thời gian thực hiện đã đo hoặc lời hứa thời gian**:

| Tier | Nội dung | Policy thời gian/phạm vi |
|---|---|---|
| T0 | Unit, 12 historical probes chuyển thành regressions, contracts | Chủ yếu synthetic 12–200 bars; suite mục tiêu≤60s sau imports/compile; báo cold riêng |
| T1 | Actual alpha/engine parity pilot | 1–2 cells; đủ warmup và lifecycle events; cap task 120s mặc định, vượt thì profile thay không drop tests |
| T2 | Mode 4/scheduler integration pilot | 2 cells, 2 cutoffs, bounded trials; cap 600s/structured pilot; không là evidence final no-edge |
| T3 | Discovery shards | Task alpha×symbol×cutoff hoặc bounded batch; mỗi shard≤900s budget đề xuất, retry deterministic |
| T4 | Frozen confirmation | Reuse prepared data/model snapshots, schedule chạy theo chain thật; sharded, progress, evidence committed; total budget được duyệt |

Deadline-driven truncation có thể làm candidate sequence phụ thuộc machine speed; không dùng partial tasks đó như complete economics. Timeouts là `BUDGET_STOPPED`/technical events, không PRUNED theo tài chính. Không tăng grants âm thầm để một arm luôn fit sớm hơn.

## 8.2 Lộ trình loại công việc lặp

- Loại per-trade `_exit_oracle` và full-window fixed-point sweeps khỏi main evaluator; dùng một QuantBT compatible run. Đây vừa sửa correctness vừa loại asymptotic repeated work.
- Load/canonicalize/read-only market arrays một lần cho mỗi worker; dùng fold views, không pandas copy toàn dataset per trial.
- Regime fit/inference theo symbol/cutoff/schema/seed một lần, reuse giữa 4 alphas khi model không phụ thuộc alpha. Không reuse nếu model design hoặc allowed cutoff khác.
- Indicator caches do strategy/lab quản lý, theo alpha version/params/history/warmup/cutoff; chỉ reuse causal pure calculations. Không cache mutable campaign/account, không backfill future fit/scaler.
- Bật prepared endpoint scoring và scalar profiles thực, đo counters. Mỗi candidate không build full report/chart/audit ledger nếu objective không cần; mọi trial/metric/status vẫn retained.
- Reuse one evaluation cho cùng exact economic input; unique trial records vẫn đầy đủ. Cache key gồm data, schema, warmup, params, initial account, costs, timing, route, seed và code semantics. Fee repair invalidate toàn kinh tế liên quan.
- Incremental JSONL/columnar records, không rebuild toàn trial DataFrame sau mỗi trial. Build report/charts từ committed artifacts cuối shard/phase.
- Bootstrap từ retained daily returns; không chạy QuantBT cho từng resample chỉ để tính CI của path đã có. Market-path stress có mục tiêu khác phải rerun strategy qua engine và ghi loại test.
- Selected audit rerun dùng cùng params/contracts/seed; chỉ audit candidates đăng ký/topselected. PF/decay cần path/trade ledger thì request đủ retention, không gọi lại simulation riêng từng metric.

## 8.3 TPE và concurrency không đổi methodology

Primary dùng fixed seed + sequential ask/tell contract của installed Mode 4; parallel hóa independent cells, hợp lệ independent training cutoffs nếu tapes/state chỉ từ past, và các native scoring tasks independent trong evaluator. Carry deployment có dependency thời gian thì giữ chronological.

Batch ask-before-tell thay adaptive search information flow; nếu thử throughput schedule, đăng ký separate policy cho **cả arms**, không gọi là identical legacy TPE. Native workers không tự làm Python callbacks giữ GIL parallel; dùng existing isolated processes khi callback-heavy, kiểm thread/BLAS oversubscription. Sources [S1–S4] mô tả API/principles, dependency actual theo lockfile, không upgrade tới stable docs version.

Không parallel shared-account legs hay carry folds như independent resets. `python_processes × nested native pools` cần budget từ profiler/topology thực; không nhân mọi layer với toàn cores.

## 8.4 Pilot budgets đủ để thực sự exercise Mode 4

Pilot 8–16 trials hữu ích kiểm plumbing nhưng có thể không đủ top candidates để clustering/min_samples hoạt động. Không lấy fallback-only pilot rồi kết luận plateau/regime không work.

RF-02 phải log `top_trials`, unique effective candidates, cluster_method, cluster_size, fallback reason và selector used. Discovery budget đề xuất bắt đầu 32–64 trials/cutoff nếu data/runtime đủ; **số cuối phải freeze sau dry-run coverage review, không coi 64 là guarantee**. Với nhiều chiều/tương tác cần signal-effect/coverage checks; nếu insufficient thì kết luận support thiếu, không âm thầm thu hẹp tới presets toàn set.

Compute matching tính total candidate-window-bars, execution-route cost, independent probes, failed attempts, model fits và wall/CPU, không chỉ count refits. Giữ một policy budget bằng nhau cho arms; không cắt trials lúc đã nhìn outcome yếu. Trials/budgets cho confirm chọn từ development thôi.

## 8.5 Profiler và bảng chi phí bắt buộc

```text
load/prepare/indicator-generation/intent-pack
QuantBT simulation/metrics/native-boundary
Mode4 selection/model-fit/regime-inference/scheduling
audit encode/flush/report generation
unique evaluations/cache hits/actual visited bars
cold compile time/warm run time/peak RSS
requested/resolved backend/native wheel/module origin
```

Lưu cả request route và actual engine/capability. Rust chỉ được claim speedup nếu measured public WFO nhanh hơn comparator cùng economics/output; cache-hit không tính như bars vừa execute. Không tắt oracle, fees, risk constraints hoặc alpha exits để giảm runtime.

---
# 9. Năm phase triển khai

Namespace mới: **RF-01…RF-05** (`Regime-Fold Corrective Study`). Không renumber hoặc xóa lịch sử LAB-01…10/PERF. Những stages cũ vẫn là evidence của source cũ. Mỗi phase phải có code, tests, actual artifacts và báo cáo; không đóng bằng việc tạo nhiều Markdown.

```text
RF-01 Freeze / invalidate / contracts / failing tests
   → RF-02 QuantBT actual execution + Mode4 baseline + fast routes
   → RF-03 Causal regime schedule + model/representation repairs
   → RF-04 Controlled real-alpha discovery + decay / contribution
   → RF-05 Frozen rerun / falsification / consolidated claims & handoff
```

RF-03 có thể sửa model/reference độc lập song song với phần adapter của RF-02, nhưng mọi market comparison chờ RF-02 validity gate. Model/data/report utilities hiện có được reuse. Chỉ 5 phase; các tasks dưới đây không tự là phase mới.

## RF-01 — Khóa phạm vi, invalidate đúng và biến findings thành regressions

**Mục tiêu:** dừng việc diễn giải kết quả sai; xác định exact Mode 4/economic/metric contracts và môi trường thực; có failing tests trước sửa.

**Inputs:** archive/source hiện tại, audit A01–A16, all evidence members trong phụ lục, approved scope Mode 4,4 alphas×5 symbols, current rules của agents.

### RF01.1 — Isolated working copy và identity

Tạo corrective branch/copy trong lab được phép, record source SHA hoặc file-manifest khi không có Git, original archive hash, core/native wheel hashes, Python/Numba/Optuna versions, actual `quantbt.__file__`, extension origin và `sys.executable`. Check production/alpha/data protected paths không writable bởi worker. Lưu source-before manifest; exclude venv/cache khỏi audit source nhưng không âm thầm ignore runtime dependencies.

Existing `.lab_marker` và sandbox policy dùng lại nếu đúng. Không đổi quyền hoặc xóa bất kỳ thư mục production để “fix import”. Nếu server có bảnlab mới hơn ZIP, map từng finding tới mới; không claim new source đã audited từ old lines.

### RF01.2 — Invalidation và claim sửa ngay

Tạo `historical_invalidation.json` trỏ A01–A16 tới affected cells/arms/source/evidence. Set economic inference của invalid contrasts thành `NOT_EVALUABLE`; giữ final historical `FAILED_VALIDITY` và raw curves để debug. E old bị `NOT_IMPLEMENTED_AS_SPECIFIED`; không delete các null/negative kết quả.

Dùng `invalidated_by`, `superseded_by`, `scope_affected`, `retest_required`, không overwrite file đăng ký cũ. New spec ID khác study cũ. Chỉ repair có chứng cứ mới cập nhật claim record.

### RF01.3 — Mode 4/config/metric contract inventory

Tạo `quantbt_binding_report.json` từ actual installed source/signatures/capability. Ít nhất verify VFY01–VFY11; check `mode_4_is_only_robust`, `per_fold_causal`, `is_only_robust`, endpoint scorer. Capture selector knobs và defaults resolved, không chỉ kwargs request.

Freeze allowed account/sizing/rate units, price/timestamp contract, execution resolution, trade frequency penalty, metric sampling, PF definitions, initial incumbent, final-bar position policy. Resolve real research retention enum. Audit names/code used by WFO vs generic optimizer: không giả mọi plateau implementations giống nhau.

### RF01.4 — Regression suite nhỏ và positive-control plan

Khôi phục historical probes từ phụ lục vào audit workspace nếu cần, nhưng chạy chúng trên archived source chỉ để tái hiện old defects. New tests phải assert **correct behavior**, không assert `confirmed_bug=true` trên code repaired. Map12 probes với T-cases Section11; một test injected fake engine result chỉ là validation test, không financial market evidence.

Thêm before-tests cho E=D, HMA enum effect, ready-time, unit normalization và report gating. Fix hardcoded venv paths. Unit results ghi passed/failed/skipped với reason; không turn environment skips thành pass.

### RF01.5 — Register primary protocol và cost/time budgets

Tạo `corrective_study_spec.json`: primary M4_CAL/M4_REGIME; permitted secondary arms; same cohort/engine/sizing; search budgets; cadence candidate grid; seed map; contamination status; primary endpoint; MDE units/business hurdle; risk constraints; report dates; exposure of historical data; cutoff/activation latency policy.

Diagnostic suite không cần profitable. Discovery settings vẫn có thể đổi theo evidence nhưng phải tăng specversion; confirmation chưa được mở trước freeze. Không ép old 4h/28d/7d/K3 thành best design. Không mở model grid hàng trăm configs.

**Files bắt đầu sửa:** `configs/*claim*`, `scripts/analyse_lab09_confirmation.py`, environment/test setup và manifests; actual path map trong report. Không chỉnh model để tìm positive PnL ở phase này.

**Outputs:** `RF-01/report.md`, `report.json`, `historical_invalidation.json`, `finding_disposition.json`, `quantbt_binding_report.json`, `corrective_study_spec.json`, regression baseline logs, budget/dry-run manifest.

**Exit:** exact scope/imports/units known; all known P0 mapped; false claims quarantined; probes small reproducible. `proof_status=TECHNICAL_ONLY` — chưa nhận định time edge.

**Rollback:** chỉ candidate lab và new reports; historical evidence không đổi. Không xóa nguồn cũ để test pass.

---

## RF-02 — Actual QuantBT simulation, Mode 4 baseline và fast execution qualification

**Mục tiêu:** có một baseline đúng và nhanh. Giải quyết A01–A08, các supplements N01/N02/N04/N05 trên public paths, không tiếp tục fixed-point fake fill bridge.

### RF02.1 — Alpha semantic specification và behavioral contracts

Mỗi alpha có adapter hash, source hash, parameter schema, active/ignored fields, warmup readiness, decision timeframe, position/sizing behavior, allowed order types, intrabar requirements và route capability table.

- A-SC: long-flat đúng source; không tự thêm shorts/pyramiding vì signal amplitude khác.
- A-HMA: canonical SL enum duy nhất; aliases cũ phải migration rõ hoặc reject. Test `ATR Only`, zone modes và `Last High/Low` nếu public search cho phép. Tick metadata thật, không cố định0.01 cho mọi symbol. Ignored knobs không vào search.
- A-VWAP: HTF closed availability, time stop, dynamic VWAP amend actual effective phase và cancellation semantics.
- A-HASH: partial TP ladder/remaining quantity/entry quantity actual, bounded TP order rules. Không dùng last target thay whole ladder. Hoàn thiện adapter bằng native QuantBT capability; thiếu capability tạo block riêng, không tự viết engine.

Optional alpha improvement là version/thesis mới, không nhập vào A/B giữa run. Presets quarantined như reference.

### RF02.2 — Thay bridge bằng route adapter đúng, reuse engine

Có ba adapters nhỏ: target/signal, compatible fast-intrabar, native-event feedback. Chỉ routing/packing/callback projection; không tính cash/fills/PnL ngoài QuantBT.

Loại `_exit_oracle` gọi tương lai theo từng trade và bounded full-window rerun reconciliation khỏi active evaluator. Reference cũ giữ trong audit-only directory không selectable bởi production runner.

Every command must end `accepted/executed/rejected/unsupported`; unmapped invalidates evaluation. Actual fills trigger actual follow-ups; same-bar priority theo package contract. Callback exceptions discard staging nhưng business rejects per command giữ semantics gốc. All fill fields (IDs, sequence, side, qty, price, fee, reason, effective phase) có canonical trace; không dictionary keyed onlybar làm mất multiple fills.

### RF02.3 — Timing/accounting gates trước speed

Run synthetic/golden cases với registered fee và slippage ở từng route. Percent equity vs fixed-notional có tests cùng signal change/price drift; rate translation exact once. Engine-reported wallet/equity/positions reconcile với independent tiny oracle và invariant.

Initial incumbent known trước start; upcoming params retain pending queue; no use before ready. Do not close/reset account tại fold boundary trừ explicit policy đã đăng ký. End-of-study liquidation report tách terminal close cost và marked open positions; cùng policy mọi arms.

HTF decision to 1m mapping phải pass before/after bar fixtures. Nếu vectorized candidate uses same-close contract, record distinct approved cohort; không gọi nó next-open. Key primary comparison always same timing within pair.

### RF02.4 — Public Mode 4 baseline, không private helper imitation

Chạy actual factory/invocation từ installed1.1.1 trên một alpha đủ route. Capture actual scorer class, selector name, `oos_used_for_selection=false`, trial/candidate records, selected digest, fold boundaries, penalty components và final stitched account.

Kiểm tra fold provider của lab bằng một lịch calendar cố định giống baseline; đối chiếu kết quả với public run gốc. Dùng lại optimizer, evaluator và retention của engine. Không thay Sharpe bằng mean utility, và không để scorer âm thầm rơi về proxy.

Với order-dependent alpha, nếu public WFO chỉ nhận signal outputs, tạo evaluator binding/strategy wrapper dùng **actual QuantBT evaluation** và reuse Mode 4 selector/lifecycle; không flatten unknown reactive PnL thành series. Support/capability proof riêng; chưa hỗ trợ thì block đúng cell thay vì fabricate vectorized path.

### RF02.5 — Prepared scoring và performance wiring

Chỉ bật target-runtime/native-prepared trên route đã được chứng minh. Báo requested/resolved route, số native batches, rows, crossings, preparation calls, copied bytes và callback time. Chuẩn bị market một lần theo lifecycle hợp lệ của worker; tái sử dụng pure indicator arrays có causal provenance. Trial scoring trả dữ liệu gọn nhưng full research ledger vẫn giữ. Chỉ materialize full report khi tổng hợp hoặc khi selected cutoff thực sự cần.

Bounded CPU budget. TPE sequence trong study giữ nguyên; parallel existing independent workloads. Prototype wrapper không được tạo engine mỗi trade. Benchmark warm/cold riêng trước full pilot.

### RF02.6 — Real-alpha pilot và quyết định route

Pilot ít nhất A-SC + một order-sensitive alpha, đủ historical warmup và fills/exit cases. Sau đó smoke cả 4 alphas trên symbols có data; không cần20 cells full-history ngay. Fixed params/regime tắt và fixed schedule parity trước optimization. Một pilot được chọn theo data coverage/lifecycle, không chọn vì PnL đẹp.

Trả route matrix cho 20 cells: `QUALIFIED_FAST`, `QUALIFIED_EVENT`, `BLOCKED_CAPABILITY`, `INSUFFICIENT_DATA`, kèm implemented tests. `%vectorized` không là gate; observed throughput trên correct paths là gate.

**Files trọng tâm:** `experiments/evaluator.py`, `integration/continuous_account.py`, `quantbt_bridge/intent_tape.py`, `selector/alpha_schemas.py`, `alphas/a_*.py`, `experiments/calendar_baseline.py`. Reuse existing APIs trong `quantbt_candidate`, patch candidate hooks nhỏ nếu thật cần, không sửa QuantBT production.

**Outputs:** `RF-02/report.*`, alpha/route registry, actual Mode 4 baseline artifacts, golden fills/rates, scalar/audit parity, timing and availability tests, benchmark profile, thin adapter diff, failed intent ledger.

**Exit:** paired eligible cells financial-correct; actual Mode 4 in use; no fabricated fills/nonconverged score; pilot within measured budget hoặc hotspot/fix rõ. Nếu HASH blocked, core study có thể discovery partial nhưng không claim bao phủ 4 alphas; phase overall phải ghi PARTIAL cho deliverable đó, không COMPLETE giả.

---

## RF-03 — Regime causal đúng và lịch Mode 4 động thực sự

**Mục tiêu:** sửa A09–A14 trên đường primary scheduler và giữ secondary response trung thực. Chứng minh treatment có thể khác baseline do thông tin hợp lệ, không chỉ rename arms.

### RF03.1 — Context và model-vintage repair

Economic panel/raw features giữ sign/level, source groups/availability. Fit residual chỉ quality/novelty. Fit scaler inner-train-only. Model namespace mapping common-coordinate, one-to-one khi K giống nhau; unmapped states có status rõ, no artificial transition. Warm filter bằng history available trước ready; decision emissions old immutable.

Unit DP/reference existing reused; sparse/HMM additions không bắt buộc. Cần logs centroids/raw descriptors/weights/empty/dead states/residuals/readiness. Membership score không gọi calibrated probability.

### RF03.2 — Model ladder có ngân sách, chọn đúng trong development

M0 + JM K2/K3 là starting ladder. Lambda/cadence training memory vài choices rationale theo feature loss scale/holding horizon. Kiểm contributions của price/activity/market context trước data mới. Feature ablation same cohort + fixed future paired utility/rank/risk target; reconstruction chỉ diagnostic. Outcome episodes phải kết thúc trước training decision; purge theo overlap thực.

K/cadence chọn trong development là hợp lệ, nhưng outer/confirmation không dùng để retune. Mỗi attempt lưu regardless outcome. Không chạy toàn bộ K × lambda × timeframe × bank × cost mọi combos mặc định; sequential decisions dựa trên diagnostics có registration version mới.

### RF03.3 — Online dynamic fold/refit controller

Implement/reuse controller như Mục 7.3–7.4. Market transition hợp lệ không phải model-version event. UNKNOWN transition có explicit novelty policy hoặc fallback. Cùng minimum spacing/max-age/budget actual, không six bins/count forced.

Search requests đóng cutoff; if delayed, incumbent continues. Refit latency có fixed conservative operational budget hoặc measured schedule scenario frozen trước market test; code optimizer chạy nhanh trên máy khác không được backdate future params. Coalesce/supersede deterministic. Event log show trigger → search → selection → ready → activation → first affected order.

Dynamic controller chỉ thay timing của Mode 4; training memory/start formula và selector giữ nguyên. Không chia một price series thành các đoạn cùng regime rồi ghép thành artificial returns.

### RF03.4 — Treatment-strength tests và synthetic controls

Với regime tape cố định có transition hợp lệ, chứng minh M4_REGIME tạo search request ở đúng thời điểm, gọi Mode 4 thật và có thể thay effective params/trades trong positive-control world. QuantBT vẫn là simulator của positive control; ground-truth labels của thế giới giả lập chỉ dùng để chấm diagnostics, không làm input đặc quyền cho policy.

Null world/placebo không bắt false-positive rate=0 tuyệt đối; report statistical support theo registered test. Namespace-only/missing-data world không trigger sai. No changes/no qualified candidate vẫn keep đúng. Thực market zero-switch có thể hợp lệ sau controller pass; report reasons không kết luận universal no edge.

### RF03.5 — Secondary response/bank disposition

Primary outcome không dùng E. Nếu sửa E trong phase: wire actual per-cell policy, warm episode context, actual campaign book/indicator readiness, proper support/cost, specialists & quality gates. Không copy D. Phải có P04 residual counterexample corrected và positive E integration, full estimate panel retrievable.

Nếu chưa chạy E market: unit/model repairs có thể DONE nhưng economic evidence status `SECONDARY_NOT_EVALUATED`; old E economic claims vẫn invalid. Không trì hoãn primary timing study vì xây lại response architecture phức tạp không cần thiết.

**Files trọng tâm:** `experiments/regime_schedule.py`, `regime/emissions.py`, `regime/registry.py`, `regime/model_selection.py`, `regime/ablation.py`, `scripts/fit_regime_model.py`, `scripts/run_response_policy.py`, `policy/*`, factorial runner wiring.

**Outputs:** `RF-03/report.*`, causal model registry/emission tapes, current coordinate contract, dynamic controller specs, synthetic positive/null results, scheduled job/activation logs, model design selection manifest, secondary disposition.

**Exit:** prefix/streaming parity và eligibility pass; no namespace false change; treatment implemented as defined; model/opportunity not yet claimed positive from labels. Poor fit/outcomes là reportable, không fail phase nếu code đúng.

---

## RF-04 — Thí nghiệm nhanh trên alpha thật, đóng metrics và decay

**Mục tiêu:** có corrected paired empirical results cho Mode 4 regime timing, không dùng audit historical curves làm new evidence. Giảm repeated work và chỉ mở complexity khi pilot có lý do.

### RF04.1 — Pilot rồi scale có điều kiện kỹ thuật

Chạy M4_CAL/M4_REGIME trên 2 cells qualified với bounded cutoffs/trials. Chọn cells trước PnL, đủ regimes/trades/warmup. Sau technical pass scale theo shards tới 4 alphas×5 symbols hoặc report actual coverage/blockers. Không bỏ losers, không thay alpha giữa arms.

Model tapes reuse per-symbol, training evaluations keyed cutoff; fixed-calendar and dynamic cohorts cùng dates/economics. Refit không mutate deployment state. Failed units retained null status, không zero. Reuse old data/indicator panels chỉ khi hashes và availability phù hợp; old economic output sau fee fix invalidated.

### RF04.2 — Full Mode 4 transparency

Tại mỗi cutoff ghi exact input hashes/training range, parameter schema, TPE distributions/trials/states, seed, intermediates/pruning, unique evaluation references, Mode 4 temporal/plateau/penalty decomposition, pre/post incumbent guard, selector fallback, selected digest và actual activation.

Mode 4 insufficient cluster hỗ trợ fallback nếu baseline contract có; cả arms dùng same fallback. Report fraction of selections fallback; không claim plateau đã được kiểm tra đầy đủ nếu toàn fallback. Search failures không thành−1e9 financial COMPLETE.

### RF04.3 — Metrics/decay panels từ engine data

Tạo raw/canonical metrics và D1/D2/D3 Mục 6. Include PF definition, trade support, metric undefined reason, first observation cost, boundary PnL reconciliation. Age diagnostics chỉ subset kế hoạch nếu budget limited, có selection rule ex ante; final comparison không dùng diagnostic future information.

Common reporting windows daily/monthly cố định cho cả hai arms; operational folds vẫn dynamic. `candidate_decay` native giữ raw/penalized fields; không sửa Mode 4 thành Mode 1 tối ưu theo decay để thỏa metric request.

### RF04.4 — Controls và opportunity diagnostics có thứ tự

Sau primary pilot: CAL_MATCHED bắt buộc nếu refit counts/compute khác rõ; delayed state và placebo theo preregistered budget; risk-only khi contribution có thể do exposure. Optional selector factorial để hiểu Mode 4 plateau; keep primary unchanged.

Nếu cells gần như cùng trades, xuất funnel: valid observations→triggers→searches→different params→activated→different orders. Nếu candidates behavior identical, inspect parameter route/geometry. Nếu route đúng, support tốt mà ranks không đổi, báo `LOW_PARAMETER_OPPORTUNITY` thay vì cứ thêm features. Không dùng hindsight best-per-segment PnL làm tradable curve.

### RF04.5 — Profiling và bounded refinement

Đo toàn stage cost, audit counts, rows/bytes, CPU budget và latency. Nếu benchmark chậm do `_sweep`/DataFrame rebuild còn active, fix root cause, not lower resolution silently. If candidate budget insufficient to reach meaningful Mode 4 mode, review allocation explicitly; do not present toy trial counts as final proof.

Discovery changes allowed trước design freeze, all hypotheses ledger. Freeze one primary design trước RF05; record no promising design nếu không có. Không chọn new positive cell rồi gọi aggregate 20 cells.

**Outputs:** `RF-04/report.*`, corrected runs/trials/folds/pair panels, all 20 cell statuses, D1/D2/D3 tables, controls, full decision funnel, runtime budget/performance report, design freeze or no-promising-design.

**Exit:** mọi contrast có validity/status/data-role đúng; primary corrected outcomes có thể positive/negative/inconclusive; không cần edge mới close technical phase. Nếu còn A01–A08 active ở cell thì contrast NOT_EVALUABLE, không statistical summary valid.

---

## RF-05 — Frozen đánh giá lại, phản chứng, báo cáo/handoff có thể kiểm tra

**Mục tiêu:** kết luận không vượt evidence; deliver repaired code và reproducibility cho Claude/OpenCode/user, không chỉ một bảng best params.

### RF05.1 — Freeze và xác nhận contamination

Khóa code/model/alphas/selector/scheduler/parameter domains/costs/budgets/primary metrics trước confirmation run. Historical periods đã dùng tìm bugs/thử design là exploratory/nested retrospective, không đổi thành untouched sau khi sửa. Nếu không còn clean holdout, có thể completed technical + retrospective claim và prospective registered protocol, **không tự chạy live**.

Không coi technical invalidity và holdout contamination là một trạng thái: technical-correct nhưng retrospective vẫn có evidence scope hẹp. Tránh hai cực “invalid mọi thứ” hoặc “đã chứng minh live edge”.

### RF05.2 — Recompute đúng tất cả affected outputs

Corrected fee/categories/cutoffs làm thay selections; cần rerun full impacted chain, không rescale old curves. Fixed design new runs phải dùng current verified engine hashes. Score/audit selected rerun parity; unit overrides biến thành explicit test scenario không sửa primary.

Run cost/latency/missing data stress trên subset scopes đã freeze; all arms same assumptions. Deep latent book không bắt buộc. Chỉ statistical bootstrap từ results không financial rerun mới; different execution model phải labeled separately.

### RF05.3 — Statistical claims và potential decision

Paired/common-shock inference, same sampling, undefined metrics flags, MDE units, multiplicity, support. Kết luận riêng theo alpha/symbol và registered aggregate. Các phát hiện secondary phải mang nhãn exploratory.

Trả ba câu hỏi tách:

1. **Thử nghiệm có đúng không?** Implementation/economic/data/cutoff validity.
2. **Trong scope đã thử có lợi ích không?** Current metrics + net paired utility + decay + cost/risk/uncertainty.
3. **Có hướng nghiên cứu tiếp có cơ sở không?** Opportunity/info/activation bottleneck với evidence, không lời hứa tăng độ phức tạp model sẽ thắng.

Negative result được giữ. Nếu CI chưa loại mức δ, `INCONCLUSIVE`, không `RULED_OUT`. Nếu no treatment actions do gates, nói policy hiện tại không adapt; không phủ nhận market information tổng quát. Nếu parameter rank không thay đổi và no meaningful gain bounded, scope-negative hợp lệ.

### RF05.4 — Phase reports, JSON và artifact integrity

Run schema/cardinality/reconstruction validation: every trial retained, every selection joins model/cutoff/parameter version/actual account, all required data ready flags. Raw/warmup/runtime failure không silently drop. Fix evidence manifest self-hash bằng external root actual digests; no self-referential invalid entry.

`simulation_complete` khác `audit_complete`; success chỉ sau required flush. JSON chuẩn không NaN/Inf; typed status + null. Complete report tạo từ saved artifacts không từ notebook RAM. Charts được build bằng .py từ chart data refs; no hand-tuned selective curves.

### RF05.5 — Code/package/docs handoff và guardrails

Chỉ small lab integration changes và read-only package binding; không merge production hoặc sửa alphas ngoài scope. Một canonical runner thay scripts copy-paste. README/CLAUDE.md/OpenCode rules thống nhất phase/status/run commands/claims. Source patch diff + dependency lock + verified sample + exact commands + resource config.

Handoff gồm safe rollback về corrected baseline, old evidence immutable và explicit invalidation. Nếu engine hook mới thật cần, đưa upstream proposal có tests, chưa tự publish QuantBT. Không thêm `quantbt-features` vào core, không bỏ Python oracle hoặc nới tolerances để qualify.

**Outputs:** `RF-05/report.*`, final `claim_report.json`, common-window/decay/equity artifacts, leakage matrix, remaining blockers, reproducibility bundle manifest, patch/handoff docs, rerun commands và future study registration nếu cần.

**Final exit:** `TECHNICALLY_VALID` cho supported scope + economic status có bằng chứng + complete audits. Edge không bắt buộc dương; correctness và honesty là bắt buộc. Không cho `COMPLETE` toàn 4 alphas khi HASH vẫn blocked; có thể `PARTIAL_TECHNICAL_CLOSURE` với scope cụ thể.

---

# 10. Rules báo cáo cho từng phase

Những rules này **bổ sung** rules hiện có của từng agent. Nếu rules khác mâu thuẫn no-leakage, source provenance hoặc scope thì record conflict, không tự bỏ safety. Người viết và người review có thể phân công giữa Claude/OpenCode; không tự gọi “independent review” chỉ vì hai agents dùng cùng context/tests.

## 10.1 Mỗi phase bắt buộc Markdown + machine-readable JSON

Nơi ghi đề xuất, agent map vào existing evidence writer:

```text
evidence/corrective_mode4_v3/<study_id>/RF-01/{report.md,report.json,...}
...
evidence/corrective_mode4_v3/<study_id>/RF-05/{report.md,report.json,...}
```

Mỗi report phải có:

1. Objective và hypothesis thực sự test; thứ gì không được test.
2. Source/data/alpha/model/economic/version identity; requested và actual resolved runtime.
3. Findings được sửa, expected behavior, failing-before/passing-after tests, source symbol/line/hash và impacted scopes.
4. Test/sample budget: raw period, train/test/warmup, candidates, trials, seeds, visited bars, execution resolution, registry validity.
5. Kết quả kỹ thuật, kết quả thị trường, synthetic/mocked được tách rõ.
6. Metrics hiện có + new canonical metrics + decay; units, definition, aggregation/support/null reasons.
7. Runtime breakdown: cold/warm, native/Python/copy/report/model, RSS, canceled budget jobs, actual vs planned work.
8. **Proof capability:** pipeline đã đủ điều kiện phát hiện/bác bỏ hypothesis nào? Positive control/null control ra sao? Treatment khác thật không?
9. **Potential assessment:** evidence cho opportunity, information value, decision response, activation, costs; bottleneck nào và falsifiable next action.
10. Claim limitations: contamination, insufficient support, blocked cells, error counts, revised data/fee assumptions, missing artifact.
11. Exit decision và remaining tasks; review notes; không đóng từ checklist file presence.
12. Exact rerun recipe, output hashes, traceability links và next phase handoff.

Không chỉ báo “196 tests pass” hoặc “không có edge”. Phải chỉ ra test chạy code nào, actual rows nào và conclusion scope.

## 10.2 Minimal phase report JSON schema sketch

```json
{
  "schema": "regime_lab.corrective_phase_report.v3",
  "phase_id": "RF-01",
  "status": "PLANNED",
  "study_id": null,
  "source": {
    "archive_sha256": "2765bd069a5caf16921c3df03dfafd8f090f4fdd2de5e1550a5ce390c87a980f",
    "candidate_commit": null,
    "candidate_source_manifest": null,
    "quantbt_core_version": "1.1.1",
    "native_artifact": null,
    "actual_import_origins": []
  },
  "objective": "Mode4 per_fold_causal calendar vs causal regime refit",
  "registered_arms": ["M4_CAL", "M4_REGIME"],
  "findings": [],
  "tests": {"passed": 0, "failed": 0, "skipped": 0, "artifact_refs": []},
  "market_runs": {"planned_cells": 20, "executed_cells": 0, "valid_pairs": 0, "blocked_cells": []},
  "metrics": {"raw_quantbt_ref": null, "canonical_ref": null, "decay_panel_ref": null},
  "performance": {"wall_seconds": null, "cpu_seconds": null, "peak_rss_bytes": null, "actual_candidate_bar_visits": null},
  "proof_capability": {"technical_validity": "NOT_TESTED", "positive_control": "NOT_TESTED", "treatment_reached_execution": "NOT_TESTED"},
  "potential": {"level": "UNASSESSED", "evidence_refs": [], "falsifiable_next_step": null},
  "claim": {"validity": "NOT_TESTED", "statistical_status": "NOT_EVALUABLE", "scope": null},
  "limitations": [],
  "review": {"author": null, "reviewer": null, "disagreements": []},
  "handoff": {"next_phase": "RF-02", "blocking_findings": []}
}
```

Đây là template hợp lệ JSON, **không phải report đã hoàn tất**. CI từ chối `status=COMPLETE` khi các fields bắt buộc chưa có. Không nhét template values vào final records để giả completeness.

## 10.3 Disposition cho mỗi finding

```text
OPEN_REPRODUCED
FIXED_PENDING_TEST
FIXED_AND_VERIFIED
ALREADY_FIXED_WITH_SOURCE_AND_TEST_EVIDENCE
QUARANTINED_UNSUPPORTED_PATH
SECONDARY_REPAIRED_NOT_MARKET_EVALUATED
BLOCKED_WITH_REASON
```

`NOT_BENEFICIAL` chỉ phù hợp performance experiment, không là disposition của fee bug/backdate/fabricated fills. `QUARANTINED` chặn mọi arm phụ thuộc path đó, không bỏ bug rồi tiếp tục score.

## 10.4 Trục đánh giá tiềm năng — không ép positive narrative

| Level | Điều kiện báo cáo | Hành động tiếp |
|---|---|---|
| `UNASSESSED` | Pipeline chưa đúng hoặc chưa có dữ liệu | Sửa technical trước |
| `LOW_PARAMETER_OPPORTUNITY` | Các candidates thực hành xử/rank gần nhau, đủ support để thấy | Kiểm schema/diversity; không tự thêm model lớn |
| `OPPORTUNITY_UNINFORMED` | Rank reversals có, context chưa dự báo được | Feature/horizon representation ablation nhỏ |
| `INFORMATIVE_NOT_ACTIONABLE` | Context có conditional evidence nhưng activation/cost/support chặn | Policy/timing evidence; không sửa labels hậu nghiệm |
| `ACTIONABLE_UNCONFIRMED` | Repaired discovery có lợi ích nhưng chưa confirm | Freeze và giữ scope |
| `POSITIVE_WITHIN_SCOPE` | Valid confirm/replay có lợi ích và constraints đạt | Bàn nghiên cứu/triển khai sau, không auto live |
| `NEGATIVE_WITHIN_SCOPE` | Valid evidence loại mức δ trong scope tested | Giữ kết quả âm, document limit |
| `INCONCLUSIVE` | Uncertainty rộng/support ít | Không viết “không có edge”; mở tiếp chỉ khi có rationale |

Potential không thay primary result, không tạo một “quality score” tổng che blockers. Mỗi khuyến nghị cải thiện phải nêu chi phí/budget, expected mechanism, test và stop condition.

## 10.5 Records cần để recompute và làm chart

```text
run_manifest
source_and_data_manifest
alpha_semantic_and_route_registry
search_space_snapshot
trial_ledger + trial_intermediate_values
candidate_evaluation_index
mode4_objective_components / selector_fallbacks
regime_model_registry / causal_emission_tape
trigger_search_ready_activation_ledger
parameter_version_by_time
QuantBT account/equity + required order/fill/trade evidence
raw_metric_contract / canonical_metric_panel
IS_OOS_decay / age_decay / adjacent_fold_changes
paired_daily_comparison / statistical_resample_manifest
validity_claim_report / historical_invalidation
runtime_profile / resource_usage / reproduction_manifest
```

JSON/JSONL giữ decisions/statuses; Parquet/Arrow/numeric files giữ tables lớn nếu existing writers hỗ trợ. Không bắt mọi bar thành dictJSON. Full research metadata phải truy xuất được ngay cả profilefinancial score; samples có actual count/policy. No NaN/Inf JSON numbers. No success before required flush.

Charts bắt buộc từ data: continuous daily equity/drawdown, parameter activation overlay với regime/ready delays, raw vs penalized IS/OOS metrics, age-decay median+support, PF/return/SR distributions với undefined counts, per-cell paired effects, decision funnel, cost/runtime. Không lấy colored regime chart đẹp làm edge evidence; no interpolation untested params như evaluated surface.

---
# 11. Bộ kiểm thử nghiệm thu

Các ID dưới đây là **tests phải có hoặc phải map tới tests thực đang có**; không phải kết quả đã pass trong lượt hợp nhất. Synthetic cases dùng để kiểm contract; conclusions về time edge chỉ dùng các real-alpha experiments hợp lệ. Không chạy full-history market study chỉ để kiểm một lỗi tính phí hoặc enum.

## 11.1 Nhóm contract, execution và alpha

| ID | Tình huống | Expected behavior / evidence |
|---|---|---|
| T01 | Một buy và một sell có notional biết trước | Actual fees khớp one-way rate ở từng route; không charge half/double |
| T02 | Giá thay đổi khi đang giữ position với allocation bằng 10% | Phân biệt transition-only equity sizing với continuous rebalancing; label đúng contract |
| T03 | Initial candidate chỉ sẵn sàng sau account start | Không active ở bar 0; incumbent hợp lệ hoặc không mở vị thế trước ready |
| T04 | Selection cutoff trước fit-ready và indicator-ready | Effective time không sớm hơn cả ba và execution boundary |
| T05 | Sửa toàn future suffix sau T | Features, regime emissions, selected params và commands có hiệu lực trước T không đổi |
| T06 | Close-generated intent chạy trên next-open route | Fill không tại close đã dùng quyết định; không double shift; no future high/low |
| T07 | Prepared same-close route được đề nghị cho next-open alpha | Binding gate reject hoặc chọn engine đúng; không thay `close=open` để lách |
| T08 | HTF 15m/1h signal và execution 1m | Chỉ closed HTF observation được dùng; map timestamp đúng; protection vẫn 1m |
| T09 | Actual fill có slippage/reject/partial quantity | Adapter nhận đúng actual fields, không cập nhật từ raw next-open dự đoán |
| T10 | Nhiều fills cùng một bar, khác IDs/sequence/price | Không collapse bằng dictionary keyed chỉ theo bar |
| T11 | Cùng exit bar nhưng khác price/qty/reason | Trace comparator fail; không dùng `set(bar_ids)` làm convergence |
| T12 | Unmapped intent hoặc execution invalid | Không trả financial score; fail/block với full reason |
| T13 | Callback phát staged commands rồi raise | Không submit partial staging; không tự retry dirty strategy state |
| T14 | Một order business-rejected trong batch hợp lệ | Không tự biến cả batch thành atomic package; giữ acceptance contract |
| T15 | HMA stop-mode categories | Mỗi allowed category map đúng enum; unknown reject; fixture có behavioral difference |
| T16 | Thêm một ignored/fixed parameter | Không thay effective execution hoặc làm tăng coverage/diversity giả |
| T17 | VWAP dynamic protection amendment | Actual amend/replace tới QuantBT, effective đúng phase; không chỉ ghi unmapped |
| T18 | HMA entry gap làm bracket invalid | Corrective EXIT được thực hiện/reject minh bạch; không booked instant favorable profit |
| T19 | HASH ladder partial TP | Quantity còn lại, target order và fee đúng; không chỉ lấy target cuối |
| T20 | SignalCombine source long-flat | Không tự mở short hoặc multiply leverage vì đọc sai signal amplitude |
| T21 | Protective orders còn mở khi params đổi | Old parameter version còn sống đến terminal hoặc migration có policy rõ |
| T22 | Bắt đầu episode sau một warmup prefix | Indicators đã warm; episode account rule rõ; không đo cold-start như stable behavior |
| T23 | Symbol bị thiếu bars/khác calendar hoặc trước listing | Không relabel bằng same length, không fabricate zero returns trước tồn tại |
| T24 | Spot/perp, tick/lot/funding coverage khác nhau | Contract và scope được ghi đúng; không claim venue-exact ngoài capability |

## 11.2 Nhóm Mode 4 và causal schedule

| ID | Tình huống | Expected behavior / evidence |
|---|---|---|
| T25 | Baseline public Mode 4 | Actual `mode_4_is_only_robust`, `per_fold_causal`, `is_only_robust` và endpoint scorer được gọi |
| T26 | Tạo utility rồi gán trường `mean_is_sharpe` | Unit/schema test reject; không coi đây là stock Mode 4 baseline |
| T27 | Thay outer OOS data/outcomes | Không ảnh hưởng selection trước outer start; OOS không vào TPE/selector |
| T28 | Dynamic fold provider nhận lịch cố định như baseline | Cùng cutoff, trials, seed, selector và economics cho equivalent output |
| T29 | Cùng model state, đổi namespace hoặc permute IDs | Không tự sinh market-change trigger; mapping dùng common coordinates |
| T30 | Emission `decision_eligible=false`, missing/stale/unknown | Không dùng như valid market state; novelty trigger nếu có là policy explicit riêng |
| T31 | Không có regime changes trong cả interval | Giữ incumbent/max-age policy đã freeze; không raise vì thiếu đúng sáu refits |
| T32 | Inference → trigger → search → ready → activation | Mọi state transition và delay truy được; jobs không backdate hoặc supersede sai |
| T33 | So hai cutoffs có số trials/cache hits khác nhau | Giữ đúng audit/budget semantics; không tái dùng candidate tương lai để ép matched set |
| T34 | Sequential TPE versus batch mode | Không gọi candidate-sequence parity nếu lịch ask/tell đổi; report distinct contract |
| T35 | Candidate reuse cache | Key bao phủ economic state/cutoff/alpha/intent; mọi trial vẫn có record riêng |
| T36 | Score cache ở một pruned/failed evaluation | Không trả như complete; intermediate reports/pruner semantics không mất |
| T37 | E path chưa nối response | `NOT_IMPLEMENTED_AS_SPECIFIED` và disabled; không copy D rồi gọi zero effect |
| T38 | Synthetic recurring-state world có advantage đã biết | Full pipeline có thể đề xuất và thực hiện change đúng khi đủ evidence/cost; dùng QuantBT để simulate |
| T39 | Synthetic null world hoặc delayed/placebo state | False-switch/gain được đo; không bắt model phải tìm edge |
| T40 | Toàn pipeline regime off | Cùng fixed params/intent/economics cho baseline parity trên actual engine |

## 11.3 Nhóm model, response và uncertainty

| ID | Tình huống | Expected behavior / evidence |
|---|---|---|
| T41 | Bull và bear đều sát centroid riêng | Economic contexts vẫn khác; zero residual không bị coi là cùng điều kiện |
| T42 | Refit scaler/model giữa versions | Context comparison và state mapping có hệ tọa độ chung; không compare raw standardized values từ hai scalers tùy ý |
| T43 | Inner fold preprocessing | Scaler/selection được fit trên inner train; future inner-validation mutation không đổi train fit |
| T44 | Thêm data group nhưng target/coverage phải cố định | Ablation đo cùng target/cùng cohort; reconstruction của hai target spaces không bị gọi là incremental decision value |
| T45 | Episode outcome kết thúc sau decision cutoff | Không được dùng trong response estimate hiện tại |
| T46 | Một đoạn liên tiếp chứa nhiều weighted episodes | Không coi số mảnh rời do top-weights tạo ra là số observations độc lập; report ESS/coverage/recurrence riêng |
| T47 | Candidate bank chứa global anchor và specialists | Quality/local-risk gates thật; behavioral diversity; no future discoveries |
| T48 | Projected switching cost theo current account | Cùng đơn vị return/allocation/horizon; không mặc định turnover=1 cho 10% entry |
| T49 | Parameter recommendation không active do open campaign | Ghi recommendation/approval/activation separately; không tính opportunity như đã execute |
| T50 | Model K/cadence được chọn từ development | Choice/rejected alternatives có ledger; không đổi confirmation sau khi xem kết quả |

## 11.4 Nhóm metrics, báo cáo và performance

| ID | Tình huống | Expected behavior / evidence |
|---|---|---|
| T51 | Loss đúng tại đầu block | PnL được tính; cộng money deltas của partition bằng total account delta |
| T52 | First fill/fee ở observation đầu | Dùng initial equity trước observation; không mất initial cost |
| T53 | Returns trên hai windows khác độ dài | Sharpe dùng same annualization/time sampling, không `sqrt(number_of_rows)` để xếp hạng |
| T54 | Profit Factor observations khác trade PF | Tên/denominator được giữ rõ; undefined/no-loss/no-trade có status, JSON không Inf/NaN |
| T55 | OOS metric trừ trade-frequency penalty | Raw Sharpe và penalized selector metric được lưu riêng, decay đúng nhãn |
| T56 | Negative/near-zero IS Sharpe hoặc return | Không ratio decay tùy tiện; additive gap và status dùng theo spec |
| T57 | Đổi params giữa hai folds | Không gọi chênh lệch adjacent-fold là pure parameter decay |
| T58 | Dynamic folds có length khác nhau | Primary comparison trên common daily account path; không trung bình fold Sharpes |
| T59 | Equity-fraction thay fixed notional | MDE/turnover units được đăng ký lại bằng actual account economics, không tái dùng factor cũ |
| T60 | P0 invalidity kèm CI trông rõ âm/dương | Claim `NOT_EVALUABLE`; không giữ subclaim `RULED_OUT`/`SUPPORTED` |
| T61 | Confidence interval chứa meaningful positive và zero | `INCONCLUSIVE`; không đổi thành “không có edge” |
| T62 | Một số cells chưa sẵn sàng hoặc failed | Đủ 20 cell statuses; không thêm zero PnL hoặc bỏ denominator im lặng |
| T63 | Audit duplicate/pruned/failed trials | Trial ledger đủ, statuses nguyên nghĩa; unique evaluation count tách trial count |
| T64 | Sample estimates ghi 4.000 nhưng giữ 400 | Cardinality test fail; sample policy và actual counts phải khớp |
| T65 | Required audit writer flush lỗi | Execution có thể complete nhưng overall run chưa success; fail/partial có evidence |
| T66 | Cache enabled/disabled và retained views | Same economics; không reuse mutable buffers còn bị result/view giữ; cache key/memory safe |
| T67 | T0/T1 pilot vượt budget | Ghi timeout kỹ thuật/profiling, không bad strategy score, không tự giảm execution fidelity |
| T68 | Native backend không có capability nhưng request require | Fail-fast hoặc documented route change đúng contract, không metadata Rust giả |
| T69 | Rebuild report từ artifacts | Metrics, claims, charts data và trial joins khớp; không phải chạy lại engine để format report |
| T70 | Khôi phục evidence từ Markdown này | 20 original ZIP members đúng bytes/hash; original self-manifest warning còn được giữ |

### Rules cho metamorphic tests

Không dùng invariant thiếu điều kiện: chia một fill thành hai fills có thể thay phí nếu fee có minimum/rounding theo từng fill; permutation symbols có thể đổi kết quả nếu sequential admission priority là một phần contract; scale price không giữ tương đương khi có tick/lot/min-notional. Mỗi test ghi điều kiện áp dụng. Independent tiny oracle phải dùng spec đúng, không copy implementation đang bị nghi ngờ.

### Rules chạy test

Các unit probes kiểu T01 chạy trên arrays ngắn và fixtures cố định. Source/integration tests dùng temporary directories, interpreter hiện tại hoặc một explicit qualified interpreter; không hardcode `/root/.../.venv/bin/python`. Market pilots có data pack nhỏ cùng hashes; không dùng synthetic result để hoàn thành real-alpha outcome. Toàn bộ source audits cũ giữ nguyên status lịch sử; số lượng tests trong chương này không phải số tests đã pass.

---

# 12. Handoff, claim và điều kiện kết thúc

## 12.1 Bảng kết quả bắt buộc cho Claude và OpenCode

Bản cuối phải trả lời bằng evidence, không bằng lời khẳng định “đã implement”:

| Câu hỏi | Kết quả phải báo |
|---|---|
| Các lỗi audit nào thực sự đã sửa? | A01–A16, D01–D08, N01–N05 có disposition, source diff, regression và affected reruns |
| Baseline có đúng Mode 4 per-fold causal không? | Actual public config/call path/selector/evaluator/import identity |
| Regime thay đổi việc refit đúng mục đích không? | Qualified triggers, no namespace-induced false transitions, no future bins requirement |
| Đã thử trên bốn alpha thật chưa? | 4×5 coverage table; declared unsupported/failed status, không zero giả |
| Có tận dụng vectorized/native nhanh không? | Route matrix và measured public timings, cùng economic contract |
| Kết quả hiệu quả hơn không? | Continuous net return/Sharpe/PF/DD, paired differences/uncertainty/constraints |
| Có giảm decay không? | IS→OOS, same-parameter age decay và adjacent-fold variation riêng biệt |
| Cải thiện do đâu? | Timing vs cadence/compute vs risk vs selector; controls đủ cho claim tương ứng |
| Chưa chứng minh vì sao? | Invalidity, thiếu opportunity, representation, activation delay, sample/support hoặc economic null |
| Có reproducible và an toàn không? | Source/data/artifact hashes, commands/env, restored package origins, protected paths unchanged |

## 12.2 Claim rules cuối cùng

**Execution validity**, **implementation fidelity**, **statistical evidence**, **economic usefulness** và **deployment readiness** là các chiều riêng.

Một record có thể hợp lệ về execution nhưng `INCONCLUSIVE` về effect. Một comparative gain có thể dương khi cả hai strategies đều lỗ; đó chưa phải recommendation deploy. Một model mô tả thị trường tốt nhưng không chọn params tốt hơn chỉ có descriptive value. Một policy bị chặn gần như mọi lần là kết quả của policy cụ thể, không chứng minh mọi regime-aware WFO bất khả thi.

Primary claim nên có dạng:

> Trên những alpha/symbols, date range, parameter schema, Mode 4 settings, data vintages, execution/sizing/cost contracts và resource budget đã đăng ký, regime-driven refit [có / không đủ evidence về / bị loại mức lợi ích đáng quan tâm của] incremental value so với calendar baseline; mức thay đổi decay và các giới hạn cụ thể được báo kèm.

Không được viết “regime không có time edge” không giới hạn scope; cũng không viết “regime work” chỉ vì một cell thắng hoặc colored chart đẹp. Nếu dùng lại toàn lịch sử từng xem, gọi kết quả là corrected retrospective/prequential evidence theo data-use audit; không tái đặt tên untouched holdout.

## 12.3 Quy tắc dừng và mở rộng

- Dừng inference khi validity fail; repair và rerun affected stages, không sửa final curve thủ công.
- Nếu pipeline đúng nhưng parameter bank không có diversity/rank reversals hữu ích, báo low opportunity. Chỉ mở search/model nếu có hypothesis mới rõ, không tăng vô hạn đến khi thắng.
- Nếu opportunity có mà context không informative, thử một feature/horizon/representation delta có budget và validation riêng.
- Nếu context informative nhưng activation muộn hoặc cost cao, thử migration policy riêng; không lùi effective timestamps.
- Nếu evidence đủ loại meaningful effect trong scope, chấp nhận kết luận âm. Negative result có giá trị không thấp hơn positive result khi thí nghiệm hợp lệ.
- Nếu uncertainty rộng, ghi `INCONCLUSIVE`; không biến số lượng bars lớn thành số observations độc lập giả.
- E_RESPONSE_V2 và selector extension chỉ mở rộng kết luận khi đã được implement và market-evaluate thật. Repair hoặc quarantine các paths cũ là bắt buộc; chứng minh E thắng không phải prerequisite của primary Mode 4 timing contrast.

## 12.4 Entry points và commands của corrective runner

Reuse scripts/CLI hiện có nếu chúng có cùng contracts. Không tạo một framework CLI mới chỉ để có thêm cấu trúc. Runner cuối phải hỗ trợ các thao tác sau, tên flags được map tới actual implementation trong `reproduction_manifest.json`:

```text
validate-environment / validate-protocol / inventory
run-regressions
run-real-alpha-parity-pilot
run-mode4-calendar
run-mode4-regime
build-metrics-and-decay
run-controls
rebuild-phase-report
rebuild-final-report
verify-evidence
```

Mỗi command có `--dry-run` hoặc equivalent cho biết inputs, output directory mới, estimated work từ pilot và resource cap **trước khi chạy job lớn**. Default không overwrite artifacts. Không dùng launcher ví dụ chưa implement làm proof. Agent phải trả actual executable command, exit code và environment identity trong từng phase report.

## 12.5 Handoff manifest đề xuất

Schema sketch dưới đây là yêu cầu đầu ra; không phải certificate đã được cấp:

```json
{
  "schema": "regime_lab.mode4_corrective_handoff.v1",
  "status": "PLANNED",
  "primary_question": "mode4_per_fold_causal_regime_timing_vs_calendar",
  "phases": ["RF-01", "RF-02", "RF-03", "RF-04", "RF-05"],
  "execution_validity": "NOT_RUN",
  "mode4_binding": "NOT_RUN",
  "alpha_coverage": {"planned": 20, "valid": 0, "blocked": 0, "not_run": 20},
  "timing_effect": "NOT_EVALUABLE",
  "decay_effect": "NOT_EVALUABLE",
  "audit_transparency": "NOT_RUN",
  "performance_qualification": "NOT_RUN",
  "original_evidence_preserved": true,
  "production_modified": false,
  "automatic_merge_or_publish": false
}
```

Manifest thật phải tham chiếu actual source/config/data/result IDs và reports; các statuses được dẫn xuất từ evidence. Không đặt `PASS` bằng tay để hoàn thành phase. Agent rules hiện tại tiếp tục áp dụng; rules về validity, claim và báo cáo của tài liệu này bổ sung và không được lược bỏ vì report template cũ ngắn hơn.

## 12.6 Định nghĩa hoàn thành

Năm phase chỉ được ghi hoàn thành khi các deliverables bắt buộc đã được nghiệm thu. Kết quả nghiên cứu hợp lệ có thể là dương, âm hoặc `INCONCLUSIVE`; `BLOCKED/PARTIAL` phải giữ nguyên là trạng thái chưa hoàn tất, không đổi thành COMPLETE. Mọi giới hạn về khả năng kết luận trong scope phải được giải thích đầy đủ. Không gọi market study hoàn tất nếu chỉ mới thêm tests/Markdown, và không gọi “đã chứng minh không có edge” vì timeout, không đủ support hoặc implementation chưa nối.

Không hứa toàn ma trận nhiều năm chạy trong một số phút cố định. Cam kết kỹ thuật là: unit tests nhỏ, pilot có budget, prepared/native reuse thực, shards có thể resume/reproduce, báo actual compute, và không mất financial semantics/audit để đạt tốc độ.

---

# 13. Nguồn, phạm vi kiểm chứng và cách dùng phụ lục

## 13.1 Ba đầu vào audit được hợp nhất

Phụ lục bên dưới giữ toàn bộ nội dung của ba deliverables cũ trong một file mới. Hai Markdown cũ cũng là members của evidence ZIP, nên mỗi nội dung được lưu **một lần**, không nhân bản thêm.

Source findings có hiệu lực với snapshot được định danh bằng archive/file hashes. Nếu checkout hiện tại đã thay đổi, agent phải re-map location và run regression. Không dùng số dòng cũ để cáo buộc một commit mới chưa đọc.

Những probes P01–P12 và kết quả 196 pass/2 environment failures là **evidence từ lượt audit trước**. Lượt hợp nhất này chỉ kiểm tra byte integrity, source/API thêm trong ZIP và khả năng khôi phục bundle; không chạy lại market experiments hoặc native wheel. Probes historical chứng minh defect của source cũ; test trên repaired source phải assert expected correct behavior.

## 13.2 Nguồn technical bổ sung, không thay source đã pin

Các tài liệu chính thức sau giải thích cơ chế chung. Version dependencies thật vẫn theo QuantBT/lab environment; không tự nâng Optuna/NumPy/PyO3 chỉ vì trang stable mới hơn:

- **S1 —** Optuna ask/tell, intermediate reporting và pruning: `https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/009_ask_and_tell.html`
- **S2 —** Optuna reproducibility và parallel optimization: `https://optuna.readthedocs.io/en/stable/faq.html`
- **S3 —** NumPy shared arrays/thread safety: `https://numpy.org/doc/stable/reference/thread_safety.html`
- **S4 —** PyO3 0.29 parallelism, detach/attach: `https://pyo3.rs/v0.29.0/parallelism.html`

Mode 4, endpoint options, fee binding, output aliases và PF semantics trong phần chính được đối chiếu **trực tiếp với source `quantbt_candidate` trong upload**, không suy từ những nguồn chung trên.

## 13.3 Tính chất của phụ lục

- Historical Markdown có thể chứa tên file/link/CLI theo workspace audit cũ. Chúng được giữ nguyên để truy xuất; không ghi đè nhiệm vụ RF-01…RF-05.
- Mọi payload là data cho review. Utility trích xuất chỉ decode/write bytes; không import hoặc execute `.py`.
- `archive_inventory.json` và `artifact_index.json` được nén lossless; có kích thước/hash gốc và decoder stdlib.
- Historical bundle có một self-entry không khớp trong `audit_bundle_manifest.json`. Giữ nguyên artifact đó; bảng member hashes bên ngoài là kiểm kê byte thực khi hợp nhất. Đây là lỗi bookkeeping cần sửa cho future manifests, không tự chứng minh mọi artifact trong ZIP hỏng.
- Không nhúng venv, wheel, market database hoặc secrets trong Markdown này. Evidence bundle gốc chủ yếu là reports, excerpts, JSON và probes; raw market snapshots vẫn cần được read-only trên server để chạy real-alpha study.

---


## 13.4 Kiểm tra toàn vẹn của bản hợp nhất này

Các kiểm tra sau đã được chạy khi tạo file, khác với market rerun còn phải làm:

| Kiểm tra | Kết quả |
|---|---|
| SHA-256 source ZIP | Khớp archive được audit ngày 11/09/2026 |
| Hai Markdown gốc | Giữ đúng bytes, không sửa nội dung lịch sử |
| Members trong evidence ZIP | **20/20** khôi phục đúng bytes và SHA-256 từ Markdown này |
| JSON và Python scripts trong bundle | Parse 10 JSON; AST parse 3 scripts, không execute các probes |
| Trích đoạn QuantBT bổ sung | 11 nhóm source verification có full-file SHA-256 và line ranges |
| Cấu trúc roadmap | Đúng 5 phase RF-01…RF-05; 70 acceptance requirements, không phải 70 tests đã pass |
| Utility trích xuất | Từ chối checksum sai, path traversal và output đã tồn tại; không thực thi source được khôi phục |
| Markdown fences | Đã kiểm tra đóng/mở hợp lệ, kể cả code fences trong tài liệu gốc |
| Market experiments hoặc native-wheel certification mới | **Không thực hiện trong lượt hợp nhất** |

Original self-manifest discrepancy N03 được bảo toàn và ghi nhận; 19 file entries còn lại khớp actual payloads. Những kiểm tra integrity này không thay semantic/domain tests, statistical validation hoặc actual market results.

---

# PHỤ LỤC VFY — Source QuantBT kiểm tra thêm trong lượt hợp nhất

Nguồn: candidate copy nằm trong ZIP đã gửi; **không phải GitHub HEAD mới hoặc installed-wheel run**. Số dòng là số dòng của toàn file source tương ứng. SHA-256 là hash toàn file. Trích đoạn này chỉ xác minh khả năng/API và giới hạn, không thay test thực trên server.

## VFY01 — `quantbt_candidate/quantbt/endpoint.py`

Factory pct_equity và signal_notional; đây là static API evidence, không phải benchmark.

**SHA-256:** `45ede55d0d66dd3a30089584b92199a455acca83e8f0418df3305874c28929a6`

**Source lines 1168–1195:**

```text
  1168 |     def pct_equity(cls, **kwargs) -> "QuantBTEndpoint":
  1169 |         """
  1170 |         Create a legacy `%_equity` endpoint.
  1171 | 
  1172 |         Use this for strategies whose signal is a direction/weight and whose
  1173 |         order notional should be recomputed from live equity on signal changes.
  1174 |         `alloc_per_trade` is interpreted as an equity fraction when <= 1.0
  1175 |         (`0.5` means 50% of current equity), or as a percent when > 1.0.
  1176 | 
  1177 |         Data requirement for `backtest()`:
  1178 |         a single OHLCV DataFrame with a DatetimeIndex and `close`; `high` and
  1179 |         `low` are strongly recommended for liquidation checks.
  1180 |         """
  1181 |         return cls(_config_from_kwargs(mode="pct_equity", sizing="%_equity", backend="legacy", **kwargs))
  1182 | 
  1183 |     @classmethod
  1184 |     def signal_notional(cls, backend: str = "native_vectorized", **kwargs) -> "QuantBTEndpoint":
  1185 |         """
  1186 |         Create a signal-notional endpoint.
  1187 | 
  1188 |         Signal changes anchor target units at the current price. Between signal
  1189 |         changes, units are frozen, avoiding price-drift micro-rebalancing. This
  1190 |         is the recommended default for systematic single-symbol alpha research.
  1191 | 
  1192 |         `backend` can be `native_vectorized` for speed or `native_event` when
  1193 |         you want generated market rebalance orders and fill records.
  1194 |         """
  1195 |         return cls(_config_from_kwargs(mode="signal_notional", sizing="signal_notional", backend=backend, **kwargs))
```

## VFY02 — `quantbt_candidate/quantbt/endpoint.py`

Public WFO signature, explicit causal semantics, research retention và default Mode 4 selection.

**SHA-256:** `45ede55d0d66dd3a30089584b92199a455acca83e8f0418df3305874c28929a6`

**Source lines 1932–1975:**

```text
  1932 |     def walk_forward(
  1933 |         cls,
  1934 |         strategy_class,
  1935 |         split_mode: Union[str, int, pd.Timestamp] = "walk_forward_2022",
  1936 |         split_frequency: str = "quarterly",
  1937 |         target_mode: str = "signal_notional",
  1938 |         window_mode: str = "expanding",
  1939 |         train_window: Optional[str] = None,
  1940 |         optimization_mode: str = "none",
  1941 |         optimization_schedule: str = "global",
  1942 |         fold_boundary_position_policy: str = "carry",
  1943 |         calendar_contract: str = "exact_v2",
  1944 |         optimization_config: Optional[Dict] = None,
  1945 |         optuna_trials: int = 0,
  1946 |         optuna_early_stopping: Optional[int] = None,
  1947 |         random_seed: int = 42,
  1948 |         **kwargs,
  1949 |     ) -> "QuantBTEndpoint":
  1950 |         """
  1951 |         Create a walk-forward endpoint.
  1952 | 
  1953 |         The strategy callable/class is invoked once per fold and must return OOS
  1954 |         signal/position output indexed by timestamp. The stitched OOS output is
  1955 |         then routed into an existing QuantBT backtest path, so boundary trades
  1956 |         are charged by the normal engine instead of averaging fold equities.
  1957 |         Supported optimization modes are `mode_1_decay`, `mode_2_sbb`,
  1958 |         `mode_3_flat_minima`, `mode_4_is_only_robust`, and
  1959 |         `mode_5_full_robust`.
  1960 |         `optimization_schedule="global"` preserves the existing one-study
  1961 |         behavior. `per_fold_decay` runs Mode 1 as one independent two-stage
  1962 |         study per fold and uses that fold's OOS metrics for decay candidate
  1963 |         selection. `per_fold_causal` runs Mode 4 as strict fold-local IS-only
  1964 |         selection, or Mode 1 with explicit nested inner validation entirely
  1965 |         inside each outer IS window. The default final account policy is
  1966 |         `carry_position`. `close_at_boundary` is supported only when an
  1967 |         embargo provides an auditable flatten gap; `reset_flat` and
  1968 |         `replay_prior_state` fail closed on this stitched-target endpoint
  1969 |         until a segmented-account or order/fill-replay adapter is selected.
  1970 |         `optimization_config` can also declare the calendar, temporal guards,
  1971 |         intent timing, lifecycle isolation, and proxy/native rank audit.
  1972 |         Fixed-parameter runs can leave
  1973 |         `optimization_mode="none"` and pass `params=...` to `backtest()`.
  1974 |         """
  1975 |         optimization_config = dict(optimization_config or {})
```

**Source lines 1990–2020:**

```text
  1990 |         retention_plan = ResearchRetentionPlanV1(
  1991 |             financial_retention=optimization_config.get(
  1992 |                 "financial_retention",
  1993 |                 wf_metadata.get("financial_retention", "score"),
  1994 |             ),
  1995 |             research_retention=optimization_config.get(
  1996 |                 "research_retention",
  1997 |                 wf_metadata.get("research_retention", "none"),
  1998 |             ),
  1999 |             financial_scope=optimization_config.get(
  2000 |                 "financial_retention_scope",
  2001 |                 wf_metadata.get("financial_retention_scope", "selected_final_execution"),
  2002 |             ),
  2003 |             chunk_rows=optimization_config.get(
  2004 |                 "research_audit_chunk_rows",
  2005 |                 wf_metadata.get("research_audit_chunk_rows", 256),
  2006 |             ),
  2007 |             max_retained_chunks=optimization_config.get(
  2008 |                 "research_audit_max_chunks",
  2009 |                 wf_metadata.get("research_audit_max_chunks", 4_096),
  2010 |             ),
  2011 |             max_materialized_frames=optimization_config.get(
  2012 |                 "research_audit_max_materialized_frames",
  2013 |                 wf_metadata.get("research_audit_max_materialized_frames", 3),
  2014 |             ),
  2015 |         )
  2016 |         wf_metadata.setdefault("financial_retention", retention_plan.financial_retention)
  2017 |         wf_metadata.setdefault("research_retention", retention_plan.research_retention)
  2018 |         wf_metadata.setdefault("financial_retention_scope", retention_plan.financial_scope)
  2019 |         wf_metadata.setdefault("research_audit_chunk_rows", retention_plan.chunk_rows)
  2020 |         wf_metadata.setdefault("research_audit_max_chunks", retention_plan.max_retained_chunks)
```

**Source lines 2086–2120:**

```text
  2086 |                 window_mode=window_mode,
  2087 |                 train_window=train_window,
  2088 |                 target_mode=target_mode,
  2089 |                 optimization_mode=optimization_mode,
  2090 |                 optimization_schedule=optimization_schedule,
  2091 |                 fold_boundary_position_policy=fold_boundary_position_policy,
  2092 |                 inner_split_frequency=optimization_config.get("inner_split_frequency"),
  2093 |                 inner_window_mode=optimization_config.get("inner_window_mode"),
  2094 |                 inner_train_window=optimization_config.get("inner_train_window"),
  2095 |                 inner_min_folds=int(optimization_config.get("inner_min_folds", 2)),
  2096 |                 calendar_contract=str(optimization_config.get("calendar_contract", calendar_contract)),
  2097 |                 calendar_primary_symbol=optimization_config.get("calendar_primary_symbol"),
  2098 |                 calendar_missing_policy=str(optimization_config.get("calendar_missing_policy", "no_observation")),
  2099 |                 label_horizon_bars=int(optimization_config.get("label_horizon_bars", 0)),
  2100 |                 purge_bars=int(optimization_config.get("purge_bars", 0)),
  2101 |                 embargo_bars=int(optimization_config.get("embargo_bars", 0)),
  2102 |                 warmup_policy=str(optimization_config.get("warmup_policy", "none")),
  2103 |                 warmup_bars=optimization_config.get("warmup_bars"),
  2104 |                 fold_account_policy=str(
  2105 |                     optimization_config.get("fold_account_policy", fold_boundary_position_policy)
  2106 |                 ),
  2107 |                 intent_contract=optimization_config.get("intent_contract"),
  2108 |                 strategy_lifecycle_policy=str(optimization_config.get("strategy_lifecycle_policy", "isolated_v1")),
  2109 |                 trusted_strategy_global=bool(optimization_config.get("trusted_strategy_global", False)),
  2110 |                 proxy_validation_mode=str(optimization_config.get("proxy_validation_mode", "off")),
  2111 |                 proxy_validation_top_fraction=float(optimization_config.get("proxy_validation_top_fraction", 0.10)),
  2112 |                 proxy_min_spearman=float(optimization_config.get("proxy_min_spearman", 0.70)),
  2113 |                 proxy_min_top_k_overlap=float(optimization_config.get("proxy_min_top_k_overlap", 0.50)),
  2114 |                 proxy_max_winner_regret=float(optimization_config.get("proxy_max_winner_regret", 0.25)),
  2115 |                 proxy_max_false_positive_rate=float(optimization_config.get("proxy_max_false_positive_rate", 0.25)),
  2116 |                 optuna_trials=optuna_trials,
  2117 |                 optuna_early_stopping=optuna_early_stopping,
  2118 |                 random_seed=random_seed,
  2119 |                 decay_lambda=float(optimization_config.get("decay_lambda", 0.5)),
  2120 |                 decay_gamma=float(optimization_config.get("decay_gamma", 0.5)),
```

## VFY03 — `quantbt_candidate/quantbt/walkforward.py`

Per-fold causal dùng optimize_params của engine; không evaluate outer OOS để chọn Mode 4.

**SHA-256:** `b3da15189cb87d5e6f0080123aeb7f245b4991d61354112049030335c8f3b256`

**Source lines 1455–1521:**

```text
  1455 |     def _run_per_fold_schedule(
  1456 |         self,
  1457 |         data,
  1458 |         folds: Sequence[WalkForwardFold],
  1459 |         param_ranges: Dict[str, Any],
  1460 |     ) -> _PerFoldScheduleRun:
  1461 |         """Run independent chronological studies under the Phase 49A contract."""
  1462 |         schedule = self.config.optimization_schedule
  1463 |         outputs: List[StrategyOutput] = []
  1464 |         selected_records: List[WalkForwardTrialRecord] = []
  1465 |         trial_records: List[WalkForwardTrialRecord] = []
  1466 |         candidate_records: List[WalkForwardTrialRecord] = []
  1467 |         params_by_fold: Dict[int, Dict[str, Any]] = {}
  1468 |         selection_rows: List[Dict[str, Any]] = []
  1469 |         inner_fold_rows: List[Dict[str, Any]] = []
  1470 | 
  1471 |         for fold in folds:
  1472 |             fold_seed = _derive_fold_seed(self.config.random_seed, fold.fold_id)
  1473 |             is_nested_mode1 = (
  1474 |                 schedule == "per_fold_causal"
  1475 |                 and self.config.optimization_mode == "mode_1_decay"
  1476 |             )
  1477 |             inner_folds: List[WalkForwardFold] = []
  1478 |             if is_nested_mode1:
  1479 |                 inner_folds = list(self._prepared_inner_folds(fold))
  1480 |             common_metadata = {
  1481 |                 "optimization_schedule": schedule,
  1482 |                 "schedule_fold_id": int(fold.fold_id),
  1483 |                 "study_id": int(fold.fold_id),
  1484 |                 "fold_seed": int(fold_seed),
  1485 |                 "selection_data_start": fold.train_start,
  1486 |                 "selection_data_end": fold.train_end,
  1487 |                 "test_start": fold.test_start,
  1488 |                 "test_end": fold.test_end,
  1489 |                 "inner_fold_count": int(len(inner_folds)),
  1490 |                 "inner_validation": _inner_validation_metadata(self.config),
  1491 |             }
  1492 |             if is_nested_mode1:
  1493 |                 selected, fold_trials, fold_candidates = self.optimize_params(
  1494 |                     data=data,
  1495 |                     folds=inner_folds,
  1496 |                     param_ranges=param_ranges,
  1497 |                     random_seed=fold_seed,
  1498 |                     study_id=int(fold.fold_id),
  1499 |                     evaluate_oos_candidates=True,
  1500 |                     research_context=common_metadata,
  1501 |                 )
  1502 |                 inner_fold_rows.extend(
  1503 |                     _inner_fold_audit_rows(
  1504 |                         outer_fold=fold,
  1505 |                         inner_folds=inner_folds,
  1506 |                     )
  1507 |                 )
  1508 |             else:
  1509 |                 selected, fold_trials, fold_candidates = self.optimize_params(
  1510 |                     data=data,
  1511 |                     folds=[fold],
  1512 |                     param_ranges=param_ranges,
  1513 |                     random_seed=fold_seed,
  1514 |                     study_id=int(fold.fold_id),
  1515 |                     evaluate_oos_candidates=schedule == "per_fold_decay",
  1516 |                     research_context=common_metadata,
  1517 |                 )
  1518 | 
  1519 |             oos_used = schedule == "per_fold_decay"
  1520 |             selection_label = (
  1521 |                 "fold_local_decay_calibration"
```

**Source lines 1539–1564:**

```text
  1539 |                     {**record.selection_metadata, **common_metadata},
  1540 |                 )
  1541 |                 for record in fold_candidates
  1542 |             ]
  1543 | 
  1544 |             selected = _with_selection_metadata(
  1545 |                 selected,
  1546 |                 {
  1547 |                     **selected.selection_metadata,
  1548 |                     **common_metadata,
  1549 |                     "causality_claim": selection_label,
  1550 |                     "outer_oos_used_for_selection": bool(oos_used),
  1551 |                     "oos_used_for_selection": bool(oos_used),
  1552 |                     "selection_adjustment_note": (
  1553 |                         "same_fold_oos_used_for_candidate_decay_selection"
  1554 |                         if oos_used
  1555 |                         else (
  1556 |                             "outer_oos_excluded_from_nested_inner_decay_selection"
  1557 |                             if is_nested_mode1
  1558 |                             else "outer_oos_excluded_from_parameter_selection"
  1559 |                         )
  1560 |                     ),
  1561 |                 },
  1562 |             )
  1563 |             params_by_fold[int(fold.fold_id)] = dict(selected.params)
  1564 | 
```

## VFY04 — `quantbt_candidate/quantbt/endpoint.py`

Prepared WFO policies mặc định off và require validation.

**SHA-256:** `45ede55d0d66dd3a30089584b92199a455acca83e8f0418df3305874c28929a6`

**Source lines 2032–2064:**

```text
  2032 |         native_prepared_wfo = str(optimization_config.get("native_prepared_wfo", "off")).lower().strip()
  2033 |         if native_prepared_wfo not in {"off", "auto", "require"}:
  2034 |             raise ValueError("native_prepared_wfo must be 'off', 'auto', or 'require'")
  2035 |         wf_metadata.setdefault("native_prepared_wfo", native_prepared_wfo)
  2036 |         wf_metadata.setdefault(
  2037 |             "native_prepared_wfo_workers",
  2038 |             int(optimization_config.get("native_prepared_wfo_workers", 1)),
  2039 |         )
  2040 |         prepared_wfo_strategy = str(
  2041 |             optimization_config.get("prepared_wfo_strategy", "off")
  2042 |         ).lower().strip()
  2043 |         if prepared_wfo_strategy not in {"off", "auto", "require"}:
  2044 |             raise ValueError("prepared_wfo_strategy must be 'off', 'auto', or 'require'")
  2045 |         prepared_wfo_strategy_adapter = str(
  2046 |             optimization_config.get("prepared_wfo_strategy_adapter", "auto")
  2047 |         ).lower().strip()
  2048 |         if prepared_wfo_strategy_adapter not in {"auto", "w1", "w2"}:
  2049 |             raise ValueError("prepared_wfo_strategy_adapter must be 'auto', 'w1', or 'w2'")
  2050 |         wf_metadata.setdefault("prepared_wfo_strategy", prepared_wfo_strategy)
  2051 |         wf_metadata.setdefault("prepared_wfo_strategy_adapter", prepared_wfo_strategy_adapter)
  2052 |         if "prepared_wfo_strategy_static_config" in optimization_config:
  2053 |             static_config = optimization_config["prepared_wfo_strategy_static_config"]
  2054 |             if not isinstance(static_config, Mapping):
  2055 |                 raise TypeError("prepared_wfo_strategy_static_config must be a mapping")
  2056 |             wf_metadata.setdefault("prepared_wfo_strategy_static_config", dict(static_config))
  2057 |         if scoring_backend != "endpoint":
  2058 |             if native_prepared_wfo == "require":
  2059 |                 raise NotImplementedError(
  2060 |                     "native_prepared_wfo='require' is not available with "
  2061 |                     f"scoring_backend={scoring_backend!r}; mode_2_sbb deliberately "
  2062 |                     "retains its bounded train-path proxy scorer"
  2063 |                 )
  2064 |             wf_metadata.setdefault(
```

## VFY05 — `quantbt_candidate/quantbt/backends/native_wfo_public.py`

Native prepared timing cùng limitations. Không chuyển same-close thành next-open bằng metadata.

**SHA-256:** `e4725ad1f841b42454b2aff967f3e82949b3a9545ad23d7aa85bc4ebf5f232ee`

**Source lines 36–45:**

```text
    36 | from .native_vectorized import NativeVectorizedConfig
    37 | 
    38 | 
    39 | _POLICIES = frozenset({"off", "auto", "require"})
    40 | _SUPPORTED_TARGETS = frozenset(
    41 |     {"signal_notional", "single_signal", "notional", "unit", "pct_equity", "%_equity"}
    42 | )
    43 | _RUST_DIRECT_TIMING = "close_target_v2_same_close"
    44 | 
    45 | 
```

**Source lines 290–335:**

```text
   290 |     def _prepare_state(self, context) -> _PreparedPublicWfoState:
   291 |         if self.target_mode not in _SUPPORTED_TARGETS:
   292 |             raise NativePreparedPublicWfoUnsupported(
   293 |                 "prepared public WFO currently certifies target_mode="
   294 |                 "'signal_notional'/'notional'/'unit' only, plus explicit pct_equity transition scoring"
   295 |             )
   296 |         if self.target_mode in {"pct_equity", "%_equity"} and self.policy != "require":
   297 |             raise NativePreparedPublicWfoUnsupported(
   298 |                 "prepared target_mode='pct_equity' scoring is opt-in: set native_prepared_wfo='require' "
   299 |                 "with target_runtime='rust'; auto preserves the legacy endpoint route"
   300 |             )
   301 |         if self.target_mode in {"pct_equity", "%_equity"}:
   302 |             legacy_one_way_fee = float(self.config.fee) / 2.0
   303 |             if not np.isclose(
   304 |                 float(self.config.v2_fee_rate),
   305 |                 legacy_one_way_fee,
   306 |                 rtol=0.0,
   307 |                 atol=1.0e-15,
   308 |             ):
   309 |                 raise NativePreparedPublicWfoUnsupported(
   310 |                     "prepared target_mode='pct_equity' requires fee_rate to equal legacy fee / 2 "
   311 |                     "for exact compatibility"
   312 |                 )
   313 |             configured_slippage = float(self.config.execution.slippage_rate)
   314 |             if configured_slippage != 0.0 and not np.isclose(
   315 |                 configured_slippage,
   316 |                 float(self.config.slippage),
   317 |                 rtol=0.0,
   318 |                 atol=1.0e-15,
   319 |             ):
   320 |                 raise NativePreparedPublicWfoUnsupported(
   321 |                     "prepared target_mode='pct_equity' requires ExecutionConfig.slippage_bps "
   322 |                     "to equal legacy slippage for exact compatibility"
   323 |                 )
   324 |         if str(getattr(self.config, "target_runtime", "numba")).lower().strip() != "rust":
   325 |             raise NativePreparedPublicWfoUnsupported(
   326 |                 "prepared public WFO requires target_runtime='rust'; it never changes a Numba route"
   327 |             )
   328 |         if int(getattr(self.wf_config, "scoring_trading_days", 365)) != 365:
   329 |             raise NativePreparedPublicWfoUnsupported(
   330 |                 "prepared public WFO currently certifies scoring_trading_days=365 only"
   331 |             )
   332 |         symbols = list(getattr(self.config, "symbols", None) or ["DEFAULT"])
   333 |         if len(symbols) != 1:
   334 |             raise NativePreparedPublicWfoUnsupported(
   335 |                 "prepared public WFO is single-symbol; portfolio/package WFO retains its dedicated route"
```

**Source lines 459–481:**

```text
   459 |             equity_fraction = None
   460 |             if self.target_mode in {"pct_equity", "%_equity"}:
   461 |                 # Preserve the legacy processed-signal surface.  The Rust
   462 |                 # request owns transition sizing/accounting; Python never
   463 |                 # expands it to per-bar units or rebalances drifting equity.
   464 |                 if not bool(self.config.use_pyramiding):
   465 |                     raw = np.sign(raw)
   466 |                 targets = np.ascontiguousarray(raw, dtype=np.float64)
   467 |                 equity_fraction = np.asarray([state.alloc], dtype=np.float64)
   468 |             else:
   469 |                 targets = self._target_units(raw, state.closes[start:end], index, state.alloc)
   470 |             local_template = state.cache.window_template(state.template, start=start, end=end)
   471 |             request = state.cache.transient_direct_target_request(
   472 |                 local_template,
   473 |                 targets=targets,
   474 |                 target_kind=target_kind,
   475 |                 timing=_RUST_DIRECT_TIMING,
   476 |                 invalid_target_policy="reject_run",
   477 |                 tradable=state.tradable[start:end],
   478 |                 stale=state.stale[start:end],
   479 |                 qty_step=state.qty_step,
   480 |                 min_qty=state.min_qty,
   481 |                 min_notional=state.min_notional,
```

## VFY06 — `quantbt_candidate/quantbt/endpoint.py`

Explicit percent-equity Rust compatibility, transition sizing và fee/2 binding.

**SHA-256:** `45ede55d0d66dd3a30089584b92199a455acca83e8f0418df3305874c28929a6`

**Source lines 3195–3250:**

```text
  3195 |     def _run_pct_equity_transition_native(
  3196 |         self,
  3197 |         *,
  3198 |         frame: pd.DataFrame,
  3199 |         idx: pd.DatetimeIndex,
  3200 |         signal: pd.Series,
  3201 |         symbols: Sequence[str],
  3202 |     ) -> BacktestResultV2:
  3203 |         """Execute the frozen legacy `%_equity` transition contract in Rust.
  3204 | 
  3205 |         This is deliberately narrow and explicit.  The historical endpoint
  3206 |         still defaults to the Numba/legacy implementation; callers request
  3207 |         this route with ``target_runtime='rust'``.  Rust owns the accepted
  3208 |         unit/account trace while the public compatibility result continues to
  3209 |         expose processed signal weights, as the legacy endpoint has always
  3210 |         done for report trade-count and hit-rate semantics.
  3211 |         """
  3212 | 
  3213 |         symbol_list = list(symbols)
  3214 |         if len(symbol_list) != 1:
  3215 |             raise NotImplementedError(
  3216 |                 "rust pct_equity_transition currently certifies one canonical symbol; "
  3217 |                 "use the legacy pct_equity endpoint for multi-symbol compatibility"
  3218 |             )
  3219 |         requested_symbol = str(symbol_list[0])
  3220 |         # The legacy BacktestEngine receives ``symbols=None`` for this route
  3221 |         # and therefore resolves its one compatible position column and its
  3222 |         # scalar/mapping constraints through DEFAULT.  Do the same here: a
  3223 |         # caller-provided label must not silently change old pct_equity math.
  3224 |         symbol = "DEFAULT"
  3225 |         raw_signal = pd.to_numeric(signal, errors="raise").astype(float)
  3226 |         if not bool(self.config.use_pyramiding):
  3227 |             raw_signal = pd.Series(np.sign(raw_signal.to_numpy(dtype=np.float64)), index=idx, dtype=float)
  3228 | 
  3229 |         legacy_one_way_fee = float(self.config.fee) / 2.0
  3230 |         if not np.isclose(
  3231 |             float(self.config.v2_fee_rate),
  3232 |             legacy_one_way_fee,
  3233 |             rtol=0.0,
  3234 |             atol=1.0e-15,
  3235 |         ):
  3236 |             raise ValueError(
  3237 |                 "rust pct_equity_transition requires fee_rate to equal legacy fee / 2 "
  3238 |                 "for exact compatibility; remove fee_rate or make the two conventions equivalent"
  3239 |             )
  3240 | 
  3241 |         # ``pct_equity`` historically accepts ``slippage`` as a fractional
  3242 |         # compatibility input. Native V2 uses explicit bps, so retain an
  3243 |         # explicitly supplied V2 rate when present and otherwise translate the
  3244 |         # legacy field exactly once at this compatibility boundary.
  3245 |         execution = self.config.execution
  3246 |         if execution.slippage_rate != 0.0 and not np.isclose(
  3247 |             float(execution.slippage_rate),
  3248 |             float(self.config.slippage),
  3249 |             rtol=0.0,
  3250 |             atol=1.0e-15,
```

## VFY07 — `quantbt_candidate/quantbt/metrics/performance.py`

PF trên stats returns; Sharpe reducer có annual periods argument.

**SHA-256:** `152015d96b01021584422839b5f3fe70760efb9ec826dd3aebded557f2487095`

**Source lines 298–322:**

```text
   298 |     if len(returns_arr) != len(equity_arr):
   299 |         raise ValueError("returns must have the same length as equity")
   300 |     if pos_arr.shape[0] != len(equity_arr):
   301 |         raise ValueError("positions must have the same number of rows as equity")
   302 | 
   303 |     stats_returns = _array_returns_for_stats(idx, equity_arr, returns_arr)
   304 |     annual_periods = _array_annualization_periods(idx, stats_returns, trading_days)
   305 |     elapsed_years = _array_elapsed_years(idx, equity_arr, trading_days)
   306 |     drawdown = _array_drawdown(equity_arr)
   307 |     max_dd = float(np.nanmax(drawdown)) if len(drawdown) else 0.0
   308 |     avg_dd = float(np.nanmean(drawdown[drawdown > 0.0])) if np.any(drawdown > 0.0) else 0.0
   309 |     max_dd_duration, avg_dd_duration = _array_drawdown_duration_days(idx, equity_arr)
   310 | 
   311 |     final_equity = float(equity_arr[-1])
   312 |     total_ret = (final_equity - float(initial_capital)) / float(initial_capital)
   313 |     cagr_value = _array_cagr(equity_arr, total_ret, elapsed_years)
   314 |     sharpe_value = _array_sharpe(stats_returns, annual_periods)
   315 |     sortino_value = _array_sortino(stats_returns, annual_periods)
   316 |     omega_value = _array_omega(stats_returns)
   317 |     pf_value = _array_profit_factor(stats_returns)
   318 |     long_hr, short_hr = _array_hitrate(returns_arr, pos_arr)
   319 |     avg_win, avg_loss = _array_avg_win_loss(stats_returns)
   320 |     hr = (long_hr + short_hr) / 200.0
   321 |     expectancy_value = hr * avg_win + (1.0 - hr) * avg_loss
   322 | 
```

**Source lines 437–449:**

```text
   437 | def _array_sharpe(r: np.ndarray, periods: float) -> float:
   438 |     if len(r) < 2:
   439 |         return 0.0
   440 |     sd = float(np.std(r, ddof=1))
   441 |     return float((np.mean(r) / sd) * np.sqrt(periods)) if sd > 0.0 else 0.0
   442 | 
   443 | 
   444 | def _array_sortino(r: np.ndarray, periods: float, mar: float = 0.0) -> float:
   445 |     downside = r[r < mar] - mar
   446 |     dd = float(np.sqrt(np.mean(downside ** 2))) if len(downside) > 0 else 0.0
   447 |     mean = float(np.mean(r)) if len(r) > 0 else 0.0
   448 |     if dd == 0.0 and mean > mar:
   449 |         return np.inf
```

**Source lines 513–526:**

```text
   513 | def _array_profit_factor(r: np.ndarray) -> float:
   514 |     gains = float(np.sum(r[r > 0.0]))
   515 |     loss = float(abs(np.sum(r[r < 0.0])))
   516 |     return gains / loss if loss > 0.0 else np.inf
   517 | 
   518 | 
   519 | def _array_avg_win_loss(r: np.ndarray) -> Tuple[float, float]:
   520 |     wins = r[r > 0.0]
   521 |     losses = r[r < 0.0]
   522 |     win = float(np.mean(wins) * 100.0) if len(wins) > 0 else 0.0
   523 |     loss = float(np.mean(losses) * 100.0) if len(losses) > 0 else 0.0
   524 |     return win, loss
   525 | 
   526 | def full_report(result: BacktestResult, trading_days: int = 365) -> Dict:
```

## VFY08 — `quantbt_candidate/quantbt/walkforward.py`

Raw/penalized outer metrics và candidate decay reporting.

**SHA-256:** `b3da15189cb87d5e6f0080123aeb7f245b4991d61354112049030335c8f3b256`

**Source lines 1566–1627:**

```text
  1566 |             out = _slice_output_to_test(out, fold.test_index)
  1567 |             outputs.append(out)
  1568 | 
  1569 |             if oos_used:
  1570 |                 outer_is = float(selected.mean_is_sharpe)
  1571 |                 outer_oos = float(selected.mean_oos_sharpe)
  1572 |                 outer_decay = float(selected.mean_decay)
  1573 |             else:
  1574 |                 oos_metrics = self._score_strategy_output(
  1575 |                     data,
  1576 |                     out,
  1577 |                     fold.test_index,
  1578 |                     fold=fold,
  1579 |                     params=dict(selected.params),
  1580 |                     context="post-selection outer OOS realization",
  1581 |                 )
  1582 |                 required = self._required_trades(fold.test_index)
  1583 |                 factor = 1.0 if self.config.trade_penalty_factor is None else float(self.config.trade_penalty_factor)
  1584 |                 penalty = trade_frequency_penalty(oos_metrics["trade_count"], required, factor)
  1585 |                 outer_is = float(selected.mean_is_sharpe)
  1586 |                 outer_oos = float(oos_metrics["sharpe"] - penalty)
  1587 |                 outer_decay = float(outer_is - outer_oos)
  1588 |                 selected = _with_selection_metadata(
  1589 |                     selected,
  1590 |                     {
  1591 |                         **selected.selection_metadata,
  1592 |                         "outer_is_metric": outer_is,
  1593 |                         "outer_oos_metric": outer_oos,
  1594 |                         "outer_realized_decay": outer_decay,
  1595 |                         "outer_oos_trade_count": float(oos_metrics["trade_count"]),
  1596 |                         "outer_oos_trade_penalty": float(penalty),
  1597 |                     },
  1598 |                 )
  1599 | 
  1600 |             selected_records.append(selected)
  1601 |             trial_records.extend(tagged_trials)
  1602 |             candidate_records.extend(tagged_candidates)
  1603 |             optuna_rows = sum(
  1604 |                 1
  1605 |                 for record in tagged_trials
  1606 |                 if record.pruned or record.selection_metadata.get("stage") == "is_search"
  1607 |             )
  1608 |             selection_rows.append(
  1609 |                 {
  1610 |                     "fold_id": int(fold.fold_id),
  1611 |                     "study_id": int(fold.fold_id),
  1612 |                     "fold_seed": int(fold_seed),
  1613 |                     "train_start": fold.train_start,
  1614 |                     "train_end": fold.train_end,
  1615 |                     "test_start": fold.test_start,
  1616 |                     "test_end": fold.test_end,
  1617 |                     "selected_trial_id": int(selected.trial_id),
  1618 |                     "selected_params": dict(selected.params),
  1619 |                     "selected_is_objective": float(selected.mean_is_sharpe),
  1620 |                     "candidate_is_metric": outer_is,
  1621 |                     "candidate_oos_metric": outer_oos,
  1622 |                     "candidate_decay": outer_decay,
  1623 |                     "candidate_count": int(len(tagged_candidates)),
  1624 |                     "study_trial_rows": int(optuna_rows),
  1625 |                     "outer_oos_used_for_selection": bool(oos_used),
  1626 |                     "causality_claim": selection_label,
  1627 |                     "inner_fold_count": int(len(inner_folds)),
```

## VFY09 — `quantbt_candidate/quantbt/walkforward.py`

Calendar fold builder và Mode 4 selector. Dynamic scheduler phải reuse chính contracts này, không giả một universal regime argument.

**SHA-256:** `b3da15189cb87d5e6f0080123aeb7f245b4991d61354112049030335c8f3b256`

**Source lines 2311–2409:**

```text
  2311 |     def build_folds(self, idx: pd.DatetimeIndex) -> List[WalkForwardFold]:
  2312 |         """Return canonical-clock chronological folds without lookahead.
  2313 | 
  2314 |         The raw calendar spans are converted once into integer boundaries.  A
  2315 |         fold's train tail is then purged before its test range, while an
  2316 |         embargo is an explicit non-trading gap before the next eligible OOS
  2317 |         range.  This makes all temporal exclusions inspectable rather than a
  2318 |         hidden boolean mask inside strategy or optimizer code.
  2319 |         """
  2320 |         idx = validate_datetime(idx)
  2321 |         if len(idx) == 0:
  2322 |             raise ValueError("walk-forward datetime index is empty")
  2323 | 
  2324 |         if self.config.optimization_mode == "mode_5_full_robust":
  2325 |             if len(idx) < self.config.min_train_bars:
  2326 |                 raise ValueError("full-sample robust calibration produced too few bars")
  2327 |             return [
  2328 |                 WalkForwardFold(
  2329 |                     fold_id=0,
  2330 |                     train_start=idx[0],
  2331 |                     train_end=idx[-1],
  2332 |                     test_start=idx[0],
  2333 |                     test_end=idx[-1],
  2334 |                     train_index=idx,
  2335 |                     test_index=idx,
  2336 |                     cutoff_timestamp=idx[-1],
  2337 |                     account_policy=self.config.fold_account_policy,
  2338 |                 )
  2339 |             ]
  2340 | 
  2341 |         first_oos = _first_oos_timestamp(self.config.split_mode)
  2342 |         if first_oos <= idx[0]:
  2343 |             raise ValueError("first OOS timestamp must be after the first data timestamp")
  2344 |         if first_oos > idx[-1]:
  2345 |             raise ValueError("first OOS timestamp is after the available data")
  2346 | 
  2347 |         first_test_start = int(idx.searchsorted(first_oos, side="left"))
  2348 |         if first_test_start >= len(idx):
  2349 |             raise ValueError("first OOS timestamp is after the available data")
  2350 | 
  2351 |         if self.config.split_frequency == "single":
  2352 |             raw_train_start = (
  2353 |                 0
  2354 |                 if self.config.window_mode == "expanding"
  2355 |                 else int(idx.searchsorted(first_oos - pd.Timedelta(self.config.train_window), side="left"))
  2356 |             )
  2357 |             fold = _build_fold_v2(
  2358 |                 idx,
  2359 |                 fold_id=0,
  2360 |                 raw_train_start=raw_train_start,
  2361 |                 test_start=first_test_start,
  2362 |                 test_stop=len(idx),
  2363 |                 config=self.config,
  2364 |             )
  2365 |             if fold is None or len(fold.train_index) < self.config.min_train_bars:
  2366 |                 raise ValueError("train/test split produced too few train bars")
  2367 |             if len(fold.test_index) < self.config.min_test_bars:
  2368 |                 raise ValueError("train/test split produced too few test bars")
  2369 |             return [fold]
  2370 | 
  2371 |         step = _frequency_offset(self.config.split_frequency)
  2372 |         folds: List[WalkForwardFold] = []
  2373 |         test_start_position = first_test_start
  2374 |         fold_id = 0
  2375 |         while test_start_position < len(idx):
  2376 |             test_start = idx[test_start_position]
  2377 |             test_stop_timestamp = test_start + step
  2378 |             test_stop_position = int(idx.searchsorted(test_stop_timestamp, side="left"))
  2379 |             if test_stop_position <= test_start_position:
  2380 |                 test_stop_position = min(len(idx), test_start_position + 1)
  2381 |             test_bars = test_stop_position - test_start_position
  2382 |             if test_bars < self.config.min_test_bars:
  2383 |                 test_start_position = test_stop_position
  2384 |                 continue
  2385 | 
  2386 |             if self.config.window_mode == "expanding":
  2387 |                 raw_train_start = 0
  2388 |             else:
  2389 |                 raw_train_start = int(
  2390 |                     idx.searchsorted(test_start - pd.Timedelta(self.config.train_window), side="left")
  2391 |                 )
  2392 |             fold = _build_fold_v2(
  2393 |                 idx,
  2394 |                 fold_id=fold_id,
  2395 |                 raw_train_start=raw_train_start,
  2396 |                 test_start=test_start_position,
  2397 |                 test_stop=test_stop_position,
  2398 |                 config=self.config,
  2399 |             )
  2400 |             if fold is None or len(fold.train_index) < self.config.min_train_bars:
  2401 |                 test_start_position = test_stop_position
  2402 |                 continue
  2403 |             folds.append(fold)
  2404 |             fold_id += 1
  2405 |             test_start_position = test_stop_position + int(self.config.embargo_bars)
  2406 | 
  2407 |         if not folds:
  2408 |             raise ValueError("walk-forward split produced no folds")
  2409 |         return folds
```

**Source lines 4062–4126:**

```text
  4062 | def select_is_only_robust_record(
  4063 |     records: Sequence[WalkForwardTrialRecord],
  4064 |     param_ranges: Dict[str, Any],
  4065 |     config: WalkForwardConfig,
  4066 | ) -> WalkForwardTrialRecord:
  4067 |     """
  4068 |     Select strict train-only robust params from IS temporal stability + plateau.
  4069 | 
  4070 |     This selector is designed for `mode_4_is_only_robust`.  It never reads OOS
  4071 |     metrics.  It combines two IS-only robustness signals:
  4072 | 
  4073 |     * temporal robustness across train subperiod shards;
  4074 |     * plateau robustness across dense top-trial parameter regions.
  4075 |     """
  4076 |     completed = [record for record in records if not record.pruned and np.isfinite(record.objective)]
  4077 |     if not completed:
  4078 |         raise ValueError("is_only_robust selection received no completed trials")
  4079 |     ranked = sorted(completed, key=lambda record: record.objective, reverse=True)
  4080 |     top_n = _candidate_count(len(ranked), config)
  4081 |     top = ranked[:top_n]
  4082 |     matrix, names = _param_matrix(top, param_ranges)
  4083 |     if matrix.shape[0] == 1 or matrix.shape[1] == 0:
  4084 |         selected = _best_temporal_record(top)
  4085 |         return _with_selection_metadata(
  4086 |             selected,
  4087 |             {
  4088 |                 **selected.selection_metadata,
  4089 |                 "objective_mode": config.optimization_mode,
  4090 |                 "selector": "fallback_best_is_temporal",
  4091 |                 "selected_by": "is_only_robust",
  4092 |                 "oos_used_for_selection": False,
  4093 |                 "reason": "insufficient_cluster_points",
  4094 |                 "top_trials": int(top_n),
  4095 |                 "candidate_selection_complete": True,
  4096 |             },
  4097 |         )
  4098 | 
  4099 |     labels, cluster_method = _dbscan_cluster_labels(
  4100 |         matrix,
  4101 |         eps=float(config.flat_eps),
  4102 |         min_samples=int(config.flat_min_samples),
  4103 |     )
  4104 |     cluster_ids = sorted(label for label in set(labels.tolist()) if label >= 0)
  4105 |     if not cluster_ids:
  4106 |         selected = _best_temporal_record(top)
  4107 |         return _with_selection_metadata(
  4108 |             selected,
  4109 |             {
  4110 |                 **selected.selection_metadata,
  4111 |                 "objective_mode": config.optimization_mode,
  4112 |                 "selector": "fallback_best_is_temporal",
  4113 |                 "selected_by": "is_only_robust",
  4114 |                 "oos_used_for_selection": False,
  4115 |                 "reason": "no_dense_train_plateau",
  4116 |                 "top_trials": int(top_n),
  4117 |                 "eps": float(config.flat_eps),
  4118 |                 "min_samples": int(config.flat_min_samples),
  4119 |                 "cluster_method": cluster_method,
  4120 |                 "candidate_selection_complete": True,
  4121 |             },
  4122 |         )
  4123 | 
  4124 |     best_cluster = None
  4125 |     best_key = None
  4126 |     best_cluster_stats = None
```

## VFY10 — `quantbt_candidate/quantbt/endpoint.py`

Reactive prepared WFO reset-flat contract, không phải continuous carried account.

**SHA-256:** `45ede55d0d66dd3a30089584b92199a455acca83e8f0418df3305874c28929a6`

**Source lines 1138–1165:**

```text
  1138 |     def prepare_reactive_walk_forward(
  1139 |         self,
  1140 |         *,
  1141 |         data: pd.DataFrame,
  1142 |         strategy_factory: object,
  1143 |         walkforward_config: WalkForwardConfig,
  1144 |         runtime_config=None,
  1145 |         symbols: Optional[Sequence[str]] = None,
  1146 |     ):
  1147 |         """Prepare the explicit W3 reactive walk-forward route.
  1148 | 
  1149 |         Unlike :meth:`walk_forward`, this route scores native command/account
  1150 |         lifecycles rather than converting a dynamic strategy into a signal
  1151 |         series.  It is currently certified for a reset-flat account per fold;
  1152 |         the returned result intentionally exposes segmented OOS accounts and
  1153 |         never fabricates one compounded carry-equity curve.
  1154 |         """
  1155 | 
  1156 |         from .backends.reactive_wfo import ReactivePreparedWfoRuntimeV1
  1157 | 
  1158 |         return ReactivePreparedWfoRuntimeV1(
  1159 |             endpoint=self,
  1160 |             data=data,
  1161 |             strategy_factory=strategy_factory,
  1162 |             walkforward_config=walkforward_config,
  1163 |             runtime_config=runtime_config,
  1164 |             symbols=symbols,
  1165 |         )
```

## VFY11 — `quantbt_candidate/quantbt/backends/native_wfo_public.py`

Compatibility aliases của native metric rows: turnover/trade count, total-return alias và volatility placeholder.

**SHA-256:** `e4725ad1f841b42454b2aff967f3e82949b3a9545ad23d7aa85bc4ebf5f232ee`

**Source lines 242–265:**

```text
   242 |                 raise RuntimeError("prepared native WFO batch omitted a requested scenario row")
   243 |             if int(result.status[row_index]) != 0:
   244 |                 detail = "; ".join(result.errors) if result.errors else "unknown native prepared failure"
   245 |                 raise RuntimeError(
   246 |                     "prepared native WFO scoring failed for "
   247 |                     f"fold_id={int(result.fold_id[row_index])}, scenario_id={scenario_id}: {detail}"
   248 |                 )
   249 |             metrics.append(
   250 |                 {
   251 |                     "sharpe": float(result.sharpe[row_index]),
   252 |                     # Historical WFO trade-frequency penalties consume the
   253 |                     # public report position-trace count, not fill count or
   254 |                     # quote turnover. Rust emits it without a Python replay.
   255 |                     "turnover": float(result.report_trade_count[row_index]),
   256 |                     "trade_count": float(result.report_trade_count[row_index]),
   257 |                     "mean_return": float(result.total_return[row_index]),
   258 |                     "volatility": 0.0,
   259 |                     "max_drawdown_pct": float(result.max_drawdown[row_index]) * 100.0,
   260 |                     "profit_factor": float(result.profit_factor[row_index]),
   261 |                 }
   262 |             )
   263 |         self._stats["score_adapter"] = str(result.metadata["adapter"])
   264 |         self._stats["score_python_row_objects"] = int(result.metadata["python_row_objects"])
   265 |         return metrics
```

---

# PHỤ LỤC BUNDLE — Ba deliverables gốc trong một tài liệu

**Không cần ba file cũ để đọc hoặc khôi phục evidence dưới đây.** Payloads giữ đúng bytes gốc; các code/probe outputs vẫn mang trạng thái lịch sử, không phải corrected-run results.

## Danh tính ba inputs

| Input | Bytes | SHA-256 |
|---|---:|---|
| `REGIME_LAB_ACTUAL_SOURCE_AUDIT_VI.md` | 48,893 | `6c7695461be6f3f32c7606349325cf74ff934a9ce1548df32d5e18184fc32373` |
| `REGIME_LAB_SOURCE_AUDIT_EVIDENCE_2026_09_11.zip` | 252,527 | `658b83886528cded740c6e28aedec19a35ed55113a975a6a0ab7f73ba4539acc` |
| `REGIME_LAB_SOURCE_EXCERPTS_VI.md` | 118,676 | `7909dd54724e0bcc2d7f35eea136797446a5612415deffb69b7bc93180c9c614` |

## Member index — actual bytes khi hợp nhất

Bảng này không tự chứa hash của chính nó; tránh self-referential manifest. Hash của original ZIP ở trên giữ container identity.

| Member | Bytes | Encoding | SHA-256 |
|---|---:|---|---|
| `README.md` | 2,153 | `utf8` | `89bf2a89d2ea53bee16cd1f27badbd28e5cf31089aa8ccaa5701284288de5eb8` |
| `REGIME_LAB_ACTUAL_SOURCE_AUDIT_VI.md` | 48,893 | `utf8` | `6c7695461be6f3f32c7606349325cf74ff934a9ce1548df32d5e18184fc32373` |
| `REGIME_LAB_SOURCE_EXCERPTS_VI.md` | 118,676 | `utf8` | `7909dd54724e0bcc2d7f35eea136797446a5612415deffb69b7bc93180c9c614` |
| `additional_probe_results.json` | 1,484 | `utf8` | `e41a4891d23ffbc3c1f84dad55cb5bfdb1b701bfa033dfbbdabfc6054c4b8930` |
| `additional_probes.log` | 1,134 | `utf8` | `c43dea98ba289b41a3e40eedb1f8102b74997fe1d53f35eefecb429f42adad25` |
| `additional_probes.py` | 4,262 | `utf8` | `2424611cdc8e2b2cb4f77d52d64a77e652cd5ada5fcd4d45ba17b64dae9842a9` |
| `archive_inventory.json` | 412,980 | `zlib+base64` | `6c2e696f30c3efa8378a038f0c4f1c49e2ef9704896124e0bdd5c45bd6da224f` |
| `artifact_index.json` | 660,500 | `zlib+base64` | `09ce26c55b30c2a9dd716c8ad170b9a84fe08f27a373eb5368eca14f72d2d813` |
| `audit_bundle_manifest.json` | 3,366 | `utf8` | `4fdc2b11ac155ec3ec9d4a27875a0cb59ef3b59fa5bbdaf4d31493c49cea7742` |
| `audit_evidence.py` | 3,902 | `utf8` | `4b7f5b4e5488594e358c01fe7adc6ceee3ac2e001ef779bd807c92e4f505d44a` |
| `audit_probe_results.json` | 3,695 | `utf8` | `bd03eff7001a8cfd69b06cf7deb442063851611fdda5fbf01110020422a66667` |
| `audit_probes.log` | 1,919 | `utf8` | `0c4c6fdf644665df9eb16622b2e679bc30a6eea8c6ec89707c9e0256bee41475` |
| `audit_probes.py` | 6,887 | `utf8` | `05c7c3552936cb1c285d872accd04a36ddc09de92b85a73cd2d39536e170b60e` |
| `evidence_reanalysis.json` | 79,726 | `utf8` | `789cb49419cbb0f0bc7bf56326494f1ebdf77af9f2db7e0bd63031bf66b76c82` |
| `evidence_reanalysis.log` | 4,187 | `utf8` | `97f413803259d94541e91d9705b58b6f5347a6b2ee36306a04d74e75c2cd6c04` |
| `jsonl_row_counts.json` | 46,061 | `utf8` | `6272488e0b7d9a06d3e1d3f780e48f3e26d10280b15ca401b6ea28aeac0dd05c` |
| `pytest_subset.log` | 19,794 | `utf8` | `9925e83b7cde5618b03474548bae795ca11029a41329b9beb0d7d6213c91795c` |
| `source_excerpt_manifest.json` | 5,666 | `utf8` | `0d09ce5c384a55e81bb8bf5e762a82a966d3001aa3cc41f43ad5f7c98a86b998` |
| `transition_audit.json` | 24,890 | `utf8` | `408e91be67f1c6559424c0f3dd08d8bb83573b543d73b6f73adc866ca7c1e4fb` |
| `trigger_eligibility_audit.json` | 12,536 | `utf8` | `385345857f4c001866b5649902fc148b5f0f474e14e3b764efda9e30d33b66da` |

## Utility khôi phục — chỉ ghi evidence, không thực thi

Lưu code dưới đây thành `extract_embedded_audit.py` trong một workspace audit được phép. Dùng **bản Markdown đầy đủ, không bị cắt/truncate** và một output directory mới. Utility từ chối path nguy hiểm, nội dung quá lớn, checksum sai hoặc output đã tồn tại. Không dùng trong thư mục production.

```bash
python3 extract_embedded_audit.py REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md --out ./audit_recovered_new
```

```python
#!/usr/bin/env python3
"""Restore audit evidence embedded in one Markdown. No imports from restored code."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zlib

MAX_DOCUMENT = 64 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_MEMBERS = 64
START = re.compile(r'^<!-- AUDIT_MEMBER_V1 (\{[^\n]+\}) -->$', re.MULTILINE)
END = '<!-- AUDIT_MEMBER_END_V1 -->'

def decode_document(document: Path) -> list[tuple[PurePosixPath, bytes]]:
    if document.stat().st_size > MAX_DOCUMENT:
        raise ValueError('Markdown exceeds the allowed input size')
    text = document.read_text(encoding='utf-8')
    matches = list(START.finditer(text))
    if not 1 <= len(matches) <= MAX_MEMBERS:
        raise ValueError('Unexpected embedded member count')
    result = []
    seen: set[str] = set()
    total = 0
    for match in matches:
        meta = json.loads(match.group(1))
        name = meta['path']
        if not isinstance(name, str) or '\\' in name or '\x00' in name:
            raise ValueError('Invalid member path')
        path = PurePosixPath(name)
        if (path.is_absolute() or not path.parts or
                any(part in ('', '.', '..') for part in name.split('/')) or
                name in seen or path.parts[0] != 'regime_lab_audit'):
            raise ValueError('Unsafe or duplicate member path')
        seen.add(name)
        expected = meta['bytes']
        if type(expected) is not int or not 0 <= expected <= MAX_TOTAL:
            raise ValueError('Invalid member size')
        total += expected
        if total > MAX_TOTAL:
            raise ValueError('Archive exceeds allowed total size')
        pos = match.end()
        if text[pos:pos + 1] != '\n':
            raise ValueError('Malformed member separator')
        pos += 1
        fence_end = text.find('\n', pos)
        if fence_end < 0:
            raise ValueError('Missing opening fence')
        opening = text[pos:fence_end]
        fence_match = re.fullmatch(r'(`{4,})(?:[a-zA-Z0-9_+.-]+)?', opening)
        if fence_match is None:
            raise ValueError('Invalid payload fence')
        fence = fence_match.group(1)
        payload_start = fence_end + 1
        closing = '\n' + fence + '\n' + END
        payload_end = text.find(closing, payload_start)
        if payload_end < 0:
            raise ValueError('Missing payload terminator')
        payload = text[payload_start:payload_end]
        encoding = meta['encoding']
        if encoding == 'utf8':
            data = payload.encode('utf-8')
        elif encoding == 'zlib+base64':
            compressed = base64.b64decode(''.join(payload.split()), validate=True)
            decoder = zlib.decompressobj()
            data = decoder.decompress(compressed, expected + 1)
            if (len(data) > expected or decoder.unconsumed_tail or
                    decoder.unused_data or not decoder.eof):
                raise ValueError('Invalid or excessive compressed payload')
        else:
            raise ValueError('Unsupported payload encoding')
        if len(data) != expected:
            raise ValueError(f'Size mismatch: {name}')
        if hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise ValueError(f'SHA-256 mismatch: {name}')
        result.append((path, data))
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('markdown', type=Path)
    parser.add_argument('--out', required=True, type=Path,
                        help='A NEW output directory; existing paths are refused')
    args = parser.parse_args()
    source = args.markdown.resolve(strict=True)
    records = decode_document(source)  # All hashes checked BEFORE any output.
    output = args.out.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Refusing existing output: {output}')
    output.parent.resolve(strict=True)
    output.mkdir(mode=0o700, exist_ok=False)
    root = output.resolve(strict=True)
    for relative, data in records:
        destination = root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.parent.resolve().is_relative_to(root):
            raise ValueError('Resolved output path escaped extraction root')
        with destination.open('xb') as handle:
            handle.write(data)
    print(json.dumps({'status': 'RESTORED_VERIFIED', 'members': len(records),
                      'bytes': sum(len(data) for _, data in records),
                      'output': str(root), 'executed_restored_code': False},
                     ensure_ascii=False))

if __name__ == '__main__':
    main()
```

Đây không phải lệnh chạy các probes hoặc thị trường. Sau khi khôi phục, review scripts và environment riêng trước khi chạy; source paths trong probe được truyền bằng environment theo README.


## B01 — `REGIME_LAB_ACTUAL_SOURCE_AUDIT_VI.md`

Original bytes: **48,893**; SHA-256: `6c7695461be6f3f32c7606349325cf74ff934a9ce1548df32d5e18184fc32373`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/REGIME_LAB_ACTUAL_SOURCE_AUDIT_VI.md","bytes":48893,"sha256":"6c7695461be6f3f32c7606349325cf74ff934a9ce1548df32d5e18184fc32373","encoding":"utf8"} -->
````text
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

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B02 — `REGIME_LAB_SOURCE_EXCERPTS_VI.md`

Original bytes: **118,676**; SHA-256: `7909dd54724e0bcc2d7f35eea136797446a5612415deffb69b7bc93180c9c614`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/REGIME_LAB_SOURCE_EXCERPTS_VI.md","bytes":118676,"sha256":"7909dd54724e0bcc2d7f35eea136797446a5612415deffb69b7bc93180c9c614","encoding":"utf8"} -->
````text
# Regime-lab — Trích đoạn nguồn đã đối chiếu

Nguồn duy nhất: ZIP người dùng cung cấp. Không phải live GitHub HEAD. Số dòng bên trái là số dòng trong file được trích. Các hash là SHA-256 của **toàn file**, không phải riêng excerpt.

## SRC01 — `src/crypto_regime_lab/experiments/factorial.py:170–203`

SHA-256: `9b22545e5f0f6fce59b07cab2d54379ba550890a9e38a3a996f0e243a2846ddf`

```text
  170 | def _schedule_from_selections(selections: list[dict], bars: pd.DataFrame, alpha_id: str,
  171 |                               *, seed_params: dict | None = None
  172 |                               ) -> tuple[VersionWindow, list[VersionWindow], bool]:
  173 |     """Turn a list of (cutoff, params) into an initial version plus a schedule.
  174 | 
  175 |     A selector that returns nothing admissible at every cutoff is a RESULT, not
  176 |     an error: the retention rule keeps the incumbent, and the honest deployment
  177 |     of "never selected" is the seed point held for the whole window. An earlier
  178 |     version raised here and took a nine-cell run down with it, which turned a
  179 |     reportable finding into a crash.
  180 |     """
  181 |     windows: list[VersionWindow] = []
  182 |     for index, record in enumerate(selections):
  183 |         params = record["params"]
  184 |         if params is None:
  185 |             continue                            # retention: the incumbent stays
  186 |         cutoff = pd.Timestamp(record["cutoff"])
  187 |         if cutoff.tzinfo is None:
  188 |             cutoff = cutoff.tz_localize("UTC")
  189 |         position = int(bars.index.searchsorted(cutoff))
  190 |         if position >= len(bars):
  191 |             continue
  192 |         windows.append(VersionWindow(
  193 |             parameter_version=parameter_digest(params), params=params,
  194 |             requested_at_bar=position, activation_id=f"act-{index}"))
  195 |     if windows:
  196 |         return windows[0], windows[1:], False
  197 |     if seed_params is None:
  198 |         raise FactorialError(
  199 |             f"{alpha_id}: the selector chose nothing at any cutoff and no incumbent seed was "
  200 |             "supplied, so there is nothing to deploy")
  201 |     return (VersionWindow(parameter_version=parameter_digest(seed_params),
  202 |                           params=dict(seed_params), requested_at_bar=0,
  203 |                           activation_id="act-incumbent-retained"), [], True)
```

## SRC02 — `src/crypto_regime_lab/integration/continuous_account.py:165–222`

SHA-256: `1c27da4459b009ce6ca4d5630ce173eafc72c035ff153ddda81dba0da6f81f67`

```text
  165 |        bars, and never carried over from the old version's state.
  166 |     """
  167 |     n = len(frame)
  168 |     if n < 10:
  169 |         raise ContinuousAccountError(f"window of {n} bars is too short")
  170 |     arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
  171 |     engine_frame = frame[["open", "high", "low", "close", "volume"]]
  172 |     market = MarketSlice(*arrays, index=frame.index)
  173 | 
  174 |     ordered_schedule = sorted(schedule, key=lambda w: w.requested_at_bar)
  175 | 
  176 |     def sweep(forced_exits: dict[int, float] | None):
  177 |         return _one_sweep(alpha_id, frame, arrays, engine_frame, market, n,
  178 |                           initial=initial, schedule=ordered_schedule, backend=backend,
  179 |                           forced_exits=forced_exits)
  180 | 
  181 |     # The same fixed point run_candidate uses. A single forward pass schedules
  182 |     # protective exits from the per-trade oracle; the whole-window engine run may
  183 |     # disagree once several positions interact, and an unverified disagreement
  184 |     # means the adapter was driven by exits the account did not actually get.
  185 |     # A-SC never fires a protective order, so this loop converges on the first
  186 |     # pass here -- but A-HMA, A-VWAP and A-HASH all rest stops, and LAB-08 runs
  187 |     # those on this same function.
  188 |     forced: dict[int, float] | None = None
  189 |     result = None
  190 |     for attempt in range(max_sweeps):
  191 |         result = sweep(forced)
  192 |         observed = {int(f["bar_index"]): float(f["price"]) for f in result.fills
  193 |                     if f["reason"] in PROTECTIVE}
  194 |         result.diagnostics["sweeps"] = attempt + 1
  195 |         result.diagnostics["protective_exits"] = len(observed)
  196 |         if set(observed) == set(result.diagnostics["applied_exits"]):
  197 |             result.diagnostics["exit_fixed_point_converged"] = True
  198 |             return result
  199 |         forced = observed
  200 |     result.diagnostics["exit_fixed_point_converged"] = False
  201 |     result.diagnostics["unconverged_exit_symmetric_difference"] = len(
  202 |         set(result.diagnostics["applied_exits"]).symmetric_difference(
  203 |             {int(f["bar_index"]) for f in result.fills if f["reason"] in PROTECTIVE}))
  204 |     return result
  205 | 
  206 | 
  207 | def _one_sweep(alpha_id: str, frame: pd.DataFrame, arrays, engine_frame, market,
  208 |                n: int, *, initial: VersionWindow, schedule: list[VersionWindow],
  209 |                backend: str, forced_exits: dict[int, float] | None) -> ContinuousAccountRun:
  210 |     """One chronological pass. Exits come from the oracle, or from a previously
  211 |     observed whole-window run when ``forced_exits`` is supplied."""
  212 |     open_ = arrays[0]
  213 |     pending = list(schedule)
  214 |     active = initial
  215 |     adapter = build_adapter(alpha_id, active.params, market)
  216 |     # Every version's adapter is fed EVERY bar from the moment it is requested,
  217 |     # so its indicators warm on real history rather than being reinitialised at
  218 |     # the switch. Only the active one may emit intents.
  219 |     shadow: dict[str, tuple[Any, VersionWindow, int]] = {}
  220 | 
  221 |     switches: list[SwitchRecord] = []
  222 |     version_by_bar: list[str] = []
```

## SRC03 — `src/crypto_regime_lab/integration/continuous_account.py:275–335`

SHA-256: `1c27da4459b009ce6ca4d5630ce173eafc72c035ff153ddda81dba0da6f81f67`

```text
  275 |                 record.wait("WAITING_FOR_WARM_INDICATORS")
  276 |                 continue
  277 |             adapter = candidate_adapter          # the warmed adapter, not a fresh one
  278 |             active = window
  279 |             record.effective_at_bar = t
  280 |             record.blocked_reason = None
  281 |             record.warm_bars_at_activation = warm_bars
  282 |             del shadow[activation_id]
  283 | 
  284 |         # -- every shadow adapter observes the bar so its indicators stay causal
  285 |         for candidate_adapter, _, _ in shadow.values():
  286 |             if candidate_adapter is not adapter:
  287 |                 candidate_adapter.on_bar_close(t)
  288 | 
  289 |         version_by_bar.append(active.parameter_version)
  290 |         decision = adapter.on_bar_close(t)
  291 |         tape_decisions.append(decision)
  292 |         for intent in decision.intents:
  293 |             if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and t + 1 < n:
  294 |                 side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
  295 |                 qty = ACCOUNT["entry_notional_usdt"] / max(float(open_[t + 1]), 1e-12)
  296 |                 follow_ups = adapter.on_fill(Fill(index=t + 1, side=side,
  297 |                                                  quantity=float(side) * qty,
  298 |                                                  price=float(open_[t + 1]),
  299 |                                                  intent_kind=intent.kind))
  300 |                 entries += 1
  301 |                 stop = take_profit = float("nan")
  302 |                 for follow in follow_ups:
  303 |                     if follow.stop_price is not None:
  304 |                         stop = float(follow.stop_price)
  305 |                         tp = follow.take_profit_price
  306 |                         if tp is None and follow.ladder:
  307 |                             tp = follow.ladder[-1][0]
  308 |                         take_profit = float(tp) if tp is not None else float("nan")
  309 |                 if np.isfinite(stop) or np.isfinite(take_profit):
  310 |                     pending_levels[t] = (stop, take_profit)
  311 |                     if forced_exits is None:
  312 |                         bar, price, _ = _exit_oracle(engine_frame, t, side, stop, take_profit,
  313 |                                                      backend=backend)
  314 |                         next_exit_bar, next_exit_price = bar, price
  315 |             elif intent.kind is IntentKind.EXIT_ALL and adapter.state.position != 0.0 \
  316 |                     and t + 1 < n:
  317 |                 adapter.on_fill(Fill(index=t + 1, side=-int(np.sign(adapter.state.position)),
  318 |                                      quantity=-adapter.state.position,
  319 |                                      price=float(open_[t + 1]),
  320 |                                      intent_kind=IntentKind.EXIT_ALL))
  321 |                 next_exit_bar, next_exit_price = None, None
  322 | 
  323 |         # a switch requested while flat, on a bar with no new entry, may land next loop
  324 |         if adapter.state.position == 0.0 and shadow:
  325 |             for activation_id in list(shadow):
  326 |                 record = next(s for s in switches if s.activation_id == activation_id)
  327 |                 if record.blocked_reason == "TRANSITION_BLOCKED_OPEN_CAMPAIGN":
  328 |                     record.blocked_reason = "WAITING_FOR_WARM_INDICATORS"
  329 | 
  330 |     if len(tape_decisions) != n:
  331 |         raise ContinuousAccountError(
  332 |             f"the decision tape has {len(tape_decisions)} rows for {n} bars; every bar must "
  333 |             "contribute exactly one decision from whichever version was active on it")
  334 |     build = build_intent_tape(tape_decisions, n, unit_size=1.0, pending_levels=pending_levels)
  335 |     out = _engine(engine_frame, build, backend)
```

## SRC04 — `src/crypto_regime_lab/experiments/regime_schedule.py:78–156`

SHA-256: `c8f50b326cfcff56913d855ea5f3bb40c7877d8afe48d74187a6a3d1bf066b15`

```text
   78 | def transition_cutoffs(emissions: list[dict], *, count: int, earliest: str,
   79 |                        latest: str, min_gap_days: float = 30.0) -> RegimeSchedule:
   80 |     """Pick ``count`` refresh times from state changes already emitted.
   81 | 
   82 |     One trigger per period, not the first ``count`` transitions. Taking them
   83 |     greedily from the front puts every refresh in the opening months and leaves
   84 |     the arm holding its initial parameters for years -- which is a coverage
   85 |     artefact wearing a timing result's clothes. Splitting the window into as many
   86 |     periods as the calendar has folds and taking the first transition INSIDE each
   87 |     period gives the same cadence with the timing chosen by the model, which is
   88 |     the only difference the contrast is meant to measure.
   89 | 
   90 |     Two properties make it causal rather than merely plausible.
   91 | 
   92 |     A trigger sits at an emission's ``available_at``, not at the bar it
   93 |     describes: the state for a bar that has not closed is not knowable, and
   94 |     LAB-07 found a version of this published fifteen times too early.
   95 | 
   96 |     And no transition is ranked by how large or how profitable it turned out to
   97 |     be. "The biggest transitions" is a quantity only the future knows; within a
   98 |     period the FIRST one is taken.
   99 |     """
  100 |     earliest_ts = pd.Timestamp(earliest)
  101 |     latest_ts = pd.Timestamp(latest)
  102 |     if earliest_ts.tzinfo is None:
  103 |         earliest_ts = earliest_ts.tz_localize("UTC")
  104 |     if latest_ts.tzinfo is None:
  105 |         latest_ts = latest_ts.tz_localize("UTC")
  106 | 
  107 |     changes: list[pd.Timestamp] = []
  108 |     previous = None
  109 |     for record in emissions:
  110 |         state = (record.get("state_namespace"), record.get("state_id"))
  111 |         moment = pd.Timestamp(record["available_at"])
  112 |         if moment.tzinfo is None:
  113 |             moment = moment.tz_localize("UTC")
  114 |         if previous is not None and state != previous and earliest_ts <= moment <= latest_ts:
  115 |             changes.append(moment)
  116 |         previous = state
  117 | 
  118 |     period = (latest_ts - earliest_ts) / count
  119 |     chosen: list[pd.Timestamp] = []
  120 |     gap = pd.Timedelta(days=min_gap_days)
  121 |     for index in range(count):
  122 |         window_start = earliest_ts + period * index
  123 |         window_end = earliest_ts + period * (index + 1)
  124 |         candidates = [m for m in changes if window_start <= m < window_end
  125 |                       and (not chosen or m - chosen[-1] >= gap)]
  126 |         if candidates:
  127 |             chosen.append(candidates[0])            # first in the period, never "biggest"
  128 |         else:
  129 |             raise ScheduleError(
  130 |                 f"no state change between {window_start.date()} and {window_end.date()} that "
  131 |                 f"respects the {min_gap_days:g}-day gap. A dynamic arm cannot be given a refresh "
  132 |                 "the states did not ask for, and one padded to the count is just the calendar")
  133 | 
  134 |     if len(chosen) != count:
  135 |         raise ScheduleError(
  136 |             f"placed {len(chosen)} of {count} refresh times; a dynamic arm with fewer refreshes "
  137 |             "is not compute-matched")
  138 |     return RegimeSchedule(
  139 |         cutoffs=tuple(t.isoformat() for t in chosen),
  140 |         source=(f"{len(changes)} emitted state changes; the first inside each of {count} equal "
  141 |                 f"periods, with a {min_gap_days:g}-day minimum gap"))
  142 | 
  143 | 
  144 | def assert_compute_matched(calendar: CalendarSpec, schedule: RegimeSchedule) -> dict:
  145 |     """The dynamic arm may not buy its advantage with extra searches."""
  146 |     matched = calendar.folds == schedule.folds and calendar.train_days == schedule.train_days
  147 |     return {
  148 |         "schema": "crypto_regime_lab.compute_match_check.v1",
  149 |         "calendar_refreshes": calendar.folds,
  150 |         "dynamic_refreshes": schedule.folds,
  151 |         "calendar_train_days": calendar.train_days,
  152 |         "dynamic_train_days": schedule.train_days,
  153 |         "matched": bool(matched),
  154 |         "rule": ("same refresh count and same training memory. Only the timing differs, which is "
  155 |                  "the contribution being measured (guide 10.1 arm C: 'training memory giữ như A')"),
  156 |     }
```

## SRC05 — `scripts/run_lab08_factorial.py:260–303`

SHA-256: `e260ffc4f542b56ceb3f78b6523d77d84a116a7f6ab48c6b382600be87eab49b`

```text
  260 |     else:
  261 |         try:
  262 |             schedule = transition_cutoffs(
  263 |                 emissions, count=CB.CALENDAR.folds,
  264 |                 earliest=f"{window_start} 00:00:00+00:00",
  265 |                 latest=f"{window_end} 00:00:00+00:00")
  266 |         except ScheduleError as exc:
  267 |             # no padding: a dynamic arm the states cannot support is absent, not
  268 |             # quietly replaced by an evenly spaced calendar
  269 |             for arm in ("C", "D", "E"):
  270 |                 results[arm] = ArmResult(arm, alpha_id, symbol, "TOO_FEW_TRANSITIONS",
  271 |                                          detail={"reason": str(exc)})
  272 |             notes["state_provider"] = "TOO_FEW_TRANSITIONS"
  273 |         else:
  274 |             notes["regime_schedule"] = schedule.as_record()
  275 |             notes["compute_match"] = assert_compute_matched(CB.CALENDAR, schedule)
  276 |             if progress:
  277 |                 progress(f"  {alpha_id}/{symbol}: {schedule.folds} regime cutoffs "
  278 |                          f"{[c[:10] for c in schedule.cutoffs]}")
  279 |             dynamic = selections_at_cutoffs(alpha_id, symbol, training_bars,
  280 |                                             list(schedule.cutoffs), progress=progress)
  281 |             notes["regime_cutoff_evidence"] = dynamic["evidence"]
  282 |             for arm, which in (("C", "A"), ("D", "B")):
  283 |                 results[arm] = run_arm(arm, alpha_id, symbol, bars, dynamic["per_arm"][which])
  284 |                 notes["deployed_selections"][arm] = dynamic["per_arm"][which]
  285 |             notes["deployed_selections"]["E"] = dynamic["per_arm"]["B"]
  286 |             # arm E extends D with the bank/response policy; without a switch the
  287 |             # policy deploys D's schedule, which is reported rather than hidden
  288 |             results["E"] = run_arm("E", alpha_id, symbol, bars, dynamic["per_arm"]["B"])
  289 |             results["E"].detail["policy_note"] = (
  290 |                 "LAB-06 measured ZERO switches for this policy on the registered thresholds, so E "
  291 |                 "deploys D's schedule and its own contribution is null by construction here. "
  292 |                 "That is reported, not hidden: E is an extension and never a substitute for C "
  293 |                 "or D")
  294 | 
  295 |     record = {
  296 |         "alpha_id": alpha_id, "symbol": symbol, "status": "RUN",
  297 |         "window": [window_start, window_end],
  298 |         "bars": int(len(bars)),
  299 |         "decision_bars": protocol["timeframes"][alpha_id]["decision_bars"],
  300 |         "arms": {arm: results[arm].as_record() for arm in ARMS},
  301 |         "contrasts": {},
  302 |         "notes": notes,
  303 |         "wall_seconds": time.perf_counter() - started,
```

## SRC06 — `scripts/run_response_policy.py:46–147`

SHA-256: `b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83`

```text
   46 | STUDY_ID = "crypto_regime_timeedge_v2"
   47 | SNAPSHOT_ID = "server_core_v1"
   48 | ALPHA, SYMBOL = "A-SC", "BTCUSDT"
   49 | HORIZON_DAYS = EP.PILOT_HORIZON_DAYS
   50 | BANK_WARMUP_BARS = 120
   51 | DEVELOPMENT_END = "2023-12-31"
   52 | 
   53 | #: The policy is the same policy in both roles. LAB-06 ran it on development;
   54 | #: L09.5 runs it on the confirmation interval to see how it behaves where the
   55 | #: design was not built -- new episodes, ambiguous states, a bank that goes stale.
   56 | #: The thresholds, the horizon, the warmup and the cost model are NOT touched
   57 | #: between the two: a policy retuned for the confirmation is not a confirmation.
   58 | ROLES = {
   59 |     "development": {
   60 |         "cells_dir": LAB_ROOT / ".cache" / "lab04_cells",
   61 |         "tape": "lab05_emission_tape.json",
   62 |         "window": (None, DEVELOPMENT_END),
   63 |         "prefix": "lab06",
   64 |         "panel": "response_panel.parquet",
   65 |     },
   66 |     "confirmation": {
   67 |         "cells_dir": LAB_ROOT / ".cache" / "lab09_cells",
   68 |         "tape": "lab09_btcusdt_emission_tape.json",
   69 |         "window": ("2024-01-01", "2026-08-31"),
   70 |         "prefix": "lab09_policy",
   71 |         "panel": "lab09_policy_response_panel.parquet",
   72 |     },
   73 | }
   74 | ROLE = "development"
   75 | CELLS_DIR = ROLES["development"]["cells_dir"]
   76 | 
   77 | 
   78 | def load_contexts(tape_name: str) -> dict:
   79 |     """Emissions keyed by the time they became AVAILABLE, not observed."""
   80 |     tape = json.loads((LAB_ROOT / "configs" / tape_name).read_text())
   81 |     def _utc(value):
   82 |         """The panel stores naive UTC; the bar index is tz-aware. Normalise once here
   83 |         rather than comparing them and hoping."""
   84 |         stamp = pd.Timestamp(value)
   85 |         return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
   86 | 
   87 |     rows = []
   88 |     for namespace, record in tape["namespaces"].items():
   89 |         for emission in record["emissions"]:
   90 |             rows.append({
   91 |                 "available_at": _utc(emission["available_at"]),
   92 |                 "observed_at": _utc(emission["observed_at"]),
   93 |                 "namespace": namespace, "state_id": emission["state_id"],
   94 |                 "features": emission["feature_contributions"],
   95 |                 "quality_status": emission["quality_status"],
   96 |                 "decision_eligible": emission["decision_eligible"],
   97 |                 "second_best_gap": emission["second_best_gap"],
   98 |             })
   99 |     rows.sort(key=lambda r: r["available_at"])
  100 |     return {"rows": rows, "namespaces": sorted(tape["namespaces"])}
  101 | 
  102 | 
  103 | def context_at(rows: list, when: pd.Timestamp) -> dict | None:
  104 |     """The most recent emission ALREADY AVAILABLE at ``when``. Never a later one."""
  105 |     best = None
  106 |     for row in rows:
  107 |         if row["available_at"] <= when:
  108 |             best = row
  109 |         else:
  110 |             break
  111 |     return best
  112 | 
  113 | 
  114 | def cutoff_records(cell: dict) -> list[dict]:
  115 |     """The (cutoff, evidence) pairs this cell produced, in either runner's shape.
  116 | 
  117 |     LAB-04 wrote them as `folds`; the LAB-09 confirmation runner writes them under
  118 |     `notes.calendar_cutoff_evidence` because it also carries a regime schedule.
  119 |     Same records, two containers -- read both rather than duplicating the policy.
  120 |     """
  121 |     if cell.get("folds"):
  122 |         return cell["folds"]
  123 |     return (cell.get("notes") or {}).get("calendar_cutoff_evidence") or []
  124 | 
  125 | 
  126 | def load_discoveries() -> list:
  127 |     """Candidates from the selector's search, each tagged with its discovery cutoff."""
  128 |     cell = json.loads((CELLS_DIR / f"{ALPHA}_{SYMBOL}.json").read_text())
  129 |     out = []
  130 |     for fold in cutoff_records(cell):
  131 |         evidence = fold.get("cutoff_evidence")
  132 |         if not evidence:
  133 |             continue
  134 |         cutoff = pd.Timestamp(fold["cutoff"])
  135 |         if cutoff.tzinfo is None:
  136 |             cutoff = cutoff.tz_localize("UTC")
  137 |         for point_id, score in evidence["robust_scores"].items():
  138 |             out.append({
  139 |                 "candidate_id": f"{point_id}",
  140 |                 "params": score["params"],
  141 |                 "discovered_at": cutoff,
  142 |                 "score": score.get("r") if score.get("r") is not None else -1e9,
  143 |                 "validation_panel": {k: score.get(k) for k in
  144 |                                      ("g", "f", "r", "p_survive", "episodes_used",
  145 |                                       "neighbours_used", "status")},
  146 |                 "reason": f"discovered by the LAB-04 search at cutoff {fold['cutoff'][:10]}",
  147 |             })
```

## SRC07 — `src/crypto_regime_lab/regime/emissions.py:190–240`

SHA-256: `1ece10418d865eb1010d2cfbb66125caded2034c8fbf09bbb2c4ca02a2239a1f`

```text
  190 |             shift = float(costs.min())
  191 |             costs = costs - shift
  192 |             self._offset += shift
  193 |         self._previous = costs
  194 |         return int(np.argmin(costs)), costs, raw
  195 | 
  196 | 
  197 | def build_emission(state_id: int, costs: np.ndarray, *, namespace: str, z_t: np.ndarray,
  198 |                    centroids: np.ndarray, weights: np.ndarray, groups: dict,
  199 |                    observed_at: str, available_at: str, inferred_at: str,
  200 |                    model_fit_cutoff: str, ready_at: str, version: str,
  201 |                    quality_status: str = QUALITY_OK,
  202 |                    input_refs: tuple[str, ...] = (),
  203 |                    novelty_score: float = 0.0,
  204 |                    decision_eligible: bool = True) -> Emission:
  205 |     """Assemble one emission with the fields guide 8.5 requires."""
  206 |     if quality_status not in QUALITY_STATUSES:
  207 |         raise JumpModelError(f"unknown quality status {quality_status!r}")
  208 |     z_t = np.asarray(z_t, dtype=np.float64)
  209 |     weights = np.asarray(weights, dtype=np.float64)
  210 |     residual = z_t - np.asarray(centroids, dtype=np.float64)[state_id]
  211 |     per_feature = 0.5 * weights * residual * residual
  212 |     group_contributions: dict[str, float] = {}
  213 |     for name, indices in groups.items():
  214 |         group_contributions[name] = float(per_feature[list(indices)].sum())
  215 |     gap = float(second_best_gap(np.asarray(costs).reshape(1, -1))[0])
  216 |     return Emission(
  217 |         state_id=int(state_id), state_namespace=namespace,
  218 |         state_costs=tuple(float(c) for c in costs), second_best_gap=gap,
  219 |         fit_residual=float(per_feature.sum()), novelty_score=float(novelty_score),
  220 |         feature_contributions=tuple(float(c) for c in per_feature),
  221 |         group_contributions=group_contributions,
  222 |         observed_at=observed_at, available_at=available_at, inferred_at=inferred_at,
  223 |         model_fit_cutoff=model_fit_cutoff, ready_at=ready_at, version=version,
  224 |         quality_status=quality_status, input_refs=tuple(input_refs),
  225 |         membership_score=tuple(float(m) for m in membership_scores(np.asarray(costs))),
  226 |         membership_is_calibrated=False, decision_eligible=decision_eligible)
  227 | 
  228 | 
  229 | def batch_stream_parity(z: np.ndarray, centroids: np.ndarray, weights: np.ndarray,
  230 |                         lambda_jump: float, *, namespace: str = "parity") -> dict:
  231 |     """T38 — streaming one observation at a time must equal the batch filter at EVERY prefix."""
  232 |     from .jump_model import forward_filter
  233 | 
  234 |     z = np.asarray(z, dtype=np.float64)
  235 |     batch = forward_filter(loss_matrix(z, centroids, weights), lambda_jump, normalise=True)
  236 | 
  237 |     streamer = OnlineStateFilter(centroids, weights, lambda_jump, namespace=namespace)
  238 |     stream_states, stream_costs = [], []
  239 |     for t in range(z.shape[0]):
  240 |         state, costs, _ = streamer.step(z[t])
```

## SRC08 — `scripts/run_response_policy.py:195–270`

SHA-256: `b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83`

```text
  195 |     # ---- L06.1 horizon from holding diagnostics -----------------------
  196 |     probe = run_candidate(ALPHA, dict(SEED_POINTS[ALPHA]),
  197 |                           bars[(bars.index >= cutoffs[0]) & (bars.index < cutoffs[1])])
  198 |     holding = window_metrics(probe)
  199 |     bar_hours = pd.Timedelta(DECISION_INTERVAL[ALPHA]).total_seconds() / 3600.0
  200 |     horizon_note = EP.horizon_from_holding_diagnostics(
  201 |         holding["mean_holding_bars"] or 0.0, bar_hours)
  202 | 
  203 |     # ---- L06.2 bank at each cutoff, lineage enforced ------------------
  204 |     banks = {}
  205 |     with writer.attempt("L06.2.bank") as att:
  206 |         for cutoff in cutoffs:
  207 |             banks[cutoff] = BK.build_bank(
  208 |                 cutoff, discoveries, adapter_hash=BK.parameter_digest({"alpha": ALPHA}),
  209 |                 warmup_bars=BANK_WARMUP_BARS, schema=schema)
  210 |         att.detail = {"cutoffs": len(banks),
  211 |                       "sizes": [len(b.admissible()) for b in banks.values()]}
  212 | 
  213 |     # ---- L06.1 episodes for every bank candidate ----------------------
  214 |     windows = EP.build_grid(bars.index, horizon_days=HORIZON_DAYS)
  215 |     window_index = {start: i for i, (start, _end) in enumerate(windows)}
  216 |     all_candidates: dict[str, dict] = {}
  217 |     for bank_obj in banks.values():
  218 |         for entry in bank_obj.admissible():
  219 |             all_candidates.setdefault(entry.candidate_id, entry.params)
  220 |     incumbent_id = "incumbent_seed"
  221 |     all_candidates[incumbent_id] = dict(SEED_POINTS[ALPHA])
  222 | 
  223 |     def outcome_for(params):
  224 |         def _fn(start, end):
  225 |             window = bars[(bars.index >= start) & (bars.index < end)]
  226 |             if len(window) < 20:
  227 |                 return None
  228 |             try:
  229 |                 run = run_candidate(ALPHA, params, window)
  230 |             except Exception:
  231 |                 return None
  232 |             metrics = window_metrics(run)
  233 |             return {"net_return": metrics["net_return"],
  234 |                     "max_drawdown": metrics["max_drawdown"],
  235 |                     "turnover": float(metrics["entries"]) * ACCOUNT["entry_notional_usdt"]
  236 |                     / ACCOUNT["initial_capital_usdt"],
  237 |                     "cost": float(metrics["fills"]) * ACCOUNT["taker_fee_rate"],
  238 |                     "trades": metrics["fills"], "exposure": metrics["exposure"],
  239 |                     "terminal_position": 0.0 if run.positions[-1] == 0 else float(
  240 |                         run.positions[-1])}
  241 |         return _fn
  242 | 
  243 |     context_lookup = {}
  244 |     for start, _end in windows:
  245 |         row = context_at(contexts["rows"], start)
  246 |         if row is not None and row["decision_eligible"]:
  247 |             context_lookup[start] = {"features": row["features"], "state_id": row["state_id"],
  248 |                                      "namespace": row["namespace"]}
  249 | 
  250 |     grids = {}
  251 |     with writer.attempt("L06.1.episodes") as att:
  252 |         for candidate_id, params in all_candidates.items():
  253 |             grids[candidate_id] = EP.build_episodes(
  254 |                 decision_times=[s for s, _ in windows], contexts=context_lookup,
  255 |                 candidate_id=candidate_id, parameter_version=BK.parameter_digest(params),
  256 |                 outcome_fn=outcome_for(params), horizon_days=HORIZON_DAYS)
  257 |         att.detail = {"candidates": len(grids),
  258 |                       "episodes": sum(len(g.episodes) for g in grids.values())}
  259 | 
  260 |     # ---- L06.3 + L06.4 decisions at every episode boundary ------------
  261 |     scheduler = CL.Scheduler()
  262 |     book = CP.CampaignBook()
  263 |     for candidate_id in all_candidates:
  264 |         book.warmups[candidate_id] = CP.IndicatorWarmup(candidate_id, BANK_WARMUP_BARS,
  265 |                                                         bars_seen=BANK_WARMUP_BARS)
  266 |     ledger, responses = [], []
  267 |     response_status_counts: dict[str, int] = {}
  268 |     current_incumbent = incumbent_id
  269 |     last_switch_at = None
  270 | 
```

## SRC09 — `scripts/run_response_policy.py:319–415`

SHA-256: `b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83`

```text
  319 |             estimates, costs = [], {}
  320 |             pooled = {}
  321 |             for entry in active:
  322 |                 if entry.candidate_id == current_incumbent:
  323 |                     continue
  324 |                 data = prepared.get(entry.candidate_id)
  325 |                 if data is None:
  326 |                     continue
  327 |                 n = usable_prefix(entry.candidate_id, decision_time)
  328 |                 keep = [k for k in range(n) if data["decision_time"][k] in inc_by_time]
  329 |                 if not keep:
  330 |                     continue
  331 |                 cand_u = data["net_return"][keep]
  332 |                 inc_u = np.asarray([inc_by_time[data["decision_time"][k]] for k in keep])
  333 |                 ctx = data["context"][keep]
  334 |                 ages = np.asarray([(decision_time - data["decision_time"][k]).total_seconds()
  335 |                                    / 86400.0 for k in keep])
  336 |                 elig = np.ones(len(keep))
  337 |                 ids = [data["episode_id"][k] for k in keep]
  338 |                 order = data["order"][keep]
  339 |                 # the pooled prior: an UNWEIGHTED mean over every eligible episode, so it
  340 |                 # carries no information about the current context and is a genuine prior
  341 |                 # rather than a second copy of the local estimate
  342 |                 pooled.update(RS.pooled_delta_from({entry.candidate_id: cand_u - inc_u}))
  343 |                 estimate = RS.estimate_response(
  344 |                     response_id=f"resp-{i}-{entry.candidate_id}",
  345 |                     candidate_id=entry.candidate_id, incumbent_id=current_incumbent,
  346 |                     x_t=np.asarray(row["features"], dtype=float),
  347 |                     contexts=ctx, ages_days=ages, eligibility=elig,
  348 |                     feature_weights=np.full(len(row["features"]),
  349 |                                             1.0 / len(row["features"])),
  350 |                     candidate_utility=cand_u, incumbent_utility=inc_u,
  351 |                     episode_ids=ids, order=order,
  352 |                     pooled_delta=pooled[entry.candidate_id])
  353 |                 estimates.append(estimate)
  354 |                 if len(responses) < 4000:
  355 |                     responses.append(estimate.as_record())
  356 |                 response_status_counts[estimate.status] = response_status_counts.get(
  357 |                     estimate.status, 0) + 1
  358 |                 costs[entry.candidate_id] = DC.transition_cost(
  359 |                     projected_turnover=1.0, fee_rate=ACCOUNT["taker_fee_rate"],
  360 |                     slippage_rate=ACCOUNT["slippage_bps"] / 1e4)
  361 | 
  362 |             outcome = DC.decide(
  363 |                 selection_id=f"sel-{i}", decision_time=decision_time,
  364 |                 incumbent_id=current_incumbent, estimates=estimates, costs=costs,
  365 |                 quality_status=row["quality_status"],
  366 |                 campaign_open=bool(book.open_campaigns()),
  367 |                 last_switch_at=last_switch_at,
  368 |                 bank_adequate=bool(active),
  369 |                 warm_candidates={c for c, w in book.warmups.items()
  370 |                                  if w.status == CP.WARMUP_READY},
  371 |                 data_cutoff=str(decision_time), bank_cutoff=str(bank_cutoff),
  372 |                 model_version=row["namespace"],
  373 |                 # guide 13.4: typed params on both sides, and the campaign version
  374 |                 # the decision would replace
  375 |                 incumbent_params=all_candidates.get(current_incumbent),
  376 |                 candidate_params={entry.candidate_id: all_candidates.get(entry.candidate_id)
  377 |                                   for entry in active},
  378 |                 campaign_version=BK.parameter_digest(
  379 |                     all_candidates.get(current_incumbent) or {}))
  380 |             ledger.append(outcome)
  381 |             if outcome.decision == DC.SWITCH_READY:
  382 |                 book.request_activation(outcome.selection_id, outcome.challenger_id,
  383 |                                         decision_time, outcome.reason)
  384 |                 current_incumbent = outcome.challenger_id
  385 |                 last_switch_at = decision_time
  386 |                 scheduler.counters.switches_executed += 1
  387 |         att.detail = {"decisions": len(ledger), "responses": len(responses)}
  388 | 
  389 |     # ---- L06.5 scheduling behaviour on the real cadence ---------------
  390 |     with writer.attempt("L06.5.clocks") as att:
  391 |         for k, cutoff in enumerate(cutoffs):
  392 |             job = scheduler.trigger(f"bank-{k}", CL.BANK_REFRESH, cutoff,
  393 |                                     "frozen baseline calendar")
  394 |             if job.status == CL.JOB_PENDING:
  395 |                 scheduler.complete(job.job_id, cutoff + pd.Timedelta(hours=6))
  396 |                 scheduler.activate(job.job_id, cutoff + pd.Timedelta(hours=6))
  397 |         att.detail = scheduler.counters.as_record()
  398 | 
  399 |     # ---- outputs ------------------------------------------------------
  400 |     panel = pd.concat([EP.to_frame(g) for g in grids.values()], ignore_index=True)
  401 |     panel_path = policy.resolve_write_target(
  402 |         LAB_ROOT / "evidence" / STUDY_ID / role["panel"])
  403 |     panel.to_parquet(panel_path, index=False)
  404 | 
  405 |     ledger_record = DC.summarize_ledger(ledger)
  406 |     informative = EP.informativeness(panel, incumbent_id)
  407 |     response_model = {
  408 |         "schema": "crypto_regime_lab.response_model.v1",
  409 |         "episode_informativeness": informative,
  410 |         "alpha_id": ALPHA, "symbol": SYMBOL,
  411 |         "horizon": horizon_note,
  412 |         "hyperparameters": RS.hyperparameters(),
  413 |         "responses": responses[:400],
  414 |         "response_count": int(sum(response_status_counts.values())),
  415 |         "status_counts": dict(sorted(response_status_counts.items())),
```

## SRC10 — `src/crypto_regime_lab/policy/response.py:100–200`

SHA-256: `4e372653a18e6257597aacf9d35244750224f74a84119e05403654edcc626057`

```text
  100 |             "diagnostics": self.diagnostics.as_record(),
  101 |             "supporting_episodes": self.supporting_episodes,
  102 |             "estimator_note": ("a policy estimator, not a calibrated posterior. The shrinkage is a "
  103 |                                "declared heuristic and the interval it implies is not a coverage "
  104 |                                "guarantee (guide 9.2)"),
  105 |         }
  106 | 
  107 | 
  108 | def context_distance(x_t: np.ndarray, x_e: np.ndarray, weights: np.ndarray) -> float:
  109 |     """Weighted distance in context space. Weights are TRAIN-ONLY (L06.3.4)."""
  110 |     x_t = np.asarray(x_t, dtype=np.float64)
  111 |     x_e = np.asarray(x_e, dtype=np.float64)
  112 |     weights = np.asarray(weights, dtype=np.float64)
  113 |     if x_t.shape != x_e.shape or weights.shape != x_t.shape:
  114 |         raise ValueError("context vectors and weights must have the same shape")
  115 |     diff = x_t - x_e
  116 |     return float(np.sqrt(np.sum(weights * diff * diff)))
  117 | 
  118 | 
  119 | def similarity_weights(x_t: np.ndarray, contexts: np.ndarray, ages_days: np.ndarray,
  120 |                        eligibility: np.ndarray, feature_weights: np.ndarray, *,
  121 |                        bandwidth: float = BANDWIDTH_H,
  122 |                        tau_days: float = RECENCY_TAU_DAYS) -> np.ndarray:
  123 |     """Guide 9.2: ``w = exp(-d^2/2h^2) * exp(-(t-e)/tau) * q_e``.
  124 | 
  125 |     ``eligibility`` may only be 0 or 1. A continuous "quality" that happened to
  126 |     correlate with outcome would smuggle the answer into the weights, so the
  127 |     function refuses anything else.
  128 |     """
  129 |     contexts = np.asarray(contexts, dtype=np.float64)
  130 |     ages = np.asarray(ages_days, dtype=np.float64)
  131 |     eligibility = np.asarray(eligibility, dtype=np.float64)
  132 |     if not np.all(np.isin(eligibility, (0.0, 1.0))):
  133 |         raise ValueError(
  134 |             "eligibility q_e must be 0 or 1. A graded quality score would let outcome-correlated "
  135 |             "information into the weights, which guide 9.2 forbids")
  136 |     if bandwidth <= 0 or tau_days <= 0:
  137 |         raise ValueError("bandwidth and tau must be positive")
  138 |     distances = np.asarray([context_distance(x_t, c, feature_weights) for c in contexts])
  139 |     kernel = np.exp(-(distances ** 2) / (2.0 * bandwidth ** 2))
  140 |     recency = np.exp(-np.maximum(ages, 0.0) / tau_days)
  141 |     return kernel * recency * eligibility
  142 | 
  143 | 
  144 | def effective_sample(weights: np.ndarray) -> float:
  145 |     weights = np.asarray(weights, dtype=np.float64)
  146 |     total = float(weights.sum())
  147 |     if total <= 0:
  148 |         return 0.0
  149 |     return float(total ** 2 / float(np.sum(weights ** 2)))
  150 | 
  151 | 
  152 | #: The support set is the smallest group of episodes carrying this share of the
  153 | #: weight. Counting blocks over EVERY episode with a non-zero weight would always
  154 | #: give one block, because a Gaussian kernel never reaches zero.
  155 | SUPPORT_COVERAGE = 0.90
  156 | 
  157 | 
  158 | def support_set(weights: np.ndarray, coverage: float = SUPPORT_COVERAGE) -> np.ndarray:
  159 |     """Indices of the smallest set of episodes carrying ``coverage`` of the weight."""
  160 |     weights = np.asarray(weights, dtype=np.float64)
  161 |     total = float(weights.sum())
  162 |     if total <= 0:
  163 |         return np.asarray([], dtype=int)
  164 |     order = np.argsort(-weights)
  165 |     cumulative = np.cumsum(weights[order]) / total
  166 |     keep = int(np.searchsorted(cumulative, coverage) + 1)
  167 |     return np.sort(order[:min(keep, weights.size)])
  168 | 
  169 | 
  170 | def contiguous_blocks(order: np.ndarray, weights: np.ndarray, *,
  171 |                       coverage: float = SUPPORT_COVERAGE) -> int:
  172 |     """How many separate stretches of time the real evidence comes from.
  173 | 
  174 |     Counted over the SUPPORT SET, not over every episode with a non-zero weight.
  175 |     The kernel gives some weight to everything, so a threshold near zero would
  176 |     always report one block and the check would be dead. What matters is whether
  177 |     the episodes actually carrying the estimate sit in one stretch of history or
  178 |     several: twelve consecutive weeks inside one market regime are one piece of
  179 |     evidence wearing twelve hats.
  180 |     """
  181 |     order = np.asarray(order)
  182 |     weights = np.asarray(weights, dtype=np.float64)
  183 |     active = support_set(weights, coverage)
  184 |     if active.size == 0:
  185 |         return 0
  186 |     positions = np.sort(order[active])
  187 |     return 1 + int(np.count_nonzero(np.diff(positions) > 1))
  188 | 
  189 | 
  190 | def lag1_autocorrelation(values: np.ndarray) -> float | None:
  191 |     values = np.asarray(values, dtype=np.float64)
  192 |     if values.size < 3:
  193 |         return None
  194 |     centred = values - values.mean()
  195 |     denominator = float(np.sum(centred ** 2))
  196 |     if denominator <= 0:
  197 |         return None
  198 |     return float(np.sum(centred[1:] * centred[:-1]) / denominator)
  199 | 
  200 | 
```

## SRC11 — `src/crypto_regime_lab/policy/bank.py:155–214`

SHA-256: `c3ef5c2bee708bac0464e603f882ce4d5f844c119719cd25ba9e3e4f125a1a55`

```text
  155 |     with a reason rather than dropped quietly, so the lineage is auditable.
  156 |     """
  157 |     bank = CandidateBank(cutoff=pd.Timestamp(cutoff))
  158 |     bank.trial_rows_retained = len(discoveries)
  159 | 
  160 |     eligible = []
  161 |     for row in discoveries:
  162 |         # normalise once and KEEP IT ON THE ROW. Reading a loop variable from the
  163 |         # filtering pass inside the building pass gave every entry the discovery
  164 |         # time of whichever row happened to be last, which is precisely the
  165 |         # lineage field T46 exists to protect.
  166 |         row = {**row, "discovered_at": pd.Timestamp(row["discovered_at"])}
  167 |         discovered = row["discovered_at"]
  168 |         if discovered > bank.cutoff:
  169 |             bank.rejected.append({
  170 |                 "candidate_id": row["candidate_id"], "discovered_at": str(discovered),
  171 |                 "reason": "discovered after the cutoff; a bank at T may not contain it (T46)"})
  172 |             continue
  173 |         eligible.append(row)
  174 | 
  175 |     # merge effective duplicates for COVERAGE, keeping the trial rows
  176 |     kept: list[BankEntry] = []
  177 |     for row in sorted(eligible, key=lambda r: (-float(r.get("score", 0.0)),
  178 |                                                str(r["candidate_id"]))):
  179 |         duplicate_of = None
  180 |         if schema is not None:
  181 |             for entry in kept:
  182 |                 if schema.distance(entry.params, row["params"]) <= duplicate_distance:
  183 |                     duplicate_of = entry
  184 |                     break
  185 |         if duplicate_of is not None:
  186 |             duplicate_of.merged_duplicates.append(row["candidate_id"])
  187 |             continue
  188 |         if len(kept) >= max_size:
  189 |             bank.rejected.append({
  190 |                 "candidate_id": row["candidate_id"],
  191 |                 "reason": f"bank already holds the proposed maximum of {max_size}"})
  192 |             continue
  193 |         kept.append(BankEntry(
  194 |             candidate_id=row["candidate_id"], params=row["params"],
  195 |             discovered_at=row["discovered_at"], entry_date=bank.cutoff,
  196 |             strategy_adapter_hash=adapter_hash,
  197 |             validation_panel=row.get("validation_panel", {}),
  198 |             warmup_bars_required=warmup_bars,
  199 |             status=STATUS_ACTIVE,
  200 |             reason=row.get("reason", "admitted from a pre-cutoff discovery")))
  201 |     bank.entries = kept
  202 |     return bank
  203 | 
  204 | 
  205 | def specialist_note() -> dict:
  206 |     """Guide 7.4 — a specialist is not dropped just because the pooled mean is lower."""
  207 |     return {
  208 |         "rule": ("a candidate whose pooled mean is below the global best may still belong in the "
  209 |                  "bank if it has conditional evidence with enough support. It is dropped for lack "
  210 |                  "of support or for failing cost/risk constraints, never for a low pooled mean "
  211 |                  "alone (guide 7.4)"),
  212 |         "counted_against_search_budget": True,
  213 |         "inactive_params_do_not_add_diversity": True,
  214 |     }
```

## SRC12 — `src/crypto_regime_lab/experiments/evaluator.py:84–119`

SHA-256: `b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5`

```text
   84 | 
   85 | 
   86 | def _engine(frame: pd.DataFrame, tape, backend: str) -> dict:
   87 |     with warnings.catch_warnings():
   88 |         warnings.simplefilter("ignore")
   89 |         return run_intrabar(frame, tape, backend=backend,
   90 |                             initial_capital=ACCOUNT["initial_capital_usdt"],
   91 |                             fee=ACCOUNT["taker_fee_rate"],
   92 |                             slippage_bps=ACCOUNT["slippage_bps"],
   93 |                             use_funding=ACCOUNT["use_funding"], close_on_last_bar=True,
   94 |                             sizing_mode="fixed_notional",
   95 |                             unit_notional=ACCOUNT["entry_notional_usdt"])
   96 | 
   97 | 
   98 | PROTECTIVE = ("stop_loss", "take_profit", "liquidation")
   99 | 
  100 | 
  101 | def _exit_oracle(engine_frame: pd.DataFrame, decision_bar: int, side: int,
  102 |                  stop: float, take_profit: float, *, backend: str,
  103 |                  horizon: int = ORACLE_HORIZON) -> tuple[int | None, float | None, str | None]:
  104 |     """Ask the ENGINE when this one position's resting protection fires.
  105 | 
  106 |     A single forward pass cannot know this, and iterating the whole window to a
  107 |     fixed point converges only about one trade per pass -- measured at roughly
  108 |     17 s per pass for A-HMA, which is hopeless at a 96-candidate budget. Asking
  109 |     the engine about one trade at a time costs about 10 ms and is exact for the
  110 |     quantity that matters: absolute price levels against that bar's own OHLC.
  111 |     The whole-window run afterwards re-derives these exits and any disagreement
  112 |     is reported rather than absorbed.
  113 |     """
  114 |     n = len(engine_frame)
  115 |     hi = min(n, decision_bar + 1 + horizon)
  116 |     segment = engine_frame.iloc[decision_bar:hi]
  117 |     m = len(segment)
  118 |     if m < 2:
  119 |         return None, None, None
```

## SRC13 — `src/crypto_regime_lab/quantbt_bridge/intent_tape.py:55–150`

SHA-256: `b690b50fa08aba7a42fca1b4474654c61f031d7d708a1ee3dbe1e2a295496a0d`

```text
   55 | def build_intent_tape(decisions: list[BarDecision], n_bars: int, *,
   56 |                       unit_size: float = 1.0,
   57 |                       pending_levels: dict[int, tuple[float, float]] | None = None) -> TapeBuild:
   58 |     """Fold a decision tape into the engine's array form.
   59 | 
   60 |     ``pending_levels`` supplies (stop, take_profit) for an entry bar when the
   61 |     adapter derives them from the fill. The engine prices the entry at the next
   62 |     open, so an absolute level chosen at the decision close is an INTENT the
   63 |     engine may reject or clamp; that is the whole point of feeding it through the
   64 |     engine rather than booking it in the adapter.
   65 |     """
   66 |     entry_side = np.zeros(n_bars)
   67 |     entry_size = np.zeros(n_bars)
   68 |     stop_value = np.full(n_bars, np.nan)
   69 |     take_profit_value = np.full(n_bars, np.nan)
   70 |     technical_exit = np.zeros(n_bars, dtype=bool)
   71 |     decision_map: dict[int, dict] = {}
   72 |     unmapped: list[dict] = []
   73 |     levels = pending_levels or {}
   74 | 
   75 |     for decision in decisions:
   76 |         for intent in decision.intents:
   77 |             t = intent.decision_index
   78 |             if intent.kind is IntentKind.ENTER_LONG:
   79 |                 entry_side[t] = 1.0
   80 |                 entry_size[t] = unit_size
   81 |             elif intent.kind is IntentKind.ENTER_SHORT:
   82 |                 entry_side[t] = -1.0
   83 |                 entry_size[t] = unit_size
   84 |             elif intent.kind is IntentKind.EXIT_ALL:
   85 |                 technical_exit[t] = True
   86 |             elif intent.kind is IntentKind.SET_PROTECTION:
   87 |                 if intent.stop_price is not None:
   88 |                     stop_value[t] = intent.stop_price
   89 |                 if intent.take_profit_price is not None:
   90 |                     take_profit_value[t] = intent.take_profit_price
   91 |                 if intent.ladder:
   92 |                     # A multi-rung ladder is not expressible in this tape; the
   93 |                     # final rung is used and the omission is recorded, never hidden.
   94 |                     take_profit_value[t] = intent.ladder[-1][0]
   95 |                     unmapped.append({
   96 |                         "index": t, "kind": intent.kind.value,
   97 |                         "reason": "ladder_rungs_beyond_final_not_expressible_in_intent_tape",
   98 |                         "rungs": [list(x) for x in intent.ladder],
   99 |                         "handling": "BLOCKED_CAPABILITY for partial ladders on this route",
  100 |                     })
  101 |             elif intent.kind in (IntentKind.AMEND_PROTECTION, IntentKind.CANCEL_PROTECTION,
  102 |                                  IntentKind.REDUCE):
  103 |                 unmapped.append({"index": t, "kind": intent.kind.value,
  104 |                                  "reason": "not expressible in IntrabarIntentTape",
  105 |                                  "handling": "BLOCKED_CAPABILITY"})
  106 |             decision_map.setdefault(t, {"intents": []})["intents"].append(intent.kind.value)
  107 | 
  108 |     for t, (stop, tp) in levels.items():
  109 |         if 0 <= t < n_bars:
  110 |             stop_value[t] = stop
  111 |             take_profit_value[t] = tp
  112 | 
  113 |     return TapeBuild(entry_side, entry_size, stop_value, take_profit_value,
  114 |                      technical_exit, decision_map, unmapped)
  115 | 
  116 | 
  117 | def run_intrabar(frame, tape_build: TapeBuild, *, backend: str = "reference",
  118 |                  initial_capital: float = 20000.0, fee: float = 0.0004,
  119 |                  slippage_bps: float = 1.0, use_funding: bool = False,
  120 |                  funding_timestamps=None, funding_rates=None,
  121 |                  close_on_last_bar: bool = True, symbol: str = "S",
  122 |                  sizing_mode: str = "units", unit_notional: float | None = None) -> dict:
  123 |     """Execute a tape on the installed engine and return the account trace."""
  124 |     import quantbt as q
  125 | 
  126 |     factory = {
  127 |         "reference": q.QuantBTEndpoint.intrabar_bracket_reference,
  128 |         "rust": q.QuantBTEndpoint.intrabar_bracket_rust,
  129 |         "auto": q.QuantBTEndpoint.intrabar_bracket,
  130 |     }[backend]
  131 |     sizing = {"units": q.IntrabarSizingMode.UNITS,
  132 |               "fixed_notional": q.IntrabarSizingMode.FIXED_NOTIONAL}[sizing_mode]
  133 |     kwargs: dict[str, Any] = dict(
  134 |         level_mode=q.IntrabarLevelMode.ABSOLUTE_PRICE,
  135 |         intrabar_sizing_mode=sizing,
  136 |         close_on_last_bar=close_on_last_bar,
  137 |         account=q.AccountConfig(initial_capital=initial_capital),
  138 |         fee=fee, slippage_bps=slippage_bps, symbols=[symbol],
  139 |         use_funding=use_funding,
  140 |     )
  141 |     if sizing is q.IntrabarSizingMode.FIXED_NOTIONAL:
  142 |         if unit_notional is None:
  143 |             raise ValueError("fixed_notional sizing requires unit_notional")
  144 |         # The engine reads the per-entry notional from alloc_per_trade (endpoint.py:3087);
  145 |         # passing it any other way silently sizes every entry at zero.
  146 |         kwargs["alloc_per_trade"] = float(unit_notional)
  147 |     elif unit_notional is not None:
  148 |         raise ValueError("unit_notional only applies to sizing_mode='fixed_notional'")
  149 |     endpoint = factory(**kwargs)
  150 |     backtest_kwargs: dict[str, Any] = {"data": frame, "intent": tape_build.as_tape()}
```

## SRC14 — `src/crypto_regime_lab/experiments/evaluator.py:126–239`

SHA-256: `b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5`

```text
  126 |     tape.take_profit_value[0] = take_profit
  127 |     out = _engine(segment, tape, backend)
  128 |     for fill in out["fills"]:
  129 |         if fill["reason"] in PROTECTIVE:
  130 |             return decision_bar + int(fill["bar_index"]), float(fill["price"]), fill["reason"]
  131 |     return None, None, None
  132 | 
  133 | 
  134 | def _sweep(alpha_id: str, params: dict, frame: pd.DataFrame, arrays: list[np.ndarray],
  135 |            engine_frame: pd.DataFrame, *, backend: str,
  136 |            forced_exits: dict[int, float] | None = None):
  137 |     """One chronological pass. Protective exits come from the oracle, or from a
  138 |     previously observed whole-window run when ``forced_exits`` is supplied."""
  139 |     n = len(frame)
  140 |     open_ = arrays[0]
  141 |     market = MarketSlice(*arrays, index=frame.index)
  142 |     adapter = build_adapter(alpha_id, params, market)
  143 |     pending_levels: dict[int, tuple[float, float]] = {}
  144 |     applied_exits: dict[int, float] = {}
  145 |     next_exit_bar: int | None = None
  146 |     next_exit_price: float | None = None
  147 | 
  148 |     for t in range(n):
  149 |         if forced_exits is not None and t in forced_exits and adapter.state.position != 0.0:
  150 |             adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
  151 |                                  quantity=-adapter.state.position,
  152 |                                  price=float(forced_exits[t]), intent_kind=IntentKind.EXIT_ALL))
  153 |             applied_exits[t] = float(forced_exits[t])
  154 |         elif next_exit_bar == t and adapter.state.position != 0.0:
  155 |             adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
  156 |                                  quantity=-adapter.state.position,
  157 |                                  price=float(next_exit_price), intent_kind=IntentKind.EXIT_ALL))
  158 |             applied_exits[t] = float(next_exit_price)
  159 |             next_exit_bar, next_exit_price = None, None
  160 | 
  161 |         decision = adapter.on_bar_close(t)
  162 |         for intent in decision.intents:
  163 |             if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and t + 1 < n:
  164 |                 side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
  165 |                 qty = ACCOUNT["entry_notional_usdt"] / max(float(open_[t + 1]), 1e-12)
  166 |                 follow_ups = adapter.on_fill(Fill(index=t + 1, side=side,
  167 |                                                   quantity=float(side) * qty,
  168 |                                                   price=float(open_[t + 1]),
  169 |                                                   intent_kind=intent.kind))
  170 |                 stop = take_profit = float("nan")
  171 |                 for follow in follow_ups:
  172 |                     if follow.stop_price is not None:
  173 |                         stop = float(follow.stop_price)
  174 |                         tp = follow.take_profit_price
  175 |                         if tp is None and follow.ladder:
  176 |                             tp = follow.ladder[-1][0]
  177 |                         take_profit = float(tp) if tp is not None else float("nan")
  178 |                 if np.isfinite(stop) or np.isfinite(take_profit):
  179 |                     pending_levels[t] = (stop, take_profit)
  180 |                     if forced_exits is None:
  181 |                         bar, price, _ = _exit_oracle(engine_frame, t, side, stop, take_profit,
  182 |                                                      backend=backend)
  183 |                         next_exit_bar, next_exit_price = bar, price
  184 |             elif intent.kind is IntentKind.EXIT_ALL and adapter.state.position != 0.0 \
  185 |                     and t + 1 < n:
  186 |                 adapter.on_fill(Fill(index=t + 1,
  187 |                                      side=-int(np.sign(adapter.state.position)),
  188 |                                      quantity=-adapter.state.position,
  189 |                                      price=float(open_[t + 1]),
  190 |                                      intent_kind=IntentKind.EXIT_ALL))
  191 |                 next_exit_bar, next_exit_price = None, None
  192 |     return adapter, pending_levels, applied_exits
  193 | 
  194 | 
  195 | def run_candidate(alpha_id: str, params: dict, frame: pd.DataFrame, *,
  196 |                   backend: str = "reference", max_sweeps: int = MAX_SWEEPS) -> CandidateRun:
  197 |     """Evaluate one parameter point over one contiguous window.
  198 | 
  199 |     Sweep chronologically with an exit oracle, run the resulting tape over the
  200 |     whole window, and require the whole-window protective exits to agree with the
  201 |     exits the adapter was actually driven with. Disagreement triggers a bounded
  202 |     repair and, if it persists, ``converged=False`` on the record.
  203 |     """
  204 |     n = len(frame)
  205 |     if n < 10:
  206 |         raise EvaluationError(f"window of {n} bars is too short to evaluate")
  207 |     arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
  208 |     engine_frame = frame[["open", "high", "low", "close", "volume"]]
  209 | 
  210 |     forced: dict[int, float] | None = None
  211 |     out = build = None
  212 |     applied: dict[int, float] = {}
  213 |     sweeps = 0
  214 |     for attempt in range(max_sweeps):
  215 |         sweeps = attempt + 1
  216 |         adapter, pending, applied = _sweep(alpha_id, params, frame, arrays, engine_frame,
  217 |                                            backend=backend, forced_exits=forced)
  218 |         build = build_intent_tape(adapter.decisions, n, unit_size=1.0, pending_levels=pending)
  219 |         out = _engine(engine_frame, build, backend)
  220 |         observed = {int(f["bar_index"]): float(f["price"]) for f in out["fills"]
  221 |                     if f["reason"] in PROTECTIVE}
  222 |         if set(observed) == set(applied):
  223 |             return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
  224 |                                 np.asarray(out["positions"], float).reshape(-1),
  225 |                                 out["fills"], frame.index, True, sweeps,
  226 |                                 int(np.count_nonzero(build.entry_side)),
  227 |                                 len(build.unmapped_intents),
  228 |                                 {"protective_exits": len(observed)})
  229 |         forced = observed
  230 | 
  231 |     return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
  232 |                         np.asarray(out["positions"], float).reshape(-1),
  233 |                         out["fills"], frame.index, False, sweeps,
  234 |                         int(np.count_nonzero(build.entry_side)),
  235 |                         len(build.unmapped_intents),
  236 |                         {"unconverged_exit_symmetric_difference":
  237 |                              len(set(applied).symmetric_difference(
  238 |                                  {int(f["bar_index"]) for f in out["fills"]
  239 |                                   if f["reason"] in PROTECTIVE}))})
```

## SRC15 — `src/crypto_regime_lab/experiments/evaluator.py:246–326`

SHA-256: `b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5`

```text
  246 | def episode_bounds(index: pd.DatetimeIndex, episodes: int) -> list[tuple[str, int, int]]:
  247 |     """Contiguous inner episodes of EQUAL bar length (guide 7.3).
  248 | 
  249 |     Equal length is the point: the score may not mix long and short blocks, so a
  250 |     remainder is dropped from the front rather than making one block longer.
  251 |     """
  252 |     n = len(index)
  253 |     if episodes <= 0 or n < episodes * 2:
  254 |         raise EvaluationError(f"window of {n} bars cannot carry {episodes} inner episodes")
  255 |     size = n // episodes
  256 |     start0 = n - size * episodes
  257 |     return [(f"e{i}", start0 + i * size, start0 + (i + 1) * size) for i in range(episodes)]
  258 | 
  259 | 
  260 | def _drawdown(equity: np.ndarray) -> float:
  261 |     peak = np.maximum.accumulate(equity)
  262 |     with np.errstate(divide="ignore", invalid="ignore"):
  263 |         dd = np.where(peak > 0, (peak - equity) / peak, 0.0)
  264 |     return float(np.max(dd)) if dd.size else 0.0
  265 | 
  266 | 
  267 | def episode_metrics(run: CandidateRun, bounds: list[tuple[str, int, int]]) -> dict:
  268 |     """Utility and gate outcome per inner episode.
  269 | 
  270 |     U = (net return - lambda_dd * max drawdown) / risk unit, with net return taken
  271 |     against the frozen initial capital so every episode is measured against the
  272 |     same fixed risk allocation rather than a drifting equity base.
  273 |     """
  274 |     capital = ACCOUNT["initial_capital_usdt"]
  275 |     out: dict[str, dict] = {}
  276 |     for name, lo, hi in bounds:
  277 |         segment = run.equity[lo:hi]
  278 |         if segment.size < 2 or not np.isfinite(segment).all():
  279 |             raise EvaluationError(f"episode {name}: account trace is not finite")
  280 |         net_return = float(segment[-1] - segment[0]) / capital
  281 |         mdd = _drawdown(segment)
  282 |         utility = (net_return - UTILITY["drawdown_penalty"] * mdd) / UTILITY["risk_unit_fraction"]
  283 |         trades = sum(1 for f in run.fills if lo <= f["bar_index"] < hi)
  284 |         exposure = float(np.mean(np.abs(run.positions[lo:hi]) > 0.0))
  285 |         out[name] = {
  286 |             "utility": float(utility), "net_return": net_return, "max_drawdown": mdd,
  287 |             "trades": int(trades), "exposure": exposure,
  288 |             "gate_pass": bool(net_return > UTILITY["gate_min_return"]
  289 |                               and mdd <= UTILITY["gate_max_drawdown"]),
  290 |         }
  291 |     return out
  292 | 
  293 | 
  294 | def window_metrics(run: CandidateRun) -> dict:
  295 |     """Whole-window summary, used for deployment reporting rather than selection."""
  296 |     capital = ACCOUNT["initial_capital_usdt"]
  297 |     equity = run.equity
  298 |     net_return = float(equity[-1] - equity[0]) / capital
  299 |     steps = np.diff(equity) / capital
  300 |     sharpe = None
  301 |     if steps.size > 2 and float(np.std(steps)) > 0:
  302 |         sharpe = float(np.mean(steps) / np.std(steps) * np.sqrt(len(steps)))
  303 |     holding = []
  304 |     open_at = None
  305 |     for i, pos in enumerate(run.positions):
  306 |         if pos != 0.0 and open_at is None:
  307 |             open_at = i
  308 |         elif pos == 0.0 and open_at is not None:
  309 |             holding.append(i - open_at)
  310 |             open_at = None
  311 |     return {
  312 |         "net_return": net_return,
  313 |         "max_drawdown": _drawdown(equity),
  314 |         "sharpe_per_window": sharpe,
  315 |         "fills": len(run.fills),
  316 |         "entries": run.entries,
  317 |         "exposure": float(np.mean(np.abs(run.positions) > 0.0)),
  318 |         "mean_holding_bars": float(np.mean(holding)) if holding else None,
  319 |         "bars": int(equity.size),
  320 |         "converged": run.converged,
  321 |         "passes": run.passes,
  322 |         "unmapped_intents": run.unmapped_intents,
  323 |     }
  324 | 
  325 | 
  326 | def run_candidate_fixed_point_reference(alpha_id: str, params: dict, frame: pd.DataFrame, *,
```

## SRC16 — `src/crypto_regime_lab/experiments/calendar_baseline.py:142–210`

SHA-256: `f468f00abf37afe692f0f7650dff411d4a38e1f72e71c4e632b79e8c8ee8642d`

```text
  142 | # ---------------------------------------------------------------------------
  143 | 
  144 | @dataclass
  145 | class Evaluation:
  146 |     point_id: str
  147 |     params: dict
  148 |     origin: str
  149 |     status: str
  150 |     episodes: dict = field(default_factory=dict)
  151 |     window: dict = field(default_factory=dict)
  152 |     error: str | None = None
  153 | 
  154 |     @property
  155 |     def objective(self) -> float:
  156 |         """The in-sample aggregate arm A ranks on: the mean episode utility."""
  157 |         values = [e["utility"] for e in self.episodes.values()]
  158 |         return float(np.mean(values)) if values else float("-inf")
  159 | 
  160 | 
  161 | def _evaluate(alpha_id: str, params: dict, frame: pd.DataFrame, bounds, origin: str,
  162 |               schema: ParamSchema, backend: str) -> Evaluation:
  163 |     point_id = _point_id(params)
  164 |     feasible, reason = schema.is_feasible(params)
  165 |     if not feasible:
  166 |         return Evaluation(point_id, params, origin, ProbeStatus.STRUCTURALLY_INVALID,
  167 |                           error=reason)
  168 |     try:
  169 |         run = run_candidate(alpha_id, params, frame, backend=backend)
  170 |         episodes = episode_metrics(run, bounds)
  171 |         window = window_metrics(run)
  172 |     except EvaluationError as exc:
  173 |         return Evaluation(point_id, params, origin, ProbeStatus.RUNTIME_ERROR, error=str(exc))
  174 |     except Exception as exc:                      # a real failure, never a loss of 0
  175 |         return Evaluation(point_id, params, origin, ProbeStatus.RUNTIME_ERROR,
  176 |                           error=f"{type(exc).__name__}: {exc}")
  177 |     return Evaluation(point_id, params, origin, ProbeStatus.EVALUATED, episodes, window)
  178 | 
  179 | 
  180 | def _discover(alpha_id: str, schema: ParamSchema, frame: pd.DataFrame, bounds,
  181 |               budget: SearchBudget, seed: int, backend: str) -> list[Evaluation]:
  182 |     """TPE search on the training window only. It never sees the test window."""
  183 |     import logging
  184 | 
  185 |     import optuna
  186 | 
  187 |     optuna.logging.set_verbosity(optuna.logging.WARNING)
  188 |     logging.getLogger("optuna").setLevel(logging.WARNING)
  189 |     found: list[Evaluation] = []
  190 |     seen: set[str] = set()
  191 | 
  192 |     def objective(trial):
  193 |         point = suggest_point(trial, schema)
  194 |         pid = _point_id(point)
  195 |         if pid in seen:
  196 |             # A repeat costs no execution; it is reported, not counted as new evidence.
  197 |             prior = next(e for e in found if e.point_id == pid)
  198 |             return prior.objective if prior.status == ProbeStatus.EVALUATED else -1e9
  199 |         seen.add(pid)
  200 |         record = _evaluate(alpha_id, point, frame, bounds, "discovery", schema, backend)
  201 |         found.append(record)
  202 |         return record.objective if record.status == ProbeStatus.EVALUATED else -1e9
  203 | 
  204 |     study = optuna.create_study(direction="maximize",
  205 |                                 sampler=optuna.samplers.TPESampler(seed=seed))
  206 |     study.optimize(objective, n_trials=budget.discovery_trials, catch=(Exception,))
  207 |     return found
  208 | 
  209 | 
  210 | def run_cutoff(alpha_id: str, symbol: str, train: pd.DataFrame, fold: int,
```

## SRC17 — `src/crypto_regime_lab/experiments/calendar_baseline.py:351–409`

SHA-256: `f468f00abf37afe692f0f7650dff411d4a38e1f72e71c4e632b79e8c8ee8642d`

```text
  351 |         "local_coverage": _coverage(neighbourhoods, ok, calendar.inner_episodes),
  352 |         "evaluations": [
  353 |             {"point_id": pid, "origin": e.origin, "status": e.status,
  354 |              "objective": _finite(e.objective) if e.status == ProbeStatus.EVALUATED else None,
  355 |              "error": e.error}
  356 |             for pid, e in evaluated.items()
  357 |         ],
  358 |         "robust_scores": {pid: s for pid, s in scored["scores"].items()},
  359 |     }
  360 | 
  361 | 
  362 | def _select_with_installed(ok: dict[str, Evaluation]) -> dict:
  363 |     """Arm A. The decision is made by the installed function, not reimplemented."""
  364 |     from quantbt.walkforward import WalkForwardConfig, WalkForwardTrialRecord
  365 |     from quantbt.walkforward import _select_oos_candidate_record
  366 | 
  367 |     if not ok:
  368 |         return {"status": "NO_EVALUATION", "params": None,
  369 |                 "reason": "no candidate produced a valid evaluation"}
  370 |     order = sorted(ok)
  371 |     records = []
  372 |     for i, pid in enumerate(order):
  373 |         e = ok[pid]
  374 |         records.append(WalkForwardTrialRecord(
  375 |             trial_id=i, params=dict(e.params), objective=e.objective,
  376 |             mean_is_sharpe=e.objective, mean_oos_sharpe=0.0, mean_decay=0.0, std_decay=0.0,
  377 |             fold_metrics=[], pruned=False,
  378 |             selection_metadata={"stage": "is_search", "lab_point_id": pid,
  379 |                                 "oos_seen_by_optuna": False}))
  380 |     config = WalkForwardConfig()
  381 |     chosen = _select_oos_candidate_record(records, config)
  382 |     return {
  383 |         "status": "SELECTED",
  384 |         "selector": "quantbt.walkforward._select_oos_candidate_record",
  385 |         "candidate_selection_metric": config.candidate_selection_metric,
  386 |         "optimization_mode": config.optimization_mode,
  387 |         "rule": "max(records, key=objective) -- the public route's default",
  388 |         "point_id": chosen.selection_metadata.get("lab_point_id"),
  389 |         "params": dict(chosen.params),
  390 |         "objective": _finite(chosen.objective),
  391 |         "candidates_considered": len(records),
  392 |         "selection_metadata": {k: v for k, v in chosen.selection_metadata.items()
  393 |                                if isinstance(v, (str, int, float, bool, type(None)))},
  394 |     }
  395 | 
  396 | 
  397 | def _select_with_neighborhood(schema: ParamSchema, scored: dict, eligible: dict,
  398 |                               ok: dict[str, Evaluation]) -> dict:
  399 |     """Arm B. R = G - lambda_F*F over an independently designed local panel."""
  400 |     if not eligible:
  401 |         cause = _dominant_cause(scored["status_counts"])
  402 |         return {"status": f"NO_ADMISSIBLE_CANDIDATE:{cause}", "params": None,
  403 |                 "selector": "lab robust neighborhood",
  404 |                 "binding_constraint": cause,
  405 |                 "reason": "no candidate passed quality, survival and local-evidence gates; "
  406 |                           "the incumbent is retained rather than fabricating a plateau",
  407 |                 "status_counts": scored["status_counts"]}
  408 |     best_r = max(eligible, key=lambda pid: (scored["scores"][pid]["r"], -int(pid, 16)))
  409 |     rep = choose_representative(schema, eligible,
```

## SRC18 — `src/crypto_regime_lab/selector/alpha_schemas.py:35–85`

SHA-256: `933268e7b8d727016c74bec73811effc3a5f09fb4af3a816cd04cba83ff10b0b`

```text
   35 |         ParamSpec("AP", "int", 5, 60, 1),
   36 |         ParamSpec("alpha.condition_threshold", "int", 30, 80, 5),
   37 |         ParamSpec("novolumedata", "fixed", fixed_value=False),
   38 |         ParamSpec("src_col", "fixed", fixed_value="close"),
   39 |     ],
   40 |     name="A-SC",
   41 | )
   42 | 
   43 | A_HMA = ParamSchema.from_specs(
   44 |     [
   45 |         ParamSpec("min_length", "int", 40, 360, 10),
   46 |         ParamSpec("max_length", "int", 60, 420, 10),
   47 |         ParamSpec("minor_min", "int", 10, 120, 2),
   48 |         ParamSpec("minor_max", "int", 30, 220, 5),
   49 |         ParamSpec("flat", "float", 4.0, 50.0, 1.0),
   50 |         ParamSpec("atr_fast", "int", 4, 60, 2),
   51 |         ParamSpec("atr_slow", "int", 10, 140, 5),
   52 |         ParamSpec("mult", "float", 0.5, 6.0, 0.25),
   53 |         ParamSpec("max_sl", "float", 1.0, 9.0, 0.25),
   54 |         ParamSpec("take_profit", "float", 1.0, 8.0, 0.5),
   55 |         ParamSpec("min_profit", "float", 0.1, 4.0, 0.1),
   56 |         ParamSpec("sl_input", "categorical",
   57 |                   choices=("Half Distance Zone", "Zone Distance", "ATR")),
   58 |         ParamSpec("tick_size", "fixed", fixed_value=0.01),
   59 |     ],
   60 |     dependencies=(("min_length", "max_length"), ("minor_min", "minor_max"),
   61 |                   ("atr_fast", "atr_slow")),
   62 |     name="A-HMA",
   63 | )
   64 | 
   65 | A_VWAP = ParamSchema.from_specs(
   66 |     [
   67 |         ParamSpec("rsi_len", "int", 5, 80, 1),
   68 |         ParamSpec("rsi_os", "int", 10, 50, 1),
   69 |         ParamSpec("rsi_ob", "int", 55, 90, 1),
   70 |         ParamSpec("dev_mult", "float", 0.5, 5.0, 0.1),
   71 |         ParamSpec("atr_len", "int", 5, 90, 1),
   72 |         ParamSpec("stop_atr", "float", 1.0, 10.0, 0.1),
   73 |         ParamSpec("target_r", "float", 1.0, 10.0, 0.1),
   74 |         ParamSpec("htf_ema_len", "int", 20, 700, 10),
   75 |         ParamSpec("exit_at_vwap", "bool", choices=(False, True)),
   76 |         ParamSpec("time_stop_on", "bool", choices=(False, True)),
   77 |         # only meaningful when the time stop is on -> declared conditional
   78 |         ParamSpec("time_stop_bars", "int", 5, 120, 5, active_when=("time_stop_on", True)),
   79 |         ParamSpec("htf_tf", "fixed", fixed_value="1h"),
   80 |     ],
   81 |     dependencies=(("rsi_os", "rsi_ob"),),
   82 |     name="A-VWAP",
   83 | )
   84 | 
   85 | A_HASH = ParamSchema.from_specs(
```

## SRC19 — `src/crypto_regime_lab/alphas/a_hma.py:26–40`

SHA-256: `dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca`

```text
   26 | from .contracts import (
   27 |     BarDecision, ExecutionPhase, Fill, IntentKind, OrderIntent, QuantityBasis,
   28 | )
   29 | from .reference import indicators as ref
   30 | 
   31 | ADAPT_PCT = 0.03141
   32 | SL_MODES = {"One Distance Zone": 0, "Half Distance Zone": 1, "Last High/Low": 2, "ATR Only": 3}
   33 | IGNORED_KNOBS = ("sl_mult", "double_up", "time_ms", "volume")
   34 | 
   35 | 
   36 | class InfeasibleConfiguration(ValueError):
   37 |     """Raised for a configuration the adapter refuses to run (SD-HMA-05)."""
   38 | 
   39 | 
   40 | @dataclass
```

## SRC20 — `src/crypto_regime_lab/alphas/a_hma.py:248–272`

SHA-256: `dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca`

```text
  248 |                                target_after_close=target, diagnostics=diagnostics)
  249 | 
  250 |         tick = float(self.params["tick_size"])
  251 |         pip_size = tick * 10.0                                  # SD-HMA-04
  252 |         sl_low_max = m.low[t] - float(self.params["max_sl"]) * f.atr_base[t]
  253 |         sl_high_max = m.high[t] + float(self.params["max_sl"]) * f.atr_base[t]
  254 |         lo = t - 47 if t >= 47 else 0
  255 |         hh48 = float(np.max(m.high[lo:t + 1]))
  256 |         ll48 = float(np.min(m.low[lo:t + 1]))
  257 |         last_high = hh48 + 5.0 * pip_size
  258 |         last_low = ll48 - 5.0 * pip_size
  259 | 
  260 |         mode = SL_MODES.get(self.params.get("sl_input", "Half Distance Zone"), 1)
  261 |         sl_buy_raw, sl_sell_raw = {
  262 |             0: (bot_tl, top_tl),
  263 |             1: (lower_tl, upper_tl),
  264 |             2: (last_low, last_high),
  265 |         }.get(mode, (sl_low_max, sl_high_max))
  266 | 
  267 |         buy = (up_sig and not up_prev and m.close[t] > f.dynamic_hma[t]
  268 |                and m.low[t] <= upper_tl and 51.0 < f.rsi[t] <= 70.0)
  269 |         sell = (dn_sig and not dn_prev and m.close[t] < f.dynamic_hma[t]
  270 |                 and m.high[t] >= lower_tl and 30.0 <= f.rsi[t] < 49.0)
  271 |         mid = (m.high[t] + m.low[t]) / 2.0
  272 |         over_buy = (up_sig and not up_prev and f.rsi[t] > 70.0 and m.close[t] > f.dynamic_hma[t]
```

## SRC21 — `src/crypto_regime_lab/alphas/a_hma.py:315–352`

SHA-256: `dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca`

```text
  315 |         return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
  316 |                            intents=intents, diagnostics=diagnostics)
  317 | 
  318 |     # -- fills ------------------------------------------------------------
  319 | 
  320 |     def _levels_from_fill(self, fill: Fill) -> list[OrderIntent]:
  321 |         """Validate the staged bracket against the ACTUAL fill (finding HM-03)."""
  322 |         staged = getattr(self, "_staged", None)
  323 |         if staged is None:
  324 |             return []
  325 |         stop_level = staged["stop_level"]
  326 |         tp_level = staged["tp_level"]
  327 |         side = staged["side"]
  328 |         wrong_side = (side > 0 and (stop_level >= fill.price or tp_level <= fill.price)) or \
  329 |                      (side < 0 and (stop_level <= fill.price or tp_level >= fill.price))
  330 |         if wrong_side:
  331 |             if self.gap_policy == "reject":
  332 |                 self.state.pending_exit = True
  333 |                 return [OrderIntent(
  334 |                     kind=IntentKind.EXIT_ALL, decision_index=fill.index,
  335 |                     earliest_phase=ExecutionPhase.NEXT_OPEN,
  336 |                     reason="bracket_invalid_after_gap",
  337 |                     metadata={"policy": "reject", "fill_price": fill.price,
  338 |                               "stop_level": stop_level, "tp_level": tp_level,
  339 |                               "note": "a gap put a protective level on the wrong side of the fill; "
  340 |                                       "the position is closed rather than booked as instant profit"})]
  341 |             distance_stop = abs(staged["stop_level"] - self.market.close[staged["decision_index"]])
  342 |             distance_tp = abs(staged["tp_level"] - self.market.close[staged["decision_index"]])
  343 |             stop_level = fill.price - side * distance_stop
  344 |             tp_level = fill.price + side * distance_tp
  345 |         self.state.stop_price = stop_level
  346 |         self.state.take_profit_price = tp_level
  347 |         return [OrderIntent(
  348 |             kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
  349 |             earliest_phase=ExecutionPhase.RESTING_INTRABAR, reason="bracket_from_actual_fill",
  350 |             stop_price=stop_level, take_profit_price=tp_level,
  351 |             metadata={"fill_price": fill.price, "gap_policy": self.gap_policy,
  352 |                       "normalized": bool(wrong_side and self.gap_policy == "normalize")})]
```

## SRC22 — `src/crypto_regime_lab/alphas/a_vwap.py:201–233`

SHA-256: `242facf154f4505ab862ac6815ee497d0e9c6e3ee70bbdb8b6cb1895a2900b77`

```text
  201 | 
  202 |         # ---- open position: only the TIME stop is a close decision ----
  203 |         # The stop and the take profit are resting orders working in the engine;
  204 |         # the adapter never books them itself (finding AV-02).
  205 |         if entering != 0.0:
  206 |             bars_held = t - (self.state.entry_index if self.state.entry_index is not None else t)
  207 |             time_stop_due = bool(self.params["time_stop_on"]) and \
  208 |                 bars_held >= int(self.params["time_stop_bars"])
  209 |             diagnostics["bars_held"] = bars_held
  210 |             diagnostics["time_stop_due"] = time_stop_due
  211 |             if time_stop_due and not self.state.pending_exit:
  212 |                 self.state.pending_exit = True
  213 |                 target = 0.0
  214 |                 intents.append(OrderIntent(
  215 |                     kind=IntentKind.EXIT_ALL, decision_index=t,
  216 |                     earliest_phase=ExecutionPhase.NEXT_OPEN, reason="time_stop",
  217 |                     metadata={"exit_reason": "time_stop", "bars_held": bars_held,
  218 |                               "precedence": list(EXIT_PRECEDENCE),
  219 |                               "note": "submitted at the close; a resting stop or take profit that "
  220 |                                       "triggered intrabar takes precedence"}))
  221 |             if bool(self.params["exit_at_vwap"]) and not self.state.pending_exit:
  222 |                 # SD-VWAP-04: rest at the PREVIOUS bar's observed VWAP, never this bar's.
  223 |                 intents.append(OrderIntent(
  224 |                     kind=IntentKind.AMEND_PROTECTION, decision_index=t,
  225 |                     earliest_phase=ExecutionPhase.RESTING_INTRABAR,
  226 |                     reason="dynamic_vwap_resting_previous_observed",
  227 |                     price=float(f.vwap[t]),
  228 |                     metadata={"effective_from_bar": t + 1,
  229 |                               "variant": "resting_previous_observed_vwap"}))
  230 |             return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
  231 |                                intents=intents, diagnostics=diagnostics)
  232 | 
  233 |         if self.state.pending_entry_side:
```

## SRC23 — `scripts/close_lab01_blockers.py:52–94`

SHA-256: `45f98643f03b22cb0c3d2247c0b27785d7d3f36d6c3683509cbc808b7c06199d`

```text
   52 |     qualification = json.loads((configs / "market_qualification.json").read_text())
   53 |     per_alpha_turnover = {}
   54 |     for record in qualification["results"]:
   55 |         if record["status"] != "QUALIFIED":
   56 |             continue
   57 |         interval = DECISION_INTERVAL[record["alpha_id"]]
   58 |         bars_per_day = {"15min": 96, "1h": 24, "4h": 6}[interval]
   59 |         days = record["bars"] / bars_per_day
   60 |         entries = record["checks"]["entries"]
   61 |         per_alpha_turnover.setdefault(record["alpha_id"], []).append(entries / days if days else 0.0)
   62 | 
   63 |     round_trips_per_day = {a: sum(v) / len(v) for a, v in per_alpha_turnover.items()}
   64 |     busiest = max(round_trips_per_day.values()) if round_trips_per_day else 0.0
   65 |     round_trip_cost = 2.0 * (TAKER_FEE + SLIPPAGE)
   66 |     stress_span = round_trip_cost * (max(COST_STRESS) - min(COST_STRESS))
   67 |     minimum_daily_effect = stress_span * busiest
   68 | 
   69 |     effect = {
   70 |         "schema": "crypto_regime_lab.minimum_economic_effect.v1",
   71 |         "registered_at_utc": utc_now_iso(),
   72 |         "registered_before_any_arm_comparison": True,
   73 |         "definition": "the smallest mean daily net-return difference the lab will call economically "
   74 |                       "meaningful for the primary endpoint",
   75 |         "derivation": {
   76 |             "taker_fee": TAKER_FEE,
   77 |             "slippage": SLIPPAGE,
   78 |             "round_trip_cost": round_trip_cost,
   79 |             "cost_stress_multipliers": list(COST_STRESS),
   80 |             "cost_uncertainty_per_round_trip": stress_span,
   81 |             "round_trips_per_day_by_alpha": round_trips_per_day,
   82 |             "busiest_alpha_round_trips_per_day": busiest,
   83 |             "formula": "cost_uncertainty_per_round_trip * busiest_round_trips_per_day",
   84 |         },
   85 |         "minimum_daily_net_return_difference": minimum_daily_effect,
   86 |         "minimum_daily_net_return_bps": minimum_daily_effect * 1e4,
   87 |         "rule": (
   88 |             "an improvement smaller than this sits inside the registered cost-stress band and is "
   89 |             "reported as inconclusive, not as an edge. The threshold is fixed now, before any arm "
   90 |             "has been compared, so it can never be chosen to fit an observed delta (guide 11.2)."
   91 |         ),
   92 |         "turnover_source": "market qualification on development slices; a smoke measurement, not a "
   93 |                            "performance claim",
   94 |     }
```

## SRC24 — `scripts/fit_regime_model.py:140–220`

SHA-256: `3057737f342d9f11cf237d4a3a300c2ef69b43b84cf68d468f331077759339ae`

```text
  140 |     ROLE = args.role
  141 |     ARTIFACT_PREFIX = args.artifact_prefix or (
  142 |         "lab05" if SYMBOL == "BTCUSDT" else f"lab08_{SYMBOL.lower()}")
  143 |     if ROLE != "development":
  144 |         unlock = LAB_ROOT / "configs" / "lab09_confirmation_spec.json"
  145 |         if not unlock.is_file():
  146 |             print(f"BLOCKED: role={ROLE} needs the L09.1 unlock "
  147 |                   "(scripts/unlock_lab09_confirmation.py) to exist first")
  148 |             return 1
  149 |     policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
  150 |     policy.assert_lab_root_ok()
  151 |     policy.assert_lab_marker_ok(STUDY_ID)
  152 |     writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
  153 | 
  154 |     frame, features, weights, schema = load_panel(policy)
  155 |     role = ROLES[ROLE]
  156 |     role_end = role["end"] or str(pd.Timestamp(frame["time"].max()).date())
  157 |     # `development` is the FITTING scope: every training window is cut from it. It
  158 |     # reaches back before the role starts because a trailing memory has to come from
  159 |     # somewhere; the emission loop below starts at the first cutoff, so nothing is
  160 |     # ever emitted before the role begins.
  161 |     development = frame[frame["time"] <= role_end].reset_index(drop=True)
  162 |     cutoffs = fit_cutoffs(DEVELOPMENT_START, role_end, TRAIN_MEMORY_DAYS,
  163 |                           FIT_CADENCE_DAYS, first_cutoff=role["first_cutoff"])
  164 |     groups: dict[str, list[int]] = {}
  165 |     for i, name in enumerate(features):
  166 |         groups.setdefault(name.split("_")[0].upper(), []).append(i)
  167 | 
  168 |     with writer.attempt("L05.4.choose_k") as att:
  169 |         # K is chosen on the FIRST cutoff's training window only, then frozen for
  170 |         # every later refit: re-choosing K at each refit would be selecting model
  171 |         # complexity repeatedly against overlapping data.
  172 |         first_cut = pd.Timestamp(cutoffs[0])
  173 |         first_train = development[(development["time"] < first_cut)
  174 |                                   & (development["time"] >= first_cut
  175 |                                      - pd.Timedelta(days=TRAIN_MEMORY_DAYS))]
  176 |         raw_first = first_train[features].to_numpy(float)
  177 |         scaler_first = C.fit_scaler(raw_first)
  178 |         z_first = C.apply_scaler(raw_first, scaler_first)
  179 |         k_choice = MS.choose_k(z_first, weights, lambda_jump=LAMBDA_JUMP, seeds=SEEDS,
  180 |                                candidates=(MS.PARSIMONIOUS_K, MS.STARTING_K))
  181 |         att.detail = {"best": k_choice["best_by_inner_criterion"]}
  182 |     # The registered starting K is 3. The inner criterion is REPORTED; it does not
  183 |     # silently override a registered choice (guide 8.1).
  184 |     n_states = MS.STARTING_K
  185 |     k_choice["registered_k_used"] = n_states
  186 |     k_choice["inner_criterion_agrees_with_registered"] = (
  187 |         k_choice["best_by_inner_criterion"] == n_states)
  188 |     k_choice["override_policy"] = (
  189 |         "the registered starting K=3 is used and the disagreement is reported rather than acted "
  190 |         "on. This is a JUDGEMENT CALL and the guide can be read both ways: 8.1 calls K=3 the "
  191 |         "'primary starting' K with K=2 a registered 'parsimonious alternative', while 8.3 says K "
  192 |         "is chosen in nested development -- which is exactly the criterion that preferred K=2 "
  193 |         "here. The lab keeps the registered starting point because switching after seeing a "
  194 |         "score, even a nested-development score, is still choosing the model on a result; but the "
  195 |         "margin is small and the decision belongs to the user, so it is recorded in "
  196 |         "reports/improvement_opinions.md rather than settled silently.")
  197 |     scores = {int(k): v["mean_per_observation_objective"] for k, v in k_choice["scores"].items()}
  198 |     if len(scores) > 1:
  199 |         best, second = sorted(scores.values())[:2]
  200 |         k_choice["margin_between_top_two"] = float(second - best)
  201 |         k_choice["relative_margin"] = float((second - best) / abs(second)) if second else None
  202 |     k_choice["direction_note"] = (
  203 |         "the usual worry is that a larger K fits better almost by construction. Here the SMALLER "
  204 |         "K scored better, which is the opposite direction and is why the standard warning does "
  205 |         "not settle this case.")
  206 |     writer.write_config(f"{ARTIFACT_PREFIX}_k_selection.json", k_choice)
  207 | 
  208 |     artifacts, mappings, transitions = [], [], []
  209 |     previous: R.ModelArtifact | None = None
  210 |     all_reports = {}
  211 | 
  212 |     for cutoff in cutoffs:
  213 |         cut = pd.Timestamp(cutoff)
  214 |         window = development[(development["time"] < cut)
  215 |                              & (development["time"] >= cut - pd.Timedelta(days=TRAIN_MEMORY_DAYS))]
  216 |         raw = window[features].to_numpy(float)
  217 |         with writer.attempt(f"L05.1.fit@{cutoff}") as att:
  218 |             scaler = C.fit_scaler(raw)
  219 |             z_train = C.apply_scaler(raw, scaler)
  220 |             fit = multi_start_fit(z_train, weights, n_states=n_states,
```

## SRC25 — `src/crypto_regime_lab/regime/registry.py:140–225`

SHA-256: `432a33230cba5fd271af9f0e06ba4141105893bdc5934cbf98863d07827a3ad6`

```text
  140 | # ---------------------------------------------------------------------------
  141 | # namespace mapping across a refit
  142 | # ---------------------------------------------------------------------------
  143 | 
  144 | def map_state_namespaces(old: ModelArtifact, new: ModelArtifact, *,
  145 |                          max_relative_distance: float = MAPPING_MAX_RELATIVE_DISTANCE) -> dict:
  146 |     """Map new-model states onto old-model states using TRAINING centroids only.
  147 | 
  148 |     No emission, no outcome and no market data after either cutoff enters this. A
  149 |     state that cannot be matched confidently is ``UNMAPPED_REFIT_STATE`` -- a model
  150 |     event, explicitly NOT a market transition and explicitly not a retrain trigger.
  151 |     """
  152 |     if tuple(old.feature_names) != tuple(new.feature_names):
  153 |         raise JumpModelError("cannot map namespaces across different feature schemas")
  154 |     old_c = np.asarray(old.centroids, dtype=np.float64)
  155 |     new_c = np.asarray(new.centroids, dtype=np.float64)
  156 |     weights = np.asarray(new.feature_weights, dtype=np.float64)
  157 | 
  158 |     def _distance(a, b):
  159 |         d = a - b
  160 |         return float(np.sqrt(np.sum(weights * d * d)))
  161 | 
  162 |     # scale by how far apart the OLD model's own states are: a "close" match must be
  163 |     # close relative to the structure the model itself resolves
  164 |     spread = [
  165 |         _distance(old_c[i], old_c[j])
  166 |         for i in range(old_c.shape[0]) for j in range(i + 1, old_c.shape[0])
  167 |     ]
  168 |     reference = float(np.median(spread)) if spread else 1.0
  169 |     if reference <= 0:
  170 |         reference = 1.0
  171 | 
  172 |     mapping = {}
  173 |     for k in range(new_c.shape[0]):
  174 |         distances = np.asarray([_distance(new_c[k], old_c[j]) for j in range(old_c.shape[0])])
  175 |         order = np.argsort(distances, kind="stable")
  176 |         best = int(order[0])
  177 |         best_d = float(distances[best])
  178 |         runner_up = float(distances[order[1]]) if distances.size > 1 else float("inf")
  179 |         relative = best_d / reference
  180 |         if relative > max_relative_distance:
  181 |             status = MAPPING_UNMAPPED
  182 |         elif runner_up < float("inf") and best_d > 0 and runner_up / max(best_d, 1e-12) < 1.25:
  183 |             status = MAPPING_AMBIGUOUS
  184 |         else:
  185 |             status = MAPPING_CONFIDENT
  186 |         mapping[str(k)] = {
  187 |             "new_state": k,
  188 |             "old_state": best if status == MAPPING_CONFIDENT else None,
  189 |             "status": status,
  190 |             "distance": best_d,
  191 |             "relative_distance": relative,
  192 |             "runner_up_distance": runner_up,
  193 |         }
  194 | 
  195 |     unmapped = [k for k, v in mapping.items() if v["status"] != MAPPING_CONFIDENT]
  196 |     return {
  197 |         "schema": "crypto_regime_lab.state_namespace_mapping.v1",
  198 |         "old_namespace": old.state_namespace, "new_namespace": new.state_namespace,
  199 |         "old_centroid_digest": old.centroid_digest(),
  200 |         "new_centroid_digest": new.centroid_digest(),
  201 |         "reference_spread": reference,
  202 |         "max_relative_distance": max_relative_distance,
  203 |         "mapping": mapping,
  204 |         "unmapped_states": unmapped,
  205 |         "all_states_mapped": not unmapped,
  206 |         "information_used": "training centroids and declared feature weights only",
  207 |         "is_market_transition": False,
  208 |         "triggers_parameter_search": False,
  209 |         "rule": ("a permuted or unmatched state ID after a refit is a MODEL event. It is emitted "
  210 |                  "as a model-transition/uncertainty record and never as a market regime change, "
  211 |                  "and it never triggers a parameter search or a market refit (guide 8.4)"),
  212 |     }
  213 | 
  214 | 
  215 | def relabel_states(states: np.ndarray, mapping: dict) -> np.ndarray:
  216 |     """Translate new-namespace states into old-namespace IDs; -1 where unmapped.
  217 | 
  218 |     -1 is deliberate: an unmapped state must be visibly absent rather than being
  219 |     folded into whichever old state happened to be nearest.
  220 |     """
  221 |     states = np.asarray(states, dtype=np.int64)
  222 |     lookup = {int(k): (v["old_state"] if v["status"] == MAPPING_CONFIDENT else -1)
  223 |               for k, v in mapping["mapping"].items()}
  224 |     return np.asarray([lookup.get(int(s), -1) for s in states], dtype=np.int64)
  225 | 
```

## SRC26 — `src/crypto_regime_lab/regime/ablation.py:1–199`

SHA-256: `5d7094c6be54a67b30f6056d9c15b2654cad4116e73b57730cbff2d5f9554e46`

```text
    1 | """Guide 8.3 — group ablation and the position taken on the model ladder.
    2 | 
    3 | Two separate obligations live here.
    4 | 
    5 | **Group ablation.** Guide 8.3: "Group ablation cần chứng minh leverage/flow/market
    6 | features có contribution ngoài price/volatility." Adding feature blocks almost
    7 | always lowers a fit objective, so the question is not whether the objective drops
    8 | but whether it drops on data the fit did not see. The comparison therefore runs on
    9 | the same nested inner blocks that choose K, never on a holdout.
   10 | 
   11 | **The model ladder.** Guide 8.1 defines five rungs. LAB-05's task list asks for M0
   12 | and M1 only. Not building M1S, M2 and M3 is a defensible reading, but leaving that
   13 | undeclared is not -- a reader would have no way to tell a deliberate scope from an
   14 | oversight. The decision, and what would have to be true to revisit it, is recorded.
   15 | """
   16 | 
   17 | from __future__ import annotations
   18 | 
   19 | import numpy as np
   20 | 
   21 | from .model_selection import score_k
   22 | 
   23 | #: Guide 8.1. ``implemented`` is a fact about this repository, not an opinion.
   24 | MODEL_LADDER = {
   25 |     "M0": {
   26 |         "model": "rule-based volatility/path-direction/activity",
   27 |         "role": "explainable control, thresholds train-only",
   28 |         "implemented": True, "module": "regime/m0_rules.py",
   29 |     },
   30 |     "M1": {
   31 |         "model": "regularized discrete statistical jump model",
   32 |         "role": "primary state model",
   33 |         "implemented": True, "module": "regime/jump_model.py",
   34 |     },
   35 |     "M1S": {
   36 |         "model": "sparse JM or group-regularized features",
   37 |         "role": "extension when there are MANY blocks; ablation against M1",
   38 |         "implemented": False,
   39 |         "why_not": (
   40 |             "the primary core is 8 features in 3 blocks (G1 3, G2 2, G5 3). Guide 8.1 scopes M1S "
   41 |             "to 'khi nhiều blocks', and 3 is not that. Guide 8.3 also forbids writing a naive "
   42 |             "sparse objective and requires a pinned research implementation or a verified "
   43 |             "constrained one; none is pinned in this environment, so writing one would be exactly "
   44 |             "the move 8.3 warns against."),
   45 |         "what_would_change_it": (
   46 |             "G3 (leverage) and G4 (liquidity) becoming available for all five symbols would take "
   47 |             "the core past 3 blocks. Then M1S needs a pinned implementation with its weight "
   48 |             "normalisation and penalty conventions recorded, plus the nondegeneracy guard that "
   49 |             "already exists in quality.check_degeneracy."),
   50 |     },
   51 |     "M2": {
   52 |         "model": "small HMM or GMM",
   53 |         "role": "comparator; guide 8.1 says do NOT sweep every model family",
   54 |         "implemented": False,
   55 |         "why_not": ("LAB-05's task list (L05.2) asks for M0 and M1 references. M2 is a comparator "
   56 |                     "the guide explicitly declines to make mandatory, and adding it would widen "
   57 |                     "the model family sweep 8.1 warns against."),
   58 |         "what_would_change_it": ("a claim that the state structure is specific to a jump model "
   59 |                                  "rather than to the features would need M2 to be falsifiable."),
   60 |     },
   61 |     "M3": {
   62 |         "model": "online novelty/change detector",
   63 |         "role": "diagnostic/secondary trigger, explicitly not wired in by default",
   64 |         "implemented": False,
   65 |         "why_not": ("guide 8.1 marks it 'chưa ghép default'. The novelty AXIS it would feed is "
   66 |                     "already measured -- fit residual against the training-residual quantile in "
   67 |                     "quality.assess -- without introducing a second detector whose disagreements "
   68 |                     "with M1 would then need their own policy."),
   69 |         "what_would_change_it": "a decision to use novelty as a trigger rather than as a status.",
   70 |     },
   71 | }
   72 | 
   73 | 
   74 | def ladder_record() -> dict:
   75 |     implemented = [k for k, v in MODEL_LADDER.items() if v["implemented"]]
   76 |     return {
   77 |         "schema": "crypto_regime_lab.model_ladder.v1",
   78 |         "rungs": MODEL_LADDER,
   79 |         "implemented": implemented,
   80 |         "not_implemented": [k for k, v in MODEL_LADDER.items() if not v["implemented"]],
   81 |         "scope_rule": ("LAB-05 L05.2 asks for M0 and M1 references. The other rungs are declared "
   82 |                        "unbuilt with a reason and a condition that would reopen them, so an "
   83 |                        "omission cannot be mistaken for an oversight (guide 8.1)"),
   84 |         "k_policy": "primary K=3; K=2 parsimonious; K=4 only on an explicit discovery decision",
   85 |     }
   86 | 
   87 | 
   88 | def group_weights(all_features: tuple[str, ...], weights: np.ndarray,
   89 |                   keep_groups: tuple[str, ...]) -> np.ndarray:
   90 |     """Zero the excluded blocks and renormalise so total weight stays 1.
   91 | 
   92 |     Renormalising matters: without it a smaller feature set simply has less total
   93 |     weight and a lower loss, and the ablation would measure the normalisation
   94 |     rather than the information.
   95 |     """
   96 |     weights = np.asarray(weights, dtype=np.float64)
   97 |     mask = np.asarray([f.split("_")[0].upper() in keep_groups for f in all_features])
   98 |     restricted = np.where(mask, weights, 0.0)
   99 |     total = restricted.sum()
  100 |     if total <= 0:
  101 |         raise ValueError(f"keeping {keep_groups} leaves no weight at all")
  102 |     return restricted / total
  103 | 
  104 | 
  105 | def variance_resolved(z_block: np.ndarray, centroids: np.ndarray, states: np.ndarray,
  106 |                       weights: np.ndarray) -> float:
  107 |     """Share of weighted variance the state assignment removes, on a held-out block.
  108 | 
  109 |     This exists because the fit objective is NOT comparable across feature sets: a
  110 |     different feature set is a different objective function, and a larger number
  111 |     could mean "worse states" or simply "noisier features". This measure is
  112 |     scale-free -- within-state weighted variance over total weighted variance,
  113 |     subtracted from one -- so the same number means the same thing whether the
  114 |     model reads 3 features or 8.
  115 |     """
  116 |     z_block = np.asarray(z_block, dtype=np.float64)
  117 |     weights = np.asarray(weights, dtype=np.float64)
  118 |     grand = np.average(z_block, axis=0, weights=None)
  119 |     total = float(np.sum(weights * np.mean((z_block - grand) ** 2, axis=0)))
  120 |     if total <= 0:
  121 |         return 0.0
  122 |     residual = z_block - np.asarray(centroids, dtype=np.float64)[states]
  123 |     within = float(np.sum(weights * np.mean(residual ** 2, axis=0)))
  124 |     return 1.0 - within / total
  125 | 
  126 | 
  127 | def group_ablation(z: np.ndarray, all_features: tuple[str, ...], weights: np.ndarray, *,
  128 |                    n_states: int, lambda_jump: float, seeds: tuple[int, ...],
  129 |                    ladder: tuple[tuple[str, ...], ...] = (("G1",), ("G1", "G2"),
  130 |                                                           ("G1", "G2", "G5")),
  131 |                    n_folds: int = 3) -> dict:
  132 |     """Does each added block buy anything on data the fit did not see?
  133 | 
  134 |     Scored on the held-out inner blocks, so a block that only helps in-sample --
  135 |     which every block does -- shows no gain here.
  136 |     """
  137 |     from .jump_model import forward_filter, loss_matrix, multi_start_fit
  138 |     from .model_selection import inner_splits
  139 | 
  140 |     rows = []
  141 |     previous_objective = None
  142 |     previous_resolved = None
  143 |     for keep in ladder:
  144 |         restricted = group_weights(all_features, weights, keep)
  145 |         score = score_k(z, restricted, n_states=n_states, lambda_jump=lambda_jump,
  146 |                         seeds=seeds, n_folds=n_folds)
  147 | 
  148 |         # the scale-free measure, on the same held-out inner blocks
  149 |         resolved = []
  150 |         for train_end, valid_start, valid_end in inner_splits(z.shape[0], n_folds):
  151 |             fit = multi_start_fit(z[:train_end], restricted, n_states=n_states,
  152 |                                   lambda_jump=lambda_jump, seeds=seeds)
  153 |             block = z[valid_start:valid_end]
  154 |             states = forward_filter(loss_matrix(block, fit["centroids"], restricted),
  155 |                                     lambda_jump).online_states
  156 |             resolved.append(variance_resolved(block, fit["centroids"], states, restricted))
  157 |         mean_resolved = float(np.mean(resolved))
  158 | 
  159 |         gain = (None if previous_objective is None
  160 |                 else previous_objective - score["mean_per_observation_objective"])
  161 |         resolved_gain = (None if previous_resolved is None
  162 |                          else mean_resolved - previous_resolved)
  163 |         rows.append({
  164 |             "groups": list(keep),
  165 |             "features_active": int(np.count_nonzero(restricted)),
  166 |             "mean_per_observation_objective": score["mean_per_observation_objective"],
  167 |             "worst_fold": score["worst_fold"],
  168 |             "variance_resolved_out_of_fold": mean_resolved,
  169 |             "gain_over_previous": gain,
  170 |             "variance_resolved_gain": resolved_gain,
  171 |             "improved": None if resolved_gain is None else bool(resolved_gain > 0),
  172 |             "improved_on_objective": None if gain is None else bool(gain > 0),
  173 |         })
  174 |         previous_objective = score["mean_per_observation_objective"]
  175 |         previous_resolved = mean_resolved
  176 | 
  177 |     added = [r for r in rows if r["variance_resolved_gain"] is not None]
  178 |     return {
  179 |         "schema": "crypto_regime_lab.group_ablation.v1",
  180 |         "ladder": rows,
  181 |         "blocks_that_improved_out_of_fold": [r["groups"][-1] for r in added if r["improved"]],
  182 |         "blocks_that_did_not": [r["groups"][-1] for r in added if not r["improved"]],
  183 |         "scored_on": "held-out inner chronological blocks of the development window",
  184 |         "holdout_used": False,
  185 |         "weights_renormalised": True,
  186 |         "decided_on": "variance_resolved_out_of_fold",
  187 |         "why_not_the_objective": (
  188 |             "a different feature set is a DIFFERENT objective function, so its value is not "
  189 |             "comparable across rows -- a higher number can mean worse states or simply noisier "
  190 |             "features. variance_resolved is within-state over total weighted variance subtracted "
  191 |             "from one, which means the same thing at 3 features and at 8. The objective column is "
  192 |             "kept for reference and is not what the verdict rests on"),
  193 |         "requirement": ("guide 8.3: flow and market-coordination blocks must be shown to "
  194 |                         "contribute BEYOND price/volatility. A block that does not is reported as "
  195 |                         "not contributing, not quietly retained"),
  196 |         "interpretation_limit": ("this measures contribution to the FIT objective out of fold. It "
  197 |                                  "says nothing about whether the extra block improves a trading "
  198 |                                  "decision, which is a LAB-06+ question"),
  199 |     }
```

## SRC27 — `scripts/analyse_lab09_confirmation.py:860–991`

SHA-256: `949c322271bfd18290a60c01a6cb6bf14d8cb155b5e2f840fe8db73e5a7fbc51`

```text
  860 |           minimum_effect: float, vocabulary: list[str],
  861 |           accounting: dict | None = None) -> dict:
  862 |     def contrast(name: str) -> dict:
  863 |         return uncertainty["contrasts"].get(name, {})
  864 | 
  865 |     def verdict(name: str, question: str, reading: str) -> dict:
  866 |         record = contrast(name)
  867 |         if record.get("status") != "OK":
  868 |             # NOT_MEASURED needs a REASON, or it reads like a negative result.
  869 |             # Every contribution that cannot be judged says why it cannot be.
  870 |             return {"contrast": name, "question": question, "status": record.get("status"),
  871 |                     "verdict": "NOT_MEASURED",
  872 |                     "reason": record.get("reason")
  873 |                     or f"the {name} contrast produced no interval ({record.get('status')})",
  874 |                     "where": "configs/lab09_uncertainty.json contrasts"}
  875 |         # three outcomes, not two. An interval that straddles the minimum has not
  876 |         # ruled the effect out; calling that NOT_SUPPORTED reads as a negative
  877 |         # result when the honest answer is that the sample cannot tell.
  878 |         clears = record["ci_lower"] > minimum_effect
  879 |         ruled_out = record["ci_upper"] < minimum_effect
  880 |         return {
  881 |             "contrast": name, "question": question,
  882 |             "baseline_is_not_untouched": record.get("baseline_is_not_untouched", False),
  883 |             "baseline_caveat": record.get("baseline_caveat"),
  884 |             "point_estimate": record["point_estimate"],
  885 |             "ci": [record["ci_lower"], record["ci_upper"]],
  886 |             "holm_adjusted_p": record.get("holm_adjusted_p"),
  887 |             "minimum_economic_effect": minimum_effect,
  888 |             "clears_minimum_effect": bool(clears),
  889 |             "ruled_out_below_the_minimum": bool(ruled_out),
  890 |             "verdict": ("SUPPORTED" if clears
  891 |                         else "RULED_OUT" if ruled_out else "INCONCLUSIVE"),
  892 |             "reading": reading,
  893 |         }
  894 | 
  895 |     contributions = {
  896 |         "DESCRIPTIVE": descriptive_contribution(),
  897 |         "PREDICTIVE": predictive_contribution(support),
  898 |         "SELECTION": verdict("B-A", "does the neighbourhood selector beat the installed one on "
  899 |                                     "the same calendar?",
  900 |                              "this is the WHICH-parameters contribution, holding timing fixed"),
  901 |         "TIMING": verdict("C-A", "does regime-triggered refresh beat the frozen calendar with "
  902 |                                  "the same selector?",
  903 |                           "this is the WHEN contribution, holding the selector fixed. A "
  904 |                           "time-edge claim rests here and nowhere else"),
  905 |         "POLICY": {
  906 |             "question": "does the bank and response policy add anything beyond D?",
  907 |             "evidence": "arm E deployed arm D's schedule; its own contribution is null by "
  908 |                         "construction wherever LAB-06 measured zero switches",
  909 |             "verdict": "NULL_BY_CONSTRUCTION",
  910 |             "where": "configs/lab09_confirmation_results.json arms.E",
  911 |         },
  912 |     }
  913 | 
  914 |     blockers = []
  915 |     if reconciliation["financial_identity"].get("cost_binding_is_a_finding"):
  916 |         blockers.append(
  917 |             "ACCOUNTING: the lab charged half the registered one-way taker fee in every phase, "
  918 |             "because the registered ONE-WAY rate was passed into an engine parameter documented "
  919 |             "as ROUND-TRIP. Measured, not inferred (configs/cost_binding_verification.json)")
  920 |     if not reconciliation["financial_identity"]["all_hold"]:
  921 |         blockers.append("ACCOUNTING: the cash identity does not close on every arm")
  922 |     if confirmation["cells_not_ready"]:
  923 |         blockers.append(
  924 |             f"MATRIX: {confirmation['cells_not_ready']} of {confirmation['cells_planned']} cells "
  925 |             "are NOT_READY with null metrics, so the matrix is incomplete")
  926 |     if unlock["holdout_status"] != "CLEAN":
  927 |         blockers.append(
  928 |             "CONTAMINATION: the confirmation interval is NESTED RETROSPECTIVE. The supplied "
  929 |             "presets were tuned on the full sample with an unknown cutoff, so no interval of "
  930 |             "this dataset is an untouched holdout")
  931 |     if stress and not stress["cost_stress"]["harness_control"]["one_x_reproduces_every_arm"]:
  932 |         blockers.append("STRESS: the 1.0x cost level did not reproduce the confirmation run")
  933 |     supported = [name for name, entry in contributions.items()
  934 |                  if entry.get("verdict") == "SUPPORTED"]
  935 |     measured = [entry for entry in contributions.values() if entry.get("ci")]
  936 |     all_ruled_out = bool(measured) and all(e["verdict"] == "RULED_OUT" for e in measured)
  937 |     severity = (accounting or {}).get("severity")
  938 | 
  939 |     # The decision rule, in order, fixed before the numbers:
  940 |     #   1. a MAJOR accounting error invalidates the run regardless of what it says
  941 |     #   2. a contrast whose whole interval sits above the minimum is an edge
  942 |     #   3. every measured contrast ruled out below the minimum is no incremental value
  943 |     #   4. anything else is the sample failing to tell, which is not a negative result
  944 |     if severity == "MAJOR":
  945 |         level = "FAILED_VALIDITY"
  946 |     elif supported:
  947 |         level = {"SELECTION": "NET_PARAMETER_SELECTION_EDGE",
  948 |                  "TIMING": "NET_TIMING_EDGE",
  949 |                  "POLICY": "NET_POLICY_EDGE"}.get(supported[0], "DESCRIPTIVE_VALUE")
  950 |     elif all_ruled_out:
  951 |         level = "NO_INCREMENTAL_VALUE"
  952 |     else:
  953 |         level = "INCONCLUSIVE_SAMPLE"
  954 |     assert level in vocabulary, f"{level} is not in the registered vocabulary"
  955 | 
  956 |     return {
  957 |         "contributions": contributions,
  958 |         "contributions_judged_separately": True,
  959 |         "why_separately": ("a study that adds them up can call a risk-timing effect a "
  960 |                            "parameter-selection edge and never notice (guide 11.1)"),
  961 |         "net_gain_after_risk_and_cost": {
  962 |             "statistic": "mean daily net-return difference, paired on the same dates",
  963 |             "primary_contrast": "C-A for a timing claim, B-A for a selection claim",
  964 |             "interval_available": all(contrast(n).get("status") == "OK"
  965 |                                       for n in ("B-A", "C-A")),
  966 |             "B-A": contrast("B-A").get("ci_lower") is not None and [
  967 |                 contrast("B-A")["ci_lower"], contrast("B-A")["ci_upper"]],
  968 |             "C-A": contrast("C-A").get("ci_lower") is not None and [
  969 |                 contrast("C-A")["ci_lower"], contrast("C-A")["ci_upper"]],
  970 |             "minimum_economic_effect": minimum_effect,
  971 |         },
  972 |         "blockers": blockers,
  973 |         "accounting_severity": accounting,
  974 |         "decision_rule": [
  975 |             "1. a MAJOR accounting error yields FAILED_VALIDITY regardless of the contrasts",
  976 |             "2. a contrast whose whole 95% interval sits above the minimum economic effect is "
  977 |             "the corresponding edge",
  978 |             "3. every measured contrast ruled out BELOW the minimum is NO_INCREMENTAL_VALUE",
  979 |             "4. anything else is INCONCLUSIVE_SAMPLE -- the sample failing to distinguish is "
  980 |             "not a negative result, and reporting it as one would overstate the evidence",
  981 |         ],
  982 |         "decision_rule_fixed_before": "the confirmation intervals were computed",
  983 |         "conclusion_level": level,
  984 |         "conclusion_vocabulary": vocabulary,
  985 |         "vocabulary_source": "configs/hypothesis_registry.json",
  986 |         "development_outcome": (discovery or {}).get("design_selection", {}).get("outcome"),
  987 |         "confirms_the_development_outcome": None,
  988 |         "forbidden": {
  989 |             "fund_grade_alpha_proven": False,
  990 |             "statement": ("no claim of a proven fund-grade alpha is made or implied. This is a "
  991 |                           "lab backtest on one cohort with no funding product, a nested "
```

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B03 — `README.md`

Original bytes: **2,153**; SHA-256: `89bf2a89d2ea53bee16cd1f27badbd28e5cf31089aa8ccaa5701284288de5eb8`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/README.md","bytes":2153,"sha256":"89bf2a89d2ea53bee16cd1f27badbd28e5cf31089aa8ccaa5701284288de5eb8","encoding":"utf8"} -->
````text
# Audit reproduction bundle

Actual findings on the user-uploaded regime-lab-main.zip, reviewed 2026-09-11. This is not a full market rerun, not a native-wheel certificate, and not evidence that regime edge exists.

Read REGIME_LAB_ACTUAL_SOURCE_AUDIT_VI.md and source excerpts first.

## Run synthetic/source probes

Use an isolated environment with numpy, pandas, numba, optuna, pytest. The supplied quantbt_candidate directory contains the Python reference. Python 3.13 was used for this audit; the included upstream cp312 native wheel was not executed.

```bash
export REGIME_LAB_ROOT=/absolute/path/to/regime-lab-main
export REGIME_AUDIT_OUT=/absolute/path/to/new_audit_output
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMBA_CACHE_DIR="$REGIME_AUDIT_OUT/numba_cache"
mkdir -p "$REGIME_AUDIT_OUT"
python audit_probes.py
python additional_probes.py
python audit_evidence.py
```

Scripts read the provided source and write only to the requested audit directory; do not point that directory at source or production data. No package installation or network calls are performed. Some probes intentionally inject mismatched/failing engine results to demonstrate inadequate validation: they are not historical market observations.

Existing test subset run:

```bash
PYTHONPATH="$REGIME_LAB_ROOT/src:$REGIME_LAB_ROOT/quantbt_candidate" \
python -m pytest "$REGIME_LAB_ROOT/tests/test_lab05_regime.py" \
 "$REGIME_LAB_ROOT/tests/test_lab04_selector.py" \
 "$REGIME_LAB_ROOT/tests/test_lab06_policy.py" \
 "$REGIME_LAB_ROOT/tests/test_lab09_uncertainty.py" -q
```

Recorded result: 196 passed, 2 failed because tests reference a missing original venv executable. The original pytest log is retained. This should not be presented as two financial failures or a full-suite pass.

No raw market data, original complete repository, dependencies, credentials or venv is redistributed in this bundle. Source excerpts are selected from the user's provided code with original line numbers and full-file hashes. Market experiment reproduction still requires the snapshots named in the source manifests.

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B04 — `audit_probe_results.json`

Original bytes: **3,695**; SHA-256: `bd03eff7001a8cfd69b06cf7deb442063851611fdda5fbf01110020422a66667`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/audit_probe_results.json","bytes":3695,"sha256":"bd03eff7001a8cfd69b06cf7deb442063851611fdda5fbf01110020422a66667","encoding":"utf8"} -->
````json
{
  "scope": "uploaded-source synthetic/reference probes, NOT market replay",
  "python": "3.13.5 (main, Jul 15 2026, 20:25:40) [GCC 14.2.0]",
  "results": [
    {
      "id": "P01_fee_binding",
      "ran": true,
      "result": {
        "registered_one_way": 0.0004,
        "actual_rates": [
          0.0002,
          0.0002
        ],
        "fills": [
          {
            "bar_index": 1,
            "sequence": 0,
            "side": 1,
            "qty": 20.0,
            "price": 100.0,
            "fee": 0.4,
            "reason": "entry"
          },
          {
            "bar_index": 9,
            "sequence": 99,
            "side": -1,
            "qty": 20.0,
            "price": 100.0,
            "fee": 0.4,
            "reason": "final_close"
          }
        ],
        "final_equity": 19999.199999999997,
        "confirmed_half_fee": true
      }
    },
    {
      "id": "P02_initial_future_params",
      "ran": true,
      "result": {
        "requested_at_bar": 100,
        "first_active_at": 0,
        "pre_request_bars_using_future_params": 100,
        "first_fills": [],
        "confirmed_backdated": true
      }
    },
    {
      "id": "P03_namespace_and_invalid_emission",
      "ran": true,
      "result": {
        "chosen": [
          "2024-01-02T00:00:00+00:00"
        ],
        "semantic_state_changed": false,
        "selected_decision_eligible": false,
        "confirmed_namespace_trigger": true
      }
    },
    {
      "id": "P04_residual_context_collapse",
      "ran": true,
      "result": {
        "true_contexts": [
          [
            -2.0
          ],
          [
            2.0
          ]
        ],
        "response_features": [
          [
            0.0
          ],
          [
            0.0
          ]
        ],
        "distance_used_by_response": 0.0,
        "confirmed_distinct_states_collapsed": true
      }
    },
    {
      "id": "P05_hma_categorical_alias",
      "ran": true,
      "result": {
        "declared_choices": [
          "Half Distance Zone",
          "Zone Distance",
          "ATR"
        ],
        "adapter_mapping": {
          "One Distance Zone": 0,
          "Half Distance Zone": 1,
          "Last High/Low": 2,
          "ATR Only": 3
        },
        "effective_modes": {
          "Half Distance Zone": 1,
          "Zone Distance": 1,
          "ATR": 1
        },
        "all_search_choices_same": true
      }
    },
    {
      "id": "P06_unconverged_candidate_accepted",
      "ran": true,
      "result": {
        "run_converged": false,
        "unmapped_intents": 3,
        "evaluation_status": "EVALUATED",
        "window": {
          "net_return": 0.00055,
          "max_drawdown": 0.0,
          "sharpe_per_window": null,
          "fills": 0,
          "entries": 0,
          "exposure": 0.0,
          "mean_holding_bars": null,
          "bars": 12,
          "converged": false,
          "passes": 4,
          "unmapped_intents": 3
        },
        "accepted": true
      }
    },
    {
      "id": "P07_price_blind_convergence",
      "ran": true,
      "result": {
        "applied_fill_price": 80.0,
        "actual_engine_price": 120.0,
        "matched_bar": 5,
        "marked_converged": true,
        "confirmed_price_blind_convergence": true
      }
    },
    {
      "id": "P08_episode_boundary_pnl",
      "ran": true,
      "result": {
        "equity": [
          20000.0,
          20000.0,
          19000.0,
          19000.0
        ],
        "whole_loss": -1000.0,
        "episode_reported_returns": {
          "e0": 0.0,
          "e1": 0.0
        },
        "lost_boundary_pnl": true
      }
    }
  ]
}
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B05 — `additional_probe_results.json`

Original bytes: **1,484**; SHA-256: `e41a4891d23ffbc3c1f84dad55cb5bfdb1b701bfa033dfbbdabfc6054c4b8930`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/additional_probe_results.json","bytes":1484,"sha256":"e41a4891d23ffbc3c1f84dad55cb5bfdb1b701bfa033dfbbdabfc6054c4b8930","encoding":"utf8"} -->
````json
[
  {
    "id": "P09_cost_threshold_units",
    "result": {
      "original_threshold_account_bps_day": 0.64,
      "entry_notional_over_capital": 0.1,
      "threshold_from_stated_cost_formula_after_size_scaling_bps_day": 0.064,
      "factor": 10.0,
      "original_C_A_ci_account_bps_day": [
        -0.406823220261542,
        0.11446871628756412
      ],
      "original_B_A_ci_account_bps_day": [
        -0.2755849174986665,
        0.22962209376875597
      ],
      "note": "Only dimensional diagnostic; does not validate the faulty market experiment or authorize threshold retuning."
    }
  },
  {
    "id": "P10_ablation_target_changes",
    "result": {
      "identical_states": true,
      "fixed_economic_target_exactly_predictable_from_states": true,
      "G1_variance_resolved": 1.0,
      "G1_G2_variance_resolved": 0.5,
      "interpretation": "R-squared target changes when weights/features change; cannot infer marginal parameter-response value from this delta alone."
    }
  },
  {
    "id": "P11_followup_exit_ignored",
    "result": {
      "entry_filled": true,
      "correction_exit_generated": 1,
      "applied_exits": {},
      "protection_levels": {},
      "position_at_end": 20.0,
      "confirmed_corrective_followup_not_consumed": true
    }
  },
  {
    "id": "P12_ready_time_not_used",
    "result": {
      "cutoff_bar": 5,
      "ready_bar": 10,
      "schedule_requested_at": 5,
      "initial_deployment_has_no_ready_check": true
    }
  }
]
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B06 — `evidence_reanalysis.json`

Original bytes: **79,726**; SHA-256: `789cb49419cbb0f0bc7bf56326494f1ebdf77af9f2db7e0bd63031bf66b76c82`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/evidence_reanalysis.json","bytes":79726,"sha256":"789cb49419cbb0f0bc7bf56326494f1ebdf77af9f2db7e0bd63031bf66b76c82","encoding":"utf8"} -->
````json
{
  "scope": "recomputed from uploaded evidence, not new market simulation",
  "files": {
    "actual_files": 1893,
    "lab_python_files": 101,
    "scripts": 88,
    "tests": 27,
    "markdown": 18
  },
  "lab08_factorial_full": {
    "cells": 20,
    "run_cells": 15,
    "E_equals_D_cells": 15,
    "selected_hma_modes_repeated_by_arm": {},
    "vwap_exit_at_vwap_repeated_by_arm": {},
    "nonconverged_final_arms": [
      [
        "A-VWAP",
        "BTCUSDT",
        "A"
      ],
      [
        "A-VWAP",
        "BTCUSDT",
        "C"
      ],
      [
        "A-VWAP",
        "ETHUSDT",
        "A"
      ],
      [
        "A-VWAP",
        "ETHUSDT",
        "C"
      ],
      [
        "A-VWAP",
        "SOLUSDT",
        "C"
      ],
      [
        "A-VWAP",
        "BNBUSDT",
        "C"
      ],
      [
        "A-VWAP",
        "DOGEUSDT",
        "C"
      ]
    ],
    "per_cell": [
      {
        "alpha": "A-HMA",
        "symbol": "BTCUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.027105451052793494,
            "daily_sharpe": 0.3954239696020345,
            "max_drawdown": -0.02681629117553852,
            "entries": 24,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.04403582547160312,
            "daily_sharpe": 0.7651040389535472,
            "max_drawdown": -0.02630526203906325,
            "entries": 19,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 4,
            "switches_effected": 4,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.0651115445218109,
            "daily_sharpe": 1.0118408504440803,
            "max_drawdown": -0.024331121132884714,
            "entries": 65,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.0769673591107014,
            "daily_sharpe": 1.0589505661193674,
            "max_drawdown": -0.027814304439992,
            "entries": 86,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.0769673591107014,
            "daily_sharpe": 1.0589505661193674,
            "max_drawdown": -0.027814304439992,
            "entries": 86,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "ETHUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.020886131337127134,
            "daily_sharpe": -0.17929374029091413,
            "max_drawdown": -0.053444228541944416,
            "entries": 84,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.035866393676082575,
            "daily_sharpe": 0.4448596048489454,
            "max_drawdown": -0.0309851543074261,
            "entries": 29,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": -0.024670427425952046,
            "daily_sharpe": -0.21201076893709908,
            "max_drawdown": -0.053444228541944416,
            "entries": 91,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.01222706803279272,
            "daily_sharpe": 0.13328130613336212,
            "max_drawdown": -0.0449029822285526,
            "entries": 88,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.01222706803279272,
            "daily_sharpe": 0.13328130613336212,
            "max_drawdown": -0.0449029822285526,
            "entries": 88,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "SOLUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.01601282134689974,
            "daily_sharpe": 0.14749538722064792,
            "max_drawdown": -0.08024213020149262,
            "entries": 30,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.019935008076403138,
            "daily_sharpe": 0.24336417326058288,
            "max_drawdown": -0.05645148708324177,
            "entries": 25,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.05011700842413136,
            "daily_sharpe": 0.4218644056262209,
            "max_drawdown": -0.0617392562989999,
            "entries": 45,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": -0.03549101644190211,
            "daily_sharpe": -0.5362709541349482,
            "max_drawdown": -0.03842379614158964,
            "entries": 20,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": -0.03549101644190211,
            "daily_sharpe": -0.5362709541349482,
            "max_drawdown": -0.03842379614158964,
            "entries": 20,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "BNBUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.042305919540029935,
            "daily_sharpe": 1.1782437497648235,
            "max_drawdown": -0.010881237672716315,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.042305919540029935,
            "daily_sharpe": 1.1782437497648235,
            "max_drawdown": -0.010881237672716315,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": -0.028274595327349328,
            "daily_sharpe": -0.21782951237722414,
            "max_drawdown": -0.08566480322889591,
            "entries": 72,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": -0.0007631968759674868,
            "daily_sharpe": 0.014202601368551029,
            "max_drawdown": -0.07898728606975769,
            "entries": 70,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": -0.0007631968759674868,
            "daily_sharpe": 0.014202601368551029,
            "max_drawdown": -0.07898728606975769,
            "entries": 70,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "DOGEUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.010360722554150659,
            "daily_sharpe": 0.0830888714615258,
            "max_drawdown": -0.18063211602582074,
            "entries": 21,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.033914888762901274,
            "daily_sharpe": 0.4680591473802991,
            "max_drawdown": -0.027143760230480596,
            "entries": 11,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.026102492407039435,
            "daily_sharpe": 0.14570157716363893,
            "max_drawdown": -0.18063211602582074,
            "entries": 22,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.029109073176819544,
            "daily_sharpe": 0.31516218232242016,
            "max_drawdown": -0.04158498904209884,
            "entries": 36,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.029109073176819544,
            "daily_sharpe": 0.31516218232242016,
            "max_drawdown": -0.04158498904209884,
            "entries": 36,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "BTCUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.004523948540733791,
            "daily_sharpe": 0.058105702717617204,
            "max_drawdown": -0.0653215706229231,
            "entries": 74,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.05344739618367611,
            "daily_sharpe": 0.4243235317582833,
            "max_drawdown": -0.09052543693029935,
            "entries": 174,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 0,
            "switches_effected": 0,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": -0.03418115645556574,
            "daily_sharpe": -0.2912067153300854,
            "max_drawdown": -0.06977359620929047,
            "entries": 89,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.042219440191689994,
            "daily_sharpe": 0.3292257745766579,
            "max_drawdown": -0.08553644405906746,
            "entries": 52,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.042219440191689994,
            "daily_sharpe": 0.3292257745766579,
            "max_drawdown": -0.08553644405906746,
            "entries": 52,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "ETHUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.1276828152903251,
            "daily_sharpe": 0.7605827800003097,
            "max_drawdown": -0.06104497652242247,
            "entries": 289,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.12901666936016243,
            "daily_sharpe": 0.7201237573142558,
            "max_drawdown": -0.06104497652242247,
            "entries": 462,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 3,
            "switches_effected": 3,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.02302917635973034,
            "daily_sharpe": 0.16242165465152925,
            "max_drawdown": -0.09877246106934912,
            "entries": 265,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.11027184787498157,
            "daily_sharpe": 0.7145363279239703,
            "max_drawdown": -0.045243984546437854,
            "entries": 173,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.11027184787498157,
            "daily_sharpe": 0.7145363279239703,
            "max_drawdown": -0.045243984546437854,
            "entries": 173,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "SOLUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.48879956373054756,
            "daily_sharpe": 1.4911119731984943,
            "max_drawdown": -0.08578859582224618,
            "entries": 78,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.8053047495034191,
            "daily_sharpe": 2.1722052146702975,
            "max_drawdown": -0.07320446452457718,
            "entries": 60,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 1,
            "switches_effected": 1,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.39686255051077524,
            "daily_sharpe": 1.8138049989992713,
            "max_drawdown": -0.06011540377848423,
            "entries": 60,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.41762414310629903,
            "daily_sharpe": 1.5031340450632826,
            "max_drawdown": -0.06913631897002592,
            "entries": 196,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.41762414310629903,
            "daily_sharpe": 1.5031340450632826,
            "max_drawdown": -0.06913631897002592,
            "entries": 196,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "BNBUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.1949736939242619,
            "daily_sharpe": 0.808140733225374,
            "max_drawdown": -0.07653940617476862,
            "entries": 118,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.5668594408048611,
            "daily_sharpe": 0.9439018910374165,
            "max_drawdown": -0.13593721286476612,
            "entries": 171,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 0,
            "switches_effected": 0,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.5531158867777388,
            "daily_sharpe": 0.8980364833322712,
            "max_drawdown": -0.15209714051015022,
            "entries": 96,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.5672352623803918,
            "daily_sharpe": 0.9443389233324823,
            "max_drawdown": -0.13593721286476612,
            "entries": 169,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.5672352623803918,
            "daily_sharpe": 0.9443389233324823,
            "max_drawdown": -0.13593721286476612,
            "entries": 169,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "DOGEUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.5206968622087973,
            "daily_sharpe": 0.6628570449832666,
            "max_drawdown": -0.3307668783222941,
            "entries": 90,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.6608439577355967,
            "daily_sharpe": 0.7812305124549327,
            "max_drawdown": -0.34397117113318465,
            "entries": 147,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 0,
            "switches_effected": 0,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.5920408596874074,
            "daily_sharpe": 0.7212723394817714,
            "max_drawdown": -0.3307668783222941,
            "entries": 67,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.6608439577355967,
            "daily_sharpe": 0.7812305124549327,
            "max_drawdown": -0.34397117113318465,
            "entries": 147,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.6608439577355967,
            "daily_sharpe": 0.7812305124549327,
            "max_drawdown": -0.34397117113318465,
            "entries": 147,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "BTCUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.035040545760585684,
            "daily_sharpe": -0.5123007667173443,
            "max_drawdown": -0.046061678362015024,
            "entries": 8,
            "exit_fixed_point_converged": false,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 2,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": -0.04401652813106016,
            "daily_sharpe": -0.890228928472463,
            "max_drawdown": -0.07046640399420112,
            "entries": 96,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 1,
            "switches_effected": 1,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.026493607218555315,
            "daily_sharpe": 0.3109898474193414,
            "max_drawdown": -0.07989161616093943,
            "entries": 43,
            "exit_fixed_point_converged": false,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 4,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": -0.005732986588715128,
            "daily_sharpe": -0.4567350691008539,
            "max_drawdown": -0.008745384151521596,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": -0.005732986588715128,
            "daily_sharpe": -0.4567350691008539,
            "max_drawdown": -0.008745384151521596,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "ETHUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.011630173154765444,
            "daily_sharpe": 0.13162951262231748,
            "max_drawdown": -0.07287240380022386,
            "entries": 10,
            "exit_fixed_point_converged": false,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 2,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": -0.010095097660075214,
            "daily_sharpe": -0.7517579675526047,
            "max_drawdown": -0.012038892045314942,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 0,
            "switches_effected": 0,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.04994133595440875,
            "daily_sharpe": 0.39127598251667806,
            "max_drawdown": -0.07357553651888904,
            "entries": 15,
            "exit_fixed_point_converged": false,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 2,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": -0.010095097660075214,
            "daily_sharpe": -0.7517579675526047,
            "max_drawdown": -0.012038892045314942,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": -0.010095097660075214,
            "daily_sharpe": -0.7517579675526047,
            "max_drawdown": -0.012038892045314942,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "SOLUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.18732765717150723,
            "daily_sharpe": -1.5625472518138572,
            "max_drawdown": -0.19263112802186233,
            "entries": 112,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": -0.10846333653075113,
            "daily_sharpe": -1.9497797753916093,
            "max_drawdown": -0.11513706775314947,
            "entries": 167,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 1,
            "switches_effected": 1,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.10870993463124212,
            "daily_sharpe": 0.6981214176105791,
            "max_drawdown": -0.1159974764727798,
            "entries": 11,
            "exit_fixed_point_converged": false,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 2,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.0955335767023997,
            "daily_sharpe": 0.7093268098335938,
            "max_drawdown": -0.0929853387181081,
            "entries": 133,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.0955335767023997,
            "daily_sharpe": 0.7093268098335938,
            "max_drawdown": -0.0929853387181081,
            "entries": 133,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "BNBUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.0017351115372510328,
            "daily_sharpe": 0.036585109215062764,
            "max_drawdown": -0.04304784234463466,
            "entries": 10,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": -0.007784808107462626,
            "daily_sharpe": -0.9346639476909242,
            "max_drawdown": -0.01040184754916662,
            "entries": 5,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 0,
            "switches_effected": 0,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": -0.020151555041914793,
            "daily_sharpe": -0.12597607513978837,
            "max_drawdown": -0.07682776735134167,
            "entries": 17,
            "exit_fixed_point_converged": false,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 3,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": -0.03622328798488961,
            "daily_sharpe": -0.2774190864164244,
            "max_drawdown": -0.06983222535055744,
            "entries": 8,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": -0.03622328798488961,
            "daily_sharpe": -0.2774190864164244,
            "max_drawdown": -0.06983222535055744,
            "entries": 8,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "DOGEUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.08972429706551655,
            "daily_sharpe": 0.6338600994979177,
            "max_drawdown": -0.04290180897911333,
            "entries": 317,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 3,
            "delay": null
          },
          "B": {
            "status": "RUN",
            "net_return": 0.07104219073698359,
            "daily_sharpe": 0.5381166094920095,
            "max_drawdown": -0.038030175919334774,
            "entries": 821,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 3,
            "switches_effected": 3,
            "delay": null
          },
          "C": {
            "status": "RUN",
            "net_return": 0.17450740776580687,
            "daily_sharpe": 1.1136909258822538,
            "max_drawdown": -0.043094451393622224,
            "entries": 64,
            "exit_fixed_point_converged": false,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "D": {
            "status": "RUN",
            "net_return": 0.010271730783202093,
            "daily_sharpe": 0.7418389582019461,
            "max_drawdown": -0.005041116734089135,
            "entries": 2,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          },
          "E": {
            "status": "RUN",
            "net_return": 0.010271730783202093,
            "daily_sharpe": 0.7418389582019461,
            "max_drawdown": -0.005041116734089135,
            "entries": 2,
            "exit_fixed_point_converged": true,
            "versions_deployed": null,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": null
          }
        }
      }
    ]
  },
  "lab09_confirmation_results": {
    "cells": 20,
    "run_cells": 15,
    "E_equals_D_cells": 15,
    "selected_hma_modes_repeated_by_arm": {
      "ATR": 43,
      "Half Distance Zone": 47,
      "Zone Distance": 30
    },
    "vwap_exit_at_vwap_repeated_by_arm": {
      "True": 40,
      "False": 80
    },
    "nonconverged_final_arms": [
      [
        "A-VWAP",
        "BTCUSDT",
        "C"
      ],
      [
        "A-VWAP",
        "BTCUSDT",
        "D"
      ],
      [
        "A-VWAP",
        "BTCUSDT",
        "E"
      ],
      [
        "A-VWAP",
        "ETHUSDT",
        "A"
      ],
      [
        "A-VWAP",
        "SOLUSDT",
        "C"
      ]
    ],
    "per_cell": [
      {
        "alpha": "A-HMA",
        "symbol": "BTCUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.0008531330233035872,
            "daily_sharpe": -0.02981748732003672,
            "max_drawdown": -0.020671015139954618,
            "entries": 32,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 62,
              "WAITING_FOR_WARM_INDICATORS": 1318
            }
          },
          "B": {
            "status": "RUN",
            "net_return": 0.0009876848348864264,
            "daily_sharpe": 0.030935701463182703,
            "max_drawdown": -0.021639823077698073,
            "entries": 55,
            "exit_fixed_point_converged": true,
            "versions_deployed": 5,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 93,
              "WAITING_FOR_WARM_INDICATORS": 1327
            }
          },
          "C": {
            "status": "RUN",
            "net_return": -0.010830373654082681,
            "daily_sharpe": -0.7386457539053075,
            "max_drawdown": -0.017495271440538307,
            "entries": 11,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1422
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.03775361914538611,
            "daily_sharpe": -0.7717140344476631,
            "max_drawdown": -0.046215141194978826,
            "entries": 64,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 352,
              "WAITING_FOR_WARM_INDICATORS": 1180
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.03775361914538611,
            "daily_sharpe": -0.7717140344476631,
            "max_drawdown": -0.046215141194978826,
            "entries": 64,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 352,
              "WAITING_FOR_WARM_INDICATORS": 1180
            }
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "ETHUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.014860756030507183,
            "daily_sharpe": 0.6019075120534644,
            "max_drawdown": -0.007939262397753666,
            "entries": 34,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 29,
              "WAITING_FOR_WARM_INDICATORS": 1781
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.0014491964057259388,
            "daily_sharpe": -0.06526202039765755,
            "max_drawdown": -0.011327478477935138,
            "entries": 12,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 15,
              "WAITING_FOR_WARM_INDICATORS": 1805
            }
          },
          "C": {
            "status": "RUN",
            "net_return": -0.00106892002514547,
            "daily_sharpe": -0.04862592411232118,
            "max_drawdown": -0.011327478477935138,
            "entries": 10,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1426
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.00106892002514547,
            "daily_sharpe": -0.04862592411232118,
            "max_drawdown": -0.011327478477935138,
            "entries": 10,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1399
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.00106892002514547,
            "daily_sharpe": -0.04862592411232118,
            "max_drawdown": -0.011327478477935138,
            "entries": 10,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1399
            }
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "SOLUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.0370462517539929,
            "daily_sharpe": 0.7694521282427735,
            "max_drawdown": -0.019972296862028283,
            "entries": 36,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 11,
              "WAITING_FOR_WARM_INDICATORS": 1639
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.01881256706785628,
            "daily_sharpe": -0.6606865779415289,
            "max_drawdown": -0.04322504915955849,
            "entries": 30,
            "exit_fixed_point_converged": true,
            "versions_deployed": 5,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 27,
              "WAITING_FOR_WARM_INDICATORS": 1763
            }
          },
          "C": {
            "status": "RUN",
            "net_return": -0.01748744954708492,
            "daily_sharpe": -0.43442377710847624,
            "max_drawdown": -0.04005058887081281,
            "entries": 48,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 2,
              "WAITING_FOR_WARM_INDICATORS": 1678
            }
          },
          "D": {
            "status": "RUN",
            "net_return": 0.004293468728911565,
            "daily_sharpe": 0.5505612112203705,
            "max_drawdown": -0.003082729858742028,
            "entries": 2,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1780
            }
          },
          "E": {
            "status": "RUN",
            "net_return": 0.004293468728911565,
            "daily_sharpe": 0.5505612112203705,
            "max_drawdown": -0.003082729858742028,
            "entries": 2,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1780
            }
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "BNBUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.020251896983754736,
            "daily_sharpe": -0.39077730981865294,
            "max_drawdown": -0.052067213925311884,
            "entries": 34,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 168,
              "WAITING_FOR_WARM_INDICATORS": 1301
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.05228454552369566,
            "daily_sharpe": -1.1472242065261948,
            "max_drawdown": -0.05419214818240792,
            "entries": 32,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 45,
              "WAITING_FOR_WARM_INDICATORS": 1425
            }
          },
          "C": {
            "status": "RUN",
            "net_return": -0.025140567341013442,
            "daily_sharpe": -0.4701412805181661,
            "max_drawdown": -0.052833860584649894,
            "entries": 38,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 267,
              "WAITING_FOR_WARM_INDICATORS": 1683
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.09094437218917883,
            "daily_sharpe": -1.3089559355602698,
            "max_drawdown": -0.11152951269546696,
            "entries": 93,
            "exit_fixed_point_converged": true,
            "versions_deployed": 4,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 538,
              "WAITING_FOR_WARM_INDICATORS": 1299
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.09094437218917883,
            "daily_sharpe": -1.3089559355602698,
            "max_drawdown": -0.11152951269546696,
            "entries": 93,
            "exit_fixed_point_converged": true,
            "versions_deployed": 4,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 538,
              "WAITING_FOR_WARM_INDICATORS": 1299
            }
          }
        }
      },
      {
        "alpha": "A-HMA",
        "symbol": "DOGEUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.06730231808601483,
            "daily_sharpe": 0.8305975975750993,
            "max_drawdown": -0.022472107570331135,
            "entries": 28,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 135,
              "WAITING_FOR_WARM_INDICATORS": 1817
            }
          },
          "B": {
            "status": "RUN",
            "net_return": 0.06435224565800013,
            "daily_sharpe": 0.7971085226742514,
            "max_drawdown": -0.022472107570331135,
            "entries": 27,
            "exit_fixed_point_converged": true,
            "versions_deployed": 4,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 118,
              "WAITING_FOR_WARM_INDICATORS": 1772
            }
          },
          "C": {
            "status": "RUN",
            "net_return": -0.027536629807589308,
            "daily_sharpe": -0.5849554714850579,
            "max_drawdown": -0.03856492079481888,
            "entries": 29,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 10,
              "WAITING_FOR_WARM_INDICATORS": 1750
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.01990860911160308,
            "daily_sharpe": -0.5102912237750011,
            "max_drawdown": -0.030507448402469772,
            "entries": 5,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1760
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.01990860911160308,
            "daily_sharpe": -0.5102912237750011,
            "max_drawdown": -0.030507448402469772,
            "entries": 5,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 1760
            }
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "BTCUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.08702999311984017,
            "daily_sharpe": 0.9760023723386692,
            "max_drawdown": -0.03473790344494587,
            "entries": 51,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 1019,
              "WAITING_FOR_WARM_INDICATORS": 168
            }
          },
          "B": {
            "status": "RUN",
            "net_return": 0.055795832099647225,
            "daily_sharpe": 0.5880810951050849,
            "max_drawdown": -0.04036910575477304,
            "entries": 168,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 937,
              "WAITING_FOR_WARM_INDICATORS": 46
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.02910581273544466,
            "daily_sharpe": 0.374279406743047,
            "max_drawdown": -0.06284666864365995,
            "entries": 105,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 575,
              "WAITING_FOR_WARM_INDICATORS": 176
            }
          },
          "D": {
            "status": "RUN",
            "net_return": 0.055795832099647225,
            "daily_sharpe": 0.5880810951050849,
            "max_drawdown": -0.04036910575477304,
            "entries": 168,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 698,
              "WAITING_FOR_WARM_INDICATORS": 46
            }
          },
          "E": {
            "status": "RUN",
            "net_return": 0.055795832099647225,
            "daily_sharpe": 0.5880810951050849,
            "max_drawdown": -0.04036910575477304,
            "entries": 168,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 698,
              "WAITING_FOR_WARM_INDICATORS": 46
            }
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "ETHUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.02913514888895441,
            "daily_sharpe": 0.2750711863275287,
            "max_drawdown": -0.07167493506549161,
            "entries": 86,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 4801,
              "WAITING_FOR_WARM_INDICATORS": 106
            }
          },
          "B": {
            "status": "RUN",
            "net_return": 0.06722513196359658,
            "daily_sharpe": 0.5315589223584302,
            "max_drawdown": -0.08471091568600542,
            "entries": 164,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 616,
              "WAITING_FOR_WARM_INDICATORS": 46
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.06276330074092096,
            "daily_sharpe": 0.5239729169446057,
            "max_drawdown": -0.0819349352399209,
            "entries": 81,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 4583,
              "WAITING_FOR_WARM_INDICATORS": 121
            }
          },
          "D": {
            "status": "RUN",
            "net_return": 0.07988302247741896,
            "daily_sharpe": 0.732340445194395,
            "max_drawdown": -0.05878813473201572,
            "entries": 223,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 296,
              "WAITING_FOR_WARM_INDICATORS": 112
            }
          },
          "E": {
            "status": "RUN",
            "net_return": 0.07988302247741896,
            "daily_sharpe": 0.732340445194395,
            "max_drawdown": -0.05878813473201572,
            "entries": 223,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 296,
              "WAITING_FOR_WARM_INDICATORS": 112
            }
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "SOLUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.007919192584813772,
            "daily_sharpe": -0.07506904642366265,
            "max_drawdown": -0.057413940676484976,
            "entries": 60,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 108,
              "WAITING_FOR_WARM_INDICATORS": 222
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.04359623298405091,
            "daily_sharpe": -0.296060845692864,
            "max_drawdown": -0.08311878219764546,
            "entries": 849,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 124,
              "WAITING_FOR_WARM_INDICATORS": 39
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.06395849682937427,
            "daily_sharpe": 0.4317490356792069,
            "max_drawdown": -0.08538395422777256,
            "entries": 97,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 1054,
              "WAITING_FOR_WARM_INDICATORS": 113
            }
          },
          "D": {
            "status": "RUN",
            "net_return": 0.058083403768675046,
            "daily_sharpe": 0.41006279181481436,
            "max_drawdown": -0.07555897611220197,
            "entries": 209,
            "exit_fixed_point_converged": true,
            "versions_deployed": 4,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 1081,
              "WAITING_FOR_WARM_INDICATORS": 88
            }
          },
          "E": {
            "status": "RUN",
            "net_return": 0.058083403768675046,
            "daily_sharpe": 0.41006279181481436,
            "max_drawdown": -0.07555897611220197,
            "entries": 209,
            "exit_fixed_point_converged": true,
            "versions_deployed": 4,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 1081,
              "WAITING_FOR_WARM_INDICATORS": 88
            }
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "BNBUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.106154321683394,
            "daily_sharpe": 1.0534983017549922,
            "max_drawdown": -0.026911183925399818,
            "entries": 233,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 379,
              "WAITING_FOR_WARM_INDICATORS": 118
            }
          },
          "B": {
            "status": "RUN",
            "net_return": 0.062277956260373246,
            "daily_sharpe": 0.6862589245634658,
            "max_drawdown": -0.050880523552103374,
            "entries": 248,
            "exit_fixed_point_converged": true,
            "versions_deployed": 4,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 104,
              "WAITING_FOR_WARM_INDICATORS": 99
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.05632318735351838,
            "daily_sharpe": 0.43568474822743297,
            "max_drawdown": -0.10826169654546647,
            "entries": 116,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 11393,
              "WAITING_FOR_WARM_INDICATORS": 121
            }
          },
          "D": {
            "status": "RUN",
            "net_return": 0.04138599230282369,
            "daily_sharpe": 0.4024093179658906,
            "max_drawdown": -0.07415956842674387,
            "entries": 94,
            "exit_fixed_point_converged": true,
            "versions_deployed": 3,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 783,
              "WAITING_FOR_WARM_INDICATORS": 73
            }
          },
          "E": {
            "status": "RUN",
            "net_return": 0.04138599230282369,
            "daily_sharpe": 0.4024093179658906,
            "max_drawdown": -0.07415956842674387,
            "entries": 94,
            "exit_fixed_point_converged": true,
            "versions_deployed": 3,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 783,
              "WAITING_FOR_WARM_INDICATORS": 73
            }
          }
        }
      },
      {
        "alpha": "A-SC",
        "symbol": "DOGEUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.07170869785037515,
            "daily_sharpe": 0.4000428848799886,
            "max_drawdown": -0.08808731124462044,
            "entries": 297,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 255,
              "WAITING_FOR_WARM_INDICATORS": 93
            }
          },
          "B": {
            "status": "RUN",
            "net_return": 0.20627266587000648,
            "daily_sharpe": 0.9405180550948574,
            "max_drawdown": -0.09600124925218045,
            "entries": 302,
            "exit_fixed_point_converged": true,
            "versions_deployed": 3,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 346,
              "WAITING_FOR_WARM_INDICATORS": 33
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.02059516854296528,
            "daily_sharpe": 0.16245738967976703,
            "max_drawdown": -0.11758292940458825,
            "entries": 78,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 121,
              "WAITING_FOR_WARM_INDICATORS": 237
            }
          },
          "D": {
            "status": "RUN",
            "net_return": 0.1939279515586534,
            "daily_sharpe": 0.8811630816896803,
            "max_drawdown": -0.09600124925218045,
            "entries": 235,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 624,
              "WAITING_FOR_WARM_INDICATORS": 50
            }
          },
          "E": {
            "status": "RUN",
            "net_return": 0.1939279515586534,
            "daily_sharpe": 0.8811630816896803,
            "max_drawdown": -0.09600124925218045,
            "entries": 235,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 624,
              "WAITING_FOR_WARM_INDICATORS": 50
            }
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "BTCUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.022184209207616545,
            "daily_sharpe": -0.4862686913566103,
            "max_drawdown": -0.03543636329682498,
            "entries": 72,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 251
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.029311322499439352,
            "daily_sharpe": -0.7154508794807575,
            "max_drawdown": -0.044893319108157304,
            "entries": 133,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 61,
              "WAITING_FOR_WARM_INDICATORS": 235
            }
          },
          "C": {
            "status": "RUN",
            "net_return": -0.037521014202370306,
            "daily_sharpe": -0.750532099967636,
            "max_drawdown": -0.04902877711563114,
            "entries": 16,
            "exit_fixed_point_converged": false,
            "versions_deployed": 3,
            "switches_requested": 5,
            "switches_effected": 2,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 92946,
              "WAITING_FOR_WARM_INDICATORS": 50
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.015207821599246052,
            "daily_sharpe": -0.4392539409377468,
            "max_drawdown": -0.02496307680314469,
            "entries": 8,
            "exit_fixed_point_converged": false,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 2,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 92768,
              "WAITING_FOR_WARM_INDICATORS": 100
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.015207821599246052,
            "daily_sharpe": -0.4392539409377468,
            "max_drawdown": -0.02496307680314469,
            "entries": 8,
            "exit_fixed_point_converged": false,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 2,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 92768,
              "WAITING_FOR_WARM_INDICATORS": 100
            }
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "ETHUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.005809276018997167,
            "daily_sharpe": -0.10348285890613787,
            "max_drawdown": -0.03901414346971421,
            "entries": 23,
            "exit_fixed_point_converged": false,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 3555,
              "WAITING_FOR_WARM_INDICATORS": 245
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.004575557509295725,
            "daily_sharpe": -0.391085339801366,
            "max_drawdown": -0.006707447804905842,
            "entries": 7,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 250
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.007170920062321562,
            "daily_sharpe": 0.23984971809543304,
            "max_drawdown": -0.011178393777573792,
            "entries": 38,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 358
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.004575557509295725,
            "daily_sharpe": -0.391085339801366,
            "max_drawdown": -0.006707447804905842,
            "entries": 7,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 250
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.004575557509295725,
            "daily_sharpe": -0.391085339801366,
            "max_drawdown": -0.006707447804905842,
            "entries": 7,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 250
            }
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "SOLUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.06286537441355722,
            "daily_sharpe": -0.6686921433080372,
            "max_drawdown": -0.0868838845453932,
            "entries": 57,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 1344,
              "WAITING_FOR_WARM_INDICATORS": 183
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.033596567187670234,
            "daily_sharpe": -0.2623651926232321,
            "max_drawdown": -0.07546136032911266,
            "entries": 121,
            "exit_fixed_point_converged": true,
            "versions_deployed": 3,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 1344,
              "WAITING_FOR_WARM_INDICATORS": 216
            }
          },
          "C": {
            "status": "RUN",
            "net_return": -0.09768597383415167,
            "daily_sharpe": -0.7340797647804321,
            "max_drawdown": -0.10276245281376273,
            "entries": 35,
            "exit_fixed_point_converged": false,
            "versions_deployed": 5,
            "switches_requested": 5,
            "switches_effected": 4,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 18999,
              "WAITING_FOR_WARM_INDICATORS": 160
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.009115122187247637,
            "daily_sharpe": -1.0806487975145602,
            "max_drawdown": -0.011631848915229726,
            "entries": 4,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 250
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.009115122187247637,
            "daily_sharpe": -1.0806487975145602,
            "max_drawdown": -0.011631848915229726,
            "entries": 4,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 250
            }
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "BNBUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": -0.014852053295355105,
            "daily_sharpe": -0.3854552576911281,
            "max_drawdown": -0.02632977307276918,
            "entries": 81,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 259
            }
          },
          "B": {
            "status": "RUN",
            "net_return": -0.013203805326323703,
            "daily_sharpe": -0.45563644068322384,
            "max_drawdown": -0.03271281175035967,
            "entries": 42,
            "exit_fixed_point_converged": true,
            "versions_deployed": 3,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 259
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.0297208000994047,
            "daily_sharpe": 0.43959750476031084,
            "max_drawdown": -0.033987539767969976,
            "entries": 63,
            "exit_fixed_point_converged": true,
            "versions_deployed": 5,
            "switches_requested": 5,
            "switches_effected": 4,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 15564,
              "WAITING_FOR_WARM_INDICATORS": 172
            }
          },
          "D": {
            "status": "RUN",
            "net_return": 0.04228209389701787,
            "daily_sharpe": 0.9332077534345938,
            "max_drawdown": -0.014273311771045516,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 4,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 15536,
              "WAITING_FOR_WARM_INDICATORS": 200
            }
          },
          "E": {
            "status": "RUN",
            "net_return": 0.04228209389701787,
            "daily_sharpe": 0.9332077534345938,
            "max_drawdown": -0.014273311771045516,
            "entries": 6,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 4,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 15536,
              "WAITING_FOR_WARM_INDICATORS": 200
            }
          }
        }
      },
      {
        "alpha": "A-VWAP",
        "symbol": "DOGEUSDT",
        "E_equals_D": true,
        "arms": {
          "A": {
            "status": "RUN",
            "net_return": 0.020042973129432262,
            "daily_sharpe": 0.40003728078986983,
            "max_drawdown": -0.02371416783449498,
            "entries": 30,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 816,
              "WAITING_FOR_WARM_INDICATORS": 269
            }
          },
          "B": {
            "status": "RUN",
            "net_return": 0.0,
            "daily_sharpe": null,
            "max_drawdown": 0.0,
            "entries": 0,
            "exit_fixed_point_converged": true,
            "versions_deployed": 2,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 318
            }
          },
          "C": {
            "status": "RUN",
            "net_return": 0.032325107127647135,
            "daily_sharpe": 0.7777068146992068,
            "max_drawdown": -0.01573704619864058,
            "entries": 44,
            "exit_fixed_point_converged": true,
            "versions_deployed": 6,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 80,
              "WAITING_FOR_WARM_INDICATORS": 315
            }
          },
          "D": {
            "status": "RUN",
            "net_return": -0.018644095041571385,
            "daily_sharpe": -1.7746936992737454,
            "max_drawdown": -0.02080970199834098,
            "entries": 7,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 250
            }
          },
          "E": {
            "status": "RUN",
            "net_return": -0.018644095041571385,
            "daily_sharpe": -1.7746936992737454,
            "max_drawdown": -0.02080970199834098,
            "entries": 7,
            "exit_fixed_point_converged": true,
            "versions_deployed": 1,
            "switches_requested": 5,
            "switches_effected": 5,
            "delay": {
              "WAITING_FOR_WARM_INDICATORS": 250
            }
          }
        }
      }
    ]
  },
  "lab06_response_model": {
    "alpha_id": "A-SC",
    "symbol": "BTCUSDT",
    "response_count": 51944,
    "status_counts": {
      "INSUFFICIENT_SUPPORT": 41240,
      "SUPPORTED": 10704
    },
    "responses_sampled": 4000,
    "episode_panel_rows": 1530,
    "actually_retained_response_records": 400,
    "retained_sample_block_count": {
      "1": 400
    },
    "top_sample_reasons": [
      [
        "N_eff=1.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support",
        336
      ],
      [
        "N_eff=2.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support",
        64
      ]
    ]
  },
  "lab09_policy_response_model": {
    "alpha_id": "A-SC",
    "symbol": "BTCUSDT",
    "response_count": 46040,
    "status_counts": {
      "INSUFFICIENT_SUPPORT": 45720,
      "SUPPORTED": 320
    },
    "responses_sampled": 4000,
    "episode_panel_rows": 4140,
    "actually_retained_response_records": 400,
    "retained_sample_block_count": {
      "1": 400
    },
    "top_sample_reasons": [
      [
        "N_eff=1.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support",
        336
      ],
      [
        "N_eff=2.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support",
        64
      ]
    ]
  },
  "lab06_decision_ledger": {
    "keys": [
      "schema",
      "decisions",
      "counts",
      "switch_count",
      "every_decision_has_a_reason",
      "every_switch_has_supporting_episodes",
      "every_decision_records_its_cutoffs",
      "verdicts",
      "vacuous_verdicts",
      "distinct_decisions_used",
      "ledger",
      "data_role",
      "window"
    ],
    "schema": "crypto_regime_lab.decision_ledger.v1",
    "decisions": 6566,
    "counts": {
      "FALLBACK_NOVEL_STATE": 101,
      "KEEP_INCUMBENT": 1322,
      "NO_SUPPORTED_CANDIDATE": 5143
    },
    "switch_count": 0,
    "every_decision_has_a_reason": true,
    "every_switch_has_supporting_episodes": true,
    "every_decision_records_its_cutoffs": true,
    "verdicts": {
      "every_decision_has_a_reason": {
        "holds": true,
        "checked": 6566,
        "vacuous": false,
        "reading": "verified over 6566 decisions"
      },
      "every_switch_has_supporting_episodes": {
        "holds": true,
        "checked": 0,
        "vacuous": true,
        "reading": "no switches occurred, so this verifies nothing"
      },
      "every_decision_records_its_cutoffs": {
        "holds": true,
        "checked": 6566,
        "vacuous": false,
        "reading": "verified over 6566 decisions"
      }
    },
    "data_role": "development"
  },
  "lab09_policy_decision_ledger": {
    "keys": [
      "schema",
      "decisions",
      "counts",
      "switch_count",
      "every_decision_has_a_reason",
      "every_switch_has_supporting_episodes",
      "every_decision_records_its_cutoffs",
      "verdicts",
      "vacuous_verdicts",
      "distinct_decisions_used",
      "ledger",
      "data_role",
      "window"
    ],
    "schema": "crypto_regime_lab.decision_ledger.v1",
    "decisions": 5839,
    "counts": {
      "FALLBACK_NOVEL_STATE": 74,
      "KEEP_INCUMBENT": 37,
      "NO_SUPPORTED_CANDIDATE": 5728
    },
    "switch_count": 0,
    "every_decision_has_a_reason": true,
    "every_switch_has_supporting_episodes": true,
    "every_decision_records_its_cutoffs": true,
    "verdicts": {
      "every_decision_has_a_reason": {
        "holds": true,
        "checked": 5839,
        "vacuous": false,
        "reading": "verified over 5839 decisions"
      },
      "every_switch_has_supporting_episodes": {
        "holds": true,
        "checked": 0,
        "vacuous": true,
        "reading": "no switches occurred, so this verifies nothing"
      },
      "every_decision_records_its_cutoffs": {
        "holds": true,
        "checked": 5839,
        "vacuous": false,
        "reading": "verified over 5839 decisions"
      }
    },
    "data_role": "confirmation"
  },
  "jsonl_integrity": {
    "files": 571,
    "rows": 5634,
    "errors": []
  }
}
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B07 — `transition_audit.json`

Original bytes: **24,890**; SHA-256: `408e91be67f1c6559424c0f3dd08d8bb83573b543d73b6f73adc866ca7c1e4fb`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/transition_audit.json","bytes":24890,"sha256":"408e91be67f1c6559424c0f3dd08d8bb83573b543d73b6f73adc866ca7c1e4fb","encoding":"utf8"} -->
````json
[
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-HMA",
    "symbol": "BTCUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 220,
    "cutoffs": [
      "2021-01-03T08:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-21T16:00:00+00:00",
      "2022-07-02T04:00:00+00:00",
      "2022-12-31T16:00:00+00:00",
      "2023-07-07T12:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-03T08:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-HMA",
    "symbol": "ETHUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 238,
    "cutoffs": [
      "2021-01-02T20:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-21T12:00:00+00:00",
      "2022-07-02T00:00:00+00:00",
      "2022-12-31T08:00:00+00:00",
      "2023-07-02T16:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-02T20:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-HMA",
    "symbol": "SOLUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 255,
    "cutoffs": [
      "2021-01-01T16:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-22T20:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2022-12-31T08:00:00+00:00",
      "2023-07-03T20:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-01T16:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-HMA",
    "symbol": "BNBUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 185,
    "cutoffs": [
      "2021-01-02T16:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-22T12:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2022-12-31T12:00:00+00:00",
      "2023-07-04T08:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-02T16:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-HMA",
    "symbol": "DOGEUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 272,
    "cutoffs": [
      "2021-01-01T04:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-11T12:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2023-01-01T12:00:00+00:00",
      "2023-07-03T20:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-01T04:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-SC",
    "symbol": "BTCUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 220,
    "cutoffs": [
      "2021-01-03T08:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-21T16:00:00+00:00",
      "2022-07-02T04:00:00+00:00",
      "2022-12-31T16:00:00+00:00",
      "2023-07-07T12:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-03T08:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-SC",
    "symbol": "ETHUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 238,
    "cutoffs": [
      "2021-01-02T20:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-21T12:00:00+00:00",
      "2022-07-02T00:00:00+00:00",
      "2022-12-31T08:00:00+00:00",
      "2023-07-02T16:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-02T20:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-SC",
    "symbol": "SOLUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 255,
    "cutoffs": [
      "2021-01-01T16:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-22T20:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2022-12-31T08:00:00+00:00",
      "2023-07-03T20:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-01T16:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-SC",
    "symbol": "BNBUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 185,
    "cutoffs": [
      "2021-01-02T16:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-22T12:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2022-12-31T12:00:00+00:00",
      "2023-07-04T08:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-02T16:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-SC",
    "symbol": "DOGEUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 272,
    "cutoffs": [
      "2021-01-01T04:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-11T12:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2023-01-01T12:00:00+00:00",
      "2023-07-03T20:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-01T04:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-VWAP",
    "symbol": "BTCUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 220,
    "cutoffs": [
      "2021-01-03T08:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-21T16:00:00+00:00",
      "2022-07-02T04:00:00+00:00",
      "2022-12-31T16:00:00+00:00",
      "2023-07-07T12:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-03T08:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-VWAP",
    "symbol": "ETHUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 238,
    "cutoffs": [
      "2021-01-02T20:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-21T12:00:00+00:00",
      "2022-07-02T00:00:00+00:00",
      "2022-12-31T08:00:00+00:00",
      "2023-07-02T16:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-02T20:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-VWAP",
    "symbol": "SOLUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 255,
    "cutoffs": [
      "2021-01-01T16:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-22T20:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2022-12-31T08:00:00+00:00",
      "2023-07-03T20:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-01T16:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-VWAP",
    "symbol": "BNBUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 185,
    "cutoffs": [
      "2021-01-02T16:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-22T12:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2022-12-31T12:00:00+00:00",
      "2023-07-04T08:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-02T16:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab08_factorial_full",
    "alpha": "A-VWAP",
    "symbol": "DOGEUSDT",
    "n_emissions": 6571,
    "namespace_changes": 39,
    "state_changes_same_model": 272,
    "cutoffs": [
      "2021-01-01T04:00:00+00:00",
      "2021-07-15T04:00:00+00:00",
      "2022-01-11T12:00:00+00:00",
      "2022-07-14T04:00:00+00:00",
      "2023-01-01T12:00:00+00:00",
      "2023-07-03T20:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "namespace_change",
      "same_model_state_change",
      "same_model_state_change"
    ],
    "initial_time": "2021-01-01",
    "first_selection": "2021-01-01T04:00:00+00:00",
    "versions": {
      "A": null,
      "B": null,
      "C": null,
      "D": null,
      "E": null
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-HMA",
    "symbol": "BTCUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 219,
    "cutoffs": [
      "2024-01-02T04:00:00+00:00",
      "2024-06-12T20:00:00+00:00",
      "2024-11-21T00:00:00+00:00",
      "2025-05-09T12:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-02T04:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 5,
      "C": 6,
      "D": 6,
      "E": 6
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-HMA",
    "symbol": "ETHUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 228,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-13T04:00:00+00:00",
      "2024-11-21T08:00:00+00:00",
      "2025-05-08T20:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 6,
      "C": 6,
      "D": 6,
      "E": 6
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-HMA",
    "symbol": "SOLUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 186,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-13T12:00:00+00:00",
      "2024-11-28T16:00:00+00:00",
      "2025-05-09T12:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 5,
      "C": 6,
      "D": 6,
      "E": 6
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-HMA",
    "symbol": "BNBUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 214,
    "cutoffs": [
      "2024-01-01T08:00:00+00:00",
      "2024-06-12T04:00:00+00:00",
      "2024-11-28T00:00:00+00:00",
      "2025-05-09T16:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-01T08:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 6,
      "C": 6,
      "D": 4,
      "E": 4
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-HMA",
    "symbol": "DOGEUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 236,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-12T16:00:00+00:00",
      "2024-11-23T12:00:00+00:00",
      "2025-05-08T20:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 4,
      "C": 6,
      "D": 6,
      "E": 6
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-SC",
    "symbol": "BTCUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 219,
    "cutoffs": [
      "2024-01-02T04:00:00+00:00",
      "2024-06-12T20:00:00+00:00",
      "2024-11-21T00:00:00+00:00",
      "2025-05-09T12:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-02T04:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 1,
      "C": 6,
      "D": 1,
      "E": 1
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-SC",
    "symbol": "ETHUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 228,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-13T04:00:00+00:00",
      "2024-11-21T08:00:00+00:00",
      "2025-05-08T20:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 1,
      "C": 6,
      "D": 2,
      "E": 2
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-SC",
    "symbol": "SOLUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 186,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-13T12:00:00+00:00",
      "2024-11-28T16:00:00+00:00",
      "2025-05-09T12:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 1,
      "C": 6,
      "D": 4,
      "E": 4
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-SC",
    "symbol": "BNBUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 214,
    "cutoffs": [
      "2024-01-01T08:00:00+00:00",
      "2024-06-12T04:00:00+00:00",
      "2024-11-28T00:00:00+00:00",
      "2025-05-09T16:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-01T08:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 4,
      "C": 6,
      "D": 3,
      "E": 3
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-SC",
    "symbol": "DOGEUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 236,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-12T16:00:00+00:00",
      "2024-11-23T12:00:00+00:00",
      "2025-05-08T20:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 3,
      "C": 6,
      "D": 2,
      "E": 2
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-VWAP",
    "symbol": "BTCUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 219,
    "cutoffs": [
      "2024-01-02T04:00:00+00:00",
      "2024-06-12T20:00:00+00:00",
      "2024-11-21T00:00:00+00:00",
      "2025-05-09T12:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-02T04:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 2,
      "C": 3,
      "D": 2,
      "E": 2
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-VWAP",
    "symbol": "ETHUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 228,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-13T04:00:00+00:00",
      "2024-11-21T08:00:00+00:00",
      "2025-05-08T20:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 1,
      "C": 6,
      "D": 1,
      "E": 1
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-VWAP",
    "symbol": "SOLUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 186,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-13T12:00:00+00:00",
      "2024-11-28T16:00:00+00:00",
      "2025-05-09T12:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 3,
      "C": 5,
      "D": 1,
      "E": 1
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-VWAP",
    "symbol": "BNBUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 214,
    "cutoffs": [
      "2024-01-01T08:00:00+00:00",
      "2024-06-12T04:00:00+00:00",
      "2024-11-28T00:00:00+00:00",
      "2025-05-09T16:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-01T08:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 3,
      "C": 5,
      "D": 2,
      "E": 2
    }
  },
  {
    "experiment": "lab09_confirmation_results",
    "alpha": "A-VWAP",
    "symbol": "DOGEUSDT",
    "n_emissions": 5839,
    "namespace_changes": 34,
    "state_changes_same_model": 236,
    "cutoffs": [
      "2024-01-03T16:00:00+00:00",
      "2024-06-12T16:00:00+00:00",
      "2024-11-23T12:00:00+00:00",
      "2025-05-08T20:00:00+00:00",
      "2025-10-11T00:00:00+00:00",
      "2026-03-23T04:00:00+00:00"
    ],
    "trigger_types": [
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "same_model_state_change",
      "namespace_change"
    ],
    "initial_time": "2024-01-01",
    "first_selection": "2024-01-03T16:00:00+00:00",
    "versions": {
      "A": 6,
      "B": 2,
      "C": 6,
      "D": 1,
      "E": 1
    }
  }
]
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B08 — `trigger_eligibility_audit.json`

Original bytes: **12,536**; SHA-256: `385345857f4c001866b5649902fc148b5f0f474e14e3b764efda9e30d33b66da`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/trigger_eligibility_audit.json","bytes":12536,"sha256":"385345857f4c001866b5649902fc148b5f0f474e14e3b764efda9e30d33b66da","encoding":"utf8"} -->
````json
[
  {
    "stage": "development",
    "symbol": "BTCUSDT",
    "cutoff": "2021-01-03T08:00:00+00:00",
    "status": "UNKNOWN_STATE",
    "decision_eligible": false,
    "ready_at": "2026-09-10T15:34:30.538602+00:00"
  },
  {
    "stage": "development",
    "symbol": "BTCUSDT",
    "cutoff": "2021-07-15T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:35:40.216584+00:00"
  },
  {
    "stage": "development",
    "symbol": "BTCUSDT",
    "cutoff": "2022-01-21T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:36:43.029258+00:00"
  },
  {
    "stage": "development",
    "symbol": "BTCUSDT",
    "cutoff": "2022-07-02T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:37:44.063956+00:00"
  },
  {
    "stage": "development",
    "symbol": "BTCUSDT",
    "cutoff": "2022-12-31T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:38:54.492067+00:00"
  },
  {
    "stage": "development",
    "symbol": "BTCUSDT",
    "cutoff": "2023-07-07T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:39:59.317576+00:00"
  },
  {
    "stage": "development",
    "symbol": "ETHUSDT",
    "cutoff": "2021-01-02T20:00:00+00:00",
    "status": "UNKNOWN_STATE",
    "decision_eligible": false,
    "ready_at": "2026-09-10T15:41:58.608485+00:00"
  },
  {
    "stage": "development",
    "symbol": "ETHUSDT",
    "cutoff": "2021-07-15T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:43:01.115404+00:00"
  },
  {
    "stage": "development",
    "symbol": "ETHUSDT",
    "cutoff": "2022-01-21T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:43:56.033969+00:00"
  },
  {
    "stage": "development",
    "symbol": "ETHUSDT",
    "cutoff": "2022-07-02T00:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:44:49.594282+00:00"
  },
  {
    "stage": "development",
    "symbol": "ETHUSDT",
    "cutoff": "2022-12-31T08:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:46:04.360879+00:00"
  },
  {
    "stage": "development",
    "symbol": "ETHUSDT",
    "cutoff": "2023-07-02T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:47:01.925661+00:00"
  },
  {
    "stage": "development",
    "symbol": "SOLUSDT",
    "cutoff": "2021-01-01T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:48:44.532930+00:00"
  },
  {
    "stage": "development",
    "symbol": "SOLUSDT",
    "cutoff": "2021-07-15T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:49:24.158236+00:00"
  },
  {
    "stage": "development",
    "symbol": "SOLUSDT",
    "cutoff": "2022-01-22T20:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:50:30.872728+00:00"
  },
  {
    "stage": "development",
    "symbol": "SOLUSDT",
    "cutoff": "2022-07-14T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:51:41.848662+00:00"
  },
  {
    "stage": "development",
    "symbol": "SOLUSDT",
    "cutoff": "2022-12-31T08:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:52:51.949329+00:00"
  },
  {
    "stage": "development",
    "symbol": "SOLUSDT",
    "cutoff": "2023-07-03T20:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:53:51.491160+00:00"
  },
  {
    "stage": "development",
    "symbol": "BNBUSDT",
    "cutoff": "2021-01-02T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:55:34.211171+00:00"
  },
  {
    "stage": "development",
    "symbol": "BNBUSDT",
    "cutoff": "2021-07-15T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:56:47.196527+00:00"
  },
  {
    "stage": "development",
    "symbol": "BNBUSDT",
    "cutoff": "2022-01-22T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:57:53.241646+00:00"
  },
  {
    "stage": "development",
    "symbol": "BNBUSDT",
    "cutoff": "2022-07-14T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T15:59:00.337268+00:00"
  },
  {
    "stage": "development",
    "symbol": "BNBUSDT",
    "cutoff": "2022-12-31T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:00:05.877933+00:00"
  },
  {
    "stage": "development",
    "symbol": "BNBUSDT",
    "cutoff": "2023-07-04T08:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:01:21.946350+00:00"
  },
  {
    "stage": "development",
    "symbol": "DOGEUSDT",
    "cutoff": "2021-01-01T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:03:16.215709+00:00"
  },
  {
    "stage": "development",
    "symbol": "DOGEUSDT",
    "cutoff": "2021-07-15T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:04:21.195966+00:00"
  },
  {
    "stage": "development",
    "symbol": "DOGEUSDT",
    "cutoff": "2022-01-11T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:05:27.871349+00:00"
  },
  {
    "stage": "development",
    "symbol": "DOGEUSDT",
    "cutoff": "2022-07-14T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:06:38.876161+00:00"
  },
  {
    "stage": "development",
    "symbol": "DOGEUSDT",
    "cutoff": "2023-01-01T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:07:32.338427+00:00"
  },
  {
    "stage": "development",
    "symbol": "DOGEUSDT",
    "cutoff": "2023-07-03T20:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-10T16:08:31.069618+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BTCUSDT",
    "cutoff": "2024-01-02T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:52:09.291217+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BTCUSDT",
    "cutoff": "2024-06-12T20:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:53:03.392675+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BTCUSDT",
    "cutoff": "2024-11-21T00:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:54:03.417339+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BTCUSDT",
    "cutoff": "2025-05-09T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:54:58.051470+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BTCUSDT",
    "cutoff": "2025-10-11T00:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:55:52.924045+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BTCUSDT",
    "cutoff": "2026-03-23T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:56:46.166722+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "ETHUSDT",
    "cutoff": "2024-01-03T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:58:07.489640+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "ETHUSDT",
    "cutoff": "2024-06-13T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T03:59:04.521575+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "ETHUSDT",
    "cutoff": "2024-11-21T08:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:00:11.205984+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "ETHUSDT",
    "cutoff": "2025-05-08T20:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:01:16.051876+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "ETHUSDT",
    "cutoff": "2025-10-11T00:00:00+00:00",
    "status": "UNKNOWN_STATE",
    "decision_eligible": false,
    "ready_at": "2026-09-11T04:02:18.174531+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "ETHUSDT",
    "cutoff": "2026-03-23T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:03:18.763939+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "SOLUSDT",
    "cutoff": "2024-01-03T16:00:00+00:00",
    "status": "UNKNOWN_STATE",
    "decision_eligible": false,
    "ready_at": "2026-09-11T04:04:39.109488+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "SOLUSDT",
    "cutoff": "2024-06-13T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:05:28.285097+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "SOLUSDT",
    "cutoff": "2024-11-28T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:06:27.391639+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "SOLUSDT",
    "cutoff": "2025-05-09T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:07:25.325385+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "SOLUSDT",
    "cutoff": "2025-10-11T00:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:08:36.830824+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "SOLUSDT",
    "cutoff": "2026-03-23T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:09:39.174540+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BNBUSDT",
    "cutoff": "2024-01-01T08:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:11:12.148621+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BNBUSDT",
    "cutoff": "2024-06-12T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:12:14.753555+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BNBUSDT",
    "cutoff": "2024-11-28T00:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:13:24.160258+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BNBUSDT",
    "cutoff": "2025-05-09T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:14:16.591487+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BNBUSDT",
    "cutoff": "2025-10-11T00:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:15:16.558438+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "BNBUSDT",
    "cutoff": "2026-03-23T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:16:17.401689+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "DOGEUSDT",
    "cutoff": "2024-01-03T16:00:00+00:00",
    "status": "UNKNOWN_STATE",
    "decision_eligible": false,
    "ready_at": "2026-09-11T04:17:52.848696+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "DOGEUSDT",
    "cutoff": "2024-06-12T16:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:18:52.223753+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "DOGEUSDT",
    "cutoff": "2024-11-23T12:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:19:58.179847+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "DOGEUSDT",
    "cutoff": "2025-05-08T20:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:20:57.386250+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "DOGEUSDT",
    "cutoff": "2025-10-11T00:00:00+00:00",
    "status": "UNKNOWN_STATE",
    "decision_eligible": false,
    "ready_at": "2026-09-11T04:22:02.194661+00:00"
  },
  {
    "stage": "confirmation",
    "symbol": "DOGEUSDT",
    "cutoff": "2026-03-23T04:00:00+00:00",
    "status": "OK",
    "decision_eligible": true,
    "ready_at": "2026-09-11T04:23:07.268738+00:00"
  }
]
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B09 — `audit_probes.py`

Original bytes: **6,887**; SHA-256: `05c7c3552936cb1c285d872accd04a36ddc09de92b85a73cd2d39536e170b60e`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/audit_probes.py","bytes":6887,"sha256":"05c7c3552936cb1c285d872accd04a36ddc09de92b85a73cd2d39536e170b60e","encoding":"utf8"} -->
````python
import os
"""Independent audit probes on uploaded snapshot; no production/data writes.
This runs supplied functions on synthetic inputs. It is NOT a market backtest.
"""
from pathlib import Path
import sys,json,traceback,hashlib
from unittest.mock import patch
import numpy as np,pandas as pd
ROOT=Path(os.environ['REGIME_LAB_ROOT']).expanduser().resolve()
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'quantbt_candidate')]
OUT=Path(os.environ['REGIME_AUDIT_OUT']).expanduser().resolve(); OUT.mkdir(parents=True, exist_ok=True)
rows=[]
def probe(name,fn):
    try:
        d=fn();rows.append({'id':name,'ran':True,'result':d})
        print(name,json.dumps(d,default=str),flush=True)
    except Exception as e:
        rows.append({'id':name,'ran':False,'error':f'{type(e).__name__}: {e}','trace':traceback.format_exc()})
        print(name,'ERROR',repr(e),flush=True)
def frame(n=100):
    c=100+3*np.sin(np.arange(n)*.3)
    return pd.DataFrame({'open':c,'high':c+.3,'low':c-.3,'close':c,'volume':np.ones(n)*100},index=pd.date_range('2024-01-01',periods=n,freq='15min',tz='UTC'))
def fee():
    from crypto_regime_lab.quantbt_bridge.intent_tape import TapeBuild,run_intrabar
    f=frame(10);f.loc[:,'open']=100.;f.loc[:,'high']=101.;f.loc[:,'low']=99.;f.loc[:,'close']=100.
    t=TapeBuild(np.r_[1.,np.zeros(9)],np.r_[1.,np.zeros(9)],np.full(10,np.nan),np.full(10,np.nan),np.zeros(10,dtype=bool))
    r=run_intrabar(f,t,fee=.0004,slippage_bps=0,backend='reference',sizing_mode='fixed_notional',unit_notional=2000)
    ratios=[x['fee']/abs(x['qty']*x['price']) for x in r['fills']]
    return {'registered_one_way':.0004,'actual_rates':ratios,'fills':r['fills'],'final_equity':float(np.asarray(r['equity']).reshape(-1)[-1]),'confirmed_half_fee':all(abs(x-.0002)<1e-12 for x in ratios)}
def initial():
    from crypto_regime_lab.integration.continuous_account import VersionWindow,run_continuous_account
    from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS
    f=frame(200)
    v=VersionWindow('FUTURE_SELECTED',dict(SEED_POINTS['A-HMA']),100,'future')
    r=run_continuous_account('A-HMA',f,initial=v,schedule=[],backend='reference')
    return {'requested_at_bar':100,'first_active_at':r.version_by_bar.index('FUTURE_SELECTED'),'pre_request_bars_using_future_params':sum(x=='FUTURE_SELECTED' for x in r.version_by_bar[:100]),'first_fills':r.fills[:4],'confirmed_backdated':r.version_by_bar[0]=='FUTURE_SELECTED'}
def namespaces():
    from crypto_regime_lab.experiments.regime_schedule import transition_cutoffs
    e=[{'state_namespace':'v1','state_id':0,'available_at':'2024-01-01T00:00:00Z','decision_eligible':True},
       {'state_namespace':'v2','state_id':0,'available_at':'2024-01-02T00:00:00Z','decision_eligible':False,'quality_status':'MISSING_DATA'}]
    s=transition_cutoffs(e,count=1,earliest='2024-01-01',latest='2024-01-04',min_gap_days=0)
    return {'chosen':s.cutoffs,'semantic_state_changed':False,'selected_decision_eligible':False,'confirmed_namespace_trigger':len(s.cutoffs)==1}
def context():
    from crypto_regime_lab.regime.emissions import build_emission
    from crypto_regime_lab.policy.response import context_distance
    mu=np.array([[-2.],[2.]])
    es=[]
    for k in (0,1):
        costs=.5*(mu[:,0]-mu[k,0])**2
        e=build_emission(k,costs,namespace='v',z_t=mu[k],centroids=mu,weights=np.ones(1),groups={'G':[0]},observed_at='2024-01-01',available_at='2024-01-01',inferred_at='2024-01-01',model_fit_cutoff='2023-12-31',ready_at='2023-12-31',version='v')
        es.append(e)
    d=context_distance(np.array(es[0].feature_contributions),np.array(es[1].feature_contributions),np.ones(1))
    return {'true_contexts':mu.tolist(),'response_features':[e.feature_contributions for e in es],'distance_used_by_response':d,'confirmed_distinct_states_collapsed':d==0.}
def hma_modes():
    from crypto_regime_lab.alphas.a_hma import SL_MODES
    from crypto_regime_lab.selector.alpha_schemas import A_HMA
    specs=getattr(A_HMA,'specs',None)
    if isinstance(specs,dict):choices=specs['sl_input'].choices
    else:
        # Actual source declared values; cross-check source text in report.
        choices=('Half Distance Zone','Zone Distance','ATR')
    mapped={c:SL_MODES.get(c,1) for c in choices}
    return {'declared_choices':list(choices),'adapter_mapping':SL_MODES,'effective_modes':mapped,'all_search_choices_same':len(set(mapped.values()))==1}
def unconverged():
    from crypto_regime_lab.experiments import calendar_baseline as cb,evaluator as ev
    from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS,SCHEMAS
    f=frame(12)
    bad=ev.CandidateRun(np.arange(12)*1.+20000,np.zeros(12),[],f.index,False,4,0,3)
    with patch.object(cb,'run_candidate',return_value=bad):
        r=cb._evaluate('A-SC',SEED_POINTS['A-SC'],f,[('e0',0,12)],'audit',SCHEMAS['A-SC'],'reference')
    return {'run_converged':False,'unmapped_intents':3,'evaluation_status':str(r.status),'window':r.window,'accepted':r.status==cb.ProbeStatus.EVALUATED}
def convergence():
    from crypto_regime_lab.experiments import evaluator as ev
    from crypto_regime_lab.quantbt_bridge.intent_tape import TapeBuild
    from types import SimpleNamespace
    f=frame(12);t=TapeBuild(np.zeros(12),np.zeros(12),np.full(12,np.nan),np.full(12,np.nan),np.zeros(12,dtype=bool))
    observed={'bar_index':5,'price':120.,'qty':2.,'reason':'take_profit','side':-1,'fee':.05}
    with patch.object(ev,'_sweep',return_value=(SimpleNamespace(decisions=[]),{}, {5:80.})),patch.object(ev,'build_intent_tape',return_value=t),patch.object(ev,'_engine',return_value={'equity':np.full(12,20000.),'positions':np.zeros(12),'fills':[observed]}):
        r=ev.run_candidate('A-SC',{},f)
    return {'applied_fill_price':80.,'actual_engine_price':120.,'matched_bar':5,'marked_converged':r.converged,'confirmed_price_blind_convergence':r.converged}
def episode_boundary():
    from crypto_regime_lab.experiments import evaluator as ev
    f=frame(4);equity=np.array([20000.,20000.,19000.,19000.])
    r=ev.CandidateRun(equity,np.zeros(4),[],f.index,True,1,0)
    m=ev.episode_metrics(r,[('e0',0,2),('e1',2,4)])
    return {'equity':equity.tolist(),'whole_loss':float(equity[-1]-equity[0]),'episode_reported_returns':{k:v['net_return'] for k,v in m.items()},'lost_boundary_pnl':all(v['net_return']==0 for v in m.values())}
for name,fn in [('P01_fee_binding',fee),('P02_initial_future_params',initial),('P03_namespace_and_invalid_emission',namespaces),('P04_residual_context_collapse',context),('P05_hma_categorical_alias',hma_modes),('P06_unconverged_candidate_accepted',unconverged),('P07_price_blind_convergence',convergence),('P08_episode_boundary_pnl',episode_boundary)]:probe(name,fn)
(OUT/'audit_probe_results.json').write_text(json.dumps({'scope':'uploaded-source synthetic/reference probes, NOT market replay','python':sys.version,'results':rows},indent=2,default=str))

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B10 — `additional_probes.py`

Original bytes: **4,262**; SHA-256: `2424611cdc8e2b2cb4f77d52d64a77e652cd5ada5fcd4d45ba17b64dae9842a9`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/additional_probes.py","bytes":4262,"sha256":"2424611cdc8e2b2cb4f77d52d64a77e652cd5ada5fcd4d45ba17b64dae9842a9","encoding":"utf8"} -->
````python
import os
from pathlib import Path
import sys,json
import numpy as np,pandas as pd
from types import SimpleNamespace
from unittest.mock import patch
R=Path(os.environ['REGIME_LAB_ROOT']).expanduser().resolve(); O=Path(os.environ['REGIME_AUDIT_OUT']).expanduser().resolve(); O.mkdir(parents=True, exist_ok=True)
sys.path[:0]=[str(R/'src'),str(R/'quantbt_candidate')]
results=[]
def record(id,x):results.append({'id':id,'result':x});print(id,json.dumps(x,default=str),flush=True)
# Registered minimum effect missing portfolio sizing factor.
m=json.loads((R/'configs/minimum_economic_effect.json').read_text());claim=json.loads((R/'configs/lab09_claim_report.json').read_text())
ratio=2000/20000
threshold=m['minimum_daily_net_return_difference']
record('P09_cost_threshold_units',{'original_threshold_account_bps_day':threshold*1e4,'entry_notional_over_capital':ratio,'threshold_from_stated_cost_formula_after_size_scaling_bps_day':threshold*ratio*1e4,'factor':1/ratio,'original_C_A_ci_account_bps_day':[v*1e4 for v in claim['contributions']['TIMING']['ci']],'original_B_A_ci_account_bps_day':[v*1e4 for v in claim['contributions']['SELECTION']['ci']],'note':'Only dimensional diagnostic; does not validate the faulty market experiment or authorize threshold retuning.'})
# Conflating fit-explanation targets across feature sets: same perfect useful labels, added noise lowers fit statistic.
from crypto_regime_lab.regime.ablation import variance_resolved
states=np.tile([0,1],100); signal=2*states-1.;noise=np.tile([-1.,-1.,1.,1.],50)
z=np.c_[signal,noise];cents=np.array([[-1.,0.],[1.,0.]])
r1=variance_resolved(z,cents,states,np.array([1.,0.]));r2=variance_resolved(z,cents,states,np.array([.5,.5]))
record('P10_ablation_target_changes',{'identical_states':True,'fixed_economic_target_exactly_predictable_from_states':True,'G1_variance_resolved':r1,'G1_G2_variance_resolved':r2,'interpretation':'R-squared target changes when weights/features change; cannot infer marginal parameter-response value from this delta alone.'})
# Candidate/adapter flow drops actual corrective EXIT follow-up.
from crypto_regime_lab.experiments import evaluator as EV
from crypto_regime_lab.alphas.contracts import BarDecision,OrderIntent,IntentKind,ExecutionPhase
class Stub:
 def __init__(self):self.state=SimpleNamespace(position=0.);self.followups=[]
 def on_bar_close(self,t):
  intents=[OrderIntent(kind=IntentKind.ENTER_LONG,decision_index=t,earliest_phase=ExecutionPhase.NEXT_OPEN,reason='audit')] if t==2 else []
  return BarDecision(index=t,position_entering_bar=self.state.position,target_after_close=self.state.position,intents=intents)
 def on_fill(self,fill):
  self.state.position+=fill.quantity
  if fill.intent_kind==IntentKind.ENTER_LONG:
   q=OrderIntent(kind=IntentKind.EXIT_ALL,decision_index=fill.index,earliest_phase=ExecutionPhase.NEXT_OPEN,reason='bracket_invalid_after_gap')
   self.followups.append(q);return [q]
  return []
f=pd.DataFrame({k:np.full(12,100.) for k in ['open','high','low','close','volume']},index=pd.date_range('2024-01-01',periods=12,freq='15min',tz='UTC'))
stub=Stub()
with patch.object(EV,'build_adapter',return_value=stub):
 ad,levels,applied=EV._sweep('AUDIT',{},f,[f[c].to_numpy() for c in ['open','high','low','close','volume']],f,backend='reference')
record('P11_followup_exit_ignored',{'entry_filled':stub.state.position!=0,'correction_exit_generated':len(stub.followups),'applied_exits':applied,'protection_levels':levels,'position_at_end':stub.state.position,'confirmed_corrective_followup_not_consumed':bool(stub.followups) and stub.state.position>0})
# Request accepted before declared ready_at: schedule only uses cutoff, even if ready provided.
from crypto_regime_lab.experiments.factorial import _schedule_from_selections
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS
sel=[{'params':SEED_POINTS['A-HMA'],'cutoff':str(f.index[5]),'fit_ready_at':str(f.index[10])}]
initial,sched,_=_schedule_from_selections(sel,f,'A-HMA',seed_params=SEED_POINTS['A-HMA'])
record('P12_ready_time_not_used',{'cutoff_bar':5,'ready_bar':10,'schedule_requested_at':initial.requested_at_bar,'initial_deployment_has_no_ready_check':True})
(O/'additional_probe_results.json').write_text(json.dumps(results,indent=2,default=str))

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B11 — `audit_evidence.py`

Original bytes: **3,902**; SHA-256: `4b7f5b4e5488594e358c01fe7adc6ceee3ac2e001ef779bd807c92e4f505d44a`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/audit_evidence.py","bytes":3902,"sha256":"4b7f5b4e5488594e358c01fe7adc6ceee3ac2e001ef779bd807c92e4f505d44a","encoding":"utf8"} -->
````python
import os
from pathlib import Path
from collections import Counter
import json,hashlib,numpy as np,pandas as pd
R=Path(os.environ['REGIME_LAB_ROOT']).expanduser().resolve(); O=Path(os.environ['REGIME_AUDIT_OUT']).expanduser().resolve(); O.mkdir(parents=True, exist_ok=True)
summary={'scope':'recomputed from uploaded evidence, not new market simulation'}
summary['files']={'actual_files':len([p for p in R.rglob('*') if p.is_file()]),'lab_python_files':len(list((R/'src').rglob('*.py'))),'scripts':len(list((R/'scripts').glob('*.py'))),'tests':len(list((R/'tests').glob('test*.py'))),'markdown':len(list(R.rglob('*.md')))}
allrows=[]
for name in ['lab08_factorial_full','lab09_confirmation_results']:
 x=json.loads((R/'configs'/f'{name}.json').read_text());rows=[];eq=0;means={};hma_modes=Counter();vwapflag=Counter();err=[]
 for c in x['cells']:
  if c['status']!='RUN': continue
  arms=c['arms'];dr=c.get('daily_returns',{})
  if 'D' in dr and 'E' in dr:
   same=dr['D']==dr['E'];eq+=int(same)
  else:same=all(arms['D'].get(k)==arms['E'].get(k) for k in ['net_return','trades','entries','daily_sharpe','bars_by_parameter_version'])
  row={'alpha':c['alpha_id'],'symbol':c['symbol'],'E_equals_D':same,'arms':{}}
  for a,v in arms.items():
   row['arms'][a]={k:v.get(k) for k in ['status','net_return','daily_sharpe','max_drawdown','entries','exit_fixed_point_converged','versions_deployed','switches_requested','switches_effected']}
   row['arms'][a]['delay']=v.get('switch_delays',{}).get('blocked_bars_by_reason')
   if v.get('status')=='RUN' and v.get('exit_fixed_point_converged') is not True:err.append((c['alpha_id'],c['symbol'],a))
  for a,selections in c.get('notes',{}).get('deployed_selections',{}).items():
   if a=='E':continue
   for s in selections:
    if c['alpha_id']=='A-HMA':hma_modes[str(s['params'].get('sl_input'))]+=1
    if c['alpha_id']=='A-VWAP':vwapflag[str(s['params'].get('exit_at_vwap'))]+=1
  rows.append(row)
 summary[name]={'cells':len(x['cells']),'run_cells':len(rows),'E_equals_D_cells':sum(r['E_equals_D'] for r in rows),'selected_hma_modes_repeated_by_arm':dict(hma_modes),'vwap_exit_at_vwap_repeated_by_arm':dict(vwapflag),'nonconverged_final_arms':err,'per_cell':rows}
 allrows+=rows
for name in ['lab06_response_model','lab09_policy_response_model']:
 x=json.loads((R/'configs'/f'{name}.json').read_text());reason=Counter();blocks=Counter()
 for r in x['responses']:
  if r['status']=='INSUFFICIENT_SUPPORT':reason[str(r.get('reason'))]+=1
  blocks[str(r['diagnostics']['contiguous_blocks'])]+=1
 summary[name]={k:x.get(k) for k in ['alpha_id','symbol','response_count','status_counts','responses_sampled','episode_panel_rows']}
 summary[name]['actually_retained_response_records']=len(x['responses']);summary[name]['retained_sample_block_count']=dict(blocks)
 summary[name]['top_sample_reasons']=reason.most_common(3)
for name in ['lab06_decision_ledger','lab09_policy_decision_ledger']:
 x=json.loads((R/'configs'/f'{name}.json').read_text());summary[name]={'keys':list(x)}
 for k,v in x.items():
  if not isinstance(v,list) and not (isinstance(v,dict) and len(json.dumps(v))>3000):summary[name][k]=v
# every JSONL parser integrity, never execute the payloads
n=0;errors=[];counts={}
for p in R.rglob('*.jsonl'):
 count=0
 try:
  with p.open() as f:
   for li,line in enumerate(f,1):
    if not line.strip():continue
    json.loads(line);n+=1;count+=1
 except Exception as e:errors.append({'file':str(p.relative_to(R)),'line':li,'error':str(e)})
 counts[str(p.relative_to(R))]=count
summary['jsonl_integrity']={'files':len(counts),'rows':n,'errors':errors}
(O/'jsonl_row_counts.json').write_text(json.dumps(counts,indent=2))
(O/'evidence_reanalysis.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
for k,v in summary.items():
 if isinstance(v,dict): print(k,json.dumps({a:b for a,b in v.items() if a!='per_cell'},ensure_ascii=False)[:2300])

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B12 — `audit_probes.log`

Original bytes: **1,919**; SHA-256: `0c4c6fdf644665df9eb16622b2e679bc30a6eea8c6ec89707c9e0256bee41475`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/audit_probes.log","bytes":1919,"sha256":"0c4c6fdf644665df9eb16622b2e679bc30a6eea8c6ec89707c9e0256bee41475","encoding":"utf8"} -->
````text
P01_fee_binding {"registered_one_way": 0.0004, "actual_rates": [0.0002, 0.0002], "fills": [{"bar_index": 1, "sequence": 0, "side": 1, "qty": 20.0, "price": 100.0, "fee": 0.4, "reason": "entry"}, {"bar_index": 9, "sequence": 99, "side": -1, "qty": 20.0, "price": 100.0, "fee": 0.4, "reason": "final_close"}], "final_equity": 19999.199999999997, "confirmed_half_fee": true}
P02_initial_future_params {"requested_at_bar": 100, "first_active_at": 0, "pre_request_bars_using_future_params": 100, "first_fills": [], "confirmed_backdated": true}
P03_namespace_and_invalid_emission {"chosen": ["2024-01-02T00:00:00+00:00"], "semantic_state_changed": false, "selected_decision_eligible": false, "confirmed_namespace_trigger": true}
P04_residual_context_collapse {"true_contexts": [[-2.0], [2.0]], "response_features": [[0.0], [0.0]], "distance_used_by_response": 0.0, "confirmed_distinct_states_collapsed": true}
P05_hma_categorical_alias {"declared_choices": ["Half Distance Zone", "Zone Distance", "ATR"], "adapter_mapping": {"One Distance Zone": 0, "Half Distance Zone": 1, "Last High/Low": 2, "ATR Only": 3}, "effective_modes": {"Half Distance Zone": 1, "Zone Distance": 1, "ATR": 1}, "all_search_choices_same": true}
P06_unconverged_candidate_accepted {"run_converged": false, "unmapped_intents": 3, "evaluation_status": "EVALUATED", "window": {"net_return": 0.00055, "max_drawdown": 0.0, "sharpe_per_window": null, "fills": 0, "entries": 0, "exposure": 0.0, "mean_holding_bars": null, "bars": 12, "converged": false, "passes": 4, "unmapped_intents": 3}, "accepted": true}
P07_price_blind_convergence {"applied_fill_price": 80.0, "actual_engine_price": 120.0, "matched_bar": 5, "marked_converged": true, "confirmed_price_blind_convergence": true}
P08_episode_boundary_pnl {"equity": [20000.0, 20000.0, 19000.0, 19000.0], "whole_loss": -1000.0, "episode_reported_returns": {"e0": 0.0, "e1": 0.0}, "lost_boundary_pnl": true}

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B13 — `additional_probes.log`

Original bytes: **1,134**; SHA-256: `c43dea98ba289b41a3e40eedb1f8102b74997fe1d53f35eefecb429f42adad25`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/additional_probes.log","bytes":1134,"sha256":"c43dea98ba289b41a3e40eedb1f8102b74997fe1d53f35eefecb429f42adad25","encoding":"utf8"} -->
````text
P09_cost_threshold_units {"original_threshold_account_bps_day": 0.64, "entry_notional_over_capital": 0.1, "threshold_from_stated_cost_formula_after_size_scaling_bps_day": 0.064, "factor": 10.0, "original_C_A_ci_account_bps_day": [-0.406823220261542, 0.11446871628756412], "original_B_A_ci_account_bps_day": [-0.2755849174986665, 0.22962209376875597], "note": "Only dimensional diagnostic; does not validate the faulty market experiment or authorize threshold retuning."}
P10_ablation_target_changes {"identical_states": true, "fixed_economic_target_exactly_predictable_from_states": true, "G1_variance_resolved": 1.0, "G1_G2_variance_resolved": 0.5, "interpretation": "R-squared target changes when weights/features change; cannot infer marginal parameter-response value from this delta alone."}
P11_followup_exit_ignored {"entry_filled": true, "correction_exit_generated": 1, "applied_exits": {}, "protection_levels": {}, "position_at_end": 20.0, "confirmed_corrective_followup_not_consumed": true}
P12_ready_time_not_used {"cutoff_bar": 5, "ready_bar": 10, "schedule_requested_at": 5, "initial_deployment_has_no_ready_check": true}

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B14 — `evidence_reanalysis.log`

Original bytes: **4,187**; SHA-256: `97f413803259d94541e91d9705b58b6f5347a6b2ee36306a04d74e75c2cd6c04`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/evidence_reanalysis.log","bytes":4187,"sha256":"97f413803259d94541e91d9705b58b6f5347a6b2ee36306a04d74e75c2cd6c04","encoding":"utf8"} -->
````text
files {"actual_files": 1893, "lab_python_files": 101, "scripts": 88, "tests": 27, "markdown": 18}
lab08_factorial_full {"cells": 20, "run_cells": 15, "E_equals_D_cells": 15, "selected_hma_modes_repeated_by_arm": {}, "vwap_exit_at_vwap_repeated_by_arm": {}, "nonconverged_final_arms": [["A-VWAP", "BTCUSDT", "A"], ["A-VWAP", "BTCUSDT", "C"], ["A-VWAP", "ETHUSDT", "A"], ["A-VWAP", "ETHUSDT", "C"], ["A-VWAP", "SOLUSDT", "C"], ["A-VWAP", "BNBUSDT", "C"], ["A-VWAP", "DOGEUSDT", "C"]]}
lab09_confirmation_results {"cells": 20, "run_cells": 15, "E_equals_D_cells": 15, "selected_hma_modes_repeated_by_arm": {"ATR": 43, "Half Distance Zone": 47, "Zone Distance": 30}, "vwap_exit_at_vwap_repeated_by_arm": {"True": 40, "False": 80}, "nonconverged_final_arms": [["A-VWAP", "BTCUSDT", "C"], ["A-VWAP", "BTCUSDT", "D"], ["A-VWAP", "BTCUSDT", "E"], ["A-VWAP", "ETHUSDT", "A"], ["A-VWAP", "SOLUSDT", "C"]]}
lab06_response_model {"alpha_id": "A-SC", "symbol": "BTCUSDT", "response_count": 51944, "status_counts": {"INSUFFICIENT_SUPPORT": 41240, "SUPPORTED": 10704}, "responses_sampled": 4000, "episode_panel_rows": 1530, "actually_retained_response_records": 400, "retained_sample_block_count": {"1": 400}, "top_sample_reasons": [["N_eff=1.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support", 336], ["N_eff=2.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support", 64]]}
lab09_policy_response_model {"alpha_id": "A-SC", "symbol": "BTCUSDT", "response_count": 46040, "status_counts": {"INSUFFICIENT_SUPPORT": 45720, "SUPPORTED": 320}, "responses_sampled": 4000, "episode_panel_rows": 4140, "actually_retained_response_records": 400, "retained_sample_block_count": {"1": 400}, "top_sample_reasons": [["N_eff=1.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support", 336], ["N_eff=2.00 (min 4.0) over 1 contiguous blocks (min 2); the incumbent is kept rather than acting on thin support", 64]]}
lab06_decision_ledger {"keys": ["schema", "decisions", "counts", "switch_count", "every_decision_has_a_reason", "every_switch_has_supporting_episodes", "every_decision_records_its_cutoffs", "verdicts", "vacuous_verdicts", "distinct_decisions_used", "ledger", "data_role", "window"], "schema": "crypto_regime_lab.decision_ledger.v1", "decisions": 6566, "counts": {"FALLBACK_NOVEL_STATE": 101, "KEEP_INCUMBENT": 1322, "NO_SUPPORTED_CANDIDATE": 5143}, "switch_count": 0, "every_decision_has_a_reason": true, "every_switch_has_supporting_episodes": true, "every_decision_records_its_cutoffs": true, "verdicts": {"every_decision_has_a_reason": {"holds": true, "checked": 6566, "vacuous": false, "reading": "verified over 6566 decisions"}, "every_switch_has_supporting_episodes": {"holds": true, "checked": 0, "vacuous": true, "reading": "no switches occurred, so this verifies nothing"}, "every_decision_records_its_cutoffs": {"holds": true, "checked": 6566, "vacuous": false, "reading": "verified over 6566 decisions"}}, "data_role": "development"}
lab09_policy_decision_ledger {"keys": ["schema", "decisions", "counts", "switch_count", "every_decision_has_a_reason", "every_switch_has_supporting_episodes", "every_decision_records_its_cutoffs", "verdicts", "vacuous_verdicts", "distinct_decisions_used", "ledger", "data_role", "window"], "schema": "crypto_regime_lab.decision_ledger.v1", "decisions": 5839, "counts": {"FALLBACK_NOVEL_STATE": 74, "KEEP_INCUMBENT": 37, "NO_SUPPORTED_CANDIDATE": 5728}, "switch_count": 0, "every_decision_has_a_reason": true, "every_switch_has_supporting_episodes": true, "every_decision_records_its_cutoffs": true, "verdicts": {"every_decision_has_a_reason": {"holds": true, "checked": 5839, "vacuous": false, "reading": "verified over 5839 decisions"}, "every_switch_has_supporting_episodes": {"holds": true, "checked": 0, "vacuous": true, "reading": "no switches occurred, so this verifies nothing"}, "every_decision_records_its_cutoffs": {"holds": true, "checked": 5839, "vacuous": false, "reading": "verified over 5839 decisions"}}, "data_role": "confirmation"}
jsonl_integrity {"files": 571, "rows": 5634, "errors": []}

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B15 — `pytest_subset.log`

Original bytes: **19,794**; SHA-256: `9925e83b7cde5618b03474548bae795ca11029a41329b9beb0d7d6213c91795c`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/pytest_subset.log","bytes":19794,"sha256":"9925e83b7cde5618b03474548bae795ca11029a41329b9beb0d7d6213c91795c","encoding":"utf8"} -->
````text
........................................................................ [ 36%]
.....................F........................F......................... [ 72%]
......................................................                   [100%]
=================================== FAILURES ===================================
____________ test_t32_probe_design_is_reproducible_across_processes ____________

    def test_t32_probe_design_is_reproducible_across_processes():
        """A frozen design that changes per interpreter is not frozen."""
        code = (
            "import sys; sys.path.insert(0, 'src');"
            "from crypto_regime_lab.selector.probe_design import ProbeDesign;"
            "from crypto_regime_lab.selector.alpha_schemas import SCHEMAS, SEED_POINTS;"
            "d = ProbeDesign(SCHEMAS['A-VWAP'], probes_per_anchor=8);"
            "b = d.build({'a': dict(SEED_POINTS['A-VWAP'])});"
            "print(','.join(p['probe_id'] for p in b['probes']['a']))"
        )
        runs = set()
        for salt in ("0", "1", "random"):
>           done = subprocess.run([str(PY_BIN), "-c", code], cwd=LAB_ROOT, capture_output=True,
                                  text=True, env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": salt})

tests/test_lab04_selector.py:214: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.13/subprocess.py:554: in run
    with Popen(*popenargs, **kwargs) as process:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/lib/python3.13/subprocess.py:1039: in __init__
    self._execute_child(args, executable, preexec_fn, close_fds,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <Popen: returncode: 255 args: ['/mnt/data/regime_audit/source/regime-lab-mai...>
args = ['/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python', '-c', "import sys; sys.path.insert(...er_anchor=8);b = d.build({'a': dict(SEED_POINTS['A-VWAP'])});print(','.join(p['probe_id'] for p in b['probes']['a']))"]
executable = b'/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python'
preexec_fn = None, close_fds = True, pass_fds = ()
cwd = PosixPath('/mnt/data/regime_audit/source/regime-lab-main')
env = {'PATH': '/usr/bin:/bin', 'PYTHONHASHSEED': '0'}, startupinfo = None
creationflags = 0, shell = False, p2cread = -1, p2cwrite = -1, c2pread = 15
c2pwrite = 16, errread = 17, errwrite = 18, restore_signals = True, gid = None
gids = None, uid = None, umask = -1, start_new_session = False
process_group = -1

    def _execute_child(self, args, executable, preexec_fn, close_fds,
                       pass_fds, cwd, env,
                       startupinfo, creationflags, shell,
                       p2cread, p2cwrite,
                       c2pread, c2pwrite,
                       errread, errwrite,
                       restore_signals,
                       gid, gids, uid, umask,
                       start_new_session, process_group):
        """Execute program (POSIX version)"""
    
        if isinstance(args, (str, bytes)):
            args = [args]
        elif isinstance(args, os.PathLike):
            if shell:
                raise TypeError('path-like args is not allowed when '
                                'shell is true')
            args = [args]
        else:
            args = list(args)
    
        if shell:
            # On Android the default shell is at '/system/bin/sh'.
            unix_shell = ('/system/bin/sh' if
                      hasattr(sys, 'getandroidapilevel') else '/bin/sh')
            args = [unix_shell, "-c"] + args
            if executable:
                args[0] = executable
    
        if executable is None:
            executable = args[0]
    
        sys.audit("subprocess.Popen", executable, args, cwd, env)
    
        if (_USE_POSIX_SPAWN
                and os.path.dirname(executable)
                and preexec_fn is None
                and (not close_fds or _HAVE_POSIX_SPAWN_CLOSEFROM)
                and not pass_fds
                and cwd is None
                and (p2cread == -1 or p2cread > 2)
                and (c2pwrite == -1 or c2pwrite > 2)
                and (errwrite == -1 or errwrite > 2)
                and not start_new_session
                and process_group == -1
                and gid is None
                and gids is None
                and uid is None
                and umask < 0):
            self._posix_spawn(args, executable, env, restore_signals, close_fds,
                              p2cread, p2cwrite,
                              c2pread, c2pwrite,
                              errread, errwrite)
            return
    
        orig_executable = executable
    
        # For transferring possible exec failure from child to parent.
        # Data format: "exception name:hex errno:description"
        # Pickle is not used; it is complex and involves memory allocation.
        errpipe_read, errpipe_write = os.pipe()
        # errpipe_write must not be in the standard io 0, 1, or 2 fd range.
        low_fds_to_close = []
        while errpipe_write < 3:
            low_fds_to_close.append(errpipe_write)
            errpipe_write = os.dup(errpipe_write)
        for low_fd in low_fds_to_close:
            os.close(low_fd)
        try:
            try:
                # We must avoid complex work that could involve
                # malloc or free in the child process to avoid
                # potential deadlocks, thus we do all this here.
                # and pass it to fork_exec()
    
                if env is not None:
                    env_list = []
                    for k, v in env.items():
                        k = os.fsencode(k)
                        if b'=' in k:
                            raise ValueError("illegal environment variable name")
                        env_list.append(k + b'=' + os.fsencode(v))
                else:
                    env_list = None  # Use execv instead of execve.
                executable = os.fsencode(executable)
                if os.path.dirname(executable):
                    executable_list = (executable,)
                else:
                    # This matches the behavior of os._execvpe().
                    executable_list = tuple(
                        os.path.join(os.fsencode(dir), executable)
                        for dir in os.get_exec_path(env))
                fds_to_keep = set(pass_fds)
                fds_to_keep.add(errpipe_write)
                self.pid = _fork_exec(
                        args, executable_list,
                        close_fds, tuple(sorted(map(int, fds_to_keep))),
                        cwd, env_list,
                        p2cread, p2cwrite, c2pread, c2pwrite,
                        errread, errwrite,
                        errpipe_read, errpipe_write,
                        restore_signals, start_new_session,
                        process_group, gid, gids, uid, umask,
                        preexec_fn, _USE_VFORK)
                self._child_created = True
            finally:
                # be sure the FD is closed no matter what
                os.close(errpipe_write)
    
            self._close_pipe_fds(p2cread, p2cwrite,
                                 c2pread, c2pwrite,
                                 errread, errwrite)
    
            # Wait for exec to fail or succeed; possibly raising an
            # exception (limited in size)
            errpipe_data = bytearray()
            while True:
                part = os.read(errpipe_read, 50000)
                errpipe_data += part
                if not part or len(errpipe_data) > 50000:
                    break
        finally:
            # be sure the FD is closed no matter what
            os.close(errpipe_read)
    
        if errpipe_data:
            try:
                pid, sts = os.waitpid(self.pid, 0)
                if pid == self.pid:
                    self._handle_exitstatus(sts)
                else:
                    self.returncode = sys.maxsize
            except ChildProcessError:
                pass
    
            try:
                exception_name, hex_errno, err_msg = (
                        errpipe_data.split(b':', 2))
                # The encoding here should match the encoding
                # written in by the subprocess implementations
                # like _posixsubprocess
                err_msg = err_msg.decode()
            except ValueError:
                exception_name = b'SubprocessError'
                hex_errno = b'0'
                err_msg = 'Bad exception data from child: {!r}'.format(
                              bytes(errpipe_data))
            child_exception_type = getattr(
                    builtins, exception_name.decode('ascii'),
                    SubprocessError)
            if issubclass(child_exception_type, OSError) and hex_errno:
                errno_num = int(hex_errno, 16)
                if err_msg == "noexec:chdir":
                    err_msg = ""
                    # The error must be from chdir(cwd).
                    err_filename = cwd
                elif err_msg == "noexec":
                    err_msg = ""
                    err_filename = None
                else:
                    err_filename = orig_executable
                if errno_num != 0:
                    err_msg = os.strerror(errno_num)
                if err_filename is not None:
>                   raise child_exception_type(errno_num, err_msg, err_filename)
E                   FileNotFoundError: [Errno 2] No such file or directory: '/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python'

/usr/lib/python3.13/subprocess.py:1972: FileNotFoundError
____________ test_centroid_categorical_tie_break_is_process_stable _____________

    def test_centroid_categorical_tie_break_is_process_stable():
        """`set` iteration over str is salted, so a tie could move between runs."""
        code = (
            "import sys; sys.path.insert(0, 'src');"
            "from crypto_regime_lab.selector.representative import centroid_point;"
            "from crypto_regime_lab.selector.schema_distance import ParamSchema, ParamSpec;"
            "s = ParamSchema.from_specs([ParamSpec('m','categorical',choices=('a','b','c'))]);"
            "print(centroid_point(s, [{'m':'a'},{'m':'b'},{'m':'c'}])['m'])"
        )
        seen = set()
        for salt in ("0", "1", "12345"):
>           done = subprocess.run([str(PY_BIN), "-c", code], cwd=LAB_ROOT, capture_output=True,
                                  text=True, env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": salt})

tests/test_lab04_selector.py:491: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.13/subprocess.py:554: in run
    with Popen(*popenargs, **kwargs) as process:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/lib/python3.13/subprocess.py:1039: in __init__
    self._execute_child(args, executable, preexec_fn, close_fds,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <Popen: returncode: 255 args: ['/mnt/data/regime_audit/source/regime-lab-mai...>
args = ['/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python', '-c', "import sys; sys.path.insert(...([ParamSpec('m','categorical',choices=('a','b','c'))]);print(centroid_point(s, [{'m':'a'},{'m':'b'},{'m':'c'}])['m'])"]
executable = b'/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python'
preexec_fn = None, close_fds = True, pass_fds = ()
cwd = PosixPath('/mnt/data/regime_audit/source/regime-lab-main')
env = {'PATH': '/usr/bin:/bin', 'PYTHONHASHSEED': '0'}, startupinfo = None
creationflags = 0, shell = False, p2cread = -1, p2cwrite = -1, c2pread = 15
c2pwrite = 16, errread = 17, errwrite = 18, restore_signals = True, gid = None
gids = None, uid = None, umask = -1, start_new_session = False
process_group = -1

    def _execute_child(self, args, executable, preexec_fn, close_fds,
                       pass_fds, cwd, env,
                       startupinfo, creationflags, shell,
                       p2cread, p2cwrite,
                       c2pread, c2pwrite,
                       errread, errwrite,
                       restore_signals,
                       gid, gids, uid, umask,
                       start_new_session, process_group):
        """Execute program (POSIX version)"""
    
        if isinstance(args, (str, bytes)):
            args = [args]
        elif isinstance(args, os.PathLike):
            if shell:
                raise TypeError('path-like args is not allowed when '
                                'shell is true')
            args = [args]
        else:
            args = list(args)
    
        if shell:
            # On Android the default shell is at '/system/bin/sh'.
            unix_shell = ('/system/bin/sh' if
                      hasattr(sys, 'getandroidapilevel') else '/bin/sh')
            args = [unix_shell, "-c"] + args
            if executable:
                args[0] = executable
    
        if executable is None:
            executable = args[0]
    
        sys.audit("subprocess.Popen", executable, args, cwd, env)
    
        if (_USE_POSIX_SPAWN
                and os.path.dirname(executable)
                and preexec_fn is None
                and (not close_fds or _HAVE_POSIX_SPAWN_CLOSEFROM)
                and not pass_fds
                and cwd is None
                and (p2cread == -1 or p2cread > 2)
                and (c2pwrite == -1 or c2pwrite > 2)
                and (errwrite == -1 or errwrite > 2)
                and not start_new_session
                and process_group == -1
                and gid is None
                and gids is None
                and uid is None
                and umask < 0):
            self._posix_spawn(args, executable, env, restore_signals, close_fds,
                              p2cread, p2cwrite,
                              c2pread, c2pwrite,
                              errread, errwrite)
            return
    
        orig_executable = executable
    
        # For transferring possible exec failure from child to parent.
        # Data format: "exception name:hex errno:description"
        # Pickle is not used; it is complex and involves memory allocation.
        errpipe_read, errpipe_write = os.pipe()
        # errpipe_write must not be in the standard io 0, 1, or 2 fd range.
        low_fds_to_close = []
        while errpipe_write < 3:
            low_fds_to_close.append(errpipe_write)
            errpipe_write = os.dup(errpipe_write)
        for low_fd in low_fds_to_close:
            os.close(low_fd)
        try:
            try:
                # We must avoid complex work that could involve
                # malloc or free in the child process to avoid
                # potential deadlocks, thus we do all this here.
                # and pass it to fork_exec()
    
                if env is not None:
                    env_list = []
                    for k, v in env.items():
                        k = os.fsencode(k)
                        if b'=' in k:
                            raise ValueError("illegal environment variable name")
                        env_list.append(k + b'=' + os.fsencode(v))
                else:
                    env_list = None  # Use execv instead of execve.
                executable = os.fsencode(executable)
                if os.path.dirname(executable):
                    executable_list = (executable,)
                else:
                    # This matches the behavior of os._execvpe().
                    executable_list = tuple(
                        os.path.join(os.fsencode(dir), executable)
                        for dir in os.get_exec_path(env))
                fds_to_keep = set(pass_fds)
                fds_to_keep.add(errpipe_write)
                self.pid = _fork_exec(
                        args, executable_list,
                        close_fds, tuple(sorted(map(int, fds_to_keep))),
                        cwd, env_list,
                        p2cread, p2cwrite, c2pread, c2pwrite,
                        errread, errwrite,
                        errpipe_read, errpipe_write,
                        restore_signals, start_new_session,
                        process_group, gid, gids, uid, umask,
                        preexec_fn, _USE_VFORK)
                self._child_created = True
            finally:
                # be sure the FD is closed no matter what
                os.close(errpipe_write)
    
            self._close_pipe_fds(p2cread, p2cwrite,
                                 c2pread, c2pwrite,
                                 errread, errwrite)
    
            # Wait for exec to fail or succeed; possibly raising an
            # exception (limited in size)
            errpipe_data = bytearray()
            while True:
                part = os.read(errpipe_read, 50000)
                errpipe_data += part
                if not part or len(errpipe_data) > 50000:
                    break
        finally:
            # be sure the FD is closed no matter what
            os.close(errpipe_read)
    
        if errpipe_data:
            try:
                pid, sts = os.waitpid(self.pid, 0)
                if pid == self.pid:
                    self._handle_exitstatus(sts)
                else:
                    self.returncode = sys.maxsize
            except ChildProcessError:
                pass
    
            try:
                exception_name, hex_errno, err_msg = (
                        errpipe_data.split(b':', 2))
                # The encoding here should match the encoding
                # written in by the subprocess implementations
                # like _posixsubprocess
                err_msg = err_msg.decode()
            except ValueError:
                exception_name = b'SubprocessError'
                hex_errno = b'0'
                err_msg = 'Bad exception data from child: {!r}'.format(
                              bytes(errpipe_data))
            child_exception_type = getattr(
                    builtins, exception_name.decode('ascii'),
                    SubprocessError)
            if issubclass(child_exception_type, OSError) and hex_errno:
                errno_num = int(hex_errno, 16)
                if err_msg == "noexec:chdir":
                    err_msg = ""
                    # The error must be from chdir(cwd).
                    err_filename = cwd
                elif err_msg == "noexec":
                    err_msg = ""
                    err_filename = None
                else:
                    err_filename = orig_executable
                if errno_num != 0:
                    err_msg = os.strerror(errno_num)
                if err_filename is not None:
>                   raise child_exception_type(errno_num, err_msg, err_filename)
E                   FileNotFoundError: [Errno 2] No such file or directory: '/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python'

/usr/lib/python3.13/subprocess.py:1972: FileNotFoundError
=========================== short test summary info ============================
FAILED tests/test_lab04_selector.py::test_t32_probe_design_is_reproducible_across_processes - FileNotFoundError: [Errno 2] No such file or directory: '/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python'
FAILED tests/test_lab04_selector.py::test_centroid_categorical_tie_break_is_process_stable - FileNotFoundError: [Errno 2] No such file or directory: '/mnt/data/regime_audit/source/regime-lab-main/environments/lab_venv/bin/python'
2 failed, 196 passed in 3.57s

````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B16 — `source_excerpt_manifest.json`

Original bytes: **5,666**; SHA-256: `0d09ce5c384a55e81bb8bf5e762a82a966d3001aa3cc41f43ad5f7c98a86b998`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/source_excerpt_manifest.json","bytes":5666,"sha256":"0d09ce5c384a55e81bb8bf5e762a82a966d3001aa3cc41f43ad5f7c98a86b998","encoding":"utf8"} -->
````json
[
  {
    "id": "SRC01",
    "path": "src/crypto_regime_lab/experiments/factorial.py",
    "start_line": 170,
    "end_line": 203,
    "sha256": "9b22545e5f0f6fce59b07cab2d54379ba550890a9e38a3a996f0e243a2846ddf"
  },
  {
    "id": "SRC02",
    "path": "src/crypto_regime_lab/integration/continuous_account.py",
    "start_line": 165,
    "end_line": 222,
    "sha256": "1c27da4459b009ce6ca4d5630ce173eafc72c035ff153ddda81dba0da6f81f67"
  },
  {
    "id": "SRC03",
    "path": "src/crypto_regime_lab/integration/continuous_account.py",
    "start_line": 275,
    "end_line": 335,
    "sha256": "1c27da4459b009ce6ca4d5630ce173eafc72c035ff153ddda81dba0da6f81f67"
  },
  {
    "id": "SRC04",
    "path": "src/crypto_regime_lab/experiments/regime_schedule.py",
    "start_line": 78,
    "end_line": 156,
    "sha256": "c8f50b326cfcff56913d855ea5f3bb40c7877d8afe48d74187a6a3d1bf066b15"
  },
  {
    "id": "SRC05",
    "path": "scripts/run_lab08_factorial.py",
    "start_line": 260,
    "end_line": 303,
    "sha256": "e260ffc4f542b56ceb3f78b6523d77d84a116a7f6ab48c6b382600be87eab49b"
  },
  {
    "id": "SRC06",
    "path": "scripts/run_response_policy.py",
    "start_line": 46,
    "end_line": 147,
    "sha256": "b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83"
  },
  {
    "id": "SRC07",
    "path": "src/crypto_regime_lab/regime/emissions.py",
    "start_line": 190,
    "end_line": 240,
    "sha256": "1ece10418d865eb1010d2cfbb66125caded2034c8fbf09bbb2c4ca02a2239a1f"
  },
  {
    "id": "SRC08",
    "path": "scripts/run_response_policy.py",
    "start_line": 195,
    "end_line": 270,
    "sha256": "b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83"
  },
  {
    "id": "SRC09",
    "path": "scripts/run_response_policy.py",
    "start_line": 319,
    "end_line": 415,
    "sha256": "b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83"
  },
  {
    "id": "SRC10",
    "path": "src/crypto_regime_lab/policy/response.py",
    "start_line": 100,
    "end_line": 200,
    "sha256": "4e372653a18e6257597aacf9d35244750224f74a84119e05403654edcc626057"
  },
  {
    "id": "SRC11",
    "path": "src/crypto_regime_lab/policy/bank.py",
    "start_line": 155,
    "end_line": 214,
    "sha256": "c3ef5c2bee708bac0464e603f882ce4d5f844c119719cd25ba9e3e4f125a1a55"
  },
  {
    "id": "SRC12",
    "path": "src/crypto_regime_lab/experiments/evaluator.py",
    "start_line": 84,
    "end_line": 119,
    "sha256": "b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5"
  },
  {
    "id": "SRC13",
    "path": "src/crypto_regime_lab/quantbt_bridge/intent_tape.py",
    "start_line": 55,
    "end_line": 150,
    "sha256": "b690b50fa08aba7a42fca1b4474654c61f031d7d708a1ee3dbe1e2a295496a0d"
  },
  {
    "id": "SRC14",
    "path": "src/crypto_regime_lab/experiments/evaluator.py",
    "start_line": 126,
    "end_line": 239,
    "sha256": "b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5"
  },
  {
    "id": "SRC15",
    "path": "src/crypto_regime_lab/experiments/evaluator.py",
    "start_line": 246,
    "end_line": 326,
    "sha256": "b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5"
  },
  {
    "id": "SRC16",
    "path": "src/crypto_regime_lab/experiments/calendar_baseline.py",
    "start_line": 142,
    "end_line": 210,
    "sha256": "f468f00abf37afe692f0f7650dff411d4a38e1f72e71c4e632b79e8c8ee8642d"
  },
  {
    "id": "SRC17",
    "path": "src/crypto_regime_lab/experiments/calendar_baseline.py",
    "start_line": 351,
    "end_line": 409,
    "sha256": "f468f00abf37afe692f0f7650dff411d4a38e1f72e71c4e632b79e8c8ee8642d"
  },
  {
    "id": "SRC18",
    "path": "src/crypto_regime_lab/selector/alpha_schemas.py",
    "start_line": 35,
    "end_line": 85,
    "sha256": "933268e7b8d727016c74bec73811effc3a5f09fb4af3a816cd04cba83ff10b0b"
  },
  {
    "id": "SRC19",
    "path": "src/crypto_regime_lab/alphas/a_hma.py",
    "start_line": 26,
    "end_line": 40,
    "sha256": "dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca"
  },
  {
    "id": "SRC20",
    "path": "src/crypto_regime_lab/alphas/a_hma.py",
    "start_line": 248,
    "end_line": 272,
    "sha256": "dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca"
  },
  {
    "id": "SRC21",
    "path": "src/crypto_regime_lab/alphas/a_hma.py",
    "start_line": 315,
    "end_line": 352,
    "sha256": "dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca"
  },
  {
    "id": "SRC22",
    "path": "src/crypto_regime_lab/alphas/a_vwap.py",
    "start_line": 201,
    "end_line": 233,
    "sha256": "242facf154f4505ab862ac6815ee497d0e9c6e3ee70bbdb8b6cb1895a2900b77"
  },
  {
    "id": "SRC23",
    "path": "scripts/close_lab01_blockers.py",
    "start_line": 52,
    "end_line": 94,
    "sha256": "45f98643f03b22cb0c3d2247c0b27785d7d3f36d6c3683509cbc808b7c06199d"
  },
  {
    "id": "SRC24",
    "path": "scripts/fit_regime_model.py",
    "start_line": 140,
    "end_line": 220,
    "sha256": "3057737f342d9f11cf237d4a3a300c2ef69b43b84cf68d468f331077759339ae"
  },
  {
    "id": "SRC25",
    "path": "src/crypto_regime_lab/regime/registry.py",
    "start_line": 140,
    "end_line": 225,
    "sha256": "432a33230cba5fd271af9f0e06ba4141105893bdc5934cbf98863d07827a3ad6"
  },
  {
    "id": "SRC26",
    "path": "src/crypto_regime_lab/regime/ablation.py",
    "start_line": 1,
    "end_line": 199,
    "sha256": "5d7094c6be54a67b30f6056d9c15b2654cad4116e73b57730cbff2d5f9554e46"
  },
  {
    "id": "SRC27",
    "path": "scripts/analyse_lab09_confirmation.py",
    "start_line": 860,
    "end_line": 991,
    "sha256": "949c322271bfd18290a60c01a6cb6bf14d8cb155b5e2f840fe8db73e5a7fbc51"
  }
]
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B17 — `jsonl_row_counts.json`

Original bytes: **46,061**; SHA-256: `6272488e0b7d9a06d3e1d3f780e48f3e26d10280b15ca401b6ea28aeac0dd05c`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/jsonl_row_counts.json","bytes":46061,"sha256":"6272488e0b7d9a06d3e1d3f780e48f3e26d10280b15ca401b6ea28aeac0dd05c","encoding":"utf8"} -->
````json
{
  "evidence/selftest/run-20260911T105819Z-6d6b9ca3/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T104610Z-88467b3c/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T142824Z-86c14978/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T105051Z-6aa85dbe/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T135112Z-8e5bccc4/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173811Z-48f51254/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T093330Z-513f277a/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T102531Z-7cc6344b/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T061201Z-843a7666/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T122035Z-4d663a08/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T135115Z-b7825b40/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T093109Z-64f8f3c0/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173526Z-432e7ff8/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T121834Z-97b854e4/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T035954Z-4a16000e/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T003309Z-d4badc7d/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135301Z-5c0bf54b/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T105054Z-ec7fbbfa/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T184436Z-f04ef34a/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T182732Z-50cfbb26/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T142621Z-2170f9d2/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T061359Z-7d735b09/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T042131Z-05334791/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T200307Z-b8339bc9/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T132656Z-5385f53f/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T065844Z-b9c26f93/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T101254Z-f748bad9/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T200307Z-a53aa619/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T075016Z-977e3535/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T130712Z-808b1292/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T164748Z-62d3b48b/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T102728Z-2095453d/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T132228Z-898e258c/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T063228Z-1a42101a/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T110040Z-cffdd3ab/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T170230Z-7afeb368/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T140440Z-2bfcae22/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T170201Z-90bc2bd7/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T104831Z-c7158f6c/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T004943Z-9285b2a4/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171811Z-e1db0126/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T170122Z-94983d9f/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135834Z-087c02ce/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T201137Z-5d862677/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135834Z-9c56bc9d/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T140031Z-45e6aed0/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T170233Z-f45e9111/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T171008Z-ea75074f/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T202302Z-bfb11ff9/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T182828Z-bdf4df03/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T171808Z-49ee99e8/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173437Z-44a78684/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T132925Z-22f895d4/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T093112Z-aba745aa/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T113514Z-d6307b1c/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T140437Z-51b0f092/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T104607Z-d10a5eb0/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T105310Z-8c9a9909/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T194235Z-ab68fd4b/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T081338Z-4fec5afc/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T030734Z-1a8160b8/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T092812Z-48829591/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T070818Z-b5d4dbea/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T171811Z-e378db84/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T064937Z-f10c2ad5/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T132224Z-5868301e/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T121834Z-24785ec0/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T053248Z-e0f0a2f5/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135115Z-924ff21d/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T173809Z-9ab2ff38/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T041310Z-e10962d9/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T142618Z-cd1a717f/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T003306Z-1e650db6/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T043839Z-2b45ab17/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T091247Z-d3e02254/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T064937Z-09a16bb3/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T004943Z-70f187a1/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T104834Z-538cd077/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T182729Z-9faed404/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173523Z-870a5cc8/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T184824Z-9f3f4e23/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T101645Z-75f487d0/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T081335Z-4ed9a5f0/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T110419Z-fedb0741/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T064933Z-81429913/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T132653Z-ffd16b62/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T200304Z-95f523f1/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T170122Z-ca18aabe/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T075406Z-0a9a4030/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173526Z-29b305b4/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T101645Z-0dc009ae/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T105447Z-9c052c2f/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T065204Z-fd037b50/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T085942Z-34f01a36/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T042134Z-62247281/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T170201Z-e10b2f81/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T130749Z-b2d5204d/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T070821Z-5b05de31/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135645Z-3a7c7413/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T130709Z-f8b4f747/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T170314Z-e5e7fffd/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T110422Z-978be856/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T124256Z-a0b1632c/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T113040Z-635c3ceb/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T140649Z-5a005117/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T192806Z-73798e9d/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T105819Z-0a413294/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T105447Z-047424a1/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T065204Z-4660be94/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T105258Z-ca10b48d/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T184734Z-06607e11/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T070821Z-640842f0/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T171011Z-bfef7b33/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T173437Z-cd20c7b2/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171732Z-445df3a6/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T041611Z-d5a3dfe9/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T124124Z-41237d3f/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T171735Z-4e5e1936/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T171011Z-2ecddb5c/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T122038Z-480c94ef/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T173811Z-c4cd5005/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T090217Z-75b9a2f8/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T025927Z-89d98d12/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T102123Z-8557547c/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T041608Z-9afa05f3/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T102728Z-f7845f94/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T075013Z-b4b6cdf5/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T184826Z-b11defa7/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T065840Z-0ba87681/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T110043Z-abf3a59a/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T184737Z-b2477fb5/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T184433Z-1aaf54ed/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T101254Z-683223f9/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T105054Z-9ac9a818/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135642Z-c5ec0067/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T165003Z-dd1f1926/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T140646Z-95e8a986/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T091247Z-bdc63a2e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T130712Z-95a73396/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T110653Z-41febe77/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T182831Z-c5ad482d/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T173724Z-67ad376f/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T202302Z-0b153094/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T140440Z-7442b1e0/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T173721Z-be1e8d57/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T053246Z-6a1100ff/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T104611Z-41f29fa8/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T061359Z-ba819394/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T195627Z-4ac72f1b/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T135831Z-e9e55e6b/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T130752Z-d2ad3cbe/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T184737Z-4d13efe5/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T124259Z-4304a3b2/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T104610Z-6d2a2205/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T110043Z-a6c3988d/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T124127Z-73624ea9/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T104611Z-020dbaf3/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T202259Z-05150916/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T164722Z-59aa73b4/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T182831Z-e94e5440/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T085946Z-7734a957/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135454Z-f84711ee/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T042134Z-82f9e68e/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T194946Z-9d674a2c/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171938Z-fecbd17f/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T142621Z-fd303a0c/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T110649Z-e4d77723/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T025935Z-37c8da24/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T081338Z-77ab1dea/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T085946Z-02f4ca7b/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T194239Z-a5d5ec4c/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T205540Z-f107b705/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T030734Z-cdb08e99/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T065201Z-536b8322/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T135304Z-e29b5362/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T091245Z-9b80b719/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173724Z-cc661419/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T041307Z-8a47cbae/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T063231Z-5f00e106/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T003309Z-76d3a01e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T102725Z-c7a70ddb/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T101250Z-7bfe44a3/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T102123Z-2c548bab/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T104605Z-58d12165/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T192806Z-11b670e9/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T182732Z-76f00001/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T110653Z-7588f92e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T123925Z-836e1ba4/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T035957Z-0b2bf728/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T192803Z-4696069e/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T171834Z-a18e9e07/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T122038Z-7b1471bf/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T075408Z-3745f6c3/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T100832Z-08556249/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173648Z-5c8db483/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T102120Z-e6d42263/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T173434Z-3cceafff/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T140031Z-8492206e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T132927Z-deff911b/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T101640Z-8f116438/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T132656Z-6876543b/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T205537Z-ed85b80a/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T093112Z-b2f3e2f2/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T170233Z-8d09a379/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135452Z-d3f52cd6/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T035957Z-bde560ff/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T100835Z-e0905643/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T132927Z-e775437e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T140649Z-63acd65b/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T100835Z-318ea9b3/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T092812Z-f143d028/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135304Z-4fdd4bb3/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T170317Z-16058ff3/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T194943Z-779c845c/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T110422Z-2fd7d5c7/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T205540Z-d3ffcaf9/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T113518Z-eaa2754e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T123925Z-67834553/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T075016Z-8f9708d1/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171832Z-78002465/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T102527Z-31a18301/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T063231Z-33def31f/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T123922Z-0b0719db/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T195631Z-ea21c708/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T194946Z-808df8a0/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171938Z-b8ba940a/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T025935Z-4eeb717e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T105444Z-92000f8e/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T030730Z-4805f6da/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T061201Z-67a66672/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T113037Z-c3f7e705/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T113518Z-9e651488/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T043836Z-d7c34105/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T135645Z-241045ea/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T104834Z-56c168ba/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T130752Z-dcf0bed5/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T065844Z-a5f06838/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T124127Z-baad349e/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T135454Z-17205699/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T164748Z-75405c07/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T194239Z-533bda56/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T165003Z-e3aafd3c/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T092809Z-e9fcb3f2/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T113040Z-0417451a/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T124259Z-e8eec6b8/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T061357Z-44b2dda4/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T061158Z-694d104a/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260911T105313Z-a5a60b10/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T173651Z-fbd27aba/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T053248Z-4663f404/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T093332Z-25f14fbc/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T102531Z-139ac872/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T090217Z-da61e654/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T195631Z-f4bc4572/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T004940Z-6a223cd8/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T201135Z-d6561725/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T075408Z-a88e3aac/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T201137Z-5e5d3a56/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T105255Z-dfbf7084/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T142821Z-fb63d551/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T142824Z-0563a2d5/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T105313Z-43278430/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171834Z-64a4ebab/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T121831Z-2c84f6d7/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T170317Z-8e9da1fa/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T173651Z-ee6e8ac7/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T184826Z-6644aef8/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T043839Z-0fa7cb34/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T140028Z-53ff8b40/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T041611Z-e310bf85/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T090214Z-511edb4e/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T105258Z-86dc9ce6/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T025932Z-97069e6e/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T093332Z-4ee95552/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171734Z-8204079e/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T025930Z-30733649/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T171936Z-42d0e8d2/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260910T041310Z-74a9c1e0/attempts.jsonl": 2,
  "evidence/selftest/run-20260910T132228Z-c57214ab/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T025930Z-c7deb6ec/attempts.jsonl": 2,
  "evidence/selftest/run-20260909T184436Z-4a39fee2/attempts.jsonl": 2,
  "evidence/selftest/run-20260911T105815Z-3e1b7d10/queued_trials.jsonl": 10,
  "evidence/selftest/run-20260909T164722Z-1d510de4/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171926Z-7ca20b6a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T082448Z-782b6c04/attempts.jsonl": 168,
  "evidence/crypto_regime_timeedge_v2/run-20260909T191844Z-8c6ecf2b/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260910T155528Z-5e208e5f/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171457Z-3c5405ad/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T140933Z-ff2442dc/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184817Z-7194e1d6/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T120451Z-1f5f4f94/attempts.jsonl": 12,
  "evidence/crypto_regime_timeedge_v2/run-20260910T041011Z-3bf06cc9/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105734Z-ce2edff0/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184430Z-518e3d3a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184801Z-93f2a306/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260910T145845Z-e0e5f0ca/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260911T034525Z-5c88b715/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182820Z-41875d98/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171411Z-ddf65d5d/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260911T080838Z-2a1275da/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T200345Z-b9cd4225/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171928Z-545431d9/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T192533Z-275f2d20/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T074338Z-8ac68cbf/attempts.jsonl": 18,
  "evidence/crypto_regime_timeedge_v2/run-20260911T041551Z-e2349922/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171533Z-1e80c36d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173802Z-09cd64ef/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171910Z-3dd566f4/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T031152Z-3e6af996/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T061945Z-5faca448/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T104140Z-e2bc08f6/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T085345Z-3012761f/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260910T151228Z-73b42e8b/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105445Z-aced3384/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184721Z-e9efb01c/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T060820Z-9fb50742/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T041103Z-315d1997/attempts.jsonl": 150,
  "evidence/crypto_regime_timeedge_v2/run-20260910T145028Z-484f90d8/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T104322Z-5d983cf5/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T153422Z-ecb1ae85/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260911T080415Z-50303509/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T060628Z-7ba312c2/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T003239Z-ef36753c/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173800Z-7d33cc5d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T073815Z-658b4831/attempts.jsonl": 20,
  "evidence/crypto_regime_timeedge_v2/run-20260910T041137Z-1c1ec483/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T064117Z-6a2c64be/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T041249Z-b2c969e6/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112732Z-81e9ab16/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T130701Z-cd652c1a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T170041Z-d6f1fcbe/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173802Z-3650e535/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T095433Z-d844328f/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182008Z-44d94460/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T030541Z-4485ea6a/attempts.jsonl": 40,
  "evidence/crypto_regime_timeedge_v2/run-20260910T151943Z-e843b643/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T095128Z-d6d1d107/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T073822Z-ae1d66ee/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T120812Z-64cab435/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173741Z-e9e5f3db/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260911T065721Z-bf6bcce3/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171910Z-119241eb/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061531Z-2f6ab91c/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171929Z-0c84be90/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105525Z-d4785388/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T063531Z-6948372d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T194830Z-f37a8c29/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171929Z-15113e9b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T160313Z-a4b3af66/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061933Z-636da500/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105525Z-852f82dd/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T133707Z-0bb81799/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260911T005241Z-5b68c3c9/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T154842Z-3002edf5/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260911T110858Z-a3d57d73/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T191303Z-134c907e/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260911T035800Z-9817d430/attempts.jsonl": 150,
  "evidence/crypto_regime_timeedge_v2/run-20260910T044943Z-c98cfe08/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T165939Z-c7cd1c3f/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182823Z-a46fcd49/attempts.jsonl": 12,
  "evidence/crypto_regime_timeedge_v2/run-20260910T124116Z-35e14340/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T200349Z-49fd828f/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260910T133639Z-367c0775/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182339Z-f0da35fa/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260911T023742Z-310a112b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T095205Z-b4c8c05d/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T080526Z-2767e849/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T121536Z-8f943693/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T194105Z-e1eccfdb/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112913Z-8a9087b4/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T040719Z-051f65a7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105335Z-d65f720a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T090934Z-3159cef7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061952Z-176382c8/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T130730Z-9a35722d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T165820Z-414c70b8/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T043816Z-170abcea/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142452Z-0226ad82/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T124507Z-a9ec0269/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T090922Z-47e364f6/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T043741Z-8b2990b6/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T061139Z-1b71fa59/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T195720Z-15235282/attempts.jsonl": 12,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061636Z-6a541c7a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T170317Z-83404c00/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T124503Z-4ca22cef/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T201131Z-844a5a05/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260910T060843Z-e5004ea9/attempts.jsonl": 40,
  "evidence/crypto_regime_timeedge_v2/run-20260910T165313Z-cbd097d0/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T025906Z-06ddbe32/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T124135Z-079044f7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T044927Z-a8aefd3f/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T130721Z-621322a1/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171641Z-9c16bb2f/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173758Z-51f2dfda/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T080719Z-a6e63b38/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T080719Z-826fd80a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T170020Z-3abb763e/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061442Z-cdbce9ab/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184757Z-0ebe394b/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260909T200920Z-e1d14977/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173718Z-476a6809/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173352Z-22089465/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182353Z-329007f5/attempts.jsonl": 12,
  "evidence/crypto_regime_timeedge_v2/run-20260909T191603Z-9d7e1b60/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260909T164406Z-0fc281dc/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260910T120355Z-e1e49eba/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260909T192947Z-f7200e03/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105338Z-c8ece877/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T055253Z-0c4e5a73/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T062006Z-02dac67e/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T122247Z-11576adb/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142923Z-33c79ffd/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184814Z-12bacd37/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171830Z-a9ff7202/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T123348Z-1fe865bf/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061041Z-9c969eb7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T064257Z-e2277fba/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T060825Z-7f2e41d5/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T214717Z-4ad96422/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T100641Z-0cb12cc6/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260911T064657Z-8cdd6034/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T055459Z-415eb98b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T100300Z-9828cf8e/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260909T200737Z-1ec020e6/attempts.jsonl": 12,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171639Z-6a82c6c3/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T100722Z-1a51ada2/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T190429Z-1b68a337/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260911T025857Z-9dcf17f5/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T095638Z-ab1e3801/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260911T005239Z-dfaf1603/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T125617Z-0cf1e9bf/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260911T005241Z-e6c86771/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T063913Z-28322b6b/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T103925Z-562f1ebd/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112554Z-f779db4a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T161057Z-e5b3909b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T042115Z-1124f03b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T123729Z-65c615ff/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112509Z-7a0c3aaa/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T094420Z-c60cbfeb/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T164816Z-506645c3/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T115825Z-75d5a47d/attempts.jsonl": 14,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173745Z-e1964503/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260911T004909Z-1a7757e8/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T130422Z-4d6a0367/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260910T214702Z-6da15cb1/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T104303Z-3d01577b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T075012Z-f425c839/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T055546Z-9156bf82/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T062301Z-2fef9d35/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260909T191058Z-a8c1d360/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260910T074007Z-c02d4064/attempts.jsonl": 164,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142922Z-d31a1de7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T030302Z-689dfddc/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T125510Z-cf0fe747/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260910T100448Z-f2b77fe8/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260911T063016Z-b8f7bafd/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T125846Z-88cae4b2/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260909T164520Z-844efbdb/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T054520Z-9e8bbe4c/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T145129Z-1139c7cc/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260911T042530Z-cb1dae1b/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112813Z-3019ea13/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105323Z-5fcb6b93/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T073809Z-50ffd78b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T164817Z-36027a6a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T064435Z-06ba4c92/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184817Z-692eb9a4/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173745Z-e89c6700/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260910T165008Z-52168067/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T073535Z-7d1f0950/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142857Z-3aa0b1e8/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T062056Z-f1658a48/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T030158Z-586bc90f/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T162225Z-96a8fa9d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T073937Z-9800e9b7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T040431Z-ee70e961/attempts.jsonl": 150,
  "evidence/crypto_regime_timeedge_v2/run-20260910T080521Z-7875b489/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T041742Z-1de3fe64/attempts.jsonl": 150,
  "evidence/crypto_regime_timeedge_v2/run-20260910T080549Z-0f3720ba/attempts.jsonl": 164,
  "evidence/crypto_regime_timeedge_v2/run-20260911T055217Z-8faab201/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T071801Z-526462fc/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142239Z-d6527c20/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T062225Z-2cc23803/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T025841Z-2a59754a/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171914Z-3c96e1e8/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260910T080539Z-db2b4009/attempts.jsonl": 20,
  "evidence/crypto_regime_timeedge_v2/run-20260911T024948Z-8cc3d764/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T164431Z-f5644fc9/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T044907Z-8bd74375/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184716Z-42b4f9c7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T102842Z-37459a17/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T003218Z-ca029f87/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T005212Z-be1eff8d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T121031Z-5739ebe6/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061558Z-5043717d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105349Z-9607506e/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T095959Z-7fbca200/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T054141Z-85b43e23/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T065201Z-6b029719/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112628Z-08654dcf/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260911T064831Z-c3b7164f/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105537Z-520fc39a/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T025642Z-fb852a02/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260911T035202Z-cf5f807d/attempts.jsonl": 150,
  "evidence/crypto_regime_timeedge_v2/run-20260909T195038Z-5c977e09/attempts.jsonl": 12,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184802Z-82c5a408/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260909T164630Z-05b732c1/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T041108Z-9afc84d0/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184315Z-ef4c4ff3/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184758Z-5c2c862a/attempts.jsonl": 10,
  "evidence/crypto_regime_timeedge_v2/run-20260910T150523Z-37c2d06e/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112459Z-bf1d685c/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T123556Z-062146f5/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061215Z-6dadcb19/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112519Z-2abe7b49/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171607Z-3f55b5b9/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184815Z-960f9105/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260911T023840Z-a1817d0c/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T140909Z-8ec87752/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182758Z-fa290a01/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T061456Z-287d9e92/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T122902Z-8048e687/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142528Z-d2cd273f/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T194623Z-b53d823f/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T070406Z-634ae674/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T170307Z-16fac3e2/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T075229Z-e7218a07/attempts.jsonl": 20,
  "evidence/crypto_regime_timeedge_v2/run-20260910T041212Z-21487214/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T062731Z-0c6e5277/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105523Z-f9281b41/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T031030Z-3b904bb6/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182819Z-1510d179/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T080347Z-0f994a2f/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173306Z-e63972b7/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171913Z-e833592b/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260910T133238Z-c6ce9b21/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112535Z-e001cf8b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061716Z-cc3d6ebb/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T041132Z-affcfd5e/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T084316Z-4cd068f9/attempts.jsonl": 170,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184721Z-b9f323ab/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T061959Z-f114cb2b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184815Z-c7f3f52d/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T171339Z-415413e3/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260910T060733Z-94a32191/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173800Z-ee1b1022/attempts.jsonl": 4,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142924Z-8284385c/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T025830Z-91036c3b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T060951Z-0fb328f5/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T124204Z-386e5335/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T061318Z-e9b40889/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T004909Z-6f507df5/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T173741Z-c1c330db/attempts.jsonl": 8,
  "evidence/crypto_regime_timeedge_v2/run-20260911T105652Z-1c786c06/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260910T120600Z-02130c64/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260911T064546Z-5d22a0cc/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T142318Z-5c26fef7/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T040836Z-7795570e/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T110847Z-57e31aef/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T184724Z-76ac1ff4/attempts.jsonl": 16,
  "evidence/crypto_regime_timeedge_v2/run-20260910T184325Z-7fa062cb/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T005236Z-f8d390d9/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T112757Z-3a18447b/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T165140Z-13d8e0f4/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260909T201224Z-2f185d7c/attempts.jsonl": 6,
  "evidence/crypto_regime_timeedge_v2/run-20260909T182815Z-35116262/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T124035Z-dc993e92/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260911T064257Z-d812ea54/attempts.jsonl": 2,
  "evidence/crypto_regime_timeedge_v2/run-20260910T154151Z-8e20816c/attempts.jsonl": 170
}
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B18 — `audit_bundle_manifest.json`

Original bytes: **3,366**; SHA-256: `4fdc2b11ac155ec3ec9d4a27875a0cb59ef3b59fa5bbdaf4d31493c49cea7742`. Nội dung gốc, đọc trực tiếp bên dưới.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/audit_bundle_manifest.json","bytes":3366,"sha256":"4fdc2b11ac155ec3ec9d4a27875a0cb59ef3b59fa5bbdaf4d31493c49cea7742","encoding":"utf8"} -->
````json
{
  "archive_sha256": "2765bd069a5caf16921c3df03dfafd8f090f4fdd2de5e1550a5ce390c87a980f",
  "scope": "actual source/artifact audit + 12 synthetic/reference probes; no full market rerun",
  "files": [
    {
      "path": "README.md",
      "bytes": 2153,
      "sha256": "89bf2a89d2ea53bee16cd1f27badbd28e5cf31089aa8ccaa5701284288de5eb8"
    },
    {
      "path": "REGIME_LAB_ACTUAL_SOURCE_AUDIT_VI.md",
      "bytes": 48893,
      "sha256": "6c7695461be6f3f32c7606349325cf74ff934a9ce1548df32d5e18184fc32373"
    },
    {
      "path": "REGIME_LAB_SOURCE_EXCERPTS_VI.md",
      "bytes": 118676,
      "sha256": "7909dd54724e0bcc2d7f35eea136797446a5612415deffb69b7bc93180c9c614"
    },
    {
      "path": "additional_probe_results.json",
      "bytes": 1484,
      "sha256": "e41a4891d23ffbc3c1f84dad55cb5bfdb1b701bfa033dfbbdabfc6054c4b8930"
    },
    {
      "path": "additional_probes.log",
      "bytes": 1134,
      "sha256": "c43dea98ba289b41a3e40eedb1f8102b74997fe1d53f35eefecb429f42adad25"
    },
    {
      "path": "additional_probes.py",
      "bytes": 4262,
      "sha256": "2424611cdc8e2b2cb4f77d52d64a77e652cd5ada5fcd4d45ba17b64dae9842a9"
    },
    {
      "path": "archive_inventory.json",
      "bytes": 412980,
      "sha256": "6c2e696f30c3efa8378a038f0c4f1c49e2ef9704896124e0bdd5c45bd6da224f"
    },
    {
      "path": "artifact_index.json",
      "bytes": 660500,
      "sha256": "09ce26c55b30c2a9dd716c8ad170b9a84fe08f27a373eb5368eca14f72d2d813"
    },
    {
      "path": "audit_bundle_manifest.json",
      "bytes": 3205,
      "sha256": "e92911e394b07717ced9953c2c9f169d8f00a6c3ddcb2e1d8ff6cd1e4c7e77b3"
    },
    {
      "path": "audit_evidence.py",
      "bytes": 3902,
      "sha256": "4b7f5b4e5488594e358c01fe7adc6ceee3ac2e001ef779bd807c92e4f505d44a"
    },
    {
      "path": "audit_probe_results.json",
      "bytes": 3695,
      "sha256": "bd03eff7001a8cfd69b06cf7deb442063851611fdda5fbf01110020422a66667"
    },
    {
      "path": "audit_probes.log",
      "bytes": 1919,
      "sha256": "0c4c6fdf644665df9eb16622b2e679bc30a6eea8c6ec89707c9e0256bee41475"
    },
    {
      "path": "audit_probes.py",
      "bytes": 6887,
      "sha256": "05c7c3552936cb1c285d872accd04a36ddc09de92b85a73cd2d39536e170b60e"
    },
    {
      "path": "evidence_reanalysis.json",
      "bytes": 79726,
      "sha256": "789cb49419cbb0f0bc7bf56326494f1ebdf77af9f2db7e0bd63031bf66b76c82"
    },
    {
      "path": "evidence_reanalysis.log",
      "bytes": 4187,
      "sha256": "97f413803259d94541e91d9705b58b6f5347a6b2ee36306a04d74e75c2cd6c04"
    },
    {
      "path": "jsonl_row_counts.json",
      "bytes": 46061,
      "sha256": "6272488e0b7d9a06d3e1d3f780e48f3e26d10280b15ca401b6ea28aeac0dd05c"
    },
    {
      "path": "pytest_subset.log",
      "bytes": 19794,
      "sha256": "9925e83b7cde5618b03474548bae795ca11029a41329b9beb0d7d6213c91795c"
    },
    {
      "path": "source_excerpt_manifest.json",
      "bytes": 5666,
      "sha256": "0d09ce5c384a55e81bb8bf5e762a82a966d3001aa3cc41f43ad5f7c98a86b998"
    },
    {
      "path": "transition_audit.json",
      "bytes": 24890,
      "sha256": "408e91be67f1c6559424c0f3dd08d8bb83573b543d73b6f73adc866ca7c1e4fb"
    },
    {
      "path": "trigger_eligibility_audit.json",
      "bytes": 12536,
      "sha256": "385345857f4c001866b5649902fc148b5f0f474e14e3b764efda9e30d33b66da"
    }
  ]
}
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B19 — `archive_inventory.json`

Original bytes: **412,980**; SHA-256: `6c2e696f30c3efa8378a038f0c4f1c49e2ef9704896124e0bdd5c45bd6da224f`. JSON inventory nén lossless; khôi phục bằng utility phía trên.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/archive_inventory.json","bytes":412980,"sha256":"6c2e696f30c3efa8378a038f0c4f1c49e2ef9704896124e0bdd5c45bd6da224f","encoding":"zlib+base64"} -->
````text
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
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

## B20 — `artifact_index.json`

Original bytes: **660,500**; SHA-256: `09ce26c55b30c2a9dd716c8ad170b9a84fe08f27a373eb5368eca14f72d2d813`. JSON inventory nén lossless; khôi phục bằng utility phía trên.

<details>
<summary>Mở evidence lịch sử — không phải kết quả repaired experiment</summary>

<!-- AUDIT_MEMBER_V1 {"path":"regime_lab_audit/artifact_index.json","bytes":660500,"sha256":"09ce26c55b30c2a9dd716c8ad170b9a84fe08f27a373eb5368eca14f72d2d813","encoding":"zlib+base64"} -->
````text
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
fgOzQVwspvxVGK/vuJ4tL8///td//ef/Aa0rxUI=
````
<!-- AUDIT_MEMBER_END_V1 -->

</details>

---

# Kết thúc tài liệu hợp nhất

**Nhiệm vụ hiện tại chỉ có RF-01…RF-05.** Các code, số liệu và plans trong phụ lục là evidence cũ được bảo toàn, không tự cấp kết luận mới. Ưu tiên: sửa actual execution và Mode 4 baseline → regime timing hợp lệ → kiểm bằng alpha thật trên QuantBT nhanh nhất có cùng semantics → báo metrics/decay/uncertainty đầy đủ → kết luận trung thực theo scope.
