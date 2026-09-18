"""Bounded technical acceptance with captured subprocess output and source hashes."""
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from .runtime import local, source_identity
from .storage import file_digest, save, read, utcnow, digest


def verify_technical(root, run_id):
    root=Path(root); directory=local(root,f"evidence/time_edge_validation_v4/technical/{run_id}")
    if directory.exists(): raise ValueError("technical evidence exists; use a new run ID")
    directory.mkdir(parents=True)
    baseline=read(root/"evidence/time_edge_validation_v4/TE-01/te01-r01-20260912-01/protected_source_verification.json")["before"]
    before={r["path"]:file_digest(r["path"]) for r in baseline}
    baseline_drift=[r["path"] for r in baseline if before[r["path"]] != r["sha256"]]
    files=sorted(root.glob("tests/time_edge_validation_v4/test_te*.py"))
    files += [root/"tests/time_edge_validation_v4/test_registration_contracts.py"]
    command=[sys.executable,"-B","-m","pytest",*[str(p.relative_to(root)) for p in files],"-q","-p","no:cacheprovider",f"--junitxml={directory/'junit.xml'}"]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",NUMBA_CACHE_DIR=str(root/".cache/numba"),TMPDIR=str(root/".cache/tmp"),
             OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",MKL_NUM_THREADS="2")
    started=time.perf_counter()
    with (directory/"stdout.log").open("xb") as out, (directory/"stderr.log").open("xb") as err:
        try:
            process=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=err,timeout=300)
            exit_code=process.returncode; timed_out=False
        except subprocess.TimeoutExpired:
            exit_code=-1; timed_out=True
    suites=ET.parse(directory/"junit.xml").getroot().findall("testsuite") if (directory/"junit.xml").exists() else []
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ("tests","failures","errors","skipped")}
    cases=[{"name":c.get("classname")+"::"+c.get("name"),"seconds":float(c.get("time",0)),
            "status":"FAIL" if c.find("failure") is not None or c.find("error") is not None else "SKIP" if c.find("skipped") is not None else "PASS"}
           for s in suites for c in s.findall("testcase")]
    after={p:file_digest(p) for p in before}
    changed=[p for p in before if before[p] != after[p]]
    protected=subprocess.run(["git","-C",str(root.parent/"quantbt"),"status","--porcelain"],capture_output=True,text=True,check=True).stdout
    passed=exit_code == 0 and counts["tests"] > 0 and not changed and not baseline_drift and not protected
    payload={"lab_run_id":run_id,"created_at":utcnow(),"status":"TECHNICAL_TESTS_PASS" if passed else "FAILED",
        "source_identity":digest(source_identity(root)),"source_files":source_identity(root),
        "technical_tests":{"passed":counts["tests"]-counts["failures"]-counts["errors"]-counts["skipped"],
            "failed":counts["failures"],"errors":counts["errors"],"skipped":counts["skipped"],"total":counts["tests"]},
        "cases":cases,"command":command,"exit_code":exit_code,"timed_out":timed_out,
        "test_source_hashes":{str(p.relative_to(root)):file_digest(p) for p in files},
        "wall_seconds":time.perf_counter()-started,"child_peak_rss_kib":resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "engine_runs":0,"runtime_status":"NOT_QUALIFIED_BY_PURE_TECHNICAL_TESTS",
        "model_evaluation":"Synthetic math/causality tests only; no market model fit or learned full-engine calibration in this suite.",
        "protected_source_count":len(before),"protected_changed":changed,"quantbt_git_status":protected,
        "protected_drift_from_te01":baseline_drift,
        "protected_hashes_before":before,"protected_hashes_after":after,
        "known_legacy_before_repair_cases":"8 historical red assertions remain separate; canonical TE replacements are tested here, old RF/FUP outputs stay quarantined",
        "next_actions":[
            {"action":"TE-02: preflight → engine qualification → bounded training pilot.","reason":"measure actual fills, packing/runtime and account fidelity before wider jobs.","gate":"OS isolation and exact pinned source; stop at first failed task; shared allocation 1800 seconds."},
            {"action":"TE-03: raw features → mature candidate targets → model vintages/emissions.","reason":"evaluate label meaning and future parameter information per vintage.","gate":"no future target profile; full-path calibration cannot be replaced by structural-world generation."},
            {"action":"TE-04/05: paired accounts, fixed-theta decay, freeze/recompute/report.","reason":"economic conclusions need measured execution, support and calibration.","gate":"true pre-fill threshold binding, alpha/parity qualification and full-path power remain runtime prerequisites."}]}
    save(directory/"acceptance.json",payload)
    return {"lab_run_id":run_id,"status":payload["status"],"technical_tests":payload["technical_tests"],
            "wall_seconds":payload["wall_seconds"],"protected_source_count":len(before),
            "evidence":str((directory/"acceptance.json").relative_to(root)),"engine_runs":0}
