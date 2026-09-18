#!/usr/bin/env python
"""LAB-03 L03.3 + L03.4 + L03.6 — availability, feature panels, cohorts, data roles.

Reads only the frozen snapshot, closed partitions only. The scaler is fitted on
the DEVELOPMENT role and applied forward; fitting it on the full history would be
the leak guide 6.4 names.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data import panel as P  # noqa: E402
from crypto_regime_lab.data.availability import funding_events, rules_for  # noqa: E402
from crypto_regime_lab.data.eligibility import cohort_report  # noqa: E402
from crypto_regime_lab.data.enrichment import enrichment_inventory  # noqa: E402
from crypto_regime_lab.data.features import GROUP_TITLES, RobustScaler, group_weights  # noqa: E402
from crypto_regime_lab.data.inventory import PRODUCTS  # noqa: E402
from crypto_regime_lab.data.provenance import DOCUMENTED_REVISIONS, provenance_report, repaired_mask  # noqa: E402
from crypto_regime_lab.data.snapshot import verify_snapshot  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
WARMUP_BARS = 30                      # the longest trailing window in the core schema

# Data roles: registered here, which closes one of LAB-01's open blockers.
DATA_ROLES = {
    "development": {"start": "2020-01-01", "end": "2023-12-31",
                    "permits": ["scaler fitting", "hyperparameter and design choices",
                                "inner chronological validation"]},
    "outer_evaluation": {"start": "2024-01-01", "end": None,
                         "permits": ["frozen-protocol evaluation"],
                         "contamination": "NOT an untouched holdout: the supplied presets were "
                                          "TPE-tuned on the full sample with an unknown cutoff"},
}


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = json.loads((snapshot_root / "manifest.json").read_text())

    with writer.attempt("L03.3.verify_read_lock") as att:
        verification = verify_snapshot(manifest)
        att.detail = {"status": verification["status"],
                      "primary_run_valid": verification["primary_run_valid"]}
        if not verification["primary_run_valid"]:
            raise RuntimeError(f"read-lock says {verification['status']}; the panel build stops")

    quality: list[dict] = []
    symbol_frames: dict[str, pd.DataFrame] = {}
    bars_4h: dict[str, pd.DataFrame] = {}

    with writer.attempt("L03.3.resample_regime_bars") as att:
        for symbol in P.MARKET_SYMBOLS:
            bars = P.load_resampled(snapshot_root, "crypto_binance_futures_1m", symbol,
                                    P.REGIME_INTERVAL, quality_out=quality, manifest=manifest)
            bars_4h[symbol] = bars
            symbol_frames[symbol] = P.build_symbol_features(bars)
        att.detail = {"symbols": len(bars_4h),
                      "bars": {s: int(len(b)) for s, b in bars_4h.items()}}

    with writer.attempt("L03.4.market_context") as att:
        market = P.build_market_context(symbol_frames)
        att.detail = {"rows": int(len(market)),
                      "max_eligible": int(market["eligible_symbols"].max())}

    metrics_cache: dict[str, pd.DataFrame] = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        metrics_cache[symbol] = P.load_resampled(
            snapshot_root, "crypto_binance_futures_metrics_5m", symbol, P.REGIME_INTERVAL,
            quality_out=None, manifest=manifest, fail_closed=False)
    spot_btc = P.load_resampled(snapshot_root, "crypto_binance_spot_1m", "BTCUSDT",
                                P.REGIME_INTERVAL, quality_out=None, manifest=manifest,
                                fail_closed=False)
    book_btc = P.load_resampled(snapshot_root, "crypto_binance_orderbook_snapshot_1h", "BTCUSDT",
                                P.REGIME_INTERVAL, quality_out=None, manifest=manifest,
                                fail_closed=False)

    panels: dict[str, pd.DataFrame] = {}
    with writer.attempt("L03.4.assemble_panels") as att:
        for symbol, local in symbol_frames.items():
            frame = P.attach_derivatives(local, metrics_cache.get(symbol))
            frame = P.attach_basis(frame, spot_btc if symbol == "BTCUSDT" else None)
            frame = P.attach_liquidity(frame, book_btc if symbol == "BTCUSDT" else None)
            frame = P.attach_market(frame, market)
            frame["symbol"] = symbol
            panels[symbol] = frame
        att.detail = {"symbols": sorted(panels), "columns": len(next(iter(panels.values())).columns)}

    # ---- scaler fitted on the development role only ----
    dev = DATA_ROLES["development"]
    stacked = pd.concat(panels.values(), ignore_index=True)
    stacked["time"] = pd.to_datetime(stacked["time"])
    train_mask = (stacked["time"] >= dev["start"]) & (stacked["time"] <= dev["end"])
    feature_cols = P.core_feature_columns(stacked)
    # The scaler is fitted over every declared feature so extensions are usable in
    # their own cohorts, but the PRIMARY core is the tier that covers all five
    # symbols, and that is what the regime model is allowed to consume.
    scaler = RobustScaler().fit(stacked.loc[train_mask].reset_index(drop=True), feature_cols)
    primary_active = [f for f in P.PRIMARY_CORE_FEATURES if f in scaler.active_features]
    weights = group_weights(primary_active, P.FEATURE_SPECS)

    coverage = {}
    for name in feature_cols:
        per_symbol = {sym: float(frame[name].notna().mean()) if name in frame.columns else 0.0
                      for sym, frame in panels.items()}
        coverage[name] = {
            "tier": P.feature_tier(name),
            "symbols_with_any_data": sorted(s for s, v in per_symbol.items() if v > 0),
            "non_null_fraction_by_symbol": {s: round(v, 4) for s, v in per_symbol.items()},
            "covers_all_five": all(v > 0 for v in per_symbol.values()),
        }

    # Mask the documented repair window in every panel.
    repair = next(r for r in DOCUMENTED_REVISIONS if r.get("window"))
    for symbol, frame in panels.items():
        frame["in_documented_repair_window"] = repaired_mask(frame, repair)

    out_dir = policy.resolve_write_target(policy.lab_root / "snapshots" / SNAPSHOT_ID / "panels")
    out_dir.mkdir(parents=True, exist_ok=True)
    panel_records = {}
    with writer.attempt("L03.4.standardise_and_write") as att:
        for symbol, frame in panels.items():
            z = scaler.transform(frame)
            z.columns = [f"z_{c}" for c in z.columns]
            merged = pd.concat([frame.reset_index(drop=True), z.reset_index(drop=True)], axis=1)
            target = out_dir / f"{symbol}.parquet"
            merged.to_parquet(target, index=False)
            panel_records[symbol] = {
                "path": str(target), "rows": int(len(merged)),
                "time_min": str(merged["time"].min()), "time_max": str(merged["time"].max()),
                "raw_columns": [c for c in merged.columns if not c.startswith("z_")],
                "standardised_columns": [c for c in merged.columns if c.startswith("z_")],
                "development_rows": int(((merged["time"] >= dev["start"]) &
                                         (merged["time"] <= dev["end"])).sum()),
            }
        att.detail = {"panels": len(panel_records), "active_features": len(scaler.active_features)}

    resample_checks = {}
    probe_symbol = "BTCUSDT"
    probe_partition = sorted(
        r["partition"] for r in manifest["files"]
        if r["product_id"] == "crypto_binance_futures_1m" and r["symbol"] == probe_symbol
        and r["closed"])[40]
    probe_path = (snapshot_root / "crypto_binance_futures_1m" / probe_symbol /
                  f"{probe_partition}.parquet")
    probe_raw, _ = P.normalize_numeric_dtypes(pd.read_parquet(probe_path))
    for target in ("15min", "1h", "4h"):
        from crypto_regime_lab.data.availability import resample_bars

        out = resample_bars(probe_raw, "1min", target)
        expected_per_bucket = out.attrs["expected_bars_per_bucket"]
        first_bucket = probe_raw[probe_raw["time"] < probe_raw["time"].iloc[0] +
                                 pd.Timedelta(target)]
        resample_checks[target] = {
            "buckets": int(len(out)),
            "expected_bars_per_bucket": int(expected_per_bucket),
            "incomplete_buckets_dropped": int(out.attrs["incomplete_buckets_dropped"]),
            "volume_sum_matches": bool(abs(float(out["volume"].iloc[0]) -
                                           float(first_bucket["volume"].sum())) < 1e-9),
            "open_is_first": bool(out["open"].iloc[0] == first_bucket["open"].iloc[0]),
            "close_is_last": bool(out["close"].iloc[0] == first_bucket["close"].iloc[-1]),
            "high_is_max": bool(out["high"].iloc[0] == first_bucket["high"].max()),
            "low_is_min": bool(out["low"].iloc[0] == first_bucket["low"].min()),
        }

    with writer.attempt("L03.1.provenance") as att:
        inventory_doc = json.loads((policy.lab_root / "configs" /
                                    "data_product_inventory.json").read_text())
        provenance = provenance_report(snapshot_root, inventory_doc)
        att.detail = {"docs_match_storage": provenance["documentation_matches_storage"],
                      "repairs": len(provenance["repaired_partitions"])}
    writer.write_config("data_provenance.json", provenance)
    writer.write_json("data_provenance.json", provenance, schema=provenance["schema"])


    schema_doc = {
        "schema": "crypto_regime_lab.feature_schema.v1",
        "snapshot_id": SNAPSHOT_ID,
        "regime_observation_interval": P.REGIME_INTERVAL,
        "groups": GROUP_TITLES,
        "specs": {n: s.as_record() for n, s in P.FEATURE_SPECS.items()},
        "feature_tiers": {k: list(v) for k, v in P.FEATURE_TIERS.items()},
        "primary_core_features": primary_active,
        "primary_core_count": len(primary_active),
        "scaler_active_features": scaler.active_features,
        "coverage_by_feature": coverage,
        "complexity_budget": "guide 6.4 starts at roughly 8-12 active features",
        "budget_respected": 8 <= len(primary_active) <= 12,
        "tier_rule": (
            "only the primary_core tier covers all five symbols and may enter the regime model. "
            "G3 needs the metrics product (BTCUSDT and ETHUSDT only) and G4 needs the book product "
            "(BTCUSDT, weeks only), so they are cohort EXTENSIONS evaluated on their own interval "
            "rather than silently-NaN core columns (guide 6.2)."
        ),
        "dropped_features": scaler.dropped_,
        "group_weights": weights,
        "group_weight_rule": "w_j = omega_g / d_g, so adding features to one block cannot inflate it",
        "scaler": scaler.as_record(),
        "intermediate_aggregates_retained": True,
        "retention_note": "raw feature values are stored alongside the z-scores so any feature can "
                          "be recomputed and audited",
    }
    availability_doc = {
        "schema": "crypto_regime_lab.availability_rules.v1",
        "resample_verification": {
            "probe": f"{probe_symbol} {probe_partition}",
            "targets": resample_checks,
            "rule": "every target is produced and its aggregation contract checked, not only the "
                    "interval the regime model happens to consume",
        },
        "products": {pid: rules_for(pid, spec["kind"], spec["interval"]).as_record()
                     for pid, spec in PRODUCTS.items()},
        "resampling": {
            "source": "1m", "targets": ["15min", "1h", "4h"],
            "ohlc": "first/max/min/last on the CLOSED bucket",
            "flow_columns": "summed in their own units; fractional volume never truncated",
            "level_columns": "open interest and ratios take the LAST value, never a sum",
            "incomplete_buckets": "dropped, never aggregated over a hole",
            "labelling": "left-labelled; the bucket open is the row's `time`",
        },
        "funding": funding_events(snapshot_root),
        "snapshot_products": {
            "crypto_binance_orderbook_snapshot_1h":
                "availability comes from the real sample_time, not the hour label (T26)",
        },
        "fail_closed": "a primary read raises on a quality failure; it never warns and continues",
    }
    # All three resample targets are produced and checked, not just the 4h the
    # regime model consumes (guide L03.3).
    eligibility = cohort_report(manifest, list(P.MARKET_SYMBOLS), WARMUP_BARS)
    eligibility["data_roles"] = DATA_ROLES
    eligibility["documented_revisions"] = DOCUMENTED_REVISIONS
    eligibility["repair_mask_column"] = "in_documented_repair_window"
    enrichment = enrichment_inventory()

    quality_summary = {
        "schema": "crypto_regime_lab.data_quality_report.v1",
        "partitions_checked": len(quality),
        "partitions_failed": sum(1 for q in quality if not q["passed"]),
        "close_time_untrusted_partitions": sum(
            1 for q in quality if not q["checks"]["close_time_trust"]["trusted"]),
        "close_time_defect_by_symbol": {},
        "quantity_granularity_by_symbol": {},
        "dtype_coercion_by_symbol": {},
        "total_missing_bars": int(sum(q["checks"]["gaps"]["missing_bars"] for q in quality)),
        "partitions": quality,
    }
    for q in quality:
        entry = quality_summary["close_time_defect_by_symbol"].setdefault(
            q["symbol"], {"partitions": 0, "untrusted": 0, "epoch_defect_rows": 0,
                          "equal_to_open_rows": 0})
        entry["partitions"] += 1
        trust = q["checks"]["close_time_trust"]
        entry["untrusted"] += int(not trust["trusted"])
        entry["epoch_defect_rows"] += int(trust.get("epoch_unit_defect_rows", 0))
        entry["equal_to_open_rows"] += int(trust.get("equal_to_open_rows", 0))
        coerced = q.get("stored_dtypes_coerced") or {}
        if coerced:
            entry_dtypes = quality_summary["dtype_coercion_by_symbol"].setdefault(
                q["symbol"], {"partitions": [], "columns": {}})
            entry_dtypes["partitions"].append(q["partition"])
            for column, dtype in coerced.items():
                entry_dtypes["columns"].setdefault(column, set()).add(dtype)
        gran = q["checks"].get("quantity_granularity", {})
        if gran.get("applicable"):
            g = quality_summary["quantity_granularity_by_symbol"].setdefault(
                q["symbol"], {"integral_only_partitions": [], "fractional_partitions": []})
            bucket = "integral_only_partitions" if gran["integral_only"] else "fractional_partitions"
            g[bucket].append(q["partition"])

    for symbol, rec in quality_summary["dtype_coercion_by_symbol"].items():
        rec["columns"] = {c: sorted(v) for c, v in rec["columns"].items()}
        rec["partition_count"] = len(rec["partitions"])
        rec["first_partition"] = min(rec["partitions"])
        rec["last_partition"] = max(rec["partitions"])
        rec["consequence"] = (
            "the stored dtype is integral for these partitions, so any fractional quantity would "
            "already have been lost upstream; the lab coerces to float64 on read so a feature's "
            "dtype never depends on which month it came from, and records the resolution limit")

    for symbol, gran in quality_summary["quantity_granularity_by_symbol"].items():
        integral = gran["integral_only_partitions"]
        fractional = gran["fractional_partitions"]
        gran["step_changed_during_sample"] = bool(integral and fractional)
        gran["first_fractional_partition"] = min(fractional) if fractional else None
        gran["last_integral_partition"] = max(integral) if integral else None
        gran["consequence"] = (
            "the instrument's quantity step is not constant over the sample; a single pinned "
            "step in the instrument registry would be wrong for part of the history"
            if gran["step_changed_during_sample"] else
            "granularity is stable over the sampled partitions")

    for name, doc in (("feature_schema.json", schema_doc),
                      ("availability_rules.json", availability_doc),
                      ("data_eligibility.json", eligibility),
                      ("enrichment_inventory.json", enrichment)):
        writer.write_config(name, doc)
        writer.write_json(name, doc, schema=doc["schema"])
    writer.write_json("data_quality_report.json", quality_summary, schema=quality_summary["schema"])
    writer.write_json("feature_panels.json", {
        "schema": "crypto_regime_lab.feature_panels.v1",
        "snapshot_id": SNAPSHOT_ID, "panels": panel_records}, schema="crypto_regime_lab.feature_panels.v1")

    print(f"read-lock          : {verification['status']} (primary valid={verification['primary_run_valid']})")
    print(f"regime bars ({P.REGIME_INTERVAL})  : " +
          ", ".join(f"{s}={len(b)}" for s, b in bars_4h.items()))
    print(f"partitions checked : {quality_summary['partitions_checked']} "
          f"failed={quality_summary['partitions_failed']} "
          f"close_time_untrusted={quality_summary['close_time_untrusted_partitions']}")
    print(f"primary core       : {len(primary_active)} features -> {primary_active}")
    print(f"scaler active      : {len(scaler.active_features)} / {len(feature_cols)}")
    for tier in ("derivatives_extension", "liquidity_extension", "registered_alternative"):
        members = [f for f in P.FEATURE_TIERS[tier] if f in scaler.active_features]
        print(f"   {tier:<24} {members}")
    if scaler.dropped_:
        for name, reason in scaler.dropped_.items():
            print(f"   dropped {name}: {reason[:70]}")
    print("cohorts            : " + ", ".join(
        f"{k}={v['member_count']}" for k, v in eligibility["cohorts"].items()))
    print(f"common period      : {eligibility['five_symbol_common_period']}")
    print(f"funding            : {availability_doc['funding']['status']}")
    print("resample targets   : " + ", ".join(
        f"{k}({v['buckets']} buckets, ok={all([v['volume_sum_matches'], v['open_is_first'], v['close_is_last'], v['high_is_max'], v['low_is_min']])})"
        for k, v in resample_checks.items()))
    print(f"provenance         : docs_match_storage={provenance['documentation_matches_storage']} "
          f"repairs={len(provenance['repaired_partitions'])} "
          f"classes={provenance['vintage_classification_counts']}")
    for symbol, rec in quality_summary["dtype_coercion_by_symbol"].items():
        print(f"   dtype coerced      : {symbol} {rec['partition_count']} partitions "
              f"{rec['columns']} ({rec['first_partition']}..{rec['last_partition']})")
    for symbol, gran in quality_summary["quantity_granularity_by_symbol"].items():
        if gran["step_changed_during_sample"]:
            print(f"   qty step changed   : {symbol} integral through {gran['last_integral_partition']}, "
                  f"fractional from {gran['first_fractional_partition']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
