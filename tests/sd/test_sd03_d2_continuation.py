"""Coverage for sd/d2_continuation.py (guide SS2.4). Window-bounds logic is
pure and tested with synthetic dates; the real evaluate_candidate path is
integration-tested against the pinned snapshot separately (real cache, real
market data), matching this lab's standing discipline of proving a real I/O
path against real artifacts, not just mocked internals.
"""
from __future__ import annotations

import pandas as pd

from crypto_regime_lab.sd import d2_continuation as d2


def test_d2_window_bounds_h1_is_56_days_h2_is_next_56_days():
    bounds = d2.d2_window_bounds("2024-03-23")
    cutoff = pd.Timestamp("2024-03-23", tz="UTC")
    assert bounds["score_start"] == cutoff
    assert bounds["h1_end"] == cutoff + pd.Timedelta(days=56)
    assert bounds["score_end"] == cutoff + pd.Timedelta(days=112)
    assert (bounds["h1_end"] - bounds["score_start"]).days == d2.H1_DAYS
    assert (bounds["score_end"] - bounds["h1_end"]).days == d2.H2_DAYS


def test_d2_window_bounds_frame_start_has_pre_roll():
    bounds = d2.d2_window_bounds("2024-03-23")
    assert bounds["frame_start"] == bounds["score_start"] - pd.Timedelta(days=d2.PRE_ROLL_DAYS)


def test_d2_total_days_is_112():
    assert d2.D2_TOTAL_DAYS == 112


def test_candidate_d2_continuation_empty_frame_typed(monkeypatch):
    def fake_loader(symbol, *, start, end):
        empty_index = pd.DatetimeIndex([], tz="UTC")
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], index=empty_index), []

    result = d2.candidate_d2_continuation(None, None, "A-SC", fake_loader, {}, origin_cutoff="2024-03-23",
                                          symbol="BTCUSDT", economics={}, producer="test")
    assert result["status"] == "EMPTY_FRAME"
    assert result["d_age"] is None


def _has_real_archive() -> bool:
    from pathlib import Path
    lab = Path(__file__).resolve().parents[2]
    return (lab / "evidence" / "sharpe_decay_sd_v1" / "init_archive" / "origin_2020-07-04.json").exists()


def test_candidate_d2_continuation_real_h1_matches_standalone_fwd_sharpe():
    """Real integration test against the pinned snapshot + real committed
    archive: the D2 continuation's own H1 Sharpe (first 56 days of a
    continuous 112-day account) must match, bit-for-bit, the archive's own
    standalone 56-day FWD Sharpe for the IDENTICAL params/origin/economics
    -- guide SD03.6's own 'H1 phai match candidate forward H1' requirement,
    proven directly, not assumed."""
    import json
    from pathlib import Path

    import pytest

    if not _has_real_archive():
        pytest.skip("real SD-01 archive not present")

    from crypto_regime_lab.fp.evaluator import default_economics
    from crypto_regime_lab.ra.ra05_market import load_real_bars
    from crypto_regime_lab.sd import archive as ar
    from crypto_regime_lab.time_edge.compute_cache import ComputeCache

    lab = Path(__file__).resolve().parents[2]
    record = json.loads((lab / "evidence" / "sharpe_decay_sd_v1" / "init_archive" / "origin_2020-07-04.json")
                        .read_text(encoding="utf-8"))
    anchor_params = record["anchor_params"]
    cache = ComputeCache(lab, "sd01archive", cache_root=lab / "evidence" / "sharpe_decay_sd_v1" / "compute-cache")
    economics = default_economics()

    result = d2.candidate_d2_continuation(cache, lab, "A-SC", load_real_bars, anchor_params,
                                          origin_cutoff="2020-07-04", symbol="BTCUSDT",
                                          economics=economics, producer="test_d2_real_parity")
    fwd = ar.candidate_window_sharpe(cache, lab, "A-SC", load_real_bars, anchor_params,
                                     origin_cutoff="2020-07-04", kind="FWD", symbol="BTCUSDT",
                                     economics=economics, producer="test_d2_real_parity_fwd")
    assert result["status"] == "OK"
    assert result["sr_h1"] == pytest.approx(fwd["sharpe"], abs=1e-9)
