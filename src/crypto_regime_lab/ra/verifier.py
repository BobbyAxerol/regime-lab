"""Thin RA-01 verifier (RA-GUIDE-1.0 §5 RA01.6, §14.3, gates G01-*).

Reuses the lab's manifest discipline (atomic strict-JSON artifacts with
lab_run_id) and adds the RA receipt check: required gate IDs, artifact
hashes, source dependency digests, actual commands/exit/status, test counts,
missing artifacts, block reasons, protected-state delta and approval
dependency. Exit code 0 alone is never enough — and neither is this
verifier's PASS without the artifacts it actually inspected.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("G01-ID", "G01-MIG", "G01-VERIFY", "G01-BUDGET", "G01-REPORT")
REQUIRED_ARTIFACTS = (
    "baseline_identity.json",
    "finding_disposition.json",
    "protocol_migration.json",
    "registration.json",
    "resource_budget.json",
    "test_registry.json",
    "phase_manifest.json",
    "report.md",
    "handoff.md",
)
FINDINGS = tuple(f"F-{i:02d}" for i in range(1, 9))
ALLOWED_DISPOSITIONS = (
    "PRESENT",
    "FIXED_WITH_PROOF",
    "SUPERSEDED_PATH_QUARANTINED",
    "NOT_REPRODUCED_WITH_SCOPE",
    "NEEDS_RUNTIME",
)

from .admission import admit_job  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(ok: bool, reasons: list[str]) -> dict:
    return {"pass": ok, "reasons": reasons}


def _load_json(path: Path, errors: list[str]) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"unreadable artifact {path.name}: {exc}")
        return None


def verify_ra01(run_dir: str | Path, *, pytest_xml: str | Path | None,
                protected_status_after: str) -> dict:
    """Verify one RA-01 run directory. Returns the gate matrix (never raises)."""
    root = Path(run_dir)
    gates: dict[str, dict] = {}

    docs: dict[str, dict | None] = {}
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    for name in REQUIRED_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            docs[name] = _load_json(root / name, [])

    # -- G01-ID: pinned branch/worktree/engine, protected untouched ----------
    reasons: list[str] = []
    ident = docs.get("baseline_identity.json")
    if ident is None:
        reasons.append("baseline_identity.json missing or unreadable")
    else:
        if "inventory" in ident and not ident.get("git_head_full"):
            ident = ident["inventory"]  # run_ra01.py nests live inventory one level
        head = ident.get("git_head_full", "")
        if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
            reasons.append(f"git HEAD not a full 40-hex sha: {head!r}")
        if not ident.get("git_branch"):
            reasons.append("git branch not recorded")
        eng = ident.get("engine", {})
        if not eng.get("quantbt_engine_version") or not eng.get("quantbt_native_version"):
            reasons.append("engine/native versions not pinned")
        rec_hash = eng.get("endpoint_sha256_installed", "")
        inst_path = eng.get("endpoint_path_installed", "")
        if rec_hash and inst_path and Path(inst_path).is_file():
            if _sha256(Path(inst_path)) != rec_hash:
                reasons.append("installed endpoint.py hash drifted since inventory")
        elif not rec_hash:
            reasons.append("installed endpoint hash not recorded")
        if not eng.get("endpoint_sha256_protected_source"):
            reasons.append("protected-source endpoint hash not recorded")
    if protected_status_after.strip():
        reasons.append(
            "protected tree changed by the phase; delta: "
            + protected_status_after.strip()[:500]
        )
    gates["G01-ID"] = _gate(not reasons, reasons)

    # -- G01-MIG: old registrations/claims/evidence immutable, mapping full --
    reasons = []
    mig = docs.get("protocol_migration.json")
    if mig is None:
        reasons.append("protocol_migration.json missing or unreadable")
    else:
        rows = mig.get("rows", [])
        if len(rows) < 6:
            reasons.append(f"migration table has {len(rows)} rows, need >= 6")
        for row in rows:
            if not row.get("old_gate") or not row.get("new_disposition") or not row.get("required_test"):
                reasons.append(f"migration row incomplete: {row}")
                break
    reg = docs.get("registration.json")
    if reg is None:
        reasons.append("registration.json missing or unreadable")
    else:
        ns = reg.get("namespace", "")
        if ns in ("R01", "r01", ""):
            reasons.append(f"registration reuses immutable namespace: {ns!r}")
        approvals = reg.get("approvals", {})
        if not approvals or any(v != "PENDING" for v in approvals.values()):
            reasons.append("approvals must all be recorded PENDING until a real decision")
    manifest = docs.get("phase_manifest.json")
    if manifest is None:
        reasons.append("phase_manifest.json missing or unreadable")
    gates["G01-MIG"] = _gate(not reasons, reasons)

    # -- G01-VERIFY: receipts, hashes, tests, no fake pass -------------------
    reasons = []
    if missing:
        reasons.append(f"missing artifacts: {missing}")
    if manifest is not None:
        for entry in manifest.get("artifacts", []):
            rel = entry.get("relpath", "")
            want = entry.get("sha256", "")
            target = root / rel
            if not target.is_file():
                reasons.append(f"manifest lists missing file: {rel}")
            elif want and _sha256(target) != want:
                reasons.append(f"hash mismatch (tampered or stale): {rel}")
        for name in REQUIRED_ARTIFACTS:
            if name.endswith(".json") and name != "phase_manifest.json" and not any(
                e.get("relpath") == name for e in manifest.get("artifacts", [])
            ):
                # The manifest never hashes itself (RA08.1: no self-reference);
                # its integrity rides the verifier run plus the scoped commit.
                reasons.append(f"required artifact not indexed in manifest: {name}")
    else:
        reasons.append("no manifest to check hashes against")
    test_info = _check_tests(pytest_xml, docs.get("test_registry.json"), reasons)
    for name in REQUIRED_ARTIFACTS:
        doc = docs.get(name)
        if isinstance(doc, dict) and doc.get("status") == "BLOCKED":
            reasons.append(f"{name} reports BLOCKED and cannot ride a PASS")
    gates["G01-VERIFY"] = _gate(not reasons, reasons)
    if test_info:
        gates["G01-VERIFY"]["tests"] = test_info

    # -- G01-BUDGET: envelope math, no reset, admission refuses over-run -----
    reasons = []
    rb = docs.get("resource_budget.json")
    if rb is None:
        reasons.append("resource_budget.json missing or unreadable")
    else:
        try:
            total = float(rb["total_wall_s"])
            charged = float(rb["charged_wall_s"])
            if abs((charged + float(rb["remaining_wall_s"])) - total) > max(1.0, total * 1e-9):
                reasons.append("remaining != total - charged")
            caps = rb["frozen_caps"]
            probe_over = admit_job(
                {"requested_wall_s": total + 1, "requested_rss_gb": 0.1,
                 "workers": 1, "retries_used": 0},
                {"total_wall_s": total, "charged_wall_s": charged}, caps)
            if probe_over["status"] != "BLOCKED_BUDGET":
                reasons.append("admission did not refuse an over-envelope probe job")
            probe_ok = admit_job(
                {"requested_wall_s": 1, "requested_rss_gb": 0.1,
                 "workers": 1, "retries_used": 0},
                {"total_wall_s": total, "charged_wall_s": charged}, caps)
            if charged < total and probe_ok["status"] != "ADMIT":
                reasons.append("admission refused a trivially admissible probe job")
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(f"budget/admission fields malformed: {exc}")
    gates["G01-BUDGET"] = _gate(not reasons, reasons)

    # -- G01-REPORT: every finding has a disposition and a future phase ------
    reasons = []
    disp = docs.get("finding_disposition.json")
    if disp is None:
        reasons.append("finding_disposition.json missing or unreadable")
    else:
        entries = {e.get("finding_id"): e for e in disp.get("findings", [])}
        for fid in FINDINGS:
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
    gates["G01-REPORT"] = _gate(not reasons, reasons)

    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES
    )
    return {
        "schema": "crypto_regime_lab.ra01_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "overall": "PASS" if overall else "FAIL",
    }


def _check_tests(pytest_xml, registry: dict | None, reasons: list[str]) -> dict | None:
    if pytest_xml is None or not Path(pytest_xml).is_file():
        reasons.append("pytest report missing: no test evidence, cannot PASS")
        return None
    try:
        suite = ET.parse(str(pytest_xml)).getroot()
        suites = suite.findall("testsuite") or [suite]
        tests = sum(int(s.get("tests", 0)) for s in suites)
        failures = sum(int(s.get("failures", 0)) for s in suites)
        errors = sum(int(s.get("errors", 0)) for s in suites)
        node_ids = {
            f"{c.get('classname', '')}::{c.get('name', '')}"
            for s in suites for c in s.findall("testcase")
        }
    except ET.ParseError as exc:
        reasons.append(f"pytest report unparseable: {exc}")
        return None
    info = {"tests": tests, "failures": failures, "errors": errors}
    if tests == 0:
        reasons.append("no-tests-collected cannot PASS")
    if failures or errors:
        reasons.append(f"test failures={failures} errors={errors} cannot PASS")
    if registry:
        for wanted in registry.get("test_node_ids", []):
            if not any(wanted in got for got in node_ids):
                reasons.append(f"registered test not found in report: {wanted}")
                break
    return info
