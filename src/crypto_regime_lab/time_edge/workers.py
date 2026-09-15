"""Typed worker operations used by the bounded CLI. All market work is isolated."""
from dataclasses import asdict
from pathlib import Path
import os
import resource
import time

import numpy as np
import pandas as pd

from ..experiments.time_edge_contracts import ContractError
from .execution import PreparedAccount, select_only, endpoint, CONTRACT, validate_market
from .metrics import account_returns, describe
from .model import fit_vintage, emit, jsonable
from .runtime import local, verify_ref
from .storage import digest, file_digest, read, save


def require_isolated(root):
    mounts=[line.split() for line in Path("/proc/self/mountinfo").read_text().splitlines()]
    roots=[m for m in mounts if m[4] == "/"]
    labs=[m for m in mounts if m[4] == str(root)]
    if os.environ.get("TE_ISOLATED_WORKER") != "1" or not roots or "ro" not in roots[-1][5].split(",") or not labs or "rw" not in labs[-1][5].split(","):
        raise ContractError("worker requires measured read-only root and writable LAB mount")
    routes=Path("/proc/net/route").read_text().splitlines()[1:]
    if any(line.split()[0] != "lo" for line in routes if line.strip()):
        raise ContractError("network isolation missing")
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    cpus=sorted(os.sched_getaffinity(0))[:2]
    os.sched_setaffinity(0,cpus)
    import importlib.metadata as md
    import quantbt
    if not Path(quantbt.__file__).resolve().is_relative_to(Path(root)/"environments/lab_venv") or md.version("quantbt-engine") != "1.1.1" or md.version("quantbt-native") != "0.4.2":
        raise ContractError("wrong QuantBT package path/version")


def read_market(root, reference, *, start, end, allow_listing_boundary=False):
    """Read only intersecting copied partitions; never execute the original loader."""
    spec=read(verify_ref(root,reference))
    lo,hi=pd.Timestamp(start),pd.Timestamp(end)
    chunks=[]
    for part in spec["partitions"]:
        if pd.Timestamp(part["end_exclusive"]) <= lo or pd.Timestamp(part["start"]) >= hi:
            continue
        p=verify_ref(root,{"path":part["path"],"sha256":part["sha256"]})
        import pyarrow.parquet as pq
        names=pq.ParquetFile(p).schema_arrow.names
        columns=[c for c in ("time","open","high","low","close","volume","quote_volume","number_of_trades","taker_buy_base_volume") if c in names]
        frame=pd.read_parquet(p,columns=columns)
        if not isinstance(frame.index,pd.DatetimeIndex):
            stamp=frame.pop("time")
            if pd.api.types.is_numeric_dtype(stamp):
                # Snapshot manifest declares epoch unit; no magnitude heuristic.
                frame.index=pd.to_datetime(stamp,unit=spec["time_unit"],utc=True)
            else: frame.index=pd.to_datetime(stamp,utc=True)
        else: frame.index=pd.to_datetime(frame.index,utc=True)
        frame=frame.loc[(frame.index >= lo) & (frame.index < hi)]
        if not frame.empty: chunks.append(frame)
    if not chunks: raise ContractError("no declared copied market partitions in task window")
    result=pd.concat(chunks).sort_index()
    validate_market(result)
    if not allow_listing_boundary and (result.index[0] != lo or result.index[-1]+pd.Timedelta(minutes=1) != hi):
        raise ContractError("task window market coverage incomplete")
    return result


