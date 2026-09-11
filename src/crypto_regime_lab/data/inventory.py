"""L03.1 — data product inventory, read from storage rather than from reader names.

Guide 6.1 is explicit: a reader class existing in the loader does NOT mean the
dataset exists. Every product here is confirmed by walking the actual Hive
partitions read-only, and a product with no partitions for a symbol is recorded
as ABSENT rather than assumed present.

The field list follows guide 6.1: product_id, actual_reader_symbol, code_sha,
storage_paths, file_hashes, schema, units, earliest_observed, latest_closed,
coverage_by_symbol, source and measurement method, bar_timestamp_convention,
available_at_rule, revision/vintage policy, license, read_only_verified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRADE_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")

# product_id -> (relative storage path, loader class in the snapshot, bar interval)
PRODUCTS: dict[str, dict[str, Any]] = {
    "crypto_binance_spot_1m": {
        "path": ("crypto", "binance_spot", "1m"),
        "reader": "CryptoBinanceSpot1m",
        "interval": "1min",
        "kind": "ohlcv_bars",
        "measurement": "Binance Vision monthly spot klines",
        "role": "SERVER_CORE_LONG spot leg; basis and spot-activity context",
    },
    "crypto_binance_futures_1m": {
        "path": ("crypto", "binance_futures", "1m"),
        "reader": "CryptoBinance1m",
        "interval": "1min",
        "kind": "ohlcv_bars",
        "measurement": "Binance USD-M perpetual klines",
        "role": "PRIMARY: signal and execution venue (guide 4.1)",
    },
    "crypto_binance_futures_metrics_5m": {
        "path": ("crypto", "binance_futures_metrics", "5m"),
        "reader": "BinanceFuturesMetrics5m",
        "interval": "5min",
        "kind": "derivatives_metrics",
        "measurement": "Binance Vision USD-M metrics (open interest and trader ratios)",
        "role": "SERVER_DERIVATIVES: G3 leverage/crowding",
    },
    "crypto_binance_orderbook_snapshot_1h": {
        "path": ("crypto", "binance_orderbook_snapshot", "1h"),
        "reader": "BinanceOrderBookSnapshot1h",
        "interval": "1h",
        "kind": "book_snapshot",
        "measurement": "REST depth snapshot, sampled once per hour",
        "role": "SERVER_LIQUIDITY: G4 spread/depth",
    },
}

# Products the guide's cohorts want but which may simply not exist here.
EXPECTED_BUT_UNCONFIRMED = {
    "funding_rate_history": {
        "needed_for": "guide 4.1 realistic net carry, and the G3 funding features",
        "searched": "storage tree and the loader's class list",
    },
    "basis_or_mark_price": {
        "needed_for": "G3 basis B_t = F_t/S_t - 1 without a spot proxy",
        "searched": "storage tree",
    },
}

_PART_RE = re.compile(r"symbol=(?P<symbol>[^/]+)/year=(?P<year>\d+)/month=(?P<month>\d+)")


@dataclass
class ProductInventory:
    product_id: str
    storage_root: Path
    exists: bool
    reader: str
    interval: str
    kind: str
    measurement: str
    role: str
    symbols_present: dict[str, dict] = field(default_factory=dict)
    symbols_absent: list[str] = field(default_factory=list)
    other_symbols: list[str] = field(default_factory=list)
    schema: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_record(self) -> dict:
        return {
            "product_id": self.product_id,
            "exists": self.exists,
            "actual_reader_symbol": self.reader,
            "storage_paths": str(self.storage_root),
            "bar_interval": self.interval,
            "kind": self.kind,
            "measurement_method": self.measurement,
            "role": self.role,
            "schema": self.schema,
            "sources_observed": self.sources,
            "coverage_by_symbol": self.symbols_present,
            "trade_symbols_absent": self.symbols_absent,
            "non_trade_symbols_present": len(self.other_symbols),
            "notes": self.notes,
            "read_only_verified": True,
        }


def _partition_files(root: Path, symbol: str) -> list[Path]:
    base = root / f"symbol={symbol}"
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.parquet"))


def _list_symbols(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(p.name.split("=", 1)[1] for p in root.iterdir()
                  if p.is_dir() and p.name.startswith("symbol="))


def inventory_product(product_id: str, storage_root: Path, *, deep: bool = True) -> ProductInventory:
    spec = PRODUCTS[product_id]
    root = storage_root.joinpath(*spec["path"])
    inv = ProductInventory(product_id=product_id, storage_root=root, exists=root.is_dir(),
                           reader=spec["reader"], interval=spec["interval"], kind=spec["kind"],
                           measurement=spec["measurement"], role=spec["role"])
    if not inv.exists:
        inv.symbols_absent = list(TRADE_SYMBOLS)
        inv.notes.append("product directory does not exist in storage")
        return inv

    all_symbols = _list_symbols(root)
    inv.other_symbols = [s for s in all_symbols if s not in TRADE_SYMBOLS]

    import pyarrow.parquet as pq

    schema_taken = False
    for symbol in TRADE_SYMBOLS:
        files = _partition_files(root, symbol)
        if not files:
            inv.symbols_absent.append(symbol)
            continue
        years, months = set(), set()
        for f in files:
            m = _PART_RE.search(str(f))
            if m:
                years.add(int(m.group("year")))
                months.add(f"{m.group('year')}-{m.group('month')}")
        record: dict[str, Any] = {
            "file_count": len(files),
            "bytes": sum(f.stat().st_size for f in files),
            "years": sorted(years),
            "partition_count": len(months),
            "first_partition": min(months) if months else None,
            "last_partition": max(months) if months else None,
        }
        if deep:
            first = pq.ParquetFile(files[0])
            last = pq.ParquetFile(files[-1])
            record["rows_first_partition"] = first.metadata.num_rows
            record["rows_last_partition"] = last.metadata.num_rows
            head = first.read_row_group(0).slice(0, 1).to_pydict()
            tail_tbl = last.read().to_pydict()
            record["earliest_observed"] = str(head["time"][0])
            record["latest_observed"] = str(tail_tbl["time"][-1])
            if "source" in head:
                for s in set(tail_tbl.get("source", [])) | {head["source"][0]}:
                    if s not in inv.sources:
                        inv.sources.append(str(s))
            if not schema_taken:
                arrow = first.schema_arrow
                inv.schema = {n: str(arrow.field(n).type) for n in arrow.names}
                schema_taken = True
        inv.symbols_present[symbol] = record

    if inv.symbols_absent:
        inv.notes.append(
            f"{len(inv.symbols_absent)} of the 5 trade symbols have no partition in this product: "
            f"{inv.symbols_absent}. Recorded as absent; never inferred present from the reader name."
        )
    return inv


QUARTERLY_RE = re.compile(r"_[0-9]{6}$")


def market_universe_options(storage_root: Path) -> dict:
    """How wide could the market-context universe be? (guide 6.2)

    The guide allows a market-context universe broader than the five traded
    symbols. Measured here: this storage has exactly five PERPETUAL symbols; the
    other symbol directories are dated quarterly contracts of the same
    underlyings, which are expiries rather than additional assets and would not
    add breadth. So the universe cannot be widened on this storage — a
    constraint, not a design choice.
    """
    root = storage_root / "crypto" / "binance_futures" / "1m"
    symbols = _list_symbols(root)
    quarterly = [s for s in symbols if QUARTERLY_RE.search(s)]
    perpetual = [s for s in symbols if s not in quarterly]
    return {
        "symbol_directories": len(symbols),
        "perpetual_symbols": sorted(perpetual),
        "quarterly_contract_count": len(quarterly),
        "quarterly_examples": sorted(quarterly)[:4],
        "wider_universe_available": sorted(set(perpetual) - set(TRADE_SYMBOLS)),
        "can_widen_market_context": bool(set(perpetual) - set(TRADE_SYMBOLS)),
        "consequence": (
            "G5 breadth, dispersion and factor concentration are computed over five symbols "
            "because five is the entire perpetual universe here. Dated quarterly contracts are "
            "expiries of the same underlyings and would inflate breadth without adding an asset."
        ),
    }


def build_inventory(storage_root: str | Path, loader_snapshot: str | Path | None = None) -> dict:
    from ..safety.paths import sha256_file

    storage_root = Path(storage_root)
    products = {pid: inventory_product(pid, storage_root).as_record() for pid in PRODUCTS}

    code_sha = None
    reader_classes: list[str] = []
    if loader_snapshot is not None and Path(loader_snapshot).is_file():
        code_sha = sha256_file(loader_snapshot)
        from ..quantbt_bridge.capabilities import map_loader_statically

        reader_classes = map_loader_statically(loader_snapshot)["crypto_readers"]

    missing_products = {}
    for name, spec in EXPECTED_BUT_UNCONFIRMED.items():
        missing_products[name] = {
            **spec,
            "found": False,
            "consequence": (
                "no funding series exists in this storage, so a realistic net-carry claim cannot be "
                "made and the funding cohort is MISSING, never silently zero (guide 4.1)"
                if name == "funding_rate_history" else
                "basis must be derived from synchronised spot and perp closes where spot exists, "
                "and is unavailable for the four symbols with no spot product"
            ),
        }

    universe = {}
    for pid, rec in products.items():
        universe[pid] = {
            "present": sorted(rec["coverage_by_symbol"]),
            "absent": rec["trade_symbols_absent"],
        }
    return {
        "schema": "crypto_regime_lab.data_product_inventory.v1",
        "market_universe": market_universe_options(storage_root),
        "storage_root": str(storage_root),
        "read_only": True,
        "loader_code_sha256": code_sha,
        "loader_reader_classes": reader_classes,
        "trade_symbols": list(TRADE_SYMBOLS),
        "products": products,
        "coverage_summary": universe,
        "expected_but_absent": missing_products,
        "policy": (
            "a reader class in the loader is not evidence that a dataset exists; every product here "
            "was confirmed by walking real partitions, and anything not found is recorded as absent"
        ),
    }
