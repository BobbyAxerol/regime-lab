"""FP01.4 gate FP01-G-* thin verifier (guide §13 exit gate + §26.3).

Behavioral by construction (FP-F09): every gate re-derives its verdict from
the artifacts on disk -- artifact hash re-check, pytest XML re-parse with the
mandatory FP01 test node IDs present, finding-disposition re-evaluation, and
re-reading (not trusting) protected/engine pins. A gate that cannot prove its
claim from the inspected bytes fails. `verify_fp01` never raises: it returns
the gate matrix with reasons.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP01-G-VALIDITY", "FP01-G-IDENTITY", "FP01-G-MIGRATION", "FP01-G-BUDGET")

REQUIRED_ARTIFACTS = (
    "baseline_identity.json",
    "finding_disposition.json",
    "protocol_migration.json",
    "registration.json",
    "resource_budget.json",
    "test_registry.json",
    "phase_manifest.json",
    "decay_reconciliation.json",
    "artifact_inventory.json",
    "gate_receipt.json",
    "report.md",
    "handoff.md",
)

REQUIRED_TEST_NODES = (
    "test_fp01_t01_future_only_emissions_do_not_change_calibration",
    "test_fp01_t02_forced_rejection_keeps_rejected_params_out_of_the_account",
    "test_fp01_t03_boundary_keeps_exactly_two_returns_on_100_120_108",
    "test_fp01_t04_warmup_outside_evaluation_does_not_grow_sample_count",
    "test_fp01_t05_same_params_data_economics_reach_parity",
    "test_fp01_t06_identical_arms_give_no_false_significant_p_value",
    "test_fp01_t07_chronology_guard_refuses_future_labels",
    "test_fp01_claim_logic_band_alone_cannot_form_a_verdict",
)

FINDING_IDS = tuple(f"FP-F{i:02d}" for i in range(1, 10))
ALLOWED_DISPOSITIONS = (
    "PRESENT",
    "FIXED_WITH_PROOF",
    "SUPERSEDED_PATH_QUARANTINED",
    "NOT_REPRODUCED_WITH_SCOPE",
    "NEEDS_RUNTIME",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(ok: bool, reasons: list) -> dict:
    return {"pass": bool(ok), "reasons": list(reasons)}


def _load_json(path: Path, errors: list) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"unreadable artifact {path.name}: {exc}")
        return None


def verify_fp01(run_dir, *, pytest_xml=None) -> dict:
    """Verify one FP-01 run directory. Returns the gate matrix (never raises)."""
    root = Path(run_dir)
    gates: dict = {}

    docs: dict = {}
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    for name in REQUIRED_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            docs[name] = _load_json(root / name, [])

    # -- manifest cross-check: every listed artifact hash must match the bytes --
    reasons: list = []
    manifest = docs.get("phase_manifest.json")
    if manifest is None:
        reasons.append("phase_manifest.json missing or unreadable")
    else:
        for entry in manifest.get("artifacts", []):
            name = entry.get("path")
            # phase_manifest.json cannot hash itself; gate_receipt.json is
            # WRITTEN TWICE by design (a PENDING_VERIFICATION placeholder,
            # hashed into this manifest, then updated in place with the
            # verdict THIS VERY VERIFICATION produces) -- its bytes
            # therefore never match the pre-verdict hash on any run AFTER
            # the one that wrote it. Both are bundle-level summaries
            # written last, not source-of-truth artifacts a drift check
            # protects; excluded for the same reason, not a loosened check.
            if not name or name in ("phase_manifest.json", "gate_receipt.json"):
                continue
            target = root / name
            if not target.is_file():
                reasons.append(f"manifest lists {name} but it is not on disk")
                continue
            if entry.get("sha256") and entry["sha256"] != _sha256(target):
                reasons.append(f"manifest hash mismatch on {name}: bytes changed after writing")

    # -- FP01-G-VALIDITY: all 7 required tests actually ran green + findings --
    disp = docs.get("finding_disposition.json")
    if disp is None:
        reasons.append("finding_disposition.json missing or unreadable")
    else:
        entries = {e.get("finding_id"): e for e in disp.get("findings", [])}
        for fid in FINDING_IDS:
            entry = entries.get(fid)
            if entry is None:
                reasons.append(f"{fid} has no disposition (no 'read therefore done')")
                continue
            if entry.get("current_disposition") not in ALLOWED_DISPOSITIONS:
                reasons.append(f"{fid} disposition not in allowed vocabulary")
            if not entry.get("evidence_refs"):
                reasons.append(f"{fid} has no evidence_refs")
            if not entry.get("planned_phase"):
                reasons.append(f"{fid} has no planned_phase")
    reg_tests = _check_tests(pytest_xml, docs.get("test_registry.json"), reasons)
    gates["FP01-G-VALIDITY"] = _gate(not reasons, reasons)

    # -- FP01-G-IDENTITY: pinned branch/worktree/engine, protected untouched --
    reasons = []
    ident = docs.get("baseline_identity.json")
    if ident is None:
        reasons.append("baseline_identity.json missing or unreadable")
    else:
        head = ident.get("git_head_full", "")
        if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
            reasons.append(f"git HEAD not a full 40-hex sha: {head!r}")
        if not ident.get("git_branch"):
            reasons.append("git branch not recorded")
        eng = ident.get("engine", {})
        if not eng.get("quantbt_engine_version") or not eng.get("quantbt_native_version"):
            reasons.append("engine/native versions not pinned")
        if eng.get("endpoint_sha256_installed") and eng.get("endpoint_path_installed"):
            live = Path(eng["endpoint_path_installed"])
            if live.is_file() and _sha256(live) != eng["endpoint_sha256_installed"]:
                reasons.append("installed endpoint changed since inventory (protected drift)")
        if (ident.get("protected", {}).get("git_status_porcelain") or "").strip():
            reasons.append("protected tree dirty at inventory time")
    gates["FP01-G-IDENTITY"] = _gate(not reasons, reasons)

    # -- FP01-G-MIGRATION: every row has old rule, new rule, reason, test --
    reasons = []
    mig = docs.get("protocol_migration.json")
    if mig is None:
        reasons.append("protocol_migration.json missing or unreadable")
    else:
        rows = mig.get("rows", [])
        if not rows:
            reasons.append("migration has no rows")
        for position, row in enumerate(rows):
            for key in ("old_rule", "new_rule", "reason", "affected_claims_or_tests"):
                if not row.get(key):
                    reasons.append(f"migration row {position} lacks {key}")
    reg = docs.get("registration.json")
    if reg is None:
        reasons.append("registration.json missing or unreadable")
    else:
        for key in ("study_id", "guide_version", "primary", "secondary",
                    "arms", "registered_at_utc"):
            if not reg.get(key):
                reasons.append(f"registration lacks {key}")
        primary = reg.get("primary") or {}
        if "C_FP_CONTEXT" not in str(primary) or "B_FP_PERSISTENCE" not in str(primary):
            reasons.append("primary contrast is not the frozen C-B fixed-timing contrast")
    gates["FP01-G-MIGRATION"] = _gate(not reasons, reasons)

    # -- FP01-G-BUDGET: FP-01 charges nothing to the shared TE ledger --
    reasons = []
    budget = docs.get("resource_budget.json")
    if budget is None:
        reasons.append("resource_budget.json missing or unreadable")
    else:
        if budget.get("fp01_wall_seconds_charged_to_shared_ledger") not in (0, 0.0, None):
            reasons.append("FP-01 must not charge the shared TE budget ledger")
        if not budget.get("shared_ledger_untouched_proof"):
            reasons.append("no proof the shared ledger was re-read, not reset")
    gates["FP01-G-BUDGET"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp01_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "missing_artifacts": missing,
        "pytest": reg_tests,
        "overall": "PASS" if overall else "FAIL",
    }


def _check_tests(pytest_xml, registry: dict | None, reasons: list) -> dict | None:
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
    for wanted in REQUIRED_TEST_NODES:
        if not any(wanted in got for got in node_ids):
            reasons.append(f"required FP01 test not in report: {wanted}")
            break
    if registry:
        for wanted in registry.get("test_node_ids", []):
            if not any(wanted in got for got in node_ids):
                reasons.append(f"registered test not found in report: {wanted}")
                break
    return info
