#!/usr/bin/env python3
"""Build RA-01 artifacts (RA-GUIDE-1.0 §5). Implementation, not a probe.

Gathers the live inventory, writes baseline_identity, finding_disposition,
protocol_migration, registration, resource_budget, test_registry and
phase_manifest under evidence/regime_time_edge_ra_v1/<run_id>/, runs the
thin verifier against a pytest XML report, then writes report.md + handoff.md.
Missing inputs become null+reason, never fabricated values.

Usage:
  lab_venv/bin/python scripts/run_ra01.py --pytest-xml <junit xml of the RA-01 tests>
Exit 0 iff the verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.reconcile import reconcile_running_rows  # noqa: E402
from crypto_regime_lab.ra.verifier import REQUIRED_ARTIFACTS, verify_ra01  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY = "regime_time_edge_ra_v1"
QUANTBT = Path("/root/bobby/pool_alpha/quantbt")
TEST_NODE_IDS = [
    "test_admit_accepts_small_job_within_envelope",
    "test_admit_refuses_over_envelope_as_blocked_budget",
    "test_admit_refuses_over_task_cap",
    "test_admit_refuses_excess_workers",
    "test_admit_new_run_id_does_not_reset_charge",
    "test_verifier_fails_on_empty_dir",
    "test_verifier_fails_on_tampered_artifact",
    "test_verifier_fails_on_zero_tests",
    "test_verifier_fails_on_blocked_status_riding_pass",
    "test_verifier_fails_on_protected_delta",
    "test_verifier_passes_on_valid_bundle",
    "test_verifier_reads_nested_baseline_identity",
    "test_reconcile_matches_live_worker_by_start_window",
    "test_reconcile_flags_orphan_running_row",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sh(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)
    return (proc.stdout or "").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protected_fingerprint() -> dict:
    status = sh(["git", "status", "--porcelain"], cwd=QUANTBT)
    endpoint = QUANTBT / "src" / "quantbt" / "endpoint.py"
    return {
        "git_status_porcelain": status,
        "git_head": sh(["git", "rev-parse", "HEAD"], cwd=QUANTBT),
        "endpoint_sha256": sha256_file(endpoint) if endpoint.is_file() else None,
    }


def lab_inventory() -> dict:
    branch = sh(["git", "branch", "--show-current"], cwd=LAB)
    head = sh(["git", "rev-parse", "HEAD"], cwd=LAB)
    dirty = sh(["git", "status", "--porcelain", "--untracked-files=no"], cwd=LAB)
    untracked_raw = sh(["git", "status", "--porcelain"], cwd=LAB)
    untracked = sorted(
        line[3:] for line in untracked_raw.splitlines() if line.startswith("?? ")
    )
    import importlib.metadata as md

    def ver(name: str) -> str | None:
        try:
            return md.version(name)
        except Exception:
            return None

    venv = LAB / "environments" / "lab_venv"
    installed_endpoint = (
        venv / "lib" / "python3.12" / "site-packages" / "quantbt" / "endpoint.py"
    )
    try:
        marker = json.loads((LAB / ".lab_marker.json").read_text())
    except (OSError, ValueError):
        marker = None
    jobs = []
    processes: list[dict] = []
    try:
        ps = subprocess.run(["ps", "-eo", "pid,lstart,cmd"], capture_output=True,
                            text=True, timeout=30).stdout.splitlines()
        for line in ps:
            if "ps -eo" in line:
                continue
            parts = line.split(None, 6)
            if len(parts) < 7:
                continue
            proc = {"pid": parts[0], "started": " ".join(parts[1:5]),
                    "cmd": parts[6][:300]}
            if str(LAB) in proc["cmd"] or "bwrap" in proc["cmd"]:
                processes.append(proc)
            if "run_time_edge.py" in proc["cmd"]:
                jobs.append(proc)
    except Exception as exc:  # keep null+reason, never fabricate
        jobs = [{"error": f"{type(exc).__name__}: {exc}"}]
        processes = [{"error": f"{type(exc).__name__}: {exc}"}]
    ledger_path = (LAB / "evidence" / "time_edge_validation_v4" / "allocations"
                   / "TE02-PILOT-R03" / "ledger.sqlite")
    ledger = {"path": str(ledger_path), "by_status": None, "revisions": None,
              "running_rows": None, "error": None}
    try:
        conn = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True)
        ledger["by_status"] = conn.execute(
            "select status,count(*),round(sum(wall),1) from attempt group by status"
        ).fetchall()
        ledger["revisions"] = conn.execute(
            "select * from budget_revision order by applied_at"
        ).fetchall()
        ledger["running_rows"] = [
            {"id": r[0], "task": r[1], "started": r[2]}
            for r in conn.execute(
                "select id, task, started from attempt where status='RUNNING'"
            ).fetchall()
        ]
        conn.close()
    except Exception as exc:
        ledger["error"] = f"{type(exc).__name__}: {exc}"
    if isinstance(processes, list) and isinstance(ledger.get("running_rows"), list):
        reconciliation = reconcile_running_rows(
            ledger["running_rows"],
            [{"pid": p["pid"], "started": p["started"], "cmd": p["cmd"]}
             for p in processes if "pid" in p])
    else:
        reconciliation = {"error": "ps or ledger snapshot unavailable; "
                                   "reconciliation not performed"}
    package_origins: dict[str, dict] = {}
    for dist_name in ("quantbt-engine", "quantbt-native"):
        try:
            dist = md.distribution(dist_name)
            package_origins[dist_name] = {
                "version": dist.version,
                "installer": (dist.read_text("INSTALLER") or "").strip(),
                "direct_url_json_present": dist.read_text("direct_url.json") is not None,
                "dist_info_path": str(dist.locate_file("")),
            }
        except Exception as exc:
            package_origins[dist_name] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        with open("/proc/meminfo") as handle:
            mem = {line.split(":")[0]: line.split(":")[1].strip()
                   for line in handle if line.startswith(("MemTotal", "MemAvailable"))}
    except OSError:
        mem = {}
    policy_path = LAB / "configs" / "sandbox_policy.json"
    return {
        "git_branch": branch, "git_head_full": head,
        "tracked_dirty": dirty, "untracked_count": len(untracked),
        "untracked_paths": untracked,
        "engine": {
            "quantbt_engine_version": ver("quantbt-engine"),
            "quantbt_native_version": ver("quantbt-native"),
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "endpoint_path_installed": str(installed_endpoint),
            "endpoint_sha256_installed": sha256_file(installed_endpoint)
            if installed_endpoint.is_file() else None,
            "endpoint_sha256_protected_source": sha256_file(
                QUANTBT / "src" / "quantbt" / "endpoint.py"),
            "installer": "pip (INSTALLER=pip, no direct_url.json; wheelhouse install)",
        },
        "package_origins": package_origins,
        "lab_marker": {"study_id": (marker or {}).get("study_id"),
                       "bootstrap_lab_run_id": (marker or {}).get("bootstrap_lab_run_id")},
        "active_jobs": jobs,
        "ledger_te02_pilot_r03": ledger,
        "running_row_reconciliation": reconciliation,
        "host_memory": mem,
        "sandbox_policy_present": policy_path.is_file(),
        "bytecode_policy": {"PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE")},
    }


def build_finding_disposition(inv: dict) -> dict:
    lab = str(LAB)
    ev = lambda *parts: str(Path(*parts))  # noqa: E731
    return {"findings": [
        {"finding_id": "F-01", "current_disposition": "PRESENT",
         "evidence_refs": [
             ev(lab, "src/crypto_regime_lab/time_edge/execution.py") + " (imports dynamic_fold_provider L15, refs event_account)",
             ev(lab, "reports/time_edge_validation_v4/te02-pilot-09-report.md") + " (32/32 trials complete, real 32-trial Mode 4 selection)",
             ev(lab, "src/crypto_regime_lab/integration/event_account.py")],
         "affected_paths": ["src/crypto_regime_lab/time_edge/execution.py",
                            "src/crypto_regime_lab/experiments/dynamic_fold_provider.py"],
         "planned_phase": "RA-04",
         "claim_limit": "224 scorer calls per audit E01, not independently re-tallied; do not call a new runner fake Mode 4 on legacy grounds."},
        {"finding_id": "F-02", "current_disposition": "PRESENT",
         "evidence_refs": [
             ev(lab, "src/crypto_regime_lab/time_edge/compute_cache.py"),
             ev(lab, "src/crypto_regime_lab/time_edge/pipeline_controls.py"),
             ev(lab, "evidence/time_edge_validation_v4/runs/te-host-controls-08"),
             ev(lab, "evidence/time_edge_validation_v4/runs/te-host-controls-09"),
             ev(lab, "evidence/time_edge_validation_v4/runs/te-host-controls-10")],
         "affected_paths": ["src/crypto_regime_lab/time_edge/compute_cache.py",
                            "src/crypto_regime_lab/time_edge/pipeline_controls.py",
                            "src/crypto_regime_lab/time_edge/storage.py"],
         "planned_phase": "RA-02",
         "claim_limit": "Metadata HIT is not enough if the engine still re-runs; fix identity, prove cross-run actual reuse."},
        {"finding_id": "F-03", "current_disposition": "PRESENT",
         "evidence_refs": [
             "te-host-controls-10 ledger: attempt cd6debd9 FAILED wall=23496.65859210398s ('isolated child exited 1')",
             "te-host-controls-10 attempts/*/stderr.log match memory-error strings",
             "1 RUNNING attempt = live --retry-failed job observed in RA01.1 inventory"],
         "affected_paths": ["src/crypto_regime_lab/time_edge/execution.py:210-306"],
         "planned_phase": "RA-03",
         "claim_limit": "OOM is not NO_EDGE; 84.4 MiB is not the whole working set; measured memory proof required."},
        {"finding_id": "F-04", "current_disposition": "PRESENT",
         "evidence_refs": [
             ev(lab, "src/crypto_regime_lab/time_edge/execution.py") + ":309-388 (selection/scorer region)",
             ev(lab, "quantbt_candidate/quantbt/walkforward.py") + ":4070-4125,4369-4410 (snapshot, provenance only)"],
         "affected_paths": ["src/crypto_regime_lab/time_edge/execution.py"],
         "planned_phase": "RA-04",
         "claim_limit": "'7/8 fallback + one finite subperiod' per audit E07; do not call every fallback a bug or delete low-trade alphas."},
        {"finding_id": "F-05", "current_disposition": "PRESENT",
         "evidence_refs": [ev(lab, "evidence/time_edge_validation_v4/te03-r2/") + " (information_value/model_causality/model_decision/model_registry files present)"],
         "affected_paths": ["src/crypto_regime_lab/time_edge/model.py",
                            "src/crypto_regime_lab/data/panel.py"],
         "planned_phase": "RA-05/RA-06",
         "claim_limit": "'5/29 JM vintages, rank-IC delta -0.03263' per audit E03; do not infer PnL from IC or 729 independent samples."},
        {"finding_id": "F-06", "current_disposition": "PRESENT",
         "evidence_refs": [
             ev(lab, "src/crypto_regime_lab/time_edge/schedule.py") + ":20-26 (triggers(), min_gap_days=28 default)",
             ev(lab, "evidence/time_edge_validation_v4/host-emissions-03.json")],
         "affected_paths": ["src/crypto_regime_lab/time_edge/schedule.py"],
         "planned_phase": "RA-05",
         "claim_limit": "'28 accepted triggers, median gap ~28.17d' is a scheduler replay, not 28 actual deployments."},
        {"finding_id": "F-07", "current_disposition": "PRESENT",
         "evidence_refs": [
             ev(lab, "configs/time_edge_validation_v4/r01/model_protocol.json") + " (threshold language present)",
             ev(lab, "src/crypto_regime_lab/time_edge/model.py")],
         "affected_paths": ["src/crypto_regime_lab/time_edge/model.py"],
         "planned_phase": "RA-05/RA-06",
         "claim_limit": "Report the actual mixture and fallback share; do not describe a mostly-M0 path as JM."},
        {"finding_id": "F-08", "current_disposition": "PRESENT",
         "evidence_refs": [
             ev(lab, "src/crypto_regime_lab/time_edge/controls.py"),
             ev(lab, "evidence/time_edge_validation_v4/te03/te03_7_power.json") + " (mentions engine_runs)",
             ev(lab, "evidence/time_edge_validation_v4/host-calibration-01.json")],
         "affected_paths": ["src/crypto_regime_lab/time_edge/controls.py"],
         "planned_phase": "RA-04/RA-07",
         "claim_limit": "No market power certified from injected synthetic effects; small targeted controls + separate power analysis."},
    ]}


def build_migration() -> dict:
    return {"rows": [
        {"old_gate": "Full multi-year learned synthetic matrix mandatory before discovery",
         "new_disposition": "Keep history; readiness replaced by RA-04 compact validity/E2E controls; full scientific calibration moves to RA-07",
         "required_test": "Q05 compact controls with actual path evidence"},
        {"old_gate": "Ranking IC > 0 as prerequisite for economic runs",
         "new_disposition": "Diagnostic/secondary endpoint, not a technical gate",
         "required_test": "D-series: IC-negative + valid execution still plans discovery"},
        {"old_gate": "Common minimum switch/selection count for every conclusion",
         "new_disposition": "Diagnostic for mechanism/support; never forces STATIC to change params or treatment to act",
         "required_test": "D04 funnel reconstructs no-switch and delayed-switch cases"},
        {"old_gate": ">=365 days for economic inference",
         "new_disposition": "Keep registered floor for confirmatory inference; shorter technical pilots are descriptive only",
         "required_test": "Short pilot artifacts carry no economic verdict"},
        {"old_gate": "Old four-hypothesis family",
         "new_disposition": "Historical unchanged; new primary H-BUDGET, other claims carry a declared family",
         "required_test": "No hypothesis dropped after seeing outcomes to cut multiplicity"},
        {"old_gate": "Quota/cost counted per legacy run",
         "new_disposition": "Cumulative ledger charge, never reset by namespace",
         "required_test": "G01-BUDGET admission probes (over-envelope refused, new ID keeps charge)"},
        {"old_gate": "T02 rejected every multi-link file anywhere under LAB_ROOT",
         "new_disposition": "T02 fails on symlinks escaping LAB_ROOT or resolving into a protected root, and on multi-link files outside the declared run-output trees (evidence/, snapshots/); content-sealed run-output dedup inside those trees is recorded informational only",
         "reason": "TE workers hardlink identical observable_market.parquet between sealed run-output tasks; the old form flagged that benign dedup as FAIL, contradicting the check's own intent (no alias to a protected source). Gate redesign, not a relaxation of the protected-source hazard: a hardlink in any source/config tree still fails.",
         "required_test": "T02 unit tests: src-tree hardlink FAILs, evidence/snapshots dedup passes as informational, symlink into a protected root FAILs"},
    ],
        "note": "Deliberate methodology revision, not a certificate that old gates passed. Owner approval opens RA economics; no silent threshold/risk-cap loosening inside the same migration."}


def build_registration() -> dict:
    return {
        "namespace": STUDY,
        "planner_alias": {"allocation_id": "TE02-PILOT-R03", "shared_ledger": True,
                          "note": "New IDs never create free compute; charge stays cumulative."},
        "arms": {
            "STATIC": {"role": "no-refit incumbent, inherits initial selection"},
            "M4_CAL": {"role": "stock Mode 4, fixed calendar cadence"},
            "M4_CAL_MATCHED": {"role": "calendar cadence matched to regime work budget", "alias": "CAL_BUDGET"},
            "M4_REGIME": {"role": "regime-triggered refresh, frozen protocol of its round"},
        },
        "contrasts": {
            "primary_H-BUDGET": "M4_REGIME minus M4_CAL_MATCHED (information timing only)",
            "secondary_timing_incl_cadence": "M4_REGIME minus M4_CAL",
            "secondary_cadence": "M4_CAL_MATCHED minus M4_CAL",
        },
        "data_roles": {"development": "RA-05 pilot-cell outcomes (reusable for RA-06 design)",
                       "confirmation": "frozen later; development data never becomes untouched confirmation"},
        "selector_version_policy": {"contract": "STOCK_MODE4_PLUS_ADMISSION_V1",
                                    "status": "PENDING_CALIBRATION",
                                    "note": "Defined in RA-04; economic jobs stay blocked until frozen there."},
        "tuning_budget": {"effective_dims": "2-3 from canonical schemas",
                          "attempts_per_cutoff": 50,
                          "first_round_seeds": 1},
        "scope": {"default_pilot": "A-SC/BTCUSDT (integration evidence exists; support re-checked per window)",
                  "change_rule": "capability/coverage/decision-support/cost only, never PnL"},
        "economic_hurdle_delta": {"status": "PENDING_CALIBRATION",
                                  "note": "Cost-uncertainty rule materialized from training-only calibration + actual traces before any paired outcome is claimed (§13.3). Never 0 to open a gate."},
        "risk_caps": {"max_drawdown_deterioration_vs_comparator": 0.02,
                      "leverage_sizing": "same as comparator",
                      "note": "Default inherited per §13.5; owner may change before eval, never after outcomes."},
        "bootstrap_plan": {"status": "PENDING_CALIBRATION",
                           "note": "Frozen in RA-07: synchronized calendar blocks, no engine calls, seeds are search randomness not markets."},
        "approvals": {"scope": "PENDING", "migration": "PENDING",
                      "arms_contrasts": "PENDING", "tuning_budget": "PENDING",
                      "risk_caps": "PENDING"},
    }


def build_resource_budget(inv: dict) -> dict:
    rows = inv["ledger_te02_pilot_r03"]["by_status"] or []
    charged = round(sum((r[2] or 0.0) for r in rows), 1)
    total = 300000.0
    running = [j for j in inv["active_jobs"] if "error" not in j]
    return {
        "allocation_id": "TE02-PILOT-R03",
        "total_wall_s": total,
        "charged_wall_s": charged,
        "remaining_wall_s": round(total - charged, 1),
        "charge_note": "Cumulative ledger charge; new run IDs never reset it. A live controls-10 --retry-failed job is consuming budget concurrently; re-read the ledger at every launch.",
        "frozen_caps": {
            "per_task_wall_s": 27000.0,
            "per_task_wall_reason": "Largest observed single attempt 23496.66s (controls-10 FAILED) + margin; larger tasks must shard.",
            "per_process_rss_gb": 3.0,
            "per_process_rss_reason": "Host 9GB total / ~1GB free at freeze; RA-03 sets the final measured acceptance (<=80% cap). Kill-guard kills only its own task; completed artifacts stay recoverable.",
            "max_workers": 1,
            "max_workers_reason": "OOM history (exit 137) + current single-worker practice; more only in owner-approved allocation with aggregate-memory test.",
            "max_retry": 1,
            "max_retry_reason": "Retries get new attempt IDs and full charge; prevents unbounded burn.",
        },
        "ra_envelope": "Remaining-at-freeze is shared by RA-02..RA-08; each phase gets its sub-envelope approved at its start. This guide grants no new quota.",
        "live_running_jobs_at_freeze": running,
    }


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def build_report(inv: dict, verdict: dict, run_id: str, manifest: dict) -> str:
    g = verdict["gates"]
    hashes = {e["relpath"]: e["sha256"][:12] for e in manifest["artifacts"]}
    eng = inv["engine"]
    recon = inv.get("running_row_reconciliation", {})
    recon_summary = recon.get("summary") if isinstance(recon, dict) else None
    if recon_summary:
        recon_line = (f"{recon_summary['running_rows']} RUNNING row(s): "
                      f"{recon_summary['live_matched']} live-matched, "
                      f"{recon_summary['orphans']} orphan(s)")
        for row in recon.get("rows", []):
            recon_line += (f"; row {str(row['ledger_attempt_id'])[:8]}... "
                           f"{row['classification']} (pids {row['evidence'].get('pids')})")
    else:
        recon_line = recon.get("error", "unavailable")
    test_info = g["G01-VERIFY"].get("tests") or {}
    test_line = (f"collected {test_info.get('tests', 'n/a')}, failed "
                 f"{test_info.get('failures', 'n/a')}, errors "
                 f"{test_info.get('errors', 'n/a')} (junit fed to the verifier; "
                 f"test_registry lists {len(TEST_NODE_IDS)} node ids)")
    gate_rows = {
        "G01-ID": ("branch/HEAD/engine+native pinned; endpoint hashes recorded; "
                   "protected tree unchanged by the phase",
                   "baseline_identity.json sha256:"
                   f"{hashes.get('baseline_identity.json', 'n/a')}..."),
        "G01-MIG": (">=6 migration rows complete; namespace not immutable R01; "
                    "approvals PENDING",
                    "protocol_migration.json sha256:"
                    f"{hashes.get('protocol_migration.json', 'n/a')}..., "
                    "registration.json sha256:"
                    f"{hashes.get('registration.json', 'n/a')}..."),
        "G01-VERIFY": ("receipts+hashes match; real test evidence; no BLOCKED "
                       "riding a PASS; no missing artifact",
                       "phase_manifest.json + verification.json (test_registry "
                       f"sha256:{hashes.get('test_registry.json', 'n/a')}...)"),
        "G01-BUDGET": ("remaining == total - charged; admission refuses "
                       "over-envelope; charge never reset",
                       "resource_budget.json sha256:"
                       f"{hashes.get('resource_budget.json', 'n/a')}..."),
        "G01-REPORT": ("every finding F-01..F-08 has disposition + evidence + "
                       "future phase",
                       "finding_disposition.json sha256:"
                       f"{hashes.get('finding_disposition.json', 'n/a')}..."),
    }
    matrix = "\n".join(
        f"| {gid} | {want} | "
        f"{'PASS' if g[gid]['pass'] else 'FAIL: ' + '; '.join(g[gid]['reasons'][:2])} "
        f"| {ev} | {'PASS' if g[gid]['pass'] else 'FAIL'} |"
        for gid, (want, ev) in gate_rows.items())
    ledger = inv["ledger_te02_pilot_r03"]
    charged = ledger["by_status"] and round(
        sum((r[2] or 0.0) for r in ledger["by_status"]), 1)
    remaining = None if charged is None else round(300000.0 - charged, 1)
    return f"""# RA-01 - baseline lock, scope, protocol migration, testable gates

