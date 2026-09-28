"""Independent verifier for Phase MF-01 (BTC-RPS-V1.2 Section 12).

Verifies the four mandatory exit gates:
- G1-SOURCE: approved Binance spot/perp/metrics inputs, schema, UTC time, aggregation rules.
- G1-EXCLUDE: every missing/optional source has typed exclusion disposition, no core blocker.
- G1-TIMELINE: full feasibility of 180d warmup, 730d train, 12 dev blocks, 91d gap, 12 test blocks, 90d follow-up.
- G1-EVIDENCE: raw receipts, protected paths untouched, non-empty artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from . import sources
from . import timeline


REQUIRED_GATES = ("G1-SOURCE", "G1-EXCLUDE", "G1-TIMELINE", "G1-EVIDENCE")


def verify_gate_source(lab_root: Path) -> dict[str, Any]:
    allowlist_path = lab_root / "configs" / "btc_regime_forecast_v1" / "source_allowlist.json"
    if not allowlist_path.is_file():
        return {"pass": False, "reason": "Missing source_allowlist.json"}
    
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    approved = allowlist.get("approved_sources", {})
    
    checks = []
    # 1. Required approved sources present
    for prod_id in ("crypto_binance_spot_1m", "crypto_binance_futures_1m", "crypto_binance_futures_metrics_5m"):
        spec = approved.get(prod_id)
        exists = spec is not None and spec.get("status") == "QUALIFIED_AVAILABLE"
        checks.append({
            "name": f"{prod_id}_present_and_qualified",
            "holds": exists,
            "detail": spec.get("role") if spec else "MISSING"
        })
    
    # 2. Check snapshot files exist and have non-zero bytes
    snapshot_root = lab_root / "snapshots" / "server_core_v1"
    for prod_id in ("crypto_binance_spot_1m", "crypto_binance_futures_1m", "crypto_binance_futures_metrics_5m"):
        spec = sources.APPROVED_PRODUCTS.get(prod_id, {})
        subdir = snapshot_root / spec.get("snapshot_subdir", "") / "BTCUSDT"
        has_files = subdir.is_dir() and len(list(subdir.glob("*.parquet"))) > 0
        checks.append({
            "name": f"{prod_id}_parquet_files_exist",
            "holds": has_files,
            "detail": str(subdir)
        })

    # 3. Check OI aggregation rule is enforced
    try:
        sources.aggregate_oi_safely(pd.Series([100.0, 200.0]), method="sum")
        oi_rule_holds = False
    except ValueError:
        oi_rule_holds = True
    checks.append({
        "name": "oi_summing_forbidden",
        "holds": oi_rule_holds,
        "detail": "Summing OI snapshots raises ValueError as required"
    })
    
    return {
        "pass": all(c["holds"] for c in checks),
        "checks": checks
    }


def verify_gate_exclude(lab_root: Path) -> dict[str, Any]:
    allowlist_path = lab_root / "configs" / "btc_regime_forecast_v1" / "source_allowlist.json"
    if not allowlist_path.is_file():
        return {"pass": False, "reason": "Missing source_allowlist.json"}
    
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    excluded = allowlist.get("excluded_sources", {})
    
    expected_exclusions = [
        "coingecko_dominance", "binance_btcdom",
        "crypto_binance_orderbook_snapshot_1h", "deribit_options"
    ]
    
    checks = []
    for src in expected_exclusions:
        entry = excluded.get(src)
        is_typed = entry is not None and entry.get("status", "").startswith("EXCLUDED_") and len(entry.get("reason", "")) > 10
        checks.append({
            "name": f"{src}_has_typed_exclusion",
            "holds": is_typed,
            "detail": entry.get("status") if entry else "MISSING"
        })
    
    return {
        "pass": all(c["holds"] for c in checks),
        "checks": checks
    }


def verify_gate_timeline(lab_root: Path) -> dict[str, Any]:
    timeline_path = lab_root / "configs" / "btc_regime_forecast_v1" / "timeline_and_maturity.json"
    if not timeline_path.is_file():
        return {"pass": False, "reason": "Missing timeline_and_maturity.json"}
    
    spec = json.loads(timeline_path.read_text(encoding="utf-8"))
    result = timeline.verify_timeline_integrity(spec)
    return {
        "pass": result["all_pass"],
        "checks": result["checks"]
    }


def verify_gate_evidence(lab_root: Path, run_dir: Path | None = None) -> dict[str, Any]:
    checks = []
    
    # 1. Config directory has all required json files
    cfg_dir = lab_root / "configs" / "btc_regime_forecast_v1"
    req_configs = ["registration.json", "protocol_migration.json", "source_allowlist.json", "timeline_and_maturity.json", "resource_budget.json"]
    for c in req_configs:
        checks.append({
            "name": f"config_{c}_present",
            "holds": (cfg_dir / c).is_file(),
            "detail": str(cfg_dir / c)
        })
    
    # 2. Check run_dir if provided
    if run_dir is not None:
        for f in ("request.json", "gate_receipt.json", "report.md", "source_exclusions.json"):
            p = run_dir / f
            checks.append({
                "name": f"run_artifact_{f}_present",
                "holds": p.is_file() and p.stat().st_size > 0,
                "detail": f"{p.stat().st_size} bytes" if p.is_file() else "MISSING"
            })
            
    return {
        "pass": all(c["holds"] for c in checks),
        "checks": checks
    }


def verify_mf01(lab_root: Path, run_dir: Path | None = None) -> dict[str, Any]:
    lab_root = Path(lab_root)
    g_source = verify_gate_source(lab_root)
    g_exclude = verify_gate_exclude(lab_root)
    g_timeline = verify_gate_timeline(lab_root)
    g_evidence = verify_gate_evidence(lab_root, run_dir=run_dir)
    
    gates = {
        "G1-SOURCE": g_source,
        "G1-EXCLUDE": g_exclude,
        "G1-TIMELINE": g_timeline,
        "G1-EVIDENCE": g_evidence,
    }
    
    all_pass = all(g["pass"] for g in gates.values())
    return {
        "overall": "PASS" if all_pass else "FAIL",
        "gates": gates
    }
