#!/usr/bin/env python
"""LAB-01 L01.3 (completed): dependency lock, compiler/thread metadata,
native capability probe, and proof that baseline and candidate run as
separate processes with separate import origins.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, environment_fingerprint  # noqa: E402
from crypto_regime_lab.quantbt_bridge.capabilities import InstalledQuantBT, probe_native_capability  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.safety.process import become_process_group_leader  # noqa: E402
from crypto_regime_lab.safety.sandbox import run_isolated_python  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"

IDENTITY_SNIPPET = """
import importlib, importlib.metadata as md, json, sys, os
mod = importlib.import_module("quantbt")
print(json.dumps({
    "pid": os.getpid(),
    "sys_path_head": sys.path[0],
    "quantbt_file": getattr(mod, "__file__", None),
    "quantbt_version_attr": getattr(mod, "__version__", None),
    "dist_version": md.version("quantbt-engine"),
}))
"""


def build_lockfile(policy: SandboxPolicy) -> dict:
    """pip --require-hashes lockfile pinned to the retained wheelhouse artifacts."""
    venv_pip = policy.lab_root / "environments" / "lab_venv" / "bin" / "pip"
    frozen = subprocess.run([str(venv_pip), "freeze", "--all"], capture_output=True, text=True, timeout=120)
    installed: dict[str, str] = {}
    for line in frozen.stdout.splitlines():
        if "==" in line and not line.startswith("-"):
            name, _, version = line.partition("==")
            installed[name.strip()] = version.strip()

    wheelhouse = policy.lab_root / "wheelhouse"
    artifacts: dict[str, dict] = {}
    for artifact in sorted(wheelhouse.iterdir()):
        if artifact.is_file():
            artifacts[artifact.name] = {
                "sha256": sha256_file(artifact),
                "size_bytes": artifact.stat().st_size,
            }

    def norm(name: str) -> str:
        return name.lower().replace("_", "-")

    matched: dict[str, list[str]] = {}
    for filename in artifacts:
        stem = filename.split("-")[0]
        matched.setdefault(norm(stem), []).append(filename)

    lines = [
        "# crypto_regime_lab environment lock (LAB-01 L01.3)",
        "# Generated from the retained wheelhouse; install with:",
        "#   pip install --no-index --find-links wheelhouse --require-hashes -r configs/requirements.lock",
        "# A package with no local artifact is listed as UNPINNED_LOCAL_ARTIFACT and must be",
        "# resolved before any confirmation run (guide L01.3 'dependency lock').",
        "",
    ]
    unpinned: list[str] = []
    for name in sorted(installed):
        version = installed[name]
        files = matched.get(norm(name), [])
        if not files:
            unpinned.append(name)
            lines.append(f"# UNPINNED_LOCAL_ARTIFACT {name}=={version}")
            continue
        hashes = " ".join(f"--hash=sha256:{artifacts[f]['sha256']}" for f in sorted(files))
        lines.append(f"{name}=={version} {hashes}")

    lock_text = "\n".join(lines) + "\n"
    lock_path = policy.resolve_write_target(policy.lab_root / "configs" / "requirements.lock")
    lock_path.write_text(lock_text, encoding="utf-8")
    return {
        "lockfile": str(lock_path),
        "lockfile_sha256": sha256_file(lock_path),
        "installed_package_count": len(installed),
        "wheelhouse_artifact_count": len(artifacts),
        "unpinned_packages": unpinned,
        "fully_pinned": not unpinned,
        "artifacts": artifacts,
        "installed": installed,
    }


def prove_process_separation(policy: SandboxPolicy) -> dict:
    """Baseline and candidate must import different files in different processes."""
    baseline = run_isolated_python(policy, IDENTITY_SNIPPET, timeout_s=120)
    candidate_prelude = (
        "import sys\n"
        f"sys.path.insert(0, {str(policy.lab_root / 'quantbt_candidate')!r})\n"
    )
    candidate = run_isolated_python(policy, candidate_prelude + IDENTITY_SNIPPET, timeout_s=120)

    def parse(completed) -> dict:
        if completed.returncode != 0:
            return {"status": "FAILED", "rc": completed.returncode, "stderr": completed.stderr[-400:]}
        return {"status": "OK", **json.loads(completed.stdout.strip().splitlines()[-1])}

    base_rec, cand_rec = parse(baseline), parse(candidate)
    # Each worker gets its OWN pid namespace, so both legitimately report a low
    # pid. Equal low pids are evidence of namespace separation, not of sharing.
    pid_namespace_isolated = (
        isinstance(base_rec.get("pid"), int) and isinstance(cand_rec.get("pid"), int)
        and base_rec["pid"] <= 5 and cand_rec["pid"] <= 5
    )
    both_ok = base_rec.get("status") == "OK" and cand_rec.get("status") == "OK"
    different_origins = (
        base_rec.get("quantbt_file") and cand_rec.get("quantbt_file")
        and base_rec["quantbt_file"] != cand_rec["quantbt_file"]
    )
    candidate_from_lab_copy = bool(
        cand_rec.get("quantbt_file", "").startswith(str(policy.lab_root / "quantbt_candidate"))
    )
    baseline_from_venv = bool(
        base_rec.get("quantbt_file", "").startswith(str(policy.lab_root / "environments" / "lab_venv"))
    )
    neither_from_protected = not any(
        str(protected) in (base_rec.get("quantbt_file") or "") + (cand_rec.get("quantbt_file") or "")
        for protected in policy.protected_roots
    )
    return {
        "baseline": base_rec,
        "candidate": cand_rec,
        "separate_subprocess_invocations": both_ok,
        "pid_namespace_isolated": pid_namespace_isolated,
        "pid_note": "both workers report a low pid because each has its own pid namespace; that is isolation, not process sharing",
        "different_import_origins": bool(different_origins),
        "baseline_from_lab_venv": baseline_from_venv,
        "candidate_from_lab_copy": candidate_from_lab_copy,
        "neither_imports_from_a_protected_root": neither_from_protected,
        "status": "SEPARATED" if (both_ok and pid_namespace_isolated and different_origins
                                  and candidate_from_lab_copy and baseline_from_venv
                                  and neither_from_protected) else "NOT_SEPARATED",
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    group = become_process_group_leader()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    with writer.attempt("L01.3.dependency_lock") as att:
        lock = build_lockfile(policy)
        att.detail = {"fully_pinned": lock["fully_pinned"], "unpinned": lock["unpinned_packages"]}

    with writer.attempt("L01.3.native_capability_probe") as att:
        installed = InstalledQuantBT.load()
        native = probe_native_capability(installed.module)
        att.detail = {"matrix_version": native.get("native_event_capability_matrix_version"),
                      "missing_required": native.get("missing_required_capabilities")}

    with writer.attempt("L01.3.process_separation") as att:
        separation = prove_process_separation(policy)
        att.detail = {"status": separation["status"]}

    report = {
        "process_group": group,
        "dependency_lock": {k: v for k, v in lock.items() if k != "artifacts"},
        "wheelhouse_artifacts": lock["artifacts"],
        "native_capability": native,
        "process_separation": separation,
        "environment": environment_fingerprint(),
        "editable_policy": (
            "Development editable code lives only under LAB_ROOT/src and LAB_ROOT/quantbt_candidate. "
            "The baseline install in environments/lab_venv is never edited, and no editable install "
            "points at a protected root."
        ),
    }
    art = writer.write_json("environment_pin.json", report, schema="crypto_regime_lab.environment_pin.v1")

    print(f"process group          : {group['status']} pgid={group['pgid']}")
    print(f"lockfile fully pinned  : {lock['fully_pinned']} ({lock['installed_package_count']} packages)")
    if lock["unpinned_packages"]:
        print(f"  unpinned             : {lock['unpinned_packages']}")
    print(f"native matrix version  : {native.get('native_event_capability_matrix_version')}")
    print(f"missing required caps  : {native.get('missing_required_capabilities')}")
    print(f"process separation     : {separation['status']}")
    print(f"  baseline origin      : {separation['baseline'].get('quantbt_file')}")
    print(f"  candidate origin     : {separation['candidate'].get('quantbt_file')}")
    print(f"evidence -> {art['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
