"""SD-01: archive-build pure logic (unique_candidates, representative_panel,
window_bounds) -- no real engine calls, those are covered by the real
integration probes cited in the SD01.7 orchestrator's own evidence."""
from __future__ import annotations

import pandas as pd
import pytest

from crypto_regime_lab.sd import archive as ar


def _trial(trial_id, params, mean_is_sharpe, pruned=False):
    return {"trial_id": trial_id, "params": params, "mean_is_sharpe": mean_is_sharpe,
           "pruned": pruned}


def test_unique_candidates_deduplicates_by_params():
    records = [
        _trial(0, {"coeff": 4, "AP": 45}, 0.20),
        _trial(1, {"coeff": 4, "AP": 45}, 0.20),   # exact duplicate params
        _trial(2, {"coeff": 5, "AP": 45}, 0.15),
    ]
    out = ar.unique_candidates(records)
    assert len(out) == 2


def test_unique_candidates_excludes_pruned():
    records = [_trial(0, {"coeff": 4}, 0.20), _trial(1, {"coeff": 5}, 0.10, pruned=True)]
    out = ar.unique_candidates(records)
    assert len(out) == 1
    assert out[0]["trial_id"] == 0


def test_representative_panel_ranks_by_mean_is_sharpe_descending():
    candidates = [_trial(0, {"c": 1}, 0.10), _trial(1, {"c": 2}, 0.50), _trial(2, {"c": 3}, 0.30)]
    panel = ar.representative_panel(candidates, anchor_params={"c": 2}, max_size=2)
    assert [r["trial_id"] for r in panel] == [1, 2]   # 0.50 then 0.30, drops 0.10


def test_representative_panel_always_includes_anchor_even_outside_top_n():
    candidates = [_trial(0, {"c": 1}, 0.90), _trial(1, {"c": 2}, 0.80),
                 _trial(2, {"c": 3}, 0.70), _trial(3, {"c": 4}, -5.0)]   # anchor, worst IS
    panel = ar.representative_panel(candidates, anchor_params={"c": 4}, max_size=2)
    assert len(panel) == 2
    assert any(r["params"] == {"c": 4} for r in panel)


def test_representative_panel_deterministic_tie_break_by_trial_id():
    candidates = [_trial(5, {"c": 1}, 0.5), _trial(2, {"c": 2}, 0.5), _trial(9, {"c": 3}, 0.5)]
    panel = ar.representative_panel(candidates, anchor_params={"c": 1}, max_size=2)
    assert [r["trial_id"] for r in panel] == [2, 5]


def test_representative_panel_raises_when_anchor_not_in_candidates():
    candidates = [_trial(0, {"c": 1}, 0.5)]
    with pytest.raises(ar.ArchiveError):
        ar.representative_panel(candidates, anchor_params={"c": 999}, max_size=1)


def test_window_bounds_is_window_180_days_ending_at_cutoff():
    bounds = ar.window_bounds("2021-06-01", kind="IS")
    assert bounds["score_end"] == pd.Timestamp("2021-06-01", tz="UTC")
    assert bounds["score_start"] == pd.Timestamp("2021-06-01", tz="UTC") - pd.Timedelta(days=180)
    assert (bounds["score_end"] - bounds["score_start"]).days == 180
    assert bounds["frame_start"] == bounds["score_start"] - pd.Timedelta(days=ar.PRE_ROLL_DAYS)


def test_window_bounds_fwd_window_56_days_starting_at_cutoff():
    bounds = ar.window_bounds("2021-06-01", kind="FWD")
    assert bounds["score_start"] == pd.Timestamp("2021-06-01", tz="UTC")
    assert bounds["score_end"] == pd.Timestamp("2021-06-01", tz="UTC") + pd.Timedelta(days=56)
    assert (bounds["score_end"] - bounds["score_start"]).days == 56


def test_window_bounds_rejects_unknown_kind():
    with pytest.raises(ar.ArchiveError):
        ar.window_bounds("2021-06-01", kind="H3")
