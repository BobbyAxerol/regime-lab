"""Render, from artifacts, exactly which historical data a phase consumed.

Every phase report states its method and its numbers, but until now none of them
stated its INPUTS: which storage products, which symbols, which date span, how
many rows, and under which read-lock verdict. A reader who wanted to audit the
raw data had to reconstruct that from four JSON documents.

Nothing here computes anything new. It reads the pinned snapshot manifest, the
eligibility report and the read-lock verification, and lays them out. If those
three disagree the section says so rather than picking one.
"""

from __future__ import annotations

import json
from pathlib import Path

#: The loader is READ but never CALLED. ``vendor_readonly/loader_snapshot/data_loader.py``
#: is a pinned read-only copy whose class list is parsed statically to learn where
#: each product lives; the bars themselves are then read straight from the lab's
#: byte-copied parquet. That distinction is not cosmetic: the loader's
#: ``_normalize`` casts ``volume`` to int64, which truncates the fractional
#: contract quantities BTCUSDT, ETHUSDT and BNBUSDT are stored with.
LOADER_ACCESS_NOTE = (
    "The lab does NOT call `data_loader.py` at run time. The loader is copied read-only into "
    "`vendor_readonly/loader_snapshot/`, pinned by SHA-256, and parsed STATICALLY so its reader "
    "classes tell the lab which storage path holds which product (guide 6.1: inventory by "
    "product, not by assumed class name). The bars are then read directly from the lab's own "
    "byte-copied parquet."
)


def loader_parity_lines(parity: dict | None) -> list[str]:
    """State, from the measured artifact, what calling the endpoint would change."""
    out = ["### How the raw bars are read", "", LOADER_ACCESS_NOTE, ""]
    if parity is None:
        out += ["> `configs/loader_endpoint_parity.json` is missing, so the difference between "
                "the endpoint and the parquet is UNMEASURED here. Run "
                "`scripts/verify_loader_parity.py`.", ""]
        return out

    compared = [r for r in parity["per_symbol"] if r.get("status") == "COMPARED"]
    differing = [r for r in compared if r.get("columns_differing")]
    out += [
        f"That distinction is measured, not asserted: `scripts/verify_loader_parity.py` calls the "
        f"pinned loader (`sha256 {parity['loader_snapshot_sha256'][:16]}…`) on "
        f"{len(compared)} partitions ({parity.get('probe_rule', 'sampled partitions')}) and "
        f"diffs its output against the same bytes read directly. "
        f"**{len(differing)} of {len(compared)} disagree**, always on the same column.",
        "",
        "| symbol | partition | stored dtype | bars with a fractional volume | bars a cast sends "
        "to zero | columns differing |",
        "|---|---|---|---|---|---|",
    ]
    for record in compared:
        out.append(
            f"| {record['symbol']} | {record['partition']} | `{record['stored_volume_dtype']}` | "
            f"{record['bars_with_a_fractional_volume']:,} | "
            f"{record['bars_a_cast_would_zero']:,} | "
            f"{', '.join(record['columns_differing']) or '—'} |")
    out += ["", parity["finding"], "", parity["lab_consequence"], ""]
    worst = max((r for r in differing),
                key=lambda r: r["columns_differing"].get("volume", {}).get(
                    "share_of_total_lost") or 0.0, default=None)
    if worst is not None:
        volume = worst["columns_differing"]["volume"]
        share = volume.get("share_of_total_lost")
        out += [
            f"Largest measured loss — **{worst['symbol']} {worst['partition']}**: "
            f"{volume['rows_differing']:,} of {worst['rows']:,} bars differ, "
            + (f"**{share:.3%}** of the partition's total volume is lost" if share is not None
               else "the loss share is undefined")
            + f", and **{worst['bars_a_cast_would_zero']:,}** bars with real trades become "
              "volume 0. Those bars feed the G2 activity and taker-imbalance features, where a "
              "zero denominator is masked rather than epsilon-padded — so the truncation would "
              "have removed observations, not merely blurred them.",
            "",
            "Guarded by `test_t21_resampling_never_truncates_real_volume`, "
            "`test_t21_stored_volume_dtype_varies_and_is_coerced` and "
            "`test_loader_endpoint_parity_artifact_matches_a_live_call`.",
            "",
        ]
    return out


