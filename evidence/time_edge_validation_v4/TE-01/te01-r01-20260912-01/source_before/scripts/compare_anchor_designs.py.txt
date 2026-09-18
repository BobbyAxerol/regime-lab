#!/usr/bin/env python
"""The coverage review guide 7.2 asks for: does the anchor composition matter?

Design v1 drew all non-incumbent anchors from the top of the TPE ranking, so every
local panel sat inside the region the sampler already favoured. Design v2 spends
one of the four anchor slots on the evaluated point FARTHEST from those, which is
what guide 7.2 step 1 asks for ("TPE IS search, incumbent VA mot phan space-filling
coverage").

v2 is the primary. v1 is kept as a registered sensitivity, not as an alternative
result to choose between after seeing which looks better.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
PRIMARY_DIR = "lab04_cells"
SENSITIVITY_DIR = "lab04_cells_v1_tpe_only"


def _load(name: str) -> list[dict]:
    root = LAB_ROOT / ".cache" / name
    return [json.loads(p.read_text()) for p in sorted(root.glob("*.json"))]


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    primary_cells = _load(PRIMARY_DIR)
    sensitivity_cells = _load(SENSITIVITY_DIR)
    if not primary_cells or not sensitivity_cells:
        print("both designs must have cells before they can be compared")
        return 1

    primary = CB.summarize(primary_cells)
    sensitivity = CB.summarize(sensitivity_cells)

    def _returns(summary):
        return {row["cell"]: row for row in summary["contrast_B_minus_A"]["per_cell"]}

    def _mechanism(cells):
        """Retention and eligibility, which is HOW an anchor design acts, not just what it scores."""
        out = {}
        for cell in cells:
            if cell["status"] != "RUN":
                continue
            folds = [f for f in cell.get("folds", []) if f.get("status") == "OK"]
            if not folds:
                continue
            out[f"{cell['alpha_id']}/{cell['symbol']}"] = {
                "cutoffs": len(folds),
                "arm_B_retained": sum(1 for f in folds
                                      if f["arms"]["B"]["retained_incumbent"]),
                "eligible_total": sum(
                    f["cutoff_evidence"]["robust_status_counts"].get("ELIGIBLE", 0)
                    for f in folds),
                "pool_total": sum(f["cutoff_evidence"]["budget"]["unique_executions"]
                                  for f in folds),
            }
        return out

    left, right = _returns(primary), _returns(sensitivity)
    mech_v2, mech_v1 = _mechanism(primary_cells), _mechanism(sensitivity_cells)
    shared = sorted(set(left) & set(right))
    rows = []
    selection_changed = 0
    for cell in shared:
        a, b = left[cell], right[cell]
        m2, m1 = mech_v2.get(cell, {}), mech_v1.get(cell, {})
        rows.append({
            "cell": cell,
            "v2_A": a["A"], "v2_B": a["B"], "v2_difference": a["difference"],
            "v1_A": b["A"], "v1_B": b["B"], "v1_difference": b["difference"],
            "arm_B_changed": abs((a["B"] or 0.0) - (b["B"] or 0.0)) > 1e-12,
            "arm_A_changed": abs((a["A"] or 0.0) - (b["A"] or 0.0)) > 1e-12,
            "v2_arm_B_retained": m2.get("arm_B_retained"),
            "v1_arm_B_retained": m1.get("arm_B_retained"),
            "v2_eligible_total": m2.get("eligible_total"),
            "v1_eligible_total": m1.get("eligible_total"),
        })
        selection_changed += int(rows[-1]["arm_B_changed"])

    def _sum(rows_, key):
        values = [r[key] for r in rows_ if r.get(key) is not None]
        return sum(values) if values else None

    arm_a_moved = sum(1 for r in rows if r["arm_A_changed"])
    mechanism_summary = {
        "arm_A_also_moved_in_cells": arm_a_moved,
        "why_arm_A_moves": (
            "arm A ranks the WHOLE pool, probes included, not just the discovery trials. The "
            "discovery search is identical between designs -- same TPE seed, same 64 trials -- but "
            "one of the four anchor slots moved from the TPE ranking to a space-filling point, so "
            "eight probes now surround a different region. When the best in-sample objective in "
            "the pool was one of the probes that no longer exists, arm A's choice moves too. "
            "This comparison is therefore between two complete DESIGNS; it does not isolate arm "
            "B's behaviour, and neither arm should be described as invariant."),
        "arm_B_retained": {"v2": _sum(rows, "v2_arm_B_retained"),
                           "v1": _sum(rows, "v1_arm_B_retained")},
        "eligible_candidates": {"v2": _sum(rows, "v2_eligible_total"),
                                "v1": _sum(rows, "v1_eligible_total")},
        "reading": ("space-filling coverage spends one of four anchor slots away from the region "
                    "TPE favours. That region is where candidates tend to clear the economic gate, "
                    "so broader coverage can COST eligibility rather than add it. Whether that is "
                    "worth it is not decided by eligibility counts -- it is decided out of "
                    "sample -- but the mechanism belongs in the record either way."),
    }

    payload = {
        "schema": "crypto_regime_lab.anchor_design_sensitivity.v1",
        "primary_design": {
            "id": "v2_with_space_filling", "cells_dir": PRIMARY_DIR,
            "anchors": "2 TPE top + 1 farthest-point space filling + 1 incumbent",
            "verdict": primary["verdict"],
            "contrast": primary["contrast_B_minus_A"]["net_return"],
        },
        "sensitivity_design": {
            "id": "v1_tpe_only", "cells_dir": SENSITIVITY_DIR,
            "anchors": "3 TPE top + 1 incumbent (no space-filling coverage)",
            "verdict": sensitivity["verdict"],
            "contrast": sensitivity["contrast_B_minus_A"]["net_return"],
        },
        "cells_compared": len(shared),
        "mechanism": mechanism_summary,
        "arm_B_outcome_changed_in_cells": selection_changed,
        "per_cell": rows,
        "rule": ("v2 is the primary because it is what guide 7.2 step 1 specifies. v1 is reported "
                 "as a registered sensitivity on the anchor composition; neither is chosen after "
                 "the fact for looking better."),
    }
    writer.write_config("lab04_anchor_design_sensitivity.json", payload)
    writer.write_json("anchor_design_sensitivity.json", payload, schema=payload["schema"])

    print(f"cells compared: {len(shared)}  arm B outcome changed in {selection_changed}")
    print(f"  arm A also moved in      : {arm_a_moved} cells "
          f"(the pool is design-dependent, so neither arm is invariant)")
    print(f"  arm B retained incumbent : v2={mechanism_summary['arm_B_retained']['v2']} "
          f"v1={mechanism_summary['arm_B_retained']['v1']}")
    print(f"  eligible candidates      : v2={mechanism_summary['eligible_candidates']['v2']} "
          f"v1={mechanism_summary['eligible_candidates']['v1']}")
    print(f"  v2 (primary, space filling): "
          f"B better in {primary['contrast_B_minus_A']['net_return']['B_better']}, "
          f"A better in {primary['contrast_B_minus_A']['net_return']['A_better']}")
    print(f"  v1 (sensitivity, TPE only) : "
          f"B better in {sensitivity['contrast_B_minus_A']['net_return']['B_better']}, "
          f"A better in {sensitivity['contrast_B_minus_A']['net_return']['A_better']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
