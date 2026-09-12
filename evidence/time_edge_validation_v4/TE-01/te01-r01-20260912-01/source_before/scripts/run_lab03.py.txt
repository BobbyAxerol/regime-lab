#!/usr/bin/env python
"""Run the whole of LAB-03 in dependency order and report the exit gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
PYTHON = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"

STEPS = [
    ("gate    preflight (prerequisite)", ["scripts/preflight.py"]),
    ("L03.1-2 inventory + frozen snapshot", ["scripts/snapshot_data.py"]),
    ("L03.3-6 availability, features, cohorts", ["scripts/build_feature_panels.py"]),
    ("L03.7   market adapter qualification", ["scripts/qualify_market_adapters.py"]),
    ("close   LAB-01 open blockers", ["scripts/close_lab01_blockers.py"]),
    ("report  data_eligibility.md", ["scripts/write_data_eligibility_md.py"]),
]


def main() -> int:
    failures: list[str] = []
    for title, argv in STEPS:
        print(f"\n=== {title} ===")
        done = subprocess.run([str(PYTHON), *argv], cwd=LAB_ROOT, capture_output=True,
                              text=True, timeout=5400)
        for line in [ln for ln in done.stdout.strip().splitlines() if ln][-7:]:
            print(f"    {line}")
        if done.returncode != 0:
            failures.append(title)
            print(f"    FAILED rc={done.returncode}\n    {done.stderr.strip()[-700:]}")
            break

    print("\n=== acceptance tests ===")
    tests = subprocess.run([str(PYTHON), "-m", "pytest", "tests", "-q"], cwd=LAB_ROOT,
                           capture_output=True, text=True, timeout=3600)
    summary = [ln for ln in tests.stdout.strip().splitlines() if "passed" in ln or "failed" in ln]
    print(f"    {summary[-1] if summary else 'no pytest summary'}")
    if tests.returncode != 0:
        failures.append("acceptance tests")

    print("\n=== LAB-03 exit ===")
    if failures:
        print(f"    STATUS = FAILED ({', '.join(failures)})")
        return 1
    print("    STATUS = PASS")
    print("    server-core cohort: 5 symbols with explicit coverage and publication assumptions")
    print("    funding = MISSING (never zero); spot = BTCUSDT only; derivatives = BTC/ETH only")
    print("    LAB-01 blockers closed: data_roles, instrument_registry_digest, minimum_economic_effect")
    print("    no external API is needed to continue the primary study")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
