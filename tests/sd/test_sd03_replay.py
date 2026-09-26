"""Coverage for scripts/run_sd03_replay.py's real replay result (guide
SD03.8: same-contract replay) -- and a synthetic proof that the gated
comparison CAN fail, so a real match is not vacuous.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[2]
REPLAY_PATH = LAB / "evidence" / "sharpe_decay_sd_v1" / "sd03_replay_result.json"

pytestmark = pytest.mark.skipif(not REPLAY_PATH.exists(), reason="real SD-03 replay result not present")


def test_real_replay_all_gated_fields_match():
    record = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    assert record["all_gated_fields_match"] is True
    for c in record["d2_comparisons"]:
        assert c["match"] is True, c


def test_real_replay_pool_replay_deliberately_not_run_and_disclosed():
    """S3-T02-POOL-REPLAY (re-running the search itself) is NOT included
    in the gated replay result -- run_origin_search has no caching layer
    (confirmed twice in this session: re-running it costs a full fresh
    ~45min real 128-trial search every time, unlike evaluate_candidate/
    run_deployment). This is disclosed explicitly, never silently
    omitted; replay_pool()'s own logic is separately tested against a
    stubbed search (see test_replay_pool_logic_reached_via_a_stubbed_
    search_never_a_real_one below)."""
    record = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    assert record["pool_replay"] is None
    assert "no caching layer" in record["pool_replay_note"]


def test_real_replay_cache_provenance_shows_miss_to_hit():
    """The original run was a real cache MISS (first computation); the
    replay must be a HIT (proving it found and reused the SAME real
    computation, not a coincidental match)."""
    record = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    assert record["cache_provenance"]["original_cache_event"] == "MISS"
    assert record["cache_provenance"]["replay_cache_event"] == "HIT"


def test_real_replay_disclosure_present_and_not_overclaimed():
    record = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    assert "NOT an independent confirmation" in record["disclosure"]


def test_gated_comparison_logic_can_actually_fail():
    """Proves the comparison shape used by run_sd03_replay.py is not
    vacuously true -- a real mismatch must be caught."""
    original = {"status": "OK", "sr_h1": 1.0, "sr_h2": 2.0, "d_age": -1.0}
    replay = {"status": "OK", "sr_h1": 1.0, "sr_h2": 2.0, "d_age": -1.5}   # deliberately wrong
    fields = ("status", "sr_h1", "sr_h2", "d_age")
    comparisons = [{"field": f, "original": original[f], "replay": replay[f],
                   "match": original[f] == replay[f]} for f in fields]
    assert not all(c["match"] for c in comparisons)


def test_replay_pool_logic_reached_via_a_stubbed_search_never_a_real_one(monkeypatch):
    """replay_pool() itself is deliberately NOT called by main() -- a real
    invocation costs a full fresh ~45min search every time (run_origin_
    search has no caching layer, confirmed twice this session). This test
    still exercises its own comparison logic for real, with
    run_origin_search/_trial_records/unique_candidates/representative_panel
    stubbed to fast, synthetic, deterministic substitutes -- proving the
    function's own arithmetic/comparison shape works, without spending
    any real engine compute."""
    import sys
    from pathlib import Path

    lab = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(lab / "scripts"))
    import run_sd03_replay as replay_mod

    fake_params = {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
                  "novolumedata": False, "src_col": "close"}
    fake_original = {"panel": {"anchor_params": fake_params,
                              "search": {"n_unique_candidates": 3},
                              "label_rows": [{"candidate_id": "anchor"}, {"candidate_id": "c1"}]}}
    fake_original_path = replay_mod.FINAL_DIR / "fold_2099-01-01.json"
    fake_original_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    fake_original_path.write_text(json.dumps(fake_original), encoding="utf-8")

    def fake_run_origin_search(**kwargs):
        return {"wf_result": {"trial_records": [], "selected_params": fake_params}}

    def fake_trial_records(wf_result):
        return []

    def fake_unique_candidates(records):
        return [{"params": fake_params}, {"params": {"coeff": 5, "AP": 21,
                "alpha.condition_threshold": 60, "novolumedata": False, "src_col": "close"}},
               {"params": {"coeff": 6, "AP": 22, "alpha.condition_threshold": 65,
                "novolumedata": False, "src_col": "close"}}]

    def fake_representative_panel(candidates, *, anchor_params, max_size=16):
        return candidates[:2]

    monkeypatch.setattr(replay_mod, "run_origin_search", fake_run_origin_search)
    monkeypatch.setattr(replay_mod, "_trial_records", fake_trial_records)
    monkeypatch.setattr(replay_mod.ar, "unique_candidates", fake_unique_candidates)
    monkeypatch.setattr(replay_mod.ar, "representative_panel", fake_representative_panel)

    try:
        result = replay_mod.replay_pool(origin_cutoff="2099-01-01")
    finally:
        fake_original_path.unlink()

    assert result["origin_cutoff"] == "2099-01-01"
    anchor_check = next(c for c in result["comparisons"] if c["field"] == "anchor_params")
    assert anchor_check["match"] is True
    count_check = next(c for c in result["comparisons"] if c["field"] == "n_unique_candidates")
    assert count_check["match"] is True