def export_account(root, folder, run, *, start, end, lab_run_id, selections, cell_id, arm):
    directory=local(root,folder); directory.mkdir(parents=True,exist_ok=True)
    daily=account_returns(run["equity"],run["index"],initial_equity=20000.,start=start,end=end)
    # Binary marks keep the full 1m account without millions of JSON objects.
    marks=directory/"engine_marks.parquet"
    if marks.exists(): raise ContractError("account trace already exists; use a new attempt")
    pd.DataFrame({"equity":run["equity"],"position":run["positions"]},index=run["index"]).to_parquet(marks,index=True)
    table_refs={}
    for key,table in run.get("engine_tables",{}).items():
        if table.empty: continue
        path=directory/("table-"+digest(key)[:16]+".parquet")
        if path.exists(): raise ContractError("engine table already exists")
        (table.to_frame() if isinstance(table,pd.Series) else table).to_parquet(path,index=True)
        table_refs[key]={"path":str(path.relative_to(root)),"sha256":file_digest(path),"rows":len(table)}
    payload={k:v for k,v in run.items() if k not in ("equity","positions","index","engine_tables")}
    payload["engine_table_refs"]=table_refs
    payload.update(lab_run_id=lab_run_id,cell_id=cell_id,arm=arm,score_start=start,score_end_exclusive=end,
        daily_returns=daily,metrics=describe(daily),selections=selections,
        engine_marks={"path":str(marks.relative_to(root)),"sha256":file_digest(marks)},
        data_role="NESTED_RETROSPECTIVE",funding="MISSING_DECLARED",cash={"value":None,"reason":"not exported by this binding; qualification must verify engine account reconciliation"})
    save(directory/"account.json",jsonable(payload))
    return jsonable(payload)


def qualify():
    """Deterministic public-engine fixtures with independently known prices/fees.

    This certifies the engine clock/economics contract only. Alpha lifecycle and
    same-cutoff Mode 4 parity are separate measured gates, never inferred here.
    """
    import quantbt as q
    index=pd.date_range("2020-01-01",periods=8,freq="min",tz="UTC")
    frame=pd.DataFrame({"open":[100,110,120,130,125,120,115,110],
                        "high":[101,111,121,131,126,121,116,111],
                        "low":[99,109,119,129,124,119,114,109],
                        "close":[100.5,110.5,120.5,130.5,125.5,120.5,115.5,110.5],"volume":1000.},index=index)
    class Probe:
        def __init__(self): self.fills=[]; self.contexts=[]
        def initialize(self,context): return []
        def on_bar_close(self,context):
            self.fills.extend([asdict(f) for f in context.fills_this_bar])
            self.contexts.append({"bar":context.bar_index,"equity":float(context.equity),"position":float(context.positions.get("S",0.))})
            if context.bar_index in (0,3):
                return [q.OrderCommand(timestamp=context.timestamp,action=q.OrderAction.PLACE,symbol="S",
                    side=q.OrderSide.BUY if context.bar_index == 0 else q.OrderSide.SELL,
                    order_type=q.OrderType.MARKET,qty=1.,reduce_only=context.bar_index == 3,
                    order_id=f"probe-{context.bar_index}")]
            return []
        def finalize(self,context): return []
    probe=Probe(); ep=endpoint(slippage=0.)
    result=ep.simulate(data=frame,strategy=probe)
    fills=getattr(result,"fills",None) or []
    prices=[float(f.price) for f in fills]
    fees=[float(f.fee) for f in fills]
    eq=np.asarray(result.equity).reshape(-1)
    expected_terminal=20000.+(125.-110.)-(110.+125.)*.0004
    checks={"two_actual_fills":len(fills) == 2,"next_open_gap":prices == [110.,125.],
        "one_way_fees":len(fees) == 2 and np.allclose(fees,[110*.0004,125*.0004],rtol=0,atol=1e-10),
        "terminal_account_reconciliation":bool(abs(eq[-1]-expected_terminal) < 1e-8),
        "feedback_count":len(probe.fills) == 2}
    metadata=jsonable(getattr(result,"metadata",{}) or {})
    return {"status":"ENGINE_CLOCK_QUALIFIED" if all(checks.values()) else "FAILED",
        "checks":checks,"check_denominator":len(checks),"prices":prices,"fees":fees,
        "terminal_equity":float(eq[-1]),"independent_expected_terminal":expected_terminal,
        "engine_metadata":metadata,"execution_contract":CONTRACT,"engine_runs":1,
        "alpha_lifecycle_gate":"NOT_RUN","mode4_parity_gate":"NOT_RUN","economic_conclusion":"NOT_EVALUABLE"}


def _selections(request):
    output=[]
    for task_id,result in request["dependencies"].items():
        if result.get("status") == "SELECTED":
            output.append({"selection_id":result["selection_id"],"params":result["params"],
                "cutoff":result["cutoff"],"ready_at":result["ready_at"],
                "model_id":result.get("model_id"),"source_task":task_id,"status":"SELECTED"})
    return sorted(output,key=lambda r:(r["ready_at"],r["selection_id"]))


