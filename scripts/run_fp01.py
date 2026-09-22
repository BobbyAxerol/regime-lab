#!/usr/bin/env python3
"""Build FP-01 artifacts (guide §13): inventory, finding dispositions with
verified repairs, migration registration, budget, test registry, manifest,
gate receipt, report.md + handoff.md under evidence/forward_persistence_fp_v1/.

Also writes configs/forward_persistence_fp_v1/{registration,protocol_migration}.json
(idempotent -- re-running never duplicates rows) and handoff/FP_CURRENT.md.

FP-01 charges nothing to the shared TE ledger; it only RE-READS it.

Usage:
  lab_venv/bin/python scripts/run_fp01.py --pytest-xml <junit xml of the FP-01 tests>
Exit 0 iff the FP-01 verifier reports PASS.
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

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.fp import GUIDE_VERSION, PHASE_ID, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp.findings import ALLOWED_DISPOSITIONS, FINDING_IDS, finding_rows  # noqa: E402
from crypto_regime_lab.fp.inventory import inventory  # noqa: E402
from crypto_regime_lab.fp.registration import migration_rows, registration  # noqa: E402
from crypto_regime_lab.fp.verifier_fp01 import (  # noqa: E402
    REQUIRED_GATES, REQUIRED_TEST_NODES, verify_fp01,
)
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

QUANTBT = Path("/root/bobby/pool_alpha/quantbt")
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"

TEST_NODE_IDS = list(REQUIRED_TEST_NODES) + [
    "test_fp01_verifier_passes_on_a_valid_bundle",
    "test_fp01_verifier_fails_on_empty_dir",
    "test_fp01_verifier_fails_on_tampered_artifact",
    "test_fp01_verifier_fails_on_zero_tests",
    "test_fp01_verifier_fails_on_disposition_without_evidence",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_configs() -> dict:
    """FP01.3: idempotent registration + migration under configs/."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    stamped = utcnow()
    reg = registration(registered_at_utc=stamped)
    reg_path = CONFIG_DIR / "registration.json"
    if reg_path.is_file():
        old = json.loads(reg_path.read_text())
        if (old.get("study_id"), old.get("guide_version"), old.get("primary"),
                old.get("secondary"), old.get("arms")) == (
                reg["study_id"], reg["guide_version"], reg["primary"],
                reg["secondary"], reg["arms"]):
            reg = old  # same contract: keep the original registration timestamp
    else:
        reg_path.write_text(json.dumps(reg, indent=2) + "\n")
    mig = {"schema": "regime_lab.fp_protocol_migration.v1", "study_id": STUDY_ID,
           "guide_version": GUIDE_VERSION, "stamped_at_utc": stamped,
           "rows": migration_rows(),
           "note": ("Deliberate methodology revision, not a certificate that old gates "
                    "passed. Owner approval opens FP economics; no silent "
                    "threshold/risk-cap loosening inside the same migration.")}
    (CONFIG_DIR / "protocol_migration.json").write_text(json.dumps(mig, indent=2) + "\n")
    return {"registration_path": str(reg_path), "registered_at_utc": reg["registered_at_utc"]}


def build_artifact_inventory() -> dict:
    """FP-F08 evidence: every run dir under the lab's evidence trees with
    path/hash/size/tracked-vs-ignored status. Missing stays listed, never
    regenerated to fill a gap."""
    import subprocess

    def tracked(path: Path) -> str:
        rel = str(path.relative_to(LAB))
        proc = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=LAB,
                              capture_output=True, timeout=30)
        if proc.returncode == 0:
            return "tracked"
        proc = subprocess.run(["git", "check-ignore", "-q", rel], cwd=LAB,
                              capture_output=True, timeout=30)
        return "ignored" if proc.returncode == 0 else "untracked"
    entries, missing = [], []
    roots = [LAB / "evidence" / "regime_time_edge_ra_v1",
             LAB / "evidence" / "corrective_mode4_v3" / "FUP-04",
             LAB / "evidence" / "corrective_mode4_v3" / "FUP-05"]
    for root in roots:
        if not root.is_dir():
            missing.append({"expected_dir": str(root.relative_to(LAB)),
                            "status": "ABSENT_DIR"})
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(LAB))
            try:
                size = path.stat().st_size
            except OSError:
                missing.append({"expected_file": rel, "status": "UNREADABLE"})
                continue
            entries.append({"path": rel, "bytes": size,
                            "sha256": sha256_file(path) if size < 64 * 1024 * 1024 else None,
                            "sha256_skipped_reason": (None if size < 64 * 1024 * 1024
                                                      else "over_64MiB_hash_on_demand"),
                            "git": tracked(path)})
    untracked_small = [e for e in entries
                       if e["git"] == "untracked" and e["bytes"] < 2 * 1024 * 1024]
    return {
        "schema": "regime_lab.fp_artifact_inventory.v1",
        "n_files": len(entries),
        "n_missing_dirs_or_files": len(missing),
        "missing": missing,
        "untracked_small_json_export_candidates": untracked_small,
        "note": ("FP-F08 PRESENT: export the small-JSON candidates in FP-02; large/"
                 "ignored binaries stay path+hash refs per the gitignore policy."),
    }


