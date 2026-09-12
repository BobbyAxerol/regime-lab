#!/usr/bin/env python
"""RF02.1 — alpha semantic and route capability registry.

Reads the actual adapters, schemas and the registered timeframe table; computes
each adapter's warmup from its own code; records the A05 canonical stop-mode
repair. Route qualification itself is filled in by RF02.6 after the real-alpha
pilot, so every cell starts PENDING_QUALIFICATION.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.alphas.base import MarketSlice  # noqa: E402
from crypto_regime_lab.alphas.a_hma import (  # noqa: E402
    AdaptiveHmaEventAdapterV1, IGNORED_KNOBS, LEGACY_SL_INPUT_ALIASES, SL_MODES,
)
from crypto_regime_lab.alphas.a_hash import HashMomentumEventAdapterV1  # noqa: E402
from crypto_regime_lab.alphas.a_sc import SignalCombineAdapterV1  # noqa: E402
from crypto_regime_lab.alphas.a_vwap import VwapMeanReversionEventAdapterV1  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS, SEED_POINTS  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-02"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")

ADAPTERS = {
    "A-SC": ("crypto_regime_lab/alphas/a_sc.py", SignalCombineAdapterV1),
    "A-HMA": ("crypto_regime_lab/alphas/a_hma.py", AdaptiveHmaEventAdapterV1),
    "A-VWAP": ("crypto_regime_lab/alphas/a_vwap.py", VwapMeanReversionEventAdapterV1),
    "A-HASH": ("crypto_regime_lab/alphas/a_hash.py", HashMomentumEventAdapterV1),
}

SEMANTICS = {
    "A-SC": {
        "intents_emitted": ["ENTER_LONG", "EXIT_ALL"],
        "sizing_basis": "FIXED_NOTIONAL",
        "protection": "none (long-flat crossover; no resting stop/target)",
        "intrabar_required": False,
        "known_blockers": [],
        "route_candidate": "signal_or_pct_equity (crossover target series is exact)",
    },
    "A-HMA": {
        "intents_emitted": ["ENTER_LONG", "ENTER_SHORT", "EXIT_ALL", "SET_PROTECTION"],
        "sizing_basis": "FIXED_NOTIONAL entries; level-based protection quantities",
        "protection": "resting stop/TP; gap policy may emit corrective EXIT_ALL after a fill",
        "intrabar_required": True,
        "known_blockers": ["corrective EXIT_ALL after an invalid bracket must reach the position (A04)"],
        "route_candidate": "native_event_feedback",
    },
    "A-VWAP": {
        "intents_emitted": ["ENTER_LONG", "ENTER_SHORT", "EXIT_ALL", "SET_PROTECTION",
                            "AMEND_PROTECTION"],
        "sizing_basis": "FIXED_NOTIONAL entries; level-based protection quantities",
        "protection": "stop/TP plus optional dynamic VWAP amendment and time stop",
        "intrabar_required": True,
        "known_blockers": ["AMEND_PROTECTION is unmapped on the intent tape (A04)"],
        "route_candidate": "native_event_feedback",
    },
    "A-HASH": {
        "intents_emitted": ["ENTER_LONG", "ENTER_SHORT", "SET_PROTECTION (partial TP ladder)"],
        "sizing_basis": "FRACTION_OF_REMAINING protection ladder; fixed-notional entries",
        "protection": "ordered multi-rung partial TP ladder with remaining quantity and cooldown",
        "intrabar_required": True,
        "known_blockers": ["partial ladder not expressible on the current intent tape; needs native "
                           "event order capability or the cell is BLOCKED_CAPABILITY"],
        "route_candidate": "native_event_feedback_or_block",
    },
}


def synthetic_market(n: int = 64) -> MarketSlice:
    close = np.full(n, 100.0)
    return MarketSlice(open=close.copy(), high=close + 0.5, low=close - 0.5, close=close,
                       volume=np.full(n, 1000.0),
                       index=pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"))


def schema_snapshot(schema) -> dict:
    params = {}
    for name, spec in schema.specs.items():
        params[name] = {
            "kind": spec.kind,
            "low": spec.low, "high": spec.high, "step": spec.step,
            "choices": list(spec.choices), "fixed_value": spec.fixed_value,
            "active_when": list(spec.active_when) if spec.active_when else None,
        }
    return {"params": params, "dependencies": [list(dep) for dep in schema.dependencies]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    target = writer.run_dir / "alpha_route_registry.json"
    if target.exists() and not args.force:
        raise SystemExit(f"{target} exists; pass --force to supersede explicitly")

    registration = json.loads((LAB_ROOT / "configs" / "study_registration.json").read_text())
    market = synthetic_market()
    alphas = {}
    for alpha_id, (relative, cls) in ADAPTERS.items():
        params = dict(SEED_POINTS[alpha_id])
        adapter = cls(params, market)
        schema = SCHEMAS[alpha_id]
        path = LAB_ROOT / "src" / relative
        alphas[alpha_id] = {
            "adapter_class": cls.__name__,
            "adapter_file": relative,
            "adapter_sha256": sha256_file(path),
            "adapter_version": getattr(cls, "adapter_version", None),
            "decision_bars": registration["timeframes"][alpha_id]["decision_bars"],
            "execution_bars": registration["timeframes"][alpha_id]["execution_bars"],
            "warmup_bars": int(adapter.warmup_bars()),
            "warmup_source": "adapter.warmup_bars() computed on this commit",
            "seed_point": params,
            "ignored_knobs": ([k for k in IGNORED_KNOBS if k in params] if alpha_id == "A-HMA" else []),
            "schema": schema_snapshot(schema),
            "semantics": SEMANTICS[alpha_id],
            "route_status": "PENDING_QUALIFICATION",
            "cell_status": {f"{alpha_id}/{symbol}": "PENDING_QUALIFICATION" for symbol in SYMBOLS},
        }

    payload = {
        "schema": "regime_lab.alpha_route_registry.v3",
        "generated_at_utc": utc_now_iso(),
        "phase": PHASE,
        "study_id": STUDY_ID,
        "rule": ("route decisions are made from capability and schema BEFORE any outcome, never from which "
                 "candidate made more money; a cell that cannot preserve semantics is BLOCKED_CAPABILITY, "
                 "not silently rerouted"),
        "alphas": alphas,
        "a05_stop_mode_repair": {
            "canonical_enum": dict(SL_MODES),
            "schema_choices_before": ["Half Distance Zone", "Zone Distance", "ATR"],
            "schema_choices_after": list(SL_MODES),
            "legacy_aliases_explicit": dict(LEGACY_SL_INPUT_ALIASES),
            "silent_default_removed": True,
            "repair": "the adapter validates sl_input and raises InfeasibleConfiguration on an unknown name; "
                      "historical names replay only through the explicit alias table",
        },
        "route_decision_vocabulary": ["QUALIFIED_FAST", "QUALIFIED_EVENT", "BLOCKED_CAPABILITY",
                                      "INSUFFICIENT_DATA"],
        "acceptance_refs": ["T15", "T16", "T19", "T20", "T22"],
    }
    writer.write_json("alpha_route_registry.json", payload, schema=payload["schema"])
    print(json.dumps({"target": str(target), "alphas": list(alphas),
                      "warmup_bars": {k: v["warmup_bars"] for k, v in alphas.items()},
                      "statuses": {k: v["route_status"] for k, v in alphas.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