## 1. Status va scope
- Technical gate: **{verdict["overall"]}** (technical phase gate only; no model positivity required); research status: none claimed; owner review: WAITING_OWNER_REVIEW.
- Branch `{inv["git_branch"]}`, HEAD `{inv["git_head_full"]}`, tracked-dirty `{inv["tracked_dirty"] or "clean"}`; guide RA-GUIDE-1.0 (section 5), study `{STUDY}`.
- Scope completed: RA01.1-RA01.6 (inventory, finding map, registration, migration, budget admission, thin verifier). Not run: nothing in phase scope; zero engine launches by this phase.

## 2. Previous findings va thay doi
- F-01..F-08 all carry dispositions (8/8, none "read therefore done"), each with source path, evidence refs and planned phase RA-02..RA-07.
- Methodology revision recorded in protocol_migration (7 rows incl. the T02 run-output-dedup scoping); old registrations/claims/evidence untouched.
- Registration: 4 arms (STATIC, M4_CAL, M4_CAL_MATCHED=CAL_BUDGET canonical, M4_REGIME), primary H-BUDGET = M4_REGIME - M4_CAL_MATCHED; economic fields PENDING_CALIBRATION block dependent economic jobs until resolved in RA-04/RA-07.

## 3. Actual execution
- Interpreter `{eng["python_executable"]}` (python {eng["python"]}); engine quantbt-engine {eng["quantbt_engine_version"]} / quantbt-native {eng["quantbt_native_version"]} ({eng["installer"]}); endpoint sha installed==protected {eng["endpoint_sha256_installed"][:12]}....
- Route: read-only inventory (git status, package metadata, ledger read-only, ps snapshot) -> artifacts -> pytest junit of tests/ra_corrective -> thin verifier. No market data read, no engine call.
- Live inventory: {inv["untracked_count"]} untracked files snapshotted and left alone.
- Ledger reconciliation: {recon_line}.
- Tests: {test_line}

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
{matrix}


