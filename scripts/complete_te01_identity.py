#!/usr/bin/env python3
"""Append TE-01 environment/archive identities; render only committed metadata."""
import argparse
import platform
import sys
from zipfile import ZipFile

from run_te01 import BASE, ROOT, digest, file_hash, git, read, record, stamp, write_bytes


def capture(out):
    marker_path = ROOT / ".lab_marker.json"
    marker = read(marker_path)
    if marker["lab_root"] != str(ROOT) or not str(sys.executable).startswith(str(ROOT / "environments/lab_venv/")):
        raise ValueError("lab identity or interpreter mismatch")
    registry = read(ROOT / "configs/alpha_registry.json")["alphas"]
    archive = ROOT / "vendor_readonly/alpha_zip_original.zip"
    members = []
    with ZipFile(archive) as stream:
        for key, spec in registry.items():
            name = "alpha_to_tes_regime_model/" + spec["filename"]
            if stream.namelist().count(name) != 1:
                raise ValueError("original alpha archive missing or duplicate allowlisted member")
            actual = digest(stream.read(name))
            members.append({"alpha": key, "member": name, "sha256": actual, "match": actual == spec["sha256"]})
    if len(members) != 4 or not all(r["match"] for r in members):
        raise ValueError("original alpha archive differs from pinned source")
    legacy = ROOT / "evidence/crypto_regime_timeedge_v2" / marker["bootstrap_lab_run_id"] / "environment_baseline.json"
    historical_archive = ROOT / "evidence/corrective_mode4_v3/audit_recovered_v1/regime_lab_audit/archive_inventory.json"
    record(out, "environment_identity.json", {
        "captured_at_utc": stamp(), "interpreter": sys.executable, "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(), "system": platform.system(),
        "release": platform.release(), "machine": platform.machine(), "libc": platform.libc_ver(),
        "capture_script_sha256": file_hash(__file__), "git_head": git("rev-parse", "HEAD").decode().strip(),
        "original_alpha_zip": {"path": str(archive.relative_to(ROOT)), "sha256": file_hash(archive), "members": members},
        "lab_marker": {"path": ".lab_marker.json", "sha256": file_hash(marker_path), "original_study_id_retained": marker["study_id"]},
        "legacy_environment": {"resolved_path": str(legacy.relative_to(ROOT)), "sha256": file_hash(legacy),
                               "stale_reference": "evidence/environment_baseline.json", "stale_path_exists": (ROOT / "evidence/environment_baseline.json").exists()},
        "historical_source_archive": {"record_path": str(historical_archive.relative_to(ROOT)),
                                      "record_sha256": file_hash(historical_archive),
                                      "historical_archive_sha256": read(historical_archive)["archive_sha256"],
                                      "current_zip_rehashed": False,
                                      "reason": "historical code ZIP has a recovered record; current lab source identity uses committed file manifest, not an assumed match to that archive"},
        "engine_runs": 0, "archive_extracted": False,
        "limits": "Metadata supplement only; source gate still waits for final FUP handoff. No archive extraction/capability certification."})


def render(out):
    p = out / "environment_identity.json"
    if git("show", "HEAD:" + p.relative_to(ROOT).as_posix()) != p.read_bytes():
        raise ValueError("identity report requires committed unchanged metadata")
    d = read(p)
    lines = ["# TE-01 — Bổ sung danh tính môi trường và archive", "",
             f"Run `{out.name}`; đo tại `{d['captured_at_utc']}`; metadata bổ sung, engine runs `{d['engine_runs']}`.", "",
             "| Nội dung | Giá trị đọc thực tế |", "|---|---|",
             f"| Python / implementation | {d['python_version']} / {d['python_implementation']} |",
             f"| OS / release / machine | {d['system']} / {d['release']} / {d['machine']} |",
             f"| Interpreter | `{d['interpreter']}` |",
             f"| ZIP alpha SHA-256 | `{d['original_alpha_zip']['sha256']}` |",
             f"| Alpha members khớp registry | {sum(r['match'] for r in d['original_alpha_zip']['members'])} / {len(d['original_alpha_zip']['members'])} |",
             f"| Legacy environment path thực | `{d['legacy_environment']['resolved_path']}` |", "",
             "`configs/study_registration.json` cũ trỏ `evidence/environment_baseline.json`, nhưng file nằm trong thư mục bootstrap run. "
             "Giữ nguyên đăng ký lịch sử; metadata mới ghi đường dẫn và hash thực. Lab marker giữ study ID gốc; "
             "v4 có registration riêng. Archive code lịch sử chỉ được dẫn lại từ recovered record; không nhận là đã băm lại ZIP đó.", "",
             "[Evidence JSON](environment_identity.json); [báo cáo chính](report.md); "
             "[package/binding](quantbt_binding_report.json); [source trước sửa](source_data_manifest.json).", "",
             "**Thuật ngữ:** metadata = thông tin nhận dạng, không là kết quả mô phỏng; SHA-256/hash = mã băm bytes; "
             "registry = danh mục alpha đã pin; archive/ZIP = gói nguồn lưu trữ; interpreter = chương trình thực thi Python; "
             "bootstrap = lần khởi tạo môi trường; marker = file đánh dấu danh tính lab; binding = API/knobs của package được dùng.", ""]
    write_bytes(out / "identity_report.md", "\n".join(lines).encode())
    record(out, "identity_report.json", {"source_sha256": file_hash(p), "report_sha256": file_hash(out / "identity_report.md"),
           "source_of_numbers": "committed environment_identity.json", "engine_runs": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("capture", "report"))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = (BASE / args.run_id).resolve()
    if out.parent != BASE.resolve() or not (out / "phase_verdict.json").is_file():
        raise SystemExit("existing TE-01 run required")
    if args.operation == "capture":
        capture(out)
    else:
        render(out)
