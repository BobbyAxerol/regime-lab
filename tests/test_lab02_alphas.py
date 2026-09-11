"""LAB-02 acceptance tests T09-T20 plus adapter, reference and bridge coverage.

No alpha module is imported: source behaviour is reached through the AST harness
(``crypto_regime_lab.alphas.source_harness``), which is how a file that cannot be
imported at all (``hash_momentum.py``) is still tested.
"""

from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.alphas import catalog as catalog_mod
from crypto_regime_lab.alphas.a_hash import (
    AccountConfigInAlpha, HashMomentumEventAdapterV1, LadderInfeasible,
)
from crypto_regime_lab.alphas.a_hma import AdaptiveHmaEventAdapterV1, InfeasibleConfiguration
from crypto_regime_lab.alphas.a_sc import SignalCombineAdapterV1, VolumeUnavailable
from crypto_regime_lab.alphas.a_vwap import (
    EXIT_PRECEDENCE, VwapMeanReversionEventAdapterV1, ema_convergence_bars, htf_ema_available_at,
)
from crypto_regime_lab.alphas.base import MarketSlice
from crypto_regime_lab.alphas.contracts import ExecutionPhase, Fill, IntentKind
from crypto_regime_lab.alphas.reference import indicators as ref
from crypto_regime_lab.alphas.source_harness import default_injection, load_functions
from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES


@pytest.fixture(scope="module")
def raw_dir(lab_root):
    return lab_root / "vendor_readonly" / "alphas_raw"


def _market(close, pad=0.5, open_=None, volume=None, index=None):
    close = np.asarray(close, dtype=float)
    open_ = np.r_[close[0], close[:-1]] if open_ is None else np.asarray(open_, dtype=float)
    high = np.maximum(open_, close) + pad
    low = np.minimum(open_, close) - pad
    volume = np.full(close.size, 1000.0) if volume is None else np.asarray(volume, dtype=float)
    return MarketSlice(open_, high, low, close, volume, index=index)


# =====================================================================
# T09 — HASH standalone missing numpy
# =====================================================================

def test_t09_raw_hash_cannot_run_without_numpy(raw_dir):
    ns = load_functions(raw_dir / "hash_momentum.py", ("calculate_indicators",), inject={})
    with pytest.raises(NameError, match="np"):
        ns["calculate_indicators"](np.zeros(50), 5, 10)


def test_t09_canonical_adapter_runs(raw_dir):
    """The packaging fix is documented (SD-HASH-01) and the adapter simply works."""
    market = _market(100 + np.cumsum(np.random.default_rng(1).normal(0, 0.5, 120)))
    adapter = HashMomentumEventAdapterV1(
        dict(mom_len=5, ema_len=10, cooldown_bars=1, stop_loss_perc=2.0, rr_ratio=3.0,
             tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
             mom_threshold_mult=1.0), market)
    decisions = adapter.run()
    assert len(decisions) == len(market)


def test_t09_static_inventory_finds_the_missing_import(raw_dir):
    inv = catalog_mod.inventory_file(raw_dir / "hash_momentum.py",
                                     ALLOWED_ALPHA_FILES["hash_momentum.py"])
    assert any(name.startswith("np@") for name in inv.undefined_globals)


# =====================================================================
# T10 — HASH short arrays and ATR convention
# =====================================================================

def test_t10_raw_hash_indexes_past_the_end_on_short_input(raw_dir):
    ns = load_functions(raw_dir / "hash_momentum.py", ("calculate_indicators",),
                        inject=default_injection())
    with pytest.raises(IndexError):
        ns["calculate_indicators"](np.arange(10, dtype=float), 2, 3)


def test_t10_adapter_fails_fast_instead_of_indexing_past_the_end():
    market = _market(np.arange(12, dtype=float) + 100.0)
    adapter = HashMomentumEventAdapterV1(
        dict(mom_len=2, ema_len=3, cooldown_bars=1, stop_loss_perc=2.0, rr_ratio=3.0,
             tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
             mom_threshold_mult=1.0), market)
    with pytest.raises(ref.WarmupError):
        adapter.prepare()


