import os
from pathlib import Path
from collections import Counter
import json,hashlib,numpy as np,pandas as pd
R=Path(os.environ['REGIME_LAB_ROOT']).expanduser().resolve(); O=Path(os.environ['REGIME_AUDIT_OUT']).expanduser().resolve(); O.mkdir(parents=True, exist_ok=True)
summary={'scope':'recomputed from uploaded evidence, not new market simulation'}
summary['files']={'actual_files':len([p for p in R.rglob('*') if p.is_file()]),'lab_python_files':len(list((R/'src').rglob('*.py'))),'scripts':len(list((R/'scripts').glob('*.py'))),'tests':len(list((R/'tests').glob('test*.py'))),'markdown':len(list(R.rglob('*.md')))}
allrows=[]
for name in ['lab08_factorial_full','lab09_confirmation_results']:
 x=json.loads((R/'configs'/f'{name}.json').read_text());rows=[];eq=0;means={};hma_modes=Counter();vwapflag=Counter();err=[]
 for c in x['cells']:
  if c['status']!='RUN': continue
  arms=c['arms'];dr=c.get('daily_returns',{})
  if 'D' in dr and 'E' in dr:
   same=dr['D']==dr['E'];eq+=int(same)
  else:same=all(arms['D'].get(k)==arms['E'].get(k) for k in ['net_return','trades','entries','daily_sharpe','bars_by_parameter_version'])
  row={'alpha':c['alpha_id'],'symbol':c['symbol'],'E_equals_D':same,'arms':{}}
  for a,v in arms.items():
   row['arms'][a]={k:v.get(k) for k in ['status','net_return','daily_sharpe','max_drawdown','entries','exit_fixed_point_converged','versions_deployed','switches_requested','switches_effected']}
   row['arms'][a]['delay']=v.get('switch_delays',{}).get('blocked_bars_by_reason')
   if v.get('status')=='RUN' and v.get('exit_fixed_point_converged') is not True:err.append((c['alpha_id'],c['symbol'],a))
  for a,selections in c.get('notes',{}).get('deployed_selections',{}).items():
   if a=='E':continue
   for s in selections:
    if c['alpha_id']=='A-HMA':hma_modes[str(s['params'].get('sl_input'))]+=1
    if c['alpha_id']=='A-VWAP':vwapflag[str(s['params'].get('exit_at_vwap'))]+=1
  rows.append(row)
 summary[name]={'cells':len(x['cells']),'run_cells':len(rows),'E_equals_D_cells':sum(r['E_equals_D'] for r in rows),'selected_hma_modes_repeated_by_arm':dict(hma_modes),'vwap_exit_at_vwap_repeated_by_arm':dict(vwapflag),'nonconverged_final_arms':err,'per_cell':rows}
 allrows+=rows
for name in ['lab06_response_model','lab09_policy_response_model']:
 x=json.loads((R/'configs'/f'{name}.json').read_text());reason=Counter();blocks=Counter()
 for r in x['responses']:
  if r['status']=='INSUFFICIENT_SUPPORT':reason[str(r.get('reason'))]+=1
  blocks[str(r['diagnostics']['contiguous_blocks'])]+=1
 summary[name]={k:x.get(k) for k in ['alpha_id','symbol','response_count','status_counts','responses_sampled','episode_panel_rows']}
 summary[name]['actually_retained_response_records']=len(x['responses']);summary[name]['retained_sample_block_count']=dict(blocks)
 summary[name]['top_sample_reasons']=reason.most_common(3)
for name in ['lab06_decision_ledger','lab09_policy_decision_ledger']:
 x=json.loads((R/'configs'/f'{name}.json').read_text());summary[name]={'keys':list(x)}
 for k,v in x.items():
  if not isinstance(v,list) and not (isinstance(v,dict) and len(json.dumps(v))>3000):summary[name][k]=v
# every JSONL parser integrity, never execute the payloads
n=0;errors=[];counts={}
for p in R.rglob('*.jsonl'):
 count=0
 try:
  with p.open() as f:
   for li,line in enumerate(f,1):
    if not line.strip():continue
    json.loads(line);n+=1;count+=1
 except Exception as e:errors.append({'file':str(p.relative_to(R)),'line':li,'error':str(e)})
 counts[str(p.relative_to(R))]=count
summary['jsonl_integrity']={'files':len(counts),'rows':n,'errors':errors}
(O/'jsonl_row_counts.json').write_text(json.dumps(counts,indent=2))
(O/'evidence_reanalysis.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
for k,v in summary.items():
 if isinstance(v,dict): print(k,json.dumps({a:b for a,b in v.items() if a!='per_cell'},ensure_ascii=False)[:2300])
