"""RA-07 verifier (RA-GUIDE-1.0 section 11, gates G07-VALID/CONTROL/STATS/
DECAY/CLAIM). Same discipline as RA-01..06: required artifacts exist and
hash-match, mandatory tests really ran (junit), no self-declared status
string, no BLOCKED artifact riding a PASS.
"""
from __future__ import annotations

from pathlib import Path

from .verifier import _gate, _load_json, _sha256

REQUIRED_GATES = ("G07-VALID", "G07-CONTROL", "G07-STATS", "G07-DECAY", "G07-CLAIM")
REQUIRED_ARTIFACTS = (
    "replication_spec.json",
    "complete_coverage_matrix.json",
    "cell2_result.json",
    "paired_accounts.json",
    "control_results.json",
    "decay_table.json",
    "uncertainty_results.json",
    "multiplicity_ledger.json",
    "bootstrap_self_check.json",
    "support_report.json",
    "sensitivity_report.json",
    "cost_risk_attribution.json",
    "phase_gate.json",
    "phase_manifest.json",
    "report.md",
    "handoff.md",
)
CASE_IDS = tuple(f"R{i:02d}" for i in range(1, 10))
GATE_SCHEMA = "regime_lab.ra_phase_gate.v1"
VERDICT_BEARING = ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
CLAIM_VOCABULARY = ("NOT_EVALUABLE", "INCONCLUSIVE_SUPPORT", "POSITIVE_WITHIN_SCOPE",
                    "NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE", "UNDERPERFORMED_WITHIN_SCOPE",
                    "INCONCLUSIVE_EFFECT")
COVERAGE_VOCABULARY = ("RUN_VALID", "BLOCKED_CAPABILITY", "NOT_RUN_BUDGET")


