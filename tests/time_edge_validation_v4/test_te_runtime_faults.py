"""Owned-child fault injection only: no model fit, market load or engine call."""
import json
from types import SimpleNamespace

import pytest

from crypto_regime_lab.time_edge import runtime
from crypto_regime_lab.time_edge.storage import (ALLOCATION_REVISION_SCHEMA, Ledger, digest,
                                                 file_digest, read, save)


def allocation_revision(allocation_id, prior_total, total, prior_charged):
    return {"schema": ALLOCATION_REVISION_SCHEMA, "revision_id": "unit-revision-1",
            "allocation_id": allocation_id, "prior_total_wall_seconds": prior_total,
            "total_wall_seconds": total, "prior_charged_wall_seconds": prior_charged,
            "task_wall_seconds": 1.0, "selection_task_wall_seconds": 2.0, "workers": 1,
            "cpu_limit": 2, "memory_gib": 4,
            "profile_refs": [{"path":"unit-profile.json","sha256":"0"*64}],
            "per_arm_compute_is_unchanged": True,
            "how_arms_stay_equal": "one sequential selection shared by every arm",
            "measured_reason": {"trials_completed": 10}, "what_it_costs": "wall clock only",
            "what_it_changes": ["task cap"], "what_it_does_not_change": ["per-arm compute"]}


def test_allocation_revision_appends_and_keeps_prior_charges(lab_tmp):
    directory=lab_tmp/"allocations/revised"
    ledger=Ledger(directory,{"allocation_id":"revised"},2.0)
    attempt=ledger.begin({"task":"first"},1.0)
    ledger.finish(attempt,status="COMPLETE",wall=.5,result={"status":"OK"})
    ledger.close()
    opened=Ledger(directory,{"allocation_id":"revised"},5.0,
                  revision=allocation_revision("revised",2.0,5.0,.5))
    try:
        status=opened.status()
        assert status["allocated_wall_seconds"] == 5.0
        assert status["charged_wall_seconds"] == .5, "prior charges survive the revision"
        assert status["remaining_wall_seconds"] == 4.5
        assert [r["id"] for r in status["budget_revisions"]] == ["unit-revision-1"]
        assert status["budget_revisions"][0]["old_budget"] == 2.0
    finally:
        opened.close()


def test_allocation_revision_cannot_slip_past_the_live_ledger(lab_tmp):
    directory=lab_tmp/"allocations/restamped"
    ledger=Ledger(directory,{"allocation_id":"restamped"},2.0)
    attempt=ledger.begin({"task":"first"},1.0)
    ledger.finish(attempt,status="COMPLETE",wall=.5,result={"status":"OK"})
    ledger.close()
    with pytest.raises(ValueError,match="must increase"):
        Ledger(directory,{"allocation_id":"restamped"},1.5,
               revision=allocation_revision("restamped",2.0,1.5,.5)).close()
    with pytest.raises(ValueError,match="prior charged"):
        Ledger(directory,{"allocation_id":"restamped"},5.0,
               revision=allocation_revision("restamped",2.0,5.0,99.)).close()
    with pytest.raises(ValueError,match="prior budget"):
        Ledger(directory,{"allocation_id":"restamped"},5.0,
               revision=allocation_revision("restamped",1.0,5.0,.5)).close()
    with pytest.raises(ValueError,match="identity/budget drift|identity drift"):
        Ledger(directory,{"allocation_id":"restamped"},5.0).close()
    with pytest.raises(ValueError,match="per-arm"):
        bad=allocation_revision("restamped",2.0,5.0,.5); bad["per_arm_compute_is_unchanged"]=False
        Ledger(directory,{"allocation_id":"restamped"},5.0,revision=bad).close()


def test_validate_job_checks_a_registered_allocation_revision(monkeypatch,lab_tmp):
    profile=lab_tmp/"evidence/selection-profile.json"; save(profile,{"measured":True})
    refs=[{"path":"evidence/selection-profile.json","sha256":file_digest(profile)}]
    revision=allocation_revision("revised",2.0,5.0,.5); revision["profile_refs"]=refs
    monkeypatch.setattr(runtime,"source_identity",lambda root:{})
    monkeypatch.setattr(runtime,"load_registration",lambda path:{})
    monkeypatch.setattr(runtime,"validate_registration",lambda registration:None)
    job={"lab_run_id":"revision-run","allocation_id":"revised","total_wall_seconds":5.0,
         "task_wall_seconds":1.0,"source_identity":digest({}),"inputs":{},
         "tasks":[{"task_id":"child","kind":"qualify","wall_seconds":1.0}],
         "profile_refs":refs,"budget_revision":revision}
    runtime.validate_job(lab_tmp,job)
    revision["per_arm_compute_is_unchanged"]=False
    with pytest.raises(ValueError,match="per-arm"):
        runtime.validate_job(lab_tmp,job)


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
