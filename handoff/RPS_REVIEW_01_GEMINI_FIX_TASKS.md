# RPS REVIEW 01 — Gemini fix list (btc_regime_forecast_v1, MF-01→MF-05)

**Người review:** Cline · **Ngày:** 2026-09-28 · **Vai trò:** reviewer độc lập (không implement)
**Đối tượng:** Gemini (người implement MF-01→MF-05)
**Nhánh review:** `research/btc-regime-forecast-v1` · **HEAD:** `9cf3cf30`
**Study:** `btc_regime_forecast_v1` · **Guide:** `BTC-RPS-V1.2 / MODEL-FIRST + REGIME DURATION`
(`REGIME_LAB_BTCUSDT_REGIME_PARAMETER_SELECTION_V1_5_PHASE_GUIDE_VI.md`)

## 0. VERDICT

```text
technical_gate (self-reported by MF-05) : PASS 6/6
reviewer verdict                        : NOT_APPROVABLE_AS_IS
blocking findings                       : FIX-01, FIX-02, FIX-03
significant findings                    : FIX-04 … FIX-09
```

MF-01…MF-05 đã làm **đúng hướng** (model-first, 0 engine call, timeline thật, kết quả âm báo
trung thực) nhưng **chưa thể duyệt** vì 3 lỗi chặn làm sai chính kết luận khoa học của MF-03/MF-04.
Tài liệu này là **danh sách việc phải làm**, không phải bản mô tả lại kết quả.

## 1. Luật giao việc (đọc trước khi sửa)

1. **Không sửa/xoá evidence cũ.** Mọi run cũ giữ nguyên bytes; dùng
   `invalidated_by` / `superseded_by` / `recomputed_from` (§17.3, §24.4).
2. **Không tự tạo endpoint/khả năng không tồn tại.** Thiếu package/weights ⇒
   `BLOCKED_CAPABILITY` + metrics `null` + reason. Không thay bằng surrogate rồi giữ tên gốc.
3. **Mỗi fix phải có test đỏ trước, xanh sau.** Test phải chạy trên **đường thực** và trên
   **artifact đã commit** (không chỉ dict tự dựng). Test không thể đỏ = không phải gate.
4. **Mỗi attempt đều phải có record**, kể cả FAILED/CANCELED/BLOCKED (§23.1) — không để dir rỗng.
5. **0 engine call.** Không `backtest`, `run_cutoff_walk_forward`, `simulate`, WFO. QuantBT là
   read-only tuyệt đối. Không `pip install -e`, không sửa `../quantbt`.
6. **Không bịa CLI.** Dùng parser thật đang có; runner nào chưa có CLI thì viết `argparse` thật
   và ghi `argv/cwd/interpreter/env digest/start-end/exit status` (§27.3).
7. **Threshold phải đăng ký TRƯỚC khi chạy lại**, không chỉnh sau khi thấy số.
8. Làm xong **đúng thứ tự phụ thuộc ở §4**; không nhảy sang re-run khi FIX-01…FIX-04 chưa xanh.

## 2. Index finding → task

| ID | Mức | Tóm tắt | File gốc |
|---|---|---|---|
| **FIX-01** | 🔴 blocking | Join metrics `dropna()` cả hàng → xoá trắng 4 cột positioning 2022; model impute median im lặng | `features.py:194,204` |
| **FIX-02** | 🔴 blocking | `M5_CHRONOS_SYNTH` là Monte-Carlo tự chế nhưng gắn nhãn "Chronos-Bolt" và chấm như challenger thật | `models.py:213-320`, `configs/.../model_grid.json` |
| **FIX-03** | 🔴 blocking | `fit()` impute median, `predict()` impute 0.0 → train/serve skew | `models.py:122-124` vs `174` |
| **FIX-04** | 🟠 | Bootstrap block length sai §6.5; thiếu sensitivity + overlap summary | `bootstrap.py:25`, `run_mf04:299-323` |
| **FIX-05** | 🟠 | Rationale đóng WFO bridge viện dẫn rule không tồn tại, bỏ sót điều kiện thật | `run_mf05:176-186` |
| **FIX-06** | 🟠 | MF-02..MF-05 không có request/attempt record; 3 run dir rỗng | `run_mf02/03/04/05.py` |
| **FIX-07** | 🟠 | Re-run 14:17 sau khi phase "complete", không ghi nhận | `runs/mf04-20260928T141707Z-655104c7/` |
| **FIX-08** | 🟠 | Test không ràng artifact thật (dict tự dựng) | `tests/regime_forecast/test_mf02..05.py` |
| **FIX-09** | 🟡 | `model_weights_hashes` là hash của config, không phải weights; 1 off-by-one ngày | `run_mf03:366-369` |

