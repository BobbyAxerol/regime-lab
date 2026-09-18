"""L03.3 — availability, resampling and staleness (guide 6.3).

Every row the lab uses carries the full timestamp set the guide names:

    event_time            the observation's own timestamp
    bar_open / bar_close  the bucket boundaries, DERIVED as time + interval
    source_published_at   when the venue could have published it
    available_at          bar_close + publication delay: the first moment a
                          causal decision may use the row
    archive_ingested_at   when this archive received it
    vintage_id            source + ingest identity of the row

``bar_close`` is derived, never read from the stored ``close_time`` column: that
column is defective on this storage (see ``quality.check_close_time_trust``), and
trusting it would move availability by up to a full bar.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .quality import INTERVAL_SECONDS

# Publication delay per product kind. Zero is a DECLARED choice for an archive
# whose bars are published at the bar close, not an accidental default.
DEFAULT_PUBLICATION_DELAY = {
    "ohlcv_bars": pd.Timedelta(0),
    "derivatives_metrics": pd.Timedelta(0),
    "book_snapshot": pd.Timedelta(0),
}
# How long an observation may be reused before it is stale.
DEFAULT_TTL = {
    "ohlcv_bars": None,                       # a closed bar never goes stale
    "derivatives_metrics": pd.Timedelta("30min"),
    "book_snapshot": pd.Timedelta("2h"),
}

# Aggregation contract for a 1m -> Nm/h resample (guide 6.3).
OHLCV_AGGREGATION = {
    "open": "first", "high": "max", "low": "min", "close": "last",
    "volume": "sum", "quote_volume": "sum", "number_of_trades": "sum",
    "taker_buy_base_volume": "sum", "taker_buy_quote_volume": "sum",
}
# Columns that must NEVER be summed.
LAST_VALUE_COLUMNS = (
    "sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio", "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio", "mid_price", "best_bid", "best_ask", "spread",
    "spread_bps",
)


class AvailabilityError(RuntimeError):
    """Raised by a fail-closed availability build."""


@dataclass
class AvailabilityRules:
    product_id: str
    kind: str
    interval: str
    publication_delay: pd.Timedelta
    ttl: pd.Timedelta | None
    bar_close_rule: str = "derived: time + interval (the stored close_time is untrusted)"
    available_at_rule: str = "bar_close + publication_delay"

    def as_record(self) -> dict:
        return {
            "product_id": self.product_id,
            "kind": self.kind,
            "interval": self.interval,
            "publication_delay_seconds": float(self.publication_delay.total_seconds()),
            "ttl_seconds": None if self.ttl is None else float(self.ttl.total_seconds()),
            "bar_timestamp_convention": "left-labelled: `time` is the bar OPEN",
            "bar_close_rule": self.bar_close_rule,
            "available_at_rule": self.available_at_rule,
            "vintage_id_rule": "source + archive_ingested_at",
        }


def rules_for(product_id: str, kind: str, interval: str,
              publication_delay: pd.Timedelta | None = None,
              ttl: pd.Timedelta | None = ...) -> AvailabilityRules:
    delay = DEFAULT_PUBLICATION_DELAY.get(kind, pd.Timedelta(0)) \
        if publication_delay is None else publication_delay
    resolved_ttl = DEFAULT_TTL.get(kind) if ttl is ... else ttl
    return AvailabilityRules(product_id, kind, interval, delay, resolved_ttl)


def annotate_availability(frame: pd.DataFrame, rules: AvailabilityRules) -> pd.DataFrame:
    """Attach the full timestamp set. Never mutates the caller's frame."""
    out = frame.copy()
    time = pd.to_datetime(out["time"])
    step = pd.Timedelta(seconds=INTERVAL_SECONDS[rules.interval])

    out["event_time"] = time
    out["bar_open"] = time
    out["bar_close"] = time + step
    if rules.kind == "book_snapshot" and "sample_time" in out.columns:
        # A snapshot is available when it was actually sampled, not at the top of
        # the hour it is filed under (guide 6.3, T26).
        sampled = pd.to_datetime(out["sample_time"])
        out["source_published_at"] = sampled
        out["available_at"] = sampled + rules.publication_delay
        out["availability_basis"] = "sample_time"
    else:
        out["source_published_at"] = out["bar_close"]
        out["available_at"] = out["bar_close"] + rules.publication_delay
        out["availability_basis"] = "derived_bar_close"

    if "ingested_at" in out.columns:
        out["archive_ingested_at"] = pd.to_datetime(out["ingested_at"])
    else:
        out["archive_ingested_at"] = pd.NaT
    source = out["source"].astype(str) if "source" in out.columns else pd.Series(
        ["unknown"] * len(out), index=out.index)
    ingest_day = out["archive_ingested_at"].dt.strftime("%Y%m%d").fillna("unknown")
    out["vintage_id"] = source + "@" + ingest_day
    return out


