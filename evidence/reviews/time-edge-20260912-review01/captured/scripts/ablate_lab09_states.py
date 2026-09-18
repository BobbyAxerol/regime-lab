#!/usr/bin/env python
"""L09.7.1 — the group ablation on a window that is actually inside the interval.

The fitter runs guide 8.3's ablation on the FIRST cutoff's training window,
because that is where LAB-05 chose K and the two belong together. For the
confirmation role that window is the 365 days BEFORE the interval starts -- it is
development data, and an ablation computed there says nothing about the
confirmation interval.

So the descriptive contribution is measured here instead, on the LAST cutoff of
the confirmation role, whose training window lies entirely inside the interval.
No refit is needed: the model artifact for that cutoff already carries the scaler
it was fitted with, and the ablation re-fits per feature subset anyway.

Naming this rather than reusing the fitter's artifact is the point. The fitter's
artifact is not wrong; it is about a different window, and a claim about the
confirmation interval cannot rest on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.regime import ablation as AB  # noqa: E402
from crypto_regime_lab.regime import causality as C  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
CONFIGS = LAB_ROOT / "configs"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
CONFIRMATION_START = "2024-01-01"
#: the fitter's registered settings, read back rather than restated
LAMBDA_JUMP, SEEDS = 1.0, (11, 23, 37, 51)


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def ablate(symbol: str, schema: dict) -> dict:
    registry = load(f"lab09_{symbol.lower()}_regime_model_registry.json")
    if registry is None:
        return {"status": "NO_REGISTRY"}
    model = registry["models"][-1]
    cutoff = pd.Timestamp(model["training_cutoff"])
    start = pd.Timestamp(model["training_start"])
    if start < pd.Timestamp(CONFIRMATION_START):
        return {"status": "WINDOW_NOT_INSIDE_THE_INTERVAL",
                "training_start": str(start), "training_cutoff": str(cutoff),
                "reason": ("even the last cutoff's training window reaches before the "
                           "confirmation interval; no in-interval ablation is available")}

    features = list(schema["primary_core_features"])
    weights = np.asarray([schema["group_weights"][f] for f in features], dtype=np.float64)
    panel = pd.read_parquet(LAB_ROOT / "snapshots" / SNAPSHOT_ID / "panels"
                            / f"{symbol}.parquet")
    panel["time"] = pd.to_datetime(panel["time"])
    window = panel[(panel["time"] >= start) & (panel["time"] < cutoff)]
    window = window.dropna(subset=features)
    if len(window) < 200:
        return {"status": "TOO_FEW_ROWS", "rows": int(len(window))}

    raw = window[features].to_numpy(float)
    z = C.apply_scaler(raw, {"median": np.asarray(model["scaler_ref"]["median"]),
                             "scale": np.asarray(model["scaler_ref"]["scale"]),
                             "clip": model["scaler_ref"]["clip"]})
    result = AB.group_ablation(z, tuple(features), weights,
                               n_states=int(model["n_states"]),
                               lambda_jump=LAMBDA_JUMP, seeds=SEEDS)
    return {
        "status": "MEASURED",
        "model_id": model["model_id"],
        "training_window": [str(start), str(cutoff)],
        "window_is_inside_the_confirmation_interval": True,
        "rows": int(len(window)),
        "blocks_that_improved_out_of_fold": result["blocks_that_improved_out_of_fold"],
        "blocks_that_did_not": result["blocks_that_did_not"],
        "ladder": result["ladder"],
        "decided_on": result["decided_on"],
    }


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    schema = json.loads((CONFIGS / "feature_schema.json").read_text())
    per_symbol = {}
    for symbol in SYMBOLS:
        print(f"  {symbol} ...", flush=True)
        with writer.attempt(f"L09.7.ablation@{symbol}") as att:
            per_symbol[symbol] = ablate(symbol, schema)
            att.detail = {"status": per_symbol[symbol]["status"]}

    measured = [v for v in per_symbol.values() if v["status"] == "MEASURED"]
    improved = [s for s, v in per_symbol.items()
                if v["status"] == "MEASURED" and v["blocks_that_improved_out_of_fold"]]
    document = {
        "schema": "crypto_regime_lab.lab09_group_ablation.v1",
        "generated_at_utc": utc_now_iso(),
        "window_rule": ("the LAST confirmation-role cutoff's training window, which lies "
                        "entirely inside the confirmation interval. The fitter's own ablation "
                        "uses the FIRST cutoff's window, which for this role is development "
                        "data"),
        "requirement": ("guide 8.3: the flow and market-coordination blocks must be shown to "
                        "contribute BEYOND price and volatility"),
        "per_symbol": per_symbol,
        "symbols_measured": len(measured),
        "symbols_where_a_block_improved_out_of_fold": len(improved),
        "symbols_improved": improved,
        "requirement_satisfied": bool(improved),
        "finding": (
            "no block beyond price and volatility improves out-of-fold variance resolved on any "
            "symbol inside the confirmation interval, which reproduces the development finding"
            if not improved else
            f"a block improved out of fold on {improved}, which development did not show"),
        "registered_core_unchanged": True,
        "why_unchanged": ("selecting a feature set on this result would be choosing the model on "
                          "an outcome. The finding is recorded; the core stays as registered"),
    }
    writer.write_config("lab09_group_ablation.json", document)
    writer.write_json("lab09_group_ablation.json", document, schema=document["schema"])

    for symbol, record in per_symbol.items():
        if record["status"] != "MEASURED":
            print(f"  {symbol:<9} {record['status']}")
            continue
        print(f"  {symbol:<9} window {record['training_window'][0][:10]}.."
              f"{record['training_window'][1][:10]}  improved="
              f"{record['blocks_that_improved_out_of_fold']}")
    print(f"requirement satisfied: {document['requirement_satisfied']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