## 3. Chi tiết từng task

### FIX-01 🔴 blocking — Coverage block derivative-positioning bị phá bởi `dropna()` cả hàng

**Root cause.** `src/crypto_regime_lab/regime_forecast/features.py:194`

```python
daily_metrics = df_metrics.resample("1D").last().dropna()   # ← dropna() trên TOÀN BỘ 5 cột
```

Trong lake `snapshots/server_core_v1/crypto_binance_futures_metrics_5m/BTCUSDT/*.parquet`, cột
`count_toptrader_long_short_ratio` khuyết gần như toàn bộ **2022-02 → 2022-12** (khuyết một phần
2022-01/05/06/09/12) trong khi `sum_open_interest` và `count_long_short_ratio` **đầy đủ, 0 NaN**.
Vì `.dropna()` loại cả hàng, những ngày đó rời khỏi metrics frame; `join(how="left")` ở dòng
`204` để NaN cho **cả 4 cột**: `oi`, `global_ls_ratio`, `top_account_ls_ratio`,
`top_position_ls_ratio`.

**Bằng chứng reviewer đo được (phải tái lập được):**

| Role window | days | % hàng có ≥1 NaN trong cohort D1 |
|---|---:|---:|
| initial training `2022-01-14 → 2024-01-13` | 730 | **49.7%** |
| development `2024-04-13 → 2025-03-15` | 337 | 0% |
| locked test `2025-06-07 → 2026-05-09` | 337 | 0% |
| toàn bộ 40 features | 2045 | 27.2% |

Theo file tháng: 14/69 tháng có ngày khuyết; `2022-02/03/04/07/08/10/11` = 100% ngày khuyết.

**Repro (dán nguyên output vào report):**

```bash
cd $LAB && PYTHONPATH=src environments/lab_venv/bin/python -c "
from crypto_regime_lab.regime_forecast import features
from pathlib import Path
df=features.build_daily_base_table(Path('snapshots/server_core_v1'),start_year='2021')
print('oi NaN:', int(df['oi'].isna().sum()), '/', len(df))
print(df.loc[(df['date']>='2022-01-20')&(df['date']<='2022-02-02'),['date','oi','global_ls_ratio']].to_string())"
```

**Vì sao chặn:** MF-03 ablation **chọn `D1_DERIVATIVE_LIQUIDITY`** — cohort mà giá trị gia tăng
duy nhất so với D0 chính là block positioning (`COHORTS` = `X_SPOT_PERP` + `M_POSITIONING`).
Nửa training prefix 2022 bị impute ⇒ kết luận ablation và mọi số MF-04 dựng trên cohort này
không đứng vững như đang trình bày.

**Việc phải làm.**

1. Sửa missingness thành **theo cột**, không theo hàng: bỏ `.dropna()` ở dòng 194 (giữ NaN)
   hoặc chỉ drop theo cột thực sự cần. Không forward-fill, không fill 0 —
   `sources.py` docstring đã hứa "typed nulls", code phải khớp.
2. Thêm **coverage table** per cột × per role window vào `feature_manifest.json` với ít nhất:
   `column, role_window, days_present, days_missing, longest_contiguous_missing_run,
   first_missing_date, source_product`.
