"""Coverage for sd/recipe_selection.py (guide SS5.8, SD02.7)."""
from __future__ import annotations

import pytest

from crypto_regime_lab.sd import fold_scoring as fsc
from crypto_regime_lab.sd import recipe_selection as rs


def _fold(origin, *, d_b, d_c_by_c):
    arms = {fsc.ARM_B: {"D_selected": d_b}}
    for c, d_c in d_c_by_c.items():
        arms[fsc.jm_arm_name(c)] = {"D_selected": d_c}
    return {"origin_cutoff": origin, "arms": arms}


def _folds_12(d_b_list, d_c_by_c_list):
    return [_fold(f"o{i}", d_b=d_b_list[i], d_c_by_c=d_c_by_c_list[i]) for i in range(12)]


def test_select_recipe_picks_largest_mean_r_among_valid_designs():
    # c=0.5: R always 0.1; c=1.0: R always 0.3 (winner); c=2.0: R always -0.1
    folds = _folds_12([1.0] * 12, [{0.5: 0.9, 1.0: 0.7, 2.0: 1.1} for _ in range(12)])
    result = rs.select_recipe(folds, recipes=(0.5, 1.0, 2.0))
    assert result["selected_c"] == 1.0
    assert result["mean_R"] == pytest.approx(0.3)
    assert result["decision"] == rs.DECISION_RECIPE_SELECTED   # 0.3 >= 0.2 threshold


def test_select_recipe_does_not_require_positive_r():
    # every design has NEGATIVE mean R -- still picks the LARGEST (least negative)
    folds = _folds_12([1.0] * 12, [{0.5: 1.3, 1.0: 1.2, 2.0: 1.5} for _ in range(12)])
    result = rs.select_recipe(folds, recipes=(0.5, 1.0, 2.0))
    # R = D_B - D_C: 0.5->-0.3, 1.0->-0.2, 2.0->-0.5 -- largest is c=1.0 (-0.2)
    assert result["selected_c"] == 1.0
    assert result["mean_R"] < 0
    assert result["decision"] == rs.DECISION_WEAK_EVIDENCE


def test_select_recipe_no_valid_design_below_paired_fold_floor():
    # only 5 paired folds for every c -- below MIN_PAIRED_FOLDS=12
    folds = _folds_12([1.0] * 5 + [None] * 7, [{0.5: 0.5, 1.0: 0.5, 2.0: 0.5} for _ in range(12)])
    result = rs.select_recipe(folds, recipes=(0.5, 1.0, 2.0))
    assert result["decision"] == rs.DECISION_NO_VALID_DESIGN
    assert result["selected_c"] is None


def test_select_recipe_tie_break_prefers_larger_c():
    folds = _folds_12([1.0] * 12, [{0.5: 0.7, 1.0: 0.7, 2.0: 0.9} for _ in range(12)])
    # R: c=0.5 -> 0.3, c=1.0 -> 0.3 (tied), c=2.0 -> 0.1
    result = rs.select_recipe(folds, recipes=(0.5, 1.0, 2.0))
    assert result["selected_c"] == 1.0   # larger of the tied {0.5, 1.0}
    assert result["tie_broken"] is True


def test_select_recipe_excludes_unpaired_folds_never_imputes():
    d_c_list = [{0.5: 0.6} for _ in range(12)]
    d_c_list[3][0.5] = None   # one fold has no D_selected for c=0.5's arm
    folds = _folds_12([1.0] * 12, d_c_list)
    for c in (1.0, 2.0):
        for row in d_c_list:
            row.setdefault(c, 0.6)
    stats = rs.recipe_stats(folds, c=0.5)
    assert stats["n_paired_folds"] == 11
    assert stats["technically_valid"] is False   # 11 < 12


def test_select_recipe_raises_with_no_recipes_to_choose_among():
    folds = _folds_12([1.0] * 12, [{} for _ in range(12)])
    with pytest.raises(rs.RecipeSelectionError):
        rs.select_recipe(folds, recipes=())


def test_recipe_stats_records_losing_designs_fully():
    folds = _folds_12([1.0] * 12, [{0.5: 2.0, 1.0: 0.5, 2.0: 0.5} for _ in range(12)])
    result = rs.select_recipe(folds, recipes=(0.5, 1.0, 2.0))
    assert len(result["candidates"]) == 3
    losing = next(c for c in result["candidates"] if c["c"] == 0.5)
    assert losing["mean_R"] == pytest.approx(-1.0)
    assert losing["technically_valid"] is True
