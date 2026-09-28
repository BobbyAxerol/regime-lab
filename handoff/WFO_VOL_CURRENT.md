# WFO_VOL_CURRENT — BTC Volatility-Conditioned WFO Study

Current Status for `btc_volatility_conditioned_wfo_v1`:

| Phase | Technical Gate | Research / Model Scope | Latest Valid Evidence Run | Next Action |
|---|---|---|---|---|
| **VWFO-01** | **PASS** (5/5 technical gates) | **MODEL_HANDOFF_ACCEPTED_H14** | `vwfo01-20260928T222146Z-e7c663cf` | `WAITING_OWNER_REVIEW` |
| **VWFO-02** | NOT_STARTED | CANDIDATE_ARCHIVE_INIT | - | Awaiting Phase 1 Approval |
| **VWFO-03** | NOT_STARTED | SELECTION_DEVELOPMENT | - | - |
| **VWFO-04** | NOT_STARTED | POLICY_OPERATIONAL_CHECK | - | - |
| **VWFO-05** | NOT_STARTED | FINAL_WFO_AND_VERDICT | - | - |

---

## Tóm tắt Phase VWFO-01 (Hoàn thành)
- **Run ID**: `vwfo01-20260928T222146Z-e7c663cf`
- **Handoff Reconciliation**: Đã làm rõ mâu thuẫn số liệu: `std_model` đạt Accuracy 62.5%, Macro F1 0.493, BSS +0.0791; `enhanced_model` đạt Accuracy 58.33% (28/48), Macro F1 0.449, BSS +0.0461. Mô hình được chọn cho WFO là `std_model` với 38 features chuẩn.
- **Timeline WFO**: Khóa 36 decision points (12 INIT + 12 DEV + 12 FINAL) trên chu kỳ 14 ngày, không chồng lấn, đủ 504 ngày forward.
- **Domain Contracts**: Dynamic sizing (10%), warmup sạch, next-open execution, và canonical Sharpe typing đều đạt 100%.
- **Config & Manifests**: Đầy đủ 6 files trong `configs/btc_volatility_conditioned_wfo_v1/`.
