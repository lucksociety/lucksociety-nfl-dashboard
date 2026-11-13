"""Research-only challenger; never imported by forecast or used to select a live model.
Run after a current forecast with python -m ufc.research_opponents.
Fixed Jan-Oct 2024 development comparison; this is not an untouched test.
"""
import json,math
from itertools import groupby
from pathlib import Path
import numpy as np
from . import data,features,model,supplement
from datetime import datetime,timezone
bouts=[b for b in data.history()if b['date']<'2026-11-13']
physical,_,_=supplement.augment(data.physical(),json.loads((data.ROOT/'data/supplement.json').read_text())['profiles'])
X,ordered,_=features.build(bouts,physical);state=features.State(physical);ledger={};extras=[]
def summary(k,day):
 s=ledger.get(k,dict(last=day,sos=0.,defense=0.,n=0.))
 d=math.exp(-math.log(2)*features.elapsed(day,s['last'])/540)
 return np.array([s['sos']*d/(s['n']*d+3),s['defense']*d/(s['n']*d+3)])
for day,group in groupby(ordered,key=lambda b:b['date']):
 group=list(group)
 for b in group:extras.append(summary(b['a'],day)-summary(b['b'],day))
 for b in group:
  old=[state.profile(k,day)for k in [b['a'],b['b']]]
  for i,k in enumerate([b['a'],b['b']]):
   s=ledger.setdefault(k,dict(last=day,sos=0.,defense=0.,n=0.));d=math.exp(-math.log(2)*features.elapsed(day,s['last'])/540)
   for key in ['sos','defense','n']:s[key]*=d
   s['sos']+=old[1-i][0];s['n']+=1
   own,opp=b['stats'][i],b['stats'][1-i]
   if own and opp and not own.get('incomplete')and not opp.get('incomplete')and b['minutes']>0:s['defense']+=old[1-i][8]-opp['sig']/b['minutes']
   s['last']=day
  state.update(b)
y=np.array([b['y']for b in ordered]);days=np.array([b['date']for b in ordered]);tr=days<'2023-01-01';cal=(days>='2023-01-01')&(days<'2024-01-01');val=(days>='2024-01-01')&(days<'2024-11-01');reports={};losses={}
for name,z in [('baseline',X),('opponent_challenger',np.column_stack([X,extras]))]:
 m=model.fit('logistic',z[tr],y[tr]);t=model.temperature(y[cal],model.probability(m,z[cal],'logistic'));p=model.probability(m,z[val],'logistic',t);reports[name]=dict(temperature=t,metrics=model.metrics(y[val],p));losses[name]=-(y[val]*np.log(p)+(1-y[val])*np.log(1-p))
diff=losses['opponent_challenger']-losses['baseline'];groups=[diff[days[val]==d].mean()for d in np.unique(days[val])];se=np.std(groups,ddof=1)/np.sqrt(len(groups));reports['selection']=dict(mean_logloss_change=float(diff.mean()),paired_event_se=float(se),passed=bool(diff.mean()<-se and reports['opponent_challenger']['metrics']['brier']<=reports['baseline']['metrics']['brier']),rule='Require log-loss improvement greater than one paired event standard error and no worse Brier on Jan-Oct 2024 development validation; no recent diagnostic used for selection.')
Path('out/ufc').mkdir(parents=True,exist_ok=True)
Path('out/ufc/opponent-challenger.json').write_text(json.dumps(reports,indent=2)+'\n');print(json.dumps({k:{'log_loss':v['metrics']['log_loss'],'brier':v['metrics']['brier']}for k,v in reports.items()if k!='selection'}));print(reports['selection'])
