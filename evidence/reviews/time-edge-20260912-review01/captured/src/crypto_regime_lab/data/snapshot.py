"""L03.2 — immutable snapshots of the declared partitions.

Files are copied byte for byte. Nothing is re-encoded, so fractional volume,
integer trade counts, UTC timestamps and the symbol mapping survive exactly as
stored; a rewrite through pandas could silently change a dtype and would violate
"do not modify the originals or their metadata".

The manifest IS the read-lock declared in ``configs/data_readlock_policy.json``:
every file carries a digest, a row count and a closed/partial state, and the
source digests are verified before AND after the copy so a partition that
changes mid-ingest is visible rather than silently absorbed.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..safety.paths import SandboxPolicy, sha256_file
from .inventory import PRODUCTS, _PART_RE

# The scope LAB-03 snapshots, decided from the measured inventory rather than
# from what the guide hoped would exist.
DEFAULT_SCOPE: dict[str, list[str]] = {
    "crypto_binance_futures_1m": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"],
    "crypto_binance_spot_1m": ["BTCUSDT"],
    "crypto_binance_futures_metrics_5m": ["BTCUSDT", "ETHUSDT"],
    "crypto_binance_orderbook_snapshot_1h": ["BTCUSDT"],
}


# Products whose partitions are mutable BY DESIGN. The order-book collector keeps
# a rolling 30-day window (documented in BINANCE_ORDERBOOK_SNAPSHOT_1H.md), so it
# prunes and rewrites partitions that look "closed" by calendar. Treating that as
# an upstream corruption would be wrong; treating it as immutable would be worse.
ROLLING_WINDOW_PRODUCTS = {"crypto_binance_orderbook_snapshot_1h"}

#: The products the PRIMARY core actually consumes. The G1/G2/G5 core features and
#: every alpha decision come from the perpetual 1m bars; the metrics and spot
#: products feed cohort extensions only (G3/G4, and only for the symbols they
#: cover). Drift is therefore reported per product AND scored against what a run
#: declares as an input -- a product no primary run reads cannot invalidate one,
#: and a product that does read it still invalidates immediately.
PRIMARY_CORE_PRODUCTS = {"crypto_binance_futures_1m"}

#: Columns that record WHEN a row was written, not WHAT was measured. A collector
#: that re-ingests an already-closed month rewrites these and nothing else, which
#: moves the file digest without moving a single measurement. The file digest is a
#: proxy for "the data changed"; when the proxy fires, the honest next step is to
#: measure the thing itself rather than to trust or to dismiss the proxy.
VINTAGE_COLUMNS = ("ingested_at",)


class SnapshotError(RuntimeError):
    """Raised when a snapshot cannot be taken safely."""


@dataclass
class FileRecord:
    product_id: str
    symbol: str
    partition: str
    source_path: str
    snapshot_path: str
    sha256: str
    bytes: int
    rows: int
    time_min: str
    time_max: str
    closed: bool
    sources: list[str] = field(default_factory=list)
    ingested_at_max: str | None = None

    def as_record(self) -> dict:
        return self.__dict__.copy()


def _partition_key(path: Path) -> str:
    m = _PART_RE.search(str(path))
    return f"{m.group('year')}-{m.group('month')}" if m else path.stem


def take_snapshot(policy: SandboxPolicy, storage_root: str | Path, snapshot_id: str,
                  scope: dict[str, list[str]] | None = None,
                  copy_bytes: bool = True) -> dict:
    """Copy the declared partitions into ``LAB_ROOT/snapshots/{snapshot_id}/``."""
    import pyarrow.parquet as pq

    storage_root = policy.assert_readable(storage_root)
    scope = scope or DEFAULT_SCOPE
    dest_root = policy.resolve_write_target(policy.lab_root / "snapshots" / snapshot_id)
    dest_root.mkdir(parents=True, exist_ok=True)

    started = datetime.now(tz=timezone.utc).isoformat()
    files: list[FileRecord] = []
    drift: list[dict] = []

    for product_id, symbols in scope.items():
        spec = PRODUCTS[product_id]
        product_root = storage_root.joinpath(*spec["path"])
        for symbol in symbols:
            base = product_root / f"symbol={symbol}"
            if not base.is_dir():
                raise SnapshotError(f"{product_id}/{symbol} is not present in storage; the scope "
                                    "must be derived from the measured inventory")
            parts = sorted(base.rglob("*.parquet"))
            latest_partition = max(_partition_key(p) for p in parts)
            for src in parts:
                before = sha256_file(src)
                partition = _partition_key(src)
                target = policy.resolve_write_target(
                    dest_root / product_id / symbol / f"{partition}.parquet")
                target.parent.mkdir(parents=True, exist_ok=True)
                if copy_bytes:
                    # Idempotent: an existing byte-identical copy is reused, so a
                    # re-run verifies the read-lock instead of rewriting 1.4 GB.
                    if not (target.is_file() and sha256_file(target) == before):
                        if target.exists():
                            target.chmod(0o644)
                        shutil.copyfile(src, target)      # byte copy, never a re-encode
                    after = sha256_file(src)
                    if before != after:
                        drift.append({"source": str(src), "before": before, "after": after})
                        raise SnapshotError(
                            f"{src} changed while it was being snapshotted; the ingest is aborted "
                            "rather than recording a torn partition"
                        )
                    digest = sha256_file(target)
                    if digest != before:
                        raise SnapshotError(f"copy of {src} does not match the source digest")
                    target.chmod(0o444)
                    read_from = target
                    digest_out = digest
                else:
                    read_from = src
                    digest_out = before

                pf = pq.ParquetFile(read_from)
                cols = pf.schema_arrow.names
                wanted = [c for c in ("time", "source", "ingested_at") if c in cols]
                table = pq.read_table(read_from, columns=wanted).to_pydict()
                times = table["time"]
                files.append(FileRecord(
                    product_id=product_id, symbol=symbol, partition=partition,
                    source_path=str(src), snapshot_path=str(target if copy_bytes else src),
                    sha256=digest_out, bytes=src.stat().st_size, rows=pf.metadata.num_rows,
                    time_min=str(times[0]), time_max=str(times[-1]),
                    closed=partition != latest_partition,
                    sources=sorted({str(s) for s in table.get("source", [])}),
                    ingested_at_max=(str(max(table["ingested_at"]))
                                     if "ingested_at" in table and table["ingested_at"] else None),
                ))

    manifest = {
        "schema": "crypto_regime_lab.snapshot_manifest.v1",
        "snapshot_id": snapshot_id,
        "storage_root": str(storage_root),
        "snapshot_root": str(dest_root),
        "ingest_started_utc": started,
        "ingest_finished_utc": datetime.now(tz=timezone.utc).isoformat(),
        "copy_mode": "byte_copy" if copy_bytes else "reference_only",
        "scope": scope,
        "file_count": len(files),
        "total_bytes": sum(f.bytes for f in files),
        "total_rows": sum(f.rows for f in files),
        "closed_partitions": sum(1 for f in files if f.closed),
        "open_partitions": sum(1 for f in files if not f.closed),
        "source_drift_detected": drift,
        "files": [f.as_record() for f in files],
        "read_lock": {
            "rule": "a run declares this snapshot_id and re-verifies every digest before and after; "
                    "drift invalidates the run as EXTERNAL_DATA_DRIFT rather than continuing",
            "policy_artifact": "configs/data_readlock_policy.json",
        },
        "primary_eligibility": {
            "closed_partitions_only": True,
            "reason": "an open trailing partition is excluded from a primary run with an explicit "
                      "reason rather than silently truncated",
        },
        "originals_unmodified": True,
    }
    return manifest


def classify_source_drift(record: dict) -> dict:
    """Did the upstream file's MEASUREMENTS change, or only its ingest vintage?

    ``verify_snapshot`` compares file digests, which is the right first test: it
    is cheap, it needs no schema knowledge and it cannot be fooled. But a digest
    answers "are these the same bytes", not "are these the same numbers", and a
    collector that re-ingests a closed month rewrites ``ingested_at`` on every
    row while leaving every measurement untouched. Reporting that as a data
    revision overstates the evidence; ignoring it would understate it.

    So when the digest moves we read both files and compare every column except
    the vintage columns. Anything that is not provably a pure re-stamp -- a
    changed value, a changed row count, a changed schema, a file that will not
    read -- is a ``CONTENT_REVISION``. The burden of proof sits on the benign
    verdict, never on the invalidating one.
    """
    import pandas as pd

    out = {
        "path": record["source_path"],
        "product_id": record["product_id"],
        "symbol": record["symbol"],
        "partition": record["partition"],
        "vintage_columns_ignored": list(VINTAGE_COLUMNS),
    }
    try:
        lab = pd.read_parquet(record["snapshot_path"])
        upstream = pd.read_parquet(record["source_path"])
    except Exception as exc:                       # unreadable, truncated, re-encoded
        return {**out, "classification": "CONTENT_REVISION",
                "reason": f"a file could not be read for comparison: {exc!r}"}

    if list(lab.columns) != list(upstream.columns):
        return {**out, "classification": "CONTENT_REVISION",
                "reason": "the column set changed",
                "columns_only_in_snapshot": sorted(set(lab.columns) - set(upstream.columns)),
                "columns_only_upstream": sorted(set(upstream.columns) - set(lab.columns))}
    if len(lab) != len(upstream):
        return {**out, "classification": "CONTENT_REVISION",
                "reason": "the row count changed",
                "rows_snapshot": int(len(lab)), "rows_upstream": int(len(upstream))}

    measured = [c for c in lab.columns if c not in VINTAGE_COLUMNS]
    sort_key = "time" if "time" in lab.columns else measured[0]
    lab = lab.sort_values(sort_key).reset_index(drop=True)
    upstream = upstream.sort_values(sort_key).reset_index(drop=True)

    changed: dict[str, dict] = {}
    for column in measured:
        left, right = lab[column], upstream[column]
        if left.equals(right):
            continue
        entry: dict = {"dtype_snapshot": str(left.dtype), "dtype_upstream": str(right.dtype)}
        try:
            delta = (left.astype("float64") - right.astype("float64")).abs()
            entry["rows_differing"] = int((delta > 0).sum())
            entry["max_abs_difference"] = float(delta.max())
        except (TypeError, ValueError):
            entry["rows_differing"] = int((left.astype(str) != right.astype(str)).sum())
        changed[column] = entry

    if changed:
        return {**out, "classification": "CONTENT_REVISION",
                "reason": "measured columns changed upstream", "changed_columns": changed}
    vintage_moved = sorted(c for c in VINTAGE_COLUMNS
                           if c in lab.columns and not lab[c].equals(upstream[c]))
    return {**out, "classification": "VINTAGE_RESTAMP_ONLY",
            "reason": ("every measured column is identical; only the ingest vintage moved, so the "
                       "numbers this study read are the numbers upstream still holds"),
            "measured_columns_compared": measured,
            "rows_compared": int(len(lab)),
            "vintage_columns_that_moved": vintage_moved,
            "vintage_max_snapshot": (str(lab[vintage_moved[0]].max()) if vintage_moved else None),
            "vintage_max_upstream": (str(upstream[vintage_moved[0]].max())
                                     if vintage_moved else None)}


def verify_snapshot(manifest: dict, *, check_sources: bool = True,
                    deep: bool = False) -> dict:
    """Re-verify the read-lock. Any drift is EXTERNAL_DATA_DRIFT, never a warning.

    ``deep`` adds one step and removes none. Closed-partition drift is still
    detected by digest exactly as before; deep then reads the two files and asks
    whether any MEASURED column moved (see ``classify_source_drift``). A
    partition proven to be a pure ingest re-stamp stops invalidating its cohort,
    and only that partition -- anything unproven still invalidates. Without
    ``deep`` the verdict is unchanged, so the shallow check stays fail-closed.
    """
    changed_snapshot, missing = [], []
    drift_closed, drift_open, drift_rolling = [], [], []
    for record in manifest["files"]:
        snap = Path(record["snapshot_path"])
        if not snap.is_file():
            missing.append(record["snapshot_path"])
            continue
        if sha256_file(snap) != record["sha256"]:
            changed_snapshot.append(record["snapshot_path"])
        if check_sources:
            src = Path(record["source_path"])
            if not src.is_file():
                missing.append(record["source_path"])
            elif sha256_file(src) != record["sha256"]:
                # An OPEN trailing partition is expected to grow: the collector
                # appends to it. That is not an invalidation, because a primary
                # run consumes closed partitions only. A CLOSED partition that
                # changes is a real invalidation.
                entry = {"path": record["source_path"], "partition": record["partition"],
                         "product_id": record["product_id"], "symbol": record["symbol"],
                         "_record": record}
                if record["product_id"] in ROLLING_WINDOW_PRODUCTS:
                    drift_rolling.append(entry)
                elif record["closed"]:
                    drift_closed.append(entry)
                else:
                    drift_open.append(entry)
    changed_source = [d["path"] for d in drift_closed + drift_open + drift_rolling]

    # A digest says "different bytes". Only a read says "different numbers".
    content_drift: list[dict] = []
    vintage_only: list[dict] = []
    if deep:
        for entry in drift_closed:
            verdict = classify_source_drift(entry["_record"])
            entry["content_verdict"] = verdict
            (vintage_only if verdict["classification"] == "VINTAGE_RESTAMP_ONLY"
             else content_drift).append(verdict)
    for entry in drift_closed:
        entry.pop("_record", None)
    # Deep classification narrows invalidation to the partitions that actually
    # changed. Shallow keeps every closed-partition drift invalidating.
    invalidating = ([e for e in drift_closed
                     if e.get("content_verdict", {}).get("classification") != "VINTAGE_RESTAMP_ONLY"]
                    if deep else drift_closed)

    drift_by_product: dict[str, dict] = {}
    for entry in invalidating:
        bucket = drift_by_product.setdefault(entry["product_id"],
                                             {"partitions": [], "symbols": set()})
        bucket["partitions"].append(entry["partition"])
        bucket["symbols"].add(entry["symbol"])
    drift_by_product = {
        product: {"closed_partitions_changed": len(info["partitions"]),
                  "partition_range": [min(info["partitions"]), max(info["partitions"])],
                  "symbols": sorted(info["symbols"]),
                  "in_primary_core": product in PRIMARY_CORE_PRODUCTS}
        for product, info in sorted(drift_by_product.items())
    }
    primary_core_drift = [d for d in invalidating if d["product_id"] in PRIMARY_CORE_PRODUCTS]
    status = "UNCHANGED"
    if missing or changed_snapshot:
        status = "SNAPSHOT_CORRUPT"
    elif invalidating:
        status = "EXTERNAL_DATA_DRIFT"
    elif vintage_only:
        status = "EXTERNAL_VINTAGE_RESTAMP_ONLY"
    elif drift_open or drift_rolling:
        status = "EXPECTED_MUTABLE_DRIFT_ONLY"
    return {
        "schema": "crypto_regime_lab.snapshot_verification.v1",
        "snapshot_id": manifest["snapshot_id"],
        "files_checked": len(manifest["files"]),
        "missing": missing,
        "snapshot_files_changed": changed_snapshot,
        "source_files_changed": changed_source,
        "closed_partition_drift": drift_closed,
        "drift_by_product": drift_by_product,
        "primary_core_products": sorted(PRIMARY_CORE_PRODUCTS),
        "primary_core_closed_drift": primary_core_drift,
        "products_invalidated": sorted(drift_by_product),
        "open_partition_drift": drift_open,
        "rolling_window_drift": drift_rolling,
        "rolling_window_products": sorted(ROLLING_WINDOW_PRODUCTS),
        "status": status,
        "consequence": {
            "UNCHANGED": "runs using this snapshot remain valid",
            "EXPECTED_MUTABLE_DRIFT_ONLY": (
                "only partitions that are mutable by design changed: an open trailing partition "
                "the collector is appending to, or a rolling-window product that prunes and "
                "rewrites its own history. The snapshot's own bytes are unchanged, so what was "
                "read is still exactly what was read, and the primary cohort does not depend on "
                "the rolling-window product."),
            "EXTERNAL_DATA_DRIFT": (
                "a CLOSED partition changed upstream: any run declaring this snapshot is "
                "invalidated and must be re-registered against a fresh snapshot"),
            "EXTERNAL_VINTAGE_RESTAMP_ONLY": (
                "closed partitions were rewritten upstream, and every one of them was READ and "
                "proven to carry identical measurements -- only the ingest vintage moved. The "
                "digests no longer match, which is reported rather than hidden, but no number "
                "this study consumed has changed, so no cohort is invalidated."),
            "SNAPSHOT_CORRUPT": "the lab's own copy no longer matches its manifest",
        }[status],
        "closed_partition_drift_classified": bool(deep),
        "closed_partition_content_revisions": content_drift,
        "closed_partition_vintage_restamps": vintage_only,
        "classification_rule": (
            "the file digest detects drift; a read decides what the drift MEANS. A closed "
            "partition stops invalidating its cohort only when every measured column is read and "
            "proven identical (VINTAGE_RESTAMP_ONLY). A changed value, row count or schema, or a "
            "file that will not read, stays CONTENT_REVISION and still invalidates. Without "
            "deep=True nothing is classified and every closed-partition drift invalidates."),
        "primary_run_valid": (not missing and not changed_snapshot
                              and not primary_core_drift),
        "primary_run_valid_rule": (
            "a primary run stays valid while the lab's own snapshot bytes match the manifest and "
            "no CLOSED partition of a product the primary core reads has changed upstream. Drift "
            "in any other product invalidates the cohorts that read THAT product and is listed in "
            "products_invalidated; it is never downgraded to a warning."),
        "cohort_runs_invalidated": sorted(drift_by_product),
        "rolling_window_note": (
            "a rolling-window product can never be part of an immutable snapshot; its cohort is "
            "reported separately and is not in the primary core (see feature tiers)"),
    }
