"""Train-only JM ladder; supervised target tails purged by outcome availability.

Inputs are raw features and independently measured candidate utility records.
Truth labels and forward price-return proxies are not accepted as utility data.
"""
from itertools import permutations

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from ..experiments.time_edge_contracts import ContractError
from ..regime.causality import fit_scaler, apply_scaler
from ..regime.jump_model import multi_start_fit, loss_matrix, forward_filter
from .storage import digest


def jsonable(value):
    from datetime import datetime
    from enum import Enum
    if isinstance(value, Enum): return jsonable(value.value)
    if isinstance(value, (pd.Timestamp,datetime)): return value.isoformat()
    if isinstance(value, pd.DataFrame): return {"columns":list(value.columns),"rows":jsonable(value.reset_index().to_dict("records"))}
    if isinstance(value, pd.Series): return jsonable(value.to_dict())
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value,float) and not np.isfinite(value):
        return {"value":None,"reason":"NONFINITE_SOURCE_VALUE"}
    if isinstance(value, dict):
        return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [jsonable(v) for v in value]
    return value


def target_rows(targets, *, before, origin_start=None, origin_end=None):
    kept = []
    for row in targets:
        required = ("origin","outcome_available_at","candidate_available_at","candidate_ids","utilities",
                    "candidate_set_hash","engine_trace_hash","economic_hash","cell_id")
        if any(k not in row for k in required):
            raise ContractError("candidate-utility target missing lineage")
        origin = pd.Timestamp(row["origin"])
        outcome = pd.Timestamp(row["outcome_available_at"])
        if origin.tz is None or outcome.tz is None or pd.Timestamp(row["candidate_available_at"]) > origin or outcome <= origin:
            raise ContractError("noncausal candidate/target clocks")
        if len(row["utilities"]) != len(row["candidate_ids"]) or len(row["utilities"]) < 2:
            raise ContractError("paired candidate utilities required")
        if len(set(row["candidate_ids"])) != len(row["candidate_ids"]) or not np.isfinite(row["utilities"]).all():
            raise ContractError("invalid fixed candidate cohort")
        if row["candidate_set_hash"] != digest(row["candidate_ids"]):
            raise ContractError("candidate set identity mismatch")
        if outcome >= pd.Timestamp(before):
            continue  # same-time availability has no certified sequence: strict exclusion
        if origin_start is not None and origin < pd.Timestamp(origin_start):
            continue
        if origin_end is not None and origin >= pd.Timestamp(origin_end):
            continue
        kept.append(row)
    return kept


def rank_ic(prediction, realized):
    a,b = rankdata(prediction),rankdata(realized)
    if np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a,b)[0,1])


def _group(row):
    return row["cell_id"],row["candidate_set_hash"],row["economic_hash"]


def information(train_targets, valid_targets, index, states):
    def state(row):
        at = index.searchsorted(pd.Timestamp(row["origin"]), side="right")-1
        if at < 0:
            raise ContractError("target origin precedes model history")
        return int(states[at])
    profiles = {}; baseline = {}
    for row in train_targets:
        baseline.setdefault(_group(row), []).append(row["utilities"])
        profiles.setdefault((_group(row),state(row)), []).append(row["utilities"])
    rows = []
    for row in valid_targets:
        group = _group(row); selected = profiles.get((group,state(row)), [])
        base = baseline.get(group, [])
        support = len(selected)
        regime_ic = rank_ic(np.mean(selected,axis=0), row["utilities"]) if support >= 2 else None
        base_ic = rank_ic(np.mean(base,axis=0), row["utilities"]) if len(base) >= 2 else None
        effect = None if regime_ic is None or base_ic is None else regime_ic-base_ic
        rows.append({"origin":row["origin"],"outcome_available_at":row["outcome_available_at"],
                     "cell_id":row["cell_id"],"candidate_set_hash":row["candidate_set_hash"],
                     "state_id":state(row),"conditional_profile_support":support,"baseline_support":len(base),
                     "regime_rank_ic":regime_ic,"baseline_rank_ic":base_ic,"effect":effect,
                     "reason":None if effect is not None else "insufficient profile or constant ranking denominator"})
    values = [r["effect"] for r in rows if r["effect"] is not None]
    return {"rows":rows,"evaluable":len(values),"planned":len(rows),
            "mean_incremental_rank_ic":float(np.mean(values)) if values else None}