def test_t10_atr_conventions_do_not_mix():
    """The legacy close-move ATR and the true-range revision are different series."""
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 1.0, 200))
    high = close + 2.0
    low = close - 2.0
    legacy = ref.atr_hash_legacy_close_move(close, 14)
    revision = ref.atr_hash_true_range_variant(high, low, close, 14)
    assert not np.allclose(legacy[20:], revision[20:])
    flat = np.full(60, 100.0)
    assert ref.atr_hash_legacy_close_move(flat, 14)[-1] == 0.0
    assert ref.atr_hash_true_range_variant(flat + 1.0, flat - 1.0, flat, 14)[-1] > 0.0


def test_t10_variant_selection_is_explicit():
    market = _market(100 + np.cumsum(np.random.default_rng(2).normal(0, 0.5, 120)))
    params = dict(mom_len=5, ema_len=10, cooldown_bars=1, stop_loss_perc=2.0, rr_ratio=3.0,
                  tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
                  mom_threshold_mult=1.0)
    a = HashMomentumEventAdapterV1(params, market); a.prepare()
    b = HashMomentumEventAdapterV1(params, market, atr_variant="true_range_revision"); b.prepare()
    assert a.features.atr_variant == "legacy_close_move"
    assert not np.allclose(a.features.atr[20:], b.features.atr[20:])
    with pytest.raises(ValueError):
        HashMomentumEventAdapterV1(params, market, atr_variant="whatever")


# =====================================================================
# T11 / T12 — HASH ladder: same-bar crossing, remaining fraction, over-close
# =====================================================================

def test_t11_raw_source_fills_only_one_rung_on_a_bar_that_crosses_all(raw_dir):
    from crypto_regime_lab.alphas.probes import _hash_one_tp_branch

    observed = _hash_one_tp_branch(raw_dir.parent.parent)()
    assert observed["units"] == [0.0, 10.0, 5.0]


def test_t11_engine_resolves_an_ambiguous_bar_conservatively():
    from crypto_regime_lab.alphas.fixtures import fixture_stop_and_tp_same_bar

    result = fixture_stop_and_tp_same_bar()
    assert result.passed, result.observed


def test_t12_tp2_is_a_fraction_of_the_remaining_quantity():
    market = _market(np.full(60, 100.0))
    adapter = HashMomentumEventAdapterV1(
        dict(mom_len=3, ema_len=5, cooldown_bars=1, stop_loss_perc=10.0, rr_ratio=3.0,
             tp1_ratio=1.0, tp1_qty_perc=55, tp2_ratio=2.0, tp2_qty_perc=65,
             mom_threshold_mult=0.0), market)
    adapter.prepare()
    _stop, ladder = adapter.build_ladder(100.0, 1)
    remaining = 1.0
    remaining -= remaining * ladder[0][1]
    remaining -= remaining * ladder[1][1]
    assert abs(remaining - 0.1575) < 1e-12, "55% then 65% OF THE REMAINDER leaves 0.1575"
    assert ladder[2][1] == 1.0


def test_t12_ladder_never_over_closes():
    from crypto_regime_lab.alphas.fixtures import fixture_oco_and_over_close

    result = fixture_oco_and_over_close()
    assert result.passed, result.observed


def test_t12_unordered_ladder_presets_are_rejected():
    market = _market(np.full(60, 100.0))
    base = dict(mom_len=3, ema_len=5, cooldown_bars=1, stop_loss_perc=2.0,
                tp1_qty_perc=50, tp2_qty_perc=50, mom_threshold_mult=0.0)
    for tp1, tp2, final in ((2.4, 2.1, 3.2), (2.9, 3.8, 1.1), (2.1, 1.4, 3.1), (1.3, 3.7, 2.7)):
        with pytest.raises(LadderInfeasible):
            HashMomentumEventAdapterV1({**base, "tp1_ratio": tp1, "tp2_ratio": tp2,
                                        "rr_ratio": final}, market)


