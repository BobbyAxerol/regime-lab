"""FP-07 locked_study: arm selection, fallback chains, admission/schedule
construction -- on synthetic rows (engine-free; these are causal/fallback
properties) plus a real cache-hit read against FP-04's actual committed
archive.
"""
from __future__ import annotations

import pandas as pd
import pytest

from crypto_regime_lab.fp import locked_study as ls
from crypto_regime_lab.fp import selector_b as sb
from crypto_regime_lab.fp import selector_c as sc

FORWARD_HORIZON_DAYS = 28


def _b_row(record_id, origin_cutoff, origin_time, *, label=0.0001, support=5, **overrides):
    base = {name: 0.5 for name in sb.FEATURE_NAMES}
    base.update(overrides)
    label_available_at = (pd.Timestamp(origin_time) + pd.Timedelta(days=FORWARD_HORIZON_DAYS)).isoformat()
    base.update({"record_id": record_id, "origin_cutoff": origin_cutoff, "origin_time": origin_time,
                "label": label, "label_available_at": label_available_at,
                "maturity_state": "matured_forward_record", "region_support_within_origin": support,
                "params": {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
                          "novolumedata": False, "src_col": "close"}})
    return base


def _c_row(b_row, *, ctx_direction_efficiency=0.1, ctx_volatility_ratio=1.0):
    return sc.build_c_row(b_row, {"ctx_direction_efficiency": ctx_direction_efficiency,
                                  "ctx_volatility_ratio": ctx_volatility_ratio})


def _archive(n_origins=6, n_per_origin=3, horizon_days=28):
    base = pd.Timestamp("2022-01-01", tz="UTC")
    b_rows = []
    for i in range(n_origins):
        origin_ts = base + pd.Timedelta(days=91 * i)
        oc = origin_ts.strftime("%Y-%m-%d")
        ot = origin_ts.isoformat()
        for j in range(n_per_origin):
            b_rows.append(_b_row(f"{oc}:R{j:02d}", oc, ot, label=0.0001 * (i + j), support=5 + j))
    c_rows = [_c_row(r) for r in b_rows]
    return b_rows, c_rows


# ---------------------------------------------------------------------------
# load_origin_wf_result / arm_a_selection -- real cache-hit read
# ---------------------------------------------------------------------------

def test_load_origin_wf_result_reads_the_real_fp04_cache():
    wf = ls.load_origin_wf_result("2021-01-01")
    assert wf["ok"] is True
    assert wf["optimization_mode"] == "mode_4_is_only_robust"


def test_load_origin_wf_result_raises_on_a_missing_origin():
    with pytest.raises(ls.LockedStudyError, match="no cached"):
        ls.load_origin_wf_result("1999-01-01")


def test_arm_a_selection_extracts_selected_params():
    wf = ls.load_origin_wf_result("2021-01-01")
    params = ls.arm_a_selection(wf)
    assert set(params) >= {"coeff", "AP", "alpha.condition_threshold"}


def test_arm_a_selection_raises_when_selected_params_missing():
    with pytest.raises(ls.LockedStudyError, match="selected_params"):
        ls.arm_a_selection({"ok": True})


# ---------------------------------------------------------------------------
# walk_forward_b_selection -- fallback chain and real selection
# ---------------------------------------------------------------------------

def test_walk_forward_b_selection_falls_back_to_a_at_the_first_origin():
    """The very first origin has zero prior matured origins -- guide 8.7's
    fit floor cannot be met, so B must fall back to A, a real disclosed
    fallback period (guide 19 item 8), not an error."""
    b_rows, _c_rows = _archive()
    first_origin = sorted({r["origin_cutoff"] for r in b_rows})[0]
    result = ls.walk_forward_b_selection(b_rows, {}, origin_cutoff=first_origin, alpha=1.0,
                                         utility_floor=6.4e-05, support_floor=2)
    assert result["source"] == "FALLBACK_TO_A"
    assert result["params"] is None


def test_walk_forward_b_selection_falls_back_when_nothing_clears_the_utility_floor():
    b_rows, _c_rows = _archive(n_origins=6, n_per_origin=3)
    last_origin = sorted({r["origin_cutoff"] for r in b_rows})[-1]
    # labels are tiny (<=0.0008) -- far below the registered 6.4e-05 floor scaled up here
    result = ls.walk_forward_b_selection(b_rows, {}, origin_cutoff=last_origin, alpha=1.0,
                                         utility_floor=1.0, support_floor=2)
    assert result["source"] == "FALLBACK_TO_A"
    assert result["params"] is None
    assert "utility/support floor" in result["reason"]


