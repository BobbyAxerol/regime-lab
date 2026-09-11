#!/usr/bin/env python
"""Recompute the per-cell controls without re-running the selector search.

The controls depend on arm A's already-recorded selections and on the state
tape, neither of which changes. Re-running the whole factorial to fix a control
would cost three hours and would re-run the expensive part for nothing; this
replays only the arms the controls need.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments.factorial import ArmResult, run_arm  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from run_lab08_factorial import (  # noqa: E402
    bars_for,
    calendar_selections,
    emissions_for,
    run_controls,
)

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    protocol = json.loads((CONFIGS / "lab08_pilot_protocol.json").read_text())
    factorial = json.loads((CONFIGS / "lab08_factorial_full.json").read_text())
    baseline = json.loads((CONFIGS / "lab04_calendar_baseline.json").read_text())
    baseline_cells = {(c["alpha_id"], c["symbol"]): c for c in baseline["cells"]}

    cache: dict = {}
    started = time.perf_counter()
    updated = 0
    for cell in factorial["cells"]:
        if cell["status"] != "RUN":
            continue
        alpha_id, symbol = cell["alpha_id"], cell["symbol"]
        source = baseline_cells[(alpha_id, symbol)]
        bars = bars_for(alpha_id, symbol, protocol, cache)
        selections = calendar_selections(source, "arm_A")
        arm_a = run_arm("A", alpha_id, symbol, bars, selections)
        results = {"A": arm_a}
        for arm in ("B", "C", "D", "E"):
            results[arm] = ArmResult(arm, alpha_id, symbol,
                                     cell["arms"][arm].get("status", "UNKNOWN"))
        cell["controls"] = run_controls(alpha_id, symbol, bars, results,
                                        emissions_for(symbol), protocol,
                                        baseline_selections=selections)
        updated += 1
        risk = cell["controls"].get("RISK_ONLY") or {}
        print(f"  {alpha_id}/{symbol}: RISK_ONLY {risk.get('net_return')} "
              f"(baseline {risk.get('baseline_net_return')}, "
              f"scale {risk.get('mean_size_scale')})", flush=True)

    factorial["controls_recomputed_at_utc"] = utc_now_iso()
    factorial["controls_recomputed_reason"] = (
        "the RISK_ONLY calibration window was a hardcoded date; it is now derived from the frozen "
        "calendar's test_days and the control trades unscaled until that window closes. Only the "
        "controls were replayed -- the arms and their selections are unchanged")
    with writer.attempt("L08.3.recompute_controls") as att:
        att.detail = {"cells": updated}
    writer.write_config("lab08_factorial_full.json", factorial)
    writer.write_json("lab08_factorial_full.json", factorial, schema=factorial["schema"])

    print(f"\nrecomputed controls on {updated} cells in "
          f"{time.perf_counter() - started:.0f}s")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
