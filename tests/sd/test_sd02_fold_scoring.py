"""Coverage for sd/fold_scoring.py (guide SS3.4/5.5, SD02.4)."""
from __future__ import annotations

import pytest

from crypto_regime_lab.sd import fold_scoring as fs


def _panel(n=4):
    anchor = {"candidate_id": "anchor", "params": {"p": 0}, "features": {"f": 0.0},
             "sr_is": 1.0, "is_anchor": True}
    rows = [anchor]
    for i in range(n):
        rows.append({"candidate_id": f"c{i}", "params": {"p": i + 1}, "features": {"f": float(i + 1)},
                    "sr_is": 1.0 + 0.1 * i, "is_anchor": False})
    return rows


def test_score_pool_anchor_gets_zero_yhat_structurally():
    panel = _panel()
    def predict_fn(row, anchor_row):
        return row["features"]["f"] - anchor_row["features"]["f"]   # trivial linear model
    result = fs.score_pool(predict_fn, panel, anchor_id="anchor")
    anchor_scored = next(r for r in result["scored"] if r["candidate_id"] == "anchor")
    assert anchor_scored["y_hat"] == pytest.approx(0.0)
    assert anchor_scored["q_hat"] == pytest.approx(0.0)


def test_score_pool_picks_lowest_yhat_among_eligible():
    panel = _panel()
    def predict_fn(row, anchor_row):
        # candidate c0 gets the most negative y_hat -> should win (minY)
        return {"c0": -0.5, "c1": 0.2, "c2": 0.3, "c3": 0.1}.get(row["candidate_id"], 0.0)
    result = fs.score_pool(predict_fn, panel, anchor_id="anchor")
    assert result["selection"]["winner_id"] == "c0"
    assert result["selection"]["is_anchor"] is False


def test_score_pool_falls_back_to_anchor_when_nothing_clears_guard():
    panel = _panel()
    def predict_fn(row, anchor_row):
        # every non-anchor candidate is way below the -0.10 guard on Q_hat
        return 0.0 if row["is_anchor"] else 5.0   # Q_hat = sr_is - sr_is_anchor - 5.0 << -0.10
    result = fs.score_pool(predict_fn, panel, anchor_id="anchor")
    assert result["selection"]["winner_id"] == "anchor"
    assert result["selection"]["is_anchor"] is True


def test_score_pool_raises_without_anchor_row():
    panel = [r for r in _panel() if not r["is_anchor"]]
    with pytest.raises(fs.FoldScoringError):
        fs.score_pool(lambda row, anchor: 0.0, panel, anchor_id="anchor")


def test_score_pool_arm_a_is_always_the_anchor_trivially():
    panel = _panel()
    result = fs.score_pool_arm_a(panel, anchor_id="anchor")
    assert result["selection"]["winner_id"] == "anchor"
    assert result["selection"]["y_hat"] == 0.0
    assert result["scored"][0]["q_hat"] == 0.0


def test_jm_arm_name_format():
    assert fs.jm_arm_name(0.5) == "JM_C0.5"
    assert fs.jm_arm_name(1.0) == "JM_C1.0"