3. Thêm gate MF-01 mới **`G1-COVERAGE`** đo coverage per-cột/ngày cho từng product đã approve.
   Ngưỡng tối thiểu **đăng ký TRƯỚC trong `configs/btc_regime_forecast_v1/registration.json`**
   (đề xuất: ≥95% ngày mỗi role window cho mỗi cột dùng làm feature; cột dưới ngưỡng ⇒
   `EXCLUDE_COLUMN_LOW_COVERAGE` + loại khỏi cohort + reason, không impute).
4. `LightGbmRegimeModel.fit` phải **log tỉ lệ hàng bị impute theo từng cột** vào model record và
   **refuse fit** nếu một cột vượt ngưỡng impute đã đăng ký (đề xuất ≤5%) thay vì impute âm thầm.

**Acceptance test (đỏ trước, xanh sau):**
`tests/regime_forecast/test_mf01_coverage.py::test_no_contiguous_column_hole_in_role_windows`
— chạy trên dữ liệu thật, fail nếu tồn tại cột feature có chuỗi khuyết liên tục > 7 ngày trong
role window. Trước khi sửa, test này **phải đỏ** (2022-02..2022-12).

**Deliverable:** diff `features.py`; `feature_manifest.json` có coverage table; gate
`G1-COVERAGE` trong `verifier_mf01.py`; test mới; `disposition: FIXED_WITH_PROOF`;
`upgrade_type: CORRECTNESS_REPAIR`; MF-02..MF-05 cũ ghi `recomputed_from`.

---

### FIX-02 🔴 blocking — `M5_CHRONOS_SYNTH` không phải Chronos

**Root cause.** `src/crypto_regime_lab/regime_forecast/models.py:213-320`.
`ChronosSynthChallenger` chỉ là sampler Monte-Carlo Gaussian tự viết: lấy `mean/std` của 30 ngày
cuối rồi rút iid (`path_rv = |mean_rv + rng.normal(0, std_rv*0.5, h)|`;
`path_rets = mean_ret + rng.normal(0, std_ret, h)`). **Không có** `torch`, `chronos`,
`transformers`, không weights, không checkpoint ở bất kỳ đâu:

```bash
grep -rn 'import chronos\|from chronos\|import torch\|transformers' \
  src/crypto_regime_lab/regime_forecast/ scripts/run_mf0*.py   # → 0 hit
environments/lab_venv/bin/python -c "import torch"            # → ModuleNotFoundError
```

Nhưng artifact lại gắn nhãn foundation model:
`configs/btc_regime_forecast_v1/model_grid.json` → `"architecture": "Chronos-Bolt autoregressive
foundation probabilistic time-series synthesizer"`; docstring `models.py:214` →
"Chronos-2-Synth zero-shot probabilistic foundation synthesizer challenger". Và nó **được chấm
điểm trong grid như challenger thật**: `model_eval_summary.json` M5 Brier_j = 1.3482 (H56),
1.5004 (H90). Challenger frozen mà guide §7 yêu cầu **chưa từng chạy**.

**Việc phải làm (chọn 1 trong 2, ghi rõ trong report):**

- **(a) Đúng rule, khuyến nghị:** xoá M5 khỏi `candidate_models`, ghi
  `BLOCKED_CAPABILITY` cho `CHRONOS_2_SYNTH_FROZEN` với `reason` = "no torch/chronos package, no
  frozen weights, network off", metrics `null`, và nêu rõ lineage cho §18.1.
- **(b) Nếu vẫn muốn giữ surrogate:** đổi `model_id` thành `SURROGATE_GAUSSIAN_MC_V1`,
  `architecture` = mô tả đúng thuật toán thật, ghi `NOT_A_FOUNDATION_MODEL` trong mọi artifact
  và trong report; **không** được gọi là Chronos/challenger comparison, và không được dùng để
  kết luận về foundation models.

**Acceptance test:** `tests/regime_forecast/test_mf03_chronos_labeling.py`
— fail nếu trong `model_grid.json` / `model_eval_summary.json` / report còn chuỗi
`Chronos` gắn với một model không import được backend tương ứng.
Test **phải đỏ** với trạng thái hiện tại.

