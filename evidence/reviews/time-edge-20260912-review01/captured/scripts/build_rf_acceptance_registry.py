#!/usr/bin/env python
"""Build configs/rf_acceptance_registry.json from the merged corrective plan.

The corrective study has its own T01..T70 acceptance set. It is registered
separately from the historical T01..T64 registry so neither can be mistaken for
the other. This script only extracts the plan's table rows; it asserts that the
count is exactly 70 and refuses to overwrite unless --force is passed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import sha256_file  # noqa: E402

PLAN = LAB_ROOT / "REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md"
OUT = LAB_ROOT / "configs" / "rf_acceptance_registry.json"
GROUP = re.compile(r"^## 11\.(\d) Nhóm (.+)$")
ROW = re.compile(r"^\| (T\d\d) \| (.+?) \| (.+?) \|$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if OUT.exists() and not args.force:
        raise SystemExit(f"{OUT} exists; pass --force to supersede explicitly")

    group = None
    requirements: list[dict] = []
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        match = GROUP.match(line)
        if match:
            group = f"11.{match.group(1)} {match.group(2)}"
            continue
        row = ROW.match(line)
        if row:
            requirements.append({"id": row.group(1), "group": group,
                                 "situation": row.group(2), "expected": row.group(3)})

    ids = [r["id"] for r in requirements]
    expected = [f"T{i:02d}" for i in range(1, 71)]
    if ids != expected:
        raise SystemExit(f"expected T01..T70 in order, found {len(ids)}: "
                         f"missing {sorted(set(expected) - set(ids))} extra {sorted(set(ids) - set(expected))}")

    payload = {
        "schema": "regime_lab.rf_acceptance_registry.v3",
        "registered_at_utc": utc_now_iso(),
        "study_id": "corrective_mode4_v3",
        "source_plan": {"path": PLAN.name, "sha256": sha256_file(PLAN)},
        "rule": ("these are requirements the corrective study must satisfy, not tests that already pass. "
                 "Test presence does not prove the runner used the tested path (finding D08)."),
        "historical_registry": {"path": "configs/acceptance_test_coverage.json",
                                "ids": "T01..T64", "status": "UNTOUCHED"},
        "counts": {"requirements": len(requirements)},
        "requirements": requirements,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(OUT), "requirements": len(requirements),
                      "groups": sorted({r["group"] for r in requirements})}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
