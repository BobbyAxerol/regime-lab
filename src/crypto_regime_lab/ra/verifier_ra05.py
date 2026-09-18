"""Thin RA-05 verifier (RA-GUIDE-1.0 section 9, gates G05-EXEC/TRACE/LEARN/SCOPE).

Same discipline as RA-01..04's verifiers: required artifacts exist and
hash-match, mandatory tests really ran (junit), no self-declared status
string, no BLOCKED artifact riding a PASS.
"""

from __future__ import annotations

from pathlib import Path

from .verifier import _gate, _load_json, _sha256

REQUIRED_GATES = ("G05-EXEC", "G05-TRACE", "G05-LEARN", "G05-SCOPE")
REQUIRED_ARTIFACTS = (
    "discovery_spec.json",
    "cal_matched_forecast.json",
    "scheduler_audit.json",
    "arms_result.json",
    "action_divergence.json",
    "descriptive_returns.json",
    "phase_gate.json",
    "phase_manifest.json",
    "report.md",
    "handoff.md",
)
CASE_IDS = tuple(f"D{i:02d}" for i in range(1, 8))
GATE_SCHEMA = "regime_lab.ra_phase_gate.v1"
VERDICT_BEARING = ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
ARMS = ("STATIC", "M4_CAL", "M4_CAL_MATCHED", "M4_REGIME")