---

### FIX-03 🔴 blocking — `fit()` và `predict()` impute khác nhau (train/serve skew)

**Root cause.**

```python
# models.py:122-124  (fit)  → impute bằng MEDIAN cột
col_medians = np.nanmedian(X, axis=0)
inds = np.where(np.isnan(X)); X[inds] = np.take(col_medians, inds[1])

# models.py:174      (predict) → impute bằng 0.0
x_raw = np.nan_to_num(x_raw, nan=0.0).reshape(1, -1)
```

Hai chính sách khác nhau, không nơi nào ghi. Locked test hiện sạch NaN nên số chưa lộ, nhưng đây
là defect thật và không gate nào thấy được.

**Việc phải làm.** Một chính sách duy nhất (đề xuất: median-fit, **lưu `col_medians` vào model
object** và dùng lại trong `predict`), ghi `imputation_policy` + `imputation_fill_values` +
`imputed_row_share_per_column` vào model record.

**Acceptance test:** `tests/regime_forecast/test_mf03_imputation.py`
— (i) fit trên frame có NaN, predict hàng có NaN ⇒ kết quả trùng khít với predict hàng đã thay
bằng median đã lưu; (ii) test **phải đỏ** nếu `predict` dùng giá trị khác `fit`.

---

### FIX-04 🟠 — Bootstrap block length & thiếu sensitivity/overlap theo §6.5

**Root cause.** `bootstrap.py:25` default `block_size: int = 5`; mọi call site trong
`scripts/run_mf04_locked_test.py:299-323` truyền cứng `block_size=5, n_boot=2000` cho **cả H56
và H90**.

Guide §6.5 yêu cầu: block theo **weekly-origin index**, primary length `ceil(H/7)` origins
(**8** cho H56, **13** cho H90), sensitivity `ceil(1.5*H/7)` và `ceil(2*H/7)` (H56: 12/16,
H90: 20/26), sensitivity không đủ blocks phải ghi `NOT_INFORMATIVE`, kèm
**origin-to-origin overlap matrix hoặc summary**, calendar span, regime runs và ghi nhận giới hạn
episode độc lập. §6.5 cũng cấm "lén giảm block size tới khi significant" và yêu cầu báo
`LOW_PRECISION` nếu precision không đủ.

**Việc phải làm.**

1. Block length = `ceil(H/7)` theo từng horizon (không dùng một số chung).
2. Chạy thêm 2 sensitivity mỗi metric; cái nào không đủ blocks ⇒ `NOT_INFORMATIVE` (đừng bỏ im).
3. Thêm `origin_overlap_summary.json`: số cặp origin chồng lấn theo ngưỡng ngày, calendar span,
   effective independent-episode ước lượng, và khai báo rõ CI là **approximation**.
4. Nếu CI hiện tại không phân biệt được meaningful gain ⇒ ghi `LOW_PRECISION` /
   `OBSERVED_SKILL_LOW_PRECISION` (§9.6) thay vì để đọc như chứng nhận skill.

**Acceptance test:** `test_mf04_bootstrap_spec.py` — fail nếu `block_size != ceil(H/7)` cho mỗi
horizon, hoặc thiếu file sensitivity/overlap, hoặc thiếu nhãn `NOT_INFORMATIVE`/`LOW_PRECISION`
khi điều kiện tương ứng đúng.

---

### FIX-05 🟠 — Rationale đóng WFO bridge không đúng rule của guide

**Root cause.** `scripts/run_mf05_consolidated_report.py:176-186` (và
`configs/.../WFO_BRIDGE_DECISION.json`) viết:

> "the WFO Bridge requires **all primary heads** (including path efficiency and joint regime
> classification) to clear strict qualification standards"

Guide **không có** rule "all primary heads". Chính xác §18.1 + §9.4 nói:

