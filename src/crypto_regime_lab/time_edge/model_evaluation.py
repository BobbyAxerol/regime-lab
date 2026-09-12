"""Evaluate the ACTUALLY emitted model on later, mature candidate utility labels."""
import numpy as np
import pandas as pd

from ..experiments.time_edge_contracts import ContractError
from .model import _states, information, target_rows
from .storage import digest


def evaluate_vintages(vintages, features, targets, emissions, *, end):
    ordered=sorted(vintages,key=lambda v:v["ready_at"]); rows=[]; models=[]
    by_model={}
    for emission in emissions: by_model.setdefault(emission["model_id"],[]).append(emission)
    for i,vintage in enumerate(ordered):
        cutoff=pd.Timestamp(vintage["cutoff"]); ready=pd.Timestamp(vintage["ready_at"])
        until=pd.Timestamp(ordered[i+1]["ready_at"]) if i+1 < len(ordered) else pd.Timestamp(end)
        history=features.loc[(features.index >= pd.Timestamp(vintage["history_start"])) & (features.index < cutoff),vintage["feature_names"]]
        history=history.loc[np.isfinite(history.to_numpy()).all(axis=1)]
        raw=history.to_numpy(float)
        if digest(raw.tolist()) != vintage["training_raw_hash"]:
            raise ContractError("model information training features differ from deployed vintage")
        scaler={**vintage["scaler"],"median":np.asarray(vintage["scaler"]["median"]),"scale":np.asarray(vintage["scaler"]["scale"])}
        fit=dict(vintage["fit"])
        if "centroids" in fit: fit["centroids"]=np.asarray(fit["centroids"])
        train_states=_states(raw,scaler,fit,vintage["design"],np.asarray(vintage["weights"]))
        training=target_rows(targets,before=cutoff.isoformat(),origin_start=history.index[0],origin_end=cutoff)
        validation=target_rows(targets,before=end,origin_start=ready,origin_end=until)
        tape=by_model.get(vintage["model_id"],[])
        if any(tape[j]["available_at"] >= tape[j+1]["available_at"] for j in range(len(tape)-1)):
            raise ContractError("model evaluation tape availability must be strictly ordered")
        usable=[]; unavailable=[]
        for target in validation:
            available=[e for e in tape if pd.Timestamp(e["available_at"]) <= pd.Timestamp(target["origin"])]
            current=available[-1] if available else None
            if current is None or current["decision_eligible"] is not True or current["quality_status"] != "OK":
                unavailable.append({"origin":target["origin"],"cell_id":target["cell_id"],"effect":None,
                                    "model_id":vintage["model_id"],"reason":"no eligible ACTUAL model emission at target origin"})
            elif current["model_design_hash"] != vintage["model_design_hash"] or current["model_ready_at"] != vintage["ready_at"]:
                raise ContractError("deployed model/emission identity mismatch")
            else: usable.append(target)
        valid_tape=[e for e in tape if e["decision_eligible"] and e["quality_status"] == "OK"]
        index=history.index.append(pd.DatetimeIndex(pd.to_datetime([e["available_at"] for e in valid_tape],utc=True)))
        states=np.r_[train_states,[e["state_id"] for e in valid_tape]].astype(int)
        scored=information(training,usable,index,states)
        for row in scored["rows"]: row["model_id"]=vintage["model_id"]
        outer=scored["rows"]+unavailable; rows.extend(outer)
        values=[r["effect"] for r in outer if r["effect"] is not None]
        models.append({"model_id":vintage["model_id"],"cutoff":vintage["cutoff"],"ready_at":vintage["ready_at"],
            "design":vintage["design"],"decision":vintage["decision"],"dossier":vintage["dossier"],
            "training_targets":len(training),"planned_outer_targets":len(validation),"evaluable_outer_targets":len(values),
            "mean_outer_information_effect":float(np.mean(values)) if values else None,
            "outer_information_ci":None,"ci_reason":"per-vintage descriptive; registered inference jointly resamples calendar episodes across vintages",
            "outer_rows":outer})
    return {"model_table":models,"information_rows":rows,"scope":"deployed model -> later completed candidate utility, not inner design-selection scores"}


def operational_folds(account, emissions, model_lookup):
    selections=sorted(account.get("selections",[]),key=lambda r:r["cutoff"])
    result=[]
    from .metrics import describe
    for i,selection in enumerate(selections):
        start=max(pd.Timestamp(account["score_start"]),pd.Timestamp(selection["cutoff"]))
        end=min(pd.Timestamp(account["score_end_exclusive"]),pd.Timestamp(selections[i+1]["cutoff"]) if i+1 < len(selections) else pd.Timestamp(account["score_end_exclusive"]))
        daily=[r for r in account["daily_returns"] if start.ceil("D") <= pd.Timestamp(r[0],tz="UTC") < end.floor("D")]
        tape=[e for e in emissions if start <= pd.Timestamp(e["available_at"]) < end]
        ids=sorted({e["model_id"] for e in tape})
        activation=next((e for e in account.get("funnel",[]) if e["event"] == "ACTIVATE" and e["selection_id"] == selection["selection_id"]),None)
        result.append({"cell_id":account["cell_id"],"arm":account["arm"],"fold_id":i,
            "start":start.isoformat(),"end_exclusive":end.isoformat(),"selection_id":selection["selection_id"],
            "ready_at":selection["ready_at"],"activation":activation,"params":selection["params"],
            "model_at_selection":selection.get("model_id"),"all_model_versions_during_fold":ids,
            "model_reports":[{"model_id":m,"report_anchor":"model_table:"+m,"status":"LINKED" if m in model_lookup else "MISSING_DOSSIER"} for m in ids],
            "emission_count":len(tape),"unknown_count":sum(e["quality_status"] != "OK" for e in tape),
            "metrics":describe(daily) if daily else None,"daily_returns":daily,
            "metric_reason":None if daily else "no complete UTC days in operational interval",
            "interpretation":"operational account can carry incumbent campaigns; not a fixed-theta D1/D2 account"})
    return result
