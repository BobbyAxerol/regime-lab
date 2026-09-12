"""Reproducible controls with explicit statistical-only versus full-path scope."""
import numpy as np
import pandas as pd

from ..experiments.time_edge_contracts import ContractError, holm_adjust
from .inference import block_mean, block_weighted, wilson
from .runtime import local
from .storage import digest, file_digest, save, read


def statistical_calibration(task, *, directory=None, lab_run_id=None):
    delta=float(task["delta"])
    repetitions=int(task.get("repetitions",1000)); n=int(task.get("days",1095))
    draws=int(task.get("draws",4999)); seed=int(task.get("seed",2026091210))
    if delta <= 0 or repetitions < 1000 or n < 365 or ((n-1)//28+1) < 20 or draws != 4999:
        raise ContractError("registered statistical calibration dimensions/positive delta required")
    rng=np.random.default_rng(seed); outcomes=[]
    for effect in (0.,1.,2.,4.):
        rejections=0; per_hypothesis=np.zeros(4,int)
        for repetition in range(repetitions):
            # Correlated hypotheses and AR(1) calendar shocks. Four-dimensional
            # noise is generated once per world; never one market per bootstrap.
            innovation=rng.normal(size=(n,5))*delta
            noise=innovation[:,:4]+innovation[:,4,None]
            for t in range(1,n): noise[t]+=.4*noise[t-1]
            cache=None if directory is None else directory/f"calibration-{int(effect)}-{repetition:04d}.json"
            seal=None if cache is None else cache.with_suffix(".sha256.json")
            identity=digest({"task":task,"run":lab_run_id,"effect":effect,"repetition":repetition})
            if cache is not None and (cache.exists() or seal.exists()):
                if not cache.exists() or not seal.exists() or file_digest(cache) != read(seal)["sha256"]:
                    raise ContractError("statistical calibration cache publication/hash mismatch")
                record=read(cache)
                if record["identity"] != identity: raise ContractError("statistical calibration cache identity drift")
                rejected=np.asarray(record["rejected"],bool)
                rejections+=bool(rejected.any()); per_hypothesis+=rejected
                continue
            values=noise+effect*delta
            # H-MODEL-INFO has threshold zero and sparse calendar episodes.
            values[:,3]-=delta
            weights=np.zeros(n); weights[::28]=1.
            estimates=[block_mean(values[:,h],delta=delta,draws=draws,seed=seed+h) for h in range(3)]
            estimates.append(block_weighted(values[:,3]*weights,weights,delta=0.,draws=draws,seed=seed+3))
            p=holm_adjust([r["p_one_sided"] for r in estimates])
            rejected=np.array([r["ci_simultaneous_basic"][0] > (delta if h<3 else 0.) and a <= .05 for h,(r,a) in enumerate(zip(estimates,p))])
            if cache is not None:
                saved=save(cache,{"lab_run_id":lab_run_id,"identity":identity,"rejected":rejected.tolist(),"estimates":estimates,"holm_p":p})
                save(seal,{"lab_run_id":lab_run_id,"sha256":saved})
            rejections+=bool(rejected.any()); per_hypothesis+=rejected
        outcomes.append({"true_effect_delta_units":effect,"worlds":repetitions,"family_rejections":rejections,
                         "rate":rejections/repetitions,"wilson95":wilson(rejections,repetitions),
                         "per_hypothesis_rejections":per_hypothesis.tolist(),"per_hypothesis_power":(per_hypothesis/repetitions).tolist(),
                         "thresholds":[delta,delta,delta,0.],"true_means":[effect*delta]*3+[(effect-1)*delta]})
    nulls=[r for r in outcomes if r["true_effect_delta_units"] <= 1]
    positive=next(r for r in outcomes if r["true_effect_delta_units"] == 2.)
    passed=all(r["wilson95"][1] <= .08 for r in nulls) and min(positive["per_hypothesis_power"]) >= .8
    return {"status":"STATISTICAL_CALIBRATION_PASS" if passed else "CALIBRATION_INCONCLUSIVE",
            "scope":"STATISTICAL_ONLY","conditions":outcomes,"seed":seed,"draws":draws,
            "engine_runs":0,"full_pipeline_calibration":"NOT_EXECUTED_BY_THIS_TASK"}


def generate_world(root, request):
    """Latent semi-Markov world; learner files contain only observable OHLCV.

    This generates opportunity/stationarity stress worlds, not a claim that a
    learner's expected timing advantage equals an injected return drift.
    """
    task=request["task"]; seed=int(task["seed"]); days=int(task.get("days",1461))
    condition=task["condition"]
    if condition not in ("NULL_STATIONARY","RECURRING_OPPORTUNITY") or days < 730:
        raise ContractError("registered control condition and at least two years required")
    rng=np.random.default_rng(seed); n=days*1440
    daily_state=np.empty(days,int); current=0; cursor=0
    while cursor < days:
        length=int(rng.integers(28,85)); daily_state[cursor:cursor+length]=current
        cursor+=length; current=1-current
    state=np.repeat(daily_state,1440)
    innovations=rng.normal(0,.0003,n)
    # Conditional serial dependence changes strategy opportunity. Truth stays in
    # a distinct artifact and cannot be passed through the raw feature schema.
    rho=np.zeros(n) if condition == "NULL_STATIONARY" else np.where(state == 0,.35,-.35)
    returns=np.empty(n); returns[0]=innovations[0]
    for i in range(1,n): returns[i]=rho[i]*returns[i-1]+innovations[i]
    close=100*np.exp(np.cumsum(returns)); opens=np.r_[100.,close[:-1]]
    spread=np.abs(rng.normal(0,.00015,n))
    volume=rng.lognormal(7,.3,n)
    frame=pd.DataFrame({"open":opens,"high":np.maximum(opens,close)*(1+spread),
        "low":np.minimum(opens,close)/(1+spread),"close":close,"volume":volume,
        "quote_volume":volume*close,"taker_buy_base_volume":volume/(1+np.exp(-returns/.0005))},
        index=pd.date_range("2019-01-01",periods=n,freq="min",tz="UTC"))
    directory=local(root,request["task_evidence"])
    market=directory/"observable_market.parquet"
    if market.exists(): raise ContractError("world artifact already exists; use a new run identity")
    frame.to_parquet(market)
    truth=directory/"evaluation_only_truth.json"
    save(truth,{"lab_run_id":request["lab_run_id"],"daily_state":daily_state.tolist(),"condition":condition,
                "decision_eligible":False,"seed":seed})
    index_path=directory/"market_index.json"
    save(index_path,{"lab_run_id":request["lab_run_id"],"time_unit":"ms","partitions":[{
        "path":str(market.relative_to(root)),"sha256":file_digest(market),
        "start":frame.index[0].isoformat(),"end_exclusive":(frame.index[-1]+pd.Timedelta(minutes=1)).isoformat()}]})
    return {"status":"CONTROL_WORLD_GENERATED","condition":condition,"seed":seed,"days":days,
            "observable_market":{"path":str(index_path.relative_to(root)),"sha256":file_digest(index_path)},
            "truth":{"path":str(truth.relative_to(root)),"sha256":file_digest(truth)},
            "world_id":digest({"seed":seed,"condition":condition,"days":days}),
            "full_pipeline_status":"PENDING_LEARNER_AND_ENGINE_RUNS",
            "known_learner_time_edge":None,"reason":"conditional opportunity does not specify a learner's net timing effect"}


def full_path_funnel(records):
    """Join actual lineage; equality paths retain a measured bottleneck."""
    required=("model_fits","eligible_emissions","triggers","searches","changed_params","ready","activations","changed_orders")
    result={}
    for key in required:
        rows=records.get(key)
        if not isinstance(rows,list): raise ContractError("missing measured funnel ledger: "+key)
        result[key]=len(rows)
    result["known_truth_entered_learner"]=records.get("truth_entered_learner")
    if records.get("truth_entered_learner") is not False:
        raise ContractError("full-path control lacks truth-exclusion proof")
    result["bottleneck"]=next((key for key in required if result[key] == 0),None)
    result["status"]="TREATMENT_REACHED_ORDERS" if result["bottleneck"] is None else "NO_MEASURED_FULL_TREATMENT"
    return result
