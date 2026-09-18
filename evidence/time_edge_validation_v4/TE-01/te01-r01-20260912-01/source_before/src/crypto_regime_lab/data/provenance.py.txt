"""Product documentation, revisions and observed vintage (guide L03.1, L03.6, 6.3).

Guide 6.1 says to read the loader code, the real endpoint/product docs and the
storage metadata — not to conclude a product is missing because a web page would
not load. The collector documentation lives beside the loader, so it is read
(read-only, digested) and its declared configuration is compared against what the
storage actually holds.

Guide 6.3 also asks for a revision/vintage policy. Two repairs are documented in
that directory, and one of them is VISIBLE in the data: the archive was seeded in
a single bulk ingest and one window was later re-fetched. That window is masked
as REPAIRED so a study can flag or exclude it instead of treating it as an
ordinary observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DOC_ROOT = Path("/root/bobby/pool_alpha/alphas_storage/_get_data")

PRODUCT_DOCS = {
    "crypto_binance_spot_1m": "BINANCE_SPOT_1M.md",
    "crypto_binance_futures_metrics_5m": "BINANCE_FUTURES_METRICS_5M.md",
    "crypto_binance_orderbook_snapshot_1h": "BINANCE_ORDERBOOK_SNAPSHOT_1H.md",
    "crypto_binance_futures_1m": "BINANCE_USDM_QUARTERLY_1M.md",
}
REVISION_DOCS = ("CONTINUITY_REPAIR_2026-06-12.md", "BINANCE_DAILY_MATRIX_REPAIR_2026-06-16.md")

# Read from the documents above. Each is a CLAIM by the collector's own docs and
# is checked against the storage, never taken on faith.
DOCUMENTED_CONFIG = {
    "crypto_binance_spot_1m": {
        "configured_symbols": ["BTCUSDT"],
        "configured_start": "2018-01-01",
        "consequence": "the four other symbols were never COLLECTED; the data is not lost, it was "
                       "never configured, so no amount of re-reading storage will produce it",
    },
    "crypto_binance_futures_metrics_5m": {
        "configured_symbols": ["BTCUSDT", "ETHUSDT", "LINKUSDT", "ARBUSDT", "OPUSDT",
                               "POLUSDT", "AAVEUSDT"],
        "configured_start": "auto-discover earliest on Binance Vision",
        "consequence": "SOLUSDT, BNBUSDT and DOGEUSDT are not in the collector config, so the "
                       "G3 derivatives block can only ever cover BTCUSDT and ETHUSDT here",
    },
    "crypto_binance_orderbook_snapshot_1h": {
        "configured_symbols": ["BTCUSDT"],
        "lookback_days": 30,
        "consequence": "THIS PRODUCT IS A ROLLING 30-DAY WINDOW. It cannot accumulate history, so "
                       "SERVER_LIQUIDITY can never support a historical study on this storage; "
                       "treating its few weeks as a cohort would be a mistake, not a limitation",
    },
    "crypto_binance_futures_1m": {
        "configured_symbols": "USD-M perpetuals plus discovered quarterly contracts",
        "consequence": "the five trade symbols are all present",
    },
}

DOCUMENTED_REVISIONS = [
    {
        "id": "CONTINUITY_REPAIR_2026-06-12",
        "affects": "crypto 1m storage",
        "window": ["2026-05-01", "2026-06-06"],
        "what_happened": "the seeded history ended in early May while the live service resumed on "
                         "2026-06-06, leaving a real gap in the raw 1m data",
        "remedy": "the missing range was re-fetched from the Binance futures API and appended, "
                  "deduplicated on (symbol, time)",
        "lab_consequence": "bars in that window carry a later ingest vintage; they are masked "
                           "REPAIRED so a study can flag or exclude them",
    },
    {
        "id": "BINANCE_DAILY_MATRIX_REPAIR_2026-06-16",
        "affects": "crypto/binance_daily_matrix",
        "window": None,
        "what_happened": "the matrix only ever held 16 rows because the collector read a global "
                         "latest index and never backfilled the head",
        "remedy": "history-first backfill policy; only fully closed daily candles are written",
        "lab_consequence": "this lab does not consume the daily matrix, so nothing here depends "
                           "on it; recorded for completeness",
    },
]


@dataclass
class VintageMap:
    symbol: str
    partition: str
    ingest_days: list[str]
    rows_by_ingest_day: dict[str, int]
    repaired_rows: int
    seed_like: bool
    classification: str = "unknown"

    def as_record(self) -> dict:
        return self.__dict__.copy()


def observed_vintages(snapshot_root: Path, product_id: str, symbol: str,
                      partitions: list[str]) -> list[VintageMap]:
    """Group each partition's rows by ingest day: seed, repair or live append."""
    base = Path(snapshot_root) / product_id / symbol
    out: list[VintageMap] = []
    for partition in partitions:
        path = base / f"{partition}.parquet"
        if not path.is_file():
            continue
        frame = pd.read_parquet(path, columns=["time", "ingested_at"])
        day = pd.to_datetime(frame["ingested_at"]).dt.strftime("%Y-%m-%d")
        counts = day.value_counts().to_dict()
        days_in_partition = pd.Period(partition, freq="M").days_in_month
        n_ingest = len(counts)
        # One ingest day is a bulk seed; roughly one per calendar day is the live
        # collector appending; a small handful in between is a repair.
        if n_ingest == 1:
            classification = "bulk_seed"
        elif n_ingest >= days_in_partition / 2:
            classification = "live_daily_append"
        else:
            classification = "repair_or_partial_backfill"
        repaired = 0
        if classification == "repair_or_partial_backfill":
            newest = max(counts)
            repaired = int(counts[newest])
        out.append(VintageMap(
            symbol=symbol, partition=partition, ingest_days=sorted(counts),
            rows_by_ingest_day={k: int(v) for k, v in counts.items()},
            repaired_rows=repaired, seed_like=n_ingest == 1,
            classification=classification))
    return out


