"""Variance challenger: select on early 2025, confirm late 2025; never tune to Nov15."""
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));from model.sim import simulate,calibrate
ROOT=Path(__file__).resolve().parents[1];df=pd.read_csv(ROOT/'research/probability-stress-inputs.csv');baseline=json.loads((ROOT/'model/sim_cal.json').read_text());variants={'baseline':baseline,'sd012':calibrate(.12,N=20000),'sd016':calibrate(.16,N=20000)};records=[]
def crps(sample,y):
 x=np.sort(sample.astype(float));n=len(x);return float(np.abs(x-y).mean()-np.dot(2*np.arange(n)+1-n,x)/(n*n))
for i,r in enumerate(df.itertuples()):
 for label,cal in variants.items():
  s=simulate(r.mu_a,r.mu_h,N=8000,seed=731+i,cal=cal);a=s['sA'].astype(int);h=s['sH'].astype(int);ph=(h>a).mean()+.5*(h==a).mean();y=float(r.act_h>r.act_a)+.5*float(r.act_h==r.act_a)
  records.append(dict(season=int(r.season),week=int(r.week),variant=label,brier=float((ph-y)**2),margin_crps=crps(h-a,r.act_h-r.act_a),total_crps=crps(h+a,r.act_h+r.act_a)))
 if i%100==0:print('Games',i,flush=True)
x=pd.DataFrame(records);out={}
for name,mask in [('selection_2025_w1_9',(x.season==2025)&(x.week<=9)),('confirmation_2025_w10_18',(x.season==2025)&(x.week>=10)),('diagnostic_2026',(x.season==2026))]:out[name]=x[mask].groupby('variant')[['brier','margin_crps','total_crps']].mean().to_dict('index')
selected=min(out['selection_2025_w1_9'],key=lambda k:out['selection_2025_w1_9'][k]['margin_crps']);out['selected']=selected
z=x[(x.season==2025)&(x.week>=10)];p=z.pivot(index=['season','week'],columns='variant',values='margin_crps') if False else z.groupby(['week','variant']).margin_crps.mean().unstack();delta=p[selected]-p.baseline;se=float(delta.std(ddof=1)/np.sqrt(len(delta)))
out['confirmation']={'margin_crps_change':float(delta.mean()),'week_se':se,'promote':bool(selected!='baseline'and delta.mean()<-1.96*se and out['confirmation_2025_w10_18'][selected]['brier']<=out['confirmation_2025_w10_18']['baseline']['brier']and out['confirmation_2025_w10_18'][selected]['total_crps']<=out['confirmation_2025_w10_18']['baseline']['total_crps'])}
out['protocol']='Early/late 2025 split of existing inspected chronological replay; confirmation requires 95% week-cluster improvement and no worse winner Brier/total CRPS. 2026 diagnostic not used for selection; no Nov 2026 outcomes.';out['input_sha256']=hashlib.sha256((ROOT/'research/probability-stress-inputs.csv').read_bytes()).hexdigest();(ROOT/'research/variance-screen-nov16.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
