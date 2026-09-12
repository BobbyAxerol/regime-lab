#!/usr/bin/env python3
"""Canonical TE CLI. Default commands do not launch market work implicitly."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
os.environ.setdefault("NUMBA_CACHE_DIR",str(ROOT/".cache/numba"))
os.environ.setdefault("MPLCONFIGDIR",str(ROOT/".cache/matplotlib"))
os.environ.setdefault("TMPDIR",str(ROOT/".cache/tmp"))

from crypto_regime_lab.time_edge.storage import read, save, utcnow
from crypto_regime_lab.time_edge.runtime import local


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    pre=commands.add_parser("preflight"); pre.add_argument("--output")
    cov=commands.add_parser("coverage"); cov.add_argument("--output",required=True)
    delivery=commands.add_parser("delivery")
    for option in ("acceptance","preflight","coverage","output","run-id"):
        delivery.add_argument("--"+option,required=True)
    check=commands.add_parser("verify-technical"); check.add_argument("--run-id",required=True)
    plan=commands.add_parser("plan")
    plan.add_argument("--run-id",required=True)
    plan.add_argument("--stage",choices=("qualify","pilot","features","models","targets","discovery","decay","controls","statistical-calibration","custom"),required=True)
    plan.add_argument("--spec"); plan.add_argument("--allocation"); plan.add_argument("--coverage")
    for name in ("run","qualify","fit-model","controls","calibrate"):
        run=commands.add_parser(name); run.add_argument("--job",required=True)
        run.add_argument("--retry-failed",action="store_true"); run.add_argument("--max-tasks",type=int)
        run.add_argument("--resume",action="store_true")
    for name in ("status","stop"):
        sub=commands.add_parser(name); sub.add_argument("--run-id",required=True)
    for name in ("analyse","freeze"):
        sub=commands.add_parser(name); sub.add_argument("--spec",required=True); sub.add_argument("--output",required=True)
        sub.add_argument("--run-id",required=True)
    verify=commands.add_parser("verify"); verify.add_argument("--manifest",required=True)
    report=commands.add_parser("report"); report.add_argument("--evidence",required=True); report.add_argument("--output",required=True)
    merge=commands.add_parser("collect"); merge.add_argument("--run-id",action="append",required=True)
    merge.add_argument("--kind",choices=("targets","bank","accounts","selections","results"),required=True)
    merge.add_argument("--task-id"); merge.add_argument("--output",required=True)
    worker=commands.add_parser("_worker",help="Internal isolated worker, invoked by run"); worker.add_argument("--request",required=True); worker.add_argument("--output",required=True)
    args=parser.parse_args(argv)
    if not str(Path(sys.executable).absolute()).startswith(str(ROOT/"environments/lab_venv")):
        raise ValueError("use this LAB's environments/lab_venv/bin/python")
    (ROOT/".cache/tmp").mkdir(parents=True,exist_ok=True)
    if args.command == "delivery":
        from crypto_regime_lab.time_edge.delivery import build_delivery
        result=build_delivery(ROOT,acceptance=args.acceptance,preflight=args.preflight,coverage=args.coverage,output=args.output,lab_run_id=args.run_id)
    elif args.command == "coverage":
        from crypto_regime_lab.time_edge.eligibility import coverage
        result=coverage(ROOT); save(local(ROOT,args.output),result)
    elif args.command == "preflight":
        from crypto_regime_lab.time_edge.runtime import preflight
        result=preflight(ROOT)
        if args.output: save(local(ROOT,args.output),result)
    elif args.command == "verify-technical":
        from crypto_regime_lab.time_edge.verification import verify_technical
        result=verify_technical(ROOT,args.run_id)
    elif args.command == "plan":
        from crypto_regime_lab.time_edge.planning import make_plan
        result=make_plan(ROOT,run_id=args.run_id,stage=args.stage,
            spec=read(local(ROOT,args.spec)) if args.spec else None,
            allocation=read(local(ROOT,args.allocation)) if args.allocation else None,
            coverage=args.coverage)
    elif args.command in ("run","qualify","fit-model","controls","calibrate"):
        from crypto_regime_lab.time_edge.runtime import run_jobs
        job=read(local(ROOT,args.job))
        allowed={"qualify":{"qualify","pilot"},"fit-model":{"models"},"controls":{"controls"},"calibrate":{"statistical-calibration"}}
        if args.command in allowed and job["stage"] not in allowed[args.command]:
            raise ValueError("job stage does not match CLI operation")
        result=run_jobs(ROOT,job,retry_failed=args.retry_failed,max_tasks=args.max_tasks,resume=args.resume)
    elif args.command in ("status","stop"):
        from crypto_regime_lab.time_edge.runtime import status, stop
        result=(status if args.command == "status" else stop)(ROOT,args.run_id)
    elif args.command == "_worker":
        from crypto_regime_lab.time_edge.workers import execute
        request=read(local(ROOT,args.request))
        try: result=execute(ROOT,request)
        except Exception as exc:
            result={"lab_run_id":request["lab_run_id"],"status":"FAILED","reason":f"{type(exc).__name__}: {exc}","created_at":utcnow()}
            save(local(ROOT,args.output),result); raise
        save(local(ROOT,args.output),result)
    elif args.command == "analyse":
        from crypto_regime_lab.time_edge.reporting import collect, analyse_accounts, gate_claims
        from crypto_regime_lab.time_edge.runtime import verify_ref
        spec=read(local(ROOT,args.spec))
        accounts=collect(ROOT,spec["accounts"])
        delta=collect(ROOT,[spec["threshold"]])[0]["value"] if spec.get("threshold") else None
        ages=collect(ROOT,spec.get("decay_accounts",[]))
        info={"model_table":[],"information_rows":[]}; tape=[]
        if spec.get("model_vintages"):
            import pandas as pd
            from crypto_regime_lab.time_edge.model_evaluation import evaluate_vintages
            bundles=collect(ROOT,spec["model_vintages"])
            vintages=[v for b in bundles for v in b.get("results",[b]) if "design_trials" in v]
            tape=collect(ROOT,[spec["emissions"]])[0]["emissions"]
            targets=collect(ROOT,[spec["targets"]])[0]["targets"]
            features=pd.read_parquet(verify_ref(ROOT,spec["features"]))
            info=evaluate_vintages(vintages,features,targets,tape,end="2024-01-01T00:00:00Z")
        result=analyse_accounts(accounts,delta=delta,decay_accounts=ages,information_rows=info["information_rows"],model_table=info["model_table"],emissions=tape)
        acceptance={}
        if spec.get("acceptance"):
            acceptance=collect(ROOT,[spec["acceptance"]])[0]
            for gate in acceptance.values():
                if isinstance(gate,dict):
                    for reference in gate.get("artifact_refs",[]): verify_ref(ROOT,reference)
        result.update(lab_run_id=args.run_id,created_at=utcnow(),claims=gate_claims(result,acceptance))
        save(local(ROOT,args.output),result)
    elif args.command == "freeze":
        from crypto_regime_lab.time_edge.reporting import freeze
        result=freeze(ROOT,read(local(ROOT,args.spec))["artifacts"],args.output,lab_run_id=args.run_id)
    elif args.command == "verify":
        from crypto_regime_lab.time_edge.reporting import verify_freeze
        result=verify_freeze(ROOT,read(local(ROOT,args.manifest)))
    elif args.command == "report":
        from crypto_regime_lab.time_edge.reporting import render
        from crypto_regime_lab.time_edge.planning import ref
        result=render(ROOT,ref(ROOT,args.evidence),args.output)
    elif args.command == "collect":
        from crypto_regime_lab.time_edge.collection import collect_runs
        result=collect_runs(ROOT,args.run_id,kind=args.kind,output=args.output,task_id=args.task_id)
    from crypto_regime_lab.time_edge.storage import jsonable as _jsonable
    print(json.dumps(_jsonable(result),ensure_ascii=False,allow_nan=False,indent=2))
    return 1 if result.get("status") in ("FAILED","FAILED_SOURCE_DRIFT") else 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        print(json.dumps({"status":"BLOCKED","reason":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)