def verify_ra07(run_dir: str | Path, *, pytest_xml, protected_status_after: str) -> dict:
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

    # -- G07-VALID: freeze + coverage + cell2 structurally sound, no arm
    # silently omitted --------------------------------------------------------
    reasons = list(test_reasons)
    if missing:
        reasons.append(f"missing artifacts: {missing}")
    if node_ids:
        for case_id in CASE_IDS:
            if not any(case_id.lower() in got.lower() or case_id in got for got in node_ids):
                reasons.append(f"{case_id} has no matching test in the junit report")
    else:
        reasons.append("no junit node IDs available to confirm R01-R09 ran")
    spec = docs.get("replication_spec.json")
    if spec is None:
        reasons.append("replication_spec.json missing or unreadable")
    elif not spec.get("frozen_before_outcomes"):
        reasons.append("replication_spec.json does not assert frozen_before_outcomes")
    coverage = docs.get("complete_coverage_matrix.json")
    if coverage is None:
        reasons.append("complete_coverage_matrix.json missing or unreadable")
    else:
        rows = coverage.get("rows") or []
        if len(rows) != 20:
            reasons.append(f"coverage matrix has {len(rows)} rows, expected 20")
        bad_status = [r["cell"] for r in rows if r.get("coverage_status") not in COVERAGE_VOCABULARY]
        if bad_status:
            reasons.append(f"coverage rows with unrecognised status: {bad_status}")
        run_valid = [r for r in rows if r.get("coverage_status") == "RUN_VALID"]
        if len(run_valid) < 2:
            reasons.append("fewer than 2 RUN_VALID cells; RA07.2 requires at least a second cell")
    cell2 = docs.get("cell2_result.json")
    if cell2 is None:
        reasons.append("cell2_result.json missing or unreadable")
    elif cell2.get("capability_status") == "EXECUTED":
        for arm in ("STATIC", "M4_CAL", "M4_CAL_MATCHED", "M4_REGIME"):
            if arm not in (cell2.get("arms") or {}):
                reasons.append(f"cell2_result.json EXECUTED but arm {arm} missing (silent drop)")
    elif not cell2.get("blocked_reason"):
        reasons.append("cell2_result.json not EXECUTED and carries no blocked_reason")
    gates["G07-VALID"] = _gate(not reasons, reasons)
    if junit_info is not None:
        gates["G07-VALID"]["tests"] = junit_info

    # -- G07-CONTROL: all 5 ordered controls present with a real status -------
    reasons = []
    controls = docs.get("control_results.json")
    if controls is None:
        reasons.append("control_results.json missing or unreadable")
    else:
        for name in ("CALENDAR_BUDGET_MATCHED", "AGE_ONLY", "DELAYED_INFORMATION",
                     "PLACEBO_TIMING", "RISK_EXPOSURE_ATTRIBUTION"):
            entry = controls.get(name)
            if entry is None:
                reasons.append(f"control_results.json missing entry: {name}")
                continue
            if not entry.get("status"):
                reasons.append(f"{name} has no status")
        age_only = controls.get("AGE_ONLY") or {}
        if age_only.get("status") == "NOT_APPLICABLE" and not age_only.get("reason"):
            reasons.append("AGE_ONLY is NOT_APPLICABLE with no reason")
        placebo = controls.get("PLACEBO_TIMING") or {}
        if placebo.get("status") == "OK" and placebo.get("fidelity") is None:
            reasons.append("PLACEBO_TIMING status OK but no fidelity check recorded")
    gates["G07-CONTROL"] = _gate(not reasons, reasons)

    # -- G07-STATS: zero engine calls, synchronized blocks, numeric reference,
    # frozen plan actually used ------------------------------------------------
    reasons = []
    uncertainty = docs.get("uncertainty_results.json")
    if uncertainty is None:
        reasons.append("uncertainty_results.json missing or unreadable")
    else:
        if not uncertainty.get("no_engine_calls"):
            reasons.append("uncertainty_results.json does not assert no_engine_calls")
        used = uncertainty.get("bootstrap_plan_used") or {}
        planned = (spec or {}).get("bootstrap_plan") or {}
        if used.get("block_length_days_primary") != planned.get("block_length_days_primary"):
            reasons.append("bootstrap block length used does not match the frozen replication_spec")
        if used.get("seed") != planned.get("seed"):
            reasons.append("bootstrap seed used does not match the frozen replication_spec")
    self_check = docs.get("bootstrap_self_check.json")
    if self_check is None:
        reasons.append("bootstrap_self_check.json missing or unreadable")
    elif not self_check.get("pass"):
        reasons.append("bootstrap_self_check.json numeric reference check did not pass")
    elif not self_check.get("uses_only_synthetic_data"):
        reasons.append("bootstrap_self_check.json does not assert synthetic-only data")
    multiplicity = docs.get("multiplicity_ledger.json")
    if multiplicity is None:
        reasons.append("multiplicity_ledger.json missing or unreadable")
    elif multiplicity.get("primary_unadjusted", {}).get("adjustment") != \
            "NONE (single pre-registered primary hypothesis, guide 13.4)":
        reasons.append("primary hypothesis must stay unadjusted (multiplicity applies to secondary only)")
    gates["G07-STATS"] = _gate(not reasons, reasons)

    # -- G07-DECAY: D1/D2/D3 all present with correct definitions -------------
    reasons = []
    decay = docs.get("decay_table.json")
    if decay is None:
        reasons.append("decay_table.json missing or unreadable")
    else:
        rows = decay.get("rows") or []
        kinds = {r.get("comparison_kind") for r in rows}
        for required_kind in ("D1_IS_TO_OOS", "D2_PARAMETER_AGE", "D3_ADJACENT_OPERATIONAL_FOLDS"):
            if required_kind not in kinds:
                reasons.append(f"decay_table.json has no {required_kind} rows")
        for row in rows:
            if row.get("validity_status") is None:
                reasons.append(f"decay row {row.get('selection_id')} has no validity_status")
            if row.get("metric_name") == "average_fold_sharpe":
                reasons.append("a decay row averages fold Sharpes, which guide 13.1 forbids")
    gates["G07-DECAY"] = _gate(not reasons, reasons)

    # -- G07-CLAIM: registered vocabulary only, no p-value shopping -----------
    reasons = []
    if uncertainty is not None:
        primary_claim = (uncertainty.get("primary") or {}).get("claim") or {}
        if primary_claim.get("status") not in (*CLAIM_VOCABULARY, None):
            reasons.append(f"primary claim status not in registered vocabulary: {primary_claim.get('status')!r}")
        for name, row in (uncertainty.get("secondary") or {}).items():
            claim = row.get("claim") or {}
            if claim.get("status") not in (*CLAIM_VOCABULARY, None):
                reasons.append(f"{name} claim status not in registered vocabulary: {claim.get('status')!r}")
    report_text = (root / "report.md").read_text() if (root / "report.md").is_file() else ""
    if "conclusion_level" not in report_text.lower() and "conclusion level" not in report_text.lower():
        reasons.append("report.md does not state a conclusion_level")
    gate_doc = docs.get("phase_gate.json")
    if gate_doc is None:
        reasons.append("phase_gate.json missing or unreadable")
    else:
        if gate_doc.get("schema") != GATE_SCHEMA:
            reasons.append(f"phase gate schema must be {GATE_SCHEMA}")
        if gate_doc.get("phase_id") != "RA-07":
            reasons.append("phase gate receipt belongs to another phase")
        if gate_doc.get("owner_review", {}).get("status") != "PENDING":
            reasons.append("owner review must stay PENDING until a real decision")
        if gate_doc.get("can_start_next_phase") is not False:
            reasons.append("can_start_next_phase must be false until owner approval")
    if protected_status_after.strip():
        reasons.append("protected tree changed by the phase; delta: " + protected_status_after.strip()[:500])
    gates["G07-CLAIM"] = _gate(not reasons, reasons)

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
    manifest_gate = _gate(not reasons, reasons)

    for name in REQUIRED_ARTIFACTS:
        doc = docs.get(name)
        if isinstance(doc, dict) and doc.get("status") == "BLOCKED":
            gates["G07-VALID"] = _gate(False, gates["G07-VALID"]["reasons"]
                                       + [f"{name} reports BLOCKED and cannot ride a PASS"])

    all_gates = {**gates, "G07-MANIFEST": manifest_gate}
    overall = all(g["pass"] for g in all_gates.values()) and all(
        g in all_gates for g in REQUIRED_GATES + ("G07-MANIFEST",))
    return {
        "schema": "crypto_regime_lab.ra07_verification.v1",
        "run_dir": str(root),
        "gates": all_gates,
        "overall": "PASS" if overall else "FAIL",
    }
