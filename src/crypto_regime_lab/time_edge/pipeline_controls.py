"""Actual learned-model -> trigger -> public Mode 4 -> QuantBT control path.

Each completed nested stage is immutable/resumable. Structural positive worlds
test opportunity and treatment reach; they do not manufacture a known 2-delta
net learner effect from a price drift. Economic-boundary calibration is separate.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from .controls import generate_world
from .execution import PreparedAccount, select_only
from .model import fit_vintage, emit
from .planning import ref
from .runtime import local
from .schedule import calendar, triggers
from .storage import read, save, digest
from ..experiments.time_edge_contracts import ContractError, paired_difference

CANONICAL_WORLDS=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","DOGEUSDT")


def full_control(root, request):
    from .workers import execute, read_market, candidate_targets, export_account
    root=Path(root); task=request["task"]; directory=local(root,request["task_evidence"])
    alpha=task["alpha_id"]; days=int(task.get("days",1461)); seed=int(task["seed"])
    if days < 730: raise ContractError("full control needs registered warmup plus at least 365 evaluation days")
    world=task.get("world")
    if world is not None and world not in CANONICAL_WORLDS:
        raise ContractError("unregistered structural world: "+str(world))
    # All registered context worlds are always generated (they define the
    # point-in-time cross-section); the shard's own world is the market whose
    # targets, selections and accounts the task computes.
    symbols=CANONICAL_WORLDS
    market=world or "BTCUSDT"
    cell=f"{alpha}/{market}"; start="2020-01-01T00:00:00Z"
    end=(pd.Timestamp("2019-01-01",tz="UTC")+pd.Timedelta(days=days)).isoformat()
    inputs={}; counts={"model_fits":0,"searches":0,"deployments":0,"target_accounts":0}
    def once(name, callback):
        path=directory/(name+".json")
        seal=directory/(name+".seal.json")
        if path.exists():
            from .storage import file_digest
            if not seal.exists() or read(seal)["sha256"] != file_digest(path):
                raise ContractError("full-control nested stage drift/incomplete publication")
            return read(path)
        value=callback(); value["lab_run_id"]=request["lab_run_id"]
        h=save(path,value); save(seal,{"lab_run_id":request["lab_run_id"],"sha256":h})
        return value
    def child(name, childtask):
        folder=directory/name; folder.mkdir(parents=True,exist_ok=True)
        return {**request,"task":childtask,"inputs":inputs,"dependencies":{},"task_evidence":str(folder.relative_to(root))}
    for symbol in symbols:
        offset=CANONICAL_WORLDS.index(symbol)
        result=once("world-"+symbol,lambda offset=offset,symbol=symbol:generate_world(root,child("raw-"+symbol,
            {"seed":seed+offset*100003,"condition":task["condition"],"days":days})))
        # Deliberately exclude result['truth'] from all learner inputs.
        inputs[symbol]=result["observable_market"]
    feature_result=once("features",lambda:execute(root,child("feature-artifacts",{
        "task_id":"features","kind":"features","market":market,"markets":{s:s for s in inputs},
        "start":"2019-01-01T00:00:00Z","end":end})))
    features=pd.read_parquet(local(root,feature_result["features"]["path"]))
    binding=read(root/"configs/time_edge_validation_v4/mode4_binding_r01.json")
    protocol=read(root/"configs/time_edge_validation_v4/r01/model_protocol.json")
    latency=int(task["latency_seconds"])
    if latency < 60: raise ContractError("full control needs frozen technical latency")
    def select(cutoff):
        name="search-"+digest(cutoff)[:16]
        folder=directory/name; folder.mkdir(parents=True,exist_ok=True)
        def run():
            from .eligibility import history_start
            lo=pd.Timestamp(history_start(alpha,pd.Timestamp(cutoff)-pd.Timedelta(days=180)))
            frame=read_market(root,inputs[market],start=lo.isoformat(),end=cutoff)
            result=select_only(frame,alpha_id=alpha,cutoff=cutoff,binding=binding,evidence_dir=folder,lab_run_id=request["lab_run_id"])
            if result["status"] != "SELECTED": raise ContractError("control selector has no admissible parameter")
            result.update(selection_id=digest({"cutoff":cutoff,"params":result["params"]}),
                ready_at=(pd.Timestamp(cutoff)+pd.Timedelta(seconds=latency)).isoformat(),model_id=None)
            return result
        result=once(name,run); counts["searches"]+=1
        return result
    from .eligibility import history_start, history_days
    bank_cutoff=max(pd.Timestamp("2019-07-15T00:00:00Z"),pd.Timestamp("2019-01-01T00:00:00Z")+pd.Timedelta(days=180+history_days(alpha)))
    bank_search=select(bank_cutoff.isoformat())
    candidate_map={digest(t["params"]):t["params"] for t in bank_search["trials"] if t.get("objective") is not None and not t.get("pruned")}
    if len(candidate_map) < 2: raise ContractError("control has no parameter opportunity cohort")
    bank_path=directory/"candidate-bank.json"
    save(bank_path,{"lab_run_id":request["lab_run_id"],"available_at":bank_search["ready_at"],
         "candidates":[{"candidate_id":k,"params":v} for k,v in sorted(candidate_map.items())]})
    inputs["bank"]=ref(root,bank_path)
    targets=[]
    for origin in calendar((bank_cutoff+pd.Timedelta(days=1)).isoformat(),end,28):
        outcome=pd.Timestamp(origin)+pd.Timedelta(days=28)
        if outcome >= pd.Timestamp(end): break
        name="targets-"+digest(origin)[:16]
        result=once(name,lambda origin=origin,outcome=outcome,name=name:candidate_targets(root,child(name+"-artifacts",{
            "origin":origin,"end":outcome.isoformat(),"history_start":history_start(alpha,origin),
            "candidate_bank":"bank","market":market,"alpha_id":alpha,"cell_id":cell})))
        targets.extend(result["targets"]); counts["target_accounts"]+=len(candidate_map)
    vintages=[]; previous=None
    for cutoff in calendar(start,end,28):
        name="model-"+digest(cutoff)[:16]
        ready=(pd.Timestamp(cutoff)+pd.Timedelta(seconds=latency)).isoformat()
        vintage=once(name,lambda cutoff=cutoff,ready=ready,previous=previous:fit_vintage(
            features,targets,cutoff=cutoff,ready_at=ready,protocol=protocol,previous=previous))
        vintages.append(vintage); previous=vintage; counts["model_fits"]+=1
    tape=[]
    for i,vintage in enumerate(vintages):
        until=vintages[i+1]["ready_at"] if i+1 < len(vintages) else end
        tape.extend(emit(vintage,features,until=until))
    control=triggers(tape,initial_ready=start,end=end)
    initial=select("2019-12-31T00:00:00Z")
    accounts={}
    schedules={"M4_CAL":calendar("2020-06-29T00:00:00Z",end,180),
               "M4_REGIME":[r["cutoff"] for r in control["triggers"]]}
    for arm,cutoffs in schedules.items():
        selections=[initial]+[select(c) for c in cutoffs]
        def deploy(arm=arm,selections=selections):
            frame=read_market(root,inputs[market],start=history_start(alpha,start),end=end)
            run=PreparedAccount(frame).run(alpha,selections,account_start=start)
            return export_account(root,str((directory/arm).relative_to(root)),run,start=start,end=end,
                                  lab_run_id=request["lab_run_id"],selections=selections,cell_id=cell,arm=arm)
        accounts[arm]=once("deployment-"+arm,deploy); counts["deployments"]+=1
    pair=paired_difference(accounts["M4_REGIME"]["daily_returns"],accounts["M4_CAL"]["daily_returns"])
    parameter_count=len({digest(s["params"]) for s in accounts["M4_REGIME"]["selections"]})
    return {"status":"FULL_PATH_STRUCTURAL_CONTROL_COMPLETED","condition":task["condition"],"seed":seed,
        "cell_id":cell,"counts":counts,"model_ids":[v["model_id"] for v in vintages],
        "model_decisions":[v["decision"] for v in vintages],"eligible_emissions":sum(r["decision_eligible"] for r in tape),
        "emissions_in_window":len(tape),
        "triggers":len(control["triggers"]),"distinct_regime_parameters":parameter_count,
        "activations":sum(r["event"] == "ACTIVATE" for r in accounts["M4_REGIME"]["funnel"]),
        "regime_commands":len(accounts["M4_REGIME"]["commands"]),"calendar_commands":len(accounts["M4_CAL"]["commands"]),
        "paired_mean_daily_effect":float(np.mean(pair["values"])),"paired_daily_returns":list(zip(pair["dates"],pair["values"])),
        "truth_entered_learner":False,"learner_input_keys":list(inputs),
        "world":world,"worlds_executed":list(symbols),
        "boundary_power_qualification":"NOT_EVALUABLE_FROM_STRUCTURAL_WORLD_ALONE",
        "reason":"known opportunity is not known net learner effect=2delta; do not certify registered boundary power from these worlds"}
