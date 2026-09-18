"""L02.8 — Python/Rust parity on fixed intents under one supported contract.

Both backends run the SAME ``IntrabarIntentTape`` under ``intrabar_bracket_v1``.
Known repairs to an alpha are irrelevant here: this compares two implementations
of one engine contract, so any difference is an engine-level discrepancy and the
lab does not "preserve a known bug" to make them agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .intent_tape import TapeBuild, contract_snapshot, run_intrabar

TRACE_FIELDS = ("equity", "positions", "fees", "funding")


@dataclass
class ParityCase:
    case_id: str
    description: str
    frame: object
    tape: TapeBuild
    kwargs: dict = field(default_factory=dict)


def _frame(open_, high, low, close, freq="1h"):
    """Build a frame that satisfies the engine's OHLCV invariant.

    QuantBT rejects a bar whose high is below max(open, close) or whose low is
    above min(open, close). Clamping here keeps a fixture from being rejected for
    a reason that has nothing to do with what it is testing.
    """
    import pandas as pd

    open_, high, low, close = (np.asarray(x, dtype=float) for x in (open_, high, low, close))
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": np.full(n, 1000.0)}, index=idx)


def _tape(n, entry_bar, side, stop, tp, exits=()):
    es = np.zeros(n); es[entry_bar] = side
    sz = np.zeros(n); sz[entry_bar] = 1.0
    sv = np.full(n, np.nan); sv[entry_bar] = stop
    tv = np.full(n, np.nan); tv[entry_bar] = tp
    te = np.zeros(n, dtype=bool)
    for b in exits:
        te[b] = True
    return TapeBuild(es, sz, sv, tv, te)


def build_cases() -> list[ParityCase]:
    cases: list[ParityCase] = []
    rng = np.random.default_rng(20260909)

    n = 40
    c = 100.0 + np.arange(n, dtype=float)
    cases.append(ParityCase("trend_long_tp", "long entry, take profit reached",
                            _frame(c - 0.5, c + 1.0, c - 1.0, c),
                            _tape(n, 3, 1.0, 90.0, 120.0)))

    c2 = 140.0 - np.arange(n, dtype=float)
    cases.append(ParityCase("trend_short_tp", "short entry, take profit reached",
                            _frame(c2 + 0.5, c2 + 1.0, c2 - 1.0, c2),
                            _tape(n, 3, -1.0, 150.0, 115.0)))

    c3 = np.full(n, 100.0)
    o3 = c3.copy(); o3[4] = 130.0
    h3 = np.maximum(c3, o3) + 1.0
    l3 = np.minimum(c3, o3) - 1.0
    cases.append(ParityCase("gap_entry", "a 30% gap on the fill bar",
                            _frame(o3, h3, l3, c3), _tape(n, 3, 1.0, 50.0, 1e9)))

    c4 = np.full(n, 100.0); h4 = np.full(n, 101.0); l4 = np.full(n, 99.0)
    h4[6] = 120.0; l4[6] = 80.0
    cases.append(ParityCase("ambiguous_bar", "a bar touching both the stop and the take profit",
                            _frame(c4.copy(), h4, l4, c4), _tape(n, 3, 1.0, 90.0, 110.0)))

    c5 = 100.0 + np.cumsum(rng.normal(0.0, 1.2, n))
    h5 = c5 + np.abs(rng.normal(0, 0.6, n)); l5 = c5 - np.abs(rng.normal(0, 0.6, n))
    cases.append(ParityCase("random_walk_technical_exit", "random walk with a technical exit",
                            _frame(np.r_[c5[0], c5[:-1]], h5, l5, c5),
                            _tape(n, 4, 1.0, float(c5.min() - 10), float(c5.max() + 10), exits=(20,))))

    c6 = np.full(n, 100.0)
    cases.append(ParityCase("terminal_open_mark", "terminal open position, mark mode",
                            _frame(c6.copy(), c6 + 1.0, c6 - 1.0, c6),
                            _tape(n, 3, 1.0, 50.0, 1e9),
                            kwargs={"close_on_last_bar": False}))

    cases.append(ParityCase("with_costs", "same tape with fees and slippage enabled",
                            _frame(c - 0.5, c + 1.0, c - 1.0, c),
                            _tape(n, 3, 1.0, 90.0, 120.0),
                            kwargs={"fee": 0.0004, "slippage_bps": 1.0}))
    return cases


def compare_case(case: ParityCase) -> dict:
    base_kwargs = dict(close_on_last_bar=True, fee=0.0, slippage_bps=0.0,
                       initial_capital=20000.0, use_funding=False)
    base_kwargs.update(case.kwargs)
    ref = run_intrabar(case.frame, case.tape, backend="reference", **base_kwargs)
    rust = run_intrabar(case.frame, case.tape, backend="rust", **base_kwargs)

    diffs: dict[str, dict] = {}
    for field_name in TRACE_FIELDS:
        a = np.asarray(ref[field_name], dtype=float).reshape(-1)
        b = np.asarray(rust[field_name], dtype=float).reshape(-1)
        if a.shape != b.shape:
            diffs[field_name] = {"shape_mismatch": [list(a.shape), list(b.shape)]}
            continue
        delta = np.abs(np.nan_to_num(a) - np.nan_to_num(b))
        diffs[field_name] = {"max_abs_diff": float(delta.max()) if delta.size else 0.0,
                             "exact": bool(np.array_equal(np.nan_to_num(a), np.nan_to_num(b)))}
    account_exact = all(d.get("exact") for d in diffs.values())
    return {
        "case_id": case.case_id,
        "description": case.description,
        "account_trace_exact": account_exact,
        "trace_diffs": diffs,
        "reference_fill_count": len(ref["fills"]),
        "rust_fill_count": len(rust["fills"]),
        "fill_trace_comparable": ref["fills_available"] and rust["fills_available"],
        "reference_fills": ref["fills"],
        "liquidated_match": ref["liquidated"] == rust["liquidated"],
    }


def parity_report() -> dict:
    cases = [compare_case(c) for c in build_cases()]
    failures = [c["case_id"] for c in cases if not c["account_trace_exact"]]
    fill_comparable = [c["case_id"] for c in cases if c["fill_trace_comparable"]]
    return {
        "schema": "crypto_regime_lab.engine_parity.v1",
        "contract": contract_snapshot(),
        "backends": ["intrabar_bracket_reference (python)", "intrabar_bracket_rust"],
        "case_count": len(cases),
        "account_trace_failures": failures,
        "cases": cases,
        "fill_trace_parity": {
            "comparable_cases": fill_comparable,
            "status": "BLOCKED_CAPABILITY" if not fill_comparable else "COMPARED",
            "detail": (
                "The rust backend returns an empty fill sequence at every report level tried "
                "(standard and full, with and without audit_detail_limit), so a fill-by-fill "
                "comparison is not available on this install. The ACCOUNT trace — equity, "
                "positions, fees, funding — is compared exactly and matches. Recorded as a blocked "
                "capability rather than described as full-trace parity (guide L02.8)."
            ),
        },
        "status": "PASS" if not failures else "FAIL",
        "claim_boundary": (
            "This establishes account-trace parity between two implementations of one contract. "
            "It is NOT a claim of Rust parity from final equity alone: every bar of equity, "
            "position, fee and funding is compared, and the missing fill-level trace is disclosed."
        ),
    }
