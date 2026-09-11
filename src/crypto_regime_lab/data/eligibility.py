"""L03.6 — eligibility, cohorts and usable intervals (guide 6.2).

Answers, per symbol and per cohort: when does data actually start, when is the
first bar a decision may use after warmup, which products are behind it, and
what is the common period across the universe.

The guide's warning is the design constraint: do not intersect every source and
shrink the core cohort to a month. Cohorts are therefore reported separately,
each with its own usable interval, instead of being collapsed into one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# The user's convention: spot is treated clean from this date. Earlier spot bars
# exist in storage (BTCUSDT back to 2018) but sit OUTSIDE the convention, so they
# are excluded from eligibility rather than quietly used.
SPOT_CLEAN_FROM = "2020-01-01"

COHORTS = {
    "SERVER_CORE_LONG": {
        "products": ["crypto_binance_futures_1m"],
        "meaning": "perpetual OHLCV with quote volume, trade count and taker volumes",
        "role": "primary signal and execution venue (guide 4.1)",
    },
    "SERVER_CORE_SPOT": {
        "products": ["crypto_binance_spot_1m"],
        "meaning": "spot OHLCV, treated clean from 2020-01-01 by user convention",
        "role": "basis and spot-activity context",
    },
    "SERVER_DERIVATIVES": {
        "products": ["crypto_binance_futures_metrics_5m"],
        "meaning": "open interest and trader ratios",
        "role": "G3 leverage and crowding",
    },
    "SERVER_LIQUIDITY": {
        "products": ["crypto_binance_orderbook_snapshot_1h"],
        "meaning": "hourly REST depth snapshots",
        "role": "G4 spread and depth",
    },
    "FREE_ENRICHED": {
        "products": [],
        "meaning": "external free sources",
        "role": "optional; never a prerequisite",
    },
}


@dataclass
class SymbolEligibility:
    symbol: str
    data_start: str | None
    data_end: str | None
    warmup_bars: int
    first_decision_bar: str | None
    products: dict[str, dict] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)

    def as_record(self) -> dict:
        return {
            "symbol": self.symbol,
            "data_start": self.data_start,
            "data_end": self.data_end,
            "warmup_bars": self.warmup_bars,
            "first_decision_bar": self.first_decision_bar,
            "usable_interval": [self.first_decision_bar, self.data_end],
            "products": self.products,
            "blockers": self.blockers,
        }


def symbol_eligibility(symbol: str, manifest: dict, warmup_bars: int,
                       regime_interval: str = "4h") -> SymbolEligibility:
    per_product: dict[str, dict] = {}
    for record in manifest["files"]:
        if record["symbol"] != symbol:
            continue
        entry = per_product.setdefault(record["product_id"], {
            "partitions": 0, "closed_partitions": 0, "rows": 0,
            "time_min": record["time_min"], "time_max": record["time_max"],
            "sources": set()})
        entry["partitions"] += 1
        entry["closed_partitions"] += int(record["closed"])
        entry["rows"] += record["rows"]
        entry["time_min"] = min(entry["time_min"], record["time_min"])
        entry["time_max"] = max(entry["time_max"], record["time_max"])
        entry["sources"].update(record["sources"])
    for entry in per_product.values():
        entry["sources"] = sorted(entry["sources"])

    spot = per_product.get("crypto_binance_spot_1m")
    if spot is not None:
        spot["storage_time_min"] = spot["time_min"]
        spot["clean_convention_from"] = SPOT_CLEAN_FROM
        spot["eligible_time_min"] = max(spot["time_min"], SPOT_CLEAN_FROM)
        spot["pre_convention_data_excluded"] = spot["time_min"] < SPOT_CLEAN_FROM
        spot["exclusion_reason"] = (
            "storage holds spot before the user's clean-from date; those bars are outside the "
            "convention and are not eligible, rather than being used silently")

    primary = per_product.get("crypto_binance_futures_1m")
    if primary is None:
        return SymbolEligibility(symbol, None, None, warmup_bars, None, per_product,
                                 ["no primary perpetual product for this symbol"])
    start = pd.Timestamp(primary["time_min"])
    end = pd.Timestamp(primary["time_max"])
    step = pd.Timedelta(regime_interval)
    first_decision = start + step * warmup_bars
    blockers = []
    for cohort, spec in COHORTS.items():
        for product in spec["products"]:
            if product not in per_product and product != "crypto_binance_futures_1m":
                blockers.append(f"{cohort}: {product} absent for {symbol}")
    return SymbolEligibility(symbol, str(start), str(end), warmup_bars,
                             str(first_decision), per_product, blockers)


def cohort_report(manifest: dict, symbols: list[str], warmup_bars: int) -> dict:
    eligibility = {s: symbol_eligibility(s, manifest, warmup_bars).as_record() for s in symbols}

    cohorts: dict[str, Any] = {}
    for name, spec in COHORTS.items():
        members, intervals = [], []
        for symbol, rec in eligibility.items():
            if all(p in rec["products"] for p in spec["products"]) and spec["products"]:
                members.append(symbol)
                product = spec["products"][0]
                entry = rec["products"][product]
                start = entry.get("eligible_time_min", entry["time_min"])
                intervals.append((start, entry["time_max"]))
        common = None
        if intervals:
            common = [max(a for a, _ in intervals), min(b for _, b in intervals)]
        cohorts[name] = {
            **spec,
            "members": members,
            "member_count": len(members),
            "common_period": common,
            "status": "AVAILABLE" if members else "EMPTY",
        }

    core = cohorts["SERVER_CORE_LONG"]
    return {
        "schema": "crypto_regime_lab.eligibility_report.v1",
        "snapshot_id": manifest["snapshot_id"],
        # A snapshot_id alone does not pin a document: server_core_v1 was read
        # more than once while the collector was still appending to the open
        # trailing month, and an eligibility report written from an earlier pass
        # under-counts rows while still naming the same snapshot. Recording the
        # manifest's own ingest stamp and row total makes a stale copy visible
        # instead of leaving it to be discovered by hand.
        "manifest_ingest_finished_utc": manifest.get("ingest_finished_utc"),
        "manifest_total_rows": manifest["total_rows"],
        "warmup_bars": warmup_bars,
        "per_symbol": eligibility,
        "cohorts": cohorts,
        "five_symbol_common_period": core["common_period"],
        "per_symbol_longest_history": {
            s: [rec["data_start"], rec["data_end"]] for s, rec in eligibility.items()
        },
        "reporting_rule": (
            "the five-symbol common-period aggregate is reported SEPARATELY from each symbol's "
            "longest valid history; returns are never back-filled with zeros before listing "
            "(guide 10.4)"
        ),
        "spot_clean_convention": {
            "clean_from": SPOT_CLEAN_FROM,
            "rule": "spot bars before this date exist in storage but are outside the user's clean "
                    "convention and are excluded from eligibility",
        },
        "no_intersection_collapse": (
            "cohorts are reported independently. Intersecting every source would shrink the core "
            "cohort to the orderbook product's few weeks, which the guide forbids (6.2)."
        ),
    }
