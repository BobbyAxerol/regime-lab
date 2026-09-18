"""TE03-05/TG05-09,12: adversarial causality and independent statistical oracles."""
import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.experiments.time_edge_contracts import ContractError
from crypto_regime_lab.time_edge.storage import digest, save
from crypto_regime_lab.time_edge.model import target_rows, information, map_states, emit, dossier, _fit
from crypto_regime_lab.time_edge.inference import block_mean, block_weighted, fixed_cohort, family, HYPOTHESES, calibration_decision, wilson
from crypto_regime_lab.time_edge.decay import anchors, age_windows, matched_decay, d1, d3
from crypto_regime_lab.time_edge.reporting import analyse_accounts, gate_claims
from crypto_regime_lab.time_edge.runtime import local, validate_job
from crypto_regime_lab.time_edge.planning import make_plan
from crypto_regime_lab.time_edge.controls import full_path_funnel


def target(origin, available, values=(1.,2.,3.)):
    ids=["a","b","c"]
    return {"origin":origin,"outcome_available_at":available,"candidate_available_at":"2019-01-01T00:00:00Z",
            "candidate_ids":ids,"candidate_set_hash":digest(ids),"utilities":list(values),
            "engine_trace_hash":"trace","economic_hash":"econ","cell_id":"A-SC/BTCUSDT"}


def test_target_tail_purge_and_equal_time_exclusion():
    rows=[target("2020-01-01T00:00:00Z",t) for t in ("2020-01-29T00:00:00Z","2020-02-01T00:00:00Z","2020-02-02T00:00:00Z")]
    selected=target_rows(rows,before="2020-02-01T00:00:00Z")
    assert len(selected) == 1 and selected[0]["outcome_available_at"] == "2020-01-29T00:00:00Z"
    rows[-1]["utilities"]=[100000.,0.,-100000.]
    assert target_rows(rows,before="2020-02-01T00:00:00Z") == selected


def test_future_candidate_bank_rejected():
    row=target("2020-01-01T00:00:00Z","2020-02-01T00:00:00Z")
    row["candidate_available_at"]="2020-01-02T00:00:00Z"
    with pytest.raises(ContractError): target_rows([row],before="2020-03-01T00:00:00Z")


def test_real_learned_jm_fit_is_train_only_math():
    raw=np.r_[np.zeros((30,3)),np.ones((30,3))*3]+np.random.default_rng(1).normal(0,.1,(60,3))
    design={"kind":"JM","k":2,"lambda":1.}
    scaler,fit,states=_fit(raw,design,np.full(3,1/3),[11,23])
    assert len(set(states)) == 2 and len(fit["runs"]) == 2
    assert scaler["fitted_rows"] == 60
    assert all(r["objective_monotone_nonincreasing"] for r in fit["runs"])


def test_information_future_parameter_ranking_not_price_direction():
    idx=pd.date_range("2020-01-01",periods=6,freq="D",tz="UTC"); states=np.array([0,0,1,1,0,1])
    train=[target(idx[i].isoformat(),(idx[i]+pd.Timedelta(hours=1)).isoformat(),values) for i,values in enumerate(((3,2,0),(4,2,0),(0,2,3),(0,2,4)))]
    valid=[target(idx[i].isoformat(),(idx[i]+pd.Timedelta(hours=1)).isoformat(),values) for i,values in ((4,(3,2,0)),(5,(0,2,3)))]
    info=information(train,valid,idx,states)
    assert info["evaluable"] == 2 and all(r["regime_rank_ic"] == pytest.approx(1.) for r in info["rows"])
    assert info["mean_incremental_rank_ic"] > 0


def test_state_mapping_common_raw_coordinates_and_ambiguity():
    a=np.array([[1.,10.],[3.,20.]])
    mapped=map_states(a,a[::-1],[1.,10.])
    assert mapped["mapping"] == {"1":0,"0":1}
    assert map_states(a,np.array([[2.,15.],[2.,15.]]),[1.,10.])["status"] == "AMBIGUOUS"