def test_t12_account_config_cannot_enter_the_alpha():
    market = _market(np.full(60, 100.0))
    base = dict(mom_len=3, ema_len=5, cooldown_bars=1, stop_loss_perc=2.0, rr_ratio=3.0,
                tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
                mom_threshold_mult=0.0)
    for key in ("initial_capital", "trading_fee", "usd_per_trade"):
        with pytest.raises(AccountConfigInAlpha):
            HashMomentumEventAdapterV1({**base, key: 1.0}, market)


# =====================================================================
# T13 / T14 / T15 — A-HMA
# =====================================================================

def test_t13_levels_move_when_the_open_gaps_away_from_the_close():
    close = np.full(80, 100.0)
    open_ = close.copy()
    market = _market(close, pad=1.0, open_=open_)
    adapter = AdaptiveHmaEventAdapterV1(
        dict(min_length=6, max_length=12, minor_min=3, minor_max=6, flat=5.0, atr_fast=3,
             atr_slow=7, mult=1.0, max_sl=2.0, take_profit=2.0, min_profit=0.5,
             tick_size=0.01), market)
    adapter.prepare()
    adapter._staged = {"side": 1, "stop_level": 95.0, "tp_level": 105.0, "decision_index": 10}
    follow = adapter._levels_from_fill(Fill(index=11, side=1, quantity=1.0, price=100.0,
                                            intent_kind=IntentKind.ENTER_LONG))
    assert follow[0].stop_price == 95.0 and follow[0].take_profit_price == 105.0
    # A gap through the take profit must not be booked as instant profit.
    adapter.state.position = 0.0
    adapter._staged = {"side": 1, "stop_level": 95.0, "tp_level": 105.0, "decision_index": 10}
    gapped = adapter._levels_from_fill(Fill(index=11, side=1, quantity=1.0, price=130.0,
                                            intent_kind=IntentKind.ENTER_LONG))
    assert gapped[0].kind is IntentKind.EXIT_ALL
    assert gapped[0].metadata["policy"] == "reject"


def test_t13_normalize_policy_keeps_the_entry_distance():
    market = _market(np.full(80, 100.0), pad=1.0)
    adapter = AdaptiveHmaEventAdapterV1(
        dict(min_length=6, max_length=12, minor_min=3, minor_max=6, flat=5.0, atr_fast=3,
             atr_slow=7, mult=1.0, max_sl=2.0, take_profit=2.0, min_profit=0.5,
             tick_size=0.01), market, gap_policy="normalize")
    adapter.prepare()
    adapter._staged = {"side": 1, "stop_level": 95.0, "tp_level": 105.0, "decision_index": 10}
    out = adapter._levels_from_fill(Fill(index=11, side=1, quantity=1.0, price=130.0,
                                         intent_kind=IntentKind.ENTER_LONG))
    assert out[0].kind is IntentKind.SET_PROTECTION
    assert out[0].stop_price == pytest.approx(125.0)
    assert out[0].take_profit_price == pytest.approx(135.0)


def test_t13_source_core_has_no_open_argument(raw_dir):
    import inspect

    ns = load_functions(raw_dir / "adaptive_hma_cpp.py", ("core_adaptive_hma_signals",),
                        inject=default_injection())
    assert "open" not in inspect.signature(ns["core_adaptive_hma_signals"]).parameters


def test_t14_inverted_lengths_are_rejected_not_swapped():
    market = _market(np.full(80, 100.0))
    base = dict(minor_min=3, minor_max=6, flat=5.0, atr_fast=3, atr_slow=7, mult=1.0,
                max_sl=2.0, take_profit=2.0, min_profit=0.5, tick_size=0.01)
    for lo, hi in ((292, 232), (320, 204), (248, 200), (308, 280)):
        with pytest.raises(InfeasibleConfiguration, match="infeasible"):
            AdaptiveHmaEventAdapterV1({**base, "min_length": lo, "max_length": hi}, market)


