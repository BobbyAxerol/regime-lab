#!/usr/bin/env python
"""Run the Appendix B probe suite INSIDE the bubblewrap sandbox.

Probes execute original alpha source through the AST harness, so they are the
first LAB-02 step that runs untrusted code. Guide L01.3 requires containment for
exactly this, and the lab's own rule is that anything touching alpha execution
goes through ``safety.sandbox``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.sandbox import probe_isolation, run_isolated  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    isolation = probe_isolation(policy)
    if not isolation.available:
        report = {"status": "BLOCKED", "reason": "OS-level isolation unavailable",
                  "failures": isolation.failures,
                  "policy": "alpha source is not executed without containment (guide L01.3)"}
        writer.write_json("appendix_b_probes_sandboxed.json", report,
                          schema="crypto_regime_lab.probes_sandboxed.v1")
        print(json.dumps(report, indent=2))
        return 1

    python = policy.lab_root / "environments" / "lab_venv" / "bin" / "python"
    worker = policy.lab_root / "scripts" / "_probe_worker.py"
    with writer.attempt("L02.1.probes_sandboxed") as att:
        completed = run_isolated(policy, [str(python), str(worker), str(policy.lab_root)],
                                 network=False, timeout_s=600)
        if completed.returncode != 0:
            raise RuntimeError(f"probe worker exited {completed.returncode}: "
                               f"{completed.stderr.strip()[-600:]}")
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        att.detail = {"confirmed": payload["confirmed_count"], "total": payload["probe_count"]}

    payload["execution_context"] = {
        "contained": True,
        "mechanism": isolation.mechanism,
        "network_blocked": isolation.checks.get("network_blocked"),
        "protected_roots_read_only": all(
            m.get("read_only") for m in isolation.checks.get("protected_mounts", {}).values()),
        "note": "alpha source functions were executed inside the sandbox, never in the orchestrator",
    }
    writer.write_json("appendix_b_probes_sandboxed.json", payload,
                      schema="crypto_regime_lab.probes_sandboxed.v1")
    print(f"contained probes : {payload['confirmed_count']}/{payload['probe_count']} CONFIRMED")
    print(f"network blocked  : {payload['execution_context']['network_blocked']}")
    print(f"protected ro     : {payload['execution_context']['protected_roots_read_only']}")
    print(f"evidence -> {writer.run_dir}/appendix_b_probes_sandboxed.json")
    return 0 if payload["confirmed_count"] == payload["probe_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