def test_emission_suffix_ready_and_warmed_filter():
    idx=pd.date_range("2020-01-01",periods=8,freq="4h",tz="UTC")
    data=pd.DataFrame({"x":[.1,.9,.9,.1,.2,.9,.1,.2]},index=idx)
    v={"model_id":"m","cutoff":idx[0].isoformat(),"ready_at":idx[1].isoformat(),"design":{"kind":"JM","k":2,"lambda":1.},
       "fit":{"centroids":[[0.],[1.]]},"weights":[1.],"training_terminal_cost":[0.,5.],
       "scaler":{"median":[0.],"scale":[1.],"clip":5.},"mapping":{"mapping":{"0":0,"1":1}},
       "feature_names":["x"],"feature_schema_hash":"f","model_design_hash":"d"}
    tape=emit(v,data,until=(idx[-1]+pd.Timedelta(hours=4)).isoformat())
    altered=data.copy(); altered.iloc[4:]=100000
    other=emit(v,altered,until=(idx[-1]+pd.Timedelta(hours=4)).isoformat())
    assert tape[:3] == other[:3] and len(tape) == 7
    assert tape[0]["state_id"] == 0 and tape[0]["available_at"] == idx[1].isoformat()


def test_dossier_denominators_and_no_fake_label_accuracy():
    d=dossier(np.array([[1.],[2.],[3.],[4.]]),[0,0,1,1],k=3,features=["x"])
    assert d["occupancy_counts"] == [2,2,0] and d["dead_states"] == [2]
    assert d["transition_denominator"] == 3 and d["recurrence_episodes"] == 2
    assert d["market_label_accuracy"] is None


def test_block_bootstrap_matches_slow_independent_oracle():
    x=np.array([1.,3.,-2.,4.,0.,8.,-3.]); b=3; draws=999; seed=72
    rng=np.random.default_rng(seed); centered=x-x.mean(); values=[]
    # Same prescribed circular sampling, explicit element-by-element oracle.
    for _ in range(draws):
        starts=rng.integers(0,len(x),size=3)
        indices=[(int(s)+k)%len(x) for s in starts for k in range(b)][:len(x)]
        values.append(centered[indices].mean())
    got=block_mean(x,delta=.3,block=b,draws=draws,seed=seed)
    q=np.quantile(values,[.05/8,1-.05/8])
    assert got["ci_simultaneous_basic"] == pytest.approx([x.mean()-q[1],x.mean()-q[0]])
    assert got["p_one_sided"] == (1+sum(v >= x.mean()-.3 for v in values))/(draws+1)


def test_family_includes_four_when_missing_hypotheses():
    series={h:None for h in HYPOTHESES}; series["H-TIMING"]=[.01+np.sin(i)*.001 for i in range(365)]
    result=family(series,{h:0. for h in HYPOTHESES},draws=999)
    p=result["H-TIMING"]["p_one_sided"]
    assert result["H-TIMING"]["adjusted_p"] == pytest.approx(4*p)
    assert result["H-DECAY"]["estimate"] is None and result["H-DECAY"]["adjusted_p"] == 1


def test_fixed_cohort_never_changes_weights_by_day():
    result=fixed_cohort({"a":[("2020-01-01",1), ("2020-01-02",2)],"b":[("2020-01-02",10)]},["a","b","c"])
    assert result["values"] == [6] and result["fixed_weight"] == .5
    assert result["full_cohort"] is False and result["excluded_cells"] == ["c"]


def test_weighted_information_constant_effect_and_zero_weight_dates():
    weights=np.zeros(730); weights[::14]=1
    result=block_weighted(weights*.4,weights,delta=0.,draws=999)
    assert result["estimate"] == pytest.approx(.4)
    assert result["ci_simultaneous_basic"] == pytest.approx([.4,.4])
    assert result["episodes"] == 53


def test_twenty_worlds_cannot_certify_fwer():
    result=calibration_decision(0,20,20)
    assert result["status"] == "CALIBRATION_INCONCLUSIVE" and result["null_wilson95"][1] > .08
    assert wilson(0,100)[1] < .08


def returns(n=270,value=.001):
    return [(d.date().isoformat(),value) for d in pd.date_range("2020-01-01",periods=n,freq="D")]


def test_exact_age_90_days_and_no_overlap():
    result=age_windows(returns(),ready_at="2020-01-01T00:00:00Z")
    assert [r["metrics"]["days"] for r in result] == [90,90,90]
    assert result[0]["end_exclusive"] == result[1]["start"]
    with pytest.raises(ContractError): age_windows(returns(269),ready_at="2020-01-01T00:00:00Z")


