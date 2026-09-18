"""Lab CLI (guide 13.5).

Every stage refuses to run when its prerequisites, the lab marker or the sandbox
policy are missing, and no stage is ever stubbed into a fake pass.

A stage becomes available when the phase that delivers it lands, and "landed" is
READ from `configs/lab0N_task_audit.json` rather than hard-coded. The first
version of this file carried a frozen `IMPLEMENTED` set from LAB-01, so after
LAB-02 and LAB-03 shipped, `certify-alphas` and `snapshot-data` were still
answering "the phase has not landed" about phases that had. A refusal that is
true today and false tomorrow is worse than no refusal, because it reads like a
checked fact.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .evidence.manifest import EvidenceWriter, utc_now_iso
from .safety.checks import run_all
from .safety.paths import SafetyViolation, SandboxPolicy, manifest_directory

#: stage -> (phase that delivers it, the audit that proves the phase landed,
#: the script the stage runs). ``runner=None`` means this module implements it.
STAGE_DELIVERY: dict[str, dict] = {
    "preflight": {"phase": "LAB-01", "audit": None, "runner": None},
    "verify-source-integrity": {"phase": "LAB-01", "audit": None, "runner": None},
    "certify-alphas": {"phase": "LAB-02", "audit": "lab02_task_audit.json",
                       "runner": "scripts/certify_alphas.py"},
    "snapshot-data": {"phase": "LAB-03", "audit": "lab03_task_audit.json",
                      "runner": "scripts/snapshot_data.py"},
    "verify-causality": {"phase": "LAB-03 (data) + LAB-05 (model)",
                         "audit": "lab05_task_audit.json",
                         "runner": "scripts/verify_causality.py"},
    "run": {"phase": "LAB-08 (discovery) / LAB-09 (confirmation)",
            "audit": "lab08_task_audit.json",
            "runner": "scripts/run_lab08_factorial.py"},
    "freeze": {"phase": "LAB-08", "audit": "lab08_task_audit.json",
               "runner": "scripts/freeze_lab08_protocol.py"},
    "report": {"phase": "LAB-10", "audit": "lab10_task_audit.json", "runner": None},
}
STAGE_PREREQUISITES: dict[str, str] = {k: v["phase"] for k, v in STAGE_DELIVERY.items()}


def _load_policy(lab_root: str | None) -> SandboxPolicy:
    root = Path(lab_root) if lab_root else Path.cwd()
    policy = SandboxPolicy.load(root / "configs" / "sandbox_policy.json") if (root / "configs" / "sandbox_policy.json").is_file() else SandboxPolicy.discover(root)
    policy.assert_lab_root_ok()
    marker = policy.lab_root / ".lab_marker.json"
    if not marker.is_file():
        raise SafetyViolation(f"no .lab_marker.json in {policy.lab_root}; run scripts/bootstrap_lab.py first")
    return policy


def cmd_preflight(args) -> int:
    policy = _load_policy(args.lab_root)
    writer = EvidenceWriter.open(policy, study_id=args.study_id)
    with writer.attempt("cli.preflight") as att:
        report = run_all(policy)
        att.detail = {"gate": report["gate"]}
    report["safe_to_run_synthetic"] = report["gate"] == "PASS"
    report["safe_to_run_market_execution"] = False
    writer.write_json("preflight_report.json", report, schema=report["schema"])
    print(json.dumps({"gate": report["gate"], "counts": report["counts"]}, indent=2))
    return 0 if report["gate"] == "PASS" else 1


def cmd_verify_source_integrity(args) -> int:
    """T08: compare protected sources against the recorded baseline."""
    policy = _load_policy(args.lab_root)
    writer = EvidenceWriter.open(policy, study_id=args.study_id)
    baselines = sorted((policy.lab_root / "evidence").rglob("source_integrity_baseline.json"))
    if not baselines:
        print("NO_BASELINE: run scripts/bootstrap_lab.py first", file=sys.stderr)
        return 1
    recorded = json.loads(baselines[-1].read_text())["manifests"]
    drift = {}
    for root, expected in recorded.items():
        actual = manifest_directory(root, ("*.py",))
        if actual != expected:
            drift[root] = {
                "added": sorted(set(actual) - set(expected)),
                "removed": sorted(set(expected) - set(actual)),
                "changed": sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k]),
            }
    report = {
        "schema": "crypto_regime_lab.source_integrity_report.v1",
        "baseline_artifact": str(baselines[-1]),
        "checked_at_utc": utc_now_iso(),
        "roots_checked": list(recorded),
        "drift": drift,
        "status": "UNCHANGED" if not drift else "EXTERNAL_DRIFT_DETECTED",
    }
    with writer.attempt("cli.verify_source_integrity") as att:
        att.detail = {"status": report["status"]}
    writer.write_json("source_integrity_report.json", report, schema=report["schema"])
    print(json.dumps({"status": report["status"], "drift": drift}, indent=2))
    return 0 if not drift else 1


def _phase_landed(policy: SandboxPolicy, stage: str) -> bool:
    """Did the phase that delivers this stage actually land? Read, not assumed."""
    audit = STAGE_DELIVERY[stage]["audit"]
    return audit is not None and (policy.lab_root / "configs" / audit).is_file()


def cmd_delegate(args, stage: str) -> int:
    """Run the script the landed phase already ships, in the lab's own venv."""
    policy = _load_policy(args.lab_root)
    runner = policy.lab_root / STAGE_DELIVERY[stage]["runner"]
    if not runner.is_file():
        return cmd_unavailable(args, stage, extra={"missing_runner": str(runner)})
    interpreter = policy.lab_root / "environments" / "lab_venv" / "bin" / "python"
    completed = subprocess.run(
        [str(interpreter if interpreter.is_file() else sys.executable), str(runner)],
        cwd=str(policy.lab_root), env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return completed.returncode


def cmd_unavailable(args, stage: str, *, extra: dict | None = None) -> int:
    """Refuse a stage, and say WHICH of the two reasons applies.

    Conflating them is how a stale status survives: "the phase has not landed"
    stays printed long after it did, and nobody re-reads it because it looks
    like a checked fact.
    """
    try:
        landed = _phase_landed(_load_policy(args.lab_root), stage)
    except SafetyViolation:
        landed = False
    payload = {
        "stage": stage,
        "status": "RUNNER_NOT_WIRED_YET" if landed else "PHASE_NOT_LANDED",
        "delivering_phase": STAGE_PREREQUISITES.get(stage, "unknown"),
        "phase_has_landed": landed,
        "note": ("the delivering phase has landed but this stage has no runner wired yet; "
                 "the phase's own script under scripts/ is the current entry point"
                 if landed else
                 "the delivering phase has not landed; the CLI refuses rather than emitting "
                 "a placeholder pass"),
    }
    if extra:
        payload.update(extra)
    print(json.dumps(payload, indent=2), file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m crypto_regime_lab.cli", description="Crypto regime lab CLI")
    parser.add_argument("--lab-root", default=None)
    parser.add_argument("--study-id", default="crypto_regime_timeedge_v2")
    sub = parser.add_subparsers(dest="stage", required=True)
    for stage in STAGE_PREREQUISITES:
        stage_parser = sub.add_parser(stage)
        if stage == "run":
            stage_parser.add_argument("--stage", dest="run_stage", choices=["discovery", "confirmation"], required=True)
        if stage in {"snapshot-data", "verify-causality", "freeze"}:
            stage_parser.add_argument("--study", default=None)
        if stage == "certify-alphas":
            stage_parser.add_argument("--registry", default=None)
        if stage == "report":
            stage_parser.add_argument("--from-artifacts", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.study_id == "time_edge_validation_v4":
        parser.error("time_edge_validation_v4 uses scripts/run_time_edge.py; historical A-E/factorial runners are quarantined for this study")
    if args.stage == "preflight":
        return cmd_preflight(args)
    if args.stage == "verify-source-integrity":
        return cmd_verify_source_integrity(args)
    delivery = STAGE_DELIVERY[args.stage]
    if delivery["runner"] is not None:
        try:
            landed = _phase_landed(_load_policy(args.lab_root), args.stage)
        except SafetyViolation:
            landed = False
        if landed:
            return cmd_delegate(args, args.stage)
    return cmd_unavailable(args, args.stage)


if __name__ == "__main__":
    raise SystemExit(main())
