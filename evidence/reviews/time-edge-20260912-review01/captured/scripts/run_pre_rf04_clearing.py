#!/usr/bin/env python
"""Pre-RF04 clearing: G2 corrected MDE, G3 spec revisions, G6 timing cohort,
G7 real A-HMA pilot, plus the model/response scope decision and gap clearance.

Reads the real BTCUSDT 1m snapshot directly. Writes under
evidence/corrective_mode4_v3/pre-RF04-clearing/.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.integration.continuous_account import VersionWindow  # noqa: E402
from crypto_regime_lab.integration.event_account import run_event_account  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "pre-RF04-clearing"
SNAP = "snapshots/server_core_v1/crypto_binance_futures_1m/BTCUSDT"


def load_bars(start: str, end: str, rule: str) -> pd.DataFrame:
    frame = pd.read_parquet(LAB_ROOT / SNAP / "2021-01.parquet",
                            columns=["time", "open", "high", "low", "close", "volume"])
    frame["time"] = pd.to_datetime(frame["time"]).dt.tz_localize("UTC")
    frame = frame.set_index("time").sort_index().loc[start:end]
    out = frame.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna()


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)
    start, end = "2021-01-05 00:00", "2021-03-05 00:00"
    bars_15m = load_bars(start, end, "15min")
    bars_1h = load_bars(start, end, "1h")
    days = (bars_1h.index[-1] - bars_1h.index[0]) / pd.Timedelta(days=1)
    pilot = {}
    for alpha_id, bars in (("A-SC", bars_15m), ("A-HMA", bars_1h)):
        initial = VersionWindow(f"{alpha_id}-seed", dict(SEED_POINTS[alpha_id]), 0, "seed")
        t0 = time.perf_counter()
        run = run_event_account(alpha_id, bars, initial=initial, schedule=[])
        pilot[alpha_id] = {"status": run.status, "entries": run.entries,
                           "engine_fills": run.engine_fill_count,
                           "fills_seen": len(run.fills),
                           "unmapped": run.unmapped_intents[:3],
                           "rejections": run.rejections[:3],
                           "equity_last": float(run.equity[-1]),
                           "wall_seconds": round(time.perf_counter() - t0, 3)}
    # G2: corrected MDE from the actual account units of the real pilot.
    round_trips_per_day = max(pilot["A-SC"]["entries"] / days, 1.0 / days)
    notional_over_equity = 2000.0 / 20000.0
    corrected_mde = 0.001 * round_trips_per_day * notional_over_equity
    mde = {
        "schema": "regime_lab.corrected_mde.v1", "generated_at_utc": utc_now_iso(),
        "pilot_window": {"start": start, "end": end, "bars_15m": int(len(bars_15m)), "bars_1h": int(len(bars_1h)), "days": round(days, 3)},
        "inputs": {"round_trip_cost_uncertainty": 0.001,
                   "round_trips_per_day_measured": round(round_trips_per_day, 6),
                   "notional_over_equity": notional_over_equity,
                   "source": "A-SC real-snapshot event account on the registered account"},
        "corrected_daily_account_mde": corrected_mde,
        "corrected_daily_account_bps": corrected_mde * 1e4,
        "historical_registered": {"value": 6.4e-05, "status": "PRESERVED_AS_HISTORY"},
        "status": "FROZEN_BEFORE_RF04_RESULTS",
        "rule": "computed from measured account units; never chosen after seeing a result",
    }
    revisions = {
        "schema": "regime_lab.spec_revisions.v1", "generated_at_utc": utc_now_iso(),
        "study_id": STUDY_ID, "revisions": [
            {"id": "REV-01", "change": "A05 canonical HMA sl_input choices 3 -> 4",
             "reason": "the old schema names silently collapsed to one mode"},
            {"id": "REV-02", "change": "A08 sizing/route registered: target_mode=signal_notional, "
                                      "backend=native_vectorized, alloc_per_trade=0.1",
             "reason": "pct_equity fallback does not establish a constant target per fold"},
            {"id": "REV-03", "change": "final stitched account timing registered as "
                                      "close_target_v2_same_close",
             "reason": "engine-declared clock; A06 governs the 1m event pilot, not this cohort"},
            {"id": "REV-04", "change": f"corrected MDE frozen at {corrected_mde:.3e} account/day "
                                      f"({corrected_mde*1e4:.4f} bps)",
             "reason": "A15: the old derivation omitted the allocation factor"},
        ],
    }
    scope = {
        "schema": "regime_lab.model_response_scope_decision.v1", "generated_at_utc": utc_now_iso(),
        "decision": ("the primary timing contrast M4_REGIME - M4_CAL depends on the regime-model "
                     "tape, not on the response/bank layer"),
        "scoped_to_rf05": ["A09/E_RESPONSE_V2", "A12 response support", "A13 bank specialists",
                           "G12 lifecycle log", "G13 parity artifact", "G14 runner wiring"],
        "not_scoped_out": ["G10 model ladder/inner-only scaler/common-coordinate mapping (A14)",
                           "G11 QuantBT positive control"],
        "rule": ("these model/positive-control gaps must be closed before any RF-04 result is "
                 "interpreted as treatment strength"),
    }
    clearance = {
        "schema": "regime_lab.gap_clearance.v1", "generated_at_utc": utc_now_iso(),
        "cleared": {"G2": "corrected MDE frozen", "G3": "spec revisions registered",
                    "G4": "legacy oracle quarantined with guard test",
                    "G5": "engine rejection tracking wired",
                    "G6": "final-account timing cohort registered",
                    "G7": "real A-HMA pilot recorded"},
        "remaining": {"G1": "positive-control plan (G11)", "G10": "model repairs (A14)",
                      "G11": "QuantBT positive control", "G8/G9": "low"},
        "pilot": pilot,
    }
    for name, payload in (("mde_corrected.json", mde), ("spec_revisions.json", revisions),
                          ("model_response_scope_decision.json", scope),
                          ("gap_clearance.json", clearance)):
        writer.write_json(name, payload, schema=payload["schema"])
    print(json.dumps({"mde_bps": round(corrected_mde * 1e4, 4), "pilot": pilot,
                      "run_dir": str(writer.run_dir)}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
