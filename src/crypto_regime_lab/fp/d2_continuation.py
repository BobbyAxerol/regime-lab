"""FP-08 D2 -- frozen-parameter age curve (guide section 10.3 / FP08.2).

Guide 10.3 freezes H1=age 0-28 days, H2=28-56 days, H3=56-84 days for the
SAME already-selected params, run as ONE continuous continuation per anchor
("Chay mot continuation lien tuc cho anchor neu contract cho phep... khong
reset moi age window" -- never reset at an age boundary).

This lab already has D1/D2/D3 machinery from the EARLIER regime_time_edge_ra_v1
study (time_edge/decay.py, ra/ra07_decay.py) -- reused here only for its
STATISTICAL PRIMITIVE (time_edge.metrics.describe, applied per window,
verbatim) and its structural discipline (complete-day contract, anchor
eligibility before outcome). NOT reused verbatim as a whole: that module's
own age_windows() hardcodes 90/180/270-day quarters, the OLDER guide's own
registered contract -- silently applying those boundaries here would apply
the WRONG guide's numbers to FP-GUIDE-1.0's explicitly different 28/56/84
freeze. A second, FP-08-owned function with FP-GUIDE-1.0's own boundaries
is the guide-correct choice, not a duplicate for its own sake.

Guide FP08.2's "Tai dung first-horizon path neu exact contract/prefix
parity": for cell 1 (A-SC/BTCUSDT), FP-07's own three continuous accounts
already cover every origin's own frozen-params segment, uninterrupted,
through the account's own end (2023-12-31) -- slicing an anchor's own
daily-return suffix from that account IS the real continuation the frozen
params would have produced standalone (guide 11.2: a valid historical
origin/evaluation is computed once), so D2 for cell 1 costs ZERO new
engine calls. A cell with no already-computed continuous account (a new
replication cell) has no such shortcut.
"""
from __future__ import annotations

H_BOUNDARIES = (("H1", 0, 28), ("H2", 28, 56), ("H3", 56, 84))
FOLLOWUP_DAYS_REQUIRED = 84   # H3's own end -- guide 10.3's full H1..H3 span

FALLBACK_SOURCES = ("FALLBACK_TO_A", "FALLBACK_TO_B")


class D2Error(ValueError):
    """A D2 continuation/anchor construction step was internally inconsistent."""


def anchors_from_selections(selections_by_origin: dict, *, arm: str,
                            origins_ordered: list[str]) -> list[dict]:
    """Guide FP08.2 item 1: anchors chosen by TIMESTAMP/ELIGIBILITY before
    any outcome is known. Every origin where ``arm`` admitted a REAL new
    selection is a candidate anchor -- a FALLBACK_TO_* origin carries no
    params of its own to freeze and is never one (guide's own 'no borrowed
    Arm A value' semantics, fp.locked_study). Never chosen by which
    anchor's OWN decay looks good (guide 10.3: 'Khong chon anchors vi nhin
    thay decay dep')."""
    out = []
    for origin in origins_ordered:
        sel = selections_by_origin[arm].get(origin)
        if sel is None:
            continue
        if sel.get("source") in FALLBACK_SOURCES:
            continue
        if not sel.get("params"):
            continue
        out.append({"origin_cutoff": origin, "arm": arm, "params": sel["params"],
                   "source": sel["source"], "record_id": sel.get("record_id")})
    return out


def slice_daily_returns_for_anchor(daily_returns: list, *, ready_at: str) -> list:
    """Guide FP08.2: reuse the first-horizon path under exact prefix
    parity. ``daily_returns`` is the arm's OWN already-computed continuous
    account (e.g. fp.locked_study.account_daily_returns); the account
    never resets at this boundary (one continuous chronological run), so
    this suffix IS the real continuation those frozen params would have
    produced standalone."""
    import pandas as pd

    ready = pd.Timestamp(ready_at, tz="UTC")
    return [(d, v) for d, v in daily_returns if pd.Timestamp(d, tz="UTC") >= ready]


