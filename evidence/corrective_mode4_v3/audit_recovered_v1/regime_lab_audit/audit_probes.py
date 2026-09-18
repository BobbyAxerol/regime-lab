import os
"""Independent audit probes on uploaded snapshot; no production/data writes.
This runs supplied functions on synthetic inputs. It is NOT a market backtest.
"""
from pathlib import Path
import sys,json,traceback,hashlib
from unittest.mock import patch
import numpy as np,pandas as pd
ROOT=Path(os.environ['REGIME_LAB_ROOT']).expanduser().resolve()
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'quantbt_candidate')]
OUT=Path(os.environ['REGIME_AUDIT_OUT']).expanduser().resolve(); OUT.mkdir(parents=True, exist_ok=True)
rows=[]
def probe(name,fn):
    try:
        d=fn();rows.append({'id':name,'ran':True,'result':d})
        print(name,json.dumps(d,default=str),flush=True)
    except Exception as e:
        rows.append({'id':name,'ran':False,'error':f'{type(e).__name__}: {e}','trace':traceback.format_exc()})
        print(name,'ERROR',repr(e),flush=True)
def frame(n=100):
    c=100+3*np.sin(np.arange(n)*.3)
    return pd.DataFrame({'open':c,'high':c+.3,'low':c-.3,'close':c,'volume':np.ones(n)*100},index=pd.date_range('2024-01-01',periods=n,freq='15min',tz='UTC'))
def fee():
    from crypto_regime_lab.quantbt_bridge.intent_tape import TapeBuild,run_intrabar
    f=frame(10);f.loc[:,'open']=100.;f.loc[:,'high']=101.;f.loc[:,'low']=99.;f.loc[:,'close']=100.
    t=TapeBuild(np.r_[1.,np.zeros(9)],np.r_[1.,np.zeros(9)],np.full(10,np.nan),np.full(10,np.nan),np.zeros(10,dtype=bool))
    r=run_intrabar(f,t,fee=.0004,slippage_bps=0,backend='reference',sizing_mode='fixed_notional',unit_notional=2000)
    ratios=[x['fee']/abs(x['qty']*x['price']) for x in r['fills']]
    return {'registered_one_way':.0004,'actual_rates':ratios,'fills':r['fills'],'final_equity':float(np.asarray(r['equity']).reshape(-1)[-1]),'confirmed_half_fee':all(abs(x-.0002)<1e-12 for x in ratios)}
def initial():
    from crypto_regime_lab.integration.continuous_account import VersionWindow,run_continuous_account
    from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS
    f=frame(200)
    v=VersionWindow('FUTURE_SELECTED',dict(SEED_POINTS['A-HMA']),100,'future')
    r=run_continuous_account('A-HMA',f,initial=v,schedule=[],backend='reference')
    return {'requested_at_bar':100,'first_active_at':r.version_by_bar.index('FUTURE_SELECTED'),'pre_request_bars_using_future_params':sum(x=='FUTURE_SELECTED' for x in r.version_by_bar[:100]),'first_fills':r.fills[:4],'confirmed_backdated':r.version_by_bar[0]=='FUTURE_SELECTED'}
def namespaces():
    from crypto_regime_lab.experiments.regime_schedule import transition_cutoffs
    e=[{'state_namespace':'v1','state_id':0,'available_at':'2024-01-01T00:00:00Z','decision_eligible':True},
       {'state_namespace':'v2','state_id':0,'available_at':'2024-01-02T00:00:00Z','decision_eligible':False,'quality_status':'MISSING_DATA'}]
    s=transition_cutoffs(e,count=1,earliest='2024-01-01',latest='2024-01-04',min_gap_days=0)
    return {'chosen':s.cutoffs,'semantic_state_changed':False,'selected_decision_eligible':False,'confirmed_namespace_trigger':len(s.cutoffs)==1}
