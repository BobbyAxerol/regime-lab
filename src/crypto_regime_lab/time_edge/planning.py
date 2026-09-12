"""Materialize runnable, hashed task plans before spending compute."""
from pathlib import Path

import pandas as pd

from ..experiments.time_edge_contracts import ContractError
from .runtime import local, source_identity, validate_job
from .schedule import calendar, triggers, matched_cadence
from .storage import digest, file_digest, read, save, utcnow
from .eligibility import history_start, coverage


def ref(root, path):
    path=local(root,path)
    return {"path":str(path.relative_to(root)),"sha256":file_digest(path)}


def snapshot_indices(root, directory):
    root=Path(root); snapshot=read(root/"snapshots/server_core_v1/manifest.json")
    refs={}
    for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","DOGEUSDT"):
        partitions=[]
        for row in snapshot["files"]:
            if row["product_id"] != "crypto_binance_futures_1m" or row["symbol"] != symbol or not row["closed"]: continue
            start=pd.Timestamp(row["time_min"],tz="UTC"); end=pd.Timestamp(row["time_max"],tz="UTC")+pd.Timedelta(minutes=1)
            if start >= pd.Timestamp("2024-01-01",tz="UTC"): continue
            path=local(root,row["snapshot_path"])
            partitions.append({"path":str(path.relative_to(root)),"sha256":row["sha256"],"start":start.isoformat(),"end_exclusive":end.isoformat()})
        path=local(root,str(Path(directory)/f"market-{symbol}.json"))
        save(path,{"lab_run_id":"TE-MARKET-INDEX","symbol":symbol,"snapshot_manifest_sha256":file_digest(root/"snapshots/server_core_v1/manifest.json"),
                   "partitions":partitions,"time_unit":"ms","price_role":"retrospective copied archive"})
        refs[symbol]=ref(root,path)
    return refs


def make_plan(root, *, run_id, stage, spec=None, allocation=None):
    root=Path(root); folder=f"evidence/time_edge_validation_v4/plans/{run_id}"
    if not run_id.replace("-","").replace("_","").isalnum():
        raise ContractError("run ID may contain only letters, digits, hyphens and underscores")
    if stage in ("discovery","decay") and (allocation is None or not allocation.get("profile_refs")):
        raise ContractError("discovery/decay require explicit profile-backed shared allocation")
    inputs={}; tasks=[]
    if allocation is None:
        allocation={"allocation_id":"TE02-PILOT-R03","total_wall_seconds":1800.,"task_wall_seconds":600.}
    if stage in ("discovery","models","targets","decay","controls","statistical-calibration") and spec is None:
        raise ContractError("this stage needs a registered --spec with measured inputs; see handoff/TE_CLI_RUNBOOK.md")
    if stage == "qualify":
        tasks=[{"task_id":"engine-clock-fee-reconciliation","kind":"qualify","wall_seconds":60.}]
    elif stage in ("pilot","features"):
        inputs=snapshot_indices(root,folder)
        if stage == "features":
            tasks=[{"task_id":"common-raw-features","kind":"features","markets":{s:s for s in inputs},
                    "start":"2020-01-01T00:00:00Z","end":"2024-01-01T00:00:00Z"}]
        else:
            # Training-only technical pilot; not a TE04 economic look.
            tasks=[{"task_id":"engine-clock-fee-reconciliation","kind":"qualify","wall_seconds":60.},
                {"task_id":"A-SC-BTC-train-selection","kind":"select","market":"BTCUSDT","alpha_id":"A-SC",
                 "cutoff":"2020-12-01T00:00:00Z","history_start":"2020-01-01T00:00:00Z","latency_seconds":60.,
                 "latency_role":"PROFILING_FLOOR_NOT_DISCOVERY_CERTIFICATE","depends_on":["engine-clock-fee-reconciliation"]},
                {"task_id":"A-SC-BTC-selected-audit","kind":"audit_selection","market":"BTCUSDT","alpha_id":"A-SC",
                 "cell_id":"A-SC/BTCUSDT","history_start":"2020-01-01T00:00:00Z","depends_on":["A-SC-BTC-train-selection"]},
                {"task_id":"A-SC-BTC-train-deployment","kind":"deploy","market":"BTCUSDT","alpha_id":"A-SC",
                 "cell_id":"A-SC/BTCUSDT","arm":"M4_CAL","history_start":"2020-01-01T00:00:00Z",
                 "start":"2020-12-01T00:00:00Z","end":"2020-12-31T00:00:00Z","depends_on":["A-SC-BTC-train-selection","A-SC-BTC-selected-audit"]}]
    if spec:
        inputs.update({k:ref(root,v) if isinstance(v,str) else v for k,v in spec.get("inputs",{}).items()})
        tasks.extend(spec.get("tasks",[]))
        if "model_series" in spec:
            series=spec["model_series"]; previous=None; fits=[]
            for cutoff in calendar(series["start"],series["end"],28):
                tid="model-"+digest(cutoff)[:12]
                tasks.append({"task_id":tid,"kind":"fit_model","features":series["features"],"targets":series["targets"],
                    "cutoff":cutoff,"ready_at":(pd.Timestamp(cutoff)+pd.Timedelta(seconds=series["latency_seconds"])).isoformat(),
                    "depends_on":[] if previous is None else [previous]})
                previous=tid; fits.append(tid)
            tasks.append({"task_id":"deployed-emissions","kind":"emit","features":series["features"],"end":series["end"],"depends_on":fits})
        if "target_series" in spec:
            series=spec["target_series"]
            for origin in calendar(series["start"],series["end"],28):
                until=pd.Timestamp(origin)+pd.Timedelta(days=28)
                if until > pd.Timestamp(series["end"]): break
                tasks.append({"task_id":"target-"+digest(origin)[:12],"kind":"targets","origin":origin,"end":until.isoformat(),
                    "history_start":history_start(series["alpha_id"],origin),"market":series["market"],
                    "candidate_bank":series["candidate_bank"],"alpha_id":series["alpha_id"],"cell_id":series["cell_id"]})
        if stage == "discovery":
            tasks.extend(discovery_tasks(root,spec,inputs))
    if not tasks: raise ContractError("no runnable tasks in registered plan")
    plan={"lab_run_id":run_id,"created_at":utcnow(),"stage":stage,"source_identity":digest(source_identity(root)),
          "inputs":inputs,"tasks":tasks,**allocation,
          "runtime_acceptance":None if spec is None else spec.get("runtime_acceptance"),
          "completion_rule":"all planned tasks; failed/blocked retained; no outcome-based stopping",
          "economic_conclusion":"NOT_ASSESSED_BY_PLAN","workers":1,"cpu_limit":2,"memory_gib":4}
    validate_job(root,plan)
    output=local(root,folder+"/job.json"); save(output,plan)
    return {"job":str(output.relative_to(root)),"sha256":file_digest(output),"tasks":len(tasks),
            "allocation_id":plan["allocation_id"],"total_wall_seconds":plan["total_wall_seconds"],
            "worst_case_reserved_seconds":sum(t.get("wall_seconds",plan["task_wall_seconds"]) for t in tasks),
            "note":"allocation is shared across run IDs; task cap is not an ETA"}


