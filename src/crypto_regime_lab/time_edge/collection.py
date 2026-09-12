"""Assemble only hash-verified completed task outputs into the next phase input."""
from pathlib import Path

from ..experiments.time_edge_contracts import ContractError
from .runtime import local
from .storage import Ledger, read, save, digest, file_digest


def collect_runs(root, run_ids, *, kind, output, task_id=None):
    root=Path(root); results=[]; refs=[]; identities=set()
    for run_id in run_ids:
        directory=local(root,f"evidence/time_edge_validation_v4/runs/{run_id}")
        job=read(directory/"job.json"); identities.add(job["source_identity"])
        ledger=Ledger(directory,{"job_hash":digest(job)},job["total_wall_seconds"])
        try:
            for task in job["tasks"]:
                if task_id is not None and task["task_id"] != task_id: continue
                result=ledger.cached(task)
                if result is not None:
                    results.append(result)
                    task_key=digest({"identity":ledger.identity,"task":task})
                    row=next(a for a in reversed(ledger.status()["attempts"]) if a["task"] == task_key and a["status"] == "COMPLETE")
                    refs.append({"path":str((directory/row["result_path"]).relative_to(root)),"sha256":row["result_hash"]})
        finally: ledger.close()
    if not results or len(identities) != 1: raise ContractError("nonempty same-source completed outputs required")
    payload={"lab_run_id":"TE-COLLECT-"+digest(run_ids)[:12],"source_identity":identities.pop(),"source_refs":refs}
    if kind == "bank":
        selected=[r for r in results if r.get("status") == "SELECTED"]
        if len(selected) != 1: raise ContractError("bank requires exactly one actual selection; specify --task-id")
        source=selected[0]
        params={digest(r["params"]):r["params"] for r in source["trials"] if not r.get("pruned") and r.get("objective") is not None}
        if len(params)<2: raise ContractError("bank has fewer than two feasible candidates")
        payload.update(available_at=source["ready_at"],alpha_id=source["alpha_id"],candidates=[{"candidate_id":k,"params":v} for k,v in sorted(params.items())])
    elif kind == "targets":
        rows=[r for result in results for r in result.get("targets",[])]
        keys=[(r["cell_id"],r["origin"],r["candidate_set_hash"]) for r in rows]
        if not rows or len(set(keys)) != len(keys): raise ContractError("empty or duplicate target cohort")
        payload["targets"]=sorted(rows,key=lambda r:(r["origin"],r["cell_id"]))
    elif kind == "accounts":
        payload["accounts"]=[reference for result,reference in zip(results,refs) if "daily_returns" in result and "arm" in result]
        if not payload["accounts"]: raise ContractError("no closed account outputs")
    elif kind == "selections":
        payload["selections"]=[dict(s,cell_id=r["cell_id"],arm=r["arm"]) for r in results if "arm" in r for s in r.get("selections",[])]
        if not payload["selections"]: raise ContractError("no deployed account selections")
    else: payload["results"]=results
    path=local(root,output); save(path,payload)
    return {"path":str(path.relative_to(root)),"sha256":file_digest(path),"completed_source_tasks":len(results),"kind":kind}