def test_t14_unused_knobs_are_recorded_not_implemented():
    market = _market(np.full(120, 100.0))
    adapter = AdaptiveHmaEventAdapterV1(
        dict(min_length=6, max_length=12, minor_min=3, minor_max=6, flat=5.0, atr_fast=3,
             atr_slow=7, mult=1.0, max_sl=2.0, take_profit=2.0, min_profit=0.5,
             tick_size=0.01, sl_mult=1.4, double_up=True), market)
    adapter.prepare()
    knobs = adapter.features.ignored_knobs
    assert set(knobs["values"]) == {"sl_mult", "double_up"}
    assert knobs["status"] == "IGNORED_BY_SOURCE"


def test_t14_tick_size_is_required_and_replaces_the_hardcoded_mintick():
    market = _market(np.full(80, 100.0))
    base = dict(min_length=6, max_length=12, minor_min=3, minor_max=6, flat=5.0, atr_fast=3,
                atr_slow=7, mult=1.0, max_sl=2.0, take_profit=2.0, min_profit=0.5)
    with pytest.raises(InfeasibleConfiguration, match="tick_size"):
        AdaptiveHmaEventAdapterV1(base, market)
    with pytest.raises(InfeasibleConfiguration):
        AdaptiveHmaEventAdapterV1({**base, "tick_size": 0.0}, market)


def test_t15_rsi_flat_repair_and_legacy_are_both_available():
    flat = np.full(40, 100.0)
    legacy = ref.rsi_hma_legacy(flat, 14)
    canonical = ref.rsi_hma_canonical(flat, 14)
    assert legacy[14] == 50.0 and legacy[15] == 100.0
    assert canonical[14] == 50.0 and canonical[15] == 50.0
    rng = np.random.default_rng(5)
    moving = 100 + np.cumsum(rng.normal(0, 1.0, 300))
    assert np.allclose(ref.rsi_hma_legacy(moving, 14), ref.rsi_hma_canonical(moving, 14))


def test_t15_no_decision_before_warmup():
    market = _market(100 + np.cumsum(np.random.default_rng(6).normal(0, 0.9, 140)))
    adapter = AdaptiveHmaEventAdapterV1(
        dict(min_length=6, max_length=12, minor_min=3, minor_max=6, flat=5.0, atr_fast=3,
             atr_slow=7, mult=1.0, max_sl=2.0, take_profit=2.0, min_profit=0.5,
             tick_size=0.01), market)
    decisions = adapter.run()
    warm = adapter.warmup_bars()
    assert warm == 58
    for d in decisions[:warm]:
        assert not d.warmup_ready and not d.intents


def test_t15_hull_padding_convention_is_preserved(raw_dir):
    ns = load_functions(raw_dir / "adaptive_hma_cpp.py", ("_xhma_at_t",), inject=default_injection())
    src = np.arange(50, dtype=float) + 100.0
    for t in (0, 1, 2, 7, 30):
        assert ns["_xhma_at_t"](src, t, 20) == pytest.approx(ref.xhma_at(src, t, 20), abs=0.0)


# =====================================================================
# T16 / T17 / T18 — A-VWAP
# =====================================================================

def _vwap_market(n=1200):
    import pandas as pd

    rng = np.random.default_rng(9)
    close = np.zeros(n)
    x = 100.0
    for i in range(n):
        x += -0.05 * (x - 100.0) + rng.normal(0, 0.6)
        close[i] = x
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return _market(close, pad=0.2, volume=np.abs(rng.normal(1000, 150, n)) + 1, index=idx)


