"""Owned-child fault injection only: no model fit, market load or engine call."""
import json
from types import SimpleNamespace

import pytest

from crypto_regime_lab.time_edge import runtime
from crypto_regime_lab.time_edge.storage import read, save


def harness(monkeypatch,lab_tmp,policy,lab_root, *, delay=0., outcome="OK"):
    monkeypatch.setattr(runtime,"validate_job",lambda *args:None)
    monkeypatch.setattr(runtime.SandboxPolicy,"discover",lambda root:policy)
    monkeypatch.setattr(runtime,"probe_isolation",lambda p:SimpleNamespace(available=True))
    monkeypatch.setattr(runtime,"disk_usage_report",lambda p:{"within_quota":True})
    def synthetic_child(policy,argv,**kwargs):
        output=argv[-1]
        # argv is passed directly to Popen. This fixture does not pretend to be
        # OS isolation; it only tests parent cancellation and durable accounting.
        program="import pathlib,time; time.sleep("+repr(delay)+"); pathlib.Path("+repr(output)+").write_text("+repr(json.dumps({"status":outcome,"lab_run_id":"fault-test"}))+ ")"
        return [str(lab_root/"environments/lab_venv/bin/python"),"-B","-c",program]
    monkeypatch.setattr(runtime,"build_bwrap_argv",synthetic_child)
    def job(name, cap=.4,total=2.):
        return {"lab_run_id":name,"allocation_id":"fault-allocation","total_wall_seconds":total,
                "task_wall_seconds":cap,"source_identity":"unit-fixture","inputs":{},
                "tasks":[{"task_id":"child","kind":"qualify"}]}
    return job


def test_owned_child_timeout_is_persisted(monkeypatch,lab_tmp,policy,lab_root):
    job=harness(monkeypatch,lab_tmp,policy,lab_root,delay=10.)
    result=runtime.run_jobs(lab_tmp,job("timeout"))
    assert result["attempts"][0]["status"] == "TIMED_OUT"
    assert .3 <= result["charged_wall_seconds"] < 4
    receipt=list((lab_tmp/"evidence").rglob("receipt.json"))
    assert len(receipt) == 1 and read(receipt[0])["status"] == "TIMED_OUT"


def test_child_start_failure_closes_both_ledgers(monkeypatch,lab_tmp,policy,lab_root):
    job=harness(monkeypatch,lab_tmp,policy,lab_root)
    monkeypatch.setattr(runtime,"build_bwrap_argv",lambda *args,**kwargs:[str(lab_tmp/"missing-executable")])
    result=runtime.run_jobs(lab_tmp,job("start-failed"))
    assert result["attempts"][0]["status"] == "FAILED"
    assert result["allocation"]["attempts"][0]["status"] == "FAILED"
    assert read(next((lab_tmp/"evidence").rglob("receipt.json")))["child_started"] is False


def test_allocation_shared_across_run_ids_and_cached_success(monkeypatch,lab_tmp,policy,lab_root):
    job=harness(monkeypatch,lab_tmp,policy,lab_root)
    first=runtime.run_jobs(lab_tmp,job("first"))
    second=runtime.run_jobs(lab_tmp,job("second"))
    assert first["attempts"][0]["status"] == "COMPLETE"
    assert len(second["allocation"]["attempts"]) == 2
    assert second["allocation"]["charged_wall_seconds"] > first["charged_wall_seconds"]
    cached=runtime.run_jobs(lab_tmp,job("first"))
    assert len(cached["allocation"]["attempts"]) == 2 and len(cached["attempts"]) == 1


def test_stop_resume_keeps_receipt_and_budget(monkeypatch,lab_tmp,policy,lab_root):
    job=harness(monkeypatch,lab_tmp,policy,lab_root)
    config=job("stopped"); directory=lab_tmp/"evidence/time_edge_validation_v4/runs/stopped"
    save(directory/"job.json",config)
    runtime.stop(lab_tmp,"stopped")
    assert runtime.run_jobs(lab_tmp,config)["attempts"] == []
    result=runtime.run_jobs(lab_tmp,config,resume=True)
    assert result["attempts"][0]["status"] == "COMPLETE"
    assert len(list((directory/"stop_history").glob("*.json"))) == 1
    assert not (directory/"STOP").exists()


def test_failure_never_runs_dependent_child(monkeypatch,lab_tmp,policy,lab_root):
    job=harness(monkeypatch,lab_tmp,policy,lab_root,outcome="FAILED")
    config=job("failed"); config["tasks"].append({"task_id":"dependent","kind":"qualify","depends_on":["child"]})
    result=runtime.run_jobs(lab_tmp,config)
    assert len(result["attempts"]) == 1 and result["attempts"][0]["status"] == "FAILED"
    with pytest.raises(ValueError,match="retry-failed"):
        runtime.run_jobs(lab_tmp,config)


def test_worker_refuses_plain_host_before_engine_import(lab_root):
    from crypto_regime_lab.time_edge.workers import require_isolated
    with pytest.raises(ValueError,match="requires measured"):
        require_isolated(lab_root)


def test_plan_without_source_or_empty_tasks_cannot_pass(lab_root):
    from crypto_regime_lab.time_edge.runtime import validate_job
    with pytest.raises(ValueError,match="code/config changed"):
        validate_job(lab_root,{"lab_run_id":"bad","allocation_id":"bad","source_identity":"wrong","inputs":{},"tasks":[],"total_wall_seconds":1,"task_wall_seconds":1})