def age_windows(daily_returns: list, *, ready_at: str) -> list[dict]:
    """Guide 10.3: H1/H2/H3 at 28/56/84 days from ``ready_at``, complete
    UTC days only. A window whose calendar range runs past the end of
    ``daily_returns`` is CENSORED (guide FP08.2: 'Giu censoring khi
    follow-up thieu') -- never padded, never dropped silently."""
    import pandas as pd

    from ..time_edge.metrics import describe

    ready = pd.Timestamp(ready_at, tz="UTC")
    start = ready.ceil("D")
    by_date = {pd.Timestamp(d, tz="UTC"): v for d, v in daily_returns}
    rows = []
    for name, left, right in H_BOUNDARIES:
        lo, hi = start + pd.Timedelta(days=left), start + pd.Timedelta(days=right)
        expected = pd.date_range(lo, hi, inclusive="left", freq="D")
        sample = [(d.isoformat(), by_date[d]) for d in expected if d in by_date]
        row = {"horizon": name, "start": lo.isoformat(), "end_exclusive": hi.isoformat(),
              "ready_at": ready.isoformat(), "days_available": len(sample),
              "days_required": len(expected)}
        if len(sample) < len(expected):
            rows.append({**row, "status": "CENSORED", "metrics": None, "daily_returns": None})
            continue
        rows.append({**row, "status": "COMPLETE", "metrics": describe(sample),
                    "daily_returns": sample})
    return rows


def signed_decline(windows: list[dict]) -> dict:
    """Guide 10.3's own required 'Signed decline H1->H2/H3', reusing D1's
    established sign convention (guide 8.5/FP-01): earlier-minus-later,
    positive = worse decay as the parameter ages. Null with a reason where
    either side is CENSORED -- never computed from a fabricated value."""
    by_name = {w["horizon"]: w for w in windows}
    if set(by_name) != {"H1", "H2", "H3"}:
        raise D2Error("three registered age windows (H1/H2/H3) required")
    out = {}
    for later_name in ("H2", "H3"):
        key = f"H1_minus_{later_name}"
        h1, later = by_name["H1"], by_name[later_name]
        if h1["status"] != "COMPLETE" or later["status"] != "COMPLETE":
            out[key] = {"value": None,
                       "reason": f"H1 or {later_name} is CENSORED -- signed decline not computable"}
            continue
        out[key] = {
            "value": h1["metrics"]["mean_daily_return"] - later["metrics"]["mean_daily_return"],
            "convention": "H1 - later; positive = worse decay as age increases (D1's own sign "
                          "convention, guide 8.5/FP-01, applied here to D2)"}
    return out


def build_d2_record(*, arm: str, origin_cutoff: str, params: dict, daily_returns: list,
                    exposure: dict | None = None, context: dict | None = None) -> dict:
    """One anchor's full D2 record: age windows, signed decline, and the
    guide's other required reporting items (exposure/context; guide 10.3's
    'Performance tung age window / Signed decline / Exposure.../ Regime,
    context thuc te / Censoring...'). ``exposure``/``context`` are optional
    because they need the arm's own raw fills/IS-frame, not just daily
    returns -- callers without them still get the required decay numbers,
    disclosed as such."""
    suffix = slice_daily_returns_for_anchor(daily_returns, ready_at=origin_cutoff)
    windows = age_windows(suffix, ready_at=origin_cutoff)
    decline = signed_decline(windows)
    censored = [w["horizon"] for w in windows if w["status"] == "CENSORED"]
    return {
        "arm": arm, "origin_cutoff": origin_cutoff, "params": params,
        "age_windows": windows, "signed_decline": decline,
        "censored_horizons": censored, "fully_complete": not censored,
        "exposure": exposure if exposure is not None else
                   {"status": "NOT_COMPUTED", "reason": "no raw fills supplied for this record"},
        "context_at_ready": context if context is not None else
                            {"status": "NOT_COMPUTED", "reason": "no IS frame supplied for this record"},
        "standardized_state_cohort": {
            "status": "NOT_APPLICABLE",
            "reason": "JM/M0 calibration-vintage state is not used in this study (FP-06's own "
                     "disclosed choice: LAB-08 measured only 1.64% JM/M0 support) -- there is no "
                     "standardized-state cohort concept to compare the actual cohort against",
        },
    }