VWAP_PARAMS = dict(rsi_len=14, rsi_os=45, rsi_ob=55, dev_mult=1.0, atr_len=14, stop_atr=2.0,
                   target_r=2.0, htf_ema_len=20, htf_tf="1h", exit_at_vwap=False,
                   time_stop_on=True, time_stop_bars=8)


def test_t16_dynamic_vwap_exit_is_off_by_default_and_lagged_when_enabled():
    market = _vwap_market()
    off = VwapMeanReversionEventAdapterV1(VWAP_PARAMS, market)
    assert off.params["exit_at_vwap"] is False, "the canonical pilot keeps it off (SD-VWAP-04)"
    on = VwapMeanReversionEventAdapterV1({**VWAP_PARAMS, "exit_at_vwap": True}, market)
    on.prepare()
    on.state.position = 1.0
    on.state.entry_index = 300
    decision = on._decide(305)
    amends = [i for i in decision.intents if i.kind is IntentKind.AMEND_PROTECTION]
    assert amends and amends[0].metadata["variant"] == "resting_previous_observed_vwap"
    assert amends[0].metadata["effective_from_bar"] == 306, "never effective on its own bar"


def test_t17_utc_day_reset_and_htf_availability():
    market = _vwap_market()
    adapter = VwapMeanReversionEventAdapterV1(VWAP_PARAMS, market)
    adapter.prepare()
    f = adapter.features
    assert f.new_day[0]
    assert int(f.new_day.sum()) == 13, "1200 fifteen-minute bars span 12.5 days"
    # No decision may be made before the HTF EMA has converged.
    needed = ema_convergence_bars(20, 1e-3)
    assert needed == 70
    ready_from = int(np.argmax(f.htf_available_from >= needed))
    decision = adapter.on_bar_close(max(ready_from - 1, 0))
    assert not decision.warmup_ready


def test_t17_htf_join_uses_available_at_not_the_resample_label():
    import pandas as pd

    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    close = np.arange(n, dtype=float) + 100.0
    ema, available_from = htf_ema_available_at(idx, close, "1h", 5, publication_delay=None)
    # The first bar of an hour cannot yet see that hour's own bucket.
    first_hour_start = 0
    assert np.isnan(ema[first_hour_start])
    # A bucket becomes available only at its close.
    assert available_from[4] == 0, "the 00:00-01:00 bucket is usable from 01:00"
    assert available_from[3] == -1


def test_t17_publication_delay_pushes_availability_later():
    import pandas as pd

    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    close = np.arange(n, dtype=float) + 100.0
    _e0, a0 = htf_ema_available_at(idx, close, "1h", 5, publication_delay=None)
    _e1, a1 = htf_ema_available_at(idx, close, "1h", 5, publication_delay="30min")
    assert (a1 <= a0).all() and (a1 < a0).any()


def test_t17_missing_index_is_a_hard_error():
    from crypto_regime_lab.alphas.a_vwap import HtfUnavailable

    market = _market(np.full(300, 100.0))
    adapter = VwapMeanReversionEventAdapterV1(VWAP_PARAMS, market)
    with pytest.raises(HtfUnavailable):
        adapter.prepare()


def test_t18_exit_precedence_is_frozen_and_identical_for_every_arm():
    assert EXIT_PRECEDENCE == ("stop_loss", "take_profit", "time_stop")
    market = _vwap_market()
    adapter = VwapMeanReversionEventAdapterV1(VWAP_PARAMS, market)
    adapter.prepare()
    adapter.state.position = 1.0
    adapter.state.entry_index = 300
    decision = adapter._decide(320)          # well past time_stop_bars
    exits = [i for i in decision.intents if i.kind is IntentKind.EXIT_ALL]
    assert exits and exits[0].reason == "time_stop"
    assert exits[0].metadata["precedence"] == list(EXIT_PRECEDENCE)
    assert exits[0].earliest_phase is ExecutionPhase.NEXT_OPEN, "a time stop is a close decision"


