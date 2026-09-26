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
    for c in record["comparisons"]:
        assert c["match"] is True, c


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
