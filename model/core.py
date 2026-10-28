"""v6 core: opponent-adjusted weighted ridge ratings (pass/rush EPA, points/drive, points),
QB-specific starter adjustment, walk-forward stacked linear points model. No market inputs."""
import numpy as np, pandas as pd
from data import load_games
T=pd.read_parquet('teamgames.parquet'); Q=pd.read_parquet('qbgames.parquet'); G=load_games()
TEAMS=sorted(T.posteam.unique()); IDX={t:i for i,t in enumerate(TEAMS)}; NT=len(TEAMS)
T['o']=T.posteam.map(IDX); T['d']=T.defteam.map(IDX)
T['ep']=T.sp/T.np.clip(lower=1); T['er']=T.sr/T.nr.clip(lower=1); T['ppd']=T.dpts/T.rdrives.clip(lower=1)
def ridge(o,d,h,y,w,lam):
    n=NT; k=2*n+1; M=np.zeros((k,k)); b=np.zeros(k)
    mu=np.average(y,weights=w); y=y-mu
    np.add.at(M,(o,o),w); np.add.at(M,(n+d,n+d),w); np.add.at(M,(o,n+d),w); np.add.at(M,(n+d,o),w)
    np.add.at(M,(o,np.full_like(o,2*n)),w*h); np.add.at(M,(n+d,np.full_like(o,2*n)),w*h)
    M[2*n,:2*n]=M[:2*n,2*n]; M[2*n,2*n]=np.sum(w*h*h)+1e-6
    np.add.at(b,o,w*y); np.add.at(b,n+d,w*y); b[2*n]=np.sum(w*y*h)
    M[np.arange(2*n),np.arange(2*n)]+=lam
    s=np.linalg.solve(M,b); return s[:n],s[n:2*n],s[2*n],mu
def gweights(df,t,season,P):
    w=P['decay']**(t-df.t.values).astype(float)
    w=w*np.where(df.season.values<season,P['prior'],1.0)
    return w
def ratings(t,season,P):
    x=T[T.t<t]; w=gweights(x,t,season,P); o=x.o.values; d=x.d.values; h=x.home.values.astype(float)
    R={}
    R['p']=ridge(o,d,h,x.ep.values,w*x.np.values,P['lam_p'])
    R['r']=ridge(o,d,h,x.er.values,w*x.nr.values,P['lam_r'])
    R['d']=ridge(o,d,h,x.ppd.values,w*x.rdrives.values,P['lam_d'])
    R['s']=ridge(o,d,h,x.pts.values.astype(float),w,P['lam_s'])
    # pace: weighted drives/game per team (offense+defense)
    dr=pd.Series(w*x.drives.values).groupby(x.o.values).sum()/pd.Series(w).groupby(x.o.values).sum()
    R['pace']=dr.reindex(range(NT)).fillna(dr.mean()).values
    # QB table
    q=Q[Q.t<t]; wq=gweights(q,t,season,P)*q.n.values
    qs=pd.DataFrame({'id':q.passer_player_id.values,'tm':q.posteam.values,'w':wq,'s':gweights(q,t,season,P)*q.s.values})
    a=qs.groupby('id')[['w','s']].sum()
    a['r']=(a.s+P['qb_prior']*P['qb_k'])/(a.w+P['qb_k'])
    R['qb']=a.r
    qs['r']=qs.id.map(a.r); mix=(qs.r*qs.w).groupby(qs.tm).sum()/qs.groupby('tm').w.sum()
    R['mix']=mix; R['qb_prior']=P['qb_prior']
    return R
def team_feats(R,off,de,home,qb_id):
    io,idd=IDX[off],IDX[de]; f={}
    for k in 'prds':
        oo,dd,hh,mu=R[k]; f['f_'+k]=mu+oo[io]+dd[idd]+hh*home
        f['r_'+k]=oo[io]+dd[idd]; f['o_'+k]=oo[io]; f['d_'+k]=dd[idd]
    f['env']=R['s'][3]; f['hfa_s']=R['s'][2]*home
    qr=R['qb'].get(qb_id,R['qb_prior']) if isinstance(qb_id,str) else R['mix'].get(off,R['qb_prior'])
    f['qb']=qr-R['mix'].get(off,R['qb_prior'])
    f['pace']=(R['pace'][io]+R['pace'][idd])/2
    f['home']=home
    return f
FEATS=['f_p','f_r','f_d','f_s','qb','pace','home','rest']
def build_feats(P,tmin=22):
    """For each team-game with t>=tmin, compute pre-game features using only data with t'<t."""
    rows=[]
    for t in sorted(G[G.t>=tmin].t.unique()):
        gg=G[G.t==t]; season=int(gg.season.iloc[0]); R=ratings(t,season,P)
        for _,g in gg.iterrows():
            neu=g.location=='Neutral'
            for side in ('home','away'):
                off=g[f'{side}_team']; de=g['away_team' if side=='home' else 'home_team']
                hm=0 if neu else (1 if side=='home' else -1)
                f=team_feats(R,off,de,hm,g.get(f'{side}_qb_id'))
                f['rest']=(g.home_rest-g.away_rest)*(1 if side=='home' else -1)
                f.update(game_id=g.game_id,t=t,season=season,week=g.week,team=off,opp=de,side=side,
                         pts=g[f'{side}_score'])
                rows.append(f)
    return pd.DataFrame(rows)
def fit_predict(F,feats,alpha=1.0,train_min=22,lw=1.0):
    """walk-forward: for each week t, fit ridge-regression pts~feats on games with t'<t (t'>=train_min), predict t."""
    F=F.copy(); F['pred']=np.nan
    for t in sorted(F.t.unique()):
        tr=F[(F.t<t)&(F.t>=train_min)&F.pts.notna()]
        if len(tr)<150: continue
        X=tr[feats].values; mu=X.mean(0); sd=X.std(0)+1e-9; Z=(X-mu)/sd
        wt=lw**(t-tr.t.values)
        A=np.c_[np.ones(len(Z)),Z]; W=np.diag(wt) if False else None
        Aw=A*wt[:,None]; reg=alpha*np.eye(A.shape[1]); reg[0,0]=0
        beta=np.linalg.solve(A.T@Aw+reg,Aw.T@tr.pts.values)
        te=F.t==t; Zt=(F.loc[te,feats].values-mu)/sd
        F.loc[te,'pred']=np.c_[np.ones(te.sum()),Zt]@beta
    return F
