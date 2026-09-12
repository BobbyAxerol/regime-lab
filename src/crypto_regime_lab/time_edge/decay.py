"""Fixed-theta age accounts and calendar-aligned decay contrasts.

Operational fold changes (D3) stay descriptive. D2 is an adjusted association:
calendar/context matching does not randomize the age of a selected parameter.
"""
import numpy as np
import pandas as pd

from ..experiments.time_edge_contracts import ContractError, pf_log_gap
from .metrics import describe


def anchors(selections, *, end, maximum=12):
    chosen = {}; rejected = []
    for row in sorted(selections,key=lambda r:(r["ready_at"],r["selection_id"])):
        ready = pd.Timestamp(row["ready_at"])
        if ready.tz is None:
            raise ContractError("UTC selection-ready clock required")
        if row.get("status") != "SELECTED" or not row.get("params"):
            rejected.append({"selection_id":row["selection_id"],"reason":"not an actual eligible selection"}); continue
        if ready.ceil("D") + pd.Timedelta(days=270) > pd.Timestamp(end):
            rejected.append({"selection_id":row["selection_id"],"reason":"incomplete 270-day follow-up"}); continue
        key=(row["cell_id"],row["arm"],ready.year,(ready.month-1)//3+1)
        if key not in chosen:
            chosen[key]=dict(row,quarter=f"{ready.year}Q{(ready.month-1)//3+1}")
    counts={}; result=[]
    for key,row in sorted(chosen.items(),key=lambda item:item[1]["ready_at"]):
        cellarm=key[:2]; counts[cellarm]=counts.get(cellarm,0)+1
        if counts[cellarm] <= maximum: result.append(row)
    return {"anchors":result,"rejected":rejected,"outcome_values_read":False}


def age_windows(returns, *, ready_at):
    # Daily statistic uses complete UTC days after ready. Preserve exact clock and
    # report discarded partial head rather than silently treating it as 90 days.
    ready=pd.Timestamp(ready_at); start=ready.ceil("D")
    rows=[]
    for left,right in ((0,90),(90,180),(180,270)):
        lo=start+pd.Timedelta(days=left); hi=start+pd.Timedelta(days=right)
        sample=[r for r in returns if lo <= pd.Timestamp(r[0],tz="UTC") < hi]
        expected=pd.date_range(lo,hi,inclusive="left",freq="D")
        actual=pd.to_datetime([r[0] for r in sample],utc=True)
        if not actual.equals(expected):
            raise ContractError("fixed-theta age account lacks 90 complete consecutive UTC days")
        rows.append({"horizon":f"H{left//90+1}","start":lo.isoformat(),"end_exclusive":hi.isoformat(),
                     "ready_at":ready.isoformat(),"daily_alignment_delay_seconds":(start-ready).total_seconds(),
                     "metrics":describe(sample),"daily_returns":sample})
    return rows


def d1(selected_is, fixed_oos):
    left,right=describe(selected_is),describe(fixed_oos)
    a,b=left["daily_sharpe"]["value"],right["daily_sharpe"]["value"]
    return {"raw_is":left,"fixed_theta_oos":right,
            "mean_return_gap":left["mean_daily_return"]-right["mean_daily_return"],
            "sharpe_gap":None if a is None or b is None else a-b,
            "pf_log_gap":pf_log_gap(left["daily_observation_pf"]["value"],right["daily_observation_pf"]["value"]),
            "limitation":"selected IS is selection-biased; OOS is a separate fixed-theta diagnostic account"}


def matched_decay(accounts):
    groups={}
    for record in accounts:
        for field in ("cell_id","arm","quarter","context_key","selection_id","ready_at","age_windows"):
            if field not in record: raise ContractError("decay record missing "+field)
        key=(record["cell_id"],record["quarter"],record["context_key"])
        arm=record["arm"]
        if arm in groups.setdefault(key,{}): raise ContractError("duplicate anchor in fixed decay stratum")
        groups[key][arm]=record
    matched=[]; unmatched=[]
    for key,pair in sorted(groups.items()):
        if not {"M4_CAL","M4_REGIME"} <= set(pair):
            unmatched.append({"stratum":list(key),"reason":"no common calendar/context support"});continue
        a,b=pair["M4_CAL"],pair["M4_REGIME"]
        if abs((pd.Timestamp(a["ready_at"])-pd.Timestamp(b["ready_at"])).total_seconds()) > 28*86400:
            unmatched.append({"stratum":list(key),"reason":"anchor readiness differs by more than 28 days"});continue
        matched.append((key,a,b))
    if not matched:
        return {"status":"NOT_EVALUABLE","effect":None,"reason":"no matched decay strata","unmatched":unmatched}
    daily={}; strata=[]
    for key,a,b in matched:
        contribution=0.
        for record,sign in ((a,1.),(b,-1.)):
            horizons=record["age_windows"]
            if [h["horizon"] for h in horizons] != ["H1","H2","H3"]:
                raise ContractError("three registered fixed-theta age windows required")
            for horizon,age_sign in ((horizons[0],1.),(horizons[2],-1.)):
                rows=horizon["daily_returns"]
                if len(rows) != 90: raise ContractError("decay horizon must contain 90 days")
                for date,value in rows:
                    weight=sign*age_sign/(90*len(matched))
                    daily[date]=daily.get(date,0.)+weight*value
                    contribution += sign*age_sign*value/90
        strata.append({"stratum":list(key),"calendar_selection":a["selection_id"],"regime_selection":b["selection_id"],"effect":contribution})
    dates=pd.date_range(min(daily),max(daily),freq="D",tz="UTC")
    # Zero here means no anchor contribution on a calendar date, NOT a missing
    # account return. Every contributing age account was checked complete above.
    influence=[len(dates)*daily.get(d.date().isoformat(),0.) for d in dates]
    return {"status":"ESTIMATED_ASSOCIATION", "effect":float(np.mean(influence)),
            "calendar_influence":[(d.date().isoformat(),v) for d,v in zip(dates,influence)],
            "matched_strata":strata,"unmatched":unmatched,"inference_unit":"joint calendar blocks across overlapping anchors",
            "limitation":"matched age/calendar/context association, not randomized causal parameter decay"}


def d3(folds):
    rows=[]
    for previous,current in zip(folds[:-1],folds[1:]):
        if current["start"] < previous["end_exclusive"]:
            raise ContractError("operational folds overlap")
        a,b=describe(previous["daily_returns"]),describe(current["daily_returns"])
        rows.append({"previous":previous["fold_id"],"current":current["fold_id"],
                     "next_minus_previous_mean":b["mean_daily_return"]-a["mean_daily_return"],
                     "previous_params":previous["params"],"current_params":current["params"],
                     "status":"DESCRIPTIVE_MIXED_CALENDAR_PARAMETER_EFFECT"})
    return rows
