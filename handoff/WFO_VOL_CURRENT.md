# WFO_VOL_CURRENT — BTC Volatility-Conditioned WFO Study

Current Status for `btc_volatility_conditioned_wfo_v1`:

| Phase | Technical Gate | Research / Model Scope | Latest Valid Evidence Run | Next Action |
|---|---|---|---|---|
| **VWFO-01** | **PASS** (5/5 technical gates) | **MODEL_HANDOFF_ACCEPTED_H14** | `vwfo01-20260928T222146Z-e7c663cf` | `APPROVED` |
| **VWFO-02** | **PASS** (6/6 technical gates) | **CANDIDATE_ARCHIVE_INIT** | `vwfo02-20260929T001715Z-4225c492` | `APPROVED` |
| **VWFO-03** | **PASS** (5/5 technical gates) | **SELECTION_DEV_AND_SAMPLER_FREEZE** | `vwfo03-20260929T015627Z-436e7838` | `APPROVED` |
| **VWFO-04** | **PASS** (5/5 technical gates) | **OPERATIONAL_BOUNDARIES_QUALIFIED** | `vwfo04-20260929T071942Z-6c3665c5` | `WAITING_OWNER_REVIEW` |
| **VWFO-05** | NOT_STARTED | FINAL_WFO_AND_VERDICT | - | Awaiting Phase 4 Approval |


---

## Tóm tắt Phase VWFO-04 (Hoàn thành)
- **Run ID**: `vwfo04-20260929T071942Z-6c3665c5`
- **Mục tiêu**: Chứng minh policy đã freeze chạy được tuần tự với legal information, không một bản backtest được đơn giản hóa khác live.
- **Timing Contract & Clocks**:
  - Khóa chặt chu kỳ 14 ngày (`update_cadence_days = 14`), độ trễ sẵn sàng danh định 1 ngày (`common_ready_lag_days = 1`, quy tắc `WAIT_FLAT_PREFIX_WITHIN_H14`), thời hạn hiệu lực đề xuất 2 ngày (`proposal_ttl_days = 2`), và giới hạn tối đa không tái kiểm chuẩn 28 ngày (`max_revalidation_age_days = 28`).
  - Áp dụng hoàn toàn đối xứng và đồng bộ trên toàn bộ 8 arms (`A_M4`, `B0_GLOBAL`, `B_CAP`, `O_PERSIST`, `C_H14`, `P_NI_01`, `P_NI_02`, `P_NI_03`).
  - Chặn đứng 100% mọi hành vi rò rỉ hoặc backdate (`not_before < cutoff` bị REJECT, `target_window_start >= target_window_end` bị REJECT).
- **Vòng đời & Tính lũy đẳng (Idempotency)**:
  - Đề xuất trùng lặp được lọc sạch tự động (`IDEMPOTENT_IGNORED_ALREADY_PROCESSED`), tuyệt đối không kích hoạt 2 lần hoặc nhân đôi lệnh giao dịch.
  - Sai lệch phiên bản đương nhiệm (`expected_incumbent_version != active_version`) bị từ chối dứt khoát (`INCUMBENT_VERSION_MISMATCH`).
  - Đề xuất hết hạn (`current_time > expires_at`) bị từ chối (`PROPOSAL_EXPIRED`).
  - Tái thẩm định cùng tham số (`same_params`): chỉ cập nhật mốc thời gian `last_revalidation` (watermark refresh), giữ nguyên vẹn vị thế, lịch sử lệnh, chỉ báo kỹ thuật, và đường vốn equity (tách bạch rõ ràng `age_since_param_change` và `age_since_revalidation`).
- **Khôi phục trạng thái khi khởi động lạnh (Cold Recovery)**:
  - Khôi phục trọn vẹn Model Bundle (weights booster, imputer column medians, temperature scaling $T_V = 3.946$, taxonomy tertiles $q_{33.3} = -0.8872, q_{66.7} = -0.5142$, và schema 38 features). Các gói bundle thiếu siêu dữ liệu ("weights-only shortcuts") đều bị chặn.
  - Lưu trữ và phục hồi nguyên vẹn AccountState, danh sách proposal IDs đã xử lý, số lần revalidation mà không bị lỗi dữ liệu (`state_corruption_detected = False`).