def test_anchor_choice_timestamp_not_best_outcome():
    rows=[{"selection_id":str(i),"ready_at":f"2020-01-0{i}T00:00:00Z","status":"SELECTED","params":{"p":i},"cell_id":"c","arm":"M4_CAL","future_profit":i*100} for i in (2,1)]
    result=anchors(rows,end="2021-01-01T00:00:00Z")
    assert [r["selection_id"] for r in result["anchors"]] == ["1"]


def test_decay_cal_minus_regime_sign_and_joint_calendar_influence():
    cal=returns(); reg=returns()
    cal=[(d,.003 if i < 90 else .001) for i,(d,v) in enumerate(cal)]
    records=[]
    for arm,rs in (("M4_CAL",cal),("M4_REGIME",reg)):
        records.append({"cell_id":"c","arm":arm,"quarter":"2020Q1","context_key":"ctx","selection_id":arm,
                        "ready_at":"2020-01-01T00:00:00Z","age_windows":age_windows(rs,ready_at="2020-01-01T00:00:00Z")})
    result=matched_decay(records)
    assert result["effect"] == pytest.approx(.002)
    assert np.mean([v for d,v in result["calendar_influence"]]) == pytest.approx(.002)
    records[1]["context_key"]="different"
    assert matched_decay(records)["status"] == "NOT_EVALUABLE"


def test_d1_raw_same_theta_and_d3_not_decay_proof():
    result=d1(returns(10,.001),returns(10,-.001))
    assert result["mean_return_gap"] == pytest.approx(.002)
    assert "selection-biased" in result["limitation"]
    folds=[{"fold_id":i,"start":str(i),"end_exclusive":str(i+1),"daily_returns":returns(2,.001*i),"params":{"p":i}} for i in range(2)]
    assert d3(folds)[0]["status"] == "DESCRIPTIVE_MIXED_CALENDAR_PARAMETER_EFFECT"


def test_no_accounts_is_not_zero_edge_or_positive_claim():
    analysis=analyse_accounts([])
    assert len(analysis["cell_table"]) == 20 and analysis["primary_full_cohort_status"] == "NOT_EVALUABLE"
    claims=gate_claims(analysis,{})
    assert all(c["status"] == "NOT_EVALUABLE" for c in claims.values())


def test_funnel_empty_and_truth_shortcut_cannot_pass():
    keys=("model_fits","eligible_emissions","triggers","searches","changed_params","ready","activations","changed_orders")
    records={k:[] for k in keys}; records["truth_entered_learner"]=False
    assert full_path_funnel(records)["status"] == "NO_MEASURED_FULL_TREATMENT"
    records["truth_entered_learner"]=True
    with pytest.raises(ContractError): full_path_funnel(records)


def test_paths_and_unregistered_jobs_refused(lab_root,lab_tmp):
    with pytest.raises(ValueError): local(lab_root,"../quantbt/test.py")
    with pytest.raises(ValueError): validate_job(lab_root,{"tasks":[]})
    # No file is written for an unsupported discovery spec.
    with pytest.raises(ContractError): make_plan(lab_root,run_id="unit-not-created",stage="discovery")


def test_strict_json_no_nonfinite_evidence(lab_tmp):
    with pytest.raises(ValueError): save(lab_tmp/"bad.json",{"lab_run_id":"x","p":float("nan")})
    assert not (lab_tmp/"bad.json").exists()


def test_legacy_factorial_cli_cannot_claim_te_study():
    from crypto_regime_lab.cli import main
    with pytest.raises(SystemExit) as stopped:
        main(["--study-id","time_edge_validation_v4","run","--stage","discovery"])
    assert stopped.value.code == 2


def test_parameter_ids_cannot_manufacture_behavioral_diversity():
    from crypto_regime_lab.time_edge.workers import behavior_digest
    assert behavior_digest({"fills":[],"version_runs":[{"version":"p1"}]}) == behavior_digest({"fills":[],"version_runs":[{"version":"p2"}]})
    fill={"bar_index":3,"side":1,"qty":1.,"price":100.,"fee":.04,"tag":"entry"}
    assert behavior_digest({"fills":[fill]}) != behavior_digest({"fills":[]})