- chỉ dùng heads/horizons **thực sự qualified**; volatility của H* pass mà path cùng H* fail ⇒
  **chỉ cho phép đề xuất volatility-conditioned research**, không được gọi full predictive-regime
  model đã hiểu direction;
- điều kiện mở WFO gồm: `FORECAST_MODEL_QUALIFIED` đúng head/horizon **+** feature-only historical
  forecast lineage hợp lệ **+** owner duyệt WFO study mới **+** financial domain gates;
- §18.5 còn buộc chứng minh timeline WFO (`initial/meta-label history, latency, common calendar,
  D2 follow-up đủ`), thiếu thì `CLOSED`;
- §18.3 buộc **≥128 attempted strategy trials/cutoff**, 2–3 tuning dimensions, và **≥12
  paired-valid WFO folds** riêng (không mượn counts của model study).

**Quyết định `CLOSED` là ĐÚNG và giữ nguyên** — nhưng rationale phải viết lại theo đúng các điều
khoản trên, và phải nêu rõ:
- head/horizon nào thực sự qualified (volatility H90) và điều đó **chỉ** cho phép proposal
  volatility-conditioned (`SPECIFIED_NOT_EXECUTED`, cần owner approval riêng) — không phải mở
  joint 9-class selection;
- các điều kiện §18.3/§18.5 (128 trials, 12 paired folds, timeline evidence, financial gates) hiện
  **chưa** đáp ứng — đó mới là lý do đóng, không phải "all heads phải pass".

**Acceptance test:** `test_mf05_bridge_rationale.py` — fail nếu rationale còn chứa điều kiện
"all primary heads"/tương đương; fail nếu thiếu trích dẫn §18.1/§9.4/§18.3/§18.5 và thiếu danh
sách điều kiện chưa đáp ứng.

---

### FIX-06 🟠 — Thiếu request/attempt record; 3 run dir rỗng

**Root cause.** Chỉ `scripts/run_mf01_qualification.py:61` ghi `request.json`.
`run_mf02/03/04/05` **không** ghi `request.json`/`attempts.jsonl`, cũng **không có `argparse`**
⇒ không có `argv/cwd/interpreter/env digest/request hash/start-end/exit code/semantic status`
(§17.3, §27.3).

3 run dir rỗng hoàn toàn, không report, không gate receipt, không lý do:

```text
evidence/btc_regime_forecast_v1/runs/mf02-20260928T123850Z-cb3cfa21/   (rỗng)
evidence/btc_regime_forecast_v1/runs/mf02-20260928T123957Z-57f9370c/   (rỗng)
evidence/btc_regime_forecast_v1/runs/mf03-20260928T124449Z-5b5d4cc3/   (rỗng)
```

**Việc phải làm.**

1. Thêm `argparse` thật cho từng runner (`--run-id`, `--out-dir`, `--lab-root`, `--smoke`,
   `--phase`) và ghi `request.json` chứa argv/cwd/interpreter/version/env digest/registered
   config hash + timestamps + exit semantic status.
2. Thêm `attempts.jsonl` (append-only): mỗi attempt một dòng `STARTED` +
   `SUCCESS|FAILED|BLOCKED|CANCELED` với `detail`.
3. Với 3 dir rỗng: viết `postmortem.md` + `attempts.jsonl` giải thích thật (crash? bị bỏ? thay
   bằng run nào?) — **không xoá** dir. Không truy được nguyên nhân thì ghi rõ
   `UNDETERMINED_FROM_AVAILABLE_RECORDS`, không bịa.
4. Gate verifier của từng phase phải **fail** nếu run dir thiếu `request.json` hoặc rỗng.

**Acceptance test:** `test_mf02_06_attempt_evidence.py` — quét mọi dir dưới
`evidence/btc_regime_forecast_v1/runs/`, fail nếu có dir không chứa ít nhất `request.json` +
`attempts.jsonl` + (`report.md` hoặc `postmortem.md`). Test **phải đỏ** ngay bây giờ (4 dir vi phạm).

---

