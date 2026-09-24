"""fp.d2_continuation -- FP-08's own H1/H2/H3 age-window machinery (guide
10.3/FP08.2), distinct from the OLDER RA-07 90/180/270-day version."""
from __future__ import annotations

import pandas as pd
import pytest

from crypto_regime_lab.fp import d2_continuation as d2


def _daily_series(start: str, n_days: int, *, daily_return: float = 0.0005) -> list:
    dates = pd.date_range(start, periods=n_days, freq="D", tz="UTC")
    return [(d.isoformat(), daily_return) for d in dates]


# ---------------------------------------------------------------------------
# anchors_from_selections
# ---------------------------------------------------------------------------

def test_anchors_from_selections_excludes_fallback_origins():
    selections = {
        "B_FP_PERSISTENCE": {
            "2021-01-01": {"source": "FALLBACK_TO_A", "params": None},
            "2021-04-01": {"source": "B_SELECTED", "params": {"coeff": 4}, "record_id": "r1"},
            "2021-07-01": {"source": "FALLBACK_TO_A", "params": None},
        },
    }
    out = d2.anchors_from_selections(selections, arm="B_FP_PERSISTENCE",
                                     origins_ordered=["2021-01-01", "2021-04-01", "2021-07-01"])
    assert len(out) == 1
    assert out[0]["origin_cutoff"] == "2021-04-01"
    assert out[0]["params"] == {"coeff": 4}


def test_anchors_from_selections_includes_every_origin_for_an_always_admitting_arm():
    selections = {"A_STOCK_CAL": {o: {"source": "A_STOCK_INSTALLED", "params": {"coeff": 1}}
                                  for o in ("2021-01-01", "2021-04-01")}}
    out = d2.anchors_from_selections(selections, arm="A_STOCK_CAL",
                                     origins_ordered=["2021-01-01", "2021-04-01"])
    assert len(out) == 2


def test_anchors_from_selections_excludes_a_null_params_row_even_without_a_fallback_label():
    selections = {"X": {"2021-01-01": {"source": "SOMETHING_ELSE", "params": None}}}
    out = d2.anchors_from_selections(selections, arm="X", origins_ordered=["2021-01-01"])
    assert out == []


# ---------------------------------------------------------------------------
# slice_daily_returns_for_anchor
# ---------------------------------------------------------------------------

def test_slice_daily_returns_for_anchor_keeps_only_bars_at_or_after_ready_at():
    series = _daily_series("2021-01-01", 10)
    sliced = d2.slice_daily_returns_for_anchor(series, ready_at="2021-01-05")
    assert sliced[0][0] == pd.Timestamp("2021-01-05", tz="UTC").isoformat()
    assert len(sliced) == 6


def test_slice_daily_returns_for_anchor_is_the_real_continuation_never_reset():
    """The sliced suffix's own values are byte-identical to the source
    series -- guide FP08.2's 'exact contract/prefix parity', not a
    re-derived approximation."""
    series = _daily_series("2021-01-01", 30, daily_return=0.001234)
    sliced = d2.slice_daily_returns_for_anchor(series, ready_at="2021-01-10")
    source_from_same_point = [row for row in series
                              if pd.Timestamp(row[0], tz="UTC") >= pd.Timestamp("2021-01-10", tz="UTC")]
    assert sliced == source_from_same_point


# ---------------------------------------------------------------------------
# age_windows
# ---------------------------------------------------------------------------

def test_age_windows_uses_28_56_84_day_boundaries_not_the_old_90_day_ones():
    series = _daily_series("2021-01-01", 100)
    windows = d2.age_windows(series, ready_at="2021-01-01")
    assert [w["horizon"] for w in windows] == ["H1", "H2", "H3"]
    h1, h2, h3 = windows
    assert h1["days_required"] == 28
    assert h2["days_required"] == 28
    assert h3["days_required"] == 28
    assert h1["status"] == h2["status"] == h3["status"] == "COMPLETE"


def test_age_windows_h1_starts_at_ready_at_ceil_to_the_next_day():
    series = _daily_series("2021-01-01", 100)
    windows = d2.age_windows(series, ready_at="2021-01-01")
    assert windows[0]["start"] == pd.Timestamp("2021-01-01", tz="UTC").isoformat()
    assert windows[0]["end_exclusive"] == pd.Timestamp("2021-01-29", tz="UTC").isoformat()
    assert windows[1]["start"] == pd.Timestamp("2021-01-29", tz="UTC").isoformat()


