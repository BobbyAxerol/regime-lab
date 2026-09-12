#!/usr/bin/env python3
"""Prepare TE-01 in a fresh namespace, or render its committed preparation report.

Does not import the lab, QuantBT, strategies, runners or the historical loader.
Does not run any experiment, change the FUP source tree, or mark TE-01 complete.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import resource
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
STUDY = "time_edge_validation_v4"
PLAN = "implementation and test_edge_plan.md"
CHECKLIST = "configs/time_edge_validation_v4/te01_checklist.json"
BASE = ROOT / "evidence" / STUDY / "TE-01"
PINNED = [
    "AGENTS.md", "CLAUDE.md", PLAN, CHECKLIST,
    "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md",
    "REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md",
    "configs/study_registration.json", "configs/alpha_registry.json",
    "configs/sandbox_policy.json", "configs/api_binding_map.json",
    "configs/minimum_economic_effect.json", "configs/requirements.lock",
    "configs/lab05_full_emission_tape.json", "configs/lab05_regime_model_registry.json",
    "snapshots/server_core_v1/manifest.json",
    "evidence/corrective_mode4_v3/RF-01/corrective_study_spec.json",
    "evidence/corrective_mode4_v3/RF-05/freeze_manifest.json",
    "evidence/corrective_mode4_v3/followup-studies/followup_studies_registration.json",
    "evidence/corrective_mode4_v3/FUP-02/budget_revision.json",
]
FUP = "evidence/corrective_mode4_v3/FUP-02/paired_discovery_fullwindow.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict(data):
    def invalid(value):
        raise ValueError(f"non-standard JSON number: {value}")
    return json.loads(data, parse_constant=invalid)


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def git(*args):
    subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                   capture_output=True, check=True)
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def capture(destination):
    if destination.exists():
        raise SystemExit("preparation evidence is append-only; choose a fresh run ID")
    start = time.monotonic()
    checklist = strict((ROOT / CHECKLIST).read_bytes())
    assert len(checklist["tasks"]) == 7
    identity = {"study_id": STUDY, "phase_id": "TE-01", "lab_run_id": destination.name}
    created = datetime.now(timezone.utc).isoformat()
    paths = [ROOT / rel for rel in PINNED]
    paths.extend(p for folder in ("src", "scripts", "tests")
                 for p in sorted((ROOT / folder).rglob("*.py")) if not p.is_symlink())
    manifest = []
    for path in paths:
        data = path.read_bytes()
        manifest.append({"path": path.relative_to(ROOT).as_posix(),
                         "sha256": sha(data), "bytes": len(data)})
    fup_bytes = (ROOT / FUP).read_bytes()
    fup = strict(fup_bytes)
    fup_stable = (ROOT / FUP).read_bytes() == fup_bytes
    sections = re.findall(r"^### (TEF-\d{2}) — (.+?)\n(.*?)(?=^<a id=|^### 5\.1)",
                          (ROOT / PLAN).read_text(), re.MULTILINE | re.DOTALL)
    assert len(sections) == 20 and len({item[0] for item in sections}) == 20
    findings = [{"finding_id": key, "title_severity_phase": title,
                 "status": "OPEN", "owner": "Codex", "review_basis": body.strip(),
                 "implementation_commit": None, "verification_ref": None,
                 "null_reason": "Implementation and runtime validation have not started."}
                for key, title, body in sections]
    packages = []
    for name in ("quantbt-engine", "quantbt-native", "numpy", "pandas", "optuna"):
        dist = metadata.distribution(name)
        location = Path(dist.locate_file("")).resolve()
        if not location.is_relative_to(ROOT / "environments/lab_venv"):
            raise SystemExit(f"dependency origin outside the lab venv: {name}")
        packages.append({"distribution": name, "version": dist.version,
                         "location": str(location), "scope": "distribution metadata; module not imported"})
    destination.mkdir(parents=True)
    (destination / "fup02_checkpoint.json").write_bytes(fup_bytes)
    write(destination / "source_data_manifest.json", {
        **identity, "schema": "regime_lab.te01_source_manifest.v1", "captured_at_utc": created,
        "git_head": git("rev-parse", "HEAD").decode().strip(),
        "git_worktree_status": git("status", "--porcelain").decode(),
        "files": manifest, "packages": packages,
        "snapshot_verification": "MANIFEST_HASH_PINNED; raw parquet bytes have not been rehashed",
        "concurrency": "Preparation snapshot only; final source/fup identity must be pinned after FUP-02 handoff."})
    write(destination / "finding_disposition.json", {
        **identity, "schema": "regime_lab.te01_findings.v1", "findings": findings})
    tasks = [{**task, "status": "IN_PROGRESS" if task["task_id"] in ("TE01.1", "TE01.2")
              else "NOT_STARTED"} for task in checklist["tasks"]]
    write(destination / "preparation.json", {
        **identity, "schema": "regime_lab.te01_preparation.v1", "created_at_utc": created,
        "status": "IN_PROGRESS_PREPARATION_ONLY", "tasks": tasks,
        "registration_frozen": False, "phase_exit_passed": False,
        "fup02_intake": {
            "status": "PENDING_FINAL_FUP02_HANDOFF", "observed_source": FUP,
            "observed_checkpoint_at_utc": fup.get("last_checkpoint_at_utc"),
            "observed_status": fup.get("status"), "stable_during_read": fup_stable,
            "captured_sha256": sha(fup_bytes), "captured_path": "fup02_checkpoint.json",
            "coverage": dict(Counter(c["coverage_status"] for c in fup["cells"])),
            "limit": "A checkpoint and terminal cell labels do not themselves prove the external agent has completed its run."},
        "rules_loaded": ["AGENTS.md", "CLAUDE.md", "../.agents/AGENTS.md"],
        "verification_scope": {
            "manifest_files_hashed": len(manifest), "findings_indexed": len(findings),
            "task_count": len(tasks), "engine_runs": 0, "optimizer_runs": 0,
            "tests_executed": 0, "market_statistical_tests": 0,
            "elapsed_seconds": time.monotonic() - start,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
        "economic_metrics": None, "economic_metrics_reason": "No economic experiment was run in preparation.",
        "remaining_before_te01_exit": [
            "Final FUP-02 intake and executable source identity after OpenCode finishes.",
            "Complete original A/D/N finding mapping and raw-data/installed-contract verification.",
            "Freeze metric/evaluation, hypothesis/multiplicity/support/power and model protocols.",
            "Freeze measured route/resource contracts and select the affected-output reuse policy.",
            "Write and execute the before-repair regression cases before TE-02/03 repairs."],
        "next_task": "TE01.3/4/5: specify contracts and analysis decisions; keep final FUP intake pending."})
    write(destination / "artifact_manifest.json", {
        **identity, "schema": "regime_lab.te01_artifact_manifest.v1",
        "artifacts": [{"path": p.name, "sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                      for p in sorted(destination.iterdir()) if p.is_file()]})
    print(f"TE-01 preparation captured: {destination.relative_to(ROOT)}; phase exit remains pending.")


def render(destination):
    artifact = strict((destination / "artifact_manifest.json").read_bytes())
    for entry in artifact["artifacts"]:
        path = destination / entry["path"]
        data = path.read_bytes()
        assert sha(data) == entry["sha256"] and len(data) == entry["bytes"]
        committed = git("show", f"HEAD:{path.relative_to(ROOT).as_posix()}")
        if committed != data:
            raise SystemExit(f"report input differs from committed artifact: {path.name}")
    payload = strict((destination / "preparation.json").read_bytes())
    counts = payload["verification_scope"]
    fup = payload["fup02_intake"]
    report = ["# TE-01 — Báo cáo khởi động và chuẩn bị", "",
              f"Run `{payload['lab_run_id']}`; chụp lúc {payload['created_at_utc']}.", "",
              "**Trạng thái: IN_PROGRESS_PREPARATION_ONLY. Chưa hoàn thành TE-01; chưa sửa runtime.**", "",
              "Đã đọc rules; đăng ký checklist trước code; ghi danh tính nguồn và sổ findings. "
              "Không can thiệp FUP-02 hoặc chạy thêm mô phỏng.", "",
              "| Phạm vi đo | Số lượng |", "|---|---:|"]
    for name, key in (("Files đã băm", "manifest_files_hashed"), ("Findings còn OPEN", "findings_indexed"),
                      ("Nhiệm vụ TE-01", "task_count"), ("Engine runs", "engine_runs"),
                      ("Optimizer runs", "optimizer_runs"), ("Tests đã chạy", "tests_executed"),
                      ("Market statistical tests", "market_statistical_tests")):
        report.append(f"| {name} | {counts[key]} |")
    report += ["", f"FUP-02 snapshot: `{fup['observed_status']}` tại `{fup['observed_checkpoint_at_utc']}`; "
               f"coverage `{json.dumps(fup['coverage'], ensure_ascii=False)}`. Đây chưa là tiếp nhận kết quả cuối.",
               "", "## Trạng thái nhiệm vụ", "", "| Task | Trạng thái | Output còn phải hoàn thành |",
               "|---|---|---|"]
    for task in payload["tasks"]:
        report.append(f"| {task['task_id']} | {task['status']} | {', '.join(task['required_outputs'])} |")
    report += ["", "## Model, time edge và decay", "",
               "Model regime chưa được đánh giá lại trong preparation; tape cũ chỉ được pin hash. "
               "Return, Sharpe, PF, D1/D2/D3 và khoảng tin cậy đều NOT_EVALUATED, không thay bằng số 0. "
               "Báo cáo này không cung cấp bằng chứng time edge.", "", "## Điều kiện còn thiếu", ""]
    report.extend(f"- {reason}" for reason in payload["remaining_before_te01_exit"])
    report += ["", "## Nguồn và tái tạo", "",
               "[Preparation JSON](preparation.json), [source/data manifest](source_data_manifest.json), "
               "[finding ledger](finding_disposition.json), [artifact manifest](artifact_manifest.json).", "",
               "```bash", f"PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01_preparation.py render --run-id {destination.name}",
               "```", "", "Report writer chỉ đọc artifacts đã commit; không gọi engine.", "",
               "## Thuật ngữ", "",
               "**Pin/hash:** lưu mã băm để nhận diện đúng bytes nguồn; không chứng minh hành vi đúng. "
               "**Finding:** vấn đề được audit ghi nhận; OPEN nghĩa chưa có bằng chứng đóng. "
               "**Checkpoint/snapshot:** bản ghi tại một thời điểm, không đảm bảo agent đã hoàn tất. "
               "**Coverage:** số cells trong từng trạng thái; cell là cặp alpha/symbol. "
               "**Engine/optimizer:** mô phỏng tài khoản/tìm tham số; cả hai chưa chạy ở preparation. "
               "**Regime:** trạng thái thị trường do model suy ra. **Time edge:** lợi ích của thời điểm dùng tham số. "
               "**Decay:** suy giảm IS→OOS (D1), theo tuổi tham số cố định (D2), hoặc thay đổi giữa folds (D3). "
               "**Sharpe/PF:** lợi nhuận điều chỉnh theo biến động/tỷ số lãi trên lỗ theo sampling đã định. "
               "**IS/OOS:** khoảng dùng chọn tham số/khoảng đánh giá về sau.", ""]
    with (destination / "report.md").open("x") as stream:
        stream.write("\n".join(report))
    write(destination / "report.json", payload)
    print(f"Rendered committed preparation artifacts into {destination.relative_to(ROOT)}/report.md + report.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("capture", "render"))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", args.run_id):
        raise SystemExit("run ID must be a single directory name")
    destination = (BASE / args.run_id).resolve()
    if not destination.is_relative_to(ROOT) or destination.parent != BASE.resolve():
        raise SystemExit("run directory must stay under the TE-01 evidence root")
    (capture if args.operation == "capture" else render)(destination)


if __name__ == "__main__":
    main()
