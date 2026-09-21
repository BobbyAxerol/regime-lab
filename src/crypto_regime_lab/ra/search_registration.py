"""RA04.4: search dimensions and budget, frozen before any candidate is scored.

Trial budget: REUSES the existing registration
`configs/time_edge_validation_v4/mode4_binding_r01.json` (`optuna_trials=32`,
`is_subperiods=6`, `search_seed=20260912`) -- the guide allows a documented
32-64 revision in place of the 50/cutoff default, and this study already
froze 32 with its own reason before any RA-04 candidate exists; RA-04 does
not re-freeze a competing number.

Search dimensions: 2-3 "effective" parameters per alpha, chosen from the
canonical schema (`selector/alpha_schemas.py`) by which ones drive the core
entry/exit mechanism, everything else held at a registered fixed point (the
SAME feasible point RA-03's route qualification already validated produces
real fills for every alpha -- reused rather than re-invented, including the
A-HASH ladder-feasibility fix for AH-07). `behavior_witness()` proves each
chosen dimension is not dead: two real small engine runs that differ ONLY in
that one dimension must produce a measurably different result.
"""
from __future__ import annotations

from .route_qualification import PROBE_MARKET, PROBE_PARAMS, synthetic_bars

BUDGET_REGISTRATION_REF = "configs/time_edge_validation_v4/mode4_binding_r01.json"
REUSED_OPTUNA_TRIALS = 32
REUSED_IS_SUBPERIODS = 6
REUSED_SEARCH_SEED = 20260912

# 2-3 effective dimensions per alpha, chosen by core-mechanism relevance; the
# rest of each alpha's schema stays fixed at PROBE_PARAMS (RA-03, reused).
SEARCH_DIMENSIONS = {
    "A-SC": ["AP", "coeff", "alpha.condition_threshold"],    # the alpha's entire tunable schema (3 dims total)
    # `min_length` and `mult` were tried first and measured DEAD (byte-identical
    # terminal_equity across their whole feasible range) on the phase-owned
    # fixture -- the adaptive lookback never binds the floor and `mult` never
    # changes the realized path here. Reported honestly rather than forced;
    # max_length/take_profit/max_sl are the ones with a measured real effect.
    "A-HMA": ["max_length", "take_profit", "max_sl"],
    "A-VWAP": ["dev_mult", "rsi_len", "stop_atr"],            # deviation-band width + oscillator window + stop distance
    "A-HASH": ["mom_len", "mom_threshold_mult", "stop_loss_perc"],  # momentum window/threshold + risk distance
}
# Dimensions probed and found DEAD (no measured effect) on the phase-owned
# fixture, kept for the record rather than silently dropped (RA04.4: "vẫn
# fallback nhiều thì report đúng; không ép... đến khi có medoid").
DEAD_ON_FIXTURE = {
    "A-HMA": ["min_length", "mult"],
}


def registered_search_config() -> dict:
    return {
        "schema": "regime_lab.ra04_search_registration.v1",
        "budget": {"optuna_trials": REUSED_OPTUNA_TRIALS, "is_subperiods": REUSED_IS_SUBPERIODS,
                  "search_seed": REUSED_SEARCH_SEED, "source": BUDGET_REGISTRATION_REF,
                  "reused_not_refrozen": True,
                  "guide_allowance": "32-64 coverage revision documented in place of the 50/cutoff default"},
        "search_dimensions": SEARCH_DIMENSIONS,
        "dead_on_fixture": DEAD_ON_FIXTURE,
        "fixed_defaults": PROBE_PARAMS,
        "fixed_defaults_source": ("src/crypto_regime_lab/ra/route_qualification.py PROBE_PARAMS "
                                  "(RA-03) -- reused, not re-derived; already validated to produce "
                                  "real fills for every alpha, incl. the AH-07 ladder-feasibility fix"),
        "geometry_or_selector_extension": ("out of scope for this study per RA04.4 -- a separate "
                                           "future study, not folded into this factorial"),
    }


def behavior_witness(alpha_id: str, dimension: str, *, low_value, high_value) -> dict:
    """RA04.4: prove `dimension` is not dead by running the SAME real small
    fixture twice, differing ONLY in `dimension`, and checking the result
    actually differs (fills, equity, or a raised/caught infeasibility -- an
    unknown-enum categorical MUST raise per Q03, not silently collapse).
    """
    from ..time_edge.execution import PreparedAccount

    if dimension not in SEARCH_DIMENSIONS.get(alpha_id, ()):
        raise ValueError(f"{dimension!r} is not a registered search dimension for {alpha_id}")
    market = PROBE_MARKET[alpha_id]
    frame = synthetic_bars((market["history_days"] + market["window_days"]) * 1440,
                           seed=market["seed"], sigma=market["sigma"])
    start = frame.index[market["history_days"] * 1440]
    base = dict(PROBE_PARAMS[alpha_id])

    def run_with(value):
        params = dict(base)
        params[dimension] = value
        selection = [{"selection_id": f"witness-{value}", "params": params,
                     "cutoff": start.isoformat(), "ready_at": start.isoformat()}]
        account = PreparedAccount(frame)
        try:
            run = account.run(alpha_id, selection, account_start=start)
            return {"status": "OK", "engine_status": run["status"], "fills": run["engine_fill_count"],
                   "terminal_equity": run["terminal_equity"]}
        except Exception as exc:
            return {"status": "RAISED", "reason": f"{type(exc).__name__}: {exc}"[:300]}

    low = run_with(low_value)
    high = run_with(high_value)
    if low["status"] == "RAISED" or high["status"] == "RAISED":
        differs = low != high
    else:
        differs = (low["fills"] != high["fills"]) or (low["terminal_equity"] != high["terminal_equity"])
    return {"schema": "regime_lab.ra04_behavior_witness.v1", "alpha_id": alpha_id,
           "dimension": dimension, "low_value": low_value, "high_value": high_value,
           "low_result": low, "high_result": high, "behavior_differs": differs}
