"""Predict an upcoming week with v6.
python3 predict.py --season 2026 --week 8 [--starters starters.json] [--adj adj.json] [--nsim 100000]
starters.json: {"TEAM": "QB full or abbreviated name as in pbp (e.g. 'C.Keenum') or gsis id"}  -> QB-specific adjustment
adj.json: {"TEAM": {"off": -1.5, "def": 0.5}}  points; off = change to TEAM's points, def = change to OPPONENT's points
          (use for injuries NOT already reflected in recent games; v6 caps each at +/-4)."""
import numpy as np,pandas as pd,json,sys,core,sim
def arg(k,d=None): return sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
cfg=json.load(open('config.json')); season=int(arg('--season',2026)); week=int(arg('--week')); NS=int(arg('--nsim',100000))
starters=json.load(open(arg('--starters'))) if arg('--starters') else {}
adj=json.load(open(arg('--adj'))) if arg('--adj') else {}
t=(season-2023)*18+week
# training rows: historical walk-forward features (same as backtest) for t'<t
F=core.build_feats(cfg['ratings'],tmin=cfg['train_min_t'])
R=core.ratings(t,season,cfg['ratings']); gg=core.G[core.G.t==t]
def resolve(team,q):
    if q is None: return None
    Q=core.Q[(core.Q.posteam==team)|(core.Q.passer_player_id==q)|(core.Q.name==q)]
    hit=core.Q[(core.Q.passer_player_id==q)|(core.Q.name==q)]
    return hit.passer_player_id.mode()[0] if len(hit) else None
rows=[]
for _,g in gg.iterrows():
    neu=g.location=='Neutral'
    for side in ('home','away'):
        off=g[f'{side}_team']; de=g['away_team' if side=='home' else 'home_team']; hm=0 if neu else (1 if side=='home' else -1)
        qid=resolve(off,starters.get(off)) if off in starters else g.get(f'{side}_qb_id'); f=core.team_feats(R,off,de,hm,qid)
        f['rest']=(g.home_rest-g.away_rest)*(1 if side=='home' else -1)
        f.update(game_id=g.game_id,t=t,team=off,opp=de,side=side,pts=np.nan,qb_used=qid,season=season,week=week); rows.append(f)
X=pd.DataFrame(rows); FF=pd.concat([F[F.t<t],X],ignore_index=True)
P=core.fit_predict(FF,cfg['features'],alpha=cfg['reg_alpha'],train_min=cfg['train_min_t'])
P=P[P.t==t].copy(); P['pred']=P.pred-cfg['hfa_shrink']*P.home
cap=lambda v:float(np.clip(v,-4,4))
for i,r in P.iterrows():
    P.loc[i,'pred']+=cap(adj.get(r.team,{}).get('off',0))+cap(adj.get(r.opp,{}).get('def',0))
cal=json.load(open('sim_cal.json')); out=[]
for k,(gid,z) in enumerate(P.groupby('game_id',sort=False)):
    h=z[z.side=='home'].iloc[0]; a=z[z.side=='away'].iloc[0]
    o=sim.simulate(a.pred,h.pred,poss=float(cal.get("poss",11.0)),N=NS,seed=t*1000+k,cal=cal); sA=o['sA'].astype(int); sH=o['sH'].astype(int)
    j=pd.Series(list(zip(sA,sH))).value_counts(normalize=True)
    out.append(dict(game_id=gid,away=a.team,home=h.team,mu_away=round(a.pred,1),mu_home=round(h.pred,1),
        primary=f"{round(a.pred)}-{round(h.pred)}",modal=f"{j.index[0][0]}-{j.index[0][1]}",p_away=round((sA>sH).mean(),3),p_home=round((sH>sA).mean(),3),
        ot=round(float(o['ot'].mean()),3),ci80_away=[int(np.percentile(sA,10)),int(np.percentile(sA,90))],ci80_home=[int(np.percentile(sH,10)),int(np.percentile(sH,90))],
        top10=[(int(s[0]),int(s[1]),round(float(p)*100,2)) for s,p in j.head(10).items()],qb_away=a.qb_used,qb_home=h.qb_used,
        qb_adj_away=round(a.qb,3),qb_adj_home=round(h.qb,3),seed=t*1000+k,nsim=NS))
json.dump(out,open(f'pred_{season}_w{week}.json','w'),indent=1)
for r in out: print(f"{r['away']:>4} @ {r['home']:<4} primary {r['primary']:>6}  mean {r['mu_away']}-{r['mu_home']}  win {r['p_away']:.2f}/{r['p_home']:.2f}  modal {r['modal']}")
