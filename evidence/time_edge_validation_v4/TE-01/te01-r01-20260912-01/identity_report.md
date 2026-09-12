# TE-01 — Bổ sung danh tính môi trường và archive

Run `te01-r01-20260912-01`; đo tại `2026-09-12T06:43:36.446336+00:00`; metadata bổ sung, engine runs `0`.

| Nội dung | Giá trị đọc thực tế |
|---|---|
| Python / implementation | 3.12.13 / CPython |
| OS / release / machine | Linux / 5.15.0-46-generic / x86_64 |
| Interpreter | `/root/bobby/pool_alpha/lab_regime_model_quantbt/environments/lab_venv/bin/python` |
| ZIP alpha SHA-256 | `57406dbb9ffdcf4617e4895925126fa73600a585a6541f996c6b2d980f6701ae` |
| Alpha members khớp registry | 4 / 4 |
| Legacy environment path thực | `evidence/crypto_regime_timeedge_v2/run-20260909T184758Z-5c2c862a/environment_baseline.json` |

`configs/study_registration.json` cũ trỏ `evidence/environment_baseline.json`, nhưng file nằm trong thư mục bootstrap run. Giữ nguyên đăng ký lịch sử; metadata mới ghi đường dẫn và hash thực. Lab marker giữ study ID gốc; v4 có registration riêng. Archive code lịch sử chỉ được dẫn lại từ recovered record; không nhận là đã băm lại ZIP đó.

[Evidence JSON](environment_identity.json); [báo cáo chính](report.md); [package/binding](quantbt_binding_report.json); [source trước sửa](source_data_manifest.json).

**Thuật ngữ:** metadata = thông tin nhận dạng, không là kết quả mô phỏng; SHA-256/hash = mã băm bytes; registry = danh mục alpha đã pin; archive/ZIP = gói nguồn lưu trữ; interpreter = chương trình thực thi Python; bootstrap = lần khởi tạo môi trường; marker = file đánh dấu danh tính lab; binding = API/knobs của package được dùng.