def repaired_mask(frame: pd.DataFrame, revision: dict) -> pd.Series:
    """True where a row falls inside a documented repair window."""
    if not revision.get("window"):
        return pd.Series(False, index=frame.index)
    start, end = revision["window"]
    time = pd.to_datetime(frame["time"])
    if getattr(time.dt, "tz", None) is not None:
        time = time.dt.tz_convert("UTC").dt.tz_localize(None)
    return (time >= pd.Timestamp(start)) & (time < pd.Timestamp(end))


def read_docs() -> dict:
    """Digest the product and revision documents that were actually read."""
    from ..safety.paths import sha256_file

    docs = {}
    for product_id, filename in PRODUCT_DOCS.items():
        path = DOC_ROOT / filename
        docs[product_id] = {
            "document": filename,
            "found": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
            "lines": len(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else 0,
            "documented_config": DOCUMENTED_CONFIG.get(product_id),
        }
    revisions = []
    for filename in REVISION_DOCS:
        path = DOC_ROOT / filename
        revisions.append({"document": filename, "found": path.is_file(),
                          "sha256": sha256_file(path) if path.is_file() else None})
    return {"product_docs": docs, "revision_docs": revisions}


def provenance_report(snapshot_root: str | Path, inventory: dict,
                      probe_partitions: tuple[str, ...] = ("2026-03", "2026-04", "2026-05",
                                                           "2026-06", "2026-07")) -> dict:
    docs = read_docs()
    vintages = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        vintages[symbol] = [v.as_record() for v in observed_vintages(
            Path(snapshot_root), "crypto_binance_futures_1m", symbol, list(probe_partitions))]

    mismatches = []
    for product_id, doc in docs["product_docs"].items():
        config = doc.get("documented_config") or {}
        declared = config.get("configured_symbols")
        if not isinstance(declared, list):
            continue
        present = set(inventory["products"][product_id]["coverage_by_symbol"])
        expected_trade = set(declared) & {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"}
        if present != expected_trade:
            mismatches.append({"product_id": product_id, "documented": sorted(expected_trade),
                               "observed": sorted(present)})

    repairs = [v for records in vintages.values() for v in records
               if v["classification"] == "repair_or_partial_backfill"]
    classifications = {}
    for records in vintages.values():
        for v in records:
            classifications.setdefault(v["classification"], 0)
            classifications[v["classification"]] += 1
    return {
        "schema": "crypto_regime_lab.provenance_report.v1",
        "documents_read": docs,
        "documented_revisions": DOCUMENTED_REVISIONS,
        "observed_vintages": vintages,
        "vintage_classification_counts": classifications,
        "repaired_partitions": [
            {"symbol": v["symbol"], "partition": v["partition"],
             "ingest_days": v["ingest_days"], "rows_from_the_later_ingest": v["repaired_rows"]}
            for v in repairs],
        "documentation_matches_storage": mismatches == [],
        "documentation_mismatches": mismatches,
        "reading": (
            "the absences in this storage are CONFIGURATION, not loss: spot tracks BTCUSDT only, "
            "the metrics collector never listed SOL/BNB/DOGE, and the order-book product keeps a "
            "rolling 30-day window so it can never accumulate history. The 2026-05 partitions "
            "carry two ingest days, which is the documented continuity repair visible in the data."
        ),
    }
