# FUP-02 — chi phí, validity và điều kiện làm tiếp

Capture `2026-09-12T06:58:58.163690+00:00`; checkpoint `2026-09-12T06:57:53.648419+00:00`. **Khuyến nghị: ngừng mở thêm shard/resume ở checkpoint an toàn; ưu tiên sửa TE-02.**

Không cần đợi toàn bộ FUP-02 mới làm TE-02. Chỉ việc sửa cùng source hoặc tiếp nhận kết quả FUP cuối cần phối hợp bàn giao. TE-02 có thể dùng bản sao vật lý riêng trong lab, pin source/data/package, evidence/cache riêng và cùng registration. Đây là sửa điều kiện chờ quá rộng trong khuyến nghị trước; chưa thực hiện dừng process.

| Số đo | Giá trị |
|---|---:|
| Bắt đầu FUP | 2026-09-12T04:16:24.476038+00:00 |
| Thời gian trôi qua tới capture (phút) | 162.56 |
| Tổng wall của các invocation đã kết thúc (phút) | 132.27 |
| Số invocation đã lưu | 4 |
| Cell RUN_VALID / FAILED / BUDGET_STOPPED / NOT_RUN_BUDGET | 4 / 2 / 1 / 13 |
| Cutoff SCORED / ERROR / NOT_RUN | 119 / 6 / 235 |
| Dòng trial ledger đã lưu | 3808 |
| Total wall cap đăng ký (giờ) | 12 |
| Lượt đọc audit (giây) / engine runs mới | 0.141 / 0 |

Không cộng wall invocation với shard rollup vì chúng chồng nhau. Invocation đang chạy chỉ được append trong finally, nên tổng đã đóng thiếu phần đang chạy. Không có số CPU/RAM host đáng tin cậy từ PID namespace hiện tại.

## Vì sao chưa đáng mở rộng

1. `run_one_fold` gọi provider; provider chạy `_event_account_payload` trên frame toàn kỳ sau selection; `finalize_arm` lại triển khai account. Đây là call-path source đã xác minh, chưa đo được tỷ lệ thời gian tiết kiệm; không hứa speedup. Failure ở deployment có thể làm mất kết quả selection trước đó trong returned payload.
2. `total_wall_budget_seconds` được đăng ký 12 giờ nhưng main không đọc cap này để trừ phần đã tiêu thụ trước resume; deadline chỉ theo invocation. Chưa kết luận đã vượt 12 giờ; kết luận là thiếu guard ngân sách tổng trong đường chạy đang dùng.
3. Scorer cắt frame từ train_index[0], bỏ warmup prefix; fill count cả train window được dùng cho subwindow metrics. Các source này vẫn khớp snapshot TE-01 đã audit; RUN_VALID cũ không chứng minh scorer đã đạt contract mới.
4. HMA dùng 1h, HASH dùng 15min; account nhận chính frame đó. Chưa đạt execution 1m của registration mới. CAL và REGIME bắt đầu bằng cutoff khác nhau; cần common initial/ready contract trước timing comparison.
5. FUP giữ model tape cũ để so với RF trước; không fit/đánh giá model mỗi fold theo protocol mới. FUP tự ghi không làm bootstrap, decay panel hoặc matched-budget control. Chạy đủ cells cũng không tự chứng minh time edge.

6. Cutoff ERROR được giữ terminal trên resume mặc định; COMPLETE_ALL_CELLS chỉ xuất hiện khi mọi cell có hai arm hoàn tất. Vì đã có lỗi giá limit không dương, chờ nhãn COMPLETE mà chưa sửa nguyên nhân không có cơ sở. Có thể bàn giao PARTIAL trung thực ngay khi checkpoint/ledger được đóng, không cần ép mọi cell thành công.

Các số account/selection hiện có vẫn hữu ích để debug và profile trong đúng scope. Không kết luận mọi fill đều sai, không xóa raw curves; các lỗi metrics hậu kỳ không được gán nhầm thành phép tính mà FUP chưa chạy.

## Việc nên làm tiếp

- OpenCode dừng mở job/shard mới ở checkpoint an toàn; ghi rõ cutoff đang dở, attempts, trial ledger và nguồn. Không hard-kill làm mất evidence.
- Tiến hành TE02.1/TE02.2 trong bản sao lab riêng; sửa scorer/clock và tách selection khỏi account deployment (TE02.3), tổng budget/resume (TE02.7).
- Chạy pilot nhỏ sau khi OS isolation và budget đạt; đo cold/warm cost rồi mới quyết định phạm vi rerun. Full model controls thuộc TE-03; inference/decay thuộc TE-04.

[Review JSON](review.json), [manifest](manifest.json), [captured FUP](captured/paired_discovery_fullwindow.json), [central plan](../../../implementation%20and%20test_edge_plan.md#te-02).

**Thuật ngữ:** cell = alpha × symbol; arm = CAL hoặc REGIME; shard = một cell × arm; cutoff = mốc chọn tham số; invocation = một lần gọi runner; resume = tiếp tục từ checkpoint đã lưu; wall = thời gian trôi qua của lượt chạy, khác CPU; ledger = sổ ghi trials/attempts; warmup = lịch sử khởi tạo indicator; scorer = bộ tính điểm candidate; bootstrap = lấy mẫu lại để ước lượng bất định; decay = suy giảm chất lượng theo tuổi tham số; validity = phép thử đúng trong phạm vi tuyên bố; profile = đo nơi tiêu tốn tài nguyên; namespace = phạm vi process/môi trường được nhìn thấy.
