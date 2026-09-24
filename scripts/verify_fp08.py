#!/usr/bin/env python3
"""Thin verifier over one FP-08 run dir (exit 0 iff overall PASS)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp.verifier_fp08 import verify_fp08  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    verdict = verify_fp08(args.run_dir, pytest_xml=args.pytest_xml)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
