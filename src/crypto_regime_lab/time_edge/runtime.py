"""One isolated, bounded child at a time; immutable job/input/source identities."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import math
import pandas as pd

from ..experiments.time_edge_contracts import load_registration, validate_registration
from ..safety.paths import SandboxPolicy
from ..safety.process import lab_worker_env, disk_usage_report
from ..safety.sandbox import build_bwrap_argv, probe_isolation
from .storage import Ledger, EvidenceError, check_allocation_revision, digest, file_digest, read, save, utcnow

KINDS = {"qualify", "select", "audit_selection", "deploy", "features", "fit_model", "emit", "targets", "world", "full_control", "decay", "statistical_calibration"}


def local(root, value):
    path=(Path(root)/value).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise EvidenceError("all TE input/output paths must stay in LAB_ROOT")
    return path


def source_identity(root):
    root=Path(root)
    files=[]
    for pattern in ("src/crypto_regime_lab/**/*.py","scripts/run_time_edge.py","scripts/te.sh","configs/time_edge_validation_v4/**/*.json",
                    "environments/lab_venv/lib/python*/site-packages/quantbt/**/*.py",
                    "environments/lab_venv/lib/python*/site-packages/quantbt/**/*.so",
                    "environments/lab_venv/lib/python*/site-packages/quantbt_native/**/*.py",
                    "environments/lab_venv/lib/python*/site-packages/quantbt_native/**/*.so",
                    "environments/lab_venv/lib/python*/site-packages/quantbt_native*.so",
                    "environments/lab_venv/lib/python*/site-packages/quantbt*dist-info/RECORD"):
        files.extend(root.glob(pattern))
    return {str(p.relative_to(root)):file_digest(p) for p in sorted(set(files))}


def verify_ref(root, reference):
    if not isinstance(reference,dict) or set(reference) != {"path","sha256"}:
        raise EvidenceError("reference requires exact path and sha256")
    p=local(root,reference["path"])
    if not p.is_file() or file_digest(p) != reference["sha256"]:
        raise EvidenceError("input drift or missing: "+str(p))
    return p


def validate_job(root, job):
    for field in ("lab_run_id","allocation_id","total_wall_seconds","task_wall_seconds","tasks","inputs","source_identity"):
        if field not in job: raise EvidenceError("job missing "+field)
    if job["source_identity"] != digest(source_identity(root)):
        raise EvidenceError("code/config changed; regenerate a new registered job identity")
    if not job["tasks"]: raise EvidenceError("empty task plan cannot pass")
    if not isinstance(job["lab_run_id"],str) or not job["lab_run_id"].replace("-","").replace("_","").isalnum():
        raise EvidenceError("unsafe lab_run_id")
    if not isinstance(job["allocation_id"],str) or not job["allocation_id"].replace("-","").replace("_","").isalnum():
        raise EvidenceError("unsafe allocation_id")
    for key in ("total_wall_seconds","task_wall_seconds"):
        if not math.isfinite(job[key]) or job[key] <= 0: raise EvidenceError("finite positive budget required")
    if job["total_wall_seconds"] > 1800 and not job.get("profile_refs"):
        raise EvidenceError("larger shared allocation requires measured profile references")
    for reference in job.get("profile_refs",[]): verify_ref(root,reference)
    if job.get("budget_revision") is not None:
        check_allocation_revision(job["allocation_id"],
            job["budget_revision"].get("prior_total_wall_seconds"),
            job["total_wall_seconds"], job["budget_revision"])
    seen=set()
    for task in job["tasks"]:
        if task["kind"] not in KINDS or task["task_id"] in seen:
            raise EvidenceError("unsupported or duplicate task")
        if not set(task.get("depends_on",[])) <= seen:
            raise EvidenceError("tasks must be topologically ordered; missing/cyclic dependency")
        seen.add(task["task_id"])
        if task["kind"] in ("deploy","decay") and pd.Timestamp(task["end"]) > pd.Timestamp("2021-01-01T00:00:00Z") and job.get("stage") not in ("discovery","decay"):
            raise EvidenceError("economic-window account cannot bypass discovery/decay prerequisites via another stage")
        if task["kind"] == "select" and pd.Timestamp(task["cutoff"]) >= pd.Timestamp("2021-01-01T00:00:00Z") and job.get("stage") != "discovery":
            raise EvidenceError("training-only pilot must precede the evaluation window")
        if job.get("stage") == "controls" and task["kind"] not in ("world","full_control"):
            raise EvidenceError("controls stage accepts only registered synthetic worlds/full-control tasks")
    for ref in job["inputs"].values(): verify_ref(root,ref)
    registration=load_registration(Path(root)/"configs/time_edge_validation_v4/r01")
    validate_registration(registration)
    if job.get("stage") in ("discovery","decay"):
        require_discovery_gate(root,job)


def require_discovery_gate(root, job):
    name=job.get("runtime_acceptance")
    if name not in job["inputs"]:
        raise EvidenceError("missing measured runtime acceptance bundle")
    gate=read(verify_ref(root,job["inputs"][name]))
    if gate.get("source_identity") != digest(source_identity(root)):
        raise EvidenceError("runtime acceptance source identity drift")
    for key in ("engine_clock","alpha_lifecycles","mode4_parity","account_reconciliation","model_causality","full_pipeline_calibration","economic_threshold"):
        proof=gate.get(key,{})
        if proof.get("status") != "PASS" or proof.get("denominator",0) <= 0 or not proof.get("artifact_refs"):
            raise EvidenceError("runtime prerequisite missing/failed: "+key)
        for reference in proof["artifact_refs"]: verify_ref(root,reference)
    from .eligibility import coverage
    if coverage(root)["blocked_cells"]:
        raise EvidenceError("registered initial history is incomplete; no hand-authored job may bypass the coverage gate")


def preflight(root):
    from .eligibility import coverage
    policy=SandboxPolicy.discover(root)
    registration=load_registration(Path(root)/"configs/time_edge_validation_v4/r01")
    validate_registration(registration)
    report=probe_isolation(policy).as_record()
    import importlib.metadata as md
    versions={p:md.version(p) for p in ("quantbt-engine","quantbt-native","numpy","pandas","optuna")}
    return {"lab_run_id":"TE-PREFLIGHT", "created_at":utcnow(),"registration":"PASS",
            "isolation":report,"versions":versions,"python":sys.executable,
            "source_identity":digest(source_identity(root)),
            "registered_data_eligibility":coverage(root),
            "runtime_status":"AVAILABLE_FOR_QUALIFICATION" if report["available"] else "BLOCKED_OS_ISOLATION",
            "engine_runs":0,"economic_conclusion":"NOT_EVALUABLE"}


def worker_cpu_sets(job):
    """Deterministic CPU slots for independent workers; total never exceeds cpu_limit.

    The host affinity is read once. ``workers`` is clamped to 4 (the registered
    envelope) and to ``cpu_limit`` so a slot is never empty; each slot receives
    ``cpu_limit // workers`` CPUs and its own thread cap.
    """
    affinity=sorted(os.sched_getaffinity(0))
    cpu_limit=max(1,min(int(job.get("cpu_limit",2)),len(affinity)))
    workers=max(1,min(int(job.get("workers",1)),4,cpu_limit,len(affinity)))
    per=max(1,cpu_limit//workers)
    sets=[affinity[i*per:(i+1)*per] for i in range(workers)]
    return [slot for slot in sets if slot]


def run_jobs(root, job, *, retry_failed=False, max_tasks=None, resume=False):
    """Run the job's task DAG with up to ``workers`` independent children.

    A child failure blocks only its dependents: independent shards keep running,
    which is the registered sharded-control contract. Every launch still reserves
    its full task cap in the shared allocation. No task is split, so per-arm
    compute (trials, seeds, windows, scorer) is untouched by scheduling.
    """
    root=Path(root); validate_job(root,job)
    policy=SandboxPolicy.discover(root)
    if not probe_isolation(policy).available:
        raise EvidenceError("BLOCKED_OS_ISOLATION: no engine/model worker launched")
    directory=local(root,f'evidence/time_edge_validation_v4/runs/{job["lab_run_id"]}')
    save(directory/"job.json",job)
    ledger=Ledger(directory,{"job_hash":digest(job)},job["total_wall_seconds"])
    allocation_dir=local(root,f'evidence/time_edge_validation_v4/allocations/{job["allocation_id"]}')
    allocation=Ledger(allocation_dir,{"allocation_id":job["allocation_id"]},job["total_wall_seconds"],
                      revision=job.get("budget_revision"))
    cpu_sets=worker_cpu_sets(job)
    slots={index:None for index in range(len(cpu_sets))}
    running={}; done={}; not_launched={}; attempted=set(); launched=0
    def task_key(task):
        return digest({"identity":ledger.identity,"task":task})
    def announce_never_launched(reason):
        for task in job["tasks"]:
            task_id=task["task_id"]
            if task_id not in done and task_id not in running and task_id not in attempted and task_id not in not_launched:
                not_launched[task_id]=reason
    def choose_next():
        if max_tasks is not None and launched >= max_tasks:
            return None
        for task in job["tasks"]:
            task_id=task["task_id"]
            if task_id in done or task_id in running or task_id in attempted or task_id in not_launched: continue
            if not all(dep in done for dep in task.get("depends_on",[])):
                continue  # dependent work may never consume a failed predecessor
            previous=[a for a in ledger.status()["attempts"] if a["task"] == task_key(task)]
            if previous and not retry_failed:
                raise EvidenceError("previous failed/interrupted task requires --retry-failed; charged budget is retained")
            return task
        return None
    def finish_child(task, state, status, reason, result=None):
        if status == "COMPLETE" and result is None:
            status="FAILED"; reason="child returned success without a result artifact"
        task_id=task["task_id"]; wall=time.monotonic()-state["started"]
        state["stdout"].close(); state["stderr"].close()
        attempt=state["attempt"]; charged_id=state["charged_id"]; aid=state["attempt_id"]
        # Receipt binds request/result/logs even when no financial output exists.
        save(attempt/"receipt.json",{"lab_run_id":job["lab_run_id"],"task_id":task_id,
            "attempt_id":aid,"wall_seconds":wall,"status":status,"reason":reason,
            "source_identity":job["source_identity"],"request_sha256":file_digest(state["request_path"]),
            "stdout_sha256":file_digest(attempt/"stdout.log"),"stderr_sha256":file_digest(attempt/"stderr.log")})
        ledger.finish(aid,status=status,wall=wall,result=result,reason=reason)
        allocation.finish(charged_id,status=status,wall=wall,
            result={"lab_run_id":job["lab_run_id"],"attempt_id":aid,"status":status},reason=reason)
        slots[state["slot"]]=None
        del running[task_id]
        if status == "COMPLETE":
            done[task_id]=result
            return True
        return False
    def launch(task, slot):
        task_id=task["task_id"]; cap=float(task.get("wall_seconds",job["task_wall_seconds"]))
        if allocation.spent()+cap > allocation.total+1e-9:
            not_launched[task_id]="TOTAL_BUDGET_EXHAUSTED: no remaining shared allocation for the registered cap"
            return False
        attempted.add(task_id)
        charged_id=allocation.begin({"job_hash":digest(job),"task":task},cap)
        try:
            aid=ledger.begin(task,cap)
        except BaseException:
            allocation.finish(charged_id,status="BLOCKED",wall=0.,reason="run ledger refused before worker launch")
            raise
        attempt=directory/"attempts"/aid; attempt.mkdir(parents=True,exist_ok=True)
        task_dir=directory/"tasks"/digest(task)
        task_dir.mkdir(parents=True,exist_ok=True)
        request={"lab_run_id":job["lab_run_id"],"task":task,"inputs":job["inputs"],
            "dependencies":{d:done[d] for d in task.get("depends_on",[])},
            "task_evidence":str(task_dir.relative_to(root)),"source_identity":job["source_identity"]}
        request_path=attempt/"request.json"; save(request_path,request)
        output=attempt/"worker_result.json"
        disk=disk_usage_report(policy)
        if not disk["within_quota"]:
            ledger.finish(aid,status="BLOCKED",wall=0.,reason="lab disk quota exceeded before child")
            allocation.finish(charged_id,status="BLOCKED",wall=0.,reason="lab disk quota exceeded before child")
            not_launched[task_id]="lab disk quota exceeded before child"
            return False
        cpus=cpu_sets[slot]
        env=lab_worker_env(policy,network=False,base={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","PYTHONPATH":str(root/"src")})
        env.update(PYTHONDONTWRITEBYTECODE="1",OMP_NUM_THREADS=str(len(cpus)),OPENBLAS_NUM_THREADS=str(len(cpus)),
                   MKL_NUM_THREADS=str(len(cpus)),NUMBA_NUM_THREADS=str(len(cpus)),TE_ISOLATED_WORKER="1")
        command=build_bwrap_argv(policy,[str(root/"environments/lab_venv/bin/python"),"-B",
            str(root/"scripts/run_time_edge.py"),"_worker","--request",str(request_path),"--output",str(output)],
            env=env,extra_readonly=(root/"snapshots",root/"environments",root/"src",root/"configs"))
        stdout=(attempt/"stdout.log").open("xb"); stderr=(attempt/"stderr.log").open("xb")
        started=time.monotonic()
        try:
            child=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True,
                preexec_fn=lambda: os.sched_setaffinity(0,set(cpus)))
        except OSError as exc:
            stdout.close(); stderr.close()
            reason=f"owned child failed to start: {type(exc).__name__}: {exc}"
            wall=time.monotonic()-started
            save(attempt/"receipt.json",{"lab_run_id":job["lab_run_id"],"task_id":task_id,"status":"FAILED",
                "reason":reason,"wall_seconds":wall,"child_started":False})
            ledger.finish(aid,status="FAILED",wall=wall,reason=reason)
            allocation.finish(charged_id,status="FAILED",wall=wall,reason=reason)
            not_launched[task_id]="owned child failed to start; see receipt"
            return False
        slots[slot]=task_id
        running[task_id]={"task":task,"child":child,"attempt":attempt,"output":output,"attempt_id":aid,
            "charged_id":charged_id,"request_path":request_path,"started":started,"cap":cap,"slot":slot,
            "stdout":stdout,"stderr":stderr}
        return True
    try:
        with allocation.lock(), ledger.lock():
            if resume and (directory/"STOP").exists():
                marker=read(directory/"STOP")
                save(directory/"stop_history"/(digest(marker)+".json"),marker)
                (directory/"STOP").unlink()
                retry_failed=True
            allocation.recover_interrupted()
            ledger.recover_interrupted()
            for task in job["tasks"]:
                cached=ledger.cached(task)
                if cached is not None:
                    done[task["task_id"]]=cached
            last_disk_check=time.monotonic()
            while True:
                stop_requested=(directory/"STOP").exists()
                for task_id,state in list(running.items()):
                    child=state["child"]; reason=None; status=None; result=None
                    if child.poll() is not None:
                        if child.returncode == 0 and state["output"].is_file():
                            result=read(state["output"])
                            if result.get("status") in ("FAILED","BLOCKED","NOT_EVALUATED","NO_ADMISSIBLE_CANDIDATE"):
                                status="BLOCKED" if result["status"] == "BLOCKED" else "FAILED"
                                reason=result.get("reason",result["status"])
                            else: status="COMPLETE"
                        else:
                            status="FAILED"; reason=f"isolated child exited {child.returncode}; see stderr.log"
                            if state["output"].is_file(): result=read(state["output"])
                        finish_child(state["task"],state,status,reason,result); continue
                    if stop_requested:
                        os.killpg(child.pid,signal.SIGTERM)
                        try: child.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid,signal.SIGKILL); child.wait()
                        finish_child(state["task"],state,"CANCELLED","run-scoped stop request"); continue
                    if time.monotonic()-state["started"] >= state["cap"]:
                        os.killpg(child.pid,signal.SIGTERM)
                        try: child.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid,signal.SIGKILL); child.wait()
                        finish_child(state["task"],state,"TIMED_OUT","task wall cap reached")
                if stop_requested:
                    announce_never_launched("run-scoped stop request before launch")
                    break
                if time.monotonic()-last_disk_check >= 10:
                    last_disk_check=time.monotonic()
                    if not disk_usage_report(policy)["within_quota"]:
                        for state in list(running.values()):
                            child=state["child"]
                            os.killpg(child.pid,signal.SIGTERM)
                            try: child.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                os.killpg(child.pid,signal.SIGKILL); child.wait()
                            finish_child(state["task"],state,"BLOCKED","lab disk quota exceeded")
                        announce_never_launched("lab disk quota exceeded; independent shards stopped")
                        break
                while any(slot is None for slot in slots.values()):
                    task=choose_next()
                    if task is None: break
                    slot=next(index for index,value in slots.items() if value is None)
                    if not launch(task,slot):
                        break
                    launched+=1
                if not running:
                    reason="no launchable task remains (dependencies blocked or budget exhausted)"
                    announce_never_launched(reason)
                    break
                time.sleep(.2)
    finally:
        for state in list(running.values()):
            child=state["child"]
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL); child.wait()
            finish_child(state["task"],state,"CANCELLED","parent interrupted; owned child reaped")
        final=ledger.status(); final["allocation"]=allocation.status()
        final["workers"]=len(cpu_sets); final["cpu_sets"]=[list(slot) for slot in cpu_sets]
        final["not_launched"]=not_launched
        ledger.close(); allocation.close()
    return final


def status(root, run_id):
    directory=local(root,f"evidence/time_edge_validation_v4/runs/{run_id}")
    job=read(directory/"job.json")
    ledger=Ledger(directory,{"job_hash":digest(job)},job["total_wall_seconds"])
    try: return ledger.status()
    finally: ledger.close()


def stop(root, run_id):
    directory=local(root,f"evidence/time_edge_validation_v4/runs/{run_id}")
    if not (directory/"job.json").is_file(): raise EvidenceError("unknown run; no stop sent")
    if not (directory/"STOP").exists():
        save(directory/"STOP",{"lab_run_id":run_id,"requested_at":utcnow()})
    return {"lab_run_id":run_id,"status":"STOP_REQUESTED","scope":"only child owned by this run"}
