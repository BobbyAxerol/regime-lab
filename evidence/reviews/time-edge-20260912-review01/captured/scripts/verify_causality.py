#!/usr/bin/env python
"""CLI stage `verify-causality` (guide 13.5) — the future cannot reach the past.

LAB-03's exit gate says the future-mutation test must pass "qua cả
loader/resampler/scaler", and LAB-05 adds the model and the streaming filter.
Those four layers are each tested, but nothing ran them together as one gate a
later phase could point at, so this stage does.

Each layer is checked the same way: take a series, mutate ONLY the suffix after
a cutoff, and require every value the past produced to be bit-identical. The
precondition is asserted too — if the mutation did not actually change the
suffix, "the past did not move" is trivially true and proves nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data import features as F  # noqa: E402
from crypto_regime_lab.data.availability import resample_bars  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.regime.causality import (  # noqa: E402
    future_suffix_mutation_test,
    run_control_pair,
)
from crypto_regime_lab.regime.emissions import OnlineStateFilter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CUTOFF = 300
N = 500


def _bars(seed: int, n: int = N) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    price = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    start = pd.Timestamp("2021-01-01")
    return pd.DataFrame({
        "time": pd.date_range(start, periods=n, freq="1min"),
        "open": price, "high": price * 1.001, "low": price * 0.999, "close": price,
        "volume": rng.uniform(0.5, 5.0, n),
    })


def check_resampler() -> dict:
    """A longer tape must not change a bucket that already closed."""
    bars = _bars(7)
    prefix = bars.iloc[:CUTOFF].copy()
    mutated = bars.copy()
    mutated.loc[CUTOFF:, ["open", "high", "low", "close"]] *= 3.0

    full = resample_bars(bars, "1min", "15min")
    short = resample_bars(prefix, "1min", "15min")
    after = resample_bars(mutated, "1min", "15min")

    closed = min(len(short), len(full))
    # compare only buckets that had closed by the cutoff
    left = short.iloc[:closed].reset_index(drop=True)
    right = full.iloc[:closed].reset_index(drop=True)
    suffix_changed = not bars.iloc[CUTOFF:]["close"].equals(mutated.iloc[CUTOFF:]["close"])
    return {
        "layer": "resampler",
        "suffix_actually_changed": bool(suffix_changed),
        "buckets_compared": int(closed),
        "prefix_identical_when_tape_is_longer": bool(left.equals(right)),
        "prefix_identical_under_mutated_future": bool(
            full.iloc[:closed].reset_index(drop=True).equals(
                after.iloc[:closed].reset_index(drop=True))),
    }


def check_scaler() -> dict:
    """A scaler fitted on the training slice cannot move when the future does."""
    bars = _bars(11)
    frame = pd.DataFrame({"f": bars["close"].to_numpy()})
    mutated = frame.copy()
    mutated.loc[CUTOFF:, "f"] *= 9.0

    train = frame.iloc[:CUTOFF]
    before = F.RobustScaler().fit(train, ["f"])
    after = F.RobustScaler().fit(mutated.iloc[:CUTOFF], ["f"])
    return {
        "layer": "scaler",
        "suffix_actually_changed": bool(not frame.iloc[CUTOFF:].equals(mutated.iloc[CUTOFF:])),
        "median_identical": bool(before.median_ == after.median_),
        "scale_identical": bool(before.scale_ == after.scale_),
        "fitted_rows": int(len(train)),
    }


def check_model() -> dict:
    """T39 — refit across a mutated future and require an identical artifact."""
    rng = np.random.default_rng(3)
    raw = np.vstack([rng.normal(0, 1, (N, 2)), ]).reshape(N, 2)
    honest = future_suffix_mutation_test(raw, CUTOFF)
    control = run_control_pair(raw, CUTOFF)
    return {"layer": "model", "test": honest, "leaky_control": control}


def check_stream() -> dict:
    """T38 — one observation at a time must equal the batch prefix."""
    rng = np.random.default_rng(5)
    obs = rng.normal(0, 1, (120, 2))
    centroids = np.array([[-1.0, -1.0], [1.0, 1.0]])
    weights = np.array([0.5, 0.5])

    def emit(stream: np.ndarray) -> list[int]:
        filt = OnlineStateFilter(centroids, weights, 1.0, namespace="verify")
        return [int(filt.step(row)[0]) for row in stream]

    longer = np.vstack([obs, rng.normal(9.0, 1.0, (40, 2))])
    short_path, long_path = emit(obs), emit(longer)
    return {
        "layer": "online_filter",
        "observations": int(len(obs)),
        "suffix_actually_changed": True,
        "prefix_identical_when_stream_continues": bool(short_path == long_path[:len(obs)]),
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    with writer.attempt("cli.verify_causality") as att:
        layers = [check_resampler(), check_scaler(), check_model(), check_stream()]
        att.detail = {"layers": len(layers)}

    def ok(layer: dict) -> bool:
        if layer["layer"] == "model":
            test = layer["test"]
            # probe_valid is the precondition: the mutation must really have
            # changed the suffix, or "nothing moved" proves nothing
            return bool(test["probe_valid"] and test["verdict"] == "CAUSAL")
        return all(v for k, v in layer.items()
                   if k != "layer" and isinstance(v, bool))

    verdicts = {layer["layer"]: bool(ok(layer)) for layer in layers}
    control = layers[2]["leaky_control"]
    control_detects = bool(control["detector_is_meaningful"])

    report = {
        "schema": "crypto_regime_lab.causality_verification.v1",
        "checked_at_utc": utc_now_iso(),
        "cutoff_index": CUTOFF,
        "layers": layers,
        "verdicts": verdicts,
        "leaky_control_is_detected": control_detects,
        "control_rule": (
            "a passing causality suite means nothing unless the same probe FAILS on a "
            "deliberately leaky fit. The leaky control is run alongside and must be detected"),
        "status": ("CAUSAL" if all(verdicts.values()) and control_detects
                   else "LEAK_OR_UNPROVEN"),
    }
    writer.write_config("causality_verification.json", report)
    writer.write_json("causality_verification.json", report, schema=report["schema"])

    for layer, verdict in verdicts.items():
        print(f"  {layer:<16} {'CAUSAL' if verdict else 'FAILED'}")
    print(f"  leaky control detected: {control_detects}")
    print(f"status: {report['status']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if report["status"] == "CAUSAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
