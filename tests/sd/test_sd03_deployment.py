"""Coverage for sd/deployment_sd03.py (guide SD03.5) -- the schedule-shaping
adapter is tested directly with synthetic fold records; the real
run_deployment call itself is FP-02/FP-07's own already-qualified,
already-tested route and is not re-tested here.
"""
from __future__ import annotations

import pandas as pd
import pytest

from crypto_regime_lab.sd import deployment_sd03 as dep


def _fold(origin, *, winner_id, params, is_anchor):
    return {"arms": {"B_SD_GLOBAL": {
        "selection": {"winner_id": winner_id, "is_anchor": is_anchor},
        "scored": [{"candidate_id": winner_id, "params": params},
                  {"candidate_id": "other", "params": {"coeff": 9}}]}}}


def test_selections_by_origin_from_final_folds_looks_up_winner_params():
    folds = {"2024-03-23": _fold("2024-03-23", winner_id="X", params={"coeff": 5}, is_anchor=False),
            "2024-05-18": _fold("2024-05-18", winner_id="anchor", params={"coeff": 4}, is_anchor=True)}
    result = dep.selections_by_origin_from_final_folds(folds, arm="B_SD_GLOBAL")
    assert result["2024-03-23"]["params"] == {"coeff": 5}
    assert result["2024-03-23"]["reason"] == "SELECTED"
    assert result["2024-05-18"]["reason"] == "ANCHOR"
    assert result["2024-05-18"]["source"] == "B_SD_GLOBAL"


def test_selections_by_origin_raises_on_missing_arm():
    folds = {"2024-03-23": _fold("2024-03-23", winner_id="X", params={"coeff": 5}, is_anchor=False)}
    with pytest.raises(dep.DeploymentSD03Error):
        dep.selections_by_origin_from_final_folds(folds, arm="NOT_AN_ARM")


def test_selections_by_origin_raises_when_winner_missing_from_own_scored_table():
    folds = {"2024-03-23": {"arms": {"B_SD_GLOBAL": {
        "selection": {"winner_id": "ghost", "is_anchor": False}, "scored": []}}}}
    with pytest.raises(dep.DeploymentSD03Error):
        dep.selections_by_origin_from_final_folds(folds, arm="B_SD_GLOBAL")


def test_build_admitted_schedules_produces_one_per_arm():
    folds = {"2024-03-23": _fold("2024-03-23", winner_id="X", params={"coeff": 5}, is_anchor=False)}
    admitted = dep.build_admitted_schedules(folds, arms=("B_SD_GLOBAL",))
    assert "B_SD_GLOBAL" in admitted
    assert admitted["B_SD_GLOBAL"]["arm"] == "B_SD_GLOBAL"


def test_build_deployment_schedules_maps_to_real_bar_indices():
    folds = {"2024-03-23": _fold("2024-03-23", winner_id="X", params={"coeff": 5}, is_anchor=False)}
    admitted = dep.build_admitted_schedules(folds, arms=("B_SD_GLOBAL",))
    frame_index = pd.date_range("2024-03-20", periods=20, freq="D", tz="UTC")
    schedules = dep.build_deployment_schedules(admitted, frame_index=frame_index)
    assert len(schedules["B_SD_GLOBAL"]) == 1
    assert schedules["B_SD_GLOBAL"][0]["params"] == {"coeff": 5}