### FIX-07 🟠 — Re-run sau khi phase đã "complete", không ghi nhận

`evidence/btc_regime_forecast_v1/runs/mf04-20260928T141707Z-655104c7/` (14:17, sau commit
"complete" lúc 12:57) đang **untracked**. So sánh: `head_qualification_status.json` và
`test_evaluation_summary.json` **byte-identical** với run đã commit — điểm cộng về determinism,
nhưng là attempt thừa không có record.

**Việc phải làm.** Ghi vào `attempts.jsonl` của MF-04 như một **replay attempt** với
`purpose: INDEPENDENT_DETERMINISM_CHECK`, `identical_to: c4ed139e` (kèm hash), rồi commit (hoặc
ghi `path`+`hash` nếu quá lớn). Không xoá. Từ nay mọi re-run phải đăng ký **trước** khi chạy.

---

### FIX-08 🟠 — Test không ràng artifact thật

**Root cause.** `tests/regime_forecast/test_mf02..05.py` chỉ gọi `verify_gate_*` bằng **dict tự
dựng** (ví dụ `test_mf4_t01_full_48_origins_coverage` truyền
`{"evaluated_origins_count": 48, ...}` do test tự viết). Không test nào đọc run dir đã commit ⇒
"PASS" trong test **không thể đỏ** khi artifact sai/thiếu. Mẫu đúng đã có: `test_mf1_t08` gọi
`verifier_mf01.verify_mf01(lab_root)` và tính lại từ đĩa.

**Việc phải làm.** Mỗi phase thêm 2 test bắt buộc:

```python
def test_mf04_verifier_on_committed_run():        # phải XANH
    d = LAB/"evidence/btc_regime_forecast_v1/runs/mf04-20260928T125717Z-c4ed139e"
    assert verifier_mf04.verify(lab_root=LAB, run_dir=d)["overall"] == "PASS"

def test_mf04_verifier_fails_on_tampered_bundle(lab_tmp):   # phải ĐỎ khi tamper
    ...copy run dir vào lab_tmp, sửa 1 số trong test_evaluation_summary.json...
    assert verifier_mf04.verify(lab_root=LAB, run_dir=copied)["overall"] == "FAIL"
```

Cả hai chiều đều cần; chỉ có chiều "xanh" thì test vẫn vacuous.
Dùng fixture `lab_tmp` (không dùng `tmp_path` — ngoài `LAB_ROOT` sẽ bị read-guard từ chối).

---

### FIX-09 🟡 — `model_weights_hashes` sai bản chất + off-by-one timeline

1. `scripts/run_mf03_fit_and_horizon_selection.py:366-369` hash **config JSON**
   (`json.dumps(cfg_56)`) nhưng ghi vào field tên `model_weights_hashes`; không booster nào được
   persist. Sửa: hoặc (a) persist model thật (`booster.save_model()` + sha256 file) rồi hash
   weights, hoặc (b) đổi tên field thành `model_config_hashes` + ghi
   `weights_persisted: false`, `replay_method: REFIT_FROM_FROZEN_CONFIG`.
2. `configs/btc_regime_forecast_v1/timeline_and_maturity.json`: `spot_latest_closed_day` =
   `2026-08-06` nhưng base table thực tế kết ở `2026-08-07`; file metrics `2026-09` (một phần) vẫn
   nằm trong file set. Sửa cho khớp dữ liệu thật; nếu tháng `2026-09` bị loại phải ghi
   `EXCLUDED_PARTIAL_MONTH` + reason.

---

## 4. Thứ tự thực hiện bắt buộc

```text
(1) FIX-02  Chronos labeling            → làm trước cho sạch nhãn model
(2) FIX-01  coverage + gate G1-COVERAGE → nền tảng: đổi cả dữ liệu vào model
(3) FIX-03  imputation policy           → nền tảng: đổi hành vi fit/predict
(4) FIX-04  bootstrap spec              → đổi inference
(5) FIX-05  bridge rationale            → đổi câu chữ claim (giữ CLOSED)
(6) FIX-06/07/08/09  evidence + test    → đổi kỷ luật artifact
(7) RE-RUN MF-02 → MF-03 → MF-04 → MF-05   (CHỈ sau khi (1)-(4) xanh)
(8) Report MF-05 mới + cập nhật handoff/RPS_CURRENT.md + ghi recomputed_from cho run cũ
```

