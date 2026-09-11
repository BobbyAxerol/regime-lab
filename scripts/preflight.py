#!/usr/bin/env python
"""LAB-01 preflight gate. Runs T01-T08 and writes the result as evidence.

Exit code 0 only when every check is PASS. BLOCKED is never treated as PASS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, environment_fingerprint  # noqa: E402
from crypto_regime_lab.safety.checks import run_all  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight safety gate (LAB-01)")
    parser.add_argument("--lab-root", default=str(LAB_ROOT))
    parser.add_argument("--study-id", default="crypto_regime_timeedge_v2")
    args = parser.parse_args()

    policy = SandboxPolicy.load(Path(args.lab_root) / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=args.study_id)

    with writer.attempt("L01.preflight") as att:
        report = run_all(policy)
        att.detail = {"gate": report["gate"], "counts": report["counts"]}

    report["os_level_isolation_declared_in_policy"] = policy.raw.get("os_level_isolation", {})
    report["safe_to_run_synthetic"] = bool(report["gate"] == "PASS")
    report["safe_to_run_market_execution"] = False
    report["market_execution_note"] = (
        "Market execution stays disabled at LAB-01 exit by design (guide LAB-01 exit gate). "
        "It is unlocked only after LAB-02 adapter certification and LAB-03 data qualification."
    )
    report["environment"] = environment_fingerprint()
    writer.write_json("preflight_report.json", report, schema="crypto_regime_lab.preflight.v1")

    for row in report["results"]:
        print(f"  {row['id']}  {row['status']:<8} {row['title']}")
    print(f"\ngate = {report['gate']}   counts = {json.dumps(report['counts'])}")
    print(f"SAFE_TO_RUN_SYNTHETIC = {report['safe_to_run_synthetic']}")
    print(f"OS_ISOLATION          = {report['os_isolation_available']}")
    print(f"containment           = {report['containment_claim']}")
    print(f"evidence -> {writer.run_dir}/preflight_report.json")
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