def dossier(raw, states, *, k, features):
    states = np.asarray(states,int); n = len(states)
    counts = np.bincount(states,minlength=k)
    transitions = np.zeros((k,k),int)
    np.add.at(transitions,(states[:-1],states[1:]),1)
    boundaries = np.r_[0,np.flatnonzero(states[1:] != states[:-1])+1,n]
    dwell = [{"state_id":int(states[a]),"observations":int(b-a)} for a,b in zip(boundaries[:-1],boundaries[1:])]
    profiles = []
    for state in range(k):
        sample = raw[states == state]
        profiles.append({"state_id":state,"train_count":len(sample),
            "raw_feature_means":dict(zip(features,sample.mean(axis=0).tolist())) if len(sample) else None,
            "raw_feature_std_ddof1":dict(zip(features,sample.std(axis=0,ddof=1).tolist())) if len(sample)>1 else None,
            "dispersion_reason":None if len(sample)>1 else "fewer than two state observations",
            "meaning":"train feature profile; numeric label is local to this vintage"})
    return {"observations":n,"occupancy_counts":counts.tolist(),"occupancy_fraction":(counts/n).tolist(),
            "transition_counts":transitions.tolist(),"transition_denominator":max(0,n-1),
            "recurrence_episodes":len(dwell),"dwell":dwell,"dead_states":np.flatnonzero(counts == 0).tolist(),
            "state_profiles":profiles,"market_label_accuracy":None,"accuracy_reason":"no independent market ground truth"}


def map_states(old_raw, new_raw, scale, *, ambiguity_margin=.05):
    """Compare both vintages in one RAW economic coordinate system, K<=3."""
    old,new = np.asarray(old_raw,float),np.asarray(new_raw,float)
    scale = np.asarray(scale,float)
    if old.shape != new.shape or np.any(scale <= 0) or not np.isfinite(scale).all():
        return {"status":"UNMATCHED","mapping":{}}
    cost = np.mean(((old[:,None,:]-new[None,:,:])/scale)**2,axis=2)
    alternatives = sorted((float(sum(cost[i,j] for i,j in enumerate(p))),p) for p in permutations(range(len(old))))
    best,p = alternatives[0]
    margin = alternatives[1][0]-best if len(alternatives)>1 else float("inf")
    if margin <= ambiguity_margin:
        return {"status":"AMBIGUOUS","mapping":{},"cost":best,"margin":margin}
    return {"status":"MATCHED","mapping":{str(j):i for i,j in enumerate(p)},"cost":best,"margin":margin}


def _fit(raw, design, weights, seeds):
    scaler = fit_scaler(raw); z = apply_scaler(raw,scaler)
    if design["kind"] == "M0":
        # Registered composite is only an interpretable comparator, not a JM label.
        score = z[:,[0,1,4]].mean(axis=1)
        cuts = np.quantile(score,[1/3,2/3])
        states = np.searchsorted(cuts,score,side="left")
        fit = {"cuts":cuts,"runs":[],"selected_seed":None}
    else:
        fit = multi_start_fit(z,weights,n_states=design["k"],lambda_jump=design["lambda"],seeds=tuple(seeds))
        states = forward_filter(loss_matrix(z,fit["centroids"],weights),design["lambda"]).online_states
    return scaler,fit,states


def _states(raw, scaler, fit, design, weights):
    z = apply_scaler(raw,scaler)
    if design["kind"] == "M0":
        return np.searchsorted(fit["cuts"],z[:,[0,1,4]].mean(axis=1),side="left")
    # Caller passes train+validation, so the valid block starts from terminal train Q.
    return forward_filter(loss_matrix(z,fit["centroids"],weights),design["lambda"]).online_states