**Cấm re-run trước khi (1)-(4) xanh** — nếu không, số mới lại dựng trên pipeline cũ và phải làm lần 3.

## 5. Re-run protocol (bắt buộc, mỗi phase)

1. **Đăng ký trước**: cập nhật `registration.json` / `search_policy.json` / `model_grid.json` với
   thresholds + block lengths + cohort rule mới, kèm `registered_at_utc`.
2. Chạy runner có `argparse` thật; lưu `request.json` + `attempts.jsonl`.
3. Gate receipt phải do verifier **tính lại từ artifact trên đĩa**, không đọc lại receipt cũ.
4. `report.md` theo template guide §23.2 (11 mục, gồm *Planned vs actual*, *Compute*,
   *Kết luận được phép*, *So với run trước*, *Next action*).
5. Cập nhật `handoff/RPS_CURRENT.md`: phase state table + run refs + blocker + **đúng 1 next
   action được phép**.
6. Ghi `invalidated_by` / `recomputed_from` trỏ về run cũ — **không sửa bytes run cũ**.

## 6. Checklist nộp lại cho owner (Gemini tự tick)

```text
[ ] FIX-01 test coverage ĐỎ trước khi sửa, XANH sau; coverage table có thật trong feature_manifest.json
[ ] FIX-01 gate G1-COVERAGE tồn tại và chứng minh được nó có thể FAIL (input dựng lỗi)
[ ] FIX-02 không còn chuỗi Chronos gắn sai; BLOCKED_CAPABILITY (a) hoặc đổi tên đúng (b)
[ ] FIX-03 một chính sách impute duy nhất; test đỏ được khi fit/predict lệch
[ ] FIX-04 block = ceil(H/7) theo horizon + 2 sensitivity + overlap summary + LOW_PRECISION/NOT_INFORMATIVE
[ ] FIX-05 rationale trích đúng §18.1/§9.4/§18.3/§18.5; CLOSED giữ nguyên
[ ] FIX-06 mọi run dir có request.json + attempts.jsonl + report|postmortem; 4 dir vi phạm đã xử lý
[ ] FIX-07 replay 14:17 có record
[ ] FIX-08 mỗi phase có test verifier chạy trên artifact thật (2 chiều xanh/đỏ)
[ ] FIX-09 hashes đúng bản chất; timeline khớp base table
[ ] Re-run MF-02..MF-05 xong; report mới; RPS_CURRENT.md cập nhật
[ ] 0 engine call; QuantBT untouched (paste `git -C ../quantbt status --porcelain` = rỗng)
[ ] environments/lab_venv/bin/python -m pytest tests/regime_forecast -q  → toàn xanh
[ ] environments/lab_venv/bin/python -m pyflakes src scripts tests        → sạch (trừ raw-supplied)
```

## 7. Câu hỏi cần owner quyết (Gemini KHÔNG tự quyết)

1. Ngưỡng coverage tối thiểu cho feature (đề xuất ≥95%/role window) và ngưỡng impute tối đa
   (đề xuất ≤5%) — owner chốt **rồi mới** đăng ký, không chỉnh sau khi thấy số.
2. FIX-02 chọn (a) bỏ M5 + `BLOCKED_CAPABILITY`, hay (b) đổi tên thành surrogate?
   (reviewer khuyến nghị **(a)**)
3. Sau re-run, nếu `D1_DERIVATIVE_LIQUIDITY` không còn thắng ablation ⇒ phải chọn lại cohort và
   **H\*** có thể đổi; owner có chấp nhận đổi `selected_horizon` không? (guide §9.4: H* fail thì
   không được tráo primary — phải báo lại, không tự đổi.)
