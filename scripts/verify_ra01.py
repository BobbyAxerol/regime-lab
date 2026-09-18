#!/usr/bin/env python3
"""Verify one RA-01 run directory (RA-GUIDE-1.0 §5 RA01.6, §14.3).

Exit 0 iff every G01 gate passes. A missing input is a FAIL with a named
reason, never an assumption; exit code 0 alone never constitutes evidence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.ra.verifier import verify_ra01  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--pytest-xml", required=True)
    parser.add_argument("--protected-status-file", default=None,
                        help="File holding `git -C ../quantbt status --porcelain` "
                             "taken after the phase; default re-reads it live.")
    args = parser.parse_args()
    if args.protected_status_file:
        protected = Path(args.protected_status_file).read_text()
    else:
        proc = subprocess.run(["git", "status", "--porcelain"],
                              cwd=LAB.parent / "quantbt",
                              capture_output=True, text=True, timeout=60)
        protected = proc.stdout
    verdict = verify_ra01(args.run_dir, pytest_xml=args.pytest_xml,
                          protected_status_after=protected)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