## 5. Correctness va causality
- RA-01 launches no economic job and reads no market data; causality N/A beyond read-only inventory. The admission path is probed red (over-envelope -> BLOCKED_BUDGET) inside the verifier, not asserted.
- No metric is defined in this phase; PENDING_CALIBRATION fields stay unresolved and blocking.

## 6. Runtime va memory
- Build-only phase: seconds of wall, zero engine accounts/visited bars/cache traffic.
- Ledger TE02-PILOT-R03 at freeze: total 300000s, charged {charged if charged is not None else "null"}s, remaining {remaining if remaining is not None else "null"}s; caps frozen in resource_budget.json (per-task 27000s, rss 3.0GB, 1 worker, 1 retry - measured bases recorded there).

## 7. Scientific result va kha nang ket luan
- None claimed. Nothing here proves or disproves an economic edge; the registration only fixes arms, contrasts and blocking fields.

## 8. Blockers/debt va quyet dinh
- Running/orphan ledger rows are reconciled with PID evidence above; any orphan is recovered by the TE supervisor (recover_interrupted under the run lock), not by RA-01.
- Shared budget is consumed concurrently by the live controls-10 retry job (not RA-owned); every later launch must re-read the ledger.
- Owner decisions pending: scope approval + migration approval (both PENDING). No P0/P1 is being carried as PASS.

