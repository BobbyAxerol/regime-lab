"""Timeline, block splitting, and maturity resolution for btc_regime_forecast_v1.

Follows BTC-RPS-V1.2 Section 1, Section 6, Section 12 (MF-01).
- 180-day raw feature warmup
- 730 initial daily training origins
- 12 Development blocks x 28 days = 48 weekly origins
- 91-day maturity gap ensuring all validation H=90 labels mature before Test
- 12 Locked Test blocks x 28 days = 48 weekly origins
- H=90 follow-up completed before data cutoff
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any


def load_timeline_spec(lab_root: Path | None = None) -> dict[str, Any]:
    if lab_root is None:
        lab_root = Path(__file__).resolve().parents[3]
    path = lab_root / "configs" / "btc_regime_forecast_v1" / "timeline_and_maturity.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing timeline spec: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compute_target_window(origin_date: str, horizon_days: int, ready_lag_days: int = 1) -> dict[str, str]:
    """Computes target_start, target_end and label_available_at for an origin."""
    d = datetime.date.fromisoformat(origin_date)
    start = d + datetime.timedelta(days=ready_lag_days)
    end = start + datetime.timedelta(days=horizon_days)
    return {
        "origin_date": origin_date,
        "horizon_days": horizon_days,
        "ready_lag_days": ready_lag_days,
        "target_start": start.isoformat(),
        "target_end": end.isoformat(),
        "label_available_at_utc": f"{end.isoformat()}T00:00:00+00:00",
    }


def generate_weekly_origins(first_origin: str, count: int = 48, stride_days: int = 7) -> list[str]:
    d0 = datetime.date.fromisoformat(first_origin)
    return [(d0 + datetime.timedelta(days=i * stride_days)).isoformat() for i in range(count)]


def generate_daily_training_origins(start_date: str, count: int = 730) -> list[str]:
    d0 = datetime.date.fromisoformat(start_date)
    return [(d0 + datetime.timedelta(days=i)).isoformat() for i in range(count)]


def build_evaluation_schedule(role: str, timeline_spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Builds the 48-origin weekly schedule for Development or Locked Test."""
    if role not in ("development", "locked_test"):
        raise ValueError(f"Unsupported evaluation role: '{role}'")
    
    spec = timeline_spec[role]
    first_origin = spec["first_origin"]
    origins = generate_weekly_origins(first_origin, count=spec["weekly_origins_count"], stride_days=timeline_spec["weekly_stride_days"])
    
    schedule = []
    for i, orig in enumerate(origins):
        block_idx = i // 4
        orig_in_block = i % 4
        h56 = compute_target_window(orig, horizon_days=56, ready_lag_days=timeline_spec["ready_lag_days"])
        h90 = compute_target_window(orig, horizon_days=90, ready_lag_days=timeline_spec["ready_lag_days"])
        schedule.append({
            "origin_index": i,
            "origin_date": orig,
            "role": role,
            "block_index": block_idx,
            "origin_in_block": orig_in_block,
            "horizons": {
                "56": h56,
                "90": h90,
            }
        })
    return schedule


def verify_timeline_integrity(timeline_spec: dict[str, Any]) -> dict[str, Any]:
    """Strict mathematical verification of all timeline contracts (§6.2, MF1-T07)."""
    checks = []
    
    # 1. Warmup >= 180 days
    warmup = timeline_spec["warmup"]
    w_start = datetime.date.fromisoformat(warmup["start_date"])
    w_end = datetime.date.fromisoformat(warmup["end_date"])
    w_days = (w_end - w_start).days + 1
    checks.append({
        "check": "warmup_days_ge_180",
        "holds": w_days >= 180,
        "detail": f"{w_days} days [{warmup['start_date']} to {warmup['end_date']}]"
    })
    
    # 2. Initial training >= 730 daily origins
    train = timeline_spec["initial_training"]
    t_start = datetime.date.fromisoformat(train["start_date"])
    t_end = datetime.date.fromisoformat(train["end_date"])
    t_days = (t_end - t_start).days + 1
    checks.append({
        "check": "initial_training_days_ge_730",
        "holds": t_days >= 730,
        "detail": f"{t_days} daily origins [{train['start_date']} to {train['end_date']}]"
    })
    
    # 3. Last training origin H90 matures before first validation origin
    dev = timeline_spec["development"]
    t_last_target_end = t_end + datetime.timedelta(days=1 + 90)
    dev_first = datetime.date.fromisoformat(dev["first_origin"])
    checks.append({
        "check": "training_h90_matures_before_or_at_dev_first",
        "holds": t_last_target_end <= dev_first,
        "detail": f"Last train H90 mature: {t_last_target_end}, Dev first: {dev_first}"
    })
    
    # 4. Development has 12 blocks, 48 weekly origins
    dev_origins = generate_weekly_origins(dev["first_origin"], count=dev["weekly_origins_count"], stride_days=7)
    checks.append({
        "check": "development_48_weekly_origins_12_blocks",
        "holds": len(dev_origins) == 48 and dev["block_count"] == 12,
        "detail": f"{len(dev_origins)} origins, 12 blocks"
    })
    
    # 5. Last validation origin H90 matures before first test origin
    dev_last_origin = datetime.date.fromisoformat(dev["last_origin"])
    dev_last_h90_end = dev_last_origin + datetime.timedelta(days=1 + 90)
    test = timeline_spec["locked_test"]
    test_first = datetime.date.fromisoformat(test["first_origin"])
    checks.append({
        "check": "dev_last_h90_matures_before_or_at_test_first",
        "holds": dev_last_h90_end <= test_first,
        "detail": f"Dev last H90 mature: {dev_last_h90_end}, Test first: {test_first}"
    })
    
    # 6. Test has 12 blocks, 48 weekly origins
    test_origins = generate_weekly_origins(test["first_origin"], count=test["weekly_origins_count"], stride_days=7)
    checks.append({
        "check": "test_48_weekly_origins_12_blocks",
        "holds": len(test_origins) == 48 and test["block_count"] == 12,
        "detail": f"{len(test_origins)} origins, 12 blocks"
    })
    
    # 7. Last test origin H90 matures on or before actual spot data cutoff
    test_last_origin = datetime.date.fromisoformat(test["last_origin"])
    test_last_h90_end = test_last_origin + datetime.timedelta(days=1 + 90)
    spot_latest = datetime.date.fromisoformat(timeline_spec["data_boundaries"]["spot_latest_closed_day"])
    checks.append({
        "check": "test_last_h90_followup_fully_covered",
        "holds": test_last_h90_end <= spot_latest,
        "detail": f"Test last H90 mature: {test_last_h90_end}, Spot latest: {spot_latest} (margin: {(spot_latest - test_last_h90_end).days} days)"
    })
    
    all_pass = all(c["holds"] for c in checks)
    return {
        "all_pass": all_pass,
        "checks": checks
    }
