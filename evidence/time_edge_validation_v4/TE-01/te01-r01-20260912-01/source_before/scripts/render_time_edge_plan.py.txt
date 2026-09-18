#!/usr/bin/env python3
"""Render measured review blocks and the two-guide index into the tracking plan.

Reads the saved review and its pinned plan inputs. Never imports the lab or runs
an experiment. Authored instructions outside the generated blocks are preserved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "implementation and test_edge_plan.md"
V2 = "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md"
V3 = "REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md"


def load(path):
    return json.loads(path.read_text())


def replace_block(text, name, body):
    start, end = f"<!-- BEGIN {name} -->", f"<!-- END {name} -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"expected exactly one {name} marker pair")
    before, rest = text.split(start)
    _, after = rest.split(end)
    return before + start + "\n\n" + body.rstrip() + "\n\n" + end + after


def summary(review):
    a, o, p = (load(review / name) for name in ("audit.json", "observations.json", "source_probes.json"))
    ref = review.relative_to(ROOT).as_posix()
    f = o["fup02"]
    r = f["review"]
    lines = [
        f"Bản chụp `{review.name}` bắt đầu **{a['capture_started_at_utc']}**, kết thúc **{a['completed_at_utc']}**.",
        f"FUP-02 tại checkpoint **{f['checkpoint']}**. Đây là ảnh chụp lịch sử; OpenCode tiếp tục chạy và có thể đã đi xa hơn.",
        "",
        "| Hạng mục rà soát | Đo được | Giới hạn diễn giải |",
        "|---|---:|---|",
        f"| Python trong src/scripts/tests | {a['source_python_files']} files; {a['source_lines']:,} dòng | Lập inventory AST toàn phạm vi; không đồng nghĩa mọi dòng được chứng minh đúng |",
        f"| Hàm test được lập chỉ mục | {a['test_functions_inventoried_not_run']} | Chưa chạy lại; khác số test cases có tham số hóa |",
        f"| JSON/JSONL/Markdown trong configs/evidence/reports/handoff | {a['evidence_text_files']} files | Kiểm parse, hash và chỉ mục; parse được không phải semantic pass |",
        f"| Lỗi parse source / JSON | {len(a['source_ast_errors'])} / {len(a['json_parse_errors'])} | Không thay thế kiểm chứng execution/statistics |",
        f"| Engine / optimizer / market statistical tests chạy trong review | {a['engine_runs']} / {a['optimizer_runs']} / {a['market_statistical_tests']} | Không can thiệp FUP-02 |",
        f"| Thời gian capture và probes | {a['elapsed_seconds']:.3f} giây | Không phải thời gian đọc sâu hoặc benchmark backtest |",
        "",
        f"**FUP-02:** {f['coverage']['RUN_VALID']}/20 cặp `RUN_VALID`; {r['cutoffs_scored']}/{r['cutoffs_planned']} cutoffs đã chấm; "
        f"{r['trials_total']} trials, {r['trials_finite']} hữu hạn, {r['trials_nonfinite']} không hữu hạn "
        f"({100*r['bad_trial_fraction']:.3f}%). `infeasible_trials={r['infeasible_trials']}` là số runner ghi, chưa chứng minh không có lỗi thực thi.",
        "",
        "| Cell đã bắt đầu | Calendar: trạng thái, đã chấm/kế hoạch | Regime: trạng thái, đã chấm/kế hoạch |",
        "|---|---|---|",
    ]
    for cell in f["progress"]:
        shards = cell["shards"]
        if not any(s["scored"] for s in shards.values()):
            continue
        left, right = shards["M4_CAL"], shards["M4_REGIME"]
        lines.append(f"| {cell['cell']} | {left['status']}, {left['scored']}/{left['planned']} | "
                     f"{right['status']}, {right['scored']}/{right['planned']} |")
    lines += ["", "Lỗi được giữ nguyên từ checkpoint:", ""]
    for failure in f["runtime_failures"]:
        lines.append(f"- `{failure['cell']} / {failure['arm']} / fold {failure['fold_id']}`: "
                     f"{failure['reason']}")
    m, d = o["regime"], o["decay"]
    lines += [
        "", "| Regime model / decay | Kết quả từ artifacts |",
        "|---|---|",
        f"| Tape chính | {m['symbol']}; {m['rows']} emissions; {m['active_registry_models']} model vintages |",
        f"| Thiết kế trong registry của tape chính | K={m['active_registry_design']['n_states']}, lambda={m['active_registry_design']['lambda_jump']}, memory={m['active_registry_design']['train_memory_days']} ngày |",
        f"| Thiết kế chọn riêng ở RF-04 | K={m['rf04_selected_design']['n_states']}, lambda={m['rf04_selected_design']['lambda_jump']}; deployment_action ghi RECORDED_DESIGN_SELECTION |",
        f"| Emissions có ready_at / state_common / economic_context | {m['field_counts']['ready_at']} / {m['field_counts']['state_common']} / {m['field_counts']['economic_context']} trên {m['rows']} |",
        f"| D1 / D2 / D3 | {d['denominators']['D1_rows']} / {d['denominators']['D2_rows']} / {d['denominators']['D3_rows']} rows; chỉ {d['denominators']['cells']} cells |",
        f"| D2 anchors / self-comparisons | {d['denominators']['anchors_replayed']} anchors; {d['D2_self_comparison_rows']} rows H1−H1 |",
        f"| D2 Profit Factor | {d['D2_PF_null_rows']}/{d['D2_PF_rows']} null; {d['D2_PF_rows_with_finite_underlying_PF']} rows có PF nền hữu hạn |",
        f"| D2 khác route với pilot | {d['D2_route_mismatch_rows']}/{d['denominators']['D2_rows']} rows |",
        "", "**Probes source nhỏ đã thực hiện**, không dùng QuantBT và không là kết quả thị trường:", "",
        f"- Model chỉ ready năm 2025 vẫn tạo trigger tại `{p['scheduler']['future_model_ready_triggered'][0]}` trong hàm controller được trích từ source.",
        f"- Tape cố định 365 observations với max-age 180 ngày tạo {len(p['scheduler']['constant_state_365_observations_max_age_180_triggers'])} triggers; chưa có mốc khởi tạo last_trigger.",
        f"- Hai cửa sổ 90 ngày trả {p['decay']['observed_H1_days']} và {p['decay']['observed_H2_days']} observations, dùng chung ngày biên {p['decay']['shared_boundary_day']}.",
        f"- Hàm daily metrics tạo PF={p['decay']['daily_profit_factor_value']:.6f}, nhưng lookup `profit_factor` của D2 trả null.",
        "- Chuỗi chỉ có ngày lỗ bị ghi `NO_TRADES`; dữ liệu lợi nhuận ngày không đủ để suy ra không có giao dịch.",
        "- RF-05 giữ lại ngày trước evaluation_start trong chuỗi chênh lệch lợi nhuận.",
        "", f"Hash tham chiếu ngược FUP-02: `{json.dumps(f['reference_hash_checks'])}`. "
        f"Chiều từ coverage/review tới checkpoint: `{json.dumps(f['forward_reference_hash_checks'])}`.",
        "",
        f"Nguồn máy đọc: [audit.json]({ref}/audit.json), [observations.json]({ref}/observations.json), "
        f"[source_probes.json]({ref}/source_probes.json), [capture_manifest.json]({ref}/capture_manifest.json).",
    ]
    return "\n".join(lines)


def owner_v3(number):
    if number in (23, 24, 59, 64, 70):
        return "TE-01", "TG-01"
    if number in (29, 30, 31, 41, 42, 43, 45, 46, 47, 50):
        return "TE-03", "TG-05"
    if number == 44:
        return "TE-03", "TG-06"
    if number == 37:
        return "TE-03", "TG-12"
    if number in (38, 39):
        return "TE-03 → TE-04", "TG-09"
    if 51 <= number <= 58:
        return "TE-04", "TG-08" if number in (55, 56, 57) else "TG-07"
    if number in (60, 61, 62, 65, 69):
        return "TE-05", "TG-11"
    if number in (33, 34, 35, 36, 63, 66, 67):
        return "TE-02", "TG-10"
    if number in (3, 4, 5, 21, 22, 32, 48, 49):
        return "TE-02", "TG-04"
    if number in (25, 26, 27, 28, 40):
        return "TE-02", "TG-03"
    return "TE-02", "TG-02"


def requirement_index(review):
    def registry(filename):
        path = review / "captured/configs" / filename
        if not path.exists():
            path = review / "plan_inputs/configs" / filename
        return load(path)["requirements"]
    old = registry("acceptance_test_coverage.json")
    new = registry("rf_acceptance_registry.json")
    if len(old) != 64 or len(new) != 70:
        raise ValueError("expected the registered 64 V2 and 70 V3 requirements")
    lines = ["Mỗi ID dưới đây là **nghĩa vụ**, chưa là test đã pass trong review. `V2:T01` và `V3:T01` khác nhau.",
             "Trạng thái COVERED cũ được giữ như khai báo lịch sử; nghiệm thu kế hoạch này cần evidence mới và test chạy đúng đường code.",
             "", "| ID gốc | Nội dung / tên trong registry | Phase chịu trách nhiệm | Test/index hiện có hoặc nhóm cần bổ sung |",
             "|---|---|---|---|"]
    phase_map = {"LAB-01": "TE-01", "LAB-02": "TE-02", "LAB-03": "TE-01", "LAB-04": "TE-02",
                 "LAB-05": "TE-03", "LAB-06": "TE-03", "LAB-07": "TE-02", "LAB-08": "TE-04",
                 "LAB-09": "TE-05", "LAB-10": "TE-05"}
    for r in old:
        phase = phase_map.get(r.get("owning_phase"), "TE-05")
        test = (r.get("tests") or [None])[0]
        evidence = (f"[{test}]({test.split('::')[0]})" if test else "Chưa có test pointer trong registry")
        title = r.get("title", r.get("requirement", ""))
        lines.append(f"| [V2:{r['id']}][g2-14] | "
                     f"{title.replace('|', '/')} | [{phase}](#{phase.lower()}) | {evidence}; khai báo cũ `{r.get('status')}` |")
    for r in new:
        number = int(r["id"][1:])
        phase, group = owner_v3(number)
        primary = phase.split(" → ")[0]
        lines.append(f"| [V3:{r['id']}][g3-11] | "
                     f"{r['situation'].replace('|', '/')} | [{phase}](#{primary.lower()}) | [{group}](#{group.lower()}); cần map tới runtime test + evidence |")
    return "\n".join(lines)


def guide_links(review):
    links = {}
    for prefix, filename in (("g2", V2), ("g3", V3)):
        links[prefix] = filename
        fenced = False
        slugs = set()
        for line in (review / "captured" / filename).read_text().splitlines():
            if line.startswith("# PHỤ LỤC"):
                break
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
            if fenced or not heading:
                continue
            title = heading[1]
            base = re.sub(r"[^\w\s-]", "", title.lower()).replace(" ", "-")
            slug, suffix = base, 0
            while slug in slugs:
                suffix += 1
                slug = f"{base}-{suffix}"
            slugs.add(slug)
            number = re.match(r"^(\d+(?:\.\d+)*)(?:\.)?\s", title)
            phase = re.match(r"^RF-(0[1-5])\s", title)
            key = (f"{prefix}-{number[1]}" if number else
                   f"{prefix}-rf{phase[1]}" if phase else None)
            if key and key not in links:
                links[key] = f"{filename}#{slug}"
    return "\n".join(f"[{key}]: {target}" for key, target in sorted(links.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True)
    args = parser.parse_args()
    review = (ROOT / args.review).resolve()
    if not review.is_relative_to(ROOT / "evidence/reviews"):
        raise SystemExit("review must be inside LAB_ROOT/evidence/reviews")
    original = PLAN.read_text()
    rendered = replace_block(original, "MEASURED_REVIEW", summary(review))
    rendered = replace_block(rendered, "GUIDE_REQUIREMENTS", requirement_index(review))
    rendered = replace_block(rendered, "GUIDE_LINKS", guide_links(review))
    used = set(re.findall(r"\[[^]\n]+\]\[(g[23][^]]*)\]", rendered))
    defined = set(re.findall(r"^\[(g[23][^]]*)\]:", rendered, re.MULTILINE))
    if used - defined:
        raise SystemExit(f"unresolved guide references: {sorted(used - defined)}")
    if re.search(r"\{\{[^}]+\}\}", rendered):
        raise SystemExit("unrendered template marker")
    PLAN.write_text(rendered)
    print(f"Rendered saved measurements and 134 guide requirements into {PLAN.name}")


if __name__ == "__main__":
    main()
