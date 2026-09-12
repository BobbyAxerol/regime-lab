"""Tests for the LAB-02 items found on the second audit.

Numba/fastmath parity, the legacy_reproduction tier and its attributed
divergence, market-input inventory, and ladder quantisation with explicit dust.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from crypto_regime_lab.alphas import catalog as catalog_mod
from crypto_regime_lab.alphas.a_hash import HashMomentumEventAdapterV1
from crypto_regime_lab.alphas.base import MarketSlice
from crypto_regime_lab.alphas.contracts import Fill, IntentKind
from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES


@pytest.fixture(scope="module")
def raw_dir(lab_root):
    return lab_root / "vendor_readonly" / "alphas_raw"


# --- L02.2: Numba / fastmath parity -------------------------------------

@pytest.fixture(scope="module")
def numba_report(raw_dir):
    from crypto_regime_lab.alphas.reference.numba_parity import numba_parity

    return numba_parity(raw_dir)


def test_compiled_kernels_are_compared_not_assumed(numba_report):
    assert numba_report["kernel_count"] >= 14
    assert numba_report["status"] == "PASS"


def test_fastmath_kernels_are_identified_and_do_not_change_decisions(numba_report):
    fastmath = numba_report["fastmath_kernels"]
    assert any("hma." in k for k in fastmath), "adaptive_hma_cpp.py compiles with fastmath=True"
    assert numba_report["decision_failures"] == []
    decision_bearing = [r for r in numba_report["results"] if r["decisions_identical"] is not None]
    assert decision_bearing, "at least one decision-level comparison must exist"
    for r in decision_bearing:
        assert r["decisions_identical"] is True, r["kernel"]


def test_non_fastmath_kernels_are_bit_exact(numba_report):
    for r in numba_report["results"]:
        if not r["fastmath"] and r["kernel"].startswith(("vwap.", "hash.mom0", "hash.atr", "hash.ema")):
            assert r["max_abs_error"] == 0.0, r["kernel"]


def test_harness_can_load_compiled_and_interpreted_forms(raw_dir):
    from crypto_regime_lab.alphas.source_harness import (
        default_injection, load_functions, numba_injection,
    )

    stripped = load_functions(raw_dir / "vwap.py", ("n_sma",), inject=default_injection())
    compiled = load_functions(raw_dir / "vwap.py", ("n_sma",), inject=numba_injection(),
                              keep_decorators=True)
    assert stripped.dropped_decorators, "the interpreted form must drop @njit"
    assert not compiled.dropped_decorators, "the compiled form must keep it"
    assert type(compiled["n_sma"]).__module__.startswith("numba")


# --- guide 2.1: the legacy_reproduction tier ----------------------------

@pytest.fixture(scope="module")
def divergences(raw_dir):
    from crypto_regime_lab.alphas.legacy import divergence_report

    return {a: divergence_report(a, raw_dir) for a in ("A-SC", "A-HMA", "A-VWAP", "A-HASH")}


@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_legacy_tier_runs_the_original_end_to_end(alpha_id, divergences):
    legacy = divergences[alpha_id]["legacy"]
    assert legacy["tier"] == "legacy_reproduction"
    assert legacy["entry_count"] >= 1
    assert legacy["minimal_fixes"], "the minimal fixes must be stated, even when there are none"


@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_legacy_tier_is_never_eligible_for_an_arm(alpha_id, divergences):
    eligibility = divergences[alpha_id]["legacy"]["eligibility"]
    assert eligibility["eligible_for_any_arm"] is False
    assert eligibility["eligible_for_ab_comparison"] is False
    assert eligibility["eligible_for_diagnostics"] is True


def test_only_hash_needs_a_dependency_fix(divergences):
    assert "numpy" in divergences["A-HASH"]["legacy"]["minimal_fixes"][0]
    assert "ta" in divergences["A-SC"]["legacy"]["minimal_fixes"][0]
    for alpha_id in ("A-HMA", "A-VWAP"):
        assert "none" in divergences[alpha_id]["legacy"]["minimal_fixes"][0]


@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_every_legacy_canonical_difference_is_attributed(alpha_id, divergences):
    attribution = divergences[alpha_id]["attribution"]
    assert attribution["explained"] is True, attribution
    assert attribution["kind"] != "UNEXPLAINED"


def test_sc_and_vwap_reproduce_the_legacy_entries_exactly(divergences):
    for alpha_id in ("A-SC", "A-VWAP"):
        assert divergences[alpha_id]["attribution"]["kind"] == "IDENTICAL"
        assert divergences[alpha_id]["divergence"]["identical"] is True


def test_hma_divergence_is_exactly_the_one_bar_weight_offset(divergences):
    attribution = divergences["A-HMA"]["attribution"]
    assert attribution["kind"] == "CONSTANT_OFFSET"
    assert attribution["offset"] == 1
    assert attribution["attributed_delta"] == "SD-HMA-02"


def test_hash_divergence_is_attributed_to_the_recorded_blocker(divergences):
    attribution = divergences["A-HASH"]["attribution"]
    assert attribution["kind"] == "PREFIX_THEN_BLOCKED_DIVERGENCE"
    assert attribution["attributed_blocker"] == "BLOCK-HASH-LADDER"
    assert attribution["common_prefix_entries"] >= 5


def test_canonical_replay_reaches_a_fixed_point_where_it_can(divergences):
    """A-SC/A-HMA/A-VWAP converge; A-HASH cannot, and that is the blocker showing."""
    for alpha_id in ("A-SC", "A-HMA", "A-VWAP"):
        assert divergences[alpha_id]["canonical"]["fixed_point_converged"] is True
    assert divergences["A-HASH"]["canonical"]["fixed_point_converged"] is False


def test_legacy_equity_column_is_flat_while_a_position_is_open():
    """AH-03 reproduced by the diagnostic helper, not just described."""
    n = 40
    close = np.full(n, 100.0)
    market = MarketSlice(close.copy(), close + 1, close - 1, close, np.full(n, 1000.0))
    adapter = HashMomentumEventAdapterV1(
        dict(mom_len=3, ema_len=5, cooldown_bars=1, stop_loss_perc=10.0, rr_ratio=3.0,
             tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
             mom_threshold_mult=0.0), market)
    adapter.prepare()
    fills = [Fill(index=5, side=1, quantity=10.0, price=100.0, intent_kind=IntentKind.ENTER_LONG),
             Fill(index=15, side=-1, quantity=-10.0, price=110.0, intent_kind=IntentKind.EXIT_ALL)]
    equity = adapter.legacy_realized_equity(fills, 10000.0)
    assert equity[5] == 10000.0 and equity[14] == 10000.0, "flat while the position is open"
    assert equity[15] == pytest.approx(10100.0), "realises only at the closing fill"


# --- L02.1: market input inventory --------------------------------------

@pytest.fixture(scope="module")
def inventories(raw_dir):
    return {inv.alpha_id: inv for inv in
            (catalog_mod.inventory_file(raw_dir / f, d) for f, d in ALLOWED_ALPHA_FILES.items())}


def test_market_columns_are_inventoried_per_alpha(inventories):
    assert sorted(inventories["A-VWAP"].data_inputs) == ["close", "high", "low", "open", "volume"]
    assert sorted(inventories["A-HASH"].data_inputs) == ["close", "high", "low"]
    assert "volume" in inventories["A-SC"].data_inputs
    assert "volume" in inventories["A-HMA"].data_inputs


def test_datetime_index_requirement_is_detected(inventories):
    assert inventories["A-VWAP"].index_uses, "A-VWAP resamples and needs a DatetimeIndex"
    assert inventories["A-HASH"].index_uses == [], "A-HASH never touches the index"
    assert inventories["A-SC"].index_uses


def test_registry_publishes_the_data_requirements(lab_root):
    path = lab_root / "configs" / "alpha_registry.json"
    if not path.is_file():
        pytest.skip("run scripts/catalog_alphas.py")
    registry = json.loads(path.read_text())["alphas"]
    assert registry["A-VWAP"]["requires_datetime_index"] is True
    assert registry["A-HASH"]["requires_datetime_index"] is False
    assert set(registry["A-VWAP"]["required_market_columns"]) == {
        "open", "high", "low", "close", "volume"}


# --- T12 completion: lot rounding and dust ------------------------------

def _hash_adapter(**extra):
    n = 40
    close = np.full(n, 100.0)
    market = MarketSlice(close.copy(), close + 1, close - 1, close, np.full(n, 1000.0))
    params = dict(mom_len=3, ema_len=5, cooldown_bars=1, stop_loss_perc=10.0, rr_ratio=3.0,
                  tp1_ratio=1.0, tp1_qty_perc=55, tp2_ratio=2.0, tp2_qty_perc=65,
                  mom_threshold_mult=0.0)
    params.update(extra)
    adapter = HashMomentumEventAdapterV1(params, market)
    adapter.prepare()
    return adapter


def test_ladder_quantisation_respects_the_instrument_step():
    adapter = _hash_adapter(qty_step=0.001, min_qty=0.001, min_notional=5.0)
    report = adapter.quantize_ladder(100.0, 1, entry_qty=0.137)
    for rung in report["rungs"]:
        step = report["instrument"]["qty_step"]
        assert abs(rung["quantised_qty"] / step - round(rung["quantised_qty"] / step)) < 1e-6


def test_ladder_never_over_closes_after_quantisation():
    for entry_qty in (0.137, 1.0, 7.77, 0.003):
        adapter = _hash_adapter(qty_step=0.001, min_qty=0.001, min_notional=5.0)
        report = adapter.quantize_ladder(100.0, 1, entry_qty=entry_qty)
        assert report["over_closed"] is False
        assert report["total_closed"] <= entry_qty + 1e-12


def test_dust_is_explicit_when_the_step_is_coarse():
    adapter = _hash_adapter(qty_step=1.0, min_qty=1.0, min_notional=0.0)
    report = adapter.quantize_ladder(100.0, 1, entry_qty=10.0)
    assert report["dust"] >= 0.0
    assert "never rolled into another rung" in report["dust_policy"]
    assert report["partial_quantity_convention"] == "fraction_of_remaining"


def test_a_rung_below_the_minimum_notional_is_rejected_not_resized():
    adapter = _hash_adapter(qty_step=0.001, min_qty=0.001, min_notional=5.0)
    report = adapter.quantize_ladder(100.0, 1, entry_qty=0.137)
    rejected = [r for r in report["rungs"] if r["rejected_below_minimum"]]
    assert rejected, "a rung whose notional is under the minimum must be rejected"
    for rung in rejected:
        assert rung["quantised_qty"] == 0.0, "rejected means zero, never a silently resized order"


def test_fraction_of_remaining_survives_quantisation():
    adapter = _hash_adapter(qty_step=0.0, min_qty=0.0, min_notional=0.0)
    report = adapter.quantize_ladder(100.0, 1, entry_qty=1.0)
    assert report["rungs"][0]["raw_qty"] == pytest.approx(0.55)
    assert report["rungs"][1]["raw_qty"] == pytest.approx(0.45 * 0.65)
    assert report["total_closed"] == pytest.approx(1.0)


# --- certification records carry the new evidence ------------------------

def test_certification_records_the_tiers_and_divergence(lab_root):
    path = lab_root / "configs" / "alpha_certification" / "A-HMA.json"
    if not path.is_file():
        pytest.skip("run scripts/certify_alphas.py")
    doc = json.loads(path.read_text())
    assert doc["version_tiers_built"] == ["raw_supplied", "legacy_reproduction", "canonical_v1"]
    assert doc["legacy_divergence"]["explained"] is True
    assert doc["legacy_divergence"]["attributed_to"] == "SD-HMA-02"


def test_summary_reports_numba_and_divergence(lab_root):
    path = lab_root / "configs" / "lab02_certification_summary.json"
    if not path.is_file():
        pytest.skip("run scripts/certify_alphas.py")
    doc = json.loads(path.read_text())
    assert "numba_fastmath_parity" in doc["suites"]
    assert doc["suites"]["legacy_divergence"] == "all explained"
    assert "0 decision differences" in doc["suites"]["numba_fastmath_parity"]


# --- L02.3: bars-since state must match the source exactly ---------------

def test_bars_since_counters_match_the_raw_source(raw_dir):
    """K1/K2/O1/O2 are load-bearing for long_signal; they must reproduce the source."""
    import pandas as pd

    from crypto_regime_lab.alphas.a_sc import SignalCombineAdapterV1
    from crypto_regime_lab.alphas.golden import golden_sc
    from crypto_regime_lab.alphas.source_harness import default_injection, load_functions

    fixture = golden_sc()
    adapter = SignalCombineAdapterV1(fixture.params, fixture.market)
    adapter.prepare()
    signals = adapter.signals

    ns = load_functions(raw_dir / "signal_combine.py", ("generate_signals",),
                        inject=default_injection())
    source = ns["generate_signals"](pd.DataFrame({"trend": signals.trend}))

    for name, ours in (("K1", signals.k1), ("K2", signals.k2),
                       ("O1", signals.o1), ("O2", signals.o2)):
        theirs = source[name].to_numpy(dtype=float)
        both_nan = np.isnan(ours) & np.isnan(theirs)
        assert np.array_equal(np.nan_to_num(ours, nan=-1.0),
                              np.nan_to_num(theirs, nan=-1.0)), name
        assert both_nan.sum() >= 1, f"{name} must keep the source's NaN prefix"

    assert np.array_equal(signals.buy_signal, source["buy_signal"].to_numpy())
    assert np.array_equal(signals.sell_signal, source["sell_signal"].to_numpy())
    assert np.array_equal(signals.long_signal,
                          source["long_signal"].fillna(False).to_numpy().astype(bool))


# --- L02.8: one corrected alpha version shared by every arm --------------

def test_one_canonical_version_is_shared_by_all_arms(lab_root):
    path = lab_root / "configs" / "alpha_registry.json"
    if not path.is_file():
        pytest.skip("run scripts/catalog_alphas.py")
    registry = json.loads(path.read_text())["alphas"]
    versions = {a: rec["adapter_version"] for a, rec in registry.items()}
    assert set(versions.values()) == {"canonical_v1"}, versions

    from crypto_regime_lab.alphas.findings import SEMANTIC_DELTAS

    arms = {"A", "B", "C", "D", "E"}
    for delta in SEMANTIC_DELTAS:
        if delta.adapter_version == "canonical_v1":
            assert set(delta.applies_to_experiment_arms) == arms, (
                f"{delta.delta_id} is canonical but does not apply to every arm; a canonical "
                f"repair must be identical across A/B/C/D/E"
            )
        else:
            assert delta.applies_to_experiment_arms == [], delta.delta_id
