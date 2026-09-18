#!/usr/bin/env python
"""Rebuild the calendar-baseline artifact from the per-cell checkpoints.

Kept separate from the runner so the committed summary always reflects the
CURRENT summarising code rather than whatever version happened to be loaded when
a multi-hour run started. It recomputes nothing about the experiment: the cells
are read exactly as they were written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.evaluator import ACCOUNT, UTILITY  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CHECKPOINTS = LAB_ROOT / ".cache" / (sys.argv[1] if len(sys.argv) > 1 else "lab04_cells")
OUT_NAME = sys.argv[2] if len(sys.argv) > 2 else "lab04_calendar_baseline.json"
EXPECTED_CELLS = len(CB.ALPHA_ORDER_DEFAULT) * len(CB.SYMBOL_ORDER_DEFAULT)


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    files = sorted(CHECKPOINTS.glob("*.json"))
    if not files:
        print(f"no cell checkpoints under {CHECKPOINTS}")
        return 1
    cells = [json.loads(path.read_text()) for path in files]
    wall = sum(c.get("wall_seconds") or 0.0 for c in cells)

    with writer.attempt("L04.6.summarize") as att:
        report = CB.summarize(cells, wall_seconds=round(wall, 1))
        att.detail = {"cells": len(cells), "run": report["cells_run"]}
    report["account_contract"] = ACCOUNT
    report["utility_hyperparameters"] = UTILITY
    report["snapshot_id"] = "server_core_v1"
    report["cells_expected"] = EXPECTED_CELLS
    report["matrix_complete"] = len(cells) == EXPECTED_CELLS
    if not report["matrix_complete"]:
        report["partial_matrix_warning"] = (
            f"only {len(cells)} of {EXPECTED_CELLS} cells are present; this summary is PARTIAL "
            "and no scope claim may be made from it")
    report["cells_dir"] = CHECKPOINTS.name
    writer.write_config(OUT_NAME, report)
    writer.write_json(OUT_NAME, report, schema=report["schema"])

    print(f"cells: {len(cells)}/{EXPECTED_CELLS} "
          f"(run={report['cells_run']}, not_ready={report['cells_not_ready']}) "
          f"complete={report['matrix_complete']}")
    for line in report["console_table"]:
        print("   " + line)
    print(f"   verdict: {report['verdict']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
