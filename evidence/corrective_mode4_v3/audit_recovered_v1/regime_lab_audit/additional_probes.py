import os
from pathlib import Path
import sys,json
import numpy as np,pandas as pd
from types import SimpleNamespace
from unittest.mock import patch
R=Path(os.environ['REGIME_LAB_ROOT']).expanduser().resolve(); O=Path(os.environ['REGIME_AUDIT_OUT']).expanduser().resolve(); O.mkdir(parents=True, exist_ok=True)
sys.path[:0]=[str(R/'src'),str(R/'quantbt_candidate')]
results=[]
def record(id,x):results.append({'id':id,'result':x});print(id,json.dumps(x,default=str),flush=True)
# Registered minimum effect missing portfolio sizing factor.
m=json.loads((R/'configs/minimum_economic_effect.json').read_text());claim=json.loads((R/'configs/lab09_claim_report.json').read_text())
ratio=2000/20000
threshold=m['minimum_daily_net_return_difference']
record('P09_cost_threshold_units',{'original_threshold_account_bps_day':threshold*1e4,'entry_notional_over_capital':ratio,'threshold_from_stated_cost_formula_after_size_scaling_bps_day':threshold*ratio*1e4,'factor':1/ratio,'original_C_A_ci_account_bps_day':[v*1e4 for v in claim['contributions']['TIMING']['ci']],'original_B_A_ci_account_bps_day':[v*1e4 for v in claim['contributions']['SELECTION']['ci']],'note':'Only dimensional diagnostic; does not validate the faulty market experiment or authorize threshold retuning.'})
# Conflating fit-explanation targets across feature sets: same perfect useful labels, added noise lowers fit statistic.
from crypto_regime_lab.regime.ablation import variance_resolved
states=np.tile([0,1],100); signal=2*states-1.;noise=np.tile([-1.,-1.,1.,1.],50)
z=np.c_[signal,noise];cents=np.array([[-1.,0.],[1.,0.]])
r1=variance_resolved(z,cents,states,np.array([1.,0.]));r2=variance_resolved(z,cents,states,np.array([.5,.5]))
record('P10_ablation_target_changes',{'identical_states':True,'fixed_economic_target_exactly_predictable_from_states':True,'G1_variance_resolved':r1,'G1_G2_variance_resolved':r2,'interpretation':'R-squared target changes when weights/features change; cannot infer marginal parameter-response value from this delta alone.'})
# Candidate/adapter flow drops actual corrective EXIT follow-up.
from crypto_regime_lab.experiments import evaluator as EV
from crypto_regime_lab.alphas.contracts import BarDecision,OrderIntent,IntentKind,ExecutionPhase
class Stub:
 def __init__(self):self.state=SimpleNamespace(position=0.);self.followups=[]
 def on_bar_close(self,t):
  intents=[OrderIntent(kind=IntentKind.ENTER_LONG,decision_index=t,earliest_phase=ExecutionPhase.NEXT_OPEN,reason='audit')] if t==2 else []
  return BarDecision(index=t,position_entering_bar=self.state.position,target_after_close=self.state.position,intents=intents)
 def on_fill(self,fill):
  self.state.position+=fill.quantity
  if fill.intent_kind==IntentKind.ENTER_LONG:
   q=OrderIntent(kind=IntentKind.EXIT_ALL,decision_index=fill.index,earliest_phase=ExecutionPhase.NEXT_OPEN,reason='bracket_invalid_after_gap')
   self.followups.append(q);return [q]
  return []
f=pd.DataFrame({k:np.full(12,100.) for k in ['open','high','low','close','volume']},index=pd.date_range('2024-01-01',periods=12,freq='15min',tz='UTC'))
stub=Stub()
with patch.object(EV,'build_adapter',return_value=stub):
 ad,levels,applied=EV._sweep('AUDIT',{},f,[f[c].to_numpy() for c in ['open','high','low','close','volume']],f,backend='reference')
record('P11_followup_exit_ignored',{'entry_filled':stub.state.position!=0,'correction_exit_generated':len(stub.followups),'applied_exits':applied,'protection_levels':levels,'position_at_end':stub.state.position,'confirmed_corrective_followup_not_consumed':bool(stub.followups) and stub.state.position>0})
# Request accepted before declared ready_at: schedule only uses cutoff, even if ready provided.
from crypto_regime_lab.experiments.factorial import _schedule_from_selections
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS
sel=[{'params':SEED_POINTS['A-HMA'],'cutoff':str(f.index[5]),'fit_ready_at':str(f.index[10])}]
initial,sched,_=_schedule_from_selections(sel,f,'A-HMA',seed_params=SEED_POINTS['A-HMA'])
record('P12_ready_time_not_used',{'cutoff_bar':5,'ready_bar':10,'schedule_requested_at':initial.requested_at_bar,'initial_deployment_has_no_ready_check':True})
(O/'additional_probe_results.json').write_text(json.dumps(results,indent=2,default=str))
