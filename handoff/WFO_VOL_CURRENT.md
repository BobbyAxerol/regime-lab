# WFO_VOL_CURRENT — BTC Volatility-Conditioned WFO Study

Current Status for `btc_volatility_conditioned_wfo_v1`:

| Phase | Technical Gate | Research / Model Scope | Latest Valid Evidence Run | Next Action |
|---|---|---|---|---|
| **VWFO-01** | **PASS** (5/5 technical gates) | **MODEL_HANDOFF_ACCEPTED_H14** | `vwfo01-20260928T222146Z-e7c663cf` | `APPROVED` |
| **VWFO-02** | **PASS** (6/6 technical gates) | **CANDIDATE_ARCHIVE_INIT** | `vwfo02-20260929T001715Z-4225c492` | `WAITING_OWNER_REVIEW` |
| **VWFO-03** | NOT_STARTED | SELECTION_DEVELOPMENT | - | Awaiting Phase 2 Approval |
| **VWFO-04** | NOT_STARTED | POLICY_OPERATIONAL_CHECK | - | - |
| **VWFO-05** | NOT_STARTED | FINAL_WFO_AND_VERDICT | - | - |

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
