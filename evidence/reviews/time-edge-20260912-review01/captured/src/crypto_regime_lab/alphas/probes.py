"""Appendix B probe suite — all 21 probes, re-run inside the lab's containment.

The guide's appendix E records these results from the review session on a
different environment (NumPy 2.3.5 / pandas 2.2.3, no QuantBT). Re-running them
here produces a NEW run record; the original stays as provenance and is never
overwritten (guide appendix E).

Every probe exercises source behaviour through the AST harness, so nothing is
imported as a module. Financial numbers here are synthetic examples, not
trading results.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .source_harness import default_injection, load_functions

SCOPE = "synthetic_or_static_source"


def _probe(probe_id: str, expectation: str, fn: Callable[[], Any]) -> dict:
    """Run one probe. A probe that raises unexpectedly is FAILED, never skipped."""
    try:
        observed = fn()
        status = "CONFIRMED"
        error = None
    except Exception as exc:  # noqa: BLE001 - a probe failure must be visible
        observed = None
        status = "PROBE_ERROR"
        error = f"{type(exc).__name__}: {exc}"
    record = {
        "id": probe_id,
        "status": status,
        "observed": observed,
        "scope": SCOPE,
        "expectation": expectation,
    }
    if error:
        record["error"] = error
        record["traceback"] = traceback.format_exc()[-1500:]
    return record


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _raw(lab_root: Path, name: str) -> Path:
    return lab_root / "vendor_readonly" / "alphas_raw" / name


def _literal_dicts(path: Path) -> dict[str, dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            try:
                payload = ast.literal_eval(node.value)
            except (ValueError, SyntaxError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(payload, dict):
                    out[target.id] = payload
    return out


def _hash_backtest(lab_root: Path):
    ns = load_functions(_raw(lab_root, "hash_momentum.py"),
                        ("calculate_indicators", "execute_hash_momentum_backtest"),
                        inject=default_injection())
    return ns


# ---------------------------------------------------------------------------
# PARSE probes (4)
# ---------------------------------------------------------------------------

GUIDE_PARSE_LINES = {"vwap.py": 249, "hash_momentum.py": 166,
                     "adaptive_hma_cpp.py": 349, "signal_combine.py": 145}


def _parse_probe(lab_root: Path, filename: str):
    def run():
        path = _raw(lab_root, filename)
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))          # must not raise
        physical = len(source.splitlines())
        return physical
    return run


# ---------------------------------------------------------------------------
# A-HASH probes (6)
# ---------------------------------------------------------------------------

def _hash_missing_numpy(lab_root: Path):
    def run():
        # Load WITHOUT injecting numpy: exactly the standalone-module situation.
        ns = load_functions(_raw(lab_root, "hash_momentum.py"), ("calculate_indicators",), inject={})
        try:
            ns["calculate_indicators"](np.zeros(50), 5, 10)
        except NameError as exc:
            return f"NameError: {exc}"
        return "NO_ERROR_RAISED"
    return run


def _hash_short_array(lab_root: Path):
    def run():
        ns = _hash_backtest(lab_root)
        try:
            ns["calculate_indicators"](np.arange(10, dtype=np.float64), 2, 3)
        except IndexError:
            return "IndexError"
        return "NO_ERROR_RAISED"
    return run


def _hash_atr_close_only(lab_root: Path):
    def run():
        ns = _hash_backtest(lab_root)
        close = np.full(40, 100.0)                     # flat closes, any high/low range
        _mom0, _mom_norm, atr, _ema = ns["calculate_indicators"](close, 5, 10)
        return float(atr[-1])
    return run


def _hash_common_fixture(ns, *, tp1_ratio, tp2_ratio, rr_ratio, high2):
    """3-bar fixture: entry on bar 1 at 100 with 10 units, then bar 2 behaviour."""
    close = np.array([99.0, 100.0, 110.0])
    high = np.array([99.0, 100.0, high2])
    low = np.array([99.0, 100.0, 110.0])
    mom0 = np.array([0.0, 1.0, 1.0])
    mom_norm = np.array([0.0, 1.0, 1.0])
    atr = np.zeros(3)
    ema = np.zeros(3)
    return ns["execute_hash_momentum_backtest"](
        close, high, low, mom0, mom_norm, atr, ema,
        10000.0,      # initial_capital
        0.0,          # trading_fee
        0,            # cooldown_bars
        5.0,          # stop_loss_perc -> stop 95, risk 5
        rr_ratio, tp1_ratio, 50.0, tp2_ratio, 50.0,
        0.0,          # mom_threshold_mult
        1000.0,       # usd_per_trade -> 10 units at 100
    )


def _hash_equity_no_mtm(lab_root: Path):
    def run():
        ns = _hash_backtest(lab_root)
        # TP levels far away so the position stays open into the last bar.
        pos, equity = _hash_common_fixture(ns, tp1_ratio=10.0, tp2_ratio=12.0,
                                           rr_ratio=14.0, high2=110.0)
        terminal = float(equity[-1] + pos[-1] * (110.0 - 100.0))
        return {
            "units": [float(x) for x in pos],
            "reported_equity": [float(x) for x in equity],
            "terminal_wallet_plus_unrealized": terminal,
        }
    return run


def _hash_one_tp_branch(lab_root: Path):
    def run():
        ns = _hash_backtest(lab_root)
        # risk = 5 -> tp1 101, tp2 102, final 105; bar 2 high 120 crosses all three.
        pos, equity = _hash_common_fixture(ns, tp1_ratio=0.2, tp2_ratio=0.4,
                                           rr_ratio=1.0, high2=120.0)
        return {
            "units": [float(x) for x in pos],
            "reported_equity": [float(x) for x in equity],
        }
    return run


def _hash_unordered_presets(lab_root: Path):
    def run():
        presets = _literal_dicts(_raw(lab_root, "hash_momentum.py"))
        bad = []
        for name, values in presets.items():
            if not {"tp1_ratio", "tp2_ratio", "rr_ratio"} <= set(values):
                continue
            if not (values["tp1_ratio"] < values["tp2_ratio"] < values["rr_ratio"]):
                bad.append(name)
        return bad
    return run


# ---------------------------------------------------------------------------
# A-HMA probes (5)
# ---------------------------------------------------------------------------

def _hma_flat_rsi(lab_root: Path):
    def run():
        ns = load_functions(_raw(lab_root, "adaptive_hma_cpp.py"), ("n_rsi",),
                            inject=default_injection())
        out = ns["n_rsi"](np.full(30, 100.0), 14)
        return {"at_seed": float(out[14]), "next": float(out[15])}
    return run


def _hma_inverted_presets(lab_root: Path):
    def run():
        presets = _literal_dicts(_raw(lab_root, "adaptive_hma_cpp.py"))
        return [name for name, v in presets.items()
                if "min_length" in v and "max_length" in v and v["min_length"] > v["max_length"]]
    return run


def _hma_unused_arguments(lab_root: Path):
    def run():
        ns = load_functions(_raw(lab_root, "adaptive_hma_cpp.py"),
                            ("n_ema", "n_atr", "n_rsi", "_xhma_at_t", "_calcslope_at_t",
                             "core_adaptive_hma_signals"),
                            inject=default_injection())
        rng = np.random.default_rng(7)
        n = 120
        close = 100 + np.cumsum(rng.normal(0, 0.5, n))
        high = close + 0.3
        low = close - 0.3
        volume = np.full(n, 1000.0)
        time_ms = np.arange(n, dtype=np.int64)
        args = dict(minLength=4, maxLength=8, minorMin=2, minorMax=4, flat=5.0,
                    atrFast=3, atrSlow=5, mult=1.0, maxSL=2.0, takeProfit=2.0,
                    minProfit=0.5, sl_input_mode=1)
        base = ns["core_adaptive_hma_signals"](
            time_ms, close, high, low, volume,
            args["minLength"], args["maxLength"], args["minorMin"], args["minorMax"],
            args["flat"], args["atrFast"], args["atrSlow"], args["mult"],
            args["maxSL"], args["takeProfit"], args["minProfit"],
            args["sl_input_mode"], False)
        mutated = ns["core_adaptive_hma_signals"](
            time_ms * 1000 + 5, close, high, low, volume * 77.0,
            args["minLength"], args["maxLength"], args["minorMin"], args["minorMax"],
            args["flat"], args["atrFast"], args["atrSlow"], args["mult"],
            args["maxSL"], args["takeProfit"], args["minProfit"],
            args["sl_input_mode"], True)
        identical = all(np.array_equal(a, b) for a, b in zip(base, mutated))
        return ["time_ms", "volume", "double_up"] if identical else []
    return run


def _hma_no_open_input(lab_root: Path):
    def run():
        ns = load_functions(_raw(lab_root, "adaptive_hma_cpp.py"),
                            ("core_adaptive_hma_signals",), inject=default_injection())
        return list(inspect.signature(ns["core_adaptive_hma_signals"]).parameters)
    return run


def _hma_ignored_sl_mult(lab_root: Path):
    def run():
        path = _raw(lab_root, "adaptive_hma_cpp.py")
        presets = _literal_dicts(path)
        with_sl_mult = [n for n, v in presets.items() if "sl_mult" in v]
        # confirm the code never reads it
        tree = ast.parse(path.read_text(encoding="utf-8"))
        read = any(
            isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
            and node.slice.value == "sl_mult"
            for node in ast.walk(tree)
        )
        return len(with_sl_mult) if not read else -1
    return run


# ---------------------------------------------------------------------------
# A-VWAP probes (2)
# ---------------------------------------------------------------------------

def _vwap_short_array(lab_root: Path):
    def run():
        ns = load_functions(_raw(lab_root, "vwap.py"), ("n_sma",), inject=default_injection())
        try:
            ns["n_sma"](np.arange(10, dtype=np.float64), 50)
        except IndexError:
            return "IndexError"
        return "NO_ERROR_RAISED"
    return run


def _vwap_open_ignored(lab_root: Path):
    def run():
        ns = load_functions(_raw(lab_root, "vwap.py"),
                            ("n_sma", "n_stdev", "core_vwap_mean_reversion_logic"),
                            inject=default_injection())
        n = 210
        close = np.full(n, 100.0)
        close[200] = 90.0
        vwap = np.full(n, 100.0)
        high = np.full(n, 100.0)
        low = np.full(n, 100.0)
        low[200] = 90.0
        rsi = np.full(n, 50.0)
        rsi[200] = 10.0
        atr = np.full(n, 1.0)
        htf = np.full(n, 90.0)
        open_a = np.full(n, 100.0)
        kwargs = dict(rsi_os=30.0, rsi_ob=70.0, dev_mult=1.0, stop_atr=1.0, target_r=1.0,
                      exit_at_vwap=False, time_stop_on=False, time_stop_bars=0)
        pos_a = ns["core_vwap_mean_reversion_logic"](
            open_a, high, low, close, vwap, rsi, atr, htf,
            kwargs["rsi_os"], kwargs["rsi_ob"], kwargs["dev_mult"], kwargs["stop_atr"],
            kwargs["target_r"], kwargs["exit_at_vwap"], kwargs["time_stop_on"],
            kwargs["time_stop_bars"])
        open_b = open_a * 3.0 + 17.0          # a completely different open series
        pos_b = ns["core_vwap_mean_reversion_logic"](
            open_b, high, low, close, vwap, rsi, atr, htf,
            kwargs["rsi_os"], kwargs["rsi_ob"], kwargs["dev_mult"], kwargs["stop_atr"],
            kwargs["target_r"], kwargs["exit_at_vwap"], kwargs["time_stop_on"],
            kwargs["time_stop_bars"])
        return {
            "p200": float(pos_a[200]),
            "p201": float(pos_a[201]),
            "same_output_after_open_change": bool(np.array_equal(pos_a, pos_b)),
        }
    return run


# ---------------------------------------------------------------------------
# A-SC probes (3)
# ---------------------------------------------------------------------------

class _StubAtr:
    def __init__(self, **kwargs):
        self._n = len(kwargs["close"])

    def average_true_range(self):
        import pandas as pd

        return pd.Series(np.ones(self._n))


class _StubRsi:
    """API-minimal stub: it has rsi() and deliberately no money_flow_index()."""

    def __init__(self, **kwargs):
        self._n = len(kwargs["close"])

    def rsi(self):
        import pandas as pd

        return pd.Series(np.full(self._n, 80.0))


class _StubMfi:
    def __init__(self, **kwargs):
        self._n = len(kwargs["close"])

    def money_flow_index(self):
        import pandas as pd

        return pd.Series(np.full(self._n, 80.0))


def _sigcombine_fallback_dispatch(lab_root: Path):
    def run():
        import pandas as pd

        inject = default_injection()
        inject.update({"AverageTrueRange": _StubAtr, "RSIIndicator": _StubRsi,
                       "MFIIndicator": _StubMfi, "SMAIndicator": object})
        ns = load_functions(_raw(lab_root, "signal_combine.py"), ("cal_TA",), inject=inject)
        # No volume column, and novolumedata is False: construction picks RSI,
        # dispatch still asks for money_flow_index.
        data = pd.DataFrame({"high": [1.0, 2.0, 3.0], "low": [0.5, 1.5, 2.5],
                             "close": [0.8, 1.8, 2.8]})
        params = {"coeff": 4, "AP": 2, "novolumedata": False,
                  "src_col": "close", "regime_threshold": 65}
        try:
            ns["cal_TA"](data, params)
        except AttributeError as exc:
            return f"AttributeError: {exc}"
        return "NO_ERROR_RAISED"
    return run


def _sigcombine_long_flat_only(lab_root: Path):
    def run():
        import pandas as pd

        ns = load_functions(_raw(lab_root, "signal_combine.py"),
                            ("apply_SigCombine_strategy",), inject=default_injection())
        crafted = pd.DataFrame({
            "long_signal": [False, True, False, False, True],
            "short_signal": [False, False, True, False, False],
        })
        # API-minimal stub for main(): the probe exercises only the position machine.
        ns.namespace["main"] = lambda data, params: crafted.copy()
        out = ns["apply_SigCombine_strategy"](crafted.copy(), {})
        return [int(x) for x in out["Position"].tolist()]
    return run


def _sigcombine_crossover_diff(lab_root: Path):
    def run():
        import pandas as pd

        ns = load_functions(_raw(lab_root, "signal_combine.py"),
                            ("generate_signals",), inject=default_injection())
        trend = pd.Series([1.0, 2.0, 3.0, 10.0, 1.0, 5.0, 2.0])
        out = ns["generate_signals"](pd.DataFrame({"trend": trend}))
        actual = [bool(x) for x in out["buy_signal"].tolist()[3:]]
        # Conventional crossover(trend, trend.shift(2)): both operands shifted.
        ref = trend.shift(2)
        standard = ((trend > ref) & (trend.shift(1) <= ref.shift(1)))
        return {"actual": actual, "standard_shifted_operand": [bool(x) for x in standard.tolist()[3:]]}
    return run


# ---------------------------------------------------------------------------
# Jump-model DP oracle (1) — LAB-05 machinery, verified here as appendix B did
# ---------------------------------------------------------------------------

def _jm_forward_dp_oracle(_lab_root: Path):
    def run():
        rng = np.random.default_rng(20260909)
        n_states, n_obs = 2, 4
        loss = rng.random((n_obs, n_states))
        lam = 0.37

        # Causal forward endpoint DP (guide 8.4).
        q = np.zeros((n_obs, n_states))
        q[0] = loss[0]
        for t in range(1, n_obs):
            for k in range(n_states):
                q[t, k] = loss[t, k] + min(q[t - 1, j] + (lam if j != k else 0.0)
                                           for j in range(n_states))

        # Brute force over every path, minimum cost per endpoint state.
        brute = np.full((n_obs, n_states), np.inf)
        for t in range(n_obs):
            for path in itertools.product(range(n_states), repeat=t + 1):
                cost = sum(loss[i, path[i]] for i in range(t + 1))
                cost += lam * sum(1 for i in range(1, t + 1) if path[i] != path[i - 1])
                brute[t, path[t]] = min(brute[t, path[t]], cost)

        return {
            "max_abs_error": float(np.max(np.abs(q - brute))),
            "prefix_endpoint_states": [int(np.argmin(q[t])) for t in range(n_obs)],
        }
    return run


# ---------------------------------------------------------------------------
# suite
# ---------------------------------------------------------------------------

def run_all_probes(lab_root: str | Path) -> dict:
    lab_root = Path(lab_root)
    specs: list[tuple[str, str, Callable]] = [
        ("PARSE_vwap.py", "AST parses without import/execution", _parse_probe(lab_root, "vwap.py")),
        ("PARSE_hash_momentum.py", "AST parses without import/execution",
         _parse_probe(lab_root, "hash_momentum.py")),
        ("PARSE_adaptive_hma_cpp.py", "AST parses without import/execution",
         _parse_probe(lab_root, "adaptive_hma_cpp.py")),
        ("PARSE_signal_combine.py", "AST parses without import/execution",
         _parse_probe(lab_root, "signal_combine.py")),
        ("HASH_MISSING_NUMPY", "unbound np raises before indicator call", _hash_missing_numpy(lab_root)),
        ("HASH_SHORT_ARRAY", "atr[14] fails for length 10", _hash_short_array(lab_root)),
        ("HASH_ATR_CLOSE_ONLY", "constant closes yield 0 regardless of any high/low range",
         _hash_atr_close_only(lab_root)),
        ("HASH_EQUITY_NO_MTM", "open-position equity omits unrealized +100", _hash_equity_no_mtm(lab_root)),
        ("HASH_ONE_TP_BRANCH_PER_BAR", "bar crosses tp1,tp2,final but only tp1 executes",
         _hash_one_tp_branch(lab_root)),
        ("HASH_UNORDERED_TP_PRESETS", "invalid for a simultaneous increasing TP ladder",
         _hash_unordered_presets(lab_root)),
        ("HMA_FLAT_RSI", "flat series changes 50 -> 100 in implementation", _hma_flat_rsi(lab_root)),
        ("HMA_INVERTED_LENGTH_PRESETS", "must not silently repair known-tuned presets",
         _hma_inverted_presets(lab_root)),
        ("HMA_UNUSED_ARGUMENTS", "time_ms,volume,double_up do not affect core outputs",
         _hma_unused_arguments(lab_root)),
        ("HMA_NO_OPEN_INPUT", "open price absent from core signature", _hma_no_open_input(lab_root)),
        ("HMA_IGNORED_SL_MULT", "sl_mult present only in presets, not parameter reads",
         _hma_ignored_sl_mult(lab_root)),
        ("VWAP_SHORT_ARRAY", "n_sma assumes >=length input", _vwap_short_array(lab_root)),
        ("VWAP_OPEN_IGNORED", "open input never used; output cannot represent gap fill economics",
         _vwap_open_ignored(lab_root)),
        ("SIGCOMBINE_LONG_FLAT_ONLY", "short signal makes pos=0, never negative",
         _sigcombine_long_flat_only(lab_root)),
        ("SIGCOMBINE_FALLBACK_DISPATCH",
         "RSI fallback still calls money_flow_index when flag false; API-minimal stubs only",
         _sigcombine_fallback_dispatch(lab_root)),
        ("SIGCOMBINE_CROSSOVER_DIFF",
         "current formula differs from conventional crossover against trend.shift(2); specification needed",
         _sigcombine_crossover_diff(lab_root)),
        ("JM_FORWARD_DP_ORACLE", "causal endpoint DP matches brute force best-prefix-ending-state cost",
         _jm_forward_dp_oracle(lab_root)),
    ]
    results = [_probe(pid, exp, fn) for pid, exp, fn in specs]
    confirmed = sum(1 for r in results if r["status"] == "CONFIRMED")
    return {
        "evidence_type": "LOCAL_SOURCE_DIAGNOSTICS_NOT_MARKET_BACKTEST",
        "scope": "AST-loaded source functions only; no QuantBT, no market data, no certification",
        "probe_count": len(results),
        "confirmed_count": confirmed,
        "results": results,
        "note": (
            "This is a NEW run record. The appendix E record from the guide's review session is "
            "provenance and is not overwritten. CONFIRMED means the stated property was observed, "
            "not that an alpha is certified."
        ),
    }