def discovery_tasks(root, spec, inputs):
    from .runtime import verify_ref
    eligibility=coverage(root)
    if eligibility["blocked_cells"]:
        raise ContractError("registered full cohort lacks initial train/history: "+", ".join(eligibility["blocked_cells"]))
    # Gate bundles are derived from completed runtime acceptance, not CLI flags.
    gate=read(verify_ref(root,inputs[spec["runtime_acceptance"]]))
    required=("engine_clock","alpha_lifecycles","mode4_parity","account_reconciliation","model_causality","full_pipeline_calibration","economic_threshold")
    for key in required:
        proof=gate.get(key,{})
        if proof.get("status") != "PASS" or proof.get("denominator",0) <= 0 or not proof.get("artifact_refs"):
            raise ContractError("discovery BLOCKED prerequisite: "+key)
        for reference in proof["artifact_refs"]: verify_ref(root,reference)
    if gate.get("source_identity") != digest(source_identity(root)):
        raise ContractError("runtime acceptance belongs to a different source identity")
    tape=read(verify_ref(root,inputs[spec["emissions"]]))
    profile=read(verify_ref(root,inputs[spec["profile"]]))
    delta=read(verify_ref(root,inputs[spec["threshold"]]))
    if delta["value"] <= 0 or delta["unit"] != "account_return/day": raise ContractError("invalid frozen economic threshold")
    initial="2020-12-31T00:00:00Z"; start="2021-01-01T00:00:00Z"; end="2024-01-01T00:00:00Z"
    generated=[]
    for cell in spec["cells"]:
        alpha,symbol=cell.split("/"); route=profile["routes"][alpha]
        latency=max(60,int(np_ceil(route["p95_search_plus_packing_seconds"])))
        if route["completed_pilot_count"] < 1: raise ContractError("unmeasured route profile")
        matched=matched_cadence(route["training_predicted_regime_work"],route["per_selection_work"],days=1095)
        model_events=triggers(tape["emissions"],initial_ready=start,end=end)["triggers"]
        schedules={"M4_CAL":calendar("2021-06-30T00:00:00Z",end,180),
                   "M4_REGIME":[r["cutoff"] for r in model_events],
                   "M4_CAL_MATCHED":calendar((pd.Timestamp(start)+pd.Timedelta(days=matched)).isoformat(),end,matched)}
        common_id=cell.replace("/","-")+"-initial"
        generated.append({"task_id":common_id,"kind":"select","alpha_id":alpha,"market":symbol,
            "cutoff":initial,"history_start":history_start(alpha,pd.Timestamp(initial)-pd.Timedelta(days=180)),"latency_seconds":latency})
        by_cutoff={initial:common_id}
        for arm,cutoffs in schedules.items():
            dependencies=[common_id]
            for cutoff in cutoffs:
                if cutoff not in by_cutoff:
                    tid=cell.replace("/","-")+"-"+digest(cutoff)[:12]
                    eligible=[r for r in tape["emissions"] if pd.Timestamp(r["available_at"]) <= pd.Timestamp(cutoff) and r["decision_eligible"] and pd.Timestamp(r["model_ready_at"]) <= pd.Timestamp(cutoff)]
                    emission=eligible[-1] if eligible else None
                    history=history_start(alpha,pd.Timestamp(cutoff)-pd.Timedelta(days=180))
                    generated.append({"task_id":tid,"kind":"select","alpha_id":alpha,"market":symbol,
                        "cutoff":cutoff,"history_start":history,"latency_seconds":latency,
                        "model_id":None if emission is None else emission["model_id"]})
                    by_cutoff[cutoff]=tid
                dependencies.append(by_cutoff[cutoff])
            generated.append({"task_id":cell.replace("/","-")+"-"+arm,"kind":"deploy","alpha_id":alpha,
                "cell_id":cell,"arm":arm,"market":symbol,"history_start":history_start(alpha,start),
                "start":start,"end":end,"depends_on":dependencies})
    return generated


def np_ceil(value):
    import math
    if not math.isfinite(value) or value < 0: raise ContractError("invalid measured latency")
    return math.ceil(value)