def fit_vintage(features, targets, *, cutoff, ready_at, protocol, previous=None):
    cutoff,ready = pd.Timestamp(cutoff),pd.Timestamp(ready_at)
    if cutoff.tz is None or ready < cutoff:
        raise ContractError("invalid model fit/ready clocks")
    names = protocol["features"]
    history = features.loc[(features.index < cutoff) & (features.index >= cutoff-pd.Timedelta(days=365)),names]
    if str(history.index.tz) != "UTC" or history.index.has_duplicates or not history.index.is_monotonic_increasing:
        raise ContractError("model features need unique sorted UTC availability")
    expected = 365*6
    if len(history)>expected or not history.index.equals(history.index.floor("4h")):
        raise ContractError("model observations must lie on the registered completed 4h availability grid")
    valid_rows=np.isfinite(history.to_numpy()).all(axis=1)
    missing_training_rows=int((~valid_rows).sum())
    if int(valid_rows.sum()) < expected*.9:
        raise ContractError("raw model feature coverage/finite fraction insufficient")
    history=history.loc[valid_rows]
    raw = history.to_numpy(float); weights = np.array([protocol["group_weights"][x] for x in names])
    designs = [{"id":"M0","kind":"M0","k":3,"lambda":0.}] + [
        {"id":f"JM-K{k}-L{lam}","kind":"JM","k":k,"lambda":lam}
        for k in protocol["ladder"]["jm_k"] for lam in protocol["ladder"]["jm_lambda"]]
    valid_targets = target_rows(targets,before=cutoff.isoformat())
    trials = []
    # Three chronological validation blocks after at least 180 calendar days.
    first = history.index[0]+pd.Timedelta(days=180)
    bounds = pd.date_range(first,cutoff,periods=4)
    for design in designs:
        fold_rows = []; admissible = True
        for a,b in zip(bounds[:-1],bounds[1:]):
            train_n = history.index.searchsorted(a,side="left")
            valid_n = history.index.searchsorted(b,side="left")
            scaler,fit,states_train = _fit(raw[:train_n],design,weights,protocol["ladder"]["fit_seeds"])
            states = _states(raw[:valid_n],scaler,fit,design,weights)
            counts = np.bincount(states_train,minlength=design["k"])
            chosen_run = next((r for r in fit["runs"] if r["seed"] == fit["selected_seed"]),None)
            fit_ok = bool((counts > 0).all()) and (chosen_run is None or chosen_run["converged"])
            admissible &= fit_ok
            training = target_rows(valid_targets,before=a.isoformat(),origin_start=history.index[0],origin_end=a)
            validation = target_rows(valid_targets,before=cutoff.isoformat(),origin_start=a,origin_end=b)
            info = information(training,validation,history.index[:valid_n],states)
            # Design-dependent missing targets cannot create a nicer comparison
            # cohort. Keep the fixed validation denominator; reject incomplete designs.
            admissible &= info["planned"] > 0 and info["evaluable"] == info["planned"]
            fold_rows.append({"train_end":a.isoformat(),"validation_end":b.isoformat(),
                "training_targets":len(training),"purge_rule":"outcome_available_at < inner cutoff",
                "fit_ok":fit_ok,"information":info,"seed_trials":fit["runs"],
                "normalized_objective":None if chosen_run is None else chosen_run["final_objective"]/train_n,
                "dossier":dossier(raw[:train_n],states_train,k=design["k"],features=names)})
        effects = [r["effect"] for f in fold_rows for r in f["information"]["rows"] if r["effect"] is not None]
        score = float(np.mean(effects)) if effects else None
        trials.append({"design":design,"admissible":bool(admissible),"inner_folds":fold_rows,
                       "ranking_utility":score,"informative_episodes":len(effects),
                       "normalized_objective":float(np.mean([f["normalized_objective"] for f in fold_rows])) if design["kind"] == "JM" else None})
    valid = [r for r in trials if r["design"]["kind"] == "JM" and r["admissible"] and r["ranking_utility"] is not None and r["ranking_utility"] > 0]
    # Fixed 1e-12 numerical tie tolerance; no outer outcome enters this decision.
    if valid:
        maximum = max(r["ranking_utility"] for r in valid)
        tied = [r for r in valid if maximum-r["ranking_utility"] <= 1e-12]
        selected = min(tied,key=lambda r:(r["design"]["k"],r["normalized_objective"],r["design"]["id"]))
        decision = "SELECTED_INNER_INFORMATIVE_DESIGN"
    else:
        selected = trials[0]; decision = "NO_PROMISING_DESIGN_M0_CONTROL"
    design = selected["design"]
    scaler,fit,states = _fit(raw,design,weights,protocol["ladder"]["fit_seeds"])
    raw_centroids = [raw[states == k].mean(axis=0).tolist() if np.any(states == k) else None for k in range(design["k"])]
    mapping = {"status":"INITIAL_NAMESPACE","mapping":{str(k):k for k in range(design["k"])}}
    common_namespace=digest({"cutoff":cutoff.isoformat(),"design":design,"raw_profiles":raw_centroids})
    if previous:
        if any(x is None for x in raw_centroids+previous["raw_centroids"]):
            mapping = {"status":"UNMATCHED","mapping":{}}
        else:
            mapping = map_states(previous["raw_centroids"],raw_centroids,scaler["scale"])
            if mapping["status"] == "MATCHED":
                prior = previous["mapping"]["mapping"]
                if prior:
                    mapping["mapping"] = {k:prior[str(v)] for k,v in mapping["mapping"].items() if str(v) in prior}
                    common_namespace=previous["common_namespace"]
                else:
                    mapping={"status":"NEW_NAMESPACE_AFTER_AMBIGUITY","mapping":{str(k):k for k in range(design["k"])}}
            elif mapping["status"] == "UNMATCHED" and len(previous["raw_centroids"]) != design["k"]:
                mapping={"status":"NEW_NAMESPACE_AFTER_K_CHANGE","mapping":{str(k):k for k in range(design["k"])}}
    result = jsonable({"cutoff":cutoff.isoformat(),"ready_at":ready.isoformat(),"design":design,
        "decision":decision,"design_trials":trials,"scaler":scaler,"fit":fit,"weights":weights,
        "raw_centroids":raw_centroids,"mapping":mapping,"common_namespace":common_namespace,"feature_names":names,
        "feature_schema_hash":digest(names),"model_design_hash":digest(design),
        "training_raw_hash":digest(raw.tolist()),"history_start":history.index[0].isoformat(),"missing_training_rows":missing_training_rows,
        "dossier":dossier(raw,states,k=design["k"],features=names),
        "training_terminal_cost":forward_filter(loss_matrix(apply_scaler(raw,scaler),fit["centroids"],weights),design["lambda"]).costs[-1] if design["kind"] == "JM" else None})
    selected_run=next((r for r in fit["runs"] if r["seed"] == fit["selected_seed"]),None)
    result["fit_quality"]="OK" if not result["dossier"]["dead_states"] and (selected_run is None or selected_run["converged"]) else "DEGENERATE_OR_NONCONVERGED"
    # Identity covers the quality decision consumed by the actual controller.
    result["model_id"]=digest({k:v for k,v in result.items() if k != "model_id"})
    return result


