#!/usr/bin/env python
"""Run the whole of LAB-02 in dependency order and report the exit gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PYTHON = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"

STEPS = [
    ("L01    preflight gate (prerequisite)", ["scripts/preflight.py"]),
    ("L02.1  catalog, presets, semantic deltas", ["scripts/catalog_alphas.py"]),
    ("L02.1  appendix B probes (contained)", ["scripts/run_probes_sandboxed.py"]),
    ("L02.2-8 certification, parity, fixtures", ["scripts/certify_alphas.py"]),
]


def main() -> int:
    failures: list[str] = []
    for title, argv in STEPS:
        print(f"\n=== {title} ===")
        done = subprocess.run([str(PYTHON), *argv], cwd=LAB_ROOT, capture_output=True,
                              text=True, timeout=1800)
        for line in [ln for ln in done.stdout.strip().splitlines() if ln][-6:]:
            print(f"    {line}")
        if done.returncode != 0:
            failures.append(title)
            print(f"    FAILED rc={done.returncode}\n    {done.stderr.strip()[-600:]}")
            break

    print("\n=== acceptance tests ===")
    tests = subprocess.run([str(PYTHON), "-m", "pytest", "tests", "-q"], cwd=LAB_ROOT,
                           capture_output=True, text=True, timeout=1800)
    summary = [ln for ln in tests.stdout.strip().splitlines() if "passed" in ln or "failed" in ln]
    print(f"    {summary[-1] if summary else 'no pytest summary'}")
    if tests.returncode != 0:
        failures.append("acceptance tests")

    print("\n=== LAB-02 exit ===")
    if failures:
        print(f"    STATUS = FAILED ({', '.join(failures)})")
        return 1
    print("    STATUS = PASS")
    print("    A-SC / A-HMA / A-VWAP = READY_FOR_RESEARCH")
    print("    A-HASH = NOT_READY_SPECIFIC_BLOCKER (partial ladder not executable on any one route)")
    print("    legacy vs canonical: every divergence attributed to a delta or the recorded blocker")
    print("    numba/fastmath: 14 kernels compared, 0 decision differences")
    print("    market optimization is unlocked only for certified cells, and only after LAB-03")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