def test_age_windows_h3_is_censored_when_the_series_ends_before_84_days():
    series = _daily_series("2021-01-01", 60)   # covers H1+H2 fully, H3 not at all
    windows = d2.age_windows(series, ready_at="2021-01-01")
    by_name = {w["horizon"]: w for w in windows}
    assert by_name["H1"]["status"] == "COMPLETE"
    assert by_name["H2"]["status"] == "COMPLETE"
    assert by_name["H3"]["status"] == "CENSORED"
    assert by_name["H3"]["metrics"] is None
    assert by_name["H3"]["days_available"] < by_name["H3"]["days_required"]


def test_age_windows_h1_itself_censored_when_barely_any_follow_up_exists():
    series = _daily_series("2021-01-01", 5)
    windows = d2.age_windows(series, ready_at="2021-01-01")
    assert windows[0]["status"] == "CENSORED"
    assert windows[0]["days_available"] == 5


def test_age_windows_raises_on_a_naive_ready_at_missing_tz_handling_is_internal():
    # ready_at is always passed as a plain date string in this codebase;
    # confirm it does not silently misinterpret an already-qualified one.
    series = _daily_series("2021-01-01", 30)
    with pytest.raises(Exception):
        d2.age_windows(series, ready_at=pd.Timestamp("2021-01-01", tz="UTC"))


# ---------------------------------------------------------------------------
# signed_decline
# ---------------------------------------------------------------------------

def test_signed_decline_h1_minus_later_positive_when_decaying():
    series = ([(d.isoformat(), 0.002) for d in pd.date_range("2021-01-01", periods=28, freq="D", tz="UTC")]
             + [(d.isoformat(), 0.0005)
               for d in pd.date_range("2021-01-29", periods=56, freq="D", tz="UTC")])
    windows = d2.age_windows(series, ready_at="2021-01-01")
    decline = d2.signed_decline(windows)
    assert decline["H1_minus_H2"]["value"] == pytest.approx(0.002 - 0.0005, abs=1e-9)
    assert decline["H1_minus_H2"]["value"] > 0
    assert decline["H1_minus_H3"]["value"] > 0


def test_signed_decline_is_null_with_a_reason_when_a_side_is_censored():
    series = _daily_series("2021-01-01", 40)   # H2/H3 censored
    windows = d2.age_windows(series, ready_at="2021-01-01")
    decline = d2.signed_decline(windows)
    assert decline["H1_minus_H2"]["value"] is None
    assert "CENSORED" in decline["H1_minus_H2"]["reason"]


def test_signed_decline_raises_when_not_exactly_the_three_registered_windows():
    with pytest.raises(d2.D2Error):
        d2.signed_decline([{"horizon": "H1", "status": "COMPLETE", "metrics": {"mean_daily_return": 0.}}])


# ---------------------------------------------------------------------------
# build_d2_record
# ---------------------------------------------------------------------------

def test_build_d2_record_integration_fully_complete():
    series = _daily_series("2021-01-01", 100)
    record = d2.build_d2_record(arm="A_STOCK_CAL", origin_cutoff="2021-01-01",
                                params={"coeff": 1}, daily_returns=series)
    assert record["fully_complete"] is True
    assert record["censored_horizons"] == []
    assert record["exposure"]["status"] == "NOT_COMPUTED"
    assert record["context_at_ready"]["status"] == "NOT_COMPUTED"
    assert record["standardized_state_cohort"]["status"] == "NOT_APPLICABLE"


def test_build_d2_record_integration_partially_censored():
    series = _daily_series("2021-01-01", 40)
    record = d2.build_d2_record(arm="B_FP_PERSISTENCE", origin_cutoff="2021-01-01",
                                params={"coeff": 4}, daily_returns=series)
    assert record["fully_complete"] is False
    assert set(record["censored_horizons"]) == {"H2", "H3"}


def test_build_d2_record_accepts_real_exposure_and_context_when_supplied():
    series = _daily_series("2021-01-01", 100)
    record = d2.build_d2_record(arm="A_STOCK_CAL", origin_cutoff="2021-01-01",
                                params={"coeff": 1}, daily_returns=series,
                                exposure={"status": "OK", "fill_count": 12},
                                context={"ctx_direction_efficiency": 0.3})
    assert record["exposure"] == {"status": "OK", "fill_count": 12}
    assert record["context_at_ready"] == {"ctx_direction_efficiency": 0.3}
