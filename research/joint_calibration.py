import pathlib,sys,os,json
import numpy as np,pandas as pd
ROOT=pathlib.Path(__file__).resolve().parents[1];os.chdir(ROOT/'model');sys.path.insert(0,str(ROOT/'model'));import sim
cal=json.load(open('sim_cal.json'));sd=cal['sd_game']
def run(k,N,seed):
 rng=np.random.default_rng(seed);z=rng.normal(0,sd,(2,N));m=k[:,None]*np.exp(z-sd*sd/2);D=np.maximum(14,np.round(rng.normal(22,sim.GS['dsd'],N))).astype(int)
 return sim._core(m[0],m[1],D,rng,sim.BASE['fgm'],sim.BASE['fgm'])[:2]
def crps(s,y):
 x=np.sort(s.astype(float));n=len(x);return np.mean(abs(x-y))-np.sum((2*np.arange(1,n+1)-n-1)*x)/(n*n)
a=pd.read_csv(ROOT/'research/current.csv');a=a[(a.season==2025)|((a.season==2026)&a.week.between(5,7))];rows=[]
for i,r in enumerate(a.itertuples()):
 target=np.array([r.mu_a,r.mu_h]);k=np.interp(target,cal['mean'],cal['grid']);s0=run(k,16000,731+i)
 for it in range(3):
  p=run(k,12000,191+i);err=target-np.array([x.mean() for x in p]);slope=np.interp(k,cal['grid'],np.gradient(cal['mean'],cal['grid']));k=np.clip(k+err/slope,.3,2.6)
 s1=run(k,16000,731+i)
 for v,s in [('current',s0),('joint_mean',s1)]:
  sa,sh=s;pa=np.mean(sa>sh)+.5*np.mean(sa==sh);y=float(r.act_a>r.act_h)+.5*float(r.act_a==r.act_h)
  rows.append(dict(season=r.season,week=r.week,variant=v,brier=(pa-y)**2,margin_crps=crps(sh-sa,r.act_h-r.act_a),total_crps=crps(sa+sh,r.act_a+r.act_h),target_error=float(np.abs(np.array([sa.mean(),sh.mean()])-target).mean())))
 if i%50==0:print(i,flush=True)
x=pd.DataFrame(rows);x.to_csv(ROOT/'research/joint-calibration.csv',index=False);out=x.groupby(['season','variant'])[['brier','margin_crps','total_crps','target_error']].mean().reset_index().to_dict('records');(ROOT/'research/joint-calibration.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