- **Bộ kiểm thử tiêm lỗi (Fault Injection Suite - 8/8 Passed)**:
  1. `FAULT-01` (Late arrival): REJECTED (`PROPOSAL_EXPIRED`).
  2. `FAULT-02` (Duplicate proposal retry): IGNORED (`IDEMPOTENT_IGNORED`).
  3. `FAULT-03` (Missing column medians): REJECTED (`MISSING_IMPUTER_MEDIANS`).
  4. `FAULT-04` (Missing temperature scaling): REJECTED (`MISSING_OR_INVALID_TEMPERATURE_SCALING`).
  5. `FAULT-05` (Missing taxonomy quantiles): REJECTED (`MISSING_TAXONOMY_QUANTILES`).
  6. `FAULT-06` (Unknown/Mismatched arm ID): REJECTED (`ARM_MISMATCH`).
  7. `FAULT-07` (Engine order rejection feedback): Tiền mặt và vị thế giữ nguyên trạng, không cập nhật theo "expected fill".
  8. `FAULT-08` (`SAFE_ENTRY_PAUSE`): Khi vượt quá 28 ngày không tái thẩm định, hệ thống tạm dừng mở vị thế mới nhưng tiếp tục duy trì 100% các lệnh thoát bảo vệ (protective exits / SL / TP), tuyệt đối không cưỡng bức thanh lý tài khoản.
- **Kiểm chứng tương đương tài chính Streaming Replay vs. Batch Backtest (Parity)**:
  - Thực hiện trên 2,304 thanh nến 15 phút thực tế của BTCUSDT (từ `2025-06-01` đến `2025-06-25`).
  - Khớp lệnh next-open contract với phí $0.0004$ và trượt giá $0.0001$.
  - Chênh lệch đường vốn tối đa: $\Delta E_{\max} = 0.00 \times 10^{-6}$ (đạt dung sai $\le 10^{-6}$).
  - Tổng số lệnh phát ra (50) và số lượng fills (50) khớp 100% giữa streaming từng nến và batch backtest.
- **Ranh giới vận hành (Operational Boundaries)**:
  - `production_orders_authorized`: `False` (chế độ lab streaming shadow, không gửi lệnh thật ra sàn).
  - Cây mã nguồn QuantBT engine (`/root/bobby/pool_alpha/quantbt`) được bảo toàn 100% nguyên vẹn, không có bất kỳ thay đổi nào.
- **Exit Gates**: **5/5 Technical Gates PASS** (`G4-CLOCKS`, `G4-LIFECYCLE`, `G4-PARITY`, `G4-RECOVERY`, `G4-NO_PRODUCTION_WRITES`), `G4-OWNER: PENDING`.
- **Trạng thái**: `WAITING_OWNER_REVIEW` sẵn sàng để Owner phê duyệt mở tiếp Phase VWFO-05 (Locked Final WFO, D1/D2 & Conclusion).

---

## Tóm tắt Phase VWFO-03 (Hoàn thành)
- **Run ID**: `vwfo03-20260929T015627Z-436e7838`
- **Execution Scale**: Hoàn thành toàn bộ 12 DEV origins (`2024-10-12` đến `2025-03-15`) cho cả 2 samplers `S_TPE` và `S_SOBOL` ($2 \times 12 \times 128 = 3,072$ trials tìm kiếm IS180 và đánh giá FWD14 event-account native trên QuantBT).
- **Candidate Descriptors & Anchor Contrast**: Trích xuất vector đặc trưng $\phi(z)$ (5 features: `coeff_norm`, `ap_norm`, `threshold_norm`, `raw_is_sharpe`, `log_fills_count`) chuẩn hóa nghiêm ngặt trên archive đã trưởng thành (past-only). Đồng nhất thức contrast $v_{a} \equiv \mathbf{0} \implies \hat Y(a) \equiv 0.000$ được bảo toàn trên 100% folds.
- **Model Solvers & 8 Arms**: Giải chính xác hồi quy Ridge có trọng số bình quân theo origin ($\lambda = 10.0$) cho $B0\_GLOBAL, B\_CAP, O\_PERSIST, C\_H14, P\_NI\_01..03$. Khi context zero hoặc biến thiên thấp ($s_{train} < 0.05$), $C\_H14$ suy biến chính xác về $B\_CAP$.
- **Quy tắc chọn Candidate**: Bộ chọn áp dụng chuẩn xác $\min \hat Y$ (không dùng argmax return hay Sharpe), bộ lọc $\hat Q \ge -0.10$, và tie-breaking bằng khoảng cách tham số Euclidean tới anchor.
- **Hiệu quả thực nghiệm trên DEV (Sampler `S_TPE`)**:
  - `A_M4` (Stock Mode 4 Anchor): Mean IS Sharpe $2.1104$, Mean FWD Sharpe $+0.0628$, Mean Decay $D = +2.0477$.
  - `B0_GLOBAL` (Learned Global Decay): Mean IS Sharpe $1.7728$, Mean FWD Sharpe $+0.7851$, Mean Decay $D = +0.9878$ (giảm hơn một nửa độ suy giảm Sharpe, tạo thặng dư $+0.7223$ điểm Sharpe so với Anchor).
  - `B_CAP`, `O_PERSIST`, `C_H14`, `P_NI`: Mean IS Sharpe $1.2759$, Mean FWD Sharpe $+0.9266$, Mean Decay $D = +0.3492$ (giảm độ suy giảm về gần 0, tạo thặng dư $+0.8638$ điểm Sharpe so với Anchor).
  - Đáng chú ý tại Fold 08 (`2025-01-18`), Stock Anchor bị sụp đổ nặng ($D = +11.085$, FWD Sharpe $-8.415$), các mô hình learned decay đã dự báo decay âm chính xác ($Yhat = -3.480$) và chọn candidate đứng ngoài flat ($D = +1.927$, FWD Sharpe $+0.000$), bảo vệ thành công $+8.415$ điểm Sharpe.
