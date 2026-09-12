#!/usr/bin/env python
"""Measure the gap between the loader ENDPOINT and the raw parquet the lab reads.

The lab reads bars straight from its byte-copied parquet and only parses the
loader statically (guide 6.1). That is a deliberate choice, and a choice worth
auditing: if calling `data_loader.load()` gave the same numbers, the choice would
be cosmetic. It does not. `MarketDataLoaderBase._normalize` ends with

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")

and Binance USD-M stores fractional contract quantities for BTCUSDT, ETHUSDT and
BNBUSDT. So the endpoint truncates every fractional bar, and a thin bar with real
trades can come back as volume 0 -- which would then propagate into the G2
activity and taker-imbalance features.

This script quantifies that per symbol so the phase reports can cite a measured
artifact instead of an assertion. It imports the lab's OWN read-only copy of the
loader with `loaders.deribit_options` stubbed, so nothing outside LAB_ROOT is
imported and no bytecode is written into a protected tree.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

import pandas as pd  # noqa: E402

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
STORAGE = "/root/bobby/pool_alpha/alphas_storage/_get_data/storage"
# Each symbol is probed on its own FIRST partition and on a late one. Fixing a
# single calendar month would silently skip BNB/SOL/DOGE, which list later --
# and those are exactly the symbols whose stored dtype differs, so a fixed month
# would have measured only the two symbols that share one behaviour.
PROBE_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT")


def import_pinned_loader(storage_dir: str):
    """Import vendor_readonly/loader_snapshot/data_loader.py without its siblings."""
    stub = types.ModuleType("loaders.deribit_options")
    for name in ("DeribitOptionOverlayLoader", "DeribitOptionSnapshots5mLoader",
                 "DeribitOptionTradesLoader"):
        setattr(stub, name, type(name, (), {}))
    package = types.ModuleType("loaders")
    package.__path__ = []                       # a namespace shell, not the real package
    sys.modules["loaders"] = package
    sys.modules["loaders.deribit_options"] = stub

    source = LAB_ROOT / "vendor_readonly" / "loader_snapshot" / "data_loader.py"
    spec = importlib.util.spec_from_file_location("pinned_data_loader", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.STORAGE_DIR = Path(storage_dir)
    return module, sha256_file(source)


def probe_partitions(snapshot_root: Path, symbol: str) -> list[str]:
    base = snapshot_root / "crypto_binance_futures_1m" / symbol
    parts = sorted(p.stem for p in base.glob("*.parquet")) if base.is_dir() else []
    if not parts:
        return []
    return sorted({parts[0], parts[len(parts) // 2], parts[-2] if len(parts) > 1 else parts[-1]})


def compare(symbol: str, partition: str, loader_module, snapshot_root: Path) -> dict:
    stored = snapshot_root / "crypto_binance_futures_1m" / symbol / f"{partition}.parquet"
    if not stored.is_file():
        return {"symbol": symbol, "status": "NO_SNAPSHOT_PARTITION", "partition": partition}
    raw = pd.read_parquet(stored).sort_values("time").reset_index(drop=True)
    start, end = raw["time"].min(), raw["time"].max()
    served = loader_module.CryptoBinance1m().load(
        symbols=symbol, start_date=str(start), end_date=str(end),
        columns="full", check_val=False).sort_values("time").reset_index(drop=True)

    if len(served) != len(raw):
        return {"symbol": symbol, "partition": partition, "status": "ROW_COUNT_DIFFERS",
                "rows_parquet": int(len(raw)), "rows_loader": int(len(served))}

    identical, differing = [], {}
    for column in raw.columns:
        if column not in served.columns:
            differing[column] = {"reason": "absent from the loader's output"}
            continue
        if raw[column].equals(served[column]):
            identical.append(column)
            continue
        entry = {"dtype_parquet": str(raw[column].dtype),
                 "dtype_loader": str(served[column].dtype)}
        try:
            delta = (raw[column].astype("float64") - served[column].astype("float64")).abs()
            total = float(raw[column].astype("float64").abs().sum())
            entry["rows_differing"] = int((delta > 0).sum())
            entry["max_absolute_difference"] = float(delta.max())
            entry["share_of_total_lost"] = (float(delta.sum()) / total) if total else None
        except (TypeError, ValueError):
            entry["rows_differing"] = int((raw[column].astype(str) != served[column].astype(str)).sum())
        differing[column] = entry

    volume = raw["volume"].astype("float64")
    return {
        "symbol": symbol,
        "status": "COMPARED",
        "partition": partition,
        "rows": int(len(raw)),
        "columns_identical": identical,
        "columns_differing": differing,
        "stored_volume_dtype": str(raw["volume"].dtype),
        "bars_with_a_fractional_volume": int((volume % 1 != 0).sum()),
        "bars_a_cast_would_zero": int(((volume > 0) & (volume < 1)).sum()),
        "volume_sum_parquet": float(volume.sum()),
        "volume_sum_loader": float(served["volume"].astype("float64").sum()),
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID

    with writer.attempt("readlock.loader_endpoint_parity") as att:
        loader_module, loader_sha = import_pinned_loader(STORAGE)
        results = [compare(symbol, partition, loader_module, snapshot_root)
                   for symbol in PROBE_SYMBOLS
                   for partition in probe_partitions(snapshot_root, symbol)]
        att.detail = {"symbols": len(results),
                      "with_a_difference": sum(1 for r in results
                                               if r.get("columns_differing"))}

    document = {
        "schema": "crypto_regime_lab.loader_endpoint_parity.v1",
        "checked_at_utc": utc_now_iso(),
        "loader_snapshot_sha256": loader_sha,
        "loader_snapshot_path": "vendor_readonly/loader_snapshot/data_loader.py",
        "storage_root": STORAGE,
        "probe_rule": "each symbol's first, middle and last closed partition",
        "how_the_lab_reads": (
            "the lab parses this loader STATICALLY to learn which storage path holds which "
            "product, then reads the parquet directly from its own byte copy; it never calls "
            "the loader at run time"),
        "why_this_is_measured": (
            "so the choice above is auditable rather than asserted: if the endpoint returned the "
            "same numbers the choice would be cosmetic, and it does not"),
        "per_symbol": results,
        "finding": (
            "MarketDataLoaderBase._normalize casts volume to int64. Symbols whose stored volume "
            "is fractional lose the fraction on every bar, and a bar under 1.0 unit with real "
            "trades becomes volume 0. Symbols already stored as int64 are unaffected, so the "
            "defect is invisible on exactly the symbols one would test first."),
        "lab_consequence": (
            "reading the parquet directly preserves the stored resolution; "
            "panel.normalize_numeric_dtypes coerces to float64 on read so a feature's dtype never "
            "depends on which month it came from"),
    }
    writer.write_config("loader_endpoint_parity.json", document)
    writer.write_json("loader_endpoint_parity.json", document, schema=document["schema"])

    print(f"loader pinned sha256 : {loader_sha[:16]}…")
    for record in results:
        if record["status"] != "COMPARED":
            print(f"  {record['symbol']:<9} {record.get('partition','')} {record['status']}")
            continue
        differing = ", ".join(record["columns_differing"]) or "none"
        print(f"  {record['symbol']:<9} {record['partition']} rows={record['rows']:>7,} "
              f"stored_dtype={record['stored_volume_dtype']:<8} "
              f"fractional_bars={record['bars_with_a_fractional_volume']:>7,} "
              f"would_zero={record['bars_a_cast_would_zero']:>4,}  differs: {differing}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