def test_t18_raw_source_puts_the_time_stop_first(raw_dir):
    """The finding this repair is based on, reproduced from the source."""
    ns = load_functions(raw_dir / "vwap.py",
                        ("n_sma", "n_stdev", "core_vwap_mean_reversion_logic"),
                        inject=default_injection())
    n = 260
    close = np.full(n, 100.0)
    close[200] = 90.0
    high = np.full(n, 100.0)
    low = np.full(n, 100.0)
    low[200] = 90.0
    low[202] = 1.0                     # bar 202 would hit any stop
    vwap = np.full(n, 100.0)
    rsi = np.full(n, 50.0); rsi[200] = 10.0
    atr = np.full(n, 1.0)
    htf = np.full(n, 90.0)
    pos = ns["core_vwap_mean_reversion_logic"](
        np.full(n, 100.0), high, low, close, vwap, rsi, atr, htf,
        30.0, 70.0, 1.0, 1.0, 100.0, False, True, 2)
    assert pos[200] == 1.0
    assert pos[202] == 0.0, "the time stop fires on the same bar the stop would have"


# =====================================================================
# T19 / T20 — A-SC
# =====================================================================

SC_PARAMS = {"coeff": 2, "AP": 11, "novolumedata": False, "src_col": "close",
             "alpha.condition_threshold": 50}


def _sc_market(n=260):
    close = np.concatenate([100 + np.linspace(0, 40, 110), 140 - np.linspace(0, 55, 80),
                            85 + np.linspace(0, 30, 70)])
    close = close + np.random.default_rng(11).normal(0, 0.25, n)
    return _market(close, pad=0.8)


def test_t19_missing_volume_is_an_explicit_rejection():
    market = _sc_market()
    zero_volume = MarketSlice(market.open, market.high, market.low, market.close,
                              np.zeros(len(market)))
    with pytest.raises(VolumeUnavailable):
        SignalCombineAdapterV1(SC_PARAMS, zero_volume)


def test_t19_fallback_is_available_but_must_be_asked_for():
    market = _sc_market()
    zero_volume = MarketSlice(market.open, market.high, market.low, market.close,
                              np.zeros(len(market)))
    adapter = SignalCombineAdapterV1(SC_PARAMS, zero_volume, strict_volume=False)
    assert adapter.use_rsi is True and adapter.fallback_applied is True
    declared = SignalCombineAdapterV1({**SC_PARAMS, "novolumedata": True}, zero_volume)
    assert declared.use_rsi is True and declared.fallback_applied is False


def test_t19_construction_and_dispatch_agree(raw_dir):
    """The source's disagreement, reproduced; the adapter has one resolved branch."""
    from crypto_regime_lab.alphas.probes import _sigcombine_fallback_dispatch

    observed = _sigcombine_fallback_dispatch(raw_dir.parent.parent)()
    assert "money_flow_index" in observed
    market = _sc_market()
    adapter = SignalCombineAdapterV1(SC_PARAMS, market)
    adapter.prepare()
    assert adapter.signals.indicator_used == "mfi"


def test_t20_position_is_long_flat_and_never_short():
    market = _sc_market()
    adapter = SignalCombineAdapterV1(SC_PARAMS, market)
    decisions = adapter.run()
    assert all(d.target_after_close >= 0.0 for d in decisions)
    kinds = {i.kind for d in decisions for i in d.intents}
    assert IntentKind.ENTER_SHORT not in kinds


def test_t20_amplitude_is_normalised_and_the_legacy_value_is_retained():
    market = _sc_market()
    adapter = SignalCombineAdapterV1(SC_PARAMS, market)
    decisions = adapter.run()
    entries = [i for d in decisions for i in d.intents if i.kind is IntentKind.ENTER_LONG]
    assert entries, "the fixture must produce at least one entry"
    meta = entries[0].metadata
    assert meta["sizing_mapping"] == "sizing_mapping_v1"
    assert meta["normalised_direction"] == 1.0 and meta["legacy_amplitude"] == 2.0