def execute(root, request):
    root=Path(root); require_isolated(root)
    task=request["task"]; kind=task["kind"]; inputs=request["inputs"]
    directory=local(root,request["task_evidence"])
    started=time.perf_counter()
    if kind == "qualify": result=qualify()
    elif kind == "select":
        cutoff=pd.Timestamp(task["cutoff"])
        frame=read_market(root,inputs[task["market"]],start=task["history_start"],end=cutoff.isoformat())
        binding=read(root/"configs/time_edge_validation_v4/mode4_binding_r01.json")
        result=select_only(frame,alpha_id=task["alpha_id"],cutoff=cutoff,binding=binding,
                           evidence_dir=directory,lab_run_id=request["lab_run_id"],fee=task.get("fee",.0004),slippage=task.get("slippage",1.))
        latency=task.get("latency_seconds")
        if latency is None or latency < 60: raise ContractError("registered measured conservative latency required")
        result.update(selection_id=digest({"task":task,"params":result.get("params")}),
                      ready_at=(cutoff+pd.Timedelta(seconds=latency)).isoformat(),model_id=task.get("model_id"))
        actual=time.perf_counter()-started
        result["measured_search_io_packing_seconds"]=actual
        if actual > latency and task.get("latency_role") != "PROFILING_FLOOR_NOT_DISCOVERY_CERTIFICATE":
            result.update(status="BLOCKED",reason="LATENCY_ENVELOPE_EXCEEDED: keep selected artifact; revise measured envelope before deploying it")
    elif kind == "audit_selection":
        selected=next(v for v in request["dependencies"].values() if v.get("status") == "SELECTED")
        cutoff=pd.Timestamp(selected["cutoff"]); start=cutoff-pd.Timedelta(days=180)
        frame=read_market(root,inputs[task["market"]],start=task["history_start"],end=cutoff.isoformat())
        account=PreparedAccount(frame)
        version={"selection_id":digest(selected["params"]),"params":selected["params"],"cutoff":start.isoformat(),"ready_at":start.isoformat()}
        warm=account.run(task["alpha_id"],[version],account_start=start)
        cold=account.run(task["alpha_id"],[version],account_start=start,cold=True)
        cold_values=cold["equity"][cold["index"] >= start]
        differences=np.abs(warm["equity"]-cold_values)
        def fill_signature(run):
            return [(f["absolute_bar_index"],f["side"],f["qty"],f["price"],f["fee"],f["tag"]) for f in run["fills"]]
        canonical=account_returns(warm["equity"],warm["index"],initial_equity=20000.,start=start.ceil("D"),end=cutoff.floor("D"))
        from ..experiments.time_edge_contracts import daily_sharpe
        score=daily_sharpe([v for _,v in canonical])["value"]
        selected_score=selected["selected"]["mean_is_sharpe"]
        checks={"two_evaluated_accounts":warm["status"] == cold["status"] == "EVALUATED",
                "equity_parity":bool(len(differences) and differences.max() <= 1e-8),
                "fill_parity":fill_signature(warm) == fill_signature(cold),
                "nonvacuous_fills":warm["engine_fill_count"] > 0,
                "raw_selected_sharpe_parity":score is not None and abs(score-selected_score) <= 1e-10}
        warm_trace=export_account(root,request["task_evidence"]+"/prepared-audit",warm,start=start.ceil("D").isoformat(),end=cutoff.floor("D").isoformat(),
            lab_run_id=request["lab_run_id"],selections=[version],cell_id=task["cell_id"],arm="TRAIN_ONLY_AUDIT")
        cold_trace=export_account(root,request["task_evidence"]+"/cold-audit",cold,start=start.ceil("D").isoformat(),end=cutoff.floor("D").isoformat(),
            lab_run_id=request["lab_run_id"],selections=[version],cell_id=task["cell_id"],arm="TRAIN_ONLY_AUDIT")
        result={"status":"SELECTED_AUDIT_PASS" if all(checks.values()) else "FAILED","checks":checks,"denominator":len(checks),
                "cold_marks":cold_trace["engine_marks"],"prepared_marks":warm_trace["engine_marks"],"maximum_equity_error":float(differences.max()),
                "raw_sharpe":score,"selected_raw_sharpe":selected_score,"fill_count":warm["engine_fill_count"],
                "cold_wall_seconds":cold["wall_seconds"],"prepared_wall_seconds":warm["wall_seconds"],
                "cold_callback_count":cold["callback_count"],"prepared_callback_count":warm["callback_count"]}
    elif kind in ("deploy","decay"):
        from .eligibility import require_history
        selections=_selections(request)
        if "selections_input" in task:
            supplied=read(verify_ref(root,inputs[task["selections_input"]]))
            selections=supplied["selections"]
        if not selections: raise ContractError("deployment needs actual successful selection artifacts")
        frame=read_market(root,inputs[task["market"]],start=task["history_start"],end=task["end"])
        require_history(frame,task["alpha_id"],task["start"])
        account=PreparedAccount(frame,fee=task.get("fee",.0004),slippage=task.get("slippage",1.))
        run=account.run(task["alpha_id"],selections,account_start=task["start"])
        result=export_account(root,request["task_evidence"]+"/deployment",run,start=task["start"],end=task["end"],
            lab_run_id=request["lab_run_id"],selections=selections,cell_id=task["cell_id"],arm=task["arm"])
        if kind == "decay":
            from .decay import age_windows
            if len(selections) != 1: raise ContractError("D2 must keep one fixed theta")
            result["age_windows"]=age_windows(result["daily_returns"],ready_at=selections[0]["ready_at"])
            result.update(quarter=task["quarter"],context_key=task["context_key"],selection_id=selections[0]["selection_id"],ready_at=selections[0]["ready_at"])
    elif kind == "features":
        from ..data.availability import OHLCV_AGGREGATION
        from ..data.panel import build_symbol_features, build_market_context, attach_market
        panels={}
        for symbol,input_name in task["markets"].items():
            market=read_market(root,inputs[input_name],start=task["start"],end=task["end"],allow_listing_boundary=True)
            aggregation={c:f for c,f in OHLCV_AGGREGATION.items() if c in market.columns}
            bars=market.resample("4h",origin="epoch",label="left",closed="left").agg(aggregation)
            bars=bars.reset_index().rename(columns={bars.index.name or "index":"time"})
            # Named datetime index survives reset under its original name.
            if "time" not in bars: bars=bars.rename(columns={bars.columns[0]:"time"})
            bars["available_at"]=bars["time"]+pd.Timedelta(hours=4)
            panels[symbol]=build_symbol_features(bars)
            del market
        market_context=build_market_context(panels)
        common=attach_market(panels[task.get("market","BTCUSDT")],market_context)
        names=read(root/"configs/time_edge_validation_v4/r01/model_protocol.json")["features"]
        common=common.set_index("available_at")[names]
        path=directory/"raw_features.parquet"
        if path.exists(): raise ContractError("feature artifact already exists")
        common.to_parquet(path)
        result={"status":"RAW_FEATURES_BUILT","features":{"path":str(path.relative_to(root)),"sha256":file_digest(path)},
                "rows":len(common),"missing_rows":int(common.isna().any(axis=1).sum()),"columns":names,
                "availability":"4h bar close; zero declared archive publication delay","scaler":"NOT_FITTED"}
    elif kind == "fit_model":
        features=pd.read_parquet(verify_ref(root,inputs[task["features"]]))
        targets=read(verify_ref(root,inputs[task["targets"]]))["targets"]
        protocol=read(root/"configs/time_edge_validation_v4/r01/model_protocol.json")
        previous=next((v for v in request["dependencies"].values() if "model_id" in v and "design_trials" in v),None)
        result=fit_vintage(features,targets,cutoff=task["cutoff"],ready_at=task["ready_at"],protocol=protocol,previous=previous)
        result["status"]="MODEL_FITTED"
    elif kind == "emit":
        features=pd.read_parquet(verify_ref(root,inputs[task["features"]]))
        vintages=sorted(request["dependencies"].values(),key=lambda r:r["ready_at"])
        tape=[]
        for i,vintage in enumerate(vintages):
            until=vintages[i+1]["ready_at"] if i+1 < len(vintages) else task["end"]
            tape.extend(emit(vintage,features,until=until))
        result={"status":"EMITTED","emissions":tape,"model_registry":{v["model_id"]:{"design":v["design"],"dossier":v["dossier"],"mapping":v["mapping"]} for v in vintages}}
    elif kind == "targets":
        result=candidate_targets(root,request)
    elif kind == "statistical_calibration":
        from .controls import statistical_calibration
        result=statistical_calibration(task,directory=directory,lab_run_id=request["lab_run_id"])
    elif kind == "world":
        from .controls import generate_world
        result=generate_world(root,request)
    elif kind == "full_control":
        from .pipeline_controls import full_control
        result=full_control(root,request)
    else: raise ContractError("unsupported typed worker task")
    result.update(lab_run_id=request["lab_run_id"],source_identity=request["source_identity"],task_id=task["task_id"],
        measured_wall_seconds=time.perf_counter()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        cpu_seconds=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,
        affinity_cpus=len(os.sched_getaffinity(0)))
    if "alpha_id" in task: result["alpha_id"]=task["alpha_id"]
    if "cell_id" in task: result["cell_id"]=task["cell_id"]
    return jsonable(result)


