"""RA-03 test matrix M01-M08 (RA-GUIDE-1.0 section 7).

M01/M02/M03 use a counting fake engine (same harness shape as
``test_te02_scorer_window.py``) so the assertion is about WHEN
``prepare_native_event_strategy`` is called, not about the real engine's
native cost. M04-M08 run the real installed engine on a small synthetic
fixture (matching RA-02's own "phase-owned experiment" scale) because the
claims (financial-output equivalence, a real fill count, a real engine call
count) are not provable against a mock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_regime_lab.time_edge import execution
from crypto_regime_lab.time_edge.execution import PreparedAccount
from crypto_regime_lab.time_edge.metrics import account_returns, describe, window_activity
from crypto_regime_lab.ra import retention
from crypto_regime_lab.ra.profiler import profile_one_task, metric_rerun_calls_no_engine
from crypto_regime_lab.ra.route_qualification import (
    PROBE_MARKET, PROBE_PARAMS, qualify_all, synthetic_bars,
)

PHASES_PER_BAR = 10


def bars(n, seed=7):
    index = pd.date_range("2020-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({"open": 100., "high": 101., "low": 99., "close": 100.,
                         "volume": 1.}, index=index)


def selection(cutoff_iso, params=None):
    return [{"selection_id": "s", "params": params or {"AP": 5, "coeff": 2, "novolumedata": False,
             "src_col": "close", "alpha.condition_threshold": 50},
             "cutoff": cutoff_iso, "ready_at": cutoff_iso}]


class FakeResult:
    def __init__(self, n):
        self.equity = np.full(n, 20000.)
        self.positions = np.zeros(n)
        self.fills = []
        self.metadata = {"canonical_trace_row_count": n,
                         "accounting_ledger_v1": pd.DataFrame({"equity_actual": [20000.]})}
        self.diagnostics = pd.DataFrame(); self.margin = pd.DataFrame()
        self.fees = pd.DataFrame(); self.funding = pd.DataFrame()


def counting_harness(monkeypatch):
    calls = []

    class FakeRunner:
        def __init__(self, data):
            self.data = data
            calls.append(("prepare", len(data)))

        def run(self, strategy, *, report_level):
            calls.append(("run", len(self.data)))
            return FakeResult(len(self.data))

    class FakeEndpoint:
        def prepare_native_event_strategy(self, *, data):
            return FakeRunner(data)

        def simulate(self, *, data, strategy):
            calls.append(("simulate", len(data)))
            return FakeResult(len(data))

    monkeypatch.setattr(execution, "endpoint", lambda **kw: FakeEndpoint())
    return calls


# --- M01: no full preparation happens unless the full window is used -------

def test_m01_construct_prepares_nothing(monkeypatch):
    history, window = 2 * 1440, 1440
    frame = bars(history + window)
    calls = counting_harness(monkeypatch)
    PreparedAccount(frame)
    assert calls == [], "PreparedAccount() must not call prepare_native_event_strategy at all"


def test_m01_first_run_prepares_only_the_window_once(monkeypatch):
    history, window = 2 * 1440, 1440
    frame = bars(history + window)
    start = frame.index[history]
    calls = counting_harness(monkeypatch)
    account = PreparedAccount(frame)
    account.run("A-SC", selection(start.isoformat()), account_start=start)
    assert calls == [("prepare", window), ("run", window)]
    account.run("A-SC", selection(start.isoformat()), account_start=start)
    assert calls == [("prepare", window), ("run", window), ("run", window)], (
        "a second run at the same account_start must be a cache HIT on the window: "
        "no second prepare call")


# --- M02: absolute/relative bars, ready/activation, boundary parity --------

def test_m02_none_and_explicit_bar_zero_share_one_window_and_agree_exactly():
    frame = bars(2880)
    account = PreparedAccount(frame)
    via_none = account.run("A-SC", selection(frame.index[0].isoformat()), account_start=None)
    via_bar0 = account.run("A-SC", selection(frame.index[0].isoformat()), account_start=frame.index[0])
    assert len(account._windows) == 1, "account_start=None and account_start=frame.index[0] are the SAME window"
    assert np.array_equal(via_none["equity"], via_bar0["equity"])
    assert via_none["fills"] == via_bar0["fills"]
    assert via_none["status"] == via_bar0["status"] == "EVALUATED"


def test_m02_absolute_fill_bar_matches_engine_offset(monkeypatch):
    # From the existing TE-02 regression: engine callback bars are relative
    # to the window; absolute_bar_index must restore the frame-relative
    # coordinate. Verified here against the NOW-lazy PreparedAccount so the
    # RA03.1 refactor did not silently change this contract.
    frame = bars(60)
    start = frame.index[30]
    strategy = execution.ClockedStrategy("A-SC", frame, selection(frame.index[-1].isoformat()),
                                         account_start=start, engine_offset=30)
    from tests.time_edge_validation_v4.test_te02_scorer_window import context
    strategy.on_bar_close(context(frame, 0))
    assert strategy.version_runs[0]["start_bar"] == 30


# --- M03: prepared/cold inputs never cross-contaminate state ---------------

def test_m03_two_candidates_at_the_same_window_do_not_share_strategy_state():
    frame = synthetic_bars(2880, seed=1, sigma=0.25)
    start = frame.index[1440]
    account = PreparedAccount(frame)
    params_a = {"AP": 10, "coeff": 2, "novolumedata": False, "src_col": "close",
               "alpha.condition_threshold": 40}
    params_b = {"AP": 40, "coeff": 6, "novolumedata": False, "src_col": "close",
               "alpha.condition_threshold": 70}
    run_a = account.run("A-SC", selection(start.isoformat(), params_a), account_start=start)
    run_b = account.run("A-SC", selection(start.isoformat(), params_b), account_start=start)
    assert len(account._windows) == 1, "both candidates share the one packed window"
    # Different params over the same window: candidate B's funnel/version_runs
    # must not carry candidate A's events (a fresh ClockedStrategy per .run()).
    assert run_a["funnel"] is not run_b["funnel"]
    a_versions = {v["version"] for v in run_a["version_runs"]}
    b_versions = {v["version"] for v in run_b["version_runs"]}
    assert a_versions == {"s"} and b_versions == {"s"}  # each only knows its own selection
    assert not np.array_equal(run_a["equity"], run_b["equity"]) or run_a["engine_fill_count"] == 0, (
        "different params on real volatile data should not coincidentally produce "
        "identical equity paths unless truly nothing traded")


def test_m03_warm_and_cold_share_the_window_cache_without_corrupting_it():
    frame = synthetic_bars(2880, seed=1, sigma=0.25)
    start = frame.index[1440]
    account = PreparedAccount(frame)
    params = PROBE_PARAMS["A-SC"]
    warm1 = account.run("A-SC", selection(start.isoformat(), params), account_start=start)
    cold = account.run("A-SC", selection(start.isoformat(), params), account_start=start, cold=True)
    warm2 = account.run("A-SC", selection(start.isoformat(), params), account_start=start)
    assert len(account._windows) == 1, "cold=True must not create or disturb the cached warm window"
    assert np.array_equal(warm1["equity"], warm2["equity"]), "the warm window is unaffected by an interleaved cold run"
    assert np.allclose(warm1["equity"], cold["equity"], atol=1e-8), "warm and cold must agree on the same params/window"


# --- M04: scalar/compact/audit tiers keep financial outputs equivalent -----

def _real_run():
    m = PROBE_MARKET["A-SC"]
    frame = synthetic_bars((m["history_days"] + m["window_days"]) * 1440, seed=m["seed"], sigma=m["sigma"])
    start = frame.index[m["history_days"] * 1440]
    account = PreparedAccount(frame)
    return account.run("A-SC", selection(start.isoformat(), PROBE_PARAMS["A-SC"]),
                       account_start=start), start, frame


def test_m04_tiers_agree_on_every_overlapping_field():
    run, start, frame = _real_run()
    scalar = retention.to_trial_scalar(run)
    audit = retention.to_selected_audit(run)
    assert scalar["status"] == audit["status"] == run["status"] == "EVALUATED"
    assert scalar["engine_fill_count"] == audit["engine_fill_count"] == run["engine_fill_count"] > 0
    assert scalar["terminal_equity"] == audit["terminal_equity"] == run["terminal_equity"]
    lo, hi = start.ceil("D"), (start + pd.Timedelta(days=8)).floor("D")
    rows = account_returns(run["equity"], run["index"], initial_equity=20000., start=lo, end=hi)
    compact = retention.to_candidate_compact(
        run, daily_returns=rows, metrics=describe(rows), daily_activity=[],
        complete_day_start=lo.isoformat(), complete_day_end_exclusive=hi.isoformat())
    assert compact["status"] == run["status"]
    assert compact["fill_count"] == len(run["fills"]) == audit["engine_fill_count"] or run["engine_fill_count"] == 0
    sizes = retention.tier_sizes(run)
    assert sizes["SELECTED_AUDIT_bytes"] >= sizes["TRIAL_SCALAR_bytes"], (
        "the audit tier must never be smaller than the scalar tier it is a superset of")


# --- M05: compact reconstructable from audit; first return/fee not lost ----

def test_m05_compact_is_a_declared_function_of_the_audit_trace():
    run, start, frame = _real_run()
    audit = retention.to_selected_audit(run)
    lo, hi = start.ceil("D"), (start + pd.Timedelta(days=8)).floor("D")
    derived = retention.candidate_compact_from_audit(
        audit, account_returns=account_returns, describe=describe,
        window_activity=window_activity, start=lo, end=hi)
    direct_rows = account_returns(run["equity"], run["index"], initial_equity=20000., start=lo, end=hi)
    assert derived["daily_returns"] == direct_rows, "compact-from-audit must equal the same reducer called directly"
    assert len(derived["daily_returns"]) > 0, "first return must not be lost"
    first_date, first_value = derived["daily_returns"][0]
    assert first_value is not None
    if run["fills"]:
        assert derived["fill_count"] == len(run["fills"]), "fee-bearing fills must not be lost in the compact form"


# --- M06: repeated runs stay bounded; artifacts recoverable -----------------

def test_m06_repeated_runs_do_not_grow_retained_memory_unboundedly():
    m = PROBE_MARKET["A-SC"]

    def build():
        return synthetic_bars((m["history_days"] + m["window_days"]) * 1440, seed=m["seed"], sigma=m["sigma"])

    profile = profile_one_task(build, "A-SC", PROBE_PARAMS["A-SC"], m["history_days"] * 1440, repeat=6)
    assert profile["windows_cached_total"] == 1, "6 repeats at the same account_start must share one window"
    slope = profile["retained_rss_growth_gib_per_extra_repeat"]
    assert slope is not None
    # Generous bound (20 MiB/repeat): real measured slope on this fixture is
    # ~1.4 MiB/repeat. A bound this loose still catches a genuine leak (e.g.
    # a per-run object retained in a growing list) while not being flaky on
    # ordinary Python/pandas allocator noise.
    assert slope < 20 / 1024, f"retained RSS grew {slope*1024:.1f} MiB per extra repeat -- investigate a leak"
    assert profile["peak_rss_gib_max"] <= profile["target_peak_rss_gib"], "under the pre-registered headroom target"
    # Recoverability of completed artifacts under a mid-run kill is C05's
    # claim (compute cache atomic publish) -- not re-proven here, cited:
    # tests/ra_corrective/test_ra02_cache_cases.py::test_c05_partial_or_corrupt_publication_is_never_a_hit


# --- M07: the one real route handles gap/stop/TP/sizing per alpha ----------

def test_m07_every_alpha_route_is_qualified_with_a_real_measured_run():
    matrix = qualify_all()
    for row in matrix["rows"]:
        assert row["status"] == "OK", f"{row['alpha_id']} route FAILED: {row.get('reason')}"
    assert matrix["primary_pilot_qualified"] is True
    assert set(matrix["qualified_alphas"]) == {"A-SC", "A-HMA", "A-VWAP", "A-HASH"}
    # Do not overclaim: a route with engine_fill_count==0 only proves it
    # didn't crash. Assert the exit-path claim ONLY for alphas that actually
    # produced fills in this probe.
    for row in matrix["rows"]:
        if row["fills"]:
            assert row["exit_tags"], f"{row['alpha_id']} had fills but no exit tag was recorded"


def test_m07_backend_policy_forbids_a_silent_native_fallback():
    import inspect

    source = inspect.getsource(execution.endpoint)
    assert 'backend_policy="certified_only"' in source, (
        "the endpoint must refuse an uncertified backend rather than silently "
        "falling back to a different implementation and still calling it 'native'")


# --- M08: one metric/report rerun and a bootstrap dry-run call no engine ---

def test_m08_metric_rerun_touches_no_engine(monkeypatch):
    run, start, frame = _real_run()

    def forbidden(**kw):
        raise AssertionError("a metric rerun must never construct a new engine endpoint")

    monkeypatch.setattr(execution, "endpoint", forbidden)
    lo, hi = start.ceil("D"), (start + pd.Timedelta(days=8)).floor("D")
    first = metric_rerun_calls_no_engine(run, account_returns=account_returns, describe=describe,
                                         start=lo, end=hi)
    # Bootstrap dry-run: recompute again from the SAME stored run (simulates
    # a second statistic over the same evaluated candidate).
    second = metric_rerun_calls_no_engine(run, account_returns=account_returns, describe=describe,
                                          start=lo, end=hi)
    assert first["daily_returns"] == second["daily_returns"]
    assert first["engine_calls"] == second["engine_calls"] == 0
