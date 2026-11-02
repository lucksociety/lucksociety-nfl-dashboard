import sys,pathlib,json,copy,os
ROOT=pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT/'model');sys.path.insert(0,str(ROOT/'model'))
import core,numpy as np,pandas as pd
from scipy.special import ndtr
cfg=json.load(open('config.json'))
variants=[('current',1.,100,.9),('recent_stack_098',.98,100,.9),('recent_stack_095',.95,100,.9),('stack_shrink_300',1.,300,.9),('slower_team_decay',1.,100,.95)]
cache={};records={};summary={}
def score(X):
 d=X.mu_h-X.mu_a;actual=X.act_h-X.act_a;p=ndtr(d/12.6);y=(actual>0).astype(float)
 return dict(n=len(X),team_mae=float((abs(X.mu_h-X.act_h)+abs(X.mu_a-X.act_a)).mean()/2),margin_mae=float(abs(d-actual).mean()),total_mae=float(abs(X.mu_h+X.mu_a-X.act_h-X.act_a).mean()),brier_normal_screen=float(((p-y)**2).mean()))
for name,lw,alpha,decay in variants:
 print('START',name,flush=True)
 if decay not in cache:
  ratings=copy.deepcopy(cfg['ratings']);ratings['decay']=decay;cache[decay]=core.build_feats(ratings,tmin=cfg['train_min_t'])
 F=cache[decay];P=core.fit_predict(F,cfg['features'],alpha=alpha,train_min=cfg['train_min_t'],lw=lw);P['pred']-=cfg['hfa_shrink']*P.home
 A=P[P.pred.notna()&P.pts.notna()];h=A[A.side=='home'].set_index('game_id');a=A[A.side=='away'].set_index('game_id');z=h.join(a,lsuffix='_h',rsuffix='_a')
 B=pd.DataFrame(dict(season=z.season_h,week=z.week_h,mu_h=z.pred_h,mu_a=z.pred_a,act_h=z.pts_h,act_a=z.pts_a));records[name]=B
 summary[name]={'selection_2025':score(B[B.season==2025]),'locked_2026_w5_7':score(B[(B.season==2026)&B.week.between(5,7)])}
 B.to_csv(ROOT/'research'/f'{name}.csv');print(name,json.dumps(summary[name]),flush=True)
selected=min(summary,key=lambda n:summary[n]['selection_2025']['brier_normal_screen'])
(ROOT/'research/point-screen.json').write_text(json.dumps(dict(protocol='Choose from five preregistered point-model variants on 2025 only; report 2026 weeks 5–7 without selecting on them. November 1 excluded. Normal probabilities are screening only, not deployment validation.',selected=selected,variants=summary),indent=2))
print('SELECTED',selected,flush=True)