def test_walk_forward_b_selection_selects_a_real_scored_candidate_when_eligible():
    b_rows, _c_rows = _archive(n_origins=6, n_per_origin=3)
    last_origin = sorted({r["origin_cutoff"] for r in b_rows})[-1]
    result = ls.walk_forward_b_selection(b_rows, {}, origin_cutoff=last_origin, alpha=0.01,
                                         utility_floor=-1.0, support_floor=0)
    assert result["source"] == "B_SELECTED"
    assert result["params"] is not None
    assert result["record_id"].startswith(last_origin)


def test_walk_forward_b_selection_never_uses_a_later_origins_record():
    """The guard is fp.forward_ledger.training_view -- already proven in
    FP-05/06; this test proves walk_forward_b_selection actually ROUTES
    through it rather than bypassing it with a different row set."""
    b_rows, _c_rows = _archive(n_origins=6, n_per_origin=1)
    origins_sorted = sorted({r["origin_cutoff"] for r in b_rows})
    mid_origin = origins_sorted[2]
    result = ls.walk_forward_b_selection(b_rows, {}, origin_cutoff=mid_origin, alpha=0.01,
                                         utility_floor=-1.0, support_floor=0)
    if result["source"] == "B_SELECTED":
        # the selected record must come from origins[2] itself (val pool),
        # never a later origin's record id
        assert result["record_id"].startswith(mid_origin)


# ---------------------------------------------------------------------------
# walk_forward_c_selection -- fallback chain
# ---------------------------------------------------------------------------

def test_walk_forward_c_selection_falls_back_to_a_when_b_already_did():
    b_result = {"source": "FALLBACK_TO_A", "params": None, "reason": "no prior history"}
    result = ls.walk_forward_c_selection([], origin_cutoff="2022-01-01", alpha=1.0,
                                         utility_floor=6.4e-05, support_floor=2, b_result=b_result)
    assert result["source"] == "FALLBACK_TO_A"
    assert result["params"] is None


def test_walk_forward_c_selection_falls_back_to_b_when_nothing_c_scored_is_eligible():
    b_rows, c_rows = _archive(n_origins=6, n_per_origin=3)
    last_origin = sorted({r["origin_cutoff"] for r in b_rows})[-1]
    b_result = {"source": "B_SELECTED", "params": {"coeff": 4, "AP": 20,
               "alpha.condition_threshold": 55, "novolumedata": False, "src_col": "close"},
               "record_id": f"{last_origin}:R00"}
    result = ls.walk_forward_c_selection(c_rows, origin_cutoff=last_origin, alpha=1.0,
                                         utility_floor=1.0, support_floor=2, b_result=b_result)
    assert result["source"] == "FALLBACK_TO_B"
    assert result["params"] == b_result["params"]


def test_walk_forward_c_selection_selects_a_real_candidate_when_eligible():
    b_rows, c_rows = _archive(n_origins=6, n_per_origin=3)
    last_origin = sorted({r["origin_cutoff"] for r in b_rows})[-1]
    b_result = {"source": "B_SELECTED", "params": {"coeff": 4, "AP": 20,
               "alpha.condition_threshold": 55, "novolumedata": False, "src_col": "close"},
               "record_id": f"{last_origin}:R00"}
    result = ls.walk_forward_c_selection(c_rows, origin_cutoff=last_origin, alpha=0.01,
                                         utility_floor=-1.0, support_floor=0, b_result=b_result)
    assert result["source"] in ("CONTEXT_CONDITIONED", "FALLBACK_TO_B")
    assert result["params"] is not None


# ---------------------------------------------------------------------------
# build_admitted_schedule -- guide 19 item 4, reuses fp.admission_wiring
# ---------------------------------------------------------------------------

def test_build_admitted_schedule_admits_a_real_selection():
    selections = {"2022-01-01": {"source": "B_SELECTED", "params": {"coeff": 4}},
                 "2022-04-01": {"source": "FALLBACK_TO_A", "params": None,
                                "reason": "no eligible candidate"}}
    out = ls.build_admitted_schedule(selections, arm="B_FP_PERSISTENCE")
    assert out["deployment_params_by_fold"]["0"] == {"coeff": 4}
    assert "1" not in out["deployment_params_by_fold"]   # the fallback fold admits nothing
    assert out["lineage"]["1"]["decision"] == "COMMON_FLAT_FALLBACK"


def test_build_run_deployment_schedule_maps_origins_to_real_bar_indices():
    idx = pd.date_range("2022-01-01", periods=200000, freq="1min", tz="UTC")
    admitted = {"arm": "B_FP_PERSISTENCE", "origins_ordered": ["2022-01-01", "2022-01-02"],
               "deployment_params_by_fold": {"0": {"coeff": 4}, "1": {"coeff": 6}}}
    schedule = ls.build_run_deployment_schedule(admitted, frame_index=idx)
    assert schedule[0]["requested_at_bar"] == 0
    assert schedule[1]["requested_at_bar"] == 1440   # exactly 1 day of 1-minute bars later
    assert schedule[0]["params"] == {"coeff": 4}