def test_t20_no_double_shift():
    """One declared decision timestamp; the fill lag lives in the engine contract."""
    market = _sc_market()
    adapter = SignalCombineAdapterV1(SC_PARAMS, market)
    decisions = adapter.run()
    for d in decisions:
        for i in d.intents:
            assert i.decision_index == d.index
            assert i.earliest_phase is ExecutionPhase.NEXT_OPEN


def test_t20_crossover_convention_is_the_source_one(raw_dir):
    from crypto_regime_lab.alphas.probes import _sigcombine_crossover_diff

    observed = _sigcombine_crossover_diff(raw_dir.parent.parent)()
    assert observed["actual"] != observed["standard_shifted_operand"]


def test_t20_seed_jump_is_not_tradable():
    """SC-07: the first condition-true bar ratchets trend off its zero seed."""
    market = _sc_market()
    adapter = SignalCombineAdapterV1(SC_PARAMS, market)
    adapter.run()
    first = adapter.signals.first_trend_init
    assert first is not None
    assert bool(adapter.signals.buy_signal[first]), "the seed jump does manufacture a buy signal"
    for d in adapter.decisions[:first + 3]:
        assert not d.warmup_ready and not d.intents


def test_t20_vectorised_and_loop_paths_agree():
    market = _sc_market()
    a = SignalCombineAdapterV1(SC_PARAMS, market, vectorised=True)
    b = SignalCombineAdapterV1(SC_PARAMS, market, vectorised=False)
    a.prepare(); b.prepare()
    for field in ("trend", "up_t", "down_t", "buy_signal", "sell_signal", "k1", "k2",
                  "o1", "o2", "long_signal", "short_signal"):
        assert np.array_equal(np.nan_to_num(getattr(a.signals, field).astype(float)),
                              np.nan_to_num(getattr(b.signals, field).astype(float))), field


# =====================================================================
# cross-cutting adapter invariants
# =====================================================================

@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_adapters_never_mutate_their_input(alpha_id):
    from crypto_regime_lab.alphas.golden import GOLDEN_FIXTURES, build_adapter

    fixture = GOLDEN_FIXTURES[alpha_id]()
    before = {name: getattr(fixture.market, name).copy()
              for name in ("open", "high", "low", "close", "volume")}
    build_adapter(fixture).run()
    for name, original in before.items():
        assert np.array_equal(original, getattr(fixture.market, name)), f"{alpha_id} mutated {name}"


@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_adapters_never_set_a_position_without_a_fill(alpha_id):
    from crypto_regime_lab.alphas.golden import GOLDEN_FIXTURES, build_adapter

    fixture = GOLDEN_FIXTURES[alpha_id]()
    adapter = build_adapter(fixture)
    for d in adapter.run():
        assert d.position_entering_bar == 0.0
    assert adapter.state.position == 0.0
    assert adapter.state.realized_fills == 0


@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_adapters_produce_an_all_no_signal_path(alpha_id):
    """A flat market must produce decisions and zero entries, never a crash."""
    from crypto_regime_lab.alphas.golden import GOLDEN_FIXTURES, build_adapter

    fixture = GOLDEN_FIXTURES[alpha_id]()
    n = len(fixture.market)
    flat = MarketSlice(np.full(n, 100.0), np.full(n, 100.0), np.full(n, 100.0),
                       np.full(n, 100.0), np.full(n, 1000.0), index=fixture.market.index)
    fixture.market = flat
    adapter = build_adapter(fixture)
    decisions = adapter.run()
    assert len(decisions) == n
    assert not any(i.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT)
                   for d in decisions for i in d.intents)


def test_look_ahead_guard_rejects_a_future_read():
    from crypto_regime_lab.alphas.base import LookAheadViolation

    market = _market(np.arange(50, dtype=float) + 100.0)
    market.set_cursor(10)
    market.guard(10)
    with pytest.raises(LookAheadViolation):
        market.guard(11)
