"""Instrument registry inferred from the snapshot (closes LAB-01's open blocker).

The study registration left ``instrument_registry_digest`` null because tick and
lot metadata had not been pinned. This module derives them from the frozen
snapshot rather than from a hardcoded table, and records that the quantity step
is NOT constant over the sample for every symbol.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

CANDIDATE_TICKS = (1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.05, 0.1, 0.5, 1.0, 10.0)
CANDIDATE_STEPS = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 1.0, 10.0)


def _infer_step(values: np.ndarray, candidates: tuple[float, ...]) -> float | None:
    """Largest candidate step that divides every observed value."""
    finite = values[np.isfinite(values)]
    finite = finite[finite > 0]
    if finite.size == 0:
        return None
    best = None
    for step in candidates:
        scaled = finite / step
        if np.all(np.abs(scaled - np.round(scaled)) < 1e-6):
            best = step
    return best


def infer_instrument(snapshot_root: Path, symbol: str, partitions: list[str]) -> dict:
    from .panel import normalize_numeric_dtypes

    base = Path(snapshot_root) / "crypto_binance_futures_1m" / symbol
    eras: list[dict] = []
    for partition in partitions:
        path = base / f"{partition}.parquet"
        if not path.is_file():
            continue
        frame, _ = normalize_numeric_dtypes(
            pd.read_parquet(path, columns=["close", "high", "low", "volume"]))
        prices = pd.concat([frame["close"], frame["high"], frame["low"]]).to_numpy(float)
        eras.append({
            "partition": partition,
            "tick_size": _infer_step(prices, CANDIDATE_TICKS),
            "qty_step": _infer_step(frame["volume"].to_numpy(float), CANDIDATE_STEPS),
            "min_observed_volume": float(np.nanmin(frame["volume"].replace(0, np.nan))),
            "min_observed_price": float(np.nanmin(prices)),
        })
    ticks = sorted({e["tick_size"] for e in eras if e["tick_size"]})
    steps = sorted({e["qty_step"] for e in eras if e["qty_step"]})
    return {
        "symbol": symbol,
        "eras_sampled": eras,
        "tick_sizes_observed": ticks,
        "qty_steps_observed": steps,
        "tick_stable": len(ticks) <= 1,
        "qty_step_stable": len(steps) <= 1,
        "conservative_tick_size": max(ticks) if ticks else None,
        "conservative_qty_step": max(steps) if steps else None,
        "note": ("inferred from observed price and quantity granularity in the frozen snapshot; "
                 "the venue's published metadata would be authoritative if it were available here"),
    }


def build_registry(snapshot_root: str | Path, symbols: list[str],
                   partitions: list[str]) -> dict:
    instruments = {s: infer_instrument(Path(snapshot_root), s, partitions) for s in symbols}
    unstable = [s for s, rec in instruments.items() if not rec["qty_step_stable"]]
    payload = {
        "schema": "crypto_regime_lab.instrument_registry.v1",
        "source": "inferred from the server_core_v1 snapshot",
        "instruments": instruments,
        "quantity_step_unstable_symbols": unstable,
        "policy": (
            "a single pinned step would be wrong for a symbol whose step changed mid-sample; the "
            "conservative (largest) observed step is used and the instability is recorded so an "
            "execution study can split the sample by era"
        ),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    payload["registry_digest"] = digest
    return payload