- **Sampler Choice (§8.7) & Final Freeze**:
  - Cả hai sampler đều đạt điều kiện tiên quyết (margin $\ge -0.10$).
  - Theo luật ưu tiên thứ tự định danh (`S_TPE` first), `S_TPE` được chọn và đóng băng chính thức làm Confirmatory Sampler trong `configs/btc_volatility_conditioned_wfo_v1/final_freeze.json`.
- **Exit Gates**: **5/5 Technical Gates PASS** (`G3-SELECTOR`, `G3-CONTROLS`, `G3-DEV12`, `G3-CHOICE`, `G3-FREEZE`), `G3-OWNER: PENDING`.
- **Trạng thái**: `WAITING_OWNER_REVIEW` sẵn sàng để Owner phê duyệt mở tiếp Phase VWFO-04.

---

## Tóm tắt Phase VWFO-02 (Hoàn thành)
- **Run ID**: `vwfo02-20260929T001715Z-4225c492`
- **Execution Scale**: Hoàn thành toàn bộ 24 searches (12 INIT origins $\times$ 2 samplers `S_TPE` và `S_SOBOL`), đạt $3,072$ trials tìm kiếm IS180 và $137$ đánh giá FWD14 event-account native trên QuantBT.
- **Stock Mode 4 Anchors**: Toàn bộ 24 anchor records được trích xuất bằng thuật toán Mode 4 robust clustering (`select_is_only_robust_record`), tuyệt đối không dùng naive `argmax(IS_Sharpe)`.
- **Base Panels & Winner Union**: 24 base panels được tạo lập với kích thước $\le 16$ candidates (phân tầng chuẩn: anchor, top IS, diversity, controls). Cơ chế Winner Union đã được kiểm chứng tái sử dụng đánh giá, không backtest lặp lại.
- **Sharpe Decay Labels**: Nhãn suy giảm $D_{k,\theta} = SR_{IS} - SR_{FWD}$, relative decay $Y_{k,\theta} = D_{k,\theta} - D_{k,a}$ được tính toán với phân ly nhân quả nghiêm ngặt. Đồng nhất thức $Y_{k,a} \equiv 0.000$ được bảo toàn 100% trên cả 24 origins.
- **Candidate Archive**: Đã tích lũy 378 candidate records có nhãn thực trên 12 INIT origins. Bộ lọc `get_matured_archive(as_of)` không rò rỉ tương lai và cơ chế trọng số origin $\sum w_k = 1.0$ được bảo toàn.
- **Semantic Caching & Reuse**: Cache hit trên run giống hệt, cache miss khi đổi phí giao dịch/vốn, cách ly hoàn toàn dữ liệu tương lai.
- **Exit Gates**: **6/6 Gates PASS** (`G2-MODE4`, `G2-POOL`, `G2-INIT12`, `G2-LABELS`, `G2-REUSE`, `G2-REPORT_OWNER`).
- **Trạng thái**: `WAITING_OWNER_REVIEW` sẵn sàng để Owner phê duyệt mở tiếp Phase VWFO-03.

---

## Tóm tắt Phase VWFO-01 (Hoàn thành)
- **Run ID**: `vwfo01-20260928T222146Z-e7c663cf`
- **Handoff Reconciliation**: Đã làm rõ mâu thuẫn số liệu: `std_model` đạt Accuracy 62.5%, Macro F1 0.493, BSS +0.0791; `enhanced_model` đạt Accuracy 58.33% (28/48), Macro F1 0.449, BSS +0.0461. Mô hình được chọn cho WFO là `std_model` với 38 features chuẩn.
- **Timeline WFO**: Khóa 36 decision points (12 INIT + 12 DEV + 12 FINAL) trên chu kỳ 14 ngày, không chồng lấn, đủ 504 ngày forward.
- **Domain Contracts**: Dynamic sizing (10%), warmup sạch, next-open execution, và canonical Sharpe typing đều đạt 100%.
- **Config & Manifests**: Đầy đủ 6 files trong `configs/btc_volatility_conditioned_wfo_v1/`.
