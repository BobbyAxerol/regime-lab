# REGIME-LAB — BTCUSDT REGIME PARAMETER SELECTION V1
## Model-first V1.2: dữ liệu Binance → thời lượng regime → dự báo 56/90 ngày → qualification → mới mở lại WFO

**Phiên bản:** `BTC-RPS-V1.2 / MODEL-FIRST + REGIME DURATION`  
**Ngày cập nhật:** 28/09/2026  
**Thay thế nội dung triển khai hiện hành của:** `BTC-RPS-V1.1 / MODEL-FIRST`, ngày 27/09/2026; bản cũ giữ nguyên.
**Parent document SHA-256:** `79953c650bb39197154679f3b3ba6c6a6219eed95c3b536dffd40e8acbf664ce`.  
**Repository:** `BobbyAxerol/regime-lab`  
**Study mới:** `btc_regime_forecast_v1`; implementation phases `MF-01` → `MF-05`, đúng năm phase.  
**Phạm vi:** BTC trên Binance; alpha/WFO sau này vẫn `A-SC / BTCUSDT / 15m`.  
**Trạng thái:** đặc tả nghiên cứu và giao việc, chưa có model mới được fit/benchmark, chưa có forecast-skill certificate và chưa chạy WFO mới.

> **Quyết định chính:** LightGBM supervised làm ứng viên chính; Chronos-2-Synth frozen là challenger. **56 và90 ngày là hai horizon ứng viên; chưa mặc định horizon nào tối ưu.** Đo duration của observed regimes riêng, chọn H* bằng development trước TEST và qualification riêng từng head/horizon. Bỏ forecast180 khỏi active roster; lookback180 và candidate-IS180 không vì thế bị xóa. Chưa mở lại Sharpe-decay WFO.
>
> **Nguồn ngoài không đủ lịch sử thì bỏ khỏi V1**, không chặn triển khai, không chờ thu thêm nhiều năm, không mua gói trả phí, không fill lịch sử giả. Binance price/volume là nền bắt buộc; OI/ratios/funding/premium được thêm theo coverage thực. Optional source bị loại có record và lý do, không trở thành một project phụ.
>
> **Không biến lựa chọn cá nhân thành chu kỳ thị trường.** 56/90 là menu nghiên cứu hữu hạn, không phải mean duration đã đo của BTC. Báo riêng duration distribution, age hiện tại, first-exit risk và remaining time khi đủ support. Horizon tốt để forecast không nhất thiết bằng mean duration, và forecast dài hơn không tự chính xác hơn.
>
> **Giữ tối thiểu 12 temporal evaluation blocks cho mỗi comparison chính.** Ở model forecasting, block là nhóm forecast origins, không phải 12 independent 56/90-day paths. Nhãn dài hạn có thể chồng lấn; phải purge theo maturity và xử lý dependence. Phép kiểm định WFO sau này vẫn có registration, 128 trials/cutoff và ít nhất 12 paired-valid folds riêng; không mượn counts của model để cấp chứng nhận WFO.

---

## Điều hướng