def _load(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def data_provenance_lines(lab_root: Path, *, snapshot_id: str, consumed: dict) -> list[str]:
    """Markdown for a phase's "which data, how much, verified how" section.

    ``consumed`` describes what THIS phase actually read: ``{"symbols": [...],
    "products": [...], "role": "development", "window": [start, end], "notes":
    [...]}``. It is stated rather than inferred, because a phase that reads a
    subset of the snapshot must say so instead of inheriting the snapshot's
    headline totals.
    """
    lab_root = Path(lab_root)
    manifest = _load(lab_root / "snapshots" / snapshot_id / "manifest.json")
    eligibility = _load(lab_root / "configs" / "data_eligibility.json")
    readlock = _load(lab_root / "configs" / "readlock_verification.json")
    parity = _load(lab_root / "configs" / "loader_endpoint_parity.json")

    out: list[str] = ["## Data provenance — which historical data this phase read", ""]
    if manifest is None:
        out += ["**BLOCKED** — no snapshot manifest for "
                f"`{snapshot_id}`; nothing about the inputs can be stated.", ""]
        return out

    out += [
        f"- snapshot **`{snapshot_id}`**, byte-copied under `snapshots/{snapshot_id}/` "
        f"({manifest['file_count']} files, **{manifest['total_rows']:,} rows**, "
        f"{manifest['total_bytes'] / 1e6:.0f} MB)",
        f"- read from `{manifest['storage_root']}` between `{manifest['ingest_started_utc'][:19]}` "
        f"and `{manifest['ingest_finished_utc'][:19]}` UTC, copy mode **{manifest['copy_mode']}**",
        f"- closed partitions **{manifest['closed_partitions']}**, open trailing "
        f"**{manifest['open_partitions']}** — only closed partitions are primary-eligible",
        "",
    ]

    if readlock is not None:
        status = readlock.get("status")
        out += [f"- read-lock re-verification: **{status}**, primary run valid "
                f"**{readlock.get('primary_run_valid')}**"]
        restamps = readlock.get("closed_partition_vintage_restamps") or []
        revisions = readlock.get("closed_partition_content_revisions") or []
        if readlock.get("closed_partition_drift_classified"):
            out += [f"  - closed-partition drift read and classified: "
                    f"**{len(revisions)} content revisions**, "
                    f"**{len(restamps)} ingest re-stamps** (measurements proven identical)"]
        elif readlock.get("closed_partition_drift"):
            out += [f"  - {len(readlock['closed_partition_drift'])} closed partitions drifted by "
                    "digest and were NOT read to see whether any measurement changed"]
        if readlock.get("cohort_runs_invalidated"):
            out += [f"  - cohorts invalidated: `{readlock['cohort_runs_invalidated']}`"]
        out += [""]

    out += ["### What the snapshot holds", "",
            "| product | symbols | files | rows | span |", "|---|---|---|---|---|"]
    per_product: dict[str, dict] = {}
    for record in manifest["files"]:
        bucket = per_product.setdefault(record["product_id"],
                                        {"symbols": set(), "files": 0, "rows": 0,
                                         "min": record["time_min"], "max": record["time_max"]})
        bucket["symbols"].add(record["symbol"])
        bucket["files"] += 1
        bucket["rows"] += record["rows"]
        bucket["min"] = min(bucket["min"], record["time_min"])
        bucket["max"] = max(bucket["max"], record["time_max"])
    for product, info in sorted(per_product.items()):
        out.append(f"| `{product}` | {', '.join(sorted(info['symbols']))} | {info['files']} | "
                   f"{info['rows']:,} | {info['min'][:10]} → {info['max'][:10]} |")
    out.append("")

    if eligibility is not None:
        stale = eligibility.get("manifest_ingest_finished_utc") != manifest["ingest_finished_utc"]
        if stale:
            out += ["> **`configs/data_eligibility.json` does not come from this manifest** "
                    f"(it names `{eligibility.get('manifest_ingest_finished_utc')}`). "
                    "Run `scripts/refresh_data_eligibility.py`.", ""]
        out += ["### Per-symbol usable history (perpetual 1m, the primary venue)", "",
                "| symbol | first bar | last bar | rows | first decision bar after warmup |",
                "|---|---|---|---|---|"]
        for symbol, record in eligibility["per_symbol"].items():
            perp = record["products"].get("crypto_binance_futures_1m")
            if perp is None:
                out.append(f"| {symbol} | — | — | — | no perpetual product |")
                continue
            out.append(f"| {symbol} | {perp['time_min'][:16]} | {perp['time_max'][:16]} | "
                       f"{perp['rows']:,} | {record['first_decision_bar'][:16]} |")
        out.append("")

    out += ["### What THIS phase consumed", ""]
    out += [f"- symbols: **{', '.join(consumed['symbols'])}**"]
    out += [f"- products: {', '.join('`' + p + '`' for p in consumed['products'])}"]
    if consumed.get("role"):
        window = consumed.get("window") or ["?", "?"]
        out += [f"- data role **{consumed['role']}**, window **{window[0]} → {window[1]}**"]
    for note in consumed.get("notes", []):
        out += [f"- {note}"]
    out += [""]
    out += loader_parity_lines(parity)
    return out
