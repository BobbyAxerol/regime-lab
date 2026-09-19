"""Thin RA-06 verifier (RA-GUIDE-1.0 section 10, gates G06-PANEL/MODEL/SCOPE).

Same discipline as RA-01..05's verifiers: required artifacts exist and
hash-match, mandatory tests really ran (junit), no self-declared status
string, no BLOCKED artifact riding a PASS.
"""

from __future__ import annotations

from pathlib import Path

from .verifier import _gate, _load_json, _sha256

REQUIRED_GATES = ("G06-PANEL", "G06-MODEL", "G06-SCOPE")
REQUIRED_ARTIFACTS = (
    "panel_a.json",
    "origins.json",
    "panel_b.json",
    "model_ladder.json",
    "controller_examples.json",
    "lock_decision.json",
    "phase_gate.json",
    "phase_manifest.json",
    "report.md",
    "handoff.md",
)
CASE_IDS = tuple(f"P{i:02d}" for i in range(1, 9))
GATE_SCHEMA = "regime_lab.ra_phase_gate.v1"
VERDICT_BEARING = ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")


def verify_ra06(run_dir: str | Path, *, pytest_xml, protected_status_after: str) -> dict:
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

    # -- G06-PANEL: panel builder + P01-P08 pass; feasibility panel has
    # provenance OR BLOCKED_CAPABILITY -----------------------------------
    reasons = list(test_reasons)
    if missing:
        reasons.append(f"missing artifacts: {missing}")
    if node_ids:
        for case_id in CASE_IDS:
            if not any(case_id.lower() in got.lower() or case_id in got for got in node_ids):
                reasons.append(f"{case_id} has no matching test in the junit report")
    else:
        reasons.append("no junit node IDs available to confirm P01-P08 ran")
    panel_a = docs.get("panel_a.json")
    panel_b = docs.get("panel_b.json")
    if panel_a is None:
        reasons.append("panel_a.json missing or unreadable")
    elif not panel_a.get("rows"):
        reasons.append("panel_a.json has no rows")
    if panel_b is None:
        reasons.append("panel_b.json missing or unreadable")
    else:
        if panel_b.get("capability_status") == "BLOCKED_CAPABILITY":
            if not panel_b.get("blocked_reason"):
                reasons.append("panel_b.json reports BLOCKED_CAPABILITY with no reason")
        elif not panel_b.get("rows"):
            reasons.append("panel_b.json has no rows and does not report BLOCKED_CAPABILITY")
    gates["G06-PANEL"] = _gate(not reasons, reasons)
    if junit_info is not None:
        gates["G06-PANEL"]["tests"] = junit_info

    # -- G06-MODEL: training attempt runs if support allows; insufficient
    # support has a measured, preregistered, non-financial disposition -----
    reasons = []
    model_ladder = docs.get("model_ladder.json")
    if model_ladder is None:
        reasons.append("model_ladder.json missing or unreadable")
    else:
        status = model_ladder.get("status")
        if status not in ("INSUFFICIENT_SUPPORT", "FIT_ATTEMPTED"):
            reasons.append(f"model_ladder.json has an unrecognised status: {status!r}")
        if status == "INSUFFICIENT_SUPPORT" and not model_ladder.get("disposition"):
            reasons.append("INSUFFICIENT_SUPPORT status carries no measured disposition")
        if status == "FIT_ATTEMPTED":
            for side in ("age_only", "age_context"):
                if not model_ladder.get(side):
                    reasons.append(f"FIT_ATTEMPTED status but {side} is missing")
                elif model_ladder[side].get("calibrated_probability_language_used"):
                    reasons.append(f"{side} claims calibrated-probability language, which guide 10.5 forbids")
    gates["G06-MODEL"] = _gate(not reasons, reasons)

    # -- G06-SCOPE: at most ONE context-policy revision locked, or
    # KEEP_BASELINE with a reason ------------------------------------------
    reasons = []
    lock_decision = docs.get("lock_decision.json")
    if lock_decision is None:
        reasons.append("lock_decision.json missing or unreadable")
    else:
        decision = lock_decision.get("decision")
        if decision not in ("KEEP_BASELINE", "LOCK_AGE_CONTEXT"):
            reasons.append(f"lock_decision.json has an unrecognised decision: {decision!r}")
        if not lock_decision.get("reason"):
            reasons.append("lock_decision.json carries no reason")
        if decision == "LOCK_AGE_CONTEXT" and not lock_decision.get("carries_to_ra07"):
            reasons.append("LOCK_AGE_CONTEXT decision carries nothing forward to RA-07")
        if decision == "KEEP_BASELINE" and lock_decision.get("carries_to_ra07") is not None:
            reasons.append("KEEP_BASELINE must not also carry a revision forward")
    gate_doc = docs.get("phase_gate.json")
    if gate_doc is None:
        reasons.append("phase_gate.json missing or unreadable")
    else:
        if gate_doc.get("schema") != GATE_SCHEMA:
            reasons.append(f"phase gate schema must be {GATE_SCHEMA}")
        if gate_doc.get("phase_id") != "RA-06":
            reasons.append("phase gate receipt belongs to another phase")
        if gate_doc.get("owner_review", {}).get("status") != "PENDING":
            reasons.append("owner review must stay PENDING until a real decision")
        if gate_doc.get("can_start_next_phase") is not False:
            reasons.append("can_start_next_phase must be false until owner approval")
    if protected_status_after.strip():
        reasons.append("protected tree changed by the phase; delta: " + protected_status_after.strip()[:500])
    gates["G06-SCOPE"] = _gate(not reasons, reasons)

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
    gates["G06-MANIFEST"] = _gate(not reasons, reasons)

    for name in REQUIRED_ARTIFACTS:
        doc = docs.get(name)
        if isinstance(doc, dict) and doc.get("status") == "BLOCKED":
            gates["G06-PANEL"] = _gate(False, gates["G06-PANEL"]["reasons"]
                                       + [f"{name} reports BLOCKED and cannot ride a PASS"])

    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES + ("G06-MANIFEST",))
    return {
        "schema": "crypto_regime_lab.ra06_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "overall": "PASS" if overall else "FAIL",
    }
