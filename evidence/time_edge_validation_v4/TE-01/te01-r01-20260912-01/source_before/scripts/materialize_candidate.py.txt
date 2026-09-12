#!/usr/bin/env python
"""LAB-01 L01.3 (completed): retain the baseline wheel and unpack a candidate copy.

The candidate copy exists so LAB-07 can hold lab-only patches without ever
touching the user's QuantBT repo. Its provenance is the PyPI wheel retained in
vendor_readonly, never /root/bobby/pool_alpha/quantbt.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SafetyViolation, SandboxPolicy, sha256_file  # noqa: E402

BASELINE_WHEELS = ("quantbt_engine-1.1.1-", "quantbt_native-0.4.2-")


def _chmod_tree_writable(root: Path) -> None:
    for path in root.rglob("*"):
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if path.is_dir() else 0))
        except OSError:
            pass


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id="crypto_regime_timeedge_v2")

    wheelhouse = policy.lab_root / "wheelhouse"
    dist_dir = policy.resolve_write_target(policy.lab_root / "vendor_readonly" / "quantbt_1_1_1_dist")
    dist_dir.mkdir(parents=True, exist_ok=True)

    with writer.attempt("L01.3.retain_baseline_wheels") as att:
        retained = []
        for prefix in BASELINE_WHEELS:
            matches = sorted(wheelhouse.glob(prefix + "*"))
            if not matches:
                raise SafetyViolation(f"baseline wheel {prefix}* not present in wheelhouse")
            for wheel in matches:
                target = dist_dir / wheel.name
                if target.exists():
                    os.chmod(target, stat.S_IWUSR | stat.S_IRUSR)
                shutil.copyfile(wheel, target)
                digest = sha256_file(target)
                if digest != sha256_file(wheel):
                    raise SafetyViolation(f"retained wheel {wheel.name} differs from source")
                os.chmod(target, 0o444)
                retained.append({"name": wheel.name, "sha256": digest, "size_bytes": target.stat().st_size})
        att.detail = {"wheels": [r["name"] for r in retained]}

    with writer.attempt("L01.3.unpack_candidate") as att:
        candidate = policy.resolve_write_target(policy.lab_root / "quantbt_candidate")
        if candidate.exists():
            _chmod_tree_writable(candidate)
            shutil.rmtree(candidate)
        candidate.mkdir(parents=True, exist_ok=True)
        core_wheel = next(p for p in dist_dir.glob("quantbt_engine-1.1.1-*.whl"))
        with zipfile.ZipFile(core_wheel) as zf:
            for info in zf.infolist():
                name = info.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    raise SafetyViolation(f"unsafe wheel member {name}")
                policy.resolve_write_target(candidate / name)
            zf.extractall(candidate)
        py_files = sorted(candidate.rglob("*.py"))
        att.detail = {"wheel": core_wheel.name, "python_files": len(py_files)}

    # Provenance guard: nothing in the candidate copy may be a link into a
    # protected tree, and nothing may carry a path from the user's repo.
    aliases = [str(p) for p in candidate.rglob("*") if p.is_symlink()]
    hardlinks = [str(p) for p in candidate.rglob("*") if p.is_file() and p.stat().st_nlink > 1]
    if aliases or hardlinks:
        raise SafetyViolation(f"candidate copy contains aliases: symlinks={aliases[:3]} hardlinks={hardlinks[:3]}")

    report = {
        "retained_wheels": retained,
        "candidate_dir": str(candidate),
        "candidate_python_files": len(py_files),
        "candidate_provenance": "unpacked from the retained PyPI wheel in vendor_readonly/quantbt_1_1_1_dist",
        "candidate_is_not_from_protected_tree": True,
        "protected_tree_not_read_for_this_step": "/root/bobby/pool_alpha/quantbt",
        "symlinks": aliases,
        "hardlinks": hardlinks,
        "usage": "LAB-07 lab-only patches live here; the baseline install in environments/lab_venv stays unmodified",
    }
    art = writer.write_json("candidate_materialization.json", report,
                            schema="crypto_regime_lab.candidate_materialization.v1")
    print(f"retained wheels     : {[r['name'] for r in retained]}")
    print(f"candidate py files  : {len(py_files)}")
    print(f"aliases in candidate: symlinks={len(aliases)} hardlinks={len(hardlinks)}")
    print(f"evidence -> {art['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