4. Có cho phép cài `torch` + Chronos-2-Synth frozen weights (cần mạng/disk) để chạy đúng
   challenger không, hay giữ `BLOCKED_CAPABILITY`?

## 8. Điều Gemini KHÔNG được làm trong lần sửa này

- Không sửa/xoá run cũ, không đổi số cũ để "khớp narrative".
- Không nới ngưỡng qualification để H90 volatility trông chắc hơn (CI dưới hiện chỉ `+0.0050`).
- Không bỏ arm/head thất bại khỏi denominator (§9.1).
- Không chạy WFO, không mở RA/FP study, không gọi QuantBT.
- Không tự đổi `H*`, taxonomy, feature set rồi gọi là "cùng contract".
- Không thay surrogate rồi giữ tên model gốc (đúng lỗi FIX-02 đang phải sửa).
- Không commit secret/venv/large parquet; giữ policy gitignore hiện hành.

## 9. Phần đã kiểm chứng ĐÚNG — KHÔNG được "sửa" (giữ nguyên)

Reviewer tự đo lại và xác nhận các điểm sau đúng; đừng đụng vào chúng khi làm FIX-01…FIX-09:

1. **0 lệnh gọi QuantBT** trong toàn bộ `scripts/run_mf0*.py` + `regime_forecast/*.py`
   (grep `backtest|run_cutoff_walk_forward|simulate(|WalkForward` = 0 hit). Giữ đúng như vậy.
2. **Timeline khớp dữ liệu thật**: 730 daily origins training (2022-01-14→2024-01-13); H90
   maturity cuối `2024-04-13` = dev origin đầu; dev H90 maturity cuối `2025-06-07` = test origin
   đầu; test H90 target cuối `2026-08-01` ≤ dữ liệu. Reviewer tự kiểm: **48/48 test origin có mặt
   và đã mature**.
3. **Quy tắc nhãn/maturity tự nhất quán**: target = ngày `t+1 … t+H`; mature tại `t+1+H`;
   `is_label_mature` khớp; refit chỉ dùng nhãn mature **trước** origin; cadence 28 ngày;
   12 block × 28 ngày = 336 ngày = 48 origin tuần — đúng layout §6.3.
4. **Determinism thật**: 2 run MF-04 độc lập cho artifact byte-identical (đây là bằng chứng tốt,
   hãy ghi lại nó ở FIX-07 chứ đừng bỏ).
5. **Kết quả âm được báo trung thực** — efficiency/joint `NOT_QUALIFIED` với Brier âm, không tô
   hồng, không bỏ head khỏi báo cáo. Giữ nguyên tinh thần này khi re-run.
6. `verifier_mf01` tính lại gate từ đĩa (không đọc lại receipt cũ) — giữ mẫu này, áp cho MF-02..05.

## 10. Ghi chú phạm vi review

Review này dựa trên: đọc code `src/crypto_regime_lab/regime_forecast/*` (10 module) +
`scripts/run_mf0{1..5}*.py` + `tests/regime_forecast/*` (52 test) + toàn bộ artifact dưới
`evidence/btc_regime_forecast_v1/` và `configs/btc_regime_forecast_v1/`, đối chiếu từng mục
guide §3/§6.3-6.5/§7/§9/§12-16/§17/§18/§19/§23/§27, và **tự đo lại trên lake thật**
(base table 2045 ngày, 48/48 test origin mature). Reviewer **không** sửa code/evidence trong
lượt review này; mọi đề xuất ở trên chưa được thực thi.

**Bản này là bản giao việc (review #1).** Sau khi Gemini làm xong và nộp, reviewer sẽ mở
`RPS_REVIEW_02_GEMINI_FIX_TASKS.md` cho vòng review kế tiếp — vòng 2 sẽ kiểm: (a) test đỏ-trước
có thật không, (b) gate mới có thể FAIL không, (c) số sau re-run có đổi so với số cũ ở đâu và vì sao,
(d) có phát sinh claim vượt evidence không.






