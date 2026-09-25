"""SD-01: candidate selection rule (S1-T09-DECAY-RANKING, S1-T10-C-INDEPENDENT)."""
from __future__ import annotations

import pytest

from crypto_regime_lab.sd import selection as sel


def test_q_hat_identity():
    assert sel.q_hat_identity(1.50, 1.20, 0.10) == pytest.approx(0.20)


def test_eligible_candidates_applies_guard_margin():
    scored = [
        {"candidate_id": "a", "y_hat": -0.5, "q_hat": -0.05},   # clears -0.10
        {"candidate_id": "b", "y_hat": -0.3, "q_hat": -0.20},   # fails -0.10
        {"candidate_id": "c", "y_hat": -0.1, "q_hat": 0.0},
    ]
    out = sel.eligible_candidates(scored)
    by_id = {r["candidate_id"]: r["eligible"] for r in out}
    assert by_id == {"a": True, "b": False, "c": True}


def test_eligible_candidates_respects_explicit_safety_flag():
    scored = [{"candidate_id": "a", "y_hat": -0.5, "q_hat": 0.0, "safety_ok": False}]
    out = sel.eligible_candidates(scored)
    assert out[0]["eligible"] is False


def test_eligible_candidates_raises_on_missing_field():
    with pytest.raises(sel.SelectionError):
        sel.eligible_candidates([{"candidate_id": "a", "y_hat": 0.0}])   # no q_hat


def _row(cid, y_hat, q_hat=0.0, eligible=True, **extra):
    return {"candidate_id": cid, "y_hat": y_hat, "q_hat": q_hat, "eligible": eligible, **extra}


def test_decay_ranking_min_y_not_max_return():
    """S1-T09-DECAY-RANKING: a fixture where min predicted Y and max predicted
    (return-like) utility disagree -- the selector follows Y, never utility.
    Candidate 'high_return' has the best (highest) utility-like field but a
    WORSE (higher) decay label; 'low_decay' has the lowest Y_hat and must win."""
    scored = [
        _row("anchor", 0.0),
        _row("high_return", -0.05, predicted_forward_utility=0.90),   # would win under F03a's old rule
        _row("low_decay", -0.40, predicted_forward_utility=0.10),     # wins under the correct minY rule
    ]
    result = sel.select_min_y(scored, anchor_id="anchor")
    assert result["winner_id"] == "low_decay"
    assert result["decision"] == "CANDIDATE_SELECTED"
    assert result["is_anchor"] is False


def test_anchor_wins_legitimately_when_nothing_beats_zero():
    scored = [_row("anchor", 0.0), _row("worse", 0.30), _row("also_worse", 0.10)]
    result = sel.select_min_y(scored, anchor_id="anchor")
    assert result["winner_id"] == "anchor"
    assert result["is_anchor"] is True


def test_select_min_y_raises_when_anchor_row_missing():
    with pytest.raises(sel.SelectionError):
        sel.select_min_y([_row("a", -0.1)], anchor_id="anchor")


def test_select_min_y_raises_when_anchor_y_hat_is_not_zero():
    with pytest.raises(sel.SelectionError):
        sel.select_min_y([_row("anchor", 0.05)], anchor_id="anchor")


def test_select_min_y_raises_when_nothing_eligible_not_even_anchor():
    scored = [_row("anchor", 0.0, eligible=False)]
    with pytest.raises(sel.SelectionError):
        sel.select_min_y(scored, anchor_id="anchor")


def test_tie_break_deterministic_by_candidate_id_without_schema():
    scored = [_row("anchor", 0.0), _row("zzz", -0.2), _row("aaa", -0.2)]
    result = sel.select_min_y(scored, anchor_id="anchor")
    assert result["winner_id"] == "aaa"
    assert result["tie_broken"] is True


def test_tie_break_uses_schema_distance_to_anchor_when_available():
    class _StubSchema:
        def distance(self, a, b):
            return abs(a["x"] - b["x"])

    scored = [
        _row("anchor", 0.0, params={"x": 0}, anchor_params={"x": 0}),
        _row("far", -0.2, params={"x": 10}, anchor_params={"x": 0}),
        _row("near", -0.2, params={"x": 1}, anchor_params={"x": 0}),
    ]
    result = sel.select_min_y(scored, anchor_id="anchor", schema=_StubSchema())
    assert result["winner_id"] == "near"


def test_c_independence_same_function_no_shared_state_between_calls():
    """S1-T10-C-INDEPENDENT (module-level structural proof): this module has
    no notion of 'B' or 'C' at all -- calling it twice with independently
    built inputs never lets one call's outcome influence the other's. This
    is what structurally prevents the F05 short-circuit (an earlier design
    literally returned FALLBACK_TO_A for C whenever B itself had fallen
    back) from recurring."""
    b_scored = [_row("anchor", 0.0)]   # B: nothing eligible beats anchor -> ANCHOR wins (its own "fallback")
    c_scored = [_row("anchor", 0.0), _row("c_winner", -0.5)]   # C: has its own genuine winner
    b_result = sel.select_min_y(b_scored, anchor_id="anchor")
    c_result = sel.select_min_y(c_scored, anchor_id="anchor")
    assert b_result["is_anchor"] is True
    assert c_result["winner_id"] == "c_winner"   # C found its own winner, unaffected by B's outcome
