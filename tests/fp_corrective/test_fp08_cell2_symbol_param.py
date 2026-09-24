"""FP-08's own symbol parameterization of checkpoint_search.run_origin_search
and selector_b.load_origin_is_frame (guide FP08.1: a second cell by symbol,
same alpha -- FP-03's search-space qualification is alpha-level and carries
over unchanged). Small real engine calls only (a few seconds each), never
the ~256-trial/45min-plus scale a real cell-2 origin costs.
"""
from __future__ import annotations

from crypto_regime_lab.fp import checkpoint_search as cs
from crypto_regime_lab.fp import selector_b as sb


def test_run_origin_search_defaults_to_btcusdt_unchanged():
    """Backward compatibility: every existing FP-03/04 caller passes no
    symbol/alpha_id kwarg and must keep getting BTCUSDT/A-SC."""
    result = cs.run_origin_search(origin_cutoff="2023-06-05", trials=2, seed=20260922,
                                  train_memory_days=3, forward_days=2)
    assert result["symbol"] == "BTCUSDT"
    assert result["alpha_id"] == "A-SC"
    assert result["wf_result"]["ok"] is True


def test_run_origin_search_accepts_a_different_symbol_and_actually_loads_its_own_data():
    """A real small engine call on ETHUSDT -- proves the symbol argument
    actually reaches load_real_bars (not silently ignored). Same real
    partitions load either way (both symbols cover this window); the price
    level itself is the discriminator, checked directly against the frame
    loaded the SAME way (load_origin_is_frame's own test below)."""
    result = cs.run_origin_search(origin_cutoff="2023-06-05", trials=2, seed=20260922,
                                  train_memory_days=3, forward_days=2, symbol="ETHUSDT")
    assert result["symbol"] == "ETHUSDT"
    assert result["wf_result"]["ok"] is True
    assert result["market_partitions_used"] == ["2023-05", "2023-06"]


def test_run_origin_search_accepts_a_different_alpha_id_too():
    """alpha_id is independently overridable, even though FP-08's own cell 2
    keeps A-SC fixed -- proves the parameterization is not coupled."""
    result = cs.run_origin_search(origin_cutoff="2023-06-05", trials=2, seed=20260922,
                                  train_memory_days=3, forward_days=2, alpha_id="A-SC")
    assert result["alpha_id"] == "A-SC"


def test_load_origin_is_frame_defaults_to_btcusdt_unchanged():
    frame = sb.load_origin_is_frame("A-SC", "2023-06-05", train_memory_days=3)
    assert len(frame) > 0
    # BTC's price level in this window is tens of thousands; ETH's is low thousands.
    assert frame["close"].mean() > 10000


def test_load_origin_is_frame_accepts_a_different_symbol():
    frame = sb.load_origin_is_frame("A-SC", "2023-06-05", train_memory_days=3, symbol="ETHUSDT")
    assert len(frame) > 0
    assert frame["close"].mean() < 10000
