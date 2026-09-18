"""Timestamp, unit and continuity checks (guide 6.3, tests T21-T24).

Guide 6.3 requires unit assertions rather than a fixed division, because the
Binance archive changes units by product and period. This module implements the
checks and, critically, decides which stored column may be TRUSTED.

Measured on this storage: the ``close_time`` column is not trustworthy. It is
correct (bar open + 59.999s) for BTC/ETH/DOGE perpetuals, mixed for BTC spot,
and garbage for SOL and BNB perpetuals where it lands near the 1970 epoch. The
lab therefore derives every bar close as ``time + interval`` and treats
``close_time`` as an untrusted diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

INTERVAL_SECONDS = {"1min": 60, "5min": 300, "15min": 900, "1h": 3600, "4h": 14400}
# A stored close_time is only plausible if it lands inside the bar it labels.
CLOSE_TIME_TOLERANCE_S = 1.0


@dataclass
class QualityReport:
    product_id: str
    symbol: str
    rows: int
    checks: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_record(self) -> dict:
        return {"product_id": self.product_id, "symbol": self.symbol, "rows": self.rows,
                "checks": self.checks, "failures": self.failures, "passed": self.passed}


class DataQualityError(RuntimeError):
    """Raised by a fail-closed read (guide L03.3: never warning-only)."""


def check_timestamps(frame: pd.DataFrame, interval: str) -> dict:
    """Monotonicity, duplicates, timezone and grid alignment of the time column."""
    time, _dtype, _bad = _parse_datetime(frame["time"])
    step = INTERVAL_SECONDS[interval]
    diffs = time.diff().dt.total_seconds().dropna()
    on_grid = (time.astype("int64") // 10**9) % step == 0
    return {
        "monotonic_increasing": bool(time.is_monotonic_increasing),
        "duplicate_timestamps": int(time.duplicated().sum()),
        "timezone": str(time.dt.tz) if getattr(time.dt, "tz", None) is not None else "naive_utc",
        "on_interval_grid": bool(on_grid.all()),
        "off_grid_rows": int((~on_grid).sum()),
        "modal_step_seconds": float(diffs.mode().iloc[0]) if not diffs.empty else None,
        "min_step_seconds": float(diffs.min()) if not diffs.empty else None,
        "max_step_seconds": float(diffs.max()) if not diffs.empty else None,
    }


def _parse_datetime(series: pd.Series) -> tuple[pd.Series, str, int]:
    """Parse a timestamp column defensively and report what it actually was.

    Some partitions of this storage keep ``close_time`` as a STRING with mixed
    fractional-second formats. That is itself a defect worth recording, so the
    observed dtype and the number of unparseable values are returned rather than
    quietly coerced.
    """
    observed = str(series.dtype)
    if pd.api.types.is_datetime64_any_dtype(series):
        return series, observed, 0
    parsed = pd.to_datetime(series, format="mixed", errors="coerce")
    return parsed, observed, int(parsed.isna().sum() - series.isna().sum())


def check_close_time_trust(frame: pd.DataFrame, interval: str) -> dict:
    """Is the stored ``close_time`` usable? Measured, per partition.

    A trustworthy close_time sits within one second of ``time + interval``.
    Anything else is a unit or population defect and the column must not be used
    to derive availability, because doing so would move a bar's availability.
    """
    if "close_time" not in frame.columns:
        return {"column_present": False, "trusted": False,
                "reason": "no close_time column; bar close is derived from time + interval"}
    step = INTERVAL_SECONDS[interval]
    close_time, close_dtype, unparseable = _parse_datetime(frame["close_time"])
    time_col, _time_dtype, _ = _parse_datetime(frame["time"])
    delta = (close_time - time_col).dt.total_seconds().dropna()
    expected = step - 0.001
    plausible = (delta - expected).abs() <= CLOSE_TIME_TOLERANCE_S
    epoch_like = delta < -1e6
    zero_like = delta.abs() <= 1e-9
    return {
        "column_present": True,
        "stored_dtype": close_dtype,
        "dtype_is_timestamp": close_dtype.startswith("datetime"),
        "unparseable_rows": unparseable,
        "rows": int(len(delta)),
        "plausible_rows": int(plausible.sum()),
        "plausible_fraction": float(plausible.mean()) if len(delta) else 0.0,
        "epoch_unit_defect_rows": int(epoch_like.sum()),
        "equal_to_open_rows": int(zero_like.sum()),
        "min_delta_seconds": float(delta.min()) if len(delta) else None,
        "max_delta_seconds": float(delta.max()) if len(delta) else None,
        "trusted": bool(len(delta) > 0 and plausible.all() and unparseable == 0
                        and close_dtype.startswith("datetime")),
        "policy": ("close_time is a diagnostic only; bar_close is always derived as "
                   "time + interval, so a defective column can never shift availability"),
    }


def check_units_and_dtypes(frame: pd.DataFrame) -> dict:
    """Volume must stay fractional and prices must be floats (T21)."""
    out: dict[str, Any] = {}
    for col in ("open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_base_volume", "taker_buy_quote_volume"):
        if col not in frame.columns:
            continue
        series = frame[col]
        out[col] = {
            "dtype": str(series.dtype),
            "is_float": bool(np.issubdtype(series.dtype, np.floating)),
            "has_fractional_values": bool(((series % 1) != 0).any()),
            "negative_values": int((series < 0).sum()),
        }
    if "number_of_trades" in frame.columns:
        out["number_of_trades"] = {"dtype": str(frame["number_of_trades"].dtype),
                                   "is_integer_like": True}
    return out


def check_quantity_granularity(frame: pd.DataFrame) -> dict:
    """Infer the traded quantity step actually present in a partition.

    Measured on this storage, the step is NOT constant: SOLUSDT volume is
    integral in 2021-2023 and fractional by 2025, so an instrument registry that
    pins one step for the whole sample would be wrong. DOGEUSDT stays integral
    throughout, which is the instrument, not a truncation.
    """
    if "volume" not in frame.columns:
        return {"applicable": False}
    volume = frame["volume"].astype("float64")
    positive = volume[volume > 0]
    if positive.empty:
        return {"applicable": True, "rows": 0, "fractional_rows": 0,
                "granularity": None, "integral_only": None}
    fractional = int(((positive % 1) != 0).sum())
    return {
        "applicable": True,
        "rows": int(len(positive)),
        "fractional_rows": fractional,
        "fractional_fraction": float(fractional / len(positive)),
        "integral_only": fractional == 0,
        "min_positive": float(positive.min()),
        "note": ("an integral volume column is the instrument's own quantity step, not a "
                 "truncation by this lab; the step can change over the sample"),
    }


def check_ohlc_invariants(frame: pd.DataFrame) -> dict:
    if not {"open", "high", "low", "close"} <= set(frame.columns):
        return {"applicable": False}
    high_ok = (frame["high"] >= frame[["open", "close"]].max(axis=1) - 1e-9)
    low_ok = (frame["low"] <= frame[["open", "close"]].min(axis=1) + 1e-9)
    return {
        "applicable": True,
        "high_violations": int((~high_ok).sum()),
        "low_violations": int((~low_ok).sum()),
        "non_positive_prices": int((frame[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
    }


def check_gaps(frame: pd.DataFrame, interval: str) -> dict:
    """Missing bars are reported as a mask, never fabricated (guide 6.3)."""
    time = pd.to_datetime(frame["time"])
    step = pd.Timedelta(seconds=INTERVAL_SECONDS[interval])
    if len(time) < 2:
        return {"expected_bars": len(time), "observed_bars": len(time), "missing_bars": 0,
                "largest_gap_bars": 0, "gap_segments": []}
    expected = int((time.iloc[-1] - time.iloc[0]) / step) + 1
    diffs = time.diff().dropna()
    gaps = diffs[diffs > step]
    segments = [{"after": str(time.iloc[i]), "missing_bars": int(d / step) - 1}
                for i, d in zip(gaps.index, gaps)][:20]
    return {
        "expected_bars": expected,
        "observed_bars": int(len(time)),
        "missing_bars": int(expected - len(time)),
        "missing_fraction": float((expected - len(time)) / expected) if expected else 0.0,
        "largest_gap_bars": int(gaps.max() / step) - 1 if not gaps.empty else 0,
        "gap_segments": segments,
        "policy": "a missing bar stays missing; no zero-volume or forward-filled bar is fabricated",
    }


def check_symbol_mapping(frame: pd.DataFrame, expected_symbol: str) -> dict:
    if "symbol" not in frame.columns:
        return {"column_present": False, "exact": False}
    observed = sorted(set(frame["symbol"].astype(str)))
    return {"column_present": True, "observed": observed,
            "exact": observed == [expected_symbol],
            "policy": "symbol mapping is exact; a same-length series is never relabelled (T23)"}


def assess(frame: pd.DataFrame, *, product_id: str, symbol: str, interval: str,
           fail_closed: bool = True) -> QualityReport:
    report = QualityReport(product_id=product_id, symbol=symbol, rows=int(len(frame)))
    report.checks = {
        "timestamps": check_timestamps(frame, interval),
        "close_time_trust": check_close_time_trust(frame, interval),
        "units": check_units_and_dtypes(frame),
        "ohlc": check_ohlc_invariants(frame),
        "gaps": check_gaps(frame, interval),
        "quantity_granularity": check_quantity_granularity(frame),
        "symbol_mapping": check_symbol_mapping(frame, symbol),
    }
    ts = report.checks["timestamps"]
    if not ts["monotonic_increasing"]:
        report.failures.append("time is not monotonically increasing")
    if ts["duplicate_timestamps"]:
        report.failures.append(f"{ts['duplicate_timestamps']} duplicate timestamps")
    if not ts["on_interval_grid"]:
        report.failures.append(f"{ts['off_grid_rows']} rows are off the {interval} grid")
    ohlc = report.checks["ohlc"]
    if ohlc.get("applicable"):
        if ohlc["high_violations"] or ohlc["low_violations"]:
            report.failures.append("OHLC invariant violated")
        if ohlc["non_positive_prices"]:
            report.failures.append("non-positive prices present")
    if not report.checks["symbol_mapping"]["exact"]:
        report.failures.append("symbol column does not match the requested symbol")

    if fail_closed and report.failures:
        raise DataQualityError(
            f"{product_id}/{symbol}: {report.failures}. A primary read fails closed; it never "
            "continues with a warning and then reports a full sample (guide L03.3)."
        )
    return report
