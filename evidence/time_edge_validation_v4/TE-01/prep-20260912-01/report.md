# TE-01 — Báo cáo khởi động và chuẩn bị

Run `prep-20260912-01`; chụp lúc 2026-09-12T05:53:45.101634+00:00.

**Trạng thái: IN_PROGRESS_PREPARATION_ONLY. Chưa hoàn thành TE-01; chưa sửa runtime.**

Đã đọc rules; đăng ký checklist trước code; ghi danh tính nguồn và sổ findings. Không can thiệp FUP-02 hoặc chạy thêm mô phỏng.

| Phạm vi đo | Số lượng |
|---|---:|
| Files đã băm | 284 |
| Findings còn OPEN | 20 |
| Nhiệm vụ TE-01 | 7 |
| Engine runs | 0 |
| Optimizer runs | 0 |
| Tests đã chạy | 0 |
| Market statistical tests | 0 |

FUP-02 snapshot: `PARTIAL_BUDGET_STOPPED` tại `2026-09-12T05:53:10.011734+00:00`; coverage `{"NOT_RUN_BUDGET": 14, "RUN_VALID": 3, "FAILED": 2, "BUDGET_STOPPED": 1}`. Đây chưa là tiếp nhận kết quả cuối.

## Trạng thái nhiệm vụ

| Task | Trạng thái | Output còn phải hoàn thành |
|---|---|---|
| TE01.1 | IN_PROGRESS | source_data_manifest.json, fup02_intake.json |
| TE01.2 | IN_PROGRESS | finding_disposition.json |
| TE01.3 | NOT_STARTED | metric_contract.json, evaluation_windows.json |
| TE01.4 | NOT_STARTED | study_registration.json, statistical_analysis_plan.json |
| TE01.5 | NOT_STARTED | model_protocol.json |
| TE01.6 | NOT_STARTED | compute_budget.json, execution_contract.json |
| TE01.7 | NOT_STARTED | reuse_decision.json, invalidation.json |

## Model, time edge và decay

Model regime chưa được đánh giá lại trong preparation; tape cũ chỉ được pin hash. Return, Sharpe, PF, D1/D2/D3 và khoảng tin cậy đều NOT_EVALUATED, không thay bằng số 0. Báo cáo này không cung cấp bằng chứng time edge.

## Điều kiện còn thiếu

- Final FUP-02 intake and executable source identity after OpenCode finishes.
- Complete original A/D/N finding mapping and raw-data/installed-contract verification.
- Freeze metric/evaluation, hypothesis/multiplicity/support/power and model protocols.
- Freeze measured route/resource contracts and select the affected-output reuse policy.
- Write and execute the before-repair regression cases before TE-02/03 repairs.

## Nguồn và tái tạo

[Preparation JSON](preparation.json), [source/data manifest](source_data_manifest.json), [finding ledger](finding_disposition.json), [artifact manifest](artifact_manifest.json).

```bash
PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01_preparation.py render --run-id prep-20260912-01
```

Report writer chỉ đọc artifacts đã commit; không gọi engine.

## Thuật ngữ

**Pin/hash:** lưu mã băm để nhận diện đúng bytes nguồn; không chứng minh hành vi đúng. **Finding:** vấn đề được audit ghi nhận; OPEN nghĩa chưa có bằng chứng đóng. **Checkpoint/snapshot:** bản ghi tại một thời điểm, không đảm bảo agent đã hoàn tất. **Coverage:** số cells trong từng trạng thái; cell là cặp alpha/symbol. **Engine/optimizer:** mô phỏng tài khoản/tìm tham số; cả hai chưa chạy ở preparation. **Regime:** trạng thái thị trường do model suy ra. **Time edge:** lợi ích của thời điểm dùng tham số. **Decay:** suy giảm IS→OOS (D1), theo tuổi tham số cố định (D2), hoặc thay đổi giữa folds (D3). **Sharpe/PF:** lợi nhuận điều chỉnh theo biến động/tỷ số lãi trên lỗ theo sampling đã định. **IS/OOS:** khoảng dùng chọn tham số/khoảng đánh giá về sau.
