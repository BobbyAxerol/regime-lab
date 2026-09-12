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


def run_jobs(root, job, *, retry_failed=False, max_tasks=None, resume=False):
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
    done={}; count=0
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
                    done[task["task_id"]]=cached; continue
                if (directory/"STOP").exists() or (max_tasks is not None and count >= max_tasks): break
                if not all(dep in done for dep in task.get("depends_on",[])):
                    break  # dependent work may never consume a failed predecessor
                task_key=digest({"identity":ledger.identity,"task":task})
                previous=[a for a in ledger.status()["attempts"] if a["task"] == task_key]
                if previous and not retry_failed:
                    raise EvidenceError("previous failed/interrupted task requires --retry-failed; charged budget is retained")
                cap=float(task.get("wall_seconds",job["task_wall_seconds"]))
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
                    break
                env=lab_worker_env(policy,network=False,base={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","PYTHONPATH":str(root/"src")})
                env.update(PYTHONDONTWRITEBYTECODE="1",OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",MKL_NUM_THREADS="2",
                           NUMBA_NUM_THREADS="2",TE_ISOLATED_WORKER="1")
                command=build_bwrap_argv(policy,[str(root/"environments/lab_venv/bin/python"),"-B",
                    str(root/"scripts/run_time_edge.py"),"_worker","--request",str(request_path),"--output",str(output)],
                    env=env,extra_readonly=(root/"snapshots",root/"environments",root/"src",root/"configs"))
                started=time.monotonic(); reason=None; status="FAILED"; result=None
                with (attempt/"stdout.log").open("xb") as stdout, (attempt/"stderr.log").open("xb") as stderr:
                    try:
                        child=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True)
                    except OSError as exc:
                        reason=f"owned child failed to start: {type(exc).__name__}: {exc}"
                        wall=time.monotonic()-started
                        save(attempt/"receipt.json",{"lab_run_id":job["lab_run_id"],"task_id":task["task_id"],"status":"FAILED", "reason":reason,"wall_seconds":wall,"child_started":False})
                        ledger.finish(aid,status="FAILED",wall=wall,reason=reason)
                        allocation.finish(charged_id,status="FAILED",wall=wall,reason=reason)
                        break
                    try:
                        last_disk_check=started
                        while child.poll() is None:
                            if time.monotonic()-last_disk_check >= 10:
                                disk=disk_usage_report(policy); last_disk_check=time.monotonic()
                                if not disk["within_quota"]:
                                    reason="lab disk quota exceeded"; status="BLOCKED"
                                    os.killpg(child.pid,signal.SIGTERM)
                                    try: child.wait(timeout=3)
                                    except subprocess.TimeoutExpired:
                                        os.killpg(child.pid,signal.SIGKILL); child.wait()
                                    break
                            if (directory/"STOP").exists() or time.monotonic()-started >= cap:
                                status="CANCELLED" if (directory/"STOP").exists() else "TIMED_OUT"
                                reason="run-scoped stop request" if status == "CANCELLED" else "task wall cap reached"
                                os.killpg(child.pid,signal.SIGTERM)
                                try: child.wait(timeout=3)
                                except subprocess.TimeoutExpired:
                                    os.killpg(child.pid,signal.SIGKILL); child.wait()
                                break
                            time.sleep(.2)
                        if child.returncode == 0 and output.is_file() and reason is None:
                            result=read(output)
                            if result.get("status") in ("FAILED","BLOCKED","NOT_EVALUATED","NO_ADMISSIBLE_CANDIDATE"):
                                status="BLOCKED" if result["status"] == "BLOCKED" else "FAILED"
                                reason=result.get("reason",result["status"])
                            else: status="COMPLETE"
                        elif reason is None:
                            reason=f"isolated child exited {child.returncode}; see stderr.log"
                            if output.is_file(): result=read(output)
                    except BaseException:
                        if child.poll() is None:
                            os.killpg(child.pid,signal.SIGTERM)
                            try: child.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                os.killpg(child.pid,signal.SIGKILL); child.wait()
                        ledger.finish(aid,status="CANCELLED",wall=time.monotonic()-started,reason="parent interrupted; owned child reaped")
                        allocation.finish(charged_id,status="CANCELLED",wall=time.monotonic()-started,reason="parent interrupted; owned child reaped")
                        raise
                wall=time.monotonic()-started
                # Receipt binds request/result/logs even when no financial output exists.
                save(attempt/"receipt.json",{"lab_run_id":job["lab_run_id"],"task_id":task["task_id"],
                    "attempt_id":aid,"wall_seconds":wall,"status":status,"reason":reason,
                    "source_identity":job["source_identity"],"request_sha256":file_digest(request_path),
                    "stdout_sha256":file_digest(attempt/"stdout.log"),"stderr_sha256":file_digest(attempt/"stderr.log")})
                ledger.finish(aid,status=status,wall=wall,result=result,reason=reason)
                allocation.finish(charged_id,status=status,wall=wall,result={"lab_run_id":job["lab_run_id"],"attempt_id":aid,"status":status},reason=reason)
                count+=1
                if status != "COMPLETE": break
                done[task["task_id"]]=result
    finally:
        final=ledger.status(); final["allocation"]=allocation.status()
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
