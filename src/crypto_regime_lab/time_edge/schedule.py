"""Causal regime triggers and explicit four-clock selection/activation lineage."""
from dataclasses import dataclass
from datetime import timedelta
from .storage import digest
from ..experiments.time_edge_contracts import ContractError, utc


@dataclass(frozen=True)
class Selection:
    selection_id: str
    cutoff: str
    ready_at: str
    params: dict
    model_id: str
    def validate(self):
        if utc(self.ready_at) < utc(self.cutoff) or not self.params:
            raise ContractError("selection must be ready after cutoff and have parameters")


def triggers(emissions, *, initial_ready, end, min_gap_days=28, max_age_days=180,
             confirmations=2, budget=None):
    initial, limit = utc(initial_ready), utc(end)
    if initial >= limit or min_gap_days < 0 or max_age_days <= 0 or confirmations < 1:
        raise ContractError("invalid controller registration")
    previous_time = None
    accepted = None
    pending = None
    repeats = 0
    last_search = initial
    rows, rejected = [], []
    for record in emissions:
        moment = utc(record["available_at"])
        if previous_time is not None and moment <= previous_time:
            raise ContractError("emissions must have strictly ordered availability")
        previous_time = moment
        if moment < initial or moment >= limit:
            continue
        required = ("model_id","model_ready_at","model_fit_cutoff","state_namespace","state_id",
                    "decision_eligible","quality_status","feature_schema_hash","model_design_hash")
        if any(k not in record for k in required):
            pending, repeats = None, 0
            rejected.append({"at":moment.isoformat(),"reason":"MISSING_ELIGIBILITY_OR_LINEAGE"});continue
        if (record["decision_eligible"] is not True or record["quality_status"] != "OK"
                or utc(record["model_ready_at"]) > moment or utc(record["model_fit_cutoff"]) > utc(record["model_ready_at"])):
            pending, repeats = None, 0
            rejected.append({"at":moment.isoformat(),"reason":"INELIGIBLE_OR_NOT_READY"});continue
        common = record.get("state_common")
        key = (record.get("state_common_namespace","common"),common) if common is not None else (record["state_namespace"],record["state_id"])
        if key == pending:
            repeats += 1
        else:
            pending, repeats = key, 1
        if accepted is None:
            accepted = key
        comparable = key[0] == accepted[0]
        changed = comparable and key != accepted and repeats >= confirmations
        if not comparable:  # model relabel alone cannot cause a market transition
            accepted = key
        due = moment-last_search >= timedelta(days=max_age_days)
        gap_ok = moment-last_search >= timedelta(days=min_gap_days)
        if gap_ok and (changed or due) and (budget is None or len(rows) < budget):
            rows.append({"cutoff":moment.isoformat(),"reason":"STATE_CHANGE" if changed else "MAX_AGE",
                         "model_id":record["model_id"],"model_design_hash":record["model_design_hash"],
                         "state_key":list(key),"observation_id":record.get("observation_id",digest(record))})
            last_search = moment
            accepted = key
    return {"triggers":rows,"rejected":rejected,"initial_age_clock":initial.isoformat()}


def calendar(start, end, days):
    moment, limit = utc(start), utc(end)
    if days <= 0 or moment >= limit:
        raise ContractError("invalid calendar interval")
    result = []
    while moment < limit:
        result.append(moment.isoformat()); moment += timedelta(days=days)
    return result


def matched_cadence(predicted_regime_work, per_selection_work, *, days, menu=(28,56,90,180)):
    """Inputs come from pre-evaluation training/profile, never realized future counts."""
    import math
    if any(not math.isfinite(x) or x <= 0 for x in (predicted_regime_work,per_selection_work,days)) or any(d <= 0 for d in menu):
        raise ContractError("positive training-only work estimates required")
    options = [(abs(math.ceil(days/d)*per_selection_work-predicted_regime_work),-d,d) for d in menu]
    return min(options)[2]