def emit(vintage, features, *, until):
    """Continue Q online including fit-to-ready observations; publish only once ready."""
    fit = vintage["fit"]; design = vintage["design"]
    q = np.asarray(vintage["training_terminal_cost"],float) if design["kind"] == "JM" else None
    scaler = dict(vintage["scaler"])
    scaler["median"],scaler["scale"] = np.asarray(scaler["median"]),np.asarray(scaler["scale"])
    block = features.loc[(features.index >= pd.Timestamp(vintage["cutoff"])) & (features.index < pd.Timestamp(until)),vintage["feature_names"]]
    output = []
    for at,row in block.iterrows():
        raw = row.to_numpy(float)
        valid = np.isfinite(raw).all()
        state = None
        if valid:
            z = apply_scaler(raw[None,:],scaler)
            if design["kind"] == "JM":
                loss = loss_matrix(z,np.asarray(fit["centroids"]),np.asarray(vintage["weights"]))[0]
                q = loss + np.minimum(q,q.min()+design["lambda"]); q -= q.min()
                state = int(q.argmin())
            else:
                state = int(np.searchsorted(fit["cuts"],z[0,[0,1,4]].mean(),side="left"))
        if at < pd.Timestamp(vintage["ready_at"]):
            continue
        common = vintage["mapping"]["mapping"].get(str(state))
        quality = "OK" if valid and common is not None and vintage.get("fit_quality","OK") == "OK" else "UNKNOWN_OR_UNMAPPED"
        record = {"model_id":vintage["model_id"],"model_fit_cutoff":vintage["cutoff"],
            "model_ready_at":vintage["ready_at"],"available_at":at.isoformat(),
            "state_namespace":vintage["model_id"],"state_id":state,"state_common":common,
            "state_common_namespace":vintage.get("common_namespace",vintage["model_id"]),
            "economic_context":"COMMON_BTCUSDT_MARKET_CONTEXT","quality_status":quality,
            "decision_eligible":quality == "OK","source_mask":"RAW_G1_G2_G5",
            "feature_schema_hash":vintage["feature_schema_hash"],"model_design_hash":vintage["model_design_hash"]}
        record["observation_id"] = digest(record); output.append(record)
    return output