def build_decay_reconciliation(*, lab_run_id: str) -> dict:
    """FP-F04 evidence: legacy vs repaired D1 boundary on one REAL arm window.

    Marks come from a committed RA-05 arm's real account equity_daily; both
    conventions run on the SAME marks; the prior mark is the day before the
    fold's test_start. Proves the numerical delta of the REPORT_OR_METRIC_FIX
    on real data instead of asserting it.
    """
    from crypto_regime_lab.fp.decay_bounds import reconcile

    arm_path = (LAB / "evidence" / "regime_time_edge_ra_v1"
                / "ra05-20260918T201236Z-de11db62" / "arms_result.json")
    payload = json.loads(arm_path.read_text())
    account = payload["arms"]["M4_CAL"]["run"]["account"]
    marks = account["equity_daily"]
    fold = payload["arms"]["M4_CAL"]["run"]["fold_selection_table"][0]
    start, end = fold["test_start"], fold["test_end"]
    recon = reconcile(marks, start=start, end=end)
    recon.update({
        "lab_run_id": lab_run_id,
        "source": {"arms_result": str(arm_path.relative_to(LAB)),
                   "arm": "M4_CAL", "fold": 0,
                   "window": [start, end],
                   "sha256": sha256_file(arm_path)},
        "disposition": ("RA-05 row keeps its published value; FP-07 D1 uses the "
                        "repaired convention (recomputed_from, never overwritten)"),
    })
    return recon