def candidate_targets(root, request):
    from .eligibility import require_history
    task=request["task"]; inputs=request["inputs"]
    if pd.Timestamp(task["end"])-pd.Timestamp(task["origin"]) != pd.Timedelta(days=28):
        raise ContractError("candidate utility target must have the registered 28-day horizon")
    bank=read(verify_ref(root,inputs[task["candidate_bank"]]))
    if pd.Timestamp(bank["available_at"]) > pd.Timestamp(task["origin"]):
        raise ContractError("future candidate bank forbidden")
    if len(bank["candidates"]) < 2: raise ContractError("opportunity requires at least two candidates")
    frame=read_market(root,inputs[task["market"]],start=task["history_start"],end=task["end"])
    require_history(frame,task["alpha_id"],task["origin"])
    engine=PreparedAccount(frame,fee=task.get("fee",.0004),slippage=task.get("slippage",1.))
    utilities=[]; traces=[]; behaviors=[]; ids=[]
    for candidate in bank["candidates"]:
        sid=digest(candidate["params"])
        selected={"selection_id":sid,"params":candidate["params"],"cutoff":bank["available_at"],"ready_at":task["origin"]}
        run=engine.run(task["alpha_id"],[selected],account_start=task["origin"])
        if run["status"] != "EVALUATED": raise ContractError("candidate cohort incomplete; no winner-only target")
        rows=account_returns(run["equity"],run["index"],initial_equity=20000.,start=task["origin"],end=task["end"])
        utilities.append(describe(rows)["mean_daily_return"]); ids.append(sid)
        behavior=behavior_digest(run); behaviors.append(behavior)
        path=local(root,request["task_evidence"])/f"target-{sid}.json"
        save(path,{"lab_run_id":request["lab_run_id"],"candidate_id":sid,"daily_returns":rows,"fills":run["fills"],"commands":run["commands"],"order_events":run["order_events"],"behavior_hash":behavior})
        traces.append({"path":str(path.relative_to(root)),"sha256":file_digest(path)})
    target={"origin":task["origin"],"outcome_available_at":task["end"],"candidate_available_at":bank["available_at"],
            "candidate_ids":ids,"candidate_set_hash":digest(ids),"utilities":utilities,"engine_trace_hash":digest(traces),
            "economic_hash":digest({"fee":task.get("fee",.0004),"slippage":task.get("slippage",1.),"contract":CONTRACT}),"cell_id":task["cell_id"]}
    return {"status":"TARGET_EVALUATED","targets":[target],"traces":traces,
            "opportunity":{"candidate_count":len(ids),"unique_behaviors":len(set(behaviors)),"utility_range":max(utilities)-min(utilities),
                           "reason":"future realized opportunity is diagnostic; only mature targets can train a later model"}}


def behavior_digest(run):
    """Executed behavior excludes parameter/version IDs; identical flat paths tie."""
    return digest([{k:f[k] for k in ("bar_index","side","qty","price","fee","tag")} for f in run["fills"]])
