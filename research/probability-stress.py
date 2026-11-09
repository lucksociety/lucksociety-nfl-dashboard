"""Market-free diagnostic reserve, selected on 2025 only; 2026 weeks 5–7 reported separately.
Fixed half-point lines are diagnostics, not independent bets or executable historical prices.
Usage: python research/probability-stress.py --data chronological-points.csv --out result.json
"""
import argparse,json,sys,math,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model.sim import simulate
ap=argparse.ArgumentParser();ap.add_argument('--data',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
df=pd.read_csv(args.data);df=df[(df.season==2025)|((df.season==2026)&df.week.between(5,7))]
groups={k:{} for k in ['moneyline','spreads','totals']};tests={k:[] for k in groups}
for _,r in df.iterrows():
 simulation=simulate(r.mu_a,r.mu_h,N=16000,seed=int.from_bytes(hashlib.sha256(r.game_id.encode()).digest()[:4],'big'))
 a,h=simulation['sA'].astype(int),simulation['sH'].astype(int)
 for kind in groups:
  if kind=='moneyline':
   if r.act_h==r.act_a:continue
   probs=np.array([(h>a).mean()]);actual=np.array([float(r.act_h>r.act_a)])
  else:
   lines=np.arange(-21.5,22,1) if kind=='spreads' else np.arange(19.5,66,1)
   values=h-a if kind=='spreads' else h+a;observed=r.act_h-r.act_a if kind=='spreads' else r.act_h+r.act_a
   probs=np.array([(values>line).mean() for line in lines]);actual=np.array([float(observed>line) for line in lines])
  favored=np.maximum(probs,1-probs);wins=np.where(probs>=.5,actual,1-actual)
  error=float(np.mean(favored-wins))
  if r.season==2025:groups[kind].setdefault(int(r.week),[]).append(error)
  else:tests[kind].append(error)
result={'input_sha256':hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),'protocol':'2025 chronological points replay; fixed half-point diagnostic lines; week-cluster bootstrap. No November outcomes or market prices select reserves. Not an individual confidence bound or evidence of profitability. 2026 weeks 5–7 are previously used research data, not a new untouched holdout.','simulation_draws_per_game':16000,'selection_games':int((df.season==2025).sum()),'comparison_games':int((df.season==2026).sum()),'families':{}}
for kind,byweek in groups.items():
 rng=np.random.default_rng(20261109);vals=list(byweek.values());boot=[]
 for _ in range(3000):boot.append(np.mean([v for i in rng.choice(len(vals),len(vals)) for v in vals[i]]))
 upper=float(np.quantile(boot,.975));result['families'][kind]={'selection_mean_overconfidence':float(np.mean([v for xs in vals for v in xs])),'bootstrap_upper_975':upper,'rounded_reserve':math.ceil(max(0,upper)*1000)/1000,'comparison_mean_overconfidence':float(np.mean(tests[kind]))}
Path(args.out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
