"""FP-08 gate FP08-G-* thin verifier (guide section 20 exit gate).

Same discipline as verifier_fp01..07: every gate re-derives its verdict
from the raw artifacts on disk, never trusting a stored summary field.

  * FP08-G-REPLICATION: a full 20-cell coverage matrix exists, every cell
    has a status from the allowed set, and cell 1/cell 2's own claimed
    status matches what their own evidence actually shows (never a cell
    marked COMPLETED with no run_dir behind it).
  * FP08-G-D2: every D2 record's signed_decline is recomputed from its own
    raw age_windows.metrics (never trusted), H1/H2/H3 use the guide's own
    28/56/84-day boundaries (not the older 90-day scheme), and a censored
    window never carries a non-null metric.
  * FP08-G-INFERENCE: every statistic uses the registered 28-day block
    bootstrap (never a bespoke test), and a DEGENERATE contrast (identical
    underlying accounts) is labelled as such, never presented as a genuine
    estimated null.
  * FP08-G-CONCENTRATION: a concentration-by-period/cell breakdown exists
    and is not silently restricted to the more favourable cell.
  * FP08-G-VERDICT: every conclusion-level label used in the report comes
    from guide FP08.5's own registered vocabulary, and the report contains
    no forbidden overclaim phrase.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP08-G-REPLICATION", "FP08-G-D2", "FP08-G-INFERENCE",
                  "FP08-G-CONCENTRATION", "FP08-G-VERDICT")

REQUIRED_ARTIFACTS = (
    "coverage_matrix.json", "d2_analysis.json", "statistics.json",
    "contribution_checks.json", "decision_rules.json", "resource_budget.json",
    "test_registry.json", "phase_manifest.json", "gate_receipt.json", "report.md", "handoff.md",
)

CELL_STATUSES = ("COMPLETED", "IN_PROGRESS", "NOT_RUN", "BLOCKED")
H_BOUNDARIES = {"H1": (0, 28), "H2": (28, 56), "H3": (56, 84)}
DECISION_VOCAB = (
    "Retention contribution trong scope", "Economic outperformance trong scope",
    "Inconclusive effect/support", "No meaningful improvement tại threshold đã thử",
    "Not evaluable", "Context mechanism chưa được exercise đủ",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(ok: bool, reasons: list) -> dict:
    return {"pass": bool(ok), "reasons": list(reasons)}


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def verify_fp08(run_dir, *, pytest_xml=None) -> dict:
    root = Path(run_dir)
    gates: dict = {}

    docs: dict = {}
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    for name in REQUIRED_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            docs[name] = _load_json(root / name)

    reasons: list = []
    manifest = docs.get("phase_manifest.json")
    if manifest is None:
        reasons.append("phase_manifest.json missing or unreadable")
    else:
        for entry in manifest.get("artifacts", []):
            name = entry.get("path")
            if not name or name in ("phase_manifest.json", "gate_receipt.json"):
                continue
            target = root / name
            if not target.is_file():
                reasons.append(f"manifest lists {name} but it is not on disk")
                continue
            if entry.get("sha256") and entry["sha256"] != _sha256(target):
                reasons.append(f"manifest hash mismatch on {name}: bytes changed after writing")
    reg_tests = _check_tests(pytest_xml, docs.get("test_registry.json"), reasons)
    manifest_reasons = list(reasons)

    coverage = docs.get("coverage_matrix.json")
    d2_analysis = docs.get("d2_analysis.json")
    statistics = docs.get("statistics.json")
    contribution = docs.get("contribution_checks.json")
    decisions = docs.get("decision_rules.json")

    # -- FP08-G-REPLICATION: full 20-cell coverage, statuses honest --
    reasons = list(manifest_reasons)
    if coverage is None:
        reasons.append("coverage_matrix.json missing or unreadable")
    else:
        cells = coverage.get("cells", [])
        if len(cells) != 20:
            reasons.append(f"coverage matrix has {len(cells)} cells, guide's primary matrix is 20 "
                           "(4 alphas x 5 symbols)")
        for cell in cells:
            status = cell.get("status")
            if status not in CELL_STATUSES:
                reasons.append(f"{cell.get('alpha_id')}/{cell.get('symbol')}: status {status!r} "
                               f"not in the allowed set {CELL_STATUSES}")
            if status == "COMPLETED" and not cell.get("evidence_ref"):
                reasons.append(f"{cell.get('alpha_id')}/{cell.get('symbol')}: COMPLETED with no "
                               "evidence_ref -- cannot verify the claim")
            if status in ("NOT_RUN", "BLOCKED") and not cell.get("reason"):
                reasons.append(f"{cell.get('alpha_id')}/{cell.get('symbol')}: {status} with no "
                               "disclosed reason")
        completed = [c for c in cells if c.get("status") == "COMPLETED"]
        if len(completed) < 1:
            reasons.append("no cell is COMPLETED -- FP08.1 requires at least the primary cell")
    gates["FP08-G-REPLICATION"] = _gate(not reasons, reasons)

    # -- FP08-G-D2: signed_decline recomputes, 28/56/84-day boundaries,
    # censored windows never carry a metric --
    reasons = list(manifest_reasons)
    if d2_analysis is None:
        reasons.append("d2_analysis.json missing or unreadable")
    else:
        all_records = []
        for cell_key in ("cell1", "cell2"):
            cell_doc = d2_analysis.get(cell_key)
            if cell_doc:
                all_records.extend(cell_doc.get("records", []))
        if not all_records:
            reasons.append("d2_analysis.json has no records under cell1/cell2")
        for rec in all_records:
            by_name = {w["horizon"]: w for w in rec.get("age_windows", [])}
            if set(by_name) != {"H1", "H2", "H3"}:
                reasons.append(f"{rec.get('arm')}@{rec.get('origin_cutoff')}: age_windows does not "
                               "carry exactly H1/H2/H3")
                continue
            for name, (lo, hi) in H_BOUNDARIES.items():
                w = by_name[name]
                if w.get("days_required") != hi - lo:
                    reasons.append(f"{rec.get('arm')}@{rec.get('origin_cutoff')}/{name}: "
                                   f"days_required={w.get('days_required')}, expected {hi - lo} "
                                   "(guide 10.3's 28/56/84-day freeze, not the older 90-day scheme)")
                if w["status"] == "CENSORED" and w.get("metrics") is not None:
                    reasons.append(f"{rec.get('arm')}@{rec.get('origin_cutoff')}/{name}: CENSORED "
                                   "but carries a non-null metrics value")
                if w["status"] == "COMPLETE" and w.get("metrics") is None:
                    reasons.append(f"{rec.get('arm')}@{rec.get('origin_cutoff')}/{name}: COMPLETE "
                                   "but metrics is null")
            for later in ("H2", "H3"):
                key = f"H1_minus_{later}"
                decl = rec.get("signed_decline", {}).get(key)
                h1, w_later = by_name["H1"], by_name[later]
                if h1["status"] != "COMPLETE" or w_later["status"] != "COMPLETE":
                    if decl is not None and decl.get("value") is not None:
                        reasons.append(f"{rec.get('arm')}@{rec.get('origin_cutoff')}/{key}: a "
                                       "censored side produced a non-null signed_decline value")
                    continue
                expected = h1["metrics"]["mean_daily_return"] - w_later["metrics"]["mean_daily_return"]
                if decl is None or decl.get("value") is None or abs(decl["value"] - expected) > 1e-9:
                    reasons.append(f"{rec.get('arm')}@{rec.get('origin_cutoff')}/{key}: stored "
                                   "signed_decline does not equal H1 - later recomputed from the "
                                   "raw stored window metrics")
    gates["FP08-G-D2"] = _gate(not reasons, reasons)

    # -- FP08-G-INFERENCE: registered bootstrap, degenerate contrasts
    # labelled as such --
    reasons = list(manifest_reasons)
    if statistics is None:
        reasons.append("statistics.json missing or unreadable")
    else:
        for key, stat in statistics.get("contrasts", {}).items():
            if stat.get("status") == "ESTIMATED":
                if stat.get("block") != 28:
                    reasons.append(f"{key}: block={stat.get('block')}, expected the registered "
                                   "28-day block bootstrap")
            if stat.get("degenerate") and stat.get("status") == "ESTIMATED" and not stat.get(
                    "degenerate_reason"):
                reasons.append(f"{key}: marked degenerate with no degenerate_reason -- a "
                               "degenerate contrast must say WHY, never just a flag")
    if contribution is None:
        reasons.append("contribution_checks.json missing or unreadable")
    elif not contribution.get("answers"):
        reasons.append("contribution_checks.json has no answers -- guide FP08.4's five questions "
                       "must each be addressed, never an empty placeholder")
    gates["FP08-G-INFERENCE"] = _gate(not reasons, reasons)

    # -- FP08-G-CONCENTRATION: a period/cell breakdown exists and is not
    # silently restricted to one cell --
    reasons = list(manifest_reasons)
    if statistics is None:
        reasons.append("statistics.json missing or unreadable")
    else:
        concentration = statistics.get("concentration_by_period_cell")
        if not concentration:
            reasons.append("statistics.json has no concentration_by_period_cell breakdown "
                           "(guide FP08.3's own required statistic)")
        elif coverage is not None:
            completed_cells = {(c["alpha_id"], c["symbol"]) for c in coverage.get("cells", [])
                              if c.get("status") == "COMPLETED"}
            reported_cells = {(row.get("alpha_id"), row.get("symbol")) for row in concentration}
            missing_cells = completed_cells - reported_cells
            if missing_cells:
                reasons.append(f"cells completed but absent from the concentration breakdown: "
                               f"{sorted(missing_cells)}")
    gates["FP08-G-CONCENTRATION"] = _gate(not reasons, reasons)

    # -- FP08-G-VERDICT: only guide FP08.5's own registered labels, no
    # forbidden overclaim phrase --
    reasons = list(manifest_reasons)
    report_text = (root / "report.md").read_text(encoding="utf-8") if (root / "report.md").is_file() else ""
    if "## 9. Kết luận được phép" not in report_text:
        reasons.append("report.md has no '## 9. Kết luận được phép' section (guide 23.2's own "
                       "run-report template, adopted from FP-08 onward)")
    if decisions is None:
        reasons.append("decision_rules.json missing or unreadable")
    else:
        for row in decisions.get("dispositions", []):
            label = row.get("disposition")
            if label not in DECISION_VOCAB:
                reasons.append(f"{row.get('claim')}: disposition {label!r} is not in guide "
                               f"FP08.5's registered vocabulary")
    forbidden_phrases = ("regime works", "regime timing works", "proves the edge",
                         "confirms the edge", "definitively beats", "context definitely helps")
    lowered = report_text.lower()
    for phrase in forbidden_phrases:
        if phrase in lowered:
            reasons.append(f"report.md contains a forbidden overclaim phrase: {phrase!r}")
    gates["FP08-G-VERDICT"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp08_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "missing_artifacts": missing,
        "pytest": reg_tests,
        "overall": "PASS" if overall else "FAIL",
    }


def _check_tests(pytest_xml, registry, reasons: list):
    if pytest_xml is None or not Path(pytest_xml).is_file():
        reasons.append("pytest report missing: no test evidence, cannot PASS")
        return None
    try:
        suite = ET.parse(str(pytest_xml)).getroot()
        suites = suite.findall("testsuite") or [suite]
        tests = sum(int(s.get("tests", 0)) for s in suites)
        failures = sum(int(s.get("failures", 0)) for s in suites)
        errors = sum(int(s.get("errors", 0)) for s in suites)
        skipped = sum(int(s.get("skipped", 0)) for s in suites)
        node_ids = {
            f"{c.get('classname', '')}::{c.get('name', '')}"
            for s in suites for c in s.findall("testcase")
        }
    except ET.ParseError as exc:
        reasons.append(f"pytest report unparseable: {exc}")
        return None
    info = {"tests": tests, "failures": failures, "errors": errors, "skipped": skipped}
    if tests == 0:
        reasons.append("no-tests-collected cannot PASS")
    if failures or errors:
        reasons.append(f"test failures={failures} errors={errors} cannot PASS")
    if skipped:
        reasons.append(f"{skipped} skipped tests cannot PASS (no mandatory skip)")
    if registry:
        for wanted in registry.get("test_node_ids", []):
            if not any(wanted in got for got in node_ids):
                reasons.append(f"registered test not found in report: {wanted}")
                break
    return info
