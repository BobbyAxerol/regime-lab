"""RA05.1: real market data and real regime emissions for the pilot cell.

RA-05 is the first RA phase to make an actual economic comparison (guide
section 9), so unlike RA-02/RA-03/RA-04's phase-owned SYNTHETIC fixtures
(`route_qualification.synthetic_bars`), this module reads REAL data:

* Real BTCUSDT 1-minute bars from the already-pinned, already-hashed
  `snapshots/server_core_v1/manifest.json` snapshot (the same read-only
  snapshot LAB-01..09 and RF-01..05 used) -- never the live loader, never
  `../alphas_storage` directly.
* Real regime-model emissions from `evidence/time_edge_validation_v4/
  host-emissions-03.json` (schema `regime_lab.te03_emissions...`, lab_run_id
  `TE03-EMISSIONS-03`), a committed artifact of 4841 real emissions from a
  29-vintage JM/M0 ladder fit on real BTCUSDT features, 2021-02-01 to
  2023-04-18 -- this is the SAME artifact F-05 measured ("5/29 vintages JM,
  24 M0") and reused here rather than re-fit (guide 4.2: reuse evidence,
  don't force a rerun; RA01.2: findings with source/runtime proof are
  reused, not rewritten).
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd

from .phase_common import LAB

SNAPSHOT_MANIFEST = LAB / "snapshots" / "server_core_v1" / "manifest.json"
EMISSIONS_ARTIFACT = LAB / "evidence" / "time_edge_validation_v4" / "host-emissions-03.json"

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


def load_real_bars(symbol: str, *, product: str = "crypto_binance_futures_1m",
                   start: str, end: str) -> pd.DataFrame:
    """Real 1m bars for ``symbol`` over ``[start, end)``, sha256-verified
    against the pinned snapshot manifest before being read."""
    manifest = json.loads(SNAPSHOT_MANIFEST.read_text())
    lo, hi = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    frames = []
    used_partitions = []
    for entry in manifest["files"]:
        if entry["symbol"] != symbol or entry["product_id"] != product:
            continue
        part_start = pd.Timestamp(entry["time_min"], tz="UTC")
        part_end = pd.Timestamp(entry["time_max"], tz="UTC") + pd.Timedelta(minutes=1)
        if part_end <= lo or part_start >= hi:
            continue
        path = LAB / entry["snapshot_path"] if not str(entry["snapshot_path"]).startswith("/") \
            else entry["snapshot_path"]
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"{entry['partition']}: snapshot sha256 mismatch, refusing to read")
        frames.append(pd.read_parquet(path))
        used_partitions.append(entry["partition"])
    if not frames:
        raise ValueError(f"no snapshot partitions for {symbol}/{product} in [{start}, {end})")
    frame = pd.concat(frames).sort_values("time")
    frame = frame.set_index(pd.to_datetime(frame["time"], utc=True))
    frame = frame.loc[(frame.index >= lo) & (frame.index < hi)]
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"snapshot bars missing required columns: {missing}")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("real bars are not uniquely, monotonically indexed")
    return frame, used_partitions


def load_real_emissions(*, window_start: str, window_end: str) -> dict:
    """Real regime emissions clipped to ``[window_start, window_end)``, plus
    the artifact's own provenance (never re-fit, never fabricated)."""
    document = json.loads(EMISSIONS_ARTIFACT.read_text())
    actual = hashlib.sha256(EMISSIONS_ARTIFACT.read_bytes()).hexdigest()
    lo, hi = pd.Timestamp(window_start, tz="UTC"), pd.Timestamp(window_end, tz="UTC")
    all_emissions = document["emissions"]
    clipped = [row for row in all_emissions
              if lo <= pd.Timestamp(row["available_at"]) < hi]
    return {
        "schema": "regime_lab.ra05_real_emissions.v1",
        "source_artifact": str(EMISSIONS_ARTIFACT.relative_to(LAB)),
        "source_artifact_sha256": actual,
        "source_lab_run_id": document.get("lab_run_id"),
        "source_model_registry_vintages": len(document.get("model_registry") or {}),
        "total_emissions_in_artifact": len(all_emissions),
        "window": [window_start, window_end],
        "emissions_in_window": len(clipped),
        "emissions": clipped,
    }