def verify_ra05(run_dir: str | Path, *, pytest_xml, protected_status_after: str) -> dict:
    root = Path(run_dir)
    gates: dict[str, dict] = {}

    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    docs: dict[str, dict | None] = {}
    for name in REQUIRED_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            docs[name] = _load_json(root / name, [])

    node_ids: set[str] = set()
    junit_info = None
    test_reasons: list[str] = []
    if pytest_xml is None or not Path(pytest_xml).is_file():
        test_reasons.append("pytest report missing: no test evidence, cannot PASS")
    else:
        try:
            import xml.etree.ElementTree as ET

            suite = ET.parse(str(pytest_xml)).getroot()
            suites = suite.findall("testsuite") or [suite]
            tests = sum(int(s.get("tests", 0)) for s in suites)
            failures = sum(int(s.get("failures", 0)) for s in suites)
            errors = sum(int(s.get("errors", 0)) for s in suites)
            skipped = sum(int(s.get("skipped", 0)) for s in suites)
            node_ids = {f"{c.get('classname','')}::{c.get('name','')}"
                       for s in suites for c in s.findall("testcase")}
            junit_info = {"tests": tests, "failures": failures, "errors": errors, "skipped": skipped}
        except Exception as exc:
            test_reasons.append(f"pytest report unparseable: {exc}")
        if junit_info is not None:
            if junit_info["tests"] == 0:
                test_reasons.append("no-tests-collected cannot PASS")
            if junit_info["failures"] or junit_info["errors"]:
                test_reasons.append(f"test failures={junit_info['failures']} errors={junit_info['errors']} cannot PASS")
            if junit_info["skipped"]:
                test_reasons.append("skipped mandatory tests cannot PASS")

    # -- G05-EXEC: actual 4-arm run completed in declared scope, or BLOCKED ----
    reasons = list(test_reasons)
    if missing:
        reasons.append(f"missing artifacts: {missing}")
    arms_result = docs.get("arms_result.json") or {}
    arms = (arms_result.get("arms") if isinstance(arms_result, dict) else None) or {}
    for arm in ARMS:
        row = arms.get(arm)
        if row is None:
            reasons.append(f"{arm} missing from arms_result.json")
            continue
        if row.get("ok") is not True and not row.get("error"):
            reasons.append(f"{arm} is neither ok nor carries a recorded error (silently dropped?)")
    gates["G05-EXEC"] = _gate(not reasons, reasons)
    if junit_info is not None:
        gates["G05-EXEC"]["tests"] = junit_info

    # -- G05-TRACE: D01-D07 pass -------------------------------------------
    reasons = []
    if node_ids:
        for case_id in CASE_IDS:
            if not any(case_id.lower() in got.lower() or case_id in got for got in node_ids):
                reasons.append(f"{case_id} has no matching test in the junit report")
    else:
        reasons.append("no junit node IDs available to confirm D01-D07 ran")
    gates["G05-TRACE"] = _gate(not reasons, reasons)

    # -- G05-LEARN: report states a mechanism conclusion, not just returns -----
    reasons = []
    divergence = docs.get("action_divergence.json")
    if divergence is None:
        reasons.append("action_divergence.json missing or unreadable")
    elif not divergence.get("pairwise"):
        reasons.append("action_divergence.json has no pairwise comparisons")
    report_text = (root / "report.md").read_text() if (root / "report.md").is_file() else ""
    if "mechanism" not in report_text.lower():
        reasons.append("report.md does not state a mechanism-level conclusion")
    if "Sharpe" in report_text and "mechanism" not in report_text.lower():
        reasons.append("report.md looks like a bare Sharpe table without a mechanism reading")
    gates["G05-LEARN"] = _gate(not reasons, reasons)

    # -- G05-SCOPE: status/CI/scope sourced; owner review PENDING before RA-06 -
    reasons = []
    descriptive = docs.get("descriptive_returns.json")
    if descriptive is None:
        reasons.append("descriptive_returns.json missing or unreadable")
    elif not descriptive.get("note"):
        reasons.append("descriptive_returns.json does not state its scope limits")
    gate_doc = docs.get("phase_gate.json")
    if gate_doc is None:
        reasons.append("phase_gate.json missing or unreadable")
    else:
        if gate_doc.get("schema") != GATE_SCHEMA:
            reasons.append(f"phase gate schema must be {GATE_SCHEMA}")
        if gate_doc.get("phase_id") != "RA-05":
            reasons.append("phase gate receipt belongs to another phase")
        if gate_doc.get("research_status") not in ("DISCOVERY_ONLY", "NOT_ASSESSED"):
            reasons.append("research_status must stay within RA-05's own discovery scope "
                           "(DISCOVERY_ONLY), never a stronger claim")
        if gate_doc.get("owner_review", {}).get("status") != "PENDING":
            reasons.append("owner review must stay PENDING until a real decision")
        if gate_doc.get("can_start_next_phase") is not False:
            reasons.append("can_start_next_phase must be false until owner approval")
    if protected_status_after.strip():
        reasons.append("protected tree changed by the phase; delta: " + protected_status_after.strip()[:500])
    gates["G05-SCOPE"] = _gate(not reasons, reasons)

    # -- manifest hashes --------------------------------------------------------
    reasons = []
    manifest = docs.get("phase_manifest.json")
    if manifest is None:
        reasons.append("no manifest to check hashes against")
    else:
        for entry in manifest.get("artifacts", []):
            rel = entry.get("relpath", "")
            want = entry.get("sha256", "")
            target = root / rel
            if not target.is_file():
                reasons.append(f"manifest lists missing file: {rel}")
            elif want and _sha256(target) != want:
                reasons.append(f"hash mismatch (tampered or stale): {rel}")
        for name in REQUIRED_ARTIFACTS:
            if name in VERDICT_BEARING:
                continue
            if name.endswith(".json") and name != "phase_manifest.json" and not any(
                    e.get("relpath") == name for e in manifest.get("artifacts", [])):
                reasons.append(f"required artifact not indexed in manifest: {name}")
    gates["G05-MANIFEST"] = _gate(not reasons, reasons)

    for name in REQUIRED_ARTIFACTS:
        doc = docs.get(name)
        if isinstance(doc, dict) and doc.get("status") == "BLOCKED":
            gates["G05-EXEC"] = _gate(False, gates["G05-EXEC"]["reasons"]
                                      + [f"{name} reports BLOCKED and cannot ride a PASS"])

    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES + ("G05-MANIFEST",))
    return {
        "schema": "crypto_regime_lab.ra05_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "overall": "PASS" if overall else "FAIL",
    }
