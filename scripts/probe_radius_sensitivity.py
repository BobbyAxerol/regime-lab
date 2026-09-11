#!/usr/bin/env python
"""Guide 7.2 -- a REGISTERED probe-radius sensitivity, not a tuning sweep.

"Khong khoa probe radius dua preset full-sample. Mot radius lon va nho co the la
sensitivity da dang ky, khong lay radius dep nhat sau outer OOS."

So the three radii are declared HERE, before the numbers are looked at, the
primary stays 0.12 whatever this shows, and the point of the artifact is to say
how sensitive the arm-B selection is to a choice that was made by judgement.
Nothing downstream may pick the best-looking radius.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data import panel as P  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS, SEED_POINTS  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
#: Declared before the run. 0.12 is and stays the primary.
RADII = (0.06, 0.12, 0.24)
PRIMARY_RADIUS = 0.12
CELL = ("A-SC", "BTCUSDT")


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    alpha_id, symbol = CELL
    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = json.loads((snapshot_root / "manifest.json").read_text())
    frame = P.load_resampled(snapshot_root, "crypto_binance_futures_1m", symbol,
                             CB.DECISION_INTERVAL[alpha_id], manifest=manifest)
    frame["time"] = pd.to_datetime(frame["time"])
    if frame["time"].dt.tz is None:
        frame["time"] = frame["time"].dt.tz_localize("UTC")
    bars = frame.set_index("time").sort_index()

    window = CB.CALENDAR.fold_windows()[0]
    train = bars[(bars.index >= window["train_start"]) & (bars.index < window["cutoff"])]
    incumbents = {arm: dict(SEED_POINTS[alpha_id]) for arm in CB.ARMS}

    results = {}
    with writer.attempt("L04.3.radius_sensitivity") as att:
        for radius in RADII:
            budget = CB.SearchBudget(radius=radius)
            out = CB.run_cutoff(alpha_id, symbol, train, 0, incumbents, budget=budget)
            results[str(radius)] = {
                "radius": radius,
                "arm_B_status": out["arm_B"]["status"],
                "arm_B_point_id": out["arm_B"].get("point_id"),
                "arm_B_params": out["arm_B"].get("params"),
                "arm_B_R": out["arm_B"].get("R"),
                "arm_B_G": out["arm_B"].get("G"),
                "arm_B_F": out["arm_B"].get("F"),
                "eligible_count": out["arm_B"].get("eligible_count"),
                "robust_status_counts": out["robust_status_counts"],
                "unique_executions": out["budget"]["unique_executions"],
                "median_evaluated_neighbours":
                    out["local_coverage"]["median_evaluated_neighbours"],
                "arm_A_point_id": out["arm_A"].get("point_id"),
            }
        att.detail = {"radii": list(RADII)}

    schema = SCHEMAS[alpha_id]
    primary = results[str(PRIMARY_RADIUS)]
    distances = {}
    for key, record in results.items():
        if record["arm_B_params"] and primary["arm_B_params"]:
            distances[key] = schema.distance(primary["arm_B_params"], record["arm_B_params"])

    selections = {r["arm_B_point_id"] for r in results.values()}
    payload = {
        "schema": "crypto_regime_lab.probe_radius_sensitivity.v1",
        "declared_before_the_run": True,
        "radii": list(RADII),
        "primary_radius": PRIMARY_RADIUS,
        "cell": {"alpha_id": alpha_id, "symbol": symbol, "fold": 0},
        "results": results,
        "schema_distance_from_primary_selection": distances,
        "selection_changed_with_radius": len(selections) > 1,
        "arm_A_is_radius_independent":
            len({r["arm_A_point_id"] for r in results.values()}) == 1,
        "rule": ("the primary radius is 0.12 regardless of what this shows; a radius is a "
                 "registered design choice, never picked after seeing an outer result"),
        "R_is_not_comparable_across_radii": (
            "R = G - lambda_F * F, and F is the regret against NEIGHBOURS. A smaller radius puts "
            "the neighbours closer, which mechanically shrinks F and inflates R. So a higher R at "
            "a smaller radius is an artefact of the geometry, not evidence that the smaller radius "
            "selects better. Only the SELECTED POINT is comparable across radii, and only G is "
            "comparable, because G does not depend on the neighbourhood at all."),
        "comparable_across_radii": ["the selected point", "G"],
        "not_comparable_across_radii": ["F", "R", "P_survive"],
        "G_by_radius": {key: record["arm_B_G"] for key, record in results.items()},
    }
    writer.write_config("lab04_probe_radius_sensitivity.json", payload)
    writer.write_json("probe_radius_sensitivity.json", payload, schema=payload["schema"])

    print(f"cell: {alpha_id}/{symbol} fold 0 (primary radius {PRIMARY_RADIUS} is unchanged)")
    for key, record in results.items():
        print(f"   radius {record['radius']:<5} B={record['arm_B_status']:<28} "
              f"eligible={record['eligible_count']} R={record['arm_B_R']} "
              f"d(primary)={distances.get(key)}")
    print(f"   arm B selection changes with radius : {payload['selection_changed_with_radius']}")
    print(f"   arm A is radius independent        : {payload['arm_A_is_radius_independent']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