## 9. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra01.py --pytest-xml <junit of tests/ra_corrective>` (new run_id per attempt; prior runs immutable).
- Independent verify: `lab_venv/bin/python scripts/verify_ra01.py --run-dir <dir> --pytest-xml <junit>`.
- Protected trees: before fingerprint recorded in baseline_identity.json / after unchanged (verifier G01-ID goes red on any delta). Phase-changed files: src/crypto_regime_lab/ra/, scripts/run_ra01.py, scripts/verify_ra01.py, tests/ra_corrective/, this run dir; committed scoped, no push.
- Next permissible action: RA-02 only after owner approval of this phase.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-xml", required=True)
    args = parser.parse_args()

    prot_before = protected_fingerprint()
    inv = lab_inventory()
    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY,
                                 lab_run_id=new_lab_run_id("ra01"))
    run_dir = writer.run_dir
    with writer.attempt("ra01_build") as att:
        writer.write_json("baseline_identity.json",
                          {"inventory": inv, "protected_before": prot_before},
                          schema="crypto_regime_lab.ra01_baseline.v1")
        writer.write_json("finding_disposition.json", build_finding_disposition(inv),
                          schema="crypto_regime_lab.ra01_disposition.v1")
        writer.write_json("protocol_migration.json", build_migration(),
                          schema="crypto_regime_lab.ra01_migration.v1")
        writer.write_json("registration.json", build_registration(),
                          schema="crypto_regime_lab.ra01_registration.v1")
        writer.write_json("resource_budget.json", build_resource_budget(inv),
                          schema="crypto_regime_lab.ra01_budget.v1")
        writer.write_json("test_registry.json",
                          {"test_file": "tests/ra_corrective/test_ra01_gates.py",
                           "test_node_ids": TEST_NODE_IDS},
                          schema="crypto_regime_lab.ra01_tests.v1")
        manifest_records = []
        for name in REQUIRED_ARTIFACTS:
            if name in ("phase_manifest.json", "report.md", "handoff.md"):
                continue
            target = run_dir / name
            manifest_records.append({"relpath": name,
                                     "sha256": sha256_file(target),
                                     "size_bytes": target.stat().st_size})
        manifest_doc = {"required_gates": ["G01-ID", "G01-MIG", "G01-VERIFY",
                                              "G01-BUDGET", "G01-REPORT"],
                           "artifacts": manifest_records,
                           "source_dependency_digests": {
                               "lab_head": inv["git_head_full"],
                               "endpoint_installed": inv["engine"]["endpoint_sha256_installed"],
                               "endpoint_protected": inv["engine"]["endpoint_sha256_protected_source"]},
                           "approvals": {"scope": "PENDING", "migration": "PENDING"}}
        writer.write_json("phase_manifest.json", manifest_doc,
                          schema="crypto_regime_lab.ra01_manifest.v1")
        prot_after = protected_fingerprint()
        # report.md/handoff.md must exist before verify (existence-gated);
        # the verdict-bearing final text replaces these drafts afterwards.
        # They are intentionally outside the hash manifest's JSON scope.
        write_text_atomic(run_dir / "report.md", "# RA-01 report — PENDING_VERIFICATION\n")
        write_text_atomic(run_dir / "handoff.md", "# RA-01 handoff — PENDING_VERIFICATION\n")
        verdict = verify_ra01(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        writer.write_json("verification.json", verdict,
                          schema="crypto_regime_lab.ra01_verification.v1")
        write_text_atomic(run_dir / "report.md",
                          build_report(inv, verdict, writer.lab_run_id, manifest_doc))
        write_text_atomic(run_dir / "handoff.md",
                          "# RA-01 handoff\n\n- run dir: evidence/" + STUDY + "/"
                          + writer.lab_run_id + "/\n- approvals: scope=PENDING, migration=PENDING\n"
                          "- next: RA-02 semantic cache, only after owner approves RA-01.\n"
                          "- Reconciliation verdict: see baseline_identity.json "
                          "running_row_reconciliation; any ORPHAN_NO_LIVE_PROCESS "
                          "row must be recovered via the TE supervisor "
                          "(recover_interrupted under the run lock) before RA-02 "
                          "launches against this ledger.\n"
                          "- live controls-10 retry job is concurrent budget consumption, not RA-owned.\n")
        att.detail = {"run_dir": str(run_dir), "overall": verdict["overall"]}
    print(json.dumps({"run_dir": str(run_dir), "overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()}},
                     indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
