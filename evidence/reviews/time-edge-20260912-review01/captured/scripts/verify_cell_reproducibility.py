#!/usr/bin/env python
"""Does the COMMITTED code still reproduce a committed cutoff decision?

A multi-hour run executes whatever version of the modules was loaded when it
started. If the source is edited afterwards, the committed code and the committed
artifact can silently disagree, and nobody notices until a re-run gives different
numbers. So re-run one real cutoff with the current code and compare it against
what the checkpoint recorded.

The comparison is on the DECISION -- the selected parameters, the point id, and
whether anything was selected at all. It is deliberately not on status TEXT: the
arm-B status label was refined during the LAB-04 re-review from a single
``INSUFFICIENT_LOCAL_EVIDENCE`` to ``NO_ADMISSIBLE_CANDIDATE:<binding constraint>``,
which renames a reason without changing any choice. A parameter difference, by
contrast, is a reproducibility failure and exits non-zero.
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
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
CHECKPOINTS = LAB_ROOT / ".cache" / "lab04_cells"
#: fold 0 of the pilot cell: its incumbents are the registered seed points, so the
#: cutoff can be reconstructed exactly without replaying earlier folds
CELL = ("A-SC", "BTCUSDT")

GOVERNING_MODULES = [
    "src/crypto_regime_lab/experiments/calendar_baseline.py",
    "src/crypto_regime_lab/experiments/evaluator.py",
    "src/crypto_regime_lab/selector/alpha_schemas.py",
    "src/crypto_regime_lab/selector/probe_design.py",
    "src/crypto_regime_lab/selector/robust_score.py",
    "src/crypto_regime_lab/selector/schema_distance.py",
    "src/crypto_regime_lab/selector/representative.py",
]


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    alpha_id, symbol = CELL
    checkpoint = CHECKPOINTS / f"{alpha_id}_{symbol}.json"
    if not checkpoint.is_file():
        print(f"no checkpoint at {checkpoint}")
        return 1
    cell = json.loads(checkpoint.read_text())
    stored = next((f for f in cell["folds"] if f.get("fold") == 0
                   and f.get("status") == "OK"), None)
    if stored is None:
        print("fold 0 of the pilot cell is not available")
        return 1

    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = json.loads((snapshot_root / "manifest.json").read_text())
    frame = P.load_resampled(snapshot_root, "crypto_binance_futures_1m", symbol,
                             CB.DECISION_INTERVAL[alpha_id], manifest=manifest)
    frame["time"] = pd.to_datetime(frame["time"])
    if frame["time"].dt.tz is None:
        frame["time"] = frame["time"].dt.tz_localize("UTC")
    bars = frame.set_index("time").sort_index()
    train = bars[(bars.index >= stored["train_start"]) & (bars.index < stored["cutoff"])]

    with writer.attempt("L04.repro.cutoff") as att:
        replay = CB.run_cutoff(alpha_id, symbol, train, 0,
                               {arm: dict(SEED_POINTS[alpha_id]) for arm in CB.ARMS})
        att.detail = {"cell": f"{alpha_id}/{symbol}", "fold": 0}

    checks = []
    reproduced = True
    for arm in CB.ARMS:
        was = stored["arms"][arm]
        now = replay[f"arm_{arm}"]
        stored_selection = was["selection"]
        same_params = was["params"] == (now["params"] if now["params"] is not None
                                        else was["params"] if was["retained_incumbent"] else None)
        # a retained incumbent means the selector returned nothing; compare that fact
        if was["retained_incumbent"]:
            same_params = now["params"] is None
        same_point = stored_selection.get("point_id") == now.get("point_id")
        same_bars = int(stored["train_bars"]) == int(replay["train_bars"])
        same_pool = (stored["cutoff_evidence"]["budget"]["unique_executions"]
                     == replay["budget"]["unique_executions"])
        ok = same_params and same_point and same_bars and same_pool
        reproduced &= ok
        checks.append({
            "arm": arm, "reproduced": ok,
            "same_selected_params": bool(same_params), "same_point_id": bool(same_point),
            "same_train_bars": bool(same_bars), "same_candidate_pool_size": bool(same_pool),
            "stored_point_id": stored_selection.get("point_id"),
            "replayed_point_id": now.get("point_id"),
            "stored_status": stored_selection.get("status"),
            "replayed_status": now.get("status"),
            "status_label_changed_only": (stored_selection.get("status")
                                          != now.get("status")) and ok,
        })

    payload = {
        "schema": "crypto_regime_lab.cutoff_reproducibility.v1",
        "cell": {"alpha_id": alpha_id, "symbol": symbol, "fold": 0},
        "train_window": {"start": stored["train_start"], "end": stored["cutoff"],
                         "bars": stored["train_bars"]},
        "reproduced": bool(reproduced),
        "compares": ("the decision -- selected parameters, point id, candidate pool size -- not "
                     "status label text; a renamed reason is not a changed choice"),
        "checks": checks,
        "governing_module_digests": {
            path: sha256_file(LAB_ROOT / path)[:16] for path in GOVERNING_MODULES},
        "probe_design_digest": replay["probe_design"]["design_digest"],
        "stored_probe_design_digest": stored["cutoff_evidence"]["probe_design"]["design_digest"],
        "probe_design_unchanged": (replay["probe_design"]["design_digest"]
                                   == stored["cutoff_evidence"]["probe_design"]["design_digest"]),
    }
    writer.write_config("lab04_cutoff_reproducibility.json", payload)
    writer.write_json("cutoff_reproducibility.json", payload, schema=payload["schema"])

    print(f"cell {alpha_id}/{symbol} fold 0  train_bars={stored['train_bars']}")
    for check in checks:
        print(f"   arm {check['arm']}: reproduced={check['reproduced']} "
              f"point {check['stored_point_id']} -> {check['replayed_point_id']}")
        if check["status_label_changed_only"]:
            print(f"      status label changed without changing the choice: "
                  f"{check['stored_status']} -> {check['replayed_status']}")
    print(f"   probe design digest unchanged: {payload['probe_design_unchanged']}")
    print(f"   overall reproduced: {payload['reproduced']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
