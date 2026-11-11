"""Opponent-adjusted efficiency and tempo; exclusively earlier final box scores."""
import datetime as dt
import hashlib
from collections import Counter
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from cfb.model import digest
from .sources import instant,season_for
VERSION='cbb-1.0.0'
SIMS=300_000


def phase(date):
    return 'opening'if instant(date).month==11 else'established'


class Ratings:
    def __init__(self,games,cutoff,ridge=8.,retention=.25):
        self.cutoff=instant(cutoff)if isinstance(cutoff,str)else cutoff;self.season=season_for(self.cutoff)
        games=[g for g in games if g['complete']and instant(g['date'])+dt.timedelta(hours=4)<self.cutoff
               and self.season-2<=g['season']<=self.season]
        if len(games)<200:raise ValueError('Insufficient possession/score history')
        self.teams=sorted({g[s]for g in games for s in ['home','away']});self.ids={t:i for i,t in enumerate(self.teams)};n=len(self.teams);self.n=n
        self.counts=Counter();self.used_ids=sorted(g['id']for g in games)
        rr=[];cc=[];vv=[];y=[];weights=[];pr=[];pc=[];pv=[];py=[];pw=[]
        for g in games:
            w=retention**(self.season-g['season']);h,a=self.ids[g['home']],self.ids[g['away']]
            if g['season']==self.season:self.counts.update([g['home'],g['away']])
            for side,other,sign in [('home','away',1),('away','home',-1)]:
                idx=len(y);rr.extend([idx]*4);cc.extend([0,1,2+self.ids[g[side]],2+n+self.ids[g[other]]]);vv.extend([1,0 if g['neutral']else sign/2,1,1])
                y.append(100*g[side+'_score']/g['possessions']);weights.append(w)
            idx=len(py);pr.extend([idx]*3);pc.extend([0,1+h,1+a]);pv.extend([1,.5,.5]);py.append(g['pace']);pw.append(w)
        X=sparse.csr_matrix((vv,(rr,cc)),shape=(len(y),2+2*n));W=sparse.diags(weights)
        self.coef=spsolve(X.T@W@X+sparse.diags([.001,25.]+[ridge]*(2*n)),X.T@(np.array(y)*weights))
        P=sparse.csr_matrix((pv,(pr,pc)),shape=(len(py),1+n));W=sparse.diags(pw)
        self.tempo=spsolve(P.T@W@P+sparse.diags([.001]+[ridge/4]*n),P.T@(np.array(py)*pw))

    def predict(self,g):
        if any(g[s]not in self.ids for s in ['home','away']):raise ValueError('No eligible history for a team')
        h,a=self.ids[g['home']],self.ids[g['away']];b=self.coef;n=self.n
        pace=float(self.tempo[0]+.5*(self.tempo[1+h]+self.tempo[1+a]))
        efficiency=np.array([b[0]+b[2+h]+b[2+n+a],b[0]+b[2+a]+b[2+n+h]])
        if not g['neutral']:efficiency+=np.array([b[1]/2,-b[1]/2])
        if not 40<pace<110 or not np.all((efficiency>40)&(efficiency<170)):raise ValueError('Unstable tempo/efficiency projection')
        return efficiency*pace/100,pace,efficiency


def walk_forward(games,ridge=8.,retention=.25,first_season=2024):
    groups={};rows=[]
    for g in games:
        if g['season']>=first_season:
            date=instant(g['date']);monday=date.date()-dt.timedelta(days=date.weekday())
            groups.setdefault((g['season'],monday),[]).append(g)
    for _,group in sorted(groups.items(),key=lambda v:min(g['date']for g in v[1])):
        cutoff=min(instant(g['date'])for g in group);fit=Ratings(games,cutoff,ridge,retention)
        for g in group:
            try:mu,pace,eff=fit.predict(g)
            except ValueError:continue
            rows.append({'id':g['id'],'season':g['season'],'date':g['date'],'phase':phase(g['date']),
                         'cutoff':cutoff.isoformat(),'mu':mu.tolist(),'actual':[g['home_score'],g['away_score']]})
    return rows


def residuals_before(rows,cutoff,stage=None):
    return np.array([np.array(r['actual'])-np.array(r['mu'])for r in rows
                     if instant(r['date'])+dt.timedelta(hours=4)<cutoff and (stage is None or r['phase']==stage)])


def simulate(mu,errors,seed,count=SIMS):
    if len(errors)<200:raise ValueError('Insufficient chronological phase-specific errors')
    rng=np.random.default_rng(seed)
    draws=np.maximum(0,np.rint(mu+errors[rng.integers(0,len(errors),count)]+rng.uniform(-.5,.5,(count,2)))).astype(int)
    ties=np.flatnonzero(draws[:,0]==draws[:,1]);draws[ties,rng.integers(0,2,len(ties))]+=rng.integers(1,8,len(ties))
    return draws


def forecast(g,fit,errors,snapshot_hash,count=SIMS):
    mu,pace,eff=fit.predict(g);seed=int(hashlib.sha256((snapshot_hash+g['id']).encode()).hexdigest()[:16],16)
    draws=simulate(mu,errors,seed,count);score=np.rint(np.mean(draws,axis=0)).astype(int)
    if score[0]==score[1]:score[int(np.mean(draws[:,0]>draws[:,1])<.5)]+=1
    return {'id':g['id'],'mean':np.mean(draws,axis=0).round(3).tolist(),'score':score.tolist(),'home_win':float(np.mean(draws[:,0]>draws[:,1])),
            'simulations':len(draws),'pace':pace,'efficiency':eff.tolist(),'phase':phase(g['date']),
            'current_games':{s:fit.counts[g[s]]for s in ['home','away']},'interval80':np.quantile(draws,[.1,.9],axis=0).round(1).tolist()},draws


def evaluate(rows,season):
    metrics=[];pools={}
    for r in rows:
        if r['season']!=season:continue
        key=(r['cutoff'],r['phase'])
        if key not in pools:pools[key]=residuals_before(rows,instant(r['cutoff']),r['phase'])
        errors=pools[key]
        if len(errors)<200:continue
        draws=simulate(np.array(r['mu']),errors,int(r['id']),4000);p=np.clip(np.mean(draws[:,0]>draws[:,1]),.005,.995)
        h,a=r['actual'];y=int(h>a);pred=draws.mean(axis=0);lo,hi=np.quantile(draws[:,0]-draws[:,1],[.1,.9])
        metrics.append([(p-y)**2,-y*np.log(p)-(1-y)*np.log(1-p),(p>.5)==bool(y),abs(pred[0]-pred[1]-h+a),abs(sum(pred)-h-a),lo<=h-a<=hi])
    if not metrics:return {'games':0}
    v=np.mean(metrics,axis=0)
    return dict(games=len(metrics),**{k:float(x)for k,x in zip(['winner_brier','winner_log_loss','winner_accuracy','margin_mae','total_mae','margin_interval80_coverage'],v)})
