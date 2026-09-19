"""RA06.4: origin selection, disclosed and outcome-blind (guide section 10.4).

A pure calendar grid -- one of the two rules guide 10.4 explicitly sanctions
("mot grid/calendar hoac union cac causal eligible requests da dinh truoc").
Chosen BEFORE any branch has run, spaced evenly, with the incumbent (the
window_start selection) given room to accumulate real track record before
the first origin -- an origin AT window_start itself would make KEEP and
REFIT identical by construction (both would just repeat the same initial
search), which is not a real test of the refit decision.
"""
from __future__ import annotations

import pandas as pd

#: Feasibility-pilot count, reduced from guide 10.3's "8-12 if budget
#: allows" ceiling -- guide's own explicit fallback ("neu khong co budget
#: tao Panel B du support, implement/test panel pipeline, giu scientific
#: INCONCLUSIVE_SUPPORT") is invoked deliberately here, disclosed, not
#: silently. Each origin costs one full real 8-trial REFIT search plus real
#: execution through the horizon; 5 was chosen to keep total real compute
#: for this phase in the same order as RA-05's, not because 5 is special.
ORIGIN_COUNT = 5
ORIGIN_SPACING_DAYS = 20


def select_origins(window_start: str, *, count: int = ORIGIN_COUNT,
                   spacing_days: int = ORIGIN_SPACING_DAYS) -> list[str]:
    """`count` calendar points, `spacing_days` apart, starting one spacing
    interval AFTER window_start (never at window_start itself)."""
    start = pd.Timestamp(window_start, tz="UTC")
    return [(start + pd.Timedelta(days=spacing_days * (i + 1))).isoformat()
           for i in range(count)]


def origin_registration(window_start: str, horizon_days: int, *, count: int = ORIGIN_COUNT,
                        spacing_days: int = ORIGIN_SPACING_DAYS) -> dict:
    origins = select_origins(window_start, count=count, spacing_days=spacing_days)
    last_needed = pd.Timestamp(origins[-1]) + pd.Timedelta(days=horizon_days)
    return {
        "schema": "regime_lab.ra06_origins.v1",
        "rule": ("pure calendar grid: window_start + spacing_days*(i+1) for i in "
                f"range({count}), spacing_days={spacing_days} -- chosen before any branch ran, "
                "never adjusted after seeing an outcome"),
        "window_start": window_start,
        "origin_count": count,
        "spacing_days": spacing_days,
        "origins": origins,
        "horizon_days": horizon_days,
        "data_needed_through": last_needed.isoformat(),
        "excludes_window_start_itself": True,
        "exclusion_reason": ("an origin at window_start would make KEEP and REFIT identical by "
                             "construction (both repeat the same initial search) -- not a real "
                             "test of the refit decision"),
    }
