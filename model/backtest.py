"""Walk-forward backtest of v6 (every prediction uses only data from earlier weeks).
Usage: python3 backtest.py [--nsim 20000]"""
import numpy as np, pandas as pd, json, sys, core, sim
cfg=json.load(open('config.json')); NS=int(sys.argv[sys.argv.index('--nsim')+1]) if '--nsim' in sys.argv else 20000
def point_preds(cfg):
    F=core.build_feats(cfg['ratings'],tmin=cfg['train_min_t'])
    G=core.fit_predict(F,cfg['features'],alpha=cfg['reg_alpha'],train_min=cfg['train_min_t'])
    G['pred']=G.pred-cfg['hfa_shrink']*G.home
    return G
if __name__=='__main__':
    G=point_preds(cfg); A=G[G.pred.notna()&G.pts.notna()]
    h=A[A.side=='home'].set_index('game_id'); a=A[A.side=='away'].set_index('game_id')
    m=h.join(a,lsuffix='_h',rsuffix='_a',how='inner'); cal=json.load(open('sim_cal.json')); rows=[]
    for i,(gid,r) in enumerate(m.iterrows()):
        poss=float(r.pace_h)  # mean drives/team for the two teams
        o=sim.simulate(r.pred_a,r.pred_h,poss=poss,N=NS,seed=1000+i,cal=cal)
        sA=o['sA'].astype(int); sH=o['sH'].astype(int); aa,ah=r.pts_a,r.pts_h
        pit=lambda s,v:(s<v).mean()+0.5*(s==v).mean()
        rows.append(dict(game_id=gid,season=r.season_h,week=r.week_h,away=r.team_a,home=r.team_h,mu_a=r.pred_a,mu_h=r.pred_h,
            med_a=np.median(sA),med_h=np.median(sH),pA=(sA>sH).mean()+0.5*(sA==sH).mean(),act_a=aa,act_h=ah,
            pitA=pit(sA,aa),pitH=pit(sH,ah),pitT=pit(sA+sH,aa+ah),pitM=pit(sA-sH,aa-ah)))
    B=pd.DataFrame(rows); B.to_csv('backtest_v6.csv',index=False)
    def summ(X):
        y=(X.act_a>X.act_h)+0.5*(X.act_a==X.act_h); p=np.r_[X.pitA,X.pitH]
        return dict(games=len(X),comb_MAE_median=(abs(X.med_a-X.act_a)+abs(X.med_h-X.act_h)).mean(),
          comb_MAE_mean=(abs(X.mu_a-X.act_a)+abs(X.mu_h-X.act_h)).mean(),
          total_MAE=abs(X.mu_a+X.mu_h-X.act_a-X.act_h).mean(),total_bias=(X.mu_a+X.mu_h-X.act_a-X.act_h).mean(),
          margin_MAE=abs(X.mu_a-X.mu_h-(X.act_a-X.act_h)).mean(),winner_acc=((X.pA>.5)==(X.act_a>X.act_h)).mean(),
          brier=((X.pA-y)**2).mean(),team_in50=((p>.25)&(p<.75)).mean(),team_in80=((p>.1)&(p<.9)).mean(),
          total_in80=((X.pitT>.1)&(X.pitT<.9)).mean(),margin_in80=((X.pitM>.1)&(X.pitM<.9)).mean())
    out={}
    for lab,msk in [('2025_all',B.season==2025),('2026_w1-4_tune',(B.season==2026)&(B.week<=4)),('2026_w5-7_HOLDOUT',(B.season==2026)&(B.week>=5)),
                    ('2026_w3-7',(B.season==2026)&(B.week>=3)),('2026_w7_13games',(B.season==2026)&(B.week==7)&(B.away!='NE'))]:
        out[lab]={k:round(float(v),4) for k,v in summ(B[msk]).items()}
    json.dump(out,open('backtest_v6_summary.json','w'),indent=1); print(json.dumps(out,indent=1))
