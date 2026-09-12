#!/usr/bin/env python
"""RF-04 step 1 — G11 QuantBT positive control and the registered discovery protocol.

A synthetic world has KNOWN regime switches. The online controller fires at the
real transitions; the event account (QuantBT is the simulator) activates the
parameters the treatment selected. The control is that the treatment changes the
effective parameters and the trades against a calendar schedule on the same
hardware. Ground-truth labels are used only to place the switches, never as a
policy input.
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
from crypto_regime_lab.experiments.regime_schedule import online_trigger_schedule  # noqa: E402
from crypto_regime_lab.integration.continuous_account import VersionWindow  # noqa: E402
from crypto_regime_lab.integration.event_account import run_event_account  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-04"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
STATE0 = {"coeff": 2, "AP": 8, "alpha.condition_threshold": 35, "novolumedata": False,
          "src_col": "close"}
STATE1 = dict(SEED_POINTS["A-SC"])


def world(n: int = 2400, seed: int = 23) -> tuple[pd.DataFrame, list[dict]]:
    rng = np.random.default_rng(seed)
    close = np.empty(n)
    switches = [400, 900, 1400, 1900]
    state = 0
    path = []
    level = 100.0
    for i in range(n):
        if i in switches:
            state = 1 - state
        drift = 0.06 if state == 1 else -0.06
        level = max(5.0, level + drift + rng.normal(0, 0.08))
        close[i] = level
        path.append(state)
    frame = pd.DataFrame({"open": np.r_[close[0], close[:-1]],
                          "high": close + 0.3, "low": close - 0.3, "close": close,
                          "volume": np.full(n, 1000.0)},
                         index=pd.date_range("2021-01-01", periods=n, freq="1h", tz="UTC"))
    emissions = [{"state_id": path[max(0, b - 1)], "state_namespace": "synth",
                  "state_common": path[max(0, b - 1)], "decision_eligible": True,
                  "quality_status": "OK", "available_at": frame.index[b].isoformat()}
                 for b in range(2, n)]
    return frame, emissions


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    frame, emissions = world()
    schedule = online_trigger_schedule(emissions, earliest=str(frame.index[0].date()),
                                       latest=str(frame.index[-1].date()), min_gap_days=5.0)
    cutoffs = [int(frame.index.searchsorted(pd.Timestamp(c))) for c in schedule.cutoffs]
    params_for_state = {0: STATE0, 1: STATE1}
    state_by_bar = np.zeros(len(frame), dtype=int)
    state = 0
    for i in range(len(frame)):
        if i in (400, 900, 1400, 1900):
            state = 1 - state
        state_by_bar[i] = state
    regime_windows = [VersionWindow(f"regime-{i}", dict(params_for_state[state_by_bar[b]]), b,
                                    f"act-{i}") for i, b in enumerate(cutoffs) if b > 0]
    initial = VersionWindow("regime-initial", dict(params_for_state[state_by_bar[0]]), 0, "act-0")
    regime = run_event_account("A-SC", frame, initial=initial, schedule=regime_windows)

    calendar_windows = [VersionWindow("cal-1", dict(STATE1), 500, "cal-1"),
                        VersionWindow("cal-2", dict(STATE0), 1000, "cal-2"),
                        VersionWindow("cal-3", dict(STATE1), 1500, "cal-3"),
                        VersionWindow("cal-4", dict(STATE0), 2000, "cal-4")]
    calendar = run_event_account("A-SC", frame, initial=initial, schedule=calendar_windows)

    last = cutoffs[-1] if cutoffs else 0
    treatment = {
        "controller_cutoffs_bars": cutoffs,
        "regime_versions_after_last_cutoff": regime.version_by_bar[last:last + 3],
        "calendar_versions_after_last_cutoff": calendar.version_by_bar[last:last + 3],
        "params_changed_by_treatment": bool(regime.version_by_bar != calendar.version_by_bar),
        "regime": {"status": regime.status, "entries": regime.entries,
                   "engine_fills": regime.engine_fill_count, "equity": float(regime.equity[-1])},
        "calendar": {"status": calendar.status, "entries": calendar.entries,
                     "engine_fills": calendar.engine_fill_count, "equity": float(calendar.equity[-1])},
        "treatment_reached_execution": (regime.status == "EVALUATED"
                                        and regime.engine_fill_count != calendar.engine_fill_count),
        "ground_truth_use": "switch bars only place the synthetic world; the policy reads emissions",
    }
    protocol = {
        "schema": "regime_lab.rf04_discovery_protocol.v1", "generated_at_utc": utc_now_iso(),
        "status": "REGISTERED_BEFORE_DISCOVERY_RUNS",
        "primary_arms": ["M4_CAL", "M4_REGIME"], "cells_planned": 20,
        "cohort": {"symbols": list(SYMBOLS), "alphas": ["A-SC", "A-HMA", "A-VWAP", "A-HASH"],
                   "data": "server_core_v1, development 2021-01-01..2023-12-31"},
        "budgets": {"pilot_trials_per_cutoff": 32, "freeze_after_coverage_review": True,
                    "tier_caps_seconds": {"T2": 600, "T3": 900}},
        "mde": {"corrected_daily_account_bps": 0.0371,
                "artifact": "evidence/corrective_mode4_v3/pre-RF04-clearing/mde_corrected.json"},
        "gates": {"must_close_before_results": ["G10 model repairs (A14)",
                                                "G11 positive control (this artifact)"]},
        "decay_panels": ["D1 IS->OOS", "D2 fixed-parameter age", "D3 adjacent operational folds"],
        "controls_order": ["M4_CAL_MATCHED after the pilot", "delayed-state/placebo if budget allows"],
    }
    for name, payload in (("positive_control.json", treatment), ("discovery_protocol.json", protocol)):
        writer.write_json(name, payload, schema=payload.get("schema", "regime_lab.rf04_positive_control.v1"))
    print(json.dumps(treatment, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