def resample_bars(frame: pd.DataFrame, source_interval: str, target_interval: str,
                  *, require_complete: bool = True) -> pd.DataFrame:
    """Aggregate closed buckets only, with the guide's per-column contract.

    A bucket missing any constituent bar is marked incomplete. With
    ``require_complete`` it is DROPPED rather than aggregated over a hole, so a
    partial bucket can never masquerade as a full one.
    """
    src_step = INTERVAL_SECONDS[source_interval]
    tgt_step = INTERVAL_SECONDS[target_interval]
    if tgt_step % src_step:
        raise AvailabilityError(f"{target_interval} is not a whole multiple of {source_interval}")
    expected_per_bucket = tgt_step // src_step

    work = frame.copy()
    work["time"] = pd.to_datetime(work["time"])
    work = work.set_index("time").sort_index()

    agg = {col: how for col, how in OHLCV_AGGREGATION.items() if col in work.columns}
    for col in LAST_VALUE_COLUMNS:
        if col in work.columns:
            agg[col] = "last"          # never summed (guide 6.3)
    rule = f"{tgt_step}s"
    grouped = work.resample(rule, label="left", closed="left")
    out = grouped.agg(agg)
    out["bars_in_bucket"] = grouped.size()
    out["complete"] = out["bars_in_bucket"] == expected_per_bucket

    if "symbol" in work.columns:
        out["symbol"] = grouped["symbol"].last()
    if "source" in work.columns:
        out["source"] = grouped["source"].last()
    if "ingested_at" in work.columns:
        out["ingested_at"] = grouped["ingested_at"].max()

    out = out[out["bars_in_bucket"] > 0]
    incomplete = int((~out["complete"]).sum())
    if require_complete:
        out = out[out["complete"]]
    out = out.reset_index().rename(columns={"index": "time"})
    out.attrs["expected_bars_per_bucket"] = expected_per_bucket
    out.attrs["incomplete_buckets_dropped"] = incomplete if require_complete else 0
    out.attrs["incomplete_buckets_seen"] = incomplete
    return out


def staleness_mask(available_at: pd.Series, as_of: pd.Series | pd.Timestamp,
                   ttl: pd.Timedelta | None) -> pd.Series:
    """True where an observation is too old to be reused."""
    if ttl is None:
        return pd.Series(False, index=available_at.index)
    reference = as_of if isinstance(as_of, pd.Series) else pd.Series(as_of, index=available_at.index)
    return (reference - pd.to_datetime(available_at)) > ttl


def as_of_join(base: pd.DataFrame, other: pd.DataFrame, *, columns: list[str],
               ttl: pd.Timedelta | None, suffix: str = "") -> pd.DataFrame:
    """Backward as-of join on ``available_at`` (guide 6.3), with a TTL.

    Joining on the label timestamp instead would let a decision read a bucket
    that had not closed yet; joining on availability cannot.
    """
    left = base.sort_values("available_at").copy()
    right = other.sort_values("available_at")[["available_at", *columns]].copy()
    right = right.rename(columns={c: f"{c}{suffix}" for c in columns})
    merged = pd.merge_asof(left, right, on="available_at", direction="backward")
    joined = [f"{c}{suffix}" for c in columns]
    if ttl is not None:
        source_time = pd.merge_asof(
            left[["available_at"]], other.sort_values("available_at")[["available_at"]]
            .assign(_src_available=lambda d: d["available_at"]),
            on="available_at", direction="backward")["_src_available"]
        stale = (merged["available_at"].to_numpy() - source_time.to_numpy()) > ttl.to_timedelta64()
        merged["stale"] = stale
        merged.loc[stale, joined] = np.nan
    else:
        merged["stale"] = False
    merged["missing"] = merged[joined].isna().all(axis=1)
    return merged


def funding_events(_snapshot_root) -> dict:
    """Funding is a separate event stream — and it does not exist on this storage."""
    return {
        "schema": "crypto_regime_lab.funding_events.v1",
        "events": [],
        "status": "MISSING",
        "searched": ["crypto/* products", "the loader's reader classes"],
        "policy": (
            "a missing funding history is NEVER treated as zero carry. Any cohort that would need "
            "funding is marked missing, and a no-funding study carries its own disclaimer "
            "(guide 4.1)."
        ),
        "consequence_for_primary": (
            "the primary economic contract runs with use_funding=False and is labelled a "
            "no-funding cohort; it may not claim realistic net carry"
        ),
    }