[0. Nguồn và migration](#s0) · [1. Scope và horizon](#s1) · [2. Rules](#s2) · [3. Dữ liệu](#s3) · [4. Feature engineering](#s4) · [4D. Regime duration, survival và horizon](#s4-duration) · [5. Targets và labels](#s5) · [6. Timeline/causality](#s6) · [7. Models/parameters](#s7) · [8. Selection và calibration](#s8) · [9. Evaluation/qualification](#s9) · [10. Output/live forecast](#s10) · [11. Compute/codebase](#s11) · [12–16. Năm phase](#s12) · [17. Evidence và upgrades](#s17) · [18. WFO bridge đang khóa](#s18) · [19. Config/acceptance](#s19) · [20. Nguồn](#s20).

<a id="s0"></a>
## 0. Nguồn, phạm vi bằng chứng và migration

### 0.1. Đây là bản cập nhật trực tiếp của guide gần nhất

File này hợp nhất các thảo luận mới về data/model/labels/horizon vào guide V1, không phải addon phải ghép thủ công. Bản V1.0 và evidence lịch sử giữ nguyên; không sửa old receipts hoặc kết luận cũ thành PASS.

Nguồn nội bộ:

- **[I1]** `CONSUMER_ENDPOINTS.md`: authority về approved **readers**, schema và coverage snapshot ngày 09/09/2026. Không cấp quyền writer/backfill vào canonical lake. SHA-256 bản nhận được: `5771710a55189c5c4f7a900f3ab8c06eeccfd09ffc1d8693bb681724d62c3df1`.
- **[I2]** Guide `REGIME_LAB_BTCUSDT_REGIME_PARAMETER_SELECTION_V1_5_PHASE_GUIDE_VI.md`, V1.0; SHA-256 bản được cập nhật: `ed8328a8f78dc05872b6a20309c3517960ce2a9c9a338a07e3686a7acda9f0c6`.
- **[I3]** `REGIME_LAB_SD01_SD03_OBJECTIVE_REVIEW_VI.md`: audit snapshot SD, không chứng nhận current HEAD. Archive lịch sử được audit có SHA-256 `7f0f639b82c9fd66ce5e367c8b08922bdc686cff8756cb9ff584459c47356d32`.
- **[E1–E10]** Tài liệu/papers chính thức tại §20, hỗ trợ lựa chọn phương pháp và giới hạn capabilities. Những defaults nghiên cứu trong guide là quyết định thiết kế đề xuất, không phải kết quả đã chứng minh của các nguồn đó.

Không có live-server check hoặc code execution mới được thực hiện để ban hành guide. Agent phải map current source/runtime trên host; code đã sửa đúng thì reuse evidence, không khôi phục source cũ đè lên.

### 0.2. Thứ tự hiệu lực

Chỉ dẫn mới của Bobby → V1.2 trong phạm vi model-first → safety/data/economic contracts đã xác minh → registration của từng run → tài liệu lịch sử không mâu thuẫn.

### 0.3. Bảng migration bắt buộc

| Bản trước (V1.0/V1.1) | V1.2 hiện hành | Cách giữ lịch sử |
|---|---|---|
| Chạy ma trận samplers × JM/HMM/context rồi test WFO | Qualification forecast model trước; WFO đóng | Không gọi old RPS đã hoàn thành chỉ vì MF xong |
| Primary Sharpe decay ngay trong mọi phase | Primary forecast quality của regime; Sharpe decay giữ ở WFO bridge | Không đổi old return/Sharpe label thành regime label bằng rename |
| V1.1 chọn H90 chính, H180 phụ | V1.2 so H56/H90, H* chọn trên development; bỏ active H180 | Targets/recipes mới, không rename old labels hoặc chọn lại sau TEST |
| Chưa có empirical timing study | Observed-state tape độc lập H, episode survival và remaining-time diagnostics | Ghi measurement definition, censoring và support; không suy duration từ runs của forward labels |
| JM/hard states là lớp model chính | Supervised targets độc lập với model; LightGBM + một Chronos challenger | JM/HMM chỉ reference, không dùng làm ground truth |
| Nguồn ngoài có thể mở thêm | Không đủ historical/free-use/availability thì exclude trước fit | Không để CoinGecko, options, L2 làm chặn core |
| 12 INIT + 12 VAL + 12 FINAL cho candidate/WFO archive | Model fit từ historical daily labels; >=12 VAL blocks + >=12 TEST blocks | Không đòi tạo QuantBT candidate archive trong model-only phases |
| 128 optimizer trials/cutoff | Vẫn giữ cho WFO sau này; model hyperparameter roster nhỏ | Không tự mở 128 ML configs/head |
| Model forecast tốt được coi gần live | Forecast replayable khác WFO edge khác live trading certification | Ba trạng thái qualification tách riêng |

Đúng năm phase MF của bản mới thay công việc hiện hành; các nội dung WFO cũ được bảo toàn ở §18, **không tự động thực thi**.

<a id="s1"></a>
## 1. Horizon là giả thuyết cần kiểm tra, không phải chu kỳ biết trước

### 1.1. Hai ứng viên H56/H90

Bobby điều chỉnh phạm vi về **56 hoặc90 ngày**. Guide không chọn lại một số bằng trực giác: nghiên cứu hai horizons trên cùng cohort, kèm empirical regime-duration analysis, rồi khóa `selected_horizon_days` trước TEST. H180 không còn là forecast task; các lookbacks180 ngày hoặc candidate-IS180 là biến khác, vẫn giữ nếu feature/financial contract cần.

| Quyết định | V1.2 |
|---|---|
| Candidate horizons | `[56, 90]` calendar days |
| Primary horizon trước validation | `UNSELECTED`; không mặc định90 |
| Primary H* trước locked TEST | Chọn theo §8.4 từ validation, duration interpretation và measured cost |
| Secondary | Horizon còn lại, báo riêng; không cứu primary thất bại bằng đổi nhãn |
| Market observations | Daily UTC, từ completed 1m/5m/15m bars |
| Official forecast origins | Mỗi7 ngày tại UTC cutoff cố định |
| Evaluation block | 28 ngày chứa4 weekly origins; không là độ dài regime |
| Model refit | Mỗi28 ngày, chỉ labels đã mature |
| Duration tape | Daily observed states riêng theo §4D, không phụ thuộc H56/H90 |
| Alpha về sau | A-SC/BTCUSDT/15m, WFO vẫn đóng |

Chọn H bằng **skill so với baseline của chính H**, không so raw MAE/accuracy qua hai bài toán rồi gọi H có số dễ hơn là tốt hơn. Mean/median regime duration là context để hiểu horizon, không một công thức H=meanL. Hai prediction windows đều có thể chứa nhiều state transitions.

### 1.2. Thứ tự học timing và chọn horizon

```text
Feature engineering → observed-state/episode ledger chỉ từ past
→ duration/survival summaries trên training prefix
→ fit/validation H56 và H90 trên cùng origins
→ chọn recipe mỗi H và chọn H* trước TEST
→ locked TEST cả hai H + timing diagnostics riêng
→ qualification theo head/H; owner mới quyết định WFO.
```

Duration study không cần đợi LightGBM fit xong; có thể đo lịch sử từ defined observed states ngay sau features. Sau model evaluation mới biết **forecasted regime/timing** có skill không. Retrospective duration plots có thể thêm cho TEST sau khi kết thúc nhưng không quay về chọn detector/H* hoặc sửa training features của các decisions trước đó.

### 1.3. Ba điều không được đánh đồng

- Regime hiện tại được nhận diện từ trailing observations khác target “đặc điểm trung bình của 56/90 ngày tương lai”.
- Regime thường dài70 ngày (nếu sau này thật sự đo được) không có nghĩa hôm nay nó còn70 ngày, hoặc chắc chắn còn70−age ngày.
- Dwell length khác recurrence cycle; một state quay lại không chứng minh thị trường có chu kỳ tuần hoàn đều.

Không công bố thời lượng BTC cụ thể khi chưa đo. Forecast skill, duration forecast skill và parameter-selection Sharpe edge là ba qualifications khác nhau. Nguồn ngoài thiếu historical vẫn bị exclude; không kéo thêm collector/model families chỉ để có duration table đẹp.

<a id="s2"></a>
## 2. Rules bắt buộc, chỉ giữ checks có ảnh hưởng thực

### 2.1. Scope, source và permissions

**R01.** Binance/BTC-only. Spot/perpetual BTC dùng làm input khác nhau; không đổi loại instrument đang giao dịch. OKX, Bybit, altcoins, news/NLP, options-surface, raw-L2 project mới ngoài V1.2.

**R02.** Chỉ import approved `data_loader`, explicit symbol, `check_val=True`. Không override `DATA_ROOT`, không đọc thẳng `storage/` để bypass manifest [I1].

**R03.** Contract reader không cấp quyền canonical writer/collector. Funding/premium mới chỉ tải vào research staging được phép; nếu cần sửa lake phải request riêng. Không fake một loader class chưa được công bố.

**R04.** Nguồn external thiếu lịch sử/điều kiện sử dụng/temporal provenance thì `EXCLUDED_*` và tiếp tục. Không mua data, scraping workaround hoặc mở collector chỉ để chờ đủ lịch sử. Nguồn cần cho target BTC price mà thiếu thật thì mới chặn phép thử tương ứng.

**R05.** Crypto naive timestamps là UTC theo contract; không tự cộng/trừ 7 giờ. Lưu riêng event time, close/sample time, available time và ingest time. Ingest hôm nay không tự là publication time lịch sử.

**R06.** Không reset/clean worktree, không xóa untracked evidence, không `git add .`. Commit scoped, không push/merge nếu chưa được phép. Không áp workflow Portal vào lab.

**R07.** Không sửa sibling QuantBT, production environment/services, original alphas hoặc immutable snapshots. Hạ tầng host thật và resource allocation là authority.

### 2.2. Data/model validity

**R08.** Features chỉ từ available past. Candidate-free model không có lý do đọc labels chưa mature. Thay future suffix không được đổi earlier prediction.

**R09.** Daily target chỉ dùng future observations thực của đúng H, không nhầm trailing overlapping target ở T+1 với toàn window tương lai.

**R10.** Labels, scalers, thresholds, clipping, feature selection, calibrator đều fit bằng permitted data của role tương ứng. Không full-sample quantiles/normalization.

**R11.** Không random split các origins có outcomes chồng lấn. Train end được lọc bằng `label_available_at`, không chỉ row timestamp.

**R12.** Missing/null khác zero. Không fill OI/ratios direct-source gaps; không extrapolate một tháng REST về nhiều năm. Không sum stocks như OI thành flow.

**R13.** Class labels không đến từ chính JM/HMM đang được chấm; không tối ưu labels để accuracy đẹp. Giữ fixed label ontology/version cho toàn validation và test.

**R14.** Foundation checkpoint phải pin weights/config/tokenizer/preprocessing và provenance. Synthetic-only không đồng nghĩa hoàn toàn hết selection/benchmark contamination.

**R15.** Forecast batch giữa origins phải isolated. Không grouping origin tương lai với origin quá khứ để cross-learn; chỉ group các biến BTC cùng cutoff.

**R16.** Funding/OI/volume future không phải known future covariates. Quantiles từng biến không tự là joint regime distribution.

**R17.** Forecast values xác suất phải có calibration status, target/horizon, data watermark và model vintage. Không gọi cost gap của JM là calibrated probability.

### 2.3. Evaluation và owner control

**R18.** Mỗi comparison chính >=12 temporal blocks chung. 48 weekly origins với H56/H90 không phải 48 independent regimes; 12 blocks cũng không là12 independent H-day paths. Episodes và risk-set support phải báo riêng.

**R19.** Menu H56/H90 khóa trước validation; H* chọn bằng frozen development rule và khóa trước TEST. Không reselect H bằng TEST duration/score, không lấy secondary cứu primary. Exclusions nguồn theo coverage trước outcome.

**R20.** Accuracy/high hit rate phải so baseline, class support, coverage và false alarms. Abstention không cho phép xóa những dự báo sai khỏi denominator toàn policy.

**R21.** Technical PASS khác model-skill PASS. CI rộng là low precision, không mặc định no-skill; dataset/model invalid không được kết luận scientific null.

**R22.** Không cần QuantBT chạy bulk để xây targets market. Trong năm phase mặc định `new_financial_engine_runs=0`; model forecast qualification trước, WFO chờ owner.

**R23.** Mỗi attempt/upgrade có raw refs, config/source hashes, measured resource và report mới. Không overwrite history; sửa narrative bằng correction record.

**R24.** Test/gate kiểm actual behavior, hashes, boolean values, maturity, prediction independence. Không đếm file/tìm chữ PASS làm chứng nhận.

**R25.** Sau phase: verify → report → scoped commit → `WAITING_OWNER_REVIEW`. Auto-advance chỉ khi có authorization thật được reference.

**R26.** Không hứa accuracy, wall time hoặc speedup chưa đo. Không tăng quota/model families nếu kết quả yếu.

**R27.** Forecast live-replayable không cấp phép trade. Không đặt keys/orders/cron vào production; các exits/risk/governance hiện tại không bị thay.

**R28.** BTC-only là scope để kiểm cơ chế và chi phí, không phải định lý “BTC không có ⇒ mọi thị trường không có”.

**R29.** Không suy empirical regime lifetime từ runs của overlapping future-H labels hoặc forecasts. Observed duration có definition/tape riêng, không đổi theo H.

**R30.** Episode còn sống ở fit cutoff là censored theo cutoff đó; không expose future exit. Unknown onset/data gap/taxonomy reset phải có status riêng, không fake completed runs.

**R31.** Mean duration không bằng remaining duration. Không tuyên bố còn mean−age ngày; probability survival/exit cần risk-set support và calibration đúng scope.

**R32.** Detector lookback/hysteresis làm thay duration estimate; phải report definition sensitivity, không tune cho mean gần56/90.

**R33.** Main forecast qualification không tự chứng nhận duration forecast. Sparse timing evidence không chặn core computations, nhưng timing-based trading claim vẫn đóng.

**R34.** Cập nhật duration age hằng ngày không tự thay forecast target window, sampler, params hoặc lịch WFO. Mọi dynamic-timing policy là nghiên cứu riêng sau qualification.

**R35.** New detector/label/H version không overwrite old state/episode/forecast records. Giữ source lineage và điều gì đã được biết tại mỗi cutoff.

<a id="s3"></a>
## 3. Data sources: use / exclude, không tạo blocker từ nguồn phụ

### 3.1. Core và priority

| Nhóm | Reader/nguồn | Tình trạng theo nguồn | V1.2 xử lý |
|---|---|---|---|
| BTC spot 1m full | `CryptoBinanceSpot1m` | Released; coverage snapshot từ 2018-01-01 [I1] | Price reference mặc định và flow; primary sample không trước 2020 nếu chưa được cho phép |
| BTC USD-M perp 1m full | `CryptoBinance1m` | Released; BTC từ 2020-01-01 [I1] | Perp context; không gọi loader này là spot |
| OI/ratios 5m | `BinanceFuturesMetrics5m` | BTC từ 2020-09-01; nullable fields [I1] | Enrichment ưu tiên; qualify theo từng field |
| Funding đã công bố | Binance `/fapi/v1/fundingRate` | Official REST, chưa có shared-reader riêng trong [I1] | Research staging chỉ khi có quyền, đủ lịch sử free và event semantics |
| Premium/mark/index | Binance premium/index/mark klines | Official REST/archive cần kiểm coverage [E2] | Enrichment có điều kiện; không dùng ignore columns làm volume |
| BTC market-cap dominance | CoinGecko hoặc file historical licensed sẵn có | API lịch sử dài không mặc định miễn phí [E3] | Nếu không phủ cohort thì loại; không block core |
| Binance BTCDOM | Chỉ số relative price strength, không market-cap dominance | Coverage và definition phải kiểm riêng | Mặc định OFF; không surrogate dominance bằng rename |
| Fear & Greed / DVOL / on-chain | External supplemental | Không cần để hoàn tất core | Mặc định OFF; chỉ giữ nếu dataset đã có và đủ timeline trước freeze |
| Order book / options | Released/frozen hoặc lịch sử ngắn hơn | Order book từ 2023; Deribit không live tail [I1] | Ngoài core V1.2; không mở raw L2/options work |

Coverage trong [I1] là snapshot ngày 09/09/2026, không xác nhận latest tail/freshness. Một source “released” chỉ chứng minh reader được phép đọc.

### 3.2. Core source disposition algorithm

1. Chốt target/reference price là **Binance BTCUSDT spot** cho model market-conditions, trừ migration rõ được duyệt trước fit. Perp vẫn là input. Việc này không tự đổi instrument của A-SC khi mở WFO.
2. Kiểm bounded samples, actual first/last timestamps và missingness từ existing approved dataset/manifest.
3. Lập base timeline chỉ từ target và price/flow inputs có lịch sử đủ. Không chọn dates theo PnL/accuracy.
4. Với enrichment/external source: kiểm nó phủ toàn required feature history, training, validation, calibration, test origins và live-like update contract của cohort hay không.
5. Nếu không đủ: `EXCLUDED_INSUFFICIENT_HISTORY`, `EXCLUDED_LICENSE`, `EXCLUDED_NO_PIT`, `EXCLUDED_COST` hoặc `EXCLUDED_UNAVAILABLE`. Remove field group trước fit; không đặt cột toàn NaN để model đoán “nguồn chưa tồn tại”.
6. Nếu chỉ một vài nullable vendor fields có gaps, có thể giữ đúng missing values nếu coverage rule đã đạt; source thiếu toàn bộ các năm không phải loại gaps này.
7. Chỉ fail core khi target/mandatory price data không đủ hoặc sai. Thiếu CoinGecko không là failure của MF-01.

Không tự cắt toàn study ngắn lại để chứa optional source. Không chạy thêm một study ngắn “chứng minh dominance” trong V1.2. Tối đa một nguồn external đủ điều kiện được thêm bằng pre-fit roster; mặc định không có.

### 3.3. Định nghĩa dominance và flow phải trung thực

\[
D_t^{BTC}=MarketCap_{BTC,t}/MarketCap_{Crypto,t}.
\]

Dominance tăng có thể do altcoins giảm; nó không trực tiếp đo net inflows BTC. Nếu đủ historical licensed data, features đề xuất là level/past percentile và changes 30/90 ngày; không chỉ có BTC market cap mà bịa global denominator. CoinGecko public historical access được công bố giới hạn 365 ngày; global market-cap history là endpoint Pro [E3]. Nếu như vậy không đủ timeline thì exclude ngay.

Quote volume của BTCUSDT là turnover tính theo USDT, không “quota tiền nạp”. Taker-buy measures aggressor side, không institutional identity. OI là open-position stock với cả long và short, không phải tiền long mới. Long/short account ratios và position ratios khác nhau; bốn ratio columns của shared reader phải được map từ schema thực, không đoán từ tên.

### 3.4. API/free acquisition registry, không fictitious loader calls

Các endpoint để qualification khi cần, không phải yêu cầu download tất cả:

```text
Binance existing public archive: klines, trades, aggTrades khi đã có nhu cầu cụ thể
GET /fapi/v1/fundingRate
GET /fapi/v1/fundingInfo
GET /fapi/v1/premiumIndexKlines
GET /fapi/v1/markPriceKlines
GET /fapi/v1/indexPriceKlines
GET /futures/data/openInterestHist
GET /futures/data/globalLongShortAccountRatio
GET /futures/data/topLongShortAccountRatio
GET /futures/data/topLongShortPositionRatio
```

Latest REST OI/ratios có retention ngắn; không hứa REST backfill từ 2020 [E2]. Tận dụng lake lịch sử đã có. Authentication/rate limits/response schema phải pin theo docs và samples thực; secrets không vào evidence. Funding schedule có thể đổi, không hardcode 3 events/day cho toàn history.

Dữ liệu Binance public có checksums và updates; Spot archive từ 2025 có thay đổi timestamp unit cần xử lý theo version thực [E1]. Reader approved là ưu tiên, không tải một bản raw khác rồi đổi nguồn không báo.

### 3.5. Aggregate đúng và provenance

- OHLC: first/max/min/last; volumes và trade counts: sum trong interval.
- Taker ratios: ratio của aggregate numerator/denominator, không mean các ratios không weight.
- OI: last available observation trước boundary, hoặc mean mức trong ngày nếu feature định nghĩa như vậy; **không sum OI snapshots**.
- Ratios: aggregate ở log-ratio/last tùy feature spec; account vs position fields giữ riêng.
- Funding: sum các **published settlements** nằm trong past interval; last rate chỉ là last rate, không lịch sử continuous rate tự forward-fill.
- Premium mean/std: dùng observed samples với coverage đủ; mark/index price fields không phải trade volume.
- Nếu interval gap: không chế tạo bar; target H ngày thiếu price/RV thì invalid target, không silently giảm H.
- Source substitution/proxy spot từ perp nếu tồn tại phải flag; không dùng đoạn hai series là bản sao để kết luận spot–perp đồng thuận.

### 3.6. Hai servers

Server mới: approved reader → bounded monthly reads → daily feature/raw-reference research export vào đường được phép. Server cũ: nhận immutable snapshot + manifest để fit/test models.

Không mang toàn options tape hoặc `.venv` giữa servers. Snapshot phải chứa source hashes, schema/unit/version, time conventions, masks, field coverage và checksums. Không viết canonical Parquet từ consumer. Các hàm endpoint đã có trong [I1]; tên mới cho funding staging là code cần triển khai, không capability đã released.

<a id="s4"></a>
## 4. Feature engineering: có cơ chế, ít chiều, đa scales

### 4.1. Thang thời gian

Primary features gồm scales 7/30/56/90 ngày; một số fast flow 1 ngày chỉ là context phụ. Không nhân tất cả 48 features với bốn horizons. Dữ liệu 5m giúp ước lượng realized variation/distribution; representation model là daily. Một fast feature được thêm không biến target thành dự báo intraday.

Target price reference mặc định spot. Daily close và RV của target không trộn mark price hay perp price. Inputs perp có prefix `perp_`; official premium có prefix `official_premium_`, khác `perp_spot_spread`.

### 4.2. Công thức lõi

Với daily log return \(r_d=\log C_d-\log C_{d-1}\), intraday 5m log returns \(r_{d,i}\):

\[
RV_d=\sum_{i=1}^{288}r_{d,i}^2,\qquad
RVOL_h(t)=\sqrt{\frac{365}{h}\sum_{d=t-h+1}^{t}RV_d}.
\]

Có preceding close đúng ở ngày đầu; thiếu 5m observations thì quality flag. Primary target-RV day mặc định cần đầy đủ observations theo canonical bars; không nhân lên để giả đủ coverage. Data gaps phải được giải quyết ở approved source, không smoothing để lấy target đẹp.

\[
PE_h(t)=\frac{\sum_{d=t-h+1}^{t}r_d}{\sum_{d=t-h+1}^{t}|r_d|},\qquad
DownShare_h(t)=\frac{\sum r_{d,i}^2\mathbf1(r_{d,i}<0)}{\sum r_{d,i}^2}.
\]

\[
FlowImb_h(t)=2\frac{\sum TB^q}{\sum V^q}-1,\qquad AvgTradeSize_h=\frac{\sum V^q}{\sum N}.
\]

\[
\Delta\log OI_h=\log OI_t-\log OI_{t-h},\qquad
Spread_t=\log(P_{perp,t}/P_{spot,t}).
\]

Với candle hoàn chỉnh: body/range = `(C-O)/(H-L)`; upper wick/range = `(H-max(O,C))/(H-L)`; lower wick/range tương tự. Zero range là undefined cho ratio, kèm mask; không epsilon để tạo outlier. OI quantity/notional phải map trước khi lấy log-change. Nếu chỉ có notional, price-adjusted change là **approximation** có tên riêng, không giả quantity observed.

Skewness/kurtosis tính trên 5m returns trong window đã đăng ký, cùng estimator/ddof và coverage; không so 7 daily observations với thousands intraday observations. Không xóa valid price jumps hoặc tails chỉ vì bất thường.

### 4.3. Feature manifest mặc định: tối đa 48 numeric features trước masks

| Block | Features theo công thức/version rõ | Số tối đa |
|---|---|---:|
| P1 trend | returns 7/30/90; PE30/PE90; EMA30-vs-EMA90 distance chuẩn hóa bởi volatility quá khứ | 6 |
| P2 volatility | RVOL7/30/56/90; log RVOL7/RVOL90; log RVOL30/RVOL180; vol-of-vol30 | 7 |
| P3 tails/persistence | DownShare30/90; skew30; excess-kurtosis30; lag1 autocorr signed daily returns30; lag1 autocorr absolute returns30 | 6 |
| P4 candles | median body/range7; upper/lower wick-share7; median range/price7 | 4 |
| F spot flow | quote-volume anomaly30; trade-count anomaly30; log AvgTradeSize30; FlowImb1/7; flow-sign persistence30 | 6 |
| X spot/perp | perp FlowImb1/7; spot-minus-perp FlowImb7; perp quote-volume share30; mean spread7; spread std30 | 6 |
| M positioning | log OI change7/30; return30×OI-change30; log global-account ratio; log top-account ratio; log top-position ratio; top-position minus top-account log ratio | 7 |
| C carry | last published funding; sum realized funding30; funding anomaly90; official premium mean30/std30; funding×OI interaction | 6 |
| **Tổng** | Được giảm theo source eligibility, không thêm bù cho đủ số | **48** |

Anomaly dùng thống kê past của cùng field; exact log transform/window và robust scale được ghi trong manifest. Nested rolling lookback phải tính vào raw prehistory, không chỉ nhìn con số 180 của RV.

Nguồn M không đủ một ratio: loại feature ấy và dependent interaction, giữ các fields đủ. Không đoán bốn ratio names từ contract [I1]. Contract không có đúng requested field thì `UNAVAILABLE_FIELD`, không điền fake series.

Optional dominance nếu đã pass coverage: tối đa level/past percentile + change30/90; loại hoặc thay feature trùng trước freeze để giữ cap 50 numeric. Không tự thêm một study bên ngoài. Diagnostic features không được đi vào training nếu không nằm trong feature allowlist.

### 4.4. Ba feature cohorts để kiểm giá trị enrichment

```text
D0_PRICE_FLOW = P1 + P2 + P3 + P4 + F
D1_POSITIONING = D0 + X + các M fields đủ coverage
D2_CARRY = D1 + các C fields đủ coverage
```

Nếu X/M không available trên cohort: D1 không tồn tại riêng. Nếu C thiếu: D2 không tồn tại riêng. Không tạo hai tên cho cùng matrix rồi quảng cáo một ablation.

So D0/D1/D2 dùng cùng model default và cùng dates; provenance-only eligibility quyết định trước outcomes. Nếu enriched source không đủ base timeline, loại khỏi V1.2 chứ không co timeline lại. Chỉ sau ablation validation mới chọn feature cohort cho locked test bằng rule đã đăng ký.

### 4.5. Normalization, missingness và regularity

- Tree model giữ NaN với masks khi permitted; median imputation cho linear/readout fit trong training. Missing masks không được làm feature cho dữ liệu target tương lai.
- Robust scaling cho linear/readout: train median/IQR; IQR=0 thì constant-feature rule, không epsilon variance. Tree model không cần scale nhưng log/ratio giúp units rõ.
- Threshold clipping nếu có chỉ fit trên train, lưu clipped-rate; không clip future targets hoặc valid tail moves để giảm error.
- Không dùng centered rolling, backward fill, full-history z-score hoặc full-sample PCA/feature selection.
- Các derived ratios dùng synchronized sample times, không ghép spot now với perp future snapshot.
- Maximum stale lag theo source phải materialize từ contract/cadence trong MF-01; vượt thì feature missing hoặc forecast stale, không kéo latest value mãi.
- Feature importance/SHAP chỉ descriptive. Incremental value phải có block ablation trên same cohort; không random-permute individual days phá hết time structure rồi kết luận nhân quả.

<a id="s4-duration"></a>
## 4D. Nghiên cứu thời lượng regime và horizon — bổ sung bắt buộc V1.2

### 4D.1. Câu hỏi cần trả lời, không mặc định BTC có chu kỳ cố định

Sau feature engineering, tạo một daily observed-state tape để đo **mỗi trạng thái đã tồn tại bao lâu**. Sau fit/validation/test, đánh giá thêm model có dự báo được **khả năng tiếp tục và thời gian còn lại** tốt hơn baseline hay không. Đây là phân tích trên market data/prediction records; không cần QuantBT hoặc chạy thêm optimizer trials.

Phải phân biệt năm đại lượng:

| Đại lượng | Định nghĩa | Không được suy thay |
|---|---|---|
| `feature_lookback` | Bao nhiêu dữ liệu quá khứ tạo một observation/feature | Không là độ dài regime |
| `observed_dwell_duration` | Thời gian giữa hai lần đổi trạng thái đã xác nhận trên cùng state-definition version | Không là một chu kỳ BTC phổ quát |
| `state_age_at_t` | Đã bao lâu từ lần bắt đầu được biết của episode hiện tại | Không được dùng future episode end |
| `remaining_duration` | Thời gian từ hiện tại tới lần first exit kế tiếp, có uncertainty | Không phải mean duration trừ age một cách máy móc |
| `forecast_horizon` | Cửa sổ tương lai dùng định nghĩa V/E labels: 56 hoặc 90 ngày | Không bắt regime giữ nguyên cả window |

Nếu quan tâm “chu kỳ quay lại”, báo riêng **recurrence interval** từ lần bắt đầu state s đến lần bắt đầu state s tiếp theo. Nó gồm thời gian ở s và thời gian ở states khác, không bằng dwell time. Không suy period cố định hoặc giao dịch theo lịch bằng một mean recurrence. Các số đo chỉ đúng với definition, observation resolution, smoothing và lịch sử đã dùng. “Observed” ở đây nghĩa là trạng thái tính được từ observations theo công thức đã đăng ký, không phải được sàn công bố hoặc latent economic truth được xác nhận độc lập.

**Không có con số BTC mean regime duration mới trong guide này.** Các trường kết quả để null tới khi đo trên actual data; không gán sẵn 56/90 để đạt câu chuyện “structural”.

### 4D.2. Đo observed states riêng, không lấy forward labels làm đồng hồ regime

Hai trục forecast §5 vẫn giữ: future volatility và future path efficiency. Để đo current regime duration, thêm **hai observed axes riêng** từ completed BTC spot days:

- `OBS_VOL`: LOW / NORMAL / HIGH của realized-volatility feature trailing L ngày.
- `OBS_PATH`: DIRECTIONAL_DOWN / LOW_EFFICIENCY / DIRECTIONAL_UP của signed path-efficiency trailing L ngày.

Bản đo mặc định `OBS14_CONFIRM3_V1`: L=14 ngày; volatility boundaries = q1/3 và q2/3 của log RVOL14 trong một prefix có >=365 valid past daily observations; path threshold = median absolute PE14 của cùng permitted prefix. Prefix/thresholds phải có trước ngày đầu tape dùng để tạo training descriptors. Không dùng future V/E labels để fit observed-state thresholds.

Quy tắc khởi đầu này là **measurement convention**, không phải kết luận 14 ngày là optimal hoặc regime luôn dài 14 ngày. Để đo độ nhạy của definition, chỉ thêm L=28 và confirmation=1 thành bộ 2×2 nhỏ:

```text
OBS14_RAW       OBS14_CONFIRM3 (primary measurement)
OBS28_RAW       OBS28_CONFIRM3 (definition sensitivity)
```

Tính cả bốn trên cùng dates, công bố cả bốn; không chọn cái có duration gần 56/90, accuracy đẹp hoặc PnL đẹp. Đây là bốn phép phân đoạn deterministic nhẹ, **không phải bốn model families hoặc bốn WFO runs**. RVOL/PE14/28 chỉ phục vụ duration diagnostic ban đầu, không tự tăng feature allowlist của LightGBM.

Lưu ý:

1. Rolling lookback tự làm observations tương quan; hysteresis tự làm state ít nhấp nháy hơn. Dwell đo được là thuộc detector đã khai báo, không raw economic truth.
2. Không dùng nhãn future-H tại t cho biết “regime hiện tại”; nhãn đó chỉ available sau t+H+lag.
3. Run lengths của forecasts H56/H90 tạo hằng tuần chỉ là **forecast-label stability**. Future windows overlap khiến chúng có thể trông dai dẳng; không dùng để suy market regime tồn tại bao lâu.
4. Same terminal state sau H ngày không đồng nghĩa đã ở nguyên state trong H ngày: có thể rời rồi quay lại. Primary duration event là **first exit**, không phải endpoint equality.
5. Không ghép hai trục thành chín states trong primary duration estimation khi support chưa đủ. Báo từng trục/state riêng. Joint-state table chỉ descriptive và không nhân hai marginal probabilities.

### 4D.3. Confirmation, timestamps và prefix invariance

Với CONFIRM3, state mới chỉ được công nhận khi raw label mới giống nhau trong ba completed daily observations liên tiếp. Trước confirmation giữ old confirmed state, đồng thời lưu `pending_state`, `pending_count`, `first_seen_at`. Nếu raw label quay lại old state hoặc chuyển sang label thứ ba, reset pending theo rule deterministic.

- `confirmed_change_at` là **available time của observation thứ ba**, không lùi về observation thứ nhất.
- `observed_episode_start` của primary operational tape là confirmed-change time. `first_seen_at` được giữ làm descriptor latency, không được backdate activation/age trong forecast history.
- Lần khởi tạo tape hoặc ngay sau một data gap chưa biết true onset: ghi `onset_known=false`; không giả state bắt đầu lúc file bắt đầu. Sau khi quan sát được một subsequent confirmed transition hợp lệ mới có episode mới với onset biết được.
- Tại cutoff t, chỉ expose confirmed tape và age đã biết tại t. Appending/changing dữ liệu sau t không được đổi record/prediction đã phát trước t.
- Forecast model refit mỗi28 ngày không tự reset observed episode. Taxonomy/detector đổi version phải mở definition epoch mới, không report là market transition.
- Không sử dụng centered moving average, backward smoothing hoặc offline changepoint result để gán thời điểm bắt đầu đã biết trong live.

Một optional **offline reference segmentation** chỉ được dùng để mô tả sensitivity/detection delay trong development, có nhãn `RETROSPECTIVE_REFERENCE`. Nó không phải ground truth tự động và không đi vào historical live features. Không bắt thêm BOCPD/HSMM để hoàn tất V1.2.

### 4D.4. Episode ledger và các đoạn chưa kết thúc

Một record tối thiểu:

```text
episode_id, axis, state, detector_version, taxonomy_epoch
first_seen_at, confirmed_start_at, last_observed_at, end_at
onset_known, duration_lower_bound_days, observed_duration_days
event_observed, event_available_at, censor_reason
source_watermark, fit_snapshot_asof, state_tape_hash
```

Quy tắc:

- State chuyển thật theo detector: event=1; duration từ confirmed start tới confirmed next-state start, cùng đơn vị calendar time.
- Còn active tại **mỗi** fit cutoff: event=0, right-censored tại information watermark. Không dùng `end_at` trong file đầy đủ nếu end nằm sau cutoff.
- Episode đang có trước đầu dataset: onset không biết. Exclude khỏi estimator known-onset mặc định, nhưng giữ exposure và lý do; không lẫn với left truncation có known birth time. Future episode sau một observed change có thể vào estimator.
- Missing ngày/state không được fill thành tiếp tục. Censor episode tại last valid observation và reset monitor; không fabricate exit event hoặc nối hai đoạn qua một khoảng chưa quan sát.
- New source/taxonomy version không phải exit kinh tế. Censor hoặc tách epoch; không tăng transition count vì refit/scaler đổi.
- Ongoing episode ở cuối TEST được report như censored, không drop khỏi study hoặc tính age hiện tại như completed length.
- Risk set ở mỗi age được đếm theo **episodes**, không theo số candidate rows, daily forecasts hoặc copies của episode qua refits.

Censoring không đồng nghĩa mọi việc không biết đều “missing at random”. Administrative cutoff dễ diễn giải hơn source outage trong stress. Báo riêng outage/taxonomy censoring và sensitivity; không claim survival probabilities calibrated nếu censoring có dấu hiệu informative. Nguyên tắc censored observations và Kaplan–Meier tham chiếu [E11–E12].

### 4D.5. Bảng duration bắt buộc sau feature engineering

Per axis/state/detector và per role (train, validation, test), xuất:

| Nhóm | Fields bắt buộc |
|---|---|
| Support | Completed episodes, ongoing/right-censored, unknown-onset excluded, transitions và total observed days |
| Typical length | Completed-only mean/median/IQR có nhãn descriptive; censored-aware KM median nếu identifiable |
| Tail | p75/p90 duration nếu survival support đủ; không extrapolate để có số |
| Survival | S(14), S(28), S(56), S(90) cùng numbers-at-risk và uncertainty status |
| Restricted average | RMST tới τ đã ghi rõ, mặc định τ=90 ngày khi support đủ; không gọi RMST90 là mean total lifetime |
| Recurrence | Khoảng cách giữa successive starts của cùng state, số complete recurrence intervals; không gọi periodic cycle |
| Stability | Bốn detector variants; từng chronological period; data/source/taxonomy changes |

Kaplan–Meier theo state s:

\[
\widehat S_s(\ell)=\prod_{u\le\ell}\left(1-\frac{d_s(u)}{n_s(u)}\right),
\]

trong đó d là số observed exits tại duration u, n là episodes at risk ngay trước u. Handle ties/event–censor order theo numeric reference. KM không yêu cầu chọn Weibull/lognormal, nhưng statistical validity còn phụ thuộc assumptions và temporal heterogeneity [E11–E12].

\[
RMST_s(\tau)=\int_0^\tau \widehat S_s(u)\,du.
\]

Nếu KM curve chưa xuống0.5 thì median tổng duration **chưa xác định**, không tự lấy ngày cuối. Tail còn censored thì không tuyên bố mean total duration bằng mean completed episodes. Nếu dữ liệu không hỗ trợ τ=90, ghi τ_supported và limitation, không kéo đoạn plateau vô hạn để kết luận regime tồn tại rất lâu [E13].

**Support policy đề xuất, không power guarantee:** forecast survival per-state cần >=10 known-onset training episodes, >=5 observed exits và >=5 at risk ở mốc duration cần dự báo. Nếu không đạt, trả null + `DURATION_SUPPORT_LOW`; vẫn report descriptive table. Không hạ floor để sinh probability. Nếu survival curve đã xuống 0 qua observed exits, ghi rõ empirical terminal-support case; không extrapolate thêm events, không tuyên bố true tail probability chắc chắn0. Mức này được freeze trước duration outcomes dùng chọn phương pháp; có thể revised có version/owner trước evaluation, không sau khi thấy curve xấu.

Uncertainty trong một chuỗi BTC không tự là iid-lifetime experiment. Greenwood/KM bands nếu dùng phải ghi model-based assumptions; primary sensitivity resample episode bundles theo contiguous calendar blocks, giữ event/censor status, không resample từng ngày như một lifetime mới. Ít episodes thì descriptive/low-precision, không “95% chắc chắn regime dài X ngày”.

### 4D.6. Tuổi hiện tại và thời gian còn lại khác mean duration

Đặt L là total duration của một episode theo observed detector, a là age **đã biết** tại origin. Với known onset, stationary state-level baseline:

\[
P(L-a>h\mid L>a,s)=\frac{S_s(a+h)}{S_s(a)},
\]

\[
p_{exit}(h\mid s,a)=1-\frac{S_s(a+h)}{S_s(a)}.
\]

Đây là xác suất first exit trong h ngày của defined state process; không tự là xác suất mất alpha, đổi giá hoặc nên refit. S(a)=0/unsupported, thiếu risk-set support tại a+h hoặc onset unknown thì không xuất một probability giả.

Restricted remaining time:

\[
RMRL_s(a;\tau)=\int_0^\tau \frac{S_s(a+u)}{S_s(a)}\,du
=E[\min(L-a,\tau)\mid L>a,s].
\]

Không gọi RMRL tới90 ngày là full expected remaining duration. Full mean chỉ được report nếu tail identifiable hoặc có explicit validated tail model; mặc định không fit tail model.

**Ví dụ khái niệm, không phải dữ liệu BTC:** mean completed duration là70 ngày và current age50 ngày không cho phép kết luận còn20 ngày. Việc đã sống được50 ngày thay đổi conditional distribution. Các episode dài cũng dễ bị quan sát trúng tại một ngày ngẫu nhiên hơn episode ngắn; daily row-weighted mean khác episode-weighted mean.

Default duration model là KM-by-state và age-conditioned ratio ở trên. Forecast origins dùng cùng weekly grid với market model; curves được ước lượng từ training prefix, đóng băng trong refit block. Chưa thêm survival forest, neural hazard hoặc HSMM sweep.

### 4D.7. Optional context-aware remaining-duration model — chỉ khi có support

Chỉ mở trước TEST nếu owner thấy age-only baseline chưa đủ và có ít nhất40 completed training episodes tổng, >=10 của từng state được claim, >=12 validation blocks có resolved outcomes. Các floors này là engineering conventions, không bảo đảm predictive power.

Một model nhỏ duy nhất: regularized discrete-time logistic hazard với fixed age bins, state indicators và tối đa ba **current observed** descriptors (volatility change, efficiency, flow pressure). L2 C=1 khởi đầu, không grid family mới. Đóng gói theo landmark: features dùng tại origin giữ nguyên cho mọi forecast offsets, không đưa realized covariates tương lai vào hazard path. Hoặc mô hình time-varying hoàn toàn khác phải có registration riêng.

Chỉ so với state+age KM baseline, không chỉ so với một constant probability yếu. Quan hệ survival = tích(1−hazard) phải monotone. Episode/landmark weights và grouping được freeze để daily rows của một episode không bị gọi nhiều independent lifetimes. Không có đủ support: `NOT_RUN_DURATION_CONTEXT`, tiếp tục main LightGBM/Chronos qualification; không coi đây là failure của core.

BOCPD có thể cung cấp posterior run length, HSMM có thể mô hình explicit duration [E14–E15], nhưng **không thêm vào active roster V1.2**. HMM thông thường có geometric-duration structure, nên expected duration suy từ self-transition probability là model-implied quantity, không phép đo duration empirical độc lập. Model/hazard prior đặt expected run length56/90 rồi “tìm thấy”56/90 là circular evidence.

### 4D.8. Evaluation timing trên validation/test — không nhìn điểm kết thúc trước

Tại prediction origin t, lưu `state`, `age`, `S`, `p_exit` cho h=14/28/56/90, estimates còn lại, risk-set counts và fit cutoff. Chỉ 56/90 là forecast-horizon candidates chính; 14/28 ở đây là event-probability diagnostics nhẹ, không mở thêm bốn LightGBM horizons.

Ground truth của first-exit forecast:

- Có actual confirmed exit tại t'<t+h hoặc tại boundary theo convention đã pin: event label=1, available sau t'.
- Quan sát đầy đủ tới t+h mà chưa có exit: label=0, available tại t+h.
- Mất quan sát trước t+h và chưa exit: censored/unknown, không đổi thành0.

Đánh giá chính trên origin grid đã định trước với target window hoàn tất theo administrative cutoff. Informatively censored rows được giữ vào coverage report; không chấm complete-case rồi claim toàn population. Nếu dùng IPCW cho incomplete follow-up, censor model chỉ fit past và weights/support phải được qualify; mặc định không mở một pipeline IPCW lớn khi có complete follow-up đủ.

Metrics tối thiểu:

1. Brier/log loss của p_exit56 và p_exit90, so state+age baseline, reliability bins có counts; chọn proper loss trước outcomes.
2. Survival calibration ở age bins định trước; at-risk counts/tail support.
3. Remaining-time median MAE **chỉ** trên completed follow-ups, nhãn `COMPLETED_ONLY_DIAGNOSTIC` vì censoring có thể làm lệch mẫu; không dùng nó một mình cấp qualification.
4. Predicted-run lengths so observed-run lengths: temporal drift/stability, không gọi label agreement là accuracy của economic truth.
5. Per-period changes và definition sensitivity. Trạng thái thường đổi mỗi vài ngày dưới OBS14 nhưng dài hơn nhiều dưới OBS28 phải được báo, không chọn một variant thuận câu chuyện trung hạn.

Mọi predictive model comparison cần >=12 common temporal evaluation blocks, như forecast heads. **12 blocks không thay minimum episodes/risk sets**. Một state chỉ xuất hiện một lần dài xuyên12blocks không tạo12regime recurrences.

Grade riêng:

```text
DURATION_DESCRIPTIVE_VALID
DURATION_SURVIVAL_ESTIMABLE
DURATION_FORECAST_QUALIFIED_WITHIN_SCOPE
DURATION_SUPPORT_LOW / DURATION_CALIBRATION_UNPROVEN
```

Qualification context-hazard (nếu chạy) dùng paired positive proper-loss improvement ngoài mẫu, Brier skill point>=0.05 và support/calibration hợp lệ. KM-baseline estimate được report là baseline, không tự cấp “ML timing skill” chỉ vì curve tính được. Main H56/H90 model có thể đủ skill trong khi duration support thấp; khi đó chỉ qualified window-forecast, không claim biết lúc regime kết thúc.

### 4D.9. Liên hệ với chọn 56 hay90 ngày

Dùng duration study để **diễn giải và kiểm tính phù hợp**, không lấy mean duration rồi làm tròn tự động thành56/90.

| Kết quả development | Diễn giải / policy scope |
|---|---|
| Nhiều state episodes ngắn hơn56 ngày | Cả H56/H90 là forecast về window pha trộn nhiều trạng thái; không gọi một state sẽ giữ nguyên |
| Duration gần56 nhưng H90 có forecast skill rõ hơn | Horizon tốt để forecast một window có thể khác typical dwell time; báo cả hai, không ép chọn56 theo average |
| H56 và H90 có skill gần nhau | Tie rule ưu tiên56 để labels trưởng thành sớm hơn; đây là cost/update policy, không kết luận duration=56 |
| Current state đã tồn tại lâu, p_exit14/28 cao | Thêm cảnh báo transition risk nếu calibrated; không tự đổi params hoặc horizon của prediction đã phát |
| Không đủ episodes hoặc sensitivity definition quá lớn | Duration chưa identified đủ; không bịa average “structural cycle”; chọn horizon theo validation skill và giữ timing claim đóng |

H* được chọn trước TEST bằng rule §8.4. Kết quả TEST chỉ đánh giá lựa chọn ấy; không chọn lại vì duration/accuracy TEST gần một con số hơn. H56/H90 vẫn được báo riêng; failed chosen horizon không được thay bằng secondary winner rồi gọi primary PASS.

### 4D.10. Output timing và feature integration

Thêm vào packet §10, mỗi observed axis riêng:

```json
{
  "duration_context": {
    "state_axis": "OBS_VOL",
    "state_id": null,
    "state_definition_version": "OBS14_CONFIRM3_V1",
    "as_of": null,
    "confirmed_start_at": null,
    "onset_known": false,
    "current_age_days": null,
    "historical_duration_km_median_days": null,
    "historical_duration_rmst_days": null,
    "rmst_limit_days": 90,
    "restricted_remaining_mean_days": null,
    "remaining_limit_days": 90,
    "p_first_exit_within_days": {"14": null, "28": null, "56": null, "90": null},
    "training_episode_count": 0,
    "training_exit_count": 0,
    "risk_set_by_age": {},
    "duration_fit_cutoff": null,
    "qualification": "NOT_EVALUATED",
    "is_independent_ground_truth_regime": false
  }
}
```

Đây là schema đề xuất cần map, không capability đã triển khai hoặc probability BTC đã đo. P(first-exit14) ≤ P(first-exit28) ≤ P(first-exit56) ≤ P(first-exit90) khi cùng origin/model và các estimates đủ support.

Các duration-derived fields không tự thành LightGBM features. Default V1.2 báo chúng như metadata/diagnostics, giữ original feature cap. Chỉ thêm `observed_state`, `age`, `exit_risk` vào predictor qua một ablation được đăng ký trước validation, giới hạn <=50 numeric features và không dùng own future labels. Không dùng h* do TEST chọn làm training feature.

### 4D.11. Artifacts và effort

Tạo logical artifacts trong existing run namespace:

```text
observed_state_spec.json
observed_state_tape.parquet hoặc CSV tương đương
regime_episode_ledger.parquet
regime_duration_summary.json
survival_curves.json
remaining_time_forecasts.jsonl
horizon_selection.json
REGIME_DURATION_AND_HORIZON_REPORT.md
```

Các names là contracts mới, không bắt thêm service/database/library. Tính daily tape/episodes một lần theo source/spec hash; prefix summaries hoặc cache theo fit cutoff. Reuse cho mọi head/model, không nhân theo128trials. Unknown/sparse durations là scientific limitation có report; không kéo theo mua data hoặc mở nguồn ngoài thiếu historical.

### 4D.12. Tests và exit-gate supplement

| Test ID | Hành vi phải chứng minh trên code được runner gọi | Phase |
|---|---|---|
| DUR-T01 | Thay H56↔H90 không đổi observed-state tape/spec; future predicted labels không tạo duration truth | MF-02 |
| DUR-T02 | Appending future suffix giữ nguyên past states/ages; CONFIRM3 không backdate 2 ngày | MF-02 |
| DUR-T03 | Synthetic sequence có known runs/counts đúng; ongoing run right-censored, unknown initial onset không coi age0 | MF-02 |
| DUR-T04 | Missing day/taxonomy epoch không nối episode qua gap hoặc tính artificial transition; forecast refit không reset age | MF-02 |
| DUR-T05 | KM đúng risk sets/ties/censor numeric reference; median/tail unsupported trả null; complete-only mean có nhãn | MF-02 |
| DUR-T06 | Train snapshot trước episode end không thấy future end; validation/test future không được chọn definition | MF-03 |
| DUR-T07 | Conditional S(a+h)/S(a) và restricted remaining integral đúng; không mean−age; xác suất monotone/range hợp lệ | MF-03 |
| DUR-T08 | BothH cùng dates/baselines/fit policy; changing TEST outcomes không đổi H* hoặc frozen timing spec | MF-03 |
| DUR-T09 | Censored before horizon không thành negative; no-change→return-to-state case vẫn ghi first exit; episode cluster không tính nhiều samples độc lập | MF-04 |
| DUR-T10 | Report artifacts/n_at_risk/12blocks đúng; sparse state không có fake calibrated probability; forecast-label persistence không gọi observed dwell | MF-04 |
| DUR-T11 | Regenerate duration/horizon report không gọi model/QuantBT; restore prefix state giữ ages/predictions | MF-05 |
| DUR-T12 | Qualified duration/mean70 không tự mở WFO, đổi refit calendar hoặc claim cadence70; selected H* và skill flags vẫn đúng | MF-05 |

Gates bổ sung: `G2-DURATION-DEFINITION` (DUR01…05 + actual feature-tape/episode summary); `G3-DURATION-AND-HORIZON-FREEZE` (DUR06…08 + duration/H* record); `G4-TIMING-EVAL` (DUR09…10 + measured support/status); `G5-DURATION-HANDOFF` (DUR11…12 + full report). Thống kê duration chưa đủ support vẫn có thể technical PASS nếu computations/limitations đúng; thiếu implementation/actual required tape không được giả `LOW_SUPPORT` để qua gate.

Không thêm phase thứ sáu. Không yêu cầu regimes phải có mean56/90, models phải đổi selection, hoặc duration forecast phải dương để đạt engineering gate.


<a id="s5"></a>
## 5. Targets, số regime labels và future ground truth

### 5.1. Forecast clock và target windows

Tại cutoff `T` (UTC boundary), chỉ dùng features của completed days và available nguồn trước T. `target_start = T + common_ready_lag_days`; default design bắt đầu với lag một ngày, nhưng phải qualify runtime và source freshness trước freeze. Nếu forecast chưa ready tại start, không backdate; status theo policy ở §10.

Cho target window \([s,s+H)\), `s=target_start`, H=56 hoặc90:

\[
V_{T,H}=\sqrt{\frac{365}{H}\sum_{d=s}^{s+H-1}RV_d},\quad Z^V_{T,H}=\log V_{T,H},
\]
\[
E_{T,H}=\frac{\sum_{d=s}^{s+H-1}r_d}{\sum_{d=s}^{s+H-1}|r_d|}.
\]

Returns ngày s dùng đúng preceding close. Entire interval nằm sau available inputs; lag days không được lọt vào target nhầm. H ngày không phải trading-session days; crypto dùng calendar days.

Không scale trực tiếp old labels28/56/90 thành label56/90; H56 cũ chỉ reuse khi exact target/economics/availability contract thực sự khớp. Tạo lại labels từ raw market observations; không cần QuantBT cho phần này.

### 5.2. Hai trục, mỗi trục ba classes

**Volatility:** `LOW`, `NORMAL`, `HIGH`.  
**Path efficiency:** `DIRECTIONAL_DOWN`, `LOW_EFFICIENCY`, `DIRECTIONAL_UP`.

Không có một 6-class softmax chung. Có hai distributions 3-class độc lập về head, tổng mỗi distribution bằng1. Có thể hiển thị chín cặp labels nhưng **không nhân marginal probabilities để giả joint probabilities**.

Path labels định nghĩa theo PE, không gọi LOW_EFFICIENCY chắc chắn mean-reversion có lãi hoặc DOWN là mọi ngày giảm. Một window có nhiều transitions vẫn có summary theo công thức; uncertainty và diagnostic phải phản ánh giới hạn đó.

### 5.3. Taxonomy freeze

- Từ một prefix train-only có outcomes đã mature trước calibration/validation, lấy q1/3 và q2/3 của `log V_H` làm boundaries riêng cho H56/H90.
- Với path, \(\tau_H=\operatorname{median}|E_H|\) trên cùng prefix là default, khóa trước outcomes validation/test. `DOWN: E<-tau`, `UP: E>tau`, phần giữa LOW_EFFICIENCY.
- Default taxonomy prefix có ít nhất 365 daily origin labels đã mature; không gọi đây là 365 độc lập. Nếu các boundaries collapse hoặc không có support các classes, ghi `DEGENERATE_TAXONOMY`, không tune threshold theo validation accuracy.
- Thresholds cố định trong toàn study. Refitting model không tự đổi nghĩa HIGH/LOW. New taxonomy là version mới; không pool classifier outputs khác ontology.
- Taxonomy phải được biết trước các historical forecasts dùng fit calibrator. Không freeze boundaries bằng dữ liệu sau những forecasts ấy rồi coi calibration là fully point-in-time.

Ở horizon dài, \(|E|\) có thể co về gần0; thresholds theo từng horizon giúp không dùng một cutoff 28 ngày lên90 ngày. Vẫn phải report class prevalence drift, không giữ tần suất1/3 nhân tạo bằng full-sample rebinning.

### 5.4. Label availability và validity

```text
label_end = target_start + H days
label_available_at = label_end + publication/reconciliation lag
eligible_for_fit(u,T) = label_available_at(u,H) < T
```

Equality chỉ chấp nhận khi event sequence chứng minh label được publish trước fit snapshot. Null future labels không được ảnh hưởng inference eligibility tại current origin.

Một target thiếu daily RV/close trong window: typed invalid/censored, không rescale H hoặc fill returns 0. Các models có chung invalid-target mask trong paired evaluation. Giữ failed model forecasts khác với invalid ground truth: model failure là lỗi availability của policy, không xóa target để cải thiện score.

### 5.5. Vì sao không học latent labels làm truth

JM/HMM state ID chỉ là một representation, không là ground truth cho accuracy. Current model accuracy phải đo với realized V/E labels đã định nghĩa độc lập thuật toán. OI/funding/flow trước mắt là features, không tự là nhãn institutional accumulation/distribution/liquidation.

Trình bày `target_definition_version` trong mọi output. Model tốt nghĩa là dự báo đúng nhiệm vụ này, không tự chứng minh đã khám phá toàn bộ regime kinh tế của Bitcoin.

<a id="s6"></a>
## 6. Split methodology cho horizon dài: không tạo statistical sample giả

### 6.1. Phân biệt bốn con số

| Con số | Ý nghĩa |
|---|---|
| Daily training origin rows | Số rows được học; labels liên tiếp chồng lấn |
| Weekly test origins | Số forecasts thực trước outcome, cùng grid giữa models |
| 28-day evaluation blocks | Nhóm báo cáo/refit có4 weekly origins; >=12 mỗi comparison |
| Non-overlapping future-window equivalents | Diagnostic support theo khoảng lịch; không phải một estimator ESS tự động |

Ví dụ 12 blocks ×28 ngày có 48 weekly forecasts. H90 khiến các forecast outcomes overlap; không gọi đó là 48 independent samples hoặc 12 independent 90-day episodes.

Nếu yêu cầu riêng **12 forward windows không overlap** thì cần tối thiểu672 ngày cho H56 hoặc1.080 ngày cho H90, chưa train/validation/calibration. Guide này **không âm thầm gọi monthly origin blocks là independent horizon folds**. WFO historical-fold contract cũ không được cấp PASS bằng model counts mới.

### 6.2. Layout được chọn cho model qualification V1.2

1. **Initial labeled history:** trước validation đầu, ít nhất730 daily origin rows có features hợp lệ và labels H tương ứng đã mature. Initial model có thể có thêm raw history; không dùng 180-day candidate training rule của WFO để fit ML này.
2. **Development:** ít nhất12 blocks28 ngày, dự báo weekly. Model recipe/feature selection bằng những outcomes sau khi mature.
3. **Freeze boundary:** toàn bộ validation outcomes cần dùng chọn recipe/calibrator đã available trước first locked-test decision. Freeze so cả hai horizons phải sau maturity của toàn bộ validation outcomes cần dùng, thường chịu H90; không đưa last validation future vào first test.
4. **Locked test:** ít nhất12 blocks28 ngày, chung dates cho models trong một horizon. H56/H90 có cùng forecast-origin dates khi so horizon; trước run bảo đảm follow-up H90 đủ. Không cắt riêng dates của horizon yếu để thay kết quả.
5. **Follow-up:** collect/score target outcomes qua end của origin test cuối + lag +H. Nếu một H thiếu actual follow-up, ghi H ấy incomplete; không tự đổi primary đã freeze. Nguồn optional thiếu vẫn exclude, khác với thiếu target bắt buộc.

Không yêu cầu thêm12 INIT WFO origins hoặc chạy128 strategy trials để fit regime labels. Initial history là dữ liệu thị trường, không optimizer evidence.

### 6.3. Coverage và episode timing cần hai bảng riêng

Nếu cần12 forward windows không overlap thì12×56=672 ngày và12×90=1.080 ngày cho riêng evaluation, chưa train/validation/readiness. Layout model-first dùng >=12 blocks28 ngày chứa weekly origins và thừa nhận overlap, không giả có đủ một lịch độc lập dài hơn dữ liệu thực.

Planner phải resolve từ raw availability: feature prehistory +730 matured daily training origins +validation origins +maturity gap của cả hai horizons +locked-test origins +H90 follow-up. Không copy các dates minh họa của V1.1 khi đổi horizon. Prefix365 observations để freeze observed-state taxonomy phải nằm trước episode evidence được dùng tại validation đầu; có thể reuse bên trong phần training history dài, không cần mở thêm WFO INIT jobs.

Episode table §4D giữ `start/end/censor/age` theo detector/calendar thật. Một episode có thể chạy qua nhiều prediction/refit blocks; không cắt nó thành nhiều durations mới ở ranh giới block. Tại từng model-fit cutoff nó có một as-of view đúng, không biến nhiều views của cùng episode thành samples khác nhau.

Thiếu coverage bắt buộc thì báo exact missing interval. Thiếu state recurrences thì report duration support riêng, không thêm symbol/source hoặc hạ per-comparison12blocks để có significance.

### 6.4. Rolling fit trong validation và test

- Tại đầu mỗi block, snapshot labels đã available. Trong block, weights cố định; weekly features thay theo market.
- Trong locked test, được refit weights hàng28 ngày bằng outcomes đã mature theo frozen rule; không reselect hyperparameters/features/taxonomy/checkpoint.
- Số train rows dùng fit phải được log theo horizon. H90 labels mature muộn hơn H56; không lấy H56 label làm H90. Log khác biệt actual training counts; recipe policy giống nhau, không cần fake cùng số labels bằng cách đọc future.
- Early stopping nếu sử dụng cần inner held-out interval và purge theo maturity. **Default V1.2 dùng fixed boosting rounds để tránh một split/calibration phức tạp không cần thiết.**
- OOF calibration forecasts phải được tạo bởi model chỉ fit labels known tại chính historical forecast origin, không use in-sample fitted logits.

### 6.5. Overlap/uncertainty

Tối thiểu report origin-to-origin overlap matrix hoặc summary, calendar span, horizons, regime runs và effective independent-episode limitations. Không resample 48 rows iid.

Default inference cho paired mean proper-loss improvement: moving/circular time blocks theo weekly-origin index, primary length `ceil(H/7)` origins, sensitivity `ceil(1.5*H/7)` và `ceil(2*H/7)` nếu sample cho phép. Wrap phải thật nếu ghi circular. Ghi các sensitivities không đủ blocks thành `NOT_INFORMATIVE`, không lén giảm block size tới khi significant.

Ngay với H56/H90 và48 forecasts, khoảng độc lập còn rất ít. CI bootstrap chỉ là approximation. Nếu precision/calibration của estimator không đủ, báo `LOW_PRECISION`, không gắn population-skill certificate từ một CI đẹp. Tăng bootstrap draws không tăng market history.

Có thể báo một deterministic non-overlap origin subset chọn theo clock trước outcomes để kiểm sensitivity; nếu ít hơn12 thì chỉ descriptive, không thay primary12block requirement.

### 6.6. Data exposure và foundation models

Old 2020–2026 market history đã từng được xem thì locked test mới vẫn retrospective với research-exposure disclosure. Input cutoff sạch không xóa selection bias qua nhiều vòng nghiên cứu [E9].

Checkpoint mới được phát hành sau historical dates: gọi `HISTORICAL_TRANSFER_EVALUATION`, không claim model thật đã available khi đó. Synthetic-only giúp giảm một rủi ro pretraining nhưng không tự chứng nhận toàn pipeline chưa xem future. Prospective proof chỉ từ decisions/outcomes thực sau freeze; guide không hứa chờ thu dữ liệu hoặc mở daemon.

<a id="s7"></a>
## 7. Model roster và parameters — đủ để implement, không mở sweep vô hạn

### 7.1. Vai trò của từng family

| Family | Vai trò V1.2 | Đặc tính và giới hạn |
|---|---|---|
| Persistence / matured class frequencies | Baseline bắt buộc | Rẻ, dự báo bằng current trailing condition hoặc tần suất quá khứ; phải cùng horizon/taxonomy |
| HAR-style realized volatility | Baseline volatility bắt buộc | Kết hợp các volatility scales; là direct-H adaptation của ý tưởng HAR-RV [E7], không tự là mô hình gốc cho mọi target |
| Regularized logistic / ridge | Baseline tabular bắt buộc | Dùng cùng permitted features, scale/impute train-only, đo giá trị của nonlinearities |
| **LightGBM** | **Primary candidate** | Tabular nonlinear interactions và missing values, multiclass + quantile regression [E4] |
| **Chronos-2-Synth frozen** | **Một foundation challenger** | Multivariate/past-only covariates, multi-step quantiles; phải qualify actual checkpoint [E6] |
| CatBoost | Alternative chỉ khi LightGBM integration/capability không đáp ứng | Không chạy song song như family thứ ba mặc định; cần preregister trước outcomes |
| JM/HMM | Historical reference/diagnostic, không ground truth | Vẫn cần filtered inference/state alignment nếu dùng lại sau này |
| TFT/PatchTST/Kronos/TimesFM | Catalog deferred | Không fit thêm ở vòng đầu; chỉ mở revision có lý do đã đo |

Model chính được chọn bằng locked development rule, không theo tính mới của architecture. Forecasting benchmark bên ngoài không chứng minh BTC regime skill.

### 7.2. Baselines có cùng information/target contract

**Persistence regression:** volatility theo realized past-H; efficiency theo trailing PE_H, tất cả tại cutoff. Không đưa phần target đã xảy ra trong ready lag vào baseline hoặc treatment.

**Historical-frequency probabilities:** tính trên các labels matured, Dirichlet/Laplace smoothing alpha=1 để tránh zero probability do finite sample; đây là predictive estimator, không sửa ground-truth class counts.

**Persistence classification:** trailing observed condition map vào fixed taxonomy; biến one-hot thành probabilistic baseline bằng transition/confusion estimate từ permitted historical origin pairs nếu đã preregister. Không dùng final frequencies.

**HAR-style:** direct regression dự báo `log V_future,H` từ log realized variance scales1/7/30 ngày (thêm90 chỉ bằng fixed formula cùng cho mọi lần fit). Ghi đây là direct-H extension, không giả đã reproduce full Corsi paper. Forecast variance qua exp transform có estimator interpretation riêng; không gọi exp(mean logV) là exact expected volatility.

**Logistic:** L2 regularization `C=1.0`, đủ `max_iter` để hội tụ, no class reweight default. **Ridge efficiency:** standardized past descriptors, alpha=10 fixed. Fit/check convergence; arbitrary exception không thành successful forecast.

Đối chứng mạnh nhất cho mỗi metric/head được chọn trong development và khóa trước TEST. Không chọn baseline yếu nhất để đạt skill; cũng không đổi baseline sau test để đổi câu chuyện.

### 7.3. LightGBM cụ thể

**Tasks:** hai multiclass heads độc lập, ba quantile regressors của `log V_H` (0.1/0.5/0.9), một median regressor của `E_H`. Tổng sáu estimators/horizon. E quantile intervals là optional **chưa chạy mặc định**; không fabricate interval từ RMSE.

Starting parameter contract, số dưới là experiment settings mới, không phải best params đã biết:

```yaml
framework: lightgbm
version: PIN_INSTALLED_APPROVED_VERSION
boosting_type: gbdt
device_type: cpu
learning_rate: 0.03
n_estimators: 400
max_depth: 4
num_leaves: 15
min_child_samples: 64
reg_alpha: 0.1
reg_lambda: 10.0
max_bin: 63
colsample_bytree: 0.9
subsample: 1.0
subsample_freq: 0
class_weight: null
random_state: 20260927
deterministic: true
force_col_wise: true
n_jobs: FROM_APPROVED_RESOURCE_ENVELOPE
```

Pin actual API names/aliases theo installed version; ví dụ native `lambda_l2` tương đương sklearn `reg_lambda`, không truyền cả hai với giá trị mâu thuẫn. Docs tham khảo không phải quyền upgrade production [E4].

Classification: `objective=multiclass`, `num_class=3`; model trả đúng class order của taxonomy. Quantile: `objective=quantile`, `alpha` theo từng quantile. Median E prediction nếu ra ngoài [-1,1] được project theo domain rule đã đăng ký; lưu cả raw value và projection flag. Quantile crossings được xử lý bằng fixed monotone rearrangement, report crossing rate; không chỉnh target để giảm lỗi.

**Small grid:** `max_depth∈{3,4}` với `num_leaves=2^depth-1`; `min_child_samples∈{64,128}`; giữ các field khác fixed. Bốn configurations. Không tăng 128 hyperparameter trials vì WFO trước đó có128 trials.

Data ablation dùng default recipe trên D0/D1/D2 đã available. Sau đó grid bốn configs chỉ trên cohort được chọn trong development; không full Cartesian data×models×grids×horizons×seeds. Các overlapping calculations reuse được. Tối đa sáu distinct LightGBM config/data recipes mỗi horizon khi default được reuse; trường hợp roster thực khác phải có exact workload table.

H56/H90 dùng cùng grid, có winner model riêng; H* được chọn theo §8.4 trên development và **không** được chọn lại bằng TEST. Default fixed 400 rounds không early stopping. Nếu có convergence/resource issue cần thay rounds, version trước locked test; không dùng TEST cho early stopping.

Leaf sample count là count/weight của dependent rows, không đảm bảo số market episodes trong leaf. Report leaf support/time concentration; small depth/regularization giảm capacity nhưng không thay validation.

### 7.4. Probability calibration

- Trong development, mọi recipe tạo past-only OOF forecasts. Recipe selection dựa raw proper scores; calibration không làm final labels lọt về past.
- Trước TEST, fit **một temperature scalar/head/horizon** từ OOF logits của winning recipe trên matured development predictions; kiểm T>0 và finite. Baselines có probability calibration tương ứng khi thích hợp.
- Model selection và calibration cùng dùng development thì ghi đúng như vậy; không gọi calibrator là independently validated. Locked TEST là lần đánh giá cả pipeline đó.
- Không dùng fitted in-sample training logits làm calibration evidence. Không calibrate bằng future TEST labels.
- Default calibrator freeze trong TEST; weights refit mỗi28 ngày nhưng recipe/temperature không đổi. Theo dõi drift, không tự refit temperature sau một fold xấu.
- Nếu support calibrator thiếu, dùng raw probabilities với `UNCALIBRATED_SUPPORT_LOW`; không tự grade calibration PASS. Primary model comparison vẫn chạy và báo limitation.
- Không dùng isotonic linh hoạt trên vài independent episodes rồi kỳ vọng calibrated. Reliability phải chấm trên TEST [E5].

### 7.5. Chronos-2-Synth challenger

```yaml
model_id: autogluon/chronos-2-synth
revision: PIN_EXACT_HUB_COMMIT
weights_sha256: REQUIRED
backbone_trainable: false
context_length: 512_daily_steps
forecast_horizons_days: [56, 90]
quantiles: [0.1, 0.5, 0.9]
cross_learning_across_origins: false
context_variant_search: disabled
```

Model card mô tả synthetic-only; Chronos-2 family có multivariate/past-only covariates và quantile forecasts [E6]. Cần kiểm actual checkpoint/package hỗ trợ context/prediction lengths yêu cầu; không silent truncate. Không mua GPU hoặc dùng cloud endpoint trả phí mặc định; micro-profile CPU/GPU đã được cấp, cap resource trước bulk.

**Hai target series input hợp lệ:** trailing-H `log RVOL_H` và trailing-H `PE_H`, mỗi observation kết thúc ở một ngày **đã biết**. Forecast cần chấm là endpoint tương ứng `target_start+H`, không step1. Nếu common lag L ngày, dự báo tới **L+H steps** theo exact timestamp alignment của API. Tại endpoint ấy, trailing-H window mới đúng future target window.

OI/funding/flow là past-only covariates. Không đưa actual future settlement/activity vào `future_df`. Taxonomy/calendar có known-future fields thực mới được truyền; không cần chúng trong default.

Không cộng các quantiles của daily vol thành quantile của56/90-day RV. Không dùng generated price paths để chứng nhận market regime accuracy. Output forecasts là statistics và phải chấm với observed ground truth.

Đối với multiclass, dùng một readout multinomial L2 nhỏ (`C=1`) trên quantile endpoints và ít observed context đã freeze; fit từ past-only Chronos OOF outputs cùng labels/taxonomy. Không biến q10/q50/q90 thành exact joint probabilities. **Challenger được gọi là Chronos + readout**, không giả classification capability native. Nếu readout chưa đủ support, chỉ chấm regression head, không sinh fake class probabilities để đủ bảng.

Rows Chronos cùng cutoff/symbol có thể grouped để dùng multivariate context. Origins khác nhau tuyệt đối không cross-learn. Test adding future task vào batch phải giữ nguyên prediction origin cũ. Cache phải gồm cutoff/window, input hash, model revision và output alignment.

### 7.6. Checkpoint/forecast provenance

Lưu weights, config/tokenizer, package version, code revision, ngày phát hành model, published training-data description, license và actual transforms. Không upload/distribute weights/fonts/secrets qua report. Synthetic-only giảm lo ngại trực tiếp về real-price pretraining nhưng không chứng minh research dataset chưa bị dùng để chọn model.

Không load untrusted pickle tự động. Forecasting code có thể dùng safetensors hoặc pinned trusted serialization trong sandbox. Failure của optional foundation challenger không chặn core LightGBM implementation; scope ghi `CHALLENGER_NOT_QUALIFIED`, không giả Chronos đã thua về scientific performance.

<a id="s8"></a>
## 8. Trình tự ablation, fit và chọn model

### 8.1. Trước hết kiểm dữ liệu, chưa cần foundation backbone

1. Chọn nguồn theo historical coverage/PIT/license, freeze allowlist.
2. Default LightGBM trên D0, D1, D2 available; tất cả chấm cùng validation origins và taxonomy.
3. So incremental predictive value bằng paired loss, không chỉ importance.
4. Chọn cohort theo predeclared rule: lowest combined primary classification loss trên validation, với regression safeguards; nếu improvement so simpler cohort nhỏ hơn1% tương đối hoặc nonfinite, ưu tiên simpler cohort. Mốc1% là tie/complexity convention, không statistical proof; freeze trước chạy.
5. Small LightGBM grid trên cohort ấy; baseline references vẫn giữ đủ.
6. Fit Chronos frozen challenger đúng cùng cohort/targets/horizons và record full cost.

Không thêm feature/mô hình vì thấy một fold xấu. Trong cùng final experiment, feature set, model family và head definitions không đổi sau freeze.

### 8.2. Rule chọn recipe trước TEST

Hai classification heads dùng Brier score theo definition §9 và same dates. Đối với chọn **một recipe model/horizon**:

\[
J=\tfrac12\left(BS_{vol}/BS_{vol,ref}+BS_{path}/BS_{path,ref}\right).
\]

Reference được pin từ baselines trước recipe selection; mẫu số zero/invalid thì không dùng ratio, ghi degenerate metric và apply deterministic raw-loss alternative đã registered. J chỉ là selection criterion trong development, không là accuracy/proof tự thân.

Tie trong0.5% relativeJ: prefer lower logV-MAE relative baseline, rồi lower measured inference cost, rồi simpler predeclared order `LightGBM -> Chronos+readout`; không tùy chọn sau output. Regression heads của cùng recipe được report, không chọn một chart riêng tốt nhất cho headline.

Nếu Chronos chỉ qualified regression nhưng không đủ classification readout, giữ nó là regression challenger, không cạnh tranh joint-class recipe bằng incomplete scores. Có thể grade một head/horizon riêng ở final, nhưng không tạo blended ensemble winner sau khi xem TEST.

Calibration sau recipe selection dùng past-only OOF predictions, mọi quyết định vẫn trước final test start. Optional external sources không đủ được exclude trước bước 1, không làm tăng ma trận.

### 8.3. Model quality phải trả lời đủ ba câu hỏi

- **Dữ liệu:** thêm OI/flow/carry có giúp ngoài price-only baseline không?
- **Mô hình:** LightGBM hoặc foundation challenger có hơn baselines đủ mạnh dùng cùng inputs không?
- **Horizon:** skill còn ở56/90 ngày hay chỉ là sự bền của một trailing statistic đã biết phần lớn?

Model forecast chưa qualified thì dừng ở conclusion đó. Không lấy regime labels đưa vào QuantBT để thử xem có tình cờ thắng không.

### 8.4. Chọn H* giữa56/90 bằng development, không bằng niềm tin hoặc TEST

1. Trước mọi comparison: pin menu `[56,90]`, same validation-origin calendar, target-specific taxonomies/baselines, detector specification và duration-report protocol. Không mở grid30/45/120/180 sau thấy kết quả.
2. Fit model/feature recipes cho mỗiH theo §8.1–8.2, từ labels đã mature. Classification tasks của haiH khác distributions; chỉ dùng normalized proper-loss criterion J_H (so baseline của đúngH), không so raw accuracy/MAE rồi chọn task dễ hơn.
3. Ghi duration summary trên **train/development-only as-of views**: per-state median/IQR/RMST, first-exit56/90 support, definition sensitivity, current-age distribution và số regimes thường xuất hiện trong một forward window. Những số này giúp đặt scope `WINDOW_CONDITION_FORECAST` hay supported timing use, không thay loss metric.
4. Trong cácH có đủ12paired validation blocks và technical eligibility, ưu tiên H có nonnegative validation Brier skill ở cả haiheads. Trong cùng nhóm chọn J_H thấp nhất. Nếu chỉ mộthead có triển vọng, vẫn report head-specific limitation và chưa tự coi full regime qualified.
5. Tie trong1% relativeJ: chọn56 vì labels mature sớm hơn; tie là quyết định cost/update đã công khai, không suy mean duration=56. Nếu cả haiH đều yếu, chọn technically valid minimumJ với `WEAK_HORIZON_EVIDENCE` chỉ khi owner duyệt locked falsification; không đổi target để tạo validation winner.
6. Freeze `horizon_selection.json` trước TEST: candidate set, commondates, model/metric refs, J perH, selectedH, duration interpretation, primary head family, tie reason và owner scope. Validation cuối của cảH phải mature trước khi dùng để freeze.
7. Trong TEST báo haiH riêng; chính thức primary chỉ làH*. Nếu primary fail và secondary pass, ghi đúng kết quả; muốn dùng secondary cho WFO cần registration/owner riêng và exposure disclosure, không gọi original primary đã thành công.

Duration report không phải điều kiện ép S(H) cao. Một forecast về volatility/path **trung bình của window** vẫn có thể có skill dù state đổi nhiều lần trong window. Chỉ khi muốn claim giữ nguyên regime/refit theo remaining time mới cần duration forecasting qualification riêng. Nếu definitions cho durations khác nhau mạnh, không chọn một “chu kỳ trung bình” duy nhất; report definition dependence.

Không có cơ chế tự thay56↔90 mỗi origin trong V1.2. Adaptive horizon theo remaining life là nghiên cứu policy sau này, phải kiểm riêng với cùng information set/budget; không bật qua một if statement trong live.

<a id="s9"></a>
## 9. Evaluation: accuracy/hit rate/error và ngưỡng qualification

### 9.1. Forecast ledger là source of truth

Mỗi forecast được lưu **trước outcome** với immutable ID, origin, available-input watermark, model/threshold/calibrator hashes, target start/end, predictions, quality và timing. Sau maturity, evaluation job nối labels bằng ID; không sửa prediction.

Report trên same paired forecasts có ground truth hợp lệ. Technical prediction failure phải có policy fallback nếu đã được registered; không bỏ chỉ model thất bại khỏi denominator. Thiếu payload chưa được mô phỏng fallback thì `INCOMPLETE_RUN`, không fill0.

### 9.2. Các metrics

| Task | Primary | Secondary bắt buộc |
|---|---|---|
| Volatility multiclass | Multiclass Brier skill vs strongest frozen baseline | Log loss, balanced accuracy, macro-F1, confusion matrix, class support |
| Path multiclass | Multiclass Brier skill vs strongest frozen baseline | Log loss, balanced accuracy, macro-F1, errors theo UP/DOWN/LOW_EFF |
| Log-volatility regression | MAE(log V), relative error reduction vs baseline | Quantile pinball loss, coverage và interval width, QLIKE diagnostic |
| Efficiency regression | MAE(E) vs baseline | Signed bias, error theo realized class, forecast distribution |
| High-vol alerts | Precision/recall/false-alarm và coverage | Distinct event episodes, lead-time/maturity, uncertainty |

Multiclass Brier convention:

\[
BS=\frac1N\sum_i\sum_{c=1}^{3}(p_{ic}-\mathbf1[y_i=c])^2,\quad
BSS=1-BS_{model}/BS_{baseline}.
\]

Logloss dùng probability floor chỉ cho numerical scoring theo fixed protocol, báo count clipped; không sửa saved probabilities để trông calibrated. Balanced accuracy là mean recall trên fixed class set; class không có truth support thì metric/support status rõ, không average một class thuận lợi rồi gọi ba classes.

QLIKE với realized variance y và positive variance forecast yhat:

\[
QLIKE=y/\hat y-\log(y/\hat y)-1.
\]

Nếu dùng `exp(2*q50_logV)` thì đó là median-based variance point proxy, không conditional mean optimal cho QLIKE; logV-MAE mới là primary của median head. Không đổi sang forecast transform khác sau khi QLIKE xấu.

Prediction intervals: 10–90% là nominal80% interval; phải báo coverage **và** width, không interval vô hạn để đạt100% coverage. Probability calibration dùng reliability bins fixed/coarse, kèm counts; ECE một mình không là gate [E5].

### 9.3. Ngưỡng mặc định cần freeze trước TEST

Các con số là experiment acceptance defaults, không universal scientific constants:

| Field | Default |
|---|---:|
| Meaningful Brier skill | 0.05 (5% relative loss reduction) |
| Balanced accuracy improvement | 0.05 absolute =5 điểm phần trăm |
| Meaningful primary regression error reduction | 0.10 =10% |
| Confidence target | 0.95; qualified approximate time-series procedure |
| Common validation/test blocks | >=12 mỗi role |
| Hard-label usage confidence threshold | 0.60, chỉ cho optional abstention report |
| Minimum selective coverage cho claim sử dụng hard labels | 0.80 |
| Nominal regression interval | 80% (q10–q90); coverage/width report riêng |

Thresholds không phải target phải làm xanh. Không tăng confidence threshold sau test để lọc những ngày khó. Primary probabilistic scores tính trên **toàn forecast policy**, không chỉ confident subset.

### 9.4. Qualification theo từng head và horizon

**`PROBABILISTIC_SKILL_QUALIFIED(H,head)`** cần:

1. Domain/data/timestamp/model tests pass, đủ12 common blocks và labels.
2. BSS point>=0.05 so reference đã freeze.
3. Cận dưới CI paired proper-loss improvement >0 với procedure đủ để diễn giải; không coi bootstrap fraction-positive là exact p-value.
4. Reliability phải có plot/bins/counts và uncertainty; không chỉ một scalar ECE. Nếu calibration drift hoặc số episodes không đủ để đánh giá, ghi `CALIBRATION_UNPROVEN` và không cấp calibrated-probability claim; vẫn báo raw predictive scores. Probability outputs chưa calibrated đúng thì chỉ có predictive-skill claim, không calibration certificate.

**`HARD_REGIME_CLASSIFICATION_QUALIFIED`** còn cần balanced-accuracy gain>=0.05, per-class support và false-alarm/missed-event profile đủ nguồn. Không bắt buộc model raw accuracy80%; so đúng baseline và prevalence.

**`CONTINUOUS_TARGET_QUALIFIED`** cần primary error point reduction>=10%, lower CI improvement>0, và domain/coverage gates. Regression pass không tự làm classification head PASS hoặc ngược lại.

**Hiệu lực bridge:** chỉ sử dụng những heads/horizons thực sự qualified; volatility của H* pass nhưng path cùng H* fail chỉ cho phép đề xuất volatility-conditioned research, không gọi full predictive-regime model đã hiểu direction. H56 không cấp chứng nhận H90 hoặc ngược lại; H* fail thì không tráo primary. Nếu CIs quá yếu, model có thể có `OBSERVED_SKILL_LOW_PRECISION`, chưa mở financial hypothesis tự động.

### 9.5. Support rare classes và dependence

Class counts từ overlapping labels không là số market episodes. Report runs của realized class, event intervals và variation theo calendars; không tự coi 20 origins liên tiếp trong cùng crash là20crashes.

Nếu một class absent trong final cohort, giữ 3-label schema và report head incompletely evaluated; không drop class để accuracy tăng. Không chạy lại new test tới khi class xuất hiện đủ mà vẫn gọi cùng test đã đăng ký. Một model không trả forecast được là operational failure, không event thiếu ground truth.

### 9.6. Final decision vocabulary

| Điều kiện | Kết luận |
|---|---|
| Technical/data invalid | `NOT_EVALUABLE` |
| Mandatory computations chưa xong | `INCOMPLETE_RUN` |
| Optional source bị loại | `EXCLUDED_SOURCE`, không block core |
| <12 paired blocks hoặc target thiếu | `INSUFFICIENT_EVALUATION_SCOPE` |
| Point gain nhưng interval rộng | `OBSERVED_SKILL_LOW_PRECISION` |
| Đạt proper score nhưng labels/hard hit rate chưa đạt | `PROBABILISTIC_ONLY_QUALIFIED` theo H/head |
| Đạt head/horizon đầy đủ | `MODEL_HEAD_QUALIFIED_WITHIN_SCOPE` |
| Qualified interval loại được meaningful gain | `NO_MEANINGFUL_SKILL_WITHIN_SCOPE` |
| Efficacy âm rõ | `UNDERPERFORMED_BASELINE_WITHIN_SCOPE` |
| Một horizon thiếu follow-up | `HORIZON_NOT_QUALIFIED_FOLLOWUP`, giữ identity H*; horizon khác report riêng |

Không gọi model forecast pass là structure trading edge. Một kết luận âm đúng, có đủ evidence, là completion hợp lệ của chương trình model-first.

<a id="s10"></a>
## 10. Output và policy forecast chạy được theo thời gian thực

### 10.1. Output contract

Mỗi origin có một record; các con số dưới đây cố ý để null vì chưa có forecast thực:

```json
{
  "schema": "btc_regime_forecast.v1",
  "symbol": "BTCUSDT",
  "target_market": "BINANCE_SPOT",
  "origin_utc": null,
  "input_watermark": null,
  "forecast_ready_at": null,
  "feature_schema_hash": null,
  "model_revision": null,
  "taxonomy_version": null,
  "calibrator_version": null,
  "source_cohort_id": null,
  "horizons": {
    "56": {
      "target_start": null,
      "target_end": null,
      "volatility_probabilities": null,
      "path_probabilities": null,
      "log_vol_quantiles": null,
      "efficiency_median": null,
      "qualification": "NOT_EVALUATED"
    },
    "90": {
      "target_start": null,
      "target_end": null,
      "volatility_probabilities": null,
      "path_probabilities": null,
      "log_vol_quantiles": null,
      "efficiency_median": null,
      "qualification": "NOT_EVALUATED"
    }
  },
  "observed_context": {},
  "observed_duration_context": {},
  "duration_qualification": "NOT_EVALUATED",
  "selected_horizon_days": null,
  "horizon_selection_ref": null,
  "quality": {
    "missing_features": [],
    "excluded_sources": [],
    "fallback_reason": null,
    "probability_calibration_status": "NOT_ASSESSED"
  },
  "forecast_status": "NOT_RUN",
  "financial_trading_authorized": false
}
```

Output `observed_context`, `observed_duration_context` (§4D.10) và `forecast_*` phải tách. Forecast của future-window class không được dùng thay current observed state. Primary H* chỉ được populate bằng pre-TEST horizon-selection record. Không gọi current OI/funding pressure là forecast sẽ xảy ra. Probabilities mỗi head sum1, đúng class order; regression units rõ (logvol, annualizedvolderived, efficiency[-1,1]).

### 10.2. State machine tối thiểu cho forecast, không xây trading controller mới

```text
INPUT_SNAPSHOT_LOCKED
  → DATA_QUALITY_CHECKED
  → INFERENCE_PENDING
  → FORECAST_VALIDATED
  → ATOMICALLY_PUBLISHED
  → OUTCOME_PENDING
  → OUTCOME_MATURED
  → EVALUATED
```

`forecast_id=digest(policy_version,origin,input_hash,target_version,model_revision)` ổn định giữa retry. Không đưa wall-clock now vào semanticID. Duplicate publish không tạo forecast logic thứ hai.

### 10.3. Late/missing/stale policy

- Price reference stale hoặc target inputs mandatory invalid: không publish reliable model forecast; `NO_VALID_INPUT` và baseline/fallback policy nếu đã registered.
- Enrichment field tạm thiếu trong permitted missingness pattern: sử dụng trained missing branch, record mask. Chưa từng qualified missing pattern thì fallback model/schema đã khóa, không drop columns rồi predict bằng sai booster.
- External source đã EXCLUDED không còn là dependency runtime.
- Model task trễ quá `target_start`: không backdate. Baseline forecast từ snapshot cutoff được tính trước như safe research fallback; nếu đã đăng ký dùng fallback thì chấm whole policy gồm fallback. Late model output chỉ diagnostic, không thay prediction ban đầu sau khi window bắt đầu.
- Không có forecast/baseline bắt buộc do job chưa chạy là `INCOMPLETE_RUN`, không gắn bình thường/fallback để đóng phase.
- Không dùng forecast56/90 của tuần trước như forecast56/90 của tuần này mà không đổi target window. Existing forecast gắn exact `[start,end)`; chỉ tái sử dụng khi cùng semantic request.
- Restart phải restore feature/model/taxonomy/calibrator/version/watermarks; không chỉ load weights. Existing predictions bất biến; kết quả mới có newattempt/ref.

### 10.4. Frequency và freshness

Weekly official model forecasts cho research/live-like paper log; daily features vẫn cập nhật. Model weights refit28 ngày; H56/H90 là prediction horizons, không phải wait56/90 mới cập nhật dự báo.

Nếu sau này muốn daily official forecasts, đó là frequency/cost revision trước test; phải so baselines cùng dates, giữ overlap corrections. Long horizon không tự cấp quyền giữ một forecast stale90 ngày.

Không tự tạo cron, stream collector hoặc brokerorders trong năm phase. Shadow deployment thật cần authorization riêng; historical streaming replay được phép trong lab và giới hạn dữ liệu đã có.

<a id="s11"></a>
## 11. Codebase, compute và cách tránh effort không cần thiết

### 11.1. Tái sử dụng có giới hạn

Tái sử dụng reader/feature cache, timestamps, runtime/attempt ledger, source manifests và reporting từ TE/FP/SD. **Không copy cả SD sang một engine mới**.

Các vị trí tham chiếu từ guide/audit cũ, agent phải verify current source:

| Existing responsibility/path | V1.2 reuse hoặc sửa |
|---|---|
| Approved `data_loader` | Read-only source access, bounded export |
| `sd/daily_bars.py`, `sd/jm_features.py` | Daily aggregation/past-only infrastructure; không buộc model mới dùng raw JM states |
| `sd/training_rows.py` | Maturity concept; không dùng hardcoded 56 days cho H56/H90 |
| FP/SD caches, runtime, manifests | Semantic cache IDs và resource accounting |
| `sd/inference_sd03.py` | Chỉ reuse nếu estimand/blocks thực sự đúng; không dùng Sharpe-CI code như Brier-CI bằng rename |
| `fp/evaluator.py`, `integration/event_account.py` | **Chưa gọi ở model-only work**; retain known economic blockers cho WFO bridge |

Có thể thêm `src/crypto_regime_lab/regime_forecast/` với các pure modules `sources`, `features`, `targets`, `splits`, `baselines`, `lgbm_model`, `chronos_adapter`, `calibration`, `evaluation`, `publisher`. Đây là logical proposal, không phải các files đã tồn tại.

### 11.2. Work budget

- Dataset daily gồm vài nghìn origins và <=50 numeric features +masks, không phải hàng triệu order/fill objects.
- Cached engineered features xây một lần, model access theo watermark. Không recompute data cho mỗi head/recipe.
- LightGBM grids nhỏ; sáu estimators/horizon là số tasks thực, không gọi một “model” rồi bỏ qua quantile/readout cost.
- Chronos có một checkpoint/context recipe, batch các targets cùng cutoff. Forecast một lần/origin rồi reuse cho calibration, evaluation và eventual selector candidates; không chạy128 lần theo128params.
- Trước jobs, tính số recipe×horizon×refit blocks×estimators và number of Chronos origin groups; measure một representative task, xét resource quota. Không tự hứa speedup/time estimate từ model-card benchmark.
- Report/metric/bootstrap regeneration dùng stored predictions+labels, `model_inference_calls=0`, `financial_engine_calls=0`.
- Nếu Chronos không fit approved resource, ghi `NOT_FUNDED_CHALLENGER` trước outcome, tiếp tục LightGBM/baselines. Không thêm cloud bill hoặc chọn checkpoint khác sau khi nhìn errors.

### 11.3. Tránh công việc không liên quan

Không yêu cầu native QuantBT E2E test suite, broker certification, options/L2 rebuild hoặc sampler tournament để pass model-only phase. Chỉ kiểm domain boundaries của việc đang chạy. Tests mô tả đủ hành vi, không lặp1.000fixtures để trông nhiều evidence.

Known financial-domain defects vẫn là blockers của **WFO_REENTRY**, không blockers giả của LightGBM forecast training. Tách việc chưa làm với việc không thuộc scope.

<a id="s12"></a>
## 12. MF-01 — Data qualification, scope và source exclusion

### Mục tiêu

Có dataset BTC đủ lịch sử và đúng semantics để nghiên cứu 56/90 ngày. Nguồn phụ thiếu thì bỏ, không chặn core; không bắt đầu bằng tải mọi endpoint.

### Công việc theo thứ tự

1. Ghi branch, commit, dirty diff, approved reader, environment và quota thực. Không khôi phục ZIP cũ đè lên working tree.
2. Đọc [I1], map schema spot/perpetual/metrics bằng bounded samples. Funding/premium chỉ được tải vào research staging trong quyền đã cấp.
3. Chốt target price reference, data version, date range và eligibility theo từng field; xác nhận units và aggregation.
4. Ghi disposition của tất cả nhóm đã bàn: dominance/CoinGecko, OHLCV full, OI/ratios, funding/premium và nguồn ngoài deferred.
5. Lập timeline H56/H90 có warmup, initial matured labels, validation, calibration, test và follow-up. Không co base window để giữ một nguồn phụ.
6. Xuất research snapshot từ server mới sang lab cũ với schema, missingness và hashes. Không đưa toàn bộ raw lake vào RAM.
7. Tạo báo cáo dữ liệu và exclusion list; owner duyệt roster trước khi fit.

### Tests bắt buộc

| ID | Hành vi cần kiểm chứng |
|---|---|
| MF1-T01 | Reader incompatible hoặc sai market/symbol bị từ chối, không bypass manifest |
| MF1-T02 | CoinGecko thiếu lịch sử được EXCLUDED; core build vẫn chạy |
| MF1-T03 | Sai timestamp unit/timezone bị phát hiện; aware/naive conversion giữ đúng thời điểm |
| MF1-T04 | Không cộng OI snapshots; ratios và volumes dùng đúng đơn vị, aggregation |
| MF1-T05 | Source gaps/null không bị đổi thành zero hoặc series forward-filled giả |
| MF1-T06 | Proxy/substituted spot–perpetual data được flag, không tạo spread signal giả |
| MF1-T07 | Timeline và field coverage tái lập từ raw refs, không chọn ngày theo outcome |
| MF1-T08 | Protected paths không bị sửa; exports có bytes/hash thật, không empty-file PASS |

### Exit gate

- **G1-SOURCE:** inputs, market identity, units và permissions rõ.
- **G1-EXCLUDE:** mọi nguồn thiếu có disposition; optional sources không chặn core.
- **G1-TIMELINE:** primary timeline khả thi hoặc có blocker cụ thể của mandatory data; cảH56/H90 có timeline và role rõ, primary chưa chọn tới MF-03.
- **G1-EVIDENCE:** raw refs, report, resource và owner review đầy đủ.

Không có model-skill verdict ở phase này. Thiếu primary target price là blocker thật; thiếu dominance không phải.

<a id="s13"></a>
## 13. MF-02 — Features, targets, observed durations, splits và baselines

### Mục tiêu

Tạo labels dài hạn đúng, thresholds biết từ quá khứ và baseline forecasts thật trước khi tuning model.

### Công việc

1. Implement feature manifest §4, cap 50 numeric features, masks và exact lookbacks; mọi transform chỉ dùng past.
2. Build V/E targets, readiness/publication lags, typed invalid values và taxonomy prefix. Không chuyển label H56 thành H90.
3. Materialize tối thiểu 12 development blocks và 12 locked-test blocks, weekly origin grid, train counts và overlap report.
4. Chạy persistence, historical frequencies, HAR-style và logistic/ridge baselines; lưu forecasts trước khi nối outcomes.
5. Kiểm numerical Brier/log loss/MAE/quantile losses, probability sums, class order và timestamp alignment.
6. Khóa menu H56/H90, horizon-selection rule, thresholds, calibration strategy và inference procedure; H* chỉ chọn sau development ở MF-03.
7. Tạo observed-state tape/episode ledger và duration summaries theo §4D; chạy sensitivity14/28, raw/confirm3, không dùng future-H labels làm current-state truth.
8. Generate baseline và REGIME_DURATION_AND_HORIZON_REPORT development; không đọc TEST labels hoặc future exits để chọn feature/detector schema.

### Tests bắt buộc

| ID | Hành vi cần kiểm chứng |
|---|---|
| MF2-T01 | Thay future prices/metrics không đổi features hoặc baseline predictions trước cutoff |
| MF2-T02 | Label dùng đúng `[start,start+H)`, preceding close và số ngày |
| MF2-T03 | Chưa tới label availability thì row không vào fit; equality cần event-order proof |
| MF2-T04 | Taxonomy H56/H90 có version và freeze trước các forecasts dùng calibration |
| MF2-T05 | Có hơn 12 rows nhưng duplicate origin hoặc thiếu block không được tính đủ 12 |
| MF2-T06 | Endpoint forecast `T+lag+H` khớp future target; step 1 không bị nhận là H-day forecast |
| MF2-T07 | Target null, zero volatility hoặc zero efficiency denominator có status, không epsilon-fix |
| MF2-T08 | Baseline probabilities/metrics khớp numeric oracle; identical models không tạo skill giả |

### Exit gate

- **G2-FEATURES:** transformations, coverage và past-only access đúng.
- **G2-TARGETS:** boundaries, taxonomy và maturity đúng.
- **G2-SPLIT:** các role có đủ origin blocks, overlap và data exposure minh bạch.
- **G2-BASELINE:** có actual forecast ledger, không chỉ script hoặc test fixtures.
- **G2-REGISTRATION:** parameters, thresholds và costs được khóa trước model comparison.
- **G2-DURATION-DEFINITION:** DUR-T01…05 pass; actual observed-state tape, episode ledger và censor-aware report có nguồn, không chỉ plan.

Baseline không cần có skill để technical PASS. Target thiếu class variation phải có specific support limitation; không đổi threshold theo final outcome.

<a id="s14"></a>
## 14. MF-03 — Fit models, duration baseline và chọn horizon trên development

### Mục tiêu

Tách đóng góp của enriched data khỏi đóng góp của model, chọn recipe trước TEST.

### Công việc

1. Chạy default LightGBM trên D0/D1/D2 đủ eligibility, cùng 12 development blocks. Không tạo hai model names cho cùng một matrix.
2. Chọn feature cohort theo §8, thực hiện grid bốn configs và ghi actual fit count; reuse các computations trùng.
3. Pin và load Chronos-2-Synth trong lab; profile một case, kiểm context length, prediction length, grouping và serialization.
4. Tạo endpoint forecasts và readout causal, không fine-tune backbone. Capability/resource failure có disposition trước khi gọi đó là scientific comparison.
5. Chấm proper scores, class metrics, regression errors và diagnostics theo từng block/horizon; giữ mọi losing recipe.
6. Chọn recipe từngH và H* theo §8.4; calibration từ development OOF forecasts có labels đã mature.
7. Fit/đánh giá survival baseline bằng as-of episode ledger; context-hazard chỉ theo conditional scope §4D.7. Khóa timing specification và H* trước TEST.
8. Freeze features, observed-state definition, survival estimator, H*, target taxonomy, checkpoint/model, calibrator, refit rule, fallbacks, TEST dates và thresholds. Không dùng nhãn validation cuối trước lúc available.

### Tests bắt buộc

| ID | Hành vi cần kiểm chứng |
|---|---|
| MF3-T01 | Actual parameters/objectives/features khớp registry; alias conflict bị phát hiện |
| MF3-T02 | Inference current features không cần future labels tồn tại |
| MF3-T03 | Thêm future-origin task vào Chronos batch không đổi earlier forecasts |
| MF3-T04 | Wrong checkpoint/hash hoặc unsupported lengths bị từ chối, không silent truncation |
| MF3-T05 | Calibration không dùng TEST labels hoặc in-sample fitted training logits |
| MF3-T06 | Đổi TEST labels không đổi recipe được chọn trên development |
| MF3-T07 | Failed recipe không thành loss zero/accuracy one; challenger unavailable không chặn primary |
| MF3-T08 | Model restore tái lập predictions trong tolerance; report regeneration không reinfer |

### Exit gate

- **G3-ABLATION:** mọi comparison được diễn giải có ít nhất 12 shared validation blocks.
- **G3-MODEL:** fit/inference và helper integration đúng trên actual path.
- **G3-CALIBRATION:** provenance, support và status có thật.
- **G3-FREEZE:** một recipe được chọn cho mỗi horizon, không TEST peeking.
- **G3-DURATION-AND-HORIZON-FREEZE:** DUR-T06…08 pass; H* và timing spec đã freeze, duration sparse được disposition đúng.
- **G3-REPORT:** không gọi development selection là confirmation; owner duyệt locked test.

Development yếu vẫn có thể được owner cho phép chạy một final falsification test. Không tuning tới khi validation dương; không tự mở thêm TFT/Kronos/JM grid.

<a id="s15"></a>
## 15. MF-04 — Locked test, qualification từng head/horizon và timing

### Mục tiêu

Đo pipeline đã khóa và xác định forecast skill trước mọi WFO rerun.

### Công việc

1. Verify freeze/source/data/model, chạy chronology trên đủ 12 TEST blocks hoặc exact N đã đăng ký.
2. Refit weights mỗi 28 ngày chỉ từ matured labels; không chọn lại recipe, taxonomy, thresholds hoặc calibrator theo TEST.
3. Persist forecasts trước outcomes; kiểm streaming replay và batch sử dụng cùng information set.
4. Chấm các heads trên common cohort; ghi đầy đủ failed predictions, fallback và abstention denominators.
5. Báo proper scores, balanced accuracy, macro-F1, confusion matrix, hits/misses/false alarms, reliability, forecast error và interval coverage/width.
6. Tính uncertainty theo time blocks đã pin; trình bày concentration, rare-class support và follow-up của H56/H90. Đo timing/p_exit/remaining-time riêng theo §4D.8, không quay lại sửa detector/H*.
7. Grade riêng từng task/horizon theo §9; lưu đủ predictions/labels để tái tính không gọi model.

### Tests bắt buộc

| ID | Hành vi cần kiểm chứng |
|---|---|
| MF4-T01 | Đủ shared-valid blocks và expected origins, không chọn 12 rows tốt nhất |
| MF4-T02 | Metrics được tái tính từ sealed predictions/labels, không nhập số tay |
| MF4-T03 | Bootstrap tôn trọng horizon overlap; variant wrap-around được implement đúng |
| MF4-T04 | Abstention không xóa ngày khó; coverage và failures reconcile |
| MF4-T05 | Missing/rare class không làm balanced accuracy tăng giả; support rõ |
| MF4-T06 | Thiếu maturity của H* không bị thay bằng horizon khác; report đầy đủ haiH và support thực |
| MF4-T07 | Model/threshold/horizon không đổi sau outcomes; changed hash bị phát hiện |
| MF4-T08 | Streaming/batch parity đạt; late/duplicate record không backdate hoặc overwrite |

### Exit gate

- **G4-EXEC:** locked forecasting thật đã chạy, không chỉ files tồn tại.
- **G4-EVAL12:** counts, cohort, target maturity và paired comparisons đúng.
- **G4-INFERENCE:** procedure phù hợp hoặc explicit LOW_PRECISION, không fake confidence.
- **G4-HEADSTATUS:** từng head/horizon có qualified/not-qualified disposition.
- **G4-TIMING-EVAL:** DUR-T09…10 pass; per-state durations/first-exit/remaining-time có measured status hoặc support limitation, không giả KM output là ML skill.
- **G4-EVIDENCE:** raw predictions, labels, hashes và report đủ.

Technical PASS có thể đi cùng no-skill/inconclusive. Khi model chưa qualified, WFO gate vẫn CLOSED; không thử tài chính để tìm một kết quả dương bù lại.

<a id="s16"></a>
## 16. MF-05 — Báo cáo hợp nhất, freeze/replay và WFO gate

### Mục tiêu

Bàn giao model-quality report và forecast policy có thể replay, để Bobby quyết định có đáng quay lại WFO không.

### Công việc

1. Kết luận data nào có ích, model nào hơn baseline, target/horizon nào đạt, sai ở đâu và uncertainty ra sao.
2. Tạo `RPS_CURRENT.md`, `MODEL_QUALIFICATION.json`, exclusion list, version manifest và resource summary.
3. Freeze package an toàn; kiểm restore, streaming, late/fallback behavior trong lab, không production writes.
4. Điền bridge proposal §18 chỉ bằng qualified heads/horizons. H* không đạt thì CLOSED; volatility của H* đạt nhưng path chưa đạt chỉ hỗ trợ đề xuất volatility-conditioned research. Duration report và timing qualification được bàn giao riêng, không thay forecast certificate.
5. Không chạy financial engine. Owner xem qualification report rồi quyết định có mở một WFO registration riêng hay không.
6. Giữ nguyên SD/FP/RPS historical results; sửa narrative bằng correction record liên kết nguồn cũ. Không tạo phase thứ sáu để tiếp tục tuning.

### Tests bắt buộc

| ID | Hành vi cần kiểm chứng |
|---|---|
| MF5-T01 | Tampered prediction/model hash/scalar hoặc missing payload làm verifier FAIL |
| MF5-T02 | `complete=false` hoặc PENDING approval không PASS chỉ vì có key/file |
| MF5-T03 | CoinGecko đã excluded không xuất hiện như required runtime input |
| MF5-T04 | Restore giữ model, taxonomy, calibrator và forecast IDs; weights-only không đủ |
| MF5-T05 | Model qualification không tự cấp WFO authorization hoặc live approval |
| MF5-T06 | H90 không được gọi qualified cho H56 hoặc ngược lại; mean duration/remaining-time không tự là refit cadence |
| MF5-T07 | Final-report/handoff regeneration không gọi inference/engine khi outputs đã đủ |
| MF5-T08 | Git changes có scope, protected states và budget rõ; không rewrite history |

### Exit gate

- **G5-REPORT:** methodology, results và limitations đầy đủ, truy được evidence.
- **G5-REPRODUCE:** package restore và report replay có actual evidence.
- **G5-SCOPE:** excluded sources không còn dependency, không mở việc ngoài quyền.
- **G5-BRIDGE:** proposal chỉ dùng allowed tasks/horizons hoặc ghi CLOSED.
- **G5-DURATION-HANDOFF:** DUR-T11…12 pass; duration report, H* rationale, supported/unsupported timing fields và future policy boundary đầy đủ.
- **G5-OWNER:** bàn giao đúng scope và review có reference thật.

**Technical completion không đòi accuracy đẹp.** Đây là điểm dừng để Bobby quyết định, không phải lời hứa tự triển khai giao dịch.

<a id="s17"></a>
## 17. Báo cáo mỗi run, upgrade và verifier

### 17.1. Bốn trạng thái tách biệt

```text
implementation_status: NOT_STARTED | RUNNING | COMPLETE | BLOCKED
technical_gate: NOT_RUN | PASS | FAIL | BLOCKED
model_skill_status: NOT_ASSESSED | OBSERVED_SKILL_LOW_PRECISION | ... per-head result
owner_review: PENDING | APPROVED | CHANGES_REQUESTED
```

Không dùng `COMPLETE` của code để nói model có skill. Một head không đủ bằng chứng không làm mất các kết quả của head khác; mọi giới hạn được tổng hợp rõ.

### 17.2. Logical artifact layout

```text
configs/btc_regime_forecast_v1/
  registration.json
  protocol_migration.json
  source_allowlist.json
  feature_manifest.json
  target_taxonomy.json
  observed_state_spec.json
  duration_protocol.json
  horizon_selection.json
  timeline_and_maturity.json
  model_roster.json
  calibration_plan.json
  analysis_and_thresholds.json
  resource_budget.json
  final_freeze.json

evidence/btc_regime_forecast_v1/
  runs/<run_id>/
    request.json
    attempts/
    source_refs.json
    input_and_feature_refs.json
    model_refs.json
    forecast_ledger_refs.json
    matured_label_refs.json
    metrics.json
    report.md
    gate_receipt.json
    detached_seal.json
  source_exclusions.json
  validation_matrix.json
  qualification_by_head.json
  observed_state_tape.parquet
  regime_episode_ledger.parquet
  regime_duration_summary.json
  survival_curves.json
  remaining_time_forecasts.jsonl
  REGIME_DURATION_AND_HORIZON_REPORT.md
  upgrade_ledger.jsonl

handoff/
  RPS_CURRENT.md
  RPS_MODEL_FORECAST_RUNBOOK.md
```

Đây là mapping đề xuất vào infrastructure hiện có. Không tạo thêm database/service chỉ để có những tên files trên. Raw data có thể ở verified storage, nhưng portable package phải có đủ refs/payload thực để reviewer tính lại metrics; không chỉ danh sách hashes viết tay.

### 17.3. Run report mẫu — mọi attempt đều có

```markdown
# MF Run Report — <run_id>

## Identity và câu hỏi
Phase, registration, branch/commit/diff, data/model versions.
Task, target, horizon, metric primary, comparator.
Đây là training, development, locked retrospective hay prospective?

## Data
Sources used/excluded và lý do; spot/perp identity.
Coverage theo field, missingness, source revisions và dataset hashes.
Feature count, target taxonomy, snapshot/availability.

## Planned vs actual
Daily training rows; matured labels; weekly prediction origins.
Validation/test blocks; horizon overlap; folds thiếu/undefined.
Models/configs/estimators đã fit; inference calls và failed attempts.

## Method và leakage checks
Feature end, label end/available time, taxonomy/calibration timing.
Chronological splits, foundation provenance và batch isolation.
Những model hoặc nguồn không được chạy, không gắn nhãn đã thua.

## Kết quả
Brier/log loss, balanced accuracy, macro-F1, confusion matrix.
MAE/quantile loss, reliability, interval coverage + width.
Precision/recall/false alarms + coverage và event support.
Từng horizon/block/head; uncertainty và paired baseline improvement.

## Timing và horizon
Observed-state definition khác future-label taxonomy; lookback/confirmation sensitivity.
Per-state episodes, censored/unknown onset, median/IQR/RMST và risk sets.
Age hiện tại, remaining-time/first-exit forecasts và calibration status.
H* đã chọn trên development, metric/duration rationale; TEST không chọn lại.
Không báo forecast-label persistence như market dwell hoặc durationmean như refit interval.

## Giải thích
Data block nào bổ sung skill? Model nào cải thiện trên cùng inputs?
Signal có chỉ từ volatility persistence/missingness/source change không?
Forecast dài hạn có còn skill, hay chỉ các targets chồng lấn dễ dự báo?

## Resources và reuse
CPU/wall/peak memory; source reads; cache hits/misses.
Model fits/inferences; financial_engine_calls phải bằng0 trong scope này.
Cost đã dùng và còn lại; retry waste.

## Gates và kết luận
Expected vs actual vs evidence hash cho từng gate.
Technical status; per-head qualification; owner review.
Điều chưa được chứng minh; WFO_REENTRY=CLOSED hoặc proposal_pending.

## So với run trước
Comparable contract hay không? Thay source/target/model/calibration gì?
Results/claims nào bị invalidate? Reuse phần nào có dependency proof?

## Next authorized action
Một hành động cụ thể trong scope đã được duyệt.
```

### 17.4. Upgrade discipline

| Thay đổi | Hành động |
|---|---|
| Prose/format | Regenerate report, không gọi model hoặc engine |
| Metric/calibration bug | Recompute affected outputs, preserve raw predictions; đánh dấu claims cũ |
| Feature/source correction | Invalidate affected features, fit/inference và downstream metrics |
| Horizon/target/taxonomy | New target version; không reuse labels bằng rename |
| Observed-state detector/duration protocol | New tape/episode/estimator version; preserve old decisions, rerun affected timing diagnostics, không reset age ngầm |
| LightGBM/Chronos/checkpoint/readout | New model version, freeze trước test cần thiết; data exposure ghi lại |
| Runtime optimization | Prove same predictions/timestamps trong tolerance; benchmark thật |
| Future WFO economics fix | Invalidate financial caches tương ứng, không giả report-only |

`upgrade_record` gồm parent/newversion, reason, exact diff, source/metric dependencies, before/after test/run refs, numbers thay đổi, resources, owner approval và affected claims. Không rerun mọi thứ khi chỉ sửa report; cũng không giữ caches sai khi đổi semantics.

`RPS_CURRENT.md` được tạo lại sau mọi run/upgrade, gồm current source, newest valid evidence, qualification từng head/H, selectedH*, duration/survival support, nguồn bị loại, known blockers, budget và next action. Nó không cấp quyền sửa rules theo outcome.

### 17.5. Verifier tối thiểu nhưng thực chất

- Đọc bytes và recompute hashes; missing payload hoặc mutated forecast làm FAIL.
- Check required gate registry riêng, không tin receipt tự đưa required_gates rỗng.
- Check values `complete=true`, owner content/scope/version; không chỉ key/file tồn tại.
- Recompute metric, class order, target window, number of origins/blocks và maturity từ raw refs.
- Mandatory tests cần actual execution logs; no-collection/skip/xfail không là PASS cho case bắt buộc.
- Source/model receipt cùng dependency version; sửa README không invalidate model coefficients, sửa target formula có invalidate labels.
- Receipt finalized trước detached seal; không self-hash hoặc sửa receipt sau seal mà không tạo version mới.
- Test mutation ở bản copy: future label, timezone, model revision, one forecast scalar, duplicate block, missing core target, missing optional source. Optional-source exclusion phải đi qua nhánh nonblocking đã định, không vô tình làm gate fail toàn bộ.

CLI mới chỉ là đề xuất, phải map parser hiện có và kiểm `--help`: `plan`, `prepare-data`, `build-labels`, `fit`, `predict`, `evaluate`, `verify`, `report`, `freeze`. Không ghi một QuantBT/loader API chưa tồn tại rồi bắt agent gọi nó. Không chạy arbitrary commands trên server mới nếu chưa được cấp quyền.

<a id="s18"></a>
## 18. WFO regime-edge bridge — bảo toàn parameters đã bàn, CHƯA chạy

### 18.1. Điều kiện mở lại

```text
FORECAST_MODEL_QUALIFIED đúng head/horizon
+ feature-only historical forecast lineage hợp lệ
+ owner duyệt WFO study mới
+ financial domain gates đạt
→ mới cấp quyền chạy WFO experiments.
```

Không tự mở WFO chỉ vì LightGBM fit xong hoặc accuracy một class cao. Chỉ dùng H* và heads thực sự đạt; secondaryH có kết quả tốt không tự thay primary hoặc mở WFO. Mean duration và duration-model skill là qualifications riêng. Model chỉ volatility-qualified thì nghiên cứu volatility-conditioned selection, không gọi full trend/flow regime edge.

Model forecast có thể đúng nhưng không giúp chọn params. Việc nối lại là **thử nghiệm tiếp theo**, không hệ quả tất yếu hoặc phần mặc định MF-05 phải chạy cho xong.

### 18.2. Giữ QuantBT và baseline Mode 4

Financial authority duy nhất vẫn QuantBT, actual version/native/module origin được pin. Binding stock cần kiểm trên package thực:

```text
optimization_mode          = mode_4_is_only_robust
optimization_schedule      = per_fold_causal
candidate_selection_metric = is_only_robust
scoring_backend            = endpoint
```

Không thay stock selection bằng max objective hoặc giả raw metrics. Context selector là extension có tên/version riêng; không gọi là stock mode không đổi.

Scope future: A-SC/BTCUSDT/15m; execution1m nếu giữ semantics. Target-model dùng spot price không tự đổi asset/contract mà A-SC giao dịch. Funding/shorting/leverage/economic assumptions phải được resolve cho actual instrument.

### 18.3. Trials, sampler và full pool

- **>=128 attempted strategy trials/cutoff**, 2–3 effective tuning dimensions; raw attempted/completed/failed/pruned/unique counts.
- TPE baseline + Sobol/QMC đối chứng sau khi mở WFO; multivariate TPE optional chỉ trước outcome. Không mở CMA/GP/TFT hàng loạt vì một kết quả yếu.
- Same authoritative IS scorer và stock selector. QMC categorical/first-trial behavior cần pin; adapter thiếu public capability thì integration blocker, không monkeypatch protected engine.
- A/B/C/controls có cùng full candidate pool trong mỗi sampler. Label panel không hạn chế prediction domain; anchor và mọi winners phải có financial outcomes.
- 16 representative labels/origin có thể tiết kiệm compute, phải balance top/diversity/mid-lower controls trước OOS; union winners freeze trước forward evaluation.
- Tất cả samplers/models dùng same labels/economics availability rules. Không chọn best seed hoặc loại sampler vì IS max thấp hơn.

Đây là parameters của future WFO experiment, không ML hyperparameter tuning hiện tại.

### 18.4. Regime feature và relative Sharpe-decay selector

Chỉ dùng **forecasts đã phát hợp lệ tại origin** làm historical context, không dùng realized future regimes hoặc forecast được tạo bằng future-trained model rồi gắn nhãn causal. Model/backbone phát hành muộn phải có transfer-study disclosure; strict historical-live claim không được suy từ input cutoff alone.

Với anchor a và candidate θ:

\[
D_{\theta}=SR_{IS,\theta}-SR_{FWD,\theta},\qquad
Y_{\theta}=D_{\theta}-D_a.
\]

\[
v_\theta=\phi(z_\theta)-\phi(z_a),\quad
\widehat Y_B=\beta^Tv_\theta,\quad
\widehat Y_C=\beta^Tv_\theta+v_\theta^TGf_T.
\]

`f_T` gồm probabilities/continuous forecasts/uncertainty/masks **của heads đã qualified**. Candidate–context interaction cần thiết để thay ranking; một pure market intercept cộng giống nhau không đủ. Anchor prediction0 theo contrast architecture.

Safeguard identity:

\[
\widehat Q(\theta)=SR_{IS,\theta}-SR_{IS,a}-\widehat Y(\theta).
\]

Guard starting margin vẫn `Q_hat >= -0.10` điểm Sharpe; chọn min predicted signed Y. Không absolute daily-return hurdle, không đòi SR/delta đổi dấu. C được chấm độc lập ngay cả khi B chọn anchor. Unsupported forecast fallback global/stock proposal tại current cutoff, không vô tình giữ một bộ tham số hàng trăm ngày.

### 18.5. Horizon, regime lifetime và WFO clocks không được đổi ngầm

Candidate IS180 ngày vẫn là baseline tham chiếu; nó không quyết định forecast horizon hoặc model-fit memory.

- H56 đủ skill cho mục tiêu56 ngày mới cho phép **đề xuất** standardized FWD56, fixed selection calendar56 và D2 gồm hai56-day windows. H90 tương ứng proposal FWD90/cadence90/D2hai90; mọi financial scope đều cần owner registration trước outcomes.
- Có thể dùng forecastH90 làm background cho selection56 nếu đăng ký rõ bài toán khác; không gọi nó đã được qualified để dự báo đúng target56 chỉ bằng rename. Tương tự H56 không đủ để giữ cùng params90 ngày mà chưa kiểm.
- Empirical mean/median dwell không tự bằng forecastH, kỳ refit hoặc tuổi hiệu dụng của params. Chọn params có thể giữ tốt qua một số regime transitions; state đổi cũng chưa chắc nên thay params.
- `current_age`, `p_first_exit` và restricted remaining time chỉ được đưa vào selector như thêm context khi lineage/calibration đạt và ablation đã đăng ký. Predictive-state future realization không được quay lại làm feature hiện tại.
- Dynamic refit hoặc adaptive horizon theo exit hazard **không thuộc nămphase model-first này**. Cần một future policy study riêng, đối chứng calendar và compute budget; không tự bật vì có survival curve.
- Vẫn giữ >=128 attempted strategy trials/cutoff, >=12 paired-valid WFO folds, full eligible pools, stock Mode4 và controls ở các mục liền kề. Counts model forecasting hoặc duration episodes không thay WFO fold requirements.
- Timeline future WFO phải chứng minh actual initial/meta-label history, latency, commoncalendar và D2 follow-up đủ. Thiếu thì WFO gate CLOSED, main model/duration study vẫn kết luận được đúng scope.

### 18.6. Controls và claim đã bàn giữ nguyên cho giai đoạn sau

1. Stock Mode4 A.
2. Global decay selector B0.
3. Pooled/capacity correction control B_CAP.
4. Observed-context selector nếu cần tách data-information khỏi forecast-information.
5. Predictive-context C từ model đã qualified.
6. No-information controls với seeds/tape rules trước outcome khi cần claim information-specific edge.

Không buộc chạy tất cả trong MF; roster future phải bounded và có budget riêng. C−B_CAP và C−observed-context giúp phân biệt thêm capacity/đọc market hiện tại với thực sự dự báo tốt hơn. Không chọn final comparator yếu nhất.

Primary future trading metric vẫn **Sharpe decay reduction** trên common dates, không bps/day. Defaults giữ để owner freeze: meaningful reduction 0.20 Sharpe; OOS/account noninferiority margin 0.10. Giảm từ 1.30 xuống 0.85 là giảm 0.45 dù decay còn dương. Luôn phân rã phần IS-reference và forward-retention; không gọi gap nhỏ vì IS kém là giữ edge tốt.

### 18.7. Financial domain gates trước mọi rerun

- Indicator-only warmup: trước economic start không order/fill/position/cash drift.
- Sizing thật: fraction 0.10 của engine equity tại entry khi contract đó được chọn; không constant 2000 trá hình.
- Cutoff < ready <= permissible activation; cache không làm ready bằng 0. Alpha decision15m next-open execution có proof.
- Admission trước engine consumes params. C không bị B short-circuit.
- Continuous accounts giữ actual order/campaign ownership, không ghép normalized fold equities.
- Same-state standardized candidates khác live incumbent counterfactual; D2 đúng frozen continuation.
- Raw daily equity/returns và reconciliation được export, không chỉ counts hoặc mean fold Sharpes.
- Old SD labels chịu pre-roll/sizing defects phải invalidate theo dependency, không reuse vì scalar checksum đúng.

### 18.8. Live policy bridge kế thừa, không live permission

Forecast updated theo cadence đã qualified; tại registered WFO cutoff dùng đúng forecast packet known. Param proposal có full input/model/feature/forecast/pool hashes, nominal/actual readiness, expiry, expected-incumbent version và monotonic sequence.

Same params được `REVALIDATED_SAME_PARAMS` mà không reset indicators/positions. Expired/late proposal không activate ngược thời gian. Pending campaign theo rule alpha, không force-close thuận lợi cho C. Duplicate/restart phải idempotent. Safety pause chặn new entries nhưng bảo vệ exits/reconciliation.

Legacy TTL7days/max-revalidation112days phải được đánh giá theo cadence56/90 đã chọn và actual latency; không suy durationmedian thànhTTL; phải materialize lại deadlines trước trading study, không copy values mâu thuẫn. Broker/venue/approval hiện có giữ nguyên; no API trading keys hoặc orders trong scope tài liệu này.

<a id="s19"></a>
## 19. Minimal config, acceptance và Definition of Done

### 19.1. Config logical để agent map vào implementation

```yaml
study_id: btc_regime_forecast_v1
guide_version: BTC-RPS-V1.2-MODEL-FIRST-DURATION
status: SPECIFICATION_NOT_RUN
scope:
  symbol: BTCUSDT
  venue: BINANCE
  model_target_price_reference: SPOT
  future_alpha_id: A-SC
  future_alpha_timeframe: 15m
sources:
  required: [approved_spot_price]
  preferred_if_full_coverage: [spot_full_fields, perp_full_fields, oi, long_short, funding, official_premium]
  external_default: EXCLUDE_UNLESS_ALREADY_FULLY_QUALIFIED
  missing_external_blocks_core: false
  paid_data_allowed: false
  canonical_writes_allowed: false
features:
  numeric_cap: 50
  preset_numeric_max: 48
  base_windows_days: [7, 30, 90, 180]
  missing_policy: source_specific_no_forward_fill_direct_metrics
forecast:
  candidate_horizons_days: [56, 90]
  selected_primary_horizon_days: null
  horizon_selection_status: PENDING_VALIDATION
  selection_rule: VALIDATION_NORMALIZED_PROPER_LOSS_DURATION_INTERPRETATION
  horizon_tie_relative_tolerance: 0.01
  horizon_tie_preference_days: 56
  secondary_horizon: OTHER_REGISTERED_HORIZON_NO_POST_TEST_PROMOTION
  forecast_180_active: false
  data_frequency: 1d_UTC
  official_origin_stride_days: 7
  refit_stride_days: 28
  ready_lag_days: 1
  ready_lag_status: REQUIRES_QUALIFICATION
  labels: [volatility_3class, efficiency_3class]
  continuous_targets: [log_future_volatility, future_efficiency]
duration:
  state_axes: [OBS_VOL, OBS_PATH]
  tape_frequency: 1d_UTC
  primary_detector: OBS14_CONFIRM3_V1
  lookback_days: 14
  confirmation_observations: 3
  sensitivity_lookbacks_days: [14, 28]
  sensitivity_confirmations: [1, 3]
  taxonomy_past_daily_rows_min: 365
  independent_of_forecast_horizon: true
  unknown_initial_onset: EXCLUDE_KNOWN_ONSET_ESTIMATOR_KEEP_RECORD
  ongoing_at_fit_cutoff: RIGHT_CENSORED
  missing_gap: CENSOR_NO_BRIDGING
  estimator: KAPLAN_MEIER_BY_STATE
  min_known_onset_episodes: 10
  min_observed_exits: 5
  min_at_risk_for_probability: 5
  restricted_mean_limit_days: 90
  first_exit_horizons_days: [14, 28, 56, 90]
  context_hazard_default: NOT_RUN_CONDITIONAL_SCOPE
  sparse_timing_blocks_main_forecast: false
  adaptive_wfo_trigger_allowed: false
splits:
  min_initial_matured_daily_origins: 730
  min_validation_blocks: 12
  min_locked_test_blocks: 12
  origin_block_days: 28
  label_overlap_allowed: true
  label_overlap_must_be_reported: true
  train_filter: label_available_at_before_fit_cutoff
  iid_inference_forbidden: true
  dates: null
models:
  primary: LIGHTGBM_SUPERVISED
  foundation_challenger: autogluon/chronos-2-synth
  backbone_finetune: false
  chronos_context_steps: 512
  checkpoint_revision: null
  lgbm_grid_size: 4
  baselines: [PERSISTENCE, MATURED_FREQUENCIES, HAR_STYLE, REGULARIZED_LINEAR]
qualification:
  brier_skill_point_min: 0.05
  balanced_accuracy_gain: 0.05
  regression_error_reduction: 0.10
  confidence_level: 0.95
  graded_separately_by_head_and_horizon: true
resources:
  allocation: null
  must_profile_before_bulk: true
wfo:
  status: CLOSED_PENDING_MODEL_QUALIFICATION_AND_OWNER
  current_phase_engine_runs_allowed: 0
  future_strategy_trials_min: 128
  future_paired_wfo_folds_min: 12
  future_candidate_IS_days_reference: 180
  future_horizon_mapping: REQUIRES_NEW_WFO_REGISTRATION
  target_metric: SHARPE_DECAY
live_trading_authorized: false
```

`null` fields và resource/dependency details phải được resolve ở phase cần chúng. Đây không phải command/API đã tồn tại hoặc certificate từ chỉ dẫn. Không silently default dates, versions hoặc quota để chạy.

### 19.2. Hoàn thành đúng phạm vi khi

- [ ] Nguồn thiếu historical như CoinGecko đã exclude, không block hoặc tạo collector chờ vô hạn.
- [ ] Target reference và spot/perp/units/funding definitions đúng nguồn.
- [ ] Features có manifest/formulas/cutoffs; <=50numeric, không full-sample transforms.
- [ ] H56/H90 cùng menu và cohort; H* chọn bằng development rồi freeze trước TEST, endpoint/lag đúng; không mặc định horizon dài dễ hơn.
- [ ] Observed-state tape độc lập futureH; durations/recurrence/age/censoring có định nghĩa và source lineage.
- [ ] Per-state median/IQR/RMST, survival/risk sets, remaining time và sensitivity có actual report hoặc measured sparse-support status.
- [ ] DUR-T01…12 đã chạy theo phase; mean lifetime không bị dùng thay remaining time hoặc WFO cadence.
- [ ] Labels independently defined, taxonomy frozen, no future training/calibration.
- [ ] >=12validation và >=12lockedtest origin blocks, overlap/ESSlimitations được báo.
- [ ] Baselines đủ mạnh, LightGBM actualparameters, một Chronos challenger hoặc honest capability disposition.
- [ ] Per-head accuracy/hitrate/properloss/regressionerrors/reliability được đo cùng samples.
- [ ] Modelskill/uncertainty/negative results có đúngscope, không épaccuracy80%.
- [ ] Forecast output có fulltimestamps/version, restart/replay/latepolicy đúng.
- [ ] Mọi run/upgrade có evidence và updated RPS_CURRENT, không overwrite lịch sử.
- [ ] WFO vẫn CLOSED nếu chưa có qualification và owner approval; giữ nguyên128 trials và 12 paired folds khi mở riêng.
- [ ] Final report đủ để Bobby quyết định model nào, inputs gì, horizon nào đáng nghiên cứu tiếp.

**Đích đến V1.2:** trước hết có một model dự báo các điều kiện BTC 56/90 ngày tốt hơn baselines trong một phạm vi kiểm định minh bạch. Sau đó mới nghiên cứu thông tin ấy có giúp chọn params ít Sharpe decay hơn. Không lấy một phép thử WFO dương thay qualification forecast, cũng không lấy forecast skill làm chứng nhận giao dịch có lãi.

<a id="s20"></a>
## 20. Sources và phân biệt evidence với đề xuất

Các nguồn E1–E10 được giữ từ bản soạn27/09/2026; V1.2 bổ sung kiểm E11–E15 ngày28/09/2026 về duration/survival/online detection, không tuyên bố đã kiểm lại mọi endpoint ngoài phạm vi lần sửa này. Không dùng ngày crawl của website làm timestamp availability của historical market data. Website docs mới không cấp phép upgrade dependency đang chạy.

### Nguồn nội bộ

**[I1] `CONSUMER_ENDPOINTS.md`**, bản user cung cấp: consumer boundaries lines3–38; market scopes44–55; full OHLCV fields101–109; OI/ratios/depth127–131; frozen/proxy boundaries244–280; coverage283–304. Chỉ đọc data, không canonicalwrite.

**[I2] Guide BTC-RPS-V1.0**, lineage gốc; **parent trực tiếp là BTC-RPS-V1.1 MODEL-FIRST ngày27/09/2026** với SHA-256 ở đầu file. Model-first migration thay active phases; source/Git/economic/WFO invariants và lessons learned được giữ.

**[I3] SD audit 26/09/2026**, source/probes về pre-roll, fixed-notional mismatch, semantic-state alignment và missing continuous-account outputs. Findings thuộc snapshot, phải verify source hiện hành trước khi gán tình trạng host.

### Tài liệu primary bên ngoài

**[E1] Binance public data** — schema/vendor fields, checksum và archive changes. Không bảo đảm mọi instrument/date đều đủ.

```text
https://github.com/binance/binance-public-data
```

**[E2] Binance USD-M market-data documentation** — OI, funding, premium/index/mark klines và source-specific retention/units. Reader contract của bạn vẫn là authority cho capability đã released trên server.

```text
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data
```

**[E3] CoinGecko historical access** — public historical limit và Pro global-history endpoint. Điều này hỗ trợ exclude thiếu lịch sử, không yêu cầu mua plan.

```text
https://support.coingecko.com/hc/en-us/articles/4538747001881-What-granularity-do-you-support-for-historical-data
https://docs.coingecko.com/reference/global-market-cap-chart
```

**[E4] LightGBM official docs** — objectives, parameters, missing handling và probability warning khi reweight classes. Hyperparameters trong guide là defaults thiết kế, không copy một benchmark đã chứng minh BTC skill.

```text
https://lightgbm.readthedocs.io/en/stable/Parameters.html
https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMClassifier.html
```

**[E5] scikit-learn probability calibration** — proper scores, reliability và yêu cầu phân biệt calibration/discrimination. Không biến một ECE/Brier thấp thành ground-truth regime certificate.

```text
https://scikit-learn.org/stable/modules/calibration.html
```

**[E6] Chronos-2-Synth/model card và Chronos-2 paper** — synthetic-only variant; multivariate/covariates/quantiles; group-attention. Research benchmark của authors không là BTC regime/WFO evidence.

```text
https://huggingface.co/autogluon/chronos-2-synth
https://huggingface.co/autogluon/chronos-2
https://arxiv.org/html/2510.15821v1
```

**[E7] Corsi (2009), A Simple Approximate Long-Memory Model of Realized Volatility** — ý tưởng multi-horizon HAR baseline; V1.2 direct 56/90 adaptation là thiết kế riêng cần kiểm, không tuyên bố replicate paper.

```text
https://doi.org/10.1093/jjfinec/nbp001
```

**[E8] Hyndman & Athanasopoulos, Forecasting: Principles and Practice, §5.5** — forecast distributions và uncertainty theo horizon. Không có căn cứ mặc định 90 ngày chính xác hơn 56 ngày; đây không phải kết quả đã đo của BTC.

```text
https://otexts.com/fpp3/prediction-intervals.html
```

**[E9] Cawley & Talbot (2010), On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation** — nguyên tắc tách development và outer evaluation. Temporal implementation cụ thể, purging và support floors trong guide là thiết kế V1.2, không suy paper đã chứng minh chúng tối ưu.

```text
https://www.jmlr.org/papers/v11/cawley10a.html
```

**[E10] Optuna documentation về samplers/reproducibility** — chỉ liên quan WFO bridge đang khóa; không phát sinh sampler sweep trong model qualification.

```text
https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html
https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.QMCSampler.html
https://optuna.readthedocs.io/en/stable/faq.html
```

**[E11] NIST — Censoring.** Phân biệt observed events và right-censored observations tại thời điểm dừng theo dõi; không dùng episode đang mở như một lifetime đã hoàn tất.

```text
https://www.itl.nist.gov/div898/handbook/apr/section1/apr131.htm
```

**[E12] NIST — Kaplan–Meier empirical estimation.** Risk sets, observed events và product-limit survival estimation. Áp dụng cho defined regime episodes là thiết kế của lab, không chứng minh Bitcoin có một lifetime distribution ổn định.

```text
https://www.itl.nist.gov/div898/handbook/apr/section2/apr215.htm
```

**[E13] lifelines official documentation — restricted mean survival time.** RMST tích phân survival tới một giới hạn, không phải full mean nếu tail chưa quan sát; nếu dùng package phải pin version/API và tests, không tự upgrade môi trường.

```text
https://lifelines.readthedocs.io/en/latest/lifelines.utils.html#lifelines.utils.restricted_mean_survival_time
```

**[E14] Adams & MacKay (2007), Bayesian Online Changepoint Detection.** Posterior run length từ online observations; không đồng nghĩa có economic state labels hoặc calibrated remaining-life predictor cho BTC. Reference, không active dependency V1.2.

```text
https://arxiv.org/abs/0710.3742
```

**[E15] Johnson & Willsky (2013), Bayesian Nonparametric Hidden Semi-Markov Models.** HMM geometric-duration constraint và explicit-duration alternatives; tham khảo để không coi HMM-implied durations là empirical fact. Không mở HSMM research family trong bản này.

```text
https://www.jmlr.org/papers/v14/johnson13a.html
```

**Tuyên bố phạm vi cuối:** đây là phương án thực nghiệm và implementation guide mới. Không có duration trung bình BTC, remaining-time forecast, accuracy, hit rate, forecast-skill gain hoặc Sharpe-decay result mới nào được tuyên bố đã đo chỉ từ tài liệu này.