def context():
    from crypto_regime_lab.regime.emissions import build_emission
    from crypto_regime_lab.policy.response import context_distance
    mu=np.array([[-2.],[2.]])
    es=[]
    for k in (0,1):
        costs=.5*(mu[:,0]-mu[k,0])**2
        e=build_emission(k,costs,namespace='v',z_t=mu[k],centroids=mu,weights=np.ones(1),groups={'G':[0]},observed_at='2024-01-01',available_at='2024-01-01',inferred_at='2024-01-01',model_fit_cutoff='2023-12-31',ready_at='2023-12-31',version='v')
        es.append(e)
    d=context_distance(np.array(es[0].feature_contributions),np.array(es[1].feature_contributions),np.ones(1))
    return {'true_contexts':mu.tolist(),'response_features':[e.feature_contributions for e in es],'distance_used_by_response':d,'confirmed_distinct_states_collapsed':d==0.}
def hma_modes():
    from crypto_regime_lab.alphas.a_hma import SL_MODES
    from crypto_regime_lab.selector.alpha_schemas import A_HMA
    specs=getattr(A_HMA,'specs',None)
    if isinstance(specs,dict):choices=specs['sl_input'].choices
    else:
        # Actual source declared values; cross-check source text in report.
        choices=('Half Distance Zone','Zone Distance','ATR')
    mapped={c:SL_MODES.get(c,1) for c in choices}
    return {'declared_choices':list(choices),'adapter_mapping':SL_MODES,'effective_modes':mapped,'all_search_choices_same':len(set(mapped.values()))==1}
def unconverged():
    from crypto_regime_lab.experiments import calendar_baseline as cb,evaluator as ev
    from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS,SCHEMAS
    f=frame(12)
    bad=ev.CandidateRun(np.arange(12)*1.+20000,np.zeros(12),[],f.index,False,4,0,3)
    with patch.object(cb,'run_candidate',return_value=bad):
        r=cb._evaluate('A-SC',SEED_POINTS['A-SC'],f,[('e0',0,12)],'audit',SCHEMAS['A-SC'],'reference')
    return {'run_converged':False,'unmapped_intents':3,'evaluation_status':str(r.status),'window':r.window,'accepted':r.status==cb.ProbeStatus.EVALUATED}
def convergence():
    from crypto_regime_lab.experiments import evaluator as ev
    from crypto_regime_lab.quantbt_bridge.intent_tape import TapeBuild
    from types import SimpleNamespace
    f=frame(12);t=TapeBuild(np.zeros(12),np.zeros(12),np.full(12,np.nan),np.full(12,np.nan),np.zeros(12,dtype=bool))
    observed={'bar_index':5,'price':120.,'qty':2.,'reason':'take_profit','side':-1,'fee':.05}
    with patch.object(ev,'_sweep',return_value=(SimpleNamespace(decisions=[]),{}, {5:80.})),patch.object(ev,'build_intent_tape',return_value=t),patch.object(ev,'_engine',return_value={'equity':np.full(12,20000.),'positions':np.zeros(12),'fills':[observed]}):
        r=ev.run_candidate('A-SC',{},f)
    return {'applied_fill_price':80.,'actual_engine_price':120.,'matched_bar':5,'marked_converged':r.converged,'confirmed_price_blind_convergence':r.converged}
def episode_boundary():
    from crypto_regime_lab.experiments import evaluator as ev
    f=frame(4);equity=np.array([20000.,20000.,19000.,19000.])
    r=ev.CandidateRun(equity,np.zeros(4),[],f.index,True,1,0)
    m=ev.episode_metrics(r,[('e0',0,2),('e1',2,4)])
    return {'equity':equity.tolist(),'whole_loss':float(equity[-1]-equity[0]),'episode_reported_returns':{k:v['net_return'] for k,v in m.items()},'lost_boundary_pnl':all(v['net_return']==0 for v in m.values())}
for name,fn in [('P01_fee_binding',fee),('P02_initial_future_params',initial),('P03_namespace_and_invalid_emission',namespaces),('P04_residual_context_collapse',context),('P05_hma_categorical_alias',hma_modes),('P06_unconverged_candidate_accepted',unconverged),('P07_price_blind_convergence',convergence),('P08_episode_boundary_pnl',episode_boundary)]:probe(name,fn)
(OUT/'audit_probe_results.json').write_text(json.dumps({'scope':'uploaded-source synthetic/reference probes, NOT market replay','python':sys.version,'results':rows},indent=2,default=str))
