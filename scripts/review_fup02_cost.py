#!/usr/bin/env python3
"""Read-only FUP-02 cost/validity review; no runner imports or engine calls."""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
FUP = ROOT / "evidence/corrective_mode4_v3/FUP-02"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def capture(out):
    if out.exists():
        raise ValueError("fresh review generation required")
    started = time.monotonic()
    names = ("paired_discovery_fullwindow.json", "attempts.jsonl", "trial_ledger.jsonl",
             "budget_revision.json", "cell_coverage.json", "coverage_review.json", "report.md", "report.json")
    stable = False
    for _ in range(3):
        captured = {n: (FUP/n).read_bytes() for n in names if (FUP/n).is_file()}
        stable = all((FUP/n).read_bytes() == b for n,b in captured.items())
        if stable:
            break
    if not stable:
        raise ValueError("checkpoint changed during read; no coherent generation captured")
    now = datetime.now(timezone.utc)
    for name, data in captured.items():
        write(out/"captured"/name, data)
    d = json.loads(captured["paired_discovery_fullwindow.json"])
    invocations = [{k: v.get(k) for k in ("invocation", "started_at_utc", "ended_at_utc", "wall_seconds", "budget_seconds")}
                   for v in d["invocations"]]
    entries = [e for c in d["cells"] for s in c["shards"].values() for e in s["cutoff_results"]]
    attempts = [json.loads(x) for x in captured["attempts.jsonl"].splitlines()]
    latest = {r["attempt_id"]: r for r in attempts}
    old = json.loads((ROOT/"evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/source_data_manifest.json").read_text())
    old_hashes = {r["path"]: r["sha256"] for r in old["files"]}
    sources = []
    for name in ("scripts/run_fup02.py", "src/crypto_regime_lab/experiments/dynamic_fold_provider.py",
                 "src/crypto_regime_lab/experiments/regime_schedule.py", "src/crypto_regime_lab/integration/event_account.py"):
        data = (ROOT/name).read_bytes()
        write(out/"source"/(name+".txt"), data)
        sources.append({"path": name, "sha256": sha(data), "same_as_te01_baseline": sha(data)==old_hashes[name]})
    runner = ast.parse((ROOT/"scripts/run_fup02.py").read_text())
    provider = ast.parse((ROOT/"src/crypto_regime_lab/experiments/dynamic_fold_provider.py").read_text())
    def fn(tree, name):
        return next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    def calls(node, name):
        return [n.lineno for n in ast.walk(node) if isinstance(n,ast.Call)
                and ((isinstance(n.func,ast.Name) and n.func.id==name) or
                     (isinstance(n.func,ast.Attribute) and n.func.attr==name))]
    main = fn(runner,"main")
    budget_reads = [n.lineno for n in ast.walk(main) if isinstance(n,ast.Subscript)
                    and isinstance(n.slice,ast.Constant) and n.slice.value=="total_wall_budget_seconds"]
    source_checks = {
        "fold_calls_whole_provider_lines": calls(fn(runner,"run_one_fold"),"run_cutoff_walk_forward"),
        "provider_deploys_account_lines": calls(fn(provider,"run_cutoff_walk_forward"),"_event_account_payload"),
        "final_arm_deploys_again_lines": calls(fn(runner,"finalize_arm"),"_event_account_payload"),
        "main_reads_registered_total_wall_cap_lines": budget_reads,
        "scope": "AST/source call-path witnesses; not sampled runtime timings or proof of exact savings"}
    assert all(source_checks[k] for k in ("fold_calls_whole_provider_lines","provider_deploys_account_lines","final_arm_deploys_again_lines"))
    cells = []
    for c in d["cells"]:
        cells.append({"cell":c["cell"],"status":c["coverage_status"],"interval":c["interval"],
                      "arms":{a:{"status":s["status"],"scored":len(s["completed_cutoffs"]),"planned":s["fold_count"],
                                 "first_cutoff":s["cutoffs"][0],"account_wall_seconds":s.get("account_wall_seconds")}
                              for a,s in c["shards"].items()}})
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {"study_id":"time_edge_validation_v4","lab_run_id":out.name,"phase_id":"FUP02_REVIEW",
              "captured_at_utc":now.isoformat(),"checkpoint_at_utc":d["last_checkpoint_at_utc"],
              "first_run_at_utc":d["run_started_at_utc"],"checkpoint_status":d["status"],
              "elapsed_since_start_seconds":(now-datetime.fromisoformat(d["run_started_at_utc"])).total_seconds(),
              "closed_invocation_wall_seconds":sum(float(r["wall_seconds"] or 0) for r in invocations if r["ended_at_utc"]),
              "stored_shard_wall_sum_seconds":sum(c.get("wall_seconds_total",0) for c in d["cells"]),
              "do_not_sum_wall_measures":"invocation wall and shard rollups overlap; incomplete invocation is absent until finally; neither measures CPU",
              "invocations":invocations,"open_attempts":[r for r in latest.values() if r["status"]=="STARTED"],
              "coverage":dict(Counter(c["coverage_status"] for c in d["cells"])),"cells":cells,
              "cutoff_counts":dict(Counter(e["status"] for e in entries)),
              "trial_ledger_rows":len(captured["trial_ledger.jsonl"].splitlines()),
              "failed_cutoffs":[{"cell":c["cell"],"arm":a,"fold":e["fold_id"],"reason":e["reason"]}
                                for c in d["cells"] for a,s in c["shards"].items() for e in s["cutoff_results"] if e["status"]=="ERROR"],
              "registered_total_wall_seconds":d["run_config"]["total_wall_budget_seconds"],
              "claim_limits":d["claim_limits"],"regime_tape":d["regime_tape"],"source_identity":sources,
              "source_checks":source_checks,"process_visibility":"current tool sees only its own PID namespace; live OpenCode CPU/RSS/liveness unverified",
              "recommendation":"PAUSE_NEW_FUP_SHARDS_AT_SAFE_CHECKPOINT_AND_REPAIR_TE02_IN_ISOLATED_LAB_COPY",
              "dependency_correction":"final FUP intake is required for accepting final FUP artifacts, not for independent TE02 development on pinned lab-owned source",
              "actions_taken":"read-only capture and review; no signals sent, no source/config/process changes to FUP",
              "engine_runs":0,"audit_wall_seconds":time.monotonic()-started}
    write(out/"review.json",(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode())
    manifest={"study_id":"time_edge_validation_v4","lab_run_id":out.name,
              "artifacts":[{"path":p.relative_to(out).as_posix(),"sha256":sha(p.read_bytes())} for p in sorted(out.rglob('*')) if p.is_file()]}
    write(out/"manifest.json",(json.dumps(manifest,indent=2)+"\n").encode())
    print(json.dumps({k:result[k] for k in ("captured_at_utc","checkpoint_at_utc","elapsed_since_start_seconds","closed_invocation_wall_seconds","coverage","cutoff_counts","audit_wall_seconds")},ensure_ascii=False))


def report(out):
    p=out/"review.json"
    subprocess.run(["git","status","--porcelain"],cwd=ROOT,capture_output=True,check=True)
    if subprocess.check_output(["git","show","HEAD:"+p.relative_to(ROOT).as_posix()],cwd=ROOT)!=p.read_bytes():
        raise ValueError("report requires committed unchanged review")
    d=json.loads(p.read_text())
    for row in json.loads((out/"manifest.json").read_text())["artifacts"]:
        assert sha((out/row["path"]).read_bytes())==row["sha256"]
    lines=["# FUP-02 — chi phí, validity và điều kiện làm tiếp", "",
           f"Capture `{d['captured_at_utc']}`; checkpoint `{d['checkpoint_at_utc']}`. **Khuyến nghị: ngừng mở thêm shard/resume ở checkpoint an toàn; ưu tiên sửa TE-02.**", "",
           "Không cần đợi toàn bộ FUP-02 mới làm TE-02. Chỉ việc sửa cùng source hoặc tiếp nhận kết quả FUP cuối cần phối hợp bàn giao. "
           "TE-02 có thể dùng bản sao vật lý riêng trong lab, pin source/data/package, evidence/cache riêng và cùng registration. "
           "Đây là sửa điều kiện chờ quá rộng trong khuyến nghị trước; chưa thực hiện dừng process.", "",
           "| Số đo | Giá trị |", "|---|---:|",
           f"| Bắt đầu FUP | {d['first_run_at_utc']} |",
           f"| Thời gian trôi qua tới capture (phút) | {d['elapsed_since_start_seconds']/60:.2f} |",
           f"| Tổng wall của các invocation đã kết thúc (phút) | {d['closed_invocation_wall_seconds']/60:.2f} |",
           f"| Số invocation đã lưu | {len(d['invocations'])} |",
           f"| Cell RUN_VALID / FAILED / BUDGET_STOPPED / NOT_RUN_BUDGET | {d['coverage'].get('RUN_VALID',0)} / {d['coverage'].get('FAILED',0)} / {d['coverage'].get('BUDGET_STOPPED',0)} / {d['coverage'].get('NOT_RUN_BUDGET',0)} |",
           f"| Cutoff SCORED / ERROR / NOT_RUN | {d['cutoff_counts'].get('SCORED',0)} / {d['cutoff_counts'].get('ERROR',0)} / {d['cutoff_counts'].get('NOT_RUN',0)} |",
           f"| Dòng trial ledger đã lưu | {d['trial_ledger_rows']} |",
           f"| Total wall cap đăng ký (giờ) | {d['registered_total_wall_seconds']/3600:g} |",
           f"| Lượt đọc audit (giây) / engine runs mới | {d['audit_wall_seconds']:.3f} / {d['engine_runs']} |", "",
           "Không cộng wall invocation với shard rollup vì chúng chồng nhau. Invocation đang chạy chỉ được append trong finally, "
           "nên tổng đã đóng thiếu phần đang chạy. Không có số CPU/RAM host đáng tin cậy từ PID namespace hiện tại.", "",
           "## Vì sao chưa đáng mở rộng", "",
           "1. `run_one_fold` gọi provider; provider chạy `_event_account_payload` trên frame toàn kỳ sau selection; `finalize_arm` lại triển khai account. "
           "Đây là call-path source đã xác minh, chưa đo được tỷ lệ thời gian tiết kiệm; không hứa speedup. Failure ở deployment có thể làm mất kết quả selection trước đó trong returned payload.",
           "2. `total_wall_budget_seconds` được đăng ký 12 giờ nhưng main không đọc cap này để trừ phần đã tiêu thụ trước resume; deadline chỉ theo invocation. "
           "Chưa kết luận đã vượt 12 giờ; kết luận là thiếu guard ngân sách tổng trong đường chạy đang dùng.",
           "3. Scorer cắt frame từ train_index[0], bỏ warmup prefix; fill count cả train window được dùng cho subwindow metrics. "
           "Các source này vẫn khớp snapshot TE-01 đã audit; RUN_VALID cũ không chứng minh scorer đã đạt contract mới.",
           "4. HMA dùng 1h, HASH dùng 15min; account nhận chính frame đó. Chưa đạt execution 1m của registration mới. "
           "CAL và REGIME bắt đầu bằng cutoff khác nhau; cần common initial/ready contract trước timing comparison.",
           "5. FUP giữ model tape cũ để so với RF trước; không fit/đánh giá model mỗi fold theo protocol mới. "
           "FUP tự ghi không làm bootstrap, decay panel hoặc matched-budget control. Chạy đủ cells cũng không tự chứng minh time edge.", "",
           "6. Cutoff ERROR được giữ terminal trên resume mặc định; COMPLETE_ALL_CELLS chỉ xuất hiện khi mọi cell có hai arm hoàn tất. "
           "Vì đã có lỗi giá limit không dương, chờ nhãn COMPLETE mà chưa sửa nguyên nhân không có cơ sở. "
           "Có thể bàn giao PARTIAL trung thực ngay khi checkpoint/ledger được đóng, không cần ép mọi cell thành công.", "",
           "Các số account/selection hiện có vẫn hữu ích để debug và profile trong đúng scope. Không kết luận mọi fill đều sai, "
           "không xóa raw curves; các lỗi metrics hậu kỳ không được gán nhầm thành phép tính mà FUP chưa chạy.", "",
           "## Việc nên làm tiếp", "",
           "- OpenCode dừng mở job/shard mới ở checkpoint an toàn; ghi rõ cutoff đang dở, attempts, trial ledger và nguồn. Không hard-kill làm mất evidence.",
           "- Tiến hành TE02.1/TE02.2 trong bản sao lab riêng; sửa scorer/clock và tách selection khỏi account deployment (TE02.3), tổng budget/resume (TE02.7).",
           "- Chạy pilot nhỏ sau khi OS isolation và budget đạt; đo cold/warm cost rồi mới quyết định phạm vi rerun. Full model controls thuộc TE-03; inference/decay thuộc TE-04.", "",
           "[Review JSON](review.json), [manifest](manifest.json), [captured FUP](captured/paired_discovery_fullwindow.json), "
           "[central plan](../../../implementation%20and%20test_edge_plan.md#te-02).", "",
           "**Thuật ngữ:** cell = alpha × symbol; arm = CAL hoặc REGIME; shard = một cell × arm; cutoff = mốc chọn tham số; "
           "invocation = một lần gọi runner; resume = tiếp tục từ checkpoint đã lưu; wall = thời gian trôi qua của lượt chạy, khác CPU; "
           "ledger = sổ ghi trials/attempts; warmup = lịch sử khởi tạo indicator; scorer = bộ tính điểm candidate; "
           "bootstrap = lấy mẫu lại để ước lượng bất định; decay = suy giảm chất lượng theo tuổi tham số; "
           "validity = phép thử đúng trong phạm vi tuyên bố; profile = đo nơi tiêu tốn tài nguyên; namespace = phạm vi process/môi trường được nhìn thấy.", ""]
    write(out/"report.md","\n".join(lines).encode())
    write(out/"report.json",(json.dumps({"study_id":"time_edge_validation_v4","lab_run_id":out.name,
          "review_sha256":sha(p.read_bytes()),"report_sha256":sha((out/"report.md").read_bytes()),
          "recommendation":d["recommendation"],"engine_runs":0},indent=2)+"\n").encode())


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("operation",choices=("capture","report"));p.add_argument("--run-id",required=True)
    a=p.parse_args();out=(ROOT/"evidence/reviews"/a.run_id).resolve()
    if out.parent!=(ROOT/"evidence/reviews").resolve():raise SystemExit("review must stay inside lab")
    (capture if a.operation=="capture" else report)(out)
