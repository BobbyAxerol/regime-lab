"""Thin RA-04 verifier (RA-GUIDE-1.0 section 8, gates G04-VALID/READINESS/REG).

Same discipline as RA-01/02/03's verifiers: required artifacts exist and
hash-match, mandatory tests really ran (junit), no self-declared status
string, no BLOCKED artifact riding a PASS.
"""

from __future__ import annotations

from pathlib import Path

from .verifier import _gate, _load_json, _sha256

REQUIRED_GATES = ("G04-VALID", "G04-READINESS", "G04-REG")
REQUIRED_ARTIFACTS = (
    "selector_semantics.json",
    "f04_reproduction.json",
    "admission_policy.json",
    "search_registration.json",
    "compact_controls.json",
    "public_path.json",
    "readiness.json",
    "phase_gate.json",
    "phase_manifest.json",
    "report.md",
    "handoff.md",
)
CASE_IDS = tuple(f"Q{i:02d}" for i in range(1, 8))
GATE_SCHEMA = "regime_lab.ra_phase_gate.v1"
VERDICT_BEARING = ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")


def verify_ra04(run_dir: str | Path, *, pytest_xml, protected_status_after: str) -> dict:
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

    # -- G04-VALID: Q01-Q07 pass for the pilot cell/primary contract ----------
    reasons = list(test_reasons)
    if missing:
        reasons.append(f"missing artifacts: {missing}")
    matrix = docs.get("readiness.json") or {}
    q_matrix = (matrix.get("q_matrix") if isinstance(matrix, dict) else None) or {}
    for case_id in CASE_IDS:
        row = q_matrix.get(case_id)
        if row is None:
            reasons.append(f"{case_id} missing from the Q matrix")
            continue
        if not row.get("test_node_ids"):
            reasons.append(f"{case_id} has no registered test")
            continue
        for wanted in row["test_node_ids"]:
            if not any(wanted in got for got in node_ids):
                reasons.append(f"{case_id} test missing from the junit report: {wanted}")
                break
        if row.get("passed") is not True:
            reasons.append(f"{case_id} not recorded as passed")
    f04 = docs.get("f04_reproduction.json")
    if f04 is None:
        reasons.append("f04_reproduction.json missing or unreadable")
    elif not f04.get("mechanism_confirmed"):
        reasons.append("F-04 reproduction did not record a mechanism_confirmed verdict")
    controls = docs.get("compact_controls.json")
    if controls is None:
        reasons.append("compact_controls.json missing or unreadable")
    else:
        if len(controls.get("controls", [])) != 7:
            reasons.append(f"expected 7 compact controls, found {len(controls.get('controls', []))}")
        if controls.get("all_pass") is not True:
            reasons.append("not every compact control passed")
    gates["G04-VALID"] = _gate(not reasons, reasons)
    if junit_info is not None:
        gates["G04-VALID"]["tests"] = junit_info

    # -- G04-READINESS: measured route budget, economics, history eligibility -
    reasons = []
    readiness = docs.get("readiness.json")
    if readiness is None:
        reasons.append("readiness.json missing or unreadable")
    else:
        for alpha in ALPHAS:
            row = (readiness.get("route_readiness") or {}).get(alpha)
            if row is None:
                reasons.append(f"{alpha} missing from route readiness")
                continue
            if row.get("status") not in ("OK", "FAILED"):
                reasons.append(f"{alpha} has no real route-readiness status")
        if not readiness.get("economics"):
            reasons.append("economics not recorded")
        if not readiness.get("history_eligibility_checked"):
            reasons.append("initial-history eligibility not confirmed")
    gates["G04-READINESS"] = _gate(not reasons, reasons)

    # -- G04-REG: selector/admission/search settings frozen, PENDING approval
    reasons = []
    search_reg = docs.get("search_registration.json")
    admission = docs.get("admission_policy.json")
    if search_reg is None:
        reasons.append("search_registration.json missing or unreadable")
    elif not (search_reg.get("budget") or {}).get("reused_not_refrozen"):
        reasons.append("search budget must state whether it reused or re-froze the trial count")
    if admission is None:
        reasons.append("admission_policy.json missing or unreadable")
    else:
        for alpha in ALPHAS:
            if alpha not in (admission.get("thresholds") or {}):
                reasons.append(f"{alpha} missing frozen admission thresholds")
    gate_doc = docs.get("phase_gate.json")
    if gate_doc is None:
        reasons.append("phase_gate.json missing or unreadable")
    else:
        if gate_doc.get("schema") != GATE_SCHEMA:
            reasons.append(f"phase gate schema must be {GATE_SCHEMA}")
        if gate_doc.get("phase_id") != "RA-04":
            reasons.append("phase gate receipt belongs to another phase")
        if gate_doc.get("owner_review", {}).get("status") != "PENDING":
            reasons.append("owner review must stay PENDING until a real decision")
        if gate_doc.get("can_start_next_phase") is not False:
            reasons.append("can_start_next_phase must be false until owner approval")
    if protected_status_after.strip():
        reasons.append("protected tree changed by the phase; delta: " + protected_status_after.strip()[:500])
    gates["G04-REG"] = _gate(not reasons, reasons)

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
    gates["G04-MANIFEST"] = _gate(not reasons, reasons)

    for name in REQUIRED_ARTIFACTS:
        doc = docs.get(name)
        if isinstance(doc, dict) and doc.get("status") == "BLOCKED":
            gates["G04-VALID"] = _gate(False, gates["G04-VALID"]["reasons"]
                                       + [f"{name} reports BLOCKED and cannot ride a PASS"])

    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES + ("G04-MANIFEST",))
    return {
        "schema": "crypto_regime_lab.ra04_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "overall": "PASS" if overall else "FAIL",
    }
