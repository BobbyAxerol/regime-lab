"""Timeline and 36-fold schedule generator for btc_volatility_conditioned_wfo_v1.

Follows VOL-WFO-V1.0 Section 5:
- 12 candidate-forward origins matured in WFO-INIT (cadence 14d)
- 12 common 14-day forward folds in WFO-DEV (cadence 14d)
- Freeze boundary and maturity gap between DEV and FINAL
- 12 common paired-valid 14-day folds in WFO-FINAL (cadence 14d)
- D2 follow-up continuation of 28 days on the final anchor
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List


def d(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


def build_wfo_timeline_spec() -> Dict[str, Any]:
    """Generates the canonical 36-decision WFO timeline specification."""
    cadence_days = 14
    folds_per_role = 12

    # INIT: 12 origins, bi-weekly
    init_start = d("2024-04-13")
    init_origins = [(init_start + datetime.timedelta(days=i * cadence_days)).isoformat() for i in range(folds_per_role)]
    init_last_end = (init_start + datetime.timedelta(days=(folds_per_role - 1) * cadence_days + cadence_days)).isoformat()

    # DEV: 12 folds, bi-weekly (starts after INIT maturity)
    dev_start = d("2024-10-12")
    dev_origins = [(dev_start + datetime.timedelta(days=i * cadence_days)).isoformat() for i in range(folds_per_role)]
    dev_last_end = (dev_start + datetime.timedelta(days=(folds_per_role - 1) * cadence_days + cadence_days)).isoformat()

    # FINAL: 12 folds, bi-weekly (starts 2025-06-07 after freeze)
    final_start = d("2025-06-07")
    final_origins = [(final_start + datetime.timedelta(days=i * cadence_days)).isoformat() for i in range(folds_per_role)]
    final_last_end = (final_start + datetime.timedelta(days=(folds_per_role - 1) * cadence_days + cadence_days)).isoformat()
    d2_end = (final_start + datetime.timedelta(days=(folds_per_role - 1) * cadence_days + 28)).isoformat()

    spec = {
        "schema": "regime_lab.vol_wfo_timeline.v1",
        "study_id": "btc_volatility_conditioned_wfo_v1",
        "version": "VOL-WFO-V1.0",
        "cadence_days": cadence_days,
        "folds_per_role": folds_per_role,
        "candidate_is_days": 180,
        "forward_eval_days": 14,
        "d2_continuation_days": 28,
        "data_boundaries": {
            "spot_earliest": "2018-01-01",
            "perp_earliest": "2020-01-01",
            "metrics_earliest": "2020-09-01",
            "spot_latest_closed_day": "2026-08-07"
        },
        "model_training_prefix": {
            "start": "2022-01-14",
            "end": "2024-01-13",
            "days": 730,
            "status": "MATURED_BEFORE_INIT"
        },
        "roles": {
            "INIT": {
                "role": "CANDIDATE_ARCHIVE_INITIATION",
                "origin_count": folds_per_role,
                "origins": init_origins,
                "first_origin": init_origins[0],
                "last_origin": init_origins[-1],
                "first_window_start": init_origins[0],
                "last_window_end": init_last_end,
                "maturity_utc": f"{init_last_end}T00:00:00+00:00",
                "notes": "12 bi-weekly origins to generate candidate archive labels D = SR_IS - SR_FWD before DEV."
            },
            "DEV": {
                "role": "SELECTION_DEVELOPMENT",
                "origin_count": folds_per_role,
                "origins": dev_origins,
                "first_origin": dev_origins[0],
                "last_origin": dev_origins[-1],
                "first_window_start": dev_origins[0],
                "last_window_end": dev_last_end,
                "maturity_utc": f"{dev_last_end}T00:00:00+00:00",
                "notes": "12 common bi-weekly folds for TPE vs Sobol evaluation and sampler freeze."
            },
            "FREEZE_BOUNDARY": {
                "freeze_start": dev_last_end,
                "freeze_end": final_origins[0],
                "gap_days": (d(final_origins[0]) - d(dev_last_end)).days,
                "notes": "70-day freeze gap ensuring all DEV outcomes mature before FINAL start."
            },
            "FINAL": {
                "role": "CONFIRMATORY_FINAL_WFO",
                "origin_count": folds_per_role,
                "origins": final_origins,
                "first_origin": final_origins[0],
                "last_origin": final_origins[-1],
                "first_window_start": final_origins[0],
                "last_window_end": final_last_end,
                "maturity_utc": f"{final_last_end}T00:00:00+00:00",
                "d2_last_anchor_end": d2_end,
                "d2_maturity_utc": f"{d2_end}T00:00:00+00:00",
                "notes": "12 paired-valid final folds on the winning sampler + 28-day D2 continuation."
            }
        }
    }
    return spec


def verify_wfo_timeline(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Validates all mathematical and causality constraints of the WFO timeline."""
    checks = []

    init = spec["roles"]["INIT"]
    dev = spec["roles"]["DEV"]
    freeze = spec["roles"]["FREEZE_BOUNDARY"]
    final = spec["roles"]["FINAL"]
    bounds = spec["data_boundaries"]

    # 1. INIT origins count == 12
    checks.append({
        "check": "init_origins_count_is_12",
        "holds": len(init["origins"]) == 12,
        "detail": f"{len(init['origins'])} origins"
    })

    # 2. DEV origins count == 12
    checks.append({
        "check": "dev_origins_count_is_12",
        "holds": len(dev["origins"]) == 12,
        "detail": f"{len(dev['origins'])} origins"
    })

    # 3. FINAL origins count == 12
    checks.append({
        "check": "final_origins_count_is_12",
        "holds": len(final["origins"]) == 12,
        "detail": f"{len(final['origins'])} origins"
    })

    # 4. Total forward windows == 36
    total_w = len(init["origins"]) + len(dev["origins"]) + len(final["origins"])
    checks.append({
        "check": "total_decision_windows_is_36",
        "holds": total_w == 36,
        "detail": f"{total_w} windows (504 forward days)"
    })

    # 5. INIT matures strictly before DEV starts
    init_matures = d(init["last_window_end"])
    dev_starts = d(dev["first_origin"])
    checks.append({
        "check": "init_matures_before_dev_starts",
        "holds": init_matures <= dev_starts,
        "detail": f"INIT matures {init_matures} <= DEV starts {dev_starts} (gap: {(dev_starts - init_matures).days}d)"
    })

    # 6. DEV matures strictly before FINAL starts
    dev_matures = d(dev["last_window_end"])
    final_starts = d(final["first_origin"])
    checks.append({
        "check": "dev_matures_before_final_starts",
        "holds": dev_matures <= final_starts,
        "detail": f"DEV matures {dev_matures} <= FINAL starts {final_starts} (gap: {(final_starts - dev_matures).days}d)"
    })

    # 7. Candidate IS 180 lookback for Fold 0 is covered by market data
    first_init = d(init["first_origin"])
    is_lookback_start = first_init - datetime.timedelta(days=spec["candidate_is_days"])
    perp_earliest = d(bounds["perp_earliest"])
    checks.append({
        "check": "first_init_is_lookback_covered",
        "holds": is_lookback_start >= perp_earliest,
        "detail": f"IS lookback start {is_lookback_start} >= Perp data start {perp_earliest}"
    })

    # 8. All FINAL folds and D2 complete strictly before data cutoff
    d2_end = d(final["d2_last_anchor_end"])
    cutoff = d(bounds["spot_latest_closed_day"])
    checks.append({
        "check": "all_evaluations_before_data_cutoff",
        "holds": d2_end <= cutoff,
        "detail": f"D2 end {d2_end} <= Closed data cutoff {cutoff}"
    })

    # 9. All origins on exact 14-day stride
    def check_stride(origins: List[str]) -> bool:
        dates = [d(o) for o in origins]
        diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        return all(diff == 14 for diff in diffs)

    checks.append({
        "check": "all_roles_use_exact_14d_stride",
        "holds": check_stride(init["origins"]) and check_stride(dev["origins"]) and check_stride(final["origins"]),
        "detail": "INIT, DEV, and FINAL strictly spaced by 14 days"
    })

    all_pass = all(c["holds"] for c in checks)
    return {
        "status": "PASS" if all_pass else "FAIL",
        "checks_count": len(checks),
        "passed_count": sum(1 for c in checks if c["holds"]),
        "checks": checks
    }