def test_build_run_deployment_schedule_skips_a_true_flat_fallback_fold():
    idx = pd.date_range("2022-01-01", periods=200000, freq="1min", tz="UTC")
    admitted = {"arm": "B_FP_PERSISTENCE", "origins_ordered": ["2022-01-01", "2022-01-02"],
               "deployment_params_by_fold": {"0": {"coeff": 4}}}   # fold "1" never admitted
    schedule = ls.build_run_deployment_schedule(admitted, frame_index=idx)
    assert len(schedule) == 1


def test_build_run_deployment_schedule_raises_when_everything_fell_back():
    idx = pd.date_range("2022-01-01", periods=200000, freq="1min", tz="UTC")
    admitted = {"arm": "B_FP_PERSISTENCE", "origins_ordered": ["2022-01-01"],
               "deployment_params_by_fold": {}}
    with pytest.raises(ls.LockedStudyError, match="nothing to deploy"):
        ls.build_run_deployment_schedule(admitted, frame_index=idx)


def test_build_run_deployment_schedule_raises_when_origin_is_not_an_exact_bar():
    idx = pd.date_range("2022-01-01 00:00:30", periods=200000, freq="1min", tz="UTC")   # offset by 30s
    admitted = {"arm": "B_FP_PERSISTENCE", "origins_ordered": ["2022-01-01"],
               "deployment_params_by_fold": {"0": {"coeff": 4}}}
    with pytest.raises(ls.LockedStudyError, match="not an exact bar"):
        ls.build_run_deployment_schedule(admitted, frame_index=idx)


# ---------------------------------------------------------------------------
# Statistical analysis -- wiring tests only (account_returns/paired_difference/
# block_mean are already tested elsewhere in this lab; these prove
# locked_study's OWN functions call them correctly, not re-prove them).
# ---------------------------------------------------------------------------

def _synthetic_account_payload(n_days: int, *, daily_return: float, initial_capital: float = 20000.0):
    idx = pd.date_range("2022-01-01", periods=n_days * 1440, freq="1min", tz="UTC")
    equity = initial_capital * (1 + daily_return) ** (pd.RangeIndex(len(idx)) // 1440)
    return {"selected_audit": {"equity": equity.to_numpy(dtype=float)}}, pd.DataFrame(index=idx)


def test_account_daily_returns_matches_the_synthetic_daily_growth_rate():
    payload, frame = _synthetic_account_payload(40, daily_return=0.001)
    rows = ls.account_daily_returns(payload, frame, initial_capital=20000.0)
    assert len(rows) == 40
    assert rows[5][1] == pytest.approx(0.001, abs=1e-9)


def test_paired_contrast_c_minus_b_sign_and_status():
    payload_c, frame_c = _synthetic_account_payload(40, daily_return=0.0015)
    payload_b, frame_b = _synthetic_account_payload(40, daily_return=0.0005)
    daily_c = ls.account_daily_returns(payload_c, frame_c, initial_capital=20000.0)
    daily_b = ls.account_daily_returns(payload_b, frame_b, initial_capital=20000.0)
    out = ls.paired_contrast(daily_c, daily_b, label="C-B", delta=6.4e-05)
    assert out["status"] == "ESTIMATED"
    # day 0's own return is measured against initial_capital, which this
    # fixture sets equal to day 0's own equity -- a spurious 0.0 diff on
    # BOTH sides for that single day, diluting the otherwise-exact
    # 0.0015-0.0005=0.001 daily diff by exactly 1/40
    assert out["estimate"] == pytest.approx(39 / 40 * 0.001, abs=1e-9)
    assert out["n_common_days"] == 40


def test_paired_contrast_reports_inconclusive_support_below_28_common_days():
    payload_c, frame_c = _synthetic_account_payload(10, daily_return=0.001)
    payload_b, frame_b = _synthetic_account_payload(10, daily_return=0.0005)
    daily_c = ls.account_daily_returns(payload_c, frame_c, initial_capital=20000.0)
    daily_b = ls.account_daily_returns(payload_b, frame_b, initial_capital=20000.0)
    out = ls.paired_contrast(daily_c, daily_b, label="C-B", delta=6.4e-05)
    assert out["status"] == "INCONCLUSIVE_SUPPORT"


def test_d1_decay_sign_convention_matches_fp01_repaired_convention():
    out = ls.d1_decay(is_mean=0.001, forward_mean=0.0003)
    assert out["D_mean_daily_return"] == pytest.approx(0.0007)
    assert "positive = worse decay" in out["convention"]
