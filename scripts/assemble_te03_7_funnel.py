#!/usr/bin/env python
"""Assemble the TE-03.7 treatment funnel from controls-07 shard artifacts.

Reads only committed/local evidence; missing steps are null + reason, never zero-filled.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

LAB=Path(__file__).resolve().parent.parent

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--run-id",default="te-host-controls-07")
    ap.add_argument("--output",default="evidence/time_edge_validation_v4/te03/te03_7_funnel_r3.json")
    a=ap.parse_args()
    run=LAB/"evidence/time_edge_validation_v4/runs"/a.run_id
    steps={k:{"value":0,"denominator":0,"reason":None} for k in
           ("valid_observations","triggers","searches","different_params","activated","different_orders")}
    task_dirs=sorted(p for p in (run/"tasks").glob("*") if p.is_dir()) if (run/"tasks").is_dir() else []
    targets=searches=seals=worlds=0
    digests=set(); notes=[]
    for d in task_dirs:
        worlds+=len(list(d.glob("world-*.json")))
        seals+=len(list(d.glob("world-*.seal.json")))
        ts=sorted(d.glob("*-artifacts/target-*.json")); targets+=len(ts)
        for s in d.glob("search-*.seal.json"):
            searches+=1
            try:
                j=json.loads(s.read_text())
                for key in ("selected_digest","digest","parameter_digest"):
                    if j.get(key): digests.add(str(j[key]))
            except Exception as e:
                notes.append(f"{s.name}: {type(e).__name__}")
    if task_dirs:
        steps["valid_observations"].update(value=targets,denominator=targets,
            reason=None if targets else "no target artifacts yet")
        steps["searches"].update(value=searches,denominator=searches,
            reason=None if searches else "no search seals yet")
        steps["different_params"].update(value=len(digests),denominator=searches,
            reason=None if searches else "no selections yet")
        for k in ("triggers","activated","different_orders"):
            steps[k]["reason"]="not materialized in the shard artifacts read by this assembler"
    else:
        for k in steps: steps[k]["reason"]=f"no task dirs under {run}"
    payload={"schema":"regime_lab.te03_7_funnel.v1","run_id":a.run_id,
             "task_dirs":len(task_dirs),"worlds":worlds,"sealed_worlds":seals,
             "funnel":steps,"notes":notes,
             "rule":"denominator carried for every step; a step not materialized is null with a reason, never zero"}
    out=LAB/a.output; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2)+"\n",encoding='utf-8')
    print(json.dumps(payload,indent=2))
if __name__=="__main__": main()
