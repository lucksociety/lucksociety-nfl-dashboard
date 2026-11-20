"""Chronological matchup-conditioned residual screen; no market data or bets.

Choose on 2025 only. Later seasons are confirmation, not retuning data.
"""
import json, datetime as dt
from pathlib import Path
import numpy as np
from .sources import archive_games, download_frame, instant
from .model import walk_forward
ROOT=Path(__file__).resolve().parent

def weights(mu, contexts, margin_band=None,total_band=None):
    n=len(contexts)
    if not margin_band and not total_band:return np.full(n,1/n)
    d=np.zeros(n)
    if margin_band:d+=((contexts[:,0]-contexts[:,1]-(mu[0]-mu[1]))/margin_band)**2
    if total_band:d+=((contexts.sum(axis=1)-sum(mu))/total_band)**2
    w=np.exp(-.5*d);w=w/w.sum()if w.sum()>1e-12 else np.full(n,1/n)
    return .25/n+.75*w

def crps(values,w,target,order):
    x=values[order];p=w[order]
    return float(np.dot(w,np.abs(values-target))-np.sum(p*x*(2*np.cumsum(p)-p-1)))

def main():
    dest=ROOT/'data/research-residuals.json'
    if dest.exists():rows=json.loads(dest.read_text())
    else:
        games=[]
        for y in range(2023,2028):
            games+=archive_games(download_frame('team',y,ROOT/'data'),download_frame('schedule',y,ROOT/'data'),y)
        # The evaluation snapshot stops before the user-requested change date.
        games=[g for g in games if instant(g['date'])<dt.datetime(2026,11,20,tzinfo=dt.timezone.utc)]
        rows=walk_forward(games,ridge=4,retention=.25)
        dest.write_text(json.dumps(rows))
    configs={'baseline':(None,None),'margin20':(20,None),'margin30_total20':(30,20),'total20':(None,20)}
    result={};cache={}
    for season in [2025,2026,2027]:
        selected=[r for r in rows if r['season']==season]
        values={c:[]for c in configs}
        for r in selected:
            key=(r['cutoff'],r['phase'])
            if key not in cache:
                past=[x for x in rows if x['phase']==r['phase']and instant(x['date'])+dt.timedelta(hours=4)<instant(r['cutoff'])]
                context=np.array([x['mu']for x in past]);errors=np.array([np.array(x['actual'])-x['mu']for x in past])
                if len(past)<200:cache[key]=None
                else:
                    mar=errors[:,0]-errors[:,1];total=errors.sum(axis=1)
                    cache[key]=(context,errors,mar,total,np.argsort(mar),np.argsort(total))
            if cache[key]is None:continue
            context,errors,mar,total,om,ot=cache[key];mu=np.array(r['mu']);actual=np.array(r['actual']);y=actual[0]>actual[1]
            for name,(mb,tb)in configs.items():
                w=weights(mu,context,mb,tb);margin=mu[0]-mu[1]
                p=np.clip(w[mar+margin>0].sum()+.5*w[mar+margin==0].sum(),.005,.995)
                loss=-np.log(p if y else 1-p)
                values[name].append([loss,(p-y)**2,crps(mar,w,actual[0]-actual[1]-margin,om),
                    crps(total,w,actual.sum()-mu.sum(),ot)])
        result[str(season)]={}
        base=np.array(values['baseline'])
        for name,v in values.items():
            a=np.array(v);delta=a-base
            result[str(season)][name]=dict(n=len(a),metrics=dict(zip(['log_loss','brier','margin_crps','total_crps'],a.mean(axis=0).tolist())),
                delta=delta.mean(axis=0).tolist(),paired_se=(delta.std(axis=0,ddof=1)/len(a)**.5).tolist())
        print(season,json.dumps(result[str(season)]),flush=True)
    Path('cbb/data/error-screen-nov20.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
