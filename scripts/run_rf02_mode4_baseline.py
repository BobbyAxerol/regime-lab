#!/usr/bin/env python
"""RF02.4 — capture the actual public Mode 4 per_fold_causal baseline.

Runs the installed pipeline on the route-ready alpha (A-SC) and writes the
engine's own trace. Synthetic and deterministic by design: this artifact proves
the public wiring, selection metric and fee/sizing binding. The real-alpha pilot
is RF02.6 and writes its own artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector.installed_wfo import synthetic_frame  # noqa: E402
from crypto_regime_lab.selector.mode4_baseline import run_mode4_public_baseline  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-02"
RANGES = {"coeff": (1, 8), "AP": (5, 60), "alpha.condition_threshold": (30, 80)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--bars", type=int, default=9000)
    parser.add_argument("--trials", type=int, default=8)
    args = parser.parse_args()

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    target = writer.run_dir / "mode4_public_baseline.json"
    if target.exists() and not args.force:
        raise SystemExit(f"{target} exists; pass --force to supersede explicitly")

    frame = synthetic_frame(n=args.bars, seed=5, freq="4h")
    started = time.perf_counter()
    baseline = run_mode4_public_baseline(
        frame, param_ranges=RANGES, optuna_trials=args.trials, seed=11,
        split_mode=2021, split_frequency="quarterly",
        target_mode="signal_notional", alloc_per_trade=0.1, backend="native_vectorized")
    baseline["wall_seconds"] = round(time.perf_counter() - started, 3)
    baseline["frame"] = {
        "source": "synthetic_frame(n=%d, seed=5, freq=4h, start=2020-01-01)" % args.bars,
        "bars": int(args.bars), "first": str(frame.index[0]), "last": str(frame.index[-1]),
        "is_synthetic": True,
        "note": "the deterministic baseline proof; real-alpha pilot is RF02.6",
    }
    writer.write_json("mode4_public_baseline.json", baseline, schema=baseline["schema"])
    summary = {
        "ok": baseline["ok"], "error": baseline.get("error"),
        "trace": baseline.get("contract_trace"),
        "trial_count": baseline.get("trial_count"),
        "objectives_nonzero": sum(1 for r in baseline.get("trial_records", [])
                                  if abs(float(r.get("objective") or 0.0)) > 1e-12),
        "selected_digest": baseline.get("selected_digest"),
        "wall_seconds": baseline["wall_seconds"],
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0 if baseline["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
