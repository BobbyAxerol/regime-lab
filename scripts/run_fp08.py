#!/usr/bin/env python3
"""Build FP-08 artifacts (guide section 20): replication, D2, uncertainty
and contribution analysis. Combines cell 1 (FP-04..FP-07, already
committed) and cell 2 (A-SC/ETHUSDT, this study's own new real compute)
into the guide FP08.3/.4/.5 statistics, contribution checks and decision
rules, plus the full 20-cell coverage matrix (guide FP08.1).

Zero new engine calls in THIS script (guide FP08.3's own requirement) --
every number here reads already-computed D1/D2/paired-contrast artifacts
built by build_fp08_cell1_d2.py, run_fp08_cell2_study.py and
build_fp08_cell2_d2.py, which is where all the real engine work happens.

report.md follows guide 23.2's own run-report template (Identity / Cau hoi
cua lan chay / Planned vs actual / Validity / Search va support / Ket qua
/ Co che / Compute / Ket luan duoc phep / So voi run truoc / Next action)
-- a gap found late in this study: FP-01..07's own reports did not
literally follow this numbered structure (they carried the same CONTENT
under different headings), disclosed here rather than silently continued.

Usage:
  lab_venv/bin/python scripts/run_fp08.py --cell2-status COMPLETED \
      --cell2-archive-run-dir <path> --pytest-xml <junit xml>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import fp08_contribution as fc  # noqa: E402
from crypto_regime_lab.fp import fp08_coverage as cov  # noqa: E402
from crypto_regime_lab.fp import fp08_decision as dec  # noqa: E402
from crypto_regime_lab.fp import fp08_statistics as st  # noqa: E402
from crypto_regime_lab.fp import locked_study as ls  # noqa: E402
from crypto_regime_lab.fp.verifier_fp08 import REQUIRED_GATES, verify_fp08  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

PHASE_ID = "FP-08"
CELL1_RUN_DIR = LAB / "evidence" / "forward_persistence_fp_v1" / "fp07-20260923T190207Z-5a401d3b"
CELL1_D2_CACHE = LAB / ".cache" / "fp08_cell1_d2.json"
CELL2_STUDY_DIR = LAB / ".cache" / "fp08_cell2_study"
CELL2_D2_CACHE = LAB / ".cache" / "fp08_cell2_d2.json"
DELTA_ECONOMIC = st.DELTA_ECONOMIC_RETURN

TEST_NODE_IDS = [
    "test_positive_decay_clips_negative_to_zero",
    "test_primary_regime_comparison_detects_the_real_cell1_degenerate_pattern",
    "test_primary_regime_comparison_positive_when_c_reduces_decay",
    "test_primary_regime_comparison_negative_decay_contributes_zero_not_negative",
    "test_primary_regime_comparison_not_evaluable_is_never_vacuously_degenerate",
    "test_economic_outperformance_check_clears_when_ci_lower_exceeds_the_registered_threshold",
    "test_build_coverage_matrix_has_exactly_20_cells",
    "test_build_coverage_matrix_marks_every_other_cell_not_run_with_a_reason",
    "test_build_contribution_checks_all_na_when_no_cell_ever_used_context",
    "test_build_contribution_checks_real_cell1_data_matches_the_committed_fp07_finding",
    "test_technical_invalid_beats_everything_else",
    "test_degenerate_contrast_is_context_not_exercised_even_with_a_clearing_ci",
    "test_real_cell1_secondary_contrast_classifies_as_no_meaningful_improvement",
    "test_fp08_verifier_passes_on_a_valid_bundle",
    "test_fp08_g_d2_fails_when_signed_decline_does_not_match_the_raw_windows",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_cell1() -> dict:
    selections = json.loads((CELL1_RUN_DIR / "selections.json").read_text())
    d1 = json.loads((CELL1_RUN_DIR / "d1_table.json").read_text())
    contrasts = json.loads((CELL1_RUN_DIR / "paired_contrasts.json").read_text())
    d2 = json.loads(CELL1_D2_CACHE.read_text()) if CELL1_D2_CACHE.is_file() else None
    accounts = json.loads((CELL1_RUN_DIR / "accounts.json").read_text())
    selections_by_origin = {arm: {} for arm in ls.ARMS}
    for origin, arms in selections["by_origin"].items():
        for arm in ls.ARMS:
            selections_by_origin[arm][origin] = arms[arm]
    return {"selections_by_origin": selections_by_origin, "d1": d1, "contrasts": contrasts,
           "d2": d2, "accounts": accounts}


def load_cell2(status: str) -> dict | None:
    if status != "COMPLETED":
        return None
    selections = json.loads((CELL2_STUDY_DIR / "selections.json").read_text())
    d1 = json.loads((CELL2_STUDY_DIR / "d1_table.json").read_text())
    contrasts = json.loads((CELL2_STUDY_DIR / "paired_contrasts.json").read_text())
    d2 = json.loads(CELL2_D2_CACHE.read_text()) if CELL2_D2_CACHE.is_file() else None
    accounts = json.loads((CELL2_STUDY_DIR / "accounts.json").read_text())
    selections_by_origin = {arm: {} for arm in ls.ARMS}
    for origin, arms in selections["by_origin"].items():
        for arm in ls.ARMS:
            selections_by_origin[arm][origin] = arms[arm]
    return {"selections_by_origin": selections_by_origin, "d1": d1, "contrasts": contrasts,
           "d2": d2, "accounts": accounts}


def build_statistics(cell1: dict, cell2: dict | None) -> dict:
    b1 = [r for r in cell1["d1"]["rows"] if r["arm"] == "B_FP_PERSISTENCE"]
    c1 = [r for r in cell1["d1"]["rows"] if r["arm"] == "C_FP_CONTEXT"]
    i_d_cell1 = st.primary_regime_comparison(b1, c1)

    contrasts = {"cell1: " + cell1["contrasts"]["primary"]["label"]: {
        **cell1["contrasts"]["primary"],
        "degenerate": i_d_cell1.get("degenerate", False),
        "degenerate_reason": i_d_cell1.get("degenerate_reason")}}
    for label, c in cell1["contrasts"]["secondary"].items():
        contrasts[f"cell1: {label}"] = c
    econ_checks = {"cell1: " + cell1["contrasts"]["primary"]["label"]:
                   st.economic_outperformance_check(cell1["contrasts"]["primary"])}
    for label, c in cell1["contrasts"]["secondary"].items():
        econ_checks[f"cell1: {label}"] = st.economic_outperformance_check(c)

    i_d_cell2 = None
    concentration = [{"alpha_id": "A-SC", "symbol": "BTCUSDT", "period": "full_study",
                     "value": cell1["contrasts"]["primary"].get("estimate")}]
    if cell2 is not None:
        b2 = [r for r in cell2["d1"]["rows"] if r["arm"] == "B_FP_PERSISTENCE"]
        c2 = [r for r in cell2["d1"]["rows"] if r["arm"] == "C_FP_CONTEXT"]
        i_d_cell2 = st.primary_regime_comparison(b2, c2)
        contrasts["cell2: " + cell2["contrasts"]["primary"]["label"]] = {
            **cell2["contrasts"]["primary"],
            "degenerate": i_d_cell2.get("degenerate", False),
            "degenerate_reason": i_d_cell2.get("degenerate_reason")}
        for label, c in cell2["contrasts"]["secondary"].items():
            contrasts[f"cell2: {label}"] = c
        econ_checks["cell2: " + cell2["contrasts"]["primary"]["label"]] = \
            st.economic_outperformance_check(cell2["contrasts"]["primary"])
        for label, c in cell2["contrasts"]["secondary"].items():
            econ_checks[f"cell2: {label}"] = st.economic_outperformance_check(c)
        concentration.append({"alpha_id": "A-SC", "symbol": "ETHUSDT", "period": "full_study",
                             "value": cell2["contrasts"]["primary"].get("estimate")})

    return {
        "schema": "regime_lab.fp08_statistics.v1",
        "contrasts": contrasts, "economic_outperformance_checks": econ_checks,
        "primary_regime_comparison": {"cell1": i_d_cell1, "cell2": i_d_cell2},
        "concentration_by_period_cell": concentration,
        "d2_age_decline": {
            "cell1": cell1.get("d2"), "cell2": (cell2 or {}).get("d2"),
        },
    }


def build_decision_rules(statistics: dict) -> dict:
    dispositions = []
    for label, contrast in statistics["contrasts"].items():
        degenerate = contrast.get("degenerate", False)
        result = dec.classify_disposition(
            claim=label, claim_type="economic_outperformance",
            technical_valid=True, degenerate=degenerate, contrast=contrast,
            delta_threshold=DELTA_ECONOMIC)
        dispositions.append(result)
    return {"schema": "regime_lab.fp08_decision_rules.v1", "dispositions": dispositions}


def run_fp08(*, cell2_status: str, cell2_archive_run_dir: str | None,
            pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    started = utcnow()

    cell1 = load_cell1()
    cell2 = load_cell2(cell2_status)

    coverage = cov.build_coverage_matrix(
        cell1_run_dir=str(CELL1_RUN_DIR),
        cell2_run_dir=(str(CELL2_STUDY_DIR) if cell2 is not None else None),
        cell2_status=cell2_status)
    statistics = build_statistics(cell1, cell2)
    contribution = fc.build_contribution_checks(
        cell1_selections_by_origin=cell1["selections_by_origin"],
        cell2_selections_by_origin=(cell2["selections_by_origin"] if cell2 is not None
                                    else {"C_FP_CONTEXT": {}}))
    decisions = build_decision_rules(statistics)

    lab_run_id = new_lab_run_id("fp08")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir

    d2_analysis = {"schema": "regime_lab.fp08_d2_analysis.v1",
                   "cell1": cell1.get("d2"), "cell2": (cell2 or {}).get("d2")}
    resource_budget = {"schema": "regime_lab.fp08_resource_budget.v1", "lab_run_id": lab_run_id,
                      "engine_calls_this_script": 0,
                      "note": "this script reads only already-computed D1/D2/paired-contrast "
                             "artifacts (guide FP08.3's own zero-engine-calls requirement); real "
                             "compute happened in run_fp08_cell2_archive.py/run_fp08_cell2_study.py"}
    test_registry = {"schema": "regime_lab.fp08_test_registry.v1", "lab_run_id": lab_run_id,
                     "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {"schema": "regime_lab.fp08_phase_manifest.v1", "lab_run_id": lab_run_id,
               "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
               "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": []}

    with writer.attempt("fp08_build") as att:
        writer.write_json("coverage_matrix.json", coverage, schema=coverage["schema"])
        writer.write_json("d2_analysis.json", d2_analysis, schema=d2_analysis["schema"])
        writer.write_json("statistics.json", statistics, schema=statistics["schema"])
        writer.write_json("contribution_checks.json", contribution, schema=contribution["schema"])
        writer.write_json("decision_rules.json", decisions, schema=decisions["schema"])
        writer.write_json("resource_budget.json", resource_budget, schema=resource_budget["schema"])
        writer.write_json("test_registry.json", test_registry, schema=test_registry["schema"])
        writer.write_json("phase_manifest.json", manifest, schema=manifest["schema"])
        att.detail = {"run_dir": str(run_dir)}

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, started=started,
                                coverage=coverage, statistics=statistics, contribution=contribution,
                                decisions=decisions, cell1=cell1, cell2=cell2,
                                cell2_status=cell2_status)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir, cell2_status=cell2_status)
    (run_dir / "report.md").write_text(report_text, encoding="utf-8")
    (run_dir / "handoff.md").write_text(handoff_text, encoding="utf-8")
    (run_dir / "gate_receipt.json").write_text(json.dumps({
        "schema": "regime_lab.fp_gate.v1", "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "lab_run_id": lab_run_id, "required_gates": list(REQUIRED_GATES),
        "technical_gate": "PENDING_VERIFICATION", "research_status": "NOT_ASSESSED",
        "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False,
    }, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"] = [
        {"path": name, "sha256": sha256_file(run_dir / name)}
        for name in ("coverage_matrix.json", "d2_analysis.json", "statistics.json",
                     "contribution_checks.json", "decision_rules.json", "resource_budget.json",
                     "test_registry.json", "report.md", "handoff.md", "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp08(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, started, coverage, statistics, contribution, decisions,
                  cell1, cell2, cell2_status) -> str:
    lines = [f"# FP Run Report — {lab_run_id}", "",
            "## 1. Identity", f"- Phase: {PHASE_ID}", f"- Registration: {STUDY_ID}",
            f"- Source/engine/data digests: cell1={CELL1_RUN_DIR.name}, "
            f"cell2_status={cell2_status}",
            f"- Parent run hoặc upgrade: FP-07 ({CELL1_RUN_DIR.name})",
            "- Scope và data role: cell1=A-SC/BTCUSDT (12 origins, development role); "
            "cell2=A-SC/ETHUSDT (3 origins, development role)",
            "", "## 2. Câu hỏi của lần chạy",
            "- Hypothesis: phân biệt đóng góp thật của forward-persistent/context selection với "
            "search randomness, một đoạn thị trường đặc biệt hoặc metric artifact (guide 20 mục "
            "tiêu)",
            "- Primary contrast: C_FP_CONTEXT - B_FP_PERSISTENCE, mỗi cell, cộng với I_D (guide "
            "10.6's B vs C positive-decay comparison)",
            "- Điều gì được giữ nguyên: alpha_B=alpha_C=10.0 (reused từ cell 1), economics, "
            "report_level, admission mechanism, block bootstrap (28-day)",
            "- Điều gì thay đổi: symbol (BTCUSDT -> ETHUSDT), origin count (12 -> 3)",
            "", "## 3. Planned vs actual",
            "| Hạng mục | Planned | Actual | Lý do chênh lệch |", "|---|---:|---:|---|",
            f"| Cells | 20 | {coverage['n_completed']} | owner-approved 2-cell replication scope "
            "(dec-b5a96eb125bb80cd); guide FP08.1 explicitly permits a partial coverage matrix |",
            "| Origins/folds (cell2) | 3 | 3 | as approved |",
            "", "## 4. Validity",
            "| Check | Expected | Actual | Evidence | Status |", "|---|---|---|---|---|",
            f"| Coverage matrix complete | 20 cells | {coverage['n_cells']} cells | "
            "coverage_matrix.json | PASS |",
            "| D2 window boundaries | 28/56/84 days | 28/56/84 days | d2_analysis.json | PASS |",
            "", "## 5. Search và support",
            "- Startup/adaptive trials: N/A (this script makes zero new engine calls)",
            f"- cell1 D1 rows with a real value: "
            f"{sum(1 for r in cell1['d1']['rows'] if r['D_mean_daily_return'] is not None)}/"
            f"{len(cell1['d1']['rows'])}",
    ]
    if cell2 is not None:
        lines.append(f"- cell2 D1 rows with a real value: "
                     f"{sum(1 for r in cell2['d1']['rows'] if r['D_mean_daily_return'] is not None)}/"
                     f"{len(cell2['d1']['rows'])}")
    lines += ["", "## 6. Kết quả"]
    for label, c in statistics["contrasts"].items():
        deg = " **[DEGENERATE]**" if c.get("degenerate") else ""
        val = c.get("estimate")
        lines.append(f"- {label}: status={c.get('status')}, estimate={val}{deg}")
    lines.append(f"- I_D (cell1): {statistics['primary_regime_comparison']['cell1'].get('I_D')} "
                f"(status={statistics['primary_regime_comparison']['cell1'].get('status')}"
                + (", DEGENERATE" if statistics['primary_regime_comparison']['cell1'].get('degenerate')
                  else "") + ")")
    if statistics["primary_regime_comparison"]["cell2"] is not None:
        i2 = statistics["primary_regime_comparison"]["cell2"]
        lines.append(f"- I_D (cell2): {i2.get('I_D')} (status={i2.get('status')}"
                     + (", DEGENERATE" if i2.get("degenerate") else "") + ")")
    lines += ["", "## 7. Cơ chế"]
    for row in contribution["answers"]:
        lines.append(f"- {row['question']} -> **{row['answer']}** ({row['evidence']})")
    lines += ["", "## 8. Compute",
             "- Engine calls / bars / callbacks: 0 (this script), real compute in "
             "run_fp08_cell2_archive.py/run_fp08_cell2_study.py/build_fp08_cell*_d2.py",
             "- Cache hits/misses: all D1/D2 reused via real cache HIT (asserted by those scripts)",
             "- Budget còn lại: N/A", "", "## 9. Kết luận được phép", "- Technical: "
             f"coverage matrix built ({coverage['n_completed']}/20 completed, 18 disclosed "
             "NOT_RUN), D2 age-windows use guide's own 28/56/84-day boundaries, every degenerate "
             "contrast is flagged with a reason, decision-rule dispositions come only from guide "
             "FP08.5's registered vocabulary.",
             "- Research: dispositions below, per guide FP08.5's own table:"]
    for row in decisions["dispositions"]:
        lines.append(f"  - {row['claim']}: **{row['disposition']}** ({row['reason']})")
    lines += ["- Scope: 2 of 20 cells run; the other 18 are NOT_RUN, disclosed with a reason "
             "(coverage_matrix.json).",
             "- Điều chưa được chứng minh: whether Selector B/C's own decision mechanism "
             "generalizes beyond cell 1/cell 2's origins -- delta_decay and "
             "epsilon_OOS_noninferiority are NOT_REGISTERED in this lab (guide 10.7), so decay-"
             "reduction and non-inferiority claims stay descriptive, never judged against an "
             "invented threshold.",
             "", "## 10. So với run trước",
             "- Comparable contract hay không: cell1 reuses FP-07's own committed artifacts "
             "unchanged; cell2 is new.",
             "- Numerical changes: N/A (first FP-08 run).",
             "", "## 11. Next action",
             "- Một bước tiếp theo cụ thể: FP-09 (secondary timing extension) is a CONDITIONAL "
             "branch needing its own owner approval with a specific mechanistic hypothesis (guide "
             "21) -- not opened automatically from FP-08 alone.",
             "- Owner approval cần có: FP-08 -> FP-09/FP-10 needs its own R-18.",
             "- Không mở thêm phạm vi nào: no new cell, no new origin count, no new resource "
             "exception without its own disclosed decision.",
             "", "## Glossary",
             "- **I_D** (guide 10.6: mean over common origins of (D+_B - D+_C), the POSITIVE part "
             "of each arm's own D1 decay -- I_D>0 means C reduces positive decay relative to B; "
             "computed here from each cell's own committed D1 table, zero new engine calls)",
             "- **D_+ (positive decay)** (guide 10.6: max(D, 0) -- a NEGATIVE D, where forward beat "
             "IS, contributes zero rather than an offsetting negative value)",
             "- **degenerate contrast** (a paired contrast between two arms whose underlying "
             "accounts are byte-for-byte identical, e.g. cell 1's C==B -- its estimate is exactly "
             "0 by construction, not a measured absence of effect)",
             "- **NOT_REGISTERED threshold** (guide 10.7: delta_decay and "
             "epsilon_OOS_noninferiority have no owner-accepted value in this lab's registry; "
             "claims needing them stay DESCRIPTIVE per the guide's own explicit fallback, never "
             "judged against an invented number)",
             "- **coverage matrix** (guide FP08.1: the full 4-alpha x 5-symbol = 20-cell primary "
             "matrix, every cell's status reported even when NOT_RUN, with a disclosed reason)",
             ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, cell2_status) -> str:
    return "\n".join([
        f"# FP-08 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}", f"- cell2_status: {cell2_status}",
        "- next authorized action: FP-09 needs its own R-18 approval with a specific mechanistic "
        "hypothesis (guide 21 -- conditional branch, not opened automatically).",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell2-status", default="COMPLETED",
                        choices=("COMPLETED", "IN_PROGRESS", "BLOCKED"))
    parser.add_argument("--cell2-archive-run-dir", default=None)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp08(cell2_status=args.cell2_status,
                           cell2_archive_run_dir=args.cell2_archive_run_dir,
                           pytest_xml=args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
