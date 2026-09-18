#!/usr/bin/env python
"""RF-02 closeout: real-snapshot pilot on 1m execution + native/Rust probe.

1. Reads BTCUSDT 1m partitions from snapshots/server_core_v1 directly (the lab
   never calls the loader at run time), runs the A-SC adapter on 15m bars and
   maps its decisions onto the 1m engine clock with execution_clock (A06).
2. Probes native_prepared_wfo='require' + target_runtime='rust' and records
   requested vs resolved route, error and timing.
Writes evidence/corrective_mode4_v3/RF-02/{real_snapshot_pilot.json,native_qualification.json}.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.alphas.a_sc import SignalCombineAdapterV1  # noqa: E402
from crypto_regime_lab.alphas.base import MarketSlice  # noqa: E402
from crypto_regime_lab.alphas.contracts import IntentKind  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.integration.execution_clock import map_htf_decisions  # noqa: E402
from crypto_regime_lab.quantbt_bridge.routes import bound_fee_kwargs  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS  # noqa: E402
from crypto_regime_lab.selector.installed_wfo import synthetic_frame  # noqa: E402
from crypto_regime_lab.selector.mode4_baseline import AScSignalStrategy  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-02"
PRODUCT = "crypto_binance_futures_1m"
SYMBOL = "BTCUSDT"
PARTITIONS = ("2021-01", "2021-02", "2021-03")


def snapshot_1m(root: Path, start: str, end: str) -> pd.DataFrame:
    frames = []
    for partition in PARTITIONS:
        path = root / PRODUCT / SYMBOL / f"{partition}.parquet"
        if path.is_file():
            frames.append(pd.read_parquet(path, columns=["time", "open", "high", "low", "close",
                                                         "volume"]))
    frame = pd.concat(frames, ignore_index=True)
    frame["time"] = pd.to_datetime(frame["time"]).dt.tz_localize("UTC")
    frame = frame.set_index("time").sort_index()
    return frame.loc[start:end]


def resample_15m(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna()


def adapters_intents(htf: pd.DataFrame, params: dict) -> dict[int, list]:
    market = MarketSlice(open=htf["open"].to_numpy(float), high=htf["high"].to_numpy(float),
                         low=htf["low"].to_numpy(float), close=htf["close"].to_numpy(float),
                         volume=htf["volume"].to_numpy(float), index=htf.index)
    adapter = SignalCombineAdapterV1(dict(params), market, vectorised=True)
    by_bar: dict[int, list] = {}
    for t in range(max(adapter.warmup_bars(), 1), len(htf)):
        decision = adapter.on_bar_close(t)
        for intent in decision.intents:
            if intent.kind in (IntentKind.ENTER_LONG, IntentKind.EXIT_ALL):
                by_bar.setdefault(t, []).append(intent)
    return by_bar


class MappedIntentStrategy:
    """Replays mapped decisions as target changes on the 1m engine clock."""

    def __init__(self, intents_by_exec_bar: dict[int, list], unit_notional: float = 2000.0):
        self.by_bar = intents_by_exec_bar
        self.unit_notional = unit_notional
        self.entries = 0
        self.fills = 0

    def initialize(self, context):
        return []

    def on_bar_close(self, context):
        import quantbt as q

        bar = int(context.bar_index)
        intents = self.by_bar.get(bar)
        if not intents:
            return []
        commands = []
        close = float(np.asarray(context.close, dtype=float).reshape(-1)[-1])
        position = float(context.positions.get("S", 0.0) or 0.0)
        for intent in intents:
            if intent.kind is IntentKind.ENTER_LONG and position == 0.0:
                qty = self.unit_notional / close
                commands.append(q.OrderCommand(
                    timestamp=context.timestamp, action=q.OrderAction.PLACE, symbol="S",
                    side=q.OrderSide.BUY, order_type=q.OrderType.MARKET, qty=qty, tag="entry"))
                self.entries += 1
            elif intent.kind is IntentKind.EXIT_ALL and position != 0.0:
                commands.append(q.OrderCommand(
                    timestamp=context.timestamp, action=q.OrderAction.PLACE, symbol="S",
                    side=q.OrderSide.SELL if position > 0 else q.OrderSide.BUY,
                    order_type=q.OrderType.MARKET, qty=abs(position), reduce_only=True, tag="exit"))
        return commands

    def finalize(self, context):
        return []


def run_real_pilot(root: Path, start: str, end: str) -> dict:
    import quantbt as q

    bars_1m = snapshot_1m(root, start, end)
    htf = resample_15m(bars_1m)
    intents_htf = adapters_intents(htf, dict(SEED_POINTS["A-SC"]))
    mapped = map_htf_decisions(intents_htf, htf.index, bars_1m.index)
    mapped = {bar: value for bar, value in mapped.items() if bar >= 0}
    strategy = MappedIntentStrategy(mapped)
    endpoint = q.QuantBTEndpoint.native_event_strategy(
        account=q.AccountConfig(initial_capital=20000.0), slippage_bps=1.0,
        symbols=["S"], use_funding=False, **bound_fee_kwargs(0.0004))
    started = time.perf_counter()
    result = endpoint.simulate(data=bars_1m.reset_index().set_index("time"), strategy=strategy)
    elapsed = time.perf_counter() - started
    fills = list(getattr(result, "fills", None) or [])
    return {
        "data": {"source": "snapshots/server_core_v1", "product": PRODUCT, "symbol": SYMBOL,
                 "window": f"{start}..{end}", "is_synthetic": False,
                 "partitions": list(PARTITIONS), "bars_1m": int(len(bars_1m)),
                 "bars_15m": int(len(htf))},
        "mapped_intents": len(intents_htf), "mapped_exec_bars": len(mapped),
        "entries_emitted": strategy.entries, "engine_fills": len(fills),
        "equity_last": float(np.asarray(result.equity, dtype=float).reshape(-1)[-1]),
        "wall_seconds": round(elapsed, 3),
        "fee_binding": bound_fee_kwargs(0.0004),
        "resolution": "A-SC decides on 15m bars; orders execute on the 1m engine clock (A06)",
    }


def native_probe() -> dict:
    import optuna
    import quantbt as q

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    frame = synthetic_frame(n=3000, seed=5, freq="4h")
    payload = {"requested": {"target_mode": "signal_notional", "target_runtime": "rust",
                             "native_prepared_wfo": "require", "scoring_backend": "endpoint"},
               "ok": False, "resolved": {}, "error": None}
    started = time.perf_counter()
    try:
        endpoint = q.QuantBTEndpoint.walk_forward(
            strategy_class=AScSignalStrategy, split_mode=2021, split_frequency="single",
            optimization_mode="mode_4_is_only_robust", optimization_schedule="per_fold_causal",
            optuna_trials=2, random_seed=11, target_mode="signal_notional",
            backend="native_vectorized", target_runtime="rust",
            account=q.AccountConfig(initial_capital=20000.0), alloc_per_trade=0.1,
            symbols=["S"], use_funding=False, slippage_bps=1.0, **bound_fee_kwargs(0.0004),
            optimization_config={"candidate_selection_metric": "is_only_robust",
                                 "scoring_backend": "endpoint",
                                 "research_retention": "full_trial_ledger",
                                 "native_prepared_wfo": "require"})
        result = endpoint.backtest(data=frame, param_ranges={"coeff": (1, 8), "AP": (5, 60),
                                                             "alpha.condition_threshold": (30, 80)})
        meta = result.metadata.get("walk_forward") or {}
        payload["ok"] = True
        payload["resolved"] = {k: meta.get(k) for k in (
            "native_prepared_wfo", "scoring_backend", "scoring_trading_days",
            "prepared_scoring_cache")}
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"[:500]
    payload["wall_seconds"] = round(time.perf_counter() - started, 3)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)

    pilot = run_real_pilot(LAB_ROOT / "snapshots" / "server_core_v1",
                           "2021-01-05 00:00", "2021-01-20 00:00")
    native = native_probe()
    for name, payload in (("real_snapshot_pilot.json", pilot),
                          ("native_qualification.json", native)):
        target = writer.run_dir / name
        if target.exists() and not args.force:
            raise SystemExit(f"{target} exists; pass --force to supersede explicitly")
        writer.write_json(name, payload)
    print(json.dumps({"pilot": pilot, "native": native}, indent=2, default=str)[:2600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
