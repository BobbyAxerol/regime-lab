"""Meaningful cold/window boundary, listing, and artifact/report regressions."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.experiments.time_edge_contracts import ContractError
from crypto_regime_lab.time_edge.eligibility import coverage, history_days, require_history
from crypto_regime_lab.time_edge.execution import ClockedStrategy
from crypto_regime_lab.time_edge.model_evaluation import operational_folds, evaluate_vintages
from crypto_regime_lab.time_edge.storage import digest, save, file_digest
from crypto_regime_lab.time_edge import reporting, runtime


def test_warmup_bound_covers_full_vwap_space_and_listing_audit(lab_root):
    assert history_days("A-VWAP") == 101
    assert history_days("A-HMA") == 18
    result=coverage(lab_root)
    assert result["planned_cells"] == 20 and result["boundary_eligible_cells"] == 12
    assert len(result["blocked_cells"]) == 8
    assert all("SOLUSDT" in c or "DOGEUSDT" in c for c in result["blocked_cells"])
    frame=pd.DataFrame(index=pd.date_range("2020-12-01",periods=31,freq="D",tz="UTC"))
    with pytest.raises(ContractError,match="indicator history"):
        require_history(frame,"A-VWAP","2020-12-31T00:00:00Z")


def test_cold_path_cannot_place_on_last_warmup_bar():
    idx=pd.date_range("2020-01-01",periods=1440,freq="min",tz="UTC")
    frame=pd.DataFrame({c:np.ones(len(idx)) for c in ("open","high","low","close","volume")},index=idx)
    start=idx[900]
    strategy=ClockedStrategy("A-SC",frame,[{"selection_id":"v","params":{},"cutoff":start.isoformat(),"ready_at":start.isoformat()}],account_start=start)
    assert strategy.on_bar_close(SimpleNamespace(bar_index=899,fills_this_bar=[])) == []
    assert strategy.next_selection == 0 and strategy.funnel == []
    with pytest.raises(ContractError,match="before the registered account"):
        strategy.on_bar_close(SimpleNamespace(bar_index=899,fills_this_bar=[object()]))


def test_operational_fold_links_models_and_keeps_missing_dossier():
    account={"cell_id":"a/b","arm":"M4_REGIME","score_start":"2021-01-01T00:00:00Z","score_end_exclusive":"2021-01-04T00:00:00Z",
        "selections":[{"selection_id":"s","params":{"p":1},"cutoff":"2020-12-31T00:00:00Z","ready_at":"2020-12-31T00:01:00Z","model_id":"m1"}],
        "daily_returns":[("2021-01-01",.01),("2021-01-02",-.01),("2021-01-03",.02)],"funnel":[]}
    tape=[{"model_id":"m2","available_at":"2021-01-02T00:00:00Z","quality_status":"UNKNOWN"}]
    row=operational_folds(account,tape,{})[0]
    assert row["model_at_selection"] == "m1" and row["unknown_count"] == 1
    assert row["metrics"]["days"] == 3 and row["activation"] is None
    assert row["model_reports"][0]["status"] == "MISSING_DOSSIER"


def test_deployed_information_rejects_changed_training_features():
    features=pd.DataFrame({"x":[1.,2.]},index=pd.date_range("2020-01-01",periods=2,freq="D",tz="UTC"))
    v={"model_id":"m","cutoff":"2020-01-03T00:00:00Z","ready_at":"2020-01-03T00:01:00Z","history_start":"2020-01-01T00:00:00Z",
       "feature_names":["x"],"training_raw_hash":digest([[1.],[999.]])}
    with pytest.raises(ContractError,match="features differ"):
        evaluate_vintages([v],features,[],[],end="2021-01-01T00:00:00Z")


def test_full_registered_model_ladder_and_actual_outer_dossier(lab_root):
    """Actual model mathematics on synthetic raw features; no market or engine."""
    from crypto_regime_lab.time_edge.model import fit_vintage, emit
    from crypto_regime_lab.time_edge.storage import read
    protocol=read(lab_root/"configs/time_edge_validation_v4/r01/model_protocol.json")
    idx=pd.date_range("2020-01-01",periods=365*6+18,freq="4h",tz="UTC")
    raw=np.random.default_rng(182).normal(0,.1,(len(idx),8))+np.repeat(np.sin(np.arange(len(idx))[:,None]/80),8,axis=1)
    features=pd.DataFrame(raw,index=idx,columns=protocol["features"])
    cutoff=idx[365*6]; ready=cutoff+pd.Timedelta(minutes=1); end=idx[-1]+pd.Timedelta(hours=4)
    vintage=fit_vintage(features,[],cutoff=cutoff.isoformat(),ready_at=ready.isoformat(),protocol=protocol)
    assert len(vintage["design_trials"]) == 7
    assert vintage["decision"] == "NO_PROMISING_DESIGN_M0_CONTROL"
    assert vintage["fit_quality"] == "OK"
    assert all(not trial["admissible"] for trial in vintage["design_trials"])
    tape=emit(vintage,features,until=end.isoformat())
    report=evaluate_vintages([vintage],features,[],tape,end=end.isoformat())
    assert report["model_table"][0]["mean_outer_information_effect"] is None
    assert report["model_table"][0]["planned_outer_targets"] == 0
    assert vintage["dossier"]["state_profiles"][0]["raw_feature_std_ddof1"] is not None


def test_freeze_detects_input_and_source_drift_without_engine(monkeypatch,lab_tmp):
    save(lab_tmp/"evidence.json",{"lab_run_id":"fixture","value":1})
    reference={"path":"evidence.json","sha256":file_digest(lab_tmp/"evidence.json")}
    monkeypatch.setattr(reporting,"require_committed",lambda *args:None)
    monkeypatch.setattr(reporting,"source_identity",lambda root:{"code":"one"})
    frozen=reporting.freeze(lab_tmp,[reference],"freeze.json",lab_run_id="fixture")
    assert reporting.verify_freeze(lab_tmp,frozen)["status"] == "VERIFIED"
    monkeypatch.setattr(reporting,"source_identity",lambda root:{"code":"two"})
    assert reporting.verify_freeze(lab_tmp,frozen)["status"] == "FAILED_SOURCE_DRIFT"
    (lab_tmp/"evidence.json").write_text("{}")
    with pytest.raises(ValueError,match="drift"):
        reporting.verify_freeze(lab_tmp,frozen)


def test_real_report_rejects_uncommitted_input(lab_root,lab_tmp):
    save(lab_tmp/"uncommitted.json",{"lab_run_id":"fixture"})
    with pytest.raises(ContractError,match="committed and unchanged"):
        reporting.require_committed(lab_root,[lab_tmp/"uncommitted.json"])


def test_discovery_cannot_open_from_boolean_prerequisites(monkeypatch,lab_tmp):
    save(lab_tmp/"gate.json",{"source_identity":digest({}),"engine_clock":{"status":"PASS","denominator":0,"artifact_refs":[]}})
    monkeypatch.setattr(runtime,"source_identity",lambda root:{})
    with pytest.raises(ValueError,match="engine_clock"):
        runtime.require_discovery_gate(lab_tmp,{"runtime_acceptance":"gate","inputs":{"gate":{"path":"gate.json","sha256":file_digest(lab_tmp/"gate.json")}}})


def test_calibration_checkpoint_resumes_after_interruption(monkeypatch,lab_tmp):
    from crypto_regime_lab.time_edge import controls
    calls=[]
    def estimate(*args,**kwargs):
        calls.append(float(np.asarray(args[0]).sum()))
        if len(calls) == 4: raise RuntimeError("injected stop between worlds")
        return {"p_one_sided":1.,"ci_simultaneous_basic":[-1.,1.]}
    monkeypatch.setattr(controls,"block_mean",estimate)
    monkeypatch.setattr(controls,"block_weighted",lambda *a,**k:{"p_one_sided":1.,"ci_simultaneous_basic":[-1.,1.]})
    task={"delta":.001,"repetitions":1000,"days":560,"draws":4999,"seed":12}
    with pytest.raises(RuntimeError,match="injected stop"):
        controls.statistical_calibration(task,directory=lab_tmp,lab_run_id="fixture")
    first=lab_tmp/"calibration-0-0000.json"; original=file_digest(first)
    calls.clear()
    with pytest.raises(RuntimeError,match="injected stop"):
        controls.statistical_calibration(task,directory=lab_tmp,lab_run_id="fixture")
    assert file_digest(first) == original and (lab_tmp/"calibration-0-0001.json").exists()