def run_fp01(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    started = utcnow()
    cfg = write_configs()
    inv = inventory(lab_root=LAB, protected_root=QUANTBT)

    lab_run_id = new_lab_run_id("fp01")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir

    rows = finding_rows(lab_run_id)
    assert [r["finding_id"] for r in rows] == list(FINDING_IDS)
    assert all(r["current_disposition"] in ALLOWED_DISPOSITIONS for r in rows)
    disposition = {
        "schema": "regime_lab.fp_finding_disposition.v1",
        "lab_run_id": lab_run_id,
        "guide_version": GUIDE_VERSION,
        "findings": rows,
    }
    recon = build_decay_reconciliation(lab_run_id=lab_run_id)
    art_inventory = build_artifact_inventory()

    budget = {
        "schema": "regime_lab.fp01_resource_budget.v1",
        "lab_run_id": lab_run_id,
        "fp01_wall_seconds_charged_to_shared_ledger": 0,
        "shared_ledger_untouched_proof": {
            "ledger_path": inv["shared_te_ledger"]["path"],
            "by_status_reread_at_utc": utcnow(),
            "by_status": inv["shared_te_ledger"]["by_status"],
            "read_error": inv["shared_te_ledger"]["error"],
            "note": "read-only sqlite open (mode=ro); no attempt row written",
        },
        "engine_calls": 0,
        "note": "FP-01 is identity/migration/validity: zero engine calls, zero ledger charge",
    }
    test_registry = {
        "schema": "regime_lab.fp01_test_registry.v1",
        "lab_run_id": lab_run_id,
        "test_node_ids": TEST_NODE_IDS,
        "pytest_xml": pytest_xml,
    }
    registration_copy = registration(registered_at_utc=cfg["registered_at_utc"])
    migration_copy = {
        "schema": "regime_lab.fp_protocol_migration.v1", "study_id": STUDY_ID,
        "guide_version": GUIDE_VERSION, "stamped_at_utc": utcnow(),
        "rows": migration_rows(),
    }
    manifest = {
        "schema": "regime_lab.fp01_phase_manifest.v1",
        "lab_run_id": lab_run_id,
        "study_id": STUDY_ID,
        "phase_id": PHASE_ID,
        "guide_version": GUIDE_VERSION,
        "started_at_utc": started,
        "configs": {"registration": "configs/forward_persistence_fp_v1/registration.json",
                    "protocol_migration": "configs/forward_persistence_fp_v1/protocol_migration.json"},
        "required_gates": list(REQUIRED_GATES),
        "artifacts": [],
    }
    with writer.attempt("fp01_build") as att:
        writer.write_json("baseline_identity.json", inv,
                          schema="regime_lab.fp01_baseline_identity.v1")
        writer.write_json("finding_disposition.json", disposition,
                          schema="regime_lab.fp_finding_disposition.v1")
        writer.write_json("protocol_migration.json", migration_copy,
                          schema="regime_lab.fp_protocol_migration.v1")
        writer.write_json("registration.json", registration_copy,
                          schema="regime_lab.fp_registration.v1")
        writer.write_json("resource_budget.json", budget,
                          schema="regime_lab.fp01_resource_budget.v1")
        writer.write_json("test_registry.json", test_registry,
                          schema="regime_lab.fp01_test_registry.v1")
        writer.write_json("decay_reconciliation.json", recon,
                          schema="regime_lab.fp_decay_boundary_reconciliation.v1")
        writer.write_json("artifact_inventory.json", art_inventory,
                          schema="regime_lab.fp_artifact_inventory.v1")
        writer.write_json("phase_manifest.json", manifest,
                          schema="regime_lab.fp01_phase_manifest.v1")
        att.detail = {"run_dir": str(run_dir)}

    # Two-pass report/verify (RA-07 lesson): write report.md + handoff.md +
    # gate_receipt.json from the artifacts, then verify the FINAL bundle so a
    # PENDING_VERIFICATION placeholder can never structurally fail G-VALIDITY.
    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, rows=rows,
                                recon=recon, art_inventory=art_inventory,
                                budget=budget, started=started)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir)
    (run_dir / "report.md").write_text(report_text, encoding="utf-8")
    (run_dir / "handoff.md").write_text(handoff_text, encoding="utf-8")
    (run_dir / "gate_receipt.json").write_text(json.dumps({
        "schema": "regime_lab.fp_gate.v1", "phase_id": PHASE_ID,
        "guide_version": GUIDE_VERSION, "lab_run_id": lab_run_id,
        "registration_digest": sha256_file(CONFIG_DIR / "registration.json"),
        "required_gates": list(REQUIRED_GATES),
        "technical_gate": "PENDING_VERIFICATION",
        "research_status": "NOT_ASSESSED",
        "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False,
    }, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"] = [
        {"path": name, "sha256": sha256_file(run_dir / name)}
        for name in ("baseline_identity.json", "finding_disposition.json",
                     "protocol_migration.json", "registration.json",
                     "resource_budget.json", "test_registry.json",
                     "decay_reconciliation.json", "artifact_inventory.json",
                     "report.md", "handoff.md", "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "lab_run_id": lab_run_id,
                    "study_id": STUDY_ID,
                    "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp01(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    write_fp_current(lab_run_id=lab_run_id, run_dir=run_dir, verdict=verdict)
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, rows, recon, art_inventory, budget, started) -> str:
    lines = [f"# FP-01 — Contracts, migration và validity repairs ({lab_run_id})",
             "",
             f"- run_dir: {run_dir}",
             f"- started_at: {started}",
             "- engine calls: 0 (identity/migration/validity; nothing financial runs here)",
             "- shared TE ledger charge: 0 (re-read read-only)",
             "",
             "## Exit gates (re-derived by src/crypto_regime_lab/fp/verifier_fp01.py)",
             "",
             "Gates FP01-G-VALIDITY / FP01-G-IDENTITY / FP01-G-MIGRATION / FP01-G-BUDGET; "
             "see gate_receipt.json for the per-gate reasons on THIS bundle.",
             "",
             "## Finding dispositions (guide §13 FP01.2)",
             ""]
    for row in rows:
        lines += [f"### {row['finding_id']} — {row['current_disposition']}",
                  f"- finding: {row['audit_finding']}",
                  f"- required: {row['required']}",
                  f"- verification: {row['verification']}",
                  f"- planned phase: {row['planned_phase']}",
                  f"- claim limit: {row['claim_limit']}",
                  ""]
    rep, leg = recon.get("repaired", {}), recon.get("legacy_ra07_deployment_slice", {})
    lines += ["## Boundary reconciliation (FP-F04, one real RA-05 M4_CAL window)",
              f"- source: {recon.get('source', {}).get('arms_result')}",
              f"- legacy observations: {len(leg.get('return_values') or [])}; "
              f"repaired observations: {len(rep.get('return_values') or [])}; "
              f"added: {recon.get('observations_added')}",
              f"- mean delta (repaired − legacy): {recon.get('mean_daily_return_delta')}",
              f"- disposition: {recon.get('disposition')}",
              "",
              "## Artifact inventory (FP-F08)",
              f"- files scanned: {art_inventory.get('n_files')}; "
              f"missing: {art_inventory.get('n_missing_dirs_or_files')}; "
              f"small-JSON export candidates: "
              f"{len(art_inventory.get('untracked_small_json_export_candidates', []))}",
              "",
              "## Permitted conclusions",
              "- Technical: admission hook, boundary convention, availability guard, "
              "chronology guard, direct-contrast claim logic and behavioral verifier "
              "exist on current source, proved by FP01-T01..T07.",
              "- Research: NOT_ASSESSED -- no market claim in FP-01.",
              "- Owner review: PENDING; FP-02 needs its own approval (R-18).",
              ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir) -> str:
    return "\n".join([
        f"# FP-01 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        "- next authorized action: NONE until the owner approves FP-01 -> FP-02 "
        "(record in evidence/regime_time_edge_ra_v1/owner_decisions.jsonl, R-18).",
        "- FP-02 (guide 14) must reuse: admission_policy hook, parity-proven route, "
        "artifact inventory export list.",
        "- blockers: FP-F08 (raw export) is PRESENT by design; FUP-05 band verdict "
        "is invalidated for causal citation (FP-F06).",
        ""])


def write_fp_current(*, lab_run_id, run_dir, verdict) -> None:
    gates = verdict.get("gates", {})
    states = " / ".join(
        f"{name}={'PASS' if gates.get(name, {}).get('pass') else 'FAIL'}"
        for name in ("FP01-G-VALIDITY", "FP01-G-IDENTITY", "FP01-G-MIGRATION",
                     "FP01-G-BUDGET"))
    (LAB / "handoff" / "FP_CURRENT.md").write_text("\n".join([
        "# FP_CURRENT", "",
        "## Current source",
        f"- run: {lab_run_id} ({run_dir})",
        f"- overall: {verdict.get('overall')}",
        f"- gates: {states}",
        "", "## Phase state",
        "| Phase | Technical | Research | Owner | Evidence |",
        "|---|---|---|---|---|",
        f"| FP-01 | {verdict.get('overall')} | NOT_ASSESSED | PENDING | "
        f"evidence/forward_persistence_fp_v1/{lab_run_id}/ |",
        "| FP-02 | NOT_RUN | NOT_ASSESSED | PENDING (needs R-18 approval) | — |",
        "", "## Latest run",
        f"FP-01 {verdict.get('overall')}: identity + 9 finding dispositions + migration "
        "registration; zero engine calls.",
        "", "## Dieu da biet tu evidence",
        "- Admission was descriptive-only in all published runs; the wired hook exists "
        "and is proved by FP01-T02 (FP-F02).",
        "- D1/OOS dropped the first return vs the IS convention; the repaired convention "
        "and its real-data delta are recorded (FP-F04).",
        "- Band-alone verdicts are unevaluable by construction (FP-F06).",
        "", "## Dieu chua biet",
        "- Whether admission-wired deployment changes any economic outcome (needs FP-07).",
        "- The full artifact export (FP-F08 PRESENT).",
        "", "## Blockers",
        "- FP-F08 PRESENT (planned FP-02/FP-10). Owner review PENDING.",
        "", "## Budget",
        "- FP-01 charged 0 to the shared TE ledger; engine calls 0.",
        "", "## Next authorized action",
        "- NONE: wait for owner approval FP-01 -> FP-02 (R-18).",
        "", "## Khong duoc lam",
        "- No bulk search; no admission/economics change without a new upgrade record; "
        "no FP-02 start without approval.",
        ""]), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp01(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())


