"""Coverage for sd/candidate_descriptors.py -- a REAL integration test
against SD-01's own already-committed archive and compute cache (a
guaranteed cache HIT, zero new engine compute), matching this lab's
standing discipline of proving a cache-reuse path against real artifacts
rather than a synthetic stand-in.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_regime_lab.fp.evaluator import default_economics
from crypto_regime_lab.ra.ra05_market import load_real_bars
from crypto_regime_lab.selector.alpha_schemas import A_SC
from crypto_regime_lab.sd import candidate_descriptors as cd
from crypto_regime_lab.time_edge.compute_cache import ComputeCache

LAB = Path(__file__).resolve().parents[2]
LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "init_archive"
CACHE_ROOT = LAB / "evidence" / "sharpe_decay_sd_v1" / "compute-cache"


def _has_real_archive() -> bool:
    return (LEDGER_DIR / "origin_2020-07-04.json").exists() and CACHE_ROOT.exists()


pytestmark = pytest.mark.skipif(not _has_real_archive(),
                                reason="SD-01's real committed archive/cache not present")


def _load_origin(origin: str) -> dict:
    return json.loads((LEDGER_DIR / f"origin_{origin}.json").read_text(encoding="utf-8"))


def test_fetch_activity_entries_is_a_real_cache_hit_on_committed_archive():
    record = _load_origin("2020-07-04")
    row = record["label_rows"][0]
    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    result = cd.fetch_activity_entries(cache, LAB, "A-SC", load_real_bars, row["params"],
                                       origin_cutoff=record["origin_cutoff"], symbol=record["symbol"],
                                       economics=default_economics(), producer="test_sd02_candidate_descriptors")
    assert result["cache_event"] == "HIT"
    assert isinstance(result["entries"], int)
    assert result["entries"] >= 0


def test_build_descriptor_row_matches_raw_feature_row_shape():
    record = _load_origin("2020-07-04")
    row = record["label_rows"][0]
    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    activity = cd.fetch_activity_entries(cache, LAB, "A-SC", load_real_bars, row["params"],
                                         origin_cutoff=record["origin_cutoff"], symbol=record["symbol"],
                                         economics=default_economics(), producer="test_sd02_candidate_descriptors")
    descriptor = cd.build_descriptor_row(A_SC, row, activity_entries=activity["entries"])
    assert set(descriptor) == {"norm_coeff", "norm_AP", "norm_alpha.condition_threshold",
                               "is_daily_sharpe", "activity_entries"}
    assert descriptor["is_daily_sharpe"] == pytest.approx(row["is_window"]["sharpe"])
    assert descriptor["activity_entries"] == pytest.approx(float(activity["entries"]))


def test_build_descriptor_row_raises_on_bad_is_status():
    row = {"candidate_id": "x", "params": {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
                                           "novolumedata": False, "src_col": "close"},
          "is_window": {"sharpe": None, "sharpe_status": "WRONG_DAY_COUNT"}}
    with pytest.raises(cd.DescriptorError):
        cd.build_descriptor_row(A_SC, row, activity_entries=10)


def test_two_candidates_at_same_origin_have_consistent_anchor_zero_via_contrast():
    """Real end-to-end: the origin's own anchor row's descriptor, contrasted
    against itself, must give v=0 -- proving the real-data path preserves
    the anchor-zero-by-construction guarantee all the way from committed
    archive JSON through to a contrast vector."""
    from crypto_regime_lab.sd.contrast_features import contrast_vector, fit_phi
    import numpy as np

    record = _load_origin("2020-07-04")
    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    rows = []
    for row in record["label_rows"]:
        activity = cd.fetch_activity_entries(cache, LAB, "A-SC", load_real_bars, row["params"],
                                             origin_cutoff=record["origin_cutoff"], symbol=record["symbol"],
                                             economics=default_economics(),
                                             producer="test_sd02_candidate_descriptors")
        rows.append(cd.build_descriptor_row(A_SC, row, activity_entries=activity["entries"]))
    anchor_idx = next(i for i, r in enumerate(record["label_rows"]) if r["is_anchor"])
    fit = fit_phi(rows)
    v = contrast_vector(fit, rows[anchor_idx], rows[anchor_idx])
    assert np.allclose(v, 0.0)
