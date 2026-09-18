# TE-01 — Registration, nguồn sự thật và phạm vi tái sử dụng

Run `te01-r01-20260912-01`; thời điểm 2026-09-12T06:38:35.906896+00:00. **PARTIAL_TECHNICAL_CLOSURE_FINAL_FUP_HANDOFF_PENDING**.

Đã kiểm chứng registration (bộ quy tắc được đăng ký trước phép thử) cho sửa chữa kỹ thuật. Chưa đóng toàn TE-01 vì chưa có bàn giao cuối FUP-02; chưa chạy mô phỏng hoặc kiểm định lợi thế thị trường.

## 1. Phạm vi và chỉ mục

Theo [central plan TE01.1–TE01.7](../../../../implementation%20and%20test_edge_plan.md#te-01); [G3 RF-01.1–RF-01.5, §4/6/7/8/10](../../../../REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md); [G2 §0/2/6/11/13](../../../../QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md). QuantBT gốc và alpha gốc chỉ đọc. Runner dùng venv lab, không import historical loader. Những ca trước sửa được giữ là FAIL thật; không đổi thành PASS hay xfail.

## 2. Số đo và phép thử thực tế

| Nội dung | Đo được |
|---|---:|
| Contract tests PASS / FAIL / SKIP | 69 / 0 / 0 |
| Before-repair PASS / FAIL / unexpected errors | 0 / 8 / 0 |
| Snapshot files / bytes đã đối chiếu hash và metadata | 627 / 1448678208 |
| Nguồn/config đã giữ nguyên bytes | 298 |
| Findings đã map / TEF được đóng | 49 / 0 |
| Wall / CPU giây | 16.299 / 10.058 |
| Process peak RSS KiB | 213796 |
| Engine / optimizer / market statistical tests | 0 / 0 / 0 |

Hash verification (đối chiếu bytes) và metadata không chứng minh toàn bộ candle rows đúng hoặc point-in-time availability đúng; đây là danh tính dữ liệu, không là kết quả tài chính. CPU/RSS là process audit; subprocess tests có wall/exit/XML riêng.

## 3. Baseline trước sửa

| Ca yêu cầu hành vi đúng | Kết quả | Sai khác |
|---|---|---|
| test_rf05_excludes_pre_evaluation_return | FAIL | assert True is False |
| test_adjacent_age_windows_are_half_open | FAIL | assert (91, 91) == (90, 90)      At index 0 diff: 91 != 90   Use -v to get more diff |
| test_d2_uses_the_computed_pf_key | FAIL | assert None == 2.0444444444444456 ± 2.0e-06      comparison failed   Obtained: None   Expected: 2.0444444444444456 ± 2.0e-06 |
| test_only_losses_are_zero_pf_not_no_trades | FAIL | assert None == 0.0 |
| test_future_model_ready_cannot_trigger | FAIL | AssertionError: assert ['2021-01-03T00:00:00+00:00'] == []      Left contains one more item: '2021-01-03T00:00:00+00:00'   Use -v to get more diff |
| test_missing_eligibility_cannot_trigger | FAIL | AssertionError: assert ['2021-01-03T00:00:00+00:00'] == []      Left contains one more item: '2021-01-03T00:00:00+00:00'   Use -v to get more diff |
| test_constant_state_has_registered_max_age | FAIL | assert 0 >= 1  +  where 0 = len([]) |
| test_unavailable_training_targets_do_not_change_profile | FAIL | assert 9.5 == 309.5 |

Log đầy đủ: [baseline log](regression_baseline.log), [baseline JSON](regression_baseline.json), [contract tests](contract_tests.json). Source probes (thử hàm nguồn cô lập) không phải full engine controls; ca target purge dùng centroid stub để cô lập logic profile, không nhận là kiểm chất lượng learned model.

Acceptance T01–T64: `{"NOT_EXERCISED_IN_TE01": 49, "PARTIAL_CONTRACT_OR_RED_BASELINE": 12, "BLOCKED_ISOLATION_UNAVAILABLE": 2, "PASS_MEASURED_IDENTITY": 1}`. [Bảng đủ 64 yêu cầu](acceptance_coverage.json) ghi ca chưa chạy và lý do; số pytest PASS không đồng nghĩa 64 yêu cầu đã đạt.

## 4. Quyết định toán học và thiết kế

Daily return giữ phí đầu account và previous mark, sau đó lọc [start,end); các age windows không chồng ngày biên. Sharpe dùng daily UTC, sqrt(365), sample standard deviation ddof=1. PF theo return observations khác PF theo trade; chỉ lỗ cho PF=0, không lỗ cho null kèm reason; không thêm epsilon.

Đăng ký bốn hypotheses: H-TIMING, H-BUDGET, H-DECAY, H-MODEL-INFO. Holm dùng cả family 4; common calendar blocks giữ dependence giữa arms/cells. CI đồng thời Bonferroni tách khỏi CI 95% mô tả. Block length, seeds, support, false-positive/power calibration và stopping đã ghi trước; TE-01 chưa chạy inference này.

δ kinh tế được đăng ký bằng công thức cost/account-turnover trên M4_CAL training-only đã qualify. Số δ phải materialize và freeze với trace hashes trước TE-04; chưa có số đó thì cấm claim kinh tế. Không kế thừa âm thầm MDE cũ khi execution/sizing đổi. MDE thống kê (effect có thể phát hiện ở power/alpha đã định) là đại lượng khác.

D1 so cùng selected θ IS/OOS và ghi selection bias; D2 cùng θ qua H1/H2/H3, so cohort calendar/context có support; D3 là observed operational fold change. Không ghép ordinal fold #3 hai arms; D2 chưa loại được market-context confounding thì chỉ là association diagnostic.

## 5. Model regime được dùng và đánh giá

**INHERITED_FROZEN_INPUT, NOT_REEVALUATED_IN_TE01.** Model cũ chỉ là input đã pin; không fit thêm model để lấp báo cáo. Protocol mới đăng ký common BTC context, raw features G1/G2/G5, M0 + JM K2/K3 với lambda 0.5/1/2, inner-train scaler và purge theo outcome availability. Regime ID là ký hiệu trong namespace model, không mặc định bull/bear; mô tả nhãn chỉ từ train. TE-03 phải nối actual selected design → emitted tape → controller và báo model theo từng fold.

Information target là future paired candidate utility từ cùng QuantBT/economics, không phải future return trừ trailing return. Full positive/null controls phải qua learned model và installed Mode 4; power chưa được chứng minh trong TE-01.

## 6. QuantBT và chiến lược

Actual import: `/root/bobby/pool_alpha/lab_regime_model_quantbt/environments/lab_venv/lib/python3.12/site-packages/quantbt/__init__.py`. Installed config matches registered knobs: `True`. Bốn alpha giữ thesis, 10% current-equity allocation và initial capital đã đăng ký; protective/partial behavior không chuyển thành target-only để chạy nhanh. Primary execution 1m; coarse next-close cần cohort khác có tên và qualification, không tự coi factory name là actual clock.

[Binding report](quantbt_binding_report.json) giữ public signatures, resolved knobs, wheels/.so hashes và VFY01–VFY11 source anchors. Đây là import/config/source qualification, chưa là public-path runtime parity hoặc Rust speedup.

## 7. FUP-02, reuse và invalidation

FUP snapshot `PARTIAL_BUDGET_STOPPED` tại `2026-09-12T06:36:57.892446+00:00`; `{"NOT_RUN_BUDGET": 13, "RUN_VALID": 3, "FAILED": 2, "BUDGET_STOPPED": 2}`. Bàn giao cuối vẫn pending; không dừng/resume/sửa FUP thay OpenCode.

| Cell | FUP status | Raw data | Account dùng cho claim mới |
|---|---|---|---|
| A-SC/BTCUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-SC/ETHUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-SC/SOLUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-SC/BNBUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-SC/DOGEUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-HMA/BTCUSDT | RUN_VALID | hash-verified reuse | diagnostic only; affected chain retest |
| A-HMA/ETHUSDT | RUN_VALID | hash-verified reuse | diagnostic only; affected chain retest |
| A-HMA/SOLUSDT | FAILED | hash-verified reuse | diagnostic only; affected chain retest |
| A-HMA/BNBUSDT | RUN_VALID | hash-verified reuse | diagnostic only; affected chain retest |
| A-HMA/DOGEUSDT | FAILED | hash-verified reuse | diagnostic only; affected chain retest |
| A-VWAP/BTCUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-VWAP/ETHUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-VWAP/SOLUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-VWAP/BNBUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-VWAP/DOGEUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-HASH/BTCUSDT | BUDGET_STOPPED | hash-verified reuse | diagnostic only; affected chain retest |
| A-HASH/ETHUSDT | BUDGET_STOPPED | hash-verified reuse | diagnostic only; affected chain retest |
| A-HASH/SOLUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-HASH/BNBUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |
| A-HASH/DOGEUSDT | NOT_RUN_BUDGET | hash-verified reuse | diagnostic only; affected chain retest |

[Reuse decision](reuse_decision.json) tách report recompute khỏi scorer/model/execution rerun. [Invalidation overlay](invalidation.json) chặn tái sử dụng financial claims bị ảnh hưởng; giữ nguyên raw curves và kết luận lịch sử. Không đưa pending/failed vào aggregate bằng số 0. [Finding disposition](finding_disposition.json) giữ đủ 49 IDs và source/caller/test references.

## 8. Readiness và giới hạn còn lại

OS worker isolation measured available: `False`; [probe evidence](os_isolation.json). Việc đọc và kiểm hợp đồng được thực hiện trong sandbox hiện tại; không suy nó thành quyền chạy market workers thiếu containment theo lab policy.

- Final FUP-02 handoff and pin executable source before changing its imports/configs.
- Actual engine/clock/scorer and model/control qualification belongs to TE-02/03.
- Materialize registered cost threshold from qualified training-only traces before TE-04.
- No new market job until measured isolation and total resource allocation pass.

**Verdict:** TECHNICAL_ONLY; economic NOT_EVALUABLE; runtime gate CLOSED. Không có time-edge estimate mới. Các FAIL trước sửa là backlog đã tái hiện, không phải bằng chứng regime không có edge.

## 9. Tái tạo và bằng chứng

```bash
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01.py audit --run-id FRESH_RUN_ID
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01.py report --run-id te01-r01-20260912-01
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01.py runtime-gate --run-id te01-r01-20260912-01
```

Commit audit inputs trước render. Runtime-gate phải trả lỗi ở trạng thái này; audit không chạy engine. [Artifact manifest](artifact_manifest.json), [phase JSON](phase_verdict.json), [protected-source verification](protected_source_verification.json), [snapshot verification](snapshot_verification.json).

## 10. Thuật ngữ

**Registration:** quy tắc/hypotheses đăng ký trước phép thử. **Gate:** điều kiện chặn bước sau khi chưa đủ evidence. **WFO/Mode 4:** tối ưu cuốn chiếu bằng bộ chọn robust IS của QuantBT. **IS/OOS:** khoảng dùng chọn tham số/khoảng đánh giá về sau. **θ:** bộ tham số cố định; **fold:** khoảng operational hoặc training đã định. **Regime/JM:** trạng thái model thị trường/jump model có penalty chuyển trạng thái. **Namespace:** danh tính nhãn riêng mỗi model vintage. **D1/D2/D3:** IS→OOS gap/age degradation/operational fold change. **PF:** tỷ lệ phần lãi trên độ lớn phần lỗ, luôn kèm sampling. **Sharpe:** mean return chia sample deviation, annualize đúng clock. **CI:** khoảng tin cậy; **δ:** ngưỡng cải thiện kinh tế; **Holm/Bonferroni:** điều chỉnh kiểm nhiều giả thuyết. **Power/false positive:** xác suất phát hiện hiệu ứng/xác suất báo có hiệu ứng khi null đúng. **Support:** lượng quan sát, recurrence và hành vi đủ để đánh giá; không chỉ đếm bars. **Bootstrap block:** lấy mẫu lại theo khối thời gian để giữ dependence. **Warmup:** lịch sử khởi tạo indicator, ngoài scoring. **Purge:** loại training targets chưa available trước cutoff. **Cutoff:** biên thông tin được phép dùng. **Hash/manifest:** mã băm bytes và danh mục nguồn. **Snapshot/checkpoint:** bản chụp dữ liệu/trạng thái tại thời điểm. **Runtime parity:** thực thi cùng contract cho trace tài chính khớp; metadata không thay thế được. **RSS/CPU/wall:** bộ nhớ cư trú/thời gian CPU/thời gian trôi qua. **Replay/retrospective:** mô phỏng tuần tự/đánh giá lịch sử đã được xem. **Thesis:** logic chiến lược gốc; **exposure:** mức vị thế thực; **turnover:** notional giao dịch chuẩn hóa vốn. **Native/.so:** backend biên dịch/thư viện nhị phân; có file không đồng nghĩa đã chạy backend đó.

## 11. Từng task và hợp đồng có thể đọc trực tiếp

| Task | Trạng thái / giới hạn |
|---|---|
| TE01.1 | PINNED_CHECKPOINT_FINAL_FUP_HANDOFF_PENDING |
| TE01.2 | MAPPED_49_FINDINGS_RUNTIME_RETESTS_REMAIN_OPEN |
| TE01.3 | CONTRACT_VALIDATED |
| TE01.4 | REGISTERED_COST_FORMULA_NUMERIC_FREEZE_REQUIRED_BEFORE_TE04 |
| TE01.5 | REGISTERED_NOT_FITTED_OR_DEPLOYED |
| TE01.6 | TE01_BUDGET_MEASURED_FUTURE_ENGINE_BUDGET_NOT_ALLOCATED |
| TE01.7 | REUSE_AND_INVALIDATION_OVERLAY_RECORDED |

Các guide references của từng task nằm tại TE-01 trong central plan; bộ [registration manifest](../../../../configs/time_edge_validation_v4/r01/registration_manifest.json) khóa hash các hợp đồng dưới đây.

- [case_registry.json](../../../../configs/time_edge_validation_v4/r01/case_registry.json)
- [compute_budget.json](../../../../configs/time_edge_validation_v4/r01/compute_budget.json)
- [evaluation_windows.json](../../../../configs/time_edge_validation_v4/r01/evaluation_windows.json)
- [execution_contract.json](../../../../configs/time_edge_validation_v4/r01/execution_contract.json)
- [metric_contract.json](../../../../configs/time_edge_validation_v4/r01/metric_contract.json)
- [model_protocol.json](../../../../configs/time_edge_validation_v4/r01/model_protocol.json)
- [reuse_policy.json](../../../../configs/time_edge_validation_v4/r01/reuse_policy.json)
- [statistical_analysis_plan.json](../../../../configs/time_edge_validation_v4/r01/statistical_analysis_plan.json)
- [study_registration.json](../../../../configs/time_edge_validation_v4/r01/study_registration.json)
- [te01_execution_checklist.json](../../../../configs/time_edge_validation_v4/r01/te01_execution_checklist.json)

Corrections TE-01: thêm bộ hợp đồng chuẩn và overlay phạm vi sử dụng; chưa sửa caller RF/FUP. [Correction ledger](../../../../configs/correction_ledger.json) giữ lịch sử và chỉ mục TE-01. Không có kết quả thị trường bị ghi đè. Ngân sách audit không cho phép engine run.
