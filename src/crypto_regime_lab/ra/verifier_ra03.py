"""Thin RA-03 verifier (RA-GUIDE-1.0 section 7, gates G03-PARITY/MEM/ROUTE/COST).

Same discipline as RA-01/RA-02's verifiers: required artifacts exist and
hash-match their manifest, mandatory tests really ran (parsed from junit),
and each gate has a machine-checkable criterion over committed artifacts --
never a self-declared status string.
"""

from __future__ import annotations

from pathlib import Path

from .verifier import _gate, _load_json, _sha256

REQUIRED_GATES = ("G03-PARITY", "G03-MEM", "G03-ROUTE", "G03-COST")
REQUIRED_ARTIFACTS = (
    "route_matrix.json",
    "retention_contract.json",
    "memory_profile.json",
    "parity_report.json",
    "work_profile.json",
    "capacity_forecast.json",
    "resource_receipts.json",
    "phase_gate.json",
    "phase_manifest.json",
    "report.md",
    "handoff.md",
)
CASE_IDS = tuple(f"M{i:02d}" for i in range(1, 9))
GATE_SCHEMA = "regime_lab.ra_phase_gate.v1"
VERDICT_BEARING = ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")


def verify_ra03(run_dir: str | Path, *, pytest_xml, protected_status_after: str) -> dict:
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

    # -- G03-PARITY: M01-M08 present in the junit and the phase kept semantics
    reasons = list(test_reasons)
    if missing:
        reasons.append(f"missing artifacts: {missing}")
    matrix = docs.get("parity_report.json")
    if matrix is None:
        reasons.append("parity_report.json missing or unreadable")
    else:
        covered = set(matrix.get("cases_covered", []))
        for case_id in CASE_IDS:
            if case_id not in covered:
                reasons.append(f"{case_id} not covered by parity_report.json")
        if matrix.get("primary_semantics_changed_for_speed") is not False:
            reasons.append("primary_semantics_changed_for_speed must be explicitly false")
        for node in matrix.get("required_test_node_ids", []):
            if not any(node in got for got in node_ids):
                reasons.append(f"required test not found in junit: {node}")
    gates["G03-PARITY"] = _gate(not reasons, reasons)
    if junit_info is not None:
        gates["G03-PARITY"]["tests"] = junit_info

    # -- G03-MEM: representative candidate + deployment scope under cap -------
    reasons = []
    mem = docs.get("memory_profile.json")
    if mem is None:
        reasons.append("memory_profile.json missing or unreadable")
    else:
        profiles = mem.get("profiles", [])
        if not profiles:
            reasons.append("no measured memory profile")
        for row in profiles:
            if row.get("extrapolated") and not row.get("extrapolation_reason"):
                reasons.append("an extrapolated profile must state why an actual probe was not run")
            if row.get("peak_rss_gib_max") is None:
                reasons.append("profile missing a measured peak RSS")
            elif not row.get("extrapolated") and row["peak_rss_gib_max"] > row.get("registered_per_process_rss_cap_gib", 0):
                reasons.append(f"{row.get('alpha_id')} exceeded the registered per-process cap")
        scopes = {row.get("scope") for row in profiles}
        if "representative_train_candidate" not in scopes:
            reasons.append("no representative train-candidate profile")
        if "deployment_scope" not in scopes:
            reasons.append("no deployment-scope profile")
    gates["G03-MEM"] = _gate(not reasons, reasons)

    # -- G03-ROUTE: pilot cell qualified; other cells keep real status --------
    reasons = []
    route = docs.get("route_matrix.json")
    if route is None:
        reasons.append("route_matrix.json missing or unreadable")
    else:
        if route.get("primary_pilot_qualified") is not True:
            reasons.append("primary pilot A-SC route not qualified")
        rows = {r.get("alpha_id"): r for r in route.get("rows", [])}
        for alpha in ALPHAS:
            row = rows.get(alpha)
            if row is None:
                reasons.append(f"{alpha} missing from the route matrix (status must never be silently absent)")
            elif row.get("status") not in ("OK", "FAILED"):
                reasons.append(f"{alpha} has no real status")
            elif row.get("status") == "OK" and row.get("fills") is None:
                reasons.append(f"{alpha} OK row missing a measured fill count (never a fabricated 0)")
    gates["G03-ROUTE"] = _gate(not reasons, reasons)

    # -- G03-COST: forecast from measurements; admission rejects an over-envelope job
    reasons = []
    forecast = docs.get("capacity_forecast.json")
    if forecast is None:
        reasons.append("capacity_forecast.json missing or unreadable")
    else:
        if not forecast.get("measured_cost_per_task_seconds"):
            reasons.append("no measured per-task cost to forecast from")
        if forecast.get("unmeasured_speedup_commitment"):
            reasons.append("forecast may not commit to an unmeasured speedup")
        probe = forecast.get("admission_probe") or {}
        if probe.get("over_envelope_status") != "BLOCKED_BUDGET":
            reasons.append("an over-envelope forecast job was not refused by admission")
        if probe.get("in_envelope_status") not in ("ADMIT",):
            reasons.append("a trivially in-envelope job was not admitted")
    gates["G03-COST"] = _gate(not reasons, reasons)

    # -- ledger/protected discipline shared with RA-01/RA-02 ------------------
    reasons = []
    receipts = docs.get("resource_receipts.json")
    if receipts is None:
        reasons.append("resource_receipts.json missing or unreadable")
    else:
        before = receipts.get("ledger_before") or {}
        after = receipts.get("ledger_after") or {}
        for key in ("spent", "attempts", "budget"):
            if before.get(key) is None or after.get(key) is None:
                reasons.append(f"ledger snapshot missing {key}")
            elif before.get(key) != after.get(key):
                reasons.append(f"ledger {key} changed during the phase: {before.get(key)} -> {after.get(key)}")
    if protected_status_after.strip():
        reasons.append("protected tree changed by the phase; delta: " + protected_status_after.strip()[:500])
    gate_doc = docs.get("phase_gate.json")
    if gate_doc is None:
        reasons.append("phase_gate.json missing or unreadable")
    else:
        if gate_doc.get("schema") != GATE_SCHEMA:
            reasons.append(f"phase gate schema must be {GATE_SCHEMA}")
        if gate_doc.get("phase_id") != "RA-03":
            reasons.append("phase gate receipt belongs to another phase")
        if gate_doc.get("owner_review", {}).get("status") != "PENDING":
            reasons.append("owner review must stay PENDING until a real decision")
        if gate_doc.get("can_start_next_phase") is not False:
            reasons.append("can_start_next_phase must be false until owner approval")
    gates["G03-LEDGER"] = _gate(not reasons, reasons)

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
    gates["G03-MANIFEST"] = _gate(not reasons, reasons)

    for name in REQUIRED_ARTIFACTS:
        doc = docs.get(name)
        if isinstance(doc, dict) and doc.get("status") == "BLOCKED":
            gates["G03-PARITY"] = _gate(False, gates["G03-PARITY"]["reasons"]
                                        + [f"{name} reports BLOCKED and cannot ride a PASS"])

    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES + ("G03-LEDGER", "G03-MANIFEST"))
    return {
        "schema": "crypto_regime_lab.ra03_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "overall": "PASS" if overall else "FAIL",
    }
