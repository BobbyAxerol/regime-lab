#!/usr/bin/env python
"""LAB-03 closes the three fields LAB-01 registered as null.

  data_roles                  -> registered from the snapshot's real coverage
  instrument_registry_digest  -> inferred from measured tick and quantity steps
  minimum_economic_effect     -> derived from the REGISTERED cost model and the
                                 turnover measured during qualification

The last one matters most: the guide forbids choosing a threshold after seeing a
delta. It is computed here from execution-cost uncertainty and observed trade
frequency, before any arm has been compared.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data.instruments import build_registry  # noqa: E402
from crypto_regime_lab.data.qualification import DECISION_INTERVAL  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
ERA_PARTITIONS = ["2021-06", "2023-06", "2025-06", "2026-06"]
TAKER_FEE = 0.0004
SLIPPAGE = 0.0001
COST_STRESS = (1.0, 1.5, 2.0)


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    configs = policy.lab_root / "configs"
    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]
    with writer.attempt("L03.close.instrument_registry") as att:
        registry = build_registry(snapshot_root, symbols, ERA_PARTITIONS)
        att.detail = {"digest": registry["registry_digest"][:16],
                      "unstable": registry["quantity_step_unstable_symbols"]}
    writer.write_config("instrument_registry.json", registry)
    writer.write_json("instrument_registry.json", registry, schema=registry["schema"])

    qualification = json.loads((configs / "market_qualification.json").read_text())
    per_alpha_turnover = {}
    for record in qualification["results"]:
        if record["status"] != "QUALIFIED":
            continue
        interval = DECISION_INTERVAL[record["alpha_id"]]
        bars_per_day = {"15min": 96, "1h": 24, "4h": 6}[interval]
        days = record["bars"] / bars_per_day
        entries = record["checks"]["entries"]
        per_alpha_turnover.setdefault(record["alpha_id"], []).append(entries / days if days else 0.0)

    round_trips_per_day = {a: sum(v) / len(v) for a, v in per_alpha_turnover.items()}
    busiest = max(round_trips_per_day.values()) if round_trips_per_day else 0.0
    round_trip_cost = 2.0 * (TAKER_FEE + SLIPPAGE)
    stress_span = round_trip_cost * (max(COST_STRESS) - min(COST_STRESS))
    minimum_daily_effect = stress_span * busiest

    effect = {
        "schema": "crypto_regime_lab.minimum_economic_effect.v1",
        "registered_at_utc": utc_now_iso(),
        "registered_before_any_arm_comparison": True,
        "definition": "the smallest mean daily net-return difference the lab will call economically "
                      "meaningful for the primary endpoint",
        "derivation": {
            "taker_fee": TAKER_FEE,
            "slippage": SLIPPAGE,
            "round_trip_cost": round_trip_cost,
            "cost_stress_multipliers": list(COST_STRESS),
            "cost_uncertainty_per_round_trip": stress_span,
            "round_trips_per_day_by_alpha": round_trips_per_day,
            "busiest_alpha_round_trips_per_day": busiest,
            "formula": "cost_uncertainty_per_round_trip * busiest_round_trips_per_day",
        },
        "minimum_daily_net_return_difference": minimum_daily_effect,
        "minimum_daily_net_return_bps": minimum_daily_effect * 1e4,
        "rule": (
            "an improvement smaller than this sits inside the registered cost-stress band and is "
            "reported as inconclusive, not as an edge. The threshold is fixed now, before any arm "
            "has been compared, so it can never be chosen to fit an observed delta (guide 11.2)."
        ),
        "turnover_source": "market qualification on development slices; a smoke measurement, not a "
                           "performance claim",
    }
    writer.write_config("minimum_economic_effect.json", effect)
    writer.write_json("minimum_economic_effect.json", effect, schema=effect["schema"])

    eligibility = json.loads((configs / "data_eligibility.json").read_text())
    study = json.loads((configs / "study_registration.json").read_text())
    with writer.attempt("L03.close.update_registration") as att:
        study["data_roles"] = eligibility["data_roles"]
        study.pop("data_roles_blocker", None)
        study["execution"]["instrument_registry_digest"] = registry["registry_digest"]
        study["execution"]["instrument_registry_artifact"] = "configs/instrument_registry.json"
        study["execution"].pop("instrument_registry_blocker", None)
        study["execution"]["fee_funding_slippage_config"]["funding"] = "MISSING_NOT_ZERO"
        study["execution"]["fee_funding_slippage_config"]["funding_evidence"] = (
            "no funding product exists in this storage; the primary runs use_funding=False and are "
            "labelled a no-funding cohort")
        study["minimum_economic_effect"] = effect["minimum_daily_net_return_difference"]
        study["minimum_economic_effect_artifact"] = "configs/minimum_economic_effect.json"
        study.pop("minimum_economic_effect_blocker", None)
        study["snapshot_id"] = SNAPSHOT_ID
        study["status"] = "REGISTERED_DATA_PINNED"
        study["status_reason"] = (
            "every field LAB-01 left null is now pinned from measured data. The study is registered "
            "and may proceed to LAB-04; it is not FROZEN, which happens at the LAB-08 design freeze."
        )
        study["cohort_coverage"] = {
            name: {"members": rec["members"], "status": rec["status"]}
            for name, rec in eligibility["cohorts"].items()
        }
        att.detail = {"status": study["status"]}
    writer.write_config("study_registration.json", study)
    writer.write_json("study_registration.json", study, schema=study["schema"])

    remaining = [k for k in study if k.endswith("_blocker")] + \
                [k for k in study["execution"] if k.endswith("_blocker")]
    print(f"instrument registry digest : {registry['registry_digest'][:24]}")
    print(f"   unstable qty step       : {registry['quantity_step_unstable_symbols']}")
    print(f"round trips per day        : "
          f"{ {a: round(v, 3) for a, v in round_trips_per_day.items()} }")
    print(f"minimum economic effect    : {effect['minimum_daily_net_return_bps']:.3f} bps per day")
    print(f"data roles                 : {sorted(study['data_roles'])}")
    print(f"study status               : {study['status']}")
    print(f"remaining blockers         : {remaining or 'none'}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
