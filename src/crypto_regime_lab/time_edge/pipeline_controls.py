"""Actual learned-model -> trigger -> public Mode 4 -> QuantBT control path.

Each completed nested stage is immutable/resumable. Structural positive worlds
test opportunity and treatment reach; they do not manufacture a known 2-delta
net learner effect from a price drift. Economic-boundary calibration is separate.

Nested stages publish into an identity-keyed compute cache: identical world,
target, selection, feature or fit identities are reused byte-for-byte instead of
being recomputed, while condition/world/cutoff/economics/contract facets stay in
the key so no artifact can be reused across a changed identity.
"""
from pathlib import Path
import os

import numpy as np
import pandas as pd

from .compute_cache import ComputeCache, code_contract, engine_contract
from .controls import generate_world
from .execution import PreparedAccount, CONTRACT, select_only
from .model import fit_vintage, emit
from .planning import ref
from .runtime import local
from .schedule import calendar, triggers
from .storage import read, save, digest, file_digest
from ..experiments.time_edge_contracts import ContractError, paired_difference

CANONICAL_WORLDS=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","DOGEUSDT")
CONFIG_BINDING="configs/time_edge_validation_v4/mode4_binding_r01.json"
CONFIG_PROTOCOL="configs/time_edge_validation_v4/r01/model_protocol.json"


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
    cache=ComputeCache(root,"controls")
    cache_ledger=[]
    contract={kind:code_contract(root,kind) for kind in ("world","targets","search","fit","features","deployment")}
    engine=engine_contract(root)
    binding_sha=file_digest(root/CONFIG_BINDING); protocol_sha=file_digest(root/CONFIG_PROTOCOL)
    protocol=read(root/CONFIG_PROTOCOL); binding=read(root/CONFIG_BINDING)
    def variant(symbol):
        offset=CANONICAL_WORLDS.index(symbol)
        return seed+offset*100003
    def world_facets(symbol):
        return {"generator":"te_worldgen_v1","contract":contract["world"],
                "seed":variant(symbol),"condition":task["condition"],"days":days,"symbol":symbol}
    def materialize_world(symbol,result):
        """Link a cached observable market instead of regenerating 131 MB of rows."""
        producer=read(local(root,result["observable_market"]["path"]))
        partition=producer["partitions"][0]
        raw=local(root,str(Path(request["task_evidence"])/("raw-"+symbol)))
        raw.mkdir(parents=True,exist_ok=True)
        linked=raw/"observable_market.parquet"
        source=local(root,partition["path"])
        if file_digest(source) != partition["sha256"]:
            raise ContractError("cached world parquet hash drift: "+partition["path"])
        if linked.exists():
            if file_digest(linked) != partition["sha256"]:
                raise ContractError("linked world parquet drift; use a new task identity")
        else:
            os.link(source,linked)
        index=raw/"market_index.json"
        save(index,{"lab_run_id":request["lab_run_id"],"time_unit":producer["time_unit"],
            "partitions":[{"path":str(linked.relative_to(root)),"sha256":partition["sha256"],
                           "start":partition["start"],"end_exclusive":partition["end_exclusive"]}]})
        truth={"lab_run_id":request["lab_run_id"],**{k:v for k,v in read(local(root,result["truth"]["path"])).items() if k != "lab_run_id"}}
        truth_path=raw/"evaluation_only_truth.json"; save(truth_path,truth)
        result["observable_market"]={"path":str(index.relative_to(root)),"sha256":file_digest(index)}
        result["truth"]={"path":str(truth_path.relative_to(root)),"sha256":file_digest(truth_path)}
        result["cache_materialized_from"]=producer.get("lab_run_id")
        return result
    def materialize_features(result):
        """Link a cached raw-feature parquet into this shard's evidence dir."""
        folder=local(root,str(Path(request["task_evidence"])/"feature-artifacts"))
        folder.mkdir(parents=True,exist_ok=True)
        producer_path=result["features"]["path"]; digest_value=result["features"]["sha256"]
        source=local(root,producer_path)
        if file_digest(source) != digest_value:
            raise ContractError("cached feature parquet hash drift: "+producer_path)
        target=folder/Path(producer_path).name
        if target.exists():
            if file_digest(target) != digest_value:
                raise ContractError("linked feature parquet drift; use a new task identity")
        else:
            os.link(source,target)
        result["features"]={"path":str(target.relative_to(root)),"sha256":digest_value}
        result["cache_materialized_from"]=producer_path
        return result
    def materialize_targets(name,result):
        """Link the producer's candidate traces so the consumer funnel sees them."""
        destination=local(root,str(Path(request["task_evidence"])/(name+"-artifacts")))
        destination.mkdir(parents=True,exist_ok=True)
        linked=[]
        for trace in result["traces"]:
            source=local(root,trace["path"])
            if file_digest(source) != trace["sha256"]:
                raise ContractError("cached target trace hash drift: "+trace["path"])
            target=destination/Path(trace["path"]).name
            if target.exists():
                if file_digest(target) != trace["sha256"]:
                    raise ContractError("linked target trace drift; use a new task identity")
            else:
                os.link(source,target)
            linked.append(str(target.relative_to(root)))
        result["cache_materialized_traces"]=linked
        return result
    def once(kind,name,facets,callback,materialize=None):
        path=directory/(name+".json")
        seal=directory/(name+".seal.json")
        if path.exists():
            if not seal.exists() or read(seal)["sha256"] != file_digest(path):
                raise ContractError("full-control nested stage drift/incomplete publication")
            cache_ledger.append({"kind":kind,"name":name,"status":"LOCAL"})
            return read(path)
        value,event=cache.get_or_compute(kind,facets,callback,producer=request["lab_run_id"])
        if event["status"] == "HIT" and materialize is not None:
            value=materialize(value)
        cache_ledger.append({"kind":kind,"name":name,**event})
        value["lab_run_id"]=request["lab_run_id"]
        h=save(path,value); save(seal,{"lab_run_id":request["lab_run_id"],"sha256":h})
        return value
    def child(name, childtask):
        folder=directory/name; folder.mkdir(parents=True,exist_ok=True)
        return {**request,"task":childtask,"inputs":inputs,"dependencies":{},"task_evidence":str(folder.relative_to(root))}
    for symbol in symbols:
        result=once("world","world-"+symbol,world_facets(symbol),
            lambda symbol=symbol: generate_world(root,child("raw-"+symbol,
                {"seed":variant(symbol),"condition":task["condition"],"days":days})),
            lambda payload,symbol=symbol: materialize_world(symbol,payload))
        # Deliberately exclude result['truth'] from all learner inputs.
        inputs[symbol]=result["observable_market"]
    feature_result=once("features","features",
        {"generator":"te_features_v1","contract":contract["features"],"protocol":protocol_sha,
         "market":market,"markets":{s:inputs[s]["sha256"] for s in symbols},
         "start":"2019-01-01T00:00:00Z","end":end},
        lambda:execute(root,child("feature-artifacts",{
            "task_id":"features","kind":"features","market":market,"markets":{s:s for s in inputs},
            "start":"2019-01-01T00:00:00Z","end":end})),
        materialize_features)
    features=pd.read_parquet(local(root,feature_result["features"]["path"]))
    features_sha=file_digest(local(root,feature_result["features"]["path"]))
    latency=int(task["latency_seconds"])
    if latency < 60: raise ContractError("full control needs frozen technical latency")
    def search_facets(cutoff):
        return {"schema":"te_search_v1","contract":contract["search"],"engine":engine,
                "binding":binding_sha,"market":inputs[market]["sha256"],"alpha":alpha,
                "cutoff":pd.Timestamp(cutoff).isoformat(),
                "history_start":(pd.Timestamp(cutoff)-pd.Timedelta(days=180)).isoformat(),
                "economics":{"fee":.0004,"slippage":1.,"contract":CONTRACT}}
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
        result=once("search",name,search_facets(cutoff),run); counts["searches"]+=1
        return result
    from .eligibility import history_start, history_days
    bank_cutoff=max(pd.Timestamp("2019-07-15T00:00:00Z"),pd.Timestamp("2019-01-01T00:00:00Z")+pd.Timedelta(days=180+history_days(alpha)))
    bank_search=select(bank_cutoff.isoformat())
    candidate_map={digest(t["params"]):t["params"] for t in bank_search["trials"] if t.get("objective") is not None and not t.get("pruned")}
    if len(candidate_map) < 2: raise ContractError("control has no parameter opportunity cohort")
    bank_candidates=[{"candidate_id":k,"params":v} for k,v in sorted(candidate_map.items())]
    bank_path=directory/"candidate-bank.json"
    save(bank_path,{"lab_run_id":request["lab_run_id"],"available_at":bank_search["ready_at"],
         "candidates":bank_candidates})
    inputs["bank"]=ref(root,bank_path)
    bank_digest=digest({"available_at":bank_search["ready_at"],"candidates":bank_candidates})
    targets=[]
    for origin in calendar((bank_cutoff+pd.Timedelta(days=1)).isoformat(),end,28):
        outcome=pd.Timestamp(origin)+pd.Timedelta(days=28)
        if outcome >= pd.Timestamp(end): break
        name="targets-"+digest(origin)[:16]
        facets={"schema":"te_targets_v1","contract":contract["targets"],"engine":engine,
                "market":inputs[market]["sha256"],"alpha":alpha,"cell_id":cell,
                "origin":pd.Timestamp(origin).isoformat(),"outcome_available_at":outcome.isoformat(),
                "history_start":history_start(alpha,origin),
                "candidate_bank":{"available_at":bank_search["ready_at"],"digest":bank_digest},
                "economics":{"fee":.0004,"slippage":1.,"contract":CONTRACT}}
        result=once("targets",name,facets,
            lambda origin=origin,outcome=outcome,name=name:candidate_targets(root,child(name+"-artifacts",{
                "origin":origin,"end":outcome.isoformat(),"history_start":history_start(alpha,origin),
                "candidate_bank":"bank","market":market,"alpha_id":alpha,"cell_id":cell})),
            lambda payload,name=name: materialize_targets(name,payload))
        targets.extend(result["targets"]); counts["target_accounts"]+=len(candidate_map)
    vintages=[]; previous=None
    for cutoff in calendar(start,end,28):
        name="model-"+digest(cutoff)[:16]
        ready=(pd.Timestamp(cutoff)+pd.Timedelta(seconds=latency)).isoformat()
        facets={"schema":"te_fit_v1","source":cache.source,"contract":contract["fit"],
                "features":features_sha,"targets":digest(targets),
                "cutoff":pd.Timestamp(cutoff).isoformat(),"ready_at":ready,"protocol":protocol_sha,
                "previous":None if previous is None else previous["model_id"]}
        vintage=once("fit",name,facets,
            lambda cutoff=cutoff,ready=ready,previous=previous:fit_vintage(
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
        accounts[arm]=once("deployment","deployment-"+arm,
            {"generator":"te_deployment_v1","contract":contract["deployment"],"engine":engine,
             "market":inputs[market]["sha256"],"alpha":alpha,"arm":arm,"start":start,"end":end,
             "selection_ids":[s["selection_id"] for s in selections],
             "economics":{"fee":.0004,"slippage":1.,"contract":CONTRACT}},
            deploy); counts["deployments"]+=1
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
        "compute_cache":{"namespace":"controls","events":cache_ledger,
            "hits":sum(1 for row in cache_ledger if row["status"] == "HIT"),
            "misses":sum(1 for row in cache_ledger if row["status"] == "MISS"),
            "local":sum(1 for row in cache_ledger if row["status"] == "LOCAL")},
        "world":world,"worlds_executed":list(symbols),
        "boundary_power_qualification":"NOT_EVALUABLE_FROM_STRUCTURAL_WORLD_ALONE",
        "reason":"known opportunity is not known net learner effect=2delta; do not certify registered boundary power from these worlds"}
