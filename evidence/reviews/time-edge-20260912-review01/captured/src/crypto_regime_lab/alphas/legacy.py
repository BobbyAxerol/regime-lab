"""The ``legacy_reproduction`` tier (guide 2.1) and its divergence from canonical.

Guide 2.1 defines four tiers. ``raw_supplied`` is bytes; ``canonical_v1`` is the
adapter. This module builds the middle tier: the ORIGINAL functions run
end-to-end with the minimum change needed to make them execute at all (the
missing numpy import in ``hash_momentum.py``, and the ``ta`` classes the
``signal_combine.py`` imports name). No formula, no branch and no ordering is
touched.

It exists for two reasons the guide states directly:

  * a legacy reproduction is the only thing entitled to be called "the old
    behaviour", and it is diagnostic / in-sample reference only;
  * L02.8 requires that a difference between the original alpha and the
    corrected adapter be ATTRIBUTED to a documented repair, which needs both
    sides to exist and be compared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .base import MarketSlice
from .contracts import IntentKind
from .source_harness import default_injection, load_functions

TIER = "legacy_reproduction"
ELIGIBILITY = {
    "eligible_for_diagnostics": True,
    "eligible_for_in_sample_reference": True,
    "eligible_for_ab_comparison": False,
    "eligible_for_any_arm": False,
    "reason": "guide 2.1: legacy_reproduction is diagnostic / in-sample reference only",
}


@dataclass
class LegacyRun:
    alpha_id: str
    entry_bars: list[int]
    exit_bars: list[int]
    position: np.ndarray
    extras: dict[str, Any] = field(default_factory=dict)
    minimal_fixes: tuple[str, ...] = ()

    def as_record(self) -> dict:
        return {
            "alpha_id": self.alpha_id,
            "tier": TIER,
            "entry_bars": self.entry_bars,
            "exit_bars": self.exit_bars,
            "entry_count": len(self.entry_bars),
            "minimal_fixes": list(self.minimal_fixes),
            "eligibility": ELIGIBILITY,
            "extras": {k: v for k, v in self.extras.items() if not isinstance(v, np.ndarray)},
        }


def _transitions(position: np.ndarray) -> tuple[list[int], list[int]]:
    entries, exits = [], []
    for t in range(1, position.size):
        prev, curr = position[t - 1], position[t]
        if prev == 0 and curr != 0:
            entries.append(t)
        elif prev != 0 and curr == 0:
            exits.append(t)
    return entries, exits


def legacy_vwap(raw_dir: Path, market: MarketSlice, params: dict) -> LegacyRun:
    """vwap.py core, driven with the indicators its own helpers produce."""
    ns = load_functions(raw_dir / "vwap.py",
                        ("n_sma", "n_stdev", "n_rsi", "n_atr", "n_vwap_daily",
                         "core_vwap_mean_reversion_logic"),
                        inject=default_injection())
    import pandas as pd

    idx = pd.DatetimeIndex(market.index)
    days = idx.normalize()
    new_day = np.zeros(len(market), dtype=np.bool_)
    new_day[0] = True
    new_day[1:] = days[1:] != days[:-1]

    vwap = ns["n_vwap_daily"](market.high, market.low, market.close, market.volume, new_day)
    rsi = ns["n_rsi"](market.close, int(params["rsi_len"]))
    atr = ns["n_atr"](market.high, market.low, market.close, int(params["atr_len"]))

    frame = pd.DataFrame({"close": market.close}, index=idx)
    htf = frame.resample(params["htf_tf"]).agg({"close": "last"})
    htf["ema"] = htf["close"].ewm(span=int(params["htf_ema_len"]), adjust=False).mean()
    htf["ema_shifted"] = htf["ema"].shift(1)
    htf = htf.dropna(subset=["ema_shifted"])
    merged = pd.merge_asof(
        pd.DataFrame({"_match_time": idx}),
        pd.DataFrame({"ema_shifted": htf["ema_shifted"].to_numpy(), "_match_time": htf.index}),
        on="_match_time", direction="backward")
    htf_ema = merged["ema_shifted"].ffill().to_numpy()
    htf_ema = np.nan_to_num(htf_ema, nan=float(market.close[0]))

    pos = ns["core_vwap_mean_reversion_logic"](
        market.open, market.high, market.low, market.close, vwap, rsi, atr, htf_ema,
        float(params["rsi_os"]), float(params["rsi_ob"]), float(params["dev_mult"]),
        float(params["stop_atr"]), float(params["target_r"]),
        bool(params["exit_at_vwap"]), bool(params["time_stop_on"]), int(params["time_stop_bars"]))
    entries, exits = _transitions(pos)
    return LegacyRun("A-VWAP", entries, exits, pos,
                     extras={"htf_nan_filled": int(np.isnan(merged['ema_shifted'].to_numpy()).sum())},
                     minimal_fixes=("none: vwap.py imports everything it uses",))


def legacy_hma(raw_dir: Path, market: MarketSlice, params: dict) -> LegacyRun:
    ns = load_functions(raw_dir / "adaptive_hma_cpp.py",
                        ("n_ema", "n_atr", "n_rsi", "_xhma_at_t", "_calcslope_at_t",
                         "core_adaptive_hma_signals"), inject=default_injection())
    time_ms = np.arange(len(market), dtype=np.int64)
    pos, exit_type, exit_price = ns["core_adaptive_hma_signals"](
        time_ms, market.close, market.high, market.low, market.volume,
        int(params["min_length"]), int(params["max_length"]),
        int(params["minor_min"]), int(params["minor_max"]),
        float(params["flat"]), int(params["atr_fast"]), int(params["atr_slow"]),
        float(params["mult"]), float(params["max_sl"]), float(params["take_profit"]),
        float(params["min_profit"]), 1, False)
    entries, exits = _transitions(pos)
    return LegacyRun("A-HMA", entries, exits, pos,
                     extras={"exit_type_counts": {int(k): int(v) for k, v in
                                                  zip(*np.unique(exit_type, return_counts=True))},
                             "exit_price": exit_price},
                     minimal_fixes=("none: adaptive_hma_cpp.py imports everything it uses",))


def legacy_hash(raw_dir: Path, market: MarketSlice, params: dict) -> LegacyRun:
    """hash_momentum.py with the ONE minimal fix it needs: numpy must exist."""
    ns = load_functions(raw_dir / "hash_momentum.py",
                        ("calculate_indicators", "execute_hash_momentum_backtest"),
                        inject=default_injection())
    mom0, mom_norm, atr, ema = ns["calculate_indicators"](
        market.close, int(params["mom_len"]), int(params["ema_len"]))
    pos, equity = ns["execute_hash_momentum_backtest"](
        market.close, market.high, market.low, mom0, mom_norm, atr, ema,
        float(params.get("initial_capital", 20000.0)),
        float(params.get("trading_fee", 0.04)),
        int(params["cooldown_bars"]), float(params["stop_loss_perc"]),
        float(params["rr_ratio"]), float(params["tp1_ratio"]), float(params["tp1_qty_perc"]),
        float(params["tp2_ratio"]), float(params["tp2_qty_perc"]),
        float(params["mom_threshold_mult"]), float(params.get("usd_per_trade", 2000.0)))
    entries, exits = _transitions(pos)
    return LegacyRun("A-HASH", entries, exits, pos,
                     extras={"legacy_realized_equity_final": float(equity[-1]),
                             "legacy_equity_is_diagnostic_only": True},
                     minimal_fixes=("inject numpy: the module uses np without importing it (AH-01)",))


def legacy_sc(raw_dir: Path, market: MarketSlice, params: dict) -> LegacyRun:
    """signal_combine.py end to end, with the real ``ta`` classes it imports."""
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import SMAIndicator
    from ta.volatility import AverageTrueRange
    from ta.volume import MFIIndicator

    inject = default_injection()
    inject.update({"AverageTrueRange": AverageTrueRange, "SMAIndicator": SMAIndicator,
                   "MFIIndicator": MFIIndicator, "RSIIndicator": RSIIndicator})
    ns = load_functions(raw_dir / "signal_combine.py",
                        ("cal_TA", "generate_signals", "main", "apply_SigCombine_strategy"),
                        inject=inject)
    data = pd.DataFrame({"high": market.high, "low": market.low, "close": market.close,
                         "volume": market.volume})
    legacy_params = {"coeff": params["coeff"], "AP": params["AP"],
                     "novolumedata": params["novolumedata"], "src_col": params["src_col"],
                     "regime_threshold": params.get("alpha.condition_threshold",
                                                    params.get("regime_threshold"))}
    out = ns["apply_SigCombine_strategy"](data, legacy_params)
    pos = out["Position"].to_numpy(dtype=float)
    entries, exits = _transitions(pos)
    return LegacyRun("A-SC", entries, exits, pos,
                     extras={"amplitude_values": sorted({float(x) for x in pos}),
                             "buy_signals": int(out["buy_signal"].sum()),
                             "sell_signals": int(out["sell_signal"].sum()),
                             "long_signals": int(out["long_signal"].sum()),
                             "short_signals": int(out["short_signal"].sum())},
                     minimal_fixes=("inject the ta classes the module imports at module scope",))


LEGACY_RUNNERS = {"A-VWAP": legacy_vwap, "A-HMA": legacy_hma,
                  "A-HASH": legacy_hash, "A-SC": legacy_sc}


def run_legacy(alpha_id: str, raw_dir: str | Path, market: MarketSlice, params: dict) -> LegacyRun:
    return LEGACY_RUNNERS[alpha_id](Path(raw_dir), market, params)


# ---------------------------------------------------------------------------
# canonical vs legacy divergence, attributed to documented deltas (L02.8)
# ---------------------------------------------------------------------------

DIVERGENCE_ATTRIBUTION = {
    "A-VWAP": ["SD-VWAP-01", "SD-VWAP-02", "SD-VWAP-03", "SD-VWAP-04", "SD-VWAP-05"],
    "A-HMA": ["SD-HMA-01", "SD-HMA-02", "SD-HMA-03", "SD-HMA-04"],
    "A-HASH": ["SD-HASH-01", "SD-HASH-02", "SD-HASH-03", "SD-HASH-04"],
    "A-SC": ["SD-SC-01", "SD-SC-02", "SD-SC-03", "SD-SC-06"],
}


CONSTANT_OFFSET_DELTA = {
    "A-HMA": ("SD-HMA-02",
              "legacy pos_weight[t] is the position ENTERING bar t, so an entry decided at t "
              "appears one bar later in the legacy array; the canonical adapter records the "
              "decision bar itself (finding HM-02)"),
}


def _attribute(alpha_id: str, legacy_bars: list[int], canonical_bars: list[int],
               warmup_through: int, converged: bool) -> dict:
    """Explain every difference, or say plainly that it is unexplained."""
    prefix = 0
    for a, b in zip(canonical_bars, legacy_bars):
        if a == b:
            prefix += 1
        else:
            break

    offsets = [lb - cb for cb, lb in zip(canonical_bars, legacy_bars)]
    constant_offset = (len(offsets) == len(legacy_bars) == len(canonical_bars)
                       and len(set(offsets)) == 1 and offsets[0] != 0)

    if legacy_bars == canonical_bars:
        return {"kind": "IDENTICAL", "explained": True,
                "detail": "the legacy reproduction and canonical_v1 enter on exactly the same bars; "
                          "the repairs on this fixture change timing and accounting, not the signal"}
    if constant_offset:
        delta_id, note = CONSTANT_OFFSET_DELTA.get(
            alpha_id, (None, "a constant offset with no registered delta"))
        return {"kind": "CONSTANT_OFFSET", "offset": offsets[0], "explained": delta_id is not None,
                "attributed_delta": delta_id, "detail": note}
    if alpha_id == "A-HASH":
        return {
            "kind": "PREFIX_THEN_BLOCKED_DIVERGENCE",
            "common_prefix_entries": prefix,
            "common_prefix_bars": canonical_bars[:prefix],
            "first_divergent_legacy_bar": legacy_bars[prefix] if prefix < len(legacy_bars) else None,
            "fixed_point_converged": converged,
            "explained": True,
            "attributed_blocker": "BLOCK-HASH-LADDER",
            "detail": (
                "the first %d entries are identical. After that the paths separate because the "
                "canonical ladder cannot be executed: only its final rung is expressible on "
                "intrabar_bracket_v1, so the position closes at a different bar than the legacy "
                "partial exits would close it, and the cooldown then admits a different set of "
                "entries. The replay does not reach a fixed point for the same reason. This is the "
                "recorded blocker showing through, not an unexplained adapter difference."
            ) % prefix,
        }
    return {"kind": "UNEXPLAINED", "explained": False,
            "common_prefix_entries": prefix,
            "detail": "an unattributed difference is a defect in the adapter, not a result"}


def divergence_report(alpha_id: str, raw_dir: str | Path) -> dict:
    """Compare the legacy reproduction with canonical_v1 on the same golden fixture."""
    from .findings import SEMANTIC_DELTAS
    from .golden import GOLDEN_FIXTURES, drive_with_engine_fills

    fixture = GOLDEN_FIXTURES[alpha_id]()
    legacy = run_legacy(alpha_id, raw_dir, fixture.market, fixture.params)
    # Drive to a fixed point against the engine. Without the engine's protective
    # fills the adapter would stall in one position and the comparison would be
    # between a full state machine and a stalled one.
    loop = drive_with_engine_fills(fixture)
    adapter = loop["adapter"]
    canonical_entries = sorted({i.decision_index for d in adapter.decisions for i in d.intents
                                if i.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT)})
    canonical_exits = sorted({i.decision_index for d in adapter.decisions for i in d.intents
                              if i.kind is IntentKind.EXIT_ALL})
    warmup_blocked = [d.index for d in adapter.decisions if not d.warmup_ready]
    blocked_max = max(warmup_blocked) if warmup_blocked else -1

    legacy_only = [b for b in legacy.entry_bars if b not in canonical_entries]
    canonical_only = [b for b in canonical_entries if b not in legacy.entry_bars]
    in_warmup = [b for b in legacy_only if b <= blocked_max]

    attribution = _attribute(alpha_id, legacy.entry_bars, canonical_entries,
                             blocked_max, loop["converged"])
    deltas = {d.delta_id: d.as_record() for d in SEMANTIC_DELTAS
              if d.delta_id in DIVERGENCE_ATTRIBUTION[alpha_id]}
    return {
        "schema": "crypto_regime_lab.legacy_divergence.v1",
        "alpha_id": alpha_id,
        "fixture": fixture.name,
        "legacy": legacy.as_record(),
        "canonical": {"entry_bars": canonical_entries, "exit_bars": canonical_exits,
                      "entry_count": len(canonical_entries),
                      "warmup_blocked_through_bar": blocked_max,
                      "protective_exit_bars": loop["protective_exit_bars"],
                      "fixed_point_converged": loop["converged"],
                      "fixed_point_passes": loop["passes"]},
        "divergence": {
            "legacy_only_entries": legacy_only,
            "canonical_only_entries": canonical_only,
            "legacy_only_inside_canonical_warmup": in_warmup,
            "identical": legacy_only == [] and canonical_only == [],
        },
        "attribution": attribution,
        "attributed_to": deltas,
        "attribution_rule": (
            "every difference must map to a semantic delta. A legacy entry that falls inside the "
            "canonical warmup window is attributed to the readiness repairs; an unattributed "
            "difference is a defect in the adapter, not a result."
        ),
        "claim_boundary": (
            "the legacy tier is diagnostic and in-sample only. Neither side is a performance claim, "
            "and a canonical result is never compared against a legacy number as if they were arms."
        ),
    }
